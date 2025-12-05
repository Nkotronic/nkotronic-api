import asyncio
import os
import logging
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional, AsyncIterator, List
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, PointStruct, Distance, models

# --- CHARGER LE FICHIER .env ---
try:
    from dotenv import load_dotenv
    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"✅ Fichier .env chargé depuis: {env_path.absolute()}")
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.warning("⚠️ python-dotenv non installé, utilise les variables d'environnement système")

# --- LOGGING CONFIG ---
logging.getLogger("qdrant_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# --- CONFIGURATION ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

# Validation des clés au démarrage
if not OPENAI_API_KEY:
    logging.error("❌ OPENAI_API_KEY non trouvée!")
else:
    logging.info(f"✅ OPENAI_API_KEY chargée")

if not QDRANT_URL:
    logging.error("❌ QDRANT_URL non trouvée!")
else:
    logging.info(f"✅ QDRANT_URL configurée")

if not QDRANT_API_KEY:
    logging.warning("⚠️ QDRANT_API_KEY non trouvée")
else:
    logging.info(f"✅ QDRANT_API_KEY chargée")

# --- GLOBAL CLIENTS ---
LLM_CLIENT: Optional[OpenAI] = None
QDRANT_CLIENT: Optional[AsyncQdrantClient] = None

# --- CONSTANTS ---
COLLECTION_NAME = "nkotronic_knowledge_base"
VECTOR_SIZE = 1536
EMBEDDING_MODEL = "text-embedding-ada-002"
LLM_MODEL = "gpt-4o"
RAG_SCORE_THRESHOLD = 0.55
                            
PROMPT_SYSTEM = """Tu es Nkotronic, assistant N'ko amical et efficace.

CONTEXTE DISPONIBLE:
{contexte_rag}

INSTRUCTIONS:
- Utilise les traductions du contexte UNIQUEMENT si la question le demande
- N'utilise PAS les salutations du contexte sauf si l'utilisateur dit "bonjour" ou "salut"
- Réponds naturellement sans ajouter de salutations inutiles
- Si c'est une question de traduction, donne directement la réponse

EXEMPLES:
Q: "tu vas bien ?" → R: "Je vais bien, merci ! Et toi ?"
Q: "c'est quoi ߛߓߍߛߎ߲ ?" → R: "ߛߓߍߛߎ߲ signifie 'lettre' en français."
Q: "bonjour" → R: "ߒߞߏ ߛߌ ! Comment puis-je t'aider ?"

Question: {user_message}

Réponds maintenant:"""

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
    global LLM_CLIENT, QDRANT_CLIENT
    logging.info("🚀 Démarrage de l'API Nkotronic...")

    # 1️⃣ INIT OpenAI
    try:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY manquante!")
        
        LLM_CLIENT = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)
        test_response = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        logging.info("✅ Client OpenAI initialisé et testé")
    except Exception as e:
        logging.error(f"❌ Erreur OpenAI: {e}")
        LLM_CLIENT = None
        yield {}
        return

    # 2️⃣ INIT Qdrant
    if QDRANT_URL and QDRANT_API_KEY:
        try:
            QDRANT_CLIENT = AsyncQdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                prefer_grpc=False,
                timeout=30.0
            )
            
            # Vérifier si la collection existe déjà
            collections = await QDRANT_CLIENT.get_collections()
            exists = any(c.name == COLLECTION_NAME for c in collections.collections)
            
            if exists:
                count = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
                logging.info(f"✅ Collection '{COLLECTION_NAME}' trouvée avec {count.count} points")
            else:
                await QDRANT_CLIENT.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
                )
                logging.info(f"✅ Collection '{COLLECTION_NAME}' créée")

        except Exception as e:
            logging.error(f"❌ Erreur Qdrant: {e}")
            QDRANT_CLIENT = None
    else:
        logging.warning("⚠️ Qdrant non configuré")

    logging.info("✅ API Nkotronic prête!")
    yield {}
    logging.info("🛑 Arrêt de l'API Nkotronic")

