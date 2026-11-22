"""
JARVIS - l'agenda du foyer : Google Agenda, Outlook, iCloud ou tout agenda qui donne un lien « ICS »
(lien privé de l'agenda, lu sans compte ni mot de passe ; Jarvis ne fait que lire).
Pour le relier : « Jarvis, relie mon agenda » (fenêtre de jarvis_agenda_ui.py).

  « qu'est-ce qu'on a demain ? », « mon agenda de la semaine »   (avec le calendrier familial, voir jarvis_foyer.py)
  « c'est quand le dentiste ? »   (cherche dans les 60 prochains jours)
La veille au soir (19 h), Jarvis rappelle les rendez-vous du lendemain.
Le lien est rangé dans le Gestionnaire d'identification de Windows (cible « Jarvis-Agenda »), jamais dans un
fichier ni sur GitHub. L'agenda est relu au plus toutes les minutes ; sans réseau, la dernière copie sert.
Répétitions prises en charge : quotidienne, hebdomadaire, mensuelle, annuelle (INTERVAL, BYDAY, COUNT, UNTIL, EXDATE).
Idée reprise du module Agenda de Cornelius (Les Frères Poulain, licence MIT), réécrite pour Jarvis.
"""

import datetime
import re
import threading
import time
import unicodedata
import urllib.request

CIBLE = "Jarvis-Agenda"
RELIRE = 60                # un rendez-vous ajouté sur le téléphone est vu au bout d'une minute environ
                           # (Google et Outlook peuvent mettre plus longtemps à mettre leur lien à jour)
HEURE_VEILLE = 19
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
_JOURS_ICS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
_cache = {"quand": 0.0, "texte": None}
_verrou = threading.Lock()
lien = None                      # remplaçable pour les essais


# ---------- Lecture du fichier .ics ----------

def cible(profil=False):
    """Le nom du coffre de Windows pour l'agenda d'un profil : « Jarvis-Agenda » pour le profil principal,
    « Jarvis-Agenda-profil-marie » pour celui de Marie. Chaque profil ne lit que le sien.
    profil : False = le profil en cours ; None = le profil principal ; sinon l'identifiant d'un profil."""
    import jarvis_mails
    return jarvis_mails.cible(CIBLE, profil)


def _lien_range(nom):
    try:
        import jarvis_mails
        ident = jarvis_mails.identifiants(nom)
        return ident[1].strip() if ident and ident[1] else None
    except Exception:
        return None


def lien_du_profil(profil=False):
    """Le lien de l'agenda relié par ce profil lui-même, ou None."""
    return _lien_range(cible(profil))


def _lien():
    """Le lien de l'agenda à lire : celui que le profil en cours a relié lui-même, et aucun autre (séparation
    stricte, comme pour les mails). None s'il n'a rien relié."""
    if lien:
        return lien
    return lien_du_profil()


