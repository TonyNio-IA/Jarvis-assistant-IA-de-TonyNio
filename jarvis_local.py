# -*- coding: utf-8 -*-
"""
JARVIS - commandes locales de plus : tout ce qui se règle sans Claude (donc sans quota, et pour ceux
qui ont installé Jarvis sans Claude).

  - le hasard : « lance un dé », « pile ou face », « tire un nombre entre 1 et 100 », « tire au sort entre A et B » ;
  - le calendrier : « dans combien de jours c'est Noël », « quel jour sera-t-on dans dix jours »,
    « quel jour tombe le 14 juillet », « quelle est la date de demain », « quel est le numéro de la semaine » ;
  - le PC : place sur le disque, mémoire, batterie, depuis quand il est allumé, adresse IP, Internet, processeur,
    carte graphique, version de Windows, résolution de l'écran ;
  - le ciel : lever et coucher du soleil, phase de la lune ;
  - une météo plus fine : « va-t-il pleuvoir demain », « faut-il un parapluie », « quel temps ce soir »,
    « la météo de la semaine », « quel temps samedi », « y a-t-il du vent » ;
  - la conversation : « merci », « ça va », « qui es-tu », blagues, devinettes, proverbes, faits amusants ;
  - sans Claude : une question que Jarvis ne sait pas traiter lui-même peut être cherchée sur Google (après un « oui »).
Chaque fonction renvoie la phrase à dire, ou None si la demande ne la concerne pas.
Rien n'est envoyé nulle part, sauf la météo (Open-Meteo) et la recherche Google que tu acceptes.
"""

import ctypes
import datetime
import math
import os
import random
import re
import shutil
import socket
import subprocess
import time
import unicodedata
import urllib.parse

import jarvis_config
import jarvis_pratique as _p

_SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]
_MOIS_SANS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet", "aout",
              "septembre", "octobre", "novembre", "decembre"]
_JOURS_SANS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _sans_accents(t):
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("œ", "oe")


def _phrase(t, accents=False):
    """La demande en minuscules et sans accents (sauf si on les garde), sans « Jarvis » au début ni politesse à la fin."""
    t = t.replace("’", "'").lower()
    if not accents:
        t = _sans_accents(t)
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t)
    t = re.sub(r"[\s,]*(?:s'il (?:te|vous) pla[iî]t|stp|jarvis)\W*$", "", t)
    return t.strip(" .!?")


def _vous():
    """Vrai si la personne vouvoie Jarvis (profil, sinon réglage d'accueil)."""
    try:
        import jarvis_personnalite
        v = jarvis_personnalite.vouvoiement()
        if v is not None:
            return bool(v)
    except Exception:
        pass
    try:
        import jarvis_accueil
        return jarvis_accueil.vouvoiement()
    except Exception:
        return False


def _tu(tutoie, vouvoie):
    return vouvoie if _vous() else tutoie


def _nombres(texte):
    """Tous les nombres d'un texte (chiffres ou lettres), dans l'ordre."""
    mots = _p._decouper(texte)
    trouves, i = [], 0
    while i < len(mots):
        valeur, j = _p._lire_nombre(mots, i)
        if valeur is None:
            i += 1
        else:
            trouves.append(valeur)
            i = j
    return trouves


def _maj(texte):
    return texte[:1].upper() + texte[1:]


def _date_longue(d, annee=True):
    jour = "premier" if d.day == 1 else str(d.day)
    return f"{JOURS[d.weekday()]} {jour} {MOIS[d.month - 1]}" + (f" {d.year}" if annee else "")


def _jour_mois(d, annee=None):
    """« 14 juillet » (avec l'année si ce n'est pas l'année en cours)."""
    jour = "premier" if d.day == 1 else str(d.day)
    avec = d.year != datetime.date.today().year if annee is None else annee
    return f"{jour} {MOIS[d.month - 1]}" + (f" {d.year}" if avec else "")


# ---------- Hasard ----------

