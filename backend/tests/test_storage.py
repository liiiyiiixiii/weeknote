import sqlite3
from concurrent.futures import ThreadPoolExecutor

from app import storage


def _create_legacy_tables(conn):
    conn.execute(
        """
        CREATE TABLE weeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT UNIQUE NOT NULL,
            raw_input TEXT NOT NULL,
            report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE user_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
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


def _create_visitor_settings_table(conn):
    conn.execute(
        """
        CREATE TABLE visitor_settings (
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


def _insert_legacy_settings(conn, *, detail_level="detailed"):
    conn.execute(
        """
        INSERT INTO user_settings (
            id, week_one_start, purpose_mode, custom_purpose_name,
            custom_purpose_description, detail_level, tone,
            onboarding_completed, updated_at
        ) VALUES (1, '2026-08-10', 'default', '', '', ?, 'natural', 1,
                  '2026-08-19 22:41:42')
        """,
        (detail_level,),
    )


def test_same_week_creates_versions_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "versions.db")
    storage.init_db()

    first_id = storage.create_week("owner", "2026-08-17", "first", "{}")
    second_id = storage.create_week("owner", "2026-08-17", "second", "{}")

    assert first_id != second_id
    rows = storage.list_weeks("owner")
    assert [(row["version"], row["version_count"]) for row in rows] == [(2, 2), (1, 2)]
    assert storage.get_week("owner", first_id)["raw_input"] == "first"
    assert storage.get_week("owner", second_id)["raw_input"] == "second"


def test_old_unique_week_schema_is_migrated_without_data_loss(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE visitor_weeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL,
            week_start TEXT NOT NULL,
            raw_input TEXT NOT NULL,
            report_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(owner_id, week_start)
        )
        """
    )
    conn.execute(
        "INSERT INTO visitor_weeks(owner_id, week_start, raw_input) VALUES (?, ?, ?)",
        ("owner", "2026-08-17", "legacy content"),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(storage, "DB_PATH", db_path)
    storage.init_db()

    rows = storage.list_weeks("owner")
    assert len(rows) == 1
    assert rows[0]["version"] == 1
    assert storage.get_week("owner", rows[0]["id"])["raw_input"] == "legacy content"


def test_empty_legacy_tables_are_marked_without_requiring_an_owner(tmp_path, monkeypatch):
    db_path = tmp_path / "empty-legacy.db"
    conn = sqlite3.connect(db_path)
    _create_legacy_tables(conn)
    conn.commit()
    conn.close()

    monkeypatch.delenv("APP_LEGACY_OWNER_ID", raising=False)
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    storage.init_db()
    storage.init_db()

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM visitor_weeks").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM visitor_settings").fetchone()[0] == 0
    marker = conn.execute(
        "SELECT owner_id FROM schema_migrations WHERE name = ?",
        (storage._LEGACY_GLOBAL_MIGRATION,),
    ).fetchall()
    assert marker == [("",)]
    conn.close()


def test_global_legacy_tables_migrate_once_and_keep_source_rows(tmp_path, monkeypatch):
    db_path = tmp_path / "global-legacy.db"
    conn = sqlite3.connect(db_path)
    _create_legacy_tables(conn)
    conn.executemany(
        """
        INSERT INTO weeks (
            id, week_start, raw_input, report_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (7, "2026-08-10", "first", '{"week": 1}', "2026-08-11", "2026-08-12"),
            (9, "2026-08-17", "second", '{"week": 2}', "2026-08-18", "2026-08-19"),
        ],
    )
    _insert_legacy_settings(conn)
    conn.commit()
    conn.close()

    monkeypatch.setenv("APP_LEGACY_OWNER_ID", "legacy-owner")
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    storage.init_db()
    storage.init_db()

    conn = sqlite3.connect(db_path)
    migrated = conn.execute(
        "SELECT id, owner_id, week_start, version, raw_input, created_at, updated_at FROM visitor_weeks ORDER BY id"
    ).fetchall()
    assert migrated == [
        (7, "legacy-owner", "2026-08-10", 1, "first", "2026-08-11", "2026-08-12"),
        (9, "legacy-owner", "2026-08-17", 1, "second", "2026-08-18", "2026-08-19"),
    ]
    settings = conn.execute(
        "SELECT owner_id, week_one_start, detail_level, updated_at FROM visitor_settings"
    ).fetchall()
    assert settings == [("legacy-owner", "2026-08-10", "detailed", "2026-08-19 22:41:42")]
    assert conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM legacy_migration_map").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == 1
    conn.close()


