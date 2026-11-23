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
DELAI_NOUVEL_ESSAI = 6 * 3600       # un envoi qui a échoué (pas de réseau...) est retenté 6 h plus tard, pas le lendemain
# Combien d'événements récents on garde par sorte : une sorte très bavarde (faux réveils, réponses) ne chasse plus les autres
PLAFONDS = {"reponse": 1200, "conversation": 300, "demande_claude": 200, "faux_reveil": 200, "incompris": 200,
            "erreur": 300, "refaite": 100, "annulation": 100, "atelier": 100, "appareil_non_gere": 100}
PLAFOND_DEFAUT = 200

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


def a_encourager_complet():
    """Vrai s'il faut glisser, dans la fenetre de discussion, l'invitation a choisir le rapport « Complet » :
    pour tous ceux qui n'ont pas choisi « Complet » (« Technique » ou « Rien »), jamais en mode enfant ou invite."""
    try:
        if niveau() == "complet" or _invite():
            return False
        import jarvis_enfant
        return not jarvis_enfant.actif()
    except Exception:
        return False


_version_notee = []


def _version_en_cours():
    """La version de Jarvis qui tourne (lue une seule fois : Jarvis redémarre après une mise à jour)."""
    if not _version_notee:
        try:
            _version_notee.append(_version_jarvis())
        except Exception:
            return "?"
    return _version_notee[0]


def noter(genre, **infos):
    """Ajoute un événement au journal local, seulement si l'utilisateur a accepté les rapports."""
    if niveau() == "aucun" or _invite():
        return
    if genre == "conversation" and niveau() != "complet":
        return
    infos["genre"] = genre
    infos["t"] = round(time.time())
    if "version" not in infos:
        infos["version"] = _version_en_cours()
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


def _lire_journal(ignores=None):
    """Les événements en attente, dans l'ordre. Pour chaque sorte, seuls les plus récents sont gardés (PLAFONDS) ;
    ce qui est écarté est compté dans « ignores » (un dictionnaire, si on en passe un)."""
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
    restants = collections.Counter(e.get("genre") for e in evenements)
    gardes = []
    for e in evenements:
        genre = e.get("genre")
        if restants[genre] > PLAFONDS.get(genre, PLAFOND_DEFAUT):
            restants[genre] -= 1
            if ignores is not None:
                ignores[genre] = ignores.get(genre, 0) + 1
            continue
        gardes.append(e)
    return gardes[-MAX_EVENEMENTS:]


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
    deja = collections.Counter(                         # plantages déjà notés sur le moment (crochets d'erreurs)
        (e.get("type"), tuple(e.get("ou") or [])) for e in _lire_journal()
        if e.get("genre") == "erreur" and (e.get("source") == "plantage" or str(e.get("source", "")).startswith("fil ")))
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
            cle = (type_, tuple(ou[-3:]))
            if deja[cle] > 0:
                deja[cle] -= 1                          # déjà noté au moment du plantage : pas deux fois
            else:
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
    for arret in arrets_inattendus(session)[:5]:
        noter("erreur", source="arrêt inattendu", type=arret["code"], message=arret["explication"], ou=arret["avant"])


# Codes de sortie de Windows qu'on rencontre quand un programme s'arrête brutalement
_CODES_ARRET = {
    "1": "erreur Python non rattrapée",
    "3221225477": "accès mémoire interdit (0xC0000005), souvent un module audio, graphique ou de reconnaissance",
    "3221226505": "arrêt d'urgence du programme (0xC0000409)",
    "3221225725": "pile dépassée (0xC00000FD)",
    "3221225786": "fenêtre fermée ou Ctrl+C (0xC000013A)",
    "3221225794": "un composant n'a pas pu se charger (0xC0000142)",
    "3221225781": "une bibliothèque manque (0xC0000135)",
    "3221226356": "mémoire saturée (0xC0000374)",
    "3221225495": "plus assez de mémoire (0xC0000017)",
}
# Lignes du journal qui contiennent ce que la personne a dit ou ce que Jarvis a répondu : jamais dans ce relevé
_LIGNE_PERSONNELLE = re.compile(r"^\s*(?:Entendu|Demande|JARVIS\s*:|Whisper\s*:|Vosk|Commande instantanée|Tablette, réponse"
                                r"|Tablette, demande|Claude\s*:|Note|Rappel|Mail|Agenda\s*:)", re.I)


