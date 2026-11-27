# -*- coding: utf-8 -*-
"""
JARVIS - la fenêtre « Premiers pas » : ce qu'un nouvel utilisateur peut essayer tout de suite.

Elle s'ouvre une seule fois, après une première installation, quand la fenêtre d'accord des rapports a reçu sa
réponse (jamais deux fenêtres à la fois). Elle se rouvre à la demande : « Jarvis, premiers pas ».
Elle montre comment parler à Jarvis, cinq demandes à essayer, et comment aller plus loin : la ville, la boîte
mail, l'agenda, et Claude (ce qu'il apporte, comment l'ajouter). Rien n'est envoyé nulle part.
"""

import re
import shutil
import threading
import time

import jarvis_accueil

ESSAIS = (("« Jarvis, quelle heure est-il ? »", "La réponse est immédiate."),
          ("« Jarvis, quel temps fait-il ? »", "Dis d'abord « ma ville est Lyon » (la tienne) pour la météo d'ici."),
          ("« Jarvis, mets un minuteur de 5 minutes »", "Il sonne et te prévient à la fin."),
          ("« Jarvis, ouvre le navigateur »", "Ou n'importe quelle application : « ouvre la calculatrice »."),
          ("« Jarvis, qu'est-ce que tu sais faire ? »", "Il te résume tout. L'aide complète est dans les réglages."))
PARLER = ("Dis « Jarvis », attends le petit son, puis fais ta demande. Tu peux aussi l'écrire dans la case au-dessus "
          "du réacteur. Pour le faire taire : « Jarvis, stop ». Un clic droit sur le réacteur ouvre le menu et les "
          "réglages.")
AVEC_CLAUDE = ("Claude est relié : tu peux aussi poser n'importe quelle question, faire résumer une page ou écrire "
               "un texte.")
SANS_CLAUDE = ("Sans Claude, Jarvis fait les commandes immédiates (heure, météo, minuteurs, applications, fenêtres, "
               "musique, mails…). Avec Claude (il faut un abonnement Claude Pro), il répond aussi à n'importe quelle "
               "question, résume une page ou écrit un texte. Pour l'ajouter plus tard : ouvre mes Réglages, onglet « Assistants », "
               "et clique sur « Installer Claude », puis sur « Connecter mon compte ». Tu peux aussi brancher un autre assistant "
"(Gemini, Groq, Mistral…) dans le même onglet.")

_COMMANDE = re.compile(r"\bpremiers pas\b|^\W*(?:jarvis\W+)?comment (?:[çc]a|tu) marches?\W*$"
                       r"|^\W*(?:jarvis\W+)?comment (?:je )?(?:t'utilise|te parler?|on te parle|on t'utilise)\W*$"
                       r"|\bvisite guid[ée]e\b")


def claude_relie():
    """Vrai si Claude Code est installé sur ce PC."""
    try:
        import jarvis_claude_reglages          # le même test que celui de Jarvis (~\\.local\\bin\\claude.exe)
        return bool(jarvis_claude_reglages.installe())
    except Exception:
        return False


def a_montrer():
    """Vrai une seule fois : après une première installation, tant que la fenêtre n'a pas été montrée."""
    donnees = jarvis_accueil._lire()
    return bool(donnees.get("nouveau")) and not donnees.get("premiers_pas")


def _noter_vue():
    donnees = jarvis_accueil._lire()
    if not donnees.get("premiers_pas"):
        donnees["premiers_pas"] = time.strftime("%Y-%m-%d")
        jarvis_accueil._ecrire(donnees)


def commande(t):
    """« Jarvis, premiers pas » : rouvre la fenêtre. Renvoie la phrase à dire, ou None."""
    t = (t or "").replace("’", "'").lower()
    if not _COMMANDE.search(t):
        return None
    ouvrir()
    return "J'ouvre la fenêtre des premiers pas."


def au_demarrage(attendre=None, delai=90, essais=45):
    """Après une première installation : ouvre la fenêtre une fois, quand la fenêtre d'accord des rapports a reçu
    sa réponse (on regarde toutes les 20 secondes, pendant un quart d'heure ; sinon, au lancement suivant)."""
    def fil():
        try:
            time.sleep(delai)
            for _ in range(essais):
                if not a_montrer():
                    return
                if not (attendre() if attendre else _accord_en_attente()):
                    _noter_vue()
                    ouvrir()
                    return
                time.sleep(20)
        except Exception as erreur:
            print("(Premiers pas :", erreur, ")")
    threading.Thread(target=fil, daemon=True).start()


