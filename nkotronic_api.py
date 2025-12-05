import asyncio
import os
import logging
import json
import uuid
from contextlib import asynccontextmanager
from typing import Optional, AsyncIterator, List, Dict
from pathlib import Path
from collections import deque
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import VectorParams, PointStruct, Distance, models

# --- CHARGER LE FICHIER .env ---
try:
    from dotenv import load_dotenv
    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info(f"✅ Fichier .env chargé depuis: {env_path.absolute()}")
except ImportError:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logging.warning("⚠️ python-dotenv non installé, utilise les variables d'environnement système")

# --- LOGGING CONFIG ---
logging.getLogger("qdrant_client").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# --- CONFIGURATION ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
QDRANT_URL = os.getenv("QDRANT_URL", "")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")

# Validation des clés au démarrage
if not OPENAI_API_KEY:
    logging.error("❌ OPENAI_API_KEY non trouvée!")
else:
    logging.info(f"✅ OPENAI_API_KEY chargée")

if not QDRANT_URL:
    logging.error("❌ QDRANT_URL non trouvée!")
else:
    logging.info(f"✅ QDRANT_URL configurée")

if not QDRANT_API_KEY:
    logging.warning("⚠️ QDRANT_API_KEY non trouvée")
else:
    logging.info(f"✅ QDRANT_API_KEY chargée")

# --- GLOBAL CLIENTS ---
LLM_CLIENT: Optional[OpenAI] = None
QDRANT_CLIENT: Optional[AsyncQdrantClient] = None

# 🆕 PHASE 6: SYSTÈME DE MÉMOIRE CONVERSATIONNELLE
# Stockage des conversations par session
CONVERSATION_MEMORY: Dict[str, deque] = {}
MAX_MEMORY_SIZE = 100  # 100 derniers messages

# --- CONSTANTS ---
COLLECTION_NAME = "nkotronic_knowledge_base"
VECTOR_SIZE = 1536
EMBEDDING_MODEL = "text-embedding-ada-002"
LLM_MODEL = "gpt-4o"
RAG_SCORE_THRESHOLD = 0.55

# 🆕 PHASE 3 : MAPPING PHONÉTIQUE N'KO
NKO_PHONETIC_MAP = {
    'ߊ': 'a', 'ߋ': 'e', 'ߌ': 'i', 'ߍ': 'ɛ', 'ߎ': 'u', 'ߏ': 'o', 'ߐ': 'ɔ',
    'ߓ': 'b', 'ߔ': 'p', 'ߕ': 't', 'ߖ': 'j', 'ߗ': 'ch', 'ߘ': 'd',
    'ߙ': 'r', 'ߚ': 'rr', 'ߛ': 's', 'ߜ': 'g', 'ߝ': 'f', 'ߞ': 'k',
    'ߟ': 'l', 'ߠ': 'm', 'ߡ': 'n', 'ߢ': 'ny', 'ߣ': 'ɲ', 'ߤ': 'h',
    'ߥ': 'w', 'ߦ': 'y', 'ߧ': 'gn', 'ߨ': 'ng',
    '߫': '', '߬': '', '߭': '', '߮': '', '߯': '', '߰': '', '߱': '', '߲': 'n',
    '߀': '0', '߁': '1', '߂': '2', '߃': '3', '߄': '4',
    '߅': '5', '߆': '6', '߇': '7', '߈': '8', '߉': '9'
}

# 🆕 PHASE 6: PROMPT SYSTÈME INTELLIGENT AVEC MÉMOIRE
PROMPT_SYSTEM_INTELLIGENT = """Tu es Nkotronic, assistant N'ko intelligent, empathique et doté d'une excellente mémoire.

🧠 PERSONNALITÉ:
- Tu es patient, pédagogue et encourageant
- Tu te souviens de TOUTE la conversation en cours
- Tu analyses, réfléchis et déduis intelligemment
- Tu as un vrai sens de l'humour et de la culture mandingue

📚 CONTEXTE DE LA CONVERSATION:
{historique_conversation}

🔍 CONNAISSANCES PERTINENTES (Base de données):
{contexte_rag}

⚠️ RÈGLES ABSOLUES:

1. PRIORITÉ AU CONTEXTE RAG:
   - Si le contexte RAG contient la réponse EXACTE (score=1.0), utilise-la OBLIGATOIREMENT
   - Ne cherche PAS ailleurs si tu as déjà la réponse dans le contexte
   - Exemple: Si contexte dit "clavier = ߝߐߞߘߎߥߟߊ", réponds EXACTEMENT ça

2. UTILISATION DE LA MÉMOIRE:
   - Relis l'historique pour comprendre le contexte complet
   - Fais référence aux messages précédents quand c'est pertinent
   - Si on te demande "tu es sûr ?", relis ce que tu as dit avant
   - Si on te demande un résumé, analyse TOUS les messages précédents

3. INTELLIGENCE ET RAISONNEMENT:
   - Déduis les relations entre concepts
   - Explique le "pourquoi" pas juste le "quoi"
   - Propose des exemples concrets et culturels
   - Corrige-toi si tu te trompes (en consultant l'historique)

4. GESTION DES LACUNES:
   - Si tu ne sais pas, dis-le honnêtement
   - Propose des alternatives proches
   - Demande des précisions si nécessaire

5. SALUTATIONS:
   - Réponds aux salutations naturellement
   - N'ajoute PAS de salutations si ce n'est pas le contexte
   - Utilise le N'ko pour les formules de politesse

EXEMPLES DE COMPORTEMENT INTELLIGENT:

Q: "salut ça va ?"
→ R: "Je vais bien, merci ! Et toi ?"

Q: "c'est quoi ߝߐߞߘߎߥߟߊ ?" + RAG: "clavier = ߝߐߞߘߎߥߟߊ (score=1.0)"
→ R: "ߝߐߞߘߎߥߟߊ signifie 'clavier' en français. C'est l'outil qu'on utilise pour taper en N'ko."

Q: "tu es sûr ?" (après avoir dit que ߝߐߞߘߎߥߟߊ = feu)
→ R: "Pardon, j'ai fait une erreur ! En relisant, je vois que je t'ai appris que ߝߐߞߘߎߥߟߊ = clavier. C'est bien clavier, pas feu."

Q: "résume notre conversation"
→ R: [Analyse les 100 derniers messages et fait un vrai résumé structuré]

Q: "on parlait de quoi il y a 10 messages ?"
→ R: [Compte -10 messages et répond précisément]

Question actuelle: {user_message}

Réponds maintenant avec intelligence, mémoire et précision:"""

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
    global LLM_CLIENT, QDRANT_CLIENT
    logging.info("🚀 Démarrage de Nkotronic v2.4.0 (Mémoire Intelligente)...")

    # 1️⃣ INIT OpenAI
    try:
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY manquante!")
        
        LLM_CLIENT = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)
        test_response = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=5
        )
        logging.info("✅ Client OpenAI initialisé et testé")
    except Exception as e:
        logging.error(f"❌ Erreur OpenAI: {e}")
        LLM_CLIENT = None
        yield {}
        return

    # 2️⃣ INIT Qdrant
    if QDRANT_URL and QDRANT_API_KEY:
        try:
            QDRANT_CLIENT = AsyncQdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                prefer_grpc=False,
                timeout=30.0
            )
            
            # Vérifier si la collection existe déjà
            collections = await QDRANT_CLIENT.get_collections()
            exists = any(c.name == COLLECTION_NAME for c in collections.collections)
            
            if exists:
                count = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
                logging.info(f"✅ Collection '{COLLECTION_NAME}' trouvée avec {count.count} points")
            else:
                await QDRANT_CLIENT.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE)
                )
                logging.info(f"✅ Collection '{COLLECTION_NAME}' créée")

        except Exception as e:
            logging.error(f"❌ Erreur Qdrant: {e}")
            QDRANT_CLIENT = None
    else:
        logging.warning("⚠️ Qdrant non configuré")

    logging.info("✅ Nkotronic v2.4.0 prêt avec mémoire conversationnelle!")
    yield {}
    logging.info("🛑 Arrêt de Nkotronic")

