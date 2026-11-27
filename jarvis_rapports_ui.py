# -*- coding: utf-8 -*-
"""
JARVIS - fenêtres des rapports : l'accord (au premier lancement), « Signaler un problème »,
« Proposer une amélioration » et le questionnaire (au bout d'une semaine). Même style que les réglages.
Chaque fenêtre s'ouvre dans son propre fil, comme la fenêtre de réglages.
"""

import jarvis_tk_sur  # noqa: F401  (images et variables Tk : jamais liberees depuis un autre fil)
import threading
import webbrowser

import jarvis_config
import jarvis_rapports

FOND, PANNEAU, PANNEAU2 = "#05090e", "#0b121b", "#111b27"
TEXTE, DISCRET = "#d7e3f4", "#7d8ca3"
POLICE = ("Segoe UI", 10)
PAGE_INFO = "https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/blob/main/docs/confidentialite.md"

EXPLICATION = ("Jarvis est fait par une seule personne, sur son temps libre. Pour savoir ce qui marche mal chez vous et "
               "l'améliorer pour tout le monde, Jarvis peut lui envoyer un rapport toutes les heures, quand il y a du nouveau.")
DETAIL = ("Rapport technique : les phrases mal comprises, les erreurs, les fonctions utilisées, les temps de réponse, "
          "les faux réveils, les demandes refaites ou annulées, les demandes confiées à Claude, la qualité du micro, "
          "le matériel du PC, les réglages jamais faits, les appareils associés (sans leur nom), le type des appareils "
          "que Jarvis ne sait pas encore piloter et les ateliers des enfants arrêtés (nom de l'atelier et étape "
          "seulement).\n\n"
          "Rapport complet : la même chose, plus vos conversations avec Jarvis.\n\n"
          "Avant l'envoi, les textes sont nettoyés : prénoms des profils, ville, adresses mail, numéros de téléphone et "
          "codes sont remplacés. Aucune voix n'est envoyée. Les rapports sont gardés 12 mois, puis effacés.\n\n"
          "Dans tous les cas, un compteur anonyme (un numéro propre à ce PC, sans lien avec vous, la version de Jarvis et de Windows, et le "
          "type de matériel : processeur, mémoire, carte graphique, portable ou fixe) sert à "
          "compter les utilisateurs ; il se coupe dans les réglages.\n\n"
          "Vous pouvez changer d'avis à tout moment (Réglages, rubrique « Rapports »), et y effacer vos données. "
          "Contact : " + jarvis_rapports.CONTACT)

_ouvertes = set()


def _accent():
    try:
        import jarvis_reglages_ui
        return jarvis_reglages_ui._couleurs_theme()[0]
    except Exception:
        return "#ff8c42"


def _lancer(nom, construire):
    """Ouvre la fenêtre « nom » dans son propre fil (une seule à la fois de chaque sorte)."""
    if nom in _ouvertes:
        return
    _ouvertes.add(nom)

    def fil():
        try:
            construire()
        except Exception as erreur:
            print("Fenêtre", nom, ":", erreur)
        finally:
            _ouvertes.discard(nom)
    threading.Thread(target=fil, daemon=True).start()


_CLASSE_CORPS = {}


def _classe_corps():
    """Le « corps » d'une fenêtre : un cadre qui défile quand la fenêtre est plus petite que son contenu."""
    if "c" in _CLASSE_CORPS:
        return _CLASSE_CORPS["c"]
    import re
    import tkinter as tk

    class Corps(tk.Frame):
        """Se comporte comme la fenêtre pour ceux qui l'utilisent (destroy, geometry, protocol...), mais les widgets
        qu'on y place sont dans une zone qui défile : sur un petit écran, on atteint toujours les boutons du bas."""

        def __getattr__(self, nom):
            if nom.startswith("_") or "_racine" not in self.__dict__:
                raise AttributeError(nom)
            return getattr(self.__dict__["_racine"], nom)

        def destroy(self):
            d = self.__dict__
            if d.get("_ferme"):                      # la fenêtre se détruit déjà : on ne fait que libérer ce cadre
                try:
                    tk.Frame.destroy(self)
                except Exception:
                    pass
                return
            d["_ferme"] = True
            d["_racine"].destroy()

        def geometry(self, spec=None):
            racine = self.__dict__["_racine"]
            if spec is None:
                return racine.geometry()
            m = re.match(r"(\d+)x(\d+)", str(spec))
            if m:                                          # jamais plus grande que l'écran
                spec = "%dx%d" % (min(int(m.group(1)), int(racine.winfo_screenwidth() * 0.95)),
                                  min(int(m.group(2)), int(racine.winfo_screenheight() * 0.90)))
            return racine.geometry(spec)

    _CLASSE_CORPS["c"] = Corps
    return Corps


