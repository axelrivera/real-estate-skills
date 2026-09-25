# Project Setup

How to walk the agent through putting their two files in a Project, so every chat or task starts knowing who they are. A Project is optional: without one, the skills still work and the agent shares `profile.md` at the start of a chat.

## Pick the Steps

Give only the steps for where the agent is now, as a short numbered list with the button names in bold, exactly as written here:

| Where the agent is | Steps |
|---|---|
| claude.ai, not in a Project | Set Up a Chat Project |
| claude.ai, inside a Project (the chat has Project files or instructions) | Already in a Chat Project |
| Cowork, not in a project | Set Up a Project in Cowork |
| Cowork, inside a project | Already in a Cowork Project |

If you can't tell, give the claude.ai steps and add one line: "Using Cowork in the desktop app? Tell me and I'll give you those steps."

When the Project's instructions already start with "Real Estate Assistant for" and the name hasn't changed, skip the instructions step and give only the profile step (or nothing, when the saved profile was updated in place).

## Set Up a Chat Project

1. Open **Projects** in the left sidebar and click **+ New Project**. Name it something like "Real Estate".
2. On the project page, click **Set project instructions**, paste everything from project-instructions.md, and save.
3. In the project's files, click **+** and upload profile.md.
4. Start your real estate chats inside the project. I'll know who you are without asking.

## Already in a Chat Project

1. On the project page, click **Set project instructions** and paste everything from project-instructions.md. If there's text there already, paste it below.
2. In the project's files, click **+** and upload profile.md.

## Set Up a Project in Cowork

1. Open **Projects** in the left sidebar and click **+**.
   - Your profile is already saved in this working folder: choose **Use an existing folder** and pick this folder.
   - Otherwise: start from scratch, name it "Real Estate" and pick a folder on your computer for your real estate work.
   - You already set up a claude.ai Project this way: choose **Import from project**. The instructions and files come with it, so you can skip step 2.
2. Paste everything from project-instructions.md into the project's **Instructions**.
3. Only if your profile isn't in that folder yet: start a task in the project, attach profile.md and say "save my profile here".
4. Start your real estate tasks inside the project.

## Already in a Cowork Project

1. Paste everything from project-instructions.md into the project's **Instructions**.
2. Your profile is saved in the project folder already, so nothing else is needed. (If it went to the outputs folder because no folder was selected, attach it in a task there and say "save my profile here".)

## Keeping It Current

- When the profile changes, replace profile.md in the claude.ai Project files. In Cowork it's updated in place.
- The instructions name only the agent, so they need replacing only when the name changes. Everything else comes from the profile.
