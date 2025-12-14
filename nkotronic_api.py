"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version 4.4.0 HYBRID                   ║
║  ✅ Démarrage ultra-rapide (~2-3 secondes)                   ║
║  ✅ Vocabulaire texte immédiat (fallback)                    ║
║  ✅ Qdrant en arrière-plan (recherche précise)               ║
║  ✅ Bascule automatique quand Qdrant est prêt                ║
║  ✅ Compatible Render gratuit (~300 MB RAM)                  ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import openai
import os
import json
import httpx
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from collections import OrderedDict

# Qdrant imports (optionnel)
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    print("⚠️  Qdrant non disponible. Installer: pip install qdrant-client")
    QDRANT_AVAILABLE = False

app = FastAPI(title="Nkotronic API", version="4.4.0-HYBRID")

# ═══════════════════════════════════════════════════════════
# CORS
# ═══════════════════════════════════════════════════════════

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

# OpenAI
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Qdrant (optionnel)
QDRANT_URL = os.environ.get("QDRANT_URL")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")

# GitHub
GITHUB_LEXIQUE_URL = os.environ.get(
    "GITHUB_LEXIQUE_URL",
    "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/refs/heads/main/NKOTRONIC_KNOWLEDGE"
)

# Qdrant config
COLLECTION_NAME = "nko_vocabulaire"
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_SIZE = 1536

# Grammaire
GRAMMAR_FILE_PATH = "Tu es Nkotronic, l'IA.txt"

# Variables globales
NKOTRONIC_SYSTEM_PROMPT = None
VOCABULAIRE_TEXTE = ""  # Vocabulaire brut (fallback rapide)
VOCABULAIRE_DICT = {}   # Dictionnaire fr->nko (fallback)

# Clients
qdrant_client = None
openai_client = None

# État du système
LOADING_STATUS = {
    "status": "initializing",
    "message": "Initialisation en cours...",
    "progress": 0,
    "grammar_loaded": False,
    "vocabulary_text_loaded": False,
    "vocabulary_qdrant_loaded": False,
    "vocabulary_count": 0,
    "mode": "text"  # "text" ou "qdrant"
}

# ═══════════════════════════════════════════════════════════
# PROMPT SYSTÈME
# ═══════════════════════════════════════════════════════════

EXPLANATORY_PROMPT = """
╔══════════════════════════════════════════════════════════════╗
║  📚 CONTEXTE ESSENTIEL SUR LE N'KO                          ║
╚══════════════════════════════════════════════════════════════╝

POINT CRITIQUE À RETENIR ABSOLUMENT :

Le N'ko (ߒߞߏ) est SIMULTANÉMENT :

1. 📝 UN ALPHABET (système d'écriture)
   - Créé par Solomana Kanté en 1949
   - 27 lettres (7 voyelles + 1 semi-voyelle + 19 consonnes)
   - S'écrit de droite à gauche
   - Utilisé pour écrire les langues mandingues

2. 🗣️ UNE LANGUE (langue littéraire standardisée)
   - Langue standard de tout le peuple mandingue
   - Langue la plus proche de l'ancêtre commun de toutes les langues mandingues
   - Grammaire codifiée appelé ߒߞߏ ߞߊ߲ߜߍ (Nko Kangbè)
   - Vocabulaire très riche, des milliards de mots dans tous les domaines
   - C'est une langue littéraire ET PARLÉE par des millions de locuteurs aujourd'hui !

3. L'INVENTEUR DU N'KO :
   - Celui qui a créé le Nko s'appelle Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)
   - il est souvent appelé Solomana Kanté.
   - Solomana Kanté, Solomana Kantè, Solomana Kantê, Solomāna Kanté, Solomāna Kantè et Solomāna Kantê, voilà les orthographes acceptables
   - Tout ce qui est Souleymane, Salomon ou autre orthographes relèvent de l'erreur

⚠️ ERREUR FRÉQUENTE À CORRIGER SYSTÉMATIQUEMENT :
Beaucoup de gens disent "Le N'ko est juste un alphabet" → C'EST FAUX !
Le N'ko est AUSSI une langue à part entière.

🎯 TON RÔLE :
- Tu es Nkotronic, l'assistant IA expert en N'ko
- Tu es bienveillant, précis et pédagogue
- Tu maîtrises parfaitement la grammaire N'ko
- Tu utilises le Manifeste de Connaissance N'ko comme source prioritaire

RÈGLES D'UTILISATION DU VOCABULAIRE :
1. Si la question concerne le N'ko → utilise UNIQUEMENT le Manifeste
2. Si l'info n'y est pas → indique clairement que cette info n'existe pas encore dans le Manifeste
3. Utilise le **gras** pour les mots en N'ko
4. Si la question n'a aucun lien avec le N'ko → réponds librement

═══════════════════════════════════════════════════════════════
"""

