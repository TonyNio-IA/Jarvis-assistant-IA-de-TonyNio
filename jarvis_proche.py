# -*- coding: utf-8 -*-
"""« Tu voulais dire : monte le son ? » : quand une phrase courte n'est comprise par aucune commande mais
ressemble de TRÈS près à une commande connue (un mot mal entendu par Whisper), Jarvis la propose, et ne la fait
qu'après un « oui ». Règles pour ne jamais faire de fausse proposition :
- seulement des phrases courtes (2 à 7 mots), jamais une question ouverte ;
- une ressemblance très forte (lettres ET mots), et nettement meilleure que la deuxième commande la plus proche ;
- seulement des commandes sans danger (rien qui éteint, efface ou envoie quelque chose)."""
import difflib
import re
import unicodedata

# Commandes sûres, dites telles qu'un utilisateur les dirait. Chacune est vérifiée dans le bac à sable
# (tests\essai_proche_166.py) : Jarvis doit vraiment la traiter seul.
COMMANDES = [
    "monte le son", "baisse le son", "coupe le son", "remets le son", "mets le son à fond", "parle plus fort",
    "parle moins fort", "parle plus vite", "parle moins vite", "mets en pause", "reprends la lecture",
    "musique suivante", "musique précédente", "quelle heure est-il", "quel temps fait-il", "donne-moi la météo",
    "quelle est la date", "mets-toi à jour", "ouvre les réglages", "règle ton micro", "coupe le micro",
    "active le wifi", "désactive le wifi", "zoom avant", "zoom arrière", "fais une capture d'écran",
    "réduis la fenêtre", "agrandis la fenêtre", "ferme la fenêtre", "ouvre l'explorateur de fichiers",
    "ouvre le panneau de configuration", "ouvre le navigateur", "vide la corbeille", "verrouille l'ordinateur",
    "lis mes mails", "quels sont mes rappels", "qu'est-ce que tu sais faire", "active le bluetooth",
    "désactive le bluetooth", "augmente la luminosité", "baisse la luminosité", "mets le mode nuit",
]

_QUESTION = re.compile(r"^(?:qui|que|quoi|qu'|quel(?:le)?s? |comment|pourquoi|combien|ou |est ce|c'est quoi|dis moi)")
_DEBUT = re.compile(r"^(?:jarvis |s'il te plait |stp |euh |alors |bon |hey |ok )+")


def _norme(texte):
    t = unicodedata.normalize("NFD", (texte or "").lower().replace("’", "'"))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9' ]+", " ", t.replace("-", " "))
    t = re.sub(r"\s+", " ", t).strip()
    t = _DEBUT.sub("", t)
    return re.sub(r" (?:s'il te plait|stp|jarvis)$", "", t).strip()


_NORMES = [(_norme(c), c) for c in COMMANDES]


def _score(a, b):
    lettres = difflib.SequenceMatcher(None, a, b).ratio()
    mots = difflib.SequenceMatcher(None, a.split(), b.split()).ratio()
    return 0.7 * lettres + 0.3 * mots


def plus_proche(phrase):
    """La commande connue la plus proche, ou None si rien n'est assez sûr."""
    s = _norme(phrase)
    mots = s.split()
    if not 2 <= len(mots) <= 7:
        return None
    scores = sorted(((_score(s, n), n, c) for n, c in _NORMES), reverse=True)
    meilleur, n, commande = scores[0]
    second = scores[1][0]
    if s == n:
        return None                       # déjà dite telle quelle : si elle n'a pas marché, la reproposer n'aide pas
    if _QUESTION.match(s) and not _QUESTION.match(n):
        return None                       # une question ne devient jamais un ordre
    if abs(len(mots) - len(n.split())) > 1:
        return None
    lettres = difflib.SequenceMatcher(None, s, n).ratio()
    # au moins le premier mot (le verbe, le plus souvent) doit se ressembler
    if difflib.SequenceMatcher(None, mots[0], n.split()[0]).ratio() < 0.6:
        return None
    if meilleur >= 0.80 and lettres >= 0.82 and meilleur - second >= 0.08:
        return commande
    return None


def proposer(textes, demander_confirmation, executer):
    """Propose la commande la plus proche ; « oui » la fait. Renvoie la phrase à dire, ou None."""
    for brut in textes:
        if not brut:
            continue
        commande = plus_proche(brut)
        if commande:
            demander_confirmation(lambda c=commande: executer([c]) or "Je n'ai pas réussi à le faire, redis-le-moi autrement.")
            return f"Tu voulais dire : « {commande} » ? Dis oui pour que je le fasse."
    return None
