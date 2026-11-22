# -*- coding: utf-8 -*-
"""
JARVIS - les appareils que Jarvis ne sait pas encore piloter.

  « allume la télé Samsung », « redémarre la Livebox », « ferme les volets », « allume les lumières connectées »
Au lieu de laisser la demande sans réponse claire, Jarvis dit simplement qu'il ne sait pas encore le faire, et
le note dans le rapport technique (le type d'appareil seulement, par exemple « télé Samsung » : ni nom, ni
adresse, ni phrase), si l'utilisateur a accepté les rapports. C'est ce qui permet de savoir quels appareils
ajouter en premier.
Les appareils que Jarvis pilote déjà gardent leurs propres modules : Freebox (jarvis_freebox), télés Android TV
et Google TV (jarvis_tele), Apple TV (jarvis_appletv), PS5 (jarvis_ps5), imprimante (jarvis_imprimante).
"""

import re

_ACTION = re.compile(
    r"\b(?:allume[rz]?|[ée]tein[st]|[ée]teindre|mets|mettre|monte[rz]?|baisse[rz]?|change[rz]?|lance[rz]?|coupe[rz]?"
    r"|r[èe]gle[rz]?|ouvre[rz]?|ouvrir|ferme[rz]?|red[ée]marre[rz]?|connecte[rz]?|associe[rz]?|relie[rz]?|pilote[rz]?"
    r"|contr[ôo]le[rz]?|active[rz]?|d[ée]sactive[rz]?|d[ée]marre[rz]?|arr[êe]te[rz]?|zappe[rz]?|passe[rz]?)\b")
# Une recherche, un achat ou une question générale n'est pas un ordre donné à l'appareil
_AUTRE = re.compile(r"\b(?:cherche[rz]?|recherche[rz]?|ach[èe]te[rz]?|prix|co[uû]te|amazon|youtube|vid[ée]os?|c'est quoi"
                    r"|qu'est[- ]ce qu|pourquoi|comment|note que|rappelle|liste|site)\b")
_TELE = r"(?:t[ée]l[ée]s?|tv|t[ée]l[ée]visions?|t[ée]l[ée]viseurs?|smart tv)"
# Télés dont la marque est dite : à regarder avant le module des télés (qui croirait à une télé déjà associée)
TELES = (
    (re.compile(r"\b" + _TELE + r" samsung\b|\bsamsung " + _TELE + r"\b"), "tele_samsung", "les télés Samsung"),
    (re.compile(r"\b" + _TELE + r" lg\b|\blg " + _TELE + r"\b"), "tele_lg", "les télés LG"),
)
AUTRES = (
    (re.compile(r"\blivebox\b|\bd[ée]codeur (?:tv )?orange\b"), "livebox", "la Livebox"),
    (re.compile(r"\bbbox\b|\bd[ée]codeur (?:tv )?bouygues\b"), "bbox", "la Bbox"),
    (re.compile(r"\bbox sfr\b|\bsfr box\b|\bd[ée]codeur (?:tv )?sfr\b"), "box_sfr", "la box SFR"),
    (re.compile(r"\b(?:philips )?hue\b|\b(?:ampoules?|lumi[èe]res?|lampes?) connect[ée]es?\b"), "lumieres",
     "les lumières connectées"),
    (re.compile(r"\bprises? connect[ée]es?\b"), "prises", "les prises connectées"),
    (re.compile(r"\bthermostat\b|\bnetatmo\b|\btado\b"), "thermostat", "le thermostat"),
    (re.compile(r"\bvolets?(?: roulants?)?\b|\bstores? (?:[ée]lectriques?|connect[ée]s?)\b"), "volets", "les volets"),
    (re.compile(r"\bportail\b|\bporte d[eu] garage\b"), "portail", "le portail"),
    (re.compile(r"\baspirateur robot\b|\brobot aspirateur\b|\broomba\b"), "aspirateur", "l'aspirateur robot"),
    (re.compile(r"\balexa\b|\b(?:amazon )?echo (?:dot|show)\b"), "alexa", "les enceintes Alexa"),
    (re.compile(r"\bgoogle (?:home|nest)\b|\bnest (?:mini|hub|audio)\b"), "google_home", "les enceintes Google"),
    (re.compile(r"\bsonos\b"), "sonos", "les enceintes Sonos"),
    (re.compile(r"\bhomepod\b"), "homepod", "le HomePod"),
    (re.compile(r"\bchromecast\b"), "chromecast", "le Chromecast"),
    (re.compile(r"\bfire ?tv\b|\bfire stick\b"), "fire_tv", "le Fire TV"),
    (re.compile(r"\bxbox\b"), "xbox", "la Xbox"),
    (re.compile(r"\bnintendo switch\b|\bla switch\b"), "switch", "la Switch"),
)


def _noter(cle):
    try:
        import jarvis_rapports
        jarvis_rapports.noter("appareil_non_gere", quoi=cle)
    except Exception:
        pass


def commande(t, teles_seulement=False):
    """Renvoie la phrase à dire si la demande vise un appareil que Jarvis ne pilote pas encore, sinon None.
    teles_seulement : seulement les télés dont la marque est dite (appelé avant le module des télés)."""
    t = (t or "").replace("’", "'").lower()
    if not _ACTION.search(t) or _AUTRE.search(t):
        return None
    for motif, cle, nom in (TELES if teles_seulement else TELES + AUTRES):
        if motif.search(t):
            _noter(cle)
            return f"Je ne sais pas encore piloter {nom}. Je le note pour une prochaine version."
    return None
