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
"""

import ctypes
import math
import os
import random
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


class RECT(ctypes.Structure):
    _fields_ = [("gauche", ctypes.c_long), ("haut", ctypes.c_long),
                ("droite", ctypes.c_long), ("bas", ctypes.c_long)]


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _melange(c1, c2, t):
    return (c1[0] + (c2[0] - c1[0]) * t, c1[1] + (c2[1] - c1[1]) * t, c1[2] + (c2[2] - c1[2]) * t)


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
        self._onde = -10.0                         # moment du dernier réveil (onde qui part du cœur)
        self._niveaux = np.zeros(NB_GRADUATIONS)   # hauteur lissée de chaque graduation
        self._jauges = {}                          # valeurs lissées des jauges
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
            os._exit(0)

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
        cible, vitesse, _, titre = src.ETATS[e]
        self.couleur = _melange(self.couleur, _rgb(cible), 1 - math.exp(-dt * 4))
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
        else:
            amplitude, eclat = 0.10, 0.8
        self._amp += (amplitude - self._amp) * (1 - math.exp(-dt * 14))
        amplitude = self._amp
        self.angle += vitesse * 0.6 * dt
        ph = self.angle

        if e != self._etat_prec:
            if e == "ecoute" or (e == "reponse" and self._etat_prec != "traitement"):
                self._onde = maintenant
            self._etat_prec = e

        cx, cy = self.w / 2, self.m + self.d / 2
        Rext = self.d / 2 - 2 * s          # bord de la couronne de graduations
        R = Rext * 0.83                    # le réacteur lui-même
        R0 = R * 0.68
        ligne, aaligne, cercle = pygame.draw.lines, pygame.draw.aalines, self._cercle
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
            pts = self._filament(cx, cy, R0 * (0.50 + 0.03 * f), amplitude * 0.8,
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
                       (cx + r * math.cos(q["a"]), cy + r * math.sin(q["a"])), (0.7 + 0.7 * scint) * s)

        # Cœur lumineux
        rc = R * (0.10 + 0.05 * voix) if e == "reponse" else R * (0.10 + 0.01 * math.sin(t * 3))
        for k, force in ((1.6, 0.10), (1.25, 0.2), (1.0, 0.32)):
            cercle(surf, teinte(force * eclat), (cx, cy), rc * k)
        cercle(surf, teinte(0.8 * eclat), (cx, cy), rc, max(1, int(1.2 * s)))
        if e == "traitement":
            r = rc * 0.65
            for i in range(3):
                debut = ph * 6 + i * (2 * math.pi / 3)
                pygame.draw.arc(surf, teinte(1.0, blanc), (cx - r, cy - r, 2 * r, 2 * r),
                                debut, debut + math.pi / 3, max(2, int(2 * s)))
        else:
            cercle(surf, teinte(0.9 * eclat, blanc), (cx, cy), rc * 0.28)

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

        # Onde de réveil : un cercle part du cœur et s'efface en atteignant le bord
        age = maintenant - self._onde
        if 0 <= age < 0.8:
            p = age / 0.8
            cercle(surf, teinte((1 - p) ** 1.5, blanc), (cx, cy), R * (0.12 + 0.8 * (1 - (1 - p) ** 2)),
                   max(1, int(2 * s)))

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

        self._couronne(surf, teinte, blanc, eclat, e, t, dt, cx, cy, Rext)
        self._panneau(surf, teinte, blanc, eclat, titre, cx, dt)

    def _couronne(self, surf, teinte, blanc, eclat, e, t, dt, cx, cy, Rext):
        """Couronne de graduations autour du réacteur : elle dessine le spectre du son en direct."""
        s, n = self.s, NB_GRADUATIONS
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
        else:                              # veille : une lente respiration parcourt la couronne
            cible = 0.12 + 0.10 * np.sin(t * 1.1 + np.arange(n) * (4 * math.pi / n))
        monte = cible > self._niveaux
        self._niveaux += (cible - self._niveaux) * np.where(monte, 1 - math.exp(-dt * 30), 1 - math.exp(-dt * 9))
        niveaux = np.clip(self._niveaux, 0, 1)

        r0 = Rext * 0.915
        longueurs = Rext * (0.018 + 0.067 * niveaux)
        longueurs[::6] += Rext * 0.012                 # une graduation sur six est plus longue
        rot = t * 0.05
        cr, sr = math.cos(rot), math.sin(rot)
        gc = self._grad_cos * cr - self._grad_sin * sr
        gs = self._grad_sin * cr + self._grad_cos * sr
        x0, y0 = cx + r0 * gc, cy + r0 * gs
        x1, y1 = cx + (r0 + longueurs) * gc, cy + (r0 + longueurs) * gs
        epais = max(1, int(1.6 * s))
        forces = np.minimum(1.0, 0.50 + 0.60 * niveaux) * (0.75 + 0.25 * eclat)
        trait = pygame.draw.line
        for i in range(n):
            f = forces[i]
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
        pygame.draw.lines(surf, teinte(1.0), False, [(x1 - e, y0), (x1, y0), (x1, y0 + e)], ep)
        pygame.draw.lines(surf, teinte(1.0), False, [(x0, y1 - e), (x0, y1), (x0 + e, y1)], ep)

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
            m = jarvis_systeme.mesures
            jauges = [("CPU", m["cpu"], "%"), ("RAM", m["ram"], "%")]
            if m.get("gpu") is not None:
                jauges.append(("GPU", m["gpu"], "%"))
            jauges.append(("NET", m.get("reseau", 0.0), "%"))
            if m.get("temp") is not None:
                jauges.append(("TMP", m["temp"], "°"))
            colonne = (x1 - x0 - 14 * s) / len(jauges)
            nb = 12 if len(jauges) <= 2 else 8
            ecart = 1.5 * s
            large = (colonne * 0.84 - (nb - 1) * ecart) / nb
            eteint = teinte(0.16)
            for i, (nom, valeur, unite) in enumerate(jauges):
                xc = x0 + 7 * s + colonne * (i + 0.5)
                couleur = ((255, 77, 77) if valeur >= 90 else (255, 165, 58) if valeur >= 75
                           else teinte(0.95))
                police = self.police_jauge if len(jauges) <= 4 else self.police_jauge_petite
                image = self._texte(police, f"{nom} {valeur:.0f}{unite}", couleur)
                surf.blit(image, image.get_rect(center=(xc, yb + 36 * s)))
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

    # ---------- Boucle ----------

    def lancer(self):
        src = self.src
        horloge = pygame.time.Clock()
        while True:
            self._evenements()
            self.image()
            pygame.display.flip()
            maintenant = time.time()
            if maintenant - self._dernier_premier_plan > 1:
                self._dernier_premier_plan = maintenant
                self._premier_plan()
            actif = (src.etat_actuel in ("ecoute", "traitement", "reponse", "erreur")
                     or self.glisse is not None or maintenant - src.texte_depuis < 1)
            if actif:
                self._dernier_actif = maintenant
                images = src.IMAGES_ACTIF
            elif maintenant - self._dernier_actif < 30:
                images = src.IMAGES_VEILLE
            else:
                images = src.IMAGES_VEILLE_LONGUE
            horloge.tick(images)
