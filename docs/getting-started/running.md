# Exécuter Argos

## Interface de développement

Depuis la racine :

```bash
uv run backend/ui_app.py
```

NiceGUI démarre par défaut sur `http://127.0.0.1:8080`. Le mode source utilise le rechargement automatique.

## Exécutable Windows

L'exécutable appelle `backend/run_packaged.py`, initialise la base locale, ouvre le navigateur et démarre NiceGUI sans rechargement automatique.

```text
Application : http://127.0.0.1:8080
Base        : %LOCALAPPDATA%\Argos\html_scrap.db
Log startup : %LOCALAPPDATA%\Argos\argos_startup.log
```

Une seule instance doit utiliser le port `8080`. Fermer l'ancienne instance avant d'en lancer une nouvelle.

## Mode CLI de diagnostic

```bash
uv run backend/main.py
```

Ce mode est destiné au développement et au diagnostic. Le parcours utilisateur de référence reste l'interface NiceGUI.

## Documentation locale

```bash
uv --config-file uv-corporate.toml pip install \
  --python .venv/bin/python --requirement docs/requirements.txt
uv run --no-sync mkdocs serve
```

Le terminal affiche l'adresse de prévisualisation, généralement `http://127.0.0.1:8000`.

## Arrêt propre

- Fermer les recherches en cours avant l'arrêt si possible.
- Interrompre le processus avec `Ctrl+C` en développement.
- Ne pas copier ou remplacer la base pendant qu'un tri IA écrit encore des résultats.
- Avant une mise à jour, effectuer une sauvegarde cohérente avec la commande SQLite `.backup`.
