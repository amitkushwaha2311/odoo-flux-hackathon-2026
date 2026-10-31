# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.controllers.app_api
#
# Authenticated SaaS Dashboard API Controller (Staff & Admin)
#
# PHASE 12 SCOPE
# --------------
# - /api/v1/app/subscriptions: All subscription contracts with state, customer, plan, next billing date.
# - /api/v1/app/subscriptions/<int:sub_id>/action: Lifecycle operations (pause, resume, renew, close).
# - /api/v1/app/catalog: Product templates and subscription plans with pricing & policies.
# - /api/v1/app/quotations: Sales quotations / orders with partner, date, state, amount.
# - /api/v1/app/invoices: Posted customer invoices with residual balances and payment states.
# - /api/v1/app/payments: Inbound customer payments with journals and allocation status.
# =============================================================================

import json
import logging
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopAppApiController(http.Controller):
    """
    Authenticated SaaS Application REST API Controller for Staff and Admin.
    """

    def _ensure_staff_or_admin(self):
        """Ensure the caller has Brightloop Staff or Admin privileges."""
        user = request.env.user
        if not user or user._is_public() or user.id == request.env.ref('base.public_user', raise_if_not_found=False).id:
            raise AccessError('Authentication required. Anonymous access is strictly prohibited.')

        if not (user._is_admin() or
                user.has_group('brightloop_core.group_brightloop_admin') or
                user.has_group('brightloop_core.group_brightloop_staff') or
                user.has_group('base.group_system') or
                user.has_group('account.group_account_invoice')):
            raise AccessError('Staff or Administrator privileges required to access internal application data.')
        return user

    def _parse_pagination(self):
        """Parse limit and offset from request params safely."""
        try:
            limit = int(request.params.get('limit', 50))
            limit = max(1, min(limit, 200))
        except (ValueError, TypeError):
            limit = 50

        try:
            offset = int(request.params.get('offset', 0))
            offset = max(0, offset)
        except (ValueError, TypeError):
            offset = 0

        return limit, offset

    # =========================================================================
    # 1. SUBSCRIPTIONS ENDPOINT
    # =========================================================================

    @http.route('/api/v1/app/subscriptions', type='http', auth='public', methods=['GET'], csrf=False)
    def app_list_subscriptions(self, **kw):
        """List all subscriptions across the system with filtering and search."""
        try:
            self._ensure_staff_or_admin()
            limit, offset = self._parse_pagination()
            state = request.params.get('state')
            search = request.params.get('search', '').strip()

            domain = []
            if state and state != 'all':
                domain.append(('state', '=', state))
            if search:
                domain.append('|')
                domain.append(('name', 'ilike', search))
                domain.append(('customer_id.name', 'ilike', search))

            Sub = request.env['brightloop.subscription'].sudo()
            total = Sub.search_count(domain)
            records = Sub.search(domain, order='create_date desc, id desc', limit=limit, offset=offset)

            items = []
            for sub in records:
                items.append({
                    'id': sub.id,
                    'name': sub.name,
                    'code': sub.code if hasattr(sub, 'code') and sub.code else sub.name,
                    'customer_id': sub.customer_id.id,
                    'customer_name': sub.customer_id.name,
                    'customer_email': sub.customer_id.email or '',
                    'plan_id': sub.subscription_plan_id.id if sub.subscription_plan_id else None,
                    'plan_name': sub.subscription_plan_id.name if sub.subscription_plan_id else 'Custom',
                    'state': sub.state,
                    'recurring_amount': float(sub.recurring_amount or 0.0),
                    'currency': sub.currency_id.name if sub.currency_id else 'USD',
                    'currency_symbol': sub.currency_id.symbol if sub.currency_id else '$',
                    'start_date': str(sub.start_date) if sub.start_date else None,
                    'end_date': str(sub.end_date) if sub.end_date else None,
                    'next_billing_date': str(sub.next_billing_date) if sub.next_billing_date else None,
                    'allow_pause': bool(sub.subscription_plan_id.allow_pause) if sub.subscription_plan_id else True,
                    'allow_close': bool(sub.subscription_plan_id.allow_early_closure) if sub.subscription_plan_id else True,
                    'created_at': str(sub.create_date),
                })

            return request.make_json_response({
                'status': 'success',
                'data': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'subscriptions': items,
                }
            }, status=200)

        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=403)
        except Exception as e:
            _logger.exception('Failed to list app subscriptions: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 2. SUBSCRIPTION ACTION (PAUSE, RESUME, RENEW, CLOSE)
    # =========================================================================

    @http.route('/api/v1/app/subscriptions/<int:sub_id>/action', type='http', auth='public', methods=['POST'], csrf=False)
    def app_subscription_action(self, sub_id, **kw):
        """Execute a lifecycle action on a subscription."""
        try:
            self._ensure_staff_or_admin()
            body = request.get_json_data() or kw
            action = body.get('action') if isinstance(body, dict) else None
            reason = body.get('reason') if isinstance(body, dict) else None

            if not action or action not in ('pause', 'resume', 'renew', 'close', 'confirm', 'activate'):
                return request.make_json_response({
                    'status': 'error',
                    'message': 'Valid action required: pause, resume, renew, close, confirm, activate.'
                }, status=400)

            sub = request.env['brightloop.subscription'].sudo().browse(sub_id)
            if not sub.exists():
                return request.make_json_response({'status': 'error', 'message': 'Subscription not found.'}, status=404)

            if action == 'pause':
                sub.action_pause(reason=reason)
            elif action == 'resume':
                sub.action_resume()
            elif action == 'renew':
                sub.action_renew(notes=reason)
            elif action == 'close':
                sub.action_close(reason=reason)
            elif action == 'confirm':
                sub.action_confirm()
            elif action == 'activate':
                sub.action_activate()

            return request.make_json_response({
                'status': 'success',
                'message': f'Subscription {sub.name} successfully executed action "{action}".',
                'data': {
                    'id': sub.id,
                    'state': sub.state,
                    'next_billing_date': str(sub.next_billing_date) if sub.next_billing_date else None,
                }
            }, status=200)

        except (UserError, ValidationError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=403)
        except Exception as e:
            _logger.exception('Failed to execute subscription action: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 3. CATALOG ENDPOINT (PRODUCTS & PLANS)
    # =========================================================================

    @http.route('/api/v1/app/catalog', type='http', auth='public', methods=['GET'], csrf=False)
    def app_get_catalog(self, **kw):
        """Retrieve active products and subscription plans catalog."""
        try:
            self._ensure_staff_or_admin()
            Plans = request.env['brightloop.subscription.plan'].sudo().search([('active', '=', True)])
            Products = request.env['product.template'].sudo().search([('active', '=', True)], limit=50)

            plans_data = []
            for p in Plans:
                plans_data.append({
                    'id': p.id,
                    'name': p.name,
                    'billing_interval': p.billing_interval,
                    'billing_interval_count': p.billing_interval_count,
                    'list_price': float(p.list_price or 0.0),
                    'currency': p.currency_id.name if p.currency_id else 'USD',
                    'currency_symbol': p.currency_id.symbol if p.currency_id else '$',
                    'allow_pause': p.allow_pause,
                    'allow_early_closure': p.allow_early_closure,
                    'auto_close': p.auto_close,
                    'active': p.active,
                })

            products_data = []
            for prod in Products:
                products_data.append({
                    'id': prod.id,
                    'name': prod.name,
                    'default_code': prod.default_code or '',
                    'list_price': float(prod.list_price or 0.0),
                    'currency': prod.currency_id.name if prod.currency_id else 'USD',
                    'currency_symbol': prod.currency_id.symbol if prod.currency_id else '$',
                    'type': prod.type,
                })

            return request.make_json_response({
                'status': 'success',
                'data': {
                    'plans': plans_data,
                    'products': products_data,
                }
            }, status=200)

        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=403)
        except Exception as e:
            _logger.exception('Failed to fetch catalog: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 4. QUOTATIONS & SALES ENDPOINT
    # =========================================================================

    @http.route('/api/v1/app/quotations', type='http', auth='public', methods=['GET'], csrf=False)
    def app_get_quotations(self, **kw):
        """Retrieve recent sales quotations and confirmed orders."""
        try:
            self._ensure_staff_or_admin()
            limit, offset = self._parse_pagination()
            state = request.params.get('state')

            domain = []
            if state and state != 'all':
                domain.append(('state', '=', state))

            Orders = request.env['sale.order'].sudo()
            total = Orders.search_count(domain)
            records = Orders.search(domain, order='date_order desc, id desc', limit=limit, offset=offset)

            orders_data = []
            for ord_rec in records:
                orders_data.append({
                    'id': ord_rec.id,
                    'name': ord_rec.name,
                    'partner_name': ord_rec.partner_id.name,
                    'date_order': str(ord_rec.date_order) if ord_rec.date_order else None,
                    'amount_total': float(ord_rec.amount_total or 0.0),
                    'currency': ord_rec.currency_id.name if ord_rec.currency_id else 'USD',
                    'currency_symbol': ord_rec.currency_id.symbol if ord_rec.currency_id else '$',
                    'state': ord_rec.state,
                })

            return request.make_json_response({
                'status': 'success',
                'data': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'quotations': orders_data,
                }
            }, status=200)

        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=403)
        except Exception as e:
            _logger.exception('Failed to fetch quotations: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 5. INVOICES ENDPOINT
    # =========================================================================

    @http.route('/api/v1/app/invoices', type='http', auth='public', methods=['GET'], csrf=False)
    def app_get_invoices(self, **kw):
        """Retrieve customer invoices and credit notes."""
        try:
            self._ensure_staff_or_admin()
            limit, offset = self._parse_pagination()
            payment_state = request.params.get('payment_state')

            domain = [('move_type', 'in', ['out_invoice', 'out_refund']), ('state', '=', 'posted')]
            if payment_state and payment_state != 'all':
                domain.append(('payment_state', '=', payment_state))

            Moves = request.env['account.move'].sudo()
            total = Moves.search_count(domain)
            records = Moves.search(domain, order='invoice_date desc, id desc', limit=limit, offset=offset)

            invoices_data = []
            for inv in records:
                invoices_data.append({
                    'id': inv.id,
                    'name': inv.name,
                    'partner_name': inv.partner_id.name,
                    'invoice_date': str(inv.invoice_date) if inv.invoice_date else None,
                    'invoice_date_due': str(inv.invoice_date_due) if inv.invoice_date_due else None,
                    'amount_total': float(inv.amount_total or 0.0),
                    'amount_residual': float(inv.amount_residual or 0.0),
                    'currency': inv.currency_id.name if inv.currency_id else 'USD',
                    'currency_symbol': inv.currency_id.symbol if inv.currency_id else '$',
                    'payment_state': inv.payment_state,
                    'move_type': inv.move_type,
                })

            return request.make_json_response({
                'status': 'success',
                'data': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'invoices': invoices_data,
                }
            }, status=200)

        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=403)
        except Exception as e:
            _logger.exception('Failed to fetch invoices: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 6. PAYMENTS ENDPOINT
    # =========================================================================

    @http.route('/api/v1/app/payments', type='http', auth='public', methods=['GET'], csrf=False)
    def app_get_payments(self, **kw):
        """Retrieve inbound customer payments."""
        try:
            self._ensure_staff_or_admin()
            limit, offset = self._parse_pagination()

            domain = [('payment_type', '=', 'inbound')]
            Payments = request.env['account.payment'].sudo()
            total = Payments.search_count(domain)
            records = Payments.search(domain, order='date desc, id desc', limit=limit, offset=offset)

            payments_data = []
            for pay in records:
                payments_data.append({
                    'id': pay.id,
                    'name': pay.name,
                    'partner_name': pay.partner_id.name if pay.partner_id else '',
                    'date': str(pay.date) if pay.date else None,
                    'amount': float(pay.amount or 0.0),
                    'currency': pay.currency_id.name if pay.currency_id else 'USD',
                    'currency_symbol': pay.currency_id.symbol if pay.currency_id else '$',
                    'journal_name': pay.journal_id.name if pay.journal_id else '',
                    'state': pay.state,
                })

            return request.make_json_response({
                'status': 'success',
                'data': {
                    'total': total,
                    'limit': limit,
                    'offset': offset,
                    'payments': payments_data,
                }
            }, status=200)

        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=403)
        except Exception as e:
            _logger.exception('Failed to fetch payments: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
