#!/usr/bin/env bash
# Step 2 of the release flow (after ./prepare-release.sh X.Y.Z): reads the
# topmost published version from CHANGELOG.md, tags it annotated and pushes the
# tag. The version lives ONLY in the changelog; the tag is a pure derivation.
# The build/release workflow does the rest.
#
# Usage:  ./release.sh [remote ...]     (default remote: origin)
set -euo pipefail

VERSION=$(sed -nE 's/^## \[([0-9]+\.[0-9]+\.[0-9]+)\].*/\1/p' CHANGELOG.md | head -1)

if [ -z "${VERSION:-}" ]; then
  echo "No version found in CHANGELOG.md." >&2
  exit 1
fi

TAG="v$VERSION"

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "Tag $TAG already exists." >&2
  exit 1
fi

# Warn if there are uncommitted changelog changes: the workflow reads
# CHANGELOG.md from the tagged commit, not from the working directory.
if ! git diff --quiet -- CHANGELOG.md || ! git diff --cached --quiet -- CHANGELOG.md; then
  echo "Warning: CHANGELOG.md has uncommitted changes — commit first," >&2
  echo "otherwise the tag points to a state without the ${VERSION} section." >&2
  exit 1
fi

git tag -a "$TAG" -m "Release $VERSION"

for remote in "${@:-origin}"; do
  git push "$remote" "$TAG"
done

echo "Tagged and pushed: $TAG"
