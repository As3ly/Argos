# Changelog

Toutes les evolutions notables d'Argos sont documentees ici.

## [Non publie]

### Retire

- Le scraper EDF, son option d'interface et sa configuration, car le portail ne constitue pas une source automatisable suffisamment fiable pour Argos.

### Ajoute

- Documentation technique et d'exploitation en MkDocs : prise en main, architecture, maintenance, SQLite et references.
- Pipeline GitLab CI pour les tests, le controle du paquet Windows, la construction stricte de la documentation et sa publication avec GitLab Pages.
- Guide d'installation et d'utilisation entièrement actualisé avec les écrans de la version 1.2.0 et le tutoriel des prompts sauvegardés.
- Affichage des erreurs partielles de source dans le detail d'une recherche.

### Technique

- Les erreurs d'un scraper sont persistees mais ne bloquent plus les sources suivantes.
- Les alertes de plusieurs sources sont maintenant ajoutees sans s'ecraser.
- Initialisation unique du magasin de certificats systeme pour tous les scrapers.

## [1.2.0] - 2026-06-23

### Ajoute

- Bibliotheque locale de prompts sauvegardes.
- Grande modal pour ajouter, consulter et relancer des prompts sauvegardes.
- Affichage de la version applicative dans l'interface.
- Logs de demarrage incluant la version de l'application packagee.
- Script de build Windows qui produit un executable versionne et un checksum SHA256.
- Guide de release Windows.

### Technique

- Nouvelle table SQLite `saved_prompts`.
- Migration idempotente `2026_06_23_saved_prompts`.
- Source de version applicative dans `backend/version.py`.
