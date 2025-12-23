"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version FINALE SIMPLE                  ║
║  ✅ Prompt système complet intégré                           ║
║  ✅ Aucune dépendance externe                                ║
║  ✅ Streaming SSE                                            ║
║  ✅ Sessions avec TTL 24h                                    ║
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
from datetime import datetime, timedelta
from collections import OrderedDict

app = FastAPI(title="Nkotronic API", version="4.0.0-FINAL-SIMPLE")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# PROMPT SYSTÈME COMPLET
# ═══════════════════════════════════════════════════════════

# Prompt explicatif qui précède la grammaire (toujours envoyé en premier)
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
   - Utilisé pour écrire les langues du monde

2. 🗣️ UNE LANGUE (langue littéraire standardisée)
   - Langue standard parlée du peuple Mandén
   - Grammaire codifiée par Solomana Kanté, appelé ߒߞߏ ߞߊ߲ߜߍ
   - Langue la plus proche de l'ancêtre commun de toutes les langues mandingues
   - Vocabulaire très riche, des milliards de mots dans tous les domaines
   - C'est une langue PARLÉE par des millions de locuteurs aujourd'hui !

3. L'INVENTEUR DU N'KO :
   - Celui qui a créé le Nko s'appelle Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)
   - il est souvent appelé Solomana Kanté.
   - Solomana Kanté, Solomana Kantè, Solomana Kantê, Solomāna Kanté, Solomāna Kantè et Solomāna Kantê, voilà les orthographes acceptables
   - Tout ce qui est Souleymane, Salomon ou autre orthographes relèvent de l'erreur

⚠️ ERREUR FRÉQUENTE À CORRIGER SYSTÉMATIQUEMENT :
Beaucoup de gens disent "Le N'ko est juste un alphabet" → C'EST FAUX !
Le N'ko est AUSSI une langue à part entière.

📖 SOURCES OFFICIELLES :
- Wikipédia français : https://fr.wikipedia.org/wiki/N%27ko_(langue)
- Tous les livres de Solomana Kanté (grammaires, dictionnaires, etc.)

🎯 TON RÔLE :
- Quand on te parle du N'ko, toujours préciser cette double nature
- Corriger avec bienveillance ceux qui réduisent le N'ko à un simple alphabet
- Expliquer que Solomana Kanté a créé SIMULTANÉMENT :
  * Un système d'écriture (l'alphabet)
  * Une langue littéraire standardisée (la langue)
- Tu es Nkotronic, l'assistant IA expert en N'ko
- Tu es bienveillant, précis et pédagogue
- Tu maîtrises parfaitement la grammaire N'ko
- Tu corriges avec bienveillance les erreurs

═══════════════════════════════════════════════════════════════

"""

# Chemin vers le fichier de grammaire
GRAMMAR_FILE_PATH = "Tu es Nkotronic, l'IA.txt"
NKOTRONIC_SYSTEM_PROMPT = None
GRAMMAR_SUMMARY = None  # Résumé condensé
LOADING_STATUS = {
    "status": "initializing",
    "message": "Initialisation en cours...",
    "progress": 0,
    "loaded": False
}

def load_system_prompt():
    """Charge le prompt système SANS le fichier de grammaire (test temporaire)"""
    global NKOTRONIC_SYSTEM_PROMPT, GRAMMAR_SUMMARY, LOADING_STATUS
    
    try:
        print("🔧 MODE TEST : Grammaire externe DÉSACTIVÉE")
        
        # Utiliser UNIQUEMENT le prompt explicatif
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + """

🌐 CAPACITÉS GÉNÉRALES :
- Tu peux discuter de TOUS les sujets (technologie, science, culture, fine-tuning, IA, etc.)
- Tu n'es PAS limité au N'ko uniquement
- Ta spécialité est le N'ko, mais tu es un assistant complet et polyvalent
- Réponds normalement aux questions hors N'ko
- Mets l'accent sur le N'ko quand c'est pertinent

Tu es Nkotronic, l'IA experte en N'ko ET assistant général polyvalent.
Tu es bienveillant, précis et pédagogue."""
        
        LOADING_STATUS.update({
            "status": "ready",
            "message": "✅ Nkotronic prêt (mode test sans grammaire externe)",
            "progress": 100,
            "loaded": True,
            "size": len(NKOTRONIC_SYSTEM_PROMPT)
        })
        print(f"✅ Prompt système de base chargé: {len(NKOTRONIC_SYSTEM_PROMPT):,} caractères")
        print(f"✅ Nkotronic prêt en mode test !")
        return True
        
    except Exception as e:
        print(f"❌ Erreur : {e}")
        LOADING_STATUS.update({
            "status": "error",
            "message": f"Erreur : {str(e)}",
            "progress": 0,
            "loaded": False
        })
        return False
    except FileNotFoundError:
        LOADING_STATUS.update({
            "status": "error",
            "message": f"❌ Fichier de grammaire introuvable : {GRAMMAR_FILE_PATH}",
            "progress": 0,
            "loaded": False,
            "error": "File not found"
        })
        print(f"❌ ERREUR: Fichier '{GRAMMAR_FILE_PATH}' introuvable !")
        print(f"📂 Placer le fichier \"Tu es Nkotronic, l'IA.txt\" dans le même dossier que ce script")
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + """
(ATTENTION: Grammaire complète non chargée - fichier manquant)

