"""SQLite-backed ephemeral runtime state shared by every application worker.

The application keeps durable reports and settings in :mod:`app.storage`.  This
module uses the same database for short-lived workflow state.  Every row has a
TTL, while owner namespace epochs prevent an in-flight request from recreating
state after a privacy clear.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app import storage


class RuntimeConflictError(RuntimeError):
    """A compare-and-swap update lost to another process."""


class RuntimeCapacityError(RuntimeError):
    """A bounded runtime collection has reached its configured limit."""


class RuntimeOwnerClearedError(RuntimeConflictError):
    """The owner cleared this kind of runtime state while work was in flight."""


class RuntimeBusyError(RuntimeError):
    """Another worker currently owns the requested session lease."""


@dataclass(frozen=True)
class Snapshot:
    data: dict
    revision: int
    epoch: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_runtime_owner_epochs (
    owner_id TEXT NOT NULL,
    namespace TEXT NOT NULL,
    epoch INTEGER NOT NULL DEFAULT 0 CHECK(epoch >= 0),
    PRIMARY KEY(owner_id, namespace)
);

CREATE TABLE IF NOT EXISTS app_runtime_conversations (
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    messages_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    touched_at REAL NOT NULL,
    PRIMARY KEY(owner_id, session_id)
);

CREATE TABLE IF NOT EXISTS app_runtime_attachments (
    attachment_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL CHECK(size >= 0),
    content_type TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    summary TEXT NOT NULL,
    category TEXT NOT NULL,
    char_count INTEGER NOT NULL CHECK(char_count >= 0),
    truncated INTEGER NOT NULL DEFAULT 0 CHECK(truncated IN (0, 1)),
    template_structure TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_runtime_template_drafts (
    draft_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    source_template_id INTEGER,
    source_template_revision INTEGER,
    source_template_status TEXT NOT NULL DEFAULT '',
    suggested_name TEXT NOT NULL DEFAULT '',
    analysis_json TEXT NOT NULL DEFAULT '{}',
    attachment_session_id TEXT NOT NULL DEFAULT '',
    messages_json TEXT NOT NULL DEFAULT '[]',
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    touched_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS app_runtime_custom_conversations (
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    template_id INTEGER NOT NULL,
    template_name TEXT NOT NULL,
    definition_json TEXT NOT NULL,
    messages_json TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    touched_at REAL NOT NULL,
    PRIMARY KEY(owner_id, session_id)
);

CREATE TABLE IF NOT EXISTS app_runtime_session_templates (
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    template_id INTEGER NOT NULL,
    touched_at REAL NOT NULL,
    PRIMARY KEY(owner_id, session_id)
);

CREATE TABLE IF NOT EXISTS app_runtime_leases (
    namespace TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    holder TEXT NOT NULL,
    expires_at REAL NOT NULL,
    PRIMARY KEY(namespace, owner_id, session_id)
);

CREATE INDEX IF NOT EXISTS idx_runtime_conversations_touched
ON app_runtime_conversations(touched_at);
CREATE INDEX IF NOT EXISTS idx_runtime_attachments_owner_created
ON app_runtime_attachments(owner_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runtime_attachments_created
ON app_runtime_attachments(created_at);
CREATE INDEX IF NOT EXISTS idx_runtime_drafts_owner_touched
ON app_runtime_template_drafts(owner_id, touched_at);
CREATE INDEX IF NOT EXISTS idx_runtime_drafts_touched
ON app_runtime_template_drafts(touched_at);
CREATE INDEX IF NOT EXISTS idx_runtime_custom_touched
ON app_runtime_custom_conversations(touched_at);
CREATE INDEX IF NOT EXISTS idx_runtime_bindings_touched
ON app_runtime_session_templates(touched_at);
CREATE INDEX IF NOT EXISTS idx_runtime_leases_expires
ON app_runtime_leases(expires_at);
"""

_schema_lock = threading.Lock()
_schema_signatures: dict[str, tuple[int, int]] = {}


def _database_path() -> Path:
    # Read dynamically so tests and maintenance scripts that override
    # storage.DB_PATH automatically use the same database.
    return Path(storage.DB_PATH)


