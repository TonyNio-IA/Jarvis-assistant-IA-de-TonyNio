# -*- coding: utf-8 -*-
"""Essai des reponses locales (calcul, date) : affiche ce que chaque module repond."""
import os, sys, io
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import jarvis_local, jarvis_savoir, jarvis_pratique

PHRASES = [
    "racine carrée de deux", "la racine carrée de deux", "racine carrée de 144", "racine carrée de seize",
    "combien font racine carrée de deux", "quelle est la racine carrée de neuf",
    "quel jour était le premier janvier deux mille", "quel jour était le 1er janvier 2000",
    "quel jour était le quatorze juillet 1789", "quel jour sera le 25 décembre 2030",
    "quel jour est le 14 juillet", "quel jour sommes-nous", "combien de jours a février deux mille dix-huit",
]
for p in PHRASES:
    t = p.lower()
    print("»", p)
    for nom, f in (("local.calendrier", lambda: jarvis_local.calendrier(t)),
                   ("savoir.commande", lambda: jarvis_savoir.commande(t, p)),
                   ("pratique.calcul", lambda: jarvis_pratique.commande_calcul(t))):
        try:
            print("   %-16s %r" % (nom, f()))
        except Exception as e:
            print("   %-16s ERREUR %s: %s" % (nom, type(e).__name__, e))
