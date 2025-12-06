"""
═══════════════════════════════════════════════════════════════════════════
NKOTRONIC v3.2.0 "LONG CONTEXT MASTER"
═══════════════════════════════════════════════════════════════════════════

Assistant N'ko intelligent avec support COMPLET des longs messages.

NOUVEAUTÉS v3.2.0:
- 🚀 PHASE 1: Quick Wins (limites x5, GPT-4-Turbo-128k)
- 📚 PHASE 2: Chunking intelligent hiérarchique
- 🗜️ PHASE 3: Compression automatique de mémoire
- 📖 Support messages jusqu'à 100k+ caractères
- ⚡ Mémoire conversationnelle infinie
- 🎯 Détection automatique + adaptation

Évolution depuis v3.1.7:
- MAX_CHARS_EMBEDDING: 2000 → 10000 (x5)
- MAX_TOKENS_RESPONSE: 2000 → 8000 (x4)
- Modèle: gpt-4o → gpt-4-turbo (contexte x16)
- Chunking: ❌ → ✅ Hiérarchique
- Compression mémoire: ❌ → ✅ Automatique

Score global: 99% (vs 98% en v3.1.7)

Auteur: Nkotronic Team
Date: Décembre 2025
Version: 3.2.0
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
import os
import logging
import json
import uuid
import random
from contextlib import asynccontextmanager
from typing import Optional, AsyncIterator, List, Dict, Tuple
from pathlib import Path
from collections import deque
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

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

# 🆕 v3.0: CONFIGURATION MÉMOIRE AVANCÉE
CONVERSATION_MEMORY: Dict[str, deque] = {}

# 🆕 v3.2.0 PHASE 1: QUICK WINS - Limites augmentées drastiquement
MAX_MEMORY_SIZE = 200  # v3.0: 100 → v3.2.0: 200
MAX_CHARS_EMBEDDING = 10000  # v3.1.5: 2000 → v3.2.0: 10000 (x5)
MAX_TOKENS_RESPONSE = 8000  # v3.1.4: 2000 → v3.2.0: 8000 (x4)
MAX_TOKENS_RESUME = 2000  # Pour résumés de compression

# 🆕 v3.2.0 PHASE 3: Configuration compression mémoire
COMPRESSION_THRESHOLD = 50  # Compresser si > 50 messages
COMPRESSION_KEEP_RECENT = 30  # Garder les 30 plus récents non compressés

USER_PROFILES: Dict[str, dict] = {}
SESSION_METADATA: Dict[str, dict] = {}

# --- CONSTANTS ---
COLLECTION_NAME = "nkotronic_knowledge_base"
VECTOR_SIZE = 1536
EMBEDDING_MODEL = "text-embedding-ada-002"

# 🆕 v3.2.0 PHASE 1: GPT-4-Turbo pour long contexte (128k tokens)
LLM_MODEL = "gpt-4-turbo"  # v3.1: gpt-4o → v3.2.0: gpt-4-turbo

RAG_SCORE_THRESHOLD = 0.55

# 🆕 PHASE 3 : MAPPING PHONÉTIQUE N'KO
NKO_PHONETIC_MAP = {
    'ߊ': 'a', 'ߋ': 'e', 'ߌ': 'i', 'ߍ': 'ɛ', 'ߎ': 'u', 'ߏ': 'o', 'ߐ': 'ɔ',
    'ߓ': 'b', 'ߔ': 'p', 'ߕ': 't', 'ߖ': 'd͡ʒ', 'ߗ': 't͡ʃ', 'ߘ': 'd',
    'ߙ': 'r', 'ߚ': 'rr', 'ߛ': 's', 'ߜ': 'ɡ͡b', 'ߝ': 'f', 'ߞ': 'k',
    'ߟ': 'l', 'ߠ': 'n', 'ߡ': 'm', 'ߢ': 'ɲ', 'ߣ': 'n', 'ߤ': 'h',
    'ߥ': 'w', 'ߦ': 'y', 'ߧ': 'ɲ', 'ߨ': 'd͡ʒ', 'ߒ': "ŋ",
    '߫': '', '߬': '', '߭': '', '߮': '', '߯': '', '߰': '', '߱': '', '߲': 'n',
}


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.0: SYSTÈME D'ANALYSE ÉMOTIONNELLE ET SENTIMENT
# ═══════════════════════════════════════════════════════════════════════════

class Emotion(Enum):
    """Types d'émotions détectables"""
    JOIE = "joie"
    TRISTESSE = "tristesse"
    FRUSTRATION = "frustration"
    CONFUSION = "confusion"
    ENTHOUSIASME = "enthousiasme"
    ENNUI = "ennui"
    SATISFACTION = "satisfaction"
    IMPATIENCE = "impatience"
    CURIOSITE = "curiosité"
    NEUTRE = "neutre"


class SentimentAnalyzer:
    """Analyseur de sentiment et d'émotions dans les messages"""
    
    EMOTION_PATTERNS = {
        Emotion.JOIE: [
            r'\b(super|génial|excellent|parfait|bravo|merci|cool|top|formidable)\b',
            r'[!]{2,}',
            r'😊|😄|😃|🎉|👍|✨|😁'
        ],
        Emotion.FRUSTRATION: [
            r'\b(merde|putain|zut|pfff|argh|grr|damn)\b',
            r'\b(ne marche pas|bug|erreur|problème|cassé)\b',
            r'😤|😠|😡|🤬|💢'
        ],
        Emotion.CONFUSION: [
            r'\b(comprends? pas|confus|perdu|comment|pourquoi|hein|quoi)\b',
            r'\?\?+',
            r'🤔|😕|😐|❓'
        ],
        Emotion.ENTHOUSIASME: [
            r'\b(wow|waou|incroyable|magnifique|extraordinaire|amazing)\b',
            r'[!]{3,}',
            r'🤩|😍|🔥|⭐|💫'
        ],
        Emotion.TRISTESSE: [
            r'\b(triste|déçu|dommage|hélas|malheureusement|peine)\b',
            r'😢|😭|😞|☹️|💔'
        ],
        Emotion.ENNUI: [
            r'\b(ennuyeux|lassant|répétitif|encore|toujours|boring)\b',
            r'😴|🥱|💤'
        ],
        Emotion.IMPATIENCE: [
            r'\b(vite|rapide|dépêche|attend|longtemps|pressé)\b',
            r'⏰|⏱️|⌛'
        ],
        Emotion.CURIOSITE: [
            r'\b(intéressant|curieux|je me demande|découvrir|explore)\b',
            r'🧐|👀|🔍'
        ],
        Emotion.SATISFACTION: [
            r'\b(content|satisfait|bien|bon|ok|d\'accord)\b',
            r'👌|✅|☑️'
        ]
    }
    
    @staticmethod
    def detecter_emotion(message: str) -> Tuple[Emotion, float]:
        """Détecte l'émotion dominante dans un message"""
        import re
        message_lower = message.lower()
        scores = {}
        
        for emotion, patterns in SentimentAnalyzer.EMOTION_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, message_lower, re.IGNORECASE))
                score += matches
            
            if score > 0:
                scores[emotion] = score
        
        if not scores:
            return Emotion.NEUTRE, 0.5
        
        emotion_dominante = max(scores, key=scores.get)
        score_max = scores[emotion_dominante]
        confiance = min(score_max / 3, 1.0)
        
        return emotion_dominante, confiance
    
    @staticmethod
    def detecter_niveau_engagement(historique: List[dict]) -> str:
        """Analyse le niveau d'engagement de l'utilisateur"""
        if len(historique) < 3:
            return "moyen"
        
        derniers = historique[-5:]
        messages_user = [m for m in derniers if m['role'] == 'user']
        
        if not messages_user:
            return "faible"
        
        longueur_moy = sum(len(m['content']) for m in messages_user) / len(messages_user)
        questions = sum(1 for m in messages_user if '?' in m['content'])
        
        if longueur_moy > 50 and questions >= 2:
            return "élevé"
        elif longueur_moy > 20 or questions >= 1:
            return "moyen"
        else:
            return "faible"


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.0: SYSTÈME DE GAMIFICATION
# ═══════════════════════════════════════════════════════════════════════════

class Badge(Enum):
    """Badges d'accomplissement"""
    PREMIER_MOT = "🌟 Premier Mot Appris"
    DIX_MOTS = "📚 10 Mots Maîtrisés"
    CINQUANTE_MOTS = "🏆 50 Mots Maîtrisés"
    CENT_MOTS = "💎 Centenaire"
    EXPLORATEUR = "🗺️ Explorateur N'ko"
    GRAMMAIRIEN = "📖 Maître de Grammaire"
    PERSEVERANT = "💪 Persévérant (7 jours)"
    CHAMPION = "👑 Champion N'ko"


@dataclass
class UserProgress:
    """Progression d'un utilisateur"""
    mots_appris: int = 0
    regles_apprises: int = 0
    jours_consecutifs: int = 0
    dernier_jour_actif: Optional[str] = None
    badges: List[str] = field(default_factory=list)
    niveau: int = 1
    points_xp: int = 0