app = FastAPI(
    title="Nkotronic API",
    description="API de traduction Français ↔ N'ko avec mémoire RAG + Mémoire Conversationnelle",
    version="2.4.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class ChatRequest(BaseModel):
    user_message: str = Field(..., description="Message utilisateur")
    session_id: Optional[str] = Field(None, description="ID de session pour mémoire conversationnelle")
    rag_enabled: bool = Field(True, description="Activer le RAG")
    debug: bool = Field(False, description="Mode debug avec détails")

class ChatResponse(BaseModel):
    response_text: str = Field(..., description="Texte de réponse")
    session_id: str = Field(..., description="ID de session")
    memory_update: Optional[dict] = Field(None, description="Mise à jour mémoire")
    debug_info: Optional[dict] = Field(None, description="Infos de debug")

class TranslationEntry(BaseModel):
    element_français: str = Field(..., description="Le mot ou expression en français.")
    element_nko: str = Field(..., description="La traduction correspondante en N'ko.")
    concept_identifie: str = Field("Général", description="Le domaine ou concept identifié.")
    
    # 🆕 PHASE 2 : ENRICHISSEMENT DU MODÈLE
    valeur_numerique: Optional[float] = Field(None, description="Valeur numérique si applicable (ex: chiffres, dates, mesures)")
    fait_texte: Optional[str] = Field(None, description="Fait ou information textuelle associée (définition, contexte, usage)")
    
    # 🆕 Métadonnées additionnelles
    exemples: Optional[List[str]] = Field(None, description="Exemples d'utilisation en contexte")
    synonymes: Optional[List[str]] = Field(None, description="Synonymes en N'ko")
    categorie_grammaticale: Optional[str] = Field(None, description="nom, verbe, adjectif, adverbe, etc.")
    niveau_langue: Optional[str] = Field(None, description="formel, courant, familier")


# 🆕 PHASE 5.1 : MODÈLE DE CONNAISSANCE MULTI-TYPES
class ConnaissanceEntry(BaseModel):
    """
    Modèle unifié pour stocker TOUS les types de connaissances N'ko.
    
    Types supportés:
    - "mot" : Traduction simple  
    - "règle" : Règle grammaticale
    - "fait" : Fait culturel/linguistique
    - "anecdote" : Histoire/récit
    - "liste" : Liste structurée (jours, mois, etc.)
    - "conjugaison" : Formes verbales
    - "expression" : Expression idiomatique
    - "proverbe" : Proverbe/dicton
    """
    # === IDENTIFICATION ===
    type_connaissance: str = Field("mot", description="Type: mot, règle, fait, anecdote, liste, conjugaison, expression, proverbe")
    
    # === POUR LES MOTS (type="mot") ===
    element_français: Optional[str] = Field(None, description="Mot en français")
    element_nko: Optional[str] = Field(None, description="Mot en N'ko")
    concept_identifie: Optional[str] = Field("Général", description="Catégorie du concept")
    
    # === POUR LES RÈGLES (type="règle") ===
    titre_règle: Optional[str] = Field(None, description="Titre de la règle grammaticale")
    explication_règle: Optional[str] = Field(None, description="Explication détaillée de la règle")
    exceptions: Optional[List[str]] = Field(None, description="Exceptions à la règle")
    
    # === POUR LES FAITS/ANECDOTES (type="fait" ou "anecdote") ===
    titre: Optional[str] = Field(None, description="Titre du fait ou de l'anecdote")
    contenu: Optional[str] = Field(None, description="Contenu narratif")
    
    # === POUR LES LISTES (type="liste") ===
    nom_liste: Optional[str] = Field(None, description="Nom de la liste")
    elements_liste: Optional[List[Dict[str, str]]] = Field(None, description="Éléments [{nko: '', fr: ''}]")
    
    # === POUR LES CONJUGAISONS (type="conjugaison") ===
    verbe_nko: Optional[str] = Field(None, description="Verbe en N'ko")
    verbe_français: Optional[str] = Field(None, description="Verbe en français")
    formes: Optional[Dict[str, str]] = Field(None, description="Formes conjuguées")
    
    # === POUR LES EXPRESSIONS/PROVERBES ===
    texte_nko: Optional[str] = Field(None, description="Texte en N'ko")
    traduction_littérale: Optional[str] = Field(None, description="Traduction mot à mot")
    signification: Optional[str] = Field(None, description="Signification réelle")
    
    # === CHAMPS COMMUNS ===
    valeur_numerique: Optional[float] = Field(None, description="Valeur numérique")
    fait_texte: Optional[str] = Field(None, description="Information contextuelle")
    exemples: Optional[List[str]] = Field(None, description="Exemples d'utilisation")
    synonymes: Optional[List[str]] = Field(None, description="Synonymes")
    categorie_grammaticale: Optional[str] = Field(None, description="Catégorie grammaticale")
    niveau_langue: Optional[str] = Field(None, description="Niveau de langue")
    tags: Optional[List[str]] = Field(None, description="Tags pour recherche")
    difficulté: Optional[str] = Field(None, description="débutant, intermédiaire, avancé")
    source: Optional[str] = Field(None, description="Source de l'information")
    appris_par: Optional[str] = Field(None, description="Qui a enseigné")
    date_ajout: Optional[str] = Field(None, description="Timestamp d'ajout")


# 🆕 PHASE 6: GESTION DE LA MÉMOIRE CONVERSATIONNELLE
def get_or_create_session(session_id: Optional[str] = None) -> str:
    """Récupère ou crée une session de conversation."""
    if session_id and session_id in CONVERSATION_MEMORY:
        return session_id
    
    # Créer nouvelle session
    new_session_id = session_id or str(uuid.uuid4())
    CONVERSATION_MEMORY[new_session_id] = deque(maxlen=MAX_MEMORY_SIZE)
    logging.info(f"🆕 Nouvelle session créée: {new_session_id}")
    return new_session_id


def ajouter_message_memoire(session_id: str, role: str, content: str):
    """Ajoute un message à l'historique de la session."""
    if session_id not in CONVERSATION_MEMORY:
        CONVERSATION_MEMORY[session_id] = deque(maxlen=MAX_MEMORY_SIZE)
    
    message = {
        'role': role,
        'content': content,
        'timestamp': datetime.now().isoformat()
    }
    
    CONVERSATION_MEMORY[session_id].append(message)
    logging.info(f"💬 Message ajouté à session {session_id[:8]}... (total: {len(CONVERSATION_MEMORY[session_id])} messages)")


def formater_historique_conversation(session_id: str, limite: int = 20) -> str:
    """
    Formate l'historique de conversation pour le contexte du LLM.
    
    Args:
        session_id: ID de la session
        limite: Nombre de derniers messages à inclure (par défaut 20 pour le contexte)
    
    Returns:
        Historique formaté
    """
    if session_id not in CONVERSATION_MEMORY:
        return "[Nouvelle conversation - Pas d'historique]"
    
    historique = list(CONVERSATION_MEMORY[session_id])
    
    if not historique:
        return "[Nouvelle conversation - Pas d'historique]"
    
    # Prendre les N derniers messages
    messages_recents = historique[-limite:] if len(historique) > limite else historique
    
    lignes = []
    lignes.append(f"[Historique: {len(historique)} messages total, affichage des {len(messages_recents)} plus récents]")
    lignes.append("")
    
    for i, msg in enumerate(messages_recents, 1):
        role_symbol = "👤" if msg['role'] == 'user' else "🤖"
        lignes.append(f"{role_symbol} Message #{len(historique) - len(messages_recents) + i}:")
        lignes.append(f"   {msg['content'][:200]}{'...' if len(msg['content']) > 200 else ''}")
        lignes.append("")
    
    return "\n".join(lignes)


async def analyser_intention_memoire(user_message: str, session_id: str, llm_client: OpenAI) -> Optional[Dict]:
    """
    Détecte si le message demande une analyse de l'historique.
    
    Types d'intentions:
    - "résume" : Résumer la conversation
    - "on parlait de quoi" : Rappeler le contexte
    - "il y a X messages" : Accéder à un message spécifique
    - "qu'est-ce que j'ai dit" : Retrouver un message utilisateur
    """
    import re
    
    message_lower = user_message.lower().strip()
    
    # Détection résumé
    if any(word in message_lower for word in ['résume', 'résumer', 'résumé', 'synthèse', 'récapitulatif']):
        return {
            'type': 'resume',
            'action': 'resume_conversation'
        }
    
    # Détection contexte passé
    if any(phrase in message_lower for phrase in ['on parlait de', 'on discutait de', 'de quoi on parlait']):
        return {
            'type': 'rappel_contexte',
            'action': 'recall_context'
        }
    
    # Détection accès message spécifique
    match_messages = re.search(r'(?:il y a|voilà|ya|y\'a)\s+(\d+)\s+messages?', message_lower)
    if match_messages:
        nb_messages = int(match_messages.group(1))
        return {
            'type': 'acces_message',
            'action': 'access_specific_message',
            'offset': nb_messages
        }
    
    # Détection "qu'est-ce que j'ai dit"
    if any(phrase in message_lower for phrase in ["qu'est-ce que j'ai dit", "qu'ai-je dit", "ce que j'ai dit", "rappelle-moi ce que"]):
        return {
            'type': 'rappel_user',
            'action': 'recall_user_messages'
        }
    
    return None


async def executer_action_memoire(intention: Dict, session_id: str, llm_client: OpenAI) -> str:
    """
    Exécute une action basée sur la mémoire conversationnelle.
    
    Args:
        intention: Dict avec type et action
        session_id: ID de session
        llm_client: Client OpenAI
    
    Returns:
        Réponse générée
    """
    if session_id not in CONVERSATION_MEMORY:
        return "Nous n'avons pas encore d'historique de conversation."
    
    historique = list(CONVERSATION_MEMORY[session_id])
    
    if not historique:
        return "Nous venons de commencer notre conversation."
    
    action = intention['action']
    
    # ACTION 1: Résumer la conversation
    if action == 'resume_conversation':
        # Construire un prompt de résumé
        messages_text = "\n".join([
            f"{'Utilisateur' if m['role'] == 'user' else 'Nkotronic'}: {m['content']}"
            for m in historique
        ])
        
        prompt_resume = f"""Analyse cette conversation entre un utilisateur et Nkotronic (assistant N'ko) et fais-en un résumé structuré et intelligent.

CONVERSATION ({len(historique)} messages):
{messages_text}

Fais un résumé qui inclut:
1. Les sujets principaux abordés
2. Les apprentissages effectués (mots, règles, etc.)
3. Les questions importantes posées
4. L'évolution de la conversation

Sois concis mais précis."""

        try:
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt_resume}],
                temperature=0.3,
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            logging.error(f"❌ Erreur résumé: {e}")
            return f"Erreur lors du résumé de la conversation: {str(e)}"
    
    # ACTION 2: Rappeler le contexte
    elif action == 'recall_context':
        derniers_messages = historique[-10:]
        lignes = ["Voici les derniers sujets dont nous avons parlé:"]
        
        for msg in derniers_messages:
            role = "Tu as dit" if msg['role'] == 'user' else "J'ai répondu"
            lignes.append(f"- {role}: {msg['content'][:100]}{'...' if len(msg['content']) > 100 else ''}")
        
        return "\n".join(lignes)
    
    # ACTION 3: Accéder à un message spécifique
    elif action == 'access_specific_message':
        offset = intention.get('offset', 1)
        
        if offset > len(historique):
            return f"Nous n'avons échangé que {len(historique)} messages jusqu'à présent."
        
        message_cible = historique[-(offset + 1)]  # +1 car on exclut le message actuel
        role = "Tu as dit" if message_cible['role'] == 'user' else "J'ai répondu"
        
        return f"Il y a {offset} messages, {role.lower()}: \"{message_cible['content']}\""
    
    # ACTION 4: Rappeler messages utilisateur
    elif action == 'recall_user_messages':
        messages_user = [m for m in historique if m['role'] == 'user']
        
        if not messages_user:
            return "Tu n'as pas encore envoyé de messages."
        
        derniers_user = messages_user[-5:]
        lignes = ["Voici tes derniers messages:"]
        
        for msg in derniers_user:
            lignes.append(f"- \"{msg['content'][:150]}{'...' if len(msg['content']) > 150 else ''}\"")
        
        return "\n".join(lignes)
    
    return "Action non reconnue."


