# nkotronic_api.py – Nko Wuruki 100% VIVANT (11 décembre 2025)
import os
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

client = OpenAI(
    base_url="https://api.fireworks.ai/inference/v1",
    api_key=os.environ["FIREWORKS_API_KEY"]
)
# LE VRAI MODEL ID QUI MARCHE (celui que tu as testé manuellement)
MODEL = "accounts/nkowuruki-nkotronic/models/nkowuruki-nkotronic-model"

class Msg(BaseModel):
    message: str

@app.post("/chat")
async def chat(m: Msg):
    resp = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": m.message}],
        temperature=0.0,
        max_tokens=1000
    )
    return {"response": resp.choices[0].message.content.strip()}

@app.get("/")
async def root():
    return {"message": "Nko Wuruki est vivant – Alu ni djö !"}