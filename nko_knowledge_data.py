# =================================================================
# Fichier : nko_knowledge_data.py
# Base de connaissances structurée pour le pré-traitement sémantique
# =================================================================

NKO_STRUCTURED_KNOWLEDGE = {
  
  # --- Propriétés Générales du Système d'Écriture ---
  "GENERAL": {
    "NAME": "N'ko",
    "SCRIPT_NAME": "ߒߞߏ",
    "TRANSLATION_DIRECTION": "Droite vers la gauche",
    "SYSTEM_ORIGIN": "Afrique de l'Ouest (Mandé)",
    "COUNT_LETTERS": 27,
    "ALPHABET_SCRIPT": "ߊ ߋ ߌ ߍ ߎ ߏ ߐ ߒ ߓ ߔ ߕ ߖ ߗ ߘ ߙ ߚ ߛ ߜ ߝ ߞ ߟ ߡ ߢ ߣ ߤ ߥ ߦ",
    "FORGING_RULE": "Chaque lettre (ߛߓߍߘߋ߲) a été forgée soit avec les deux premières lettres (ߊ et ߋ) soit avec l'une des deux uniquement."
  },

  # --- Vocabulaire Clé ---
  # Utilisé par le pré-traitement pour la substitution N'ko -> Français
  "VOCABULARY": {
    "Nko": "ߒߞߏ",
    "lettre": "ߛߓߍߘߋ߲",
    "alphabet": "ߛߓߍߛߎ߲",
    "écriture": "ߛߓߍߛߎ߲",
    "voyelle": ["ߛߌ߰ߙߊ߬ߟߊ߲", "ߟߊߞߎߡߊߟߊ߲"],
    "consonne": "ߛߌ߰ߙߊ߬ߕߊ",
    "semi-voyelle": "ߛߌ߰ߙߊ߬ߟߊ߲߬ߠߊ߬ߡߊ",
    "neutre": "ߕߍߘߐ",
    "nasalisateur": "ߞߊ߲ߠߊߘߌߦߊߟߊ߲",
  },

  # --- Catégories de Lettres ---
  "CATEGORIES": {
    "VOYELLES": {
      "COUNT": 7,
      "SCRIPT": "ߊ ߋ ߌ ߍ ߎ ߏ ߐ",
    },
    "CONSONNES": {
      "COUNT": 19,
      "SCRIPT": "ߓ ߔ ߕ ߖ ߗ ߘ ߙ ߚ ߛ ߜ ߝ ߞ ߟ ߡ ߢ ߣ ߤ ߥ ߦ",
      "BICONSONANTIQUES": "ߖ ߗ ߜ", # 3 consonnes co-articulées
    },
    "SPECIALE_N": { # La lettre ߒ
      "SCRIPT": "ߒ",
      "SOUND_IPA": "ŋ",
      "ROLES": ["semi voyelle", "voyelle neutre", "semi consonne", "consonne neutre", "voyelle et consonne intermédiaire"],
      "ALIAS": ["tèdö", "tèdɔ", "ߕߍߘߐ"],
    }
  },

  # --- Sons et Transcriptions (pour la phonétique) ---
"PHONETICS": {
    "MAP": {
      "a": "ߊ", "e": "ߋ", "i": "ߌ", "ɛ": "ߍ", "u": "ߎ", "o": "ߏ", "ɔ": "ߐ", "ŋ": "ߒ",
      "b": "ߓ", "p": "ߔ", "t": "ߕ", "d͡ʒ": "ߘ", "t͡ʃ": "ߗ", "d": "ߘ", "r": ["ߙ", "ߚ"],
      "s": "ߛ", "ɡ͡b": "ߜ", "f": "ߝ", "k": "ߞ", "l": "ߟ", "m": "ߡ", "ɲ": "ߢ",
      "n": "ߣ", "h": "ߤ", "w": "ߥ", "j": "ߦ",
      # AJOUTS NÉCESSAIRES (exemple, le 'v' n'est pas standard, souvent transcrit par 'f' ou 'w' en Mandé)
      # Supposons qu'il utilise le ߥ (wa) ou ߝ (fa) pour les sons proches du v.
      "v": "ߥ", # Exemple : Mappe V vers ߥ (wa)
      "é": "ߋ", # gérer les accents
      # ... compléter si nécessaire
    }
},

  # --- Règles de Mutation et Nasalisation ---
  "RULES": {
    "NASALISATION": {
      "SCRIPT": "߲",
      "NAME": "Kannadiyalan",
      "DESCRIPTION": "Point de nasalisation mis sous une voyelle (ߛߌ߰ߙߊ߬ߟߊ߲) pour la nasaliser.",
      "RESULT_SCRIPT": "ߊ߲ ߋ߲ ߌ߲ ߍ߲ ߎ߲ ߏ߲ ߐ߲",
    },
    "MUTATION": {
      "LETTRES_MUTANTES": [
        {"LETTER": "ߠ", "ALIAS": "na wolosso", "MUTATES_FROM": "ߟ" },
        {"LETTER": "ߧ", "ALIAS": "ɲa wolosso", "MUTATES_FROM": "ߦ" },
      ],
      "CONDITION": "Quand la lettre est précédée par une voyelle nasalisée ou le tèdö (ߒ).",
    }
  }
}