def _telecharger():
    adresse = _lien()
    if not adresse:
        return None
    adresse = re.sub(r"^webcal://", "https://", adresse)
    with _verrou:
        if _cache.get("adresse") not in (None, adresse):          # autre profil, autre agenda : rien de l'ancien
            _cache.update(quand=0.0, texte=None)
        _cache["adresse"] = adresse
        if _cache["texte"] is not None and time.time() - _cache["quand"] < RELIRE:
            return _cache["texte"]
    try:
        req = urllib.request.Request(adresse, headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(req, timeout=10) as r:
            texte = r.read(2_000_000).decode("utf-8", "replace")
        if "BEGIN:VCALENDAR" not in texte:
            raise ValueError("pas un agenda")
        with _verrou:
            if _cache.get("adresse") == adresse:
                _cache.update(quand=time.time(), texte=texte)
        return texte
    except Exception as erreur:
        print("Agenda :", erreur)
    with _verrou:
        return _cache["texte"] if _cache.get("adresse") == adresse else None


def _lignes(texte):
    """Lignes du .ics, avec les lignes repliées (commençant par un espace) recollées."""
    lignes = []
    for ligne in texte.replace("\r\n", "\n").split("\n"):
        if ligne[:1] in (" ", "\t") and lignes:
            lignes[-1] += ligne[1:]
        elif ligne:
            lignes.append(ligne)
    return lignes


def _date(valeur, parametres):
    """(datetime local, journée entière ?)"""
    valeur = valeur.strip()
    if "VALUE=DATE" in parametres or re.fullmatch(r"\d{8}", valeur):
        return datetime.datetime.strptime(valeur[:8], "%Y%m%d"), True
    moment = datetime.datetime.strptime(valeur[:15], "%Y%m%dT%H%M%S")
    if valeur.endswith("Z"):                     # UTC : ramené à l'heure de ce PC
        moment = moment.replace(tzinfo=datetime.timezone.utc).astimezone().replace(tzinfo=None)
    return moment, False                         # avec TZID : agenda français, heure locale


def _texte(valeur):
    valeur = valeur.replace("\\n", " ").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")
    # l'iPhone glisse parfois un caractère invisible (U+FFFC, pièce jointe) ou des émojis : Jarvis ne les lit pas
    valeur = "".join(c for c in valeur if unicodedata.category(c) not in ("So", "Co", "Cn", "Cf", "Cs")
                     and c != "￼")
    return re.sub(r"\s+", " ", valeur).strip()


def _evenements_bruts(texte):
    evenements, courant = [], None
    for ligne in _lignes(texte):
        if ligne == "BEGIN:VEVENT":
            courant = {"exdates": set()}
        elif ligne == "END:VEVENT" and courant is not None:
            if "debut" in courant:
                evenements.append(courant)
            courant = None
        elif courant is not None and ":" in ligne:
            cle_brute, valeur = ligne.split(":", 1)
            cle, _, parametres = cle_brute.partition(";")
            try:
                if cle == "DTSTART":
                    courant["debut"], courant["journee"] = _date(valeur, parametres)
                elif cle == "DTEND":
                    courant["fin"], _ = _date(valeur, parametres)
                elif cle == "SUMMARY":
                    courant["titre"] = _texte(valeur)
                elif cle == "LOCATION":
                    courant["lieu"] = _texte(valeur)
                elif cle == "RRULE":
                    courant["regle"] = dict(p.split("=", 1) for p in valeur.split(";") if "=" in p)
                elif cle == "EXDATE":
                    for v in valeur.split(","):
                        courant["exdates"].add(_date(v, parametres)[0].date())
                elif cle == "RECURRENCE-ID":
                    courant["remplace"], _ = _date(valeur, parametres)
                elif cle == "UID":
                    courant["uid"] = valeur.strip()
                elif cle == "STATUS" and valeur.strip() == "CANCELLED":
                    courant["annule"] = True
            except ValueError:
                pass
    return evenements


# ---------- Répétitions ----------

def _ajouter_mois(d, n):
    mois = d.month - 1 + n
    annee, mois = d.year + mois // 12, mois % 12 + 1
    import calendar
    jour = min(d.day, calendar.monthrange(annee, mois)[1])
    return d.replace(year=annee, month=mois, day=jour)


def _occurrences(ev, debut, fin):
    """Débuts des occurrences de l'événement entre debut et fin (datetime)."""
    depart = ev["debut"]
    duree = (ev.get("fin") or depart + (datetime.timedelta(days=1) if ev.get("journee") else datetime.timedelta(hours=1))) - depart
    regle = ev.get("regle")
    if not regle:
        return [depart] if depart < fin and depart + duree > debut else []
    freq = regle.get("FREQ", "")
    pas = max(1, int(regle.get("INTERVAL", "1") or 1))
    nombre = int(regle["COUNT"]) if regle.get("COUNT", "").isdigit() else None
    jusqua = None
    if regle.get("UNTIL"):
        try:
            jusqua = _date(regle["UNTIL"], "")[0]
            if len(regle["UNTIL"]) == 8:
                jusqua += datetime.timedelta(days=1)
        except ValueError:
            pass
    jours_semaine = [_JOURS_ICS.index(j[-2:]) for j in regle.get("BYDAY", "").split(",") if j[-2:] in _JOURS_ICS]
    resultats, vus = [], 0
    courant, garde = depart, 0
    while garde < 5000:
        garde += 1
        candidats = [courant]
        if freq == "WEEKLY" and jours_semaine:
            lundi = courant - datetime.timedelta(days=courant.weekday())
            candidats = sorted(lundi + datetime.timedelta(days=j) for j in jours_semaine)
        for c in candidats:
            if c < depart:
                continue
            if jusqua and c > jusqua:
                return resultats
            vus += 1
            if nombre is not None and vus > nombre:
                return resultats
            if c >= fin:
                return resultats
            if c.date() not in ev["exdates"] and c + duree > debut:
                resultats.append(c)
        if freq == "DAILY":
            courant += datetime.timedelta(days=pas)
        elif freq == "WEEKLY":
            courant += datetime.timedelta(weeks=pas)
        elif freq == "MONTHLY":
            courant = _ajouter_mois(depart, (garde) * pas)
        elif freq == "YEARLY":
            courant = _ajouter_mois(depart, 12 * garde * pas)
        else:
            return resultats
    return resultats


def evenements(debut, fin):
    """Liste triée de dicts {debut, fin, journee, titre, lieu} entre deux datetime, pour l'agenda du profil en cours.
    None s'il n'a pas relié d'agenda."""
    texte = _telecharger()
    if texte is None:
        return None
    bruts = _evenements_bruts(texte)
    remplaces = {(e.get("uid"), e["remplace"].date()) for e in bruts if e.get("remplace")}
    liste = []
    for ev in bruts:
        if ev.get("annule") and not ev.get("remplace"):
            continue
        duree = (ev.get("fin") or ev["debut"] + (datetime.timedelta(days=1) if ev.get("journee") else datetime.timedelta(hours=1))) - ev["debut"]
        for d in _occurrences(ev, debut, fin):
            if not ev.get("remplace") and (ev.get("uid"), d.date()) in remplaces:
                continue                          # cette occurrence a été déplacée ou modifiée
            if ev.get("annule"):
                continue
            liste.append({"debut": d, "fin": d + duree, "journee": ev.get("journee", False),
                          "titre": ev.get("titre") or "un rendez-vous", "lieu": ev.get("lieu") or ""})
    return sorted(liste, key=lambda e: (e["debut"], e["titre"]))


# ---------- Phrases ----------

def _heure(d):
    if d.hour == 12 and d.minute == 0:
        return "midi"
    return f"{d.hour} h" + (f" {d.minute:02d}" if d.minute else "")


def _jour(d, aujourd_hui):
    ecart = (d.date() - aujourd_hui).days
    if ecart == 0:
        return "aujourd'hui"
    if ecart == 1:
        return "demain"
    numero = "1er" if d.day == 1 else str(d.day)
    return f"{JOURS[d.weekday()]} {numero}" + ("" if ecart < 7 else f" {MOIS[d.month - 1]}")


def _phrase(e, aujourd_hui, avec_jour=True):
    if e["journee"]:
        derniere = (e["fin"] - datetime.timedelta(days=1)).date()
        quand = "toute la journée" if derniere <= e["debut"].date() else f"jusqu'au {JOURS[derniere.weekday()]} {derniere.day}"
    elif e["debut"].date() < aujourd_hui <= e["fin"].date() or (e["debut"] <= datetime.datetime.now() < e["fin"]):
        quand = f"en cours, jusqu'à {_heure(e['fin'])}"
    else:
        quand = f"à {_heure(e['debut'])}"
    jour = f"{_jour(e['debut'], aujourd_hui)} " if avec_jour else ""
    return f"{jour}{quand} : {e['titre']}"


_AGENDA = re.compile(r"\b(?:agenda|calendrier (?:icloud|google|outlook)|planning|emploi du temps)\b")
_QUAND = re.compile(r"\bc'est quand (?:le |la |les |l')?(?P<quoi>[\w' -]{3,40}?)\W*$")
# « c'est quand » souvent mal entendu (« c'est Khan, le rendez-vous », « c'est ça le rendez-vous test ») :
# accepté seulement si un rendez-vous de l'agenda correspond vraiment
_QUAND_FLOU = re.compile(r"^\W*(?:(?:c'est|ces|ses|s'est)\W+(?:qu'en|quand|khan|kan|camp|comme|con|ça|ca|carl|car|cols?|quel)|second(?:e|es)?)\W+"
                         r"(?:le |la |les |l'|mon |ma |mes )?(?P<quoi>[\w' -]{3,40}?)\W*$")
_PROCHAIN = re.compile(r"^(?:mon |ma |notre )?prochaine? (?:rendez[- ]vous|rdv|rendez)\b|^(?:mon |le )?(?:prochain )?rendez[- ]vous$")
_SUJET_AGENDA = re.compile(r"rendez[- ]vous|\brdv\b|agenda|calendrier|planning|emploi du temps|c'est quand|prochain")


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t.lower()


def commande(t):
    """« c'est quand le dentiste ? » : cherche dans l'agenda relié (60 jours). La liste des rendez-vous d'une période
    (« mon agenda de demain ») est donnée par jarvis_foyer, qui mêle le calendrier familial de Jarvis et l'agenda relié."""
    t = t.replace("’", "'").lower()
    maintenant = datetime.datetime.now()
    aujourd_hui = maintenant.date()
    q = _QUAND.search(t)
    flou = False
    if not q:
        q, flou = _QUAND_FLOU.search(re.sub(r"\s*,\s*", " ", t)), True
    if not q or _AGENDA.search(t):
        return None
    quoi = q.group("quoi").strip()
    cherche = _sans_accents(re.sub(r"^(?:prochain|prochaine)\s+", "", quoi)).strip()
    if len(cherche) < 3 or re.match(r"(?:prochaines? vacances|vacances|rentr|f[ée]ri|poubelle|verre|anniversaire)", cherche):
        return None
    liste = evenements(maintenant, maintenant + datetime.timedelta(days=60))
    if liste is None:
        return None
    if _PROCHAIN.search(_sans_accents(quoi)):            # « c'est quand mon prochain rendez-vous ? »
        trouves = liste[:1]
    else:
        mots = [m for m in re.findall(r"\w+", cherche) if len(m) > 2 and m not in ("pour", "avec", "des", "les")]
        trouves = [e for e in liste if mots and all(m in _sans_accents(e["titre"]) for m in mots)]
    if not trouves:
        if not flou:
            # pas dans l'agenda : une autre commande (ou Claude) répondra, mais Claude saura que l'agenda a été lu
            global _non_trouve
            _non_trouve = (time.time(), quoi)
        return None
    e = trouves[0]
    return f"Dans l'agenda : {_phrase(e, aujourd_hui)}" + (f" (lieu : {e['lieu']})" if e["lieu"] else "") + "."


_non_trouve = None          # (heure, ce qui a été cherché) : la dernière recherche « c'est quand … » sans résultat


def note_claude(demande=""):
    """Note pour Claude quand la demande touche à l'agenda (ou vient d'y chercher en vain) : la liste des prochains
    rendez-vous, pour qu'il réponde même à une phrase mal entendue, sans dire qu'il ne peut pas consulter l'agenda
    et sans rien inventer. Vide sinon."""
    global _non_trouve
    recherche, _non_trouve = _non_trouve, None
    recente = bool(recherche) and time.time() - recherche[0] <= 15
    if not recente and not _SUJET_AGENDA.search(_sans_accents(demande.replace("’", "'"))):
        return ""
    maintenant = datetime.datetime.now()
    try:
        liste = evenements(maintenant, maintenant + datetime.timedelta(days=60))
    except Exception:
        liste = None
    if liste is None:
        return ""
    aujourd_hui = maintenant.date()
    if liste:
        contenu = "voici ses prochains rendez-vous : " + " ; ".join(_phrase(e, aujourd_hui) for e in liste[:10]) + "."
    else:
        contenu = "il n'y a aucun rendez-vous dans les 60 prochains jours."
    cherche = f" Il n'y a rien qui corresponde à « {recherche[1]} »." if recente else ""
    return ("(Note : Jarvis a consulté à l'instant l'agenda de la personne qui parle ; " + contenu + cherche +
            " Si la question porte sur un rendez-vous de la famille (même mal retranscrite), réponds à partir de "
            "cette liste uniquement, en une ou deux phrases, sans inventer de date ni de prénom, et ne dis jamais "
            "que tu ne peux pas consulter l'agenda. Si elle porte sur autre chose, ignore cette note.) ")


def rendez_vous_de_demain():
    """Phrase du rappel de la veille, ou None s'il n'y a rien."""
    demain = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
    liste = evenements(demain, demain + datetime.timedelta(days=1)) or []
    liste = [e for e in liste if e["debut"] >= demain or e["journee"]]
    if not liste:
        return None
    aujourd_hui = datetime.date.today()
    return "Demain dans l'agenda : " + " ; ".join(_phrase(e, aujourd_hui, avec_jour=False) for e in liste[:5]) + "."


def _veille_faite(fichier_date, jour, nom):
    """Vrai si le rappel de la veille a déjà été fait aujourd'hui pour cet agenda. (Ancien format du fichier : la
    date seule, qui vaut pour le profil principal.)"""
    try:
        with open(fichier_date, encoding="utf-8") as f:
            lignes = [l.strip() for l in f.read().splitlines() if l.strip()]
    except OSError:
        return False
    return (jour + " " + nom) in lignes or (jour in lignes and nom == CIBLE)


def _noter_veille(fichier_date, jour, nom):
    try:
        with open(fichier_date, encoding="utf-8") as f:
            lignes = [l.strip() for l in f.read().splitlines() if l.strip().startswith(jour + " ")]
    except OSError:
        lignes = []
    if (jour + " " + nom) not in lignes:
        lignes.append(jour + " " + nom)
    with open(fichier_date, "w", encoding="utf-8") as f:
        f.write("\n".join(lignes) + "\n")


def surveiller(annoncer, fichier_date):
    """La veille au soir, une seule fois par profil : les rendez-vous du lendemain de la personne qui est là
    (le profil en cours). Un profil qui n'a pas relié d'agenda n'entend rien, et rien de l'agenda d'un autre."""
    def boucle():
        time.sleep(150)
        while True:
            try:
                jour = time.strftime("%Y-%m-%d")
                if time.localtime().tm_hour >= HEURE_VEILLE and _lien() and not _veille_faite(fichier_date, jour, cible()):
                    phrase = rendez_vous_de_demain()
                    _noter_veille(fichier_date, jour, cible())
                    if phrase:
                        annoncer(phrase)
            except Exception as erreur:
                print("Agenda, rappel de la veille :", erreur)
            time.sleep(600)
    threading.Thread(target=boucle, daemon=True).start()
