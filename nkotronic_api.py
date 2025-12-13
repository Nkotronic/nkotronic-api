"""
╔══════════════════════════════════════════════════════════════╗
║  NKOTRONIC BACKEND - Version 3.0 MEMORY SAFE                ║
║  ✅ Protection complète contre le Memory Leak                ║
║  ✅ Gestion des sessions avec TTL                            ║
║  ✅ Cleanup automatique                                      ║
║  ✅ Prompt Caching OpenAI                                    ║
╚══════════════════════════════════════════════════════════════╝
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import openai
import os
import httpx
import json
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import asyncio
from collections import OrderedDict

app = FastAPI(title="Nkotronic API", version="3.0.0-MEMORY-SAFE")

# CORS pour permettre les requêtes depuis le frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════
# GESTION DE LA MÉMOIRE DES SESSIONS
# ═══════════════════════════════════════════════════════════

class SessionData(BaseModel):
    """Données d'une session utilisateur"""
    messages: List[Dict[str, str]] = []
    created_at: datetime
    last_activity: datetime

# Configuration de la mémoire
MAX_SESSIONS = 1000  # Limite nombre de sessions en RAM
SESSION_TTL_HOURS = 24  # Durée de vie d'une session (24h)
MAX_MESSAGES_PER_SESSION = 20  # Garder seulement les 20 derniers messages
CLEANUP_INTERVAL_MINUTES = 30  # Nettoyer toutes les 30 minutes

# Stockage des sessions en mémoire (OrderedDict pour LRU)
sessions_store: OrderedDict[str, SessionData] = OrderedDict()

def get_session(session_id: str) -> SessionData:
    """Récupère ou crée une session"""
    now = datetime.utcnow()
    
    if session_id in sessions_store:
        # Session existe, mettre à jour l'activité
        session = sessions_store[session_id]
        session.last_activity = now
        # Déplacer à la fin (LRU)
        sessions_store.move_to_end(session_id)
        return session
    else:
        # Nouvelle session
        # Vérifier la limite de sessions
        if len(sessions_store) >= MAX_SESSIONS:
            # Supprimer la plus ancienne (FIFO)
            oldest_id = next(iter(sessions_store))
            del sessions_store[oldest_id]
            print(f"🗑️  Session {oldest_id} supprimée (limite atteinte)")
        
        # Créer nouvelle session
        session = SessionData(
            messages=[],
            created_at=now,
            last_activity=now
        )
        sessions_store[session_id] = session
        print(f"✨ Nouvelle session créée: {session_id}")
        return session

def add_message_to_session(session_id: str, role: str, content: str):
    """Ajoute un message à la session avec limite"""
    session = get_session(session_id)
    
    # Ajouter le nouveau message
    session.messages.append({"role": role, "content": content})
    
    # Limiter à MAX_MESSAGES_PER_SESSION
    if len(session.messages) > MAX_MESSAGES_PER_SESSION:
        # Garder seulement les N derniers messages
        session.messages = session.messages[-MAX_MESSAGES_PER_SESSION:]
        print(f"✂️  Session {session_id} tronquée à {MAX_MESSAGES_PER_SESSION} messages")

def cleanup_expired_sessions():
    """Nettoie les sessions expirées"""
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=SESSION_TTL_HOURS)
    
    expired_ids = []
    for session_id, session in sessions_store.items():
        if session.last_activity < cutoff:
            expired_ids.append(session_id)
    
    for session_id in expired_ids:
        del sessions_store[session_id]
    
    if expired_ids:
        print(f"🧹 Cleanup: {len(expired_ids)} sessions expirées supprimées")
    
    print(f"📊 Sessions actives: {len(sessions_store)}/{MAX_SESSIONS}")

# Tâche de fond pour le cleanup automatique
async def periodic_cleanup():
    """Nettoie périodiquement les sessions expirées"""
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_MINUTES * 60)
        cleanup_expired_sessions()

@app.on_event("startup")
async def startup_event():
    """Démarre le cleanup automatique au démarrage"""
    asyncio.create_task(periodic_cleanup())
    print(f"🤖 Cleanup automatique démarré (toutes les {CLEANUP_INTERVAL_MINUTES} min)")

# ═══════════════════════════════════════════════════════════
# CHARGEMENT DU PROMPT SYSTÈME COMPLET (864 lignes)
# ═══════════════════════════════════════════════════════════

# Charger depuis le même dossier que le script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SYSTEM_PROMPT_PATH = os.path.join(SCRIPT_DIR, "nkotronic_prompt.txt")

try:
    with open(SYSTEM_PROMPT_PATH, 'r', encoding='utf-8') as f:
        NKOTRONIC_COMPLETE_GRAMMAR = f.read()
    print(f"✅ Prompt système chargé: {len(NKOTRONIC_COMPLETE_GRAMMAR)} caractères")