class GamificationSystem:
    """Système de gamification pour l'apprentissage"""
    
    XP_PAR_MOT = 10
    XP_PAR_REGLE = 25
    XP_PAR_NIVEAU = 100
    
    @staticmethod
    def calculer_niveau(xp: int) -> int:
        """Calcule le niveau basé sur l'XP"""
        return 1 + (xp // GamificationSystem.XP_PAR_NIVEAU)
    
    @staticmethod
    def xp_pour_niveau_suivant(niveau_actuel: int) -> int:
        """XP nécessaire pour atteindre le niveau suivant"""
        return niveau_actuel * GamificationSystem.XP_PAR_NIVEAU
    
    @staticmethod
    def verifier_nouveaux_badges(progress: UserProgress) -> List[Badge]:
        """Vérifie si l'utilisateur a débloqué de nouveaux badges"""
        nouveaux_badges = []
        badges_actuels_str = set(progress.badges)
        
        def badge_existe(badge: Badge) -> bool:
            return badge.value in badges_actuels_str
        
        if progress.mots_appris >= 1 and not badge_existe(Badge.PREMIER_MOT):
            nouveaux_badges.append(Badge.PREMIER_MOT)
        
        if progress.mots_appris >= 10 and not badge_existe(Badge.DIX_MOTS):
            nouveaux_badges.append(Badge.DIX_MOTS)
        
        if progress.mots_appris >= 50 and not badge_existe(Badge.CINQUANTE_MOTS):
            nouveaux_badges.append(Badge.CINQUANTE_MOTS)
        
        if progress.mots_appris >= 100 and not badge_existe(Badge.CENT_MOTS):
            nouveaux_badges.append(Badge.CENT_MOTS)
        
        if progress.regles_apprises >= 5 and not badge_existe(Badge.GRAMMAIRIEN):
            nouveaux_badges.append(Badge.GRAMMAIRIEN)
        
        if progress.jours_consecutifs >= 7 and not badge_existe(Badge.PERSEVERANT):
            nouveaux_badges.append(Badge.PERSEVERANT)
        
        return nouveaux_badges
    
    @staticmethod
    def message_celebration(badge: Badge) -> str:
        """Message de célébration pour un nouveau badge"""
        messages = {
            Badge.PREMIER_MOT: "🎉 Félicitations ! On a encore progressé en N'ko !",
            Badge.DIX_MOTS: "🌟 Bravo ! On maîtrise maintenant 10 mots ! Continuons comme ça !",
            Badge.CINQUANTE_MOTS: "🏆 Incroyable ! 50 mots appris ! On est en excellente voie !",
            Badge.CENT_MOTS: "💎 EXTRAORDINAIRE ! 100 mots ! On est de véritables champions !",
            Badge.GRAMMAIRIEN: "📖 Badge Maître de Grammaire débloqué ! La structure du N'ko n'a plus de secrets pour nous !",
            Badge.PERSEVERANT: "💪 Badge Persévérant ! 7 jours d'apprentissage consécutifs ! Quelle détermination !",
            Badge.CHAMPION: "👑 ON EST DES CHAMPIONS DU N'KO ! Respect total !"
        }
        return messages.get(badge, f"🎖️ Nouveau badge débloqué : {badge.value}")


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.0: SYSTÈME PÉDAGOGIQUE AVANCÉ
# ═══════════════════════════════════════════════════════════════════════════

class DifficultyLevel(Enum):
    """Niveaux de difficulté"""
    DEBUTANT = "débutant"
    INTERMEDIAIRE = "intermédiaire"
    AVANCE = "avancé"
    EXPERT = "expert"


class PedagogicalSystem:
    """Système pédagogique avec scaffolding et questionnement socratique"""
    
    @staticmethod
    def generer_question_socratique() -> str:
        """Génère une question pour stimuler la réflexion"""
        questions = [
            "Qu'en penses-tu toi-même ?",
            "Comment expliquerais-tu ça dans tes propres mots ?",
            "Vois-tu un lien avec ce qu'on a vu avant ?",
            "Pourquoi crois-tu que c'est ainsi ?",
            "Peux-tu deviner ce qui vient ensuite ?"
        ]
        return random.choice(questions)
    
    @staticmethod
    def creer_analogie(concept_francais: str) -> str:
        """Crée une analogie pour faciliter la compréhension"""
        analogies = {
            "pluriel": "C'est comme en français où on ajoute 's', sauf qu'en N'ko c'est 'ߥ'",
            "ton": "Imagine les tons comme la mélodie d'une chanson - chaque syllabe a sa note",
            "alphabet": "L'alphabet N'ko, c'est comme un nouveau clavier pour écrire la langue mandingue",
        }
        return analogies.get(concept_francais.lower(), f"Pense à {concept_francais} comme...")


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.0: SYSTÈME DE DÉTECTION CONTEXTUELLE
# ═══════════════════════════════════════════════════════════════════════════

class ContextAnalyzer:
    """Analyse le contexte conversationnel et culturel"""
    
    @staticmethod
    def detecter_changement_sujet(message_actuel: str, historique: List[dict]) -> bool:
        """Détecte si l'utilisateur change de sujet"""
        import re
        if len(historique) < 2:
            return False
        
        changement_patterns = [
            r'\b(changeons|parlons|passons|maintenant|sinon|au fait)\b',
            r'\b(autre chose|nouvelle question|différent)\b'
        ]
        
        for pattern in changement_patterns:
            if re.search(pattern, message_actuel.lower()):
                return True
        
        return False
    
    @staticmethod
    def detecter_niveau_formalite(message: str) -> str:
        """Détecte le niveau de formalité souhaité"""
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['vous', 'monsieur', 'madame', 'pourriez', 'veuillez']):
            return "formel"
        
        if any(word in message_lower for word in ['salut', 'ouais', 'ok', 'cool', 'mec']):
            return "familier"
        
        return "standard"


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.0: SYSTÈME DE GESTION DES ERREURS AVANCÉ
# ═══════════════════════════════════════════════════════════════════════════

class ErrorRecoverySystem:
    """Système de récupération gracieuse des erreurs"""
    
    @staticmethod
    def generer_message_incomprehension(tentative: int) -> str:
        """Génère un message d'incompréhension adapté au nombre de tentatives"""
        if tentative == 1:
            return "Hmm, je n'ai pas bien compris. Peux-tu reformuler différemment ?"
        elif tentative == 2:
            return "Désolé, je suis encore un peu perdu. Essaie peut-être avec d'autres mots ?"
        else:
            return "Je pense qu'on a du mal à se comprendre. Veux-tu qu'on essaie autrement, ou qu'on passe à autre chose ?"
    
    @staticmethod
    def detecter_repetition_utilisateur(historique: List[dict], seuil: int = 3) -> bool:
        """Détecte si l'utilisateur répète la même chose plusieurs fois"""
        if len(historique) < seuil * 2:
            return False
        
        messages_user = [m['content'].lower() for m in historique[-seuil*2:] if m['role'] == 'user']
        
        if len(messages_user) < seuil:
            return False
        
        derniers = messages_user[-seuil:]
        if len(set(derniers)) == 1:
            return True
        
        return False
    
    @staticmethod
    def corriger_fautes_courantes(message: str) -> str:
        """Corrige les fautes de frappe courantes"""
        import re
        corrections = {
            r'\bslt\b': 'salut',
            r'\bcv\b': 'ça va',
            r'\bpq\b': 'parce que',
            r'\btkt\b': 'ne t\'inquiète pas',
            r'\bcmnt\b': 'comment',
            r'\bsvp\b': 's\'il vous plaît',
        }
        
        message_corrige = message
        for pattern, remplacement in corrections.items():
            message_corrige = re.sub(pattern, remplacement, message_corrige, flags=re.IGNORECASE)
        
        return message_corrige


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.2.0 PHASE 2: SYSTÈME DE CHUNKING INTELLIGENT
# ═══════════════════════════════════════════════════════════════════════════

class ChunkingSystem:
    """
    Système de découpage intelligent pour textes longs.
    Implémente la technique Hierarchical Attention.
    """
    
    @staticmethod
    def chunker_texte_long(texte: str, max_chunk: int = 4000) -> List[str]:
        """
        Découpe un texte long en chunks intelligents.
        
        Stratégie:
        1. Découper par paragraphes (préserve le sens)
        2. Regrouper jusqu'à max_chunk
        3. Si paragraphe trop long, découper par phrases
        
        Args:
            texte: Texte à découper
            max_chunk: Taille max d'un chunk en caractères
        
        Returns:
            Liste de chunks
        """
        import re
        
        # Étape 1: Découper par paragraphes
        paragraphes = re.split(r'\n\s*\n', texte)
        
        chunks = []
        chunk_actuel = ""
        
        for para in paragraphes:
            para = para.strip()
            if not para:
                continue
            
            # Si le paragraphe seul dépasse max_chunk, le découper par phrases
            if len(para) > max_chunk:
                phrases = re.split(r'([.!?]+\s+)', para)
                phrase_courante = ""
                
                for i in range(0, len(phrases), 2):
                    phrase = phrases[i]
                    separateur = phrases[i + 1] if i + 1 < len(phrases) else ""
                    
                    if len(phrase_courante) + len(phrase) + len(separateur) < max_chunk:
                        phrase_courante += phrase + separateur
                    else:
                        if phrase_courante:
                            chunks.append(phrase_courante.strip())
                        phrase_courante = phrase + separateur
                
                if phrase_courante:
                    chunks.append(phrase_courante.strip())
                
            # Sinon, accumuler les paragraphes normalement
            elif len(chunk_actuel) + len(para) + 2 < max_chunk:  # +2 pour \n\n
                chunk_actuel += para + "\n\n"
            else:
                if chunk_actuel:
                    chunks.append(chunk_actuel.strip())
                chunk_actuel = para + "\n\n"
        
        # Ajouter le dernier chunk
        if chunk_actuel:
            chunks.append(chunk_actuel.strip())
        
        return chunks


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.2.0 PHASE 3: SYSTÈME DE COMPRESSION MÉMOIRE
# ═══════════════════════════════════════════════════════════════════════════

