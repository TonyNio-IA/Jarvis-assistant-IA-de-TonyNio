"""
JARVIS - le foyer : calendrier familial, messages entre profils, défi du jour et étoiles, quiz en famille.

  Calendrier :
    « Léo a piscine mercredi à 14 h », « j'ai dentiste jeudi à 10 h 30 »,
    « Marie a rendez-vous chez le coiffeur le 25 novembre à 9 h »
    Jarvis le rappelle à la personne concernée la veille au soir (19 h) et une heure avant.
    « qu'est-ce qu'on a demain ? », « qu'est-ce que j'ai cette semaine ? », « quel est le programme de Léo ? »
    « annule la piscine de Léo »
  Messages : « dis à Marie que je rentre tard », « laisse un message à Léo : bravo pour ta dictée »
    Le message est dit dès que la personne parle à Jarvis (reconnue à sa voix, ou « Jarvis, c'est Marie »).
  Défi du jour (profil enfant) : « donne-moi mon défi », « c'est quoi le défi du jour ? »
    Un petit défi à son niveau ; s'il le réussit, il gagne une étoile. Jarvis le propose aussi de temps en
    temps (une fois par jour au plus, sur son profil). « Combien j'ai d'étoiles ? » ; le dimanche, Jarvis
    fait le bilan des étoiles de la semaine.
  Quiz en famille : « on fait un quiz en famille » (« on arrête le quiz » pour finir)
    Chacun son tour, une question adaptée à la personne (plus simple pour un enfant), la réponse est
    attribuée grâce à la voix quand elle est reconnue, et Jarvis compte les points de chacun.

Tout est rangé dans des fichiers qui restent sur ce PC (calendrier.json, messages.json, et dans profils.json
pour les étoiles).
"""

import datetime
import json
import os
import random
import re
import threading
import time

import jarvis_config
import jarvis_profils

FICHIER_CALENDRIER = jarvis_config.chemin("calendrier.json")
FICHIER_MESSAGES = jarvis_config.chemin("messages.json")
HEURE_RAPPEL_VEILLE = 19
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
_verrou = threading.RLock()


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t


def _lire(fichier, defaut):
    try:
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def _ecrire(fichier, donnees):
    provisoire = fichier + ".tmp"
    with open(provisoire, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=1)
    os.replace(provisoire, fichier)


def _prenom(ident):
    if not ident:
        return jarvis_profils.PRINCIPAL["prenom"] or ""
    return jarvis_profils._lire().get(ident, {}).get("prenom", "")


def _qui(nom):
    """Profil désigné par un mot (« je », « Marie », « mon fils »...) : identifiant ("" = principal) ou None."""
    nom = (nom or "").strip().lower()
    if re.fullmatch(r"(?:je|j|moi|j'ai)", nom):
        return jarvis_profils.actif() or ""
    return jarvis_profils._trouver(nom)


def _heure_parlee(h, m):
    if h == 0 and m == 0:
        return "minuit"
    if h == 12 and m == 0:
        return "midi"
    return f"{h} heure{'s' if h > 1 else ''}" + (f" {m}" if m else "")


def _jour_parle(quand):
    d = datetime.date.fromtimestamp(quand)
    aujourdhui = datetime.date.today()
    if d == aujourdhui:
        return "aujourd'hui"
    if d == aujourdhui + datetime.timedelta(days=1):
        return "demain"
    if 1 < (d - aujourdhui).days < 7:
        return JOURS[d.weekday()]
    return f"le {JOURS[d.weekday()]} {'premier' if d.day == 1 else d.day} {MOIS[d.month - 1]}"


# ---------- Calendrier familial ----------

