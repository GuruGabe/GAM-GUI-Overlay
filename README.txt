================================================================================
  GAMGUI 2.83 - A GRAPHICAL FRONT-END FOR GAM7
  Author: Gabriel Clifton
================================================================================

  This is the full reference manual. New, non-technical users should start
  with HOW-TO-GUIDE.txt (a plain-English walkthrough) and README.md (the
  illustrated overview with screenshots).

1. WHAT THIS PROGRAM DOES
   GAMGUI is a point-and-click front end for GAM7, the command line tool for
   Google Workspace administration (https://github.com/GAM-team/GAM).
   It presents over 710 admin tasks as fill-in-the-blank forms across 38
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
                    permissions; share / unshare Looker Studio assets (now
                    called Data Studio again, 2.79);
                    Search Console sites; verified web resources; Business
                    Profile accounts.
     - Vault:       download or copy a Google Takeout export bucket; download
                    one Cloud Storage file.
     - Chrome Browsers & Policies: Chrome version history.
     - Gmail:       show a user's signature; Gmail filter details.

   COMPLETENESS SWEEP IN 2.43 (by category):
     - Users:       hide / show a user in the shared directory; is a user
                    shown; list directory profiles; is a user suspended.
     - Aliases:     move an alias to another user or group.
     - Groups:      sync a user's groups to an exact list (removes them from
                    every other group - optionally limited to one domain).
     - Gmail:       create a draft in a user's mailbox; archive matching
                    messages into a Google Group.
     - Calendars:   show out-of-office / working location / focus time;
                    event details.
     - Drive:       upload a file from this PC (optionally converting to a
                    Google Doc / Sheet / Slides); full file details with
                    folder path; a file's folder tree; apply or remove a
                    Drive label on a file.
     - Shared Drives: Shared Drive details (admin).
     - Chromebooks: device telemetry (battery, storage, CPU, memory); the
                    result of a remote command; count devices in a scope.
     - Cloud Identity Devices: delete a device user.
     - Org Units:   is this OU empty? (check before deleting).
     - Custom Schemas: add or remove a field on an existing schema.
     - Buildings, Features & Rooms: delete a feature.
     - Contacts:    replace an old domain in a user's contacts; copy or move
                    Other contacts into My Contacts.
     - Classroom:   list student-group members; delete all student groups.
     - Vault:       copy a saved search to another matter.
     - Google Tasks & Keep: task details; move a task; Keep note details.
     - Google Sheets & Docs: create a spreadsheet from JSON.
     - Domains:     domain alias info; make a domain the primary domain.
     - Google Chat: message details.

   WHAT IS STILL CONSOLE-ONLY (use "Run ANY GAM command"): GAM's own setup
   and plumbing - creating GCP projects and service accounts, OAuth
   create / refresh / export, enabling APIs, YubiKey keys, and 'gam setup
   chat'. Plus a few rarely used variants (Chat sidebar sections, Gmail label
   operations by internal label ID, domain shared-contact photos).

   TEMPORARY ADMIN ROLES (2.45): Admin Roles & Privileges > "Assign a
   TEMPORARY admin role" (whole domain or one OU) grants a role that Google
   removes automatically at the expiration.
     - Type the expiration DATE as YYYY-MM-DD, MM-DD-YYYY, or M/D/YYYY.
     - Type the TIME as 24-hour (17:30) or 12-hour (5:30 PM), or leave it
       blank for midnight at the START of that date.
     - Both are in THIS computer's time zone. GAMGUI converts them to UTC
       ("Zulu", e.g. 2026-10-31T22:00:00Z) - the format Google's API needs -
       using the daylight-saving offset in effect on the date you enter. The
       converted time is what you see in the command preview.
     - The expiration must be in the future and within one year; GAMGUI
       refuses to build the command otherwise.
     - Requires GAM 7.48.06 or newer ('gam create admin ... expires').
     - 2.46: the same local date/time entry is now used by Groups > Add a
       member who expires on a date, Chrome Browsers & Policies > Create a
       browser enrollment token (optional expiration), Calendars > Create
       focus time (a date plus local start and end times), and Google Tasks
       & Keep > Create a task (the due date is date-only and is written as
       midnight UTC with NO time-zone shift, so it never moves a day).
     - "List admin role assignments" shows the end time in the
       expirationDetails.expireTime column (in gam.cfg's time zone - UTC
       unless you changed it).

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
     - Offers "Preview (dry run)" on 41 tasks (2.66): GAM shows what a real
       run would change, and changes nothing
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

   MACOS FIRST LAUNCH: GAMGUI is not signed with a paid Apple Developer ID or
   notarized, so macOS warns once ("cannot be verified"):
     - macOS 15 Sequoia and later: open it, click Done, then System Settings
       -> Privacy & Security -> "GAMGUI was blocked..." -> Open Anyway, and
       enter your password.
     - macOS 14 and earlier: right-click (Control-click) GAMGUI -> Open ->
       Open.
     - Or in Terminal: xattr -dr com.apple.quarantine /Applications/GAMGUI.app
   Releases 2.49 and earlier had a packaging bug that made macOS say the app
   is "DAMAGED" - fixed in 2.50; download 2.50 or later.

   MACOS: POINTING GAMGUI AT GAM AND gam.cfg (2.52): an app opened from
   Finder or the Dock does not get the Terminal's PATH or a GAMCFGDIR set in
   ~/.zshrc. GAMGUI now also looks for gam in GAM7's default ~/bin/gam7/gam.
   If your gam.cfg is not in ~/.gam, click Locate gam.cfg... (top right,
   2.54) and pick it (Cmd+Shift+. shows hidden folders; Cmd+Shift+G types a
   path). Check any download
   against the SHA-256 in its release notes (shasum -a 256 <file>).

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
                        If blank or missing, GAMGUI looks next to itself, on
                        the PATH, then in GAM7's default install folder
                        (C:\GAM7 on Windows; ~/bin/gam7 on macOS/Linux).
     - SIGNS IN AS (2.65): the status line under the top buttons shows the
                        gam program, the gam.cfg in use, and the Google
                        account GAM signs in as (from 'gam [select
                        <section>] oauth info', run in the background at
                        start-up and whenever the gam.cfg or Section
                        changes). Uploads to Google Sheets land in that
                        account's Drive, and GAM emails it a link unless
                        todrive_noemail = true in gam.cfg.
     - gam_cfg_dir    : Locate gam.cfg... (top right, or the Settings menu)
                        - the folder holding the gam.cfg you picked (GAM only
                        reads a file named exactly gam.cfg). When set, GAMGUI sets the
                        GAMCFGDIR environment variable for every gam it starts
                        and writes it into saved scripts (which stop with exit
                        code 3 if gam.cfg is missing there). Blank = GAM's own
                        default: GAMCFGDIR if set, else ~/.gam (checked in
                        GAM's source). The top bar shows the folder in use and
                        why; Settings -> Where is my gam.cfg? explains it.
     - dark_mode      : View -> Dark mode (a soft low-contrast dark theme).
     - check_updates  : Help -> Check for updates at startup (on by default).
     - text_size      : View -> Larger text / Smaller text / Normal text size
                        (Ctrl +, Ctrl -, Ctrl 0). A step number from 0 to 6;
                        1 is normal size.
   Favorites and the Recent list are kept in gamgui_tasklists.json in the same
   folder as gamgui.ini. Deleting that file simply empties both lists.

   BROWSER VERSION (gam_web.py) - 2.48 CHANGES:
     - SECURITY: only GAM Web's own page can use it. A random session token
       is created at each start and written into the page; every API request
       must send it (X-GAMWeb-Token header), must be JSON, and must arrive
       with an expected Host (localhost, 127.0.0.1, a Google Cloud Shell
       preview host, or one listed in the GAMWEB_ALLOWED_HOSTS environment
       variable). Before this, another web page open in the same browser
       could have sent commands to http://127.0.0.1:<port>/api/run.
     - FIX: typing quickly could leave an OLDER build of the command in the
       preview - and Run would use it. Each build is now numbered and only
       the newest one counts.
     - Date/time tasks convert in the VIEWER's time zone (sent by the
       browser), not the server's. If the server cannot resolve that zone and
       its own offset differs, it refuses with a clear message instead of
       producing a wrong time (install Python's 'tzdata' package to fix).
     - Added a task search box, a GAM docs link per task, and pre-filled
       defaults (Windows-only default paths are left blank on Linux).

   RUN ANY TASK FOR EVERY ROW OF A CSV (2.47): open a task, click "Run for
   each CSV row...", and pick a CSV whose first row holds column names. For
   each box choose the CSV column that holds its value, or keep the form
   value (same for every row). GAMGUI builds ONE command -
     gam csv <file> [maxrows N] gam <the task, with ~Column for mapped boxes>
   - shows it in the preview, and you click Run (destructive tasks still
   confirm). Details:
     - A mapped box becomes ~Column, or ~~Column~~ when the value sits inside
       a larger argument (GAM's documented CSV substitution).
     - "Test run: only the first N rows" adds maxrows N - try a few rows first.
     - Output: Screen, or ONE CSV file / ONE Google Sheet for all rows (GAMGUI
       uses GAM's 'redirect csv ... multiprocess' outside the loop).
     - The Section dropdown is applied INSIDE the loop ('gam select <section>'
       on each row), because GAM does not carry an outer select into it.
     - Dropdowns, the advanced box, and boxes GAMGUI translates (license
       names, dates/times, scope pickers) cannot vary per row.
     - Changing a box in the form afterwards rebuilds the single-run command;
       click "Run for each CSV row..." again to rebuild the bulk one.

   STAFF DEPARTURE HAND-OFF (2.57): Users -> Staff departure hand-off. One
   run hands a departing staff member's account to the person taking over.
   Each step is a Yes/No choice:
     - mailbox delegation      gam user <old> delegate to <new>
     - calendar editor         gam calendar <old> add editor <new>
     - forwarding (keep copy)  gam user <old> add forwardingaddress <new>
                               gam user <old> forward on keep <new>
     - auto-reply              gam user <old> vacation on subject ... message
                               ... (#old# / #new# filled in; \n = new line)
     - Drive transfer          gam create datatransfer <old> drive <new> all
                               (Google Data Transfer: private + shared files,
                               runs in the background at Google)
     - remove from ALL groups  gam user <old> delete groups   (default No)
   Afterwards the old account is one of:
     - Kept ACTIVE but locked: gam update user <old> password random, then
       gam user <old> deprovision popimap signout (no turnoff2sv: it fails
       where 2SV is enforced, and the password already locks the account -
       found in the live test). Forwarding and
       the auto-reply keep working; it still uses a license. The random
       password is not shown or logged (GAM only writes it out with
       'logpassword').
     - SUSPENDED: gam update user <old> suspended on. Google's help page
       "Suspend a user temporarily" says new email to a suspended user is
       blocked, so forwarding and the auto-reply stop - the confirmation
       says so when forwarding / auto-reply are on.
     - Put back the way it was.
   Delegation, calendar sharing, forwarding and the auto-reply act AS the old
   user, so a suspended / archived old account is enabled first (only when
   one of those steps is on). If the run stops early (Stop, an error), the
   account is put back to its original state. The preview lists every gam
   command; you type HANDOFF to run it; a summary shows OK / FAILED per step.
   Both accounts are looked up before anything changes.
   LIVE-TESTED (2.58) on two throwaway accounts in a test OU (created and
   deleted for the test): delegation "accepted", calendar ACL "writer" (GAM's
   name for editor), forwarding + auto-reply (blank line from \n kept), the
   Drive file changed owner (transfer "completed"), and a real test message
   reached the new account both forwarded and with the auto-reply. Found and
   fixed by that test:
     - 'turnoff2sv' FAILS where 2-Step Verification is ENFORCED by policy, so
       the lock step no longer uses it (the random password locks the
       account; app passwords, backup codes, tokens and POP/IMAP are still
       removed and the user is signed out).
     - Right after an account is switched back on, Gmail can answer
       "Delegator user is disabled" for a moment: the step is retried every
       15 seconds, up to 4 times.
     - Running a hand-off again: "already exists" (delegate / forwarding
       address already there) is shown as "OK (was already set)".

   REPORT BUILDER (2.53): Reports -> Report builder... writes ONE script
   that runs any mix of ready-made reports: a Windows batch file for Task
   Scheduler, or (2.55) a macOS / Linux bash script for cron.
   Each report is saved as CSV files in
       <output folder>\<report name>\<MM-DD-YYYY>\
   Reports: Admin activity (one file per admin, plus automatic-... files for
   SYSTEM / Security Center / device actions, plus _all-admin-activity.csv),
   Group membership changes, Password changes, Sign-ins from outside your
   countries, Accounts disabled for a leaked password, Suspicious sign-ins,
   Users with many failed sign-ins, Storage used per user, Active accounts
   not signed in lately, Accounts without 2-Step Verification, Suspended
   accounts, Chromebooks not used lately.
   COUNTERMEASURE (2.61): Drive -> Remove outside sharing listed in a report.
     1. Open the report's CSV (e.g. ...\Files shared outside\<date>\
        shared-outside.csv) and DELETE the rows you want to KEEP. Save it.
     2. Pick it in the task and choose what to remove: everything listed,
        only outside people, or only 'anyone with the link' / public links.
     3. The preview shows the counts; Run asks you to type REMOVE.
   It saves <report>-undo-<MM-DD-YYYY_HH-MM-SS>.csv next to the report FIRST,
   then runs, as each file's owner:
       gam csv <list> gam user ~owner delete drivefileacl ~doc_id ~perm
   (perm = the outside address, anyonewithlink, or anyone). Rows are skipped
   (with the reason shown) for shared-drive files, access that was already
   removed, and rows without a file ID or owner. "Delete Failed: Does not
   exist" means the file or that access is already gone.
   Drive -> Put back sharing from an undo file re-adds it (type RESTORE):
       gam user ~owner add drivefileacl ~doc_id user ~target role ~role
       gam user ~owner add drivefileacl ~doc_id anyone role ~role withlink
       gam user ~owner add drivefileacl ~doc_id anyone role ~role
           allowfilediscovery true
   People get back the role the audit log recorded (can_edit = writer,
   can_comment = commenter, can_view = reader); links come back view-only
   (the audit log does not record a link's role). No emails are sent.
   The report itself (2.61) now leaves out events where outside access was
   REMOVED, and keeps the new_value (role) column the undo file needs.
   LIVE-TESTED (2.62) on throwaway accounts with a REAL report from the Drive
   audit log (it showed the test shares about 6 minutes after they were
   made): a file shared with a person, one with 'anyone with the link' and
   one public on the web were all un-shared (3 of 3 'Deleted', then only the
   owner left), and the undo file put back exactly the same sharing (person
   as editor, link and public as viewer). Found by that test and fixed:
   creating a file logs the OWNER being given access to it (new_value
   'owner'); the report now drops those events and the remove step never
   touches the file owner's own access. The put-back summary now counts
   what was added per kind.

   Added in 2.59: Files shared outside your domains (Drive audit log,
   change_document_visibility + change_user_access). You list your own
   domains (sub-domains are included, so example.org also covers
   students.example.org) and, optionally, partner domains to ignore. A row
   is kept when a PERSON outside those domains got access, or (optional)
   when a file was opened to anyone with the link / the web. GAMGUI does not
   rely on Google's 'visibility_change = external' flag: in a live test it
   also marked many shares to people inside the domain. It uses the plain
   list form of GAM's row filters - the JSON form of
   csv_output_row_drop_filter was silently ignored in the same test.
   Added in 2.56: Admin role changes, App access and SSO changes (both
   alert reports), Account changes, and Accounts using the default profile
   picture (one OU and its sub-OUs, or all active accounts - uses the _ns
   selectors so suspended accounts are skipped). Every event name in these
   reports was checked one by one against the live Reports API: an unknown
   name makes the whole report fail ("Event ... not found in manifest").
     - Every command starts with "config timezone local", so "Yesterday" is
       the local calendar day (GAM's default is the UTC day) and times in
       the CSVs are local.
     - "One file per admin" = one GAM call for the whole day, then PowerShell
       splits it by the admin's email (actor.email), so the per-admin files
       always add up to the day. (A per-admin GAM loop was tested and
       rejected: GAM's csv loop does not pass the local time zone to its
       child processes, so those files covered the UTC day instead.)
     - The out-of-country report uses networkInfo.regionCode, the country
       Google records for each sign-in. No IP addresses go to any third
       party.
     - Folder dates come from PowerShell, so they do not depend on the PC's
       regional date format.
     - Output folder: blank = a Reports folder next to the script. Clean-up
       (optional): dated folders older than N days are deleted - only
       folders named MM-DD-YYYY inside this script's own report folders.
     - Log: Logs\<script name>.log next to the script. A failed report is
       logged and the rest still run. Exit codes: 0 all worked, 1 a report
       failed, 2 gam.exe missing, 3 gam.cfg missing (when a GAM config folder
       is set), 4 could not read the date.
     - The script's first comment block holds its settings (one base64
       line); "Open a saved report script..." reads it back for editing.
     - The window remembers your last choices (gamgui.ini report_builder).
     - Scheduling: Task Scheduler > Create Task; "Run whether user is logged
       on or not" as an account that can read the GAM config folder; Daily
       trigger after midnight; Action = Start a program > the .bat.
     - Keep the .bat in a folder whose path has no & ( ) % ^ ! - cmd.exe,
       which Task Scheduler uses to start it, drops the quotes around such a
       path. GAMGUI warns before saving there (Save as script too).
     - SECURITY: the reports hold names, emails, sign-in IPs and locations.
       Keep the output folder readable only by IT.
     - GOOGLE SHEETS (2.54): each report can also replace one tab of an
       existing Google Sheet (paste the sheet's link or file ID; tab blank =
       the report's name). GAM arguments: todrive tdfileid <id> tdretaintitle
       true tdsheet <tab> tdupdatesheet true tdnobrowser true tdnoemail true
       tdlocalcopy true [tduser <Sheets account>]. tdlocalcopy matters: with
       todrive, GAM writes no local CSV without it (checked in GAM's source).
       A wrong file ID fails that report before any data is read ("Drive
       File ID: ..., Not Found", exit 2) - check the log after the first run.
       Tested live: the tab read back from Google matched the local CSV.
     - EMAIL SUMMARY (2.54): Never / Every run / Only when an alert report
       finds something (alert reports: sign-ins outside your countries,
       leaked-password lockouts, suspicious sign-ins, many failed sign-ins;
       a failed report also triggers it). Body = Logs\<name>-summary.txt (row
       count per report). Optional attachments: each report's main CSV when
       it has rows and is 5 MB or less. Sent with 'gam sendemail <to>
       [from <addr>] subject ... file <summary> attach ...' as GAM's admin
       account (or From), so no SMTP password is stored. Tested live.
     - Every run writes Logs\<name>-summary.txt, emailing or not.
     - MACOS / LINUX (2.55): Script type = "macOS / Linux shell script (.sh)"
       writes a bash script that does the same things. It uses only what a
       stock Mac has: bash 3.2, the system awk, and date (it tries GNU
       'date -d' first, then BSD 'date -v'). "One file per admin" is split
       by a small awk CSV reader (quoted commas, doubled quotes and line
       breaks inside values are handled; records are copied unchanged).
       Schedule it with cron, e.g. crontab -e, then add this line:
           0 1 * * * '/full/path/GAM-Daily-Reports.sh'
       The .sh can be made on any system (e.g. on Windows for a Linux
       server). Tested with real bash, awk in strict POSIX mode, and a
       stand-in for BSD date; a live run on a real tenant split 67,048 admin
       events into 13 files with every event in the right file.

   SAVE AS SCRIPT (2.51): the "Save as script..." button (next to Copy)
   saves the command in the preview as a script that runs it exactly:
     - Windows: a .bat with a standard header block, @ECHO OFF / SETLOCAL, a
       GAM path line you can edit, and a log at Logs\<script name>.log next
       to the script (MM-DD-YYYY HH:MM:SS start/end lines, GAM's output, and
       the exit code). The script exits with GAM's exit code, so Task
       Scheduler can report failures. CRLF line endings.
     - macOS / Linux: a .sh (bash) with the same logging; schedule with cron.
     - Special characters (& | < > ^ % quotes) are escaped so cmd.exe passes
       every argument to GAM unchanged - proven by running generated scripts
       through the real cmd.exe (tests/test_script_export.py).
     - WARNINGS before saving: a command containing a password (it would be
       stored in plain text in the script), and destructive tasks (a script
       runs without the confirmation GAMGUI normally shows).
     - The Section dropdown's choice is included in the script.
     - Multi-step workflows (incident response, bulk license, etc.) cannot be
       saved as one script.

   2.83 - COMPROMISED ACCOUNT SECTION; PICK... FOR COURSES, DEVICES, ROOMS;
          GAM 7.48.21 CHECKED:
     - Compromised Account (Gabe's idea): workflow "compromised"
       (GamGui._run_compromised / _compromised_plan, pure and tested) and
       "compromisedchecklist". Order: CONTAIN (update user <u> password
       blocklogin - GAM's unusable random password; user <u> signout),
       EVIDENCE (read-only; .txt from 'show' output, CSV via 'redirect csv'
       for print / report: info user, show filters / forward /
       forwardingaddresses / delegates / sendas / vacation / imap / pop /
       asps, print tokens, print mobile query email:<u>, print messages
       query "in:sent newer_than:<n>d" max_to_print 500, report login /
       drive / gmail user <u> start -<n>d), REMOVE (user <u> deprovision =
       app passwords + backup codes + tokens; imap off; pop off; optional
       turnoff2sv), SUSPEND last (GAM cannot remove backup codes from a
       suspended user). Typed confirm CONTAIN; mode 'none' = evidence only,
       no question. Folder Logs\Compromised_<user>_<stamp> with Summary.txt
       and NEXT-STEPS.txt (gam_catalog.COMPROMISED_CHECKLIST). Report steps
       get a 10-minute limit (_capture_gam timeout - kills the process
       tree): a real busy account had 50,000+ token events a week, so the
       app-authorization log is NOT collected ('print tokens' shows the
       apps that have access); its Drive log took 80 s for 7 days. Every
       command passes GAM's parser; the evidence steps were run read-only
       on a real account (temp files deleted). If From / Subject are given,
       _offer_email_cleanup opens the Full incident-response workflow
       filled in (_open_task_filled). LIVE TEST 10-06-2026 on a throwaway
       user in a test OU with a planted filter, auto-reply and IMAP/POP
       on: every step worked (lock, sign out, 15 evidence files - the
       planted filter and auto-reply were captured - deprovision, IMAP and
       POP off, suspended last); turnoff2sv was refused because that OU
       ENFORCES 2-Step Verification ("required by admin policy") - the
       workflow now says so in plain words. The test user was deleted.
       F(..., picker="user") gives a
       workflow box the Pick... list. Search: hacked / compromised /
       breach / takeover / phished.
     - Email Cleanup boxes: _mail_fields() (from, subject, msgid, more) on
       Search / Trash / Delete from mailboxes, Delete from ONE mailbox and
       the targeted workflow; token {mailquery:from:subject:msgid:more} ->
       ONE argument, mail_query() = incident_query (from:x subject:(words))
       + rfc822msgid:<id> (< > removed) + more; blank = refused. The
       Gmail category's own trash / spam keep a general query box.
     - Course picker (gam_catalog.course_picker / parse_course_list,
       GAMGUI._pick_course): every box whose GAM word is 'course',
       'courses', 'course-studentgroups' or 'course-studentgroup-members'
       gets 'Pick...' (38 boxes). Columns: name, section, teacher (owner),
       state, ID; Find searches all of them; the course ID goes in the box.
       Lists (read-only, kept per Section like the other pickers):
         courses     - print courses states active,provisioned
                       fields id,name,section,coursestate owneremail
         courses_all - the same without 'states' (every course) - ticked
                       by 'Include archived courses'; Delete course and
                       Reactivate open with it ticked.
       Checked read-only in a real district: 1,623 active + provisioned
       courses in about 35 seconds; all 14,332 courses in about 130
       seconds. GAM exits 56 ('does not exist') when a course's owner
       account was deleted (the row says 'Unknown user') - the list is
       complete, so _gam_list now takes per-list accepted exit codes and
       timeouts (courses 600 s, courses_all 1800 s; others unchanged:
       exit 0 only, 300 s). A newer load always wins over an older one
       still running. Screenshot: docs/img/course_picker.png
       (tests/make_shot_283.py, made-up data).
     - More ID pickers (gam_catalog.id_picker / parse_id_list): 'Pick...'
       on the box of 'info|update|delete browser|printer|building|resource|
       alias {x}' (15 boxes; create commands and the course-alias tasks get
       none). Lists: print browsers fields deviceid,machinename,orgunitpath,
       lastactivitytime; print printers; print buildings; print resources;
       print aliases (GAM walks every user and group for this one - about
       40 seconds in a real district).
     - Calendar list (gam_catalog.calendar_picker / calendar_rows;
       PICK_TABLES 'calendars' combine=('users','resources')): every
       'calendars {x}' box except 'remove calendars' (secondary delete) and
       calendar transfer - 20 boxes. combine_rows(kind, parts) now builds
       every combined table (members, calendars) on both apps. Real
       district: 8,226 people + 234 rooms in 17 s.
     - Chromebooks are SEARCHED too (gam_catalog.chromebook_picker, 13
       'cros_sn {x}' boxes): SEARCHED_LISTS holds each searched list's
       allowed text (lower-cased; letters, digits, . _ @ -, 3+), its fixed
       queries and its 'bad text' message. Chromebooks run 'print cros
       fields deviceid,serialnumber,annotatedassetid,annotateduser,
       orgunitpath,status,lastsync query <q>' for id:<t>, asset_id:<t> and
       user:<t> (2-5 s together in a real district; a bare word is refused
       by GAM - every query must be field:value), merged by serial
       (merge_search_rows). The serial number goes in the box. Device ID is
       a width-0 column: searched by Find, not shown.
     - Mobile devices are SEARCHED, not listed: 'print mobile' took 6
       minutes for 43,000 devices in a real district, but 'print mobile
       fields resourceid,email,model,os,status,lastsync query
       email:<start>*' answers in about 2 seconds. The window opens empty;
       type the start of the address and press Enter / Search
       (gam_catalog.mobile_search_query: letters, digits and . _ @ + -
       only, at least 3 - so the text can only ever be an address search).
       Typing more narrows the rows already found; Enter with new text
       searches again; Refresh list repeats the last search. 5 boxes.
     - address_picker also covers teacher(s) / student(s) / delegate /
       contactdelegate (users: 282 boxes now) and cigroup(s) (groups: 28),
       never 'create cigroup'. member / admin / owner stay typed - they may
       be a user, a group or an outside address.
     - FIX - "name or ID" boxes: GAM's Matter/Query/Hold/Export items are
       a name or id:<ID> (<UniqueID> ::= id:<String>) and <RoleItem> is
       id:<RoleID>|<RoleName>; a BARE ID is looked up as a name ("Does not
       exist" - checked on 7.48.20 for a matter, a saved query and a role).
       _mark_unique_id_boxes gives each box an idform and build_command
       turns each matching comma item into id:<ID> (unique_ids; names and
       id:/uid: values untouched): uuid (Vault matters + saved queries, 25
       boxes; every real ID is a UUID) and roleid (all digits, 10+; 7
       boxes; all 43 real role IDs are 15 digits, no role name is all
       digits). Hold / export IDs: no real example to check the shape, so
       their labels now say '(name, or id:<ID>)' instead of guessing.
       Verified: the built 'info matter id:<ID> basic' finds the matter.
       ssoid (4 SSO profile boxes): GAM 7.48.20 wants id:<ID> and adds
       'inboundSamlSsoProfiles/' itself; a bare ID and the printed
       'inboundSamlSsoProfiles/<ID>' are looked up as display names ("No SSO
       profile matches display name"), and the WIKI's documented
       id:inboundSamlSsoProfiles/<ID> failed before GAM 7.48.22 ("does not
       match the pattern"; fixed in 7.48.22) - all three now become
       id:<ID>, which every GAM version accepts; real IDs are 15 lower-case
       letters /
       digits starting with 2 digits. Verified with real profiles.
     - Calendar events + doit (GAM issue #1997, opened 10-06-2026): GAM's
       'delete|purge events' delete NOTHING without doit (documented), but
       7.48.20's purge without doit still destroys the events (moved to a
       temporary calendar that is deleted). GAMGUI's Delete event(s) sent no
       doit (so it never deleted), and Purge relied on the bug. Both now
       carry a task 'tail' ("doit",) that build_command adds AFTER the typed
       selection (GAM reads calendar, selection, then options - a selector
       after doit is an unknown argument; verified by GAM's parser against a
       non-existent calendar / user). A tail task never offers a dry run.
       Delete event(s)' selector is now required (blank = every event). The
       old example 'events id:<eventId>' was wrong ('events' takes the next
       word as the ID): now query "Fire Drill" / eventid <id>.
       known_gam_bug(argv, gam_version) warns before a typed 'purge events'
       without doit (desktop Are you sure + web /api/classify 'warning') -
       only when the GAM is older than 7.48.21 or its version is unknown:
       GAM 7.48.21 (released 10-06-2026) fixed #1997, so from then on purge
       WITHOUT doit does nothing - GAMGUI's purge task needs its doit tail.
       gam_web asks 'gam version' once (gam_version(), cached).
     - Examples for raw (Extra arguments) boxes checked by GAM's parser:
       tests/parse_check_gam.py --examples puts each example from a raw
       box's label and its task's description ('e.g.  A  or  B', placeholders
       such as <id> / ... skipped, examples that a normal box's label shows
       skipped) into the raw box and runs it with the SAME safety rules as
       the parse check (non-existent targets, create/send never run).
       'EXAMPLE FAIL' = GAM stopped at the example's own word. Found and
       fixed: single quotes (win_split groups only "double quotes" - like
       cmd), contact email / organization need primary|notprimary, 'events
       id:<eventId>' / 'events query' (events takes an ID list), signature
       '&{name}' (GAM: {Tag} + replace <Tag> field:<name>), cigroups 'a
       query'. Result 10-06-2026: 31 PASS, 0 FAIL, 9 REVIEW (all stop at a
       stand-in value), 30 SKIPPED. test_v283 guards quotes / 'events id:'.
     - Meet conference boxes (3, field 'addprefix'): GAM passes the value
       straight to Google as the parent, which must be
       conferenceRecords/<ID> (_printShowMeetItems), so a bare ID (letters,
       digits, _ -) gets that prefix. No real conference to test with -
       from GAM's source.
     - Vault matter list (matter_picker): 'print vaultmatters fields
       matterid,name,state,description' (33 in 3 s in a real district);
       the ID goes in the box and is sent as id:<ID>.
     - Shared Drive list (gam_catalog.shareddrive_picker): every box behind
       a {shareddrive:KEY} token (14). 'print shareddrives fields
       id,name,createdtime,orgunit' (396 drives in 8 s in a real district,
       5 names used twice). The ID goes in the box; the token sends it as
       'shareddriveid' (all 396 real IDs match its 0A... pattern).
     - Users-and-groups list (gam_catalog.member_picker /
       MEMBER_PICKER_RULES / member_rows; PICK_TABLES 'members' with
       combine=('users','groups')): 22 boxes that take either (group
       members, create admin, drivefileacl, chatmember, Keep / Drive label
       {whotype}, update alias {ttype}); plus 10 user boxes (oauth
       create|update admin, transfer ownership / drive new owner, Classroom
       owner, 'delegate to') and 2 group boxes ('info member', 'archive
       messages'). Each rule is the command's exact shape - e.g. the File
       ID box of 'transfer ownership {fileid} {newowner}' gets nothing. The
       two lists load (and are kept) separately and are merged with a Type
       column; if either fails the error shows, never half a list.
     - Browser version (gam_web.py): the same lists. gam_catalog now holds
       PICK_LISTS (kind -> argv, parser, accepted exit codes, timeout -
       moved out of GamGui._gam_list) and PICK_TABLES (columns etc. - moved
       out of GAMGUI.py, plus 'ous' and 'roles' for the browser),
       pick_rows() and web_picker(task, field). /api/tasks gives each box
       its 'picker'; GET /api/picktables the layouts; POST /api/list
       {kind, all, text, refresh} runs only a PICK_TABLES list (anything
       else: 'Unknown list.'), validates mobile text on the server too,
       and keeps results in memory. 414 boxes there (OU boxes only when
       they always take an OU). tests/test_web_pickers.py runs it against
       a stand-in gam (GAM_PATH) that records every command: all 'print'.
     - One picker window for all of these (GamGui._pick_table, driven by
       PICK_TABLES): users, groups, courses, the five lists above and
       mobile devices.
     - GAM 7.48.19 / 7.48.20 checked (release notes, GAM's own source and
       every GAMGUI command parsed by the new gam.exe): nothing GAMGUI uses
       changed. 7.48.19 also brought back 'gam show browsers' (7.48.17 had
       dropped it by mistake; GAMGUI uses 'print browsers').
     - Linux installers: the GitHub build now names Ubuntu 24.04 instead of
       'ubuntu-latest', which GitHub moves to Ubuntu 26 from 10-19-2026.
     - HOW-TO-GUIDE.txt: 'Picking a user or group without typing the
       address' (the 2.82 Pick... button). README.md: the same, with a
       screenshot (docs/img/user_picker.png, made-up names -
       tests/make_shot_282.py).
     - Create a course: optional 'Grade level(s)' box -> 'levels <text>'
       (GAM 7.47.07). Free text: real Classroom courses hold values such as
       '5th Grade', '9-12', '6th/ 7th/ 8th Grade' (checked read-only with
       'print courses fields levels'). GAM_VERSION_NEEDS now has 'subject'
       and 'levels' with 'course' (7.47.07) - the existing Subject box
       needed that version too but had no warning.

   2.82 - PLAIN-ENGLISH CHOICES EVERYWHERE:
     - Every dropdown now shows plain English instead of GAM's own words
       (the GAM command is unchanged): group roles (Member / Manager (can
       manage the members) / Owner (full control of the group)), Create
       alias ('The alias is for' A user / A group / Let GAM work out
       which), out-of-office / working location / focus time, Classroom
       invitation roles, Count courses for each student / teacher, Vault
       matter detail, the Activity report list (e.g. 'Apps given access -
       OAuth (token)' - GAM's word stays in brackets), usage report
       parameters. tests/test_v282.py fails if a raw GAM word comes back.
     - 'Undo:' notes: 108 destructive tasks now end their description with
       how to undo them (the GAMGUI task that puts it back) or 'Undo: none
       in GAM' with what to export first. Facts only: GAM's own undo
       commands are undelete user / vault matter / alert and untrash Drive
       files / Gmail messages; tasks where Google's behaviour is not
       certain have no note (gam_catalog.UNDO_NOTES).
     - FIX: 'Who is GAM authorized as?' - 'show scope details' never
       reached GAM (the template's optional part had no field in it, so it
       was always dropped). A test now checks every template for this.
     - Search synonyms (gam_catalog.SEARCH_SYNONYMS / SEARCH_PHRASES): each
       typed word may also match a synonym - disable/lock/block = suspend,
       offboard = deprovision / departure / hand-off, mfa/2fa = 2-Step,
       ooo / 'out of office' = vacation / auto-reply, erase/wipe =
       powerwash, 'address book' = Global Address List / directory, 'new
       hire' = create user, seat = license, recover = undelete / untrash /
       restore, remove = delete / revoke. The browser version now asks
       the server (POST /api/search) so it searches exactly the same way -
       before, it only matched the typed text against task names.
     - User / group picker: boxes that take an EXISTING user ('user {x}' /
       'users {x}' in the command) or group get a 'Pick...' button
       (gam_catalog.address_picker). The list comes from the read-only
       'gam print users fields primaryemail,name' or 'gam print groups
       fields email,name', is kept for the session (Refresh list re-reads
       it), and shows at most 500 matches at a time - type part of a name
       or address to narrow. Enter picks the match when only one is left.
       Boxes that name a NEW user or group get no picker.
     - GitHub releases now come once a day (5 PM Central) with the day's
       changes together.

   2.81 - CLEAR ON/OFF CHOICES, ARCHIVE USERS:
     - Gabe: 'Suspend / unsuspend user' offered Action 'on' / 'off' - does
       'on' suspend the account (GAM's meaning) or turn it on? Every bare
       on/off choice now says what it does (the GAM command underneath is
       unchanged): Suspend / unsuspend (Users and Common Tasks), Hide/show
       in the Global Address List, Turn IMAP / POP on/off, Disable /
       re-enable a Chromebook (one and BULK). A test fails if a bare
       on/off or true/false choice comes back.
     - New: Archive / unarchive user ('update user <email> archived
       on|off'), BULK: archive / unarchive users, Archived users report
       ('print users isarchived'). The descriptions explain Archived User
       licenses.
     - FIX: a command built from the form was never checked for being
       destructive, so 'Suspend' chosen in the dropdown ran without "Are
       you sure?" (only typed/edited commands were checked). Every command
       is checked now; tasks already marked destructive keep their own
       confirmation. Newly asking: Suspend, Archive, a subscription's
       renewal set to cancel, disabling a CSE key pair.

   2.80 - TASKS GROUPED, CHROMEBOOKS IN GRADE-NAMED OUs:
     - Every category with more than 12 tasks now shows its tasks under
       headings that keep companion tasks together (gam_catalog.TASK_GROUPS:
       e.g. Drive > Look up a file / Look at a user's Drive / Sharing /
       Outside sharing & bad files / Ownership & transfers / Upload, create,
       copy & move / Trash, restore & delete / Drive labels). Smaller
       categories got a better order. Task names did not change, so
       Favorites, Recent and saved scripts are unaffected. The browser
       version shows the same headings. Headings are in italics.
     - Chromebooks > Move Chromebooks up a grade in grade-named OUs: for
       Chromebook OUs named 'Grade 5' / '5th Grade' / 'Kindergarten' /
       'PK'. Moves the Chromebooks DIRECTLY in each OU up one grade with
       'gam update org <new OU> move cros_ou <old OU>', highest grade first.
       Safety: never mixes two grades (an OU whose Chromebooks cannot move
       blocks the grade below), seniors need a graduated OU (or an explicit
       'leave them'), two possible next-grade OUs = a warning, OUs holding
       'Class of' OUs and student ACCOUNT OUs are not included by default,
       and finished steps are remembered per school year (gamgui.ini
       gradeou_done_<section>) and never run again; a failed step stops the
       steps below it.
     - Live-tested on empty OUs in a test OU (12 -> graduated, 11 -> 12,
       10 -> 11, then shown as done).

   2.79 - DATA STUDIO NAME, POLICY FIX VERSION:
     - Google renamed Looker Studio back to Data Studio (GAM 7.48.10). The
       four Marketing & Analytics tasks are now named 'Data Studio (Looker
       Studio)' - searching either name finds them. GAMGUI already sent
       GAM's datastudio... commands. Favorites and Recent saved under the
       old names are translated (gam_catalog.TASK_RENAMES).
     - Transfer data to another user: 'Data Studio' added to the examples
       (GAM 7.48.01+).
     - 'Create or update a Cloud Identity policy from JSON' aimed at an OU
       or group: GAMGUI warns before running on GAM older than 7.48.02,
       which always failed that way (GAM issue #1974, Error 7016).

   2.78 - GAM 7.48.17: CHAT MESSAGE SEARCH IS NO LONGER A DEVELOPER PREVIEW:
     - Chat > Search a user's Chat messages: the description now says it
       needs GAM 7.48.17+ (older GAM still needs the Developer Preview
       settings in gam.cfg). Checked with gam.exe 7.48.17: it runs without
       them now.
     - The 'Developer Preview is required' hint now suggests updating GAM
       first.
     - Full parse check of every task against GAM 7.48.17.

   2.77 - CHROMEBOOK ROLLOVER: TWO FIXES FROM THE LIVE TEST:
     - After a rollover the window still said the OUs were set up for LAST
       school year, so 'Find class OUs' planned a second rollover. GAMGUI
       now remembers the year it finished a rollover for (gamgui.ini,
       classof_year_<section>; saved only when every step worked) and shows
       it; 'Prepare for' defaults to next year only from March to August.
       The confirmation names both years.
     - Which OU holds a grade: whole OUs, most Chromebooks first (then fewest
       grades). Before, a small alternative high school holding grades
       10-12 would have taken them from the real high school (9-12).
       Double-click an OU to put it in the grade ladder or take it out.
     - Live tests 10-02-2026: rollover on a fake district inside a test OU
       (8 of 8 done, finding again plans nothing, real tree checked, then
       deleted); Shared Drive scan / remove / put back on a
       temporary Shared Drive with an 'anyone with the link' Doc (all
       passed, then deleted).

   2.76 - SHARED DRIVE SHARING, CHROMEBOOK ROLLOVER, RETIRE, DLP LISTS:
     - Drive > Find outside sharing on Shared Drives - CSV report (read-only):
       outside MEMBERS of each Shared Drive (print shareddriveacls) and
       outside sharing set on the files in it (gam csv <organizers> gam user
       ~organizers print filelist select teamdriveid ~id ... pm ...
       inherited false em pmfilter oneitemperrow - Ross Scroggs, GAM Public
       Chat). Drives with no organizer in your domains are listed in a
       NotScanned CSV (a non-member scan silently returns nothing).
     - Drive > Remove outside sharing listed in a report now also takes that
       Shared Drive report: files as the drive's organizer, a drive's own
       members with admin rights, by permission ID. The undo file has a new
       'scope' column; Put back handles groups, domains and drive members.
     - Chromebooks > Move 'Class of' Chromebook OUs up a grade: finds class
       OUs by their naming pattern (2- or 4-digit years, extras like
       Bluetooth inside or beside them), works out which OU holds which
       grade (grade = school year + 13 - class year), shows the plan, then
       moves (update org <path> parent <new>) and creates (create org <leaf>
       parent <parent>). Re-running only does what is left; the plan and
       results go to Records.
     - Chromebooks > Retire Chromebooks: powerwash, then deprovision; stops
       before deprovisioning if a powerwash fails. ALL devices not offered.
     - Access & Identity > Edit a DLP detector's URL or word list (window;
       old version saved to Records; update policy json file).
     - GAM 7.48.15 / 7.48.16: List a user's calendars can show only the
       organization's calendars (showownorganizationonly); Download a Google
       Doc as JSON has Suggested edits and Comments choices.
     - All new commands checked with the real gam.exe; full parse check of
       every task against GAM 7.48.16: no FAIL.

   2.75 - FROM THE GAM PUBLIC CHAT (questions people asked, Jul-Sep 2026):
     - Groups > List EVERYONE in a group, including nested groups: people
       through every nested group (each listed once), or the nested groups
       themselves - including EMPTY ones, which 'recursive' alone misses.
     - Calendar > Move a user's events to another calendar: the events a
       leaving user ORGANIZED move to a calendar their replacement owns
       (upcoming only by default; out-of-office / focus time / working
       location cannot move). The user needs edit access to the
       destination first - the description says so. Asks "Are you sure".
     - Calendar list tasks (add / show-hide / both BULK ones): new box
       "Name shown in their list" (GAM 'summary' = the user's own name for
       it; only the owner can rename the calendar itself).
     - Export all aliases: optional "Only aliases in this domain" box, to
       find (then bulk delete) the aliases of an old secondary domain.
     - File details: also shows the Shared Drive's name.
     - Deprovision (one / BULK): tip - powerwash FIRST if it should be
       wiped; a deprovisioned device no longer takes commands.
     - New "What this usually means" hints: damaged service account key
       (oauth2service.json), "Writer access required to both calendars",
       "owner access to this calendar", a class whose owner is suspended,
       a group chat listing its creator, "Service/App not enabled", and
       Google's "service is currently unavailable".
     - All new syntax checked with the real gam.exe (GAM read every word).

   2.74 - CLAIM OWNERSHIP OF A WHOLE FOLDER:
     - Drive > Claim ownership of a file/folder now has boxes for GAM's
       options (checked in GAM's source, claimOwnership, and with gam.exe):
         retainrole reader|commenter|none  (default: old owners keep EDIT)
         subdomains <domains>  (by default only owners in the claiming
                                user's own domain are included)
         includetrashed, filepath (paths in the Preview list)
       On a FOLDER, GAM claims everything inside it, every sub-folder down.
     - Marked DESTRUCTIVE ("Are you sure"), typed or from the form - it can
       move ownership of thousands of items. Preview (dry run) as before.
     - From a GAM-list question: a curriculum folder many teachers fill all
       year, handed to a role account at the end of the year.

   2.73 - COMMENTS (and ready for Google's new comment/suggestion APIs):
     - Google (09-30-2026) added WRITING comments and suggestions to the
       Docs, Sheets and Slides APIs. GAM 7.48.14 can only READ comments
       (print|show filecomments, Drive API). GAMGUI covers all of that:
         Drive > List comments on a file (new: include deleted comments)
         Drive > Which of a user's Docs, Sheets and Slides have comments?
                 (counts) - print filecomments my_commentable_items
                 positivecountsonly (GAM 7.01.02+)
       Both open the GAM wiki page Users-Drive-Comments.
     - When GAM adds the new commands, the GAM Change Watch report shows
       them FIRST (watch_topics.txt), and NOTES.md lists the tasks to add.
       Commands GAM has not published are NOT guessed.

   2.72 - EVERY COMMAND CHECKED AGAINST THE REAL GAM PARSER:
     - GamCommands.txt is not always what gam.exe accepts. tests\
       parse_check_gam.py asks the INSTALLED gam.exe about every task: it
       adds a nonsense last word, points every target (user, group, OU,
       file, device, ID) at something that does not exist, never runs a
       create/add/send-style command or a GAM setup command, and reads GAM's
       >>>word<<< marker to see how far GAM got. PASS = GAM read the whole
       command; FAIL = GAM stopped at one of the task's own words.
       (Lesson: a few GAM commands - delete alert, delete inboundssoprofile /
       assignment, empty drivetrash - call Google BEFORE rejecting the extra
       word, so the non-existent targets are what really keep it safe.)
     - Fixed (GAM 7.48.14 rejected them): print course-works -> course-work;
       print channelcustomercentitlements -> channelcustomerentitlements;
       print tagmanagerccounts -> tagmanageraccounts (NOT a GAM quirk as
       2.39 said - only GamCommands.txt / a source comment spell it that
       way); calendars <cal> transfer <user> -> transfer ownership <user>;
       print alertfeedback alert <id> -> alertid <id>.
     - Worked around a GAM bug: top-level 'gam sync shareddriveacls' crashes
       (TypeError: copySyncSharedDriveACLs() missing 'users'); the task now
       runs 'gam user <admin> sync shareddriveacls ... asadmin' (new Admin
       email box).
     - Search a user's Chat messages: its description now says it needs a
       Developer Preview key in gam.cfg (developer_preview_apis = chat,
       developer_preview_api_key).
     - Error hints: "invalid_grant: Invalid email or User ID" means the user
       does not exist (it was wrongly explained as an expired sign-in);
       "Developer Preview is required" explained.
     - GAM Change Watch reports now remind you to run the parse check after
       installing a new GAM.

   2.71 - "ARE YOU SURE" GAPS CLOSED (maintenance fix):
     - Checked every task GAMGUI marks DESTRUCTIVE against the typed-command
       check: 22 would NOT have asked when typed by hand. Added words (spam,
       turnoff2sv, obliterate, dedup, suspend, disable, accountwipe), prefixes
       (deprovision*, wipe* - Chromebook actions) and word pairs that are
       destructive only together (suspended on/true, end meetconference,
       update domain primary, update sheetrange, update license, audit
       monitor create, rotate sakey, update makesecuritygroup, transfer
       drive / ownership, calendars transfer, update calattendees). 'info
       transfer' and 'create ... makesecuritygroup' stay non-destructive.
     - _mark_destructive_by_words(): at load, a task whose FIXED command
       words are destructive gets destructive=True (15 tasks: Delete label,
       Delete filter, Remove member, Remove delegate, course removals,
       cancellations, ownership transfers...). Only adds the flag; names are
       unchanged (Favorites / Recent keys).
     - Error hint: GAM prints "Not Authorized to access this resource/api"
       AND "Reauthentication is needed" together when Google refuses a
       service (GAM issue #1991) - the hint now names the two real causes
       (service not in the sign-in / account lacks the admin role) instead
       of "sign in again".

   THE 2.70 COMPLETION RUN (from the GAM list, GitHub, and GamUpdate.txt):
     - Run ANY GAM command / an edited task command: gam_catalog.
       classify_command reads the words (whole words; GAM ignores case and
       '_') -> read-only / changes / DESTRUCTIVE (delete, del, purge, wipe,
       clear, empty, erase, trash, deprovision, remove, revoke, sync,
       powerwash, cancel...) / unknown (batch, tbatch). DESTRUCTIVE and
       unknown ask "Are you sure" (Gabe: ALWAYS). A task already marked
       DESTRUCTIVE keeps its own confirmation. The output shows "[What this
       command does: ...]". Same in gam_web.py (/api/classify).
     - Syntax button: the open task's blocks from GamCommands.txt next to
       gam (parse_gam_commands / syntax_blocks; 698 of 709 tasks match - the
       rest take their GAM word from a dropdown). Find searches every block.
     - Error hints (GAM_ERROR_HELP, GAM's own message texts): expired
       sign-in, No Client Access allowed, scopes not authorized, service
       account not approved, API not enabled, Not Authorized / 403, Service
       not applicable, Condition not met, rate limits, Invalid argument,
       Does not exist, Duplicate. Shown only when a run FAILS.
     - GAM version: 'gam version' is read with the "signs in as" check; the
       status line shows it. GAM_VERSION_NEEDS lists options that need a
       newer GAM (expires on create admin 7.48.06, extensionupdatecheck
       7.48.11, allowlisteddomains 7.48.00, chatavailability 7.47.00,
       showmembertypes 7.46.09, ownedsecondary / showenabled 7.46.08,
       configlicenseskus 7.46.07, isdisabled / disabledbefore /
       movefilepermissions 7.45.00, whocanaddexternalmembers 7.40.03). A too
       old GAM gets a question before the run, not an 'Invalid argument'.
     - No console window for ANY captured gam run (NO_WINDOW =
       CREATE_NO_WINDOW; interactive consoles keep theirs).
     - New / changed tasks: Deprovision candidates (print users isdisabled
       true [disabledbefore -30d..-2y]); Let a group have / Block outside
       members (allowexternalmembers true + whocanaddexternalmembers in ONE
       command - GAM list 09-21-2026); Move a file/folder (parentid, and
       movefilepermissions false); Create a course (subject); optional
       showmembertypes / ownedsecondary / showenabled dropdowns.
     - Move a user's Drive INTO a NEW Shared Drive: "Remove the files' old
       sharing" (default No). Yes = first 'gam redirect csv <Records\
       SharedDriveMove-<user>-<MM-DD-YYYY-HHMMSS>.csv> user <old> print
       filelist select root fields id,name,mimetype,webviewlink,permissions
       oneitemperrow filepath' (one row per file per person/link), then the
       move with movefilepermissions false. No record = nothing moved.
       Records\ is kept by both updaters (robocopy /XD, KEEP_ON_UPDATE).
     - Dry run wording: GAM's preview lists PLANNED changes, not whether
       Google accepts each one (Ross Scroggs, GAM list 09-01-2026).
     - GAM Change Watch (a separate tool, not in GAMGUI): weekly and
       on-demand check of GAM's newest release against the version GAMGUI
       was checked against - see NOTES / the GAM-Change-Watch folder.

   SET UP AN ADMINISTRATOR (2.68):
     - Admin Roles & Privileges > Set up an administrator (also in Users).
       Run opens a window with four parts:
         1. The account: an existing one, or create it (first/last name,
            password with a Generate button, must change at first sign-in,
            the account's OU, email the sign-in details to).
         2. Admin roles: tick roles from this domain's list (gam print
            adminroles), and/or create a new custom role (all_ou, all, or
            privileges picked from gam print privileges).
         3. Where: the whole organization, or only the OUs picked from the
            OU tree (or typed).
         4. Optional: an end date (expires, max one year), and the steps for
            letting that admin run GAM with only these rights.
     - The commands (new_admin_plan in gam_catalog.py), in order:
         gam create user <email> firstname .. lastname .. password ..
             changepassword on [ou ..] [notify ..]
         gam create adminrole "<name>" [description ..] privileges all_ou
         gam create admin <email> <role> customer | org_unit <OU>
             [expires <UTC>]      (one per role, per OU)
     - Refused before anything runs: a bad email, a password under 8
       characters, no role, an OU without a leading /, and Super Admin or a
       role with ALL privileges limited to OUs (Google's rule: an OU-limited
       role may only hold OU-level privileges).
     - Confirm: Yes/No; Super Admin or 'privileges all' needs ADMIN typed.
     - A role given right after the account was created may fail with GAM's
       "Does not exist" while Google finishes creating it: retried every 15
       seconds, up to 4 times. "Duplicate" / "already exists" = OK (was
       already set), so a re-run is safe. If the account or the new role
       fails, the run stops.
     - The password: masked in "Show the commands", in the command echo, and
       in the log; shown ONCE in a small Sign-in details window to copy. The
       window remembers its other values for the session, never the
       password.
     - "Run GAM themselves" prints the steps Ross Scroggs gave (gam oauth
       create as that admin, then gam user <email> update serviceaccount) -
       NOT run by GAMGUI, because 'oauth create' replaces the GAM sign-in of
       whatever config folder it runs in.

   PICKERS (2.68):
     - Browse OUs... on every box that takes an OU path: an OU tree (top
       level first, open an OU to see the OUs inside it; OUs sorted with
       numbers in number order, so Grade 9 comes before Grade 10) with a
       Find box that matches anywhere in the path. Scope boxes (email / OU /
       group / query) enable it only while their dropdown is an OU type.
     - Pick... on every box that takes an existing admin role, and on the
       privileges boxes (a privilege that exists in two services is written
       NAME:serviceId, the form GAM accepts for that).
     - The lists come from read-only commands (gam print orgs fields
       orgunitpath / print adminroles / print privileges), loaded in the
       background with no console window, kept per Section for the session;
       Refresh list reloads. If a list cannot load, the box can still be
       typed in.
     - FIXED: "Create custom admin role" had no privileges box, and GAM
       requires one ("Missing argument: privileges") - it never worked.

   PREVIEW (DRY RUN) (2.66):
     - The "Preview (dry run)" button next to Run runs the open task in GAM's
       own preview mode. GAM lists what a real run WOULD do and changes
       nothing. No confirmation is asked, because nothing changes.
     - Two kinds, both marked in the task's template (gam_catalog.py):
         {dryrun}  GAM has a 'preview' option. GAMGUI puts it where GAM
                   reads it - for group membership that is right before the
                   member list (e.g. update group X add member preview Y).
         {doit}    GAM only acts when 'doit' is given, so the dry run leaves
                   it out (Gmail message actions, calendar event removal and
                   attendee swap, file revisions, Chromebook powerwash and
                   wipe_users).
     - Every marked task was checked against GAM 7.48.14's source and then
       run for real against GAM (tests/live_dry_run.py) - each answer said
       "(Preview)" or "use doit". NOT marked, on purpose: Chromebook reboot,
       take_a_screenshot and set_volume (GAM runs them even without doit),
       and Cloud Identity device commands (without doit GAM only prints a
       count, so there is nothing useful to preview).
     - Safety: the dry run is always built from the FORM (an edited command
       box is ignored, and the output says so), and it refuses to run if
       'doit' was typed into Extra arguments (any case, with or without _).
     - After the exit code GAMGUI adds one plain-English line, because GAM
       ends many dry runs with a code that is not an error here: 30 orphans
       found, 51 action not performed (no doit), 60 nothing matched.
     - Same button in the browser version (gam_web.py).
     - "Run for each CSV row..." (2.67): when the bulk command is built for a
       task that has a dry run, GAMGUI also builds its dry-run twin (the same
       'gam csv <file> [maxrows N] gam ...' loop, each row in preview form).
       Preview (dry run) then previews EVERY row; Run does the real thing.
       The twin is used only while that bulk command is the current one - a
       change in the form rebuilds the single command and drops it. A bulk
       dry run always prints to the screen (preview lines are messages, so a
       Sheet or CSV output choice would only make an empty file). Tested
       against real GAM (tests/live_dry_run_bulk.py).

   SEARCH, SHORTCUTS, AND SAVING OUTPUT (2.49):
     - Search matches every word you type against the task's name, category,
       description, AND its GAM command - e.g. "cigroup" or "vacation".
     - Ctrl+F = search box; Enter (in the search box) = open the first match;
       Esc = clear the search; Ctrl+Enter = Run (same confirmations as the
       button); F1 = GAM docs for the open task.
     - "Save output..." writes the output pane to a .txt file exactly as
       shown - it may contain names, addresses, or a password GAM printed, so
       store it with care.

   DATES IN 2.49: Security > "Create an email monitor" now takes a local end
   date/time (converted to UTC 'YYYY-MM-DD HH:MM', the form GAM passes to the
   Email Audit API, which documents UTC dates). The dormant-users report date
   accepts MM-DD-YYYY as well as YYYY-MM-DD. Every date/time box in GAMGUI now
   takes normal local entries.

   WORKING FASTER (2.44):
     - FAVORITES: click "+ Favorite" (or right-click a task) to pin it at the
       top of the task list; "- Favorite" or right-click removes it.
     - RECENT: the last 10 tasks you ran appear under "Recent". Right-click
       the Recent heading to clear the list.
     - LIVE PREVIEW: the command preview rebuilds a moment after you type in
       any box. (If you hand-edit the preview and then change a box, the
       preview is rebuilt from the boxes.)
     - GAM DOCS: opens the GAM wiki page that documents the task you are on.
     - BROWSE...: file pickers for non-CSV files (.eml, .pem, .p12, images,
       JSON) now list All files instead of only CSV files.
   In a form, fields marked * are required; others are optional and are simply
   omitted from the command when left blank.

   OUTPUT DESTINATION: any task that lists or exports results has a "Save
   results to" dropdown - the screen, a Google Sheet, or a CSV file on your PC.

   MULTIPLE DOMAINS: the Section dropdown at the top (named "Domain" before
   2.54; renamed on the suggestion of GAM developer Ross Scroggs, since it
   picks a gam.cfg section) runs a command against a
   chosen gam.cfg section (tenant) without changing your saved default - handy
   for MSPs. Single-domain setups just see "(default)".

5. WHAT IT CHANGES / SIDE EFFECTS
   GAMGUI itself changes nothing except writing gamgui.ini,
   gamgui_tasklists.json (Favorites / Recent), and log files. The
   gam commands you run change whatever they say they change - the preview box
   always shows the exact command first. Destructive tasks (delete/suspend/
   deprovision a user; delete a group/OU/course; powerwash/wipe/deprovision a
   device; sync membership; trash/delete messages; transfer a Drive; remove
   access/licenses; and the bulk equivalents) pop a confirmation showing the
   full command before running.

6. LOG FILES
   BACKUP CODES ARE NEVER LOGGED (2.60): the output of any command that
   shows or generates 2-Step Verification backup codes (show / update /
   print backupcodes or verificationcodes) is shown on screen but NOT
   written to the session log; the log records "OUTPUT NOT LOGGED" instead.
   Backup codes are working second factors. Logs from GAMGUI 2.59 and
   earlier may contain codes if those tasks were used - search them for
   'backupcodes' and delete or edit those files.

   Logs\GAMGUI_MM-DD-YYYY_HH-MM-SS.log - one per session. Contains timestamps,
   every command run, all output, and exit codes. Note that a password you type
   into a "create user ... password X" form WILL appear in the log and on
   screen - prefer the random-password option (GAM generates it server-side),
   and treat any CSV that contains plaintext passwords as sensitive: store it
   safely and delete it after provisioning. Keep or purge logs per your
   organization's retention practice.

7. TROUBLESHOOTING
   "gam.exe not found"      - Click Locate gam.exe and browse to it.
   gam works in Terminal but not in GAMGUI (macOS), or the wrong tenant is
   used                     - Locate gam.cfg... (top right) and pick your
                              gam.cfg. Confirm with
                              Diagnostics > GAM version (Config File: line).
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
   place (keeping gamgui.ini, gamgui_tasklists.json, and Logs); an installed
   copy re-runs the installer
   with a Windows administrator (UAC) prompt. You can also use Help -> Check
   for updates now..., and toggle the startup check under Help.
   WHAT'S NEW (2.64): the first time GAMGUI opens after an update it lists
   the changes since the version this computer had (from the CHANGELOG.txt
   built into the app - works offline). Help -> What's new... shows the five
   newest versions any time. A new install does not pop it up. The last
   version run is kept in gamgui.ini (last_run_version).
   TURN IT OFF / ON (2.69): untick "Show this after every update" in the
   What's new window, or Help -> "Show What's new after an update" (both
   are the same setting, show_whats_new in gamgui.ini; on by default; an
   unreadable value counts as on). While it is off, the version is still
   recorded, the log notes the update, and Help -> What's new... still
   works.

   MACOS AND LINUX (2.63+) - no PowerShell needed (gam_update.py):
     - macOS GAMGUI.app: downloads GAMGUI-<v>-macOS.zip, checks its SHA-256
       against the release notes, unpacks it with ditto, checks the new app
       with 'codesign --verify --deep --strict', and after GAMGUI closes a
       small bash script swaps the app (the old one is put back if the copy
       fails) and reopens it. Needs write access to the folder holding
       GAMGUI.app (normally /Applications); otherwise the Releases page opens.
     - Settings on macOS now live in ~/Library/Application Support/GAMGUI
       (not inside GAMGUI.app, where writing could break the app's
       signature and an update would erase them). Settings from older
       versions are copied there once.
     - Linux portable folder: downloads GAMGUI-<v>-Linux.tar.gz (unpacked with
       a check that nothing can land outside the work folder), then swaps
       the program files, keeping gamgui.ini, gamgui_tasklists.json and Logs;
       a failed copy puts the old files back. Relaunches GAMGUI.
     - Linux .deb / .rpm (/opt/GAMGUI, root-owned): downloads and verifies the
       package into ~/Downloads and shows the sudo apt / dnf install command
       (copied to the clipboard). GAMGUI never asks for root.
     - Nothing is installed unless the download's SHA-256 matches the value
       in the release notes (they are added right after each build - if they
       are not there yet, GAMGUI says so and changes nothing).
     - Log: Logs/gamgui-update.log.
     - Macs on 2.62 or older: install 2.63 by hand once (those versions only
       open the Releases page). Save settings first, in Terminal:
         mkdir -p ~/Library/Application\ Support/GAMGUI
         cp /Applications/GAMGUI.app/Contents/MacOS/gamgui* ~/Library/Application\ Support/GAMGUI/

   MANUAL (bundled script): updategamgui.ps1 in the app folder is what the
   in-app updater runs. Run it yourself, e.g. a weekly scheduled task:
       powershell -ExecutionPolicy Bypass -File "C:\GAM7\GAMGUI\updategamgui.ps1" -Quiet
   It auto-detects a portable copy, a Setup.exe install, or both, and updates
   each one that is behind. Switches: -InstallType auto|zip|exe|both,
   -InstallRoot "<path>", -Force, -Launch, -Quiet. Every download is verified
   against a SHA-256 published in the release notes. Update activity is logged
   to <install>\Logs\GAMGUI-Update.log.
================================================================================
