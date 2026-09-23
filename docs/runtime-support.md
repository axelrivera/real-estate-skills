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

| Item | Claude Code (macOS, dev machine) | claude.ai | Cowork |
|---|---|---|---|
| pandas / numpy | No | Pending | Pending |
| bs4 | No | Pending | Pending |
| PyYAML | No | Pending | Pending |
| Pillow | Yes (12.3) | Pending | Pending |
| Playwright → PDF | Yes | Pending | Pending |
| Node / npm | Yes (26.5 / 11.17) | Pending | Pending |
| pptxgenjs + deck modules | No | Pending | Pending |
| pdftotext | Yes | Pending | Pending |
| LibreOffice | No | Pending | Pending |
| PyPI / npm reachable | Yes / Yes | Pending | Pending |
| `/mnt/user-data/outputs` | No | Pending | Pending |

Claude Code runs on the user's own machine, so results there vary by user. This dev machine is a best case. A typical agent's machine is likely to have less installed.
