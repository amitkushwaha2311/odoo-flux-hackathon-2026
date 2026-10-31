# -*- coding: utf-8 -*-
# =============================================================================
# brightloop_core.models.res_users
#
# Extensions to res.users for Brightloop Authentication & Security
#
# PHASE 2 SCOPE
# -------------
# - Password strength policy enforcement (length > 8, upper, lower, special char).
# - Secure Customer Registration service with email normalization & uniqueness.
# - Authorized Staff User Creation restricted strictly to Administrators.
# - Protection against privilege escalation during user creation and update.
# - Security audit logging for registration, staff creation, and role changes.
# =============================================================================

import re
import logging
from odoo import api, fields, models
from odoo.exceptions import AccessError, ValidationError, UserError

_logger = logging.getLogger(__name__)

EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')


class ResUsers(models.Model):
    _inherit = 'res.users'

    # =========================================================================
    # PASSWORD POLICY VALIDATION
    # =========================================================================

    @api.model
    def _validate_password_policy(self, password: str) -> None:
        """
        Validate password according to Brightloop Phase 2 security policy:
          1. Must be more than 8 characters long (> 8 chars, i.e., min 9 chars).
          2. Must contain at least one uppercase letter (A-Z).
          3. Must contain at least one lowercase letter (a-z).
          4. Must contain at least one special character (non-alphanumeric).

        :param password: Candidate plaintext password.
        :raises ValidationError: If any policy criteria is not met.
        """
        if not password or not isinstance(password, str):
            raise ValidationError('Password is required and must be a string.')

        if len(password) <= 8:
            raise ValidationError('Password must contain more than eight characters.')

        if not re.search(r'[A-Z]', password):
            raise ValidationError('Password must contain at least one uppercase letter.')

        if not re.search(r'[a-z]', password):
            raise ValidationError('Password must contain at least one lowercase letter.')

        if not re.search(r'[^A-Za-z0-9]', password):
            raise ValidationError('Password must contain at least one special character.')

    # =========================================================================
    # OVERRIDE: SECURE PASSWORD HOOK
    # =========================================================================

    def _set_password(self):
        """
        Intercept password updates to enforce password policy before hashing.
        """
        for user in self:
            if user.password:
                self._validate_password_policy(user.password)
        return super()._set_password()

    # =========================================================================
    # CUSTOMER REGISTRATION SERVICE
    # =========================================================================

    @api.model
    def register_customer(self, name: str, email: str, password: str, ip_address=None):
        """
        Securely register a new customer account.

        Requirements:
          - Email is required.
          - Email normalized to lowercase and trimmed.
          - Case-insensitive email uniqueness check.
          - Password policy enforcement.
          - Automatic Odoo partner association.
          - Assign ONLY the Customer role (base.group_portal + group_brightloop_customer).
          - Strips any privileged groups.
          - Audit log entry.

        :param name: Customer full name.
        :param email: Customer email address.
        :param password: Customer plaintext password.
        :param ip_address: Optional client IP address.
        :return: Created res.users record.
        """
        # Validate name
        name = (name or '').strip()
        if not name:
            raise ValidationError('Customer name is required.')

        # Validate and normalize email
        raw_email = (email or '').strip()
        if not raw_email:
            raise ValidationError('Email is required.')

        if not EMAIL_REGEX.match(raw_email):
            raise ValidationError('Please provide a valid email address.')

        normalized_email = raw_email.lower()

        # Check case-insensitive uniqueness against login and email
        existing = self.sudo().search([
            '|',
            ('login', '=ilike', normalized_email),
            ('email', '=ilike', normalized_email),
        ], limit=1)
        if existing:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Duplicate customer registration attempt',
                details=f'Attempted registration with existing email: {normalized_email}',
                ip_address=ip_address,
            )
            raise ValidationError('A user with this email address already exists.')

        # Validate password policy
        self._validate_password_policy(password)

        # Lookup security groups
        customer_group = self.env.ref('brightloop_core.group_brightloop_customer')
        portal_group = self.env.ref('base.group_portal')

        # Create or find partner
        partner = self.env['res.partner'].sudo().create({
            'name': name,
            'email': normalized_email,
            'company_id': self.env.company.id,
        })

        # Create user with restricted customer permissions only
        user = self.sudo().create({
            'name': name,
            'login': normalized_email,
            'email': normalized_email,
            'password': password,
            'partner_id': partner.id,
            'company_id': self.env.company.id,
            'group_ids': [(6, 0, [customer_group.id, portal_group.id])],
        })

        # Log security audit
        self.env['brightloop.security.audit'].log_event(
            event_type='customer_registration',
            summary='New customer registered',
            details=f'Customer {normalized_email} registered successfully.',
            target_user_id=user.id,
            ip_address=ip_address,
        )

        return user

    # =========================================================================
    # STAFF CREATION SERVICE
    # =========================================================================

    @api.model
    def create_staff_user(self, name: str, email: str, password: str, ip_address=None):
        """
        Create an internal Staff user.

        RESTRICTIONS:
          - Caller MUST have Administrator privileges (group_brightloop_admin or superuser).
          - Non-admins attempting this action are rejected with AccessError and logged.
          - Assigns Brightloop Staff role (group_brightloop_staff + base.group_user).
          - Strictly prevents assigning Administrator permissions via this method.

        :param name: Staff full name.
        :param email: Staff corporate email.
        :param password: Staff initial password.
        :param ip_address: Optional IP address.
        :return: Created res.users record.
        """
        # Authorization check: only Admins may create staff
        caller = self.env.user
        caller_is_admin = self.env.is_admin() or caller.has_group('brightloop_core.group_brightloop_admin') or caller.has_group('base.group_system')

        if not caller_is_admin:
            self.env['brightloop.security.audit'].log_event(
                event_type='unauthorized_access',
                summary='Unauthorized staff creation attempt',
                details=f'User {caller.login} (ID={caller.id}) attempted to create staff user without Admin role.',
                ip_address=ip_address,
            )
            raise AccessError('Only Brightloop Administrators can create Staff users.')

        name = (name or '').strip()
        if not name:
            raise ValidationError('Staff name is required.')

        raw_email = (email or '').strip()
        if not raw_email:
            raise ValidationError('Email is required.')

        if not EMAIL_REGEX.match(raw_email):
            raise ValidationError('Please provide a valid email address.')

        normalized_email = raw_email.lower()

        # Check uniqueness
        existing = self.sudo().search([
            '|',
            ('login', '=ilike', normalized_email),
            ('email', '=ilike', normalized_email),
        ], limit=1)
        if existing:
            raise ValidationError('A user with this email address already exists.')

        # Validate password policy
        self._validate_password_policy(password)

        staff_group = self.env.ref('brightloop_core.group_brightloop_staff')
        internal_group = self.env.ref('base.group_user')

        # Create partner
        partner = self.env['res.partner'].sudo().create({
            'name': name,
            'email': normalized_email,
            'company_id': self.env.company.id,
        })

        # Create staff user
        staff_user = self.sudo().create({
            'name': name,
            'login': normalized_email,
            'email': normalized_email,
            'password': password,
            'partner_id': partner.id,
            'company_id': self.env.company.id,
            'group_ids': [(6, 0, [staff_group.id, internal_group.id])],
        })

        # Log audit
        self.env['brightloop.security.audit'].log_event(
            event_type='staff_creation',
            summary='Internal staff user created',
            details=f'Staff user {normalized_email} created by admin {caller.login}.',
            target_user_id=staff_user.id,
            ip_address=ip_address,
        )

        return staff_user

    # =========================================================================
    # WRITE OVERRIDE: PRIVILEGE ESCALATION PROTECTION
    # =========================================================================

    def write(self, vals):
        """
        Prevent non-admin users from escalating privileges by assigning
        Administrator roles to themselves or others.
        """
        if 'group_ids' in vals and not self.env.is_superuser():
            admin_group = self.env.ref('brightloop_core.group_brightloop_admin', raise_if_not_found=False)
            system_group = self.env.ref('base.group_system', raise_if_not_found=False)
            erp_manager = self.env.ref('base.group_erp_manager', raise_if_not_found=False)

            protected_group_ids = {
                g.id for g in [admin_group, system_group, erp_manager] if g
            }

            caller = self.env.user
            caller_is_admin = self.env.is_admin() or caller.has_group('brightloop_core.group_brightloop_admin')

            if not caller_is_admin:
                # Inspect group operations in vals['group_ids']
                for op in vals['group_ids']:
                    if isinstance(op, (list, tuple)) and len(op) >= 2:
                        code = op[0]
                        # (4, id), (6, 0, [ids])
                        target_ids = []
                        if code == 4 and len(op) >= 2:
                            target_ids = [op[1]]
                        elif code == 6 and len(op) >= 3:
                            target_ids = op[2]

                        if any(gid in protected_group_ids for gid in target_ids):
                            self.env['brightloop.security.audit'].log_event(
                                event_type='unauthorized_access',
                                summary='Privilege escalation attempt blocked',
                                details=f'User {caller.login} attempted to grant administrator group {target_ids}',
                                target_user_id=self.id if len(self) == 1 else False,
                            )
                            raise AccessError('Only Administrators can modify administrative permissions.')

        return super().write(vals)
