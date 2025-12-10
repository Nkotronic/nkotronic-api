# nkotronic_api.py – Nkotronic v14 : Sherlock Mode – Mémoire totale + réponses factuelles instantanées
import os
import httpx
import numpy as np
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware

# ========================= CONFIG =========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MANIFESTE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/NKOTRONIC_KNOWLEDGE"
MODEL = "gpt-4o-mini-2024-07-18"
EMBEDDING_MODEL = "text-embedding-ada-002"
CHUNK_SIZE = 700
TOP_K = 8
BATCH_SIZE = 800

app = FastAPI(title="Nkotronic v14 – Sherlock Mode")

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

# ========================= UTILITAIRES =========================
def split_chunks(text):
    return [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]

async def embed_batch(batch):
    resp = client.embeddings.create(input=batch, model=EMBEDDING_MODEL)
    return [e.embedding for e in resp.data]

async def load_rag():
    global chunks, embeddings
    async with httpx.AsyncClient() as c:
        r = await c.get(MANIFESTE_URL)
        r.raise_for_status()
        text = r.text.strip()

    chunks = split_chunks(text)
    print(f"{len(chunks)} chunks créés → embedding en cours…")

    all_emb = []
    for i in range(0, len(chunks), BATCH_SIZE):
        all_emb.extend(await embed_batch(chunks[i:i+BATCH_SIZE]))
    embeddings = np.array(all_emb)
    print("Nkotronic v14 chargé – mémoire 100 % – mode Sherlock activé")

@app.on_event("startup")
async def startup():
    await load_rag()

# ========================= MODELES =========================
class Msg(BaseModel):
    message: str

class Rep(BaseModel):
    response: str

# ========================= SIMILARITÉ =========================
def cos_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

# ========================= ROUTE CHAT =========================
@app.post("/chat", response_model=Rep)
async def chat(req: Msg):
    q = req.message.strip().lower()

    # Détection N’ko très large
    keywords = ["nko","n'ko","ߒߞߏ","kanté","solomana","fodé","ߞߊ߲","ߡߊ߲߬ߘߋ","ߘߌ߯ߟߊ","ton","voyelle","grammaire","alphabet","écriture"]
    if any(k in q for k in keywords):
        # RAG
        q_emb = np.array(client.embeddings.create(input=[req.message], model=EMBEDDING_MODEL).data[0].embedding)
        sims = [cos_sim(q_emb, e) for e in embeddings]
        top_idx = np.argsort(sims)[-TOP_K:][::-1]
        context = "\n\n".join(chunks[i] for i in top_idx)

        prompt = f"""Tu es Nkotronic, intelligence analytique spécialisée N’ko.
Réponds exclusivement à partir des extraits suivants, sans métaphore ni émotion.

Extraits :
{context}

Question : {req.message}

Réponse factuelle uniquement."""
        temp = 0.0
    else:
        prompt = f"Réponse brève et factuelle : {req.message}"
        temp = 0.0

    completion = await run_in_threadpool(
        client.chat.completions.create,
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temp,
        max_tokens=500
    )

    answer = completion.choices[0].message.content.strip()
    answer = answer.replace("**", "")

    return Rep(response=answer)

# ========================= RELOAD =========================
@app.post("/reload")
async def reload():
    await load_rag()
    return {"status": "Mémoire rechargée – 100 % à jour"}