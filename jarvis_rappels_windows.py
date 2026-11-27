# -*- coding: utf-8 -*-
"""
JARVIS - les rappels sont aussi confiés à Windows (Planificateur de tâches).

Quand Jarvis tourne, c'est lui qui dit le rappel, comme avant. Mais si Jarvis est fermé ou planté à ce moment-là,
Windows lance ce fichier, qui affiche le rappel dans une petite fenêtre : un rappel n'est plus jamais perdu.
  - une tâche par rappel prévu dans plus de 5 minutes, rangée dans le dossier « Jarvis » du Planificateur ;
  - la tâche ne contient pas le texte du rappel, seulement un numéro ; le texte reste dans rappels.json ;
  - elle se supprime toute seule une fois passée, et Jarvis retire celles des rappels annulés ;
  - aucun droit d'administrateur : ce sont des tâches de l'utilisateur.
Lancé par Windows :  pythonw jarvis_rappels_windows.py <numéro>
"""

import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from xml.sax.saxutils import escape

import jarvis_config

PREFIXE = "\\Jarvis\\Rappel-"
FICHIER_RAPPELS = jarvis_config.chemin("rappels.json")
FICHIER_VIE = jarvis_config.chemin("jarvis_en_vie.txt")      # Jarvis y écrit l'heure toutes les 20 secondes
AVANCE_MIN = 5 * 60          # un rappel à moins de 5 minutes n'est pas confié à Windows
RETARD_TACHE = 20            # la tâche part 20 secondes après l'heure : Jarvis, s'il tourne, a déjà dit le rappel
MAX_TACHES = 40
SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_actif = False               # mis à Vrai par Jarvis à son démarrage (jamais pendant les essais)
_demande = threading.Event()
_verrou = threading.Lock()
_dernier_battement = 0.0
_erreur_dite = False


def empreinte(r):
    """Le numéro d'un rappel : il change si l'heure ou le texte change (un rappel répété a donc une tâche par fois)."""
    return hashlib.sha256(f"{int(r.get('quand', 0))}|{r.get('message', '')}".encode("utf-8")).hexdigest()[:12]


def _schtasks(*arguments, delai=30):
    return subprocess.run(["schtasks", *arguments], capture_output=True, timeout=delai, creationflags=SANS_FENETRE)


def _python():
    dossier = os.path.dirname(sys.executable)
    sans_console = os.path.join(dossier, "pythonw.exe")
    return sans_console if os.path.exists(sans_console) else sys.executable


def _xml(quand, ident):
    debut = datetime.datetime.fromtimestamp(quand + RETARD_TACHE).replace(microsecond=0)
    fin = debut + datetime.timedelta(days=3)                   # PC éteint à l'heure dite : rattrapé pendant 3 jours
    utilisateur = (os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "")).strip("\\")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Rappel de Jarvis : affiché par Windows si Jarvis est fermé à ce moment-là.</Description></RegistrationInfo>
  <Triggers><TimeTrigger><StartBoundary>{debut.isoformat()}</StartBoundary><EndBoundary>{fin.isoformat()}</EndBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>{escape(utilisateur)}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT1H</ExecutionTimeLimit><DeleteExpiredTaskAfter>PT0S</DeleteExpiredTaskAfter><Enabled>true</Enabled></Settings>
  <Actions Context="Author"><Exec><Command>{escape(_python())}</Command><Arguments>"{escape(os.path.abspath(__file__))}" {ident}</Arguments><WorkingDirectory>{escape(jarvis_config.DOSSIER)}</WorkingDirectory></Exec></Actions>
</Task>"""


def creer(r):
    """Crée (ou remplace) la tâche Windows de ce rappel. Renvoie True si Windows l'a acceptée."""
    ident = empreinte(r)
    fichier = os.path.join(tempfile.gettempdir(), f"jarvis-rappel-{ident}.xml")
    try:
        with open(fichier, "w", encoding="utf-16") as f:
            f.write(_xml(r["quand"], ident))
        resultat = _schtasks("/Create", "/TN", PREFIXE + ident, "/XML", fichier, "/F")
        if resultat.returncode != 0:
            raise OSError((resultat.stderr or resultat.stdout).decode("cp850", "replace").strip()[:200])
        return True
    finally:
        try:
            os.remove(fichier)
        except OSError:
            pass


def supprimer(ident):
    return _schtasks("/Delete", "/TN", PREFIXE + ident, "/F").returncode == 0


def existantes():
    """Les numéros des tâches « Rappel » de Jarvis déjà dans le Planificateur."""
    sortie = _schtasks("/Query", "/FO", "CSV", "/NH", delai=60).stdout.decode("cp850", "replace")
    trouvees = set()
    for ligne in sortie.splitlines():
        nom = ligne.split('","')[0].strip('"')
        if nom.lower().startswith(PREFIXE.lower()):
            trouvees.add(nom[len(PREFIXE):])
    return trouvees


def synchroniser(rappels=None):
    """Met le Planificateur d'accord avec rappels.json : crée les tâches qui manquent, retire celles en trop."""
    global _erreur_dite
    with _verrou:
        try:
            rappels = _lire() if rappels is None else rappels
            maintenant = time.time()
            voulus = {}
            for r in sorted(rappels, key=lambda x: x.get("quand", 0)):
                if r.get("quand", 0) - maintenant > AVANCE_MIN and len(voulus) < MAX_TACHES:
                    voulus[empreinte(r)] = r
            deja = existantes()
            for ident in deja - set(voulus):
                supprimer(ident)
            crees = sum(1 for ident, r in voulus.items() if ident not in deja and creer(r))
            if crees or deja - set(voulus):
                print(f"(Rappels confiés à Windows : {len(voulus)} en place.)")
            return len(voulus)
        except Exception as erreur:
            if not _erreur_dite:                               # dit une fois, pas à chaque rappel
                _erreur_dite = True
                print("(Rappels : Windows n'a pas pris la tâche de secours :", type(erreur).__name__, erreur, ")")
            return None


