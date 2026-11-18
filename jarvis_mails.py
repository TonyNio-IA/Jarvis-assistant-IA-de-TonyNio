"""
JARVIS - les mails, seulement quand on les demande.

  « Jarvis, est-ce que j'ai des nouveaux mails ? »  -> le nombre de mails non lus et leurs expéditeurs
  « Jarvis, lis-moi mes mails »                      -> l'expéditeur et l'objet des 5 derniers non lus
  « Jarvis, lis-moi le premier mail »                -> le début du texte de ce mail (le 2e, le 3e...)

  « Jarvis, envoie un mail à Marie pour lui dire que je serai en retard »  -> lu, affiché, puis envoyé
  « Jarvis, envoie-moi un mail pour me rappeler d'appeler le garage »         seulement après « oui »

Jarvis ne dit jamais rien tout seul. Il ne supprime et ne déplace aucun mail, et les mails lus par lui
restent « non lus » dans ta messagerie. Il n'envoie un mail que sur demande, après l'avoir lu à voix haute
et attendu ton « oui » ; le destinataire doit être dans tes contacts iCloud (avec une adresse mail) ou
quelqu'un à qui tu as déjà écrit. Refusé en mode enfant et en mode invité.
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
    hote = re.sub(r"^imap\.", "smtp.", SERVEUR)
    return hote, 587


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
    if not forcer and _contacts["liste"] and time.time() - _contacts["quand"] < 3600:
        return _contacts["liste"]
    ident = identifiants()
    if not ident or not ident[0] or not ident[1]:
        raise LookupError
    compte = {}
    boite = imaplib.IMAP4_SSL(SERVEUR, 993, timeout=20)
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
    if "me.com" not in SERVEUR and "icloud" not in SERVEUR:
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
    ident = identifiants()
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
        hote, port = _smtp()
        with smtplib.SMTP(hote, port, timeout=20) as serveur:
            serveur.starttls()
            serveur.login(*ident)
            serveur.send_message(mail)
    except smtplib.SMTPAuthenticationError:
        return "Ta messagerie a refusé l'envoi : le mot de passe pour app est peut-être faux ou expiré. Le mail n'est pas parti."
    except Exception as erreur:
        print("Envoi du mail :", erreur)
        return "Je n'ai pas réussi à envoyer le mail. Il n'est pas parti."
    try:                                                    # copie dans « Envoyés » (iCloud ne le fait pas seul)
        boite = imaplib.IMAP4_SSL(SERVEUR, 993, timeout=15)
        boite.login(*ident)
        dossier = _dossier_envoyes(boite)
        if dossier:
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
            ident = identifiants()
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
