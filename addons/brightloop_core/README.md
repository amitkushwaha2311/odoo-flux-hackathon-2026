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


---

## Phase 8: Automated Recurring Invoicing & Billing Engine

### 1. Overview & Architectural Principles
Phase 8 implements a high-throughput, idempotent, automated recurring billing engine directly atop Odoo's native accounting (`account.move` and `account.move.line`) and tax calculation infrastructure.

Key capabilities:
- **`brightloop.billing.period`**: Dedicated contract billing cycle model guaranteeing 1:1 traceability between subscription cycles and generated customer invoices.
- **`brightloop.billing.service`**: Stateless business service orchestrating due discovery, gapless period calculation, atomic invoice generation, tax/discount application, schedule progression, and multi-cycle missed period recovery.
- **Native Odoo `account.move` Integration**: Generates official `out_invoice` records with `is_subscription_invoice=True`, linking header and lines directly back to the subscription contract.
- **PostgreSQL-Level Idempotency**: Hard schema constraint `UNIQUE (idempotency_key)` on format `sub_{subscription_id}_{start_date}_{end_date}` prevents duplicate period creation even across concurrent threads.
- **Row-Level Concurrency Protection**: Acquires `SELECT ... FOR UPDATE` locks on subscriptions during billing evaluation, eliminating race conditions.
- **Gapless Period Chaining**: Periods chain continuously (`next_start = prior_end + 1 day`) while preserving calendar anchor dates (e.g. 31st across Feb/Apr/Jun/Sep/Nov).
- **Real-Time Tax & Discount Revalidation**: Queries live product taxes (`product.taxes_id`) and verifies discount validity/usage limits at invoice time, consuming discount usage atomically.
- **Automated Missed Billing Catchup**: Iterates sequentially through multiple overdue cycles in historical order without skips or overlaps.
- **Bounded Retries with Failure Isolation**: Caps automatic retries at 3 with detailed failure reasons and provides authorized manual retry (`action_retry()`).
- **Scheduled Actions (`ir.cron`)**: Automated daily billing batch execution and periodic retry of failed cycles.
- **Role-Based Security & Audit**: Full Admin CRUD, Staff operational access + manual retry, Customer portal read isolation (own partner records only), and 9 dedicated audit event types.

---

### 2. Billing Engine Workflow

```mermaid
flowchart TD
    A["Scheduled Cron / Manual Trigger"] --> B["get_due_subscriptions(target_date)"]
    B --> C["Filter: state == 'active' & next_billing_date <= target_date"]
    C --> D["Acquire SELECT ... FOR UPDATE Lock"]
    D --> E["calculate_billing_period() — Gapless Chain & Anchor"]
    E --> F["create_or_get_billing_period() — Idempotency Key Guard"]
    F --> G{"Already Invoiced?"}
    G -- "Yes" --> H["Return Existing invoice_id (Idempotent)"]
    G -- "No" --> I["generate_invoice()"]
    I --> J["Revalidate Discounts & Consume Usage Atomically"]
    I --> K["Compute Real-Time Taxes from product.taxes_id"]
    I --> L["Create Native account.move (out_invoice) & lines"]
    L --> M["Update Billing Period: status='invoiced', amounts"]
    M --> N["Advance Subscription: last_billing_date & next_billing_date"]
    N --> O["Log Security Audit Events & Lifecycle History"]
    I -- "Exception" --> P["Savepoint Rollback & Record failure_reason, retry_count++"]
```

---

### 3. Reused Native Accounting Models

| Native Model | Extension Purpose in Brightloop |
|---|---|
| `account.move` | Augmented with `is_subscription_invoice`, `subscription_id`, `billing_period_id`, `billing_period_start`, and `billing_period_end`. |
| `account.move.line` | Augmented with `subscription_id` and `subscription_line_id` for granular line-level revenue traceability. |
| `account.tax` | Evaluated dynamically at invoice creation time via `product_id.taxes_id` supporting tax-inclusive, tax-exclusive, and CGST/SGST splits. |
| `account.journal` | Automatic resolution of company sales journal (`type='sale'`). |

---

### 4. Billing Period Model (`brightloop.billing.period`)

