# Structure du dépôt

```text
Argos/
├── backend/
│   ├── Scrapers/
│   │   ├── __init__.py
│   │   ├── scrap_boamp.py
│   │   ├── scrap_edf.py
│   │   └── scrap_ted.py
│   ├── db/
│   │   ├── migrations.py
│   │   ├── repository.py
│   │   └── schema.py
│   ├── IAfiltre_async.py
│   ├── pipeline.py
│   ├── proxy_config.py
│   ├── tls_config.py
│   ├── ui_app.py
│   ├── run_packaged.py
│   └── version.py
├── docs/
├── scripts/
│   ├── build_release.py
│   └── build_user_guide.py
├── tests/
├── Argos.spec
├── mkdocs.yml
├── pyproject.toml
├── uv.lock
├── uv-corporate.toml
└── .gitlab-ci.yml
```

## Points d'entrée

| Fichier | Usage |
|---|---|
| `backend/ui_app.py` | Exécution de développement |
| `backend/run_packaged.py` | Exécution packagée Windows |
| `backend/main.py` | Diagnostic CLI |
| `scripts/build_release.py` | Contrôle et génération d'une release |
| `mkdocs.yml` | Configuration du site documentaire |

## Fichiers générés ou locaux

Ces éléments ne doivent pas être versionnés :

- `.env` et secrets ;
- `.venv/` ;
- `html_scrap.db` et autres bases locales ;
- `build/`, `dist/`, `release/` ;
- `site/` et `public/` ;
- logs et artefacts navigateur ;
- caches Python et `.DS_Store`.

## Règles de modification

- Une évolution du schéma implique une migration idempotente.
- Une nouvelle variable implique une entrée dans `.env.example` et dans la référence MkDocs.
- Une nouvelle source implique son test, son enregistrement et sa documentation.
- Une modification de version doit rester cohérente entre `backend/version.py` et `pyproject.toml`.
- Toute page Markdown ajoutée doit figurer dans `nav` ou être volontairement exclue avant un build strict.
