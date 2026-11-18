"""
JARVIS - l'Apple TV, comme l'app Télécommande de l'iPhone.

  « Jarvis, allume l'Apple TV », « éteins l'Apple TV »
  « mets l'Apple TV en pause », « reprends l'Apple TV »
  « monte le son de l'Apple TV », « baisse le son de l'Apple TV »
  « qu'est-ce qui passe sur l'Apple TV ? »
  « lance Netflix sur l'Apple TV » (n'importe quelle app installée sur l'Apple TV)

Association une seule fois : « Jarvis, associe l'Apple TV » ouvre jarvis_associer_appletv.py (codes à 4 chiffres affichés sur la télé). Les clés
d'association sont rangées dans le Gestionnaire d'identification de Windows (« Jarvis-AppleTV-Companion »
et « Jarvis-AppleTV-AirPlay »), jamais dans un fichier ni sur GitHub. Module pyatv (licence MIT).
"""

import asyncio
import difflib
import re
import threading
import time
import unicodedata

CIBLES = {"Companion": "Jarvis-AppleTV-Companion", "AirPlay": "Jarvis-AppleTV-AirPlay"}
_memo = {"ip": None, "quand": 0.0}
_APPLE_TV = re.compile(r"\b(?:apple|appel|apel|happy|apple's|polle|pôle|pole|appelle)[\s-]*"
                       r"(?:tv|t\.v\.?|tévé|tivi|télé|tele|t v)\b")


def adresse(forcer=False):
    """IP de l'Apple TV d'après la Freebox (gardée 10 minutes), ou None."""
    if _memo["ip"] and not forcer and time.time() - _memo["quand"] < 600:
        return _memo["ip"]
    import jarvis_freebox
    for h in jarvis_freebox._lire("lan/browser/pub/") or []:
        texte = ((h.get("vendor_name") or "") + " " + (h.get("primary_name") or "")).lower()
        if "apple" in texte and re.search(r"\btv\b|apple-tv|appletv", texte):
            ips = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4" and c.get("active")]
            if ips:
                _memo.update(ip=ips[0], quand=time.time())
                return ips[0]
    return None


def _cles():
    import jarvis_mails
    cles = {}
    for protocole, cible in CIBLES.items():
        ident = jarvis_mails.identifiants(cible)
        if ident and ident[1]:
            cles[protocole] = ident[1]
    return cles


def associe():
    return "Companion" in _cles()


def _sans_accents(t):
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


async def _connecter(ip):
    import pyatv
    from pyatv.const import Protocol
    loop = asyncio.get_running_loop()
    trouves = await pyatv.scan(loop, hosts=[ip], timeout=5)
    if not trouves:
        raise ConnectionError("Apple TV introuvable")
    conf = trouves[0]
    for protocole, cle in _cles().items():
        conf.set_credentials(getattr(Protocol, protocole), cle)
    return await pyatv.connect(conf, loop)


# ---------- Connexion gardée ouverte (plus rapide : pas de recherche ni de poignée de main à chaque ordre) ----------

_boucle = None
_lien = {"atv": None, "ip": None}
_applis = {"quand": 0.0, "liste": None}


def _boucle_fond():
    """Une boucle asyncio qui tourne en permanence dans un fil à part, pour garder la connexion."""
    global _boucle
    if _boucle is None:
        _boucle = asyncio.new_event_loop()
        threading.Thread(target=_boucle.run_forever, daemon=True, name="Apple TV").start()
    return _boucle


def _oublier_connexion():
    atv = _lien["atv"]
    _lien.update(atv=None, ip=None)
    if atv is not None:
        try:
            atv.close()
        except Exception:
            pass


async def _connexion(ip):
    if _lien["atv"] is not None and _lien["ip"] == ip:
        return _lien["atv"]
    _oublier_connexion()
    from pyatv.interface import DeviceListener

    class _Ecoute(DeviceListener):
        def connection_lost(self, exception):
            _lien.update(atv=None, ip=None)

        def connection_closed(self):
            _lien.update(atv=None, ip=None)

    atv = await _connecter(ip)
    atv.listener = _Ecoute()
    _lien.update(atv=atv, ip=ip)
    return atv


async def _agir_avec_reprise(ip, action, valeur=None):
    """Avec la connexion gardée ; si elle était tombée sans qu'on le sache, on se reconnecte une fois."""
    try:
        return await _agir(await _connexion(ip), action, valeur)
    except Exception as erreur:
        if any(m in type(erreur).__name__ for m in ("Auth", "Pairing", "NotSupported")):
            raise
        _oublier_connexion()
        return await _agir(await _connexion(ip), action, valeur)


def prechauffer():
    """Au démarrage de Jarvis : se connecter tout de suite, pour que le premier ordre soit rapide."""
    if not associe():
        return
    def connecter():
        try:
            ip = adresse()
            if ip:
                asyncio.run_coroutine_threadsafe(_connexion(ip), _boucle_fond()).result(timeout=20)
        except Exception as erreur:
            print("Apple TV (préparation) :", type(erreur).__name__, erreur)
    threading.Thread(target=connecter, daemon=True).start()


