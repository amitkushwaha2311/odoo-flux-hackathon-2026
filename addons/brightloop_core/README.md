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
- `sale.order` & `sale.order.line` extensions — Backend Quotation & Sales Management Engine integrating product variants, subscription plans, pricing service calculations, quotation validity, commercial lifecycle workflows, and security audit trail.
- `sale.order.template` & `sale.order.template.line` extensions — Reusable quotation templates supporting subscription plans with automatic order line generation, duplicate prevention, and active product/plan verification.

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

### Billing Anchor Policy for Repeated Month-End Dates
When monthly or yearly billing is evaluated across consecutive recurring cycles:
- **Naive Incremental Addition (Date Drift):** If cycle 2 is calculated by adding 1 month to cycle 1's clamped date (`2026-02-28 + 1 month`), it yields `2026-03-28`. The billing day permanently drifts from the 31st to the 28th.
- **Anchored Calculation Policy (Standard):** Subscriptions in Phase 6 will store a persistent `billing_anchor_date` (or `billing_day_of_month = 31`). The billing date for cycle $k$ is computed from the original anchor:
  $$\text{next\_billing\_date} = \text{anchor\_date} + \text{relativedelta}(\text{months} = k \times \text{interval\_count})$$
  Under this policy:
  - Cycle 1 ($k=1$): `2026-01-31` + 1 month $\to$ `2026-02-28` (clamped)
  - Cycle 2 ($k=2$): `2026-01-31` + 2 months $\to$ `2026-03-31` (restored to 31st)
  - Cycle 3 ($k=3$): `2026-01-31` + 3 months $\to$ `2026-04-30` (clamped to 30th)
  - Cycle 4 ($k=4$): `2026-01-31` + 4 months $\to$ `2026-05-31` (restored to 31st)
This completely prevents billing date drift across recurring subscription lifetimes.

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

### Customer Plan Discovery Architecture (Future Customer-Facing Workflows)
To maintain security isolation while enabling customers to discover active, eligible plans in future sales/portal workflows:
- **Direct ORM Isolation Preserved:** Portal customers remain blocked from querying `brightloop.subscription.plan` directly via standard ORM methods, preventing field exploration, draft plan leaks, or internal parameter tampering.
- **Service-Based Discovery (`get_published_plans`):** In future customer workflows (Phase 5/portal), plans will be surfaced via a controlled service endpoint or portal controller executing with elevated backend privileges (`sudo()`) while applying strict mandatory business filters:
  1. `active = True`
  2. `availability_start_date <= today <= availability_end_date` (or unset)
  3. `product_id.active = True`
  4. Exposing only public fields (`id`, `name`, `description`, `list_price`, `currency_id`, `billing_interval`, `billing_interval_count`, `minimum_quantity`).
  5. Excluding internal company accounting configurations and audit links.

---

## Phase 5: Quotation & Sales Management Engine

### Reused Native Odoo Models
Brightloop avoids duplicating sales models by extending Odoo's standard commercial infrastructure:
- `sale.order` — Represents customer quotations and confirmed sales orders. Extended with subscription-awareness (`is_subscription_quotation`), expiration tracking (`is_expired`), date validity constraints, authorized validity extension, and commercial lifecycle workflows.
- `sale.order.line` — Represents commercial order lines. Extended with `subscription_plan_id`, billing metadata (`billing_interval`, `billing_interval_count`), minimum quantity enforcement, variant surcharge pricing via `brightloop.pricing.service`, and multi-company active product/plan guards.
- `sale.order.template` & `sale.order.template.line` — Reusable quotation templates with admin-only management, subscription plan propagation, clean line reapplication preventing duplicates, and validation against archived catalog records.

### Commercial Line Architecture & Deterministic Pricing
Quotations accommodate both one-time products and recurring subscription plans side-by-side:
- **Variant Pricing Integration:** When a subscription plan referencing a product variant is added to a quotation line, unit price is evaluated through `brightloop.pricing.service.calculate_variant_price()`.
- **Zero Double-Application Guarantee:** Surcharges (e.g. ₹560 for Odoo Edition) are derived strictly from active attribute combination lines; re-saving or modifying quantity never double-applies extras.
  - Base Platform Template: ₹2,000.00
  - Variant Attribute Surcharge: ₹560.00
  - Unit Price: ₹2,560.00
  - Quantity 2: ₹5,120.00 subtotal
- **Billing Frequency Metadata:** Subscription lines store related `billing_interval` and `billing_interval_count` from the linked plan for downstream lifecycle processing.
- **Integrity Constraints:** Prevents zero/negative quantity, negative unit prices, discount outside 0–100%, archived products, and quantities below plan minimums.

