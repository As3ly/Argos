# Release Windows

La version applicative est définie dans `backend/version.py` et doit correspondre à `project.version` dans `pyproject.toml`.

## Préparer

1. Mettre à jour `APP_VERSION`.
2. Mettre à jour `pyproject.toml`.
3. Ajouter une entrée dans `CHANGELOG.md`.
4. Synchroniser le lock uniquement via le Nexus interne.
5. Construire la documentation en mode strict.
6. Sauvegarder et tester une copie de la base d'une version précédente.

```powershell
uv --config-file uv-corporate.toml sync --locked --group dev
uv --config-file uv-corporate.toml pip install --python .venv\Scripts\python.exe --requirement docs\requirements.txt
$env:PYTHONPATH = "backend"
uv run python -m unittest discover -s tests -p "test_*.py"
uv run --no-sync mkdocs build --strict
uv run --group dev python scripts/build_release.py --check
```

Le contrôle `--check` vérifie :

- la cohérence des versions ;
- la présence du Nexus interne dans le lock ;
- l'absence d'URL PyPI publique ;
- la configuration proxy et TLS ;
- l'utilisation du helper TLS par Azure et les scrapers.

## Construire

Sur Windows :

```powershell
uv run --group dev python scripts/build_release.py
```

Le script nettoie `build/` et `dist/`, lance PyInstaller puis produit :

```text
release\Argos-<version>-windows-x64.exe
release\Argos-<version>-windows-x64.exe.sha256.txt
```

## Recette

Sur un poste de test représentatif :

1. vérifier le SHA256 ;
2. démarrer l'exécutable ;
3. confirmer l'affichage de la version ;
4. ouvrir une base existante et vérifier les migrations ;
5. créer, modifier et supprimer un prompt sauvegardé ;
6. lancer une recherche courte BOAMP/TED ;
7. consulter pertinents, non pertinents et détail ;
8. fermer puis relancer l'application ;
9. vérifier la conservation de la base.

## Distribuer

Distribuer uniquement l'exécutable et son checksum via le canal interne approuvé. Ne jamais joindre :

- `.env` ;
- la base SQLite d'un utilisateur ;
- les logs ;
- le dossier source complet ;
- les artefacts intermédiaires PyInstaller.

Le guide détaillé historique reste disponible dans `RELEASE_WINDOWS.md`.
