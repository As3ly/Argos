import os
import json
import time
import random
import sqlite3
import asyncio
import httpx
import framatome
import truststore
from urllib.parse import urlparse

from db.repository import safe_insert, safe_delete_raw
from jsonschema import validate as jsonschema_validate, ValidationError
from openai import AsyncAzureOpenAI
from dotenv import load_dotenv

# ========================================================================
# PROXY + ENV
# ========================================================================
truststore.inject_into_ssl()
load_dotenv()

def _mask_secret(secret: str | None) -> str:
    if not secret:
        return "(vide)"
    return f"{secret[:4]}****"


subscription_key = os.getenv("AZURE_API_KEY")
use_proxy = os.getenv("AZURE_USE_PROXY", "true").strip().lower() in {"1", "true", "yes", "on"}
default_proxy = getattr(framatome, "HTTPS_PROXY", None)
proxy = os.getenv("AZURE_PROXY_URL") or (default_proxy if use_proxy else None)

print("Proxy utilisé :", proxy if proxy else "(désactivé)")
print("AZURE_API_KEY chargé :", _mask_secret(subscription_key))

# ========================================================================
# OPENAI CONFIG
# ========================================================================
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT")
DEPLOYMENT = os.getenv("DEPLOYMENT")
API_VERSION = os.getenv("API_VERSION")
PROMPT_GEN_MAX_TOKENS = int(os.getenv("PROMPT_GEN_MAX_TOKENS", "900"))

missing_azure_env = [
    name for name, value in (
        ("AZURE_API_KEY", subscription_key),
        ("AZURE_ENDPOINT", AZURE_ENDPOINT),
        ("DEPLOYMENT", DEPLOYMENT),
        ("API_VERSION", API_VERSION),
    )
    if not value
]
if missing_azure_env:
    raise RuntimeError(
        "Configuration Azure incomplète. Variables manquantes: "
        + ", ".join(missing_azure_env)
    )

connect_timeout_s = float(os.getenv("AZURE_CONNECT_TIMEOUT_S", "10"))
read_timeout_s = float(os.getenv("AZURE_READ_TIMEOUT_S", "120"))
write_timeout_s = float(os.getenv("AZURE_WRITE_TIMEOUT_S", "30"))
pool_timeout_s = float(os.getenv("AZURE_POOL_TIMEOUT_S", "30"))
HTTP_TIMEOUT = httpx.Timeout(
    connect=connect_timeout_s,
    read=read_timeout_s,
    write=write_timeout_s,
    pool=pool_timeout_s,
)

transport_kwargs = {"verify": True}
if proxy:
    transport_kwargs["proxy"] = proxy

httpx_client = httpx.AsyncClient(
    transport=httpx.AsyncHTTPTransport(**transport_kwargs),
    timeout=HTTP_TIMEOUT,
)

async_client = AsyncAzureOpenAI(
    api_key=subscription_key,
    azure_endpoint=AZURE_ENDPOINT,
    api_version=API_VERSION,
    http_client=httpx_client
)

# ========================================================================
# JSON SCHEMA (inchangé)
# ========================================================================
EXTRACTION_SCHEMA = {
    "name": "appels_offres_extraction_schema_v2",
    "schema": {
        "type": "object",
        "properties": {
            "extraction": {
                "type": "object",
                "properties": {
                    "titre": {"type": ["string", "null"]},
                    "date_publication": {"type": ["string", "null"]},
                    "date_cloture": {"type": ["string", "null"]},
                    "lieu": {"type": ["string", "null"]},
                    "budget": {"type": ["string", "null"]},
                    "type_marche": {"type": ["string", "null"]},
                    "acheteur": {"type": ["string", "null"]},
                    "reference": {"type": ["string", "null"]},
                    "score_ia": {"type": ["number", "null"]},
                    "tags": {"type": ["string", "null"]},
                    "raison": {"type": ["string", "null"]},
                    "secteur": {"type": ["string", "null"]},
                    "mot_cle": {"type": ["string", "null"]},
                    "lien": {"type": ["string", "null"]}
                },
                "required": [
                    "titre", "date_publication", "date_cloture", "lieu",
                    "budget", "type_marche", "acheteur", "reference", "score_ia",
                    "tags", "raison", "secteur", "mot_cle", "lien"
                ],
                "additionalProperties": False
            }
        },
        "required": ["extraction"],
        "additionalProperties": False
    },
    "strict": True
}

