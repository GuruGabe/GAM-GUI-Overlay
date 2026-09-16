#!/usr/bin/env bash
# =============================================================================
# build-linux-packages.sh - build a .deb and a .rpm for GAMGUI with fpm.
#
# Run AFTER build-app.sh has produced dist/GAMGUI/ (the one-folder app). Usage:
#   installer/build-linux-packages.sh <version>
# Produces, in the current directory:
#   gamgui_<version>_amd64.deb
#   gamgui-<version>-1.x86_64.rpm
#
# Installing either one registers GAMGUI with the system package manager (dpkg
# / rpm) - so the OS knows it is installed and at what version (dpkg -l gamgui,
# rpm -q gamgui), and it can be removed with apt/dnf/rpm. The app lands in
# /opt/GAMGUI, with a launcher at /usr/bin/gamgui and a desktop-menu entry.
#
# Requires fpm (gem install fpm) and, for the .rpm, the 'rpm' tools; the CI
# workflow installs both.
# =============================================================================
set -euo pipefail

VER="${1:?usage: build-linux-packages.sh <version>}"
APPDIR="dist/GAMGUI"
MAINT="Gabriel Clifton (FSISD IT)"
URL="https://github.com/GuruGabe/GAM-GUI-Overlay"
DESC="GAMGUI - a point-and-click window for the GAM7 Google Workspace CLI."

if [ ! -d "$APPDIR" ]; then
    echo "ERROR: $APPDIR not found. Run build-app.sh first." >&2
    exit 1
fi

# Build a staging tree that mirrors where the files install on the target.
STAGE="$(mktemp -d)"
mkdir -p "$STAGE/opt/GAMGUI" "$STAGE/usr/bin" "$STAGE/usr/share/applications"
cp -R "$APPDIR/." "$STAGE/opt/GAMGUI/"

# A small launcher on PATH so users can just run "gamgui".
cat > "$STAGE/usr/bin/gamgui" <<'EOF'
#!/bin/sh
exec /opt/GAMGUI/GAMGUI "$@"
EOF
chmod 755 "$STAGE/usr/bin/gamgui"

# A desktop-menu entry so it shows up in the application launcher.
cat > "$STAGE/usr/share/applications/gamgui.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=GAMGUI
Comment=$DESC
Exec=/opt/GAMGUI/GAMGUI
Terminal=false
Categories=Utility;System;
EOF

COMMON=(-s dir -n gamgui -v "$VER" --description "$DESC" --url "$URL"
        --maintainer "$MAINT" --license "Apache-2.0" -a amd64
        --category admin -C "$STAGE" .)

# .deb (Debian/Ubuntu)
rm -f gamgui_*.deb
fpm -t deb -p "gamgui_${VER}_amd64.deb" "${COMMON[@]}"

# .rpm (Fedora/RHEL). fpm uses its own arch label for rpm.
rm -f gamgui-*.rpm
fpm -t rpm -a x86_64 -p "gamgui-${VER}-1.x86_64.rpm" -s dir -n gamgui -v "$VER" \
    --description "$DESC" --url "$URL" --maintainer "$MAINT" \
    --license "Apache-2.0" --category admin -C "$STAGE" .

rm -rf "$STAGE"
echo "Built gamgui_${VER}_amd64.deb and gamgui-${VER}-1.x86_64.rpm"