def _raw_connection() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return stat.st_dev, stat.st_ino


def _ensure_schema() -> None:
    path = _database_path()
    key = str(path.resolve())
    signature = _file_signature(path)
    if signature is not None and _schema_signatures.get(key) == signature:
        return
    with _schema_lock:
        signature = _file_signature(path)
        if signature is not None and _schema_signatures.get(key) == signature:
            return
        conn = _raw_connection()
        try:
            # executescript otherwise commits before running its input. Put the
            # complete idempotent schema migration inside one explicit writer
            # transaction so concurrent worker startups cannot observe a
            # partially initialized runtime schema.
            conn.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA)
            draft_columns = {str(row["name"]) for row in conn.execute("PRAGMA table_info(app_runtime_template_drafts)")}
            if "source_template_revision" not in draft_columns:
                conn.execute("ALTER TABLE app_runtime_template_drafts ADD COLUMN source_template_revision INTEGER")
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        signature = _file_signature(path)
        if signature is not None:
            _schema_signatures[key] = signature


def _connection() -> sqlite3.Connection:
    _ensure_schema()
    return _raw_connection()


@contextmanager
def _transaction() -> Iterator[sqlite3.Connection]:
    conn = _connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _epoch(conn: sqlite3.Connection, owner_id: str, namespace: str) -> int:
    row = conn.execute(
        "SELECT epoch FROM app_runtime_owner_epochs WHERE owner_id = ? AND namespace = ?",
        (owner_id, namespace),
    ).fetchone()
    return int(row["epoch"]) if row else 0


def namespace_epoch(owner_id: str, namespace: str) -> int:
    conn = _connection()
    try:
        return _epoch(conn, owner_id, namespace)
    finally:
        conn.close()


def assert_namespace_epoch(owner_id: str, namespace: str, expected_epoch: int) -> None:
    """Fail if a privacy/settings clear invalidated the caller's snapshot."""
    conn = _connection()
    try:
        if _epoch(conn, owner_id, namespace) != expected_epoch:
            raise RuntimeOwnerClearedError("运行态已被用户清除")
    finally:
        conn.close()


def _assert_epoch(
    conn: sqlite3.Connection,
    owner_id: str,
    namespace: str,
    expected_epoch: int,
) -> None:
    if _epoch(conn, owner_id, namespace) != expected_epoch:
        raise RuntimeOwnerClearedError("运行态已被用户清除")


def _assert_owner_epoch(
    conn: sqlite3.Connection,
    owner_id: str,
    expected_owner_epoch: int | None,
) -> None:
    """Validate a request-wide privacy epoch inside the caller's write transaction."""
    if expected_owner_epoch is not None:
        _assert_epoch(conn, owner_id, "owner", expected_owner_epoch)


def _bump_epoch(conn: sqlite3.Connection, owner_id: str, namespace: str) -> None:
    conn.execute(
        "INSERT INTO app_runtime_owner_epochs (owner_id, namespace, epoch) VALUES (?, ?, 1) "
        "ON CONFLICT(owner_id, namespace) DO UPDATE SET epoch = epoch + 1",
        (owner_id, namespace),
    )


def _clear_namespace(
    namespace: str,
    tables: tuple[str, ...],
    owner_id: str | None,
) -> int:
    allowed = {
        "app_runtime_conversations",
        "app_runtime_attachments",
        "app_runtime_template_drafts",
        "app_runtime_custom_conversations",
        "app_runtime_session_templates",
    }
    if not set(tables) <= allowed:
        raise ValueError("invalid runtime table")
    with _transaction() as conn:
        if owner_id is None:
            owners: set[str] = set()
            for table in tables:
                owners.update(str(row["owner_id"]) for row in conn.execute(f"SELECT DISTINCT owner_id FROM {table}"))
            owners.update(
                str(row["owner_id"])
                for row in conn.execute(
                    "SELECT owner_id FROM app_runtime_owner_epochs WHERE namespace = ?",
                    (namespace,),
                )
            )
            for current_owner in owners:
                _bump_epoch(conn, current_owner, namespace)
            removed = 0
            for table in tables:
                removed += conn.execute(f"DELETE FROM {table}").rowcount
            return removed
        _bump_epoch(conn, owner_id, namespace)
        removed = 0
        for table in tables:
            removed += conn.execute(f"DELETE FROM {table} WHERE owner_id = ?", (owner_id,)).rowcount
        return removed


