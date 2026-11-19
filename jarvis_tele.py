"""
JARVIS - la télé, par le Freebox Player POP (Android TV), comme la télécommande de l'application Google TV.

  « Jarvis, allume la télé », « éteins la télé »
  « monte le son de la télé », « baisse le son de la télé de 5 », « coupe le son de la télé »
  « mets la chaîne 6 », « mets France 2 », « chaîne suivante », « chaîne précédente »
  « mets la télé en pause », « reprends la télé »
  « lance Netflix sur la télé » (Netflix, YouTube, Disney+, Prime Video)

Association une seule fois : « Jarvis, associe la télé » ouvre jarvis_associer_tele.py ; la télé affiche un code, on le tape. Jarvis garde son
certificat dans le dossier « tele » (jamais publié). Le Player est trouvé par la Freebox.
Module androidtvremote2 (licence Apache 2.0).
"""

import asyncio
import os
import re
import threading
import time

DOSSIER_CERT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tele")
CERT = os.path.join(DOSSIER_CERT, "cert.pem")
CLE = os.path.join(DOSSIER_CERT, "key.pem")
_memo = {"ip": None, "quand": 0.0}

# Chaînes dont le numéro est stable sur la Freebox (TNT) ; sinon, dire le numéro
CHAINES = {"tf1": 1, "tf un": 1, "france 2": 2, "france deux": 2, "france 3": 3, "france trois": 3,
           "canal plus": 4, "canal+": 4, "canal": 4, "france 5": 5, "france cinq": 5, "m6": 6, "m 6": 6,
           "aime six": 6, "arte": 7}
APPLIS = {"netflix": "com.netflix.ninja", "youtube": "com.google.android.youtube.tv",
          "disney": "com.disney.disneyplus", "prime video": "com.amazon.amazonvideo.livingroom",
          "amazon prime": "com.amazon.amazonvideo.livingroom"}
_NOMBRES = {"un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8,
            "neuf": 9, "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15,
            "seize": 16, "vingt": 20, "trente": 30}
_TELE = re.compile(r"\b(?:télé|tele|télévision|television|tv|téloche|player|freebox)\b")


# ---------- Plusieurs télés (facultatif) ----------
# Sans réglage, « la télé » est le Freebox Player. Pour piloter aussi d'autres télés Android TV de la maison, on les
# décrit dans tele/teles.json (dossier jamais publié : les noms des pièces restent sur ce PC) :
#   {"teles": [{"nom": "du salon", "mots": ["salon"], "appareil": "player", "defaut": true},
#              {"nom": "de la chambre", "mots": ["chambre"], "appareil": "Android TV"}]}
# « appareil » : « player » pour le Freebox Player, sinon le nom de la télé tel que la Freebox l'affiche.
# « mets France 2 sur la télé de la chambre » va à la télé dont un des « mots » est dans la phrase ; sinon à celle par défaut.
FICHIER_TELES = os.path.join(DOSSIER_CERT, "teles.json")
_memos = {}                     # appareil -> (ip, quand)


def _sans_accents(t):
    for a, b in (("àâä", "a"), ("éèêë", "e"), ("îï", "i"), ("ôö", "o"), ("ùûü", "u"), ("ç", "c")):
        for lettre in a:
            t = t.replace(lettre, b)
    return t.lower()


def teles():
    """Les télés décrites dans tele/teles.json ([] s'il n'y en a pas : une seule télé, le Player)."""
    try:
        import json
        with open(FICHIER_TELES, encoding="utf-8-sig") as f:
            return [x for x in json.load(f).get("teles", []) if x.get("nom") and x.get("appareil")]
    except (OSError, ValueError, AttributeError):
        return []


def tele_nommee(t):
    """(télé citée dans la phrase ou None, phrase sans le nom de la pièce). None : la télé par défaut."""
    simple = _sans_accents(t)
    for tele in teles():
        for mot in sorted(tele.get("mots") or [], key=len, reverse=True):
            m = re.search(r"\s*\b(?:(?:de|dans|à|a) (?:la |le |l')?|du |d')?" + re.escape(_sans_accents(mot)) + r"\b", simple)
            if m:
                reste = (t[:m.start()] + t[m.end():]).strip()
                return (None if tele.get("defaut") else tele), " ".join(reste.split())
    return None, t


