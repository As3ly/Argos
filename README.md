# Argos

Argos est un outil de **veille d'appels d'offres** orienté technique.
Il automatise 3 étapes :

1. Générer des mots-clés pertinents à partir d'un besoin en langage naturel (Azure OpenAI).
2. Scraper des appels d'offres via les API BOAMP et TED/JOUE.
3. Trier / scorer les résultats avec l'IA et les afficher dans une interface NiceGUI.

---

## Fonctionnalités

- Génération de **mots-clés métier** et d'un **méta-prompt** de pertinence.
- Génération automatique d'un **titre de recherche** (`titre_recherche`) stocké en base.
- Scraping paginé BOAMP/TED + dédoublonnage des liens.
- Stockage SQLite des jobs, raws, et appels d'offres enrichis.
- UI NiceGUI pour lancer les recherches et consulter les résultats.

---

## Stack technique

- **Python 3.13+**
- **uv** (packaging / env / lockfile)
- **NiceGUI** (front)
- **SQLite**
- **Azure OpenAI** (`openai` SDK)

---

## Installation rapide (CLI) avec `uv`

### 1) Installer `uv`

- Windows (PowerShell)

```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

- macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2) Cloner et installer les dépendances

```bash
git clone <URL_DU_REPO>
cd Argos
uv sync
```

> `uv sync` crée/maintient l'environnement virtuel et installe les dépendances du `pyproject.toml`.

### 3) Variables d'environnement

Créer un fichier `.env` à la racine du projet :

```env
AZURE_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
AZURE_ENDPOINT=https://<ressource>.openai.azure.com
DEPLOYMENT=<nom_du_deployment_azure>
API_VERSION=2024-10-21
# Timeout Azure (optionnels)
# AZURE_CONNECT_TIMEOUT_S=10
# AZURE_READ_TIMEOUT_S=120
# AZURE_WRITE_TIMEOUT_S=30
# AZURE_POOL_TIMEOUT_S=30
# Nombre max de tokens en génération mots-clés
# PROMPT_GEN_MAX_TOKENS=900
# Proxy Azure (optionnels)
# AZURE_USE_PROXY=true
# AZURE_PROXY_URL=http://proxy:8080
# Proxy scrapers BOAMP/TED (optionnels)
# ARGOS_HTTP_PROXY=http://proxy:8080
# ARGOS_HTTPS_PROXY=http://proxy:8080
# Optionnel: surcharge DB
# ARGOS_DB_PATH=/chemin/vers/html_scrap.db
```

> Les scrapers et Azure utilisent `framatome.HTTP_PROXY/HTTPS_PROXY` si la lib interne est disponible.
> Sinon ils utilisent `ARGOS_HTTP_PROXY` / `ARGOS_HTTPS_PROXY`, puis un proxy Fra par défaut.

---

## Lancer l'outil

### Mode UI (recommandé)

Depuis la racine du repo :

```bash
uv run backend/ui_app.py
```

Ensuite ouvrir l'URL affichée par NiceGUI (souvent `http://127.0.0.1:8080`).

## Versioning et release Windows

La version applicative est definie dans `backend/version.py` et doit rester synchronisee avec `pyproject.toml`.
Le lock de dependances est volontairement fige sur le Nexus corporate Framatome.

Pour preparer une distribution Windows, suivre le guide :

```text
RELEASE_WINDOWS.md
```

Le script de release genere un executable versionne dans `release/` :

```powershell
uv --config-file uv-corporate.toml sync --group dev --locked
uv run --group dev python scripts/build_release.py
```

### Mode CLI (debug / test local)

```bash
uv run backend/main.py
```

Ce mode permet d'éditer manuellement les groupes de mots-clés avant le scraping.

---

## Workflow utilisateur (UI)

1. Saisir un prompt métier.
2. Choisir la période de publication.
3. Sélectionner les sources BOAMP et/ou TED.
4. Lancer la recherche.
5. Ajuster les mots-clés proposés (ajout/suppression).
6. Valider pour exécuter scraping + tri IA.
7. Consulter les cartes résultat et le détail de chaque AO.

---

## Mini-template de prompt (à copier-coller)

Utilise ce mini-template pour obtenir des résultats plus pertinents :

```text
Contexte entreprise :
[Qui vous êtes, votre activité principale]

Je recherche des appels d'offres sur :
[Domaines techniques précis, ex: maintenance prédictive, instrumentation, essais, simulation numérique]

Je veux prioriser :
[Technologies, méthodes, normes, livrables attendus]

Je ne veux PAS :
[Ce que vous excluez: fourniture matériel, travaux de génie civil, lots non pertinents, etc.]

Zone géographique :
[France entière / régions / départements]

Mots-clés importants (optionnel) :
[Liste libre de termes incontournables]
```

### Exemple rempli

```text
Contexte entreprise :
Bureau d'études spécialisé en essais vibratoires et modélisation.

Je recherche des appels d'offres sur :
Maintenance prédictive de moteurs électriques, analyse vibratoire, capteurs condition monitoring.

Je veux prioriser :
Mesure vibratoire, traitement de signal, diagnostic de défauts, campagne d'essais, jumeau numérique.

Je ne veux PAS :
Fourniture de moteurs neufs, remplacement complet d'équipements, travaux électriques lourds.

Zone géographique :
France métropolitaine.

Mots-clés importants (optionnel) :
vibration, FFT, accéléromètre, défaut roulement, alignement.
```

---

## Structure du projet

```text
backend/
  IAfiltre_async.py    # génération mots-clés + scoring IA
  inspect_db.py        # accès DB SQLite
  pipeline.py          # orchestration async (UI/CLI)
  ui_app.py            # interface NiceGUI
  main.py              # mode CLI
  Scrapers/            # scrapers sources AO
```

---

## Dépannage rapide

- **`ModuleNotFoundError`**
  - Vérifier que vous lancez bien via `uv run ...` après `uv sync`.
- **Erreur Azure API key**
  - Vérifier `AZURE_API_KEY` dans `.env`.
- **Timeout Azure lors de la génération mots-clés**
  - Vérifier `AZURE_ENDPOINT`, `DEPLOYMENT`, `API_VERSION`.
  - Si votre réseau impose un proxy, valider `AZURE_USE_PROXY` / `AZURE_PROXY_URL`.
  - Augmenter `AZURE_READ_TIMEOUT_S` (ex: `120` ou `180`).
  - Réduire `PROMPT_GEN_MAX_TOKENS` (ex: `700` à `900`) pour accélérer la réponse.
- **Aucun résultat**
  - Élargir la période, assouplir le prompt, retirer des exclusions trop strictes.
- **UI ne démarre pas**
  - Vérifier que NiceGUI est bien installée dans l'environnement `uv`.

---

## Commandes utiles

```bash
# installer / mettre à jour env
uv sync

# lancer UI
uv run backend/ui_app.py

# lancer mode CLI
uv run backend/main.py

# compilation rapide des modules (sanity check)
uv run python -m compileall backend
```
