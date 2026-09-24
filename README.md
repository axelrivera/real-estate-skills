# Real Estate Marketplace

A Claude plugin marketplace for real estate agents. Skills run in the Claude desktop app and cloud (claude.ai and Cowork).

## Install

- **Cowork:** add this repository as a plugin marketplace, then install `core` and `transactions`.
- **claude.ai:** run `make package` and upload each zip in `dist/` as a skill (not `dist/dev/`, which holds a diagnostic).

## Plugins

| Plugin | Description |
|---|---|
| `core` | Agent and market profiles used as context by every other plugin |
| `transactions` | Buyer and seller CMAs, offer strategy and review, contract timelines |

Details in [docs/plugins.md](docs/plugins.md).

## Documentation

- [docs/architecture.md](docs/architecture.md): rules every skill follows
- [docs/skill-guidelines.md](docs/skill-guidelines.md): how a skill is structured
- [docs/migration-plan.md](docs/migration-plan.md): rebuilding the prototypes as final skills
- [docs/plugins.md](docs/plugins.md): plugin and skill catalog
- [docs/runtime-support.md](docs/runtime-support.md): what each runtime can run
- [docs/development.md](docs/development.md): local setup and generating outputs
- [docs/status.md](docs/status.md): where the work stands and what's next
