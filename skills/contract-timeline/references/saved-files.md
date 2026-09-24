# Saved Files

Where the agent's profiles live between conversations, and where to look for them. A profile is a convenience: when none is found, collect what the task needs in the chat, as the skill says.

## The Saved Folder

In Cowork, when the agent has a working folder selected, profiles are saved in `.claude/real-estate/` inside that folder:

| File | What It Holds |
|---|---|
| `agent-profile.md` | The agent's name, brokerage, contact details, voice, disclaimers and brand colors |
| `market-profile-<area>.md` | One per market, for example `market-profile-seminole.md` |

Resolve the path from the agent's working folder, never from the current directory: in Cowork, skills run from a plugin folder, not from the agent's folder. If you can't tell which folder the agent selected, there is no saved folder for this conversation.

## Finding a Profile

Use the first place that has one:

1. **The conversation:** a file the agent uploaded or pasted, or one written earlier in this chat.
2. **Project files** (claude.ai Projects).
3. **The saved folder,** when there is a working folder: `.claude/real-estate/agent-profile.md`, and the `market-profile-*.md` whose state and area match the deal.

Pass the file to the scripts by its path (`--agent`, `--market`). When the profile came from the saved folder, say so in one short line ("Using your saved profile"), so the agent knows where it came from.

## Saving a Profile

Only save after the agent has given or confirmed the details.

- **Cowork with a working folder:** save straight to `.claude/real-estate/` in that folder (create the folder when it's missing). The first time, say the full path in the hand-over. When a file is already there, the update replaces it; say in plain words what changed.
- **Anywhere else** (a claude.ai chat, a Project, or Cowork with no folder selected): save to the outputs folder (the runtime provides it; never the skill's own folder) and hand it over with one line on keeping it:
  - **claude.ai inside a Project** (the conversation has Project files or instructions): "Add this file to your Project files so every chat can use it."
  - **Cowork with no folder selected:** "Select a working folder and I'll save this there, so every session can use it." Offer to save it once they do.
  - **Otherwise:** "Keep this file and share it at the start of a chat when you want it used. If you use a Project, add it to the Project files."

Never block the task over saving: the profile still works for the rest of this conversation.

## CMA Handoffs

A CMA saves `<address>.buyer.cma.json` or `<address>.seller.cma.json` next to its report, where the agent can see it. The offer skills look for it in this order: the conversation (a file, or a reply ending in a `cma-handoff v1` block), Project files, then the outputs folder and the working folder. Use a match only when the address is the same home, and name the file you used.
