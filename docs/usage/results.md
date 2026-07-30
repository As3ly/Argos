# Résultats et alertes

## Cartes d'appels d'offres

Une carte affiche les informations synthétiques disponibles :

- titre ;
- score IA ;
- acheteur et lieu ;
- date de clôture ;
- type de marché, secteur et tags ;
- lien vers l'avis officiel.

Le bouton **Détails** ouvre les champs complémentaires, notamment la référence, le budget, le mot-clé d'origine et la raison produite par l'IA.

## Pertinents et non pertinents

Les deux vues reposent sur la valeur booléenne `pertinent` enregistrée en base :

- `1` : AO pertinent ;
- `0` : AO non pertinent ;
- `NULL` : état historique ou incomplet, normalement absent après un traitement réussi.

Le score sert au classement visuel. Il ne doit pas être interprété seul comme une preuve de conformité.

## Compteurs

| Compteur | Signification |
|---|---|
| `nb_trouves` | Avis bruts uniques insérés par les scrapers |
| `nb_insere` | Avis classifiés effectivement ajoutés à `appels_offres` |

Un écart peut provenir d'une classification encore en cours, d'une réponse IA invalide ou d'un doublon global sur le lien.

## Alertes non bloquantes

Les alertes sont conservées dans `recherches_jobs.warnings_json` et affichées dans le détail.

| Type | Interprétation |
|---|---|
| `pagination_limit` | Une requête a atteint le plafond de 300 avis lus |
| `captcha_required` | EDF demande une validation humaine |
| `access_policy_denied` | La politique du portail EDF n'autorise pas la collecte |
| `authorized_session_config_error` | La session EDF autorisée est absente ou invalide |
| `portal_format_error` | La structure HTML EDF a changé |
| `scraper_error` | Erreur générique d'une source |

Une alerte de source signifie que les résultats sont partiels, pas que les résultats déjà présents sont invalides.

## Suppression d'une recherche

La suppression d'une recherche entraîne, via les clés étrangères SQLite :

- la suppression de ses lignes `raw_recherches` ;
- la suppression de ses lignes `appels_offres`.

Elle ne supprime pas les prompts sauvegardés.
