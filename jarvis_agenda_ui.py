# -*- coding: utf-8 -*-
"""
JARVIS - relier son agenda (Google Agenda, Outlook, iCloud ou tout agenda qui donne un lien « ICS »).

  « relie mon agenda », « connecte mon calendrier », « configure l'agenda »   -> la fenêtre s'ouvre
La fenêtre explique où trouver le lien privé de l'agenda, le teste (est-ce bien un agenda ? combien de
rendez-vous ?) puis le range dans le Gestionnaire d'identification de Windows (jamais dans un fichier).
Jarvis lit ensuite l'agenda avec jarvis_agenda.py, sans compte ni mot de passe. Lecture seule : Jarvis
n'écrit jamais dans l'agenda.
"""

import re
import time
import urllib.error
import urllib.request

import jarvis_agenda
import jarvis_coffre

SERVICES = (
    ("google", "Google Agenda", "https://calendar.google.com/calendar/u/0/r/settings",
     ("Sur un ordinateur, ouvre Google Agenda (bouton ci-dessous).",
      "À gauche, sous « Paramètres de mes agendas », clique sur le nom de ton agenda.",
      "Descends jusqu'à « Intégrer l'agenda ».",
      "Copie l'« Adresse secrète au format iCal » (elle se termine par .ics).",
      "Colle-la ci-dessous.")),
    ("outlook", "Outlook", "https://outlook.live.com/calendar/0/options/calendar/SharedCalendars",
     ("Ouvre Outlook sur le web (bouton ci-dessous) : Paramètres, Calendrier, Calendriers partagés.",
      "Dans « Publier un calendrier », choisis ton calendrier et « Peut afficher tous les détails ».",
      "Clique sur « Publier ».",
      "Copie le lien « ICS » (pas le lien « HTML »).",
      "Colle-le ci-dessous.")),
    ("icloud", "iCloud (iPhone)", "",
     ("Sur l'iPhone, ouvre l'app Calendrier et touche « Calendriers », en bas.",
      "Touche le ⓘ à côté de ton agenda.",
      "Active « Calendrier public », puis touche « Partager le lien ».",
      "Envoie-toi ce lien (par mail par exemple) pour l'ouvrir sur ce PC.",
      "Colle-le ci-dessous.")),
    ("autre", "Autre agenda", "",
     ("Beaucoup d'agendas donnent un lien de partage au format « ICS » ou « iCal »",
      "(Proton, Nextcloud, Zimbra, Yahoo, Doctolib, un club de sport, une école…).",
      "Cherche « partager », « publier » ou « exporter le lien » dans ses réglages.",
      "Le lien commence par https:// ou webcal:// et se termine souvent par .ics.",
      "Colle-le ci-dessous.")),
)
AVERTISSEMENT = ("Ce lien est privé : toute personne qui l'a peut lire ton agenda. Jarvis le garde dans le coffre de "
                 "Windows, sur ce PC seulement, et ne fait que lire l'agenda.")

_COMMANDE = re.compile(
    r"\b(?:relie[rz]?|reli[ée]|connecte[rz]?|configure[rz]?|param[eè]tre[rz]?|synchronise[rz]?|associe[rz]?|branche[rz]?"
    r"|d[ée]connecte[rz]?|d[ée]lie[rz]?)\b\W+(?:moi \W*)?(?:mon |ton |l'|le |notre |un |mes |nos )?"
    r"(?:agendas?|calendriers?)\b"
    r"|^\W*(?:ajoute[rz]?|change[rz]?|retire[rz]?|enl[eè]ve[rz]?)\W+(?:mon |l'|un |le lien (?:de |d')(?:mon |l'))"
    r"(?:agenda|calendrier)(?:\W+(?:google|outlook|icloud|apple|hotmail|microsoft))?\W*$")


def _ouvrir_adresse(adresse, delai=15):
    requete = urllib.request.Request(adresse, headers={"User-Agent": "Jarvis"})
    with urllib.request.urlopen(requete, timeout=delai) as r:
        return r.read(2_000_000).decode("utf-8", "replace")


def nettoyer(adresse):
    """Le lien tel qu'il sera rangé : sans espaces, guillemets ni chevrons autour (souvent collés avec)."""
    adresse = (adresse or "").strip().strip("<>\"'«» \t\r\n")
    return re.sub(r"\s+", "", adresse)