def clear_all_owner_runtime(owner_id: str) -> dict[str, int]:
    """Atomically invalidate and remove every runtime state owned by a visitor."""
    namespaces = ("conversation", "attachment", "draft", "custom")
    tables = {
        "conversations": "app_runtime_conversations",
        "attachments": "app_runtime_attachments",
        "drafts": "app_runtime_template_drafts",
        "custom_conversations": "app_runtime_custom_conversations",
        "session_templates": "app_runtime_session_templates",
    }
    with _transaction() as conn:
        for namespace in namespaces:
            _bump_epoch(conn, owner_id, namespace)
        removed = {
            label: conn.execute(f"DELETE FROM {table} WHERE owner_id = ?", (owner_id,)).rowcount
            for label, table in tables.items()
        }
        removed["leases"] = conn.execute("DELETE FROM app_runtime_leases WHERE owner_id = ?", (owner_id,)).rowcount
        return removed


def delete_all_owner_data(owner_id: str) -> tuple[dict[str, int], dict[str, int]]:
    """Atomically invalidate and erase runtime plus durable visitor-owned data."""
    namespaces = ("owner", "conversation", "attachment", "draft", "custom")
    runtime_tables = {
        "conversations": "app_runtime_conversations",
        "attachments": "app_runtime_attachments",
        "drafts": "app_runtime_template_drafts",
        "custom_conversations": "app_runtime_custom_conversations",
        "session_templates": "app_runtime_session_templates",
    }
    with _transaction() as conn:
        for namespace in namespaces:
            _bump_epoch(conn, owner_id, namespace)
        runtime_removed = {
            label: conn.execute(f"DELETE FROM {table} WHERE owner_id = ?", (owner_id,)).rowcount
            for label, table in runtime_tables.items()
        }
        runtime_removed["leases"] = conn.execute(
            "DELETE FROM app_runtime_leases WHERE owner_id = ?", (owner_id,)
        ).rowcount
        removed = {
            "weeks": conn.execute("DELETE FROM visitor_weeks WHERE owner_id = ?", (owner_id,)).rowcount,
            "templates": conn.execute("DELETE FROM custom_templates WHERE owner_id = ?", (owner_id,)).rowcount,
            "settings": conn.execute("DELETE FROM visitor_settings WHERE owner_id = ?", (owner_id,)).rowcount,
        }
        return removed, runtime_removed


# Ordinary conversations ----------------------------------------------------


def load_conversation(
    owner_id: str,
    session_id: str,
    *,
    now: float,
    ttl_seconds: int,
) -> Snapshot | None:
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM app_runtime_conversations WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        epoch = _epoch(conn, owner_id, "conversation")
        row = conn.execute(
            "SELECT messages_json, revision FROM app_runtime_conversations WHERE owner_id = ? AND session_id = ?",
            (owner_id, session_id),
        ).fetchone()
        if not row:
            return None
        return Snapshot(
            data={"messages": json.loads(row["messages_json"])},
            revision=int(row["revision"]),
            epoch=epoch,
        )


