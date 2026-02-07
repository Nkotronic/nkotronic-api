# ══════════════════════════════════════════════════════════════╗
# ║  NKOTRONIC BACKEND - VERSION GEMINI CORRIGÉE               ║
# ║  ✅ Tous les endpoints nécessaires                         ║
# ║  ✅ Gestion correcte de l'historique                       ║
# ║  ✅ Cold start détection                                   ║
# ║  ✅ Message système initial dans l'historique              ║
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
from datetime import datetime, timedelta
from collections import OrderedDict
import asyncio

app = FastAPI(title="Nkotronic API - Gemini Edition", version="5.2.0")

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

INITIAL_SYSTEM_MESSAGE = "Alu ni djö ! Je suis Nkotronic, votre assistant du N'ko. Que puis-je faire pour vous ?"

GRAMMAR_FILE_PATH = "Tu es Nkotronic, l'IA.txt"
NKOTRONIC_SYSTEM_PROMPT = ""
LOADING_STATUS = {
    "status": "init", 
    "message": "Initialisation...", 
    "progress": 0, 
    "loaded": False,
    "grammar_loaded": False,
    "start_time": None
}

# Variable pour détecter le cold start
SERVER_START_TIME = datetime.now()
FIRST_REQUEST = True

def load_system_prompt():
    global NKOTRONIC_SYSTEM_PROMPT, LOADING_STATUS
    try:
        LOADING_STATUS["status"] = "loading"
        LOADING_STATUS["message"] = "Chargement de la grammaire..."
        LOADING_STATUS["progress"] = 50
        
        if os.path.exists(GRAMMAR_FILE_PATH):
            with open(GRAMMAR_FILE_PATH, 'r', encoding='utf-8') as f:
                grammar_content = f.read()
            NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\n\n" + grammar_content
            LOADING_STATUS.update({
                "status": "ready", 
                "message": "Grammaire chargée avec succès",
                "loaded": True, 
                "grammar_loaded": True,
                "progress": 100
            })
            print(f"✅ Grammaire chargée ({len(NKOTRONIC_SYSTEM_PROMPT)} caractères)")
            return True
        else:
            NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT
            LOADING_STATUS.update({
                "status": "warning", 
                "message": "Fichier grammaire manquant - Mode dégradé",
                "loaded": True,
                "grammar_loaded": False,
                "progress": 100
            })
            print("⚠️ Fichier grammaire non trouvé - Mode dégradé")
            return False
    except Exception as e:
        LOADING_STATUS.update({
            "status": "error", 
            "message": f"Erreur : {str(e)}",
            "loaded": False,
            "grammar_loaded": False
        })
        print(f"❌ Erreur chargement grammaire : {e}")
        return False

# ═══════════════════════════════════════════════════════════
# GESTION DES SESSIONS
# ═══════════════════════════════════════════════════════════

class SessionData(BaseModel):
    history: List[Dict] = []
    last_activity: datetime
    message_count: int = 0

sessions: OrderedDict[str, SessionData] = OrderedDict()

def get_session(session_id: str, initialize: bool = False) -> SessionData:
    """Récupère ou crée une session"""
    if session_id in sessions:
        sessions.move_to_end(session_id)
        session = sessions[session_id]
        session.last_activity = datetime.now()
        return session
    
    # Nouvelle session
    new_session = SessionData(
        history=[],
        last_activity=datetime.now(),
        message_count=0
    )
    
    # Si initialize=True, ajouter le message système initial
    if initialize:
        new_session.history = [
            {
                "role": "user",
                "parts": ["Bonjour"]
            },
            {
                "role": "model",
                "parts": [INITIAL_SYSTEM_MESSAGE]
            }
        ]
    
    sessions[session_id] = new_session
    
    # Limite à 1000 sessions max
    if len(sessions) > 1000:
        sessions.popitem(last=False)
    
    print(f"📝 Nouvelle session créée : {session_id}")
    return new_session

def cleanup_old_sessions():
    """Nettoie les sessions inactives depuis plus de 24h"""
    cutoff = datetime.now() - timedelta(hours=24)
    to_delete = [sid for sid, data in sessions.items() if data.last_activity < cutoff]
    for sid in to_delete:
        del sessions[sid]
    if to_delete:
        print(f"🧹 {len(to_delete)} sessions nettoyées")

