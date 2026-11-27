# -*- coding: utf-8 -*-
"""
JARVIS - un éventail plus large de réponses entièrement locales (sans Claude, sans autre assistant, instantané).

  - pourcentages et argent : « 15 % de 80 », « 80 euros moins 20 pour cent », prix TTC et hors taxes, « 30 sur 120, ça fait
    quel pourcentage », « partage 90 euros en 4 », pourboire ;
  - calculs : « 2 puissance 10 », tables de multiplication, nombre premier, pair ou impair, diviseurs, PGCD et PPCM,
    factorielle, arrondi, moyenne, fractions simples ;
  - nombres : chiffres romains dans les deux sens, un nombre écrit en lettres, zéros d'un million ;
  - dates : jours restants dans l'année ou dans le mois, trimestre, week-end, semaine, changement d'heure,
    nombre de jours entre deux dates ;
  - départements : numéro, nom, région, préfecture (liste officielle, jarvis_departements.py) ;
  - culture générale qui ne change pas (planètes, polygones, sports, symboles chimiques, records connus…) ;
  - conversions de durées, d'octets et de cuillères ; lettres d'un mot, mot à l'envers ; quelques politesses.

commande(t, brut) renvoie la phrase à dire, ou None si la demande ne concerne pas ce module : elle continue alors son
chemin (les autres réponses locales, puis Claude ou un autre assistant). Les motifs sont volontairement stricts : en cas
de doute, ce module se tait. Rien ici n'agit sur le PC.
"""

import datetime
import math
import random
import re
from fractions import Fraction

import jarvis_savoir

_NOM_MOIS = jarvis_savoir._NOM_MOIS
_MOIS = jarvis_savoir._MOIS
_JOURS = jarvis_savoir._JOURS
_RE_MOIS = jarvis_savoir._RE_MOIS
_N = r"(\d+(?:[.,]\d+)?|[a-z][a-z\- ]{1,40}?)"          # un nombre en chiffres, ou en lettres (vérifié ensuite)
_DEBUT = r"^(?:dis[- ]moi |donne[- ]moi |tu peux me dire |peux[- ]tu me dire |est[- ]ce que tu sais |sais[- ]tu )?"


def _phrase(t):
    t = (t or "").replace("%", " pour cent ").replace("€", " euros ")
    s = jarvis_savoir._phrase(t)
    s = re.sub(r"\bpourcents?\b", "pour cent", s)
    return re.sub(r"\s+", " ", s).strip()


def _n(texte):
    return jarvis_savoir._nombre((texte or "").strip(" ,.?"))


def _dire(x):
    return jarvis_savoir._dire(round(float(x), 6))


def _euros(x):
    x = round(float(x) + 1e-9, 2)
    if abs(x - round(x)) < 0.005:
        return f"{_dire(round(x))} euro" + ("s" if abs(x) >= 2 else "")
    entier, centimes = int(x), int(round((x - int(x)) * 100))
    return f"{_dire(entier)} euro{'s' if entier >= 2 else ''} {centimes:02d}"


def _entier(x, maxi=10 ** 12):
    return x is not None and float(x).is_integer() and 0 <= x <= maxi


# ---------------------------------------------------------------- pourcentages et argent

def _pourcentages(s):
    m = re.search(rf"\b(?:reduction|remise|rabais|solde) de {_N} pour cent sur {_N} euros?\b", s) \
        or None
    if m:
        p, a = _n(m.group(1)), _n(m.group(2))
    else:
        m = re.search(rf"{_N} euros? (?:avec |moins |a )(?:une (?:reduction|remise) de |un rabais de )?{_N} pour cent"
                      rf"(?: de (?:reduction|remise|rabais))?$", s)
        a, p = (_n(m.group(1)), _n(m.group(2))) if m else (None, None)
        if m and re.search(r" a [^ ]+ pour cent$", s) and not re.search(r"reduction|remise|rabais|solde", s):
            m = None                                   # « 60 euros à 10 pour cent » : pas forcément une réduction
    if m and a is not None and p is not None and 0 <= p <= 100:
        return (f"Avec {_dire(p)} pour cent de réduction, {_euros(a)} passent à {_euros(a * (1 - p / 100))} : "
                f"tu économises {_euros(a * p / 100)}.")
    m = re.search(rf"{_N} euros? plus {_N} pour cent$", s)
    if m and _n(m.group(1)) is not None and _n(m.group(2)) is not None:
        a, p = _n(m.group(1)), _n(m.group(2))
        return f"{_euros(a)} plus {_dire(p)} pour cent, ça fait {_euros(a * (1 + p / 100))}."
    # TVA
    if re.search(r"\b(ttc|hors taxes?|ht|tva)\b", s):
        taux = 20.0
        mt = re.search(rf"\btva (?:a|de) {_N} pour cent", s)
        if mt and _n(mt.group(1)) is not None:
            taux = _n(mt.group(1))
        m = re.search(rf"{_N} euros? (?:hors taxes?|ht)\b", s) or re.search(rf"\bprix ttc (?:de|pour) {_N} euros?", s)
        if m and _n(m.group(1)) is not None and re.search(r"\bttc\b", s):
            a = _n(m.group(1))
            return f"Avec une TVA à {_dire(taux)} pour cent, {_euros(a)} hors taxes font {_euros(a * (1 + taux / 100))} TTC."
        m = re.search(rf"{_N} euros? ttc\b", s) or re.search(rf"\bprix (?:hors taxes?|ht) (?:de|pour) {_N} euros?", s)
        if m and _n(m.group(1)) is not None and re.search(r"\b(hors taxes?|ht)\b", s):
            a = _n(m.group(1))
            return f"Avec une TVA à {_dire(taux)} pour cent, {_euros(a)} TTC font {_euros(a / (1 + taux / 100))} hors taxes."
    m = re.search(rf"\bpourboire (?:de {_N} pour cent )?(?:pour|sur) {_N} euros?(?: a {_N} pour cent)?", s)
    if m:
        p = _n(m.group(1)) if m.group(1) else (_n(m.group(3)) if m.group(3) else 10.0)
        a = _n(m.group(2))
        if a is not None and p is not None:
            return f"Un pourboire de {_dire(p)} pour cent sur {_euros(a)}, ça fait {_euros(a * p / 100)}."
    m = re.search(rf"\bquel pourcentage (?:represente(?:nt)?|fait|font) {_N} sur {_N}$", s) \
        or re.search(rf"^{_N} sur {_N},? (?:ca fait|c'est|represente) quel pourcentage$", s)
    if m and _n(m.group(1)) is not None and _n(m.group(2)):
        a, b = _n(m.group(1)), _n(m.group(2))
        return f"{_dire(a)} sur {_dire(b)}, ça fait {_dire(round(100 * a / b, 2))} pour cent."
    m = re.search(rf"\b(?:partage|partager|divise|diviser|repartis) {_N} euros? (?:en|entre|par) {_N}(?: personnes?| parts?)?$", s)
    if m and _n(m.group(1)) is not None and _n(m.group(2)):
        a, b = _n(m.group(1)), _n(m.group(2))
        return f"{_euros(a)} partagés en {_dire(b)}, ça fait {_euros(a / b)} chacun."
    m = re.search(rf"^(?:combien (?:font|fait|vaut|vale?nt) |calcule |quel est |c'est quoi |ca fait combien )?"
                  rf"{_N} pour cent d[eu'] ?{_N}(?: euros?)?$", s)
    if m and _n(m.group(1)) is not None and _n(m.group(2)) is not None:
        p, a = _n(m.group(1)), _n(m.group(2))
        return f"{_dire(p)} pour cent de {_dire(a)}, ça fait {_dire(round(a * p / 100, 4))}."
    return None


