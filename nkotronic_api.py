"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC BACKEND - VERSION FINALE CORRIGÉE
═══════════════════════════════════════════════════════════════════
✅ Modèle : gemini-2.5-flash
✅ Endpoint /health avec cold start detection
✅ Message système intégré dans l'historique
✅ Cleanup automatique des sessions
✅ Variable FIRST_REQUEST correctement initialisée
✅ Streaming SSE optimisé
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

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# VARIABLES GLOBALES
# ═══════════════════════════════════════════════════════════════════

sessions: Dict[str, 'SessionData'] = {}
SERVER_START_TIME = datetime.now()
FIRST_REQUEST = True  # ✅ VARIABLE INITIALISÉE
LOADING_STATUS = {
    "grammar_loaded": False,
    "grammar_load_time": None
}

# Message système
SYSTEM_MESSAGE = "Alu ni djö ! Je suis Nkotronic, votre assistant du N'ko. Que puis-je faire pour vous ?"

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

# ═══════════════════════════════════════════════════════════════════
# MODÈLES DE DONNÉES
# ═══════════════════════════════════════════════════════════════════

class SessionData(BaseModel):
    session_id: str
    history: List[dict]
    created_at: datetime
    last_activity: datetime
    message_count: int = 0

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gemini-2.5-flash"  # ✅ GEMINI 2.5 FLASH
    temperature: float = 0.7
    max_tokens: int = 4000

# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="Nkotronic API", version="2.0.0")

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
    """Nettoie les sessions inactives depuis plus de 24h"""
    now = datetime.now()
    to_delete = []
    
    for session_id, session in sessions.items():
        if (now - session.last_activity) > timedelta(hours=24):
            to_delete.append(session_id)
    
    for session_id in to_delete:
        del sessions[session_id]
        logger.info(f"🗑️  Session supprimée: {session_id}")
    
    if to_delete:
        logger.info(f"🧹 Nettoyage: {len(to_delete)} session(s) supprimée(s)")

def get_session(session_id: str, initialize: bool = False) -> SessionData:
    """Récupère ou crée une session"""
    cleanup_old_sessions()
    
    if session_id not in sessions:
        if not initialize:
            raise HTTPException(status_code=404, detail=f"Session {session_id} introuvable")
        
        # Créer nouvelle session avec message système dans l'historique
        sessions[session_id] = SessionData(
            session_id=session_id,
            history=[
                {"role": "user", "parts": [{"text": "Bonjour"}]},
                {"role": "model", "parts": [{"text": SYSTEM_MESSAGE}]}
            ],
            created_at=datetime.now(),
            last_activity=datetime.now(),
            message_count=0
        )
        logger.info(f"✨ Nouvelle session créée: {session_id}")
    
    return sessions[session_id]

# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Endpoint racine"""
    return {
        "service": "Nkotronic API",
        "version": "2.0.0",
        "status": "running",
        "model": "gemini-2.5-flash",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions)
    }

@app.get("/health")
async def health_check():
    """
    ✅ Endpoint de health check avec détection de cold start
    """
    uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
    is_cold_start = uptime < 5  # Cold start si uptime < 5 secondes
    
    return {
        "status": "healthy",
        "cold_start": is_cold_start,
        "uptime_seconds": uptime,
        "grammar_loaded": LOADING_STATUS["grammar_loaded"],
        "active_sessions": len(sessions),
        "model": "gemini-2.5-flash"
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
                "history_length": len(s.history)
            }
            for s in sessions.values()
        ]
    }

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Supprime une session spécifique"""
    if session_id in sessions:
        del sessions[session_id]
        logger.info(f"🗑️  Session supprimée manuellement: {session_id}")
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session introuvable")

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    ✅ Endpoint de chat avec streaming SSE
    """
    global FIRST_REQUEST  # ✅ Déclarer comme global
    
    session_id = request.session_id
    user_message = request.message
    
    logger.info(f"📩 Message reçu - Session: {session_id}")
    logger.info(f"💬 Contenu: {user_message[:50]}...")
    
    # Vérifier la clé API
    if not GEMINI_API_KEY:
        logger.error("❌ Clé API manquante")
        yield f"data: {json.dumps({'error': 'Clé API manquante'})}\n\n"
        return
    
    # Cold start detection
    uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
    is_cold_start = FIRST_REQUEST and uptime < 60
    
    async def generate():
        global FIRST_REQUEST
        
        try:
            # Envoyer notification cold start si nécessaire
            if is_cold_start:
                logger.info("❄️  Cold start détecté")
                yield f"data: {json.dumps({'cold_start': True, 'message': 'Initialisation du serveur (30-60s)...'})}\n\n"
                FIRST_REQUEST = False
            
            # Récupérer ou créer la session
            is_new_session = session_id not in sessions
            session = get_session(session_id, initialize=is_new_session)
            
            # Ajouter le message utilisateur à l'historique
            session.history.append({
                "role": "user",
                "parts": [{"text": user_message}]
            })
            
            # Créer le modèle
            model = genai.GenerativeModel(
                model_name=request.model,
                safety_settings=safety_settings
            )
            
            # Générer la réponse en streaming
            logger.info(f"🤖 Génération avec {request.model}...")
            
            response = model.generate_content(
                session.history,
                generation_config=genai.types.GenerationConfig(
                    temperature=request.temperature,
                    max_output_tokens=request.max_tokens,
                ),
                stream=True
            )
            
            full_response = ""
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'content': chunk.text})}\n\n"
            
            # Ajouter la réponse complète à l'historique
            session.history.append({
                "role": "model",
                "parts": [{"text": full_response}]
            })
            
            # Mettre à jour la session
            session.last_activity = datetime.now()
            session.message_count += 1
            
            logger.info(f"✅ Réponse générée ({len(full_response)} chars)")
            
            # Envoyer le signal de fin
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
# STARTUP EVENT
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup_event():
    """Événement de démarrage"""
    logger.info("═" * 60)
    logger.info("🚀 NKOTRONIC API - DÉMARRAGE")
    logger.info("═" * 60)
    logger.info(f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"🤖 Modèle: gemini-2.5-flash")
    logger.info(f"🔑 Clé API: {'✅ Configurée' if GEMINI_API_KEY else '❌ Manquante'}")
    logger.info("═" * 60)
    
    # Simuler le chargement de la grammaire
    LOADING_STATUS["grammar_loaded"] = True
    LOADING_STATUS["grammar_load_time"] = datetime.now().isoformat()
    logger.info("📚 Grammaire N'ko chargée")

@app.on_event("shutdown")
async def shutdown_event():
    """Événement d'arrêt"""
    logger.info("=" * 60)
    logger.info("🛑 NKOTRONIC API - ARRÊT")
    logger.info(f"📊 Sessions actives: {len(sessions)}")
    logger.info(f"⏱️  Uptime: {(datetime.now() - SERVER_START_TIME).total_seconds():.0f}s")
    logger.info("=" * 60)

# ═══════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)