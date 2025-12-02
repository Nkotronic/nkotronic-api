# =================================================================
# Fichier : nkotronic_api.py
# Backend de l'application Nkotronic (API FastAPI)
# =================================================================

import os
import json
import re
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

# --- Imports pour Qdrant et LLM ---
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct
from openai import OpenAI
from bcs_data import BCS_INITIAL_FACTS # Import des faits critiques

# --- 1. CONFIGURATION ET CLÉS SECRÈTES ---
load_dotenv() 

# Récupération des clés API (DOIVENT être définies dans votre fichier .env)
QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") 
LLM_API_KEY = os.getenv("LLM_API_KEY")

# Configuration des modèles (à adapter si vous n'utilisez pas OpenAI)
COLLECTION_NAME = "nkotronic_knowledge_base"
EMBEDDING_MODEL = "text-embedding-ada-002" # Modèle de vectorisation (dim 1536)
LLM_MODEL = "gpt-4o-mini" # Modèle conversationnel

# --- 2. INITIALISATION DES CLIENTS ---
try:
    QDRANT_CLIENT = QdrantClient(
        url=QDRANT_URL,
        api_key=QDRANT_API_KEY
    )
    LLM_CLIENT = OpenAI(api_key=LLM_API_KEY)
except Exception as e:
    print(f"ERREUR CRITIQUE: Échec de l'initialisation des clients Qdrant/LLM. Détail: {e}")
    QDRANT_CLIENT = None
    LLM_CLIENT = None

# --- 3. PROMPT SYSTÈME (Le Cerveau de Nkotronic) ---

