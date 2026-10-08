import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from planning import calculate
from productivity_contract import ContractError, validate_recurrence


def event(id, start, end, **fields):
    return {
        "id": id,
        "start": {"kind": "datetime", "at": start, "time_zone": "UTC"},
        "end": {"kind": "datetime", "at": end, "time_zone": "UTC"},
        **fields,
    }


class ExpandedTests(unittest.TestCase):
    def test_union_clipping_and_adjacency(self):
        p = {
            "from": "2026-10-09T09:00:00Z",
            "to": "2026-10-09T18:00:00Z",
            "time_zone": "UTC",
            "duration_minutes": 60,
        }
        rows = [
            event("a", "2026-10-09T08:00:00Z", "2026-10-09T10:00:00Z"),
            event("b", "2026-10-09T09:30:00Z", "2026-10-09T11:00:00Z"),
            event("c", "2026-10-09T12:00:00Z", "2026-10-09T13:00:00Z"),
        ]
        r = calculate(rows, p, ["c"])
        self.assertEqual([s["duration_minutes"] for s in r["slots"]], [60, 300])
        p.update({"from": "2026-10-09T11:00:00Z", "to": "2026-10-09T12:00:00Z"})
        self.assertFalse(calculate(rows, p, ["c"], True)["has_conflicts"])

    def test_free_canceled_and_exclusions(self):
        p = {
            "from": "2026-10-09T09:00:00Z",
            "to": "2026-10-09T10:00:00Z",
            "time_zone": "UTC",
            "duration_minutes": 60,
        }
        rows = [
            event("a", p["from"], p["to"], availability="free"),
            event("b", p["from"], p["to"], status="canceled"),
        ]
        self.assertEqual(len(calculate(rows, p, ["c"])["slots"]), 1)
        self.assertTrue(
            calculate(rows, {**p, "include_free_events": True}, ["c"], True)[
                "has_conflicts"
            ]
        )
        self.assertFalse(
            calculate(
                rows,
                {**p, "include_free_events": True, "exclude_event_ids": ["a"]},
                ["c"],
                True,
            )["has_conflicts"]
        )

    def test_all_day_uses_query_timezone(self):
        row = {
            "id": "a",
            "start": {"kind": "date", "date": "2026-10-09"},
            "end": {"kind": "date", "date": "2026-10-10"},
        }
        p = {
            "from": "2026-10-08T16:00:00Z",
            "to": "2026-10-09T16:00:00Z",
            "time_zone": "Asia/Taipei",
            "duration_minutes": 60,
        }
        self.assertEqual(calculate([row], p, ["c"])["slots"], [])
        self.assertEqual(
            len(calculate([row], {**p, "include_all_day": False}, ["c"])["slots"]), 1
        )

    def test_working_hours_weekdays_and_limit(self):
        p = {
            "from": "2026-10-09T00:00:00Z",
            "to": "2026-10-13T00:00:00Z",
            "time_zone": "UTC",
            "duration_minutes": 120,
            "working_hours": {
                "start": "09:00",
                "end": "17:00",
                "weekdays": [1, 2, 3, 4, 5],
            },
            "limit": 1,
        }
        r = calculate([], p, ["c"])
        self.assertTrue(r["has_more"])
        self.assertEqual(r["slots"][0]["duration_minutes"], 480)

    def test_dst_elapsed_time_and_gap_rejection(self):
        p = {
            "from": "2026-11-01T00:00:00-04:00",
            "to": "2026-11-02T00:00:00-05:00",
            "time_zone": "America/New_York",
            "duration_minutes": 60,
        }
        self.assertEqual(calculate([], p, ["c"])["slots"][0]["duration_minutes"], 1500)
        p.update(
            {
                "from": "2026-03-08T00:00:00-05:00",
                "to": "2026-03-09T00:00:00-04:00",
                "working_hours": {"start": "02:30", "end": "04:00", "weekdays": [7]},
            }
        )
        with self.assertRaises(ContractError):
            calculate([], p, ["c"])

    def test_complex_recurrence_validation(self):
        for rule in [
            {"frequency": "weekly", "days_of_week": [{"day": 3}, {"day": 5}]},
            {
                "frequency": "monthly",
                "days_of_week": [{"day": 6}],
                "set_positions": [-1],
            },
            {"frequency": "yearly", "months_of_year": [10], "days_of_month": [-1]},
        ]:
            validate_recurrence(rule)
        for rule in [
            {"frequency": "daily", "days_of_month": [1]},
            {"frequency": "weekly", "days_of_week": [{"day": 2, "week": -1}]},
            {"frequency": "monthly", "set_positions": [-1]},
            {"frequency": "monthly", "days_of_month": [0]},
            {"frequency": "yearly", "months_of_year": [1, 1]},
        ]:
            with self.assertRaises(ContractError):
                validate_recurrence(rule)

    def test_calendar_empty_check_does_not_trust_four_year_cap(self):
        import eventkit_provider as e

        class Store:
            def predicateForEventsWithStartDate_endDate_calendars_(self, a, b, c):
                return a

            def eventsMatchingPredicate_(self, p):
                return ["future"] if p.year >= 2030 else []

        with patch.object(e, "native_date", side_effect=lambda dt: dt):
            self.assertTrue(e.calendar_has_items(Store(), object()))

    def test_mail_revision_conflict_prevents_write(self):
        import mail_provider as m

        with patch.object(
            m, "native", return_value={"id": "d", "subject": "changed"}
        ) as native:
            with self.assertRaises(ContractError):
                m.perform(
                    "mail_update_draft",
                    {
                        "id": "d",
                        "expected_revision": "old",
                        "confirm": True,
                        "subject": "new",
                    },
                )
            self.assertEqual(native.call_count, 1)

    def test_folder_revision_conflict_prevents_write(self):
        import notes_provider as n

        with patch.object(
            n, "native", return_value={"id": "f", "title": "changed"}
        ) as native:
            with self.assertRaises(ContractError):
                n.perform(
                    "notes_update_folder",
                    {
                        "id": "f",
                        "expected_revision": "old",
                        "confirm": True,
                        "title": "new",
                    },
                )
            self.assertEqual(native.call_count, 1)

    def test_noninteractive_permissions(self):
        import permissions_provider as p

        with patch.object(p.sys, "platform", "linux"):
            self.assertEqual(
                p.perform("macos_get_permissions", {})["calendar"],
                "unsupported_platform",
            )


