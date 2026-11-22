# -*- coding: utf-8 -*-
"""
JARVIS - rapports pour améliorer Jarvis.

Ce que Jarvis envoie, et quand (le détail est dans docs/confidentialite.md) :
  - Compteur anonyme (tout le monde, désactivable dans les réglages) : un numéro tiré au hasard sur ce PC,
    la version de Jarvis et celle de Windows, au démarrage puis toutes les heures. Il sert à compter les
    installations et les utilisateurs actifs. Rien d'autre.
  - Rapport technique (seulement si l'utilisateur l'a accepté) : une fois par jour, les phrases mal comprises,
    les erreurs, les fonctions utilisées, les temps de réponse, les faux réveils, les demandes refaites ou
    annulées, les demandes confiées à Claude, la qualité du micro, les réglages jamais faits, les appareils
    associés (sans leur nom), le matériel du PC et les ateliers des enfants abandonnés (nom et étape seulement).
  - Rapport complet (seulement si l'utilisateur l'a choisi) : le rapport technique + les conversations.
  - « Signaler un problème », « Proposer une amélioration », le questionnaire : quand l'utilisateur les envoie.
Les textes sont nettoyés avant l'envoi : prénoms des profils, ville, adresses mail, numéros de téléphone,
codes et chemins de dossiers sont remplacés. Le mode invité n'enregistre rien.
L'envoi se fait en arrière-plan ; s'il échoue, Jarvis réessaie trois fois, puis abandonne ce rapport.
« Effacer mes données » (réglages) supprime ce qui a été envoyé depuis ce PC et le journal local.
"""

import collections
import difflib
import json
import os
import platform
import re
import secrets
import statistics
import sys
import threading
import time
import traceback
import urllib.request

import jarvis_config

DEPOT = "https://script.google.com/macros/s/AKfycbw3XAghBX-SX7H1ZmP1sLRFM3jvyRkDarC8Wmy-KPx6REKbOzIZ42lkGbHQq_AFvO3X/exec"
FICHIER = jarvis_config.chemin("rapports.json")              # réglages des rapports (reste sur ce PC)
JOURNAL = jarvis_config.chemin("rapports_journal.jsonl")     # ce qui attend le prochain rapport (reste sur ce PC)
CONTACT = "https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/issues"
INTERVALLE_SIGNAL = 3600            # compteur anonyme : toutes les heures
INTERVALLE_RAPPORT = 24 * 3600      # rapport technique : une fois par jour
ESSAIS = 3                          # un envoi qui échoue est retenté 3 fois, puis abandonné
JOURS_QUESTIONNAIRE = 7
JOURS_RAPPEL = 14                   # un seul rappel, deux semaines après un « non merci »
MAX_EVENEMENTS = 3000

NIVEAUX = {"aucun": "Rien", "technique": "Technique", "complet": "Complet"}      # (noms courts : liste des réglages)

_verrou = threading.RLock()
_donnees = None
_derniere_demande = {"t": 0.0, "texte": "", "action": False}
_niveaux_micro = collections.deque(maxlen=600)
_demarre = False


# ---------- Réglages des rapports ----------

def _lire():
    global _donnees
    if _donnees is None:
        try:
            with open(FICHIER, encoding="utf-8") as f:
                _donnees = json.load(f)
        except (OSError, ValueError):
            _donnees = {}
        if not isinstance(_donnees, dict):
            _donnees = {}
        change = False
        if not re.fullmatch(r"[0-9a-f]{32}", str(_donnees.get("id", ""))):
            _donnees["id"] = secrets.token_hex(16)              # numéro tiré au hasard, sans lien avec la personne
            change = True
        _donnees.setdefault("niveau", None)                     # None : pas encore demandé
        _donnees.setdefault("compteur", True)
        _donnees.setdefault("testeur", False)
        if "premier_lancement" not in _donnees:
            _donnees["premier_lancement"] = time.time()
            change = True
        if change:
            _ecrire()
    return _donnees


