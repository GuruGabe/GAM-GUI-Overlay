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
- The Pick... lists read GAM's real column names (checked read-only against a
  real tenant), and their tests use a stand-in `gam` that records every
  command it is given - only read-only `print` commands are allowed.
- Workflows that change accounts (for example the Staff departure hand-off)
  are tested with a recorder in place of GAM and then live, on throwaway test
  accounts that are deleted afterwards.
- Public Information Requests were run end to end against real Google Vault
  (matter, saved searches, holds, counts, exports, downloads with checksums,
  close) on throwaway accounts and requests, all deleted afterwards.
- The desktop app and the browser version build their forms separately, so
  their start values, commands and confirmation questions are compared by
  tests; browser changes are also checked in a real browser page.

## Still to do

- Report builder: more reports as admins ask for them.
- Report builder `.sh` scripts: confirm on a real Mac (bash 3.2, BSD awk and
  date). The automated tests use strict POSIX awk and a BSD-date stand-in.
- The browser version (`gam_web.py`) has every task, every multi-step
  workflow and (2.92) Run for each CSV row; only the Report builder (which
  writes scheduled .bat / .sh scripts) is desktop-only.
- macOS / Linux in-app updater (2.63): tested with bash and stand-ins for
  Apple's tools; confirm on a real Mac and a real Linux desktop.

## Known limitations

- The mobile-device Pick... list searches by the START of the user's email
  address (listing every phone and tablet in a large domain can take many
  minutes). Mobile devices whose user has no address are not found there.

- Multi-step workflows cannot be saved as one script with Save as script.
- The macOS app is not notarized by Apple (GAMGUI is free, with no paid
  developer account), so macOS asks once before opening it - see README.md.
- In a domain that ENFORCES 2-Step Verification, the `turnoff2sv` part of
  "Deprovision user" fails (the rest of the deprovision still happens).
- Right after a Public Information Request's holds are removed (Close a
  request), Google may refuse to DELETE an account that was on the hold
  ("recently on Google Vault hold") for a short while - about 15 minutes in
  testing.
- Google blocks new mail to a SUSPENDED account, so forwarding and
  auto-replies on a suspended account do not work (the Staff departure
  hand-off offers "kept active but locked" for this reason).
