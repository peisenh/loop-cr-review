#!/usr/bin/env bash
# Step 1 of the release flow: turn the "## [Unreleased]" section in CHANGELOG.md
# into a real version block (with today's date), add a fresh empty Unreleased
# section on top, update the compare links at the bottom -- then commit and push.
# Tagging happens separately in release.sh.
#
# Usage:  ./prepare-release.sh X.Y.Z [remote ...]     (default remote: origin)
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: ./prepare-release.sh X.Y.Z [remote ...]" >&2
  exit 1
fi
VERSION="$1"; shift || true
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version '$VERSION' does not look like X.Y.Z." >&2
  exit 1
fi
TAG="v$VERSION"

# Increment the Android Play versionCode for every prepared release.
ANDROID_GRADLE="android/app/build.gradle.kts"
if [ ! -f "$ANDROID_GRADLE" ]; then
  echo "Android build.gradle.kts not found: $ANDROID_GRADLE" >&2
  exit 1
fi
CURRENT_VERSION_CODE=$(sed -nE 's/^[[:space:]]*versionCode[[:space:]]*=[[:space:]]*([0-9]+)[[:space:]]*$/\1/p' "$ANDROID_GRADLE")
if [ -z "$CURRENT_VERSION_CODE" ]; then
  echo "Could not determine Android versionCode." >&2
  exit 1
fi
if [ "$(printf '%s\n' "$CURRENT_VERSION_CODE" | wc -l)" -ne 1 ]; then
  echo "Expected exactly one Android versionCode." >&2
  exit 1
fi
NEXT_VERSION_CODE=$((CURRENT_VERSION_CODE + 1))
sed -i -E "s/^([[:space:]]*versionCode[[:space:]]*=)[[:space:]]*[0-9]+([[:space:]]*)$/\1 $NEXT_VERSION_CODE\2/" "$ANDROID_GRADLE"
echo "Android versionCode: $CURRENT_VERSION_CODE -> $NEXT_VERSION_CODE"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "Tag $TAG already exists." >&2
  exit 1
fi
if ! git diff --quiet -- CHANGELOG.md || ! git diff --cached --quiet -- CHANGELOG.md; then
  echo "CHANGELOG.md already has uncommitted changes -- resolve first." >&2
  exit 1
fi
if ! grep -q '^## \[Unreleased\]$' CHANGELOG.md; then
  echo "No '## [Unreleased]' section found in CHANGELOG.md." >&2
  exit 1
fi
UNRELEASED_BODY=$(sed -n '/^## \[Unreleased\]$/,/^## \[/p' CHANGELOG.md | sed '1d;$d')
if [ -z "$(echo "$UNRELEASED_BODY" | tr -d '[:space:]')" ]; then
  echo "'## [Unreleased]' is empty -- nothing to release." >&2
  exit 1
fi

PREV_VERSION=$(grep -oP '^## \[\K[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | head -1)
DATE=$(date +%Y-%m-%d)
REPO_URL=$(grep -oP '(?<=\[0\.1\.0\]: )https://\S+(?=/releases/tag/v0\.1\.0)' CHANGELOG.md \
  || echo "https://github.com/OWNER/REPO")

# 1) "## [Unreleased]" -> "## [Unreleased]\n\n## [X.Y.Z] - DATE" (fresh empty
#    Unreleased section stays on top, the previous content moves into the new
#    version block below -- replacing the header line alone is enough).
python3 - "$VERSION" "$DATE" <<'PYEOF'
import re
import sys
version, date = sys.argv[1], sys.argv[2]
text = open("CHANGELOG.md", encoding="utf-8").read()
text = text.replace(
    "## [Unreleased]\n",
    f"## [Unreleased]\n\n## [{version}] - {date}\n",
    1,
)
open("CHANGELOG.md", "w", encoding="utf-8").write(text)
PYEOF

# 2) Add/update the compare links at the bottom.
if [ -n "$PREV_VERSION" ]; then
  NEW_UNRELEASED_LINK="[Unreleased]: ${REPO_URL}/compare/v${VERSION}...HEAD"
  NEW_VERSION_LINK="[${VERSION}]: ${REPO_URL}/compare/v${PREV_VERSION}...v${VERSION}"
  if grep -q '^\[Unreleased\]: ' CHANGELOG.md; then
    sed -i "s#^\[Unreleased\]: .*#${NEW_UNRELEASED_LINK}#" CHANGELOG.md
  else
    printf '\n%s\n' "$NEW_UNRELEASED_LINK" >> CHANGELOG.md
  fi
  # insert the new version line right after the Unreleased link line
  awk -v newline="$NEW_VERSION_LINK" '
    { print }
    /^\[Unreleased\]: / && !done { print newline; done=1 }
  ' CHANGELOG.md > CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md
fi

echo "--- CHANGELOG.md (excerpt) ---"
sed -n '1,20p' CHANGELOG.md
echo "..."

git add CHANGELOG.md android/app/build.gradle.kts
git commit -s -m "changelog: release $VERSION"

for remote in "${@:-origin}"; do
  git push "$remote"
done

echo
echo "Prepared and pushed: $VERSION (no tag yet)."
echo "Next step: ./release.sh"
