# -*- coding: utf-8 -*-
"""Essais de la page et du serveur de la tablette (réacteur au style du PC, voix en deux morceaux, cache, « répète »).
    python-env\\Scripts\\python.exe tests\\essai_tablette_112.py
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
JARVIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, JARVIS)
import jarvis_tablette as t

echecs = 0


def verifier(nom, ok):
    global echecs
    print(("OK   " if ok else "ÉCHEC") + " " + nom)
    if not ok:
        echecs += 1


p = t.PAGE
verifier("réacteur dessiné (plus de __REACTEUR__)", "__REACTEUR__" not in p and 'class="a ga"' in p and 'class="a gb"' in p)
verifier("onde de réveil", 'id="onde_reveil"' in p and "@keyframes reveil" in p)
verifier("filaments qui suivent la voix", "#rond .ga,#rond .gb{scale:" in p and "function enveloppe" in p)
verifier("réponse mot à mot", "function suivreVoix" in p and "function toutAfficher" in p)
verifier("cadre à pans coupés", "clip-path:polygon(15px 0" in p)
verifier("mesure de fluidité", "function mesurerFluidite" in p and "body.leger" in p)
verifier("voix en deux morceaux (page)", "partie: 1" in p and "function jouer" in p)
verifier("aucun code de profil dans la page", not re.search(r"\b(1211|1401)\b", p))

# Voix coupée en deux : seulement les longues réponses, à la fin d'une phrase
court = "Il est 21 heures."
verifier("réponse courte : un seul morceau", t._parties_voix(court) == [court])
long = ("Voici la recette des crêpes. Il te faut 250 grammes de farine, quatre œufs, un demi-litre de lait, "
        "une pincée de sel et un peu de beurre fondu pour la poêle.")
parts = t._parties_voix(long)
verifier("longue réponse : deux morceaux", len(parts) == 2 and parts[0] == "Voici la recette des crêpes." and " ".join(parts) == long)
sans_point = "a" * 300
verifier("sans fin de phrase : un seul morceau", t._parties_voix(sans_point) == [sans_point])

# « répète »
for phrase in ("répète", "Jarvis, tu peux répéter ?", "redis-le", "j'ai pas compris", "Pardon ?", "quoi",
               "qu'est-ce que tu as dit"):
    verifier(f"« {phrase} » = répéter", bool(t._REPETE.search(phrase)))
for phrase in ("quoi de neuf", "répartis les tâches", "met de la musique", "dis-moi une blague"):
    verifier(f"« {phrase} » n'est pas « répète »", not t._REPETE.search(phrase))

verifier("« répète à X que… » est un message, pas « répète »", not t._REPETE.search("répète à papa que je l'aime"))

# Aide
for phrase in ("qu'est-ce que tu sais faire", "aide", "aide-moi", "qu'est-ce que je peux te demander", "que sais-tu faire"):
    verifier(f"« {phrase} » ouvre l'aide", bool(t._AIDE.search(t._net(phrase))))
verifier("« aide-moi à faire mes devoirs » n'ouvre pas l'aide", not t._AIDE.search(t._net("aide-moi à faire mes devoirs")))
verifier("écran d'aide dans la page", 'id="p_aide"' in p and "function aide()" in p and 'a.type === "aide"' in p)

# Calendrier familial et messages entre profils (sans écrire dans les vrais fichiers)
import jarvis_foyer
verifier("calendrier : fonction des rendez-vous à venir", callable(jarvis_foyer.evenements_a_venir))
verifier("le profil principal = \"\" pour le foyer", t._ident_foyer({"id": t.PRINCIPAL}) == "" and t._ident_foyer({"id": "x"}) == "x")
verifier("rendez-vous affichés dans la page", 'm.genre === "agenda"' in p)

# Le cache de la voix ne garde que des phrases courtes
verifier("cache : longueur limitée", t.CACHE_VOIX_LONGUEUR <= 200 and t.CACHE_VOIX_MAX >= 100)

print("\nTout est bon." if not echecs else f"\n{echecs} échec(s).")
