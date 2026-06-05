import xmlrpc.client
import json
import base64
import requests
import os
import random
import subprocess
import argparse
from datetime import datetime, timedelta

# Configuration
URL = os.environ.get('ODOO_URL', 'http://localhost:8069').strip() or 'http://localhost:8069'
USER = os.environ.get('ODOO_USER', 'admin').strip() or 'admin'
PASS = os.environ.get('ODOO_PASS', 'admin').strip() or 'admin'
MASTER_PASS = os.environ.get('ODOO_MASTER_PASSWORD', 'admin').strip() or 'admin'
DB_CONTAINER = os.environ.get('ODOO_DB_CONTAINER', 'odoo-demo-db-1').strip() or 'odoo-demo-db-1'
DB = None  # Set in run_industry_loader from industry name

def drop_database(db_name):
    """Drop database via PostgreSQL container (--clean)."""
    # Terminate active connections first
    subprocess.run(
        ['docker', 'exec', '-i', DB_CONTAINER, 'psql', '-U', 'odoo', '-d', 'postgres', '-c',
         f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db_name}' AND pid <> pg_backend_pid();"],
        capture_output=True
    )
    result = subprocess.run(
        ['docker', 'exec', '-i', DB_CONTAINER, 'psql', '-U', 'odoo', '-d', 'postgres', '-c',
         f'DROP DATABASE IF EXISTS "{db_name}";'],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f'Database {db_name} dropped')
        return True
    print(f'Could not drop database {db_name}: {result.stderr.strip()}')
    return False

def install_modules(db_name, module_names):
    """Install Odoo modules on a fresh database."""
    common = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/common', allow_none=True)
    uid = common.authenticate(db_name, 'admin', 'admin', {})
    if not uid:
        raise Exception(f'Cannot authenticate on {db_name}')

    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)
    for module_name in module_names:
        module_ids = models.execute_kw(db_name, uid, 'admin', 'ir.module.module', 'search', [[('name', '=', module_name)]])
        if not module_ids:
            print(f'  Module {module_name} not found, skipping')
            continue
        state = models.execute_kw(db_name, uid, 'admin', 'ir.module.module', 'read', [module_ids, ['state']])
        if state[0]['state'] == 'installed':
            print(f'  Module {module_name} already installed')
            continue
        print(f'  Installing module: {module_name}')
        models.execute_kw(db_name, uid, 'admin', 'ir.module.module', 'button_immediate_install', [module_ids])
        print(f'  Module {module_name} installed')

def ensure_database(industry_name):
    """Create the industry database if it doesn't exist."""
    global DB
    db_name = DB  # Already set by run_industry_loader

    # Check if database exists via JSON-RPC
    resp = requests.post(f'{URL}/jsonrpc', json={
        'jsonrpc': '2.0', 'method': 'call',
        'params': {'service': 'db', 'method': 'db_exist', 'args': [db_name]},
        'id': 1
    }).json()

    if resp.get('result'):
        print(f'Using database: {db_name}')
        return

    # Create the database
    print(f'Creating database: {db_name}')
    resp = requests.post(f'{URL}/jsonrpc', json={
        'jsonrpc': '2.0', 'method': 'call',
        'params': {'service': 'db', 'method': 'create_database', 'args': [MASTER_PASS, db_name, False, 'en_US', 'admin']},
        'id': 1
    }).json()

    if resp.get('result') is False:
        raise Exception(f'Failed to create database: {resp}')

    print(f'Database {db_name} created')
    install_modules(db_name, ['sale'])

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
        accounts[key] = search_or_create(models, uid, password, 'account.account', domain, data)

    journal_map = {
        'sale_journal': {'type': 'sale', 'code': 'INV', 'name': 'Customer Invoices', 'default_account_id': accounts['income_account']},
        'purchase_journal': {'type': 'purchase', 'code': 'PUR', 'name': 'Supplier Invoices'},
        'bank_journal': {'type': 'bank', 'code': 'BNK', 'name': 'Bank'},
        'cash_journal': {'type': 'cash', 'code': 'CAS', 'name': 'Cash'},
    }
    journals = {}
    for key, data in journal_map.items():
        domain = [('code', '=', data['code'])]
        journals[key] = search_or_create(models, uid, password, 'account.journal', domain, data)

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


