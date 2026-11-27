# -*- coding: utf-8 -*-
"""
JARVIS - petites réponses de culture pratique, entièrement locales (aucun quota, aucun Internet, instantané).

  - « quel mois sommes-nous », « en quelle année sommes-nous », « quelle saison », « quand commence l'été » ;
  - « quel jour était le 1er janvier 2000 » (une date avec son année) ;
  - « la moitié de 90 », « le double de 45 », « le carré de 12 », « le cube de 3 » ;
  - « combien de secondes dans une heure », « combien de jours dans février 2028 »,
    « combien de centimètres dans 5 pouces », « combien de litres dans un gallon » ;
  - « quel âge a quelqu'un né en 1990 », « quel est le signe du 3 mars » ;
  - « quelle est la capitale du Japon » (une soixantaine de pays, sans risque d'erreur) ;
  - « qui t'a créé », « quel âge as-tu », « combien de mémoire vive j'ai ».
commande(t) renvoie la phrase à dire, ou None si la demande ne concerne pas ce module (elle continue alors son
chemin : Claude ou un autre assistant). Rien ici n'agit sur le PC.
"""

import datetime
import re

_MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
         "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
_NOM_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
             "novembre", "décembre"]
_JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_RE_MOIS = "|".join(_MOIS)


def _sans_accents(texte):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


_MOIS_ACC = r"janvier|f[eé]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[eé]cembre"


def annees_en_chiffres(texte):
    """« le 14 juillet deux mille trente » -> « le 14 juillet 2030 » (années 1000 à 2999 dites en lettres,
    après un mois ou « en » / « né » / « née »). Le reste du texte ne change pas."""
    if not texte:
        return texte
    try:
        import jarvis_pratique
        mots = re.split(r"(\s+)", texte)             # mots et espaces gardés
        pos = [i for i in range(len(mots)) if i % 2 == 0]
        sortie, k = [], 0
        while k < len(pos):
            i = pos[k]
            avant = mots[pos[k - 1]].lower() if k else ""
            if k and re.fullmatch(rf"{_MOIS_ACC}|en|nee?s?", avant):
                fait = False
                for n in range(6, 1, -1):               # le plus long groupe de mots d'abord
                    groupe = [mots[p] for p in pos[k:k + n]]
                    if len(groupe) < n:
                        continue
                    cand = " ".join(groupe).lower().replace("-", " ")
                    morceaux = jarvis_pratique._decouper(cand)
                    valeur, fin = jarvis_pratique._lire_nombre(morceaux, 0)
                    if valeur is not None and fin >= len(morceaux) and 1000 <= valeur <= 2999 and len(morceaux) >= 2:
                        sortie.append(str(int(valeur)))
                        k += n
                        fait = True
                        break
                if fait:
                    if k < len(pos):
                        sortie.append(" ")
                    continue
            sortie.append(mots[i])
            if k + 1 < len(pos):
                sortie.append(mots[i + 1])
            k += 1
        return "".join(sortie)
    except Exception:
        return texte



def _phrase(t):
    s = _sans_accents((t or "").lower())
    s = re.sub(r"[^a-z0-9' ,.]", " ", s.replace("’", "'"))
    return re.sub(r"\s+", " ", s).strip(" .!?,")


def _nombre(texte):
    """Un nombre écrit en chiffres ou en lettres (« 45 », « quarante-cinq »), ou None."""
    texte = (texte or "").strip().lower()
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)", texte)
    if m:
        return float(m.group(1).replace(",", "."))
    try:
        import jarvis_pratique
        mots = jarvis_pratique._decouper(texte)
        valeur, fin = jarvis_pratique._lire_nombre(mots, 0)
        if valeur is not None and fin >= len(mots):
            return float(valeur)
    except Exception:
        pass
    return None


def _dire(x):
    try:
        import jarvis_pratique
        return jarvis_pratique.dire_nombre(x)
    except Exception:
        return str(int(x)) if float(x).is_integer() else str(x)


def _jour_mois_annee(s):
    """« 1er janvier 2000 », « 14 juillet 2030 » -> datetime.date, ou None."""
    m = re.search(rf"\b(1er|premier|\d{{1,2}}) ({_RE_MOIS}) (\d{{4}})\b", s)
    if not m:
        return None
    jour = 1 if m.group(1) in ("1er", "premier") else int(m.group(1))
    try:
        return datetime.date(int(m.group(3)), _MOIS[m.group(2)], jour)
    except ValueError:
        return None


