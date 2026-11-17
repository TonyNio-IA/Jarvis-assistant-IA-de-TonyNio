"""
JARVIS - reconnaître qui parle, pour passer tout seul sur le bon profil.

Chaque profil (voir jarvis_profils.py) peut avoir une empreinte de voix. Quand au moins deux profils en ont
une, Jarvis compare la voix de chaque demande aux empreintes et passe sur le profil de la personne reconnue.
S'il hésite (demande trop courte, voix entre deux empreintes, voix inconnue), il ne change rien : on peut
toujours dire « Jarvis, c'est Marie ». Tout se passe sur ce PC ; les empreintes sont des listes de nombres
rangées dans le dossier profils/ (jamais publié).

  « Jarvis, apprends ma voix »     sur ton profil : Jarvis apprend ta voix pendant tes 6 demandes suivantes
  « Jarvis, oublie ma voix »       efface l'empreinte de ton profil
  « Jarvis, reconnais-tu ma voix ? »

Ce n'est pas une sécurité : deux voix proches peuvent être confondues, et une voix s'imite.
Il faut le petit modèle « vosk-model-spk-0.4 » (13 Mo, alphacephei.com/vosk/models) dans le dossier de Jarvis ;
sans lui, cette fonction est simplement absente.
"""

import json
import os
import re
import threading
import time

import numpy as np

import jarvis_config
import jarvis_profils

DOSSIER_MODELE = jarvis_config.chemin("vosk-model-spk-0.4")
TRAMES_MIN = 90            # en dessous (moins d'une seconde de voix environ), on ne conclut rien
DISTANCE_MAX = 0.66        # distance maximale à l'empreinte pour reconnaître quelqu'un (0 = identique)
MARGE_MIN = 0.15           # écart minimal avec l'empreinte suivante : sinon, c'est une hésitation
NB_APPRENTISSAGE = 6       # demandes écoutées pour apprendre une voix
TRAMES_CONFIRMEES = 45     # assez pour une demande où la personne dit elle-même qui elle est
_confirmable = {}
NB_GARDEES = 20            # empreintes gardées par profil

_modele = None             # le modèle de reconnaissance vocale de Jarvis (donné par jarvis_claude)
_voix = None               # le modèle d'empreintes de voix
_dernier = {"fil": None, "resultat": None}
_apprentissage = {"profil": None, "reste": 0}
_verrou = threading.RLock()
_empreintes = None         # {identifiant ("" = profil principal): [vecteurs]}


def preparer(modele):
    """Charge le modèle d'empreintes en arrière-plan (s'il est installé)."""
    global _modele
    _modele = modele
    if not os.path.isdir(DOSSIER_MODELE):
        return

    def charger():
        global _voix
        try:
            from vosk import SpkModel
            _voix = SpkModel(DOSSIER_MODELE)
        except Exception as erreur:
            print("Empreintes de voix indisponibles :", erreur)
    threading.Thread(target=charger, daemon=True).start()


def disponible():
    return _voix is not None and _modele is not None


def _vecteur(octets, texte=""):
    """L'empreinte de la voix de cet enregistrement. Avec le texte déjà entendu, le calcul est dix fois plus
    rapide (0,2 s) : Vosk n'a qu'à retrouver ces mots au lieu de tout reconnaître de nouveau."""
    from vosk import KaldiRecognizer
    if texte.strip():
        reconnaisseur = KaldiRecognizer(_modele, 16000, json.dumps([texte.strip().lower(), "[unk]"], ensure_ascii=False))
        reconnaisseur.SetSpkModel(_voix)
    else:
        reconnaisseur = KaldiRecognizer(_modele, 16000, _voix)
    reconnaisseur.AcceptWaveform(octets)
    resultat = json.loads(reconnaisseur.FinalResult())
    if "spk" not in resultat:
        return None
    vecteur = np.array(resultat["spk"], dtype=float)
    norme = np.linalg.norm(vecteur)
    return (vecteur / norme, int(resultat.get("spk_frames", 0))) if norme else None


def analyser(octets, texte=""):
    """Lance le calcul de l'empreinte de cette demande (en parallèle de la retranscription)."""
    if not disponible() or not octets:
        return
    if not _apprentissage["reste"] and len(_charger()) < 2:
        return                                   # rien à comparer : pas de calcul inutile
    boite = {"fil": None, "resultat": None}

    def travail():
        try:
            boite["resultat"] = _vecteur(bytes(octets), texte)
        except Exception as erreur:
            print("Empreinte de voix :", erreur)
    boite["fil"] = threading.Thread(target=travail, daemon=True)
    boite["fil"].start()
    _dernier.update(boite)
    _dernier["boite"] = boite


def _resultat(delai=0.8):
    boite = _dernier.pop("boite", None)
    if not boite:
        return None
    boite["fil"].join(delai)
    return boite["resultat"]


# ---------- Empreintes rangées par profil ----------

def _fichier(ident):
    return os.path.join(jarvis_profils.DOSSIER, ident or "_principal", "voix.json")


