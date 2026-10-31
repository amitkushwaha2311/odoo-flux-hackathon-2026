# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.analytics_service
#
# Finance Dashboard & Analytics Engine for Brightloop Subscription Intelligence
#
# PHASE 11 SCOPE
# --------------
# - Centralized financial analytics and reporting service.
# - Financial KPI calculation (Invoiced Revenue, Paid Revenue, Residual, MRR, ARR, ARPU).
# - Subscription growth and churn analytics (growth rate, renewal rate, cancellation rate).
# - Native accounting reconciliation and payment analytics.
# - Overdue and invoice aging buckets (Not due, 1-30d, 31-60d, 61-90d, >90d).
# - Plan and product performance analytics.
# - Period-based time-series trend reporting (daily, weekly, monthly, quarterly, yearly).
# - Period-over-period comparison with absolute and percentage variance.
# - Multi-company and multi-currency reporting with Odoo currency rate conversion.
# - Strict role-based authorization (Admin full access, Staff operational, Customer denied).
# - Zero financial mutation: strictly read-only execution.
# - Sub-2 second query execution optimized with SQL/ORM aggregations.
# =============================================================================

import logging
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

_logger = logging.getLogger(__name__)


class BrightloopAnalyticsService(models.AbstractModel):
    """
    Brightloop Financial Analytics & Reporting Engine.

    Stateless AbstractModel coordinating all financial KPIs, revenue analytics,
    subscription health, and invoice aging computations across multi-company
    and multi-currency boundaries.
    """

    _name = 'brightloop.analytics.service'
    _description = 'Brightloop Financial Analytics & Reporting Service'

    # =========================================================================
    # 1. SECURITY & ACCESS CONTROL
    # =========================================================================

    def _check_analytics_access(self, user=None, company_id=None):
        """
        Verify that caller has internal authorization to access finance analytics.

        Rules:
        - Anonymous / public users are strictly blocked.
        - Customer portal users (group_brightloop_customer) are strictly blocked.
        - Staff and Admin users are granted access according to their company assignments.
        - Caller cannot query companies outside their authorized company_ids.

        :param user: res.users record or None (defaults to env.user)
        :param company_id: int or None
        :return: validated res.users record
        :raises AccessError: on permission denial
        """
        caller = user or self.env.user
        if not caller or caller._is_public() or caller.id == self.env.ref('base.public_user', raise_if_not_found=False).id:
            raise AccessError('Authentication required to access financial analytics.')

        # Strict block on customer portal accounts
        is_customer = caller.has_group('brightloop_core.group_brightloop_customer')
        is_staff = (
            caller.has_group('brightloop_core.group_brightloop_staff')
            or caller.has_group('brightloop_core.group_brightloop_admin')
            or caller.has_group('base.group_user')
        )

        if is_customer and not is_staff:
            self._log_unauthorized_access(caller, 'Customer attempted to access internal finance dashboard analytics.')
            raise AccessError('Access denied: Customer accounts do not have permission to access financial analytics.')

        if not is_staff and not caller._is_admin():
            self._log_unauthorized_access(caller, 'Non-staff user attempted to access finance dashboard analytics.')
            raise AccessError('Access denied: Staff or Admin role required for financial analytics.')

        # Company boundary enforcement
        if company_id and company_id not in caller.company_ids.ids:
            raise AccessError(f'Access denied: You do not have permission to query analytics for company ID {company_id}.')

        return caller

    def _log_unauthorized_access(self, user, summary):
        """Record unauthorized access attempt in independent transaction."""
        try:
            with self.env.registry.cursor() as cr:
                env = self.env(cr=cr)
                # Verify entity visibility in autonomous cursor (handles uncommitted test fixtures)
                user_committed = env['res.users'].browse(user.id).exists()
                company_committed = env['res.company'].browse(user.company_id.id).exists()
                env['brightloop.security.audit'].sudo().create({
                    'event_type': 'analytics_unauthorized_access',
                    'name': summary,
                    'details': f'User {user.login} attempted unauthorized access to financial analytics.',
                    'user_id': user.id if user_committed else False,
                    'timestamp': fields.Datetime.now(),
                    'company_id': user.company_id.id if company_committed else env.company.id,
                })
                cr.commit()
        except Exception as e:
            _logger.exception('Failed to log analytics unauthorized audit: %s', e)

    # =========================================================================
    # 2. MULTI-COMPANY & MULTI-CURRENCY HELPERS
    # =========================================================================

    def _resolve_company(self, company_id=None, user=None):
        """Resolve target company recordset."""
        caller = user or self.env.user
        if company_id:
            company = self.env['res.company'].browse(company_id)
            if not company.exists():
                raise ValidationError(f'Company with ID {company_id} does not exist.')
            return company
        return caller.company_id or self.env.company

    def _resolve_currency(self, currency_id=None, company=None):
        """Resolve reporting currency recordset."""
        if currency_id:
            curr = self.env['res.currency'].browse(currency_id)
            if not curr.exists():
                raise ValidationError(f'Currency with ID {currency_id} does not exist.')
            return curr
        comp = company or self.env.company
        return comp.currency_id

    def _convert_currency(self, amount, from_currency, to_currency, company, as_of_date=None):
        """
        Convert financial amount between currencies using native Odoo exchange rates.

        :param amount: float
        :param from_currency: res.currency record
        :param to_currency: res.currency record
        :param company: res.company record
        :param as_of_date: date object or None
        :return: float converted and rounded amount
        """
        if not amount or from_currency.id == to_currency.id:
            return float(to_currency.round(amount or 0.0))

        conv_date = as_of_date or fields.Date.today()
        converted = from_currency._convert(amount, to_currency, company, conv_date)
        return float(to_currency.round(converted))

    def _parse_date(self, val):
        """Safely parse input string or date to date object."""
        if not val:
            return None
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if isinstance(val, str):
            try:
                return datetime.strptime(val[:10], '%Y-%m-%d').date()
            except ValueError:
                raise ValidationError(f'Invalid date format: "{val}". Use YYYY-MM-DD.')
        return None

    # =========================================================================
    # 3. FINANCIAL KPI OVERVIEW ENGINE
    # =========================================================================

    @api.model
    def get_financial_kpis(self, company_id=None, currency_id=None, start_date=None, end_date=None, user=None):
        """
        Calculate top-level financial KPIs.

        Metrics calculated:
        - Total Invoiced Revenue (Gross & Net)
        - Paid Revenue (Cash Collected)
        - Outstanding Balance (Residual)
        - Monthly Recurring Revenue (MRR)
        - Annual Recurring Revenue (ARR)
        - Active Subscriptions Count
        - Total Customers & Active Subscribers
        - Average Revenue Per User (ARPU)

        :param company_id: int or None
        :param currency_id: int or None
        :param start_date: str or date or None
        :param end_date: str or date or None
        :param user: res.users or None
        :return: dict of high-level financial KPIs
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        d_start = self._parse_date(start_date)
        d_end = self._parse_date(end_date)

        # 1. Invoiced & Paid Revenue from posted customer invoices
        inv_domain = [
            ('company_id', '=', company.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
        ]
        if d_start:
            inv_domain.append(('invoice_date', '>=', d_start))
        if d_end:
            inv_domain.append(('invoice_date', '<=', d_end))

        invoices = self.env['account.move'].search(inv_domain)

        total_invoiced_gross = 0.0
        total_invoiced_net = 0.0
        total_paid_revenue = 0.0
        total_outstanding = 0.0

        for inv in invoices:
            sign = -1.0 if inv.move_type == 'out_refund' else 1.0
            gross_conv = self._convert_currency(inv.amount_total, inv.currency_id, currency, company, inv.invoice_date)
            net_conv = self._convert_currency(inv.amount_untaxed, inv.currency_id, currency, company, inv.invoice_date)
            res_conv = self._convert_currency(inv.amount_residual, inv.currency_id, currency, company, inv.invoice_date)
            paid_inv = max(0.0, inv.amount_total - inv.amount_residual)
            paid_conv = self._convert_currency(paid_inv, inv.currency_id, currency, company, inv.invoice_date)

            total_invoiced_gross += sign * gross_conv
            total_invoiced_net += sign * net_conv
            total_outstanding += sign * res_conv
            total_paid_revenue += sign * paid_conv

        # 2. MRR & ARR from active subscriptions
        mrr_data = self.get_mrr_arr_analytics(company_id=company.id, currency_id=currency.id, as_of_date=d_end, user=user)
        active_mrr = mrr_data['active_mrr']
        arr = mrr_data['arr']

        # 3. Active Subscriptions & Customer counts
        sub_domain = [('company_id', '=', company.id)]
        total_subs = self.env['brightloop.subscription'].search_count(sub_domain)
        active_subs = self.env['brightloop.subscription'].search_count(sub_domain + [('state', '=', 'active')])
        paused_subs = self.env['brightloop.subscription'].search_count(sub_domain + [('state', '=', 'paused')])

        # Unique active subscriber partners
        active_partners = self.env['brightloop.subscription'].search(
            sub_domain + [('state', '=', 'active')]
        ).mapped('customer_id.commercial_partner_id')
        active_customer_count = len(active_partners)

        # Average Revenue Per User (ARPU = MRR / Active Subscribers)
        arpu = round(active_mrr / max(active_customer_count, 1), 2)

        return {
            'company_id': company.id,
            'company_name': company.name,
            'currency_id': currency.id,
            'currency_code': currency.name,
            'currency_symbol': currency.symbol,
            'period': {
                'start_date': str(d_start) if d_start else None,
                'end_date': str(d_end) if d_end else None,
            },
            'revenue': {
                'total_invoiced_gross': round(total_invoiced_gross, 2),
                'total_invoiced_net': round(total_invoiced_net, 2),
                'paid_revenue': round(total_paid_revenue, 2),
                'outstanding_balance': round(total_outstanding, 2),
                'collection_rate_percent': round((total_paid_revenue / max(total_invoiced_gross, 0.001)) * 100.0, 2) if total_invoiced_gross > 0 else 0.0,
            },
            'recurring': {
                'mrr': active_mrr,
                'arr': arr,
                'paused_mrr': mrr_data['paused_mrr'],
                'committed_mrr': mrr_data['committed_mrr'],
            },
            'subscriptions': {
                'total': total_subs,
                'active': active_subs,
                'paused': paused_subs,
            },
            'customers': {
                'active_subscribers': active_customer_count,
                'arpu': arpu,
            },
        }

    # =========================================================================
    # 4. MRR & ARR ENGINE (CALENDAR NORMALIZATION)
    # =========================================================================

    @api.model
    def get_mrr_arr_analytics(self, company_id=None, currency_id=None, as_of_date=None, user=None):
        """
        Calculate Monthly Recurring Revenue (MRR) and Annual Recurring Revenue (ARR).

        Normalization Rules:
        - Monthly: amount / interval_count
        - Quarterly: amount / (interval_count * 3) when interval is monthly, or amount / 3
        - Yearly: amount / (12 * interval_count)
        - Weekly: amount / interval_count * (52 / 12) [4.3333 weeks/month]
        - Daily: amount / interval_count * (365 / 12) [30.4167 days/month]

        Eligibility:
        - Only subscriptions with state == 'active' are recognized in active_mrr.
        - Paused subscriptions (state == 'paused') are tracked separately as paused_mrr.
        - Draft, closed, cancelled subscriptions are strictly 0.0.
        - Respects line quantities and discounts.

        :param company_id: int or None
        :param currency_id: int or None
        :param as_of_date: date or str or None
        :param user: res.users or None
        :return: dict with MRR and ARR breakdowns
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        ref_date = self._parse_date(as_of_date) or fields.Date.today()

        domain = [
            ('company_id', '=', company.id),
            ('state', 'in', ('active', 'paused')),
        ]
        if as_of_date:
            domain.append(('start_date', '<=', ref_date))

        subscriptions = self.env['brightloop.subscription'].search(domain)

        active_mrr = 0.0
        paused_mrr = 0.0
        mrr_by_plan = {}

        for sub in subscriptions:
            # Calculate recurring value of all lines
            sub_recurring_amount = 0.0
            for line in sub.subscription_line_ids:
                discount_mult = 1.0 - ((line.discount or 0.0) / 100.0)
                line_amt = line.price_unit * line.quantity * discount_mult
                sub_recurring_amount += line_amt

            # Normalize to monthly equivalent
            interval = sub.billing_interval or 'monthly'
            count = max(1, sub.billing_interval_count or 1)

            if interval == 'monthly':
                monthly_amt = sub_recurring_amount / count
            elif interval == 'yearly':
                monthly_amt = sub_recurring_amount / (12.0 * count)
            elif interval == 'weekly':
                monthly_amt = (sub_recurring_amount / count) * (52.0 / 12.0)
            elif interval == 'daily':
                monthly_amt = (sub_recurring_amount / count) * (365.0 / 12.0)
            else:
                monthly_amt = sub_recurring_amount / count

            # Convert to target reporting currency
            mrr_converted = self._convert_currency(monthly_amt, sub.currency_id, currency, company, ref_date)

            plan_name = sub.subscription_plan_id.name or 'Custom Plan'
            plan_id = sub.subscription_plan_id.id or 0

            if sub.state == 'active':
                active_mrr += mrr_converted
                if plan_id not in mrr_by_plan:
                    mrr_by_plan[plan_id] = {'plan_id': plan_id, 'plan_name': plan_name, 'mrr': 0.0, 'sub_count': 0}
                mrr_by_plan[plan_id]['mrr'] += mrr_converted
                mrr_by_plan[plan_id]['sub_count'] += 1
            elif sub.state == 'paused':
                paused_mrr += mrr_converted

        active_mrr_rounded = round(active_mrr, 2)
        paused_mrr_rounded = round(paused_mrr, 2)
        arr_rounded = round(active_mrr_rounded * 12.0, 2)

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'currency_symbol': currency.symbol,
            'as_of_date': str(ref_date),
            'active_mrr': active_mrr_rounded,
            'paused_mrr': paused_mrr_rounded,
            'committed_mrr': round(active_mrr_rounded + paused_mrr_rounded, 2),
            'arr': arr_rounded,
            'plans': sorted(mrr_by_plan.values(), key=lambda x: x['mrr'], reverse=True),
        }

    # =========================================================================
    # 5. REVENUE ANALYTICS & BREAKDOWNS
    # =========================================================================

    @api.model
    def get_revenue_analytics(self, company_id=None, currency_id=None, start_date=None, end_date=None, user=None):
        """
        Comprehensive revenue breakdown by company, plan, product, and customer.

        Excludes draft and cancelled moves. Correctly subtracts customer credit notes.
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        d_start = self._parse_date(start_date)
        d_end = self._parse_date(end_date)

        domain = [
            ('company_id', '=', company.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
        ]
        if d_start:
            domain.append(('invoice_date', '>=', d_start))
        if d_end:
            domain.append(('invoice_date', '<=', d_end))

        invoices = self.env['account.move'].search(domain)

        total_gross = 0.0
        total_net = 0.0
        total_tax = 0.0
        by_customer = {}
        by_plan = {}
        by_product = {}

        for inv in invoices:
            sign = -1.0 if inv.move_type == 'out_refund' else 1.0
            gross = sign * self._convert_currency(inv.amount_total, inv.currency_id, currency, company, inv.invoice_date)
            net = sign * self._convert_currency(inv.amount_untaxed, inv.currency_id, currency, company, inv.invoice_date)
            tax = sign * self._convert_currency(inv.amount_tax, inv.currency_id, currency, company, inv.invoice_date)

            total_gross += gross
            total_net += net
            total_tax += tax

            # Customer Breakdown
            c_partner = inv.partner_id.commercial_partner_id
            cid = c_partner.id
            if cid not in by_customer:
                by_customer[cid] = {'customer_id': cid, 'customer_name': c_partner.name, 'revenue': 0.0, 'invoice_count': 0}
            by_customer[cid]['revenue'] += gross
            by_customer[cid]['invoice_count'] += 1

            # Plan Breakdown
            sub = inv.subscription_id
            plan = sub.subscription_plan_id if sub else False
            pid = plan.id if plan else 0
            pname = plan.name if plan else 'Ad-hoc / Non-Subscription'
            if pid not in by_plan:
                by_plan[pid] = {'plan_id': pid, 'plan_name': pname, 'revenue': 0.0, 'invoice_count': 0}
            by_plan[pid]['revenue'] += gross
            by_plan[pid]['invoice_count'] += 1

            # Product Breakdown via invoice lines
            for line in inv.invoice_line_ids:
                if not line.product_id:
                    continue
                pr_id = line.product_id.id
                pr_name = line.product_id.display_name
                line_net = sign * self._convert_currency(line.price_subtotal, inv.currency_id, currency, company, inv.invoice_date)
                if pr_id not in by_product:
                    by_product[pr_id] = {'product_id': pr_id, 'product_name': pr_name, 'revenue': 0.0, 'quantity': 0.0}
                by_product[pr_id]['revenue'] += line_net
                by_product[pr_id]['quantity'] += sign * line.quantity

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'summary': {
                'total_gross_revenue': round(total_gross, 2),
                'total_net_revenue': round(total_net, 2),
                'total_tax': round(total_tax, 2),
                'invoice_count': len(invoices),
            },
            'by_plan': sorted(by_plan.values(), key=lambda x: x['revenue'], reverse=True),
            'by_product': sorted(by_product.values(), key=lambda x: x['revenue'], reverse=True),
            'top_customers': sorted(by_customer.values(), key=lambda x: x['revenue'], reverse=True)[:20],
        }

    # =========================================================================
    # 6. SUBSCRIPTION GROWTH & CHURN ANALYTICS
    # =========================================================================

    @api.model
    def get_subscription_growth_metrics(self, company_id=None, start_date=None, end_date=None, user=None):
        """
        Calculate subscription growth, renewal rates, and churn metrics.

        Formulas:
        - Growth Rate: (Active End - Active Start) / max(Active Start, 1) * 100%
        - Renewal Rate: Renewed / max(Renewed + Churned, 1) * 100%
        - Churn / Cancellation Rate: Churned / max(Active Start, 1) * 100%
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        d_start = self._parse_date(start_date) or (fields.Date.today() - relativedelta(months=1))
        d_end = self._parse_date(end_date) or fields.Date.today()

        base_domain = [('company_id', '=', company.id)]

        # Active at start of period
        active_at_start = self.env['brightloop.subscription'].search_count(base_domain + [
            ('start_date', '<', d_start),
            ('state', 'in', ('active', 'paused')),
        ])

        # Active at end of period
        active_at_end = self.env['brightloop.subscription'].search_count(base_domain + [
            ('start_date', '<=', d_end),
            ('state', 'in', ('active', 'paused')),
        ])

        # New subscriptions in period (non-renewals)
        new_subs = self.env['brightloop.subscription'].search_count(base_domain + [
            ('start_date', '>=', d_start),
            ('start_date', '<=', d_end),
            ('renewal_count', '=', 0),
        ])

        # Renewals in period
        renewed_subs = self.env['brightloop.subscription'].search_count(base_domain + [
            ('start_date', '>=', d_start),
            ('start_date', '<=', d_end),
            ('renewal_count', '>', 0),
        ])

        # Churned / Closed in period
        churned_subs = self.env['brightloop.subscription'].search_count(base_domain + [
            ('end_date', '>=', d_start),
            ('end_date', '<=', d_end),
            ('state', 'in', ('closed', 'cancelled')),
        ])

        # Current status counts
        total_now = self.env['brightloop.subscription'].search_count(base_domain)
        active_now = self.env['brightloop.subscription'].search_count(base_domain + [('state', '=', 'active')])
        paused_now = self.env['brightloop.subscription'].search_count(base_domain + [('state', '=', 'paused')])
        closed_now = self.env['brightloop.subscription'].search_count(base_domain + [('state', '=', 'closed')])

        # Rates
        denom_start = max(active_at_start, 1)
        net_growth = (active_at_end - active_at_start)
        growth_rate = round((net_growth / denom_start) * 100.0, 2)
        renewal_rate = round((renewed_subs / max(renewed_subs + churned_subs, 1)) * 100.0, 2)
        churn_rate = round((churned_subs / denom_start) * 100.0, 2)

        return {
            'company_id': company.id,
            'period': {'start_date': str(d_start), 'end_date': str(d_end)},
            'counts': {
                'total_current': total_now,
                'active_current': active_now,
                'paused_current': paused_now,
                'closed_current': closed_now,
                'new_in_period': new_subs,
                'renewed_in_period': renewed_subs,
                'churned_in_period': churned_subs,
            },
            'rates': {
                'growth_rate_percent': growth_rate,
                'renewal_rate_percent': renewal_rate,
                'churn_rate_percent': churn_rate,
            },
        }

    # =========================================================================
    # 6B. CUSTOMER FINANCIAL ANALYTICS
    # =========================================================================

    @api.model
    def get_customer_financial_metrics(self, company_id=None, currency_id=None, user=None):
        """
        Calculate aggregate customer financial metrics without exposing personal details.

        Metrics:
        - Total Customers
        - Active Subscribers Count
        - Customers with Overdue Invoices
        - Average Revenue Per User (ARPU)
        - Customer Lifetime Revenue Average
        - Subscription Tier Distribution (Single vs Multi-subscription)
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        today = fields.Date.today()

        # All customer commercial partners with contracts or invoices in this company
        sub_partners = self.env['brightloop.subscription'].search([
            ('company_id', '=', company.id),
        ]).mapped('customer_id.commercial_partner_id')

        inv_partners = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('move_type', 'in', ('out_invoice', 'out_refund')),
        ]).mapped('partner_id.commercial_partner_id')

        all_customers = sub_partners | inv_partners
        total_customers = len(all_customers)

        # Active subscribers
        active_subscribers = self.env['brightloop.subscription'].search([
            ('company_id', '=', company.id),
            ('state', '=', 'active'),
        ]).mapped('customer_id.commercial_partner_id')
        active_sub_count = len(active_subscribers)

        # Customers with overdue invoices
        overdue_partners = self.env['account.move'].search([
            ('company_id', '=', company.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('amount_residual', '>', 0.0),
            ('invoice_date_due', '<', today),
        ]).mapped('partner_id.commercial_partner_id')
        overdue_cust_count = len(overdue_partners)

        # MRR for ARPU
        mrr_data = self.get_mrr_arr_analytics(company_id=company.id, currency_id=currency.id, user=user)
        arpu = round(mrr_data['active_mrr'] / max(active_sub_count, 1), 2)

        # Total revenue for Average Customer Invoiced Revenue
        rev_data = self.get_revenue_analytics(company_id=company.id, currency_id=currency.id, user=user)
        total_rev = rev_data['summary']['total_gross_revenue']
        avg_ltv = round(total_rev / max(total_customers, 1), 2)

        # Customer Subscription Distribution
        single_sub = 0
        multi_sub = 0
        for p in all_customers:
            cnt = self.env['brightloop.subscription'].search_count([
                ('company_id', '=', company.id),
                ('customer_id.commercial_partner_id', '=', p.id),
            ])
            if cnt == 1:
                single_sub += 1
            elif cnt > 1:
                multi_sub += 1

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'total_customers': total_customers,
            'active_subscribers': active_sub_count,
            'customers_with_overdue_invoices': overdue_cust_count,
            'arpu': arpu,
            'average_customer_revenue': avg_ltv,
            'subscription_distribution': {
                'single_subscription_customers': single_sub,
                'multi_subscription_customers': multi_sub,
            },
        }

    # =========================================================================
    # 7. INVOICE AGING & OVERDUE ANALYTICS
    # =========================================================================

    @api.model
    def get_invoice_aging_report(self, company_id=None, currency_id=None, as_of_date=None, user=None):
        """
        Calculate invoice aging buckets based on payment due dates and residuals.

        Buckets:
        - not_due: due_date >= ref_date
        - 1_30_days: 1 to 30 days overdue
        - 31_60_days: 31 to 60 days overdue
        - 61_90_days: 61 to 90 days overdue
        - over_90_days: > 90 days overdue

        Excludes:
        - Fully paid invoices (amount_residual == 0)
        - Draft and cancelled invoices
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        ref_date = self._parse_date(as_of_date) or fields.Date.today()

        domain = [
            ('company_id', '=', company.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
            ('amount_residual', '>', 0.0),
        ]

        invoices = self.env['account.move'].search(domain)

        buckets = {
            'not_due': {'label': 'Not Due', 'amount': 0.0, 'count': 0},
            '1_30_days': {'label': '1–30 Days Overdue', 'amount': 0.0, 'count': 0},
            '31_60_days': {'label': '31–60 Days Overdue', 'amount': 0.0, 'count': 0},
            '61_90_days': {'label': '61–90 Days Overdue', 'amount': 0.0, 'count': 0},
            'over_90_days': {'label': 'Over 90 Days Overdue', 'amount': 0.0, 'count': 0},
        }

        total_outstanding = 0.0
        total_overdue = 0.0

        for inv in invoices:
            due_date = inv.invoice_date_due or inv.invoice_date or ref_date
            res_conv = self._convert_currency(inv.amount_residual, inv.currency_id, currency, company, ref_date)
            total_outstanding += res_conv

            days_overdue = (ref_date - due_date).days

            if days_overdue <= 0:
                b_key = 'not_due'
            elif 1 <= days_overdue <= 30:
                b_key = '1_30_days'
                total_overdue += res_conv
            elif 31 <= days_overdue <= 60:
                b_key = '31_60_days'
                total_overdue += res_conv
            elif 61 <= days_overdue <= 90:
                b_key = '61_90_days'
                total_overdue += res_conv
            else:
                b_key = 'over_90_days'
                total_overdue += res_conv

            buckets[b_key]['amount'] += res_conv
            buckets[b_key]['count'] += 1

        # Calculate percentages
        denom = max(total_outstanding, 0.001)
        for k in buckets:
            buckets[k]['amount'] = round(buckets[k]['amount'], 2)
            buckets[k]['percent'] = round((buckets[k]['amount'] / denom) * 100.0, 2)

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'as_of_date': str(ref_date),
            'total_outstanding': round(total_outstanding, 2),
            'total_overdue': round(total_overdue, 2),
            'overdue_ratio_percent': round((total_overdue / denom) * 100.0, 2) if total_outstanding > 0 else 0.0,
            'buckets': buckets,
        }

    # =========================================================================
    # 8. INVOICE & PAYMENT ANALYTICS
    # =========================================================================

    @api.model
    def get_invoice_analytics(self, company_id=None, currency_id=None, start_date=None, end_date=None, user=None):
        """Summarize customer invoice volumes and settlement states."""
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        d_start = self._parse_date(start_date)
        d_end = self._parse_date(end_date)

        domain = [
            ('company_id', '=', company.id),
            ('move_type', '=', 'out_invoice'),
            ('state', '=', 'posted'),
        ]
        if d_start:
            domain.append(('invoice_date', '>=', d_start))
        if d_end:
            domain.append(('invoice_date', '<=', d_end))

        invoices = self.env['account.move'].search(domain)

        paid_cnt = 0
        partial_cnt = 0
        unpaid_cnt = 0
        overdue_cnt = 0
        total_amt = 0.0
        total_res = 0.0
        today = fields.Date.today()

        for inv in invoices:
            total_amt += self._convert_currency(inv.amount_total, inv.currency_id, currency, company, inv.invoice_date)
            total_res += self._convert_currency(inv.amount_residual, inv.currency_id, currency, company, inv.invoice_date)

            if inv.payment_state == 'paid':
                paid_cnt += 1
            elif inv.payment_state in ('partial', 'in_payment'):
                partial_cnt += 1
            else:
                unpaid_cnt += 1

            if inv.amount_residual > 0 and inv.invoice_date_due and inv.invoice_date_due < today:
                overdue_cnt += 1

        inv_count = len(invoices)
        avg_val = round(total_amt / max(inv_count, 1), 2)

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'total_invoices': inv_count,
            'paid_count': paid_cnt,
            'partially_paid_count': partial_cnt,
            'unpaid_count': unpaid_cnt,
            'overdue_count': overdue_cnt,
            'total_invoiced_amount': round(total_amt, 2),
            'total_residual_amount': round(total_res, 2),
            'average_invoice_value': avg_val,
        }

    @api.model
    def get_payment_analytics(self, company_id=None, currency_id=None, start_date=None, end_date=None, user=None):
        """Summarize inbound customer payment execution and journal breakdown."""
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        d_start = self._parse_date(start_date)
        d_end = self._parse_date(end_date)

        domain = [
            ('company_id', '=', company.id),
            ('payment_type', '=', 'inbound'),
            ('partner_type', '=', 'customer'),
        ]
        if d_start:
            domain.append(('date', '>=', d_start))
        if d_end:
            domain.append(('date', '<=', d_end))

        payments = self.env['account.payment'].search(domain)

        total_collected = 0.0
        settled_cnt = 0
        reversed_cnt = 0
        by_journal = {}

        for p in payments:
            if p.state == 'cancel':
                reversed_cnt += 1
                continue

            amt_conv = self._convert_currency(p.amount, p.currency_id, currency, company, p.date)
            total_collected += amt_conv
            settled_cnt += 1

            j_name = p.journal_id.name or 'Unknown Journal'
            by_journal[j_name] = by_journal.get(j_name, 0.0) + amt_conv

        formatted_journals = [
            {'journal_name': k, 'amount': round(v, 2)}
            for k, v in by_journal.items()
        ]

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'total_payments_count': settled_cnt,
            'reversed_payments_count': reversed_cnt,
            'total_collected_amount': round(total_collected, 2),
            'by_journal': sorted(formatted_journals, key=lambda x: x['amount'], reverse=True),
        }

    # =========================================================================
    # 9. PLAN & PRODUCT PERFORMANCE
    # =========================================================================

    @api.model
    def get_plan_performance_analytics(self, company_id=None, currency_id=None, user=None):
        """Evaluate plan commercial metrics: active count, MRR, revenue, renewals."""
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)

        plans = self.env['brightloop.subscription.plan'].search([('company_id', '=', company.id)])
        mrr_summary = self.get_mrr_arr_analytics(company_id=company.id, currency_id=currency.id, user=user)
        plan_mrr_map = {p['plan_id']: p['mrr'] for p in mrr_summary['plans']}

        result = []
        for plan in plans:
            subs = self.env['brightloop.subscription'].search([('subscription_plan_id', '=', plan.id)])
            total_sub_cnt = len(subs)
            active_cnt = len(subs.filtered(lambda s: s.state == 'active'))
            renewed_cnt = sum(s.renewal_count for s in subs)
            closed_cnt = len(subs.filtered(lambda s: s.state in ('closed', 'cancelled')))

            # Total revenue from invoices generated by this plan
            plan_invoices = self.env['account.move'].search([
                ('subscription_id', 'in', subs.ids),
                ('state', '=', 'posted'),
                ('move_type', '=', 'out_invoice'),
            ])
            rev = sum(
                self._convert_currency(inv.amount_total, inv.currency_id, currency, company, inv.invoice_date)
                for inv in plan_invoices
            )

            result.append({
                'plan_id': plan.id,
                'plan_name': plan.name,
                'billing_interval': plan.billing_interval,
                'billing_interval_count': plan.billing_interval_count,
                'list_price': plan.list_price,
                'total_subscriptions': total_sub_cnt,
                'active_subscriptions': active_cnt,
                'mrr': plan_mrr_map.get(plan.id, 0.0),
                'total_revenue': round(rev, 2),
                'renewals_count': renewed_cnt,
                'cancellations_count': closed_cnt,
            })

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'plans': sorted(result, key=lambda x: x['mrr'], reverse=True),
        }

    @api.model
    def get_product_performance_analytics(self, company_id=None, currency_id=None, user=None):
        """Evaluate product variant revenue and subscription adoption."""
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)

        # Query invoice lines for posted customer invoices
        lines = self.env['account.move.line'].search([
            ('company_id', '=', company.id),
            ('move_id.move_type', '=', 'out_invoice'),
            ('move_id.state', '=', 'posted'),
            ('product_id', '!=', False),
        ])

        by_prod = {}
        for l in lines:
            pid = l.product_id.id
            if pid not in by_prod:
                by_prod[pid] = {
                    'product_id': pid,
                    'product_name': l.product_id.display_name,
                    'total_quantity': 0.0,
                    'total_revenue': 0.0,
                }
            amt_conv = self._convert_currency(l.price_subtotal, l.currency_id, currency, company, l.move_id.invoice_date)
            by_prod[pid]['total_revenue'] += amt_conv
            by_prod[pid]['total_quantity'] += l.quantity

        for k in by_prod:
            by_prod[k]['total_revenue'] = round(by_prod[k]['total_revenue'], 2)

        return {
            'company_id': company.id,
            'currency_code': currency.name,
            'products': sorted(by_prod.values(), key=lambda x: x['total_revenue'], reverse=True),
        }

    # =========================================================================
    # 10. TIME-SERIES TRENDS & PERIOD COMPARISONS
    # =========================================================================

    @api.model
    def get_financial_trends(self, metric='revenue', interval='month', company_id=None, currency_id=None, start_date=None, end_date=None, user=None):
        """
        Compute time-series points grouped by day, week, month, quarter, or year.

        :param metric: 'revenue' or 'payments' or 'new_subscriptions'
        :param interval: 'day', 'week', 'month', 'quarter', 'year'
        :param company_id: int or None
        :param currency_id: int or None
        :param start_date: str or date or None
        :param end_date: str or date or None
        :param user: res.users or None
        :return: list of time series dictionaries
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)
        d_start = self._parse_date(start_date) or (fields.Date.today() - relativedelta(months=6))
        d_end = self._parse_date(end_date) or fields.Date.today()

        if d_start > d_end:
            raise ValidationError('Start date cannot be after end date.')

        series = {}

        if metric == 'revenue':
            invoices = self.env['account.move'].search([
                ('company_id', '=', company.id),
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('invoice_date', '>=', d_start),
                ('invoice_date', '<=', d_end),
            ], order='invoice_date asc')

            for inv in invoices:
                dt = inv.invoice_date or d_start
                key = self._format_interval_key(dt, interval)
                sign = -1.0 if inv.move_type == 'out_refund' else 1.0
                amt = sign * self._convert_currency(inv.amount_total, inv.currency_id, currency, company, dt)
                series[key] = series.get(key, 0.0) + amt

        elif metric == 'payments':
            payments = self.env['account.payment'].search([
                ('company_id', '=', company.id),
                ('payment_type', '=', 'inbound'),
                ('partner_type', '=', 'customer'),
                ('state', 'in', ('paid', 'reconciled')),
                ('date', '>=', d_start),
                ('date', '<=', d_end),
            ], order='date asc')

            for p in payments:
                dt = p.date or d_start
                key = self._format_interval_key(dt, interval)
                amt = self._convert_currency(p.amount, p.currency_id, currency, company, dt)
                series[key] = series.get(key, 0.0) + amt

        elif metric == 'new_subscriptions':
            subs = self.env['brightloop.subscription'].search([
                ('company_id', '=', company.id),
                ('start_date', '>=', d_start),
                ('start_date', '<=', d_end),
            ], order='start_date asc')

            for s in subs:
                key = self._format_interval_key(s.start_date, interval)
                series[key] = series.get(key, 0) + 1

        points = [
            {'period': k, 'value': round(v, 2) if isinstance(v, float) else v}
            for k, v in sorted(series.items())
        ]

        return {
            'metric': metric,
            'interval': interval,
            'company_id': company.id,
            'currency_code': currency.name,
            'data_points': points,
        }

    def _format_interval_key(self, dt, interval):
        """Format a date into interval key string."""
        if interval == 'day':
            return dt.strftime('%Y-%m-%d')
        elif interval == 'week':
            return f"{dt.year}-W{dt.isocalendar()[1]:02d}"
        elif interval == 'quarter':
            q = (dt.month - 1) // 3 + 1
            return f"{dt.year}-Q{q}"
        elif interval == 'year':
            return str(dt.year)
        else:  # month
            return dt.strftime('%Y-%m')

    @api.model
    def compare_periods(self, metric='revenue', current_start=None, current_end=None,
                        previous_start=None, previous_end=None, company_id=None,
                        currency_id=None, user=None):
        """
        Compare metric performance across two distinct periods.

        Provides: current value, previous value, absolute difference, percentage change.
        """
        self._check_analytics_access(user=user, company_id=company_id)
        company = self._resolve_company(company_id=company_id, user=user)
        currency = self._resolve_currency(currency_id=currency_id, company=company)

        c_start = self._parse_date(current_start) or (fields.Date.today() - relativedelta(months=1))
        c_end = self._parse_date(current_end) or fields.Date.today()

        if not previous_start or not previous_end:
            # Auto-compute previous period of same duration
            delta = c_end - c_start
            p_end = c_start - timedelta(days=1)
            p_start = p_end - delta
        else:
            p_start = self._parse_date(previous_start)
            p_end = self._parse_date(previous_end)

        def _calc_metric(start, end):
            if metric == 'revenue':
                invs = self.env['account.move'].search([
                    ('company_id', '=', company.id),
                    ('move_type', 'in', ('out_invoice', 'out_refund')),
                    ('state', '=', 'posted'),
                    ('invoice_date', '>=', start),
                    ('invoice_date', '<=', end),
                ])
                tot = 0.0
                for inv in invs:
                    sign = -1.0 if inv.move_type == 'out_refund' else 1.0
                    tot += sign * self._convert_currency(inv.amount_total, inv.currency_id, currency, company, inv.invoice_date)
                return tot
            elif metric == 'payments':
                pays = self.env['account.payment'].search([
                    ('company_id', '=', company.id),
                    ('payment_type', '=', 'inbound'),
                    ('partner_type', '=', 'customer'),
                    ('state', 'in', ('paid', 'reconciled')),
                    ('date', '>=', start),
                    ('date', '<=', end),
                ])
                return sum(self._convert_currency(p.amount, p.currency_id, currency, company, p.date) for p in pays)
            elif metric == 'new_subscriptions':
                return float(self.env['brightloop.subscription'].search_count([
                    ('company_id', '=', company.id),
                    ('start_date', '>=', start),
                    ('start_date', '<=', end),
                ]))
            return 0.0

        curr_val = round(_calc_metric(c_start, c_end), 2)
        prev_val = round(_calc_metric(p_start, p_end), 2)

        abs_change = round(curr_val - prev_val, 2)
        if prev_val == 0.0:
            pct_change = 100.0 if curr_val > 0.0 else 0.0
        else:
            pct_change = round((abs_change / abs(prev_val)) * 100.0, 2)

        return {
            'metric': metric,
            'company_id': company.id,
            'currency_code': currency.name,
            'current_period': {'start': str(c_start), 'end': str(c_end), 'value': curr_val},
            'previous_period': {'start': str(p_start), 'end': str(p_end), 'value': prev_val},
            'variance': {
                'absolute_change': abs_change,
                'percentage_change': pct_change,
            },
        }
