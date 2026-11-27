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
import shutil
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
INTERVALLE_FORCEES = 5 * 60                               # secondes entre deux coups d'œil à GitHub
ATTENTE_APRES_ECHEC = 60                                  # secondes avant de réessayer quand GitHub n'a pas répondu
ESSAIS_RAPPROCHES = 5                                     # essais rapprochés, puis retour au rythme habituel
_forcee_lancee = False
_forcee_lancee_le = 0.0  # quand le dernier essai d'installation forcée a été lancé
_forcee_essais = 0       # nombre d'essais depuis le démarrage de Jarvis
_telechargement_rate = False     # le dernier essai a échoué au téléchargement (Internet) : on réessaie vite
_bloquee_par_windows = False     # Windows a refusé l'installateur : inutile de réessayer tout seul
ESSAIS_FORCEE = 6                # essais au plus par démarrage de Jarvis
NOUVEL_ESSAI_TELECHARGEMENT = 5 * 60     # secondes avant de réessayer après un téléchargement raté
NOUVEL_ESSAI_INSTALLATION = 15 * 60      # installateur lancé mais Jarvis tourne toujours : il n'a pas abouti
DEMARRAGE = time.time()
DEMARRAGE_SANS_ATTENTE = 3 * 60          # au démarrage de Jarvis, une forcée s'installe sans attendre la veille
_empreintes = {}         # SHA-256 publiés dans les notes de la version : {"Installer-Jarvis.exe": "ABCD…"}
DOSSIER_PRECEDENT = jarvis_config.chemin("version_precedente")   # les programmes d'avant, gardés le temps d'une mise à jour
FICHIER_RETOUR = jarvis_config.chemin("retour_version.json")     # écrit par le gardien s'il a dû revenir en arrière
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
    global _empreintes
    _empreintes = lire_empreintes(str(derniere.get("body") or ""))
    with _verrou:
        if _nombres(version) > _nombres(version_actuelle()) and _nombres(version) != _nombres(version_refusee()):
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
    """Au démarrage, puis toutes les 5 minutes : une version plus récente est-elle publiée ?
    Une mise à jour ordinaire est annoncée comme d'habitude ; une mise à jour forcée est installée dès que
    Jarvis est en veille (voir forcee_a_installer)."""
    def tache():
        premiere = True
        echecs = 0           # Internet pas encore là au démarrage : on réessaie vite, puis au rythme habituel
        while True:
            try:
                trouve = verifier()
                if premiere or echecs or (trouve and forcee):
                    _noter("Mise à jour :", (f"version {trouve[0]} disponible" + (" (mise à jour forcée)." if forcee else "."))
                          if trouve else "Jarvis est à jour.")
                echecs = 0
            except Exception as erreur:
                if not echecs:
                    _noter("Vérification des mises à jour impossible pour l'instant (", type(erreur).__name__, erreur,
                           ") : nouvel essai dans une minute.")
                echecs += 1
            premiere = False
            time.sleep(ATTENTE_APRES_ECHEC if 0 < echecs <= ESSAIS_RAPPROCHES else INTERVALLE_FORCEES)
    threading.Thread(target=tache, daemon=True).start()


CALME_AVANT_FORCEE = 20      # secondes de veille, sans demande, avant d'installer une mise à jour forcée
CALME_TABLETTE = 5 * 60      # après une demande d'une tablette (atelier, histoire...), on attend plus longtemps
_activite_tablette = 0.0


def signaler_activite():
    global _activite_tablette
    _activite_tablette = time.time()


def calme_requis():
    """Secondes de veille exigées avant une mise à jour forcée : aucune juste après le démarrage de Jarvis."""
    return 0 if time.time() - DEMARRAGE < DEMARRAGE_SANS_ATTENTE else CALME_AVANT_FORCEE


