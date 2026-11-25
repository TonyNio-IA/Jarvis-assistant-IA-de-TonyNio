"""
JARVIS - les mails, seulement quand on les demande.

  « Jarvis, est-ce que j'ai des nouveaux mails ? »  -> le nombre de mails non lus et leurs expéditeurs
  « Jarvis, lis-moi mes mails »                      -> l'expéditeur et l'objet des 5 derniers non lus
  « Jarvis, lis-moi le premier mail »                -> le début du texte de ce mail (le 2e, le 3e...)

  « Jarvis, envoie un mail à Marie pour lui dire que je serai en retard »  -> lu, affiché, puis envoyé
  « Jarvis, envoie-moi un mail pour me rappeler d'appeler le garage »         seulement après « oui »

Jarvis ne dit jamais rien tout seul. Il ne supprime et ne déplace aucun mail, et les mails lus par lui
restent « non lus » dans ta messagerie. Il n'envoie un mail que sur demande, après l'avoir lu à voix haute
et attendu ton « oui » ; le destinataire doit être quelqu'un à qui tu as déjà écrit, ou, avec iCloud, un de
tes contacts qui a une adresse mail. Refusé en mode enfant et en mode invité.
Le contenu des mails n'est pas envoyé à Claude : il est seulement lu à voix haute.

Mise en place (une fois) : « Jarvis, relie mes mails » ouvre une fenêtre qui guide pas à pas (Gmail, Orange,
Free, La Poste, Yahoo, iCloud ou une autre messagerie « IMAP » ; voir jarvis_mails_ui.py). Le mot de passe
n'est jamais écrit dans un fichier : Windows le range dans son Gestionnaire d'identification, sous le nom
« Jarvis-Mails ». L'ancienne méthode marche toujours : dans PowerShell,
    cmdkey /generic:Jarvis-Mails /user:ton.adresse@icloud.com /pass
et, pour une messagerie qui n'est pas reconnue à son adresse, dans config.json :
    "mails": {"serveur": "imap.exemple.fr"}
Outlook.com, Hotmail et Live ne sont pas encore possibles (Microsoft refuse les mots de passe).
"""

import ctypes
import ctypes.wintypes as wt
import email
import email.header
import email.utils
import html
import imaplib
import json
import re
import socket

import jarvis_config

CIBLE = "Jarvis-Mails"
CIBLE_REGLAGES = "Jarvis-Mails-Reglages"      # la messagerie choisie dans la fenêtre « relier mes mails »
SERVEUR = None                                # (pour les essais : force le serveur de réception)
ENVOI_PAR_DEFAUT = ((587, "starttls"), (465, "ssl"))
# Les messageries courantes en France. « envoi » : les réglages d'envoi à essayer, dans l'ordre.
# « copie » : Jarvis range lui-même une copie dans « Envoyés » sans vérifier (iCloud ne le fait jamais seul) ;
# pour les autres, il regarde d'abord si la messagerie l'a déjà rangée (Gmail le fait), pour ne pas la doubler.
FOURNISSEURS = {
    "gmail": {"nom": "Gmail", "imap": "imap.gmail.com", "smtp": "smtp.gmail.com",
              "envoi": ((587, "starttls"), (465, "ssl")), "domaines": ("gmail.com", "googlemail.com")},
    "orange": {"nom": "Orange", "imap": "imap.orange.fr", "smtp": "smtp.orange.fr",
               "envoi": ((465, "ssl"), (587, "starttls")), "domaines": ("orange.fr", "wanadoo.fr")},
    "free": {"nom": "Free", "imap": "imap.free.fr", "smtp": "smtp.free.fr",
             "envoi": ((587, "starttls"), (465, "ssl")), "domaines": ("free.fr",)},
    "laposte": {"nom": "La Poste", "imap": "imap.laposte.net", "smtp": "smtp.laposte.net",
                "envoi": ((465, "ssl"), (587, "starttls")), "domaines": ("laposte.net",)},
    "yahoo": {"nom": "Yahoo", "imap": "imap.mail.yahoo.com", "smtp": "smtp.mail.yahoo.com",
              "envoi": ((465, "ssl"), (587, "starttls")),
              "domaines": ("yahoo.fr", "yahoo.com", "ymail.com", "rocketmail.com")},
    "icloud": {"nom": "iCloud", "imap": "imap.mail.me.com", "smtp": "smtp.mail.me.com",
               "envoi": ((587, "starttls"),), "domaines": ("icloud.com", "me.com", "mac.com"), "copie": True},
}
# Outlook.com, Hotmail, Live : Microsoft n'accepte plus les mots de passe depuis septembre 2024 (connexion
# « OAuth2 » seulement). Pas encore possible avec Jarvis.
MICROSOFT = ("outlook.fr", "outlook.com", "hotmail.fr", "hotmail.com", "live.fr", "live.com", "msn.com")
REFUS_MICROSOFT = ("Les adresses Outlook, Hotmail et Live ne marchent pas encore avec Jarvis : Microsoft n'accepte "
                   "plus les mots de passe pour les applications. C'est prévu pour une prochaine version.")


def profil_actif():
    """Identifiant du profil en cours (« marie »), ou None pour le profil principal."""
    try:
        import jarvis_profils
        return jarvis_profils.actif() or None
    except Exception:
        return None


