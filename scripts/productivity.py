#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyobjc-framework-EventKit; sys_platform == 'darwin'"]
# ///
"""JSON-over-stdin native productivity tools. No title-based write selectors."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from productivity_contract import ContractError, create_once, fail


def dispatch(operation, payload):
    if operation.startswith("notes_"):
        from notes_provider import perform
    elif operation.startswith(("calendar_", "reminders_")):
        from eventkit_provider import perform
    else:
        fail("invalid_argument", "Unknown operation")
    if "create" in operation:
        return create_once(operation, payload, lambda: perform(operation, payload))
    return perform(operation, payload)


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            fail("invalid_argument", "Expected one operation name")
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            fail("invalid_argument", "Input must be valid JSON")
        if not isinstance(payload, dict):
            fail("invalid_argument", "Input must be a JSON object")
        result = dispatch(sys.argv[1], payload)
        print(
            json.dumps(
                {"success": True, "data": result, "metadata": {"schema_version": "v2"}},
                ensure_ascii=False,
            )
        )
    except ContractError as e:
        print(json.dumps({"success": False, "error": e.error}, ensure_ascii=False))
        sys.exit(1)
    except Exception as e:
        # No payload, traceback or private body in an error response.
        print(
            json.dumps(
                {
                    "success": False,
                    "error": {
                        "code": "native_error",
                        "message": str(e)[:500],
                        "hint": "Check native app permissions and read the item again",
                    },
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)