def adresse(forcer=False, appareil=None):
    """IP de la télé d'après la Freebox (gardée 10 minutes), ou None. Sans « appareil » : le Freebox Player POP."""
    if appareil and appareil.lower() != "player":
        ip, quand = _memos.get(appareil, (None, 0.0))
        if ip and not forcer and time.time() - quand < 600:
            return ip
        import jarvis_freebox
        for h in jarvis_freebox._lire("lan/browser/pub/") or []:
            if (h.get("primary_name") or "").strip().lower() == appareil.strip().lower():
                ips = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4" and c.get("active")]
                if ips:
                    _memos[appareil] = (ips[0], time.time())
                    return ips[0]
        return None
    if _memo["ip"] and not forcer and time.time() - _memo["quand"] < 600:
        return _memo["ip"]
    import jarvis_freebox
    for h in jarvis_freebox._lire("lan/browser/pub/") or []:
        if h.get("host_type") == "freebox_pop" or "player" in (h.get("primary_name") or "").lower():
            ips = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4" and c.get("active")]
            if ips:
                _memo.update(ip=ips[0], quand=time.time())
                return ips[0]
    return None


def associe():
    return os.path.exists(CERT) and os.path.exists(CLE)


# ---------- Connexion gardée ouverte : les ordres partent tout de suite ----------

_boucle = None
_liens = {}                     # ip -> connexion ouverte (une par télé)


def _boucle_fond():
    global _boucle
    if _boucle is None:
        _boucle = asyncio.new_event_loop()
        threading.Thread(target=_boucle.run_forever, daemon=True, name="Télé").start()
    return _boucle


def _oublier_connexion(ip=None):
    """Ferme la connexion de cette télé (ou de toutes, sans adresse)."""
    for adresse_ip in ([ip] if ip else list(_liens)):
        tele = _liens.pop(adresse_ip, None)
        if tele is not None:
            try:
                tele.disconnect()
            except Exception:
                pass


async def _connexion(ip):
    if _liens.get(ip) is not None:
        return _liens[ip]
    from androidtvremote2 import AndroidTVRemote
    tele = AndroidTVRemote("Jarvis", CERT, CLE, ip)
    await asyncio.wait_for(tele.async_connect(), timeout=8)
    tele.keep_reconnecting()                           # se reconnecte tout seul si la télé redémarre
    await asyncio.sleep(0.4)                           # le temps de recevoir l'état (allumée ou non)
    _liens[ip] = tele
    return tele


def prechauffer():
    """Au démarrage de Jarvis : se connecter tout de suite, pour que le premier ordre soit rapide
    (le Player, et les autres télés déjà associées)."""
    if not associe():
        return
    def connecter():
        for appareil in [None] + [x["appareil"] for x in teles() if not x.get("defaut") and x.get("associee")]:
            try:
                ip = adresse(appareil=appareil)
                if ip:
                    asyncio.run_coroutine_threadsafe(_connexion(ip), _boucle_fond()).result(timeout=15)
            except Exception as erreur:
                print("Télé (préparation) :", appareil or "Player", type(erreur).__name__, erreur)
    threading.Thread(target=connecter, daemon=True).start()


async def _envoyer_avec_reprise(ip, actions):
    try:
        return await _envoyer(await _connexion(ip), actions)
    except Exception as erreur:
        if "InvalidAuth" in type(erreur).__name__:
            raise
        _oublier_connexion(ip)
        return await _envoyer(await _connexion(ip), actions)


async def _envoyer(tele, actions):
    """actions : liste de ("touche", code) / ("appli", nom) / ("allumer", bool). Renvoie l'état allumé."""
    if True:
        for genre, valeur in actions:
            if genre == "allumer":
                if bool(tele.is_on) != valeur:
                    tele.send_key_command("KEYCODE_POWER")
            elif genre == "touche":
                tele.send_key_command(valeur)
                await asyncio.sleep(0.12)
            elif genre == "appli":
                tele.send_launch_app_command(valeur)
        await asyncio.sleep(0.1)
        return tele.is_on


