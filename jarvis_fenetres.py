"""
JARVIS - gestion des fenêtres à la voix (sans passer par Claude).

  « mets la fenêtre en plein écran », « agrandis Imou », « mets Chrome en grand »
  « réduis la fenêtre », « réduis Chrome »
  « mets la fenêtre à gauche » (à droite, en haut, en bas : la moitié de l'écran)
  « mets Imou au premier plan »
  « ferme la fenêtre », « ferme Imou »
  « affiche le bureau », « change de fenêtre »

Sans nom d'application, la commande agit sur la fenêtre active. Avec un nom, Jarvis cherche
parmi les fenêtres ouvertes celle qui lui ressemble le plus, même si le nom a été mal entendu
(« immo » pour Imou) : comme il n'y a que quelques fenêtres ouvertes, il y a peu de risque d'erreur.
"""

import ctypes
import ctypes.wintypes
import difflib
import os
import re
import time

try:
    import psutil
except Exception:
    psutil = None

user32 = ctypes.windll.user32
user32.GetForegroundWindow.restype = ctypes.c_void_p
for _f in ("IsWindowVisible", "IsIconic", "IsZoomed", "GetWindowTextLengthW", "SetForegroundWindow"):
    getattr(user32, _f).argtypes = [ctypes.c_void_p]
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
user32.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
_ENUM = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows.argtypes = [_ENUM, ctypes.c_void_p]

CLASSES_IGNOREES = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
                    "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow")
SEUIL = 0.6          # ressemblance minimale entre le nom entendu et une fenêtre ouverte
SEUIL_FERMER = 0.75  # pour fermer, on exige un nom plus proche (une erreur serait plus gênante)
ECART = 0.1          # ... et avance minimale sur la deuxième fenêtre la plus ressemblante


# ---------- Ressemblance entre un nom entendu et un nom réel ----------

def sans_accents(t):
    t = t.lower()
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def cle_sonore(nom):
    """Écriture approximative de la façon dont un nom se prononce (« Imou » -> « imu », « immo » -> « imo »)."""
    t = sans_accents(nom).replace(" ", "")
    for a, b in (("eau", "o"), ("au", "o"), ("ou", "u"), ("ph", "f"), ("qu", "k"), ("ch", "x"),
                 ("ck", "k"), ("y", "i"), ("h", "")):
        t = t.replace(a, b)
    t = re.sub(r"c(?=[ei])", "s", t).replace("c", "k")
    t = re.sub(r"(.)\1+", r"\1", t)               # lettres doublées
    return re.sub(r"(es|e|s|t|d|x)$", "", t) if len(t) > 3 else t


