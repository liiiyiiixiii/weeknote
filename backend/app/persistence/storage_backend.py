"""SQLite 存储：按匿名访客隔离数据，并原子记录每日用量。"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from app.core.config import BACKEND_DIR, AppSettings

SETTINGS = AppSettings.from_env()
DB_PATH = Path(SETTINGS.app_db_path) if SETTINGS.app_db_path else BACKEND_DIR / "data.db"


class RuntimeStateConflictError(RuntimeError):
    """A privacy clear invalidated an in-flight workflow before a durable write."""


_WEEKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS visitor_weeks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    week_start TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
    raw_input TEXT NOT NULL,
    report_json TEXT NOT NULL DEFAULT '{}',
    output_kind TEXT NOT NULL DEFAULT 'weekly',
    template_id INTEGER,
    template_name TEXT NOT NULL DEFAULT '',
    template_definition_json TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(owner_id, week_start, version)
)
"""


_TEMPLATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS custom_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL DEFAULT 'active',
    definition_json TEXT NOT NULL,
    analysis_summary_json TEXT NOT NULL DEFAULT '{}',
    legacy_source_key TEXT NOT NULL DEFAULT '',
    revision INTEGER NOT NULL DEFAULT 1 CHECK(revision > 0),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK(source_type IN ('manual', 'learned', 'legacy')),
    CHECK(status IN ('draft', 'active'))
)
"""


_LEGACY_GLOBAL_MIGRATION = "legacy-global-tables-v1"


_MIGRATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL DEFAULT '',
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""


_LEGACY_MIGRATION_MAP_SQL = """
CREATE TABLE IF NOT EXISTS legacy_migration_map (
    migration_name TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_key TEXT NOT NULL,
    target_table TEXT NOT NULL,
    target_key TEXT NOT NULL,
    disposition TEXT NOT NULL,
    migrated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY(migration_name, source_table, source_key)
)
"""


def _conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _enable_wal(conn: sqlite3.Connection) -> None:
    """Enable WAL despite simultaneous imports from multiple Uvicorn workers."""
    for attempt in range(40):
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 39:
                raise
            time.sleep(0.05)


def _ensure_week_version_schema(conn) -> None:
    """把早期“每周只能有一条”的表原地迁移为可保留多版本的表。"""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(visitor_weeks)").fetchall()}
    if not columns or "version" in columns:
        return
    conn.execute("ALTER TABLE visitor_weeks RENAME TO visitor_weeks_legacy")
    conn.execute(_WEEKS_TABLE_SQL)
    conn.execute(
        """
        INSERT INTO visitor_weeks (
            id, owner_id, week_start, version, raw_input, report_json, created_at, updated_at
        )
        SELECT id, owner_id, week_start, 1, raw_input, report_json, created_at, updated_at
        FROM visitor_weeks_legacy
        """
    )
    conn.execute("DROP TABLE visitor_weeks_legacy")


def _ensure_column(conn, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _table_exists(conn, table: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone() is not None
    )


def _assert_runtime_epoch(
    conn: sqlite3.Connection,
    owner_id: str,
    namespace: str,
    expected_epoch: int | None,
) -> None:
    """Validate a runtime namespace while holding the durable write lock."""
    if expected_epoch is None:
        return
    actual_epoch = 0
    if _table_exists(conn, "app_runtime_owner_epochs"):
        row = conn.execute(
            "SELECT epoch FROM app_runtime_owner_epochs WHERE owner_id = ? AND namespace = ?",
            (owner_id, namespace),
        ).fetchone()
        if row:
            actual_epoch = int(row["epoch"])
    if actual_epoch != expected_epoch:
        raise RuntimeStateConflictError("运行中的请求已被数据清除操作取消")


def _assert_runtime_draft(
    conn: sqlite3.Connection,
    owner_id: str,
    draft_id: str,
    expected_revision: int,
    expected_epoch: int,
) -> None:
    _assert_runtime_epoch(conn, owner_id, "draft", expected_epoch)
    if not _table_exists(conn, "app_runtime_template_drafts"):
        raise RuntimeStateConflictError("模板草稿不存在或已经失效")
    row = conn.execute(
        "SELECT revision FROM app_runtime_template_drafts WHERE owner_id = ? AND draft_id = ?",
        (owner_id, draft_id),
    ).fetchone()
    if not row or int(row["revision"]) != expected_revision:
        raise RuntimeStateConflictError("模板草稿已在其他页面或请求中更新")


def _consume_runtime_draft(
    conn: sqlite3.Connection,
    owner_id: str,
    draft_id: str,
    expected_revision: int,
) -> None:
    removed = conn.execute(
        "DELETE FROM app_runtime_template_drafts WHERE owner_id = ? AND draft_id = ? AND revision = ?",
        (owner_id, draft_id, expected_revision),
    )
    if removed.rowcount != 1:
        raise RuntimeStateConflictError("模板草稿已在其他页面或请求中更新")


def _legacy_owner_id(conn) -> str:
    """Resolve the anonymous owner that receives data from the old single-user tables."""
    configured = AppSettings.from_env().app_legacy_owner_id
    if configured:
        return configured

    rows = conn.execute(
        "SELECT owner_id FROM visitor_settings "
        "UNION SELECT owner_id FROM visitor_weeks "
        "UNION SELECT owner_id FROM custom_templates"
    ).fetchall()
    owners = [str(row["owner_id"]) for row in rows if row["owner_id"]]
    if len(owners) == 1:
        return owners[0]
    if not owners:
        raise RuntimeError("旧版全局数据没有可映射的匿名访客；请设置 APP_LEGACY_OWNER_ID 后重试")
    raise RuntimeError("旧版全局数据对应多个匿名访客；请设置 APP_LEGACY_OWNER_ID 明确迁移目标")


def _record_legacy_mapping(
    conn,
    source_table: str,
    source_key: str,
    target_table: str,
    target_key: str,
    disposition: str,
) -> None:
    conn.execute(
        "INSERT INTO legacy_migration_map ("
        "migration_name, source_table, source_key, target_table, target_key, disposition"
        ") VALUES (?, ?, ?, ?, ?, ?)",
        (
            _LEGACY_GLOBAL_MIGRATION,
            source_table,
            source_key,
            target_table,
            target_key,
            disposition,
        ),
    )


def _migrate_legacy_week(conn, owner_id: str, row: sqlite3.Row) -> None:
    exact = conn.execute(
        "SELECT id FROM visitor_weeks WHERE owner_id = ? AND week_start = ? "
        "AND raw_input = ? AND report_json = ? AND created_at = ? AND updated_at = ?",
        (
            owner_id,
            row["week_start"],
            row["raw_input"],
            row["report_json"],
            row["created_at"],
            row["updated_at"],
        ),
    ).fetchone()
    if exact:
        _record_legacy_mapping(
            conn,
            "weeks",
            str(row["id"]),
            "visitor_weeks",
            str(exact["id"]),
            "matched-existing",
        )
        return

    version = int(
        conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS version FROM visitor_weeks WHERE owner_id = ? AND week_start = ?",
            (owner_id, row["week_start"]),
        ).fetchone()["version"]
    )
    id_available = conn.execute("SELECT 1 FROM visitor_weeks WHERE id = ?", (row["id"],)).fetchone() is None
    columns = "owner_id, week_start, version, raw_input, report_json, created_at, updated_at"
    values = (
        owner_id,
        row["week_start"],
        version,
        row["raw_input"],
        row["report_json"],
        row["created_at"],
        row["updated_at"],
    )
    if id_available:
        cur = conn.execute(
            f"INSERT INTO visitor_weeks (id, {columns}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (row["id"], *values),
        )
    else:
        cur = conn.execute(f"INSERT INTO visitor_weeks ({columns}) VALUES (?, ?, ?, ?, ?, ?, ?)", values)
    _record_legacy_mapping(
        conn,
        "weeks",
        str(row["id"]),
        "visitor_weeks",
        str(cur.lastrowid),
        "inserted",
    )


def _migrate_legacy_settings(conn, owner_id: str, row: sqlite3.Row) -> None:
    existing = conn.execute("SELECT 1 FROM visitor_settings WHERE owner_id = ?", (owner_id,)).fetchone()
    if existing:
        disposition = "preserved-target"
    else:
        conn.execute(
            """
            INSERT INTO visitor_settings (
                owner_id, week_one_start, purpose_mode, custom_purpose_name,
                custom_purpose_description, detail_level, tone,
                onboarding_completed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                row["week_one_start"],
                row["purpose_mode"],
                row["custom_purpose_name"],
                row["custom_purpose_description"],
                row["detail_level"],
                row["tone"],
                row["onboarding_completed"],
                row["updated_at"],
            ),
        )
        disposition = "inserted"
    _record_legacy_mapping(
        conn,
        "user_settings",
        str(row["id"]),
        "visitor_settings",
        owner_id,
        disposition,
    )


