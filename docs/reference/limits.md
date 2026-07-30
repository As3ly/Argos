# Limites et volumétrie

## Génération de recherche

| Élément | Limite |
|---|---:|
| Critères générés | 5 à 50 |
| Règles générées | 2 à 50 |
| Groupes de mots-clés générés | 3 à 50 |
| Longueur du titre | 8 à 120 caractères |

Le prompt conseille habituellement 5 à 15 groupes. L'interface permet ensuite leur modification.

## Scraping

| Source | Taille de page | Plafond par groupe | Délai |
|---|---:|---:|---:|
| BOAMP | 100 | 300 avis lus | 30 s |
| TED | 100 | 300 avis lus | 30 s |
| EDF | Taille du portail | 300 lignes lues | 30 s par requête |

Le plafond est appliqué séparément à chaque groupe de mots-clés et à chaque source. Avec 15 groupes et trois sources, le nombre théorique d'avis lus peut donc être important, même si les liens sont ensuite dédupliqués.

## Traitement IA

- Une tâche asynchrone est créée pour chaque raw contenant plus de 50 caractères.
- Dix appels Azure au maximum s'exécutent simultanément dans le processus.
- Extraction : trois tentatives, budget initial de 9 000 tokens, plafond 14 000.
- Classification : cinq tentatives, budget initial de 800 tokens, plafond 2 000.
- Les tâches en attente restent en mémoire jusqu'à la fin de la recherche.

Plusieurs recherches lancées en parallèle multiplient la charge globale. Il n'existe pas actuellement de limite globale documentée sur le nombre de jobs simultanés.

## Interface

| Vue | Limite ou cadence |
|---|---:|
| Historique | 20 recherches par page |
| AO pertinents | 300 cartes |
| AO non pertinents | 300 cartes |
| Rafraîchissement accueil | 3 secondes |
| Rafraîchissement détail dédié | 5 secondes |

Une recherche volumineuse peut générer un lot important de mises à jour NiceGUI. Le transport WebSocket possède une limite proche de 1 Mo pour un message entrant.

## SQLite

- Le lien d'un AO est unique dans toute la table, pas seulement dans une recherche.
- Les raws sont dédupliqués par recherche et lien dans le code.
- SQLite convient à une application locale, mais n'est pas prévu ici pour plusieurs processus d'écriture distribués.
- Les écritures IA utilisent WAL, un timeout de 30 secondes et un `busy_timeout` de 5 secondes.

## Augmenter une limite

Avant toute augmentation :

1. mesurer le nombre de groupes, pages, raws et appels Azure ;
2. vérifier la capacité du proxy et les règles de la source ;
3. tester la mémoire et la durée ;
4. paginer l'interface si nécessaire ;
5. limiter les recherches concurrentes ;
6. ajouter un test de charge ;
7. documenter la nouvelle valeur et son impact.