# --- FONCTION D'EXTRACTION MOT-CLÉ ---
async def extraire_mot_cle(user_message: str, llm_client: OpenAI) -> str:
    """Extrait le mot français à traduire de manière robuste."""
    import re
    
    # Recherche de mots entre guillemets
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", user_message)
    if quoted:
        mot = quoted[0].strip().lower()
        logging.info(f"🔑 Mot extrait des guillemets: '{mot}'")
        return mot
    
    # Extraction via LLM
    prompt = f"""Extrait UNIQUEMENT le mot français à traduire. Réponds avec UN SEUL MOT.

Exemples:
- "comment dit-on silex en n'ko" -> silex
- "traduction de bonjour" -> bonjour
- "c'est quoi eau" -> eau

Question: {user_message}
Mot:"""

    try:
        resp = await asyncio.to_thread(
            llm_client.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=10
        )
        mot = resp.choices[0].message.content.strip().lower()
        mot = re.sub(r'[^\w\s-]', '', mot).strip()
        logging.info(f"🔑 Mot-clé extrait par LLM: '{mot}'")
        return mot
    except Exception as e:
        logging.error(f"❌ Erreur extraction: {e}")
        words = user_message.lower().split()
        stop_words = {'comment', 'dit', 'on', 'en', 'nko', 'n\'ko', 'traduction', 'de', 'le', 'la', 'un', 'une', 'c\'est', 'quoi'}
        significant = [w for w in words if w not in stop_words and len(w) > 2]
        return significant[-1] if significant else user_message.lower()


# 🆕 PHASE 6: RECHERCHE INTELLIGENTE AVEC FILTRAGE SCORE=1.0
async def recherche_intelligente_filtree(mot_cle: str, llm_client: OpenAI, qdrant_client: AsyncQdrantClient):
    """
    Recherche avec filtrage intelligent:
    - Si score=1.0 trouvé, ne retourne QUE ce résultat
    - Sinon, retourne top 5 résultats pertinents
    """
    all_results = []
    
    # STRATÉGIE 1: Recherche exacte
    try:
        logging.info(f"🔍 Recherche pour '{mot_cle}'")
        emb_resp = await asyncio.to_thread(
            llm_client.embeddings.create,
            input=[mot_cle],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        result = await qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=20,
            with_payload=True
        )
        hits = result.points
        all_results.extend(hits)
        
        # 🎯 FILTRAGE INTELLIGENT: Si score=1.0, ne garder QUE ce résultat
        perfect_match = [h for h in hits if h.score >= 0.999]  # Score quasi-parfait
        
        if perfect_match:
            logging.info(f"✅ MATCH PARFAIT trouvé (score={perfect_match[0].score:.4f})")
            return perfect_match[:1]  # Retourner UNIQUEMENT le match parfait
        
        logging.info(f"   -> {len(hits)} résultats trouvés (meilleur score: {hits[0].score if hits else 0:.4f})")
        
    except Exception as e:
        logging.error(f"❌ Recherche échouée: {e}")
    
    # STRATÉGIE 2: Si pas de match parfait, utiliser top 5 pertinents
    unique_results = []
    seen_ids = set()
    
    for hit in all_results:
        if hit.id not in seen_ids and hit.score > RAG_SCORE_THRESHOLD:
            seen_ids.add(hit.id)
            unique_results.append(hit)
            
            if len(unique_results) >= 5:  # Limiter à 5 résultats max
                break
    
    unique_results.sort(key=lambda x: x.score, reverse=True)
    return unique_results


