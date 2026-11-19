"""
JARVIS - petites commandes du quotidien (version 1.24).

  « quelle heure est-il à Tokyo ? »                  l'heure dans une autre ville du monde
  « ouvre le dernier téléchargement »                le fichier le plus récent du dossier Téléchargements
  « où j'en étais ? », « rouvre mes onglets »        Chrome rouvre les onglets de la dernière fois
  « active le mode cinéma » / « désactive... »       vidéo en plein écran, Jarvis répond par écrit
  « ferme tout »                                     ferme toutes les fenêtres, après confirmation
                                                     (chaque application propose d'enregistrer)
  « donne-moi la recette des crêpes étape par étape » puis « étape suivante », « étape précédente »,
                                                     « répète l'étape », « étape 3 »
  « l'anniversaire de Marie est le 3 mars »          retenu par Jarvis : il le rappelle la veille et le jour même
  « quand est l'anniversaire de Marie ? », « quels sont les prochains anniversaires ? »
  « active le mode invité » / « désactive... »       un invité utilise Jarvis : ni mails, ni notes, ni mémoire
"""

import ctypes
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import jarvis_config

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
_MOIS_RE = r"(janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[uû]t|septembre|octobre|novembre|d[ée]cembre)"
SANS_FENETRE = 0x08000000


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t


def _json(url, delai=10):
    requete = urllib.request.Request(url, headers={"User-Agent": "Jarvis"})
    with urllib.request.urlopen(requete, timeout=delai) as reponse:
        return json.loads(reponse.read().decode("utf-8"))


# ---------- L'heure ailleurs dans le monde ----------

_HEURE_AILLEURS = re.compile(r"\bquelle heure\b(?: est[- ]il| il est| fait[- ]il)?\s+(?:à|a|au|aux|en)\s+(?P<lieu>[^?!.]+)")


def commande_heure_ailleurs(t):
    m = _HEURE_AILLEURS.search(t.replace("’", "'"))
    if not m:
        return None
    lieu = re.sub(r"\b(maintenant|en ce moment|actuellement|là[- ]bas|s'il te pla[iî]t|jarvis)\b", "", m.group("lieu")).strip()
    if not lieu:
        return None
    try:
        trouves = _json("https://geocoding-api.open-meteo.com/v1/search?count=1&language=fr&format=json&name="
                        + urllib.parse.quote(lieu)).get("results") or []
        if not trouves:
            return f"Je ne trouve pas de ville qui s'appelle {lieu}."
        ville = trouves[0]
        prevision = _json("https://api.open-meteo.com/v1/forecast?latitude={}&longitude={}&current=temperature_2m"
                          "&timezone=auto".format(ville["latitude"], ville["longitude"]))
        decalage = int(prevision["utc_offset_seconds"])
    except Exception as erreur:
        print("Heure ailleurs :", erreur)
        return "Je n'arrive pas à trouver l'heure de cette ville pour le moment."
    la_bas = time.gmtime(time.time() + decalage)
    ici = time.localtime()
    h, mn = la_bas.tm_hour, la_bas.tm_min
    heure = "minuit" if h == 0 else "midi" if h == 12 else f"{h} heure{'s' if h > 1 else ''}"
    phrase = f"À {ville['name']}, il est {heure}{f' {mn}' if mn else ''}"
    ecart = round((decalage - ici.tm_gmtoff) / 3600, 1)
    jours = (la_bas.tm_yday - ici.tm_yday) if la_bas.tm_year == ici.tm_year else (1 if la_bas.tm_year > ici.tm_year else -1)
    if jours > 0:
        phrase += ", déjà demain"
    elif jours < 0:
        phrase += ", encore hier"
    if ecart:
        nombre = (str(int(abs(ecart))) if ecart == int(ecart) else str(abs(ecart)).replace(".", " heure ")
                  .replace(" heure 5", " heures et demie"))
        nombre = nombre if " heure" in nombre else nombre + (" heures" if abs(ecart) >= 2 else " heure")
        phrase += f" : {nombre} de {'plus' if ecart > 0 else 'moins'} qu'ici"
    return phrase + "."


