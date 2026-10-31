# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.tests.test_role_security
#
# Automated Tests for Role Architecture, Staff Provisioning & Permission Controls
# =============================================================================

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase


class TestRoleSecurity(TransactionCase):
    """
    Test suite for role permissions, admin-only staff provisioning, privilege
    escalation defense, and customer administration restriction.
    """

    def setUp(self):
        super().setUp()
        self.Users = self.env['res.users']
        self.admin_group = self.env.ref('brightloop_core.group_brightloop_admin')
        self.staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        self.customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        self.internal_group = self.env.ref('base.group_user')
        self.portal_group = self.env.ref('base.group_portal')

        # 1. Create an Admin user
        partner_admin = self.env['res.partner'].create({'name': 'Brightloop Admin', 'email': 'admin@brightloop.io'})
        self.admin_user = self.Users.create({
            'name': 'Brightloop Admin',
            'login': 'admin@brightloop.io',
            'email': 'admin@brightloop.io',
            'partner_id': partner_admin.id,
            'group_ids': [(6, 0, [self.admin_group.id, self.internal_group.id])],
        })

        # 2. Create a Staff user via admin
        self.staff_user = self.Users.with_user(self.admin_user).create_staff_user(
            name='Staff Member',
            email='staff@brightloop.io',
            password='StaffSecurePass123!',
        )

        # 3. Create a Customer user via registration
        self.customer_user = self.Users.register_customer(
            name='Customer Member',
            email='customer@brightloop.io',
            password='CustomerSecurePass123!',
        )

    def test_01_admin_can_create_staff(self):
        """Admin user must be authorized to create staff members."""
        new_staff = self.Users.with_user(self.admin_user).create_staff_user(
            name='Second Staff',
            email='second.staff@brightloop.io',
            password='SecondStaffPass123!',
        )
        self.assertTrue(new_staff)
        self.assertIn(self.staff_group, new_staff.all_group_ids)
        self.assertNotIn(self.admin_group, new_staff.all_group_ids)

    def test_02_staff_cannot_create_staff(self):
        """Staff user attempting to create another staff user must raise AccessError."""
        with self.assertRaises(AccessError):
            self.Users.with_user(self.staff_user).create_staff_user(
                name='Illegal Staff',
                email='illegal.staff@brightloop.io',
                password='IllegalStaffPass123!',
            )

    def test_03_customer_cannot_create_staff(self):
        """Customer attempting to create a staff user must raise AccessError."""
        with self.assertRaises(AccessError):
            self.Users.with_user(self.customer_user).create_staff_user(
                name='Customer Rogue Staff',
                email='rogue.staff@brightloop.io',
                password='RogueStaffPass123!',
            )

    def test_04_staff_cannot_grant_admin_permissions(self):
        """Staff user cannot escalate privileges to Administrator."""
        with self.assertRaises(AccessError):
            self.staff_user.with_user(self.staff_user).write({
                'group_ids': [(4, self.admin_group.id)],
            })

    def test_05_customer_cannot_access_audit_logs(self):
        """Customer cannot read system security audit records."""
        # Create an audit event
        self.env['brightloop.security.audit'].log_event(
            event_type='staff_creation',
            summary='Test event for audit check',
        )

        # Customer attempts to read audit logs
        with self.assertRaises(AccessError):
            self.env['brightloop.security.audit'].with_user(self.customer_user).search([])
