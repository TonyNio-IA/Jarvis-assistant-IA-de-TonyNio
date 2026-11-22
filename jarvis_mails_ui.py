# -*- coding: utf-8 -*-
"""
JARVIS - relier sa boîte mail (Gmail, Orange, Free, La Poste, Yahoo, iCloud ou une autre messagerie « IMAP »).

  « relie mes mails », « configure ma messagerie », « connecte ma boîte mail »   -> la fenêtre s'ouvre
La fenêtre explique quoi préparer pour chaque messagerie, essaie la connexion (lecture, puis envoi, sans rien
envoyer) et range l'adresse et le mot de passe dans le Gestionnaire d'identification de Windows. Rien n'est
écrit dans un fichier, et le mot de passe n'apparaît jamais dans le journal.
Outlook.com, Hotmail et Live : pas encore possible (Microsoft refuse les mots de passe depuis septembre 2024).
"""

import imaplib
import json
import re
import smtplib
import socket

import jarvis_coffre
import jarvis_mails

# (clé, nom affiché, page d'aide à ouvrir ou « », étapes)
SERVICES = (
    ("gmail", "Gmail", "https://myaccount.google.com/apppasswords",
     ("Gmail demande un « mot de passe d'application » : un code réservé à Jarvis, pas ton mot de passe Google.",
      "1. La validation en deux étapes doit être activée sur ton compte Google.",
      "2. Ouvre la page « Mots de passe des applications » (bouton ci-dessous).",
      "3. Donne-lui un nom, par exemple Jarvis, puis crée-le.",
      "4. Copie le code de 16 lettres et colle-le dans « Mot de passe ».")),
    ("orange", "Orange", "",
     ("1. Ouvre ta messagerie Orange dans ton navigateur, puis ses paramètres.",
      "2. Vérifie que l'accès « POP/IMAP » (pour les logiciels de messagerie) est autorisé.",
      "3. Si Orange t'a fait créer un mot de passe réservé aux logiciels de messagerie, c'est celui-là "
      "qu'il faut écrire ici. Sinon, c'est le mot de passe de ta boîte mail.",
      "Ton adresse peut finir par @orange.fr ou @wanadoo.fr.")),
    ("free", "Free", "",
     ("Rien à préparer.",
      "Écris ton adresse @free.fr en entier et le mot de passe de ta boîte mail Free",
      "(celui du webmail, pas celui de ton espace abonné).")),
    ("laposte", "La Poste", "",
     ("Rien à préparer.",
      "Écris ton adresse @laposte.net en entier et le mot de passe de ta boîte mail.")),
    ("yahoo", "Yahoo", "https://login.yahoo.com/account/security",
     ("Yahoo demande un « mot de passe d'application » : un code réservé à Jarvis.",
      "1. Ouvre la page « Sécurité du compte » de Yahoo (bouton ci-dessous).",
      "2. Choisis « Générer un mot de passe d'application ».",
      "3. Donne-lui un nom, par exemple Jarvis.",
      "4. Copie le code affiché et colle-le dans « Mot de passe ».")),
    ("icloud", "iCloud", "https://account.apple.com",
     ("Apple demande un « mot de passe pour app » : un code réservé à Jarvis, pas ton mot de passe Apple.",
      "1. Ouvre account.apple.com (bouton ci-dessous), rubrique « Connexion et sécurité ».",
      "2. Choisis « Mots de passe pour app » et crée-en un, nommé Jarvis.",
      "3. Copie le code affiché et colle-le dans « Mot de passe ».",
      "Ton adresse peut finir par @icloud.com, @me.com ou @mac.com.")),
    ("microsoft", "Outlook / Hotmail", "",
     ("Pas encore possible.",
      "Depuis septembre 2024, Microsoft n'accepte plus les mots de passe pour les applications comme Jarvis",
      "sur les adresses Outlook.com, Hotmail, Live et MSN.",
      "C'est prévu pour une prochaine version de Jarvis.")),
    ("autre", "Autre", "",
     ("Pour une autre messagerie, il faut ses serveurs : cherche « paramètres IMAP » dans son aide.",
      "Réception : le serveur « IMAP » (par exemple imap.exemple.fr), en connexion sécurisée, port 993.",
      "Envoi : le serveur « SMTP ». Laisse vide et Jarvis essaiera de le trouver.")),
)
# Ce qu'il faut vérifier quand la messagerie refuse le mot de passe
SI_REFUS = {
    "gmail": "Gmail a refusé. Il faut le code de 16 lettres créé à l'étape 3, pas ton mot de passe Google.",
    "orange": ("Orange a refusé. Vérifie le mot de passe, et que l'accès « POP/IMAP » est bien autorisé dans les "
               "paramètres de ta messagerie Orange."),
    "free": "Free a refusé. Vérifie l'adresse (en entier) et le mot de passe de ta boîte mail Free.",
    "laposte": "La Poste a refusé. Vérifie l'adresse (en entier) et le mot de passe de ta boîte mail.",
    "yahoo": "Yahoo a refusé. Il faut le code créé à l'étape 2, pas ton mot de passe Yahoo.",
    "icloud": "Apple a refusé. Il faut le « mot de passe pour app » créé à l'étape 2, pas ton mot de passe Apple.",
    "autre": "Ta messagerie a refusé. Vérifie l'adresse et le mot de passe.",
}
AVERTISSEMENT = ("Ton mot de passe reste sur ce PC, dans le coffre de Windows. Jarvis ne lit tes mails que quand tu le "
                 "demandes, et n'en envoie jamais sans ton « oui ».")