# ---------------------------------------------------------------- calculs

def _diviseur(n):
    """Le plus petit diviseur de n supérieur à 1 (n lui-même si n est premier)."""
    if n % 2 == 0:
        return 2
    d = 3
    while d * d <= n:
        if n % d == 0:
            return d
        d += 2
    return n


_FRACTIONS = {"demi": 2, "demie": 2, "moitie": 2, "tiers": 3, "quart": 4, "quarts": 4, "cinquieme": 5, "cinquiemes": 5,
              "sixieme": 6, "sixiemes": 6, "septieme": 7, "septiemes": 7, "huitieme": 8, "huitiemes": 8,
              "neuvieme": 9, "neuviemes": 9, "dixieme": 10, "dixiemes": 10}
_NOMS_FRACTION = {2: ("demi", "demis"), 3: ("tiers", "tiers"), 4: ("quart", "quarts"), 5: ("cinquième", "cinquièmes"),
                  6: ("sixième", "sixièmes"), 7: ("septième", "septièmes"), 8: ("huitième", "huitièmes"),
                  9: ("neuvième", "neuvièmes"), 10: ("dixième", "dixièmes"), 12: ("douzième", "douzièmes")}


def _fraction(texte):
    texte = texte.strip()
    m = re.fullmatch(rf"{_N} sur {_N}", texte)
    if m and _entier(_n(m.group(1))) and _entier(_n(m.group(2))) and _n(m.group(2)):
        return Fraction(int(_n(m.group(1))), int(_n(m.group(2))))
    m = re.fullmatch(r"(.+?) (" + "|".join(_FRACTIONS) + ")", texte)
    if m and _entier(_n(m.group(1))):
        return Fraction(int(_n(m.group(1))), _FRACTIONS[m.group(2)])
    return None


def _dire_fraction(f):
    if f.denominator == 1:
        return _dire(f.numerator)
    noms = _NOMS_FRACTION.get(f.denominator)
    nom = (noms[0] if abs(f.numerator) == 1 else noms[1]) if noms else None
    texte = f"{_dire(f.numerator)} {nom}" if nom else f"{_dire(f.numerator)} sur {_dire(f.denominator)}"
    return f"{texte}, soit environ {_dire(round(float(f), 3))}"


