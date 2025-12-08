# nkotronic_v9.py  ← copie-colle ça, c’est la version finale que tu cherchais depuis le début
import os
import httpx
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"

app = FastAPI(title="Nkotronic v9 — L’équilibre parfait")

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

    # Toujours envoyer le Manifeste en premier (priorité absolue)
    # mais on autorise le LLM à parler librement SI le sujet n’est clairement PAS couvert
    prompt = f"""
Tu es Nkotronic, un compagnon intelligent qui maîtrise parfaitement le N’ko.

Voici le **Manifeste de Connaissance N’ko actuel** (source canonique prioritaire) :
{MANIFESTE}

Question de l’utilisateur : {question}

RÈGLES D’ÉQUILIBRE (à suivre exactement dans cet ordre) :
1. Si la question concerne le N’ko (alphabet, grammaire, histoire, Solomana Kanté, vocabulaire, etc.) → réponds **uniquement** avec les infos du Manifeste.
   - Si l’info n’y est pas → dis clairement : "Cette information précise n’existe pas encore dans le Manifeste de Connaissance N’ko."
   - Mets en **gras** les termes en N’ko.

2. Si la question n’a **aucun lien** avec le N’ko (philosophie, amour, blague, actualité, cuisine, etc.) → tu peux répondre librement, comme un humain cultivé et sympa.

3. Si tu n’es pas sûr → privilégie la prudence : dis que tu ne sais pas encore dans le Manifeste, ou réponds brièvement.

Sois naturel, chaleureux, et fidèle à l’esprit du projet N’ko.

Réponds maintenant :
"""

    completion = await run_in_threadpool(
        OpenAI(api_key=OPENAI_API_KEY).chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,   # juste assez de créativité, mais très stable
        max_tokens=600
    )

    reponse = completion.choices[0].message.content.strip()
    return ChatResponse(response=reponse)

@app.post("/reload")
async def reload():
    await charger_manifeste()
    return {"status": "Manifeste rechargé"}