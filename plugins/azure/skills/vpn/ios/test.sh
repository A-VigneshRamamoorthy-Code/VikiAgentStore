#!/bin/bash
# Runs the StoreKit tests (trial start, trial ending, paid period ending) on a simulator
# against the local AvenVPN.storekit. Usage: ./test.sh [simulator-udid]
set -euo pipefail
cd "$(dirname "$0")"
xcodegen -q
# XcodeGen only sets the StoreKit config on the Run action; the Test action needs it too,
# or purchases go to the sandbox and wait for an Apple Account sign-in.
python3 - <<'PY'
p = "AvenVPN.xcodeproj/xcshareddata/xcschemes/AvenVPN.xcscheme"
s = open(p).read()
ref = '      <StoreKitConfigurationFileReference\n         identifier = "../../AvenVPN.storekit">\n      </StoreKitConfigurationFileReference>\n   '
i = s.index("</TestAction>")
if "StoreKitConfigurationFileReference" not in s[s.index("<TestAction"):i]:
    s = s[:i] + ref + s[i:]
open(p, "w").write(s)
PY
DEST=${1:+id=$1}
DEST=${DEST:-"platform=iOS Simulator,name=iPhone 17"}
xcodebuild test -project AvenVPN.xcodeproj -scheme AvenVPN -destination "$DEST" \
  -only-testing:AvenVPNTests -test-timeouts-enabled YES -maximum-test-execution-time-allowance 120
