# brightloop_core

**Brightloop Core** is the foundational Odoo addon for the Brightloop Subscription Intelligence platform.

---

## Architecture Overview

`brightloop_core` provides the core backend infrastructure, multi-company foundation, abstract mixins, authentication/authorization architecture, and the product & variant management engine for Brightloop.

### Key Capabilities
- `brightloop.base` — Abstract mixin providing company awareness, UTC date helpers, logging conventions, and error handling.
- `brightloop.security.audit` — Immutable audit trail of critical security, authentication, role, and product catalog lifecycle events.
- `brightloop.password.reset.token` — Cryptographically secure single-use expiring token generator and validator (hashed storage).
- `brightloop.auth.service` — Centralized backend authentication, registration, and password recovery service.
- `brightloop.customer.record` — Partner-linked document model enforcing row-level security and customer data isolation.
- `res.users` extensions — Strict password policy validation, customer registration service, admin-only staff provisioning, and privilege escalation protection.
- `product.template` & `product.product` extensions — Catalog integrity constraints, role-based modification controls, lifecycle protection (archival preferred over deletion), and audit logging.
- `brightloop.pricing.service` — Deterministic, currency-aware variant price calculation engine preventing double-application of attribute surcharges.

---

## Phase 3: Product & Variant Management Engine

### Standard Odoo Models Reused
Brightloop leverages Odoo's native product infrastructure rather than introducing redundant custom models:
- `product.template` — Core product definitions (name, type, sales price, cost price, active status, attributes).
- `product.product` — Specific product variants generated from attribute combinations.
- `product.attribute` — Attribute categories (e.g., Edition, Support Tier, Deployment Mode).
- `product.attribute.value` — Distinct attribute values (e.g., Standard, Pro, Enterprise, Odoo).
- `product.template.attribute.line` (PTAL) — Template-specific attribute configurations.
- `product.template.attribute.value` (PTAV) — Per-template attribute value mappings holding `price_extra`.
- `product.pricelist` & `product.pricelist.item` — Standard currency and pricelist infrastructure.

### Product Types Supported
- `'service'` — Service/Subscription offerings (compute licenses, SaaS subscriptions, consulting services).
- `'consu'` — Consumable goods (hardware authentication keys, physical backup media).
- `'combo'` — Composite bundles combining multiple products.

### Data Integrity Constraints
- **Product Name:** Required; empty or whitespace-only names raise `ValidationError`.
- **Sales Price (`list_price`):** Cannot be negative (`list_price >= 0.0`).
- **Cost Price (`standard_price`):** Cannot be negative (`standard_price >= 0.0`).
- **Currency Validation:** Product currency must be active.
- **Availability Enforcement:** `check_available_for_sale()` ensures archived products cannot be included in sales operations.

---

## Variant Pricing Engine

Variant pricing is managed by `brightloop.pricing.service`:

$$\text{effective\_price} = \text{base\_template\_price} + \sum \text{price\_extra}$$

### Pricing Rules & Guarantees
1. **Deterministic Calculation:** Pricing strictly follows the template base price plus the sum of variant attribute extras (`product.template.attribute.value.price_extra`).
2. **Single-Application Guarantee:** Surcharges are computed directly from the active variant combination; surcharges are never applied twice or compounded across calculations.
3. **Currency Precision:** The result is rounded using `currency.round()` according to the active currency precision (e.g., 2 decimal places for INR/USD/EUR).
4. **Availability Verification:** Attempting to price an inactive or archived variant or template raises a `UserError`.

### Example Calculation: SaaS Edition Plan
- **Template Base Price (`list_price`):** ₹2,000.00
- **Attribute:** *Edition*
  - Value *Standard*: `price_extra = 0.0` → **Effective Price:** ₹2,000.00
  - Value *Odoo*: `price_extra = 560.0` → **Effective Price:** ₹2,560.00 (₹2,000.00 + ₹560.00)
