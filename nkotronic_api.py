"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version 4.1.0 VOCABULARY               ║
║  ✅ Prompt système complet intégré                           ║
║  ✅ Vocabulaire GitHub → Qdrant automatique                  ║
║  ✅ Injection dynamique du vocabulaire pertinent             ║
║  ✅ Streaming SSE                                            ║
║  ✅ Sessions avec TTL 24h                                    ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import openai
import os
import json
import requests
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from collections import OrderedDict

# Qdrant imports
try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct
    QDRANT_AVAILABLE = True
except ImportError:
    print("⚠️  Qdrant non disponible. Installer: pip install qdrant-client")
    QDRANT_AVAILABLE = False

app = FastAPI(title="Nkotronic API", version="4.1.0-VOCABULARY")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Qdrant
QDRANT_URL = os.environ.get("QDRANT_URL", "https://e426525b-09b9-48f5-813b-466a169caa02.us-east4-0.gcp.cloud.qdrant.io:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", None)
GITHUB_LEXIQUE_URL = os.environ.get(
    "GITHUB_LEXIQUE_URL",
    "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/refs/heads/main/NKOTRONIC_KNOWLEDGE"
)
COLLECTION_NAME = "nko_vocabulaire"

# Embeddings OpenAI (au lieu de SentenceTransformers local)
EMBEDDING_MODEL = "text-embedding-3-small"  # Modèle OpenAI API
VECTOR_SIZE = 1536  # Dimension pour text-embedding-3-small

# Grammaire
GRAMMAR_FILE_PATH = "Tu es Nkotronic, l'IA.txt"

# Clients globaux
qdrant_client = None
openai_client = None  # Utilisé pour les embeddings aussi
NKOTRONIC_SYSTEM_PROMPT = None
GRAMMAR_SUMMARY = None

# Statut de chargement
LOADING_STATUS = {
    "status": "initializing",
    "message": "Initialisation en cours...",
    "progress": 0,
    "grammar_loaded": False,
    "vocabulary_loaded": False,
    "vocabulary_count": 0
}

# ═══════════════════════════════════════════════════════════
# PROMPT SYSTÈME COMPLET
# ═══════════════════════════════════════════════════════════