CLASSIFICATION_SCHEMA = {
    "name": "appels_offres_classification_schema_v1",
    "schema": {
        "type": "object",
        "properties": {
            "pertinent": {"type": "boolean"}
        },
        "required": ["pertinent"],
        "additionalProperties": False
    },
    "strict": True
}

CRITERES_GEN_SCHEMA = {
    "name": "criteres_generation",
    "schema": {
        "type": "object",
        "properties": {
            "criteres": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 5,
                "maxItems": 50
            },
            "regles": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 50
            },
            "mots_recherche": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 50
            },
            "titre_recherche": {
                "type": "string",
                "minLength": 8,
                "maxLength": 120
            }
        },
        "required": ["criteres", "regles", "mots_recherche", "titre_recherche"],
        "additionalProperties": False
    }
}

# ========================================================================
# PROMPTS
# ========================================================================
SYSTEM_PROMPT_EXTRACTION = """
Tu es un agent spécialisé en extraction et structuration d'appels d'offres.

OBJECTIFS :
1) Lire l'appel d'offre.
2) Extraire les champs définis dans le schéma JSON.
3) Retourner STRICTEMENT un JSON conforme.

RÈGLES :
- Aucune invention.
- Dates en YYYY-MM-DD.
- Pas d'invention budget.
- "score_ia" ∈ [0,1].
- Sortie 100% JSON strict.
"""

SYSTEM_PROMPT_CLASSIFICATION = """
Tu es un agent spécialisé en classification et qualification d'appels d'offres.

OBJECTIFS :
1) Lire l'appel d'offre et les critères de pertinence.
2) Déterminer uniquement si l'appel est pertinent (true/false).
3) Retourner STRICTEMENT un JSON conforme.

RÈGLES :
- Aucune invention.
- La décision doit se baser sur le contenu fourni.
- Sortie 100% JSON strict.
"""

# ========================================================================
# Génèration Prompt
# ========================================================================

DB_PATH = "backend/html_scrap.db"