- **Fields**:
  - `subscription_id` (Many2one `brightloop.subscription`, required, cascade)
  - `customer_id` (Many2one `res.partner`, required)
  - `company_id` (Many2one `res.company`, required, default current company)
  - `currency_id` (Many2one `res.currency`, required)
  - `billing_period_start` (Date, inclusive start of cycle)
  - `billing_period_end` (Date, inclusive end of cycle)
  - `billing_date` (Date, invoice/due date)
  - `billing_interval` & `billing_interval_count` (inherited from subscription plan)
  - `status` (`pending`, `processing`, `invoiced`, `failed`, `skipped`, `cancelled`)
  - `invoice_id` (Many2one `account.move`, readonly link to customer invoice)
  - `retry_count` (Integer, capped at 3 for automatic processing)
  - `last_attempt_date` (Datetime)
  - `failure_reason` (Text)
  - `idempotency_key` (Char, unique deterministic key)
  - `amount_untaxed`, `amount_tax`, `amount_total` (Monetary)
- **PostgreSQL Constraints**:
  - `brightloop_billing_period_idempotency_key_uniq`: `UNIQUE (idempotency_key)`
  - `brightloop_billing_period_period_range_uniq`: `UNIQUE (subscription_id, billing_period_start, billing_period_end)`

---

### 5. Automated Scheduled Jobs

1. **`ir_cron_process_due_billing`**:
   - Model: `brightloop.billing.period`
   - Code: `model._cron_process_due_billing()`
   - Interval: Daily (1 Day)
   - Function: Discovers active subscriptions due for billing and processes them in bounded batches with transaction savepoint failure isolation.
2. **`ir_cron_retry_failed_billing`**:
   - Model: `brightloop.billing.period`
   - Code: `model._cron_retry_failed_periods()`
   - Interval: 4 Hours
   - Function: Automatically retries failed billing periods whose `retry_count < 3`.

---

### 6. Phase 8 Test Suite Coverage (`test_billing_engine.py` — 33 Tests)

1. **Billing Period Calculation (Tests 01–06)**:
   - Daily gapless 1-day windows
   - Weekly 7-day inclusive windows
   - Monthly full-calendar calculation
   - Quarterly 3-month calculation
   - Annual 365/366-day calculation
   - Gapless chaining from prior period end date without time drift
2. **Invoice Generation & Traceability (Tests 07–12)**:
   - Generation of native `account.move` (`out_invoice`) with matching customer, company, currency
   - Brightloop backlink fields (`is_subscription_invoice`, `subscription_id`, `billing_period_id`)
   - Granular invoice line traceability to `subscription_line_id`
   - Strict exclusion/skipping of paused, closed, and draft contracts
   - Multi-line subscription invoicing with accurate line totals
3. **Tax Integration (Tests 13–15)**:
   - Tax-exclusive 18% GST (base ₹1,500 + tax ₹270 = ₹1,770)
   - Tax-inclusive 18% GST (base ₹1,271.19 + tax ₹228.81 = ₹1,500)
   - Intra-state CGST 9% + SGST 9% split (base ₹1,500 + ₹135 + ₹135 = ₹1,770)
4. **Discount Revalidation & Usage (Tests 16–19)**:
   - Recurring percentage discount application (10% off ₹1,500 = ₹1,350 untaxed)
   - Expired discount rejection during recurring revalidation (full price ₹1,500 invoiced)
   - Exhausted usage limit discount rejection (full price ₹1,500 invoiced)
   - Atomic usage increment upon successful invoice creation (`usage_count` 0 → 1)
5. **Idempotency & Duplicate Prevention (Tests 20–22)**:
   - PostgreSQL unique constraint rejection of duplicate idempotency keys
   - Idempotent service execution returning existing invoice for already-invoiced periods
   - Batch exclusion of subscriptions not yet due
6. **Missed Billing Recovery (Tests 23–24)**:
   - Multi-cycle overdue recovery generating 3 consecutive invoices for 3 missed months
   - Strict gapless boundary continuity across recovered periods
7. **Retries & Error Recovery (Tests 25–27)**:
   - Failure tracking with status, error reason, and attempt timestamp
   - Authorized manual retry via `action_retry()` successfully recovering failed periods
   - Cron retry boundary excluding periods reaching maximum 3 retries
8. **Billing Schedule Advancement (Tests 28–29)**:
   - Exact advancement of `last_billing_date` and `next_billing_date` upon success
   - Billing anchor day preservation across shorter months (Jan 31 → Feb 28 → Mar 31)
9. **Role-Based Security & Audit Trail (Tests 30–32)**:
   - Customer portal read isolation (customers can view only their own billing periods)
   - Security audit logging for 9 Phase 8 event types
   - Duplicate attempt detection and `billing_duplicate_prevented` audit logging
10. **Performance Benchmark (Test 33)**:
    - 1,000 active subscriptions processed in an automated batch run.
    - Verified 0 failures, 0 duplicate billing periods, and 100% billing date advancement.

---

## Phase 9: Payment & Reconciliation Engine

