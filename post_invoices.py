# Internal Odoo Shell script to post all draft invoices
moves = env['account.move'].search([('state', '=', 'draft'), ('move_type', '=', 'out_invoice')])
for move in moves:
    try:
        move.action_post()
        print(f"Posted invoice {move.name}")
    except Exception as e:
        print(f"Failed to post {move.id}: {e}")