def save_conversation(
    owner_id: str,
    session_id: str,
    messages: list[dict],
    *,
    expected_revision: int | None,
    expected_epoch: int,
    now: float,
    ttl_seconds: int,
    max_records: int,
    expected_owner_epoch: int | None = None,
) -> int:
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        _assert_epoch(conn, owner_id, "conversation", expected_epoch)
        conn.execute(
            "DELETE FROM app_runtime_conversations WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        current = conn.execute(
            "SELECT revision FROM app_runtime_conversations WHERE owner_id = ? AND session_id = ?",
            (owner_id, session_id),
        ).fetchone()
        if current is None:
            if expected_revision is not None:
                raise RuntimeConflictError("conversation was removed")
            conn.execute(
                "INSERT INTO app_runtime_conversations "
                "(owner_id, session_id, messages_json, revision, touched_at) VALUES (?, ?, ?, 0, ?)",
                (owner_id, session_id, _json(messages), now),
            )
            revision = 0
        else:
            revision = int(current["revision"])
            if expected_revision != revision:
                raise RuntimeConflictError("conversation revision changed")
            revision += 1
            conn.execute(
                "UPDATE app_runtime_conversations SET messages_json = ?, revision = ?, touched_at = ? "
                "WHERE owner_id = ? AND session_id = ?",
                (_json(messages), revision, now, owner_id, session_id),
            )
        count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_conversations").fetchone()[0])
        excess = count - max_records
        if excess > 0:
            conn.execute(
                "DELETE FROM app_runtime_conversations WHERE rowid IN "
                "(SELECT rowid FROM app_runtime_conversations ORDER BY touched_at LIMIT ?)",
                (excess,),
            )
        return revision


def delete_conversation(owner_id: str, session_id: str) -> bool:
    with _transaction() as conn:
        return bool(
            conn.execute(
                "DELETE FROM app_runtime_conversations WHERE owner_id = ? AND session_id = ?",
                (owner_id, session_id),
            ).rowcount
        )


def clear_conversations(owner_id: str | None = None) -> int:
    return _clear_namespace("conversation", ("app_runtime_conversations",), owner_id)


def cleanup_conversations(*, now: float, ttl_seconds: int, max_records: int) -> int:
    with _transaction() as conn:
        removed = conn.execute(
            "DELETE FROM app_runtime_conversations WHERE touched_at < ?",
            (now - ttl_seconds,),
        ).rowcount
        count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_conversations").fetchone()[0])
        excess = count - max_records
        if excess > 0:
            removed += conn.execute(
                "DELETE FROM app_runtime_conversations WHERE rowid IN "
                "(SELECT rowid FROM app_runtime_conversations ORDER BY touched_at LIMIT ?)",
                (excess,),
            ).rowcount
        return removed


# Attachments ---------------------------------------------------------------


def prepare_attachment(
    owner_id: str,
    *,
    now: float,
    ttl_seconds: int,
    max_per_owner: int,
    max_records: int,
    expected_owner_epoch: int | None = None,
) -> int:
    """Do a cheap capacity check before parsing and return the owner epoch."""
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        conn.execute(
            "DELETE FROM app_runtime_attachments WHERE created_at < ?",
            (now - ttl_seconds,),
        )
        owner_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM app_runtime_attachments WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()[0]
        )
        total_count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_attachments").fetchone()[0])
        if owner_count >= max_per_owner:
            raise RuntimeCapacityError("owner attachment capacity reached")
        if total_count >= max_records:
            raise RuntimeCapacityError("global attachment capacity reached")
        return _epoch(conn, owner_id, "attachment")


