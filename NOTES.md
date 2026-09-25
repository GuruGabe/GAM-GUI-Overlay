# GAMGUI - public development notes

This is the public summary of GAMGUI's roadmap and known limitations. The
full version history is in [CHANGELOG.txt](CHANGELOG.txt); how to use every
feature is in [README.md](README.md) and [README.txt](README.txt).

## How GAMGUI is tested

- Every task's command template is checked by an automated catalog validator,
  and GAM syntax is checked against GAM's own `GamCommands.txt` and source.
- Scripts that GAMGUI writes (Save as script, Report builder) are run through
  the real `cmd.exe`, PowerShell and bash with a stand-in `gam`, including
  folder names containing `& ( ) % !` and spaces.
- Read-only reports are also run against a real Google Workspace tenant.
- Workflows that change accounts (for example the Staff departure hand-off)
  are tested with a recorder in place of GAM and then live, on throwaway test
  accounts that are deleted afterwards.

## Still to do

- Report builder: more reports as admins ask for them.
- Report builder `.sh` scripts: confirm on a real Mac (bash 3.2, BSD awk and
  date). The automated tests use strict POSIX awk and a BSD-date stand-in.
- The browser version (`gam_web.py`) does not include the Report builder or
  the multi-step workflows yet.
- macOS / Linux: "Update now" opens the Releases page (the automatic
  updater is Windows-only today).

## Known limitations

- Multi-step workflows cannot be saved as one script with Save as script.
- The macOS app is not notarized by Apple (GAMGUI is free, with no paid
  developer account), so macOS asks once before opening it - see README.md.
- In a domain that ENFORCES 2-Step Verification, the `turnoff2sv` part of
  "Deprovision user" fails (the rest of the deprovision still happens).
- Google blocks new mail to a SUSPENDED account, so forwarding and
  auto-replies on a suspended account do not work (the Staff departure
  hand-off offers "kept active but locked" for this reason).