def _accord_en_attente():
    try:
        import jarvis_rapports
        import jarvis_rapports_ui
        return bool(jarvis_rapports.a_demander()) or "accord" in jarvis_rapports_ui._ouvertes
    except Exception:
        return False


def ouvrir():
    import jarvis_rapports_ui
    jarvis_rapports_ui._lancer("premiers-pas", _fenetre_premiers_pas)


def _fenetre_premiers_pas(fermer_apres=None, avec_claude=None):
    import tkinter as tk
    import jarvis_rapports_ui as ui
    accent = ui._accent()
    r, sc = ui._fenetre("Jarvis - Premiers pas", 640, 760)
    ui._titre(r, "Bienvenue ! Voici comment me parler", accent)
    large = int(590 * sc)
    tk.Label(r, text=PARLER, bg=ui.FOND, fg=ui.TEXTE, font=("Segoe UI", 10), wraplength=large,
             justify="left").pack(anchor="w", padx=24)

    def section(texte):
        tk.Label(r, text=texte.upper(), bg=ui.FOND, fg=accent, font=("Segoe UI Semibold", 9)).pack(
            anchor="w", padx=24, pady=(14, 4))

    section("À essayer tout de suite")
    for phrase, detail in ESSAIS:
        carte = tk.Frame(r, bg=ui.PANNEAU2, highlightthickness=1, highlightbackground="#1b2838")
        carte.pack(fill="x", padx=24, pady=2)
        tk.Label(carte, text=phrase, bg=ui.PANNEAU2, fg=ui.TEXTE, font=("Segoe UI Semibold", 11)).pack(
            anchor="w", padx=12, pady=(6, 0))
        tk.Label(carte, text=detail, bg=ui.PANNEAU2, fg=ui.DISCRET, font=("Segoe UI", 9), wraplength=int(550 * sc),
                 justify="left").pack(anchor="w", padx=12, pady=(0, 6))

    section("Pour aller plus loin")
    ligne = tk.Frame(r, bg=ui.FOND)
    ligne.pack(fill="x", padx=24, pady=(0, 6))

    def comptes(quoi):
        try:
            if quoi == "mails":
                import jarvis_mails_ui
                jarvis_mails_ui.ouvrir()
            else:
                import jarvis_agenda_ui
                jarvis_agenda_ui.ouvrir()
        except Exception as erreur:
            print("(Premiers pas :", erreur, ")")

    def aide():
        try:
            import jarvis_reglages_ui
            jarvis_reglages_ui._fenetre["page"] = "Aide"
            jarvis_reglages_ui.ouvrir()
        except Exception as erreur:
            print("(Premiers pas :", erreur, ")")
    ui._bouton(ligne, "Relier ma boîte mail", lambda: comptes("mails")).pack(side="left")
    ui._bouton(ligne, "Relier mon agenda", lambda: comptes("agenda")).pack(side="left", padx=8)
    ui._bouton(ligne, "Toute l'aide", aide).pack(side="left")
    relie = claude_relie() if avec_claude is None else avec_claude
    tk.Label(r, text=AVEC_CLAUDE if relie else SANS_CLAUDE, bg=ui.FOND, fg=ui.TEXTE if relie else ui.DISCRET,
             font=("Segoe UI", 10), wraplength=large, justify="left").pack(anchor="w", padx=24, pady=(4, 0))
    bas = tk.Frame(r, bg=ui.FOND)
    bas.pack(side="bottom", fill="x", padx=24, pady=16)
    ui._bouton(bas, "C'est parti", r.destroy, fort=True, accent=accent).pack(side="right")   # d'abord : jamais coupé
    tk.Label(bas, text="Pour revoir cette fenêtre : « Jarvis, premiers pas ».", bg=ui.FOND, fg=ui.DISCRET,
             font=("Segoe UI", 9), wraplength=max(200, large - 160), justify="left").pack(side="left")
    if fermer_apres:                                      # pour les essais automatiques
        r.after(int(fermer_apres * 1000), r.destroy)
    r.mainloop()
