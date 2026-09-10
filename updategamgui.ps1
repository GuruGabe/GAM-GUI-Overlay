<#
.SYNOPSIS
    Auto-updates GAMGUI to the latest GitHub release (or installs it fresh).

.DESCRIPTION
    Checks the GAMGUI GitHub repository for the newest release, compares it
    against the version currently installed, and - if a newer version exists -
    downloads the Windows zip, verifies its SHA-256, and installs it over the
    existing folder WITHOUT touching the user's settings (gamgui.ini) or the
    Logs folder. If the target folder does not exist yet, it acts as a
    first-time installer.

    WHY POWERSHELL (not Batch, per the FSISD language-preference order): this
    task calls the GitHub REST API, parses JSON, extracts a zip, computes a
    SHA-256 hash, and selectively mirrors files. None of that is possible in
    plain Windows Batch without extra tools, so PowerShell is the correct
    choice here. It is written to run on Windows PowerShell 5.1 AND PowerShell
    7+, and uses only ASCII characters.

.PARAMETER InstallRoot
    The GAMGUI application folder (the one that contains GAMGUI.exe) to update
    or create. Default: C:\GAM7\GAMGUI

.PARAMETER Repo
    The GitHub owner/repo to pull releases from.
    Default: GuruGabe/GAM-GUI-Overlay

.PARAMETER Force
    Reinstall the latest release even if it is already the installed version.

.PARAMETER Quiet
    Suppress console output and the end-of-run pause. Use this when running the
    script from Task Scheduler so it never waits for a keypress.

.PARAMETER Launch
    Start GAMGUI.exe after a successful update.

.EXAMPLE
    .\updategamgui.ps1
    Interactive update of the default C:\GAM7\GAMGUI folder.

.EXAMPLE
    .\updategamgui.ps1 -Quiet
    Silent update suitable for a scheduled task (no prompts, no pause).

.EXAMPLE
    .\updategamgui.ps1 -InstallRoot "D:\Tools\GAMGUI" -Launch
    Update a GAMGUI installed elsewhere and launch it when finished.

.NOTES
    Script:   updategamgui.ps1
    Author:   Gabe - FSISD IT Department (built with Claude)
    Created:  09-10-2026
    Modified: 09-10-2026
    Version:  1.0
    Requires: Windows PowerShell 5.1 or PowerShell 7+, internet access to
              api.github.com and github.com. No administrator rights are needed
              as long as the current user can write to InstallRoot.
#>

# =============================================================================
# PARAMETERS
# =============================================================================
[CmdletBinding()]
param(
    # The GAMGUI application folder to update or create.
    [string]$InstallRoot = "C:\GAM7\GAMGUI",

    # The GitHub repository that publishes GAMGUI releases.
    [string]$Repo = "GuruGabe/GAM-GUI-Overlay",

    # Reinstall the newest release even if it is already installed.
    [switch]$Force,

    # Run without any console output or end-of-run pause (for scheduled tasks).
    [switch]$Quiet,

    # Launch GAMGUI.exe after a successful update.
    [switch]$Launch
)

# =============================================================================
# INITIAL SETUP
# =============================================================================

# Stop on the first unhandled error so problems surface instead of being
# silently ignored; the big try/catch at the bottom turns these into clear
# messages and a non-zero exit code.
$ErrorActionPreference = "Stop"

# GitHub only serves API and download traffic over TLS 1.2+, and Windows
# PowerShell 5.1 still defaults to older protocols. Force TLS 1.2 up front or
# every web call below would fail with a handshake error.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# Key file/URL locations derived from the parameters. The marker file records
# which release tag is currently installed so we can tell when an update is
# needed; it lives inside InstallRoot and is preserved across updates.
$MarkerFile   = Join-Path $InstallRoot "gamgui-version.txt"
$ExePath      = Join-Path $InstallRoot "GAMGUI.exe"
$LogDir       = Join-Path $InstallRoot "Logs"
$LogFile      = Join-Path $LogDir     "GAMGUI-Update.log"
$ApiUrl       = "https://api.github.com/repos/$Repo/releases/latest"
$UserAgent    = "GAMGUI-Updater"

# A temporary working folder for this run (download + extraction). A GUID keeps
# concurrent runs from colliding. It is always removed in the finally block.
$TempDir      = Join-Path $env:TEMP ("gamgui-update-" + [Guid]::NewGuid().ToString("N"))

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

