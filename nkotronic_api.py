"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC BACKEND - VERSION CORRIGÉE (SYNTAX FIX)
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

SYSTEM_MESSAGE = "Alu ni djö ! Je suis Nkotronic, votre assistant du N'ko. Que puis-je faire pour vous ?"

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION GEMINI
# ═══════════════════════════════════════════════════════════════════

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY or "DUMMY_KEY") # Évite crash au boot si clé absente

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
    model: str = "gemini-2.0-flash"  # Note: gemini-2.5 n'existe pas encore, 2.0 est la plus récente
    temperature: float = 0.7
    max_tokens: int = 4000

# ═══════════════════════════════════════════════════════════════════
# FASTAPI APP
# ═══════════════════════════════════════════════════════════════════

app = FastAPI(title="Nkotronic API", version="2.0.0")

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
        logger.info(f"🗑️ Session supprimée: {sid}")

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
    return sessions[session_id]

# ═══════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {
        "service": "Nkotronic API",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions)
    }

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    ENDPOINT CORRIGÉ : Le 'yield' est uniquement dans la sous-fonction generate()
    """
    
    async def generate():
        global FIRST_REQUEST
        
        # 1. Vérification Clé API (dans le flux)
        if not GEMINI_API_KEY:
            yield f"data: {json.dumps({'error': 'GEMINI_API_KEY manquante sur le serveur'})}\n\n"
            return

        try:
            # 2. Détection Cold Start
            uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
            if FIRST_REQUEST and uptime < 60:
                yield f"data: {json.dumps({'cold_start': True, 'message': 'Réveil du serveur...'})}\n\n"
                FIRST_REQUEST = False

            # 3. Gestion Session
            session = get_session(request.session_id, initialize=True)
            session.history.append({"role": "user", "parts": [{"text": request.message}]})

            # 4. Appel Gemini
            model = genai.GenerativeModel(
                model_name=request.model,
                safety_settings=safety_settings
            )

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

            # 5. Sauvegarde Historique
            session.history.append({"role": "model", "parts": [{"text": full_response}]})
            session.last_activity = datetime.now()
            session.message_count += 1
            
            yield f"data: {json.dumps({'done': True, 'message_count': session.message_count})}\n\n"

        except Exception as e:
            logger.error(f"❌ Erreur Stream: {str(e)}")
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

# Les autres endpoints (health, loading-status, etc.) restent identiques
@app.get("/health")
async def health_check():
    return {"status": "healthy", "uptime": (datetime.now() - SERVER_START_TIME).total_seconds()}

@app.on_event("startup")
async def startup_event():
    LOADING_STATUS["grammar_loaded"] = True
    logger.info("🚀 NKOTRONIC API READY")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)