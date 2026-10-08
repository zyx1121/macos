#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Offline behavior tests: dates, conflicts, pagination and durable create claims."""

import concurrent.futures
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from productivity_contract import (
    ContractError,
    check_revision,
    checked_schedule,
    content_html,
    create_once,
    event_interval,
    paginate,
)


class Contracts(unittest.TestCase):
    def test_timezone_and_dst(self):
        checked_schedule(
            {
                "kind": "datetime",
                "at": "2026-10-18T23:00:00+08:00",
                "time_zone": "Asia/Taipei",
            }
        )
        with self.assertRaises(ContractError):
            checked_schedule(
                {
                    "kind": "datetime",
                    "at": "2026-10-18T23:00:00+00:00",
                    "time_zone": "Asia/Taipei",
                }
            )
        with self.assertRaises(ContractError):
            checked_schedule(
                {
                    "kind": "datetime",
                    "at": "2026-03-08T02:30:00-05:00",
                    "time_zone": "America/New_York",
                }
            )
        for offset in ["-04:00", "-05:00"]:
            checked_schedule(
                {
                    "kind": "datetime",
                    "at": "2026-11-01T01:30:00" + offset,
                    "time_zone": "America/New_York",
                }
            )
        with self.assertRaises(ContractError):
            checked_schedule(
                {
                    "kind": "datetime",
                    "at": "2026-10-18T23:00:00",
                    "time_zone": "Asia/Taipei",
                }
            )

    def test_all_day_end_exclusive(self):
        event_interval(
            {"kind": "date", "date": "2026-10-18"},
            {"kind": "date", "date": "2026-10-19"},
        )
        with self.assertRaises(ContractError):
            event_interval(
                {"kind": "date", "date": "2026-10-18"},
                {"kind": "date", "date": "2026-10-18"},
            )

    def test_conflicts(self):
        check_revision({"revision": "a"}, "a")
        with self.assertRaises(ContractError) as err:
            check_revision({"revision": "b"}, "a")
        self.assertEqual(err.exception.error["code"], "conflict")

    def test_cursor_changes_and_completeness(self):
        rows = [{"id": str(i)} for i in range(5)]
        p = {"query": "x", "limit": 2}
        first = paginate(rows, p)
        second = paginate(rows, {**p, "cursor": first["next_cursor"]})
        third = paginate(rows, {**p, "cursor": second["next_cursor"]})
        self.assertEqual(first["items"] + second["items"] + third["items"], rows)
        self.assertIsNone(third["next_cursor"])
        with self.assertRaises(ContractError):
            paginate(rows + [{"id": "new"}], {**p, "cursor": first["next_cursor"]})
        with self.assertRaises(ContractError):
            paginate(rows, {**p, "query": "different", "cursor": first["next_cursor"]})

    def test_html_escaping(self):
        self.assertEqual(
            content_html({"body_text": "<script>\n&"}),
            "<div>&lt;script&gt;<br>&amp;</div>",
        )
        with self.assertRaises(ContractError):
            content_html({"body_html": "a", "body_text": "b"})

    def test_retry_claim(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.sqlite3"
            p = {"request_key": "one", "title": "Test"}
            calls = []

            def create():
                calls.append(1)
                return {"id": "result"}

            self.assertEqual(create_once("create", p, create, path), {"id": "result"})
            self.assertEqual(create_once("create", p, create, path), {"id": "result"})
            self.assertEqual(len(calls), 1)
            with self.assertRaises(ContractError):
                create_once("create", {**p, "title": "Other"}, create, path)

    def test_unknown_outcome_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.sqlite3"
            p = {"request_key": "one"}

            def uncertain():
                raise RuntimeError("transport lost after write")

            with self.assertRaises(RuntimeError):
                create_once("create", p, uncertain, path)
            with self.assertRaises(ContractError) as err:
                create_once("create", p, lambda: {}, path)
            self.assertEqual(err.exception.error["code"], "outcome_unknown")

    def test_preflight_failure_can_retry(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.sqlite3"
            p = {"request_key": "one"}

            def rejected():
                raise ContractError("invalid_argument", "bad", write_not_started=True)

            with self.assertRaises(ContractError):
                create_once("create", p, rejected, path)
            self.assertEqual(
                create_once("create", p, lambda: {"id": "ok"}, path), {"id": "ok"}
            )

    def test_concurrent_create(self):
        import threading

        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.sqlite3"
            p = {"request_key": "one"}
            calls = []
            lock = threading.Lock()

            def create():
                with lock:
                    calls.append(1)
                return {"id": "once"}

            def run(_):
                try:
                    return create_once("create", p, create, path)
                except ContractError as e:
                    return e.error

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(run, range(4)))
            self.assertEqual(len(calls), 1)
            self.assertTrue(
                all(
                    r.get("id") == "once" or r.get("code") == "outcome_unknown"
                    for r in results
                )
            )


class NativeProviderContracts(unittest.TestCase):
    def test_append_preserves_original_html_and_checks_revision(self):
        import notes_provider as n

        original = {
            "id": "note-1",
            "title": "Test",
            "folder_id": "folder-1",
            "created_at": None,
            "modified_at": "2026-10-08T00:00:00+00:00",
            "locked": False,
            "shared": False,
            "attachment_count": 0,
            "attachments": [],
            "body_html": "<html><body><div><b>Original</b></div></body></html>",
            "body_text": "Original",
        }
        calls = []

        def native(op, p):
            calls.append((op, p))
            if op == "notes_get":
                return original
            return {
                **original,
                "body_html": p["new_html"],
                "body_text": "Original\nAdded",
            }

        with patch.object(n, "native", side_effect=native):
            result = n.perform(
                "notes_append",
                {
                    "id": "note-1",
                    "expected_revision": n.with_revision(original)["revision"],
                    "body_text": "Added",
                    "confirm": True,
                },
            )
            self.assertIn(
                "<div><b>Original</b></div><div>Added</div></body>", result["body_html"]
            )
            self.assertIn("expected_snapshot", calls[-1][1])
            count = len(calls)
            with self.assertRaises(ContractError):
                n.perform(
                    "notes_append",
                    {
                        "id": "note-1",
                        "expected_revision": "stale",
                        "body_text": "Added",
                        "confirm": True,
                    },
                )
            self.assertEqual(len(calls), count + 1)

    def test_all_day_round_trip_uses_local_dates_and_exclusive_end(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        import eventkit_provider as e

        class NativeDate:
            def __init__(self, value):
                self.value = value

            def timeIntervalSince1970(self):
                return self.value

        class Event:
            title = lambda s: "All day"
            notes = lambda s: None
            URL = lambda s: None
            alarms = lambda s: []
            hasRecurrenceRules = lambda s: False
            recurrenceRules = lambda s: []
            lastModifiedDate = lambda s: None
            timeZone = lambda s: None
            isAllDay = lambda s: True
            startDate = lambda s: NativeDate(
                datetime(2026, 10, 9, tzinfo=ZoneInfo("Asia/Taipei")).timestamp()
            )
            endDate = lambda s: NativeDate(
                datetime(
                    2026, 10, 9, 23, 59, 59, tzinfo=ZoneInfo("Asia/Taipei")
                ).timestamp()
            )
            eventIdentifier = lambda s: "event-1"
            location = lambda s: None
            calendar = lambda s: SimpleNamespace(
                calendarIdentifier=lambda: "cal-1",
                allowsContentModifications=lambda: True,
            )

        foundation = SimpleNamespace(
            NSTimeZone=SimpleNamespace(
                localTimeZone=lambda: SimpleNamespace(name=lambda: "Asia/Taipei")
            )
        )
        with patch.dict(sys.modules, {"Foundation": foundation}):
            row = e.event_row(Event())
        self.assertEqual(row["start"], {"kind": "date", "date": "2026-10-09"})
        self.assertEqual(row["end"], {"kind": "date", "date": "2026-10-10"})

    def test_native_recurrence_description_never_affects_revision(self):
        import eventkit_provider as e

        class Rule:
            frequency = lambda s: 0
            interval = lambda s: 1
            recurrenceEnd = lambda s: None
            daysOfTheWeek = lambda s: []
            daysOfTheMonth = lambda s: []
            monthsOfTheYear = lambda s: []
            weeksOfTheYear = lambda s: []
            daysOfTheYear = lambda s: []
            setPositions = lambda s: []
            firstDayOfTheWeek = lambda s: 0

            def description(self):
                raise AssertionError(
                    "Native description includes unstable memory addresses"
                )

        r = e.recurrence_row(SimpleNamespace(recurrenceRules=lambda: [Rule()]))
        self.assertEqual(r[0]["frequency"], "daily")
        self.assertNotIn("description", r[0])

    def test_reminder_date_only_alarms_are_rejected_before_write(self):
        import eventkit_provider as e

        fake = SimpleNamespace(
            NSDateComponents=None,
            NSCalendar=None,
            NSCalendarIdentifierGregorian=None,
            NSTimeZone=None,
        )
        with (
            patch.dict(sys.modules, {"Foundation": fake}),
            patch.object(
                e,
                "reminder_row",
                return_value={
                    "due": {"kind": "date", "date": "2026-10-09"},
                    "alarms_minutes_before": [],
                    "recurring": False,
                },
            ),
        ):
            with self.assertRaises(ContractError) as err:
                e.apply_reminder(object(), {"alarms_minutes_before": [60]})
        self.assertEqual(err.exception.error["code"], "invalid_argument")
        self.assertTrue(err.exception.error["write_not_started"])


if __name__ == "__main__":
    unittest.main()
