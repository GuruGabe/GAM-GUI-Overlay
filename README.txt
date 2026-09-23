================================================================================
  GAMGUI 2.42 - A GRAPHICAL FRONT-END FOR GAM7
  Author: Gabriel Clifton
================================================================================

  This is the full reference manual. New, non-technical users should start
  with HOW-TO-GUIDE.txt (a plain-English walkthrough) and README.md (the
  illustrated overview with screenshots).

1. WHAT THIS PROGRAM DOES
   GAMGUI is a point-and-click front end for GAM7, the command line tool for
   Google Workspace administration (https://github.com/GAM-team/GAM).
   It presents over 670 admin tasks as fill-in-the-blank forms across 38
   categories, plus a "Run ANY GAM command (advanced)" console that accepts
   any GAM command not built into a form. You get GAM's power without
   memorizing commands. It is built for anyone who uses GAM - schools,
   businesses, nonprofits, and resellers/MSPs alike.

   The categories are: OAuth Setup, Common Tasks, Users, Groups, Aliases,
   Org Units, Domains & Domain Aliases, Chromebooks, Chrome Browsers &
   Policies, Gmail, Calendars, Drive,
   Shared Drives, Classroom, Google Meet, Google Forms, Google Chat, Google
   Tasks & Keep, Google Sheets & Docs, Licenses, Vault, Mobile Devices, Cloud Identity Devices, Custom Schemas, Contacts,
   Admin Roles & Privileges, Data Transfers, Reseller / Channel, Marketing &
   Analytics, Chrome Printers, Buildings/Features/Rooms, Customer/Settings,
   Reports, Security, Access & Identity (SSO, CAA, Policies), Email Cleanup, Bulk/Batch, and Diagnostics.

   Not covered, because GAM itself does not manage them: Google Voice (only
   its license SKUs, which ARE covered under Licenses), Google Sites, and
   Cloud Storage buckets.

   BULK ACTIONS: many categories include BULK tasks that act on many objects
   at once. They share a target picker - point an action at an OU, an OU and
   its sub-OUs, a group, a search query, a CSV column, or everyone. Examples:
     - Users:       bulk create from a CSV; bulk suspend / unsuspend / move to
                    an OU / change any attribute across a scope.
     - Gmail:       set a signature, set/clear an auto-reply, turn OFF
                    auto-forwarding, add/remove a delegate across a scope.
     - Chromebooks: bulk move / disable / deprovision / reboot / powerwash /
                    wipe by OU, query, or CSV; import asset tags from a CSV.
     - Drive:       bulk transfer / share / unshare files matching a query;
                    empty trash; collect orphaned files; transfer a whole Drive.
     - Groups:      bulk add / remove members; add/remove one user across many
                    groups; create / delete groups from a CSV.
     - Classroom:   add students/teachers from a group, OU, or CSV; bulk create
                    courses; bulk invite guardians.
     - Licenses:    exact-match sync of a license to a scope (adds it to users
                    in the scope, removes it from everyone else).
     - Photos:      set profile photos for a whole scope from a folder of
                    images named after each user.
     - Email:       send the same message to every user in a scope.

   EVERYDAY TASKS ADDED IN 2.40 (by category):
     - Gmail:       restore messages from Trash; mark as spam; add/remove a
                    label on matching messages (remove UNREAD = mark read,
                    remove INBOX = archive); forward matching messages; export
                    them to .eml files; import an .eml; rename a label;
                    rename/merge labels by pattern; send email as a user.
     - Drive:       restore a trashed file or every trashed file matching a
                    query; permanently purge a trashed file; create a nested
                    folder path; create a shortcut; rename; replace a file's
                    contents from this PC (keeps its ID, link, and sharing).
     - Users:       download / set / delete a profile photo; check whether an
                    address is an unmanaged (personal) account on your domain;
                    invite it to join; check or cancel the invitation.
     - Calendars:   swap one attendee for another on every matching event;
                    purge selected events (a selector is REQUIRED - see the
                    safety note below); import an event by iCalUID; create
                    out-of-office, working location, and focus time entries,
                    and remove them.
     - Groups:      check whether a user is in one or more groups (optionally
                    through nested groups); a user's role in a group.
     - Org Units:   OU info (details and users, optionally sub-OUs).
     - Classroom:   sync a student's guardians to an exact list; clear a
                    student's guardians or pending invitations.
     - Contacts:    remove duplicate addresses; list / add / remove contact
                    delegates.
     - Admin Roles: a role's privileges; rename/edit or delete a custom role.
     - Buildings, Features & Rooms: building info and update; rename a
                    feature; room/resource info and update.
     - Chrome Printers: update a printer.
     - Reports:     usage reports (per user or whole organization) for a date
                    range; list the usage-report parameter names.
     - Security:    Alert Center alert details; delete or restore an alert.
     - Google Tasks & Keep (NEW category): list, create, complete, rename, and
                    delete tasks and task lists; clear completed tasks; list,
                    create, delete, and share Keep notes; download a note's
                    attachments.
     - Google Sheets & Docs (NEW category): read a range or a spreadsheet's
                    tabs (to screen, Sheet, or CSV); append rows or write
                    values from a JSON file; clear a range.

   SECURITY AND IDENTITY TASKS ADDED IN 2.41 (by category):
     - Chrome Browsers & Policies (NEW category): show / set / remove Chrome
                    policies for an OU; look up policy schemas; managed
                    Chrome browsers (info, move, annotate, delete); browser
                    enrollment tokens (create, list, revoke); managed Chrome
                    profiles (list, info, delete, clear cache / cookies);
                    installed apps and extensions and which devices have one;
                    wallpaper / avatar images; managed networks from JSON.
     - Access & Identity (SSO, CAA, Policies) (NEW category): SAML SSO
                    profiles (create, update, delete), IdP signing
                    certificates, SSO on/off for an OU or group; Context-
                    Aware Access levels (IP ranges, countries, custom rule);
                    Cloud Identity policies (list, info, create/update from
                    JSON, delete); allowlisted domains.
     - Groups:      Cloud Identity view - security groups, dynamic groups
                    (members by query), lock / unlock, members that EXPIRE on
                    a date, member lists with expirations.
     - Security:    S/MIME certificates (list, upload, default, delete);
                    Gmail client-side encryption key pairs and identities;
                    Alert Center Pub/Sub settings and feedback; email
                    monitors (Email Audit API); delete backup codes.
     - Drive:       Drive labels (classification labels) and who can use them.
     - Shared Drives: copy one drive's members to another, or sync them to
                    an exact match.
     - Chromebooks: download device files (logs, screenshots).
     - Domains:     get a verification token; verify a domain.
     - OAuth Setup: show GAM's service-account keys; rotate the key (you
                    choose whether old keys are kept, replaced, or deleted).

   COLLABORATION AND RESELLER TASKS ADDED IN 2.42 (by category):
     - Google Chat: list every space in the organization (admin, 'asadmin'),
                    a space's members, its messages, and search messages;
                    create / rename / delete spaces; add / remove members and
                    change roles; post / edit / delete messages as a user or
                    as GAM's Chat bot; show / set Chat status; custom emoji.
                    NOTE: Google requires GAM's Chat bot for ANY Chat task -
                    run  gam setup chat  once (GAM wiki: Users - Chat).
                    FIXED: the v2.38 'admin' space/member lists used the bot
                    form (only spaces the bot is in) and 'List a user's Chat
                    messages' left out the required space.
     - Google Meet: create a meeting space with join rules; change its
                    settings; space info; end a running meeting.
     - Google Forms: create a form (optionally a quiz); rename; open or close
                    it for responses.
     - Google Sheets & Docs: download a Google Doc as JSON (Docs API).
     - Reseller / Channel: customer info / create / update; subscription
                    info / create; change seats, plan, or renewal; suspend,
                    activate, start paid service; cancel, downgrade, or
                    transfer to direct.
     - Marketing & Analytics: Tag Manager containers, workspaces, tags, and
                    permissions; share / unshare Looker Studio assets;
                    Search Console sites; verified web resources; Business
                    Profile accounts.
     - Vault:       download or copy a Google Takeout export bucket; download
                    one Cloud Storage file.
     - Chrome Browsers & Policies: Chrome version history.
     - Gmail:       show a user's signature; Gmail filter details.

   PASSWORDS ARE MASKED IN THE LOG: the value after any "password" keyword
   (new-user and reset passwords, S/MIME certificate passwords) is written to
   the session log as ******** . The command that runs is not changed.

   REQUIRED FREE-TEXT BOXES: a few tasks have a required free-text box (for
   example "Which events" on Purge specific events, or "Changes" on Update a
   building). Time values follow GAM's formats: a full time needs a time
   zone, e.g. 2027-01-05T09:00:00-06:00 (or Z for UTC); a Google Tasks due
   date is written 2027-01-15T00:00:00Z; many time fields also accept a
   relative value such as +90d. GAMGUI refuses to build the command if that box is empty,
   because leaving it off could change what GAM does (purge events with no
   selector purges EVERY event on the calendar). When a value in one of these
   boxes contains spaces, wrap it in DOUBLE quotes, e.g. query "Old Meeting".

   INCIDENT RESPONSE (Email Cleanup category): search every mailbox (or a
   domain / OU / group) for a malicious message (read-only preview), then
   trash or permanently delete matches with a per-mailbox limit as a seatbelt.
   The "Full incident-response workflow" runs the complete cleanup: 1) a scoped
   search saved to an evidence CSV, 2) a confirmation showing the hit count and
   requiring you to type DELETE, 3) deletion by exact Message-ID when available
   (falling back to the From+Subject query), 4) optional Drive sweep of the
   attachment, and 5) Gmail/Drive audit report pulls for the lookback window.
   All evidence is saved to a timestamped Incident folder under Logs, and
   canceling at the confirmation keeps the evidence while deleting nothing.

   For every task GAMGUI:
     - Builds the exact gam command from your form entries
     - Shows it in an editable preview BEFORE anything runs (so you learn the
       command, and can tweak it)
     - Runs it through YOUR gam executable and streams the output live
     - Requires an extra typed/dialog confirmation for destructive actions
     - Logs everything to a session log file

   GAMGUI never talks to Google itself and holds no credentials. All authority
   comes from your existing GAM authorization. If GAM is not set up, GAMGUI
   cannot do anything.