def _maths(s):
    m = re.search(rf"^(?:combien (?:font|fait|vaut) )?{_N} (?:puissance|exposant) {_N}$", s)
    if m and _n(m.group(1)) is not None and _n(m.group(2)) is not None:
        a, b = _n(m.group(1)), _n(m.group(2))
        if abs(b) <= 200 and abs(a) <= 10 ** 6:
            try:
                r = a ** b
                if abs(r) < 10 ** 15:
                    return f"Ça fait {_dire(r)}."
            except (OverflowError, ZeroDivisionError):
                pass
        return None
    m = re.search(rf"\btable (?:de multiplication )?(?:de |du |des ){_N}$", s)
    if m and _entier(_n(m.group(1)), 1000) and not re.search(r"\b(nuit|chevet|salon|cuisine|jardin|ping)\b", s):
        n = int(_n(m.group(1)))
        return f"Table de {n} : " + " ; ".join(f"{n} fois {k}, {n * k}" for k in range(1, 11)) + "."
    m = re.search(rf"(?:est[- ]ce que |est[- ]ce qu')?{_N},? (?:est[- ]il|est[- ]ce|est)(?: un)?(?: nombre)? premier\b", s)
    if m and _entier(_n(m.group(1))):
        n = int(_n(m.group(1)))
        if n < 2:
            return f"Non, {n} n'est pas un nombre premier."
        d = _diviseur(n)
        return f"Oui, {n} est un nombre premier." if d == n else f"Non, {n} n'est pas premier : il est divisible par {d}."
    m = re.search(rf"(?:est[- ]ce que |est[- ]ce qu')?{_N},? (?:est[- ]il|est[- ]ce|est)(?: un)?(?: nombre)? (pair|impair)\b", s)
    if m and _entier(_n(m.group(1))):
        n = int(_n(m.group(1)))
        return f"{n} est {'pair' if n % 2 == 0 else 'impair'}."
    m = re.search(rf"\bdiviseurs d[eu'] ?{_N}$", s)
    if m and _entier(_n(m.group(1)), 10 ** 7) and _n(m.group(1)) >= 1:
        n = int(_n(m.group(1)))
        petits = [d for d in range(1, int(n ** 0.5) + 1) if n % d == 0]
        tous = sorted(set(petits + [n // d for d in petits]))
        return f"Les diviseurs de {n} sont : " + ", ".join(str(d) for d in tous) + "."
    m = re.search(rf"\b(pgcd|ppcm|plus grand (?:commun )?diviseur(?: commun)?|plus petit (?:commun )?multiple(?: commun)?) "
                  rf"(?:de |d'|entre ){_N} et (?:de |d')?{_N}$", s)
    if m and _entier(_n(m.group(2))) and _entier(_n(m.group(3))) and _n(m.group(2)) and _n(m.group(3)):
        a, b = int(_n(m.group(2))), int(_n(m.group(3)))
        if m.group(1).startswith(("pgcd", "plus grand")):
            return f"Le PGCD de {a} et {b} est {math.gcd(a, b)}."
        return f"Le PPCM de {a} et {b} est {a * b // math.gcd(a, b)}."
    m = re.search(rf"\bfactorielle (?:de |d'){_N}$", s)
    if m and _entier(_n(m.group(1)), 20):
        return f"Factorielle {int(_n(m.group(1)))}, ça fait {math.factorial(int(_n(m.group(1))))}."
    m = re.search(rf"\barrondi[sr]?(?:e|ez)? {_N} (?:a|au) (.+)$", s)
    if m and _n(m.group(1)) is not None:
        x, quoi = _n(m.group(1)), m.group(2)
        md = re.fullmatch(rf"{_N} (?:decimales?|chiffres? apres la virgule)", quoi)
        decimales = int(_n(md.group(1))) if md and _entier(_n(md.group(1)), 10) else \
            {"l'unite": 0, "l'entier": 0, "dixieme": 1, "centieme": 2, "millieme": 3}.get(quoi.replace("pres", "").strip())
        if decimales is None:
            return None
        r = float(f"{x:.{decimales}f}") if decimales else float(math.floor(x + 0.5))
        return f"Ça fait {_dire(r)}."
    m = re.search(r"\bmoyenne (?:de|des nombres|entre) (.+)$", s)
    if m:
        morceaux = [x for x in re.split(r"\s*(?:,| et | )\s*", m.group(1)) if x]
        valeurs = [_n(x) for x in morceaux]
        if len(valeurs) >= 2 and all(v is not None for v in valeurs):
            return f"La moyenne est {_dire(round(sum(valeurs) / len(valeurs), 3))}."
        return None
    m = re.search(r"^(?:combien (?:font|fait) )?(.+?) (plus|moins|fois|divise par) (.+)$", s)
    if m:
        a, b = _fraction(m.group(1)), _fraction(m.group(3))
        if a is not None and b is not None and (a.denominator > 1 or b.denominator > 1):
            try:
                r = {"plus": a + b, "moins": a - b, "fois": a * b, "divise par": a / b}[m.group(2)]
            except ZeroDivisionError:
                return None
            return f"Ça fait {_dire_fraction(r)}."
    return None


# ---------------------------------------------------------------- nombres : chiffres romains, lettres, zéros

_ROMAINS = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
            (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
_UNITES = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze",
           "treize", "quatorze", "quinze", "seize", "dix-sept", "dix-huit", "dix-neuf"]
_DIZAINES = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}


def en_romain(n):
    sortie = ""
    for valeur, lettres in _ROMAINS:
        while n >= valeur:
            sortie += lettres
            n -= valeur
    return sortie


def de_romain(texte):
    """La valeur d'un nombre romain bien écrit (« XIV » -> 14), ou None."""
    valeurs = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    texte = texte.upper()
    if not texte or any(c not in valeurs for c in texte):
        return None
    total = 0
    for i, c in enumerate(texte):
        v = valeurs[c]
        total += -v if i + 1 < len(texte) and valeurs[texte[i + 1]] > v else v
    return total if 0 < total < 4000 and en_romain(total) == texte else None


def _moins_de_cent(n):
    if n < 20:
        return _UNITES[n]
    if n < 70:
        d, u = n // 10 * 10, n % 10
        if u == 0:
            return _DIZAINES[d]
        return _DIZAINES[d] + (" et un" if u == 1 else "-" + _UNITES[u])
    if n < 80:
        return "soixante" + (" et onze" if n == 71 else "-" + _UNITES[n - 60])
    if n == 80:
        return "quatre-vingts"
    return "quatre-vingt-" + _UNITES[n - 80]


def _moins_de_mille(n, fin=True):
    c, r = n // 100, n % 100
    if c == 0:
        texte = _moins_de_cent(r)
    else:
        texte = ("cent" if c == 1 else _UNITES[c] + " cent") + ("s" if c > 1 and r == 0 and fin else "")
        if r:
            texte += " " + _moins_de_cent(r)
    if not fin and texte.endswith("quatre-vingts"):
        texte = texte[:-1]                                # « quatre-vingt mille »
    return texte


def en_lettres(n):
    """Un entier de 0 à 999 999 999 999 écrit en toutes lettres."""
    if n == 0:
        return "zéro"
    morceaux = []
    for valeur, nom in ((10 ** 9, "milliard"), (10 ** 6, "million")):
        q, n = divmod(n, valeur)
        if q:
            morceaux.append(_moins_de_mille(q) + " " + nom + ("s" if q > 1 else ""))
    q, n = divmod(n, 1000)
    if q:
        morceaux.append("mille" if q == 1 else _moins_de_mille(q, fin=False) + " mille")
    if n:
        morceaux.append(_moins_de_mille(n))
    return " ".join(morceaux)


def _nombres(s):
    m = re.search(rf"^(?:ecris |ecrire |convertis |c'est quoi |comment (?:s'ecrit|ecrire|on ecrit) )?{_N} en (?:chiffres?|nombres?|lettres?) romaine?s?$", s)
    if m and _entier(_n(m.group(1)), 3999) and _n(m.group(1)) >= 1 and de_romain(m.group(1).strip()) is None:
        n = int(_n(m.group(1)))
        return f"{n} en chiffres romains s'écrit {', '.join(en_romain(n))}."
    m = re.search(r"^(?:que vaut|combien vaut|c'est quoi|convertis|combien fait|ca fait combien) (?:le chiffre romain |le nombre romain )?"
                  r"([ivxlcdm]{1,15})(?: en chiffres?(?: romains?| arabes?)?| en nombres?)?$", s)
    if m and de_romain(m.group(1)) is not None and ("romain" in s or (len(m.group(1)) > 2 and s.startswith(("que vaut", "combien vaut")))):
        return f"{', '.join(m.group(1).upper())}, ça vaut {de_romain(m.group(1))}."
    m = re.search(rf"^(?:ecris |ecrire |comment (?:s'ecrit|ecrire|on ecrit|ca s'ecrit) |epelle ){_N} en (?:toutes )?lettres$", s)
    if m and _entier(_n(m.group(1)), 999999999999):
        n = int(_n(m.group(1)))
        return f"{n} s'écrit : {en_lettres(n)}."
    m = re.search(r"\bcombien (?:de |d'|y a[- ]t[- ]il de )zeros (?:dans|a|il y a dans|pour) (?:un |une |1 )?(cent|mille|million|milliard|billion)$", s)
    if m:
        nb = {"cent": 2, "mille": 3, "million": 6, "milliard": 9, "billion": 12}[m.group(1)]
        return f"{ {'cent': 'Cent', 'mille': 'Mille'}.get(m.group(1), 'Un ' + m.group(1)) } s'écrit avec {nb} zéros."
    return None


# ---------------------------------------------------------------- dates

def _date_longue(d, annee=True):
    jour = "premier" if d.day == 1 else str(d.day)
    return f"{_JOURS[d.weekday()]} {jour} {_NOM_MOIS[d.month - 1]}" + (f" {d.year}" if annee else "")


def _dernier_dimanche(annee, mois):
    d = datetime.date(annee, mois + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() + 1) % 7)


def _une_date(texte, aujourdhui):
    m = re.fullmatch(rf"(?:le )?(1er|premier|\d{{1,2}}) ({_RE_MOIS})(?: (\d{{4}}))?", texte.strip())
    if not m:
        return None, False
    jour = 1 if m.group(1) in ("1er", "premier") else int(m.group(1))
    try:
        return datetime.date(int(m.group(3)) if m.group(3) else aujourdhui.year, _MOIS[m.group(2)], jour), bool(m.group(3))
    except ValueError:
        return None, False


def entre_deux_dates(t, aujourdhui=None):
    """« combien de jours entre le 1er janvier et le 14 juillet » : à appeler AVANT les autres réponses de calendrier,
    qui ne voient qu'une seule des deux dates."""
    s = _phrase(jarvis_savoir.annees_en_chiffres(t))
    aujourdhui = aujourdhui or datetime.date.today()
    m = re.search(r"\bcombien (?:de |y a[- ]t[- ]il de |il y a de )?(jours|semaines|mois) (?:y a[- ]t[- ]il |il y a )?"
                  r"entre (.+?) et (.+)$", s)
    if not m:
        return None
    a, annee_a = _une_date(m.group(2), aujourdhui)
    b, annee_b = _une_date(m.group(3), aujourdhui)
    if not a or not b:
        return None
    if b < a and not annee_b:
        b = b.replace(year=b.year + 1) if not (b.month == 2 and b.day == 29) else None
        if b is None:
            return None
    jours = abs((b - a).days)
    debut, fin = min(a, b), max(a, b)
    if m.group(1) == "semaines":
        detail = f"{jours // 7} semaines" + (f" et {jours % 7} jour{'s' if jours % 7 > 1 else ''}" if jours % 7 else "")
    elif m.group(1) == "mois":
        mois = (fin.year - debut.year) * 12 + fin.month - debut.month - (1 if fin.day < debut.day else 0)
        detail = f"{mois} mois" + ("" if fin.day == debut.day else f" (et {jours} jours en tout)")
    else:
        detail = f"{jours} jour{'s' if jours > 1 else ''}"
    return f"Entre le {_date_longue(debut)} et le {_date_longue(fin)}, il y a {detail}."


def _dates(s, aujourdhui):
    if re.search(r"\bcombien (?:de |d')?jours? (?:il )?(?:reste(?:nt)?(?:[- ]t[- ]ils?)? |y a[- ]t[- ]il |)?(?:dans|avant (?:la fin de )?|jusqu'a (?:la fin de )?|d'ici (?:la fin de )?)"
                 r"(?:l'annee|cette annee|le nouvel an|le jour de l'an|le premier janvier|le 1er janvier)", s) \
            or re.search(r"\bcombien (?:de |d')?jours? (?:il )?reste(?:nt)?(?:[- ]t[- ]ils?)? (?:dans|avant la fin de|jusqu'a la fin de) (?:l'annee|cette annee)", s):
        n = (datetime.date(aujourdhui.year, 12, 31) - aujourdhui).days
        if n == 0:
            return "C'est le dernier jour de l'année : nous sommes le 31 décembre."
        return f"Il reste {n} jour{'s' if n > 1 else ''} avant la fin de l'année, le 31 décembre {aujourdhui.year}."
    if re.search(r"\bcombien (?:de |d')?jours? (?:il )?(?:reste(?:nt)?(?:[- ]t[- ]ils?)? )?(?:dans|avant la fin d[eu]|jusqu'a la fin d[eu]|d'ici la fin d[eu]) ?(?:le |ce )?mois$", s):
        fin = (aujourdhui.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        n = (fin - aujourdhui).days
        if n == 0:
            return "C'est le dernier jour du mois."
        return f"Il reste {n} jour{'s' if n > 1 else ''} avant la fin du mois, le {_date_longue(fin, False)}."
    if re.search(r"\b(?:quel|on est (?:a|au|dans) quel|nous sommes (?:a|au|dans) quel) trimestre\b", s):
        t = (aujourdhui.month - 1) // 3
        noms = ("janvier à mars", "avril à juin", "juillet à septembre", "octobre à décembre")
        return f"Nous sommes au {('premier', 'deuxième', 'troisième', 'quatrième')[t]} trimestre {aujourdhui.year} ({noms[t]})."
    if re.search(r"\b(?:dans combien de (?:jours|temps)|c'est quand|quand (?:est|commence|arrive)|combien de jours avant) (?:est )?(?:le |ce )?(?:prochain )?week[- ]?end\b", s):
        j = aujourdhui.weekday()
        if j >= 5:
            return "C'est le week-end !" if j == 5 else "C'est le week-end, plus qu'aujourd'hui avant lundi."
        n = 5 - j
        return f"Le week-end commence dans {n} jour{'s' if n > 1 else ''}, samedi." if n > 1 else "Le week-end commence demain."
    if re.search(r"^(?:on est|nous sommes|c'est|on est en|nous sommes en) (?:a |en )?quelle semaine(?: de l'annee)?$|^quelle semaine (?:on est|sommes[- ]nous|est[- ]on)$", s):
        annee, semaine, _ = aujourdhui.isocalendar()
        lundi = aujourdhui - datetime.timedelta(days=aujourdhui.weekday())
        return (f"Nous sommes en semaine {semaine}, du {_date_longue(lundi, False)} au "
                f"{_date_longue(lundi + datetime.timedelta(days=6), False)}.")
    if re.search(r"\bchangement d'heure\b|\bquand (?:passe[- ]t[- ]on|on passe|est[- ]ce qu'on passe) a l'heure d'(?:ete|hiver)\b|"
                 r"\b(?:prochain )?passage a l'heure d'(?:ete|hiver)\b", s) and re.search(r"\b(quand|quel|quelle|date|c'est)\b", s):
        candidats = []
        for annee in (aujourdhui.year, aujourdhui.year + 1):
            candidats.append((_dernier_dimanche(annee, 3), "on avance d'une heure (passage à l'heure d'été)"))
            candidats.append((_dernier_dimanche(annee, 10), "on recule d'une heure (passage à l'heure d'hiver)"))
        if "ete" in s.split("heure d'")[-1][:4] and "heure d'" in s:
            candidats = [c for c in candidats if "été" in c[1]]
        elif "hiver" in s:
            candidats = [c for c in candidats if "hiver" in c[1]]
        jour, quoi = min(c for c in candidats if c[0] >= aujourdhui)
        veille = jour - datetime.timedelta(days=1)
        return (f"Le prochain changement d'heure a lieu dans la nuit du {_date_longue(veille, False)} au "
                f"{_date_longue(jour)} : {quoi}.")
    return None


# ---------------------------------------------------------------- départements

_departements = None


def _simple(nom):
    return re.sub(r"[^a-z0-9]+", " ", jarvis_savoir._sans_accents(nom.lower())).strip()


def _liste_departements():
    global _departements
    if _departements is None:
        try:
            import jarvis_departements
            _departements = [(c, n, r, p, _simple(n)) for c, n, r, p in jarvis_departements.DEPARTEMENTS]
        except Exception:
            _departements = []
    return _departements


def _departement_cite(s):
    """Le département dont le nom figure dans la phrase (le nom le plus long l'emporte : « tarn et garonne » avant « tarn »)."""
    propre = " " + _simple(s) + " "
    trouves = [d for d in _liste_departements() if f" {d[4]} " in propre]
    return max(trouves, key=lambda d: len(d[4])) if trouves else None


def _departement_de_la_ville(nom):
    """« dans quel département est Toulouse » : l'annuaire officiel des communes (en ligne, 4 secondes au plus).
    Sans réponse du service : None, la demande continue son chemin."""
    import json
    import urllib.parse
    import urllib.request
    try:
        url = ("https://geo.api.gouv.fr/communes?nom=" + urllib.parse.quote(_simple(nom))
               + "&fields=nom,departement,region,population&boost=population&limit=8")
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Jarvis"}), timeout=4) as r:
            communes = json.load(r)
    except Exception:
        return None
    exactes = [c for c in communes if _simple(c.get("nom", "")) == _simple(nom) and c.get("departement")]
    if not exactes:
        return None
    exactes.sort(key=lambda c: -(c.get("population") or 0))
    c = exactes[0]
    texte = (f"{c['nom']} est dans le département {c['departement']['nom']} ({c['departement']['code']}), "
             f"en région {(c.get('region') or {}).get('nom', '')}.")
    if len(exactes) > 1:
        autres = sorted({x["departement"]["nom"] for x in exactes[1:]} - {c["departement"]["nom"]})
        if autres:
            texte += f" Il existe aussi une commune de ce nom dans : {', '.join(autres[:4])}."
    return texte


def _departements_fr(s):
    deps = _liste_departements()
    if not deps:
        return None
    # « quel est le numéro de la Haute-Garonne » : le mot « département » n'est pas dit, mais un département est nommé
    m = re.search(r"^(?:quel est |c'est quoi |donne[- ]moi |dis[- ]moi )?le numero (?:du departement )?(?:de la |du |de l'|des |de |d')(.+)$", s)
    if m:
        d = _departement_cite(m.group(1))
        if d and _simple(m.group(1)) in (d[4], "departement " + d[4]):
            return f"{d[1]}, c'est le département {d[0]}, en région {d[2]}."
    if not re.search(r"\b(departements?|prefectures?|chef[- ]lieu|chefs[- ]lieux|regions?)\b", s):
        return None
    m = re.search(r"^(?:dans |c'est dans )?quel departement (?:est|se trouve|se situe|il y a) (?:la ville de |la commune de )?([a-z' \-]{2,40})$", s)
    if m:
        return _departement_de_la_ville(m.group(1))
    if re.search(r"\bcombien (?:de |d'|y a[- ]t[- ]il de )departements\b", s) and re.search(r"\b(france|francais|pays|y a)\b", s):
        outre_mer = sum(1 for d in deps if len(d[0]) == 3)
        return f"La France compte {len(deps)} départements : {len(deps) - outre_mer} en métropole et {outre_mer} en outre-mer."
    if re.search(r"\bcombien (?:de |d'|y a[- ]t[- ]il de )regions\b", s) and re.search(r"\b(france|francais|pays|y a)\b", s):
        regions = sorted({d[2] for d in deps})
        outre_mer = len({d[2] for d in deps if len(d[0]) == 3})
        return f"La France compte {len(regions)} régions : {len(regions) - outre_mer} en métropole et {outre_mer} en outre-mer."
    m = re.search(r"\bdepartements? (?:de la region |de |d'|du |en |de l')(.+)$", s)
    if m and re.search(r"\b(quels|liste|cite|donne|nomme)\b", s):
        voulu = _simple(m.group(1))
        for region in sorted({d[2] for d in deps}):
            if _simple(region) == voulu:
                noms = [d[1] for d in deps if d[2] == region]
                return f"Les départements de la région {region} sont : " + ", ".join(noms) + "."
        return None
    m = re.search(r"\b(?:departement|region pour le departement|prefecture du departement) (?:numero |n )?(\d{1,3}|2a|2b)\b", s) \
        or re.search(r"^c'est quel departement le (\d{2,3}|2a|2b)$", s)
    if m:
        code = m.group(1).upper().zfill(2)
        d = next((x for x in deps if x[0] == code), None)
        if not d:
            return f"Je ne connais pas de département numéro {m.group(1)}."
        return f"Le {d[0]}, c'est le département {d[1]}, en région {d[2]}. Sa préfecture est {d[3]}."
    d = _departement_cite(s)
    if not d:
        return None
    if re.search(r"\b(prefecture|chef[- ]lieu)\b", s):
        return f"La préfecture du département {d[1]} ({d[0]}) est {d[3]}."
    if re.search(r"\b(?:dans |a )?quelle region\b", s):
        return f"Le département {d[1]} ({d[0]}) est en région {d[2]}."
    if re.search(r"\b(numero|quel numero|quel est le numero|c'est quel numero)\b", s) or re.search(r"\bquel est le departement\b", s):
        return f"{d[1]}, c'est le département {d[0]}, en région {d[2]}."
    return None


# ---------------------------------------------------------------- culture générale qui ne change pas

_SYMBOLES = {"hydrogene": "H", "helium": "He", "lithium": "Li", "carbone": "C", "azote": "N", "oxygene": "O", "fluor": "F",
             "neon": "Ne", "sodium": "Na", "magnesium": "Mg", "aluminium": "Al", "silicium": "Si", "phosphore": "P",
             "soufre": "S", "chlore": "Cl", "argon": "Ar", "potassium": "K", "calcium": "Ca", "titane": "Ti", "fer": "Fe",
             "nickel": "Ni", "cuivre": "Cu", "zinc": "Zn", "argent": "Ag", "etain": "Sn", "iode": "I", "platine": "Pt",
             "or": "Au", "mercure": "Hg", "plomb": "Pb", "uranium": "U"}
_NOM_ELEMENT = {"hydrogene": "l'hydrogène", "helium": "l'hélium", "oxygene": "l'oxygène", "neon": "le néon",
                "magnesium": "le magnésium", "etain": "l'étain", "or": "l'or", "argent": "l'argent", "azote": "l'azote",
                "aluminium": "l'aluminium", "iode": "l'iode", "uranium": "l'uranium", "argon": "l'argon"}
_POLYGONES = {"triangle": 3, "carre": 4, "rectangle": 4, "losange": 4, "pentagone": 5, "hexagone": 6, "heptagone": 7,
              "octogone": 8, "enneagone": 9, "decagone": 10, "dodecagone": 12}
_EQUIPES = (("foot", "football", 11), ("football", "football", 11), ("rugby a quinze", "rugby à quinze", 15),
            ("rugby a 15", "rugby à quinze", 15), ("rugby a sept", "rugby à sept", 7), ("rugby a 7", "rugby à sept", 7),
            ("rugby a treize", "rugby à treize", 13), ("rugby a 13", "rugby à treize", 13), ("rugby", "rugby à quinze", 15),
            ("basket", "basket", 5), ("basketball", "basket", 5), ("handball", "handball", 7), ("hand", "handball", 7),
            ("volley", "volley", 6), ("volleyball", "volley", 6), ("hockey sur glace", "hockey sur glace", 6),
            ("water polo", "water-polo", 7), ("baseball", "baseball", 9))
_FAITS = (
    (r"\bcombien (?:de |y a[- ]t[- ]il de )planetes\b", "Le système solaire compte 8 planètes : Mercure, Vénus, la Terre, Mars, Jupiter, Saturne, Uranus et Neptune."),
    (r"\bplus grande planete(?: du systeme solaire)?$", "La plus grande planète du système solaire est Jupiter."),
    (r"\bplus petite planete(?: du systeme solaire)?$", "La plus petite planète du système solaire est Mercure."),
    (r"\bplanete la plus proche du soleil\b", "La planète la plus proche du Soleil est Mercure."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )continents\b", "On compte six continents quand on regroupe les Amériques : l'Afrique, l'Amérique, l'Antarctique, l'Asie, l'Europe et l'Océanie. D'autres découpages en comptent sept."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de |d')oceans\b", "On compte cinq océans : Pacifique, Atlantique, Indien, Austral et Arctique."),
    (r"\bplus grand ocean(?: du monde| de la terre| au monde)?$", "Le plus grand océan est l'océan Pacifique."),
    (r"\bvitesse de la lumiere\b", "La vitesse de la lumière dans le vide est d'environ 299 792 kilomètres par seconde, soit près de 300 000 kilomètres par seconde."),
    (r"\bvitesse du son\b", "Dans l'air, le son se déplace à environ 340 mètres par seconde, soit environ 1 225 kilomètres par heure."),
    (r"\b(?:a quelle temperature|a combien de degres) (?:l'eau bout|bout l'eau)\b|\btemperature d'ebullition de l'eau\b", "L'eau bout à 100 degrés Celsius, à la pression du niveau de la mer."),
    (r"\b(?:a quelle temperature|a combien de degres) (?:l'eau gele|gele l'eau)\b|\btemperature de (?:congelation|solidification) de l'eau\b", "L'eau gèle à 0 degré Celsius."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )lettres (?:dans|a|compte) l'alphabet\b", "L'alphabet français compte 26 lettres : 6 voyelles et 20 consonnes."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )voyelles (?:dans|a|compte) l'alphabet\b", "L'alphabet compte 6 voyelles : A, E, I, O, U et Y."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )touches (?:sur|a|dans|compte) un piano\b", "Un piano a 88 touches : 52 blanches et 36 noires."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )cordes (?:sur|a|dans|compte) une guitare\b", "Une guitare classique a 6 cordes."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )cordes (?:sur|a|dans|compte) un violon\b", "Un violon a 4 cordes."),
    (r"\bcouleurs de l'arc[- ]en[- ]ciel\b", "L'arc-en-ciel a sept couleurs : rouge, orange, jaune, vert, bleu, indigo et violet."),
    (r"\bcombien (?:d'|de |y a[- ]t[- ]il d')os\b.*\b(corps|humain|squelette)\b", "Le squelette d'un adulte compte 206 os."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )dents\b.*\b(adulte|humain|bouche|on a)\b", "Un adulte a 32 dents, dents de sagesse comprises."),
    (r"\bformule (?:chimique )?de l'eau\b", "La formule de l'eau est H2O : deux atomes d'hydrogène et un atome d'oxygène."),
    (r"\bformule (?:chimique )?du (?:sel|sel de table)\b", "La formule du sel de table est NaCl : le chlorure de sodium."),
    (r"\bformule (?:chimique )?du (?:gaz carbonique|dioxyde de carbone)\b", "La formule du dioxyde de carbone est CO2."),
    (r"\bplus haute montagne (?:du monde|de la terre)\b|\bplus haut sommet (?:du monde|de la terre)\b", "La plus haute montagne du monde est l'Everest, dans l'Himalaya : environ 8 849 mètres."),
    (r"\bplus haute montagne (?:de france|d'europe de l'ouest|des alpes)\b|\bplus haut sommet (?:de france|des alpes)\b", "Le plus haut sommet de France et des Alpes est le mont Blanc, à environ 4 806 mètres."),
    (r"\bplus long fleuve de france\b", "Le plus long fleuve de France est la Loire : un peu plus de 1 000 kilomètres."),
    (r"\bplus grand pays(?: du monde| de la terre| au monde)?$", "Le plus grand pays du monde par sa superficie est la Russie."),
    (r"\bplus petit pays(?: du monde| de la terre| au monde)?$", "Le plus petit pays du monde est le Vatican."),
    (r"\bplus grand desert(?: chaud)?(?: du monde| de la terre| au monde)?$", "Le plus grand désert chaud du monde est le Sahara. Le plus grand désert tout court est l'Antarctique."),
    (r"\bdistance (?:de la |entre la )?terre (?:a|et) la lune\b|\ba quelle distance est la lune\b", "La Lune est à environ 384 400 kilomètres de la Terre, en moyenne."),
    (r"\bdistance (?:de la |entre la )?terre (?:au|et le) soleil\b|\ba quelle distance est le soleil\b", "Le Soleil est à environ 150 millions de kilomètres de la Terre."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )cartes (?:dans|a|compte) un jeu\b", "Un jeu de cartes classique compte 52 cartes, sans les jokers. Un jeu de belote en compte 32."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )cases (?:sur|dans|a|compte) un (?:echiquier|jeu d'echecs)\b", "Un échiquier compte 64 cases : 8 sur 8."),
    (r"\bcouleurs du drapeau (?:francais|de la france)\b", "Le drapeau français est bleu, blanc et rouge."),
    (r"\bhymne (?:national )?(?:francais|de la france)\b", "L'hymne national français est La Marseillaise."),
    (r"\bdevise de la (?:france|republique)\b", "La devise de la République française est : Liberté, Égalité, Fraternité."),
    (r"\b(?:combien vaut|que vaut|quelle est la valeur de|c'est quoi) (?:le nombre )?pi\b", "Pi vaut environ 3,14159."),
    (r"\b(?:combien vaut|que vaut|quelle est la valeur du|c'est quoi le) nombre d'or\b", "Le nombre d'or vaut environ 1,618."),
    (r"\btemperature (?:normale )?du corps(?: humain)?\b", "La température normale du corps humain est d'environ 37 degrés Celsius."),
    (r"\bcombien (?:de temps )?dure un match de foot(?:ball)?\b", "Un match de football dure 90 minutes : deux mi-temps de 45 minutes, plus le temps additionnel."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )jours (?:dans|a|compte) une annee bissextile\b", "Une année bissextile compte 366 jours."),
    (r"\bcombien (?:de |y a[- ]t[- ]il de )(?:semaines) (?:dans|a|compte) (?:une|un) an(?:nee)?\b", "Une année compte 52 semaines, plus un jour, ou deux les années bissextiles."),
)