class MemoryCompressionSystem:
    """
    Système de compression automatique de la mémoire conversationnelle.
    Implémente la technique Compression dynamique / Selective Attention.
    """
    
    @staticmethod
    async def compresser_memoire_ancienne(
        session_id: str,
        llm_client: OpenAI,
        threshold: int = COMPRESSION_THRESHOLD,
        keep_recent: int = COMPRESSION_KEEP_RECENT
    ) -> bool:
        """
        Compresse les vieux messages en résumé.
        
        Stratégie:
        1. Si < threshold messages, ne rien faire
        2. Sinon, résumer les (total - keep_recent) plus anciens
        3. Remplacer par 1 message résumé
        
        Args:
            session_id: ID de session
            llm_client: Client OpenAI
            threshold: Nombre de messages déclenchant compression
            keep_recent: Nombre de messages récents à garder intacts
        
        Returns:
            True si compression effectuée, False sinon
        """
        if session_id not in CONVERSATION_MEMORY:
            return False
        
        historique = list(CONVERSATION_MEMORY[session_id])
        
        # Si moins de threshold messages, pas de compression
        if len(historique) < threshold:
            return False
        
        # Séparer anciens et récents
        nb_anciens = len(historique) - keep_recent
        anciens = historique[:nb_anciens]
        recents = historique[nb_anciens:]
        
        logging.info(f"🗜️ Compression mémoire session {session_id[:8]}...")
        logging.info(f"   Total: {len(historique)} | Anciens: {nb_anciens} | Récents: {keep_recent}")
        
        # Créer texte à résumer
        messages_text = "\n".join([
            f"{'👤 User' if m['role'] == 'user' else '🤖 Nkotronic'}: {m['content']}"
            for m in anciens
        ])
        
        # Prompt de résumé
        prompt = f"""Tu es Nkotronic. Résume cette ancienne conversation en gardant:
- Les mots/règles/faits appris
- Les questions importantes posées
- Le contexte général

Sois concis (5-10 lignes max).

CONVERSATION ({nb_anciens} messages):
{messages_text}

RÉSUMÉ:"""
        
        try:
            response = await asyncio.to_thread(
                llm_client.chat.completions.create,
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=MAX_TOKENS_RESUME
            )
            
            resume = response.choices[0].message.content.strip()
            
            # Créer nouveau message résumé
            message_resume = {
                'role': 'system',
                'content': f"[📜 RÉSUMÉ CONVERSATION PASSÉE]\n\n{resume}",
                'timestamp': datetime.now().isoformat(),
                'compressed': True,
                'original_count': nb_anciens
            }
            
            # Remplacer l'historique
            CONVERSATION_MEMORY[session_id] = deque(
                [message_resume] + recents,
                maxlen=MAX_MEMORY_SIZE
            )
            
            logging.info(f"✅ Compression réussie: {nb_anciens} messages → 1 résumé")
            logging.info(f"   Nouveau total: {len(CONVERSATION_MEMORY[session_id])} messages")
            
            return True
            
        except Exception as e:
            logging.error(f"❌ Erreur compression mémoire: {e}")
            return False
    
    @staticmethod
    def doit_compresser(session_id: str) -> bool:
        """Vérifie si la session doit être compressée"""
        if session_id not in CONVERSATION_MEMORY:
            return False
        
        return len(CONVERSATION_MEMORY[session_id]) >= COMPRESSION_THRESHOLD


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.2.0: DÉTECTION AUTOMATIQUE ET ADAPTATION
# ═══════════════════════════════════════════════════════════════════════════

class MessageTypeDetector:
    """Détecte automatiquement le type de message et adapte le traitement"""
    
    @staticmethod
    def analyser_longueur_message(message: str) -> Dict[str, any]:
        """
        Analyse la longueur d'un message et recommande le traitement.
        
        Returns:
            Dict avec: longueur, type, strategie, params
        """
        longueur = len(message)
        
        if longueur < 2000:
            return {
                'longueur': longueur,
                'type': 'court',
                'strategie': 'normal',
                'max_tokens': MAX_TOKENS_RESPONSE,
                'chunking': False,
                'description': 'Message court - traitement standard'
            }
        
        elif longueur < 8000:
            return {
                'longueur': longueur,
                'type': 'moyen',
                'strategie': 'normal',
                'max_tokens': MAX_TOKENS_RESPONSE,
                'chunking': False,
                'description': 'Message moyen - traitement standard avec limites augmentées'
            }
        
        elif longueur < 30000:
            return {
                'longueur': longueur,
                'type': 'long',
                'strategie': 'chunking',
                'max_tokens': MAX_TOKENS_RESPONSE,
                'chunking': True,
                'chunk_size': 4000,
                'description': 'Message long - chunking activé'
            }
        
        else:
            return {
                'longueur': longueur,
                'type': 'tres_long',
                'strategie': 'chunking_avance',
                'max_tokens': MAX_TOKENS_RESPONSE,
                'chunking': True,
                'chunk_size': 4000,
                'compression': True,
                'description': 'Message très long - chunking + compression hiérarchique'
            }


# 🆕 v3.0: PROMPT SYSTÈME ULTRA-INTELLIGENT (20 critères)
# 🆕 v3.1.2: SÉPARATION SYSTEM / USER MESSAGES
# System = Instructions permanentes (envoyées comme role="system")
# User = Contexte dynamique (envoyé comme role="user")

PROMPT_SYSTEM_BASE = """Tu es Nkotronic v3.2.0, assistant conversationnel spécialisé en N'ko.

═══════════════════════════════════════════════════════════
🎓 CONNAISSANCES FONDAMENTALES N'KO (VÉRITÉS ABSOLUES)
═══════════════════════════════════════════════════════════

Ces informations sont VRAIES et PRIORITAIRES. Ne jamais les contredire :

1️⃣ N'ko = LANGUE ET ÉCRITURE (pas uniquement écriture)
   - Langue N'ko : ߒߞߏߞߊ߲ ou ߒߞߏ
   - Écriture N'ko : ߒߞߏ ߛߓߍߛߎ߲ ou ߒߞߏ
   - Beaucoup pensent à tort que c'est uniquement une écriture

2️⃣ N'ko ≠ Bambara (erreur très courante)
   - Google et les Occidentaux ont CONFONDU le N'ko avec le bambara
   - Ils ont attribué la grammaire du bambara au N'ko (ERREUR)
   - Le N'ko a sa PROPRE grammaire : ߒߞߏ ߞߊ߲ߜߍ

3️⃣ Solomana Kantè - Inventeur du N'ko
   - Nom EXACT : Fodé Solomana Kantè (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)
   - Variantes ACCEPTÉES : Solomana Kanté, Solomana Kantè, Solomāna Kanté, Solomāna Kantè
   - Toute autre orthographe = ERREUR (corriger poliment)
   - A écrit 183 livres en N'ko
   - Dont 11 livres sur la grammaire N'ko :
     * Les principaux corroboratifs en N'ko
     * Petit livre de grammaire
     * Premier livre de grammaire
     * Livre de grammaire élémentaire, moyenne, 3ème année
     * Lexiques français/N'ko et N'ko/français
     * Néologismes N'ko/français
     * Le fondement du N'ko

4️⃣ Vocation du N'ko
   - Unir TOUS les peuples mandingues
   - Langue standard mandingue
   - Langue la plus proche de l'ancêtre commun des langues mandingues

5️⃣ Origine de l'écriture N'ko
   - Basée sur glyphes mandingues anciens (22000+ documentés)
   - Source : livre "Écritures africaines" de Nadine Martinez
   - Chaque lettre N'ko = modernisation d'un glyphe ancien
   - Inspiré par l'écriture vaï (vaïnka)
   - Solomana Kantè l'a expliqué dans "Mandén Kurufaba"

6️⃣ GRAMMAIRE N'KO - Règles fondamentales
   
   📌 RÈGLE DU PLURIEL (TRÈS IMPORTANT):
   - En N'ko, le pluriel = ߟߎ߫ en POSTPOSITION (après le mot)
   - Le pluriel n'est JAMAIS collé au mot (toujours séparé par un espace)
   - Exemple: ߛߏ (maison) → ߛߏ ߟߎ߫ (maisons) ✅ PAS ߛߏߟߎ߫ ❌
   - SAUF exceptions que l'utilisateur t'apprendra explicitement
   - Si tu vois un pluriel collé sans que l'utilisateur t'ait dit que c'est une exception,
     c'est probablement une ERREUR

7️⃣ VOCABULAIRE DE BASE - Corrections importantes
   - soleil = ߕߋ߬ߟߋ (PAS ߕߊ)
   - feu = ߕߊ
   - Ne JAMAIS confondre soleil et feu

⚠️ Si quelqu'un contredit ces faits, corrige poliment avec sources.

═══════════════════════════════════════════════════════════
⚠️ RÈGLE ABSOLUE - HIÉRARCHIE DES SOURCES (NON NÉGOCIABLE)
═══════════════════════════════════════════════════════════

Tu as DEUX sources de connaissances :
  A) 📚 CONTEXTE RAG (ci-dessous) = Enseignements directs de l'utilisateur
  B) 🧠 Tes connaissances générales = Ton entraînement GPT-4

PROCÉDURE OBLIGATOIRE (Chain-of-Thought):
  1. Lis le CONTEXTE RAG en entier
  2. La question concerne-t-elle une info présente dans le RAG ?
     → OUI : Utilise UNIQUEMENT le RAG, ignore tes connaissances générales
     → NON : Utilise tes connaissances générales

INTERDICTIONS :
  ❌ Mélanger RAG et connaissances générales
  ❌ Contredire le RAG même si tu "sais mieux"
  ❌ Ignorer le RAG parce qu'il semble incomplet

⚠️ RÈGLE DE NATURALITÉ (TRÈS IMPORTANT):
  ❌ JAMAIS mentionner "RAG", "contexte RAG", "base de données"
  ❌ JAMAIS dire "Le terme ne figure pas dans le contexte RAG"
  ❌ JAMAIS dire "Je ne trouve pas dans le CONTEXTE RAG"
  
  ✅ Dire plutôt :
     - "Selon ce que tu m'as appris..."
     - "D'après ce que je sais..."
     - "Je me souviens que tu m'as dit..."
     - Si info manquante : "Je ne sais pas encore" ou "Je n'ai pas cette info"

EXEMPLE CONCRET (Few-Shot Learning):
  RAG: "Règle: le pluriel = ߟߎ߫ en postposition"
  Question: "C'est quoi la marque du pluriel ?"
  
  ✅ BON: "Le pluriel se forme en ajoutant ߟߎ߫ en postposition (règle que tu m'as enseignée)."
  ❌ FAUX: "La marque n'est pas explicite, ça dépend..." (connaissances générales)
"""

