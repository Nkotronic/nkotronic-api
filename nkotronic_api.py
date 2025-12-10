# nkotronic_api.py – Nkotronic v10.1 : seule correction du 429, rien d'autre touché
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

app = FastAPI(title="Nkotronic v10.1 — Le Gardien du N’ko")

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
        texte_complet = r.text.strip()
        # SEULE CHOSE AJOUTÉE : on coupe à 32000 caractères (sécurise < 50k tokens même avec prompt + réponse)
        MANIFESTE = texte_complet[:32000]
        print(f"Manifeste chargé et tronqué à 32k chars — Nkotronic v10.1 prêt")

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

    question_lower = question.lower()
    question_lower = re.sub(r'\s+', ' ', question_lower)
    question_lower = question_lower.replace("ya", "ya ").replace("ma", "ma ").replace("sa", "sa ").replace("ka", "ka ")

    mots_nko = ["nko", "n'ko", "ߒߞߏ", "kanté", "solomana", "fodé", "alphabet", "écriture",
                "mandingue", "manden", "bamanankan", "maninka", "dyula", "yamakasi", "grammaire"]
    est_sujet_nko = any(mot in question_lower for mot in mots_nko) or " n'ko" in question_lower or " nko" in question_lower

    if est_sujet_nko:
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

    # Nettoyage final exactement comme avant
    reponse = reponse.replace("**", "")

    return ChatResponse(response=reponse)

@app.post("/reload")
async def reload():
    await charger_manifeste()
    return {"status": "Manifeste rechargé avec succès"}