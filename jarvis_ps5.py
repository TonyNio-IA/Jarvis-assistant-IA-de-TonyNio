# -*- coding: utf-8 -*-
"""
JARVIS - les PlayStation 5 de la maison : sont-elles allumées, en veille ou éteintes ?

  « Jarvis, est-ce que la PS5 est allumée ? », « la PlayStation est en veille ? »
  « est-ce que la PS5 de Léo est allumée ? » (s'il y en a plusieurs : le mot dit est cherché dans le nom de la console)

  « Jarvis, allume la PS5 » (elle doit être en mode repos), « mets la PS5 en veille » (Jarvis demande confirmation)

Pour allumer ou mettre en veille, la console doit avoir été reliée une fois : « Jarvis, relie la PS5 » ouvre
jarvis_associer_ps5.py (connexion à ton compte PlayStation dans le navigateur, puis code affiché par la console).
Module pyremoteplay (licence MIT). Ce qui permet de reconnaître Jarvis reste dans ton dossier personnel (.pyremoteplay), jamais publié.

Pour l'état, lecture seule : Jarvis pose à chaque console la question « es-tu là ? » du protocole de découverte de Sony (celui de
l'application PS Remote Play). Rien n'est modifié sur la console, aucun compte ni mot de passe n'est nécessaire.
Les consoles sont trouvées par la Freebox (leurs noms restent sur ce PC), sinon par un appel sur le réseau local.
"""
import os
import re
import socket
import time

_PS5 = re.compile(r"\b(?:ps ?5|ps ?cinq|p s 5|playstation(?: ?5| cinq)?|play ?station(?: ?5| cinq)?|pé ?s ?5)\b")
_QUESTION = re.compile(r"\b(?:allum[ée]e?s?|[ée]teinte?s?|en veille|en marche|marche|tourne|[ée]tat|est-ce que|est-ce qu'|"
                       r"qui joue|on joue|quelqu'un joue|joue encore|toujours)\b")
_ORDRE = re.compile(r"\b(?:allume|allumer|[ée]teins|[ée]teindre|lance|lancer|mets|ouvre|d[ée]marre|coupe)\b")
_PAS_UN_NOM = {"ps5", "ps", "pro", "playstation", "play", "station", "slim", "sony", "console", "digital"}
_memo = {"quand": 0.0, "liste": []}
_derniere_ip = {}               # nom -> dernière adresse connue (une console en mode repos peut sembler absente)


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t.lower()


def _consoles():
    """[(nom, ip ou None)] des PlayStation connues de la Freebox (gardé 2 minutes)."""
    if _memo["liste"] and time.time() - _memo["quand"] < 120:
        return _memo["liste"]
    liste = []
    try:
        import jarvis_freebox
        for h in jarvis_freebox._lire("lan/browser/pub/") or []:
            nom = (h.get("primary_name") or "").strip()
            if h.get("host_type") != "vg_console" and not re.search(r"ps5|playstation", nom, re.I):
                continue
            if "sony" not in (h.get("vendor_name") or "").lower() and not re.search(r"ps5|playstation", nom, re.I):
                continue
            ips = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4" and c.get("active")]
            connues = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4"]
            if ips or connues:
                _derniere_ip[nom] = (ips or connues)[0]
            liste.append((nom, ips[0] if ips and h.get("active") else None))
    except Exception as erreur:
        print("PS5 (Freebox) :", type(erreur).__name__, erreur)
    _memo.update(quand=time.time(), liste=liste)
    return liste


def _demander(ip, attente=1.5):
    """État d'une console : « allumee », « veille » ou None (pas de réponse), et ses renseignements."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(attente)
    try:
        if ip == "255.255.255.255":
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00030010\n", (ip, 9302))
        donnees, _ = s.recvfrom(2048)
    except OSError:
        return None, {}
    finally:
        s.close()
    lignes = donnees.decode("utf-8", "replace").split("\n")
    infos = dict(l.split(":", 1) for l in lignes[1:] if ":" in l)
    code = lignes[0].split()[1] if len(lignes[0].split()) > 1 else ""
    return ("allumee" if code == "200" else "veille" if code == "620" else None), infos


def _nom_dit(nom):
    """« PS5-Pro-Léo » -> « de Léo » (ce qui distingue la console), ou « » s'il n'y a rien d'autre dans son nom."""
    mots = [m for m in re.split(r"[^0-9A-Za-zÀ-ÿ]+", nom) if m and _sans_accents(m) not in _PAS_UN_NOM
            and not re.fullmatch(r"[\d.]+", m)]
    if not mots:
        return ""
    reste = " ".join(m.capitalize() for m in mots)
    return ("d'" if _sans_accents(reste[0]) in "aeiouyh" else "de ") + reste


def _phrase(nom, etat, infos, seule):
    qui = "La PS5" + ("" if seule or not _nom_dit(nom) else " " + _nom_dit(nom))
    if etat == "allumee":
        jeu = (infos.get("running-app-name") or "").strip()
        return f"{qui} est allumée" + (f", sur {jeu}." if jeu else ".")
    if etat == "veille":
        return f"{qui} est en veille."
    return f"{qui} est éteinte."


