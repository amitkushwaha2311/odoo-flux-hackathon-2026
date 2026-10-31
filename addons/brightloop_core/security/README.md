# Brightloop Security Foundation

This directory contains Odoo access control configuration files for Brightloop.

## Odoo 20.0 Security Architecture

In Odoo 20.0, access controls have been unified into `ir.access`:

### 1. Access Control Lists (ACLs)
**Target File (Phase 2):** `ir.access.csv`

**Odoo 20 Header Format:**
```csv
id,name,model_id,group_id/id,operation,domain
```

**Columns:**
- `id`: Unique XML ID for the rule (e.g. `access_brightloop_subscription_user`)
- `name`: Descriptive human-readable name
- `model_id`: Target model technical name (e.g. `brightloop.subscription`)
- `group_id/id`: Security group reference (e.g. `brightloop_core.group_user`, `base.group_user`)
- `operation`: Combination of `c` (create), `r` (read), `u` (update/write), `d` (delete/unlink), e.g. `crud`, `r`, `ru`
- `domain`: Optional domain filter directly integrated into the access rule (e.g. `"[('company_id', 'in', company_ids)]"`)

### 2. Security Groups
**Target File (Phase 2):** `security_groups.xml`

Groups define hierarchical roles for the subscription management platform:
- `group_brightloop_user`: Standard user (view subscriptions, basic workflows)
- `group_brightloop_manager`: Subscription manager (create plans, approve cancellations)
- `group_brightloop_admin`: Administrator (full system configuration, billing credentials)

### 3. Record Rules
**Target File (Phase 2):** `record_rules.xml`

Row-level multi-company and multi-tenant security policies:
- Multi-company isolation: Users only see records belonging to their active companies (`['|', ('company_id', '=', False), ('company_id', 'in', company_ids)]`)

## Phase 1 Status
In Phase 1, `brightloop_core` only defines `brightloop.base`, which is an `models.AbstractModel`. Abstract models are Python mixins and do not have database tables or access control records. Full security groups and rules will be registered in Phase 2 alongside the concrete business models.