_NB_DES = {"un": 1, "une": 1, "le": 1, "mon": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
           "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6}
_DE = re.compile(r"^(?:lance|lances|jette|jettes|lancer|jeter|fais rouler|roule|tire)(?:-moi| moi)? "
                 r"(?P<n>un|une|le|mon|deux|trois|quatre|cinq|six|[1-6]) des?(?: (?:a|de) (?P<f>.+?) faces?)?$")
_PILE = re.compile(r"\bpile ou face\b|^(?:lance|jette|tire|fais)\w*(?:-moi)? (?:une|la) piece$")
_NOMBRE = re.compile(r"^(?:tire|tires|choisis|choisi|donne|dis|genere|trouve|invente)(?:-moi| moi)?(?: un| une)? "
                     r"(?:nombre|chiffre|numero)(?: au hasard| aleatoire| quelconque)?"
                     r"(?:(?: compris)? (?:entre|de) (?P<a>.+?) (?:et|a|jusqu'a) (?P<b>.+))?$")
_TIRAGE = re.compile(r"^(?:tire|tires|tirer)(?:-moi)?(?: quelqu'un| un nom| un pr[ée]nom)? au sort(?: entre| parmi| dans)? (?P<l>.+)$|"
                     r"^(?:choisis|d[ée]cide|tranche)(?:-moi| moi)?(?: pour moi)? entre (?P<m>.+)$")


def _hasard(s, avec_accents=""):
    if _PILE.search(s):
        return random.choice(["Pile.", "Face."])
    m = _DE.match(s)
    if m:
        n = _NB_DES[m.group("n")]
        faces = 6
        if m.group("f"):
            trouves = _nombres(m.group("f"))
            if not trouves or not (2 <= trouves[0] <= 1000) or trouves[0] != int(trouves[0]):
                return None
            faces = int(trouves[0])
        tirages = [random.randint(1, faces) for _ in range(n)]
        quel = "Le dé" if faces == 6 else f"Le dé à {faces} faces"
        if n == 1:
            return f"{quel} tombe sur {tirages[0]}."
        return (f"{'Les dés donnent' if faces == 6 else f'Les dés à {faces} faces donnent'} "
                f"{', '.join(map(str, tirages[:-1]))} et {tirages[-1]} : ça fait {sum(tirages)}.")
    m = _NOMBRE.match(s)
    if m:
        bas, haut = 1, 100
        if m.group("a"):
            a, b = _nombres(m.group("a")), _nombres(m.group("b"))
            if not a or not b:
                return None
            bas, haut = int(min(a[0], b[0])), int(max(a[0], b[0]))
            if haut - bas > 10 ** 9 or bas == haut:
                return None
        return f"Je choisis {random.randint(bas, haut)}."
    m = _TIRAGE.match(s)
    if m and avec_accents:                       # les noms sont redits avec leurs accents (« pâtes »)
        m = _TIRAGE.match(avec_accents) or m
    if m:
        liste = m.group("l") or m.group("m")
        morceaux = [x.strip() for x in re.split(r",|;|\bet\b|\bou\b", liste) if x.strip()]
        morceaux = list(dict.fromkeys(morceaux))
        if not (2 <= len(morceaux) <= 12) or any(len(x.split()) > 5 for x in morceaux):
            return None
        return (f"Le sort a choisi : {random.choice(morceaux)}." if m.group("l")
                else f"Je choisis : {random.choice(morceaux)}.")
    return None


# ---------- Calendrier ----------

def _paques(annee):
    """Dimanche de Pâques (calendrier grégorien, méthode de Meeus)."""
    a, b, c = annee % 19, annee // 100, annee % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mois, jour = divmod(h + l - 7 * m + 114, 31)
    return datetime.date(annee, mois, jour + 1)


def _dimanche(annee, mois, rang):
    """Le « rang »-ième dimanche du mois (rang -1 : le dernier)."""
    if rang > 0:
        premier = datetime.date(annee, mois, 1)
        return premier + datetime.timedelta(days=(6 - premier.weekday()) % 7 + 7 * (rang - 1))
    dernier = datetime.date(annee, mois, calendar_jours(annee, mois))
    return dernier - datetime.timedelta(days=(dernier.weekday() + 1) % 7)


def calendar_jours(annee, mois):
    return [31, 29 if _bissextile(annee) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mois - 1]


def _bissextile(annee):
    return annee % 4 == 0 and (annee % 100 != 0 or annee % 400 == 0)


def _fete_des_meres(a):
    d = _dimanche(a, 5, -1)
    return _dimanche(a, 6, 1) if d == _paques(a) + datetime.timedelta(days=49) else d


def _black_friday(a):
    jeudis = [datetime.date(a, 11, j) for j in range(1, 31) if datetime.date(a, 11, j).weekday() == 3]
    return jeudis[3] + datetime.timedelta(days=1)


# (motif sans accents, date selon l'année, comment on le dit)
_FETES = [
    (r"reveillon de noel|veille de noel", lambda a: datetime.date(a, 12, 24), "le réveillon de Noël"),
    (r"noel", lambda a: datetime.date(a, 12, 25), "Noël"),
    (r"reveillon du nouvel an|saint[- ]sylvestre|reveillon de la saint[- ]sylvestre|31 decembre",
     lambda a: datetime.date(a, 12, 31), "la Saint-Sylvestre"),
    (r"nouvel an|jour de l'an|bonne annee", lambda a: datetime.date(a, 1, 1), "le jour de l'an"),
    (r"saint[- ]valentin", lambda a: datetime.date(a, 2, 14), "la Saint-Valentin"),
    (r"fete nationale", lambda a: datetime.date(a, 7, 14), "la fête nationale"),
    (r"fete du travail", lambda a: datetime.date(a, 5, 1), "la fête du travail"),
    (r"armistice", lambda a: datetime.date(a, 11, 11), "l'armistice"),
    (r"toussaint", lambda a: datetime.date(a, 11, 1), "la Toussaint"),
    (r"assomption", lambda a: datetime.date(a, 8, 15), "l'Assomption"),
    (r"halloween", lambda a: datetime.date(a, 10, 31), "Halloween"),
    (r"lundi de paques", lambda a: _paques(a) + datetime.timedelta(days=1), "le lundi de Pâques"),
    (r"paques", _paques, "Pâques"),
    (r"ascension", lambda a: _paques(a) + datetime.timedelta(days=39), "l'Ascension"),
    (r"lundi de pentecote", lambda a: _paques(a) + datetime.timedelta(days=50), "le lundi de Pentecôte"),
    (r"pentecote", lambda a: _paques(a) + datetime.timedelta(days=49), "la Pentecôte"),
    (r"fete des meres", _fete_des_meres, "la fête des mères"),
    (r"fete des peres", lambda a: _dimanche(a, 6, 3), "la fête des pères"),
    (r"black friday", _black_friday, "le Black Friday"),
]
_NOMS_MOIS = "|".join(_MOIS_SANS)
_JOUR_DIT = (r"(?:premier|1er|\d{1,2}|(?:(?:vingt|trente|un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|"
             r"douze|treize|quatorze|quinze|seize|et)[ -]?)+)")
_DATE_DITE = re.compile(r"(?:le )?(?P<j>" + _JOUR_DIT + r")\s*(?P<m>" + _NOMS_MOIS + r")(?:\s+(?P<a>20\d\d))?\b")
_DATE_CHIFFRES = re.compile(r"\b(?P<j>\d{1,2})[/.](?P<m>\d{1,2})(?:[/.](?P<a>20\d\d|\d\d))?\b")


def _jour_en_nombre(j):
    j = j.strip()
    if j in ("premier", "1er"):
        return 1
    if j.isdigit():
        return int(j)
    trouves = _nombres(j)
    return int(trouves[0]) if trouves else None


def _prochaine(jour, mois, annee=None, aujourdhui=None):
    """La date (jour, mois) : celle de l'année demandée, sinon la prochaine à partir d'aujourd'hui."""
    aujourdhui = aujourdhui or datetime.date.today()
    annees = [annee] if annee else [aujourdhui.year, aujourdhui.year + 1, aujourdhui.year + 2]
    for a in annees:
        try:
            d = datetime.date(a, mois, jour)
        except ValueError:
            continue
        if annee or d >= aujourdhui:
            return d
    return None


def _evenement(s):
    """Ce que la phrase désigne : (date, nom dit, est une fête) ou None. Une fête ou une date précise."""
    aujourdhui = datetime.date.today()
    annee = re.search(r"\b(20\d\d)\b", s)
    annee = int(annee.group(1)) if annee else None
    for motif, calcul, nom in _FETES:
        if re.search(r"(?<![a-z])(?:" + motif + r")(?![a-z])", s):
            for a in ([annee] if annee else [aujourdhui.year, aujourdhui.year + 1]):
                d = calcul(a)
                if annee or d >= aujourdhui:
                    return d, nom, True
    m = _DATE_DITE.search(s)
    if m:
        j = _jour_en_nombre(m.group("j"))
        mois = _MOIS_SANS.index(m.group("m")) + 1
        if j and 1 <= j <= 31:
            d = _prochaine(j, mois, int(m.group("a")) if m.group("a") else None)
            if d:
                return d, "", False
    m = _DATE_CHIFFRES.search(s)
    if m:
        j, mois = int(m.group("j")), int(m.group("m"))
        a = m.group("a")
        a = (2000 + int(a) if len(a) == 2 else int(a)) if a else None
        if 1 <= mois <= 12 and 1 <= j <= 31:
            d = _prochaine(j, mois, a)
            if d:
                return d, "", False
    return None


def _distance(d):
    """« dans 31 jours », « demain », « aujourd'hui »..."""
    n = (d - datetime.date.today()).days
    if n == 0:
        return "aujourd'hui"
    if n == 1:
        return "demain"
    if n == -1:
        return "hier"
    if n < 0:
        return f"il y a {-n} jours"
    return f"dans {n} jours"


_COMBIEN = re.compile(r"^(?:dans combien de (?:jours?|semaines?|mois|temps)(?: (?:est[- ]ce que |est |sera |c'est |ce sera |on est |on fete |arrive ))*|"
                      r"combien (?:de )?(?:jours?|semaines?|mois|temps)(?: (?:il )?(?:me )?(?:reste|restent|faut[- ]il|y a[- ]t[- ]il))?"
                      r"(?: avant| jusqu'(?:a|au|aux)|jusqu'|pour|d'ici)?|"
                      r"(?:il )?(?:me )?reste(?:-t-il)? combien (?:de )?(?:jours?|semaines?|temps)(?: avant| jusqu'(?:a|au|aux)| pour)?)\s*")
_QUAND = re.compile(r"^(?:c'est quand|quand (?:est|tombe|sera|a lieu|arrive)|quelle est la date (?:de|du|des)|"
                    r"a quelle date (?:est|tombe|sera)|quel jour (?:est|tombe|sera|a lieu|on fete|est[- ]ce)|"
                    r"quel jour de la semaine (?:est|tombe|sera))\s*")
_DECALAGE = re.compile(r"\b(apres[- ]demain|avant[- ]hier|demain|hier)\b")
_DATE_INTENT = re.compile(r"\b(?:quel(?:le)? (?:est la )?(?:date|jour)|on (?:est|sera|etait)|nous (?:sommes|serons|etions)|"
                          r"sera[- ]t?[- ]?on|etait[- ]on|est[- ]on|sommes[- ]nous|serons[- ]nous|etions[- ]nous)\b")
_NOMBRE_UNITE = re.compile(r"\b(?P<n>.+?)\s+(?P<u>jours?|semaines?|mois|ans?|annees?)\b")


def _ajouter_mois(d, n):
    mois = d.month - 1 + n
    annee, mois = d.year + mois // 12, mois % 12 + 1
    return datetime.date(annee, mois, min(d.day, calendar_jours(annee, mois)))


def _calendrier(s):
    aujourdhui = datetime.date.today()
    # la date d'aujourd'hui : « quelle est la date », « on est quel jour », « la date d'aujourd'hui »
    if re.fullmatch(r"(?:quelle est la date|quelle date (?:on est|sommes[- ]nous|est[- ]on)|la date(?: d'aujourd'hui)?|"
                    r"(?:on est|nous sommes|c'est) quel jour(?: aujourd'hui)?|quel jour (?:on est|est[- ]on|sommes[- ]nous|est[- ]ce)"
                    r"(?: aujourd'hui)?|quelle est la date d'aujourd'hui|quel jour (?:est[- ]ce )?aujourd'hui)", s):
        return f"Nous sommes le {_date_longue(aujourdhui)}."
    # le numéro de la semaine
    if re.search(r"\b(?:numero de (?:la )?semaine|quelle semaine (?:on est|sommes[- ]nous|est[- ]on)|"
                 r"on est (?:en|a) quelle semaine|semaine (?:numero|de l'annee))\b", s):
        annee, semaine, _ = aujourdhui.isocalendar()
        lundi = aujourdhui - datetime.timedelta(days=aujourdhui.weekday())
        dimanche = lundi + datetime.timedelta(days=6)
        debut = f"{lundi.day}" + (f" {MOIS[lundi.month - 1]}" if lundi.month != dimanche.month else "")
        return (f"Nous sommes en semaine {semaine}, du lundi {debut} au dimanche {dimanche.day} "
                f"{MOIS[dimanche.month - 1]}.")
    # année bissextile
    if re.search(r"\bbissextile", s):
        a = re.search(r"\b(\d{4})\b", s)
        a = int(a.group(1)) if a else aujourdhui.year
        return (f"Oui, {a} est une année bissextile : février a 29 jours." if _bissextile(a)
                else f"Non, {a} n'est pas une année bissextile.")
    # demain, hier... : « quelle est la date de demain », « on sera quel jour demain »
    m = _DECALAGE.search(s)
    if m and _DATE_INTENT.search(s) and not re.search(r"\b(?:meteo|temps|pluie|rendez|reunion|rappel|minuteur)\b", s):
        n = {"demain": 1, "hier": -1, "apres demain": 2, "apres-demain": 2, "avant hier": -2, "avant-hier": -2}[
            m.group(1).replace("  ", " ")]
        d = aujourdhui + datetime.timedelta(days=n)
        quand = {1: "Demain", 2: "Après-demain", -1: "Hier", -2: "Avant-hier"}[n]
        return f"{quand}, {'nous serons' if n > 0 else 'nous étions'} le {_date_longue(d)}."
    # « dans trois semaines », « il y a dix jours » + quel jour / quelle date
    if _DATE_INTENT.search(s):
        m = re.search(r"\b(dans|il y a)\s+(.+)", s)
        if m:
            u = _NOMBRE_UNITE.match(m.group(2))
            if u:
                nombres = _nombres(u.group("n"))
                if len(nombres) == 1 and nombres[0] == int(nombres[0]) and 0 < nombres[0] <= 1000:
                    n = int(nombres[0]) * (1 if m.group(1) == "dans" else -1)
                    unite = u.group("u")
                    if unite.startswith("jour"):
                        d = aujourdhui + datetime.timedelta(days=n)
                    elif unite.startswith("semaine"):
                        d = aujourdhui + datetime.timedelta(days=7 * n)
                    elif unite == "mois":
                        d = _ajouter_mois(aujourdhui, n)
                    else:
                        d = _ajouter_mois(aujourdhui, 12 * n)
                    return (f"Dans {abs(n)} {u.group('u')}, nous serons le {_date_longue(d)}." if n > 0
                            else f"Il y a {abs(n)} {u.group('u')}, nous étions le {_date_longue(d)}.")
    # « combien de jours dans un février de 2018 » : la durée d'un mois, pas un compte à rebours (voir jarvis_savoir)
    if re.search(r"\bcombien (?:de )?jours (?:y a[- ]t[- ]il |il y a )?(?:dans|en) (?:le mois d[eu'] ?|un |le )?"
                 r"(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\b", s):
        return None
    # « dans combien de jours c'est Noël », « combien de jours avant le 14 juillet »
    m = _COMBIEN.match(s)
    if m:
        quoi = _evenement(s[m.end():])
        if quoi:
            d, nom, _ = quoi
            n = (d - aujourdhui).days
            if n == 0:
                return f"C'est aujourd'hui : {nom} !" if nom else "C'est aujourd'hui !"
            if n == 1:
                return f"C'est demain : {nom}, {_date_longue(d)}." if nom else f"C'est demain, {_date_longue(d)}."
            suite = f", soit environ {n // 7} semaines" if n >= 21 else ""
            cible = f"{nom}, le {_date_longue(d)}" if nom else f"le {_date_longue(d)}"
            return f"Il reste {n} jours avant {cible}{suite}."
        return None
    # « c'est quand Pâques », « quel jour tombe le 14 juillet »
    m = _QUAND.match(s)
    if m:
        quoi = _evenement(s[m.end():])
        if quoi:
            d, nom, _ = quoi
            if nom:
                return f"{_maj(nom)}, c'est le {_date_longue(d)} : {_distance(d)}."
            return f"Le {_jour_mois(d, annee=d.year != aujourdhui.year)}, c'est un {JOURS[d.weekday()]}."
    return None


# ---------- Le PC ----------

def _go(octets):
    x = octets / 2 ** 30
    return _p.dire_nombre(round(x, 1)) if x < 10 else str(round(x))


def _disques():
    resultat = []
    lecteurs = ctypes.windll.kernel32.GetLogicalDrives()
    for i in range(26):
        if lecteurs & (1 << i):
            racine = f"{chr(65 + i)}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(racine) == 3:           # disque fixe
                try:
                    u = shutil.disk_usage(racine)
                except OSError:
                    continue
                if u.total:
                    resultat.append((chr(65 + i), u.free, u.total))
    return resultat


def _disque():
    disques = _disques()
    if not disques:
        return None
    if len(disques) == 1:
        lettre, libre, total = disques[0]
        pct = round(libre * 100 / total)
        return (f"Il reste {_go(libre)} gigaoctets libres sur {_go(total)}, soit {pct} pour cent."
                + (" C'est peu : pense à faire de la place." if pct < 10 and not _vous()
                   else " C'est peu : pensez à faire de la place." if pct < 10 else ""))
    morceaux = [f"disque {l} : {_go(libre)} gigaoctets libres sur {_go(total)}" for l, libre, total in disques]
    return "Sur ton PC, " + ", ".join(morceaux[:-1]) + " et " + morceaux[-1] + "."


class _Memoire(ctypes.Structure):
    _fields_ = [("taille", ctypes.c_ulong), ("charge", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                ("libre", ctypes.c_ulonglong), ("total_swap", ctypes.c_ulonglong), ("libre_swap", ctypes.c_ulonglong),
                ("total_virtuel", ctypes.c_ulonglong), ("libre_virtuel", ctypes.c_ulonglong),
                ("etendue", ctypes.c_ulonglong)]


def _memoire():
    m = _Memoire()
    m.taille = ctypes.sizeof(_Memoire)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return None
    utilise = m.total - m.libre
    return (f"Ton PC a {_go(m.total)} gigaoctets de mémoire vive : {_go(utilise)} utilisés, {_go(m.libre)} libres, "
            f"soit {m.charge} pour cent d'utilisation.")


def _allume():
    ms = ctypes.windll.kernel32.GetTickCount64
    ms.restype = ctypes.c_ulonglong
    s = int(ms() // 1000)
    j, h, mn = s // 86400, s % 86400 // 3600, s % 3600 // 60
    if j:
        duree = f"{j} jour{'s' if j > 1 else ''} et {h} heure{'s' if h > 1 else ''}"
    elif h:
        duree = f"{h} heure{'s' if h > 1 else ''} et {mn} minute{'s' if mn > 1 else ''}"
    else:
        duree = f"{mn} minute{'s' if mn > 1 else ''}"
    return f"Ton PC est allumé depuis {duree}."


class _Alimentation(ctypes.Structure):
    _fields_ = [("secteur", ctypes.c_ubyte), ("drapeau", ctypes.c_ubyte), ("pourcent", ctypes.c_ubyte),
                ("etat", ctypes.c_ubyte), ("duree", ctypes.c_ulong), ("duree_pleine", ctypes.c_ulong)]


def _batterie():
    e = _Alimentation()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(e)):
        return None
    if e.drapeau == 255 or e.drapeau & 128 or e.pourcent == 255:
        return "Ce PC n'a pas de batterie : il est branché sur le secteur."
    texte = f"La batterie est à {e.pourcent} pour cent"
    if e.secteur == 1:
        texte += ", le PC est branché" + (" et la batterie est pleine." if e.pourcent >= 100 else " : elle se recharge.")
    else:
        texte += ", sur batterie"
        if e.duree != 0xFFFFFFFF and e.duree > 0:
            h, mn = e.duree // 3600, e.duree % 3600 // 60
            texte += f" : il reste environ {h} heure{'s' if h > 1 else ''} {mn}." if h else f" : il reste environ {mn} minutes."
        else:
            texte += "."
    return texte


def _adresse_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))             # rien n'est envoyé : on lit seulement la carte réseau choisie
        ip = s.getsockname()[0]
    except OSError:
        return "Je ne trouve pas d'adresse sur le réseau : le PC n'est peut-être pas connecté."
    finally:
        s.close()
    return f"L'adresse de ce PC sur ton réseau est {ip.replace('.', ' point ')}."


