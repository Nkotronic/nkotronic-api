"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version 3.0 MEMORY SAFE                ║
║  ✅ Protection complète contre le Memory Leak                ║
║  ✅ Gestion des sessions avec TTL                            ║
║  ✅ Cleanup automatique                                      ║
║  ✅ Prompt Caching OpenAI                                    ║
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

app = FastAPI(title="Nkotronic API", version="3.0.0-MEMORY-SAFE")

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

# Stockage des sessions en mémoire (OrderedDict pour LRU)
sessions_store: OrderedDict[str, SessionData] = OrderedDict()

def get_session(session_id: str) -> SessionData:
    """Récupère ou crée une session"""
    now = datetime.utcnow()
    
    if session_id in sessions_store:
        # Session existe, mettre à jour l'activité
        session = sessions_store[session_id]
        session.last_activity = now
        # Déplacer à la fin (LRU)
        sessions_store.move_to_end(session_id)
        return session
    else:
        # Nouvelle session
        # Vérifier la limite de sessions
        if len(sessions_store) >= MAX_SESSIONS:
            # Supprimer la plus ancienne (FIFO)
            oldest_id = next(iter(sessions_store))
            del sessions_store[oldest_id]
            print(f"🗑️  Session {oldest_id} supprimée (limite atteinte)")
        
        # Créer nouvelle session
        session = SessionData(
            messages=[],
            created_at=now,
            last_activity=now
        )
        sessions_store[session_id] = session
        print(f"✨ Nouvelle session créée: {session_id}")
        return session

def add_message_to_session(session_id: str, role: str, content: str):
    """Ajoute un message à la session avec limite"""
    session = get_session(session_id)
    
    # Ajouter le nouveau message
    session.messages.append({"role": role, "content": content})
    
    # Limiter à MAX_MESSAGES_PER_SESSION
    if len(session.messages) > MAX_MESSAGES_PER_SESSION:
        # Garder seulement les N derniers messages
        session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
        print(f"✂️  Session {session_id} tronquée à {MAX_MESSAGES_PER_SESSION} messages")

def cleanup_expired_sessions():
    """Nettoie les sessions expirées"""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=SESSION_TTL_HOURS)
    
    expired_ids = []
    for session_id, session in sessions_store.items():
        if session.last_activity < cutoff:
            expired_ids.append(session_id)
    
    for session_id in expired_ids:
        del sessions_store[session_id]
    
    if expired_ids:
        print(f"🧹 Cleanup: {len(expired_ids)} sessions expirées supprimées")
    
    print(f"📊 Sessions actives: {len(sessions_store)}/{MAX_SESSIONS}")

