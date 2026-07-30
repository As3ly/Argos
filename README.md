# Argos

Argos est un outil de veille d'appels d'offres techniques. Il transforme un besoin métier en mots-clés, interroge les sources BOAMP, TED/JOUE et EDF, puis extrait et classe les résultats avec Azure OpenAI dans une interface NiceGUI.

## Documentation

La documentation complète est publiée à l'adresse
[https://gitlab.framatome.io/elyas-automatisation/argos/](https://gitlab.framatome.io/elyas-automatisation/argos/)
et se construit avec MkDocs Material.

```bash
uv --config-file uv-corporate.toml run --no-project \
  --with-requirements docs/requirements.txt \
  mkdocs serve
```

Contrôle utilisé par la CI :

```bash
uv --config-file uv-corporate.toml run --no-project \
  --with-requirements docs/requirements.txt \
  mkdocs build --strict
```

Les parcours principaux sont :

- [installation](https://gitlab.framatome.io/elyas-automatisation/argos/getting-started/installation/) ;
- [première recherche](https://gitlab.framatome.io/elyas-automatisation/argos/getting-started/first-search/) ;
- [architecture](https://gitlab.framatome.io/elyas-automatisation/argos/architecture/overview/) ;
- [maintenance](https://gitlab.framatome.io/elyas-automatisation/argos/maintenance/schedule/) ;
- [base SQLite](https://gitlab.framatome.io/elyas-automatisation/argos/database/schema/) ;
- [release Windows](https://gitlab.framatome.io/elyas-automatisation/argos/maintenance/release-windows/).

Le guide utilisateur illustré est également disponible dans
[le dépôt GitLab FRA](https://gitlab.framatome.io/elyas-automatisation/argos/-/blob/main/output/pdf/Guide_Argos_installation_utilisation_v1.2.pdf).

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
uv --config-file uv-corporate.toml run --no-project \
  --with-requirements docs/requirements.txt \
  mkdocs build --strict
```
