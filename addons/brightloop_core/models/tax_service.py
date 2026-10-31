# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.tax_service
#
# Brightloop Tax Calculation Service
#
# PHASE 7 SCOPE
# -------------
# - Wraps Odoo's native account.tax computation engine.
# - Supports tax-exclusive and tax-inclusive pricing.
# - Supports multiple taxes (CGST + SGST, IGST, custom rates).
# - Respects fiscal positions, tax sequences, and company configuration.
# - Respects currency rounding.
# - Returns a structured tax breakdown for audit and invoice generation.
# - GST configuration is managed via native Odoo account.tax records.
#
# ARCHITECTURE DECISION
# ---------------------
# We deliberately delegate all tax math to Odoo's native
# account.tax._compute_taxes() / compute_all() API rather than
# reimplementing it. This ensures:
# - Correct repartition line handling.
# - Proper include_base_amount chaining.
# - Tax group aggregation.
# - Currency rounding is done by the Odoo tax engine.
#
# GST SUPPORT
# -----------
# Indian GST (CGST, SGST, IGST) is configured as native account.tax records.
# Fiscal positions map intra-state transactions to CGST+SGST tax groups
# and inter-state transactions to IGST. Brightloop does NOT hardcode rates.
# Brightloop merely applies whatever taxes are assigned to products or
# quotation/subscription lines.
#
# STATUTORY DISCLAIMER
# --------------------
# Brightloop calculates taxes as configured by the Odoo administrator.
# It does not guarantee legal tax compliance. Statutory accuracy depends on
# correct tax configuration (rates, repartition accounts, fiscal positions,
# tax periods) by qualified accounting personnel.
# =============================================================================

