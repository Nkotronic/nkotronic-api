# nkotronic_api.py – Nkotronic v13-final : RAG qui marche même avec 10 Mo de manifeste
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
CHUNK_SIZE = 600
TOP_K = 7
BATCH_SIZE = 1000  # < 300k tokens garanti

app = FastAPI(title="Nkotronic v13-final – Mémoire totale + réponses en 1 seconde")

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

async def embed_batch(batch):
    """Embed un petit batch en une seule requête"""
    resp = client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
    return [e.embedding for e in resp.data]

async def charger_rag():
    global chunks, embeddings
    async with httpx.AsyncClient(timeout=60.0) as c:
        r = await c.get(MANIFESTE_URL)
        r.raise_for_status()
        manifeste = r.text.strip()
    
    chunks = split_into_chunks(manifeste)
    print(f"{len(chunks)} chunks créés → embedding par batch de {BATCH_SIZE}…")
    
    all_embeddings = []
    # on fait les embeddings en plusieurs petites requêtes
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i:i+BATCH_SIZE]
        batch_emb = await run_in_threadpool(embed_batch, batch)
        all_embeddings.extend(batch_emb)
        print(f"  → batch {i//BATCH_SIZE + 1}/{(len(chunks)-1)//BATCH_SIZE + 1} terminé")
    
    embeddings = np.array(all_embeddings)
    print(f"RAG 100% chargé : {len(chunks)} chunks prêts – Nkotronic v13-final live")

@app.on_event("startup")
async def startup():
    await charger_rag()

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str

def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    question = req.message.strip()
    q_lower = question.lower()

    mots_nko = ["nko","n'ko","ߒߞߏ","kanté","solomana","fodé","alphabet","écriture",
                "mandingue","manden","bamanankan","maninka","dyula","grammaire"]
    est_nko = any(m in q_lower for m in mots_nko) or " nko" in f" {q_lower}"

    if est_nko and embeddings is not None:
        # Embedding question
        q_emb = client.embeddings.create(input=[question], model=EMBEDDING_MODEL).data[0].embedding
        q_vec = np.array(q_emb)

        # Top K
        similarities = [cosine_sim(q_vec, emb) for emb in embeddings]
        top_indices = np.argsort(similarities)[-TOP_K:][::-1]
        context = "\n\n".join(chunks[i] for i in top_indices)

        prompt = f"""
Tu es Nkotronic, expert absolu en langue et écriture N’ko.

Passages les plus pertinents des meilleurs manuels de références :
{context}

Question : {question}

RÈGLES STRICTES :
1. Réponds UNIQUEMENT avec ces passages
2. Combine tous les faits pertinents
3. **Gras** sur tout terme en N’ko
4. Si l’info manque → "Cette information précise n’existe pas encore dans les meilleurs manuels de références sur le N’ko."
5. Sois clair, chaleureux, exhaustif

Réponds maintenant :
"""
        temperature = 0.0
    else:
        prompt = f"""Tu es Nkotronic, compagnon cultivé et chaleureux.
Question : {question}
Réponds librement avec humour et profondeur."""
        temperature = 0.7

    completion = await run_in_threadpool(
        client.chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=700
    )

    reponse = completion.choices[0].message.content.strip()
    reponse = reponse.replace("**", "")

    return ChatResponse(response=reponse)

@app.post("/reload")
async def reload():
    await charger_rag()
    return {"status": "RAG rechargé – mémoire totale à jour"}