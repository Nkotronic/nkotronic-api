"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC BACKEND - VERSION FÉVRIER 2026
═══════════════════════════════════════════════════════════════════
✅ Modèle : gemini-3-flash-preview (Dernière version stable preview)
✅ Correction SyntaxError SSE
✅ Gestion de session robuste
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
FIRST_REQUEST = True 
LOADING_STATUS = {
    "grammar_loaded": False,
    "grammar_load_time": None
}

# Message système pour l'assistant N'ko
SYSTEM_MESSAGE = "Alu ni djö ! Je suis Nkotronic, votre assistant du N'ko. Que puis-je faire pour vous ?"

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION GEMINI
# ═══════════════════════════════════════════════════════════════════

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Initialisation sécurisée
genai.configure(api_key=GEMINI_API_KEY if GEMINI_API_KEY else "DUMMY_KEY")

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
    model: str = "gemini-3-flash-preview"  # ✨ MISE À JOUR VERS GEMINI 3
    temperature: float = 0.7
    max_tokens: int = 4000

# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="Nkotronic API", version="3.0.0")

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
    now = datetime.now()
    to_delete = [sid for sid, s in sessions.items() if (now - s.last_activity) > timedelta(hours=24)]
    for sid in to_delete:
        del sessions[sid]
        logger.info(f"🗑️ Session expirée supprimée: {sid}")

def get_session(session_id: str, initialize: bool = False) -> SessionData:
    cleanup_old_sessions()
    if session_id not in sessions:
        if not initialize:
            raise HTTPException(status_code=404, detail=f"Session {session_id} introuvable")
        
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
        logger.info(f"✨ Nouvelle session: {session_id}")
    return sessions[session_id]

# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "service": "Nkotronic API",
        "version": "3.0.0",
        "model": "gemini-3-flash-preview",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions)
    }

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Endpoint de chat en streaming SSE corrigé.
    """
    
    async def generate():
        global FIRST_REQUEST
        
        # Vérification clé API au début du flux
        if not GEMINI_API_KEY:
            logger.error("❌ Clé API manquante")
            yield f"data: {json.dumps({'error': 'Configuration serveur : Clé API manquante'})}\n\n"
            return

        try:
            # Détection Cold Start (Render)
            uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
            if FIRST_REQUEST and uptime < 60:
                yield f"data: {json.dumps({'cold_start': True, 'message': 'Réveil des moteurs Nkotronic...'})}\n\n"
                FIRST_REQUEST = False

            # Récupération de la session
            session = get_session(request.session_id, initialize=True)
            
            # Ajout du message utilisateur
            session.history.append({"role": "user", "parts": [{"text": request.message}]})

            # Initialisation du modèle Gemini 3
            model = genai.GenerativeModel(
                model_name=request.model,
                safety_settings=safety_settings
            )

            # Appel API en streaming
            logger.info(f"🤖 Appel Gemini 3 - Session: {request.session_id}")
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

            # Mise à jour de l'historique avec la réponse complète
            session.history.append({"role": "model", "parts": [{"text": full_response}]})
            session.last_activity = datetime.now()
            session.message_count += 1
            
            # Signal de fin de flux
            yield f"data: {json.dumps({'done': True, 'message_count': session.message_count})}\n\n"

        except Exception as e:
            logger.error(f"❌ Erreur pendant le stream: {str(e)}")
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

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "model": "gemini-3-flash-preview",
        "active_sessions": len(sessions)
    }

@app.on_event("startup")
async def startup_event():
    LOADING_STATUS["grammar_loaded"] = True
    LOADING_STATUS["grammar_load_time"] = datetime.now().isoformat()
    logger.info("🚀 NKOTRONIC API v3 DÉMARRÉE SUR GEMINI 3")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)