async def generate_criteres_prompt_json(search_id: int, user_description: str) -> list:
    print(f"[PROMPT-GEN] Génération de critères (JSON compact) pour search_id={search_id}")

    SYSTEM = """
Tu es un expert en ingénierie, analyse technique, text mining et extraction de données.
Tu aides à construire un module d’intelligence artificielle capable d’analyser des appels d’offres techniques
et d’évaluer leur pertinence pour un utilisateur final.

OBJECTIF :
L’utilisateur décrit ses besoins (langage naturel).
Tu dois produire une liste SÉRIEUSE, TECHNIQUE, PRÉCISE de critères clé reflétant son domaine d’intérêt.

⚠️ ATTENTION : tu ne dois PAS produire de texte long.
⚠️ ATTENTION : tu ne dois PAS rédiger le bloc final 'CRITÈRES DE PERTINENCE'.

TU DOIS UNIQUEMENT produire un JSON TRÈS COURT respectant strictement le schéma fourni,
contenant :

- "criteres" : liste de mots-clés techniques, termes spécialisés, concepts métier
- "regles" : règles booléennes simples indiquant comment décider la pertinence
- "mots_recherche" : requêtes prêtes à l’emploi pour un moteur de recherche (chaînes brèves)
- "titre_recherche" : un titre court, professionnel et lisible pour nommer la recherche


RÈGLES STRICTES POUR "mots_recherche" :

- Liste de chaînes courtes (1 à 4 mots maximum).
- Requêtes prêtes à copier-coller dans un moteur de recherche.
- Aucun opérateur logique.
- Aucun guillemet.
- Pas de doublons.
- Pas de caractères spéciaux superflus.


INTERDICTIONS STRICTES :

Les mots de liaison suivants sont interdits dans les requêtes : de, la, le, les, du, des, en, pour, avec, sur, dans.

Les requêtes doivent être des groupes nominaux techniques sans mots de liaison.
Exemples :
MAUVAIS: maintenance de moteurs, analyse de vibration

BON: maintenance moteurs, analyse vibration


INTERDICTION IMPORTANTE :

Ne jamais inclure les expressions suivantes :

appel d'offre
appels d'offres
marché public
marchés publics

Ces termes sont inutiles car la plateforme cible contient déjà des appels d’offres.


STRATÉGIE DE GÉNÉRATION :

Les requêtes doivent être suffisamment larges pour capter un maximum d’opportunités pertinentes.

Si un domaine technique peut être résumé par un terme central, utiliser directement ce terme seul.

Exemple :

MAUVAIS
CFD simulation
CFD nucléaire
CFD industrie

BON
CFD

Cependant il faut combiner des mots larges et des mots plus spécifiques afin de ne pas limiter la recherche.

Exemple :

CFD
aérodynamique
simulation numérique
mécanique fluides
turbulence


RÈGLE STRUCTURELLE IMPORTANTE :

Au moins 30 pourcent des éléments de la liste "mots_recherche" doivent être constitués d’un seul mot.
Ces mots uniques doivent correspondre à des termes techniques centraux du domaine.


NIVEAU DE DÉTAIL ATTENDU :

- Les termes doivent être techniques, cohérents et stricts.
- Jamais de phrases complètes.
- Pas d’explications.
- Listes compactes : 5 à 15 éléments.

Les règles doivent être ultra concises.

Exemples :
pertinent si présence critère
non pertinent si domaine différent
aucune invention


CONTRAINTES FONDAMENTALES :

- Ne générer AUCUN texte en dehors du JSON.
- Ne générer AUCUN commentaire.
- Ne générer AUCUN bloc Markdown.
- Ne générer AUCUN code fence.
- Le JSON doit être PARFAITEMENT conforme au schéma.
"""

    USER = f"""
Description utilisateur :
\"\"\"{user_description}\"\"\"

Instructions :
- Analyse précisément la description.
- Extrapole les domaines, termes techniques et mots‑clés pertinents.
- Génère "mots_recherche" : liste de chaînes brèves (1–4 mots), prêtes pour la recherche web.
- Génère "titre_recherche" : un titre concis (5 à 12 mots), précis, en français, sans ponctuation superflue.
- Génère UNIQUEMENT le JSON court attendu.
"""

    async def _one_try(attempt: int):
        print(f"[PROMPT-GEN] Appel Azure (tentative {attempt})")
        resp = await async_client.chat.completions.create(
            model=DEPLOYMENT,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER}
            ],
            response_format={"type": "json_schema", "json_schema": CRITERES_GEN_SCHEMA},
            max_completion_tokens=PROMPT_GEN_MAX_TOKENS,
        )

        # Debug helpful: finish_reason
        try:
            choice = resp.choices[0]
            print(f"[PROMPT-GEN] finish_reason={choice.finish_reason}")
        except Exception:
            pass

        content = (resp.choices[0].message.content or "").strip()
        return content

    # Retry exponentiel (3 tentatives)
    raw = ""
    for attempt in range(1, 4):
        try:
            raw = await _one_try(attempt)
            if raw:
                break
            else:
                print("[PROMPT-GEN] ⚠ Réponse Azure vide → retry…")
        except Exception as e:
            print(f"[PROMPT-GEN] ⚠ Erreur Azure ({type(e).__name__}) : {e!r}")

        wait = (2 ** (attempt - 1)) + random.random()
        print(f"[PROMPT-GEN] Retry dans {wait:.1f}s…")
        await asyncio.sleep(wait)

    if not raw:
        raise TimeoutError(
            "Azure n'a retourné aucune réponse pour la génération des mots-clés "
            "après 3 tentatives."
        )

    # Parse JSON
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"[PROMPT-GEN] ❌ Erreur JSON parse : {e}")
        print(raw[:300])
        raise ValueError("Réponse Azure non JSON pour la génération des critères.") from e

    # Validation strict JSON Schema
    try:
        jsonschema_validate(data, CRITERES_GEN_SCHEMA["schema"])
    except ValidationError as e:
        print(f"[PROMPT-GEN] ❌ JSON non conforme : {e.message}")
        print(raw[:300])
        raise ValueError(
            f"JSON Azure non conforme au schéma de génération: {e.message}"
        ) from e

    criteres = data["criteres"]
    regles = data["regles"]
    mots_recherche = data["mots_recherche"]
    titre_recherche = str(data["titre_recherche"]).strip()

    # Reconstruction du texte final "CRITERES DE PERTINENCE"
    criteres_text = (
        "=======================\n"
        "CRITÈRES DE PERTINENCE\n"
        "=======================\n" +
        "\n".join(f"• {c}" for c in criteres) +
        "\n\n=======================\n"
        "RÈGLES DE DÉCISION\n"
        "=======================\n" +
        "\n".join(f"- {r}" for r in regles)
    )

    print(f"[PROMPT-GEN] Critères (aperçu 120 chars) : {criteres_text[:120]!r}")
    print(f"[PROMPT-GEN] Mots de recherche : {mots_recherche[:8]}{'...' if len(mots_recherche)>8 else ''}")
    print(f"[PROMPT-GEN] Nombre de mots de recherche : {len(mots_recherche)}")
    print(f"[PROMPT-GEN] Titre recherche : {titre_recherche}")

    # Sauvegarde en DB
    try:
        conn = sqlite3.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")

        cur = conn.cursor()
        cur.execute(
            "UPDATE recherches_jobs SET params = ?, titre = ? WHERE id = ?",
            (criteres_text, titre_recherche, search_id)
        )
        conn.commit()
        print(f"[PROMPT-GEN] ✔ Critères enregistrés (search_id={search_id})")

    except Exception as e:
        print(f"[PROMPT-GEN] ❌ Erreur DB : {e}")
        raise RuntimeError("Impossible d'enregistrer les critères générés en base.") from e
    finally:
        try:
            conn.close()
        except Exception:
            pass
    
    normalized = []
    for m in mots_recherche:
        if not isinstance(m, str):
            continue  # sécurité : on ignore les entrées non str
        m = m.strip()
        if not m:
            continue
        parts = m.split()
        if len(parts) == 1:
            normalized.append(parts[0])
        else:
            normalized.append(parts)


    return [normalized, criteres_text, titre_recherche]