def _date_dite(t):
    """La date dite dans la phrase -> datetime.date, ou None."""
    aujourdhui = datetime.date.today()
    if re.search(r"\bapr[eè]s[- ]demain\b", t):
        return aujourdhui + datetime.timedelta(days=2)
    if re.search(r"\bdemain\b", t):
        return aujourdhui + datetime.timedelta(days=1)
    if re.search(r"\baujourd'hui\b|\bce (?:matin|soir|midi)\b|\bcet apr[eè]s[- ]midi\b", t):
        return aujourdhui
    m = re.search(r"\b(?:le )?(\d{1,2}|premier|1er) (" + "|".join(MOIS + ["fevrier", "aout", "decembre"]) + r")\b", t)
    if m:
        jour = 1 if m.group(1) in ("premier", "1er") else int(m.group(1))
        nom = _sans_accents(m.group(2))
        mois = [_sans_accents(x) for x in MOIS].index(nom) + 1
        for annee in (aujourdhui.year, aujourdhui.year + 1):
            try:
                d = datetime.date(annee, mois, jour)
            except ValueError:
                return None
            if d >= aujourdhui:
                return d
        return None
    m = re.search(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b", t)
    if m:
        ecart = (JOURS.index(m.group(1)) - aujourdhui.weekday()) % 7
        if re.search(r"\b" + m.group(1) + r" prochain\b|\bla semaine prochaine\b", t) and ecart == 0:
            ecart = 7
        return aujourdhui + datetime.timedelta(days=ecart)
    return None


_EVENEMENT = re.compile(r"^\W*(?:jarvis\W+)?(?:(?P<nom>[\w\-]+(?: [\w\-]+)?) (?:a|aura|à)|(?P<moi>j'ai|j'aurai))\s+"
                        r"(?P<quoi>.+?)\s+(?P<quand>(?:aujourd'hui|demain|apr[eè]s[- ]demain|ce (?:matin|soir|midi)|"
                        r"cet apr[eè]s[- ]midi|(?:le |ce )?(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)|"
                        r"le (?:\d|premier|1er)).*)$")
_AJOUT_CAL = re.compile(r"^\W*(?:jarvis\W+)?(?:note|ajoute|mets|inscris)(?: dans| au| sur)? (?:le |mon |notre )?"
                        r"(?:calendrier|agenda)(?: que)? (?P<reste>.+)$")


def commande_ajout(t, heure_fixe):
    """« Léo a piscine mercredi à 14 h » : ajoute l'événement au calendrier. heure_fixe : lit l'heure."""
    t = t.replace("’", "'")
    m = _AJOUT_CAL.match(t)
    phrase = m.group("reste") if m else t
    m = _EVENEMENT.match(phrase)
    if not m:
        return None
    jour, heure = _date_dite(m.group("quand")), heure_fixe(m.group("quand"))
    if jour is None or heure is None:
        return None
    ident = jarvis_profils.actif() or "" if m.group("moi") else _qui(m.group("nom"))
    if ident is None:
        return None                       # « Le train a du retard demain à 8 h » : pas un membre du foyer
    quoi = re.sub(r"^(?:un |une )", "", m.group("quoi")).strip()
    if not quoi or len(quoi.split()) > 8:
        return None
    quand = datetime.datetime.combine(jour, datetime.time(*heure)).timestamp()
    if quand < time.time() - 60:
        return "Ce moment est déjà passé. Redis-moi le jour."
    with _verrou:
        calendrier = _lire(FICHIER_CALENDRIER, [])
        calendrier.append({"quand": quand, "quoi": quoi, "pour": ident, "annonces": []})
        calendrier.sort(key=lambda e: e["quand"])
        _ecrire(FICHIER_CALENDRIER, calendrier)
    qui = "tu as" if ident == (jarvis_profils.actif() or "") else f"{_prenom(ident)} a"
    h, mn = heure
    return f"C'est noté : {_jour_parle(quand)} à {_heure_parlee(h, mn)}, {qui} {quoi}. Je le rappellerai la veille."


def _evenements(debut, fin, ident=None):
    with _verrou:
        calendrier = _lire(FICHIER_CALENDRIER, [])
    return [e for e in calendrier if debut <= e["quand"] < fin and (ident is None or e.get("pour") == ident)]


def _phrase_evenement(e, avec_jour=True, avec_qui=True):
    t = time.localtime(e["quand"])
    qui = (_prenom(e.get("pour")) + " a ") if avec_qui else ""
    jour = (_jour_parle(e["quand"]) + " ") if avec_jour else ""
    return f"{jour}à {_heure_parlee(t.tm_hour, t.tm_min)}, {qui}{e['quoi']}"


def commande_consulter(t):
    t = t.replace("’", "'")
    # « c'est quoi mon prochain rendez-vous ? » (toute la demande) : le premier à venir, dans les 60 jours
    prochain = re.search(r"^\W*(?:jarvis\W+)?(?:c'est quoi|quel est|quels sont|dis[- ]moi|donne[- ]moi)?\s*"
                         r"(?:mon|mes|le|les|notre|nos)?\s*prochains? (?:rendez[- ]vous|rdv)\W*$", t, re.I)
    if not prochain and not re.search(r"\b(qu'est-ce qu(?:'on|e j'ai|e tu as|e nous avons)|quel est le programme|quels sont les rendez-vous|"
                     r"calendrier|agenda|on a quoi|j'ai quoi|qu'y a-t-il)\b", t):
        return None
    if re.search(r"\b(fait|fais|faire)\b", t):
        return None                                  # « qu'est-ce qu'on a fait aujourd'hui » : le résumé
    aujourdhui = datetime.date.today()
    debut_jour = datetime.datetime.combine(aujourdhui, datetime.time()).timestamp()
    if prochain:
        debut, fin, periode = time.time(), debut_jour + 60 * 86400, "dans les deux mois qui viennent"
    elif re.search(r"\bcette semaine\b|\bla semaine\b", t):
        debut, fin, periode = time.time(), debut_jour + 7 * 86400, "cette semaine"
    elif re.search(r"\bapr[eè]s[- ]demain\b", t):
        debut, fin, periode = debut_jour + 2 * 86400, debut_jour + 3 * 86400, "après-demain"
    elif re.search(r"\bdemain\b", t):
        debut, fin, periode = debut_jour + 86400, debut_jour + 2 * 86400, "demain"
    elif re.search(r"\baujourd'hui\b|\bce soir\b", t):
        debut, fin, periode = time.time(), debut_jour + 86400, "aujourd'hui"
    elif re.search(r"\b(calendrier|agenda|programme|rendez-vous)\b", t):
        debut, fin, periode = time.time(), debut_jour + 30 * 86400, "dans les jours qui viennent"
    else:
        jour = _date_dite(t)
        if jour is None:
            return None
        debut = datetime.datetime.combine(jour, datetime.time()).timestamp()
        fin, periode = debut + 86400, _jour_parle(debut + 43200)
    ident = None
    if re.search(r"\b(j'ai|je|mon programme|mes rendez-vous|moi)\b", t):
        ident = jarvis_profils.actif() or ""
    else:
        m = re.search(r"\b(?:programme|rendez-vous|agenda) (?:de |d')([\w\-]+)", t) or \
            re.search(r"\bqu'est-ce qu'(?:a|aura) ([\w\-]+)", t)
        if m:
            ident = _qui(m.group(1))
            if ident is None:
                return f"Je ne connais personne qui s'appelle {m.group(1)}."
    evenements = _evenements(debut, fin, ident)
    # Agenda iCloud du foyer (jarvis_agenda.py), sauf quand on demande le programme d'une autre personne
    if ident in (None, jarvis_profils.actif() or ""):
        try:
            import jarvis_agenda
            for e in jarvis_agenda.evenements(datetime.datetime.fromtimestamp(debut),
                                              datetime.datetime.fromtimestamp(fin)) or []:
                evenements.append({"quand": e["debut"].timestamp(), "quoi": e["titre"], "icloud": True,
                                   "journee": e["journee"]})
            evenements.sort(key=lambda e: e["quand"])
        except Exception as erreur:
            print("Agenda iCloud :", erreur)
    if not evenements:
        return f"Rien de prévu {periode}" + (f" pour {_prenom(ident)}" if ident not in (None, jarvis_profils.actif() or "") else "") + "."
    moi = jarvis_profils.actif() or ""
    phrases = []
    for e in evenements[:6]:
        t_e = time.localtime(e["quand"])
        jour = "" if periode in ("demain", "aujourd'hui", "après-demain") else _jour_parle(e["quand"]) + " "
        if e.get("icloud"):
            quand = "toute la journée" if e.get("journee") else f"à {_heure_parlee(t_e.tm_hour, t_e.tm_min)}"
            phrases.append(f"{jour}{quand}, {e['quoi']}")
            continue
        qui = "tu as" if e.get("pour") == moi else f"{_prenom(e.get('pour'))} a"
        phrases.append(f"{jour}à {_heure_parlee(t_e.tm_hour, t_e.tm_min)}, {qui} {e['quoi']}")
    if prochain:
        return "Prochain rendez-vous : " + phrases[0] + "."
    debut_phrase = (periode[0].upper() + periode[1:]) if periode in ("demain", "aujourd'hui", "après-demain") else "Au programme"
    return debut_phrase + " : " + " ; ".join(phrases) + "."


def commande_annuler(t):
    t = t.replace("’", "'")
    m = re.search(r"\b(?:annule|supprime|efface|enl[eè]ve)\b\s+(?:le |la |les |l'|mon |ma |son |sa )?(?P<quoi>.+?)"
                  r"(?:\s+(?:de|d')\s+(?P<nom>[\w\-]+))?(?:\s+(?P<quand>demain|aujourd'hui|lundi|mardi|mercredi|jeudi|"
                  r"vendredi|samedi|dimanche))?\W*$", t)
    if not m:
        return None
    with _verrou:
        calendrier = _lire(FICHIER_CALENDRIER, [])
        candidats = []
        if len(m.group("quoi").strip()) < 3:
            return None
        for e in calendrier:
            if e["quand"] < time.time() or len(e["quoi"]) < 3:
                continue
            if _sans_accents(e["quoi"].lower()) not in _sans_accents(m.group("quoi").lower()) and \
                    _sans_accents(m.group("quoi").lower()) not in _sans_accents(e["quoi"].lower()):
                continue
            if m.group("nom") and _qui(m.group("nom")) != e.get("pour"):
                continue
            if m.group("quand") and _date_dite(m.group("quand")) != datetime.date.fromtimestamp(e["quand"]):
                continue
            candidats.append(e)
        if not candidats:
            return None
        e = candidats[0]
        calendrier.remove(e)
        _ecrire(FICHIER_CALENDRIER, calendrier)
    return f"C'est annulé : {_phrase_evenement(e)}."


def surveiller_calendrier(annoncer):
    """Rappelle chaque événement à la personne concernée : la veille à 19 h et une heure avant."""
    def boucle():
        time.sleep(75)
        while True:
            try:
                maintenant = time.time()
                a_dire = []
                with _verrou:
                    calendrier = _lire(FICHIER_CALENDRIER, [])
                    garde, change = [], False
                    for e in calendrier:
                        if e["quand"] < maintenant - 3600:
                            change = True                      # passé depuis plus d'une heure : on le retire
                            continue
                        veille = datetime.datetime.combine(datetime.date.fromtimestamp(e["quand"]) - datetime.timedelta(days=1),
                                                           datetime.time(HEURE_RAPPEL_VEILLE)).timestamp()
                        if "veille" not in e["annonces"] and veille <= maintenant < e["quand"] - 2 * 3600:
                            e["annonces"].append("veille")
                            change = True
                            if maintenant - veille < 3 * 3600:
                                a_dire.append((e, "demain"))
                        if "heure" not in e["annonces"] and e["quand"] - 3600 <= maintenant < e["quand"]:
                            e["annonces"].append("heure")
                            change = True
                            a_dire.append((e, "bientot"))
                        garde.append(e)
                    if change:
                        _ecrire(FICHIER_CALENDRIER, garde)
                for e, moment in a_dire:
                    t = time.localtime(e["quand"])
                    qui = _prenom(e.get("pour"))
                    if moment == "demain":
                        annoncer(f"Rappel pour {qui} : demain à {_heure_parlee(t.tm_hour, t.tm_min)}, {e['quoi']}.")
                    else:
                        annoncer(f"Rappel pour {qui} : à {_heure_parlee(t.tm_hour, t.tm_min)}, {e['quoi']}.")
            except Exception as erreur:
                print("Calendrier :", erreur)
            time.sleep(30)
    threading.Thread(target=boucle, daemon=True).start()


def evenements_du_jour(decalage=0):
    """Pour « Jarvis, bonjour » : les événements du jour de la personne en cours."""
    debut = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=decalage), datetime.time()).timestamp()
    ident = jarvis_profils.actif() or ""
    return [_phrase_evenement(e, avec_jour=False, avec_qui=False) for e in _evenements(debut, debut + 86400, ident)]


