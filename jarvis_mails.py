"""
JARVIS - les mails, seulement quand on les demande.

  « Jarvis, est-ce que j'ai des nouveaux mails ? »  -> le nombre de mails non lus et leurs expéditeurs
  « Jarvis, lis-moi mes mails »                      -> l'expéditeur et l'objet des 5 derniers non lus
  « Jarvis, lis-moi le premier mail »                -> le début du texte de ce mail (le 2e, le 3e...)

Jarvis ne dit jamais rien tout seul, il ne fait que lire : il n'envoie, ne supprime et ne déplace
aucun mail, et les mails lus par lui restent « non lus » dans ta messagerie.
Le contenu des mails n'est pas envoyé à Claude : il est seulement lu à voix haute.

Mise en place (une fois) : le mot de passe n'est jamais écrit dans un fichier. Il est rangé par
Windows dans le Gestionnaire d'identification, sous le nom « Jarvis-Mails ». Dans PowerShell :
    cmdkey /generic:Jarvis-Mails /user:ton.adresse@icloud.com /pass
(Windows demande alors le mot de passe, qui ne s'affiche pas). Pour iCloud, c'est un « mot de passe
pour app » créé sur account.apple.com (Connexion et sécurité > Mots de passe pour app), pas ton
mot de passe Apple. Serveur iCloud par défaut ; un autre se règle dans config.json :
    "mails": {"serveur": "imap.gmail.com"}
"""

import ctypes
import ctypes.wintypes as wt
import email
import email.header
import email.utils
import html
import imaplib
import re
import socket

import jarvis_config

CIBLE = "Jarvis-Mails"
SERVEUR = ((jarvis_config._lu.get("mails") or {}).get("serveur") if isinstance(jarvis_config._lu.get("mails"), dict)
           else None) or "imap.mail.me.com"
NB_LUS = 5
LONGUEUR_LECTURE = 900          # caractères lus d'un mail (environ une minute)

_derniers = []                  # numéros des mails annoncés, pour « lis le deuxième mail »


# ---------- Identifiants rangés par Windows (Gestionnaire d'identification) ----------

class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wt.DWORD),
                ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
                ("UserName", wt.LPWSTR)]


def identifiants():
    """(adresse, mot de passe) rangés sous « Jarvis-Mails », ou None."""
    try:
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredReadW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))]
        advapi.CredReadW.restype = wt.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        pointeur = ctypes.POINTER(_CREDENTIAL)()
        if not advapi.CredReadW(CIBLE, 1, 0, ctypes.byref(pointeur)):      # 1 = identifiant générique
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


def _connexion():
    ident = identifiants()
    if not ident or not ident[0] or not ident[1]:
        raise LookupError
    boite = imaplib.IMAP4_SSL(SERVEUR, 993, timeout=15)
    boite.login(*ident)
    boite.select("INBOX", readonly=True)          # lecture seule : rien n'est modifié, les mails restent non lus
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
        return ("Je n'ai pas encore accès à ta boîte mail. Il faut d'abord ranger ton adresse et un mot de "
                "passe pour app dans Windows, sous le nom Jarvis-Mails. C'est expliqué sur la page du projet, "
                "à la rubrique Mails.")
    if isinstance(erreur, imaplib.IMAP4.error):
        return "Ta boîte mail a refusé la connexion : le mot de passe pour app est peut-être faux ou expiré."
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