### Commercial Lifecycle & State Machine
1. **Draft (`state = 'draft'`):** Staff or Admin prepares quotation, links customer, configures lines or applies templates. Customer role is blocked from creating internal quotations.
2. **Sent (`state = 'sent'`):** Quotation communicated to customer with audit logging.
3. **Confirmed (`state = 'sale'`):** Staff/Admin confirms quotation:
   - Rejects confirmation if quotation has expired (`is_expired = True`).
   - Rejects confirmation if quotation was previously cancelled (`state = 'cancel'`).
   - Validates that all referenced products and plans remain active and within commercial availability windows.
   - Converts quotation into a confirmed Sales Order.
   - **Phase 5/6 Boundary Guarantee:** Quotation confirmation emits a `quotation_confirmed` audit event, but does **not** create or activate `brightloop.subscription` records (Phase 6 ownership).
4. **Cancelled (`state = 'cancel'`):** Cancelled quotations cannot be modified or confirmed.
5. **Modification Restrictions:** Confirmed orders cannot have their lines, customer, or currency modified by non-admin staff.

### Quotation Validity & Expiration Policy
- `validity_date` cannot be earlier than `date_order` (`_check_validity_date`).
- `is_expired` automatically evaluates to `True` when `validity_date < today` and quotation is unconfirmed (`draft` or `sent`).
- Expired quotations cannot be confirmed until an authorized Staff or Admin invokes `extend_validity(new_validity_date)`.
- Validity extension updates the date and emits an immutable `quotation_validity_extended` audit event.

### Quotation Templates
- Administrators manage templates specifying pre-configured product and subscription plan lines and default validity durations (`number_of_days`).
- Applying a template (`apply_brightloop_template`):
  - Validates that template and all referenced items are active.
  - Clears existing lines (`(5, 0, 0)`) before appending new lines, guaranteeing **zero duplicate line generation** on re-application.
  - Automatically calculates quotation `validity_date = date_order + number_of_days`.
  - Propagates terms and conditions (`note`).

---

## Project Roadmap Alignment

The Brightloop project follows an agreed modular roadmap:
- **Phase 1: Foundation & Odoo Setup** *(Completed)* — Dockerized Odoo 20 + PostgreSQL 16, `brightloop_core` base addon, `brightloop.base` mixin.
- **Phase 2: Authentication & Security** *(Completed)* — Role architecture (Admin, Staff, Customer), customer registration, password policy, secure reset tokens, audit trail.
- **Phase 3: Product & Variant Management** *(Completed)* — Product catalog reuse (`product.template`/`product.product`), validation constraints, variant pricing surcharge engine (₹2,000 + ₹560 = ₹2,560).
- **Phase 4: Subscription Plan Engine** *(Completed)* — Reusable plan model, calendar-exact billing engine, variant integration, availability windows, lifecycle policies, RBAC.
- **Phase 5: Quotations & Sales Engine** *(Completed)* — Quotation generation, customer quote presentation, staff quotation workflows, conversion to sales orders.
- **Phase 6: Subscription Lifecycle & State Machine** *(Next)* — Live subscription contracts (`brightloop.subscription`), active/paused/closed/renewed state transitions, automated closure on expiry, billing anchor day management.
- **Phase 7: Recurring Invoicing & Billing** — Recurring invoice generation, prorated calculations, tax and discount applications.
- **Phase 8: Payment Processing & Collections** — Payment gateway integration, tokenized renewals, retry logic, dunning management.

---

## Security Audit Trail

The `brightloop.security.audit` model captures all system lifecycle events:
- Authentication: `customer_registration`, `staff_creation`, `login_failure`, `unauthorized_access`
- Password recovery: `password_reset_request`, `password_reset_success`
- Product catalog: `product_created`, `product_updated`, `product_archived`, `product_reactivated`, `variant_attributes_modified`, `variant_pricing_modified`
- Subscription plans: `plan_created`, `plan_updated`, `plan_archived`, `plan_reactivated`, `plan_price_modified`, `plan_interval_modified`, `plan_policy_modified`
- Quotations & Sales: `quotation_created`, `quotation_updated`, `quotation_sent`, `quotation_confirmed`, `quotation_cancelled`, `quotation_expired`, `quotation_validity_extended`, `quotation_template_applied`, `quotation_line_added`, `quotation_line_updated`, `quotation_line_removed`

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