def ressemblance(a, b):
    """De 0 à 1 : à quel point deux noms se ressemblent, à l'écrit ou à l'oreille."""
    a, b = sans_accents(a), sans_accents(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ecrit = difflib.SequenceMatcher(None, a, b).ratio()
    oral = difflib.SequenceMatcher(None, cle_sonore(a), cle_sonore(b)).ratio()
    return max(ecrit, oral)


def meilleur(nom, candidats, seuil=SEUIL, ecart=ECART):
    """candidats : liste de (objet, [noms possibles]). Renvoie l'objet le plus ressemblant, ou None."""
    notes = []
    for objet, noms in candidats:
        notes.append((max((ressemblance(nom, n) for n in noms if n), default=0.0), objet))
    notes.sort(key=lambda x: -x[0])
    if not notes or notes[0][0] < seuil:
        return None
    if len(notes) > 1 and notes[0][0] < 0.85 and notes[0][0] - notes[1][0] < ecart:
        return None                               # deux candidats trop proches : on ne devine pas
    return notes[0][1]


# ---------- Les fenêtres ouvertes ----------

def _texte(hwnd):
    tampon = ctypes.create_unicode_buffer(300)
    user32.GetWindowTextW(hwnd, tampon, 300)
    return tampon.value


def _classe(hwnd):
    tampon = ctypes.create_unicode_buffer(200)
    user32.GetClassNameW(hwnd, tampon, 200)
    return tampon.value


def _programme(hwnd):
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == os.getpid():
        return None                               # c'est Jarvis lui-même
    if psutil is None:
        return ""
    try:
        return os.path.splitext(psutil.Process(pid.value).name())[0]
    except Exception:
        return ""


def _visible(hwnd):
    if not user32.IsWindowVisible(hwnd) or not user32.GetWindowTextLengthW(hwnd):
        return False
    if user32.GetWindowLongW(hwnd, -20) & 0x80:   # fenêtre outil (sans bouton dans la barre des tâches)
        return False
    if _classe(hwnd) in CLASSES_IGNOREES:
        return False
    masquee = ctypes.c_int(0)                     # fenêtres d'applications suspendues (invisibles)
    try:
        ctypes.windll.dwmapi.DwmGetWindowAttribute(ctypes.c_void_p(hwnd), 14, ctypes.byref(masquee), 4)
    except Exception:
        pass
    return not masquee.value


def fenetres():
    """Liste des fenêtres ouvertes : (identifiant, titre, programme)."""
    trouvees = []

    def une(hwnd, _):
        if _visible(hwnd):
            programme = _programme(hwnd)
            if programme is not None:
                trouvees.append((hwnd, _texte(hwnd), programme))
        return True

    user32.EnumWindows(_ENUM(une), None)
    return trouvees


def active():
    """La fenêtre active, ou None si c'est le bureau (ou Jarvis)."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or not _visible(hwnd) or _programme(hwnd) is None:
        return None
    return hwnd


def _noms(titre, programme):
    morceaux = [p.strip() for p in re.split(r"\s[-–—|]\s", titre) if p.strip()]
    mots = [m for m in sans_accents(titre).split() if len(m) >= 3]
    return [programme, titre] + morceaux + mots


def trouver(nom, seuil=SEUIL):
    """La fenêtre ouverte dont le titre ou le programme ressemble le plus à « nom », ou None."""
    return meilleur(nom, [(hwnd, _noms(titre, programme)) for hwnd, titre, programme in fenetres()], seuil)


def nom_court(hwnd):
    """Nom à prononcer pour une fenêtre : la dernière partie de son titre (« ... - Google Chrome »)."""
    titre = _texte(hwnd)
    morceaux = [p.strip() for p in re.split(r"\s[-–—|]\s", titre) if p.strip()]
    nom = morceaux[-1] if morceaux else titre
    return nom if 0 < len(nom) <= 30 else "la fenêtre"


def contexte(maximum=8):
    """Note donnée à Claude avec chaque demande : la fenêtre active et les autres fenêtres ouvertes."""
    ouvertes = fenetres()
    if not ouvertes:
        return ""
    devant = active()
    noms = []
    for hwnd, titre, programme in ouvertes:
        nom = nom_court(hwnd)
        nom = programme or "fenêtre" if nom == "la fenêtre" else nom
        if hwnd != devant and nom not in noms:
            noms.append(nom)
    note = "(Sur l'écran de TonyNio"
    if devant:
        note += " : fenêtre active « " + _texte(devant)[:70] + " »"
    if noms:
        note += " ; autres fenêtres ouvertes : " + ", ".join(noms[:maximum])
    return note + ".) "


# ---------- Actions ----------

def _touche(*codes):
    for code in codes:
        user32.keybd_event(code, 0, 0, 0)
    for code in reversed(codes):
        user32.keybd_event(code, 0, 2, 0)


def premier_plan(hwnd):
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)
    _touche(0x12)                                 # un appui sur Alt : Windows autorise alors le changement
    user32.SetForegroundWindow(hwnd)


def agrandir(hwnd):
    premier_plan(hwnd)
    user32.ShowWindow(hwnd, 3)


def reduire(hwnd):
    user32.ShowWindow(hwnd, 6)


def restaurer(hwnd):
    premier_plan(hwnd)
    user32.ShowWindow(hwnd, 9)


def fermer(hwnd):
    user32.PostMessageW(hwnd, 0x0010, 0, 0)       # fermeture normale : l'application peut proposer d'enregistrer


def placer(hwnd, cote):
    """Place la fenêtre sur une moitié de l'écran : « gauche », « droite », « haut » ou « bas »."""
    zone = ctypes.wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(zone), 0)
    x, y, l, h = zone.left, zone.top, zone.right - zone.left, zone.bottom - zone.top
    if cote == "gauche":
        l //= 2
    elif cote == "droite":
        x, l = x + l // 2, l - l // 2
    elif cote == "haut":
        h //= 2
    else:
        y, h = y + h // 2, h - h // 2
    premier_plan(hwnd)
    user32.ShowWindow(hwnd, 9)
    time.sleep(0.05)
    user32.SetWindowPos(hwnd, None, x, y, l, h, 0x0004 | 0x0040)


def afficher_bureau():
    _touche(0x5B, 0x44)                           # Windows + D


def fenetre_precedente():
    _touche(0x12, 0x09)                           # Alt + Tab


# ---------- Commandes à la voix ----------

_AGRANDIR = (r"\b(agrandis|agrandir|agrandit|maximise|maximiser)\b|"
             r"\b(mets|mettre|met|passe|passer|affiche|ouvre)\b.*\b(plein écran|grand écran|grande? fenêtre|en grande?|en entier)\b")
_REDUIRE = (r"\b(réduis|réduire|réduit|minimise|minimiser)\b|"
            r"\b(mets|mettre|passe)\b.*\b(en petit|dans la barre des tâches)\b")