# ---------- Messages entre profils ----------

_MESSAGE = re.compile(r"^\W*(?:jarvis\W+)?(?:dis|dites|r[ée]p[eè]te)[- ](?:à|a) (?P<nom>[\w\-]+(?: [\w\-]+)?) (?:que |qu')(?P<texte>.+)$"
                      r"|^\W*(?:jarvis\W+)?(?:laisse|transmets|donne)(?:-lui)? un message (?:à|a|pour) (?P<nom2>[\w\-]+)\s*:?\s*"
                      r"(?:pour (?:lui )?dire (?:que |qu')?)?(?P<texte2>.+)$")


def commande_message(t):
    m = _MESSAGE.match(t.replace("’", "'"))
    if not m:
        return None
    nom, texte = (m.group("nom"), m.group("texte")) if m.group("nom") else (m.group("nom2"), m.group("texte2"))
    ident = _qui(nom)
    if ident is None:
        return None                          # « dis à Google que... » : pas un membre du foyer
    if ident == (jarvis_profils.actif() or ""):
        return "C'est toi ! Je ne peux pas te laisser un message à toi-même. Pour t'en souvenir, demande-moi un rappel."
    texte = texte.strip(" .!?")
    if not texte:
        return None
    with _verrou:
        messages = _lire(FICHIER_MESSAGES, [])
        messages.append({"pour": ident, "de": jarvis_profils.prenom_actif() or "", "texte": texte, "quand": time.time()})
        _ecrire(FICHIER_MESSAGES, messages[-50:])
    return f"D'accord, je le dirai à {_prenom(ident)} dès que je l'entendrai."


