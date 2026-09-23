# Runtime support

What each runtime provides for the skills' scripts. Produced by the diagnostic skill in `tools/runtime-check/` (not shipped in any plugin).

To re-run: `python3 tools/runtime-check/scripts/check.py` in Claude Code. For claude.ai and Cowork, upload `dist/runtime-check.zip` as a skill and ask "run the runtime check". Build the zip with `cd tools && zip -r ../dist/runtime-check.zip runtime-check`.

## Dependencies the prototypes use

| Kind | Dependency | Used for |
|---|---|---|
| Python | pandas, numpy | CMA export parsing, market stats |
| Python | bs4 | HTML handling in CMA renderers |
| Python | playwright + Chromium | HTML → PDF (all PDF outputs) |
| Python | Pillow | Brand color extraction from images (new) |
| Node | pptxgenjs, react, react-dom, react-icons, sharp | Seller listing presentation (PPTX) |
| CLI | pdftotext | Reading uploaded contracts |
| CLI | soffice (LibreOffice) | Deck validation and preview |

## Results

Checked 2026-09-23.

| Item | Claude Code (macOS, dev machine) | claude.ai | Cowork |
|---|---|---|---|
| Python | 3.12 | 3.12 | **3.11** |
| pandas / numpy | No | Yes | Yes |
| bs4 | No | Yes | Yes |
| PyYAML | No | Yes | Yes |
| Pillow | Yes | Yes | Yes |
| Playwright → PDF | Yes | Yes | Yes |
| Node / npm | Yes (26.5) | Yes (22.22) | Yes (22.22) |
| pptxgenjs + deck modules | No | Yes | Yes |
| pdftotext | Yes | Yes | Yes |
| LibreOffice | No | Yes | Yes |
| PyPI / npm reachable | Yes / Yes | Yes / Yes | Yes / Yes |
| `/mnt/user-data/outputs` | No | Yes | Yes |
| Web fetch / search tools | Yes | Yes | Yes |

Notes:
- claude.ai and Cowork have everything the prototypes use. Both run on Linux in a sandbox.
- In claude.ai the working directory is the skill's own folder (`/mnt/skills/plugins/...`). Never write outputs there. Use `/mnt/user-data/outputs/`, per the output location rule.
- Claude Code runs on the user's own machine, so results vary by user. This dev machine is a best case. A typical agent's machine is likely to have less installed.

## Dependency policy

Based on these results:

1. **Python 3.11 is the minimum.** Cowork runs 3.11, so no 3.12-only syntax.
2. **Data work uses the Python standard library only.** No pandas, numpy, bs4 or PyYAML in skill scripts. The prototypes use them for CSV parsing, simple statistics and HTML, which `csv`, `statistics` and `html.parser` cover. Profile YAML is parsed by a small reader in `shared/` that supports the profile format only.
3. **Only two heavy dependencies, both for file mode:**
   - **Chromium through Playwright** for PDFs.
   - **pptxgenjs** for decks. Whether react, react-icons and sharp are needed (icons in the prototype deck) is decided when `seller-cma` is rebuilt.
4. **Pillow** only in `agent-profile`, for reading colors from images.
5. **Missing dependency (mostly Claude Code):** the skill says what's missing in plain words and offers the exact install command. It runs the command only with the user's approval. Otherwise it falls back to markdown mode. It never fails silently.
6. **pdftotext and LibreOffice are optional.** If `pdftotext` is missing, Claude reads the PDF directly. LibreOffice is used only for deck quality checks, which are skipped when it isn't installed.
