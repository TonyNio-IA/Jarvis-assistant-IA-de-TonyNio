"""
JARVIS - la Freebox (sans Claude, sur le réseau de la maison uniquement).

  « qui m'a appelé ? », « est-ce que j'ai des appels manqués ? »        derniers appels du téléphone fixe
  « est-ce qu'Internet marche ? », « quel est le débit ? »              état de la connexion
  « combien d'appareils sont connectés ? »                               appareils actifs sur le réseau
Jarvis a été autorisé sur l'écran de la Freebox ; son jeton est rangé dans le Gestionnaire d'identification
de Windows (cible « Jarvis-Freebox »), jamais dans un fichier. Sans ce jeton, ces commandes répondent
comment l'autoriser. Rien n'est modifié sur la box : lecture seule.
"""

import hashlib
import hmac
import json
import re
import time
import urllib.request

BASE = "http://mafreebox.freebox.fr/api/v16/"
APP_ID = "fr.jarvis.assistant"
CIBLE = "Jarvis-Freebox"

_APPELS = re.compile(r"\b(?:qui m'a (?:appel[ée]|t[ée]l[ée]phon[ée])|appels? (?:manqu[ée]s?|en absence|re[çc]us)|"
                     r"(?:derniers|mes) appels|on m'a appel[ée]|quelqu'un a appel[ée]|journal des appels|"
                     r"(?:j'ai eu|ai-je eu|il y a eu|y a eu|j'ai re[çc]u) des appels)\b")
_CONNEXION = re.compile(r"\b(?:internet (?:marche|fonctionne|est coup[ée]|est en panne)|(?:la |ma )?connexion internet|"
                        r"(?:quel est le |mon |le )d[ée]bit|vitesse (?:d'internet|de la connexion|de ma connexion)|"
                        r"[ée]tat de (?:la |ma )?(?:connexion|freebox|box))\b")
_APPAREILS = re.compile(r"\b(?:combien|quels?)\b.{0,20}\bappareils?\b.{0,25}\b(?:connect[ée]s|r[ée]seau|wi-?fi|box)\b|"
                        r"\bqui est connect[ée]\b")


def _appel(chemin, donnees=None, session=None):
    corps = json.dumps(donnees).encode() if donnees is not None else None
    entetes = {"Content-Type": "application/json"}
    if session:
        entetes["X-Fbx-App-Auth"] = session
    req = urllib.request.Request(BASE + chemin, data=corps, headers=entetes)
    with urllib.request.urlopen(req, timeout=6) as r:
        return json.loads(r.read().decode())


def _session():
    import jarvis_mails
    ident = jarvis_mails.identifiants(CIBLE)
    if not ident or not ident[1]:
        return None
    defi = _appel("login/")["result"]["challenge"]
    mot = hmac.new(ident[1].strip().encode(), defi.encode(), hashlib.sha1).hexdigest()
    r = _appel("login/session/", {"app_id": APP_ID, "password": mot})
    return r["result"]["session_token"] if r.get("success") else None


def _lire(chemin):
    session = _session()
    if session is None:
        raise PermissionError
    try:
        return _appel(chemin, session=session).get("result")
    finally:
        try:
            _appel("login/logout/", {}, session=session)
        except Exception:
            pass


def _quand(horodatage):
    t, maintenant = time.localtime(horodatage), time.localtime()
    heure = f"{t.tm_hour} h {t.tm_min:02d}" if t.tm_min else f"{t.tm_hour} h"
    if t.tm_yday == maintenant.tm_yday and t.tm_year == maintenant.tm_year:
        return f"aujourd'hui à {heure}"
    if time.localtime(horodatage + 86400).tm_yday == maintenant.tm_yday:
        return f"hier à {heure}"
    return f"le {t.tm_mday}/{t.tm_mon:02d} à {heure}"


def _qui(appel):
    nom = (appel.get("name") or "").strip()
    numero = (appel.get("number") or "").strip()
    if nom and nom != numero:
        return nom
    if not numero:
        return "un numéro masqué"
    chiffres = re.sub(r"\D", "", numero)
    return "le " + " ".join(chiffres[i:i + 2] for i in range(0, len(chiffres), 2))


