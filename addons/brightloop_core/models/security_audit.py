# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.security_audit
#
# Immutable Security Audit Logging Model
#
# PHASE 2 SCOPE
# -------------
# Records critical security and authorization events:
#   - Staff account creation
#   - Role / permission modifications
#   - Password reset requests and completions
#   - Customer registrations
#   - Unauthorized access attempts
#
# SECURITY RULES
# --------------
# - Append-only: records cannot be altered once written.
# - Never log plaintext passwords, reset tokens, or secret session credentials.
# - Restricted access: only Administrators can view security audit logs.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class BrightloopSecurityAudit(models.Model):
    """
    Security Audit Log for Brightloop Subscription Intelligence.

    Maintains an immutable audit trail of authentication and authorization
    events across the system.
    """
    _name = 'brightloop.security.audit'
    _description = 'Brightloop Security Audit Log'
    _inherit = ['brightloop.base']
    _order = 'timestamp desc, id desc'

    name = fields.Char(
        string='Summary',
        required=True,
        readonly=True,
        help='High-level summary of the security event.',
    )

    event_type = fields.Selection(
        selection=[
            ('customer_registration', 'Customer Registration'),
            ('staff_creation', 'Staff Account Creation'),
            ('role_assignment', 'Role Assignment'),
            ('permission_modification', 'Permission Modification'),
            ('password_reset_request', 'Password Reset Request'),
            ('password_reset_success', 'Password Reset Success'),
            ('unauthorized_access', 'Unauthorized Access Attempt'),
            ('login_failure', 'Login Failure'),
            ('product_created', 'Product Created'),
            ('product_updated', 'Product Updated'),
            ('product_archived', 'Product Archived'),
            ('product_reactivated', 'Product Reactivated'),
            ('variant_attributes_modified', 'Variant Attributes Modified'),
            ('variant_pricing_modified', 'Variant Pricing Modified'),
            ('plan_created', 'Subscription Plan Created'),
            ('plan_updated', 'Subscription Plan Updated'),
            ('plan_archived', 'Subscription Plan Archived'),
            ('plan_reactivated', 'Subscription Plan Reactivated'),
            ('plan_price_modified', 'Subscription Plan Price Modified'),
            ('plan_interval_modified', 'Subscription Plan Interval Modified'),
            ('plan_policy_modified', 'Subscription Plan Policy Modified'),
            ('quotation_created', 'Quotation Created'),
            ('quotation_updated', 'Quotation Updated'),
            ('quotation_sent', 'Quotation Sent'),
            ('quotation_confirmed', 'Quotation Confirmed'),
            ('quotation_cancelled', 'Quotation Cancelled'),
            ('quotation_expired', 'Quotation Expired'),
            ('quotation_validity_extended', 'Quotation Validity Extended'),
            ('quotation_template_applied', 'Quotation Template Applied'),
            ('quotation_line_added', 'Quotation Line Added'),
            ('quotation_line_updated', 'Quotation Line Updated'),
            ('quotation_line_removed', 'Quotation Line Removed'),
        ],
        string='Event Type',
        required=True,
        readonly=True,
        index=True,
    )

    user_id = fields.Many2one(
        comodel_name='res.users',
        string='Actor (User)',
        readonly=True,
        index=True,
        help='The user who performed or triggered the action.',
    )

    target_user_id = fields.Many2one(
        comodel_name='res.users',
        string='Target User',
        readonly=True,
        index=True,
        help='The user account that was created or modified, if applicable.',
    )

    ip_address = fields.Char(
        string='IP Address',
        readonly=True,
        help='Origin IP address of the request.',
    )

    details = fields.Text(
        string='Details',
        readonly=True,
        help='Safe descriptive metadata. Never contains passwords, tokens, or secrets.',
    )

    timestamp = fields.Datetime(
        string='Event Timestamp (UTC)',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
        index=True,
    )

    # =========================================================================
    # IMMUTABILITY ENFORCEMENT
    # =========================================================================

    def write(self, vals):
        """Audit records are strictly immutable once created."""
        raise UserError('Security audit records cannot be modified once written.')

    def unlink(self):
        """Audit records cannot be deleted through standard operations."""
        if not self.env.is_superuser():
            raise UserError('Security audit records cannot be deleted.')
        return super().unlink()

    # =========================================================================
    # LOGGING HELPER
    # =========================================================================

    @api.model
    def log_event(self, event_type, summary, details='', target_user_id=None, ip_address=None):
        """
        Record a security audit log event using elevated system privileges.

        :param event_type: Valid event_type selection key.
        :param summary: Human-readable short summary.
        :param details: Safe supplementary details (NO credentials/tokens).
        :param target_user_id: ID of the subject user, if applicable.
        :param ip_address: Origin IP address.
        :return: Created audit record.
        """
        vals = {
            'event_type': event_type,
            'name': summary,
            'details': details or '',
            'user_id': self.env.user.id if self.env.user and self.env.user.id else False,
            'target_user_id': target_user_id or False,
            'ip_address': ip_address or False,
            'timestamp': fields.Datetime.now(),
            'company_id': self.env.company.id,
        }
        record = self.sudo().create(vals)
        _logger.info('[AUDIT] %s | %s | actor=%s | target=%s', event_type, summary, vals['user_id'], target_user_id)
        return record

