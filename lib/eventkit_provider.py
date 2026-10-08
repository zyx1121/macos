"""Calendar and Reminders read/write provider. EventKit is imported lazily."""

from __future__ import annotations

import threading
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from productivity_contract import (
    check_revision,
    checked_schedule,
    digest,
    event_interval,
    fail,
    paginate,
    timestamp,
)


def native_date(dt):
    from Foundation import NSDate

    return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def iso(native, zone=None):
    if native is None:
        return None
    return datetime.fromtimestamp(
        native.timeIntervalSince1970(), zone or timezone.utc
    ).isoformat()


def store_for(kind):
    import EventKit as E

    store = E.EKEventStore.alloc().init()
    entity = E.EKEntityTypeEvent if kind == "calendar" else E.EKEntityTypeReminder
    status = E.EKEventStore.authorizationStatusForEntityType_(entity)
    if status == 0:
        done = threading.Event()
        answer = {}

        def completion(granted, error):
            answer["granted"] = granted
            done.set()

        method = (
            "requestFullAccessToEventsWithCompletion_"
            if kind == "calendar"
            else "requestFullAccessToRemindersWithCompletion_"
        )
        if hasattr(store, method):
            getattr(store, method)(completion)
        else:
            store.requestAccessToEntityType_completion_(entity, completion)
        if not done.wait(25):
            fail(
                "permission_required",
                "Native permission prompt was not answered",
                "Grant full access in System Settings",
                write_not_started=True,
            )
        status = E.EKEventStore.authorizationStatusForEntityType_(entity)
    if status != 3:
        fail(
            "permission_denied",
            f"Full {kind} access is required",
            "System Settings > Privacy & Security: grant the MCP host full access",
            write_not_started=True,
        )
    return store


def entity(kind):
    import EventKit as E

    return E.EKEntityTypeEvent if kind == "calendar" else E.EKEntityTypeReminder


def containers(store, kind):
    return list(store.calendarsForEntityType_(entity(kind)) or [])


def container(store, kind, identifier, writable=False):
    found = next(
        (c for c in containers(store, kind) if c.calendarIdentifier() == identifier),
        None,
    )
    if found is None:
        fail(
            "not_found",
            "Calendar/list ID no longer exists",
            "List containers again",
            write_not_started=True,
        )
    if writable and not found.allowsContentModifications():
        fail("read_only", "Target calendar/list is read-only", write_not_started=True)
    return found


def container_row(c):
    return {
        "id": c.calendarIdentifier(),
        "title": c.title(),
        "account": c.source().title(),
        "writable": bool(c.allowsContentModifications()),
    }


def recurrence_row(item):
    rules = item.recurrenceRules() or []
    if not rules:
        return None
    out = []
    for r in rules:
        end = r.recurrenceEnd()
        out.append(
            {
                "frequency": ["daily", "weekly", "monthly", "yearly"][
                    int(r.frequency())
                ],
                "interval": int(r.interval()),
                "count": int(end.occurrenceCount())
                if end and end.occurrenceCount()
                else None,
                "until": iso(end.endDate()) if end else None,
                "days_of_week": [
                    {"day": int(d.dayOfTheWeek()), "week": int(d.weekNumber())}
                    for d in (r.daysOfTheWeek() or [])
                ],
                "days_of_month": list(r.daysOfTheMonth() or []),
                "months_of_year": list(r.monthsOfTheYear() or []),
                "weeks_of_year": list(r.weeksOfTheYear() or []),
                "days_of_year": list(r.daysOfTheYear() or []),
                "set_positions": list(r.setPositions() or []),
                "first_day_of_week": int(r.firstDayOfTheWeek()),
            }
        )
    return out


def alarm_values(item):
    # Absolute/location alarms are returned separately and are preserved by omission.
    return [
        -float(a.relativeOffset()) / 60
        for a in (item.alarms() or [])
        if a.absoluteDate() is None and a.structuredLocation() is None
    ]


