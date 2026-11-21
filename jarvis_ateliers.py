# -*- coding: utf-8 -*-
"""
JARVIS - les ateliers du profil enfant, sur la tablette.

Le réacteur remonte en haut de l'écran et une grande fenêtre s'ouvre en dessous :
  - calcul      « on fait du calcul », « les tables de 5 » : « 3 + 2 = ? » écrit en gros, l'enfant répond à la voix ;
  - mot         « comment s'écrit chien ? » : le mot en gros, épelé lettre par lettre ;
  - dictée      « fais-moi une dictée » : Jarvis dit un mot, l'enfant l'écrit avec les lettres de l'écran ;
  - animal      « devine l'animal » : un animal flou qui se précise peu à peu ;
  - heure       « on apprend l'heure » : une horloge à aiguilles, l'enfant dit l'heure.
D'abord l'enfant essaie seul ; s'il se trompe ou ne dit rien, deux ou trois réponses possibles s'affichent (dont la
bonne) et il touche celle qu'il pense juste. Chaque bonne réponse rapporte une étoile, gardée dans son profil ; toutes
les 10 étoiles, une récompense (une blague, ou un nouveau thème de couleurs pour son réacteur).
Le niveau est celui du CE1 : additions et soustractions jusqu'à 20, tables de 2, 5 et 10, heures et demi-heures.
"""
import datetime
import json
import os
import random
import re
import threading
import time
import unicodedata

DUREE_JEU = 15 * 60              # secondes sans réponse : l'atelier est oublié
_jeux = {}                       # profil -> l'atelier en cours (en mémoire seulement)
_verrou = threading.Lock()
_etoiles_essai = {}              # pendant un mode essai : les étoiles ne sont pas gardées sur le disque

BRAVO = ("Bravo !", "Super !", "Génial !", "C'est ça !", "Bien joué !", "Excellent !", "Parfait !", "Trop fort !")
ENCORE = ("Pas tout à fait.", "Presque !", "Oups, ce n'est pas ça.", "Essaie encore.")
BLAGUES = (
    "Que dit un zéro à un huit ? Jolie ceinture !",
    "Pourquoi les poissons n'aiment pas jouer au tennis ? Parce qu'ils ont peur du filet !",
    "Qu'est-ce qui est jaune et qui attend ? Jonathan !",
    "Pourquoi le livre de maths est triste ? Parce qu'il a trop de problèmes !",
    "Comment appelle-t-on un chat tombé dans un pot de peinture le jour de Noël ? Un chat-peint de Noël !",
    "Quel est l'animal le plus heureux ? Le hibou, parce que sa femme est chouette !",
    "Pourquoi les canards ont-ils des plumes ? Pour couvrir leur derrière !",
    "Que fait une fraise sur un cheval ? Tagada, tagada !",
)
# Thèmes de couleurs gagnés avec les étoiles (20, 40, 60 étoiles) ; les autres paliers donnent une blague
RECOMPENSES = (("étoile d'or", ("#ffd23f", "#ffb52e", "#fff3b0")),
               ("arc-en-ciel", ("#ff3b3b", "#ffd23f", "#3fa9ff")),
               ("fusée", ("#5b6cff", "#ff8c42", "#e8f4ff")))

ANIMAUX = (("🐶", ("chien", "chiot", "toutou")), ("🐱", ("chat", "chaton", "minou")), ("🐰", ("lapin",)),
           ("🐮", ("vache",)), ("🐷", ("cochon", "porc")), ("🐸", ("grenouille",)), ("🦁", ("lion",)),
           ("🐯", ("tigre",)), ("🐵", ("singe",)), ("🐘", ("elephant",)), ("🐴", ("cheval", "poney")),
           ("🐑", ("mouton", "brebis", "agneau")), ("🐔", ("poule", "coq", "poulet")), ("🦆", ("canard",)),
           ("🐧", ("pingouin", "manchot")), ("🐢", ("tortue",)), ("🐟", ("poisson",)), ("🐬", ("dauphin",)),
           ("🦋", ("papillon",)), ("🐝", ("abeille",)), ("🐌", ("escargot",)), ("🦊", ("renard",)),
           ("🐻", ("ours", "nounours")), ("🐼", ("panda",)), ("🐭", ("souris",)), ("🦉", ("hibou", "chouette")),
           ("🐍", ("serpent",)), ("🦀", ("crabe",)), ("🐳", ("baleine",)), ("🐊", ("crocodile", "croco", "alligator")))
NOMS_ANIMAUX = {"elephant": "éléphant"}

MOTS_DICTEE = ("chat", "chien", "lune", "ami", "vélo", "lapin", "pomme", "table", "rouge", "livre", "école", "maison",
               "jardin", "fleur", "train", "ballon", "crayon", "mouton", "salade", "tomate", "cheval", "bateau",
               "gâteau", "poisson", "oiseau", "soleil", "étoile", "souris", "tortue", "neige", "nuage", "forêt",
               "musique", "copain", "papa", "maman", "frère", "pluie", "lit", "robe")
