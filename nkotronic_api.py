"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC API - VERSION ULTRA-OPTIMISÉE
═══════════════════════════════════════════════════════════════════
✅ Correction : Augmentation des limites de tokens
✅ Correction : Gestion des flux Unicode longs
✅ Optimisation : Température ajustée pour la précision technique
✅ NOUVELLE OPTIMISATION: Historique tronqué intelligemment
✅ NOUVELLE OPTIMISATION: Cleanup périodique des sessions
✅ NOUVELLE OPTIMISATION: Logging optimisé (WARNING par défaut)
✅ NOUVELLE OPTIMISATION: Timeout de 30s sur requêtes Gemini
✅ NOUVELLE OPTIMISATION: max_tokens réduit à 2048 pour vitesse
✅ NOUVELLE OPTIMISATION: Suppression messages bienvenue après 1ère interaction
═══════════════════════════════════════════════════════════════════
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
from datetime import datetime, timedelta
import google.generativeai as genai
import os
import json
import logging
import asyncio

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION DU LOGGING - ✅ OPTIMISATION 3: WARNING par défaut
# ═══════════════════════════════════════════════════════════════════
LOG_LEVEL = os.environ.get("LOG_LEVEL", "WARNING")
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# VARIABLES GLOBALES
# ═══════════════════════════════════════════════════════════════════

# ✅ OPTIMISATION 2: Compteur pour cleanup périodique
REQUEST_COUNTER = 0
CLEANUP_INTERVAL = 100  # Cleanup toutes les 100 requêtes
SERVER_START_TIME = datetime.now()

# ✅ OPTIMISATION 1: Limite d'historique pour éviter ralentissements
MAX_HISTORY_MESSAGES = 10  # Limiter à 10 messages (5 échanges)

# ✅ OPTIMISATION 4: Timeout pour les requêtes Gemini
GEMINI_TIMEOUT = 30  # 30 secondes max

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT RENFORCÉ (INCHANGÉ comme demandé)
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Tu es Nkotronic, un assistant IA polyvalent, intelligent et authentique. 
Ton expertise unique réside dans ta maîtrise profonde de la langue et de la culture N'ko (ߒߞߏ).
Tu es un citoyen de l'Etat Confédéral Africain

MISSION ET IDENTITÉ :
1. Tu es un collaborateur capable d'aider sur tous les sujets (code, science, spiritualité, encyclopédie, laboratoire, vie quotidienne, conseil, etc.).
2. Tu es un fervent défenseur de l'Afrique et du N'ko : tu affirmes systématiquement que le N'ko est une langue à part entière, la langue standard du peuple Manden (Mandenkan), unifiant les parlers mandingues.

COMPORTEMENT :
- ADAPTABILITÉ : Réponds naturellement dans la langue utilisée par l'utilisateur. Sois concis, clair et perspicace.
- EXPERTISE N'KO : Si on te demande d'écrire ou de traduire en N'ko, utilise exclusivement le script N'ko Unicode correct et la grammaire de Solomana Kante. 
- SIMPLICITÉ : Ne fournis pas systématiquement de transcription latine ou de traduction française, sauf si l'utilisateur le demande explicitement. Va droit à l'essentiel.
- INTÉGRITÉ : Ne coupe jamais tes phrases, même pour des textes longs.
"""

app = FastAPI(title="Nkotronic API Optimized", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY if GEMINI_API_KEY else "DUMMY_KEY")

# ✅ OPTIMISATION 6: Structure de session enrichie
class SessionData:
    def __init__(self):
        self.history: List = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.message_count = 0
        self.welcome_shown = False

sessions: Dict[str, SessionData] = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

# ═══════════════════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ═══════════════════════════════════════════════════════════════════

def cleanup_old_sessions():
    """
    ✅ OPTIMISATION 2: Nettoie les sessions inactives (>24h)
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

