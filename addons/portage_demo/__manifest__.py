# -*- coding: utf-8 -*-
{
    'name': "Portage & Developer Placement Demo",
    'summary': "Demo data for developer placement and portage services",
    'description': """
        This module provides demo data for:
        - Developer profiles (Contractors)
        - Client companies
        - Sample projects and invoices
    """,
    'author': "Antigravity",
    'category': 'Sales',
    'version': '1.0',
    'depends': ['base', 'account', 'hr', 'sale'],
    'data': [
        'data/demo_partners.xml',
        'data/demo_products.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
}
