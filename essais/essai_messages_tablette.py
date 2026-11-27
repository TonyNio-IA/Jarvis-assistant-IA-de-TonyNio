# -*- coding: utf-8 -*-
"""Essai : un message laissé depuis la tablette, puis délivré au bon profil (fichiers temporaires, rien de réel).
    python-env\\Scripts\\python.exe tests\\essai_messages_tablette.py
"""
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8")
JARVIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JARVIS)
import jarvis_foyer
import jarvis_profils

dossier = tempfile.mkdtemp()
jarvis_foyer.FICHIER_MESSAGES = os.path.join(dossier, "messages.json")
jarvis_foyer.FICHIER_CALENDRIER = os.path.join(dossier, "calendrier.json")
echecs = 0


def verifier(nom, ok):
    global echecs
    print(("OK   " if ok else "ÉCHEC") + " " + nom)
    if not ok:
        echecs += 1


connus = [(i, p) for i, p in jarvis_profils._lire().items() if not i.startswith("_") and p.get("prenom")]
if not connus:
    print("Aucun profil secondaire : essai sauté.")
    sys.exit(0)
ident, p = connus[0]
reponse = jarvis_foyer.commande_message(f"dis à {p['prenom'].lower()} que le repas est prêt", moi="")
verifier("message laissé depuis la tablette du profil principal", reponse and reponse.startswith("D'accord"))
verifier("pas de message à soi-même", jarvis_foyer.commande_message("dis à moi que bonjour", moi=ident).startswith("C'est toi"))
attente = jarvis_foyer.messages_en_attente(ident)
verifier("délivré au bon profil", "le repas est prêt" in attente)
verifier("délivré une seule fois", jarvis_foyer.messages_en_attente(ident) == "")

# Calendrier : un rendez-vous dans 3 heures apparaît dans les 24 h à venir de ce profil seulement
jarvis_foyer._ecrire(jarvis_foyer.FICHIER_CALENDRIER, [{"quand": time.time() + 3 * 3600, "quoi": "piscine", "pour": ident,
                                                        "annonces": []}])
verifier("rendez-vous visible pour son profil", [e["quoi"] for e in jarvis_foyer.evenements_a_venir(ident)] == ["piscine"])
verifier("pas pour les autres", jarvis_foyer.evenements_a_venir("") == [])
print("\nTout est bon." if not echecs else f"\n{echecs} échec(s).")