def _internet():
    for hote, port in (("1.1.1.1", 443), ("8.8.8.8", 53), ("9.9.9.9", 443)):
        try:
            socket.create_connection((hote, port), timeout=3).close()
            return "Oui, tu es bien connecté à Internet."
        except OSError:
            continue
    return "Non, je n'arrive pas à joindre Internet. Vérifie ta box ou ton câble."


def _lire_registre(cle, nom):
    import winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, cle) as k:
        return winreg.QueryValueEx(k, nom)[0]


def _processeur():
    nom = _lire_registre(r"HARDWARE\DESCRIPTION\System\CentralProcessor\0", "ProcessorNameString")
    nom = re.sub(r"\((?:R|TM|tm|r)\)|\bCPU\b|\b\d+(?:st|nd|rd|th) Gen\b", "", nom)
    nom = re.sub(r"\s*@.*$", "", nom)
    nom = " ".join(nom.split())
    return f"Ton processeur est un {nom}, avec {os.cpu_count()} threads."


def _carte_graphique():
    import jarvis_rapports
    cartes = jarvis_rapports._cartes_graphiques()
    noms = [c.get("nom") for c in cartes if c.get("nom")]
    if not noms:
        return "Je ne trouve pas ta carte graphique."
    if len(noms) == 1:
        return f"Ta carte graphique est une {noms[0]}." if not re.match(r"(?i)[aeiouy]", noms[0]) else \
            f"Ta carte graphique est une {noms[0]}."
    return f"Ton PC a {len(noms)} cartes graphiques : " + ", ".join(noms[:-1]) + " et " + noms[-1] + "."


