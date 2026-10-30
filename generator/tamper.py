"""INJ-7 and INJ-11: tamper by direct SQL, bypassing the audit API on purpose (owner: GxP seat).

* ``tamper_audit_row`` (INJ-7) edits an audit_log row; the hash chain catches it.
* ``tamper_base_row`` (INJ-11) edits a base-table row; the record reconciliation catches it.

This simulates the fraud the hash chain exists to catch (AC-3.3): someone with access to the database file back-dates
a custody event in the audit trail. It must never be called by the normal pipeline except for INJ-7, after all
audited writes and before ``verify_chain`` (DESIGN 4).
"""

from __future__ import annotations

import datetime as dt
import json

CUSTODY_TABLE = "lims.custody_events"


def tamper_audit_row(con, event_id: str, table: str = CUSTODY_TABLE) -> int:
    """Directly UPDATE ``new_value`` of the INSERT audit row for ``event_id``. Returns the audit_seq it changed.

    The edit back-dates ``performed_at`` by one day (or, if the record has no parseable ``performed_at``, changes
    ``location``). The hashes are left alone, exactly as a naive tamperer would, so ``verify_chain`` must report
    ``first_broken_seq`` equal to the returned audit_seq.
    """
    row = con.execute(
        "SELECT audit_seq, new_value FROM audit.audit_log "
        "WHERE table_name = ? AND record_key = ? AND action = 'INSERT' ORDER BY audit_seq LIMIT 1",
        [table, event_id],
    ).fetchone()
    if row is None:
        raise KeyError(f"no INSERT audit row for {event_id!r} in {table}")
    seq, new_value = int(row[0]), row[1]
    rec = json.loads(new_value) if new_value else {}
    try:
        performed = dt.datetime.fromisoformat(rec["performed_at"])
        rec["performed_at"] = (performed - dt.timedelta(days=1)).isoformat()
    except (KeyError, TypeError, ValueError):
        rec["location"] = f"{rec.get('location') or ''}-TAMPERED"
    tampered = json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    con.execute("UPDATE audit.audit_log SET new_value = ? WHERE audit_seq = ?", [tampered, seq])
    return seq


def tamper_base_row(con, event_id: str, table: str = CUSTODY_TABLE) -> int:
    """INJ-11: directly UPDATE one custody event in the BASE table, leaving the audit trail alone (BUG-005).

    This is the more realistic fraud: re-attributing work to someone else after the fact. ``performed_by`` is set to
    another user from ``lims.users`` (the first one, in ID order, that differs), so no other check (UNKNOWN_USER,
    LATE_ENTRY, CUSTODY_ORDER) fires and only the record reconciliation can catch it (RECORD_MISMATCH). If there is
    no other user, ``performed_at`` is moved one hour earlier instead.

    Returns the audit_seq of the record's INSERT audit row, which ``reconcile`` will report.
    """
    seq = con.execute(
        "SELECT audit_seq FROM audit.audit_log WHERE table_name = ? AND record_key = ? AND action = 'INSERT' "
        "ORDER BY audit_seq LIMIT 1",
        [table, event_id],
    ).fetchone()
    current = con.execute(f"SELECT performed_by FROM {table} WHERE event_id = ?", [event_id]).fetchone()
    if seq is None or current is None:
        raise KeyError(f"no audited row for {event_id!r} in {table}")
    other = con.execute(
        "SELECT user_id FROM lims.users WHERE user_id IS DISTINCT FROM ? ORDER BY user_id LIMIT 1", [current[0]]
    ).fetchone()
    if other is not None:
        con.execute(f"UPDATE {table} SET performed_by = ? WHERE event_id = ?", [other[0], event_id])
    else:
        con.execute(f"UPDATE {table} SET performed_at = performed_at - INTERVAL 1 HOUR WHERE event_id = ?",
                    [event_id])
    return int(seq[0])
