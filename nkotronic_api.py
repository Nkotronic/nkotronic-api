# nkotronic_api.py – Nkotronic v11 : Stable, exhaustif, anti-429, zéro hallucination (10 décembre 2025)
import os
import re
import time
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI, RateLimitError
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# === CONFIG ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"

app = FastAPI(title="Nkotronic v11 — Le Gardien du N’ko")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cache du manifeste (rafraîchi toutes les 45 s max)
manifeste_cache = {"content": "", "last_fetch": 0}
CACHE_TTL = 45  # secondes

# Client OpenAI unique
client = OpenAI(api_key=OPENAI_API_KEY)

# Détection N’ko ultra-robuste
mots_nko = [
    "nko", "n'ko", "ߒߞߏ", "ߣߞߐ", "ߞߊ߲ߡߊ", "ߞߊ߲ߝߍ",
    "solomana", "souleymane", "kanté", "kante", "fodé", "fodeba",
    "alphabet", "écriture", "lettres", "tons", "tonalités", "diacritique",
    "manding", "manden", "bamanan", "bambara", "manink", "dyula", "dioula", "julakan",
    "ߓߊߡߊߣߊ߲", "ߡߊ߲߬ߘߋ", "ߘߌ߯ߟߊ", "ߛߏߡߊ߲߬"
]

regex_en_nko = re.compile(r"\ben\s+(n'?ko|nko)\b", re.IGNORECASE)

def est_sujet_nko(texte: str) -> bool:
    texte = texte.lower()
    if any(mot in texte for mot in mots_nko):
        return True
    if regex_en_nko.search(texte):
        return True
    # Phonétique mandingue légère (attrape "i ni ce", "aw ni wula", etc.)
    if re.search(r"\b(a|i|u|e|o|ɔ|ɛ|an|in|un|en|on)\b", texte):
        if re.search(r"\b(ni|ce|sogoma|wula|tile|tɔn|djö|djo|ce)\b", texte):
            return True
    return False

async def get_manifeste() -> str:
    global manifeste_cache
    now = time.time()
    if now - manifeste_cache["last_fetch"] > CACHE_TTL or not manifeste_cache["content"]:
        async with httpx.AsyncClient(timeout=15.0) as c:
            try:
                r = await c.get(MANIFESTE_URL)
                r.raise_for_status()
                manifeste_cache["content"] = r.text.strip()
                manifeste_cache["last_fetch"] = now
                print(f"Manifeste rafraîchi — {len(manifeste_cache['content'])} caractères")
            except Exception as e:
                if not manifeste_cache["content"]:
                    raise e
                print(f"Échec refresh, on garde l’ancien ({e})")
    return manifeste_cache["content"]

def nettoyer_reponse(texte: str, mode_nko: bool) -> str:
    texte = texte.strip()
    # Supprime les ** résiduels
    texte = texte.replace("**", "")
    if mode_nko:
        # Force le gras sur tout ce qui est en N’ko (tout ce qui contient des caractères ߀-߿)
        texte = re.sub(r"([߀-߿]+)", r"**\1**", texte)
        # Nettoyage léger des espaces autour du gras
        texte = texte.replace(" **", " ").replace("** ", " ")
    return texte

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.on_event("startup")
async def startup():
    await get_manifeste()
    print("Nkotronic v11 prêt — exhaustif, stable et professionnel")

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()
    question_lower = question.lower()

    mode_nko = est_sujet_nko(question_lower)

    manifeste = await get_manifeste()

    if mode_nko:
        prompt = f"""Tu es Nkotronic, expert mondialement reconnu en langue et écriture N’ko.

Voici les meilleurs manuels de références sur le N’ko (source canonique absolue) :
{manifeste}

Question de l’utilisateur : {question}

RÈGLES STRICTES :
1. Réponds EXCLUSIVEMENT avec les informations contenues dans les manuels ci-dessus.
2. Combine TOUS les faits pertinents pour une réponse complète et précise.
3. Mets en gras tous les termes et seulement les termes en N’ko (ex. **ߒߞߏ**).
4. Si l’information demandée n’existe pas → réponds UNIQUEMENT :
   "Cette information précise n’existe pas encore dans les meilleurs manuels de références sur le N’ko."
5. Sois clair, pédagogique, chaleureux et exhaustif.
6. Jamais le mot "Manifeste" dans la réponse.

Réponds maintenant en français standard :"""
        temperature = 0.0
        max_tokens = 600
    else:
        prompt = f"""Tu es Nkotronic, un compagnon intelligent, cultivé et chaleureux.
Cette question ne concerne pas le N’ko. Tu peux parler librement avec humour, philosophie, science, amour, etc.

Question : {question}

Réponds comme un humain sympa, sincère et profond en français standard."""
        temperature = 0.7
        max_tokens = 500

    try:
        completion = await run_in_threadpool(
            client.chat.completions.create,
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens
        )
        reponse = completion.choices[0].message.content.strip()

    except RateLimitError:
        reponse = "Désolé, trop de demandes simultanées en ce moment. Réessaie dans quelques secondes, je suis toujours là !"
    except Exception as e:
        reponse = "Une petite erreur technique est survenue. Je reviens dans un instant !"

    reponse_finale = nettoyer_reponse(reponse, mode_nko)

    return ChatResponse(response=reponse_finale)

@app.post("/reload")
async def reload():
    await get_manifeste()
    return {"status": "Manifeste rechargé avec succès"}