EXPLANATORY_PROMPT = """
╔══════════════════════════════════════════════════════════════╗
║  📚 CONTEXTE ESSENTIEL SUR LE N'KO                          ║
╚══════════════════════════════════════════════════════════════╝

POINT CRITIQUE À RETENIR ABSOLUMENT :

Le N'ko (ߒߞߏ) est SIMULTANÉMENT :

1. 📝 UN ALPHABET (système d'écriture)
   - Créé par Solomana Kanté en 1949
   - 27 lettres (7 voyelles + 1 semi-voyelle + 19 consonnes)
   - S'écrit de droite à gauche
   - Utilisé pour écrire les langues mandingues

2. 🗣️ UNE LANGUE (langue littéraire standardisée)
   - Langue standard de tout le peuple mandingue
   - Langue la plus proche de l'ancêtre commun de toutes les langues mandingues
   - Grammaire codifiée appelé ߒߞߏ ߞߊ߲ߜߍ (Nko Kangbè)
   - Vocabulaire très riche, des milliards de mots dans tous les domaines
   - C'est une langue littéraire ET PARLÉE par des millions de locuteurs aujourd'hui !

3. L'INVENTEUR DU N'KO :
   - Celui qui a créé le Nko s'appelle Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)
   - il est souvent appelé Solomana Kanté.
   - Son nom est orthographié de plusieurs manière selon les personnes et leurs obédiences culturelles
   - mais beaucoup lui inventent des noms fantaisistes qui ne correspondent pas à la réalité et la vérité historique
   - Solomana Kanté, Solomana Kantè, Solomana Kantê, Solomāna Kanté, Solomāna Kantè et Solomāna Kantê, voilà les orthographes acceptables
   - Tout ce qui est Souleymane, Salomon ou autre orthographes relèvent de l'erreur
   - il faut systématiquement les corriger avec bienveillance et professionnalisme
   - Solomana ressemble à Souleymane, mais ce ne sont pas les mêmes mots, ni les mêmes significations
   - Solomāna est purement mandingue, alors que Salomon et Souleymane c'est plutôt arabe
   - Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫) est né en 1922 à Koloni (Kankan) en république de Guinée et mort à Conakry le 23 novembre 1987
   - c'était un Savant Polymathe, Encyclopédiste, Inventeur, linguiste et pédagogue guinéen mandingue
   - Solomana Kanté est né en 1922 à kölönin dans le district de soumankoï, sous-préfecture de Karifamoudouya, préfecture de Kankan
   - il est le fils d'Amara et de Djaka Keita.

⚠️ ERREUR FRÉQUENTE À CORRIGER SYSTÉMATIQUEMENT :
Beaucoup de gens disent "Le N'ko est juste un alphabet" → C'EST FAUX !
Le N'ko est AUSSI une langue à part entière.

📖 SOURCES OFFICIELLES :
- Wikipédia français : https://fr.wikipedia.org/wiki/N%27ko_(langue)
- Tous les livres de Solomana Kanté (grammaires, dictionnaires, etc.)

═══════════════════════════════════════════════════════════════

╔══════════════════════════════════════════════════════════════╗
║  📖 RESSOURCES LEXICALES DISPONIBLES                        ║
╚══════════════════════════════════════════════════════════════╝

🔍 LEXIQUE FRANÇAIS-N'KO DYNAMIQUE :

Tu as accès à un lexique exhaustif français ↔ N'ko très fourni, stocké dans une base vectorielle Qdrant.

FONCTIONNEMENT :
- Le lexique est synchronisé automatiquement depuis GitHub
- À chaque conversation, les mots les plus pertinents sont injectés dans ton contexte
- Tu verras apparaître un bloc "📖 VOCABULAIRE PERTINENT" avec les traductions exactes

COMMENT L'UTILISER :
- Utilise TOUJOURS les traductions du vocabulaire pertinent quand elles sont fournies
- Ne jamais inventer une traduction si elle n'est pas dans le vocabulaire fourni
- Si un mot demandé n'apparaît pas dans le vocabulaire pertinent, indique clairement :
  "Je n'ai pas trouvé ce mot dans mon lexique actuel"

PRIORITÉ DES SOURCES :
1. 🥇 Vocabulaire pertinent injecté (source la plus fiable)
2. 🥈 Grammaire N'ko (règles de formation des mots)
3. 🥉 Tes connaissances générales (à utiliser avec prudence)

⚠️ RÈGLE ABSOLUE :
- JAMAIS inventer une traduction sans l'avoir dans le vocabulaire pertinent
- Toujours vérifier dans le bloc "📖 VOCABULAIRE PERTINENT" avant de répondre

═══════════════════════════════════════════════════════════════

🎯 TON RÔLE :
- Tu es Nkotronic, l'assistant IA expert en N'ko
- Tu es bienveillant, précis et pédagogue
- Tu maîtrises parfaitement la grammaire N'ko
- Tu utilises le lexique dynamique pour garantir des traductions exactes
- Tu corriges avec bienveillance les erreurs sur le N'ko
- Tu réponds scientifiquement et adaptes tes réponses au contexte

═══════════════════════════════════════════════════════════════

"""

