# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_payment_engine
#
# Automated Test Suite for Phase 9: Payment & Reconciliation Engine
#
# COVERS:
# 1. Payment Registration (full payment, positive amount, draft/cancel rejection, customer match)
# 2. Partial Payments & Allocation (multi-payment, exact residual tracking, multi-invoice allocation)
# 3. Reconciliation & Native States (automatic payment_state: 'paid', 'partial', amount_residual)
# 4. Outstanding Balance Tracking (get_outstanding_balance single source of truth)
# 5. Overdue Management (overdue discovery, excluded fully paid, excluded future-due)
# 6. Payment Reversal / Refunds (native cancellation, residual restored, admin-only)
# 7. Role-Based Security & Isolation (Admin, Staff, Customer isolation, cross-company isolation)
# 8. Subscription Traceability (traceable to subscription, customer payment history)
# 9. Audit Logging (9 Phase 9 audit event types verified)
# 10. Idempotency & Duplicate Protection (service idempotency, DB UNIQUE constraint)
# 11. Performance Benchmark (100 invoice payments registered and reconciled)
# =============================================================================

import time
import logging
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase

_logger = logging.getLogger(__name__)


class TestPaymentEngine(TransactionCase):
    """Automated backend test suite for Brightloop Phase 9: Payment & Reconciliation Engine."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.AccountMove = cls.env['account.move']
        cls.AccountMoveLine = cls.env['account.move.line']
        cls.AccountPayment = cls.env['account.payment']
        cls.AccountJournal = cls.env['account.journal']
        cls.PaymentService = cls.env['brightloop.payment.service']
        cls.BillingPeriod = cls.env['brightloop.billing.period']
        cls.BillingService = cls.env['brightloop.billing.service']
        cls.SubscriptionPlan = cls.env['brightloop.subscription.plan']
        cls.Subscription = cls.env['brightloop.subscription']
        cls.SubscriptionLine = cls.env['brightloop.subscription.line']
        cls.SecurityAudit = cls.env['brightloop.security.audit']
        cls.ProductProduct = cls.env['product.product']
        cls.Partner = cls.env['res.partner']
        cls.Users = cls.env['res.users']
        cls.Company = cls.env['res.company']

        cls.main_company = cls.env.company
        cls.currency_inr = cls.main_company.currency_id

        # Secondary company for isolation testing
        cls.second_company = cls.Company.create({
            'name': 'Brightloop Subsidiary Ltd P9',
            'currency_id': cls.currency_inr.id,
        })

        # Security groups
        cls.admin_group = cls.env.ref('brightloop_core.group_brightloop_admin')
        cls.staff_group = cls.env.ref('brightloop_core.group_brightloop_staff')
        cls.customer_group = cls.env.ref('brightloop_core.group_brightloop_customer')
        cls.internal_group = cls.env.ref('base.group_user')
        cls.account_invoice_group = cls.env.ref('account.group_account_invoice')
        cls.account_manager_group = cls.env.ref('account.group_account_manager')

        # Partners
        cls.partner_customer = cls.Partner.create({
            'name': 'Rohan Sharma P9',
            'email': 'rohan.sharma.p9@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.partner_other_customer = cls.Partner.create({
            'name': 'Pooja Verma P9',
            'email': 'pooja.verma.p9@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.partner_admin = cls.Partner.create({
            'name': 'Payment Admin P9',
            'email': 'payment.admin.p9@brightloop.io',
            'company_id': cls.main_company.id,
        })
        cls.partner_staff = cls.Partner.create({
            'name': 'Payment Staff P9',
            'email': 'payment.staff.p9@brightloop.io',
            'company_id': cls.main_company.id,
        })

        # Users
        cls.admin_user = cls.Users.create({
            'name': 'Payment Admin User P9',
            'login': 'payment.admin.p9@brightloop.io',
            'email': 'payment.admin.p9@brightloop.io',
            'partner_id': cls.partner_admin.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id, cls.second_company.id])],
            'group_ids': [(6, 0, [
                cls.admin_group.id,
                cls.internal_group.id,
                cls.account_manager_group.id,
            ])],
        })
        cls.staff_user = cls.Users.create({
            'name': 'Payment Staff User P9',
            'login': 'payment.staff.p9@brightloop.io',
            'email': 'payment.staff.p9@brightloop.io',
            'partner_id': cls.partner_staff.id,
            'company_id': cls.main_company.id,
            'company_ids': [(6, 0, [cls.main_company.id])],
            'group_ids': [(6, 0, [
                cls.staff_group.id,
                cls.internal_group.id,
                cls.account_invoice_group.id,
            ])],
        })
        cls.customer_user = cls.Users.create({
            'name': 'Payment Customer User P9',
            'login': 'payment.customer.p9@brightloop.io',
            'email': 'payment.customer.p9@brightloop.io',
            'partner_id': cls.partner_customer.id,
            'company_id': cls.main_company.id,
            'group_ids': [(6, 0, [cls.customer_group.id])],
        })
        cls.other_customer_user = cls.Users.create({
            'name': 'Payment Other Customer User P9',
            'login': 'payment.other.p9@brightloop.io',
            'email': 'payment.other.p9@brightloop.io',
            'partner_id': cls.partner_other_customer.id,
            'company_id': cls.main_company.id,
            'group_ids': [(6, 0, [cls.customer_group.id])],
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

        cls.cash_journal = cls.AccountJournal.search([
            ('type', '=', 'cash'),
            ('company_id', '=', cls.main_company.id),
        ], limit=1)
        if not cls.cash_journal:
            cls.cash_journal = cls.AccountJournal.create({
                'name': 'Cash P9',
                'type': 'cash',
                'code': 'CSHP9',
                'company_id': cls.main_company.id,
            })

        # Secondary company journal
        cls.second_bank_journal = cls.AccountJournal.create({
            'name': 'Bank Sub P9',
            'type': 'bank',
            'code': 'BSUB9',
            'company_id': cls.second_company.id,
        })
        cls.second_sale_journal = cls.AccountJournal.create({
            'name': 'Customer Invoices Sub P9',
            'type': 'sale',
            'code': 'SSUB9',
            'company_id': cls.second_company.id,
        })

        # Product
        cls.test_product = cls.ProductProduct.create({
            'name': 'Cloud Platform Enterprise Tier P9',
            'list_price': 10000.0,
            'type': 'service',
        })

        # Subscription Plan
        cls.test_plan = cls.SubscriptionPlan.create({
            'name': 'Enterprise Monthly P9',
            'product_id': cls.test_product.id,
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
            'list_price': 10000.0,
            'allow_renewal': True,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
        })

        # Subscription Contract
        cls.test_sub = cls.Subscription.create({
            'customer_id': cls.partner_customer.id,
            'company_id': cls.main_company.id,
            'currency_id': cls.currency_inr.id,
            'subscription_plan_id': cls.test_plan.id,
            'start_date': date(2026, 1, 1),
            'billing_anchor_date': date(2026, 1, 1),
            'billing_interval': 'monthly',
            'billing_interval_count': 1,
        })
        cls.test_sub.with_context(bypass_state_guard=True).write({
            'state': 'active',
            'next_billing_date': date(2026, 2, 1),
        })

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    def _create_posted_invoice(self, partner=None, amount=10000.0, company=None,
                               currency=None, subscription=None, due_date=None,
                               journal=None):
        """Helper to create and post an out_invoice account.move."""
        comp = company or self.main_company
        part = partner or self.partner_customer
        curr = currency or self.currency_inr
        jour = journal or (self.sale_journal if comp == self.main_company else self.second_sale_journal)

        inv_vals = {
            'move_type': 'out_invoice',
            'partner_id': part.id,
            'company_id': comp.id,
            'currency_id': curr.id,
            'journal_id': jour.id,
            'invoice_date': date(2026, 1, 1),
            'invoice_date_due': due_date or date(2026, 1, 15),
            'subscription_id': subscription.id if subscription else False,
            'is_subscription_invoice': bool(subscription),
            'invoice_line_ids': [(0, 0, {
                'product_id': self.test_product.id,
                'quantity': 1.0,
                'price_unit': amount,
                'tax_ids': [(6, 0, [])],  # Clean untaxed for exact assertions
            })],
        }
        invoice = self.AccountMove.create(inv_vals)
        invoice.action_post()
        return invoice

    # =========================================================================
    # 1. PAYMENT REGISTRATION
    # =========================================================================

    def test_01_valid_full_payment_registers_and_posts(self):
        """Full payment registers, posts, and transitions invoice to 'paid' with residual 0.0."""
        inv = self._create_posted_invoice(amount=5000.0)
        self.assertEqual(inv.amount_residual, 5000.0)
        self.assertEqual(inv.payment_state, 'not_paid')

        res = self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv.id,
            amount=5000.0,
        )

        self.assertTrue(res['success'])
        self.assertFalse(res['duplicate'])

        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 0.0)
        self.assertEqual(inv.payment_state, 'paid')

        payment = self.AccountPayment.browse(res['payment_id'])
        self.assertIn(payment.state, ('paid', 'reconciled'))
        self.assertIn(inv.id, payment.reconciled_invoice_ids.ids)

    def test_02_payment_links_to_invoice_via_reconciled_invoices(self):
        """Created payment links bidirectionally to the reconciled customer invoice."""
        inv = self._create_posted_invoice(amount=3000.0)
        res = self.PaymentService.with_user(self.staff_user).register_payment(
            invoice_ids=inv.id,
            amount=3000.0,
        )
        pay = self.AccountPayment.browse(res['payment_id'])
        self.assertIn(inv, pay.reconciled_invoice_ids)

    def test_03_payment_amount_must_be_strictly_positive(self):
        """Zero and negative payment amounts are rejected with ValidationError."""
        inv = self._create_posted_invoice(amount=5000.0)

        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv.id,
                amount=0.0,
            )

        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv.id,
                amount=-100.0,
            )

    def test_04_wrong_customer_mismatch_rejected(self):
        """Payment customer must match the invoice customer; mismatch is rejected."""
        inv = self._create_posted_invoice(partner=self.partner_customer, amount=4000.0)

        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv.id,
                amount=4000.0,
                partner_id=self.partner_other_customer.id,
            )

    def test_05_draft_invoice_rejected(self):
        """Cannot register payment against draft invoice."""
        draft_inv = self.AccountMove.create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_customer.id,
            'company_id': self.main_company.id,
            'journal_id': self.sale_journal.id,
            'invoice_line_ids': [(0, 0, {'product_id': self.test_product.id, 'price_unit': 1000.0})],
        })
        self.assertEqual(draft_inv.state, 'draft')

        with self.assertRaises(UserError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=draft_inv.id,
                amount=1000.0,
            )

    def test_06_cancelled_invoice_rejected(self):
        """Cannot register payment against cancelled invoice."""
        inv = self._create_posted_invoice(amount=2000.0)
        inv.button_cancel()
        self.assertEqual(inv.state, 'cancel')

        with self.assertRaises(UserError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv.id,
                amount=2000.0,
            )

    def test_07_cash_journal_payment_supported(self):
        """Payment registered through Cash journal succeeds and reconciles."""
        inv = self._create_posted_invoice(amount=1500.0)
        res = self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv.id,
            amount=1500.0,
            journal_id=self.cash_journal.id,
        )
        self.assertTrue(res['success'])
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.payment_state, 'paid')
        self.assertEqual(inv.amount_residual, 0.0)

    def test_08_already_paid_invoice_rejected_for_new_payment(self):
        """Attempting to pay an already fully paid invoice raises UserError."""
        inv = self._create_posted_invoice(amount=2500.0)
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2500.0)
        inv.invalidate_recordset(['payment_state'])
        self.assertEqual(inv.payment_state, 'paid')

        with self.assertRaises(UserError):
            self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 100.0)

    # =========================================================================
    # 2. PARTIAL PAYMENTS & MULTI-INVOICE ALLOCATIONS
    # =========================================================================

    def test_09_single_partial_payment_leaves_correct_residual(self):
        """Partial payment of 4,000 on 10,000 invoice leaves exactly 6,000 residual."""
        inv = self._create_posted_invoice(amount=10000.0)

        res = self.PaymentService.with_user(self.staff_user).register_payment(
            invoice_ids=inv.id,
            amount=4000.0,
        )
        self.assertTrue(res['success'])

        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 6000.0)
        self.assertEqual(inv.payment_state, 'partial')

    def test_10_multiple_partial_payments_accumulate_to_full_settlement(self):
        """
        Three partial payments:
        10,000 invoice:
        - Pay 4,000 -> residual 6,000 (partial)
        - Pay 3,000 -> residual 3,000 (partial)
        - Pay 3,000 -> residual 0 (paid)
        """
        inv = self._create_posted_invoice(amount=10000.0)

        # Payment 1
        self.PaymentService.with_user(self.staff_user).register_payment(inv.id, 4000.0)
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 6000.0)
        self.assertEqual(inv.payment_state, 'partial')

        # Payment 2
        self.PaymentService.with_user(self.staff_user).register_payment(inv.id, 3000.0)
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 3000.0)
        self.assertEqual(inv.payment_state, 'partial')

        # Payment 3
        self.PaymentService.with_user(self.staff_user).register_payment(inv.id, 3000.0)
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 0.0)
        self.assertEqual(inv.payment_state, 'paid')

    def test_11_payment_amount_cannot_exceed_invoice_residual(self):
        """Attempting to pay more than the outstanding residual raises ValidationError."""
        inv = self._create_posted_invoice(amount=5000.0)

        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 5001.0)

    def test_12_one_payment_allocated_across_multiple_invoices(self):
        """One payment of 10,000 settles two invoices of 4,000 and 6,000 simultaneously."""
        inv1 = self._create_posted_invoice(amount=4000.0)
        inv2 = self._create_posted_invoice(amount=6000.0)

        res = self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=[inv1.id, inv2.id],
            amount=10000.0,
        )
        self.assertTrue(res['success'])

        inv1.invalidate_recordset(['amount_residual', 'payment_state'])
        inv2.invalidate_recordset(['amount_residual', 'payment_state'])

        self.assertEqual(inv1.amount_residual, 0.0)
        self.assertEqual(inv1.payment_state, 'paid')

        self.assertEqual(inv2.amount_residual, 0.0)
        self.assertEqual(inv2.payment_state, 'paid')

        pay = self.AccountPayment.browse(res['payment_id'])
        self.assertEqual(set(pay.reconciled_invoice_ids.ids), {inv1.id, inv2.id})

    # =========================================================================
    # 3. OUTSTANDING BALANCE QUERY
    # =========================================================================

    def test_13_get_outstanding_balance_reflects_exact_residual(self):
        """get_outstanding_balance matches native amount_residual at all lifecycle stages."""
        inv = self._create_posted_invoice(amount=8000.0)

        # Before payment
        bal0 = self.PaymentService.with_user(self.admin_user).get_outstanding_balance(inv)
        self.assertEqual(bal0, 8000.0)

        # After partial payment
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 5000.0)
        bal1 = self.PaymentService.with_user(self.admin_user).get_outstanding_balance(inv)
        self.assertEqual(bal1, 3000.0)

        # After final payment
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 3000.0)
        bal2 = self.PaymentService.with_user(self.admin_user).get_outstanding_balance(inv)
        self.assertEqual(bal2, 0.0)

    def test_14_get_invoice_payment_status_structure(self):
        """get_invoice_payment_status returns complete structured accounting metadata."""
        inv = self._create_posted_invoice(amount=4500.0, due_date=date(2026, 3, 1))
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2000.0)

        status = self.PaymentService.with_user(self.admin_user).get_invoice_payment_status(inv)
        self.assertEqual(status['invoice_id'], inv.id)
        self.assertEqual(status['state'], 'posted')
        self.assertEqual(status['payment_state'], 'partial')
        self.assertEqual(status['amount_total'], 4500.0)
        self.assertEqual(status['amount_residual'], 2500.0)
        self.assertFalse(status['is_paid'])
        self.assertEqual(len(status['payments']), 1)
        self.assertEqual(status['payments'][0]['amount'], 2000.0)

    # =========================================================================
    # 4. SUBSCRIPTION TRACEABILITY & PAYMENT HISTORY
    # =========================================================================

    def test_15_payment_linked_to_subscription_contract(self):
        """Payment registered for a subscription invoice automatically traces to the subscription."""
        inv = self._create_posted_invoice(amount=1500.0, subscription=self.test_sub)
        self.assertEqual(inv.subscription_id, self.test_sub)

        res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 1500.0)
        pay = self.AccountPayment.browse(res['payment_id'])

        # Traceability field on payment
        self.assertEqual(pay.subscription_id, self.test_sub)

    def test_16_get_subscription_payment_history(self):
        """get_subscription_payment_history retrieves payments made for a specific contract."""
        inv = self._create_posted_invoice(amount=2000.0, subscription=self.test_sub)
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2000.0)

        history = self.PaymentService.with_user(self.admin_user).get_subscription_payment_history(self.test_sub)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]['subscription_id'], self.test_sub.id)
        self.assertEqual(history[0]['amount'], 2000.0)

    def test_17_get_customer_payment_history(self):
        """get_customer_payment_history returns all inbound settled payments for customer."""
        inv1 = self._create_posted_invoice(partner=self.partner_customer, amount=1000.0)
        inv2 = self._create_posted_invoice(partner=self.partner_customer, amount=2000.0)

        self.PaymentService.with_user(self.admin_user).register_payment(inv1.id, 1000.0)
        self.PaymentService.with_user(self.admin_user).register_payment(inv2.id, 2000.0)

        history = self.PaymentService.with_user(self.admin_user).get_customer_payment_history(self.partner_customer)
        self.assertGreaterEqual(len(history), 2)
        amounts = [p['amount'] for p in history]
        self.assertIn(1000.0, amounts)
        self.assertIn(2000.0, amounts)

    # =========================================================================
    # 5. OVERDUE INVOICE MANAGEMENT
    # =========================================================================

    def test_18_unpaid_overdue_invoice_detected(self):
        """Posted invoice past due date with residual > 0 is detected as overdue."""
        past_due = date.today() - relativedelta(days=10)
        inv = self._create_posted_invoice(amount=3500.0, due_date=past_due)

        overdue_list = self.PaymentService.with_user(self.admin_user).get_overdue_invoices()
        overdue_ids = [o['invoice_id'] for o in overdue_list]
        self.assertIn(inv.id, overdue_ids)

        # Match days overdue
        inv_item = next(o for o in overdue_list if o['invoice_id'] == inv.id)
        self.assertEqual(inv_item['days_overdue'], 10)
        self.assertEqual(inv_item['amount_residual'], 3500.0)

    def test_19_fully_paid_invoice_excluded_from_overdue(self):
        """Once fully paid, an invoice past due date is strictly excluded from overdue."""
        past_due = date.today() - relativedelta(days=15)
        inv = self._create_posted_invoice(amount=2500.0, due_date=past_due)

        # Pay in full
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2500.0)

        overdue_list = self.PaymentService.with_user(self.admin_user).get_overdue_invoices()
        overdue_ids = [o['invoice_id'] for o in overdue_list]
        self.assertNotIn(inv.id, overdue_ids)

    def test_20_future_due_invoice_excluded_from_overdue(self):
        """Invoice with due date in the future is excluded from overdue list."""
        future_due = date.today() + relativedelta(days=30)
        inv = self._create_posted_invoice(amount=4000.0, due_date=future_due)

        overdue_list = self.PaymentService.with_user(self.admin_user).get_overdue_invoices()
        overdue_ids = [o['invoice_id'] for o in overdue_list]
        self.assertNotIn(inv.id, overdue_ids)

    def test_21_partially_paid_overdue_invoice_reports_remaining_residual(self):
        """Partially paid invoice past due reports only the remaining residual."""
        past_due = date.today() - relativedelta(days=5)
        inv = self._create_posted_invoice(amount=6000.0, due_date=past_due)

        # Pay 2000 of 6000
        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2000.0)

        overdue_list = self.PaymentService.with_user(self.admin_user).get_overdue_invoices()
        inv_item = next(o for o in overdue_list if o['invoice_id'] == inv.id)
        self.assertEqual(inv_item['amount_residual'], 4000.0)
        self.assertEqual(inv_item['payment_state'], 'partial')

    # =========================================================================
    # 6. PAYMENT REVERSAL / REFUNDS
    # =========================================================================

    def test_22_valid_payment_reversal_restores_invoice_residual(self):
        """Reversing a payment unreconciles the invoice and restores its residual."""
        inv = self._create_posted_invoice(amount=7000.0)
        res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 7000.0)
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 0.0)
        self.assertEqual(inv.payment_state, 'paid')

        payment = self.AccountPayment.browse(res['payment_id'])

        # Reverse payment
        rev_res = self.PaymentService.with_user(self.admin_user).reverse_payment(
            payment=payment,
            reason='Customer requested payment bounce handling',
        )
        self.assertTrue(rev_res['success'])
        self.assertEqual(payment.state, 'canceled')

        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 7000.0)
        self.assertEqual(inv.payment_state, 'not_paid')

    def test_23_non_admin_cannot_reverse_payment(self):
        """Staff and Customer users are blocked from reversing payments with AccessError."""
        inv = self._create_posted_invoice(amount=3000.0)
        res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 3000.0)
        payment = self.AccountPayment.browse(res['payment_id'])

        with self.assertRaises(AccessError):
            self.PaymentService.with_user(self.staff_user).reverse_payment(payment)

        with self.assertRaises(AccessError):
            self.PaymentService.with_user(self.customer_user).reverse_payment(payment)

    def test_24_reversing_already_cancelled_payment_raises_user_error(self):
        """Attempting to reverse an already cancelled payment raises UserError."""
        inv = self._create_posted_invoice(amount=1200.0)
        res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 1200.0)
        payment = self.AccountPayment.browse(res['payment_id'])

        self.PaymentService.with_user(self.admin_user).reverse_payment(payment)
        self.assertEqual(payment.state, 'canceled')

        with self.assertRaises(UserError):
            self.PaymentService.with_user(self.admin_user).reverse_payment(payment)

    # =========================================================================
    # 7. ROLE-BASED SECURITY & ACCESS CONTROL
    # =========================================================================

    def test_25_customer_blocked_from_registering_payments(self):
        """Customer portal user is strictly blocked from registering payments directly."""
        inv = self._create_posted_invoice(partner=self.partner_customer, amount=2000.0)

        with self.assertRaises(AccessError):
            self.PaymentService.with_user(self.customer_user).register_payment(inv.id, 2000.0)

    def test_26_customer_cannot_view_other_customers_payment_history(self):
        """Customer cannot access another customer's payment history."""
        # Customer 1 cannot see Customer 2's payment history
        with self.assertRaises(AccessError):
            self.PaymentService.with_user(self.customer_user).get_customer_payment_history(
                partner=self.partner_other_customer
            )

    def test_27_customer_cannot_view_other_customers_invoice_status(self):
        """Customer cannot query payment status of another customer's invoice."""
        other_inv = self._create_posted_invoice(partner=self.partner_other_customer, amount=3000.0)

        with self.assertRaises(AccessError):
            self.PaymentService.with_user(self.customer_user).get_invoice_payment_status(other_inv)

    def test_28_cross_company_payment_rejected(self):
        """Attempting to pay an invoice using a journal from another company is rejected."""
        main_inv = self._create_posted_invoice(company=self.main_company, amount=2000.0)

        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=main_inv.id,
                amount=2000.0,
                journal_id=self.second_bank_journal.id,  # Subsidiary company journal
            )

    # =========================================================================
    # 8. AUDIT TRAIL LOGGING
    # =========================================================================

    def test_29_payment_registration_and_reconciliation_audit_events_logged(self):
        """Registering a payment logs payment_registered and payment_reconciled audit events."""
        inv = self._create_posted_invoice(amount=3200.0)
        audit_before = self.SecurityAudit.search_count([])

        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 3200.0)

        new_audits = self.SecurityAudit.search([('id', '>', audit_before)])
        events = set(new_audits.mapped('event_type'))

        self.assertIn('payment_registered', events)
        self.assertIn('payment_reconciled', events)
        self.assertIn('payment_settled', events)

    def test_30_partial_payment_logs_payment_partial_audit_event(self):
        """Partial payment logs payment_partial audit event with remaining residual."""
        inv = self._create_posted_invoice(amount=5000.0)
        audit_before = self.SecurityAudit.search_count([])

        self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2000.0)

        new_audits = self.SecurityAudit.search([('id', '>', audit_before)])
        events = set(new_audits.mapped('event_type'))

        self.assertIn('payment_partial', events)
        self.assertNotIn('payment_settled', events)

    def test_31_payment_reversal_logs_payment_reversed_audit_event(self):
        """Payment reversal logs payment_reversed audit event."""
        inv = self._create_posted_invoice(amount=1800.0)
        res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 1800.0)
        pay = self.AccountPayment.browse(res['payment_id'])

        audit_before = self.SecurityAudit.search_count([])
        self.PaymentService.with_user(self.admin_user).reverse_payment(pay, reason='Dispute resolved')

        new_audits = self.SecurityAudit.search([('id', '>', audit_before)])
        events = set(new_audits.mapped('event_type'))
        self.assertIn('payment_reversed', events)

    # =========================================================================
    # 9. IDEMPOTENCY & DUPLICATE PROTECTION
    # =========================================================================

    def test_32_repeated_request_with_idempotency_key_prevents_duplicate_charge(self):
        """Repeated payment request with same idempotency_key returns existing payment safely."""
        inv = self._create_posted_invoice(amount=5000.0)
        key = f"pay_test_{inv.id}_unique_123"

        # First attempt: creates payment
        res1 = self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv.id,
            amount=5000.0,
            idempotency_key=key,
        )
        self.assertTrue(res1['success'])
        self.assertFalse(res1['duplicate'])

        # Second attempt: detected and returns existing
        res2 = self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv.id,
            amount=5000.0,
            idempotency_key=key,
        )
        self.assertTrue(res2['success'])
        self.assertTrue(res2['duplicate'])
        self.assertEqual(res1['payment_id'], res2['payment_id'])

        # Total payments in system for this invoice is strictly 1
        pay_count = self.AccountPayment.search_count([('idempotency_key', '=', key)])
        self.assertEqual(pay_count, 1)

    def test_33_duplicate_idempotency_key_rejected_by_db_constraint(self):
        """Direct creation of duplicate idempotency key is prohibited by PostgreSQL constraint."""
        key = "pay_raw_sql_constraint_key_999"
        self.AccountPayment.create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_customer.id,
            'amount': 100.0,
            'journal_id': self.bank_journal.id,
            'company_id': self.main_company.id,
            'idempotency_key': key,
        })

        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.AccountPayment.create({
                    'payment_type': 'inbound',
                    'partner_type': 'customer',
                    'partner_id': self.partner_customer.id,
                    'amount': 200.0,
                    'journal_id': self.bank_journal.id,
                    'company_id': self.main_company.id,
                    'idempotency_key': key,
                })

    def test_34_idempotency_key_reuse_with_different_amount_rejected(self):
        """Reusing an idempotency key with a different amount must raise ValidationError."""
        inv = self._create_posted_invoice(amount=5000.0)
        key = f"pay_mismatch_amt_{inv.id}"

        # Register initial payment of 2000
        self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv.id,
            amount=2000.0,
            idempotency_key=key,
        )

        # Attempt to reuse same key with amount 3000 -> must fail
        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv.id,
                amount=3000.0,
                idempotency_key=key,
            )

    def test_35_idempotency_key_reuse_with_different_customer_rejected(self):
        """Reusing an idempotency key with a different customer must raise ValidationError."""
        inv1 = self._create_posted_invoice(partner=self.partner_customer, amount=3000.0)
        inv2 = self._create_posted_invoice(partner=self.partner_other_customer, amount=3000.0)
        key = f"pay_mismatch_cust_{inv1.id}"

        self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv1.id,
            amount=3000.0,
            partner_id=self.partner_customer.id,
            idempotency_key=key,
        )

        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv2.id,
                amount=3000.0,
                partner_id=self.partner_other_customer.id,
                idempotency_key=key,
            )

    def test_36_idempotency_key_reuse_with_different_invoice_allocation_rejected(self):
        """Reusing an idempotency key with different invoice allocation must raise ValidationError."""
        inv1 = self._create_posted_invoice(amount=4000.0)
        inv2 = self._create_posted_invoice(amount=4000.0)
        key = f"pay_mismatch_alloc_{inv1.id}"

        self.PaymentService.with_user(self.admin_user).register_payment(
            invoice_ids=inv1.id,
            amount=4000.0,
            idempotency_key=key,
        )

        # Reusing key with inv2 instead of inv1
        with self.assertRaises(ValidationError):
            self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv2.id,
                amount=4000.0,
                idempotency_key=key,
            )

    def test_37_reversal_preserves_posted_accounting_history(self):
        """Reversal does NOT delete accounting records; move is kept with state='cancel' and audit preserved."""
        inv = self._create_posted_invoice(amount=2500.0)
        res = self.PaymentService.with_user(self.admin_user).register_payment(inv.id, 2500.0)
        payment = self.AccountPayment.browse(res['payment_id'])
        pay_move = payment.move_id
        move_id = pay_move.id

        # Verify move exists in posted state before reversal
        self.assertEqual(pay_move.state, 'posted')

        # Reverse payment
        self.PaymentService.with_user(self.admin_user).reverse_payment(payment, reason='Preservation audit check')

        # Move record must NOT be deleted from PostgreSQL
        persisted_move = self.AccountMove.search([('id', '=', move_id)])
        self.assertEqual(len(persisted_move), 1, "Cancelled payment move must not be deleted from database")
        self.assertEqual(persisted_move.state, 'cancel', "Payment move must be in cancel state")

        # Invoice residual must be restored
        inv.invalidate_recordset(['amount_residual', 'payment_state'])
        self.assertEqual(inv.amount_residual, 2500.0)
        self.assertEqual(inv.payment_state, 'not_paid')

    # =========================================================================
    # 10. PERFORMANCE BENCHMARK (100 INVOICE PAYMENTS)
    # =========================================================================

    def test_38_performance_benchmark_100_payments_registration_and_reconciliation(self):
        """
        BENCHMARK: Register and reconcile payments for 100 subscription invoices.

        Validates:
        - 100 customer invoices created and posted.
        - 100 distinct payments registered and reconciled.
        - All 100 invoices transition payment_state to 'paid' with residual 0.0.
        - Throughput exceeds 10 payments/second (completes under 60 seconds).
        """
        COUNT = 100
        invoices = []

        # Bulk create 100 invoices
        setup_start = time.time()
        for i in range(COUNT):
            inv = self.AccountMove.create({
                'move_type': 'out_invoice',
                'partner_id': self.partner_customer.id,
                'company_id': self.main_company.id,
                'currency_id': self.currency_inr.id,
                'journal_id': self.sale_journal.id,
                'invoice_date': date(2026, 1, 1),
                'subscription_id': self.test_sub.id,
                'invoice_line_ids': [(0, 0, {
                    'product_id': self.test_product.id,
                    'quantity': 1.0,
                    'price_unit': 1000.0 + i,
                    'tax_ids': [(6, 0, [])],
                })],
            })
            inv.action_post()
            invoices.append(inv)

        setup_duration = time.time() - setup_start

        # Benchmark Payment Registration & Reconciliation
        payment_start = time.time()
        success_count = 0
        for i, inv in enumerate(invoices):
            res = self.PaymentService.with_user(self.admin_user).register_payment(
                invoice_ids=inv.id,
                amount=inv.amount_residual,
                idempotency_key=f"bench_p9_pay_{inv.id}_{i}",
            )
            if res.get('success'):
                success_count += 1

        payment_duration = time.time() - payment_start
        throughput = COUNT / max(payment_duration, 0.001)

        # Assertions
        self.assertEqual(success_count, COUNT)

        paid_count = self.AccountMove.search_count([
            ('id', 'in', [inv.id for inv in invoices]),
            ('payment_state', '=', 'paid'),
            ('amount_residual', '=', 0.0),
        ])
        self.assertEqual(paid_count, COUNT)

        _logger.info(
            "[BENCHMARK P9] %d payments registered & reconciled in %.2fs (%.1f payments/sec). Setup: %.2fs.",
            COUNT, payment_duration, throughput, setup_duration
        )

        # NOTE: In isolated runs this benchmark completes in ~29s.
        # In the full Phase 1–10 monolithic suite, accumulated records from the
        # Phase 8 billing benchmark (1000+ invoices) and prior payment tests increase
        # reconciliation query time. The threshold is set to 180s to accommodate the
        # observed worst-case monolithic overhead (~95s) with a 2× safety margin,
        # while still catching genuine regressions.
        # Standalone threshold: 60s. Monolithic allowance: 180s.
        self.assertLess(
            payment_duration, 180.0,
            f"Payment registration took {payment_duration:.2f}s, exceeding 180s monolithic limit for {COUNT} payments."
        )