def _culture(s):
    m = re.search(r"\bcombien (?:de |d'|y a[- ]t[- ]il de )cotes (?:a |possede |y a[- ]t[- ]il (?:dans|sur) |dans |pour )?(?:un |une |le |l')?([a-z]+)$", s)
    if m and m.group(1) in _POLYGONES:
        return f"Un {m.group(1).replace('carre', 'carré').replace('enneagone', 'ennéagone').replace('decagone', 'décagone').replace('dodecagone', 'dodécagone')} a {_POLYGONES[m.group(1)]} côtés."
    m = re.search(r"\bcombien (?:de |y a[- ]t[- ]il de )joueurs\b.*\b(?:equipe|match|terrain)\b.*?\b(?:de |du |au |a )(.+)$", s) \
        or re.search(r"\bcombien (?:de |y a[- ]t[- ]il de )joueurs (?:au|en|dans le|dans une equipe de|a) (.+)$", s)
    if m:
        sport = m.group(1).strip()
        for cle, nom, nombre in _EQUIPES:
            if sport == cle:
                return f"Au {nom}, une équipe a {nombre} joueurs sur le terrain."
    m = re.search(r"\bsymbole (?:chimique )?(?:de l'|du |de la |de |d')([a-z]+)$", s)
    if m and m.group(1) in _SYMBOLES:
        nom = _NOM_ELEMENT.get(m.group(1), "le " + m.group(1))
        return f"Le symbole chimique de {nom} est {', '.join(_SYMBOLES[m.group(1)])}."
    for motif, reponse in _FAITS:
        if re.search(motif, s):
            return reponse
    return None


