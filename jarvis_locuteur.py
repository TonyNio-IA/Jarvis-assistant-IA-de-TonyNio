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
_guide = {"profil": None, "vecteurs": [], "demarre": False}    # apprentissage guidé, phrase par phrase
TRAMES_GUIDE = 60          # une phrase répétée doit durer au moins ça pour compter
PHRASES_GUIDE = (                       # courtes et simples : un enfant doit pouvoir les répéter
    "Bonjour, je m'appelle {prenom}.",
    "Un, deux, trois, quatre, cinq.",
    "Le chat fait miaou.",
    "J'aime les frites.",
    "Il fait beau aujourd'hui.",
    "Je suis très content.",      # (pas « à demain » : trop proche de « arrête », qui coupe Jarvis)
)
RESSEMBLANCE_MIN = 0.55    # ce qui est entendu doit ressembler à la phrase demandée (lettre à lettre)...
MOTS_COMMUNS_MIN = 0.6     # ... ou en reprendre la plupart des mots (« qui suis-je » ≠ « je suis très content »)
_verrou = threading.RLock()
dernier_identifie = None   # profil reconnu à la voix pour la dernière demande (None = inconnu)
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
    if not _apprentissage["reste"] and _guide["profil"] is None and len(_charger()) < 2:
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


# ----- Échantillons pris en passant : quand une voix est reconnue sans aucun doute, Jarvis garde de temps en
# temps cette demande pour affiner l'empreinte (voix du matin, enrhumée, plus loin du micro...). Ils sont rangés
# à part (voix_auto.json) : les phrases apprises restent la base, et « oublie ma voix » efface tout.
AUTO_DISTANCE_MAX = 0.45   # seulement quand la voix est très proche de son empreinte...
AUTO_MARGE_MIN = 0.25      # ... et très loin de toutes les autres
AUTO_INTERVALLE = 600      # au plus un échantillon toutes les 10 minutes par profil
AUTO_NB_GARDES = 14        # les plus récents sont gardés
_auto = None               # {identifiant: [vecteurs]}
_auto_dernier = {}


def _fichier_auto(ident):
    return os.path.join(jarvis_profils.DOSSIER, ident or "_principal", "voix_auto.json")


def _charger_auto():
    global _auto
    with _verrou:
        if _auto is None:
            _auto = {}
            for ident in [""] + list(jarvis_profils._lire()):
                try:
                    with open(_fichier_auto(ident), encoding="utf-8") as f:
                        _auto[ident] = [np.array(v, dtype=float) for v in json.load(f)]
                except (OSError, ValueError):
                    pass
        return _auto


def _echantillon(ident, vecteur):
    """Garde cet échantillon de la voix (au plus un par heure et par profil)."""
    if time.time() - _auto_dernier.get(ident, 0) < AUTO_INTERVALLE:
        return
    _auto_dernier[ident] = time.time()
    auto = _charger_auto()
    with _verrou:
        liste = auto.setdefault(ident, [])
        liste.append(vecteur)
        del liste[:-AUTO_NB_GARDES]
        try:
            os.makedirs(os.path.dirname(_fichier_auto(ident)), exist_ok=True)
            with open(_fichier_auto(ident), "w", encoding="utf-8") as f:
                json.dump([[round(float(x), 5) for x in v] for v in liste], f)
        except OSError as erreur:
            print("Échantillon de voix non enregistré :", erreur)
    print(f"(Voix : nouvel échantillon pour {ident or 'principal'}, {len(liste)} en tout.)")


def oublier_echantillons(ident):
    auto = _charger_auto()
    with _verrou:
        auto.pop(ident or "", None)
    try:
        os.remove(_fichier_auto(ident))
    except OSError:
        pass


