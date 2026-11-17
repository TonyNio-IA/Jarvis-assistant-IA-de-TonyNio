"""
JARVIS - mode enfant.

« Jarvis, active le mode enfant » / « désactive le mode enfant » / « est-ce que le mode enfant est activé ? »

Quand il est actif, tout ce qui passe par Jarvis est adapté à un enfant :
  - les vidéos et la musique s'ouvrent sur YouTube Kids (« mets une vidéo de dinosaures ») ;
  - les recherches Google passent par le filtre SafeSearch ; les sites d'achat ne sont pas ouverts ;
  - Claude répond avec des mots simples, gentiment, sans contenu qui fait peur ou qui n'est pas de son âge,
    et ne fait aucune action sur le PC ;
  - quiz et devinettes : une question à la fois, Jarvis attend la réponse ;
  - longues histoires (environ 10 minutes), avec la suite le lendemain (« raconte la suite »).

Limite : Jarvis ne contrôle que ce qu'on lui demande. Si l'enfant tape lui-même une adresse dans le
navigateur, Jarvis ne peut pas l'en empêcher (c'est le rôle du contrôle parental de Windows).

Le choix (actif ou non) et l'histoire en cours restent sur ce PC, dans enfant.json.
"""

import json
import os
import re
import threading
import time
import urllib.parse

import jarvis_config

FICHIER = jarvis_config.chemin("enfant.json")
_verrou = threading.Lock()

YOUTUBE_KIDS = "https://www.youtubekids.com"
RECHERCHE_YOUTUBE_KIDS = "https://www.youtubekids.com/search?q={}"
RECHERCHE_GOOGLE_PROTEGEE = "https://www.google.com/search?safe=active&q={}"
IMAGES_GOOGLE_PROTEGEES = "https://www.google.com/search?safe=active&tbm=isch&q={}"
SITES_INTERDITS = r"amazon|le ?bon ?coin|leboncoin|cdiscount|vinted|ebay|aliexpress|temu|shein|fnac"


