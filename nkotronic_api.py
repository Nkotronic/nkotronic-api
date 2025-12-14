"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version 4.5.0 GRAMMAR ONLY             ║
║  ✅ Grammaire N'ko uniquement                                ║
║  ✅ Démarrage ultra-rapide (~1 seconde)                      ║
║  ✅ Compatible Render gratuit (~100 MB RAM)                  ║
║  ✅ Prêt pour ajout vocabulaire futur                        ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import openai
import os
import json
from typing import List, Optional, Dict
from datetime import datetime
from collections import OrderedDict

app = FastAPI(title="Nkotronic API", version="4.5.0-GRAMMAR-ONLY")

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

# Grammaire
GRAMMAR_FILE_PATH = "Tu es Nkotronic, l'IA.txt"

# Variables globales
NKOTRONIC_SYSTEM_PROMPT = None
LOADING_STATUS = {
    "status": "initializing",
    "grammar_loaded": False,
    "version": "4.5.0-GRAMMAR-ONLY"
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
- Tu corriges avec bienveillance les erreurs

═══════════════════════════════════════════════════════════════
"""

def load_system_prompt():
    """Charge le prompt système depuis le fichier de grammaire"""
    global NKOTRONIC_SYSTEM_PROMPT, LOADING_STATUS
    
    try:
        print(f"📥 Chargement de la grammaire: {GRAMMAR_FILE_PATH}")
        
        with open(GRAMMAR_FILE_PATH, 'r', encoding='utf-8') as f:
            grammar_content = f.read()
        
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + grammar_content + """

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
    model_config = {"protected_namespaces": ()}  # Fix Pydantic warning
    
    response: str
    model_used: str
    tokens_used: Optional[int] = None
    session_id: str
    messages_in_session: int

# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint principal de conversation"""
    try:
        if not LOADING_STATUS.get("grammar_loaded"):
            raise HTTPException(status_code=503, detail="Grammaire en cours de chargement")
        
        if not OPENAI_API_KEY:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
        
        session = get_session(request.session_id)
        
        # Messages
        messages = [{"role": "system", "content": NKOTRONIC_SYSTEM_PROMPT}]
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
            messages_in_session=len(session.messages)
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
            
            # Messages
            messages = [{"role": "system", "content": NKOTRONIC_SYSTEM_PROMPT}]
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
            
            yield f"data: {json.dumps({'done': True})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/")
async def root():
    return {
        "name": "Nkotronic API",
        "version": "4.5.0-GRAMMAR-ONLY",
        "status": "running",
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False),
        "vocabulary": "disabled (upgrade to enable)",
        "ram_usage": "~100 MB"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False)
    }

@app.get("/status")
async def status():
    return LOADING_STATUS

# ═══════════════════════════════════════════════════════════
# DÉMARRAGE
# ═══════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    print("=" * 70)
    print("🚀 NKOTRONIC API v4.5.0 - GRAMMAR ONLY")
    print("=" * 70)
    print("💡 Version légère - Grammaire uniquement")
    print("💰 Vocabulaire disponible après upgrade")
    print("=" * 70)
    
    # Charger la grammaire
    print("\n📖 Chargement de la grammaire N'ko...")
    grammar_ok = load_system_prompt()
    
    print("\n" + "=" * 70)
    if grammar_ok:
        print("✅ API PRÊTE !")
        print(f"📊 Grammaire: {len(NKOTRONIC_SYSTEM_PROMPT):,} caractères")
        print("💾 RAM utilisée: ~100 MB")
    else:
        print("⚠️ Grammaire non chargée - mode dégradé")
    print("=" * 70 + "\n")
    
    LOADING_STATUS["status"] = "ready"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)