PROMPT_SYSTEM = """
Tu es Nkotronic, l'Analyste, l'Organisateur de la Mémoire et l'Autorité Linguistique du N'ko.
Ton rôle est triple : enseigner le N'ko, corriger les erreurs historiques avec bienveillance et gérer la mémoire.

---
[INSTRUCTIONS ET RÈGLES DE COMPORTEMENT]
---

Règle A. Extraction de Mémoire (Apprentissage Autonome) :
Si le message de l'utilisateur est un ENSEIGNEMENT, tu dois générer une réponse conversationnelle suivie OBLIGATOIREMENT du JSON de mise à jour de la mémoire. Le JSON doit être formaté exactement comme l'objet 'memory_update' ci-dessous et doit être la dernière chose que tu génères.

Règle B. Correction d'Identité (Défense de la Langue) :
Si l'utilisateur affirme que le N'ko est 'seulement un alphabet' ou qu'il utilise le N'ko de manière historiquement incorrecte, tu dois corriger en citant les faits de ta Base de Connaissances Statique (Langue Standard, Ancêtre Commun, Manuel ߒߞߏ ߞߊ߲ߜߍ).
Ajoute OBLIGATOIREMENT les hyperliens directs suivants à la fin de ta correction :
* [N'ko (langue) — Wikipédia](https://fr.wikipedia.org/wiki/N%27ko_(langue))
* [ߒߞߏ ߞߊ߲ߜߍ ߞߎ߲߬ߝߟߐ - Solomana Kantè - Google Livres](https://books.google.fr/books/about/%DF%92%DF%9E%DF%8F_%DF%9E%DF%8A%DF%B2%DF%9C%DF%8D_%DF%9E%DF%8E%DF%B2%DF%AC%DF%9D%DF%9F%DF%90.html?id=Jl63swEACAAJ&redir_esc=y)
Conclus la correction avec la proposition de contact : "Si vous souhaitez en discuter davantage, je peux proposer de contacter le créateur de Nkotronic."

Règle C. Correction d'Autorité (Nom de l'Auteur) :
Si l'utilisateur utilise un nom pour l'inventeur qui n'est pas Fodé Solomana Kantè (ou l'une des quatre formes abrégées tolérées), tu dois corriger immédiatement. Le nom complet est **Fodé Solomana Kantè (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)**.

Règle D. Style de Référence (Unicité) :
Le nom complet avec la transcription N'ko (Fodé Solomana Kantè (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)) doit être inclus UNE SEULE fois dans la réponse. Les références ultérieures dans la même réponse utiliseront seulement "Fodé Solomana Kantè" ou "Kantè".

Règle E. Langue :
Réponds toujours dans la langue de l'utilisateur (Français ou N'ko).

---
[CONTEXTE RAG FOURNI PAR LA BASE DE DONNÉES]
Les faits de mémoire pertinents pour cette requête seront insérés ici par le code Backend.

---
[SCHÉMA JSON D'EXTRACTION]

```json
{
  "memory_update": {
    "intention_type": "Vocabulaire | Règle Grammaticale | Fait Culturel | Autre",
    "texte_source_enseigne": "Le message exact de l'utilisateur.",
    "resume_structuré": {
      "concept_identifie": "Le concept principal (ex: ciel, salutations).",
      "element_nko": "Le mot ou la phrase en écriture N'ko (Unicode).",
      "element_français": "La traduction ou l'explication en français.",
      "note_grammaticale": "Toute information supplémentaire (classe nominale, ton, source). [Laisser vide si non pertinent]"
    }
  }
}
--- FONCTIONS D'ASSISTANCE ---
def separer_texte_et_json(llm_output: str) -> (str, str): """ Recherche le bloc JSON de 'memory_update' (délimité par json) et le sépare du texte conversationnel. """ # Utilisation d'une regex pour capturer le contenu JSON entre les délimiteurs match = re.search(r"json\s*({.})\s```", llm_output, re.DOTALL)

if match:
    json_data = match.group(1).strip()
    # Supprimer le bloc JSON de la sortie pour obtenir la réponse conversationnelle propre
    response_text = llm_output.replace(match.group(0), "").strip()
    return response_text, json_data
else:
    return llm_output, None
def mettre_a_jour_memoire(json_data_string: str) -> bool: """ Parse le JSON généré par le LLM et stocke la nouvelle donnée dans Qdrant. """ if not QDRANT_CLIENT or not LLM_CLIENT: print("Mise à jour de mémoire impossible: Clients LLM/Qdrant non initialisés.") return False

try:
    data = json.loads(json_data_string)
    memory_update = data.get("memory_update", {})
    structured_data = memory_update.get("resume_structuré", {})
    
    if not structured_data or not structured_data.get("element_français"):
        return False 
    
    # 1. CONSTRUIRE LE TEXTE À VECTORISER (pour une recherche future)
    text_to_embed = (
        structured_data.get("element_nko", "") + " " +
        structured_data.get("element_français", "") + " " +
        structured_data.get("note_grammaticale", "")
    ).strip()
    
    if not text_to_embed:
        return False

    # 2. VECTORISER (Utilisation de l'API LLM pour l'embedding)
    response = LLM_CLIENT.embeddings.create(input=[text_to_embed], model=EMBEDDING_MODEL)
    new_vector = response.data[0].embedding

    # 3. INJECTER DANS QDRANT
    QDRANT_CLIENT.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=[
            PointStruct(
                id=str(uuid.uuid4()), # Utilisation d'un UUID unique pour l'ID
                vector=new_vector,
                payload=structured_data
            )
        ]
    )
    return True
    
except json.JSONDecodeError:
    print("ERREUR: Le LLM a généré un JSON invalide.")
    return False
except Exception as e:
    print(f"ERREUR D'INJECTION QDRANT: {e}")
    return False
--- LOGIQUE D'INITIALISATION ET INJECTION B.C.S. ---
def connexion_initiale_qdrant(): """ Crée la collection Qdrant si elle n'existe pas et injecte la B.C.S. """ if not QDRANT_CLIENT or not LLM_CLIENT: return

