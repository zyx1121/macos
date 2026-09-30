#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["typer", "rich"]
# ///
"""Atomic Safari.app operations via AppleScript.

url / title / text / tabs / open / close / selection / js. The first six work
out of the box. `selection` and `js` need a one-time Safari setting:

    Safari → Settings → Advanced → "Show Develop menu in menu bar"
    Develop → "Allow JavaScript from Apple Events"
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

import typer
from rich.console import Console
from rich.table import Table

from _envelope import emit, fail  # noqa: E402

app = typer.Typer(
    rich_markup_mode=None,
    no_args_is_help=True,
    add_completion=False,
    help="Atomic Safari.app ops — url / title / text / tabs / open / close / selection / js.",
)
console = Console()


JS_HINT = (
    'Enable JS evaluation: Safari → Settings → Advanced → '
    '"Show Develop menu in menu bar" → Develop → '
    '"Allow JavaScript from Apple Events".'
)


def normalize_quotes(text: str) -> str:
    """AppleScript errors use typographic apostrophes ("Can't get window 1"),
    so plain-ASCII substring probes never match without this."""
    return text.replace("’", "'").replace("‘", "'")


def run_as(script: str, *, want_stdout: bool = True) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        probe = normalize_quotes(stderr)
        if "Allow JavaScript from Apple Events" in probe:
            fail("JavaScript-from-Apple-Events is disabled", why=stderr, hint=JS_HINT, code=2)
        if "Can't get window" in probe or "Invalid index" in probe:
            fail(
                "Safari has no open window",
                why=stderr,
                hint="open a Safari window first, or call safari_open_url to create one",
                code=2,
            )
        if "Can't get current tab" in probe or "Can't get tab" in probe:
            fail("no active tab", why=stderr, hint="open a page in Safari first", code=2)
        if "not authorized" in probe or "-1743" in probe:
            fail(
                "macOS denied Automation access to Safari",
                why=stderr,
                hint="System Settings > Privacy & Security > Automation: allow this terminal to control Safari",
                code=2,
            )
        fail(
            stderr or "AppleScript failed",
            hint="check that Safari is running and this terminal has Automation access to it",
            code=2,
        )
    return result.stdout.rstrip("\n") if want_stdout else ""


def escape_as(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ── url ──────────────────────────────────────────────────────────
@app.command(help="Print the URL of the front tab.")
def url():
    out = run_as('tell application "Safari" to return URL of current tab of front window')
    emit({"url": out}, human=lambda d, _m: print(d["url"]))


# ── title ────────────────────────────────────────────────────────
@app.command(help="Print the title (name) of the front tab.")
def title():
    out = run_as('tell application "Safari" to return name of current tab of front window')
    emit({"title": out}, human=lambda d, _m: print(d["title"]))


# ── text ─────────────────────────────────────────────────────────
@app.command(help="Print the visible text of the front tab (no JS required).")
def text():
    out = run_as('tell application "Safari" to return text of current tab of front window')
    emit({"text": out}, human=lambda d, _m: print(d["text"]))


# ── tabs ─────────────────────────────────────────────────────────
@app.command(help="List all tabs across all windows.")
def tabs():
    script = '''
tell application "Safari"
    set output to ""
    repeat with w from 1 to count of windows
        repeat with t from 1 to count of tabs of window w
            set theTab to tab t of window w
            set output to output & w & "/" & t & "\t" & (name of theTab) & "\t" & (URL of theTab) & "<<<EOL>>>"
        end repeat
    end repeat
    return output
end tell
'''
    raw = run_as(script)
    rows = [l for l in raw.split("<<<EOL>>>") if l.strip()]
    data = []
    for line in rows:
        parts = line.split("\t")
        if len(parts) >= 3:
            data.append({"wt": parts[0], "title": parts[1], "url": parts[2]})

    def human(tabs, _meta):
        if not tabs:
            console.print("[dim](no tabs open)[/]")
            return
        table = Table(title="Safari tabs", show_header=True)
        table.add_column("w/t", style="cyan")
        table.add_column("title", style="bold")
        table.add_column("URL", style="dim")
        for t in tabs:
            table.add_row(t["wt"], t["title"], t["url"])
        console.print(table)

    emit(data, {"count": len(data)}, human=human)


# ── open ─────────────────────────────────────────────────────────
@app.command(name="open", help="Open <url> in a new tab. Does NOT block on page load — pair with a sleep if you need content immediately.")
def open_cmd(target: str = typer.Argument(..., metavar="URL", help="URL to open.")):
    safe = escape_as(target)
    run_as(
        f'tell application "Safari" to make new document with properties {{URL:"{safe}"}}',
        want_stdout=False,
    )
    emit(
        {"action": "open", "url": target},
        human=lambda d, _m: print(f"opened: {d['url']}"),
    )


# ── close ────────────────────────────────────────────────────────
@app.command(help="Close the front tab (reports the URL that just closed).")
def close():
    script = '''
tell application "Safari"
    set u to URL of current tab of front window
    close current tab of front window
    return u
end tell
'''
    out = run_as(script)
    emit(
        {"action": "close", "url": out or None},
        human=lambda d, _m: print(f"closed: {d['url']}" if d["url"] else "closed"),
    )


# ── selection ────────────────────────────────────────────────────
@app.command(help='Print the user\'s current text selection on the front tab. Needs "Allow JavaScript from Apple Events".')
def selection():
    js_expr = "window.getSelection().toString()"
    out = run_as(
        f'tell application "Safari" to do JavaScript "{escape_as(js_expr)}" in current tab of front window'
    )

    def human(d, _m):
        if not d["selection"]:
            console.print("[dim](no selection)[/]")
            return
        print(d["selection"])

    emit({"selection": out or None}, human=human)


# ── js ───────────────────────────────────────────────────────────
@app.command(help='Evaluate a JavaScript expression in the front tab and print the result. Needs "Allow JavaScript from Apple Events".')
def js(expression: str = typer.Argument(..., help="JS expression to evaluate.")):
    safe = escape_as(expression)
    out = run_as(
        f'tell application "Safari" to return (do JavaScript "{safe}" in current tab of front window) as string'
    )
    emit({"result": out}, human=lambda d, _m: print(d["result"]))


if __name__ == "__main__":
    app()
