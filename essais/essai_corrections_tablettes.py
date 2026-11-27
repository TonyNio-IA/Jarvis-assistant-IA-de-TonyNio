# -*- coding: utf-8 -*-
"""Essai des corrections tirées de l'usage réel des tablettes.
    python-env\\Scripts\\python.exe tests\\essai_corrections_tablettes.py
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_corrections as c

echecs = 0
for avant, attendu in (("Mais, un minuteur de 30 secondes pour les pâtes.", "mets un minuteur de 30 secondes"),
                       ("Mais, un limiteur de 20 secondes.", "mets un minuteur de 20 secondes"),
                       ("J'avise.", "Jarvis"), ("Jean-Vice", "Jarvis"), ("J'arvisse !", "Jarvis"),
                       ("mais un jour je viendrai", "mais un jour je viendrai"), ("j'avise demain", "j'avise demain"),
                       ("parle-moi de GTA 6", "GTA 6"),
                       ("Mais en compte à report de 10 secondes.", "mets un compte à rebours de 10 secondes"),
                       ("Qu'est-leur il est ?", "quelle heure est-il"),
                       ("Trouvement une recette pour les crêpes.", "trouve-moi une recette"),
                       ("le compte à rebours", "le compte à rebours")):
    apres = c.corriger(avant)
    ok = attendu.lower() in apres.lower()
    echecs += not ok
    print(("OK   " if ok else "ÉCHEC") + f" « {avant} » -> « {apres} »")
print("\nTout est bon." if not echecs else f"\n{echecs} échec(s).")