def _charger():
    global _empreintes
    with _verrou:
        if _empreintes is None:
            _empreintes = {}
            for ident in [""] + list(jarvis_profils._lire()):
                try:
                    with open(_fichier(ident), encoding="utf-8") as f:
                        vecteurs = [np.array(v, dtype=float) for v in json.load(f)]
                    if vecteurs:
                        _empreintes[ident] = vecteurs
                except (OSError, ValueError):
                    pass
        return _empreintes


def _enregistrer(ident):
    vecteurs = _charger().get(ident) or []
    chemin = _fichier(ident)
    try:
        if not vecteurs:
            if os.path.exists(chemin):
                os.remove(chemin)
            return
        os.makedirs(os.path.dirname(chemin), exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump([[round(float(x), 5) for x in v] for v in vecteurs], f)
    except OSError as erreur:
        print("Empreinte de voix non enregistrée :", erreur)


def ajouter(ident, vecteur):
    empreintes = _charger()
    with _verrou:
        empreintes.setdefault(ident or "", []).append(vecteur)
        del empreintes[ident or ""][:-NB_GARDEES]
    _enregistrer(ident or "")


def _centre(vecteurs):
    centre = np.mean(vecteurs, axis=0)
    return centre / np.linalg.norm(centre)


def identifier(vecteur):
    """L'identifiant du profil reconnu ("" = profil principal), ou None en cas de doute."""
    empreintes = {i: v for i, v in _charger().items() if len(v) >= 3 and (i == "" or i in jarvis_profils._lire())}
    if len(empreintes) < 2:
        return None
    distances = sorted((1 - float(vecteur @ _centre(v)), i) for i, v in empreintes.items())
    (d1, ident), (d2, _) = distances[0], distances[1]
    print("(Voix : %s)" % ", ".join("%s %.2f" % (i or "principal", d) for d, i in distances))
    if d1 <= DISTANCE_MAX and d2 - d1 >= MARGE_MIN:
        return ident
    return None


def appliquer():
    """À appeler au début du traitement d'une demande. Apprend la voix si un apprentissage est en cours,
    sinon passe sur le profil de la personne reconnue. Renvoie une phrase à dire avant la réponse (ou « »)."""
    resultat = _resultat()
    if not resultat:
        return ""
    vecteur, trames = resultat
    _confirmable.update(vecteur=vecteur if trames >= TRAMES_CONFIRMEES else None, moment=time.time())
    if trames < TRAMES_MIN:
        return ""
    actif = jarvis_profils.actif() or ""
    if _apprentissage["reste"] and _apprentissage["profil"] == actif:
        ajouter(actif, vecteur)
        _apprentissage["reste"] -= 1
        if not _apprentissage["reste"]:
            return "C'est bon, je connais ta voix maintenant. "
        return ""
    ident = identifier(vecteur)
    if ident is None or ident == actif:
        return ""
    prenom = jarvis_profils.activer(ident)
    return f"Bonjour {prenom}. " if prenom else ""


def confirmer(ident):
    """La personne vient de dire elle-même qui elle est (« Jarvis, c'est Marie ») : si ce profil a déjà une
    empreinte, la voix de cette demande y est ajoutée. Jarvis la reconnaîtra mieux d'un jour à l'autre."""
    vecteur = _confirmable.get("vecteur")
    if vecteur is None or time.time() - _confirmable.get("moment", 0) > 20:
        return
    _confirmable["vecteur"] = None
    if len(_charger().get(ident or "") or []) >= 3:
        ajouter(ident or "", vecteur)


# ---------- À la voix ----------

def commande(t):
    t = t.replace("’", "'").lower()
    if not re.search(r"\b(ma|la|sa) voix\b", t):
        return None
    actif = jarvis_profils.actif() or ""
    prenom = jarvis_profils.prenom_actif()
    if re.search(r"\b(apprends|apprend|apprendre|enregistre|m[ée]morise|retiens)\b", t):
        if not disponible():
            return ("Il me manque le petit modèle des empreintes de voix. C'est expliqué sur la page du projet, "
                    "à la rubrique Profils.")
        with _verrou:
            _charger().pop(actif, None)
        _apprentissage.update(profil=actif, reste=NB_APPRENTISSAGE)
        qui = f", {prenom}" if prenom else ""
        return (f"D'accord{qui} : j'apprends ta voix pendant tes {NB_APPRENTISSAGE} prochaines demandes. "
                "Parle-moi normalement, avec des phrases complètes.")
    if re.search(r"\b(oublie|efface|supprime)\b", t):
        with _verrou:
            _charger().pop(actif, None)
        _enregistrer(actif)
        _apprentissage.update(profil=None, reste=0)
        return "C'est fait, j'ai oublié ta voix."
    if re.search(r"\b(reconnais|connais|sais)\b", t):
        nombre = len(_charger().get(actif) or [])
        if nombre >= 3:
            return f"Oui, je connais la voix de ce profil{(' : ' + prenom) if prenom else ''}."
        return "Pas encore. Dis : Jarvis, apprends ma voix."
    return None