# ---------------------------------------------------------------- conversions : durées, octets, cuillères

_DUREES = {"seconde": 1, "minute": 60, "heure": 3600, "jour": 86400, "semaine": 604800}
_OCTETS = {"octet": 0, "kilooctet": 1, "kilo octet": 1, "ko": 1, "megaoctet": 2, "mega octet": 2, "mo": 2, "mega": 2,
           "gigaoctet": 3, "giga octet": 3, "go": 3, "giga": 3, "teraoctet": 4, "tera octet": 4, "to": 4, "tera": 4}
_NOM_OCTETS = ("octet", "kilooctet", "mégaoctet", "gigaoctet", "téraoctet")


def _pluriel(x, mot):
    return mot + ("s" if abs(x) >= 2 else "")


def _conversions(s):
    m = re.search(rf"^(?:combien (?:font|fait|vaut) |convertis |ca fait combien )?{_N} (seconde|minute|heure|jour|semaine)s? "
                  rf"(?:en |ca fait combien d[e'] ?|c'est combien d[e'] ?)(seconde|minute|heure|jour|semaine)s?$", s)
    if m and _n(m.group(1)) is not None and m.group(2) != m.group(3):
        x = _n(m.group(1))
        secondes = x * _DUREES[m.group(2)]
        r = secondes / _DUREES[m.group(3)]
        texte = f"{_dire(x)} {_pluriel(x, m.group(2))}, ça fait {_dire(round(r, 3))} {_pluriel(r, m.group(3))}"
        if m.group(3) == "heure" and m.group(2) == "minute" and not float(r).is_integer() and float(x).is_integer():
            h, mn = divmod(int(x), 60)
            texte += f", soit {h} heure{'s' if h > 1 else ''} {mn:02d}" if h else ""
        return texte + "."
    unites = "|".join(sorted(_OCTETS, key=len, reverse=True))
    m = re.search(rf"^(?:combien (?:font|fait|vaut) |convertis |ca fait combien )?{_N} ({unites})s? en ({unites})s?$", s) \
        or re.search(rf"^combien (?:de |d')({unites})s? (?:dans|font|fait|pour|il y a dans) {_N} ({unites})s?$", s)
    if m:
        if m.re.pattern.startswith("^combien (?:de"):
            x, de, vers = _n(m.group(2)), m.group(3), m.group(1)
        else:
            x, de, vers = _n(m.group(1)), m.group(2), m.group(3)
        if x is not None and _OCTETS[de] != _OCTETS[vers]:
            r = x * 1000.0 ** (_OCTETS[de] - _OCTETS[vers])
            suite = ""
            if _OCTETS[de] - _OCTETS[vers] == 1:
                suite = f" Windows, lui, compte par 1024 et en affiche {_dire(x * 1024)}."
            return (f"{_dire(x)} {_pluriel(x, _NOM_OCTETS[_OCTETS[de]])}, ça fait {_dire(r)} "
                    f"{_pluriel(r, _NOM_OCTETS[_OCTETS[vers]])}.{suite}")
    m = re.search(r"\bcombien (?:de |d')(millilitres|ml|centilitres|cl) (?:dans|fait|font|pour|il y a dans) (?:une |1 )?cuilleree?s? a (soupe|cafe|the)\b", s) \
        or re.search(r"\b(?:une |1 )?cuilleree?s? a (soupe|cafe|the),? (?:ca fait|c'est|en) combien(?: de| en)? (millilitres|ml|centilitres|cl)?", s)
    if m:
        quoi = "soupe" if "soupe" in m.group(0) else "café"
        ml = 15 if quoi == "soupe" else 5
        return f"Une cuillère à {quoi}, c'est environ {ml} millilitres, soit {_dire(ml / 10)} centilitre{'s' if ml >= 20 else ''}."
    return None