def arrets_inattendus(lignes):
    """Dans les lignes d'une session du journal : chaque arrêt inattendu noté par le gardien, avec son code de sortie,
    ce qu'il veut dire, et les 8 dernières lignes techniques qui le précèdent (nettoyées ; jamais ce qui a été dit)."""
    arrets = []
    for i, ligne in enumerate(lignes):
        m = re.search(r"s'est arrêté tout seul \(code (-?\d+)\) après (\d+) s", ligne)
        if not m:
            continue
        code = m.group(1)
        if code.startswith("-"):                       # certains Windows donnent le code en négatif
            code = str(int(code) + 2 ** 32)
        avant = []
        for precedente in reversed(lignes[max(0, i - 60):i]):
            precedente = precedente.strip()
            if not precedente or precedente.startswith("[gardien") or _LIGNE_PERSONNELLE.match(precedente):
                continue
            avant.append(anonymiser(precedente, 120))
            if len(avant) == 8:
                break
        arrets.append({"code": code, "apres_s": int(m.group(2)),
                       "explication": _CODES_ARRET.get(code, "code inconnu") + f", après {m.group(2)} s de marche",
                       "avant": list(reversed(avant))})
    return arrets


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
    try:                                            # cœurs et fils de calcul (pour comprendre les lenteurs)
        m["fils_de_calcul"] = os.cpu_count()
        import psutil
        m["coeurs"] = psutil.cpu_count(logical=False)
    except Exception:
        pass
    try:
        cartes = _cartes_graphiques()
        if cartes:
            m["cartes_graphiques"] = cartes
    except Exception:
        pass
    try:                                            # le disque où Jarvis est installé : taille et place libre
        import shutil
        disque = shutil.disk_usage(os.path.splitdrive(jarvis_config.chemin("x"))[0] + os.sep)
        m["disque_go"], m["disque_libre_go"] = round(disque.total / 2 ** 30), round(disque.free / 2 ** 30)
    except Exception:
        pass
    try:                                            # l'écran tel que Jarvis le voit : taille, échelle de Windows, nombre d'écrans
        import ctypes
        u = ctypes.windll.user32
        ecran = {"largeur": u.GetSystemMetrics(0), "hauteur": u.GetSystemMetrics(1), "ecrans": u.GetSystemMetrics(80)}
        try:
            ecran["echelle_pct"] = round(u.GetDpiForSystem() * 100 / 96)
        except Exception:
            pass
        m["ecran"] = ecran
    except Exception:
        pass
    try:                                            # portable (il a une batterie) ou PC fixe
        import ctypes

        class Alimentation(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                        ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        etat = Alimentation()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(etat)) and etat.BatteryFlag != 255:
            m["portable"] = not (etat.BatteryFlag & 128)        # 128 : pas de batterie
    except Exception:
        pass
    return m


def _cartes_graphiques():
    """[{"nom": ..., "memoire_go": ...}] des cartes graphiques, lues dans le registre de Windows (sans rien lancer).
    Les écrans virtuels (bureau à distance, affichage de base) ne comptent pas."""
    import winreg
    classe = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
    cartes = []
    for i in range(10):
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, classe + "\\%04d" % i) as k:
                nom = " ".join(str(winreg.QueryValueEx(k, "DriverDesc")[0]).split())[:80]
                memoire = None
                for valeur_nom in ("HardwareInformation.qwMemorySize", "HardwareInformation.MemorySize"):
                    try:
                        brut = winreg.QueryValueEx(k, valeur_nom)[0]
                        octets = int.from_bytes(brut, "little") if isinstance(brut, bytes) else int(brut)
                        if octets > 0:
                            memoire = round(octets / 2 ** 30, 1)
                            break
                    except (OSError, ValueError, TypeError):
                        continue
        except OSError:
            continue
        if not nom or re.search(r"basic display|remote|virtual|mirror|indirect|parsec|citrix|vnc", nom, re.I):
            continue
        if nom not in [c["nom"] for c in cartes]:
            cartes.append({"nom": nom, "memoire_go": memoire} if memoire else {"nom": nom})
    return cartes


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


def _claude_installe():
    """Claude est-il installé ? Le même test que Jarvis (~\\.local\\bin\\claude.exe) : seul ce Claude-là lui sert."""
    try:
        import jarvis_claude_reglages
        return bool(jarvis_claude_reglages.installe())
    except Exception:
        return os.path.exists(os.path.expanduser(r"~\.local\bin\claude.exe"))


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
            "claude": _claude_installe(), "profils": _compte_json("profils.json"), "voix_apprises": voix,
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