### 1. Overview & Architectural Principles
Phase 9 delivers a robust, idempotent, and auditable payment registration and reconciliation engine built directly on Odoo 20 Community Edition's native accounting framework (`account.payment`, `account.move`, `account.move.line`, and `account.partial.reconcile`).

Key architectural principles:
- **Zero Parallel Accounting**: Reuses native Odoo journal entries and payment mechanisms rather than creating custom ledger records.
- **Native Residual State Authority**: `amount_residual` and `payment_state` on `account.move` remain the authoritative computed source of truth; no manual state overwriting.
- **Atomic Two-Sided Reconciliation**: Payments and customer invoices are reconciled via native receivable line matching (`js_assign_outstanding_line`), immediately updating invoice residuals.
- **Partial Payment & Allocation**: Fully supports multiple partial payments against an invoice (e.g. ₹4,000 + ₹3,000 + ₹3,000 = ₹10,000) and multi-invoice settlement from a single payment.
- **PostgreSQL Idempotency**: Hard schema constraint `UNIQUE (idempotency_key)` on `account.payment` prevents duplicate payment processing at the database level.
- **Subscription Contract Traceability**: Automatically links customer payments to source subscriptions (`brightloop.subscription`) and billing periods (`brightloop.billing.period`).
- **Overdue Management**: Discovers overdue invoices based on real-time due date, posted status, and residual amount, excluding settled or future-due invoices.
- **Reversal & Refund Consistency**: Reverses payments safely via `payment.action_cancel()`, unlinking journal entries, unreconciling moves, and restoring original invoice residuals with full audit tracking.

---

### 2. Native Odoo Models Reused
| Native Model | Brightloop Phase 9 Role |
|---|---|
| `account.payment` | Core inbound customer payment record extended with `subscription_id`, `billing_period_id`, and `idempotency_key`. |
| `account.move` | Customer invoice (`out_invoice`) whose `amount_residual` and `payment_state` are automatically updated by reconciliation. |
| `account.move.line` | Journal items (debit/credit) reconciled via `js_assign_outstanding_line()` on receivable lines. |
| `account.journal` | Bank and Cash journals (`type in ('bank', 'cash')`) used to process payments. |
| `account.partial.reconcile` | Native reconciliation records tracking matched amounts between payments and invoices. |

---

### 3. Payment Service API (`brightloop.payment.service`)
Stateless business service coordinating financial transactions:
- `validate_payment_request(invoices, amount, partner, journal, currency, company)`: Validates positive amounts, posted invoice states, non-exceedance of residuals, customer match, and company/currency compatibility.
- `register_payment(invoice_ids, amount, journal_id, payment_date, memo, partner_id, currency_id, company_id, idempotency_key)`: Transactional payment creation, posting, reconciliation, and audit logging with duplicate protection.
- `get_outstanding_balance(invoice)`: Queries current `amount_residual` with customer partner isolation.
- `get_invoice_payment_status(invoice)`: Structured summary including total, residual, paid state, overdue flag, and payment breakdown.
- `get_customer_payment_history(partner, company, limit)`: Historical customer payment records enforced by customer isolation.
- `get_subscription_payment_history(subscription, limit)`: Contract-linked payment records.
- `get_overdue_invoices(company, target_date, limit)`: Identifies posted unpaid/partially paid invoices past due date.
- `reverse_payment(payment, reason)`: Admin-only cancellation restoring invoice balances.

---

### 4. Phase 9 Test Suite Coverage (`test_payment_engine.py` — 34 Tests)
1. **Payment Registration (Tests 01–08)**:
   - Full payment registration and posting with transition to `paid`
   - Bidirectional linkage via `reconciled_invoice_ids`
   - Strict rejection of zero and negative amounts
   - Customer partner mismatch validation
   - Draft and cancelled invoice rejection
   - Cash journal payment support
   - Rejection of payments against already fully settled invoices
2. **Partial Payments & Multi-Invoice Allocation (Tests 09–12)**:
   - Single partial payment leaving exact residual (₹4,000 on ₹10,000 leaves ₹6,000)
   - Multi-step partial payments accumulating to full settlement (₹4,000 + ₹3,000 + ₹3,000 = ₹10,000)
   - Prevention of payment amounts exceeding outstanding invoice residual
   - Single payment allocated across multiple invoices (₹10,000 settling ₹4,000 and ₹6,000 invoices simultaneously)
3. **Outstanding Balance & Payment Status (Tests 13–14)**:
   - `get_outstanding_balance` exact tracking across invoice lifecycle
   - Structured metadata validation via `get_invoice_payment_status`
4. **Subscription Traceability & History (Tests 15–17)**:
   - Automated payment linkage to `brightloop.subscription`
   - Subscription contract payment history extraction
   - Customer payment history extraction
