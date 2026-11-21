# -*- coding: utf-8 -*-
"""
JARVIS - fenêtre du QR code (Wi-Fi invité, ou Jarvis sur la tablette).

Lancée par jarvis_freebox.py ou jarvis_tablette.py. Ce qu'il faut coder arrive par l'entrée standard (jamais
dans la ligne de commande ni dans un fichier). Le QR code est dessiné directement à l'écran, sans image
enregistrée. Il suffit de le viser avec l'appareil photo d'un téléphone ou d'une tablette.
Pour la tablette ("etapes": true), des écrans dessinés montrent quoi toucher à chaque étape.
La fenêtre se ferme toute seule après quelques minutes, ou d'un clic, ou avec Échap.
"""
import json
import sys
import tkinter as tk

import segno
from segno import helpers

ORANGE = "#ff7a00"          # ce qu'il faut toucher
BLEU = "#1a73e8"


# ---------- Petits outils de dessin (coordonnées en fractions de l'écran du téléphone) ----------

def _arrondi(c, x0, y0, x1, y1, r, **options):
    r = max(1, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
              x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(points, smooth=True, **options)


class _Ecran:
    def __init__(self, c, boite, s):
        self.c, self.s = c, s
        self.x0, self.y0, self.x1, self.y1 = boite

    def p(self, fx, fy):
        return self.x0 + fx * (self.x1 - self.x0), self.y0 + fy * (self.y1 - self.y0)

    def police(self, taille, gras=False):
        return ("Segoe UI", max(6, int(taille * self.s)), "bold" if gras else "normal")

    def fond(self, couleur):
        self.c.create_rectangle(self.x0, self.y0, self.x1, self.y1, fill=couleur, width=0)

    def bloc(self, fx0, fy0, fx1, fy1, couleur, rayon=4, contour=""):
        (a, b), (c_, d) = self.p(fx0, fy0), self.p(fx1, fy1)
        return _arrondi(self.c, a, b, c_, d, rayon * self.s, fill=couleur, outline=contour)

    def texte(self, fx, fy, texte, taille=8, couleur="#222", gras=False, ancre="center", largeur=0.9):
        x, y = self.p(fx, fy)
        self.c.create_text(x, y, text=texte, font=self.police(taille, gras), fill=couleur, anchor=ancre,
                           width=largeur * (self.x1 - self.x0), justify="center" if ancre == "center" else "left")

    def toucher(self, fx0, fy0, fx1, fy1):
        """Entoure en orange ce qu'il faut toucher, avec un rond pour le doigt."""
        (a, b), (c_, d) = self.p(fx0, fy0), self.p(fx1, fy1)
        m = 3 * self.s
        _arrondi(self.c, a - m, b - m, c_ + m, d + m, 6 * self.s, fill="", outline=ORANGE, width=max(2, int(3 * self.s)))
        r = 8 * self.s
        cx, cy = c_ + r * 0.1, d + r * 0.35
        self.c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=ORANGE, outline="white", width=max(1, int(2 * self.s)))


# ---------- Les écrans dessinés ----------

def _camera(e):
    e.fond("#4a4f57")
    e.bloc(0.22, 0.22, 0.78, 0.56, "white", 2)
    for fx, fy in ((0.27, 0.27), (0.6, 0.27), (0.27, 0.43)):
        e.bloc(fx, fy, fx + 0.12, fy + 0.08, "black", 1)
    for i in range(5):
        e.bloc(0.46 + 0.05 * (i % 3), 0.4 + 0.04 * i, 0.5 + 0.05 * (i % 3), 0.43 + 0.04 * i, "black", 0)
    e.bloc(0.12, 0.72, 0.88, 0.84, "white", 8)
    e.texte(0.5, 0.78, "Ouvrir le lien", 8, "#222", True)
    e.toucher(0.12, 0.72, 0.88, 0.84)


def _avertissement(e, deplie):
    e.fond("white")
    e.bloc(0, 0, 1, 0.08, "#eeeeee", 0)
    e.texte(0.06, 0.04, "https://192.168…", 6, "#c5221f", ancre="w")
    x, y = e.p(0.18, 0.2)
    t = 16 * e.s
    e.c.create_polygon(x - t / 2, y + t * 0.8, x + t / 2, y + t * 0.8, x, y - t * 0.1, fill="#c5221f", outline="")
    e.c.create_text(x, y + t * 0.45, text="!", fill="white", font=e.police(8, True))
    e.texte(0.08, 0.36, "Votre connexion n'est pas privée", 8, "#202124", True, ancre="w", largeur=0.86)
    if not deplie:
        e.texte(0.08, 0.5, "C'est normal : le certificat est fabriqué par Jarvis lui-même.", 6, "#5f6368", ancre="w", largeur=0.86)
        e.texte(0.07, 0.88, "Paramètres avancés", 6, BLEU, True, ancre="w", largeur=0.5)
        e.toucher(0.05, 0.84, 0.57, 0.92)
    else:
        e.texte(0.08, 0.5, "Ce serveur n'a pas pu prouver qu'il est bien 192.168…", 6, "#5f6368", ancre="w", largeur=0.86)
        e.texte(0.08, 0.67, "Continuer vers 192.168… (dangereux)", 6, BLEU, True, ancre="w", largeur=0.84)
        e.toucher(0.05, 0.6, 0.95, 0.74)
    e.bloc(0.62, 0.83, 0.94, 0.93, BLEU, 6)
    e.texte(0.78, 0.88, "Retour", 6, "white", True)