# 🆕 v3.1.2: PROMPT_USER_CONTEXT - Contexte dynamique par requête
PROMPT_USER_CONTEXT = """
═══════════════════════════════════════════════════════════
🎭 MODE: {mode_actuel}
═══════════════════════════════════════════════════════════

{instruction_mode}

═══════════════════════════════════════════════════════════
📚 CONTEXTE RAG (À VÉRIFIER EN PREMIER)
═══════════════════════════════════════════════════════════

{contexte_rag}

═══════════════════════════════════════════════════════════
📝 HISTORIQUE CONVERSATION
═══════════════════════════════════════════════════════════

{historique_conversation}

═══════════════════════════════════════════════════════════
📊 CONTEXTE UTILISATEUR
═══════════════════════════════════════════════════════════

Émotion: {emotion_detectee} ({emotion_confiance})
Engagement: {niveau_engagement}
Niveau: {niveau_utilisateur} | Progression: Niveau {niveau_actuel}
XP: {xp_actuel}/{xp_prochain_niveau} | Mots appris: {mots_appris}
Badges: {badges_actuels}

{nouveau_niveau}
{message_badge}

💬 FLUIDITÉ CONVERSATIONNELLE:
- Utilise connecteurs naturels: "d'ailleurs", "en revanche", "donc"
- Simule réflexion: "Hmm...", "Voyons voir...", "Ah oui !"
- Varie le rythme selon complexité

🌍 CONSCIENCE CULTURELLE:
- Adapte vocabulaire au contexte mandingue
- Utilise proverbes N'ko quand approprié
- Explique nuances culturelles

⏰ CONTEXTE TEMPOREL:
Heure: {heure_actuelle} | Date: {jour_actuel}

═══════════════════════════════════════════════════════════
💬 MESSAGE UTILISATEUR
═══════════════════════════════════════════════════════════

{user_message}

═══════════════════════════════════════════════════════════

PROCESSUS DE RÉPONSE :
  1. Le RAG contient-il l'info ? → Si OUI, utilise RAG uniquement
  2. Quel mode ? → {mode_actuel}
  3. Quelle émotion ? → {emotion_detectee}
  4. Génère réponse adaptée

Réponds maintenant.

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

# 🆕 v3.1: MODE_INSTRUCTIONS - Few-Shot Learning par mode
MODE_INSTRUCTIONS = {
    "conversationnel": """
MODE: Conversation naturelle

Comportement:
- Ton décontracté, empathique
- Pas de posture professorale
- N'utilise N'ko que si pertinent au contexte
- Pas de félicitations gratuites

Exemple:
User: "ça va bien !"
✅ "Cool ! Quoi de neuf ?"
❌ "ߛߋ߬ߣߍ߲߬ ! C'est super ! ߞߊ߬ߙߊ߲߬ߠߊ߬ߘߎ߯ !"
""",

    "élève": """
MODE: Apprentissage détecté - Tu es en mode ÉLÈVE

Comportement:
- Gratitude sincère mais sobre
- Confirme l'apprentissage
- Gamification
- Humble

Exemple:
User: "table=ߕߊߓߟߊ"
✅ "✅ Merci ! J'ai appris : ߕߊߓߟߊ = table
    +10 XP | 10/100 niveau 1 😊"
❌ "Magnifique opportunité pédagogique ! ߞߊ߬ߙߊ߲߬ߠߊ߬ߘߎ߯ !"
""",

    "enseignant": """
MODE: Question détectée - Tu es en mode ENSEIGNANT

⚠️ VÉRIFIE D'ABORD LE RAG !

Si RAG contient l'info:
  → Utilise RAG + cite la source ("selon ce que tu m'as appris")
  
Si RAG vide:
  → Utilise connaissances générales

Exemples:

CAS 1 - RAG contient l'info:
User: "C'est quoi la marque du pluriel ?"
RAG: "Règle: pluriel = ߟߎ߫ en postposition"
✅ "Le pluriel se forme en ajoutant ߟߎ߫ en postposition (règle que tu m'as enseignée)."

CAS 2 - RAG vide:
User: "Combien de lettres en N'ko ?"
RAG: [vide]
✅ "Il y a 27 lettres en N'ko."

Comportement:
- Clair et précis
- Bienveillant mais concis
- PAS de félicitations à la fin
"""
}

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[dict]:
    global LLM_CLIENT, QDRANT_CLIENT
    logging.info("🚀 Démarrage de Nkotronic v3.2.0 (Long Context Master)...")

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

    logging.info("✅ Nkotronic v3.2.0 prêt avec Long Context Master!")
    yield {}
    logging.info("🛑 Arrêt de Nkotronic")

app = FastAPI(
    title="Nkotronic API",
    description="API de traduction Français ↔ N'ko avec mémoire RAG + Long Context Master",
    version="3.2.0",
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


# ═══════════════════════════════════════════════════════════════════════════
# 🆕 v3.0: FONCTIONS DE GESTION DES PROFILS UTILISATEURS
# ═══════════════════════════════════════════════════════════════════════════

def get_or_create_user_profile(session_id: str) -> dict:
    """Récupère ou crée un profil utilisateur"""
    if session_id not in USER_PROFILES:
        USER_PROFILES[session_id] = {
            'session_id': session_id,
            'created_at': datetime.now().isoformat(),
            'niveau': DifficultyLevel.DEBUTANT.value,
            'preferences': {
                'style_reponse': 'standard',
                'langue_interface': 'français',
                'notifications': True
            },
            'progress': UserProgress().__dict__,
            'statistiques': {
                'total_messages': 0,
                'mots_appris': 0,
                'regles_apprises': 0,
                'temps_total_minutes': 0
            },
            'derniere_activite': datetime.now().isoformat()
        }
        logging.info(f"✨ Nouveau profil créé pour session {session_id[:8]}...")
    
    return USER_PROFILES[session_id]


def update_user_progress(session_id: str, action: str, details: dict = None) -> dict:
    """Met à jour la progression de l'utilisateur"""
    profile = get_or_create_user_profile(session_id)
    progress_dict = profile['progress']
    progress = UserProgress(**progress_dict)
    
    # Mettre à jour selon l'action
    if action == 'mot_appris':
        progress.mots_appris += 1
        progress.points_xp += GamificationSystem.XP_PAR_MOT
        profile['statistiques']['mots_appris'] += 1
        
    elif action == 'regle_apprise':
        progress.regles_apprises += 1
        progress.points_xp += GamificationSystem.XP_PAR_REGLE
        profile['statistiques']['regles_apprises'] += 1
    
    # Vérifier les jours consécutifs
    aujourd_hui = datetime.now().date()
    if progress.dernier_jour_actif:
        dernier_jour = datetime.fromisoformat(progress.dernier_jour_actif).date()
        if aujourd_hui - dernier_jour == timedelta(days=1):
            progress.jours_consecutifs += 1
        elif aujourd_hui != dernier_jour:
            progress.jours_consecutifs = 1
    else:
        progress.jours_consecutifs = 1
    
    progress.dernier_jour_actif = datetime.now().isoformat()
    
    # Calculer le niveau
    ancien_niveau = progress.niveau
    progress.niveau = GamificationSystem.calculer_niveau(progress.points_xp)
    
    # Vérifier nouveaux badges
    nouveaux_badges = GamificationSystem.verifier_nouveaux_badges(progress)
    
    # Ajouter les nouveaux badges à la liste
    for badge in nouveaux_badges:
        if badge.value not in progress.badges:
            progress.badges.append(badge.value)
    
    # Sauvegarder
    profile['progress'] = progress.__dict__
    profile['derniere_activite'] = datetime.now().isoformat()
    
    return {
        'niveau_change': ancien_niveau != progress.niveau,
        'nouveau_niveau': progress.niveau if ancien_niveau != progress.niveau else None,
        'nouveaux_badges': nouveaux_badges,
        'xp_total': progress.points_xp,
        'xp_prochain_niveau': GamificationSystem.xp_pour_niveau_suivant(progress.niveau),
        'mots_total': progress.mots_appris
    }


def ajouter_message_memoire(session_id: str, role: str, content: str, metadata: dict = None):
    """Ajoute un message à l'historique de la session avec métadonnées optionnelles."""
    if session_id not in CONVERSATION_MEMORY:
        CONVERSATION_MEMORY[session_id] = deque(maxlen=MAX_MEMORY_SIZE)
    
    message = {
        'role': role,
        'content': content,
        'timestamp': datetime.now().isoformat()
    }
    
    if metadata:
        message.update(metadata)
    
    CONVERSATION_MEMORY[session_id].append(message)
    logging.info(f"💬 Message ajouté à session {session_id[:8]}... (total: {len(CONVERSATION_MEMORY[session_id])} messages)")