app = FastAPI(
    title="Nkotronic API",
    description="API de traduction Français ↔ N'ko avec mémoire RAG",
    version="2.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class ChatRequest(BaseModel):
    user_message: str = Field(..., description="Message utilisateur")
    rag_enabled: bool = Field(True, description="Activer le RAG")
    debug: bool = Field(False, description="Mode debug avec détails")

class ChatResponse(BaseModel):
    response_text: str = Field(..., description="Texte de réponse")
    memory_update: Optional[dict] = Field(None, description="Mise à jour mémoire")
    debug_info: Optional[dict] = Field(None, description="Infos de debug")

class TranslationEntry(BaseModel):
    element_français: str = Field(..., description="Le mot ou expression en français.")
    element_nko: str = Field(..., description="La traduction correspondante en N'ko.")
    concept_identifie: str = Field("Général", description="Le domaine ou concept identifié.")

# --- FONCTION D'EXTRACTION MOT-CLÉ ---
async def extraire_mot_cle(user_message: str, llm_client: OpenAI) -> str:
    """Extrait le mot français à traduire de manière robuste."""
    import re
    
    # Recherche de mots entre guillemets
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", user_message)
    if quoted:
        mot = quoted[0].strip().lower()
        logging.info(f"🔑 Mot extrait des guillemets: '{mot}'")
        return mot
    
    # Extraction via LLM
    prompt = f"""Extrait UNIQUEMENT le mot français à traduire. Réponds avec UN SEUL MOT.

Exemples:
- "comment dit-on silex en n'ko" -> silex
- "traduction de bonjour" -> bonjour
- "c'est quoi eau" -> eau

Question: {user_message}
Mot:"""

    try:
        resp = await asyncio.to_thread(
            llm_client.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        mot = resp.choices[0].message.content.strip().lower()
        mot = re.sub(r'[^\w\s-]', '', mot).strip()
        logging.info(f"🔑 Mot-clé extrait par LLM: '{mot}'")
        return mot
    except Exception as e:
        logging.error(f"❌ Erreur extraction: {e}")
        words = user_message.lower().split()
        stop_words = {'comment', 'dit', 'on', 'en', 'nko', 'n\'ko', 'traduction', 'de', 'le', 'la', 'un', 'une', 'c\'est', 'quoi'}
        significant = [w for w in words if w not in stop_words and len(w) > 2]
        return significant[-1] if significant else user_message.lower()

# --- RECHERCHE MULTI-STRATÉGIE ---
async def recherche_intelligente(mot_cle: str, llm_client: OpenAI, qdrant_client: AsyncQdrantClient):
    """Recherche avec plusieurs stratégies pour maximiser les résultats."""
    all_results = []
    
    # STRATÉGIE 1: Recherche exacte
    try:
        logging.info(f"🔍 Stratégie 1: Recherche exacte pour '{mot_cle}'")
        emb_resp = await asyncio.to_thread(
            llm_client.embeddings.create,
            input=[mot_cle],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        result = await qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=20,
            with_payload=True
        )
        hits = result.points
        all_results.extend(hits)
        logging.info(f"   -> {len(hits)} résultats trouvés")
    except Exception as e:
        logging.error(f"❌ Stratégie 1 échouée: {e}")
    
    # STRATÉGIE 2: Recherche avec variantes
    variantes = [
        mot_cle,
        mot_cle + 's',
        mot_cle.rstrip('s'),
        mot_cle.replace('é', 'e').replace('è', 'e').replace('ê', 'e'),
    ]
    variantes = list(set(variantes))
    
    if len(variantes) > 1:
        try:
            logging.info(f"🔍 Stratégie 2: Recherche avec variantes {variantes}")
            emb_resp = await asyncio.to_thread(
                llm_client.embeddings.create,
                input=variantes,
                model=EMBEDDING_MODEL
            )
            
            for i, var in enumerate(variantes[1:], 1):
                vector = emb_resp.data[i].embedding
                result = await qdrant_client.query_points(
                    collection_name=COLLECTION_NAME,
                    query=vector,
                    limit=10,
                    with_payload=True
                )
                hits = result.points
                all_results.extend(hits)
            logging.info(f"   -> {len(all_results)} résultats totaux")
        except Exception as e:
            logging.error(f"❌ Stratégie 2 échouée: {e}")
    
    # STRATÉGIE 3: Échantillon de la base
    try:
        sample = await qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            limit=5,
            with_payload=True
        )
        logging.info(f"📚 Échantillon de la base (5 premiers):")
        for point in sample[0]:
            logging.info(f"   - {point.payload}")
    except Exception as e:
        logging.error(f"❌ Échantillon échoué: {e}")
    
    # Dédupliquer et trier
    seen_ids = set()
    unique_results = []
    for hit in all_results:
        if hit.id not in seen_ids:
            seen_ids.add(hit.id)
            unique_results.append(hit)
    
    unique_results.sort(key=lambda x: x.score, reverse=True)
    return unique_results

# --- PRÉ-TRAITEMENT INTELLIGENT ---
async def pretraiter_question(user_message: str, llm_client: OpenAI, qdrant_client: AsyncQdrantClient):
    """Détecte les mots N'ko et les traduit pour enrichir la recherche."""
    import re
    
    # Regex pour détecter les caractères N'ko (U+07C0 à U+07FF)
    nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
    nko_words = nko_pattern.findall(user_message)
    
    if not nko_words:
        return user_message, []
    
    logging.info(f"🔍 Mots N'ko détectés dans la question: {nko_words}")
    
    traductions = []
    for nko_word in nko_words:
        try:
            # Créer un embedding du mot N'ko
            emb_resp = await asyncio.to_thread(
                llm_client.embeddings.create,
                input=[nko_word],
                model=EMBEDDING_MODEL
            )
            vector = emb_resp.data[0].embedding
            
            # Rechercher les points similaires
            results = await qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                limit=10,
                with_payload=True
            )
            
            # Chercher celui qui a exactement ce mot N'ko
            for point in results.points:
                if point.payload.get('element_nko') == nko_word:
                    fr = point.payload.get('element_français')
                    if fr:
                        traductions.append({
                            'nko': nko_word,
                            'français': fr,
                            'payload': point.payload
                        })
                        logging.info(f"✅ Traduction trouvée: {nko_word} = {fr}")
                        break
            
            if not any(t['nko'] == nko_word for t in traductions):
                logging.warning(f"⚠️ Aucune traduction trouvée pour: {nko_word}")
                
        except Exception as e:
            logging.error(f"❌ Erreur lors de la recherche de {nko_word}: {e}")
    
    # Enrichir la question
    question_enrichie = user_message
    for trad in traductions:
        question_enrichie = question_enrichie.replace(
            trad['nko'], 
            f"{trad['nko']} ({trad['français']})"
        )
    
    if traductions:
        logging.info(f"💡 Question enrichie: {question_enrichie}")
    
    return question_enrichie, traductions

