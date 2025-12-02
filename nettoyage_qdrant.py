# Fichier : nettoyage_qdrant.py

import os
from qdrant_client import QdrantClient, models
from dotenv import load_dotenv

# --- CONFIGURATION FIXÉE ---
load_dotenv() # Charge QDRANT_URL et QDRANT_API_KEY depuis .env

# Définition manuelle du nom de la collection :
COLLECTION_NAME = "nkotronic_knowledge_base"  # <-- VALEUR FIXÉE

# Récupération des autres variables du .env (qui sont bien là)
QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# --- INITIALISATION DU CLIENT ---
try:
    QDRANT_CLIENT = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    print("Connexion Qdrant établie pour le nettoyage.")
except Exception as e:
    print(f"Erreur de connexion Qdrant: {e}")
    QDRANT_CLIENT = None

# ... (Le reste du code de nettoyage) ...