# Real Estate Marketplace

A Claude plugin marketplace for real estate agents. Skills run in Claude Code, claude.ai and Cowork.

## Install

```
/plugin marketplace add <repo URL or local path>
/plugin install core@real-estate-marketplace
/plugin install transactions@real-estate-marketplace
```

## Plugins

| Plugin | Description |
|---|---|
| `core` | Agent and market profiles used as context by every other plugin |
| `transactions` | Buyer and seller CMAs, offer strategy and review, contract timelines |

Details in [docs/plugins.md](docs/plugins.md).

## Documentation

- [docs/architecture.md](docs/architecture.md): rules every skill follows
- [docs/migration-plan.md](docs/migration-plan.md): rebuilding the prototypes as final skills
- [docs/plugins.md](docs/plugins.md): plugin and skill catalog
