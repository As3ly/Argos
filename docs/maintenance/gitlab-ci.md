# Pipeline GitLab

Le fichier `.gitlab-ci.yml` couvre la qualité, la documentation, le SAST et la publication GitLab Pages.

## Prérequis du runner FRA

- accès au dépôt ;
- `uv` installé ;
- Python 3.13 disponible ;
- accès au Nexus et au proxy configurés dans `uv-corporate.toml` ;
- capacité à utiliser les modèles de sécurité GitLab internes.

Le pipeline ne télécharge pas directement les dépendances depuis un index public.

## Jobs

| Job | Étape | Contrôles |
|---|---|---|
| `tests` | `test` | Compilation, tests unitaires, contraintes de release |
| `sast` | `test` | Analyse statique via le modèle GitLab |
| `docs:build` | `documentation` | `mkdocs build --strict`, artefact `site/` |
| `pages` | `deploy` | Publication de `public/` sur la branche par défaut |

## Variables et secrets

Les tests actuels n'appellent pas Azure ni les portails réels. Aucun secret n'est nécessaire pour le build documentaire.

Si un futur test d'intégration requiert un service :

- utiliser une variable GitLab protégée et masquée ;
- limiter le job aux branches protégées ;
- ne jamais afficher sa valeur ;
- prévoir un timeout et un mode hors ligne pour les merge requests.

## Reproduire localement

```bash
uv --config-file uv-corporate.toml sync --locked --group dev
uv --config-file uv-corporate.toml pip install \
  --python .venv/bin/python --requirement docs/requirements.txt
uv run python -m compileall -q backend scripts
PYTHONPATH=backend uv run python -m unittest discover -s tests -p "test_*.py"
uv run --group dev python scripts/build_release.py --check
uv run --no-sync mkdocs build --strict
```

## Échec du build documentaire

Le mode strict transforme les avertissements en échecs. Contrôler :

- chaque page déclarée dans `nav` ;
- les liens relatifs ;
- les images ;
- les titres dupliqués ;
- la syntaxe YAML ;
- la compatibilité de la version MkDocs verrouillée.

## Publication propre

Le dépôt GitLab destiné à FRA doit être initialisé depuis une branche dont l'historique et les métadonnées ont été validés. Ne pas importer automatiquement des références, remotes ou branches provenant d'un hébergement personnel.