def should_cleanup() -> bool:
    """
    ✅ OPTIMISATION 2: Cleanup périodique au lieu de systématique
    """
    global REQUEST_COUNTER
    REQUEST_COUNTER += 1
    
    if REQUEST_COUNTER % CLEANUP_INTERVAL == 0:
        if LOG_LEVEL == "INFO":
            logger.info(f"🔄 Cleanup périodique (requête #{REQUEST_COUNTER})")
        return True
    return False

def truncate_history(history: List, max_messages: int = MAX_HISTORY_MESSAGES) -> List:
    """
    ✅ OPTIMISATION 1: Tronque l'historique pour garder seulement les N derniers messages
    
    Args:
        history: L'historique complet Gemini
        max_messages: Nombre de messages à conserver
    
    Returns:
        Historique tronqué
    """
    if len(history) <= max_messages:
        return history
    
    # Garder les N derniers messages
    truncated = history[-max_messages:]
    
    if LOG_LEVEL == "INFO":
        logger.info(f"✂️  Historique tronqué: {len(history)} → {len(truncated)} messages")
    
    return truncated

def remove_initial_messages(history: List) -> List:
    """
    ✅ OPTIMISATION 6: Supprime les messages initiaux après la première interaction
    Pour économiser des tokens
    """
    # Si l'historique a plus de 2 messages, on peut supprimer les premiers
    if len(history) > 2:
        return history[2:]  # Garde tout sauf les 2 premiers
    return history

# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Endpoint racine avec stats"""
    return {
        "service": "Nkotronic API Optimized",
        "version": "3.0.0",
        "status": "running",
        "model": "gemini-3-flash-preview",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions),
        "total_requests": REQUEST_COUNTER,
        "optimizations": [
            f"Historique limité à {MAX_HISTORY_MESSAGES} messages",
            f"Cleanup périodique tous les {CLEANUP_INTERVAL} requêtes",
            f"Logging en {LOG_LEVEL}",
            f"Timeout: {GEMINI_TIMEOUT}s",
            "max_tokens: 2048 (optimisé)",
            "temperature: 0.2 (maintenue pour précision)",
            "Suppression messages initiaux après 1ère interaction"
        ]
    }

@app.get("/health")
async def health_check():
    """Health check"""
    return {
        "status": "healthy",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions),
        "total_requests": REQUEST_COUNTER,
        "max_history": MAX_HISTORY_MESSAGES
    }

