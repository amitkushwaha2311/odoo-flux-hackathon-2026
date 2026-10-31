# Brightloop Security Foundation
#
# This directory contains Odoo access control configuration files.
#
# ## Intended Organization (to be populated in Phase 2)
#
# ### Access Control Lists (ACLs)
# File: ir.model.access.csv
#
# Format: id, name, model_id:id, group_id:id, perm_read, perm_write,
#              perm_create, perm_unlink
#
# ACLs define which security groups can read/write/create/delete records
# on a given model. Each Brightloop model will have entries here once
# it is implemented.
#
# ### Security Groups
# File: security_groups.xml (Phase 2)
#
# Groups organize users by their role in the subscription platform:
#
#   brightloop_core.group_user         — Standard Brightloop user
#   brightloop_core.group_manager      — Subscription manager
#   brightloop_core.group_admin        — Full administrative access
#
# ### Record Rules
# File: record_rules.xml (Phase 2)
#
# Record rules add row-level security to models, for example:
#   - Users can only see their own company's subscriptions (multi-company)
#   - Managers can see subscriptions across all companies they belong to
#
# ## Phase 2 Deliverables
# - security_groups.xml: Define user groups with implied hierarchy
# - ir.model.access.csv: Full ACL entries for all Phase 2+ models
# - record_rules.xml: Multi-company record isolation rules
#
# ## References
# Odoo documentation: https://www.odoo.com/documentation/20.0/developer/reference/backend/security.html