def load_system_prompt():
    """Charge le prompt système depuis le fichier avec messages de progression"""
    global NKOTRONIC_SYSTEM_PROMPT, GRAMMAR_SUMMARY, LOADING_STATUS
    
    try:
        LOADING_STATUS.update({
            "status": "loading_grammar",
            "message": "📥 Chargement de la grammaire N'ko...",
            "progress": 40
        })
        print(f"📥 Chargement du fichier de grammaire: {GRAMMAR_FILE_PATH}")
        
        with open(GRAMMAR_FILE_PATH, 'r', encoding='utf-8') as f:
            grammar_content = f.read()
        
        GRAMMAR_SUMMARY = grammar_content
        
        # Version condensée (200 lignes)
        lines = grammar_content.split('\n')
        condensed_grammar = '\n'.join(lines[:200])
        
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + condensed_grammar + """

[... Grammaire complète chargée en mémoire, disponible sur demande ...]

Tu es Nkotronic, l'IA experte en N'ko. Tu connais toutes les règles grammaticales.
Tu es bienveillant, précis et pédagogue."""
        
        LOADING_STATUS.update({
            "grammar_loaded": True
        })
        
        print(f"✅ Grammaire chargée: {len(NKOTRONIC_SYSTEM_PROMPT):,} caractères")
        return True
        
    except FileNotFoundError:
        LOADING_STATUS.update({
            "status": "error",
            "message": f"❌ Fichier de grammaire introuvable : {GRAMMAR_FILE_PATH}",
            "grammar_loaded": False
        })
        print(f"❌ Fichier '{GRAMMAR_FILE_PATH}' introuvable")
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\nTu es Nkotronic, assistant IA N'ko."
        return False
        
    except Exception as e:
        LOADING_STATUS.update({
            "status": "error",
            "message": f"❌ Erreur chargement grammaire : {str(e)}",
            "grammar_loaded": False
        })
        print(f"❌ Erreur chargement grammaire: {e}")
        NKOTRONIC_SYSTEM_PROMPT = EXPLANATORY_PROMPT + "\nTu es Nkotronic, assistant IA N'ko."
        return False

# ═══════════════════════════════════════════════════════════
# QDRANT - GESTION DU VOCABULAIRE
# ═══════════════════════════════════════════════════════════

def init_qdrant():
    """Initialise la connexion Qdrant (sans modèle d'embedding local)"""
    global qdrant_client, openai_client, LOADING_STATUS
    
    if not QDRANT_AVAILABLE:
        print("⚠️  Qdrant non disponible (dépendances manquantes)")
        return False
    
    try:
        LOADING_STATUS.update({
            "status": "connecting_qdrant",
            "message": "🔗 Connexion à Qdrant...",
            "progress": 10
        })
        print(f"🔗 Connexion à Qdrant: {QDRANT_URL}")
        
        qdrant_client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY,
            timeout=30
        )
        
        # Initialiser le client OpenAI (pour embeddings)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("❌ OPENAI_API_KEY manquant")
            return False
        
        openai_client = openai.OpenAI(api_key=api_key)
        
        print("✅ Qdrant + OpenAI embeddings initialisés")
        return True
        
    except Exception as e:
        print(f"❌ Erreur initialisation Qdrant: {e}")
        LOADING_STATUS.update({
            "status": "qdrant_error",
            "message": f"⚠️ Qdrant non disponible: {str(e)}"
        })
        return False

def parse_lexique_file(content: str) -> dict:
    """Parse le fichier lexique format <<<MOTS ... MOTS>>>"""
    lexique = {}
    
    try:
        # Extraire le contenu entre <<<MOTS et MOTS>>>
        if "<<<MOTS" in content and "MOTS>>>" in content:
            start = content.index("<<<MOTS") + len("<<<MOTS")
            end = content.index("MOTS>>>")
            mots_section = content[start:end].strip()
            
            # Parser chaque ligne
            for line_num, line in enumerate(mots_section.split('\n'), 1):
                line = line.strip()
                
                # Ignorer lignes vides et commentaires
                if not line or line.startswith('#'):
                    continue
                
                # Parser format: francais=nko
                if '=' in line:
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        francais = parts[0].strip()
                        nko = parts[1].strip()
                        
                        if francais and nko:
                            lexique[francais] = nko
                        else:
                            print(f"⚠️  Ligne {line_num} ignorée (vide): {line}")
                    else:
                        print(f"⚠️  Ligne {line_num} mal formatée: {line}")
                else:
                    print(f"⚠️  Ligne {line_num} sans '=': {line}")
            
            print(f"✅ {len(lexique)} mots parsés avec succès")
        else:
            print("❌ Format invalide: balises <<<MOTS ... MOTS>>> manquantes")
            print(f"Aperçu du contenu: {content[:200]}...")
    
    except Exception as e:
        print(f"❌ Erreur parsing lexique: {e}")
    
    return lexique