# ---------- Dernier téléchargement ----------

def _telechargements():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as cle:
            valeur = winreg.QueryValueEx(cle, "{374DE290-123F-4565-9164-39C4925E467B}")[0]
            return os.path.expandvars(valeur)
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Downloads")


def commande_dernier_telechargement(t):
    if not re.search(r"\b(dernier|derni[eè]re|plus r[ée]cent)\b.*\bt[ée]l[ée]charg|\bt[ée]l[ée]charg\w*\b.*\b(dernier|plus r[ée]cent)\b"
                     r"|\bce que je viens de t[ée]l[ée]charger\b", t):
        return None
    dossier = _telechargements()
    try:
        fichiers = [os.path.join(dossier, nom) for nom in os.listdir(dossier)
                    if not nom.lower().endswith((".crdownload", ".tmp", ".part", ".ini"))]
        fichiers = [f for f in fichiers if os.path.isfile(f)]
    except OSError:
        fichiers = []
    if not fichiers:
        return "Ton dossier Téléchargements est vide."
    dernier = max(fichiers, key=os.path.getmtime)
    nom = os.path.basename(dernier)
    if re.search(r"\b(c'est quoi|quel est|quelle est|comment s'appelle|dis-moi)\b", t) and not re.search(r"\bouvre\b", t):
        return f"Ton dernier téléchargement, c'est {os.path.splitext(nom)[0]}."
    if nom.lower().endswith((".exe", ".msi", ".bat", ".cmd", ".ps1", ".vbs", ".js", ".scr")):
        # un programme : on ne le lance pas à la voix, on le montre dans l'explorateur
        subprocess.Popen(["explorer.exe", "/select,", dernier])
        return f"Ton dernier téléchargement est un programme, {nom}. Je te le montre dans le dossier, sans le lancer."
    os.startfile(dernier)
    return f"J'ouvre {os.path.splitext(nom)[0]}."


# ---------- Où j'en étais : les onglets de Chrome ----------

def _chrome():
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""),
                 os.environ.get("LOCALAPPDATA", "")):
        chemin = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
        if base and os.path.exists(chemin):
            return chemin
    return None


def _chrome_ouvert():
    try:
        import psutil
        return any((p.info["name"] or "").lower() == "chrome.exe" for p in psutil.process_iter(["name"]))
    except Exception:
        return False


def commande_ou_jen_etais(t):
    if re.search(r"\b(histoire|recette|livre|lecture)\b", t):
        return None
    if not re.search(r"\bo[uù] j'en [ée]tais\b|\b(rouvre|réouvre|reouvre|restaure|récupère|recupere)\b.*\bonglets?\b", t):
        return None
    chrome = _chrome()
    if not chrome:
        return "Je ne trouve pas Google Chrome sur cet ordinateur."
    if _chrome_ouvert():
        # Chrome déjà ouvert : Ctrl+Maj+T rouvre les derniers onglets ou la dernière fenêtre fermés
        subprocess.Popen([chrome])
        time.sleep(1.2)
        import jarvis_pratique
        jarvis_pratique.touches(jarvis_pratique.CTRL, jarvis_pratique.MAJ, 0x54)
        return "Je rouvre ce que tu avais fermé en dernier dans Chrome."
    subprocess.Popen([chrome, "--restore-last-session"])
    return "Je rouvre Chrome avec tes onglets de la dernière fois."


# ---------- Mode cinéma ----------

_cinema = {"actif": False, "nuit_avant": False}


