from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from .migrations import apply_migrations
from .schema import create_base_schema

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("ARGOS_DB_PATH", str(BASE_DIR / "html_scrap.db"))).resolve()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_source_id_by_code(code: str, *, conn: Optional[sqlite3.Connection] = None) -> Optional[int]:
    if not code or not code.strip():
        return None
    code = code.strip().lower()
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
    try:
        row = conn.execute("SELECT id FROM sources WHERE code = ? LIMIT 1", (code,)).fetchone()
        return int(row["id"] if isinstance(row, sqlite3.Row) else row[0]) if row else None
    finally:
        if owns_conn and conn is not None:
            conn.close()


def ensure_source(
    code: str,
    *,
    label: Optional[str] = None,
    base_url: Optional[str] = None,
    active: int = 1,
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    if not code or not code.strip():
        raise ValueError("Le champ 'code' est obligatoire pour la table sources.")
    code = code.strip().lower()
    owns_conn = conn is None
    if owns_conn:
        conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO sources(code, label, base_url, active)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                label = COALESCE(excluded.label, sources.label),
                base_url = COALESCE(excluded.base_url, sources.base_url),
                active = excluded.active
            """,
            (code, label, base_url, active),
        )
        source_id = get_source_id_by_code(code, conn=conn)
        if source_id is None:
            raise RuntimeError(f"Impossible de récupérer l'id source pour code='{code}'.")
        return source_id
    finally:
        if owns_conn and conn is not None:
            conn.close()


def initialize_database() -> None:
    """Point d'entrée unique: schéma de base -> migrations -> seed minimal."""
    with closing(get_conn()) as conn, conn:
        create_base_schema(conn)
        apply_migrations(conn)
        ensure_source(
            "francemarches",
            label="France Marchés",
            base_url="https://www.francemarches.com/",
            active=1,
            conn=conn,
        )


def init_db() -> None:
    """Alias de compatibilité."""
    initialize_database()


def create_recherche_job(
    *,
    requete: str,
    source: Optional[str] = None,
    titre: Optional[str] = None,
    params: Optional[str] = None,
    statut: Optional[str] = None,
    nb_trouves: Optional[int] = None,
    nb_insere: Optional[int] = None,
) -> int:
    if not requete:
        raise ValueError("Le champ 'requete' est obligatoire.")
    with closing(get_conn()) as conn, conn:
        source_id = get_source_id_by_code(source, conn=conn) if source else None
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO recherches_jobs (requete, source, source_id, params, statut, nb_trouves, nb_insere, titre, date_lancement)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (requete, source, source_id, params, statut, nb_trouves, nb_insere, titre),
        )
        return cur.lastrowid


def update_recherche_job(
    search_id: int,
    *,
    statut: Optional[str] = None,
    nb_trouves: Optional[int] = None,
    nb_insere: Optional[int] = None,
    titre: Optional[str] = None,
    requete: Optional[str] = None,
) -> None:
    sets = []
    values = []
    if statut is not None:
        sets.append("statut = ?")
        values.append(statut)
    if nb_trouves is not None:
        sets.append("nb_trouves = ?")
        values.append(nb_trouves)
    if nb_insere is not None:
        sets.append("nb_insere = ?")
        values.append(nb_insere)
    if requete is not None:
        sets.append("requete = ?")
        values.append(requete)
    if titre is not None:
        sets.append("titre = ?")
        values.append(titre)

    if not sets:
        return

    values.append(search_id)
    with closing(get_conn()) as conn, conn:
        conn.execute(f"UPDATE recherches_jobs SET {', '.join(sets)} WHERE id = ?", values)


def list_recherche_jobs(limit: int = 50, order_by: str = "date_lancement DESC") -> Iterable[Dict[str, Any]]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            f"SELECT * FROM recherches_jobs ORDER BY {order_by} LIMIT ?", (limit,)
        ).fetchall()
        for row in rows:
            yield dict(row)


