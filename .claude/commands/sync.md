---
description: Re-read the project folders and refresh the mirror
---

Refresh what the brain knows about the owner's project folders.

1. Run:
   ```
   python3 brain/tools/sync.py
   ```
   It reads every folder in `brain/config.json`'s `sources` list — their
   TODO/README/CLAUDE files for open checkboxes, and git/file dates for when
   each was last worked on — writes `brain/synced.md`, and rebuilds the page.

2. **Read the fresh `brain/synced.md`** and say, briefly, what changed since
   the brain last looked: projects gone quiet, new open items, anything the
   config lists that no longer exists on disk.

3. If a synced project's activity contradicts its workstream (the workstream
   says Moving but the folder has been untouched for a month, or vice versa),
   update the workstream's Status/Touched to match reality and mention it.

4. If the owner has projects that are not in `sources` yet, offer to add
   them — the config is just a list of `{name, path, files}` entries.