- **Detailed Price Breakdown API:**
  `brightloop.pricing.service.get_variant_price_breakdown(variant)` provides a structured audit dictionary with base price, attribute extra breakdown, currency symbol, and effective price.

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

### Comprehensive Permission Matrix

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
| **Read Product Catalog (`product.template`)** | ❌ Forbidden | ✅ Read-Only | ✅ Full Access |
| **Create / Modify Products & Prices** | ❌ Forbidden | ❌ Forbidden (AccessError) | ✅ Permitted |
| **Read Product Cost (`standard_price`)** | ❌ Hidden (`base.group_user`) | ✅ Permitted | ✅ Full Access |
| **Configure Attributes & Variants** | ❌ Forbidden | ❌ Forbidden | ✅ Permitted |
| **Archive / Reactivate Products** | ❌ Forbidden | ❌ Forbidden | ✅ Permitted |

---

## Product Lifecycle & Deletion Protection

To protect financial integrity and transaction history:
1. **Permanent Deletion Protection (`unlink`):** Products referenced in customer records or historical transactions cannot be permanently deleted. Attempting deletion raises `UserError` instructing the user to archive the product instead.
2. **Archival (`active = False`):** Archival removes the product from active operational searches while preserving historical integrity.
3. **Reactivation (`active = True`):** Archived products can be reactivated by administrators.
4. **Audit Trail:** Every product creation, modification, archival, and reactivation logs an immutable record in `brightloop.security.audit`.

---

## Security Audit Trail

The `brightloop.security.audit` model captures key catalog and security lifecycle events:
- `login_success` / `login_failure`
- `customer_registration`
- `staff_creation`
- `password_reset_request` / `password_reset_success`
- `privilege_escalation_attempt`
- `unauthorized_access`
- `product_created`
- `product_updated`
- `product_archived`
- `product_reactivated`
- `variant_attributes_modified`
- `variant_pricing_modified`

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

## Running Automated Tests

Run the complete test suite inside the Odoo Docker container:

```bash
docker compose exec -T odoo /entrypoint.sh odoo \
  -c /etc/odoo/odoo.conf \
  -d brightloop_dev \
  -u brightloop_core \
  --test-enable \
  --test-tags brightloop_core \
  --stop-after-init
```

### Automated Test Coverage (65 Tests, 100% Pass)
- `test_brightloop_base.py` (5 tests): Abstract mixin helpers, company currency, UTC datetime, timezone.
- `test_registration.py` (8 tests): Valid registration, missing email, duplicate email, case-insensitive duplicate, password length > 8, missing uppercase, missing lowercase, missing special char.
- `test_authentication.py` (5 tests): Valid login, case-insensitive login, invalid password, unknown email, empty credentials.
- `test_password_reset.py` (6 tests): End-to-end reset, single-use token reuse prevention, token expiration, invalid token, anti-enumeration identical response, rate limiting.
- `test_role_security.py` (5 tests): Admin creates staff, staff cannot create staff, customer cannot create staff, privilege escalation blocked, customer cannot access audit logs.
- `test_record_isolation.py` (5 tests): Customer reads own records, customer cannot read other customer's record by ID, customer cannot modify other customer's record, customer cannot create unauthorized records, staff/admin operational access.
- `test_products.py` (31 tests):
  - Product creation and type handling (`service`, `consu`)
  - Validation constraints (required name, non-negative sales price, non-negative cost price)
  - Lifecycle operations (archival, reactivation, deletion protection)
  - Product attribute and multi-variant generation (single and multiple attributes)
  - Pricing calculation (base price ₹2,000, zero surcharge, ₹560 surcharge = ₹2,560)
  - Single-application pricing guarantee (no double application of extra charges)
  - Multi-attribute cumulative pricing
  - Transparent pricing breakdown service
  - Role-based access control (Admin CRUD, Staff read-only, Customer access denial)
  - Product cost price masking for unauthorized roles
  - Audit logging for product creation, modification, price change, and archival
