import xmlrpc.client
import json
import base64
import requests
import os
import random
import argparse
from datetime import datetime, timedelta

# Configuration
URL = os.environ['ODOO_URL'].strip()
DB = os.environ['ODOO_DB'].strip()
USER = os.environ['ODOO_USER'].strip()
PASS = os.environ['ODOO_PASS'].strip()

def safe_execute(models, db, uid, password, model, method, *args, **kwargs):
    try:
        return models.execute_kw(db, uid, password, model, method, *args, **kwargs)
    except Exception as e:
        if "cannot marshal None" in str(e):
            return True
        raise e

def get_uid():
    proxy = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', allow_none=True)
    return proxy.authenticate(DB, USER, PASS, {})

def search_or_create(models, uid, password, model, domain, create_vals):
    ids = models.execute_kw(DB, uid, password, model, 'search', [domain], {'limit': 1})
    if ids:
        return ids[0]
    return models.execute_kw(DB, uid, password, model, 'create', [create_vals])


def setup_accounting(models, uid, password):
    print('Bootstrapping accounting configuration...')

    account_map = {
        'income_account': {'code': '700000', 'name': 'Sales Revenue', 'account_type': 'income', 'reconcile': False},
        'receivable_account': {'code': '411000', 'name': 'Trade Receivables', 'account_type': 'asset_receivable', 'reconcile': True},
        'expense_account': {'code': '600000', 'name': 'Expenses', 'account_type': 'expense', 'reconcile': False},
        'payable_account': {'code': '401000', 'name': 'Trade Payables', 'account_type': 'liability_payable', 'reconcile': True},
    }
    accounts = {}
    for key, data in account_map.items():
        domain = [('code', '=', data['code'])]
        accounts[key] = search_or_create(
            models, uid, password,
            'account.account',
            domain,
            data
        )

    journal_map = {
        'sale_journal': {'type': 'sale', 'code': 'INV', 'name': 'Customer Invoices', 'default_account_id': accounts['income_account']},
        'purchase_journal': {'type': 'purchase', 'code': 'PUR', 'name': 'Supplier Invoices'},
        'bank_journal': {'type': 'bank', 'code': 'BNK', 'name': 'Bank'},
        'cash_journal': {'type': 'cash', 'code': 'CAS', 'name': 'Cash'},
    }
    journals = {}
    for key, data in journal_map.items():
        domain = [('code', '=', data['code'])]
        journals[key] = search_or_create(
            models, uid, password,
            'account.journal',
            domain,
            data
        )

    models.execute_kw(DB, uid, password, 'res.company', 'write', [[1], {
        'income_account_id': accounts['income_account'],
        'expense_account_id': accounts['expense_account'],
    }])

    return {
        'income_account_id': accounts['income_account'],
        'receivable_account_id': accounts['receivable_account'],
        'expense_account_id': accounts['expense_account'],
        'payable_account_id': accounts['payable_account'],
        'sale_journal_id': journals['sale_journal'],
        'purchase_journal_id': journals['purchase_journal'],
        'bank_journal_id': journals['bank_journal'],
        'cash_journal_id': journals['cash_journal'],
    }


def fetch_asset_as_base64(url):
    try:
        req = requests.get(url, timeout=10)
        if req.status_code == 200:
            return base64.b64encode(req.content).decode('utf-8')
    except Exception:
        pass
    return False

def cleanup_data(models, uid, PASS):
    print("Cleaning existing demo data...")
    # Wipe Invoices
    inv_ids = models.execute_kw(DB, uid, PASS, 'account.move', 'search', [[]])
    for i in inv_ids:
        try:
            models.execute_kw(DB, uid, PASS, 'account.move', 'button_draft', [[i]])
            models.execute_kw(DB, uid, PASS, 'account.move', 'unlink', [[i]])
        except Exception:
            try:
                models.execute_kw(DB, uid, PASS, 'account.move', 'unlink', [[i]])
            except Exception:
                pass
    
    # Wipe Sales Orders
    so_ids = models.execute_kw(DB, uid, PASS, 'sale.order', 'search', [[]])
    for s in so_ids:
        try:
            models.execute_kw(DB, uid, PASS, 'sale.order', 'action_cancel', [[s]])
            models.execute_kw(DB, uid, PASS, 'sale.order', 'unlink', [[s]])
        except Exception:
            try:
                models.execute_kw(DB, uid, PASS, 'sale.order', 'unlink', [[s]])
            except Exception:
                pass
    
    # Wipe Partners
    partner_ids = models.execute_kw(DB, uid, PASS, 'res.partner', 'search', [[('id', '>', 10)]])
    for p in partner_ids:
        try:
            models.execute_kw(DB, uid, PASS, 'res.partner', 'unlink', [[p]])
        except Exception:
            pass