def _windows():
    build = int(_lire_registre(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "CurrentBuildNumber"))
    nom = "Windows 11" if build >= 22000 else "Windows 10"
    try:
        version = _lire_registre(r"SOFTWARE\Microsoft\Windows NT\CurrentVersion", "DisplayVersion")
    except OSError:
        version = ""
    return f"Tu as {nom}" + (f", version {version}" if version else "") + f", numéro de build {build}."


def _ecran():
    u = ctypes.windll.user32
    texte = f"Ton écran fait {u.GetSystemMetrics(0)} sur {u.GetSystemMetrics(1)} pixels"
    try:
        echelle = round(u.GetDpiForSystem() * 100 / 96)
        texte += f", avec un affichage à {echelle} pour cent"
    except Exception:
        pass
    nb = u.GetSystemMetrics(80)
    return texte + (f". Tu as {nb} écrans." if nb > 1 else ".")


_PC_VERBES = r"\b(?:ouvre|ferme|lance|nettoie|vide|supprime|formate|ejecte|cherche|trouve|deplace|copie|range)\b"


def _systeme(s):
    if re.search(_PC_VERBES, s):
        return None
    if re.search(r"\b(?:espace disque|espace libre|place (?:libre|disponible|sur le disque|qu'il (?:me )?reste)|"
                 r"stockage|disque dur|disque c|le disque)\b", s) \
            and re.search(r"\b(?:reste|libre|disponible|combien|plein|occupe|quel(?:le)?)\b", s):
        return _disque()
    if re.search(r"\b(?:memoire vive|ram)\b", s) and re.search(r"\b(?:combien|utilise|libre|j'ai|ai[- ]je|occupe|reste|quelle?|taille)\b", s) \
            and not re.search(r"\b(?:charge|temperature)\b", s):
        return _memoire()
    if re.search(r"\b(?:depuis (?:combien de temps|quand)|combien de temps)\b.*\b(?:pc|ordinateur|ordi|machine)\b.*\b(?:allume|demarre|marche|tourne)\b", s) \
            or re.search(r"\b(?:uptime|duree d'allumage)\b", s):
        return _allume()
    if re.search(r"\b(?:batterie|autonomie)\b", s) and re.search(r"\b(?:niveau|combien|reste|quel(?:le)?|charge|pourcentage|etat|est[- ]elle|%)\b", s) \
            and not re.search(r"\b(?:telephone|tablette|manette|casque|souris|clavier|telecommande|montre)\b", s):
        return _batterie()
    if re.search(r"\badresse ip\b|\bmon ip\b|\bip locale\b", s) and not re.search(r"\b(?:publique|externe|internet|exterieure)\b", s):
        return _adresse_ip()
    if re.search(r"\b(?:suis[- ]je|je suis|on est|est[- ]ce que (?:je suis|on est|j'ai)|j'ai)\b.*\binternet\b|"
                 r"\binternet\b.*\b(?:marche|fonctionne|coupe|disponible)\b|\by a[- ]t[- ]il internet\b|\bconnexion internet\b", s) \
            and not re.search(r"\b(?:freebox|box|debit|vitesse|test)\b", s):
        return _internet()
    if re.search(r"\bquel(?:le)?\b.*\b(?:processeur|cpu)\b|\b(?:j'ai|ai[- ]je)\b.*\b(?:processeur|cpu)\b", s) \
            and not re.search(r"\b(?:charge|utilise|temperature|pour cent|%|sollicite)\b", s):
        return _processeur()
    if re.search(r"\b(?:quelle|quel|j'ai|ai[- ]je)\b.*\b(?:carte graphique|gpu|carte video)\b", s):
        return _carte_graphique()
    if re.search(r"\b(?:quelle?|sous quel(?:le)?|j'ai|ai[- ]je)\b.*\bwindows\b", s) and re.search(r"\b(?:version|windows 10|windows 11|quel windows|sous quel)\b", s):
        return _windows()
    if re.search(r"\b(?:resolution|taille)\b.*\becran\b|\becran\b.*\bresolution\b|\bquelle?\b.*\bresolution\b", s):
        return _ecran()
    if re.search(r"\b(?:nom|comment s'appelle)\b.*\b(?:mon|ce|cet|de mon|de ce)\b.*\b(?:pc|ordinateur|ordi)\b", s) \
            and not re.search(r"\b(?:change|renomme|appelle[- ]le|s'appelle (?:maintenant|desormais))\b", s):
        nom = os.environ.get("COMPUTERNAME")
        return f"Ce PC s'appelle {nom}." if nom else None
    if re.search(r"\bnom d'utilisateur\b|\bquel compte\b.*\bwindows\b|\bsous quel compte\b", s):
        nom = os.environ.get("USERNAME")
        return f"Tu es connecté à Windows avec le compte {nom}." if nom else None
    return None


# ---------- Le ciel : soleil et lune ----------

def _soleil_minutes(d, lat, lon):
    """(lever, coucher) en minutes depuis minuit, heure locale du PC ; None s'il n'y a ni lever ni coucher (formules de la NOAA)."""
    n = d.timetuple().tm_yday
    g = 2 * math.pi / 365 * (n - 1)
    equation = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                         - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    cos_h = math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl)) - math.tan(phi) * math.tan(decl)
    if not -1 <= cos_h <= 1:
        return None
    h = math.degrees(math.acos(cos_h))
    midi_local = datetime.datetime(d.year, d.month, d.day, 12).astimezone()
    decalage = midi_local.utcoffset().total_seconds() / 60
    return 720 - 4 * (lon + h) - equation + decalage, 720 - 4 * (lon - h) - equation + decalage


