"""
JARVIS - gardien.

C'est lui que le raccourci lance. Il démarre Jarvis (jarvis_reacteur.py) et le surveille :
  - si Jarvis plante ou perd le micro, il le relance tout seul ;
  - si Jarvis reste figé (son affichage ne bat plus depuis 5 minutes), il l'arrête et le relance ;
  - si une nouvelle version ne démarre pas (3 arrêts de suite, juste après une mise à jour), il remet la version
    d'avant, gardée dans le dossier version_precedente ;
  - si tu choisis « Arrêter Jarvis » (clic droit sur le réacteur), il s'arrête aussi ;
  - « Jarvis, redémarre-toi » relance Jarvis proprement.
Après 5 relances en 10 minutes, il attend une minute entre deux essais, pour ne pas tourner en rond.
Il n'utilise aucun autre programme de Jarvis : il doit marcher même si l'un d'eux est abîmé.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

DOSSIER = os.path.dirname(os.path.abspath(__file__))
JOURNAL = os.path.join(DOSSIER, "jarvis.log")
CODE_REDEMARRER = 3          # Jarvis demande lui-même à être relancé
CODE_ARRET_EXTERIEUR = 0x40010004   # arrêté de l'extérieur (Gestionnaire des tâches, autre programme) : pas un plantage

# --- Jarvis figé ---
BATTEMENT = "battement.txt"  # l'affichage de Jarvis y écrit l'heure toutes les 10 secondes
FIGE_APRES = 300             # secondes sans battement avant de le dire figé
PAS = 5                      # secondes entre deux coups d'œil
BLOCAGES_PAR_HEURE = 2       # au-delà, on ne l'arrête plus (pour ne jamais tourner en rond)

# --- Retour à la version d'avant ---
PRECEDENT = "version_precedente"     # copie des programmes faite par Jarvis juste avant une mise à jour
RETOUR = "retour_version.json"       # dit à Jarvis quelle version ne démarrait pas (il ne la réinstalle pas)
ARRET_RAPIDE = 120           # un arrêt en moins de 2 minutes, juste après une mise à jour, compte comme « ne démarre pas »
ARRETS_AVANT_RETOUR = 3
VALIDEE_APRES = 600          # 10 minutes sans arrêt : la nouvelle version est bonne, la copie d'avant est effacée


def noter(message):
    try:
        with open(chemin("jarvis.log"), "a", encoding="utf-8") as f:
            f.write(f"[gardien {time.strftime('%d/%m %H:%M:%S')}] {message}\n")
    except OSError:
        pass


def chemin(*morceaux):
    return os.path.join(DOSSIER, *morceaux)


def version_installee(dossier=None):
    """Le numéro de version écrit dans jarvis_claude.py, ou « » s'il est illisible."""
    try:
        with open(os.path.join(dossier or DOSSIER, "jarvis_claude.py"), encoding="utf-8", errors="replace") as f:
            trouve = re.search(r'(?m)^VERSION\s*=\s*"([^"]+)"', f.read(200_000))
        return trouve.group(1) if trouve else ""
    except OSError:
        return ""


# ---------- Jarvis figé ----------

def age_du_battement(debut, maintenant=None):
    """Depuis combien de secondes l'affichage de Jarvis n'a pas battu. None tant que CE lancement n'a pas encore
    battu une première fois (démarrage en cours, ou ancienne version qui ne bat pas)."""
    try:
        dernier = os.path.getmtime(chemin(BATTEMENT))
    except OSError:
        return None
    if dernier < debut:
        return None
    return (maintenant or time.time()) - dernier


def est_fige(debut, repit, blocages, maintenant=None):
    """Vrai si Jarvis est figé : plus de battement depuis FIGE_APRES secondes, hors sortie de veille du PC (repit)
    et sans dépasser BLOCAGES_PAR_HEURE."""
    maintenant = maintenant or time.time()
    age = age_du_battement(debut, maintenant)
    if age is None or age < FIGE_APRES or maintenant - repit < FIGE_APRES:
        return False
    return len([b for b in blocages if maintenant - b < 3600]) < BLOCAGES_PAR_HEURE


# ---------- Retour à la version d'avant ----------

def sauvegarde_en_attente():
    """Les informations de la copie faite avant la dernière mise à jour, ou None s'il n'y en a pas (ou plus)."""
    try:
        with open(chemin(PRECEDENT, "version.json"), encoding="utf-8") as f:
            infos = json.load(f)
        return infos if isinstance(infos, dict) and infos.get("version") else None
    except (OSError, ValueError):
        return None


def valider_version():
    """La nouvelle version tourne bien : la copie de l'ancienne ne sert plus."""
    if os.path.isdir(chemin(PRECEDENT)):
        shutil.rmtree(chemin(PRECEDENT), ignore_errors=True)
        noter("la version installée tourne bien : copie de la version d'avant effacée.")


