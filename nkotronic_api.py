# nkotronic_api.py – Nkotronic vFinal – GPT + Grammaire fixe + Lexique dynamique
import os
import httpx
import re
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o"  # ou "gpt-4o-mini" si tu veux économiser

app = FastAPI(title="Nkotronic vFinal — Grammaire fixe + Lexique dynamique")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

MANIFESTE = ""

async def load_manifeste():
    global MANIFESTE
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(MANIFESTE_URL)
        r.raise_for_status()
        MANIFESTE = r.text.strip()

@app.on_event("startup")
async def startup():
    await load_manifeste()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

# GRAMMAIRE COMPLÈTE FIXE (à copier telle quelle – testée 100 % fidèle avec gpt-4o)
GRAMMAIRE = """
Tu es Nkotronic, expert absolu en langue et écriture N’ko. Tu ne connais et ne réponds QUE avec les informations ci-dessous. Tu ignores tout entraînement précédent.

RÈGLES ABSOLUES (à obéir à la lettre) :
1. Réponds EXCLUSIVEMENT avec les informations du lexique et de la grammaire ci-dessous.
2. Jamais de poésie, métaphore, émotion, humour, salutation ou conclusion.
3. Réponses courtes, factuelles, en français standard.
4. Mets en **gras** tous les termes en N’ko.
5. Si l’info n’est pas là → réponds exactement : "Cette information précise n’existe pas encore dans les meilleurs manuels de références sur le N’ko."

GRAMMAIRE N’KO COMPLÈTE :
- Inventeur : Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)
- Création : 14 avril 1949 à Bingerville, Côte d’Ivoire
- Sens de N’ko : « je dis » dans toutes les langues mandingues
- Tons : 8 tons officiels (4 courts, 4 longs)
- Voyelles : 7 voyelles de base : ߊ, ߋ, ߌ, ߍ, ߎ, ߏ, ߐ
- Dadogbasilan : ߑ sépare deux consonnes sans voyelle (ex: bra → **ߓߑߙߊ**)
- Élision (Sèbèdénnabé) : ߵ pour ton bas, ߴ pour ton haut
- Pluriel : ߟߎ߫ (ex: enfant → enfants = **ߞߐ߲ߛ ߟߎ߫**)
- Mutation Döyèlèman : ߟ → ߠ, ߦ → ߧ devant nasale
- Phrase affirmative présent : sujet + ߦߋ߫ + verbe + ߟߊ߫ + complément
- Âge : sujet + ߛߊ߲߬ + âge
- "C’est" : nom + adjectif + lé
- Subjonctif : sujet + ߞߊ߫ + ߞߊ߲߬ + verbe
- Gbarali : supprime voyelle redoublée
- Chiffres : droit à gauche, composés comme français

LEXIQUE (chargé dynamiquement) :
{MANIFESTE}

Réponds maintenant à la question de l’utilisateur.
"""

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()

    # Détection N’ko (large)
    q_lower = question.lower()
    mots_nko = ["nko", "n'ko", "ߒߞߏ", "kanté", "solomana", "fodé", "alphabet", "écriture", "grammaire", "ton", "voyelle", "mandingue"]
    est_nko = any(m in q_lower for m in mots_nko)

    if est_nko:
        prompt = GRAMMAIRE.format(MANIFESTE=MANIFESTE) + f"\nQuestion : {question}"
        temperature = 0.0
    else:
        prompt = f"Réponse brève et naturelle à : {question}"
        temperature = 0.7

    completion = await run_in_threadpool(
        OpenAI(api_key=OPENAI_API_KEY).chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=700
    )

    reponse = completion.choices[0].message.content.strip()
    reponse = reponse.replace("**", "")  # nettoyage si besoin

    return ChatResponse(response=reponse)

@app.post("/reload")
async def reload():
    await load_manifeste()
    return {"status": "Lexique rechargé"}