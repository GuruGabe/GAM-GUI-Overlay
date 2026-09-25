#!/usr/bin/env bash
# =============================================================================
# build-macos-dmg.sh - stamp the version into GAMGUI.app, RE-SIGN it, verify
# the signature, and build a DMG.
#
# Run AFTER build-app.sh (or the CI build step) has produced dist/GAMGUI.app.
# Usage:
#   installer/build-macos-dmg.sh <version>
# Produces:  GAMGUI-<version>.dmg  in the current directory, and leaves
#            dist/GAMGUI.app stamped and validly signed (the CI workflow zips
#            it AFTER this script, so the zip gets the same app).
#
# WHY THE RE-SIGN (this is what caused "GAMGUI is damaged" on macOS):
#   PyInstaller signs the .app (an "ad-hoc" signature - free, no Apple
#   account). The signature seals every file in the bundle, INCLUDING
#   Contents/Info.plist. Stamping the version into Info.plist afterwards broke
#   that seal, and macOS reports a broken seal as "damaged" - with no way to
#   open it from Finder. Re-signing after every change keeps the seal valid;
#   macOS then shows the normal "cannot be verified" warning for an app that
#   is not notarized by Apple, which users can approve once (README: macOS).
#
# The DMG contains GAMGUI.app plus a symlink to /Applications, so the user just
# opens the DMG and drags GAMGUI into Applications (the standard macOS install).
# =============================================================================
set -euo pipefail

VER="${1:?usage: build-macos-dmg.sh <version>}"
APP="dist/GAMGUI.app"
PLIST="$APP/Contents/Info.plist"
BUNDLE_ID="com.gurugabe.gamgui"

if [ ! -d "$APP" ]; then
    echo "ERROR: $APP not found. Run build-app.sh first." >&2
    exit 1
fi

# ---- 1. Stamp version + bundle id into Info.plist ---------------------------
# Use Set, falling back to Add when a key is missing, so this works on any
# PyInstaller output.
plutil_set() {
    local key="$1" val="$2"
    /usr/libexec/PlistBuddy -c "Set :$key $val" "$PLIST" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Add :$key string $val" "$PLIST"
}
plutil_set "CFBundleShortVersionString" "$VER"
plutil_set "CFBundleVersion" "$VER"
plutil_set "CFBundleIdentifier" "$BUNDLE_ID"
echo "Set app version to $VER (bundle id $BUNDLE_ID)"

# ---- 2. Re-sign (ad-hoc) now that the bundle changed -------------------------
# '--sign -' = ad-hoc signature. '--deep' also re-signs the nested libraries
# and frameworks PyInstaller bundled. '--force' replaces the old signature.
# Extended attributes (e.g. Finder info) are stripped first because codesign
# refuses bundles that carry them ("resource fork ... not allowed").
xattr -cr "$APP"
codesign --force --deep --sign - "$APP"

# ---- 3. Verify - a broken signature must fail the build, not ship ------------
codesign --verify --deep --strict --verbose=2 "$APP"
echo "Signature OK: $APP"

# ---- 4. Build the DMG -------------------------------------------------------
# Stage a folder holding just the app and an Applications shortcut, then build a
# compressed DMG from it with hdiutil (built in - no extra tools needed).
# 'ditto' (not 'cp -R') copies the bundle exactly as macOS expects.
STAGE="$(mktemp -d)"
ditto "$APP" "$STAGE/GAMGUI.app"
ln -s /Applications "$STAGE/Applications"

OUT="GAMGUI-${VER}.dmg"
rm -f "$OUT"
hdiutil create -volname "GAMGUI ${VER}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"

# ---- 5. Verify the app INSIDE the finished DMG too ---------------------------
MNT="$(mktemp -d)"
# The build machine's disk-image service sometimes answers "Resource
# temporarily unavailable" right after 'hdiutil create' (seen on GitHub's
# macOS runners, 09-25-2026) - retry the mount a few times before failing.
ATTACHED=""
for TRY in 1 2 3 4 5; do
    if hdiutil attach -nobrowse -readonly -mountpoint "$MNT" "$OUT" >/dev/null; then
        ATTACHED=1; break
    fi
    echo "hdiutil attach failed (try $TRY of 5) - waiting 10 seconds"
    sleep 10
done
[ -n "$ATTACHED" ] || { echo "ERROR: could not mount $OUT to verify it"; exit 1; }
trap 'hdiutil detach "$MNT" >/dev/null 2>&1 || true' EXIT
codesign --verify --deep --strict --verbose=2 "$MNT/GAMGUI.app"
hdiutil detach "$MNT" >/dev/null
trap - EXIT
echo "Built $OUT (app inside verified)"