def insert_attachment(
    record: dict,
    *,
    expected_epoch: int,
    now: float,
    ttl_seconds: int,
    max_per_owner: int,
    max_records: int,
    expected_owner_epoch: int | None = None,
) -> None:
    owner_id = str(record["owner_id"])
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        _assert_epoch(conn, owner_id, "attachment", expected_epoch)
        conn.execute(
            "DELETE FROM app_runtime_attachments WHERE created_at < ?",
            (now - ttl_seconds,),
        )
        owner_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM app_runtime_attachments WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()[0]
        )
        total_count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_attachments").fetchone()[0])
        if owner_count >= max_per_owner:
            raise RuntimeCapacityError("owner attachment capacity reached")
        if total_count >= max_records:
            raise RuntimeCapacityError("global attachment capacity reached")
        conn.execute(
            """
            INSERT INTO app_runtime_attachments (
                attachment_id, owner_id, session_id, name, size, content_type,
                extracted_text, summary, category, char_count, truncated,
                template_structure, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["attachment_id"],
                owner_id,
                record["session_id"],
                record["name"],
                int(record["size"]),
                record["content_type"],
                record["extracted_text"],
                record["summary"],
                record["category"],
                int(record["char_count"]),
                int(bool(record["truncated"])),
                record["template_structure"],
                now,
            ),
        )


def load_attachments(
    owner_id: str,
    session_id: str,
    attachment_ids: list[str],
    *,
    now: float,
    ttl_seconds: int,
) -> dict[str, dict]:
    if not attachment_ids:
        return {}
    placeholders = ",".join("?" for _ in attachment_ids)
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM app_runtime_attachments WHERE created_at < ?",
            (now - ttl_seconds,),
        )
        rows = conn.execute(
            "SELECT * FROM app_runtime_attachments WHERE owner_id = ? AND session_id = ? "
            f"AND attachment_id IN ({placeholders})",
            (owner_id, session_id, *attachment_ids),
        ).fetchall()
        return {str(row["attachment_id"]): dict(row) for row in rows}


def remove_attachment(owner_id: str, session_id: str, attachment_id: str) -> bool:
    with _transaction() as conn:
        return bool(
            conn.execute(
                "DELETE FROM app_runtime_attachments WHERE attachment_id = ? AND owner_id = ? AND session_id = ?",
                (attachment_id, owner_id, session_id),
            ).rowcount
        )


def clear_owner_attachments(owner_id: str) -> int:
    return _clear_namespace("attachment", ("app_runtime_attachments",), owner_id)


def clear_session_attachments(owner_id: str, session_id: str) -> int:
    with _transaction() as conn:
        return conn.execute(
            "DELETE FROM app_runtime_attachments WHERE owner_id = ? AND session_id = ?",
            (owner_id, session_id),
        ).rowcount


def cleanup_attachments(*, now: float, ttl_seconds: int) -> int:
    with _transaction() as conn:
        return conn.execute(
            "DELETE FROM app_runtime_attachments WHERE created_at < ?",
            (now - ttl_seconds,),
        ).rowcount


# Template drafts -----------------------------------------------------------


def insert_draft(
    data: dict,
    *,
    expected_epoch: int,
    now: float,
    ttl_seconds: int,
    max_per_owner: int,
    max_records: int,
    expected_owner_epoch: int | None = None,
) -> None:
    owner_id = str(data["owner_id"])
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        _assert_epoch(conn, owner_id, "draft", expected_epoch)
        conn.execute(
            "DELETE FROM app_runtime_template_drafts WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        owner_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM app_runtime_template_drafts WHERE owner_id = ?",
                (owner_id,),
            ).fetchone()[0]
        )
        total_count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_template_drafts").fetchone()[0])
        if owner_count >= max_per_owner:
            raise RuntimeCapacityError("owner draft capacity reached")
        if total_count >= max_records:
            raise RuntimeCapacityError("global draft capacity reached")
        conn.execute(
            """
            INSERT INTO app_runtime_template_drafts (
                draft_id, owner_id, source_type, definition_json, source_template_id,
                source_template_revision, source_template_status, suggested_name, analysis_json,
                attachment_session_id, messages_json, revision, touched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["id"],
                owner_id,
                data["source_type"],
                _json(data["definition"]),
                data.get("source_template_id"),
                data.get("source_template_revision"),
                data.get("source_template_status", ""),
                data.get("suggested_name", ""),
                _json(data.get("analysis", {})),
                data.get("attachment_session_id", ""),
                _json(data.get("messages", [])),
                int(data.get("revision", 0)),
                now,
            ),
        )


def _draft_data(row: sqlite3.Row) -> dict:
    return {
        "id": row["draft_id"],
        "owner_id": row["owner_id"],
        "source_type": row["source_type"],
        "definition": json.loads(row["definition_json"]),
        "source_template_id": row["source_template_id"],
        "source_template_revision": row["source_template_revision"],
        "source_template_status": row["source_template_status"],
        "suggested_name": row["suggested_name"],
        "analysis": json.loads(row["analysis_json"]),
        "attachment_session_id": row["attachment_session_id"],
        "messages": json.loads(row["messages_json"]),
        "revision": int(row["revision"]),
        "touched_at": float(row["touched_at"]),
    }


