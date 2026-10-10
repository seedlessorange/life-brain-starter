#!/bin/zsh
# Build "Brain Pen.app" at the top of the brain folder (macOS only).
#
#     zsh brain/tools/make_pen_app.sh
#
# Brain Pen is the ⌃⌥R rewriter (pen.swift). It holds Accessibility, which
# lets it read the box she is typing in and press ⌘C and ⌘V for her, so it
# is its own small app rather than a permission handed to Terminal.
#
# Rebuilding makes a different app in macOS's eyes, so Accessibility has to
# be switched on again; the script clears the old switch so macOS asks.
# The brain's security alarm watches pen.swift and the built app.
set -e
cd "${0:A:h}/../.."
ROOT=$PWD
APP="$ROOT/Brain Pen.app"
SRC="$ROOT/brain/tools/pen.swift"
WORK=$(mktemp -d "$ROOT/.brain-pen-build.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# Quit a running copy first: it holds the hotkey.
osascript -e 'tell application id "local.lifebrain.pen" to quit' >/dev/null 2>&1 || true

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
swiftc -O -swift-version 5 -o "$APP/Contents/MacOS/Brain Pen" "$SRC"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key><string>local.lifebrain.pen</string>
  <key>CFBundleName</key><string>Brain Pen</string>
  <key>CFBundleExecutable</key><string>Brain Pen</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleIconFile</key><string>applet</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>LSUIElement</key><true/>
  <key>NSAppTransportSecurity</key>
  <dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict>
</plist>
PLIST

# The brain's own logo as the icon.
LOGO="$ROOT/brain/logo-512.png"
if [ -f "$LOGO" ]; then
  SET="$WORK/pen.iconset"; mkdir "$SET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$LOGO" --out "$SET/icon_${s}x${s}.png" >/dev/null
    d=$((s * 2)); [ $d -le 512 ] && sips -z $d $d "$LOGO" --out "$SET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$SET" -o "$APP/Contents/Resources/applet.icns"
fi

# Signed last, ad hoc: macOS records Accessibility against this signature.
codesign --force --deep --sign - "$APP"
codesign --verify --deep "$APP"

# The old Accessibility switch belongs to the old build and would look on
# while doing nothing. Register this build, then clear Brain Pen's entry so
# macOS asks afresh on the next launch.
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$APP" >/dev/null 2>&1 || true
tccutil reset Accessibility local.lifebrain.pen >/dev/null 2>&1 || true
print "Built $APP"
print "Next: open it, then System Settings > Privacy & Security > Accessibility > Brain Pen on"
