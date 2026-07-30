"""Façade de compatibilité temporaire vers backend.db.repository."""

from db.repository import (  # noqa: F401
    BASE_DIR,
    DB_PATH,
    add_appel_offre,
    count_recherche_jobs,
    create_recherche_job,
    delete_saved_prompt,
    delete_recherche_jobs,
    ensure_source,
    get_appel_offre_by_lien,
    get_conn,
    get_source_id_by_code,
    init_db,
    initialize_database,
    inserer_raw_recherche,
    list_appels_offres_non_pert,
    list_appels_offres_pert,
    list_recherche_jobs,
    list_saved_prompts,
    raw_lien_existe,
    safe_delete_raw,
    safe_insert,
    save_prompt,
    update_saved_prompt,
    update_recherche_job,
)
from db.schema import (  # noqa: F401
    DDL_APPELS_OFFRES,
    DDL_INDEXES,
    DDL_RAW_RECHERCHES,
    DDL_RECHERCHES_JOBS,
    DDL_SAVED_PROMPTS,
    DDL_SOURCES,
)

__all__ = [
    "BASE_DIR",
    "DB_PATH",
    "DDL_APPELS_OFFRES",
    "DDL_INDEXES",
    "DDL_RAW_RECHERCHES",
    "DDL_RECHERCHES_JOBS",
    "DDL_SAVED_PROMPTS",
    "DDL_SOURCES",
    "add_appel_offre",
    "count_recherche_jobs",
    "create_recherche_job",
    "delete_saved_prompt",
    "delete_recherche_jobs",
    "ensure_source",
    "get_appel_offre_by_lien",
    "get_conn",
    "get_source_id_by_code",
    "init_db",
    "initialize_database",
    "inserer_raw_recherche",
    "list_appels_offres_non_pert",
    "list_appels_offres_pert",
    "list_recherche_jobs",
    "list_saved_prompts",
    "raw_lien_existe",
    "safe_delete_raw",
    "safe_insert",
    "save_prompt",
    "update_saved_prompt",
    "update_recherche_job",
]

if __name__ == "__main__":
    initialize_database()
    for ao in list_appels_offres_pert(search_id=0, limit=10):
        print(ao)
