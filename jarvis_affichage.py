"""
JARVIS - affichage rapide du réacteur (60 images par seconde).

Même visuel que l'ancien affichage, mais dessiné avec pygame, beaucoup plus
rapide : environ 5 ms par image au lieu de 37. Le réacteur peut donc tourner
à 60 images par seconde quand Jarvis est actif.

Autour du réacteur, une couronne de graduations réagit au vrai son : le spectre de
ta voix quand Jarvis écoute, celui de sa voix quand il répond. Une onde part du cœur
à chaque réveil, et un léger halo lumineux entoure les filaments.

Sous le réacteur, le panneau affiche l'état de Jarvis, l'heure et des jauges :
processeur, mémoire, carte graphique, réseau (et température si le PC la fournit).
Pendant l'écoute, les mots compris s'y affichent au fur et à mesure.

En veille, le réacteur se fait discret : il rétrécit et son panneau disparaît. Il reprend sa
taille dès que Jarvis t'entend, ou quand tu passes la souris dessus.
Un minuteur ou un rappel en attente se lit sur la couronne (elle se vide peu à peu) et dans le panneau.
Au lancement, le réacteur se forme ; à l'arrêt ou au redémarrage, il se referme.
"""

import ctypes
import ctypes.wintypes
import math
import os
import random
import re
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np
import pygame

import jarvis_claude
import jarvis_systeme
import jarvis_voix

CLE = (1, 2, 3)          # couleur rendue invisible (transparence de la fenêtre)
ELARGISSEMENT = 30       # largeur ajoutée au panneau de chaque côté du réacteur
NB_GRADUATIONS = 72      # traits de la couronne extérieure (ils dessinent le spectre du son)
MODE_DISCRET = True      # en veille, le réacteur rétrécit et le panneau disparaît
TAILLE_DISCRETE = 0.45   # taille du réacteur en veille (1 = taille normale)
DELAI_DISCRET = 35       # secondes de veille avant de rétrécir
VITESSE_REFLET = 58      # vitesse du reflet de lumière qui fait le tour des panneaux et du réacteur (points/s)
LONGUEUR_REFLET = 40     # longueur du reflet (points)
PAUSE_REFLET = 0.0       # secondes de pause entre deux tours (0 : il tourne sans s'arrêter)
REFLET_REACTEUR = True   # le reflet fait aussi le tour du cercle du réacteur
DANSE_MUSIQUE = True     # en veille, le réacteur bouge au rythme du son du PC (musique, vidéo)
REGARD_SOURIS = True     # le cœur du réacteur se tourne un peu vers la souris quand elle approche
DOUX_LA_NUIT = True      # la nuit (après le coucher du soleil), le réacteur en veille est moins lumineux
FETES = True             # petite animation à minuit et le jour de l'anniversaire
DUREE_FETE = 8.0         # secondes
COULEURS_FETE = ((255, 215, 90), (255, 46, 151), (80, 220, 255), (157, 77, 255), (120, 255, 150))
ICONES_JAUGES = True     # petite icône entre le nom et la valeur de chaque jauge
PANNEAU_COMPACT = True   # en mode discret, les jauges restent visibles dans un petit panneau (sinon il disparaît)
DUREE_NAISSANCE = 1.4    # secondes que met le réacteur à se former au lancement
DUREE_ALERTE = 5.0       # secondes d'animation quand un minuteur ou un rappel sonne
DUREE_FERMETURE = 0.7    # secondes qu'il met à se refermer à l'arrêt
HALO = True              # léger halo lumineux autour des filaments (False = dessin net, un peu plus rapide)
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


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.wintypes.RECT):
    """Le rectangle de Windows (même type que celui déclaré par jarvis_ecran : user32 est partagé entre
    les modules, et deux types différents faisaient planter le réacteur au survol de la souris)."""
    gauche = property(lambda self: self.left)
    haut = property(lambda self: self.top)
    droite = property(lambda self: self.right)
    bas = property(lambda self: self.bottom)


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _melange(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t, c1[2] + (c2[2] - c1[2]) * t)


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


