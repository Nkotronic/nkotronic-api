# nkotronic_api.py – Nko Wuruki FIXED (11 décembre 2025)
import os
from fastapi import FastAPI
from pydantic import BaseModel
from openai import OpenAI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Nko Wuruki – Parfait")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

client = OpenAI(
    base_url="https://api.fireworks.ai/inference/v1",
    api_key=os.getenv("FIREWORKS_API_KEY")
)

# REMPLACE PAR TON ID EXACT (ex: accounts/nkowuruki-nkotronic/deployments/1093in)
MODEL = "accounts/nkowuruki-nkotronic/deployedModels/llama-v3-8b-instruct-ujhovgli"  # MET L'ID PRÉCIS ICI

class Msg(BaseModel):
    message: str

@app.post("/chat")
async def chat(m: Msg):
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": m.message}],
            temperature=0.0,
            max_tokens=1000
        )
        return {"response": resp.choices[0].message.content.strip()}
    except Exception as e:
        return {"error": str(e)}  # pour debug

@app.get("/")
async def root():
    return {"message": "Nko Wuruki est prêt – Alu ni djö !"}