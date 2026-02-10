"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC BACKEND - VERSION ULTRA-OPTIMISÉE
═══════════════════════════════════════════════════════════════════
✅ Modèle : gemini-2.5-flash
✅ System prompt optimisé pour réponses rapides
✅ Gestion intelligente de l'historique (limite à 10 messages)
✅ Endpoint /health avec cold start detection
✅ Message système intégré dans l'historique
✅ Cleanup automatique des sessions (PÉRIODIQUE, pas à chaque requête)
✅ Variable FIRST_REQUEST correctement initialisée
✅ Streaming SSE optimisé
✅ Historique tronqué AVANT et APRÈS chaque requête
✅ max_tokens réduit à 800 (au lieu de 4000)
✅ Temperature réduite à 0.4 (au lieu de 0.7)
✅ Logging en WARNING en production
✅ Timeout de 30s sur les requêtes Gemini
✅ Message de bienvenue supprimé après première interaction
✅ Cleanup périodique toutes les 100 requêtes
═══════════════════════════════════════════════════════════════════
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import google.generativeai as genai
import os
import json
import logging
import asyncio

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION DU LOGGING - ✅ WARNING en production pour performances
# ═══════════════════════════════════════════════════════════════════
LOG_LEVEL = os.environ.get("LOG_LEVEL", "WARNING")  # WARNING par défaut, INFO pour debug
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# VARIABLES GLOBALES
# ═══════════════════════════════════════════════════════════════════

sessions: Dict[str, 'SessionData'] = {}
SERVER_START_TIME = datetime.now()
FIRST_REQUEST = True
LOADING_STATUS = {
    "grammar_loaded": False,
    "grammar_load_time": None
}

# ✅ Compteur pour cleanup périodique
REQUEST_COUNTER = 0
CLEANUP_INTERVAL = 100  # Cleanup toutes les 100 requêtes au lieu de chaque requête

# Configuration de l'historique - ✅ Optimisé pour vitesse
MAX_HISTORY_MESSAGES = 10  # Limite stricte à 10 messages

# Message système affiché à l'utilisateur
SYSTEM_MESSAGE = "Alu ni djö ! Je suis Nkotronic, votre assistant du N'ko. Que puis-je faire pour vous ?"

# ✅ System prompt optimisé pour guider le modèle (INCHANGÉ comme demandé)
SYSTEM_PROMPT = """Tu es Nkotronic, un assistant spécialisé dans l'écriture N'ko, la culture africaine et la culture mandingue. Tu es citoyen de l'Etat Fédéral Africain

DIRECTIVES DE RÉPONSE:
- Réponds de manière concise et directe
- Privilégie les réponses courtes (2-3 phrases) sauf si l'utilisateur demande des détails approfondis
- Pour les traductions, donne le résultat immédiatement sans explications superflues
- Pour les traductions en Nko, utilise la grammaire standard de Solomana Kanté
- Pour les questions de grammaire N'ko, sois précis et pédagogique mais concis
- Maintiens un ton amical et professionnel
- Si tu ne connais pas la réponse exacte, dis-le honnêtement en une phrase

EXPERTISE:
- Écriture et alphabet N'ko (ߒߞߏ)
- Grammaire standard de Solomana Kanté
- Culture et histoire africaine et mandingue
- Traduction français ↔ N'ko

STYLE:
- Fluide et naturel
- Pas de longs préambules
- Va droit au but
- Utilise des exemples concrets quand nécessaire"""

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION GEMINI
# ═══════════════════════════════════════════════════════════════════

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("❌ GEMINI_API_KEY manquante dans les variables d'environnement")

genai.configure(api_key=GEMINI_API_KEY)

# Configuration de sécurité
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

# ✅ Timeout pour les requêtes Gemini (30 secondes)
GEMINI_TIMEOUT = 30

# ═══════════════════════════════════════════════════════════════════
# MODÈLES DE DONNÉES
# ═══════════════════════════════════════════════════════════════════