def commande_cinema(t):
    if not re.search(r"\bmode (?:cin[ée]ma|film)\b", t):
        return None
    import jarvis_voix
    if re.search(r"\b(d[ée]sactive|enl[eè]ve|arr[eê]te|coupe|quitte|sors|stop|fin du)\b", t):
        if not _cinema["actif"]:
            return "Le mode cinéma n'est pas activé."
        _cinema["actif"] = False
        jarvis_voix.forcer_nuit(_cinema["nuit_avant"])
        return "Mode cinéma terminé. Bon retour !"
    if re.search(r"\b(est-ce que|es-tu|tu es|est activ[ée]|est actif)\b", t) and not re.search(r"\b(active|mets|lance)\b", t):
        return "Le mode cinéma est activé." if _cinema["actif"] else "Le mode cinéma n'est pas activé."
    if _cinema["actif"]:
        return "Le mode cinéma est déjà activé."
    _cinema.update(actif=True, nuit_avant=jarvis_voix.mode_nuit())
    message = "Mode cinéma : je réponds par écrit pour ne pas te déranger. Bon film !"
    try:
        import jarvis_fenetres
        import jarvis_pratique
        fenetre = jarvis_fenetres.active()
        if fenetre and re.search(r"youtube|netflix|prime video|disney|vimeo|twitch|molotov|france\.tv|arte",
                                 jarvis_fenetres._texte(fenetre).lower()):
            jarvis_pratique.touches(0x46)          # touche F : plein écran de la vidéo
    except Exception as erreur:
        print("Mode cinéma :", erreur)
    # la phrase est encore dite à voix haute ; ensuite seulement, Jarvis passe en mode écrit
    minuteur = threading.Timer(7, lambda: jarvis_voix.forcer_nuit(True) if _cinema["actif"] else None)
    minuteur.daemon = True
    minuteur.start()
    return message


# ---------- Ferme tout ----------

PROGRAMMES_GARDES = {"claude", "explorer", "pythonw", "python", "jarvis", "textinputhost", "shellexperiencehost",
                     "searchhost", "startmenuexperiencehost", "applicationframehost", "systemsettings"}


def _fermer_tout():
    import jarvis_fenetres
    fermees = 0
    for hwnd, titre, programme in jarvis_fenetres.fenetres():
        if (programme or "").lower() in PROGRAMMES_GARDES and not ((programme or "").lower() == "explorer"
                                                                  and jarvis_fenetres._classe(hwnd) == "CabinetWClass"):
            continue
        jarvis_fenetres.fermer(hwnd)
        fermees += 1
    if not fermees:
        return "Il n'y avait aucune fenêtre à fermer."
    return ("Je ferme tout. Si un document n'est pas enregistré, l'application te demandera quoi faire."
            if fermees > 1 else "Je ferme la fenêtre ouverte.")


def commande_ferme_tout(t, demander_confirmation):
    if not re.search(r"^\W*(?:jarvis\W+)?(?:ferme|fermer|quitte)\s+(?:tout|toutes? les fen[eê]tres|toutes? les applications?"
                     r"|tous les programmes)\W*$", t):
        return None
    demander_confirmation(_fermer_tout)
    return "Tu veux que je ferme toutes les fenêtres ? Dis oui pour confirmer."


# ---------- Recette pas à pas ----------

FICHIER_RECETTE = jarvis_config.chemin("recette.json")
_RECETTE_DEMANDEE = re.compile(r"\brecette\b.*\b(?:[ée]tape par [ée]tape|pas à pas|pas a pas|guide|guide-moi|avec moi)\b"
                               r"|\b(?:[ée]tape par [ée]tape|pas à pas|guide-moi)\b.*\b(?:recette|cuisiner|pr[ée]parer|faire)\b")


def note_recette(demande):
    """Consigne pour Claude quand une recette pas à pas est demandée (sinon « »)."""
    if not _RECETTE_DEMANDEE.search(demande.lower()):
        return ""
    return ("(Recette pas à pas : dis d'abord brièvement les ingrédients et les quantités, puis la première étape "
            "seulement, puis : « Dis Jarvis, étape suivante, quand tu es prêt. » Termine OBLIGATOIREMENT ta réponse "
            "par une ligne seule qui commence par RECETTE: suivie du nom du plat, puis de toutes les étapes dans "
            "l'ordre, séparées par ||, chacune en une ou deux phrases, à lire à voix haute. Cette ligne ne sera pas lue.) ")


