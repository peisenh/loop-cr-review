# Android wheels

| File | In git? | Source |
|------|---------|--------|
| `numpy-2.3.2-1-*-android_24_arm64_v8a.whl` | no | `./tools/fetch-android-wheels.sh` → <https://chaquo.com/pypi-upstream/> |

numpy is the only compiled dependency left. matplotlib used to be committed here
as a hand-built wheel — the charts are drawn as SVG now, so it is gone, and with
it the wheel build script, the numpy version coupling and the 16 KB questions
that came with building one by hand.

Licenses: [NOTICE.md](NOTICE.md).