def _fenetre(titre, largeur, hauteur):
    import tkinter as tk
    r = tk.Tk()
    r.title(titre)
    r.configure(bg=FOND)
    sc = max(1.0, r.winfo_fpixels("1i") / 96.0)
    # jamais plus grande que l'écran (petit portable, échelle Windows de 125 ou 150 %), et bien placée dessus
    ecran_l, ecran_h = r.winfo_screenwidth(), r.winfo_screenheight()
    l = min(int(largeur * sc), int(ecran_l * 0.95))
    h = min(int(hauteur * sc), int(ecran_h * 0.90))
    r.geometry(f"{l}x{h}+{max(0, (ecran_l - l) // 2)}+{max(0, (ecran_h - h) // 3)}")
    r.minsize(min(int(420 * sc), l), min(int(300 * sc), h))
    r.attributes("-topmost", True)
    try:
        r.iconbitmap(jarvis_config.chemin("installateur", "jarvis.ico"))
    except Exception:
        pass
    try:
        import ctypes
        r.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(r.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception:
        pass
    r.after(1500, lambda: r.attributes("-topmost", False))
    # zone qui défile (molette + fine barre) : quand tout tient, rien ne change à l'écran
    toile = tk.Canvas(r, bg=FOND, highlightthickness=0)
    barre = tk.Canvas(r, width=max(4, int(6 * sc)), bg=FOND, highlightthickness=0)
    barre.pack(side="right", fill="y", pady=4)
    toile.pack(side="left", fill="both", expand=True)
    corps = _classe_corps()(toile, bg=FOND)
    corps.__dict__["_racine"] = r
    fen = toile.create_window((0, 0), window=corps, anchor="nw")

    def position_barre(debut, fin):
        barre.delete("all")
        debut, fin = float(debut), float(fin)
        if fin - debut < 0.999:
            hh = barre.winfo_height()
            barre.create_line(int(3 * sc), debut * hh + 3, int(3 * sc), max(debut * hh + 8, fin * hh - 3),
                              width=max(3, int(4 * sc)), capstyle="round", fill="#3a4a5e")
    toile.configure(yscrollcommand=position_barre)

    def regler(_e=None):
        lt, ht = toile.winfo_width(), toile.winfo_height()
        besoin = corps.winfo_reqheight()
        toile.itemconfigure(fen, width=lt, height=max(ht, besoin))
        toile.configure(scrollregion=(0, 0, lt, max(ht, besoin)))
    toile.bind("<Configure>", regler)
    corps.bind("<Configure>", regler)

    def molette(e):
        if e.widget.winfo_class() == "Text":            # une zone de texte a sa propre molette
            return
        toile.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")
    r.bind_all("<MouseWheel>", molette)
    detruire_racine = r.destroy

    def detruire():                                        # fermer la fenêtre directement ne doit pas se détruire deux fois
        corps.__dict__["_ferme"] = True
        detruire_racine()
    r.destroy = detruire
    r.protocol("WM_DELETE_WINDOW", corps.destroy)         # (les fenêtres peuvent le remplacer)
    return corps, sc


def _bouton(parent, texte, action, fort=False, accent="#ff8c42"):
    import tkinter as tk
    b = tk.Label(parent, text=texte, bg=accent if fort else "#1b2838", fg="#0b0f14" if fort else TEXTE,
                 font=("Segoe UI Semibold", 11 if fort else 10), padx=18 if fort else 12, pady=9 if fort else 6,
                 cursor="hand2")
    b.bind("<Button-1>", lambda e: action())
    return b


def _titre(r, texte, accent):
    import tkinter as tk
    tk.Label(r, text="J A R V I S", bg=FOND, fg=DISCRET, font=("Segoe UI Light", 11)).pack(anchor="w", padx=24, pady=(18, 0))
    tk.Label(r, text=texte, bg=FOND, fg=TEXTE, font=("Segoe UI Semibold", 16)).pack(anchor="w", padx=24, pady=(2, 0))
    tk.Frame(r, bg=accent, height=2, width=90).pack(anchor="w", padx=24, pady=(6, 10))


# ---------- L'accord ----------

def ouvrir_accord():
    _lancer("accord", _accord)


def _accord():
    import tkinter as tk
    accent = _accent()
    r, sc = _fenetre("Jarvis - Aider à améliorer Jarvis", 600, 560)
    _titre(r, "Aider à améliorer Jarvis ?", accent)
    tk.Label(r, text=EXPLICATION, bg=FOND, fg=TEXTE, font=("Segoe UI", 11), wraplength=int(550 * sc),
             justify="left").pack(anchor="w", padx=24)
    choix = tk.StringVar(r, value="technique")
    cadre = tk.Frame(r, bg=FOND)
    cadre.pack(fill="x", padx=20, pady=(12, 4))
    for valeur, libelle, sous in (("technique", "Rapport technique (conseillé)",
                                   "Erreurs, phrases mal comprises, statistiques. Sans vos conversations."),
                                  ("complet", "Rapport complet", "La même chose, plus vos conversations avec Jarvis.")):
        ligne = tk.Frame(cadre, bg=PANNEAU2, highlightthickness=1, highlightbackground="#1b2838")
        ligne.pack(fill="x", pady=3)
        tk.Radiobutton(ligne, text=libelle, variable=choix, value=valeur, bg=PANNEAU2, fg=TEXTE, selectcolor=PANNEAU,
                       activebackground=PANNEAU2, activeforeground=TEXTE, font=("Segoe UI Semibold", 10),
                       highlightthickness=0, bd=0).pack(anchor="w", padx=10, pady=(8, 0))
        tk.Label(ligne, text=sous, bg=PANNEAU2, fg=DISCRET, font=POLICE).pack(anchor="w", padx=36, pady=(0, 8))
    detail = tk.Label(r, text="", bg=FOND, fg=DISCRET, font=("Segoe UI", 9), wraplength=int(550 * sc), justify="left")
    lien = tk.Label(r, text="Ce qui est envoyé, en détail ▾", bg=FOND, fg=accent, font=("Segoe UI", 10, "underline"),
                    cursor="hand2")

    def montrer():
        if detail.cget("text"):
            detail.configure(text="")
            r.geometry(f"{int(600 * sc)}x{int(560 * sc)}")
        else:
            detail.configure(text=DETAIL)
            r.geometry(f"{int(600 * sc)}x{int(820 * sc)}")
    lien.bind("<Button-1>", lambda e: montrer())
    lien.pack(anchor="w", padx=24, pady=(8, 0))
    detail.pack(anchor="w", padx=24)
    bas = tk.Frame(r, bg=FOND)
    bas.pack(side="bottom", fill="x", padx=24, pady=20)

    def oui():
        jarvis_rapports.choisir_niveau(choix.get())
        r.destroy()

    def non():
        jarvis_rapports.choisir_niveau("aucun")        # (un seul rappel, deux semaines plus tard)
        r.destroy()
    _bouton(bas, "Oui, j'aide à améliorer Jarvis", oui, fort=True, accent=accent).pack(side="right")
    _bouton(bas, "Non merci", non).pack(side="right", padx=10)
    tk.Label(bas, text="Modifiable à tout moment\ndans les réglages.", bg=FOND, fg=DISCRET, font=("Segoe UI", 9),
             justify="left").pack(side="left")

    def fermer():                 # fermée sans répondre : on reposera la question au prochain démarrage
        r.destroy()
    r.protocol("WM_DELETE_WINDOW", fermer)
    if jarvis_rapports.valeur("niveau") == "aucun":            # le rappel unique, deux semaines après un refus
        jarvis_rapports.regler("rappel_fait", True)
    r.mainloop()


# ---------- Signaler un problème, proposer une amélioration ----------

def ouvrir_message(genre):
    """genre : « probleme » ou « idee »."""
    _lancer("message-" + genre, lambda: _message(genre))


def _message(genre):
    import tkinter as tk
    accent = _accent()
    probleme = genre == "probleme"
    r, sc = _fenetre("Jarvis - " + ("Signaler un problème" if probleme else "Proposer une amélioration"), 560, 470)
    _titre(r, "Signaler un problème" if probleme else "Proposer une amélioration", accent)
    tk.Label(r, text=("Décrivez ce qui ne va pas, en une ou deux phrases : ce que vous avez dit ou fait, et ce que "
                      "Jarvis a fait." if probleme else
                      "Une idée de fonction, quelque chose à changer ? Écrivez-la ici, elle sera lue."),
             bg=FOND, fg=TEXTE, font=("Segoe UI", 10), wraplength=int(510 * sc), justify="left").pack(anchor="w", padx=24)
    zone = tk.Text(r, height=7, bg=PANNEAU2, fg=TEXTE, insertbackground=TEXTE, relief="flat", font=("Segoe UI", 11),
                   wrap="word", highlightthickness=1, highlightbackground="#1b2838", highlightcolor=accent)
    zone.pack(fill="x", padx=24, pady=10)
    zone.focus_set()
    joindre = tk.BooleanVar(r, value=probleme)
    if probleme:
        tk.Checkbutton(r, text="Joindre le journal technique de Jarvis (nettoyé, sans vos conversations"
                               + (")" if jarvis_rapports.niveau() != "complet" else " sauf en rapport complet)"),
                       variable=joindre, bg=FOND, fg=DISCRET, selectcolor=PANNEAU, activebackground=FOND,
                       activeforeground=TEXTE, font=("Segoe UI", 9), highlightthickness=0, bd=0,
                       wraplength=int(500 * sc), justify="left").pack(anchor="w", padx=20)
    etat = tk.Label(r, text="", bg=FOND, fg=DISCRET, font=("Segoe UI", 10))
    etat.pack(anchor="w", padx=24, pady=(6, 0))
    bas = tk.Frame(r, bg=FOND)
    bas.pack(side="bottom", fill="x", padx=24, pady=18)

    envoi = {"en_cours": False, "fait": False}

    def envoyer():
        if envoi["en_cours"] or envoi["fait"]:        # plusieurs clics de suite : un seul message part
            return
        texte = zone.get("1.0", "end").strip()
        if len(texte) < 3:
            etat.configure(text="Écrivez quelques mots avant d'envoyer.", fg=accent)
            return
        envoi["en_cours"] = True
        etat.configure(text="Envoi en cours…", fg=DISCRET)
        r.update()

        def fil():
            ok = jarvis_rapports.envoyer_message(genre, texte, joindre_journal=joindre.get())
            try:
                r.after(0, lambda: fin(ok))
            except Exception:
                pass
        threading.Thread(target=fil, daemon=True).start()

    def fin(ok):
        envoi["en_cours"] = False
        envoi["fait"] = bool(ok)
        if ok:
            etat.configure(text="Merci ! C'est bien parti.", fg=accent)
            r.after(1800, r.destroy)
        else:
            etat.configure(text="L'envoi n'a pas marché (Internet ?). Réessayez plus tard.", fg="#ff6b6b")
    _bouton(bas, "Envoyer", envoyer, fort=True, accent=accent).pack(side="right")
    _bouton(bas, "Annuler", r.destroy).pack(side="right", padx=10)
    r.mainloop()


# ---------- Le questionnaire (une seule fois, au bout d'une semaine) ----------

QUESTIONS = (("aime", "Qu'est-ce que vous aimez le plus dans Jarvis ?"),
             ("gene", "Qu'est-ce qui vous gêne ou marche mal ?"),
             ("manque", "Qu'est-ce qui vous manque ?"))


def ouvrir_questionnaire():
    _lancer("questionnaire", _questionnaire)


def _questionnaire():
    import tkinter as tk
    accent = _accent()
    r, sc = _fenetre("Jarvis - Trois petites questions", 580, 600)
    _titre(r, "Trois petites questions", accent)
    tk.Label(r, text="Vous utilisez Jarvis depuis une semaine. Vos réponses aident à décider des prochaines "
                     "améliorations. Une minute suffit ; aucune réponse n'est obligatoire.",
             bg=FOND, fg=TEXTE, font=("Segoe UI", 10), wraplength=int(530 * sc), justify="left").pack(anchor="w", padx=24)
    zones = {}
    for cle, question in QUESTIONS:
        tk.Label(r, text=question, bg=FOND, fg=accent, font=("Segoe UI Semibold", 10)).pack(anchor="w", padx=24, pady=(12, 2))
        z = tk.Text(r, height=3, bg=PANNEAU2, fg=TEXTE, insertbackground=TEXTE, relief="flat", font=("Segoe UI", 10),
                    wrap="word", highlightthickness=1, highlightbackground="#1b2838", highlightcolor=accent)
        z.pack(fill="x", padx=24)
        zones[cle] = z
    etat = tk.Label(r, text="", bg=FOND, fg=DISCRET, font=("Segoe UI", 10))
    etat.pack(anchor="w", padx=24, pady=(8, 0))
    bas = tk.Frame(r, bg=FOND)
    bas.pack(side="bottom", fill="x", padx=24, pady=18)

    def envoyer():
        reponses = {c: z.get("1.0", "end").strip() for c, z in zones.items()}
        if not any(reponses.values()):
            etat.configure(text="Répondez au moins à une question, ou cliquez sur « Non merci ».", fg=accent)
            return
        etat.configure(text="Envoi en cours…")

        def fil():
            ok = jarvis_rapports.envoyer_message("questionnaire", reponses)
            try:
                r.after(0, lambda: (etat.configure(text="Merci beaucoup !", fg=accent), r.after(1500, r.destroy))
                        if ok else etat.configure(text="L'envoi n'a pas marché. Réessayez plus tard.", fg="#ff6b6b"))
            except Exception:
                pass
        threading.Thread(target=fil, daemon=True).start()

    def jamais():
        jarvis_rapports.regler("questionnaire", "refusé")
        r.destroy()

    def plus_tard():               # reproposé au prochain démarrage de Jarvis
        r.destroy()
    _bouton(bas, "Envoyer", envoyer, fort=True, accent=accent).pack(side="right")
    _bouton(bas, "Plus tard", plus_tard).pack(side="right", padx=10)
    _bouton(bas, "Non merci", jamais).pack(side="left")
    r.protocol("WM_DELETE_WINDOW", plus_tard)
    r.mainloop()


def commande(t):
    """« signale un problème », « j'ai un problème à signaler », « propose une amélioration », « j'ai une idée
    pour Jarvis » : la fenêtre s'ouvre (rien ne part avant que la personne appuie sur Envoyer)."""
    import re
    if re.search(r"\b(?:signale[rz]?|signaler|rapporte[rz]?)\b.{0,20}\b(?:probl[eè]me|bug|souci)\b"
                 r"|\bprobl[eè]me [àa] signaler\b|\bsignaler un bug\b", t):
        ouvrir_message("probleme")
        return "J'ouvre la fenêtre pour signaler un problème. Décris-le en une ou deux phrases."
    if re.search(r"\b(?:propose[rz]?|proposer|sugg[eè]re[rz]?)\b.{0,20}\b(?:am[ée]lioration|id[ée]e|fonction)\b"
                 r"|\bj'ai une id[ée]e pour (?:toi|jarvis|t'am[ée]liorer)\b", t):
        ouvrir_message("idee")
        return "J'ouvre la fenêtre pour proposer une amélioration. Écris ton idée, elle sera lue."
    return None


def ouvrir_page_info():
    webbrowser.open(PAGE_INFO)


def au_demarrage():
    """Une minute après le démarrage : l'accord s'il n'a pas encore été donné (ou le rappel unique),
    sinon le questionnaire au bout d'une semaine."""
    def fil():
        import time
        time.sleep(60)
        try:
            if jarvis_rapports.a_demander():
                ouvrir_accord()
            elif jarvis_rapports.questionnaire_a_proposer():
                ouvrir_questionnaire()
        except Exception as erreur:
            print("(Rapports, fenêtres :", erreur, ")")
    threading.Thread(target=fil, daemon=True).start()