def _migrate_legacy_global_tables(conn) -> None:
    """Migrate the pre-visitor single-user tables once, without deleting source data."""
    if conn.execute("SELECT 1 FROM schema_migrations WHERE name = ?", (_LEGACY_GLOBAL_MIGRATION,)).fetchone():
        return

    week_rows = conn.execute("SELECT * FROM weeks ORDER BY id").fetchall() if _table_exists(conn, "weeks") else []
    settings_rows = (
        conn.execute("SELECT * FROM user_settings ORDER BY id").fetchall()
        if _table_exists(conn, "user_settings")
        else []
    )
    owner_id = _legacy_owner_id(conn) if week_rows or settings_rows else ""
    for row in week_rows:
        _migrate_legacy_week(conn, owner_id, row)
    for row in settings_rows:
        _migrate_legacy_settings(conn, owner_id, row)
    conn.execute(
        "INSERT INTO schema_migrations(name, owner_id) VALUES (?, ?)",
        (_LEGACY_GLOBAL_MIGRATION, owner_id),
    )


def _legacy_template_definition(description: str) -> dict:
    return {
        "version": 1,
        "title_pattern": "第 {week_number} 周自定义汇报（{date_range}）",
        "sections": [
            {
                "id": "legacy_main",
                "title": "主要内容",
                "description": "由旧版自定义用途迁移，请确认结构后再使用。",
                "blocks": [
                    {
                        "id": "legacy_content",
                        "type": "paragraph",
                        "label": "汇报内容",
                        "instruction": description[:500],
                        "required": True,
                        "columns": [],
                    }
                ],
            }
        ],
    }