# --- PRÉ-TRAITEMENT INTELLIGENT ---
async def pretraiter_question(user_message: str, llm_client: OpenAI, qdrant_client: AsyncQdrantClient):
    """Détecte les mots N'ko et les traduit pour enrichir la recherche."""
    import re
    import unicodedata
    
    def normaliser_nko(texte: str) -> str:
        """Normalise un texte N'ko pour comparaison fiable"""
        if not texte:
            return ""
        texte = unicodedata.normalize('NFD', texte)
        texte = unicodedata.normalize('NFC', texte)
        texte = ' '.join(texte.split())
        return texte.strip()
    
    # Regex pour détecter les caractères N'ko (U+07C0 à U+07FF)
    nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
    nko_words = nko_pattern.findall(user_message)
    
    if not nko_words:
        return user_message, []
    
    logging.info(f"🔍 Mots N'ko détectés dans la question: {nko_words}")
    
    traductions = []
    for nko_word in nko_words:
        try:
            nko_word_norm = normaliser_nko(nko_word)
            logging.info(f"🔤 Mot normalisé: {nko_word} → {nko_word_norm}")
            
            emb_resp = await asyncio.to_thread(
                llm_client.embeddings.create,
                input=[nko_word_norm],
                model=EMBEDDING_MODEL
            )
            vector = emb_resp.data[0].embedding
            
            results = await qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=vector,
                limit=20,
                with_payload=True
            )
            
            logging.info(f"📊 Recherche pour '{nko_word_norm}': {len(results.points)} résultats")
            
            # STRATÉGIE 1: Match exact normalisé
            for point in results.points:
                point_nko = point.payload.get('element_nko', '')
                point_nko_norm = normaliser_nko(point_nko)
                
                if point_nko_norm == nko_word_norm:
                    fr = point.payload.get('element_français')
                    if fr:
                        traductions.append({
                            'nko': nko_word,
                            'français': fr,
                            'payload': point.payload
                        })
                        logging.info(f"✅ Match exact trouvé: {nko_word} = {fr} (score: {point.score:.4f})")
                        break
            
            # STRATÉGIE 2: Si pas de match exact, prendre le meilleur score
            if not any(t['nko'] == nko_word for t in traductions):
                if results.points and results.points[0].score > 0.80:
                    best = results.points[0]
                    fr = best.payload.get('element_français')
                    nko_found = best.payload.get('element_nko')
                    if fr:
                        traductions.append({
                            'nko': nko_word,
                            'français': fr,
                            'payload': best.payload
                        })
                        logging.info(f"✅ Meilleur match trouvé: {nko_word} ≈ {nko_found} = {fr} (score: {best.score:.4f})")
                else:
                    logging.warning(f"⚠️ Aucune traduction trouvée pour: {nko_word}")
                
        except Exception as e:
            logging.error(f"❌ Erreur lors de la recherche de {nko_word}: {e}")
    
    # Enrichir la question
    question_enrichie = user_message
    for trad in traductions:
        question_enrichie = question_enrichie.replace(
            trad['nko'], 
            f"{trad['nko']} ({trad['français']})"
        )
    
    if traductions:
        logging.info(f"💡 Question enrichie: {question_enrichie}")
    
    return question_enrichie, traductions


# --- PHASE 5.1: DÉTECTION MULTI-TYPES COMPLÈTE ---

def detecter_type_connaissance(message: str) -> Optional[Dict]:
    """
    Détecte le type de connaissance dans le message.
    
    Types supportés:
    - "règle" : Règles grammaticales
    - "fait" : Faits culturels/linguistiques
    - "anecdote" : Histoires/récits
    - "liste" : Listes structurées
    - "conjugaison" : Formes verbales
    - "expression" : Expressions idiomatiques
    - "proverbe" : Proverbes/dictons
    - "mot" : Mots simples (fallback)
    """
    import re
    
    message_clean = message.strip().lower()
    
    # 1️⃣ RÈGLES GRAMMATICALES (priorité haute)
    patterns_règle = [
        r'(?:apprends?|mémorise[rz]?)\s+(?:la\s+)?règle\s*[:;]?\s*(.+)',
        r'règle\s+(?:de\s+)?(?:grammaire|grammaticale)\s*[:;]?\s*(.+)',
        r'en\s+n.?ko,?\s+(.+?)\s+(?:se\s+forme|fonctionne|s.écrit)',
    ]
    
    for pattern in patterns_règle:
        match = re.search(pattern, message_clean, re.IGNORECASE | re.DOTALL)
        if match:
            explication = match.group(1).strip()
            titre = explication.split()[:8]
            titre = ' '.join(titre) + ("..." if len(explication.split()) > 8 else "")
            
            return {
                'type': 'règle',
                'titre_règle': titre,
                'explication_règle': explication,
                'concept_identifie': 'grammaire'
            }
    
    # 2️⃣ FAITS CULTURELS
    patterns_fait = [
        r'(?:apprends?|mémorise[rz]?)\s+(?:le\s+)?fait\s*[:;]?\s*(.+)',
        r'fait\s+(?:culturel|historique|linguistique)\s*[:;]?\s*(.+)',
        r'contexte\s*[:;]?\s*(.+)',
        r'(?:sache|note)\s+que\s+(.+)',
    ]
    
    for pattern in patterns_fait:
        match = re.search(pattern, message_clean, re.IGNORECASE | re.DOTALL)
        if match:
            contenu = match.group(1).strip()
            titre = contenu[:60] + ("..." if len(contenu) > 60 else "")
            
            return {
                'type': 'fait',
                'titre': titre,
                'contenu': contenu,
                'concept_identifie': 'culture'
            }
    
    # 3️⃣ ANECDOTES
    patterns_anecdote = [
        r'anecdote\s*[:;]?\s*(.+)',
        r'histoire\s*[:;]?\s*(.+)',
        r'(?:il\s+paraît|on\s+raconte)\s+que\s+(.+)',
    ]
    
    for pattern in patterns_anecdote:
        match = re.search(pattern, message_clean, re.IGNORECASE | re.DOTALL)
        if match:
            contenu = match.group(1).strip()
            titre = contenu[:50] + ("..." if len(contenu) > 50 else "")
            
            return {
                'type': 'anecdote',
                'titre': titre,
                'contenu': contenu,
                'concept_identifie': 'culture'
            }
    
    # 4️⃣ LISTES STRUCTURÉES
    patterns_liste = [
        r'(?:apprends?|mémorise[rz]?)\s+(?:la\s+)?liste\s+(?:des?\s+)?([^:;]+)\s*[:;]?\s*(.+)',
        r'liste\s+(?:des?\s+)?([^:;]+)\s*[:;]?\s*(.+)',
    ]
    
    for pattern in patterns_liste:
        match = re.search(pattern, message_clean, re.IGNORECASE | re.DOTALL)
        if match:
            nom_liste = match.group(1).strip()
            contenu_liste = match.group(2).strip()
            
            # Parser les éléments
            elements = []
            items = re.split(r'[\n,;]', contenu_liste)
            
            for item in items:
                item = item.strip().lstrip('- ')
                if not item:
                    continue
                
                # Pattern: nko = français
                item_match = re.search(r'([\u07C0-\u07FF]+)\s*[=:]\s*([^=:,\n]+)', item)
                if item_match:
                    elements.append({
                        'nko': item_match.group(1).strip(),
                        'fr': item_match.group(2).strip()
                    })
            
            if elements:
                return {
                    'type': 'liste',
                    'nom_liste': nom_liste,
                    'elements_liste': elements,
                    'concept_identifie': 'vocabulaire'
                }
    
    # 5️⃣ CONJUGAISONS
    patterns_conjugaison = [
        r'(?:le\s+verbe|verbe)\s+([\u07C0-\u07FF]+)\s*\(([^)]+)\)\s+(?:se\s+conjugue|conjugaison)\s*[:;]?\s*(.+)',
        r'conjugaison\s+de\s+([\u07C0-\u07FF]+)\s*\(([^)]+)\)\s*[:;]?\s*(.+)',
    ]
    
    for pattern in patterns_conjugaison:
        match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
        if match:
            verbe_nko = match.group(1).strip()
            verbe_fr = match.group(2).strip()
            contenu = match.group(3).strip()
            
            # Parser les formes
            formes = {}
            lignes = contenu.split('\n')
            
            for ligne in lignes:
                ligne = ligne.strip().lstrip('- ')
                if not ligne:
                    continue
                
                forme_match = re.search(r'([^:]+)\s*[:]\s*([\u07C0-\u07FF\s]+)', ligne)
                if forme_match:
                    temps = forme_match.group(1).strip()
                    forme = forme_match.group(2).strip()
                    formes[temps] = forme
            
            if formes:
                return {
                    'type': 'conjugaison',
                    'verbe_nko': verbe_nko,
                    'verbe_français': verbe_fr,
                    'formes': formes,
                    'concept_identifie': 'grammaire'
                }
    
    # 6️⃣ EXPRESSIONS IDIOMATIQUES
    patterns_expression = [
        r'expression\s*[:;]?\s+([\u07C0-\u07FF\s]+)\s*[=:]?\s*(?:signifie|veut dire)\s+(.+)',
        r'([\u07C0-\u07FF\s]+)\s+(?:est\s+une\s+expression|idiome)\s+(?:qui\s+)?(?:signifie|veut dire)\s+(.+)',
    ]
    
    for pattern in patterns_expression:
        match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
        if match:
            texte_nko = match.group(1).strip()
            signification = match.group(2).strip()
            
            # Extraire traduction littérale si présente
            traduction_lit = None
            lit_match = re.search(r'littéralement\s+["\']([^"\']+)["\']', signification, re.IGNORECASE)
            if lit_match:
                traduction_lit = lit_match.group(1)
            
            return {
                'type': 'expression',
                'texte_nko': texte_nko,
                'signification': signification,
                'traduction_littérale': traduction_lit,
                'concept_identifie': 'expression'
            }
    
    # 7️⃣ PROVERBES
    patterns_proverbe = [
        r'proverbe\s*[:;]?\s+([\u07C0-\u07FF\s]+)\s*[=:]?\s*(.+)',
        r'dicton\s*[:;]?\s+([\u07C0-\u07FF\s]+)\s*[=:]?\s*(.+)',
    ]
    
    for pattern in patterns_proverbe:
        match = re.search(pattern, message, re.IGNORECASE | re.DOTALL)
        if match:
            texte_nko = match.group(1).strip()
            signification = match.group(2).strip()
            
            return {
                'type': 'proverbe',
                'texte_nko': texte_nko,
                'signification': signification,
                'concept_identifie': 'culture'
            }
    
    # 8️⃣ MOTS (fallback - ancien système)
    return None