def etats():
    """[(nom, état, renseignements)] de toutes les consoles."""
    consoles = _consoles()
    if not consoles:                                   # sans Freebox : un appel à toutes les consoles du réseau
        etat, infos = _demander("255.255.255.255", 2.0)
        return [(infos.get("host-name", "PS5").strip(), etat, infos)] if etat else []
    resultat = []
    for nom, ip in consoles:
        ip = ip or _derniere_ip.get(nom)               # en mode repos, la Freebox peut la croire absente
        etat, infos = (None, {})
        for _ in range(3 if ip else 0):                # une réponse peut se perdre (surtout en mode repos)
            etat, infos = _demander(ip)
            if etat:
                break
        resultat.append((nom, etat, infos))
    return resultat


# ---------- Allumer, mettre en veille (consoles reliées avec jarvis_associer_ps5.py) ----------

_RELIER = re.compile(r"\b(?:relie|relier|associe|associer|connecte|appaire|jumelle)\b")
_ALLUMER = re.compile(r"\b(?:allume|allumer|r[ée]veille|r[ée]veiller|d[ée]marre|d[ée]marrer|rallume)\b")
_VEILLE = re.compile(r"\b(?:[ée]teins|[ée]teindre|coupe|arr[êe]te)\b|\b(?:mets|met|passe)\b.{0,25}\b(?:veille|repos)\b")


def preparer_netifaces():
    """pyremoteplay a besoin du module « netifaces », qui ne s'installe pas sur Windows avec Python 3.14 (il faudrait
    le compiler). Jarvis fournit à la place ce dont pyremoteplay se sert (liste des cartes réseau et de leurs
    adresses IPv4), à partir de psutil. À appeler avant tout import de pyremoteplay."""
    import sys
    if "netifaces" in sys.modules:
        return
    try:
        import netifaces                                  # noqa: F401  (le vrai module, s'il est là)
        return
    except ImportError:
        pass
    import types
    import psutil
    module = types.ModuleType("netifaces")
    module.AF_INET = socket.AF_INET

    def interfaces():
        return list(psutil.net_if_addrs())

    def ifaddresses(interface):
        resultat = {}
        for a in psutil.net_if_addrs().get(interface, []):
            if a.family == socket.AF_INET:
                resultat.setdefault(socket.AF_INET, []).append(
                    {"addr": a.address, "netmask": a.netmask, "broadcast": a.broadcast})
        return resultat
    module.interfaces, module.ifaddresses = interfaces, ifaddresses
    sys.modules["netifaces"] = module


def pilotage_disponible():
    """Vrai si l'allumage et la mise en veille sont possibles (module pyremoteplay installé et chargeable)."""
    try:
        preparer_netifaces()
        import pyremoteplay                               # noqa: F401
        return True
    except Exception as erreur:
        print("PS5 (module de pilotage) :", type(erreur).__name__, erreur)
        return False


def profils():
    """Les comptes et consoles reliés. Le module les range dans le dossier personnel de l'utilisateur
    (.pyremoteplay), hors du dossier de Jarvis : ils ne sont donc jamais publiés."""
    preparer_netifaces()
    from pyremoteplay.profile import Profiles
    return Profiles.load()


def _appareil(ip):
    """(console, utilisateur relié) ou (console, None) si elle n'a pas été reliée."""
    preparer_netifaces()
    from pyremoteplay import RPDevice
    console = RPDevice(ip)
    for _ in range(4):                                 # en mode repos, la console ne répond pas à chaque fois
        if console.get_status():
            break
    p = profils()
    relies = console.get_users(p) if console.status else []
    return console, (relies[0] if relies else None), p


def _pas_reliee(qui):
    return (f"{qui} n'est pas encore reliée à Jarvis. Dis-moi : relie la PS5, puis suis les indications "
            "de la fenêtre.")


def allumer(nom, ip, seule=True):
    qui = "La PS5" + ("" if seule or not _nom_dit(nom) else " " + _nom_dit(nom))
    ip = ip or _derniere_ip.get(nom)
    if not ip:
        return f"{qui} est éteinte ou introuvable : je ne peux la rallumer que si elle est en mode repos."
    console, utilisateur, p = _appareil(ip)
    if console.is_on:
        return f"{qui} est déjà allumée."
    if not console.status:
        return f"{qui} ne répond pas : je ne peux la rallumer que si elle est en mode repos."
    if not utilisateur:
        return _pas_reliee(qui)
    console.wakeup(utilisateur, p)
    return f"J'allume {qui[0].lower() + qui[1:]}."


