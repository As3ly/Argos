# Commandes utiles

## Environnement

```bash
# Synchroniser l'application
uv --config-file uv-corporate.toml sync --locked

# Installer les outils de maintenance, puis la documentation
uv --config-file uv-corporate.toml sync --locked --group dev
uv --config-file uv-corporate.toml pip install \
  --python .venv/bin/python --requirement docs/requirements.txt
```

## Exécution

```bash
# Interface
uv run backend/ui_app.py

# Diagnostic CLI
uv run backend/main.py
```

## Qualité

```bash
uv run python -m compileall -q backend scripts
PYTHONPATH=backend uv run python -m unittest discover -s tests -p "test_*.py"
uv run --group dev python scripts/build_release.py --check
```

## Documentation

```bash
# Prévisualiser
uv run --no-sync mkdocs serve

# Construire comme la CI
uv run --no-sync mkdocs build --strict
```

## Release Windows

```powershell
uv --config-file uv-corporate.toml sync --locked --group dev
uv run --group dev python scripts/build_release.py
```

## SQLite

```bash
# Sauvegarde cohérente
sqlite3 html_scrap.db ".backup 'argos-backup.db'"

# Intégrité
sqlite3 html_scrap.db "PRAGMA integrity_check;"
sqlite3 html_scrap.db "PRAGMA foreign_key_check;"

# Recherches récentes
sqlite3 -header -column html_scrap.db \
  "SELECT id,titre,statut,nb_trouves,nb_insere,date_lancement
   FROM recherches_jobs ORDER BY id DESC LIMIT 20;"

# Raws restants
sqlite3 -header -column html_scrap.db \
  "SELECT search_id,source,COUNT(*) AS nombre
   FROM raw_recherches GROUP BY search_id,source;"
```

## Lock de dépendances

À exécuter uniquement dans le cadre d'une mise à jour contrôlée :

```bash
uv --config-file uv-corporate.toml lock
uv --config-file uv-corporate.toml sync --locked --group dev
uv run --group dev python scripts/build_release.py --check
```