def _page_jarvis(e, laquelle):
    e.fond("#0d1b2a")
    x, y = e.p(0.5, 0.17)
    r = 13 * e.s
    e.c.create_oval(x - r, y - r, x + r, y + r, outline="#4fc3f7", width=max(2, int(3 * e.s)))
    e.texte(0.5, 0.33, "L'application Jarvis", 8, "white", True)
    e.bloc(0.1, 0.48, 0.9, 0.6, "#1e88e5", 6)
    e.texte(0.5, 0.54, "1. Télécharger et installer", 6, "white", True)
    e.bloc(0.1, 0.66, 0.9, 0.78, "#1e88e5", 6)
    e.texte(0.5, 0.72, "2. Ouvrir dans l'application", 6, "white", True)
    e.texte(0.5, 0.88, "Plus tard", 6, "#9fb3c8")
    if laquelle == 1:
        e.toucher(0.1, 0.48, 0.9, 0.6)
    else:
        e.toucher(0.1, 0.66, 0.9, 0.78)


def _source(e):
    e.fond("white")
    e.texte(0.08, 0.1, "Installer des applis inconnues", 8, "#202124", True, ancre="w", largeur=0.86)
    e.bloc(0.06, 0.3, 0.94, 0.46, "#f1f3f4", 6)
    e.texte(0.1, 0.38, "Autoriser cette source", 7, "#202124", ancre="w", largeur=0.6)
    e.bloc(0.72, 0.34, 0.9, 0.42, "#8ab4f8", 10)
    x, y = e.p(0.85, 0.38)
    r = 6 * e.s
    e.c.create_oval(x - r, y - r, x + r, y + r, fill=BLEU, outline="")
    e.toucher(0.7, 0.33, 0.92, 0.43)
    e.bloc(0.06, 0.62, 0.94, 0.86, "#f8f9fa", 6, contour="#dadce0")
    e.texte(0.5, 0.68, "Installer cette application ?", 6, "#202124", True)
    e.texte(0.72, 0.8, "Installer", 7, BLEU, True)
    e.toucher(0.52, 0.76, 0.92, 0.84)


ETAPES = (
    (_camera, "Vise le code avec l'appareil photo, puis touche le lien."),
    (lambda e: _avertissement(e, False), "Avertissement de sécurité : touche « Paramètres avancés »."),
    (lambda e: _avertissement(e, True), "Puis « Continuer vers… (dangereux) ». C'est bien Jarvis."),
    (lambda e: _page_jarvis(e, 1), "Touche « Télécharger et installer »."),
    (_source, "Si Android le demande : « Paramètres », « Autoriser cette source », puis « Installer »."),
    (lambda e: _page_jarvis(e, 2), "Reviens sur la page et touche « Ouvrir dans l'application »."),
)


