# Runtime support

Skills run in the Claude **desktop app and cloud**: claude.ai chat and Cowork. Both run skills in a Linux sandbox with the same tools installed. Claude Code is not a supported runtime.

Local machines are for development only. See [development.md](development.md).

## Sandbox results

Produced by the diagnostic skill in `dev/runtime-check/` (never shipped). Checked 2026-09-23.

| Item | claude.ai | Cowork |
|---|---|---|
| Python | 3.12.3 | **3.11.15** |
| pandas / numpy | 3.0.2 / 2.4.4 | 3.0.2 / 2.4.4 |
| beautifulsoup4 | 4.14.3 | 4.14.3 |
| PyYAML | 6.0.3 | 6.0.3 |
| Pillow | 12.1.1 | 12.2.0 |
| Playwright → PDF | 1.56.0 | Yes |
| Node / npm | 22.22.2 / 10.9.7 | 22.22.2 / 10.9.7 |
| pptxgenjs / react / react-dom | 4.0.1 / 19.2.5 / 19.2.5 | Yes |
| react-icons / sharp | 5.6.0 / 0.34.5 | Yes |
| pdftotext | 24.02.0 | 24.02.0 |
| LibreOffice | 24.2.7 | 24.2.7 |
| PyPI / npm reachable | Yes | Yes |
| `/mnt/user-data/outputs` | Yes | Yes |
| Web fetch / search tools | Yes | Yes |

Versions for Playwright and the Node modules come from a second claude.ai run on 2026-09-23. Cowork's exact versions for these weren't recorded; they are assumed to match claude.ai, since every version that was recorded in both runtimes matched (except a Pillow patch release). `dev/requirements.txt`, `dev/package.json` and `.nvmrc` are pinned to the claude.ai versions.

Notes:
- In claude.ai the working directory is the skill's own folder (`/mnt/skills/plugins/...`). Never write outputs there. Use `/mnt/user-data/outputs/`, per the [output location](architecture.md#output-location) rule.

To re-run: `make package-skills`, upload `dist/dev/runtime-check.zip` as a skill, and ask "run the runtime check".

## Dependency policy

1. **Python 3.11 syntax.** Cowork runs 3.11, so no 3.12-only features.
2. **Use only what the sandbox already has.** Everything in the table above is available. Skills never install packages at run time.
3. **Node 22** for the deck builder.
4. **Local dev mirrors the sandbox** through `.venv` and nvm, pinned to the versions above.
