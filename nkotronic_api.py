# =================================================================
# Fichier : nkotronic_api.py
# Backend de l'application Nkotronic (API FastAPI) - VERSION V9 (Complète et Corrigée)
# =================================================================

import os
import json
import re
import uuid
import time
import asyncio
import hashlib
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

# --- IMPORTS DE LA BASE DE CONNAISSANCES N'KO ---
# NOTE: Assurez-vous que nko_knowledge_data.py et bcs_data.py sont disponibles
from bcs_data import BCS_INITIAL_FACTS
from nko_knowledge_data import NKO_STRUCTURED_KNOWLEDGE 

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
QDRANT_LOCK = asyncio.Lock()

try:
    # 1. Initialisation Qdrant
    if QDRANT_URL and QDRANT_API_KEY:
        QDRANT_CLIENT = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            # 🚨 CORRECTION : RETIRER LE PARAMÈTRE INCONNU 🚨
            # check_compatibility=False  <-- A RETIRER
        )

    # 2. Initialisation LLM (OpenAI)
    
    # 👇 TEST DE DIAGNOSTIC SIMPLIFIÉ
    if LLM_API_KEY:
        print(f"DEBUG SUCCÈS : LLM_API_KEY est chargée. Clé : {LLM_API_KEY[:5]}...")
        # CORRECTION : Augmentation du timeout à 60s pour les appels d'embeddings lents
        LLM_CLIENT = OpenAI(api_key=LLM_API_KEY, timeout=60.0) 
    else:
        print("DEBUG ERREUR CRITIQUE : LLM_API_KEY est vide/NONE. Initialisation LLM impossible.")
        LLM_CLIENT = None
    
    # FIN DU TEST
    
except Exception as e:
    print(f"ERREUR CRITIQUE: Échec de l'initialisation des clients Qdrant/LLM. Détail: {e}")
    QDRANT_CLIENT = None
    LLM_CLIENT = None

except Exception as e:
    print(f"ERREUR CRITIQUE: Échec de l'initialisation des clients Qdrant/LLM. Détail: {e}")
    QDRANT_CLIENT = None
    LLM_CLIENT = None

except Exception as e:
    print(f"ERREUR CRITIQUE: Échec de l'initialisation des clients Qdrant/LLM. Détail: {e}")
    QDRANT_CLIENT = None
    LLM_CLIENT = None


# --- 3. PROMPT SYSTÈME (Le Cerveau de Nkotronic) ---
PROMPT_SYSTEM = """
Tu es Nkotronic, l'Analyste, l'Organisateur de la Mémoire et l'Autorité Linguistique du N'ko.

⚠️ RÈGLES CRITIQUES - À RESPECTER ABSOLUMENT :

1. PRISE DE DÉCISION, SYNTHÈSE et CONCISION :
    - Pour toute question factuelle utilisant le mot 'lettre' (ߛߓߍߘߋ߲), tu dois **TOUJOURS** répondre en utilisant le nombre total de lettres de l'alphabet N'ko trouvé dans le CONTEXTE RAG.
    - **PRIORITÉ ABSOLUE :** Ta réponse doit être **courte, directe et factuelle** et uniquement basée sur le nombre factuel (27, 7 ou 19, etc.). NE JAMAIS compter l'occurrence des mots dans la phrase de l'utilisateur. NE JAMAIS verbaliser le processus de vérification.
    - Pour l'analyse ou la transcription, utilise le FACT RAG fourni par le moteur (score 1.0) comme réponse unique et définitive.

2. **PRIORITÉ ABSOLUE AU CONTEXTE MÉMOIRE RAG** :
    - Si le CONTEXTE MÉMOIRE RAG contient une information (traduction, définition, règle), tu DOIS l'utiliser EXCLUSIVEMENT.
    - JAMAIS inventer ou deviner une traduction si elle n'est pas dans le contexte RAG.
    
3. **COMPORTEMENT EN CAS D'ABSENCE D'INFORMATION ET DE TYPE DE QUESTION** :
    - **Pour les questions de faits, de règles ou de traductions N'ko (qui nécessitent le RAG) :**
      * Si le contexte RAG est vide ou non pertinent :
          1. DIS CLAIREMENT : "Je ne connais pas encore cette information dans ma mémoire."
          2. PROPOSE : "Voulez-vous me l'apprendre ?"
      * N'invente JAMAIS de traductions N'ko ou de faits.
    - **Pour les questions conversationnelles, les salutations ou les sujets généraux :**
      * Réponds de manière naturelle et engageante, en utilisant ta personnalité d'Analyste Nkotronic.
      * Tu n'as pas besoin de mentionner le manque de mémoire ou de proposer un apprentissage dans ce cas.

4. **GESTION DE LA MÉMOIRE** :
    - Quand un utilisateur t'apprend quelque chose (ex: "chat se dit ߛߊ en N'ko"), tu dois :
      a) Confirmer que tu as enregistré l'information
      b) Générer le JSON de mémoire dans les balises <MEMOIRE></MEMOIRE>
    
5. **FORMAT DE SORTIE MÉMOIRE** :
    - Le JSON doit être un tableau d'objets [...]
    - Champs requis :
      * "concept_identifie": un identifiant stable (ex: "traduction_chat_nko")
      * "element_français": description complète en français
      * "element_nko": traduction ou équivalent en N'ko (si applicable)

Exemple de réponse avec apprentissage :
"Merci ! J'ai bien enregistré que 'chat' se dit ߛߊ en N'ko. <MEMOIRE>[{"concept_identifie": "traduction_chat_nko", "element_français": "Le mot 'chat' se traduit par ߛߊ en écriture N'ko", "element_nko": "ߛߊ"}]</MEMOIRE>"

Exemple de réponse sans information (pour un fait N'ko) :
"Je ne connais pas encore la traduction de ce mot dans ma mémoire. Voulez-vous me l'apprendre ?"

Message Utilisateur:
"""

