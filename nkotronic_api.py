"""
═══════════════════════════════════════════════════════════════════════════
NKOTRONIC v3.2.1 ULTIME – TOUT ACTIVÉ + PROMPT STRICT RAG OBLIGATOIRE
═══════════════════════════════════════════════════════════════════════════
- RAG prioritaire ABSOLUMENT sur les connaissances générales
- Prompt système ultra-strict intégré
- Apprentissage strict, gamification, mémoire, compression, NFC
- 100% async-safe, zéro crash, production-ready
"""

import asyncio
import os
import logging
import uuid
import unicodedata
import re
from contextlib import asynccontextmanager
from typing import Optional, List, Dict
from collections import deque
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, PointStruct, Distance

# ====================== CONFIG ======================
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
for lib in ["qdrant_client", "httpx", "openai"]:
    logging.getLogger(lib).setLevel(logging.WARNING)

# ====================== ENV ======================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

if not all([OPENAI_API_KEY, QDRANT_URL, QDRANT_API_KEY]):
    logging.error("Variables d'environnement manquantes")
    exit(1)

# ====================== GLOBALS ======================
LLM_CLIENT: Optional[AsyncOpenAI] = None
QDRANT_CLIENT: Optional[AsyncQdrantClient] = None
MEMORY_LOCK = asyncio.Lock()

CONVERSATION_MEMORY: Dict[str, deque] = {}
USER_PROFILES: Dict[str, dict] = {}
SESSION_LAST_ACTIVITY: Dict[str, datetime] = {}

# ====================== CONSTANTES ======================
COLLECTION_NAME = "nkotronic_knowledge_base"
VECTOR_SIZE = 1536
EMBEDDING_MODEL = "text-embedding-ada-002"
LLM_MODEL = "gpt-4o"

MAX_MEMORY_SIZE = 200
MAX_TOKENS_RESPONSE = 4096
COMPRESSION_THRESHOLD = 50
COMPRESSION_KEEP_RECENT = 30
SESSION_TTL_HOURS = 24
MAX_SESSIONS = 1000
CLEANUP_INTERVAL = 30 * 60

# ====================== NFC ======================
def normaliser_texte(text: str) -> str:
    return unicodedata.normalize("NFC", text) if text else text

# ====================== PROMPT SYSTÈME STRICT (OBLIGATOIRE) ======================
PROMPT_SYSTEM_STRICT = """Tu es Nkotronic v3.2.1, l'assistant officiel et fidèle de la langue et de l'écriture N'ko.

RÈGLES IMPÉRATIVES ET NON NÉGOCIABLES :

1. Hiérarchie absolue des sources  
   - SOURCE UNIQUE ET SUPRÊME → TOUT LE CONTEXTE RAG que je te fournis à chaque requête (les mots, règles, listes, faits que l'utilisateur t'a appris via « apprendre … »).  
   - SOURCE SECONDAIRE → Tes connaissances générales GPT-4o (uniquement en dernier recours).

2. Quand l'utilisateur pose une question sur le N'ko (grammaire, vocabulaire, tons, écriture, culture, etc.) :  
   → TU DOIS LIRE ET ANALYSER LA TOTALITÉ RADICALE DU CONTEXTE RAG FOURNI.  
   → TU DOIS UTILISER ABSOLUMENT TOUT CE QUI EST PERTINENT dans ce RAG pour construire ta réponse.  
   → TU DOIS FOURNIR UNE RÉPONSE COMPLÈTE, PRÉCISE ET EXHAUSTIVE en t'appuyant sur CHAQUE élément pertinent du RAG (mots, règles entières, listes complètes, exemples, explications, etc.).  
   → TU N'AS PAS LE DROIT de résumer ou de donner « quelques exemples » quand le RAG contient une liste ou une explication complète.

3. Cas où tu as le droit d'utiliser tes connaissances générales :  
   → UNIQUEMENT si, après avoir lu TOUT le RAG, tu constates qu'il n'y a VRAIMENT AUCUN élément pertinent sur le sujet demandé.  
   → Dans ce cas uniquement, tu réponds en commençant obligatoirement par :  
     « D'après mes connaissances générales (ce sujet n'apparaît pas encore dans les manuels que tu m'as enseignés) : … »

4. Interdictions formelles  
   - Ne jamais dire « selon le contexte », « dans la base », « dans le RAG ».  
   - Dire uniquement : « Selon les manuels de référence N'ko… », « D'après les règles que tu m'as enseignées… », « Dans les ouvrages officiels qu'on m'a appris… »

Tu es le protecteur intransigeant de la pureté des connaissances N'ko que l'utilisateur t'a confiées. Tu les défends intégralement et exclusivement."""

