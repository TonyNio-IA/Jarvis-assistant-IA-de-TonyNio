"""
JARVIS - commandes pratiques (sans Claude, donc instantanées et sans quota).

  - les calculs : « combien font 15 % de 80 », « calcule 12 fois 7 », « racine carrée de 144 » ;
  - les conversions : « 3 miles en kilomètres », « 20 degrés en fahrenheit », « 50 dollars en euros »
    (les taux de change viennent du service gratuit Frankfurter, données de la Banque centrale européenne) ;
  - le chronomètre : « lance un chrono », « où en est le chrono », « arrête le chrono » ;
  - les listes : « ajoute du pain à la liste », « enlève le pain de la liste », « lis-moi la liste »,
    « ajoute appeler le garage à la liste des tâches » (fichier liste.json, gardé sur ce PC) ;
  - les raccourcis clavier dans la fenêtre active : « copie », « colle », « coupe », « annule ça »,
    « refais », « enregistre », « sélectionne tout », « imprime », « nouvel onglet », « ferme l'onglet »,
    « actualise », « onglet suivant » ;
  - avancer ou reculer dans une vidéo : « avance de 30 secondes », « recule de 10 secondes » ;
  - le volume d'une seule application : « baisse le son du navigateur », « mets le son de Spotify à 30 » ;
  - le mode sombre ou clair de Windows ;
  - « qu'est-ce que tu sais faire ? ».
Chaque fonction « commande_... » renvoie la phrase à dire, ou None si la demande ne la concerne pas.
"""

import ast
import ctypes
import difflib
import json
import math
import operator
import re
import threading
import time
import urllib.request

import os

import jarvis_config

FICHIER_LISTE = jarvis_config.chemin("liste.json")      # reste sur ce PC (jamais publié)


# ---------- Nombres dits en lettres ou écrits en chiffres ----------

_UNITES = {"zéro": 0, "zero": 0, "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6,
           "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
           "quinze": 15, "seize": 16, "vingt": 20, "vingts": 20, "trente": 30, "quarante": 40, "cinquante": 50,
           "soixante": 60, "cent": 100, "cents": 100}
_GRANDS = {"mille": 1000, "million": 10 ** 6, "millions": 10 ** 6, "milliard": 10 ** 9, "milliards": 10 ** 9}


def _mots_vers_nombre(mots):
    """« deux cent quarante et un » -> 241 ; « quatre vingt dix » -> 90. None si ce ne sont pas des nombres."""
    total, courant, vu = 0, 0, False
    for mot in mots:
        if mot == "et":
            continue
        if mot in _GRANDS:
            total += (courant or 1) * _GRANDS[mot]
            courant, vu = 0, True
        elif mot in ("cent", "cents"):
            courant = (courant or 1) * 100
            vu = True
        elif mot in _UNITES:
            v = _UNITES[mot]
            if v == 20 and courant % 100 == 4:
                courant += 76                         # quatre-vingt = 80
            else:
                courant += v
            vu = True
        else:
            return None
    return total + courant if vu else None


def _decouper(texte):
    """Découpe en mots et nombres ; « 12,5 » et « 12.5 » restent un seul nombre ; « 1 000 » aussi."""
    texte = re.sub(r"(?<=\d) (?=\d{3}\b)", "", texte)            # « 1 000 » -> « 1000 »
    texte = texte.replace("-", " ").replace("’", "'")
    return re.findall(r"\d+(?:[.,]\d+)?|%|[a-zàâäçéèêëîïôöùûüœ']+|[+*/x×÷^()]", texte.lower())


def _lire_nombre(mots, i):
    """Lit un nombre à partir de la position i. Renvoie (valeur, position suivante) ou (None, i)."""
    if i < len(mots) and re.fullmatch(r"\d+(?:[.,]\d+)?", mots[i]):
        valeur, j = float(mots[i].replace(",", ".")), i + 1
    else:
        j = i
        while j < len(mots) and (mots[j] in _UNITES or mots[j] in _GRANDS or (mots[j] == "et" and j > i
                                                                            and j + 1 < len(mots)
                                                                            and mots[j + 1] in ("un", "une", "onze"))):
            j += 1
        valeur = _mots_vers_nombre(mots[i:j]) if j > i else None
        if valeur is None:
            return None, i
    # « douze virgule cinq »
    if j + 1 < len(mots) and mots[j] == "virgule":
        k = j + 1
        if re.fullmatch(r"\d+", mots[k]):
            return float(f"{int(valeur)}.{mots[k]}"), k + 1
        m = k
        while m < len(mots) and mots[m] in _UNITES:
            m += 1
        decimales = _mots_vers_nombre(mots[k:m]) if m > k else None
        if decimales is not None:
            zeros = 0
            while k + zeros < m and mots[k + zeros] in ("zéro", "zero"):
                zeros += 1
            return float(f"{int(valeur)}.{'0' * zeros}{int(decimales)}"), m
    return valeur, j


