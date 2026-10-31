# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.sale_order
#
# Extensions to native sale.order for Brightloop Quotation & Sales Management
#
# PHASE 5 SCOPE
# -------------
# - Reusable quotation foundation extending Odoo's native sale.order.
# - Customer, company, currency, validity, and quotation metadata integration.
# - Quotation validity enforcement, expiration checks, and authorized extension.
# - Quotation state transitions (Draft -> Sent -> Confirmed, Cancelled).
# - Protection against confirming expired or cancelled quotations.
# - Guarantee that confirming a quotation does NOT activate subscriptions in Phase 5.
# - Role-based permissions (Admin full CRUD, Staff operational access, Customer isolated).
# - Immutable audit logging for quotation lifecycle events.
# =============================================================================

import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    # =========================================================================
    # BRIGHTLOOP FIELDS
    # =========================================================================

    is_subscription_quotation = fields.Boolean(
        string='Contains Subscriptions',
        compute='_compute_is_subscription_quotation',
        store=True,
        index=True,
        help='Indicates whether this quotation includes subscription plan lines.',
    )

    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        help='True if quotation has passed its validity date while unconfirmed.',
    )

    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================

    @api.depends('order_line.subscription_plan_id')
    def _compute_is_subscription_quotation(self):
        for order in self:
            order.is_subscription_quotation = any(line.subscription_plan_id for line in order.order_line)

    @api.depends('validity_date', 'state')
    def _compute_is_expired(self):
        today = fields.Date.today()
        for order in self:
            order.is_expired = bool(
                order.validity_date
                and order.validity_date < today
                and order.state in ('draft', 'sent')
            )

    # =========================================================================
    # DATA INTEGRITY CONSTRAINTS
    # =========================================================================

    @api.constrains('partner_id')
    def _check_customer_required(self):
        for order in self:
            if not order.partner_id:
                raise ValidationError('Customer is required for a quotation.')

    @api.constrains('validity_date', 'date_order')
    def _check_validity_date(self):
        for order in self:
            if order.validity_date and order.date_order:
                order_date = order.date_order.date() if isinstance(order.date_order, datetime) else order.date_order
                if order.validity_date < order_date:
                    raise ValidationError('Quotation validity date cannot be earlier than quotation date.')

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL & AUDIT LOGGING OVERRIDES
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        caller_is_staff = caller.has_group('brightloop_core.group_brightloop_staff')
        caller_is_customer = (
            caller.has_group('brightloop_core.group_brightloop_customer')
            and not caller_is_staff
            and not caller_is_admin
        )

        if caller_is_customer:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized quotation creation attempt',
                details=f'Customer {caller.login} (ID={caller.id}) attempted to create an internal quotation.',
            )
            raise AccessError('Customers cannot create internal quotations.')

        records = super().create(vals_list)

        for rec in records:
            self.env['brightloop.security.audit'].log_event(
                event_type='quotation_created',
                summary=f'Quotation created: {rec.name}',
                details=f'Quotation "{rec.name}" created for customer "{rec.partner_id.name}" (Total: {rec.amount_total} {rec.currency_id.name}).',
            )

        return records

    def write(self, vals):
        caller = self.env.user
        caller_is_admin = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or self.env.is_superuser()
        )
        caller_is_staff = caller.has_group('brightloop_core.group_brightloop_staff')
        caller_is_customer = (
            caller.has_group('brightloop_core.group_brightloop_customer')
            and not caller_is_staff
            and not caller_is_admin
        )

        if caller_is_customer and any(f in vals for f in ['order_line', 'partner_id', 'pricelist_id', 'company_id', 'state', 'validity_date']):
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized quotation modification attempt',
                details=f'Customer {caller.login} attempted to modify protected fields on quotations {self.ids}.',
            )
            raise AccessError('Customers cannot modify internal quotations.')

        # Confirmed quotations cannot be modified arbitrarily by non-admins
        for order in self:
            if order.state == 'sale' and not caller_is_admin and any(f in vals for f in ['order_line', 'partner_id', 'currency_id']):
                raise UserError(f'Confirmed quotation "{order.name}" cannot be modified. Create a new quotation or amendment.')

        result = super().write(vals)

        if vals.get('state') == 'sent':
            for order in self:
                self.env['brightloop.security.audit'].log_event(
                    event_type='quotation_sent',
                    summary=f'Quotation sent: {order.name}',
                    details=f'Quotation "{order.name}" state updated to sent.',
                )

        if any(f in vals for f in ['order_line', 'partner_id', 'validity_date', 'note']):
            for order in self:
                self.env['brightloop.security.audit'].log_event(
                    event_type='quotation_updated',
                    summary=f'Quotation updated: {order.name}',
                    details=f'Updated quotation "{order.name}" fields: {list(vals.keys())}.',
                )

        return result

    # =========================================================================
    # WORKFLOW ACTIONS & VALIDITY EXTENSION
    # =========================================================================

    def extend_validity(self, new_validity_date):
        """
        Extend quotation validity date by an authorized Staff or Administrator.
        """
        caller = self.env.user
        caller_is_authorized = (
            self.env.is_admin()
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or caller.has_group('brightloop_core.group_brightloop_staff')
            or self.env.is_superuser()
        )
        if not caller_is_authorized:
            raise AccessError('Only authorized staff or administrators can extend quotation validity.')

        if isinstance(new_validity_date, str):
            new_validity_date = fields.Date.from_string(new_validity_date)
        elif isinstance(new_validity_date, datetime):
            new_validity_date = new_validity_date.date()

        for order in self:
            order_date = order.date_order.date() if isinstance(order.date_order, datetime) else order.date_order
            if new_validity_date < order_date:
                raise ValidationError('Quotation validity date cannot be earlier than quotation date.')

            old_date = order.validity_date
            order.write({'validity_date': new_validity_date})

            self.env['brightloop.security.audit'].log_event(
                event_type='quotation_validity_extended',
                summary=f'Quotation validity extended: {order.name}',
                details=f'Quotation "{order.name}" validity date extended from {old_date} to {new_validity_date}.',
            )

        return True

    def action_confirm(self):
        """
        Confirm quotation with strict checks:
          - Prevents confirmation of expired quotations.
          - Prevents confirmation of cancelled quotations.
          - Validates availability of products and subscription plans.
          - Logs quotation_confirmed audit event.
          - DOES NOT activate subscriptions (Phase 6 ownership).
        """
        for order in self:
            if order.is_expired:
                raise UserError(
                    f'Cannot confirm quotation "{order.name}" because it expired on {order.validity_date}. '
                    'Please extend the quotation validity before confirming.'
                )
            if order.state == 'cancel':
                raise UserError(
                    f'Cannot confirm cancelled quotation "{order.name}". '
                    'Please create a new quotation.'
                )

            # Validate products and subscription plans
            for line in order.order_line:
                if line.product_id and not line.product_id.active:
                    raise UserError(f'Cannot confirm quotation containing archived product "{line.product_id.name}".')
                if line.subscription_plan_id:
                    target_date = order.date_order.date() if isinstance(order.date_order, datetime) else order.date_order
                    line.subscription_plan_id.check_availability(
                        target_date=target_date,
                        quantity=line.product_uom_qty,
                    )

        result = super().action_confirm()

        for order in self:
            self.env['brightloop.security.audit'].log_event(
                event_type='quotation_confirmed',
                summary=f'Quotation confirmed: {order.name}',
                details=f'Quotation "{order.name}" confirmed as Sales Order (Total: {order.amount_total} {order.currency_id.name}).',
            )

        return result

    def _action_cancel(self):
        result = super()._action_cancel()
        for order in self:
            self.env['brightloop.security.audit'].log_event(
                event_type='quotation_cancelled',
                summary=f'Quotation cancelled: {order.name}',
                details=f'Quotation "{order.name}" was cancelled.',
            )
        return result

    def action_quotation_send(self):
        result = super().action_quotation_send()
        for order in self:
            self.env['brightloop.security.audit'].log_event(
                event_type='quotation_sent',
                summary=f'Quotation sent: {order.name}',
                details=f'Quotation "{order.name}" sent to customer "{order.partner_id.name}".',
            )
        return result

    # =========================================================================
    # QUOTATION TEMPLATE APPLICATION
    # =========================================================================

    def apply_brightloop_template(self, template):
        """
        Apply a quotation template cleanly without line duplication.
        Validates template active status, product/plan active status,
        and computes validity_date.
        """
        self.ensure_one()

        if not template or not template.active:
            raise UserError('Cannot apply an archived or invalid quotation template.')

        # Check template lines
        for t_line in template.sale_order_template_line_ids:
            if t_line.product_id and not t_line.product_id.active:
                raise UserError(f'Template contains archived product "{t_line.product_id.name}".')
            if hasattr(t_line, 'subscription_plan_id') and t_line.subscription_plan_id and not t_line.subscription_plan_id.active:
                raise UserError(f'Template contains archived subscription plan "{t_line.subscription_plan_id.name}".')

        new_lines_data = []
        for t_line in template.sale_order_template_line_ids:
            if not t_line.product_id:
                continue
            line_vals = {
                'product_id': t_line.product_id.id,
                'product_uom_qty': t_line.product_uom_qty or 1.0,
                'name': t_line.name or t_line.product_id.display_name,
            }
            if hasattr(t_line, 'subscription_plan_id') and t_line.subscription_plan_id:
                line_vals['subscription_plan_id'] = t_line.subscription_plan_id.id
            new_lines_data.append((0, 0, line_vals))

        # Clear existing lines and set new lines (prevents unintended duplicate lines)
        self.order_line = [(5, 0, 0)] + new_lines_data

        if template.number_of_days > 0:
            order_date = self.date_order.date() if isinstance(self.date_order, datetime) else self.date_order
            self.validity_date = order_date + relativedelta(days=template.number_of_days)

        if template.note:
            self.note = template.note

        self.sale_order_template_id = template.id

        self.env['brightloop.security.audit'].log_event(
            event_type='quotation_template_applied',
            summary=f'Template applied to quotation: {self.name}',
            details=f'Applied template "{template.name}" with {len(new_lines_data)} line(s) to quotation "{self.name}".',
        )

        return True

