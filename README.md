# Real Estate Skills

Claude skills for real estate agents, in one plugin: a one-file agent profile, buyer and seller CMAs, offer strategy and review, and contract timelines. Skills run in the Claude desktop app and cloud (claude.ai and Cowork).

## Install

### Desktop App, From the Release Zip

1. Go to the [latest release](https://github.com/axelrivera/real-estate-skills/releases/latest) and, under **Assets**, download `real-estate-skills-<version>.zip`.
2. Unzip it. The folder holds the plugin (`real-estate-<version>.plugin`), a setup guide (`README.md`) and the manual (`Real-Estate-Skills-Manual.pdf`).
3. Open the Claude desktop app and go to the plugin settings.
4. Choose **Upload local plugin**.
5. Drag `real-estate-<version>.plugin` onto the upload area (or click **browse** and pick it), then click **Upload**.

To update, download the newer zip and upload its `.plugin` the same way. If the app keeps the old version, remove the plugin first and upload the new one. Your profile stays as it is.

The [PDF manual](dev/package/Real-Estate-Skills-Manual.pdf) walks through setup, the MLS export and each skill.

### Other Routes

- **Cowork or the desktop app, from GitHub:** add the marketplace `axelrivera/real-estate-skills` (https://github.com/axelrivera/real-estate-skills), then install the `real-estate` plugin. In Claude Code terms: `/plugin marketplace add axelrivera/real-estate-skills`, then `/plugin install real-estate@real-estate-skills`.
- **claude.ai, single skills:** run `make package-skills` and upload each zip in `dist/skills/` as a skill (not `dist/dev/`, which holds a diagnostic).

Start with `agent-profile` ("set me up"): a two-minute interview that saves `profile.md` and ready-to-paste Project instructions, with the steps to set up a claude.ai or Cowork Project. In Cowork, select a working folder first: the profile is saved in `.claude/real-estate/` there, so every session finds it.

## Skills

| Skill | What It Does |
|---|---|
| `agent-profile` | One short interview, one file: the agent's name, brokerage, contact details, voice and brand colors. Reports work out local costs from the listing |
| `buyer-cma` | Buyer-side CMA for a listing, with a suggested offer |
| `seller-cma` | Listing CMA with pricing strategies and nets, plus a listing presentation on request |
| `buyer-offer-strategy` | The strongest offer inside the buyer's limits, plus an offer package |
| `seller-offer-review` | Nets, certainty and counters for offers on a listing |
| `contract-timeline` | Every deadline in an executed contract, plus a closing calendar |

Details in [docs/skills.md](docs/skills.md). Sample output from each skill, made from mock data, is in [samples/](samples/).

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