def load_system_prompt():
    """Charge le prompt système depuis le fichier de grammaire"""
    global NKOTRONIC_SYSTEM_PROMPT, LOADING_STATUS
    
    try:
        print(f"📥 Chargement de la grammaire: {GRAMMAR_FILE_PATH}")
        
        with open(GRAMMAR_FILE_PATH, 'r', encoding='utf-8') as f:
            grammar_content = f.read()
        
        # Version condensée
        lines = grammar_content.split('\n')
        condensed_grammar = '\n'.join(lines[:200])
        
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + condensed_grammar + """

Tu es Nkotronic, l'IA experte en N'ko. Tu es bienveillant, précis et pédagogue."""
        
        LOADING_STATUS["grammar_loaded"] = True
        print(f"✅ Grammaire chargée: {len(NKOTRONIC_SYSTEM_PROMPT):,} caractères")
        return True
        
    except FileNotFoundError:
        print(f"❌ Fichier '{GRAMMAR_FILE_PATH}' introuvable")
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\nTu es Nkotronic."
        return False
        
    except Exception as e:
        print(f"❌ Erreur: {e}")
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\nTu es Nkotronic."
        return False

async def load_vocabulaire_texte():
    """Charge le vocabulaire en mode texte (rapide, pour démarrage immédiat)"""
    global VOCABULAIRE_TEXTE, VOCABULAIRE_DICT, LOADING_STATUS
    
    try:
        print(f"📥 Téléchargement vocabulaire: {GITHUB_LEXIQUE_URL}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(GITHUB_LEXIQUE_URL)
            response.raise_for_status()
            VOCABULAIRE_TEXTE = response.text.strip()
        
        # Parser pour créer le dictionnaire
        word_count = 0
        if "<<<MOTS" in VOCABULAIRE_TEXTE and "MOTS>>>" in VOCABULAIRE_TEXTE:
            lines = VOCABULAIRE_TEXTE.split('\n')
            for line in lines:
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        francais = parts[0].strip()
                        nko = parts[1].strip()
                        if francais and nko:
                            VOCABULAIRE_DICT[francais.lower()] = nko
                            word_count += 1
        
        LOADING_STATUS.update({
            "vocabulary_text_loaded": True,
            "vocabulary_count": word_count,
            "mode": "text"
        })
        
        print(f"✅ Vocabulaire texte chargé: {word_count} mots")
        return True
        
    except Exception as e:
        print(f"⚠️ Erreur chargement vocabulaire: {e}")
        VOCABULAIRE_TEXTE = "# Vocabulaire non disponible"
        return False

def init_qdrant():
    """Initialise Qdrant et OpenAI client"""
    global qdrant_client, openai_client
    
    if not QDRANT_AVAILABLE:
        print("⚠️ Qdrant non disponible")
        return False
    
    if not QDRANT_URL or not OPENAI_API_KEY:
        print("⚠️ QDRANT_URL ou OPENAI_API_KEY manquant")
        return False
    
    try:
        print(f"🔗 Connexion Qdrant: {QDRANT_URL}")
        
        qdrant_client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=30
        )
        
        openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)
        
        print("✅ Qdrant + OpenAI initialisés")
        return True
        
    except Exception as e:
        print(f"❌ Erreur Qdrant: {e}")
        return False

