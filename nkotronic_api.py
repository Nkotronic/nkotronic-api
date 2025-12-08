# nkotronic_api.py – Version finale (texte propre, CORS, équilibre parfait)
import os
import re
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"

app = FastAPI(title="Nkotronic v9 — Fidèle quand il faut, humain quand il peut")

# CORS pour Weebly / tout frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MANIFESTE = ""

async def charger_manifeste():
    global MANIFESTE
    async with httpx.AsyncClient() as client:
        r = await client.get(MANIFESTE_URL)
        r.raise_for_status()
        MANIFESTE = r.text.strip()
    print("Manifeste chargé. Nkotronic v9 prêt — fidèle quand il faut, humain quand il peut.")

@app.on_event("startup")
async def startup():
    await charger_manifeste()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message

    prompt = f"""
Tu es Nkotronic, un compagnon intelligent qui maîtrise parfaitement le N’ko.

Voici le **Manifeste de Connaissance N’ko actuel** (source canonique prioritaire) :
{MANIFESTE}

Question de l’utilisateur : {question}

RÈGLES D’ÉQUILIBRE :
1. Si la question concerne le N’ko → réponds UNIQUEMENT avec le Manifeste.
   - Si l’info n’y est pas → "Cette information précise n’existe pas encore dans le Manifeste de Connaissance N’ko."
   - Mets en **gras** les termes en N’ko (le modèle le fait naturellement).

2. Si la question n’a aucun lien avec le N’ko → réponds librement, comme un humain cultivé et chaleureux.

Sois naturel, sincère, et fidèle à l’esprit du projet N’ko.

Réponds maintenant :
"""

    completion = await run_in_threadpool(
        OpenAI(api_key=OPENAI_API_KEY).chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=600
    )

    reponse = completion.choices[0].message.content.strip()

    # NETTOYAGE FINAL : enlève tous les ** du Markdown → texte propre
    reponse = reponse.replace("**", "")

    return ChatResponse(response=reponse)

@app.post("/reload")
async def reload():
    await charger_manifeste()
    return {"status": "Manifeste rechargé avec succès"}