# --- Fonctions historiques conservées telles quelles pour compatibilité ---
def inserer_raw_recherche(*, search_id: int, source: str, mot_cle, html_contenu: str, lien: str):
    if isinstance(mot_cle, list):
        mot_cle = mot_cle[0] if mot_cle else ""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Le champ 'source' est obligatoire pour raw_recherches.")

    with closing(get_conn()) as conn, conn:
        cur = conn.cursor()
        source_id = get_source_id_by_code(source, conn=conn)
        cur.execute(
            """
            INSERT INTO raw_recherches (search_id, source, source_id, mot_cle, html_contenu, lien)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (search_id, source, source_id, mot_cle, html_contenu, lien),
        )


def raw_lien_existe(search_id: int, lien: str) -> bool:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM raw_recherches WHERE search_id = ? AND lien = ? LIMIT 1",
            (search_id, lien),
        )
        return cur.fetchone() is not None


def safe_insert(extraction: dict, pertinent: bool, raw_id: int, lien: str, source: str, search_id: int):
    if not isinstance(source, str) or not source.strip():
        print(f"[RAW {raw_id}] ❌ Insertion refusée: source vide/invalide (source={source!r})")
        return

    if not isinstance(search_id, int) or search_id <= 0:
        print(f"[RAW {raw_id}] ❌ Insertion refusée: search_id invalide (search_id={search_id!r})")
        return

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")

        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO appels_offres (
                titre, source, source_id, date_publication, date_cloture, lieu, budget,
                type_marche, acheteur, reference, score_ia, tags, raison,
                secteur, mot_cle, lien, search_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                extraction["titre"],
                source.strip(),
                get_source_id_by_code(source, conn=conn),
                extraction["date_publication"],
                extraction["date_cloture"],
                extraction["lieu"],
                extraction["budget"],
                extraction["type_marche"],
                extraction["acheteur"],
                extraction["reference"],
                extraction["score_ia"],
                extraction["tags"],
                extraction["raison"],
                extraction["secteur"],
                extraction["mot_cle"],
                lien,
                search_id,
            ),
        )

        conn.commit()
        print(f"[RAW {raw_id}] ✔ INSERT OK (pertinent={pertinent})")

    except sqlite3.IntegrityError:
        print(f"[RAW {raw_id}] ⚠ Doublon détecté → ignoré")

    except Exception as e:
        print(f"[RAW {raw_id}] ❌ Erreur INSERT : {e}")

    finally:
        if conn is not None:
            conn.close()


def safe_delete_raw(raw_id: int, search_id: int):
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")

        cur = conn.cursor()
        cur.execute("DELETE FROM raw_recherches WHERE id = ? AND search_id = ?", (raw_id, search_id))

        conn.commit()
        print(f"[RAW {raw_id}] ✔ RAW supprimé")

    except Exception as e:
        print(f"[RAW {raw_id}] ❌ Erreur suppression RAW : {e}")

    finally:
        conn.close()


def add_appel_offre(
    *,
    search_id: int,
    titre: Optional[str] = None,
    source: Optional[str] = None,
    date_publication: Optional[str] = None,
    date_cloture: Optional[str] = None,
    lieu: Optional[str] = None,
    budget: Optional[str] = None,
    type_marche: Optional[str] = None,
    acheteur: Optional[str] = None,
    reference: Optional[str] = None,
    score_ia: Optional[float] = None,
    tags: Optional[str] = None,
    raison: Optional[str] = None,
    secteur: Optional[str] = None,
    mot_cle: Optional[str] = None,
    lien: Optional[str] = None,
) -> int:
    if not lien:
        raise ValueError("Le champ 'lien' est obligatoire (clé unique).")
    if not search_id:
        raise ValueError("Le champ 'search_id' est obligatoire.")

    with closing(get_conn()) as conn, conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM recherches_jobs WHERE id = ? LIMIT 1", (search_id,))
        if cur.fetchone() is None:
            raise ValueError(f"search_id={search_id} introuvable dans 'recherches_jobs'.")

        source_id = get_source_id_by_code(source, conn=conn) if source else None
        cur.execute(
            """
            INSERT OR IGNORE INTO appels_offres
            (titre, source, source_id, date_publication, date_cloture, lieu, budget, type_marche,
             acheteur, reference, score_ia, tags, raison, secteur, mot_cle, lien, search_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                titre, source, source_id, date_publication, date_cloture, lieu, budget, type_marche,
                acheteur, reference, score_ia, tags, raison, secteur, mot_cle, lien, search_id
            )
        )
        cur.execute("SELECT id FROM appels_offres WHERE lien = ? LIMIT 1", (lien,))
        row = cur.fetchone()
        return int(row["id"]) if row else -1


def get_appel_offre_by_lien(lien: str) -> Optional[Dict[str, Any]]:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM appels_offres WHERE lien = ? LIMIT 1", (lien,))
        row = cur.fetchone()
        return dict(row) if row else None


def list_appels_offres_pert(*, search_id: Optional[int] = None, limit: int = 50, order_by: str = "date_ajout DESC") -> Iterable[Dict[str, Any]]:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        if search_id:
            query = f"""
                SELECT * FROM appels_offres
                WHERE search_id = ? AND score_ia > 0.45
                ORDER BY {order_by}
                LIMIT ?
            """
            cur.execute(query, (search_id, limit))
        else:
            query = f"SELECT * FROM appels_offres ORDER BY {order_by} LIMIT ?"
            cur.execute(query, (limit,))
        for r in cur.fetchall():
            yield dict(r)


def list_appels_offres_non_pert(*, search_id: Optional[int] = None, limit: int = 50, order_by: str = "date_ajout DESC") -> Iterable[Dict[str, Any]]:
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        if search_id:
            query = f"""
                SELECT * FROM appels_offres
                WHERE search_id = ? AND score_ia <= 0.45
                ORDER BY {order_by}
                LIMIT ?
            """
            cur.execute(query, (search_id, limit))
        else:
            query = f"SELECT * FROM appels_offres ORDER BY {order_by} LIMIT ?"
            cur.execute(query, (limit,))
        for r in cur.fetchall():
            yield dict(r)
