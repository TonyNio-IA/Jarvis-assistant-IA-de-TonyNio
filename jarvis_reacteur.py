"""
JARVIS - le réacteur.

Affiche un cercle animé façon réacteur, toujours au premier plan, qui montre
l'état de Jarvis :
  - En veille     : bleu-cyan faible, rotation lente
  - Je t'écoute   : cyan vif, pulsation
  - Je réfléchis  : orange, rotation rapide
  - Je réponds    : bleu, le cœur vibre comme une voix
  - Erreur        : rouge clignotant
  - En pause      : violet, pendant que Claude lit un message (F9)
Sous le réacteur : ce que Jarvis a compris, puis la charge du processeur,
la mémoire utilisée et le débit du réseau, en temps réel.

Lancement :  python C:\\Jarvis\\jarvis_reacteur.py
Déplacer   :  clic gauche maintenu sur le réacteur
Quitter    :  clic droit sur le réacteur, puis « Arrêter Jarvis »
"""

import ctypes
import math
import random
import os
import socket
import sys
import threading
import time
import tkinter as tk

import numpy as np

# Image nette sur écran 4K (doit être fait avant de créer la fenêtre)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

DOSSIER = os.path.dirname(os.path.abspath(__file__))

# Lancé sans console (pythonw, au démarrage de Windows) : messages dans un journal
if sys.stdout is None or sys.stderr is None:
    _chemin = os.path.join(DOSSIER, "jarvis.log")
    try:                                   # le journal ne grossit pas indéfiniment
        if os.path.getsize(_chemin) > 1_000_000:
            with open(_chemin, "rb") as f:
                f.seek(-300_000, 2)
                _fin = f.read()
            with open(_chemin, "wb") as f:
                f.write(_fin[_fin.find(b"\n") + 1:])
    except OSError:
        pass
    journal = open(os.path.join(DOSSIER, "jarvis.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = journal
    print("\n=====", time.strftime("%d/%m/%Y %H:%M:%S"), "démarrage de Jarvis =====")

# Un seul Jarvis à la fois : si un autre tourne déjà, on s'arrête
_verrou = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    _verrou.bind(("127.0.0.1", 47821))
except OSError:
    print("Jarvis est déjà lancé.")
    sys.exit(0)

sys.path.insert(0, DOSSIER)
import jarvis_claude  # noqa: E402
import jarvis_voix    # noqa: E402
import jarvis_systeme  # noqa: E402

# ===== Réglages =====
TAILLE = 220            # taille du réacteur (avant mise à l'échelle de l'écran)
MARGE_DROITE = 40
MARGE_BAS = 140         # au-dessus de la barre des tâches
TRANSPARENT = "#010203" # couleur rendue invisible autour du cercle
FOND = "#05090e"
NB_PARTICULES = 70      # nombre de particules lumineuses
STYLE = "anneau"        # "anneau" = anneau de filaments ondulants, "hud" = ancien style viseur
NB_FILAMENTS = 9        # nombre de filaments qui forment l'anneau
NB_FILAMENTS_INT = 4    # filaments plus fins à l'intérieur
NB_FILAMENTS_BORD = 3   # filaments fins qui forment le bord extérieur
NB_POUSSIERE = 40       # particules lumineuses à l'intérieur de l'anneau
AFFICHER_SYSTEME = True # processeur, mémoire et réseau sous le réacteur
IMAGES_ACTIF = 30       # images par seconde quand Jarvis écoute, réfléchit ou répond
IMAGES_VEILLE = 10      # images par seconde en veille (économise le processeur)
IMAGES_VEILLE_LONGUE = 5   # après 30 secondes de veille : animation encore plus économe

ETATS = {
    #  nom          couleur      vitesse  pulsation  texte
    "veille":     ("#23a596",   0.25,    0.04,      "En veille"),
    "ecoute":     ("#4ff2dc",   0.8,     0.12,      "Je t'écoute"),
    "traitement": ("#ffa53a",   3.0,     0.06,      "Je réfléchis"),
    "reponse":    ("#4fb4ff",   1.0,     0.0,       "Je réponds"),
    "erreur":     ("#ff3b3b",   0.4,     0.0,       "Erreur"),
    "pause":      ("#8a7fd6",   0.15,    0.02,      "En pause (lecture)"),
    "demarrage":  ("#6c7a89",   0.5,     0.03,      "Démarrage..."),
}
# ====================

etat_actuel = "demarrage"
texte_actuel = ""          # ce que Jarvis a compris, affiché sous le réacteur
texte_depuis = 0.0
DUREE_TEXTE = 12           # secondes d'affichage


def changer_texte(texte):
    global texte_actuel, texte_depuis
    texte = " ".join(str(texte).split())
    texte_actuel = texte if len(texte) <= 70 else texte[:67] + "..."
    texte_depuis = time.time()


def changer_etat(nom):
    global etat_actuel
    if nom in ETATS:
        etat_actuel = nom


def hex_vers_rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def rgb_vers_hex(r, g, b):
    return "#%02x%02x%02x" % (int(r), int(g), int(b))


def melange(c1, c2, t):
    return tuple(a + (b - a) * t for a, b in zip(c1, c2))


class Reacteur:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Jarvis")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass

        echelle = self.root.winfo_fpixels("1i") / 96.0
        self.s = echelle
        self.d = int(TAILLE * echelle)
        self.m = int((30 if STYLE == "hud" else 4) * echelle)   # marge (particules du style hud)
        self.w = self.d + 2 * self.m
        self.h = int(self.d + 2 * self.m + (106 if AFFICHER_SYSTEME else 74) * echelle)
        jarvis_systeme.demarrer()
        x = self.root.winfo_screenwidth() - self.w - int(MARGE_DROITE * echelle)
        y = self.root.winfo_screenheight() - self.h - int(MARGE_BAS * echelle)
        self.root.geometry(f"{self.w}x{self.h}+{x}+{y}")

        # Particules : angle, distance au centre (en fraction du rayon), vitesse, taille
        self.particules = [self._nouvelle_particule(random.uniform(0.2, 1.2))
                           for _ in range(NB_PARTICULES)]
        self.t_prec = time.time()

        self.c = tk.Canvas(self.root, width=self.w, height=self.h,
                           bg=TRANSPARENT, highlightthickness=0)
        self.c.pack()

        self.couleur = hex_vers_rgb(ETATS["demarrage"][0])
        self.angle = 0.0
        self.t0 = time.time()

        # Déplacement et menu
        self.c.bind("<ButtonPress-1>", self._debut_deplacement)
        self.c.bind("<B1-Motion>", self._deplacer)
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label=f"Jarvis version {jarvis_claude.VERSION}", state="disabled")
        self.menu.add_separator()
        self.menu.add_command(label="Nouvelle conversation",
                              command=jarvis_claude.oublier_conversation)
        self.menu.add_separator()
        self.menu.add_command(label="Arrêter Jarvis", command=self.quitter)
        self.c.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

    def _debut_deplacement(self, e):
        self._dx, self._dy = e.x, e.y

    def _deplacer(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def quitter(self):
        self.root.destroy()
        os._exit(0)

    def dessiner(self):
        if STYLE == "hud":
            self._dessiner_hud()
        else:
            self._dessiner_anneau()
        actif = (etat_actuel in ("ecoute", "traitement", "reponse", "erreur")
                 or time.time() - texte_depuis < 1)
        if actif:
            self._dernier_actif = time.time()
            images = IMAGES_ACTIF
        elif time.time() - getattr(self, "_dernier_actif", 0) < 30:
            images = IMAGES_VEILLE
        else:
            images = IMAGES_VEILLE_LONGUE
        self.root.after(int(1000 / images), self.dessiner)

    # ---------- Style « anneau » : objets créés une seule fois, puis déplacés ----------

    def _init_anneau(self):
        c, s = self.c, self.s
        n = self.n_pts = 160      # assez de points pour une courbe lisse sans « smooth » (très lent)
        th = np.arange(n + 1) * (2 * math.pi / n)
        self.cos_t, self.sin_t = np.cos(th), np.sin(th)
        # sin(kθ) et cos(kθ) précalculés, et calculs faits d'un bloc avec numpy
        self.harm = {k: (np.sin(k * th), np.cos(k * th)) for k in (2, 3, 4, 5, 7)}
        self._cfg_cache = {}     # dernier réglage de chaque objet : on ne renvoie que ce qui change
        self._pos_cache = {}

        # Carte sombre sous le réacteur (texte lisible sur n'importe quel fond d'écran)
        x0, x1 = 5 * s, self.w - 5 * s
        y0, y1 = self.m + self.d + 5 * s, self.h - 3 * s
        r = 12 * s
        self.it_carte = c.create_polygon(
            x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
            x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0, smooth=True, fill=FOND)
        self.it_sys = None
        if AFFICHER_SYSTEME:
            yb = self.m + self.d
            largeur = 64 * s
            self.it_sys = {}
            for nom, x in (("cpu", self.w * 0.27), ("ram", self.w * 0.73)):
                texte = c.create_text(x, yb + 70 * s, font=("Segoe UI", 8, "bold"))
                c.create_rectangle(x - largeur / 2, yb + 79 * s, x + largeur / 2, yb + 82 * s,
                                   fill="#16232b", outline="")
                barre = c.create_rectangle(0, 0, 0, 0, outline="")
                self.it_sys[nom] = (texte, barre, x - largeur / 2, yb + 79 * s, largeur, 3 * s)
            self.it_reseau = c.create_text(self.w / 2, yb + 93 * s, font=("Segoe UI", 8))

        self.it_fond = [c.create_oval(0, 0, 0, 0, outline="") for _ in range(7)]
        self.it_bord = [(c.create_line(0, 0, 1, 1), c.create_line(0, 0, 1, 1))
                        for _ in range(NB_FILAMENTS_BORD)]
        self.it_int = [(c.create_line(0, 0, 1, 1),
                        c.create_line(0, 0, 1, 1)) for _ in range(NB_FILAMENTS_INT)]
        self.it_poussiere = [c.create_oval(0, 0, 0, 0, outline="") for _ in range(NB_POUSSIERE)]
        self.poussiere = [{"a": random.uniform(0, 2 * math.pi), "r": random.uniform(0.15, 0.5),
                           "v": random.uniform(0.6, 1.4), "p": random.uniform(0, 6.3)}
                          for _ in range(NB_POUSSIERE)]
        self.it_coeur = [c.create_oval(0, 0, 0, 0, outline="") for _ in range(3)]
        self.it_coeur_bord = c.create_oval(0, 0, 0, 0, fill="")
        self.it_arcs = [c.create_arc(0, 0, 1, 1, style="arc", extent=60) for _ in range(3)]
        self.it_point = c.create_oval(0, 0, 0, 0, outline="")
        self.it_fil = [(c.create_line(0, 0, 1, 1),
                        c.create_line(0, 0, 1, 1)) for _ in range(NB_FILAMENTS)]
        self.idx_points = [list(range(f % 6, n, 6)) for f in range(NB_FILAMENTS)]
        self.it_points = [[c.create_oval(0, 0, 0, 0, outline="") for _ in idx]
                          for idx in self.idx_points]
        self.it_texte = c.create_text(0, 0, font=("Segoe UI", 11, "bold"))
        self.it_sous_titre = c.create_text(0, 0, font=("Segoe UI", 8), anchor="n",
                                           justify="center", width=self.w - 26 * s)
        self._voix = 0.0
        self._micro = 0.0
        self._amp = 0.1
        self._anneau_pret = True

    def _filament(self, cx, cy, rayon, amp, harmoniques):
        """Filament fermé : rayon * (1 + amp * somme d'ondes).
        Renvoie (coordonnées à plat pour le dessin, liste des x, liste des y)."""
        onde = 0.0
        for k, poids, ph in harmoniques:
            sk, ck = self.harm[k]
            onde = onde + sk * (poids * math.cos(ph)) + ck * (poids * math.sin(ph))
        r = rayon * (1 + amp * onde)
        xs, ys = cx + r * self.cos_t, cy + r * self.sin_t
        plat = np.empty(2 * len(xs))
        plat[0::2], plat[1::2] = xs, ys
        return plat.tolist(), xs.tolist(), ys.tolist()

    def _dessiner_anneau(self):
        """Anneau de filaments ondulants, cœur lumineux et poussière intérieure."""
        if not getattr(self, "_anneau_pret", False):
            self._init_anneau()
        c, s = self.c, self.s
        t = time.time() - self.t0
        dt = min(0.25, time.time() - self.t_prec)
        cache = self._cfg_cache

        def cfg(it, **kw):
            if cache.get(it) != kw:
                cache[it] = kw
                c.itemconfigure(it, **kw)

        self.t_prec = time.time()
        couleur_cible, vitesse, pulsation, texte = ETATS[etat_actuel]
        self.couleur = melange(self.couleur, hex_vers_rgb(couleur_cible), 0.12)
        base = self.couleur
        e = etat_actuel
        if e == "erreur":
            base = melange(base, hex_vers_rgb(FOND), 0.45 + 0.45 * math.sin(t * 6))
        fond = hex_vers_rgb(FOND)
        blanc = melange(base, (255, 255, 255), 0.55)

        def teinte(force, vers=None):
            r, g, b = melange(fond, vers or base, max(0.0, min(1.0, force)))
            return "#%02x%02x%02x" % (int(r) & 252, int(g) & 252, int(b) & 252)

        # L'anneau suit le vrai son : la voix de Jarvis quand il répond, ton micro quand il écoute
        self._voix += (min(1.0, jarvis_voix.niveau * 1.6) - self._voix) * 0.45
        self._micro += (min(1.0, jarvis_claude.niveau_micro * 5) - self._micro) * 0.3
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
        self._amp += (amplitude - self._amp) * 0.4
        amplitude = self._amp
        self.angle += vitesse * 0.6 * dt
        ph = self.angle

        cx = cy = self.m + self.d / 2
        R = self.d / 2 - 3 * s
        R0 = R * 0.68

        positions = self._pos_cache

        def place(it, r, x=cx, y=cy):
            cle = (round(x, 1), round(y, 1), round(r, 1))
            if positions.get(it) != cle:
                positions[it] = cle
                c.coords(it, x - r, y - r, x + r, y + r)

        # Fond : dégradé sombre, plus lumineux au centre, et fin liseré
        for k, it in enumerate(self.it_fond):
            r = R * (len(self.it_fond) - k) / len(self.it_fond)
            place(it, r)
            cfg(it, fill=teinte(0.03 + k * 0.022 * eclat))
        # Anneau extérieur : fins filaments qui ondulent au bord du cercle
        for f, (halo, ligne) in enumerate(self.it_bord):
            phi = f * 2.2
            plat, xs, ys = self._filament(cx, cy, R * (0.955 - 0.012 * f), 0.018 + amplitude * 0.1,
                                 [(4, 0.6, ph * 0.7 + phi), (7, 0.4, -ph * 1.1 + 2 * phi)])
            c.coords(halo, *plat)
            c.coords(ligne, *plat)
            force = (0.35 + 0.2 * math.sin(t * 0.8 + phi)) * eclat
            cfg(halo, fill=teinte(0.12 * eclat), width=3 * s)
            cfg(ligne, fill=teinte(force), width=1 * s)

        # Filaments intérieurs, plus fins, qui tournent en sens inverse
        for f, (halo, ligne) in enumerate(self.it_int):
            phi = f * 1.9
            plat, xs, ys = self._filament(cx, cy, R0 * (0.50 + 0.03 * f), amplitude * 0.8,
                                 [(2, 0.6, -ph * 0.8 + phi), (4, 0.4, ph * 0.5 + 2 * phi)])
            c.coords(halo, *plat)
            c.coords(ligne, *plat)
            force = (0.35 + 0.15 * math.sin(t * 0.9 + phi)) * eclat
            cfg(halo, fill=teinte(0.15 * force * 2), width=3 * s)
            cfg(ligne, fill=teinte(force), width=1 * s)

        # Poussière lumineuse, uniquement à l'intérieur de l'anneau
        for q, it in zip(self.poussiere, self.it_poussiere):
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
            r = q["r"] * R0
            x, y = cx + r * math.cos(q["a"]), cy + r * math.sin(q["a"])
            scint = 0.5 + 0.5 * math.sin(t * 3 * q["v"] + q["p"])
            bord = min(1.0, (0.55 - q["r"]) / 0.1, (q["r"] - 0.1) / 0.06)
            force = max(0.0, scint * bord) * eclat
            place(it, (0.7 + 0.7 * scint) * s, x, y)
            cfg(it, fill=teinte(force * 0.9, blanc),
                            state="normal" if force > 0.1 else "hidden")

        # Cœur lumineux
        if e == "reponse":
            rc = R * (0.10 + 0.05 * voix)
        else:
            rc = R * (0.10 + 0.01 * math.sin(t * 3))
        for it, (k, force) in zip(self.it_coeur, ((1.6, 0.10), (1.25, 0.2), (1.0, 0.32))):
            place(it, rc * k)
            cfg(it, fill=teinte(force * eclat))
        place(self.it_coeur_bord, rc)
        cfg(self.it_coeur_bord, outline=teinte(0.8 * eclat), width=1.2 * s)
        place(self.it_point, rc * 0.28)
        cfg(self.it_point, fill=teinte(0.9 * eclat, blanc),
                        state="hidden" if e == "traitement" else "normal")
        for i, it in enumerate(self.it_arcs):
            if e == "traitement":
                place(it, rc * 0.65)
                cfg(it, state="normal", start=-math.degrees(ph) * 6 + i * 120,
                                outline=teinte(1.0, blanc), width=2 * s)
            else:
                cfg(it, state="hidden")

        # Anneau principal de filaments, avec ses particules
        for f, (halo, ligne) in enumerate(self.it_fil):
            phi = f * 2.399
            force = (0.6 + 0.4 * (0.5 + 0.5 * math.sin(t * 0.7 + phi))) * eclat
            amp_f = amplitude * (0.6 + 0.8 * ((f * 0.37) % 1))
            decal = 0.05 * math.sin(phi * 1.7 + t * 0.5)
            plat, xs, ys = self._filament(cx, cy, R0 * (1 + decal), amp_f,
                                 [(3, 0.55, ph * 1.3 + phi), (5, 0.30, -ph * 0.9 + 2 * phi),
                                  (2, 0.15, ph * 0.6 + 3 * phi)])
            c.coords(halo, *plat)
            c.coords(ligne, *plat)
            cfg(halo, fill=teinte(0.3 * force), width=4 * s)
            cfg(ligne, fill=teinte(force), width=1.2 * s)
            for i, it in zip(self.idx_points[f], self.it_points[f]):
                scint = 0.5 + 0.5 * math.sin(t * 4 + i * 0.7 + phi)
                if scint < 0.35:
                    cfg(it, state="hidden")
                    continue
                x, y = xs[i], ys[i]
                place(it, (0.9 + 0.9 * scint) * s, x, y)
                cfg(it, state="normal", fill=teinte(force * scint, blanc))

        cfg(self.it_carte, outline=teinte(0.3 * eclat), width=1 * s)
        if self.it_sys:
            m = jarvis_systeme.mesures
            for nom, valeur in (("cpu", m["cpu"]), ("ram", m["ram"])):
                texte_it, barre, bx, by, largeur, hauteur = self.it_sys[nom]
                couleur = "#ff4d4d" if valeur >= 90 else "#ffa53a" if valeur >= 75 else teinte(0.9)
                cfg(texte_it, text=f"{nom.upper()} {valeur:.0f} %", fill=couleur)
                cfg(barre, fill=couleur)
                cle = round(valeur)
                if positions.get(barre) != cle:
                    positions[barre] = cle
                    c.coords(barre, bx, by, bx + largeur * min(100, valeur) / 100, by + hauteur)
            cfg(self.it_reseau, fill=teinte(0.7, blanc),
                text=f"↓ {jarvis_systeme.debit(m['recu'])}    ↑ {jarvis_systeme.debit(m['envoye'])}")
        c.coords(self.it_texte, cx, self.m + self.d + 19 * s)
        cfg(self.it_texte, text=texte, fill=teinte(1.0))
        age = time.time() - texte_depuis
        visible = texte_actuel and age < DUREE_TEXTE
        fondu = 1.0 if age < DUREE_TEXTE - 2 else max(0.0, (DUREE_TEXTE - age) / 2)
        c.coords(self.it_sous_titre, cx, self.m + self.d + 32 * s)
        cfg(self.it_sous_titre, text=("« " + texte_actuel + " »") if visible else "",
                        fill=teinte(0.75 * fondu, blanc))

    def _dessiner_hud(self):
        c, s = self.c, self.s
        t = time.time() - self.t0
        couleur_cible, vitesse, pulsation, texte = ETATS[etat_actuel]

        # Transition douce de couleur
        self.couleur = melange(self.couleur, hex_vers_rgb(couleur_cible), 0.12)
        base = self.couleur
        if etat_actuel == "erreur":
            base = melange(base, hex_vers_rgb(FOND), 0.5 + 0.5 * math.sin(t * 6))
        fond = hex_vers_rgb(FOND)

        def teinte(force):
            """force 1 = couleur vive, 0 = fond."""
            return rgb_vers_hex(*melange(fond, base, max(0.0, min(1.0, force))))

        vif = teinte(1.0)
        blanc = rgb_vers_hex(*melange(base, (255, 255, 255), 0.55))

        self.angle = (self.angle + vitesse * 1.6) % 360
        A = self.angle
        cx = cy = self.m + self.d / 2
        R = self.d / 2 - 3 * s

        if etat_actuel == "reponse":
            battement = 0.5 + 0.5 * abs(math.sin(t * 11)) * (0.6 + 0.4 * math.sin(t * 3.7))
        else:
            battement = 0.5 + 0.5 * math.sin(t * 3)

        c.delete("all")

        def cercle(r, **k):
            return c.create_oval(cx - r, cy - r, cx + r, cy + r, **k)

        def arc(r, debut, etendue, epaisseur, couleur, halo=True):
            if halo:
                c.create_arc(cx - r, cy - r, cx + r, cy + r, start=debut, extent=etendue,
                             style="arc", outline=teinte(0.25), width=epaisseur * 3 * s)
            c.create_arc(cx - r, cy - r, cx + r, cy + r, start=debut, extent=etendue,
                         style="arc", outline=couleur, width=epaisseur * s)

        def rayon(angle_deg, r1, r2, couleur, epaisseur=1):
            a = math.radians(angle_deg)
            c.create_line(cx + r1 * math.cos(a), cy - r1 * math.sin(a),
                          cx + r2 * math.cos(a), cy - r2 * math.sin(a),
                          fill=couleur, width=epaisseur * s)

        # Fond : disque sombre avec un léger dégradé lumineux vers le centre
        for k in range(10, 0, -1):
            cercle(R * k / 10, fill=teinte(0.04 + (10 - k) * 0.018), outline="")

        # Anneau extérieur fin + deux grands arcs épais qui tournent lentement
        cercle(R - 4 * s, outline=teinte(0.55), width=1.5 * s)
        arc(R - 9 * s, 20 + A * 0.3, 75, 5, vif)
        arc(R - 9 * s, 160 + A * 0.3, 50, 5, vif)
        arc(R - 9 * s, 245 + A * 0.3, 20, 5, teinte(0.7))

        # Graduations en éventail qui tournent en sens inverse
        r_ext, r_int = R - 22 * s, R - 34 * s
        for i in range(0, 360, 4):
            ang = i - A * 0.8
            secteur = (i % 360)
            if 40 <= secteur <= 150 or 200 <= secteur <= 250 or 290 <= secteur <= 335:
                long = r_int if i % 20 else r_int - 5 * s
                force = 0.45 + 0.4 * (0.5 + 0.5 * math.sin(math.radians(i * 3) + t * 2))
                rayon(ang, long, r_ext, teinte(force), 1.5)

        # Viseur : lignes horizontale et verticale interrompues au centre
        r_vis_ext, r_vis_int = R - 6 * s, R * 0.36
        for ang in (0, 90, 180, 270):
            rayon(ang, r_vis_int, r_vis_ext, teinte(0.35), 1)
        for ang in (0, 90, 180, 270):
            rayon(ang, R * 0.50, R * 0.56, vif, 2)

        # Anneaux intérieurs
        cercle(R * 0.62, outline=teinte(0.45), width=1 * s)
        cercle(R * 0.55, outline=teinte(0.8), width=1.5 * s)
        arc(R * 0.48, -A * 2.2, 100, 2, vif, halo=False)
        arc(R * 0.48, 180 - A * 2.2, 100, 2, vif, halo=False)

        # Cœur : halo lumineux
        rc = R * 0.30
        for k, force in ((1.25, 0.18), (1.1, 0.32), (0.95, 0.5)):
            cercle(rc * k, fill=teinte(force * (0.7 + 0.3 * battement)), outline="")

        if etat_actuel == "reponse":
            # Barres de voix au centre
            n = 9
            largeur = rc * 1.4 / n
            for i in range(n):
                x = cx - rc * 0.7 + largeur * (i + 0.5)
                centre = 1 - abs(i - (n - 1) / 2) / ((n - 1) / 2)
                h = rc * (0.15 + 0.75 * centre * abs(math.sin(t * 9 + i * 1.3)))
                c.create_rectangle(x - largeur * 0.3, cy - h, x + largeur * 0.3, cy + h,
                                   fill=blanc, outline="")
        elif etat_actuel == "traitement":
            # Arcs qui tournent vite autour d'un point central
            for i in range(3):
                arc(rc * 0.6, A * 4 + i * 120, 70, 3, blanc, halo=False)
            cercle(rc * 0.18, fill=blanc, outline="")
        else:
            r = rc * (0.42 + 0.12 * pulsation / 0.12 * battement if pulsation else 0.42)
            cercle(r, fill=vif, outline="")
            cercle(r * 0.55, fill=blanc, outline="")

        # Texte de l'état
        self._particules(cx, cy, R, base, battement)

        c.create_text(cx, self.m * 2 + self.d + 10 * s, text=texte, fill=vif,
                      font=("Segoe UI", 11, "bold"))

    def _nouvelle_particule(self, r):
        return {"a": random.uniform(0, 2 * math.pi), "r": r,
                "v": random.uniform(0.6, 1.4), "t": random.uniform(1.0, 2.6),
                "p": random.uniform(0, 2 * math.pi)}

    def _particules(self, cx, cy, R, base, battement, nombre=None):
        """Nuée de particules lumineuses dont le mouvement dépend de l'état."""
        maintenant = time.time()
        dt = min(0.1, maintenant - self.t_prec)
        self.t_prec = maintenant
        fond = hex_vers_rgb(FOND)
        blanc = melange(base, (255, 255, 255), 0.6)
        e = etat_actuel
        for q in self.particules[:nombre]:
            if e == "ecoute":          # aspirées vers le cœur
                q["a"] += 0.5 * q["v"] * dt
                q["r"] -= 0.35 * q["v"] * dt
                if q["r"] < 0.25:
                    q.update(self._nouvelle_particule(random.uniform(1.1, 1.25)))
            elif e == "traitement":    # tourbillon rapide
                q["a"] += 3.0 * q["v"] * dt
                q["r"] += math.sin(maintenant * 2 + q["p"]) * 0.15 * dt
                q["r"] = min(1.2, max(0.35, q["r"]))
            elif e == "reponse":       # jaillissent du cœur au rythme de la voix
                q["a"] += 0.3 * q["v"] * dt
                q["r"] += (0.25 + 0.9 * battement) * q["v"] * dt
                if q["r"] > 1.25:
                    q.update(self._nouvelle_particule(random.uniform(0.25, 0.35)))
            elif e == "erreur":        # agitation désordonnée
                q["a"] += random.uniform(-1, 1) * dt
                q["r"] += random.uniform(-0.3, 0.3) * dt
                q["r"] = min(1.2, max(0.3, q["r"]))
            else:                      # veille, pause, démarrage : lente dérive
                lent = 0.3 if e == "pause" else 1.0
                q["a"] += 0.12 * q["v"] * dt * lent
                q["r"] += math.sin(maintenant * 0.8 + q["p"]) * 0.03 * dt * lent
                if q["r"] < 0.3 or q["r"] > 1.22:
                    q["r"] = random.uniform(0.7, 1.1)
            # Scintillement et atténuation près des bords
            eclat = 0.55 + 0.45 * math.sin(maintenant * 3 * q["v"] + q["p"])
            if e in ("veille", "pause", "demarrage"):
                eclat *= 0.6
            bord = 1.0 if q["r"] < 1.0 else max(0.0, 1 - (q["r"] - 1.0) / 0.25)
            force = eclat * bord
            if force < 0.08:
                continue
            couleur = rgb_vers_hex(*melange(fond, blanc, force))
            x = cx + q["r"] * R * math.cos(q["a"])
            y = cy + q["r"] * R * math.sin(q["a"])
            t = q["t"] * self.s * (0.7 + 0.5 * force)
            self.c.create_oval(x - t, y - t, x + t, y + t, fill=couleur, outline="")

    def lancer(self):
        self.dessiner()
        self.root.mainloop()


def boucle_jarvis():
    try:
        jarvis_claude.main()
    except Exception as erreur:
        print("Erreur Jarvis :", erreur)
    changer_etat("erreur")


if __name__ == "__main__":
    jarvis_claude.afficher_etat = changer_etat
    jarvis_claude.afficher_texte = changer_texte
    reacteur = Reacteur()
    threading.Thread(target=boucle_jarvis, daemon=True).start()
    reacteur.lancer()