def verifier_lien(adresse, ouvrir=None):
    """Teste le lien d'un agenda. Renvoie {"ok": bool, "message": phrase à afficher, "adresse": lien nettoyé,
    "nombre": nombre de rendez-vous lus}. Ne range rien."""
    adresse = nettoyer(adresse)
    resultat = {"ok": False, "message": "", "adresse": adresse, "nombre": 0}
    if not adresse:
        resultat["message"] = "Colle d'abord le lien de ton agenda dans la case."
        return resultat
    if not re.match(r"(?:https?|webcal)://[^/\s]+\.[^/\s]+", adresse, re.I):
        resultat["message"] = "Ce n'est pas un lien : il doit commencer par https:// ou webcal://."
        return resultat
    if len(adresse) > jarvis_coffre.TAILLE_MAX:
        resultat["message"] = "Ce lien est trop long pour être rangé. Vérifie que tu n'as collé que le lien."
        return resultat
    bas = adresse.lower()
    if "calendar.google.com" in bas and "/ical/" not in bas:
        resultat["message"] = ("C'est le lien de la page Google Agenda, pas celui de l'agenda. Il faut l'« Adresse "
                               "secrète au format iCal », qui se termine par .ics (étape 4).")
        return resultat
    if re.search(r"outlook\.|office365\.|office\.com", bas) and bas.split("?")[0].endswith(".html"):
        resultat["message"] = "C'est le lien « HTML ». Prends l'autre, le lien « ICS », juste en dessous."
        return resultat
    try:
        texte = (ouvrir or _ouvrir_adresse)(re.sub(r"^webcal://", "https://", adresse, flags=re.I))
    except urllib.error.HTTPError as erreur:
        resultat["message"] = (f"Ce lien est refusé (erreur {erreur.code}). Il a peut-être été désactivé, ou il "
                               "manque un morceau : recopie-le en entier.")
        return resultat
    except (urllib.error.URLError, TimeoutError, OSError) as erreur:
        resultat["message"] = ("Je n'arrive pas à ouvrir ce lien. Vérifie qu'Internet marche et que le lien est "
                               "complet, puis réessaie.")
        print("Agenda (essai du lien) :", type(erreur).__name__)
        return resultat
    except Exception as erreur:
        resultat["message"] = "Ce lien n'est pas lisible. Recopie-le en entier, puis réessaie."
        print("Agenda (essai du lien) :", type(erreur).__name__)
        return resultat
    if "BEGIN:VCALENDAR" not in (texte or ""):
        resultat["message"] = ("Ce lien n'ouvre pas un agenda (c'est sans doute une page web). Il faut le lien "
                               "« ICS » ou « iCal » de l'agenda.")
        return resultat
    try:
        nombre = len(jarvis_agenda._evenements_bruts(texte))
    except Exception:
        nombre = texte.count("BEGIN:VEVENT")
    resultat.update(ok=True, nombre=nombre, texte=texte,
                    message=("C'est bien un agenda : " + ("aucun rendez-vous pour l'instant." if nombre == 0 else
                             "1 rendez-vous trouvé." if nombre == 1 else f"{nombre} rendez-vous trouvés.")))
    return resultat


def relie(profil=False):
    """Vrai si le profil en cours (ou celui donné) a relié son propre agenda."""
    return bool(jarvis_agenda.lien_du_profil(profil))


def agenda_du_foyer(profil=False):
    """Toujours faux : chaque profil ne lit que son propre agenda (séparation stricte, comme pour les mails)."""
    return False


def service_relie(profil=False):
    """L'agenda relié par ce profil, reconnu à son lien : « google », « outlook », « icloud » ou « autre » ;
    None s'il n'a rien relié."""
    lien = (jarvis_agenda.lien_du_profil(profil) or "").lower()
    if not lien:
        return None
    hote = re.sub(r"^\w+://", "", lien).split("/")[0]
    if "icloud.com" in hote or "me.com" in hote:
        return "icloud"
    if "google.com" in hote:
        return "google"
    if re.search(r"outlook\.|office365\.|office\.com|live\.com", hote):
        return "outlook"
    return "autre"


def nom_service(cle):
    """« Google Agenda », « Outlook », « iCloud »… pour l'affichage (« » pour un autre agenda)."""
    return {"google": "Google Agenda", "outlook": "Outlook", "icloud": "iCloud"}.get(cle, "")


def enregistrer(adresse, texte=None, profil=False):
    """Range le lien (déjà testé) pour le profil en cours (ou celui donné) et fait relire l'agenda tout de suite.
    Renvoie True si c'est fait."""
    adresse = nettoyer(adresse)
    if not jarvis_coffre.ranger(jarvis_agenda.cible(profil), "agenda", adresse):
        return False
    if jarvis_agenda.lien_du_profil(profil) != adresse:    # relu dans le coffre : c'est bien ce lien-là qui sert
        return False
    with jarvis_agenda._verrou:
        # l'agenda qu'on vient de lire pendant le test sert tout de suite (pas de second téléchargement)
        jarvis_agenda._cache.update(quand=time.time() if texte else 0.0, texte=texte,
                                    adresse=re.sub(r"^webcal://", "https://", adresse) if texte else None)
    return True


