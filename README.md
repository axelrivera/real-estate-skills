# Real Estate Skills

Claude skills for real estate agents, in one plugin: agent and market profiles, buyer and seller CMAs, offer strategy and review, and contract timelines. Skills run in the Claude desktop app and cloud (claude.ai and Cowork).

## Install

- **Cowork or the desktop app, from GitHub:** add the marketplace `axelrivera/real-estate-skills` (https://github.com/axelrivera/real-estate-skills), then install the `real-estate` plugin. In Claude Code terms: `/plugin marketplace add axelrivera/real-estate-skills`, then `/plugin install real-estate@real-estate-skills`.
- **Desktop app, from a file:** upload `real-estate-<version>.plugin` with **Upload local plugin** (build it with `make package`; it lands in `dist/`, along with `real-estate-skills-<version>.zip`, which bundles the `.plugin` with install instructions for sharing).
- **claude.ai, single skills:** run `make package-skills` and upload each zip in `dist/skills/` as a skill (not `dist/dev/`, which holds a diagnostic).

Start with `agent-profile`. In Cowork, select a working folder: profiles are saved in `.claude/real-estate/` there, so every session finds them.

## Skills

| Skill | What It Does |
|---|---|
| `agent-profile` | The agent's name, brokerage, contact details, voice and brand colors |
| `market-profile` | Local closing costs, taxes, commissions and contract rules |
| `buyer-cma` | Buyer-side CMA for a listing, with a suggested offer |
| `seller-cma` | Listing CMA with pricing strategies, nets and a listing presentation |
| `buyer-offer-strategy` | The strongest offer inside the buyer's limits, plus an offer package |
| `seller-offer-review` | Nets, certainty and counters for offers on a listing |
| `contract-timeline` | Every deadline in an executed contract, plus a closing calendar |

Details in [docs/skills.md](docs/skills.md).

## Documentation

- [docs/architecture.md](docs/architecture.md): rules every skill follows
- [docs/skill-guidelines.md](docs/skill-guidelines.md): how a skill is structured
- [docs/migration-plan.md](docs/migration-plan.md): rebuilding the prototypes as final skills
- [docs/skills.md](docs/skills.md): skill catalog
- [docs/runtime-support.md](docs/runtime-support.md): what each runtime can run
- [docs/development.md](docs/development.md): local setup, packaging and generating outputs
- [docs/status.md](docs/status.md): where the work stands and what's next

## License

[MIT](LICENSE)
