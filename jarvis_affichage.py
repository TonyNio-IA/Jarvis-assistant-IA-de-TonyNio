"""
JARVIS - affichage rapide du réacteur (60 images par seconde).

Même visuel que l'ancien affichage, mais dessiné avec pygame, beaucoup plus
rapide : environ 5 ms par image au lieu de 37. Le réacteur peut donc tourner
à 60 images par seconde quand Jarvis est actif.

Autour du réacteur, une couronne de graduations réagit au vrai son : le spectre de
ta voix quand Jarvis écoute, celui de sa voix quand il répond. Une onde part du cœur
à chaque réveil, et un léger halo lumineux entoure les filaments.

Au-dessus du réacteur, la fenêtre de discussion : ce que tu dis s'y écrit au fur et à mesure, puis la
réponse de Jarvis le remplace. Un clic dedans et tu peux écrire ta demande au clavier (Entrée l'envoie).
Sous le réacteur, le panneau affiche l'état de Jarvis, l'heure et des jauges :
processeur, mémoire, carte graphique, réseau (et température si le PC la fournit).

En veille, le réacteur se fait discret : il rétrécit, la fenêtre de discussion et le panneau disparaissent
(il reste les jauges). Il reprend sa taille dès que Jarvis t'entend, ou quand tu passes la souris dessus.
Un minuteur ou un rappel en attente se lit sur la couronne (elle se vide peu à peu) et dans le panneau.
Au lancement, le réacteur se forme ; à l'arrêt ou au redémarrage, il se referme.
"""

import ctypes
import ctypes.wintypes
import math
import os
import random
import re
import threading
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
import pygame

import jarvis_claude
import jarvis_systeme
import jarvis_famille
import jarvis_vigilance
import jarvis_voix

CLE = (1, 2, 3)          # couleur rendue invisible (transparence de la fenêtre)
ELARGISSEMENT = 30       # largeur ajoutée au panneau de chaque côté du réacteur
NB_GRADUATIONS = 72      # traits de la couronne extérieure (ils dessinent le spectre du son)
MODE_DISCRET = True      # en veille, le réacteur rétrécit et le panneau disparaît
TAILLE_DISCRETE = 0.45   # taille du réacteur en veille (1 = taille normale)
DELAI_DISCRET = 35       # secondes de veille avant de rétrécir
VITESSE_REFLET = 174      # vitesse du reflet de lumière qui fait le tour des panneaux et du réacteur (points/s)
TOUR_REFLET_REACTEUR = 7.0   # secondes pour que le reflet fasse le tour du cercle du réacteur (vitesse régulière)
NB_REFLETS = 2          # nombre de reflets sur chaque contour, répartis à égale distance
LONGUEUR_REFLET = 160     # longueur du reflet (points)
PAUSE_REFLET = 0.0       # secondes de pause entre deux tours (0 : il tourne sans s'arrêter)
REFLET_REACTEUR = True   # le reflet fait aussi le tour du cercle du réacteur
DANSE_MUSIQUE = True     # en veille, le réacteur bouge au rythme du son du PC (musique, vidéo)
REGARD_SOURIS = True     # le cœur du réacteur se tourne un peu vers la souris quand elle approche
FORCE_DANSE = 0.22       # intensité de la danse sur la musique
FORCE_REGARD = 0.195     # intensité du suivi de la souris (décalage du cœur, en part du rayon)
DOUCEUR_NUIT = 0.72      # luminosité du réacteur en veille la nuit (1 = comme le jour)
JAUGES = ("CPU", "RAM", "GPU", "NET", "TMP")   # jauges affichées sous le réacteur
actuel = None            # l'affichage en cours (pour les réglages : position de la fenêtre)
GRAND_EN_MODE_ENFANT = True   # en mode enfant, le réacteur est bien plus grand (l'enfant voit s'il écoute, réfléchit...)
ECHELLE_ENFANT = 3.0     # 3 fois sa taille normale (limité à la hauteur de l'écran)
DOUX_LA_NUIT = True      # la nuit (après le coucher du soleil), le réacteur en veille est moins lumineux
FETES = True             # petite animation à minuit et le jour de l'anniversaire
DUREE_FETE = 8.0         # secondes
COULEURS_FETE = ((255, 215, 90), (255, 46, 151), (80, 220, 255), (157, 77, 255), (120, 255, 150))
DUREE_VIGILANCE = 12.0   # secondes d'animation quand une alerte météo de Météo-France est annoncée
COULEURS_VIGILANCE = {2: (255, 214, 0), 3: (255, 128, 0), 4: (255, 30, 30)}     # jaune, orange, rouge
ICONES_JAUGES = True     # petite icône entre le nom et la valeur de chaque jauge
PANNEAU_COMPACT = True   # en mode discret, les jauges restent visibles dans un petit panneau (sinon il disparaît)
DUREE_NAISSANCE = 2.4    # secondes que met le réacteur à se former au lancement
DUREE_ALERTE = 5.0       # secondes d'animation quand un minuteur ou un rappel sonne
DUREE_FERMETURE = 0.7    # secondes qu'il met à se refermer à l'arrêt
HALO = True              # léger halo lumineux autour des filaments (False = dessin net, un peu plus rapide)
HAUTEUR_DISCUSSION = 66  # hauteur de la fenêtre de discussion, au-dessus du réacteur
LIGNES_DISCUSSION = 3    # lignes de texte visibles (un texte plus long défile tout seul)
LONGUEUR_SAISIE = 400    # caractères au plus dans une demande écrite
ABANDON_SAISIE = 60      # secondes sans frappe avant d'abandonner une demande commencée
INVITE_SAISIE = "Clique ici pour écrire à Jarvis"
# Des idées de demandes, qui défilent dans la fenêtre de discussion quand elle est vide
IDEES = ("Quelle heure est-il ?", "Quel temps fera-t-il demain ?", "Mets un minuteur pâtes de 10 minutes",
         "Rappelle-moi demain à 9 heures d'appeler le garage", "Combien font 17 fois 23 ?", "Convertis 30 miles en kilomètres",
         "Ajoute du lait à la liste de courses", "Qu'est-ce qu'il y a sur ma liste de courses ?", "Réveille-moi à 7 heures",
         "Quelle heure est-il à New York ?", "Y a-t-il une alerte météo ?", "C'est quand les prochaines vacances scolaires ?",
         "C'est quand le prochain jour férié ?", "Ouvre le bloc-notes", "Monte la luminosité", "Active le mode sombre",
         "Baisse le son de Spotify", "Cherche des vidéos de chats sur YouTube", "Cherche un casque audio sur Amazon",
         "Résume ce que j'ai copié", "Traduis en anglais ce que j'ai copié", "Corrige ce que j'ai copié",
         "Qu'est-ce qu'il y a à l'écran ?", "Fais une capture d'écran", "Est-ce que mon PC va bien ?",
         "Est-ce que j'ai des nouveaux mails ?", "C'est quand mon prochain rendez-vous ?", "Qu'est-ce que j'ai demain ?",
         "Est-ce qu'Internet fonctionne ?", "Qui m'a appelé ?", "Allume la télé", "Raconte-moi une blague",
         "Raconte-moi une anecdote", "Retiens que mon plat préféré, ce sont les lasagnes", "Note que je dois racheter du café",
         "Lance un chrono", "Mets les couleurs Aurore", "Prends une voix de femme", "Parle plus vite",
         "Active le mode nuit", "Ouvre les réglages", "Qu'est-ce que tu sais faire ?", "Combien coûte le gazole près de chez moi ?",
         "Donne-moi la recette des crêpes", "Coupe le micro")
DUREE_IDEE = 6.0          # secondes par idée affichée
user32 = ctypes.windll.user32
user32.CreatePopupMenu.restype = ctypes.c_void_p
user32.AppendMenuW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_wchar_p]
user32.TrackPopupMenu.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p]
user32.DestroyMenu.argtypes = [ctypes.c_void_p]
# Sur un Windows 64 bits, « toujours au premier plan » (-1) doit être passé comme un pointeur :
# sans cette déclaration, la demande était ignorée et le réacteur passait derrière les fenêtres.
user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_uint]
PREMIER_PLAN = ctypes.c_void_p(-1)
TOUJOURS_DEVANT = False      # False : le réacteur reste sur le Bureau, derrière les fenêtres (il écoute et répond quand même)
_clavier = ctypes.WinDLL("user32")       # copie à part de user32, pour donner le clavier à la fenêtre
_clavier.SetFocus.argtypes = [ctypes.c_void_p]
_clavier.SetFocus.restype = ctypes.c_void_p
_clavier.GetFocus.restype = ctypes.c_void_p


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.wintypes.RECT):
    """Le rectangle de Windows (même type que celui déclaré par jarvis_ecran : user32 est partagé entre
    les modules, et deux types différents faisaient planter le réacteur au survol de la souris)."""
    gauche = property(lambda self: self.left)
    haut = property(lambda self: self.top)
    droite = property(lambda self: self.right)
    bas = property(lambda self: self.bottom)


PLUS_PREMIER_PLAN = ctypes.c_void_p(-2)
_ecrans = ctypes.WinDLL("user32")        # copie à part de user32 (les déclarations ne gênent pas les autres modules)
_ecrans.GetForegroundWindow.restype = ctypes.c_void_p
_ecrans.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
_ecrans.MonitorFromWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
_ecrans.MonitorFromWindow.restype = ctypes.c_void_p
_ecrans.GetClassNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
_ecrans.IsWindowVisible.argtypes = [ctypes.c_void_p]
_ecrans.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
_ecrans.GetWindowLongW.restype = ctypes.c_long
_dwm = ctypes.WinDLL("dwmapi")
_dwm.DwmGetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]


class _INFO_ECRAN(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", ctypes.wintypes.RECT), ("rcWork", ctypes.wintypes.RECT),
                ("dwFlags", ctypes.c_ulong)]


_ecrans.GetMonitorInfoW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_INFO_ECRAN)]
_FENETRES_BUREAU = ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd")


def plein_ecran(soi=None):
    """Vrai si une vidéo, un jeu ou une présentation occupe tout l'écran : le réacteur ne reste pas devant."""
    try:
        etat = ctypes.c_int(0)                    # jeu en plein écran exclusif (Direct3D) ou mode présentation
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(etat)) == 0 and etat.value in (3, 4):
            return True
        hwnd = _ecrans.GetForegroundWindow()
        if not hwnd or (soi and (hwnd & 0xFFFFFFFF) == (soi & 0xFFFFFFFF)):
            return False
        nom = ctypes.create_unicode_buffer(64)
        _ecrans.GetClassNameW(hwnd, nom, 64)
        if nom.value in _FENETRES_BUREAU:
            return False
        # une fenêtre invisible, cachée par Windows ou « outil » (ex. WMPTransition) n'est pas une vidéo plein écran
        if not _ecrans.IsWindowVisible(hwnd):
            return False
        cache = ctypes.c_int(0)
        _dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cache), ctypes.sizeof(cache))
        if cache.value:
            return False
        style_ext = _ecrans.GetWindowLongW(hwnd, -20)
        if style_ext & 0x80:                      # WS_EX_TOOLWINDOW
            return False
        if style_ext & 0x20 and style_ext & 0x80000:   # transparente aux clics et superposée : une couche d'effet
            return False
        r = ctypes.wintypes.RECT()
        _ecrans.GetWindowRect(hwnd, ctypes.byref(r))
        info = _INFO_ECRAN()
        info.cbSize = ctypes.sizeof(_INFO_ECRAN)
        if not _ecrans.GetMonitorInfoW(_ecrans.MonitorFromWindow(hwnd, 2), ctypes.byref(info)):
            return False
        m = info.rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom
    except Exception:
        return False


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _melange(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t, c1[2] + (c2[2] - c1[2]) * t)


def _melange_ent(c1, c2, t):
    """Le même mélange, en nombres entiers (ce que pygame attend pour dessiner)."""
    return tuple(int(v) for v in _melange(c1, c2, t))


def _soleil(lat, lon, jour_annee, decalage_minutes):
    """Heures (en minutes, heure locale) du lever et du coucher du soleil : formule de la NOAA."""
    g = 2 * math.pi / 365 * (jour_annee - 1)
    equation = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g)
                         - 0.014615 * math.cos(2 * g) - 0.040849 * math.sin(2 * g))
    decl = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
            + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    phi = math.radians(lat)
    x = math.cos(math.radians(90.833)) / (math.cos(phi) * math.cos(decl)) - math.tan(phi) * math.tan(decl)
    angle = math.degrees(math.acos(max(-1.0, min(1.0, x))))
    lever = 720 - 4 * (lon + angle) - equation + decalage_minutes
    coucher = 720 - 4 * (lon - angle) - equation + decalage_minutes
    return lever, coucher


