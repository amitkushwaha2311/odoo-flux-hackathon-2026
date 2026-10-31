# brightloop_core

**Brightloop Core** is the foundational Odoo addon for the Brightloop Subscription Intelligence platform.

---

## Architecture Overview

`brightloop_core` provides the core backend infrastructure, multi-company foundation, abstract mixins, and authentication/authorization architecture for Brightloop.

### Key Capabilities
- `brightloop.base` — Abstract mixin providing company awareness, UTC date helpers, logging conventions, and error handling.
- `brightloop.security.audit` — Immutable audit trail of critical security, authentication, and role events.
- `brightloop.password.reset.token` — Cryptographically secure single-use expiring token generator and validator (hashed storage).
- `brightloop.auth.service` — Centralized backend authentication, registration, and password recovery service.
- `brightloop.customer.record` — Partner-linked document model enforcing row-level security and customer data isolation.
- `res.users` extensions — Strict password policy validation, customer registration service, admin-only staff provisioning, and privilege escalation protection.

---

## User Roles & Permission Matrix

Brightloop defines three role tiers using Odoo's native security group hierarchy:

```
[Administrator: group_brightloop_admin]
                 │ (implies)
                 ▼
     [Staff: group_brightloop_staff]
                 │ (implies)
                 ▼
       [Internal User: base.group_user]

[Customer: group_brightloop_customer]
                 │ (implies)
                 ▼
         [Portal: base.group_portal]
```

### Permission Matrix

| Operation / Capability | Customer (`group_brightloop_customer`) | Staff (`group_brightloop_staff`) | Administrator (`group_brightloop_admin`) |
|---|:---:|:---:|:---:|
| **Access Internal Admin Backend** | ❌ Forbidden | ✅ Permitted | ✅ Permitted |
| **View Own Customer Profile & Data** | ✅ Full Access | ✅ Permitted | ✅ Permitted |
| **View Other Customers' Data** | ❌ Forbidden (AccessError) | ✅ Assigned / Permitted | ✅ Full System Access |
| **Create Customer Records (Quotes/Invoices)** | ❌ Read-Only | ✅ Permitted | ✅ Full Access |
| **Create Internal Staff Users** | ❌ Forbidden | ❌ Forbidden (AccessError) | ✅ Permitted |
| **Assign or Modify Security Roles** | ❌ Forbidden | ❌ Forbidden (AccessError) | ✅ Permitted |
| **View Security Audit Logs** | ❌ Forbidden | ❌ Forbidden | ✅ Full Access |
| **Modify or Delete Security Audit Logs** | ❌ Immutable | ❌ Immutable | ❌ Immutable |

---

## Registration Rules

Customer self-registration is processed strictly through `res.users.register_customer()` or `brightloop.auth.service`:
1. **Email Required:** Must be non-empty and conform to standard email syntax.
2. **Case-Insensitive Normalization:** Emails are stripped and normalized to lowercase.
3. **Uniqueness:** Guaranteed case-insensitively across both `login` and `email` fields.
4. **Partner Association:** A linked `res.partner` is automatically created with matching name and email.
5. **Group Protection:** New customers are assigned **only** `group_brightloop_customer` and `base.group_portal`. Privileged group injections are rejected and stripped.
6. **Audit Trail:** Successful and duplicate registration attempts generate audit records.

---

## Password Policy

All passwords set or updated in Brightloop must meet the following policy (`res.users._validate_password_policy`):
- **Length:** Must contain **more than eight characters** (minimum 9 characters).
- **Uppercase:** At least one uppercase letter (`A-Z`).
- **Lowercase:** At least one lowercase letter (`a-z`).
- **Special Character:** At least one non-alphanumeric special character (e.g., `!@#$%^&*`).
- **Storage:** Passwords are never stored in plaintext. They are salted and hashed using Odoo's native crypt context (PBKDF2-SHA512).

---

## Password Reset Workflow