def messages_en_attente():
    """Les messages pour la personne en cours, à dire avant la réponse (ils sont ensuite effacés)."""
    ident = jarvis_profils.actif() or ""
    with _verrou:
        messages = _lire(FICHIER_MESSAGES, [])
        pour_moi = [x for x in messages if x.get("pour") == ident]
        if not pour_moi:
            return ""
        _ecrire(FICHIER_MESSAGES, [x for x in messages if x.get("pour") != ident])
    phrases = []
    for x in pour_moi[:5]:
        de = x.get("de") or "Quelqu'un"
        phrases.append(f"{de} t'a laissé un message : {x['texte']}.")
    return " ".join(phrases) + " "


# ---------- Défi du jour et étoiles (profil enfant) ----------

_defi = {"profil": None, "depuis": 0.0, "propose": ""}
DUREE_DEFI = 10 * 60


def _etoiles(ident):
    return list(jarvis_profils._lire().get(ident, {}).get("etoiles") or [])


def _ajouter_etoile(ident):
    import jarvis_famille
    etoiles = _etoiles(ident)
    etoiles.append(time.strftime("%Y-%m-%d"))
    jarvis_famille._regler(ident, etoiles=etoiles[-400:])


def _enfant():
    ident = jarvis_profils.actif()
    return ident if ident and jarvis_profils._lire().get(ident, {}).get("enfant") else None