def _presse_papiers():
    """Le texte du presse-papiers (pour Ctrl+V dans la fenêtre de discussion), ou « » s'il n'y en a pas."""
    u, k = ctypes.WinDLL("user32"), ctypes.WinDLL("kernel32")     # copies à part : types déclarés ici seulement
    u.GetClipboardData.restype = ctypes.c_void_p
    k.GlobalLock.restype = ctypes.c_void_p
    k.GlobalLock.argtypes = k.GlobalUnlock.argtypes = [ctypes.c_void_p]
    texte = ""
    try:
        if not u.OpenClipboard(None):
            return ""
        try:
            poignee = u.GetClipboardData(13)               # 13 : texte Unicode
            if poignee:
                adresse = k.GlobalLock(poignee)
                if adresse:
                    try:
                        texte = ctypes.wstring_at(adresse)
                    finally:
                        k.GlobalUnlock(poignee)
        finally:
            u.CloseClipboard()
    except Exception as erreur:
        print("Presse-papiers :", erreur)
    return texte[:LONGUEUR_SAISIE]


def _degrade(couleurs, position):
    """Couleur à la « position » (0 à len(couleurs), en boucle) d'un dégradé circulaire."""
    n = len(couleurs)
    position %= n
    i = int(position)
    return _melange(couleurs[i], couleurs[(i + 1) % n], position - i)