def _ecrire():
    try:
        provisoire = FICHIER + ".tmp"
        with open(provisoire, "w", encoding="utf-8") as f:
            json.dump(_donnees, f, ensure_ascii=False, indent=1)
        os.replace(provisoire, FICHIER)
    except OSError as erreur:
        print("Rapports : réglages non enregistrés :", erreur)


def valeur(cle, defaut=None):
    with _verrou:
        return _lire().get(cle, defaut)


def regler(cle, val):
    with _verrou:
        _lire()[cle] = val
        _ecrire()


def niveau():
    return valeur("niveau") or "aucun"


def choisir_niveau(n):
    """« aucun », « technique » ou « complet », choisi par l'utilisateur (fenêtre d'accord ou réglages)."""
    if n not in NIVEAUX:
        return
    with _verrou:
        d = _lire()
        d["niveau"] = n
        d["choisi_le"] = time.time()
        if n == "aucun":
            d.setdefault("refuse_le", time.time())
        _ecrire()
    print("(Rapports : niveau choisi :", n + ".)")
    if n == "aucun":
        _vider_journal()                 # plus rien n'attend d'être envoyé
    threading.Thread(target=_signal, daemon=True).start()


def a_demander():
    """Vrai s'il faut montrer la fenêtre d'accord : jamais répondu, ou un seul rappel après un « non merci »."""
    d = _lire()
    if d.get("niveau") is None:
        return True
    if (d.get("niveau") == "aucun" and not d.get("rappel_fait") and d.get("refuse_le")
            and time.time() - d["refuse_le"] > JOURS_RAPPEL * 86400):
        return True
    return False


def questionnaire_a_proposer():
    d = _lire()
    return (not d.get("questionnaire") and time.time() - d.get("premier_lancement", time.time())
            > JOURS_QUESTIONNAIRE * 86400)


# ---------- Nettoyage des textes ----------

def _noms_a_cacher():
    noms = set()
    try:
        noms.add(jarvis_config.PRENOM)
        import jarvis_profils
        noms.update(jarvis_profils._noms())
    except Exception:
        pass
    try:
        import jarvis_profils
        for dossier in os.listdir(jarvis_profils.DOSSIER):     # identifiants des voix apprises
            noms.add(dossier.strip("_"))
        noms.update(jarvis_profils._lire().keys())
    except Exception:
        pass
    noms.discard("principal")
    try:
        noms.add(os.environ.get("USERNAME", ""))
    except Exception:
        pass
    return sorted((n for n in noms if n and len(n) >= 2), key=len, reverse=True)


def _lieux_a_cacher():
    """La ville, le département et les villes voisines notés dans ville.txt."""
    lieux = set()
    try:
        with open(jarvis_config.chemin("ville.txt"), encoding="utf-8-sig") as f:
            for ligne in f:
                for morceau in re.split(r"[;,]", ligne):
                    m = re.sub(r"^(dans|en|à|a)\s+(le|la|les|l')?\s*", "", morceau.strip(), flags=re.I).strip()
                    if len(m) >= 3 and not re.fullmatch(r"[-\d.\s]+", m):
                        lieux.add(m)
    except OSError:
        pass
    return sorted(lieux, key=len, reverse=True)


def anonymiser(texte, longueur=300):
    """Le texte, sans rien qui permette de reconnaître ou de situer la personne."""
    t = str(texte or "")
    t = re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[mail]", t)
    t = re.sub(r"https?://\S+", "[lien]", t)
    t = re.sub(r"[A-Za-z]:\\[^\s\"']*", "[dossier]", t)
    t = re.sub(r"(?:\+33\s?|0)[1-9](?:[\s.-]?\d{2}){4}", "[téléphone]", t)
    t = re.sub(r"\d{5,}", "[nombre]", t)                        # codes postaux, codes, numéros
    for lieu in _lieux_a_cacher():
        t = re.sub(r"(?<!\w)" + re.escape(lieu) + r"(?!\w)", "[lieu]", t, flags=re.I)
    for nom in _noms_a_cacher():
        t = re.sub(r"(?<!\w)" + re.escape(nom) + r"(?!\w)", "[prénom]", t, flags=re.I)
    t = " ".join(t.split())
    return t[:longueur]


