"""
JARVIS - réglages personnels.

Tout ce qui dépend de la personne qui utilise Jarvis est dans le fichier config.json, placé dans
le dossier de Jarvis. Ce fichier reste sur ton PC (il n'est jamais envoyé sur GitHub).
Pour le créer : copie config.exemple.json, renomme la copie en config.json et remplis-la.
Sans config.json, Jarvis fonctionne quand même, avec des réglages neutres.

  prenom         : comment Jarvis t'appelle (« Bonjour Alex »)
  sujets         : les rubriques de ton point du jour, après la météo et les actualités
  site           : un site à consulter pour le point du jour (facultatif)
  vocabulaire    : les noms propres que tu prononces souvent, pour qu'ils soient mieux compris
  mode_nuit      : les heures du mode nuit, où Jarvis répond par écrit sans parler (les rappels sonnent
                   quand même) : {"debut": 22, "fin": 7} par défaut ; false pour ne jamais l'activer
"""

import json
import os

DOSSIER = os.path.dirname(os.path.abspath(__file__))


def chemin(*morceaux):
    """Chemin d'un fichier ou d'un dossier de Jarvis (à côté de ses programmes)."""
    return os.path.join(DOSSIER, *morceaux)


try:
    with open(chemin("config.json"), encoding="utf-8-sig") as _f:
        _lu = json.load(_f)
except (OSError, ValueError) as _erreur:
    if os.path.exists(chemin("config.json")):
        print("config.json illisible (", _erreur, ") : réglages neutres utilisés.")
    _lu = {}

PRENOM = str(_lu.get("prenom") or "").strip()
NOM = PRENOM or "l'utilisateur"                    # dans les consignes données à Claude
SALUT = (" " + PRENOM) if PRENOM else ""           # « Bonjour Alex. » ou « Bonjour. »
SUJETS = [str(s).strip() for s in (_lu.get("sujets") or []) if str(s).strip()]
SITE = _lu.get("site") if isinstance(_lu.get("site"), dict) and _lu["site"].get("adresse") else None
VOCABULAIRE = [str(s).strip() for s in (_lu.get("vocabulaire") or []) if str(s).strip()]

_nuit = _lu.get("mode_nuit", {"debut": 22, "fin": 7})
try:
    HEURES_NUIT = None if _nuit is False else (int(_nuit.get("debut", 22)) % 24, int(_nuit.get("fin", 7)) % 24)
except (AttributeError, TypeError, ValueError):
    HEURES_NUIT = (22, 7)