_MOT_MAIL = r"(?:e-?mails?|mails?|m[eè]ls?|courriels?|messagerie|bo[iî]te (?:e-?mail|mail|aux lettres [ée]lectronique)|adresse (?:e-?mail|mail))"
_COMMANDE = re.compile(
    r"\b(?:relie[rz]?|connecte[rz]?|configure[rz]?|param[eè]tre[rz]?|associe[rz]?|branche[rz]?|d[ée]connecte[rz]?"
    r"|d[ée]lie[rz]?)\b\W+(?:moi \W*)?(?:mon |ma |mes |ton |ta |tes |l'|le |la |les |notre |nos |une |un )?" + _MOT_MAIL + r"\b(?!\W+vocale)"
    r"|^\W*(?:ajoute[rz]?|change[rz]?|retire[rz]?|enl[eè]ve[rz]?)\W+(?:mon |ma |mes |l'|la )" + _MOT_MAIL
    + r"(?:\W+(?:gmail|orange|free|la poste|yahoo|icloud|apple|outlook|hotmail))?\W*$")
_ENVOI = re.compile(r"^\W*(?:jarvis\W+)?(?:envoie|envoies|envoyer|envoi|[ée]cris|[ée]crire|[ée]crit|r[ée]dige|fais|lis|lire)\b")


def nettoyer_mot(cle, mot):
    """Le mot de passe tel qu'il sera utilisé : Google et Yahoo affichent leur code par groupes séparés
    d'espaces, qui n'en font pas partie."""
    mot = (mot or "").strip()
    return re.sub(r"\s+", "", mot) if cle in ("gmail", "yahoo") else mot


