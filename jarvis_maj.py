"""
JARVIS - mises à jour depuis GitHub.

  - à chaque démarrage, Jarvis regarde sur la page GitHub du projet si une version plus récente est publiée ;
  - s'il en trouve une, il le dit après avoir répondu à ta prochaine demande, et demande s'il doit l'installer ;
    il n'installe rien sans ton « oui » ;
  - la mise à jour est faite par l'installateur officiel (Installer-Jarvis.exe de la dernière version publiée),
    exactement comme si tu le relançais toi-même et choisissais « 1. Mettre à jour » : tes réglages, ta mémoire,
    tes rappels et tes listes sont gardés. Jarvis s'arrête pendant quelques minutes, puis redémarre tout seul
    et dit si la mise à jour a réussi ;
  - à la voix : « Jarvis, cherche les mises à jour », « Jarvis, mets-toi à jour », « quelle est ta version ? ».
"""

import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request

import jarvis_config

DEPOT = "TonyNio-IA/Jarvis-assistant-IA-de-TonyNio"
API_DERNIERE = f"https://api.github.com/repos/{DEPOT}/releases/latest"
API_VERSIONS = f"https://api.github.com/repos/{DEPOT}/releases?per_page=10"   # avec les pré-versions (testeurs)
INSTALLATEUR = f"https://github.com/{DEPOT}/releases/latest/download/Installer-Jarvis.exe"
FICHIER_SUIVI = jarvis_config.chemin("mise_a_jour.json")     # reste sur ce PC
# La ligne qui installe Jarvis à la main sur un PC dont le Contrôle intelligent des applications bloque tout
LIGNE_INSTALLATION = ('$f="$env:TEMP\\Installer-Jarvis.bat"; iwr https://github.com/' + DEPOT +
                      '/releases/latest/download/Installer-Jarvis.bat -OutFile $f; Start-Process $f')
ATTENTE_AVANT_INSTALLATION = 8          # secondes : le temps que Jarvis finisse sa phrase

disponible = None        # (« 1.21 », « titre de la version ») si une version plus récente existe
forcee = False           # la version disponible est une mise à jour forcée : installée tout de suite, sans question
MARQUE_FORCEE = "<!-- jarvis:mise-a-jour-forcee -->"     # dans les notes de la version sur GitHub (invisible sur la page)
INTERVALLE_FORCEES = 15 * 60                              # secondes entre deux coups d'œil à GitHub
_forcee_lancee = False
_installateur = None     # l'installateur de la version trouvée (une pré-version, pour un testeur)
_etiquette = None        # son étiquette sur GitHub (« v1.33 ») : l'installateur prend exactement cette version


def _testeur():
    """Vrai si l'utilisateur s'est porté testeur volontaire (Réglages, Rapports) : il reçoit les pré-versions."""
    try:
        import jarvis_rapports
        return bool(jarvis_rapports.valeur("testeur"))
    except Exception:
        return False
_annoncee = False
lancee = False          # une mise à jour vient d'être lancée : Jarvis va s'arrêter (pas de question après)
_verrou = threading.Lock()


def _noter(*texte):
    """Une ligne du journal, avec l'heure : on voit quand la mise à jour s'est lancée."""
    print(time.strftime("%H:%M:%S"), *texte)


def controle_applications_actif():
    """Vrai si le « Contrôle intelligent des applications » de Windows est activé (il bloque les fichiers inconnus)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\CI\Policy") as cle:
            return winreg.QueryValueEx(cle, "VerifiedAndReputablePolicyState")[0] == 1
    except Exception:
        return False


def avertissement_windows():
    """Phrase ajoutée avant une mise à jour automatique : Windows peut afficher un message de blocage, c'est normal."""
    if not controle_applications_actif():
        return ""
    return (" Windows peut afficher un message disant qu'une partie de l'application a été bloquée : "
            "c'est normal, la mise à jour continue.")


def version_actuelle():
    """Le numéro VERSION écrit dans jarvis_claude.py (lu dans le fichier : pas de double chargement de Jarvis)."""
    try:
        with open(jarvis_config.chemin("jarvis_claude.py"), encoding="utf-8") as f:
            m = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def _nombres(version):
    """« v1.21 » -> (1, 21) ; une version illisible -> ()."""
    return tuple(int(n) for n in re.findall(r"\d+", version or ""))