def revenir_en_arriere():
    """Remet les programmes de la version d'avant. Renvoie (version qui ne démarrait pas, version remise), ou None
    si ce n'est pas possible (pas de copie, copie incomplète, ou même version)."""
    infos = sauvegarde_en_attente()
    if not infos:
        return None
    source = chemin(PRECEDENT)
    try:
        fichiers = [n for n in os.listdir(source) if n.startswith("jarvis_") and n.endswith(".py")]
    except OSError:
        return None
    ancienne, nouvelle = version_installee(source), version_installee()
    # copie complète (le nombre de fichiers noté au départ), lisible, et bien d'une autre version
    try:
        attendus = int(infos.get("fichiers") or 1)
    except (TypeError, ValueError):
        attendus = 1
    if (not ancienne or ancienne == nouvelle or len(fichiers) < attendus
            or "jarvis_reacteur.py" not in fichiers or "jarvis_gardien.py" not in fichiers):
        return None
    try:
        for nom in fichiers:
            shutil.copy2(os.path.join(source, nom), chemin(nom))
    except OSError as erreur:
        noter(f"retour à la version {ancienne} impossible : {erreur}")
        return None
    try:
        with open(chemin(RETOUR), "w", encoding="utf-8") as f:
            json.dump({"refusee": nouvelle, "revenue": ancienne, "quand": int(time.time())}, f)
    except OSError:
        pass
    try:
        os.remove(chemin("mise_a_jour.json"))              # le bilan « la mise à jour n'a pas abouti » serait en trop
    except OSError:
        pass
    shutil.rmtree(source, ignore_errors=True)
    return nouvelle, ancienne


def ecrire_reprise(cause, detail):
    reprise = chemin("reprise.json")                       # Jarvis dira au redémarrage qu'il s'est relancé
    if cause in ("retour", "blocage") or not os.path.exists(reprise):   # (sauf s'il a déjà noté la cause lui-même)
        try:
            with open(reprise, "w", encoding="utf-8") as f:
                json.dump({"quand": int(time.time()), "cause": cause, "detail": detail}, f)
        except OSError:
            pass


def arret_exterieur(code):
    """Code 1 sans « Erreur Jarvis » ni « s'arrête de lui-même » juste avant dans le journal : fermé de l'extérieur."""
    if code == CODE_ARRET_EXTERIEUR:
        return True
    if code != 1:
        return False
    try:
        journal = chemin("jarvis.log")
        with open(journal, encoding="utf-8", errors="replace") as f:
            f.seek(max(0, os.path.getsize(journal) - 4000))
            fin = f.read()
        fin = fin[fin.rfind("===== "):] if "===== " in fin else fin
        return ("Erreur Jarvis" not in fin and "s'arrête de lui-même" not in fin and "Traceback" not in fin
                and "Fatal Python error" not in fin and "SyntaxError" not in fin)
    except OSError:
        return False


def surveiller(processus, debut, blocages):
    """Attend la fin de Jarvis. Renvoie son code de sortie, ou « blocage » s'il a fallu l'arrêter parce qu'il était figé."""
    repit = dernier_tour = time.time()
    while True:
        try:
            return processus.wait(timeout=PAS)
        except subprocess.TimeoutExpired:
            pass
        maintenant = time.time()
        if maintenant - dernier_tour > 60:                 # le PC sort de veille : on laisse à Jarvis le temps de repartir
            repit = maintenant
        dernier_tour = maintenant
        if maintenant - debut >= VALIDEE_APRES and sauvegarde_en_attente():
            valider_version()
        if est_fige(debut, repit, blocages, maintenant):
            noter(f"Jarvis est figé (son affichage ne bat plus depuis {age_du_battement(debut, maintenant):.0f} s) : "
                  "arrêt, puis relance.")
            blocages.append(maintenant)
            try:
                processus.kill()
                processus.wait(timeout=20)
            except Exception:
                pass
            return "blocage"


def apres_arret(code, duree, arrets_rapides):
    """Jarvis vient de s'arrêter (ni arrêt demandé, ni redémarrage à la voix) : note la cause, et remet la version
    d'avant si la nouvelle ne démarre pas. Renvoie le nouveau compte d'arrêts rapides."""
    if code == "blocage":
        ecrire_reprise("blocage", "affichage figé")
        return arrets_rapides
    exterieur = arret_exterieur(code)
    noter((f"Jarvis a été arrêté de l'extérieur (code {code}, sans message d'erreur : sans doute un autre programme)"
           if exterieur else f"Jarvis s'est arrêté tout seul (code {code})") + f" après {duree:.0f} s : relance.")
    ecrire_reprise("exterieur" if exterieur else "plantage", f"code {code}")
    if duree >= ARRET_RAPIDE:
        return 0
    if exterieur or not sauvegarde_en_attente():
        return arrets_rapides
    arrets_rapides += 1                                    # juste après une mise à jour : elle ne démarre pas ?
    if arrets_rapides < ARRETS_AVANT_RETOUR:
        return arrets_rapides
    retour = revenir_en_arriere()
    if retour:
        noter(f"la version {retour[0]} ne démarre pas sur ce PC ({ARRETS_AVANT_RETOUR} arrêts de suite) : "
              f"retour à la version {retour[1]}.")
        ecrire_reprise("retour", f"{retour[0]} -> {retour[1]}")
    return 0


def main():
    verrou = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        verrou.bind(("127.0.0.1", 47822))          # un seul gardien à la fois
    except OSError:
        return
    environnement = dict(os.environ, JARVIS_GARDIEN="1")
    relances, blocages, arrets_rapides = [], [], 0
    while True:
        debut = time.time()
        processus = subprocess.Popen([sys.executable, chemin("jarvis_reacteur.py")], cwd=DOSSIER, env=environnement)
        code = surveiller(processus, debut, blocages)
        if code == 0:
            return                                 # arrêt demandé (ou Jarvis tournait déjà)
        if code == CODE_REDEMARRER:
            noter("redémarrage demandé à la voix.")
            time.sleep(1)
            continue
        arrets_rapides = apres_arret(code, time.time() - debut, arrets_rapides)
        relances = [t for t in relances if time.time() - t < 600] + [time.time()]
        time.sleep(60 if len(relances) > 5 else 3)


if __name__ == "__main__":
    main()
