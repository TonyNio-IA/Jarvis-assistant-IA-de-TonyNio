# -*- coding: utf-8 -*-
"""
JARVIS - fenêtre du QR code du Wi-Fi invité.

Lancée par jarvis_freebox.py. Le nom du réseau et le mot de passe arrivent par l'entrée standard (jamais
dans la ligne de commande ni dans un fichier). Le QR code est dessiné directement à l'écran, sans image
enregistrée. Il suffit de le viser avec l'appareil photo d'un téléphone pour se connecter.
La fenêtre se ferme toute seule après quelques minutes, ou d'un clic, ou avec Échap.
"""
import json
import sys
import tkinter as tk

import segno
from segno import helpers


def main():
    donnees = json.loads(sys.stdin.read() or "{}")
    reseau, cle = donnees.get("reseau", ""), donnees.get("cle", "")
    minutes = max(1, min(int(donnees.get("minutes", 5)), 30))
    if not reseau or not cle:
        return
    qr = helpers.make_wifi(ssid=reseau, password=cle, security="WPA", hidden=False)
    matrice = list(qr.matrix_iter(border=4))

    fen = tk.Tk()
    fen.title("Wi-Fi invité")
    fen.configure(bg="white")
    fen.attributes("-topmost", True)
    fen.resizable(False, False)
    hauteur_ecran = fen.winfo_screenheight()
    case = max(4, min(14, int(hauteur_ecran * 0.4 / len(matrice))))     # assez grand pour un téléphone, sans déborder
    taille = case * len(matrice)

    tk.Label(fen, text="Wi-Fi invité", font=("Segoe UI", 22, "bold"), bg="white").pack(pady=(16, 4))
    tk.Label(fen, text="Vise ce code avec l'appareil photo du téléphone", font=("Segoe UI", 12),
             bg="white", fg="#444").pack()
    toile = tk.Canvas(fen, width=taille, height=taille, bg="white", highlightthickness=0)
    toile.pack(padx=24, pady=12)
    for y, ligne in enumerate(matrice):
        for x, noir in enumerate(ligne):
            if noir:
                toile.create_rectangle(x * case, y * case, (x + 1) * case, (y + 1) * case, fill="black", width=0)
    tk.Label(fen, text=f"Réseau : {reseau}", font=("Segoe UI", 13), bg="white").pack()
    tk.Label(fen, text=f"Mot de passe : {cle}", font=("Consolas", 15, "bold"), bg="white").pack(pady=(2, 6))
    tk.Label(fen, text=f"Se ferme tout seul dans {minutes} minute{'s' if minutes > 1 else ''} (ou clique dessus).",
             font=("Segoe UI", 9), bg="white", fg="#777").pack(pady=(0, 14))

    fen.update_idletasks()
    largeur, haut = fen.winfo_width(), fen.winfo_height()
    fen.geometry(f"+{(fen.winfo_screenwidth() - largeur) // 2}+{max(0, (hauteur_ecran - haut) // 2)}")
    fen.bind("<Button-1>", lambda e: fen.destroy())
    fen.bind("<Escape>", lambda e: fen.destroy())
    fen.after(minutes * 60 * 1000, fen.destroy)
    fen.lift()
    fen.focus_force()
    fen.mainloop()


if __name__ == "__main__":
    main()
