# -*- coding: utf-8 -*-
"""Avertissement « disque presque plein » : rare, seulement si ça empire, désactivable. Tout dans le bac à sable
(une copie de Jarvis : le vrai disque.json n'est pas touché)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b
import jarvis_disque as d
sys.stdout.reconfigure(encoding="utf-8")
J = 86400
T0 = 1_800_000_000
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


f = d.faut_il_prevenir
verifier(not f(200, 476, {}, T0), "disque bien rempli (200 Go sur 476) : rien")
verifier(not f(40, 237, {}, T0), "40 Go libres sur 237 (17 %) : rien")
verifier(f(15 * 0.99, 237, {}, T0), "14,9 Go sur 237 (6 %) : prévenu une première fois")
verifier(not f(20, 1000, {}, T0), "20 Go sur 1 To : au-dessus de 15 Go, rien")
verifier(f(4, 2000, {}, T0), "4 Go libres, même sur un grand disque : prévenu")
deja = {"dernier": T0, "libre_go": 14}
verifier(not f(14, 237, deja, T0 + 1 * J), "le lendemain, même place : silence")
verifier(not f(13, 237, deja, T0 + 10 * J), "10 jours après, à peine moins : silence")
verifier(not f(6, 237, deja, T0 + 2 * J), "2 jours après, divisé par deux : silence quand même (3 jours mini)")
verifier(f(6, 237, deja, T0 + 4 * J), "4 jours après, place divisée par deux : prévenu (ça empire)")
verifier(f(13, 237, deja, T0 + 31 * J), "31 jours après, toujours plein : un rappel")
verifier(f(1.5, 237, {"dernier": T0, "libre_go": 2.5}, T0 + 4 * J), "passe sous 2 Go : prévenu")
verifier(not f(1, 237, {"coupe": True}, T0), "avertissements coupés : jamais")

# verifier() : ne parle qu'une fois, puis la place revient, puis manque de nouveau
dits = []
d.place = lambda: (10.0, 237.0)
d._ecrire({})
verifier(d.verifier(dits.append, T0) and len(dits) == 1, "1er contrôle (10 Go) : une phrase -> " + dits[0][:70])
verifier(not d.verifier(dits.append, T0 + 6 * 3600) and len(dits) == 1, "6 h plus tard : rien")
d.place = lambda: (60.0, 237.0)
d.verifier(dits.append, T0 + 2 * J)
d.place = lambda: (10.0, 237.0)
verifier(d.verifier(dits.append, T0 + 6 * J) and len(dits) == 2, "place libérée puis de nouveau pleine : re-prévenu")
verifier("1,5" in d.phrase(1.5) and "gigaoctet" in d.phrase(1.5), "phrase sous 2 Go -> " + d.phrase(1.5)[:60])

# commandes vocales, par le vrai chemin des commandes
for phrase, attendu in (("Jarvis, ne me préviens plus pour le disque", "ne te préviendrai plus"),
                        ("préviens-moi pour le disque", "de nouveau"),
                        ("arrête de me prévenir pour le disque plein", "ne te préviendrai plus")):
    traitee, r, _ = b.essayer(phrase)
    verifier(r and attendu in r, f"« {phrase} » -> {r}")
verifier(d._lire().get("coupe") is True, "réglage gardé : coupé")
for phrase in ("combien de place sur le disque", "préviens-moi dans 10 minutes", "mets un disque de jazz"):
    traitee, r, _ = b.essayer(phrase)
    verifier(not (r and "préviendrai" in r), f"« {phrase} » n'est pas pris pour le réglage -> {str(r)[:70]}")
print(f"\n{ok} / {total} essais réussis.")