# ═══════════════════════════════════════════════════════════
# MODÈLES DE DONNÉES
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gemini-2.5-flash"  # ✅ MEILLEUR CHOIX
    temperature: float = 0.7
    max_tokens: int = 4000

# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/")
async def root():
    """Endpoint racine"""
    return {
        "status": "online",
        "service": "Nkotronic API",
        "model": "Gemini",
        "version": "5.2.0",
        "uptime_seconds": (datetime.now() - SERVER_START_TIME).total_seconds(),
        "active_sessions": len(sessions)
    }

@app.get("/health")
async def health_check():
    """Endpoint de santé pour le warmup"""
    global FIRST_REQUEST
    
    # Détecter le cold start
    uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
    is_cold_start = uptime < 5  # Si le serveur vient de démarrer
    
    cleanup_old_sessions()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": uptime,
        "cold_start": is_cold_start,
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False),
        "active_sessions": len(sessions),
        "first_request": FIRST_REQUEST
    }

@app.get("/loading-status")
async def loading_status():
    """Status du chargement de la grammaire"""
    return LOADING_STATUS

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Endpoint de chat avec streaming SSE"""
    global FIRST_REQUEST
    
    async def generate():
        try:
            # Vérifier la clé API
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'Clé API Gemini manquante'})}\n\n"
                return

            # Configurer Gemini
            genai.configure(api_key=api_key)
            
            # Configuration de sécurité : autoriser tout
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # Créer le modèle
            model = genai.GenerativeModel(
                model_name=request.model,
                system_instruction=NKOTRONIC_SYSTEM_PROMPT,
                safety_settings=safety_settings
            )

            # Récupérer ou créer la session
            is_new_session = request.session_id not in sessions
            session = get_session(request.session_id, initialize=is_new_session)
            
            # Détecter le cold start (première requête après démarrage)
            uptime = (datetime.now() - SERVER_START_TIME).total_seconds()
            is_cold_start = FIRST_REQUEST and uptime < 60
            
            if is_cold_start:
                FIRST_REQUEST = False
                # Informer le frontend qu'il y a eu un cold start
                yield f"data: {json.dumps({
                    'cold_start': True,
                    'message': 'Initialisation du serveur...'
                })}\n\n"
                # Petit délai pour que le frontend affiche le message
                await asyncio.sleep(0.5)
            
            # Créer le chat avec l'historique
            chat = model.start_chat(history=session.history)
            
            # Envoyer le message avec streaming
            full_response = ""
            response_stream = chat.send_message(
                request.message,
                stream=True,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=request.max_tokens,
                    temperature=request.temperature,
                )
            )
            
            # Streamer la réponse
            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'content': chunk.text})}\n\n"
            
            # Mettre à jour l'historique de la session
            session.history = chat.history
            session.last_activity = datetime.now()
            session.message_count += 1
            
            # Signal de fin
            yield f"data: {json.dumps({
                'done': True, 
                'session_id': request.session_id,
                'message_count': session.message_count
            })}\n\n"
            
            print(f"✅ Message traité pour session {request.session_id} (total: {session.message_count})")
            
        except Exception as e:
            print(f"❌ Erreur streaming : {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Supprimer une session"""
    if session_id in sessions:
        del sessions[session_id]
        return {"status": "deleted", "session_id": session_id}
    return {"status": "not_found", "session_id": session_id}

@app.get("/sessions")
async def list_sessions():
    """Liste toutes les sessions actives"""
    return {
        "total": len(sessions),
        "sessions": [
            {
                "id": sid,
                "message_count": data.message_count,
                "last_activity": data.last_activity.isoformat()
            }
            for sid, data in sessions.items()
        ]
    }

# ═══════════════════════════════════════════════════════════
# ÉVÉNEMENTS
# ═══════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    """Chargement au démarrage"""
    print("🚀 Démarrage de Nkotronic API...")
    LOADING_STATUS["start_time"] = datetime.now().isoformat()
    load_system_prompt()
    print(f"✅ Serveur prêt - {len(sessions)} sessions actives")

@app.on_event("shutdown")
async def shutdown():
    """Nettoyage à l'arrêt"""
    print("👋 Arrêt de Nkotronic API...")
    sessions.clear()

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)