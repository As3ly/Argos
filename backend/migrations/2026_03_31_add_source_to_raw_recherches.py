#!/usr/bin/env python3
"""Migration idempotente: ajoute raw_recherches.source + backfill depuis recherches_jobs.source."""

import sqlite3
from pathlib import Path

DB_PATH = (Path(__file__).resolve().parents[1] / "html_scrap.db").resolve()


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def run_migration() -> None:
    print(f"[migration] DB: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")

    try:
        has_source = column_exists(conn, "raw_recherches", "source")

        if not has_source:
            print("[migration] Ajout de la colonne source (temporairement nullable)")
            conn.execute("ALTER TABLE raw_recherches ADD COLUMN source TEXT")
        else:
            print("[migration] Colonne source déjà présente")

        print("[migration] Backfill source depuis recherches_jobs.source")
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

        print("[migration] Fallback source='unknown_source' si job sans source")
        conn.execute(
            """
            UPDATE raw_recherches
            SET source = 'unknown_source'
            WHERE source IS NULL OR TRIM(source) = ''
            """
        )

        # Vérification post-migration
        missing = conn.execute(
            "SELECT COUNT(*) FROM raw_recherches WHERE source IS NULL OR TRIM(source) = ''"
        ).fetchone()[0]

        total = conn.execute("SELECT COUNT(*) FROM raw_recherches").fetchone()[0]
        distinct_sources = conn.execute(
            "SELECT COUNT(DISTINCT source) FROM raw_recherches"
        ).fetchone()[0]

        if missing != 0:
            raise RuntimeError(
                f"Post-vérification échouée: {missing} lignes sans source dans raw_recherches."
            )

        conn.commit()
        print("[migration] ✅ OK")
        print(f"[migration] Lignes raw_recherches: {total}")
        print(f"[migration] Sources distinctes: {distinct_sources}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
