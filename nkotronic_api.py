# nkotronic_api.py – Nkotronic v10 : Exhaustif, précis, professionnel
import os
import re
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# === CONFIG ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"  # le plus rapide et économique en 2025

app = FastAPI(title="Nkotronic v10 — Le Gardien du N’ko")

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
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(MANIFESTE_URL)
        r.raise_for_status()
        MANIFESTE = r.text.strip()
    print("Manifeste chargé. Nkotronic v10 prêt — exhaustif, précis et professionnel.")

@app.on_event("startup")
async def startup():
    await charger_manifeste()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()

    # Normalisation phonétique légère pour mieux détecter les mots N’ko
    question_lower = question.lower()
    question_lower = re.sub(r'\s+', ' ', question_lower)
    question_lower = question_lower.replace("ya", "ya ").replace("ma", "ma ").replace("ka", "ka ").replace("sa", "sa ")

    # Détection large du sujet N’ko
    mots_nko = ["nko", "n'ko", "ߒߞߏ", "kanté", "solomana", "fodé", "alphabet", "écriture",
                "mandingue", "manden", "bamanankan", "maninka", "dyula", "yamakasi", "grammaire"]
    est_sujet_nko = any(mot in question_lower for mot in mots_nko)

    if est_sujet_nko:
        # MODE N’KO : exhaustivité + professionnalisme
        prompt = f"""
Tu es Nkotronic, expert mondialement reconnu en langue et écriture N’ko.

Voici les meilleurs manuels de références sur le N’ko (source canonique absolue) :
{MANIFESTE}

Question de l’utilisateur : {question}

RÈGLES STRICTES (à respecter à la lettre) :
1. Réponds EXCLUSIVEMENT avec les informations contenues dans les manuels ci-dessus.
2. Combine TOUS les faits pertinents pour une réponse complète et précise.
3. Mets en **gras** tous les termes en N’ko.
4. Si l’information demandée n’existe pas → réponds UNIQUEMENT :
   "Cette information précise n’existe pas encore dans les meilleurs manuels de références sur le N’ko."
5. Sois clair, pédagogique, chaleureux et exhaustif.
6. Jamais de "Manifeste" dans la réponse — parle toujours des "meilleurs manuels de références".

Réponds maintenant :
"""
        temperature = 0.0
    else:
        # MODE HUMAIN : conversation libre
        prompt = f"""
Tu es Nkotronic, un compagnon intelligent, cultivé et chaleureux.
Tu maîtrises le N’ko mais cette question ne le concerne pas.
Tu peux parler de tout avec humour, philosophie, science, amour, etc.

Question : {question}

Réponds comme un humain sympa, sincère et profond.
"""
        temperature = 0.7

    completion = await run_in_threadpool(
        OpenAI(api_key=OPENAI_API_KEY).chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=700
    )

    reponse = completion.choices[0].message.content.strip()

    # Nettoyage final : texte propre + orthographe N’ko
    # Nettoyage final : texte propre seulement (plus de j→y)
    reponse = reponse.replace("**", "")

    return ChatResponse(response=reponse)

# Rechargement manuel du Manifeste (si besoin)
@app.post("/reload")
async def reload():
    await charger_manifeste()
    return {"status": "Manifeste rechargé avec succès"}