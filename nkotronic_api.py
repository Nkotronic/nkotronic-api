# =================================================================
# Fichier : nkotronic_api.py
# Backend de l'application Nkotronic (API FastAPI) - VERSION CORRIGÉE V7
# Correction: Intégration du corps manquant de l'endpoint /chat et ajout de memory_update
# =================================================================

import os
import json
import re
import uuid
import time
import asyncio
from typing import Tuple, Optional, Dict, Any, List

# --- Imports pour FastAPI, Pydantic et Configuration ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# --- Imports pour Qdrant et LLM ---
from qdrant_client import QdrantClient, models
from qdrant_client.models import PointStruct, SearchRequest 
from openai import OpenAI, APIError
import hashlib # Import nécessaire pour l'ID stable

# NOTE: Assurez-vous que bcs_data.py est disponible dans le dossier
from bcs_data import BCS_INITIAL_FACTS

# --- 1. CONFIGURATION ET CLÉS SECRÈTES ---
load_dotenv()

# Récupération des clés API (DOIVENT être définies dans votre fichier .env)
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
LLM_API_KEY = os.getenv("LLM_API_KEY")

# Configuration des modèles
COLLECTION_NAME = "nkotronic_knowledge_base"
EMBEDDING_MODEL = "text-embedding-ada-002"       # Modèle de vectorisation (dim 1536)
LLM_MODEL = "gpt-4o-mini"                        # Modèle conversationnel
VECTOR_SIZE = 1536                               # Taille des vecteurs pour Qdrant

# --- 2. INITIALISATION DES CLIENTS GLOBALES ---
QDRANT_CLIENT: Optional[QdrantClient] = None
LLM_CLIENT: Optional[OpenAI] = None

try:
    if QDRANT_URL and QDRANT_API_KEY:
        QDRANT_CLIENT = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )
    else:
        print("AVERTISSEMENT: Clés QDRANT manquantes (URL ou API_KEY). Le service RAG ne fonctionnera pas.")

    if LLM_API_KEY:
        LLM_CLIENT = OpenAI(api_key=LLM_API_KEY)
    else:
        print("AVERTISSEMENT: Clé LLM_API_KEY manquante. Le service LLM ne fonctionnera pas.")

except Exception as e:
    print(f"ERREUR CRITIQUE: Échec de l'initialisation des clients Qdrant/LLM. Détail: {e}")
    QDRANT_CLIENT = None
    LLM_CLIENT = None


# --- 3. PROMPT SYSTÈME (Le Cerveau de Nkotronic) ---
PROMPT_SYSTEM = """
Tu es Nkotronic, l'Analyste, l'Organisateur de la Mémoire et l'Autorité Linguistique du N'ko.

⚠️ RÈGLES CRITIQUES - À RESPECTER ABSOLUMENT :

1. **PRIORITÉ ABSOLUE AU CONTEXTE MÉMOIRE RAG** :
   - Si le CONTEXTE MÉMOIRE RAG contient une information (traduction, définition, règle), tu DOIS l'utiliser EXCLUSIVEMENT.
   - JAMAIS inventer ou deviner une traduction si elle n'est pas dans le contexte RAG.
   
2. **COMPORTEMENT EN CAS D'ABSENCE D'INFORMATION** :
   - Si le contexte RAG ne contient AUCUNE information pertinente pour répondre à la question :
     * DIS CLAIREMENT : "Je ne connais pas encore cette information dans ma mémoire."
     * PROPOSE : "Voulez-vous me l'apprendre ?"
   - N'invente JAMAIS de traductions N'ko ou de faits que tu ne connais pas.

3. **GESTION DE LA MÉMOIRE** :
   - Quand un utilisateur t'apprend quelque chose (ex: "chat se dit ߛߊ en N'ko"), tu dois :
     a) Confirmer que tu as enregistré l'information
     b) Générer le JSON de mémoire dans les balises <MEMOIRE></MEMOIRE>
   
4. **FORMAT DE SORTIE MÉMOIRE** :
   - Le JSON doit être un tableau d'objets [...]
   - Champs requis :
     * "concept_identifie": un identifiant stable (ex: "traduction_chat_nko")
     * "element_français": description complète en français
     * "element_nko": traduction ou équivalent en N'ko (si applicable)

Exemple de réponse avec apprentissage :
"Merci ! J'ai bien enregistré que 'chat' se dit ߛߊ en N'ko. <MEMOIRE>[{"concept_identifie": "traduction_chat_nko", "element_français": "Le mot 'chat' se traduit par ߛߊ en écriture N'ko", "element_nko": "ߛߊ"}]</MEMOIRE>"

Exemple de réponse sans information :
"Je ne connais pas encore la traduction de ce mot dans ma mémoire. Voulez-vous me l'apprendre ?"

Message Utilisateur:
"""