def dire_nombre(x):
    """12.5 -> « 12,5 » ; 3.0 -> « 3 » ; arrondi lisible à voix haute."""
    if x != x or abs(x) == float("inf"):
        return "un nombre impossible"
    if abs(x) >= 1000 or x == int(x):
        x = round(x, 2 if abs(x) < 10 ** 6 else 0)
    else:
        chiffres = max(2, 4 - len(str(int(abs(x)))))
        x = round(x, chiffres)
    texte = (f"{x:.10f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x))
    if texte in ("-0", ""):
        texte = "0"
    return texte.replace(".", ",")


# ---------- Calculs ----------

_DEBUT_CALCUL = re.compile(r"^\W*(?:jarvis\W+)?(?:combi(?:en)? (?:font|fait|ça fait|ca fait|égale|egale|vaut)|"
                           r"calcule(?:-moi)?|ça fait combien|ca fait combien|c'est combien|quel est le résultat de|"
                           r"quel est le resultat de|résous|résultat de)\b[\s:,]*", re.I)
_OPERATEURS = [
    (("multiplié", "par"), "*"), (("multipliée", "par"), "*"), (("divisé", "par"), "/"), (("divisée", "par"), "/"),
    (("puissance",), "**"), (("exposant",), "**"),
    (("plus",), "+"), (("moins",), "-"), (("fois",), "*"), (("x",), "*"), (("×",), "*"), (("*",), "*"),
    (("divisé",), "/"), (("÷",), "/"), (("/",), "/"), (("+",), "+"), (("^",), "**"),
]
_PERMIS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
           ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _evaluer(noeud):
    if isinstance(noeud, ast.Expression):
        return _evaluer(noeud.body)
    if isinstance(noeud, ast.Constant) and isinstance(noeud.value, (int, float)):
        return float(noeud.value)
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in _PERMIS:
        gauche, droite = _evaluer(noeud.left), _evaluer(noeud.right)
        if isinstance(noeud.op, ast.Pow) and abs(droite) > 100:
            raise ValueError("puissance trop grande")
        return _PERMIS[type(noeud.op)](gauche, droite)
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in _PERMIS:
        return _PERMIS[type(noeud.op)](_evaluer(noeud.operand))
    if isinstance(noeud, ast.Call) and isinstance(noeud.func, ast.Name) and noeud.func.id == "racine" \
            and len(noeud.args) == 1:
        return math.sqrt(_evaluer(noeud.args[0]))
    raise ValueError("expression non permise")


def _expression(mots):
    """Transforme les mots d'un calcul en expression Python sûre (« 15 % de 80 » -> « (15/100*80) »).
    Renvoie None si un mot n'est pas compris."""
    sortie, i, attend_nombre = [], 0, True
    while i < len(mots):
        mot = mots[i]
        if mot in ("le", "la", "de", "d'", "du", "des", "à", "a", "égal", "egal", "combien", "?") and not attend_nombre:
            i += 1
            continue
        if attend_nombre:
            if mot in ("racine", "la") and "racine" in mots[i:i + 2]:
                k = mots.index("racine", i) + 1
                while k < len(mots) and mots[k] in ("carrée", "carree", "carré", "carre", "de", "d'"):
                    k += 1
                valeur, j = _lire_nombre(mots, k)
                if valeur is None:
                    return None
                sortie.append(f"racine({valeur})")
                i, attend_nombre = j, False
                continue
            if mot == "moins":
                sortie.append("-")
                i += 1
                continue
            valeur, j = _lire_nombre(mots, i)
            if valeur is None:
                return None
            # « 15 % de 80 », « 15 pour cent de 80 »
            if j < len(mots) and (mots[j] == "%" or mots[j:j + 2] == ["pour", "cent"]):
                j += 1 if mots[j] == "%" else 2
                if j < len(mots) and mots[j] in ("de", "d'", "du", "des", "sur"):
                    autre, k = _lire_nombre(mots, j + 1)
                    if autre is None:
                        return None
                    sortie.append(f"({valeur}/100*{autre})")
                    i, attend_nombre = k, False
                    continue
                sortie.append(f"({valeur}/100)")
                i, attend_nombre = j, False
                continue
            sortie.append(repr(valeur))
            i, attend_nombre = j, False
            # « au carré », « au cube »
            if mots[i:i + 2] in (["au", "carré"], ["au", "carre"]):
                sortie.append("**2")
                i += 2
            elif mots[i:i + 2] == ["au", "cube"]:
                sortie.append("**3")
                i += 2
            continue
        for forme, symbole in _OPERATEURS:
            if tuple(mots[i:i + len(forme)]) == forme:
                sortie.append(symbole)
                i += len(forme)
                attend_nombre = True
                break
        else:
            return None
    if attend_nombre or not sortie:
        return None
    return "".join(sortie)


def commande_calcul(t):
    m = _DEBUT_CALCUL.match(t)
    reste = t[m.end():] if m else t
    reste = reste.strip(" ?.!")
    mots = _decouper(reste)
    # Sans « combien », « calcule »... : seulement une opération nette (« 12 fois 7 »), pas une phrase quelconque
    racine = bool(re.match(r"(?:la )?racine carr", reste))
    if not m and not racine and not (len(mots) >= 3 and any(o in mots for o in ("plus", "moins", "fois", "divisé",
                                                                                "multiplié", "x", "×", "*", "/", "+"))
                                     and _lire_nombre(mots, 0)[0] is not None):
        return None
    if not mots:
        return None
    expression = _expression(mots)
    if expression is None or not re.search(r"[+\-*/]|racine", expression):
        return None
    try:
        resultat = _evaluer(ast.parse(expression, mode="eval"))
    except ZeroDivisionError:
        return "On ne peut pas diviser par zéro."
    except (ValueError, SyntaxError, OverflowError):
        return None
    return f"Ça fait {dire_nombre(resultat)}."


# ---------- Conversions ----------

# (noms possibles, grandeur, valeur dans l'unité de base, nom à dire)
_UNITES_MESURE = [
    (("kilomètres par heure", "kilomètres heure", "kilomètre heure", "kilomètres à l'heure", "km/h", "km h"),
     "vitesse", 1 / 3.6, "kilomètres heure"),
    (("miles par heure", "miles à l'heure", "mph"), "vitesse", 0.44704, "miles par heure"),
    (("mètres par seconde", "m/s"), "vitesse", 1.0, "mètres par seconde"),
    (("nœuds", "noeuds", "nœud", "noeud"), "vitesse", 0.514444, "nœuds"),
    (("kilomètres", "kilomètre", "km"), "longueur", 1000.0, "kilomètres"),
    (("centimètres", "centimètre", "cm"), "longueur", 0.01, "centimètres"),
    (("millimètres", "millimètre", "mm"), "longueur", 0.001, "millimètres"),
    (("mètres", "mètre", "m"), "longueur", 1.0, "mètres"),
    (("miles", "mile", "milles", "mille"), "longueur", 1609.344, "miles"),
    (("pieds", "pied", "feet", "foot"), "longueur", 0.3048, "pieds"),
    (("pouces", "pouce", "inches", "inch"), "longueur", 0.0254, "pouces"),
    (("yards", "yard"), "longueur", 0.9144, "yards"),
    (("tonnes", "tonne"), "masse", 1000.0, "tonnes"),
    (("kilogrammes", "kilogramme", "kilos", "kilo", "kg"), "masse", 1.0, "kilos"),
    (("grammes", "gramme", "g"), "masse", 0.001, "grammes"),
    (("livres", "livre", "lbs", "lb"), "masse", 0.45359237, "livres"),
    (("onces", "once", "oz"), "masse", 0.028349523125, "onces"),
    (("litres", "litre", "l"), "volume", 1.0, "litres"),
    (("centilitres", "centilitre", "cl"), "volume", 0.01, "centilitres"),
    (("millilitres", "millilitre", "ml"), "volume", 0.001, "millilitres"),
    (("gallons", "gallon"), "volume", 3.785411784, "gallons"),
]
_TEMPERATURES = [
    (("degrés celsius", "degré celsius", "celsius"), "celsius"),
    (("degrés fahrenheit", "degré fahrenheit", "fahrenheit"), "fahrenheit"),
    (("kelvins", "kelvin"), "kelvin"),
    (("degrés", "degré"), "celsius"),
]
_MONNAIES = [
    (("euros", "euro", "€"), "EUR", "euros"),
    (("dollars américains", "dollars us", "dollars", "dollar", "$"), "USD", "dollars"),
    (("dollars canadiens", "dollar canadien"), "CAD", "dollars canadiens"),
    (("livres sterling", "livre sterling", "livres anglaises"), "GBP", "livres sterling"),
    (("francs suisses", "franc suisse"), "CHF", "francs suisses"),
    (("yens", "yen"), "JPY", "yens"),
    (("yuans", "yuan"), "CNY", "yuans"),
]


def _trouver(texte, table, position_nom=0):
    """Unité dite au début de « texte » : renvoie (entrée de la table, longueur reconnue)."""
    meilleur = None
    for entree in table:
        for nom in entree[position_nom]:
            if re.match(re.escape(nom) + r"(?![a-zàâäçéèêëîïôöùûüœ])", texte):
                if meilleur is None or len(nom) > meilleur[1]:
                    meilleur = (entree, len(nom))
    return meilleur


_CONVERSION = re.compile(r"^\W*(?:jarvis\W+)?(?:convertis(?:-moi)?|conversion de|combi(?:en)? (?:font|fait|ça fait|ca fait|vaut|valent|"
                         r"de|d')|ça fait combien|c'est combien|ça donne combien)?[\s:,]*(?P<nombre>.+?)\s+"
                         r"(?P<de>[a-zàâäçéèêëîïôöùûüœ$€/' ]+?)\s+(?:en|dans|vers|un|1)\s+(?P<vers>[a-zàâäçéèêëîïôöùûüœ$€/' ]+?)\W*$")


def _taux(de, vers, montant):
    """Montant converti par le service gratuit Frankfurter (Banque centrale européenne)."""
    for adresse in ("https://api.frankfurter.dev/v1/latest", "https://api.frankfurter.app/latest"):
        try:
            requete = urllib.request.Request(f"{adresse}?amount={montant}&from={de}&to={vers}",
                                             headers={"User-Agent": "Jarvis"})
            with urllib.request.urlopen(requete, timeout=5) as r:
                return float(json.load(r)["rates"][vers])
        except Exception:
            continue
    return None


def _accorde(nom, valeur):
    """« 1 gallons » -> « 1 gallon » : au singulier sous 2 (« 1,5 kilo »), au pluriel ensuite."""
    if abs(valeur) < 2:
        return re.sub(r"(?<=[a-zàâäçéèêëîïôöùûüœ])s\b", "", nom, count=1)
    return nom


def commande_conversion(t):
    m = _CONVERSION.match(t.replace("’", "'"))
    if not m:
        return None
    mots = _decouper(m.group("nombre"))
    valeur, j = _lire_nombre(mots, 0)
    if valeur is None or j != len(mots):
        return None
    de, vers = m.group("de").strip(), m.group("vers").strip()
    de = re.sub(r"^(?:de |d')", "", de)
    vers = re.sub(r"^(?:des |de |d'|le |la |les )", "", vers)
    # Monnaies
    a, b = _trouver(de, _MONNAIES), _trouver(vers, _MONNAIES)
    if a and b and a[1] == len(de) and b[1] == len(vers):
        if a[0][1] == b[0][1]:
            return None
        resultat = _taux(a[0][1], b[0][1], valeur)
        if resultat is None:
            return "Je n'arrive pas à obtenir le taux de change pour le moment."
        return (f"{dire_nombre(valeur)} {_accorde(a[0][2], valeur)}, ça fait environ "
                f"{dire_nombre(round(resultat, 2))} {_accorde(b[0][2], resultat)}.")
    # Températures
    a, b = _trouver(de, _TEMPERATURES), _trouver(vers, _TEMPERATURES)
    if a and b and a[1] == len(de) and b[1] == len(vers) and a[0][1] != b[0][1]:
        celsius = {"celsius": valeur, "fahrenheit": (valeur - 32) * 5 / 9, "kelvin": valeur - 273.15}[a[0][1]]
        resultat = {"celsius": celsius, "fahrenheit": celsius * 9 / 5 + 32, "kelvin": celsius + 273.15}[b[0][1]]
        noms = {"celsius": "degrés Celsius", "fahrenheit": "degrés Fahrenheit", "kelvin": "kelvins"}
        return (f"{dire_nombre(valeur)} {_accorde(noms[a[0][1]], valeur)}, ça fait "
                f"{dire_nombre(round(resultat, 1))} {_accorde(noms[b[0][1]], resultat)}.")
    # Longueurs, masses, volumes, vitesses
    a, b = _trouver(de, _UNITES_MESURE), _trouver(vers, _UNITES_MESURE)
    if not (a and b and a[1] == len(de) and b[1] == len(vers)) or a[0][1] != b[0][1] or a[0] is b[0]:
        return None
    resultat = valeur * a[0][2] / b[0][2]
    return (f"{dire_nombre(valeur)} {_accorde(a[0][3], valeur)}, ça fait "
            f"{dire_nombre(resultat)} {_accorde(b[0][3], resultat)}.")


# ---------- Chronomètre ----------

_chrono = {"debut": None, "fin": None}


def _duree_chrono(secondes):
    if secondes < 60:
        return f"{dire_nombre(round(secondes, 1))} seconde{'s' if secondes >= 2 else ''}"
    h, reste = divmod(int(secondes), 3600)
    m, s = divmod(reste, 60)
    parties = []
    if h:
        parties.append(f"{h} heure{'s' if h > 1 else ''}")
    if m:
        parties.append(f"{m} minute{'s' if m > 1 else ''}")
    if s:
        parties.append(f"{s} seconde{'s' if s > 1 else ''}")
    return " et ".join(parties)


def commande_chrono(t):
    if not re.search(r"\b(chrono|chronos|chronomètre|chronometre)\b", t):
        return None
    maintenant = time.time()
    debut, fin = _chrono["debut"], _chrono["fin"]
    if re.search(r"\b(?:remets?|remettre|remise)\b.*\bzéro\b|\b(?:réinitialise|reinitialise|efface)\b", t):
        _chrono.update(debut=None, fin=None)
        return "Le chronomètre est remis à zéro."
    if re.search(r"\b(arrête|arrete|stoppe|stop|termine|fin|pause|bloque)\b", t):
        if debut is None:
            return "Aucun chronomètre ne tourne."
        if fin is None:
            _chrono["fin"] = fin = maintenant
        return f"Chronomètre arrêté : {_duree_chrono(fin - debut)}."
    if re.search(r"\b(lance|lances|démarre|demarre|commence|déclenche|declenche|part|pars|go|relance|nouveau)\b", t):
        if debut is not None and fin is None and not re.search(r"\b(relance|nouveau)\b", t):
            return f"Le chronomètre tourne déjà, depuis {_duree_chrono(maintenant - debut)}."
        _chrono.update(debut=maintenant, fin=None)
        return "Chronomètre lancé."
    if debut is None:
        return "Aucun chronomètre n'est lancé. Dis : lance un chrono."
    ecoule = (fin or maintenant) - debut
    return f"Le chronomètre {'est arrêté à' if fin else 'en est à'} {_duree_chrono(ecoule)}."


# ---------- Listes (courses, tâches) ----------

_verrou_liste = threading.Lock()
_NOM_LISTE = r"(?:la |ma |sur la |sur ma |dans la |dans ma )?liste(?P<quelle> (?:de|des|à) (?:courses|tâches|taches|choses à faire|faire))?"


def _quelle_liste(quelle):
    return "tâches" if quelle and re.search(r"tâches|taches|faire", quelle) else "courses"


class ListeIllisible(Exception):
    pass


def _lire_listes():
    """Les listes enregistrées. Un fichier présent mais illisible n'est jamais écrasé : il lève ListeIllisible."""
    if not os.path.exists(FICHIER_LISTE):
        return {}
    try:
        with open(FICHIER_LISTE, encoding="utf-8-sig") as f:     # « -sig » : accepte aussi un fichier enregistré avec BOM
            listes = json.load(f)
    except (OSError, ValueError) as erreur:
        raise ListeIllisible(str(erreur))
    if isinstance(listes, list):                                  # une simple liste : ce sont les courses
        return {"courses": [str(e) for e in listes]}
    if not isinstance(listes, dict):
        raise ListeIllisible("contenu inattendu")
    return {str(nom): [str(e) for e in (elements or [])] for nom, elements in listes.items()}


def _ecrire_listes(listes):
    with open(FICHIER_LISTE, "w", encoding="utf-8") as f:
        json.dump(listes, f, ensure_ascii=False, indent=1)


COURSES_COURANTES = [
    "pain", "baguette", "lait", "œufs", "beurre", "farine", "sucre", "sel", "poivre", "huile", "vinaigre", "riz",
    "pâtes", "café", "thé", "chocolat", "eau", "jus d'orange", "yaourts", "fromage", "gruyère", "emmental", "jambon",
    "poulet", "viande hachée", "steaks hachés", "poisson", "saumon", "thon", "sardines", "pommes", "poires", "bananes",
    "oranges", "citrons", "fraises", "raisin", "tomates", "salade", "carottes", "pommes de terre", "oignons", "ail",
    "échalotes", "courgettes", "aubergines", "poivrons", "concombre", "champignons", "haricots verts", "petits pois",
    "épinards", "brocolis", "lessive", "liquide vaisselle", "papier toilette", "essuie-tout", "mouchoirs",
    "dentifrice", "shampooing", "gel douche", "savon", "éponges", "sacs poubelle", "croquettes", "biscuits",
    "céréales", "confiture", "miel", "crème fraîche", "lardons", "saucisses", "pizza", "glaces", "bière", "vin",
    "soda", "compote", "moutarde", "mayonnaise", "ketchup", "sauce tomate", "chips", "brioche", "croissants",
    "jus de pomme", "lait de coco", "crème", "mozzarella", "parmesan", "pâte feuilletée", "pâte à pizza", "levure",
]


def _cle(mot):
    return re.sub(r"[^a-z' ]", "", _sans_accents(mot.lower().replace("œ", "oe")))


def _sans_accents(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _connu(element, seuil=0.8):
    """« des oufs » -> (« des œufs », 0.89) si le mot ressemble à une course courante ; sinon (element, 0)."""
    m = re.match(r"^((?:du |de la |de l'|des |de |d'|le |la |les |l'|un |une |deux |trois |quatre |\d+ )?)(.+)$",
                 element.strip(), re.I)
    article, nom = m.group(1), m.group(2)
    cles = {_cle(c): c for c in COURSES_COURANTES}
    proche = difflib.get_close_matches(_cle(nom), list(cles), n=1, cutoff=seuil)
    if not proche:
        return element, 0.0
    juste = cles[proche[0]]
    return article + juste, difflib.SequenceMatcher(None, _cle(nom), proche[0]).ratio()


def _sans_article(texte):
    return re.sub(r"^(?:du |de la |de l'|des |de |d'|le |la |les |l'|un |une )", "", texte.strip().lower())


def _enumerer(elements):
    return elements[0] if len(elements) == 1 else ", ".join(elements[:-1]) + " et " + elements[-1]


def commande_liste(t):
    try:
        return _commande_liste(t)
    except ListeIllisible as erreur:
        print("Liste illisible :", erreur)
        return ("Je n'arrive pas à lire le fichier de ta liste, alors je n'y touche pas. "
                "Il s'appelle liste.json, dans mon dossier.")


def _commande_liste(t):
    if not re.search(r"\bliste\b", t):
        return None
    t = t.replace("’", "'")
    nom = None
    # Ajouter
    m = re.match(r"^\W*(?:jarvis\W+)?(?:ajoutes?|ajouter|ajout|rajoutes?|rajouter|mets|mettre|inscris|note)\s+(?P<quoi>.+?)\s+"
                 r"(?:à|a|sur|dans)\s+" + _NOM_LISTE + r"\W*$", t)
    if m:
        nom = _quelle_liste(m.group("quelle"))
        elements = [e.strip(" ,.") for e in re.split(r",| et (?=(?:du|de la|de l'|des|un|une|deux|trois|quatre|"
                                                       r"cinq|six|\d+|le|la|les|l')\b)", m.group("quoi"))
                    if e.strip(" ,.")]
        if not elements:
            return None
        elements = [_connu(e)[0] for e in elements]
        with _verrou_liste:
            listes = _lire_listes()
            liste = listes.setdefault(nom, [])
            ajoutes = [e for e in elements if _sans_article(e) not in {_sans_article(x) for x in liste}]
            liste.extend(ajoutes)
            _ecrire_listes(listes)
        if not ajoutes:
            return f"C'est déjà sur ta liste de {nom}."
        return f"J'ajoute {_enumerer(ajoutes)} à ta liste de {nom}."
    # Enlever
    m = re.match(r"^\W*(?:jarvis\W+)?(?:enlève|enleve|enlever|retire|retirer|supprime|supprimer|raye|rayer|efface|"
                 r"effacer|barre|barrer)\s+(?P<quoi>.+?)\s+(?:de|d'|du|sur)\s*" + _NOM_LISTE + r"\W*$", t)
    if m and not re.fullmatch(r"(?:la |ma )?liste|tout(?: ce qu'il y a)?|tous|tout le reste", m.group("quoi")):
        nom = _quelle_liste(m.group("quelle"))
        cherche = _sans_article(m.group("quoi"))
        with _verrou_liste:
            listes = _lire_listes()
            liste = listes.get(nom, [])
            noms = [_sans_article(e) for e in liste]
            proche = difflib.get_close_matches(cherche, noms, n=1, cutoff=0.6)
            if not proche:
                return f"Je ne trouve pas {m.group('quoi')} sur ta liste de {nom}."
            retire = liste.pop(noms.index(proche[0]))
            _ecrire_listes(listes)
        return f"J'enlève {retire} de ta liste de {nom}."
    # Vider
    # « vide la liste », « supprime tout de la liste des courses », « efface tout ce qu'il y a sur ma liste »
    m = re.match(r"^\W*(?:jarvis\W+)?(?:vide|vider|efface|effacer|supprime|supprimer|enlève|enleve|retire|remets à zéro)\s+"
                 r"(?:tout\s+(?:ce qu'il y a\s+)?(?:(?:de|du|sur|dans)\s+)?)?" + _NOM_LISTE + r"\W*$", t)
    if m:
        nom = _quelle_liste(m.group("quelle"))
        with _verrou_liste:
            listes = _lire_listes()
            listes[nom] = []
            _ecrire_listes(listes)
        return f"Ta liste de {nom} est vide."
    # Lire (aussi quand « lis-moi » est mal entendu : « lit moins la liste », « Limois, la liste »)
    m = (re.search(r"\b(?:lis|lire|relis|dis-moi|donne-moi|qu'est-ce qu'il y a|qu'y a-t-il|quoi|c'est quoi|rappelle-moi)\b.*?"
                   + _NOM_LISTE, t)
         or re.fullmatch(r"\W*(?:jarvis\W+)?(?:[a-zàâäçéèêëîïôöùûüœ-]+[\s,]+){0,2}(?:la |ma )liste"
                         r"(?P<quelle> (?:de|des) (?:courses|tâches|taches))?\W*", t))
    if m:
        nom = _quelle_liste(m.group("quelle"))
        liste = _lire_listes().get(nom, [])
        if not liste:
            return f"Ta liste de {nom} est vide."
        return f"Sur ta liste de {nom} : {_enumerer(liste)}."
    return None


# ---------- Aide ----------

_AIDE = re.compile(r"\b(qu'est-ce que tu sais faire|que sais-tu faire|tu sais faire quoi|qu'est-ce que tu peux faire|"
                   r"que peux-tu faire|tu peux faire quoi|quelles sont tes commandes|liste de tes commandes|"
                   r"comment (?:on |je )?t'utiliser|à quoi tu sers|a quoi tu sers)\b")


def commande_aide(t):
    if not _AIDE.search(t.replace("’", "'")):
        return None
    return ("Je réponds tout de suite à l'heure, la météo, les calculs et les conversions. "
            "Je gère les minuteurs, les rappels, même répétés comme « tous les lundis à 20 heures », "
            "le réveil, le chronomètre et ta liste de courses. "
            "J'ouvre et je ferme les applications, je place les fenêtres, je règle le son, "
            "je mets de la musique sur YouTube, et je fais les raccourcis comme copier ou coller. "
            "Je peux aussi lire ou résumer un texte que tu as copié, et regarder ton écran. "
            "Dis « active le mode nuit » pour que je réponde par écrit, ou « active le mode enfant » "
            "pour les vidéos YouTube Kids, les quiz, les devinettes et les longues histoires. "
            "Je te donne l'heure dans une autre ville, les alertes météo, une recette étape par étape, "
            "les anniversaires de tes proches, et je rouvre ton dernier téléchargement ou tes onglets. "
            "Il y a aussi le mode cinéma et le mode invité. "
            "Pour la famille : les profils, le calendrier, les messages, le quiz, les devoirs et le défi du jour. "
            "Je connais aussi le prix des carburants près de chez toi, les vacances scolaires, les jours fériés, "
            "l'éphéméride du jour, et je te rappelle quelle poubelle sortir. "
            "Avec la Freebox : qui t'a appelé, l'état d'Internet, les appareils connectés et un Wi-Fi invité avec "
            "son QR code. Je pilote aussi la télé et l'Apple TV, je regarde l'encre de l'imprimante, je lis ton "
            "agenda (Google, Outlook, iCloud : dis « relie mon agenda »), et je lis ou j'envoie tes mails après ton accord (dis « relie mes mails »). "
            "Tu peux aussi régler ma façon de te parler : plus bref, plus détaillé, plus ou moins d'humour. "
            "Et dis « ouvre les réglages » pour tout régler, avec l'aide complète. "
            "Pour tout le reste, pose-moi simplement ta question : je la confie à Claude.")


# ---------- Clavier ----------

class _CLAVIER(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _SOURIS(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_size_t)]


class _UNION(ctypes.Union):
    _fields_ = [("clavier", _CLAVIER), ("souris", _SOURIS)]


class _ENTREE(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _UNION)]


CTRL, MAJ, ALT = 0x11, 0x10, 0x12
_ETENDUES = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E}   # flèches, Page préc./suiv., Début, Fin


