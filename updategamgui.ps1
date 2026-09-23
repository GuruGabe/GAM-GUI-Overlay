<#
.SYNOPSIS
    Auto-updates GAMGUI to the latest GitHub release (or installs it fresh),
    handling BOTH ways GAMGUI can be installed: a portable Zip-extracted copy
    and/or the Setup.exe (Inno Setup) installer.

.DESCRIPTION
    Checks the GAMGUI GitHub repository for the newest release, then detects how
    GAMGUI is installed on THIS machine and updates whatever it finds:

      1. PORTABLE (Zip) install - a folder (default C:\GAM7\GAMGUI) that holds
         GAMGUI.exe and a gamgui-version.txt marker. Updated by downloading the
         Windows zip, verifying its SHA-256, and mirroring the new files over the
         folder WITHOUT touching the user's settings (gamgui.ini) or Logs.

      2. EXE (Setup.exe) install - a per-machine install under Program Files,
         registered at HKLM\SOFTWARE\GAMGUI (Version + InstallLocation) and in
         Add/Remove Programs. Updated by downloading the new GAMGUI-<tag>-Setup.exe,
         verifying its SHA-256, and running it silently. Because the installer's
         AppId is stable, the new Setup.exe upgrades the existing install in place.
         This step needs administrator rights (it writes Program Files + HKLM).

    When BOTH are present, both are updated. When NEITHER is present, the script
    behaves as a first-time PORTABLE installer into -InstallRoot (its original
    behavior). Each install type is compared to the latest release on its own, so
    only the ones that are behind (or all of them with -Force) get updated.

    WHY POWERSHELL (not Batch, per the FSISD language-preference order): this
    task calls the GitHub REST API, parses JSON, reads the registry, computes a
    SHA-256 hash, extracts a zip, and selectively mirrors files. None of that is
    practical in plain Windows Batch, so PowerShell is the correct choice. It is
    written for Windows PowerShell 5.1 AND PowerShell 7+, ASCII only.

.PARAMETER InstallRoot
    The PORTABLE GAMGUI application folder (the one that contains GAMGUI.exe) to
    update or create. Default: C:\GAM7\GAMGUI. This does NOT affect the Setup.exe
    install, whose location comes from the registry.

.PARAMETER InstallType
    Which install type(s) to update:
      auto  (default) - detect and update whatever is present (Zip and/or Exe).
      zip             - only update the portable folder at -InstallRoot.
      exe             - only update the Setup.exe (Program Files) install.
      both            - update both, and warn if one of them is not found.

.PARAMETER Repo
    The GitHub owner/repo to pull releases from.
    Default: GuruGabe/GAM-GUI-Overlay

.PARAMETER Force
    Reinstall the latest release even if it is already the installed version.

.PARAMETER Quiet
    Suppress console output and the end-of-run pause. Use this when running the
    script from Task Scheduler so it never waits for a keypress. Note: a silent
    EXE update still needs admin; under -Quiet with no admin rights the EXE
    update is skipped (there is no one to answer a UAC prompt).

.PARAMETER Launch
    Start GAMGUI.exe after a successful update (prefers the portable copy, then
    the exe install).

.EXAMPLE
    .\updategamgui.ps1
    Detect how GAMGUI is installed and update it (portable and/or exe).

.EXAMPLE
    .\updategamgui.ps1 -Quiet
    Silent update suitable for a scheduled task (no prompts, no pause).

.EXAMPLE
    .\updategamgui.ps1 -InstallType zip -InstallRoot "D:\Tools\GAMGUI" -Launch
    Update only a portable GAMGUI installed elsewhere and launch it when done.

.NOTES
    Script:   updategamgui.ps1
    Author:   Gabe - FSISD IT Department (built with Claude)
    Created:  09-10-2026
    Modified: 09-23-2026
    Version:  2.0
    Requires: Windows PowerShell 5.1 or PowerShell 7+, internet access to
              api.github.com and github.com. Updating a portable copy needs
              write access to -InstallRoot. Updating the Setup.exe install needs
              administrator rights (it re-runs the installer for a per-machine
              install).
#>

