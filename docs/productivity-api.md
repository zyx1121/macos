# Productivity API v2

## Design contract

Tools use lowercase snake_case names, with an app family followed by an action and, where needed, an object: calendar_get_event, notes_append, reminders_complete. These are project conventions; MCP itself specifies discovery, JSON schemas, structured results and behavior annotations.

- list enumerates or filters a collection. search matches a case-insensitive substring of title or body/notes. get reads one complete item.
- create makes a new item with an explicit container and request_key. update changes only supplied fields. delete removes precisely the requested ID.
- No tool chooses the first item with a matching title. Same-named folders, calendars and lists remain distinct through their IDs and accounts.
- Every item has an opaque id and revision. IDs come from native stores and can become invalid after account changes or sync. Return not_found and rediscover; never substitute a same-titled item.
- Write descriptions state their effect. All existing-item writes require confirm=true. This argument is a contract acknowledgement; the caller must honor the user's authorization and its host's approval policy. MCP annotations are hints, not an authorization mechanism.

## Tool catalog

| Family | Tools |
|---|---|
| Notes | notes_list_folders, notes_list, notes_search, notes_get, notes_create, notes_update, notes_append, notes_delete |
| Calendar | calendar_list_calendars, calendar_list_events, calendar_search_events, calendar_get_event, calendar_create_event, calendar_update_event, calendar_delete_event |
| Reminders | reminders_list_lists, reminders_list, reminders_search, reminders_get, reminders_create, reminders_update, reminders_complete, reminders_delete |

Discovery includes ID, title, account and writability. Notes does not expose a reliable writability flag through Apple Events, so its value is null. Native writes can still be refused by the account.

## Common inputs and results

Pagination returns `{items, next_cursor}`. Pass that cursor with the same filters to fetch the next page. If results change, stale_cursor requires restarting without the cursor. Limits are 1 to 100, default 30. Calendar queries require an explicit positive range of at most 366 days and include overlapping occurrences. Reminder due bounds are inclusive dates; an undated reminder is excluded when a due bound is specified. Omit completed to include both states, or pass false for open tasks.

Every MCP result has structuredContent and the equivalent JSON text, using `{data, metadata}` on success and `{error}` with isError=true on failure. Metadata declares schema_version=v2. Specific item/page schemas are published through outputSchema. Native results may include additional details, such as complex recurrence fields and absolute or location alarms.

Updates use expected_revision from get. A stale revision returns conflict without writing. This is a preflight check against the current native item, not a distributed transaction with iCloud or an atomic compare-and-swap against concurrent apps. Omitted fields are preserved; null clears a nullable field; [] clears alarms. Empty updates fail. Complete on an already completed reminder returns its current state unchanged. Update completed=false reopens a task.

## Dates, alarms and recurrence

Date-only schedules are `{kind:"date", date:"2026-10-18"}`. Timed schedules are `{kind:"datetime", at:"2026-10-18T23:00:00+08:00", time_zone:"Asia/Taipei"}`. Offsets must agree with the IANA zone at that instant; invalid DST gaps are refused. All-day event end dates are exclusive. Native all-day events are floating local dates. A reminder's date-only due has no alarm time.

alarms_minutes_before is an array of nonnegative minute offsets. [] clears all alarms, including existing absolute/location alarms. Omission preserves them. Timed reminder alarms require a timed due. Output includes other_alarms when native absolute/location alarms are present; this version preserves but does not create those alarm types.

Simple recurrence accepts frequency (daily/weekly/monthly/yearly), interval, and at most one of count or until. Existing complex native recurrence is fully described in output and is preserved when the field is omitted. Supplying recurrence replaces it with a simple rule; null clears it. Weekly weekday selectors and exception creation are not exposed as recurrence input.

Recurring event get/update/delete requires occurrence_at from list/search, because a series ID alone does not identify an occurrence. Writes also require scope="this" or "future". Changing the recurrence rule itself requires future. Future follows EventKit's series-splitting semantics, and the returned ID may change. Recurring reminders follow Apple's task behavior: completion advances recurrence; delete removes the recurring task. Recurring reminders require a due date.

## Notes content and attachments

