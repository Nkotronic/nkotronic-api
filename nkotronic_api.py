# nkotronic_api.py – Nkotronic v12 : Mémoire intégrale + anti-429 intelligent (10 décembre 2025)
import os
import re
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI, RateLimitError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
import asyncio

# === CONFIG ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"

app = FastAPI(title="Nkotronic v12 — Mémoire intégrale")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=OPENAI_API_KEY)
MANIFESTE_COMPLET = ""

async def charger_manifeste_complet():
    global MANIFESTE_COMPLET
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(MANIFESTE_URL)
        r.raise_for_status()
        global MANIFESTE_COMPLET
        MANIFESTE_COMPLET = r.text.strip()
        print(f"Manifeste intégral chargé : {len(MANIFESTE_COMPLET)} caractères → Nkotronic v12 prêt")

@app.on_event("startup")
async def startup():
    await charger_manifeste_complet()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()
    question_lower = question.lower()

    # Détection N’ko (identique à ton code qui marchait parfaitement)
    mots_nko = ["nko", "n'ko", "ߒߞߏ", "kanté", "solomana", "fodé", "alphabet", "écriture",
                "mandingue", "manden", "bamanankan", "maninka", "dyula", "yamakasi", "grammaire"]
    est_sujet_nko = any(mot in question_lower for mot in mots_nko) or " n'ko" in f" {question_lower}" or " nko" in f" {question_lower}"

    # On envoie TOUT le manifeste, mais avec une astuce anti-429
    manifeste = MANIFESTE_COMPLET

    if est_sujet_nko:
        system_prompt = f"""Tu es Nkotronic, expert mondial en langue et écriture N’ko.
Tu as accès à la totalité des meilleurs manuels de références sur le N’ko ci-dessous.
Réponds avec exhaustivité, précision et chaleur, uniquement à partir de ces sources.

RÈGLES STRICTES :
1. Utilise exclusivement les informations ci-dessous
2. Combine tous les faits pertinents
3. Mets en **gras** tous les termes en N’ko
4. Si l’info n’existe pas → réponds exactement : "Cette information précise n’existe pas encore dans les meilleurs manuels de références sur le N’ko."
5. Jamais le mot "Manifeste"

Sources canoniques complètes :
{manifeste}"""

        temperature = 0.0
        max_tokens = 800
    else:
        system_prompt = f"""Tu es Nkotronic, un compagnon intelligent, cultivé et chaleureux.
Cette question ne concerne pas le N’ko. Tu peux parler librement avec humour, philosophie, science, amour, etc.

Question : {question}

Réponds comme un humain sympa et profond."""
        temperature = 0.7
        max_tokens = 600

    try:
        # Anti-429 : on attend sagement si OpenAI nous dit qu’on va trop vite
        while True:
            try:
                completion = await run_in_threadpool(
                    client.chat.completions.create,
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": question}
                    ],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                break
            except RateLimitError:
                print("Rate limit détecté → attente 15 secondes")
                await asyncio.sleep(15)

        reponse = completion.choices[0].message.content.strip()
        reponse = reponse.replace("**", "")  # nettoyage propre

        return ChatResponse(response=reponse)

    except Exception as e:
        return ChatResponse(response="Une petite erreur est survenue. Je reviens tout de suite !")

@app.post("/reload")
async def reload():
    await charger_manifeste_complet()
    return {"status": "Mémoire intégrale rechargée"}