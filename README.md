# Argos

Argos est un outil de veille d'appels d'offres techniques. Il transforme un besoin métier en mots-clés, interroge les sources BOAMP, TED/JOUE et EDF, puis extrait et classe les résultats avec Azure OpenAI dans une interface NiceGUI.

## Documentation

La documentation complète est disponible dans [`docs/`](docs/index.md) et se construit avec MkDocs Material.

```bash
uv --config-file uv-corporate.toml sync --locked
uv --config-file uv-corporate.toml pip install \
  --python .venv/bin/python --requirement docs/requirements.txt
uv run --no-sync mkdocs serve
```

Contrôle utilisé par la CI :

```bash
uv run --no-sync mkdocs build --strict
```

Les parcours principaux sont :

- [installation](docs/getting-started/installation.md) ;
- [première recherche](docs/getting-started/first-search.md) ;
- [architecture](docs/architecture/overview.md) ;
- [maintenance](docs/maintenance/schedule.md) ;
- [base SQLite](docs/database/schema.md) ;
- [release Windows](docs/maintenance/release-windows.md).

Le guide utilisateur illustré est également disponible dans
[`output/pdf/Guide_Argos_installation_utilisation_v1.2.pdf`](output/pdf/Guide_Argos_installation_utilisation_v1.2.pdf).

## Démarrage rapide

Pré-requis : Python 3.13, `uv`, accès au Nexus interne et une configuration Azure OpenAI valide.

```bash
git clone <URL_GITLAB_FRA_DU_PROJET>
cd Argos
uv --config-file uv-corporate.toml sync --locked
cp .env.example .env
uv run backend/ui_app.py
```

L'interface est ensuite accessible sur l'adresse indiquée dans la console, par défaut `http://127.0.0.1:8080`.

## Vérifications

```bash
uv run python -m compileall -q backend scripts
PYTHONPATH=backend uv run python -m unittest discover -s tests -p "test_*.py"
uv run --group dev python scripts/build_release.py --check
uv --config-file uv-corporate.toml pip install --python .venv/bin/python --requirement docs/requirements.txt
uv run --no-sync mkdocs build --strict
```
