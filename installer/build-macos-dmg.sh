#!/usr/bin/env bash
# =============================================================================
# build-macos-dmg.sh - stamp the version into GAMGUI.app and build a DMG.
#
# Run AFTER build-app.sh has produced dist/GAMGUI.app. Usage:
#   installer/build-macos-dmg.sh <version>
# Produces:  GAMGUI-<version>.dmg  in the current directory.
#
# The DMG contains GAMGUI.app plus a symlink to /Applications, so the user just
# opens the DMG and drags GAMGUI into Applications (the standard macOS install).
# macOS then knows the app and its version from the app's Info.plist
# (CFBundleShortVersionString / CFBundleVersion), which we set here. The app is
# NOT code-signed, so the first launch is right-click -> Open.
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

# Set version + a stable bundle identifier in the app's Info.plist. Use Set,
# falling back to Add when a key is missing, so this works on any PyInstaller
# output.
plutil_set() {
    local key="$1" val="$2"
    /usr/libexec/PlistBuddy -c "Set :$key $val" "$PLIST" 2>/dev/null \
        || /usr/libexec/PlistBuddy -c "Add :$key string $val" "$PLIST"
}
plutil_set "CFBundleShortVersionString" "$VER"
plutil_set "CFBundleVersion" "$VER"
plutil_set "CFBundleIdentifier" "$BUNDLE_ID"
echo "Set app version to $VER (bundle id $BUNDLE_ID)"

# Stage a folder holding just the app and an Applications shortcut, then build a
# compressed DMG from it with hdiutil (built in - no extra tools needed).
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

OUT="GAMGUI-${VER}.dmg"
rm -f "$OUT"
hdiutil create -volname "GAMGUI ${VER}" -srcfolder "$STAGE" -ov -format UDZO "$OUT"
rm -rf "$STAGE"
echo "Built $OUT"
