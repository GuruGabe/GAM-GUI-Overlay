================================================================================
  GAMGUI 1.0 - A GRAPHICAL FRONT-END FOR GAM7
  Author: Gabe - FSISD IT Department
================================================================================

1. WHAT THIS PROGRAM DOES
   GAMGUI is a point-and-click front end for GAM7, the command line tool for
   Google Workspace administration (https://github.com/GAM-team/GAM).
   It presents 75 common admin tasks as fill-in forms across 14 categories:
   Users, Groups, Aliases, Org Units, Chromebooks, Gmail, Calendars, Drive,
   Classroom, Licenses, Reports, Security, Email Cleanup, and Diagnostics -
   plus a Custom command mode that accepts any GAM command.

   The Email Cleanup category handles phishing incident response: search
   every mailbox in the domain for a malicious message (read-only preview),
   then trash or permanently delete matches domain-wide with a per-mailbox
   limit as a seatbelt. The "Full incident-response workflow" task runs
   the complete four-phase cleanup built in: 1) domain-wide search saved
   to an evidence CSV, 2) a confirmation that shows the hit count and
   requires typing DELETE, 3) deletion by exact Message-ID when available
   (falling back to the From+Subject query), 4) Gmail and Drive audit
   report pulls for the lookback window. All evidence is saved to a
   timestamped Incident folder under Logs, and canceling at the
   confirmation keeps the evidence while deleting nothing.

   For every task GAMGUI:
     - Builds the exact gam command from your form entries
     - Shows it in an editable preview BEFORE anything runs
     - Runs it through YOUR gam executable and streams the output live
     - Requires an extra confirmation for destructive actions
     - Logs everything to a session log file

   GAMGUI never talks to Google itself and holds no credentials. All
   authority comes from your existing GAM authorization. If GAM is not
   set up, GAMGUI cannot do anything.

2. REQUIREMENTS
   - Windows 10/11 (EXE build). From source: any OS with Python 3.10+
     and tkinter (macOS/Linux work; see item 3).
   - GAM7 installed and authorized for your domain.
   - Admin rights: only whatever your gam commands themselves need.
   - Network access: only what gam itself uses.

   FOR NON-TECHNICAL USERS: see HOW-TO-GUIDE.txt in this folder - a full
   plain-English walkthrough written for coworkers who have never used GAM
   or a command line. Hand that file to new users before their first use.

3. HOW TO RUN IT
   EXE (recommended):
     a. Copy GAMGUI.exe into your GAM folder (e.g. C:\GAM7) so it finds
        gam.exe automatically.
     b. Double-click GAMGUI.exe.
     c. If gam lives elsewhere, click "Locate gam.exe..." (top right);
        the choice is remembered in gamgui.ini.
   From source (Windows/macOS/Linux):
     a. Install Python 3.10+ (python.org; on Linux also install the
        python3-tk package).
     b. python GAMGUI.py
   Building the EXE yourself:
     a. pip install pyinstaller
     b. Run Build-EXE.bat (Windows). For macOS/Linux run:
        pyinstaller --onefile --windowed --name GAMGUI GAMGUI.py
     c. The result is in the dist folder.

4. PARAMETERS / OPTIONS
   GAMGUI takes no command line parameters. Configuration:
   - gamgui.ini (next to the program): stores the gam path. Delete it to
     re-run auto-detection.
   - Fields marked * in a form are required; others are optional and are
     simply omitted from the command when left blank.

5. WHAT IT CHANGES / SIDE EFFECTS
   GAMGUI itself changes nothing except writing gamgui.ini and log files.
   The gam commands you run change whatever they say they change - the
   preview box always shows the exact command first. Tasks flagged
   DESTRUCTIVE (delete user/group/OU/course, powerwash, wipe, sync group,
   trash messages, transfer drive, revoke access/licenses) pop a
   confirmation dialog showing the full command before running.

6. LOG FILES
   Logs\GAMGUI_MM-DD-YYYY_HH-MM-SS.log next to the program - one per
   session. Contains timestamps, every command run, all output, and exit
   codes. No passwords are entered into GAMGUI except as gam command
   arguments you type yourself; note that "create user ... password X"
   WILL appear in the log and on screen - prefer the random-password
   option, which makes GAM generate the password server-side.
   Keep or purge logs per your district retention practice.

7. TROUBLESHOOTING
   "gam.exe not found"      - Click Locate gam.exe and browse to it.
   Output shows auth errors - Run "gam oauth info" (Diagnostics category);
                              re-authorize GAM if scopes are missing.
   Window frozen            - It should never freeze (commands run on a
                              background thread); long commands just take
                              long. Use Stop to kill a runaway command.
   Garbled characters       - Output is decoded as UTF-8; odd names may
                              show replacement characters. Cosmetic only.
   Nothing happens on Run   - Check the preview box: if it shows
                              "(Missing required value: ...)" fill in the
                              starred fields.

8. KNOWN LIMITATIONS
   - The 71 built-in forms cover everyday tasks, not all of GAM's
     thousands of command permutations - that is what Custom command
     mode is for.
   - No CSV bulk-run builder yet (planned; see NOTES.md). Bulk work is
     still best done with "gam csv" in Custom mode or a terminal.
   - Commands run WITHOUT a shell: arguments go straight to gam, so
     characters like & | > < and quotes inside subjects and queries are
     always safe. The trade-off: shell pipes (|) and > redirection do not
     work in Custom mode - use GAM's own "redirect csv ./file.csv" or
     "todrive" options instead, which do the same job.
   - The preview is editable by design; treat it like a terminal and do
     not paste commands you do not understand.
   - English only.
   - The incident-response workflow pulls raw Gmail/Drive audit CSVs but
     does not correlate attachment names/hashes or check Drive for
     persisted attachments (the original FSISD batch workflow's deepest
     analysis phase). Review the raw CSVs manually for that level.
================================================================================
