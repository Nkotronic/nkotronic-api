"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version 3.0 MEMORY SAFE + GITHUB       ║
║  ✅ Protection complète contre le Memory Leak                ║
║  ✅ Gestion des sessions avec TTL                            ║
║  ✅ Cleanup automatique                                      ║
║  ✅ Prompt Caching OpenAI                                    ║
║  ✅ Chargement depuis GitHub                                 ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import openai
import os
import httpx
import json
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import asyncio
from collections import OrderedDict

app = FastAPI(title="Nkotronic API", version="3.0.0-MEMORY-SAFE-GITHUB")

# CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# GESTION DE LA MÉMOIRE DES SESSIONS
# ═══════════════════════════════════════════════════════════

class SessionData(BaseModel):
    """Données d'une session utilisateur"""
    messages: List[Dict[str, str]] = []
    created_at: datetime
    last_activity: datetime

# Configuration de la mémoire
MAX_SESSIONS = 1000  # Limite nombre de sessions en RAM
SESSION_TTL_HOURS = 24  # Durée de vie d'une session (24h)
MAX_MESSAGES_PER_SESSION = 20  # Garder seulement les 20 derniers messages
CLEANUP_INTERVAL_MINUTES = 30  # Nettoyer toutes les 30 minutes

# Stockage des sessions (OrderedDict pour FIFO)
sessions: OrderedDict[str, SessionData] = OrderedDict()

def get_session(session_id: str) -> SessionData:
    """Récupère ou crée une session"""
    now = datetime.now()
    
    if session_id in sessions:
        session = sessions[session_id]
        session.last_activity = now
        # Déplacer en fin (LRU)
        sessions.move_to_end(session_id)
        return session
    
    # Créer nouvelle session
    session = SessionData(
        messages=[],
        created_at=now,
        last_activity=now
    )
    
    sessions[session_id] = session
    
    # Si trop de sessions, supprimer les plus anciennes
    while len(sessions) > MAX_SESSIONS:
        oldest_id = next(iter(sessions))
        del sessions[oldest_id]
        print(f"🗑️  Session {oldest_id} supprimée (limite atteinte)")
    
    return session

def add_message_to_session(session_id: str, role: str, content: str):
    """Ajoute un message à la session avec limite"""
    session = get_session(session_id)
    session.messages.append({"role": role, "content": content})
    
    # Garder seulement les N derniers messages
    if len(session.messages) > MAX_MESSAGES_PER_SESSION:
        session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
        print(f"✂️  Session {session_id}: Limité à {MAX_MESSAGES_PER_SESSION} messages")

def cleanup_old_sessions():
    """Nettoie les sessions expirées"""
    now = datetime.now()
    expired_threshold = now - timedelta(hours=SESSION_TTL_HOURS)
    
    expired_sessions = [
        sid for sid, session in sessions.items()
        if session.last_activity < expired_threshold
    ]
    
    for sid in expired_sessions:
        del sessions[sid]
    
    if expired_sessions:
        print(f"🧹 Nettoyage: {len(expired_sessions)} sessions expirées supprimées")

# Nettoyage automatique en arrière-plan
async def auto_cleanup():
    """Tâche de nettoyage périodique"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_MINUTES * 60)
        cleanup_old_sessions()

@app.on_event("startup")
async def startup_event():
    """Démarre le nettoyage automatique au démarrage"""
    asyncio.create_task(auto_cleanup())
    print(f"🚀 Nkotronic API v3.0 démarrée")
    print(f"📊 Config: Max {MAX_SESSIONS} sessions, TTL {SESSION_TTL_HOURS}h, Cleanup {CLEANUP_INTERVAL_MINUTES}min")

# ═══════════════════════════════════════════════════════════
# CHARGEMENT DU CONTEXTE COMPLET DEPUIS GITHUB
# ═══════════════════════════════════════════════════════════

GITHUB_KNOWLEDGE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
KNOWLEDGE_CACHE = None

async def load_full_knowledge(force_reload: bool = False):
    """Charge le contexte complet (grammaire + lexique) depuis GitHub avec cache"""
    global KNOWLEDGE_CACHE
    
    if KNOWLEDGE_CACHE is not None and not force_reload:
        return KNOWLEDGE_CACHE
    
    try:
        async with httpx.AsyncClient() as client:
            print("📥 Chargement du contexte complet depuis GitHub...")
            response = await client.get(GITHUB_KNOWLEDGE_URL, timeout=30.0)
            response.raise_for_status()
            KNOWLEDGE_CACHE = response.text
            print(f"✅ Contexte complet chargé: {len(KNOWLEDGE_CACHE)} caractères")
            return KNOWLEDGE_CACHE
    except Exception as e:
        print(f"❌ Erreur chargement contexte: {e}")
        # Fallback minimal si GitHub indisponible
        return """Tu es Nkotronic, l'assistant IA expert en N'ko. 
