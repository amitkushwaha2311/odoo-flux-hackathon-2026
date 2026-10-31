# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.account_payment
#
# Extensions to native account.payment for Brightloop Subscription Payments
#
# PHASE 9 SCOPE
# -------------
# - Links native customer payments (account.payment) to source subscriptions
#   and billing periods via reconciled invoices.
# - Adds idempotency key for database-level duplicate payment protection.
# - Provides computed subscription traceability.
# =============================================================================

import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    subscription_id = fields.Many2one(
        comodel_name='brightloop.subscription',
        string='Subscription Contract',
        compute='_compute_brightloop_traceability',
        store=True,
        index=True,
        copy=False,
        help='Brightloop subscription contract linked via paid invoices.',
    )

    billing_period_id = fields.Many2one(
        comodel_name='brightloop.billing.period',
        string='Billing Period',
        compute='_compute_brightloop_traceability',
        store=True,
        index=True,
        copy=False,
        help='Brightloop billing period linked via paid invoices.',
    )

    idempotency_key = fields.Char(
        string='Idempotency Key',
        index=True,
        copy=False,
        help='Unique key to prevent duplicate payment registration.',
    )

    _idempotency_key_uniq = models.Constraint(
        'UNIQUE (idempotency_key)',
        'A payment with this idempotency key already exists. Duplicate payment registration is prohibited.',
    )

    @api.depends('reconciled_invoice_ids.subscription_id', 'reconciled_invoice_ids.billing_period_id',
                 'invoice_ids.subscription_id', 'invoice_ids.billing_period_id')
    def _compute_brightloop_traceability(self):
        for pay in self:
            invoices = pay.reconciled_invoice_ids or pay.invoice_ids
            subs = invoices.mapped('subscription_id')
            periods = invoices.mapped('billing_period_id')
            pay.subscription_id = subs[0] if subs else False
            pay.billing_period_id = periods[0] if periods else False

