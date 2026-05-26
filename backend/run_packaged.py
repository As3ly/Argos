from __future__ import annotations

import os
from pathlib import Path

from db.repository import initialize_database
from ui_app import ui


def _ensure_clean_runtime_db() -> Path:
    base_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / "Argos"
    base_dir.mkdir(parents=True, exist_ok=True)

    db_path = base_dir / "html_scrap.db"

    # Force l'application à utiliser une BDD utilisateur,
    # pas une BDD embarquée dans le .exe.
    os.environ["ARGOS_DB_PATH"] = str(db_path)

    return db_path


if __name__ in {"__main__", "__mp_main__"}:
    _ensure_clean_runtime_db()
    initialize_database()

    ui.run(
        title="Argos",
        reload=False,
        native=False,
        port=8080,
    )