_RESTAURER = r"\b(restaure|restaurer)\b|\b(taille|fenêtre) normale\b"
_PLACER = r"\b(mets|mettre|met|place|placer|déplace|cale|colle)\b.*\b(à gauche|à droite|en haut|en bas)\b"
_DEVANT = r"\b(mets|mettre|met|passe|affiche|montre|ramène|remets)\b.*\b(au premier plan|devant|en avant)\b"
_FERMER = r"\b(ferme|fermer|fermes)\b"
_BUREAU = r"\b(affiche|montre|montre-moi|reviens)\b.*\bbureau\b|\b(réduis|cache|minimise) tout\b"
_SUIVANTE = r"\b(change de fenêtre|fenêtre (suivante|précédente)|autre fenêtre)\b"
_AUTRE_SUJET = r"\b(son|volume|musique|luminosité|chanson|vidéo|texte|police|image|photo|prix|minuteur|rappel)\b"
# Mots qui ne font pas partie du nom de l'application
_MOTS_COMMANDE = (r"\b(jarvis|est-ce que|tu peux|peux-tu|s'il te plaît|stp|moi|agrandis|agrandir|agrandit|maximise|maximiser|"
                  r"réduis|réduire|réduit|minimise|minimiser|restaure|restaurer|mets|mettre|met|passe|passer|affiche|"
                  r"montre|ramène|remets|place|placer|déplace|cale|colle|ouvre|ferme|fermer|fermes|"
                  r"en plein écran|plein écran|en grand écran|grand écran|en grande fenêtre|en grand fenêtre|"
                  r"grande fenêtre|en grande|en grand|en entier|en petit|dans la barre des tâches|taille normale|"
                  r"à gauche|à droite|en haut|en bas|au premier plan|devant|en avant|"
                  r"la fenêtre|cette fenêtre|ma fenêtre|une fenêtre|fenêtre|l'application|cette application|"
                  r"application|appli|logiciel|programme|active|actuelle|en cours|de l'écran|sur l'écran|"
                  r"écran|ecran|grande|grand|plein|pleine|taille|"
                  r"le|la|les|l'|de|du|des|d'|un|une|ça|ca|cela|aussi|maintenant|et)\b")


def _cible(t, seuil=SEUIL):
    """Renvoie (fenêtre, nom à prononcer), ou (None, None) si le nom donné ne correspond à aucune
    fenêtre ouverte (la demande est alors laissée à Claude)."""
    nom = " ".join(re.sub(_MOTS_COMMANDE, " ", t).replace("'", " ").split()).strip(" .,!?")
    if not nom:
        hwnd = active()
        return (hwnd, nom_court(hwnd)) if hwnd else (None, "")
    hwnd = trouver(nom, seuil)
    return (hwnd, nom_court(hwnd)) if hwnd else (None, None)


def trouver_nom(t, seuil=SEUIL):
    """Le nom d'application contenu dans la demande, s'il désigne une fenêtre ouverte (sinon None)."""
    nom = " ".join(re.sub(_MOTS_COMMANDE, " ", t).replace("'", " ").split()).strip(" .,!?")
    return trouver(nom, seuil) if nom else None


def commande(t):
    """t : la demande en minuscules. Renvoie la phrase à dire, ou None si ce n'est pas pour les fenêtres."""
    if re.search(_AUTRE_SUJET, t):
        return None
    if re.search(_BUREAU, t):
        afficher_bureau()
        return "Voilà le bureau."
    if re.search(_SUIVANTE, t):
        fenetre_precedente()
        return "C'est fait."
    for motif, action, phrase in ((_PLACER, None, None), (_AGRANDIR, agrandir, "J'agrandis {}."),
                                  (_DEVANT, premier_plan, "Voilà {}."), (_REDUIRE, reduire, "Je réduis {}."),
                                  (_RESTAURER, restaurer, "C'est fait pour {}."), (_FERMER, fermer, "Je ferme {}.")):
        m = re.search(motif, t)
        if not m:
            continue
        hwnd, nom = _cible(t, SEUIL_FERMER if action is fermer else SEUIL)
        if hwnd is None:
            # nom inconnu : Claude s'en occupe ; aucune fenêtre active : on le dit
            return None if nom is None else ("Aucune fenêtre n'est active." if action is not fermer else None)
        if motif is _PLACER:
            cote = {"à gauche": "gauche", "à droite": "droite", "en haut": "haut", "en bas": "bas"}[
                re.search(r"à gauche|à droite|en haut|en bas", t).group(0)]
            placer(hwnd, cote)
            return f"C'est fait, {nom} est {'en ' + cote if cote in ('haut', 'bas') else 'à ' + cote}."
        # « ferme » tout seul ne ferme rien : il faut dire quoi (« la fenêtre », « ça », un nom d'application)
        if action is fermer and hwnd == active() and not re.search(
                r"\b(fenêtre|ça|ca|cela|application|appli)\b", t) and trouver_nom(t, SEUIL_FERMER) is None:
            return None
        action(hwnd)
        return phrase.format(nom)
    return None