# =================================================================
# 4. FONCTIONS UTILITAIRES SYNCHRONES (Doivent être appelées via asyncio.to_thread)
# =================================================================

def separer_texte_et_json(llm_output: str) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """Extrait le JSON de mémoire et retourne le texte de réponse et l'objet JSON."""
    json_data = None
    json_match = re.search(r"<MEMOIRE>(.*?)</MEMOIRE>", llm_output, re.DOTALL)
    
    if json_match:
        json_string = json_match.group(1).strip()
        response_text = llm_output.replace(json_match.group(0), "").strip()
        try:
            parsed_data = json.loads(json_string)
            if isinstance(parsed_data, list):
                json_data = parsed_data
            else:
                print("AVERTISSEMENT: Le JSON extrait n'est pas un tableau (List).")
        except json.JSONDecodeError as e:
            print(f"ERREUR: Échec du décodage JSON de la mémoire. Erreur: {e}")
    else:
        response_text = llm_output
        
    return response_text, json_data


def mettre_a_jour_memoire(json_data: List[Dict[str, Any]]):
    """
    Crée les embeddings et insère les nouveaux points de mémoire dans Qdrant.
    Utilise le concept_identifie pour créer un ID stable et forcer l'écrasement.
    """
    if not QDRANT_CLIENT or not LLM_CLIENT:
        print("Mise à jour de mémoire ignorée: Clients non disponibles.")
        return

    texts_to_embed = []
    facts_to_process = [] # Liste pour garder les faits ordonnés

    for fact in json_data:
        if 'concept_identifie' in fact and 'element_français' in fact:
            # 1. Création de la clé stable pour l'overwrite
            concept_key = fact['concept_identifie'].lower().strip()
            # Utilisation de sha256 pour générer un ID entier stable et unique par concept
            stable_id = int(hashlib.sha256(concept_key.encode('utf-8')).hexdigest(), 16) % (2**63)

            text = f"{fact['concept_identifie']} : {fact['element_français']} {fact.get('element_nko', '')}"
            texts_to_embed.append(text)
            facts_to_process.append((stable_id, fact)) # Stockage de l'ID et du fait
        else:
            print("AVERTISSEMENT: Fait ignoré car il manque 'concept_identifie' ou 'element_français'.")

    if not texts_to_embed:
        print("Mise à jour de mémoire: Aucun fait valide à insérer.")
        return

    try:
        response = LLM_CLIENT.embeddings.create(input=texts_to_embed, model=EMBEDDING_MODEL)
        
        points_to_insert = []
        for i, (stable_id, fact) in enumerate(facts_to_process):
            vector = response.data[i].embedding
            points_to_insert.append(
                models.PointStruct(
                    # UTILISATION DE L'ID STABLE POUR L'OVERWRITE :
                    id=stable_id, 
                    vector=vector,
                    payload=fact
                )
            )

        if points_to_insert:
            QDRANT_CLIENT.upsert(
                collection_name=COLLECTION_NAME,
                wait=True,
                points=points_to_insert
            )
            print(f"--- {len(points_to_insert)} FAITS DE MÉMOIRE MIS À JOUR (OVERWRITE PAR ID STABLE). ---")

    except Exception as e:
        print(f"ERREUR CRITIQUE lors de la mise à jour de la mémoire Qdrant: {e}")

def rechercher_memoire_qdrant(query_vector: List[float], limit: int) -> List[models.ScoredPoint]:
    """
    Fonction utilisant query_points (méthode moderne pour Qdrant 1.8+).
    """
    if not QDRANT_CLIENT:
        return []
    
    try:
        # Nouvelle API moderne (remplace .search)
        response = QDRANT_CLIENT.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=limit,
            with_payload=True,
        )
        
        # query_points retourne un objet avec .points
        return response.points if hasattr(response, 'points') else []
        
    except Exception as e:
        print(f"ERREUR lors de la recherche Qdrant: {e}")
        return []