# ---------------------------------------------------------------- calendrier

def _mois_annee(s, aujourdhui):
    if re.search(r"\b(sera|prochain|dernier|demain|hier|passe|suivant)\b", s):
        return None
    if re.search(r"\bquel mois\b", s):
        return f"Nous sommes en {_NOM_MOIS[aujourdhui.month - 1]} {aujourdhui.year}."
    if re.search(r"\b(?:en )?quelle annee\b", s):
        return f"Nous sommes en {aujourdhui.year}."
    return None


_SAISONS = [("printemps", (3, 20)), ("été", (6, 21)), ("automne", (9, 22)), ("hiver", (12, 21))]


def _saison(s, aujourdhui):
    if re.search(r"\bquelle saison\b", s) and not re.search(r"\b(sera|prochaine)\b", s):
        md = (aujourdhui.month, aujourdhui.day)
        nom = "hiver"
        for n, debut in _SAISONS:
            if md >= debut:
                nom = n
        return f"Nous sommes en {nom}."
    m = re.search(r"\bquand (?:commence|debute|arrive|finit) (?:le |l'|la )?(printemps|ete|automne|hiver)\b", s)
    if m:
        cible = {"printemps": "printemps", "ete": "été", "automne": "automne", "hiver": "hiver"}[m.group(1)]
        mois, jour = dict(_SAISONS)[cible]
        annee = aujourdhui.year
        if datetime.date(annee, mois, jour) < aujourdhui:
            annee += 1
        d = datetime.date(annee, mois, jour)
        article = "L'" if cible in ("été", "automne", "hiver") else "Le "
        return (f"{article}{cible} commence autour du {jour} {_NOM_MOIS[mois - 1]} {annee}, "
                f"dans {(d - aujourdhui).days} jours. La date exacte varie d'un jour ou deux selon les années.")
    return None


def _jour_de_la_date(s, aujourdhui):
    if not re.search(r"\bquel jour\b|\bc'est quel jour\b|\bquel jour de la semaine\b", s):
        return None
    d = _jour_mois_annee(s)
    if not d:
        return None
    nom = _JOURS[d.weekday()]
    dit = f"{'1er' if d.day == 1 else d.day} {_NOM_MOIS[d.month - 1]} {d.year}"
    if d == aujourdhui:
        return f"Le {dit}, c'est aujourd'hui, un {nom}."
    return f"Le {dit}, {'ce sera' if d > aujourdhui else 'c' + chr(39) + 'était'} un {nom}."


# ---------------------------------------------------------------- calculs « de tête »

_OPERATIONS = {"moitie": lambda x: x / 2, "double": lambda x: x * 2, "triple": lambda x: x * 3,
               "quart": lambda x: x / 4, "tiers": lambda x: x / 3, "carre": lambda x: x * x,
               "cube": lambda x: x ** 3}


def _calcul(s):
    r = re.search(r"\bracine carree? d[eu'] ?(.+)$", s)
    if r:
        x = _nombre(r.group(1).strip(" ?"))
        if x is None or x < 0:
            return None
        return f"Ça fait {_dire(round(x ** 0.5, 6))}."
    m = re.search(r"\b(?:la |le )?(moitie|double|triple|quart|tiers|carre|cube) d[eu']\s?(.+)$", s)
    if not m:
        return None
    x = _nombre(m.group(2).strip(" ?"))
    if x is None:
        return None
    return f"Ça fait {_dire(_OPERATIONS[m.group(1)](x))}."


# ---------------------------------------------------------------- « combien de X dans Y »

_SECONDES = {"seconde": 1, "minute": 60, "heure": 3600, "jour": 86400, "journee": 86400, "semaine": 604800,
             "an": 31536000, "annee": 31536000}
_TEMPS_NOM = {"seconde": ("seconde", "secondes"), "minute": ("minute", "minutes"), "heure": ("heure", "heures"),
              "jour": ("jour", "jours"), "semaine": ("semaine", "semaines"), "an": ("an", "ans")}


def _racine(mot):
    mot = mot.strip()
    if mot.endswith("s") and mot not in ("mois",):
        mot = mot[:-1]
    return {"journee": "jour", "annee": "an"}.get(mot, mot)