def _grouper_erreurs(liste, maximum=40):
    """Les erreurs identiques (même source, type, message, endroit, version) sont regroupées avec un compteur :
    une même erreur répétée 40 fois ne cache plus les autres, et le rapport reste léger."""
    groupes = {}
    for e in liste:
        cle = tuple(json.dumps(e.get(k), ensure_ascii=False, sort_keys=True)
                    for k in ("source", "type", "message", "ou", "version"))
        g = groupes.get(cle)
        if g is None:
            g = groupes[cle] = {k: e.get(k) for k in ("source", "type", "message", "ou", "version")}
            g["nombre"] = 0
        g["nombre"] += 1
        g["derniere_fois"] = e.get("t")
    return list(groupes.values())[-maximum:]


def _erreurs_a_plat(groupes, maximum=40):
    """Les erreurs au format que lit le dépôt Google (une ligne par erreur, 40 au plus : son résumé du lundi les
    compte une à une). On prend tour à tour une erreur de chaque sorte : une erreur répétée ne cache plus les autres.
    Les compteurs exacts sont dans « erreurs_groupees »."""
    restes = [dict(g) for g in groupes]
    plat = []
    while len(plat) < maximum and any(g["nombre"] > 0 for g in restes):
        for g in restes:
            if g["nombre"] > 0 and len(plat) < maximum:
                plat.append({k: g.get(k) for k in ("source", "type", "message", "ou")})
                g["nombre"] -= 1
    return plat


