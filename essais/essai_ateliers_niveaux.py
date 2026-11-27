# -*- coding: utf-8 -*-
"""Essais : difficulté qui s'adapte, tableau des étoiles, progression vers la récompense (dans un dossier temporaire).
    python-env\\Scripts\\python.exe tests\\essai_ateliers_niveaux.py
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
JARVIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JARVIS)
import jarvis_ateliers as a

echecs = 0


def verifier(nom, ok):
    global echecs
    print(("OK   " if ok else "ÉCHEC") + " " + nom)
    if not ok:
        echecs += 1


dossier = tempfile.mkdtemp()
profil = {"id": "enfant_essai", "enfant": True}

# Niveaux des questions
verifier("niveau 1 : additions jusqu'à 10", all(a._question_calcul("addition", 1)["juste"] <= 10 for _ in range(300)))
verifier("niveau 3 : additions plus grandes", max(a._question_calcul("addition", 3)["juste"] for _ in range(300)) > 20)
verifier("niveau 1 : soustractions positives", all(a._question_calcul("soustraction", 1)["juste"] >= 1 for _ in range(300)))
verifier("niveau 1 : tables jusqu'à 5 fois", all(a._question_calcul("table5", 1)["juste"] <= 25 for _ in range(300)))
verifier("niveau 1 : heures pile", all(a._question_heure(1)["juste"][1] == 0 for _ in range(200)))
verifier("niveau 1 : mots courts en dictée", all(len(a._question_dictee([], 1)["juste"]) <= 4 for _ in range(200)))
verifier("questions toujours avec 3 choix", all(len(set(a._question_heure(n)["choix"])) == 3 for n in (1, 2, 3) for _ in range(100)))

# Trois bonnes réponses du premier coup : le niveau monte
r = a.traiter("on fait des additions", profil, dossier)
verifier("l'atelier démarre avec la progression", r and r["atelier"].get("prochaine", {}).get("reste") == 10)
messages = []
for _ in range(3):
    juste = a._jeux[profil["id"]]["question"]["juste"]
    r = a.traiter(str(juste), profil, dossier)
    messages.append(r["reponse"])
verifier("niveau monté après 3 réussites", a.niveau(dossier, profil["id"], "calcul") == 3 and "je corse" in messages[-1])
verifier("progression : 3 étoiles sur 10", r["atelier"]["prochaine"]["faites"] == 3)

# Deux questions ratées d'affilée : le niveau redescend
for _ in range(2):
    a.traiter("1000", profil, dossier)
    r = a.traiter("1000", profil, dossier)
verifier("niveau redescendu après 2 ratées", a.niveau(dossier, profil["id"], "calcul") == 2 and "plus faciles" in r["reponse"])

# Tableau des étoiles (hors atelier) et pendant un atelier (la question reste affichée)
r = a.traiter("combien j'ai d'étoiles", profil, dossier)
verifier("pendant l'atelier : la question reste affichée", r["atelier"].get("grand"))
a.traiter("on arrête", profil, dossier)
r = a.traiter("combien j'ai d'étoiles", profil, dossier)
verifier("tableau des étoiles", r["atelier"]["jeu"] == "etoiles" and r["atelier"]["tableau"]["total"] == 3
         and r["atelier"]["tableau"]["prochaine"]["quoi"] == "une blague")
verifier("prochaine récompense : thème à 20", a.prochaine(15)["quoi"].startswith("le thème"))

# Mode essai : rien sur le disque
autre = {"id": "enfant_essai2", "enfant": True}
a.traiter("on fait des additions", autre, dossier, essai=True)
for _ in range(3):
    a.traiter(str(a._jeux[autre["id"]]["question"]["juste"]), autre, dossier, essai=True)
verifier("mode essai : niveau gardé en mémoire seulement", "enfant_essai2" not in a._lire_etoiles(dossier))

print("\nTout est bon." if not echecs else f"\n{echecs} échec(s).")