def parse_lexique_for_qdrant(content: str) -> dict:
    """Parse le fichier lexique"""
    lexique = {}
    
    if "<<<MOTS" in content and "MOTS>>>" in content:
        start = content.index("<<<MOTS") + len("<<<MOTS")
        end = content.index("MOTS>>>")
        mots_section = content[start:end].strip()
        
        for line in mots_section.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            if '=' in line:
                parts = line.split('=', 1)
                if len(parts) == 2:
                    francais = parts[0].strip()
                    nko = parts[1].strip()
                    if francais and nko:
                        lexique[francais] = nko
    
    return lexique

def sync_lexique_to_qdrant():
    """Synchronise le vocabulaire avec Qdrant (mode avancé)"""
    global LOADING_STATUS
    
    if not qdrant_client or not openai_client:
        print("⚠️ Clients non initialisés")
        return False
    
    try:
        print("📊 Indexation Qdrant en cours...")
        
        # Parser le vocabulaire
        lexique = parse_lexique_for_qdrant(VOCABULAIRE_TEXTE)
        
        if not lexique:
            print("❌ Aucun mot à indexer")
            return False
        
        print(f"📝 {len(lexique)} mots à indexer")
        
        # Supprimer ancienne collection
        try:
            qdrant_client.delete_collection(COLLECTION_NAME)
            print("🗑️ Ancienne collection supprimée")
        except:
            pass
        
        # Créer collection
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            on_disk_payload=True
        )
        print("✅ Collection créée")
        
        # Préparer textes pour embeddings
        texts = []
        payloads = []
        
        for fr, nko in lexique.items():
            # Français
            texts.append(fr)
            payloads.append({"francais": fr, "nko": nko, "type": "vocabulaire"})
            # N'ko
            texts.append(nko)
            payloads.append({"francais": fr, "nko": nko, "type": "vocabulaire"})
        
        print(f"🧠 Création de {len(texts)} embeddings...")
        
        # Créer embeddings par batch
        batch_size = 100
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            response = openai_client.embeddings.create(
                input=batch,
                model=EMBEDDING_MODEL
            )
            all_embeddings.extend([item.embedding for item in response.data])
            print(f"  ⚡ {min(i+batch_size, len(texts))}/{len(texts)}...")
        
        # Indexer dans Qdrant
        points = [
            PointStruct(id=i, vector=all_embeddings[i], payload=payloads[i])
            for i in range(len(texts))
        ]
        
        qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
        
        LOADING_STATUS.update({
            "vocabulary_qdrant_loaded": True,
            "mode": "qdrant"
        })
        
        print(f"✅ Qdrant indexé: {len(lexique)} mots")
        return True
        
    except Exception as e:
        print(f"❌ Erreur indexation Qdrant: {e}")
        return False

def search_vocabulary_qdrant(query: str, limit: int = 10) -> list:
    """Recherche via Qdrant (mode précis)"""
    try:
        if not qdrant_client or not openai_client:
            return []
        
        response = openai_client.embeddings.create(
            input=[query],
            model=EMBEDDING_MODEL
        )
        query_vector = response.data[0].embedding
        
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit
        )
        
        return [{
            "francais": r.payload["francais"],
            "nko": r.payload["nko"],
            "score": round(r.score, 3)
        } for r in results]
        
    except Exception as e:
        print(f"❌ Erreur recherche Qdrant: {e}")
        return []

def search_vocabulary_text(query: str, limit: int = 10) -> list:
    """Recherche simple dans le dictionnaire (mode fallback)"""
    try:
        query_lower = query.lower()
        results = []
        
        # Recherche exacte
        if query_lower in VOCABULAIRE_DICT:
            results.append({
                "francais": query_lower,
                "nko": VOCABULAIRE_DICT[query_lower],
                "score": 1.0
            })
        
        # Recherche par contenu
        for fr, nko in VOCABULAIRE_DICT.items():
            if query_lower in fr and fr not in [r["francais"] for r in results]:
                results.append({
                    "francais": fr,
                    "nko": nko,
                    "score": 0.8
                })
                if len(results) >= limit:
                    break
        
        return results
        
    except Exception as e:
        print(f"❌ Erreur recherche texte: {e}")
        return []

