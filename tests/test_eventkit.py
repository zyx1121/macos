#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Offline self-check for lib/_eventkit.py's date form.

The calendar and reminders atoms read through EventKit but keep printing
dates the way AppleScript did (`Monday, September 28, 2026 at 3:30:00 PM`),
because callers such as today-mod parse that form. Checks the hour edges,
that the names stay English under another locale, and that every string
matches today-mod's parser. Needs no EventKit and runs on any OS.

    ./tests/test_eventkit.py
"""
from __future__ import annotations

import locale
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from _eventkit import apple_date  # noqa: E402

# today-mod hooks/agenda.ts APPLE_DATE, verbatim.
APPLE_DATE = re.compile(r"^(?:\w+, )?(\w+) (\d{1,2}), (\d{4})(?: at (\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AP]M)?)?$", re.I)

CASES = {
    datetime(2026, 9, 28, 0, 0): "Monday, September 28, 2026 at 12:00:00 AM",
    datetime(2026, 9, 28, 0, 5, 9): "Monday, September 28, 2026 at 12:05:09 AM",
    datetime(2026, 10, 1, 10, 10): "Thursday, October 1, 2026 at 10:10:00 AM",
    datetime(2026, 7, 13, 12, 0): "Monday, July 13, 2026 at 12:00:00 PM",
    datetime(2026, 7, 13, 15, 30): "Monday, July 13, 2026 at 3:30:00 PM",
    datetime(2025, 12, 31, 23, 59, 59): "Wednesday, December 31, 2025 at 11:59:59 PM",
}


def main() -> int:
    failures = []
    for dt, want in CASES.items():
        got = apple_date(dt)
        if got != want:
            failures.append(f"{dt}: got {got!r}, want {want!r}")
        if not APPLE_DATE.match(got):
            failures.append(f"{got!r} does not match today-mod's parser")

    for name in ("zh_TW.UTF-8", "de_DE.UTF-8", "ja_JP.UTF-8"):
        try:
            locale.setlocale(locale.LC_ALL, name)
        except locale.Error:
            continue
        got = apple_date(datetime(2026, 9, 28, 15, 30))
        if got != "Monday, September 28, 2026 at 3:30:00 PM":
            failures.append(f"under {name}: got {got!r}")
        break
    locale.setlocale(locale.LC_ALL, "C")

    for line in failures:
        print(f"FAIL {line}")
    print("ok" if not failures else f"{len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
