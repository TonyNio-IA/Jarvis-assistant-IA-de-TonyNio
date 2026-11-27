# -*- coding: utf-8 -*-
"""Désinstallation : essai complet sur un FAUX dossier de Jarvis, de faux raccourcis et une clé de registre d'essai.
Le vrai Jarvis (C:\\Jarvis, ses raccourcis, sa clé de registre, Python, Claude) n'est jamais touché : aucun composant
n'est désinstallé pendant l'essai, et les garde-fous sont vérifiés (dossier qui n'est pas un Jarvis, fichier sans nom Jarvis)."""
import os
import shutil
import subprocess
import sys
import tempfile
import winreg
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding="utf-8")
import jarvis_config
import jarvis_desinstaller as d

erreurs = 0


def verifie(nom, ok):
    global erreurs
    print(("OK   " if ok else "ERREUR ") + nom)
    erreurs += not ok


def ecrire(chemin, contenu="x"):
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)


base = tempfile.mkdtemp(prefix="jarvis-essai-desinst-")
faux = os.path.join(base, "Jarvis")
bureau = os.path.join(base, "Bureau")
for nom in ("jarvis_gardien.py", "jarvis_claude.py", "config.json", "memoire.json", "notes.txt", "jarvis.log",
            os.path.join("profils", "lea", "voix.json"), os.path.join("tele", "teles.json"),
            os.path.join("python-env", "Scripts", "python.exe"), os.path.join("python-env", "Lib", "site-packages", "a", "b", "c.py"),
            os.path.join("enregistrements", "son.wav")):
    ecrire(os.path.join(faux, nom))
ecrire(os.path.join(bureau, "Jarvis.lnk"))
ecrire(os.path.join(bureau, "Autre programme.lnk"))
trace = os.path.join(base, "jarvis-trace.txt")
precieux = os.path.join(base, "important.txt")
ecrire(trace)
ecrire(precieux)
CLE = r"Software\Jarvis-TonyNio-essai"
with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLE) as k:
    winreg.SetValueEx(k, "Dossier", 0, winreg.REG_SZ, faux)


def cle_existe(nom):
    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, nom))
        return True
    except OSError:
        return False


vraie_cle = cle_existe(d.CLE_REGISTRE)

# 1. garder et copie compressée
garde, nombre = d.garder(os.path.join(bureau, d.NOM_DOSSIER_GARDE), dossier=faux)
verifie(f"fichiers personnels gardés ({nombre})", nombre == 5 and os.path.isfile(os.path.join(garde, "profils", "lea", "voix.json"))
        and os.path.isfile(os.path.join(garde, "config.json")) and not os.path.exists(os.path.join(garde, "jarvis_claude.py"))
        and not os.path.exists(os.path.join(garde, "jarvis.log")))
copie = d.sauvegarde(bureau, dossier=faux)
with zipfile.ZipFile(copie) as z:
    noms = sorted(n.replace("\\", "/") for n in z.namelist())
verifie(f"copie compressée : {noms}", noms == ["config.json", "memoire.json", "notes.txt", "profils/lea/voix.json", "tele/teles.json"])

# 2. garde-fou : un dossier qui n'est pas un Jarvis n'est jamais supprimé
pas_jarvis = os.path.join(base, "Documents importants")
ecrire(os.path.join(pas_jarvis, "photo.jpg"))
bilan = os.path.join(base, "bilan1.txt")
r = subprocess.run(d.preparer(dossier=pas_jarvis, liens=[], autres=[], cle="HKCU:\\" + CLE, silencieux=True, resultat=bilan),
                   capture_output=True, creationflags=0x08000000, timeout=120)
verifie("dossier qui n'est pas un Jarvis : refusé, rien supprimé", r.returncode == 1 and os.path.isfile(os.path.join(pas_jarvis, "photo.jpg"))
        and cle_existe(CLE) and "n'a pas commencé" in open(bilan, encoding="utf-8").read())

# 3. désinstallation complète du faux Jarvis (aucun composant : ni Python, ni Claude, ni Visual C++)
bilan = os.path.join(base, "bilan2.txt")
commande = d.preparer(garder_dans=garde, dossier=faux, liens=[os.path.join(bureau, "Jarvis.lnk"), os.path.join(bureau, "Autre programme.lnk")],
                      autres=[trace, precieux], cle="HKCU:\\" + CLE, silencieux=True, resultat=bilan)
plan = open(commande[-1], encoding="utf-8").read()
verifie("le plan ne désinstalle aucun composant", '"python": false' in plan and '"claude": false' in plan and '"vc": false' in plan)
r = subprocess.run(commande, capture_output=True, creationflags=0x08000000, timeout=180)
texte = open(bilan, encoding="utf-8").read() if os.path.exists(bilan) else ""
print("      bilan :", texte.replace("\n", " | "))
verifie("le faux dossier de Jarvis a disparu", not os.path.exists(faux))
verifie("le raccourci Jarvis a disparu, l'autre raccourci est resté", not os.path.exists(os.path.join(bureau, "Jarvis.lnk"))
        and os.path.exists(os.path.join(bureau, "Autre programme.lnk")))
verifie("la trace au nom de Jarvis a disparu", not os.path.exists(trace))
verifie("un fichier sans le nom de Jarvis est refusé et signalé", os.path.exists(precieux) and "important.txt" in texte and r.returncode == 2)
verifie("la clé de registre d'essai a disparu", not cle_existe(CLE))
verifie("les fichiers gardés sont toujours là", os.path.isfile(os.path.join(garde, "memoire.json")) and garde in texte)

# 4. le vrai Jarvis n'a pas bougé
verifie("le vrai dossier de Jarvis est intact", os.path.isfile(jarvis_config.chemin("jarvis_gardien.py"))
        and os.path.isdir(jarvis_config.chemin("python-env")))
verifie("la vraie clé de registre est intacte", cle_existe(d.CLE_REGISTRE) == vraie_cle)
verifie("Claude Code est intact", os.path.exists(d.CLAUDE_EXE) or not os.path.exists(os.path.dirname(d.CLAUDE_EXE)))

# 5. récapitulatif et composants
lignes = d.recapitulatif(True, False)
verifie("récapitulatif (garder) : " + str(len(lignes)) + " lignes", any("PAS supprimés" in l for l in lignes))
lignes = d.recapitulatif(False, True)
verifie("récapitulatif (supprimer, avec copie)", any("copie compressée" in l for l in lignes))
liste = d.composants()
print("      composants trouvés :", [(c, par) for c, _, par in liste], "| noté par l'installateur :", d.trace())
verifie("composants : liste lisible", all(c in ("python", "claude", "vc") for c, _, _ in liste))

shutil.rmtree(base, ignore_errors=True)
print("erreurs :", erreurs)
sys.exit(1 if erreurs else 0)
