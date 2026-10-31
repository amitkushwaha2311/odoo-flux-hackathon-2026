# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.product_template
#
# Extensions to product.template for Brightloop Product Management Engine
#
# PHASE 3 SCOPE
# -------------
# - Data integrity constraints (non-negative sales/cost price, required name).
# - Role-based authorization: only Administrators can create/modify products.
# - Lifecycle rules: safe archival/reactivation and deletion protection for referenced products.
# - Audit logging for product lifecycle, attribute, and price changes.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # =========================================================================
    # DATA INTEGRITY CONSTRAINTS
    # =========================================================================

    @api.constrains('name')
    def _check_product_name(self):
        """Ensure product name is non-empty after stripping whitespace."""
        for template in self:
            if not template.name or not template.name.strip():
                raise ValidationError('Product name is required and cannot be empty.')

    @api.constrains('list_price')
    def _check_sales_price(self):
        """Ensure sales price is non-negative."""
        for template in self:
            if template.list_price is not None and template.list_price < 0.0:
                raise ValidationError('Product sales price cannot be negative.')

    @api.constrains('standard_price')
    def _check_cost_price(self):
        """Ensure cost price is non-negative."""
        for template in self:
            if template.standard_price is not None and template.standard_price < 0.0:
                raise ValidationError('Product cost price cannot be negative.')

    @api.constrains('currency_id')
    def _check_currency(self):
        """Ensure currency is valid and active."""
        for template in self:
            if template.currency_id and not template.currency_id.active:
                raise ValidationError('Product currency must be an active currency.')

    # =========================================================================
    # ROLE-BASED ACCESS CONTROL ENFORCEMENT
    # =========================================================================

    @api.model_create_multi
    def create(self, vals_list):
        """
        Enforce that only Brightloop Administrators can create products.
        Log product creation to the security audit trail.
        """
        caller = self.env.user
        caller_is_admin = self.env.is_admin() or caller.has_group('brightloop_core.group_brightloop_admin') or self.env.is_superuser()

        if not caller_is_admin:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized product creation attempt',
                details=f'User {caller.login} (ID={caller.id}) attempted to create a product without Admin privileges.',
            )
            raise AccessError('Only Brightloop Administrators can create products in the catalog.')

        records = super().create(vals_list)

        # Audit log creation
        for rec in records:
            self.env['brightloop.security.audit'].log_event(
                event_type='product_created',
                summary=f'Product created: {rec.name}',
                details=f'Created product "{rec.name}" (Type={rec.type}, Sales Price={rec.list_price}, Cost={rec.standard_price}).',
            )

        return records

    def write(self, vals):
        """
        Enforce that only Brightloop Administrators can modify product pricing or catalog data.
        Log updates, price modifications, and archival/reactivations.
        """
        caller = self.env.user
        caller_is_admin = self.env.is_admin() or caller.has_group('brightloop_core.group_brightloop_admin') or self.env.is_superuser()

        # Restricted fields that require Admin role
        restricted_fields = {'list_price', 'standard_price', 'name', 'type', 'attribute_line_ids', 'active'}
        if not caller_is_admin and any(f in vals for f in restricted_fields):
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized product modification attempt',
                details=f'User {caller.login} attempted to modify restricted fields {set(vals.keys()) & restricted_fields} on products {self.ids}.',
            )
            raise AccessError('Only Brightloop Administrators can modify product information or pricing.')

        # Track state changes before write
        old_prices = {rec.id: rec.list_price for rec in self} if 'list_price' in vals else {}
        old_active = {rec.id: rec.active for rec in self} if 'active' in vals else {}

        result = super().write(vals)

        # Audit events
        if 'active' in vals:
            for rec in self:
                if old_active.get(rec.id) is True and rec.active is False:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='product_archived',
                        summary=f'Product archived: {rec.name}',
                        details=f'Product ID={rec.id} ("{rec.name}") was archived.',
                    )
                elif old_active.get(rec.id) is False and rec.active is True:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='product_reactivated',
                        summary=f'Product reactivated: {rec.name}',
                        details=f'Product ID={rec.id} ("{rec.name}") was reactivated.',
                    )

        if 'list_price' in vals:
            for rec in self:
                old_p = old_prices.get(rec.id)
                if old_p != rec.list_price:
                    self.env['brightloop.security.audit'].log_event(
                        event_type='product_updated',
                        summary=f'Product price updated: {rec.name}',
                        details=f'Product "{rec.name}" price changed from {old_p} to {rec.list_price}.',
                    )
        elif any(f in vals for f in ['name', 'description_sale', 'type', 'standard_price']):
            for rec in self:
                self.env['brightloop.security.audit'].log_event(
                    event_type='product_updated',
                    summary=f'Product details updated: {rec.name}',
                    details=f'Updated fields on product "{rec.name}": {list(vals.keys())}.',
                )

        return result

    # =========================================================================
    # LIFECYCLE & DELETION PROTECTION
    # =========================================================================

    def unlink(self):
        """
        Prevent permanent deletion if the product is referenced by customer records
        or historical transactions. Enforce archival instead to preserve financial history.
        """
        CustomerRecord = self.env.get('brightloop.customer.record')
        for template in self:
            if CustomerRecord:
                # Check if referenced in customer records or payload
                ref_count = CustomerRecord.sudo().search_count([
                    ('data_payload', 'ilike', template.name),
                ])
                if ref_count > 0:
                    raise UserError(
                        f'Cannot delete product "{template.name}" because it is referenced in '
                        f'existing customer records ({ref_count} references found). '
                        'Please archive the product instead to preserve historical records.'
                    )
        return super().unlink()

    def check_available_for_sale(self):
        """
        Verify that the product is active and available for use in commercial operations.
        Raises UserError if the product is archived.
        """
        for template in self:
            if not template.active:
                raise UserError(f'Product "{template.name}" is archived and cannot be used in sales operations.')
        return True