def test_legacy_migration_preserves_new_rows_and_records_conflicts(tmp_path, monkeypatch):
    db_path = tmp_path / "legacy-conflicts.db"
    conn = sqlite3.connect(db_path)
    _create_legacy_tables(conn)
    conn.execute(storage._WEEKS_TABLE_SQL)
    _create_visitor_settings_table(conn)
    conn.execute(
        """
        INSERT INTO visitor_settings (
            owner_id, week_one_start, detail_level, updated_at
        ) VALUES ('owner', '2026-08-24', 'concise', '2026-08-25')
        """
    )
    conn.executemany(
        """
        INSERT INTO visitor_weeks (
            id, owner_id, week_start, version, raw_input, report_json, created_at, updated_at
        ) VALUES (?, 'owner', ?, 1, ?, ?, ?, ?)
        """,
        [
            (1, "2026-08-10", "new content", '{"new": true}', "2026-08-20", "2026-08-20"),
            (10, "2026-08-17", "same content", "{}", "2026-08-18", "2026-08-19"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO weeks (
            id, week_start, raw_input, report_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "2026-08-10", "old content", '{"old": true}', "2026-08-11", "2026-08-12"),
            (2, "2026-08-17", "same content", "{}", "2026-08-18", "2026-08-19"),
        ],
    )
    _insert_legacy_settings(conn, detail_level="detailed")
    conn.commit()
    conn.close()

    monkeypatch.delenv("APP_LEGACY_OWNER_ID", raising=False)
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    storage.init_db()

    conn = sqlite3.connect(db_path)
    current = conn.execute(
        "SELECT week_start, version, raw_input FROM visitor_weeks ORDER BY week_start, version"
    ).fetchall()
    assert current == [
        ("2026-08-10", 1, "new content"),
        ("2026-08-10", 2, "old content"),
        ("2026-08-17", 1, "same content"),
    ]
    assert conn.execute(
        "SELECT week_one_start, detail_level, updated_at FROM visitor_settings WHERE owner_id = 'owner'"
    ).fetchone() == ("2026-08-24", "concise", "2026-08-25")
    dispositions = conn.execute(
        "SELECT source_table, source_key, disposition FROM legacy_migration_map ORDER BY source_table, source_key"
    ).fetchall()
    assert dispositions == [
        ("user_settings", "1", "preserved-target"),
        ("weeks", "1", "inserted"),
        ("weeks", "2", "matched-existing"),
    ]
    assert conn.execute("SELECT COUNT(*) FROM weeks").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0] == 1
    conn.close()


def test_legacy_migration_rolls_back_when_owner_is_ambiguous(tmp_path, monkeypatch):
    db_path = tmp_path / "ambiguous-owner.db"
    conn = sqlite3.connect(db_path)
    _create_legacy_tables(conn)
    _insert_legacy_settings(conn)
    _create_visitor_settings_table(conn)
    conn.executemany(
        "INSERT INTO visitor_settings(owner_id, week_one_start) VALUES (?, '2026-08-24')",
        [("owner-a",), ("owner-b",)],
    )
    conn.commit()
    conn.close()

    monkeypatch.delenv("APP_LEGACY_OWNER_ID", raising=False)
    monkeypatch.setattr(storage, "DB_PATH", db_path)
    try:
        storage.init_db()
    except RuntimeError as exc:
        assert "APP_LEGACY_OWNER_ID" in str(exc)
    else:
        raise AssertionError("ambiguous legacy owner must abort the migration")

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM visitor_settings").fetchone()[0] == 2
    assert (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'").fetchone()
        is None
    )
    assert conn.execute("SELECT COUNT(*) FROM user_settings").fetchone()[0] == 1
    conn.close()


def test_asr_reservation_is_atomic_and_releases_unused_seconds(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "quota.db")
    storage.init_db()

    assert storage.reserve_daily_asr("ip", "2026-08-23", 120, 180) == (True, 120)
    assert storage.reserve_daily_asr("ip", "2026-08-23", 120, 180) == (False, 120)
    assert storage.release_daily_asr("ip", "2026-08-23", 90) == 30
    assert storage.reserve_daily_asr("ip", "2026-08-23", 120, 180) == (True, 150)


def test_concurrent_week_versions_are_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "concurrent.db")
    storage.init_db()

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(
            pool.map(
                lambda number: storage.create_week("owner", "2026-08-17", f"version-{number}", "{}"),
                range(8),
            )
        )

    assert len(set(ids)) == 8
    assert sorted(row["version"] for row in storage.list_weeks("owner")) == list(range(1, 9))


def test_concurrent_worker_schema_initialization_retries_wal_lock(tmp_path, monkeypatch):
    database = tmp_path / "worker-startup.db"
    monkeypatch.setattr(storage, "DB_PATH", database)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: storage.init_db(), range(8)))

    conn = sqlite3.connect(database)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


def test_legacy_attachment_context_can_be_audited_and_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "privacy.db")
    storage.init_db()
    marker = storage._LEGACY_ATTACHMENT_MARKER
    week_id = storage.create_week("owner", "2026-08-17", f"用户原文\n\n{marker}\nSECRET", "{}")

    assert storage.legacy_attachment_context_count("owner") == 1
    assert storage.scrub_legacy_attachment_contexts("owner") == 1
    assert storage.get_week("owner", week_id)["raw_input"] == "用户原文"