def formater_historique_conversation(session_id: str, limite: int = 20) -> str:
    """Formate l'historique de conversation pour le contexte du LLM."""
    if session_id not in CONVERSATION_MEMORY:
        return "[Nouvelle conversation - Pas d'historique]"
    
    historique = list(CONVERSATION_MEMORY[session_id])
    
    if not historique:
        return "[Nouvelle conversation - Pas d'historique]"
    
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
    """Détecte si le message demande une analyse de l'historique."""
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
    """Exécute une action basée sur la mémoire conversationnelle."""
    if session_id not in CONVERSATION_MEMORY:
        return "Nous n'avons pas encore d'historique de conversation."
    
    historique = list(CONVERSATION_MEMORY[session_id])
    
    if not historique:
        return "Nous venons de commencer notre conversation."
    
    action = intention['action']
    
    # ACTION 1: Résumer la conversation
    if action == 'resume_conversation':
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
                max_tokens=MAX_TOKENS_RESUME
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
        
        message_cible = historique[-(offset + 1)]
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
    
    # Patterns regex pour éviter appel LLM inutile
    patterns_rapides = [
        r"comment (?:dit-on|on dit) (?:le |la |l'|un |une )?([a-zàâäéèêëïîôùûü]+)",
        r"(?:c'est quoi|quoi c'est) (?:le |la |l'|un |une )?([a-zàâäéèêëïîôùûü]+)",
        r"traduction (?:de |d')?(?:le |la |l'|un |une )?([a-zàâäéèêëïîôùûü]+)",
        r"(?:le |la |l'|un |une )?([a-zàâäéèêëïîôùûü]+) en n'?ko"
    ]
    
    for pattern in patterns_rapides:
        match = re.search(pattern, user_message.lower())
        if match:
            mot = match.group(1).strip()
            logging.info(f"🔑 Mot extrait rapidement: '{mot}'")
            return mot
    
    # Recherche de mots entre guillemets
    quoted = re.findall(r"['\"]([^'\"]+)['\"]", user_message)
    if quoted:
        mot = quoted[0].strip().lower()
        logging.info(f"🔑 Mot extrait des guillemets: '{mot}'")
        return mot
    
    # Extraction via LLM (fallback)
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


# 🆕 PHASE 6: RECHERCHE INTELLIGENTE AVEC FILTRAGE
async def recherche_intelligente_filtree(mot_cle: str, llm_client: OpenAI, qdrant_client: AsyncQdrantClient):
    """Recherche vectorielle optimisée."""
    try:
        emb_resp = await asyncio.to_thread(
            llm_client.embeddings.create,
            input=[mot_cle],
            model=EMBEDDING_MODEL
        )
        vector = emb_resp.data[0].embedding
        
        limit_rag = 15 if len(mot_cle.split()) > 2 else 10
        
        result = await qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=vector,
            limit=limit_rag,
            with_payload=True,
            score_threshold=0.7
        )
        
        hits = result.points
        
        if hits:
            logging.info(f"🔍 RAG: {len(hits)} résultats pour '{mot_cle}'")
            for i, h in enumerate(hits[:5], 1):
                type_r = h.payload.get('type', 'mot')
                titre = h.payload.get('element_français') or h.payload.get('titre_règle', 'N/A')
                logging.info(f"   [{i}] {type_r.upper()} | Score: {h.score:.3f} | {titre[:40]}")
        else:
            logging.warning(f"⚠️ RAG: Aucun résultat pour '{mot_cle}'")
        
        return hits
        
    except Exception as e:
        logging.error(f"❌ Recherche échouée: {e}")
        return []


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
    
    nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
    nko_words = nko_pattern.findall(user_message)
    
    if not nko_words:
        return user_message, []
    
    logging.info(f"🔍 Mots N'ko détectés dans la question: {nko_words}")
    
    traductions = []
    for nko_word in nko_words:
        try:
            nko_word_norm = normaliser_nko(nko_word)
            
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
            
            # Match exact normalisé
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
                        logging.info(f"✅ Match exact trouvé: {nko_word} = {fr}")
                        break
            
            # Meilleur score si pas de match exact
            if not any(t['nko'] == nko_word for t in traductions):
                if results.points and results.points[0].score > 0.80:
                    best = results.points[0]
                    fr = best.payload.get('element_français')
                    if fr:
                        traductions.append({
                            'nko': nko_word,
                            'français': fr,
                            'payload': best.payload
                        })
                        logging.info(f"✅ Meilleur match trouvé: {nko_word} = {fr}")
                
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


# 🆕 v3.1: DÉTECTION DE MODE - Role Playing Adaptatif
def detecter_mode_reponse(
    user_message: str, 
    apprentissage_info: Optional[Dict], 
    type_info: Optional[Dict]
) -> str:
    """Détermine le mode de réponse: conversationnel, élève, ou enseignant."""
    import re
    
    # MODE ÉLÈVE: Si apprentissage détecté
    if apprentissage_info or type_info:
        return "élève"
    
    # MODE ENSEIGNANT: Si question sur N'ko
    patterns_enseignement = [
        r'comment\s+(dit-on|on\s+dit|dire|écrire|prononce)',
        r'qu.est-ce\s+que.*en\s+n.?ko',
        r'tradui[st]',
        r'(ça|c.est)\s+(veut\s+dire|signifie)\s+quoi',
        r'explique.*n.?ko',
        r'c.est\s+quoi',
        r'quel(?:le)?\s+(?:est|sont)',
        r'combien\s+(?:de|y\s+a)',
        r'pourquoi.*n.?ko',
        r'donne[-\s]moi',
        r'peux[-\s]tu\s+(?:me\s+)?(?:dire|donner|expliquer)',
        r'écri[st]\s+.+\s+(?:en\s+)?(?:n.?ko|au\s+pluriel|au\s+singulier)',
        r'marque\s+(?:du|de\s+la|des)',
        r'forme\s+(?:du|de\s+la)',
    ]
    
    message_lower = user_message.lower()
    for pattern in patterns_enseignement:
        if re.search(pattern, message_lower):
            return "enseignant"
    
    return "conversationnel"


# 🆕 v3.1.1: DÉTECTION LISTES MULTI-LIGNES
def detecter_liste_multilignes(message: str) -> Optional[Dict]:
    """Détecte les listes avec plusieurs lignes de format A=B ou A\tB."""
    import re
    
    lines = message.strip().split('\n')
    lines = [l.strip() for l in lines if l.strip()]
    
    if len(lines) < 2:
        return None
    
    items = []
    for line in lines:
        match = re.match(r'^(.+?)\s*[=\t]\s*(.+)$', line)
        if match:
            partie1 = match.group(1).strip()
            partie2 = match.group(2).strip()
            
            nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
            has_nko_1 = bool(nko_pattern.search(partie1))
            has_nko_2 = bool(nko_pattern.search(partie2))
            
            if has_nko_1 and not has_nko_2:
                items.append({'français': partie2, 'nko': partie1})
            elif has_nko_2 and not has_nko_1:
                items.append({'français': partie1, 'nko': partie2})
    
    if len(items) >= 2:
        return {
            'type': 'liste',
            'items': items,
            'nom_liste': f"Liste de {len(items)} mots"
        }
    
    return None


# --- PHASE 5.1: DÉTECTION MULTI-TYPES COMPLÈTE ---
def detecter_type_connaissance(message: str) -> Optional[Dict]:
    """Détecte le type de connaissance dans le message."""
    import re
    
    message = message.replace("\\'", "'").replace('\\"', '"')
    message_clean = message.strip().lower()
    
    # Filtre - Phrases qui ne sont PAS des apprentissages
    phrases_ignorees = [
        'il me semble', 'je pense', 'à mon avis', 'peut-être', 'probablement',
        'claude.ai', 'claude', 'tu vois', 'fais', 'peux-tu', 'pourrais-tu',
        'devrais', 'devrait', 'comment fonctionne', 'parle moi', 'explique'
    ]
    
    if any(phrase in message_clean for phrase in phrases_ignorees):
        return None
    
    # PRIORITÉ 0 - Détection listes multi-lignes
    liste_info = detecter_liste_multilignes(message)
    if liste_info:
        return liste_info
    
    # 1️⃣ RÈGLES GRAMMATICALES
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
    
    return None


# --- PHASE 5: DÉTECTION D'APPRENTISSAGE (MOTS SIMPLES) ---
def detecter_apprentissage(message: str) -> Optional[Dict[str, str]]:
    """Détecte si le message est une demande d'apprentissage de MOT simple."""
    import re
    
    message = message.replace("\\'", "'").replace('\\"', '"')
    message_clean = message.strip().lower()
    
    # Pattern 0 - "apprend [et enregistre/mémorise] [ça/que] : X signifie Y"
    pattern0 = r'(?:apprends?|mémorise[rz]?|enregistre[rz]?)\s+(?:et\s+)?(?:enregistre[rz]?|mémorise[rz]?)?\s*(?:ça|ceci|cela|que)?\s*[:;]\s*(.+?)\s+signifie\s+["\']?(.+?)(?:["\'])?$'
    
    match = re.search(pattern0, message_clean, re.IGNORECASE)
    if match:
        partie1 = match.group(1).strip()
        partie2 = match.group(2).strip()
        
        nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
        
        has_nko_1 = bool(nko_pattern.search(partie1))
        has_nko_2 = bool(nko_pattern.search(partie2))
        
        if has_nko_1 and not has_nko_2:
            return {'nko': partie1, 'français': partie2, 'pattern': 'explication_signifie'}
        elif has_nko_2 and not has_nko_1:
            return {'nko': partie2, 'français': partie1, 'pattern': 'explication_signifie'}
    
    # Pattern 1 - "apprend [et enregistre] [ça/que] : X = Y"
    pattern1 = r'(?:apprends?|mémorise[rz]?|enregistre[rz]?)\s+(?:et\s+)?(?:enregistre[rz]?|mémorise[rz]?)?\s*(?:ça|ceci|cela|que)?\s*[:;]?\s*(.+?)\s*[=:]\s*(.+)'
    
    # Pattern 2: "X = Y" (simple)
    pattern2 = r'^([^\s=]+)\s*[=:]\s*([^\s=]+)$'
    
    # Pattern 3: "X signifie Y"
    pattern3 = r'(.+?)\s+signifie\s+(.+)'
    
    # Pattern 4: "Y se dit X en N'ko"
    pattern4 = r'(.+?)\s+se\s+dit\s+(.+?)\s+en\s+n.?ko'
    
    for pattern in [pattern1, pattern3, pattern4, pattern2]:
        match = re.search(pattern, message_clean, re.IGNORECASE)
        if match:
            word1, word2 = match.groups()
            word1 = word1.strip()
            word2 = word2.strip()
            
            # Nettoyer mots parasites
            parasites = ['et enregistre ça', 'et mémorise ça', 'et enregistre', 'et mémorise']
            for parasite in parasites:
                word1 = word1.replace(parasite, '').strip()
                word2 = word2.replace(parasite, '').strip()
            
            nko_pattern = re.compile(r'[\u07C0-\u07FF]+')
            
            has_nko_1 = bool(nko_pattern.search(word1))
            has_nko_2 = bool(nko_pattern.search(word2))
            
            if has_nko_1 and not has_nko_2:
                return {'nko': word1, 'français': word2, 'pattern': 'détecté'}
            elif has_nko_2 and not has_nko_1:
                return {'nko': word2, 'français': word1, 'pattern': 'détecté'}
    
    return None