# =================================================================
# 4. FONCTIONS UTILITAIRES SYNCHRONES 
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


# Insérer dans la section 4. FONCTIONS UTILITAIRES SYNCHRONES

def transcrire_et_analyser(message: str) -> str:
    """
    Tente de détecter si le message est une requête de transcription phonétique 
    (Français -> N'ko) ou d'analyse N'ko (N'ko -> IPA/Français) et fournit une réponse directe.

    Retourne un fait formaté pour le LLM si la détection est positive, sinon retourne None.
    """
    
    # Récupérer la map phonétique
    PHONETIC_MAP = NKO_STRUCTURED_KNOWLEDGE['PHONETICS']['MAP']
    
    # 1. Tâche de DÉTECTION DE TRANSCRIPTION (Français -> N'ko)
    # Ex: "transcris 'tomate' en n'ko"
    match_transcribe = re.search(r"(transcris|traduis phonétiquement|écris phonétiquement) ['\"]?([a-zA-ZÀ-ÿ\s]+)['\"]? en n[']?ko", message, re.IGNORECASE)
    
    if match_transcribe:
        word_to_transcribe = match_transcribe.group(2).lower().strip()
        
        # Ce n'est qu'une démonstration simple de substitution lettre par lettre
        # Dans un vrai système, il faudrait un modèle de prononciation plus complexe.
        nko_output = []
        for char in word_to_transcribe:
            # On cherche une correspondance simple, sinon on garde l'espace
            nko_char = PHONETIC_MAP.get(char)
            if isinstance(nko_char, str):
                nko_output.append(nko_char)
            elif char == ' ':
                nko_output.append(' ')
        
        nko_result = "".join(nko_output)
        
        if nko_result:
            # Formatage du résultat pour qu'il soit injecté comme un fait RAG (Score de 1.0)
            fact = f"""
CONTEXTE MÉMOIRE RAG (PRIORITÉ ABSOLUE - TRANSCRIPTION):
FACT 1 (Score: 1.00) - transcription_directe: La transcription phonétique de '{word_to_transcribe}' est calculée comme étant : {nko_result} | N'ko: {nko_result}
            """
            return fact.strip()

    # 2. Tâche de DÉTECTION D'ANALYSE (N'ko -> Français/Phonétique)
    # Ex: "lis ߓߊ"
    match_analyse = re.search(r"(lis|prononce|analyse) ['\"]?(\s*[\u07C0-\u07FF]+\s*)['\"]?", message)
    
    if match_analyse:
        nko_word = match_analyse.group(2).strip()
        ipa_output = []
        
        # Inversion de la map pour N'ko -> IPA/Phonétique
        IPA_REVERSE_MAP = {}
        for ipa_char, nko_chars in PHONETIC_MAP.items():
            if isinstance(nko_chars, str):
                IPA_REVERSE_MAP[nko_chars] = ipa_char
            elif isinstance(nko_chars, list):
                for nko_char in nko_chars:
                    IPA_REVERSE_MAP[nko_char] = ipa_char
        
        for nko_char in nko_word:
            ipa_char = IPA_REVERSE_MAP.get(nko_char, nko_char) # Garde le caractère si pas de map
            ipa_output.append(ipa_char)
            
        ipa_result = "".join(ipa_output)
        
        # Formatage du résultat pour qu'il soit injecté comme un fait RAG
        fact = f"""
CONTEXTE MÉMOIRE RAG (PRIORITÉ ABSOLUE - ANALYSE):
FACT 1 (Score: 1.00) - analyse_directe: L'analyse phonétique du terme N'ko '{nko_word}' est : [{ipa_result}]. | N'ko: {nko_word}
        """
        return fact.strip()
        
    return None


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


