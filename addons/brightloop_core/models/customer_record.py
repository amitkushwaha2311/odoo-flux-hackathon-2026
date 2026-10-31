# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.customer_record
#
# Foundational Customer-Linked Document Model for Record Isolation Testing
#
# PHASE 2 SCOPE
# -------------
# Provides a concrete partner-linked model to establish and verify row-level
# security rules, multi-tenant isolation, and customer data privacy without
# prematurely implementing Phase 3/4 subscription/billing business logic.
# =============================================================================

from odoo import fields, models


class BrightloopCustomerRecord(models.Model):
    """
    Partner-linked record model used to enforce and verify customer data isolation.
    """
    _name = 'brightloop.customer.record'
    _description = 'Brightloop Customer Data Record'
    _inherit = ['brightloop.base']
    _order = 'create_date desc'

    name = fields.Char(
        string='Title',
        required=True,
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer Partner',
        required=True,
        index=True,
        help='Partner who owns this record. Security rules restrict customers to their own partner.',
    )

    record_type = fields.Selection(
        selection=[
            ('subscription_summary', 'Subscription Summary'),
            ('invoice_summary', 'Invoice Summary'),
            ('profile_data', 'Profile Data'),
        ],
        string='Record Type',
        default='profile_data',
        required=True,
    )

    reference = fields.Char(
        string='Reference Code',
    )

    data_payload = fields.Text(
        string='Secure Payload',
        help='Customer-specific private data payload.',
    )