def load_draft(
    owner_id: str,
    draft_id: str,
    *,
    now: float,
    ttl_seconds: int,
    touch: bool = True,
) -> Snapshot | None:
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM app_runtime_template_drafts WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        epoch = _epoch(conn, owner_id, "draft")
        row = conn.execute(
            "SELECT * FROM app_runtime_template_drafts WHERE draft_id = ? AND owner_id = ?",
            (draft_id, owner_id),
        ).fetchone()
        if not row:
            return None
        if touch:
            conn.execute(
                "UPDATE app_runtime_template_drafts SET touched_at = ? WHERE draft_id = ?",
                (now, draft_id),
            )
        data = _draft_data(row)
        data["touched_at"] = now if touch else data["touched_at"]
        return Snapshot(data=data, revision=int(row["revision"]), epoch=epoch)


def update_draft(
    owner_id: str,
    draft_id: str,
    *,
    definition: dict,
    messages: list[dict] | None,
    expected_revision: int,
    expected_epoch: int,
    now: float,
    expected_owner_epoch: int | None = None,
) -> Snapshot:
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        _assert_epoch(conn, owner_id, "draft", expected_epoch)
        row = conn.execute(
            "SELECT * FROM app_runtime_template_drafts WHERE draft_id = ? AND owner_id = ?",
            (draft_id, owner_id),
        ).fetchone()
        if not row:
            raise RuntimeConflictError("draft was removed")
        if int(row["revision"]) != expected_revision:
            raise RuntimeConflictError("draft revision changed")
        revision = expected_revision + 1
        next_messages = messages if messages is not None else json.loads(row["messages_json"])
        conn.execute(
            "UPDATE app_runtime_template_drafts SET definition_json = ?, messages_json = ?, "
            "revision = ?, touched_at = ? WHERE draft_id = ? AND owner_id = ? AND revision = ?",
            (
                _json(definition),
                _json(next_messages),
                revision,
                now,
                draft_id,
                owner_id,
                expected_revision,
            ),
        )
        updated = conn.execute("SELECT * FROM app_runtime_template_drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        return Snapshot(data=_draft_data(updated), revision=revision, epoch=expected_epoch)


def discard_draft(owner_id: str, draft_id: str) -> dict | None:
    with _transaction() as conn:
        row = conn.execute(
            "SELECT * FROM app_runtime_template_drafts WHERE draft_id = ? AND owner_id = ?",
            (draft_id, owner_id),
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "DELETE FROM app_runtime_template_drafts WHERE draft_id = ? AND owner_id = ?",
            (draft_id, owner_id),
        )
        return _draft_data(row)


def clear_owner_drafts(owner_id: str) -> int:
    return _clear_namespace("draft", ("app_runtime_template_drafts",), owner_id)


def cleanup_drafts(*, now: float, ttl_seconds: int) -> int:
    with _transaction() as conn:
        return conn.execute(
            "DELETE FROM app_runtime_template_drafts WHERE touched_at < ?",
            (now - ttl_seconds,),
        ).rowcount


# Custom-template conversations and bindings -------------------------------


def _custom_data(row: sqlite3.Row) -> dict:
    return {
        "template_id": int(row["template_id"]),
        "template_name": row["template_name"],
        "definition": json.loads(row["definition_json"]),
        "messages": json.loads(row["messages_json"]),
        "touched_at": float(row["touched_at"]),
    }


def load_custom_conversation(
    owner_id: str,
    session_id: str,
    *,
    now: float,
    ttl_seconds: int,
) -> Snapshot | None:
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM app_runtime_custom_conversations WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        epoch = _epoch(conn, owner_id, "custom")
        row = conn.execute(
            "SELECT * FROM app_runtime_custom_conversations WHERE owner_id = ? AND session_id = ?",
            (owner_id, session_id),
        ).fetchone()
        if not row:
            return None
        return Snapshot(data=_custom_data(row), revision=int(row["revision"]), epoch=epoch)


def save_custom_conversation(
    owner_id: str,
    session_id: str,
    state: dict,
    *,
    expected_revision: int | None,
    expected_epoch: int,
    now: float,
    ttl_seconds: int,
    max_per_owner: int,
    max_records: int,
    expected_owner_epoch: int | None = None,
) -> int:
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        _assert_epoch(conn, owner_id, "custom", expected_epoch)
        conn.execute(
            "DELETE FROM app_runtime_custom_conversations WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        row = conn.execute(
            "SELECT revision FROM app_runtime_custom_conversations WHERE owner_id = ? AND session_id = ?",
            (owner_id, session_id),
        ).fetchone()
        values = (
            int(state["template_id"]),
            state["template_name"],
            _json(state["definition"]),
            _json(state["messages"]),
            now,
        )
        if row is None:
            if expected_revision is not None:
                raise RuntimeConflictError("custom conversation was removed")
            owner_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM app_runtime_custom_conversations WHERE owner_id = ?",
                    (owner_id,),
                ).fetchone()[0]
            )
            total_count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_custom_conversations").fetchone()[0])
            if owner_count >= max_per_owner:
                raise RuntimeCapacityError("owner custom conversation capacity reached")
            if total_count >= max_records:
                raise RuntimeCapacityError("global custom conversation capacity reached")
            conn.execute(
                "INSERT INTO app_runtime_custom_conversations "
                "(owner_id, session_id, template_id, template_name, definition_json, "
                "messages_json, revision, touched_at) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
                (owner_id, session_id, *values),
            )
            return 0
        revision = int(row["revision"])
        if expected_revision != revision:
            raise RuntimeConflictError("custom conversation revision changed")
        revision += 1
        conn.execute(
            "UPDATE app_runtime_custom_conversations SET template_id = ?, template_name = ?, "
            "definition_json = ?, messages_json = ?, touched_at = ?, revision = ? "
            "WHERE owner_id = ? AND session_id = ?",
            (*values, revision, owner_id, session_id),
        )
        return revision


