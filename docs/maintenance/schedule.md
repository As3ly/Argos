# Politique et calendrier de maintenance

La maintenance d'Argos couvre quatre domaines : disponibilité des sources, qualité de la classification, intégrité SQLite et reproductibilité de la release.

## À chaque mise en production

1. Sauvegarder la base de référence.
2. Vérifier la cohérence des versions.
3. Exécuter les tests et le build MkDocs strict.
4. Tester au moins une recherche courte sur BOAMP et TED.
5. Vérifier les vues pertinentes et non pertinentes.
6. Contrôler le SHA256 de l'exécutable.
7. Ajouter l'évolution au changelog.

## Chaque semaine

| Contrôle | Méthode | Signal d'alerte |
|---|---|---|
| Recherches terminées | Compter les statuts récents | Jobs durablement en `scraping` ou `tri_ia` |
| Résultats par source | Agrégation SQLite | Chute inhabituelle à zéro |
| Raws restants | Compter `raw_recherches` | Accumulation après jobs terminés |
| Alertes | Lire `warnings_json` | Erreurs HTTP ou limites répétées |
| Sauvegarde | `.backup` SQLite | Sauvegarde absente ou non vérifiée |

## Chaque mois

- Exécuter `PRAGMA integrity_check` et `PRAGMA foreign_key_check`.
- Vérifier la taille de la base et du fichier WAL.
- Contrôler les dates d'expiration des accès et secrets.
- Rejouer un petit corpus d'AO connus pour surveiller les faux positifs.
- Vérifier les changements d'API BOAMP/TED.
- Contrôler que le lock utilise uniquement le Nexus interne.
- Vérifier la construction de la documentation dans GitLab.

## Chaque trimestre

- Tester une restauration complète de la base.
- Revoir les dépendances, avis de sécurité et compatibilités Python.
- Auditer les variables GitLab protégées et les personnes autorisées.
- Revoir les limites de pagination à partir des volumes observés.
- Examiner les corrections utilisateurs de classification.
- Mettre à jour les captures d'écran si l'interface a changé.
- Supprimer les branches de travail obsolètes dans le GitLab FRA selon la politique du projet.

## Maintenance déclenchée par événement

Intervenir immédiatement lorsque :

- une API modifie son schéma, son endpoint ou son authentification ;
- le proxy, le certificat ou le Nexus change ;
- le déploiement Azure est remplacé ;
- une migration SQLite est nécessaire ;
- une erreur de classification est répétitive et concerne une exclusion explicite ;
- une vulnérabilité affecte une dépendance utilisée ;
- un changement NiceGUI modifie le protocole WebSocket ou le rendu.

## Priorité des incidents

| Priorité | Exemple | Réponse attendue |
|---|---|---|
| P1 | Base corrompue, secrets exposés, toutes les recherches indisponibles | Arrêt, sauvegarde, confinement et restauration |
| P2 | Azure ou deux sources majeures indisponibles | Diagnostic le jour même |
| P3 | Une source partielle, classification dégradée, alerte répétée | Correction planifiée rapidement |
| P4 | Documentation, ergonomie ou optimisation sans impact immédiat | Prochaine maintenance |

## Trace de maintenance

Chaque intervention doit conserver :

- date et version ;
- symptôme ;
- périmètre ;
- cause identifiée ;
- sauvegarde réalisée ;
- modifications et tests ;
- résultat du déploiement ;
- action de suivi éventuelle.

Aucun secret ou contenu sensible ne doit apparaître dans cette trace.