# ---------------------------------------------------------------- mots

_ACCENTS = {"é": "E accent aigu", "è": "E accent grave", "ê": "E accent circonflexe", "ë": "E tréma", "à": "A accent grave",
            "â": "A accent circonflexe", "î": "I accent circonflexe", "ï": "I tréma", "ô": "O accent circonflexe",
            "ù": "U accent grave", "û": "U accent circonflexe", "ü": "U tréma", "ç": "C cédille", "œ": "O E liés",
            "-": "trait d'union", "'": "apostrophe"}


def _mot_d_origine(brut, s_mot):
    """Le mot tel qu'il a été dit (avec ses accents), retrouvé dans la phrase d'origine."""
    for mot in re.findall(r"[A-Za-zÀ-ÿœŒ'’\-]+", brut or ""):
        if jarvis_savoir._sans_accents(mot.lower()).replace("’", "'") == s_mot:
            return mot.lower().replace("’", "'")
    return s_mot


def _mots(s, brut):
    m = re.search(r"^(?:comment (?:s'ecrit|ca s'ecrit|on ecrit|ecrire|tu ecris)|orthographe (?:du mot|de)|comment epeler) (?:le mot )?([a-z'\-]{2,30})$", s)
    if m and m.group(1) not in ("ca", "cela", "ton", "mon", "son", "le", "la"):
        mot = _mot_d_origine(brut, m.group(1))
        return f"{mot.capitalize()} s'écrit : " + ", ".join(_ACCENTS.get(c, c.upper()) for c in mot) + "."
    m = re.search(r"\bcombien (?:de |y a[- ]t[- ]il de )lettres (?:dans|a|compte|il y a dans|contient) (?:le mot )([a-z'\-]{1,40})$", s)
    if m:
        mot = _mot_d_origine(brut, m.group(1))
        n = len([c for c in mot if c.isalpha()])
        return f"Le mot {mot} compte {n} lettre{'s' if n > 1 else ''}."
    m = re.search(r"^(?:mets |ecris |dis |epelle )(?:le mot )?([a-z'\-]{2,30}) a l'envers$", s) \
        or re.search(r"^(?:c'est quoi |que donne |ca donne quoi )(?:le mot )?([a-z'\-]{2,30}) a l'envers$", s)
    if m:
        mot = _mot_d_origine(brut, m.group(1))
        return f"{mot.capitalize()} à l'envers, ça donne : {mot[::-1]}. " + ", ".join(_ACCENTS.get(c, c.upper()) for c in mot[::-1]) + "."
    return None