def retirer(profil=False):
    """Oublie le lien de l'agenda du profil en cours (ou de celui donné). Renvoie True s'il n'y en a plus."""
    fait = jarvis_coffre.retirer(jarvis_agenda.cible(profil))
    if fait:
        with jarvis_agenda._verrou:
            jarvis_agenda._cache.update(quand=0.0, texte=None, adresse=None)
    return fait


# ---------- À la voix ----------

def commande(t, enfant=False, invite=False):
    """« relie mon agenda » : ouvre la fenêtre. Renvoie la phrase à dire, ou None si ce n'est pas la demande."""
    t = (t or "").replace("’", "'").lower()
    if not _COMMANDE.search(t):
        return None
    if enfant:
        return "Relier un agenda, c'est un réglage pour les parents."
    if invite:
        return "En mode invité, je ne touche pas à l'agenda."
    ouvrir()
    if relie():
        return "J'ouvre la fenêtre de l'agenda. Ton agenda est déjà relié : tu peux le remplacer ou le retirer."
    if agenda_du_foyer():
        return ("J'ouvre la fenêtre de l'agenda. Sur ton profil, je lis pour l'instant l'agenda du foyer : "
                "tu peux relier le tien.")
    return "J'ouvre la fenêtre pour relier ton agenda. Choisis ton agenda, puis suis les étapes."


# ---------- La fenêtre ----------

def ouvrir():
    import jarvis_rapports_ui
    jarvis_rapports_ui._lancer("agenda", _fenetre_agenda)