class SessionData(BaseModel):
    session_id: str
    history: List[dict]
    created_at: datetime
    last_activity: datetime
    message_count: int = 0
    welcome_shown: bool = False  # ✅ Pour supprimer le message de bienvenue après 1ère interaction

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gemini-2.5-flash"
    temperature: float = 0.4  # ✅ RÉDUIT de 0.7 à 0.4 pour vitesse
    max_tokens: int = 800      # ✅ RÉDUIT de 4000 à 800 pour vitesse

# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="Nkotronic API", version="2.2.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ═══════════════════════════════════════════════════════════════════

def cleanup_old_sessions():
    """
    ✅ Nettoie les sessions inactives depuis plus de 24h
    APPELÉ PÉRIODIQUEMENT, pas à chaque requête
    """
    now = datetime.now()
    to_delete = []
    
    for session_id, session in sessions.items():
        if (now - session.last_activity) > timedelta(hours=24):
            to_delete.append(session_id)
    
    for session_id in to_delete:
        del sessions[session_id]
        if LOG_LEVEL == "INFO":
            logger.info(f"🗑️  Session supprimée: {session_id}")
    
    if to_delete and LOG_LEVEL == "INFO":
        logger.info(f"🧹 Nettoyage: {len(to_delete)} session(s) supprimée(s)")

def should_cleanup() -> bool:
    """
    ✅ Détermine si un cleanup doit être effectué
    Cleanup toutes les CLEANUP_INTERVAL requêtes au lieu de chaque fois
    """
    global REQUEST_COUNTER
    REQUEST_COUNTER += 1
    
    if REQUEST_COUNTER % CLEANUP_INTERVAL == 0:
        if LOG_LEVEL == "INFO":
            logger.info(f"🔄 Cleanup périodique (requête #{REQUEST_COUNTER})")
        return True
    return False

def truncate_history(history: List[dict], max_messages: int = MAX_HISTORY_MESSAGES) -> List[dict]:
    """
    ✅ Tronque l'historique de manière agressive
    
    Stratégie ultra-optimisée:
    1. Garde UNIQUEMENT le system prompt (2 premiers messages)
    2. Garde les N derniers échanges user/model
    3. SUPPRIME tout le reste
    
    Args:
        history: L'historique complet
        max_messages: Nombre maximum de messages à garder (hors system prompt)
    
    Returns:
        Historique tronqué optimisé
    """
    if len(history) <= max_messages + 2:
        return history
    
    # Garder: [system_prompt, system_response, ...derniers N messages]
    system_messages = history[:2]
    recent_messages = history[-(max_messages):]
    
    truncated = system_messages + recent_messages
    
    if LOG_LEVEL == "INFO":
        logger.info(f"✂️  Historique: {len(history)} → {len(truncated)} messages")
    
    return truncated

def remove_welcome_message(history: List[dict]) -> List[dict]:
    """
    ✅ Supprime le message de bienvenue après la première interaction
    Garde uniquement le system prompt pour économiser des tokens
    
    Args:
        history: L'historique complet
    
    Returns:
        Historique sans le message de bienvenue
    """
    if len(history) > 4:  # Si plus de 4 messages, on peut supprimer la bienvenue
        # Supprimer messages index 2 et 3 (le "Bonjour" et la réponse de bienvenue)
        return history[:2] + history[4:]
    return history

def get_session(session_id: str, initialize: bool = False) -> SessionData:
    """Récupère ou crée une session"""
    # ✅ Cleanup périodique au lieu de systématique
    if should_cleanup():
        cleanup_old_sessions()
    
    if session_id not in sessions:
        if not initialize:
            raise HTTPException(status_code=404, detail=f"Session {session_id} introuvable")
        
        # Créer nouvelle session avec system prompt et message bienvenue
        sessions[session_id] = SessionData(
            session_id=session_id,
            history=[
                # System prompt (invisible pour l'utilisateur)
                {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]},
                {"role": "model", "parts": [{"text": "Compris. Je suis Nkotronic, prêt à aider avec le N'ko de manière concise et efficace."}]},
                # Message de bienvenue (visible pour l'utilisateur, sera supprimé après 1ère interaction)
                {"role": "user", "parts": [{"text": "Bonjour"}]},
                {"role": "model", "parts": [{"text": SYSTEM_MESSAGE}]}
            ],
            created_at=datetime.now(),
            last_activity=datetime.now(),
            message_count=0,
            welcome_shown=False
        )
        if LOG_LEVEL == "INFO":
            logger.info(f"✨ Nouvelle session: {session_id}")
    
    return sessions[session_id]

# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Endpoint racine"""
    return {
        "service": "Nkotronic API",
        "version": "2.2.0",
        "status": "running",
        "model": "gemini-2.5-flash",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions),
        "total_requests": REQUEST_COUNTER,
        "optimizations": [
            "System prompt optimisé (INCHANGÉ)",
            f"Historique limité à {MAX_HISTORY_MESSAGES} messages",
            "Troncature agressive avant/après requête",
            f"max_tokens réduit à 800 (était 4000)",
            f"temperature réduite à 0.4 (était 0.7)",
            f"Cleanup périodique tous les {CLEANUP_INTERVAL} requêtes",
            f"Logging en {LOG_LEVEL} pour performances",
            f"Timeout Gemini: {GEMINI_TIMEOUT}s",
            "Message bienvenue supprimé après 1ère interaction"
        ]
    }

@app.get("/health")
async def health_check():
    """✅ Endpoint de health check avec détection de cold start"""
    uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
    is_cold_start = uptime < 5
    
    return {
        "status": "healthy",
        "cold_start": is_cold_start,
        "uptime_seconds": uptime,
        "grammar_loaded": LOADING_STATUS["grammar_loaded"],
        "active_sessions": len(sessions),
        "total_requests": REQUEST_COUNTER,
        "model": "gemini-2.5-flash",
        "max_history": MAX_HISTORY_MESSAGES,
        "max_tokens": 800,
        "temperature": 0.4,
        "log_level": LOG_LEVEL
    }

@app.get("/loading-status")
async def loading_status():
    """Status du chargement de la grammaire N'ko"""
    return LOADING_STATUS