def essayer(cle, adresse, mot, imap=None, smtp=None):
    """Essaie la connexion sans rien envoyer ni modifier. Renvoie {"ok", "message", "envoi", "reglages",
    "adresse", "mot"} ; « envoi » dit si l'envoi de mails marchera aussi."""
    adresse = re.sub(r"\s+", "", adresse or "")
    resultat = {"ok": False, "message": "", "envoi": False, "reglages": None, "adresse": adresse, "mot": ""}
    if cle == "microsoft":
        resultat["message"] = jarvis_mails.REFUS_MICROSOFT
        return resultat
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s.]+", adresse):
        resultat["message"] = "Écris ton adresse mail en entier, par exemple prenom.nom@exemple.fr."
        return resultat
    devine = jarvis_mails.fournisseur_de(adresse)
    if devine == "microsoft" and cle != "autre":
        resultat["message"] = jarvis_mails.REFUS_MICROSOFT
        return resultat
    if cle in jarvis_mails.FOURNISSEURS and devine in jarvis_mails.FOURNISSEURS and devine != cle:
        nom = jarvis_mails.FOURNISSEURS[devine]["nom"]
        resultat["message"] = f"Cette adresse est une adresse {nom} : choisis « {nom} » en haut, puis réessaie."
        return resultat
    mot = nettoyer_mot(cle, mot)
    if not mot:
        resultat["message"] = "Écris le mot de passe (ou le code créé pour Jarvis)."
        return resultat
    if len(mot) > jarvis_coffre.TAILLE_MAX:
        resultat["message"] = "Ce mot de passe est trop long. Vérifie que tu n'as collé que le code."
        return resultat
    if cle == "autre":
        if not re.fullmatch(r"[\w.-]+\.[a-zA-Z]{2,}", re.sub(r"^\w+://", "", (imap or "").strip()).strip("/")):
            resultat["message"] = "Écris le serveur de réception (IMAP), par exemple imap.exemple.fr."
            return resultat
        regl = jarvis_mails.reglages_pour(None, imap, smtp)
    elif cle in jarvis_mails.FOURNISSEURS:
        regl = jarvis_mails.reglages_pour(cle)
    else:
        resultat["message"] = "Choisis d'abord ta messagerie, en haut."
        return resultat
    resultat.update(reglages=regl, mot=mot)
    nom = regl["nom"] if regl["cle"] != "autre" else "Ta messagerie"
    boite = None
    try:                                           # 1. la lecture
        boite = imaplib.IMAP4_SSL(regl["imap"], 993, timeout=15)
        boite.login(adresse, mot)
        boite.select("INBOX", readonly=True)
    except imaplib.IMAP4.error:
        resultat["message"] = SI_REFUS.get(regl["cle"], SI_REFUS["autre"])
        return resultat
    except socket.gaierror:
        resultat["message"] = (f"Le serveur « {regl['imap']} » est introuvable. Vérifie son nom, et qu'Internet marche."
                               if regl["cle"] == "autre" else
                               f"Je n'arrive pas à joindre {nom}. Vérifie qu'Internet marche, puis réessaie.")
        return resultat
    except (OSError, EOFError) as erreur:
        print("Mails (essai) :", type(erreur).__name__)
        resultat["message"] = f"Je n'arrive pas à joindre {nom}. Vérifie qu'Internet marche, puis réessaie."
        return resultat
    except Exception as erreur:
        print("Mails (essai) :", type(erreur).__name__)
        resultat["message"] = "La connexion n'a pas marché. Réessaie dans un moment."
        return resultat
    finally:
        try:
            if boite is not None:
                boite.logout()
        except Exception:
            pass
    resultat["ok"] = True
    try:                                           # 2. l'envoi (connexion seulement : rien ne part)
        essais = [(regl["smtp"], port, mode) for port, mode in regl["envoi"]]
        jarvis_mails._fermer(jarvis_mails._ouvrir_smtp((adresse, mot), essais, delai=15))
        resultat["envoi"] = True
        resultat["message"] = "C'est bon : je peux lire tes mails et en envoyer."
    except Exception as erreur:
        print("Mails (essai de l'envoi) :", type(erreur).__name__)
        resultat["message"] = ("C'est bon pour lire tes mails. L'envoi, lui, n'a pas répondu"
                               + (" : indique le serveur d'envoi (SMTP) de ta messagerie." if regl["cle"] == "autre"
                                  else " pour l'instant : tu pourras réessayer plus tard."))
    return resultat


def _cibles(profil=False):
    """Les deux noms du coffre (compte, messagerie choisie) pour un profil (False = celui en cours)."""
    return jarvis_mails.cible(jarvis_mails.CIBLE, profil), jarvis_mails.cible(jarvis_mails.CIBLE_REGLAGES, profil)