def _combien_dans(s, t):
    # VARIANTES de formulation (Whisper écrit « galon », on dit aussi « font » ou « février a combien de jours »)
    s = re.sub(r"\bgalons?\b", "gallon", s)
    t = re.sub(r"(?i)\bgalons?\b", "gallon", t)
    s = re.sub(r"\b(combien (?:de|d') ?[a-z/ ]+?) font (un|une|[0-9]+(?:[.,][0-9]+)?) ", r"\1 dans \2 ", s)
    t = re.sub(r"(?i)\b(combien (?:de|d') ?[^ ]+(?: [^ ]+)?) font (un|une|[0-9]+(?:[.,][0-9]+)?) ", r"\1 dans \2 ", t)
    s = re.sub(rf"\bcombien de jours a ({_RE_MOIS})( \d{{4}})?$", r"combien de jours en \1\2", s)
    s = re.sub(rf"^({_RE_MOIS})( \d{{4}})? a combien de jours$", r"combien de jours en \1\2", s)
    # jours dans un mois précis (« combien de jours dans février 2028 »)
    mm = re.search(rf"\bcombien (?:y a t il |y a-t-il |il y a )?de jours (?:y a t il |y a-t-il |il y a )?(?:dans|en) (?:le mois d[eu'] ?|un |le )?({_RE_MOIS})(?: (?:de |en )?(\d{{4}}))?$", s)
    if mm:
        mois = _MOIS[mm.group(1)]
        if mois == 2:
            if mm.group(2):
                an = int(mm.group(2))
                bis = (an % 4 == 0 and an % 100 != 0) or an % 400 == 0
                return f"En février {an}, il y a {29 if bis else 28} jours."
            return "Février a 28 jours, et 29 les années bissextiles."
        return f"{_NOM_MOIS[mois - 1].capitalize()} a {30 if mois in (4, 6, 9, 11) else 31} jours."
    m = re.search(r"\bcombien (?:de|d')\s?([a-z/ ]+?) (?:y a t il |y a-t-il |il y a )?(?:dans|en) (un|une|[0-9]+(?:[.,][0-9]+)?|[a-z-]+) ([a-z/ ]+?)$", s)
    if not m:
        return None
    cherche, quantite, source = m.group(1).strip(), m.group(2), m.group(3).strip()
    a, b = _racine(cherche), _racine(source)
    if a in _SECONDES and b in _SECONDES:
        n = 1 if quantite in ("un", "une") else _nombre(quantite)
        if n is None:
            return None
        total = n * _SECONDES[b] / _SECONDES[a]
        if a == "an" or b == "an":
            note = " (en comptant une année de 365 jours)"
        else:
            note = ""
        nom_b = _TEMPS_NOM[b][0 if n == 1 else 1]
        nom_a = _TEMPS_NOM[a][0 if total == 1 else 1]
        return f"Dans {_dire(n)} {nom_b}, il y a {_dire(total)} {nom_a}{note}."
    if (a, b) == ("mois", "an"):
        return "Il y a 12 mois dans une année."
    if (a, b) == ("jour", "mois"):
        return "Un mois dure 28 à 31 jours, selon le mois."
    if (a, b) == ("semaine", "mois"):
        return "Un mois fait un peu plus de quatre semaines."
    # une conversion d'unités : « combien de centimètres dans 5 pouces » -> « 5 pouces en centimètres »
    try:
        import jarvis_pratique
        n = quantite if re.fullmatch(r"[0-9]+(?:[.,][0-9]+)?", quantite) else ("1" if quantite in ("un", "une") else None)
        if n is None:
            v = _nombre(quantite)
            n = None if v is None else str(int(v) if float(v).is_integer() else v)
        if n:
            mm2 = re.search(r"\bcombien (?:de|d')\s?([^ ]+(?: [^ ]+)?) (?:y a t il |y a-t-il |il y a )?(?:dans|en) "
                            r"(?:un|une|[0-9a-z,.-]+) (.+)$", t.lower())
            if mm2:
                return jarvis_pratique.commande_conversion(f"{n} {mm2.group(2).strip(' ?')} en {mm2.group(1)}")
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- âge, signe

_SIGNES = [((1, 20), "le Verseau"), ((2, 19), "les Poissons"), ((3, 21), "le Bélier"), ((4, 20), "le Taureau"),
           ((5, 21), "les Gémeaux"), ((6, 21), "le Cancer"), ((7, 23), "le Lion"), ((8, 23), "la Vierge"),
           ((9, 23), "la Balance"), ((10, 23), "le Scorpion"), ((11, 22), "le Sagittaire"), ((12, 22), "le Capricorne")]


