"""Migrations versionnées et idempotentes pour la base Argos."""

from __future__ import annotations

import sqlite3
from typing import Callable

MigrationFn = Callable[[sqlite3.Connection], None]


def _has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(r[1] == column_name for r in rows)


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _is_applied(conn: sqlite3.Connection, version: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM schema_migrations WHERE version = ? LIMIT 1", (version,)
    ).fetchone()
    return row is not None


def _mark_applied(conn: sqlite3.Connection, version: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
        (version,),
    )


def _migration_2026_03_31_raw_source(conn: sqlite3.Connection) -> None:
    """Ajoute raw_recherches.source + backfill depuis recherches_jobs.source."""
    if not _has_column(conn, "raw_recherches", "source"):
        conn.execute("ALTER TABLE raw_recherches ADD COLUMN source TEXT")

    conn.execute(
        """
        UPDATE raw_recherches
        SET source = (
            SELECT rj.source
            FROM recherches_jobs rj
            WHERE rj.id = raw_recherches.search_id
        )
        WHERE source IS NULL OR TRIM(source) = ''
        """
    )

    conn.execute(
        """
        UPDATE raw_recherches
        SET source = 'unknown_source'
        WHERE source IS NULL OR TRIM(source) = ''
        """
    )


def _migration_2026_04_01_source_id_columns(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes source_id et backfill vers francemarches."""
    if not _has_column(conn, "recherches_jobs", "source_id"):
        conn.execute("ALTER TABLE recherches_jobs ADD COLUMN source_id INTEGER")
    if not _has_column(conn, "raw_recherches", "source_id"):
        conn.execute("ALTER TABLE raw_recherches ADD COLUMN source_id INTEGER")
    if not _has_column(conn, "appels_offres", "source_id"):
        conn.execute("ALTER TABLE appels_offres ADD COLUMN source_id INTEGER")

    conn.execute(
        """
        INSERT INTO sources(code, label, base_url, active)
        VALUES ('francemarches', 'France Marchés', 'https://www.francemarches.com/', 1)
        ON CONFLICT(code) DO NOTHING
        """
    )

    source_row = conn.execute(
        "SELECT id FROM sources WHERE code = 'francemarches' LIMIT 1"
    ).fetchone()
    if source_row is None:
        raise RuntimeError("Impossible de récupérer/initialiser la source 'francemarches'.")

    source_id = int(source_row[0])
    conn.execute(
        "UPDATE recherches_jobs SET source_id = ? WHERE source_id IS NULL",
        (source_id,),
    )
    conn.execute(
        "UPDATE raw_recherches SET source_id = ? WHERE source_id IS NULL",
        (source_id,),
    )
    conn.execute(
        "UPDATE appels_offres SET source_id = ? WHERE source_id IS NULL",
        (source_id,),
    )


def _migration_2026_04_01_recherches_jobs_date_lancement(conn: sqlite3.Connection) -> None:
    """Aligne recherches_jobs.created_at vers recherches_jobs.date_lancement."""
    has_created_at = _has_column(conn, "recherches_jobs", "created_at")
    has_date_lancement = _has_column(conn, "recherches_jobs", "date_lancement")

    if has_created_at and not has_date_lancement:
        conn.execute("ALTER TABLE recherches_jobs ADD COLUMN date_lancement TEXT")
        conn.execute(
            """
            UPDATE recherches_jobs
            SET date_lancement = created_at
            WHERE date_lancement IS NULL
            """
        )


def _migration_2026_04_13_recherches_jobs_warnings_json(conn: sqlite3.Connection) -> None:
    """Ajoute recherches_jobs.warnings_json pour persister les alertes de scraping."""
    if not _has_column(conn, "recherches_jobs", "warnings_json"):
        conn.execute("ALTER TABLE recherches_jobs ADD COLUMN warnings_json TEXT")


MIGRATIONS: list[tuple[str, MigrationFn]] = [
    ("2026_03_31_raw_recherches_source", _migration_2026_03_31_raw_source),
    ("2026_04_01_source_id_columns", _migration_2026_04_01_source_id_columns),
    (
        "2026_04_01_recherches_jobs_date_lancement",
        _migration_2026_04_01_recherches_jobs_date_lancement,
    ),
    (
        "2026_04_13_recherches_jobs_warnings_json",
        _migration_2026_04_13_recherches_jobs_warnings_json,
    ),
]


def apply_migrations(conn: sqlite3.Connection) -> None:
    """Applique toutes les migrations non encore marquées."""
    _ensure_migrations_table(conn)
    for version, migration_fn in MIGRATIONS:
        if _is_applied(conn, version):
            continue
        migration_fn(conn)
        _mark_applied(conn, version)