def _migrate_legacy_custom_settings(conn) -> None:
    rows = conn.execute(
        "SELECT owner_id, custom_purpose_name, custom_purpose_description "
        "FROM visitor_settings WHERE purpose_mode = 'custom'"
    ).fetchall()
    for row in rows:
        exists = conn.execute(
            "SELECT 1 FROM custom_templates WHERE owner_id = ? AND legacy_source_key = ?",
            (row["owner_id"], "settings-v1"),
        ).fetchone()
        if exists:
            conn.execute(
                "UPDATE visitor_settings SET purpose_mode = 'default' WHERE owner_id = ?",
                (row["owner_id"],),
            )
            continue
        name = (row["custom_purpose_name"] or "旧版自定义模板").strip()[:30]
        description = (row["custom_purpose_description"] or "请根据用户提供的内容整理汇报。").strip()
        conn.execute(
            "INSERT INTO custom_templates "
            "(owner_id, name, source_type, status, definition_json, legacy_source_key) "
            "VALUES (?, ?, 'legacy', 'draft', ?, 'settings-v1')",
            (row["owner_id"], name, json.dumps(_legacy_template_definition(description), ensure_ascii=False)),
        )
        conn.execute(
            "UPDATE visitor_settings SET purpose_mode = 'default' WHERE owner_id = ?",
            (row["owner_id"],),
        )


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = _conn()
    try:
        _enable_wal(conn)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(_WEEKS_TABLE_SQL)
        _ensure_week_version_schema(conn)
        _ensure_column(conn, "visitor_weeks", "output_kind", "TEXT NOT NULL DEFAULT 'weekly'")
        _ensure_column(conn, "visitor_weeks", "template_id", "INTEGER")
        _ensure_column(conn, "visitor_weeks", "template_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "visitor_weeks", "template_definition_json", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visitor_settings (
                owner_id TEXT PRIMARY KEY,
                week_one_start TEXT NOT NULL,
                purpose_mode TEXT NOT NULL DEFAULT 'default',
                custom_purpose_name TEXT NOT NULL DEFAULT '',
                custom_purpose_description TEXT NOT NULL DEFAULT '',
                detail_level TEXT NOT NULL DEFAULT 'standard',
                tone TEXT NOT NULL DEFAULT 'natural',
                onboarding_completed INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )
            """
        )
        _ensure_column(conn, "visitor_settings", "selected_template_id", "INTEGER")
        conn.execute(_TEMPLATES_TABLE_SQL)
        _ensure_column(conn, "custom_templates", "revision", "INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_usage (
                identity_hash TEXT NOT NULL,
                usage_day TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0 CHECK(message_count >= 0),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY(identity_hash, usage_day)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_asr_usage (
                identity_hash TEXT NOT NULL,
                usage_day TEXT NOT NULL,
                audio_seconds INTEGER NOT NULL DEFAULT 0 CHECK(audio_seconds >= 0),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY(identity_hash, usage_day)
            )
            """
        )
        conn.execute(_MIGRATIONS_TABLE_SQL)
        conn.execute(_LEGACY_MIGRATION_MAP_SQL)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_visitor_weeks_owner_start "
            "ON visitor_weeks(owner_id, week_start DESC, version DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_templates_owner_status "
            "ON custom_templates(owner_id, status, created_at, id)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_templates_owner_active_name "
            "ON custom_templates(owner_id, name COLLATE NOCASE) WHERE status = 'active'"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_custom_templates_legacy_source "
            "ON custom_templates(owner_id, legacy_source_key) WHERE legacy_source_key != ''"
        )
        _migrate_legacy_global_tables(conn)
        _migrate_legacy_custom_settings(conn)
        conn.execute("PRAGMA optimize")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def create_week(
    owner_id,
    week_start,
    raw_input,
    report_json,
    *,
    output_kind="weekly",
    template_id=None,
    template_name="",
    template_definition_json="",
    expected_runtime_namespace: str = "",
    expected_runtime_epoch: int | None = None,
    expected_owner_epoch: int | None = None,
):
    """为指定周创建不可覆盖的新版本，返回新记录 id。"""
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _assert_runtime_epoch(conn, owner_id, "owner", expected_owner_epoch)
        if expected_runtime_namespace:
            _assert_runtime_epoch(
                conn,
                owner_id,
                expected_runtime_namespace,
                expected_runtime_epoch,
            )
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 AS next_version "
            "FROM visitor_weeks WHERE owner_id = ? AND week_start = ?",
            (owner_id, week_start),
        ).fetchone()
        version = int(row["next_version"])
        cur = conn.execute(
            "INSERT INTO visitor_weeks ("
            "owner_id, week_start, version, raw_input, report_json, output_kind, "
            "template_id, template_name, template_definition_json"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                owner_id,
                week_start,
                version,
                raw_input,
                report_json,
                output_kind,
                template_id,
                template_name,
                template_definition_json,
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_weeks(owner_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, week_start, version, updated_at, output_kind, template_id, template_name, "
            "COUNT(*) OVER (PARTITION BY week_start) AS version_count "
            "FROM visitor_weeks WHERE owner_id = ? "
            "ORDER BY week_start DESC, version DESC",
            (owner_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_week(owner_id, week_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT w.*, (SELECT COUNT(*) FROM visitor_weeks siblings "
            "WHERE siblings.owner_id = w.owner_id AND siblings.week_start = w.week_start) "
            "AS version_count FROM visitor_weeks w WHERE w.id = ? AND w.owner_id = ?",
            (week_id, owner_id),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_week(owner_id: str, week_id: int) -> bool:
    conn = _conn()
    try:
        deleted = conn.execute("DELETE FROM visitor_weeks WHERE id = ? AND owner_id = ?", (week_id, owner_id))
        conn.commit()
        return deleted.rowcount == 1
    finally:
        conn.close()


def delete_owner_data(owner_id: str) -> dict[str, int]:
    """删除匿名访客的周报与设置；按 IP 统计的额度不与访客身份关联。"""
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        weeks = conn.execute("DELETE FROM visitor_weeks WHERE owner_id = ?", (owner_id,)).rowcount
        templates = conn.execute("DELETE FROM custom_templates WHERE owner_id = ?", (owner_id,)).rowcount
        settings = conn.execute("DELETE FROM visitor_settings WHERE owner_id = ?", (owner_id,)).rowcount
        conn.commit()
        return {"weeks": weeks, "templates": templates, "settings": settings}
    finally:
        conn.close()


def get_settings(owner_id):
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM visitor_settings WHERE owner_id = ?", (owner_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def save_settings(
    owner_id,
    settings: dict,
    *,
    expected_owner_epoch: int | None = None,
):
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _assert_runtime_epoch(conn, owner_id, "owner", expected_owner_epoch)
        conn.execute(
            """
            INSERT INTO visitor_settings (
                owner_id, week_one_start, purpose_mode, custom_purpose_name,
                custom_purpose_description, detail_level, tone,
                onboarding_completed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
            ON CONFLICT(owner_id) DO UPDATE SET
                week_one_start = excluded.week_one_start,
                purpose_mode = excluded.purpose_mode,
                custom_purpose_name = excluded.custom_purpose_name,
                custom_purpose_description = excluded.custom_purpose_description,
                detail_level = excluded.detail_level,
                tone = excluded.tone,
                onboarding_completed = excluded.onboarding_completed,
                updated_at = excluded.updated_at
            """,
            (
                owner_id,
                settings["week_one_start"],
                settings["purpose_mode"],
                settings.get("custom_purpose_name", ""),
                settings.get("custom_purpose_description", ""),
                settings["detail_level"],
                settings["tone"],
                1 if settings.get("onboarding_completed", True) else 0,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM visitor_settings WHERE owner_id = ?", (owner_id,)).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_templates(owner_id: str, *, include_drafts: bool = True) -> list[dict]:
    conn = _conn()
    try:
        where = "owner_id = ?" if include_drafts else "owner_id = ? AND status = 'active'"
        rows = conn.execute(
            "SELECT * FROM custom_templates WHERE "
            + where
            + " ORDER BY CASE status WHEN 'active' THEN 0 ELSE 1 END, created_at, id",
            (owner_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_template(owner_id: str, template_id: int, *, active_only: bool = False) -> dict | None:
    conn = _conn()
    try:
        sql = "SELECT * FROM custom_templates WHERE id = ? AND owner_id = ?"
        if active_only:
            sql += " AND status = 'active'"
        row = conn.execute(sql, (template_id, owner_id)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def active_template_count(owner_id: str) -> int:
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM custom_templates WHERE owner_id = ? AND status = 'active'",
            (owner_id,),
        ).fetchone()
        return int(row["count"])
    finally:
        conn.close()


def create_template(
    owner_id: str,
    name: str,
    source_type: str,
    definition_json: str,
    analysis_summary_json: str = "{}",
    *,
    expected_runtime_epoch: int | None = None,
    runtime_draft_id: str = "",
    expected_draft_revision: int | None = None,
) -> dict:
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if runtime_draft_id:
            if expected_runtime_epoch is None or expected_draft_revision is None:
                raise ValueError("保存模板时缺少草稿版本")
            _assert_runtime_draft(
                conn,
                owner_id,
                runtime_draft_id,
                expected_draft_revision,
                expected_runtime_epoch,
            )
        else:
            _assert_runtime_epoch(conn, owner_id, "draft", expected_runtime_epoch)
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM custom_templates WHERE owner_id = ? AND status = 'active'",
            (owner_id,),
        ).fetchone()
        if int(row["count"]) >= 20:
            raise ValueError("最多只能保存 20 个自定义模板")
        cur = conn.execute(
            "INSERT INTO custom_templates "
            "(owner_id, name, source_type, status, definition_json, analysis_summary_json) "
            "VALUES (?, ?, ?, 'active', ?, ?)",
            (owner_id, name, source_type, definition_json, analysis_summary_json),
        )
        if runtime_draft_id:
            _consume_runtime_draft(conn, owner_id, runtime_draft_id, expected_draft_revision)
        created = conn.execute(
            "SELECT * FROM custom_templates WHERE id = ? AND owner_id = ?",
            (cur.lastrowid, owner_id),
        ).fetchone()
        conn.commit()
        return dict(created)
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("模板名称已存在") from exc
    finally:
        conn.close()


def activate_legacy_template(
    owner_id: str,
    template_id: int,
    name: str,
    definition_json: str,
    *,
    expected_revision: int,
    runtime_draft_id: str = "",
    expected_draft_revision: int | None = None,
    expected_runtime_epoch: int | None = None,
) -> dict | None:
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if runtime_draft_id:
            if expected_runtime_epoch is None or expected_draft_revision is None:
                raise ValueError("保存模板时缺少草稿版本")
            _assert_runtime_draft(
                conn,
                owner_id,
                runtime_draft_id,
                expected_draft_revision,
                expected_runtime_epoch,
            )
        row = conn.execute(
            "SELECT id FROM custom_templates WHERE id = ? AND owner_id = ? AND status = 'draft' AND revision = ?",
            (template_id, owner_id, expected_revision),
        ).fetchone()
        if not row:
            conn.rollback()
            return None
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM custom_templates WHERE owner_id = ? AND status = 'active'",
            (owner_id,),
        ).fetchone()
        if int(count["count"]) >= 20:
            raise ValueError("最多只能保存 20 个自定义模板")
        conn.execute(
            "UPDATE custom_templates SET name = ?, definition_json = ?, status = 'active', "
            "revision = revision + 1, updated_at = datetime('now') "
            "WHERE id = ? AND owner_id = ? AND revision = ?",
            (name, definition_json, template_id, owner_id, expected_revision),
        )
        if runtime_draft_id:
            _consume_runtime_draft(conn, owner_id, runtime_draft_id, expected_draft_revision)
        updated = conn.execute(
            "SELECT * FROM custom_templates WHERE id = ? AND owner_id = ?",
            (template_id, owner_id),
        ).fetchone()
        conn.commit()
        return dict(updated)
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("模板名称已存在") from exc
    finally:
        conn.close()


def update_template(
    owner_id: str,
    template_id: int,
    name: str,
    definition_json: str,
    *,
    expected_revision: int,
    runtime_draft_id: str = "",
    expected_draft_revision: int | None = None,
    expected_runtime_epoch: int | None = None,
) -> dict | None:
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if runtime_draft_id:
            if expected_runtime_epoch is None or expected_draft_revision is None:
                raise ValueError("保存模板时缺少草稿版本")
            _assert_runtime_draft(
                conn,
                owner_id,
                runtime_draft_id,
                expected_draft_revision,
                expected_runtime_epoch,
            )
        cur = conn.execute(
            "UPDATE custom_templates SET name = ?, definition_json = ?, "
            "revision = revision + 1, updated_at = datetime('now') "
            "WHERE id = ? AND owner_id = ? AND status = 'active' AND revision = ?",
            (name, definition_json, template_id, owner_id, expected_revision),
        )
        if cur.rowcount and runtime_draft_id:
            _consume_runtime_draft(conn, owner_id, runtime_draft_id, expected_draft_revision)
        updated = (
            conn.execute(
                "SELECT * FROM custom_templates WHERE id = ? AND owner_id = ?",
                (template_id, owner_id),
            ).fetchone()
            if cur.rowcount
            else None
        )
        conn.commit()
        return dict(updated) if updated else None
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("模板名称已存在") from exc
    finally:
        conn.close()


def rename_template(owner_id: str, template_id: int, name: str) -> dict | None:
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE custom_templates SET name = ?, revision = revision + 1, "
            "updated_at = datetime('now') "
            "WHERE id = ? AND owner_id = ? AND status = 'active'",
            (name, template_id, owner_id),
        )
        updated = (
            conn.execute(
                "SELECT * FROM custom_templates WHERE id = ? AND owner_id = ?",
                (template_id, owner_id),
            ).fetchone()
            if cur.rowcount
            else None
        )
        conn.commit()
        return dict(updated) if updated else None
    except sqlite3.IntegrityError as exc:
        raise ValueError("模板名称已存在") from exc
    finally:
        conn.close()


def delete_template(owner_id: str, template_id: int) -> bool:
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        deleted = conn.execute(
            "DELETE FROM custom_templates WHERE id = ? AND owner_id = ?",
            (template_id, owner_id),
        )
        if deleted.rowcount:
            conn.execute(
                "UPDATE visitor_settings SET selected_template_id = NULL "
                "WHERE owner_id = ? AND selected_template_id = ?",
                (owner_id, template_id),
            )
        conn.commit()
        return deleted.rowcount == 1
    finally:
        conn.close()


def save_template_selection(owner_id: str, template_id: int | None) -> dict | None:
    conn = _conn()
    try:
        if template_id is not None:
            row = conn.execute(
                "SELECT 1 FROM custom_templates WHERE id = ? AND owner_id = ? AND status = 'active'",
                (template_id, owner_id),
            ).fetchone()
            if not row:
                return None
        cur = conn.execute(
            "UPDATE visitor_settings SET selected_template_id = ?, updated_at = datetime('now','localtime') "
            "WHERE owner_id = ?",
            (template_id, owner_id),
        )
        conn.commit()
        return get_settings(owner_id) if cur.rowcount else None
    finally:
        conn.close()


def earliest_week_start(owner_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT MIN(week_start) AS week_start FROM visitor_weeks WHERE owner_id = ?",
            (owner_id,),
        ).fetchone()
        return row["week_start"] if row and row["week_start"] else None
    finally:
        conn.close()


def consume_daily_message(identity_hash: str, usage_day: str, limit: int) -> tuple[bool, int]:
    """原子消耗一次额度，返回 (是否允许, 当日已用次数)。"""
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO daily_usage(identity_hash, usage_day, message_count) VALUES (?, ?, 0)",
            (identity_hash, usage_day),
        )
        updated = conn.execute(
            "UPDATE daily_usage SET message_count = message_count + 1, updated_at = datetime('now') "
            "WHERE identity_hash = ? AND usage_day = ? AND message_count < ?",
            (identity_hash, usage_day, limit),
        )
        row = conn.execute(
            "SELECT message_count FROM daily_usage WHERE identity_hash = ? AND usage_day = ?",
            (identity_hash, usage_day),
        ).fetchone()
        conn.commit()
        return updated.rowcount == 1, int(row["message_count"])
    finally:
        conn.close()


def reserve_daily_asr(identity_hash: str, usage_day: str, reserve_seconds: int, limit_seconds: int) -> tuple[bool, int]:
    """原子预留一次语音会话的最长时长，结束后由 release_daily_asr 退回未使用部分。"""
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO daily_asr_usage(identity_hash, usage_day, audio_seconds) VALUES (?, ?, 0)",
            (identity_hash, usage_day),
        )
        updated = conn.execute(
            "UPDATE daily_asr_usage SET audio_seconds = audio_seconds + ?, updated_at = datetime('now') "
            "WHERE identity_hash = ? AND usage_day = ? AND audio_seconds + ? <= ?",
            (reserve_seconds, identity_hash, usage_day, reserve_seconds, limit_seconds),
        )
        row = conn.execute(
            "SELECT audio_seconds FROM daily_asr_usage WHERE identity_hash = ? AND usage_day = ?",
            (identity_hash, usage_day),
        ).fetchone()
        conn.commit()
        return updated.rowcount == 1, int(row["audio_seconds"])
    finally:
        conn.close()


def release_daily_asr(identity_hash: str, usage_day: str, seconds: int) -> int:
    """退回预留但未实际使用的语音秒数，返回当前已用秒数。"""
    seconds = max(0, int(seconds))
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "UPDATE daily_asr_usage SET audio_seconds = MAX(0, audio_seconds - ?), "
            "updated_at = datetime('now') WHERE identity_hash = ? AND usage_day = ?",
            (seconds, identity_hash, usage_day),
        )
        row = conn.execute(
            "SELECT audio_seconds FROM daily_asr_usage WHERE identity_hash = ? AND usage_day = ?",
            (identity_hash, usage_day),
        ).fetchone()
        conn.commit()
        return int(row["audio_seconds"]) if row else 0
    finally:
        conn.close()


def cleanup_expired(report_retention_days: int, usage_retention_days: int) -> dict[str, int]:
    """按配置的数据保留期清理内容；0 表示该类数据不自动删除。"""
    report_retention_days = max(0, int(report_retention_days))
    usage_retention_days = max(0, int(usage_retention_days))
    removed = {"weeks": 0, "settings": 0, "message_usage": 0, "asr_usage": 0}
    conn = _conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        if report_retention_days:
            removed["weeks"] = conn.execute(
                "DELETE FROM visitor_weeks WHERE updated_at < datetime('now', ?)",
                (f"-{report_retention_days} days",),
            ).rowcount
            removed["settings"] = conn.execute(
                "DELETE FROM visitor_settings WHERE updated_at < datetime('now', ?) "
                "AND NOT EXISTS (SELECT 1 FROM visitor_weeks "
                "WHERE visitor_weeks.owner_id = visitor_settings.owner_id) "
                "AND NOT EXISTS (SELECT 1 FROM custom_templates "
                "WHERE custom_templates.owner_id = visitor_settings.owner_id)",
                (f"-{report_retention_days} days",),
            ).rowcount
        if usage_retention_days:
            modifier = f"-{usage_retention_days} days"
            removed["message_usage"] = conn.execute(
                "DELETE FROM daily_usage WHERE usage_day < date('now', ?)", (modifier,)
            ).rowcount
            removed["asr_usage"] = conn.execute(
                "DELETE FROM daily_asr_usage WHERE usage_day < date('now', ?)", (modifier,)
            ).rowcount
        conn.commit()
        return removed
    finally:
        conn.close()


_LEGACY_ATTACHMENT_MARKER = "以下内容来自用户主动上传的附件"


def legacy_attachment_context_count(owner_id: str | None = None) -> int:
    conn = _conn()
    try:
        if owner_id:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM visitor_weeks WHERE owner_id = ? AND instr(raw_input, ?) > 0",
                (owner_id, _LEGACY_ATTACHMENT_MARKER),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM visitor_weeks WHERE instr(raw_input, ?) > 0",
                (_LEGACY_ATTACHMENT_MARKER,),
            ).fetchone()
        return int(row["count"])
    finally:
        conn.close()


def scrub_legacy_attachment_contexts(owner_id: str | None = None) -> int:
    """删除旧版本误写入 raw_input 的附件提取正文，保留标记前的用户原始文字。"""
    conn = _conn()
    try:
        if owner_id:
            updated = conn.execute(
                "UPDATE visitor_weeks SET raw_input = rtrim(substr(raw_input, 1, "
                "instr(raw_input, ?) - 1), char(9) || char(10) || char(13) || ' ') "
                "WHERE owner_id = ? AND instr(raw_input, ?) > 0",
                (_LEGACY_ATTACHMENT_MARKER, owner_id, _LEGACY_ATTACHMENT_MARKER),
            )
        else:
            updated = conn.execute(
                "UPDATE visitor_weeks SET raw_input = rtrim(substr(raw_input, 1, "
                "instr(raw_input, ?) - 1), char(9) || char(10) || char(13) || ' ') "
                "WHERE instr(raw_input, ?) > 0",
                (_LEGACY_ATTACHMENT_MARKER, _LEGACY_ATTACHMENT_MARKER),
            )
        conn.commit()
        return updated.rowcount
    finally:
        conn.close()