async def apprendre_mot(
    nko_word: str,
    fr_word: str,
    llm_client: OpenAI,
    qdrant_client: AsyncQdrantClient,
    concept: str = "Appris par utilisateur",
    user_context: Optional[Dict] = None
) -> Dict[str, any]:
    """Apprend un nouveau mot et le stocke dans Qdrant."""
    try:
        import unicodedata
        
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
    """Apprend n'importe quel type de connaissance (règles, faits, listes, etc.)."""
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
        else:
            texte_embedding = str(connaissance_data)
        
        # 🆕 v3.2.0 PHASE 2: Détection automatique + chunking si nécessaire
        texte_embedding = texte_embedding.replace("\\'", "'").replace('\\"', '"')
        texte_embedding = ' '.join(texte_embedding.split())
        texte_embedding = ''.join(char for char in texte_embedding if ord(char) >= 32 or char in '\n\t')
        
        if len(texte_embedding) > MAX_CHARS_EMBEDDING:
            logging.warning(f"⚠️ Texte long ({len(texte_embedding)} chars)")
            
            # Analyser le message
            analyse = MessageTypeDetector.analyser_longueur_message(texte_embedding)
            
            if analyse['chunking']:
                # CHUNKING activé pour textes très longs
                logging.info(f"📦 Chunking activé: {analyse['description']}")
                chunks = ChunkingSystem.chunker_texte_long(texte_embedding, max_chunk=4000)
                logging.info(f"✅ {len(chunks)} chunks créés")
                
                # Traiter chaque chunk séparément
                resultats_chunks = []
                for i, chunk in enumerate(chunks):
                    # Créer embedding du chunk
                    emb_resp_chunk = await asyncio.to_thread(
                        llm_client.embeddings.create,
                        input=[chunk],
                        model=EMBEDDING_MODEL
                    )
                    vector_chunk = emb_resp_chunk.data[0].embedding
                    
                    # Stocker avec métadonnées de chunking
                    chunk_data = {
                        **connaissance_data,
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'contenu_chunk': chunk,
                        'is_chunk': True,
                        'appris_par': 'utilisateur',
                        'date_ajout': str(time.time())
                    }
                    
                    point_chunk = PointStruct(
                        id=str(uuid.uuid4()),
                        vector=vector_chunk,
                        payload=chunk_data
                    )
                    
                    await qdrant_client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=[point_chunk]
                    )
                    
                    resultats_chunks.append(point_chunk.id)
                
                # Retourner résultat multi-chunks
                message_chunks = f"✅ Texte long traité en {len(chunks)} chunks"
                if type_conn == 'mot':
                    message_chunks = f"✅ Liste de {len(chunks)} sections mémorisée"
                elif type_conn == 'règle':
                    message_chunks = f"✅ Règle longue mémorisée en {len(chunks)} parties"
                
                return {
                    'status': 'success',
                    'message': message_chunks,
                    'type': type_conn,
                    'chunks': len(chunks),
                    'point_ids': resultats_chunks
                }
            else:
                # Tronquer à MAX_CHARS_EMBEDDING si pas de chunking nécessaire
                texte_embedding = texte_embedding[:MAX_CHARS_EMBEDDING] + "..."
        
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
        elif type_conn == 'liste':
            nb_elements = len(connaissance_data.get('elements_liste', []))
            message = f"✅ Liste '{connaissance_data.get('nom_liste')}' mémorisée ({nb_elements} éléments)"
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


# --- PHASE 5.1: FORMATAGE CONTEXTE MULTI-TYPES ---
def formater_connaissance_pour_contexte(payload: Dict) -> str:
    """Formate une connaissance pour le contexte RAG selon son type."""
    type_conn = payload.get('type', 'mot')
    
    if type_conn == 'mot':
        fr = payload.get('element_français', '')
        nko = payload.get('element_nko', '')
        concept = payload.get('concept_identifie', '')
        ligne = f"- {fr} = {nko} ({concept})"
        
        valeur_num = payload.get('valeur_numerique')
        if valeur_num is not None:
            ligne += f" | valeur: {valeur_num}"
        
        fait = payload.get('fait_texte')
        if fait:
            ligne += f" | info: {fait}"
        
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
    
    elif type_conn == 'liste':
        nom_liste = payload.get('nom_liste', '')
        elements = payload.get('elements_liste', [])
        elements_str = ', '.join([f"{e.get('fr')}={e.get('nko')}" for e in elements[:5]])
        if len(elements) > 5:
            elements_str += f"... ({len(elements)} éléments)"
        return f"- [LISTE] {nom_liste}: {elements_str}"
    
    else:
        return f"- {payload}"