def _rearmer_forcee():
    """Un essai d'installation forcée n'a pas abouti (téléchargement raté, ou installateur lancé mais Jarvis
    tourne toujours un quart d'heure plus tard) : on permet un nouvel essai, au lieu de rester bloqué."""
    global _forcee_lancee, lancee
    if not _forcee_lancee or _bloquee_par_windows or _forcee_essais >= ESSAIS_FORCEE:
        return
    attente = NOUVEL_ESSAI_TELECHARGEMENT if _telechargement_rate else NOUVEL_ESSAI_INSTALLATION
    if time.time() - _forcee_lancee_le >= attente:
        if not _telechargement_rate:          # (un téléchargement raté est déjà compté par installer())
            noter_echec("installation")        # lancé, mais Jarvis tourne toujours un quart d'heure plus tard
            try:
                os.remove(FICHIER_SUIVI)       # déjà compté : le bilan du prochain démarrage ne le recompte pas
            except OSError:
                pass
        _forcee_lancee = False
        lancee = False
        _noter("Mise à jour forcée : le dernier essai n'a pas abouti, nouvel essai (", _forcee_essais + 1, "sur",
               ESSAIS_FORCEE, ").")


def premier_essai_forcee():
    """Vrai au premier essai : Jarvis n'annonce la mise à jour à voix haute qu'une fois, pas à chaque nouvel essai."""
    return _forcee_essais <= 1


def forcee_en_attente():
    _rearmer_forcee()
    return bool(disponible and forcee and not _forcee_lancee
                and time.time() - _activite_tablette >= CALME_TABLETTE)


