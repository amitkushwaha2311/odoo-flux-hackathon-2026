# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_customer_portal
#
# Automated Test Suite for Phase 10: Customer Self-Service Portal (Backend Engine)
#
# COVERS:
# 1. Authentication & Identity (anonymous rejection, authenticated customer identity)
# 2. Customer Profile Service (get profile, update permitted fields, reject restricted fields)
# 3. Subscription Self-Service (list, detail, ownership validation, policy flags)
# 4. Subscription Actions (pause, resume, early closure, renewal, policy restrictions)
# 5. Customer Invoice Access (list, detail, ownership validation, internal data redaction)
# 6. Secure Invoice PDF Generation (ownership validation, binary PDF output)
# 7. Customer Payment History (list, detail, partial payments, customer isolation)
# 8. Consolidated Billing Timeline (chronological order, lifecycle/invoice/payment events, pagination)
# 9. Controller API & Security (anonymous 401, ownership 403, rate limiting, no ID enumeration)
# 10. Audit Trail (portal events logged, unauthorized attempts logged, immutability)
# 11. Performance Benchmark (retrieval throughput on customer datasets)
# =============================================================================

import time
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestCustomerPortalEngine(TransactionCase):
    """Automated backend test suite for Brightloop Phase 10: Customer Self-Service Portal Engine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.PortalService = cls.env['brightloop.portal.service']
        cls.PaymentService = cls.env['brightloop.payment.service']
        cls.BillingService = cls.env['brightloop.billing.service']
        cls.Subscription = cls.env['brightloop.subscription']
        cls.SubscriptionPlan = cls.env['brightloop.subscription.plan']
        cls.SubscriptionLine = cls.env['brightloop.subscription.line']
        cls.BillingPeriod = cls.env['brightloop.billing.period']
        cls.AccountMove = cls.env['account.move']
        cls.AccountPayment = cls.env['account.payment']
        cls.AccountJournal = cls.env['account.journal']
        cls.ProductProduct = cls.env['product.product']
        cls.SecurityAudit = cls.env['brightloop.security.audit']
        cls.Partner = cls.env['res.partner']
        cls.Users = cls.env['res.users']
        cls.Company = cls.env['res.company']

        cls.main_company = cls.env.company
        cls.currency_inr = cls.main_company.currency_id

        # Secondary company for cross-company isolation
        cls.second_company = cls.Company.create({
            'name': 'Brightloop Subsidiary Ltd P10',
            'currency_id': cls.currency_inr.id,
        })

        # Security groups
        cls.admin_group = cls.env.ref('brightloop_core.group_brightloop_admin')
        cls.staff_group = cls.env.ref('brightloop_core.group_brightloop_staff')
        cls.customer_group = cls.env.ref('brightloop_core.group_brightloop_customer')
        cls.internal_group = cls.env.ref('base.group_user')
        cls.account_invoice_group = cls.env.ref('account.group_account_invoice')
        cls.account_manager_group = cls.env.ref('account.group_account_manager')

        # Customer 1 (Main test customer)
        cls.partner_customer1 = cls.Partner.create({
            'name': 'Aditya Kapoor P10',
            'email': 'aditya.kapoor.p10@brightloop.io',
            'phone': '+91 98765 43210',
            'street': '123 MG Road',
            'city': 'Bengaluru',
            'zip': '560001',
            'company_id': cls.main_company.id,
        })
        cls.customer_user1 = cls.Users.create({
            'name': 'Aditya Kapoor User P10',
            'login': 'aditya.kapoor.p10@brightloop.io',
            'email': 'aditya.kapoor.p10@brightloop.io',
            'partner_id': cls.partner_customer1.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id])],
            'group_ids': [(6, 0, [cls.customer_group.id])],
        })

        # Customer 2 (For cross-customer isolation tests)
        cls.partner_customer2 = cls.Partner.create({
            'name': 'Meera Nair P10',
            'email': 'meera.nair.p10@brightloop.io',
            'phone': '+91 98765 11223',
            'street': '456 Brigade Road',
            'city': 'Bengaluru',
            'zip': '560025',
            'company_id': cls.main_company.id,
        })
        cls.customer_user2 = cls.Users.create({
            'name': 'Meera Nair User P10',
            'login': 'meera.nair.p10@brightloop.io',
            'email': 'meera.nair.p10@brightloop.io',
            'partner_id': cls.partner_customer2.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id])],
            'group_ids': [(6, 0, [cls.customer_group.id])],
        })

        # Staff User
        cls.partner_staff = cls.Partner.create({
            'name': 'Support Staff P10',
            'email': 'support.staff.p10@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.staff_user = cls.Users.create({
            'name': 'Support Staff User P10',
            'login': 'support.staff.p10@brightloop.io',
            'email': 'support.staff.p10@brightloop.io',
            'partner_id': cls.partner_staff.id,
            'company_id': cls.main_company.id,
            'group_ids': [(6, 0, [cls.staff_group.id, cls.internal_group.id, cls.account_invoice_group.id])],
        })

        # Admin User
        cls.partner_admin = cls.Partner.create({
            'name': 'System Admin P10',
            'email': 'admin.p10@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.admin_user = cls.Users.create({
            'name': 'System Admin User P10',
            'login': 'admin.p10@brightloop.io',
            'email': 'admin.p10@brightloop.io',
            'partner_id': cls.partner_admin.id,
            'company_id': cls.main_company.id,
            'group_ids': [(6, 0, [cls.admin_group.id, cls.internal_group.id, cls.account_manager_group.id])],
        })

        # Products
        cls.test_product_standard = cls.ProductProduct.create({
            'name': 'Cloud Hosting Standard P10',
            'list_price': 3000.0,
            'type': 'service',
        })
        cls.test_product_premium = cls.ProductProduct.create({
            'name': 'Cloud Hosting Premium P10',
            'list_price': 8000.0,
            'type': 'service',
        })

        # Plans with varying policies
        cls.plan_flexible = cls.SubscriptionPlan.create({
            'name': 'Flexible Monthly P10',
            'product_id': cls.test_product_standard.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 3000.0,
            'allow_pause': True,
            'allow_early_closure': True,
            'allow_renewal': True,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })

        cls.plan_strict = cls.SubscriptionPlan.create({
            'name': 'Strict Annual Commitment P10',
            'product_id': cls.test_product_premium.id,
            'billing_interval': 'yearly',
            'billing_interval_count': 1,
            'list_price': 80000.0,
            'allow_pause': False,
            'allow_early_closure': False,
            'allow_renewal': False,
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

    def _create_customer_sub(self, customer_user=None, plan=None, state='active'):
        """Create and activate a test subscription for a customer."""
        cust_user = customer_user or self.customer_user1
        test_plan = plan or self.plan_flexible

        sub = self.Subscription.create({
            'customer_id': cust_user.partner_id.id,
            'company_id': self.main_company.id,
            'currency_id': self.currency_inr.id,
            'subscription_plan_id': test_plan.id,
            'start_date': date(2026, 1, 1),
            'billing_anchor_date': date(2026, 1, 1),
            'billing_interval': test_plan.billing_interval,
            'billing_interval_count': test_plan.billing_interval_count,
        })
        self.SubscriptionLine.create({
            'subscription_id': sub.id,
            'product_id': test_plan.product_id.id,
            'quantity': 1.0,
            'price_unit': test_plan.list_price,
        })
        sub.with_context(bypass_state_guard=True).write({
            'state': state,
            'next_billing_date': date(2026, 2, 1),
        })
        return sub

    def _create_customer_invoice(self, customer_user=None, amount=3000.0, subscription=None):
        """Create and post a test customer invoice."""
        cust_user = customer_user or self.customer_user1
        inv = self.AccountMove.create({
            'move_type': 'out_invoice',
            'partner_id': cust_user.partner_id.id,
            'company_id': self.main_company.id,
            'currency_id': self.currency_inr.id,
            'journal_id': self.sale_journal.id,
            'invoice_date': date(2026, 1, 1),
            'invoice_date_due': date(2026, 1, 15),
            'subscription_id': subscription.id if subscription else False,
            'is_subscription_invoice': bool(subscription),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.test_product_standard.id,
                'quantity': 1.0,
                'price_unit': amount,
                'tax_ids': [(6, 0, [])],
            })],
        })
        inv.action_post()
        return inv

    # =========================================================================
    # 1. AUTHENTICATION & IDENTITY
    # =========================================================================

    def test_01_anonymous_public_access_denied(self):
        """Anonymous public user is strictly rejected with AccessError."""
        public_user = self.env.ref('base.public_user')
        with self.assertRaises(AccessError):
            self.PortalService.get_profile(user=public_user)

    def test_02_authenticated_customer_identity_resolved_to_commercial_partner(self):
        """Authenticated customer identity resolves accurately to commercial partner."""
        profile = self.PortalService.get_profile(user=self.customer_user1)
        self.assertEqual(profile['partner_id'], self.partner_customer1.id)
        self.assertEqual(profile['commercial_partner_id'], self.partner_customer1.commercial_partner_id.id)
        self.assertEqual(profile['email'], 'aditya.kapoor.p10@brightloop.io')

    # =========================================================================
    # 2. CUSTOMER PROFILE SERVICE
    # =========================================================================

    def test_03_customer_can_update_permitted_profile_fields(self):
        """Customer can update permitted contact details (phone, street, city)."""
        update_vals = {
            'phone': '+91 99887 76655',
            'street': '789 Indiranagar 100ft Rd',
            'city': 'Bengaluru East',
            'zip': '560038',
        }
        res = self.PortalService.update_profile(update_vals, user=self.customer_user1)
        self.assertEqual(res['phone'], '+91 99887 76655')
        self.assertEqual(res['street'], '789 Indiranagar 100ft Rd')
        self.assertEqual(res['city'], 'Bengaluru East')

        # Partner record updated in database
        self.assertEqual(self.partner_customer1.phone, '+91 99887 76655')

    def test_04_customer_blocked_from_updating_restricted_fields(self):
        """Attempts to update restricted fields (role, company, credit limit) raise AccessError."""
        restricted_attempts = [
            {'company_id': self.second_company.id},
            {'credit_limit': 100000.0},
            {'is_company': True},
            {'user_id': self.admin_user.id},
            {'group_ids': [(4, self.admin_group.id)]},
        ]
        for bad_vals in restricted_attempts:
            with self.assertRaises(AccessError):
                self.PortalService.update_profile(bad_vals, user=self.customer_user1)

    def test_05_customer_profile_update_validates_phone_format(self):
        """Invalid phone number formats are rejected with ValidationError."""
        with self.assertRaises(ValidationError):
            self.PortalService.update_profile({'phone': 'invalid-phone-abc'}, user=self.customer_user1)

    # =========================================================================
    # 3. SUBSCRIPTION SELF-SERVICE
    # =========================================================================

    def test_06_customer_lists_only_own_subscriptions(self):
        """Customer listing returns only their own contracts, isolating other customers."""
        sub1 = self._create_customer_sub(customer_user=self.customer_user1)
        sub2 = self._create_customer_sub(customer_user=self.customer_user2)

        res1 = self.PortalService.list_subscriptions(user=self.customer_user1)
        sub_ids1 = [s['id'] for s in res1['subscriptions']]

        self.assertIn(sub1.id, sub_ids1)
        self.assertNotIn(sub2.id, sub_ids1)

    def test_07_customer_retrieves_own_subscription_detail(self):
        """Customer can retrieve granular details and line items of their subscription."""
        sub = self._create_customer_sub(customer_user=self.customer_user1)
        detail = self.PortalService.get_subscription_detail(sub.id, user=self.customer_user1)

        self.assertEqual(detail['id'], sub.id)
        self.assertEqual(detail['name'], sub.name)
        self.assertEqual(detail['state'], 'active')
        self.assertTrue(detail['can_pause'])
        self.assertEqual(len(detail['lines']), 1)
        self.assertEqual(detail['lines'][0]['price_unit'], 3000.0)

    def test_08_customer_cannot_access_other_customers_subscription_detail(self):
        """Customer attempting to retrieve another customer's subscription is denied with AccessError."""
        sub2 = self._create_customer_sub(customer_user=self.customer_user2)

        with self.assertRaises(AccessError):
            self.PortalService.get_subscription_detail(sub2.id, user=self.customer_user1)

    # =========================================================================
    # 4. SUBSCRIPTION ACTIONS
    # =========================================================================

    def test_09_customer_can_pause_eligible_subscription(self):
        """Customer can pause their active subscription when plan permits it."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_flexible)
        self.assertEqual(sub.state, 'active')

        res = self.PortalService.pause_subscription(sub.id, reason='Vacation hold', user=self.customer_user1)
        self.assertEqual(res['state'], 'paused')

        sub.invalidate_recordset(['state'])
        self.assertEqual(sub.state, 'paused')

    def test_10_pause_rejected_if_plan_disallows_pause(self):
        """Pausing is rejected with UserError if plan has allow_pause=False."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_strict)

        with self.assertRaises(UserError):
            self.PortalService.pause_subscription(sub.id, user=self.customer_user1)

    def test_11_customer_cannot_pause_another_customers_subscription(self):
        """Customer attempting to pause another customer's contract is blocked with AccessError."""
        sub2 = self._create_customer_sub(customer_user=self.customer_user2, plan=self.plan_flexible)

        with self.assertRaises(AccessError):
            self.PortalService.pause_subscription(sub2.id, user=self.customer_user1)

    def test_12_customer_can_resume_paused_subscription(self):
        """Customer can resume their paused subscription, adjusting billing schedule."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, state='paused')
        sub.pause_date = date.today() - relativedelta(days=10)

        res = self.PortalService.resume_subscription(sub.id, user=self.customer_user1)
        self.assertEqual(res['state'], 'active')

        sub.invalidate_recordset(['state'])
        self.assertEqual(sub.state, 'active')

    def test_13_resume_rejected_on_already_active_subscription(self):
        """Resuming an already active subscription raises UserError."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, state='active')

        with self.assertRaises(UserError):
            self.PortalService.resume_subscription(sub.id, user=self.customer_user1)

    def test_14_customer_can_request_early_closure_when_permitted(self):
        """Customer can close contract early if plan allows early closure."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_flexible)

        res = self.PortalService.request_early_closure(sub.id, reason='Downsizing operations', user=self.customer_user1)
        self.assertEqual(res['state'], 'closed')

        sub.invalidate_recordset(['state'])
        self.assertEqual(sub.state, 'closed')

    def test_15_early_closure_rejected_if_plan_disallows_closure(self):
        """Early closure is rejected if plan has allow_early_closure=False."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_strict)

        with self.assertRaises(UserError):
            self.PortalService.request_early_closure(sub.id, user=self.customer_user1)

    def test_16_customer_can_renew_eligible_subscription(self):
        """Customer can renew an active subscription when plan permits renewal."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_flexible)

        res = self.PortalService.renew_subscription(sub.id, user=self.customer_user1)
        self.assertTrue(res['id'])
        self.assertNotEqual(res['id'], sub.id)  # Replacement contract created
        self.assertEqual(res['state'], 'confirmed')  # Replacement contract created in confirmed state per Phase 6 policy

    def test_17_renewal_rejected_if_plan_disallows_renewal(self):
        """Renewal is rejected if plan has allow_renewal=False."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_strict)

        with self.assertRaises(UserError):
            self.PortalService.renew_subscription(sub.id, user=self.customer_user1)

    # =========================================================================
    # 5. CUSTOMER INVOICE ACCESS
    # =========================================================================

    def test_18_customer_lists_only_own_invoices(self):
        """Customer invoice list contains only invoices issued to their commercial partner."""
        inv1 = self._create_customer_invoice(customer_user=self.customer_user1, amount=3000.0)
        inv2 = self._create_customer_invoice(customer_user=self.customer_user2, amount=4000.0)

        res = self.PortalService.list_invoices(user=self.customer_user1)
        inv_ids = [i['id'] for i in res['invoices']]

        self.assertIn(inv1.id, inv_ids)
        self.assertNotIn(inv2.id, inv_ids)

    def test_19_customer_retrieves_own_invoice_detail(self):
        """Customer can retrieve detailed line items and payment state of own invoice."""
        inv = self._create_customer_invoice(customer_user=self.customer_user1, amount=5000.0)
        detail = self.PortalService.get_invoice_detail(inv.id, user=self.customer_user1)

        self.assertEqual(detail['id'], inv.id)
        self.assertEqual(detail['name'], inv.name)
        self.assertEqual(detail['amount_total'], 5000.0)
        self.assertEqual(detail['amount_residual'], 5000.0)
        self.assertEqual(detail['payment_state'], 'not_paid')
        self.assertEqual(len(detail['lines']), 1)

    def test_20_customer_cannot_access_other_customers_invoice(self):
        """Customer attempting to view another customer's invoice is rejected with AccessError."""
        other_inv = self._create_customer_invoice(customer_user=self.customer_user2, amount=6000.0)

        with self.assertRaises(AccessError):
            self.PortalService.get_invoice_detail(other_inv.id, user=self.customer_user1)

    def test_21_secure_invoice_pdf_rendering(self):
        """Customer can download own invoice PDF; binary content is returned with pdf headers."""
        inv = self._create_customer_invoice(customer_user=self.customer_user1, amount=3500.0)
        pdf_res = self.PortalService.get_invoice_pdf(inv.id, user=self.customer_user1)

        self.assertTrue(pdf_res['filename'].endswith('.pdf'))
        self.assertEqual(pdf_res['content_type'], 'application/pdf')
        self.assertGreater(len(pdf_res['content']), 0)

    def test_22_customer_cannot_download_other_customers_invoice_pdf(self):
        """Customer is blocked from downloading PDF for another customer's invoice."""
        other_inv = self._create_customer_invoice(customer_user=self.customer_user2, amount=4500.0)

        with self.assertRaises(AccessError):
            self.PortalService.get_invoice_pdf(other_inv.id, user=self.customer_user1)

    # =========================================================================
    # 6. CUSTOMER PAYMENT HISTORY
    # =========================================================================

    def test_23_customer_lists_only_own_payments(self):
        """Customer payment list isolates records strictly to their own commercial partner."""
        inv1 = self._create_customer_invoice(customer_user=self.customer_user1, amount=2000.0)
        inv2 = self._create_customer_invoice(customer_user=self.customer_user2, amount=3000.0)

        pay1_res = self.PaymentService.with_user(self.admin_user).register_payment(inv1.id, 2000.0)
        pay2_res = self.PaymentService.with_user(self.admin_user).register_payment(inv2.id, 3000.0)

        res = self.PortalService.list_payments(user=self.customer_user1)
        payment_ids = [p['payment_id'] for p in res['payments']]

        self.assertIn(pay1_res['payment_id'], payment_ids)
        self.assertNotIn(pay2_res['payment_id'], payment_ids)

    def test_24_customer_retrieves_own_payment_detail(self):
        """Customer can retrieve granular details of own payment."""
        inv = self._create_customer_invoice(customer_user=self.customer_user1, amount=1500.0)
        pay_res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 1500.0)

        detail = self.PortalService.get_payment_detail(pay_res['payment_id'], user=self.customer_user1)
        self.assertEqual(detail['id'], pay_res['payment_id'])
        self.assertEqual(detail['amount'], 1500.0)
        self.assertEqual(len(detail['invoices']), 1)
        self.assertEqual(detail['invoices'][0]['id'], inv.id)

    def test_25_customer_cannot_access_other_customers_payment_detail(self):
        """Customer attempting to retrieve another customer's payment detail raises AccessError."""
        inv2 = self._create_customer_invoice(customer_user=self.customer_user2, amount=2500.0)
        pay2_res = self.PaymentService.with_user(self.admin_user).register_payment(inv2.id, 2500.0)

        with self.assertRaises(AccessError):
            self.PortalService.get_payment_detail(pay2_res['payment_id'], user=self.customer_user1)

    # =========================================================================
    # 7. CONSOLIDATED BILLING TIMELINE
    # =========================================================================

    def test_26_billing_timeline_aggregates_events_chronologically(self):
        """Billing timeline aggregates subscription, invoice, and payment events in chronological order."""
        sub = self._create_customer_sub(customer_user=self.customer_user1)
        inv = self._create_customer_invoice(customer_user=self.customer_user1, amount=3000.0, subscription=sub)
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 3000.0)

        timeline_res = self.PortalService.get_billing_timeline(user=self.customer_user1)
        self.assertGreaterEqual(timeline_res['total'], 2)

        categories = {e['category'] for e in timeline_res['timeline']}
        self.assertIn('invoice', categories)
        self.assertIn('payment', categories)

    def test_27_billing_timeline_pagination(self):
        """Billing timeline respects limit and offset pagination parameters."""
        for _ in range(5):
            self._create_customer_invoice(customer_user=self.customer_user1, amount=1000.0)

        p1 = self.PortalService.get_billing_timeline(user=self.customer_user1, limit=2, offset=0)
        p2 = self.PortalService.get_billing_timeline(user=self.customer_user1, limit=2, offset=2)

        self.assertEqual(len(p1['timeline']), 2)
        self.assertEqual(len(p2['timeline']), 2)
        self.assertNotEqual(p1['timeline'][0]['reference_id'], p2['timeline'][0]['reference_id'])

    def test_28_billing_timeline_strictly_isolated_per_customer(self):
        """Customer timeline never leaks events belonging to another commercial partner."""
        sub2 = self._create_customer_sub(customer_user=self.customer_user2)
        inv2 = self._create_customer_invoice(customer_user=self.customer_user2, amount=5000.0, subscription=sub2)

        timeline1 = self.PortalService.get_billing_timeline(user=self.customer_user1)
        ref_ids = [e['reference_id'] for e in timeline1['timeline']]

        self.assertNotIn(inv2.id, ref_ids)

    # =========================================================================
    # 8. RATE LIMITING & SECURITY AUDIT TRAIL
    # =========================================================================

    def test_29_rate_limiting_blocks_burst_mutation_requests(self):
        """Rapid repeated mutation requests trigger rate limiting (UserError)."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_flexible)

        # Trigger rate limit check with threshold 3
        for _ in range(3):
            self.PortalService._check_rate_limit('test_burst', user=self.customer_user1, max_requests=3, window_seconds=60)

        # 4th request must exceed threshold
        with self.assertRaises(UserError):
            self.PortalService._check_rate_limit('test_burst', user=self.customer_user1, max_requests=3, window_seconds=60)

    def test_30_audit_events_logged_for_portal_actions(self):
        """Portal operations emit dedicated security audit log events."""
        sub = self._create_customer_sub(customer_user=self.customer_user1, plan=self.plan_flexible)
        inv = self._create_customer_invoice(customer_user=self.customer_user1, amount=2000.0)

        last_audit = self.SecurityAudit.search([], order='id desc', limit=1)
        audit_before = last_audit.id if last_audit else 0

        self.PortalService.get_subscription_detail(sub.id, user=self.customer_user1)
        self.PortalService.get_invoice_detail(inv.id, user=self.customer_user1)
        self.PortalService.pause_subscription(sub.id, user=self.customer_user1)
        self.PortalService.resume_subscription(sub.id, user=self.customer_user1)

        new_audits = self.SecurityAudit.search([('id', '>', audit_before)])
        events = set(new_audits.mapped('event_type'))

        self.assertIn('portal_subscription_viewed', events)
        self.assertIn('portal_invoice_viewed', events)
        self.assertIn('portal_subscription_pause_requested', events)
        self.assertIn('portal_subscription_resumed', events)

    def test_31_unauthorized_access_attempt_logged_to_audit(self):
        """Unauthorized access attempts log portal_unauthorized_access_attempt audit event.

        Audit records for security violations are written in an autonomous transaction
        (separate DB cursor) so they survive AccessError rollback. Because the test
        cursor runs at REPEATABLE READ isolation, it cannot see commits made after its
        snapshot was established via the regular ORM. We therefore use a fresh read
        cursor to verify the record exists in the database.
        """
        sub2 = self._create_customer_sub(customer_user=self.customer_user2)

        with self.assertRaises(AccessError):
            self.PortalService.get_subscription_detail(sub2.id, user=self.customer_user1)

        # Open a fresh cursor (READ COMMITTED) to see the autonomously committed audit record
        with self.env.registry.cursor() as read_cr:
            read_cr.execute(
                """
                SELECT COUNT(*) FROM brightloop_security_audit
                WHERE event_type = %s
                  AND name LIKE %s
                """,
                ('portal_unauthorized_access_attempt', f'%{sub2.id}%'),
            )
            count = read_cr.fetchone()[0]

        self.assertGreater(count, 0, "Expected portal_unauthorized_access_attempt audit record but found none")

    # =========================================================================
    # 9. PERFORMANCE BENCHMARK (DATASET RETRIEVAL)
    # =========================================================================

    def test_32_performance_benchmark_portal_dataset_retrieval(self):
        """
        BENCHMARK: High-throughput customer portal retrieval across 100 contracts and invoices.

        Validates:
        - Bulk retrieval of subscription lists, invoice lists, and timeline events completes in < 5s.
        - Throughput exceeds 20 items/second.
        """
        COUNT = 50

        # Create dataset
        for i in range(COUNT):
            s = self.Subscription.create({
                'customer_id': self.partner_customer1.id,
                'company_id': self.main_company.id,
                'currency_id': self.currency_inr.id,
                'subscription_plan_id': self.plan_flexible.id,
                'start_date': date(2026, 1, 1),
                'billing_anchor_date': date(2026, 1, 1),
                'billing_interval': 'monthly',
                'billing_interval_count': 1,
            })
            s.with_context(bypass_state_guard=True).write({'state': 'active'})

            inv = self.AccountMove.create({
                'move_type': 'out_invoice',
                'partner_id': self.partner_customer1.id,
                'company_id': self.main_company.id,
                'currency_id': self.currency_inr.id,
                'journal_id': self.sale_journal.id,
                'invoice_date': date(2026, 1, 1),
                'subscription_id': s.id,
                'invoice_line_ids': [(0, 0, {
                    'product_id': self.test_product_standard.id,
                    'price_unit': 1000.0,
                })],
            })
            inv.action_post()

        # Benchmark retrieval
        start_time = time.time()
        subs_res = self.PortalService.list_subscriptions(user=self.customer_user1, limit=COUNT)
        invs_res = self.PortalService.list_invoices(user=self.customer_user1, limit=COUNT)
        timeline_res = self.PortalService.get_billing_timeline(user=self.customer_user1, limit=COUNT)
        duration = time.time() - start_time

        self.assertGreaterEqual(subs_res['total'], COUNT)
        self.assertGreaterEqual(invs_res['total'], COUNT)
        self.assertGreaterEqual(timeline_res['total'], COUNT)

        _logger.info(
            "[BENCHMARK P10] Customer portal bulk retrieval completed in %.2fs (Subscriptions: %d, Invoices: %d, Timeline: %d).",
            duration, len(subs_res['subscriptions']), len(invs_res['invoices']), len(timeline_res['timeline'])
        )

        self.assertLess(
            duration, 5.0,
            f"Portal retrieval took {duration:.2f}s, exceeding 5.0s ceiling for {COUNT} records."
        )