5. **Overdue Invoice Management (Tests 18–21)**:
   - Detection of past-due unpaid invoices with days overdue calculation
   - Strict exclusion of fully paid invoices from overdue lists
   - Strict exclusion of future-due invoices from overdue lists
   - Accurate residual reporting for partially paid overdue invoices
6. **Payment Reversal / Refunds (Tests 22–24)**:
   - Native payment cancellation restoring invoice residual and `not_paid` state
   - Role-based restriction: Staff and Customer blocked from reversing payments
   - UserError raised when attempting to reverse already cancelled payments
7. **Role-Based Security & Isolation (Tests 25–28)**:
   - Customer portal users blocked from registering payments directly
   - Customer partner isolation preventing viewing other customers' payment histories
   - Customer partner isolation preventing viewing other customers' invoice payment statuses
   - Cross-company payment rejection (mismatched journal company)
8. **Audit Trail Logging (Tests 29–31)**:
   - `payment_registered`, `payment_reconciled`, and `payment_settled` audit event logging
   - `payment_partial` audit event logging on partial settlement
   - `payment_reversed` audit event logging on administrative reversal
9. **Idempotency & Duplicate Protection (Tests 32–33)**:
   - Repeated payment request with same idempotency key returns existing payment without double charging
   - PostgreSQL `UNIQUE (idempotency_key)` constraint rejects duplicate keys at SQL level
10. **Performance Benchmark (Test 34)**:
    - 100 customer invoices created, posted, and settled with 100 distinct payments.
    - Achieved throughput: **3.3 payments/second** (100 payments in 30.16s), 100% success rate, 0 failures.

---

### 5. Known Limitations
- **No External Gateway Tokens**: Phase 9 implements backend accounting payment registration and reconciliation using native Odoo journals (Bank/Cash). Online payment gateways (Stripe, Razorpay) and card tokenization are deferred to future integration phases.
- **Manual Payment Method Lines**: Bank and Cash journals use standard manual payment methods in Odoo Community Edition.

---

## Phase 10: Customer Self-Service Portal (Backend Engine)

### 1. Overview & Architectural Principles
Phase 10 delivers a secure, multi-tenant customer self-service backend engine enabling authenticated portal customers to view and manage their subscriptions, retrieve invoices, download rendered PDF documents, inspect payment histories, and access consolidated chronological billing timelines.

Key architectural principles:
- **Backend-Only Execution**: Strictly backend services, models, access controls, controllers, and tests. No HTML, OWL, SCSS, or frontend portal screens.
- **Commercial Partner Authority**: Customer identity resolves strictly to `user.partner_id.commercial_partner_id`, ensuring company-level isolation across parent-child contact structures.
- **Zero Object ID Enumeration**: Any attempt to access subscriptions, invoices, or payments belonging to other commercial partners raises a uniform `AccessError` ("not found or access denied") preventing existence probing.
- **Plan Lifecycle Policy Enforcement**: Mutation operations (`pause`, `resume`, `request_early_closure`, `renew`) strictly enforce subscription plan flags (`allow_pause`, `allow_early_closure`, `allow_renewal`).
- **Autonomous Audit Persistence**: Unauthorized access attempts and rate limit violations write audit records via autonomous database transactions (`self.env.registry.cursor()`), ensuring durable security logging even when the caller's transaction is rolled back by an `AccessError` or `UserError`.
- **Sliding-Window Abuse Protection**: Mutation endpoints are protected by in-memory sliding-window rate limiters preventing brute-force and rapid spamming.
- **Native Odoo Document Generation**: Invoice PDFs are rendered through Odoo's native `ir.actions.report._render_qweb_pdf('account.account_invoices', [invoice.id])`.

---

### 2. Service Architecture (`brightloop.portal.service`)
The `brightloop.portal.service` model coordinates customer self-service capabilities:

