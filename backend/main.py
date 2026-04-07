# /// script
# dependencies = ["requests", "beautifulsoup4", "truststore", "framatome", "httpx", "jsonschema", "openai", "dotenv"]
# ///

import re
import asyncio

# main.py reste un "mode CLI" pratique pour tester sans UI.
# L'orchestration propre (compatible serveur async) est dans pipeline.py.
from pipeline import create_job_for_prompt, generate_keywords, run_full_pipeline
from db.repository import initialize_database, update_recherche_job


#################################### Init ###############################
prompt_client = (
    "Je recherche des appels d’offres liés à la maintenance prédictive de moteurs électriques "
    "et vibrations mécaniques. Mais je ne veux pas fournir le matériel je ne fais que des essais "
    "technique ou de la modélisations numérique."
)


#################################### Script ###############################
def main(prompt_client: str):
    initialize_database()

    # 1) Créer le job
    search_id = create_job_for_prompt(source="francemarches", statut="en_cours")

    # 2) Appel async N°1 : génération des mots-clés + meta_prompt
    kw = asyncio.run(generate_keywords(search_id=search_id, prompt_client=prompt_client))
    mots_recherche, meta_prompt = kw.mots_recherche, kw.meta_prompt

    ############################# Input de modif (à remplacer par le front plus tard) #############################

    def afficher_mots_cle(mots_recherche):
        print("\n=== Liste actuelle des mots-clés ===")
        if not mots_recherche:
            print("(Liste vide)")
            return
        for i, mots in enumerate(mots_recherche, start=1):
            print(f"{i}: {mots}")

    afficher_mots_cle(mots_recherche)

    # --- Interaction utilisateur ---
    while True:
        print("\nQue souhaitez-vous faire ?")
        print("1 - Supprimer un groupe de mots-clés")
        print("2 - Ajouter un ou plusieurs groupes de mots-clés")
        print("3 - Afficher la liste actuelle")
        print("4 - Continuer")
        choix = input("Votre choix (1/2/3/4) : ").strip().lower()

        if choix == "1":
            index = input("Numéro du groupe à supprimer : ").strip()
            if index.isdigit() and 1 <= int(index) <= len(mots_recherche):
                index = int(index) - 1
                print(f"Suppression : {mots_recherche[index]}")
                mots_recherche.pop(index)
            else:
                print("❌ Numéro invalide.")

        elif choix == "2":
            print("\n--- AJOUT DE MOTS-CLÉS ---")
            print("Mini tuto :")
            print(" - Utilisez la virgule OU le point-virgule pour séparer les groupes")
            print(" - Exemple : moteurs electriques, vibration capteur; analyse numerique")
            print(" - Chaque groupe sera automatiquement découpé en mots individuels.\n")

            saisie = input("Entrez vos groupes de mots : ").strip()

            if not saisie:
                print("❌ Aucun mot saisi.")
                continue

            # On accepte ',' ou ';'
            groupes = re.split(r"[;,]", saisie)
            groupes = [g.strip() for g in groupes if g.strip()]

            if not groupes:
                print("❌ Aucun groupe valide détecté.")
                continue

            for g in groupes:
                liste_mots = g.split()
                mots_recherche.append(liste_mots)
                print(f"Ajouté : {liste_mots}")

        elif choix == "3":
            afficher_mots_cle(mots_recherche)

        elif choix == "4":
            print("\nValidation effectuée. Suite du script…\n")
            break

        else:
            print("❌ Choix invalide.")

    # --- Mise à jour de la requête ---
    requete_str = ",".join(" ".join(g) for g in mots_recherche)
    update_recherche_job(search_id, requete=requete_str)

    # --- SCRAPING + IA (orchestrés) ---
    print("début du scraping + tri IA:")
    asyncio.run(
        run_full_pipeline(
            search_id=search_id,
            mots_recherche=mots_recherche,
            meta_prompt=meta_prompt,
        )
    )

    print("[INFO] Félicitation, Scrapping + classification terminée!")


if __name__ == "__main__":
    main(prompt_client)