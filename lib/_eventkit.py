"""EventKit reads for the calendar and reminders atoms.

AppleScript reads launch Calendar.app and Reminders.app; EventKit reads the
same store through the system's calendar daemon and leaves both apps closed.
Writes stay on AppleScript in the scripts themselves.

macOS only. EventKit is imported inside the functions, not at module top, so
a script that imports this still starts (and prints --help) anywhere. The
caller's script must list `pyobjc-framework-EventKit` in its dependencies.
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any, Literal, Optional

from _envelope import fail

Kind = Literal["event", "reminder"]

# EKAuthorizationStatus values.
_NOT_DETERMINED = 0
_FULL_ACCESS = 3
_STATUS_TEXT = {0: "not determined", 1: "restricted", 2: "denied", 3: "full access", 4: "add only"}

_PANE = {"event": "Calendars", "reminder": "Reminders"}

_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _entity(kind: Kind) -> int:
    import EventKit

    return EventKit.EKEntityTypeEvent if kind == "event" else EventKit.EKEntityTypeReminder


def _request(store: Any, kind: Kind) -> bool:
    """Ask for full access (the first run on a machine); True when granted.

    Waits 25 s, inside the 30 s today-mod gives a read, so an unanswered prompt
    ends in a failure envelope rather than a killed process; the next run asks again.
    """
    done = threading.Event()
    answer = {"granted": False}

    def completion(granted, _error):
        answer["granted"] = bool(granted)
        done.set()

    name = "requestFullAccessToEventsWithCompletion_" if kind == "event" else "requestFullAccessToRemindersWithCompletion_"
    request = getattr(store, name, None)
    if request is not None:
        request(completion)
    else:  # before macOS 14
        store.requestAccessToEntityType_completion_(_entity(kind), completion)
    done.wait(25)
    return answer["granted"]


def store_for(kind: Kind) -> Any:
    """An EKEventStore with full access to `kind`, else fail with the grant to make."""
    import EventKit

    store = EventKit.EKEventStore.alloc().init()
    status = EventKit.EKEventStore.authorizationStatusForEntityType_(_entity(kind))
    if status == _NOT_DETERMINED:
        status = _FULL_ACCESS if _request(store, kind) else EventKit.EKEventStore.authorizationStatusForEntityType_(_entity(kind))
    if status != _FULL_ACCESS:
        pane = _PANE[kind]
        fail(
            f"no read access to {pane}",
            why=f"EventKit access to {pane} is {_STATUS_TEXT.get(status, status)}; reading needs full access",
            hint=f"System Settings > Privacy & Security > {pane}: set your terminal to Full Access",
            code=2,
        )
    return store


def calendars(store: Any, kind: Kind, name: Optional[str] = None) -> list:
    """The store's calendars (Reminders lists) of `kind`, only those titled `name` when given.

    Titles match ignoring case, as AppleScript's string comparison does.
    """
    found = list(store.calendarsForEntityType_(_entity(kind)) or [])
    return found if name is None else [c for c in found if (c.title() or "").casefold() == name.casefold()]


def nsdate(dt: datetime) -> Any:
    """The NSDate of a naive local datetime."""
    from Foundation import NSDate

    return NSDate.dateWithTimeIntervalSince1970_(dt.timestamp())


def local(date: Any) -> datetime:
    """The naive local datetime of an NSDate."""
    return datetime.fromtimestamp(date.timeIntervalSince1970())


def due_of(reminder: Any) -> Optional[datetime]:
    """A reminder's due moment, local; midnight for a date-only due; None without one.

    The components are read in their own calendar, else the Gregorian one, never
    the system's: under a ROC or Buddhist system calendar the year would shift.
    """
    from Foundation import NSCalendar, NSCalendarIdentifierGregorian

    components = reminder.dueDateComponents()
    if components is None:
        return None
    calendar = components.calendar() or NSCalendar.calendarWithIdentifier_(NSCalendarIdentifierGregorian)
    date = calendar.dateFromComponents_(components)
    return local(date) if date is not None else None


def fetch_reminders(store: Any, predicate: Any) -> list:
    """The reminders `predicate` matches. EventKit answers on another thread."""
    done = threading.Event()
    found: list = []

    def completion(reminders):
        found.extend(reminders or [])
        done.set()

    store.fetchRemindersMatchingPredicate_completion_(predicate, completion)
    if not done.wait(30):
        fail("Reminders did not answer in time", hint="try again in a moment", code=2)
    return found


def apple_date(dt: datetime) -> str:
    """`dt` as AppleScript's `date as string` prints it on an English Mac.

    `Monday, September 28, 2026 at 3:30:00 PM`: the form these atoms always
    returned and callers such as today-mod parse. English names whatever the
    locale, so the form holds on any Mac.
    """
    hour = dt.hour % 12 or 12
    meridiem = "AM" if dt.hour < 12 else "PM"
    return (
        f"{_DAYS[dt.weekday()]}, {_MONTHS[dt.month - 1]} {dt.day}, {dt.year} "
        f"at {hour}:{dt.minute:02d}:{dt.second:02d} {meridiem}"
    )