def enregistrer(resultat, profil=False):
    """Range le compte qui vient d'être essayé avec succès, pour le profil en cours (ou celui donné).
    Renvoie True si c'est fait."""
    if not resultat or not resultat.get("ok") or not resultat.get("reglages"):
        return False
    regl, adresse, mot = resultat["reglages"], resultat["adresse"], resultat["mot"]
    choix = "-" if regl["cle"] != "autre" else json.dumps({"imap": regl["imap"], "smtp": regl["smtp"]})
    compte, messagerie = _cibles(profil)
    if not jarvis_coffre.ranger(compte, adresse, mot):
        return False
    if not jarvis_coffre.ranger(messagerie, regl["cle"], choix):
        return False
    relu = jarvis_mails.identifiants(compte)
    if not relu or relu[0] != adresse or not relu[1]:
        return False
    jarvis_mails._contacts.update(quand=0.0, liste=[])
    jarvis_mails._derniers = []
    return True


def compte_relie(profil=False):
    """L'adresse de la boîte mail reliée au profil en cours (ou à celui donné), ou None."""
    try:
        ident = jarvis_mails.identifiants(_cibles(profil)[0])
    except Exception:
        ident = None
    return ident[0] if ident and ident[0] and ident[1] else None


def retirer(profil=False):
    """Oublie l'adresse, le mot de passe et le choix de la messagerie du profil en cours (ou de celui donné).
    Renvoie True s'il n'en reste rien."""
    compte, messagerie = _cibles(profil)
    fait = jarvis_coffre.retirer(compte)
    fait = jarvis_coffre.retirer(messagerie) and fait
    if fait:
        jarvis_mails._contacts.update(quand=0.0, liste=[])
        jarvis_mails._derniers = []
    return fait


# ---------- À la voix ----------

def commande(t, enfant=False, invite=False):
    """« relie mes mails » : ouvre la fenêtre. Renvoie la phrase à dire, ou None si ce n'est pas la demande."""
    t = (t or "").replace("’", "'").lower()
    if _ENVOI.match(t) or not _COMMANDE.search(t):       # « envoie un mail… », « lis mes mails » : pas ici
        return None
    if enfant:
        return "Relier une boîte mail, c'est un réglage pour les parents."
    if invite:
        return "En mode invité, je ne touche pas aux mails."
    ouvrir()
    if compte_relie():
        return "J'ouvre la fenêtre des mails. Une boîte mail est déjà reliée : tu peux la remplacer ou la retirer."
    return "J'ouvre la fenêtre pour relier ta boîte mail. Choisis ta messagerie, puis suis les étapes."


# ---------- La fenêtre ----------

def _prenom(profil):
    try:
        import jarvis_profils
        return jarvis_profils._lire().get(profil, {}).get("prenom", "") if profil else jarvis_profils.PRINCIPAL["prenom"]
    except Exception:
        return ""


def ouvrir():
    import jarvis_rapports_ui
    jarvis_rapports_ui._lancer("mails", _fenetre_mails)


