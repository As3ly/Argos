# Configuration

Argos charge le fichier `.env` situé à la racine du projet. Le fichier `.env.example` constitue la référence versionnée des variables disponibles.

## Règles de sécurité

- Ne jamais versionner `.env`.
- Ne jamais copier une clé Azure ou un cookie EDF dans la documentation, un ticket ou un log.
- Utiliser des variables GitLab protégées et masquées pour la CI/CD.
- Renouveler immédiatement tout secret exposé.
- Restreindre le cookie de session EDF à une autorisation explicite et à la durée nécessaire.

## Configuration minimale

```env
AZURE_API_KEY=<secret>
AZURE_ENDPOINT=https://<ressource>.openai.azure.com
DEPLOYMENT=<deploiement>
API_VERSION=2024-10-21
```

Les quatre valeurs sont validées au premier appel à Azure OpenAI. L'interface peut démarrer sans elles, mais la génération des mots-clés échouera.

## Réseau FRA

Le proxy est résolu dans cet ordre :

1. `ARGOS_HTTP_PROXY` et `ARGOS_HTTPS_PROXY` ;
2. valeurs fournies par le module interne lorsqu'il est disponible ;
3. variables système `HTTP_PROXY` et `HTTPS_PROXY` ;
4. connexion directe si aucune valeur n'est configurée.

Argos ne contient pas d'adresse de proxy codée en dur : elle deviendrait rapidement
obsolète selon le site, le VPN ou la politique réseau. Sur un poste qui exige le
proxy FRA, le renseigner dans `.env` ou utiliser le module interne.

Azure utilise le proxy HTTPS Argos lorsqu'il est configuré. Pour le désactiver explicitement :

```env
AZURE_USE_PROXY=false
```

Le magasin de certificats du système est injecté via `truststore`. Cela permet de respecter l'inspection TLS de l'environnement d'entreprise sans désactiver la validation des certificats.

## Délais Azure

| Variable | Défaut | Rôle |
|---|---:|---|
| `AZURE_CONNECT_TIMEOUT_S` | `10` | Établissement de la connexion |
| `AZURE_READ_TIMEOUT_S` | `120` | Attente de la réponse |
| `AZURE_WRITE_TIMEOUT_S` | `30` | Envoi de la requête |
| `AZURE_POOL_TIMEOUT_S` | `30` | Attente d'une connexion disponible |
| `PROMPT_GEN_MAX_TOKENS` | `9000` | Budget initial de génération des critères |

Augmenter un délai uniquement après avoir distingué un traitement lent d'un problème de proxy, de certificat ou de disponibilité Azure.

## Base SQLite

En développement, la base par défaut est `html_scrap.db` à la racine du projet. Pour isoler un environnement :

```env
ARGOS_DB_PATH=/chemin/absolu/vers/argos.db
```

Sur la version Windows packagée, le lanceur impose `%LOCALAPPDATA%\Argos\html_scrap.db`.

## Source EDF

Le mode sûr par défaut est :

```env
ARGOS_EDF_CAPTCHA_MODE=fail
ARGOS_EDF_SCRAPING_AUTHORIZED=false
ARGOS_EDF_AUTHORIZED_SESSION_COOKIE=
```

Dans ce mode, un CAPTCHA ou une interdiction dans `robots.txt` désactive EDF pour la recherche courante, tandis que BOAMP et TED continuent.

Le mode `prevalidated_session` est réservé à une autorisation explicite d'EDF :

```env
ARGOS_EDF_CAPTCHA_MODE=prevalidated_session
ARGOS_EDF_SCRAPING_AUTHORIZED=true
ARGOS_EDF_AUTHORIZED_SESSION_COOKIE=<cookie_fourni_ou_valide_dans_le_cadre_autorise>
```

!!! danger "Aucun contournement"
    Cette configuration ne résout pas un CAPTCHA. Elle réutilise uniquement une session déjà validée dans un cadre autorisé. Si la session expire, EDF est ignoré et une alerte est enregistrée.

La liste exhaustive des variables figure dans [Variables d'environnement](../reference/environment.md).
