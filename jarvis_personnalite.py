"""
JARVIS - façon de parler propre à chaque personne du foyer (comme la personnalité réglable de Cornelius).

Chaque profil peut demander à la voix :
  « réponds-moi plus brièvement », « fais des réponses plus courtes »      réponses en une phrase si possible
  « donne-moi des réponses plus détaillées », « explique-moi plus »        réponses plus complètes
  « mets plus d'humour », « sois plus drôle »                              un peu plus d'humour
  « moins d'humour », « sois plus sérieux »                                 ton sérieux, sans blague
  « vouvoie-moi » / « tutoie-moi »                                          pour cette personne seulement
  « comment tu me parles ? », « quel est ton style avec moi ? »            ce qui est réglé
  « reprends ton style normal », « parle-moi normalement »                  tout revient comme avant
Le réglage est donné à Claude (ses consignes), et une nouvelle conversation démarre pour l'appliquer.
Les réglages restent sur ce PC, dans personnalite.json (jamais publié).
"""

import json
import re
import threading

import jarvis_config

FICHIER = jarvis_config.chemin("personnalite.json")
_verrou = threading.Lock()

_COURT = re.compile(r"\b(?:r[ée]ponds?(?:-moi)?|r[ée]ponses?|parle(?:-moi)?|sois|fais)\b.{0,30}"
                    r"\b(?:plus (?:courte?s?|br[èe]ve?s?|bri[èe]vement|concise?s?|court)|moins longue?s?|moins long)\b")
_LONG = re.compile(r"\b(?:r[ée]ponds?(?:-moi)?|r[ée]ponses?|explique(?:-moi)?|sois|fais)\b.{0,30}"
                   r"\b(?:plus (?:d[ée]taill[ée]e?s?|longue?s?|compl[èe]te?s?|en d[ée]tail)|moins courte?s?)\b|"
                   r"\bexplique(?:-moi)? (?:plus|davantage)\b")
_PLUS_HUMOUR = re.compile(r"\b(?:plus d'humour|sois (?:plus )?(?:dr[ôo]le|marrant|rigolo)|fais(?:-moi)? (?:plus )?rire|"
                          r"mets (?:plus )?d'humour|avec (?:plus )?d'humour)\b")
_MOINS_HUMOUR = re.compile(r"\b(?:moins d'humour|sans humour|pas d'humour|arr[êe]te (?:les blagues|l'humour|de blaguer)|"
                           r"sois (?:plus )?s[ée]rieux(?:se)?)\b")
_VOUS = re.compile(r"\b(?:vouvoie[- ]moi|tu peux me vouvoyer|vouvoyez[- ]moi)\b")
_TU = re.compile(r"\b(?:tutoie[- ]moi|tu peux me tutoyer|tutoyez[- ]moi|on peut se tutoyer)\b")
_ETAT = re.compile(r"\b(?:comment tu me parles|quel est ton style|ton style avec moi|comment tu me r[ée]ponds)\b")
_NORMAL = re.compile(r"\b(?:reprends? ton style (?:normal|habituel)|parle[- ]moi normalement|redeviens normal|"
                     r"style (?:normal|par d[ée]faut))\b")


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
            json.dump(donnees, f, ensure_ascii=False, indent=1)
    except OSError as erreur:
        print("Personnalité :", erreur)


def _profil():
    try:
        import jarvis_profils
        return jarvis_profils.actif() or ""
    except Exception:
        return ""


def reglages(ident=None):
    ident = _profil() if ident is None else ident
    valeur = _lire().get(ident or "principal")
    return valeur if isinstance(valeur, dict) else {}


def _regler(**valeurs):
    with _verrou:
        donnees = _lire()
        cle = _profil() or "principal"
        actuels = donnees.get(cle) if isinstance(donnees.get(cle), dict) else {}
        actuels.update(valeurs)
        donnees[cle] = {k: v for k, v in actuels.items() if v is not None}
        if not donnees[cle]:
            donnees.pop(cle)
        _ecrire(donnees)
    try:
        import jarvis_extras
        jarvis_extras.redemarrer_claude = True       # nouvelle conversation : Claude reçoit le nouveau style
    except Exception:
        pass


def vouvoiement():
    """True / False si la personne l'a choisi, None sinon (on garde alors le choix de l'accueil)."""
    return reglages().get("vous")


def consigne():
    """Ajoutée aux consignes de Claude : la façon de parler voulue par la personne qui parle."""
    r = reglages()
    parties = []
    if r.get("longueur") == "court":
        parties.append("Elle préfère des réponses très courtes : une phrase si possible, deux au plus.")
    elif r.get("longueur") == "long":
        parties.append("Elle préfère des réponses plus détaillées : tu peux aller jusqu'à cinq ou six phrases, "
                       "toujours sans liste ni markdown.")
    if r.get("humour") == "plus":
        parties.append("Elle aime l'humour : glisse volontiers une petite touche d'humour bienveillant.")
    elif r.get("humour") == "moins":
        parties.append("Elle préfère un ton sérieux : pas de blague ni de trait d'humour.")
    if r.get("vous") is True:
        parties.append("Vouvoie-la toujours.")
    elif r.get("vous") is False:
        parties.append("Tutoie-la toujours.")
    return (" Façon de parler choisie par la personne qui te parle : " + " ".join(parties)) if parties else ""


def _etat():
    r = reglages()
    morceaux = []
    if r.get("longueur"):
        morceaux.append("des réponses courtes" if r["longueur"] == "court" else "des réponses détaillées")
    if r.get("humour"):
        morceaux.append("plus d'humour" if r["humour"] == "plus" else "un ton sérieux")
    if r.get("vous") is not None:
        morceaux.append("le vouvoiement" if r["vous"] else "le tutoiement")
    if not morceaux:
        return "Je te parle avec mon style habituel. Tu peux me demander des réponses plus courtes, plus détaillées, " \
               "plus ou moins d'humour."
    return "Avec toi, j'utilise " + (morceaux[0] if len(morceaux) == 1 else ", ".join(morceaux[:-1]) + " et " + morceaux[-1]) + "."


def commande(t):
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    if _ETAT.search(t):
        return _etat()
    if _NORMAL.search(t):
        _regler(longueur=None, humour=None, vous=None)
        return "D'accord, je reprends mon style habituel."
    if _VOUS.search(t):
        _regler(vous=True)
        return "Entendu, je vous vouvoierai désormais."
    if _TU.search(t):
        _regler(vous=False)
        return "Parfait, on se tutoie."
    if _COURT.search(t):
        _regler(longueur="court")
        return "D'accord, je serai plus bref."
    if _LONG.search(t):
        _regler(longueur="long")
        return "D'accord, je te donnerai des réponses plus détaillées."
    if _MOINS_HUMOUR.search(t):
        _regler(humour="moins")
        return "D'accord, je reste sérieux."
    if _PLUS_HUMOUR.search(t):
        _regler(humour="plus")
        return "Avec plaisir, je vais essayer d'être plus drôle !"
    return None
