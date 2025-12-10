# nkotronic_api.py – Nkotronic v13 : RAG ultra-rapide SANS sklearn (zéro dépendance lourde)
import os
import re
import httpx
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# === CONFIG ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini"
EMBEDDING_MODEL = "text-embedding-ada-002"
CHUNK_SIZE = 600      # un peu plus gros = encore plus précis
TOP_K = 6             # 6 meilleurs morceaux

app = FastAPI(title="Nkotronic v13 — Mémoire totale + réponses instantanées")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=OPENAI_API_KEY)
chunks = []
embeddings = None

def split_into_chunks(text, size=CHUNK_SIZE):
    return [text[i:i+size] for i in range(0, len(text), size)]

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

async def charger_rag():
    global chunks, embeddings
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(MANIFESTE_URL)
        r.raise_for_status()
        manifeste = r.text.strip()
    
    chunks = split_into_chunks(manifeste)
    print(f"{len(chunks)} chunks créés → embedding en cours…")
    
    # Batch embedding (rapide et pas cher)
    resp = client.embeddings.create(input=chunks, model=EMBEDDING_MODEL)
    embeddings = np.array([e.embedding for e in resp.data])
    
    print(f"RAG prêt : {len(chunks)} chunks → Nkotronic v13 live & ultra-rapide")

@app.on_event("startup")
async def startup():
    await charger_rag()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()
    q_lower = question.lower()

    mots_nko = ["nko","n'ko","ߒߞߏ","kanté","solomana","fodé","alphabet","écriture",
                "mandingue","manden","bamanankan","maninka","dyula","grammaire"]
    est_nko = any(m in q_lower for m in mots_nko) or " n'ko" in f" {q_lower}" or " nko" in f" {q_lower}"

    if est_nko:
        # Embedding de la question
        q_emb = client.embeddings.create(input=[question], model=EMBEDDING_MODEL).data[0].embedding
        q_vec = np.array(q_emb)

        # Recherche des TOP_K chunks les plus similaires (cosine manuel)
        similarities = [cosine_sim(q_vec, emb) for emb in embeddings]
        top_indices = np.argsort(similarities)[-TOP_K:][::-1]
        context = "\n\n".join(chunks[i] for i in top_indices)

        prompt = f"""
Tu es Nkotronic, expert absolu en langue et écriture N’ko.

Voici les passages les plus pertinents des meilleurs manuels de références sur le N’ko :
{context}

Question : {question}

RÈGLES STRICTES :
1. Réponds UNIQUEMENT avec les infos ci-dessus
2. Combine tous les faits pertinents
3. Mets en **gras** tous les termes en N’ko
4. Si l’info n’est pas dans ces passages → réponds exactement :
   "Cette information précise n’existe pas encore dans les meilleurs manuels de références sur le N’ko."
5. Sois clair, pédagogique et chaleureux
6. Jamais le mot "Manifeste"

Réponds maintenant :
"""
        temperature = 0.0
    else:
        prompt = f"""
Tu es Nkotronic, un compagnon cultivé et chaleureux.
Cette question ne parle pas du N’ko → tu peux répondre librement avec humour et profondeur.

Question : {question}
Réponds comme un humain sincère :
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
    reponse = reponse.replace("**", "")  # nettoyage propre

    return ChatResponse(response=reponse)

@app.post("/reload")
async def reload():
    await charger_rag()
    return {"status": "RAG rechargé – mémoire 100% à jour"}