def executer(actions, tele=None):
    """Envoie les touches à la télé (sans « tele » : le Freebox Player). Renvoie (réussi, message d'erreur)."""
    nom = ("la télé " + tele["nom"]) if tele else "la télé"
    appareil = tele["appareil"] if tele else None
    if not associe() or (tele and not tele.get("associee")):
        return False, (f"{nom[0].upper() + nom[1:]} n'est pas encore associée à Jarvis. Dis-moi : associe {nom}, "
                       "puis tape le code qui s'affiche sur l'écran.")
    ip = adresse(appareil=appareil) or adresse(forcer=True, appareil=appareil)
    if not ip:
        if tele:
            return False, f"Je ne trouve pas {nom} sur le réseau. Elle est peut-être éteinte ou débranchée."
        return False, "Je ne trouve pas le Freebox Player sur le réseau. Il est peut-être débranché."
    try:
        asyncio.run_coroutine_threadsafe(_envoyer_avec_reprise(ip, actions), _boucle_fond()).result(timeout=20)
        return True, ""
    except Exception as erreur:
        print("Télé :", type(erreur).__name__, erreur)
        if tele:
            _memos.pop(appareil, None)
        else:
            _memo.update(ip=None, quand=0.0)
        _boucle_fond().call_soon_threadsafe(_oublier_connexion, ip)
        if "InvalidAuth" in type(erreur).__name__:
            return False, f"{nom[0].upper() + nom[1:]} ne reconnaît plus Jarvis. Dis-moi : associe {nom}, pour recommencer l'association."
        if tele:
            return False, f"{nom[0].upper() + nom[1:]} ne répond pas. Elle est peut-être éteinte ou débranchée."
        return False, "Le Freebox Player ne répond pas. Il est peut-être en veille profonde ou débranché."


def _nombre(texte, defaut):
    m = re.search(r"\b(\d{1,2})\b", texte)
    if m:
        return int(m.group(1))
    for mot, n in _NOMBRES.items():
        if re.search(r"\b" + mot + r"\b", texte):
            return n
    return defaut


def _chaine(t):
    """Numéro de chaîne demandé, ou None."""
    m = re.search(r"\bcha[îi]ne\s+(?:numéro\s+|n°\s*)?(\d{1,3}|[a-z]+)\b", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _NOMBRES.get(m.group(1))
        if n:
            return n
    # (« mets » est souvent entendu « mais » : accepté seulement si la suite est un nom de chaîne connu)
    m = re.search(r"\b(?:mets|met|mais|passe|zappe|change)\b(?:\s+(?:sur|la télé sur|moi))?\s+(.+?)\s*$", t)
    if m:
        nom = re.sub(r"^(?:la|le|l')\s*", "", m.group(1)).strip()
        nom = re.sub(r"\s+(?:sur|à) la (?:télé|tele|tv)$", "", nom)
        if nom in CHAINES:
            return CHAINES[nom]
    # « télé, France 2 », « la télé sur Arte » : le nom de la chaîne juste après « télé »
    m = re.search(r"\b(?:télé|tele|tv)\W+(?:sur\s+)?(?:la\s+|le\s+)?(.+?)\s*$", t)
    if m and m.group(1).strip() in CHAINES:
        return CHAINES[m.group(1).strip()]
    return None


_ASSOCIER = re.compile(r"\b(?:associe|associer|appaire|appairer|jumelle|jumeler|connecte|relie|apparie)\b.{0,25}"
                       r"\b(?:télé|tele|télévision|tv|player|apple)\b")
_CAMERAS = re.compile(r"\b(?:ajoute|ajouter|relie|associe|connecte|configure)\b.{0,15}\bcam[ée]ras?\b")


def _lancer_outil(nom, *arguments):
    """Ouvre un petit outil (association de la télé, de l'Apple TV, des caméras) dans sa propre fenêtre :
    il faut y taper un code, que Jarvis ne voit jamais."""
    import subprocess
    import sys
    dossier = os.path.dirname(os.path.abspath(__file__))
    python = os.path.join(os.path.dirname(sys.executable), "python.exe")
    if not os.path.exists(python):
        python = sys.executable
    subprocess.Popen([python, os.path.join(dossier, nom), *arguments], cwd=dossier,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))


def commande_associer(t, enfant=False):
    """« associe la télé », « associe l'Apple TV », « ajoute les caméras » : ouvre l'outil d'association."""
    t = t.replace("’", "'").lower()
    arguments = ()
    if _CAMERAS.search(t):
        outil, texte = "jarvis_ajouter_camera.py", ("J'ouvre la fenêtre des caméras. Tape le code de sécurité de chaque "
                                                   "caméra, celui écrit sous la caméra ; je ne le vois jamais.")
    elif _ASSOCIER.search(t):
        if re.search(r"\b(?:apple|appel|apel|polle|pôle|pole)\b", t):
            outil, texte = "jarvis_associer_appletv.py", ("J'ouvre la fenêtre d'association. Un code à quatre chiffres "
                                                         "va s'afficher deux fois sur la télé : tape-le dans la fenêtre.")
        else:
            outil, texte = "jarvis_associer_tele.py", ("J'ouvre la fenêtre d'association. Allume la télé : un code de six "
                                                      "caractères va s'y afficher, tape-le dans la fenêtre.")
            cible = tele_nommee(t)[0]                      # « associe la télé de la chambre » : une autre télé
            if cible:
                arguments = (cible["appareil"],)
                texte = (f"J'ouvre la fenêtre d'association. Allume la télé {cible['nom']} : un code de six "
                         "caractères va s'y afficher, tape-le dans la fenêtre.")
    else:
        return None
    if enfant:
        return "Ça, c'est pour les parents."
    try:
        _lancer_outil(outil, *arguments)
    except Exception as erreur:
        print("Outil d'association :", erreur)
        return "Je n'arrive pas à ouvrir la fenêtre d'association."
    return texte