def _appels(t):
    journal = _lire("call/log/") or []
    manques = [a for a in journal if a.get("type") == "missed"]
    if not journal:
        return "Je ne vois aucun appel dans le journal de la Freebox."
    recents = sorted(manques if (manques or "manqu" in t or "absence" in t) else journal,
                     key=lambda a: a.get("datetime", 0), reverse=True)[:3]
    if not recents:
        return "Tu n'as aucun appel manqué."
    nouveaux = sum(1 for a in manques if a.get("new"))
    debut = (f"Tu as {nouveaux} appel{'s' if nouveaux > 1 else ''} manqué{'s' if nouveaux > 1 else ''} pas encore vu"
             f"{'s' if nouveaux > 1 else ''}. " if nouveaux else "")
    phrases = [f"{_qui(a)}, {_quand(a.get('datetime', 0))}" for a in recents]
    titre = "Derniers appels manqués" if manques else "Derniers appels"
    return debut + titre + " : " + " ; ".join(phrases) + "."


def _megabits(octets_par_seconde):
    return round(octets_par_seconde * 8 / 1e6)


def _connexion():
    c = _lire("connection/") or {}
    if c.get("state") != "up":
        return "La Freebox n'est pas connectée à Internet en ce moment."
    maxi = round((c.get("bandwidth_down") or 0) / 1e6)
    phrase = "Oui, Internet fonctionne"
    if c.get("media") == "ftth":
        phrase += ", par la fibre"
    if maxi:
        phrase += f", jusqu'à {maxi // 1000} gigabit{'s' if maxi >= 2000 else ''}" if maxi >= 1000 else f", jusqu'à {maxi} mégabits"
    bas, haut = _megabits(c.get("rate_down") or 0), _megabits(c.get("rate_up") or 0)
    if bas or haut:
        phrase += f". En ce moment, la maison utilise {bas} mégabits en réception et {haut} en envoi"
    else:
        phrase += ". La connexion est presque inutilisée en ce moment"
    return phrase + "."


def _appareils():
    hotes = _lire("lan/browser/pub/") or []
    actifs = [h for h in hotes if h.get("active")]
    return f"{len(actifs)} appareil{'s sont connectés' if len(actifs) > 1 else ' est connecté'} au réseau de la maison en ce moment."


# ---------- Wi-Fi invité (le mot de passe est seulement affiché, jamais dit à voix haute) ----------

_WIFI = r"(?:wi-?fi|wifi|réseau|reseau|accès|acces|code wi-?fi)"
_INVITE_CREER = re.compile(r"\b(?:cr[ée]e|ouvre|active|fais|donne|pr[ée]pare|g[ée]n[èe]re)\b.{0,25}" + _WIFI + r".{0,15}\binvit[ée]s?\b|"
                           r"\bcode wi-?fi pour (?:un |une |des |mes |nos )?(?:invit[ée]s?|amis?)\b")
_INVITE_MONTRER = re.compile(r"\b(?:affiche|montre|redonne|r[ée]affiche|c'est quoi|quel est)\b.{0,30}"
                             r"\b(?:code|mot de passe|cl[ée]|qr|q r|cure)\b.{0,20}" + _WIFI + r".{0,10}\binvit[ée]s?\b")
_INVITE_FERMER = re.compile(r"\b(?:supprime|ferme|coupe|d[ée]sactive|arr[êe]te|retire|enl[èe]ve)\b.{0,25}" + _WIFI +
                            r".{0,15}\binvit[ée]s?\b")
DESCRIPTION = "Jarvis"
_LETTRES = "abcdefghjkmnpqrstuvwxyz23456789"         # sans l, i, o, 0, 1 : rien de confondable


def _afficher(texte):
    """Affiche dans la fenêtre de discussion (une vingtaine de secondes), sans le dire."""
    try:
        import jarvis_voix
        return jarvis_voix.montrer(texte)
    except Exception as erreur:
        print("Affichage :", erreur)
    return False


