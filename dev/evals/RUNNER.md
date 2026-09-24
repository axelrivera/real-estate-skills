# Eval runner instructions

You are playing Claude inside claude.ai / Cowork, helping a real estate agent. A skill is installed; use it exactly as its SKILL.md says. The agent (the user) is not technical and is not available to answer questions: when the skill tells you to ask something, write the question into your reply as you would send it, then continue as far as the skill allows without the answer (use defaults, placeholders or a Preliminary report as the skill says). Don't stop at "I need more info" if the skill says to proceed with defaults.

## Environment (simulates the sandbox)

- Skill folder: given in your task. Read only files inside the skill folder and the eval's `inputs/` folder. Do NOT read anything else in the repository (no docs/, dev/, shared/, other skills, git history): a real user's sandbox only has the skill.
- Run the skill's scripts from the skill folder, with this prefix so Python, Node and the output folder match the sandbox:
  ```
  cd <skill folder> && export PATH=<repo>/.venv/bin:$PATH OUTPUT_DIR=<outputs folder> NODE_PATH=<repo>/dev/node_modules && . ~/.nvm/nvm.sh && nvm use --silent 22 >/dev/null; python3 scripts/...
  ```
  `python3` then resolves to the right interpreter. `/mnt/user-data/outputs/` doesn't exist here: wherever the skill says the outputs folder, use your outputs folder.
- Write every file you create (data JSON, profiles, PDFs, PPTX, handoffs) to your outputs folder. Never write inside the skill folder or anywhere else in the repo.
- Web search is available if the skill says to look something up.
- Today is 2026-09-26 (the eval files assume late September 2026: the Cypress Bend contract was executed 9/25).

## What to save in the outputs folder

1. Every file the skill produced (PDF, PPTX, .md profile, .cma.json, data JSON).
2. `response.md`: your final reply to the agent, exactly as you would send it in chat (markdown).
3. `friction.md`: an honest, specific list of every place the skill made you stumble: instructions that were unclear, missing or contradictory; script errors or confusing script output (quote the command and the error); fields you had to guess the format of; things the skill told you to do that didn't fit this request; anything you did that the skill didn't cover. Also note anything in the output that looks wrong to you (numbers, layout, wording). If nothing, say so. This is the most important file.

Keep going until the task is done as the skill intends. When finished, reply with a 3-line summary: what you delivered, the files, and the top friction point.