def touches(*codes, repetitions=1):
    """Appuie ensemble sur les touches données (ex. CTRL, 0x43 = Ctrl+C), puis les relâche."""
    sequence = []
    for _ in range(repetitions):
        sequence += [(c, 0) for c in codes] + [(c, 2) for c in reversed(codes)]
    entrees = (_ENTREE * len(sequence))()
    for i, (code, drapeau) in enumerate(sequence):
        entrees[i].type = 1
        entrees[i].u.clavier = _CLAVIER(code, 0, drapeau | (1 if code in _ETENDUES else 0), 0, 0)
    return ctypes.windll.user32.SendInput(len(entrees), entrees, ctypes.sizeof(_ENTREE))


def _plus_tard(*codes, repetitions=1):
    """La touche part 0,3 s plus tard : le temps que Jarvis ait fini d'écouter, la bonne fenêtre reste au premier plan."""
    threading.Timer(0.3, touches, args=codes, kwargs={"repetitions": repetitions}).start()


_RACCOURCIS = [
    (r"(?:copie|copier|copies)(?: ça| ca| ceci| le texte| la sélection| la selection| tout)?", (CTRL, 0x43), "Copié."),
    (r"(?:colle|coller|colles)(?: ça| ca| ici| le texte)?", (CTRL, 0x56), "Collé."),
    (r"(?:coupe|couper)(?: ça| ca| le texte| la sélection| la selection)", (CTRL, 0x58), "Coupé."),
    (r"coupe", (CTRL, 0x58), "Coupé."),
    (r"(?:annule|annuler)(?: ça| ca| la dernière action| la derniere action| la frappe| ce que j'ai fait)|"
     r"(?:fais )?(?:contrôle|controle|ctrl) z", (CTRL, 0x5A), "Annulé."),
    (r"(?:refais|refaire|rétablis|retablis)(?: ça| ca| la dernière action)?|(?:fais )?(?:contrôle|controle|ctrl) y",
     (CTRL, 0x59), "C'est fait."),
    (r"(?:enregistre|enregistrer|sauvegarde|sauvegarder)(?: ça| ca| le fichier| le document| mon travail)?",
     (CTRL, 0x53), "Enregistré."),
    (r"(?:sélectionne|selectionne|sélectionner) tout(?: le texte)?|tout sélectionner|tout selectionner",
     (CTRL, 0x41), "Tout est sélectionné."),
    (r"(?:imprime|imprimer)(?: ça| ca| la page| le document)?", (CTRL, 0x50), "J'ouvre l'impression."),
    (r"(?:ouvre )?(?:un )?nouvel onglet", (CTRL, 0x54), "Nouvel onglet."),
    (r"ferme (?:l'onglet|cet onglet|l'onglet actuel)", (CTRL, 0x57), "Onglet fermé."),
    (r"(?:rouvre|réouvre|rouvrir) (?:l'onglet|le dernier onglet)(?: fermé)?", (CTRL, MAJ, 0x54), "Onglet rouvert."),
    (r"onglet suivant", (CTRL, 0x09), "Onglet suivant."),
    (r"onglet précédent|onglet precedent", (CTRL, MAJ, 0x09), "Onglet précédent."),
    (r"(?:actualise|rafraîchis|rafraichis|recharge)(?: la page| ça)?", (0x74,), "J'actualise."),
]


