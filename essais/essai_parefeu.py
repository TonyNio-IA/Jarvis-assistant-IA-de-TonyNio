# -*- coding: utf-8 -*-
"""Essai : commande « autorise les tablettes » et diagnostic du pare-feu, sans jamais toucher au vrai pare-feu."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import jarvis_parefeu, jarvis_tablette as jt

appels = []
jarvis_parefeu.ajouter = lambda: appels.append("ajouter") or True      # jamais de vraie demande à Windows ici
erreurs = 0


def verifier(nom, ok):
    global erreurs
    print(("OK   " if ok else "ÉCHEC"), nom)
    erreurs += 0 if ok else 1


present = {"v": False}
jarvis_parefeu.regle_presente = lambda: present["v"]

for phrase in ("autorise les tablettes", "Jarvis, autorise les tablettes.", "débloque les tablettes",
               "ouvre le pare-feu pour la tablette", "règle le pare-feu des tablettes"):
    appels.clear()
    r = jt.commande(phrase.lower())
    time.sleep(0.2)
    verifier(f"« {phrase} » → autorisation demandée", bool(r) and "réponds Oui" in r and appels == ["ajouter"])

appels.clear()
r = jt.commande("autorise les tablettes", enfant=True)
verifier("enfant : refusé, rien demandé à Windows", "adulte" in (r or "") and not appels)

present["v"] = True
appels.clear()
r = jt.commande("autorise les tablettes")
time.sleep(0.2)
verifier("règle déjà là : « c'est déjà fait », rien demandé", "déjà fait" in (r or "") and not appels)

for phrase in ("mets une vidéo youtube sur la tablette", "quelle heure est-il", "est-ce que la tablette est activée"):
    r = jt.commande(phrase)
    verifier(f"« {phrase} » n'est pas une commande de pare-feu", not r or "pare-feu" not in r)

d = jarvis_parefeu.diagnostic()
verifier("diagnostic : liste de phrases", isinstance(d, list) and all(isinstance(s, str) for s in d))
print("diagnostic :", d, "| adresse :", jarvis_parefeu.adresse_locale())
print("RÉSULTAT :", "tout est bon" if not erreurs else f"{erreurs} échec(s)")
sys.exit(1 if erreurs else 0)