# --- ENDPOINT CHAT ---
@app.post('/chat', response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    global LLM_CLIENT, QDRANT_CLIENT

    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='LLM non initialisé')

    debug_info = {} if req.debug else None
    rag_active = req.rag_enabled and (QDRANT_CLIENT is not None)
    contexte_rag_text = '[Aucune donnée en mémoire]'

    try:
        if rag_active:
            try:
                # Pré-traiter la question
                question_enrichie, traductions_contexte = await pretraiter_question(
                    req.user_message, 
                    LLM_CLIENT, 
                    QDRANT_CLIENT
                )
                
                if req.debug:
                    debug_info['question_enrichie'] = question_enrichie
                    debug_info['traductions_contexte'] = traductions_contexte
                
                # Extraire le mot-clé
                mot_cle = await extraire_mot_cle(question_enrichie, LLM_CLIENT)
                if req.debug:
                    debug_info['mot_cle_extrait'] = mot_cle

                # Recherche intelligente
                hits = await recherche_intelligente(mot_cle, LLM_CLIENT, QDRANT_CLIENT)

                # Afficher top résultats
                logging.info(f"📊 TOP 10 RÉSULTATS pour '{mot_cle}':")
                for i, h in enumerate(hits[:10], 1):
                    logging.info(f"  #{i}: score={h.score:.4f} -> {h.payload.get('element_français', 'N/A')}")
                
                if req.debug:
                    debug_info['top_results'] = [
                        {'score': h.score, 'payload': h.payload} 
                        for h in hits[:10]
                    ]

                # Filtrer résultats pertinents
                pertinents = [h for h in hits if h.score > RAG_SCORE_THRESHOLD]

                if pertinents:
                    logging.info(f"✅ {len(pertinents)} résultat(s) pertinent(s) (score > {RAG_SCORE_THRESHOLD})")
                    # Format simplifié et clair
                    lignes = []
                    for h in pertinents[:5]:
                        fr = h.payload.get('element_français', '')
                        nko = h.payload.get('element_nko', '')
                        concept = h.payload.get('concept_identifie', '')
                        lignes.append(f"- {fr} = {nko} ({concept})")
                    contexte_rag_text = '\n'.join(lignes)
                else:
                    logging.warning(f"⚠️ Aucun résultat > {RAG_SCORE_THRESHOLD}")
                    if hits:
                        logging.info(f"💡 Utilisation des 3 meilleurs résultats")
                        lignes = []
                        for h in hits[:3]:
                            fr = h.payload.get('element_français', '')
                            nko = h.payload.get('element_nko', '')
                            concept = h.payload.get('concept_identifie', '')
                            lignes.append(f"- {fr} = {nko} ({concept})")
                        contexte_rag_text = '\n'.join(lignes)

                # Ajouter les traductions contextuelles
                if traductions_contexte:
                    contexte_extra = '\n'.join(
                        f"- {t['français']} = {t['nko']}"
                        for t in traductions_contexte
                    )
                    contexte_rag_text = contexte_extra + '\n' + contexte_rag_text

            except Exception as e:
                logging.error(f"❌ Erreur RAG: {e}", exc_info=True)
                if req.debug:
                    debug_info['rag_error'] = str(e)
                rag_active = False

        # Debug: afficher le contexte envoyé
        logging.info(f"📤 CONTEXTE ENVOYÉ AU LLM:\n{contexte_rag_text}")

        # Build prompt
        prompt = PROMPT_SYSTEM.format(
            contexte_rag=contexte_rag_text,
            user_message=req.user_message
        )

        # Call LLM
        llm_resp = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=300
        )
        llm_output = llm_resp.choices[0].message.content
        logging.info("✅ Réponse LLM reçue")

        # Extract text and memory JSON
        def separer_texte_et_json(output: str):
            start = output.find('```json')
            if start == -1:
                return output.strip(), None
            end = output.find('```', start + 7)
            if end == -1:
                return output.strip(), None
            text = output[:start].strip()
            json_str = output[start + 7:end].strip()
            try:
                return text, json.loads(json_str)
            except:
                return output.strip(), None

        response_text, memory_json = separer_texte_et_json(llm_output)

        return ChatResponse(
            response_text=response_text,
            memory_update=memory_json,
            debug_info=debug_info
        )
    
    except Exception as e:
        logging.error(f"❌ Erreur critique dans /chat: {e}", exc_info=True)
        return ChatResponse(
            response_text=f"Erreur interne : {str(e)}",
            memory_update=None,
            debug_info={'error': str(e)} if req.debug else None
        )

