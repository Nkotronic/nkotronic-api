import json
import re

# 1. Nom de votre fichier lexique
# **ASSUREZ-VOUS QUE CE NOM DE FICHIER EST CORRECT**
FILE_PATH = "vocab_global (2).txt"

# Fonction de nettoyage pour créer un 'concept_identifie' valide (sans caractères spéciaux)
def clean_for_concept(text):
    # Convertir en minuscules
    text = text.lower()
    # Remplacer les espaces et les tirets par des underscores
    text = re.sub(r'[\s\-]+', '_', text)
    # Supprimer tous les caractères qui ne sont ni alphanumériques ni des underscores
    text = re.sub(r'[^\w]', '', text)
    # Tronquer l'ID pour éviter les longueurs excessives (max 50 caractères)
    return text[:50]

# Fonction principale pour charger le lexique et transformer
def generate_bcs_facts(file_path):
    print(f"Chargement et conversion du lexique depuis : {file_path}")
    try:
        # Lire le fichier en gérant l'encodage
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERREUR: Le fichier '{file_path}' n'a pas été trouvé. Veuillez vérifier le nom.")
        return []
    except json.JSONDecodeError as e:
        print(f"ERREUR de décodage JSON. Vérifiez la structure de votre fichier: {e}")
        return []

    facts = []
    # Assurez-vous d'accéder à la liste sous la clé 'vocab'
    vocab_list = data.get("vocab", [])

    for item in vocab_list:
        nko_term = item.get("a", "").strip()
        french_term = item.get("b", "").strip()
        
        if nko_term and french_term:
            # Créer l'identifiant unique basé sur la traduction
            concept_key = clean_for_concept(f"traduction_{french_term}_nko")

            fact = {
                "concept_identifie": concept_key,
                "element_français": f"Le mot français '{french_term}' se traduit en N'ko par {nko_term}.",
                "element_nko": nko_term,
                "note_grammaticale": "Vocabulaire de base."
            }
            facts.append(fact)
            
    return facts

# Générer les faits
new_facts = generate_bcs_facts(FILE_PATH)

# =======================================================
# ÉCRITURE DANS UN FICHIER JSON SÉPARÉ
# =======================================================
OUTPUT_FILE = "bcs_lexique_auto.json"

if new_facts:
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            # Écrire la liste des dictionnaires directement en JSON
            json.dump(new_facts, f, indent=4, ensure_ascii=False)
        
        print("\n" + "#" * 50)
        print(f"# ✅ SUCCÈS : {len(new_facts)} FAITS LEXICAUX SAUVEGARDÉS dans '{OUTPUT_FILE}'")
        print("#" * 50)
        print("ACTION REQUISE : Modifier nkotronic_api.py pour charger ce fichier.")
        
    except Exception as e:
        print(f"ERREUR lors de l'écriture du fichier {OUTPUT_FILE}: {e}")
        
else:
    print("\nAucun fait n'a été généré. Veuillez vérifier le fichier et la structure JSON.")