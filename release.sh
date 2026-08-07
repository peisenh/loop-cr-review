#!/usr/bin/env bash
# Schritt 2 des Release-Ablaufs (nach ./prepare-release.sh X.Y.Z): liest die
# oberste veroeffentlichte Version aus CHANGELOG.md, taggt sie annotiert und
# pusht den Tag. Die Version steht NUR im Changelog; der Tag ist reine
# Ableitung. Der Build-/Release-Workflow erledigt den Rest.
#
# Aufruf:  ./release.sh [remote ...]     (Default-Remote: origin)
set -euo pipefail

VERSION=$(grep -oP '^## \[\K[0-9]+\.[0-9]+\.[0-9]+' CHANGELOG.md | head -1)

if [ -z "${VERSION:-}" ]; then
  echo "Keine Version in CHANGELOG.md gefunden." >&2
  exit 1
fi

TAG="v$VERSION"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "Tag $TAG existiert bereits." >&2
  exit 1
fi

# Warnen, falls uncommittete Changelog-Aenderungen vorliegen: der Workflow
# liest CHANGELOG.md vom getaggten Commit, nicht vom Arbeitsverzeichnis.
if ! git diff --quiet -- CHANGELOG.md || ! git diff --cached --quiet -- CHANGELOG.md; then
  echo "Warnung: CHANGELOG.md hat uncommittete Aenderungen — erst committen," >&2
  echo "sonst zeigt der Tag auf einen Stand ohne den ${VERSION}-Abschnitt." >&2
  exit 1
fi

git tag -a "$TAG" -m "Release $VERSION"

for remote in "${@:-origin}"; do
  git push "$remote" "$TAG"
done

echo "Getaggt und gepusht: $TAG"
