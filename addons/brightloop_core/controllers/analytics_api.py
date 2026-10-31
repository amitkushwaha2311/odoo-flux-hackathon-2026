# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.controllers.analytics_api
#
# Finance Dashboard & Analytics REST API Controller
#
# PHASE 11 SCOPE
# --------------
# - RESTful JSON endpoints under /api/v1/analytics/* namespace.
# - Role-based authorization: Internal Staff and Admin only.
# - Strict block on Customer portal users and Anonymous visitors.
# - Standardized JSON response formatting and appropriate HTTP status codes.
# - Read-only financial insights: Zero mutation capabilities.
# =============================================================================

import json
import logging

from odoo import http
from odoo.http import request
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopAnalyticsApiController(http.Controller):
    """
    REST API controller serving the Brightloop Financial Analytics and Dashboard data layer.
    """

    def _get_service(self):
        return request.env['brightloop.analytics.service']

    def _ensure_internal_user(self):
        """
        Verify that request caller is an authenticated internal staff or admin user.

        :return: res.users record or raises AccessError
        """
        user = request.env.user
        if not user or user._is_public() or user.id == request.env.ref('base.public_user', raise_if_not_found=False).id:
            raise AccessError('Authentication required. Anonymous access is strictly prohibited.')

        # Validate internal role
        self._get_service()._check_analytics_access(user=user)
        return user

    def _parse_int_param(self, param_name):
        """Safely parse integer parameter from query string."""
        val = request.params.get(param_name)
        if val:
            try:
                return int(val)
            except (ValueError, TypeError):
                raise ValidationError(f'Invalid integer for parameter "{param_name}": {val}')
        return None

    # =========================================================================
    # 1. OVERVIEW KPIS
    # =========================================================================

    @http.route('/api/v1/analytics/kpis', type='http', auth='public', methods=['GET'], csrf=False)
    def get_financial_kpis(self, **kw):
        """Retrieve top-level financial KPIs (MRR, ARR, Invoiced, Paid, Residual)."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            start_date = request.params.get('start_date')
            end_date = request.params.get('end_date')

            data = self._get_service().get_financial_kpis(
                company_id=company_id,
                currency_id=currency_id,
                start_date=start_date,
                end_date=end_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response(
                {'status': 'error', 'message': str(e)},
                status=401 if 'Authentication' in str(e) else 403,
            )
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get financial KPIs: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 2. REVENUE ANALYTICS & BREAKDOWNS
    # =========================================================================

    @http.route('/api/v1/analytics/revenue', type='http', auth='public', methods=['GET'], csrf=False)
    def get_revenue_analytics(self, **kw):
        """Retrieve revenue summary and breakdowns by plan, product, and customer."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            start_date = request.params.get('start_date')
            end_date = request.params.get('end_date')

            data = self._get_service().get_revenue_analytics(
                company_id=company_id,
                currency_id=currency_id,
                start_date=start_date,
                end_date=end_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get revenue analytics: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 3. MRR & ARR ANALYTICS
    # =========================================================================

    @http.route('/api/v1/analytics/mrr', type='http', auth='public', methods=['GET'], csrf=False)
    def get_mrr_arr(self, **kw):
        """Retrieve Monthly Recurring Revenue (MRR) and Annual Recurring Revenue (ARR)."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            as_of_date = request.params.get('as_of_date')

            data = self._get_service().get_mrr_arr_analytics(
                company_id=company_id,
                currency_id=currency_id,
                as_of_date=as_of_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get MRR analytics: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 4. SUBSCRIPTION GROWTH & CHURN
    # =========================================================================

    @http.route('/api/v1/analytics/subscriptions', type='http', auth='public', methods=['GET'], csrf=False)
    def get_subscription_growth(self, **kw):
        """Retrieve subscription status counts, growth rates, renewal rates, and churn rates."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            start_date = request.params.get('start_date')
            end_date = request.params.get('end_date')

            data = self._get_service().get_subscription_growth_metrics(
                company_id=company_id,
                start_date=start_date,
                end_date=end_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get subscription growth: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 4B. CUSTOMER FINANCIAL ANALYTICS
    # =========================================================================

    @http.route('/api/v1/analytics/customers', type='http', auth='public', methods=['GET'], csrf=False)
    def get_customer_metrics(self, **kw):
        """Retrieve aggregate customer financial metrics (ARPU, LTV, tier distribution)."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')

            data = self._get_service().get_customer_financial_metrics(
                company_id=company_id,
                currency_id=currency_id,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get customer metrics: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 5. INVOICE AGING REPORT
    # =========================================================================

    @http.route('/api/v1/analytics/aging', type='http', auth='public', methods=['GET'], csrf=False)
    def get_invoice_aging(self, **kw):
        """Retrieve invoice aging report with standard aging buckets."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            as_of_date = request.params.get('as_of_date')

            data = self._get_service().get_invoice_aging_report(
                company_id=company_id,
                currency_id=currency_id,
                as_of_date=as_of_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get aging report: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 6. INVOICE & PAYMENT STATISTICS
    # =========================================================================

    @http.route('/api/v1/analytics/invoices', type='http', auth='public', methods=['GET'], csrf=False)
    def get_invoice_analytics(self, **kw):
        """Retrieve customer invoice volume, residual, and status analytics."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            start_date = request.params.get('start_date')
            end_date = request.params.get('end_date')

            data = self._get_service().get_invoice_analytics(
                company_id=company_id,
                currency_id=currency_id,
                start_date=start_date,
                end_date=end_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get invoice analytics: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    @http.route('/api/v1/analytics/payments', type='http', auth='public', methods=['GET'], csrf=False)
    def get_payment_analytics(self, **kw):
        """Retrieve customer payment volumes, collections, and journal distributions."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            start_date = request.params.get('start_date')
            end_date = request.params.get('end_date')

            data = self._get_service().get_payment_analytics(
                company_id=company_id,
                currency_id=currency_id,
                start_date=start_date,
                end_date=end_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get payment analytics: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 7. PLAN & PRODUCT PERFORMANCE
    # =========================================================================

    @http.route('/api/v1/analytics/plans', type='http', auth='public', methods=['GET'], csrf=False)
    def get_plan_performance(self, **kw):
        """Retrieve plan performance metrics."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')

            data = self._get_service().get_plan_performance_analytics(
                company_id=company_id,
                currency_id=currency_id,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get plan performance: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    @http.route('/api/v1/analytics/products', type='http', auth='public', methods=['GET'], csrf=False)
    def get_product_performance(self, **kw):
        """Retrieve product variant revenue performance."""
        try:
            user = self._ensure_internal_user()
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')

            data = self._get_service().get_product_performance_analytics(
                company_id=company_id,
                currency_id=currency_id,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get product performance: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    # =========================================================================
    # 8. TRENDS & PERIOD COMPARISONS
    # =========================================================================

    @http.route('/api/v1/analytics/trends', type='http', auth='public', methods=['GET'], csrf=False)
    def get_trends(self, **kw):
        """Retrieve time-series trend points."""
        try:
            user = self._ensure_internal_user()
            metric = request.params.get('metric', 'revenue')
            interval = request.params.get('interval', 'month')
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            start_date = request.params.get('start_date')
            end_date = request.params.get('end_date')

            data = self._get_service().get_financial_trends(
                metric=metric,
                interval=interval,
                company_id=company_id,
                currency_id=currency_id,
                start_date=start_date,
                end_date=end_date,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to get trends: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)

    @http.route('/api/v1/analytics/compare', type='http', auth='public', methods=['GET'], csrf=False)
    def compare_periods(self, **kw):
        """Compare metric across two periods with absolute and percentage variance."""
        try:
            user = self._ensure_internal_user()
            metric = request.params.get('metric', 'revenue')
            company_id = self._parse_int_param('company_id')
            currency_id = self._parse_int_param('currency_id')
            c_start = request.params.get('current_start')
            c_end = request.params.get('current_end')
            p_start = request.params.get('previous_start')
            p_end = request.params.get('previous_end')

            data = self._get_service().compare_periods(
                metric=metric,
                current_start=c_start,
                current_end=c_end,
                previous_start=p_start,
                previous_end=p_end,
                company_id=company_id,
                currency_id=currency_id,
                user=user,
            )
            return request.make_json_response({'status': 'success', 'data': data}, status=200)
        except AccessError as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=401 if 'Authentication' in str(e) else 403)
        except (ValidationError, UserError) as e:
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=400)
        except Exception as e:
            _logger.exception('Failed to compare periods: %s', e)
            return request.make_json_response({'status': 'error', 'message': str(e)}, status=500)