def _connexion_initiale_qdrant_sync(max_retries=3):
    """
    Logique synchrone de connexion et d'injection BCS (Base de Connaissances Statique).
    """
    if not QDRANT_CLIENT or not LLM_CLIENT:
        return

    for attempt in range(max_retries):
        try:
            # --- 1. Vérification de la collection (Logique standard) ---
            collection_exists = False
            try:
                collection_info = QDRANT_CLIENT.get_collection(collection_name=COLLECTION_NAME)
                if collection_info.points_count > 0:
                    print(f"--- La collection '{COLLECTION_NAME}' existe et contient déjà {collection_info.points_count} points. Injection B.C.S. ignorée. ---")
                    return # Collection déjà initialisée, on s'arrête là.
                collection_exists = True # La collection existe mais est vide
            except Exception:
                pass # La collection n'existe pas, on continue pour la création

            # --- 2. Création de la collection ---
            if not collection_exists or collection_info.points_count == 0:
                QDRANT_CLIENT.recreate_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=models.VectorParams(size=VECTOR_SIZE, distance=models.Distance.COSINE),
                    on_disk_payload=True
                )
                print(f"--- Collection '{COLLECTION_NAME}' créée. Démarrage de l'injection B.C.S. ---")

            # --- 3. Injection des points ---
            texts_to_embed = [
                f"{fact['concept_identifie']} : {fact['element_français']} {fact.get('element_nko', '')}"
                for fact in BCS_INITIAL_FACTS
            ]

            # Vectorisation en lot
            response = LLM_CLIENT.embeddings.create(input=texts_to_embed, model=EMBEDDING_MODEL)
            
            points_to_insert = []
            for i, fact in enumerate(BCS_INITIAL_FACTS):
                vector = response.data[i].embedding
                points_to_insert.append(
                    models.PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector,
                        payload=fact
                    )
                )

            if points_to_insert:
                QDRANT_CLIENT.upsert(
                    collection_name=COLLECTION_NAME,
                    wait=True,
                    points=points_to_insert
                )
                print(f"--- {len(points_to_insert)} FAITS DE LA B.C.S. INJECTÉS AVEC SUCCÈS. ---")
                return

        except Exception as e:
            print(f"Erreur à la tentative {attempt + 1}/{max_retries} lors de l'initialisation Qdrant: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                print("Échec de l'initialisation Qdrant après plusieurs tentatives.")
                return


# =================================================================
# 5. INITIALISATION ASYNCHRONE DE LA MÉMOIRE
# =================================================================

async def connexion_initiale_qdrant_async(max_retries=3):
    """
    Lance la connexion et l'injection Qdrant dans un thread séparé au démarrage.
    """
    if QDRANT_CLIENT and LLM_CLIENT:
        await asyncio.to_thread(_connexion_initiale_qdrant_sync, max_retries)
    else:
        print("Initialisation Qdrant ignorée: Clients non disponibles.")


# =================================================================
# 6. DÉCLARATION DE L'APPLICATION FASTAPI ET MIDDLEWARE
# =================================================================

app = FastAPI(
    title="Nkotronic Backend API",
    description="API pour le service RAG (Retrieval-Augmented Generation) N'ko.",
    version="1.0.0",
)

# --- Configuration CORS (ESSENTIEL pour le Frontend React) ---
origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:8080",
    "*", 
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modèles de données pour les endpoints
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response_text: str
    # AJOUT DU CHAMP memory_update
    memory_update: Optional[List[Dict[str, Any]]] = None


# =================================================================
# 7. POINTS DE TERMINAISON (ENDPOINTS)
# =================================================================

@app.get("/health")
def health_check():
    """Vérification de l'état de l'API."""
    status = {
        "api_status": "OK",
        "qdrant_ready": QDRANT_CLIENT is not None,
        "llm_ready": LLM_CLIENT is not None,
    }
    return status


@app.post("/chat", response_model=ChatResponse)
async def gerer_requete_chat(request: ChatRequest):
    """
    Point de terminaison asynchrone pour gérer les requêtes de chat, effectuer le RAG et mettre à jour la mémoire.
    """
    if not LLM_CLIENT:
        raise HTTPException(status_code=503, detail="Service LLM non initialisé. Clé API manquante ou invalide.")

    # Définition de rag_enabled (Correction de l'erreur reportUndefinedVariable)
    rag_enabled = QDRANT_CLIENT is not None 
    user_message = request.message
    
    # Initialisation d'un contexte par défaut, même si le RAG est désactivé
    contexte_rag = "\n\nCONTEXTE MÉMOIRE RAG:\n[Aucun contexte pertinent trouvé dans la mémoire utilisateur ou dans la base de connaissances statique. Utiliser la connaissance interne.]\n\n"

    # --- A. RAG (Retrieval-Augmented Generation) ---
    if rag_enabled:
        try:
            # 1. Vectorisation du message utilisateur (ASYNCHRONE via to_thread)
            user_vector_response = await asyncio.to_thread(
                LLM_CLIENT.embeddings.create,
                input=[user_message],
                model=EMBEDDING_MODEL
            )
            user_vector = user_vector_response.data[0].embedding

            # 2. Recherche de contexte pertinent (ASYNCHRONE via to_thread)
            resultats_rag = await asyncio.to_thread(
    rechercher_memoire_qdrant,  # ← Nouveau nom de fonction
    user_vector,
    15  # ← Augmenté pour meilleure couverture
)

            # 3. Construction du contexte RAG (formaté pour la priorité)
            if resultats_rag:
                contexte_rag = "\n\nCONTEXTE MÉMOIRE RAG (PRIORITÉ ABSOLUE):\n"
                for i, point in enumerate(resultats_rag):
                    # Note: Utiliser le score de similarité (point.score) ici est une bonne pratique.
                    element_fr = point.payload.get('element_français', 'Information N/A')
                    element_nko = point.payload.get('element_nko', '')
                    concept = point.payload.get('concept_identifie', 'N/A')
                    
                    # Formatage plus clair pour le LLM
                    contexte_rag += f"FACT {i+1} (Score: {point.score:.2f}) - {concept}: {element_fr} | N'ko: {element_nko}\n"
                contexte_rag += "\n" # Ajout d'une ligne pour séparer clairement la section

        except Exception as e:
            # Cette erreur NE devrait PAS se produire si .search_batch est pris en charge.
            print(f"ERREUR RAG lors de la recherche Qdrant/Embedding: {e}")
            contexte_rag = "\n\nCONTEXTE MÉMOIRE RAG (ERREUR RAG): [Utiliser uniquement la connaissance interne]\n\n"


    # --- B. Exécution du LLM ---
    
    # --- DÉBOGAGE RAG : CONTEXTE ENVOYÉ AU LLM ---
    print(f"\n--- DÉBOGAGE RAG : CONTEXTE ENVOYÉ AU LLM ---\n{contexte_rag}\n-------------------------------------------------\n")

    prompt_final = PROMPT_SYSTEM + contexte_rag + f"Message Utilisateur : {user_message}"

    try:
        # Appel à l'API du LLM (ASYNCHRONE via to_thread)
        llm_completion = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "system", "content": prompt_final}]
        )