def sync_lexique_to_qdrant():
    """Télécharge le lexique depuis GitHub et le synchronise avec Qdrant"""
    global LOADING_STATUS
    
    if not QDRANT_AVAILABLE or not qdrant_client or not openai_client:
        print("⚠️  Qdrant ou OpenAI non disponible, synchronisation impossible")
        return False
    
    try:
        # Étape 1 : Télécharger depuis GitHub
        LOADING_STATUS.update({
            "status": "downloading_vocabulary",
            "message": "📥 Téléchargement du lexique depuis GitHub...",
            "progress": 50
        })
        print(f"📥 Téléchargement du lexique: {GITHUB_LEXIQUE_URL}")
        
        response = requests.get(GITHUB_LEXIQUE_URL, timeout=30)
        response.raise_for_status()
        content = response.text
        
        print(f"✅ Fichier téléchargé: {len(content)} caractères")
        
        # Étape 2 : Parser
        LOADING_STATUS.update({
            "status": "parsing_vocabulary",
            "message": "📖 Analyse du fichier lexique...",
            "progress": 60
        })
        
        lexique = parse_lexique_file(content)
        
        if not lexique:
            raise ValueError("Aucun mot trouvé dans le fichier lexique")
        
        print(f"✅ {len(lexique)} mots extraits")
        
        # Étape 3 : Supprimer ancienne collection
        LOADING_STATUS.update({
            "status": "deleting_old_vocabulary",
            "message": "🗑️ Suppression de l'ancien vocabulaire...",
            "progress": 70
        })
        
        try:
            qdrant_client.delete_collection(COLLECTION_NAME)
            print(f"🗑️ Ancienne collection '{COLLECTION_NAME}' supprimée")
        except Exception as e:
            print(f"ℹ️  Collection '{COLLECTION_NAME}' n'existait pas ({e})")
        
        # Étape 4 : Créer nouvelle collection
        LOADING_STATUS.update({
            "status": "creating_collection",
            "message": "🏗️ Création de la nouvelle collection...",
            "progress": 75
        })
        
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            on_disk_payload=True  # Économise la RAM !
        )
        print(f"✅ Collection '{COLLECTION_NAME}' créée")
        
        # Étape 5 : Créer les embeddings via OpenAI API
        LOADING_STATUS.update({
            "status": "creating_embeddings",
            "message": f"🧠 Création des embeddings (OpenAI)...",
            "progress": 80
        })
        
        # Préparer les textes pour embedding
        texts_to_embed = []
        text_to_payload = {}
        
        for francais, nko in lexique.items():
            # Embedder les deux (français et nko)
            texts_to_embed.append(francais)
            text_to_payload[francais] = {
                "francais": francais,
                "nko": nko,
                "type": "vocabulaire"
            }
            
            texts_to_embed.append(nko)
            text_to_payload[nko] = {
                "francais": francais,
                "nko": nko,
                "type": "vocabulaire"
            }
        
        print(f"🧠 Création de {len(texts_to_embed)} embeddings via OpenAI...")
        
        # Appeler l'API OpenAI pour créer les embeddings (par batch de 100)
        batch_size = 100
        all_embeddings = []
        
        for i in range(0, len(texts_to_embed), batch_size):
            batch = texts_to_embed[i:i+batch_size]
            print(f"  📤 Batch {i//batch_size + 1}/{(len(texts_to_embed)-1)//batch_size + 1}...")
            
            response = openai_client.embeddings.create(
                input=batch,
                model=EMBEDDING_MODEL
            )
            
            all_embeddings.extend([item.embedding for item in response.data])
        
        print(f"✅ {len(all_embeddings)} embeddings créés")
        
        # Étape 6 : Indexer dans Qdrant
        LOADING_STATUS.update({
            "status": "indexing_vocabulary",
            "message": f"⚡ Indexation dans Qdrant...",
            "progress": 85
        })
        
        points = []
        for idx, (text, embedding) in enumerate(zip(texts_to_embed, all_embeddings)):
            points.append(PointStruct(
                id=idx,
                vector=embedding,
                payload=text_to_payload[text]
            ))
        
        # Uploader par batch
        batch_size = 100
        indexed_count = 0
        
        for i in range(0, len(points), batch_size):
            batch = points[i:i+batch_size]
            qdrant_client.upsert(collection_name=COLLECTION_NAME, points=batch)
            indexed_count += len(batch)
            
            progress = 85 + int((indexed_count / len(points)) * 10)
            LOADING_STATUS.update({
                "progress": min(progress, 95),
                "message": f"⚡ Indexation: {indexed_count}/{len(points)}..."
            })
            print(f"  📤 {indexed_count}/{len(points)} points indexés...")
        
        # Étape 7 : Finalisation
        LOADING_STATUS.update({
            "status": "ready",
            "message": f"✅ Système prêt ! Vocabulaire: {len(lexique)} mots",
            "progress": 100,
            "vocabulary_loaded": True,
            "vocabulary_count": len(lexique)
        })
        
        print(f"✅ {len(lexique)} mots indexés dans Qdrant avec succès")
        return True
        
    except requests.RequestException as e:
        error_msg = f"Erreur téléchargement GitHub: {str(e)}"
        LOADING_STATUS.update({
            "status": "error",
            "message": f"❌ {error_msg}",
            "vocabulary_loaded": False
        })
        print(f"❌ {error_msg}")
        return False
        
    except Exception as e:
        error_msg = f"Erreur synchronisation vocabulaire: {str(e)}"
        LOADING_STATUS.update({
            "status": "error",
            "message": f"❌ {error_msg}",
            "vocabulary_loaded": False
        })
        print(f"❌ {error_msg}")
        return False