ARTICLES = {"chat": "le", "chien": "le", "lune": "la", "ami": "un", "vélo": "le", "lapin": "le", "pomme": "la",
            "table": "la", "livre": "le", "école": "l'", "maison": "la", "jardin": "le", "fleur": "la", "train": "le",
            "ballon": "le", "crayon": "le", "mouton": "le", "salade": "la", "tomate": "la", "cheval": "le",
            "bateau": "le", "gâteau": "le", "poisson": "le", "oiseau": "l'", "soleil": "le", "étoile": "l'",
            "souris": "la", "tortue": "la", "neige": "la", "nuage": "le", "forêt": "la", "musique": "la",
            "copain": "le", "frère": "le", "pluie": "la", "lit": "le", "robe": "la"}

NOMS_LETTRES = {"y": "i grec", "w": "double V", "é": "E accent aigu", "è": "E accent grave", "ê": "E accent circonflexe",
                "ë": "E tréma", "à": "A accent grave", "â": "A accent circonflexe", "ç": "C cédille",
                "î": "I accent circonflexe", "ï": "I tréma", "ô": "O accent circonflexe", "ù": "U accent grave",
                "û": "U accent circonflexe", "ü": "U tréma", "œ": "O E collés", "æ": "A E collés", "'": "apostrophe",
                "-": "trait d'union", " ": "espace"}


# ---------- Outils ----------

def _simple(texte):
    texte = unicodedata.normalize("NFD", str(texte).lower().replace("’", "'"))
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def _propre(texte):
    t = str(texte).lower().replace("’", "'").strip()
    t = re.sub(r"^\W*(?:dis\W+)?jarvis\W+", "", t)
    return t.strip(" .!?,;:«»\"")


def _nombres(texte):
    """Les nombres dits ou écrits dans la phrase, dans l'ordre (« cinq », « 12 », « vingt-deux »)."""
    import jarvis_pratique as p
    texte = re.sub(r"\b(?:un|une)\s+(?=[a-zàâäçéèêëîïôöùûü])(?!(?:et|virgule|cent|mille)\b)", " ", str(texte).lower())   # « une histoire » n'est pas 1
    mots = p._decouper(texte)
    trouves, i = [], 0
    while i < len(mots):
        valeur, j = p._lire_nombre(mots, i)
        if valeur is not None and j > i:
            trouves.append(valeur)
            i = j
        else:
            i += 1
    return trouves


def _je_sais_pas(t):
    return bool(re.search(r"\b(?:je (?:ne )?sais pas|j'sais pas|chais pas|aide[- ]moi|un indice|indice|"
                          r"je (?:ne )?trouve pas|j'y arrive pas|je n'y arrive pas|aucune idée)\b", t))


_ARRET = re.compile(r"^(?:stop|arr[eê]te|arr[eê]tons|on arr[eê]te|c'est fini|j'ai fini|fini|termin[ée]|fin|"
                    r"j'en ai marre|on a fini)\b|\b(?:arr[eê]te|stop|fin|termine|quitte|ferme)\b.*\b(?:jeu|calcul|atelier|"
                    r"dict[ée]e|heure|animaux?|exercices?)\b")


# ---------- Les étoiles ----------

def _fichier_etoiles(dossier):
    return os.path.join(dossier, "etoiles.json")


def _lire_etoiles(dossier):
    try:
        with open(_fichier_etoiles(dossier), encoding="utf-8") as f:
            lu = json.load(f)
        return lu if isinstance(lu, dict) else {}
    except (OSError, ValueError):
        return {}


def etoiles(dossier, ident, essai=False):
    """{"total", "jours": {"AAAA-MM-JJ": n}, "recompenses": [noms de thèmes]} pour ce profil."""
    if essai and ident in _etoiles_essai:
        return _etoiles_essai[ident]
    e = _lire_etoiles(dossier).get(ident) or {}
    return {"total": int(e.get("total", 0)), "jours": dict(e.get("jours") or {}), "recompenses": list(e.get("recompenses") or []),
            "niveaux": dict(e.get("niveaux") or {})}


def _ecrire(dossier, ident, e, essai):
    """Garde les étoiles (et les niveaux) de ce profil ; en mode essai, seulement en mémoire."""
    if essai:
        _etoiles_essai[ident] = e
        return
    tout = _lire_etoiles(dossier)
    tout[ident] = e
    try:
        os.makedirs(dossier, exist_ok=True)
        with open(_fichier_etoiles(dossier) + ".tmp", "w", encoding="utf-8") as f:
            json.dump(tout, f, ensure_ascii=False)
        os.replace(_fichier_etoiles(dossier) + ".tmp", _fichier_etoiles(dossier))
    except OSError as erreur:
        print("Ateliers (étoiles) :", erreur)


# ---------- La difficulté s'adapte : 3 bonnes réponses du premier coup d'affilée, ça monte ; 2 ratées d'affilée, ça descend
NIVEAU_DEPART, NIVEAU_MAX = 2, 3
SERIE_POUR_MONTER, RATEES_POUR_DESCENDRE = 3, 2


def niveau(dossier, ident, nom, essai=False):
    return int(etoiles(dossier, ident, essai)["niveaux"].get(nom, NIVEAU_DEPART))


def _changer_niveau(dossier, ident, nom, essai, ecart):
    """Monte ou descend d'un niveau dans cet atelier. Renvoie le nouveau niveau (ou None s'il n'a pas bougé)."""
    with _verrou:
        e = etoiles(dossier, ident, essai)
        avant = int(e["niveaux"].get(nom, NIVEAU_DEPART))
        apres = max(1, min(NIVEAU_MAX, avant + ecart))
        if apres == avant:
            return None
        e["niveaux"][nom] = apres
        _ecrire(dossier, ident, e, essai)
        return apres