def _heure_dite(minutes):
    minutes = int(round(minutes)) % 1440
    h, m = divmod(minutes, 60)
    return f"{h} heure{'s' if h > 1 else ''}" + (f" {m}" if m else "")


def _ville():
    import jarvis_commandes
    return jarvis_commandes.VILLE_DEFAUT


def _soleil(s):
    lever = re.search(r"\b(?:se leve|lever|leve)\b", s)
    coucher = re.search(r"\b(?:se couche|coucher|couche)\b", s)
    if not (re.search(r"\bsoleil\b", s) and (lever or coucher)):
        return None
    nom, lat, lon = _ville()
    d = datetime.date.today()
    quand = "aujourd'hui"
    if re.search(r"\bapres[- ]demain\b", s):
        d, quand = d + datetime.timedelta(days=2), "après-demain"
    elif re.search(r"\bdemain\b", s):
        d, quand = d + datetime.timedelta(days=1), "demain"
    elif re.search(r"\bhier\b", s):
        d, quand = d - datetime.timedelta(days=1), "hier"
    heures = _soleil_minutes(d, lat, lon)
    if not heures:
        return f"À {nom}, le soleil ne se lève ou ne se couche pas {quand}."
    maintenant = datetime.datetime.now().hour * 60 + datetime.datetime.now().minute if d == datetime.date.today() else None
    morceaux = []
    if lever:
        verbe = "s'est levé" if maintenant is not None and maintenant > heures[0] else "se lève" if d >= datetime.date.today() else "s'était levé"
        morceaux.append(f"le soleil {verbe} vers {_heure_dite(heures[0])}")
    if coucher:
        verbe = "s'est couché" if maintenant is not None and maintenant > heures[1] else "se couche" if d >= datetime.date.today() else "s'était couché"
        morceaux.append(f"{'il' if lever else 'le soleil'} {verbe} vers {_heure_dite(heures[1])}")
    return f"À {nom}, {quand}, " + " et ".join(morceaux) + "."


_SYNODIQUE = 29.530588853
_PHASES = [(1.85, "nouvelle lune"), (5.54, "premier croissant"), (9.22, "premier quartier"),
           (12.91, "lune gibbeuse croissante"), (16.61, "pleine lune"), (20.30, "lune gibbeuse décroissante"),
           (23.99, "dernier quartier"), (27.68, "dernier croissant"), (99, "nouvelle lune")]


def _age_lune(moment=None):
    """Âge de la lune en jours depuis la dernière nouvelle lune (valeur moyenne : à un jour près)."""
    moment = moment or datetime.datetime.now(datetime.timezone.utc)
    reference = datetime.datetime(2000, 1, 6, 18, 14, tzinfo=datetime.timezone.utc)
    return ((moment - reference).total_seconds() / 86400) % _SYNODIQUE


def _lune(s):
    if not re.search(r"\blune\b", s):
        return None
    age = _age_lune()
    m = re.search(r"\bprochaine (pleine|nouvelle) lune\b|\bquand (?:est|sera) la (?:prochaine )?(pleine|nouvelle) lune\b", s)
    if m:
        cible = 14.765 if (m.group(1) or m.group(2)) == "pleine" else 0.0
        reste = (cible - age) % _SYNODIQUE
        nom_phase = f"{m.group(1) or m.group(2)} lune"
        if reste < 1 or reste > _SYNODIQUE - 1:
            return f"C'est la {nom_phase} aujourd'hui, à un jour près."
        d = datetime.date.today() + datetime.timedelta(days=round(reste))
        return f"La prochaine {nom_phase} sera vers le {_date_longue(d)}, dans environ {round(reste)} jours."
    if re.search(r"\b(?:phase|quelle lune|quelle est la lune|lune (?:ce soir|aujourd'hui|en ce moment)|age (?:de|a) la lune|"
                 r"quel age a la lune|c'est la pleine lune|est[- ]ce la pleine lune)\b", s):
        phase = next(nom for limite, nom in _PHASES if age < limite)
        eclairee = round((1 - math.cos(2 * math.pi * age / _SYNODIQUE)) / 2 * 100)
        return f"Phase de la lune aujourd'hui : {phase}, environ {eclairee} pour cent éclairée (à un jour près)."
    return None


# ---------- Météo plus fine (Open-Meteo, comme la météo de base) ----------

_CIEL = {0: "ciel dégagé", 1: "ciel peu nuageux", 2: "ciel partiellement nuageux", 3: "ciel couvert",
         45: "brouillard", 48: "brouillard givrant", 51: "bruine légère", 53: "bruine", 55: "bruine forte",
         56: "bruine verglaçante", 57: "bruine verglaçante", 61: "pluie faible", 63: "pluie", 65: "forte pluie",
         66: "pluie verglaçante", 67: "pluie verglaçante", 71: "neige faible", 73: "neige", 75: "fortes chutes de neige",
         77: "neige en grains", 80: "averses", 81: "averses", 82: "fortes averses", 85: "averses de neige",
         86: "fortes averses de neige", 95: "orages", 96: "orages avec grêle", 99: "orages avec grêle"}
_MOT_METEO = re.compile(r"\b(?:pleuvoir|pleut|pleuvra|parapluie|impermeable|pluie|neiger|neige|neigera|orage|orages|"
                        r"vent|rafales?|temperature|degres|froid|chaud|frais|ressenti|dehors|il fait combien|meteo|quel temps|temps (?:fait|qu'il)|"
                        r"previsions?)\b")
_MOMENTS = {"apres-midi": (15, "cet après-midi", "demain après-midi"), "matin": (8, "ce matin", "demain matin"),
            "midi": (12, "à midi", "demain midi"), "soir": (21, "ce soir", "demain soir")}


def _jour_cible(s):
    """Nombre de jours à partir d'aujourd'hui, et comment le dire ; None si la demande vise plusieurs jours."""
    if re.search(r"\bapres[- ]demain\b", s):
        return 2, "Après-demain"
    if re.search(r"\bdemain\b", s):
        return 1, "Demain"
    aujourdhui = datetime.date.today()
    for i, nom in enumerate(_JOURS_SANS):
        if re.search(r"\b" + nom + r"\b", s):
            ecart = (i - aujourdhui.weekday()) % 7
            return ecart, ("Aujourd'hui" if ecart == 0 else _maj(nom))
    return 0, "Aujourd'hui"