def _lire():
    try:
        with open(FICHIER, encoding="utf-8-sig") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(donnees):
    try:
        with open(FICHIER, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
    except OSError as erreur:
        print("Mode enfant non enregistré :", erreur)


def actif():
    with _verrou:
        return bool(_lire().get("actif"))


def _regler(valeur):
    with _verrou:
        donnees = _lire()
        donnees["actif"] = bool(valeur)
        _ecrire(donnees)


def _ouvrir(adresse):
    os.startfile(adresse)


# ---------- Activer, désactiver ----------

_MODE = re.compile(r"\bmode (?:enfants?|enfance|en fan|enfin|en face|gamins?|kids?|junior)\b")


def commande(t):
    """Active, désactive ou donne l'état du mode enfant."""
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    if not _MODE.search(t):
        return None
    if re.search(r"\b(?:est-ce que|es-tu|tu es|t'es|c'est)\b", t) and not re.search(
            r"\b(?:active|désactive|desactive|mets|passe|enlève|enleve|coupe|arrête|arrete|quitte|sors)\b", t):
        return "Le mode enfant est activé." if actif() else "Le mode enfant n'est pas activé."
    if re.search(r"\b(?:désactive|desactive|enlève|enleve|retire|arrête|arrete|coupe|quitte|sors du|stop|fin du)\b", t):
        _regler(False)
        return "Mode enfant désactivé."
    if re.search(r"\b(?:active|mets|passe|lance|démarre|demarre)\b|\ben mode\b", t):
        _regler(True)
        return ("Mode enfant activé. Les vidéos passent par YouTube Kids, les recherches sont filtrées, "
                "et je réponds comme à un enfant. Je peux aussi faire un quiz, des devinettes "
                "ou raconter une longue histoire.")
    return "Tu veux que j'active ou que je désactive le mode enfant ?"


# ---------- Vidéos, musique, recherches : version enfant ----------

def commande_web(t):
    """En mode enfant, remplace YouTube par YouTube Kids, filtre Google et refuse les sites d'achat.
    Renvoie la réponse à dire, ou None si la demande ne concerne pas le web."""
    if not actif():
        return None
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    if re.search(r"\b(?:" + SITES_INTERDITS + r")\b", t):
        return "En mode enfant, je n'ouvre pas les sites d'achat."
    # « ouvre YouTube »
    if re.fullmatch(r"(?:ouvre|lance|va sur|mets)(?:-moi)? (?:le site )?youtube(?: kids)?", t):
        _ouvrir(YOUTUBE_KIDS)
        return "J'ouvre YouTube Kids."
    # « cherche des dinosaures sur Google », « cherche des images de chats »
    m = re.match(r"(?:cherche|recherche|trouve|regarde)(?:-moi)? (?P<quoi>.+?) (?:sur|dans|avec) "
                 r"(?:google images|les images|images)$", t)
    if m:
        _ouvrir(IMAGES_GOOGLE_PROTEGEES.format(urllib.parse.quote(_nettoyer(m.group("quoi")))))
        return f"Je cherche des images de {_nettoyer(m.group('quoi'))}, avec le filtre pour les enfants."
    m = re.match(r"(?:cherche|recherche|trouve|regarde)(?:-moi)? (?P<quoi>.+?) (?:sur|dans|avec) "
                 r"(?:google|internet|le web|le net)$", t)
    if m:
        _ouvrir(RECHERCHE_GOOGLE_PROTEGEE.format(urllib.parse.quote(_nettoyer(m.group("quoi")))))
        return f"Je cherche {_nettoyer(m.group('quoi'))} sur Google, avec le filtre pour les enfants."
    # « lance la deuxième vidéo » : un clic dans la page ouverte, pas une nouvelle recherche
    if re.search(r"\b(?:premi[eè]re?|1[eè]?re?|deuxi[eè]me|second[e]?|troisi[eè]me|quatri[eè]me|cinqui[eè]me|"
                 r"\d+e|\d+ème|dernière|derniere) (?:vidéo|video)\b", t):
        return None
    # Vidéos et musique : « mets une vidéo de dinosaures », « cherche Peppa Pig sur YouTube »,
    # « mets la musique de la Reine des neiges »
    video = re.search(r"\b(?:vidéos?|video|youtube|dessins? animés?|musiques?|chansons?|clips?|épisodes?)\b", t)
    verbes = (r"(?:mets|met|mais|mes|joue|lance|passe|cherche|recherche|trouve|montre|ouvre|ouvrez|regarde|"
              r"je veux(?: voir| regarder)?|j'aimerais(?: voir| regarder)?|je voudrais(?: voir| regarder)?|"
              r"tu peux(?: me)? (?:mettre|trouver|montrer|ouvrir))(?:-moi| moi)?\b")
    action = re.match(verbes, t) or re.match(r"(?:une|des|la|les|un) (?:vidéos?|video|dessins? animés?|chansons?|"
                                              r"musiques?|épisodes?)\b", t)   # « une vidéo de dinosaures » (suite)
    if video and action:
        quoi = re.sub("^" + verbes, "", t)
        quoi = re.sub(r"\b(?:sur youtube(?: kids)?|youtube(?: kids)?|s'il te plaît|stp)\b", " ", quoi)
        quoi = re.sub(r"^\s*(?:moi\s+)?(?:une |des |la |les |le |un )?(?:vidéos?|video|musiques?|chansons?|clips?|"
                      r"épisodes?)?\s*(?:de la |de l'|des |du |de |d'|sur les |sur le |sur la |sur )?", "", quoi)
        quoi = _nettoyer(quoi)
        if not quoi:
            _ouvrir(YOUTUBE_KIDS)
            return "J'ouvre YouTube Kids."
        _ouvrir(RECHERCHE_YOUTUBE_KIDS.format(urllib.parse.quote(quoi)))
        return f"Je cherche {quoi} sur YouTube Kids."
    return None


def _nettoyer(quoi):
    quoi = " ".join(quoi.split())
    quoi = re.sub(r"^(?:sur |de |à propos de |avec )?(?:des |de la |du |de l'|les |le |la |l'|un |une )?", "", quoi)
    return " ".join(quoi.split()).strip(" .,!?")


# ---------- Ce que Claude reçoit en mode enfant ----------

LONGUEUR_HISTOIRE = 1500        # mots, environ 10 minutes de lecture à voix haute
_HISTOIRE = re.compile(r"\b(?:histoire|conte|la suite|raconte)\b")
_BALISE = re.compile(r"^\s*HISTOIRE\s*:\s*(.+)$", re.M)


def note(demande):
    """Consignes ajoutées devant la demande quand le mode enfant est actif (sinon « »)."""
    if not actif():
        return ""
    texte = ("(Mode enfant : tu parles à un enfant. Réponds avec des mots simples, gentiment et avec "
             "enthousiasme, sans rien qui fasse peur, de violent ou qui ne soit pas de son âge. "
             "Ne fais aucune action sur le PC et n'ouvre aucun site ; pour une vidéo, dis-lui de "
             "demander « mets une vidéo de… ». Pour un quiz ou des devinettes : pose une seule question "
             "à la fois, termine par la question, puis attends sa réponse ; dis-lui gentiment si c'est "
             "juste ou non, donne la bonne réponse, compte les points et pose la suivante, jusqu'à ce "
             "qu'il veuille arrêter. ")
    if _HISTOIRE.search(demande.lower()):
        texte += (f"Pour une histoire, oublie la limite de trois phrases : raconte une longue histoire "
                  f"d'au moins {LONGUEUR_HISTOIRE} mots (dix minutes à voix haute, jamais moins : prends le temps "
                  f"des descriptions, des dialogues et de plusieurs péripéties), avec un titre dit au "
                  f"début, des personnages attachants, et une fin de chapitre qui donne envie de connaître "
                  f"la suite. Écris seulement le texte à lire, sans titre de section ni mise en forme. "
                  f"Termine toujours par une ligne « HISTOIRE: » suivie d'un résumé de toute l'histoire "
                  f"jusqu'ici (personnages, lieux, ce qui s'est passé) en quatre phrases au plus : "
                  f"cette ligne n'est pas lue, elle sert à raconter la suite plus tard. ")
        with _verrou:
            histoire = _lire().get("histoire")
        if histoire and re.search(r"\bsuite\b|\bcontinue\b|\bdernier chapitre\b|\bchapitre suivant\b",
                                  demande.lower()):
            texte += ("Il demande la suite de l'histoire déjà commencée, dont voici le résumé : "
                      + histoire + " Raconte le chapitre suivant, avec les mêmes personnages. ")
    return texte + ")\n"


def appliquer(reponse):
    """Retire la ligne « HISTOIRE: … » de la réponse de Claude et garde le résumé pour la suite."""
    resumes = _BALISE.findall(reponse or "")
    if not resumes:
        return reponse
    with _verrou:
        donnees = _lire()
        donnees["histoire"] = resumes[-1].strip()[:1500]
        donnees["histoire_le"] = time.strftime("%d/%m/%Y %H:%M")
        _ecrire(donnees)
    return _BALISE.sub("", reponse).strip()


def histoire_demandee(demande):
    return actif() and bool(_HISTOIRE.search(demande.lower()))
