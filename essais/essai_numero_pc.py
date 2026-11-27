# -*- coding: utf-8 -*-
"""Essai du numéro anonyme lié au PC (1.63) : aucun envoi réseau, dossier temporaire, vrais réglages intacts."""
import json
import os
import re
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Jarvis")
import jarvis_rapports as r  # noqa: E402

erreurs = []


def verifier(cond, quoi):
    print(("OK  " if cond else "ÉCHEC ") + quoi)
    if not cond:
        erreurs.append(quoi)


def neuf(nom):
    dossier = tempfile.mkdtemp(prefix="jarvis_numero_")
    r.FICHIER = os.path.join(dossier, nom)
    r._donnees = None


vrai = r._numero_du_pc

# 1. la fonction elle-même
n1, n2 = vrai(), vrai()
if sys.platform == "win32":
    verifier(n1 is not None and re.fullmatch(r"[0-9a-f]{32}", n1) is not None, "numéro du PC : 32 caractères hexadécimaux")
    verifier(n1 == n2, "le même numéro à chaque lecture")
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as cle:
            guid = str(winreg.QueryValueEx(cle, "MachineGuid")[0]).strip().lower()
        verifier(guid.replace("-", "") not in n1 and guid not in n1, "l'identifiant de Windows n'apparaît pas dans le numéro")
    except OSError:
        verifier(True, "(identifiant Windows illisible ici : vérification sautée)")
else:
    verifier(n1 is None, "hors Windows : pas de numéro de PC (numéro au hasard)")

# 2. première installation : le numéro du PC est pris
neuf("a.json")
r._numero_du_pc = lambda: "ab" * 16
verifier(r.valeur("id") == "ab" * 16, "première installation : numéro = celui du PC")
verifier("ancien_id" not in r._lire(), "rien à garder de l'ancien numéro")

# 3. réinstallation (réglages effacés) : même numéro
fichier = r.FICHIER
os.remove(fichier)
r._donnees = None
verifier(r.valeur("id") == "ab" * 16, "réinstallation : le même numéro revient")

# 4. mise à jour d'un PC qui avait un numéro au hasard : bascule une fois, l'ancien reste sur le PC
neuf("b.json")
with open(r.FICHIER, "w", encoding="utf-8") as f:
    json.dump({"id": "1" * 32, "niveau": "technique"}, f)
r._numero_du_pc = lambda: "cd" * 16
verifier(r.valeur("id") == "cd" * 16, "mise à jour : le numéro du PC remplace l'ancien numéro au hasard")
verifier(r._lire().get("ancien_id") == "1" * 32, "l'ancien numéro est gardé sur le PC (jamais envoyé)")
verifier(r.valeur("niveau") == "technique", "les autres réglages sont conservés")
with open(r.FICHIER, encoding="utf-8") as f:
    verifier(json.load(f)["id"] == "cd" * 16, "le numéro est bien enregistré")

# 5. Windows ne donne rien : numéro au hasard, stable ensuite
neuf("c.json")
r._numero_du_pc = lambda: None
premier = r.valeur("id")
verifier(re.fullmatch(r"[0-9a-f]{32}", premier) is not None, "sans identifiant Windows : numéro au hasard valide")
r._donnees = None
verifier(r.valeur("id") == premier, "ce numéro au hasard reste le même ensuite")

# 6. « Effacer mes données » : le numéro du PC reste, rien n'est envoyé pour de vrai
neuf("d.json")
r._numero_du_pc = lambda: "ef" * 16
envois = []
r._envoyer = lambda charge: envois.append(charge) or True
r._vider_journal = lambda: None
r.valeur("id")
verifier(r.effacer_mes_donnees(), "« Effacer mes données » réussit")
verifier(envois and envois[0].get("genre") == "effacer" and envois[0].get("id") == "ef" * 16, "la demande d'effacement porte le numéro du PC")
verifier(r.valeur("id") == "ef" * 16, "après l'effacement, le numéro du PC reste le même")

r._numero_du_pc = vrai
print()
print("TOUT EST BON" if not erreurs else "ÉCHECS : %d" % len(erreurs))
sys.exit(1 if erreurs else 0)