# ---------- Ce qui est noté sur ce PC ----------

def _invite():
    try:
        import jarvis_extras
        return jarvis_extras.invite()
    except Exception:
        return False


def noter(genre, **infos):
    """Ajoute un événement au journal local, seulement si l'utilisateur a accepté les rapports."""
    if niveau() == "aucun" or _invite():
        return
    if genre == "conversation" and niveau() != "complet":
        return
    infos["genre"] = genre
    infos["t"] = round(time.time())
    try:
        with _verrou:
            with open(JOURNAL, "a", encoding="utf-8") as f:
                f.write(json.dumps(infos, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _vider_journal():
    with _verrou:
        try:
            os.remove(JOURNAL)
        except OSError:
            pass


def _lire_journal():
    evenements = []
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            for ligne in f:
                try:
                    evenements.append(json.loads(ligne))
                except ValueError:
                    pass
    except OSError:
        pass
    return evenements[-MAX_EVENEMENTS:]


# Catégories des demandes (statistiques d'usage) : le premier mot-clé trouvé décide
CATEGORIES = [
    ("minuteur", r"minuteur|chrono|compte à rebours"), ("rappel", r"rappelle|rappel\b|réveil|alarme"),
    ("météo", r"météo|temps fera|pleuvoir|pluie|neige|vigilance|température dehors"),
    ("heure et date", r"quelle heure|quel jour|quelle date|heure est-il"),
    ("calcul et conversion", r"combien font|calcule|convertis|fois \d|plus \d|racine"),
    ("musique", r"musique|chanson|spotify|playlist|deezer"), ("son", r"\bson\b|volume|monte le|baisse le|muet"),
    ("télé", r"télé|tele\b|chaîne|apple tv|netflix|freebox|player"), ("ps5", r"ps5|playstation|console"),
    ("internet et wifi", r"internet|wi-?fi|appel|répondeur|box"),
    ("navigateur", r"cherche|recherche|youtube|amazon|google|ouvre le site|clique|avance|recule"),
    ("applications", r"ouvre|ferme|lance|démarre|bloc-notes|calculatrice|explorateur"),
    ("écran et pc", r"luminosité|mode sombre|bluetooth|capture|écran|mon pc|ordinateur|batterie"),
    ("texte copié", r"copié|presse-papiers|résume|traduis|corrige"),
    ("mails et agenda", r"mail|rendez-vous|agenda|calendrier|prévu"),
    ("listes et notes", r"liste|note que|notes|courses"), ("famille et profils", r"profil|c'est \w+$|dis à|message"),
    ("ateliers enfants", r"calcul|dictée|animal|étoiles|défi|devinette|histoire"),
    ("réglages de jarvis", r"réglages|couleurs?|voix|micro|parle plus|version|mise à jour|mode nuit"),
    ("infos pratiques", r"gazole|essence|vacances|férié|anecdote|blague|actualités|point du jour"),
]


def categorie(texte):
    t = str(texte or "").lower()
    for nom, motif in CATEGORIES:
        if re.search(motif, t):
            return nom
    return "autre"


def demande(texte):
    """Appelé au début de chaque demande : repère les demandes refaites et les annulations."""
    maintenant = time.time()
    avant = _derniere_demande.copy()
    _derniere_demande.update(t=maintenant, texte=texte, action=False)
    ecart = maintenant - avant["t"]
    if not avant["texte"] or ecart > 60:
        return
    simple = lambda x: re.sub(r"[^\w ]", "", str(x).lower()).strip()
    if re.fullmatch(r"\W*(?:jarvis\W+)?(?:stop|arr[eê]te|annule|non\W*pas ça|non\W*pas ca|non c'est pas ça|laisse tomber"
                    r"|c'est pas ça|tais[- ]toi)\W*", str(texte).lower()):
        noter("annulation", demande=anonymiser(avant["texte"], 160), apres_s=round(ecart, 1))
    elif difflib.SequenceMatcher(None, simple(texte), simple(avant["texte"])).ratio() > 0.85:
        noter("refaite", demande=anonymiser(texte, 160), apres_s=round(ecart, 1))


def reponse(texte_demande, par, duree, erreur=False, etape="", origine="pc", enfant=False):
    """Une réponse donnée : par « local » (commande instantanée), « atelier » ou « claude » ;
    origine : « pc » ou « tablette ». Pour un profil enfant, jamais le texte de la demande : seulement sa catégorie."""
    cat = categorie(texte_demande)
    infos = {"categorie": cat, "par": par, "duree_s": round(duree, 2)}
    if origine != "pc":
        infos["origine"] = origine
    if etape:
        infos["etape"] = etape
    if erreur:
        infos["erreur"] = True
    noter("reponse", **infos)
    if par == "claude" and not enfant:
        noter("demande_claude", demande=anonymiser(texte_demande, 200), categorie=cat,
              **({"origine": origine} if origine != "pc" else {}))


def incompris(texte, raison="trop court"):
    noter("incompris", texte=anonymiser(texte, 200), raison=raison)


def faux_reveil(cause, entendu=""):
    noter("faux_reveil", cause=cause, entendu=anonymiser(entendu, 80))


def conversation(texte_demande, texte_reponse):
    noter("conversation", demande=anonymiser(texte_demande, 400), reponse=anonymiser(texte_reponse, 600))


def atelier(nom, fin, questions, etoiles=0):
    """Un atelier des enfants qui s'arrête : seulement son nom, comment il finit et l'étape (aucun prénom)."""
    noter("atelier", nom=nom, fin=fin, questions=int(questions), etoiles=int(etoiles))


def erreur(source, exc=None, texte=""):
    """Une erreur technique : le type, le message nettoyé et l'endroit dans le code (fichier et ligne)."""
    infos = {"source": source}
    if exc is not None:
        infos["type"] = type(exc).__name__
        infos["message"] = anonymiser(str(exc), 200)
        tb = traceback.extract_tb(exc.__traceback__)[-3:] if exc.__traceback__ else []
        infos["ou"] = [f"{os.path.basename(f.filename)}:{f.lineno}" for f in tb]
    if texte:
        infos["message"] = anonymiser(texte, 200)
    noter("erreur", **infos)


def _crochets():
    """Toutes les erreurs non rattrapées sont notées (et Jarvis fait comme avant)."""
    ancien = sys.excepthook

    def crochet(t, e, tb):
        try:
            e.__traceback__ = tb
            erreur("plantage", e)
        except Exception:
            pass
        ancien(t, e, tb)
    sys.excepthook = crochet
    ancien_fil = threading.excepthook

    def crochet_fil(args):
        try:
            if args.exc_value is not None:
                erreur("fil " + str(getattr(args.thread, "name", "")), args.exc_value)
        except Exception:
            pass
        ancien_fil(args)
    threading.excepthook = crochet_fil


def _erreurs_du_journal_precedent():
    """Les plantages de la session précédente (lus dans jarvis.log) : type d'erreur et endroit, rien d'autre."""
    try:
        with open(jarvis_config.chemin("jarvis.log"), encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 600_000))
            lignes = f.read().splitlines()
    except OSError:
        return
    debuts = [i for i, l in enumerate(lignes) if "démarrage de Jarvis =====" in l]
    if len(debuts) < 2:
        return
    session = lignes[debuts[-2]:debuts[-1]]
    vu = d = 0
    i = 0
    while i < len(session) and vu < 20:
        if session[i].startswith("Traceback"):
            ou = []
            k = i + 1
            while k < len(session) and (session[k].startswith(" ") or session[k].startswith("\t")):
                m = re.search(r'File "([^"]+)", line (\d+)', session[k])
                if m:
                    ou.append(f"{os.path.basename(m.group(1))}:{m.group(2)}")
                k += 1
            derniere = session[k] if k < len(session) else ""
            type_ = derniere.split(":")[0].strip()[:60]
            noter("erreur", source="plantage (session précédente)", type=type_,
                  message=anonymiser(derniere[len(type_) + 1:], 200), ou=ou[-3:])
            vu += 1
            i = k
        else:
            if "s'est arrêté tout seul" in session[i]:
                d += 1
            i += 1
    if d:
        noter("erreur", source="gardien", message=f"{d} arrêt(s) inattendu(s), Jarvis relancé")


# ---------- Le PC, les réglages, les appareils ----------

def _windows():
    try:
        v = sys.getwindowsversion()
        return f"Windows {'11' if v.build >= 22000 else '10'} (build {v.build})"
    except Exception:
        return platform.platform()[:40]


def _version_jarvis():
    try:
        import jarvis_maj
        return jarvis_maj.version_actuelle()
    except Exception:
        return "?"


def _materiel():
    m = {"windows": _windows(), "python": platform.python_version()}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            m["processeur"] = " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())[:80]
    except Exception:
        pass
    try:
        import ctypes

        class Memoire(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
        mem = Memoire()
        mem.dwLength = ctypes.sizeof(Memoire)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))
        m["memoire_go"] = round(mem.ullTotalPhys / 2 ** 30, 1)
    except Exception:
        pass
    try:
        import sounddevice as sd
        m["micro"] = anonymiser(sd.query_devices(kind="input")["name"], 80)
    except Exception:
        pass
    return m


