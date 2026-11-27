"""Essai : la question « tutoyer ou vouvoyer » n'est posée qu'une fois, plus si la personne a déjà choisi,
et une question sans réponse est abandonnée après deux fois. (Fichier provisoire : le vrai accueil.json n'est pas touché.)"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_accueil as a

ok = True
def verif(nom, cond):
    global ok
    print(("OK  " if cond else "ECHEC ") + nom); ok = ok and cond

a.FICHIER = os.path.join(tempfile.gettempdir(), "essai_accueil.json")
if os.path.exists(a.FICHIER):
    os.remove(a.FICHIER)
a._ecrire({"nouveau": True, "faites": ["voix", "ville", "couleur"]})
import jarvis_personnalite
choix = {"v": None}
jarvis_personnalite.vouvoiement = lambda: choix["v"]

def lancement():
    a._pose.update(question=None, moment=0.0, lancement=False)
    return a.question()

verif("1er lancement : la question est posée", "tutoie" in lancement())
verif("même lancement : pas de seconde question", a.question() == "")
verif("2e lancement sans réponse : posée encore une fois", "tutoie" in lancement())
verif("3e lancement sans réponse : abandonnée", "tutoie" not in lancement())

a._ecrire({"nouveau": True, "faites": ["voix", "ville", "couleur"]})
choix["v"] = False                                   # la personne a dit « on peut se tutoyer » avant
verif("déjà choisi autrement : la question n'est pas posée", "tutoie" not in lancement())
os.remove(a.FICHIER)
print("RESULTAT :", "TOUT EST BON" if ok else "ECHEC")
sys.exit(0 if ok else 1)