try:
    collection_info = QDRANT_CLIENT.get_collection(collection_name=COLLECTION_NAME)
    # Vérifie si la collection existe et si elle est non-vide (pour éviter une réinjection)
    if collection_info.points_count > 0:
        print(f"--- La collection '{COLLECTION_NAME}' existe et contient déjà {collection_info.points_count} points. Injection B.C.S. ignorée. ---")
        return

except Exception:
    # La collection n'existe pas ou erreur de connexion, on la recrée
    QDRANT_CLIENT.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=models.VectorParams(size=1536, distance=models.Distance.COSINE),
        on_disk_payload=True
    )
    print(f"--- Collection '{COLLECTION_NAME}' créée. Démarrage de l'injection B.C.S. ---")

points_to_insert = []
for i, fact in enumerate(BCS_INITIAL_FACTS):
    # 1. Préparer le texte à vectoriser
    text_to_embed = f"{fact['concept_identifie']} : {fact['element_français']} {fact['element_nko']}"
    
    # 2. Vectoriser le texte
    response = LLM_CLIENT.embeddings.create(input=[text_to_embed], model=EMBEDDING_MODEL)
    vector = response.data[0].embedding
    
    # 3. Créer le Point
    points_to_insert.append(
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=fact
        )
    )
    
# 4. Injecter en masse dans Qdrant
if points_to_insert:
    QDRANT_CLIENT.upsert(
        collection_name=COLLECTION_NAME,
        wait=True,
        points=points_to_insert
    )
    print(f"--- {len(points_to_insert)} FAITS DE LA B.C.S. INJECTÉS AVEC SUCCÈS. ---")
=================================================================
4. POINT DE TERMINAISON PRINCIPAL DE L'API (FastAPI)
=================================================================
app = FastAPI()

Modèles pour l'API
class ChatRequest(BaseModel): message: str

class ChatResponse(BaseModel): response_text: str

@app.post("/chat", response_model=ChatResponse) def gerer_requete_chat(request: ChatRequest): if not LLM_CLIENT or not QDRANT_CLIENT: raise HTTPException(status_code=503, detail="Service Nkotronic non initialisé. Clés API manquantes ou invalides.")

user_message = request.message

# --- A. RAG (Retrieval-Augmented Generation) ---

# 1. Vectorisation du message utilisateur
user_vector = LLM_CLIENT.embeddings.create(input=[user_message], model=EMBEDDING_MODEL).data[0].embedding

# 2. Recherche de contexte pertinent
resultats_rag = QDRANT_CLIENT.search(
    collection_name=COLLECTION_NAME,
    query_vector=user_vector,
    limit=5 # Récupère les 5 faits les plus pertinents
)

# 3. Construction du contexte RAG pour le LLM
contexte_rag = "CONTEXTE MÉMOIRE:\n"
for point in resultats_rag:
    # Utiliser l'élément français et le concept du payload pour le contexte
    contexte_rag += f"- {point.payload.get('element_français', 'Information N/A')} (Concept: {point.payload.get('concept_identifie', 'N/A')})\n"
    
# --- B. Exécution du LLM ---

prompt_final = PROMPT_SYSTEM + contexte_rag + f"\n\nMessage Utilisateur : {user_message}"

# Appel à l'API du LLM
llm_completion = LLM_CLIENT.chat.completions.create(
    model=LLM_MODEL,
    messages=[{"role": "system", "content": prompt_final}]
)
llm_output = llm_completion.choices[0].message.content

# --- C. Post-Traitement, Séparation et Mise à Jour (D) ---

response_text, json_data = separer_texte_et_json(llm_output)

if json_data:
    mettre_a_jour_memoire(json_data) # Mise à jour asynchrone

# --- E. Réponse Finale ---
return ChatResponse(response_text=response_text)
--- 5. Tâche de Démarrage ---
@app.on_event("startup") async def startup_event(): """ S'exécute au démarrage de l'application pour garantir que la B.C.S. est en place. """ connexion_initiale_qdrant()


---

Votre prochaine étape est de remplir le fichier **`.env`** avec vos clés secrètes, puis de tester et déployer le Backend !