notes_list/search return summaries and previews. notes_get returns body_html, body_text and attachment metadata. Protected notes remain discoverable; reading/editing requires unlocking in Notes. The plugin does not unlock notes or retrieve passwords.

Create/update/append accept body_text or body_html, never both. Plain text is escaped into HTML, including line breaks. The note title forms the first line. update with body content is an explicit replacement; append preserves existing HTML and inserts the new fragment. Title-only and folder-only edits preserve the body and attachments.

Body writes on notes containing attachments are refused with attachments_present. Apple's HTML round-trip does not guarantee preservation of all attachment types. The tool does not silently flatten them or claim to edit embedded scans/drawings. Attachments are discoverable but file import/export is outside this interface. Smart-folder queries and shared-note collaboration permissions remain native-app features.

Notes does not provide a documented general-purpose Calendar linking API. Store an E3/web URL in events/reminders, or refer to a note's opaque ID in the notes field. No unsupported Notes deep-link format is invented. Scheduling from note dates is agent work; continuous synchronization is not implied.

## Create retries

Every create requires a caller-generated request_key, unique across these tools. A durable local SQLite claim is recorded before writing. Retrying the identical request returns the original result without another native write. Reusing a key with different inputs returns request_key_conflict.

If a process dies or loses its result after claiming a create, outcome_unknown prevents blind duplicate creation. Search the app to reconcile the result before issuing a new key. Do not delete the state directory to resolve an unknown outcome. The claim cannot make the native write and SQLite commit atomic. Original replay responses are snapshots: get the item again before modifying it.

## Errors

Actionable codes include invalid_argument, permission_required, permission_denied, not_found, read_only, conflict, occurrence_required, scope_required, locked, attachments_present, stale_cursor, request_key_conflict, outcome_unknown, timeout, native_write_failed and native_error. Errors never intentionally include full note bodies or request payloads. A native app may still supply its own short diagnostic. Dependency/spawn failures use the common MCP envelope and describe the missing dependency.

## Example: add a coursework deadline

Discover lists, then call reminders_create:

```json
{
  "list_id": "ID_FROM_REMINDERS_LIST_LISTS",
  "request_key": "coursework-animation-hw1-2026-10-20",
  "title": "Submit animation HW1",
  "due": {"kind": "datetime", "at": "2026-10-20T23:59:00+08:00", "time_zone": "Asia/Taipei"},
  "alarms_minutes_before": [1440, 60],
  "url": "https://e3p.nycu.edu.tw/mod/assign/view.php?id=241725",
  "notes": "Upload the source ZIP and PDF report; include the demo video link."
}
```

If the deadline changes, read the task with reminders_get and pass its ID/revision to reminders_update. Do not create a second reminder or delete/recreate the old one.

## Organization and planning

The organization tools add account/source discovery and create/get/update/delete for Notes folders, Calendar calendars and Reminders lists. Creation requires account_id (Notes) or source_id (EventKit), title and request_key. Sources can refuse creation even when existing calendar content is writable; unsupported_source requires choosing a different native source, not silently switching accounts.

Container get returns a revision. Calendar item_count is null because EventKit does not expose a reliable total count. Reminders counts include completed tasks. Folder counts include direct notes and child folders. Deletion refuses nonempty containers, uses the current revision, and has the same preflight concurrency limits as item updates. Calendar emptiness is checked in bounded four-year queries across Gregorian years 1 through 9999 because EventKit truncates a single wider predicate. It is not inferred from the next year's events.

Notes folder creation supports parent_id within an explicit account. Update accepts title and/or a new parent_id in the same account, rejecting cycles. Root moves and cross-account moves are not exposed. Nested folder deletion returns unsupported_operation: native Apple Events can acknowledge this operation without deleting the folder. Empty root folders can be deleted; system folders can still be refused by Notes. The plugin does not use UI scripting or edit the Notes database to bypass these limits.

Recurrence now accepts days_of_week (Sunday=1 through Saturday=7, week=0 for any week or -5..5 for a monthly ordinal, and -53..53 for a yearly ordinal), days_of_month, months_of_year, weeks_of_year, days_of_year and set_positions. Negative selectors count from the end. Selectors must match their frequency and cannot contain duplicates or zero-valued positions. For example, weekly Tuesday/Thursday is days_of_week=[{day:3},{day:5}], and the last Friday of each month is frequency=monthly, days_of_week=[{day:6}], set_positions=[-1]. Existing native rules remain unchanged when recurrence is omitted.