Tu es bienveillant, précis et pédagogue. Tu maîtrises parfaitement le N'ko.
(Contexte complet temporairement indisponible)"""

# ═══════════════════════════════════════════════════════════
# MODÈLES PYDANTIC
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2000

class ChatResponse(BaseModel):
    response: str
    model_used: str
    tokens_used: Optional[int] = None
    session_id: str
    messages_in_session: int

# ═══════════════════════════════════════════════════════════
# CONSTRUCTION DU CONTEXTE COMPLET
# ═══════════════════════════════════════════════════════════

async def build_full_context():
    """Charge et retourne le contexte complet depuis GitHub"""
    return await load_full_knowledge()

# ═══════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL DE CHAT AVEC GESTION MÉMOIRE
# ═══════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint principal de conversation avec Nkotronic
    
    NOUVELLES FONCTIONNALITÉS v3.0:
    ✅ Gestion des sessions avec TTL (24h)
    ✅ Limite de 20 messages par session
    ✅ Cleanup automatique toutes les 30 min
    ✅ Protection contre memory leak
    ✅ Prompt Caching OpenAI (50-90% réduction coûts)
    ✅ Chargement depuis GitHub
    """
    try:
        # Vérifier que la clé API OpenAI est configurée
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="OPENAI_API_KEY not configured"
            )
        
        # Récupérer la session (ou en créer une nouvelle)
        session = get_session(request.session_id)
        
        # Construire le contexte complet
        full_context = await build_full_context()
        
        # Message système AVEC prompt caching
        system_message = {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": full_context,
                    "cache_control": {"type": "ephemeral"}  # ⚡ Cache activé
                }
            ]
        }
        
        # Préparer les messages pour OpenAI
        messages = [system_message]
        
        # Ajouter l'historique de la session (limité à 20 messages)
        for msg in session.messages:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Ajouter le message actuel
        messages.append({"role": "user", "content": request.message})
        
        # Vérifier que le modèle supporte le prompt caching
        supported_models = ["gpt-4o", "gpt-4o-mini"]
        if request.model not in supported_models:
            print(f"⚠️  Modèle {request.model} ne supporte pas le caching, utilisation de gpt-4o")
            request.model = "gpt-4o"
        
        # Appel à OpenAI avec cache activé
        client = openai.OpenAI(api_key=api_key)
        
        completion = client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            store=True  # ⚡ Active le cache
        )
        
        # Log détaillé des tokens
        if completion.usage:
            total = completion.usage.total_tokens
            prompt = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            
            print(f"📊 Session {request.session_id} - Tokens: {total} (Prompt: {prompt}, Completion: {completion_tokens})")
            
            # Vérifier si le cache a été utilisé
            if hasattr(completion.usage, 'prompt_tokens_details'):
                details = completion.usage.prompt_tokens_details
                if hasattr(details, 'cached_tokens') and details.cached_tokens > 0:
                    cache_percent = (details.cached_tokens / prompt) * 100
                    print(f"💾 CACHE HIT ! {details.cached_tokens} tokens ({cache_percent:.1f}%)")
                else:
                    print(f"❄️  Cache miss")
        
        response_text = completion.choices[0].message.content
        tokens_used = completion.usage.total_tokens if completion.usage else None
        
        # Sauvegarder les messages dans la session
        add_message_to_session(request.session_id, "user", request.message)
        add_message_to_session(request.session_id, "assistant", response_text)
        
        return ChatResponse(
            response=response_text,
            model_used=request.model,
            tokens_used=tokens_used,
            session_id=request.session_id,
            messages_in_session=len(session.messages)
        )
        
    except openai.APIError as e:
        print(f"❌ OpenAI API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OpenAI API Error: {str(e)}")
    except Exception as e:
        print(f"❌ Erreur inattendue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ═══════════════════════════════════════════════════════════
# ENDPOINT STREAMING SSE - Affichage progressif temps réel
# ═══════════════════════════════════════════════════════════

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Endpoint de streaming SSE pour affichage progressif (lettre par lettre)
    
    FONCTIONNALITÉS:
    ✅ Streaming temps réel (Server-Sent Events)
    ✅ Affichage progressif comme ChatGPT/Claude
    ✅ Gestion des sessions identique à /chat
    ✅ Prompt Caching activé
    ✅ Chargement depuis GitHub
    """
    
    async def generate():
        try:
            # Vérifier la clé API
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'OPENAI_API_KEY not configured'})}\n\n"
                return
            
            # Récupérer la session
            session = get_session(request.session_id)
            
            # Construire le contexte complet
            full_context = await build_full_context()
            
            # Message système avec cache
            system_message = {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": full_context,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            }
            
            # Préparer les messages
            messages = [system_message]
            
            # Historique de session
            for msg in session.messages:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Message actuel
            messages.append({"role": "user", "content": request.message})
            
            # Vérifier le modèle
            supported_models = ["gpt-4o", "gpt-4o-mini"]
            if request.model not in supported_models:
                request.model = "gpt-4o"
            
            # OpenAI Streaming
            client = openai.OpenAI(api_key=api_key)
            
            stream = client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                store=True,
                stream=True  # ✅ STREAMING ACTIVÉ
            )
            
            full_response = ""
            
            # Streamer les chunks
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    
                    # Envoyer chunk au frontend
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            # Sauvegarder dans la session
            add_message_to_session(request.session_id, "user", request.message)
            add_message_to_session(request.session_id, "assistant", full_response)
            
            # Signal de fin
            yield f"data: {json.dumps({'done': True, 'session_id': request.session_id, 'messages_in_session': len(session.messages)})}\n\n"
            
            print(f"✅ Session {request.session_id} - Streaming terminé ({len(full_response)} chars)")
            
        except Exception as e:
            print(f"❌ Erreur streaming: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# ═══════════════════════════════════════════════════════════
# ENDPOINTS UTILITAIRES
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Page d'accueil avec informations sur l'API"""
    return {
        "name": "Nkotronic API",
        "version": "3.0.0-MEMORY-SAFE-GITHUB",
        "status": "running",
        "features": [
            "Session management with TTL",
            "Auto cleanup every 30min",
            "20 messages per session limit",
            "OpenAI Prompt Caching",
            "SSE Streaming support",
            "GitHub knowledge loading"
        ],
        "endpoints": {
            "POST /chat": "Standard chat endpoint",
            "POST /chat/stream": "Streaming chat endpoint (SSE)",
            "GET /health": "Health check",
            "GET /stats": "Statistics",
            "POST /warmup": "Warmup endpoint"
        }
    }

@app.get("/health")
async def health():
    """Endpoint de santé pour warmup Render"""
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "knowledge_loaded": KNOWLEDGE_CACHE is not None,
        "knowledge_size": len(KNOWLEDGE_CACHE) if KNOWLEDGE_CACHE else 0
    }

@app.get("/stats")
async def stats():
    """Statistiques des sessions"""
    now = datetime.now()
    recent_threshold = now - timedelta(minutes=5)
    
    recent_sessions = sum(
        1 for session in sessions.values()
        if session.last_activity > recent_threshold
    )
    
    return {
        "total_sessions": len(sessions),
        "recent_sessions_5min": recent_sessions,
        "max_sessions": MAX_SESSIONS,
        "session_ttl_hours": SESSION_TTL_HOURS,
        "max_messages_per_session": MAX_MESSAGES_PER_SESSION,
        "knowledge_loaded": KNOWLEDGE_CACHE is not None,
        "knowledge_size_chars": len(KNOWLEDGE_CACHE) if KNOWLEDGE_CACHE else 0
    }

@app.post("/warmup")
async def warmup():
    """Endpoint de warmup pour pré-charger le contexte"""
    try:
        context = await build_full_context()
        return {
            "status": "warmed_up",
            "context_size": len(context),
            "knowledge_loaded": True
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "knowledge_loaded": False
        }

# Démarrage
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)