function Write-Log {
    # Appends one timestamped line to the update log, creating the Logs folder
    # on first use. Date/time use the FSISD-standard MM-DD-YYYY / HH:MM:SS
    # format. Logging never throws - a logging failure must not abort an update.
    param([string]$Message)
    try {
        if (-not (Test-Path -LiteralPath $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }
        $stamp = Get-Date -Format "MM-dd-yyyy HH:mm:ss"
        Add-Content -LiteralPath $LogFile -Value ("[" + $stamp + "] " + $Message)
    } catch {
        # Intentionally swallow logging errors.
    }
}

function Say {
    # Writes a line to the console unless -Quiet was given, and always logs it.
    # $Color lets callers highlight success (green) or warnings (yellow).
    param([string]$Message, [string]$Color = "Gray")
    if (-not $Quiet) { Write-Host $Message -ForegroundColor $Color }
    Write-Log $Message
}

function Convert-ToVersion {
    # Turns a release tag like "2.7" or "v2.7" into a [version] object so that
    # numeric comparison is correct (2.10 is newer than 2.9, which a plain
    # string compare would get wrong). Returns [version]0.0 if it cannot parse.
    param([string]$Tag)
    if ([string]::IsNullOrWhiteSpace($Tag)) { return [version]"0.0" }
    $clean = $Tag.Trim()
    if ($clean.StartsWith("v") -or $clean.StartsWith("V")) { $clean = $clean.Substring(1) }
    $parsed = $null
    if ([version]::TryParse($clean, [ref]$parsed)) { return $parsed }
    return [version]"0.0"
}

# =============================================================================
# MAIN
# =============================================================================
try {
    Say "GAMGUI updater - checking $Repo for the latest release..." "Cyan"

    # -- Guard: never overwrite a GAMGUI that is currently running --------------
    # A running GAMGUI.exe holds file locks in InstallRoot; replacing the folder
    # would fail halfway and could corrupt the install. Ask the user to close it
    # first (we deliberately do NOT force-kill it). We only block when the
    # running instance is THIS install (its exe path is inside InstallRoot) - a
    # GAMGUI running from some other folder is none of our business. If a
    # process's path cannot be read (another user's instance), we play it safe
    # and treat it as a match.
    $rootFull = (Resolve-Path -LiteralPath $InstallRoot -ErrorAction SilentlyContinue)
    $rootPath = if ($rootFull) { $rootFull.Path } else { $InstallRoot }
    $running = Get-Process -Name "GAMGUI" -ErrorAction SilentlyContinue | Where-Object {
        (-not $_.Path) -or $_.Path.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)
    }
    if ($running) {
        Say "GAMGUI is currently running. Close it and run this again." "Yellow"
        Write-Log "Aborted: GAMGUI.exe is running."
        if (-not $Quiet) { Read-Host "Press Enter to exit" | Out-Null }
        exit 1
    }

    # -- Step 1: ask GitHub for the latest release -----------------------------
    # GitHub requires a User-Agent header or it returns HTTP 403. This endpoint
    # is public, so no token is needed for a public repository.
    #   API URL: https://api.github.com/repos/<owner>/<repo>/releases/latest
    $headers = @{ "User-Agent" = $UserAgent; "Accept" = "application/vnd.github+json" }
    $release = Invoke-RestMethod -Uri $ApiUrl -Headers $headers

    $latestTag = $release.tag_name
    if ([string]::IsNullOrWhiteSpace($latestTag)) {
        throw "GitHub returned no tag_name; cannot determine the latest version."
    }
    Say "Latest published release: $latestTag"

    # -- Step 2: figure out what is installed now ------------------------------
    # The marker file holds the tag we last installed. No marker (or no folder)
    # means a fresh install, so we treat the current version as 0.0.
    $currentTag = "(none)"
    if (Test-Path -LiteralPath $MarkerFile) {
        $currentTag = (Get-Content -LiteralPath $MarkerFile -Raw).Trim()
    } elseif (Test-Path -LiteralPath $ExePath) {
        # An existing exe with no marker: unknown version. Force an update so the
        # marker gets written, unless the user is only checking.
        $currentTag = "(unknown)"
    }
    Say "Currently installed:      $currentTag"

    $latestVer  = Convert-ToVersion $latestTag
    $currentVer = Convert-ToVersion $currentTag

    # -- Step 3: decide whether to update --------------------------------------
    # Update when the latest release is strictly newer than what is installed,
    # when the installed version is unknown, or when -Force was given.
    $needsUpdate = $Force -or ($currentTag -eq "(unknown)") -or ($latestVer -gt $currentVer)
    if (-not $needsUpdate) {
        Say "GAMGUI is already up to date ($currentTag)." "Green"
        Write-Log "No update needed."
        if (-not $Quiet) { Read-Host "Press Enter to exit" | Out-Null }
        exit 0
    }
    Say "An update is available: $currentTag -> $latestTag" "Cyan"

    # -- Step 4: locate the Windows zip asset ----------------------------------
    # Prefer an asset named like GAMGUI-*-Windows.zip; fall back to the first
    # .zip attached to the release.
    $asset = $release.assets | Where-Object { $_.name -like "GAMGUI-*Windows.zip" } | Select-Object -First 1
    if (-not $asset) {
        $asset = $release.assets | Where-Object { $_.name -like "*.zip" } | Select-Object -First 1
    }
    if (-not $asset) {
        throw "Release $latestTag has no downloadable .zip asset."
    }

    # -- Step 5: download the zip ----------------------------------------------
    New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    $zipPath = Join-Path $TempDir $asset.name
    Say "Downloading $($asset.name) ..."
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("User-Agent", $UserAgent)
    $wc.DownloadFile($asset.browser_download_url, $zipPath)
    $wc.Dispose()

    # -- Step 6: verify the SHA-256 if the release notes publish one -----------
    # Our release notes include the zip's SHA-256 as a bare 64-hex string. If we
    # find one in the release body, the download MUST match it or we abort - this
    # protects against a corrupted or tampered download. If no hash is published
    # we warn and continue (the reference GAM updater does no verification).
    $expectedHash = $null
    if ($release.body -and ($release.body -match "([0-9A-Fa-f]{64})")) {
        $expectedHash = $Matches[1].ToUpper()
    }
    if ($expectedHash) {
        $actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpper()
        if ($actualHash -ne $expectedHash) {
            throw ("SHA-256 mismatch - download may be corrupt. Expected " +
                   $expectedHash + " but got " + $actualHash + ".")
        }
        Say "SHA-256 verified OK." "Green"
    } else {
        Say "No SHA-256 published in the release notes; skipping hash check." "Yellow"
    }

    # -- Step 7: extract the zip -----------------------------------------------
    # The zip contains a top-level GAMGUI\ folder, so the extracted app lands in
    # $TempDir\GAMGUI.
    $extractDir = Join-Path $TempDir "extracted"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $sourceApp = Join-Path $extractDir "GAMGUI"
    if (-not (Test-Path -LiteralPath (Join-Path $sourceApp "GAMGUI.exe"))) {
        # Some zips may not nest under GAMGUI\; fall back to the extract root if
        # it directly contains the exe.
        if (Test-Path -LiteralPath (Join-Path $extractDir "GAMGUI.exe")) {
            $sourceApp = $extractDir
        } else {
            throw "Extracted files do not contain GAMGUI.exe; unexpected zip layout."
        }
    }

    # -- Step 8: install over the existing folder ------------------------------
    # robocopy /MIR makes InstallRoot match the new app EXACTLY (so stale files
    # from the old version are removed), but /XF and /XD keep the user's
    # settings, the version marker, and the Logs folder from being deleted.
    # robocopy exit codes 0-7 are success (bit flags); 8+ is a real failure.
    if (-not (Test-Path -LiteralPath $InstallRoot)) {
        New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    }
    Say "Installing to $InstallRoot ..."
    robocopy $sourceApp $InstallRoot /MIR /XF gamgui.ini gamgui-version.txt /XD Logs /R:2 /W:2 /NFL /NDL /NP /NJH /NJS | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy failed with exit code $rc (could not copy the new files - is the folder in use or read-only?)."
    }

    # -- Step 9: record the installed version ----------------------------------
    Set-Content -LiteralPath $MarkerFile -Value $latestTag -Encoding ASCII
    Say "GAMGUI updated to $latestTag." "Green"
    Write-Log "Update complete: $currentTag -> $latestTag (robocopy rc=$rc)."

    # -- Step 10: optionally launch --------------------------------------------
    if ($Launch -and (Test-Path -LiteralPath $ExePath)) {
        Say "Launching GAMGUI..."
        Start-Process -FilePath $ExePath
    }

    if (-not $Quiet) { Read-Host "Press Enter to exit" | Out-Null }
    exit 0
}
catch {
    # Any unhandled error lands here: log it, show it, and exit non-zero so a
    # scheduled task records a failure.
    $err = $_.Exception.Message
    Write-Log ("ERROR: " + $err)
    if (-not $Quiet) {
        Write-Host ("Update failed: " + $err) -ForegroundColor Red
        Write-Host "If this was a permissions error, re-run PowerShell as Administrator." -ForegroundColor Yellow
        Read-Host "Press Enter to exit" | Out-Null
    }
    exit 1
}
finally {
    # Always clean up the temporary download/extract folder, success or fail.
    if (Test-Path -LiteralPath $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
