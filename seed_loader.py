import xmlrpc.client
import json
import base64
import requests
import os
import random
import argparse
from datetime import datetime, timedelta

# Configuration
URL = os.getenv("ODOO_URL")
DB = os.getenv("ODOO_DB")
USER = os.getenv("ODOO_USER")
PASS = os.getenv("ODOO_PASS")


def get_uid():
    proxy = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/common", allow_none=True)
    return proxy.authenticate(DB, USER, PASS, {})


def fetch_asset_as_base64(url):
    """Downloads an image and converts it to base64 for Odoo ingestion."""
    try:
        req = requests.get(url, timeout=10)
        if req.status_code == 200:
            return base64.b64encode(req.content).decode("utf-8")
    except Exception:
        pass
    return False


def run_industry_loader(path):
    uid = get_uid()
    models = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", allow_none=True)

    # 1. Company Configuration
    agency_path = os.path.join(path, "agency.json")
    if os.path.exists(agency_path):
        with open(agency_path, "r") as f:
            cfg = json.load(f)

        print(f"Configuring Company: {cfg['name']}")
        models.execute_kw(
            DB,
            uid,
            PASS,
            "res.company",
            "write",
            [
                [1],
                {
                    "name": cfg["name"],
                    "street": cfg["street"],
                    "city": cfg["city"],
                    "zip": cfg["zip"],
                    "phone": cfg["phone"],
                    "email": cfg["email"],
                    "website": cfg["website"],
                    "vat": cfg["vat"],
                    "company_registry": cfg["company_registry"],
                    "logo": fetch_asset_as_base64(cfg["logo_url"]),
                },
            ],
        )

    # 2. Master Data: Partners
    clients_path = os.path.join(path, "clients.json")
    client_ids = []
    if os.path.exists(clients_path):
        with open(clients_path, "r") as f:
            clients = json.load(f)

        print(f"[*] Importing {len(clients)} clients...")
        for c in clients:
            cid = models.execute_kw(
                DB,
                uid,
                PASS,
                "res.partner",
                "create",
                [
                    {
                        "name": c["name"],
                        "is_company": True,
                        "street": c["street"],
                        "city": c["city"],
                        "zip": c["zip"],
                        "email": c["email"],
                        "phone": c["phone"],
                        "vat": c["vat"],
                    }
                ],
            )
            client_ids.append(cid)

    # 3. Master Data: Resources
    devs_path = os.path.join(path, "developers.json")
    res_ids = []
    if os.path.exists(devs_path):
        with open(devs_path, "r") as f:
            devs = json.load(f)

        print(f"[*] Importing {len(devs)} resources...")
        for d in devs:
            rid = models.execute_kw(
                DB,
                uid,
                PASS,
                "res.partner",
                "create",
                [
                    {
                        "name": d["name"],
                        "function": d.get("job_title", ""),
                        "email": d["email"],
                        "phone": d["phone"],
                        "image_1920": fetch_asset_as_base64(d.get("avatar_url", "")),
                    }
                ],
            )
            res_ids.append(rid)

    # 4. Transactional Data: Sales & Invoicing
    if client_ids:
        print("Generating transaction history...")
        product_ids = models.execute_kw(
            DB,
            uid,
            PASS,
            "product.product",
            "search",
            [[["type", "=", "service"]]],
            {"limit": 1},
        )
        if not product_ids:
            return
        pid = product_ids[0]
        models.execute_kw(
            DB,
            uid,
            PASS,
            "product.product",
            "write",
            [[pid], {"invoice_policy": "order"}],
        )

        for i in range(20):
            cid = client_ids[i % len(client_ids)]
            # Randomized dates: Emission and Due
            emission_dt = datetime.now() - timedelta(days=random.randint(10, 150))
            due_dt = emission_dt + timedelta(days=random.randint(20, 30))

            emission_str = emission_dt.strftime("%Y-%m-%d")
            due_str = due_dt.strftime("%Y-%m-%d")

            # Sale Order
            so_id = models.execute_kw(
                DB,
                uid,
                PASS,
                "sale.order",
                "create",
                [
                    {
                        "partner_id": cid,
                        "date_order": emission_str + " 09:00:00",
                    }
                ],
            )

            models.execute_kw(
                DB,
                uid,
                PASS,
                "sale.order.line",
                "create",
                [
                    {
                        "order_id": so_id,
                        "product_id": pid,
                        "product_uom_qty": random.randint(1, 22),
                        "price_unit": random.choice([400, 550, 700, 850, 1100]),
                    }
                ],
            )

            models.execute_kw(DB, uid, PASS, "sale.order", "action_confirm", [so_id])

            # Invoicing Wizard
            wiz_id = models.execute_kw(
                DB,
                uid,
                PASS,
                "sale.advance.payment.inv",
                "create",
                [
                    {
                        "sale_order_ids": [[6, 0, [so_id]]],
                        "advance_payment_method": "delivered",
                    }
                ],
            )

            try:
                models.execute_kw(
                    DB,
                    uid,
                    PASS,
                    "sale.advance.payment.inv",
                    "create_invoices",
                    [wiz_id],
                )
                so_ref = models.execute_kw(
                    DB, uid, PASS, "sale.order", "read", [so_id], {"fields": ["name"]}
                )[0]["name"]
                inv_ids = models.execute_kw(
                    DB,
                    uid,
                    PASS,
                    "account.move",
                    "search",
                    [[["invoice_origin", "=", so_ref]]],
                )
                if inv_ids:
                    models.execute_kw(
                        DB,
                        uid,
                        PASS,
                        "account.move",
                        "write",
                        [
                            inv_ids,
                            {"invoice_date": emission_str, "invoice_date_due": due_str},
                        ],
                    )
                    models.execute_kw(
                        DB, uid, PASS, "account.move", "action_post", [inv_ids]
                    )
            except Exception as e:
                if "cannot marshal None" not in str(e):
                    print(f"[!] Warning: Failed to post invoice for SO {so_ref}: {e}")

    print(f"Industry package '{os.path.basename(path)}' successfully deployed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry", type=str, required=True)
    args = parser.parse_args()

    # Priority to container path
    target = f"/tmp/seeds/{args.industry}"
    if not os.path.exists(target):
        target = f"seeds/{args.industry}"

    if os.path.exists(target):
        run_industry_loader(target)
    else:
        print(f"[-] Error: Data package '{args.industry}' not found.")