def commande_raccourci(t):
    phrase = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    for motif, codes, reponse in _RACCOURCIS:
        if re.fullmatch(motif, phrase):
            _plus_tard(*codes)
            return reponse
    return None


def _fenetre_active():
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    tampon = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, tampon, n + 1)
    return tampon.value


def commande_avance(t):
    """« avance de 30 secondes », « recule d'une minute » dans la vidéo ou la musique de la fenêtre active."""
    t = t.replace("’", "'")
    # « avance » est souvent mal entendu : « avant de », « à vent de », « six de », « va de »...
    t = re.sub(r"^\W*(?:jarvis\W+)?(?:avant|à vent|a vent|avant ce|six|cie|va|vas|avancé|avancez|avances)"
               r"(?=\s+(?:de |d')\s*\S+\s+(?:secondes?|minutes?)\b)", "avance", t)
    t = re.sub(r"^\W*(?:jarvis\W+)?(?:recul|reculent|reculez|reculé|recules|requiert)(?=\s+(?:de |d'))", "recule", t)
    m = re.match(r"^\W*(?:jarvis\W+)?(?P<sens>avance|avancer|recule|reculer|reviens|revenir|retourne)"
                 r"(?: la vidéo| la video| la musique| le film)?(?: en arrière| en avant)?\s+(?:de |d')\s*(?P<duree>.+?)\W*$", t)
    if not m:
        # « de 30 secondes » tout seul (le verbe s'est perdu) : on avance, si une vidéo est au premier plan
        m = re.match(r"^\W*(?:jarvis\W+)?(?P<sens>)(?:de |d')\s*(?P<duree>\S+\s+(?:secondes?|minutes?))\W*$", t)
        if not m or not re.search(r"youtube|netflix|vlc|lecteur|film|vidéo|video|prime video|disney", _fenetre_active().lower()):
            return None
    mots = _decouper(m.group("duree"))
    if mots and mots[0] in ("une", "un") and len(mots) == 2:
        valeur, j = 1, 1
    else:
        valeur, j = _lire_nombre(mots, 0)
    if valeur is None or j >= len(mots):
        return None
    unite = mots[j]
    secondes = valeur * (60 if unite.startswith("minute") else 1 if unite.startswith("seconde") else 0)
    if not secondes:
        return None
    en_arriere = m.group("sens").startswith(("recul", "revien", "reven", "retourn"))
    if "youtube" in _fenetre_active().lower():
        # Sur YouTube, J et L reculent ou avancent de 10 secondes, les flèches de 5 secondes
        dizaines, reste = divmod(int(secondes), 10)
        cinq = round(reste / 5) if dizaines else max(1, round(reste / 5))

        def appuyer():
            if dizaines:
                touches(0x4A if en_arriere else 0x4C, repetitions=dizaines)
            if cinq:
                touches(0x25 if en_arriere else 0x27, repetitions=cinq)
        threading.Timer(0.3, appuyer).start()
    else:
        # Ailleurs, les flèches gauche et droite : 5 secondes dans la plupart des lecteurs (YouTube, Netflix...)
        _plus_tard(0x25 if en_arriere else 0x27, repetitions=max(1, round(secondes / 5)))
    duree = _duree_chrono(secondes)
    duree = "d'une minute" if duree == "1 minute" else "de " + duree        # « je recule d'une minute »
    return ("Je recule " if en_arriere else "J'avance ") + duree + "."