def _fenetre_mails(fermer_apres=None, choix_initial=None):
    import threading
    import time
    import tkinter as tk
    import webbrowser
    import jarvis_rapports_ui as ui
    accent = ui._accent()
    profil = jarvis_mails.profil_actif()
    prenom = _prenom(profil)
    r, sc = ui._fenetre("Jarvis - Relier ma boîte mail", 660, 760)
    ui._titre(r, "Relier ma boîte mail" + (f" (profil de {prenom})" if profil and prenom else ""), accent)
    tk.Label(r, text="Jarvis pourra te dire si tu as de nouveaux mails, te les lire, et en envoyer après ton « oui ». "
                     "Quelle est ta messagerie ?",
             bg=ui.FOND, fg=ui.TEXTE, font=("Segoe UI", 10), wraplength=int(610 * sc),
             justify="left").pack(anchor="w", padx=24)
    grille = tk.Frame(r, bg=ui.FOND)
    grille.pack(fill="x", padx=24, pady=(10, 6))
    etapes = tk.Label(r, text="", bg=ui.PANNEAU2, fg=ui.TEXTE, font=("Segoe UI", 10), wraplength=int(580 * sc),
                      justify="left", padx=14, pady=12, anchor="w")
    etapes.pack(fill="x", padx=24)
    ligne_page = tk.Frame(r, bg=ui.FOND)
    ligne_page.pack(fill="x", padx=24, pady=(6, 0))
    formulaire = tk.Frame(r, bg=ui.FOND)
    formulaire.pack(fill="x", padx=24, pady=(10, 0))
    courant = {"cle": "gmail", "page": "", "boutons": {}}

    def champ(libelle, masque=False):
        cadre = tk.Frame(formulaire, bg=ui.FOND)
        tk.Label(cadre, text=libelle, bg=ui.FOND, fg=ui.DISCRET, font=("Segoe UI", 10), width=22,
                 anchor="w").pack(side="left")
        case = tk.Entry(cadre, bg=ui.PANNEAU2, fg=ui.TEXTE, insertbackground=ui.TEXTE, relief="flat",
                        font=("Segoe UI", 11), highlightthickness=1, highlightbackground="#1b2838",
                        highlightcolor=accent, show="•" if masque else "")
        case.pack(side="left", fill="x", expand=True, ipady=5)
        return cadre, case

    cadre_adresse, case_adresse = champ("Ton adresse mail :")
    cadre_mot, case_mot = champ("Mot de passe :", masque=True)
    cadre_imap, case_imap = champ("Serveur de réception :")
    cadre_smtp, case_smtp = champ("Serveur d'envoi :")

    def choisir(nom):
        courant["cle"] = nom
        adresse_reliee = compte_relie(profil)
        deja = jarvis_mails.reglages(adresse_reliee)["cle"] if adresse_reliee else None
        for cle, libelle, page, lignes in SERVICES:
            actif = cle == nom
            courant["boutons"][cle].configure(bg=accent if actif else "#1b2838", fg="#0b0f14" if actif else ui.TEXTE,
                                              text=libelle + ("  ✓" if cle == deja else ""))   # la boîte déjà reliée
            if actif:
                etapes.configure(text="\n".join(lignes))
                courant["page"] = page
        for enfant_ in ligne_page.winfo_children():
            enfant_.destroy()
        if courant["page"]:
            ui._bouton(ligne_page, "Ouvrir la page pour créer ce code",
                       lambda: webbrowser.open(courant["page"])).pack(side="left")
        for cadre in (cadre_adresse, cadre_mot, cadre_imap, cadre_smtp):
            cadre.pack_forget()
        if nom != "microsoft":
            cadre_adresse.pack(fill="x", pady=3)
            cadre_mot.pack(fill="x", pady=3)
            if nom == "autre":
                cadre_imap.pack(fill="x", pady=3)
                cadre_smtp.pack(fill="x", pady=3)

    for i, (cle, libelle, page, lignes) in enumerate(SERVICES):
        b = tk.Label(grille, text=libelle, bg="#1b2838", fg=ui.TEXTE, font=("Segoe UI Semibold", 10), padx=10, pady=7,
                     cursor="hand2")
        b.bind("<Button-1>", lambda e, n=cle: choisir(n))
        b.grid(row=i // 4, column=i % 4, sticky="ew", padx=(0, 8), pady=(0, 8))
        courant["boutons"][cle] = b
    for colonne in range(4):
        grille.columnconfigure(colonne, weight=1, uniform="messageries")

    etat = tk.Label(r, text="", bg=ui.FOND, fg=ui.DISCRET, font=("Segoe UI", 10), wraplength=int(610 * sc),
                    justify="left")
    etat.pack(anchor="w", padx=24, pady=(10, 0))
    tk.Label(r, text=AVERTISSEMENT, bg=ui.FOND, fg=ui.DISCRET, font=("Segoe UI", 9), wraplength=int(610 * sc),
             justify="left").pack(anchor="w", padx=24, pady=(8, 0))
    bas = tk.Frame(r, bg=ui.FOND)
    bas.pack(side="bottom", fill="x", padx=24, pady=18)
    occupe = {"oui": False, "retrait": 0.0}

    def dire(texte, couleur=None):
        etat.configure(text=texte, fg=couleur or ui.DISCRET)

    def tester():
        if occupe["oui"]:
            return
        if courant["cle"] == "microsoft":
            dire(jarvis_mails.REFUS_MICROSOFT, accent)
            return
        occupe["oui"] = True
        valeurs = (courant["cle"], case_adresse.get(), case_mot.get(), case_imap.get(), case_smtp.get())
        dire("J'essaie la connexion… (jusqu'à une demi-minute)")
        r.update_idletasks()

        def fil():
            resultat = essayer(*valeurs)
            fait = enregistrer(resultat, profil) if resultat["ok"] else False
            try:
                r.after(0, lambda: fin(resultat, fait))
            except Exception:
                pass
        threading.Thread(target=fil, daemon=True).start()

    def fin(resultat, fait):
        occupe["oui"] = False
        if not resultat["ok"]:
            dire(resultat["message"], "#ff6b6b")
        elif not fait:
            dire("La connexion marche, mais Windows a refusé de ranger le mot de passe. Réessaie.", "#ff6b6b")
        else:
            dire(resultat["message"] + " Ta boîte mail est reliée. Essaie : « Jarvis, est-ce que j'ai des "
                 "nouveaux mails ? »", accent)
            case_mot.delete(0, "end")
            montrer_retrait()
            choisir(courant["cle"])

    def retirer_compte():
        if time.time() - occupe["retrait"] > 6:           # premier clic : on demande de confirmer
            occupe["retrait"] = time.time()
            dire("Clique encore une fois sur « Retirer ma boîte mail » pour confirmer. Jarvis oubliera l'adresse et "
                 "le mot de passe ; tes mails, eux, ne changent pas.", accent)
            return
        occupe["retrait"] = 0.0
        if retirer(profil):
            dire("C'est fait : Jarvis n'a plus accès à ta boîte mail.", accent)
            montrer_retrait()
            choisir(courant["cle"])
        else:
            dire("Windows a refusé de retirer le mot de passe. Réessaie.", "#ff6b6b")

    bouton_retrait = ui._bouton(bas, "Retirer ma boîte mail", retirer_compte)

    def montrer_retrait():
        if compte_relie(profil):
            bouton_retrait.pack(side="left")
        else:
            bouton_retrait.pack_forget()

    ui._bouton(bas, "Essayer et relier", tester, fort=True, accent=accent).pack(side="right")
    ui._bouton(bas, "Fermer", r.destroy).pack(side="right", padx=10)
    for case in (case_adresse, case_mot, case_imap, case_smtp):
        case.bind("<Return>", lambda e: tester())

    deja = compte_relie(profil)
    depart = choix_initial
    if not depart and deja:
        depart = jarvis_mails.reglages(deja)["cle"]
    choisir(depart if depart in courant["boutons"] else "gmail")
    montrer_retrait()
    if deja:
        case_adresse.insert(0, deja)
        nom_deja = jarvis_mails.reglages(deja)["nom"]
        dire("✓ Ta boîte mail " + (nom_deja + " " if nom_deja != "ta messagerie" else "") + "(" + deja + ") est reliée "
             "à Jarvis. Rien à faire. Pour en changer, écris la nouvelle adresse et son mot de passe ; pour l'enlever, "
             "clique sur « Retirer ma boîte mail ».", accent)
    case_adresse.focus_set()
    if fermer_apres:                                      # pour les essais automatiques
        r.after(int(fermer_apres * 1000), r.destroy)
    r.mainloop()
