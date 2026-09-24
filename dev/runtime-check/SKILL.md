---
name: runtime-check
description: Development-only diagnostic for the real-estate skills. Checks which Python packages, Node modules, command-line tools and install paths are available in the current runtime, and actually renders a test PDF and PPTX. Use only when the user asks to "run the runtime check" or "check the runtime".
---

# Runtime check

1. Run `python3 scripts/check.py` from this skill's directory. It takes about a minute and prints a markdown report.
2. Add one line to the report stating which runtime this is (Claude Code, claude.ai or Cowork) and whether your web fetch or web search tools are available in this session.
3. Reply with the full report exactly as printed. Do not install anything, fix anything, or summarize.