def delete_custom_conversation(owner_id: str, session_id: str) -> bool:
    with _transaction() as conn:
        return bool(
            conn.execute(
                "DELETE FROM app_runtime_custom_conversations WHERE owner_id = ? AND session_id = ?",
                (owner_id, session_id),
            ).rowcount
        )


def bind_session_template(
    owner_id: str,
    session_id: str,
    template_id: int,
    *,
    now: float,
    ttl_seconds: int,
    max_per_owner: int,
    max_records: int,
    expected_owner_epoch: int | None = None,
) -> bool:
    with _transaction() as conn:
        _assert_owner_epoch(conn, owner_id, expected_owner_epoch)
        conn.execute(
            "DELETE FROM app_runtime_session_templates WHERE touched_at < ?",
            (now - ttl_seconds,),
        )
        row = conn.execute(
            "SELECT template_id FROM app_runtime_session_templates WHERE owner_id = ? AND session_id = ?",
            (owner_id, session_id),
        ).fetchone()
        if row and int(row["template_id"]) != template_id:
            return False
        if row is None:
            owner_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM app_runtime_session_templates WHERE owner_id = ?",
                    (owner_id,),
                ).fetchone()[0]
            )
            if owner_count >= max_per_owner:
                raise RuntimeCapacityError("owner session binding capacity reached")
            total_count = int(conn.execute("SELECT COUNT(*) FROM app_runtime_session_templates").fetchone()[0])
            if total_count >= max_records:
                raise RuntimeCapacityError("global session binding capacity reached")
        conn.execute(
            "INSERT INTO app_runtime_session_templates "
            "(owner_id, session_id, template_id, touched_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(owner_id, session_id) DO UPDATE SET touched_at = excluded.touched_at",
            (owner_id, session_id, template_id, now),
        )
        return True


def clear_custom_conversations(owner_id: str | None = None) -> int:
    return _clear_namespace(
        "custom",
        ("app_runtime_custom_conversations", "app_runtime_session_templates"),
        owner_id,
    )


