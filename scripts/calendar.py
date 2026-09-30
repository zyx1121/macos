#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "pyobjc-framework-EventKit; sys_platform == 'darwin'"]
# ///
"""Atomic Calendar operations: reads via EventKit, writes via AppleScript.

show-cals / list / search read through EventKit, so Calendar.app stays closed.
add / delete drive Calendar.app over AppleScript. Dates are built
locale-independently to avoid `date "..."` string parsing failing on
non-English Macs.
"""
from __future__ import annotations

# Siblings shadow stdlib — drop our dir off sys.path so typer/rich resolve.
import sys as _sys
from pathlib import Path as _Path
_sys.path[:] = [p for p in _sys.path if _Path(p).resolve() != _Path(__file__).resolve().parent]
# Add ../lib for shared output helpers (envelope, fail).
_LIB = str(_Path(__file__).resolve().parent.parent / "lib")
if _LIB not in _sys.path:
    _sys.path.insert(0, _LIB)

import subprocess
from datetime import datetime, timedelta
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

app = typer.Typer(
    rich_markup_mode=None,
    no_args_is_help=True,
    add_completion=False,
    help="Atomic Calendar.app ops — show-cals / list / add / search / delete.",
)
console = Console()


def run_as(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False, timeout=60,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not authorized" in stderr or "-1743" in stderr:
            fail(
                "macOS denied Automation access to Calendar",
                why=stderr,
                hint="System Settings > Privacy & Security > Automation: allow this terminal to control Calendar",
                code=2,
            )
        fail(
            stderr or "AppleScript failed",
            hint="run `calendar show-cals` to confirm the calendar name exists and is writable",
            code=2,
        )
    return result.stdout.rstrip("\n")


def escape_as(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def parse_when(when: str) -> datetime:
    """Accept ISO date/datetime, HH:MM (today), 'today', 'tomorrow', 'next week'."""
    s = when.strip().lower()
    now = datetime.now().replace(second=0, microsecond=0)
    if s == "now":
        return now
    if s == "today":
        return now.replace(hour=0, minute=0)
    if s == "tomorrow":
        return (now + timedelta(days=1)).replace(hour=9, minute=0)
    if s in ("next week", "next-week"):
        return (now + timedelta(days=7)).replace(hour=9, minute=0)
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M"):
        try:
            dt = datetime.strptime(when.strip(), fmt)
            if fmt == "%H:%M":
                dt = dt.replace(year=now.year, month=now.month, day=now.day)
            return dt
        except ValueError:
            continue
    fail(
        f"can't parse '{when}'",
        hint="try YYYY-MM-DD, YYYY-MM-DDTHH:MM, 'today', 'tomorrow', 'now'",
        code=2,
    )


def as_date_block(dt: datetime, var: str = "theDate") -> str:
    return (
        f'set {var} to current date\n'
        f'set year of {var} to {dt.year}\n'
        f'set month of {var} to {dt.month}\n'
        f'set day of {var} to {dt.day}\n'
        f'set hours of {var} to {dt.hour}\n'
        f'set minutes of {var} to {dt.minute}\n'
        f'set seconds of {var} to 0'
    )


def cal_clause(cal: Optional[str]) -> str:
    return f'calendar "{escape_as(cal)}"' if cal else 'first calendar whose writable is true'


def events_starting(start_dt: datetime, end_dt: datetime, cal: Optional[str]) -> list:
    """(start, event) for each occurrence starting in [start_dt, end_dt], earliest first.

    A recurring event yields one row per occurrence, at that occurrence's date.
    `cal` keeps every calendar with that title, ignoring case.
    """
    from _eventkit import calendars, local, nsdate, store_for

    store = store_for("event")
    chosen = None
    if cal:
        chosen = calendars(store, "event", cal)
        if not chosen:
            fail(f"no calendar named '{cal}'", hint="run `calendar show-cals` to see the calendar names", code=2)
    # EventKit matches events that overlap the range; the atom lists those that start in it.
    # A second of slack each side keeps zero-length events at either edge.
    predicate = store.predicateForEventsWithStartDate_endDate_calendars_(
        nsdate(start_dt - timedelta(seconds=1)), nsdate(end_dt + timedelta(seconds=1)), chosen,
    )
    rows = []
    for event in store.eventsMatchingPredicate_(predicate) or []:
        start = local(event.startDate())
        if start_dt <= start <= end_dt:
            rows.append((start, event))
    rows.sort(key=lambda row: (row[0], row[1].calendar().title()))
    return rows


# ── show-cals ────────────────────────────────────────────────────
@app.command(name="show-cals", help="List all calendars with writability.")
def show_cals():
    from _eventkit import calendars, store_for

    data = [
        {"name": c.title(), "writable": bool(c.allowsContentModifications())}
        for c in calendars(store_for("event"), "event")
    ]

    def human(rows, _meta):
        table = Table(title="Calendars", show_header=True)
        table.add_column("name", style="bold")
        table.add_column("writable", style="green")
        for c in rows:
            mark = "✓" if c["writable"] else "—"
            table.add_row(c["name"], mark)
        console.print(table)

    emit(data, {"count": len(data)}, human=human)


# ── list ─────────────────────────────────────────────────────────
@app.command(name="list", help="List events in a date range. Default range: today → +7 days.")
def list_cmd(
    cal: Optional[str] = typer.Option(None, "--cal", "-c", help="Filter to a single calendar (default: all)."),
    from_: Optional[str] = typer.Option(None, "--from", help="Range start (default: today 00:00)."),
    to: Optional[str] = typer.Option(None, "--to", help="Range end (default: today + 7 days)."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Cap rows shown."),
):
    start_dt = parse_when(from_) if from_ else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_when(to) if to else start_dt + timedelta(days=7)

    from _eventkit import apple_date

    rows = events_starting(start_dt, end_dt, cal)
    if limit:
        rows = rows[:limit]
    data = [
        {
            "calendar": event.calendar().title(),
            "start": apple_date(start),
            "summary": event.title() or "",
            "location": (event.location() or "").strip(),
        }
        for start, event in rows
    ]

    start_label = start_dt.strftime("%Y-%m-%d")
    end_label = end_dt.strftime("%Y-%m-%d")

    def human(events, _meta):
        if not events:
            console.print(f"[dim](no events in {start_label} – {end_label})[/]")
            return
        table = Table(title=f"Events {start_label} – {end_label}", show_header=True)
        table.add_column("calendar", style="cyan")
        table.add_column("start", style="dim")
        table.add_column("summary", style="bold")
        table.add_column("location", style="dim")
        for e in events:
            table.add_row(e["calendar"], e["start"], e["summary"], e["location"] or "—")
        console.print(table)

    emit(data, {"count": len(data), "from": start_dt.isoformat(), "to": end_dt.isoformat()}, human=human)


# ── add ──────────────────────────────────────────────────────────
@app.command(help="Add a new event. --at and --duration set the time window.")
def add(
    summary: str = typer.Argument(..., help="Event title."),
    at: str = typer.Option(..., "--at", "-a", help="Start time (YYYY-MM-DDTHH:MM, 'tomorrow', etc.)."),
    duration: int = typer.Option(60, "--duration", "-d", help="Duration in minutes (default 60)."),
    cal: Optional[str] = typer.Option(None, "--cal", "-c", help="Calendar name (default: first writable)."),
    location: Optional[str] = typer.Option(None, "--location", "-L", help="Location."),
    notes: Optional[str] = typer.Option(None, "--notes", "-N", help="Description / notes."),
):
    start_dt = parse_when(at)
    end_dt = start_dt + timedelta(minutes=duration)

    props = [f'summary:"{escape_as(summary)}"', "start date:startDt", "end date:endDt"]
    if location:
        props.append(f'location:"{escape_as(location)}"')
    if notes:
        props.append(f'description:"{escape_as(notes)}"')
    props_str = ", ".join(props)

    script = f'''
tell application "Calendar"
    {as_date_block(start_dt, "startDt")}
    {as_date_block(end_dt, "endDt")}
    tell {cal_clause(cal)}
        set newE to make new event with properties {{{props_str}}}
        return summary of newE
    end tell
end tell
'''
    name_out = run_as(script)
    data = {
        "action": "add",
        "summary": name_out,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "calendar": cal,
        "location": location,
    }

    def human(d, _meta):
        msg = (
            f"added: [bold]{d['summary']}[/] · "
            f"{start_dt.strftime('%Y-%m-%d %H:%M')} → {end_dt.strftime('%H:%M')}"
        )
        if d["calendar"]:
            msg += f" · {d['calendar']}"
        if d["location"]:
            msg += f" @ {d['location']}"
        console.print(msg)

    emit(data, human=human)


# ── search ───────────────────────────────────────────────────────
@app.command(help="Search event summaries within a date range (default: today → +30 days).")
def search(
    query: str = typer.Argument(..., help="Search text (case-insensitive substring of summary)."),
    cal: Optional[str] = typer.Option(None, "--cal", "-c", help="Filter to one calendar (default: all)."),
    from_: Optional[str] = typer.Option(None, "--from", help="Range start (default: today)."),
    to: Optional[str] = typer.Option(None, "--to", help="Range end (default: today + 30 days)."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Cap rows shown."),
):
    start_dt = parse_when(from_) if from_ else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_when(to) if to else start_dt + timedelta(days=30)

    from _eventkit import apple_date

    needle = query.casefold()
    rows = [(start, event) for start, event in events_starting(start_dt, end_dt, cal) if needle in (event.title() or "").casefold()]
    if limit:
        rows = rows[:limit]
    data = [
        {"calendar": event.calendar().title(), "start": apple_date(start), "summary": event.title() or ""}
        for start, event in rows
    ]

    def human(events, _meta):
        if not events:
            console.print(f"[dim](no events matching '{query}')[/]")
            return
        table = Table(title=f"Search: '{query}'", show_header=True)
        table.add_column("calendar", style="cyan")
        table.add_column("start", style="dim")
        table.add_column("summary", style="bold")
        for e in events:
            table.add_row(e["calendar"], e["start"], e["summary"])
        console.print(table)

    emit(data, {"count": len(data), "query": query, "from": start_dt.isoformat(), "to": end_dt.isoformat()}, human=human)


# ── delete ───────────────────────────────────────────────────────
@app.command(help="Delete the first event matching <summary> in the date range. Requires --cal for safety.")
def delete(
    summary: str = typer.Argument(..., help="Event summary (exact match)."),
    cal: str = typer.Option(..., "--cal", "-c", help="Calendar to search (required, no fuzzy delete)."),
    from_: Optional[str] = typer.Option(None, "--from", help="Range start (default: today)."),
    to: Optional[str] = typer.Option(None, "--to", help="Range end (default: today + 30 days)."),
):
    start_dt = parse_when(from_) if from_ else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = parse_when(to) if to else start_dt + timedelta(days=30)

    script = f'''
tell application "Calendar"
    {as_date_block(start_dt, "rangeStart")}
    {as_date_block(end_dt, "rangeEnd")}
    tell calendar "{escape_as(cal)}"
        set target to first event whose start date is greater than or equal to rangeStart and start date is less than or equal to rangeEnd and summary is "{escape_as(summary)}"
        set foundName to summary of target
        delete target
        return foundName
    end tell
end tell
'''
    name_out = run_as(script)
    data = {"action": "delete", "summary": name_out, "calendar": cal}

    def human(d, _meta):
        console.print(f"deleted: [bold]{d['summary']}[/] from [cyan]{d['calendar']}[/]")

    emit(data, human=human)


if __name__ == "__main__":
    app()