def appliquer_recette(reponse):
    """Retire la ligne RECETTE: de la réponse et garde les étapes pour la suite."""
    m = re.search(r"^\s*RECETTE\s*:(.*)$", reponse, re.M | re.S)
    if not m:
        return reponse
    morceaux = [" ".join(e.split()) for e in m.group(1).split("||") if e.strip()]
    if len(morceaux) >= 2:
        try:
            with open(FICHIER_RECETTE, "w", encoding="utf-8") as f:
                json.dump({"plat": morceaux[0], "etapes": morceaux[1:], "position": 0, "date": time.time()}, f, ensure_ascii=False)
        except OSError:
            pass
    return reponse[:m.start()].rstrip()


_NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
            "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "premiere": 1, "première": 1, "dernière": -1, "derniere": -1}


def commande_etape(t):
    if not re.search(r"\b[ée]tapes?\b", t) or len(t.split()) > 7 or re.search(r"\b(projet|travail|mon|ma|mes)\b", t):
        return None
    try:
        with open(FICHIER_RECETTE, encoding="utf-8") as f:
            recette = json.load(f)
        etapes, position = recette["etapes"], int(recette.get("position", 0))
        if time.time() - float(recette.get("date", 0)) > 6 * 3600:      # une recette d'un autre jour est oubliée
            return None
    except (OSError, ValueError, KeyError, TypeError):
        return None                                 # pas de recette en cours : la demande va à Claude
    total = len(etapes)
    if re.search(r"\bcombien\b", t):
        return f"La recette a {total} étapes. Tu es à l'étape {position + 1}."
    m = re.search(r"\b[ée]tape (?:num[ée]ro )?(\d+|\w+)\b", t)
    if re.search(r"\b(suivantes?|d'apr[eè]s|prochaines?|ensuite|apr[eè]s)\b", t):
        if position + 1 >= total:
            return "C'était la dernière étape. Bon appétit !"
        position += 1
    elif re.search(r"\b(pr[ée]c[ée]dentes?|d'avant|retour)\b", t):
        position = max(0, position - 1)
    elif m and (m.group(1).isdigit() or m.group(1) in _NOMBRES):
        n = int(m.group(1)) if m.group(1).isdigit() else _NOMBRES[m.group(1)]
        position = total - 1 if n == -1 else max(0, min(total - 1, n - 1))
    elif not re.search(r"\b(r[ée]p[eè]te|redis|relis|quelle|o[uù] j'en suis|actuelle|en cours)\b", t):
        return None
    recette["position"] = position
    try:
        with open(FICHIER_RECETTE, "w", encoding="utf-8") as f:
            json.dump(recette, f, ensure_ascii=False)
    except OSError:
        pass
    fin = " C'est la dernière étape." if position == total - 1 else ""
    return f"Étape {position + 1} : {etapes[position]}{fin}"


# ---------- Anniversaires des proches (retenus dans la mémoire de Jarvis) ----------

FICHIER_ANNONCES = jarvis_config.chemin("anniversaires.date")
# le jour peut être écrit en lettres (« le trois mars ») : Whisper le fait souvent
_JOURS_MOTS = {m: i + 1 for i, m in enumerate(
    "un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize dix-sept dix-huit "
    "dix-neuf vingt vingt-et-un vingt-deux vingt-trois vingt-quatre vingt-cinq vingt-six vingt-sept vingt-huit "
    "vingt-neuf trente trente-et-un".split())}
_JOURS_MOTS.update({"vingt et un": 21, "trente et un": 31})
_JOUR_RE = r"(?P<jour>\d{1,2}|premier|1er|" + "|".join(sorted((re.escape(m) for m in _JOURS_MOTS), key=len, reverse=True)) + ")"
_ANNIV_FAIT = re.compile(r"\banniversaire (?:de |d')(?P<nom>[\w\-' ]+?) (?:est |et |c'est |tombe )?(?:le )?" + _JOUR_RE + " "
                         + _MOIS_RE, re.I)
_NE_FAIT = re.compile(r"^(?P<nom>[\w\-' ]+?) (?:est |sont )?n[ée]e?s? le " + _JOUR_RE + " "
                      + _MOIS_RE, re.I)


def _jour(texte):
    texte = texte.lower()
    if texte in ("premier", "1er"):
        return 1
    return _JOURS_MOTS.get(texte) or int(texte)


