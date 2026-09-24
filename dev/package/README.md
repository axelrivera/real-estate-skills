# Real Estate Skills {{VERSION}}

Claude skills for real estate agents, in one plugin: agent and market profiles, buyer and seller CMAs, offer strategy and review, and contract timelines.

`{{PLUGIN_FILE}}` in this folder is the plugin, ready to upload to the Claude desktop app.

## Install in the Claude Desktop App

1. Unzip this archive.
2. Open the Claude desktop app and go to the plugin settings.
3. Choose **Upload local plugin**.
4. Drag `{{PLUGIN_FILE}}` onto the upload area (or click **browse** and pick it), then click **Upload**.

Upload the `.plugin` file itself. Don't upload this zip or the unzipped folder.

All 7 skills then appear as `real-estate:<skill>`. Start with `real-estate:agent-profile`. In Cowork, select a working folder: profiles are saved in `.claude/real-estate/` there, so every session finds them.

## Install From GitHub (Cowork)

Instead of uploading the file, add the marketplace `axelrivera/real-estate-skills`, then install the `real-estate` plugin. Updates then come from GitHub.

## Updating

Upload the new `.plugin` file. If the app keeps the old version, remove the plugin first and upload it again.

## More Information

Source, documentation and license: https://github.com/axelrivera/real-estate-skills