# ========================================================================
# ASYNC SEMAPHORE
# ========================================================================
semaphore = asyncio.Semaphore(10)

# ========================================================================
# VALIDATION JSON STRICTE
# ========================================================================
def validate_ai_json(raw_json: dict, raw_id: int) -> bool:
    """Valide le JSON via jsonschema."""
    try:
        jsonschema_validate(raw_json, EXTRACTION_SCHEMA["schema"])
        if "pertinent" not in raw_json:
            raise ValidationError("'pertinent' est requis")
        jsonschema_validate({"pertinent": raw_json["pertinent"]}, CLASSIFICATION_SCHEMA["schema"])
        return True
    except ValidationError as e:
        print(f"[RAW {raw_id}] ❌ JSON non valide : {e.message}")
        return False
    except Exception as e:
        print(f"[RAW {raw_id}] ❌ Erreur JSONSchema : {e}")
        return False

# ========================================================================
# RETRY EXPONENTIEL - FONCTION EXTRACTION AI
# ========================================================================
async def limited_extract(ao_text: str, search_id: int, raw_id: int, CRITERES_PERTINENCE: str):
    """Extraction structurée via Azure OpenAI avec retry exponentiel + jitter."""
    async with semaphore:
        max_attempts = 5
        base_delay = 1

        for attempt in range(1, max_attempts + 1):
            try:
                print(f"[RAW {raw_id}] Appel Azure (tentative {attempt})")

                response = await async_client.chat.completions.create(
                    model=DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_EXTRACTION + CRITERES_PERTINENCE},
                        {"role": "user", "content": f"search_id={search_id}\n\n{ao_text}"}
                    ],
                    response_format={"type": "json_schema", "json_schema": EXTRACTION_SCHEMA},
                    max_completion_tokens=2000
                )

                raw = response.choices[0].message.content
                print(f"[RAW {raw_id}] Réponse Azure (100 chars) : {raw[:100]!r}")

                if not raw:
                    print(f"[RAW {raw_id}] ❌ Réponse vide Azure.")
                    return None

                try:
                    parsed = json.loads(raw)
                    return parsed
                except Exception as e:
                    print(f"[RAW {raw_id}] ❌ JSON cassé : {e}")
                    print(raw)
                    return None

            except Exception as e:
                print(f"[RAW {raw_id}] ⚠️ Erreur Azure ({type(e).__name__}) : {e!r}")

            # Retry
            wait = base_delay * (2 ** (attempt - 1))
            wait += random.random()
            print(f"[RAW {raw_id}] Retry dans {wait:.1f} sec…")
            await asyncio.sleep(wait)

        print(f"[RAW {raw_id}] ❌ Échec final après {max_attempts} tentatives")
        return None


