# -*- coding: utf-8 -*-
"""
Jarvis - santé.

  - diagnostic() : vérifie le micro, le haut-parleur, Vosk, Whisper, Claude, la connexion, la reconnaissance
    des voix, le disque et les fichiers de Jarvis. Sert à l'onglet « Santé » des réglages et à la commande
    « Jarvis, fais un diagnostic ».
  - noter_cause() / phrase_reprise() : quand Jarvis plante ou perd le micro, le gardien le relance ;
    au redémarrage, Jarvis dit ce qui s'est passé.
"""
import json
import os
import re
import shutil
import socket
import sys
import threading
import time

import jarvis_config

DOSSIER = os.path.dirname(os.path.abspath(__file__))
FICHIER_REPRISE = jarvis_config.chemin("reprise.json")
REPRISE_MAX = 600            # secondes : une cause plus ancienne n'est plus annoncée

OK, ATTENTION, ERREUR, INCONNU = "ok", "attention", "erreur", "inconnu"


# ---------- Reprise après un problème ----------

def noter_cause(erreur):
    """Appelé juste avant que Jarvis ne s'arrête sur une erreur : le gardien va le relancer."""
    texte = str(erreur or "")
    cause = "micro" if re.search(r"micro|input|device|périphérique|audio", texte, re.I) else "plantage"
    try:
        with open(FICHIER_REPRISE, "w", encoding="utf-8") as f:
            json.dump({"quand": time.time(), "cause": cause, "detail": texte[:200]}, f, ensure_ascii=False)
    except OSError:
        pass


def phrase_reprise():
    """Au démarrage : la phrase qui dit pourquoi Jarvis vient de se relancer, ou None."""
    try:
        with open(FICHIER_REPRISE, encoding="utf-8") as f:
            infos = json.load(f)
        os.remove(FICHIER_REPRISE)
    except (OSError, ValueError):
        return None
    if not isinstance(infos, dict) or time.time() - float(infos.get("quand", 0)) > REPRISE_MAX:
        return None
    if infos.get("cause") == "micro":
        return "Le micro ne répondait plus, je me suis relancé. Tout est reparti."
    if infos.get("cause") == "mise_a_jour":       # relancé depuis le PC après des améliorations (tests/redemarrer_jarvis.py)
        return "Je me suis relancé avec les dernières améliorations. Je t'écoute."
    return "J'ai rencontré un souci et je me suis relancé tout seul. Tout est reparti."


# ---------- Diagnostic ----------

def _jarvis():
    return sys.modules.get("jarvis_claude")      # présent seulement dans le processus de Jarvis


def _micro():
    try:
        import sounddevice as sd
        info = sd.query_devices(kind="input")
        sd.check_input_settings(samplerate=16000, channels=1, dtype="int16")
        return OK, info["name"]
    except Exception as erreur:
        return ERREUR, f"aucun micro utilisable ({erreur})"


def _haut_parleur():
    try:
        import sounddevice as sd
        return OK, sd.query_devices(kind="output")["name"]
    except Exception as erreur:
        return ERREUR, f"aucune sortie son ({erreur})"


def _vosk():
    j = _jarvis()
    chemin = getattr(j, "MODEL_PATH", None) or os.path.join(DOSSIER, "vosk-model-small-fr-0.22")
    return (OK, "modèle français présent") if os.path.isdir(chemin) else (ERREUR, "modèle français introuvable")


def _whisper():
    j = _jarvis()
    if j is None:
        return INCONNU, "visible seulement depuis Jarvis"
    if getattr(j, "whisper", None) is not None:
        return OK, "prêt"
    return ATTENTION, "pas encore chargé (Jarvis utilise Vosk en attendant)"


def _claude():
    j = _jarvis()
    if j is None:
        return INCONNU, "visible seulement depuis Jarvis"
    proc = getattr(getattr(j, "claude", None), "proc", None)
    if proc is not None and proc.poll() is None:
        return OK, "prêt en continu"
    return ATTENTION, "pas démarré : il se lancera à la prochaine question"