def cible(base=None, profil=False):
    """Le nom sous lequel le coffre de Windows range le compte du profil en cours : « Jarvis-Mails » pour le
    profil principal (comme avant), « Jarvis-Mails-profil-marie » pour le profil de Marie. Chaque profil a sa
    propre boîte mail : personne ne lit ni n'envoie les mails d'un autre.
    profil : False = le profil en cours ; None = le profil principal ; sinon l'identifiant d'un profil."""
    base = base or CIBLE
    ident = profil_actif() if profil is False else profil
    return base if not ident else f"{base}-profil-{ident}"


def fournisseur_de(adresse):
    """La messagerie d'une adresse d'après ce qui suit le @ : « gmail », « orange »…, « microsoft », ou None."""
    domaine = (adresse or "").strip().lower().rsplit("@", 1)[-1]
    if domaine in MICROSOFT:
        return "microsoft"
    return next((cle for cle, f in FOURNISSEURS.items() if domaine in f["domaines"]), None)


def reglages_pour(cle=None, imap=None, smtp=None, port=None):
    """Les réglages d'une messagerie connue (« gmail »…) ou d'une autre, décrite par ses serveurs."""
    if cle in FOURNISSEURS:
        return dict(FOURNISSEURS[cle], cle=cle)
    imap = re.sub(r"^\w+://", "", str(imap or "")).strip().strip("/").lower()
    if not imap:
        return dict(FOURNISSEURS["icloud"], cle="icloud")
    connu = next((c for c, f in FOURNISSEURS.items() if f["imap"] == imap), None)
    if connu and not smtp:
        return dict(FOURNISSEURS[connu], cle=connu)
    smtp = re.sub(r"^\w+://", "", str(smtp or "")).strip().strip("/").lower() or re.sub(r"^imap\.", "smtp.", imap)
    envoi = ENVOI_PAR_DEFAUT
    try:
        if port:
            port = int(port)
            envoi = ((port, "ssl" if port == 465 else "starttls"),) + tuple(e for e in ENVOI_PAR_DEFAUT if e[0] != port)
    except (TypeError, ValueError):
        pass
    return {"cle": "autre", "nom": "ta messagerie", "imap": imap, "smtp": smtp, "envoi": envoi}


def reglages(adresse=None):
    """Les réglages de la messagerie de l'utilisateur. Dans l'ordre : le choix fait dans la fenêtre « relier mes
    mails », puis config.json ("mails": {"serveur": ...}), puis l'adresse elle-même (@gmail.com → Gmail…),
    et enfin iCloud, comme avant."""
    try:
        choix = identifiants(cible(CIBLE_REGLAGES))
    except Exception:
        choix = None
    if choix and choix[0]:
        if choix[0] in FOURNISSEURS:
            return reglages_pour(choix[0])
        if choix[0] == "autre":
            try:
                d = json.loads(choix[1])
                if d.get("imap"):
                    return reglages_pour(None, d["imap"], d.get("smtp"), d.get("port"))
            except Exception:
                pass
    conf = jarvis_config._lu.get("mails")
    if isinstance(conf, dict) and conf.get("serveur"):
        return reglages_pour(None, conf["serveur"], conf.get("smtp"), conf.get("port_smtp"))
    if adresse is None:
        try:
            ident = identifiants(cible(CIBLE))
        except Exception:
            ident = None
        adresse = ident[0] if ident else ""
    cle = fournisseur_de(adresse)
    return reglages_pour(cle if cle in FOURNISSEURS else "icloud")


def _serveur():
    return SERVEUR or reglages()["imap"]
NB_LUS = 5
LONGUEUR_LECTURE = 900          # caractères lus d'un mail (environ une minute)

_derniers = []                  # numéros des mails annoncés, pour « lis le deuxième mail »
_memoire_de = {"cible": None}   # le compte auquel appartiennent _derniers et _contacts (ils changent avec le profil)


def _bon_compte():
    """Appelé avant chaque lecture : si le profil a changé, ce qui a été retenu pour l'autre compte est oublié."""
    global _derniers
    actuelle = cible(CIBLE)
    if _memoire_de["cible"] is None:              # première lecture depuis le démarrage : rien à oublier
        _memoire_de["cible"] = actuelle
        return
    if _memoire_de["cible"] != actuelle:
        _memoire_de["cible"] = actuelle
        _derniers = []
        try:
            _contacts.update(quand=0.0, liste=[])
        except NameError:
            pass


# ---------- Identifiants rangés par Windows (Gestionnaire d'identification) ----------

class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wt.DWORD),
                ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
                ("UserName", wt.LPWSTR)]