def run_industry_loader(path, clean=False):
    uid = get_uid()
    if not uid:
        print("Error: Authentication failed.")
        return

    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)
    
    if clean:
        cleanup_data(models, uid, PASS)

    # 1. Company Configuration
    agency_path = os.path.join(path, 'agency.json')
    if os.path.exists(agency_path):
        with open(agency_path, 'r') as f:
            cfg = json.load(f)
        
        print(f"Configuring Company: {cfg['name']}")
        
        # Resolve Country and Currency
        country_ids = models.execute_kw(DB, uid, PASS, 'res.country', 'search', [[('code', '=', cfg.get('country_code', 'US'))]])
        country_id = country_ids[0] if country_ids else False
        
        # Resolve and Activate Currency (Search inclusive of inactive records)
        currency_code = 'EUR' if cfg.get('country_code') == 'FR' else 'USD'
        currency_ids = models.execute_kw(DB, uid, PASS, 'res.currency', 'search', [[
            ('name', '=ilike', currency_code),
            ('active', 'in', [True, False])
        ]])
        
        if currency_ids:
            currency_id = currency_ids[0]
            models.execute_kw(DB, uid, PASS, 'res.currency', 'write', [[currency_id], {'active': True}])
        else:
            try:
                # Create currency if missing entirely
                currency_id = models.execute_kw(DB, uid, PASS, 'res.currency', 'create', [{
                    'name': currency_code,
                    'symbol': '€' if currency_code == 'EUR' else '$',
                    'active': True
                }])
            except Exception:
                # Last resort fallback to USD (ID 1)
                currency_id = 1

        # Handle Logo (Local file prioritized, then URL)
        logo_data = False
        local_logo = os.path.join(path, 'logo.png')
        if os.path.exists(local_logo):
            with open(local_logo, 'rb') as lf:
                logo_data = base64.b64encode(lf.read()).decode('utf-8')
        elif cfg.get('logo_url'):
            logo_data = fetch_asset_as_base64(cfg['logo_url'])

        models.execute_kw(DB, uid, PASS, 'res.company', 'write', [[1], {
            'name': cfg['name'],
            'street': cfg['street'],
            'city': cfg['city'],
            'zip': cfg['zip'],
            'phone': cfg['phone'],
            'email': cfg['email'],
            'website': cfg['website'],
            'vat': cfg['vat'],
            'company_registry': cfg['company_registry'],
            'country_id': country_id,
            'currency_id': currency_id,
            'logo': logo_data
        }])

    accounting_defaults = setup_accounting(models, uid, PASS)

    # 2. Partners
    clients_path = os.path.join(path, 'clients.json')
    client_ids = []
    if os.path.exists(clients_path):
        with open(clients_path, 'r') as f:
            clients = json.load(f)
        
        print(f"Importing {len(clients)} partners...")
        for c in clients:
            cid = models.execute_kw(DB, uid, PASS, 'res.partner', 'create', [{
                'name': c['name'],
                'is_company': True,
                'street': c['street'],
                'city': c['city'],
                'zip': c['zip'],
                'email': c['email'],
                'phone': c['phone'],
                'vat': c['vat']
            }])
            client_ids.append(cid)

    # 3. Resources
    devs_path = os.path.join(path, 'developers.json')
    if os.path.exists(devs_path):
        with open(devs_path, 'r') as f:
            devs = json.load(f)
        
        print(f"Importing {len(devs)} resources...")
        for d in devs:
            models.execute_kw(DB, uid, PASS, 'res.partner', 'create', [{
                'name': d['name'],
                'function': d.get('job_title', ''),
                'email': d['email'],
                'phone': d['phone'],
                'image_1920': fetch_asset_as_base64(d.get('avatar_url', ''))
            }])

    # 4. Transactions
    if client_ids:
        print("Generating transaction history...")
        income_account = accounting_defaults['income_account_id']

        product_ids = models.execute_kw(DB, uid, PASS, 'product.product', 'search', [[('name', '=', 'Consulting Service'), ('type', '=', 'service')]], {'limit': 1})
        if product_ids:
            pid = product_ids[0]
            models.execute_kw(DB, uid, PASS, 'product.product', 'write', [[pid], {
                'invoice_policy': 'order',
                'property_account_income_id': income_account
            }])
        else:
            pid = models.execute_kw(DB, uid, PASS, 'product.product', 'create', [{
                'name': 'Consulting Service',
                'type': 'service',
                'list_price': 500,
                'property_account_income_id': income_account,
                'invoice_policy': 'order',
            }])

        for i in range(20):
            cid = client_ids[i % len(client_ids)]
            
            # Dates: Emission and Due (20-30 days)
            emission_dt = datetime.now() - timedelta(days=random.randint(10, 150))
            due_dt = emission_dt + timedelta(days=random.randint(20, 30))
            
            emission_str = emission_dt.strftime('%Y-%m-%d')
            due_str = due_dt.strftime('%Y-%m-%d')
            
            so_id = models.execute_kw(DB, uid, PASS, 'sale.order', 'create', [{
                'partner_id': cid,
                'date_order': emission_str + " 09:00:00",
            }])
            
            models.execute_kw(DB, uid, PASS, 'sale.order.line', 'create', [{
                'order_id': so_id,
                'product_id': pid,
                'product_uom_qty': random.randint(1, 22),
                'price_unit': random.choice([400, 550, 700, 850, 1100]),
            }])
            
            models.execute_kw(DB, uid, PASS, 'sale.order', 'action_confirm', [so_id])
            
            wiz_id = models.execute_kw(DB, uid, PASS, 'sale.advance.payment.inv', 'create', [{
                'sale_order_ids': [[6, 0, [so_id]]],
                'advance_payment_method': 'delivered',
            }])
            
            try:
                # Get SO reference for linking and logging
                so_data = models.execute_kw(DB, uid, PASS, 'sale.order', 'read', [so_id], {'fields': ['name', 'order_line']})[0]
                so_ref = so_data['name']
                so_lines = so_data['order_line']

                # Create the invoice record directly with the requested dates
                inv_id = models.execute_kw(DB, uid, PASS, 'account.move', 'create', [{
                    'move_type': 'out_invoice',
                    'partner_id': cid,
                    'invoice_date': emission_str,
                    'date': emission_str,
                    'invoice_date_due': due_str,
                    'invoice_origin': so_ref,
                    'invoice_line_ids': [
                        (0, 0, {
                            'product_id': pid,
                            'quantity': random.randint(1, 10),
                            'price_unit': random.choice([400, 550, 700]),
                            'name': 'Consulting Services',
                            'sale_line_ids': [[6, 0, so_lines]],
                            'account_id': income_account,
                        })
                    ]
                }])
                
                if inv_id:
                    # Post the manually created invoice
                    models.execute_kw(DB, uid, PASS, 'account.move', 'action_post', [[inv_id]])
            except Exception as e:
                print(f"Error creating invoice for {so_ref}: {e}")

    print(f"Industry package '{os.path.basename(path)}' successfully deployed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--industry', type=str, required=True)
    parser.add_argument('--clean', action='store_true', help='Wipe existing demo data before seeding')
    args = parser.parse_args()

    target = f'/tmp/seeds/{args.industry}'
    if not os.path.exists(target):
        target = f'seeds/{args.industry}'
        
    if os.path.exists(target):
        run_industry_loader(target, clean=args.clean)
    else:
        print(f"Error: Data package '{args.industry}' not found.")