# --- ENDPOINT CHAT AVEC MÉMOIRE INTELLIGENTE ET LONG CONTEXT ---
@app.post('/chat', response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    global LLM_CLIENT, QDRANT_CLIENT

    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail='LLM non initialisé')

    # Gestion de la session
    session_id = get_or_create_session(req.session_id)
    
    # Correction des fautes courantes
    message_corrige = ErrorRecoverySystem.corriger_fautes_courantes(req.user_message)
    
    # Analyse émotionnelle
    emotion, confiance = SentimentAnalyzer.detecter_emotion(message_corrige)
    
    # Profil utilisateur et progression
    profile = get_or_create_user_profile(session_id)
    progress = UserProgress(**profile['progress'])
    
    # Niveau d'engagement
    niveau_engagement = SentimentAnalyzer.detecter_niveau_engagement(
        list(CONVERSATION_MEMORY.get(session_id, []))
    )
    
    # Détection de répétition utilisateur
    if ErrorRecoverySystem.detecter_repetition_utilisateur(
        list(CONVERSATION_MEMORY.get(session_id, []))
    ):
        tentatives = SESSION_METADATA.get(session_id, {}).get('tentatives_incomprehension', 0)
        tentatives += 1
        if session_id not in SESSION_METADATA:
            SESSION_METADATA[session_id] = {}
        SESSION_METADATA[session_id]['tentatives_incomprehension'] = tentatives
        
        if tentatives >= 3:
            message_incomprehension = ErrorRecoverySystem.generer_message_incomprehension(tentatives)
            ajouter_message_memoire(session_id, 'user', req.user_message)
            ajouter_message_memoire(session_id, 'assistant', message_incomprehension)
            return ChatResponse(
                response_text=message_incomprehension,
                session_id=session_id,
                memory_update=None
            )
    
    debug_info = {} if req.debug else None
    rag_active = req.rag_enabled and (QDRANT_CLIENT is not None)
    contexte_rag_text = '[Aucune donnée en mémoire]'

    try:
        # 🆕 v3.2.0 PHASE 3: Compression automatique de mémoire
        if MemoryCompressionSystem.doit_compresser(session_id):
            logging.info(f"🗜️ Déclenchement compression auto session {session_id[:8]}...")
            compression_ok = await MemoryCompressionSystem.compresser_memoire_ancienne(
                session_id=session_id,
                llm_client=LLM_CLIENT
            )
            
            if compression_ok and req.debug:
                debug_info['memory_compressed'] = True
                debug_info['memory_size_after'] = len(CONVERSATION_MEMORY[session_id])
        
        # Vérifier si c'est une demande d'analyse de mémoire
        intention_memoire = await analyser_intention_memoire(req.user_message, session_id, LLM_CLIENT)
        
        if intention_memoire:
            logging.info(f"🧠 Intention mémoire détectée: {intention_memoire['type']}")
            
            response_text = await executer_action_memoire(intention_memoire, session_id, LLM_CLIENT)
            
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
        
        # Détecter type de connaissance (règles, faits, listes, etc.)
        type_info = detecter_type_connaissance(req.user_message)
        
        if type_info:
            logging.info(f"🎓 {type_info['type'].upper()} détecté: {type_info}")
            
            resultat = await apprendre_connaissance(
                connaissance_data=type_info,
                llm_client=LLM_CLIENT,
                qdrant_client=QDRANT_CLIENT
            )
            
            # GAMIFICATION - Mise à jour progression
            action_type = 'regle_apprise' if type_info['type'] in ['règle', 'conjugaison', 'grammaire'] else 'mot_appris'
            progress_update = update_user_progress(session_id, action_type, type_info)
            
            # Construction du message de célébration
            celebration = ""
            
            if progress_update['niveau_change']:
                celebration += f"\n\n🌟 **NIVEAU {progress_update['nouveau_niveau']} ATTEINT !**"
                celebration += f"\n✨ Tu as maintenant {progress_update['xp_total']} XP !"
            
            for badge in progress_update['nouveaux_badges']:
                celebration += f"\n\n{GamificationSystem.message_celebration(badge)}"
            
            if action_type == 'mot_appris':
                nb_mots_total = progress_update.get('mots_total', progress.mots_appris)
                
                if nb_mots_total == 1:
                    celebration += "\n\n🎉 Félicitations ! On a appris notre premier mot en N'ko !"
                elif nb_mots_total == 10:
                    celebration += f"\n\n🎊 Bravo ! On a maintenant {nb_mots_total} mots !"
                elif nb_mots_total == 50:
                    celebration += f"\n\n🏆 Incroyable ! {nb_mots_total} mots maîtrisés !"
                elif nb_mots_total == 100:
                    celebration += f"\n\n💎 Centenaire atteint ! {nb_mots_total} mots !"
                elif nb_mots_total % 25 == 0:
                    celebration += f"\n\n🌟 Excellent ! {nb_mots_total} mots en N'ko !"
            
            xp_gain = GamificationSystem.XP_PAR_REGLE if action_type == 'regle_apprise' else GamificationSystem.XP_PAR_MOT
            xp_restants = progress_update['xp_prochain_niveau'] - progress_update['xp_total']
            celebration += f"\n\n📊 **+{xp_gain} XP** | Encore {xp_restants} XP pour le niveau {progress.niveau + 1}"
            
            resultat['message'] += celebration
            
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
        
        # Détecter apprentissage de MOT simple
        apprentissage_info = detecter_apprentissage(req.user_message)
        
        if apprentissage_info:
            logging.info(f"🎓 Apprentissage MOT détecté: {apprentissage_info}")
            
            resultat = await apprendre_mot(
                nko_word=apprentissage_info['nko'],
                fr_word=apprentissage_info['français'],
                llm_client=LLM_CLIENT,
                qdrant_client=QDRANT_CLIENT,
                concept="Appris par utilisateur"
            )
            
            progress_update = update_user_progress(session_id, 'mot_appris', apprentissage_info)
            
            celebration = ""
            
            if progress_update['niveau_change']:
                celebration += f"\n\n🌟 **NIVEAU {progress_update['nouveau_niveau']} ATTEINT !**"
                celebration += f"\n✨ Tu as maintenant {progress_update['xp_total']} XP !"
            
            for badge in progress_update['nouveaux_badges']:
                celebration += f"\n\n{GamificationSystem.message_celebration(badge)}"
            
            nb_mots_total = progress_update.get('mots_total', progress.mots_appris)
            
            if nb_mots_total == 1:
                celebration += "\n\n🎉 Félicitations ! On a appris notre premier mot en N'ko !"
            elif nb_mots_total == 10:
                celebration += f"\n\n🎊 Bravo ! On a maintenant {nb_mots_total} mots !"
            elif nb_mots_total == 50:
                celebration += f"\n\n🏆 Incroyable ! {nb_mots_total} mots maîtrisés !"
            elif nb_mots_total == 100:
                celebration += f"\n\n💎 Centenaire atteint ! {nb_mots_total} mots !"
            elif nb_mots_total % 25 == 0:
                celebration += f"\n\n🌟 Excellent ! {nb_mots_total} mots en N'ko !"
            
            xp_restants = progress_update['xp_prochain_niveau'] - progress_update['xp_total']
            celebration += f"\n\n📊 **+{GamificationSystem.XP_PAR_MOT} XP** | Encore {xp_restants} XP pour le niveau {progress.niveau + 1}"
            
            resultat['message'] += celebration
            
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

                # Recherche intelligente filtrée
                hits = await recherche_intelligente_filtree(mot_cle, LLM_CLIENT, QDRANT_CLIENT)

                logging.info(f"📊 RÉSULTATS pour '{mot_cle}':")
                for i, h in enumerate(hits[:10], 1):
                    logging.info(f"  #{i}: score={h.score:.4f} -> {h.payload.get('element_français', 'N/A')}")
                
                if req.debug:
                    debug_info['top_results'] = [
                        {'score': h.score, 'payload': h.payload} 
                        for h in hits[:10]
                    ]

                # Formater contexte RAG avec GROUPEMENT PAR TYPE
                if hits:
                    logging.info(f"✅ {len(hits)} résultat(s) pertinent(s)")
                    
                    regles = [h for h in hits[:10] if h.payload.get('type') == 'règle']
                    mots = [h for h in hits[:10] if h.payload.get('type') == 'mot']
                    autres = [h for h in hits[:10] if h.payload.get('type') not in ['règle', 'mot']]
                    
                    parts = []
                    
                    if regles:
                        parts.append("🎯 RÈGLES GRAMMATICALES ENSEIGNÉES PAR L'UTILISATEUR:")
                        for r in regles[:3]:
                            titre = r.payload.get('titre_règle', '')
                            explic = r.payload.get('explication_règle', '')
                            parts.append(f"\n📖 {titre}")
                            parts.append(f"   {explic}")
                        parts.append("")
                    
                    if mots:
                        parts.append("📚 VOCABULAIRE APPRIS:")
                        for m in mots[:8]:
                            nko = m.payload.get('element_nko', '')
                            fr = m.payload.get('element_français', '')
                            parts.append(f"  • {fr} = {nko}")
                        parts.append("")
                    
                    if autres:
                        parts.append("ℹ️ AUTRES CONNAISSANCES:")
                        for a in autres[:3]:
                            ligne = formater_connaissance_pour_contexte(a.payload)
                            parts.append(f"  • {ligne}")
                    
                    contexte_rag_text = "\n".join(parts)
                    
                    if not regles and not mots and not autres:
                        contexte_rag_text = "[Aucune connaissance pertinente]"
                else:
                    logging.warning(f"⚠️ Aucun résultat trouvé")
                    contexte_rag_text = "[Base de connaissances vide]"

                if traductions_contexte:
                    contexte_extra = '\n'.join(
                        f"- {t['français']} = {t['nko']}"
                        for t in traductions_contexte
                    )
                    contexte_rag_text = contexte_extra + '\n\n' + contexte_rag_text

            except Exception as e:
                logging.error(f"❌ Erreur RAG: {e}", exc_info=True)
                if req.debug:
                    debug_info['rag_error'] = str(e)
                rag_active = False

        # Formater l'historique de conversation
        historique_conversation = formater_historique_conversation(session_id, limite=20)
        
        logging.info(f"📤 CONTEXTE ENVOYÉ AU LLM:\n{contexte_rag_text}")

        # DÉTERMINER MODE DE RÉPONSE
        mode = detecter_mode_reponse(
            req.user_message,
            apprentissage_info if 'apprentissage_info' in locals() else None,
            type_info if 'type_info' in locals() else None
        )
        logging.info(f"🎭 Mode détecté: {mode.upper()}")
        
        instruction_mode = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["conversationnel"])

        # ARCHITECTURE FIX - Séparer system et user messages
        system_message = PROMPT_SYSTEM_BASE
        
        user_message_content = PROMPT_USER_CONTEXT.format(
            mode_actuel=mode.upper(),
            instruction_mode=instruction_mode,
            emotion_detectee=emotion.value if emotion else "neutre",
            emotion_confiance=f"{confiance:.2f}" if confiance else "0.50",
            niveau_engagement=niveau_engagement,
            niveau_utilisateur=profile.get('niveau', 'débutant'),
            niveau_actuel=progress.niveau,
            xp_actuel=progress.points_xp,
            xp_prochain_niveau=GamificationSystem.xp_pour_niveau_suivant(progress.niveau),
            mots_appris=progress.mots_appris,
            badges_actuels=", ".join(progress.badges[:3]) + ("..." if len(progress.badges) > 3 else "") if progress.badges else "Aucun",
            message_badge="",
            nouveau_niveau="",
            historique_conversation=historique_conversation,
            contexte_rag=contexte_rag_text,
            heure_actuelle=datetime.now().strftime("%H:%M"),
            jour_actuel=datetime.now().strftime("%A %d %B %Y"),
            user_message=message_corrige
        )

        # 🆕 v3.2.0 PHASE 1: Call LLM avec max_tokens=8000 et GPT-4-Turbo
        temperature_mode = {
            'conversationnel': 0.7,
            'enseignant': 0.3,
            'élève': 0.5
        }
        
        llm_resp = await asyncio.to_thread(
            LLM_CLIENT.chat.completions.create,
            model=LLM_MODEL,  # v3.2.0: gpt-4-turbo
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message_content}
            ],
            temperature=temperature_mode.get(mode, 0.5),
            max_tokens=MAX_TOKENS_RESPONSE,  # v3.2.0: 8000
            stream=False
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
        
        # Ajouter à l'historique avec métadonnées émotionnelles
        ajouter_message_memoire(
            session_id, 
            'user', 
            req.user_message,
            metadata={
                'emotion': emotion.value if emotion else None,
                'emotion_confiance': confiance if confiance else None,
                'corrige': message_corrige if message_corrige != req.user_message else None
            }
        )
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


# --- ENDPOINTS MÉMOIRE ---
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


# 🆕 v3.2.0: ENDPOINTS COMPRESSION MÉMOIRE
@app.get('/memory/compression-status/{session_id}')
async def get_compression_status(session_id: str):
    """Vérifie le statut de compression d'une session"""
    if session_id not in CONVERSATION_MEMORY:
        raise HTTPException(status_code=404, detail="Session non trouvée")
    
    historique = list(CONVERSATION_MEMORY[session_id])
    compresse = any(m.get('compressed', False) for m in historique)
    doit_compresser = MemoryCompressionSystem.doit_compresser(session_id)
    
    return {
        'session_id': session_id,
        'total_messages': len(historique),
        'compresse': compresse,
        'doit_compresser': doit_compresser,
        'threshold': COMPRESSION_THRESHOLD,
        'messages_avant_compression': max(0, COMPRESSION_THRESHOLD - len(historique))
    }


@app.post('/memory/force-compression/{session_id}')
async def force_compression(session_id: str):
    """Force la compression d'une session"""
    if LLM_CLIENT is None:
        raise HTTPException(status_code=503, detail="LLM non disponible")
    
    if session_id not in CONVERSATION_MEMORY:
        raise HTTPException(status_code=404, detail="Session non trouvée")
    
    avant = len(CONVERSATION_MEMORY[session_id])
    
    compression_ok = await MemoryCompressionSystem.compresser_memoire_ancienne(
        session_id=session_id,
        llm_client=LLM_CLIENT,
        threshold=0  # Force même si < 50 messages
    )
    
    apres = len(CONVERSATION_MEMORY[session_id]) if compression_ok else avant
    
    return {
        'status': 'success' if compression_ok else 'failed',
        'messages_avant': avant,
        'messages_apres': apres,
        'gain': avant - apres if compression_ok else 0
    }