def identifier(vecteur):
    """L'identifiant du profil reconnu ("" = profil principal), ou None en cas de doute."""
    profils = jarvis_profils._lire()
    auto = _charger_auto()
    empreintes = {i: list(v) + list(auto.get(i, [])) for i, v in _charger().items()
                  if len(v) >= 3 and (i == "" or i in profils)}
    if len(empreintes) < 2:
        return None
    distances = sorted((1 - float(vecteur @ _centre(v)), i) for i, v in empreintes.items())
    (d1, ident), (d2, _) = distances[0], distances[1]
    print("(Voix : %s)" % ", ".join("%s %.2f" % (i or "principal", d) for d, i in distances))
    if d1 <= DISTANCE_MAX and d2 - d1 >= MARGE_MIN:
        if d1 <= AUTO_DISTANCE_MAX and d2 - d1 >= AUTO_MARGE_MIN:
            _echantillon(ident, vecteur)
        return ident
    return None


def appliquer():
    """À appeler au début du traitement d'une demande. Apprend la voix si un apprentissage est en cours,
    sinon passe sur le profil de la personne reconnue. Renvoie une phrase à dire avant la réponse (ou « »)."""
    global dernier_identifie
    dernier_identifie = None
    resultat = _resultat()
    if not resultat:
        return ""
    vecteur, trames = resultat
    if jarvis_profils.choix_recent():
        return ""                     # la personne vient de dire elle-même qui elle est : on ne la contredit pas
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
    dernier_identifie = ident
    try:
        import jarvis_foyer
        if jarvis_foyer.quiz_actif():
            return ""                 # pendant le quiz, la voix dit qui répond, sans changer de profil
    except Exception:
        pass
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
    empreintes = _charger()
    if len(empreintes.get(ident or "") or []) < 3:
        return
    # Sécurité : si cette voix ressemble nettement plus à quelqu'un d'autre, elle n'est pas ajoutée
    # (jamais la voix d'une personne dans l'empreinte d'une autre).
    try:
        distances = {i: 1 - float(vecteur @ _centre(v)) for i, v in empreintes.items() if v}
        cible = distances.get(ident or "")
        if cible is None or cible > DISTANCE_MAX:
            print("Empreinte non complétée : voix trop différente du profil.")
            return
        autre = min((d for i, d in distances.items() if i != (ident or "")), default=None)
        if autre is not None and autre < cible:
            print("Empreinte non complétée : voix plus proche d'un autre profil.")
            return
    except Exception as erreur:
        print("Empreinte de voix :", erreur)
        return
    ajouter(ident or "", vecteur)


def oublier_confirmable():
    _confirmable["vecteur"] = None


# ---------- Apprentissage guidé ----------

def guide_demande():
    """Vrai juste après « apprends ma voix » : l'apprentissage guidé doit commencer."""
    if _guide["profil"] is not None and not _guide["demarre"]:
        _guide["demarre"] = True
        return True
    return False


def phrases_guide(prenom):
    return [p.format(prenom=prenom or "Jarvis") for p in PHRASES_GUIDE]


def _mots(texte):
    texte = texte.lower().replace("’", "'")
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            texte = texte.replace(lettre, b)
    chiffres = {"1": "un", "2": "deux", "3": "trois", "4": "quatre", "5": "cinq", "6": "six", "7": "sept",
                "8": "huit", "9": "neuf", "10": "dix"}
    return [chiffres.get(m, m) for m in re.findall(r"[a-z0-9]+", texte)]


def ressemble(entendu, phrase):
    """Vrai si ce qui a été entendu ressemble à la phrase demandée (pas une autre demande).
    Quand deux retranscriptions sont données (« X » (autre retranscription possible … : « Y »)), chacune compte."""
    morceaux = re.findall(r"«\s*(.+?)\s*»", entendu or "")
    if len(morceaux) >= 2:
        return any(ressemble(m, phrase) for m in morceaux)
    import difflib
    a, b = " ".join(_mots(entendu)), " ".join(_mots(phrase))
    if not a:
        return False
    communs = len(set(_mots(entendu)) & set(_mots(phrase))) / max(1, len(set(_mots(phrase))))
    return communs >= MOTS_COMMUNS_MIN or difflib.SequenceMatcher(None, a, b).ratio() >= RESSEMBLANCE_MIN