```
[Customer / Staff]
        │
        ▼ 1. Request Reset (Email)
[brightloop.auth.service]
        │
        ├── 2. Anti-Enumeration: Identical response returned regardless of email existence
        │
        ├── 3. Rate Limit Check: Max 3 requests in 15 minutes per user
        │
        ├── 4. Token Generation: secrets.token_urlsafe(32) (256-bit entropy)
        │
        ├── 5. Hashed Storage: SHA-256 hash stored in brightloop.password.reset.token
        │                      Plaintext token is NEVER persisted to disk/DB
        │
        ├── 6. Single-Use Expiration: 1-hour expiration timestamp
        │
        ▼ 7. Delivery: Sent via mail_template_password_reset template
[Customer Receives Token]
        │
        ▼ 8. Submit Token & New Password
[brightloop.auth.service.confirm_password_reset]
        │
        ├── 9. Validate Token (Hash match, expiration check, used check)
        ├── 10. Enforce Password Policy on new password
        ├── 11. Invalidate Token (used=True, used_date=now)
        ├── 12. Invalidate all other pending tokens for user
        ├── 13. Update user password via Odoo crypt context
        └── 14. Log audit event: password_reset_success
```

---

## Security Group Configuration

Groups are defined in [`security/security_groups.xml`](file:///c:/Users/AMIT%20KUSHWAHA/OneDrive/Desktop/odoo/addons/brightloop_core/security/security_groups.xml):
- `brightloop_core.module_category_brightloop`: High-level module category.
- `brightloop_core.group_brightloop_customer`: Implies `base.group_portal`.
- `brightloop_core.group_brightloop_staff`: Implies `base.group_user`.
- `brightloop_core.group_brightloop_admin`: Implies `brightloop_core.group_brightloop_staff` and `base.group_system`.

---

## ACL & Record Rule Configuration (Odoo 20 Architecture)

In Odoo 20, model permissions and row-level domain restrictions are unified in [`security/ir.access.csv`](file:///c:/Users/AMIT%20KUSHWAHA/OneDrive/Desktop/odoo/addons/brightloop_core/security/ir.access.csv):

| XML ID | Model | Group | Operations | Domain Expression |
|---|---|---|:---:|---|
| `access_brightloop_security_audit_admin` | `brightloop.security.audit` | Administrator | `crud` | *(None — full model access)* |
| `access_brightloop_password_reset_token_admin` | `brightloop.password.reset.token` | Administrator | `crud` | *(None — full model access)* |
| `access_brightloop_customer_record_admin` | `brightloop.customer.record` | Administrator | `crud` | *(None — full model access)* |
| `access_brightloop_customer_record_staff` | `brightloop.customer.record` | Staff | `crud` | *(None — operational access)* |
| `access_brightloop_customer_record_customer` | `brightloop.customer.record` | Customer | `r` | `[('partner_id', '=', user.partner_id.id)]` |

### Customer Data Isolation Mechanism
When a customer queries `brightloop.customer.record`, the domain `[('partner_id', '=', user.partner_id.id)]` is injected into the SQL query by Odoo's ORM:
- Customer A can only see records linked to their partner record.
- Direct ORM lookup (`browse(id).read()`) on Customer B's record raises `odoo.exceptions.AccessError`.
- Customer has only read (`r`) permission; attempts to `create`, `write`, or `unlink` raise `AccessError`.

---

## Running Automated Tests

Run the complete Phase 1 + Phase 2 test suite inside the Odoo Docker container:

```bash
docker compose exec -T odoo /entrypoint.sh odoo \
  -c /etc/odoo/odoo.conf \
  -d brightloop_dev \
  -u brightloop_core \
  --test-enable \
  --test-tags brightloop_core \
  --stop-after-init
```

### Test Coverage (34 Tests, 100% Pass)
- `test_brightloop_base.py` (5 tests): Abstract mixin helpers, company currency, UTC datetime, timezone.
- `test_registration.py` (8 tests): Valid registration, missing email, duplicate email, case-insensitive duplicate, password length > 8, missing uppercase, missing lowercase, missing special char.
- `test_authentication.py` (5 tests): Valid login, case-insensitive login, invalid password, unknown email, empty credentials.
- `test_password_reset.py` (6 tests): End-to-end reset, single-use token reuse prevention, token expiration, invalid token, anti-enumeration identical response, rate limiting.
- `test_role_security.py` (5 tests): Admin creates staff, staff cannot create staff, customer cannot create staff, privilege escalation blocked, customer cannot access audit logs.
- `test_record_isolation.py` (5 tests): Customer reads own records, customer cannot read other customer's record by ID, customer cannot modify other customer's record, customer cannot create unauthorized records, staff/admin operational access.