# ---------------------------------------------------------------- politesses

def _politesses(s):
    if re.fullmatch(r"(?:jarvis )?(?:bon appetit)(?: jarvis)?", s):
        return "Merci ! Bon appétit à toi."
    m = re.fullmatch(r"(?:dis|souhaite) (bonjour|bonsoir|bon anniversaire|joyeux anniversaire|bon courage|bravo) a ([a-z\- ]{2,25})", s)
    if m and len(m.group(2).split()) <= 3:
        return f"{m.group(1).capitalize()} {m.group(2).title()} !"
    return None


# ---------------------------------------------------------------- pluriel des noms

_PLURIELS_SPECIAUX = {"oeil": "yeux", "œil": "yeux", "ciel": "cieux", "aieul": "aïeux", "aïeul": "aïeux",
                      "madame": "mesdames", "monsieur": "messieurs", "mademoiselle": "mesdemoiselles",
                      "bonhomme": "bonshommes", "gentilhomme": "gentilshommes"}
_AL_EN_ALS = {"bal", "carnaval", "chacal", "festival", "recital", "regal", "cal", "narval", "choral", "nopal", "ceremonial",
              "serval", "aval", "cantal", "chacal", "gavial", "rorqual"}
_AIL_EN_AUX = {"bail", "corail", "email", "soupirail", "travail", "vantail", "vitrail"}
_OU_EN_OUX = {"bijou", "caillou", "chou", "genou", "hibou", "joujou", "pou"}
_EU_EN_EUS = {"bleu", "pneu", "emeu", "landau", "sarrau", "enfeu"}