def cleanup_custom_conversations(*, now: float, ttl_seconds: int) -> int:
    with _transaction() as conn:
        removed = conn.execute(
            "DELETE FROM app_runtime_custom_conversations WHERE touched_at < ?",
            (now - ttl_seconds,),
        ).rowcount
        removed += conn.execute(
            "DELETE FROM app_runtime_session_templates WHERE touched_at < ?",
            (now - ttl_seconds,),
        ).rowcount
        return removed


# Cross-process leases ------------------------------------------------------


class SessionLease:
    def __init__(
        self,
        namespace: str,
        owner_id: str,
        session_id: str,
        holder: str,
        ttl_seconds: float,
    ) -> None:
        self.namespace = namespace
        self.owner_id = owner_id
        self.session_id = session_id
        self.holder = holder
        self.ttl_seconds = ttl_seconds
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    def start_heartbeat(self) -> None:
        interval = max(1.0, self.ttl_seconds / 3)

        def heartbeat() -> None:
            while not self._stop.wait(interval):
                try:
                    if not _renew_lease(self):
                        self._lost.set()
                        return
                except sqlite3.Error:
                    # A transient busy database is retried before the lease TTL.
                    continue

        self._thread = threading.Thread(
            target=heartbeat,
            name=f"runtime-lease-{self.namespace}",
            daemon=True,
        )
        self._thread.start()

    def ensure_owned(self) -> None:
        if self._lost.is_set() or not _lease_is_owned(self):
            self._lost.set()
            raise RuntimeBusyError("session lease was lost")

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        _release_lease(self)


def _try_acquire_lease(lease: SessionLease) -> bool:
    now = time.time()
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM app_runtime_leases WHERE expires_at <= ?",
            (now,),
        )
        cursor = conn.execute(
            "INSERT INTO app_runtime_leases "
            "(namespace, owner_id, session_id, holder, expires_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(namespace, owner_id, session_id) DO UPDATE SET "
            "holder = excluded.holder, expires_at = excluded.expires_at "
            "WHERE app_runtime_leases.expires_at <= ? OR app_runtime_leases.holder = excluded.holder",
            (
                lease.namespace,
                lease.owner_id,
                lease.session_id,
                lease.holder,
                now + lease.ttl_seconds,
                now,
            ),
        )
        return cursor.rowcount == 1


def _renew_lease(lease: SessionLease) -> bool:
    with _transaction() as conn:
        return bool(
            conn.execute(
                "UPDATE app_runtime_leases SET expires_at = ? WHERE namespace = ? "
                "AND owner_id = ? AND session_id = ? AND holder = ?",
                (
                    time.time() + lease.ttl_seconds,
                    lease.namespace,
                    lease.owner_id,
                    lease.session_id,
                    lease.holder,
                ),
            ).rowcount
        )


def _lease_is_owned(lease: SessionLease) -> bool:
    conn = _connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM app_runtime_leases WHERE namespace = ? AND owner_id = ? "
            "AND session_id = ? AND holder = ? AND expires_at > ?",
            (
                lease.namespace,
                lease.owner_id,
                lease.session_id,
                lease.holder,
                time.time(),
            ),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _release_lease(lease: SessionLease) -> None:
    with _transaction() as conn:
        conn.execute(
            "DELETE FROM app_runtime_leases WHERE namespace = ? AND owner_id = ? AND session_id = ? AND holder = ?",
            (lease.namespace, lease.owner_id, lease.session_id, lease.holder),
        )


@contextmanager
def session_lease(
    namespace: str,
    owner_id: str,
    session_id: str,
    *,
    ttl_seconds: float = 30,
    wait_seconds: float = 1,
) -> Iterator[SessionLease]:
    lease = SessionLease(
        namespace,
        owner_id,
        session_id,
        secrets.token_urlsafe(18),
        ttl_seconds,
    )
    deadline = time.monotonic() + max(0, wait_seconds)
    while not _try_acquire_lease(lease):
        if time.monotonic() >= deadline:
            raise RuntimeBusyError("session is already active")
        time.sleep(0.05)
    lease.start_heartbeat()
    try:
        yield lease
    finally:
        lease.close()
