#!/bin/zsh
# Build "Brain Server.app" at the top of the brain folder (macOS only).
#
#     zsh brain/tools/make_brain_app.sh
#
# Why it exists: reading Voice Memos and Mail's index needs Full Disk Access,
# and granting that to Terminal hands it to everything run in Terminal too
# (install scripts, other tools). Brain Server gets it instead, and only the
# server it starts inherits it. Not "Brain": that name is her Safari web app
# for the page.
#
# Rebuilding makes a different app in macOS's eyes, so the permission has to
# be granted again. Rebuild only when brain_app.applescript changes; the
# behaviour lives in brain_app.sh, which can change freely.
set -e
cd "${0:A:h}/../.."
ROOT=$PWD
APP="$ROOT/Brain Server.app"
SRC="$ROOT/brain/tools/brain_app.applescript"
WORK=$(mktemp -d "$ROOT/.brain-app-build.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

rm -rf "$APP"
osacompile -s -o "$APP" "$SRC"            # -s: stays open, so it can quit cleanly

# The brain's own logo as the icon.
LOGO="$ROOT/brain/logo-512.png"
if [ -f "$LOGO" ]; then
  SET="$WORK/brain.iconset"; mkdir "$SET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$LOGO" --out "$SET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2)); [ $d -le 512 ] && sips -z $d $d "$LOGO" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$SET" -o "$APP/Contents/Resources/applet.icns"
fi

PL="$APP/Contents/Info.plist"
plutil -replace CFBundleIdentifier -string "local.lifebrain.server" "$PL"
plutil -replace CFBundleName -string "Brain Server" "$PL"
# The applet's stock icon catalog would win over applet.icns.
plutil -remove CFBundleIconName "$PL" 2>/dev/null || true
rm -f "$APP/Contents/Resources/Assets.car"

# Signed last, ad hoc: macOS records the permission against this signature.
codesign --force --deep --sign - "$APP"
codesign --verify --deep "$APP"
print "Built $APP"
print "Next: System Settings > Privacy & Security > Full Disk Access > + > Brain Server"