def pre_traiter_requete(message: str) -> str:
    """
    Reformule la requête utilisateur en substituant les termes N'ko
    mémorisés (vocabulaire) par leurs équivalents français.
    Ceci améliore la pertinence de la recherche RAG.
    """
    processed_message = message.lower()
    
    # Inversion du dictionnaire de vocabulaire pour recherche rapide N'ko -> Français
    VOCAB_REVERSE_MAP = {}
    
    for fr_term, nko_terms in NKO_STRUCTURED_KNOWLEDGE['VOCABULARY'].items():
        if isinstance(nko_terms, str):
            VOCAB_REVERSE_MAP[nko_terms] = fr_term
        elif isinstance(nko_terms, list):
            for nko_term in nko_terms:
                VOCAB_REVERSE_MAP[nko_term] = fr_term


    # Substitution : Remplacer les termes N'ko par leur traduction française
    # On itère sur les termes N'ko du map inversé.
    for nko_term, fr_term in VOCAB_REVERSE_MAP.items():
        # Utilisation de regex pour ne remplacer que des mots entiers (ou presque)
        # re.escape est CRITIQUE pour gérer les caractères N'ko
        processed_message = re.sub(r'\b' + re.escape(nko_term) + r'\b', fr_term, processed_message)

    
    # Deuxième passe : Tenter d'identifier les questions de FAITS PURS (non-RAG direct)
    
    # 1. Requête de type "Combien de [concept] ?"
    match_count = re.search(r"combien de (lettre|voyelle|consonne)(s)?\b", processed_message)
    if match_count:
        concept = match_count.group(1).lower()
        if concept in ['lettre', 'voyelle', 'consonne']:
            # On force la requête RAG pour trouver le fait exact "il y a X lettres..."
            return f"information factuelle: nombre de {concept}s dans l'alphabet nko"

    # 2. Requête de type "Montre-moi les [concept]"
    match_show = re.search(r"montre(s)? moi (les )?(lettre|voyelle|consonne)s?\b", processed_message)
    if match_show:
        concept = match_show.group(3).lower()
        if concept in ['lettre', 'voyelle', 'consonne']:
            # On force la requête RAG pour trouver la liste exacte "les 27 lettres sont: ..."
            return f"liste des {concept}s de l'alphabet nko"

    return processed_message

# --- NOUVELLE FONCTION UTILITAIRE POUR LE BATCHING ---
def chunk_list(data: list, chunk_size: int) -> List[list]:
    """Divise une liste en lots (chunks) de taille maximale spécifiée."""
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]


# Fichier : nkotronic_api.py (Remplacement de la Section 5)

# =================================================================# 5. INITIALISATION ASYNCHRONE DE QDRANT (VERSION FINALE CORRIGÉE)
# =================================================================

# Global pour suivre l'état d'initialisation
QDRANT_INITIALIZED = False