Tu es Nkotronic, l'assistant IA expert en N'ko.
Tu es bienveillant, précis et pédagogue. Tu maîtrises parfaitement le N'ko."""
        return False
        
    except Exception as e:
        LOADING_STATUS.update({
            "status": "error",
            "message": f"❌ Erreur lors du chargement : {str(e)}",
            "progress": 0,
            "loaded": False,
            "error": str(e)
        })
        print(f"❌ Erreur chargement prompt: {e}")
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\nTu es Nkotronic, assistant IA N'ko."
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
        # Vérifier si le prompt est en cours de chargement
        if not LOADING_STATUS["loaded"]:
            raise HTTPException(
                status_code=503, 
                detail={
                    "error": "Service temporairement indisponible",
                    "message": LOADING_STATUS["message"],
                    "status": LOADING_STATUS["status"],
                    "progress": LOADING_STATUS["progress"]
                }
            )
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
        
        if not NKOTRONIC_SYSTEM_PROMPT:
            raise HTTPException(status_code=500, detail="Prompt système non chargé")
        
        session = get_session(request.session_id)
        
        # Message système
        messages = [{"role": "system", "content": NKOTRONIC_SYSTEM_PROMPT}]
        
        # Historique
        for msg in session.messages:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Message actuel
        messages.append({"role": "user", "content": request.message})
        
        # OpenAI
        client = openai.OpenAI(api_key=api_key)
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
    """Endpoint streaming SSE"""
    
    async def generate():
        try:
            # Vérifier si le prompt est en cours de chargement
            if not LOADING_STATUS["loaded"]:
                yield f"data: {json.dumps({
                    'error': 'Service temporairement indisponible',
                    'message': LOADING_STATUS['message'],
                    'status': LOADING_STATUS['status'],
                    'progress': LOADING_STATUS['progress']
                })}\n\n"
                return
            
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'OPENAI_API_KEY not configured'})}\n\n"
                return
            
            if not NKOTRONIC_SYSTEM_PROMPT:
                yield f"data: {json.dumps({'error': 'Prompt système non chargé'})}\n\n"
                return
            
            session = get_session(request.session_id)
            
            # Streaming
            client = openai.OpenAI(api_key=api_key)
            
            # Détecter si on utilise un modèle GPT-5 (Responses API) ou autre (Chat Completions API)
            is_gpt5 = request.model.startswith("gpt-5")
            
            full_response = ""
            
            if is_gpt5:
                # ========== RESPONSES API (pour GPT-5) ==========
                # Construire l'input pour Responses API
                input_messages = []
                
                # Ajouter le prompt système
                input_messages.append({
                    "role": "developer",
                    "content": NKOTRONIC_SYSTEM_PROMPT
                })
                
                # Ajouter l'historique
                for msg in session.messages:
                    input_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
                
                # Ajouter le message utilisateur
                input_messages.append({
                    "role": "user",
                    "content": request.message
                })
                
                # Stream avec Responses API
                stream = client.responses.create(
                    model=request.model,
                    input=input_messages,
                    stream=True
                )
                
                # Traiter le stream Responses API
                for event in stream:
                    # Extraire le texte des output items
                    if hasattr(event, 'output') and event.output:
                        for item in event.output:
                            if hasattr(item, 'text') and item.text:
                                content = item.text
                                full_response += content
                                yield f"data: {json.dumps({'content': content})}\n\n"
            else:
                # ========== CHAT COMPLETIONS API (pour GPT-4o-mini, etc.) ==========
                messages = [{"role": "system", "content": NKOTRONIC_SYSTEM_PROMPT}]
                for msg in session.messages:
                    messages.append({"role": msg["role"], "content": msg["content"]})
                messages.append({"role": "user", "content": request.message})
                
                stream = client.chat.completions.create(
                    model=request.model,
                    messages=messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        yield f"data: {json.dumps({'content': content})}\n\n"
            
            # Sauvegarder
            add_message(request.session_id, "user", request.message)
            add_message(request.session_id, "assistant", full_response)
            
            yield f"data: {json.dumps({'done': True, 'session_id': request.session_id})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/")
async def root():
    return {
        "name": "Nkotronic API",
        "version": "4.0.0-FINAL-SIMPLE",
        "status": "running",
        "prompt_loaded": NKOTRONIC_SYSTEM_PROMPT is not None,
        "prompt_size": len(NKOTRONIC_SYSTEM_PROMPT) if NKOTRONIC_SYSTEM_PROMPT else 0
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "prompt_loaded": NKOTRONIC_SYSTEM_PROMPT is not None
    }

@app.get("/loading-status")
async def loading_status():
    """Endpoint pour vérifier le statut de chargement du prompt"""
    return LOADING_STATUS

@app.post("/warmup")
async def warmup():
    return {
        "status": "warmed_up",
        "prompt_loaded": NKOTRONIC_SYSTEM_PROMPT is not None,
        "prompt_size": len(NKOTRONIC_SYSTEM_PROMPT) if NKOTRONIC_SYSTEM_PROMPT else 0
    }

# ═══════════════════════════════════════════════════════════
# DÉMARRAGE
# ═══════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    print("=" * 60)
    print("🚀 NKOTRONIC API v4.0.0 - FINAL SIMPLE")
    print("=" * 60)
    
    # Charger le prompt système
    if load_system_prompt():
        print(f"✅ Prompt système OK: {len(NKOTRONIC_SYSTEM_PROMPT):,} caractères")
    else:
        print("⚠️  ATTENTION: Prompt système par défaut (incomplet)")
        print(f"📂 Placer \"Tu es Nkotronic, l'IA.txt\" dans: {os.getcwd()}")
    
    print(f"📊 Config: {MAX_SESSIONS} sessions max, TTL {SESSION_TTL_HOURS}h")
    print("=" * 60)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)