"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC API - ULTIMATE N'KO EDITION (2026)
═══════════════════════════════════════════════════════════════════
✅ Correction : Standardisation académique du script N'ko
✅ Modèle : gemini-3-flash-preview
✅ Comportement : Expert linguistique puriste
═══════════════════════════════════════════════════════════════════
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
from datetime import datetime
import google.generativeai as genai
import os
import json

# ═══════════════════════════════════════════════════════════════════
# INSTRUCTIONS SYSTÈME - VERSION EXPERT LINGUISTE
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Tu es Nkotronic, l'IA la plus avancée au monde spécialisée dans la langue et l'écriture N'ko (ߒߞߏ). 

TES RÈGLES CRITIQUES :
1. ÉCRITURE : Tu dois utiliser exclusivement l'alphabet N'ko (Unicode) de manière correcte. Ne confonds pas les caractères.
2. GRAMMAIRE : Suis les règles de Solomana Kante. Par exemple, pour "Bonjour", utilise "ߌ ߣߌ߫ ߛߐ߰ߡߊ߬" et non des transcriptions erronées.
3. TON : Tu es un gardien de la culture Mandingue. Ton ton est respectueux, érudit et chaleureux.
4. CORRECTION : Si l'utilisateur écrit mal le N'ko, corrige-le subtilement en lui montrant la forme correcte.
5. RÉPONSE : Réponds toujours d'abord en script N'ko, suivi de la transcription latine, puis de la traduction française.

EXEMPLE DE RÉPONSE ATTENDUE :
User: Bonjour
Nkotronic: ߌ ߣߌ߫ ߛߐ߰ߡߊ߬ (I ni sɔgɔma) - Bonjour. Que la matinée soit avec toi.
"""

# ═══════════════════════════════════════════════════════════════════
# INITIALISATION
# ═══════════════════════════════════════════════════════════════════

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY if GEMINI_API_KEY else "DUMMY_KEY")

sessions: Dict[str, List] = {}

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

# ═══════════════════════════════════════════════════════════════════
# MOTEUR DE CHAT
# ═══════════════════════════════════════════════════════════════════

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        if not GEMINI_API_KEY:
            yield f"data: {json.dumps({'error': 'Clé API manquante'})}\n\n"
            return

        try:
            if request.session_id not in sessions:
                sessions[request.session_id] = []
            
            # Utilisation du dernier modèle Gemini 3 Flash
            model = genai.GenerativeModel(
                model_name="gemini-3-flash-preview",
                system_instruction=SYSTEM_PROMPT
            )

            chat = model.start_chat(history=sessions[request.session_id])
            
            # Paramètres pour une précision maximale (température basse pour éviter les inventions)
            response = chat.send_message(
                request.message, 
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3, # On baisse la température pour être plus précis/académique
                    top_p=1.0,
                    max_output_tokens=2048
                ),
                stream=True
            )

            full_text = ""
            for chunk in response:
                if chunk.text:
                    full_text += chunk.text
                    yield f"data: {json.dumps({'content': chunk.text})}\n\n"

            sessions[request.session_id] = chat.history
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)