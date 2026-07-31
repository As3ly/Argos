# Première recherche

## 1. Décrire le besoin

Rédiger un prompt qui sépare clairement :

- le contexte de l'entreprise ;
- les prestations recherchées ;
- les critères prioritaires ;
- les exclusions ;
- la zone géographique ;
- les mots-clés incontournables.

Exemple :

```text
Nous recherchons des prestations d'analyse vibratoire et de maintenance
prédictive sur moteurs électriques en France métropolitaine.

Inclure : diagnostic de roulements, accéléromètres, traitement du signal.
Exclure : fourniture de moteurs neufs et travaux électriques lourds.
```

Une exclusion doit être formulée explicitement. Les formulations courtes mais ambiguës produisent des critères moins fiables.

## 2. Choisir la période et les sources

La période par défaut couvre les sept derniers jours. Les sources proposées sont :

- BOAMP ;
- TED / JOUE.

## 3. Vérifier les mots-clés

Argos génère un titre, des critères et plusieurs groupes de mots-clés. Avant de confirmer :

1. supprimer les termes hors domaine ;
2. conserver des termes larges pour le rappel ;
3. ajouter les technologies ou acronymes indispensables ;
4. éviter plusieurs variantes presque identiques ;
5. vérifier que les exclusions restent présentes dans les critères affichés.

Les mots-clés servent à collecter largement. La pertinence finale est décidée plus tard par le classificateur.

## 4. Suivre le traitement

Le statut passe normalement par :

```text
en_cours → generation_mots_cle → scraping → tri_ia → termine
```

Une erreur propre à une source apparaît dans le détail de la recherche sans faire échouer le pipeline complet. Une erreur de génération ou de pipeline nécessite en revanche un diagnostic.

## 5. Contrôler les résultats

Ouvrir le détail de la recherche puis :

- examiner les AO pertinents ;
- consulter le score, la raison et les informations extraites ;
- basculer vers les AO non pertinents pour contrôler les faux négatifs ;
- vérifier les alertes de pagination ou de source ;
- ouvrir le lien d'origine avant toute décision métier.

Le panneau de détail affiche les paramètres, les alertes éventuelles et les cartes d'appels d'offres classées.

!!! note "Responsabilité de validation"
    La classification aide au tri ; elle ne remplace pas la lecture de l'avis officiel. Un champ absent de la réponse de la source ne peut pas être déduit de manière fiable.