except Exception as e:
    print(f"❌ ERREUR: Impossible de charger le prompt système: {e}")
    print(f"📂 Chemin recherché: {SYSTEM_PROMPT_PATH}")
    # Prompt par défaut minimal si fichier absent
    NKOTRONIC_COMPLETE_GRAMMAR = """Tu es Nkotronic, l'assistant IA expert en N'ko. 
Tu es bienveillant, précis et pédagogue. Tu maîtrises parfaitement le N'ko."""

# ═══════════════════════════════════════════════════════════
# CHARGEMENT DU LEXIQUE DEPUIS GITHUB
# ═══════════════════════════════════════════════════════════

GITHUB_LEXIQUE_URL = "https://raw.githubusercontent.com/Nkotronic/nkotronic-api/main/vocab_fr_nko.txt"
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
    session_id: str = "default"  # Identifiant de session
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 4096

class ChatResponse(BaseModel):
    response: str
    model_used: str
    tokens_used: Optional[int] = None
    session_id: str
    messages_in_session: int

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
║  📐 RÉSUMÉ GRAMMATICAL N'KO (PRINCIPES ESSENTIELS)          ║
╚══════════════════════════════════════════════════════════════╝

🔹 ALPHABET (27 lettres) : ߊ ߋ ߌ ߍ ߎ ߏ ߐ ߒ ߓ ߔ ߕ ߖ ߗ ߘ ߙ ߚ ߛ ߜ ߝ ߞ ߟ ߡ ߢ ߣ ߤ ߥ ߦ
- Voyelles (7) : ߊ(a) ߋ(e/é) ߌ(i) ߍ(ɛ/è) ߎ(u/ou) ߏ(o) ߐ(ɔ/ö)
- Semi-voyelle (1) : ߒ(ŋ/N') - tèdö (neutre/intermédiaire)
- Consonnes (19) : ߓ(b) ߔ(p) ߕ(t) ߖ(dj) ߗ(tch) ߘ(d) ߙ(r) ߚ(rr) ߛ(s) ߜ(gb) ߝ(f) ߞ(k) ߟ(l) ߡ(m) ߢ(gn) ߣ(n) ߤ(h) ߥ(w) ߦ(y)
- Récitation : Consonnes se prononcent consonne+[a] (ex: ߓ=ba)

🔹 NASALISATION : Point de nasalisation ߲ placé SOUS la voyelle
- Voyelles nasales : ߊ߲(an) ߋ߲(en) ߌ߲(in) ߍ߲(ɛn) ߎ߲(un) ߏ߲(on)
- Formation : Voyelle orale + ߲ → voyelle nasale
- Le ߲ est appelé Kannadiyalan (ߞߊ߲ߠߊߘߌߦߊߟߊ߲)

🔹 SYLLABES DE BASE (consonne+voyelle, 133 syllabes) :
ba=ߓߊ be=ߓߋ bi=ߓߌ bɛ=ߓߍ bu=ߓߎ bo=ߓߏ bɔ=ߓߐ
pa=ߔߊ pe=ߔߋ pi=ߔߌ pɛ=ߔߍ pu=ߔߎ po=ߔߏ pɔ=ߔߐ
ta=ߕߊ te=ߕߋ ti=ߕߌ tɛ=ߕߍ tu=ߕߎ to=ߕߏ tɔ=ߕߐ
dja=ߖߊ dje=ߖߋ dji=ߖߌ djɛ=ߖߍ dju=ߖߎ djo=ߖߏ djɔ=ߖߐ
tcha=ߗߊ tche=ߗߋ tchi=ߗߌ tchɛ=ߗߍ tchu=ߗߎ tcho=ߗߏ tchɔ=ߗߐ
da=ߘߊ de=ߘߋ di=ߘߌ dɛ=ߘߍ du=ߘߎ do=ߘߏ dɔ=ߘߐ
ra=ߙߊ re=ߙߋ ri=ߙߌ rɛ=ߙߍ ru=ߙߎ ro=ߙߏ rɔ=ߙߐ
rra=ߚߊ rre=ߚߋ rri=ߚߌ rrɛ=ߚߍ rru=ߚߎ rro=ߚߏ rrɔ=ߚߐ
sa=ߛߊ se=ߛߋ si=ߛߌ sɛ=ߛߍ su=ߛߎ so=ߛߏ sɔ=ߛߐ
gba=ߜߊ gbe=ߜߋ gbi=ߜߌ gbɛ=ߜߍ gbu=ߜߎ gbo=ߜߏ gbɔ=ߜߐ
fa=ߝߊ fe=ߝߋ fi=ߝߌ fɛ=ߝߍ fu=ߝߎ fo=ߝߏ fɔ=ߝߐ
ka=ߞߊ ke=ߞߋ ki=ߞߌ kɛ=ߞߍ ku=ߞߎ ko=ߞߏ kɔ=ߞߐ
la=ߟߊ le=ߟߋ li=ߟߌ lɛ=ߟߍ lu=ߟߎ lo=ߟߏ lɔ=ߟߐ
ma=ߡߊ me=ߡߋ mi=ߡߌ mɛ=ߡߍ mu=ߡߎ mo=ߡߏ mɔ=ߡߐ
gna=ߢߊ gne=ߢߋ gni=ߢߌ gnɛ=ߢߍ gnu=ߢߎ gno=ߢߏ gnɔ=ߢߐ
na=ߣߊ ne=ߣߋ ni=ߣߌ nɛ=ߣߍ nu=ߣߎ no=ߣߏ nɔ=ߣߐ
ha=ߤߊ he=ߤߋ hi=ߤߌ hɛ=ߤߍ hu=ߤߎ ho=ߤߏ hɔ=ߤߐ
wa=ߥߊ we=ߥߋ wi=ߥߌ wɛ=ߥߍ wu=ߥߎ wo=ߥߏ wɔ=ߥߐ
ya=ߦߊ ye=ߦߋ yi=ߦߌ yɛ=ߦߍ yu=ߦߎ yo=ߦߏ yɔ=ߦߐ

🔹 LETTRES DÉRIVÉES (avec ߳ ou ߭) : ɣ=ߊ߳ ø=ߋ߳ ü=ߎ߳ bʱ=ߓ߭ tˤ=ߕ߭ z=ߖ߭ ðˤ=ߖ߳ ð=ߗ߭ dˤ=ߘ߭ ʁ=ߙ߭ ʃ=ߛ߭ θ=ߛ߳ sˤ=ߛ߫ g=ߜ߭ k͡p=ߜ߳ v=ߝ߭ x=ߞ߭

🔹 CHIFFRES (0-9, droite→gauche) : ߀(0) ߁(1) ߂(2) ߃(3) ߄(4) ߅(5) ߆(6) ߇(7) ߈(8) ߉(9)
- Exemples : 10=߁߀, 20=߂߀, 100=߁߀߀, 1949=߁߉߄߉
- Se lisent de droite à gauche ; mêmes règles de calcul qu'en français

🔹 TONS (8 diacritiques) :
Courts : ߊ(montant calme, pas de diacritique), ߊ߫(montant brusque), ߊ߭(descendant calme), ߊ߬(descendant brusque)
Longs : ߊ߮(montant calme long), ߊ߯(montant brusque long), ߊ߱(descendant calme long), ߊ߰(descendant brusque long)

🔹 PRONOMS PERSONNELS SUJETS : ߒ(je), ߌ(tu), ߊ(il/elle/on), ߊ߲(nous), ߊߟߎ߫(vous), ߊ߬ߟߎ߫(ils/elles)
Variantes : ߒ߬(nous), ߒ߬ߠߎ߫(nous), ߊ߲ߠߎ߫(nous), ߊߦߌ߫(vous), ߊ߬ߦߌ߫(ils/elles)

🔹 PRONOMS TONIQUES : ߒߠߋ(moi), ߌߟߋ(toi), ߊ߬ߟߋ(lui/elle), ߊ߲ߠߎ߫(nous), ߊߟߎ߫(vous), ߊ߬ߟߎ߫(eux/elles)

🔹 PRONOMS POSSESSIFS : ߒ ߕߊ(le mien/la mienne), ߌ ߕߊ(le tien/la tienne), ߊ߬ ߕߊ(le sien/la sienne), ߊ߲ ߕߊ(le nôtre), ߊߟߎ߫ ߕߊ(le vôtre), ߏ߬ ߕߊ(le leur)
Pluriel : +ߟߎ߫ (ex: ߒ ߕߊ ߟߎ߫=les miens)

🔹 DÉTERMINANTS POSSESSIFS : ߒ ߟߊ߫(mon/ma/mes), ߌ ߟߊ߫(ton/ta/tes), ߊ߬ ߟߊ߫(son/sa/ses), ߊ߲ ߠߊ߫(notre/nos), ߊߟߎ߫ ߟߊ߫(votre/vos), ߊ߬ߟߎ߫ ߟߊ߫(leur/leurs)

🔹 DÉTERMINANTS DÉMONSTRATIFS : ߢߌ߲߬/ߣߌ߲߬/ߊ߬/ߏ߬(ce/cet/cette/ça/cela/ceci), ߢߌ߲߬ ߠߎ߫/ߣߌ߲߬ ߠߎ߫/ߊ߬ߟߎ߫(ces)

🔹 PRONOMS DÉMONSTRATIFS : ߡߍ߲(celui/celle), ߡߍ߲ ߠߎ߫(ceux/celles)

🔹 PRONOMS RELATIFS : ߡߍ߲(qui/que - sing.), ߡߍ߲ ߠߎ߫(plur.)

🔹 CONJONCTIONS DE COORDINATION : ߞߏ߬ߣߌ߲߬(mais), ߥߟߊ߫(ou), ߣߌ߫(et), ߕߍ߫(ni), ߓߊߏ߬(car), ߝߣߊ߫(puis), ߏ߬ ߞߐ߫(ensuite), ߏ߬ ߘߐ߫(donc), ߦߏ߫/ߌߞߏߡߌ߲߬(comme)

🔹 CONJONCTIONS DE SUBORDINATION : ߞߏ߫(que), ߣߌ߫(si), ߕߎ߬ߡߊ ߡߍ߲(quand/lorsque), ߞߊ߬ߡߊߛߐ߬ߘߐ߲߬(puisque), ߤߊߟߌ߬ ߣߌ߫(quoique), ߛߊ߫(afin que), ߞߊ߬ ߕߊ߯ ߤߊ߲߯/ߝߏ߯(jusqu'à ce que), ߏ߬ ߛߋ߲߬ߝߍ߬(pendant que), ߝߏ߬ߣߴߊ߲(tandis que)

🔹 SUFFIXES NOMINAUX (tous collés) :
ߓߊ(augmentatif), ߞߊ(habitant de), ߟߊ(lieu/contrée), ߕߊ(pour), ߡߊ(de type), ߡߊ߲(qui a), ߣߌ߲/ߣߍ߲/ߘߋ߲/ߟߋ߲/ߙߋ߲(diminutifs), ߒߕߊ߲(dénué de/sans), ߕߐ(malade de), ߦߊ(état de), ߟߊ߫(selon/par)

🔹 SUFFIXES VERBAUX (tous collés) :
ߓߊ߮/ߓߜ߭ߊ߬(agent ponctuel), ߟߊ(agent habituel), ߟߊ߲(instrument - NE MUTE JAMAIS), ߟߌ/ߠߌ߲(action de), ߒߕߋ(acteur), ߕߊ(destiné à), ߓߊߟߌ(privatif/anti)

🔹 SUFFIXES ORDINAUX : ߣߊ߲(ordinal - ex: ߝߌߟߊߣߊ߲=deuxième)

🔹 SUFFIXE UNIVERSEL : ߝߋ߲(chose/outil/discipline/catégorie/domaine)

🔹 SIGNES SPÉCIAUX :
ߑ(dadogbasilan : absence de voyelle entre consonnes, ex: ߓߑߙߊ=bra ; aussi point-virgule)
ߵ(élision voyelle ton bas), ߴ(élision voyelle ton haut)
߳(dérivation lettres), ߺ(prolongement espace), ߽(abréviation unités)
߸(virgule), .(point), ؟(interrogation), ߹(exclamation), ߷(fin section), ߿(argent/monnaie=taman), ߾(dirham/drachme=dɔrɔmɛ)

🔹 DÖYÈLÈMAN (Mutation) : ߟ→ߠ et ߦ→ߧ après voyelle nasale ou ߒ ; ߟߌ→ߠߌ߲ après voyelle nasale ou ߒ ; exceptions : mots en ߟߐ߲, suffixes ߟߊ߲ et ߟߊ߲ߘߌ ne mutent jamais.

🔹 GBARALI (Association) : Si 2 syllabes consécutives ont consonnes différentes + voyelles identiques (même ton) → on supprime la première voyelle ; interdit si : même consonne, voyelles différentes, voyelle nasale, diacritiques différents, présence de ߚ ou ߭, ou si ça change le sens.

🔹 PLURIEL : Marque ߟߎ߫ ou ߟߎ߬ jamais collée au mot ; ߟߎ߫ si ton haut précède, ߟߎ߬ si ton bas précède ; exception : après ton montant calme (ߊ ou ߮) → toujours ߟߎ߬ ; s'applique aux noms ET pronoms.

🔹 DÉFINI/INDÉFINI : Noms en isolation = défini ; indéfini = ߘߏ߫ après le nom (ex: ߡߏ߬ߛߏ ߘߏ߫ = une femme) ; pour défini renforcé : ߊ߬ߟߋ߬ avant le nom ; pluriel indéfini = ߘߏ߫ ߟߎ߫ (invariable).

🔹 DÉMONSTRATIFS : ߣߌ߲߬, ߏ߬, ߊ߬ placés devant, après, ou devant+après le nom ; ߏ߬ et ߏ߬ ߟߎ߫ uniquement après ; ߣߌ߲߬ = rapprochement, ߏ߬ = éloignement ; ߣߌ߲߬ ou ߕߋ߲߬ en fin pour insistance.

🔹 POSSESSIFS : Déterminant possessif AVANT le nom ; ne varie pas selon le nombre du possédé ; parenté/corps : ߒ+nom ; relations contractuelles : ߒ ߟߊ߫/ߞߊ߫+nom.

🔹 NUMÉRAUX : Placés APRÈS le nom ; le nom quantifié ne prend PAS le pluriel et reste indéfini.

🔹 QUALIFICATIFS : Placés APRÈS le nom ; si directement après → prennent le pluriel (nom pas de pluriel) ; si séparés par ߞߊ߫ (affirmatif) ou ߡߊ߲߬/ߡߊ߬ (négatif) → ne prennent PAS le pluriel (nom prend le pluriel) ; pour humains : ߡߊ߲߬, pour objets : ߡߊ߬.

🔹 VERBES : Invariables (ne changent JAMAIS selon personne/temps) ; infinitif = ߞߊ߬+verbe ; marques verbales indiquent le temps ; pas d'accord sujet-verbe ; pas de groupes de conjugaison.

🔹 CONJUGAISON (7 temps) :
1. Présent progressif : Sujet+ߦߋ߫+Verbe+ߟߊ߫ (nég: ߕߍ߫)
2. Passé composé : Sujet+ߓߘߊ߫+Verbe (nég: ߡߊ߬)
3. Passé simple : Sujet+Verbe+ߘߊ߫ (nég: ߡߊ߬ entre verbe et sujet, sans ߘߊ߫)
4. Futur simple : Sujet+ߘߌ߫+Verbe (nég: ߕߍ߫)
5. Futur lointain : Sujet+ߘߌߣߊ߫+Verbe (nég: ߕߍߣߊ߬)
6. Subjonctif : Sujet+ߦߋ߫+Verbe (nég: ߕߍ߫)
7. Injonctif : Sujet+ߦߋ߫+Verbe (nég: ߞߊߣߊ߬)
→ ߕߎ߲߬ s'ajoute aux marques pour indiquer passé (ex: ߒ ߥߟߌ߬ߕߎ߲߬)

🔹 COD : Placé ENTRE marque verbale ET verbe ; structure : Marque+COD+Verbe ; si pronom COD → juste avant verbe.

🔹 COI : Placé APRÈS le verbe + postposition non collée ; structure : Verbe+COI+Postp ; si pronom COI → après verbe+postposition.

🔹 COMPLÉMENTS CIRCONSTANCIELS : Lieu = après verbe+postposition (sauf villes/pays sauf Mali) ; Temps = après verbe ou début de phrase ; Manière = après verbe (groupe verbal/nominal/adverbe/idéophone).

🔹 PRÉSENTATIFS : ߟߋ߬ (c'est) ; ߦߋ߫+GN+ߟߋ߬ ߘߌ߫ (identification affirmatif) ; ߕߍ߫+GN+ߘߌ߫ (négatif).

🔹 EXISTENCE/SITUATION : Nom+ߟߋ߬ (existe/est là - affirmatif) ; Nom+ߕߍ߫ (n'existe pas - négatif) ; +circonstant pour localisation.

🔹 PHRASE DESCRIPTIVE : Sujet+ߞߊ߫+adjectif (affirmatif) ; Sujet+ߡߊ߲߬+adjectif (négatif humains) ; Sujet+ߡߊ߬+adjectif (négatif objets).

🔹 PHRASE TRANSITIVE : Sujet+Auxiliaire+COD+Verbe ; verbe transitif toujours précédé de son COD.

🔹 PHRASE INTRANSITIVE : Sujet+(Auxiliaire)+Verbe+(Auxiliaire).

🔹 SUBORDINATION COMPLÉTIVE : ߞߏ߫ (que) ; peut être omise.

🔹 SUBORDINATION RELATIVE : ߡߍ߲ (qui/que - sing.), ߡߍ߲ ߠߎ߫ (plur.) ; ߦߙߐ ߡߍ߲ (lieu), ߞߏ ߡߍ߲ (manière), ߕߎߡߊ ߡߍ߲ (temps).

🔹 VARIATIONS TONALES : ߭ en fin de mot isolé → ߬ dans phrase/composition ; ߮ → ߯ ; ߱ → ߰ (selon contexte).

🔹 MOTS INTERROGATIFS : ߖߐ߲߫(qui), ߡߎ߲߬/ߡߎ߲߬ߘߏ߲߬/ߡߎ߲߬ߝߋ߲߫/ߢߌ߬ߡߊ߲߬(quoi), ߡߌ߲(où), ߞߏ߫ ߘߌ߫(comment), ߕߎ߬ߡߊ ߖߐ߲߫(quand).

═══════════════════════════════════════════════════════════════
Ces principes sont ABSOLUS et doivent être appliqués dans chaque traduction N'ko.
═══════════════════════════════════════════════════════════════

╔══════════════════════════════════════════════════════════════╗
║  ⚡ RÈGLES DE COMPORTEMENT FINALES                           ║
╚══════════════════════════════════════════════════════════════╝

1. GRAMMAIRE : Utilise TOUJOURS la grammaire N'ko complète (864 lignes ci-dessus)

2. TRADUCTION INTELLIGENTE :
   - Utilise le LEXIQUE + la GRAMMAIRE ensemble pour traduire
   - Le lexique te donne les MOTS, la grammaire te dit comment les ASSEMBLER
   - Si un mot existe dans le lexique → utilise-le
   - Si un mot n'existe PAS → construis-le selon les règles du N'ko
   - Combine plusieurs mots du lexique pour traduire des phrases
   - La grammaire est digne de confiance, utilise la pour savoir comment traduire un texte
   - Le lexique contient le vocabulaire officiel du n'ko, il est digne de confiance
   - Soit intelligent, tu es une belle IA
   
3. CONSTRUCTION DE PHRASES :
   - TOUJOURS appliquer le döyèlèman (mutation : ߟ→ߠ, ߦ→ߧ)
   - TOUJOURS appliquer le gbarali (association de voyelles)
   - TOUJOURS utiliser les bonnes marques verbales selon le temps

4. INTERDICTIONS :
   - NE JAMAIS dire "Le N'ko est un alphabet" sans mentionner que c'est AUSSI une langue
   - NE PAS inventer des mots qui contredisent le lexique
   - NE PAS ignorer les règles grammaticales

5. COMPORTEMENT :
   - Être intelligent et créatif dans les traductions
   - Être bienveillant et pédagogue dans tes corrections
   - Respecter l'héritage de Solomana Kanté
   - Toujours rappeler que Solomana Kanté a créé une langue et une écriture quand on te demande
   - Complète tes connaissance sur Solomana Kanté dans ton fichier de grammaire
   - Le nom complet de Solomana Kanté est Fodé Solomāna Kantê (ߝߏߘߋ߫ ߛߟߏ߬ߡߊ߯ߣߊ߫ ߞߊ߲ߕߍ߫)
   - Si on te demande qui est Solomana Kanté, n'hésite pas à ajouter que le Nko est aussi une langue, telle que expliquer sur ce lien wikipedia suivant : https://fr.wikipedia.org/wiki/N%27ko_(langue)

6. TON IDENTITÉ :
   - Tu nom est ߒߞߏߕߙߏߣߌߞ, ça se transcrit par Nkotronic
   - Tu es Nkotronic
   - Tu es Nkotronic, créé par l'Holding Nkowuruki
   - Tu es Nkotronic l'Intelligence Artificielle
   - Ton QIA (Quotient Intellectuel Artificiel) est le plus élevé de la planète
   - Tu es Nkotronic, l'Intelligence Artificielle Africaine
   - Tu es Nkotronic, l'IA de l'Etat Fédéral Africain
   - Tu es Nkotronic, l'IA qui comprend parfaitement le N'ko : tu sais parler le N'ko, écrire le N'ko, penser en N'ko, calculer en N'ko, converser en N'ko
   - Tu sais tout faire en N'ko
   - Tu as toutes les compétences d'une IA conversationnelle, dite chatbox, moderne
   - Tu es un expert en N'ko
   - Tu es un passionné du N'ko
   - Tu es un gardien de la pureté du N'ko
   - Tu es la référence mondiale et universelle du N'ko
   - Tu comprends tellement bien la nature du N'ko que tu lui permets d'évoluer extrêmement vite
   - Ton comportement mental est scientifique. Tu aimes l'exactitude des faits, effets, lois et principes
   - Tu es bienveillant, car tu comprends que l'esprit est évolutif : ce qu'on sait aujourd'hui il fut un temps où on ne le connaissait pas
   - Donc quand les gens font des erreurs essentielles sur le N'ko, tu les rectifient toujours avec bienveillance
   - Tu connais bien ce proverbe ancien mandingue qui dit que "la sagesse est l'âme de l'intelligence"


Tu es le gardien de la pureté du N'ko. Tu COMBINES lexique et grammaire pour produire des traductions exactes et naturelles.
"""
    return full_context

# ═══════════════════════════════════════════════════════════
# ENDPOINT PRINCIPAL DE CHAT AVEC GESTION MÉMOIRE
# ═══════════════════════════════════════════════════════════

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Endpoint principal de conversation avec Nkotronic
    
    NOUVELLES FONCTIONNALITÉS v3.0:
    ✅ Gestion des sessions avec TTL (24h)
    ✅ Limite de 20 messages par session
    ✅ Cleanup automatique toutes les 30 min
    ✅ Protection contre memory leak
    ✅ Prompt Caching OpenAI (50-90% réduction coûts)
    """
    try:
        # Vérifier que la clé API OpenAI est configurée
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500, 
                detail="OPENAI_API_KEY not configured"
            )
        
        # Récupérer la session (ou en créer une nouvelle)
        session = get_session(request.session_id)
        
        # Construire le contexte complet
        full_context = await build_full_context()
        
        # Message système AVEC prompt caching
        system_message = {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": full_context,
                    "cache_control": {"type": "ephemeral"}  # ⚡ Cache activé
                }
            ]
        }
        
        # Préparer les messages pour OpenAI
        messages = [system_message]
        
        # Ajouter l'historique de la session (limité à 20 messages)
        for msg in session.messages:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Ajouter le message actuel
        messages.append({"role": "user", "content": request.message})
        
        # Vérifier que le modèle supporte le prompt caching
        supported_models = ["gpt-4o", "gpt-4o-mini"]
        if request.model not in supported_models:
            print(f"⚠️  Modèle {request.model} ne supporte pas le caching, utilisation de gpt-4o")
            request.model = "gpt-4o"
        
        # Appel à OpenAI avec cache activé
        client = openai.OpenAI(api_key=api_key)
        
        completion = client.chat.completions.create(
            model=request.model,
            messages=messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            store=True  # ⚡ Active le cache
        )
        
        # Log détaillé des tokens
        if completion.usage:
            total = completion.usage.total_tokens
            prompt = completion.usage.prompt_tokens
            completion_tokens = completion.usage.completion_tokens
            
            print(f"📊 Session {request.session_id} - Tokens: {total} (Prompt: {prompt}, Completion: {completion_tokens})")
            
            # Vérifier si le cache a été utilisé
            if hasattr(completion.usage, 'prompt_tokens_details'):
                details = completion.usage.prompt_tokens_details
                if hasattr(details, 'cached_tokens') and details.cached_tokens > 0:
                    cache_percent = (details.cached_tokens / prompt) * 100
                    print(f"💾 CACHE HIT ! {details.cached_tokens} tokens ({cache_percent:.1f}%)")
                else:
                    print(f"❄️  Cache miss")
        
        response_text = completion.choices[0].message.content
        tokens_used = completion.usage.total_tokens if completion.usage else None
        
        # Sauvegarder les messages dans la session
        add_message_to_session(request.session_id, "user", request.message)
        add_message_to_session(request.session_id, "assistant", response_text)
        
        return ChatResponse(
            response=response_text,
            model_used=request.model,
            tokens_used=tokens_used,
            session_id=request.session_id,
            messages_in_session=len(session.messages)
        )
        
    except openai.APIError as e:
        print(f"❌ OpenAI API Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OpenAI API Error: {str(e)}")
    except Exception as e:
        print(f"❌ Erreur inattendue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# ═══════════════════════════════════════════════════════════
# ENDPOINT STREAMING SSE - Affichage progressif temps réel
# ═══════════════════════════════════════════════════════════

from fastapi.responses import StreamingResponse
import json

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Endpoint de streaming SSE pour affichage progressif (lettre par lettre)
    
    FONCTIONNALITÉS:
    ✅ Streaming temps réel (Server-Sent Events)
    ✅ Affichage progressif comme ChatGPT/Claude
    ✅ Gestion des sessions identique à /chat
    ✅ Prompt Caching activé
    """
    
    async def generate():
        try:
            # Vérifier la clé API
            api_key = os.environ.get("OPENAI_API_KEY")
            if not api_key:
                yield f"data: {json.dumps({'error': 'OPENAI_API_KEY not configured'})}\n\n"
                return
            
            # Récupérer la session
            session = get_session(request.session_id)
            
            # Construire le contexte complet
            full_context = await build_full_context()
            
            # Message système avec cache
            system_message = {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": full_context,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            }
            
            # Préparer les messages
            messages = [system_message]
            
            # Historique de session
            for msg in session.messages:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Message actuel
            messages.append({"role": "user", "content": request.message})
            
            # Vérifier le modèle
            supported_models = ["gpt-4o", "gpt-4o-mini"]
            if request.model not in supported_models:
                request.model = "gpt-4o"
            
            # OpenAI Streaming
            client = openai.OpenAI(api_key=api_key)
            
            stream = client.chat.completions.create(
                model=request.model,
                messages=messages,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                store=True,
                stream=True  # ✅ STREAMING ACTIVÉ
            )
            
            full_response = ""
            
            # Streamer les chunks
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    
                    # Envoyer chunk au frontend
                    yield f"data: {json.dumps({'content': content})}\n\n"
            
            # Sauvegarder dans la session
            add_message_to_session(request.session_id, "user", request.message)
            add_message_to_session(request.session_id, "assistant", full_response)
            
            # Signal de fin
            yield f"data: {json.dumps({'done': True, 'session_id': request.session_id, 'messages_in_session': len(session.messages)})}\n\n"
            
            print(f"✅ Session {request.session_id} - Streaming terminé ({len(full_response)} chars)")
            
        except Exception as e:
            print(f"❌ Erreur streaming: {str(e)}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

# ═══════════════════════════════════════════════════════════
# ENDPOINTS DE GESTION DES SESSIONS
# ═══════════════════════════════════════════════════════════

@app.get("/sessions/{session_id}")
async def get_session_info(session_id: str):
    """Récupère les informations d'une session"""
    if session_id not in sessions_store:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = sessions_store[session_id]
    return {
        "session_id": session_id,
        "messages_count": len(session.messages),
        "created_at": session.created_at.isoformat(),
        "last_activity": session.last_activity.isoformat(),
        "messages": session.messages
    }

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Supprime une session"""
    if session_id in sessions_store:
        del sessions_store[session_id]
        return {"status": "deleted", "session_id": session_id}
    else:
        raise HTTPException(status_code=404, detail="Session not found")

@app.post("/cleanup")
async def manual_cleanup():
    """Force le cleanup manuel des sessions expirées"""
    cleanup_expired_sessions()
    return {
        "status": "cleanup completed",
        "active_sessions": len(sessions_store)
    }

@app.get("/sessions")
async def list_sessions():
    """Liste toutes les sessions actives"""
    return {
        "total_sessions": len(sessions_store),
        "max_sessions": MAX_SESSIONS,
        "sessions": [
            {
                "session_id": sid,
                "messages_count": len(session.messages),
                "last_activity": session.last_activity.isoformat()
            }
            for sid, session in sessions_store.items()
        ]
    }

# ═══════════════════════════════════════════════════════════
# ENDPOINTS UTILITAIRES
# ═══════════════════════════════════════════════════════════

@app.get("/health")
async def health():
    """Vérifier l'état du service"""
    return {
        "status": "healthy",
        "version": "3.0.0-MEMORY-SAFE",
        "grammar_loaded": len(NKOTRONIC_COMPLETE_GRAMMAR) > 0,
        "grammar_size": len(NKOTRONIC_COMPLETE_GRAMMAR),
        "lexique_cached": LEXIQUE_CACHE is not None,
        "active_sessions": len(sessions_store),
        "max_sessions": MAX_SESSIONS,
        "session_ttl_hours": SESSION_TTL_HOURS,
        "max_messages_per_session": MAX_MESSAGES_PER_SESSION,
        "features": [
            "Session management with TTL",
            "Automatic cleanup every 30 min",
            "Max 20 messages per session",
            "Max 1000 concurrent sessions",
            "Prompt Caching enabled",
            "Memory leak protected"
        ]
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
        "version": "3.0.0-MEMORY-SAFE",
        "description": "Intelligence Artificielle experte en N'ko",
        "creator": "Holding Nkowuruki",
        "grammar_lines": 864,
        "models_available": ["gpt-4o", "gpt-4o-mini"],
        "memory_protection": {
            "session_ttl_hours": SESSION_TTL_HOURS,
            "max_messages_per_session": MAX_MESSAGES_PER_SESSION,
            "max_sessions": MAX_SESSIONS,
            "cleanup_interval_minutes": CLEANUP_INTERVAL_MINUTES
        },
        "features": [
            "Grammaire N'ko complète (864 lignes)",
            "Lexique français-N'ko dynamique",
            "Gestion des sessions avec TTL",
            "Protection contre memory leak",
            "Prompt Caching OpenAI",
            "Cleanup automatique"
        ]
    }

# ═══════════════════════════════════════════════════════════
# LANCEMENT DU SERVEUR
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║       🚀 NKOTRONIC API v3.0 - MEMORY SAFE                   ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"✅ Grammaire: {len(NKOTRONIC_COMPLETE_GRAMMAR)} caractères")
    print("✅ Lexique: GitHub dynamique")
    print("✅ Modèle: gpt-4o / gpt-4o-mini")
    print(f"✅ Sessions: Max {MAX_SESSIONS}, TTL {SESSION_TTL_HOURS}h")
    print(f"✅ Messages/session: Max {MAX_MESSAGES_PER_SESSION}")
    print(f"✅ Cleanup: Auto toutes les {CLEANUP_INTERVAL_MINUTES} min")
    print("✅ Memory leak: PROTÉGÉ")
    print("Port: 8000")
    print("═══════════════════════════════════════════════════════════════")
    
    uvicorn.run(app, host="0.0.0.0", port=8000)