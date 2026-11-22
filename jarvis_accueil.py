"""
JARVIS - premiers pas d'un nouvel utilisateur.

Après une première installation (l'installateur écrit accueil.json), Jarvis apprend à connaître la personne, une seule
question à la fois (une par lancement, après une réponse) : voix d'homme ou de femme, tutoiement ou
vouvoiement, sa ville (si elle n'est pas encore réglée), la couleur du réacteur, puis une petite visite
de ce qu'il sait faire. Elle répond simplement (« une voix de femme », « tutoie-moi », « Lyon »,
« en bleu »...) ; si elle parle d'autre chose, la question reviendra une autre fois.
Le fichier accueil.json (gardé sur ce PC) retient où on en est. Pour tout recommencer : supprime-le.
"""

import json
import os
import re
import time

import jarvis_config

FICHIER = jarvis_config.chemin("accueil.json")
MAX_FOIS = 2                       # une question sans réponse est posée deux fois au plus
ATTENTE_REPONSE = 180              # secondes pendant lesquelles une réponse à la question est attendue

QUESTIONS = {
    "voix": "Au fait, tu préfères que je parle avec une voix d'homme ou une voix de femme ?",
    "tutoiement": "Petite question : tu veux que je te tutoie, ou que je te vouvoie ?",
    "ville": "Dans quelle ville habites-tu ? Ça me sert pour la météo et les alertes météo.",
    "couleur": ("Pour mon réacteur, tu préfères quelles couleurs : Vice City, bleu, vert, rouge, violet "
                "ou orange ?"),
    "visite": ("Une dernière chose : tu peux me demander la météo, un minuteur, de la musique, une recherche, "
               "d'ouvrir une application, de lire tes mails ou de résumer une page. Dis Jarvis, aide, "
               "pour tout découvrir. Je suis content de t'avoir rencontré !"),
}
ORDRE = ("voix", "tutoiement", "ville", "couleur", "visite")

_pose = {"question": None, "moment": 0.0, "lancement": False}


def _lire():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(donnees):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False)
    except OSError:
        pass


def vouvoiement():
    return bool(_lire().get("vous"))


def consigne():
    """Ajoutée aux consignes de Claude."""
    return (" Vouvoie toujours " + jarvis_config.NOM + ", c'est son choix.") if vouvoiement() else ""


def _nouvel_utilisateur(donnees):
    # accueil.json contient {"nouveau": true} juste après une première installation (écrit par l'installateur)
    return bool(donnees.get("nouveau")) and not donnees.get("fini")


def _restantes(donnees):
    faites = set(donnees.get("faites", []))
    restantes = [q for q in ORDRE if q not in faites]
    if "ville" in restantes and os.path.exists(jarvis_config.chemin("ville.txt")):
        restantes.remove("ville")
    if "tutoiement" in restantes:
        try:                          # déjà choisi autrement (« tutoie-moi », « on peut se tutoyer »)
            import jarvis_personnalite
            if jarvis_personnalite.vouvoiement() is not None:
                restantes.remove("tutoiement")
        except Exception:
            pass
    # une question posée deux fois sans réponse est abandonnée : on ne harcèle pas
    deja = donnees.get("posees", {})
    restantes = [q for q in restantes if q == "visite" or deja.get(q, 0) < MAX_FOIS]
    return restantes


def question():
    """La question à ajouter après la réponse de Jarvis (une seule par lancement), ou « »."""
    if _pose["lancement"]:
        return ""
    donnees = _lire()
    if not _nouvel_utilisateur(donnees):
        return ""
    restantes = _restantes(donnees)
    if not restantes:
        donnees["fini"] = True
        _ecrire(donnees)
        return ""
    donnees.setdefault("posees", {})[restantes[0]] = donnees.get("posees", {}).get(restantes[0], 0) + 1
    _ecrire(donnees)
    _pose.update(question=restantes[0], moment=time.time(), lancement=True)
    if restantes[0] == "visite":                  # la visite n'attend pas de réponse
        _marquer("visite", fin=True)
        _pose["question"] = None
    return QUESTIONS[restantes[0]]


def _marquer(nom, fin=False, **reglages):
    donnees = _lire()
    donnees.setdefault("faites", [])
    if nom not in donnees["faites"]:
        donnees["faites"].append(nom)
    donnees.update(reglages)
    if fin:
        donnees["fini"] = True
    _ecrire(donnees)
    _pose["question"] = None


def reponse(t, brut, commande_ville):
    """Interprète la réponse à la question posée juste avant. Renvoie la phrase à dire, ou None."""
    nom = _pose["question"]
    if not nom or time.time() - _pose["moment"] > ATTENTE_REPONSE:
        return None
    t = t.replace("’", "'")
    # une vraie réponse est courte et n'est pas une autre demande (« tu peux mettre de la musique ? »)
    if len(t.split()) > 6 or re.search(r"\b(mets|met|ouvre|lance|ferme|joue|cherche|quelle|quel|comment|pourquoi|"
                                       r"combien|est-ce|peux|pourrais|météo|heure|minuteur|rappel|musique)\b", t):
        return None
    if nom == "voix":
        import jarvis_voix
        if re.search(r"\b(femme|f[ée]minine|fille|denise)\b", t):
            jarvis_voix.regler_voix("denise")
            _marquer("voix")
            return "D'accord, je garde cette voix de femme."
        if re.search(r"\b(homme|masculine|gar[çc]on|henri)\b", t):
            jarvis_voix.regler_voix("henri")
            _marquer("voix")
            return "D'accord, je garde cette voix d'homme."
    elif nom == "tutoiement":
        if re.search(r"\b(vouvoie|vouvoyer|vouvoiement|vous)\b", t):
            _marquer("tutoiement", vous=True)
            return "Entendu, je vous vouvoierai désormais."
        if re.search(r"\b(tutoie|tutoyer|tutoiement|tu|toi)\b", t):
            _marquer("tutoiement", vous=False)
            return "Parfait, on se tutoie."
    elif nom == "ville":
        lieu = re.sub(r"^\W*(?:j'habite|je vis|je suis|c'est|à|a|au|en|dans)\s+(?:à |a |au |en |dans )?", "", brut.strip(),
                      flags=re.I).strip(" .!?")
        if lieu and len(lieu.split()) <= 4:
            texte = commande_ville("ma ville est " + lieu)
            if texte and not texte.startswith("\x00"):
                _marquer("ville")
                return texte
            return None
    elif nom == "couleur":
        import jarvis_extras
        choix = jarvis_extras.choisir_couleur(t)
        if choix:
            _marquer("couleur")
            return f"Voilà, mon réacteur est maintenant en {'couleurs Vice City' if choix == 'vice city' else choix}."
    return None