class PlanningProviderTests(unittest.TestCase):
    def test_floating_all_day_query_is_padded_for_other_timezones(self):
        from types import SimpleNamespace

        import eventkit_provider as e

        captured = []

        class Store:
            def predicateForEventsWithStartDate_endDate_calendars_(self, a, b, c):
                captured.append((a, b))
                return object()

            def eventsMatchingPredicate_(self, p):
                return []

        p = {
            "calendar_ids": ["cal"],
            "from": "2026-10-09T18:00:00-04:00",
            "to": "2026-10-09T20:00:00-04:00",
            "time_zone": "America/New_York",
        }
        with (
            patch.dict(sys.modules, {"EventKit": SimpleNamespace()}),
            patch.object(e, "store_for", return_value=Store()),
            patch.object(e, "container", return_value=object()),
            patch.object(e, "native_date", side_effect=lambda dt: dt),
        ):
            e.perform("calendar_check_conflicts", p)
            e.perform("calendar_check_conflicts", {**p, "include_all_day": False})
        self.assertEqual((captured[1][0] - captured[0][0]).total_seconds(), 2 * 86400)
        self.assertEqual((captured[0][1] - captured[1][1]).total_seconds(), 2 * 86400)


class MailRebuildTests(unittest.TestCase):
    def current(self):
        return {
            "id": "original",
            "subject": "Coursework",
            "body_text": "old body",
            "sender": "sender@example.test",
            "to": ["recipient@example.test"],
            "cc": [],
            "bcc": [],
            "visible": True,
        }

    def test_attachments_and_threading_refuse_before_creation(self):
        import mail_provider as m

        for info in [
            {"attachment_count": 1, "threaded": False},
            {"attachment_count": 0, "threaded": True},
        ]:
            with patch.object(m, "native", return_value=info) as native:
                with self.assertRaises(ContractError):
                    m.rebuild_draft(
                        self.current(),
                        {
                            "id": "original",
                            "expected_revision": "old",
                            "confirm": True,
                            "body_text": "new",
                        },
                    )
                self.assertEqual(native.call_count, 1)

    def test_rebuild_preserves_fields_and_returns_new_identity(self):
        import os
        import tempfile

        import mail_provider as m

        old = self.current()
        replacement = {**old, "id": "replacement", "body_text": "new"}
        operations = []

        def native(op, p):
            operations.append((op, p))
            if op == "mail_inspect_saved_draft":
                return {"attachment_count": 0, "threaded": False}
            if op == "mail_create_draft":
                return replacement
            if op == "mail_get_draft":
                return replacement if p["id"] == "replacement" else old
            if op == "mail_delete_draft":
                return {"id": "original", "deleted": True, "saved_message_id": 7}
            if op == "mail_verify_draft_deleted":
                return {"deleted": True}
            raise AssertionError(op)

        with (
            tempfile.TemporaryDirectory() as d,
            patch.dict(os.environ, {"MACOS_MCP_STATE_DIR": d}),
            patch.object(m, "native", side_effect=native),
        ):
            p = {
                "id": "original",
                "expected_revision": m.revision(old)["revision"],
                "confirm": True,
                "body_text": "new",
            }
            result = m.rebuild_draft(old, p)
            self.assertEqual(result["id"], "replacement")
            self.assertEqual(result["replacement_of"], "original")
            created = next(args for op, args in operations if op == "mail_create_draft")
            self.assertEqual(created["to"], old["to"])
            self.assertEqual(created["subject"], old["subject"])
            self.assertEqual(created["sender"], old["sender"])
            self.assertIn("original", m.deleted_drafts())

    def test_changed_original_is_retained_and_reports_replacement_id(self):
        import mail_provider as m

        old = self.current()
        replacement = {**old, "id": "replacement", "body_text": "new"}

        def native(op, p):
            if op == "mail_inspect_saved_draft":
                return {"attachment_count": 0, "threaded": False}
            if op == "mail_get_draft":
                return (
                    replacement
                    if p["id"] == "replacement"
                    else {**old, "subject": "Concurrent change"}
                )
            raise AssertionError("No discard after a concurrent change")

        with (
            patch.object(m, "native", side_effect=native),
            patch.object(m, "create_once", return_value=replacement),
        ):
            with self.assertRaises(ContractError) as ex:
                m.rebuild_draft(
                    old,
                    {
                        "id": "original",
                        "expected_revision": m.revision(old)["revision"],
                        "confirm": True,
                        "body_text": "new",
                    },
                )
            self.assertEqual(ex.exception.error["code"], "outcome_unknown")
            self.assertEqual(ex.exception.error["replacement_draft_id"], "replacement")


if __name__ == "__main__":
    unittest.main()
