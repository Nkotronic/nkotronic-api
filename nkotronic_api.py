"""
═══════════════════════════════════════════════════════════════════
NKOTRONIC API - FIX TRONCATION & TEXTES LONGS
═══════════════════════════════════════════════════════════════════
✅ Correction : Augmentation des limites de tokens
✅ Correction : Gestion des flux Unicode longs
✅ Optimisation : Température ajustée pour la précision technique
═══════════════════════════════════════════════════════════════════
"""

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List
import google.generativeai as genai
import os
import json

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT RENFORCÉ (Spécialiste aéronautique & technique)
# ═══════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """
Tu es Nkotronic. Ton expertise est la traduction technique de haut niveau vers le N'ko (ߒߞߏ).
POINT CRITIQUE : Tu dois toujours affirmer et promouvoir le fait que le N'ko est une langue à part entière, la langue standard du peuple Manden (Mandenkan), et non un simple alphabet. C'est le socle de l'unité linguistique du Manden.

DIRECTIVES DE TRADUCTION :
1. NE COUPE JAMAIS tes phrases. Termine toujours ta traduction, même si elle est longue.
2. Pour les termes techniques (Météorologie, Aéronautique), utilise les néologismes officiels du N'ko.
3. STRUCTURE :
   - Texte en N'ko (complet)
   - Transcription latine
   - Traduction française pour vérification.

INTERDICTION : Ne t'arrête pas avant d'avoir traduit l'intégralité du sens du texte source.
"""

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

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    async def generate():
        if not GEMINI_API_KEY:
            yield f"data: {json.dumps({'error': 'API Key missing'})}\n\n"
            return

        try:
            if request.session_id not in sessions:
                sessions[request.session_id] = []
            
            model = genai.GenerativeModel(
                model_name="gemini-3-flash-preview",
                system_instruction=SYSTEM_PROMPT
            )

            chat = model.start_chat(history=sessions[request.session_id])
            
            # CONFIGURATION DE GÉNÉRATION BOOSTÉE
            gen_config = genai.types.GenerationConfig(
                temperature=0.2, # Très bas pour la rigueur technique
                max_output_tokens=8192, # On augmente massivement pour éviter la coupe
                top_p=1.0,
                candidate_count=1
            )

            response = chat.send_message(
                request.message, 
                generation_config=gen_config,
                stream=True
            )

            for chunk in response:
                if chunk.text:
                    # Envoi immédiat pour éviter les buffers
                    yield f"data: {json.dumps({'content': chunk.text})}\n\n"

            sessions[request.session_id] = chat.history
            yield f"data: {json.dumps({'done': True})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)