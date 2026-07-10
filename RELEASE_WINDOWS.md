# Release Windows Argos

Ce guide sert a repackager Argos sur un PC Windows apres avoir pull la branche de release.

Version courante prevue : **1.2.0**.

## 1. Recuperer le code

```powershell
git checkout codex/test-main-clean-ted-boamp-ui
git pull origin codex/test-main-clean-ted-boamp-ui
```

## 2. Installer / synchroniser l'environnement

Depuis la racine du repo :

```powershell
uv --config-file uv-corporate.toml sync --group dev --locked
```

La configuration `uv-corporate.toml` force :

- le Nexus corporate `https://nexus.framatome.corp/repository/py-pypi/simple`
- le proxy Fra `http://163.116.128.80:8080`
- `native-tls = true` pour utiliser le magasin de certificats Windows avec l'inspection SSL corporate

Ne pas relancer `uv lock` sans cette configuration, sinon `uv.lock` peut repasser sur PyPI.

## 3. Verifier la version

```powershell
uv run python -c "from backend.version import APP_DISPLAY_NAME; print(APP_DISPLAY_NAME)"
```

La commande doit afficher :

```text
Argos v1.2.0
```

## 4. Verifier rapidement le code

```powershell
uv run python -m compileall backend
uv run --group dev python scripts/build_release.py --check
```

## 5. Builder l'executable

```powershell
uv run --group dev python scripts/build_release.py
```

Le script nettoie `build/` et `dist/`, lance PyInstaller, puis cree :

```text
release\Argos-1.2.0-windows-x64.exe
release\Argos-1.2.0-windows-x64.exe.sha256.txt
```

## 6. Test local avant distribution

Lancer :

```powershell
.\release\Argos-1.2.0-windows-x64.exe
```

Verifier :

- le navigateur s'ouvre sur `http://127.0.0.1:8080`
- l'interface affiche `v1.2.0`
- l'historique existant est conserve
- une nouvelle recherche peut etre lancee
- la modal des prompts sauvegardes s'ouvre

Les donnees utilisateur restent dans :

```text
%LOCALAPPDATA%\Argos\html_scrap.db
```

Les logs de demarrage sont dans :

```text
%LOCALAPPDATA%\Argos\argos_startup.log
```

## 7. Distribuer

Distribuer uniquement :

```text
Argos-1.2.0-windows-x64.exe
Argos-1.2.0-windows-x64.exe.sha256.txt
```

Important : demander aux collegues de fermer l'ancienne version avant de lancer la nouvelle.

## 8. Regles pour les prochaines versions

- Changer `APP_VERSION` dans `backend/version.py`
- Changer `version` dans `pyproject.toml`
- Regenerer le lock uniquement avec `uv --config-file uv-corporate.toml lock`
- Ajouter une entree dans `CHANGELOG.md`
- Creer un commit `Release X.Y.Z`
- Creer un tag Git `vX.Y.Z`
- Rebuilder avec ce guide