# --- ENDPOINT AJOUT TRADUCTION ---
@app.post('/add_translation', response_model=dict)
async def add_translation(entries: List[TranslationEntry]):
    """Ajoute une liste de traductions à Qdrant."""
    global LLM_CLIENT, QDRANT_CLIENT

    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='LLM non initialisé')
    if QDRANT_CLIENT is None:
        raise HTTPException(status_code=503, detail='Qdrant non initialisé')

    if not entries:
        return {"status": "warning", "message": "Aucune entrée fournie."}

    try:
        french_elements = [entry.element_français for entry in entries]
        num_elements = len(french_elements)

        logging.info(f"🔄 Génération de {num_elements} embeddings...")
        emb_resp = await asyncio.to_thread(
            LLM_CLIENT.embeddings.create,
            input=french_elements,
            model=EMBEDDING_MODEL
        )
        vectors = [data.embedding for data in emb_resp.data]

        points_to_upsert: List[PointStruct] = []
        for i, entry in enumerate(entries):
            payload = entry.model_dump()
            
            point = PointStruct(
                id=uuid.uuid4().int >> 64,
                vector=vectors[i],
                payload=payload
            )
            points_to_upsert.append(point)

        logging.info(f"💾 Upsert de {num_elements} points dans '{COLLECTION_NAME}'...")
        operation_info = await QDRANT_CLIENT.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert,
            wait=True
        )

        logging.info(f"✅ {num_elements} traductions ajoutées. Status: {operation_info.status.value}")
        return {
            "status": "success",
            "message": f"{num_elements} traductions ajoutées à Qdrant.",
            "qdrant_status": operation_info.status.value,
            "elements_added": num_elements
        }

    except Exception as e:
        logging.error(f"❌ Erreur ajout traduction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")