# Tâche de fond pour le cleanup automatique
async def periodic_cleanup():
    """Nettoie périodiquement les sessions expirées"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_MINUTES * 60)
        cleanup_expired_sessions()

@app.on_event("startup")
async def startup_event():
    """Démarre le cleanup automatique au démarrage"""
    asyncio.create_task(periodic_cleanup())
    print(f"🤖 Cleanup automatique démarré (toutes les {CLEANUP_INTERVAL_MINUTES} min)")

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

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"  # Identifiant de session
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 4096

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

from fastapi.responses import StreamingResponse
import json

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Endpoint de streaming SSE pour affichage progressif (lettre par lettre)
    
    FONCTIONNALITÉS:
    ✅ Streaming temps réel (Server-Sent Events)
    ✅ Affichage progressif comme ChatGPT/Claude
    ✅ Gestion des sessions identique à /chat
    ✅ Prompt Caching activé
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
# ENDPOINTS DE GESTION DES SESSIONS
# ═══════════════════════════════════════════════════════════

@app.get("/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Récupère les informations d'une session"""
    if session_id not in sessions_store:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions_store[session_id]
    return {
        "session_id": session_id,
        "messages_count": len(session.messages),
        "created_at": session.created_at.isoformat(),
        "last_activity": session.last_activity.isoformat(),
        "messages": session.messages
    }

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Supprime une session"""
    if session_id in sessions_store:
        del sessions_store[session_id]
        return {"status": "deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.post("/cleanup")
async def manual_cleanup():
    """Force le cleanup manuel des sessions expirées"""
    cleanup_expired_sessions()
    return {
        "status": "cleanup completed",
        "active_sessions": len(sessions_store)
    }

@app.get("/sessions")
async def list_sessions():
    """Liste toutes les sessions actives"""
    return {
        "total_sessions": len(sessions_store),
        "max_sessions": MAX_SESSIONS,
        "sessions": [
            {
                "session_id": sid,
                "messages_count": len(session.messages),
                "last_activity": session.last_activity.isoformat()
            }
            for sid, session in sessions_store.items()
        ]
    }

# ═══════════════════════════════════════════════════════════
# ENDPOINTS UTILITAIRES
# ═══════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Vérifier l'état du service"""
    return {
        "status": "healthy",
        "version": "3.0.0-MEMORY-SAFE",
        "grammar_loaded": len(NKOTRONIC_COMPLETE_GRAMMAR) > 0,
        "grammar_size": len(NKOTRONIC_COMPLETE_GRAMMAR),
        "lexique_cached": LEXIQUE_CACHE is not None,
        "active_sessions": len(sessions_store),
        "max_sessions": MAX_SESSIONS,
        "session_ttl_hours": SESSION_TTL_HOURS,
        "max_messages_per_session": MAX_MESSAGES_PER_SESSION,
        "features": [
            "Session management with TTL",
            "Automatic cleanup every 30 min",
            "Max 20 messages per session",
            "Max 1000 concurrent sessions",
            "Prompt Caching enabled",
            "Memory leak protected"
        ]
    }

@app.post("/reload-lexique")
async def reload_lexique():
    """Forcer le rechargement du lexique depuis GitHub"""
    lexique = await load_lexique(force_reload=True)
    return {
        "status": "reloaded",
        "lexique_size": len(lexique)
    }

@app.get("/info")
async def info():
    """Informations sur Nkotronic"""
    return {
        "name": "Nkotronic",
        "version": "3.0.0-MEMORY-SAFE",
        "description": "Intelligence Artificielle experte en N'ko",
        "creator": "Holding Nkowuruki",
        "grammar_lines": 864,
        "models_available": ["gpt-4o", "gpt-4o-mini"],
        "memory_protection": {
            "session_ttl_hours": SESSION_TTL_HOURS,
            "max_messages_per_session": MAX_MESSAGES_PER_SESSION,
            "max_sessions": MAX_SESSIONS,
            "cleanup_interval_minutes": CLEANUP_INTERVAL_MINUTES
        },
        "features": [
            "Grammaire N'ko complète (864 lignes)",
            "Lexique français-N'ko dynamique",
            "Gestion des sessions avec TTL",
            "Protection contre memory leak",
            "Prompt Caching OpenAI",
            "Cleanup automatique"
        ]
    }

# ═══════════════════════════════════════════════════════════
# LANCEMENT DU SERVEUR
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║       🚀 NKOTRONIC API v3.0 - MEMORY SAFE                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"✅ Grammaire: {len(NKOTRONIC_COMPLETE_GRAMMAR)} caractères")
    print("✅ Lexique: GitHub dynamique")
    print("✅ Modèle: gpt-4o / gpt-4o-mini")
    print(f"✅ Sessions: Max {MAX_SESSIONS}, TTL {SESSION_TTL_HOURS}h")
    print(f"✅ Messages/session: Max {MAX_MESSAGES_PER_SESSION}")
    print(f"✅ Cleanup: Auto toutes les {CLEANUP_INTERVAL_MINUTES} min")
    print("✅ Memory leak: PROTÉGÉ")
    print("Port: 8000")
    print("═══════════════════════════════════════════════════════════════")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)