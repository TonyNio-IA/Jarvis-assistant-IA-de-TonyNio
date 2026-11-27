# -*- coding: utf-8 -*-
"""« Jarvis » pendant que Jarvis parle : ignoré seulement pendant le morceau où il dit son nom (et 1,5 s après)."""
import sys, time
sys.path.insert(0, r"C:\Jarvis")
import jarvis_claude as jc
import jarvis_voix as jv

ok = []


def verifier(nom, cond):
    ok.append(cond)
    print(("OK   " if cond else "ÉCHEC") + " " + nom)


jc.rec_coupure = None
jv._morceau("Voici ta réponse, première partie.")
verifier("morceau sans le nom : « jarvis » entendu coupe", not jc._nom_dit_par_jarvis())
jv._morceau("Dis simplement « Jarvis, ouvre Chrome ».")
verifier("morceau où Jarvis dit son nom : ignoré (écho)", jc._nom_dit_par_jarvis())
jv._morceau("Et voici la suite de la réponse.")
verifier("juste après ce morceau : encore ignoré (écho qui traîne)", jc._nom_dit_par_jarvis())
jc._suivi_morceau["fin_nom"] -= jc.ECHO_NOM_S + 0.1
verifier("1,5 s plus tard : « jarvis » coupe de nouveau", not jc._nom_dit_par_jarvis())
src = open(r"C:\Jarvis\jarvis_claude.py", encoding="utf-8").read()
verifier("phrases d'attente coupables (parler au lieu de speak)", "coupe = parler(phrase_patience(minuscules))" in src)
print(f"{sum(ok)} / {len(ok)} essais réussis.")