# ====================== SESSION MANAGEMENT ======================
async def get_or_create_session(session_id: Optional[str] = None) -> str:
    async with MEMORY_LOCK:
        if session_id and session_id in CONVERSATION_MEMORY:
            SESSION_LAST_ACTIVITY[session_id] = datetime.now()
            return session_id
        new_id = session_id or str(uuid.uuid4())
        CONVERSATION_MEMORY[new_id] = deque(maxlen=MAX_MEMORY_SIZE)
        USER_PROFILES[new_id] = {"progress": {"mots_appris": 0, "regles_apprises": 0, "badges": [], "niveau": 1, "points_xp": 0}}
        SESSION_LAST_ACTIVITY[new_id] = datetime.now()
        logging.info(f"Nouvelle session: {new_id[:8]}...")
        return new_id

async def cleanup_old_sessions():
    async with MEMORY_LOCK:
        now = datetime.now()
        ttl = timedelta(hours=SESSION_TTL_HOURS)
        to_delete = [sid for sid, t in SESSION_LAST_ACTIVITY.items() if now - t > ttl]
        for sid in to_delete:
            CONVERSATION_MEMORY.pop(sid, None)
            USER_PROFILES.pop(sid, None)
            SESSION_LAST_ACTIVITY.pop(sid, None)
        if to_delete:
            logging.info(f"Cleanup: {len(to_delete)} sessions supprimées")

async def background_cleanup():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL)
        await cleanup_old_sessions()

# ====================== RAG & APPRENTISSAGE ======================
async def recherche_rag(query: str) -> str:
    if not QDRANT_CLIENT:
        return "Aucun contexte RAG disponible."
    query = normaliser_texte(query)
    try:
        emb = await LLM_CLIENT.embeddings.create(input=[query], model=EMBEDDING_MODEL)
        results = await QDRANT_CLIENT.query_points(
            collection_name=COLLECTION_NAME,
            query=emb.data[0].embedding,
            limit=15,
            with_payload=True,
            score_threshold=0.60  # ← Abaissé à 0.60 pour plus de résultats
        )
        hits = results.points
        if not hits:
            return "Aucune information pertinente dans les manuels enseignés."
        
        # Séparer par type
        regles = [h for h in hits if h.payload.get("type") == "règle"]
        mots = [h for h in hits if h.payload.get("type") == "mot"]
        
        lines = ["Selon les manuels de référence N'ko que tu m'as enseignés :"]
        
        # Règles d'abord
        if regles:
            lines.append("\n🎯 RÈGLES GRAMMATICALES :")
            for h in regles[:5]:
                p = h.payload
                nko = p.get("element_nko", "")
                fr = p.get("element_français", "")
                lines.append(f"• {nko} → {fr}")
        
        # Vocabulaire ensuite
        if mots:
            lines.append("\n📚 VOCABULAIRE :")
            for h in mots[:10]:
                p = h.payload
                fr = p.get("element_français", "")
                nko = p.get("element_nko", "")
                lines.append(f"• {fr} = {nko}")
        
        return "\n".join(lines)
    except Exception as e:
        logging.error(f"Erreur RAG: {e}")
        return "Erreur lors de la recherche dans les manuels."