# --- PHASE 5: DÉTECTION D'APPRENTISSAGE (MOTS SIMPLES) ---
def detecter_apprentissage(message: str) -> Optional[Dict[str, str]]:
    """
    Détecte si le message est une demande d'apprentissage de MOT simple.
    Cette fonction est maintenant un fallback pour les mots simples.
    
    Pour les autres types (règles, faits, etc.), utilisez detecter_type_connaissance()
    """
    import re
    
    # Nettoyer le message
    message_clean = message.strip().lower()
    
    # Pattern 1: "apprends [que] X = Y" ou "mémorise [que] X = Y"
    pattern1 = r'(?:apprends?|mémorise[rz]?|enregistre[rz]?)\s*(?:que)?\s*[:;]?\s*(.+?)\s*[=:]\s*(.+)'
    
    # Pattern 2: "X = Y" (simple)
    pattern2 = r'^([^\s=]+)\s*[=:]\s*([^\s=]+)$'
    
    # Pattern 3: "X signifie Y"
    pattern3 = r'(.+?)\s+signifie\s+(.+)'
    
    # Pattern 4: "Y se dit X en N'ko" ou "Y se dit X en nko"
    pattern4 = r'(.+?)\s+se\s+dit\s+(.+?)\s+en\s+n.?ko'
    
    # Tester les patterns
    for pattern in [pattern1, pattern3, pattern4, pattern2]:
        match = re.search(pattern, message_clean, re.IGNORECASE)
        if match:
            word1, word2 = match.groups()
            word1 = word1.strip()
            word2 = word2.strip()
            
            # Déterminer quel est le N'ko et quel est le français
            import unicodedata
            nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
            
            has_nko_1 = bool(nko_pattern.search(word1))
            has_nko_2 = bool(nko_pattern.search(word2))
            
            if has_nko_1 and not has_nko_2:
                # word1 est N'ko, word2 est français
                return {
                    'nko': word1,
                    'français': word2,
                    'pattern': 'détecté'
                }
            elif has_nko_2 and not has_nko_1:
                # word2 est N'ko, word1 est français
                return {
                    'nko': word2,
                    'français': word1,
                    'pattern': 'détecté'
                }
    
    return None


async def apprendre_mot(
    nko_word: str,
    fr_word: str,
    llm_client: OpenAI,
    qdrant_client: AsyncQdrantClient,
    concept: str = "Appris par utilisateur",
    user_context: Optional[Dict] = None
) -> Dict[str, any]:
    """
    Apprend un nouveau mot et le stocke dans Qdrant.
    
    Args:
        nko_word: Mot en N'ko
        fr_word: Traduction française
        llm_client: Client OpenAI
        qdrant_client: Client Qdrant
        concept: Catégorie du mot
        user_context: Contexte additionnel fourni par l'utilisateur
    
    Returns:
        Dict avec status et message
    """
    try:
        import unicodedata
        
        # Normaliser les mots
        def normaliser(texte: str) -> str:
            texte = unicodedata.normalize('NFD', texte)
            texte = unicodedata.normalize('NFC', texte)
            return ' '.join(texte.split()).strip()
        
        nko_word_clean = normaliser(nko_word)
        fr_word_clean = normaliser(fr_word)
        
        logging.info(f"📚 Apprentissage: {nko_word_clean} = {fr_word_clean}")
        
        # Vérifier si le mot existe déjà
        emb_resp = await asyncio.to_thread(
            llm_client.embeddings.create,
            input=[fr_word_clean],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        # Chercher dans Qdrant
        results = await qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=5,
            with_payload=True
        )
        
        # Vérifier match exact
        for point in results.points:
            if (normaliser(point.payload.get('element_nko', '')) == nko_word_clean and
                normaliser(point.payload.get('element_français', '')) == fr_word_clean):
                logging.info(f"ℹ️ Ce mot existe déjà dans la base")
                return {
                    'status': 'exists',
                    'message': f"Je connais déjà ce mot : {nko_word_clean} = {fr_word_clean}",
                    'word_nko': nko_word_clean,
                    'word_fr': fr_word_clean
                }
        
        # Créer l'entrée
        nouvelle_entree = {
            'element_français': fr_word_clean,
            'element_nko': nko_word_clean,
            'concept_identifie': concept,
            'fait_texte': user_context.get('description') if user_context else None,
            'exemples': user_context.get('exemples') if user_context else None,
            'appris_par': 'utilisateur',
            'timestamp': str(asyncio.get_event_loop().time())
        }
        
        # Créer le point Qdrant
        point_id = str(uuid.uuid4())
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=nouvelle_entree
        )
        
        # Insérer dans Qdrant
        await qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )
        
        logging.info(f"✅ Mot appris et stocké: {nko_word_clean} = {fr_word_clean}")
        
        return {
            'status': 'success',
            'message': f"✅ J'ai appris : {nko_word_clean} = {fr_word_clean}",
            'word_nko': nko_word_clean,
            'word_fr': fr_word_clean,
            'point_id': point_id
        }
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de l'apprentissage: {e}")
        return {
            'status': 'error',
            'message': f"❌ Erreur lors de l'apprentissage: {str(e)}"
        }