# --- ENDPOINTS UTILITAIRES ---
@app.get('/')
async def root():
    count = 0
    if QDRANT_CLIENT:
        try:
            c = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
            count = c.count
        except:
            pass
    
    return {
        'service': 'Nkotronic API',
        'version': '2.0.0',
        'status': 'running',
        'llm_status': 'ok' if LLM_CLIENT else 'error',
        'qdrant_status': 'ok' if QDRANT_CLIENT else 'disabled',
        'memory_size': count
    }

@app.get('/health')
async def health():
    health_status = {
        'llm': LLM_CLIENT is not None,
        'qdrant': QDRANT_CLIENT is not None
    }
    
    if not all(health_status.values()):
        raise HTTPException(status_code=503, detail=health_status)
    
    return {'status': 'healthy', 'components': health_status}

@app.get('/stats')
async def stats():
    """Statistiques de la base de données"""
    if QDRANT_CLIENT is None:
        raise HTTPException(status_code=503, detail='Qdrant non disponible')
    
    try:
        count = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
        sample = await QDRANT_CLIENT.scroll(
            collection_name=COLLECTION_NAME,
            limit=10,
            with_payload=True
        )
        
        return {
            'total_points': count.count,
            'collection_name': COLLECTION_NAME,
            'sample': [p.payload for p in sample[0]]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/search_direct')
async def search_direct(word: str):
    """Recherche directe dans Qdrant pour debug"""
    if QDRANT_CLIENT is None or LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='Services non disponibles')
    
    try:
        emb_resp = await asyncio.to_thread(
            LLM_CLIENT.embeddings.create,
            input=[word],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        result = await QDRANT_CLIENT.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=20,
            with_payload=True
        )
        hits = result.points
        
        return {
            'query': word,
            'results_count': len(hits),
            'top_10': [
                {
                    'score': h.score,
                    'element_français': h.payload.get('element_français', 'N/A'),
                    'element_nko': h.payload.get('element_nko', 'N/A'),
                    'concept': h.payload.get('concept_identifie', 'N/A')
                }
                for h in hits[:10]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))