import logging
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopTaxService(models.AbstractModel):
    """
    Brightloop Tax Calculation Service.

    Wraps Odoo's native account.tax.compute_all() to provide deterministic
    tax calculations with structured breakdowns.

    Usage:
        result = self.env['brightloop.tax.service'].compute_taxes(
            taxes=line.tax_id,
            price_unit=1800.0,
            quantity=2,
            currency=self.env.company.currency_id,
            product=line.product_id,
            partner=order.partner_id,
            fiscal_position=order.fiscal_position_id,
            price_include=False,
        )
    """
    _name = 'brightloop.tax.service'
    _description = 'Brightloop Tax Calculation Service'

    # =========================================================================
    # CORE TAX COMPUTATION
    # =========================================================================

    @api.model
    def compute_taxes(
        self,
        taxes,
        price_unit,
        quantity=1.0,
        currency=None,
        product=None,
        partner=None,
        fiscal_position=None,
        price_include=False,
    ):
        """
        Compute taxes using Odoo's native tax engine and return a structured breakdown.

        :param taxes: account.tax recordset — taxes to apply
        :param price_unit: float — unit price (after discounts, before tax)
        :param quantity: float — quantity
        :param currency: res.currency — for rounding (defaults to company currency)
        :param product: product.product — for tax scope filtering
        :param partner: res.partner — for fiscal position evaluation
        :param fiscal_position: account.fiscal.position or None — if provided, maps taxes
        :param price_include: bool — True if price_unit already includes tax (tax-inclusive)
        :return: dict with full tax breakdown

        Output structure:
        {
            'untaxed_amount': float,       # price_unit * quantity (tax-exclusive base)
            'taxable_base': float,         # effective taxable base after inclusions
            'tax_lines': [                 # one per tax applied
                {
                    'tax_id': int,
                    'tax_name': str,
                    'tax_amount_type': str,
                    'amount': float,       # tax amount for this line
                    'base': float,         # base amount this tax was computed on
                    'price_include': bool,
                }
            ],
            'total_tax': float,            # sum of all tax amounts
            'total_included': float,       # untaxed_amount + total_tax (tax-exclusive view)
            'total_excluded': float,       # effective untaxed subtotal
            'price_include': bool,         # whether input prices included tax
            'currency': str,              # currency name
        }
        """
        currency = currency or self.env.company.currency_id

        # Apply fiscal position mapping if provided
        mapped_taxes = taxes
        if fiscal_position and taxes:
            try:
                mapped_taxes = fiscal_position.map_tax(taxes)
            except Exception:
                _logger.warning('Fiscal position tax mapping failed, using original taxes.', exc_info=True)
                mapped_taxes = taxes

        if not mapped_taxes:
            # No taxes — return zeroed breakdown
            untaxed = currency.round(price_unit * quantity)
            return {
                'untaxed_amount': untaxed,
                'taxable_base': untaxed,
                'tax_lines': [],
                'total_tax': 0.0,
                'total_included': untaxed,
                'total_excluded': untaxed,
                'price_include': price_include,
                'currency': currency.name,
            }

        # Call Odoo's native compute_all
        # compute_all returns:
        # {
        #   'base_tags': ...,
        #   'taxes': [{'id': ..., 'name': ..., 'amount': ..., 'base': ..., ...}],
        #   'total_excluded': float,
        #   'total_included': float,
        # }
        try:
            result = mapped_taxes.compute_all(
                price_unit=price_unit,
                currency=currency,
                quantity=quantity,
                product=product,
                partner=partner,
                is_refund=False,
            )
        except Exception as e:
            _logger.error('Tax computation failed: %s', str(e))
            raise UserError(f'Tax calculation error: {str(e)}')

        # Build structured output
        tax_lines = []
        total_tax = 0.0
        for t in result.get('taxes', []):
            tax_lines.append({
                'tax_id': t.get('id'),
                'tax_name': t.get('name', ''),
                'tax_amount_type': t.get('amount_type', 'percent'),
                'amount': t.get('amount', 0.0),
                'base': t.get('base', 0.0),
                'price_include': t.get('price_include', False),
            })
            total_tax += t.get('amount', 0.0)

        total_tax = currency.round(total_tax)
        total_excluded = currency.round(result.get('total_excluded', price_unit * quantity))
        total_included = currency.round(result.get('total_included', total_excluded + total_tax))

        return {
            'untaxed_amount': total_excluded,
            'taxable_base': total_excluded,
            'tax_lines': tax_lines,
            'total_tax': total_tax,
            'total_included': total_included,
            'total_excluded': total_excluded,
            'price_include': price_include,
            'currency': currency.name,
        }

    # =========================================================================
    # SUBSCRIPTION LINE TAX COMPUTATION
    # =========================================================================

    @api.model
    def compute_taxes_for_subscription_line(self, subscription_line, fiscal_position=None):
        """
        Compute taxes for a brightloop.subscription.line using its linked
        product's default taxes.

        :param subscription_line: brightloop.subscription.line record
        :param fiscal_position: account.fiscal.position or None
        :return: tax breakdown dict (same structure as compute_taxes)
        """
        product = subscription_line.product_id
        currency = subscription_line.currency_id or self.env.company.currency_id
        price_after_discount = subscription_line.price_unit * (1 - (subscription_line.discount or 0.0) / 100.0)

        # Get product's customer taxes (sales taxes)
        taxes = product.taxes_id if product and hasattr(product, 'taxes_id') else self.env['account.tax']

        return self.compute_taxes(
            taxes=taxes,
            price_unit=price_after_discount,
            quantity=subscription_line.quantity,
            currency=currency,
            product=product,
            partner=subscription_line.subscription_id.customer_id if subscription_line.subscription_id else None,
            fiscal_position=fiscal_position,
            price_include=False,
        )

    # =========================================================================
    # QUOTATION LINE TAX COMPUTATION
    # =========================================================================

    @api.model
    def compute_taxes_for_quotation_line(self, order_line, fiscal_position=None):
        """
        Compute taxes for a sale.order.line.

        :param order_line: sale.order.line record
        :param fiscal_position: account.fiscal.position or None (falls back to order's)
        :return: tax breakdown dict
        """
        currency = order_line.currency_id or self.env.company.currency_id
        price_after_discount = order_line.price_unit * (1 - (order_line.discount or 0.0) / 100.0)
        taxes = order_line.tax_ids if 'tax_ids' in order_line._fields else getattr(order_line, 'tax_id', self.env['account.tax'])

        fp = fiscal_position or (order_line.order_id.fiscal_position_id
                                  if hasattr(order_line.order_id, 'fiscal_position_id') else None)

        return self.compute_taxes(
            taxes=taxes,
            price_unit=price_after_discount,
            quantity=order_line.product_uom_qty,
            currency=currency,
            product=order_line.product_id,
            partner=order_line.order_partner_id or order_line.order_id.partner_id,
            fiscal_position=fp,
            price_include=False,
        )

    # =========================================================================
    # GST CONVENIENCE HELPER
    # =========================================================================

    @api.model
    def get_gst_breakdown(self, taxes, price_unit, quantity=1.0, currency=None,
                           product=None, partner=None, fiscal_position=None):
        """
        Compute GST breakdown (CGST, SGST, IGST) from native account.tax records.

        This is a convenience wrapper for Indian GST scenarios. The actual GST
        tax split (CGST+SGST vs IGST) is determined by which taxes are assigned
        to the product and which fiscal position is applied by the administrator.

        Example GST scenario:
          - Intra-state: CGST 9% + SGST 9% = 18% GST
          - Inter-state: IGST 18% = 18% GST

        :return: tax breakdown dict with GST line items labeled by their tax name
        """
        result = self.compute_taxes(
            taxes=taxes,
            price_unit=price_unit,
            quantity=quantity,
            currency=currency,
            product=product,
            partner=partner,
            fiscal_position=fiscal_position,
            price_include=False,
        )

        # Label GST components by name for reporting clarity
        gst_components = {}
        for tl in result['tax_lines']:
            name = tl['tax_name']
            gst_components[name] = tl['amount']

        result['gst_components'] = gst_components
        return result

    # =========================================================================
    # AUDIT
    # =========================================================================

    @api.model
    def _log_tax_event(self, event_type, summary, details=''):
        """Log a tax-related audit event."""
        self.env['brightloop.security.audit'].log_event(
            event_type=event_type,
            summary=summary,
            details=details,
        )