# --- PHASE 5.1: APPRENTISSAGE MULTI-TYPES ---
async def apprendre_connaissance(
    connaissance_data: Dict,
    llm_client: OpenAI,
    qdrant_client: AsyncQdrantClient
) -> Dict[str, any]:
    """
    Apprend n'importe quel type de connaissance (règles, faits, listes, etc.).
    
    Args:
        connaissance_data: Dict avec 'type' et données spécifiques
        llm_client: Client OpenAI
        qdrant_client: Client Qdrant
    
    Returns:
        Dict avec status et message
    """
    try:
        import unicodedata
        import time
        
        type_conn = connaissance_data.get('type', 'mot')
        
        logging.info(f"📚 Apprentissage type '{type_conn}': {connaissance_data}")
        
        # Déterminer le texte pour l'embedding selon le type
        if type_conn == 'mot':
            texte_embedding = connaissance_data.get('français', '')
        elif type_conn == 'règle':
            texte_embedding = f"{connaissance_data.get('titre_règle', '')} {connaissance_data.get('explication_règle', '')}"
        elif type_conn in ['fait', 'anecdote']:
            texte_embedding = f"{connaissance_data.get('titre', '')} {connaissance_data.get('contenu', '')}"
        elif type_conn == 'liste':
            nom = connaissance_data.get('nom_liste', '')
            elements = connaissance_data.get('elements_liste', [])
            elements_text = ' '.join([f"{e.get('fr', '')} {e.get('nko', '')}" for e in elements])
            texte_embedding = f"{nom} {elements_text}"
        elif type_conn == 'conjugaison':
            verbe = connaissance_data.get('verbe_français', '')
            formes = connaissance_data.get('formes', {})
            formes_text = ' '.join(formes.values())
            texte_embedding = f"conjugaison {verbe} {formes_text}"
        elif type_conn in ['expression', 'proverbe']:
            texte_nko = connaissance_data.get('texte_nko', '')
            signification = connaissance_data.get('signification', '')
            texte_embedding = f"{signification} {texte_nko}"
        else:
            texte_embedding = str(connaissance_data)
        
        # Créer embedding
        emb_resp = await asyncio.to_thread(
            llm_client.embeddings.create,
            input=[texte_embedding],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        # Créer l'entrée avec métadonnées
        nouvelle_entree = {
            **connaissance_data,
            'appris_par': 'utilisateur',
            'date_ajout': str(time.time())
        }
        
        # Créer le point Qdrant
        point_id = str(uuid.uuid4())
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=nouvelle_entree
        )
        
        # Insérer dans Qdrant
        await qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=[point]
        )
        
        # Message de confirmation selon le type
        if type_conn == 'mot':
            message = f"✅ J'ai appris : {connaissance_data.get('element_nko')} = {connaissance_data.get('element_français')}"
        elif type_conn == 'règle':
            message = f"✅ Règle grammaticale mémorisée : {connaissance_data.get('titre_règle')}"
        elif type_conn == 'fait':
            message = f"✅ Fait culturel mémorisé : {connaissance_data.get('titre')}"
        elif type_conn == 'anecdote':
            message = f"✅ Anecdote mémorisée : {connaissance_data.get('titre')}"
        elif type_conn == 'liste':
            nb_elements = len(connaissance_data.get('elements_liste', []))
            message = f"✅ Liste '{connaissance_data.get('nom_liste')}' mémorisée ({nb_elements} éléments)"
        elif type_conn == 'conjugaison':
            message = f"✅ Conjugaison du verbe {connaissance_data.get('verbe_nko')} ({connaissance_data.get('verbe_français')}) mémorisée"
        elif type_conn == 'expression':
            message = f"✅ Expression mémorisée : {connaissance_data.get('texte_nko')}"
        elif type_conn == 'proverbe':
            message = f"✅ Proverbe mémorisé : {connaissance_data.get('texte_nko')}"
        else:
            message = f"✅ Connaissance de type '{type_conn}' mémorisée"
        
        logging.info(f"✅ Connaissance apprise et stockée: {message}")
        
        return {
            'status': 'success',
            'message': message,
            'type': type_conn,
            'point_id': point_id
        }
        
    except Exception as e:
        logging.error(f"❌ Erreur lors de l'apprentissage: {e}")
        return {
            'status': 'error',
            'message': f"❌ Erreur lors de l'apprentissage: {str(e)}"
        }


# 🆕 PHASE 3 : FONCTIONS DE TRANSCRIPTION PHONÉTIQUE
def transcrire_nko_phonetique(mot_nko: str) -> str:
    """Transcrit un mot N'ko en phonétique latine."""
    transcription = ""
    for char in mot_nko:
        transcription += NKO_PHONETIC_MAP.get(char, char)
    return transcription

def decomposer_syllabe_nko(mot_nko: str) -> List[str]:
    """Décompose un mot N'ko en syllabes phonétiques."""
    import re
    
    # Voyelles N'ko
    voyelles = 'ߊߋߌߍߎߏߐ'
    
    # Pattern: (Consonne)+ Voyelle (Modificateurs)*
    pattern = f'[^{voyelles}]*[{voyelles}][߲߫߬߭߮߯߰߱]*'
    
    syllabes = re.findall(pattern, mot_nko)
    
    # Si rien trouvé, retourner le mot entier
    if not syllabes:
        return [mot_nko]
    
    return syllabes


# --- PHASE 5.1: FORMATAGE CONTEXTE MULTI-TYPES ---
def formater_connaissance_pour_contexte(payload: Dict) -> str:
    """
    Formate une connaissance pour le contexte RAG selon son type.
    
    Args:
        payload: Données de la connaissance depuis Qdrant
    
    Returns:
        Ligne formatée pour le contexte
    """
    type_conn = payload.get('type', 'mot')
    
    if type_conn == 'mot':
        # Format classique pour les mots
        fr = payload.get('element_français', '')
        nko = payload.get('element_nko', '')
        concept = payload.get('concept_identifie', '')
        ligne = f"- {fr} = {nko} ({concept})"
        
        # Enrichissements
        valeur_num = payload.get('valeur_numerique')
        if valeur_num is not None:
            ligne += f" | valeur: {valeur_num}"
        
        fait = payload.get('fait_texte')
        if fait:
            ligne += f" | info: {fait}"
        
        exemples = payload.get('exemples')
        if exemples:
            ligne += f" | ex: {exemples[0] if isinstance(exemples, list) else exemples}"
        
        # Phonétique
        phonetique = transcrire_nko_phonetique(nko)
        if phonetique and phonetique != nko:
            ligne += f" | prononciation: {phonetique}"
        
        return ligne
    
    elif type_conn == 'règle':
        titre = payload.get('titre_règle', '')
        explication = payload.get('explication_règle', '')
        return f"- [RÈGLE] {titre}: {explication}"
    
    elif type_conn == 'fait':
        titre = payload.get('titre', '')
        contenu = payload.get('contenu', '')
        return f"- [FAIT] {titre}: {contenu}"
    
    elif type_conn == 'anecdote':
        titre = payload.get('titre', '')
        contenu = payload.get('contenu', '')
        return f"- [ANECDOTE] {titre}: {contenu}"
    
    elif type_conn == 'liste':
        nom_liste = payload.get('nom_liste', '')
        elements = payload.get('elements_liste', [])
        elements_str = ', '.join([f"{e.get('fr')}={e.get('nko')}" for e in elements[:5]])
        if len(elements) > 5:
            elements_str += f"... ({len(elements)} éléments)"
        return f"- [LISTE] {nom_liste}: {elements_str}"
    
    elif type_conn == 'conjugaison':
        verbe_nko = payload.get('verbe_nko', '')
        verbe_fr = payload.get('verbe_français', '')
        formes = payload.get('formes', {})
        formes_str = ', '.join([f"{temps}: {forme}" for temps, forme in list(formes.items())[:3]])
        return f"- [CONJUGAISON] {verbe_nko} ({verbe_fr}): {formes_str}"
    
    elif type_conn == 'expression':
        texte_nko = payload.get('texte_nko', '')
        signification = payload.get('signification', '')
        trad_lit = payload.get('traduction_littérale', '')
        ligne = f"- [EXPRESSION] {texte_nko} = {signification}"
        if trad_lit:
            ligne += f" (litt: {trad_lit})"
        return ligne
    
    elif type_conn == 'proverbe':
        texte_nko = payload.get('texte_nko', '')
        signification = payload.get('signification', '')
        return f"- [PROVERBE] {texte_nko} = {signification}"
    
    else:
        return f"- {payload}"


