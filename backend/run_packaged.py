from __future__ import annotations

import os
import sys
import traceback
import webbrowser
from pathlib import Path
from threading import Timer
from multiprocessing import freeze_support

from version import APP_DISPLAY_NAME, APP_NAME, APP_VERSION


def _runtime_dir() -> Path:
    base_dir = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _log(message: str) -> None:
    log_path = _runtime_dir() / "argos_startup.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message, flush=True)


def _ensure_clean_runtime_db() -> Path:
    base_dir = _runtime_dir()
    db_path = base_dir / "html_scrap.db"
    os.environ["ARGOS_DB_PATH"] = str(db_path)
    return db_path


if __name__ in {"__main__", "__mp_main__"}:
    freeze_support()

    try:
        _log(f"=== START {APP_DISPLAY_NAME} ===")

        db_path = _ensure_clean_runtime_db()
        _log(f"DB PATH = {db_path}")

        _log("IMPORT initialize_database...")
        from db.repository import initialize_database

        _log("IMPORT ui...")
        from ui_app import ui

        _log("INITIALIZE DATABASE...")
        initialize_database()
        _log("DATABASE OK")

        url = "http://127.0.0.1:8080"
        _log(f"STARTING NICEGUI {APP_VERSION} ON {url}")

        Timer(2.0, lambda: webbrowser.open(url)).start()

        ui.run(
            title=APP_DISPLAY_NAME,
            reload=False,
            native=False,
            host="127.0.0.1",
            port=8080,
            show=False,
        )

    except Exception:
        error = traceback.format_exc()
        _log("=== ERROR ===")
        _log(error)
        raise
