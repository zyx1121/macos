"""Pure interval arithmetic with explicit native-calendar coverage and policies."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from productivity_contract import fail, timestamp


def range_bounds(p):
    start, end = timestamp(p["from"]), timestamp(p["to"])
    if end <= start or end - start > timedelta(days=366):
        fail("invalid_argument", "Range must be positive and no longer than 366 days")
    try:
        zone = ZoneInfo(p["time_zone"])
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        fail("invalid_argument", "Unknown IANA time zone")
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc), zone


def bounds(row, zone):
    if row["start"]["kind"] == "date":
        return tuple(
            datetime.combine(
                datetime.fromisoformat(row[k]["date"]).date(), time.min, zone
            ).astimezone(timezone.utc)
            for k in ("start", "end")
        )
    return timestamp(row["start"]["at"]).astimezone(timezone.utc), timestamp(
        row["end"]["at"]
    ).astimezone(timezone.utc)


def occupied(rows, p, zone):
    out = []
    excluded = set(p.get("exclude_event_ids", []))
    for r in rows:
        if r["id"] in excluded:
            continue
        if not p.get("include_all_day", True) and r["start"]["kind"] == "date":
            continue
        if not p.get("include_free_events", False) and r.get("availability") == "free":
            continue
        if r.get("status") == "canceled":
            continue
        a, b = bounds(r, zone)
        out.append((a, b, r))
    return sorted(out, key=lambda x: (x[0], x[1], x[2]["id"]))


def calculate(rows, p, coverage, conflicts=False):
    first, last, zone = range_bounds(p)
    busy = occupied(rows, p, zone)
    policy = {
        "time_zone": p["time_zone"],
        "include_all_day": p.get("include_all_day", True),
        "include_free_events": p.get("include_free_events", False),
        "exclude_event_ids": p.get("exclude_event_ids", []),
    }
    common = {
        "from": p["from"],
        "to": p["to"],
        "calendar_ids": coverage,
        "policy": policy,
        "coverage": "local_synced_events_only",
    }
    if conflicts:
        hits = [r for a, b, r in busy if a < last and b > first]
        return {**common, "conflicts": hits, "has_conflicts": bool(hits)}
    minutes = p.get("duration_minutes", 60)
    if not isinstance(minutes, int) or not 1 <= minutes <= 10080:
        fail("invalid_argument", "duration_minutes must be 1..10080")
    windows = []
    working = p.get("working_hours")
    if working:
        try:
            begin = time.fromisoformat(working["start"])
            end = time.fromisoformat(working["end"])
            if begin.tzinfo or end.tzinfo or end <= begin:
                raise ValueError()
            days = working["weekdays"]
            if not days or any(d not in range(1, 8) for d in days):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            fail(
                "invalid_argument",
                "Working hours require same-day HH:MM bounds and ISO weekdays 1..7",
            )
        day = first.astimezone(zone).date()
        while day <= last.astimezone(zone).date():
            if day.isoweekday() in days:

                def local(t):
                    v = datetime.combine(day, t, zone)
                    if v.astimezone(timezone.utc).astimezone(zone).replace(
                        tzinfo=None
                    ) != v.replace(tzinfo=None):
                        fail(
                            "invalid_argument",
                            "Working-hour boundary falls in a DST gap",
                        )
                    return v.astimezone(timezone.utc)

                a, b = max(first, local(begin)), min(last, local(end))
                if a < b:
                    windows.append((a, b))
            day += timedelta(days=1)
    else:
        windows = [(first, last)]
    gaps = []
    for a, b in windows:
        cursor = a
        for x, y, _ in busy:
            if y <= cursor or x >= b:
                continue
            if x > cursor:
                gaps.append((cursor, min(x, b)))
            cursor = max(cursor, y)
            if cursor >= b:
                break
        if cursor < b:
            gaps.append((cursor, b))
    slots = [
        {
            "start": a.astimezone(zone).isoformat(),
            "end": b.astimezone(zone).isoformat(),
            "duration_minutes": (b - a).total_seconds() / 60,
        }
        for a, b in gaps
        if b - a >= timedelta(minutes=minutes)
    ]
    limit = p.get("limit", 30)
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        fail("invalid_argument", "limit must be 1..100")
    return {
        **common,
        "slots": slots[:limit],
        "has_more": len(slots) > limit,
        "minimum_duration_minutes": minutes,
    }
