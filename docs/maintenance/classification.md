# Classification IA

## Fonctionnement actuel

Le traitement comporte trois usages d'Azure OpenAI :

1. génération des critères et mots-clés depuis le prompt utilisateur ;
2. extraction structurée des champs de l'AO ;
3. classification booléenne de pertinence.

Les réponses sont contraintes par des schémas JSON. Un sémaphore limite à dix les appels simultanés.

## Points d'attention

### Perte d'intention

Le classificateur reçoit le méta-prompt généré, pas directement le prompt original. Les critères sont des chaînes libres : une obligation, une préférence et une exclusion ne sont pas représentées par des types distincts.

Une modification du générateur doit donc vérifier particulièrement :

- les négations ;
- les exclusions géographiques ;
- les types de prestations interdits ;
- les conditions obligatoires ;
- la différence entre recherche large et pertinence stricte.

### Score et décision

`score_ia` et `raison` sont produits pendant l'extraction. La décision `pertinent` vient du second appel. Ces valeurs peuvent être incohérentes ; le booléen détermine la vue et le score détermine principalement l'ordre.

### Information absente

Un modèle ne peut pas vérifier une contrainte qui n'apparaît pas dans les données collectées. Il faut distinguer « condition satisfaite » de « information inconnue » dans toute future évolution du schéma.

## Politique recommandée pour les exclusions

Pour une précision élevée :

1. convertir le prompt en critères structurés ;
2. séparer obligations, préférences et exclusions ;
3. attribuer un identifiant stable à chaque critère ;
4. demander une preuve textuelle par critère ;
5. appliquer les exclusions bloquantes par une règle déterministe ;
6. réserver le score aux avis ayant passé les contraintes obligatoires ;
7. envoyer les cas inconnus ou contradictoires dans une file « à vérifier ».

Une exclusion explicite ne doit pas être compensée par un score sémantique élevé.

## Tester une modification

Constituer un jeu de référence versionné sans données sensibles :

- cas clairement pertinents ;
- cas clairement non pertinents ;
- faux positifs signalés ;
- faux négatifs signalés ;
- avis contenant une exclusion ;
- avis où l'information obligatoire est absente.

Mesurer au minimum :

| Mesure | Objectif |
|---|---|
| Précision | Part des AO affichés pertinents qui le sont réellement |
| Rappel | Part des AO réellement pertinents retrouvés |
| Exclusions manquées | Faux positifs violant une règle bloquante |
| Cas indécis | Avis sans information suffisante |

Pour Argos, les exclusions manquées doivent être suivies séparément et considérées comme plus graves qu'un simple écart de score.

## Procédure de changement

1. Sauvegarder le prompt système et la version du modèle évalués.
2. Exécuter le corpus de référence avant modification.
3. Modifier un seul niveau à la fois : générateur, extraction ou classification.
4. Rejouer exactement le même corpus.
5. Comparer les métriques et les raisons.
6. Faire valider des exemples par des utilisateurs métier.
7. Déployer avec un moyen de retour arrière.

Changer uniquement de modèle ou augmenter les tokens ne garantit pas le respect des exclusions.