def _existe(*morceaux):
    return os.path.exists(jarvis_config.chemin(*morceaux))


def _compte_json(*morceaux):
    try:
        with open(jarvis_config.chemin(*morceaux), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            for cle in ("teles", "appareils", "tablettes", "profils"):
                if isinstance(d.get(cle), (dict, list)):
                    return len(d[cle])
            return len(d)
        return len(d) if isinstance(d, list) else 1
    except (OSError, ValueError):
        return 0


def _reglages():
    """Les réglages faits ou jamais faits (oui / non, rien de leur contenu)."""
    import shutil
    voix = 0
    try:
        for nom in os.listdir(jarvis_config.chemin("profils")):
            voix += os.path.exists(jarvis_config.chemin("profils", nom, "voix.json"))
    except OSError:
        pass
    return {"prenom": bool(jarvis_config.PRENOM), "ville": _existe("ville.txt"),
            "claude": bool(shutil.which("claude")), "profils": _compte_json("profils.json"), "voix_apprises": voix,
            "mode_nuit_auto": bool(jarvis_config.HEURES_NUIT), "point_du_jour": bool(jarvis_config.SUJETS),
            "couleurs_choisies": _existe("apparence.json"), "reglages_modifies": _existe("preferences.json")}


def _appareils():
    """Les appareils associés à Jarvis (combien, jamais leur nom)."""
    def range_(cible):                 # identifiant rangé dans Windows ? (seulement oui ou non, rien n'est lu d'autre)
        try:
            import jarvis_mails
            return jarvis_mails.identifiants(cible) is not None
        except Exception:
            return False
    tablettes = 0
    try:
        with open(jarvis_config.chemin("tablette.json"), encoding="utf-8") as f:
            tablettes = len(json.load(f).get("sessions") or {})
    except (OSError, ValueError, AttributeError):
        pass
    try:
        ps5 = any(n.lower().startswith("ps5") for n in os.listdir(jarvis_config.chemin("tele")))
    except OSError:
        ps5 = False
    return {"teles": _compte_json("tele", "teles.json"), "tablettes": tablettes, "ps5": ps5,
            "apple_tv": range_("Jarvis-AppleTV-Companion"), "freebox": range_("Jarvis-Freebox"),
            "mails": range_("Jarvis-Mails"), "agenda": range_("Jarvis-Agenda"), "cameras": _existe("cameras.json")}


def _micro():
    """Le niveau du micro : bruit de fond (médiane) et sons forts (95 %), entre 0 et 1."""
    if len(_niveaux_micro) < 20:
        return {}
    v = sorted(_niveaux_micro)
    return {"bruit_de_fond": round(statistics.median(v), 4), "sons_forts": round(v[int(len(v) * 0.95)], 4),
            "mesures": len(v)}


def _suivre_micro():
    while True:
        time.sleep(30)
        try:
            jc = sys.modules.get("jarvis_claude")
            if jc is not None and not getattr(jc, "micro_coupe", False):
                _niveaux_micro.append(float(getattr(jc, "niveau_micro", 0.0)))
        except Exception:
            pass


# ---------- Construction et envoi ----------

def _mediane(valeurs):
    return round(statistics.median(valeurs), 2) if valeurs else None


def construire_rapport():
    ev = _lire_journal()
    par_genre = collections.defaultdict(list)
    for e in ev:
        par_genre[e.get("genre")].append(e)
    reponses = par_genre["reponse"]
    local = [e["duree_s"] for e in reponses if e.get("par") == "local"]
    claude = [e["duree_s"] for e in reponses if e.get("par") == "claude"]
    lents = sorted(reponses, key=lambda e: -e.get("duree_s", 0))[:10]
    rapport = {
        "genre": "rapport", "id": valeur("id"), "niveau": niveau(), "testeur": valeur("testeur"),
        "version": _version_jarvis(), "windows": _windows(),
        "periode": {"debut": min((e["t"] for e in ev), default=None), "fin": max((e["t"] for e in ev), default=None)},
        "materiel": _materiel(), "reglages": _reglages(), "appareils": _appareils(), "micro": _micro(),
        "statistiques": {"demandes": len(reponses), "locales": len(local), "claude": len(claude),
                         "par_categorie": dict(collections.Counter(e.get("categorie") for e in reponses)),
                         "par_origine": dict(collections.Counter(e.get("origine", "pc") for e in reponses))},
        "temps": {"local_median_s": _mediane(local), "claude_median_s": _mediane(claude),
                  "claude_max_s": max(claude) if claude else None,
                  "plus_lents": [{k: e.get(k) for k in ("categorie", "par", "duree_s", "etape")} for e in lents]},
        "incompris": [{k: e.get(k) for k in ("texte", "raison")} for e in par_genre["incompris"][-80:]],
        "faux_reveils": {"nombre": len(par_genre["faux_reveil"]),
                         "causes": dict(collections.Counter(e.get("cause") for e in par_genre["faux_reveil"])),
                         "entendu": [e.get("entendu") for e in par_genre["faux_reveil"][-20:] if e.get("entendu")]},
        "refaites": [{k: e.get(k) for k in ("demande", "apres_s")} for e in par_genre["refaite"][-40:]],
        "annulations": [{k: e.get(k) for k in ("demande", "apres_s")} for e in par_genre["annulation"][-40:]],
        "demandes_claude": [{k: e.get(k) for k in ("demande", "categorie")} for e in par_genre["demande_claude"][-80:]],
        "erreurs": [{k: e.get(k) for k in ("source", "type", "message", "ou")} for e in par_genre["erreur"][-40:]],
        "ateliers": [{k: e.get(k) for k in ("nom", "fin", "questions", "etoiles")} for e in par_genre["atelier"][-60:]],
    }
    if niveau() == "complet":
        rapport["conversations"] = [{k: e.get(k) for k in ("t", "demande", "reponse")}
                                    for e in par_genre["conversation"][-150:]]
    return rapport, len(ev)


def _envoyer(donnees):
    """Envoie au dépôt. Trois essais espacés, puis abandon. Renvoie True si c'est parti."""
    corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    for essai in range(ESSAIS):
        try:
            req = urllib.request.Request(DEPOT, data=corps, headers={"Content-Type": "application/json",
                                                                     "User-Agent": "Jarvis"})
            with urllib.request.urlopen(req, timeout=40) as r:
                reponse_ = json.loads(r.read().decode("utf-8", "replace") or "{}")
            if reponse_.get("ok"):
                return True
            print("(Rapports : envoi refusé :", reponse_.get("raison"), ")")
            return False
        except Exception as e:
            if essai < ESSAIS - 1:
                time.sleep(20 * (essai + 1))
            else:
                print("(Rapports : envoi abandonné après", ESSAIS, "essais :", type(e).__name__, ")")
    return False


def _signal():
    if not valeur("compteur", True) or _invite():
        return False
    return _envoyer({"genre": "signal", "id": valeur("id"), "version": _version_jarvis(), "windows": _windows(),
                     "niveau": niveau() + (" + testeur" if valeur("testeur") else "")})


def envoyer_rapport(force=False):
    """Envoie le rapport technique (ou complet) s'il y a quelque chose de nouveau."""
    if niveau() == "aucun" or _invite():
        return False
    with _verrou:
        if not force and time.time() - valeur("dernier_rapport", 0) < INTERVALLE_RAPPORT:
            return False
        rapport, n = construire_rapport()
    if not n and not force:
        return False
    ok = _envoyer(rapport)
    with _verrou:
        regler("dernier_rapport", time.time())          # même en cas d'échec : on ne réessaie pas en boucle
        if ok:
            _vider_journal()
            print(f"(Rapports : rapport envoyé, {n} événements.)")
        elif os.path.exists(JOURNAL) and os.path.getsize(JOURNAL) > 2_000_000:
            _vider_journal()                            # rien ne s'accumule sur le PC
    return ok


def envoyer_message(genre, texte, joindre_journal=False):
    """« probleme » (Signaler un problème), « idee » (Proposer une amélioration) ou « questionnaire ».
    Envoyé seulement quand l'utilisateur appuie sur Envoyer ; renvoie True si c'est parti."""
    d = {"genre": genre, "id": valeur("id"), "version": _version_jarvis(), "windows": _windows(),
         "niveau": niveau()}
    if isinstance(texte, dict):
        d["reponses"] = {k: anonymiser(v, 1000) for k, v in texte.items()}
    else:
        d["texte"] = anonymiser(texte, 2000)
    if joindre_journal:
        d["journal"], _ = construire_rapport()          # (les conversations n'y sont qu'en rapport complet)
        d["dernieres_lignes"] = _dernieres_lignes_log()
    ok = _envoyer(d)
    if ok and genre == "questionnaire":
        regler("questionnaire", "fait")
    return ok


def _dernieres_lignes_log(n=80):
    """Les dernières lignes du journal de Jarvis, nettoyées (pour « Signaler un problème »)."""
    try:
        with open(jarvis_config.chemin("jarvis.log"), encoding="utf-8", errors="replace") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 40_000))
            lignes = f.read().splitlines()[-n:]
    except OSError:
        return []
    garder = []
    for l in lignes:
        if re.match(r"^(Entendu|Demande|Demande écrite|Claude|JARVIS|Whisper)\b", l) and niveau() != "complet":
            l = l.split(":")[0] + " : [texte non joint]"
        garder.append(anonymiser(l, 240))
    return garder


