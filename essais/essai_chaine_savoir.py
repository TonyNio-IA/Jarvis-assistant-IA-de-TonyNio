# -*- coding: utf-8 -*-
"""Passe les phrases de savoir dans la chaîne réelle (calendrier -> savoir -> date...) : montre qui répond."""
import sys, re, inspect
sys.path.insert(0, r"C:\Jarvis")
import jarvis_commandes as C
import jarvis_local, jarvis_savoir
src = open(r"C:\Jarvis\tests\essai_savoir.py", encoding="utf-8").read()
phr = re.findall(r'^verif\("([^"]+)",\s*\[', src, re.M)
sig = inspect.signature(C.commande_instantanee)
for q in phr:
    try:
        r = C.commande_instantanee([q], lambda *a, **k: None) if len(sig.parameters) >= 2 else C.commande_instantanee([q])
    except Exception as e:
        r = "ERREUR " + repr(e)
    qui = "cal" if jarvis_local.calendrier(C._propre(q)) else ("sav" if jarvis_savoir.commande(C._propre(q), q) else "--")
    print("%-3s | %-52s | %s" % (qui, q, r))