def _meteo(s, brut):
    if not _MOT_METEO.search(s) or re.search(r"\b(?:ouvre|lance|cherche|recherche|site|page|rappelle|minuteur|reveil|musique)\b", s):
        return None
    pluie = re.search(r"\b(?:pleuvoir|pleut|pleuvra|parapluie|impermeable|risque de pluie|de la pluie|neiger|neigera|orage|orages)\b", s)
    vent = re.search(r"\b(?:vent|rafales?)\b", s)
    temp = re.search(r"\b(?:temperature|ressenti|dehors|exterieur|il fait combien|fait[- ]il (?:froid|chaud|frais|doux|bon))\b", s) \
        and not re.search(r"\b(?:meteo|quel temps|chauffage|clim|climatisation|pc|ordinateur|processeur|cpu|piece|salon|chambre)\b", s)
    semaine = re.search(r"\b(?:semaine|week[- ]?end)\b", s) and re.search(r"\b(?:meteo|temps|previsions?|pluie|pleuvoir)\b", s)
    moment = next((k for k in _MOMENTS if re.search(r"\b" + k.replace("-", "[- ]") + r"\b", s)), None) \
        if re.search(r"\b(?:meteo|quel temps|temps (?:fait|qu'il)|pleuvoir|pleut|froid|chaud)\b", s) else None
    jour_precis = re.search(r"\b(?:" + "|".join(_JOURS_SANS) + r")\b", s) and re.search(r"\b(?:meteo|quel temps|temps)\b", s)
    if not (pluie or vent or temp or semaine or moment or jour_precis):
        return None
    if semaine and re.search(r"\bsemaine prochaine\b", s):
        return None                                   # au-delà des 7 jours prévus : pour Claude
    import jarvis_commandes as c
    ville = None
    m = re.search(r"\b(?:à|a|au|aux)\s+([A-ZÀ-Ý][\wÀ-ÿ'\-]*(?:[ \-][A-ZÀ-Ýa-zà-ÿ'\-]+){0,3})", brut.strip(" .!?"))
    if m:
        ville = re.split(r"\s+(?:demain|après|apres|aujourd|ce|cet|cette|ce soir|samedi|dimanche|lundi|mardi|mercredi|jeudi|"
                         r"vendredi|s'il|stp|pour|dehors)\b", m.group(1))[0].strip()
    try:
        lieu = c._lieu(ville)
        if lieu is None:
            return None
        nom, lat, lon = lieu
        d = c._json("https://api.open-meteo.com/v1/forecast?" f"latitude={lat}&longitude={lon}"
                    "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m,wind_gusts_10m"
                    "&hourly=temperature_2m,weather_code,precipitation_probability"
                    "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                    "precipitation_sum,snowfall_sum,wind_speed_10m_max,wind_gusts_10m_max"
                    "&timezone=auto&forecast_days=7")
    except Exception:
        return "Je n'arrive pas à joindre le service météo pour le moment. Réessaie dans un instant."
    q, jours = d["daily"], d["daily"]["time"]

    def val(cle, i):
        v = q[cle][i] if i < len(q[cle]) else None
        return v

    def jour_nom(i):
        return JOURS[datetime.date.fromisoformat(jours[i]).weekday()]

    if semaine:
        if re.search(r"\bweek[- ]?end\b", s):
            indices = [i for i in range(len(jours)) if datetime.date.fromisoformat(jours[i]).weekday() >= 5]
            debut = "Ce week-end"
        else:
            indices = list(range(len(jours)))
            debut = "Cette semaine"
        if not indices:
            return None
        parties = []
        for i in indices:
            ciel = _CIEL.get(val("weather_code", i), "temps variable")
            lib = "aujourd'hui" if i == 0 else "demain" if i == 1 else jour_nom(i)
            parties.append(f"{lib} {ciel}, de {c._arrondi(val('temperature_2m_min', i))} à "
                           f"{c._arrondi(val('temperature_2m_max', i))} degrés")
        pire = max(indices, key=lambda i: val("precipitation_probability_max", i) or 0)
        probabilite = val("precipitation_probability_max", pire) or 0
        nom_pire = "aujourd'hui" if pire == 0 else "demain" if pire == 1 else jour_nom(pire)
        fin = (f" Le jour le plus pluvieux : {nom_pire}, "
               f"avec {c._arrondi(probabilite)} pour cent de risque de pluie.") if probabilite >= 50 else ""
        return f"{debut} à {nom} : " + " ; ".join(parties) + "." + fin
    n, quand = _jour_cible(s)
    if n >= len(jours):
        return None
    if moment:
        heure, ce, demain = _MOMENTS[moment]
        if n == 1 and "demain" not in ce:
            ce = demain
        elif n > 1:
            ce = f"{jour_nom(n)} {moment}"
        cle = f"{jours[n]}T{heure:02d}:00"
        try:
            i = d["hourly"]["time"].index(cle)
        except ValueError:
            return None
        pp = d["hourly"]["precipitation_probability"][i]
        reponse = (f"{_maj(ce)} à {nom}, vers {heure} heures : {_CIEL.get(d['hourly']['weather_code'][i], 'temps variable')}, "
                   f"{c._arrondi(d['hourly']['temperature_2m'][i])} degrés")
        return reponse + (f". Risque de pluie de {c._arrondi(pp)} pour cent." if pp is not None else ".")
    cur = d["current"]
    if pluie:
        neige = re.search(r"\bneig", s)
        orage = re.search(r"\borage", s)
        if neige:
            cm = val("snowfall_sum", n) or 0
            return (f"{quand} à {nom}, oui, de la neige est prévue : environ {_p.dire_nombre(round(cm, 1))} centimètres."
                    if cm >= 0.1 else f"{quand} à {nom}, aucune neige n'est prévue.")
        if orage:
            code = val("weather_code", n)
            return (f"{quand} à {nom}, oui, des orages sont prévus." if code in (95, 96, 99)
                    else f"{quand} à {nom}, aucun orage n'est prévu.")
        pp = val("precipitation_probability_max", n)
        if pp is None:
            return "Je n'ai pas de prévision de pluie pour ce jour."
        mm = val("precipitation_sum", n) or 0
        cumul = f", environ {_p.dire_nombre(round(mm, 1))} millimètres" if mm >= 0.5 else ""
        verdict = "oui, il devrait pleuvoir" if pp >= 60 else "il pourrait pleuvoir" if pp >= 30 else "non, peu de risque de pluie"
        if re.search(r"\b(?:parapluie|impermeable)\b", s):
            conseil = ("Oui, prends un parapluie. " if pp >= 40 else "Pas besoin de parapluie. ") if not _vous() \
                else ("Oui, prenez un parapluie. " if pp >= 40 else "Pas besoin de parapluie. ")
            return f"{conseil}{quand} à {nom}, risque de pluie de {c._arrondi(pp)} pour cent{cumul}."
        return f"{quand} à {nom}, {verdict} : risque de pluie de {c._arrondi(pp)} pour cent{cumul}."
    if vent:
        if n == 0:
            v, r = cur["wind_speed_10m"], cur.get("wind_gusts_10m")
        else:
            v, r = val("wind_speed_10m_max", n), val("wind_gusts_10m_max", n)
        force = "faible" if v < 20 else "modéré" if v < 40 else "assez fort" if v < 60 else "fort"
        rafales = f", avec des rafales jusqu'à {c._arrondi(r)} kilomètres heure" if r and r - v >= 10 else ""
        return (f"{quand} à {nom}, le vent est {force} : {c._arrondi(v)} kilomètres heure{rafales}."
                if n == 0 else f"{quand} à {nom}, le vent sera {force}, jusqu'à {c._arrondi(v)} kilomètres heure{rafales}.")
    if n == 0 and (temp or jour_precis is None):
        t, r = cur["temperature_2m"], cur["apparent_temperature"]
        ressenti = r if r is not None else t
        qualite = ("très froid" if ressenti < 0 else "froid" if ressenti < 8 else "frais" if ressenti < 15
                   else "doux" if ressenti < 22 else "agréable" if ressenti < 28 else "chaud" if ressenti < 35 else "très chaud")
        suite = f", ressenti {c._arrondi(r)}" if r is not None and abs(r - t) >= 2 else ""
        return f"À {nom}, il fait {c._arrondi(t)} degrés{suite}. C'est {qualite}."
    ciel = _CIEL.get(val("weather_code", n), "temps variable")
    pp = val("precipitation_probability_max", n)
    return (f"{quand} à {nom} : {ciel}, de {c._arrondi(val('temperature_2m_min', n))} à "
            f"{c._arrondi(val('temperature_2m_max', n))} degrés."
            + (f" Risque de pluie de {c._arrondi(pp)} pour cent." if pp is not None else ""))


# ---------- Conversation ----------