def forcee_a_installer():
    """Vrai une seule fois quand une mise à jour forcée attend : Jarvis l'installe alors aussitôt."""
    global _forcee_lancee, _forcee_lancee_le, _forcee_essais
    if disponible and forcee and not _forcee_lancee:
        _forcee_lancee = True
        _forcee_lancee_le = time.time()
        _forcee_essais += 1
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
    # Le titre de la version sur GitHub est parfois juste « Jarvis 1.50 » : le répéter après « la 1.50 » sonne faux
    if titre and re.fullmatch(r"(?i)\s*jarvis\s*v?[\d.]*\s*", titre):
        titre = ""
    return (f"Une nouvelle version de Jarvis est disponible : la {version}"
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


def _ouvrir_aide(texte=None):
    """Écrit l'aide dans le dossier temporaire et l'ouvre dans le Bloc-notes (programme signé par Microsoft)."""
    chemin = os.path.join(tempfile.gettempdir(), "Jarvis-aide-Windows.txt")
    with open(chemin, "w", encoding="utf-8-sig", newline="") as f:
        f.write((texte or texte_aide(True)).replace("\n", "\r\n"))
    subprocess.Popen(["notepad.exe", chemin])


# ---------- Mise à jour qui n'aboutit pas (Windows, antivirus) : au bout de 2 essais ratés, on explique ----------

FICHIER_ECHECS = jarvis_config.chemin("mise_a_jour_echecs.json")    # reste sur ce PC
ECHECS_AVANT_AIDE = 2


def texte_aide_blocage(genre="installation"):
    """La marche à suivre quand la mise à jour échoue plusieurs fois (Windows, antivirus, connexion)."""
    cause = ("Le téléchargement de la mise à jour a échoué deux fois. Souvent, c'est la connexion Internet, ou un "
             "antivirus qui supprime le fichier dès qu'il arrive." if genre == "telechargement" else
             "La mise à jour s'est lancée deux fois sans aller au bout. Souvent, c'est Windows ou un antivirus qui "
             "bloque le fichier d'installation de Jarvis.")
    return ("Jarvis n'arrive pas à se mettre à jour.\n\n" + cause + " Rien n'est cassé : Jarvis continue de marcher "
            "dans sa version actuelle. Voici comment débloquer, de la solution la plus simple à la plus complète.\n\n"
            "SOLUTION 1 (recommandée, elle marche sur tous les PC) : la ligne à coller dans le Terminal\n"
            "1. Appuie sur la touche Windows + X, puis choisis Terminal (ou Windows PowerShell).\n"
            "2. Copie la ligne ci-dessous, colle-la dans la fenêtre (clic droit), puis appuie sur Entrée :\n\n"
            + LIGNE_INSTALLATION + "\n\n"
            "3. La fenêtre d'installation de Jarvis s'ouvre : choisis « Mettre à jour ». Tes réglages, tes profils et "
            "tes rappels sont gardés.\n\n"
            "SOLUTION 2 : si Windows affiche « Windows a protégé votre ordinateur »\n"
            "Clique sur « Informations complémentaires », puis sur « Exécuter quand même ».\n\n"
            "SOLUTION 3 : si ton antivirus a mis Jarvis de côté\n"
            "- Avec la protection de Windows : ouvre « Sécurité Windows », puis « Protection contre les virus et menaces », "
            "puis « Historique de protection ». Si « Installer-Jarvis » y apparaît comme bloqué ou mis en quarantaine, "
            "choisis de l'autoriser ou de le restaurer.\n"
            "- Avec un autre antivirus (Avast, AVG, Norton, Bitdefender, Kaspersky, McAfee...) : ouvre-le et cherche "
            "la « quarantaine » ou l'« historique des menaces ». Si Installer-Jarvis ou un fichier de C:\\Jarvis y est, "
            "restaure-le et autorise-le.\n"
            "Puis refais la solution 1.\n\n"
            "Ce blocage ne veut pas dire que le fichier est dangereux : Jarvis est un projet personnel et gratuit, sans le "
            "certificat payant que Windows et les antivirus connaissent. Ne désactive pas ton antivirus, et ne colle "
            "jamais dans le Terminal une commande reçue par message, par mail ou trouvée sur un autre site : la ligne "
            "officielle ne contient qu'une adresse, qui commence par https://github.com/" + DEPOT + "/ .\n\n"
            "Si rien ne marche, signale-le : dans les réglages de Jarvis, onglet Rapports, « Signaler un problème ».\n")


def _lire_echecs():
    try:
        with open(FICHIER_ECHECS, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def noter_echec(genre, cible=None, ouvrir=True):
    """Un essai de mise à jour n'a pas abouti. Au 2e essai raté vers la même version, Jarvis explique comment
    débloquer (une seule fois par version) : phrase dite + Bloc-notes avec la marche à suivre + ligne copiée.
    Renvoie True si l'aide vient d'être montrée."""
    global _echec
    cible = cible or (disponible[0] if disponible else "?")
    d = _lire_echecs()
    if d.get("vers") != cible:
        d = {"vers": cible, "echecs": 0, "aide": False}
    d["echecs"] = int(d.get("echecs", 0)) + 1
    d["dernier"] = genre
    montrer = d["echecs"] >= ECHECS_AVANT_AIDE and not d.get("aide")
    if montrer:
        d["aide"] = True
    try:
        with open(FICHIER_ECHECS, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
    except OSError:
        pass
    _noter(f"Mise à jour vers {cible} : essai raté n° {d['echecs']} ({genre}).")
    if not montrer:
        return False
    _echec = ("Ma mise à jour n'arrive pas à s'installer : Windows ou ton antivirus la bloque sans doute. "
              "J'ai ouvert le Bloc-notes avec la marche à suivre pour la débloquer, et la ligne à coller est déjà "
              "copiée : Contrôle V.")
    if ouvrir:
        try:
            copie = subprocess.Popen(["clip"], stdin=subprocess.PIPE,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
            copie.communicate(LIGNE_INSTALLATION.encode("ascii"), timeout=10)
        except Exception:
            pass
        try:
            _ouvrir_aide(texte_aide_blocage(genre))
        except Exception as erreur:
            _noter("Bloc-notes impossible :", erreur)
    return True


def oublier_echecs():
    try:
        os.remove(FICHIER_ECHECS)
    except OSError:
        pass


def lire_empreintes(notes):
    """Les empreintes SHA-256 écrites dans les notes d'une version : {nom du fichier: empreinte en majuscules}."""
    return {nom: valeur.upper() for nom, valeur in
            re.findall(r"\|\s*(Installer-Jarvis\.(?:exe|bat))\s*\|\s*`?([0-9A-Fa-f]{64})`?\s*\|", notes or "")}


def _empreinte(chemin):
    import hashlib
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for morceau in iter(lambda: f.read(1 << 20), b""):
            h.update(morceau)
    return h.hexdigest().upper()


def controler_empreinte(chemin):
    """Le fichier téléchargé est-il bien celui qui est publié ? Lève ValueError sinon. Sans empreinte publiée
    (anciennes versions), rien n'est contrôlé, comme avant."""
    attendue = _empreintes.get(os.path.basename(chemin))
    if not attendue:
        return False
    if _empreinte(chemin) != attendue:
        try:
            os.remove(chemin)
        except OSError:
            pass
        raise ValueError("le fichier téléchargé ne correspond pas à celui qui est publié (empreinte SHA-256 différente)")
    return True


def version_refusee():
    """La version qui ne démarrait pas sur ce PC (le gardien est revenu à la précédente) : on ne la réinstalle pas."""
    try:
        with open(FICHIER_RETOUR, encoding="utf-8") as f:
            return str(json.load(f).get("refusee") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def sauvegarder_version(cible=None):
    """Avant une mise à jour : copie les programmes actuels (jarvis_*.py, moins de 2 Mo) dans version_precedente.
    Si la nouvelle version ne démarre pas, le gardien les remet en place. Renvoie le nombre de fichiers copiés."""
    source = jarvis_config.chemin()
    try:
        shutil.rmtree(DOSSIER_PRECEDENT, ignore_errors=True)
        os.makedirs(DOSSIER_PRECEDENT, exist_ok=True)
        n = 0
        for nom in os.listdir(source):
            if nom.startswith("jarvis_") and nom.endswith(".py"):
                shutil.copy2(os.path.join(source, nom), os.path.join(DOSSIER_PRECEDENT, nom))
                n += 1
        with open(os.path.join(DOSSIER_PRECEDENT, "version.json"), "w", encoding="utf-8") as f:
            json.dump({"version": version_actuelle(), "vers": cible, "quand": int(time.time()), "fichiers": n}, f)
        return n
    except OSError as erreur:
        _noter("Sauvegarde de la version actuelle impossible :", erreur)
        shutil.rmtree(DOSSIER_PRECEDENT, ignore_errors=True)      # jamais une sauvegarde à moitié faite
        return 0


def installer():
    """Télécharge l'installateur de la dernière version et le lance en mode « mise à jour », sans question.
    Renvoie la phrase à dire."""
    global _annoncee, lancee, _telechargement_rate
    _telechargement_rate = False
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
        if controler_empreinte(programme):
            _noter("Mise à jour : empreinte SHA-256 de l'installateur vérifiée.")
    except Exception as erreur:
        _telechargement_rate = True
        _noter("Téléchargement de la mise à jour impossible :", erreur)
        if noter_echec("telechargement", cible):
            return echec_a_dire()
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
        global _echec, _bloquee_par_windows
        # console cachée : seule la fenêtre claire d'avancement se voit (le journal installation.log garde tout)
        drapeaux = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        sauvegarder_version(cible)             # si la nouvelle version ne démarre pas, le gardien revient à celle-ci
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
        _bloquee_par_windows = True
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
        controler_empreinte(lot)
        return lot if os.path.getsize(lot) > 20_000 else None
    except Exception as erreur:
        _noter("Téléchargement de l'installateur .bat impossible :", erreur)
        return None


def notes_de(version):
    """Les notes de la version publiées sur GitHub, ou « » si on n'y arrive pas."""
    try:
        requete = urllib.request.Request(f"https://api.github.com/repos/{DEPOT}/releases/tags/v{version}",
                                         headers={"User-Agent": "Jarvis", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(requete, timeout=4) as r:
            return str(json.load(r).get("body") or "")
    except Exception:
        return ""


def notes_depuis(depuis, actuelle):
    """[(version, notes)] de toutes les versions publiées après « depuis » jusqu'à « actuelle » comprise, pour que
    quelqu'un qui saute des mises à jour reçoive quand même les remerciements des versions sautées.
    Sans réponse de GitHub : seulement les notes de la version actuelle."""
    try:
        requete = urllib.request.Request(f"https://api.github.com/repos/{DEPOT}/releases?per_page=30",
                                         headers={"User-Agent": "Jarvis", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(requete, timeout=5) as r:
            liste = json.load(r)
        trouvees = []
        for rel in liste:
            v = str(rel.get("tag_name") or "").lstrip("v")
            if (v and not rel.get("draft") and _nombres(depuis) < _nombres(v) <= _nombres(actuelle)):
                trouvees.append((v, str(rel.get("body") or "")))
        if trouvees:
            return sorted(trouvees, key=lambda x: _nombres(x[0]))
    except Exception:
        pass
    notes = notes_de(actuelle)
    return [(actuelle, notes)] if notes else []


def _vous():
    try:
        import jarvis_local
        return bool(jarvis_local._vous())
    except Exception:
        return False


def merci_utilisateur(notes):
    """Après une mise à jour : une phrase pour dire que son signalement ou sa suggestion a bien été reçu(e), et
    pris(e) en compte si cette version le dit (ligne cachée des notes : <!-- jarvis-merci: probleme=1a2b3c,4d5e6f
    idee=1a2b3c --> ; ce sont les six premiers caractères du numéro anonyme du PC, rien de personnel).
    Ne dit que ce qui est vrai : « reçu » seulement si l'envoi a réussi depuis ce PC. « » si rien à dire.
    Remet à zéro le décompte des messages envoyés."""
    try:
        import jarvis_rapports
        mon_id = str(jarvis_rapports.valeur("id") or "")[:6]
        envoyes = jarvis_rapports.valeur("messages_envoyes") or {}
        corriges, idees = set(), set()
        for genre, liste in re.findall(r"(probleme|idee)=([0-9a-f,]+)", notes or ""):
            (corriges if genre == "probleme" else idees).update(x for x in liste.split(",") if x)
        vous = _vous()
        phrases = []
        if mon_id and mon_id in corriges:
            phrases.append("Le problème que vous avez signalé est corrigé dans cette version." if vous
                           else "Le problème que tu as signalé est corrigé dans cette version.")
        elif envoyes.get("probleme"):
            phrases.append("Votre signalement a bien été reçu." if vous else "Ton signalement a bien été reçu.")
        if mon_id and mon_id in idees:
            phrases.append("Votre suggestion d'amélioration a été prise en compte dans cette version." if vous
                           else "Ta suggestion d'amélioration a été prise en compte dans cette version.")
        elif envoyes.get("idee"):
            phrases.append("Votre suggestion a bien été reçue." if vous else "Ta suggestion a bien été reçue.")
        if envoyes:
            jarvis_rapports.regler("messages_envoyes", {})
        if phrases:
            phrases.append("Merci, c'est grâce à vous que je m'améliore." if vous
                           else "Merci, c'est grâce à toi que je m'améliore.")
        return " ".join(phrases)
    except Exception:
        return ""


def nouveautes_de(version, notes=None):
    """Les titres des nouveautés d'une version, en une courte phrase (« tous les navigateurs, toutes les boîtes
    mail et tous les agendas »), lus dans ses notes sur GitHub (les lignes « - **Titre** : … »). « » si rien."""
    if notes is None:
        notes = notes_de(version)
        if not notes:
            return ""
    titres = []
    for titre in re.findall(r"(?m)^\s*[-*]\s+\*\*([^*\n]{3,60})\*\*", notes or ""):
        titre = titre.strip(" :.")
        if "«" in titre or "?" in titre or "(" in titre:
            continue                                   # une phrase à dire telle quelle, pas un titre
        if len(titre) > 1 and not titre[1].isupper():
            titre = titre[0].lower() + titre[1:]
        titres.append(titre)
        if len(titres) == 3:
            break
    if not titres:
        return ""
    return titres[0] if len(titres) == 1 else ", ".join(titres[:-1]) + " et " + titres[-1]


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
        oublier_echecs()                       # réussie : les essais ratés d'avant ne comptent plus
        notes = notes_de(actuelle)
        nouveautes = nouveautes_de(actuelle, notes) if notes else ""
        deja = []
        try:
            import jarvis_rapports
            deja = list(jarvis_rapports.valeur("merci_versions") or [])
        except Exception:
            jarvis_rapports = None
        a_lire = [(v, n) for v, n in notes_depuis(suivi.get("depuis"), actuelle) if v not in deja]
        merci = merci_utilisateur("\n".join(n for _, n in a_lire))     # rien de nouveau à lire : rien redit
        if jarvis_rapports is not None and a_lire:
            try:
                jarvis_rapports.regler("merci_versions", (deja + [v for v, _ in a_lire])[-30:])   # une seule fois par version
            except Exception:
                pass
        return (f"Mise à jour terminée : je suis maintenant en version {actuelle}."
                + (f" Les nouveautés : {nouveautes}." if nouveautes else "")
                + (f" {merci}" if merci else ""))
    if noter_echec("installation", suivi.get("vers")):
        return echec_a_dire()                  # 2e essai raté : la marche à suivre pour débloquer
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