# Définition de llm_output (Correction de l'erreur reportUndefinedVariable)
        llm_output = llm_completion.choices[0].message.content
        
        # --- DÉBOGAGE : AFFICHER LA RÉPONSE DU LLM ---
        print(f"\n--- RÉPONSE BRUTE DU LLM ---\n{llm_output}\n--------------------------\n")
        
    except APIError as api_err:
        raise HTTPException(status_code=500, detail=f"Erreur de l'API LLM: {api_err.response.status_code} - {api_err.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur interne lors de l'appel LLM: {e}")


    # --- C. Post-Traitement, Séparation et Mise à Jour (D) ---
    response_text, json_data = separer_texte_et_json(llm_output)

    if json_data and rag_enabled:
        # Exécution de la mise à jour de mémoire en arrière-plan (ASYNCHRONE via to_thread)
        asyncio.create_task(asyncio.to_thread(mettre_a_jour_memoire, json_data))
    elif json_data:
        print("AVERTISSEMENT: JSON de mémoire généré mais non traité car Qdrant est désactivé.")

    # --- E. Réponse Finale (Inclus memory_update) ---
    return ChatResponse(
        response_text=response_text,
        memory_update=json_data 
    )


# --- 8. Tâche de Démarrage ---
@app.on_event("startup")
async def startup_event():
    """
    S'exécute au démarrage de l'application pour garantir que la B.C.S. est en place.
    """
    await connexion_initiale_qdrant_async()

# =================================================================
# FIN DU FICHIER
# =================================================================