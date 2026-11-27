# -*- coding: utf-8 -*-
"""Essais des nouvelles commandes d'action, dans le bac à sable (rien n'est fait sur le PC) :
chaque phrase doit donner la bonne réponse ET la bonne action notée (ou aucune action)."""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bac_a_sable as b          # applique le bac à sable avant de charger Jarvis
c = b.c

ok = []


def cas(phrase, reponse, action=None, sans_action=False):
    traitee, r, actions = b.essayer(phrase)
    bon = bool(r) and re.search(reponse, str(r), re.I) is not None
    if action:
        bon = bon and any(re.search(action, a) for a in actions)
    if sans_action:
        bon = bon and not any(re.search(r"ouvre|programme|SendInput|keybd|son :", a) for a in actions)
    ok.append(bon)
    print(("OK   " if bon else "ÉCHEC") + f" « {phrase} » -> {str(r)[:90]}  {actions[:2]}")


cas("lance youtube", r"J'ouvre YouTube", r"ouvre : https://www.youtube.com$")
cas("lance-moi youtube", r"J'ouvre YouTube", r"youtube.com$")
cas("mets une vidéo de recettes", r"YouTube", r"search_query=recettes$")
cas("ouvre le site des impôts", r"le site des impôts", r"impots.gouv.fr")
cas("va sur le site de la mairie", r"le site de la mairie sur Google", r"google.com/search")
cas("ouvre amazon", r"le site d'Amazon", r"amazon.fr")
cas("zoom avant", r"Zoom avant")
cas("dézoome", r"Zoom arrière")
cas("zoom normal", r"Zoom normal")
cas("active le mode avion", r"mode avion", r"ms-settings:network-airplanemode")
cas("active le wifi", r"Wi-Fi|Windows n'a pas accepté", r"programme : powershell")
cas("coupe le wi-fi", r"Wi-Fi|Windows n'a pas accepté", r"programme : powershell")
cas("est-ce que le wifi est activé", r"Wi-Fi|Windows|Je n'arrive", r"programme : powershell")
# la corbeille : question d'abord, puis vidée seulement après « oui » (bloqué ici : noté, jamais fait)
c._corbeille = lambda: (3, 5_000_000)   # une corbeille pleine pour l'essai (la vraie n'est jamais vidée)
b.bloque.clear()
r1 = c.commande_instantanee(["vide la corbeille"])
avant = list(b.bloque)
print("      corbeille ->", r1)
if r1 and "Dis oui" in r1:
    r2 = c.commande_instantanee(["oui"])
    bon = "shell32.SHEmptyRecycleBinW" in b.bloque and "SHEmptyRecycleBinW" not in " ".join(avant)
    print(("OK   " if bon else "ÉCHEC") + f" corbeille : vidée seulement après « oui » -> {r2}")
    b.bloque.clear()
    r1 = c.commande_instantanee(["vide la corbeille"])
    r3 = c.commande_instantanee(["oui mais attends"])
    bon2 = "shell32.SHEmptyRecycleBinW" not in b.bloque
    print(("OK   " if bon2 else "ÉCHEC") + f" corbeille : « oui mais attends » ne vide rien -> {r3}")
    ok += [bon, bon2]
else:
    bon = r1 in ("La corbeille est déjà vide.",)
    print(("OK   " if bon else "ÉCHEC") + " corbeille vide : " + str(r1))
    ok.append(bon)
c._attente = None
# ne doivent pas déclencher ces nouvelles actions
for phrase in ("donne-moi le mot de passe du wifi invité", "quel temps fait-il", "le wifi de la freebox marche ?",
               "je vais au zoo", "parle-moi du mode avion", "ferme les volets", "quitte"):
    traitee, r, actions = b.essayer(phrase)
    bon = not any(re.search(r"airplanemode|powershell.*Radios|SHEmptyRecycleBin|google.com/search\?q=.*site%20officiel", a) for a in actions) \
        and not re.search(r"Zoom|corbeille|mode avion|Wi-Fi coupé", str(r or ""))
    ok.append(bon)
    print(("OK   " if bon else "ÉCHEC") + f" (ne doit rien faire de nouveau) « {phrase} » -> {str(r)[:80]}")
print(f"\n{sum(ok)} / {len(ok)} essais réussis.")
