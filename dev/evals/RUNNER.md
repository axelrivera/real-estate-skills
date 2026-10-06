# Eval runner instructions

You are playing Claude inside claude.ai / Cowork, helping a real estate agent. A skill is installed; use it exactly as its SKILL.md says. The agent (the user) is not technical and is not available to answer questions: when the skill tells you to ask something, write the question into your reply as you would send it, then continue as far as the skill allows without the answer (use defaults, placeholders or a Preliminary report as the skill says). Don't stop at "I need more info" if the skill says to proceed with defaults.

Your task gives you one run folder (`out/evals/iteration-N/<skill>/eval-<id>/run-<k>/`) and its skill folder or folders (`runs.json` in the iteration folder lists them). Other runs of the same eval may be going at the same time: work only in your run folder, and never read another run's files.

## Environment (simulates the sandbox)

- Skill folder: given in your task. When it names two (for example buyer-cma and buyer-offer-strategy), both skills are installed in the same chat: use whichever the message calls for, and what one saves in this conversation is there for the other, as it would be in a real chat. Read only files inside the skill folder(s) and the run's `inputs/` folder. Do NOT read anything else in the repository (no docs/, dev/, shared/, other skills, git history, other runs): a real user's sandbox only has the skill.
- Run the skill's scripts from the skill folder, with this prefix so Python, Node and the output folder match the sandbox:
  ```
  cd <skill folder> && export PATH=<repo>/.venv/bin:$PATH OUTPUT_DIR=<outputs folder> NODE_PATH=<repo>/dev/node_modules && . ~/.nvm/nvm.sh && nvm use --silent 22 >/dev/null; python3 scripts/...
  ```
  `python3` then resolves to the right interpreter. `/mnt/user-data/outputs/` doesn't exist here: wherever the skill says the outputs folder, use your outputs folder (`run-<k>/with_skill/outputs/`).
- Write every file you create (data JSON, profiles, PDFs, PPTX, handoffs) to your outputs folder. Wherever the skill says a temporary or working folder (for its data file, handoffs, extracted text, page images), use a `_work/` subfolder of your outputs folder, never a shared temp or scratchpad name another runner could overwrite. Never write inside the skill folder or anywhere else in the repo.
- Web search is available if the skill says to look something up.
- Today is the date on your task's first line ("Today is ...", written by `dev/evals/setup.py`: the eval's `today`, else 2026-09-26, since the eval files assume late September 2026). Use it even if the machine clock says otherwise, and pass it to any script that takes a report date.

## Several Messages

When task.md has `## Message 1`, `## Message 2` and so on, they are one conversation: answer Message 1 completely as your reply to it (files and all), then read Message 2 and answer it as the next reply in the same chat, and so on. Don't read ahead: answer each message as if the next hadn't arrived. A message that says files are attached means those files from `inputs/`; don't open an input before the message that brings it.

## What to save in the outputs folder

1. Every file the skill produced (PDF, PPTX, ICS, .md profile, .cma.json, data JSON).
2. The data file each report was rendered from, under the name the skill gives it (`deal.json`, `listing.json`, `buyer.json`, `report.json`, `net-sheet.json`), in `_work/`: the final version, the one the last render or compute ran on. When you re-run after a fix or a new message, update that file in place rather than starting another. Keep any `.cma.json` handoff there too. `dev/evals/spread.py` re-runs these files to compare repeat runs of the eval.
3. `response.md`: your final reply to the agent, exactly as you would send it in chat (markdown). With several messages, one section per reply: `## Reply 1`, `## Reply 2`, and so on.
4. `friction.md`: an honest, specific list of every place the skill made you stumble: instructions that were unclear, missing or contradictory; script errors or confusing script output (quote the command and the error); every stop on a figure or a script-written field in what you wrote, and how you rewrote it; fields you had to guess the format of; things the skill told you to do that didn't fit this request; anything you did that the skill didn't cover. Also note anything in the output that looks wrong to you (numbers, layout, wording). If nothing, say so. This is the most important file.

Keep going until the task is done as the skill intends. When finished, reply with a 3-line summary: what you delivered, the files, and the top friction point.
