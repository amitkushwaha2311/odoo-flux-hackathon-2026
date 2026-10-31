# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core — Odoo 20.0 Manifest
# =============================================================================
{
    'name': 'Brightloop Core',
    'version': '20.0.1.0.0',
    'summary': 'Brightloop Subscription Intelligence — Core Foundation',
    'description': """
        Brightloop Core
        ===============

        Foundation module for the Brightloop Subscription Intelligence platform.

        This module establishes the architectural base that all other Brightloop
        modules depend on. It provides:

        - Core configuration conventions
        - Company-aware architecture base
        - Currency-aware financial conventions
        - Timezone-aware date handling utilities
        - Logging conventions
        - Consistent error handling patterns
        - Safe database transaction practices

        Phase 1: Infrastructure foundation only.
        Subscription business logic is implemented in subsequent phases.
    """,

    # -------------------------------------------------------------------------
    # Metadata
    # -------------------------------------------------------------------------
    'author': 'Brightloop',
    'website': 'https://brightloop.io',
    'category': 'Accounting/Accounting',
    'license': 'LGPL-3',

    # -------------------------------------------------------------------------
    # Dependencies
    # -------------------------------------------------------------------------
    # Minimal: only what is actually used.
    # Phase 1: base, mail
    # Phase 3: product (Odoo official product and variant engine)
    'depends': [
        'base',          # Core Odoo (res.company, res.partner, res.currency, etc.)
        'mail',          # Messaging/chatter & notification templates
        'product',       # Official Odoo product & variant management engine
        'sale_management',  # Official Odoo sales & quotation template engine
        'account',       # Official Odoo accounting & tax engine (account.tax, fiscal.position)
    ],

    # -------------------------------------------------------------------------
    # Data files loaded on installation (order matters)
    # -------------------------------------------------------------------------
    # Security groups defined first, then access control rules, then templates.
    'data': [
        'security/security_groups.xml',
        'security/ir.access.csv',
        'data/mail_template_data.xml',
        'data/subscription_sequence_data.xml',
        'data/subscription_cron.xml',
    ],

    # -------------------------------------------------------------------------
    # Demo data (only loaded when Odoo demo mode is active)
    # -------------------------------------------------------------------------
    'demo': [],

    # -------------------------------------------------------------------------
    # Module behaviour
    # -------------------------------------------------------------------------
    # installable: the module can be installed from the Apps menu
    'installable': True,

    # auto_install: do not auto-install; always require explicit installation
    'auto_install': False,

    # application: True means this appears as a top-level App in the menu
    # False for Phase 1 — no menus yet
    'application': False,
}

