#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich", "pyobjc-framework-EventKit; sys_platform == 'darwin'"]
# ///
"""Atomic Reminders operations: reads via EventKit, writes via AppleScript.

show-lists / list read through EventKit, so Reminders.app stays closed.
add / done / delete drive Reminders.app over AppleScript. Dates are built
locale-independently (set year/month/day individually rather than parsing
strings).
"""
from __future__ import annotations

# Siblings shadow stdlib — drop our dir off sys.path so typer/rich resolve normally.
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
    help="Atomic Reminders.app ops — list / add / done / delete / show-lists.",
)
console = Console()


def run_as(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not authorized" in stderr or "-1743" in stderr:
            fail(
                "macOS denied Automation access to Reminders",
                why=stderr,
                hint="System Settings > Privacy & Security > Automation: allow this terminal to control Reminders",
                code=2,
            )
        fail(
            stderr or "AppleScript failed",
            hint="run `reminders show-lists` to confirm the list name exists",
            code=2,
        )
    return result.stdout.rstrip("\n")


def escape_as(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def list_clause(list_name: Optional[str]) -> str:
    return f'list "{escape_as(list_name)}"' if list_name else "default list"


def parse_when(when: str) -> datetime:
    """Accept ISO date/datetime, HH:MM (today), 'today', 'tomorrow', 'next week'."""
    s = when.strip().lower()
    now = datetime.now().replace(second=0, microsecond=0)
    if s == "today":
        return now.replace(hour=23, minute=59)
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
        f"can't parse date '{when}'",
        hint="try YYYY-MM-DD, YYYY-MM-DDTHH:MM, 'today', or 'tomorrow'",
        code=2,
    )


def as_date_block(dt: datetime, var: str = "theDate") -> str:
    """Build AppleScript fragment that constructs `var` as a date object."""
    return (
        f'set {var} to current date\n'
        f'set year of {var} to {dt.year}\n'
        f'set month of {var} to {dt.month}\n'
        f'set day of {var} to {dt.day}\n'
        f'set hours of {var} to {dt.hour}\n'
        f'set minutes of {var} to {dt.minute}\n'
        f'set seconds of {var} to 0'
    )


# ── show-lists ───────────────────────────────────────────────────
@app.command(name="show-lists", help="List all Reminders lists (Inbox, custom lists, etc.).")
def show_lists():
    from _eventkit import calendars, store_for

    data = [{"name": c.title()} for c in calendars(store_for("reminder"), "reminder")]

    def human(rows, _meta):
        table = Table(title="Reminders lists", show_header=True)
        table.add_column("name", style="bold")
        for r in rows:
            table.add_row(r["name"])
        console.print(table)

    emit(data, {"count": len(data)}, human=human)


# ── list ─────────────────────────────────────────────────────────
@app.command(name="list", help="List reminders in a list (default: the user's default list).")
def list_cmd(
    list_name: Optional[str] = typer.Option(None, "--list", "-l", help='Reminder list name (default: the default list).'),
    show_done: bool = typer.Option(False, "--show-done", help="Include completed reminders."),
    limit: Optional[int] = typer.Option(None, "--limit", "-n", help="Max reminders to show."),
):
    from _eventkit import apple_date, calendars, due_of, fetch_reminders, store_for

    store = store_for("reminder")
    if list_name:
        lists = calendars(store, "reminder", list_name)
        if not lists:
            fail(f"no Reminders list named '{list_name}'", hint="run `reminders show-lists` to see the list names", code=2)
    else:
        default = store.defaultCalendarForNewReminders()
        if default is None:
            fail("Reminders has no default list", hint="pass --list; run `reminders show-lists` to see the list names", code=2)
        lists = [default]
    if show_done:
        predicate = store.predicateForRemindersInCalendars_(lists)
    else:
        predicate = store.predicateForIncompleteRemindersWithDueDateStarting_ending_calendars_(None, None, lists)
    # EventKit has no list order to give; due ones first, soonest first.
    rows = sorted(
        ((due_of(r), r) for r in fetch_reminders(store, predicate)),
        key=lambda row: (row[0] is None, row[0] or datetime.max, row[1].title() or ""),
    )
    if limit:
        rows = rows[:limit]
    data = [
        {"name": r.title() or "", "due": apple_date(due) if due else "", "done": bool(r.isCompleted())}
        for due, r in rows
    ]

    def human(rows, _meta):
        if not rows:
            console.print("[dim](no reminders)[/]")
            return
        table = Table(title=f"Reminders ({list_name or 'default list'})", show_header=True)
        table.add_column("#", justify="right", style="cyan")
        table.add_column("name", style="bold")
        table.add_column("due", style="dim")
        table.add_column("done", style="green")
        for i, r in enumerate(rows, start=1):
            mark = "✓" if r["done"] else ""
            table.add_row(str(i), r["name"], r["due"] or "—", mark)
        console.print(table)

    emit(data, {"count": len(data), "list": list_name or "default list", "show_done": show_done}, human=human)


# ── add ──────────────────────────────────────────────────────────
@app.command(help="Add a new reminder.")
def add(
    name: str = typer.Argument(..., help="Reminder text."),
    due: Optional[str] = typer.Option(None, "--due", "-d", help="Due time (YYYY-MM-DD, YYYY-MM-DDTHH:MM, 'today', 'tomorrow', 'next week')."),
    list_name: Optional[str] = typer.Option(None, "--list", "-l", help="Target reminder list (default: the default list)."),
    notes: Optional[str] = typer.Option(None, "--notes", "-N", help="Body / notes."),
):
    props = [f'name:"{escape_as(name)}"']
    if notes:
        props.append(f'body:"{escape_as(notes)}"')

    if due:
        dt = parse_when(due)
        date_block = as_date_block(dt)
        props.append("due date:theDate")
        props_str = ", ".join(props)
        script = f'''
tell application "Reminders"
    {date_block}
    set newR to make new reminder at {list_clause(list_name)} with properties {{{props_str}}}
    return name of newR
end tell
'''
    else:
        props_str = ", ".join(props)
        script = f'''
tell application "Reminders"
    set newR to make new reminder at {list_clause(list_name)} with properties {{{props_str}}}
    return name of newR
end tell
'''
    name_out = run_as(script)
    due_str = dt.strftime("%Y-%m-%d %H:%M") if due else None
    data = {"action": "add", "name": name_out, "due": due_str, "list": list_name}

    def human(d, _meta):
        msg = f"added: [bold]{d['name']}[/]"
        if d["due"]:
            msg += f" (due {d['due']})"
        if d["list"]:
            msg += f" → {d['list']}"
        console.print(msg)

    emit(data, human=human)


# ── done ─────────────────────────────────────────────────────────
@app.command(help="Mark the first reminder matching <name> as completed.")
def done(
    name: str = typer.Argument(..., help="Exact reminder name (first match wins)."),
    list_name: Optional[str] = typer.Option(None, "--list", "-l", help="Search in this list (default: the default list)."),
):
    script = f'''
tell application "Reminders"
    set target to first reminder of {list_clause(list_name)} whose name is "{escape_as(name)}"
    set completed of target to true
    return name of target
end tell
'''
    name_out = run_as(script)
    data = {"action": "done", "name": name_out, "list": list_name}
    emit(data, human=lambda d, _m: console.print(f"done: [bold]{d['name']}[/] ✓"))


# ── delete ───────────────────────────────────────────────────────
@app.command(help="Delete the first reminder matching <name>.")
def delete(
    name: str = typer.Argument(..., help="Exact reminder name (first match wins)."),
    list_name: Optional[str] = typer.Option(None, "--list", "-l", help="Search in this list (default: the default list)."),
):
    script = f'''
tell application "Reminders"
    set target to first reminder of {list_clause(list_name)} whose name is "{escape_as(name)}"
    delete target
    return "{escape_as(name)}"
end tell
'''
    name_out = run_as(script)
    data = {"action": "delete", "name": name_out, "list": list_name}
    emit(data, human=lambda d, _m: console.print(f"deleted: [bold]{d['name']}[/]"))


if __name__ == "__main__":
    app()