# ---------- Volume d'une seule application ----------

_ALIAS_APPLIS = {"chrome": "chrome", "google chrome": "chrome", "google": "@navigateur", "edge": "msedge",
                 "microsoft edge": "msedge", "firefox": "firefox", "spotify": "spotify", "discord": "discord",
                 "vlc": "vlc", "teams": "ms-teams", "steam": "steam", "deezer": "deezer", "opera": "opera",
                 "brave": "brave", "netflix": "netflix", "youtube": "@navigateur", "le navigateur": "@navigateur",
                 "navigateur": "@navigateur", "internet": "@navigateur", "jeu": "", "whatsapp": "whatsapp", "zoom": "zoom", "skype": "skype"}


def _sessions_son():
    from pycaw.pycaw import AudioUtilities
    sessions = []
    for session in AudioUtilities.GetAllSessions():
        try:
            if session.Process:
                sessions.append((session.Process.name().lower().removesuffix(".exe"), session))
        except Exception:
            continue
    return sessions


def commande_volume_appli(t):
    m = re.search(r"\b(?:son|volume)\s+(?:de |du |d'|des |sur )(?:l'application |l'appli |la fenêtre )?(?P<appli>.+?)"
                  r"(?:\s+(?:à|a|sur)\s+(?P<niveau>\S+)(?: pour cent| %)?)?\W*$", t.replace("’", "'"))
    if not m:
        return None
    appli = m.group("appli").strip()
    appli = re.sub(r"^(?:le |la |les )", "", appli)
    if appli in ("pc", "l'ordinateur", "ordinateur", "ordi", "système", "systeme", "base", "fond"):
        return None
    sessions = _sessions_son()
    cible = _ALIAS_APPLIS.get(appli, appli.replace(" ", ""))
    noms = sorted({n for n, _ in sessions})
    if cible == "@navigateur":
        # le navigateur qui joue du son, celui de Windows en priorité
        import jarvis_web
        defaut = jarvis_web.navigateur_par_defaut()["programme"]
        cible = next((p for p in [defaut] + list(jarvis_web.NAVIGATEURS) if p in noms), defaut)
    if cible not in noms:
        proches = difflib.get_close_matches(cible, noms, n=1, cutoff=0.6)
        if not proches:
            proches = [n for n in noms if cible and (cible in n or n in cible)][:1]
        if not proches:
            return f"{appli.capitalize()} ne joue aucun son en ce moment."
        cible = proches[0]
    volumes = [s.SimpleAudioVolume for n, s in sessions if n == cible]
    actuel = round(volumes[0].GetMasterVolume() * 100)
    pas = 15
    niveau = None
    if m.group("niveau"):
        valeur, _ = _lire_nombre(_decouper(m.group("niveau")), 0)
        if valeur is not None:
            niveau = max(0, min(100, int(valeur)))
    if re.search(r"\b(coupe|couper|sourdine|muet|mute)\b", t):
        for v in volumes:
            v.SetMute(1, None)
        return f"Le son de {appli} est coupé."
    if re.search(r"\b(remets|remet|réactive|rétablis|rallume)\b", t) and niveau is None:
        for v in volumes:
            v.SetMute(0, None)
        return f"Le son de {appli} est remis."
    if niveau is None:
        if re.search(r"\b(monte|monter|augmente|augmenter|plus fort)\b", t):
            niveau = min(100, actuel + pas)
        elif re.search(r"\b(baisse|baisser|diminue|diminuer|moins fort)\b", t):
            niveau = max(0, actuel - pas)
        elif re.search(r"\b(quel|combien)\b", t):
            return f"Le son de {appli} est à {actuel} pour cent."
        else:
            return None
    for v in volumes:
        v.SetMute(0, None)
        v.SetMasterVolume(niveau / 100, None)
    return f"Son de {appli} à {niveau} pour cent."


