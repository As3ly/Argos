# Pipeline GitLab

Le fichier `.gitlab-ci.yml` couvre la qualité, la construction de la
documentation et la publication GitLab Pages.

## Prérequis du runner FRA

- accès au dépôt ;
- `uv` installé ;
- Python 3.13 disponible ;
- accès au Nexus et au proxy configurés dans `uv-corporate.toml` ;
- magasin de certificats Windows contenant l'autorité interne FRA.

Le pipeline ne télécharge pas directement les dépendances depuis un index public.

## Jobs

| Job | Étape | Contrôles |
|---|---|---|
| `tests` | `test` | Compilation, tests unitaires, contraintes de release |
| `docs:build` | `documentation` | `mkdocs build --strict`, artefact `site/` |
| `pages` | `deploy` | Publication de `public/` sur la branche par défaut |

## Compatibilité avec le runner Windows

Le runner FRA utilise l'exécuteur `shell` avec PowerShell. La pipeline n'utilise
donc ni composant contenant des commandes Bash, ni image Docker, ni chemin
`.venv/bin/python`.

Les variables `UV_SYSTEM_CERTS=true` et `UV_NATIVE_TLS=true` couvrent
respectivement les versions anciennes et récentes de `uv`. Elles demandent
l'utilisation du magasin de certificats Windows et évitent l'erreur
`UnknownIssuer` lors de l'accès au Nexus interne. Le réglage est également
présent dans `uv-corporate.toml`.

Les jobs documentaires utilisent :

```powershell
uv run --no-project --with-requirements docs/requirements.txt mkdocs build --strict
```

`--no-project` est important : MkDocs n'a pas besoin des dépendances de
l'application. La documentation reste donc constructible même si une
dépendance métier n'est pas disponible sur le registre du runner.

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
uv run python -m compileall -q backend scripts
PYTHONPATH=backend uv run python -m unittest discover -s tests -p "test_*.py"
uv run --group dev python scripts/build_release.py --check
uv --config-file uv-corporate.toml run --no-project \
  --with-requirements docs/requirements.txt \
  mkdocs build --strict
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
