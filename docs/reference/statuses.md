# Statuts et alertes

## Statuts de recherche

| Statut | Signification |
|---|---|
| `en_cours` | Job créé, assistant de mots-clés en préparation |
| `generation_mots_cle` | Appel Azure de génération |
| `scraping` | Collecte des sources |
| `tri_ia` | Extraction et classification des raws |
| `termine` | Pipeline achevé |
| `erreur_generation` | Échec de génération des critères |
| `erreur_scraper` | Registre absent, aucune source ou erreur globale de scraping |
| `erreur_pipeline` | Exception non gérée pendant le pipeline |

Les erreurs individuelles de BOAMP ou TED ne changent pas nécessairement le statut final. Elles sont enregistrées comme alertes.

## Structure d'une alerte

```json
{
  "type": "scraper_error",
  "severity": "error",
  "source": "ted",
  "message": "Message destiné à l'utilisateur"
}
```

Une alerte de pagination peut aussi contenir `limited_searches` :

```json
{
  "type": "pagination_limit",
  "severity": "warning",
  "limited_searches": [
    {
      "recherche": "maintenance moteurs",
      "nb_offres_lues": 300,
      "nb_inserts": 215,
      "seuil": 300
    }
  ]
}
```

## Types connus

| Type | Sévérité habituelle | Action |
|---|---|---|
| `pagination_limit` | warning | Réduire période ou élargissement sémantique |
| `scraper_error` | error | Diagnostiquer HTTP, proxy, TLS ou parsing |

## Interprétation opérationnelle

- `termine` avec alertes : recherche réussie mais partielle.
- `termine` sans résultats : requête sans correspondance ou données dédupliquées.
- `tri_ia` prolongé : volume important, Azure lent ou raws en difficulté.
- raws restants après `termine` : échecs IA ou doublons à diagnostiquer.