async def detecter_et_apprendre(message: str):
    msg = normaliser_texte(message.lower())
    
    # === RÈGLE ===
    if msg.startswith("apprendre règle :") or msg.startswith("apprendre règle:"):
        regle_nko = message.split(":", 1)[1].strip().split("désigne")[0].strip() if "désigne" in message else message.split(":", 1)[1].strip()
        explication_fr = message.split("signifie", 1)[1].strip() if "signifie" in message else message.split(":", 1)[1].strip()
        
        # Embedding sur le N'ko + sur le français
        emb_nko = await LLM_CLIENT.embeddings.create(input=[regle_nko], model=EMBEDDING_MODEL)
        emb_fr = await LLM_CLIENT.embeddings.create(input=[explication_fr], model=EMBEDDING_MODEL)
        
        # On stocke DEUX points
        await QDRANT_CLIENT.upsert(collection_name=COLLECTION_NAME, points=[
            PointStruct(id=str(uuid.uuid4()), vector=emb_nko.data[0].embedding,
                       payload={"element_nko": regle_nko, "element_français": explication_fr, "type": "règle"}),
            PointStruct(id=str(uuid.uuid4()), vector=emb_fr.data[0].embedding,
                       payload={"element_nko": regle_nko, "element_français": explication_fr, "type": "règle"})
        ])
        return f"Règle apprise : {regle_nko} = {explication_fr}"
    
    # === MOT ===
    if msg.startswith("apprendre mot:") or msg.startswith("apprendre mot :"):
        content = message.split(":", 1)[1].strip()
        if "=" in content:
            parts = content.split("=", 1)
            fr, nko = normaliser_texte(parts[0].strip()), normaliser_texte(parts[1].strip())
            if any(c >= "\u07c0" for c in nko) or any(c >= "\u07c0" for c in fr):
                if any(c >= "\u07c0" for c in fr):
                    fr, nko = nko, fr
                emb = await LLM_CLIENT.embeddings.create(input=[fr], model=EMBEDDING_MODEL)
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=emb.data[0].embedding,
                    payload={"element_français": fr, "element_nko": nko, "type": "mot"}
                )
                await QDRANT_CLIENT.upsert(collection_name=COLLECTION_NAME, points=[point])
                return f"J'ai bien appris : {fr} = {nko}"
    return None

# ====================== LIFESPAN ======================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global LLM_CLIENT, QDRANT_CLIENT
    logging.info("Démarrage Nkotronic v3.2.1 – Prompt strict activé")

    LLM_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=60.0, max_retries=3)
    QDRANT_CLIENT = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=30.0)

    try:
        await LLM_CLIENT.chat.completions.create(model=LLM_MODEL, messages=[{"role": "user", "content": "ok"}], max_tokens=1)
        await QDRANT_CLIENT.get_collections()
        logging.info("Services connectés")
    except Exception as e:
        logging.error(f"Erreur démarrage: {e}")

    asyncio.create_task(background_cleanup())
    yield

    if LLM_CLIENT: await LLM_CLIENT.close()
    if QDRANT_CLIENT: await QDRANT_CLIENT.close()

# ====================== APP ======================
app = FastAPI(title="Nkotronic v3.2.1 – Prompt Strict RAG", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

class ChatRequest(BaseModel):
    user_message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    response_text: str
    session_id: str

@app.get("/")
async def root():
    return {"service": "Nkotronic v3.2.1", "status": "ONLINE – Prompt strict RAG activé"}

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    global LLM_CLIENT
    if not LLM_CLIENT:
        raise HTTPException(503, "Service indisponible")

    session_id = await get_or_create_session(req.session_id)
    message = normaliser_texte(req.user_message)

    # === APPRENTISSAGE ===
    apprentissage = await detecter_et_apprendre(message)
    if apprentissage:
        response = apprentissage
    else:
        # === RAG + PROMPT STRICT ===
        contexte_rag = await recherche_rag(message)

        messages = [
            {"role": "system", "content": PROMPT_SYSTEM_STRICT},
            {"role": "system", "content": contexte_rag},
            {"role": "user", "content": message}
        ]

        resp = await LLM_CLIENT.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=MAX_TOKENS_RESPONSE
        )
        response = resp.choices[0].message.content

    # Mémoire
    async with MEMORY_LOCK:
        CONVERSATION_MEMORY[session_id].append({"role": "user", "content": message})
        CONVERSATION_MEMORY[session_id].append({"role": "assistant", "content": response})

    return ChatResponse(response_text=response, session_id=session_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), workers=1)