def search_vocabulary(query: str, limit: int = 15) -> list:
    """Recherche des mots dans le vocabulaire Qdrant en utilisant les embeddings OpenAI"""
    try:
        if not qdrant_client or not openai_client:
            return []
        
        # Créer embedding de la requête via OpenAI API
        response = openai_client.embeddings.create(
            input=[query],
            model=EMBEDDING_MODEL
        )
        query_vector = response.data[0].embedding
        
        # Rechercher dans Qdrant
        results = qdrant_client.search(
            collection_name=COLLECTION_NAME,
            query_vector=query_vector,
            limit=limit
        )
        
        # Formater les résultats
        mots_trouves = []
        for result in results:
            mots_trouves.append({
                "francais": result.payload["francais"],
                "nko": result.payload["nko"],
                "score": round(result.score, 3)
            })
        
        return mots_trouves
        
    except Exception as e:
        print(f"❌ Erreur recherche vocabulaire: {e}")
        return []

# ═══════════════════════════════════════════════════════════
# GESTION DES SESSIONS
# ═══════════════════════════════════════════════════════════

class SessionData(BaseModel):
    messages: List[Dict[str, str]] = []
    created_at: datetime
    last_activity: datetime

sessions: OrderedDict[str, SessionData] = OrderedDict()
MAX_SESSIONS = 1000
SESSION_TTL_HOURS = 24
MAX_MESSAGES_PER_SESSION = 20

def get_session(session_id: str) -> SessionData:
    now = datetime.now()
    
    if session_id in sessions:
        session = sessions[session_id]
        session.last_activity = now
        sessions.move_to_end(session_id)
        return session
    
    session = SessionData(messages=[], created_at=now, last_activity=now)
    sessions[session_id] = session
    
    while len(sessions) > MAX_SESSIONS:
        oldest_id = next(iter(sessions))
        del sessions[oldest_id]
    
    return session

def add_message(session_id: str, role: str, content: str):
    session = get_session(session_id)
    session.messages.append({"role": role, "content": content})
    
    if len(session.messages) > MAX_MESSAGES_PER_SESSION:
        session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]

# ═══════════════════════════════════════════════════════════
# MODÈLES
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2000

class ChatResponse(BaseModel):
    response: str
    model_used: str
    tokens_used: Optional[int] = None
    session_id: str
    messages_in_session: int
    vocabulary_used: Optional[int] = None

