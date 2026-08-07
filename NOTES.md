# GAMGUI - Development Notes

## Status

- Single-file tkinter application (`GAMGUI.py`), Python standard library only.
- 78 tasks across 14 categories, plus a Custom-command mode, a built-in
  phishing incident-response workflow, and a read-only mailbox takeover audit.
- Windows one-folder build via `Build-EXE.bat`. On Python 3.14 the build bundles
  the Tcl/Tk 9 script library (see `extract_tcl.py`) so the app starts reliably.

## Roadmap / ideas

- CSV bulk-run builder: pick a CSV, map columns to a task's fields, generate a
  `gam csv` command.
- Favorites / recent-commands list.
- Per-task "open wiki page" help button.
- Dark mode; larger font option for demos.
- Dry-run/preview mode where GAM supports it.
- macOS/Linux builds (the source is cross-platform; needs building and testing
  on those systems).

## Known limitations

- GAMGUI runs the operator's own authorized `gam` and has no permission model of
  its own: whoever can open it can run whatever their `gam` is authorized to do.
- The command preview is editable by design - treat it like a terminal.
- Custom-command mode does not support shell pipes or redirection; use GAM's own
  `redirect csv` / `todrive` options instead.
- The incident-response workflow pulls raw Gmail/Drive audit CSVs but does not
  correlate attachment hashes or check Drive for persisted attachments.
- Gmail's API exposes no filter creation timestamp, so the mailbox takeover audit
  lists all current filters rather than only recently created ones.

## Contributing

Issues and pull requests are welcome. `GAMGUI.py` is intentionally a single file
with a data-driven task catalog (the `TASKS` dictionary) - adding a task is a
few lines and needs no new code. Please keep it dependency-free (standard library
only) so it stays easy to build and audit.
