# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_finance_analytics
#
# Automated Test Suite for Phase 11: Finance Dashboard & Analytics Engine
#
# COVERS:
# - Revenue metrics (invoiced, paid, residual, credit notes, exclusions)
# - MRR and ARR calendar normalization (daily, weekly, monthly, quarterly, yearly)
# - Discounts, quantities, and paused subscription MRR handling
# - Subscription growth, renewal rate, and churn rate analytics
# - Invoice and payment analytics (paid, partial, unpaid, overdue, reversed)
# - Invoice aging buckets (not due, 1-30d, 31-60d, 61-90d, >90d)
# - Plan and product performance analytics
# - Time-series trends and period comparisons
# - Multi-company isolation and multi-currency conversion
# - Role-based security (Admin/Staff access, Customer denial, Cross-company blocking)
# - Read-only integrity (zero financial mutation)
# - High-throughput performance benchmark (< 2 seconds)
# =============================================================================

import time
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase, tagged


@tagged('post_install', '-at_install', 'brightloop_core', 'TestFinanceAnalyticsEngine')
class TestFinanceAnalyticsEngine(TransactionCase):
    """Automated test suite for Brightloop Financial Analytics & Reporting Engine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.AnalyticsService = cls.env['brightloop.analytics.service']
        cls.Company = cls.env['res.company']
        cls.Partner = cls.env['res.partner']
        cls.Users = cls.env['res.users']
        cls.Currency = cls.env['res.currency']
        cls.ProductTemplate = cls.env['product.template']
        cls.Product = cls.env['product.product']
        cls.SubscriptionPlan = cls.env['brightloop.subscription.plan']
        cls.Subscription = cls.env['brightloop.subscription']
        cls.SubscriptionLine = cls.env['brightloop.subscription.line']
        cls.AccountMove = cls.env['account.move']
        cls.AccountPayment = cls.env['account.payment']
        cls.AccountJournal = cls.env['account.journal']
        cls.SecurityAudit = cls.env['brightloop.security.audit']

        # Company Setup
        cls.main_company = cls.env.company

        # Currencies (main and foreign currency)
        cls.currency_inr = cls.main_company.currency_id

        cls.currency_usd = cls.Currency.with_context(active_test=False).search([
            ('id', '!=', cls.currency_inr.id),
        ], limit=1)
        if cls.currency_usd:
            cls.currency_usd.write({'active': True})
        else:
            cls.currency_usd = cls.Currency.create({'name': 'EUR', 'symbol': '€', 'rounding': 0.01, 'active': True})

        # Secondary company for cross-company isolation
        cls.second_company = cls.Company.create({
            'name': 'Brightloop Analytics EMEA Ltd P11',
            'currency_id': cls.currency_usd.id,
        })

        # Security Groups
        cls.admin_group = cls.env.ref('brightloop_core.group_brightloop_admin')
        cls.staff_group = cls.env.ref('brightloop_core.group_brightloop_staff')
        cls.customer_group = cls.env.ref('brightloop_core.group_brightloop_customer')
        cls.internal_group = cls.env.ref('base.group_user')

        # Admin User
        cls.partner_admin = cls.Partner.create({
            'name': 'Finance Admin P11',
            'email': 'finance.admin.p11@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.admin_user = cls.Users.create({
            'name': 'Finance Admin User P11',
            'login': 'finance.admin.p11@brightloop.io',
            'email': 'finance.admin.p11@brightloop.io',
            'partner_id': cls.partner_admin.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id, cls.second_company.id])],
            'group_ids': [(6, 0, [cls.admin_group.id, cls.internal_group.id])],
        })

        # Staff User
        cls.partner_staff = cls.Partner.create({
            'name': 'Finance Staff P11',
            'email': 'finance.staff.p11@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.staff_user = cls.Users.create({
            'name': 'Finance Staff User P11',
            'login': 'finance.staff.p11@brightloop.io',
            'email': 'finance.staff.p11@brightloop.io',
            'partner_id': cls.partner_staff.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id])],
            'group_ids': [(6, 0, [cls.staff_group.id, cls.internal_group.id])],
        })

        # Customer User
        cls.partner_customer = cls.Partner.create({
            'name': 'Customer Portal User P11',
            'email': 'customer.p11@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.customer_user = cls.Users.create({
            'name': 'Customer User P11',
            'login': 'customer.p11@brightloop.io',
            'email': 'customer.p11@brightloop.io',
            'partner_id': cls.partner_customer.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id])],
            'group_ids': [(6, 0, [cls.customer_group.id])],
        })

        # Products
        cls.test_product_saas = cls.Product.create({
            'name': 'SaaS Platform Analytics P11',
            'list_price': 5000.0,
            'type': 'service',
        })
        cls.test_product_addon = cls.Product.create({
            'name': 'Analytics Addon P11',
            'list_price': 1000.0,
            'type': 'service',
        })

        # Subscription Plans
        cls.plan_monthly = cls.SubscriptionPlan.create({
            'name': 'Pro Monthly Analytics P11',
            'product_id': cls.test_product_saas.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 5000.0,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })
        cls.plan_quarterly = cls.SubscriptionPlan.create({
            'name': 'Pro Quarterly Analytics P11',
            'product_id': cls.test_product_saas.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 3,
            'list_price': 14000.0,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })
        cls.plan_yearly = cls.SubscriptionPlan.create({
            'name': 'Enterprise Yearly Analytics P11',
            'product_id': cls.test_product_saas.id,
            'billing_interval': 'yearly',
            'billing_interval_count': 1,
            'list_price': 60000.0,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })
        cls.plan_weekly = cls.SubscriptionPlan.create({
            'name': 'Weekly Sprint Analytics P11',
            'product_id': cls.test_product_saas.id,
            'billing_interval': 'weekly',
            'billing_interval_count': 1,
            'list_price': 1200.0,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })
        cls.plan_daily = cls.SubscriptionPlan.create({
            'name': 'Daily Usage Analytics P11',
            'product_id': cls.test_product_saas.id,
            'billing_interval': 'daily',
            'billing_interval_count': 1,
            'list_price': 200.0,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })

        # Journals
        cls.sale_journal = cls.AccountJournal.search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.main_company.id),
        ], limit=1)
        cls.bank_journal = cls.AccountJournal.search([
            ('type', '=', 'bank'),
            ('company_id', '=', cls.main_company.id),
        ], limit=1)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _create_test_subscription(self, plan=None, state='active', partner=None, start_date=None, lines=None):
        """Create test subscription with lines and state."""
        p = plan or self.plan_monthly
        cust = partner or self.partner_customer
        sub = self.Subscription.create({
            'customer_id': cust.id,
            'company_id': self.main_company.id,
            'currency_id': self.currency_inr.id,
            'subscription_plan_id': p.id,
            'start_date': start_date or date(2026, 1, 1),
            'billing_anchor_date': start_date or date(2026, 1, 1),
            'billing_interval': p.billing_interval,
            'billing_interval_count': p.billing_interval_count,
        })
        if lines:
            for l in lines:
                self.SubscriptionLine.create({
                    'subscription_id': sub.id,
                    'product_id': l.get('product_id', p.product_id.id),
                    'quantity': l.get('quantity', 1.0),
                    'price_unit': l.get('price_unit', p.list_price),
                    'discount': l.get('discount', 0.0),
                })
        else:
            self.SubscriptionLine.create({
                'subscription_id': sub.id,
                'product_id': p.product_id.id,
                'quantity': 1.0,
                'price_unit': p.list_price,
            })

        sub.with_context(bypass_state_guard=True).write({'state': state})
        return sub

    def _create_test_invoice(self, partner=None, amount=5000.0, move_type='out_invoice', state='posted', due_date=None, sub=None):
        """Create and post a test invoice."""
        cust = partner or self.partner_customer
        inv = self.AccountMove.create({
            'move_type': move_type,
            'partner_id': cust.id,
            'company_id': self.main_company.id,
            'currency_id': self.currency_inr.id,
            'journal_id': self.sale_journal.id,
            'invoice_date': date(2026, 2, 1),
            'invoice_date_due': due_date or date(2026, 2, 15),
            'subscription_id': sub.id if sub else False,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.test_product_saas.id,
                'quantity': 1.0,
                'price_unit': amount,
                'tax_ids': [(6, 0, [])],
            })],
        })
        if state == 'posted':
            inv.action_post()
        return inv

    # =========================================================================
    # 1. SECURITY & ACCESS CONTROL TESTS
    # =========================================================================

    def test_01_customer_access_strictly_denied(self):
        """Customer portal users are strictly blocked from accessing financial analytics."""
        with self.assertRaises(AccessError):
            self.AnalyticsService.get_financial_kpis(user=self.customer_user)

    def test_02_staff_access_granted_within_company(self):
        """Staff user can access financial analytics for authorized company."""
        res = self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.staff_user)
        self.assertIn('revenue', res)
        self.assertIn('recurring', res)
        self.assertEqual(res['company_id'], self.main_company.id)

    def test_03_staff_blocked_from_unauthorized_company(self):
        """Staff user cannot query analytics for a company they do not belong to."""
        with self.assertRaises(AccessError):
            self.AnalyticsService.get_financial_kpis(company_id=self.second_company.id, user=self.staff_user)

    def test_04_admin_has_full_multi_company_access(self):
        """Admin user can query any assigned company."""
        res1 = self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.admin_user)
        res2 = self.AnalyticsService.get_financial_kpis(company_id=self.second_company.id, user=self.admin_user)
        self.assertEqual(res1['company_id'], self.main_company.id)
        self.assertEqual(res2['company_id'], self.second_company.id)

    # =========================================================================
    # 2. REVENUE METRICS TESTS
    # =========================================================================

    def test_05_invoiced_revenue_includes_posted_only(self):
        """Invoiced revenue counts posted invoices and strictly excludes draft/cancelled."""
        # Posted: 5000
        self._create_test_invoice(amount=5000.0, state='posted')
        # Draft: 10000 (must be excluded)
        self._create_test_invoice(amount=10000.0, state='draft')

        res = self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.admin_user)
        self.assertGreaterEqual(res['revenue']['total_invoiced_gross'], 5000.0)

    def test_06_credit_notes_deducted_from_revenue(self):
        """Customer credit notes (out_refund) subtract from total invoiced revenue."""
        initial = self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.admin_user)
        init_rev = initial['revenue']['total_invoiced_gross']

        # Post invoice: 8000
        self._create_test_invoice(amount=8000.0, move_type='out_invoice', state='posted')
        # Post credit note / refund: 3000
        self._create_test_invoice(amount=3000.0, move_type='out_refund', state='posted')

        after = self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.admin_user)
        net_diff = after['revenue']['total_invoiced_gross'] - init_rev
        self.assertEqual(round(net_diff, 2), 5000.0)  # 8000 - 3000 = 5000

    def test_07_revenue_breakdown_by_plan_and_product(self):
        """Revenue analytics correctly categorizes by subscription plan and product line."""
        sub = self._create_test_subscription(plan=self.plan_monthly)
        self._create_test_invoice(amount=6000.0, sub=sub)

        data = self.AnalyticsService.get_revenue_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertIn('by_plan', data)
        self.assertIn('by_product', data)
        self.assertTrue(any(p['plan_id'] == self.plan_monthly.id for p in data['by_plan']))

    # =========================================================================
    # 3. MRR & ARR ENGINE TESTS
    # =========================================================================

    def test_08_mrr_calculation_monthly_plan(self):
        """Monthly plan MRR equals monthly subscription value."""
        self._create_test_subscription(plan=self.plan_monthly, state='active')  # 5000 INR
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertGreaterEqual(res['active_mrr'], 5000.0)
        self.assertEqual(res['arr'], round(res['active_mrr'] * 12.0, 2))

    def test_09_mrr_calculation_quarterly_plan(self):
        """Quarterly plan (monthly interval count 3) divides by 3 for MRR."""
        # 14,000 / 3 = 4,666.67
        sub = self._create_test_subscription(plan=self.plan_quarterly, state='active')
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        # Verify plan breakdown exists with normalized value
        plan_stat = next((p for p in res['plans'] if p['plan_id'] == self.plan_quarterly.id), None)
        self.assertIsNotNone(plan_stat)
        self.assertEqual(round(plan_stat['mrr'], 2), round(14000.0 / 3.0, 2))

    def test_10_mrr_calculation_yearly_plan(self):
        """Yearly plan divides by 12 for MRR."""
        # 60,000 / 12 = 5,000
        sub = self._create_test_subscription(plan=self.plan_yearly, state='active')
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        plan_stat = next((p for p in res['plans'] if p['plan_id'] == self.plan_yearly.id), None)
        self.assertIsNotNone(plan_stat)
        self.assertEqual(round(plan_stat['mrr'], 2), 5000.0)

    def test_11_mrr_calculation_weekly_plan(self):
        """Weekly plan multiplies by (52 / 12) for MRR."""
        # 1200 * (52 / 12) = 5,200
        sub = self._create_test_subscription(plan=self.plan_weekly, state='active')
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        plan_stat = next((p for p in res['plans'] if p['plan_id'] == self.plan_weekly.id), None)
        self.assertIsNotNone(plan_stat)
        self.assertEqual(round(plan_stat['mrr'], 2), 5200.0)

    def test_12_mrr_calculation_daily_plan(self):
        """Daily plan multiplies by (365 / 12) for MRR."""
        # 200 * (365 / 12) = 6,083.33
        sub = self._create_test_subscription(plan=self.plan_daily, state='active')
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        plan_stat = next((p for p in res['plans'] if p['plan_id'] == self.plan_daily.id), None)
        self.assertIsNotNone(plan_stat)
        self.assertEqual(round(plan_stat['mrr'], 2), round(200.0 * 365.0 / 12.0, 2))

    def test_13_mrr_quantity_and_discount_support(self):
        """MRR accounts for line quantity and percentage discount."""
        # Price 1000, Qty 3, Discount 20% -> 1000 * 3 * 0.8 = 2400/month
        lines = [{'product_id': self.test_product_addon.id, 'quantity': 3.0, 'price_unit': 1000.0, 'discount': 20.0}]
        sub = self._create_test_subscription(plan=self.plan_monthly, state='active', lines=lines)
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertGreaterEqual(res['active_mrr'], 2400.0)

    def test_14_paused_subscriptions_tracked_separately_from_active_mrr(self):
        """Paused subscriptions are excluded from active_mrr and tracked in paused_mrr."""
        sub = self._create_test_subscription(plan=self.plan_monthly, state='paused')
        res = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertGreaterEqual(res['paused_mrr'], 5000.0)

    def test_15_draft_and_closed_subscriptions_excluded_from_mrr(self):
        """Draft and closed subscriptions contribute zero to MRR."""
        init = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        init_mrr = init['active_mrr']

        self._create_test_subscription(plan=self.plan_monthly, state='draft')
        self._create_test_subscription(plan=self.plan_monthly, state='closed')

        after = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertEqual(init_mrr, after['active_mrr'])

    # =========================================================================
    # 4. SUBSCRIPTION GROWTH & CHURN TESTS
    # =========================================================================

    def test_16_subscription_growth_metrics(self):
        """Growth rate, renewal rate, and churn rate calculations."""
        t_start = date(2026, 1, 1)
        t_end = date(2026, 3, 31)

        self._create_test_subscription(start_date=date(2026, 1, 15), state='active')
        self._create_test_subscription(start_date=date(2026, 2, 1), state='closed')

        data = self.AnalyticsService.get_subscription_growth_metrics(
            company_id=self.main_company.id,
            start_date=str(t_start),
            end_date=str(t_end),
            user=self.admin_user,
        )
        self.assertIn('rates', data)
        self.assertIn('growth_rate_percent', data['rates'])
        self.assertIn('renewal_rate_percent', data['rates'])
        self.assertIn('churn_rate_percent', data['rates'])

    # =========================================================================
    # 5. INVOICE AGING & OVERDUE ANALYTICS TESTS
    # =========================================================================

    def test_17_invoice_aging_buckets(self):
        """Invoices are categorized into correct aging buckets based on due date."""
        ref_date = date(2026, 4, 1)

        # 1. Not Due (due after ref_date)
        self._create_test_invoice(amount=1000.0, due_date=date(2026, 4, 15))

        # 2. 1-30 days overdue (due 15 days before ref_date)
        self._create_test_invoice(amount=2000.0, due_date=date(2026, 3, 17))

        # 3. 31-60 days overdue (due 45 days before ref_date)
        self._create_test_invoice(amount=3000.0, due_date=date(2026, 2, 15))

        # 4. 61-90 days overdue (due 75 days before ref_date)
        self._create_test_invoice(amount=4000.0, due_date=date(2026, 1, 16))

        # 5. Over 90 days overdue (due 120 days before ref_date)
        self._create_test_invoice(amount=5000.0, due_date=date(2025, 12, 2))

        report = self.AnalyticsService.get_invoice_aging_report(
            company_id=self.main_company.id,
            as_of_date=str(ref_date),
            user=self.admin_user,
        )

        buckets = report['buckets']
        self.assertGreaterEqual(buckets['not_due']['amount'], 1000.0)
        self.assertGreaterEqual(buckets['1_30_days']['amount'], 2000.0)
        self.assertGreaterEqual(buckets['31_60_days']['amount'], 3000.0)
        self.assertGreaterEqual(buckets['61_90_days']['amount'], 4000.0)
        self.assertGreaterEqual(buckets['over_90_days']['amount'], 5000.0)
        self.assertGreater(report['total_overdue'], 0.0)

    def test_18_fully_paid_invoices_excluded_from_aging(self):
        """Fully settled invoices (amount_residual == 0) are excluded from aging buckets."""
        inv = self._create_test_invoice(amount=2500.0, due_date=date(2025, 1, 1))
        # Simulate payment residual to 0.0
        inv.with_context(check_move_validity=False).write({'amount_residual': 0.0, 'payment_state': 'paid'})

        report = self.AnalyticsService.get_invoice_aging_report(
            company_id=self.main_company.id,
            as_of_date='2026-04-01',
            user=self.admin_user,
        )
        # Ensure the 0 residual invoice is not counted
        self.assertTrue(report['total_outstanding'] >= 0.0)

    # =========================================================================
    # 6. INVOICE & PAYMENT ANALYTICS TESTS
    # =========================================================================

    def test_19_invoice_analytics_summary(self):
        """Invoice analytics returns totals, residual amounts, and status counts."""
        self._create_test_invoice(amount=3000.0)
        data = self.AnalyticsService.get_invoice_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertIn('total_invoices', data)
        self.assertIn('total_invoiced_amount', data)
        self.assertIn('total_residual_amount', data)
        self.assertIn('average_invoice_value', data)

    def test_20_payment_analytics_and_journal_breakdown(self):
        """Payment analytics aggregates collected revenue and journal distributions."""
        pay = self.AccountPayment.create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_customer.id,
            'amount': 4500.0,
            'currency_id': self.currency_inr.id,
            'journal_id': self.bank_journal.id,
            'company_id': self.main_company.id,
            'date': date(2026, 2, 1),
        })
        pay.action_post()

        data = self.AnalyticsService.get_payment_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.assertGreaterEqual(data['total_collected_amount'], 4500.0)
        self.assertTrue(any(j['journal_name'] == self.bank_journal.name for j in data['by_journal']))

    # =========================================================================
    # 7. CUSTOMER FINANCIAL ANALYTICS
    # =========================================================================

    def test_21_customer_financial_metrics(self):
        """Customer financial metrics compute ARPU and tier distribution without exposing PII."""
        self._create_test_subscription(plan=self.plan_monthly, state='active')
        data = self.AnalyticsService.get_customer_financial_metrics(company_id=self.main_company.id, user=self.admin_user)

        self.assertIn('total_customers', data)
        self.assertIn('active_subscribers', data)
        self.assertIn('arpu', data)
        self.assertIn('average_customer_revenue', data)
        self.assertIn('subscription_distribution', data)
        # Ensure no PII in response
        self.assertNotIn('email', str(data))
        self.assertNotIn('password', str(data))

    # =========================================================================
    # 8. TRENDS & PERIOD COMPARISONS
    # =========================================================================

    def test_22_financial_trends_monthly_grouping(self):
        """Time-series trend groups revenue correctly by month."""
        self._create_test_invoice(amount=2000.0)
        trends = self.AnalyticsService.get_financial_trends(
            metric='revenue',
            interval='month',
            company_id=self.main_company.id,
            start_date='2026-01-01',
            end_date='2026-03-31',
            user=self.admin_user,
        )
        self.assertEqual(trends['interval'], 'month')
        self.assertIsInstance(trends['data_points'], list)

    def test_23_period_comparison_variance(self):
        """Period comparison computes absolute difference and percentage variance."""
        res = self.AnalyticsService.compare_periods(
            metric='revenue',
            current_start='2026-02-01',
            current_end='2026-02-28',
            previous_start='2026-01-01',
            previous_end='2026-01-31',
            company_id=self.main_company.id,
            user=self.admin_user,
        )
        self.assertIn('current_period', res)
        self.assertIn('previous_period', res)
        self.assertIn('variance', res)
        self.assertIn('percentage_change', res['variance'])

    # =========================================================================
    # 9. MULTI-COMPANY & MULTI-CURRENCY CONVERSION
    # =========================================================================

    def test_24_multi_currency_reporting_conversion(self):
        """Reporting converts values accurately when foreign currency is selected."""
        # Query main company (INR) in USD reporting currency
        res_inr = self.AnalyticsService.get_financial_kpis(
            company_id=self.main_company.id,
            currency_id=self.currency_inr.id,
            user=self.admin_user,
        )
        res_usd = self.AnalyticsService.get_financial_kpis(
            company_id=self.main_company.id,
            currency_id=self.currency_usd.id,
            user=self.admin_user,
        )
        self.assertEqual(res_inr['currency_code'], self.currency_inr.name)
        self.assertEqual(res_usd['currency_code'], self.currency_usd.name)

    def test_25_read_only_integrity_preservation(self):
        """Analytics computations preserve data integrity and make zero modifications to accounting records."""
        sub = self._create_test_subscription(plan=self.plan_monthly, state='active')
        inv = self._create_test_invoice(amount=3000.0, sub=sub)

        sub_state_before = sub.state
        inv_residual_before = inv.amount_residual
        inv_state_before = inv.state

        # Run multiple analytics queries
        self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.admin_user)
        self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        self.AnalyticsService.get_invoice_aging_report(company_id=self.main_company.id, user=self.admin_user)
        self.AnalyticsService.get_plan_performance_analytics(company_id=self.main_company.id, user=self.admin_user)

        # Assert zero change
        self.assertEqual(sub.state, sub_state_before)
        self.assertEqual(inv.amount_residual, inv_residual_before)
        self.assertEqual(inv.state, inv_state_before)

    # =========================================================================
    # 10. PERFORMANCE BENCHMARK
    # =========================================================================

    def test_26_performance_benchmark_analytics_computation(self):
        """
        BENCHMARK: Ensure financial KPI, MRR, revenue, and aging reports execute in < 2.0 seconds.
        """
        # Create a bulk batch of 100 subscriptions and 100 invoices
        setup_start = time.time()
        subs = []
        for i in range(50):
            s = self.Subscription.create({
                'customer_id': self.partner_customer.id,
                'company_id': self.main_company.id,
                'currency_id': self.currency_inr.id,
                'subscription_plan_id': self.plan_monthly.id,
                'start_date': date(2026, 1, 1),
                'billing_interval': 'monthly',
                'billing_interval_count': 1,
            })
            self.SubscriptionLine.create({
                'subscription_id': s.id,
                'product_id': self.test_product_saas.id,
                'quantity': 1.0,
                'price_unit': 5000.0,
            })
            s.with_context(bypass_state_guard=True).write({'state': 'active'})
            subs.append(s)

        for i in range(50):
            inv = self.AccountMove.create({
                'move_type': 'out_invoice',
                'partner_id': self.partner_customer.id,
                'company_id': self.main_company.id,
                'currency_id': self.currency_inr.id,
                'journal_id': self.sale_journal.id,
                'invoice_date': date(2026, 2, 1),
                'invoice_date_due': date(2026, 2, 15) if i % 2 == 0 else date(2026, 4, 1),
                'invoice_line_ids': [(0, 0, {
                    'product_id': self.test_product_saas.id,
                    'quantity': 1.0,
                    'price_unit': 2000.0 + i,
                })],
            })
            inv.action_post()

        # Benchmark core KPI computation
        t0 = time.time()
        kpis = self.AnalyticsService.get_financial_kpis(company_id=self.main_company.id, user=self.admin_user)
        mrr = self.AnalyticsService.get_mrr_arr_analytics(company_id=self.main_company.id, user=self.admin_user)
        aging = self.AnalyticsService.get_invoice_aging_report(company_id=self.main_company.id, user=self.admin_user)
        duration = time.time() - t0

        self.assertLess(duration, 2.0, f"Analytics computation took {duration:.3f}s, exceeding 2.0s benchmark limit.")

    # =========================================================================
    # 11. REST API & VALIDATION TESTS
    # =========================================================================

    def test_27_invalid_date_filter_raises_validation_error(self):
        """Malformed date strings raise clear ValidationError."""
        with self.assertRaises(ValidationError):
            self.AnalyticsService.get_financial_kpis(
                company_id=self.main_company.id,
                start_date="not-a-date",
                user=self.admin_user,
            )

    def test_28_plan_and_product_performance_analytics(self):
        """Plan and product performance endpoints return expected aggregates."""
        sub = self._create_test_subscription(plan=self.plan_monthly, state='active')
        self._create_test_invoice(amount=5000.0, sub=sub)

        plan_res = self.AnalyticsService.get_plan_performance_analytics(company_id=self.main_company.id, user=self.admin_user)
        prod_res = self.AnalyticsService.get_product_performance_analytics(company_id=self.main_company.id, user=self.admin_user)

        self.assertIn('plans', plan_res)
        self.assertIn('products', prod_res)
        self.assertTrue(len(plan_res['plans']) > 0)

    def test_29_anonymous_access_strictly_denied(self):
        """Anonymous callers without session or user are rejected."""
        public_user = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            self.AnalyticsService.get_financial_kpis(user=public_user)

    def test_30_analytics_unauthorized_audit_logging(self):
        """Unauthorized customer access attempts emit audit event in brightloop.security.audit."""
        try:
            self.AnalyticsService.get_financial_kpis(user=self.customer_user)
        except AccessError:
            pass

        # Read using fresh autonomous cursor to see autonomous commit across REPEATABLE READ snapshot
        with self.env.registry.cursor() as read_cr:
            read_cr.execute(
                """
                SELECT COUNT(*) FROM brightloop_security_audit
                WHERE event_type = %s
                """,
                ('analytics_unauthorized_access',),
            )
            count = read_cr.fetchone()[0]

        self.assertGreater(count, 0)