def defi_demande(demande):
    t = demande.lower().replace("’", "'")
    return bool(_enfant()) and bool(re.search(r"\bd[ée]fi\b", t)) and not re.search(r"\b(combien|[ée]toiles?)\b", t)


def defi_en_cours():
    return _defi["profil"] is not None and _defi["profil"] == _enfant() and time.time() - _defi["depuis"] < DUREE_DEFI


def note_defi(demande):
    """Consignes pour Claude pendant le défi du jour (sinon « »)."""
    ident = _enfant()
    if not ident:
        return ""
    if defi_demande(demande):
        _defi.update(profil=ident, depuis=time.time())
    elif not defi_en_cours():
        return ""
    import jarvis_famille
    prenom = jarvis_profils.prenom_actif()
    niveau = jarvis_famille.classe()
    deja = time.strftime("%Y-%m-%d") in _etoiles(ident)
    return ("(Défi du jour de " + prenom + (f", en {niveau}" if niveau else "") + " : propose UN seul petit défi amusant "
            "à son niveau (un mot à épeler, un calcul mystère, une devinette, une suite logique), dis-le avec "
            "enthousiasme et termine par le défi. Quand il répond : si c'est juste, félicite-le "
            + ("(il a déjà gagné son étoile aujourd'hui : c'est un défi pour le plaisir) " if deja else
               "et annonce qu'il gagne une étoile, puis ajoute une ligne seule « ETOILE: oui » (elle ne sera pas lue) ")
            + "; si c'est faux, donne un indice et laisse-lui une deuxième chance, puis donne la réponse gentiment.)\n")


