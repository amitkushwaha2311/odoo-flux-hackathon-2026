# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.subscription_history
#
# Immutable lifecycle history tracking for Brightloop Subscriptions
#
# PHASE 6 SCOPE
# -------------
# - Records all lifecycle events: created, confirmed, activated, paused,
#   resumed, closed, auto_closed, renewed, date_modified.
# - Stores actor, timestamps, previous state, new state, and reason.
# - Strictly immutable: prevents editing or deletion by ordinary users.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BrightloopSubscriptionHistory(models.Model):
    _name = 'brightloop.subscription.history'
    _description = 'Brightloop Subscription Lifecycle History'
    _order = 'timestamp desc, id desc'
    _rec_name = 'event_type'

    subscription_id = fields.Many2one(
        comodel_name='brightloop.subscription',
        string='Subscription',
        required=True,
        ondelete='cascade',
        index=True,
    )

    event_type = fields.Selection(
        selection=[
            ('created', 'Subscription Created'),
            ('confirmed', 'Subscription Confirmed'),
            ('activated', 'Subscription Activated'),
            ('paused', 'Subscription Paused'),
            ('resumed', 'Subscription Resumed'),
            ('closed', 'Subscription Closed'),
            ('auto_closed', 'Subscription Auto Closed'),
            ('renewed', 'Subscription Renewed'),
            ('date_modified', 'Subscription Date Modified'),
            ('invoice_generated', 'Recurring Invoice Generated'),
        ],
        string='Lifecycle Event',
        required=True,
        index=True,
    )

    previous_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('active', 'Active'),
            ('paused', 'Paused'),
            ('closed', 'Closed'),
        ],
        string='Previous State',
    )

    new_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('active', 'Active'),
            ('paused', 'Paused'),
            ('closed', 'Closed'),
        ],
        string='New State',
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Actor (User)',
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )

    timestamp = fields.Datetime(
        string='Event Timestamp',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )

    reason = fields.Text(
        string='Reason / Description',
    )

    metadata = fields.Text(
        string='Metadata Payload',
        help='Serialized contextual details or parameter states.',
    )

    # =========================================================================
    # IMMUTABILITY ENFORCEMENT
    # =========================================================================

    def write(self, vals):
        """Lifecycle history records are strictly append-only and cannot be altered."""
        raise UserError('Subscription lifecycle history is immutable and cannot be modified.')

    def unlink(self):
        """Lifecycle history records cannot be deleted directly."""
        if not self.env.context.get('bypass_history_guard'):
            raise UserError('Subscription lifecycle history is immutable and cannot be deleted.')
        return super().unlink()