2. REQUIREMENTS
   - Windows 10/11 (prebuilt app). From source: any OS with Python 3.10+ and
     tkinter (macOS/Linux work too; see item 3).
   - GAM7 installed and authorized for your domain.
   - Admin rights: only whatever your gam commands themselves need. (Updating
     the Setup.exe install also needs Windows administrator rights - see item 9.)
   - Network access: what gam itself uses, plus api.github.com / github.com for
     the optional update check.

   FOR NON-TECHNICAL USERS: see HOW-TO-GUIDE.txt in this folder - a full
   plain-English walkthrough written for coworkers who have never used GAM or a
   command line. Hand that file to new users before their first use.

3. HOW TO GET AND RUN IT
   From the Releases page (https://github.com/GuruGabe/GAM-GUI-Overlay/releases)
   choose ONE Windows option:

   PORTABLE (recommended for a folder or network share):
     a. Download GAMGUI-<version>-Windows.zip and unzip it.
     b. Keep the whole GAMGUI\ folder together (GAMGUI.exe needs the _internal\
        folder next to it). A good home is C:\GAM7\GAMGUI\.
     c. Launch GAMGUI.exe. gam.exe is found automatically when GAM is installed
        normally (C:\GAM7). If not, click "Locate gam.exe..." (top right); the
        choice is saved in gamgui.ini.

   INSTALLER:
     a. Download GAMGUI-<version>-Setup.exe and run it (needs admin rights).
     b. It installs to Program Files, creates Start-Menu and desktop shortcuts,
        and registers in Add/Remove Programs. Launch it from the shortcut.

   Windows may warn about an unrecognized app because it is not code-signed;
   choose "More info -> Run anyway".

   macOS (.dmg) and Linux (.deb / .rpm / .tar.gz) builds are attached to each
   release as well.

   FROM SOURCE (Windows/macOS/Linux):
     a. Install Python 3.10+ (python.org; on Linux also install python3-tk).
     b. python GAMGUI.py

   BUILDING THE APP YOURSELF (Windows):
     a. py -m pip install pyinstaller
     b. Run Build-EXE.bat. It first runs extract_tcl.py (which pulls the
        Tcl/Tk 9 libraries out of the DLL's zip filesystem - required on
        Python 3.14, or the build crashes with "_tcl_data not found"), then
        builds the one-folder app with those libraries bundled.
     c. The result is dist\GAMGUI\ - copy the whole folder to its home.
     The one-folder (not single-file) layout is intentional: the single-file
     build crashed intermittently on Python 3.14 (Tcl/Tk 9).

4. OPTIONS AND SETTINGS
   GAMGUI takes no command line parameters. Settings live in gamgui.ini (next
   to the program for a portable copy, or in %LOCALAPPDATA%\GAMGUI for an
   installed copy that cannot write to Program Files):
     - gam_path       : the gam executable to use (set via Locate gam.exe...).
     - dark_mode      : View -> Dark mode (a soft low-contrast dark theme).
     - check_updates  : Help -> Check for updates at startup (on by default).
   In a form, fields marked * are required; others are optional and are simply
   omitted from the command when left blank.

   OUTPUT DESTINATION: any task that lists or exports results has a "Save
   results to" dropdown - the screen, a Google Sheet, or a CSV file on your PC.

   MULTIPLE DOMAINS: the Domain dropdown at the top runs a command against a
   chosen gam.cfg section (tenant) without changing your saved default - handy
   for MSPs. Single-domain setups just see "(default)".

5. WHAT IT CHANGES / SIDE EFFECTS
   GAMGUI itself changes nothing except writing gamgui.ini and log files. The
   gam commands you run change whatever they say they change - the preview box
   always shows the exact command first. Destructive tasks (delete/suspend/
   deprovision a user; delete a group/OU/course; powerwash/wipe/deprovision a
   device; sync membership; trash/delete messages; transfer a Drive; remove
   access/licenses; and the bulk equivalents) pop a confirmation showing the
   full command before running.

6. LOG FILES
   Logs\GAMGUI_MM-DD-YYYY_HH-MM-SS.log - one per session. Contains timestamps,
   every command run, all output, and exit codes. Note that a password you type
   into a "create user ... password X" form WILL appear in the log and on
   screen - prefer the random-password option (GAM generates it server-side),
   and treat any CSV that contains plaintext passwords as sensitive: store it
   safely and delete it after provisioning. Keep or purge logs per your
   organization's retention practice.

7. TROUBLESHOOTING
   "gam.exe not found"      - Click Locate gam.exe and browse to it.
   Output shows auth errors - Run a Diagnostics task (e.g. Authorization check);
                              re-authorize GAM if scopes are missing.
   Window frozen            - It should never freeze (commands run on a
                              background thread); long commands just take long.
                              Use Stop to kill a runaway command.
   "(Missing required value)" in the preview - fill in the starred fields.
   Bulk task did nothing    - Check the scope picker: it needs a value (an OU
                              path, a group, a query, or a file:column) unless
                              you chose "ALL".
   Update did not run       - See item 9. An installed copy needs an admin (UAC)
                              prompt; a portable copy must be closed first.

8. KNOWN LIMITATIONS
   - The guided forms cover the common options; the "Extra arguments (advanced)"
     box on each task and the "Run ANY GAM command (advanced)" console cover the
     long tail of GAM's thousands of command permutations.
   - Commands run WITHOUT a shell: arguments go straight to gam, so characters
     like & | > < and quotes inside subjects and queries are always safe. The
     trade-off: shell pipes (|) and > redirection do not work in the console -
     use GAM's own "redirect csv ./file.csv" or "todrive" instead.
   - GAM cannot create or grade Classroom assignments (a Classroom API limit),
     so those are not offered.
   - The preview is editable by design; treat it like a terminal and do not
     paste commands you do not understand.
   - English only.

9. KEEPING GAMGUI UP TO DATE
   IN-APP (easiest): GAMGUI checks for a newer release at startup (if online)
   and asks whether to update. Click Yes and it closes, updates itself, and
   reopens - it never updates without your OK. A portable copy updates in
   place (keeping gamgui.ini and Logs); an installed copy re-runs the installer
   with a Windows administrator (UAC) prompt. You can also use Help -> Check
   for updates now..., and toggle the startup check under Help.

   MANUAL (bundled script): updategamgui.ps1 in the app folder is what the
   in-app updater runs. Run it yourself, e.g. a weekly scheduled task:
       powershell -ExecutionPolicy Bypass -File "C:\GAM7\GAMGUI\updategamgui.ps1" -Quiet
   It auto-detects a portable copy, a Setup.exe install, or both, and updates
   each one that is behind. Switches: -InstallType auto|zip|exe|both,
   -InstallRoot "<path>", -Force, -Launch, -Quiet. Every download is verified
   against a SHA-256 published in the release notes. Update activity is logged
   to <install>\Logs\GAMGUI-Update.log.
================================================================================