def appliquer_defi(reponse):
    """Retire la ligne ETOILE: et ajoute l'étoile gagnée (une par jour)."""
    if not reponse or "ETOILE" not in reponse:
        return reponse
    reponse_sans = re.sub(r"^\s*ETOILE\s*:.*$", "", reponse, flags=re.M).strip()
    ident = _enfant()
    if ident and time.strftime("%Y-%m-%d") not in _etoiles(ident):
        _ajouter_etoile(ident)
        _defi.update(profil=None, depuis=0.0)
    return reponse_sans


def commande_etoiles(t):
    if not re.search(r"\b[ée]toiles?\b", t) or not re.search(r"\b(combien|mes|j'ai|bilan|compte)\b", t):
        return None
    ident = _enfant()
    if not ident:
        return None
    etoiles = _etoiles(ident)
    semaine = _depuis_lundi(etoiles)
    return (f"Tu as {len(etoiles)} étoile{'s' if len(etoiles) > 1 else ''} en tout, dont {semaine} cette semaine. "
            + ("Bravo !" if etoiles else "Demande-moi ton défi pour gagner la première !"))


def _depuis_lundi(etoiles):
    lundi = datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())
    return sum(1 for d in etoiles if d >= lundi.isoformat())


def a_ajouter_apres(reponse_donnee):
    """Après une réponse sur le profil enfant : le bilan du dimanche, ou la proposition du défi (une fois par jour)."""
    import jarvis_famille
    ident = _enfant()
    if (not ident or jarvis_famille.dodo["actif"] or defi_en_cours() or quiz_actif()
            or time.time() - jarvis_famille._devoirs["dernier"] < jarvis_famille.DUREE_DEVOIRS):
        return ""
    profil = jarvis_profils._lire().get(ident, {})
    aujourdhui = time.strftime("%Y-%m-%d")
    if datetime.date.today().weekday() == 6 and profil.get("bilan") != aujourdhui:
        jarvis_famille._regler(ident, bilan=aujourdhui)
        n = _depuis_lundi(_etoiles(ident))
        if n:
            return (f" Au fait, c'est dimanche : cette semaine, tu as gagné {n} étoile{'s' if n > 1 else ''}. "
                    + ("Bravo, quel champion !" if n >= 4 else "Bravo, continue comme ça !"))
        return " Au fait, c'est dimanche : cette semaine, pas encore d'étoile. La semaine prochaine, on en gagne ensemble ?"
    heure = time.localtime().tm_hour
    if (profil.get("defi_propose") != aujourdhui and aujourdhui not in _etoiles(ident) and 10 <= heure < 20
            and random.random() < 0.5):
        jarvis_famille._regler(ident, defi_propose=aujourdhui)
        return " Au fait, tu veux relever le défi du jour ? Dis : Jarvis, donne-moi mon défi."
    return ""


# ---------- Quiz en famille ----------

quiz = {"actif": False, "joueurs": [], "tour": 0, "scores": {}, "dernier": 0.0, "attendu": None}
DUREE_QUIZ = 30 * 60


def quiz_actif():
    return quiz["actif"] and time.time() - quiz["dernier"] < DUREE_QUIZ


def _joueurs():
    """[(identifiant, prénom, enfant ?)] : tout le foyer."""
    joueurs = [("", jarvis_profils.PRINCIPAL["prenom"] or "Joueur 1", False)]
    for ident, p in jarvis_profils._lire().items():
        joueurs.append((ident, p.get("prenom", ident), bool(p.get("enfant"))))
    return joueurs