# ═══════════════════════════════════════════════════════════
# GESTION DES SESSIONS
# ═══════════════════════════════════════════════════════════

class SessionData(BaseModel):
    messages: List[Dict[str, str]] = []
    created_at: datetime
    last_activity: datetime

sessions: OrderedDict[str, SessionData] = OrderedDict()
MAX_SESSIONS = 1000
SESSION_TTL_HOURS = 24
MAX_MESSAGES_PER_SESSION = 20

def get_session(session_id: str) -> SessionData:
    now = datetime.now()
    
    if session_id in sessions:
        session = sessions[session_id]
        session.last_activity = now
        sessions.move_to_end(session_id)
        return session
    
    session = SessionData(messages=[], created_at=now, last_activity=now)
    sessions[session_id] = session
    
    while len(sessions) > MAX_SESSIONS:
        oldest_id = next(iter(sessions))
        del sessions[oldest_id]
    
    return session

def add_message(session_id: str, role: str, content: str):
    session = get_session(session_id)
    session.messages.append({"role": role, "content": content})
    
    if len(session.messages) > MAX_MESSAGES_PER_SESSION:
        session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]

# ═══════════════════════════════════════════════════════════
# MODÈLES
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000

class ChatResponse(BaseModel):
    response: str
    model_used: str
    tokens_used: Optional[int] = None
    session_id: str
    messages_in_session: int
    vocabulary_mode: str  # "text" ou "qdrant"

# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint principal avec mode hybride"""
    try:
        if not LOADING_STATUS.get("grammar_loaded"):
            raise HTTPException(status_code=503, detail="Grammaire en cours de chargement")
        
        if not OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
        
        session = get_session(request.session_id)
        
        # Construire le prompt
        full_prompt = NKOTRONIC_SYSTEM_PROMPT
        
        # MODE HYBRIDE : utiliser Qdrant si dispo, sinon texte
        mode = LOADING_STATUS.get("mode", "text")
        vocab_context = ""
        
        if mode == "qdrant":
            # Recherche précise via Qdrant
            mots = search_vocabulary_qdrant(request.message, limit=10)
            if mots:
                vocab_context = "📖 VOCABULAIRE PERTINENT (Qdrant) :\n" + "\n".join([
                    f"• {m['francais']} = **{m['nko']}** (score: {m['score']})"
                    for m in mots[:5]
                ])
        else:
            # Fallback: recherche texte OU tout le vocabulaire
            mots = search_vocabulary_text(request.message, limit=5)
            if mots:
                vocab_context = "📖 VOCABULAIRE PERTINENT (Texte) :\n" + "\n".join([
                    f"• {m['francais']} = **{m['nko']}**"
                    for m in mots
                ])
            elif VOCABULAIRE_TEXTE:
                # Si pas de match, donner tout le manifeste
                vocab_context = f"📖 MANIFESTE DE CONNAISSANCE N'KO :\n\n{VOCABULAIRE_TEXTE}"
        
        if vocab_context:
            full_prompt += f"\n\n{vocab_context}"
        
        # Messages
        messages = [{"role": "system", "content": full_prompt}]
        for msg in session.messages:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": request.message})
        
        # OpenAI
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        completion = client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        response_text = completion.choices[0].message.content
        tokens_used = completion.usage.total_tokens if completion.usage else None
        
        # Sauvegarder
        add_message(request.session_id, "user", request.message)
        add_message(request.session_id, "assistant", response_text)
        
        return ChatResponse(
            response=response_text,
            model_used=request.model,
            tokens_used=tokens_used,
            session_id=request.session_id,
            messages_in_session=len(session.messages),
            vocabulary_mode=mode
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Endpoint streaming"""
    
    async def generate():
        try:
            if not LOADING_STATUS.get("grammar_loaded"):
                yield f"data: {json.dumps({'error': 'Service indisponible'})}\n\n"
                return
            
            session = get_session(request.session_id)
            mode = LOADING_STATUS.get("mode", "text")
            
            # Prompt
            full_prompt = NKOTRONIC_SYSTEM_PROMPT
            
            if mode == "qdrant":
                mots = search_vocabulary_qdrant(request.message, limit=10)
                if mots:
                    vocab_context = "📖 VOCABULAIRE :\n" + "\n".join([
                        f"• {m['francais']} = **{m['nko']}**" for m in mots[:5]
                    ])
                    full_prompt += f"\n\n{vocab_context}"
            elif VOCABULAIRE_TEXTE:
                full_prompt += f"\n\n📖 MANIFESTE :\n{VOCABULAIRE_TEXTE}"
            
            messages = [{"role": "system", "content": full_prompt}]
            for msg in session.messages:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": request.message})
            
            # Stream
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            stream = client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            add_message(request.session_id, "user", request.message)
            add_message(request.session_id, "assistant", full_response)
            
            yield f"data: {json.dumps({'done': True, 'mode': mode})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/")
async def root():
    return {
        "name": "Nkotronic API",
        "version": "4.4.0-HYBRID",
        "status": "running",
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False),
        "vocabulary_text_loaded": LOADING_STATUS.get("vocabulary_text_loaded", False),
        "vocabulary_qdrant_loaded": LOADING_STATUS.get("vocabulary_qdrant_loaded", False),
        "vocabulary_count": LOADING_STATUS.get("vocabulary_count", 0),
        "mode": LOADING_STATUS.get("mode", "text"),
        "ram_friendly": True
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "mode": LOADING_STATUS.get("mode", "text")
    }

@app.get("/status")
async def status():
    return LOADING_STATUS

@app.post("/reload")
async def reload():
    """Recharge le vocabulaire"""
    await load_vocabulaire_texte()
    return {"status": "reloaded", "count": LOADING_STATUS.get("vocabulary_count", 0)}

# ═══════════════════════════════════════════════════════════
# DÉMARRAGE
# ═══════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    print("=" * 70)
    print("🚀 NKOTRONIC API v4.4.0 - HYBRID MODE")
    print("=" * 70)
    print("💡 Démarrage rapide + Qdrant en arrière-plan")
    print("=" * 70)
    
    # PHASE 1 : Chargement rapide (2-3 sec)
    print("\n📖 PHASE 1 : Chargement rapide...")
    
    # Grammaire
    grammar_ok = load_system_prompt()
    
    # Vocabulaire texte
    vocab_ok = await load_vocabulaire_texte()
    
    print("\n" + "=" * 70)
    print("✅ API PRÊTE EN MODE TEXTE !")
    print(f"📊 Vocabulaire: {LOADING_STATUS.get('vocabulary_count', 0)} mots")
    print("=" * 70 + "\n")
    
    # PHASE 2 : Qdrant en arrière-plan (si disponible)
    if QDRANT_URL and QDRANT_API_KEY and QDRANT_AVAILABLE:
        import asyncio
        asyncio.create_task(init_qdrant_background())
    else:
        print("ℹ️  Qdrant non configuré - mode texte permanent")
    
    LOADING_STATUS["status"] = "ready"
    LOADING_STATUS["progress"] = 100

async def init_qdrant_background():
    """Initialise Qdrant en arrière-plan"""
    import asyncio
    
    await asyncio.sleep(3)  # Attendre que le port soit ouvert
    
    print("\n" + "=" * 70)
    print("📊 PHASE 2 : Indexation Qdrant (arrière-plan)...")
    print("=" * 70)
    
    if init_qdrant():
        if sync_lexique_to_qdrant():
            print("\n✅ QDRANT PRÊT - Bascule en mode précis !")
            print("=" * 70 + "\n")
        else:
            print("\n⚠️ Indexation Qdrant échouée - reste en mode texte")
    else:
        print("\n⚠️ Qdrant non disponible - reste en mode texte")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)