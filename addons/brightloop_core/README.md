# brightloop_core

**Brightloop Core** is the foundational Odoo addon for the Brightloop Subscription Intelligence platform.

---

## Architecture Overview

`brightloop_core` provides the core backend infrastructure, multi-company foundation, abstract mixins, authentication/authorization architecture, product & variant management engine, and the subscription plan engine for Brightloop.

### Key Capabilities
- `brightloop.base` — Abstract mixin providing company awareness, UTC date helpers, logging conventions, and error handling.
- `brightloop.security.audit` — Immutable audit trail of critical security, authentication, role, catalog, and subscription plan lifecycle events.
- `brightloop.password.reset.token` — Cryptographically secure single-use expiring token generator and validator (hashed storage).
- `brightloop.auth.service` — Centralized backend authentication, registration, and password recovery service.
- `brightloop.customer.record` — Partner-linked document model enforcing row-level security and customer data isolation.
- `res.users` extensions — Strict password policy validation, customer registration service, admin-only staff provisioning, and privilege escalation protection.
- `product.template` & `product.product` extensions — Catalog integrity constraints, role-based modification controls, lifecycle protection (archival preferred over deletion), and audit logging.
- `brightloop.pricing.service` — Deterministic, currency-aware variant price calculation engine preventing double-application of attribute surcharges.
- `brightloop.subscription.plan` — Reusable subscription plan engine with calendar-aware billing frequencies, variant pricing integration, minimum quantity validation, availability windows, and configurable lifecycle policies.

---

## Phase 4: Subscription Plan Engine

### Model Architecture: `brightloop.subscription.plan`
The subscription plan model encapsulates reusable commercial offering configurations:
- `name` (Char, required): Display name of the subscription plan.
- `description` (Text): Internal and customer-facing plan description.
- `active` (Boolean, default=True): Active status with archival support.
- `product_id` (Many2one `product.product`): Primary product variant linked to this plan.
- `product_ids` (Many2many `product.product`): Associated products/variants.
- `billing_interval` (Selection): `'daily'`, `'weekly'`, `'monthly'`, `'yearly'`.
- `billing_interval_count` (Integer, default=1): Number of intervals per cycle (e.g. 3 for quarterly).
- `list_price` (Monetary): Overridden or computed base sales price.
- `currency_id` (Many2one `res.currency`): Commercial currency.
- `minimum_quantity` (Float, default=1.0): Minimum purchase quantity required.
- `availability_start_date` / `availability_end_date` (Date): Commercial availability window.
- `auto_close` (Boolean, default=False): Flag indicating whether subscriptions close automatically on termination.
- `allow_early_closure` (Boolean, default=True): Flag controlling early closure permissions.
- `allow_pause` (Boolean, default=True): Flag controlling temporary suspension/pause permissions.
- `allow_renewal` (Boolean, default=True): Flag controlling subscription renewal eligibility.
- `company_id` (Many2one `res.company`): Inherited from `brightloop.base` for multi-company isolation.

---

## Billing Frequency Engine & Calendar Arithmetic

The billing calculation engine (`calculate_next_billing_date` and `calculate_billing_date`) uses Python's `dateutil.relativedelta` for calendar-exact arithmetic, avoiding approximations (such as 30 days for a month or 365 days for a year).

### Exact Calculation Semantics

| Frequency | Interval Count | Start Date | Calculated Next Date | Semantic Rule |
|---|:---:|:---:|:---:|---|
| **Daily** | 1 | `2026-10-31` | `2026-11-01` | Adds 1 calendar day |
| **Weekly** | 1 | `2026-10-31` | `2026-11-07` | Adds 7 calendar days |
| **Monthly** | 1 | `2026-10-31` | `2026-11-30` | November has 30 days (month-end clamp) |
| **Monthly (Feb non-leap)** | 1 | `2026-01-31` | `2026-02-28` | Clamped to non-leap February end |
| **Monthly (Feb leap year)** | 1 | `2024-01-31` | `2024-02-29` | Clamped to leap-year February end |
| **Yearly (Leap day)** | 1 | `2024-02-29` | `2025-02-28` | 2025 is non-leap year (adjusted to Feb 28) |
| **Quarterly (Monthly × 3)** | 3 | `2026-01-31` | `2026-04-30` | 3 calendar months forward (April end) |

---

## Plan Pricing & Product Integration

Plan pricing integrates with the Phase 3 product & variant engine:
- If a plan is associated with an Odoo product variant, `calculate_plan_price()` calls `brightloop.pricing.service.calculate_variant_price()`.
- **Zero Double Application:** Surcharges (such as the ₹560 Odoo variant surcharge) are derived strictly from the active variant combination; recalculations or multi-quantity evaluations never double-apply the extra price.
- **₹2,000 + ₹560 = ₹2,560 Calculation:**
  - Base Product Template: ₹2,000.00
  - Variant *Odoo* Attribute Surcharge: ₹560.00
  - Unit Price: ₹2,560.00
  - Quantity 2: ₹5,120.00
