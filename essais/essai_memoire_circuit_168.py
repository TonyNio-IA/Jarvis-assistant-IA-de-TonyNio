# -*- coding: utf-8 -*-
"""Mémoire par sujet dans le vrai circuit des commandes (bac à sable : copie de Jarvis, rien ne se passe sur le PC)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b
import jarvis_memoire as m
sys.stdout.reconfigure(encoding="utf-8")
ok = total = 0


def verifier(bon, quoi):
    global ok, total
    total += 1
    ok += bool(bon)
    print("OK " if bon else "NON", quoi)


m.tout_effacer()                      # (mémoire de la copie du bac à sable)
verifier("jarvis_bac" in m.FICHIER.lower() or "temp" in m.FICHIER.lower(), "mémoire de l'essai : dans la copie provisoire (" + m.FICHIER[-40:] + ")")
for phrase in ("retiens que ma voiture est une Clio grise", "retiens qu'on a décidé de refaire la terrasse en mai"):
    t, r, a = b.essayer(phrase)
    verifier(t and r == "C'est retenu.", f"« {phrase} » -> {r}")
cas = [("qu'est-ce que tu as retenu sur ma voiture", "Clio"),
       ("rappelle-moi ce qu'on avait décidé pour la terrasse", "terrasse en mai"),
       ("qu'est-ce qu'on avait décidé pour le jardin", "rien retenu sur le jardin"),
       ("qu'est-ce que tu sais sur ma voiture", "Clio"),
       ("cherche dans ta mémoire la terrasse", "terrasse en mai")]
for phrase, attendu in cas:
    t, r, a = b.essayer(phrase)
    verifier(t and attendu in str(r) and not a, f"« {phrase} » -> {str(r)[:90]}")
t, r, a = b.essayer("rappelle-moi dans 10 minutes de sortir le linge")
verifier(t and "retenu" not in str(r).lower() and "10 minutes" in str(r), "un vrai rappel reste un rappel -> " + str(r)[:80])
t, r, a = b.essayer("qu'est-ce que tu sais sur les trous noirs")
verifier("retenu" not in str(r).lower(), "« sais sur les trous noirs » : pas la mémoire -> " + str(r)[:70])
t, r, a = b.essayer("qu'est-ce que tu as retenu")
verifier(t and "2 choses" in str(r), "liste complète, comme avant -> " + str(r)[:80])
print(f"\n{ok} / {total} essais réussis.")
