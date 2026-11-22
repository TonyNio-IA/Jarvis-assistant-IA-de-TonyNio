# -*- coding: utf-8 -*-
"""
JARVIS - ce qui joue en ce moment sur le PC, quelle que soit l'application (Spotify, Deezer, YouTube dans
n'importe quel navigateur, VLC, Apple Music, Lecteur multimédia…).

  « qu'est-ce qui joue ? », « c'est quoi cette musique ? », « quel est ce morceau ? », « qui chante ? »
Jarvis lit le titre que l'application donne à Windows (le même que celui affiché près du réglage du volume).
Rien n'est installé en plus et rien ne sort du PC. Quand Windows ne connaît pas la lecture (certaines
applications, certains réglages), Jarvis regarde quelle application produit du son à cet instant et donne le
titre de sa fenêtre.
Pour mettre en pause, passer au suivant ou régler le son : voir jarvis_commandes.py et jarvis_pratique.py
(touches multimédia, elles aussi valables pour toutes les applications).
"""

import json
import re
import subprocess
import time

SANS_FENETRE = 0x08000000
# Windows donne la liste des lectures en cours ; PowerShell, présent sur tous les Windows 11, sait la lire
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Attendre($operation, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($operation)); if (-not $t.Wait(4000)) { throw 'trop long' }; $t.Result }
$classe = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media.Control,ContentType=WindowsRuntime]
$proprietes = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties,Windows.Media.Control,ContentType=WindowsRuntime]
$g = Attendre ($classe::RequestAsync()) $classe
$courante = $g.GetCurrentSession()
$liste = @()
foreach ($s in $g.GetSessions()) {
  $titre = ''; $artiste = ''
  try { $p = Attendre ($s.TryGetMediaPropertiesAsync()) $proprietes; $titre = [string]$p.Title; $artiste = [string]$p.Artist } catch {}
  $liste += [pscustomobject]@{ appli = [string]$s.SourceAppUserModelId; etat = [string]$s.GetPlaybackInfo().PlaybackStatus; titre = $titre; artiste = $artiste; courante = [bool]($courante -and $s.SourceAppUserModelId -eq $courante.SourceAppUserModelId) }
}
'JARVIS-MUSIQUE:' + (ConvertTo-Json -Compress -InputObject @($liste))
"""

# Nom prononcé de l'application d'après l'identifiant que Windows donne (« Spotify.exe », « chrome », « …ZuneMusic… »)
_APPLIS = (("spotify", "Spotify"), ("deezer", "Deezer"), ("chrome", "Chrome"), ("msedge", "Edge"), ("firefox", "Firefox"),
           ("308046b0af4a39cb", "Firefox"),       # l'identifiant que Firefox donne à Windows
           ("brave", "Brave"), ("opera", "Opera"), ("vivaldi", "Vivaldi"), ("vlc", "VLC"), ("itunes", "iTunes"),
           ("applemusic", "Apple Music"), ("appleinc.applemusic", "Apple Music"), ("zunemusic", "le Lecteur multimédia"),
           ("zunevideo", "Films et TV"), ("amazon", "Amazon Music"), ("tidal", "Tidal"), ("qobuz", "Qobuz"),
           ("youtubemusic", "YouTube Music"), ("netflix", "Netflix"), ("disney", "Disney+"), ("primevideo", "Prime Video"),
           ("molotov", "Molotov"), ("foobar", "foobar2000"), ("aimp", "AIMP"), ("winamp", "Winamp"), ("musicbee", "MusicBee"),
           ("mpc-hc", "Media Player Classic"), ("mpc-be", "Media Player Classic"), ("potplayer", "PotPlayer"), ("kodi", "Kodi"))
_NAVIGATEURS = ("Chrome", "Edge", "Firefox", "Brave", "Opera", "Vivaldi")

_QUESTION = re.compile(
    r"\bqu'est[- ]ce (?:qui|que) (?:(?:[çc]a |c'est qui )?(?:joue|passe)|se joue|(?:j'[ée]coute|on [ée]coute|tu joues|tu passes))\b"
    r"|\bqu'est[- ]ce que c'est (?:que |comme )?(?:cette |ce |la |le )?(?:musique|chanson|morceau|titre|son)\b"
    r"|\bc'est quo[iy] (?:(?:cette|ce|la|le|comme) )?(?:musique|chanson|morceau|titre|son)\b"
    r"|\bc'est quelle (?:musique|chanson)\b|\bc'est quel (?:morceau|titre)\b"
    r"|\bquel(?:le)? est (?:cette |ce |la |le |le nom de (?:cette |ce |la )?|le titre de (?:cette |ce |la )?)"
    r"(?:musique|chanson|morceau|titre)\b"
    r"|\b(?:qui|c'est qui(?: qui)?) (?:chante(?: (?:[çc]a|cette chanson|ce morceau|l[aà]))?"
    r"|joue (?:[çc]a|cette chanson|ce morceau))\W*$"
    r"|\b(?:donne|dis)[- ]moi le (?:titre|nom) (?:de (?:la |cette |ce )?(?:musique|chanson|morceau)|du morceau)\b"
    r"|\b(?:musique|chanson|morceau|titre) (?:en cours|qui passe|qui joue)\b")
# Ce qui n'est pas une question sur la lecture en cours (« qu'est-ce qui passe à la télé ce soir ? »)
_AUTRE_SUJET = re.compile(r"\b(?:t[ée]l[ée]|tv|cin[ée]ma|ce soir|demain|cha[iî]ne|radio (?:ce|demain)|programme)\b")

_lire = None        # remplaçable pour les essais : fonction qui renvoie la liste des lectures
_son = None         # remplaçable pour les essais : fonction qui renvoie [(programme, titre de sa fenêtre)]
_PAS_UNE_MUSIQUE = ("python", "pythonw", "jarvis", "systemsounds", "audiodg", "shellexperiencehost")
_SITES = re.compile(r"youtube|spotify|deezer|netflix|twitch|dailymotion|soundcloud|radio|music|prime video|disney", re.I)
_FIN_NAVIGATEUR = re.compile(r"(?: et \d+ (?:autres? )?(?:pages?|onglets?)(?: de plus)?)?(?:\s[-–—]\s[^-–—]{1,30})?\s[-–—]\s"
                             r"(?:Google Chrome|Mozilla Firefox(?: [\w ]+)?|Microsoft.{0,2}Edge|Brave|Opera(?: GX)?|Vivaldi)\s*$")


def nom_appli(identifiant):
    """Nom prononcé d'une application d'après l'identifiant donné par Windows, ou « » si elle est inconnue."""
    bas = (identifiant or "").lower()
    for morceau, nom in _APPLIS:
        if morceau in bas:
            return nom
    nom = re.sub(r"\.exe$", "", bas.rsplit("\\", 1)[-1].split("!")[0])
    return "" if not nom or "_" in nom or len(nom) > 25 else nom.capitalize()