def apprendre_phrase(entendu="", phrase=""):
    """Après une phrase répétée : garde son empreinte si c'est bien la phrase demandée et qu'elle est assez
    longue. Renvoie True si elle compte."""
    resultat = _resultat(delai=4.0)
    if not resultat:
        return False
    if phrase and not ressemble(entendu, phrase):
        return False
    vecteur, trames = resultat
    if trames < TRAMES_GUIDE:
        return False
    _guide["vecteurs"].append(vecteur)
    return True


def annuler_guide():
    _guide.update(profil=None, vecteurs=[], demarre=False)


def terminer_guide(prenom=""):
    """Fin de l'apprentissage guidé : remplace l'empreinte du profil si au moins 4 phrases ont été retenues."""
    ident, vecteurs = _guide["profil"], list(_guide["vecteurs"])
    annuler_guide()
    if ident is None:
        return ""
    qui = f" {prenom}" if prenom else ""
    if len(vecteurs) < 4:
        return (f"Je n'ai pas assez bien entendu{qui}, on réessaiera un peu plus tard, dans un endroit calme. "
                "Dis : Jarvis, apprends ma voix.")
    with _verrou:
        _charger()[ident] = vecteurs[-NB_GARDEES:]
    _enregistrer(ident)
    oublier_echantillons(ident)          # une voix réapprise repart des nouvelles phrases
    return f"Bravo{qui} ! C'est bon, je connais ta voix maintenant."


# ---------- À la voix ----------

def commande(t):
    t = t.replace("’", "'").lower()
    # « apprends ma voix » est souvent mal entendu : « apprends m'envoie », « apparemment voie »
    t = re.sub(r"\b(?:apprends?|apprendre|apparemment)\W+(?:ma |la |m'|à |a |ta )?(?:voix|voie|voit|vois|envoie)\b", "apprends ma voix", t)
    # … ou « attends la voix », « apprend à voix » quand c'est toute la demande
    t = re.sub(r"^\W*(?:jarvis\W+)?(?:attends?|attend|entends?) (?:ma|la|à) (?:voix|voie)\W*$", "apprends ma voix", t)
    if not re.search(r"\b(ma|la|sa) voix\b", t):
        return None
    actif = jarvis_profils.actif() or ""
    prenom = jarvis_profils.prenom_actif()
    if re.search(r"\b(apprends|apprend|apprendre|enregistre|m[ée]morise|retiens)\b", t):
        if not disponible():
            return ("Il me manque le petit modèle des empreintes de voix. C'est expliqué sur la page du projet, "
                    "à la rubrique Profils.")
        # Apprentissage guidé : Jarvis dit une phrase, attend qu'on la répète, puis passe à la suivante.
        # L'ancienne empreinte n'est remplacée qu'à la fin, si assez de phrases ont été bien entendues.
        _guide.update(profil=actif, vecteurs=[], demarre=False)
        _apprentissage.update(profil=None, reste=0)
        qui = f" {prenom}" if prenom else ""
        return (f"D'accord{qui} ! Je vais te dire {len(PHRASES_GUIDE)} phrases, une par une. Après le bip, "
                "répète chaque phrase, tranquillement. On commence.")
    if re.search(r"\b(oublie|efface|supprime)\b", t):
        annuler_guide()
        with _verrou:
            _charger().pop(actif, None)
        _enregistrer(actif)
        oublier_echantillons(actif)
        _apprentissage.update(profil=None, reste=0)
        return "C'est fait, j'ai oublié ta voix."
    if re.search(r"\b(reconnais|connais|sais)\b", t):
        nombre = len(_charger().get(actif) or [])
        if nombre >= 3:
            return f"Oui, je connais la voix de ce profil{(' : ' + prenom) if prenom else ''}."
        return "Pas encore. Dis : Jarvis, apprends ma voix."
    return None