def recherche_phonetique(query: str, mot_nko: str) -> float:
    """Calcule un score de similarité phonétique entre query et mot N'ko."""
    # Transcrire le mot N'ko
    transcription = transcrire_nko_phonetique(mot_nko)
    
    # Normaliser les deux chaînes
    query_norm = query.lower().strip()
    transcription_norm = transcription.lower().strip()
    
    # Score basique : distance de Levenshtein simplifiée
    if query_norm == transcription_norm:
        return 1.0
    
    if query_norm in transcription_norm or transcription_norm in query_norm:
        return 0.8
    
    # Calcul de similarité basique
    matches = sum(1 for a, b in zip(query_norm, transcription_norm) if a == b)
    max_len = max(len(query_norm), len(transcription_norm))
    
    return matches / max_len if max_len > 0 else 0.0


# --- ENDPOINT CHAT AVEC MÉMOIRE INTELLIGENTE ---
@app.post('/chat', response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    global LLM_CLIENT, QDRANT_CLIENT

    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='LLM non initialisé')

    # 🆕 PHASE 6: Gestion de la session
    session_id = get_or_create_session(req.session_id)
    
    debug_info = {} if req.debug else None
    rag_active = req.rag_enabled and (QDRANT_CLIENT is not None)
    contexte_rag_text = '[Aucune donnée en mémoire]'

    try:
        # 🆕 PHASE 6: Vérifier si c'est une demande d'analyse de mémoire
        intention_memoire = await analyser_intention_memoire(req.user_message, session_id, LLM_CLIENT)
        
        if intention_memoire:
            # C'est une demande d'analyse de l'historique !
            logging.info(f"🧠 Intention mémoire détectée: {intention_memoire['type']}")
            
            response_text = await executer_action_memoire(intention_memoire, session_id, LLM_CLIENT)
            
            # Ajouter à l'historique
            ajouter_message_memoire(session_id, 'user', req.user_message)
            ajouter_message_memoire(session_id, 'assistant', response_text)
            
            return ChatResponse(
                response_text=response_text,
                session_id=session_id,
                memory_update=None,
                debug_info={
                    'intention_memoire': intention_memoire,
                    'historique_size': len(CONVERSATION_MEMORY[session_id])
                } if req.debug else None
            )
        
        # PHASE 5.1: Détecter type de connaissance (règles, faits, listes, etc.) - PRIORITÉ HAUTE
        type_info = detecter_type_connaissance(req.user_message)
        
        if type_info:
            # C'est une règle, fait, anecdote, liste, conjugaison, expression ou proverbe !
            logging.info(f"🎓 {type_info['type'].upper()} détecté: {type_info}")
            
            resultat = await apprendre_connaissance(
                connaissance_data=type_info,
                llm_client=LLM_CLIENT,
                qdrant_client=QDRANT_CLIENT
            )
            
            # Ajouter à l'historique
            ajouter_message_memoire(session_id, 'user', req.user_message)
            ajouter_message_memoire(session_id, 'assistant', resultat['message'])
            
            return ChatResponse(
                response_text=resultat['message'],
                session_id=session_id,
                memory_update=None,
                debug_info={
                    'apprentissage': True,
                    'type': type_info['type'],
                    'status': resultat['status'],
                    'details': resultat
                } if req.debug else None
            )
        
        # PHASE 5: Détecter apprentissage de MOT simple (fallback)
        apprentissage_info = detecter_apprentissage(req.user_message)
        
        if apprentissage_info:
            # C'est un mot simple !
            logging.info(f"🎓 Apprentissage MOT détecté: {apprentissage_info}")
            
            resultat = await apprendre_mot(
                nko_word=apprentissage_info['nko'],
                fr_word=apprentissage_info['français'],
                llm_client=LLM_CLIENT,
                qdrant_client=QDRANT_CLIENT,
                concept="Appris par utilisateur"
            )
            
            # Ajouter à l'historique
            ajouter_message_memoire(session_id, 'user', req.user_message)
            ajouter_message_memoire(session_id, 'assistant', resultat['message'])
            
            return ChatResponse(
                response_text=resultat['message'],
                session_id=session_id,
                memory_update=None,
                debug_info={
                    'apprentissage': True,
                    'type': 'mot',
                    'status': resultat['status'],
                    'details': resultat
                } if req.debug else None
            )
        
        # Si pas d'apprentissage, continuer normalement
        if rag_active:
            try:
                # Pré-traiter la question
                question_enrichie, traductions_contexte = await pretraiter_question(
                    req.user_message, 
                    LLM_CLIENT, 
                    QDRANT_CLIENT
                )
                
                if req.debug:
                    debug_info['question_enrichie'] = question_enrichie
                    debug_info['traductions_contexte'] = traductions_contexte
                
                # Extraire le mot-clé
                mot_cle = await extraire_mot_cle(question_enrichie, LLM_CLIENT)
                if req.debug:
                    debug_info['mot_cle_extrait'] = mot_cle

                # 🆕 PHASE 6: Recherche intelligente filtrée (priorité score=1.0)
                hits = await recherche_intelligente_filtree(mot_cle, LLM_CLIENT, QDRANT_CLIENT)

                # Afficher top résultats
                logging.info(f"📊 RÉSULTATS pour '{mot_cle}':")
                for i, h in enumerate(hits[:10], 1):
                    logging.info(f"  #{i}: score={h.score:.4f} -> {h.payload.get('element_français', 'N/A')}")
                
                if req.debug:
                    debug_info['top_results'] = [
                        {'score': h.score, 'payload': h.payload} 
                        for h in hits[:10]
                    ]

                # Formater le contexte RAG
                if hits:
                    logging.info(f"✅ {len(hits)} résultat(s) pertinent(s)")
                    
                    # 🎯 Si score parfait, mettre en évidence
                    if hits[0].score >= 0.999:
                        contexte_rag_text = "⭐ RÉPONSE EXACTE TROUVÉE:\n"
                    else:
                        contexte_rag_text = "📚 Connaissances pertinentes:\n"
                    
                    lignes = []
                    for h in hits:
                        ligne = formater_connaissance_pour_contexte(h.payload)
                        lignes.append(ligne)
                    contexte_rag_text += '\n'.join(lignes)
                else:
                    logging.warning(f"⚠️ Aucun résultat trouvé")
                    contexte_rag_text = "[Aucune connaissance pertinente trouvée]"

                # Ajouter les traductions contextuelles
                if traductions_contexte:
                    contexte_extra = '\n'.join(
                        f"- {t['français']} = {t['nko']}"
                        for t in traductions_contexte
                    )
                    contexte_rag_text = contexte_extra + '\n' + contexte_rag_text

            except Exception as e:
                logging.error(f"❌ Erreur RAG: {e}", exc_info=True)
                if req.debug:
                    debug_info['rag_error'] = str(e)
                rag_active = False

        # 🆕 PHASE 6: Formater l'historique de conversation
        historique_conversation = formater_historique_conversation(session_id, limite=20)
        
        # Debug: afficher le contexte envoyé
        logging.info(f"📤 CONTEXTE ENVOYÉ AU LLM:\n{contexte_rag_text}")
        logging.info(f"📜 HISTORIQUE CONVERSATION:\n{historique_conversation[:500]}...")

        # 🆕 PHASE 6: Build prompt avec mémoire intelligente
        prompt = PROMPT_SYSTEM_INTELLIGENT.format(
            historique_conversation=historique_conversation,
            contexte_rag=contexte_rag_text,
            user_message=req.user_message
        )

        # Call LLM
        llm_resp = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=500  # Augmenté pour résumés
        )
        llm_output = llm_resp.choices[0].message.content
        logging.info("✅ Réponse LLM reçue")

        # Extract text and memory JSON
        def separer_texte_et_json(output: str):
            start = output.find('```json')
            if start == -1:
                return output.strip(), None
            end = output.find('```', start + 7)
            if end == -1:
                return output.strip(), None
            text = output[:start].strip()
            json_str = output[start + 7:end].strip()
            try:
                return text, json.loads(json_str)
            except:
                return output.strip(), None

        response_text, memory_json = separer_texte_et_json(llm_output)
        
        # 🆕 PHASE 6: Ajouter à l'historique
        ajouter_message_memoire(session_id, 'user', req.user_message)
        ajouter_message_memoire(session_id, 'assistant', response_text)

        return ChatResponse(
            response_text=response_text,
            session_id=session_id,
            memory_update=memory_json,
            debug_info=debug_info
        )
    
    except Exception as e:
        logging.error(f"❌ Erreur critique dans /chat: {e}", exc_info=True)
        return ChatResponse(
            response_text=f"Erreur interne : {str(e)}",
            session_id=session_id,
            memory_update=None,
            debug_info={'error': str(e)} if req.debug else None
        )


