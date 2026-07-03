# 7. Distribution — DMG, GitHub release, README, launch posts

## DMG (drag-to-install) with built-in hdiutil (no Homebrew/create-dmg)
```bash
# scripts/make_dmg.sh
APP=build/App.app; DMG=App.dmg; STAGE=build/dmg-stage
rm -rf "$STAGE" "$DMG"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"          # drag target
hdiutil create -volname "App" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG"
```
Verify it:
```bash
hdiutil verify App.dmg
MP=$(hdiutil attach App.dmg -nobrowse -readonly | grep Volumes | awk '{print $3}')
ls "$MP"                                # App.app + Applications symlink
shasum "$MP/App.app/Contents/MacOS/App" build/App.app/Contents/MacOS/App  # hashes MATCH
hdiutil detach "$MP"
```
A NotchPaw-sized app is ~600KB compressed. Gatekeeper note for users: an ad-hoc
signed (un-notarized) app needs **right-click → Open** on first launch.

## GitHub publish — needs the USER's credentials
`gh` requires interactive auth (`gh auth login`) — **the agent cannot authenticate
as the user**. If `gh`/Homebrew aren't installed, do all local prep and hand off.
Make a `scripts/publish.sh` that's idempotent and self-checking:
```bash
command -v gh >/dev/null || { echo "install gh + run: gh auth login"; exit 1; }
gh auth status >/dev/null || { echo "run: gh auth login"; exit 1; }
USER=$(gh api user --jq .login)                    # derive real username
[ -f App.dmg ] || { ./scripts/build_app.sh release && ./scripts/make_dmg.sh; }
gh repo create App --public --source=. --remote=origin --push   # or: git push if origin exists
gh release create v1.0.0 App.dmg --title "App v1.0.0" --notes "…"
gh repo edit --add-topic macos --add-topic notch --add-topic swift
```

## Git hygiene
`.gitignore` must exclude build artifacts and the DMG:
```
.build/        # SwiftPM
build/         # assembled .app + icon intermediates (regenerated)
*.dmg          # release artifact (attached to the GitHub release)
.DS_Store
```
Commit only source + scripts + README + assets. Set a repo-local identity (don't
touch global config) if none exists; include the project's required commit trailer.

## README & launch copy
- README: lead with the *delight hook* (what the creature does), then Features,
  Install (DMG drag + first-launch right-click→Open), Build-from-source (SwiftPM,
  no Xcode), and a Screenshots/GIF placeholder.
- Optional `launch_posts/` (reddit, hackernews "Show HN", producthunt, twitter,
  indiehackers) — write copy that sells the *behavior*, not generic "enhances your
  notch" filler.

## Common environment reality
Many Macs have **only Command Line Tools** (no Xcode/XCTest), and often **no
Homebrew and no gh**. Detect and degrade gracefully:
- `hdiutil`, `iconutil`, `sips`, `git`, `curl` are built-in → DMG/icon/local git
  all work without installs.
- `gh` publish must be handed to the user with clear 1-2-3 steps.