def lectures():
    """Les lectures connues de Windows : [{"appli", "etat" (« Playing », « Paused »…), "titre", "artiste",
    "courante"}]. Liste vide si rien ne joue ; None si Windows n'a pas pu répondre."""
    if _lire is not None:
        return _lire()
    try:
        sortie = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                 "-Command", _SCRIPT], capture_output=True, timeout=12, creationflags=SANS_FENETRE)
        texte = sortie.stdout.decode("utf-8", "replace")
        m = re.search(r"JARVIS-MUSIQUE:(.*)", texte)
        if not m:
            print("Musique : Windows n'a pas répondu (", sortie.stderr.decode("utf-8", "replace").strip()[:160], ")")
            return None
        donnees = json.loads(m.group(1).strip() or "[]")
        if isinstance(donnees, dict):
            donnees = [donnees]
        return [d for d in donnees if isinstance(d, dict)]
    except Exception as erreur:
        print("Musique :", type(erreur).__name__, erreur)
        return None


def _titres_fenetres():
    """{programme: [titres de ses fenêtres visibles, la plus récente d'abord]}."""
    import ctypes
    import ctypes.wintypes as wt
    import psutil
    user32 = ctypes.windll.user32
    titres, noms = {}, {}

    def voir(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            longueur = user32.GetWindowTextLengthW(hwnd)
            if longueur:
                tampon = ctypes.create_unicode_buffer(longueur + 1)
                user32.GetWindowTextW(hwnd, tampon, longueur + 1)
                pid = wt.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value not in noms:
                    try:
                        noms[pid.value] = psutil.Process(pid.value).name().lower().removesuffix(".exe")
                    except Exception:
                        noms[pid.value] = ""
                if noms[pid.value]:
                    titres.setdefault(noms[pid.value], []).append(tampon.value)
        return True
    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(voir), 0)
    return titres