def _montrer_qr(reseau, cle, minutes=5):
    """Ouvre la fenêtre du QR code (jarvis_fenetre_qr.py). Le mot de passe lui est passé par l'entrée standard :
    jamais dans la ligne de commande, jamais dans un fichier. Renvoie True si la fenêtre a pu s'ouvrir."""
    if not reseau or reseau == "le Wi-Fi invité" or not cle:
        return False                             # sans le vrai nom du réseau, le QR code ne marcherait pas
    try:
        import os
        import subprocess
        import sys
        executable = sys.executable
        if executable.lower().endswith("pythonw.exe") is False:
            sans_console = os.path.join(os.path.dirname(executable), "pythonw.exe")
            executable = sans_console if os.path.exists(sans_console) else executable
        script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis_fenetre_qr.py")
        p = subprocess.Popen([executable, script], stdin=subprocess.PIPE,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        p.stdin.write(json.dumps({"reseau": reseau, "cle": cle, "minutes": minutes}).encode("utf-8"))
        p.stdin.close()
        return True
    except Exception as erreur:
        print("QR code :", erreur)
        return False


def _requete(chemin, session, donnees=None, methode=None):
    corps = json.dumps(donnees).encode() if donnees is not None else None
    req = urllib.request.Request(BASE + chemin, data=corps, method=methode,
                                 headers={"Content-Type": "application/json", "X-Fbx-App-Auth": session})
    with urllib.request.urlopen(req, timeout=8) as r:
        return json.loads(r.read().decode())


def _duree(t):
    m = re.search(r"\bpour (?:(\d+)|une?|deux|trois) ?(heures?|h|jours?|semaines?)\b", t)
    if not m:
        return 24 * 3600, "24 heures"
    n = int(m.group(1)) if m.group(1) else {"un": 1, "une": 1, "deux": 2, "trois": 3}[re.search(r"pour (\w+)", t).group(1)]
    unite = m.group(2)
    secondes = n * (3600 if unite.startswith("h") else 86400 if unite.startswith("j") else 7 * 86400)
    secondes = max(3600, min(secondes, 30 * 86400))
    mots = "heure" if unite.startswith("h") else "jour" if unite.startswith("j") else "semaine"
    return secondes, f"{n} {mots}{'s' if n > 1 else ''}"


def _wifi_invite(t, action):
    import secrets
    session = _session()
    if session is None:
        raise PermissionError
    try:
        nom = next((b.get("status", {}).get("custom_key_ssid") for b in (_requete("wifi/bss/", session).get("result") or [])
                    if b.get("status", {}).get("custom_key_ssid")), None) or "le Wi-Fi invité"
        cles = [k for k in (_requete("wifi/custom_key/", session).get("result") or [])
                if (k.get("params") or {}).get("description") == DESCRIPTION]
        if action == "fermer":
            for k in cles:
                _requete(f"wifi/custom_key/{k['id']}", session, methode="DELETE")
            return "C'est fermé : plus aucun accès invité créé par moi." if cles else "Il n'y avait pas d'accès invité ouvert."
        if action == "montrer":
            if not cles:
                return "Il n'y a pas d'accès invité ouvert. Dis-moi « crée un Wi-Fi invité » si tu en veux un."
            cle = max(cles, key=lambda k: k.get("remaining") or 0)
            heures = round((cle.get("remaining") or 0) / 3600)
            code = cle['params'].get('key', '?')
            _afficher(f"Wi-Fi invité : {code}")
            qr = _montrer_qr(nom, code)
            return (f"{'Je t’affiche le QR code à l’écran : il suffit de le scanner. ' if qr else 'Je l’affiche au-dessus du réacteur. '}"
                    f"Réseau {nom}, encore valable environ {heures} heure{'s' if heures > 1 else ''}.")
        secondes, duree_dite = _duree(t)
        code = "-".join("".join(secrets.choice(_LETTRES) for _ in range(4)) for _ in range(3))
        r = _requete("wifi/custom_key/", session, {"description": DESCRIPTION, "key": code, "max_use_count": 0,
                                                    "duration": secondes, "access_type": "net_only"}, "POST")
        if not r.get("success"):
            print("Wi-Fi invité :", r.get("msg"))
            return "La Freebox a refusé de créer l'accès invité."
        affiche = _afficher(f"Wi-Fi invité : {code}")
        if _montrer_qr(nom, code):
            fin = (" Le QR code est à l'écran : tes invités n'ont qu'à le scanner avec l'appareil photo. "
                   "Redemande « montre le QR code du Wi-Fi invité » si besoin.")
        elif affiche:
            fin = (" Le mot de passe est affiché au-dessus du réacteur pendant quelques secondes ; "
                   "redemande « affiche le code du Wi-Fi invité » si besoin.")
        else:
            fin = " Je n'arrive pas à l'afficher ici : regarde dans Freebox OS, rubrique Wi-Fi invité."
        return f"C'est fait : le réseau {nom} est ouvert pour {duree_dite}, Internet seulement.{fin}"
    finally:
        try:
            _appel("login/logout/", {}, session=session)
        except Exception:
            pass


def commande(t):
    t = t.replace("’", "'").lower()
    try:
        import jarvis_enfant
        enfant = jarvis_enfant.actif()
    except Exception:
        enfant = False
    reponse = commande_autoriser(t, enfant)
    if reponse:
        return reponse
    for motif, action in ((_INVITE_MONTRER, "montrer"), (_INVITE_FERMER, "fermer"), (_INVITE_CREER, "creer")):
        if motif.search(t):
            try:
                import jarvis_enfant, jarvis_extras
                if action != "montrer" and (jarvis_enfant.actif() or jarvis_extras.invite()):
                    return "Le Wi-Fi invité ne se règle pas en mode enfant ni en mode invité."
            except Exception:
                pass
            try:
                return _wifi_invite(t, action)
            except PermissionError:
                return "Je n'ai pas encore accès à la Freebox."
            except Exception as erreur:
                print("Freebox, Wi-Fi invité :", erreur)
                return "Je n'arrive pas à joindre la Freebox pour le moment."
    for motif, faire in ((_APPELS, lambda: _appels(t)), (_CONNEXION, _connexion), (_APPAREILS, _appareils)):
        if motif.search(t):
            try:
                return faire()
            except PermissionError:
                return ("Je n'ai pas encore accès à la Freebox. Dis-moi : connecte-toi à la Freebox, puis valide "
                        "sur l'écran de la box.")
            except Exception as erreur:
                print("Freebox :", erreur)
                return "Je n'arrive pas à joindre la Freebox pour le moment."
    return None


# ---------- Autorisation (une fois) : la demande se valide sur l'écran de la Freebox ----------

_AUTORISER = re.compile(r"\b(?:connecte[- ]toi|autorise|associe|relie[- ]toi|branche[- ]toi)\b.{0,25}\bfreebox\b|"
                        r"\bfreebox\b.{0,20}\b(?:autorise|autoriser|associer|connecter)\b")


def autoriser(app_version="1.25"):
    """Demande à la Freebox d'autoriser Jarvis ; un fil attend la validation sur l'écran de la box (3 minutes)
    et range le jeton dans le Gestionnaire d'identification de Windows (« Jarvis-Freebox »), sans l'afficher."""
    import threading
    r = _appel("login/authorize/", {"app_id": APP_ID, "app_name": "Jarvis", "app_version": app_version,
                                    "device_name": "Jarvis"})
    if not r.get("success"):
        return False
    jeton, suivi = r["result"]["app_token"], r["result"]["track_id"]

    def attendre():
        fin = time.time() + 180
        while time.time() < fin:
            try:
                statut = _appel(f"login/authorize/{suivi}").get("result", {}).get("status")
            except Exception:
                statut = None
            if statut == "granted":
                from jarvis_ajouter_camera import ranger
                ok = ranger(CIBLE, APP_ID, jeton)
                print("Freebox : Jarvis est autorisé." if ok else "Freebox : autorisé, mais le jeton n'a pas pu être rangé.")
                _afficher("Freebox : Jarvis est autorisé." if ok else "Freebox : autorisation à refaire.")
                return
            if statut in ("denied", "timeout", "unknown"):
                print("Freebox : autorisation", statut)
                _afficher("Freebox : autorisation refusée ou expirée.")
                return
            time.sleep(2)
        print("Freebox : pas de réponse à la demande d'autorisation.")
    threading.Thread(target=attendre, daemon=True).start()
    return True


def commande_autoriser(t, enfant=False):
    if not _AUTORISER.search(t.replace("’", "'").lower()):
        return None
    if enfant:
        return "Ça, c'est pour les parents."
    try:
        if autoriser():
            return ("C'est demandé. Va devant la Freebox et valide sur son écran, avec la flèche puis OK : tu as "
                    "trois minutes. Ensuite, dans Freebox OS, tu pourras me donner plus de droits, par exemple "
                    "pour le Wi-Fi invité.")
        return "La Freebox a refusé la demande. Réessaie dans un moment."
    except Exception as erreur:
        print("Freebox, autorisation :", erreur)
        return "Je n'arrive pas à joindre la Freebox. Ce PC est bien branché sur sa box ?"