def _mois(nom):
    nom = _sans_accents(nom.lower())
    return [_sans_accents(m) for m in MOIS].index(nom) + 1


def anniversaires():
    """[(nom, jour, mois)] trouvés dans la mémoire de Jarvis (hors ceux de l'utilisateur lui-même)."""
    import jarvis_memoire
    trouves = {}
    for fait in jarvis_memoire.faits():
        texte = " ".join(str(fait).split())
        m = _ANNIV_FAIT.search(texte) or _NE_FAIT.search(texte)
        if not m:
            continue
        nom = re.sub(r"(?i)^(mon|ma|mes) ", lambda x: {"mon": "ton ", "ma": "ta ", "mes": "tes "}[x.group(1).lower()],
                     m.group("nom").strip())
        if re.match(r"(?i)^(je|j'|moi|mon anniversaire|l'utilisateur|tonynio)\b", nom) or re.search(r"(?i)\b(je suis|mon)$", nom):
            continue
        try:
            jour = _jour(m.group("jour"))
            trouves[nom.lower()] = (nom, jour, _mois(m.group(m.lastindex)))
        except ValueError:
            pass
    return list(trouves.values())


def _date_parlee(jour, mois):
    return f"{'premier' if jour == 1 else jour} {MOIS[mois - 1]}"


def _jours_avant(jour, mois):
    aujourdhui = time.localtime()
    for annee in (aujourdhui.tm_year, aujourdhui.tm_year + 1):
        try:
            cible = time.mktime((annee, mois, jour, 12, 0, 0, 0, 0, -1))
        except (OverflowError, ValueError):
            return None
        debut = time.mktime((aujourdhui.tm_year, aujourdhui.tm_mon, aujourdhui.tm_mday, 12, 0, 0, 0, 0, -1))
        if cible >= debut - 3600:
            return round((cible - debut) / 86400)
    return None


def commande_anniversaire(t, brut):
    t = t.replace("’", "'")
    m = _ANNIV_FAIT.search(t)
    if m and not re.search(r"\b(quand|quel|quelle|c'est quand)\b", t):
        import jarvis_memoire
        nom = m.group("nom").strip()
        if re.match(r"^(mon|ma|je)\b", nom):
            return None
        nom_propre = " ".join(w.capitalize() if not w.startswith(("de", "d'")) else w for w in nom.split())
        jour = _jour(m.group("jour"))
        jarvis_memoire.retenir(f"L'anniversaire de {nom_propre} est le {_date_parlee(jour, _mois(m.group(m.lastindex)))}")
        return f"C'est retenu : je te le rappellerai la veille et le jour même."
    if not re.search(r"\banniversaires?\b", t) or re.search(r"\bmon anniversaire\b", t):
        return None
    liste = anniversaires()
    if re.search(r"\b(prochains?|à venir|les anniversaires|quels anniversaires)\b", t):
        if not liste:
            return "Je ne connais encore aucun anniversaire. Dis par exemple : l'anniversaire de Marie est le 3 mars."
        prochains = sorted((j, n, jo, mo) for n, jo, mo in liste if (j := _jours_avant(jo, mo)) is not None)[:3]
        morceaux = []
        for j, n, jo, mo in prochains:
            quand = "aujourd'hui" if j == 0 else "demain" if j == 1 else f"le {_date_parlee(jo, mo)}"
            morceaux.append(f"{n} {quand}")
        return "Les prochains anniversaires : " + ", ".join(morceaux) + "."
    q = re.search(r"\banniversaire (?:de |d')(?P<nom>[\w\-' ]+?)\W*$", t)
    if q and re.search(r"\b(quand|quel|quelle|c'est quand|date)\b", t):
        cherche = _sans_accents(q.group("nom").lower().strip())
        for n, jo, mo in liste:
            if _sans_accents(n.lower()) == cherche or cherche in _sans_accents(n.lower()).split():
                j = _jours_avant(jo, mo)
                suite = " C'est aujourd'hui !" if j == 0 else " C'est demain !" if j == 1 else \
                    f" Dans {j} jours." if j is not None else ""
                return f"L'anniversaire de {n} est le {_date_parlee(jo, mo)}.{suite}"
        return f"Je ne connais pas la date d'anniversaire de {q.group('nom').strip().title()}."
    return None