def _signe(s):
    m = re.search(rf"\bsigne(?: astrologique| du zodiaque)? (?:du|de|pour le|pour) ?(1er|premier|\d{{1,2}}) ({_RE_MOIS})\b", s)
    if not m:
        return None
    jour = 1 if m.group(1) in ("1er", "premier") else int(m.group(1))
    mois = _MOIS[m.group(2)]
    try:
        datetime.date(2024, mois, jour)
    except ValueError:
        return None
    nom = "le Capricorne"                       # avant le 20 janvier
    for debut, signe in _SIGNES:
        if (mois, jour) >= debut:
            nom = signe
    return (f"Le {'1er' if jour == 1 else jour} {_NOM_MOIS[mois - 1]}, c'est {nom}. Les dates changent d'un jour "
            "selon les années.")


def _age(s, aujourdhui):
    if not re.search(r"\bquel age\b|\bcombien d'?ans\b", s):
        return None
    m = re.search(rf"\bne(?:e)? (?:le )?(1er|premier|\d{{1,2}}) ({_RE_MOIS}) (\d{{4}})\b", s)
    if m:
        jour = 1 if m.group(1) in ("1er", "premier") else int(m.group(1))
        try:
            n = datetime.date(int(m.group(3)), _MOIS[m.group(2)], jour)
        except ValueError:
            return None
        ans = aujourdhui.year - n.year - ((aujourdhui.month, aujourdhui.day) < (n.month, n.day))
        return f"Une personne née le {jour} {_NOM_MOIS[n.month - 1]} {n.year} a {ans} ans aujourd'hui."
    m = re.search(r"\bne(?:e)? en (\d{4})\b", s)
    if m:
        an = int(m.group(1))
        if an > aujourdhui.year:
            return None
        haut = aujourdhui.year - an
        return f"Une personne née en {an} a {haut - 1} ou {haut} ans, selon que son anniversaire est passé ou non."
    return None


# ---------------------------------------------------------------- capitales

_CAPITALES = {
    "france": "Paris", "allemagne": "Berlin", "espagne": "Madrid", "italie": "Rome", "portugal": "Lisbonne",
    "belgique": "Bruxelles", "suisse": "Berne", "pays-bas": "Amsterdam", "pays bas": "Amsterdam",
    "luxembourg": "Luxembourg", "royaume-uni": "Londres", "royaume uni": "Londres", "angleterre": "Londres",
    "irlande": "Dublin", "ecosse": "Édimbourg", "autriche": "Vienne", "grece": "Athènes", "pologne": "Varsovie",
    "suede": "Stockholm", "norvege": "Oslo", "danemark": "Copenhague", "finlande": "Helsinki", "islande": "Reykjavik",
    "russie": "Moscou", "ukraine": "Kiev", "roumanie": "Bucarest", "bulgarie": "Sofia", "hongrie": "Budapest",
    "republique tcheque": "Prague", "tchequie": "Prague", "slovaquie": "Bratislava", "croatie": "Zagreb",
    "serbie": "Belgrade", "slovenie": "Ljubljana", "turquie": "Ankara", "chypre": "Nicosie", "malte": "La Valette",
    "etats-unis": "Washington", "etats unis": "Washington", "canada": "Ottawa", "mexique": "Mexico",
    "bresil": "Brasilia", "argentine": "Buenos Aires", "chili": "Santiago", "perou": "Lima", "colombie": "Bogota",
    "venezuela": "Caracas", "cuba": "La Havane", "uruguay": "Montevideo", "bolivie": "Sucre", "equateur": "Quito",
    "paraguay": "Asuncion", "chine": "Pékin", "japon": "Tokyo", "inde": "New Delhi", "coree du sud": "Séoul",
    "coree du nord": "Pyongyang", "thailande": "Bangkok", "vietnam": "Hanoï", "indonesie": "Jakarta",
    "philippines": "Manille", "pakistan": "Islamabad", "iran": "Téhéran", "irak": "Bagdad", "israel": "Jérusalem",
    "arabie saoudite": "Riyad", "egypte": "Le Caire", "maroc": "Rabat", "algerie": "Alger", "tunisie": "Tunis",
    "senegal": "Dakar", "cote d'ivoire": "Yamoussoukro", "nigeria": "Abuja", "kenya": "Nairobi",
    "ethiopie": "Addis-Abeba", "afrique du sud": "Pretoria", "madagascar": "Antananarivo", "australie": "Canberra",
    "nouvelle-zelande": "Wellington", "nouvelle zelande": "Wellington", "mongolie": "Oulan-Bator",
    "afghanistan": "Kaboul", "liban": "Beyrouth", "jordanie": "Amman", "syrie": "Damas", "qatar": "Doha",
    "mali": "Bamako", "cameroun": "Yaoundé", "ghana": "Accra", "monaco": "Monaco", "andorre": "Andorre-la-Vieille",
    "estonie": "Tallinn", "lettonie": "Riga", "lituanie": "Vilnius", "bielorussie": "Minsk", "albanie": "Tirana",
}