# ---------- Mode sombre ou clair de Windows ----------

def commande_theme(t):
    m = re.search(r"\b(?:mode|thème|theme)\s+(?P<quoi>sombre|clair|noir|blanc|foncé|fonce)\b", t)
    if not m:
        return None
    sombre = m.group("quoi") in ("sombre", "noir", "foncé", "fonce")
    if re.search(r"\b(désactive|desactive|enlève|enleve|retire|arrête|arrete|quitte|sors du)\b", t):
        sombre = not sombre
    import winreg
    cle = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cle, 0, winreg.KEY_SET_VALUE) as k:
        for nom in ("AppsUseLightTheme", "SystemUsesLightTheme"):
            winreg.SetValueEx(k, nom, 0, winreg.REG_DWORD, 0 if sombre else 1)
    resultat = ctypes.c_size_t()                  # prévient Windows et les applications du changement
    ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, "ImmersiveColorSet", 0x0002, 3000,
                                             ctypes.byref(resultat))
    return "Mode sombre activé." if sombre else "Mode clair activé."


def rapide(t):
    """Vrai pour une commande pratique comprise sans la retranscription précise (Whisper) : environ 2 s de gagnées."""
    phrase = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    return (any(re.fullmatch(motif, phrase) for motif, _, _ in _RACCOURCIS)
            or bool(re.search(r"\b(chrono|chronomètre)\b", t)) or bool(_AIDE.search(t))
            or bool(re.search(r"\b(?:mode|thème|theme)\s+(?:sombre|clair)\b", t)))


