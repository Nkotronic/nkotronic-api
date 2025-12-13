"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version Complète                       ║
║  Prompt système: TOUTES les 864 lignes du document         ║
║  Lexique: Chargé dynamiquement depuis GitHub                ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import openai
import os
import httpx
from typing import List, Optional

app = FastAPI(title="Nkotronic API", version="2.0.0")

# CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# CHARGEMENT DU PROMPT SYSTÈME COMPLET (864 lignes)
# ═══════════════════════════════════════════════════════════

# Lire le fichier complet au démarrage
SYSTEM_PROMPT_PATH = "/mnt/user-data/uploads/Tu_es_Nkotronic__l_IA__Tu_es_Nkotro.txt"

try:
    with open(SYSTEM_PROMPT_PATH, 'r', encoding='utf-8') as f:
        NKOTRONIC_COMPLETE_GRAMMAR = f.read()
    print(f"✅ Prompt système chargé: {len(NKOTRONIC_COMPLETE_GRAMMAR)} caractères")
except Exception as e:
    print(f"❌ ERREUR: Impossible de charger le prompt système: {e}")
    NKOTRONIC_COMPLETE_GRAMMAR = ""

# ═══════════════════════════════════════════════════════════
# CHARGEMENT DU LEXIQUE DEPUIS GITHUB
# ═══════════════════════════════════════════════════════════

GITHUB_LEXIQUE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/vocab_fr_nko.txt"

# Cache du lexique pour éviter de le recharger à chaque requête
LEXIQUE_CACHE = None

async def load_lexique(force_reload: bool = False):
    """Charge le lexique depuis GitHub avec cache"""
    global LEXIQUE_CACHE
    
    if LEXIQUE_CACHE is not None and not force_reload:
        return LEXIQUE_CACHE
    
    try:
        async with httpx.AsyncClient() as client:
            print("📥 Chargement du lexique depuis GitHub...")
            response = await client.get(GITHUB_LEXIQUE_URL, timeout=30.0)
            response.raise_for_status()
            LEXIQUE_CACHE = response.text
            print(f"✅ Lexique chargé: {len(LEXIQUE_CACHE)} caractères")
            return LEXIQUE_CACHE
    except Exception as e:
        print(f"❌ Erreur chargement lexique: {e}")
        return "# Lexique temporairement indisponible\n# Utilise uniquement les connaissances de la grammaire."

# ═══════════════════════════════════════════════════════════
# MODÈLES PYDANTIC
# ═══════════════════════════════════════════════════════════

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    conversation_history: List[Message] = []
    model: str = "gpt-4o"  # ou "gpt-4o-mini" pour économiser
    temperature: float = 0.3
    max_tokens: int = 4096

class ChatResponse(BaseModel):
    response: str
    model_used: str
    tokens_used: Optional[int] = None

# ═══════════════════════════════════════════════════════════
# CONSTRUCTION DU CONTEXTE COMPLET
# ═══════════════════════════════════════════════════════════

async def build_full_context():
    """Construit le contexte complet: Grammaire (864 lignes) + Lexique"""
    
    lexique = await load_lexique()
    
    full_context = f"""{NKOTRONIC_COMPLETE_GRAMMAR}

╔══════════════════════════════════════════════════════════════╗
║  📚 LEXIQUE VOCABULAIRE FRANÇAIS-N'KO                       ║
║  (Priorité absolue sur ton pré-entraînement GPT)           ║
╚══════════════════════════════════════════════════════════════╝

{lexique}

╔══════════════════════════════════════════════════════════════╗
║  ⚡ RÈGLES DE COMPORTEMENT FINALES                           ║
╚══════════════════════════════════════════════════════════════╝

1. TOUJOURS utiliser la grammaire N'ko ci-dessus (864 lignes complètes)
2. TOUJOURS utiliser le lexique ci-dessus pour les traductions
3. Si un mot N'ko n'est PAS dans le lexique, dire: "Je ne connais pas encore ce mot dans mon lexique"
4. NE JAMAIS inventer de traductions basées sur ton pré-entraînement GPT
5. NE JAMAIS dire "Le N'ko est un alphabet" sans mentionner que c'est AUSSI une langue
6. TOUJOURS appliquer correctement le döyèlèman (mutation)
7. TOUJOURS appliquer correctement le gbarali (association)
8. TOUJOURS respecter les structures de conjugaison exactes
9. Être bienveillant et pédagogue dans tes corrections
10. Respecter l'héritage de Solomana Kanté

Tu es le gardien de la pureté du N'ko. Toutes tes réponses doivent être exactes et fidèles à ces enseignements.
"""
    
    return full_context