- **Minimum Quantity Enforcement:** Quantities below `minimum_quantity` raise a `ValidationError`.
- **Unit of Measure (UoM) Validation:** Discrete count units (Units, Pieces) reject invalid fractional quantities (e.g. 1.5 units raises `ValidationError`).

---

## Plan Availability & Lifecycle Policies

### Availability Window Rules
- Start date cannot be after end date (`availability_start_date <= availability_end_date`).
- Availability queries (`check_availability()`) reject:
  - Inactive / archived plans (`active=False`).
  - Dates prior to `availability_start_date`.
  - Dates after `availability_end_date`.
  - Plans referencing archived products or variants.

### Lifecycle Policy Methods
- `validate_early_closure()`: Verifies `allow_early_closure` (raises `UserError` if disabled).
- `validate_pause()`: Verifies `allow_pause` (raises `UserError` if disabled).
- `validate_renewal()`: Verifies `allow_renewal` (raises `UserError` if disabled).
- `auto_close`: Exposes whether subscriptions automatically terminate at the expiration condition.

---

## Phase 3: Product & Variant Management Engine

### Standard Odoo Models Reused
- `product.template` — Core product definitions (name, type, sales price, cost price, active status, attributes).
- `product.product` — Concrete product variants generated from attribute combinations.
- `product.attribute` — Attribute categories (e.g., Edition, Support Tier).
- `product.attribute.value` — Distinct attribute values (e.g., Standard, Odoo).
- `product.template.attribute.line` (PTAL) — Template-attribute configuration.
- `product.template.attribute.value` (PTAV) — Holds `price_extra` surcharges.
- `product.pricelist` & `product.pricelist.item` — Standard currency and pricelist infrastructure.

### Product Types Supported
- `'service'` — Service/Subscription offerings.
- `'consu'` — Consumable goods.
- `'combo'` — Composite bundles.

---

## User Roles & Permission Matrix

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
| **Read Subscription Plans (`brightloop.subscription.plan`)** | ❌ Forbidden (AccessError) | ✅ Read-Only | ✅ Full Access |
| **Create / Modify Subscription Plans** | ❌ Forbidden | ❌ Forbidden (AccessError) | ✅ Permitted |
| **Archive / Reactivate Subscription Plans** | ❌ Forbidden | ❌ Forbidden (AccessError) | ✅ Permitted |

---

## Security Audit Trail

The `brightloop.security.audit` model captures all system lifecycle events:
- Authentication: `customer_registration`, `staff_creation`, `login_failure`, `unauthorized_access`
- Password recovery: `password_reset_request`, `password_reset_success`
- Product catalog: `product_created`, `product_updated`, `product_archived`, `product_reactivated`, `variant_attributes_modified`, `variant_pricing_modified`
- Subscription plans: `plan_created`, `plan_updated`, `plan_archived`, `plan_reactivated`, `plan_price_modified`, `plan_interval_modified`, `plan_policy_modified`

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

### Automated Test Coverage (106 Tests, 100% Pass)
- `test_brightloop_base.py` (5 tests): Abstract mixin helpers, company currency, UTC datetime, timezone.
- `test_registration.py` (8 tests): Valid registration, missing email, duplicate email, case-insensitive duplicate, password length > 8, missing uppercase, missing lowercase, missing special char.
- `test_authentication.py` (5 tests): Valid login, case-insensitive login, invalid password, unknown email, empty credentials.
- `test_password_reset.py` (6 tests): End-to-end reset, single-use token reuse prevention, token expiration, invalid token, anti-enumeration identical response, rate limiting.
- `test_role_security.py` (5 tests): Admin creates staff, staff cannot create staff, customer cannot create staff, privilege escalation blocked, customer cannot access audit logs.
- `test_record_isolation.py` (5 tests): Customer reads own records, customer cannot read other customer's record by ID, customer cannot modify other customer's record, customer cannot create unauthorized records, staff/admin operational access.
- `test_products.py` (31 tests): Product creation, constraints, archival, reactivations, attributes, variants, pricing formulas, ₹2,000 + ₹560 = ₹2,560, single application guarantee, RBAC, cost hiding, audit logs.
- `test_subscription_plans.py` (41 tests):
  - Daily, weekly, monthly, and yearly plan creation
  - Negative price and invalid frequency validation
  - Minimum quantity and interval count validation
  - Calendar-aware daily (+1 day), weekly (+7 days), and monthly (+1 month) calculations
  - Month-end arithmetic (Jan 31 -> Feb 28/29, Mar 31 -> Apr 30)
  - Leap-year boundary calculations (Feb 29 -> Feb 28)
  - Multi-interval calculations (quarterly = 3 months)
  - Base product pricing and variant integration (₹2,000 + ₹560 = ₹2,560)
  - Single-application surcharge guarantee
  - Discrete UoM decimal precision validation
  - Plan availability windows (start date, end date, expired plans, archived plans, archived products)
  - Lifecycle policy configuration (auto_close, early closure, pause, renewal)
  - Role-based permissions (Admin CRUD, Staff read-only, Customer access denied)
  - Audit logging for plan creation, updates, price changes, policy modifications, and archival