_BLAGUES = [
    "Pourquoi les plongeurs plongent-ils toujours en arrière ? Parce que sinon, ils tombent dans le bateau.",
    "Que dit un geek quand il a froid ? Il ferme les fenêtres... enfin, les Windows.",
    "Quel est le comble pour un électricien ? De ne pas être au courant.",
    "Pourquoi l'ordinateur est-il allé chez le médecin ? Parce qu'il avait un virus.",
    "Quel est le comble pour un jardinier ? De raconter des salades.",
    "Que dit un zéro à un huit ? Sympa, ta ceinture !",
    "Pourquoi les astronautes n'ont-ils pas d'amis dans l'espace ? Parce qu'il manque d'atmosphère.",
    "Quel est l'animal le plus rapide ? Le pou, parce qu'il est toujours en tête.",
    "Pourquoi le livre de maths est-il triste ? Parce qu'il a trop de problèmes.",
    "Que fait une fraise sur un cheval ? Tagada, tagada.",
    "Comment appelle-t-on un boomerang qui ne revient pas ? Un bâton.",
    "Quel est le comble pour un cordonnier ? D'être mal chaussé.",
    "Que dit-on à un ordinateur qui fait des siennes ? Redémarre, ça ira mieux.",
    "Pourquoi les oiseaux volent-ils vers le sud ? Parce que c'est trop loin à pied.",
    "Que dit une maman kangourou quand il pleut ? Vite, tous les enfants dans la poche !",
    "Quel est le comble pour un boulanger ? De se faire rouler dans la farine.",
    "Qu'est-ce qui est jaune et qui attend ? Jonathan.",
    "Quel est le comble pour un informaticien ? De retrouver ses fichiers dans la corbeille.",
]
_DEVINETTES = [
    ("Je suis toujours devant toi, mais on ne peut jamais me voir. Qui suis-je ?", "L'avenir."),
    ("Plus on m'enlève, plus je deviens grand. Qui suis-je ?", "Un trou."),
    ("J'ai des villes mais pas de maisons, des montagnes mais pas d'arbres, de l'eau mais pas de poissons. Qui suis-je ?",
     "Une carte."),
    ("Je parle sans bouche et j'entends sans oreilles. Qui suis-je ?", "Un écho."),
    ("Qu'est-ce qui a des touches mais n'ouvre aucune porte ?", "Un clavier, ou un piano."),
    ("Plus il y en a, moins on voit. Qu'est-ce que c'est ?", "L'obscurité."),
    ("Qu'est-ce qui monte et qui descend sans bouger ?", "Un escalier."),
    ("Qu'est-ce qui appartient à toi, mais que les autres utilisent plus que toi ?", "Ton prénom."),
    ("Qu'est-ce qui est plein de trous et qui pourtant retient l'eau ?", "Une éponge."),
    ("Qu'est-ce qui court sans jamais avoir de jambes ?", "L'eau d'une rivière."),
]
_PROVERBES = [
    "Petit à petit, l'oiseau fait son nid.", "Qui ne tente rien n'a rien.", "Rome ne s'est pas faite en un jour.",
    "Les petits ruisseaux font les grandes rivières.", "Mieux vaut tard que jamais.", "Après la pluie, le beau temps.",
    "Tout vient à point à qui sait attendre.", "La nuit porte conseil.", "Aide-toi, le ciel t'aidera.",
    "C'est en forgeant qu'on devient forgeron.", "L'union fait la force.", "Chaque chose en son temps.",
    "Qui sème le vent récolte la tempête.", "Pierre qui roule n'amasse pas mousse.",
]
_FAITS = [
    "Le miel, bien conservé, ne se périme pratiquement pas : il contient très peu d'eau et il est naturellement acide.",
    "Les pieuvres ont trois cœurs : deux pour leurs branchies, un pour le reste du corps.",
    "Sur Vénus, un jour dure plus longtemps qu'une année : elle tourne sur elle-même en environ 243 jours terrestres, "
    "et fait le tour du Soleil en environ 225.",
    "Les wombats produisent des crottes en forme de cubes.",
    "La tour Eiffel peut s'allonger de quelques centimètres en été, à cause de la dilatation du métal.",
    "Une journée sur Mars dure environ 24 heures et 40 minutes.",
    "Le bananier n'est pas un arbre : c'est une immense plante herbacée.",
    "Les abeilles indiquent à leurs compagnes où trouver les fleurs en dansant.",
    "Les girafes ont sept vertèbres dans le cou, comme les humains, mais beaucoup plus longues.",
    "Le plus petit os du corps humain est l'étrier, dans l'oreille : il mesure environ trois millimètres.",
    "La lumière du Soleil met environ huit minutes et vingt secondes pour arriver jusqu'à la Terre.",
    "La peau de l'ours polaire est noire : sa fourrure paraît blanche, mais elle est en réalité translucide.",
]
_COMPLIMENTS = [
    "Tu as une qualité rare : tu te poses des questions et tu cherches à comprendre. C'est très bien.",
    "Tu prends le temps de faire les choses sérieusement, et ça se voit.",
    "Tu as le sens du détail, c'est une vraie force.",
    "Tu es persévérant : quand quelque chose ne marche pas, tu insistes jusqu'à ce que ça marche.",
    "Ta curiosité est contagieuse. Continue comme ça.",
]
_deja = {"blague": [], "devinette": [], "proverbe": [], "fait": [], "compliment": []}
_devinette_en_cours = {"reponse": None, "moment": 0.0}


def _piocher(nom, liste):
    """Un élément au hasard, sans répéter avant d'avoir tout vu."""
    vus = _deja[nom]
    restants = [i for i in range(len(liste)) if i not in vus] or list(range(len(liste)))
    if len(restants) == len(liste):
        vus.clear()
    i = random.choice(restants)
    vus.append(i)
    return liste[i]


def _compliment_vous(texte):
    return texte.replace("Tu as", "Vous avez").replace("Tu prends", "Vous prenez").replace("tu te poses", "vous vous posez") \
        .replace("tu cherches", "vous cherchez").replace("Tu es", "Vous êtes").replace("tu insistes", "vous insistez") \
        .replace("quand quelque chose ne marche pas, tu", "quand quelque chose ne marche pas, vous") \
        .replace("Ta curiosité", "Votre curiosité").replace("Continue", "Continuez")


