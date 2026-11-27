# -*- coding: utf-8 -*-
"""Les 13 questions sans réponse dans essai_eventail_local, passées cette fois dans TOUTE la chaîne de Jarvis
(commande_instantanee), sans Claude. Les lancements sont neutralisés : rien n'est ouvert, fermé ni éteint."""
import os, subprocess, sys
sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
os.startfile = lambda *a, **k: print("      (aurait ouvert", a, ")")
import jarvis_commandes as c
import jarvis_claude_reglages
jarvis_claude_reglages.installe = lambda: False          # comme un PC sans Claude
PHRASES = ["combien de jours avant les vacances d'été", "c'est quand le prochain jour férié", "quel est le prochain jour férié",
           "combien de jours fériés en mai", "dans quel département est Toulouse", "200 grammes de farine en tasses",
           "combien font 5000 pas en kilomètres", "combien de syllabes dans chocolat", "quel est le pluriel de cheval",
           "tu es en quelle version", "que sais-tu faire", "bonne nuit", "dis-moi quelque chose de gentil"]
for p in PHRASES:
    try:
        r = c.commande_instantanee([p])
    except Exception as e:
        r = f"ERREUR {type(e).__name__} {e}"
    c._attente = None
    print(f"« {p} »\n   -> {r}")