_NUANCES = {
    "israel": "Israël a déclaré Jérusalem capitale, mais ce statut n'est pas reconnu par tous les pays, et la plupart "
              "des ambassades sont à Tel-Aviv.",
    "bolivie": "La capitale officielle est Sucre, mais le gouvernement siège à La Paz.",
    "cote d'ivoire": "La capitale officielle est Yamoussoukro, mais la plus grande ville et le centre économique est Abidjan.",
    "pays-bas": "La capitale est Amsterdam, mais le gouvernement siège à La Haye.",
    "pays bas": "La capitale est Amsterdam, mais le gouvernement siège à La Haye.",
    "afrique du sud": "L'Afrique du Sud a trois capitales : Pretoria pour l'administration, Le Cap pour le parlement "
                      "et Bloemfontein pour la justice.",
}


def _capitale(s):
    if not re.match(r"^(?:et )?(?:(?:jarvis )?(?:dis moi |donne moi )?(?:quelle est |c'est quoi |quel est le nom de ))?"
                    r"(?:la )?capitale (?:de|du|d'|des)", s):
        return None
    m = re.search(r"\bcapitale (?:de la |de l'|de |du |des |d'|des )?(?:republique democratique du )?([a-z' -]+?)$", s)
    if not m:
        return None
    if re.search(r"\bcongo\b", s):
        return ("Il y a deux Congo : la République du Congo, dont la capitale est Brazzaville, et la République "
                "démocratique du Congo, dont la capitale est Kinshasa.")
    pays = m.group(1).strip()
    nuance = _NUANCES.get(pays.replace("l'", "").replace("la ", "").replace("le ", "").replace("les ", ""))
    if nuance:
        return nuance
    for nom in (pays, pays.replace("l'", ""), pays.replace("la ", ""), pays.replace("le ", ""), pays.replace("les ", "")):
        if nom in _CAPITALES:
            return f"La capitale est {_CAPITALES[nom]}."
    return None


# ---------------------------------------------------------------- Jarvis lui-même, et le PC

def _identite(s):
    if re.search(r"\bqui (?:t'a|ta) (?:cree|fait|programme|invente|developpe|concu|construit)\b|\bqui est ton createur\b", s):
        return "J'ai été créé par TonyNio, avec l'aide de Claude, l'assistant d'Anthropic."
    if re.search(r"\bquel age (?:as|a) ?-?tu\b|\btu as quel age\b", s):
        try:
            import jarvis_claude
            version = f", en version {jarvis_claude.VERSION}"
        except Exception:
            version = ""
        return f"Je n'ai pas d'âge : je suis un programme qui tourne sur ton PC{version}."
    if re.search(r"\b(?:combien de|quelle est la) (?:ram|memoire vive)\b|\bquelle (?:quantite )?de memoire (?:vive )?(?:j'ai|a mon pc|a ce pc)\b"
                 r"|\bquelle est la memoire de (?:mon|ce) (?:pc|ordinateur)\b|\bcombien de memoire (?:j'ai|a mon pc|a ce pc|a mon ordinateur)\b", s):
        try:
            import jarvis_local
            return jarvis_local._memoire()
        except Exception:
            return None
    return None


# ---------------------------------------------------------------- entrée

def commande(t, brut="", aujourdhui=None):
    t = annees_en_chiffres(t)
    s = _phrase(t)
    if not s or len(s) > 140:
        return None
    aujourdhui = aujourdhui or datetime.date.today()
    for fonction in (lambda: _mois_annee(s, aujourdhui), lambda: _saison(s, aujourdhui),
                     lambda: _jour_de_la_date(s, aujourdhui), lambda: _calcul(s), lambda: _combien_dans(s, t or ""),
                     lambda: _signe(s), lambda: _age(s, aujourdhui), lambda: _capitale(s), lambda: _identite(s)):
        try:
            reponse = fonction()
        except Exception:
            reponse = None
        if reponse:
            return reponse
    return None
