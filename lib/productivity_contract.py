"""Portable contracts shared by native providers and offline tests."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ContractError(Exception):
    def __init__(self, code, message, hint=None, **details):
        super().__init__(message)
        self.error = {"code": code, "message": message, "hint": hint, **details}


def fail(code, message, hint=None, **details):
    raise ContractError(code, message, hint, **details)


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def timestamp(value):
    if not isinstance(value, str):
        fail("invalid_argument", "Timestamp must be an ISO string with an offset")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("invalid_argument", "Invalid ISO timestamp")
    if dt.tzinfo is None:
        fail("invalid_argument", "Timestamp requires a UTC offset")
    return dt


def checked_schedule(value):
    if not isinstance(value, dict):
        fail("invalid_argument", "Schedule must be an object")
    if value.get("kind") == "date":
        try:
            date.fromisoformat(value["date"])
        except (KeyError, ValueError):
            fail("invalid_argument", "Invalid date-only schedule")
        return value
    if value.get("kind") != "datetime":
        fail("invalid_argument", "Schedule kind must be date or datetime")
    dt = timestamp(value.get("at"))
    try:
        zone = ZoneInfo(value.get("time_zone", ""))
    except (ZoneInfoNotFoundError, ValueError):
        fail("invalid_argument", "Unknown IANA time zone")
    converted = dt.astimezone(zone)
    if dt.utcoffset() != converted.utcoffset():
        fail(
            "invalid_argument",
            "Timestamp offset does not agree with time_zone",
            "Use the offset valid at this date in the specified zone",
        )
    return value


def event_interval(start, end):
    checked_schedule(start)
    checked_schedule(end)
    if start["kind"] != end["kind"]:
        fail(
            "invalid_argument",
            "Event start and end must both be date-only or both timed",
        )
    if start["kind"] == "date":
        first, last = date.fromisoformat(start["date"]), date.fromisoformat(end["date"])
    else:
        if start["time_zone"] != end["time_zone"]:
            fail("invalid_argument", "Event start and end must use the same time zone")
        first, last = timestamp(start["at"]), timestamp(end["at"])
    if last <= first:
        fail(
            "invalid_argument",
            "Event end must be after start; date-only end is exclusive",
        )


def check_revision(item, expected, already_done=False):
    if already_done:
        return
    if expected != item["revision"]:
        fail(
            "conflict",
            "Item changed since it was read",
            "Read the item again and review the new contents before retrying",
            current_revision=item["revision"],
        )


def content_html(payload):
    if "body_text" in payload and "body_html" in payload:
        fail("invalid_argument", "Choose body_text or body_html, not both")
    if "body_html" in payload:
        return payload["body_html"]
    return (
        "<div>"
        + html.escape(payload.get("body_text", "")).replace("\n", "<br>")
        + "</div>"
    )


def paginate(items, payload):
    limit = payload.get("limit", 30)
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        fail("invalid_argument", "limit must be between 1 and 100")
    query = digest({k: v for k, v in payload.items() if k not in {"cursor", "limit"}})
    snapshot = digest(items)
    offset = 0
    if payload.get("cursor"):
        try:
            c = json.loads(base64.urlsafe_b64decode(payload["cursor"]))
            if c["query"] != query or c["snapshot"] != snapshot:
                fail(
                    "stale_cursor", "Query or results changed", "Restart without cursor"
                )
            offset = c["offset"]
            if not isinstance(offset, int) or not 0 <= offset <= len(items):
                raise ValueError()
        except ContractError:
            raise
        except Exception:
            fail("invalid_argument", "Invalid pagination cursor")
    next_offset = offset + limit
    cursor = (
        None
        if next_offset >= len(items)
        else base64.urlsafe_b64encode(
            json.dumps(
                {"offset": next_offset, "query": query, "snapshot": snapshot}
            ).encode()
        ).decode()
    )
    return {"items": items[offset:next_offset], "next_cursor": cursor}


def create_once(operation, payload, create, path=None):
    """A durable claim precedes native creation. Unknown outcomes are never retried blindly."""
    key = payload.get("request_key")
    if not isinstance(key, str) or not key or len(key) > 200:
        fail("invalid_argument", "Create requires a request_key")
    path = (
        path
        or Path(
            os.environ.get(
                "MACOS_MCP_STATE_DIR", "~/Library/Application Support/zyx1121/macos"
            )
        ).expanduser()
        / "requests.sqlite3"
    )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS requests (key TEXT PRIMARY KEY, operation TEXT NOT NULL, fingerprint TEXT NOT NULL, result TEXT)"
        )
        os.chmod(path, 0o600)
        fingerprint = digest(payload)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT operation,fingerprint,result FROM requests WHERE key=?", (key,)
        ).fetchone()
        if row:
            db.rollback()
            if row[:2] != (operation, fingerprint):
                fail(
                    "request_key_conflict",
                    "request_key was already used for a different request",
                )
            if row[2] is None:
                fail(
                    "outcome_unknown",
                    "Previous creation has an unknown or pending outcome",
                    "Search the native app before issuing a new request key; do not blindly retry",
                )
            return json.loads(row[2])
        db.execute(
            "INSERT INTO requests VALUES (?,?,?,NULL)", (key, operation, fingerprint)
        )
        db.commit()
        try:
            result = create()
        except ContractError as e:
            # Providers mark failures known to happen before any native write.
            if e.error.get("write_not_started"):
                db.execute("DELETE FROM requests WHERE key=?", (key,))
                db.commit()
            raise
        db.execute(
            "UPDATE requests SET result=? WHERE key=?",
            (json.dumps(result, ensure_ascii=False), key),
        )
        db.commit()
        return result
    finally:
        db.close()


def validate_recurrence(value):
    if value is None:
        return
    frequencies = {"daily", "weekly", "monthly", "yearly"}
    frequency = value.get("frequency")
    if frequency not in frequencies:
        fail("invalid_argument", "Unknown recurrence frequency")
    if value.get("count") and value.get("until"):
        fail("invalid_argument", "Choose count or until")
    if not 1 <= value.get("interval", 1) <= 100:
        fail("invalid_argument", "Invalid recurrence interval")
    if "count" in value and not 1 <= value["count"] <= 10000:
        fail("invalid_argument", "Invalid recurrence count")
    if value.get("until"):
        timestamp(value["until"])
    allowed = {
        "days_of_week": {"weekly", "monthly", "yearly"},
        "days_of_month": {"monthly", "yearly"},
        "months_of_year": {"yearly"},
        "weeks_of_year": {"yearly"},
        "days_of_year": {"yearly"},
        "set_positions": {"monthly", "yearly"},
    }
    for key, frequencies in allowed.items():
        if key in value and (not value[key] or frequency not in frequencies):
            fail("invalid_argument", f"{key} is not valid for {frequency}")
    for key, bound in [
        ("days_of_month", 31),
        ("months_of_year", 12),
        ("weeks_of_year", 53),
        ("days_of_year", 366),
        ("set_positions", 366),
    ]:
        if key in value and (
            len(value[key]) != len(set(value[key]))
            or any(
                not isinstance(n, int)
                or n == 0
                or abs(n) > bound
                or (key == "months_of_year" and n < 0)
                for n in value[key]
            )
        ):
            fail("invalid_argument", f"Invalid {key}")
    weekdays = value.get("days_of_week", [])
    if len({(d.get("day"), d.get("week", 0)) for d in weekdays}) != len(weekdays):
        fail("invalid_argument", "Duplicate weekdays")
    for d in weekdays:
        if d.get("day") not in range(1, 8) or d.get("week", 0) not in range(-53, 54):
            fail("invalid_argument", "Invalid weekday selector")
        if frequency == "monthly" and abs(d.get("week", 0)) > 5:
            fail("invalid_argument", "Monthly weekday ordinals must be -5..5")
        if (
            frequency == "yearly"
            and value.get("months_of_year")
            and abs(d.get("week", 0)) > 5
        ):
            fail(
                "invalid_argument",
                "Yearly month-specific weekday ordinals must be -5..5",
            )
        if frequency == "weekly" and d.get("week", 0) != 0:
            fail("invalid_argument", "Weekly weekdays cannot have ordinal weeks")
        if (
            frequency == "yearly"
            and value.get("weeks_of_year")
            and d.get("week", 0) != 0
        ):
            fail(
                "invalid_argument",
                "Yearly week selectors cannot combine ordinal weekdays",
            )
    if value.get("set_positions") and not any(
        value.get(k)
        for k in ("days_of_week", "days_of_month", "weeks_of_year", "days_of_year")
    ):
        fail("invalid_argument", "set_positions requires a day/week selector")
    if value.get("days_of_year") and any(
        value.get(k) for k in ("days_of_month", "weeks_of_year", "months_of_year")
    ):
        fail(
            "invalid_argument", "Year-day selectors cannot combine month/week selectors"
        )