def surveiller_anniversaires(annoncer):
    """Une fois par jour (après 8 heures) : annonce les anniversaires de la veille et du jour même."""
    def boucle():
        time.sleep(90)
        while True:
            try:
                jour = time.strftime("%Y-%m-%d")
                deja = ""
                try:
                    with open(FICHIER_ANNONCES, encoding="utf-8") as f:
                        deja = f.read().strip()
                except OSError:
                    pass
                if deja != jour and time.localtime().tm_hour >= 8:
                    phrases = []
                    for nom, jo, mo in anniversaires():
                        j = _jours_avant(jo, mo)
                        if j == 0:
                            phrases.append(f"Aujourd'hui, c'est l'anniversaire de {nom} !")
                        elif j == 1:
                            phrases.append(f"Demain, c'est l'anniversaire de {nom}.")
                    with open(FICHIER_ANNONCES, "w", encoding="utf-8") as f:
                        f.write(jour)
                    if phrases:
                        annoncer(" ".join(phrases))
            except Exception as erreur:
                print("Anniversaires :", erreur)
            time.sleep(600)
    threading.Thread(target=boucle, daemon=True).start()


# ---------- Mode invité ----------

_invite = {"actif": False}
redemarrer_claude = False          # lu par jarvis_claude : nouvelle conversation, sans la mémoire


def invite():
    return _invite["actif"]


def commande_invite(t):
    global redemarrer_claude
    if not re.search(r"\bmode (?:invit[ée]s?|visiteurs?)\b", t):
        return None
    if re.search(r"\b(d[ée]sactive|enl[eè]ve|arr[eê]te|coupe|quitte|sors|stop|fin du)\b", t):
        if not _invite["actif"]:
            return "Le mode invité n'est pas activé."
        _invite["actif"] = False
        redemarrer_claude = True
        return "Mode invité désactivé. Je retrouve ta mémoire, tes notes et tes mails."
    if re.search(r"\b(est-ce que|es-tu|tu es)\b", t) and not re.search(r"\bactive\b", t):
        return "Le mode invité est activé." if _invite["actif"] else "Le mode invité n'est pas activé."
    _invite["actif"] = True
    redemarrer_claude = True
    return ("Mode invité activé : je ne donne accès ni aux mails, ni aux notes, ni à ma mémoire, "
            "et je n'enregistre rien de nos échanges. Dis désactive le mode invité pour revenir.")


_PRIVE = re.compile(r"\b(mails?|e-mails?|courriels?|messages?|notes?|pense-b[eê]te|m[ée]moire|souviens|retiens|oublie|"
                    r"liste de courses|ma liste|mes listes?|rappelle-toi)\b")


def refus_invite(t):
    if _invite["actif"] and _PRIVE.search(t):
        return "En mode invité, je ne donne pas accès aux mails, aux notes ni à ma mémoire."
    return None


# ---------- Résumé d'une vidéo YouTube (avec sa transcription, affichée par YouTube lui-même) ----------

VIDEO_POUR_CLAUDE = re.compile(r"\b(?:résume|resume|résumer|résumé|résument|de quoi parle|que dit|qu'est-ce que dit|explique)\b"
                               r".*\b(?:cette vidéo|la vidéo|cette video|la video|ce youtube)\b")