def commande(t, enfant=False):
    t = t.replace("’", "'").lower().strip(" .!?")
    t = re.sub(r"^\W*(?:jarvis\W+)?", "", t)
    reponse = commande_associer(t, enfant)
    if reponse:
        return reponse
    if re.search(r"\b(?:apple|appel|apel|happy|polle|pôle|pole|appelle)[\s-]*(?:tv|t\.v|tévé|tivi|télé|tele)\b", t):
        return None                                      # l'Apple TV a son propre module (jarvis_appletv)
    cible, t = tele_nommee(t)                            # « … sur la télé de la chambre » : quelle télé ?
    tele = bool(_TELE.search(t))
    actions, reponse = None, None
    if tele and re.search(r"\b(?:allume|allumer|démarre|mets en route)\b", t):
        actions, reponse = [("allumer", True)], "J'allume la télé."
    elif tele and re.search(r"\b(?:éteins|eteins|éteindre|coupe la télé|arrête la télé|ferme la télé)\b", t) \
            and not re.search(r"\bson\b", t):
        actions, reponse = [("allumer", False)], "J'éteins la télé."
    elif tele and re.search(r"\b(?:coupe|couper|remets|rétablis)\b.*\bson\b|\bmuet\b", t):
        actions, reponse = [("touche", "KEYCODE_VOLUME_MUTE")], "C'est fait."
    elif tele and re.search(r"\b(?:monte|augmente|plus fort|hausse)\b", t):
        n = min(_nombre(t, 3), 20)
        actions, reponse = [("touche", "KEYCODE_VOLUME_UP")] * n, "Je monte le son de la télé."
    elif tele and re.search(r"\b(?:baisse|diminue|moins fort)\b", t):
        n = min(_nombre(t, 3), 20)
        actions, reponse = [("touche", "KEYCODE_VOLUME_DOWN")] * n, "Je baisse le son de la télé."
    elif re.search(r"\bcha[îi]ne\s+(?:suivante|d'après)\b", t):
        actions, reponse = [("touche", "KEYCODE_CHANNEL_UP")], "Chaîne suivante."
    elif re.search(r"\bcha[îi]ne\s+(?:précédente|d'avant)\b", t):
        actions, reponse = [("touche", "KEYCODE_CHANNEL_DOWN")], "Chaîne précédente."
    elif tele and re.search(r"\b(?:pause|reprends|reprendre|relance la lecture|play)\b", t):
        actions, reponse = [("touche", "KEYCODE_MEDIA_PLAY_PAUSE")], "C'est fait."
    elif tele and re.search(r"\b(?:lance|ouvre|mets)\b", t) and any(a in t for a in APPLIS):
        nom = next(a for a in APPLIS if a in t)
        actions, reponse = [("allumer", True), ("appli", APPLIS[nom])], f"Je lance {nom.title()} sur la télé."
    else:
        n = _chaine(t)
        if n and (tele or re.search(r"\bcha[îi]ne\b", t) or re.search(r"\b(?:mets|passe|zappe)\b", t)):
            actions = [("allumer", True)] + [("touche", f"KEYCODE_{c}") for c in str(n)]
            reponse = f"Je mets la chaîne {n}."
    if not actions:
        return None
    if enfant and actions[0] == ("allumer", True) and len(actions) == 1:
        return "Pour allumer la télé, demande à un parent."
    if cible is None:
        ok, erreur = executer(actions)
        return reponse if ok else erreur
    ok, erreur = executer(actions, cible)
    if not ok:
        return erreur
    if "la télé" in reponse:
        return reponse.replace("la télé", "la télé " + cible["nom"], 1)
    return reponse.rstrip(".") + f", sur la télé {cible['nom']}."
