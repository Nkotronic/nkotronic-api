# ══════════════════════════════════════════════════════════════╗
# ║  NKOTRONIC BACKEND - VERSION GEMINI ULTIME (FULL)          ║
# ║  ✅ Prompt système complet + Grammaire                     ║
# ║  ✅ Gestion de l'historique Persistant                     ║
# ║  ✅ Paramètres de sécurité désactivés (pour la précision)  ║
# ║  ✅ Streaming SSE optimisé                                  ║
# ╚══════════════════════════════════════════════════════════════╝

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import json
from typing import List, Optional, Dict
from datetime import datetime
from collections import OrderedDict

app = FastAPI(title="Nkotronic API - Gemini Edition", version="5.1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# PROMPT SYSTÈME & CHARGEMENT
# ═══════════════════════════════════════════════════════════

EXPLANATORY_PROMPT = """
╔══════════════════════════════════════════════════════════════╗
║  📚 CONTEXTE ESSENTIEL SUR LE N'KO                          ║
╚══════════════════════════════════════════════════════════════╝
Le N'ko (ߒߞߏ) est SIMULTANÉMENT un Alphabet et une Langue.
Inventeur : Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫).

🎯 TON RÔLE :
- Tu es Nkotronic, l'assistant IA expert en N'ko.
- Tu maîtrises la grammaire ߒߞߏ ߞߊ߲ߜߍ.
- TRADUCTION TECHNIQUE : Ne simplifie JAMAIS. Utilise les termes exacts fournis :
  Ex: Météorologie = ߓߊ߲ߘߊߦߋߙߋ߲ߟߐ߲ߘߐߦߊ, Aéronautique = ߛߊ߲ߡߊߖߊ߲ߓߊ߲ߡߊ, Pilote = ߟߊߜߊ߲ߠߊ.
"""

GRAMMAR_FILE_PATH = "Tu es Nkotronic, l'IA.txt"
NKOTRONIC_SYSTEM_PROMPT = ""
LOADING_STATUS = {"status": "init", "message": "Attente...", "progress": 0, "loaded": False}

def load_system_prompt():
    global NKOTRONIC_SYSTEM_PROMPT, LOADING_STATUS
    try:
        if os.path.exists(GRAMMAR_FILE_PATH):
            with open(GRAMMAR_FILE_PATH, 'r', encoding='utf-8') as f:
                grammar_content = f.read()
            NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\n\n" + grammar_content
            LOADING_STATUS.update({"status": "ready", "loaded": True, "progress": 100})
            print(f"✅ Grammaire chargée ({len(NKOTRONIC_SYSTEM_PROMPT)} chars)")
            return True
        else:
            NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT
            LOADING_STATUS.update({"status": "warning", "message": "Fichier grammaire manquant", "loaded": True})
            return False
    except Exception as e:
        LOADING_STATUS.update({"status": "error", "message": str(e), "loaded": False})
        return False

# ═══════════════════════════════════════════════════════════
# GESTION DES SESSIONS
# ═══════════════════════════════════════════════════════════

class SessionData(BaseModel):
    history: List[Dict] = []
    last_activity: datetime

sessions: OrderedDict[str, SessionData] = OrderedDict()

def get_session(session_id: str) -> SessionData:
    if session_id in sessions:
        sessions.move_to_end(session_id)
        return sessions[session_id]
    new_session = SessionData(history=[], last_activity=datetime.now())
    sessions[session_id] = new_session
    if len(sessions) > 1000: sessions.popitem(last=False)
    return new_session

# ═══════════════════════════════════════════════════════════
# LOGIQUE CHAT
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gemini-1.5-flash" # Ou gemini-1.5-pro
    temperature: float = 0.7
    max_tokens: int = 4000

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        try:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'Clé API manquante'})}\n\n"
                return

            genai.configure(api_key=api_key)
            
            # Configuration de sécurité : on autorise tout pour éviter les blocages sur les termes techniques
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            model = genai.GenerativeModel(
                model_name=request.model,
                system_instruction=NKOTRONIC_SYSTEM_PROMPT,
                safety_settings=safety_settings
            )

            session = get_session(request.session_id)
            chat = model.start_chat(history=session.history)
            
            full_response = ""
            response_stream = chat.send_message(
                request.message,
                stream=True,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
            )
            
            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'content': chunk.text})}\n\n"

            # Mise à jour de l'historique
            session.history = chat.history
            session.last_activity = datetime.now()
            
            yield f"data: {json.dumps({'done': True, 'session_id': request.session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# ═══════════════════════════════════════════════════════════
# ENDPOINTS DE MAINTENANCE
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"status": "online", "model": "Gemini-Nkotronic"}

@app.get("/loading-status")
async def status():
    return LOADING_STATUS

@app.on_event("startup")
async def startup():
    load_system_prompt()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)