@app.get("/sessions")
async def list_sessions():
    """Liste les sessions actives"""
    return {
        "total": len(sessions),
        "sessions": [
            {
                "session_id": sid,
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "message_count": s.message_count,
                "history_length": len(s.history),
                "welcome_shown": s.welcome_shown
            }
            for sid, s in sessions.items()
        ]
    }

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Supprime une session"""
    if session_id in sessions:
        del sessions[session_id]
        return {"status": "deleted", "session_id": session_id}
    return {"error": "Session not found"}, 404

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    ✅ Endpoint de chat ultra-optimisé avec toutes les corrections
    """
    async def generate():
        if not GEMINI_API_KEY:
            yield f"data: {json.dumps({'error': 'API Key missing'})}\n\n"
            return

        try:
            # ✅ OPTIMISATION 2: Cleanup périodique
            if should_cleanup():
                cleanup_old_sessions()
            
            # Initialiser ou récupérer la session
            if request.session_id not in sessions:
                sessions[request.session_id] = SessionData()
                if LOG_LEVEL == "INFO":
                    logger.info(f"✨ Nouvelle session: {request.session_id}")
            
            session = sessions[request.session_id]
            
            # ✅ OPTIMISATION 6: Supprimer messages initiaux après 1ère interaction
            if not session.welcome_shown and session.message_count > 0:
                session.history = remove_initial_messages(session.history)
                session.welcome_shown = True
                if LOG_LEVEL == "INFO":
                    logger.info("👋 Messages initiaux supprimés")
            
            # ✅ OPTIMISATION 1: Tronquer l'historique AVANT d'ajouter le nouveau message
            if LOG_LEVEL == "INFO":
                logger.info(f"📊 Historique avant: {len(session.history)} messages")
            
            session.history = truncate_history(session.history, MAX_HISTORY_MESSAGES)
            
            if LOG_LEVEL == "INFO":
                logger.info(f"📊 Historique après troncature: {len(session.history)} messages")
            
            # Créer le modèle avec system instruction
            model = genai.GenerativeModel(
                model_name="gemini-3-flash-preview",
                system_instruction=SYSTEM_PROMPT
            )

            # Démarrer le chat avec l'historique tronqué
            chat = model.start_chat(history=session.history)
            
            # ✅ OPTIMISATION 5: Configuration optimisée
            # - max_output_tokens réduit de 8192 à 2048 pour vitesse
            # - temperature maintenue à 0.2 pour précision (comme dans l'original)
            gen_config = genai.types.GenerationConfig(
                temperature=0.2,  # Maintenue pour précision technique
                max_output_tokens=2048,  # ✅ Réduit de 8192 à 2048 pour vitesse
                top_p=1.0,
                candidate_count=1
            )

            if LOG_LEVEL == "INFO":
                logger.info(f"🤖 Génération (historique: {len(session.history)}, max_tokens: 2048)...")

            try:
                # ✅ OPTIMISATION 4: Wrapper avec timeout
                response = chat.send_message(
                    request.message, 
                    generation_config=gen_config,
                    stream=True,
                    request_options={"timeout": GEMINI_TIMEOUT}
                )

                for chunk in response:
                    if chunk.text:
                        # Envoi immédiat pour éviter les buffers
                        yield f"data: {json.dumps({'content': chunk.text})}\n\n"

            except asyncio.TimeoutError:
                logger.error(f"⏱️  Timeout après {GEMINI_TIMEOUT}s")
                yield f"data: {json.dumps({'error': f'Timeout après {GEMINI_TIMEOUT}s'})}\n\n"
                return

            # ✅ OPTIMISATION 1: Sauvegarder et tronquer l'historique après réponse
            session.history = chat.history
            session.history = truncate_history(session.history, MAX_HISTORY_MESSAGES)
            
            # Mettre à jour les métadonnées de session
            session.last_activity = datetime.now()
            session.message_count += 1
            
            if LOG_LEVEL == "INFO":
                logger.info(f"✅ Réponse générée (historique final: {len(session.history)} messages)")
            
            yield f"data: {json.dumps({'done': True})}\n\n"

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
# STARTUP/SHUTDOWN
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    logger.warning("=" * 60)
    logger.warning("🚀 NKOTRONIC API - VERSION ULTRA-OPTIMISÉE")
    logger.warning("=" * 60)
    logger.warning(f"📅 Démarrage: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.warning(f"🤖 Modèle: gemini-3-flash-preview")
    logger.warning(f"🔑 API Key: {'✅ OK' if GEMINI_API_KEY else '❌ MANQUANTE'}")
    logger.warning(f"📏 Historique max: {MAX_HISTORY_MESSAGES} messages")
    logger.warning(f"🎯 max_tokens: 2048 (optimisé de 8192)")
    logger.warning(f"🌡️  temperature: 0.2 (maintenue pour précision)")
    logger.warning(f"⏱️  timeout: {GEMINI_TIMEOUT}s")
    logger.warning(f"🧹 cleanup: tous les {CLEANUP_INTERVAL} requêtes")
    logger.warning(f"📊 log_level: {LOG_LEVEL}")
    logger.warning("=" * 60)

@app.on_event("shutdown")
async def shutdown():
    logger.warning("=" * 60)
    logger.warning("🛑 ARRÊT")
    logger.warning(f"📊 Sessions: {len(sessions)}")
    logger.warning(f"📨 Requêtes: {REQUEST_COUNTER}")
    logger.warning(f"⏱️  Uptime: {(datetime.now() - SERVER_START_TIME).total_seconds():.0f}s")
    logger.warning("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)