# =============================================================================
# PARAMETERS
# =============================================================================
[CmdletBinding()]
param(
    # The PORTABLE GAMGUI application folder to update or create.
    [string]$InstallRoot = "C:\GAM7\GAMGUI",

    # Which install type(s) to update: auto (detect), zip, exe, or both.
    [ValidateSet("auto", "zip", "exe", "both")]
    [string]$InstallType = "auto",

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

# Key locations for the PORTABLE copy, derived from -InstallRoot. The marker
# file records which release tag the portable copy is on; it lives inside
# InstallRoot and is preserved across updates.
$MarkerFile   = Join-Path $InstallRoot "gamgui-version.txt"
$ExePath      = Join-Path $InstallRoot "GAMGUI.exe"

# The update log always lives with the portable copy's Logs folder (or is
# created there) so there is one predictable place to look, regardless of which
# install type triggered the run.
$LogDir       = Join-Path $InstallRoot "Logs"
$LogFile      = Join-Path $LogDir     "GAMGUI-Update.log"

$ApiUrl       = "https://api.github.com/repos/$Repo/releases/latest"
$UserAgent    = "GAMGUI-Updater"

# The stable Inno Setup AppId (see installer\gamgui.iss). Inno records the
# per-machine install under ...\Uninstall\{AppId}_is1, but we read our own
# explicit HKLM\SOFTWARE\GAMGUI key instead, which is simpler and carries both
# the Version and the InstallLocation.
$ExeRegPaths  = @(
    "HKLM:\SOFTWARE\GAMGUI",
    "HKLM:\SOFTWARE\WOW6432Node\GAMGUI"
)

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

function Pause-Exit {
    # Waits for a keypress so a double-clicked window does not vanish before the
    # user can read it - but ONLY when it is safe. It is skipped under -Quiet
    # (scheduled tasks) and when the host is non-interactive (e.g. launched with
    # -NonInteractive, or piped), and any Read-Host failure is swallowed. This
    # matters because the pause runs at the very end of a SUCCESSFUL update: if
    # Read-Host were allowed to throw here it would be caught below and wrongly
    # reported as an update failure.
    if ($Quiet) { return }
    if (-not [Environment]::UserInteractive) { return }
    try { Read-Host "Press Enter to exit" | Out-Null } catch { }
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

function Test-IsAdmin {
    # Returns $true if the current process is elevated (Administrator). Updating
    # the per-machine Setup.exe install requires this.
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ExeInstall {
    # Detects the Setup.exe (Inno) install by reading our explicit registry key.
    # Returns a hashtable @{ Present; Version; InstallLocation } - Present is
    # $false when no exe install is registered.
    foreach ($regPath in $ExeRegPaths) {
        try {
            if (Test-Path -LiteralPath $regPath) {
                $key = Get-ItemProperty -LiteralPath $regPath -ErrorAction Stop
                if ($key.Version -or $key.InstallLocation) {
                    return @{
                        Present         = $true
                        Version         = [string]$key.Version
                        InstallLocation = [string]$key.InstallLocation
                    }
                }
            }
        } catch {
            # Ignore an unreadable view and try the next one.
        }
    }
    return @{ Present = $false; Version = ""; InstallLocation = "" }
}

function Get-PublishedHash {
    # Finds the SHA-256 that a release body publishes for a SPECIFIC asset. Our
    # release notes use lines like:
    #     SHA-256 (GAMGUI-2.25-Windows.zip):
    #     7D2ADB79...   (64 hex chars, on the same or the next line)
    # Returns the uppercase hash, or $null if none is published for that asset.
    # As a back-compatibility fallback, if the body contains exactly ONE 64-hex
    # string and the requested asset is the Windows zip, that single hash is used
    # (older releases published only the zip hash with no per-asset label).
    param([string]$Body, [string]$AssetName)
    if ([string]::IsNullOrWhiteSpace($Body)) { return $null }

    # Label-aware match: the asset name in parentheses, then the next hex run.
    $escaped = [regex]::Escape($AssetName)
    $labeled = [regex]::Match($Body, $escaped + "\s*\)?\s*:?\s*[\r\n]*\s*([0-9A-Fa-f]{64})")
    if ($labeled.Success) { return $labeled.Groups[1].Value.ToUpper() }

    # Fallback for the old single-hash format (zip only).
    if ($AssetName -like "*Windows.zip") {
        $all = [regex]::Matches($Body, "[0-9A-Fa-f]{64}")
        if ($all.Count -eq 1) { return $all[0].Value.ToUpper() }
    }
    return $null
}

function Get-RunningInPath {
    # Returns any GAMGUI.exe processes whose exe path is inside $PathRoot. A
    # process whose path cannot be read (another user's instance) is treated as
    # a match, to be safe.
    param([string]$PathRoot)
    $resolved = (Resolve-Path -LiteralPath $PathRoot -ErrorAction SilentlyContinue)
    $full = if ($resolved) { $resolved.Path } else { $PathRoot }
    return Get-Process -Name "GAMGUI" -ErrorAction SilentlyContinue | Where-Object {
        (-not $_.Path) -or $_.Path.StartsWith($full, [System.StringComparison]::OrdinalIgnoreCase)
    }
}

function Get-ReleaseAsset {
    # Returns the release asset object whose name matches $Pattern (first match),
    # or $null if the release has no such asset.
    param($Release, [string]$Pattern)
    return $Release.assets | Where-Object { $_.name -like $Pattern } | Select-Object -First 1
}

function Save-Download {
    # Downloads $Url to $Destination with the required GitHub User-Agent header.
    param([string]$Url, [string]$Destination)
    $wc = New-Object System.Net.WebClient
    $wc.Headers.Add("User-Agent", $UserAgent)
    try {
        $wc.DownloadFile($Url, $Destination)
    } finally {
        $wc.Dispose()
    }
}

function Confirm-Hash {
    # Verifies $FilePath against $Expected (uppercase SHA-256). Throws on a
    # mismatch. When $Expected is $null, warns and returns (matches the original
    # script's behavior of continuing when no hash is published).
    param([string]$FilePath, [string]$Expected, [string]$Label)
    if (-not $Expected) {
        Say "No SHA-256 published for $Label; skipping hash check." "Yellow"
        return
    }
    $actual = (Get-FileHash -LiteralPath $FilePath -Algorithm SHA256).Hash.ToUpper()
    if ($actual -ne $Expected) {
        throw ("SHA-256 mismatch for $Label - download may be corrupt. Expected " +
               $Expected + " but got " + $actual + ".")
    }
    Say "SHA-256 verified OK for $Label." "Green"
}

# =============================================================================
# UPDATE ROUTINES (one per install type)
# =============================================================================

function Update-Portable {
    # Updates (or first-time installs) the portable copy at $InstallRoot from the
    # release's Windows zip. Returns $true if it installed, $false if skipped.
    param($Release, [string]$LatestTag, [version]$LatestVer)

    # What version is the portable copy on now? No marker (or no folder) = fresh.
    $currentTag = "(none)"
    if (Test-Path -LiteralPath $MarkerFile) {
        $currentTag = (Get-Content -LiteralPath $MarkerFile -Raw).Trim()
    } elseif (Test-Path -LiteralPath $ExePath) {
        $currentTag = "(unknown)"
    }
    Say "Portable copy at ${InstallRoot}: $currentTag"

    $currentVer = Convert-ToVersion $currentTag
    $needs = $Force -or ($currentTag -eq "(unknown)") -or ($LatestVer -gt $currentVer)
    if (-not $needs) {
        Say "Portable copy is already up to date ($currentTag)." "Green"
        return $false
    }

    # Never overwrite a portable copy that is currently running (file locks).
    $running = Get-RunningInPath -PathRoot $InstallRoot
    if ($running) {
        Say "GAMGUI is running from $InstallRoot. Close it and run again to update the portable copy." "Yellow"
        Write-Log "Portable update skipped: GAMGUI.exe running from InstallRoot."
        return $false
    }

    # Locate + download the Windows zip.
    $asset = Get-ReleaseAsset -Release $Release -Pattern "GAMGUI-*Windows.zip"
    if (-not $asset) { $asset = Get-ReleaseAsset -Release $Release -Pattern "*.zip" }
    if (-not $asset) { throw "Release $LatestTag has no downloadable .zip asset." }

    $zipPath = Join-Path $TempDir $asset.name
    Say "Downloading $($asset.name) ..."
    Save-Download -Url $asset.browser_download_url -Destination $zipPath

    # Verify the zip's published SHA-256 (or warn if none is published).
    Confirm-Hash -FilePath $zipPath -Expected (Get-PublishedHash $Release.body $asset.name) -Label $asset.name

    # Extract; the zip nests the app under GAMGUI\, but tolerate a flat layout.
    $extractDir = Join-Path $TempDir "extracted"
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
    $sourceApp = Join-Path $extractDir "GAMGUI"
    if (-not (Test-Path -LiteralPath (Join-Path $sourceApp "GAMGUI.exe"))) {
        if (Test-Path -LiteralPath (Join-Path $extractDir "GAMGUI.exe")) {
            $sourceApp = $extractDir
        } else {
            throw "Extracted files do not contain GAMGUI.exe; unexpected zip layout."
        }
    }

    # Mirror the new app over InstallRoot, preserving settings + marker + Logs.
    # robocopy exit codes 0-7 are success (bit flags); 8+ is a real failure.
    if (-not (Test-Path -LiteralPath $InstallRoot)) {
        New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    }
    Say "Installing portable copy to $InstallRoot ..."
    robocopy $sourceApp $InstallRoot /MIR /XF gamgui.ini gamgui-version.txt /XD Logs /R:2 /W:2 /NFL /NDL /NP /NJH /NJS | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "robocopy failed with exit code $rc (is the folder in use or read-only?)."
    }

    Set-Content -LiteralPath $MarkerFile -Value $LatestTag -Encoding ASCII
    Say "Portable copy updated to $LatestTag." "Green"
    Write-Log "Portable update complete: $currentTag -> $LatestTag (robocopy rc=$rc)."
    return $true
}

function Update-Exe {
    # Updates the Setup.exe (Program Files) install by re-running the new
    # installer silently. Returns $true if it installed, $false if skipped.
    param($Release, [string]$LatestTag, [version]$LatestVer, $ExeInfo)

    $currentTag = if ($ExeInfo.Version) { $ExeInfo.Version } else { "(unknown)" }
    Say "Setup.exe install ($($ExeInfo.InstallLocation)): $currentTag"

    $currentVer = Convert-ToVersion $currentTag
    $needs = $Force -or ($currentTag -eq "(unknown)") -or ($LatestVer -gt $currentVer)
    if (-not $needs) {
        Say "Setup.exe install is already up to date ($currentTag)." "Green"
        return $false
    }

    # Re-running a per-machine installer needs admin. If we are not elevated we
    # cannot silently install: under -Quiet there is no one to answer UAC, so we
    # skip; interactively we tell the user to re-run as Administrator.
    if (-not (Test-IsAdmin)) {
        Say "The Setup.exe install needs Administrator rights to update. Re-run this script as Administrator to update it." "Yellow"
        Write-Log "Exe update skipped: not elevated."
        return $false
    }

    # Warn if the installed app is running from the exe location; Inno can close
    # it for us (/CLOSEAPPLICATIONS), but a heads-up is logged either way.
    if ($ExeInfo.InstallLocation) {
        $running = Get-RunningInPath -PathRoot $ExeInfo.InstallLocation
        if ($running) {
            Say "GAMGUI is running from the Program Files install; the installer will close it to upgrade." "Yellow"
        }
    }

    # Locate + download the Setup.exe.
    $asset = Get-ReleaseAsset -Release $Release -Pattern "GAMGUI-*Setup.exe"
    if (-not $asset) { throw "Release $LatestTag has no GAMGUI-*Setup.exe asset to update the exe install with." }

    $setupPath = Join-Path $TempDir $asset.name
    Say "Downloading $($asset.name) ..."
    Save-Download -Url $asset.browser_download_url -Destination $setupPath

    # Verify the installer's published SHA-256. Running an installer elevated is
    # sensitive, so we verify when a hash is published; if none is (older
    # releases), Confirm-Hash warns and continues, consistent with the zip path.
    Confirm-Hash -FilePath $setupPath -Expected (Get-PublishedHash $Release.body $asset.name) -Label $asset.name

    # Run the installer silently. Because the AppId is stable, this upgrades the
    # existing install in place and updates the Add/Remove Programs entry.
    #   /VERYSILENT          - no wizard, no progress window
    #   /SUPPRESSMSGBOXES    - no message boxes
    #   /NORESTART           - never reboot the machine
    #   /CLOSEAPPLICATIONS   - close a running GAMGUI so files can be replaced
    #   /NORESTARTAPPLICATIONS - do not auto-reopen what it closed
    Say "Running $($asset.name) silently to upgrade the Program Files install ..."
    $switches = @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                  "/CLOSEAPPLICATIONS", "/NORESTARTAPPLICATIONS")
    $proc = Start-Process -FilePath $setupPath -ArgumentList $switches -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        throw "The installer exited with code $($proc.ExitCode); the exe install was not updated."
    }

    Say "Setup.exe install updated to $LatestTag." "Green"
    Write-Log "Exe update complete: $currentTag -> $LatestTag (installer exit 0)."
    return $true
}