def _fenetre_agenda(fermer_apres=None):
    import threading
    import tkinter as tk
    import webbrowser
    import jarvis_rapports_ui as ui
    accent = ui._accent()
    import jarvis_mails
    profil = jarvis_mails.profil_actif()          # la fenêtre garde le profil pour lequel elle a été ouverte
    try:
        import jarvis_profils
        prenom = jarvis_profils._lire().get(profil, {}).get("prenom", "") if profil else ""
    except Exception:
        prenom = ""
    r, sc = ui._fenetre("Jarvis - Relier mon agenda", 620, 640)
    ui._titre(r, "Relier mon agenda" + (f" (profil de {prenom})" if prenom else ""), accent)
    tk.Label(r, text="Jarvis pourra te dire tes rendez-vous (« qu'est-ce que j'ai demain ? », « c'est quand le "
                     "dentiste ? ») et te les rappeler la veille au soir. Quel agenda utilises-tu ?",
             bg=ui.FOND, fg=ui.TEXTE, font=("Segoe UI", 10), wraplength=int(570 * sc),
             justify="left").pack(anchor="w", padx=24)
    choix = tk.Frame(r, bg=ui.FOND)
    choix.pack(fill="x", padx=24, pady=(10, 6))
    etapes = tk.Label(r, text="", bg=ui.PANNEAU2, fg=ui.TEXTE, font=("Segoe UI", 10), wraplength=int(540 * sc),
                      justify="left", padx=14, pady=12, anchor="w")
    etapes.pack(fill="x", padx=24)
    ligne_page = tk.Frame(r, bg=ui.FOND)
    ligne_page.pack(fill="x", padx=24, pady=(6, 0))
    courant = {"page": "", "boutons": {}}

    def choisir(nom):
        deja = service_relie(profil)
        for cle, libelle, page, lignes in SERVICES:
            bouton = courant["boutons"][cle]
            actif = cle == nom
            bouton.configure(bg=accent if actif else "#1b2838", fg="#0b0f14" if actif else ui.TEXTE,
                             text=libelle + ("  ✓" if cle == deja else ""))      # la coche : l'agenda déjà relié
            if actif:
                etapes.configure(text="\n".join((f"{i}. {l}" if nom != "autre" else l) for i, l in enumerate(lignes, 1)))
                courant["page"] = page
        for enfant_ in ligne_page.winfo_children():
            enfant_.destroy()
        if courant["page"]:
            ui._bouton(ligne_page, "Ouvrir la page des réglages de l'agenda",
                       lambda: webbrowser.open(courant["page"])).pack(side="left")

    for cle, libelle, page, lignes in SERVICES:
        b = tk.Label(choix, text=libelle, bg="#1b2838", fg=ui.TEXTE, font=("Segoe UI Semibold", 10), padx=12, pady=7,
                     cursor="hand2")
        b.bind("<Button-1>", lambda e, n=cle: choisir(n))
        b.pack(side="left", padx=(0, 8))
        courant["boutons"][cle] = b

    tk.Label(r, text="Le lien de ton agenda :", bg=ui.FOND, fg=ui.DISCRET,
             font=("Segoe UI", 10)).pack(anchor="w", padx=24, pady=(14, 2))
    ligne = tk.Frame(r, bg=ui.FOND)
    ligne.pack(fill="x", padx=24)
    case = tk.Entry(ligne, bg=ui.PANNEAU2, fg=ui.TEXTE, insertbackground=ui.TEXTE, relief="flat",
                    font=("Segoe UI", 11), highlightthickness=1, highlightbackground="#1b2838", highlightcolor=accent)

    def coller():
        try:
            texte = r.clipboard_get()
        except Exception:
            texte = ""
        if texte:
            case.delete(0, "end")
            case.insert(0, nettoyer(texte))
    ui._bouton(ligne, "Coller", coller).pack(side="right", padx=(8, 0))
    case.pack(side="left", fill="x", expand=True, ipady=6)
    etat = tk.Label(r, text="", bg=ui.FOND, fg=ui.DISCRET, font=("Segoe UI", 10), wraplength=int(570 * sc),
                    justify="left")
    etat.pack(anchor="w", padx=24, pady=(8, 0))
    tk.Label(r, text=AVERTISSEMENT, bg=ui.FOND, fg=ui.DISCRET, font=("Segoe UI", 9), wraplength=int(570 * sc),
             justify="left").pack(anchor="w", padx=24, pady=(8, 0))
    bas = tk.Frame(r, bg=ui.FOND)
    bas.pack(side="bottom", fill="x", padx=24, pady=18)
    occupe = {"oui": False, "retrait": 0.0}

    def dire(texte, couleur=None):
        etat.configure(text=texte, fg=couleur or ui.DISCRET)

    def tester():
        if occupe["oui"]:
            return
        occupe["oui"] = True
        adresse = case.get()
        dire("Je teste le lien…")
        r.update_idletasks()

        def fil():
            resultat = verifier_lien(adresse)
            fait = enregistrer(resultat["adresse"], resultat.get("texte"), profil) if resultat["ok"] else False
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
            dire("Le lien est bon, mais Windows a refusé de le ranger. Réessaie.", "#ff6b6b")
        else:
            dire(resultat["message"] + " Ton agenda est relié. Essaie : « Jarvis, qu'est-ce que j'ai cette "
                 "semaine ? »", accent)
            case.delete(0, "end")
            montrer_retrait()
            choisir(service_relie(profil) or courant.get("cle") or "google")

    def retirer_lien():
        import time
        if time.time() - occupe["retrait"] > 6:           # premier clic : on demande de confirmer
            occupe["retrait"] = time.time()
            dire("Clique encore une fois sur « Retirer l'agenda relié » pour confirmer. Jarvis oubliera le lien ; "
                 "ton agenda, lui, ne change pas.", accent)
            return
        occupe["retrait"] = 0.0
        if retirer(profil):
            dire("C'est fait : Jarvis n'a plus accès à ton agenda.", accent)
            montrer_retrait()
            choisir("google")
        else:
            dire("Windows a refusé de retirer le lien. Réessaie.", "#ff6b6b")

    bouton_retrait = ui._bouton(bas, "Retirer l'agenda relié", retirer_lien)

    def montrer_retrait():
        if relie(profil):
            bouton_retrait.pack(side="left")
        else:
            bouton_retrait.pack_forget()

    ui._bouton(bas, "Tester et relier", tester, fort=True, accent=accent).pack(side="right")
    ui._bouton(bas, "Fermer", r.destroy).pack(side="right", padx=10)
    case.bind("<Return>", lambda e: tester())
    deja = service_relie(profil)
    choisir(deja or "google")
    montrer_retrait()
    if not deja and agenda_du_foyer(profil):
        dire("Pour l'instant, sur ton profil, Jarvis lit l'agenda du foyer. Relie ton propre agenda ici : c'est lui "
             "que Jarvis lira sur ton profil.")
    if deja:
        dire("✓ Ton agenda " + (nom_service(deja) + " " if nom_service(deja) else "") + "est relié à Jarvis. Rien à "
             "faire. Pour en changer, colle un nouveau lien ; pour l'enlever, clique sur « Retirer l'agenda relié ».",
             accent)
    case.focus_set()
    if fermer_apres:                                      # pour les essais automatiques
        r.after(int(fermer_apres * 1000), r.destroy)
    r.mainloop()
