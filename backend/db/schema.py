"""Définition du schéma SQL initial (DDL uniquement)."""

DDL_RECHERCHES_JOBS = """
CREATE TABLE IF NOT EXISTS recherches_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titre TEXT,
    requete TEXT NOT NULL,
    source TEXT,
    source_id INTEGER,
    params TEXT,
    statut TEXT DEFAULT 'pending',
    nb_trouves INTEGER DEFAULT 0,
    nb_insere INTEGER DEFAULT 0,
    date_lancement TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (source_id)
        REFERENCES sources(id)
        ON DELETE SET NULL
);
"""

DDL_SOURCES = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    label TEXT,
    base_url TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_APPELS_OFFRES = """
CREATE TABLE IF NOT EXISTS appels_offres (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titre TEXT,
    source TEXT,
    source_id INTEGER,
    date_publication TEXT,
    date_cloture TEXT,
    lieu TEXT,
    budget TEXT,
    type_marche TEXT,
    acheteur TEXT,
    reference TEXT,
    score_ia REAL,
    tags TEXT,
    raison TEXT,
    secteur TEXT,
    mot_cle TEXT,
    lien TEXT UNIQUE,
    search_id INTEGER NOT NULL,
    date_ajout TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (search_id)
        REFERENCES recherches_jobs(id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_id)
        REFERENCES sources(id)
        ON DELETE SET NULL
);
"""

DDL_RAW_RECHERCHES = """
CREATE TABLE IF NOT EXISTS raw_recherches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    search_id INTEGER NOT NULL,
    source TEXT NOT NULL,
    source_id INTEGER,
    mot_cle TEXT,
    html_contenu TEXT,
    lien TEXT,
    date_visite TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (search_id)
        REFERENCES recherches_jobs(id)
        ON DELETE CASCADE,
    FOREIGN KEY (source_id)
        REFERENCES sources(id)
        ON DELETE SET NULL
);
"""

DDL_INDEXES = [
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_sources_code ON sources(code)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_ao_lien ON appels_offres(lien)",
    "CREATE INDEX IF NOT EXISTS idx_ao_search_id ON appels_offres(search_id)",
    "CREATE INDEX IF NOT EXISTS idx_raw_recherches_search_lien ON raw_recherches(search_id, lien)",
    "CREATE INDEX IF NOT EXISTS idx_raw_recherches_search_source ON raw_recherches(search_id, source_id)",
    "CREATE INDEX IF NOT EXISTS idx_ao_search_source ON appels_offres(search_id, source_id)",
]


def create_base_schema(conn) -> None:
    """Crée le schéma de base sans logique de migration."""
    cur = conn.cursor()
    cur.execute(DDL_SOURCES)
    cur.execute(DDL_RECHERCHES_JOBS)
    cur.execute(DDL_APPELS_OFFRES)
    cur.execute(DDL_RAW_RECHERCHES)
    for ddl in DDL_INDEXES:
        cur.execute(ddl)