def _noms_cites(morceau):
    """Identifiants des profils cités dans « Léo et Marie », « moi, Léo »… ("moi" = None, à remplacer)."""
    trouves = []
    for nom in re.split(r"\s*(?:,|\bet\b|&)\s*", morceau):
        nom = re.sub(r"^(?:avec|aussi|tous|toutes)\s+|\s+(?:aussi|également)$", "", nom.strip(" .!?"))
        if not nom:
            continue
        if nom in ("moi", "moi-même"):
            trouves.append(None)
            continue
        ident = jarvis_profils._trouver(nom)
        if ident is not None:
            trouves.append(ident)
    return trouves


def _joueurs_choisis(demande, voix_de=None):
    """Les joueurs du quiz : ceux qui sont nommés (« quiz en famille avec Léo »), plus la personne qui parle ;
    sans prénom cité, tout le foyer. « sans Marie » retire Marie."""
    t = demande.lower().replace("’", "'")
    tous = _joueurs()
    parle = voix_de if voix_de is not None else (jarvis_profils.actif() or "")
    garder = None
    m = re.search(r"\bavec\s+(.+?)(?:\s+sans\s+.*)?$", t)
    if m:
        cites = [parle if i is None else i for i in _noms_cites(m.group(1))]
        if cites:
            garder = set(cites) | {parle}
    m = re.search(r"\bsans\s+(.+)$", t)
    exclus = {i for i in _noms_cites(m.group(1)) if i is not None} if m else set()
    choisis = [j for j in tous if (garder is None or j[0] in garder) and j[0] not in exclus]
    return choisis or tous


_RETIRER = re.compile(r"^\W*(?:jarvis\W+)?(.+?)\s+(?:ne joue pas|ne joue plus|n'est pas là|n'est plus là|"
                      r"arrête de jouer|est partie?|ne veut plus jouer)\b")
_AJOUTER = re.compile(r"^\W*(?:jarvis\W+)?(?:(.+?)\s+(?:joue aussi|veut jouer|est là aussi)|(?:ajoute|rajoute)\s+(.+?)\s+au quiz)\b")


def _changer_joueurs(t):
    """Pendant le quiz : « Marie ne joue pas » / « Léo joue aussi »."""
    m = _RETIRER.match(t)
    if m:
        idents = {i for i in _noms_cites(m.group(1)) if i is not None}
        partis = [j for j in quiz["joueurs"] if j[0] in idents]
        if not partis:
            return None
        if len(partis) >= len(quiz["joueurs"]):
            return "Il faut au moins un joueur. Pour arrêter, dis : Jarvis, on arrête le quiz."
        quiz["joueurs"] = [j for j in quiz["joueurs"] if j[0] not in idents]
        for j in partis:
            quiz["scores"].pop(j[1], None)
        if quiz["attendu"] and quiz["attendu"][0] in idents:
            quiz["attendu"] = None
        quiz["dernier"] = time.time()
        noms = " et ".join(j[1] for j in partis)
        return (f"D'accord, {noms} ne joue pas. On continue avec " +
                ", ".join(j[1] for j in quiz["joueurs"]) + ".")
    m = _AJOUTER.match(t)
    if m:
        deja = {j[0] for j in quiz["joueurs"]}
        nouveaux = [j for j in _joueurs() if j[0] in set(_noms_cites(m.group(1) or m.group(2))) and j[0] not in deja]
        if not nouveaux:
            return None
        quiz["joueurs"] += nouveaux
        for j in nouveaux:
            quiz["scores"].setdefault(j[1], 0)
        quiz["dernier"] = time.time()
        return " et ".join(j[1] for j in nouveaux) + " rejoint le quiz. On continue !"
    return None


def commande_quiz(t):
    """Démarre ou arrête le quiz en famille (la suite passe par Claude, avec note_quiz)."""
    if re.search(r"\b(arr[eê]te|arr[eê]tons|fin|stop|termine)\b.*\bquiz\b|\bquiz\b.*\b(fini|termin[ée])\b", t) and quiz_actif():
        return _fin_quiz()
    if quiz_actif():
        reponse = _changer_joueurs(t)
        if reponse:
            return reponse
    if re.search(r"\bscores?\b|\bqui (?:gagne|m[eè]ne)\b|\bcombien de points\b", t) and quiz_actif():
        return _scores() + "."
    return None


def quiz_demande(demande):
    t = demande.lower()
    return bool(re.search(r"\bquiz\b.*\b(famille|tous|ensemble|plusieurs)\b|\b(famille|tous ensemble)\b.*\bquiz\b", t)) \
        and not re.search(r"\b(arr[eê]te|fin|stop)\b", t)


