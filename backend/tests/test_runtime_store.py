import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app import attachments, runtime_store, storage, template_system


@pytest.fixture(autouse=True)
def runtime_db(tmp_path, monkeypatch):
    path = tmp_path / "runtime.db"
    monkeypatch.setattr(storage, "DB_PATH", path)
    storage.init_db()
    return path


def _child(code: str, database: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "APP_DB_PATH": str(database)}
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_attachment_extracted_text_survives_process_restart_without_raw_blob(runtime_db):
    item = attachments.add("owner", "session", "notes.md", "text/markdown", "跨进程可见正文".encode())

    conn = sqlite3.connect(runtime_db)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(app_runtime_attachments)")}
        assert "raw_data" not in columns
        assert "data" not in columns
    finally:
        conn.close()

    attachment_id = item["id"]
    result = _child(
        f"""
import time
from app import runtime_store
rows = runtime_store.load_attachments(
    "owner", "session", [{attachment_id!r}], now=time.time(), ttl_seconds=21600
)
print(rows[{attachment_id!r}]["extracted_text"])
""",
        runtime_db,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "跨进程可见正文"


def test_session_lease_is_enforced_by_sqlite_across_processes(runtime_db):
    child_code = """
from app import runtime_store
try:
    with runtime_store.session_lease("conversation", "owner", "session", wait_seconds=0):
        print("acquired")
except runtime_store.RuntimeBusyError:
    print("busy")
"""
    with runtime_store.session_lease("conversation", "owner", "session", ttl_seconds=5, wait_seconds=0):
        blocked = _child(child_code, runtime_db)
    acquired = _child(child_code, runtime_db)

    assert blocked.returncode == 0, blocked.stderr
    assert blocked.stdout.strip() == "busy"
    assert acquired.returncode == 0, acquired.stderr
    assert acquired.stdout.strip() == "acquired"


def test_draft_compare_and_swap_rejects_stale_worker():
    draft = template_system.create_manual_draft("owner")
    first = runtime_store.load_draft("owner", draft.id, now=time.time(), ttl_seconds=template_system.DRAFT_TTL_SECONDS)
    stale = runtime_store.load_draft("owner", draft.id, now=time.time(), ttl_seconds=template_system.DRAFT_TTL_SECONDS)
    assert first and stale

    changed = first.data["definition"]
    changed["sections"][0]["title"] = "worker one"
    runtime_store.update_draft(
        "owner",
        draft.id,
        definition=changed,
        messages=None,
        expected_revision=first.revision,
        expected_epoch=first.epoch,
        now=time.time(),
    )

    with pytest.raises(runtime_store.RuntimeConflictError):
        runtime_store.update_draft(
            "owner",
            draft.id,
            definition=stale.data["definition"],
            messages=None,
            expected_revision=stale.revision,
            expected_epoch=stale.epoch,
            now=time.time(),
        )


def test_privacy_clear_blocks_inflight_attachment_recreation():
    epoch = runtime_store.namespace_epoch("owner", "attachment")
    attachments.clear_owner("owner")

    with pytest.raises(runtime_store.RuntimeOwnerClearedError):
        runtime_store.insert_attachment(
            {
                "attachment_id": "late",
                "owner_id": "owner",
                "session_id": "session",
                "name": "late.txt",
                "size": 4,
                "content_type": "text/plain",
                "extracted_text": "late",
                "summary": "late",
                "category": "文本",
                "char_count": 4,
                "truncated": False,
                "template_structure": "late",
            },
            expected_epoch=epoch,
            now=time.time(),
            ttl_seconds=attachments.ATTACHMENT_TTL_SECONDS,
            max_per_owner=attachments.MAX_ATTACHMENTS_PER_VISITOR,
            max_records=attachments.MAX_ATTACHMENT_RECORDS,
        )


def test_privacy_clear_blocks_inflight_durable_week_recreation():
    epoch = runtime_store.namespace_epoch("owner", "conversation")
    runtime_store.clear_all_owner_runtime("owner")

    with pytest.raises(storage.RuntimeStateConflictError):
        storage.create_week(
            "owner",
            "2026-08-24",
            "late",
            "{}",
            expected_runtime_namespace="conversation",
            expected_runtime_epoch=epoch,
        )

    assert storage.list_weeks("owner") == []


def test_template_save_consumes_exact_draft_atomically_and_honors_privacy_epoch():
    draft = template_system.create_manual_draft("owner")
    stale_snapshot = draft
    runtime_store.clear_all_owner_runtime("owner")

    with pytest.raises(storage.RuntimeStateConflictError):
        storage.create_template(
            "owner",
            "late",
            "manual",
            json.dumps(stale_snapshot.definition, ensure_ascii=False),
            runtime_draft_id=stale_snapshot.id,
            expected_draft_revision=stale_snapshot.revision,
            expected_runtime_epoch=stale_snapshot.runtime_epoch,
        )

    assert storage.list_templates("owner") == []


def test_delete_all_owner_data_erases_runtime_and_durable_rows_in_one_transaction():
    owner_epoch = runtime_store.namespace_epoch("owner", "owner")
    conversation_epoch = runtime_store.namespace_epoch("owner", "conversation")
    storage.save_settings(
        "owner",
        {
            "week_one_start": "2026-08-24",
            "purpose_mode": "default",
            "custom_purpose_name": "",
            "custom_purpose_description": "",
            "detail_level": "standard",
            "tone": "natural",
            "onboarding_completed": True,
        },
        expected_owner_epoch=owner_epoch,
    )
    storage.create_week("owner", "2026-08-24", "durable", "{}")
    runtime_store.save_conversation(
        "owner",
        "conversation",
        [{"role": "system", "content": "temporary"}],
        expected_revision=None,
        expected_epoch=conversation_epoch,
        now=time.time(),
        ttl_seconds=21_600,
        max_records=500,
        expected_owner_epoch=owner_epoch,
    )
    attachments.add(
        "owner",
        "attachment-session",
        "note.txt",
        "text/plain",
        b"temporary",
        expected_owner_epoch=owner_epoch,
    )
    template_system.create_manual_draft(
        "owner",
        expected_owner_epoch=owner_epoch,
    )
    assert template_system.bind_session_template(
        "owner",
        "bound-session",
        None,
        expected_owner_epoch=owner_epoch,
    )

    with runtime_store.session_lease("conversation", "owner", "leased-session"):
        removed, runtime_removed = runtime_store.delete_all_owner_data("owner")

    assert removed == {"weeks": 1, "templates": 0, "settings": 1}
    assert runtime_removed == {
        "conversations": 1,
        "attachments": 1,
        "drafts": 1,
        "custom_conversations": 0,
        "session_templates": 1,
        "leases": 1,
    }
    assert storage.list_weeks("owner") == []
    assert storage.get_settings("owner") is None

    with pytest.raises(storage.RuntimeStateConflictError):
        storage.create_week(
            "owner",
            "2026-08-24",
            "late durable write",
            "{}",
            expected_owner_epoch=owner_epoch,
        )
    with pytest.raises(runtime_store.RuntimeOwnerClearedError):
        runtime_store.save_conversation(
            "owner",
            "late-conversation",
            [{"role": "system", "content": "late"}],
            expected_revision=None,
            expected_epoch=conversation_epoch,
            now=time.time(),
            ttl_seconds=21_600,
            max_records=500,
            expected_owner_epoch=owner_epoch,
        )


def test_session_template_binding_is_shared_between_workers(runtime_db):
    assert template_system.bind_session_template("owner", "session", None)
    result = _child(
        """
from app import template_system
print(template_system.bind_session_template("owner", "session", 42))
""",
        runtime_db,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


def test_binding_capacity_does_not_evict_live_session():
    now = time.time()
    assert runtime_store.bind_session_template(
        "owner",
        "first",
        7,
        now=now,
        ttl_seconds=60,
        max_per_owner=1,
        max_records=10,
    )
    with pytest.raises(runtime_store.RuntimeCapacityError):
        runtime_store.bind_session_template(
            "owner",
            "second",
            8,
            now=now + 1,
            ttl_seconds=60,
            max_per_owner=1,
            max_records=10,
        )
    assert not runtime_store.bind_session_template(
        "owner",
        "first",
        9,
        now=now + 2,
        ttl_seconds=60,
        max_per_owner=1,
        max_records=10,
    )


def test_edit_draft_keeps_source_template_revision_across_reads():
    row = storage.create_template(
        "owner",
        "模板",
        "manual",
        json.dumps(template_system.default_definition(), ensure_ascii=False),
    )
    draft = template_system.create_edit_draft("owner", row)
    reloaded = template_system.get_draft("owner", draft.id)

    assert reloaded
    assert reloaded.source_template_revision == int(row["revision"])
    assert reloaded.runtime_epoch == runtime_store.namespace_epoch("owner", "draft")
