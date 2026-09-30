from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


CASE_STATUSES = ("OPEN", "INVESTIGATING", "ESCALATED", "RESOLVED", "CLOSED")

CASE_STATUS_VI = {
    "OPEN": "ĐANG MỞ",
    "INVESTIGATING": "ĐANG ĐIỀU TRA",
    "ESCALATED": "ĐÃ ESCALATE",
    "RESOLVED": "ĐÃ XỬ LÝ",
    "CLOSED": "ĐÃ ĐÓNG",
}

ALLOWED_TRANSITIONS = {
    "OPEN": ("INVESTIGATING",),
    "INVESTIGATING": ("ESCALATED", "RESOLVED"),
    "ESCALATED": ("INVESTIGATING", "RESOLVED"),
    "RESOLVED": ("INVESTIGATING", "CLOSED"),
    "CLOSED": ("INVESTIGATING",),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def available_statuses(current_status: str) -> list[str]:
    current = str(current_status or "OPEN").upper()
    if current not in CASE_STATUSES:
        raise ValueError(f"Unsupported investigation case status: {current}")
    return [current, *ALLOWED_TRANSITIONS[current]]


def open_case(
    store,
    *,
    signal_id: str,
    priority: str,
    owner: str | None = None,
    note: str | None = None,
) -> dict:
    if not store.get_signal(signal_id):
        raise ValueError(f"Signal not found: {signal_id}")

    existing = store.get_investigation_case_by_signal(signal_id)
    if existing:
        return dict(existing)

    now = _now_iso()
    case_id = str(uuid4())
    clean_owner = (owner or "").strip() or None
    clean_note = (note or "").strip() or None
    row = {
        "case_id": case_id,
        "signal_id": signal_id,
        "priority": str(priority or "THEO DÕI").strip(),
        "status": "OPEN",
        "owner": clean_owner,
        "investigation_note": clean_note,
        "resolution": None,
        "opened_at": now,
        "updated_at": now,
        "closed_at": None,
    }
    store.create_investigation_case(row)
    store.insert_investigation_audit(
        {
            "audit_id": str(uuid4()),
            "case_id": case_id,
            "action_type": "CASE_OPENED",
            "from_status": None,
            "to_status": "OPEN",
            "owner": clean_owner,
            "note": clean_note,
            "created_at": now,
        }
    )
    return dict(store.get_investigation_case(case_id) or row)


def update_case(
    store,
    *,
    case_id: str,
    status: str,
    owner: str | None = None,
    note: str | None = None,
    resolution: str | None = None,
) -> dict:
    current = store.get_investigation_case(case_id)
    if not current:
        raise ValueError(f"Investigation case not found: {case_id}")
    current = dict(current)

    old_status = str(current.get("status") or "OPEN").upper()
    new_status = str(status or old_status).upper()
    if new_status not in CASE_STATUSES:
        raise ValueError(f"Unsupported investigation case status: {new_status}")
    if new_status != old_status and new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise ValueError(f"Invalid case transition: {old_status} -> {new_status}")

    clean_owner = (owner or "").strip() or None
    clean_note = (note or "").strip() or None
    clean_resolution = (resolution or "").strip() or None

    if new_status in {"ESCALATED", "RESOLVED", "CLOSED"} and new_status != old_status and not clean_note:
        raise ValueError("Cần ghi chú khi escalation, resolve hoặc close case.")

    effective_resolution = clean_resolution or current.get("resolution")
    if new_status in {"RESOLVED", "CLOSED"} and not effective_resolution:
        raise ValueError("Cần nhập kết quả xử lý trước khi chuyển case sang RESOLVED/CLOSED.")

    now = _now_iso()
    closed_at = current.get("closed_at")
    if new_status == "CLOSED":
        closed_at = now
    elif old_status == "CLOSED" and new_status != "CLOSED":
        closed_at = None

    changes = {
        "status": new_status,
        "owner": clean_owner,
        "investigation_note": clean_note or current.get("investigation_note"),
        "resolution": effective_resolution,
        "updated_at": now,
        "closed_at": closed_at,
    }
    store.update_investigation_case(case_id, changes)

    changed_status = new_status != old_status
    owner_changed = clean_owner != current.get("owner")
    note_changed = bool(clean_note and clean_note != current.get("investigation_note"))
    resolution_changed = bool(clean_resolution and clean_resolution != current.get("resolution"))
    if changed_status or owner_changed or note_changed or resolution_changed:
        action_type = "STATUS_CHANGED" if changed_status else "CASE_UPDATED"
        store.insert_investigation_audit(
            {
                "audit_id": str(uuid4()),
                "case_id": case_id,
                "action_type": action_type,
                "from_status": old_status,
                "to_status": new_status,
                "owner": clean_owner,
                "note": clean_note or (clean_resolution if resolution_changed else None),
                "created_at": now,
            }
        )

    return dict(store.get_investigation_case(case_id))


def audit_rows(store, case_id: str, limit: int = 100) -> list[dict]:
    return [dict(row) for row in store.investigation_audit(case_id, limit=limit)]
