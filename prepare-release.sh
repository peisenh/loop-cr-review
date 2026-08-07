#!/usr/bin/env bash
# Schritt 1 des Release-Ablaufs: die "## [Unreleased]"-Sektion in CHANGELOG.md
# zu einem echten Versionsblock machen (mit heutigem Datum), eine frische leere
# Unreleased-Sektion oben ergaenzen, die Compare-Links unten aktualisieren --
# und das Ganze committen und pushen. Taggen passiert separat in release.sh.
#
# Aufruf:  ./prepare-release.sh X.Y.Z [remote ...]     (Default-Remote: origin)
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Aufruf: ./prepare-release.sh X.Y.Z [remote ...]" >&2
  exit 1
fi
VERSION="$1"; shift || true
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Version '$VERSION' sieht nicht wie X.Y.Z aus." >&2
  exit 1
fi
TAG="v$VERSION"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "Tag $TAG existiert bereits." >&2
  exit 1
fi
if ! git diff --quiet -- CHANGELOG.md || ! git diff --cached --quiet -- CHANGELOG.md; then
  echo "CHANGELOG.md hat bereits uncommittete Aenderungen -- erst klaeren." >&2
  exit 1
fi
if ! grep -q '^## \[Unreleased\]$' CHANGELOG.md; then
  echo "Keine '## [Unreleased]'-Sektion in CHANGELOG.md gefunden." >&2
  exit 1
fi
UNRELEASED_BODY=$(sed -n '/^## \[Unreleased\]$/,/^## \[/p' CHANGELOG.md | sed '1d;$d')
if [ -z "$(echo "$UNRELEASED_BODY" | tr -d '[:space:]')" ]; then
  echo "'## [Unreleased]' ist leer -- nichts zu releasen." >&2
  exit 1
fi

PREV_VERSION=$(grep -oP '^## \[\K[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | head -1)
DATE=$(date +%Y-%m-%d)
REPO_URL=$(grep -oP '(?<=\[0\.1\.0\]: )https://\S+(?=/releases/tag/v0\.1\.0)' CHANGELOG.md \
  || echo "https://github.com/OWNER/REPO")

# 1) "## [Unreleased]" -> "## [Unreleased]\n\n## [X.Y.Z] - DATUM" (frische leere
#    Unreleased-Sektion bleibt oben stehen, der bisherige Inhalt wandert in den
#    neuen Versionsblock darunter -- die Kopfzeile allein reicht als Ersetzung).
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

# 2) Compare-Links unten ergaenzen/aktualisieren.
if [ -n "$PREV_VERSION" ]; then
  NEW_UNRELEASED_LINK="[Unreleased]: ${REPO_URL}/compare/v${VERSION}...HEAD"
  NEW_VERSION_LINK="[${VERSION}]: ${REPO_URL}/compare/v${PREV_VERSION}...v${VERSION}"
  if grep -q '^\[Unreleased\]: ' CHANGELOG.md; then
    sed -i "s#^\[Unreleased\]: .*#${NEW_UNRELEASED_LINK}#" CHANGELOG.md
  else
    printf '\n%s\n' "$NEW_UNRELEASED_LINK" >> CHANGELOG.md
  fi
  # neue Versionszeile direkt nach der Unreleased-Link-Zeile einfuegen
  awk -v newline="$NEW_VERSION_LINK" '
    { print }
    /^\[Unreleased\]: / && !done { print newline; done=1 }
  ' CHANGELOG.md > CHANGELOG.md.tmp && mv CHANGELOG.md.tmp CHANGELOG.md
fi

echo "--- CHANGELOG.md (Ausschnitt) ---"
sed -n '1,20p' CHANGELOG.md
echo "..."

git add CHANGELOG.md
git commit -s -m "changelog: release $VERSION"

for remote in "${@:-origin}"; do
  git push "$remote"
done

echo
echo "Vorbereitet und gepusht: $VERSION (noch kein Tag)."
echo "Naechster Schritt: ./release.sh"
