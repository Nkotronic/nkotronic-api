# nkotronic_api.py – Nkotronic v13 : RAG pour mémoire intégrale + réponses ultra-rapides (10 décembre 2025)
import os
import re
import httpx
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sklearn.metrics.pairwise import cosine_similarity  # Pour similarité simple (env a sklearn via statsmodels)

# === CONFIG ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-ada-002"  # Petit et rapide
CHUNK_SIZE = 500  # Caractères par chunk → équilibre exhaustivité/vitesse
TOP_K = 5  # Chunks les plus pertinents par requête

app = FastAPI(title="Nkotronic v13 — Mémoire intégrale + RAG rapide")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=OPENAI_API_KEY)
chunks = []  # Liste des chunks texte
embeddings = []  # Matrice numpy des embeddings

def chunk_text(text, size=CHUNK_SIZE):
    """Split texte en chunks de taille ~size"""
    return [text[i:i+size] for i in range(0, len(text), size)]

async def charger_et_preparer_rag():
    global chunks, embeddings
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(MANIFESTE_URL)
        r.raise_for_status()
        manifeste = r.text.strip()
    
    # Chunking
    chunks = chunk_text(manifeste)
    
    # Embeddings (batch pour vitesse)
    response = client.embeddings.create(input=chunks, model=EMBEDDING_MODEL)
    embeddings = np.array([emb.embedding for emb in response.data])
    
    print(f"RAG prêt : {len(chunks)} chunks embeddés → Nkotronic v13 exhaustif et rapide")

@app.on_event("startup")
async def startup():
    await charger_et_preparer_rag()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()
    question_lower = question.lower()

    mots_nko = ["nko", "n'ko", "ߒߞߏ", "kanté", "solomana", "fodé", "alphabet", "écriture",
                "mandingue", "manden", "bamanankan", "maninka", "dyula", "yamakasi", "grammaire"]
    est_sujet_nko = any(mot in question_lower for mot in mots_nko) or " n'ko" in f" {question_lower}" or " nko" in f" {question_lower}"

    if est_sujet_nko:
        # Embed query
        query_emb = client.embeddings.create(input=[question], model=EMBEDDING_MODEL).data[0].embedding
        query_emb = np.array(query_emb)
        
        # Retrieval rapide (cosine sim)
        similarities = cosine_similarity(query_emb.reshape(1, -1), embeddings)[0]
        top_indices = np.argsort(similarities)[-TOP_K:]
        relevant_chunks = "\n\n".join(chunks[i] for i in top_indices[::-1])  # Plus pertinent en premier
        
        prompt = f"""
Tu es Nkotronic, expert mondialement reconnu en langue et écriture N’ko.

Voici les extraits pertinents des meilleurs manuels de références sur le N’ko (source canonique absolue) :
{relevant_chunks}

Question de l’utilisateur : {question}

RÈGLES STRICTES (à respecter à la lettre) :
1. Réponds EXCLUSIVEMENT avec les informations contenues dans les extraits ci-dessus.
2. Combine TOUS les faits pertinents pour une réponse complète et précise.
3. Mets en **gras** tous les termes en N’ko.
4. Si l’information demandée n’existe pas dans les extraits → réponds UNIQUEMENT :
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
        client.chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=700
    )

    reponse = completion.choices[0].message.content.strip()

    # Nettoyage final
    reponse = reponse.replace("**", "")

    return ChatResponse(response=reponse)

# Rechargement manuel (ré-embed tout)
@app.post("/reload")
async def reload():
    await charger_et_preparer_rag()
    return {"status": "Mémoire RAG rechargée avec succès"}