# -*- coding: utf-8 -*-
"""La question de premiers pas est dite à part, après la réponse (rien n'est réellement prononcé : parler est remplacé)."""
import os, sys
sys.path.insert(0, r"C:\Jarvis")
os.chdir(r"C:\Jarvis")
import jarvis_claude as jc

dits, echecs = [], 0
jc.PAUSE_AVANT_QUESTION = 0
Q = "Au fait, tu préfères que je parle avec une voix d'homme ou une voix de femme ?"


def verifier(titre, ok, detail=""):
    global echecs
    echecs += not ok
    print(("OK    " if ok else "ECHEC ") + titre + (("  ->  " + str(detail)) if detail != "" else ""))


def parler(texte, toujours=False):
    dits.append(texte)
    return False


jc.parler = parler
appels = []
jc.jarvis_accueil.question = lambda: (appels.append(1) or Q)
jc.jarvis_foyer.a_ajouter_apres = lambda *a: ""

r = jc._poser_question_accueil("Il est 13 heures 27.", False)
verifier("réponse normale : la question est dite seule, à part", dits == [Q] and r is False, dits)
dits.clear(); appels.clear()
r = jc._poser_question_accueil("Il est 13 heures 27.", True)
verifier("réponse interrompue : aucune question, et elle n'est pas marquée comme posée", dits == [] and appels == [] and r is True, (dits, appels))
r = jc._poser_question_accueil("Je ne trouve pas cette application.", False)
verifier("après « je ne trouve pas » : aucune question", dits == [] and appels == [] and r is False, (dits, appels))
jc.jarvis_accueil.question = lambda: ""
r = jc._poser_question_accueil("Il est 13 heures 27.", False)
verifier("aucune question en attente : rien n'est dit", dits == [] and r is False, dits)
jc.jarvis_foyer.a_ajouter_apres = lambda *a: " Tu as gagné trois étoiles cette semaine."
r = jc._poser_question_accueil("Il est 13 heures 27.", False)
verifier("profil enfant : le mot des étoiles est dit à part lui aussi", dits == ["Tu as gagné trois étoiles cette semaine."], dits)
dits.clear()
jc.jarvis_accueil.question = lambda: Q
jc.parler = lambda texte, toujours=False: (dits.append(texte) or True)
r = jc._poser_question_accueil("Il est 13 heures 27.", False)
verifier("question interrompue par « stop » : renvoie True", r is True and dits == [Q], dits)
jc.jarvis_maj.lancee = True
dits.clear()
r = jc._poser_question_accueil("Je lance la mise à jour.", False)
verifier("mise à jour lancée : aucune question", dits == [] and r is False, dits)
print("ECHECS :", echecs)