def applis_qui_jouent():
    """Les applications qui produisent du son à cet instant : [(programme, titre de sa fenêtre ou « »)].
    Regarde trois fois de suite, au cas où la musique serait pile entre deux notes."""
    if _son is not None:
        return _son()
    try:
        from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        programmes = []
        for essai in range(3):
            for session in AudioUtilities.GetAllSessions():
                try:
                    if not session.Process:
                        continue
                    nom = session.Process.name().lower().removesuffix(".exe")
                    if nom in _PAS_UNE_MUSIQUE or nom in programmes:
                        continue
                    if session._ctl.QueryInterface(IAudioMeterInformation).GetPeakValue() > 0.01:
                        programmes.append(nom)
                except Exception:
                    continue
            if programmes:
                break
            time.sleep(0.15)
        if not programmes:
            return []
        try:
            fenetres = _titres_fenetres()
        except Exception:
            fenetres = {}
        resultat = []
        for nom in programmes:
            titres = fenetres.get(nom, [])
            titre = next((x for x in titres if _SITES.search(x)), titres[0] if titres else "")
            resultat.append((nom, titre))
        return resultat
    except Exception as erreur:
        print("Musique (son) :", type(erreur).__name__, erreur)
        return []


def phrase_son(programme, titre):
    """La phrase à dire quand on ne connaît que l'application qui produit le son et le titre de sa fenêtre."""
    nom = nom_appli(programme) or "une application"
    titre = _propre(titre)
    titre = _FIN_NAVIGATEUR.sub("", titre)
    titre = re.sub(r"^\(\d+\)\s*", "", titre)                       # « (3) Titre » : le compteur de notifications
    titre = re.sub(r"\s*[-–|]\s*YouTube\s*$", "", titre).strip()
    if not titre or titre.lower() in (nom.lower(), programme.lower(), "spotify", "spotify premium", "spotify free"):
        return f"Le son vient de {nom}, mais je n'ai pas le titre."
    if nom in _NAVIGATEURS:
        return f"Le son vient de {nom}. Sa fenêtre affiche : {titre}."
    return f"Sur {nom} : {titre}."


def en_cours(liste=None):
    """La lecture la plus probable : celle qui joue (celle que Windows met en avant d'abord), sinon celle en
    pause que Windows met en avant. None si rien."""
    liste = lectures() if liste is None else liste
    if not liste:
        return None
    jouent = [l for l in liste if l.get("etat") == "Playing"]
    for groupe in (jouent, [l for l in liste if l.get("etat") == "Paused"]):
        if groupe:
            return next((l for l in groupe if l.get("courante")), groupe[0])
    return None


def _propre(texte):
    texte = re.sub(r"\s*(?://|\|)\s*", ", ", str(texte or ""))       # « Titre // Clip officiel » se dit mal
    return re.sub(r"\s+", " ", texte).strip(" ,")


def phrase(lecture):
    """La phrase à dire pour une lecture."""
    titre, artiste = _propre(lecture.get("titre")), _propre(lecture.get("artiste"))
    appli = nom_appli(lecture.get("appli"))
    en_pause = lecture.get("etat") != "Playing"
    ou = (" dans " if appli in _NAVIGATEURS else " sur ") + appli if appli else ""
    ou = ou.replace(" sur le Lecteur", " dans le Lecteur")
    if not titre:
        return ("Quelque chose " + ("est en pause" if en_pause else "joue") + (ou or " sur ce PC")
                + ", mais l'application ne donne pas son titre.")
    titre = re.sub(r"\s*[-–|]\s*YouTube\s*$", "", titre)          # « Titre - YouTube » dans certains navigateurs
    debut = "En pause : " if en_pause else "C'est "
    if artiste and artiste.lower() not in titre.lower():
        return f"{debut}{titre}, de {artiste}{ou}."
    return f"{debut}{titre}{ou}."


def commande(t):
    """« qu'est-ce qui joue ? » : le titre en cours. Renvoie la phrase à dire, ou None si ce n'est pas la demande."""
    t = (t or "").replace("’", "'").lower()
    if not _QUESTION.search(t) or _AUTRE_SUJET.search(t):
        return None
    liste = lectures()
    lecture = en_cours(liste)
    if lecture is not None and lecture.get("etat") == "Playing":
        return phrase(lecture)
    # Windows ne connaît aucune lecture en cours : quelle application produit du son à cet instant ?
    sons = applis_qui_jouent()
    if sons:
        return phrase_son(*sons[0])
    if lecture is not None:                       # rien ne s'entend, mais une lecture est en pause
        return phrase(lecture)
    if liste is None:
        return "Je n'arrive pas à savoir ce qui joue sur ce PC."
    return "Rien ne joue sur ce PC en ce moment."
