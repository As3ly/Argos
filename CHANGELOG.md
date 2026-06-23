# Changelog

Toutes les evolutions notables d'Argos sont documentees ici.

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
