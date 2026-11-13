#!/bin/sh
# Build Leap VPN.app (internal name LeapVPN) + its WireGuard packet-tunnel Network Extension without Xcode,
# sign both with your Apple Development identity and install into /Applications.
#
# Needs: Command Line Tools (swift, clang), Go (brew install go), and provisioning
# profiles from tools/provision.py (App Store Connect API key).
#
# LEAPVPN_MAS=1 builds the sandboxed Mac App Store variant instead: signed with the
# "3rd Party Mac Developer" identities and the MAC_APP_STORE profiles in .build/profiles-mas,
# packaged as .build/LeapVPN.pkg for upload (LEAPVPN_BUILD sets the build number).
set -eu
cd "$(dirname "$0")"
ROOT=$(pwd)
DEST="${1:-/Applications}"
BUNDLE_ID="${LEAPVPN_BUNDLE_ID:-com.sololeap.leapvpn}"
TUNNEL_ID="$BUNDLE_ID.tunnel"
WG_REF="${WG_REF:-master}"
B="$ROOT/.build"
MAS="${LEAPVPN_MAS:-0}"
BUILD_NO="${LEAPVPN_BUILD:-2}"
PROFILES="$B/profiles"
[ "$MAS" = 1 ] && PROFILES="$B/profiles-mas"
WG="$B/wireguard-apple"
SIGN_KIND="Apple Development"; [ "$MAS" = 1 ] && SIGN_KIND="3rd Party Mac Developer Application"
IDENTITY="${LEAPVPN_SIGN_IDENTITY:-$(security find-identity -v -p codesigning | awk -F'"' -v k="$SIGN_KIND" 'index($0,k){print $2; exit}')}"
[ -n "$IDENTITY" ] || { echo "no Apple Development signing identity" >&2; exit 1; }
for id in "$BUNDLE_ID" "$TUNNEL_ID"; do
  [ -f "$PROFILES/$id.provisionprofile" ] || { echo "missing $PROFILES/$id.provisionprofile — run tools/provision.py" >&2; exit 1; }
done
TEAM=$(security cms -D -i "$PROFILES/$BUNDLE_ID.provisionprofile" | plutil -extract TeamIdentifier.0 raw -o - -)
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin"

# --- WireGuardKit (wireguard-go as a static library + the Swift wrapper) ---
if [ ! -d "$WG" ]; then
  git clone -q https://github.com/WireGuard/wireguard-apple.git "$WG"
  git -C "$WG" checkout -q "$WG_REF"
fi
# Newer SDKs build Clang modules strictly: the header uses u_int32_t without including it.
HDR="$WG/Sources/WireGuardKitC/WireGuardKitC.h"
grep -q '<sys/types.h>' "$HDR" || sed -i '' 's|#include "key.h"|#include <sys/types.h>\
#include "key.h"|' "$HDR"
LIBWG="$WG/Sources/WireGuardKitGo/out/libwg-go.a"
[ -f "$LIBWG" ] || make -C "$WG/Sources/WireGuardKitGo" ARCHS=arm64 MACOSX_DEPLOYMENT_TARGET=14.0 >/dev/null

# --- packet tunnel extension ---
OBJ="$B/tunnel-obj"; mkdir -p "$OBJ"
SDK=$(xcrun --sdk macosx --show-sdk-path)
TARGET=arm64-apple-macos14.0
for c in key x25519; do
  clang -O2 -target $TARGET -isysroot "$SDK" -c "$WG/Sources/WireGuardKitC/$c.c" -o "$OBJ/$c.o"