def prochaine(total):
    """Ce que l'enfant gagnera à la prochaine dizaine d'étoiles : {"reste", "faites", "quoi"}."""
    palier = total // 10 + 1
    if palier % 2 == 0 and palier // 2 <= len(RECOMPENSES):
        quoi = "le thème « " + RECOMPENSES[palier // 2 - 1][0] + " »"
    else:
        quoi = "une blague"
    return {"reste": 10 - total % 10, "faites": total % 10, "quoi": quoi}


def tableau(dossier, ident, essai=False):
    """Le tableau des étoiles, affiché dans la fenêtre des ateliers."""
    e = etoiles(dossier, ident, essai)
    aujourd = e["jours"].get(datetime.date.today().isoformat(), 0)
    return {"total": e["total"], "aujourdhui": aujourd, "gagnes": [nom for nom, _ in RECOMPENSES if nom in e["recompenses"]],
            "prochaine": prochaine(e["total"])}


def recompenses(dossier, ident):
    """Les thèmes gagnés par ce profil : {nom: (trois couleurs)}."""
    gagnes = set(etoiles(dossier, ident).get("recompenses", []))
    return {nom: couleurs for nom, couleurs in RECOMPENSES if nom in gagnes}


def _gagner(dossier, ident, essai):
    """Une étoile de plus. Renvoie (total, texte de la récompense ou « »)."""
    with _verrou:
        e = etoiles(dossier, ident, essai)
        e["total"] += 1
        jour = datetime.date.today().isoformat()
        e["jours"][jour] = e["jours"].get(jour, 0) + 1
        e["jours"] = dict(sorted(e["jours"].items())[-60:])
        texte = ""
        if e["total"] % 10 == 0:
            palier = e["total"] // 10
            if palier % 2 == 0 and palier // 2 <= len(RECOMPENSES):
                nom = RECOMPENSES[palier // 2 - 1][0]
                if nom not in e["recompenses"]:
                    e["recompenses"].append(nom)
                texte = (f" Waouh, {e['total']} étoiles ! Tu as gagné un nouveau thème pour ton réacteur : « {nom} ». "
                         "Demande à un adulte de le choisir dans la roue, à Thème.")
            else:
                texte = f" Waouh, {e['total']} étoiles ! Tu as gagné une blague : {BLAGUES[(palier - 1) % len(BLAGUES)]}"
        _ecrire(dossier, ident, e, essai)
        return e["total"], texte


def _bilan_etoiles(dossier, ident, essai):
    e = etoiles(dossier, ident, essai)
    aujourd = e["jours"].get(datetime.date.today().isoformat(), 0)
    lundi = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    semaine = sum(n for jour, n in e["jours"].items() if jour >= lundi.isoformat())
    if not e["total"]:
        return "Tu n'as pas encore d'étoile. Dis « on fait du calcul » pour en gagner !"
    return (f"Tu as {e['total']} étoile{'s' if e['total'] > 1 else ''} en tout : {aujourd} aujourd'hui "
            f"et {semaine} cette semaine. Encore {10 - e['total'] % 10} et tu gagnes {prochaine(e['total'])['quoi']} !")


# ---------- Les questions ----------

def _question_calcul(genre, niv=NIVEAU_DEPART):
    """niv 1 : petits nombres (jusqu'à 10, tables jusqu'à 5 fois) ; 2 : jusqu'à 20, tables de 2, 5, 10 ;
    3 : jusqu'à 60 et tables de 3 et 4 en plus (niveau CE1)."""
    fois_max = 5 if niv <= 1 else 10
    if genre == "table":
        table = random.choice((2, 10) if niv <= 1 else (2, 5, 10) if niv == 2 else (2, 3, 4, 5, 10))
        n = random.randint(1, fois_max)
        a, b, signe, dit, juste = n, table, "×", "fois", n * table
    elif genre.startswith("table"):
        table = int(genre[5:])
        n = random.randint(1, fois_max)
        a, b, signe, dit, juste = n, table, "×", "fois", n * table
    else:
        if genre == "melange":
            genre = random.choice(("addition", "addition", "soustraction", "table"))
            if genre == "table":
                return _question_calcul("table", niv)
        if genre == "addition":
            if niv <= 1:
                a = random.randint(1, 8)
                b = random.randint(1, 10 - a)
            elif niv == 2:
                a = random.randint(1, 12)
                b = random.randint(1, 20 - a) if a < 20 else 1
            else:
                a = random.randint(10, 45)
                b = random.randint(2, 60 - a)
            signe, dit, juste = "+", "plus", a + b
        else:
            if niv <= 1:
                a = random.randint(3, 10)
                b = random.randint(1, a - 1)
            elif niv == 2:
                a = random.randint(4, 20)
                b = random.randint(1, min(10, a))
            else:
                a = random.randint(20, 60)
                b = random.randint(3, 20)
            signe, dit, juste = "−", "moins", a - b
    autres = {juste + d for d in (-2, -1, 1, 2, 10, -10) if juste + d >= 0 and juste + d != juste}
    choix = random.sample(sorted(autres), 2) + [juste]
    random.shuffle(choix)
    return {"juste": juste, "ecrit": f"{a} {signe} {b} = ?", "dit": f"Combien font {a} {dit} {b} ?",
            "choix": [str(c) for c in choix]}


def _ecrire_heure(h, m):
    return f"{h} h" + (f" {m:02d}" if m else "")


def _question_heure(niv=NIVEAU_DEPART):
    """niv 1 : heures pile ; 2 : et demie en plus ; 3 : et quart, moins le quart en plus."""
    h = random.randint(1, 12)
    m = random.choice((0,) if niv <= 1 else (0, 0, 30) if niv == 2 else (0, 30, 15, 45))
    autres = set()
    if m:
        autres.add((m // 5 if m // 5 <= 12 else h, h * 5 % 60 if h * 5 % 60 != m else 0))   # aiguilles confondues
    autres.update({(h % 12 + 1, m), ((h - 2) % 12 + 1, m), (h, (m + 30) % 60)})
    autres = [x for x in autres if x != (h, m) and 1 <= x[0] <= 12]
    choix = random.sample(autres, 2) + [(h, m)]
    random.shuffle(choix)
    return {"juste": (h, m), "horloge": {"h": h, "m": m}, "dit": "Quelle heure indique l'horloge ?",
            "choix": [_ecrire_heure(*c) for c in choix]}


def _heure_dite(texte):
    """(heure 0-11, minutes) lue dans « trois heures et demie », « 15 h 30 », « midi », « quatre heures moins le quart »."""
    import jarvis_pratique as p
    t = _propre(texte).replace("-", " ")
    t = re.sub(r"\bmidi\b", "12 heures", t)
    t = re.sub(r"\bminuit\b", "12 heures", t)
    t = re.sub(r"(\d)h(\d)", r"\1 h \2", t)
    mots = p._decouper(t)
    heure, minutes, fin = None, 0, None
    for i, mot in enumerate(mots):
        if mot in ("heure", "heures", "h"):
            for j in range(max(0, i - 4), i):
                v, k = p._lire_nombre(mots, j)
                if v is not None and k == i:
                    heure, fin = int(v), i + 1
                    break
            if heure is not None:
                break
    if heure is None:
        nombres = _nombres(t)
        if not nombres:
            return None
        heure = int(nombres[0])
        minutes = int(nombres[1]) if len(nombres) > 1 else 0
    else:
        reste = " ".join(mots[fin:])
        if re.search(r"\bet demie?\b", reste):
            minutes = 30
        elif re.search(r"\bet quart\b", reste):
            minutes = 15
        elif re.search(r"\bmoins (?:le )?quart\b", reste):
            heure, minutes = heure - 1, 45
        else:
            v, k = p._lire_nombre(mots, fin) if fin < len(mots) else (None, fin)
            if fin < len(mots) and mots[fin] == "moins":
                v, k = p._lire_nombre(mots, fin + 1)
                if v is not None:
                    heure, minutes = heure - 1, 60 - int(v)
            elif v is not None:
                minutes = int(v)
    return heure % 12, minutes % 60


def _animal_dit(texte):
    """L'animal nommé dans la phrase (son émoji), ou None."""
    t = _simple(_propre(texte))
    for emoji, noms in ANIMAUX:
        for nom in noms:
            if re.search(r"\b" + re.escape(nom) + r"[sx]?\b", t):
                return emoji
    return None


def _nom_animal(emoji):
    nom = next(noms[0] for e, noms in ANIMAUX if e == emoji)
    return NOMS_ANIMAUX.get(nom, nom)


def _question_animal(deja):
    restants = [a for a in ANIMAUX if a[0] not in deja] or list(ANIMAUX)
    emoji, noms = random.choice(restants)
    autres = random.sample([a for a in ANIMAUX if a[0] != emoji], 2)
    choix = [_nom_animal(e) for e, _ in autres] + [_nom_animal(emoji)]
    random.shuffle(choix)
    return {"juste": emoji, "animal": emoji, "dit": "Devine quel animal se cache derrière le flou !", "choix": choix}


ECRIT_DICTEE = "Écris le mot que tu entends. Dis « répète » pour l'entendre encore."


def _question_dictee(deja, niv=NIVEAU_DEPART):
    """niv 1 : mots de 4 lettres au plus ; 2 : 5 lettres au plus ; 3 : tous les mots."""
    longueur = 4 if niv <= 1 else 5 if niv == 2 else 99
    possibles = [m for m in MOTS_DICTEE if len(m) <= longueur] or list(MOTS_DICTEE)
    restants = [m for m in possibles if m not in deja] or possibles
    mot = random.choice(restants)
    article = ARTICLES.get(mot, "")
    groupe = f"{article}{mot}" if article.endswith("'") else f"{article} {mot}".strip()
    return {"juste": mot, "dit": f"Écris le mot : {mot}. {groupe.capitalize()}.", "longueur": len(mot)}


def _mot_tape_juste(tape, mot):
    """Le mot de la dictée est-il bien écrit ? L'article dit avec lui est accepté, avec ou sans espace
    (« la robe », « larobe », « l'école ») ; les accents comptent."""
    tape = " ".join(tape.replace("’", "'").split())
    if tape == mot:
        return True
    article = ARTICLES.get(mot, "")
    colle = tape.replace(" ", "")
    return bool(article) and colle in (article.replace(" ", "") + mot, "le" + mot, "la" + mot, "un" + mot, "une" + mot,
                                       "l'" + mot)


def epeler(mot):
    """« C, H, I, E, N » à dire à voix haute (les accents sont nommés)."""
    noms = []
    for c in mot:
        bas = c.lower()
        noms.append(NOMS_LETTRES.get(bas, c.upper()))
    return ", ".join(noms)


# ---------- Ce que l'enfant demande ----------

_CALCUL = re.compile(r"\b(?:calculs?|additions?|soustractions?|tables? (?:de|du) (?:\d+|deux|cinq|dix|trois|quatre|multiplication)|"
                     r"tables de multiplication|maths?|math[ée]matiques?|multiplications?)\b|\bles tables\b")   # pas « mets la table »
_VERBE = re.compile(r"\b(?:on (?:fait|joue|refait)|faire|fais|jouer|jeu|veux|voudrais|exercices?|entra[iî]ne|r[ée]viser|"
                    r"revoir|apprendre|pose|donne|travailler|commence|lance|encore)\b")
_MOT = re.compile(r"(?:comment (?:s'|ça s'|ca s'|est-ce qu'on |est ce qu'on |on |tu )?[ée]cri[st]|[ée]pell?e(?:[- ]moi)?|"
                  r"[ée]peler|comment (?:s'|ça s'|ca s')[ée]pell?e)\s+(?:le mot\s+|la mot\s+)?(?P<mot>[^?!.,;:]{1,40})")
_MOT_AVANT = re.compile(r"^(?:le mot\s+)?(?P<mot>[^?!.,;:]{1,30}?),? comment (?:ça|ca|il|elle|on|tu) (?:s'|l')?[ée]cri[st]")
_DICTEE = re.compile(r"\bdict[ée]es?\b|\b(?:[ée]crire|[ée]cris) (?:des|un|les) mots?\b")
_ANIMAL = re.compile(r"\bdevine(?:r|tte)?s?\b.*\banimaux?\b|\banimaux?\b.*\bdevine|\bjeu des animaux\b|\bdevine l'animal\b")
_HEURE = re.compile(r"\b(?:apprendre|lire|jouer|jeu|r[ée]viser|exercices?|on (?:fait|apprend|joue))\b.*\bl'heure\b|\bjeu de l'heure\b"
                    r"|\bhorloges?\b")
_ETOILES = re.compile(r"\b(?:combien|mes|nombre)\b.*\b[ée]toiles?\b|\b[ée]toiles?\b.*\b(?:combien|j'ai|gagn)")


def _genre_calcul(t):
    m = re.search(r"\btables? (?:de |du )?(\d+|deux|cinq|dix|trois|quatre)\b", t)
    if m:
        valeur = {"deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "dix": 10}.get(m.group(1)) or int(m.group(1))
        if 2 <= valeur <= 10:
            return f"table{valeur}"
    if re.search(r"\btables\b|multiplications?", t):
        return "table"
    if re.search(r"\badditions?\b", t):
        return "addition"
    if re.search(r"\bsoustractions?\b", t):
        return "soustraction"
    return "melange"


def _affichage(jeu, total, **plus):
    return {"jeu": jeu["nom"], "etoiles": total, "prochaine": prochaine(total), **plus}


def _poser(jeu, dossier, ident, essai, avant=""):
    """Pose la question suivante de l'atelier. Renvoie la réponse pour la tablette."""
    nom = jeu["nom"]
    niv = niveau(dossier, ident, nom, essai)
    if nom == "calcul":
        q = _question_calcul(jeu["genre"], niv)
    elif nom == "heure":
        q = _question_heure(niv)
    elif nom == "animal":
        q = _question_animal(jeu["vus"])
    else:
        q = _question_dictee(jeu["vus"], niv)
    jeu.update(question=q, essais=0, choix=False, silences=0)
    jeu["vus"] = (jeu["vus"] + [q["juste"]])[-12:] if nom in ("animal", "dictee") else jeu["vus"]
    total = etoiles(dossier, ident, essai)["total"]
    plus = {}
    if nom == "calcul":
        plus["grand"] = q["ecrit"]
    elif nom == "heure":
        plus["horloge"] = q["horloge"]
    elif nom == "animal":
        plus["animal"] = q["animal"]
    else:
        plus.update(clavier=True, longueur=q["longueur"])
    fait = {"reponse": (avant + " " + q["dit"]).strip(), "suite": nom != "dictee",
            "atelier": _affichage(jeu, total, **plus)}
    if nom == "dictee":                              # le mot est dit, mais jamais écrit à l'écran (sinon il suffit de recopier)
        fait["ecrit"] = (avant + " " + ECRIT_DICTEE).strip()
    return fait


def _repondre(jeu, t, dossier, ident, essai, parle):
    """Une réponse de l'enfant pendant l'atelier. None si la phrase n'en est pas une (on sort de l'atelier)."""
    q, nom = jeu["question"], jeu["nom"]
    if re.search(r"\b(?:r[ée]p[eè]te|redis|j'ai pas entendu|je n'ai pas entendu|encore une fois)\b", t):
        fait = {"reponse": q["dit"], "suite": nom != "dictee", "atelier": _affichage(jeu, etoiles(dossier, ident, essai)["total"],
                                                                                        **_vue_question(jeu, q))}
        if nom == "dictee":
            fait["ecrit"] = ECRIT_DICTEE
        return fait
    if re.search(r"\b(?:autre|une autre|suivant|suivante|passe|change)\b", t) and len(t.split()) <= 4:
        return _poser(jeu, dossier, ident, essai, "D'accord, une autre.")
    sais_pas = _je_sais_pas(t) or not t
    if nom == "calcul":
        nombres = _nombres(t)
        donne = int(nombres[-1]) if nombres and not sais_pas else None
        juste = donne is not None and donne == q["juste"]
    elif nom == "heure":
        lue = None if sais_pas else _heure_dite(t)
        donne = lue
        juste = lue is not None and lue == (q["juste"][0] % 12, q["juste"][1])
    elif nom == "animal":
        donne = None if sais_pas else _animal_dit(t)
        juste = donne == q["juste"]
    else:
        if parle and not sais_pas:
            return {"reponse": "Écris-le avec les lettres en bas de l'écran, puis touche « Valider ».", "suite": False,
                    "atelier": _affichage(jeu, etoiles(dossier, ident, essai)["total"], **_vue_question(jeu, q))}
        donne = None if sais_pas else _propre(t)
        juste = donne is not None and _mot_tape_juste(donne, q["juste"])
    if donne is None and not sais_pas and len(t.split()) > 4:
        return None                                  # une autre demande : l'atelier s'arrête, Jarvis y répond
    if juste:
        total, recompense = _gagner(dossier, ident, essai)
        du_premier_coup = not jeu["essais"] and not jeu["choix"] and not jeu.get("silences")
        jeu["serie"] = jeu.get("serie", 0) + 1 if du_premier_coup else 0
        jeu["ratees"] = 0
        progres = ""
        if jeu["serie"] >= SERIE_POUR_MONTER and nom != "animal":
            jeu["serie"] = 0
            if _changer_niveau(dossier, ident, nom, essai, +1):
                progres = " Tu es trop fort : je corse un peu !"
        suite = _poser(jeu, dossier, ident, essai, random.choice(BRAVO) + recompense + progres + " Suivante :")
        suite["atelier"].update(gagnee=True, etoiles=total, palier=bool(recompense))
        return suite
    if sais_pas:
        jeu["silences"] = jeu.get("silences", 0) + 1
    else:
        jeu["essais"] += 1
    if not jeu["choix"]:                             # premier échec : les réponses possibles s'affichent
        jeu["choix"] = True
        debut = random.choice(ENCORE) if not sais_pas else "Je t'aide."
        if nom == "dictee":
            indice = q["juste"][0] + " _" * (len(q["juste"]) - 1)
            jeu["indice"] = indice
            texte = f"{debut} Le mot commence par {epeler(q['juste'][0])} et il a {len(q['juste'])} lettres. Réessaie."
        else:
            texte = f"{debut} Choisis la bonne réponse sur l'écran."
        return {"reponse": texte, "suite": False, "atelier": _affichage(jeu, etoiles(dossier, ident, essai)["total"],
                                                                        **_vue_question(jeu, q))}
    if sais_pas and nom != "dictee":
        return {"reponse": "Prends ton temps, et touche la réponse que tu penses juste.", "suite": False,
                "atelier": _affichage(jeu, etoiles(dossier, ident, essai)["total"], **_vue_question(jeu, q))}
    # deuxième échec : la bonne réponse est donnée, puis une nouvelle question
    if nom == "calcul":
        solution = f"{q['ecrit'][:-1]}{q['juste']}."
    elif nom == "heure":
        solution = f"Il était {_ecrire_heure(*q['juste']).replace('h', 'heures')}."
    elif nom == "animal":
        solution = f"C'était un {_nom_animal(q['juste'])}."
    else:
        solution = f"Le mot {q['juste']} s'écrit : {epeler(q['juste'])}."
    jeu["serie"] = 0
    jeu["ratees"] = jeu.get("ratees", 0) + 1
    if jeu["ratees"] >= RATEES_POUR_DESCENDRE and nom != "animal":
        jeu["ratees"] = 0
        if _changer_niveau(dossier, ident, nom, essai, -1):
            solution += " Je te donne des questions un peu plus faciles."
    suite = _poser(jeu, dossier, ident, essai, f"Ce n'est pas grave. {solution} On continue :")
    suite["atelier"]["solution"] = solution
    return suite


def _vue_question(jeu, q):
    """Ce que la fenêtre montre pour la question en cours (avec les choix ou l'indice, s'il y en a)."""
    nom, vue = jeu["nom"], {}
    if nom == "calcul":
        vue["grand"] = q["ecrit"]
    elif nom == "heure":
        vue["horloge"] = q["horloge"]
    elif nom == "animal":
        vue["animal"] = q["animal"]
    else:
        vue.update(clavier=True, longueur=q["longueur"])
        if jeu.get("choix"):
            vue["indice"] = jeu.get("indice", "")
    if jeu.get("choix") and nom != "dictee":
        vue["choix"] = q["choix"]
    return vue


def traiter(texte, profil, dossier, essai=False, parle=True):
    """La réponse de l'atelier ({"reponse", "suite", "atelier"}), ou None si la phrase ne le concerne pas.
    profil : {"id", "enfant", ...} ; dossier : où garder les étoiles ; essai : ne rien garder sur le disque ;
    parle : la phrase a été dite (et non écrite ou touchée à l'écran)."""
    if not profil or not profil.get("enfant"):
        return None
    ident = profil["id"]
    t = _propre(texte)
    oublie = None
    with _verrou:
        jeu = _jeux.get(ident)
        if jeu and time.time() - jeu["quand"] > DUREE_JEU:
            _jeux.pop(ident, None)
            oublie, jeu = jeu, None
    if oublie:                                        # (noté hors du verrou : les étoiles se lisent avec lui)
        _rapport_atelier(oublie, "abandonné (plus de réponse)", dossier, ident, essai)
    if _ETOILES.search(t) and len(t.split()) <= 9:         # « combien j'ai d'étoiles » : le tableau des étoiles s'ouvre
        if jeu and jeu.get("question"):               # pendant un atelier : la question en cours reste affichée
            return {"reponse": _bilan_etoiles(dossier, ident, essai), "suite": False,
                    "atelier": _affichage(jeu, etoiles(dossier, ident, essai)["total"], **_vue_question(jeu, jeu["question"]))}
        tab = tableau(dossier, ident, essai)
        return {"reponse": _bilan_etoiles(dossier, ident, essai), "suite": False,
                "atelier": {"jeu": "etoiles", "tableau": tab, "etoiles": tab["total"], "prochaine": tab["prochaine"]}}
    m = _MOT.search(t) or _MOT_AVANT.search(t)
    if m:
        mot = re.sub(r"^(?:le |la |les |l'|un |une |des |du |de )", "", m.group("mot").strip(" \"«»'")).strip()
        mot = re.sub(r"\s+(?:s'il te pla[iî]t|stp|jarvis)$", "", mot).strip()
        brut = re.search(re.escape(mot), str(texte), re.I)
        if brut and texte.find(brut.group(0)) > 0:
            mot = brut.group(0)                       # la majuscule d'un prénom est gardée
        if 1 <= len(mot) <= 30 and len(mot.split()) <= 3:
            with _verrou:
                _jeux.pop(ident, None)
            return {"reponse": f"{mot.capitalize() if mot.islower() else mot} s'écrit : {epeler(mot)}.", "suite": False,
                    "atelier": {"jeu": "mot", "mot": mot, "epeler": True, "etoiles": etoiles(dossier, ident, essai)["total"]}}
    depart = None
    if _DICTEE.search(t):
        depart = ("dictee", "")
    elif _ANIMAL.search(t):
        depart = ("animal", "")
    elif _HEURE.search(t) and not re.search(r"\bquelle heure\b", t):
        depart = ("heure", "")
    elif _CALCUL.search(t) and (_VERBE.search(t) or len(t.split()) <= 5):        # « les tables de 5 », « du calcul »
        depart = ("calcul", _genre_calcul(t))
    if depart:
        if jeu:
            _rapport_atelier(jeu, "remplacé par un autre atelier", dossier, ident, essai)
        jeu = {"nom": depart[0], "genre": depart[1], "vus": [], "quand": time.time(), "gagnees": 0,
               "debut_total": etoiles(dossier, ident, essai)["total"]}
        with _verrou:
            _jeux[ident] = jeu
        accueil = {"calcul": "C'est parti pour le calcul !", "dictee": "C'est parti pour la dictée !",
                   "animal": "C'est parti, devine l'animal !", "heure": "C'est parti, on lit l'heure !"}[depart[0]]
        return _poser(jeu, dossier, ident, essai, accueil)
    if not jeu:
        return None
    if _ARRET.search(t) or (t in ("stop", "arrête", "fini") ):
        with _verrou:
            _jeux.pop(ident, None)
        _rapport_atelier(jeu, "arrêté par l'enfant", dossier, ident, essai)
        gagnees = etoiles(dossier, ident, essai)["total"] - jeu["debut_total"]
        bilan = (f"Tu as gagné {gagnees} étoile{'s' if gagnees > 1 else ''}. Bravo !" if gagnees
                 else "À bientôt pour gagner des étoiles !")
        return {"reponse": f"D'accord, on arrête. {bilan}", "suite": False, "atelier": {"jeu": "", "fermer": True}}
    jeu["quand"] = time.time()
    reponse = _repondre(jeu, t, dossier, ident, essai, parle)
    if reponse is None:
        with _verrou:
            _jeux.pop(ident, None)
        _rapport_atelier(jeu, "quitté pour une autre demande", dossier, ident, essai)
        return None
    return reponse


def _rapport_atelier(jeu, fin, dossier, ident, essai):
    """Rapports (si l'utilisateur les a acceptés) : le nom de l'atelier, comment il s'arrête, le nombre de questions
    posées et d'étoiles gagnées. Jamais le prénom, ni la voix, ni les réponses de l'enfant."""
    if essai:
        return
    try:
        import jarvis_rapports
        gagnees = etoiles(dossier, ident, essai)["total"] - jeu.get("debut_total", 0)
        jarvis_rapports.atelier(jeu.get("nom", "?"), fin, len(jeu.get("vus") or []), max(0, gagnees))
    except Exception:
        pass


# ---------- Une réponse courte mal comprise ----------
# Whisper écrit souvent mal une réponse d'un seul mot (« treize » devient « Très », « dix » « Disse »). Quand ce qu'il
# a écrit n'est pas une réponse lisible, Vosk réécoute le même son en ne cherchant QUE les réponses possibles de
# l'atelier (nombres, noms d'animaux, heures) : il ne peut alors ni inventer un autre mot, ni se tromper de famille.
# (Donner à Whisper une liste de nombres en exemple a été essayé : il en invente quand il entend mal.)
_UNITES = ("zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize "
           "dix-sept dix-huit dix-neuf").split()
_DIZAINES = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def en_lettres(n):
    """0 à 100 écrits en lettres, comme on les dit (« vingt et un », « soixante-dix », « quatre-vingts »)."""
    if n < 20:
        return _UNITES[n]
    if n == 100:
        return "cent"
    d, u = divmod(n, 10)
    if d in (7, 9):
        base, reste = ("soixante" if d == 7 else "quatre-vingt"), 10 + u
        return base + (" et " if reste == 11 and d == 7 else "-") + _UNITES[reste]
    base = "quatre-vingt" if d == 8 else _DIZAINES[d]
    if u == 0:
        return "quatre-vingts" if d == 8 else base
    return base + (" et un" if u == 1 and d != 8 else "-" + _UNITES[u])


_HEURES_DITES = [en_lettres(h) for h in range(1, 13)]
_FINS_HEURE = ("", " et demie", " et quart", " moins le quart", " trente", " quinze", " quarante-cinq")


def _grammaire(jeu):
    """Les phrases que Vosk peut reconnaître pour la réponse de cet atelier (avec et sans traits d'union)."""
    communes = ["je ne sais pas", "je sais pas", "on arrête", "stop", "répète"]
    if jeu == "calcul":
        phrases = [en_lettres(n) for n in range(0, 101)]
        phrases += ["ça fait " + p for p in phrases[:31]] + ["c'est " + p for p in phrases[:31]]
    elif jeu == "animal":
        phrases = [nom for _, noms in ANIMAUX for nom in (NOMS_ANIMAUX.get(n, n) for n in noms)]
        phrases += ["un " + p for p in phrases] + ["une " + p for p in phrases]
    elif jeu == "heure":
        phrases = [h + (" heure" if h == "un" else " heures") + fin for h in _HEURES_DITES for fin in _FINS_HEURE]
        phrases += ["midi" + fin for fin in _FINS_HEURE[:3]] + ["minuit" + fin for fin in _FINS_HEURE[:3]]
    else:
        return None
    phrases += communes
    return sorted(set(phrases + [p.replace("-", " ") for p in phrases])) + ["[unk]"]


_modele_vosk = None


def _vosk():
    """Le modèle français de Vosk : celui que Jarvis a déjà chargé, sinon il est chargé ici (une fois)."""
    global _modele_vosk
    if _modele_vosk is None:
        try:
            import jarvis_locuteur
            _modele_vosk = jarvis_locuteur._modele
        except Exception:
            _modele_vosk = None
        if _modele_vosk is None:
            import jarvis_config
            from vosk import Model, SetLogLevel
            SetLogLevel(-1)
            _modele_vosk = Model(jarvis_config.chemin("vosk-model-small-fr-0.22"))
    return _modele_vosk


def ecouter_reponse(audio, jeu):
    """Ce que Vosk entend dans le son (tableau de -1 à 1, 16 kHz), limité aux réponses de cet atelier (« » sinon)."""
    phrases = _grammaire(jeu)
    if not phrases or audio is None or len(audio) < 1600:
        return ""
    try:
        import numpy as np
        from vosk import KaldiRecognizer
        crete = float(np.max(np.abs(audio))) or 1.0
        octets = (np.clip(audio * min(8.0, 0.7 / crete), -1, 1) * 32767).astype(np.int16).tobytes()
        ecoute = KaldiRecognizer(_vosk(), 16000, json.dumps(phrases, ensure_ascii=False))
        ecoute.AcceptWaveform(octets)
        return json.loads(ecoute.FinalResult()).get("text", "").replace("[unk]", "").strip()
    except Exception as erreur:
        print("Ateliers (Vosk) :", erreur)
        return ""


def corriger(ident, texte, audio):
    """Pendant une question d'atelier : si Whisper n'a pas écrit une réponse lisible, ce que Vosk y entend (limité aux
    réponses possibles). Sinon le texte de Whisper, tel quel."""
    jeu = _jeux.get(ident)
    if not jeu or time.time() - jeu["quand"] > DUREE_JEU or jeu["nom"] not in ("calcul", "animal", "heure"):
        return texte
    t = _propre(texte or "")
    mots = t.split()
    repete = len(mots) > 4 and len(set(mots)) <= len(mots) / 2       # « C'est ça ? C'est ça ? C'est ça ? » : rien de lisible
    if _je_sais_pas(t) or _ARRET.search(t) or (len(mots) > 4 and not repete):
        return texte                                 # « je ne sais pas », « on arrête », ou une autre demande
    lisible = not repete and (_nombres(t) if jeu["nom"] == "calcul" else _animal_dit(t) if jeu["nom"] == "animal"
                              else _heure_dite(t))
    if lisible:
        return texte
    entendu = ecouter_reponse(audio, jeu["nom"])
    if entendu:
        print(f"Ateliers : réponse mal écrite par Whisper, Vosk a entendu « {entendu} ».")
        return entendu
    return texte


def en_cours(ident):
    jeu = _jeux.get(ident)
    return bool(jeu and time.time() - jeu["quand"] <= DUREE_JEU)


def arreter(ident):
    with _verrou:
        _jeux.pop(ident, None)
