# Ajouter une source

## Contrat minimal

Un scraper Argos doit exposer une fonction compatible avec :

```python
def scrape_source_into_raw(
    search_id: int,
    mots_recherche: list,
    sess,
    date_pub_min: date | None = None,
    date_pub_max: date | None = None,
) -> None:
    ...
```

Il doit :

1. appliquer la période demandée ;
2. parcourir les groupes de mots-clés ;
3. utiliser un délai réseau explicite ;
4. respecter proxy FRA et TLS système ;
5. paginer avec un garde-fou ;
6. produire un lien stable ;
7. dédupliquer dans la recherche ;
8. appeler `inserer_raw_recherche()` ;
9. incrémenter `nb_trouves` ;
10. lever une exception explicite en cas d'échec.

Il ne doit pas décider de la pertinence ni écrire directement dans `appels_offres`.

## Choisir le transport

- API HTTP ou HTML statique : `requests.Session`.
- Cookies et formulaires : `requests.Session`.
- Page réellement dépendante de JavaScript ou d'interactions : Playwright uniquement si `requests` ne suffit pas.
- Lorsqu'un navigateur est indispensable, utiliser Microsoft Edge conformément aux conventions du projet.

Playwright ne doit jamais servir à contourner un CAPTCHA, une authentification ou une politique d'accès.

## Réseau commun

```python
from proxy_config import get_requests_proxies
from tls_config import inject_truststore_once

inject_truststore_once()
session = requests.Session()
session.proxies.update(get_requests_proxies())
```

Ne pas copier une adresse de proxy dans un nouveau scraper. La résolution reste centralisée.

## Intégration

1. Ajouter `backend/Scrapers/scrap_<code>.py`.
2. Importer la fonction dans `backend/Scrapers/__init__.py`.
3. Ajouter `(code, fonction)` dans `SCRAPERS`.
4. Ajouter le libellé dans `SCRAPER_LABELS`.
5. Initialiser la source dans `db.repository.initialize_database()`.
6. Ajouter des tests hors réseau avec des réponses représentatives.
7. Documenter la source dans [Réseau et sources](../architecture/network-and-sources.md).
8. Ajouter ses erreurs dans [Statuts et alertes](../reference/statuses.md).

## Erreurs non bloquantes

Pour un message spécifique dans l'interface, l'exception peut définir :

```python
class SourceFormatError(RuntimeError):
    warning_type = "portal_format_error"
    user_message = "Le format de la source a changé."
```

L'orchestrateur capture l'exception, persiste l'alerte et passe à la source suivante.

## Tests attendus

- parsing d'une réponse valide ;
- réponse vide ;
- pagination ;
- date aux bornes de la période ;
- doublon de lien ;
- erreur HTTP ;
- changement de format ;
- timeout ;
- persistance de l'alerte et continuation de la source suivante ;
- proxy et validation TLS non désactivée.

Les tests unitaires ne doivent pas envoyer de requêtes aux portails réels.