def _etapes(parent, s):
    grille = tk.Frame(parent, bg="white")
    largeur, hauteur = int(130 * s), int(220 * s)
    for i, (dessin, legende) in enumerate(ETAPES):
        case = tk.Frame(grille, bg="white")
        case.grid(row=i // 3, column=i % 3, padx=int(8 * s), pady=int(6 * s), sticky="n")
        c = tk.Canvas(case, width=largeur + 8, height=hauteur + 8, bg="white", highlightthickness=0)
        c.pack()
        _arrondi(c, 4, 4, largeur + 4, hauteur + 4, 16 * s, fill="#202124", outline="")
        boite = (4 + 7 * s, 4 + 16 * s, largeur + 4 - 7 * s, hauteur + 4 - 16 * s)
        dessin(_Ecran(c, boite, s))
        legende = legende.replace("« ", "« ").replace(" »", " »")     # pas de guillemet seul en début de ligne
        tk.Label(case, text=f"{i + 1}. {legende}", font=("Segoe UI", max(8, int(10 * s))), bg="white", fg="#222",
                 wraplength=largeur + 20, justify="center").pack(pady=(2, 0))
    return grille


def _capturer(fen, chemin):
    try:
        import subprocess
        fen.update()
        x, y, l, h = fen.winfo_rootx(), fen.winfo_rooty(), fen.winfo_width(), fen.winfo_height()
        script = ("Add-Type -AssemblyName System.Drawing; "
                  "Add-Type -Name D -Namespace W -MemberDefinition '[DllImport(\"user32.dll\")] public static extern bool SetProcessDPIAware();'; "
                  "[void][W.D]::SetProcessDPIAware(); $e = [Drawing.Graphics]::FromHwnd([IntPtr]::Zero); $k = $e.DpiX / 96; "
                  f"$b = New-Object Drawing.Bitmap ([int]({l}*$k)),([int]({h}*$k)); $g = [Drawing.Graphics]::FromImage($b); "
                  f"$g.CopyFromScreen([int]({x}*$k),[int]({y}*$k),0,0,$b.Size); $b.Save('{chemin}')")
        subprocess.run(["powershell", "-NoProfile", "-Command", script], timeout=30)
    finally:
        fen.destroy()


def main():
    donnees = json.loads(sys.stdin.read() or "{}")
    reseau, cle = donnees.get("reseau", ""), donnees.get("cle", "")
    adresse = donnees.get("adresse", "")          # autre usage : une adresse à ouvrir (Jarvis sur la tablette)
    minutes = max(1, min(int(donnees.get("minutes", 5)), 30))
    if adresse:
        qr = segno.make(adresse, error="m")
    elif reseau and cle:
        qr = helpers.make_wifi(ssid=reseau, password=cle, security="WPA", hidden=False)
    else:
        return
    matrice = list(qr.matrix_iter(border=4))
    titre = donnees.get("titre") or "Wi-Fi invité"
    avec_etapes = bool(adresse and donnees.get("etapes"))

    fen = tk.Tk()
    fen.title(titre)
    fen.configure(bg="white")
    fen.attributes("-topmost", True)
    fen.resizable(False, False)
    hauteur_ecran, largeur_ecran = fen.winfo_screenheight(), fen.winfo_screenwidth()
    part = 0.36 if avec_etapes else 0.4
    case = max(4, min(14, int(hauteur_ecran * part / len(matrice))))     # assez grand pour un téléphone, sans déborder
    taille = case * len(matrice)

    tk.Label(fen, text=titre, font=("Segoe UI", 22, "bold"), bg="white").pack(pady=(16, 4))
    corps = tk.Frame(fen, bg="white")
    corps.pack(padx=12)
    gauche = tk.Frame(corps, bg="white")
    gauche.pack(side="left", anchor="n")
    tk.Label(gauche, text=donnees.get("texte") or "Vise ce code avec l'appareil photo du téléphone", font=("Segoe UI", 12),
             bg="white", fg="#444").pack()
    toile = tk.Canvas(gauche, width=taille, height=taille, bg="white", highlightthickness=0)
    toile.pack(padx=12, pady=12)
    for y, ligne in enumerate(matrice):
        for x, noir in enumerate(ligne):
            if noir:
                toile.create_rectangle(x * case, y * case, (x + 1) * case, (y + 1) * case, fill="black", width=0)
    if adresse:                                   # l'adresse contient une clé : elle n'est pas écrite en clair
        for ligne in donnees.get("lignes") or []:
            tk.Label(gauche, text=str(ligne), font=("Segoe UI", 12), bg="white", anchor="w", justify="left",
                     wraplength=max(360, taille + 20)).pack(fill="x", padx=12)
    else:
        tk.Label(gauche, text=f"Réseau : {reseau}", font=("Segoe UI", 13), bg="white").pack()
        tk.Label(gauche, text=f"Mot de passe : {cle}", font=("Consolas", 15, "bold"), bg="white").pack(pady=(2, 6))
    if avec_etapes:
        # Les écrans doivent tenir à côté du QR code : on les réduit sur les petits écrans
        s = max(0.6, min(1.15, (hauteur_ecran - 200) / 620, (largeur_ecran - taille - 160) / 520))
        droite = tk.Frame(corps, bg="white")
        droite.pack(side="left", anchor="n", padx=(12, 0))
        tk.Label(droite, text="Sur la tablette, touche ce qui est entouré en orange :", font=("Segoe UI", 12, "bold"),
                 bg="white", fg=ORANGE).pack(anchor="w", padx=8)
        _etapes(droite, s).pack()
    tk.Label(fen, text=f"Se ferme tout seul dans {minutes} minute{'s' if minutes > 1 else ''} (ou clique dessus).",
             font=("Segoe UI", 9), bg="white", fg="#777").pack(pady=(4, 14))

    fen.update_idletasks()
    largeur, haut = fen.winfo_width(), fen.winfo_height()
    fen.geometry(f"+{max(0, (largeur_ecran - largeur) // 2)}+{max(0, (hauteur_ecran - haut) // 2)}")
    fen.bind("<Button-1>", lambda e: fen.destroy())
    fen.bind("<Escape>", lambda e: fen.destroy())
    fen.after(minutes * 60 * 1000, fen.destroy)
    fen.lift()
    fen.focus_force()
    if "--capture" in sys.argv:                   # essais : une image de la fenêtre, puis on ferme
        fen.after(1500, lambda: _capturer(fen, sys.argv[sys.argv.index("--capture") + 1]))
    fen.mainloop()


if __name__ == "__main__":
    main()