| Method | Access Scope | Functional Responsibility |
|---|---|---|
| `get_profile(user)` | Customer | Retrieves sanitized contact details (`name`, `email`, `phone`, `street`, `city`, `zip`, `country`, `company`). |
| `update_profile(vals, user)` | Customer | Updates permitted contact fields with format validation; rejects restricted accounting/security fields. |
| `list_subscriptions(domain, limit, offset, user)` | Customer | Lists active/historical subscriptions isolated to commercial partner. |
| `get_subscription_detail(sub_id, user)` | Customer | Detailed view with contract lines, pricing, next billing dates, and policy flags. |
| `pause_subscription(sub_id, user)` | Customer | Pauses active subscription if `allow_pause=True`; rate-limited & audited. |
| `resume_subscription(sub_id, user)` | Customer | Resumes paused subscription back to active; rate-limited & audited. |
| `request_early_closure(sub_id, reason, user)` | Customer | Transitions active subscription to closed if `allow_early_closure=True`. |
| `renew_subscription(sub_id, user)` | Customer | Creates replacement confirmed subscription if `allow_renewal=True`. |
| `list_invoices(domain, limit, offset, user)` | Customer | Retrieves posted customer invoices (`out_invoice`) with residual and payment state. |
| `get_invoice_detail(inv_id, user)` | Customer | Detailed invoice metadata including line items, taxes, residuals, and payment status. |
| `get_invoice_pdf(inv_id, user)` | Customer | Generates binary PDF document stream using native Odoo reporting. |
| `list_payments(domain, limit, offset, user)` | Customer | Lists inbound customer payments linked to commercial partner. |
| `get_payment_detail(pay_id, user)` | Customer | Detailed payment record including allocated invoices, reconciliation status, and amounts. |
| `get_billing_timeline(subscription_id, limit, user)` | Customer | Consolidated chronological event stream (subscriptions, billing periods, invoices, payments). |
| `_check_rate_limit(action, user, max_reqs, window)` | Internal | Sliding-window threshold verification. |
| `_log_unauthorized_audit(event_type, summary, details)` | Internal | Autonomous cursor audit logging surviving exception rollbacks. |

---

### 3. REST API Controllers (`/api/v1/portal/*`)
Standardized JSON endpoints exposed with session-based authentication (`auth='user'`):
- `GET /api/v1/portal/profile` — Contact profile details.
- `PUT /api/v1/portal/profile` — Whitelisted contact profile update.
- `GET /api/v1/portal/subscriptions` — Filtered subscription list.
- `GET /api/v1/portal/subscriptions/<id>` — Granular subscription contract details.
- `POST /api/v1/portal/subscriptions/<id>/pause` — Pause subscription.
- `POST /api/v1/portal/subscriptions/<id>/resume` — Resume subscription.
- `POST /api/v1/portal/subscriptions/<id>/close` — Request early contract closure.
- `POST /api/v1/portal/subscriptions/<id>/renew` — Contract renewal.
- `GET /api/v1/portal/invoices` — Customer invoice listing.
- `GET /api/v1/portal/invoices/<id>` — Invoice breakdown and residual state.
- `GET /api/v1/portal/invoices/<id>/pdf` — Binary PDF download stream.
- `GET /api/v1/portal/payments` — Customer payment history.
- `GET /api/v1/portal/payments/<id>` — Payment allocation detail.
- `GET /api/v1/portal/timeline` — Unified billing timeline.

---

### 4. Phase 10 Test Suite Coverage (`test_customer_portal.py` — 32 Tests)
1. **Authentication & Identity Resolution (Tests 01–02)**: Anonymous rejection, commercial partner resolution across child contacts.
2. **Customer Profile Management (Tests 03–05)**: Permitted field updates, strict rejection of prohibited fields, phone format validation.
3. **Subscription Access & Isolation (Tests 06–08)**: Scoped listing, detail retrieval, cross-customer ID enumeration rejection (`AccessError`).
4. **Subscription Lifecycle Actions (Tests 09–17)**:
   - Pause subscription & policy enforcement (`allow_pause=False` rejection)
   - Cross-customer pause prevention
   - Resume paused subscription & invalid state rejection
   - Early closure & policy enforcement (`allow_early_closure=False` rejection)
   - Contract renewal & policy enforcement (`allow_renewal=False` rejection)
5. **Customer Invoice Access (Tests 18–22)**:
   - Scoped invoice listing & detail retrieval
   - Cross-customer invoice access rejection
   - Native PDF document rendering
   - Cross-customer PDF download rejection
6. **Customer Payment Access (Tests 23–25)**: Scoped payment listing, payment detail retrieval, cross-customer payment isolation.
7. **Billing Timeline (Tests 26–28)**:
   - Aggregated chronological event stream across 4 models
   - Timeline pagination verification
   - Cross-customer timeline isolation
8. **Abuse Protection & Audit Trails (Tests 29–31)**:
   - Sliding-window rate limiting on mutation burst
   - Standard portal audit logging (`portal_subscription_viewed`, `portal_invoice_viewed`, etc.)
   - Autonomous transaction audit logging for security violations
9. **Performance Benchmark (Test 32)**:
   - High-throughput bulk dataset retrieval across 50 subscriptions, 50 invoices, and 50 timeline events.
   - Result: Completed in **0.02 seconds** (over 2,500 entities/sec).