def identifiants(cible=CIBLE):
    """(identifiant, mot de passe) rangés sous « Jarvis-Mails » (ou un autre nom), ou None."""
    try:
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
        advapi.CredReadW.restype = wt.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        pointeur = ctypes.POINTER(_CREDENTIAL)()
        if not advapi.CredReadW(cible, 1, 0, ctypes.byref(pointeur)):      # 1 = identifiant générique
            return None
        try:
            c = pointeur.contents
            octets = bytes(c.CredentialBlob[i] for i in range(c.CredentialBlobSize))
            # cmdkey range le mot de passe en UTF-16 ; d'autres outils en UTF-8
            try:
                mot = octets.decode("utf-16-le") if len(octets) % 2 == 0 and b"\x00" in octets else octets.decode()
            except UnicodeDecodeError:
                mot = octets.decode("latin-1")
            mot = mot.strip()
            # Rien ne s'affiche pendant la frappe : le code est parfois collé plusieurs fois de suite
            for n in (2, 3, 4):
                if len(mot) % n == 0 and mot == mot[:len(mot) // n] * n:
                    mot = mot[:len(mot) // n]
                    break
            return (c.UserName or "").strip(), mot
        finally:
            advapi.CredFree(pointeur)
    except Exception:
        return None


# ---------- Lecture ----------

def _decoder(valeur):
    morceaux = []
    for texte, codage in email.header.decode_header(valeur or ""):
        if isinstance(texte, bytes):
            try:
                texte = texte.decode(codage or "utf-8", "replace")
            except LookupError:
                texte = texte.decode("utf-8", "replace")
        morceaux.append(texte)
    return " ".join("".join(morceaux).split())


def _expediteur(valeur):
    nom, adresse = email.utils.parseaddr(_decoder(valeur))
    return nom.strip('" ') or adresse.split("@")[0] or "un expéditeur inconnu"


def _texte(message):
    """Le texte lisible d'un mail (la partie texte, sinon la partie HTML sans balises)."""
    texte_html = None
    for partie in message.walk():
        if partie.get_content_maintype() == "multipart" or partie.get_filename():
            continue
        type_ = partie.get_content_type()
        try:
            contenu = partie.get_payload(decode=True) or b""
            contenu = contenu.decode(partie.get_content_charset() or "utf-8", "replace")
        except Exception:
            continue
        if type_ == "text/plain" and contenu.strip():
            return contenu
        if type_ == "text/html" and texte_html is None:
            contenu = re.sub(r"(?is)<(script|style).*?</\1>", " ", contenu)
            texte_html = html.unescape(re.sub(r"<[^>]+>", " ", contenu))
    return texte_html or ""


def _connexion(ecriture=False):
    _bon_compte()
    ident = identifiants(cible())
    if not ident or not ident[0] or not ident[1]:
        raise LookupError
    boite = imaplib.IMAP4_SSL(_serveur(), 993, timeout=15)
    boite.login(*ident)
    statut = boite.select("INBOX", readonly=not ecriture)    # lecture seule sauf « marque comme lus »
    if ecriture and statut[0] != "OK":
        raise PermissionError
    return boite


def _non_lus(boite):
    statut, donnees = boite.search(None, "UNSEEN")
    numeros = donnees[0].split() if statut == "OK" and donnees and donnees[0] else []
    return list(reversed(numeros))                # le plus récent d'abord


def _recents(boite, nombre=NB_LUS):
    """Les derniers mails reçus, lus ou non (le plus récent d'abord)."""
    statut, donnees = boite.search(None, "ALL")
    numeros = donnees[0].split() if statut == "OK" and donnees and donnees[0] else []
    return list(reversed(numeros[-nombre:]))


def _entetes(boite, numero):
    statut, donnees = boite.fetch(numero, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
    brut = next((d[1] for d in donnees if isinstance(d, tuple)), b"")
    m = email.message_from_bytes(brut)
    return _expediteur(m.get("From")), _decoder(m.get("Subject")) or "sans objet"


def _erreur(erreur):
    if isinstance(erreur, LookupError):
        if profil_actif():
            return ("Tu n'as pas encore relié de boîte mail sur ton profil : chaque profil a la sienne. "
                    "Dis « relie mes mails » : une fenêtre te guide.")
        return ("Je n'ai pas encore accès à ta boîte mail. Dis « relie mes mails » : une fenêtre te guide, "
                "avec Gmail, Orange, Free, La Poste, Yahoo ou iCloud.")
    if isinstance(erreur, imaplib.IMAP4.error):
        return ("Ta boîte mail a refusé la connexion : le mot de passe est peut-être faux ou expiré. "
                "Dis « relie mes mails » pour le remettre.")
    if isinstance(erreur, (socket.timeout, OSError)):
        return "Je n'arrive pas à joindre ta boîte mail. Internet fonctionne ?"
    return "Je n'arrive pas à lire tes mails pour le moment."


def nouveaux():
    global _derniers
    try:
        boite = _connexion()
        try:
            numeros = _non_lus(boite)
            _derniers = numeros[:NB_LUS]
            if not numeros:
                return "Tu n'as aucun nouveau mail."
            noms = []
            for n in numeros[:3]:
                nom = _entetes(boite, n)[0]
                if nom not in noms:
                    noms.append(nom)
            de = " et ".join([", ".join(noms[:-1]), noms[-1]] if len(noms) > 1 else noms)
            total = len(numeros)
            debut = "Tu as un nouveau mail" if total == 1 else f"Tu as {total} nouveaux mails"
            return f"{debut}, notamment de {de}." if total > len(noms) else f"{debut}, de {de}."
        finally:
            boite.logout()
    except Exception as erreur:
        if not isinstance(erreur, LookupError):
            print("Mails :", erreur)
        return _erreur(erreur)


def lire_liste(tous=False):
    global _derniers
    try:
        boite = _connexion()
        try:
            numeros = _non_lus(boite)
            debut = ""
            if not numeros or tous:
                numeros = _recents(boite)
                debut = ("Tu n'as pas de nouveau mail. Voici les derniers reçus. " if not tous else
                         "Voici tes derniers mails. ")
                if not numeros:
                    return "Ta boîte de réception est vide."
            _derniers = numeros[:NB_LUS]
            phrases = []
            for i, n in enumerate(_derniers):
                nom, objet = _entetes(boite, n)
                phrases.append(f"{_RANGS[i].capitalize()} : {nom}, objet : {objet}.")
            plus = len(numeros) - len(_derniers) if not debut else 0
            fin = f" Et {plus} autre{'s' if plus > 1 else ''}." if plus > 0 else ""
            return (debut + " ".join(phrases) + fin + " Pour en écouter un, dis par exemple : lis-moi le premier mail.")
        finally:
            boite.logout()
    except Exception as erreur:
        if not isinstance(erreur, LookupError):
            print("Mails :", erreur)
        return _erreur(erreur)


def lire_un(rang, tous=False):
    global _derniers
    try:
        boite = _connexion()
        try:
            if tous:                                   # « le dernier mail » : le plus récent, lu ou non
                _derniers = _recents(boite)
            elif not _derniers:
                _derniers = _non_lus(boite)[:NB_LUS] or _recents(boite)
            if rang >= len(_derniers):
                return "Je ne trouve pas ce mail parmi les derniers reçus."
            statut, donnees = boite.fetch(_derniers[rang], "(BODY.PEEK[])")
            brut = next((d[1] for d in donnees if isinstance(d, tuple)), b"")
            message = email.message_from_bytes(brut)
            texte = " ".join(_texte(message).split())
            texte = re.sub(r"https?://\S+", "", texte)           # les liens ne se lisent pas à voix haute
            if len(texte) > LONGUEUR_LECTURE:
                texte = texte[:LONGUEUR_LECTURE].rsplit(" ", 1)[0] + "… La suite est dans ta messagerie."
            nom, objet = _expediteur(message.get("From")), _decoder(message.get("Subject")) or "sans objet"
            return f"Mail de {nom}, objet : {objet}. {texte or 'Ce mail ne contient pas de texte.'}"
        finally:
            boite.logout()
    except Exception as erreur:
        if not isinstance(erreur, LookupError):
            print("Mails :", erreur)
        return _erreur(erreur)


_RANGS = ["premier", "deuxième", "troisième", "quatrième", "cinquième"]
_RANG = {"premier": 0, "1er": 0, "dernier": 0, "deuxième": 1, "second": 1, "2e": 1, "troisième": 2, "3e": 2,
         "quatrième": 3, "4e": 3, "cinquième": 4, "5e": 4}
_MAIL = r"(?:e-?mails?|mails?|mèles?|messages? (?:électroniques?|reçus?)|courriels?|courriers?)"


def commande(t, enfant=False):
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    # « Li-moi », « Limois », « lit moi » : « lis-moi » mal entendu
    t = re.sub(r"\b(?:li|lit|lis|lie)[- ]?mois?\b|\blimois?\b", "lis-moi", t)
    t = re.sub(r"^moi\b", "lis-moi", t)
    if not re.search(r"\b" + _MAIL + r"\b", t) or re.search(r"\b(?:envoie|envoyer|écris|écrire|réponds|répondre|"
                                                            r"supprime|efface)\b", t):
        return None
    if enfant:
        return "Les mails, c'est réservé aux parents."
    m = re.search(r"\b(?:lis|lit|lire|ouvre)(?:-moi)? (?:le |la |mon )?(premier|1er|dernier|deuxième|second|2e|"
                  r"troisième|3e|quatrième|4e|cinquième|5e)\b", t)
    if m:
        return lire_un(_RANG[m.group(1)], tous=m.group(1) == "dernier")
    if re.search(r"\b(?:lis|lit|lire|ouvre)(?:-moi)? (?:un|le|mon) " + _MAIL + r"\b", t) or \
            re.search(r"\b(?:dernier|plus récent) " + _MAIL, t):
        return lire_un(0, tous=True)              # « lis-moi un mail » : le plus récent, lu ou non
    if re.search(r"\b(?:derniers|tous mes|tous les)\b", t):
        return lire_liste(tous=True)
    if re.search(r"\b(?:lis|lit|lire|liste|quels? sont|c'est quoi)(?:-moi)?\b", t):
        return lire_liste()
    if re.search(r"\b(?:nouveaux?|nouvelles?|non lus?|reçu|j'ai des|ai-je des|combien|des mails|mes mails)\b", t):
        return nouveaux()
    return None



# ---------- Marquer comme lus : toujours après un « oui » ----------
#
#   « Jarvis, marque tous mes mails comme lus »
# Seul changement fait dans la boîte : le drapeau « lu » sur les mails non lus de la boîte de réception.
# Rien n'est supprimé ni déplacé. Si la messagerie refuse la modification : « Je ne sais pas faire ça. »

_MARQUER = re.compile(r"\b(?:marque|marques|marquer|mark|marc|mets|met|mettre|passe|passer|coche|cocher|considère)\b"
                      r".*\b" + _MAIL + r"\b.*\b(?:comme|en)\s+(?:lus?|lue?s?|lui)\b")
_MARQUER_TOUT = re.compile(r"\b(?:marque|marquer|mark|marc|mets|met|mettre|passe|passer)\b.*\btout\b.*\bcomme\s+(?:lus?|lue?s?)\b")
_MARQUER_APRES = re.compile(r"\b(?:marque|marques|marquer|mark|marc|mets|met|mettre|passe|passer)\b.*\b(?:comme|en)\s+(?:lus?|lue?s?|lui)\b.*\b" + _MAIL + r"\b")
NE_SAIT_PAS = "Je ne sais pas faire ça."
_TRANCHE = 400


def _compter_non_lus():
    boite = _connexion()
    try:
        return len(_non_lus(boite))
    finally:
        try:
            boite.logout()
        except Exception:
            pass


def marquer_lus():
    """Marque comme lus tous les mails non lus de la boîte de réception. Renvoie la phrase à dire."""
    try:
        boite = _connexion(ecriture=True)
    except PermissionError:
        return NE_SAIT_PAS
    except Exception as erreur:
        if not isinstance(erreur, LookupError):
            print("Mails :", erreur)
        return _erreur(erreur)
    try:
        numeros = _non_lus(boite)
        if not numeros:
            return "Tu n'as aucun mail non lu."
        try:
            for i in range(0, len(numeros), _TRANCHE):
                statut = boite.store(b",".join(numeros[i:i + _TRANCHE]), "+FLAGS", "\\Seen")[0]
                if statut != "OK":
                    return NE_SAIT_PAS
            reste = len(_non_lus(boite))
        except Exception as erreur:
            print("Mails (marquer comme lus) :", erreur)
            return NE_SAIT_PAS
        fait = len(numeros) - reste
        if fait <= 0:
            return NE_SAIT_PAS
        pluriel = "s" if fait > 1 else ""
        if reste:
            return f"J'ai marqué {fait} mail{pluriel} comme lu{pluriel}. Il en reste {reste} que je n'ai pas réussi à marquer."
        return f"C'est fait, {fait} mail{pluriel} marqué{pluriel} comme lu{pluriel}."
    finally:
        try:
            boite.logout()
        except Exception:
            pass


def commande_marquer_lus(t, confirmer, enfant=False, invite=False):
    """« marque tous mes mails comme lus » : compte, demande « oui », puis marque."""
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.lower().replace("’", "'")).strip(" .!?")
    if not (_MARQUER.search(t) or _MARQUER_APRES.search(t) or (_MARQUER_TOUT.search(t) and re.search(r"\b" + _MAIL + r"\b", t))):
        return None
    if re.search(r"\b(?:envoie|envoyer|supprime|efface|lis|lit|lire|ouvre)\b", t):
        return None
    if enfant:
        return "Les mails, c'est réservé aux parents."
    if invite:
        return "En mode invité, je ne touche pas aux mails."
    try:
        total = _compter_non_lus()
    except Exception as erreur:
        if not isinstance(erreur, LookupError):
            print("Mails :", erreur)
        return _erreur(erreur)
    if not total:
        return "Tu n'as aucun mail non lu."
    confirmer(marquer_lus)
    quoi = "1 mail" if total == 1 else f"{total} mails"
    return f"Je vais marquer {quoi} comme lu{'s' if total > 1 else ''}. Je ne supprime rien. Je le fais ? Dis oui pour confirmer."


# ---------- Envoi : toujours relu et confirmé par un « oui » ----------
#
#   « Jarvis, envoie un mail à Marie pour lui dire que je serai en retard »
#   « Jarvis, écris un mail à Marie : on mange à 20 heures »
#   « Jarvis, envoie-moi un mail pour me rappeler d'appeler le garage »
# Le destinataire est cherché parmi les personnes à qui tu as déjà écrit (dossier « Envoyés » de ta
# messagerie, relu au plus une fois par heure). Rien n'est écrit dans un fichier. Jarvis lit le mail et
# l'affiche ; il ne part qu'après « oui ». Refusé en mode enfant et en mode invité.

import smtplib
import time
import unicodedata
import difflib
import email.message

_ENVOI = re.compile(r"^(?:envoie|envoies|envoyer|envoi|écris|écrire|écrit|rédige|fais)(?P<moi>[- ]moi)?\s+"
                    r"(?:un |une )?(?:petit |court )?" + _MAIL + r"(?:\s+(?:à|a|au|aux|pour(?!\s+(?:me|ne|lui|leur|dire|demander|rappeler|prévenir|penser)\b))\s+(?P<reste>.+)|\s+(?P<reste_moi>"
                    r"(?:pour|pommes?|qui|en|disant|:).+))?$")
_COUPURE = re.compile(r"\s*(?:,|:)\s*(?:pour\s+)?|\s+(?:(?:pour|pommes?)\s+(?:me\s+)?(?:faire\s+)?penser\s+(?:à|a)|"
                      r"(?:pour|pommes?)\s+ne\s+pas\s+oublier(?:\s+de)?|"
                      r"(?:pour|pommes?)\s+(?:lui|leur|me)\s+(?:dire|demander|rappeler|"
                      r"prévenir|annoncer|souhaiter)|pour\s+(?:dire|demander|rappeler|prévenir|souhaiter)|"
                      r"et\s+(?:dis|demande|rappelle)[- ](?:lui|leur)|qui\s+dit|en\s+(?:lui\s+)?disant|disant)\s+")
_contacts = {"quand": 0.0, "liste": []}
_envoi_attente = {}            # pour les essais : le dernier mail préparé


def _smtp():
    """Les réglages d'envoi à essayer, dans l'ordre : [(serveur, port, « starttls » ou « ssl »)]."""
    r = reglages_pour(None, SERVEUR) if SERVEUR else reglages()
    return [(r["smtp"], port, mode) for port, mode in r["envoi"]]


def _ouvrir_smtp(ident, essais=None, delai=20):
    """Connexion au serveur d'envoi, identifiée. Si le premier réglage ne répond pas (port fermé chez certains
    fournisseurs ou sur certaines box), le suivant est essayé. Un mot de passe refusé arrête tout de suite."""
    derniere = None
    for hote, port, mode in (essais or _smtp()):
        serveur = None
        try:
            if mode == "ssl":
                serveur = smtplib.SMTP_SSL(hote, port, timeout=delai)
            else:
                serveur = smtplib.SMTP(hote, port, timeout=delai)
                serveur.starttls()
            serveur.login(*ident)
            return serveur
        except smtplib.SMTPAuthenticationError:
            _fermer(serveur)
            raise
        except (OSError, smtplib.SMTPException) as erreur:
            derniere = erreur
            _fermer(serveur)
    raise derniere or OSError("aucun serveur d'envoi")


def _fermer(serveur):
    try:
        if serveur is not None:
            serveur.quit()
    except Exception:
        try:
            serveur.close()
        except Exception:
            pass


def _deja_range(boite, dossier, identifiant_message):
    """Vrai si la messagerie a déjà rangé elle-même ce mail dans « Envoyés » (Gmail le fait)."""
    for essai in range(2):
        try:
            if boite.select('"' + dossier + '"', readonly=True)[0] == "OK":
                statut, donnees = boite.search(None, "HEADER", "Message-ID", '"' + identifiant_message.strip() + '"')
                if statut == "OK" and donnees and donnees[0] and donnees[0].split():
                    return True
        except Exception:
            return False
        if essai == 0:
            time.sleep(2)
    return False


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _dossier_envoyes(boite):
    statut, lignes = boite.list()
    for ligne in lignes or []:
        texte = ligne.decode("utf-8", "replace") if isinstance(ligne, bytes) else str(ligne)
        if "\\Sent" in texte:
            return texte.rsplit(' "', 1)[-1].strip('"') if texte.endswith('"') else texte.split()[-1]
    for nom in ("Sent Messages", "Sent", "Envoyés", "[Gmail]/Messages envoyés", "[Gmail]/Sent Mail"):
        if boite.select('"' + nom + '"', readonly=True)[0] == "OK":
            return nom
    return None


def contacts(forcer=False):
    """[(nom, adresse, poids)] : les personnes à qui tu as écrit (500 derniers mails envoyés), plus les
    fiches Contacts iCloud qui ont une adresse mail. Gardé en mémoire une heure, jamais écrit dans un fichier."""
    _bon_compte()
    if not forcer and _contacts["liste"] and time.time() - _contacts["quand"] < 3600:
        return _contacts["liste"]
    ident = identifiants(cible())
    if not ident or not ident[0] or not ident[1]:
        raise LookupError
    compte = {}
    boite = imaplib.IMAP4_SSL(_serveur(), 993, timeout=20)
    try:
        boite.login(*ident)
        dossier = _dossier_envoyes(boite)
        numeros = []
        if dossier and boite.select('"' + dossier + '"', readonly=True)[0] == "OK":
            statut, donnees = boite.search(None, "ALL")
            numeros = donnees[0].split() if statut == "OK" and donnees and donnees[0] else []
        numeros = numeros[-500:]
        if numeros:
            statut, donnees = boite.fetch(numeros[0] + b":" + numeros[-1], "(BODY.PEEK[HEADER.FIELDS (TO CC)])")
            for d in donnees or []:
                if not isinstance(d, tuple):
                    continue
                m = email.message_from_bytes(d[1])
                for nom, adresse in email.utils.getaddresses([_decoder(m.get("To")), _decoder(m.get("Cc"))]):
                    adresse = adresse.strip().lower()
                    if "@" not in adresse or adresse == ident[0].lower():
                        continue
                    ancien = compte.get(adresse, ("", 0))
                    compte[adresse] = (nom.strip('" ') or ancien[0], ancien[1] + 1)
    finally:
        try:
            boite.logout()
        except Exception:
            pass
    # + les fiches Contacts de l'iPhone qui ont une adresse mail (iCloud, même mot de passe pour app)
    try:
        for nom, adresse in _contacts_icloud(*ident):
            if adresse != ident[0].lower():
                ancien = compte.get(adresse, ("", 0))
                compte[adresse] = (ancien[0] or nom, ancien[1] + 1)
    except Exception as erreur:
        print("Contacts iCloud :", erreur)
    liste = sorted(((nom, adr, n) for adr, (nom, n) in compte.items()), key=lambda x: -x[2])
    _contacts.update(quand=time.time(), liste=liste)
    return liste


def _contacts_icloud(identifiant, mot_de_passe):
    """[(nom, adresse)] des contacts iCloud (CardDAV), seulement si la messagerie est iCloud."""
    if "me.com" not in _serveur() and "icloud" not in _serveur():
        return []
    import base64
    import urllib.request
    auth = "Basic " + base64.b64encode(f"{identifiant}:{mot_de_passe}".encode()).decode()

    def dav(url, methode, corps, profondeur="0"):
        req = urllib.request.Request(url, data=corps.encode(), method=methode, headers={
            "Authorization": auth, "Depth": profondeur, "Content-Type": "application/xml; charset=utf-8"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")

    url, x = dav("https://contacts.icloud.com/", "PROPFIND",
                 '<d:propfind xmlns:d="DAV:"><d:prop><d:current-user-principal/></d:prop></d:propfind>')
    base = re.match(r"https://[^/]+", url).group(0)
    principal = re.search(r"current-user-principal[^>]*>\s*<[^>]*href[^>]*>([^<]+)<", x).group(1)
    _, x = dav(base + principal, "PROPFIND", '<d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
                                             '<d:prop><c:addressbook-home-set/></d:prop></d:propfind>')
    home = re.search(r"addressbook-home-set[^>]*>\s*<[^>]*href[^>]*>([^<]+)<", x).group(1)
    if home.startswith("/"):
        home = base + home
    hote = re.match(r"https://[^/]+", home).group(0)
    _, x = dav(home, "PROPFIND", '<d:propfind xmlns:d="DAV:"><d:prop><d:resourcetype/></d:prop></d:propfind>', "1")
    trouves = []
    for c in re.findall(r"<[^>]*href[^>]*>([^<]+)</[^>]*href>", x):
        if not c.rstrip("/").endswith("card"):
            continue
        _, x = dav(c if c.startswith("http") else hote + c, "REPORT",
                   '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
                   '<d:prop><c:address-data/></d:prop></c:addressbook-query>', "1")
        x = html.unescape(re.sub(r"\r?\n[ \t]", "", x))          # lignes repliées des vCard recollées
        for carte in x.split("BEGIN:VCARD")[1:]:
            fn = re.search(r"(?im)^FN[^:\n]*:(.*)$", carte)
            nom = fn.group(1).strip().replace("\\,", ",") if fn else ""
            for adr in re.findall(r"(?im)^(?:item\d+\.)?EMAIL[^:\n]*:\s*(\S+@\S+?)\s*$", carte):
                trouves.append((nom, adr.lower()))
    return trouves


def _mots(t):
    return [m for m in re.findall(r"[a-z0-9]+", _sans_accents(t)) if len(m) > 1]


def trouver(nom, liste):
    """Les contacts qui correspondent au nom dit (prénom, nom, ou les deux), du plus écrit au moins écrit."""
    dits = [m for m in _mots(nom) if m not in ("mon", "ma", "mes", "de", "du", "la", "le")]
    if not dits:
        return []
    trouves = []
    for contact in liste:
        siens = _mots(contact[0]) + _mots(contact[1].split("@")[0].replace(".", " ").replace("_", " "))
        if all(any(m == s or (len(m) > 3 and difflib.SequenceMatcher(None, m, s).ratio() >= 0.8) for s in siens)
               for m in dits):
            trouves.append(contact)
    return trouves


def _nom_dit(contact):
    nom = contact[0] or contact[1].split("@")[0].replace(".", " ").title()
    # émojis et symboles des fiches Contacts (« Marie ❤️ ») : ni lus, ni affichés
    nom = "".join(c for c in nom if unicodedata.category(c)[0] in "LNZ" or c in "-'.")
    return re.sub(r"\s+", " ", nom).strip() or contact[1].split("@")[0]


def _message_propre(message):
    message = message.strip(" .,:;")
    message = re.sub(r"^(?:que|qu')\s*", "", message, flags=re.I)
    if re.match(r"(?i)s'ils?\b", message):                  # « s'il vient samedi » -> « Est-ce qu'il vient samedi ? »
        message = "Est-ce qu'" + message[2:].strip() + " ?"
    elif re.match(r"(?i)si\s", message):                    # « si tu viens » -> « Est-ce que tu viens ? »
        reste = message[3:].strip()
        message = ("Est-ce qu'" if re.match(r"(?i)[aeiouyéèêàâîôûh]", reste) else "Est-ce que ") + reste + " ?"
    if message and message[-1] not in ".!?":
        message += "."
    return message[:1].upper() + message[1:]


def envoyer(adresse, nom, sujet, corps):
    """Envoie vraiment le mail (après le « oui »), et en garde une copie dans « Envoyés »."""
    ident = identifiants(cible())
    if not ident or not ident[0] or not ident[1]:
        return _erreur(LookupError())
    mail = email.message.EmailMessage()
    mail["From"] = email.utils.formataddr((jarvis_config.PRENOM or "", ident[0]))
    mail["To"] = email.utils.formataddr((nom if nom != "toi" else "", adresse))
    mail["Subject"] = sujet
    mail["Date"] = email.utils.formatdate(localtime=True)
    mail["Message-ID"] = email.utils.make_msgid()
    mail.set_content(corps)
    try:
        serveur = _ouvrir_smtp(ident)
        try:
            serveur.send_message(mail)
        finally:
            _fermer(serveur)
    except smtplib.SMTPAuthenticationError:
        return ("Ta messagerie a refusé l'envoi : le mot de passe est peut-être faux ou expiré. Le mail n'est pas "
                "parti. Dis « relie mes mails » pour le remettre.")
    except Exception as erreur:
        print("Envoi du mail :", erreur)
        return "Je n'ai pas réussi à envoyer le mail. Il n'est pas parti."
    try:                                                    # copie dans « Envoyés » (iCloud ne le fait pas seul)
        boite = imaplib.IMAP4_SSL(_serveur(), 993, timeout=15)
        boite.login(*ident)
        dossier = _dossier_envoyes(boite)
        if dossier and (reglages().get("copie") or not _deja_range(boite, dossier, mail["Message-ID"])):
            boite.append('"' + dossier + '"', "(\\Seen)", imaplib.Time2Internaldate(time.time()), mail.as_bytes())
        boite.logout()
    except Exception as erreur:
        print("Copie dans Envoyés :", erreur)
    return f"C'est envoyé à {nom}." if nom != "toi" else "C'est envoyé, tu le trouveras dans ta boîte mail."


def commande_envoi(t, brut, confirmer, enfant=False, invite=False):
    """« envoie un mail à Marie pour lui dire … » : prépare, lit et affiche le mail, puis attend « oui »."""
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")
    m = _ENVOI.match(t)
    if not m:
        return None
    if enfant:
        return "Envoyer des mails, c'est réservé aux parents."
    if invite:
        return "En mode invité, je n'envoie pas de mail."
    pour_moi = bool(m.group("moi"))
    reste = " " + (m.group("reste") or m.group("reste_moi") or "")
    # même découpage sur la phrase d'origine (majuscules, ponctuation de Whisper)
    brut = re.sub(r"^\W*(?:jarvis\W+)?", "", brut.replace("’", "'"), flags=re.I).strip()
    coupe = _COUPURE.search(reste)
    if not coupe:
        if pour_moi or re.fullmatch(r"\W*moi\W*", reste):
            return "Que veux-tu que je mette dans le mail ? Redis-moi tout d'une traite, par exemple : envoie-moi un mail pour me rappeler d'appeler le garage."
        return ("Que veux-tu que je lui écrive ? Redis-moi tout d'une traite, par exemple : envoie un mail à Marie "
                "pour lui dire que je serai en retard.")
    qui = reste[:coupe.start()].strip()
    debut_message = coupe.group(0).strip().lower()
    # le message pris dans la phrase d'origine, à la même place (ses majuscules et sa ponctuation)
    message = reste[coupe.end():]
    position = brut.lower().replace("’", "'").rfind(message[:25]) if message else -1
    if position >= 0:
        message = brut[position:]
    if pour_moi and re.search(r"rappel|penser|oublier", coupe.group(0)):   # « pour me rappeler d'appeler le garage »
        message = re.sub(r"(?i)^\s*(?:de\s+|d')", "", message)
        message = "Penser à " + message if message else message
    elif re.search(r"dire|rappel", coupe.group(0)) and re.match(r"(?i)\s*(?:de\s+|d')", message):
        # « pour lui dire d'acheter du pain » -> « Pense à acheter du pain. »
        message = "Pense à " + re.sub(r"(?i)^\s*(?:de\s+|d')", "", message)
    message = _message_propre(message)
    if len(message) < 3:
        return "Je n'ai pas compris le message à envoyer. Redis-moi tout d'une traite."
    demande = "demand" in debut_message
    try:
        if re.fullmatch(r"(?:à\s+)?moi(?:[- ]même)?", qui) or pour_moi:
            ident = identifiants(cible())
            if not ident or not ident[0]:
                raise LookupError
            adresse, nom = ident[0], "toi"
        else:
            trouves = trouver(qui, contacts())
            if not trouves and time.time() - _contacts["quand"] > 60:   # fiche ajoutée entre-temps sur l'iPhone ?
                trouves = trouver(qui, contacts(forcer=True))
            adresses = []
            for c in trouves:
                if c[1] not in [a[1] for a in adresses]:
                    adresses.append(c)
            if not adresses:
                return (f"Je ne trouve pas d'adresse mail pour {qui.title()}, ni dans tes contacts ni parmi les "
                        "personnes à qui tu as déjà écrit. Ajoute son adresse mail dans sa fiche Contacts sur ton "
                        "iPhone, puis redemande-moi.")
            if len(adresses) > 1 and adresses[0][2] < 3 * adresses[1][2]:
                noms = " ; ".join(f"{_nom_dit(c)}, {c[1].split('@')[0]}" for c in adresses[:3])
                return f"J'ai plusieurs {qui.title()} : {noms}. Redis-moi la demande avec le nom de famille."
            adresse, nom = adresses[0][1], _nom_dit(adresses[0])
    except Exception as erreur:
        if not isinstance(erreur, LookupError):
            print("Mails (contacts) :", erreur)
        return _erreur(erreur)
    if demande and not message.endswith("?"):
        message = message.rstrip(".") + " ?"
    prenom = jarvis_config.PRENOM
    sujet = ("Rappel" if nom == "toi" else (f"Message de {prenom}" if prenom else "Message"))
    corps = (message + "\n") if nom == "toi" else (f"Bonjour,\n\n{message}\n\n{prenom}\n" if prenom else
                                                   f"Bonjour,\n\n{message}\n")
    _envoi_attente.update(adresse=adresse, nom=nom, sujet=sujet, corps=corps)
    try:
        import jarvis_voix
        if jarvis_voix.afficher:
            jarvis_voix.afficher(f"Mail à {nom if nom != 'toi' else 'toi'} ({adresse}) : {message}")
    except Exception as erreur:
        print("Affichage :", erreur)
    confirmer(lambda: envoyer(adresse, nom, sujet, corps))
    debut = "Je vais t'envoyer ce mail" if nom == "toi" else f"Je vais envoyer à {nom}"
    return f"{debut} : « {message} » Je l'envoie ? Dis oui pour confirmer."
