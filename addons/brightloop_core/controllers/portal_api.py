# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.controllers.portal_api
#
# Customer Self-Service Portal REST API Controller for Brightloop Subscription Intelligence
#
# PHASE 10 SCOPE
# --------------
# - RESTful JSON API endpoints for customer self-service.
# - Endpoints under /api/v1/portal/* namespace.
# - Enforces user authentication and commercial partner data isolation.
# - Customer profile (GET, PUT).
# - Customer subscriptions (GET list, GET detail, POST pause, POST resume, POST close, POST renew).
# - Customer invoices (GET list, GET detail, GET PDF).
# - Customer payments (GET list, GET detail).
# - Consolidated billing timeline (GET timeline).
# - Consistent JSON response structures and standard HTTP status codes.
# =============================================================================

import json
import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopPortalApiController(http.Controller):
    """
    REST API controller serving the Brightloop Customer Self-Service Portal backend.
    """

    def _get_service(self):
        return request.env['brightloop.portal.service']

    def _ensure_authenticated_customer(self):
        """
        Verify that request caller is an authenticated user and not public/anonymous.

        :return: res.users record or raises AccessError
        """
        user = request.env.user
        if not user or user._is_public() or user.id == request.env.ref('base.public_user').id:
            raise AccessError('Authentication required. Anonymous access is strictly prohibited.')
        return user

    def _parse_pagination(self):
        """Parse limit and offset from query parameters safely."""
        try:
            limit = int(request.params.get('limit', 50))
            limit = max(1, min(limit, 100))  # Bound between 1 and 100
        except (ValueError, TypeError):
            limit = 50

        try:
            offset = int(request.params.get('offset', 0))
            offset = max(0, offset)
        except (ValueError, TypeError):
            offset = 0

        return limit, offset

    # =========================================================================
    # 1. PROFILE ENDPOINTS
    # =========================================================================

    @http.route('/api/v1/portal/profile', type='http', auth='public', methods=['GET'], csrf=False)
    def get_profile(self, **kw):
        """Retrieve the authenticated customer's profile."""
        try:
            user = self._ensure_authenticated_customer()
            data = self._get_service().get_profile(user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to retrieve customer profile: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    @http.route('/api/v1/portal/profile', type='http', auth='public', methods=['PUT'], csrf=False)
    def update_profile(self, **kw):
        """Update permitted contact fields on the customer profile."""
        try:
            user = self._ensure_authenticated_customer()
            body = request.get_json_data() or kw
            if not isinstance(body, dict):
                return request.make_json_response({'status': 'error', 'message': 'JSON body required.'}, status=400)

            data = self._get_service().update_profile(body, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to update customer profile: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 2. SUBSCRIPTION ENDPOINTS
    # =========================================================================

    @http.route('/api/v1/portal/subscriptions', type='http', auth='public', methods=['GET'], csrf=False)
    def list_subscriptions(self, **kw):
        """List subscriptions belonging to the authenticated customer."""
        try:
            user = self._ensure_authenticated_customer()
            limit, offset = self._parse_pagination()
            data = self._get_service().list_subscriptions(user=user, limit=limit, offset=offset)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to list customer subscriptions: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    @http.route('/api/v1/portal/subscriptions/<int:sub_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_subscription_detail(self, sub_id, **kw):
        """Retrieve details of a specific subscription with ownership validation."""
        try:
            user = self._ensure_authenticated_customer()
            data = self._get_service().get_subscription_detail(sub_id, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to get subscription detail: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    @http.route('/api/v1/portal/subscriptions/<int:sub_id>/pause', type='http', auth='public', methods=['POST'], csrf=False)
    def pause_subscription(self, sub_id, **kw):
        """Customer action: Pause an active subscription contract."""
        try:
            user = self._ensure_authenticated_customer()
            body = request.get_json_data() or kw
            reason = body.get('reason') if isinstance(body, dict) else None

            data = self._get_service().pause_subscription(sub_id, reason=reason, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (UserError, ValidationError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to pause subscription: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    @http.route('/api/v1/portal/subscriptions/<int:sub_id>/resume', type='http', auth='public', methods=['POST'], csrf=False)
    def resume_subscription(self, sub_id, **kw):
        """Customer action: Resume a paused subscription contract."""
        try:
            user = self._ensure_authenticated_customer()
            data = self._get_service().resume_subscription(sub_id, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (UserError, ValidationError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to resume subscription: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    @http.route('/api/v1/portal/subscriptions/<int:sub_id>/close', type='http', auth='public', methods=['POST'], csrf=False)
    def close_subscription(self, sub_id, **kw):
        """Customer action: Request early closure for a subscription contract."""
        try:
            user = self._ensure_authenticated_customer()
            body = request.get_json_data() or kw
            reason = body.get('reason') if isinstance(body, dict) else None

            data = self._get_service().request_early_closure(sub_id, reason=reason, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (UserError, ValidationError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to close subscription: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    @http.route('/api/v1/portal/subscriptions/<int:sub_id>/renew', type='http', auth='public', methods=['POST'], csrf=False)
    def renew_subscription(self, sub_id, **kw):
        """Customer action: Renew a subscription contract."""
        try:
            user = self._ensure_authenticated_customer()
            data = self._get_service().renew_subscription(sub_id, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (UserError, ValidationError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to renew subscription: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 3. INVOICE ENDPOINTS
    # =========================================================================

    @http.route('/api/v1/portal/invoices', type='http', auth='public', methods=['GET'], csrf=False)
    def list_invoices(self, **kw):
        """List posted invoices belonging to the authenticated customer."""
        try:
            user = self._ensure_authenticated_customer()
            limit, offset = self._parse_pagination()
            data = self._get_service().list_invoices(user=user, limit=limit, offset=offset)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to list invoices: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    @http.route('/api/v1/portal/invoices/<int:inv_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_invoice_detail(self, inv_id, **kw):
        """Retrieve details of a customer invoice with ownership validation."""
        try:
            user = self._ensure_authenticated_customer()
            data = self._get_service().get_invoice_detail(inv_id, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to get invoice detail: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    @http.route('/api/v1/portal/invoices/<int:inv_id>/pdf', type='http', auth='public', methods=['GET'], csrf=False)
    def get_invoice_pdf(self, inv_id, **kw):
        """Download invoice PDF document securely with ownership validation."""
        try:
            user = self._ensure_authenticated_customer()
            res = self._get_service().get_invoice_pdf(inv_id, user=user)
            headers = [
                ('Content-Type', res['content_type']),
                ('Content-Length', str(len(res['content']))),
                ('Content-Disposition', f'attachment; filename="{res["filename"]}"'),
            ]
            return request.make_response(res['content'], headers=headers)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to render invoice PDF: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 4. PAYMENT ENDPOINTS
    # =========================================================================

    @http.route('/api/v1/portal/payments', type='http', auth='public', methods=['GET'], csrf=False)
    def list_payments(self, **kw):
        """List settled payments belonging to the authenticated customer."""
        try:
            user = self._ensure_authenticated_customer()
            limit, offset = self._parse_pagination()
            data = self._get_service().list_payments(user=user, limit=limit, offset=offset)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to list payments: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    @http.route('/api/v1/portal/payments/<int:pay_id>', type='http', auth='public', methods=['GET'], csrf=False)
    def get_payment_detail(self, pay_id, **kw):
        """Retrieve details of a customer payment with ownership validation."""
        try:
            user = self._ensure_authenticated_customer()
            data = self._get_service().get_payment_detail(pay_id, user=user)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to get payment detail: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

    # =========================================================================
    # 5. CONSOLIDATED BILLING TIMELINE
    # =========================================================================

    @http.route('/api/v1/portal/timeline', type='http', auth='public', methods=['GET'], csrf=False)
    def get_billing_timeline(self, **kw):
        """Retrieve unified chronological billing timeline across contracts, invoices, and payments."""
        try:
            user = self._ensure_authenticated_customer()
            limit, offset = self._parse_pagination()
            sub_id = int(request.params['subscription_id']) if request.params.get('subscription_id') else None

            data = self._get_service().get_billing_timeline(subscription_id=sub_id, user=user, limit=limit, offset=offset)
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except Exception as e:
            _logger.exception('Failed to get billing timeline: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)

