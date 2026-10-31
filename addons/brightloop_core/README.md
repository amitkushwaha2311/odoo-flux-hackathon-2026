# brightloop_core

**Brightloop Core** is the foundation Odoo addon for the Brightloop Subscription Intelligence platform.

## Purpose

This module is the architectural base that all other Brightloop modules depend on.

It provides:
- `brightloop.base` — Abstract mixin for all Brightloop models
- Centralized logging conventions
- Company-aware architecture
- Currency-aware financial stubs
- Timezone-aware date handling
- Consistent error handling patterns
- Safe transaction helpers

## Phase

**Phase 1 — Infrastructure Foundation**

Business logic (subscriptions, billing, invoicing, reporting) is implemented in subsequent phases.

## Inheritance

All Brightloop models should inherit from `brightloop.base`:

```python
class MySubscriptionModel(models.Model):
    _name = 'brightloop.subscription'
    _inherit = ['brightloop.base']
    _description = 'Subscription'
```

## Dependencies

| Odoo Module | Reason |
|---|---|
| `base` | Core models: `res.company`, `res.partner`, `res.currency` |
| `mail` | Chatter / message log for future subscription events |

## Running Tests

```bash
docker compose exec odoo odoo \
  -d brightloop_dev \
  --test-enable \
  --test-tags brightloop_core \
  -i brightloop_core \
  --stop-after-init
```