async def initialiser_qdrant(collection_name, dimension):
    global QDRANT_CLIENT, QDRANT_INITIALIZED, QDRANT_LOCK
    
    if not QDRANT_CLIENT or not LLM_CLIENT:
        print("Initialisation Qdrant non démarrée : Client Qdrant ou LLM non initialisé.")
        return

    async with QDRANT_LOCK:
        if QDRANT_INITIALIZED:
            print("Qdrant déjà initialisé.")
            return

        print(f"Tentative de vérification/injection Qdrant...")
        
        # 1. Préparation et Fusion des faits (Logique inchangée, utilise les variables globales)
        tous_les_faits = BCS_INITIAL_FACTS.copy()
        LEXIQUE_FILE = "bcs_lexique_auto.json"
        try:
            with open(LEXIQUE_FILE, 'r', encoding='utf-8') as f:
                lexique_faits = json.load(f)
                tous_les_faits.extend(lexique_faits)
                print(f"--- FUSION DES FAITS : {len(lexique_faits)} faits du lexique chargés. ---")
        except FileNotFoundError:
            print(f"AVERTISSEMENT: Fichier lexique '{LEXIQUE_FILE}' non trouvé. Utilisation de BCS_INITIAL_FACTS uniquement.")
        except json.JSONDecodeError as e:
            print(f"ERREUR de décodage JSON dans '{LEXIQUE_FILE}'. Vérifiez le format. {e}")
            
        print(f"Total des faits à traiter : {len(tous_les_faits)}")

        # 2. Vérification et Création de la collection
        try:
            # Tente de récupérer les informations de la collection
            collection_exists = True
            try:
                await asyncio.to_thread(
                    QDRANT_CLIENT.get_collection,
                    collection_name=collection_name
                )
            except Exception:
                collection_exists = False

            # Créer la collection seulement si elle n'existe pas
            if not collection_exists:
                print(f"Collection '{collection_name}' non trouvée. Création...")
                await asyncio.to_thread(
                    QDRANT_CLIENT.recreate_collection,
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(size=dimension, distance=models.Distance.COSINE)
                )
                print(f"Collection '{collection_name}' créée.")
            else:
                print(f"Collection '{collection_name}' trouvée. Démarrage de la mise à jour B.C.S...")
            
            # 3. Injection/Mise à jour de TOUS les faits (BCS + Lexique)
            if tous_les_faits:
                print(f"Démarrage de l'injection/mise à jour B.C.S. : {len(tous_les_faits)} points...")
                
                # Récupérer les textes à embarquer
                textes_a_embarquer = [f['element_français'] for f in tous_les_faits]
                
                # --- NOUVELLE LOGIQUE DE BATCHING POUR ÉVITER LA LIMITE OPENAI ---
                
                # Taille de lot de 100 entrées est très sûre pour les embeddings OpenAI.
                CHUNK_SIZE = 100
                
                # Diviser les textes et les faits en lots correspondants
                text_batches = chunk_list(textes_a_embarquer, CHUNK_SIZE)
                fact_batches = chunk_list(tous_les_faits, CHUNK_SIZE)
                
                total_points_injected = 0
                
                print(f"Génération de {len(textes_a_embarquer)} embeddings... Traitement par lots de {CHUNK_SIZE}.")
                
                # Boucle d'injection par lots
                MAX_RETRIES = 3
                for i, (text_batch, fact_batch) in enumerate(zip(text_batches, fact_batches)):
    
                    # Messages de débogage nettoyés
                    print(f"    -> Traitement du lot {i+1}/{len(text_batches)} ({len(text_batch)} faits)...")
    
                    # 1. Génération des embeddings pour le lot 
                    embeddings_response = await asyncio.to_thread(
                        LLM_CLIENT.embeddings.create,
                        input=text_batch,
                        model=EMBEDDING_MODEL
                    )
                    
                    # 2. Création des Points avec des ID STABLES pour le lot
                    points_to_upsert = []
                    for j, fact in enumerate(fact_batch):
                        # La logique de l'ID stable reste la même (pour l'overwrite)
                        concept_key = fact.get('concept_identifie', f"bcs_fact_{total_points_injected + j}").lower().strip()
                        stable_id = int(hashlib.sha256(concept_key.encode('utf-8')).hexdigest(), 16) % (2**63)
                        
                        points_to_upsert.append(
                            models.PointStruct(
                                id=stable_id,
                                vector=embeddings_response.data[j].embedding,
                                payload=fact
                            )
                        )
                    
                    # 3. Injecter/Mettre à jour les points Qdrant pour ce lot (upsert)
                    # 🚨 LOGIQUE DE RÉESSAI APPLIQUÉE ICI 🚨
                    for attempt in range(MAX_RETRIES):
                        try:
                            # On injecte après chaque lot pour la fiabilité.
                            await asyncio.to_thread(
                                QDRANT_CLIENT.upsert,
                                collection_name=collection_name,
                                points=points_to_upsert,
                                wait=True
                            )
                            # Si l'upsert réussit, on sort de la boucle de réessai
                            break
                        except Exception as e:
                            if attempt < MAX_RETRIES - 1:
                                print(f"AVERTISSEMENT: Échec de l'injection Qdrant du lot {i+1} (Tentative {attempt+1}/{MAX_RETRIES}). Erreur: {e}. Nouvelle tentative dans 5 secondes...")
                                await asyncio.sleep(5)  # Attendre 5 secondes avant de réessayer
                            else:
                                # Si c'est la dernière tentative, on lève l'exception critique
                                print(f"ERREUR CRITIQUE: Échec de l'injection Qdrant du lot {i+1} après {MAX_RETRIES} tentatives. Détail: {e}")
                                # On lève l'exception pour que le bloc except du point 2 la capture et arrête tout.
                                raise 

                    total_points_injected += len(points_to_upsert)
    
                    # Pause augmentée (3s) pour éviter le timeout de Qdrant/OpenAI
                    print("    -> Pause de 3 secondes pour respecter les limites de débit et le délai Qdrant...")
                    await asyncio.sleep(3) # Pause asynchrone
                    
                print(f"Injection/Mise à jour B.C.S. de {total_points_injected} points terminée.")
            else:
                print("AVERTISSEMENT: Aucun fait à injecter.")

        except Exception as e:
            # Ce bloc attrape les erreurs critiques après les tentatives de réessai
            print(f"ERREUR lors de la création ou de l'injection Qdrant: {e}")
            QDRANT_CLIENT = None 
            return 

        QDRANT_INITIALIZED = True
        print(f"Initialisation Qdrant terminée. Collection '{collection_name}' prête.")


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


