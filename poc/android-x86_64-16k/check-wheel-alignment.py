#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check that a wheel's native libraries load on a 16 KB page size device.

The whole reason these wheels are built by hand is alignment: a shared object
whose PT_LOAD segments are aligned to 4 KB is refused outright by the linker on
a device with 16 KB pages, with a message that names the library and nothing
else. That failure only shows on the device, long after the build.

So it is checked here, on the wheel, right after it is built. Reads the ELF
program headers directly rather than shelling out to readelf, which is not
installed everywhere.

Usage:  check-wheel-alignment.py <wheel> [...]
"""
import struct
import sys
import zipfile
from pathlib import Path

WANT_ALIGN = 16384          # what a 16 KB page size device needs
PT_LOAD = 1


def load_aligns(blob):
    """Alignment of every PT_LOAD segment in an ELF image. -> list[int]"""
    if blob[:4] != b"\x7fELF":
        return []
    is_64 = blob[4] == 2
    little = blob[5] == 1
    end = "<" if little else ">"
    if not is_64:
        # Every Android ABI this project targets is 64-bit; a 32-bit object
        # here means something went wrong earlier, so say so rather than guess.
        raise ValueError("32-bit ELF, expected a 64-bit Android ABI")
    e_phoff, = struct.unpack_from(end + "Q", blob, 0x20)
    e_phentsize, e_phnum = struct.unpack_from(end + "HH", blob, 0x36)
    aligns = []
    for i in range(e_phnum):
        base = e_phoff + i * e_phentsize
        p_type, = struct.unpack_from(end + "I", blob, base)
        if p_type == PT_LOAD:
            p_align, = struct.unpack_from(end + "Q", blob, base + 0x30)
            aligns.append(p_align)
    return aligns


def check(path):
    """-> list of complaints for one wheel"""
    problems, checked = [], 0
    with zipfile.ZipFile(path) as wheel:
        for name in wheel.namelist():
            if not name.endswith(".so") and ".so." not in name:
                continue
            blob = wheel.read(name)
            try:
                aligns = load_aligns(blob)
            except ValueError as exc:
                problems.append(f"{name}: {exc}")
                continue
            if not aligns:
                continue
            checked += 1
            worst = min(aligns)
            if worst < WANT_ALIGN:
                problems.append(
                    f"{name}: PT_LOAD align 0x{worst:x}, needs at least "
                    f"0x{WANT_ALIGN:x} — this will not load on a 16 KB device")
    if not checked:
        problems.append("no native libraries found — is this the right wheel?")
    return problems, checked


def main():
    """-> exit code"""
    if len(sys.argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    failed = False
    for name in sys.argv[1:]:
        problems, checked = check(Path(name))
        label = Path(name).name
        if problems:
            failed = True
            print(f"    {label}  REJECTED", file=sys.stderr)
            for problem in problems:
                print(f"      {problem}", file=sys.stderr)
        else:
            print(f"    {label}  {checked} libraries, all 16 KB aligned")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