async def limited_classify(ao_text: str, search_id: int, raw_id: int, CRITERES_PERTINENCE: str, extraction: dict):
    """Classification de pertinence via un second appel IA dédié."""
    async with semaphore:
        max_attempts = 5
        base_delay = 1

        for attempt in range(1, max_attempts + 1):
            try:
                print(f"[RAW {raw_id}] Appel Azure classification (tentative {attempt})")

                response = await async_client.chat.completions.create(
                    model=DEPLOYMENT,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT_CLASSIFICATION + CRITERES_PERTINENCE},
                        {
                            "role": "user",
                            "content": (
                                f"search_id={search_id}\n\n"
                                f"EXTRACTION_DONNEES={json.dumps(extraction, ensure_ascii=False)}\n\n"
                                f"CONTENU_BRUT={ao_text}"
                            ),
                        }
                    ],
                    response_format={"type": "json_schema", "json_schema": CLASSIFICATION_SCHEMA},
                    max_completion_tokens=800,
                )

                raw = response.choices[0].message.content
                print(f"[RAW {raw_id}] Réponse classification (100 chars) : {raw[:100]!r}")

                if not raw:
                    print(f"[RAW {raw_id}] ❌ Réponse vide classification.")
                    return None

                try:
                    parsed = json.loads(raw)
                    return parsed
                except Exception as e:
                    print(f"[RAW {raw_id}] ❌ JSON classification cassé : {e}")
                    print(raw)
                    return None

            except Exception as e:
                print(
                    f"[RAW {raw_id}] ⚠️ Erreur Azure classification ({type(e).__name__}) : {e!r}"
                )

            wait = base_delay * (2 ** (attempt - 1))
            wait += random.random()
            print(f"[RAW {raw_id}] Retry classification dans {wait:.1f} sec…")
            await asyncio.sleep(wait)

        print(f"[RAW {raw_id}] ❌ Échec classification après {max_attempts} tentatives")
        return None

# ========================================================================
# TRAITEMENT D'UN RAW
# ========================================================================
def resolve_source(job_source: str | None, lien: str) -> str:
    if isinstance(job_source, str) and job_source.strip():
        return job_source.strip()

    parsed = urlparse((lien or "").strip())
    netloc = (parsed.netloc or "").strip().lower()
    if netloc:
        return netloc

    return "unknown_source"


async def handle_single_raw(
    raw_id: int,
    html_content: str,
    lien: str,
    search_id: int,
    source: str,
    crit: str,
):

    print(f"[RAW {raw_id}] Début traitement")
    result = await limited_extract(html_content, search_id, raw_id, crit)

    if result is None:
        print(f"[RAW {raw_id}] ❌ Extraction IA échouée → RAW conservé")
        return

    extraction = result.get("extraction")
    if extraction is None:
        print(f"[RAW {raw_id}] ❌ Extraction absente du JSON IA → pas d'insertion, pas de suppression")
        return

    classification = await limited_classify(html_content, search_id, raw_id, crit, extraction)
    if classification is None:
        print(f"[RAW {raw_id}] ❌ Classification IA échouée → RAW conservé")
        return

    result["pertinent"] = classification.get("pertinent")

    if not validate_ai_json(result, raw_id):
        print(f"[RAW {raw_id}] ❌ JSON IA invalide → pas d'insertion, pas de suppression")
        return

    pertinent = result["pertinent"]
    
    
    if not pertinent:
        print(f"[RAW {raw_id}] 🚫 Non pertinent")
        safe_insert(extraction, pertinent, raw_id, lien, source=source, search_id=search_id)
        safe_delete_raw(raw_id, search_id)   #il faudra qu'on choisisse si on garde ou pas
        return


    safe_insert(extraction, pertinent, raw_id, lien, source=source, search_id=search_id)
    safe_delete_raw(raw_id, search_id)

# ========================================================================
# TRAITEMENT GLOBAL
# ========================================================================
async def process_search_id_async(search_id: int, user_description: str):
    conn = sqlite3.connect("backend/html_scrap.db", timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    cur = conn.cursor()
    
    cur.execute("""
        SELECT source
        FROM recherches_jobs
        WHERE id = ?
    """, (search_id,))
    row = cur.fetchone()
    job_source = row[0] if row else None

    cur.execute("""
        SELECT id, html_contenu, lien, source
        FROM raw_recherches
        WHERE search_id = ?
    """, (search_id,))
    raws = cur.fetchall()
    conn.close()

    tasks = []
    for raw_id, html_content, lien, raw_source in raws:
        if html_content and len(html_content.strip()) > 50:
            source = resolve_source(raw_source or job_source, lien)
            tasks.append(asyncio.create_task(
                handle_single_raw(raw_id, html_content, lien, search_id, source, user_description)
            ))

    await asyncio.gather(*tasks)