async def _agir(atv, action, valeur=None):
    if True:
        if action == "allumer":
            await atv.power.turn_on()
        elif action == "eteindre":
            await atv.power.turn_off()
        elif action == "pause":
            await atv.remote_control.pause()
        elif action == "lecture":
            await atv.remote_control.play()
        elif action == "plus":
            for _ in range(valeur or 2):
                await atv.audio.volume_up()
        elif action == "moins":
            for _ in range(valeur or 2):
                await atv.audio.volume_down()
        elif action == "menu":
            await atv.remote_control.home()
        elif action == "quoi":
            try:
                appli = atv.metadata.app
                nom_appli = appli.name if appli else ""
            except Exception:
                nom_appli = ""
            try:
                lecture = await atv.metadata.playing()
                titre = " — ".join(x for x in (lecture.title, lecture.artist or lecture.series_name) if x)
                etat = lecture.device_state.name
            except Exception:
                titre, etat = "", ""
            return nom_appli, titre, etat
        elif action == "appli":
            if _applis["liste"] is None or time.time() - _applis["quand"] > 3600:    # liste gardée une heure
                _applis.update(liste=await atv.apps.app_list(), quand=time.time())
            noms = {_sans_accents(a.name): a for a in _applis["liste"]}
            cherche = _sans_accents(valeur)
            choix = noms.get(cherche) or next((a for n, a in noms.items() if cherche in n), None)
            if not choix:
                proche = difflib.get_close_matches(cherche, list(noms), n=1, cutoff=0.7)
                choix = noms[proche[0]] if proche else None
            if not choix:
                return None
            try:
                from pyatv.const import PowerState
                if atv.power.power_state != PowerState.On:
                    await atv.power.turn_on()
            except Exception:
                await atv.power.turn_on()
            await atv.apps.launch_app(choix.identifier)
            return choix.name
        return True


def executer(action, valeur=None):
    """(réussi, résultat ou message d'erreur)."""
    if not associe():
        return False, ("L'Apple TV n'est pas encore associée à Jarvis. Dis-moi : associe l'Apple TV, puis tape les "
                       "codes qui s'affichent sur la télé.")
    ip = adresse() or adresse(forcer=True)
    if not ip:
        return False, "Je ne trouve pas l'Apple TV sur le réseau."
    try:
        futur = asyncio.run_coroutine_threadsafe(_agir_avec_reprise(ip, action, valeur), _boucle_fond())
        return True, futur.result(timeout=25)
    except Exception as erreur:
        print("Apple TV :", type(erreur).__name__, erreur)
        _memo.update(ip=None, quand=0.0)
        _boucle_fond().call_soon_threadsafe(_oublier_connexion)     # fermée dans son propre fil
        if "Auth" in type(erreur).__name__ or "Pairing" in type(erreur).__name__:
            return False, "L'Apple TV ne reconnaît plus Jarvis. Dis-moi : associe l'Apple TV, pour recommencer."
        if "NotSupported" in type(erreur).__name__:
            return False, "L'Apple TV ne permet pas de faire ça à distance."
        return False, "L'Apple TV ne répond pas."


def _nombre(t, defaut):
    m = re.search(r"\b(\d{1,2})\b", t)
    return min(int(m.group(1)), 15) if m else defaut


def commande(t, enfant=False):
    t = t.replace("’", "'").lower().strip(" .!?")
    if not _APPLE_TV.search(t):
        return None
    if re.search(r"\b(?:éteins|eteins|éteindre|arrête|ferme)\b", t) and not re.search(r"\bson\b", t):
        action, valeur, reponse = "eteindre", None, "J'éteins l'Apple TV."
    elif re.search(r"\b(?:allume|allumer|réveille)\b", t):
        if enfant:
            return "Pour allumer l'Apple TV, demande à un parent."
        action, valeur, reponse = "allumer", None, "J'allume l'Apple TV."
    elif re.search(r"\bpause\b", t):
        action, valeur, reponse = "pause", None, "C'est en pause."
    elif re.search(r"\b(?:reprends|reprendre|relance|play|lecture)\b", t):
        action, valeur, reponse = "lecture", None, "C'est reparti."
    elif re.search(r"\b(?:monte|augmente|plus fort)\b", t):
        action, valeur, reponse = "plus", _nombre(t, 2), "Je monte le son."
    elif re.search(r"\b(?:baisse|diminue|moins fort)\b", t):
        action, valeur, reponse = "moins", _nombre(t, 2), "Je baisse le son."
    elif re.search(r"\b(?:accueil|menu)\b", t):
        action, valeur, reponse = "menu", None, "Retour à l'accueil."
    elif re.search(r"qu'est-ce qui (?:passe|joue)|qu'est-ce qu'on regarde|c'est quoi (?:ce|le) (?:film|programme)|"
                   r"il y a quoi|qu'est-ce qu'il y a", t):
        ok, resultat = executer("quoi")
        if not ok:
            return resultat
        appli, titre, etat = resultat
        if titre:
            return f"Sur l'Apple TV : {titre}" + (f", dans {appli}" if appli else "") + \
                (", en pause." if etat == "Paused" else ".")
        if appli:
            return f"L'Apple TV est sur {appli}, mais elle ne dit pas ce qui passe."
        return "Rien ne passe sur l'Apple TV en ce moment."
    else:
        m = re.search(r"\b(?:lance|lances|ouvre|mets|met|mes|mais)\s+(.+?)\s+(?:sur|à|dans)\s+(?:l'|la\s+)?\s*"
                      r"(?:apple|appel|apel|happy|polle|pôle|pole|appelle)", t)
        if not m:
            return None
        ok, nom = executer("appli", m.group(1).strip())
        if not ok:
            return nom
        return f"Je lance {nom} sur l'Apple TV." if nom else f"Je ne trouve pas {m.group(1)} sur l'Apple TV."
    ok, erreur = executer(action, valeur)
    return reponse if ok else erreur
