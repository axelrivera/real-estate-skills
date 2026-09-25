# Saved Files

Where the agent's profile lives between conversations, and where to look for it. The profile is a convenience: when none is found, collect what the task needs in the chat, as the skill says.

## The Saved Folder

In Cowork, when the agent has a working folder selected, the profile is saved as `.claude/real-estate/profile.md` inside that folder. It's one file: the agent's name, brokerage, contact details, brand colors, voice and disclaimers. It holds no local costs: reports take those from the property.

Resolve the path from the agent's working folder, never from the current directory: in Cowork, skills run from a plugin folder, not from the agent's folder. If you can't tell which folder the agent selected, there is no saved folder for this conversation.

## Finding the Profile

Use the first place that has one:

1. **The conversation:** a file the agent uploaded or pasted, or one written earlier in this chat.
2. **Project files** (claude.ai Projects).
3. **The saved folder,** when there is a working folder: `.claude/real-estate/profile.md`.

Pass the file to `render.py` by its path (`--profile`). When the profile came from the saved folder, say so in one short line ("Using your saved profile"), so the agent knows where it came from.

## Saving the Profile

Only save after the agent has given or confirmed the details.

- **Cowork with a working folder:** save straight to `.claude/real-estate/` in that folder (create the folder when it's missing). The first time, say the full path in the hand-over. When a file is already there, the update replaces it; say in plain words what changed.
- **Anywhere else** (a claude.ai chat, a Project, or Cowork with no folder selected): save to the outputs folder (the runtime provides it; never the skill's own folder) and hand it over with one line on keeping it:
  - **claude.ai inside a Project** (the conversation has Project files or instructions): "Add this file to your Project files so every chat can use it."
  - **Cowork with no folder selected:** "Select a working folder and I'll save this there, so every session can use it." Offer to save it once they do.
  - **Otherwise:** "Keep this file and share it at the start of a chat when you want it used. If you use a Project, add it to the Project files."

`project-instructions.md` (written by agent-profile) is saved next to the profile, by the same rules. It's for the agent to paste into a Project; other skills never read it.

Never block the task over saving: the profile still works for the rest of this conversation.

## Working Files

The data files a skill writes (report.json, buyer.json, listing.json, deal.json, columns.json) and the CMA handoff (`.cma.json`) are working files: they feed the scripts and are never handed to the agent. Create a temporary folder once per conversation (`mktemp -d`) and write them there, never in the outputs folder and never in the skill's own folder. Only the finished files (PDF, PowerPoint, calendar, the profile and its project instructions) go in the outputs folder, and only those are presented or linked. Never offer a JSON file for download or paste one into a reply.

## CMA Handoffs

compute.py saves `<address>.buyer.cma.json` or `<address>.seller.cma.json` next to report.json, in the temporary folder. Later in the same conversation, pass that file to an offer skill with `--cma`. In a new conversation it's gone: read the CMA the agent shares (its PDF or chat summary) for the low, high and median adjusted value, confirm them in one line, and fill them in by hand, as the offer skill says for any other CMA. Use a CMA only when the address is the same home.