# =============================================================================
# MAIN
# =============================================================================
try {
    Say "GAMGUI updater - checking $Repo for the latest release..." "Cyan"

    # -- Step 1: ask GitHub for the latest release -----------------------------
    # GitHub requires a User-Agent header or it returns HTTP 403. This endpoint
    # is public, so no token is needed for a public repository.
    $headers = @{ "User-Agent" = $UserAgent; "Accept" = "application/vnd.github+json" }
    $release = Invoke-RestMethod -Uri $ApiUrl -Headers $headers

    $latestTag = $release.tag_name
    if ([string]::IsNullOrWhiteSpace($latestTag)) {
        throw "GitHub returned no tag_name; cannot determine the latest version."
    }
    $latestVer = Convert-ToVersion $latestTag
    Say "Latest published release: $latestTag"

    # -- Step 2: detect which install type(s) are present ----------------------
    # Portable = a GAMGUI.exe under -InstallRoot. Exe = our HKLM registry key.
    # If the portable path IS the exe install's folder, it is not a SEPARATE
    # portable copy, so we do not also robocopy it (the installer owns it).
    $exeInfo       = Get-ExeInstall
    $portablePresent = Test-Path -LiteralPath $ExePath
    if ($portablePresent -and $exeInfo.Present -and $exeInfo.InstallLocation) {
        $sameFolder = $false
        try {
            $a = (Resolve-Path -LiteralPath $InstallRoot -ErrorAction SilentlyContinue).Path
            $b = (Resolve-Path -LiteralPath $exeInfo.InstallLocation -ErrorAction SilentlyContinue).Path
            if ($a -and $b -and ($a.TrimEnd('\') -ieq $b.TrimEnd('\'))) { $sameFolder = $true }
        } catch { }
        if ($sameFolder) {
            $portablePresent = $false
            Say "The folder at $InstallRoot is the Setup.exe install; it will be updated as the exe install, not as a separate portable copy." "Yellow"
        }
    }

    # Decide, from -InstallType and what was detected, what to actually do.
    $doZip = $false
    $doExe = $false
    switch ($InstallType) {
        "zip"  { $doZip = $true }
        "exe"  { $doExe = $true }
        "both" { $doZip = $true; $doExe = $true }
        default {
            # auto: update whatever is present. If NEITHER is present, fall back
            # to a first-time PORTABLE install into -InstallRoot (original use).
            $doZip = $portablePresent
            $doExe = $exeInfo.Present
            if (-not $doZip -and -not $doExe) {
                Say "No existing GAMGUI detected; performing a first-time portable install to $InstallRoot." "Cyan"
                $doZip = $true
            }
        }
    }

    if ($doZip -and -not $portablePresent -and $InstallType -ne "auto" -and $InstallType -ne "zip") {
        Say "No portable copy found at $InstallRoot to update." "Yellow"
    }
    if ($doExe -and -not $exeInfo.Present) {
        Say "No Setup.exe install found in the registry to update." "Yellow"
        $doExe = $false
    }

    # -- Step 3: run the requested updates -------------------------------------
    # Only create the temp folder if we will actually download something.
    if ($doZip -or $doExe) {
        New-Item -ItemType Directory -Path $TempDir -Force | Out-Null
    }

    $updatedAny = $false
    if ($doZip) {
        if (Update-Portable -Release $release -LatestTag $latestTag -LatestVer $latestVer) { $updatedAny = $true }
    }
    if ($doExe) {
        if (Update-Exe -Release $release -LatestTag $latestTag -LatestVer $latestVer -ExeInfo $exeInfo) { $updatedAny = $true }
    }

    if (-not $updatedAny) {
        Say "Nothing to do - GAMGUI is already current (or nothing eligible was found)." "Green"
    }

    # -- Step 4: optionally launch ---------------------------------------------
    # Prefer the portable exe; otherwise the exe install's location.
    if ($Launch) {
        $launchExe = $null
        if (Test-Path -LiteralPath $ExePath) {
            $launchExe = $ExePath
        } elseif ($exeInfo.Present -and $exeInfo.InstallLocation) {
            $candidate = Join-Path $exeInfo.InstallLocation "GAMGUI.exe"
            if (Test-Path -LiteralPath $candidate) { $launchExe = $candidate }
        }
        if ($launchExe) {
            Say "Launching GAMGUI..."
            Start-Process -FilePath $launchExe
        }
    }

    Pause-Exit
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
    }
    Pause-Exit
    exit 1
}
finally {
    # Always clean up the temporary download/extract folder, success or fail.
    if (Test-Path -LiteralPath $TempDir) {
        Remove-Item -LiteralPath $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