def _conversation(s):
    if _devinette_en_cours["reponse"] and time.time() - _devinette_en_cours["moment"] < 300 \
            and re.fullmatch(r"(?:la reponse|donne[- ]moi la reponse|dis[- ]moi la reponse|je donne ma langue au chat|"
                             r"je (?:ne )?sais pas|aucune idee|j'abandonne|alors|et la reponse)", s):
        reponse = _devinette_en_cours["reponse"]
        _devinette_en_cours["reponse"] = None
        return f"La réponse : {reponse}"
    if re.fullmatch(r"(?:merci(?: beaucoup| bien| infiniment| mille fois)?(?: jarvis)?|je te remercie|je vous remercie|"
                    r"(?:ok|super|parfait|top|genial|d'accord|tres bien) merci|c'est gentil)", s):
        return random.choice(["Avec plaisir.", "De rien.", "Pas de souci."]) if not _vous() \
            else random.choice(["Avec plaisir.", "Je vous en prie.", "De rien."])
    if re.fullmatch(r"(?:comment (?:ca va|vas[- ]tu|tu vas|allez[- ]vous)|ca va(?: bien)?|tu vas bien|vous allez bien|"
                    r"ca va jarvis|la forme)(?: aujourd'hui| ce matin| ce soir)?", s):
        return _tu("Très bien, merci ! Et toi ?", "Très bien, merci ! Et vous ?")
    if re.fullmatch(r"(?:qui es[- ]tu|tu es qui|tu es quoi|qui est jarvis|c'est quoi jarvis|qu'est[- ]ce que tu es|"
                    r"comment tu t'appelles|comment t'appelles[- ]tu|tu t'appelles comment|quel est ton nom|presente[- ]toi|"
                    r"presentez[- ]vous|comment vous appelez[- ]vous|qui etes[- ]vous)", s):
        return ("Je m'appelle Jarvis, ton assistant vocal. Je tourne sur ton PC : je réponds à l'heure, à la météo, aux "
                "calculs, je gère tes minuteurs, tes rappels, ta musique, tes applications et tes fenêtres. "
                "Dis : qu'est-ce que tu sais faire, pour en savoir plus.") if not _vous() else (
                "Je m'appelle Jarvis, votre assistant vocal. Je tourne sur votre PC : je réponds à l'heure, à la météo, "
                "aux calculs, je gère vos minuteurs, vos rappels, votre musique, vos applications et vos fenêtres. "
                "Dites : qu'est-ce que tu sais faire, pour en savoir plus.")
    if re.fullmatch(r"bonne (?:journee|soiree|apres[- ]midi|matinee|semaine|fin de journee|week[- ]end)(?: jarvis)?", s):
        return _tu("Merci, à toi aussi !", "Merci, à vous aussi !")
    if re.fullmatch(r"(?:tu es la|t'es la|tu m'entends|tu m'entend|tu m'ecoutes|est[- ]ce que tu m'entends|"
                    r"tu es toujours la|allo|vous m'entendez|vous etes la)", s):
        return _tu("Oui, je suis là et je t'écoute.", "Oui, je suis là et je vous écoute.")
    if re.fullmatch(r"(?:tu peux m'aider|peux[- ]tu m'aider|pouvez[- ]vous m'aider|j'ai besoin d'aide|j'ai besoin de toi)", s):
        return _tu("Bien sûr. Dis-moi ce dont tu as besoin, ou dis : qu'est-ce que tu sais faire, pour connaître mes commandes.",
                   "Bien sûr. Dites-moi ce dont vous avez besoin, ou dites : qu'est-ce que tu sais faire, pour connaître mes commandes.")
    if re.fullmatch(r"(?:je m'ennuie|je m'ennuis|y a rien a faire|j'ai rien a faire|je m'embete)", s):
        return _tu("Je peux te raconter une blague, te poser une devinette, te dire un fait amusant ou te mettre de la "
                   "musique. Dis par exemple : raconte-moi une blague.",
                   "Je peux vous raconter une blague, vous poser une devinette, vous dire un fait amusant ou vous mettre de "
                   "la musique. Dites par exemple : raconte-moi une blague.")
    if re.fullmatch(r"(?:tu es|t'es|vous etes) (?:genial|super|top|formidable|incroyable|excellent|le meilleur|trop fort|fort)|"
                    r"bravo|bien joue|felicitations|bon travail|beau travail|c'est super", s):
        return "Merci, ça me fait plaisir !"
    if re.fullmatch(r"(?:fais[- ]moi|dis[- ]moi|donne[- ]moi) un compliment|complimente[- ]moi", s):
        c = _piocher("compliment", _COMPLIMENTS)
        return _compliment_vous(c) if _vous() else c
    if re.search(r"\b(?:raconte|dis|fais|donne|sors|balance)\b(?:-moi| moi)? (?:une |une petite |une bonne )?"
                 r"(?:blague|histoire drole|plaisanterie|vanne)\b|^fais[- ]moi rire$|^une blague$|\b(?:connais|sais)[- ]tu une blague\b", s):
        return _piocher("blague", _BLAGUES)
    if re.search(r"\b(?:raconte|dis|pose|donne|fais)\b(?:-moi| moi)? (?:une |une petite |une autre )?devinette\b|^une devinette$|"
                 r"\bune autre devinette\b", s):
        question, reponse = _piocher("devinette", _DEVINETTES)
        _devinette_en_cours.update(reponse=reponse, moment=time.time())
        return question + " Dis : la réponse, quand tu veux que je te la donne." if not _vous() \
            else question + " Dites : la réponse, quand vous voulez que je vous la donne."
    if re.search(r"\b(?:dis|donne|raconte)\b(?:-moi| moi)? (?:un|une) (?:proverbe|citation|dicton|pensee|phrase (?:motivante|inspirante)|"
                 r"bonne parole)\b", s):
        return "Voici un proverbe : " + _piocher("proverbe", _PROVERBES)
    if re.search(r"\b(?:dis|donne|raconte)\b(?:-moi| moi)? (?:un |une )?(?:fait amusant|fait insolite|anecdote|truc surprenant|"
                 r"chose surprenante|info insolite|fait curieux)\b|\bsais[- ]tu que\b|^(?:surprends[- ]moi|apprends[- ]moi quelque chose)$", s):
        return _piocher("fait", _FAITS)
    if re.fullmatch(r"(?:dis|raconte)(?:-moi| moi) quelque chose", s):
        return random.choice([_piocher("fait", _FAITS), _piocher("blague", _BLAGUES), "Voici un proverbe : " + _piocher("proverbe", _PROVERBES)])
    m = re.fullmatch(r"epelle(?:-moi| moi)? (?:le mot )?([a-z][a-z'-]{1,24})", s)
    if m:
        lettres = [("tiret" if x == "-" else "apostrophe" if x == "'" else x.upper()) for x in m.group(1)]
        return f"{m.group(1)} s'écrit : " + ", ".join(lettres) + "."
    return None


# ---------- Point d'entrée ----------

def calendrier(t):
    """Les questions de date et de calendrier (aussi appelées avant le raccourci « quelle date »)."""
    try:
        import jarvis_savoir
        t = jarvis_savoir.annees_en_chiffres(t)   # « deux mille trente » -> 2030
    except Exception:
        pass
    return _calendrier(_phrase(t))


def commande(t, brut=""):
    """La réponse à dire, ou None si la demande n'est pas une de celles-ci."""
    s = _phrase(t)
    if not s or len(s.split()) > 22:
        return None
    reponse = _hasard(s, _phrase(t, accents=True))
    if reponse:
        return reponse
    for fonction in (_conversation, _calendrier, _soleil, _lune, _systeme):
        reponse = fonction(s)
        if reponse:
            return reponse
    return _meteo(s, brut or t)


# ---------- Sans Claude : chercher la réponse sur Google (après un « oui ») ----------

_QUESTION = re.compile(r"^(?:qui|que|quoi|qu'|quel|quelle|quels|quelles|combien|comment|pourquoi|ou |quand|lequel|laquelle|"
                       r"est[- ]ce|c'est (?:quoi|qui|quand|ou|combien)|definition|definis|explique|dis[- ]moi (?:qui|ce que|comment|"
                       r"pourquoi|ou|quand|combien|quel)|parle[- ]moi de|traduis|comment dit[- ]on|synonyme|contraire|conjugue|"
                       r"(?:fais|fait) (?:une |moi une )?recherche|cherche|recherche|trouve[- ]moi|ou (?:est|se trouve)|"
                       r"y a[- ]t[- ]il|(?:donne|donne[- ]moi) (?:les |des |la |le )?(?:nouvelles|infos|actualites|resultats?|score))")
_ACTU = re.compile(r"\b(?:actualites?|nouvelles|infos du jour|informations du jour|a la une)\b")


def _claude_installe():
    try:
        import jarvis_claude_reglages
        return bool(jarvis_claude_reglages.installe())
    except Exception:
        return False


def sans_claude(t, brut, demander_confirmation, ouvrir):
    """Sans Claude : une question que Jarvis ne sait pas traiter lui-même. Il propose de la chercher sur Google
    (ou les actualités) et ne le fait qu'après un « oui » (un bruit mal compris n'ouvre donc pas le navigateur)."""
    if _claude_installe():
        return None
    try:
        import jarvis_enfant
        import jarvis_extras
        if jarvis_enfant.actif() or jarvis_extras.invite():
            return None
    except Exception:
        pass
    try:                                    # un autre assistant est branché : c'est lui qui répondra, pas Google
        import jarvis_assistants
        if jarvis_assistants.utilisable_maintenant():
            return None
    except Exception:
        pass
    s = _phrase(t)
    mots = s.split()
    if len(mots) < 3 or len(mots) > 25 or not _QUESTION.match(s):
        return None
    if re.fullmatch(r"(?:qu'est[- ]ce qu'il y a|qu'est[- ]ce que (?:c'est|tu dis|tu fais|ca)|comment (?:ca va|vas[- ]tu)|c'est quoi ca|quoi de neuf)", s):
        return None
    if _ACTU.search(s):
        adresse, quoi = "https://news.google.com/?hl=fr&gl=FR&ceid=FR:fr", "les actualités"
    else:
        question = re.sub(r"^\W*(?:jarvis\W+)?(?:fais(?:-moi)? une recherche (?:sur |a propos de |pour )?|cherche(?:-moi)?(?: sur (?:internet|google))? |"
                          r"recherche |trouve-moi )", "", brut.strip(" .!?«»\"'"), flags=re.I) or brut
        adresse, quoi = "https://www.google.com/search?q=" + urllib.parse.quote(question.strip()), "cette question"

    def lancer():
        ouvrir(adresse)
        return "Je lance la recherche." if quoi == "cette question" else "J'ouvre les actualités."

    demander_confirmation(lancer)
    if _vous():
        return f"Je n'ai pas Claude sur ce PC pour vous répondre moi-même. Voulez-vous que je cherche {quoi} sur Google ? Dites oui."
    return f"Je n'ai pas Claude sur ce PC pour te répondre moi-même. Veux-tu que je cherche {quoi} sur Google ? Dis oui."