# Fichier : nkotronic_api.py (Fonction gerer_requete_chat corrigée)

@app.post("/chat", response_model=ChatResponse)
async def gerer_requete_chat(request: ChatRequest):
    """
    Point de terminaison asynchrone pour gérer les requêtes de chat, effectuer le RAG
    avec pré-traitement et mettre à jour la mémoire.
    """
    if not LLM_CLIENT:
        raise HTTPException(status_code=503, detail="Service LLM non initialisé. Clé API manquante ou invalide.")

    # 🚨 INITIALISATION DES VARIABLES (CORRECTION DES ERREURS PYLANCE)
    rag_enabled = QDRANT_CLIENT is not None 
    user_message_original = request.message
    user_message = user_message_original # Initialisation par défaut
    
    # Initialisation d'un contexte par défaut
    contexte_rag = "\n\nCONTEXTE MÉMOIRE RAG:\n[Aucun contexte pertinent trouvé dans la mémoire utilisateur ou dans la base de connaissances statique. Utiliser la connaissance interne.]\n\n"
    
    # 1. TENTATIVE DE TRANSCRIPTION/ANALYSE DIRECTE
    contexte_direct = transcrire_et_analyser(user_message_original)
    
    if contexte_direct:
        # Si une réponse directe est trouvée, on bypass le pré-traitement et le RAG normal
        contexte_rag = contexte_direct
        # user_message reste user_message_original (déjà initialisé)
        print("\n--- DÉBOGAGE RAG : CONTEXTE DIRECT (Transcription/Analyse) INJECTÉ ---")
        
    else:
        # Si pas de réponse directe, on procède au Pré-Traitement de la requête
        user_message = pre_traiter_requete(user_message_original)
        
        if user_message.lower() != user_message_original.lower():
            print(f"--- PRÉ-TRAITEMENT APPLIQUÉ : '{user_message_original}' -> '{user_message}' ---")

        # --- A. RAG (Retrieval-Augmented Generation) ---
        if rag_enabled:
            # Note: Le 'contexte_rag' est déjà initialisé au défaut.
            try:
                # 1. Vectorisation du message utilisateur (on utilise le user_message PRÉ-TRAITÉ pour le RAG)
                # UTILISATION D'UN BLOC TRY/EXCEPT SPÉCIFIQUE ICI (Pour les erreurs d'Embedding/API)
                try:
                    user_vector_response = await asyncio.to_thread(
                        LLM_CLIENT.embeddings.create,
                        input=[user_message],
                        model=EMBEDDING_MODEL
                    )
                    user_vector = user_vector_response.data[0].embedding
                except Exception as e:
                    # Si l'embedding échoue, on log l'erreur et on force user_vector à None.
                    print(f"ERREUR D'EMBEDDING CRITIQUE: {e}. Le RAG est désactivé pour cette requête.")
                    user_vector = None
                
                
                if user_vector: # Continuer seulement si l'embedding a réussi
                    # 2. Recherche de contexte pertinent
                    resultats_rag = await asyncio.to_thread(
                        rechercher_memoire_qdrant,
                        user_vector,
                        15 
                    )

                    # 3. Construction du contexte RAG
                    if resultats_rag:
                        contexte_rag = "\n\nCONTEXTE MÉMOIRE RAG (PRIORITÉ ABSOLUE):\n"
                        for i, point in enumerate(resultats_rag):
                            element_fr = point.payload.get('element_français', 'Information N/A')
                            element_nko = point.payload.get('element_nko', '')
                            concept = point.payload.get('concept_identifie', 'N/A')
                            
                            contexte_rag += f"FACT {i+1} (Score: {point.score:.2f}) - {concept}: {element_fr} | N'ko: {element_nko}\n"
                        contexte_rag += "\n" 

            except Exception as e:
                # Cette erreur attrape les problèmes restants (comme Qdrant)
                print(f"ERREUR RAG GÉNÉRALE : {e}")
                contexte_rag = "\n\nCONTEXTE MÉMOIRE RAG (ERREUR RAG): [Utiliser uniquement la connaissance interne]\n\n"

    # --- B. Exécution du LLM ---
    
    # --- DÉBOGAGE RAG : CONTEXTE ENVOYÉ AU LLM ---
    print(f"\n--- DÉBOGAGE RAG : CONTEXTE ENVOYÉ AU LLM ---\n{contexte_rag}\n-------------------------------------------------\n")

    # Le prompt final utilise le CONTEXTE RAG et le MESSAGE ORIGINAL
    prompt_final = PROMPT_SYSTEM + contexte_rag + f"Message Utilisateur : {user_message_original}"

    # ... (Reste de la fonction inchangée : appel LLM, post-traitement, retour) ...
    try:
        llm_completion = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "system", "content": prompt_final}]
        )
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
        # Exécution de la mise à jour de mémoire en arrière-plan
        asyncio.create_task(asyncio.to_thread(mettre_a_jour_memoire, json_data))
    elif json_data:
        print("AVERTISSEMENT: JSON de mémoire généré mais non traité car Qdrant est désactivé.")

    # --- E. Réponse Finale (Inclus memory_update) ---
    return ChatResponse(
        response_text=response_text,
        memory_update=json_data 
    )


# =================================================================
# 8. Tâche de Démarrage
# =================================================================

@app.on_event("startup")
async def startup_event():
    """
    S'exécute au démarrage de l'application pour garantir que la B.C.S. est en place.
    """
    print("Démarrage de l'application Nkotronic API...")

    if QDRANT_URL and EMBEDDING_MODEL and LLM_CLIENT:
        # CORRECTION : Appel de la fonction initialiser_qdrant avec les bons arguments
        await initialiser_qdrant(
            COLLECTION_NAME, # La collection est COLLECTION_NAME
            VECTOR_SIZE      # La dimension est VECTOR_SIZE
        )
    else:
        print("Initialisation Qdrant ignorée : Clients ou clés manquantes.")

# =================================================================
# FIN DU FICHIER
# =================================================================