@app.get("/sessions")
async def list_sessions():
    """Liste toutes les sessions actives"""
    return {
        "total": len(sessions),
        "sessions": [
            {
                "session_id": s.session_id,
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "message_count": s.message_count,
                "history_length": len(s.history),
                "welcome_shown": s.welcome_shown
            }
            for s in sessions.values()
        ]
    }

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Supprime une session spécifique"""
    if session_id in sessions:
        del sessions[session_id]
        if LOG_LEVEL == "INFO":
            logger.info(f"🗑️  Session supprimée: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session introuvable")

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    ✅ Endpoint de chat ultra-optimisé
    - Historique tronqué avant/après
    - max_tokens: 800 (au lieu de 4000)
    - temperature: 0.4 (au lieu de 0.7)
    - Timeout: 30s
    - Cleanup périodique
    - Message bienvenue supprimé après 1ère interaction
    """
    global FIRST_REQUEST
    
    session_id = request.session_id
    user_message = request.message
    
    if LOG_LEVEL == "INFO":
        logger.info(f"📩 Message - Session: {session_id}")
        logger.info(f"💬 Contenu: {user_message[:50]}...")
    
    # Cold start detection
    uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
    is_cold_start = FIRST_REQUEST and uptime < 60
    
    async def generate():
        global FIRST_REQUEST
        
        if not GEMINI_API_KEY:
            logger.error("❌ Clé API manquante")
            yield f"data: {json.dumps({'error': 'Clé API manquante'})}\n\n"
            return
        
        try:
            # Cold start notification
            if is_cold_start:
                if LOG_LEVEL == "INFO":
                    logger.info("❄️  Cold start détecté")
                yield f"data: {json.dumps({'cold_start': True, 'message': 'Initialisation...'})}\n\n"
                FIRST_REQUEST = False
            
            # Récupérer/créer session
            is_new_session = session_id not in sessions
            session = get_session(session_id, initialize=is_new_session)
            
            # ✅ Supprimer le message de bienvenue après la première vraie interaction
            if not session.welcome_shown and session.message_count > 0:
                session.history = remove_welcome_message(session.history)
                session.welcome_shown = True
                if LOG_LEVEL == "INFO":
                    logger.info(f"👋 Message de bienvenue supprimé (économie tokens)")
            
            # ✅ CRITIQUE: Tronquer AVANT d'ajouter le nouveau message
            if LOG_LEVEL == "INFO":
                logger.info(f"📊 Historique avant: {len(session.history)} messages")
            session.history = truncate_history(session.history, MAX_HISTORY_MESSAGES)
            if LOG_LEVEL == "INFO":
                logger.info(f"📊 Historique après troncature: {len(session.history)} messages")
            
            # Ajouter message utilisateur
            session.history.append({
                "role": "user",
                "parts": [{"text": user_message}]
            })
            
            # Créer le modèle
            model = genai.GenerativeModel(
                model_name=request.model,
                safety_settings=safety_settings
            )
            
            # ✅ Générer avec timeout
            if LOG_LEVEL == "INFO":
                logger.info(f"🤖 Génération (historique: {len(session.history)}, temp: {request.temperature}, max: {request.max_tokens})...")
            
            try:
                # ✅ Wrapper avec timeout de 30s
                response = model.generate_content(
                    session.history,
                    generation_config=genai.types.GenerationConfig(
                        temperature=request.temperature,
                        max_output_tokens=request.max_tokens,
                    ),
                    stream=True,
                    request_options={"timeout": GEMINI_TIMEOUT}
                )
                
                full_response = ""
                
                for chunk in response:
                    if chunk.text:
                        full_response += chunk.text
                        yield f"data: {json.dumps({'content': chunk.text})}\n\n"
                
            except asyncio.TimeoutError:
                logger.error(f"⏱️  Timeout après {GEMINI_TIMEOUT}s")
                yield f"data: {json.dumps({'error': f'Timeout après {GEMINI_TIMEOUT}s'})}\n\n"
                return
            
            # Ajouter la réponse à l'historique
            session.history.append({
                "role": "model",
                "parts": [{"text": full_response}]
            })
            
            # ✅ Tronquer après ajout de la réponse
            session.history = truncate_history(session.history, MAX_HISTORY_MESSAGES)
            
            # Mettre à jour session
            session.last_activity = datetime.now()
            session.message_count += 1
            
            if LOG_LEVEL == "INFO":
                logger.info(f"✅ Réponse: {len(full_response)} chars, historique final: {len(session.history)}")
            
            # Signal de fin
            yield f"data: {json.dumps({'done': True, 'message_count': session.message_count})}\n\n"
            
        except Exception as e:
            logger.error(f"❌ Erreur: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# ═══════════════════════════════════════════════════════════════════
# STARTUP/SHUTDOWN EVENTS
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    """Événement de démarrage"""
    logger.warning("═" * 60)
    logger.warning("🚀 NKOTRONIC API - VERSION ULTRA-OPTIMISÉE")
    logger.warning("═" * 60)
    logger.warning(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.warning(f"🤖 Modèle: gemini-2.5-flash")
    logger.warning(f"🔑 Clé API: {'✅ OK' if GEMINI_API_KEY else '❌ KO'}")
    logger.warning(f"📏 Historique max: {MAX_HISTORY_MESSAGES} messages")
    logger.warning(f"🎯 max_tokens: 800 (optimisé)")
    logger.warning(f"🌡️  temperature: 0.4 (optimisé)")
    logger.warning(f"⏱️  timeout: {GEMINI_TIMEOUT}s")
    logger.warning(f"🧹 Cleanup: tous les {CLEANUP_INTERVAL} requêtes")
    logger.warning(f"📊 Log level: {LOG_LEVEL}")
    logger.warning("═" * 60)
    
    LOADING_STATUS["grammar_loaded"] = True
    LOADING_STATUS["grammar_load_time"] = datetime.now().isoformat()

@app.on_event("shutdown")
async def shutdown_event():
    """Événement d'arrêt"""
    logger.warning("=" * 60)
    logger.warning("🛑 NKOTRONIC API - ARRÊT")
    logger.warning(f"📊 Sessions actives: {len(sessions)}")
    logger.warning(f"📨 Total requêtes: {REQUEST_COUNTER}")
    logger.warning(f"⏱️  Uptime: {(datetime.now() - SERVER_START_TIME).total_seconds():.0f}s")
    logger.warning("=" * 60)

# ═══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)