### Automated Test Coverage (249 Post-Tests / 100% Pass)
- `test_brightloop_base.py` (5 tests): Abstract mixin helpers, company currency, UTC datetime, timezone.
- `test_registration.py` (8 tests): Valid registration, missing email, duplicate email, case-insensitive duplicate, password length > 8, missing uppercase, missing lowercase, missing special char.
- `test_authentication.py` (5 tests): Valid login, case-insensitive login, invalid password, unknown email, empty credentials.
- `test_password_reset.py` (6 tests): End-to-end reset, single-use token reuse prevention, token expiration, invalid token, anti-enumeration identical response, rate limiting.
- `test_role_security.py` (5 tests): Admin creates staff, staff cannot create staff, customer cannot create staff, privilege escalation blocked, customer cannot access audit logs.
- `test_record_isolation.py` (5 tests): Customer reads own records, customer cannot read other customer's record by ID, customer cannot modify other customer's record, customer cannot create unauthorized records, staff/admin operational access.
- `test_products.py` (31 tests): Product creation, constraints, archival, reactivations, attributes, variants, pricing formulas, ₹2,000 + ₹560 = ₹2,560, single application guarantee, RBAC, cost hiding, audit logs.
- `test_subscription_plans.py` (42 tests):
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
  - Audit logging for plan creation, updates, price changes, policy modifications, archival, and anchor date restoration
- `test_quotations.py` (44 tests):
  - Quotation creation & customer selection: draft status, customer required, multi-company isolation (tests 01–05)
  - Product & plan lines: regular products, variants, subscription plans, archived item rejection, minimum quantity, plan-product compatibility (tests 06–12)
  - Pricing & calculations: base product pricing, variant surcharge ₹2,000 + ₹560 = ₹2,560, quantity multiplication (qty 2 = ₹5,120), currency rounding, zero double surcharge guarantee, billing interval metadata preservation (tests 13–18)
  - Quotation templates: admin template creation, single-line & multi-line application, duplicate line prevention on reapply, archived product/plan guards (tests 19–24)
  - Validity & expiration: validity date constraints, automatic expiration evaluation, expired confirmation rejection, authorized validity extension, extension audit trail (tests 25–30)
  - Commercial workflow: Draft -> Sent -> Confirmed (state='sale'), quotation cancellation, cancelled confirmation rejection, confirmed order modification restrictions, Phase 5/6 boundary guarantee ensuring NO premature subscription activation (tests 31–36)
  - Role-based security: Admin full CRUD, Staff operational quote/line management, Customer isolated from other quotes and blocked from modifying/creating internal quotations (tests 37–41)
  - Security audit logging: quotation creation, update, confirmation, cancellation, and template application event generation (tests 42–44)
- `test_subscriptions.py` (48 tests):
  - Creation & quotation conversion: confirmed quotation conversion, regular product exclusion, multi-line conversion, customer preservation, draft confirmation guards, duplicate prevention, database uniqueness constraint (tests 01–08)
  - State machine & action methods: Draft -> Confirmed -> Active <-> Paused -> Closed, direct state modification prevention via write guard (tests 09–16)
  - Activation & billing schedule: calendar-aware next billing computation, future start dates, repeated activation guard, archived plan/product guards (tests 17–21)
  - Pause & resume policy: active-to-paused transition, pause duration calculation, billing date extension, unpauseable plan restriction, duplicate pause/resume rejection (tests 22–27)
  - Closure & automatic closure: early closure enforcement, restriction when allow_early_closure=False, daily cron auto-close execution, idempotency, future end date protection (tests 28–33)
  - Subscription renewal: renewal lineage tracking, renewal_count increment, start/end date calculation, closed original contract, renewal restriction enforcement (tests 34–38)
  - Lifecycle audit & history immutability: transition event capture, write/unlink modification block, tamper resistance (tests 39–43)
  - Role-based access control: Admin full CRUD, Staff operational management, Customer own-record read isolation, Customer blocked from modifying, creating, or calling lifecycle actions (tests 44–48)