def pluriel_nom(mot):
    """Le pluriel d'un nom commun d'un seul mot, selon les règles et leurs exceptions ; None si le mot n'est pas simple."""
    m = mot.lower().strip()
    if not re.fullmatch(r"[a-zàâäçéèêëîïôöùûüÿœæ]{2,30}", m):
        return None
    simple = _simple(m)
    if m in _PLURIELS_SPECIAUX:
        return _PLURIELS_SPECIAUX[m]
    if m[-1] in "sxz":
        return m
    if simple.endswith("al"):
        return m + "s" if simple in _AL_EN_ALS else m[:-2] + "aux"
    if simple.endswith("ail"):
        return m[:-3] + "aux" if simple in _AIL_EN_AUX else m + "s"
    if simple.endswith("ou"):
        return m + "x" if simple in _OU_EN_OUX else m + "s"
    if simple.endswith(("au", "eu")):
        return m + "s" if simple in _EU_EN_EUS else m + "x"
    return m + "s"


def _pluriel_demande(s, brut):
    m = (re.search(r"^(?:quel est |c'est quoi |donne[- ]moi )?le pluriel (?:de |du mot |d')(?:un |une |le |la |l')?([a-z'\-]{2,30})$", s)
         or re.search(r"^(?:comment (?:on ecrit|s'ecrit|ecrire|dit[- ]on) )?(?:un |une |le |la |l')?([a-z\-]{2,30}) au pluriel$", s))
    if not m:
        return None
    mot = _mot_d_origine(brut, m.group(1).split("'")[-1])
    pl = pluriel_nom(mot)
    if not pl:
        return None
    if pl == mot.lower():
        return f"{mot.capitalize()} ne change pas au pluriel : des {pl}."
    return f"Au pluriel, {mot.lower()} devient {pl} : des {pl}."


# ---------------------------------------------------------------- cuisine et pas

# Une tasse américaine (environ 240 ml) : poids habituels des ingrédients courants
_TASSE = {"farine": 125, "sucre": 200, "beurre": 225, "lait": 240, "eau": 240, "huile": 215}


def _cuisine_et_pas(s):
    m = re.search(r"^(?:combien (?:font|fait|de tasses? (?:font|fait|pour)) )?" + _N + r" (?:grammes?|g) de (farine|sucre|beurre|lait|eau|huile)"
                  r" (?:en|ca fait combien de|c'est combien de) tasses?$", s)
    if m:
        g = _n(m.group(1))
        if g:
            t = g / _TASSE[m.group(2)]
            return (f"{_dire(round(g))} grammes de {m.group(2)}, c'est environ {_dire(round(t, 1))} tasse{'s' if t >= 2 else ''} "
                    f"(une tasse américaine de 240 millilitres, soit à peu près {_TASSE[m.group(2)]} grammes de {m.group(2)}).")
    m = re.search(r"^(?:combien (?:de grammes (?:dans|pour|font|fait) |font |fait ))?(une|un|" + _N[1:-1] + r") tasses? de (farine|sucre|beurre|lait|eau|huile)"
                  r"(?: en grammes| ca fait combien de grammes| c'est combien de grammes)?$", s)
    if m and ("gramme" in s or s.startswith("combien")):
        n = 1 if m.group(1) in ("une", "un") else _n(m.group(1))
        if n:
            g = n * _TASSE[m.group(2)]
            return (f"{_dire(n)} tasse{'s' if n >= 2 else ''} de {m.group(2)}, c'est environ {_dire(round(g))} grammes "
                    "(tasse américaine de 240 millilitres).")
    m = re.search(r"^(?:combien (?:font|fait) )?" + _N + r" pas (?:en|ca fait combien de|c'est combien de) (?:kilometres?|km)$", s)
    if m:
        p = _n(m.group(1))
        if p:
            km = p * 0.7 / 1000
            return (f"{_dire(round(p))} pas, c'est environ {_dire(round(km, 1))} kilomètre{'s' if km >= 2 else ''}, "
                    "en comptant un pas d'adulte de 70 centimètres ; selon la taille, le pas va de 60 à 80 centimètres.")
    m = re.search(r"^combien (?:de pas|faut[- ]il de pas) (?:pour|dans|font|fait|y a[- ]t[- ]il dans) " + _N + r" (?:kilometres?|km)$", s) \
        or re.search(r"^combien (?:de pas|faut[- ]il de pas) (?:pour|dans|fait) (un) (?:kilometre|km)$", s)
    if m:
        k = 1 if m.group(1) == "un" else _n(m.group(1))
        if k:
            return (f"Pour {_dire(k)} kilomètre{'s' if k >= 2 else ''}, il faut environ {_dire(round(k * 1000 / 0.7, -1))} pas, "
                    "avec un pas d'adulte de 70 centimètres.")
    return None


# ---------------------------------------------------------------- un mot gentil

_GENTIL = ("Tu es quelqu'un de bien, et ça se voit dans la façon dont tu prends soin des autres.",
           "Tu as plus de courage que tu ne le crois.", "Ta curiosité est une vraie qualité : ne la perds jamais.",
           "Merci d'être là. Les journées sont plus agréables avec toi.", "Tu progresses, même les jours où tu ne le vois pas.",
           "Tu as le droit d'être fier de tout ce que tu as déjà accompli.")
_GENTIL_VOUS = ("Vous êtes quelqu'un de bien, et ça se voit dans la façon dont vous prenez soin des autres.",
                "Vous avez plus de courage que vous ne le croyez.", "Votre curiosité est une vraie qualité : ne la perdez jamais.",
                "Merci d'être là. Les journées sont plus agréables avec vous.",
                "Vous progressez, même les jours où vous ne le voyez pas.",
                "Vous avez le droit d'être fier de tout ce que vous avez déjà accompli.")


def _gentil(s):
    if not re.fullmatch(r"(?:dis[- ]moi |dites[- ]moi )?(?:quelque chose|un mot|une phrase) (?:de )?gentil(?:le)?|"
                        r"(?:fais|faites)[- ]moi un compliment|un compliment|remonte[- ]moi le moral|dis[- ]moi un compliment", s):
        return None
    try:
        import jarvis_local
        vous = jarvis_local._vous()
    except Exception:
        vous = False
    return random.choice(_GENTIL_VOUS if vous else _GENTIL)


# ---------------------------------------------------------------- entrée

def commande(t, brut="", aujourdhui=None):
    """La réponse à dire, ou None si la demande n'est pas l'une de celles de ce module."""
    try:
        s = _phrase(jarvis_savoir.annees_en_chiffres(t))
    except Exception:
        return None
    if not s or len(s) > 160:
        return None
    aujourdhui = aujourdhui or datetime.date.today()
    for fonction in (lambda: _pourcentages(s), lambda: _maths(s), lambda: _nombres(s), lambda: _dates(s, aujourdhui),
                     lambda: _departements_fr(s), lambda: _culture(s), lambda: _conversions(s),
                     lambda: _mots(s, brut or t), lambda: _pluriel_demande(s, brut or t), lambda: _cuisine_et_pas(s),
                     lambda: _gentil(s), lambda: _politesses(s)):
        try:
            reponse = fonction()
        except Exception:
            reponse = None
        if reponse:
            return reponse
    return None