class Affichage:
    def __init__(self, source):
        """source : le module jarvis_reacteur (réglages, état et texte à afficher)."""
        global actuel
        actuel = self
        self.src = source
        try:
            dpi = user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        self._s0 = dpi / 96.0
        self._echelle = 1.0                        # 3 en mode enfant : le réacteur se voit de loin
        self._echelle_vue = 0.0
        self._calculer_tailles(1.0)
        s = self.s

        largeur_ecran, hauteur_ecran = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = largeur_ecran - self.w - int(source.MARGE_DROITE * s)
        y = hauteur_ecran - self.h - int(source.MARGE_BAS * s)
        migre = False
        try:                                  # dernière position choisie à la souris
            with open(source.FICHIER_POSITION, encoding="utf-8") as f:
                valeurs = [int(v) for v in f.read().split(",")]
            px, py = valeurs[0], valeurs[1]
            if len(valeurs) < 3:              # position retenue avant la fenêtre de discussion : la fenêtre
                py -= self.haut               # a grandi vers le haut, le réacteur reste où il était
                migre = True
            # Une position qui dépasse un peu du bord est ramenée dans l'écran (avant, elle était ignorée)
            x = max(0, min(largeur_ecran - self.w, px))
            y = max(0, min(hauteur_ecran - self.h, py))
        except (OSError, ValueError, IndexError):
            pass

        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
        os.environ.setdefault("SDL_MOUSE_FOCUS_CLICKTHROUGH", "1")   # le premier clic compte (pas seulement le deuxième)
        pygame.display.init()
        pygame.font.init()
        pygame.key.set_repeat(400, 35)        # une touche maintenue se répète (effacer)
        self.ecran = pygame.display.set_mode((self.w, self.h), pygame.NOFRAME)
        pygame.display.set_caption("Jarvis")
        self.hwnd = pygame.display.get_wm_info()["window"]
        # Fenêtre transparente autour du dessin, sans bouton dans la barre des tâches
        user32.ShowWindow(self.hwnd, 0)
        style = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, style | 0x80000 | 0x80)
        user32.SetLayeredWindowAttributes(self.hwnd, CLE[0] | CLE[1] << 8 | CLE[2] << 16, 0, 1)
        user32.ShowWindow(self.hwnd, 8)
        self._premier_plan()
        try:                                  # la frappe au clavier est prête dès le lancement
            pygame.key.start_text_input()
        except Exception:
            pass

        self.fond = _rgb(source.FOND)
        self.couleur = _rgb(source.ETATS["demarrage"][0])
        self.angle = 0.0
        self.t0 = self.t_prec = time.time()
        self._voix = self._micro = 0.0
        self._amp = 0.1
        self._dernier_actif = 0.0
        self._dernier_premier_plan = time.time()
        self.glisse = None
        self._etat_prec = None
        self._forme = 1.0                          # 1 = taille normale, 0 = mode discret
        self._alerte = -100.0                      # moment où le dernier rappel a sonné
        self._fermeture = None                     # moment où l'arrêt a été demandé
        self._sortie = 0                           # code de sortie à l'arrêt
        self._quitter = True
        self._rappel = None                        # prochain rappel (quand, début, message)
        self._rappel_lu = 0.0
        self._onde = -10.0                         # moment du dernier réveil (onde qui part du cœur)
        self._niveaux = np.zeros(NB_GRADUATIONS)   # hauteur lissée de chaque graduation
        self._jauges = {}                          # valeurs lissées des jauges
        self._musique = 0.0                        # niveau lissé du son du PC (le réacteur danse)
        self._regard = (0.0, 0.0)                  # décalage du cœur vers la souris
        self._fete, self._fete_vue = None, None    # animation de minuit ou d'anniversaire en cours
        self._vigilance_vue, self._vigilance = None, None    # alerte météo animée
        self._jour = time.strftime("%Y-%m-%d")
        self._nuit_calcul, self._nuit = 0.0, False
        ang = np.arange(NB_GRADUATIONS) * (2 * math.pi / NB_GRADUATIONS)
        self._grad_cos, self._grad_sin = np.cos(ang), np.sin(ang)
        # Chaque graduation suit une bande du spectre : graves en bas, aigus en haut, en miroir gauche/droite
        haut = (np.arange(NB_GRADUATIONS) + NB_GRADUATIONS // 4) % NB_GRADUATIONS
        self._grad_bande = np.abs(haut - NB_GRADUATIONS / 2) / (NB_GRADUATIONS / 2)   # 0 = haut, 1 = bas
        petit = max(8, self.d // 4)
        self._halo_petit = (petit, petit)
        self._zone = pygame.Rect(self.w // 2 - self.d // 2, self.yr, self.d, self.d)
        self._masque = pygame.Surface((self.d, self.d))
        self._masque.set_colorkey((255, 0, 255))
        self._polices()
        self._saisie = None                        # la demande en cours de frappe (None : on n'écrit pas)
        self._menu_ouvert = None                   # menu du clic droit (None : fermé)
        self._saisie_touche = 0.0                  # moment de la dernière frappe
        self._zone_discussion = None               # rectangle de la fenêtre de discussion (pour le clic)
        self._fin_active = 0.0                     # dernier moment où Jarvis écoutait, réfléchissait ou parlait
        self._lignes = (None, [])                  # dernier texte mis en lignes (pour ne pas le recalculer)

        n = self.n = 160
        th = np.arange(n + 1) * (2 * math.pi / n)
        self.cos_t, self.sin_t = np.cos(th), np.sin(th)
        self.harm = {k: (np.sin(k * th), np.cos(k * th)) for k in (2, 3, 4, 5, 7)}
        self.idx_points = [np.arange(f % 6, n, 6) for f in range(source.NB_FILAMENTS)]
        self.poussiere = [{"a": random.uniform(0, 2 * math.pi), "r": random.uniform(0.15, 0.5),
                           "v": random.uniform(0.6, 1.4), "p": random.uniform(0, 6.3)}
                          for _ in range(source.NB_POUSSIERE)]

        self._historique = {}                       # jauge -> les valeurs des dernières minutes (petite courbe)
        self._histo_quand = 0.0
        self.meteo = None                           # (température, code du ciel) de la ville réglée
        threading.Thread(target=self._suivre_meteo, daemon=True).start()
        self._zone_compacte = None                  # rectangle du petit panneau (pour le survol de la souris)
        self._cercle = getattr(pygame.draw, "aacircle", pygame.draw.circle)
        if migre:
            self.enregistrer_position()

    def _calculer_tailles(self, echelle):
        """Tailles de la fenêtre pour cette échelle (1 = normale, 3 = mode enfant)."""
        source = self.src
        s = self.s = self._s0 * echelle
        self.d = int(source.TAILLE * s)
        self.m = int(4 * s)
        # Le panneau est un peu plus large que le réacteur, pour des jauges bien lisibles
        self.w = self.d + 2 * self.m + int((2 * ELARGISSEMENT if source.AFFICHER_SYSTEME else 0) * s)
        # De haut en bas : la fenêtre de discussion, le réacteur, puis le panneau (état, heure et jauges)
        self.haut = int(HAUTEUR_DISCUSSION * s)
        self.yr = self.haut + self.m                       # haut du réacteur
        self.h = self.haut + self.d + 2 * self.m + int((66 if source.AFFICHER_SYSTEME else 30) * s)

    def _polices(self):
        s = self.s
        self.police_discussion = pygame.font.SysFont("segoeui", int(12 * s))
        self._lignes = (None, [])
        self.police_titre = pygame.font.SysFont("segoeui", int(13.5 * s), bold=True)
        self.police_jauge = pygame.font.SysFont("consolas", int(11 * s), bold=True)
        self.police_jauge_petite = pygame.font.SysFont("consolas", int(11 * s), bold=True)
        self.police_compacte = pygame.font.SysFont("consolas", max(9, int(10 * s)), bold=True)
        self.police_texte = pygame.font.SysFont("segoeui", int(11 * s))
        self._textes = {}

    def _echelle_voulue(self):
        """3 quand le mode enfant est actif (profil enfant ou « active le mode enfant »), sinon 1."""
        if not GRAND_EN_MODE_ENFANT:
            return 1.0
        maintenant = time.time()
        if maintenant - self._echelle_vue < 1.0:
            return self._echelle
        self._echelle_vue = maintenant
        try:
            import jarvis_enfant
            voulue = ECHELLE_ENFANT if jarvis_enfant.actif() else 1.0
        except Exception:
            return self._echelle
        # jamais plus grand que l'écran
        hauteur_ecran = user32.GetSystemMetrics(1)
        hauteur_normale = self.h / self._echelle
        return max(1.0, min(voulue, 0.92 * hauteur_ecran / max(1.0, hauteur_normale)))

    def _changer_echelle(self, echelle):
        """Agrandit ou réduit le réacteur en gardant son centre et son bas au même endroit ; en revenant à la
        taille normale, il reprend exactement sa place d'avant."""
        ancien_x, ancien_y = self._position()
        centre, bas = ancien_x + self.w / 2, ancien_y + self.h
        if self._echelle == 1.0 and echelle != 1.0:
            self._place_normale = (ancien_x, ancien_y)
        self._echelle = echelle
        self._calculer_tailles(echelle)
        largeur_ecran, hauteur_ecran = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = int(max(0, min(largeur_ecran - self.w, centre - self.w / 2)))
        y = int(max(0, min(hauteur_ecran - self.h, bas - self.h)))
        if echelle == 1.0 and getattr(self, "_place_normale", None):
            x, y = self._place_normale
            self._place_normale = None
        self.ecran = pygame.display.set_mode((self.w, self.h), pygame.NOFRAME)
        style = user32.GetWindowLongW(self.hwnd, -20)
        user32.SetWindowLongW(self.hwnd, -20, style | 0x80000 | 0x80)
        user32.SetLayeredWindowAttributes(self.hwnd, CLE[0] | CLE[1] << 8 | CLE[2] << 16, 0, 1)
        user32.SetWindowPos(self.hwnd, PREMIER_PLAN, x, y, 0, 0, 0x0001 | 0x0010)
        petit = max(8, self.d // 4)
        self._halo_petit = (petit, petit)
        self._zone = pygame.Rect(self.w // 2 - self.d // 2, self.yr, self.d, self.d)
        self._masque = pygame.Surface((self.d, self.d))
        self._masque.set_colorkey((255, 0, 255))
        self._polices()

    # ---------- Fenêtre ----------

    def enregistrer_position(self):
        """Retient l'emplacement de la fenêtre pour les prochains démarrages (le « 2 » dit que la hauteur
        compte déjà la fenêtre de discussion)."""
        try:
            with open(self.src.FICHIER_POSITION, "w", encoding="utf-8") as f:
                f.write("%d,%d,2" % self._position())
        except OSError:
            pass

    def _premier_plan(self):
        # Une vidéo ou un jeu en plein écran : le réacteur passe derrière, et revient devant ensuite
        plein = plein_ecran(self.hwnd)
        if plein != getattr(self, "_derriere", False):
            self._derriere = plein
            print("(Plein écran : le réacteur passe derrière.)" if plein else "(Fin du plein écran : le réacteur revient.)")
        # Sur le Bureau (réglage par défaut) : derrière toutes les fenêtres, sauf pendant qu'on s'en sert
        # (on écrit, le menu du clic droit est ouvert, on le déplace)
        en_main = (getattr(self, "_saisie", None) is not None or getattr(self, "_menu_ouvert", None) is not None
                   or getattr(self, "glisse", None) is not None)
        if plein or not (TOUJOURS_DEVANT or en_main):
            user32.SetWindowPos(self.hwnd, PLUS_PREMIER_PLAN, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            user32.SetWindowPos(self.hwnd, ctypes.c_void_p(1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)   # tout en dessous
            return
        user32.SetWindowPos(self.hwnd, PREMIER_PLAN, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

    def _position(self):
        r = RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.gauche, r.haut

    def _curseur(self):
        p = POINT()
        user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    # ---------- Menu du clic droit, dessiné dans la fenêtre aux couleurs du réacteur ----------

    def _entrees_menu(self):
        coupe = jarvis_claude.micro_coupe
        return [(3, "", "Réglages"),
                (1, "", "Nouvelle conversation"),
                (4, "" if coupe else "", "Rallumer le micro" if coupe else "Couper le micro"),
                (None, None, None),
                (5, "\ue7ba", "Signaler un problème"),
                (6, "\uea80", "Proposer une amélioration"),
                (None, None, None),
                (2, "", "Arrêter Jarvis")]

    def _ouvrir_menu(self, pos):
        s = self.s
        largeur, haut_ligne = 214 * s, 30 * s
        hauteur = 34 * s + sum(9 * s if i is None else haut_ligne for i, _, _ in self._entrees_menu()) + 8 * s
        x = max(4 * s, min(pos[0], self.w - largeur - 4 * s))
        y = max(4 * s, min(pos[1], self.h - hauteur - 4 * s))
        self._menu_ouvert = {"rect": pygame.Rect(int(x), int(y), int(largeur), int(hauteur)), "depuis": time.time(),
                             "zones": []}
        user32.SetForegroundWindow(self.hwnd)

    def _clic_menu(self, pos):
        """Un clic pendant que le menu est ouvert : choisit une entrée, ou referme le menu."""
        menu, self._menu_ouvert = self._menu_ouvert, None
        for choix, zone in menu["zones"]:
            if zone.collidepoint(pos):
                self._menu(choix)
                return

    def _dessiner_menu(self, surf, teinte, blanc):
        menu = getattr(self, "_menu_ouvert", None)
        if menu is None:
            return
        s = self.s
        # le menu se referme si on passe à une autre fenêtre
        if (time.time() - menu["depuis"] > 0.4
                and (user32.GetForegroundWindow() & 0xFFFFFFFF) != (self.hwnd & 0xFFFFFFFF)):
            self._menu_ouvert = None
            return
        apparition = min(1.0, (time.time() - menu["depuis"]) / 0.15)
        r = menu["rect"].copy()
        r.y += int((1 - apparition) * 8 * s)
        if not hasattr(self, "police_icone"):
            self.police_icone = pygame.font.SysFont("segoemdl2assets", int(12 * s))
            self.police_menu = pygame.font.SysFont("segoeui", int(11.5 * s))
            self.police_menu_titre = pygame.font.SysFont("segoeui", int(9.5 * s), bold=True)
        arrondi = int(10 * s)
        pygame.draw.rect(surf, tuple(int(c) for c in _melange(self.fond, (0, 0, 0), 0.3)), r.move(0, int(3 * s)),
                         border_radius=arrondi)                                          # ombre
        pygame.draw.rect(surf, self.fond, r, border_radius=arrondi)
        pygame.draw.rect(surf, teinte(0.45), r, max(1, int(1.2 * s)), border_radius=arrondi)
        # en-tête : « JARVIS » et la version, avec un petit trait lumineux
        titre = self._texte(self.police_menu_titre, f"JARVIS  ·  VERSION {jarvis_claude.VERSION}", teinte(0.75))
        surf.blit(titre, (r.x + 14 * s, r.y + 10 * s))
        pygame.draw.line(surf, teinte(0.9), (r.x + 14 * s, r.y + 27 * s), (r.x + 44 * s, r.y + 27 * s), max(1, int(2 * s)))
        pygame.draw.line(surf, teinte(0.18), (r.x + 46 * s, r.y + 27 * s), (r.right - 14 * s, r.y + 27 * s), 1)
        souris = pygame.mouse.get_pos()
        y = r.y + 34 * s
        zones = []
        for choix, icone, libelle in self._entrees_menu():
            if choix is None:
                pygame.draw.line(surf, teinte(0.18), (r.x + 14 * s, y + 4 * s), (r.right - 14 * s, y + 4 * s), 1)
                y += 9 * s
                continue
            zone = pygame.Rect(int(r.x + 6 * s), int(y), int(r.width - 12 * s), int(30 * s))
            zones.append((choix, zone))
            survol = zone.collidepoint(souris)
            rouge = choix == 2
            if survol:
                fond_survol = (120, 30, 40) if rouge else teinte(0.22)
                pygame.draw.rect(surf, fond_survol, zone, border_radius=int(6 * s))
                pygame.draw.line(surf, (255, 90, 90) if rouge else teinte(1.0), (zone.x + 2 * s, zone.y + 8 * s),
                                 (zone.x + 2 * s, zone.bottom - 8 * s), max(2, int(2.5 * s)))
            couleur = (255, 130, 130) if rouge else (blanc if survol else teinte(0.85, blanc))
            ic = self._texte(self.police_icone, icone, (255, 110, 110) if rouge else teinte(1.0 if survol else 0.8))
            surf.blit(ic, ic.get_rect(center=(zone.x + 20 * s, zone.centery)))
            lib = self._texte(self.police_menu, libelle, couleur)
            surf.blit(lib, lib.get_rect(midleft=(zone.x + 38 * s, zone.centery)))
            y += 30 * s
        menu["zones"] = zones

    def _menu(self, choix):
        """Ce qu'on a choisi dans le menu du clic droit."""
        if choix == 3:
            try:
                import jarvis_reglages_ui
                jarvis_reglages_ui.ouvrir()
            except Exception as erreur:
                print("Réglages indisponibles :", erreur)
        elif choix == 1:
            jarvis_claude.oublier_conversation()
        elif choix in (5, 6):
            try:
                import jarvis_rapports_ui
                jarvis_rapports_ui.ouvrir_message("probleme" if choix == 5 else "idee")
            except Exception as erreur:
                print("Fenêtre de message indisponible :", erreur)
        elif choix == 4:
            jarvis_claude.micro_coupe = not jarvis_claude.micro_coupe
            print("(Micro coupé par le menu du réacteur.)" if jarvis_claude.micro_coupe else "(Micro rallumé par le menu.)")
        elif choix == 2:
            print("(Arrêt demandé par le menu du réacteur.)")
            try:
                jarvis_claude.remonter_son()       # un son baissé pendant une écoute ne reste pas baissé
            except Exception:
                pass
            self.fermer(0)

    def fermer(self, code=0, quitter=True):
        """Le réacteur se referme. Avec quitter=True, Jarvis s'arrête ensuite avec ce code de sortie
        (sinon c'est celui qui a demandé la fermeture qui s'en charge, par exemple « redémarre-toi »)."""
        if self._fermeture is None:
            self._fermeture, self._sortie, self._quitter = time.time(), code, quitter

    def _survol(self):
        """Vrai si la souris est sur le réacteur (ou sur toute la fenêtre quand il est déployé)."""
        x, y = self._curseur()
        fx, fy = self._position()
        if self._forme > 0.5:
            return fx <= x <= fx + self.w and fy <= y <= fy + self.h
        rayon = self.d / 2 * (TAILLE_DISCRETE + 0.1)
        zone = self._zone_compacte
        if zone is not None and zone.collidepoint(x - fx, y - fy):
            return True
        return math.hypot(x - (fx + self.w / 2), y - (fy + self.yr + self.d / 2)) <= rayon

    # ---------- Écrire à Jarvis ----------

    def _ouvrir_saisie(self):
        """Un clic dans la fenêtre de discussion : on peut écrire sa demande."""
        if self._saisie is None:
            self._saisie = ""
            print("(Fenêtre de discussion : clic, prête pour une demande écrite.)")
        self._saisie_touche = self._saisie_clavier = time.time()
        try:
            user32.SetForegroundWindow(self.hwnd)          # les touches du clavier arrivent ici
            # La toute première fois que la fenêtre passait au premier plan, Windows ne lui donnait pas le
            # clavier pour de bon : les touches arrivaient, mais pas les lettres. On le lui donne nous-mêmes.
            _clavier.SetFocus(ctypes.c_void_p(self.hwnd))
        except Exception as erreur:
            print("Fenêtre de discussion (clavier) :", erreur)

    def _fermer_saisie(self):
        self._saisie = None

    def _envoyer_saisie(self):
        """Entrée : la phrase part chez Jarvis. Elle reste affichée jusqu'à sa réponse, qui la remplace."""
        texte = " ".join((self._saisie or "").split())
        self._saisie = ""
        self._saisie_touche = time.time()
        if not texte:
            return
        self._message(texte)
        try:
            jarvis_claude.ecrire(texte)
        except Exception as erreur:
            print("Demande écrite :", erreur)

    def _touche(self, ev):
        """Une touche pendant qu'on écrit : Entrée envoie, Échap annule, Retour arrière efface, Ctrl+V colle."""
        self._saisie_touche = time.time()
        controle = bool(ev.mod & pygame.KMOD_CTRL) and not ev.mod & pygame.KMOD_ALT     # AltGr = Ctrl+Alt
        if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self._envoyer_saisie()
        elif ev.key == pygame.K_ESCAPE:
            self._fermer_saisie()
        elif ev.key == pygame.K_BACKSPACE:
            if controle:                                   # Ctrl + Retour arrière : le dernier mot
                self._saisie = re.sub(r"\S+\s*$", "", self._saisie)
            else:
                self._saisie = self._saisie[:-1]
        elif ev.key == pygame.K_v and controle:
            colle = " ".join(_presse_papiers().split())
            self._saisie = (self._saisie + colle)[:LONGUEUR_SAISIE]

    def _evenements(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                os._exit(0)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1 and getattr(self, "_menu_ouvert", None):
                self._clic_menu(ev.pos)                    # menu ouvert : on choisit, ou on le referme
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and getattr(self, "_menu_ouvert", None):
                self._menu_ouvert = None
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                zone = self._zone_discussion
                if zone is not None and zone.collidepoint(ev.pos):
                    self._ouvrir_saisie()                  # clic dans la discussion : on écrit
                else:
                    if not self._saisie:
                        self._fermer_saisie()
                    self.glisse = (self._curseur(), self._position())
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.glisse:
                self.glisse = None
                self.enregistrer_position()   # la position est retenue pour les prochains démarrages
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 3:
                self._ouvrir_menu(ev.pos)
            elif ev.type == pygame.TEXTINPUT and self._saisie is not None:
                self._saisie = (self._saisie + ev.text)[:LONGUEUR_SAISIE]
                self._saisie_touche = time.time()
            elif ev.type == pygame.KEYDOWN and self._saisie is not None:
                self._touche(ev)
        if self._saisie is not None:
            maintenant = time.time()
            # On a cliqué ailleurs sans rien écrire : la saisie se referme (après 2 secondes sans le clavier,
            # pour ne pas la refermer sur un simple aller-retour entre deux fenêtres).
            if (user32.GetForegroundWindow() & 0xFFFFFFFF) == (self.hwnd & 0xFFFFFFFF):
                self._saisie_clavier = maintenant
            elif not self._saisie and maintenant - self._saisie_clavier > 2:
                self._fermer_saisie()
            # Une demande commencée puis laissée de côté est abandonnée au bout d'une minute
            if self._saisie is not None and maintenant - self._saisie_touche > ABANDON_SAISIE:
                self._fermer_saisie()
        if self.glisse:
            if not pygame.mouse.get_pressed()[0]:
                self.glisse = None
            else:
                (cx0, cy0), (fx0, fy0) = self.glisse
                cx, cy = self._curseur()
                user32.SetWindowPos(self.hwnd, 0, fx0 + cx - cx0, fy0 + cy - cy0, 0, 0,
                                    0x0001 | 0x0004 | 0x0010)

    # ---------- Dessin ----------

    def _texte(self, police, texte, couleur):
        cle = (id(police), texte, couleur)
        image = self._textes.get(cle)
        if image is None:
            if len(self._textes) > 400:
                self._textes.clear()
            image = self._textes[cle] = police.render(texte, True, couleur)
        return image

    def _filament(self, cx, cy, rayon, amp, harmoniques):
        onde = 0.0
        for k, poids, ph in harmoniques:
            sk, ck = self.harm[k]
            onde = onde + sk * (poids * math.cos(ph)) + ck * (poids * math.sin(ph))
        r = rayon * (1 + amp * onde)
        return np.column_stack((cx + r * self.cos_t, cy + r * self.sin_t))

    def image(self):
        voulue = self._echelle_voulue()
        if abs(voulue - self._echelle) > 0.01:
            try:
                self._changer_echelle(voulue)
            except Exception as erreur:
                print("Taille du réacteur :", erreur)
        src, s, surf = self.src, self.s, self.ecran
        e = src.etat_actuel
        maintenant = time.time()
        dt = min(0.25, maintenant - self.t_prec)
        self.t_prec = maintenant
        t = maintenant - self.t0
        # Un rappel sonne : l'alerte dure au moins 5 secondes, même si Jarvis a fini de parler
        if e == "rappel" and self._etat_prec != "rappel":
            self._alerte = maintenant
        alerte = maintenant - self._alerte
        if FETES:
            self._detecter_fete(maintenant)
        vigilance = jarvis_vigilance.animation
        if vigilance and maintenant - vigilance[0] >= DUREE_VIGILANCE:
            vigilance = None
        if vigilance and vigilance[0] != self._vigilance_vue:
            self._vigilance_vue = vigilance[0]
            self._message("Vigilance " + jarvis_vigilance.COULEURS.get(vigilance[1], "") + " : "
                          + ", ".join(vigilance[2]))
        self._vigilance = vigilance
        if alerte < DUREE_ALERTE and e in ("veille", "pause", "reponse"):
            e = "rappel"
        self._en_alerte = e == "rappel"
        cible, vitesse, _, titre = src.ETATS[e]
        cible = _rgb(cible)
        palette = getattr(src, "COULEURS_VEILLE", None)
        if e == "veille" and palette:                  # veille : les couleurs défilent lentement
            cible = _degrade([_rgb(c) for c in palette], t / max(1.0, getattr(src, "CYCLE_VEILLE", 12)))
        if vigilance and e in ("veille", "pause", "reponse", "rappel"):    # alerte météo : couleur de la vigilance
            cible = COULEURS_VIGILANCE.get(vigilance[1], cible)
            if e in ("veille", "pause"):
                titre = "Alerte météo"
        self._micro_coupe = bool(getattr(jarvis_claude, "micro_coupe", False)) and e in ("veille", "pause")
        if self._micro_coupe:
            titre = "Micro coupé"
        self.couleur = _melange(self.couleur, cible, 1 - math.exp(-dt * 4))
        base = self.couleur
        if e == "erreur":
            base = _melange(base, self.fond, 0.45 + 0.45 * math.sin(t * 6))
        fond = self.fond
        blanc = _melange(base, (255, 255, 255), 0.55)

        def teinte(force, vers=None):
            r, g, b = _melange(fond, vers or base, max(0.0, min(1.0, force)))
            return int(r), int(g), int(b)

        # L'anneau suit le vrai son : la voix de Jarvis quand il répond, le micro quand il écoute
        self._voix += (min(1.0, jarvis_voix.niveau * 1.6) - self._voix) * (1 - math.exp(-dt * 18))
        self._micro += (min(1.0, jarvis_claude.niveau_micro * 5) - self._micro) * (1 - math.exp(-dt * 10))
        voix = 0.0
        if e == "reponse":
            voix = self._voix
            amplitude, eclat = 0.08 + 0.24 * voix, 0.85 + 0.15 * voix
        elif e == "ecoute":
            amplitude, eclat = 0.11 + 0.16 * self._micro, 1.0
        elif e == "traitement":
            amplitude, eclat = 0.16, 1.0
        elif e == "erreur":
            amplitude, eclat = 0.20, 0.95
        elif e == "rappel":
            # la voix de Jarvis anime aussi l'anneau pendant qu'il annonce le rappel
            amplitude, eclat = 0.14 + 0.2 * self._voix + 0.05 * math.sin(t * 8), 1.0
        elif e == "veille" and getattr(src, "COULEURS_VEILLE", None):
            amplitude, eclat = 0.10, 0.95          # couleurs Vice City : plus vives qu'une veille ordinaire
        else:
            amplitude, eclat = 0.10, 0.8
        # Le son du PC (musique, vidéo) fait danser le réacteur en veille
        brut = min(1.0, jarvis_claude.niveau_musique * 1.4) if DANSE_MUSIQUE and e in ("veille", "pause") else 0.0
        self._musique += (brut - self._musique) * (1 - math.exp(-dt * (22 if brut > self._musique else 5)))
        if self._musique > 0.02:
            amplitude += FORCE_DANSE * self._musique
            eclat = min(1.0, eclat + 0.25 * self._musique)
        # La nuit, en veille, il se fait plus doux
        if DOUX_LA_NUIT and e in ("veille", "pause") and self._est_nuit(maintenant):
            eclat *= DOUCEUR_NUIT
        if jarvis_famille.dodo["actif"] and e in ("veille", "pause"):     # l'enfant dort : lumière très douce
            eclat *= 0.4
            amplitude *= 0.5
        self._amp += (amplitude - self._amp) * (1 - math.exp(-dt * 14))
        amplitude = self._amp
        self.angle += vitesse * 0.6 * dt
        ph = self.angle

        if src.etat_actuel != self._etat_prec:
            e_vrai = src.etat_actuel
            if e_vrai == "ecoute" or (e_vrai == "reponse" and self._etat_prec != "traitement"):
                self._onde = maintenant
            if e_vrai == "arret":
                self.fermer(quitter=False)
            # Jarvis se remet à écouter : l'ancienne réponse s'efface (un texte tout neuf, lui, reste)
            if (e_vrai == "ecoute" and src.texte_actuel and not getattr(src, "texte_en_direct", False)
                    and maintenant - src.texte_depuis > 0.5):
                src.texte_actuel = ""
            self._etat_prec = e_vrai

        # Le texte de la discussion reste tant que Jarvis écoute, réfléchit ou parle, puis encore un moment
        if src.etat_actuel not in ("veille", "pause", "demarrage"):
            self._fin_active = maintenant
        self._reste_texte = max(src.texte_depuis + getattr(src, "duree_texte", src.DUREE_TEXTE),
                                self._fin_active + 8) - maintenant if src.texte_actuel else 0.0
        if src.texte_actuel and self._reste_texte <= 0:
            src.texte_actuel = ""
        ecrit = self._saisie is not None

        # Taille du réacteur : discret en veille, normal dès qu'il se passe quelque chose
        en_fete = self._fete is not None and maintenant - self._fete[0] < DUREE_FETE
        actif = (e not in ("veille", "pause") or self.glisse is not None or alerte < DUREE_ALERTE or en_fete
                 or self._vigilance is not None or ecrit
                 or getattr(self, "_menu_ouvert", None) is not None
                 or self._reste_texte > 0)
        if actif:
            self._dernier_eveil = maintenant
        deploye = (not MODE_DISCRET or actif or maintenant - getattr(self, "_dernier_eveil", maintenant) < DELAI_DISCRET
                   or self._survol())
        self._forme += ((1.0 if deploye else 0.0) - self._forme) * (1 - math.exp(-dt * (9 if deploye else 4)))
        k = TAILLE_DISCRETE + (1 - TAILLE_DISCRETE) * self._forme
        naissance = min(1.0, t / DUREE_NAISSANCE)
        # Au lancement, le réacteur prend vite sa taille, puis s'allume couche par couche :
        # la couronne, le disque, les filaments du bord, ceux de l'intérieur, et enfin le cœur
        k *= 1 - (1 - min(1.0, t / (DUREE_NAISSANCE * 0.35))) ** 3

        def couche(debut, fin):
            if naissance >= 1:
                return 1.0
            x = max(0.0, min(1.0, (naissance - debut) / (fin - debut)))
            return x * x * (3 - 2 * x)
        self._naissance_couronne = couche(0.0, 0.35)
        if naissance < 1 and naissance >= 0.72 and not getattr(self, "_coeur_allume", False):
            self._coeur_allume = True
            self._onde = maintenant                        # le cœur s'allume : une onde part vers le bord
        if self._fermeture is not None:                    # à l'arrêt, il se referme
            k *= max(0.0, 1 - (maintenant - self._fermeture) / DUREE_FERMETURE) ** 2
        self._naissance = naissance
        self._k = k
        s = s * (0.55 + 0.45 * min(1.0, k))                # traits et points un peu plus fins quand il est petit

        cx, cy = self.w / 2, self.yr + self.d / 2
        self._zone_discussion = None
        if k < 0.03:                                       # trop petit pour être dessiné
            surf.fill(CLE)
            return
        Rext = (self.d / 2 - 2 * self.s) * k   # bord de la couronne de graduations
        R = Rext * 0.83                    # le réacteur lui-même
        R0 = R * 0.68
        ligne, aaligne, cercle = pygame.draw.lines, pygame.draw.aalines, self._cercle
        gx, gy = self._suivre_regard(cx, cy, R, dt)    # le cœur se tourne un peu vers la souris
        # Réacteur rétréci (veille) : un point sur deux suffit à tracer les filaments, les courbes restent
        # aussi lisses à cette taille et le dessin coûte moins cher
        fin = 2 if self._k < 0.6 else 1
        surf.fill(CLE)

        # Fond : le contour du disque ondule lui aussi (il n'est plus un cercle fixe),
        # puis dégradé sombre, plus lumineux au centre
        ondulation = 0.022 + amplitude * 0.12
        contour = self._filament(cx, cy, R * 0.975, ondulation,
                                 [(4, 0.6, ph * 0.7), (7, 0.4, -ph * 1.1)])
        c_fond, c_bord = couche(0.12, 0.4), couche(0.3, 0.55)
        c_fil, c_coeur = couche(0.45, 0.75), couche(0.68, 0.95)
        pygame.draw.polygon(surf, teinte(0.03 * c_fond), contour)
        aaligne(surf, teinte(0.22 * eclat * c_fond), True, contour)
        for k in range(1, 7):
            pygame.draw.circle(surf, teinte((0.03 + k * 0.022 * eclat) * c_fond), (cx, cy), R * (7 - k) / 7)

        # Anneau extérieur : fins filaments qui ondulent au bord du cercle
        for f in range(src.NB_FILAMENTS_BORD if c_bord > 0 else 0):
            phi = f * 2.2
            pts = self._filament(cx, cy, R * (0.925 - 0.014 * f), ondulation,
                                 [(4, 0.6, ph * 0.7 + phi), (7, 0.4, -ph * 1.1 + 2 * phi)])
            ligne(surf, teinte(0.12 * eclat * c_bord), True, pts[::fin], max(2, int(3 * s)))
            aaligne(surf, teinte((0.35 + 0.2 * math.sin(t * 0.8 + phi)) * eclat * c_bord), True, pts[::fin])

        # Filaments intérieurs, qui tournent en sens inverse
        for f in range(src.NB_FILAMENTS_INT if c_fil > 0 else 0):
            phi = f * 1.9
            pts = self._filament(cx + gx * 0.5, cy + gy * 0.5, R0 * (0.50 + 0.03 * f), amplitude * 0.8,
                                 [(2, 0.6, -ph * 0.8 + phi), (4, 0.4, ph * 0.5 + 2 * phi)])
            force = (0.35 + 0.15 * math.sin(t * 0.9 + phi)) * eclat * c_fil
            ligne(surf, teinte(0.3 * force), True, pts[::fin], max(2, int(3 * s)))
            aaligne(surf, teinte(force), True, pts[::fin])

        # Poussière lumineuse à l'intérieur de l'anneau
        for q in self.poussiere:
            if e == "ecoute":
                q["r"] -= 0.12 * q["v"] * dt
                q["a"] += 0.4 * q["v"] * dt
                if q["r"] < 0.12:
                    q["r"], q["a"] = 0.52, random.uniform(0, 6.3)
            elif e == "reponse":
                q["r"] += (0.06 + 0.3 * voix) * q["v"] * dt
                q["a"] += 0.3 * q["v"] * dt
                if q["r"] > 0.52:
                    q["r"], q["a"] = 0.14, random.uniform(0, 6.3)
            elif e == "traitement":
                q["a"] += 2.2 * q["v"] * dt
            else:
                q["a"] += 0.15 * q["v"] * dt
            scint = 0.5 + 0.5 * math.sin(t * 3 * q["v"] + q["p"])
            bord = min(1.0, (0.55 - q["r"]) / 0.1, (q["r"] - 0.1) / 0.06)
            force = max(0.0, scint * bord) * eclat * c_coeur
            if force > 0.1:
                r = q["r"] * R0
                cercle(surf, teinte(force * 0.9, blanc),
                       (cx + gx * 0.4 + r * math.cos(q["a"]), cy + gy * 0.4 + r * math.sin(q["a"])),
                       (0.7 + 0.7 * scint) * s)

        # Cœur lumineux
        rc = R * (0.10 + 0.05 * voix) if e == "reponse" else R * (0.10 + 0.01 * math.sin(t * 3))
        rc *= 1 + 0.45 * self._musique                     # il bat au rythme de la musique
        rc *= 0.3 + 0.7 * c_coeur                          # au lancement, le cœur grossit en s'allumant
        xc, yc = cx + gx, cy + gy
        for k, force in ((1.6, 0.10), (1.25, 0.2), (1.0, 0.32)):
            cercle(surf, teinte(force * eclat * c_coeur), (xc, yc), rc * k)
        cercle(surf, teinte(0.8 * eclat * c_coeur), (xc, yc), rc, max(1, int(1.2 * s)))
        if e == "traitement":
            r = rc * 0.65
            for i in range(3):
                debut = ph * 6 + i * (2 * math.pi / 3)
                pygame.draw.arc(surf, teinte(1.0, blanc), (xc - r, yc - r, 2 * r, 2 * r),
                                debut, debut + math.pi / 3, max(2, int(2 * s)))
        else:
            cercle(surf, teinte(0.9 * eclat * c_coeur, blanc), (xc, yc), rc * 0.28)

        # Anneau principal de filaments, avec ses particules (au lancement, ils apparaissent l'un après l'autre)
        for f in range(src.NB_FILAMENTS if c_fil > 0 else 0):
            phi = f * 2.399
            un_par_un = 1.0 if c_fil >= 1 else max(0.0, min(1.0, c_fil * src.NB_FILAMENTS - f))
            force = (0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 0.7 + phi))) * eclat * un_par_un
            amp_f = amplitude * (0.6 + 0.8 * ((f * 0.37) % 1))
            decal = 0.05 * math.sin(phi * 1.7 + t * 0.5)
            pts = self._filament(cx, cy, R0 * (1 + decal), amp_f,
                                 [(3, 0.55, ph * 1.3 + phi), (5, 0.30, -ph * 0.9 + 2 * phi),
                                  (2, 0.15, ph * 0.6 + 3 * phi)])
            ligne(surf, teinte(0.3 * force), True, pts[::fin], max(2, int(4 * s)))
            aaligne(surf, teinte(force), True, pts[::fin])
            idx = self.idx_points[f]
            scints = 0.5 + 0.5 * np.sin(t * 4 + idx * 0.7 + phi)
            for i, scint in zip(idx.tolist(), scints.tolist()):
                if scint >= 0.35:
                    cercle(surf, teinte(force * scint, blanc), pts[i], (0.9 + 0.9 * scint) * s)

        # Rappel : des ondes partent du cœur l'une après l'autre, comme un sonar
        if self._en_alerte:
            fondu = min(1.0, (DUREE_ALERTE - alerte) / 0.8) if alerte < DUREE_ALERTE else 1.0
            for i in range(3):
                p = ((alerte if alerte < DUREE_ALERTE else t) / 1.2 + i / 3) % 1
                cercle(surf, teinte((1 - p) ** 1.3 * fondu, blanc), (cx, cy), R * (0.12 + 0.86 * p),
                       max(1, int((3 - 2 * p) * s)))

        # Onde de réveil : un cercle part du cœur et s'efface en atteignant le bord
        age = maintenant - self._onde
        if 0 <= age < 0.8:
            p = age / 0.8
            cercle(surf, teinte((1 - p) ** 1.5, blanc), (cx, cy), R * (0.12 + 0.8 * (1 - (1 - p) ** 2)),
                   max(1, int(2 * s)))

        # Minuit, anniversaire : des anneaux de toutes les couleurs et des étincelles tout autour
        if self._fete is not None and maintenant - self._fete[0] < DUREE_FETE:
            age = maintenant - self._fete[0]
            fondu = min(1.0, age / 0.4, (DUREE_FETE - age) / 1.5)
            for i, couleur in enumerate(COULEURS_FETE):
                p = (age * 0.55 + i / len(COULEURS_FETE)) % 1
                cercle(surf, teinte((1 - p) ** 1.2 * fondu, couleur), (cx, cy), R * (0.14 + 0.84 * p),
                       max(1, int(2.2 * s)))
            for j in range(28):
                a = j * (2 * math.pi / 28) + age * (1.4 if j % 2 else -1.1)
                rr = R * (0.99 + 0.06 * math.sin(age * 5 + j))
                eclair = fondu * (0.55 + 0.45 * math.sin(age * 9 + j * 1.7))
                cercle(surf, teinte(eclair, COULEURS_FETE[j % len(COULEURS_FETE)]),
                       (cx + rr * math.cos(a), cy + rr * math.sin(a)), (1.2 + 1.2 * eclair) * s)

        # Alerte météo : des ondes à la couleur de la vigilance et le symbole du phénomène au centre
        if self._vigilance is not None:
            age = maintenant - self._vigilance[0]
            fondu = min(1.0, age / 0.4, (DUREE_VIGILANCE - age) / 1.5)
            couleur = COULEURS_VIGILANCE.get(self._vigilance[1], (255, 214, 0))
            for i in range(3):
                p = (age / 1.6 + i / 3) % 1
                cercle(surf, teinte((1 - p) ** 1.3 * fondu, couleur), (cx, cy), R * (0.2 + 0.8 * p),
                       max(1, int((3 - 2 * p) * s)))
            battement = 0.75 + 0.25 * math.sin(age * 5)
            self._symbole_meteo(surf, self._vigilance[2][0], cx, cy, R * 0.34,
                                teinte(fondu * battement, _melange(couleur, (255, 255, 255), 0.25)), s)

        # Halo : le dessin est réduit puis agrandi (ce qui le rend flou) et ajouté par-dessus
        if HALO:
            zone = self._zone
            petit = pygame.transform.smoothscale(surf.subsurface(zone), self._halo_petit)
            petit.fill((150, 150, 150), special_flags=pygame.BLEND_MULT)      # halo adouci
            surf.blit(pygame.transform.smoothscale(petit, zone.size), zone, special_flags=pygame.BLEND_ADD)
            # ... puis tout ce qui dépasse du contour redevient transparent
            self._masque.fill(CLE)
            pygame.draw.polygon(self._masque, (255, 0, 255), contour - (zone.x, zone.y))
            surf.blit(self._masque, zone)
            aaligne(surf, teinte(0.22 * eclat), True, contour)
        if REFLET_REACTEUR and naissance >= 1:           # le reflet fait aussi le tour du cercle du réacteur
            self._reflet(surf, teinte, blanc, contour, time.time(), tour_fixe=TOUR_REFLET_REACTEUR)

        self._couronne(surf, teinte, blanc, eclat, e, t, dt, cx, cy, Rext)
        if getattr(self, "_micro_coupe", False) and naissance >= 1:
            self._badge_micro(surf, teinte, blanc, cx + R * 0.62, cy + R * 0.62, max(7.0, R * 0.16))
        if self._en_alerte and naissance >= 1 and self._k > 0.6:
            self._bandeau_rappel(surf, teinte, blanc, cx, cy + R * 0.58, R * 1.5)
        self._zone_compacte = None
        if self._forme > 0.5 and naissance >= 1 and self._fermeture is None:
            # le panneau et la discussion apparaissent en fondu pendant que le réacteur s'agrandit
            revele = min(1.0, (self._forme - 0.5) / 0.4)
            self._panneau(surf, teinte, blanc, eclat * revele, titre, cx, dt)
            self._discussion(surf, teinte, blanc, eclat * revele, cx, maintenant)
        elif PANNEAU_COMPACT and src.AFFICHER_SYSTEME and naissance >= 1 and self._fermeture is None:
            # mode discret : un petit panneau juste sous le réacteur, avec seulement les jauges
            self._panneau_compact(surf, teinte, blanc, e, t, cx, cy + Rext + 5 * self.s, dt)
        self._dessiner_menu(surf, teinte, blanc)

    def _badge_micro(self, surf, teinte, blanc, x, y, r):
        """Micro coupé : une petite pastille avec un micro barré, posée sur le bord du réacteur."""
        pygame.draw.circle(surf, self.fond, (int(x), int(y)), int(r + 2))
        pygame.draw.circle(surf, teinte(0.9), (int(x), int(y)), int(r), max(1, int(r / 6)))
        ep = max(1, int(r / 6))
        lc, hc = r * 0.42, r * 0.78
        pygame.draw.rect(surf, blanc, pygame.Rect(int(x - lc / 2), int(y - r * 0.62), int(lc), int(hc)),
                         border_radius=int(lc / 2))
        pygame.draw.arc(surf, blanc, pygame.Rect(int(x - r * 0.5), int(y - r * 0.45), int(r * 1.0), int(r * 0.85)),
                        math.pi, 2 * math.pi, ep)
        pygame.draw.line(surf, blanc, (x, y + r * 0.4), (x, y + r * 0.62), ep)
        pygame.draw.line(surf, blanc, (x - r * 0.25, y + r * 0.62), (x + r * 0.25, y + r * 0.62), ep)
        pygame.draw.line(surf, (235, 80, 80), (x - r * 0.55, y - r * 0.55), (x + r * 0.55, y + r * 0.55), ep + 1)

    def _bandeau_rappel(self, surf, teinte, blanc, cx, cy, largeur_max):
        """Pendant qu'un rappel sonne : une pastille avec son texte, posée sur le bas du réacteur."""
        texte = (getattr(self.src, "texte_actuel", "") or "").strip()
        if not texte:
            return
        police = self.police_titre
        while len(texte) > 4 and police.size(texte)[0] > largeur_max - 20 * self.s:
            texte = texte[:-2].rstrip() + "…" if not texte.endswith("…") else texte[:-3].rstrip() + "…"
        image = self._texte(police, texte, blanc)
        lw, lh = image.get_width() + 18 * self.s, image.get_height() + 6 * self.s
        boite = pygame.Rect(int(cx - lw / 2), int(cy - lh / 2), int(lw), int(lh))
        clignote = 0.6 + 0.4 * math.sin(time.time() * 5)
        pygame.draw.rect(surf, self.fond, boite, border_radius=int(lh / 2))
        pygame.draw.rect(surf, teinte(clignote), boite, max(1, int(1.5 * self.s)), border_radius=int(lh / 2))
        surf.blit(image, image.get_rect(center=boite.center))

    @staticmethod
    def _symbole_meteo(surf, phenomene, cx, cy, r, couleur, s):
        """Un symbole simple dessiné en traits : éclair, gouttes, flocon, soleil, thermomètre, vent ou vagues."""
        epais = max(2, int(3 * s))
        if phenomene == "orages":
            pts = [(0.15, -1), (-0.45, 0.1), (0.0, 0.1), (-0.2, 1), (0.5, -0.2), (0.05, -0.2), (0.35, -1)]
            pygame.draw.polygon(surf, couleur, [(cx + x * r, cy + y * r) for x, y in pts])
        elif phenomene in ("pluie-inondation", "crues"):
            for dx, dy, k in ((-0.45, -0.15, 0.55), (0.45, -0.15, 0.55), (0.0, 0.25, 0.7)):
                x, y, t = cx + dx * r, cy + dy * r, k * r
                pygame.draw.circle(surf, couleur, (int(x), int(y + 0.35 * t)), max(2, int(0.42 * t)))
                pygame.draw.polygon(surf, couleur, [(x, y - 0.75 * t), (x - 0.41 * t, y + 0.3 * t),
                                                    (x + 0.41 * t, y + 0.3 * t)])
            if phenomene == "crues":
                pygame.draw.line(surf, couleur, (cx - r, cy + 0.95 * r), (cx + r, cy + 0.95 * r), epais)
        elif phenomene in ("neige-verglas", "grand froid", "avalanches"):
            for k in range(6):
                a = k * math.pi / 3
                x, y = cx + r * math.cos(a), cy + r * math.sin(a)
                pygame.draw.line(surf, couleur, (cx, cy), (x, y), epais)
                for c in (-1, 1):                          # les petites branches du flocon
                    mx, my = cx + 0.6 * r * math.cos(a), cy + 0.6 * r * math.sin(a)
                    b = a + c * 0.7
                    pygame.draw.line(surf, couleur, (mx, my), (mx + 0.3 * r * math.cos(b),
                                                           my + 0.3 * r * math.sin(b)), max(1, epais - 1))
        elif phenomene == "canicule":
            pygame.draw.circle(surf, couleur, (int(cx), int(cy)), max(3, int(0.45 * r)))
            for k in range(8):
                a = k * math.pi / 4
                pygame.draw.line(surf, couleur, (cx + 0.62 * r * math.cos(a), cy + 0.62 * r * math.sin(a)),
                                 (cx + r * math.cos(a), cy + r * math.sin(a)), epais)
        else:                                              # vent violent, vagues-submersion : trois ondulations
            for j, dy in enumerate((-0.5, 0.0, 0.5)):
                pts = [(cx + (i / 10 * 2 - 1) * r * (1 - 0.15 * j),
                        cy + dy * r + 0.18 * r * math.sin(i / 10 * 2 * math.pi)) for i in range(11)]
                pygame.draw.lines(surf, couleur, False, pts, epais)

    def _suivre_regard(self, cx, cy, R, dt):
        """Décalage du cœur vers la souris quand elle s'approche du réacteur (sinon il revient au centre)."""
        cible = (0.0, 0.0)
        if REGARD_SOURIS and self._k > 0.3:
            try:
                x, y = self._curseur()
                fx, fy = self._position()
                dx, dy = x - (fx + cx), y - (fy + cy)
                distance = math.hypot(dx, dy)
                if 1 < distance < R * 5:
                    force = FORCE_REGARD * R * min(1.0, distance / (1.2 * R)) * min(1.0, (R * 5 - distance) / (R * 1.5))
                    cible = (dx / distance * force, dy / distance * force)
            except Exception:
                pass
        f = 1 - math.exp(-dt * 6)
        self._regard = (self._regard[0] + (cible[0] - self._regard[0]) * f,
                        self._regard[1] + (cible[1] - self._regard[1]) * f)
        return self._regard

    def _est_nuit(self, maintenant):
        """Vrai entre le coucher et le lever du soleil chez l'utilisateur (calcul local, revu toutes les 5 min)."""
        if maintenant - self._nuit_calcul < 300:
            return self._nuit
        self._nuit_calcul = maintenant
        heure = time.localtime()
        minutes = heure.tm_hour * 60 + heure.tm_min
        try:
            _, lat, lon = jarvis_claude.jarvis_commandes.VILLE_DEFAUT
            lever, coucher = _soleil(float(lat), float(lon), heure.tm_yday, heure.tm_gmtoff / 60)
        except Exception:
            lever, coucher = 7 * 60, 19 * 60
        self._nuit = minutes < lever or minutes > coucher
        return self._nuit

    def _detecter_fete(self, maintenant):
        """Minuit passé, ou anniversaire annoncé par Jarvis : lance l'animation (et un petit message)."""
        jour = time.strftime("%Y-%m-%d")
        if jour != self._jour:
            self._jour = jour
            if time.localtime().tm_hour == 0:
                self._fete = (maintenant, "minuit")
                self._message("Minuit : une nouvelle journée commence !")
        demande = getattr(jarvis_claude, "fete_demandee", None)
        if demande and demande[0] != self._fete_vue:
            self._fete_vue = demande[0]
            self._fete = (maintenant, demande[1])
            if demande[1] == "anniversaire":
                self._message("Joyeux anniversaire !")

    def _message(self, texte):
        try:
            self.src.changer_texte(texte)
        except Exception:
            pass

    def _prochain_rappel(self):
        """Le prochain minuteur ou rappel, relu une fois par seconde."""
        maintenant = time.time()
        if maintenant - self._rappel_lu > 1:
            self._rappel_lu = maintenant
            try:
                self._rappel = jarvis_claude.jarvis_commandes.prochain_rappel()
            except Exception:
                self._rappel = None
        return self._rappel

    def _couronne(self, surf, teinte, blanc, eclat, e, t, dt, cx, cy, Rext):
        """Couronne de graduations autour du réacteur : elle dessine le spectre du son en direct."""
        s, n = self.s * (0.55 + 0.45 * min(1.0, self._k)), NB_GRADUATIONS
        if e == "reponse":
            spectre, gain = jarvis_voix.spectre, 1.0
        elif e == "ecoute":
            spectre, gain = jarvis_claude.spectre_micro, 1.0
        else:
            spectre, gain = None, 0.0
        if spectre is not None and len(spectre):
            bandes = np.asarray(spectre, dtype=float)
            cible = np.interp(self._grad_bande * (len(bandes) - 1), np.arange(len(bandes)), bandes[::-1]) * gain
        elif e == "traitement":            # une comète fait le tour pendant que Jarvis réfléchit
            cible = np.maximum(0, np.cos((np.arange(n) * (2 * math.pi / n) - t * 5) / 2)) ** 24 * 0.9
        elif e == "erreur":
            cible = np.full(n, 0.35 + 0.35 * math.sin(t * 6))
        elif e == "rappel":                # deux éclats tournent autour de la couronne, qui bat en rythme
            angle = np.arange(n) * (2 * math.pi / n) - t * 4
            cible = np.maximum(0, np.cos(angle)) ** 10 * 0.9 + 0.30 + 0.20 * math.sin(t * 8)
            if jarvis_voix.spectre is not None:
                bandes = np.asarray(jarvis_voix.spectre, dtype=float)
                cible = np.maximum(cible, np.interp(self._grad_bande * (len(bandes) - 1),
                                                    np.arange(len(bandes)), bandes[::-1]))
        else:                              # veille : une lente respiration parcourt la couronne
            cible = 0.12 + 0.10 * np.sin(t * 1.1 + np.arange(n) * (4 * math.pi / n))
            if self._musique > 0.02:       # musique : des vagues font le tour de la couronne, au rythme du son
                vagues = 0.5 + 0.5 * np.sin(np.arange(n) * (6 * math.pi / n) - t * 3.2)
                cible = np.maximum(cible, self._musique * (0.25 + 0.75 * vagues ** 2))
            # Un minuteur ou un rappel en attente : la couronne est pleine au départ et se vide
            # dans le sens des aiguilles d'une montre, à partir du haut
            rappel = self._prochain_rappel()
            if rappel:
                quand, debut, _ = rappel
                reste = max(0.0, min(1.0, (quand - time.time()) / max(1.0, quand - debut)))
                depuis_haut = (np.arange(n) + n // 4) % n          # 0 = graduation du haut
                cible = np.where(depuis_haut >= (1 - reste) * n, 0.75, 0.04)
        monte = cible > self._niveaux
        self._niveaux += (cible - self._niveaux) * np.where(monte, 1 - math.exp(-dt * 30), 1 - math.exp(-dt * 9))
        niveaux = np.clip(self._niveaux, 0, 1)

        r0 = Rext * 0.915
        longueurs = Rext * (0.018 + 0.067 * niveaux)
        longueurs[::6] += Rext * 0.012                 # une graduation sur six est plus longue
        rot = 0.0 if (spectre is None and e not in ("traitement", "erreur") and self._prochain_rappel()) else t * 0.05
        cr, sr = math.cos(rot), math.sin(rot)
        gc = self._grad_cos * cr - self._grad_sin * sr
        gs = self._grad_sin * cr + self._grad_cos * sr
        x0, y0 = cx + r0 * gc, cy + r0 * gs
        x1, y1 = cx + (r0 + longueurs) * gc, cy + (r0 + longueurs) * gs
        epais = max(1, int(1.6 * s))
        forces = np.minimum(1.0, 0.50 + 0.60 * niveaux) * (0.75 + 0.25 * eclat)
        trait = pygame.draw.line
        visibles = n if self._naissance >= 1 else int(n * getattr(self, "_naissance_couronne", self._naissance))   # au lancement, elles apparaissent une à une
        palette = getattr(self.src, "COULEURS_VEILLE", None) if e == "veille" else None
        if palette:                                    # veille : dégradé des couleurs tout autour de la couronne
            couleurs = [_rgb(c) for c in palette]
            decalage = t / max(1.0, getattr(self.src, "CYCLE_VEILLE", 12))
        for i in range(visibles):
            f = forces[i]
            if palette:
                vers = _degrade(couleurs, decalage + i * len(couleurs) / n)
                trait(surf, teinte(f, vers), (x0[i], y0[i]), (x1[i], y1[i]), epais)
                continue
            trait(surf, teinte(f, blanc if f > 0.8 else None), (x0[i], y0[i]), (x1[i], y1[i]), epais)

        # Deux arcs lumineux tournent en sens inverse juste à l'intérieur des graduations
        ra = Rext * 0.895
        for sens, depart, etendue in ((1, 0.0, 1.0), (-1, 2.4, 0.6)):
            a0 = sens * t * (0.5 if e in ("veille", "pause", "demarrage") else 1.6) + depart
            angles = a0 + np.linspace(0, etendue, 14)
            pts = np.column_stack((cx + ra * np.cos(angles), cy + ra * np.sin(angles)))
            pygame.draw.aalines(surf, teinte(0.75 * eclat), False, pts)

    def _suivre_meteo(self):
        """La température et le ciel de la ville réglée, relus tous les quarts d'heure (Open-Meteo, sans clé)."""
        time.sleep(20)
        while True:
            try:
                import jarvis_commandes as c
                _, lat, lon = c.VILLE_DEFAUT
                d = c._json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
                            "&current=temperature_2m,weather_code&timezone=auto")["current"]
                self.meteo = (round(d["temperature_2m"]), int(d["weather_code"]))
            except Exception:
                pass                                 # pas de connexion : la météo ne s'affiche pas, rien de plus
            time.sleep(900)

    @staticmethod
    def _icone_ciel(surf, code, x, y, r, couleur, blanc):
        """Un petit pictogramme : soleil (ciel clair), nuage, nuage et pluie, ou nuage et neige."""
        if code <= 1:
            pygame.draw.circle(surf, couleur, (x, y), r * 0.5)
            for i in range(8):
                a = i * math.pi / 4
                pygame.draw.line(surf, couleur, (x + r * 0.72 * math.cos(a), y + r * 0.72 * math.sin(a)),
                                 (x + r * math.cos(a), y + r * math.sin(a)), max(1, int(r * 0.14)))
            return
        for dx, dy, rr in ((-0.42, 0.12, 0.38), (0.0, -0.12, 0.5), (0.45, 0.12, 0.36)):
            pygame.draw.circle(surf, blanc, (x + dx * r, y + dy * r), rr * r)
        pygame.draw.rect(surf, blanc, (x - 0.8 * r, y + 0.05 * r, 1.6 * r, 0.45 * r))
        if code >= 51:                                  # pluie, averses, neige, orages : quelques traits dessous
            for dx in (-0.45, 0.0, 0.45):
                pygame.draw.line(surf, couleur, (x + dx * r, y + 0.7 * r), (x + (dx - 0.15) * r, y + 1.1 * r), max(1, int(r * 0.14)))

    def _panneau(self, surf, teinte, blanc, eclat, titre, cx, dt=0.05):
        src, s = self.src, self.s
        yb = self.yr + self.d
        x0, x1 = 5 * s, self.w - 5 * s
        y0, y1 = yb + 4 * s, self.h - 3 * s
        k = 9 * s
        contour = [(x0 + k, y0), (x1, y0), (x1, y1 - k), (x1 - k, y1), (x0, y1), (x0, y0 + k)]
        pygame.draw.polygon(surf, self.fond, contour)
        pygame.draw.aalines(surf, teinte(0.28 * eclat), True, contour)
        # Équerres lumineuses dans les deux angles droits
        e, ep = 14 * s, max(2, int(2 * s))
        if getattr(self, "_en_alerte", False):       # pendant un rappel, les équerres s'agrandissent et clignotent
            e *= 1.6 + 0.6 * math.sin(time.time() * 8)
            ep += 1
        pygame.draw.lines(surf, teinte(1.0), False, [(x1 - e, y0), (x1, y0), (x1, y0 + e)], ep)
        pygame.draw.lines(surf, teinte(1.0), False, [(x0, y1 - e), (x0, y1), (x0 + e, y1)], ep)
        self._reflet(surf, teinte, blanc, contour, time.time())

        image = self._texte(self.police_titre, titre.upper(), teinte(1.0))
        yt = yb + 17 * s
        decal = 6 * s                                   # le titre se décale un peu : un point lumineux le précède
        surf.blit(image, image.get_rect(center=(cx + decal, yt)))
        # Le point d'état : il clignote quand Jarvis écoute ou réfléchit
        battement = 1.0
        if self.src.etat_actuel in ("ecoute", "traitement"):
            battement = 0.35 + 0.65 * abs(math.sin(time.time() * (4 if self.src.etat_actuel == "ecoute" else 6)))
        xp = cx + decal - image.get_width() / 2 - 9 * s
        pygame.draw.circle(surf, teinte(0.35 * battement), (xp, yt), 5.5 * s)
        pygame.draw.circle(surf, teinte(battement, blanc), (xp, yt), 3 * s)
        demi = image.get_width() / 2 + 10 * s
        gauche_titre = xp - 9 * s
        # À droite : la météo, puis l'heure, quand il reste de la place
        heure = self._texte(self.police_jauge, time.strftime("%H:%M"), teinte(0.6))
        fin_ligne = x1 - 12 * s
        if cx + decal + demi + heure.get_width() + 22 * s < x1:
            surf.blit(heure, heure.get_rect(midright=(x1 - 10 * s, yt)))
            fin_ligne = x1 - 16 * s - heure.get_width()
            if self.meteo is not None:
                temp = self._texte(self.police_jauge, f"{self.meteo[0]}°", teinte(0.75, blanc))
                if cx + decal + demi + heure.get_width() + temp.get_width() + 46 * s < x1:
                    surf.blit(temp, temp.get_rect(midright=(fin_ligne - 2 * s, yt)))
                    self._icone_ciel(surf, self.meteo[1], fin_ligne - temp.get_width() - 12 * s, yt - 1 * s, 5.5 * s,
                                     teinte(0.9), teinte(0.7, blanc))
                    fin_ligne -= temp.get_width() + 26 * s
        # À gauche : un voyant par tablette (allumé si elle est en ligne), avec l'initiale et la batterie
        debut_ligne = x0 + k + 4 * s
        try:
            import jarvis_tablette
            tablettes = jarvis_tablette.tablettes_en_ligne()
        except Exception:
            tablettes = []
        for prenom, en_ligne, pile in tablettes[:3]:
            etiquette = prenom[:1].upper() + (f" {pile}%" if en_ligne and pile is not None else "")
            img = self._texte(self.police_compacte, etiquette, teinte(0.75 if en_ligne else 0.35, blanc))
            if debut_ligne + 12 * s + img.get_width() > gauche_titre - 6 * s:
                break
            couleur = (61, 220, 132) if en_ligne else teinte(0.3)
            if en_ligne and pile is not None and pile <= 15:
                couleur = (255, 140, 66)
            pygame.draw.circle(surf, couleur, (debut_ligne + 3 * s, yt), 3 * s)
            surf.blit(img, img.get_rect(midleft=(debut_ligne + 9 * s, yt)))
            debut_ligne += 15 * s + img.get_width()
        if gauche_titre > debut_ligne + 6 * s:
            pygame.draw.line(surf, teinte(0.45), (debut_ligne, yt), (gauche_titre, yt))
        if fin_ligne > cx + decal + demi:
            pygame.draw.line(surf, teinte(0.45), (cx + decal + demi, yt), (fin_ligne, yt))

        if src.AFFICHER_SYSTEME:
            jauges = self._mesures()
            colonne = (x1 - x0 - 14 * s) / len(jauges)
            eteint = teinte(0.14)
            couleurs_veille = self._couleurs_jauges(len(jauges))
            maintenant = time.time()
            garder = maintenant - self._histo_quand >= 3          # un point de courbe toutes les 3 secondes
            if garder:
                self._histo_quand = maintenant
            for i, (nom, valeur, unite) in enumerate(jauges):
                xc = x0 + 7 * s + colonne * (i + 0.5)
                couleur = ((255, 77, 77) if valeur >= 90 else (255, 165, 58) if valeur >= 75
                           else couleurs_veille[i] if couleurs_veille else teinte(0.95))
                police = self.police_jauge if len(jauges) <= 4 else self.police_jauge_petite
                self._etiquette(surf, police, nom, valeur, unite, couleur, xc, yb + 36 * s)
                # Une barre fine et arrondie, qui glisse vers la nouvelle valeur au lieu de sauter
                lisse = self._jauges.get(nom, valeur)
                lisse += (valeur - lisse) * (1 - math.exp(-dt * 6))
                self._jauges[nom] = lisse
                large = colonne * 0.82
                xa, ya, haut = xc - large / 2, yb + 44 * s, max(3, int(4 * s))
                rayon = haut // 2
                pygame.draw.rect(surf, eteint, (xa, ya, large, haut), border_radius=rayon)
                plein = large * max(0.0, min(100.0, lisse)) / 100
                if plein >= 2:
                    pygame.draw.rect(surf, couleur, (xa, ya, plein, haut), border_radius=rayon)
                    pygame.draw.circle(surf, _melange_ent(couleur, (255, 255, 255), 0.6), (xa + plein - rayon, ya + haut / 2), rayon)
                # ... et dessous, la courbe des dernières minutes
                histo = self._historique.setdefault(nom, [])
                if garder:
                    histo.append(min(100.0, max(0.0, float(valeur))))
                    del histo[:-40]
                if len(histo) >= 2:
                    y_bas, h_courbe = yb + 59 * s, 9 * s
                    pas = large / 39
                    depart = xa + large - pas * (len(histo) - 1)
                    pts = [(depart + j * pas, y_bas - v / 100 * h_courbe) for j, v in enumerate(histo)]
                    pygame.draw.polygon(surf, _melange_ent(self.fond, couleur, 0.16), pts + [(pts[-1][0], y_bas), (pts[0][0], y_bas)])
                    pygame.draw.aalines(surf, _melange_ent(self.fond, couleur, 0.85), False, pts)

    # ---------- Fenêtre de discussion (au-dessus du réacteur) ----------

    def _mettre_en_lignes(self, texte, largeur):
        """Découpe le texte en lignes qui tiennent dans la largeur (gardé en mémoire tant qu'il ne change pas)."""
        cle = (texte, int(largeur), id(self.police_discussion))
        if self._lignes[0] == cle:
            return self._lignes[1]
        mesure = self.police_discussion.size
        lignes, ligne = [], ""
        for mot in texte.split(" "):
            essai = (ligne + " " + mot) if ligne else mot
            if mesure(essai)[0] <= largeur:
                ligne = essai
                continue
            if ligne:
                lignes.append(ligne)
            while mesure(mot)[0] > largeur and len(mot) > 1:     # un mot plus long que la ligne : on le coupe
                n = len(mot) - 1
                while n > 1 and mesure(mot[:n])[0] > largeur:
                    n -= 1
                lignes.append(mot[:n])
                mot = mot[n:]
            ligne = mot
        if ligne:
            lignes.append(ligne)
        self._lignes = (cle, lignes)
        return lignes

    def _invite(self):
        """Fenêtre de discussion vide : « Clique ici pour écrire à Jarvis », puis des idées de demandes, tour à tour."""
        tour = int(time.time() / DUREE_IDEE)
        if tour % 3 == 0:
            return INVITE_SAISIE
        return "Essaie : « " + random.Random(tour).choice(IDEES) + " »"

    def _texte_rappel(self):
        """« dans 3:20 · minuteur » : le prochain minuteur ou rappel, ou « » s'il n'y en a pas."""
        rappel = self._prochain_rappel()
        if not rappel:
            return ""
        quand, _, message = rappel
        reste = quand - time.time()
        if reste < 3600:
            moment = "dans %d:%02d" % (max(0, reste) // 60, max(0, reste) % 60)
        else:
            moment = "à " + time.strftime("%H:%M", time.localtime(quand))
        message = re.sub(r"^Rappel : |\.$", "", message)
        if message.startswith("Le minuteur") or message.startswith("Il est"):
            message = "minuteur" if message.startswith("Le minuteur") else "rappel"
        return f"{moment} · {message}"

    def _discussion(self, surf, teinte, blanc, eclat, cx, maintenant):
        """La fenêtre de discussion : ce que tu dis ou écris, puis la réponse de Jarvis, qui le remplace.
        Un clic dedans, et tu écris ta demande ; Entrée l'envoie."""
        src, s = self.src, self.s
        x0, x1 = 5 * s, self.w - 5 * s
        y0, y1 = 3 * s, self.haut - 2 * s
        k = 9 * s
        contour = [(x0 + k, y0), (x1, y0), (x1, y1 - k), (x1 - k, y1), (x0, y1), (x0, y0 + k)]
        pygame.draw.polygon(surf, self.fond, contour)
        # Un léger dégradé, plus clair en haut, aux couleurs du moment (une ligne sur deux suffit, l'œil lisse le reste)
        haut_fenetre = y1 - y0
        for yy in range(int(y0) + 1, int(y1), 2):
            p = (yy - y0) / haut_fenetre
            xg = x0 + max(0.0, k - (yy - y0)) + 1
            xd = x1 - max(0.0, (yy - y0) - (haut_fenetre - k)) - 1
            pygame.draw.line(surf, teinte(0.09 * (1 - p) * eclat), (xg, yy), (xd, yy), 2)
        ecrit = self._saisie is not None
        pygame.draw.aalines(surf, teinte((0.6 if ecrit else 0.28) * eclat), True, contour)
        e, ep = 14 * s, max(2, int(2 * s))
        pygame.draw.lines(surf, teinte(1.0), False, [(x1 - e, y0), (x1, y0), (x1, y0 + e)], ep)
        pygame.draw.lines(surf, teinte(1.0), False, [(x0, y1 - e), (x0, y1), (x0 + e, y1)], ep)
        self._reflet(surf, teinte, blanc, contour, time.time(), decalage=1.7)
        self._zone_discussion = pygame.Rect(int(x0), int(y0), int(x1 - x0), int(y1 - y0))

        largeur = x1 - x0 - 22 * s
        curseur = int(maintenant * 2.5) % 2 == 0
        nb = LIGNES_DISCUSSION
        if ecrit and (self._saisie or not src.texte_actuel):
            # On écrit : la demande en cours, avec un curseur qui clignote (les dernières lignes si elle est longue)
            lignes = list(self._mettre_en_lignes(self._saisie, largeur - 8 * s))[-nb:] or [""]
            lignes[-1] += "|" if curseur else " "
            couleur = teinte(0.95, blanc)
        elif src.texte_actuel:
            lignes = self._mettre_en_lignes(src.texte_actuel, largeur)
            if getattr(src, "texte_en_direct", False) and src.etat_actuel == "ecoute":
                # pendant l'écoute : les mots au fil de l'eau, avec un curseur qui clignote
                lignes = list(lignes[-nb:])
                lignes[-1] += " |" if curseur else "  "
                couleur = teinte(0.85, blanc)
            else:
                if len(lignes) > nb:                       # un long texte défile, à la vitesse où on le lit
                    par_ligne = max(1.2, len(src.texte_actuel) / len(lignes) / 14.0)
                    debut = int((maintenant - src.texte_depuis) / par_ligne - 1.5)
                    debut = max(0, min(len(lignes) - nb, debut))
                    lignes = lignes[debut:debut + nb]
                fondu = max(0.0, min(1.0, self._reste_texte / 2))
                # la réponse de Jarvis est plus lumineuse que la demande
                force = 0.95 if getattr(src, "texte_reponse", False) else 0.7
                couleur = teinte(force * fondu, blanc)
        else:
            rappel = self._texte_rappel()
            lignes = self._mettre_en_lignes(rappel, largeur)[:nb] if rappel else [self._invite()]
            couleur = teinte(0.7, blanc) if rappel else teinte(0.68)
        pas = self.police_discussion.get_linesize()
        y = (y0 + y1) / 2 - pas * (len(lignes) - 1) / 2
        haut_texte = y - pas / 2
        plus_large = 0
        for ligne in lignes:
            image = self._texte(self.police_discussion, ligne, couleur)
            surf.blit(image, image.get_rect(center=(cx, y)))
            plus_large = max(plus_large, image.get_width())
            y += pas
        # La réponse de Jarvis : un trait de couleur devant le texte, pour la distinguer de ta demande
        if src.texte_actuel and not ecrit and getattr(src, "texte_reponse", False) and plus_large:
            xb = max(x0 + 8 * s, cx - plus_large / 2 - 9 * s)
            pygame.draw.line(surf, teinte(0.95 * max(0.0, min(1.0, self._reste_texte / 2))), (xb, haut_texte + 2 * s),
                             (xb, y - pas / 2 - 2 * s), max(2, int(2.5 * s)))

    def _couleurs_jauges(self, nombre):
        """En veille avec les couleurs Vice City : une teinte du dégradé par jauge (sinon None)."""
        palette = getattr(self.src, "COULEURS_VEILLE", None)
        if not palette or self.src.etat_actuel != "veille":
            return None
        couleurs = [_rgb(c) for c in palette]
        decalage = time.time() / max(1.0, getattr(self.src, "CYCLE_VEILLE", 12))
        return [tuple(int(c) for c in _degrade(couleurs, decalage + i * len(couleurs) / nombre))
                for i in range(nombre)]

    def _reflet(self, surf, teinte, blanc, points, t, decalage=0.0, tour_fixe=None):
        """Un reflet de lumière fait tout le tour d'un contour (panneau ou cercle du réacteur), puis une
        courte pause avant le tour suivant. points : les sommets du contour, dans l'ordre."""
        S = self.s
        # Le contour fermé et la distance parcourue jusqu'à chaque sommet : tous les points du reflet sont
        # ensuite placés d'un seul calcul (avant, chaque petit trait reparcourait le contour : 40 % du temps
        # de dessin d'une image)
        pts = np.asarray(points, dtype=float)
        pts = np.vstack((pts, pts[:1]))
        cumul = np.concatenate(([0.0], np.cumsum(np.hypot(np.diff(pts[:, 0]), np.diff(pts[:, 1])))))
        total = float(cumul[-1])
        if total < 1:
            return
        longueur = min(LONGUEUR_REFLET * S, 0.7 * total / max(1, NB_REFLETS))   # jamais deux reflets qui se touchent
        tour = total / (VITESSE_REFLET * S) + PAUSE_REFLET           # secondes pour un tour, pause comprise
        avance = ((t + decalage) % tour) * VITESSE_REFLET * S
        if tour_fixe:
            # Le cercle du réacteur change sans cesse de taille (il respire, grandit, rétrécit) : son reflet
            # tourne donc à vitesse régulière, un tour en « tour_fixe » secondes, quelle que soit sa taille.
            avance = ((t + decalage) % tour_fixe) / tour_fixe * total + total
            longueur = min(longueur, 0.22 * total)
        elif PAUSE_REFLET <= 0:
            avance += total                    # sans pause : la traîne continue sur le tour précédent
        elif avance > total + longueur:
            return

        morceaux = 24
        pas = longueur / morceaux
        epais = max(1, int(1.7 * S))
        # plusieurs reflets, répartis à égale distance sur le contour (deux : l'un à l'opposé de l'autre)
        nombre = NB_REFLETS if PAUSE_REFLET <= 0 else 1
        debuts, fins, forces = [], [], []             # chaque morceau du reflet : d'où à où, et sa force
        for r in range(max(1, nombre)):
            tete = avance + r * total / max(1, nombre)
            for k in range(morceaux):
                d1, d2 = tete - k * pas, tete - (k + 1) * pas
                if d1 <= 0:
                    break
                if d1 > total and PAUSE_REFLET > 0:     # la tête a fini le tour : seule la traîne finit de passer
                    continue
                debuts.append(max(0.0, d2))
                fins.append(d1)
                forces.append(0.95 * (1 - k / morceaux) ** 1.4)
        if not forces:
            return
        # on suit le contour même dans les angles : chaque morceau est fait de plusieurs petits traits
        n = max(1, int(pas / (3 * S)))
        debuts, fins = np.array(debuts)[:, None], np.array(fins)[:, None]
        d = (debuts + (fins - debuts) * np.linspace(0.0, 1.0, n + 1)[None, :]) % total
        xy = np.stack((np.interp(d, cumul, pts[:, 0]), np.interp(d, cumul, pts[:, 1])), axis=2)
        for force, morceau in zip(forces, xy):
            # un morceau à cheval sur la fin du tour : le contour est fermé, ses points se suivent quand même
            pygame.draw.lines(surf, teinte(force, blanc), False, morceau, epais)

    def _etiquette(self, surf, police, nom, valeur, unite, couleur, xc, yc):
        """« CPU [icône] 12% », centré sur (xc, yc). L'icône a la hauteur des lettres."""
        if not ICONES_JAUGES:
            image = self._texte(police, f"{nom} {valeur:.0f}{unite}", couleur)
            surf.blit(image, image.get_rect(center=(xc, yc)))
            return
        gauche = self._texte(police, nom, couleur)
        droite = self._texte(police, f"{valeur:.0f}{unite}", couleur)
        taille = police.get_ascent() * 1.0                  # hauteur des lettres, environ
        ecart = 3 * self.s
        largeur = gauche.get_width() + droite.get_width() + taille + 2 * ecart
        x = xc - largeur / 2
        surf.blit(gauche, gauche.get_rect(midleft=(x, yc)))
        x += gauche.get_width() + ecart
        self._icone(surf, nom, x, yc, taille, couleur)
        x += taille + ecart
        surf.blit(droite, droite.get_rect(midleft=(x, yc)))

    def _icone(self, surf, nom, x, yc, h, couleur):
        """Petites icônes dessinées dans le style du réacteur (les émojis en couleur ne s'affichent pas ici).
        x : bord gauche, yc : milieu, h : taille (carré h × h)."""
        ep = max(1, int(round(h / 9)))
        y = yc - h / 2
        trait = pygame.draw.line
        if nom == "CPU":                                    # une puce : un carré, des pattes, un cœur plein
            m = h * 0.2
            pygame.draw.rect(surf, couleur, (x + m, y + m, h - 2 * m, h - 2 * m), ep)
            pygame.draw.rect(surf, couleur, (x + h * 0.38, y + h * 0.38, h * 0.24, h * 0.24))
            for f in (0.38, 0.62):
                for a, b in (((x + h * f, y), (x + h * f, y + m)), ((x + h * f, y + h - m), (x + h * f, y + h)),
                             ((x, y + h * f), (x + m, y + h * f)), ((x + h - m, y + h * f), (x + h, y + h * f))):
                    trait(surf, couleur, a, b, ep)
        elif nom == "RAM":                                  # une barrette : puces dessus, contacts dessous
            pygame.draw.rect(surf, couleur, (x, y + h * 0.22, h, h * 0.5), ep)
            for f in (0.14, 0.42, 0.70):
                pygame.draw.rect(surf, couleur, (x + h * f, y + h * 0.34, h * 0.16, h * 0.26))
            for f in (0.15, 0.35, 0.55, 0.75, 0.9):
                trait(surf, couleur, (x + h * f, y + h * 0.72), (x + h * f, y + h * 0.9), ep)
        elif nom == "GPU":                                  # une carte graphique et son ventilateur
            pygame.draw.rect(surf, couleur, (x, y + h * 0.18, h, h * 0.6), ep)
            pygame.draw.circle(surf, couleur, (x + h * 0.38, y + h * 0.48), h * 0.17, ep)
            pygame.draw.rect(surf, couleur, (x + h * 0.66, y + h * 0.32, h * 0.2, h * 0.32))
            trait(surf, couleur, (x + h * 0.12, y + h * 0.78), (x + h * 0.12, y + h * 0.95), ep)
        elif nom == "NET":                                  # le Wi-Fi : trois arcs et un point
            cx, cy = x + h / 2, y + h * 0.9
            for r in (0.85, 0.58, 0.31):
                pygame.draw.arc(surf, couleur, (cx - h * r, cy - h * r, 2 * h * r, 2 * h * r),
                                math.radians(45), math.radians(135), ep)
            pygame.draw.circle(surf, couleur, (cx, cy - h * 0.04), max(1.0, h * 0.09))
        elif nom == "TMP":                                  # un thermomètre
            cx = x + h / 2
            cx = x + h * 0.4
            pygame.draw.circle(surf, couleur, (cx, y + h * 0.76), h * 0.22)
            pygame.draw.rect(surf, couleur, (cx - h * 0.12, y + h * 0.02, h * 0.24, h * 0.68), ep,
                             border_radius=int(h * 0.12))
            trait(surf, couleur, (cx, y + h * 0.3), (cx, y + h * 0.7), max(2, ep + 1))
            for f in (0.18, 0.34, 0.5):
                trait(surf, couleur, (cx + h * 0.2, y + h * f), (cx + h * 0.4, y + h * f), max(1, ep - 1))

    @staticmethod
    def _mesures():
        """Les jauges à afficher : (nom, valeur, unité)."""
        m = jarvis_systeme.mesures
        jauges = [("CPU", m["cpu"], "%"), ("RAM", m["ram"], "%")]
        if m.get("gpu") is not None:
            jauges.append(("GPU", m["gpu"], "%"))
        jauges.append(("NET", m.get("reseau", 0.0), "%"))
        if m.get("temp") is not None:
            jauges.append(("TMP", m["temp"], "°"))
        choisies = [j for j in jauges if j[0] in JAUGES]
        return choisies or jauges[:1]

    def _panneau_compact(self, surf, teinte, blanc, e, t, cx, y0, dt=0.05):
        """Mode discret : un panneau fin sous le réacteur, avec seulement les jauges, toujours lisibles.
        Chaque jauge : son nom et sa valeur, puis une barre lumineuse qui glisse vers la nouvelle valeur."""
        S = self.s
        jauges = self._mesures()
        colonne = (55 if ICONES_JAUGES else 47) * S
        largeur = colonne * len(jauges) + 10 * S
        hauteur = 29 * S
        x0, x1 = cx - largeur / 2, cx + largeur / 2
        y1 = y0 + hauteur
        if y1 > self.h - 1:                                  # ne sort jamais de la fenêtre
            y0, y1 = self.h - 1 - hauteur, self.h - 1
        k = 6 * S
        contour = [(x0 + k, y0), (x1, y0), (x1, y1 - k), (x1 - k, y1), (x0, y1), (x0, y0 + k)]
        pygame.draw.polygon(surf, self.fond, contour)
        pygame.draw.aalines(surf, teinte(0.35), True, contour)
        # deux petites équerres lumineuses, comme sur le grand panneau
        q, ep = 8 * S, max(1, int(1.5 * S))
        pygame.draw.lines(surf, teinte(1.0), False, [(x1 - q, y0), (x1, y0), (x1, y0 + q)], ep)
        pygame.draw.lines(surf, teinte(1.0), False, [(x0, y1 - q), (x0, y1), (x0 + q, y1)], ep)
        self._reflet(surf, teinte, blanc, contour, time.time())
        couleurs_veille = self._couleurs_jauges(len(jauges)) if e == "veille" else None
        for i, (nom, valeur, unite) in enumerate(jauges):
            xc = x0 + 5 * S + colonne * (i + 0.5)
            if valeur >= 90:
                vive = (255, 77, 77)
            elif valeur >= 75:
                vive = (255, 165, 58)
            elif couleurs_veille:                            # veille : chaque jauge prend une teinte du dégradé
                vive = couleurs_veille[i]
            else:
                vive = teinte(1.0)
            vive = tuple(int(c) for c in _melange(vive, (255, 255, 255), 0.12))   # un peu plus clair : lisible
            self._etiquette(surf, self.police_compacte, nom, valeur, unite, vive, xc, y0 + 10.5 * S)
            lisse = self._jauges.get(nom, valeur)
            lisse += (valeur - lisse) * (1 - math.exp(-dt * 6))
            self._jauges[nom] = lisse
            # barre : fond sombre, partie remplie lumineuse, et une pointe blanche au bout
            large, epais = colonne * 0.78, max(2, int(3 * S))
            xa, yb = xc - large / 2, y0 + 20.5 * S
            pygame.draw.line(surf, teinte(0.14), (xa, yb), (xa + large, yb), epais)
            rempli = large * max(0.0, min(1.0, lisse / 100))
            if rempli >= 1:
                sombre = tuple(int(c) for c in _melange(self.fond, vive, 0.55))
                pygame.draw.line(surf, sombre, (xa, yb), (xa + rempli, yb), epais)
                pygame.draw.line(surf, vive, (xa + rempli * 0.35, yb), (xa + rempli, yb), epais)
                pygame.draw.circle(surf, tuple(int(c) for c in _melange(vive, (255, 255, 255), 0.6)),
                                   (xa + rempli, yb), epais * 0.75)
        self._zone_compacte = pygame.Rect(int(x0), int(y0), int(largeur) + 1, int(hauteur) + 1)

    # ---------- Boucle ----------

    def lancer(self):
        src = self.src
        horloge = pygame.time.Clock()
        while True:
            self._evenements()
            self.image()
            pygame.display.flip()
            maintenant = time.time()
            if (self._fermeture is not None and self._quitter
                    and maintenant - self._fermeture > DUREE_FERMETURE + 0.1):
                os._exit(self._sortie)
            if maintenant - self._dernier_premier_plan > 1:
                self._dernier_premier_plan = maintenant
                self._premier_plan()
            actif = (src.etat_actuel in ("ecoute", "traitement", "reponse", "erreur", "arret", "rappel")
                     or maintenant - self._alerte < DUREE_ALERTE
                     or self.glisse is not None or maintenant - src.texte_depuis < 1
                     or self._saisie is not None           # on écrit : les lettres suivent la frappe
                     or getattr(self, "_menu_ouvert", None) is not None   # le menu suit la souris
                     or maintenant - self.t0 < DUREE_NAISSANCE + 0.5 or self._fermeture is not None
                     or 0.02 < self._forme < 0.98)          # pendant qu'il change de taille
            if actif:
                self._dernier_actif = maintenant
                images = src.IMAGES_ACTIF
            elif maintenant - self._dernier_actif < 30:
                images = src.IMAGES_VEILLE
            else:
                images = src.IMAGES_VEILLE_LONGUE
            horloge.tick(images)