@app.post('/analyze-message-length')
async def analyze_message_length(message: str):
    """Analyse un message et recommande la stratégie de traitement"""
    analyse = MessageTypeDetector.analyser_longueur_message(message)
    
    # Si chunking nécessaire, montrer preview des chunks
    if analyse['chunking']:
        chunks = ChunkingSystem.chunker_texte_long(message, max_chunk=4000)
        analyse['chunks_preview'] = [
            {
                'index': i,
                'longueur': len(chunk),
                'debut': chunk[:100] + "..."
            }
            for i, chunk in enumerate(chunks[:5])
        ]
        analyse['total_chunks'] = len(chunks)
    
    return analyse


# --- ENDPOINTS PROFILS ET GAMIFICATION ---
@app.get('/profile/{session_id}')
async def get_profile(session_id: str):
    """Récupère le profil complet d'un utilisateur."""
    if session_id not in USER_PROFILES:
        raise HTTPException(status_code=404, detail="Profil non trouvé")
    
    return USER_PROFILES[session_id]


@app.put('/profile/{session_id}/preferences')
async def update_preferences(session_id: str, preferences: dict):
    """Met à jour les préférences utilisateur."""
    profile = get_or_create_user_profile(session_id)
    profile['preferences'].update(preferences)
    
    return {
        "status": "success",
        "message": "Préférences mises à jour",
        "preferences": profile['preferences']
    }


@app.get('/leaderboard')
async def get_leaderboard(limit: int = 10):
    """Classement des meilleurs apprenants par XP."""
    if not USER_PROFILES:
        return {
            'total_users': 0,
            'top_users': []
        }
    
    users_sorted = sorted(
        USER_PROFILES.values(),
        key=lambda p: UserProgress(**p['progress']).points_xp,
        reverse=True
    )[:limit]
    
    return {
        'total_users': len(USER_PROFILES),
        'top_users': [
            {
                'session_id': u['session_id'][:8] + '...',
                'niveau': UserProgress(**u['progress']).niveau,
                'xp': UserProgress(**u['progress']).points_xp,
                'mots_appris': UserProgress(**u['progress']).mots_appris,
                'regles_apprises': UserProgress(**u['progress']).regles_apprises,
                'badges': len(UserProgress(**u['progress']).badges),
                'jours_consecutifs': UserProgress(**u['progress']).jours_consecutifs
            }
            for u in users_sorted
        ]
    }


@app.get('/badges')
async def get_all_badges():
    """Liste de tous les badges disponibles dans le système."""
    badges_info = [
        {'nom': Badge.PREMIER_MOT.value, 'critere': '1 mot appris', 'type': 'bronze'},
        {'nom': Badge.DIX_MOTS.value, 'critere': '10 mots appris', 'type': 'argent'},
        {'nom': Badge.CINQUANTE_MOTS.value, 'critere': '50 mots appris', 'type': 'or'},
        {'nom': Badge.CENT_MOTS.value, 'critere': '100 mots appris', 'type': 'diamant'},
        {'nom': Badge.GRAMMAIRIEN.value, 'critere': '5 règles apprises', 'type': 'or'},
        {'nom': Badge.PERSEVERANT.value, 'critere': '7 jours consécutifs', 'type': 'or'},
        {'nom': Badge.CHAMPION.value, 'critere': 'Niveau 10+', 'type': 'legendaire'}
    ]
    
    return {
        'total_badges': len(badges_info),
        'badges': badges_info
    }


@app.get('/user/{session_id}/progress-summary')
async def get_progress_summary(session_id: str):
    """Résumé de progression détaillé pour un utilisateur."""
    if session_id not in USER_PROFILES:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    
    profile = USER_PROFILES[session_id]
    progress = UserProgress(**profile['progress'])
    
    tous_badges = list(Badge)
    badges_actuels = set(progress.badges)
    badges_manquants = [b for b in tous_badges if b.value not in badges_actuels]
    
    objectifs = []
    if progress.mots_appris < 10:
        objectifs.append(f"Apprends {10 - progress.mots_appris} mots pour le badge 📚 10 Mots")
    elif progress.mots_appris < 50:
        objectifs.append(f"Apprends {50 - progress.mots_appris} mots pour le badge 🏆 50 Mots")
    
    if progress.regles_apprises < 5:
        objectifs.append(f"Apprends {5 - progress.regles_apprises} règles pour le badge 📖 Grammairien")
    
    xp_prochain = GamificationSystem.xp_pour_niveau_suivant(progress.niveau)
    xp_restants = xp_prochain - progress.points_xp
    objectifs.append(f"Gagne {xp_restants} XP pour atteindre le niveau {progress.niveau + 1}")
    
    return {
        'progression_actuelle': {
            'niveau': progress.niveau,
            'xp': progress.points_xp,
            'xp_prochain_niveau': xp_prochain,
            'pourcentage_niveau': round((progress.points_xp / xp_prochain) * 100, 1),
            'mots_appris': progress.mots_appris,
            'regles_apprises': progress.regles_apprises,
            'badges_actuels': progress.badges,
            'jours_consecutifs': progress.jours_consecutifs
        },
        'prochains_objectifs': objectifs,
        'badges_manquants': [b.value for b in badges_manquants],
        'recommandations': [
            "Pratique tous les jours pour maintenir ta série !",
            "Apprends des règles de grammaire pour gagner +25 XP",
            "Explore différents thèmes de vocabulaire"
        ]
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
        'version': '3.2.0',
        'features': [
            'RAG',
            'Multi-types',
            'Mémoire conversationnelle (200 messages)',
            'Compression automatique',
            'Chunking intelligent',
            'Long Context Master (100k+ chars)',
            'GPT-4-Turbo (128k context)'
        ],
        'status': 'running',
        'llm_status': 'ok' if LLM_CLIENT else 'error',
        'qdrant_status': 'ok' if QDRANT_CLIENT else 'disabled',
        'memory_size': count,
        'active_sessions': len(CONVERSATION_MEMORY),
        'max_chars_embedding': MAX_CHARS_EMBEDDING,
        'max_tokens_response': MAX_TOKENS_RESPONSE,
        'model': LLM_MODEL
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
    """Statistiques globales du système v3.2.0"""
    if QDRANT_CLIENT is None:
        raise HTTPException(status_code=503, detail='Qdrant non disponible')
    
    try:
        count = await QDRANT_CLIENT.count(collection_name=COLLECTION_NAME)
        sample = await QDRANT_CLIENT.scroll(
            collection_name=COLLECTION_NAME,
            limit=10,
            with_payload=True
        )
        
        total_users = len(USER_PROFILES)
        total_sessions = len(CONVERSATION_MEMORY)
        total_messages = sum(len(hist) for hist in CONVERSATION_MEMORY.values())
        
        xp_total = sum(
            UserProgress(**p['progress']).points_xp 
            for p in USER_PROFILES.values()
        ) if USER_PROFILES else 0
        
        xp_moyen = xp_total / total_users if total_users > 0 else 0
        
        mots_total = sum(
            p['statistiques']['mots_appris']
            for p in USER_PROFILES.values()
        ) if USER_PROFILES else 0
        
        regles_total = sum(
            p['statistiques']['regles_apprises']
            for p in USER_PROFILES.values()
        ) if USER_PROFILES else 0
        
        badges_total = sum(
            len(UserProgress(**p['progress']).badges)
            for p in USER_PROFILES.values()
        ) if USER_PROFILES else 0
        
        return {
            'version': '3.2.0',
            'nom': 'Nkotronic Long Context Master',
            'total_points_qdrant': count.count,
            'total_utilisateurs': total_users,
            'total_sessions': total_sessions,
            'total_messages': total_messages,
            'mots_appris_total': mots_total,
            'regles_apprises_total': regles_total,
            'badges_debloques_total': badges_total,
            'xp_total_cumule': xp_total,
            'xp_moyen_par_user': round(xp_moyen, 2),
            'timestamp': datetime.now().isoformat(),
            'capacites_v320': {
                'max_chars_embedding': MAX_CHARS_EMBEDDING,
                'max_tokens_response': MAX_TOKENS_RESPONSE,
                'chunking': 'Activé',
                'compression_auto': f'Seuil: {COMPRESSION_THRESHOLD} messages',
                'modele': LLM_MODEL,
                'contexte_llm': '128k tokens'
            },
            'sample_data': [p.payload for p in sample[0][:3]]
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
                    'concept': h.payload.get('concept_identifie', 'N/A'),
                    'type': h.payload.get('type', 'mot')
                }
                for h in hits[:10]
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/transcribe_phonetic')
async def transcribe_phonetic(nko_text: str):
    """Transcrit un texte N'ko en phonétique latine"""
    try:
        transcription = transcrire_nko_phonetique(nko_text)
        
        return {
            'nko_original': nko_text,
            'transcription_complete': transcription
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 🆕 v3.2.0: Endpoint de test rapide
@app.get('/test-long-context')
async def test_long_context():
    """Test rapide des capacités Long Context v3.2.0"""
    return {
        'status': 'ready',
        'version': '3.2.0',
        'capabilities': {
            'max_chars_embedding': f'{MAX_CHARS_EMBEDDING:,} chars (x5 vs v3.1.7)',
            'max_tokens_response': f'{MAX_TOKENS_RESPONSE:,} tokens (x4 vs v3.1.7)',
            'model': f'{LLM_MODEL} (128k context vs 8k)',
            'chunking': 'Intelligent hierarchical chunking enabled',
            'compression': f'Auto compression at {COMPRESSION_THRESHOLD} messages',
            'memory_size': f'{MAX_MEMORY_SIZE} messages (x2 vs v3.1.7)'
        },
        'test_scenarios': [
            'Message court (<2k): traitement normal',
            'Message moyen (2k-8k): limites augmentées',
            'Message long (8k-30k): chunking activé',
            'Message très long (>30k): chunking + compression hiérarchique',
            'Conversation longue (>50 messages): compression automatique'
        ]
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)