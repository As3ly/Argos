# Variables d'environnement

Le fichier `.env.example` est la référence versionnée. Les valeurs réelles restent locales ou dans les variables protégées de GitLab.

## Azure OpenAI

| Variable | Obligatoire | Défaut | Usage |
|---|---:|---:|---|
| `AZURE_API_KEY` | Oui | — | Authentification |
| `AZURE_ENDPOINT` | Oui | — | URL de la ressource Azure |
| `DEPLOYMENT` | Oui | — | Nom du déploiement |
| `API_VERSION` | Oui | — | Version de l'API Azure |
| `AZURE_CONNECT_TIMEOUT_S` | Non | `10` | Connexion |
| `AZURE_READ_TIMEOUT_S` | Non | `120` | Lecture |
| `AZURE_WRITE_TIMEOUT_S` | Non | `30` | Écriture |
| `AZURE_POOL_TIMEOUT_S` | Non | `30` | Attente du pool |
| `PROMPT_GEN_MAX_TOKENS` | Non | `9000` | Budget initial de génération |

La génération ajoute jusqu'à 1 000 tokens par nouvelle tentative, avec un plafond de 14 000.

## Proxy

| Variable | Défaut | Usage |
|---|---:|---|
| `ARGOS_HTTP_PROXY` | Proxy FRA | Flux HTTP des scrapers |
| `ARGOS_HTTPS_PROXY` | Proxy FRA | Flux HTTPS des scrapers |
| `HTTP_PROXY` / `http_proxy` | Aucun | Repli système HTTP |
| `HTTPS_PROXY` / `https_proxy` | Aucun | Repli système HTTPS |
| `AZURE_USE_PROXY` | `true` | Active le proxy pour Azure |
| `AZURE_PROXY_URL` | Proxy HTTPS Argos | Surcharge Azure |

Les valeurs du module interne, lorsqu'il est installé, sont prioritaires sur les variables Argos.

## SQLite

| Variable | Défaut | Usage |
|---|---:|---|
| `ARGOS_DB_PATH` | `<racine>/html_scrap.db` | Chemin absolu de la base en mode source |
| `LOCALAPPDATA` | Fourni par Windows | Racine des données de l'exécutable |

Le lanceur Windows positionne lui-même `ARGOS_DB_PATH` vers `%LOCALAPPDATA%\Argos\html_scrap.db`.

## EDF

| Variable | Défaut | Usage |
|---|---:|---|
| `ARGOS_EDF_CAPTCHA_MODE` | `fail` | `fail` ou `prevalidated_session` |
| `ARGOS_EDF_SCRAPING_AUTHORIZED` | `false` | Confirme une autorisation explicite d'EDF |
| `ARGOS_EDF_AUTHORIZED_SESSION_COOKIE` | vide | Session prévalidée autorisée |

`prevalidated_session` exige simultanément l'autorisation et un cookie valide. Le cookie doit rester secret et être renouvelé lorsqu'EDF redemande un CAPTCHA.

## Ajouter une variable

1. Définir un défaut sûr dans le code.
2. Ajouter le nom à `.env.example` sans secret.
3. Documenter son type, son défaut et son usage ici.
4. Ajouter une validation et un test.
5. Vérifier le comportement lorsque la variable est absente ou invalide.