done
swiftc -O -parse-as-library -application-extension -target $TARGET -sdk "$SDK" \
  -module-name LeapVPNTunnel -D SWIFT_PACKAGE \
  -I "$WG/Sources/WireGuardKitC" -I "$WG/Sources/WireGuardKitGo" \
  "$WG"/Sources/WireGuardKit/*.swift Tunnel/PacketTunnelProvider.swift \
  "$OBJ/key.o" "$OBJ/x25519.o" -L "$WG/Sources/WireGuardKitGo/out" -lwg-go \
  -framework NetworkExtension -Xlinker -e -Xlinker _NSExtensionMain \
  -o "$OBJ/LeapVPNTunnel"

# --- app ---
swift build -c release
APP="$B/LeapVPN.app"
APPEX="$APP/Contents/PlugIns/LeapVPNTunnel.appex"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APPEX/Contents/MacOS"
cp "$(swift build -c release --show-bin-path)/LeapVPN" "$APP/Contents/MacOS/LeapVPN"
mkdir -p "$APP/Contents/Resources"
cp "$ROOT/../homeexit/Install-LeapVPNExit.ps1" "$APP/Contents/Resources/"
# The app provisions servers itself, so it carries the VM agent and the reconciler runbook.
mkdir -p "$APP/Contents/Resources/server"
cp "$ROOT"/../server/* "$APP/Contents/Resources/server/"
cp "$ROOT/../reconciler/Reconcile-LeapVPN.ps1" "$APP/Contents/Resources/"
cp "$ROOT"/Assets/AppIcon.icns "$ROOT"/Assets/MenuBarTemplate*.png "$APP/Contents/Resources/"
cp "$OBJ/LeapVPNTunnel" "$APPEX/Contents/MacOS/LeapVPNTunnel"
cp "$PROFILES/$BUNDLE_ID.provisionprofile" "$APP/Contents/embedded.provisionprofile"
cp "$PROFILES/$TUNNEL_ID.provisionprofile" "$APPEX/Contents/embedded.provisionprofile"

plist() { # id name exe type extra
  cat <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleIdentifier</key><string>$1</string>
  <key>CFBundleName</key><string>$2</string>
  <key>CFBundleDisplayName</key><string>$2</string>
  <key>CFBundleExecutable</key><string>$3</string>
  <key>CFBundlePackageType</key><string>$4</string>
  <key>CFBundleShortVersionString</key><string>1.1.0</string>
  <key>CFBundleVersion</key><string>$BUILD_NO</string>
  <key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSHumanReadableCopyright</key><string>MIT</string>
$5
</dict></plist>
P
}
plist "$BUNDLE_ID" "Leap VPN" LeapVPN APPL '  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.utilities</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundleURLTypes</key><array><dict>
    <key>CFBundleURLName</key><string>LeapVPN control</string>
    <key>CFBundleURLSchemes</key><array><string>leapvpn</string></array>
  </dict></array>' > "$APP/Contents/Info.plist"
plist "$TUNNEL_ID" "Leap VPN Tunnel" LeapVPNTunnel XPC! '  <key>NSExtension</key><dict>
    <key>NSExtensionPointIdentifier</key><string>com.apple.networkextension.packet-tunnel</string>
    <key>NSExtensionPrincipalClass</key><string>LeapVPNTunnel.PacketTunnelProvider</string>
  </dict>' > "$APPEX/Contents/Info.plist"

ent() { # app-id sandboxed
  cat <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>com.apple.application-identifier</key><string>$TEAM.$1</string>
  <key>com.apple.developer.team-identifier</key><string>$TEAM</string>
  <key>com.apple.developer.networking.networkextension</key><array><string>packet-tunnel-provider</string></array>
$2
</dict></plist>
P
}
ent "$TUNNEL_ID" '  <key>com.apple.security.app-sandbox</key><true/>
  <key>com.apple.security.network.client</key><true/>
  <key>com.apple.security.network.server</key><true/>' > "$B/tunnel.entitlements"
if [ "$MAS" = 1 ]; then
  # Sandboxed: Application Support resolves inside the container; the home-PC installer goes to Downloads.
  ent "$BUNDLE_ID" '  <key>com.apple.security.app-sandbox</key><true/>
  <key>com.apple.security.network.client</key><true/>
  <key>com.apple.security.files.downloads.read-write</key><true/>
  <key>com.apple.security.files.user-selected.read-write</key><true/>' > "$B/app.entitlements"
else
  ent "$BUNDLE_ID" '' > "$B/app.entitlements"
fi

codesign --force --options runtime --timestamp=none --sign "$IDENTITY" --entitlements "$B/tunnel.entitlements" "$APPEX"
codesign --force --options runtime --timestamp=none --sign "$IDENTITY" --entitlements "$B/app.entitlements" "$APP"
codesign --verify --deep --strict "$APP"

if [ "$MAS" = 1 ]; then
  INSTALLER=$(security find-identity -v | awk -F'"' '/3rd Party Mac Developer Installer/{print $2; exit}')
  rm -f "$B/LeapVPN.pkg"
  productbuild --component "$APP" /Applications --sign "$INSTALLER" "$B/LeapVPN.pkg" >/dev/null
  echo "packaged $B/LeapVPN.pkg (build $BUILD_NO, team $TEAM)"
  exit 0
fi

# Quit a running copy so the new extension is picked up.
osascript -e 'tell application id "'"$BUNDLE_ID"'" to quit' >/dev/null 2>&1 || true
rm -rf "$DEST/Leap VPN.app"
cp -R "$APP" "$DEST/Leap VPN.app"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$DEST/Leap VPN.app"
echo "installed $DEST/Leap VPN.app (team $TEAM)"