calendar_check_conflicts and calendar_find_free_slots require distinct explicit calendar_ids, from/to timestamps and an IANA time_zone. They query native occurrences directly without page limits. Coverage is limited to locally synced events in the returned calendar_ids; the response never claims coverage of unqueried accounts. Intervals are half-open: adjacent events do not conflict. Canceled events are ignored, unknown availability blocks time, free events are ignored unless include_free_events=true, and all-day events block their local dates unless include_all_day=false. All-day dates are interpreted in the requested planning timezone. exclude_event_ids excludes an entire native ID, including all returned occurrences of that ID.

Free slots are maximal free intervals at least duration_minutes long, not a sampled grid of every possible meeting start. Optional working_hours specifies same-day local start/end (HH:MM) and ISO weekdays (Monday=1 through Sunday=7). DST gaps in working-hour boundaries are refused; ambiguous boundaries use the first occurrence. Durations are elapsed minutes. limit caps the returned slots and has_more declares omitted slots. Planning reads do not reserve time or guarantee availability after another app changes its calendar.

## Mail API v2

Mail uses productivity.py with the same private JSON stdin, envelopes, typed schemas and paging. Legacy mail_list_inbox, mail_read_message and mail_compose_draft are removed. mail_get_message accepts an opaque ID, never a subject selector. mail_list_accounts returns IDs and address arrays. mail_list_mailboxes returns explicit account/parent relationships, including local mailboxes. Mailbox IDs encode native account and hierarchy information; renamed/moved mailboxes require rediscovery.

mail_list_messages and mail_search_messages accept mailbox_id/account_id, unread, received_from and received_to. Date bounds are inclusive/exclusive respectively. Omitted mailbox scans all discovered synced mailboxes; use explicit filters for large stores. Search matches subject or sender, not attachment contents or unsynced server mail. List/search return summaries; get returns text, recipients and attachment count. This version does not send messages or edit received messages.

mail_create_draft requires subject, body_text, to and request_key, with optional cc/bcc, account_id and visible. The explicit account selects its first configured sender address. visible defaults true. Native compose IDs include Mail's process launch identity; closing/reopening or restarting Mail requires rediscovery. mail_list_drafts enumerates native compose objects, not every saved draft in the Drafts mailbox. Saved draft messages can still be read using message tools.

Draft update/get/delete use IDs and revisions. Omitted fields are preserved, and [] clears recipient arrays. Mail can silently ignore its existing-body setter. Body replacement therefore creates a verified replacement draft with the requested body and preserved omitted fields, then discards the original. It returns a new id and replacement_of; use the returned ID for subsequent calls. Body replacement is refused for attachment-bearing and reply/forward drafts to preserve attachments and threading. Subject/recipient updates preserve attachments. A durable internal retry claim prevents duplicate replacements for the same ID, revision and patch; failures after creation return outcome_unknown with both IDs for reconciliation. Native readback verifies fields and saving; native_write_unverified requires reading the current draft before retrying.

Draft discard verifies a unique matching saved copy by subject, text and recipients as a read-only preflight, while the write targets the exact native compose ID. Ambiguous copies return ambiguous_draft instead of selecting one. Saved-copy removal or native deleted status is verified before reporting deletion. Some Mail versions retain discarded compose objects in their in-memory collection; a private, process-scoped tombstone hides those objects from subsequent list/get calls. The state file also contains durable creation claims and must not be cleared to force retries.

## Capability diagnostics

macos_get_capabilities remains callable even on Linux or when native dependencies are missing. It reports every tool, registration availability, missing requirements, native permission statuses, probe failures and remediation hints. Registration availability does not assert native authorization or account write access.

Permission checks do not request access or open apps. EventKit reports full/write-only/denied/restricted/not-determined status; Screen Recording uses a preflight check, and Automation uses a non-prompting Apple Events check. target_not_running and unknown are not grants. Diagnostics use the MCP host identity, which can differ from the terminal used for native verification.
