# Dépannage

## La génération des mots-clés échoue

Vérifier :

- `AZURE_API_KEY`, `AZURE_ENDPOINT`, `DEPLOYMENT`, `API_VERSION` ;
- le proxy Azure ;
- le certificat système ;
- les délais de connexion et de lecture ;
- la disponibilité du déploiement Azure.

Le job passe normalement à `erreur_generation`.

## Une source ne retourne rien

1. Ouvrir le détail de la recherche.
2. Lire les alertes.
3. Vérifier la période et les mots-clés.
4. Contrôler la connectivité via le proxy FRA.
5. Tester une requête minimale sans modifier la production.
6. Comparer les compteurs récents de cette source.

Un volume nul n'est pas toujours une panne : la requête peut être trop restrictive.

## EDF demande un CAPTCHA

Comportement attendu :

- EDF est ignoré ;
- une alerte `captcha_required` apparaît ;
- BOAMP et TED continuent.

Ne pas automatiser la résolution. Si une autorisation EDF existe, renouveler la session prévalidée conformément à la procédure autorisée.

## EDF est refusé par `robots.txt`

Sans autorisation explicite, Argos enregistre `access_policy_denied`. Vérifier la décision d'accès avec le responsable de la source avant toute activation.

## La base est verrouillée

Symptômes : `database is locked`, compteurs non mis à jour ou raws conservés.

- vérifier qu'une seule opération administrative écrit dans la base ;
- laisser finir le tri IA ;
- éviter un outil SQLite ouvert en transaction d'écriture ;
- contrôler l'espace disque ;
- redémarrer proprement après sauvegarde si le verrou persiste.

Ne pas supprimer les fichiers `-wal` ou `-shm` pendant l'exécution.

## Des raws restent après un job terminé

Causes possibles :

- extraction Azure vide ou invalide ;
- classification invalide ;
- avis déjà présent globalement dans `appels_offres` ;
- erreur SQLite à l'insertion ou à la suppression.

Inspecter les raws par `search_id`, puis les logs du traitement avant toute suppression.

## Les compteurs diffèrent

`nb_trouves` compte les raws collectés ; `nb_insere` compte les AO nouveaux insérés. Un doublon global, un raw en échec ou un traitement en cours crée un écart.

## Message trop long ou buffer dépassé

NiceGUI échange les événements par WebSocket et applique une limite proche de 1 Mo à un message entrant. Relever le texte exact :

- « message trop long » après collage : réduire le prompt ou le champ envoyé ;
- erreur en ouvrant une recherche volumineuse : contrôler le nombre de cartes et les rafraîchissements ;
- erreur Windows `10055` : rechercher un épuisement de sockets, une pression mémoire ou trop de recherches concurrentes.

Ne pas augmenter un buffer avant d'avoir identifié s'il s'agit du navigateur, de NiceGUI, du proxy ou du système.

## L'interface ne démarre pas

- vérifier le port `8080` ;
- fermer une ancienne instance ;
- vérifier `uv sync` ;
- consulter `%LOCALAPPDATA%\Argos\argos_startup.log` pour l'exécutable ;
- exécuter `uv run backend/ui_app.py` pour obtenir une trace complète en développement.

## Le pipeline GitLab échoue

- `uv` absent : corriger le runner FRA ;
- lock refusé : régénérer avec `uv-corporate.toml` ;
- SAST indisponible : vérifier les modèles autorisés sur l'instance GitLab ;
- MkDocs strict : corriger le lien ou la navigation signalés ;
- release check : réaligner version, Nexus, proxy ou TLS.