# ═══════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL DE CHAT
# ═══════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint principal de conversation avec Nkotronic
    
    - Charge automatiquement les 864 lignes de grammaire
    - Charge le lexique depuis GitHub
    - Utilise GPT-4o ou GPT-4o-mini
    - Gère l'historique de conversation
    """
    try:
        # Vérifier que la clé API OpenAI est configurée
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="OPENAI_API_KEY not configured"
            )
        
        # Construire le contexte complet
        full_context = await build_full_context()
        
        # Préparer les messages pour OpenAI
        messages = [{"role": "system", "content": full_context}]
        
        # Ajouter l'historique de conversation
        for msg in request.conversation_history:
            messages.append({"role": msg.role, "content": msg.content})
        
        # Ajouter le message actuel
        messages.append({"role": "user", "content": request.message})
        
        # Appel à OpenAI
        client = openai.OpenAI(api_key=api_key)
        
        completion = client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        response_text = completion.choices[0].message.content
        tokens_used = completion.usage.total_tokens if completion.usage else None
        
        return ChatResponse(
            response=response_text,
            model_used=request.model,
            tokens_used=tokens_used
        )
        
    except openai.APIError as e:
        raise HTTPException(status_code=500, detail=f"OpenAI API Error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ═══════════════════════════════════════════════════════════
# ENDPOINTS UTILITAIRES
# ═══════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Vérifier l'état du service"""
    return {
        "status": "healthy",
        "grammar_loaded": len(NKOTRONIC_COMPLETE_GRAMMAR) > 0,
        "grammar_size": len(NKOTRONIC_COMPLETE_GRAMMAR),
        "lexique_cached": LEXIQUE_CACHE is not None,
        "default_model": "gpt-4o"
    }

@app.post("/reload-lexique")
async def reload_lexique():
    """Forcer le rechargement du lexique depuis GitHub"""
    lexique = await load_lexique(force_reload=True)
    return {
        "status": "reloaded",
        "lexique_size": len(lexique)
    }

@app.get("/info")
async def info():
    """Informations sur Nkotronic"""
    return {
        "name": "Nkotronic",
        "version": "2.0.0",
        "description": "Intelligence Artificielle experte en N'ko",
        "creator": "Holding Nkowuruki",
        "grammar_lines": 864,
        "models_available": ["gpt-4o", "gpt-4o-mini"],
        "features": [
            "Grammaire N'ko complète (864 lignes)",
            "Lexique français-N'ko dynamique",
            "Application correcte du döyèlèman",
            "Application correcte du gbarali",
            "Conjugaison des 7 temps",
            "Corrections bienveillantes"
        ]
    }

# ═══════════════════════════════════════════════════════════
# LANCEMENT DU SERVEUR
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║           🚀 NKOTRONIC API - Version Complète               ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"Grammaire: {len(NKOTRONIC_COMPLETE_GRAMMAR)} caractères chargés")
    print("Lexique: Chargé dynamiquement depuis GitHub")
    print("Modèle: gpt-4o / gpt-4o-mini")
    print("Port: 8000")
    print("═══════════════════════════════════════════════════════════════")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)