# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_record_isolation
#
# Automated Tests for Record-Level Security & Customer Data Isolation
# =============================================================================

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestRecordIsolation(TransactionCase):
    """
    Test suite for customer row-level isolation, multi-tenant privacy,
    and access boundary enforcement.
    """

    def setUp(self):
        super().setUp()
        self.Users = self.env['res.users']
        self.RecordModel = self.env['brightloop.customer.record']

        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')
        self.internal_group = self.env.ref('base.group_user')

        # 1. Admin
        partner_admin = self.env['res.partner'].create({'name': 'Admin', 'email': 'admin_rec@brightloop.io'})
        self.admin_user = self.Users.create({
            'name': 'Admin Rec',
            'login': 'admin_rec@brightloop.io',
            'email': 'admin_rec@brightloop.io',
            'partner_id': partner_admin.id,
            'group_ids': [(6, 0, [self.admin_group.id, self.internal_group.id])],
        })

        # 2. Staff
        self.staff_user = self.Users.with_user(self.admin_user).create_staff_user(
            name='Staff Rec',
            email='staff_rec@brightloop.io',
            password='StaffSecurePass123!',
        )

        # 3. Customer A
        self.customer_a = self.Users.register_customer(
            name='Customer Alice',
            email='customer.a@brightloop.io',
            password='CustomerAPassword123!',
        )

        # 4. Customer B
        self.customer_b = self.Users.register_customer(
            name='Customer Bob',
            email='customer.b@brightloop.io',
            password='CustomerBPassword123!',
        )

        # 5. Create customer records for Alice (Subscriptions and Invoices)
        self.record_a_sub = self.RecordModel.sudo().create({
            'name': 'Alice SaaS Pro Subscription',
            'partner_id': self.customer_a.partner_id.id,
            'record_type': 'subscription_summary',
            'reference': 'SUB-ALICE-001',
            'data_payload': 'Confidential subscription terms for Alice',
        })

        self.record_a_inv = self.RecordModel.sudo().create({
            'name': 'Alice Invoice INV/2026/001',
            'partner_id': self.customer_a.partner_id.id,
            'record_type': 'invoice_summary',
            'reference': 'INV-ALICE-001',
            'data_payload': 'Amount Due: $499.00',
        })

        # 6. Create customer records for Bob
        self.record_b_sub = self.RecordModel.sudo().create({
            'name': 'Bob Enterprise Subscription',
            'partner_id': self.customer_b.partner_id.id,
            'record_type': 'subscription_summary',
            'reference': 'SUB-BOB-001',
            'data_payload': 'Confidential enterprise subscription terms for Bob',
        })

    def test_01_customer_can_read_own_records(self):
        """Customer A must be able to view their own records."""
        alice_records = self.RecordModel.with_user(self.customer_a).search([])
        alice_ids = alice_records.ids

        self.assertIn(self.record_a_sub.id, alice_ids, "Alice must see her subscription.")
        self.assertIn(self.record_a_inv.id, alice_ids, "Alice must see her invoice.")
        self.assertNotIn(self.record_b_sub.id, alice_ids, "Alice must NOT see Bob's subscription in search results.")

    def test_02_customer_cannot_read_other_customer_record_by_id(self):
        """Customer A attempting direct ORM access to Customer B's record must be rejected."""
        # Direct read on Bob's record using Customer A's environment
        with self.assertRaises(AccessError):
            self.RecordModel.with_user(self.customer_a).browse(self.record_b_sub.id).read(['name', 'data_payload'])

    def test_03_customer_cannot_modify_other_customer_record(self):
        """Customer A attempting to modify Customer B's record must raise AccessError."""
        with self.assertRaises(AccessError):
            self.RecordModel.with_user(self.customer_a).browse(self.record_b_sub.id).write({
                'name': 'Hacked Bob Subscription',
            })

    def test_04_customer_cannot_create_unauthorized_records(self):
        """Customer cannot create arbitrary records (only 'r' read permission is granted in ir.access)."""
        with self.assertRaises(AccessError):
            self.RecordModel.with_user(self.customer_a).create({
                'name': 'Unauthorized Fake Record',
                'partner_id': self.customer_a.partner_id.id,
            })

    def test_05_staff_and_admin_have_authorized_access(self):
        """Staff and Admin users have operational visibility across customer records."""
        admin_records = self.RecordModel.with_user(self.admin_user).search([])
        self.assertIn(self.record_a_sub.id, admin_records.ids)
        self.assertIn(self.record_b_sub.id, admin_records.ids)

        staff_records = self.RecordModel.with_user(self.staff_user).search([])
        self.assertIn(self.record_a_sub.id, staff_records.ids)
        self.assertIn(self.record_b_sub.id, staff_records.ids)