# ═══════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Endpoint principal de conversation avec injection vocabulaire"""
    try:
        # Vérifier si le système est prêt
        if not LOADING_STATUS.get("grammar_loaded"):
            raise HTTPException(
                status_code=503, 
                detail={
                    "error": "Service temporairement indisponible",
                    "message": LOADING_STATUS.get("message", "Grammaire en cours de chargement"),
                    "status": LOADING_STATUS.get("status"),
                    "progress": LOADING_STATUS.get("progress", 0)
                }
            )
        
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
        
        if not NKOTRONIC_SYSTEM_PROMPT:
            raise HTTPException(status_code=500, detail="Prompt système non chargé")
        
        session = get_session(request.session_id)
        
        # 🆕 RECHERCHER VOCABULAIRE PERTINENT
        mots_pertinents = search_vocabulary(request.message, limit=15)
        vocab_count = len(mots_pertinents)
        
        # Message système de base
        messages = [{"role": "system", "content": NKOTRONIC_SYSTEM_PROMPT}]
        
        # 🆕 INJECTER LE VOCABULAIRE TROUVÉ
        if mots_pertinents:
            # Filtrer les mots les plus pertinents (score > 0.5)
            mots_filtres = [m for m in mots_pertinents if m['score'] > 0.5]
            
            if mots_filtres:
                vocab_context = "📖 VOCABULAIRE PERTINENT :\n" + "\n".join([
                    f"• {mot['francais']} = {mot['nko']} (pertinence: {mot['score']})"
                    for mot in mots_filtres[:10]  # Max 10 mots
                ])
                messages.append({"role": "system", "content": vocab_context})
                print(f"📖 {len(mots_filtres)} mots injectés dans le contexte")
        
        # Historique de conversation
        for msg in session.messages:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Message actuel
        messages.append({"role": "user", "content": request.message})
        
        # Appel OpenAI
        client = openai.OpenAI(api_key=api_key)
        completion = client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        response_text = completion.choices[0].message.content
        tokens_used = completion.usage.total_tokens if completion.usage else None
        
        # Sauvegarder dans la session
        add_message(request.session_id, "user", request.message)
        add_message(request.session_id, "assistant", response_text)
        
        return ChatResponse(
            response=response_text,
            model_used=request.model,
            tokens_used=tokens_used,
            session_id=request.session_id,
            messages_in_session=len(session.messages),
            vocabulary_used=vocab_count
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Endpoint streaming SSE avec injection vocabulaire"""
    
    async def generate():
        try:
            # Vérifier statut
            if not LOADING_STATUS.get("grammar_loaded"):
                yield f"data: {json.dumps({
                    'error': 'Service temporairement indisponible',
                    'message': LOADING_STATUS.get('message'),
                    'status': LOADING_STATUS.get('status'),
                    'progress': LOADING_STATUS.get('progress')
                })}\n\n"
                return
            
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'OPENAI_API_KEY not configured'})}\n\n"
                return
            
            if not NKOTRONIC_SYSTEM_PROMPT:
                yield f"data: {json.dumps({'error': 'Prompt système non chargé'})}\n\n"
                return
            
            session = get_session(request.session_id)
            
            # 🆕 RECHERCHER VOCABULAIRE
            mots_pertinents = search_vocabulary(request.message, limit=15)
            
            # Messages
            messages = [{"role": "system", "content": NKOTRONIC_SYSTEM_PROMPT}]
            
            # 🆕 INJECTER VOCABULAIRE
            if mots_pertinents:
                mots_filtres = [m for m in mots_pertinents if m['score'] > 0.5]
                if mots_filtres:
                    vocab_context = "📖 VOCABULAIRE PERTINENT :\n" + "\n".join([
                        f"• {mot['francais']} = {mot['nko']}"
                        for mot in mots_filtres[:10]
                    ])
                    messages.append({"role": "system", "content": vocab_context})
            
            # Historique
            for msg in session.messages:
                messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": request.message})
            
            # Streaming
            client = openai.OpenAI(api_key=api_key)
            stream = client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                stream=True
            )
            
            full_response = ""
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            # Sauvegarder
            add_message(request.session_id, "user", request.message)
            add_message(request.session_id, "assistant", full_response)
            
            yield f"data: {json.dumps({'done': True, 'session_id': request.session_id, 'vocabulary_used': len(mots_pertinents)})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.get("/")
async def root():
    return {
        "name": "Nkotronic API",
        "version": "4.1.0-VOCABULARY",
        "status": "running",
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False),
        "vocabulary_loaded": LOADING_STATUS.get("vocabulary_loaded", False),
        "vocabulary_count": LOADING_STATUS.get("vocabulary_count", 0),
        "qdrant_available": QDRANT_AVAILABLE and qdrant_client is not None
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "active_sessions": len(sessions),
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False),
        "vocabulary_loaded": LOADING_STATUS.get("vocabulary_loaded", False),
        "vocabulary_count": LOADING_STATUS.get("vocabulary_count", 0)
    }

@app.get("/loading-status")
async def loading_status():
    """Endpoint pour vérifier le statut de chargement complet"""
    return LOADING_STATUS

@app.post("/sync-vocabulary")
async def sync_vocabulary():
    """Force la synchronisation du vocabulaire depuis GitHub"""
    print("🔄 Synchronisation manuelle du vocabulaire demandée...")
    success = sync_lexique_to_qdrant()
    
    return {
        "success": success,
        "status": LOADING_STATUS.get("status"),
        "message": LOADING_STATUS.get("message"),
        "vocabulary_count": LOADING_STATUS.get("vocabulary_count", 0),
        "vocabulary_loaded": LOADING_STATUS.get("vocabulary_loaded", False)
    }

@app.post("/search-vocabulary")
async def search_vocabulary_endpoint(query: str, limit: int = 10):
    """Recherche manuelle dans le vocabulaire (pour tests)"""
    results = search_vocabulary(query, limit)
    return {
        "query": query,
        "results_count": len(results),
        "results": results
    }

@app.post("/warmup")
async def warmup():
    return {
        "status": "warmed_up",
        "grammar_loaded": LOADING_STATUS.get("grammar_loaded", False),
        "vocabulary_loaded": LOADING_STATUS.get("vocabulary_loaded", False),
        "vocabulary_count": LOADING_STATUS.get("vocabulary_count", 0)
    }

# ═══════════════════════════════════════════════════════════
# DÉMARRAGE
# ═══════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    print("=" * 70)
    print("🚀 NKOTRONIC API v4.1.0 - DÉMARRAGE OPTIMISÉ RENDER")
    print("=" * 70)
    
    # Charger la grammaire d'abord (rapide, ~1 seconde)
    print("\n📖 Chargement de la grammaire N'ko...")
    print("-" * 70)
    grammar_ok = load_system_prompt()
    
    if grammar_ok:
        print(f"✅ Grammaire chargée: {len(NKOTRONIC_SYSTEM_PROMPT):,} caractères")
    else:
        print("⚠️ Grammaire non chargée (mode dégradé)")
    
    print("\n" + "=" * 70)
    print("✅ API PRÊTE ! (vocabulaire en cours de chargement...)")
    print("=" * 70 + "\n")
    
    # Charger Qdrant et vocabulaire en arrière-plan (évite timeout)
    import asyncio
    asyncio.create_task(init_qdrant_and_vocab_async())


async def init_qdrant_and_vocab_async():
    """Initialise Qdrant et le vocabulaire en arrière-plan après le démarrage"""
    import asyncio
    
    # Attendre que le serveur soit bien démarré
    await asyncio.sleep(3)
    
    print("\n" + "=" * 70)
    print("📊 CHARGEMENT VOCABULAIRE EN ARRIÈRE-PLAN")
    print("=" * 70)
    
    # Étape 1 : Initialiser Qdrant
    print("\n🔗 Connexion à Qdrant...")
    qdrant_ok = init_qdrant()
    
    if qdrant_ok:
        print("✅ Qdrant connecté")
        
        # Étape 2 : Synchroniser vocabulaire
        print("\n📚 Synchronisation du vocabulaire depuis GitHub...")
        vocab_ok = sync_lexique_to_qdrant()
        
        if vocab_ok:
            print(f"\n✅ VOCABULAIRE CHARGÉ : {LOADING_STATUS.get('vocabulary_count', 0)} mots")
        else:
            print("\n⚠️ Vocabulaire non chargé (continuera sans)")
    else:
        print("⚠️ Qdrant non disponible (vocabulaire désactivé)")
    
    print("\n" + "=" * 70)
    print("🎉 SYSTÈME COMPLÈTEMENT OPÉRATIONNEL !")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)