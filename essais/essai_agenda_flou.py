# -*- coding: utf-8 -*-
"""Essai de l'agenda iCloud avec les phrases réellement mal entendues au micro (18/11/2026).
Utilise un agenda d'essai en mémoire : ne touche pas au vrai agenda."""
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_agenda as a
import jarvis_claude

erreurs = 0


def verifie(nom, ok):
    global erreurs
    print(("OK   " if ok else "ERREUR ") + nom)
    erreurs += not ok


d = datetime.datetime.now() + datetime.timedelta(days=2)
ics = ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1\r\nSUMMARY:Rendez-vous test pour Jarvis ￼\r\n"
       f"DTSTART:{d:%Y%m%d}T124500\r\nDTEND:{d:%Y%m%d}T134500\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
a._lien = lambda: "https://exemple.invalid/agenda.ics"
a._cache.update(quand=10 ** 12, texte=ics)

for phrase in ["c'est quand le rendez-vous de test", "C'est Khan, le rendez-vous de test.", "c'est ca le rendez-vous de test",
               "Seconde, le rendez-vous, test.", "c'est quand mon prochain rendez-vous", "c'est ça le rendez-vous test", "C'est Carl Rendez-vous, test !",
               "c'est cols le rendez-vous test", "Second, le rendez-vous test."]:
    r = a.commande(phrase)
    verifie(f"« {phrase} » -> {r}", bool(r) and "12 h 45" in r and "￼" not in r)
for phrase in ["c'est Marie", "c'est ça le problème", "c'est comme ça", "c'est quand Noël"]:
    r = a.commande(phrase)
    verifie(f"« {phrase} » laissé aux autres -> {r}", r is None)
a.note_claude()
n = a.note_claude("C'est comme mon prochain man de vous. c'est quand mon prochain ne vous")
verifie("note pour Claude avec les rendez-vous", "12 h 45" in n and "Rendez-vous test" in n)
verifie("pas de note hors sujet", a.note_claude("quelle heure est-il") == "")
for phrase in ["redémarre", "Redémarre.", "jarvis redémarre", "redémarre-toi"]:
    verifie(f"« {phrase} » redémarre", bool(jarvis_claude.DEMANDE_REDEMARRAGE.search(phrase.lower())))
verifie("« redémarre la vidéo » ne redémarre pas Jarvis",
        not jarvis_claude.DEMANDE_REDEMARRAGE.search("redémarre la vidéo"))
print("erreurs :", erreurs)
sys.exit(1 if erreurs else 0)