def construire_rapport():
    ignores = {}
    ev = _lire_journal(ignores)
    par_genre = collections.defaultdict(list)
    for e in ev:
        par_genre[e.get("genre")].append(e)
    reponses = par_genre["reponse"]
    local = [e["duree_s"] for e in reponses if e.get("par") == "local"]
    claude = [e["duree_s"] for e in reponses if e.get("par") == "claude"]
    lents = sorted(reponses, key=lambda e: -e.get("duree_s", 0))[:10]
    groupes_erreurs = _grouper_erreurs(par_genre["erreur"])
    rapport = {
        "genre": "rapport", "id": valeur("id"), "niveau": niveau(), "testeur": valeur("testeur"),
        "version": _version_jarvis(), "windows": _windows(),
        "periode": {"debut": min((e["t"] for e in ev), default=None), "fin": max((e["t"] for e in ev), default=None)},
        "materiel": _materiel(), "reglages": _reglages(), "appareils": _appareils(), "micro": _micro(),
        "statistiques": {"demandes": len(reponses), "locales": len(local), "claude": len(claude),
                         "en_erreur": sum(1 for e in reponses if e.get("erreur")),
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
        "erreurs": _erreurs_a_plat(groupes_erreurs),
        "erreurs_groupees": groupes_erreurs,
        "ateliers": [{k: e.get(k) for k in ("nom", "fin", "questions", "etoiles")} for e in par_genre["atelier"][-60:]],
        # appareils demandés que Jarvis ne pilote pas encore : leur type et le nombre de demandes, rien d'autre
        "appareils_non_geres": dict(collections.Counter(str(e.get("quoi")) for e in par_genre["appareil_non_gere"])),
    }
    rapport["versions"] = dict(collections.Counter(e.get("version") for e in ev if e.get("version")))
    if ignores:
        rapport["evenements_ignores"] = ignores           # trop nombreux : seuls les plus récents de leur sorte sont là
    if niveau() == "complet":
        rapport["conversations"] = [{k: e.get(k) for k in ("t", "demande", "reponse")}
                                    for e in par_genre["conversation"][-150:]]
    return rapport, len(ev)


_dernier_envoi = {"refus": False}       # le dépôt a-t-il répondu « non » (et pas seulement : pas de réseau) ?


def _envoyer(donnees):
    """Envoie au dépôt. Trois essais espacés, puis abandon. Renvoie True si c'est parti."""
    corps = json.dumps(donnees, ensure_ascii=False).encode("utf-8")
    _dernier_envoi["refus"] = False
    for essai in range(ESSAIS):
        try:
            req = urllib.request.Request(DEPOT, data=corps, headers={"Content-Type": "application/json",
                                                                     "User-Agent": "Jarvis"})
            with urllib.request.urlopen(req, timeout=40) as r:
                reponse_ = json.loads(r.read().decode("utf-8", "replace") or "{}")
            if reponse_.get("ok"):
                return True
            print("(Rapports : envoi refusé :", reponse_.get("raison"), ")")
            _dernier_envoi["refus"] = True
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
    signal = {"genre": "signal", "id": valeur("id"), "version": _version_jarvis(), "windows": _windows(),
              "niveau": niveau() + (" + testeur" if valeur("testeur") else "")}
    try:                                   # le type de matériel seulement : rien qui dise qui est la personne
        signal["materiel"] = materiel_du_compteur()
    except Exception:
        pass
    nom = str(valeur("etiquette") or "").strip()
    if nom:                                # un nom que l'utilisateur a donné lui-même à ce PC (« nomme ce PC … »)
        signal["nom"] = nom[:40]
    return _envoyer(signal)


def materiel_du_compteur():
    """Ce que le compteur anonyme dit du PC : processeur, cœurs, mémoire, carte graphique, portable ou fixe.
    Ni le nom du micro, ni le disque, ni aucun réglage : ceux-là restent réservés au rapport technique."""
    m = _materiel()
    resume = {cle: m[cle] for cle in ("processeur", "coeurs", "fils_de_calcul", "memoire_go", "portable") if cle in m}
    cartes = [c.get("nom") + (f" ({c['memoire_go']} Go)" if c.get("memoire_go") else "")
              for c in m.get("cartes_graphiques", []) if c.get("nom")]
    if cartes:
        resume["carte_graphique"] = " + ".join(cartes)[:120]
    return resume


_NOMMER = re.compile(r"^\W*(?:jarvis\W+)?(?:nomme|appelle|baptise)\s+ce\s+(?:pc|p\.c\.|ordinateur|ordi)\W+(.{2,60}?)\W*$", re.I)
_OUBLIER_NOM = re.compile(r"^\W*(?:jarvis\W+)?(?:oublie|efface|retire|enl[eè]ve|supprime)\s+le\s+nom\s+de\s+ce\s+"
                          r"(?:pc|ordinateur|ordi)\W*$", re.I)


def commande_nom_pc(brut):
    """« Nomme ce PC PC du salon » : un nom choisi par l'utilisateur, envoyé avec le compteur anonyme pour que le
    créateur de Jarvis reconnaisse ce PC (utile pour ses propres PC d'essai). « Oublie le nom de ce PC » l'enlève."""
    brut = (brut or "").replace("’", "'").strip()
    if _OUBLIER_NOM.match(brut):
        regler("etiquette", "")
        threading.Thread(target=_signal, daemon=True).start()
        return "C'est fait : ce PC n'a plus de nom dans mes rapports."
    m = _NOMMER.match(brut)
    if not m:
        return None
    nom = " ".join(m.group(1).split()).strip(" .!?«»\"'")[:40]
    if len(nom) < 2:
        return None
    if _invite():
        return "En mode invité, je ne change pas ce réglage."
    regler("etiquette", nom)
    threading.Thread(target=_signal, daemon=True).start()
    return (f"C'est noté : ce PC s'appelle « {nom} » dans mes rapports. Ce nom est envoyé avec le compteur anonyme. "
            "Pour l'enlever, dis : oublie le nom de ce PC.")


def envoyer_rapport(force=False):
    """Envoie le rapport technique (ou complet) s'il y a quelque chose de nouveau."""
    if niveau() == "aucun" or _invite():
        return False
    with _verrou:
        if not force and time.time() - valeur("dernier_rapport", 0) < INTERVALLE_RAPPORT:
            return False
        octets = os.path.getsize(JOURNAL) if os.path.exists(JOURNAL) else 0
        rapport, n = construire_rapport()
    if not n and not force:
        return False
    ok = _envoyer(rapport)
    with _verrou:
        if ok:
            regler("dernier_rapport", time.time())
            _retirer_envoyes(octets)                    # ce qui a été noté pendant l'envoi reste pour le prochain
            print(f"(Rapports : rapport envoyé, {n} événements.)")
        else:                                           # on réessaiera dans quelques heures, pas en boucle
            delai = INTERVALLE_RAPPORT if _dernier_envoi["refus"] else DELAI_NOUVEL_ESSAI
            regler("dernier_rapport", time.time() - INTERVALLE_RAPPORT + delai)
            if os.path.exists(JOURNAL) and os.path.getsize(JOURNAL) > 2_000_000:
                _vider_journal()                        # rien ne s'accumule sur le PC
    return ok


def _retirer_envoyes(octets):
    """Retire du journal les « octets » premiers octets (ce qui vient d'être envoyé), pas ce qui a été noté depuis."""
    with _verrou:
        try:
            with open(JOURNAL, "rb") as f:
                f.seek(octets)
                reste = f.read()
            if not reste.strip():
                _vider_journal()
                return
            provisoire = JOURNAL + ".tmp"
            with open(provisoire, "wb") as f:
                f.write(reste)
            os.replace(provisoire, JOURNAL)
        except OSError:
            pass


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
        if niveau() != "complet":
            perso = _LIGNE_PERSONNELLE.match(l)
            if perso:                                   # on ne garde que le début de la ligne, jamais la suite
                l = perso.group(0).strip().rstrip(":").strip() + " : [texte non joint]"
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
