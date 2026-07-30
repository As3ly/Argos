# Installation

## Choisir le mode d'installation

| Profil | Mode recommandé |
|---|---|
| Utilisateur Windows | Exécutable versionné fourni par l'équipe de maintenance |
| Développeur ou mainteneur | Environnement Python géré par `uv` |
| Pipeline GitLab | Synchronisation verrouillée avec `uv-corporate.toml` |

## Pré-requis de développement

- Windows 10/11, macOS ou Linux pour le développement ;
- Python 3.13 ;
- Git ;
- `uv` ;
- accès au GitLab FRA, au Nexus interne, au proxy FRA et à Azure OpenAI ;
- Microsoft Edge uniquement si une évolution nécessite une automatisation navigateur.

Argos utilise actuellement `requests` pour ses trois sources. Playwright n'est donc pas requis pour exécuter la version courante.

## Installation avec `uv`

```bash
git clone <URL_GITLAB_FRA_DU_PROJET>
cd Argos
uv --config-file uv-corporate.toml sync --locked --group dev
uv --config-file uv-corporate.toml pip install \
  --python .venv/bin/python --requirement docs/requirements.txt
cp .env.example .env
```

Sous PowerShell :

```powershell
git clone <URL_GITLAB_FRA_DU_PROJET>
Set-Location Argos
uv --config-file uv-corporate.toml sync --locked --group dev
uv --config-file uv-corporate.toml pip install --python .venv\Scripts\python.exe --requirement docs\requirements.txt
Copy-Item .env.example .env
```

Compléter ensuite `.env` en suivant la page [Configuration](configuration.md).

!!! warning "Lock de dépendances"
    Ne pas exécuter `uv lock` sans `--config-file uv-corporate.toml`. Le lock versionné doit continuer à référencer le Nexus interne et ne doit pas réintroduire d'URL PyPI publique.

## Vérification rapide

```bash
uv run python -m compileall -q backend scripts
PYTHONPATH=backend uv run python -m unittest discover -s tests -p "test_*.py"
uv run --group dev python scripts/build_release.py --check
uv run --no-sync mkdocs build --strict
```

Ces commandes vérifient respectivement la syntaxe, les tests automatisés, la cohérence de release et la documentation.

## Installation de l'exécutable Windows

1. Copier l'exécutable `Argos-<version>-windows-x64.exe` sur le poste.
2. Vérifier son SHA256 avec le fichier fourni.
3. Fermer toute ancienne instance d'Argos.
4. Lancer l'exécutable.
5. Vérifier l'ouverture de `http://127.0.0.1:8080`.

Les données utilisateur sont conservées dans :

```text
%LOCALAPPDATA%\Argos\html_scrap.db
```

Une nouvelle version de l'exécutable réutilise cette base et applique automatiquement les migrations manquantes au démarrage.