def _scores():
    tri = sorted(quiz["scores"].items(), key=lambda x: -x[1])
    return "Les scores : " + ", ".join(f"{n} {s} point{'s' if s > 1 else ''}" for n, s in tri)


def _fin_quiz():
    tri = sorted(quiz["scores"].items(), key=lambda x: -x[1])
    quiz.update(actif=False, attendu=None)
    if not tri or tri[0][1] == 0:
        return "Fin du quiz ! Personne n'a marqué de point cette fois, on rejoue quand vous voulez."
    gagnants = [n for n, s in tri if s == tri[0][1]]
    vainqueur = (" et ".join(gagnants) + " sont à égalité") if len(gagnants) > 1 else f"{gagnants[0]} gagne"
    return f"Fin du quiz ! {_scores()}. {vainqueur}, bravo à tous !"


def note_quiz(demande, voix_de=None):
    """Consignes pour Claude pendant le quiz. voix_de : identifiant reconnu à la voix (ou None)."""
    if quiz_demande(demande) and not quiz_actif():
        joueurs = _joueurs_choisis(demande, voix_de)
        random.shuffle(joueurs)
        quiz.update(actif=True, joueurs=joueurs, tour=0, scores={p: 0 for _, p, _ in joueurs}, dernier=time.time())
        debut = True
    elif quiz_actif():
        quiz["dernier"] = time.time()
        debut = False
    else:
        return ""
    import jarvis_famille
    joueurs = quiz["joueurs"]
    attendu = quiz["attendu"]
    lignes = []
    if not debut and attendu is not None:
        repond = attendu[1]
        if voix_de is not None and voix_de != attendu[0]:
            autre = next((p for i, p, _ in joueurs if i == voix_de), None)
            if autre:
                lignes.append(f"Attention : d'après sa voix, c'est {autre} qui vient de répondre à la place de {repond} ; "
                              f"dis-le avec humour, et ne compte pas le point.")
        lignes.append(f"Cette réponse est celle de {repond} à ta dernière question. Dis si c'est juste (et donne la "
                      f"bonne réponse sinon). Si c'est juste, ajoute une ligne seule « POINT: {repond} » (elle ne sera pas lue).")
    suivant = joueurs[quiz["tour"] % len(joueurs)]
    quiz["tour"] += 1
    quiz["attendu"] = (suivant[0], suivant[1])
    niveau = "un enfant" + (f" en {jarvis_famille._classe_de(suivant[0])}" if jarvis_famille._classe_de(suivant[0]) else "") \
        if suivant[2] else "un adulte"
    regles = ("(Quiz en famille. Joueurs : " + ", ".join(p for _, p, _ in joueurs) + ". " + _scores() + ". "
              "Thèmes accessibles à tous, petits et grands : animaux, nature, dessins animés, cuisine, sport, monde, "
              "corps humain, inventions... Pas de question qui fasse peur ni réservée aux adultes. "
              + ("Commence par annoncer joyeusement le quiz et les joueurs, et précise en une phrase que si quelqu'un "
                 "n'est pas là, il suffit de dire : Jarvis, untel ne joue pas. " if debut else "") + " ".join(lignes) +
              f" Puis pose la question suivante à {suivant[1]}, adaptée à {niveau} (plus simple pour un enfant, "
              f"plus difficile pour un adulte), en commençant par son prénom, et termine par la question. "
              "Une seule question à la fois. Pour arrêter, il suffit de dire : Jarvis, on arrête le quiz.)\n")
    return regles


def appliquer_quiz(reponse):
    """Compte les points annoncés par les lignes POINT: et les retire de la réponse."""
    if not reponse or "POINT" not in reponse:
        return reponse
    for nom in re.findall(r"^\s*POINT\s*:\s*(.+?)\s*$", reponse, flags=re.M):
        for prenom in quiz["scores"]:
            if _sans_accents(prenom.lower()) == _sans_accents(nom.lower()):
                quiz["scores"][prenom] += 1
    return re.sub(r"^\s*POINT\s*:.*$", "", reponse, flags=re.M).strip()
