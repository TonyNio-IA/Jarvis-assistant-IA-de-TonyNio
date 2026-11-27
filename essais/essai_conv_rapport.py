# -*- coding: utf-8 -*-
"""Rapport complet : « par » + « autre » ; rien en enfant ; aucune écriture réelle (mémoire et journal simulés)."""
import sys
sys.path.insert(0, r"C:\Jarvis")
import jarvis_rapports as r, jarvis_memoire as m, jarvis_enfant as e
notes = []
r.noter = lambda genre, **i: notes.append((genre, i))
m._charger = lambda: {"echanges": []}
m._enregistrer = lambda: None
m._invite = lambda: False
echecs = 0
def ok(c, msg):
    global echecs
    echecs += (not c)
    print("OK   " if c else "ECHEC", msg)

e.actif = lambda: False
m.noter_echange("quel jour tombe le 14 juillet 2030", "Le 14 juillet 2030, c'est un dimanche.", "local", "quel jour tombe le quatorze juillet deux mille trente")
g, i = notes[-1]
ok(g == "conversation" and i.get("par") == "local" and "autre" in i, "local + autre version envoyés : %r" % (i,))
m.noter_echange("bonjour", "Salut.", "claude", "Bonjour")
ok(notes[-1][1].get("par") == "claude" and "autre" not in notes[-1][1], "même texte (casse) : pas d'« autre »")
m.noter_echange("ancien appel", "réponse")
ok(notes[-1][1].get("par") is None, "appel sans « par » : compatible")
n = len(notes)
e.actif = lambda: True
m.noter_echange("phrase d'un enfant", "réponse enfant", "local", "autre")
ok(len(notes) == n, "profil enfant : rien dans le rapport")
e.actif = lambda: False
m._invite = lambda: True
m.noter_echange("phrase invité", "réponse", "local", "x")
ok(len(notes) == n, "mode invité : rien")
# niveau « technique » : la vraie fonction noter ne garde pas les conversations
r2 = __import__("importlib").reload(r)
r2._donnees = {"niveau": "technique"}
r2._invite = lambda: False
sauve = []
r2.JOURNAL = r"C:\Jarvis\tests\sortie\journal_essai.jsonl"
import os
if os.path.exists(r2.JOURNAL):
    os.remove(r2.JOURNAL)
r2.conversation("a", "b", "local", "c")
ok(not os.path.exists(r2.JOURNAL), "niveau technique : conversation non gardée")
r2._donnees = {"niveau": "complet"}
r2.conversation("quel mois sommes-nous", "Nous sommes en novembre 2026.", "local", "dans quel mois on est")
ok(os.path.exists(r2.JOURNAL) and '"par": "local"' in open(r2.JOURNAL, encoding="utf-8").read(), "niveau complet : gardée avec par")
if os.path.exists(r2.JOURNAL):
    os.remove(r2.JOURNAL)
print("ECHECS :", echecs)
sys.exit(1 if echecs else 0)