def transcription_youtube():
    """Sur une vidéo YouTube au premier plan : ouvre le panneau « Transcription » de YouTube et en copie le texte.
    Renvoie le texte, ou « » si la vidéo n'a pas de transcription."""
    import jarvis_web
    if not jarvis_web.navigateur_actif():
        return ""
    import jarvis_fenetres
    fenetre = jarvis_fenetres.active()
    if not fenetre or "youtube" not in jarvis_fenetres._texte(fenetre).lower():
        return ""
    bouton = jarvis_web._meilleur(["Afficher la transcription", "Show transcript"], seuil=0.85)
    if bouton is None:                                  # le bouton est dans la description : on la déplie
        plus = jarvis_web._meilleur(["...plus", "…plus", "Plus", "afficher plus", "...more", "more"], seuil=0.9)
        if plus is not None:
            jarvis_web._activer(plus)
            time.sleep(1.0)
            bouton = jarvis_web._meilleur(["Afficher la transcription", "Show transcript"], seuil=0.85)
    if bouton is not None:
        jarvis_web._activer(bouton)
        time.sleep(2.5)                                 # le temps que YouTube charge la transcription
    texte = jarvis_web.texte_de_la_page()
    # les lignes de la transcription commencent par un horodatage (« 0:12 », « 1:02:03 »)
    lignes = texte.splitlines()
    morceaux, dans_transcription = [], False
    for i, ligne in enumerate(lignes):
        ligne = ligne.strip()
        if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", ligne):
            dans_transcription = True
            continue
        if dans_transcription and ligne and not re.search(r"secondes?$|minutes?$", ligne):
            morceaux.append(ligne)
    return " ".join(morceaux)


# ---------- Couleurs du réacteur en veille ----------

FICHIER_APPARENCE = jarvis_config.chemin("apparence.json")
PALETTES = {
    "vice city": ("#ff2e97", "#ff8c42", "#9d4dff"),
    "bleu": ("#2f9bff", "#00e1ff", "#5b6cff"),
    "vert": ("#2bff88", "#00e1b4", "#9dff4d"),
    "rouge": ("#ff3b3b", "#ff7a2e", "#ff2e97"),
    "violet": ("#9d4dff", "#d04dff", "#5b6cff"),
    "orange": ("#ff8c42", "#ffc142", "#ff5e3a"),
    "iron man": ("#ff3b2f", "#ffb52e", "#ffd75e"),
    "océan": ("#00b4d8", "#0077ff", "#48e5c2"),
    "forêt": ("#3ddc84", "#a3e635", "#14b8a6"),
}
_COULEUR = re.compile(r"\b(vice city|iron man|oc[ée]an|for[êe]t|bleu|bleue|vert|verte|rouge|violet|violette|orange)\b")


def _reacteur():
    import sys
    for nom in ("__main__", "jarvis_reacteur"):
        module = sys.modules.get(nom)
        if module is not None and hasattr(module, "COULEURS_VEILLE"):
            return module
    return None


def appliquer_couleur(nom=None):
    """Applique la palette choisie (ou celle gardée dans apparence.json) au réacteur. Renvoie le nom, ou None."""
    if nom is None:
        try:
            with open(FICHIER_APPARENCE, encoding="utf-8") as f:
                nom = json.load(f).get("couleur")
        except (OSError, ValueError, AttributeError):
            return None
    if nom not in PALETTES:
        return None
    module = _reacteur()
    if module is not None:
        module.COULEURS_VEILLE = PALETTES[nom]
    return nom


def choisir_couleur(texte):
    m = _COULEUR.search(texte)
    if not m:
        return None
    nom = m.group(1).rstrip("e") if m.group(1) in ("bleue", "verte") else m.group(1)
    nom = {"violette": "violet", "ocean": "océan", "foret": "forêt"}.get(nom, nom)
    appliquer_couleur(nom)
    try:
        with open(FICHIER_APPARENCE, "w", encoding="utf-8") as f:
            json.dump({"couleur": nom}, f)
    except OSError:
        pass
    return nom


def commande_couleur(t):
    if not re.search(r"\br[ée]acteur\b|\b(tes|ta) couleurs?\b|\bcouleurs? vice city\b", t) or not re.search(
            r"\b(mets|met|remets|remet|change|passe|repasse|choisis|prends|reprends|reviens|retourne|"
            r"je veux|je pr[ée]f[eè]re|en)\b", t):        # « remets les couleurs Vice City » aussi
        return None
    if re.search(r"\bquelles? couleurs?\b.*\b(possibles?|disponibles?|existe)", t):
        return "Je peux prendre les couleurs Vice City, bleu, vert, rouge, violet ou orange."
    nom = choisir_couleur(t)
    if not nom:
        return None
    return f"C'est fait : mon réacteur passe en {'couleurs Vice City' if nom == 'vice city' else nom}."