def _generate_invoices(models, uid, password, client_ids, accounting_defaults):
    income_account = accounting_defaults['income_account_id']

    product_ids = models.execute_kw(DB, uid, password, 'product.product', 'search', [[('name', '=', 'Consulting Service'), ('type', '=', 'service')]], {'limit': 1})
    if product_ids:
        pid = product_ids[0]
        models.execute_kw(DB, uid, password, 'product.product', 'write', [[pid], {
            'invoice_policy': 'order',
            'property_account_income_id': income_account
        }])
    else:
        pid = models.execute_kw(DB, uid, password, 'product.product', 'create', [{
            'name': 'Consulting Service',
            'type': 'service',
            'list_price': 500,
            'property_account_income_id': income_account,
            'invoice_policy': 'order',
        }])

    print("Generating transaction history...")
    invoice_pairs = [(cid, j) for cid in client_ids for j in range(random.randint(5, 10))]
    for cid, _ in invoice_pairs:

        emission_dt = datetime.now() - timedelta(days=random.randint(10, 150))
        due_dt = emission_dt + timedelta(days=random.randint(20, 30))
        emission_str = emission_dt.strftime('%Y-%m-%d')
        due_str = due_dt.strftime('%Y-%m-%d')

        so_id = models.execute_kw(DB, uid, password, 'sale.order', 'create', [{
            'partner_id': cid,
            'date_order': emission_str + " 09:00:00",
        }])

        models.execute_kw(DB, uid, password, 'sale.order.line', 'create', [{
            'order_id': so_id,
            'product_id': pid,
            'product_uom_qty': random.randint(1, 22),
            'price_unit': random.choice([400, 550, 700, 850, 1100]),
        }])

        models.execute_kw(DB, uid, password, 'sale.order', 'action_confirm', [so_id])

        wiz_id = models.execute_kw(DB, uid, password, 'sale.advance.payment.inv', 'create', [{
            'sale_order_ids': [[6, 0, [so_id]]],
            'advance_payment_method': 'delivered',
        }])

        try:
            so_data = models.execute_kw(DB, uid, password, 'sale.order', 'read', [so_id], {'fields': ['name', 'order_line']})[0]
            so_ref = so_data['name']
            so_lines = so_data['order_line']

            inv_id = models.execute_kw(DB, uid, password, 'account.move', 'create', [{
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
                models.execute_kw(DB, uid, password, 'account.move', 'action_post', [[inv_id]])
        except Exception as e:
            print(f"Error creating invoice for {so_ref}: {e}")


def run_industry_loader(path, clean=False, invoices_only=False):
    global DB
    industry_name = os.path.basename(path)
    DB = os.environ.get('ODOO_DB', f'{industry_name}_demo').strip()

    if clean:
        drop_database(DB)

    ensure_database(industry_name)

    uid = get_uid()
    if not uid:
        print("Error: Authentication failed.")
        return

    models = xmlrpc.client.ServerProxy(f'{URL}/xmlrpc/2/object', allow_none=True)

    if invoices_only:
        accounting_defaults = setup_accounting(models, uid, PASS)
        client_ids = models.execute_kw(DB, uid, PASS, 'res.partner', 'search', [[('is_company', '=', True), ('id', '>', 10)]])
        _generate_invoices(models, uid, PASS, client_ids, accounting_defaults)
        print(f"Industry package '{industry_name}' successfully deployed.")
        return

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
        _generate_invoices(models, uid, PASS, client_ids, accounting_defaults)

    print(f"Industry package '{industry_name}' successfully deployed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--industry', type=str, required=True)
    parser.add_argument('--clean', action='store_true', help='Drop and recreate the industry database')
    parser.add_argument('--invoices', action='store_true', help='Generate invoices for existing partners (skip company config, partners, resources)')
    args = parser.parse_args()

    target = f'/tmp/seeds/{args.industry}'
    if not os.path.exists(target):
        target = f'seeds/{args.industry}'

    if os.path.exists(target):
        run_industry_loader(target, clean=args.clean, invoices_only=args.invoices)
    else:
        print(f"Error: Data package '{args.industry}' not found.")
