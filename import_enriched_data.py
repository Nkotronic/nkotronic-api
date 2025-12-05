#!/usr/bin/env python3
"""
Script d'import des traductions enrichies dans Nkotronic
Usage: python import_enriched_data.py
"""

import json
import requests
import sys

# Configuration
API_URL = "https://nkotronic-api.onrender.com"  # Remplacer par votre URL
ENDPOINT = f"{API_URL}/add_translation"

def load_translations(filepath):
    """Charge les traductions depuis un fichier JSON"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ {len(data)} traductions chargées depuis {filepath}")
        return data
    except FileNotFoundError:
        print(f"❌ Fichier non trouvé: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Erreur de parsing JSON: {e}")
        sys.exit(1)

def import_translations(translations):
    """Envoie les traductions à l'API"""
    try:
        print(f"📤 Envoi de {len(translations)} traductions à {ENDPOINT}...")
        
        response = requests.post(
            ENDPOINT,
            json=translations,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Succès: {result['message']}")
            print(f"   Status Qdrant: {result.get('qdrant_status', 'N/A')}")
            print(f"   Éléments ajoutés: {result.get('elements_added', 0)}")
            return True
        else:
            print(f"❌ Erreur HTTP {response.status_code}")
            print(f"   Détails: {response.text}")
            return False
            
    except requests.exceptions.Timeout:
        print("❌ Timeout: le serveur met trop de temps à répondre")
        return False
    except requests.exceptions.ConnectionError:
        print("❌ Erreur de connexion: impossible de joindre le serveur")
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue: {e}")
        return False

def verify_import(api_url):
    """Vérifie que les données ont bien été importées"""
    try:
        response = requests.get(f"{api_url}/stats", timeout=10)
        if response.status_code == 200:
            stats = response.json()
            print(f"\n📊 STATISTIQUES APRÈS IMPORT:")
            print(f"   Total de points: {stats['total_points']}")
            print(f"   Collection: {stats['collection_name']}")
            if stats.get('sample'):
                print(f"   Échantillon (premiers éléments):")
                for item in stats['sample'][:3]:
                    fr = item.get('element_français', 'N/A')
                    nko = item.get('element_nko', 'N/A')
                    print(f"     - {fr} = {nko}")
        else:
            print(f"⚠️ Impossible de récupérer les stats (HTTP {response.status_code})")
    except Exception as e:
        print(f"⚠️ Erreur lors de la vérification: {e}")

def main():
    """Fonction principale"""
    print("=" * 60)
    print("🚀 IMPORT DE TRADUCTIONS ENRICHIES - NKOTRONIC")
    print("=" * 60)
    
    # Charger les données
    filepath = "exemples_traductions_enrichies.json"
    translations = load_translations(filepath)
    
    # Afficher un aperçu
    print(f"\n📋 APERÇU DES DONNÉES:")
    for i, t in enumerate(translations[:3], 1):
        print(f"   {i}. {t['element_français']} = {t['element_nko']}")
        if t.get('valeur_numerique'):
            print(f"      Valeur: {t['valeur_numerique']}")
        if t.get('fait_texte'):
            print(f"      Info: {t['fait_texte'][:50]}...")
    
    if len(translations) > 3:
        print(f"   ... et {len(translations) - 3} autres")
    
    # Demander confirmation
    print(f"\n⚠️  Vous allez importer {len(translations)} traductions enrichies.")
    confirm = input("   Continuer ? (o/n): ").lower().strip()
    
    if confirm != 'o':
        print("❌ Import annulé")
        sys.exit(0)
    
    # Importer
    success = import_translations(translations)
    
    if success:
        # Vérifier
        verify_import(API_URL)
        print("\n✅ IMPORT TERMINÉ AVEC SUCCÈS!")
    else:
        print("\n❌ ÉCHEC DE L'IMPORT")
        sys.exit(1)

if __name__ == "__main__":
    main()