def activer():
    """Au démarrage de Jarvis : les rappels sont désormais doublés par Windows."""
    global _actif
    if _actif or os.name != "nt":
        return
    _actif = True

    def boucle():
        while True:
            _demande.wait()
            time.sleep(1.5)                                    # plusieurs écritures de suite : une seule mise à jour
            _demande.clear()
            synchroniser()
    threading.Thread(target=boucle, daemon=True, name="rappels-windows").start()
    _demande.set()


def a_change():
    """rappels.json vient d'être écrit : le Planificateur sera mis d'accord, en arrière-plan."""
    if _actif:
        _demande.set()


def battement():
    """Jarvis signale qu'il tourne (au plus une écriture toutes les 20 secondes)."""
    global _dernier_battement
    if time.time() - _dernier_battement < 20:
        return
    _dernier_battement = time.time()
    try:
        with open(FICHIER_VIE, "w", encoding="utf-8") as f:
            f.write(str(int(_dernier_battement)))
    except OSError:
        pass


# ---------- Côté Windows : Jarvis est-il là ? Sinon, on affiche le rappel ----------

def _lire():
    try:
        with open(FICHIER_RAPPELS, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, list) else []
    except (OSError, ValueError):
        return []


def _ecrire(rappels):
    provisoire = FICHIER_RAPPELS + ".tmp"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(rappels, f, ensure_ascii=False, indent=1)
    os.replace(provisoire, FICHIER_RAPPELS)


def jarvis_en_vie():
    try:
        return time.time() - os.path.getmtime(FICHIER_VIE) < 50
    except OSError:
        return False


def _prochaine_fois(jours, h, m, apres):
    base = datetime.datetime.fromtimestamp(apres)
    for ecart in range(0, 8):
        cible = (base + datetime.timedelta(days=ecart)).replace(hour=h, minute=m, second=0, microsecond=0)
        if cible.weekday() in jours and cible.timestamp() > apres:
            return cible.timestamp()
    return apres + 7 * 86400


def texte_du_rappel(r):
    message, pour = str(r.get("message", "")), r.get("pour")
    if pour and message.startswith("Rappel : "):
        return f"Rappel pour {pour} : " + message[len("Rappel : "):]
    return message


def secours(ident, attente=40, attente_jarvis=90, afficher=None):
    """Lancé par Windows à l'heure du rappel. Si Jarvis s'en est occupé, rien. Sinon : la fenêtre du rappel.
    Renvoie le texte affiché, ou None."""
    debut = time.time()
    limite = debut + attente
    while True:
        r = next((x for x in _lire() if empreinte(x) == ident), None)
        if r is None:
            return None                                        # Jarvis l'a dit (ou le rappel a été annulé)
        if jarvis_en_vie():
            limite = max(limite, debut + attente_jarvis)       # Jarvis tourne : on lui laisse le temps
        if time.time() >= limite:
            break
        time.sleep(min(3, max(0.2, limite - time.time())))
    restants = [x for x in _lire() if empreinte(x) != ident]
    suivant = None
    if r.get("repete"):                                        # rappel répété : la fois suivante est reprogrammée
        q = time.localtime(r["quand"])
        suivant = dict(r, quand=_prochaine_fois(r["repete"], q.tm_hour, q.tm_min, time.time()))
        restants.append(suivant)
    _ecrire(restants)
    if suivant:
        try:
            creer(suivant)
        except Exception:
            pass
    texte = texte_du_rappel(r)
    (afficher or _fenetre)(texte, r.get("quand", time.time()))
    return texte


def _fenetre(texte, quand):
    import tkinter as tk
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass
    racine = tk.Tk()
    racine.title("Jarvis - Rappel")
    racine.configure(bg="#0b1420")
    racine.attributes("-topmost", True)
    heure = time.strftime("%H h %M", time.localtime(quand))
    tk.Label(racine, text="Rappel de Jarvis", bg="#0b1420", fg="#ff8c42", font=("Segoe UI Semibold", 15)).pack(padx=28, pady=(20, 4))
    tk.Label(racine, text=texte, bg="#0b1420", fg="#e8eef5", font=("Segoe UI", 13), wraplength=440, justify="center").pack(padx=28, pady=8)
    tk.Label(racine, text=f"Prévu à {heure}. Jarvis était fermé : c'est Windows qui te le rappelle.", bg="#0b1420",
             fg="#8a9bb0", font=("Segoe UI", 9), wraplength=440, justify="center").pack(padx=28, pady=(2, 10))
    tk.Button(racine, text="D'accord", command=racine.destroy, bg="#ff8c42", fg="#0b1420", relief="flat",
              font=("Segoe UI Semibold", 11), padx=22, pady=6, cursor="hand2").pack(pady=(0, 20))
    racine.update_idletasks()
    largeur, hauteur = racine.winfo_reqwidth(), racine.winfo_reqheight()
    racine.geometry(f"+{(racine.winfo_screenwidth() - largeur) // 2}+{(racine.winfo_screenheight() - hauteur) // 3}")
    racine.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        secours(sys.argv[1])
