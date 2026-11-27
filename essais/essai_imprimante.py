# -*- coding: utf-8 -*-
"""Essai de l'imprimante : phrases et aiguillage avec une imprimante imaginaire.
Avec --reel : interroge aussi la vraie imprimante (lecture seule, rien n'est imprimé)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_imprimante as imp
import jarvis_commandes

erreurs = 0


def verifie(nom, ok):
    global erreurs
    print(("OK   " if ok else "ERREUR ") + nom)
    erreurs += not ok


p = imp.phrase({"marker-names": ["tri-color ink", "black ink"], "marker-levels": [50, 20], "printer-state": [3],
                "printer-state-reasons": ["marker-supply-low-warning"]})
verifie(p, "couleur à 50 %" in p and "noir à 20 %" in p and "noire est presque vide" in p)
p = imp.phrase({"marker-names": ["black ink"], "marker-levels": [0], "printer-state": [5],
                "printer-state-reasons": ["media-empty", "marker-supply-empty"]})
verifie(p, "noire est vide" in p and "plus de papier" in p and p.count("vide") == 1)
p = imp.phrase({"marker-names": ["cyan ink"], "marker-levels": [-3], "printer-state": [4]})
verifie(p, "niveau inconnu" in p and "en train d'imprimer" in p)

reel = "--reel" in sys.argv
if not reel:
    imp._adresse = lambda forcer=False: "192.0.2.1"
    imp.interroger = lambda ip: {"marker-names": ["black ink"], "marker-levels": [70], "printer-state": [3]}
for phrase in ["il reste combien d'encre", "Jarvis, c'est quoi le niveau d'encre ?", "est-ce que l'imprimante est allumée",
               "comment va l'imprimante", "niveau des cartouches", "il reste de l'encre dans l'imprimante ?"]:
    r = jarvis_commandes.commande_instantanee([phrase])
    verifie(f"« {phrase} » -> {r}", bool(r) and ("encre" in r.lower() or "imprimante" in r.lower()))
for phrase in ["imprime ce document", "c'est quoi l'encre de chine", "combien coûte une cartouche d'encre HP 305",
               "quelle heure est-il"]:
    verifie(f"« {phrase} » n'est pas pour l'imprimante", imp.commande(jarvis_commandes._propre(phrase)) is None)
print("erreurs :", erreurs)
sys.exit(1 if erreurs else 0)