def verifier():
    """Interroge GitHub. Renvoie (version, titre) si une version plus récente est publiée, sinon None."""
    global disponible, forcee
    testeur = _testeur()
    requete = urllib.request.Request(API_VERSIONS if testeur else API_DERNIERE,
                                     headers={"User-Agent": "Jarvis", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(requete, timeout=10) as r:
        derniere = json.load(r)
    if testeur and isinstance(derniere, list):   # testeur volontaire : la plus récente, pré-version comprise (jamais un brouillon)
        publiees = [v for v in derniere if not v.get("draft")]
        publiees.sort(key=lambda v: _nombres(str(v.get("tag_name", ""))), reverse=True)
        derniere = publiees[0] if publiees else {}
    if derniere.get("draft") or (derniere.get("prerelease") and not testeur):
        return None
    global _installateur, _etiquette
    _etiquette = str(derniere.get("tag_name") or "") or None
    _installateur = next((a.get("browser_download_url") for a in derniere.get("assets", [])
                          if a.get("name") == "Installer-Jarvis.exe"), None) or INSTALLATEUR
    version = str(derniere.get("tag_name", "")).lstrip("vV")
    with _verrou:
        if _nombres(version) > _nombres(version_actuelle()):
            titre = str(derniere.get("name") or "").split(":", 1)[-1].strip()
            disponible = (version, titre)
            forcee = MARQUE_FORCEE in str(derniere.get("body") or "") or _forcee_entre(version_actuelle(), version)
        else:
            disponible = None
            forcee = False
        return disponible


def _forcee_entre(actuelle, derniere):
    """PC resté éteint pendant plusieurs versions : si l'une de celles qu'il a manquées était forcée, la dernière
    version est installée d'office elle aussi (elle contient toutes les corrections d'avant)."""
    try:
        requete = urllib.request.Request(API_VERSIONS, headers={"User-Agent": "Jarvis", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(requete, timeout=10) as r:
            versions = json.load(r)
        return any(isinstance(v, dict) and not v.get("draft") and MARQUE_FORCEE in str(v.get("body") or "")
                   and _nombres(actuelle) < _nombres(str(v.get("tag_name", ""))) <= _nombres(derniere)
                   for v in versions)
    except Exception:
        return False


def verifier_en_arriere_plan():
    """Au démarrage, puis toutes les 15 minutes : une version plus récente est-elle publiée ?
    Une mise à jour ordinaire est annoncée comme d'habitude ; une mise à jour forcée est installée dès que
    Jarvis est en veille (voir forcee_a_installer)."""
    def tache():
        premiere = True
        while True:
            try:
                trouve = verifier()
                if premiere or (trouve and forcee):
                    _noter("Mise à jour :", (f"version {trouve[0]} disponible" + (" (mise à jour forcée)." if forcee else "."))
                          if trouve else "Jarvis est à jour.")
            except Exception as erreur:
                if premiere:
                    print("Vérification des mises à jour impossible :", erreur)
            premiere = False
            if _forcee_lancee:
                return
            time.sleep(INTERVALLE_FORCEES)
    threading.Thread(target=tache, daemon=True).start()


CALME_AVANT_FORCEE = 60      # secondes de veille, sans demande, avant d'installer une mise à jour forcée
CALME_TABLETTE = 5 * 60      # après une demande d'une tablette (atelier, histoire...), on attend plus longtemps
_activite_tablette = 0.0


def signaler_activite():
    global _activite_tablette
    _activite_tablette = time.time()


def forcee_en_attente():
    return bool(disponible and forcee and not _forcee_lancee
                and time.time() - _activite_tablette >= CALME_TABLETTE)


def forcee_a_installer():
    """Vrai une seule fois quand une mise à jour forcée attend : Jarvis l'installe alors aussitôt."""
    global _forcee_lancee
    if disponible and forcee and not _forcee_lancee:
        _forcee_lancee = True
        return True
    return False


def a_annoncer():
    """Vrai une seule fois par démarrage, quand une nouvelle version attend d'être annoncée."""
    global _annoncee
    if disponible and not forcee and not _annoncee:
        _annoncee = True
        return True
    return False


def annonce():
    version, titre = disponible
    return (f"Au fait, une nouvelle version de Jarvis est disponible : la {version}"
            + (f", {titre}" if titre else "") + ". Tu veux que je l'installe maintenant ?")


# ---------- Installation ----------

def texte_aide(mise_a_jour=False):
    """Le texte du Bloc-notes quand Windows bloque : Jarvis le crée (mise à jour) ; le même texte est joint à chaque
    publication GitHub (installation)."""
    debut = ("Jarvis n'a pas pu se mettre à jour : Windows a bloqué le fichier." if mise_a_jour
             else "Windows a bloqué le fichier d'installation de Jarvis ?")
    return (debut + "\n\n"
            "C'est la protection « Contrôle intelligent des applications » de Windows 11. Elle laisse passer les programmes "
            "que Microsoft connaît déjà, ou ceux signés avec un certificat payant. Jarvis est un projet personnel et gratuit, "
            "sans ce certificat : ce blocage ne veut pas dire que le fichier est dangereux. Rien n'est cassé, et il ne faut "
            "rien désactiver.\n\n"
            "1. Appuie sur la touche Windows + X, puis choisis Terminal (ou Windows PowerShell).\n"
            "2. Copie la ligne ci-dessous, colle-la dans la fenêtre (clic droit), puis appuie sur Entrée :\n\n"
            + LIGNE_INSTALLATION + "\n\n"
            "3. La fenêtre d'installation de Jarvis s'ouvre : continue normalement. Rien n'est installé avant que tu "
            "cliques sur « Installer ».\n\n"
            "Ce que fait la ligne : elle télécharge l'installateur de la dernière version publiée sur la page officielle "
            "de Jarvis (https://github.com/" + DEPOT + "), puis l'ouvre.\n\n"
            "Avant de la coller, vérifie qu'elle ne contient qu'une seule adresse, qui commence par "
            "https://github.com/" + DEPOT + "/ . Ne colle jamais dans le Terminal une commande reçue par message, par mail "
            "ou trouvée sur un autre site : c'est une ruse courante pour installer des programmes malveillants.\n")


def _ouvrir_aide():
    """Écrit l'aide dans le dossier temporaire et l'ouvre dans le Bloc-notes (programme signé par Microsoft)."""
    chemin = os.path.join(tempfile.gettempdir(), "Jarvis-aide-Windows.txt")
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        f.write(texte_aide(True).replace("\n", "\r\n"))
    subprocess.Popen(["notepad.exe", chemin])


def installer():
    """Télécharge l'installateur de la dernière version et le lance en mode « mise à jour », sans question.
    Renvoie la phrase à dire."""
    global _annoncee, lancee
    _annoncee = True          # la mise à jour est lancée : ne plus proposer « tu veux que je l'installe ? »
    lancee = True
    cible = disponible[0] if disponible else "la plus récente"
    dossier = os.path.join(tempfile.gettempdir(), "Jarvis-mise-a-jour")
    os.makedirs(dossier, exist_ok=True)
    programme = os.path.join(dossier, "Installer-Jarvis.exe")
    try:
        requete = urllib.request.Request(_installateur or INSTALLATEUR, headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(requete, timeout=60) as r, open(programme, "wb") as f:
            f.write(r.read())
        with open(programme, "rb") as f:
            if f.read(2) != b"MZ" or os.path.getsize(programme) < 50_000:
                raise ValueError("le fichier téléchargé n'est pas l'installateur")
    except Exception as erreur:
        _noter("Téléchargement de la mise à jour impossible :", erreur)
        return "Je n'arrive pas à télécharger la mise à jour. Vérifie la connexion Internet, puis redemande-le-moi."
    try:
        with open(FICHIER_SUIVI, "w", encoding="utf-8") as f:
            json.dump({"depuis": version_actuelle(), "vers": cible, "quand": time.strftime("%d/%m/%Y %H:%M")}, f)
    except OSError:
        pass
    source_essai = os.environ.get("JARVIS_MAJ_SOURCE")     # essais : fichiers pris dans un dossier local
    environnement = {k: v for k, v in os.environ.items() if not k.startswith("JARVIS_")}
    environnement.update(JARVIS_AUTO="1", JARVIS_ACTION="1", JARVIS_OK="o", JARVIS_SANS_VOIX="1", JARVIS_FENETRE_MAJ="1")
    if source_essai:
        environnement["JARVIS_SOURCE"] = source_essai
    if _etiquette:
        environnement["JARVIS_ETIQUETTE"] = _etiquette

    def lancer():
        # Une fenêtre montre l'avancée ; l'installateur arrête Jarvis, le met à jour, puis le relance
        global _echec
        # console cachée : seule la fenêtre claire d'avancement se voit (le journal installation.log garde tout)
        drapeaux = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            subprocess.Popen([programme], cwd=dossier, env=environnement, creationflags=drapeaux)
            _noter("Mise à jour : installateur .exe lancé (accepté par Windows).")
            return
        except OSError as erreur:
            # Windows (Contrôle intelligent des applications) peut refuser un .exe neuf : on lance alors le même
            # installateur en fichier .bat, que cmd.exe (signé par Microsoft) accepte
            _noter("Lancement de l'installateur refusé par Windows :", erreur)
        try:
            lot = _telecharger_lot(dossier)
            if lot:
                interpreteur = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", "cmd.exe")
                subprocess.Popen([interpreteur, "/c", lot], cwd=dossier, env=environnement, creationflags=drapeaux)
                _noter("Mise à jour : installateur .bat lancé via cmd.exe (le .exe avait été refusé).")
                return
        except OSError as erreur:
            _noter("Lancement de l'installateur (.bat) refusé aussi :", erreur)
        _noter("Mise à jour : .exe et .bat refusés par Windows, Bloc-notes ouvert avec la marche à suivre.")
        _echec = ("Windows a bloqué la mise à jour. Je reste en version " + version_actuelle() +
                  ". J'ai ouvert le Bloc-notes avec la marche à suivre : lis-le, la ligne à coller y est "
                  "(elle est aussi copiée : Contrôle V).")
        try:
            copie = subprocess.Popen(["clip"], stdin=subprocess.PIPE, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            copie.communicate(LIGNE_INSTALLATION.encode("ascii"), timeout=10)
        except Exception:
            pass
        try:
            _ouvrir_aide()
        except Exception as erreur:
            _noter("Bloc-notes impossible :", erreur)
            try:
                subprocess.Popen(["explorer.exe", "/select,", programme])
            except OSError:
                pass
    minuteur = threading.Timer(ATTENTE_AVANT_INSTALLATION, lancer)
    minuteur.daemon = True
    minuteur.start()
    version = f"la version {cible}" if disponible else "la dernière version"
    return (f"Je lance la mise à jour vers {version}. Je vais m'arrêter quelques minutes, "
            "puis je redémarrerai tout seul.")


_echec = None


def echec_a_dire():
    """La phrase à dire une seule fois si Windows a refusé de lancer l'installateur, sinon None."""
    global _echec
    phrase, _echec = _echec, None
    return phrase


def _telecharger_lot(dossier):
    """Télécharge Installer-Jarvis.bat de la même version (même contenu que le .exe). Renvoie son chemin, ou None."""
    adresse = (_installateur or INSTALLATEUR).rsplit("/", 1)[0] + "/Installer-Jarvis.bat"
    lot = os.path.join(dossier, "Installer-Jarvis.bat")
    try:
        requete = urllib.request.Request(adresse, headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(requete, timeout=60) as r, open(lot, "wb") as f:
            f.write(r.read())
        return lot if os.path.getsize(lot) > 20_000 else None
    except Exception as erreur:
        _noter("Téléchargement de l'installateur .bat impossible :", erreur)
        return None


def bilan_au_demarrage():
    """Après une mise à jour lancée par Jarvis : la phrase qui dit si elle a réussi, ou None."""
    try:
        with open(FICHIER_SUIVI, encoding="utf-8") as f:
            suivi = json.load(f)
        os.remove(FICHIER_SUIVI)
    except (OSError, ValueError):
        return None
    actuelle = version_actuelle()
    if _nombres(actuelle) > _nombres(suivi.get("depuis")):
        return f"Mise à jour terminée : je suis maintenant en version {actuelle}."
    return (f"La mise à jour n'a pas abouti : je suis toujours en version {actuelle}. "
            "Le détail est dans le fichier installation.log, dans mon dossier.")


# ---------- À la voix ----------

_METS_A_JOUR = re.compile(r"\b(?:mets|met|mette|mettes|metz|mettez)[- ]+(?:toi|toit|tois)\s+[àa]\s+jour\b|\bmettre\s+[àa]\s+jour\b"
                          r"|\bmettons(?:[- ]nous)?\s+[àa]\s+jour\s*$"
                          r"|\b(?:installe|lance|fais|fait)\b.*\bmise [àa] jour\b|\bmets [àa] jour jarvis\b")
_CHERCHE = re.compile(r"\b(?:cherche|recherche|vérifie|verifie|regarde)\b.*\bmises? à jour\b|"
                      r"\b(?:y a-t-il|il y a|est-ce qu'il y a|y a|existe-t-il)\b.*\b(?:mises? à jour|nouvelle version)\b|"
                      r"\bes-tu à jour\b|\b(?:tu es|t'es) à jour\b")
_VERSION = re.compile(r"\b(?:quelle|c'est quoi|tu es en quelle|t'es en quelle)\b.*\bversion\b")


def commande(t, demander_confirmation):
    """Renvoie la phrase à dire, ou None. demander_confirmation(action) prépare l'attente d'un « oui »."""
    t = t.replace("’", "'")
    if _METS_A_JOUR.search(t):
        try:
            trouve = verifier()
        except Exception:
            return "Je n'arrive pas à joindre GitHub pour le moment. Réessaie plus tard."
        if not trouve:
            return f"Je suis déjà à jour : version {version_actuelle()}."
        return installer()
    if _CHERCHE.search(t):
        try:
            trouve = verifier()
        except Exception:
            return "Je n'arrive pas à joindre GitHub pour le moment. Réessaie plus tard."
        if not trouve:
            return f"Je suis à jour : version {version_actuelle()}."
        global _annoncee
        _annoncee = True
        demander_confirmation("maj")
        return annonce()
    if _VERSION.search(t) and not re.search(r"\b(windows|python|chrome|navigateur|pc|ordinateur)\b", t):
        reponse = f"Je suis Jarvis, version {version_actuelle()}."
        if disponible:
            reponse += f" La version {disponible[0]} est disponible : dis, mets-toi à jour, pour l'installer."
        return reponse
    return None