def common(item):
    return {
        "title": item.title() or "",
        "notes": item.notes(),
        "url": str(item.URL().absoluteString()) if item.URL() else None,
        "alarms_minutes_before": alarm_values(item),
        "recurring": bool(item.hasRecurrenceRules()),
        "recurrence": recurrence_row(item),
        "modified_at": iso(item.lastModifiedDate()),
        "other_alarms": [
            {
                "absolute_at": iso(a.absoluteDate()),
                "location_based": a.structuredLocation() is not None,
            }
            for a in (item.alarms() or [])
            if a.absoluteDate() is not None or a.structuredLocation() is not None
        ],
    }


def event_row(e):
    data = common(e)
    from Foundation import NSTimeZone

    zone_name = (
        str(e.timeZone().name())
        if e.timeZone()
        else (str(NSTimeZone.localTimeZone().name()) if e.isAllDay() else "UTC")
    )
    try:
        zone = ZoneInfo(zone_name)
    except Exception:
        zone_name = "UTC"
        zone = timezone.utc

    def schedule(native):
        dt = datetime.fromtimestamp(native.timeIntervalSince1970(), zone)
        return (
            {"kind": "date", "date": dt.date().isoformat()}
            if e.isAllDay()
            else {"kind": "datetime", "at": dt.isoformat(), "time_zone": zone_name}
        )

    if e.isAllDay():
        end_dt = datetime.fromtimestamp(e.endDate().timeIntervalSince1970(), zone)
        end_value = {
            "kind": "date",
            "date": (end_dt.date() + timedelta(days=1)).isoformat(),
        }
    else:
        end_value = schedule(e.endDate())
    data.update(
        {
            "id": e.eventIdentifier(),
            "calendar_id": e.calendar().calendarIdentifier(),
            "start": schedule(e.startDate()),
            "end": end_value,
            "location": e.location(),
            "occurrence_at": iso(e.startDate()),
            "read_only": not bool(e.calendar().allowsContentModifications()),
        }
    )
    data["revision"] = digest(data)
    return data


def reminder_row(r):
    data = common(r)
    c = r.dueDateComponents()
    due = None
    if c:
        from Foundation import (
            NSCalendar,
            NSCalendarIdentifierGregorian,
            NSDateComponentUndefined,
        )

        cal = c.calendar() or NSCalendar.calendarWithIdentifier_(
            NSCalendarIdentifierGregorian
        )
        if c.hour() == NSDateComponentUndefined:
            due = {"kind": "date", "date": f"{c.year():04}-{c.month():02}-{c.day():02}"}
        else:
            zone_name = str(c.timeZone().name()) if c.timeZone() else "UTC"
            native = cal.dateFromComponents_(c)
            due = {
                "kind": "datetime",
                "at": iso(native, ZoneInfo(zone_name)),
                "time_zone": zone_name,
            }
    data.update(
        {
            "id": r.calendarItemIdentifier(),
            "list_id": r.calendar().calendarIdentifier(),
            "due": due,
            "completed": bool(r.isCompleted()),
            "priority": int(r.priority()),
            "completed_at": iso(r.completionDate()),
        }
    )
    data["revision"] = digest(data)
    return data


