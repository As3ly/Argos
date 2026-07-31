# Maintenir les scrapers

## Méthode de diagnostic

1. Identifier la source et le groupe de mots-clés.
2. Relever le statut HTTP et le type d'exception sans journaliser de cookie.
3. Reproduire avec une requête minimale sur le réseau FRA.
4. Comparer la réponse reçue avec le parseur et les champs attendus.
5. Vérifier la période, la pagination et le dédoublonnage.
6. Corriger le parseur ou la requête.
7. Ajouter un test de non-régression à partir d'un échantillon anonymisé.
8. Vérifier qu'une panne reste non bloquante.

## BOAMP

Surveiller en priorité :

- l'endpoint OpenDataSoft/Huwise ;
- le nom du dataset ;
- la syntaxe ODSQL ;
- la liste `BOAMP_SELECT_FIELDS` ;
- les noms des champs de dates et de liens ;
- la limite de 100 résultats par appel.

Une erreur `400` indique souvent une requête ou un champ devenu invalide. Une erreur `404` suggère un endpoint ou un dataset obsolète.

## TED / JOUE

Surveiller :

- la version de l'API ;
- la syntaxe de requête ;
- les codes de type d'avis ;
- le champ du pays d'exécution ;
- la forme de la pagination ;
- les structures multilingues et listes dans les champs.

Le périmètre actuel filtre `FRA`. Toute extension géographique doit être explicite et testée, car elle augmente fortement le volume.

## Garde-fous de volume

Les deux scrapers s'arrêtent après 300 avis lus par groupe. Une alerte `pagination_limit` est alors ajoutée. Si ce cas devient fréquent :

1. améliorer la précision des groupes de mots-clés ;
2. réduire la période ;
3. analyser la capacité Azure et SQLite ;
4. seulement ensuite envisager de modifier le plafond.

Augmenter le plafond sans pagination d'interface et sans limitation globale de concurrence peut dégrader la mémoire, le nombre d'appels Azure et les messages NiceGUI.

## Critères d'acceptation

Une correction de scraper est prête lorsque :

- le cas signalé est couvert par un test ;
- les limites et délais restent explicites ;
- les autres sources continuent en cas d'échec ;
- les compteurs sont cohérents ;
- aucun secret n'apparaît dans les logs ;
- la documentation et le changelog sont à jour.
