# -*- coding: utf-8 -*-
"""Essai du mot de remerciement après une mise à jour (jarvis_maj.merci_utilisateur). Ne touche pas aux vrais réglages."""
import sys
sys.path.insert(0, r"C:\Jarvis")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import jarvis_maj as m
import jarvis_rapports as r

etat = {}
r.valeur = lambda cle, defaut=None: etat.get(cle, defaut)
r.regler = lambda cle, val: etat.__setitem__(cle, val)
echecs = 0


def essai(nom, id_, envoyes, notes, vous, attendu_contient, attendu_absent=()):
    global echecs
    etat.clear()
    etat["id"] = id_
    if envoyes:
        etat["messages_envoyes"] = dict(envoyes)
    m._vous = lambda: vous
    sortie = m.merci_utilisateur(notes)
    bon = all(x in sortie for x in attendu_contient) and not any(x in sortie for x in attendu_absent)
    if attendu_contient == [] and sortie != "":
        bon = False
    reste = etat.get("messages_envoyes")
    if envoyes and reste:
        bon = False                                     # le décompte doit être remis à zéro
    print(("OK   " if bon else "ÉCHEC"), nom, "->", repr(sortie))
    if not bon:
        echecs += 1


ID = "a0c818" + "0" * 26
NOTES = "- **Truc** : x\n<!-- jarvis-merci: probleme=a0c818,95c12d idee=a0c818 -->"
essai("rien envoyé, pas dans la liste", "123456" + "0" * 26, None, NOTES, False, [])
essai("signalement envoyé, pas dans la liste", "123456" + "0" * 26, {"probleme": 1}, NOTES, False,
      ["Ton signalement a bien été reçu.", "grâce à toi"], ["corrigé"])
essai("idée envoyée, pas dans la liste", "123456" + "0" * 26, {"idee": 2}, NOTES, False,
      ["Ta suggestion a bien été reçue."], ["prise en compte"])
essai("dans les deux listes", ID, {"probleme": 1, "idee": 1}, NOTES, False,
      ["Le problème que tu as signalé est corrigé", "prise en compte dans cette version"], ["bien été reçu"])
essai("dans la liste sans compteur (envoi d'avant)", ID, None, NOTES, False, ["corrigé", "prise en compte"])
essai("vouvoiement", ID, {"idee": 1}, NOTES, True, ["Le problème que vous avez signalé", "grâce à vous"], ["tu "])
essai("hors ligne (notes vides), idée envoyée", "123456" + "0" * 26, {"idee": 1}, "", False,
      ["Ta suggestion a bien été reçue."])
essai("hors ligne, rien envoyé", "123456" + "0" * 26, None, "", False, [])
essai("liste d'un autre genre seulement", "95c12d" + "0" * 26, None,
      "<!-- jarvis-merci: idee=a0c818 -->", False, [])
print("\n=== %d ÉCHEC(S) ===" % echecs)