def mettre_en_veille(nom, ip, seule=True):
    import asyncio
    qui = "La PS5" + ("" if seule or not _nom_dit(nom) else " " + _nom_dit(nom))
    console, utilisateur, p = _appareil(ip)
    if not console.is_on:
        return f"{qui} n'est pas allumée."
    if not utilisateur:
        return _pas_reliee(qui)

    async def faire():
        try:
            return await asyncio.wait_for(console.standby(utilisateur, p), timeout=30)
        finally:
            console.disconnect()

    try:
        ok = asyncio.run(faire())
    except Exception as erreur:
        print("PS5 (veille) :", type(erreur).__name__, erreur)
        ok = False
    for _ in range(8):                                 # le module dit parfois « raté » alors que la console s'endort bien
        if ok:
            break
        time.sleep(1.5)
        ok = _demander(ip)[0] == "veille"
    return f"{qui} passe en veille." if ok else f"Je n'ai pas réussi à mettre {qui[0].lower() + qui[1:]} en veille."


def _citees(t, liste):
    dits = re.findall(r"[a-z0-9]+", _sans_accents(t))
    return [c for c in liste if any(len(m) >= 3 and _sans_accents(m) in dits
                                    for m in re.sub(r"^d(?:e |')", "", _nom_dit(c[0])).split())]


def _commande_action(t, confirmer, enfant):
    """« relie la PS5 », « allume la PS5 », « mets la PS5 en veille ». None si ce n'est pas un ordre."""
    if re.search(r"\best-ce qu|\bjeu\b|\bjeux\b|\bsur la (?:ps|play)", t):
        return None
    relier, allume, veille = _RELIER.search(t), _ALLUMER.search(t), _VEILLE.search(t)
    if not (relier or allume or veille):
        return None
    if enfant:
        return "Ça, c'est pour les parents."
    if not pilotage_disponible():
        # le module de pilotage n'a pas pu être installé : seule la lecture de l'état reste possible
        return ("Pour allumer la PS5 ou la mettre en veille, il me manque un module. Pour le réinstaller, relance "
                "l'installateur de Jarvis et choisis 1, mettre à jour ou réparer. En attendant, je peux te dire si elle "
                "est allumée : demande-moi, est-ce que la PS5 est allumée.")
    if relier:
        try:
            import jarvis_tele
            jarvis_tele._lancer_outil("jarvis_associer_ps5.py")
        except Exception as erreur:
            print("PS5 (outil) :", erreur)
            return "Je n'arrive pas à ouvrir la fenêtre pour relier la PS5."
        return ("J'ouvre la fenêtre pour relier la PS5. Tu vas te connecter à ton compte PlayStation, puis taper "
                "le code affiché par la console.")
    consoles = _consoles()
    if not consoles:
        return "Je ne trouve aucune PS5 sur le réseau de la maison."
    choisies = _citees(t, consoles)
    if not choisies and len(consoles) > 1:
        noms = " ou ".join("celle " + _nom_dit(c[0]) for c in consoles if _nom_dit(c[0]))
        return f"Laquelle : {noms} ? Redis-moi la demande avec son nom."
    nom, ip = (choisies or consoles)[0]
    seule = len(consoles) == 1
    try:
        if allume:
            return allumer(nom, ip, seule)
        if not ip:
            return "La PS5" + ("" if seule else " " + _nom_dit(nom)) + " n'est pas allumée."
        if confirmer is None:
            return mettre_en_veille(nom, ip, seule)
        confirmer(lambda: mettre_en_veille(nom, ip, seule))
        qui = "la PS5" + ("" if seule else " " + _nom_dit(nom))
        return f"Tu veux que je mette {qui} en veille ? Si quelqu'un joue, sa partie s'arrête. Dis oui pour confirmer."
    except Exception as erreur:
        print("PS5 :", type(erreur).__name__, erreur)
        return "Je n'arrive pas à piloter la PS5 pour le moment."


def commande(t, confirmer=None, enfant=False):
    t = t.replace("’", "'").lower().strip(" .!?")
    if not _PS5.search(t):
        return None
    reponse = _commande_action(t, confirmer, enfant)
    if reponse:
        return reponse
    if not _QUESTION.search(t):
        return None
    if _ORDRE.search(t) and not re.search(r"\best-ce qu", t):
        return None                                    # « lance un jeu sur la PS5 » : Jarvis ne sait pas le faire
    try:
        liste = etats()
    except Exception as erreur:
        print("PS5 :", type(erreur).__name__, erreur)
        return "Je n'arrive pas à interroger la PS5 pour le moment."
    if not liste:
        return "Je ne trouve aucune PS5 sur le réseau de la maison. Elle est peut-être éteinte."
    simple = _sans_accents(t)
    dits = re.findall(r"[a-z0-9]+", simple)
    citees = [c for c in liste if any(len(m) >= 3 and _sans_accents(m) in dits
                                      for m in re.sub(r"^d(?:e |')", "", _nom_dit(c[0])).split())]
    if citees:
        liste = citees
    return " ".join(_phrase(nom, etat, infos, len(liste) == 1 and not citees) for nom, etat, infos in liste)