def _connexion():
    for hote in ("github.com", "speech.platform.bing.com"):
        try:
            socket.create_connection((hote, 443), timeout=3).close()
        except OSError:
            return ERREUR, f"pas d'accès à {hote} : la voix et Claude ne marcheront pas"
    return OK, "Internet et la voix en ligne joignables"


def _voix():
    try:
        import jarvis_locuteur
        if jarvis_locuteur.disponible():
            return OK, "reconnaissance des voix prête"
        if _jarvis() is None:
            return INCONNU, "visible seulement depuis Jarvis"
        if os.path.isdir(os.path.join(DOSSIER, "vosk-model-spk-0.4")):
            return ATTENTION, "modèle présent, en cours de chargement"
        return ATTENTION, "modèle des voix absent : Jarvis ne sait pas qui parle"
    except Exception as erreur:
        return ATTENTION, str(erreur)


def _disque():
    try:
        libre = shutil.disk_usage(DOSSIER).free / 1e9
        if libre < 1:
            return ERREUR, f"plus que {libre:.1f} Go libres"
        return (ATTENTION if libre < 5 else OK), f"{libre:.0f} Go libres"
    except OSError as erreur:
        return INCONNU, str(erreur)


def _fichiers():
    abimes = []
    for nom in ("profils.json", "preferences.json", "memoire.json", "calendrier.json", "messages.json",
                "corrections.json", "enfant.json"):
        chemin = jarvis_config.chemin(nom)
        if os.path.exists(chemin):
            try:
                with open(chemin, encoding="utf-8-sig") as f:
                    json.load(f)
            except (OSError, ValueError):
                abimes.append(nom)
    if abimes:
        return ERREUR, "fichier abîmé : " + ", ".join(abimes)
    return OK, "profils, mémoire et réglages lisibles"


VERIFICATIONS = (("Micro", _micro), ("Haut-parleur", _haut_parleur), ("Reconnaissance (Vosk)", _vosk),
                 ("Reconnaissance précise (Whisper)", _whisper), ("Claude", _claude), ("Connexion", _connexion),
                 ("Voix des profils", _voix), ("Disque", _disque), ("Fichiers de Jarvis", _fichiers))


def diagnostic():
    """[(nom, état, détail)] ; les vérifications tournent en parallèle (5 s au plus)."""
    resultats = {}

    def lancer(nom, fonction):
        try:
            resultats[nom] = fonction()
        except Exception as erreur:
            resultats[nom] = (INCONNU, str(erreur))
    fils = [threading.Thread(target=lancer, args=v, daemon=True) for v in VERIFICATIONS]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=6)
    return [(nom, *resultats.get(nom, (INCONNU, "trop long"))) for nom, _ in VERIFICATIONS]


def resume(liste=None):
    """La phrase que Jarvis dit après un diagnostic."""
    liste = liste or diagnostic()
    erreurs = [f"{n} : {d}" for n, e, d in liste if e == ERREUR]
    attentions = [f"{n} : {d}" for n, e, d in liste if e == ATTENTION]
    if not erreurs and not attentions:
        return "Tout va bien : micro, son, reconnaissance, Claude et connexion fonctionnent."
    morceaux = []
    if erreurs:
        morceaux.append("Problème. " + ". ".join(erreurs))
    if attentions:
        morceaux.append("À surveiller. " + ". ".join(attentions))
    return ". ".join(morceaux) + ". Le détail est dans l'onglet Santé des réglages."


_COMMANDE = re.compile(r"\b(?:fais|fait|lance|faire|lancer)\b.{0,15}\bdiagnostic\b|^\W*(?:jarvis\W+)?diagnostic\W*$|"
                       r"\b(?:vérifie|verifie|teste)\b.{0,10}\b(?:que tout|si tout)\b.{0,10}\b(?:fonctionne|marche|va bien)\b|"
                       r"\best-ce que tu (?:fonctionnes|marches) bien\b")


def commande(t):
    if _COMMANDE.search(t):
        return resume()
    return None