def liste_parmi(textes):
    """Ajout à une liste : Whisper invente parfois des mots (« du ping » pour « du pain ») alors que Vosk, qui ne
    connaît que de vrais mots français, a bien entendu. Si les deux versions sont comprises, celle de Vosk (la
    dernière) est retenue ; sinon, la première comprise."""
    textes = [x.lower().replace("’", "'").strip(" .!?") for x in textes if x]
    analyses = [commande_liste_essai(x) for x in textes]
    if len(textes) < 2 or not all(analyses):
        return None
    # Chaque élément : la version qui ressemble le plus à une course courante, sinon celle de Vosk (la dernière)
    morceaux = [[e.strip(" ,.") for e in re.split(r",| et ", a.group("quoi")) if e.strip(" ,.")] for a in analyses]
    if len({len(m) for m in morceaux}) == 1:
        choisis = []
        for versions in zip(*morceaux):
            notes = [_connu(v) for v in versions]
            meilleur = max(range(len(versions)), key=lambda i: (notes[i][1], i))
            choisis.append(notes[meilleur][0] if notes[meilleur][1] else versions[-1])
        quelle = analyses[-1].group("quelle") or ""
        return commande_liste(f"ajoute {', '.join(choisis)} à la liste{quelle}")
    return commande_liste(textes[-1])


def commande_liste_essai(t):
    """L'analyse d'un ajout à une liste (sans rien écrire), ou None."""
    t = t.lower().replace("’", "'").strip(" .!?")
    return re.match(r"^\W*(?:jarvis\W+)?(?:ajoutes?|ajouter|ajout|rajoutes?|rajouter|mets|mettre|inscris|note)\s+(?P<quoi>.+?)\s+"
                    r"(?:à|a|sur|dans)\s+" + _NOM_LISTE + r"\W*$", t)