def _degrade(couleurs, position):
    """Couleur à la « position » (0 à len(couleurs), en boucle) d'un dégradé circulaire."""
    n = len(couleurs)
    position %= n
    i = int(position)
    return _melange(couleurs[i], couleurs[(i + 1) % n], position - i)


class Affichage:
    def __init__(self, source):
        """source : le module jarvis_reacteur (réglages, état et texte à afficher)."""
        self.src = source
        try:
            dpi = user32.GetDpiForSystem()
        except Exception:
            dpi = 96
        s = self.s = dpi / 96.0
        self.d = int(source.TAILLE * s)
        self.m = int(4 * s)
        # Le panneau est un peu plus large que le réacteur, pour des jauges bien lisibles
        self.w = self.d + 2 * self.m + int((2 * ELARGISSEMENT if source.AFFICHER_SYSTEME else 0) * s)
        self.h = self.d + 2 * self.m + int((70 if source.AFFICHER_SYSTEME else 44) * s)

        largeur_ecran, hauteur_ecran = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x = largeur_ecran - self.w - int(source.MARGE_DROITE * s)
        y = hauteur_ecran - self.h - int(source.MARGE_BAS * s)
        try:                                  # dernière position choisie à la souris
            with open(source.FICHIER_POSITION, encoding="utf-8") as f:
                px, py = (int(v) for v in f.read().split(","))
            # Une position qui dépasse un peu du bord est ramenée dans l'écran (avant, elle était ignorée)
            x = max(0, min(largeur_ecran - self.w, px))
            y = max(0, min(hauteur_ecran - self.h, py))
        except (OSError, ValueError):
            pass

        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{x},{y}"
        pygame.display.init()
        pygame.font.init()
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
        self._jour = time.strftime("%Y-%m-%d")
        self._nuit_calcul, self._nuit = 0.0, False
        ang = np.arange(NB_GRADUATIONS) * (2 * math.pi / NB_GRADUATIONS)
        self._grad_cos, self._grad_sin = np.cos(ang), np.sin(ang)
        # Chaque graduation suit une bande du spectre : graves en bas, aigus en haut, en miroir gauche/droite
        haut = (np.arange(NB_GRADUATIONS) + NB_GRADUATIONS // 4) % NB_GRADUATIONS
        self._grad_bande = np.abs(haut - NB_GRADUATIONS / 2) / (NB_GRADUATIONS / 2)   # 0 = haut, 1 = bas
        petit = max(8, self.d // 4)
        self._halo_petit = (petit, petit)
        self._zone = pygame.Rect(self.w // 2 - self.d // 2, self.m, self.d, self.d)
        self._masque = pygame.Surface((self.d, self.d))
        self._masque.set_colorkey((255, 0, 255))

        n = self.n = 160
        th = np.arange(n + 1) * (2 * math.pi / n)
        self.cos_t, self.sin_t = np.cos(th), np.sin(th)
        self.harm = {k: (np.sin(k * th), np.cos(k * th)) for k in (2, 3, 4, 5, 7)}
        self.idx_points = [np.arange(f % 6, n, 6) for f in range(source.NB_FILAMENTS)]
        self.poussiere = [{"a": random.uniform(0, 2 * math.pi), "r": random.uniform(0.15, 0.5),
                           "v": random.uniform(0.6, 1.4), "p": random.uniform(0, 6.3)}
                          for _ in range(source.NB_POUSSIERE)]

        self.police_titre = pygame.font.SysFont("segoeui", int(13.5 * s), bold=True)
        self.police_jauge = pygame.font.SysFont("consolas", int(11 * s), bold=True)
        self.police_jauge_petite = pygame.font.SysFont("consolas", int(11 * s), bold=True)
        self.police_compacte = pygame.font.SysFont("consolas", max(9, int(10 * s)), bold=True)
        self._zone_compacte = None                  # rectangle du petit panneau (pour le survol de la souris)
        self.police_texte = pygame.font.SysFont("segoeui", int(11 * s))
        self._textes = {}
        self._cercle = getattr(pygame.draw, "aacircle", pygame.draw.circle)

    # ---------- Fenêtre ----------

    def _premier_plan(self):
        user32.SetWindowPos(self.hwnd, PREMIER_PLAN, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

    def _position(self):
        r = RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return r.gauche, r.haut

    def _curseur(self):
        p = POINT()
        user32.GetCursorPos(ctypes.byref(p))
        return p.x, p.y

    def _menu(self):
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, 0x1, 0, f"Jarvis version {jarvis_claude.VERSION}")
        user32.AppendMenuW(menu, 0x800, 0, None)
        user32.AppendMenuW(menu, 0, 1, "Nouvelle conversation")
        user32.AppendMenuW(menu, 0x800, 0, None)
        user32.AppendMenuW(menu, 0, 2, "Arrêter Jarvis")
        x, y = self._curseur()
        user32.SetForegroundWindow(self.hwnd)
        choix = user32.TrackPopupMenu(menu, 0x100 | 0x2, x, y, 0, self.hwnd, None)
        user32.DestroyMenu(menu)
        if choix == 1:
            jarvis_claude.oublier_conversation()
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
        return math.hypot(x - (fx + self.w / 2), y - (fy + self.m + self.d / 2)) <= rayon

    def _evenements(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                os._exit(0)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                self.glisse = (self._curseur(), self._position())
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1 and self.glisse:
                self.glisse = None
                try:                          # la position est retenue pour les prochains démarrages
                    with open(self.src.FICHIER_POSITION, "w", encoding="utf-8") as f:
                        f.write("%d,%d" % self._position())
                except OSError:
                    pass
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 3:
                self._menu()
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
        if alerte < DUREE_ALERTE and e in ("veille", "pause", "reponse"):
            e = "rappel"
        self._en_alerte = e == "rappel"
        cible, vitesse, _, titre = src.ETATS[e]
        cible = _rgb(cible)
        palette = getattr(src, "COULEURS_VEILLE", None)
        if e == "veille" and palette:                  # veille : les couleurs défilent lentement
            cible = _degrade([_rgb(c) for c in palette], t / max(1.0, getattr(src, "CYCLE_VEILLE", 12)))
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
            amplitude += 0.22 * self._musique
            eclat = min(1.0, eclat + 0.25 * self._musique)
        # La nuit, en veille, il se fait plus doux
        if DOUX_LA_NUIT and e in ("veille", "pause") and self._est_nuit(maintenant):
            eclat *= 0.72
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
            self._etat_prec = e_vrai

        # Taille du réacteur : discret en veille, normal dès qu'il se passe quelque chose
        en_fete = self._fete is not None and maintenant - self._fete[0] < DUREE_FETE
        actif = (e not in ("veille", "pause") or self.glisse is not None or alerte < DUREE_ALERTE or en_fete
                 or maintenant - src.texte_depuis < src.DUREE_TEXTE)
        if actif:
            self._dernier_eveil = maintenant
        deploye = (not MODE_DISCRET or actif or maintenant - getattr(self, "_dernier_eveil", maintenant) < DELAI_DISCRET
                   or self._survol())
        self._forme += ((1.0 if deploye else 0.0) - self._forme) * (1 - math.exp(-dt * (9 if deploye else 4)))
        k = TAILLE_DISCRETE + (1 - TAILLE_DISCRETE) * self._forme
        naissance = min(1.0, t / DUREE_NAISSANCE)
        k *= 1 - (1 - naissance) ** 3                      # au lancement, le réacteur se forme
        if self._fermeture is not None:                    # à l'arrêt, il se referme
            k *= max(0.0, 1 - (maintenant - self._fermeture) / DUREE_FERMETURE) ** 2
        self._naissance = naissance
        self._k = k
        s = s * (0.55 + 0.45 * min(1.0, k))                # traits et points un peu plus fins quand il est petit

        cx, cy = self.w / 2, self.m + self.d / 2
        if k < 0.03:                                       # trop petit pour être dessiné
            surf.fill(CLE)
            return
        Rext = (self.d / 2 - 2 * self.s) * k   # bord de la couronne de graduations
        R = Rext * 0.83                    # le réacteur lui-même
        R0 = R * 0.68
        ligne, aaligne, cercle = pygame.draw.lines, pygame.draw.aalines, self._cercle
        gx, gy = self._suivre_regard(cx, cy, R, dt)    # le cœur se tourne un peu vers la souris
        surf.fill(CLE)

        # Fond : le contour du disque ondule lui aussi (il n'est plus un cercle fixe),
        # puis dégradé sombre, plus lumineux au centre
        ondulation = 0.022 + amplitude * 0.12
        contour = self._filament(cx, cy, R * 0.975, ondulation,
                                 [(4, 0.6, ph * 0.7), (7, 0.4, -ph * 1.1)])
        pygame.draw.polygon(surf, teinte(0.03), contour)
        aaligne(surf, teinte(0.22 * eclat), True, contour)
        for k in range(1, 7):
            pygame.draw.circle(surf, teinte(0.03 + k * 0.022 * eclat), (cx, cy), R * (7 - k) / 7)

        # Anneau extérieur : fins filaments qui ondulent au bord du cercle
        for f in range(src.NB_FILAMENTS_BORD):
            phi = f * 2.2
            pts = self._filament(cx, cy, R * (0.925 - 0.014 * f), ondulation,
                                 [(4, 0.6, ph * 0.7 + phi), (7, 0.4, -ph * 1.1 + 2 * phi)])
            ligne(surf, teinte(0.12 * eclat), True, pts, max(2, int(3 * s)))
            aaligne(surf, teinte((0.35 + 0.2 * math.sin(t * 0.8 + phi)) * eclat), True, pts)

        # Filaments intérieurs, qui tournent en sens inverse
        for f in range(src.NB_FILAMENTS_INT):
            phi = f * 1.9
            pts = self._filament(cx + gx * 0.5, cy + gy * 0.5, R0 * (0.50 + 0.03 * f), amplitude * 0.8,
                                 [(2, 0.6, -ph * 0.8 + phi), (4, 0.4, ph * 0.5 + 2 * phi)])
            force = (0.35 + 0.15 * math.sin(t * 0.9 + phi)) * eclat
            ligne(surf, teinte(0.3 * force), True, pts, max(2, int(3 * s)))
            aaligne(surf, teinte(force), True, pts)

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
            force = max(0.0, scint * bord) * eclat
            if force > 0.1:
                r = q["r"] * R0
                cercle(surf, teinte(force * 0.9, blanc),
                       (cx + gx * 0.4 + r * math.cos(q["a"]), cy + gy * 0.4 + r * math.sin(q["a"])),
                       (0.7 + 0.7 * scint) * s)

        # Cœur lumineux
        rc = R * (0.10 + 0.05 * voix) if e == "reponse" else R * (0.10 + 0.01 * math.sin(t * 3))
        rc *= 1 + 0.45 * self._musique                     # il bat au rythme de la musique
        xc, yc = cx + gx, cy + gy
        for k, force in ((1.6, 0.10), (1.25, 0.2), (1.0, 0.32)):
            cercle(surf, teinte(force * eclat), (xc, yc), rc * k)
        cercle(surf, teinte(0.8 * eclat), (xc, yc), rc, max(1, int(1.2 * s)))
        if e == "traitement":
            r = rc * 0.65
            for i in range(3):
                debut = ph * 6 + i * (2 * math.pi / 3)
                pygame.draw.arc(surf, teinte(1.0, blanc), (xc - r, yc - r, 2 * r, 2 * r),
                                debut, debut + math.pi / 3, max(2, int(2 * s)))
        else:
            cercle(surf, teinte(0.9 * eclat, blanc), (xc, yc), rc * 0.28)

        # Anneau principal de filaments, avec ses particules
        for f in range(src.NB_FILAMENTS):
            phi = f * 2.399
            force = (0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 0.7 + phi))) * eclat
            amp_f = amplitude * (0.6 + 0.8 * ((f * 0.37) % 1))
            decal = 0.05 * math.sin(phi * 1.7 + t * 0.5)
            pts = self._filament(cx, cy, R0 * (1 + decal), amp_f,
                                 [(3, 0.55, ph * 1.3 + phi), (5, 0.30, -ph * 0.9 + 2 * phi),
                                  (2, 0.15, ph * 0.6 + 3 * phi)])
            ligne(surf, teinte(0.3 * force), True, pts, max(2, int(4 * s)))
            aaligne(surf, teinte(force), True, pts)
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
            self._reflet(surf, teinte, blanc, contour, time.time(), decalage=4.0)

        self._couronne(surf, teinte, blanc, eclat, e, t, dt, cx, cy, Rext)
        self._zone_compacte = None
        if self._forme > 0.75 and naissance >= 1 and self._fermeture is None:
            self._panneau(surf, teinte, blanc, eclat, titre, cx, dt)
        elif PANNEAU_COMPACT and src.AFFICHER_SYSTEME and naissance >= 1 and self._fermeture is None:
            # mode discret : un petit panneau juste sous le réacteur, avec seulement les jauges
            self._panneau_compact(surf, teinte, blanc, e, t, cx, cy + Rext + 5 * self.s, dt)

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
                    force = 0.12 * R * min(1.0, distance / (1.2 * R)) * min(1.0, (R * 5 - distance) / (R * 1.5))
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
        visibles = n if self._naissance >= 1 else int(n * self._naissance)   # au lancement, elles apparaissent une à une
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

    def _panneau(self, surf, teinte, blanc, eclat, titre, cx, dt=0.05):
        src, s = self.src, self.s
        yb = self.m + self.d
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
        surf.blit(image, image.get_rect(center=(cx, yt)))
        demi = image.get_width() / 2 + 10 * s
        # L'heure, à droite du titre quand il reste de la place
        heure = self._texte(self.police_jauge, time.strftime("%H:%M"), teinte(0.6))
        fin_ligne = x1 - 12 * s
        if cx + demi + heure.get_width() + 22 * s < x1:
            surf.blit(heure, heure.get_rect(midright=(x1 - 10 * s, yt)))
            fin_ligne = x1 - 16 * s - heure.get_width()
        if cx - demi > x0 + k + 6 * s:
            pygame.draw.line(surf, teinte(0.45), (x0 + k + 4 * s, yt), (cx - demi, yt))
            pygame.draw.line(surf, teinte(0.45), (cx + demi, yt), (fin_ligne, yt))

        age = time.time() - src.texte_depuis
        visible = bool(src.texte_actuel) and age < src.DUREE_TEXTE
        if src.AFFICHER_SYSTEME:
            jauges = self._mesures()
            colonne = (x1 - x0 - 14 * s) / len(jauges)
            nb = 12 if len(jauges) <= 2 else 8
            ecart = 1.5 * s
            large = (colonne * 0.84 - (nb - 1) * ecart) / nb
            eteint = teinte(0.16)
            couleurs_veille = self._couleurs_jauges(len(jauges))
            for i, (nom, valeur, unite) in enumerate(jauges):
                xc = x0 + 7 * s + colonne * (i + 0.5)
                couleur = ((255, 77, 77) if valeur >= 90 else (255, 165, 58) if valeur >= 75
                           else couleurs_veille[i] if couleurs_veille else teinte(0.95))
                police = self.police_jauge if len(jauges) <= 4 else self.police_jauge_petite
                self._etiquette(surf, police, nom, valeur, unite, couleur, xc, yb + 36 * s)
                # Les segments glissent vers la nouvelle valeur au lieu de sauter
                lisse = self._jauges.get(nom, valeur)
                lisse += (valeur - lisse) * (1 - math.exp(-dt * 6))
                self._jauges[nom] = lisse
                allumes = math.ceil(lisse / 100 * nb - 0.001) if lisse >= 1 else 0
                xa = xc - (nb * large + (nb - 1) * ecart) / 2
                ya, yz = yb + 44.5 * s, yb + 50 * s
                for j in range(nb):
                    xj = xa + j * (large + ecart)
                    pygame.draw.polygon(surf, couleur if j < allumes else eteint,
                                        [(xj + 1.5 * s, ya), (xj + large + 1.5 * s, ya),
                                         (xj + large, yz), (xj, yz)])
        if not visible:
            rappel = self._prochain_rappel()
            if rappel:
                quand, _, message = rappel
                reste = quand - time.time()
                if reste < 3600:
                    moment = "dans %d:%02d" % (max(0, reste) // 60, max(0, reste) % 60)
                else:
                    moment = "à " + time.strftime("%H:%M", time.localtime(quand))
                message = re.sub(r"^Rappel : |\.$", "", message)
                if message.startswith("Le minuteur") or message.startswith("Il est"):
                    message = "minuteur" if message.startswith("Le minuteur") else "rappel"
                contenu = f"{moment} · {message}"
                if len(contenu) > 44:
                    contenu = contenu[:43] + "…"
                image = self._texte(self.police_texte, contenu, teinte(0.7, blanc))
                surf.blit(image, image.get_rect(center=(cx, yb + (60 if src.AFFICHER_SYSTEME else 32) * s)))
        if visible:
            fondu = 1.0 if age < src.DUREE_TEXTE - 2 else max(0.0, (src.DUREE_TEXTE - age) / 2)
            if getattr(src, "texte_en_direct", False) and src.etat_actuel == "ecoute":
                # pendant l'écoute : les mots au fil de l'eau, avec un curseur qui clignote
                contenu = src.texte_actuel + (" |" if int(time.time() * 2.5) % 2 else "  ")
                fondu = 1.0
            else:
                contenu = "« " + src.texte_actuel + " »"
            image = self._texte(self.police_texte, contenu, teinte(0.85 * fondu, blanc))
            surf.blit(image, image.get_rect(center=(cx, yb + (60 if src.AFFICHER_SYSTEME else 32) * s)))

    def _couleurs_jauges(self, nombre):
        """En veille avec les couleurs Vice City : une teinte du dégradé par jauge (sinon None)."""
        palette = getattr(self.src, "COULEURS_VEILLE", None)
        if not palette or self.src.etat_actuel != "veille":
            return None
        couleurs = [_rgb(c) for c in palette]
        decalage = time.time() / max(1.0, getattr(self.src, "CYCLE_VEILLE", 12))
        return [tuple(int(c) for c in _degrade(couleurs, decalage + i * len(couleurs) / nombre))
                for i in range(nombre)]

    def _reflet(self, surf, teinte, blanc, points, t, decalage=0.0):
        """Un reflet de lumière fait tout le tour d'un contour (panneau ou cercle du réacteur), puis une
        courte pause avant le tour suivant. points : les sommets du contour, dans l'ordre."""
        S = self.s
        pts = [(float(x), float(y)) for x, y in points]
        longueurs = [math.hypot(pts[(i + 1) % len(pts)][0] - pts[i][0], pts[(i + 1) % len(pts)][1] - pts[i][1])
                     for i in range(len(pts))]
        total = sum(longueurs)
        if total < 1:
            return
        tour = total / (VITESSE_REFLET * S) + PAUSE_REFLET           # secondes pour un tour, pause comprise
        avance = ((t + decalage) % tour) * VITESSE_REFLET * S
        if PAUSE_REFLET <= 0:
            avance += total                    # sans pause : la traîne continue sur le tour précédent
        elif avance > total + LONGUEUR_REFLET * S:
            return

        def point(d):
            d %= total
            for i, l in enumerate(longueurs):
                if d <= l or i == len(longueurs) - 1:
                    a, b = pts[i], pts[(i + 1) % len(pts)]
                    f = d / l if l else 0.0
                    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
                d -= l
            return pts[0]

        morceaux = 8
        pas = LONGUEUR_REFLET * S / morceaux
        epais = max(1, int(1.7 * S))
        for k in range(morceaux):
            d1, d2 = avance - k * pas, avance - (k + 1) * pas
            if d1 <= 0:
                break
            if d1 > total and PAUSE_REFLET > 0:         # la tête a fini le tour : seule la traîne finit de passer
                continue
            force = 0.95 * (1 - k / morceaux) ** 1.4
            depart = max(0.0, d2)
            # on suit le contour même dans les angles (plusieurs petits traits)
            n = max(1, int((d1 - depart) / (3 * S)))
            prec = point(depart)
            for m in range(1, n + 1):
                cour = point(depart + (d1 - depart) * m / n)
                pygame.draw.line(surf, teinte(force, blanc), prec, cour, epais)
                prec = cour

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
        return jauges

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