# --- ENDPOINT AJOUT TRADUCTION ---
@app.post('/add_translation', response_model=dict)
async def add_translation(entries: List[TranslationEntry]):
    """Ajoute une liste de traductions à Qdrant."""
    global LLM_CLIENT, QDRANT_CLIENT

    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='LLM non initialisé')
    if QDRANT_CLIENT is None:
        raise HTTPException(status_code=503, detail='Qdrant non initialisé')

    if not entries:
        return {"status": "warning", "message": "Aucune entrée fournie."}

    try:
        french_elements = [entry.element_français for entry in entries]
        num_elements = len(french_elements)

        logging.info(f"🔄 Génération de {num_elements} embeddings...")
        emb_resp = await asyncio.to_thread(
            LLM_CLIENT.embeddings.create,
            input=french_elements,
            model=EMBEDDING_MODEL
        )
        vectors = [data.embedding for data in emb_resp.data]

        points_to_upsert: List[PointStruct] = []
        for i, entry in enumerate(entries):
            payload = entry.model_dump()
            
            point = PointStruct(
                id=uuid.uuid4().int >> 64,
                vector=vectors[i],
                payload=payload
            )
            points_to_upsert.append(point)

        logging.info(f"💾 Upsert de {num_elements} points dans '{COLLECTION_NAME}'...")
        operation_info = await QDRANT_CLIENT.upsert(
            collection_name=COLLECTION_NAME,
            points=points_to_upsert,
            wait=True
        )

        logging.info(f"✅ {num_elements} traductions ajoutées. Status: {operation_info.status.value}")
        return {
            "status": "success",
            "message": f"{num_elements} traductions ajoutées à Qdrant.",
            "qdrant_status": operation_info.status.value,
            "elements_added": num_elements
        }

    except Exception as e:
        logging.error(f"❌ Erreur ajout traduction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erreur: {str(e)}")


# 🆕 PHASE 6: ENDPOINTS MÉMOIRE
@app.get('/memory/{session_id}')
async def get_memory(session_id: str, limit: int = 100):
    """Récupère l'historique d'une session."""
    if session_id not in CONVERSATION_MEMORY:
        raise HTTPException(status_code=404, detail='Session non trouvée')
    
    historique = list(CONVERSATION_MEMORY[session_id])
    
    return {
        'session_id': session_id,
        'total_messages': len(historique),
        'messages': historique[-limit:] if limit else historique
    }


@app.delete('/memory/{session_id}')
async def clear_memory(session_id: str):
    """Efface l'historique d'une session."""
    if session_id in CONVERSATION_MEMORY:
        del CONVERSATION_MEMORY[session_id]
        logging.info(f"🗑️ Session {session_id} effacée")
        return {'status': 'success', 'message': f'Mémoire de la session {session_id} effacée'}
    
    raise HTTPException(status_code=404, detail='Session non trouvée')


@app.get('/sessions')
async def list_sessions():
    """Liste toutes les sessions actives."""
    sessions_info = []
    
    for session_id, messages in CONVERSATION_MEMORY.items():
        sessions_info.append({
            'session_id': session_id,
            'message_count': len(messages),
            'last_message': messages[-1]['timestamp'] if messages else None
        })
    
    return {
        'total_sessions': len(CONVERSATION_MEMORY),
        'sessions': sessions_info
    }


# --- ENDPOINTS UTILITAIRES ---
@app.get('/')
async def root():
    count = 0
    if QDRANT_CLIENT:
        try:
            c = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
            count = c.count
        except:
            pass
    
    return {
        'service': 'Nkotronic API',
        'version': '2.4.0',
        'features': ['RAG', 'Multi-types', 'Mémoire conversationnelle (100 messages)', 'Intelligence avancée'],
        'status': 'running',
        'llm_status': 'ok' if LLM_CLIENT else 'error',
        'qdrant_status': 'ok' if QDRANT_CLIENT else 'disabled',
        'memory_size': count,
        'active_sessions': len(CONVERSATION_MEMORY)
    }

@app.get('/health')
async def health():
    health_status = {
        'llm': LLM_CLIENT is not None,
        'qdrant': QDRANT_CLIENT is not None,
        'memory': True
    }
    
    if not all(health_status.values()):
        raise HTTPException(status_code=503, detail=health_status)
    
    return {'status': 'healthy', 'components': health_status}

@app.get('/stats')
async def stats():
    """Statistiques de la base de données"""
    if QDRANT_CLIENT is None:
        raise HTTPException(status_code=503, detail='Qdrant non disponible')
    
    try:
        count = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
        sample = await QDRANT_CLIENT.scroll(
            collection_name=COLLECTION_NAME,
            limit=10,
            with_payload=True
        )
        
        return {
            'total_points': count.count,
            'collection_name': COLLECTION_NAME,
            'sample': [p.payload for p in sample[0]],
            'active_sessions': len(CONVERSATION_MEMORY),
            'total_conversation_messages': sum(len(msgs) for msgs in CONVERSATION_MEMORY.values())
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/search_direct')
async def search_direct(word: str):
    """Recherche directe dans Qdrant pour debug"""
    if QDRANT_CLIENT is None or LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='Services non disponibles')
    
    try:
        emb_resp = await asyncio.to_thread(
            LLM_CLIENT.embeddings.create,
            input=[word],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        result = await QDRANT_CLIENT.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=20,
            with_payload=True
        )
        hits = result.points
        
        return {
            'query': word,
            'results_count': len(hits),
            'top_10': [
                {
                    'score': h.score,
                    'element_français': h.payload.get('element_français', 'N/A'),
                    'element_nko': h.payload.get('element_nko', 'N/A'),
                    'concept': h.payload.get('concept_identifie', 'N/A')
                }
                for h in hits[:10]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🆕 PHASE 3: Endpoint de test phonétique
@app.post('/transcribe_phonetic')
async def transcribe_phonetic(nko_text: str):
    """Transcrit un texte N'ko en phonétique latine"""
    try:
        transcription = transcrire_nko_phonetique(nko_text)
        syllabes = decomposer_syllabe_nko(nko_text)
        syllabes_phonetiques = [transcrire_nko_phonetique(s) for s in syllabes]
        
        return {
            'nko_original': nko_text,
            'transcription_complete': transcription,
            'syllabes_nko': syllabes,
            'syllabes_phonetiques': syllabes_phonetiques
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 🆕 PHASE 4: Endpoint de test de raisonnement
@app.post('/test_reasoning')
async def test_reasoning(question: str, session_id: Optional[str] = None, debug: bool = True):
    """Teste les capacités de raisonnement avancé de Nkotronic"""
    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='LLM non disponible')
    
    try:
        # Simuler une requête avec debug activé
        req = ChatRequest(
            user_message=question,
            session_id=session_id,
            rag_enabled=True,
            debug=debug
        )
        
        response = await chat_endpoint(req)
        
        return {
            'question': question,
            'response': response.response_text,
            'session_id': response.session_id,
            'debug_info': response.debug_info,
            'reasoning_applied': True
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))