- `test_taxes_and_discounts.py` (50 tests):
  - Tax configuration: percentage tax, fixed fee, tax activation, archival, company isolation, staff/customer modification restrictions (tests 01–06)
  - Tax calculation service: tax-exclusive calculation, tax-inclusive calculation, intra-state multiple taxes (CGST+SGST), mixed percentage & fixed fee, quantity multiplier, zero taxes, duplicate tax guard (tests 07–13)
  - GST support & fiscal positions: inter-state fiscal position mapping (CGST+SGST -> IGST), named GST breakdown, avoidance of simultaneous intra/inter-state tax application (tests 14–16)
  - Discount model & constraints: percentage discount, fixed discount, negative value rejection, >100% rejection, date range validation, negative threshold validation (tests 17–22)
  - Discount eligibility engine: active discount, inactive rejection, pre-start date rejection, post-expiry rejection, minimum purchase amount threshold, minimum quantity threshold, product-specific scope, category-specific scope, subscription plan scope, exhausted usage limit rejection (tests 23–32)
  - Discount calculation: 10% of ₹2,000 = ₹200 (net ₹1,800), fixed ₹250 on ₹2,000 = ₹1,750, maximum discount amount cap (₹400 cap on ₹1,000 raw discount), zero-floor negative protection, quantity multiplier (qty 3 = ₹600 discount), stacking priority rules (tests 33–38)
  - Quotation integration: discount applied to quotation line, ineligible discount rejection, tax computation on post-discount taxable base (₹1,800 * 18% = ₹324) (tests 39–41)
  - Subscription integration: subscription line receives discount_id and computes tax automatically, recurring discount revalidation detects future expiry, boundary guarantee: zero account.move invoice generation (tests 42–44)
  - Usage limits & concurrency protection: atomic usage increment, strict ceiling enforcement at usage limit, quotation confirmation usage consumption (tests 45–47)
  - Security & audit logging: Admin CRUD vs Staff read-only, Customer access blocked, security audit log generation for discount creation and rejection (tests 48–50)

---

## Phase 7: Tax & Discount Management Engine Architecture

### 1. Reused Native Accounting & Tax Models
- **`account.tax`**: Official Odoo tax computation engine (percentage, fixed, group taxes, tax inclusion/exclusion, sequence, repartition lines).
- **`account.tax.group`**: Aggregates related tax lines into reporting groups (e.g. GST, VAT, Cess).
- **`account.fiscal.position`**: Maps default domestic product taxes to destination taxes (e.g. mapping intra-state CGST 9% + SGST 9% to inter-state IGST 18%).
- **`account`**: Added as an official dependency in `__manifest__.py`.

### 2. Dedicated Brightloop Discount Model (`brightloop.discount`)
- **Fields**: `name`, `description`, `active`, `discount_type` (percentage/fixed), `discount_value`, `maximum_discount_amount`, `minimum_purchase_amount`, `minimum_quantity`, `start_date`, `end_date`, `usage_limit`, `usage_count`, `application_scope` (all, product, category, subscription_plan), `product_ids`, `product_category_ids`, `subscription_plan_ids`, `stackable`, `priority`, `company_id`, `currency_id`.
- **Concurrency & Usage Protection**: Uses raw database-level `SELECT usage_count, usage_limit FROM brightloop_discount WHERE id = %s FOR UPDATE` to atomically lock discount records before incrementing, guaranteeing zero concurrent over-redemption beyond the configured limit.
- **Consumption Business Rule**: Usage is consumed when an order containing the discount is **confirmed** (`action_confirm()`) or when a recurring subscription invoice is generated. If the enclosing database transaction fails or is rolled back, the usage increment is aborted automatically.

### 3. Reusable Services
- **`brightloop.tax.service`** (AbstractModel):
  - Wraps Odoo's native `account.tax.compute_all()` API.
  - Computes taxes for products, subscription plans, quotation lines (`sale.order.line`), and subscription lines (`brightloop.subscription.line`).
  - Supports tax-exclusive and tax-inclusive pricing with currency rounding.
  - Provides `get_gst_breakdown()` helper returning named GST line items.
- **`brightloop.discount.service`** (AbstractModel):
  - Deterministic eligibility check (`check_eligibility()`): validates active status, date windows, minimum purchase amount, minimum quantity, scope (product/category/plan), usage limit, and company/currency compatibility.
  - Multi-discount application (`apply_discounts()`): enforces priority order, applies non-stackable discount first, chains stackable discounts on remaining balances, enforces maximum caps, and floors line subtotals at zero.
  - Recurring discount validator (`validate_recurring_discount()`): re-evaluates discount eligibility for future billing cycles before Phase 8 invoice generation.

### 4. Calculation Order
1. Base unit price resolved from product variant / pricing service.
2. Gross line total computed: `gross = price_unit * quantity`.
3. Eligible discounts identified via `brightloop.discount.service.check_eligibility()`.
4. Highest priority non-stackable discount applied, followed by stackable discounts on the post-discount base. Caps applied, floored at ₹0.00.
5. Taxable base established (`price_subtotal`).
6. Native `account.tax.compute_all()` calculates applicable taxes (respecting fiscal position mapping).
7. Final line total computed (`price_total = price_subtotal + tax_amount`).

### 5. Statutory Configuration Disclaimer
Brightloop calculates taxes according to the tax rates, sequences, repartition lines, and fiscal positions configured by the system administrator. It does not certify statutory tax compliance. All GST / VAT rates and accounting mappings must be configured and reviewed by certified tax professionals.