def fetch_reminders(store, chosen):
    done = threading.Event()
    rows = []

    def completion(result):
        rows.extend(result or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(
        store.predicateForRemindersInCalendars_(chosen), completion
    )
    if not done.wait(30):
        fail("timeout", "Reminders did not answer", "Retry the read")
    return rows


def event_by_id(store, p):
    e = store.eventWithIdentifier_(p["id"])
    if e is None:
        fail(
            "not_found",
            "Event ID no longer exists",
            "Search events again",
            write_not_started=True,
        )
    if p.get("occurrence_at"):
        dt = timestamp(p["occurrence_at"])
        pred = store.predicateForEventsWithStartDate_endDate_calendars_(
            native_date(dt - timedelta(seconds=1)),
            native_date(dt + timedelta(seconds=1)),
            [e.calendar()],
        )
        matches = [
            x
            for x in (store.eventsMatchingPredicate_(pred) or [])
            if x.calendarItemIdentifier() == e.calendarItemIdentifier()
            and abs(x.startDate().timeIntervalSince1970() - dt.timestamp()) < 0.5
        ]
        if len(matches) != 1:
            fail(
                "not_found",
                "Event occurrence no longer exists",
                "List occurrences again",
                write_not_started=True,
            )
        return matches[0]
    if e.hasRecurrenceRules():
        fail(
            "occurrence_required",
            "Recurring events require occurrence_at",
            "Use a timestamp returned by list/search",
            write_not_started=True,
        )
    return e


def write_scope(item, p):
    import EventKit as E

    if item.hasRecurrenceRules() and (not p.get("occurrence_at") or not p.get("scope")):
        fail(
            "scope_required",
            "Recurring event writes require occurrence_at and scope",
            write_not_started=True,
        )
    if p.get("scope") not in (None, "this", "future"):
        fail("invalid_argument", "Unknown recurrence scope", write_not_started=True)
    return E.EKSpanFutureEvents if p.get("scope") == "future" else E.EKSpanThisEvent


def set_recurrence(item, value):
    import EventKit as E

    if value is None:
        item.setRecurrenceRules_(None)
        return
    end = None
    if value.get("count"):
        end = E.EKRecurrenceEnd.recurrenceEndWithOccurrenceCount_(value["count"])
    elif value.get("until"):
        end = E.EKRecurrenceEnd.recurrenceEndWithEndDate_(
            native_date(timestamp(value["until"]))
        )
    frequency = {
        "daily": E.EKRecurrenceFrequencyDaily,
        "weekly": E.EKRecurrenceFrequencyWeekly,
        "monthly": E.EKRecurrenceFrequencyMonthly,
        "yearly": E.EKRecurrenceFrequencyYearly,
    }[value["frequency"]]
    rule = E.EKRecurrenceRule.alloc().initRecurrenceWithFrequency_interval_end_(
        frequency, value.get("interval", 1), end
    )
    item.setRecurrenceRules_([rule])


def patch_common(item, p):
    import EventKit as E
    from Foundation import NSURL

    if "title" in p:
        item.setTitle_(p["title"])
    if "notes" in p:
        item.setNotes_(p["notes"])
    if "url" in p:
        item.setURL_(NSURL.URLWithString_(p["url"]) if p["url"] else None)
    if "alarms_minutes_before" in p:
        item.setAlarms_(
            [
                E.EKAlarm.alarmWithRelativeOffset_(-n * 60)
                for n in p["alarms_minutes_before"]
            ]
        )
    if "recurrence" in p:
        set_recurrence(item, p["recurrence"])


def apply_event(e, p):
    from Foundation import NSTimeZone

    old = event_row(e) if e.startDate() and e.endDate() else {}
    start = p.get("start", old.get("start"))
    end = p.get("end", old.get("end"))
    event_interval(start, end)
    e.setAllDay_(False)
    if start["kind"] == "date":
        # All-day events follow the local native calendar, not UTC dates.
        zone = NSTimeZone.localTimeZone()
        name = str(zone.name())
        first = datetime.combine(
            date.fromisoformat(start["date"]), datetime.min.time(), ZoneInfo(name)
        )
        last = datetime.combine(
            date.fromisoformat(end["date"]), datetime.min.time(), ZoneInfo(name)
        )
        e.setTimeZone_(zone)
    else:
        first = timestamp(start["at"])
        last = timestamp(end["at"])
        e.setAllDay_(False)
        e.setTimeZone_(NSTimeZone.timeZoneWithName_(start["time_zone"]))
    e.setStartDate_(native_date(first))
    e.setEndDate_(native_date(last))
    e.setAllDay_(start["kind"] == "date")
    if "location" in p:
        e.setLocation_(p["location"])
    patch_common(e, p)


def apply_reminder(r, p):
    from Foundation import (
        NSCalendar,
        NSCalendarIdentifierGregorian,
        NSDateComponents,
        NSTimeZone,
    )

    old = reminder_row(r)
    due = p.get("due", old["due"])
    if due:
        checked_schedule(due)
    alarms = p.get("alarms_minutes_before", old["alarms_minutes_before"])
    if alarms and (not due or due["kind"] == "date"):
        fail(
            "invalid_argument",
            "Relative reminder alarms require a timed due",
            "Use due.kind=datetime or clear alarms",
            write_not_started=True,
        )
    if (
        p.get("recurrence") or (old["recurring"] and "recurrence" not in p)
    ) and not due:
        fail(
            "invalid_argument",
            "Recurring reminders require a due date",
            write_not_started=True,
        )
    if "due" in p:
        c = None
        if due:
            c = NSDateComponents.alloc().init()
            cal = NSCalendar.calendarWithIdentifier_(NSCalendarIdentifierGregorian)
            if due["kind"] == "date":
                dt = date.fromisoformat(due["date"])
            else:
                dt = timestamp(due["at"])
                tz = NSTimeZone.timeZoneWithName_(due["time_zone"])
                c.setTimeZone_(tz)
                cal.setTimeZone_(tz)
                c.setHour_(dt.hour)
                c.setMinute_(dt.minute)
                c.setSecond_(dt.second)
            c.setCalendar_(cal)
            c.setYear_(dt.year)
            c.setMonth_(dt.month)
            c.setDay_(dt.day)
        r.setDueDateComponents_(c)
    if "priority" in p:
        r.setPriority_(p["priority"])
    if "completed" in p:
        r.setCompleted_(p["completed"])
    patch_common(r, p)


def save(store, item, kind, span=None, remove=False):
    if kind == "calendar":
        result = (
            store.removeEvent_span_commit_error_(item, span, True, None)
            if remove
            else store.saveEvent_span_commit_error_(item, span, True, None)
        )
    else:
        result = (
            store.removeReminder_commit_error_(item, True, None)
            if remove
            else store.saveReminder_commit_error_(item, True, None)
        )
    ok, error = result
    if not ok:
        fail(
            "native_write_failed",
            "Native store rejected the write",
            str(error),
            write_not_started=True,
        )


def _perform(operation, p):
    import EventKit as E

    kind = "calendar" if operation.startswith("calendar_") else "reminders"
    store = store_for(kind)
    if operation in {"calendar_list_calendars", "reminders_list_lists"}:
        return sorted(
            [container_row(c) for c in containers(store, kind)],
            key=lambda r: (r["account"], r["title"], r["id"]),
        )
    if operation in {"calendar_list_events", "calendar_search_events"}:
        start = timestamp(p["from"])
        end = timestamp(p["to"])
        if end <= start or end - start > timedelta(days=366):
            fail(
                "invalid_argument",
                "Event query range must be positive and no longer than 366 days",
            )
        chosen = (
            [container(store, kind, p["calendar_id"])] if p.get("calendar_id") else None
        )
        pred = store.predicateForEventsWithStartDate_endDate_calendars_(
            native_date(start), native_date(end), chosen
        )
        rows = [
            event_row(e)
            for e in (store.eventsMatchingPredicate_(pred) or [])
            if e.startDate().timeIntervalSince1970() < end.timestamp()
            and e.endDate().timeIntervalSince1970() > start.timestamp()
        ]
        needle = p.get("query", "").casefold()
        rows = [
            r
            for r in rows
            if needle in (r["title"] + "\n" + (r["notes"] or "")).casefold()
        ]
        rows.sort(key=lambda r: (r["occurrence_at"], r["id"]))
        return paginate(rows, p)
    if operation in {"reminders_list", "reminders_search"}:
        chosen = (
            [container(store, kind, p["list_id"])]
            if p.get("list_id")
            else containers(store, kind)
        )
        rows = [reminder_row(r) for r in fetch_reminders(store, chosen)]
        if "completed" in p:
            rows = [r for r in rows if r["completed"] == p["completed"]]
        for field, greater in [("due_from", True), ("due_to", False)]:
            if field in p:
                boundary = date.fromisoformat(p[field])
                rows = [
                    r
                    for r in rows
                    if r["due"]
                    and (
                        (
                            date.fromisoformat(
                                r["due"].get("date", r["due"].get("at", "")[:10])
                            )
                            >= boundary
                        )
                        if greater
                        else (
                            date.fromisoformat(
                                r["due"].get("date", r["due"].get("at", "")[:10])
                            )
                            <= boundary
                        )
                    )
                ]
        if p.get("due_from") and p.get("due_to") and p["due_from"] > p["due_to"]:
            fail("invalid_argument", "due_from must not exceed due_to")
        needle = p.get("query", "").casefold()
        rows = [
            r
            for r in rows
            if needle in (r["title"] + "\n" + (r["notes"] or "")).casefold()
        ]
        rows.sort(
            key=lambda r: (
                (r["due"] or {}).get("date", (r["due"] or {}).get("at", "9999")),
                r["id"],
            )
        )
        return paginate(rows, p)
    create = operation in {"calendar_create_event", "reminders_create"}
    if create:
        c = container(
            store, kind, p["calendar_id" if kind == "calendar" else "list_id"], True
        )
        item = (
            E.EKEvent.eventWithEventStore_(store)
            if kind == "calendar"
            else E.EKReminder.reminderWithEventStore_(store)
        )
        item.setCalendar_(c)
    else:
        item = (
            event_by_id(store, p)
            if kind == "calendar"
            else store.calendarItemWithIdentifier_(p["id"])
        )
        if item is None or (kind == "reminders" and not isinstance(item, E.EKReminder)):
            fail(
                "not_found",
                "Item ID no longer exists",
                "Search again",
                write_not_started=True,
            )
    row = event_row if kind == "calendar" else reminder_row
    if operation in {"calendar_get_event", "reminders_get"}:
        return row(item)
    if not create:
        if not p.get("confirm"):
            fail(
                "confirmation_required",
                "Writing existing items requires confirm=true",
                write_not_started=True,
            )
        current = row(item)
        if operation == "reminders_complete" and current["completed"]:
            return current
        check_revision(current, p["expected_revision"])
        if not item.calendar().allowsContentModifications():
            fail(
                "read_only",
                "Item belongs to a read-only container",
                write_not_started=True,
            )
    if (
        not create
        and kind == "calendar"
        and item.hasRecurrenceRules()
        and "recurrence" in p
        and p.get("scope") != "future"
    ):
        fail(
            "invalid_argument",
            "Changing a recurring rule requires scope=future",
            write_not_started=True,
        )
    span = (
        E.EKSpanThisEvent
        if create
        else (write_scope(item, p) if kind == "calendar" else None)
    )
    if operation in {"calendar_delete_event", "reminders_delete"}:
        identifier = p["id"]
        save(store, item, kind, span, True)
        return {"id": identifier, "deleted": True}
    if not create and not any(
        k not in {"id", "expected_revision", "confirm", "scope", "occurrence_at"}
        for k in p
    ):
        if operation != "reminders_complete":
            fail(
                "invalid_argument",
                "Update requires at least one changed field",
                write_not_started=True,
            )
    container_key = "calendar_id" if kind == "calendar" else "list_id"
    if not create and container_key in p:
        item.setCalendar_(container(store, kind, p[container_key], True))
    if operation == "reminders_complete":
        p = {**p, "completed": True}
    if kind == "calendar":
        apply_event(item, p)
    else:
        apply_reminder(item, p)
    save(store, item, kind, span)
    return row(item)


def perform(operation, payload):
    try:
        return _perform(operation, payload)
    except Exception as error:
        from productivity_contract import ContractError

        if isinstance(error, ContractError) and error.error["code"] in {
            "invalid_argument",
            "not_found",
            "read_only",
            "conflict",
            "scope_required",
            "occurrence_required",
        }:
            error.error["write_not_started"] = True
        raise
