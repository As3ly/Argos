# Sauvegarde et opérations SQLite

## Sauvegarder

Arrêter de préférence Argos, puis utiliser l'API de sauvegarde SQLite :

```bash
sqlite3 html_scrap.db ".backup 'argos-backup-2026-07-30.db'"
```

Pour la version Windows :

```powershell
sqlite3 "$env:LOCALAPPDATA\Argos\html_scrap.db" ".backup 'argos-backup.db'"
```

La commande `.backup` est préférable à une simple copie lorsque la base utilise WAL, car une écriture récente peut encore se trouver dans le fichier `-wal`.

## Vérifier une sauvegarde

```bash
sqlite3 argos-backup-2026-07-30.db "PRAGMA integrity_check;"
sqlite3 argos-backup-2026-07-30.db "PRAGMA foreign_key_check;"
```

Le premier résultat attendu est `ok`. La seconde commande ne doit retourner aucune ligne.

Tester régulièrement une restauration sur un poste ou dans un dossier isolé :

```bash
ARGOS_DB_PATH=/tmp/argos-restore.db uv run backend/ui_app.py
```

## Inspecter l'activité

```sql
SELECT id, titre, statut, nb_trouves, nb_insere, date_lancement
FROM recherches_jobs
ORDER BY id DESC
LIMIT 20;

SELECT source, pertinent, COUNT(*) AS nombre
FROM appels_offres
GROUP BY source, pertinent
ORDER BY source, pertinent;

SELECT search_id, source, COUNT(*) AS raws_restants
FROM raw_recherches
GROUP BY search_id, source
ORDER BY search_id DESC;

SELECT version, applied_at
FROM schema_migrations
ORDER BY applied_at, version;
```

## Mesurer la taille

```bash
ls -lh html_scrap.db html_scrap.db-wal html_scrap.db-shm 2>/dev/null
sqlite3 html_scrap.db "PRAGMA page_count; PRAGMA page_size; PRAGMA freelist_count;"
```

La taille logique approximative est `page_count × page_size`.

## Maintenance du fichier

Après une sauvegarde et hors période d'utilisation :

```bash
sqlite3 html_scrap.db "PRAGMA wal_checkpoint(TRUNCATE);"
sqlite3 html_scrap.db "PRAGMA optimize;"
```

`VACUUM` réécrit entièrement la base. Ne l'utiliser que si un volume important a été supprimé, avec suffisamment d'espace disque et après sauvegarde :

```bash
sqlite3 html_scrap.db "VACUUM;"
```

## Restaurer

1. Fermer Argos.
2. Sauvegarder le fichier actuel, même s'il paraît corrompu.
3. Vérifier l'intégrité de la sauvegarde choisie.
4. Remplacer la base ou pointer `ARGOS_DB_PATH` vers la copie restaurée.
5. Redémarrer Argos pour appliquer les migrations manquantes.
6. Contrôler l'historique, les prompts et les compteurs.

## Opérations interdites en exploitation

- Supprimer directement des lignes sans sauvegarde.
- Modifier manuellement `schema_migrations`.
- Copier uniquement le fichier `.db` pendant une écriture WAL.
- Désactiver les clés étrangères pour contourner une erreur.
- Versionner une base contenant des prompts ou des résultats utilisateur.