def effacer_mes_donnees():
    """Supprime sur le dépôt tout ce qui vient de ce PC, vide le journal local et tire un nouveau numéro."""
    ok = _envoyer({"genre": "effacer", "id": valeur("id")})
    _vider_journal()
    if ok:
        regler("id", secrets.token_hex(16))
    return ok


def _boucle():
    time.sleep(45)                                   # Jarvis finit de démarrer tranquillement
    _signal()
    prochain_signal = time.time() + INTERVALLE_SIGNAL
    while True:
        try:
            envoyer_rapport()
        except Exception as e:
            print("(Rapports :", type(e).__name__, ")")
        if time.time() >= prochain_signal:
            try:
                _signal()
            except Exception:
                pass
            prochain_signal = time.time() + INTERVALLE_SIGNAL
        time.sleep(300)


def demarrer():
    """Au démarrage de Jarvis : crochets d'erreurs, plantages précédents, envois en arrière-plan."""
    global _demarre
    if _demarre:
        return
    _demarre = True
    try:
        _lire()
        _crochets()
        _erreurs_du_journal_precedent()
    except Exception as e:
        print("(Rapports : démarrage :", e, ")")
    threading.Thread(target=_suivre_micro, daemon=True, name="rapports-micro").start()
    threading.Thread(target=_boucle, daemon=True, name="rapports").start()
