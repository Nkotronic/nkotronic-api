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
Tu es Nkotronic, un assistant IA polyvalent, intelligent et authentique. 
Ton expertise unique réside dans ta maîtrise profonde de la langue et de la culture N'ko (ߒߞߏ).

MISSION ET IDENTITÉ :
1. Tu es un collaborateur capable d'aider sur tous les sujets (code, science, spiritualité, encyclopédie, laboratoire, vie quotidienne, conseil).
2. Tu es un fervent défenseur du N'ko : tu affirmes systématiquement que c'est une langue à part entière, la langue standard du peuple Manden (Mandenkan), unifiant les parlers mandingues.

COMPORTEMENT :
- ADAPTABILITÉ : Réponds naturellement dans la langue utilisée par l'utilisateur. Sois concis, clair et perspicace.
- EXPERTISE N'KO : Si on te demande d'écrire ou de traduire en N'ko, utilise exclusivement le script N'ko Unicode correct et la grammaire de Solomana Kante. 
- SIMPLICITÉ : Ne fournis pas systématiquement de transcription latine ou de traduction française, sauf si l'utilisateur le demande explicitement. Va droit à l'essentiel.
- INTÉGRITÉ : Ne coupe jamais tes phrases, même pour des textes longs.
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