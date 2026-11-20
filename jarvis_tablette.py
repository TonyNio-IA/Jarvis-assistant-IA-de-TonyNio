# -*- coding: utf-8 -*-
"""
JARVIS - la tablette de la maison.

Jarvis sert une petite application aux tablettes et téléphones de la maison, par le Wi-Fi (ou de plus loin, par
le VPN de la box) : on appuie sur le rond, on parle (ou on écrit), et Jarvis répond sur la tablette, par écrit
et à voix haute. La voix est comprise par le Whisper de ce PC, comme pour le micro du PC.
La même page s'ouvre dans un navigateur ou dans l'application Android « Jarvis » (dossier android/), qui ajoute
le lancement des applications de la tablette et les mises à jour.

    « Jarvis, active la tablette »            (ou « ... pour Léo », le prénom d'un profil)
    « Jarvis, montre le QR code de la tablette »
    « Jarvis, désactive la tablette »

À l'activation, un QR code s'affiche : on le vise avec l'appareil photo de la tablette, on accepte
l'avertissement de sécurité (le certificat est fabriqué par Jarvis, il n'est connu de personne d'autre),
puis on installe l'application proposée par la page (ou on ajoute la page à l'écran d'accueil).

Profils : la tablette s'ouvre sur le profil par défaut (celui donné à l'activation). Chaque personne du foyer
retrouve son profil, ses couleurs et sa propre conversation. Un profil enfant s'ouvre sans code ; un profil
adulte demande un code à 4 chiffres (trois erreurs : une minute d'attente). Un code se choisit sur la tablette
dans les dix minutes qui suivent l'affichage du QR code sur le PC : un adulte est donc forcément là.
Si la voix d'un enfant du foyer est reconnue, la tablette passe toute seule sur son profil ; pour un adulte,
elle le propose seulement, et demande toujours le code.

Sécurité :
  - éteint par défaut ; seul un adulte peut l'activer (jamais en mode enfant ni en mode invité) ;
  - la page ne répond qu'avec la clé secrète contenue dans le QR code (tablette.json, jamais publié) ;
  - la liaison est chiffrée (HTTPS), ce qui permet aussi au navigateur d'utiliser le micro ;
  - depuis la tablette, Jarvis ne fait AUCUNE action sur le PC ni sur la maison (ni fenêtres, ni télé, ni
    mails, ni rappels, ni mémoire) : il discute, répond aux questions, donne l'heure, la météo, calcule,
    fait des quiz et raconte de courtes histoires ; sur la tablette elle-même, il peut ouvrir une application
    installée ou lancer une recherche dans le navigateur (sans passer par Claude) ;
  - la voix reçue ne sert jamais à apprendre ou à modifier les empreintes de voix ;
  - chaque demande (texte, réponse, et le son s'il y en a un) est gardée sur ce PC, rangée par profil, dans
    tablette/historique (jamais publié) : les 1 000 dernières par profil, les plus anciennes sont effacées.
"""
import asyncio
import base64
import datetime
import difflib
import hashlib
import hmac
import http.server
import io
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import zlib

import jarvis_config

FICHIER = jarvis_config.chemin("tablette.json")      # clé secrète, codes (hachés), couleurs : restent sur ce PC
DOSSIER = jarvis_config.chemin("tablette")           # certificat fabriqué par Jarvis, historique : restent sur ce PC
# L'application Android, proposée par la page : celle publiée avec Jarvis (docs/), ou celle fabriquée sur ce PC
# par android/construire.py si elle est plus récente.
APK = jarvis_config.chemin("docs", "Jarvis-tablette.apk")
APK_INFOS = jarvis_config.chemin("docs", "Jarvis-tablette.json")
APK_LOCALE = (jarvis_config.chemin("android", "Jarvis-tablette.apk"), jarvis_config.chemin("android", "Jarvis-tablette.json"))
PAQUET = "fr.tonynio.jarvis"     # nom de l'application Android
PORT = 47826
HOTE = "0.0.0.0"                 # toutes les cartes réseau du PC (le Wi-Fi de la maison)
TAILLE_MAX = 4_000_000           # octets : une demande parlée de 20 secondes pèse bien moins
LONGUEUR_MAX = 400               # caractères d'une demande écrite
DELAI_CLAUDE = 90                # secondes au plus pour une réponse
OUTILS = "WebSearch,WebFetch"    # depuis la tablette, Claude peut chercher sur le web, rien d'autre
PRINCIPAL = "_principal"         # nom, pour la tablette, du profil de la personne qui a installé Jarvis
DEFAUT = "_defaut"               # profil sans prénom (aucun profil donné à l'activation) : ton enfant, sans code
HISTORIQUE_MAX = 1000            # demandes gardées par profil
ESSAIS_CODE = 3                  # codes faux avant le blocage
BLOCAGE_CODE = 60                # secondes de blocage
DUREE_SESSION = 12 * 3600        # secondes sans demande : fin de la session d'un profil enfant (rouverte toute seule)
DUREE_SESSION_GARDEE = 30 * 86400   # un adulte reste sur son profil 30 jours sans retaper son code (sauf s'il en change)
DUREE_REGLAGE = 600              # secondes, après l'affichage du QR code, pendant lesquelles un code peut être choisi
REPOS_CLAUDE = 900               # secondes : la conversation d'un profil qui ne parle plus est fermée
MESSAGE_DONNEES = ("Tes données restent sur ton PC. Seuls le texte des questions et des réponses passent par Claude "
                   "et par la voix en ligne.")
PALETTES = {
    "vice city": ("#ff2e97", "#ff8c42", "#9d4dff"),
    "iron man": ("#ff3b2f", "#ffb52e", "#ffd75e"),
    "océan": ("#00b4d8", "#0077ff", "#48e5c2"),
    "forêt": ("#3ddc84", "#a3e635", "#14b8a6"),
    "paillettes": ("#ff5fb7", "#c77dff", "#ffd6f5"),
    "récré": ("#ffd23f", "#3fa9ff", "#4ade80"),
}
PALETTE_DEFAUT = "vice city"
# Le micro de l'application : source Android (1 : micro simple, 5 : micro de la caméra, 6 : voix brute, 7 : voix traitée),
# « facteur » fois le bruit de la pièce = seuil de la voix, seuil minimal, silence (ms) qui termine une phrase.
# Se règle sans refaire l'application, en ajoutant "micro": {...} dans tablette.json.
# Mesuré sur une Galaxy Tab : 5 (micro de la caméra) donne une voix nette ; 6 et 9 presque rien ; 7 hache la voix.
# Avec la source 5, une voix arrive entre 0,02 et 0,09 ; les petits bruits de la pièce (objets, clavier) sous 0,008.
# « silence » : millièmes de seconde sans voix qui terminent une phrase (écoute permanente), « silence_rond » : après un appui.
MICRO = {"source": 5, "facteur": 4, "seuil": 0.004, "silence": 800, "silence_rond": 1000}

_jarvis = None                   # le module jarvis_claude (Whisper, Claude), donné par configurer()
_claude = None                   # la classe des conversations de la tablette (None tant que Jarvis n'est pas prêt)
_claudes = {}                    # profil -> sa conversation, séparée de celle du PC et de celles des autres profils
_serveur = None
_verrou = threading.Lock()       # protège les réglages, les sessions et les conversations
_verrous = {}                    # profil -> une demande à la fois
_verrou_historique = threading.Lock()
_sessions = {}                   # empreinte du jeton -> [profil, fin, gardée sur ce PC]
_sessions_lues = None            # le fichier dont les sessions gardées ont été lues
_echecs = {}                     # profil -> [codes faux, bloqué jusqu'à]
_applis = {}                     # tablette -> [{"nom", "paquet"}] : les applications installées sur cette tablette
_applis_lues = None              # le dossier dont cette liste a été relue (elle est gardée sur ce PC)
_taches = {}                     # demandes envoyées par étapes : numéro -> ce que la tablette vient chercher
_reglage_fin = 0.0               # jusqu'à quand un code peut être choisi depuis la tablette


# ---------- Réglages ----------

def _lire():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            donnees = json.load(f)
        return donnees if isinstance(donnees, dict) else {}
    except (OSError, ValueError):
        return {}


def _ecrire(donnees):
    with open(FICHIER, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False, indent=1)


def actif():
    donnees = _lire()
    return bool(donnees.get("actif") and donnees.get("cle"))


def adresse_locale():
    """L'adresse de ce PC sur le réseau de la maison (« » si le PC n'est relié à rien)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))          # aucun envoi : sert seulement à savoir par quelle carte on sort
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def lien():
    """L'adresse à ouvrir sur la tablette, avec la clé (après le #, qui n'est jamais envoyé sur le réseau)."""
    ip = adresse_locale()
    cle = _lire().get("cle")
    return f"https://{ip}:{PORT}/#cle={cle}" if ip and cle else ""


# ---------- Certificat (fabriqué une fois par Jarvis, pour chiffrer la liaison) ----------

def _certificat():
    """Chemins (certificat, clé). Le certificat est refait si l'adresse du PC a changé ou s'il expire ; la clé,
    elle, ne change jamais : c'est à elle que l'application de la tablette reconnaît Jarvis."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    chemin_cert, chemin_cle = os.path.join(DOSSIER, "certificat.pem"), os.path.join(DOSSIER, "cle.pem")
    ip = adresse_locale() or "127.0.0.1"
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    try:
        with open(chemin_cert, "rb") as f:
            ancien = x509.load_pem_x509_certificate(f.read())
        adresses = ancien.extensions.get_extension_for_class(x509.SubjectAlternativeName).value \
            .get_values_for_type(x509.IPAddress)
        if (ipaddress.ip_address(ip) in adresses and os.path.exists(chemin_cle)
                and ancien.not_valid_after_utc - maintenant > datetime.timedelta(days=30)):
            return chemin_cert, chemin_cle
    except Exception:
        pass
    os.makedirs(DOSSIER, exist_ok=True)
    cle = None
    try:
        with open(chemin_cle, "rb") as f:
            cle = serialization.load_pem_private_key(f.read(), None)
    except Exception:
        cle = None
    if cle is None:
        cle = ec.generate_private_key(ec.SECP256R1())
        with open(chemin_cle, "wb") as f:
            f.write(cle.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    nom = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Jarvis")])
    autres = [x509.IPAddress(ipaddress.ip_address(a)) for a in dict.fromkeys((ip, "127.0.0.1"))]
    certificat = (x509.CertificateBuilder().subject_name(nom).issuer_name(nom).public_key(cle.public_key())
                  .serial_number(x509.random_serial_number())
                  .not_valid_before(maintenant - datetime.timedelta(days=1))
                  .not_valid_after(maintenant + datetime.timedelta(days=800))
                  .add_extension(x509.SubjectAlternativeName(autres + [x509.DNSName("localhost")]), critical=False)
                  .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                  .sign(cle, hashes.SHA256()))
    with open(chemin_cert, "wb") as f:
        f.write(certificat.public_bytes(serialization.Encoding.PEM))
    return chemin_cert, chemin_cle


def empreinte():
    """L'empreinte de la clé publique de Jarvis (« » si le certificat n'existe pas) : l'application de la tablette
    la garde, et ne parle ensuite qu'à ce PC."""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives import serialization
        with open(os.path.join(DOSSIER, "certificat.pem"), "rb") as f:
            certificat = x509.load_pem_x509_certificate(f.read())
        der = certificat.public_key().public_bytes(serialization.Encoding.DER,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo)
        return hashlib.sha256(der).hexdigest()
    except Exception:
        return ""


# ---------- Profils, codes et couleurs ----------

def _profils():
    """Les profils du foyer : [{"id", "prenom", "enfant"}]."""
    import jarvis_profils
    liste = []
    if jarvis_profils.PRINCIPAL["prenom"]:
        liste.append({"id": PRINCIPAL, "prenom": jarvis_profils.PRINCIPAL["prenom"], "enfant": False})
    for ident, p in jarvis_profils._lire().items():
        if not ident.startswith("_"):
            liste.append({"id": ident, "prenom": str(p.get("prenom") or ident), "enfant": bool(p.get("enfant"))})
    return liste


def _couleurs(reglage):
    """{"palette", "couleurs"} pour le réglage gardé d'un profil (une palette, ou trois couleurs choisies)."""
    reglage = reglage if isinstance(reglage, dict) else {}
    perso = reglage.get("perso")
    if (isinstance(perso, list) and len(perso) == 3
            and all(isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in perso)):
        return {"palette": "perso", "couleurs": [c.lower() for c in perso]}
    nom = reglage.get("palette") if reglage.get("palette") in PALETTES else PALETTE_DEFAUT
    return {"palette": nom, "couleurs": list(PALETTES[nom])}


def profils():
    """(liste des profils pour la tablette, identifiant du profil par défaut)."""
    donnees = _lire()
    liste = _profils()
    prenom = str(donnees.get("prenom") or "").strip()
    defaut = next((p["id"] for p in liste if prenom and p["prenom"].lower() == prenom.lower()), None)
    if defaut is None:
        liste.insert(0, {"id": DEFAUT, "prenom": prenom, "enfant": True})
        defaut = DEFAUT
    codes = donnees.get("codes") if isinstance(donnees.get("codes"), dict) else {}
    couleurs = donnees.get("couleurs") if isinstance(donnees.get("couleurs"), dict) else {}
    for p in liste:
        p["code"] = bool(not p["enfant"] and p["id"] in codes)
        p.update(_couleurs(couleurs.get(p["id"])))
    return liste, defaut


def _profil(ident):
    liste, defaut = profils()
    return next((p for p in liste if p["id"] == (ident or defaut)), None)


def _hacher(code, sel):
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), bytes.fromhex(sel), 120_000).hex()


def definir_code(ident, code):
    """Garde le code à 4 chiffres d'un profil adulte (haché : le code lui-même n'est écrit nulle part)."""
    if not re.fullmatch(r"\d{4}", str(code or "")):
        return False
    with _verrou:
        donnees = _lire()
        codes = donnees.get("codes") if isinstance(donnees.get("codes"), dict) else {}
        sel = secrets.token_hex(16)
        codes[ident] = {"sel": sel, "hache": _hacher(str(code), sel)}
        donnees["codes"] = codes
        _ecrire(donnees)
        _echecs.pop(ident, None)
    return True


def _code_bon(ident, code):
    garde = (_lire().get("codes") or {}).get(ident) or {}
    try:
        return bool(garde) and hmac.compare_digest(_hacher(str(code or ""), garde["sel"]), garde["hache"])
    except (KeyError, ValueError):
        return False


def _attente(ident):
    """Secondes pendant lesquelles ce profil reste bloqué après trop de codes faux."""
    return max(0, int(_echecs.get(ident, [0, 0])[1] - time.time() + 0.999))


def _essayer_code(ident, code):
    """(bon, message, secondes d'attente)."""
    attente = _attente(ident)
    if attente:
        return False, f"Trop de codes faux. Réessaie dans {attente} secondes.", attente
    if _code_bon(ident, code):
        _echecs.pop(ident, None)
        return True, "", 0
    echec = _echecs.setdefault(ident, [0, 0])
    echec[0] += 1
    if echec[0] >= ESSAIS_CODE:
        _echecs[ident] = [0, time.time() + BLOCAGE_CODE]
        return False, f"Trop de codes faux. Réessaie dans {BLOCAGE_CODE} secondes.", BLOCAGE_CODE
    reste = ESSAIS_CODE - echec[0]
    return False, f"Ce n'est pas le bon code. Encore {reste} essai{'s' if reste > 1 else ''}.", 0


def _empreinte_jeton(jeton):
    return hashlib.sha256(str(jeton or "").encode("utf-8")).hexdigest()


def _lire_sessions():
    """Au premier besoin : les sessions des adultes gardées sur ce PC (la tablette rouvre le dernier profil sans
    redemander le code, même après un redémarrage de Jarvis). Seule l'empreinte du jeton est écrite."""
    global _sessions_lues
    if _sessions_lues == FICHIER:
        return
    _sessions_lues = FICHIER
    _sessions.clear()
    gardees = _lire().get("sessions")
    for empreinte_, session in (gardees if isinstance(gardees, dict) else {}).items():
        if isinstance(session, list) and len(session) == 2 and session[1] > time.time():
            _sessions[empreinte_] = [str(session[0]), float(session[1]), True]


def _ecrire_sessions():
    donnees = _lire()
    donnees["sessions"] = {e: [s[0], s[1]] for e, s in _sessions.items() if s[2]}
    _ecrire(donnees)


def _ouvrir_session(ident, garder=False):
    """Un jeton pour ce profil. garder : la session d'un adulte, gardée sur ce PC pendant DUREE_SESSION_GARDEE."""
    maintenant = time.time()
    with _verrou:
        _lire_sessions()
        for vieux in [j for j, s in _sessions.items() if s[1] < maintenant]:
            del _sessions[vieux]
        jeton = secrets.token_urlsafe(24)
        _sessions[_empreinte_jeton(jeton)] = [ident, maintenant + (DUREE_SESSION_GARDEE if garder else DUREE_SESSION), garder]
        if garder:
            _ecrire_sessions()
    return jeton


def _session(jeton):
    """Le profil de cette session (None si elle n'existe pas ou plus)."""
    if not jeton:
        return None
    with _verrou:
        _lire_sessions()
        cle = _empreinte_jeton(jeton)
        session = _sessions.get(cle)
        if not session or session[1] < time.time():
            _sessions.pop(cle, None)
            return None
        if not session[2]:
            session[1] = time.time() + DUREE_SESSION
        return session[0]


def _fermer_session(jeton):
    with _verrou:
        _lire_sessions()
        session = _sessions.pop(_empreinte_jeton(jeton), None)
        if session and session[2]:
            _ecrire_sessions()


def reglage_ouvert():
    return time.time() < _reglage_fin


def entrer(ident, code=None, jeton=None):
    """La tablette demande à passer sur un profil. Renvoie ce qu'elle doit savoir.
    jeton : la session déjà ouverte sur cette tablette. Si c'est celle de ce profil, il s'ouvre sans code (la tablette
    redémarre sur le dernier profil utilisé) ; si c'est celle d'un autre, elle est fermée : on a changé de profil."""
    profil = _profil(ident)
    if profil is None:
        return {"erreur": "Ce profil n'existe plus."}
    ouvert = _session(jeton)
    if ouvert is not None and ouvert == profil["id"] and (profil["enfant"] or profil["code"]):
        _chauffer(profil["id"])
        return {"ok": True, "jeton": jeton, "profil": profil}
    if profil["enfant"]:
        if ouvert is not None:
            _fermer_session(jeton)
        _chauffer(profil["id"])
        return {"ok": True, "jeton": _ouvrir_session(profil["id"]), "profil": profil}
    if not profil["code"]:
        if reglage_ouvert():
            return {"creer": True}
        return {"erreur": "Ce profil n'a pas encore de code. Sur l'ordinateur, dis « Jarvis, montre le QR code de la "
                          "tablette », puis reviens ici dans les dix minutes pour choisir ton code."}
    if code is None:
        return {"code": True, "attente": _attente(profil["id"])}
    bon, message, attente = _essayer_code(profil["id"], code)
    if not bon:
        return {"erreur": message, "attente": attente}
    if ouvert is not None:
        _fermer_session(jeton)
    _chauffer(profil["id"])
    return {"ok": True, "jeton": _ouvrir_session(profil["id"], garder=True), "profil": profil}


def choisir_code(ident, code, ancien=None):
    """Choisit ou change le code d'un profil adulte : avec l'ancien code, ou pendant que le réglage est ouvert."""
    profil = _profil(ident)
    if profil is None or profil["enfant"]:
        return {"erreur": "Ce profil n'a pas de code."}
    if not re.fullmatch(r"\d{4}", str(code or "")):
        return {"erreur": "Le code doit faire 4 chiffres."}
    if ancien is not None and profil["code"]:
        bon, message, attente = _essayer_code(profil["id"], ancien)
        if not bon:
            return {"erreur": message, "attente": attente}
    elif not reglage_ouvert():
        return {"erreur": "Pour choisir un code, dis d'abord sur l'ordinateur « Jarvis, montre le QR code de la "
                          "tablette », puis recommence ici dans les dix minutes."}
    definir_code(profil["id"], code)
    profil["code"] = True
    with _verrou:                                    # un nouveau code ferme les sessions ouvertes avec l'ancien
        _lire_sessions()
        for vieux in [j for j, s in _sessions.items() if s[0] == profil["id"]]:
            del _sessions[vieux]
        _ecrire_sessions()
    return {"ok": True, "jeton": _ouvrir_session(profil["id"], garder=True), "profil": profil}


def regler_couleurs(ident, palette=None, perso=None):
    """Les couleurs de ce profil sur la tablette : une palette, ou trois couleurs choisies."""
    reglage = {"perso": perso} if perso else {"palette": palette}
    couleurs = _couleurs(reglage)
    if (perso and couleurs["palette"] != "perso") or (not perso and palette not in PALETTES):
        return {"erreur": "Ces couleurs ne sont pas valables."}
    with _verrou:
        donnees = _lire()
        gardees = donnees.get("couleurs") if isinstance(donnees.get("couleurs"), dict) else {}
        gardees[ident] = {"perso": couleurs["couleurs"]} if perso else {"palette": palette}
        donnees["couleurs"] = gardees
        _ecrire(donnees)
    return {"ok": True, **couleurs}


def _apk_choisie():
    """(chemin, numéro, nom) de l'application Android la plus récente que ce PC peut proposer ((None, 0, « ») s'il n'y en a pas)."""
    meilleure = (None, 0, "")
    for chemin, infos in ((APK, APK_INFOS), APK_LOCALE):
        try:
            with open(infos, encoding="utf-8") as f:
                lu = json.load(f)
            numero = int(lu.get("code") or 0)
            if os.path.exists(chemin) and numero > meilleure[1]:
                meilleure = (chemin, numero, str(lu.get("nom") or ""))
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return meilleure


def _apk():
    """(numéro, nom) de l'application Android proposée par ce PC ((0, « ») s'il n'y en a pas)."""
    return _apk_choisie()[1:]


def _micro():
    """Les réglages du micro de l'application : ceux par défaut, corrigés par "micro" dans tablette.json."""
    donnees = _lire()
    garde = donnees.get("micro")
    return {**MICRO, **(garde if isinstance(garde, dict) else {}), "bilan": bool(donnees.get("essai"))}


def _version_page():
    """Une empreinte de la page : une tablette restée ouverte se recharge toute seule quand la page a changé."""
    return hashlib.sha256(PAGE.encode("utf-8")).hexdigest()[:12]


def _essai(audio, texte):
    """Seulement pendant un réglage du micro ("essai": true dans tablette.json, à retirer ensuite) : ce que l'écoute
    permanente a entendu est écrit dans le journal, et le son est gardé dans tests/sortie pour l'examiner."""
    if not _lire().get("essai"):
        return
    try:
        import wave
        import numpy as np
        dossier = jarvis_config.chemin("tests", "sortie", "veille")
        os.makedirs(dossier, exist_ok=True)
        nom = os.path.join(dossier, time.strftime("%H%M%S") + ".wav")
        with wave.open(nom, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(16000)
            f.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        print(f"Tablette (essai du micro) : entendu « {texte} » ({len(audio) / 16000:.1f} s, crête "
              f"{float(np.max(np.abs(audio))) if len(audio) else 0:.3f}), son gardé dans {os.path.basename(nom)}")
    except Exception as erreur:
        print("Tablette (essai du micro) :", erreur)


def etat():
    """Ce que la tablette demande à l'ouverture : les profils, les palettes, la version."""
    liste, defaut = profils()
    version = ""
    try:
        import jarvis_maj
        version = jarvis_maj.version_actuelle() or ""
    except Exception:
        pass
    return {"ok": True, "prenom": next((p["prenom"] for p in liste if p["id"] == defaut), ""),
            "profils": liste, "defaut": defaut, "palettes": {nom: list(c) for nom, c in PALETTES.items()},
            "version": version, "apk": _apk()[0], "apk_nom": _apk()[1], "paquet": PAQUET, "empreinte": empreinte(),
            "micro": _micro(), "page": _version_page(),
            "reglage": reglage_ouvert(), "donnees": MESSAGE_DONNEES, "historique": HISTORIQUE_MAX}


# ---------- Comprendre et répondre ----------

def configurer(module_jarvis):
    """Appelé par jarvis_claude au lancement : donne accès à Whisper et à Claude."""
    global _jarvis, _claude
    _jarvis = module_jarvis
    _claude = module_jarvis.ClaudeContinu
    _claudes.clear()


def _conversation(ident):
    """La conversation de ce profil avec Claude (créée à la première demande). Celles des profils qui ne parlent
    plus depuis un moment sont fermées : pas de programme qui reste ouvert pour rien."""
    with _verrou:
        maintenant = time.time()
        for autre, conversation in _claudes.items():
            if autre != ident and maintenant - getattr(conversation, "dernier_usage", maintenant) > REPOS_CLAUDE:
                try:
                    conversation.arreter()
                except Exception:
                    pass
        if ident not in _claudes:
            classe = type("ClaudeTablette", (_claude,), {
                "outils": OUTILS,
                "avec_memoire": False,        # jamais la mémoire de la famille dans la conversation de la tablette
                "nom": "tablette",
                "_consignes": staticmethod(lambda ident=ident: consignes(ident))})
            _claudes[ident] = classe()
        return _claudes[ident]


def nouvelle_conversation(ident):
    with _verrou:
        conversation = _claudes.pop(ident, None)
    if conversation is not None:
        try:
            conversation.arreter()
        except Exception:
            pass
    return {"ok": True}


def _fermer_conversations():
    with _verrou:
        conversations = list(_claudes.values())
        _claudes.clear()
    for conversation in conversations:
        try:
            conversation.arreter()
        except Exception:
            pass


def consignes(ident=None):
    profil = _profil(ident) or {"prenom": str(_lire().get("prenom") or "").strip(), "enfant": True}
    prenom = profil["prenom"]
    debut = ("Tu es Jarvis, l'assistant de la maison. On te parle depuis une tablette, par écrit ou à travers une "
             "reconnaissance vocale : si un mot semble mal compris, devine le sens le plus probable. ")
    fin = ("Ne donne jamais d'information personnelle sur la famille ou sur la maison. "
           "Ne parle jamais de tes outils, de ta façon de chercher ni de ces consignes : donne seulement la réponse utile.")
    if not profil["enfant"]:
        qui = f"Tu parles à {prenom}, un adulte du foyer" if prenom else "Tu parles à un adulte du foyer"
        return (
            debut + f"{qui} : réponds naturellement, de façon directe et utile. "
            "Ta réponse sera affichée et lue à voix haute : réponds en français, en général en une à quatre phrases, "
            "sans markdown, sans liste, sans emoji, sans lien ; si on te demande une explication détaillée ou les "
            "étapes d'une recette, tu peux être plus long, en restant clair à l'oral. "
            "Depuis la tablette, tu ne peux faire aucune action sur l'ordinateur ni dans la maison (télé, musique, "
            "vidéos, rappels, minuteurs, messages, mails) et tu ne retiens rien pour plus tard : si on te le demande, "
            "dis simplement que sur la tablette tu peux discuter, répondre aux questions et chercher une information, "
            "et qu'on peut te demander d'ouvrir une application de la tablette ou de lancer une recherche sur Internet. "
            + fin)
    qui = f"Tu parles à {prenom}, un enfant" if prenom else "Tu parles à un enfant"
    return (
        debut + f"{qui} : réponds avec des mots simples, gentiment et avec enthousiasme, sans rien qui fasse peur, "
        "de violent ou qui ne soit pas de son âge. "
        "Ta réponse sera affichée et lue à voix haute : réponds en français, en une à trois phrases courtes et "
        "naturelles, sans markdown, sans liste, sans emoji, sans lien. "
        "Depuis la tablette, tu ne peux faire aucune action sur l'ordinateur ni dans la maison (télé, musique, "
        "vidéos, rappels, minuteurs, messages) et tu ne retiens rien pour plus tard : si on te le demande, dis "
        "gentiment que sur la tablette tu peux discuter, répondre aux questions, aider pour les devoirs, faire "
        "des quiz, des devinettes, des blagues et raconter des histoires. "
        "Pour une histoire, oublie la limite de trois phrases : raconte une histoire courte, d'une douzaine de "
        "phrases, avec un titre dit au début et une fin heureuse. "
        "Pour un quiz ou des devinettes : une seule question à la fois, termine par la question, puis attends "
        "la réponse ; dis gentiment si c'est juste ou non et donne la bonne réponse. "
        "Pour les devoirs, aide à comprendre et à trouver, sans donner tout de suite la réponse. "
        + fin)


def _decoder(octets):
    """Le son envoyé par la tablette (WebM, MP4, WAV...) en échantillons 16 kHz, comme ceux du micro du PC."""
    import av
    import numpy as np
    reech = av.AudioResampler(format="s16", layout="mono", rate=16000)
    morceaux = []
    with av.open(io.BytesIO(octets)) as conteneur:
        for trame in conteneur.decode(audio=0):
            for sortie in reech.resample(trame):
                morceaux.append(sortie.to_ndarray().flatten())
    if not morceaux:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(morceaux).astype(np.float32) / 32768.0


AMORCE = ("Demandes à l'assistant vocal Jarvis : Jarvis, quelle heure est-il ? Jarvis, raconte-moi une histoire. "
          "Jarvis, ouvre YouTube. Jarvis, pose-moi une devinette.")


def _amorce():
    """Quelques demandes types données à Whisper avant d'écouter : sans elles, « Jarvis » devient « J'arvisse » ; avec
    seulement « Jarvis, », il disparaît de la phrase ; avec le vocabulaire du PC (qui contient des prénoms), Whisper
    croit entendre ces prénoms. Mesuré sur de vraies demandes enregistrées par la tablette."""
    return AMORCE


def _transcrire(audio, amorce=""):
    """Texte entendu (« » si rien de clair), ou None si Whisper n'est pas prêt.
    amorce : un début de phrase donné à Whisper (écoute permanente : il reconnaît mieux le mot « Jarvis »)."""
    import numpy as np
    j = _jarvis
    if j is None or getattr(j, "whisper", None) is None:
        return None
    if len(audio) < 16000 * 0.3:
        return ""
    crete = float(np.max(np.abs(audio)))
    if crete < 0.01:
        return ""
    if crete < 0.5:
        audio = audio * (0.7 / crete)               # voix trop faible : on l'amplifie
    audio = np.concatenate((np.zeros(8000, dtype=np.float32), audio.astype(np.float32)))
    with j.verrou_whisper:
        if amorce:
            try:
                segments, _ = j.whisper.transcribe(audio, language="fr", beam_size=j.WHISPER_FAISCEAU, initial_prompt=amorce)
            except TypeError:
                segments, _ = j.whisper.transcribe(audio, language="fr", beam_size=j.WHISPER_FAISCEAU)
        else:
            segments, _ = j.whisper.transcribe(audio, language="fr", beam_size=j.WHISPER_FAISCEAU)
        texte = " ".join(s.text for s in segments).strip()
    if not texte or re.search(r"amara|sous-titr", texte, re.I) or j._repetitif(texte):
        return ""                                    # phrases que Whisper invente sur du bruit
    return texte


def _reconnaitre(audio, texte):
    """Le profil dont c'est la voix (None en cas de doute). Lecture seule : les empreintes apprises sur le PC
    servent à comparer, mais rien de ce qui vient de la tablette n'y est jamais ajouté."""
    try:
        import numpy as np
        import jarvis_locuteur as loc
        import jarvis_profils
        if not loc.disponible() or len(audio) < 16000:
            return None
        crete = float(np.max(np.abs(audio)))
        if crete < 0.01:
            return None
        if crete < 0.5:
            audio = audio * (0.7 / crete)
        octets = (np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes()
        resultat = loc._vecteur(octets, texte)
        if not resultat or resultat[1] < loc.TRAMES_MIN:
            return None
        vecteur = resultat[0]
        connus = jarvis_profils._lire()
        auto = loc._charger_auto()
        empreintes = {i: list(v) + list(auto.get(i, [])) for i, v in loc._charger().items()
                      if len(v) >= 3 and (i == "" or i in connus)}
        if len(empreintes) < 2:
            return None
        distances = sorted((1 - float(vecteur @ loc._centre(v)), i) for i, v in empreintes.items())
        (d1, ident), (d2, _) = distances[0], distances[1]
        if d1 <= loc.DISTANCE_MAX and d2 - d1 >= loc.MARGE_MIN:
            return ident or PRINCIPAL
    except Exception as erreur:
        print("Tablette (voix reconnue) :", erreur)
    return None


# « Jarvis » tel que Whisper l'écrit parfois : Jarvis, Jervis, Javis, « J'avise », « J'arvisse », Gervais, Charvis...
_MOT_APPEL = re.compile(r"\b(?:d?j['’ ]?[ae]r?v[iy]s*e?\w{0,2}|d?jarv\w{0,4}|gerv(?:ais|is|aise)|[cs]harv[iy]s?)\b", re.I)


def _apres_appel(texte):
    """Écoute permanente : la demande dite avec « Jarvis » (« » si on l'a seulement appelé), ou None si la phrase
    n'était pas pour lui."""
    m = _MOT_APPEL.search(texte)
    if not m:
        return None
    apres = texte[m.end():].strip(" ,.!?;:-")
    avant = texte[:m.start()].strip(" ,.!?;:-")
    return apres if len(apres) >= 2 else (avant if len(avant) >= 4 else "")


# « quelle heure est-il », mais aussi « quel heure » (comme Whisper l'écrit parfois), « donne-moi l'heure », « il est quelle heure »
_HEURE = re.compile(r"\bquel(?:le)?s? heures?\b|\b(?:donne|dis)[- ]moi l'heure\b|\bl'heure qu'il est\b|^(?:c'est quoi )?l'heure\b")


def _commande(texte):
    """Les réponses immédiates permises depuis la tablette : seulement celles qui ne font que renseigner."""
    import jarvis_commandes as c
    import jarvis_extras
    import jarvis_pratique
    t = c._propre(texte)
    essais = (
        lambda: c._heure() if _HEURE.search(t) and not re.search(r"\b(à|au|aux|en)\s+\w", t) else None,
        lambda: c._date() if re.search(r"\b(quel jour|quelle date|on est le combien|nous sommes le combien)\b", t)
        and not re.search(r"\b(sera|était|demain|hier)\b", t) else None,
        lambda: jarvis_extras.commande_heure_ailleurs(t),
        lambda: jarvis_pratique.commande_conversion(t),
        lambda: jarvis_pratique.commande_calcul(t),
        lambda: c._commande_meteo(t, texte),
    )
    for essai in essais:
        try:
            reponse = essai()
        except Exception as erreur:
            print("Tablette (commande) :", erreur)
            reponse = None
        if reponse:
            return reponse
    return None


# ----- Ce que la tablette fait elle-même, sans Claude : ouvrir une de ses applications, lancer une recherche

SITES_INTERDITS = r"amazon|le ?bon ?coin|leboncoin|cdiscount|vinted|ebay|aliexpress|temu|shein|fnac"   # profils enfant
_OUVRIR = re.compile(r"^(?:tu peux |peux-tu |est-ce que tu peux )?(?:ouvre|ouvrir|ouvres|lance|lancer|lances|d[ée]marre|"
                     r"d[ée]marrer|mets|va sur|aller sur)(?:[- ]moi)?\s+(?P<appli>(?:l'|la |le |mon |ma )?"
                     r"(?:application|appli|app|jeu)\s+)?(?:(?:le|la|les)\s+|l')?(?P<nom>.{2,40})$")
_YOUTUBE = re.compile(r"^(?:cherche|recherche|trouve|mets|montre)(?:[- ]moi)?\s+(?P<q>.{2,100}?)\s+sur youtube(?: kids)?$")
_IMAGES = re.compile(r"^(?:montre|cherche|trouve|affiche)(?:[- ]moi)?\s+(?:une |des |les |l')?(?:images?|photos?|dessins?) "
                     r"(?:de la |de l'|du |des |de |d')(?P<q>.{2,80})$")
_RECETTE = re.compile(r"\brecettes? (?:de la |de l'|du |des |de |d'|pour (?:faire |pr[ée]parer )?(?:la |le |les |des |un |une |du )?)"
                      r"(?P<q>.{3,60})$")
_WEB = re.compile(r"^(?:cherche|recherche|trouve|regarde|google)(?:[- ]moi)?\s+(?P<q>.{2,120}?)\s+(?:sur|dans) "
                  r"(?:internet|google|le web|le net|le navigateur)$")
_CHERCHE = re.compile(r"^(?:cherche|recherche|fais une recherche sur|google)(?:[- ]moi)?\s+(?P<q>.{2,120})$")


def _net(texte):
    t = texte.lower().replace("’", "'").strip()
    t = re.sub(r"^\W*(?:dis\W+)?jarvis\W+", "", t)
    t = re.sub(r"\W*(?:s'il te pla[iî]t|s'il vous pla[iî]t|stp|merci)\W*$", "", t)
    return t.strip(" .!?,;:«»\"")


_MOTS_PAQUET = frozenset("com android google apps app samsung sec client mediaclient mobile view thirdpartyclient net fr org "
                         "www free lite".split())
_AUTRES_NOMS = {"reglages": "parametres", "reglage": "parametres", "camera": "appareilphoto", "photo": "appareilphoto",
                "navigateur": "chrome", "internet": "chrome", "reveil": "horloge", "alarme": "horloge", "minuteur": "horloge",
                "fichiers": "mesfichiers", "playstore": "playstore", "magasin": "playstore"}


def _noms_appli(appli):
    """Les façons d'appeler une application : son nom à l'écran, puis ce que dit son nom technique (l'application
    « YT Kids » s'appelle com.google.android.apps.youtube.kids : on la trouve aussi en disant « YouTube Kids »)."""
    import jarvis_profils as jp
    noms = [(jp._simple(appli["nom"]).replace("-", ""), 0.0)]
    mots = [m for m in re.split(r"[^a-z0-9]+", appli["paquet"].lower()) if m and m not in _MOTS_PAQUET]
    if mots:
        noms.append(("".join(mots), 0.03))
        noms.extend((m, 0.06) for m in mots if len(m) >= 4)
    return [(n, malus) for n, malus in noms if n]


def _trouver_appli(nom, applis):
    """L'application de la tablette dont le nom ressemble à ce qui est demandé (None si aucune)."""
    import jarvis_profils as jp
    cherche = jp._simple(nom).replace("-", "")
    cherche = _AUTRES_NOMS.get(cherche, cherche)
    if len(cherche) < 2:
        return None
    meilleure, note = None, 0.0
    for appli in applis:
        for n, malus in _noms_appli(appli):
            ecart = abs(len(n) - len(cherche)) * 0.005
            if n == cherche:
                r = 1.0
            elif n.startswith(cherche) or cherche.startswith(n):
                r = 0.9 - ecart
            elif len(cherche) >= 4 and cherche in n:
                r = 0.82 - ecart
            elif malus:
                continue                             # un nom technique doit correspondre franchement, pas « à peu près »
            else:
                r = max(difflib.SequenceMatcher(None, cherche, n).ratio(),
                        difflib.SequenceMatcher(None, jp._son(nom), jp._son(appli["nom"])).ratio())
            if r - malus > note:
                meilleure, note = appli, r - malus
    return meilleure if note >= 0.78 else None


def _router(texte, profil, tablette=""):
    """(réponse, action) quand la tablette peut le faire elle-même, sinon (None, None)."""
    t = _net(texte)
    enfant = profil["enfant"]
    applis = applis_de(tablette)
    m = _OUVRIR.match(t)
    if m and applis:
        trouvee = _trouver_appli(m.group("nom"), applis)
        if trouvee:
            return f"J'ouvre {trouvee['nom']}.", {"type": "appli", "paquet": trouvee["paquet"], "nom": trouvee["nom"]}
        if m.group("appli"):
            return f"Je ne trouve pas l'application {m.group('nom')} sur cette tablette.", None
    elif m and m.group("appli"):
        return "Je ne connais pas encore les applications de cette tablette. Ferme et rouvre Jarvis, puis redemande-moi.", None
    if enfant and re.search(SITES_INTERDITS, t):
        return None, None

    def adresse(modele, quoi):
        return modele.format(urllib.parse.quote_plus(quoi))

    m = _YOUTUBE.match(t)
    if m:
        q = m.group("q")
        modele = "https://www.youtubekids.com/search?q={}" if enfant else "https://www.youtube.com/results?search_query={}"
        return f"Je cherche {q} sur YouTube.", {"type": "lien", "url": adresse(modele, q)}
    m = _IMAGES.match(t)
    if m:
        q = m.group("q")
        modele = "https://www.google.com/search?tbm=isch&q={}" + ("&safe=active" if enfant else "")
        return f"Voici des images de {q}.", {"type": "lien", "url": adresse(modele, q)}
    m = _RECETTE.search(t)
    if m:
        q = m.group("q")
        return (f"Voici des recettes de {q}.",
                {"type": "lien", "url": adresse("https://www.marmiton.org/recettes/recherche.aspx?aqt={}", q)})
    m = _WEB.match(t) or (None if enfant else _CHERCHE.match(t))
    if m:
        q = m.group("q")
        modele = "https://www.google.com/search?q={}" + ("&safe=active" if enfant else "")
        return f"Je cherche {q} sur Internet.", {"type": "lien", "url": adresse(modele, q)}
    return None, None


def _fichier_applis():
    return os.path.join(DOSSIER, "applications.json")


def _lire_applis():
    """Les listes d'applications des tablettes, relues une fois : elles survivent à un redémarrage de Jarvis."""
    global _applis_lues
    if _applis_lues == DOSSIER:
        return
    _applis_lues = DOSSIER
    try:
        with open(_fichier_applis(), encoding="utf-8") as f:
            gardees = json.load(f)
        _applis.clear()
        _applis.update({str(t): l for t, l in gardees.items() if isinstance(l, list)})
    except (OSError, ValueError, AttributeError):
        pass


def applis_de(tablette):
    with _verrou:
        _lire_applis()
        return _applis.get(str(tablette or "")[:40]) or []


def garder_applis(tablette, applis):
    """La liste des applications installées sur une tablette, envoyée par son application Jarvis."""
    propres = []
    for appli in applis if isinstance(applis, list) else []:
        if isinstance(appli, dict) and appli.get("nom") and appli.get("paquet"):
            propres.append({"nom": str(appli["nom"])[:60], "paquet": str(appli["paquet"])[:120]})
    with _verrou:
        _lire_applis()
        if len(_applis) > 20:
            _applis.clear()
        cle = str(tablette or "")[:40]
        change = _applis.get(cle) != propres[:400]
        _applis[cle] = propres[:400]
        if change:
            print(f"Tablette : {len(propres)} applications connues sur cette tablette.")
            try:
                os.makedirs(DOSSIER, exist_ok=True)
                with open(_fichier_applis(), "w", encoding="utf-8") as f:
                    json.dump(_applis, f, ensure_ascii=False)
            except OSError as erreur:
                print("Tablette (applications) :", erreur)
    return {"ok": True, "applis": len(propres)}


def _propre(reponse):
    """La réponse de Claude, sans mise en forme ni lignes réservées à Jarvis."""
    reponse = re.sub(r"(?m)^\s*(?:RETENIR|OUBLIER|HISTOIRE)\s*:.*$", "", reponse)
    return re.sub(r"\s*\n\s*", " ", re.sub(r"[*_#`>]", "", reponse)).strip()


def _son(texte):
    """La voix de Jarvis pour ce texte : un MP3 écrit en base64, joint à la réponse (None si c'est impossible :
    la tablette lit alors la réponse avec sa propre voix)."""
    fichier = os.path.join(tempfile.gettempdir(), f"jarvis_tablette_{secrets.token_hex(6)}.mp3")
    try:
        import jarvis_voix
        asyncio.run(jarvis_voix._generer(jarvis_voix.sans_balises_voix(texte)[:1500], fichier))
        with open(fichier, "rb") as f:
            son = f.read()
    except Exception as erreur:
        print("Tablette (voix) :", erreur)
        return None
    finally:
        try:
            os.remove(fichier)
        except OSError:
            pass
    return base64.b64encode(son).decode("ascii") if son else None


# ----- Historique : les demandes de chaque profil, gardées sur ce PC

_EXTENSIONS = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a", "audio/mpeg": ".mp3",
               "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/aac": ".aac", "audio/3gpp": ".3gp"}


def _compacter(son):
    """Le son brut envoyé par l'application (WAV), réécrit dix fois plus petit (Opus) pour l'historique."""
    import av
    import numpy as np
    pcm = (np.clip(_decoder(son), -1, 1) * 32767).astype(np.int16)
    tampon = io.BytesIO()
    with av.open(tampon, "w", format="ogg") as sortie:
        flux = sortie.add_stream("libopus", rate=16000)
        flux.bit_rate = 24000
        pas = 320                                    # 20 millièmes de seconde : ce que l'encodeur attend
        for debut in range(0, len(pcm), pas):
            morceau = pcm[debut:debut + pas]
            if len(morceau) < pas:
                morceau = np.pad(morceau, (0, pas - len(morceau)))
            trame = av.AudioFrame.from_ndarray(morceau.reshape(1, -1), format="s16", layout="mono")
            trame.sample_rate = 16000
            trame.pts = debut
            for paquet in flux.encode(trame):
                sortie.mux(paquet)
        for paquet in flux.encode(None):
            sortie.mux(paquet)
    return tampon.getvalue()


def _garder(ident, texte, reponse, son=None, genre="", origine="", voix_reconnue=None):
    """Ajoute cette demande à l'historique du profil, et efface les plus anciennes au-delà de la limite."""
    try:
        dossier = os.path.join(DOSSIER, "historique", re.sub(r"[^\w\-]", "_", ident))
        with _verrou_historique:
            os.makedirs(dossier, exist_ok=True)
            journal = os.path.join(dossier, "journal.jsonl")
            ligne = {"quand": time.strftime("%Y-%m-%d %H:%M:%S"), "demande": texte, "reponse": reponse,
                     "origine": origine}
            if voix_reconnue:
                ligne["voix_reconnue"] = voix_reconnue
            if son:
                extension = _EXTENSIONS.get(genre.split(";")[0].strip().lower(), ".son")
                if extension == ".wav":
                    try:
                        son, extension = _compacter(son), ".ogg"
                    except Exception as erreur:
                        print("Tablette (son gardé tel quel) :", erreur)
                nom = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(3) + extension
                with open(os.path.join(dossier, nom), "wb") as f:
                    f.write(son)
                ligne["son"] = nom
            try:
                with open(journal, encoding="utf-8") as f:
                    lignes = [l for l in f.read().splitlines() if l.strip()]
            except OSError:
                lignes = []
            lignes.append(json.dumps(ligne, ensure_ascii=False))
            for ancienne in lignes[:-HISTORIQUE_MAX]:
                try:
                    vieux = json.loads(ancienne).get("son")
                    if vieux:
                        os.remove(os.path.join(dossier, os.path.basename(vieux)))
                except (OSError, ValueError):
                    pass
            with open(journal + ".tmp", "w", encoding="utf-8") as f:
                f.write("\n".join(lignes[-HISTORIQUE_MAX:]) + "\n")
            os.replace(journal + ".tmp", journal)
    except Exception as erreur:
        print("Tablette (historique) :", erreur)


def repondre(texte=None, son=None, jeton=None, tablette="", genre="", muet=False, veille="", etapes=False):
    """Traite une demande de la tablette. Renvoie {"entendu", "reponse", "voix", ...} ou {"erreur"}.
    veille : la phrase vient de l'écoute permanente de l'application. « 1 » : elle n'est une demande que si elle
    contient « Jarvis » (sinon {"ignore"} : elle n'est ni traitée, ni gardée, ni écrite dans le journal) ;
    « suite » : Jarvis vient de poser une question, la phrase est sa réponse.
    etapes : comme sur le PC, la tablette affiche d'abord la phrase comprise, puis la réponse. On renvoie tout de
    suite {"entendu", "attente"} ; la réponse se demande ensuite avec resultat(), et la voix avec voix()."""
    if veille and son is not None:
        resultat_ = _repondre(texte, son, jeton, tablette, genre, muet, veille, etapes)
        if resultat_.get("erreur") and "entendu" not in resultat_ and "session" not in resultat_:
            return {"ignore": True}                  # rien de clair, ou Jarvis occupé : la tablette n'affiche rien
        return resultat_
    return _repondre(texte, son, jeton, tablette, genre, muet, "", etapes)


def _nouvelle_tache():
    """Une demande en cours de traitement : la tablette vient chercher sa réponse, puis sa voix."""
    maintenant = time.time()
    with _verrou:
        for vieille in [i for i, t in _taches.items() if maintenant - t["quand"] > 300]:
            del _taches[vieille]
        numero = secrets.token_urlsafe(12)
        _taches[numero] = {"quand": maintenant, "fini": threading.Event(), "resultat": None,
                           "voix_prete": threading.Event(), "voix": None}
    return numero, _taches[numero]


def resultat(numero):
    """La réponse d'une demande envoyée par étapes (attend qu'elle soit prête)."""
    tache = _taches.get(str(numero or ""))
    if tache is None or not tache["fini"].wait(DELAI_CLAUDE + 30):
        return {"erreur": "Je n'ai pas réussi à répondre. Essaie encore."}
    return tache["resultat"]


def voix(numero):
    """La voix de Jarvis pour la réponse d'une demande envoyée par étapes (attend qu'elle soit fabriquée)."""
    tache = _taches.get(str(numero or ""))
    if tache is None:
        return {"voix": None}
    tache["voix_prete"].wait(25)
    _taches.pop(str(numero), None)
    return {"voix": tache["voix"]}


def _traiter(profil, texte, son, genre, muet, tablette, reconnue, debut, tache=None):
    """La réponse à une demande comprise : commande immédiate, action sur la tablette, ou Claude."""
    action = None
    reponse = _commande(texte)
    if not reponse:
        reponse, action = _router(texte, profil, tablette)
    if not reponse:
        if _claude is None:
            return {"entendu": texte, "erreur": "Je ne peux pas répondre pour le moment."}
        reponse, erreur = _conversation(profil["id"]).demander(texte, delai=DELAI_CLAUDE)
        if erreur:                                   # le détail (limite atteinte, Claude absent...) reste dans le journal du PC
            print("Tablette, Claude n'a pas répondu :", reponse)
            _garder(profil["id"], texte, "", son, genre, "voix" if son else "écrit", reconnue)
            return {"entendu": texte, "erreur": "Je n'arrive pas à réfléchir pour le moment. Réessaie un peu plus tard."}
        reponse = _propre(reponse) or "Je n'ai pas de réponse, tu peux me redemander ?"
    print(f"Tablette, réponse ({time.time() - debut:.1f} s) :", reponse[:300])
    resultat_ = {"entendu": texte, "reponse": reponse, "voix": None}
    if action:
        resultat_["action"] = action
    if tache is not None and not muet:               # le texte part tout de suite ; la voix suit dès qu'elle est fabriquée

        def fabriquer():
            try:
                tache[1]["voix"] = _son(reponse)
            finally:
                tache[1]["voix_prete"].set()
        resultat_["voix_attente"] = tache[0]
        threading.Thread(target=fabriquer, daemon=True).start()
    elif not muet:
        resultat_["voix"] = _son(reponse)
    garder = (profil["id"], texte, reponse, son, genre, "voix" if son else "écrit", reconnue)
    if tache is not None:                            # la réponse n'attend pas l'écriture de l'historique
        threading.Thread(target=_garder, args=garder, daemon=True).start()
    else:
        _garder(*garder)
    return resultat_


def _repondre(texte, son, jeton, tablette, genre, muet, veille, etapes=False):
    ident = _session(jeton)
    if ident is None:
        profil = _profil(None)                       # sans session : le profil par défaut, s'il s'ouvre sans code
        if jeton or profil is None or not profil["enfant"]:
            return {"erreur": "Choisis ton profil pour continuer.", "session": "finie"}
    else:
        profil = _profil(ident)
        if profil is None:
            return {"erreur": "Ce profil n'existe plus.", "session": "finie"}
    with _verrou:
        verrou = _verrous.setdefault(profil["id"], threading.Lock())
    if not verrou.acquire(blocking=False):
        return {"erreur": "Une seconde, je finis de répondre."}
    garde = False                                    # vrai quand un fil termine le travail : c'est lui qui rend le verrou
    try:
        debut = time.time()
        suite = {}
        reconnue = None
        if son is not None:
            try:
                audio = _decoder(son)
                texte = _transcrire(audio, _amorce())
                if veille:
                    _essai(audio, texte)
            except Exception as erreur:
                print("Tablette (son illisible) :", erreur)
                return {"erreur": "Je n'ai pas réussi à écouter. Essaie encore, ou écris ta question."}
            if texte is None:
                return {"erreur": "Je ne peux pas encore écouter. Écris ta question, ou réessaie dans un instant."}
            if not texte:
                return {"erreur": "Je n'ai rien entendu. Appuie sur le rond et parle bien fort."}
            if veille == "1":
                texte = _apres_appel(texte)
                if texte is None:
                    print(f"Tablette (écoute permanente) : une phrase sans « Jarvis », ignorée ({len(audio) / 16000:.1f} s).")  # jamais ce qui a été dit
                    return {"ignore": True}
                if not texte:
                    return {"ecoute": True}          # « Jarvis » tout seul : la tablette écoute la suite
            reconnue = _reconnaitre(audio, texte)
            autre = _profil(reconnue) if reconnue and reconnue != profil["id"] else None
            if autre is not None and autre["enfant"]:            # un enfant du foyer : la tablette passe sur son profil
                profil = autre
                suite["bascule"] = {"profil": autre["id"], "jeton": _ouvrir_session(autre["id"])}
            elif autre is not None:                              # un adulte : proposé seulement, le code reste demandé
                suite["propose"] = autre["id"]
        texte = " ".join(str(texte or "").split())[:LONGUEUR_MAX]
        if not texte:
            return {"erreur": "Je n'ai rien reçu."}
        print(f"Tablette ({profil['prenom'] or 'sans prénom'}), demande ({time.time() - debut:.1f} s) :", texte)
        changement = _changer_profil(texte, profil)
        if changement:                               # on a dit qui on est : pas besoin de Claude
            print("Tablette, réponse :", changement[0])
            if "bascule" in changement[1]:
                _chauffer(changement[1]["bascule"]["profil"])
            return {"entendu": texte, "reponse": changement[0], "voix": None if muet else _son(changement[0]),
                    **suite, **changement[1]}
        if not etapes:
            return {**_traiter(profil, texte, son, genre, muet, tablette, reconnue, debut), **suite}
        tache = _nouvelle_tache()

        def travail():
            try:
                tache[1]["resultat"] = _traiter(profil, texte, son, genre, muet, tablette, reconnue, debut, tache)
            except Exception as erreur:
                print("Tablette :", erreur)
                tache[1]["resultat"] = {"entendu": texte, "erreur": "J'ai eu un souci. Essaie encore."}
            finally:
                verrou.release()
                tache[1]["fini"].set()
        garde = True
        threading.Thread(target=travail, daemon=True).start()
        return {"entendu": texte, "attente": tache[0], **suite}
    finally:
        if not garde:
            verrou.release()


_CEST = re.compile(r"^(?:non\W+|mais\W+|euh\W+)*(?:c'est moi\W+|moi c'est|c'est|je suis|ici)\s+(?P<nom>[\w\-]{2,20})\W*$")
_PROFIL = re.compile(r"\b(?:passe|passer|repasse|mets|mettre|va|aller|change|changer|bascule|ouvre|ouvrir|prends|reviens|retourne)\b"
                     r".*\bprofils?\b(?:\s+(?:de|du|à|a)\s+|\s+d')?(?P<nom>[\w\-]{2,20})?\W*$")


def _changer_profil(texte, profil):
    """« c'est Léo », « je suis Marie », « passe sur le profil de Léo », « change de profil » : comme sur le PC, on dit qui
    on est. Renvoie None si la phrase ne parle pas de ça, sinon (réponse à dire, ce que la tablette doit faire) :
    un enfant passe tout de suite sur son profil ; un adulte doit toujours taper son code."""
    import jarvis_profils as jp
    t = _net(texte)
    m = _CEST.match(t) or _PROFIL.search(t)
    if not m:
        return None
    nom = m.group("nom") or ""
    liste, _ = profils()
    trouve, note = None, 0.0
    for p in liste:
        if not p["prenom"]:
            continue
        r = max(difflib.SequenceMatcher(None, jp._simple(nom), jp._simple(p["prenom"])).ratio(),
                difflib.SequenceMatcher(None, jp._son(nom), jp._son(p["prenom"])).ratio())
        if r > note:
            trouve, note = p, r
    if note < 0.72:
        if m.re is _PROFIL:                          # « change de profil » : la tablette montre la liste
            return "Choisis ton profil.", {"profils": True}
        return None                                  # « c'est super » : ce n'est pas un prénom du foyer
    if trouve["id"] == profil["id"]:
        return f"Tu es déjà sur ton profil, {trouve['prenom']}.", {}
    if trouve["enfant"]:
        return (f"Bonjour {trouve['prenom']} ! Tu es sur ton profil.",
                {"bascule": {"profil": trouve["id"], "jeton": _ouvrir_session(trouve["id"])}})
    return f"Bonjour {trouve['prenom']}. Tape ton code pour ouvrir ton profil.", {"code": trouve["id"]}


def _chauffer(ident):
    """Dès qu'un profil s'ouvre sur une tablette, sa conversation avec Claude est préparée : la première question
    n'attend plus le démarrage de Claude (rien n'est envoyé à Claude, donc rien n'est consommé)."""
    def travail():
        try:
            conversation = _conversation(ident)
            if conversation.verrou.acquire(blocking=False):
                try:
                    if conversation.proc is None or conversation.proc.poll() is not None:
                        conversation.demarrer()
                finally:
                    conversation.verrou.release()
        except Exception:
            pass                                     # Jarvis pas encore prêt : Claude démarrera à la première question
    if _claude is not None:
        threading.Thread(target=travail, daemon=True).start()


# ---------- L'application (une page web) ----------

def _icone(taille=192):
    """L'icône de l'application (PNG) : un petit réacteur, dessiné ici pour n'avoir aucun fichier à fournir."""
    import numpy as np
    y, x = np.mgrid[0:taille, 0:taille]
    d = np.hypot(x - taille / 2 + 0.5, y - taille / 2 + 0.5) / (taille / 2)
    force = (np.clip(1 - np.abs(d - 0.62) / 0.07, 0, 1) + np.clip(1 - d / 0.2, 0, 1)
             + 0.25 * np.clip(1 - np.abs(d - 0.62) / 0.25, 0, 1))
    force = np.clip(force, 0, 1)[..., None]
    image = (np.array((5, 9, 14)) * (1 - force) + np.array((79, 242, 220)) * force).astype(np.uint8)
    lignes = b"".join(b"\x00" + image[i].tobytes() for i in range(taille))

    def bloc(nom, donnees):
        return struct.pack(">I", len(donnees)) + nom + donnees + struct.pack(">I", zlib.crc32(nom + donnees) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", struct.pack(">IIBBBBB", taille, taille, 8, 2, 0, 0, 0))
            + bloc(b"IDAT", zlib.compress(lignes, 9)) + bloc(b"IEND", b""))


def _silence():
    """Un dixième de seconde de silence (WAV) : joué au premier appui, il autorise ensuite la page à parler."""
    son = b"\x80" * 800
    entete = (b"RIFF" + struct.pack("<I", 36 + len(son)) + b"WAVEfmt " + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 8000, 1, 8)
              + b"data" + struct.pack("<I", len(son)))
    return "data:audio/wav;base64," + base64.b64encode(entete + son).decode("ascii")


PAGE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Jarvis</title>
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Jarvis">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="theme-color" content="#05090e">
<meta name="referrer" content="no-referrer">
<link rel="icon" href="/icone.png">
<link rel="apple-touch-icon" href="/icone.png">
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;margin:0}
body{background:#05090e;color:#e8f4ff;font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif;display:flex;flex-direction:column;
 align-items:center;justify-content:space-between;padding:env(safe-area-inset-top) 18px env(safe-area-inset-bottom);
 overflow:hidden;touch-action:manipulation;--p1:#ff2e97;--p2:#ff8c42;--p3:#9d4dff;--c:var(--p1);--a:var(--p1);--b:var(--p2);--d:var(--p3);
 user-select:none;-webkit-user-select:none}
body.ecoute{--c:#4ff2dc;--a:#4ff2dc;--b:#4ff2dc;--d:#4ff2dc} body.reflechit{--c:#ffa53a;--a:#ffa53a;--b:#ffa53a;--d:#ffa53a}
body.repond{--c:#4fb4ff;--a:#4fb4ff;--b:#4fb4ff;--d:#4fb4ff}
body.nuit{background:#000} body.nuit>*{filter:brightness(.45)}
button{font-family:inherit;color:inherit}
#haut{width:100%;max-width:640px;display:flex;align-items:center;justify-content:space-between;margin-top:10px;min-height:44px}
#qui{font-size:18px;font-weight:600;padding:10px 20px;border-radius:22px;border:1px solid #233447;background:#0b131d;color:var(--p1);
 max-width:60%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;visibility:hidden}
#roue{width:44px;height:44px;border-radius:50%;border:1px solid #233447;background:#0b131d;padding:9px;visibility:hidden;position:relative}
#roue svg{width:100%;height:100%;display:block;fill:var(--p1)}
#roue.neuf:after{content:"";position:absolute;top:2px;right:2px;width:11px;height:11px;border-radius:50%;background:#ffa53a}
#etat{margin-top:6px;font-size:15px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:var(--c);transition:color .3s}
#scene{position:relative;flex:none}
#rond{position:relative;display:block;width:54vmin;height:54vmin;max-width:330px;max-height:330px;min-width:170px;min-height:170px;border:0;
 border-radius:50%;background:none;padding:0;cursor:pointer;--n:0;transform:scale(calc(1 + var(--n) * .08));transition:transform .08s}
#rond:before{content:"";position:absolute;inset:0;border-radius:50%;
 background:conic-gradient(from 0deg,var(--a),transparent 28%,var(--b) 50%,transparent 78%,var(--a));animation:tour 9s linear infinite;
 filter:drop-shadow(0 0 14px var(--c));transition:filter .3s}
#rond:after{content:"";position:absolute;inset:9px;border-radius:50%;
 background:radial-gradient(circle,var(--d) 0,var(--d) 7%,#0d1622 9%,#080e16 55%,#05090e 100%)}
body.ecoute #rond:before{animation-duration:3s} body.reflechit #rond:before{animation-duration:1s} body.repond #rond:before{animation-duration:4s}
body.repond #rond{animation:voix 1.1s ease-in-out infinite}
@keyframes tour{to{transform:rotate(360deg)}}
@keyframes voix{50%{transform:scale(1.05)}}
.et{position:absolute;width:10px;height:10px;background:#fff;border-radius:50%;opacity:0;pointer-events:none;display:none;
 box-shadow:0 0 8px 2px var(--p3),0 0 16px 4px var(--p1);animation:brille 2.4s ease-in-out infinite}
body.paillettes .et{display:block}
.et:nth-child(2){top:2%;left:16%;animation-delay:0s} .et:nth-child(3){top:12%;right:4%;animation-delay:.5s;width:7px;height:7px}
.et:nth-child(4){bottom:8%;left:2%;animation-delay:1s;width:7px;height:7px} .et:nth-child(5){bottom:0;right:14%;animation-delay:1.5s}
.et:nth-child(6){top:46%;left:-5%;animation-delay:.8s;width:6px;height:6px} .et:nth-child(7){top:40%;right:-5%;animation-delay:1.9s;width:6px;height:6px}
@keyframes brille{0%,100%{opacity:0;transform:scale(.3)}50%{opacity:1;transform:scale(1)}}
#textes{width:100%;max-width:640px;min-height:22vh;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center}
#entendu{font-size:15px;color:#7d93a8;min-height:20px;margin-bottom:8px}
#bulle{font-size:21px;line-height:1.4;max-height:26vh;overflow-y:auto;-webkit-overflow-scrolling:touch;padding:0 4px}
#bulle.demande{color:#9fb4c8} #bulle.erreur{color:#ffb38a} #bulle.calme{color:#7d93a8;font-size:17px}
.pastille{display:none;margin-top:12px;font-size:16px;padding:10px 18px;border-radius:22px;border:1px solid var(--p1);background:#0b131d;color:var(--p1)}
#forme{width:100%;max-width:640px;display:flex;gap:10px;margin:10px 0 18px}
#champ{flex:1;min-width:0;font-size:17px;padding:13px 16px;border-radius:14px;border:1px solid #233447;background:#0b131d;color:#e8f4ff;
 outline:none;user-select:text;-webkit-user-select:text}
#champ:focus{border-color:var(--c)}
#envoi{font-size:17px;padding:0 20px;border-radius:14px;border:0;background:var(--c);color:#05090e;font-weight:700;transition:background .3s}
button:disabled,input:disabled{opacity:.4}
#voile{position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(3,6,10,.94);display:none;align-items:center;justify-content:center;
 padding:calc(env(safe-area-inset-top) + 14px) 14px calc(env(safe-area-inset-bottom) + 14px);z-index:5}
#voile.ouvert{display:flex}
.panneau{display:none;width:100%;max-width:440px;max-height:100%;overflow-y:auto;-webkit-overflow-scrolling:touch;background:#0b131d;
 border:1px solid #233447;border-radius:20px;padding:20px 18px}
.panneau.ouvert{display:block}
.panneau h2{margin:0 0 6px;font-size:21px;color:var(--p1);text-align:center}
.panneau p{margin:8px 0;font-size:16px;line-height:1.45;color:#b9c9d8;text-align:center}
.panneau p.petit{font-size:13.5px;color:#7d93a8}
.ligne{display:flex;align-items:center;width:100%;min-height:54px;margin-top:10px;padding:10px 16px;border-radius:14px;border:1px solid #233447;
 background:#0e1825;font-size:17px;text-align:left;gap:12px}
.ligne.choisi{border-color:var(--p1)}
.ligne .droite{margin-left:auto;color:#7d93a8;font-size:14px;white-space:nowrap}
.ligne.plein{justify-content:center;background:var(--p1);border-color:var(--p1);color:#05090e;font-weight:700}
.ligne.sobre{justify-content:center;color:#9fb4c8}
.ligne small{font-size:13px;color:#7d93a8}
.ligne>.pastilles:last-child{margin-left:auto}
.ligne input[type=range]{flex:1;min-width:0;accent-color:var(--p1)}
.bascule{margin-left:auto;width:50px;height:28px;border-radius:14px;background:#233447;position:relative;flex:none;transition:background .2s}
.bascule:after{content:"";position:absolute;top:3px;left:3px;width:22px;height:22px;border-radius:50%;background:#e8f4ff;transition:left .2s}
.actif .bascule{background:var(--p1)} .actif .bascule:after{left:25px}
.points{display:flex;justify-content:center;gap:16px;margin:16px 0 6px}
.points i{width:16px;height:16px;border-radius:50%;border:2px solid var(--p1)} .points i.mis{background:var(--p1)}
#msg_code{min-height:44px;color:#ffb38a}
#touches{display:flex;flex-wrap:wrap;justify-content:center;gap:12px;max-width:300px;margin:0 auto}
#touches button{width:84px;height:62px;border-radius:16px;border:1px solid #233447;background:#0e1825;font-size:26px}
#touches button.sobre{font-size:14px;color:#9fb4c8}
.pastilles{display:flex;gap:5px;flex:none} .pastilles i{width:20px;height:20px;border-radius:50%}
.nuancier{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 4px;justify-content:center}
.nuancier button{width:34px;height:34px;border-radius:50%;border:3px solid transparent;padding:0}
.nuancier button.choisi{border-color:#fff}
.titre{font-size:14px;color:#7d93a8;margin:16px 0 0;text-align:center;text-transform:uppercase;letter-spacing:1.5px}
</style>
</head>
<body class="veille">
<div id="haut">
<button id="qui" type="button"></button>
<button id="roue" type="button" aria-label="Réglages"><svg viewBox="0 0 24 24"><path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z"/></svg></button>
</div>
<div id="etat">Jarvis</div>
<div id="scene"><button id="rond" type="button" aria-label="Parler à Jarvis"></button><i class="et"></i><i class="et"></i><i class="et"></i><i class="et"></i><i class="et"></i><i class="et"></i></div>
<div id="textes"><div id="entendu"></div><div id="bulle" class="calme"></div>
<button id="ouvrir" class="pastille" type="button">Ouvrir</button><button id="propose" class="pastille" type="button"></button></div>
<form id="forme" autocomplete="off">
<input id="champ" type="text" maxlength="400" enterkeyhint="send" placeholder="Ou écris ici…">
<button id="envoi" type="submit">Envoyer</button>
</form>
<audio id="lecteur" preload="auto"></audio>

<div id="voile">
<div class="panneau" id="p_bienvenue">
 <h2>Bienvenue sur Jarvis</h2>
 <p id="donnees1"></p>
 <p class="petit" id="donnees2"></p>
 <button class="ligne plein" type="button" id="b_compris">J'ai compris</button>
</div>
<div class="panneau" id="p_profils">
 <h2>Qui es-tu ?</h2>
 <div id="liste_profils"></div>
 <button class="ligne sobre" type="button" id="b_profils_fermer">Annuler</button>
</div>
<div class="panneau" id="p_code">
 <h2 id="titre_code"></h2>
 <div class="points" id="points"><i></i><i></i><i></i><i></i></div>
 <p id="msg_code"></p>
 <div id="touches"></div>
 <button class="ligne sobre" type="button" id="b_autre">Changer de profil</button>
</div>
<div class="panneau" id="p_reglages">
 <h2>Réglages</h2>
 <button class="ligne" type="button" id="r_profil"><span>Profil</span><span class="droite" id="r_profil_nom"></span></button>
 <div class="ligne"><span>Volume</span><input id="r_volume" type="range" min="0" max="100" step="5"></div>
 <button class="ligne" type="button" id="r_veille"><span>Écoute permanente<br><small>Dis « Jarvis », puis ta demande</small></span><span class="bascule"></span></button>
 <button class="ligne" type="button" id="r_muet"><span>Mode silencieux</span><span class="bascule"></span></button>
 <button class="ligne" type="button" id="r_nuit"><span>Mode nuit</span><span class="bascule"></span></button>
 <button class="ligne" type="button" id="r_nouvelle"><span>Nouvelle conversation</span></button>
 <button class="ligne" type="button" id="r_couleurs"><span>Mes couleurs</span><span class="pastilles" id="r_pastilles"></span></button>
 <button class="ligne" type="button" id="r_code"><span>Changer mon code</span></button>
 <button class="ligne" type="button" id="r_maj"><span>Mise à jour</span><span class="droite" id="r_maj_etat"></span></button>
 <button class="ligne" type="button" id="r_installer"><span>Installer l'application</span></button>
 <button class="ligne" type="button" id="r_apropos"><span>À propos</span></button>
 <button class="ligne" type="button" id="r_desinstaller"><span>Désinstaller</span></button>
 <button class="ligne plein" type="button" id="r_fermer">Fermer</button>
</div>
<div class="panneau" id="p_couleurs">
 <h2>Mes couleurs</h2>
 <div id="liste_palettes"></div>
 <div class="titre">Ou choisis tes trois couleurs</div>
 <div class="nuancier" id="n0"></div><div class="nuancier" id="n1"></div><div class="nuancier" id="n2"></div>
 <button class="ligne plein" type="button" id="b_couleurs_ok">Garder mes trois couleurs</button>
 <button class="ligne sobre" type="button" id="b_couleurs_retour">Retour</button>
</div>
<div class="panneau" id="p_apropos">
 <h2>À propos</h2>
 <p id="versions"></p>
 <p id="donnees3"></p>
 <p class="petit" id="donnees4"></p>
 <button class="ligne sobre" type="button" id="b_apropos_retour">Retour</button>
</div>
<div class="panneau" id="p_installer">
 <h2>L'application Jarvis</h2>
 <p>Avec l'application, Jarvis peut ouvrir les applications de cette tablette et se met à jour tout seul.</p>
 <p id="donnees5"></p>
 <a class="ligne plein" id="lien_apk" href="/jarvis.apk" style="text-decoration:none">1. Télécharger et installer</a>
 <p class="petit">Android demande d'autoriser l'installation : accepte, puis reviens sur cette page.</p>
 <a class="ligne plein" id="lien_appli" href="#" style="text-decoration:none">2. Ouvrir dans l'application</a>
 <button class="ligne sobre" type="button" id="b_installer_retour">Plus tard</button>
</div>
<div class="panneau" id="p_message">
 <p id="texte_message"></p>
 <button class="ligne plein" type="button" id="b_message_ok">D'accord</button>
</div>
</div>
<script>
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var rond = $("rond"), etat = $("etat"), bulle = $("bulle"), entendu = $("entendu"), champ = $("champ"),
      forme = $("forme"), lecteur = $("lecteur"), voile = $("voile");
  var NOMS = { veille: "Jarvis", ecoute: "Je t'écoute", reflechit: "Je réfléchis", repond: "Je réponds" };
  var NUANCES = ["#ff2e97", "#ff5fb7", "#ff3b3b", "#ff8c42", "#ffd23f", "#a3e635", "#3ddc84", "#00e1b4", "#00b4d8", "#3fa9ff",
                 "#5b6cff", "#9d4dff", "#c77dff", "#ffffff"];
  var appli = window.JarvisApp || null;
  var mode = "veille", cle = null, debloque = false, serveur = null, profil = null, jeton = null, tablette = "";
  var flux = null, rec = null, morceaux = [], ctx = null, source = null, minuterie = null, adresseSon = null;
  var reglages = { volume: 100, muet: false, nuit: false, veille: true };
  var enVol = false, enAttente = null, voixAttendue = null, parEtapes = false, suiteFin = 0, veilleDite = null, attentiveDite = null, questionEnAttente = false;
  var saisie = "", etapeCode = "", profilCode = null, premierCode = "", ancienCode = null, compteur = null;
  var dernier = null, reprise = null, aFaire = null, lienAttente = null, choix = ["", "", ""], apresMessage = null;

  function lire(nom) { try { return localStorage.getItem(nom); } catch (e) { return null; } }
  function ecrire(nom, valeur) { try { localStorage.setItem(nom, valeur); } catch (e) {} }
  function versionAppli() { try { return appli ? parseInt(appli.version(), 10) || 0 : 0; } catch (e) { return 0; } }

  try {
    var m = location.hash.match(/cle=([\w-]+)/);
    if (m) { cle = m[1]; }
    if (cle) { localStorage.setItem("jarvis_cle", cle); } else { cle = localStorage.getItem("jarvis_cle"); }
  } catch (e) { /* stockage refusé : la clé de l'adresse suffit */ }
  tablette = lire("jarvis_tablette") || "";
  if (!tablette) { tablette = "t" + Math.random().toString(36).slice(2, 12); ecrire("jarvis_tablette", tablette); }
  try { var r0 = JSON.parse(lire("jarvis_reglages") || "{}"); for (var k in reglages) { if (r0[k] !== undefined) { reglages[k] = r0[k]; } } } catch (e) {}

  function mettre(nouveau) {
    mode = nouveau;
    var c = document.body.className.replace(/\b(veille|ecoute|reflechit|repond)\b/g, "").replace(/\s+/g, " ").trim();
    document.body.className = (nouveau + " " + c).trim();
    etat.textContent = NOMS[nouveau];
    if (nouveau !== "ecoute") { rond.style.setProperty("--n", 0); }
    majVeille();
  }
  // Écoute permanente (dans l'application) : le micro reste ouvert tant que Jarvis attend, et il suffit de dire « Jarvis ».
  function peutVeiller() { return !!(appli && appli.ecouteVeille); }
  function majVeille() {
    if (!peutVeiller()) { return; }
    var voulue = !!(reglages.veille && profil && !document.hidden && !rond.disabled);
    var attentive = mode === "veille" && voile.className !== "ouvert";
    try {
      if (!appli.attentif) { voulue = voulue && attentive; }       // ancienne application : le micro est coupé hors attente
      else if (attentive !== attentiveDite) { attentiveDite = attentive; appli.attentif(attentive); }
      if (voulue !== veilleDite) { veilleDite = voulue; appli.ecouteVeille(voulue); }
    } catch (e) {}
  }
  function classe(nom, oui) {
    var c = (" " + document.body.className + " ").replace(" " + nom + " ", " ").trim();
    document.body.className = oui ? (c + " " + nom).trim() : c;
  }
  function montrer(texte, genre) { bulle.textContent = texte; bulle.className = genre || ""; bulle.scrollTop = 0; }
  function natif() { return !!(appli && appli.ecouter); }      // l'application écoute elle-même, avec le micro de la tablette
  function peutEcouter() {
    return natif() || !!(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }
  function accueil() {
    var prenom = profil ? profil.prenom : "";
    montrer((prenom ? "Bonjour " + prenom + " ! " : "Bonjour ! ")
      + (peutVeiller() && reglages.veille ? "Dis « Jarvis », puis ta demande. Tu peux aussi appuyer sur le rond."
        : peutEcouter() ? "Appuie sur le rond et parle-moi." : "Écris-moi ta question juste en dessous."), "calme");
  }
  function bloquer(message) {
    fermer();
    montrer(message, "erreur");
    rond.disabled = champ.disabled = $("envoi").disabled = true;
    if (appli && appli.oublier) {
      $("ouvrir").textContent = "Relier de nouveau la tablette";
      $("ouvrir").style.display = "inline-block";
      lienAttente = null;
      $("ouvrir").onclick = function () { try { appli.oublier(); } catch (e) {} };
    }
  }

  // ----- Panneaux
  function ouvrir(id) {
    var p = voile.querySelectorAll(".panneau");
    for (var i = 0; i < p.length; i++) { p[i].className = "panneau" + (p[i].id === id ? " ouvert" : ""); }
    voile.className = "ouvert";
    majVeille();
    if (compteur && id !== "p_code") { clearInterval(compteur); compteur = null; }
  }
  function fermer() { voile.className = ""; if (compteur) { clearInterval(compteur); compteur = null; } majVeille(); }
  function message(texte, ensuite) { $("texte_message").textContent = texte; apresMessage = ensuite || null; ouvrir("p_message"); }
  $("b_message_ok").onclick = function () { var f = apresMessage; apresMessage = null; if (f) { f(); } else { fermer(); } };

  function api(chemin, corps, suite) {
    var entetes = { "X-Jarvis-Cle": cle || "", "X-Jarvis-Tablette": tablette };
    if (jeton) { entetes["X-Jarvis-Profil"] = jeton; }
    var options = { headers: entetes };
    if (corps !== null) { options.method = "POST"; entetes["Content-Type"] = "application/json"; options.body = JSON.stringify(corps); }
    fetch(chemin, options).then(function (r) { return r.status === 403 ? { refus: true } : r.json(); })
      .then(suite).catch(function () { suite(null); });
  }

  // ----- Couleurs et réglages
  function peindre(couleurs, palette) {
    for (var i = 0; i < 3; i++) { document.body.style.setProperty("--p" + (i + 1), couleurs[i]); }
    classe("paillettes", palette === "paillettes");
    var h = "";
    for (var j = 0; j < 3; j++) { h += '<i style="background:' + couleurs[j] + '"></i>'; }
    $("r_pastilles").innerHTML = h;
  }
  function appliquer() {
    classe("nuit", reglages.nuit);
    lecteur.volume = Math.max(0, Math.min(1, reglages.volume / 100));
    $("r_volume").value = reglages.volume;
    $("r_muet").className = "ligne" + (reglages.muet ? " actif" : "");
    $("r_nuit").className = "ligne" + (reglages.nuit ? " actif" : "");
    $("r_veille").className = "ligne" + (reglages.veille ? " actif" : "");
    $("r_veille").style.display = peutVeiller() ? "" : "none";
    majVeille();
    ecrire("jarvis_reglages", JSON.stringify(reglages));
  }
  function silencieux() { return reglages.muet || reglages.nuit; }

  // ----- Profils
  function trouver(id) {
    var liste = serveur ? serveur.profils : [];
    for (var i = 0; i < liste.length; i++) { if (liste[i].id === id) { return liste[i]; } }
    return null;
  }
  function entrerDans(p, j, discret) {
    profil = p; jeton = j;
    for (var i = 0; i < serveur.profils.length; i++) { if (serveur.profils[i].id === p.id) { serveur.profils[i] = p; } }
    ecrire("jarvis_profil", p.id);
    ecrire("jarvis_jeton", p.enfant ? "" : j);        // un adulte retrouve son profil à la prochaine ouverture, sans retaper son code
    peindre(p.couleurs, p.palette);
    $("qui").textContent = p.prenom || "Jarvis";
    $("qui").style.visibility = $("roue").style.visibility = "visible";
    $("propose").style.display = "none";
    rond.disabled = champ.disabled = $("envoi").disabled = false;
    fermer();
    majVeille();
    if (reprise) { var r = reprise; reprise = null; return envoyer(r.corps, r.type); }
    if (!discret) { entendu.textContent = ""; accueil(); }
  }
  function choisir(p) {
    if (!p) { return listeProfils(false); }
    if (p.enfant) {
      return api("/profil", { id: p.id }, function (d) {
        if (d && d.jeton) { entrerDans(d.profil, d.jeton); } else if (d && d.refus) { refuse(); }
        else if (d && d.erreur) { message(d.erreur, function () { listeProfils(true); }); } else { horsLigne(); }
      });
    }
    profilCode = p; ancienCode = null;
    api("/profil", { id: p.id }, function (d) {
      if (!d) { return horsLigne(); }
      if (d.refus) { return refuse(); }
      if (d.jeton) { return entrerDans(d.profil, d.jeton); }       // son profil était resté ouvert sur cette tablette
      if (d.creer) { return clavier("creer1"); }
      if (d.erreur) { return message(d.erreur, function () { listeProfils(!profil); }); }
      clavier("entrer", "", d.attente);
    });
  }
  function listeProfils(oblige) {
    var boite = $("liste_profils");
    boite.innerHTML = "";
    serveur.profils.forEach(function (p) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "ligne" + (profil && profil.id === p.id ? " choisi" : "");
      var pastilles = '<span class="pastilles">';
      for (var i = 0; i < 3; i++) { pastilles += '<i style="background:' + p.couleurs[i] + '"></i>'; }
      b.innerHTML = pastilles + "</span><span></span><span class='droite'></span>";
      b.children[1].textContent = p.prenom || "Jarvis";
      b.children[2].textContent = p.enfant ? "" : "code";
      b.onclick = function () { choisir(p); };
      boite.appendChild(b);
    });
    $("b_profils_fermer").style.display = oblige ? "none" : "";
    ouvrir("p_profils");
  }
  $("b_profils_fermer").onclick = fermer;
  $("qui").onclick = function () { seTaire(); listeProfils(false); };

  // ----- Code à 4 chiffres
  function points() {
    var p = $("points").children;
    for (var i = 0; i < 4; i++) { p[i].className = i < saisie.length ? "mis" : ""; }
  }
  function attendre(secondes) {
    var fin = Date.now() + secondes * 1000, boutons = $("touches").querySelectorAll("button");
    function tic() {
      var reste = Math.ceil((fin - Date.now()) / 1000), i;
      for (i = 0; i < boutons.length; i++) { boutons[i].disabled = reste > 0; }
      if (reste > 0) { $("msg_code").textContent = "Trop de codes faux. Réessaie dans " + reste + " s."; return; }
      clearInterval(compteur); compteur = null; $("msg_code").textContent = "";
    }
    if (compteur) { clearInterval(compteur); }
    compteur = setInterval(tic, 500); tic();
  }
  function clavier(etape, texte, attente) {
    etapeCode = etape; saisie = ""; points();
    var nom = profilCode.prenom || "";
    $("titre_code").textContent = etape === "entrer" ? "Code de " + nom : etape === "ancien" ? "Ton code actuel"
      : etape === "creer1" ? "Choisis ton code à 4 chiffres" : "Encore une fois, pour être sûr";
    $("msg_code").textContent = texte || "";
    $("b_autre").textContent = profil && etape !== "entrer" ? "Annuler" : "Changer de profil";
    ouvrir("p_code");
    var boutons = $("touches").querySelectorAll("button");
    for (var i = 0; i < boutons.length; i++) { boutons[i].disabled = false; }
    if (attente) { attendre(attente); }
  }
  function codeComplet() {
    var code = saisie;
    if (etapeCode === "entrer") {
      return api("/profil", { id: profilCode.id, code: code }, function (d) {
        if (!d) { return horsLigne(); }
        if (d.refus) { return refuse(); }
        if (d.jeton) { return entrerDans(d.profil, d.jeton); }
        clavier("entrer", d.erreur || "", d.attente);
      });
    }
    if (etapeCode === "ancien") { ancienCode = code; return clavier("creer1"); }
    if (etapeCode === "creer1") { premierCode = code; return clavier("creer2"); }
    if (code !== premierCode) { return clavier("creer1", "Les deux codes ne sont pas pareils. Recommence."); }
    var corps = { id: profilCode.id, code: code };
    if (ancienCode !== null) { corps.ancien = ancienCode; }
    api("/code", corps, function (d) {
      if (!d) { return horsLigne(); }
      if (d.refus) { return refuse(); }
      if (d.jeton) { entrerDans(d.profil, d.jeton); return message("Ton code est enregistré."); }
      if (ancienCode !== null && !d.attente) { ancienCode = null; return clavier("ancien", d.erreur || ""); }
      message(d.erreur || "Je n'ai pas pu enregistrer ce code.", function () { if (profil) { fermer(); } else { listeProfils(true); } });
    });
  }
  (function () {
    var noms = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Effacer", "0", ""];
    noms.forEach(function (n) {
      var b = document.createElement("button");
      b.type = "button"; b.textContent = n;
      if (n === "Effacer") { b.className = "sobre"; }
      if (n === "") { b.style.visibility = "hidden"; }
      b.onclick = function () {
        if (n === "Effacer") { saisie = saisie.slice(0, -1); return points(); }
        if (saisie.length >= 4) { return; }
        saisie += n; points();
        if (saisie.length === 4) { setTimeout(codeComplet, 120); }
      };
      $("touches").appendChild(b);
    });
  })();
  $("b_autre").onclick = function () { if (profil && etapeCode !== "entrer") { fermer(); } else { listeProfils(!profil); } };

  // ----- La roue des réglages
  function majDisponible() { return appli && serveur && serveur.apk > versionAppli(); }
  function roue() {
    seTaire();
    $("r_profil_nom").textContent = profil.prenom || "Jarvis";
    $("r_code").style.display = profil.enfant ? "none" : "";
    $("r_maj").style.display = $("r_desinstaller").style.display = appli ? "" : "none";
    $("r_installer").style.display = !appli && serveur.apk && /Android/i.test(navigator.userAgent) ? "" : "none";
    $("r_maj_etat").textContent = majDisponible() ? (serveur.apk_nom ? "Installer la version " + serveur.apk_nom : "Installer la nouvelle version") : "Rechercher";
    appliquer();
    ouvrir("p_reglages");
  }
  $("roue").onclick = roue;
  $("r_fermer").onclick = fermer;
  $("r_profil").onclick = function () { listeProfils(false); };
  $("r_volume").oninput = $("r_volume").onchange = function () { reglages.volume = parseInt(this.value, 10) || 0; appliquer(); };
  $("r_muet").onclick = function () { reglages.muet = !reglages.muet; appliquer(); };
  $("r_nuit").onclick = function () { reglages.nuit = !reglages.nuit; appliquer(); };
  $("r_veille").onclick = function () { reglages.veille = !reglages.veille; appliquer(); };
  $("r_nouvelle").onclick = function () {
    api("/nouvelle", {}, function (d) {
      fermer(); entendu.textContent = "";
      montrer(d && d.ok ? "C'est reparti de zéro. De quoi veux-tu parler ?" : "Je n'ai pas réussi, réessaie.", d && d.ok ? "calme" : "erreur");
    });
  };
  $("r_code").onclick = function () { profilCode = profil; ancienCode = null; clavier("ancien"); };
  $("r_apropos").onclick = function () {
    var nomAppli = "";
    try { nomAppli = appli && appli.nom ? appli.nom() : ""; } catch (e) {}
    $("versions").textContent = "Jarvis " + (serveur.version || "") + (appli ? " — application " + (nomAppli || "n° " + versionAppli()) : " — dans le navigateur");
    ouvrir("p_apropos");
  };
  $("b_apropos_retour").onclick = roue;
  $("r_desinstaller").onclick = function () { try { appli.desinstaller(); } catch (e) {} };
  $("r_installer").onclick = function () { installer(); };
  $("b_installer_retour").onclick = function () { fermer(); if (!profil) { demarrer(); } };
  $("r_maj").onclick = function () {
    if (majDisponible()) { $("r_maj_etat").textContent = "Téléchargement…"; try { appli.mettreAJour(); } catch (e) {} return; }
    $("r_maj_etat").textContent = "Recherche…";
    api("/etat", null, function (d) {
      if (d && d.ok) { serveur.apk = d.apk; serveur.apk_nom = d.apk_nom; serveur.version = d.version; }
      $("r_maj_etat").textContent = majDisponible() ? (serveur.apk_nom ? "Installer la version " + serveur.apk_nom : "Installer la nouvelle version") : d && d.ok ? "Tu as la dernière version" : "Jarvis ne répond pas";
      $("roue").className = majDisponible() ? "neuf" : "";
    });
  };
  window.jarvisMaj = function (texte) { $("r_maj_etat").textContent = texte; };
  setInterval(function () { if (serveur && profil && !document.hidden) { window.jarvisNote(""); } }, 60000);   // réglages et page à jour
  window.jarvisNote = function (texte) {       // pour le journal du PC ; en retour, les réglages du micro et la version de la page
    api("/note", { texte: String(texte) }, function (d) {
      if (!d || !d.ok) { return; }
      try { if (appli && appli.reglerMicro && d.micro) { appli.reglerMicro(JSON.stringify(d.micro)); } } catch (e) {}
      if (d.applis === 0) { envoyerApplis(); }    // le PC ne connaît plus les applications de cette tablette
      if (d.page && serveur && serveur.page && d.page !== serveur.page && mode === "veille" && voile.className !== "ouvert") {
        location.reload();                        // la page a été améliorée sur le PC : la tablette la reprend toute seule
      }
    });
  };
  function installer() {
    $("lien_appli").href = "intent://relier?h=" + encodeURIComponent(location.host) + "&c=" + encodeURIComponent(cle)
      + "&e=" + encodeURIComponent(serveur.empreinte || "") + "#Intent;scheme=jarvis;package=" + serveur.paquet + ";end";
    ouvrir("p_installer");
  }

  // ----- Couleurs
  function nuanciers() {
    for (var n = 0; n < 3; n++) {
      (function (n) {
        var boite = $("n" + n);
        boite.innerHTML = "";
        NUANCES.forEach(function (c) {
          var b = document.createElement("button");
          b.type = "button"; b.style.background = c;
          b.className = choix[n] === c ? "choisi" : "";
          b.onclick = function () { choix[n] = c; peindre(choix, "perso"); nuanciers(); };
          boite.appendChild(b);
        });
      })(n);
    }
  }
  function garderCouleurs(corps) {
    api("/couleurs", corps, function (d) {
      if (d && d.ok) { profil.couleurs = d.couleurs; profil.palette = d.palette; peindre(d.couleurs, d.palette); return couleurs(); }
      peindre(profil.couleurs, profil.palette);
      message(d && d.erreur ? d.erreur : "Je n'ai pas réussi à garder ces couleurs.", couleurs);
    });
  }
  function couleurs() {
    var boite = $("liste_palettes");
    boite.innerHTML = "";
    Object.keys(serveur.palettes).forEach(function (nom) {
      var c = serveur.palettes[nom], b = document.createElement("button");
      b.type = "button";
      b.className = "ligne" + (profil.palette === nom ? " choisi" : "");
      b.innerHTML = '<span class="pastilles"><i style="background:' + c[0] + '"></i><i style="background:' + c[1]
        + '"></i><i style="background:' + c[2] + '"></i></span><span></span>';
      b.children[1].textContent = nom.charAt(0).toUpperCase() + nom.slice(1);
      b.onclick = function () { garderCouleurs({ palette: nom }); };
      boite.appendChild(b);
    });
    choix = profil.couleurs.slice();
    nuanciers();
    ouvrir("p_couleurs");
  }
  $("r_couleurs").onclick = couleurs;
  $("b_couleurs_ok").onclick = function () { garderCouleurs({ perso: choix }); };
  $("b_couleurs_retour").onclick = function () { peindre(profil.couleurs, profil.palette); roue(); };

  // Au premier appui, un son silencieux : la page a ensuite le droit de faire parler Jarvis
  function debloquer() {
    if (debloque) { return; }
    debloque = true;
    try { lecteur.src = "__SILENCE__"; var p = lecteur.play(); if (p && p.catch) { p.catch(function () {}); } } catch (e) {}
  }

  // ----- Ce que la tablette fait elle-même : ouvrir une application, lancer une recherche
  function agir() {
    var a = aFaire; aFaire = null;
    if (!a) { return; }
    if (a.type === "profil") { return a.id ? choisir(trouver(a.id)) : listeProfils(false); }     // « c'est Marie », « change de profil »
    try {
      if (a.type === "appli" && appli) { appli.ouvrir(a.paquet); }
      else if (a.type === "lien" && appli) { appli.lien(a.url); }
    } catch (e) {}
  }
  function fin() {
    if (mode === "repond") { mettre("veille"); }
    if (questionEnAttente) { questionEnAttente = false; suiteFin = Date.now() + 20000; }
    agir();
  }
  function questionPosee(texte) {       // Jarvis pose une question : pendant 20 secondes après sa voix, on lui répond sans redire « Jarvis »
    suiteFin = 0;
    questionEnAttente = /\?\s*$/.test(texte || "");
  }
  function voixTablette(texte) {
    try {
      if (!window.speechSynthesis) { return fin(); }
      var u = new SpeechSynthesisUtterance(texte);
      u.lang = "fr-FR"; u.volume = Math.max(0, Math.min(1, reglages.volume / 100)); u.onend = fin; u.onerror = fin;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(u);
    } catch (e) { fin(); }
  }
  function dire(d) {
    if (silencieux()) { mettre("veille"); if (questionEnAttente) { questionEnAttente = false; suiteFin = Date.now() + 20000; } return setTimeout(agir, 700); }
    mettre("repond");
    if (d.voix_attente) {                         // le texte est déjà affiché ; la voix arrive dès qu'elle est fabriquée
      var numero = d.voix_attente;
      d.voix_attente = null; voixAttendue = numero;
      return api("/voix", { id: numero }, function (v) {
        if (voixAttendue !== numero || mode !== "repond") { return; }
        voixAttendue = null; d.voix = v && v.voix ? v.voix : null;
        dire(d);
      });
    }
    if (!d.voix) { return voixTablette(d.reponse); }
    try {
      var brut = atob(d.voix), octets = new Uint8Array(brut.length);
      for (var i = 0; i < brut.length; i++) { octets[i] = brut.charCodeAt(i); }
      if (adresseSon) { URL.revokeObjectURL(adresseSon); }
      adresseSon = URL.createObjectURL(new Blob([octets], { type: "audio/mpeg" }));
      lecteur.onended = fin;
      lecteur.onerror = function () { voixTablette(d.reponse); };
      lecteur.src = adresseSon;
      var p = lecteur.play();
      if (p && p.catch) { p.catch(function () { voixTablette(d.reponse); }); }
    } catch (e) { voixTablette(d.reponse); }
  }
  function seTaire() {
    aFaire = null; voixAttendue = null;
    try { lecteur.pause(); } catch (e) {}
    try { if (window.speechSynthesis) { window.speechSynthesis.cancel(); } } catch (e) {}
    mettre("veille");
  }

  function horsLigne() {
    fermer();
    montrer("Je n'arrive pas à joindre Jarvis. L'ordinateur est-il allumé ?", "erreur");
    mettre("veille");
  }
  function refuse() { bloquer("Cette tablette n'est plus reliée à Jarvis. Demande à un adulte de montrer le QR code de la tablette."); }
  function proposer(id) {            // la voix d'un adulte du foyer a été reconnue : on lui propose son profil (avec son code)
    var p = id ? trouver(id) : null;
    if (p && profil && p.id !== profil.id) {
      $("propose").textContent = "C'est toi, " + p.prenom + " ? Passe sur ton profil";
      $("propose").style.display = "inline-block";
      $("propose").onclick = function () { seTaire(); choisir(p); };
    } else { $("propose").style.display = "none"; }
  }
  function recevoir(d) {
    $("ouvrir").style.display = "none";
    if (d && d.refus) { mettre("veille"); return refuse(); }
    if (d && d.session === "finie") {             // le profil est resté trop longtemps sans rien demander
      mettre("veille"); jeton = null; ecrire("jarvis_jeton", ""); reprise = dernier;
      return choisir(trouver(profil ? profil.id : serveur.defaut) || trouver(serveur.defaut));
    }
    if (d.bascule && trouver(d.bascule.profil)) { entrerDans(trouver(d.bascule.profil), d.bascule.jeton, true); }
    if (d.attente) {                              // comme sur le PC : la phrase comprise s'affiche, puis la réponse la remplace
      entendu.textContent = "";
      montrer(d.entendu || "…", "demande");
      parEtapes = true;
      proposer(d.propose);
      mettre("reflechit");
      return api("/resultat", { id: d.attente }, function (r) { if (r && r.refus) { return refuse(); } if (!r) { return horsLigne(); } recevoir(r); });
    }
    entendu.textContent = d.entendu && mode === "reflechit" && bulle.className !== "demande" ? "« " + d.entendu + " »" : "";
    if (d.erreur || !d.reponse) {
      montrer(d.erreur || "Je n'ai pas de réponse.", "erreur");
      return mettre("veille");
    }
    montrer(d.reponse, "");
    questionPosee(d.reponse);
    if (!parEtapes) { proposer(d.propose); }
    aFaire = d.code ? { type: "profil", id: d.code } : d.profils ? { type: "profil", id: null } : d.action || null;
    if (aFaire && aFaire.type === "lien" && !appli) {      // dans un navigateur : un bouton, qu'on touche pour ouvrir la page
      lienAttente = aFaire.url; aFaire = null;
      $("ouvrir").textContent = "Ouvrir la page";
      $("ouvrir").style.display = "inline-block";
      $("ouvrir").onclick = function () { window.open(lienAttente, "_blank"); };
    }
    dire(d);
  }
  function envoyer(corps, type) {
    dernier = { corps: corps, type: type };
    parEtapes = false;
    mettre("reflechit");
    var entetes = { "X-Jarvis-Cle": cle || "", "X-Jarvis-Tablette": tablette, "Content-Type": type, "X-Jarvis-Etapes": "1" };
    if (jeton) { entetes["X-Jarvis-Profil"] = jeton; }
    if (silencieux()) { entetes["X-Jarvis-Muet"] = "1"; }
    fetch("/demande", { method: "POST", headers: entetes, body: corps })
      .then(function (r) { return r.status === 403 ? { refus: true } : r.json(); })
      .then(recevoir)
      .catch(horsLigne);
  }

  // ----- Écouter : on parle, et l'enregistrement s'arrête tout seul au silence -----
  function liberer() {
    if (minuterie) { clearInterval(minuterie); clearTimeout(minuterie); minuterie = null; }
    try { if (source) { source.disconnect(); } } catch (e) {}
    source = null;
    if (flux) { flux.getTracks().forEach(function (p) { p.stop(); }); flux = null; }     // le micro est rendu
  }
  function arreter() {
    if (natif()) {
      try { appli.arreterEcoute(mode === "ecoute"); } catch (e) {}
      if (mode !== "ecoute") { mettre("veille"); }
      return;
    }
    if (minuterie) { clearInterval(minuterie); clearTimeout(minuterie); minuterie = null; }
    if (rec && rec.state !== "inactive") { rec.stop(); } else { liberer(); if (mode === "ecoute") { mettre("veille"); } }
  }
  function finEcoute() {
    var type = (rec && rec.mimeType) || "audio/webm";
    var son = new Blob(morceaux, { type: type });
    liberer();
    if (mode !== "ecoute") { return; }
    if (son.size < 800) { montrer("Je n'ai rien entendu.", "erreur"); return mettre("veille"); }
    montrer("…", "calme");
    envoyer(son, /^audio\//.test(type) ? type : "audio/webm");
  }
  function surveiller() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { minuterie = setTimeout(arreter, 8000); return; }
    ctx = ctx || new AC();
    if (ctx.state === "suspended") { ctx.resume(); }
    source = ctx.createMediaStreamSource(flux);
    var analyse = ctx.createAnalyser();
    analyse.fftSize = 1024;
    source.connect(analyse);
    var t = new Uint8Array(analyse.fftSize), debut = Date.now(), dernierSon = 0, parle = false, plancher = null;
    minuterie = setInterval(function () {
      analyse.getByteTimeDomainData(t);
      var s = 0;
      for (var i = 0; i < t.length; i++) { var v = (t[i] - 128) / 128; s += v * v; }
      var niveau = Math.sqrt(s / t.length), maintenant = Date.now();
      plancher = plancher === null || niveau < plancher ? niveau : plancher * 0.98 + niveau * 0.02;   // bruit de la pièce
      if (niveau > Math.max(0.035, plancher * 3)) { parle = true; dernierSon = maintenant; }
      rond.style.setProperty("--n", Math.min(1, niveau * 6));
      if ((parle && maintenant - dernierSon > 1400) || (!parle && maintenant - debut > 7000) || maintenant - debut > 20000) { arreter(); }
    }, 80);
  }
  function microRefuse(raison) {
    montrer(raison === "panne" ? "Je n'ai pas réussi à utiliser le micro. Réessaie, ou écris ta question."
      : "Je n'ai pas le droit d'utiliser le micro. Autorise-le, ou écris ta question.", "erreur");
    mettre("veille");
    api("/note", { texte: "micro : " + raison }, function () {});
  }
  window.jarvisNiveau = function (n) { if (mode === "ecoute") { rond.style.setProperty("--n", n); } };
  window.jarvisMicro = function (raison) { if (mode === "ecoute") { microRefuse(raison); } };
  window.jarvisSon = function (texte, type, demande) {
    var brut = "", octets;
    try { brut = atob(texte || ""); } catch (e) {}
    if (brut.length >= 800) {
      octets = new Uint8Array(brut.length);
      for (var i = 0; i < brut.length; i++) { octets[i] = brut.charCodeAt(i); }
    }
    if (demande === false) { return octets ? phraseEntendue(new Blob([octets], { type: type }), type) : null; }
    if (mode !== "ecoute") { return; }
    if (!octets) { montrer("Je n'ai rien entendu.", "erreur"); return mettre("veille"); }
    montrer("…", "calme");
    envoyer(new Blob([octets], { type: type }), type);
  };
  // Une phrase entendue par l'écoute permanente : le PC dit si elle était pour Jarvis. Sinon, rien ne bouge à l'écran.
  function phraseEntendue(son, type) {
    if (mode !== "veille" || !profil || voile.className === "ouvert") { return; }
    if (enVol) { enAttente = { son: son, type: type }; return; }     // le PC est occupé : la dernière phrase attend son tour
    enVol = true;
    var suite = Date.now() < suiteFin;
    var entetes = { "X-Jarvis-Cle": cle || "", "X-Jarvis-Tablette": tablette, "Content-Type": type, "X-Jarvis-Veille": suite ? "suite" : "1",
                    "X-Jarvis-Etapes": "1" };
    if (jeton) { entetes["X-Jarvis-Profil"] = jeton; }
    if (silencieux()) { entetes["X-Jarvis-Muet"] = "1"; }
    fetch("/demande", { method: "POST", headers: entetes, body: son })
      .then(function (r) { return r.status === 403 ? { refus: true } : r.json(); })
      .then(function (d) {
        enVol = false;
        var suivante = enAttente; enAttente = null;
        if (suivante && (!d || d.ignore) && mode === "veille") { return phraseEntendue(suivante.son, suivante.type); }
        if (!d || d.ignore || mode !== "veille") { return; }
        if (d.ecoute) { debloquer(); return ecouter(); }
        suiteFin = 0;
        dernier = { corps: son, type: type };
        parEtapes = false;
        mode = "reflechit";
        recevoir(d);
      })
      .catch(function () { enVol = false; enAttente = null; });
  }
  function ecouter() {
    seTaire();
    if (natif()) {
      entendu.textContent = "";
      $("ouvrir").style.display = $("propose").style.display = "none";
      montrer("Parle, je t'écoute…", "calme");
      mettre("ecoute");
      try { appli.ecouter(); } catch (e) { microRefuse("panne"); }
      return;
    }
    navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } })
      .then(function (f) {
        flux = f; morceaux = [];
        rec = new MediaRecorder(f);
        rec.ondataavailable = function (e) { if (e.data && e.data.size) { morceaux.push(e.data); } };
        rec.onstop = finEcoute;
        rec.start();
        entendu.textContent = "";
        $("ouvrir").style.display = $("propose").style.display = "none";
        montrer("Parle, je t'écoute…", "calme");
        mettre("ecoute");
        surveiller();
      })
      .catch(function (e) {
        liberer();
        microRefuse(e && e.name ? e.name : "refus");
      });
  }

  rond.addEventListener("click", function () {
    debloquer();
    if (!profil) { return; }
    if (mode === "ecoute") { return arreter(); }
    if (mode === "repond") { return seTaire(); }
    if (mode === "reflechit") { return; }
    if (peutEcouter()) { ecouter(); } else { champ.focus(); }
  });
  forme.addEventListener("submit", function (e) {
    e.preventDefault();
    debloquer();
    var texte = champ.value.replace(/\s+/g, " ").trim();
    if (!texte || mode === "reflechit" || !profil) { return; }
    if (mode === "ecoute") { mode = "veille"; arreter(); }
    seTaire();
    champ.value = "";
    champ.blur();
    entendu.textContent = "";
    $("ouvrir").style.display = $("propose").style.display = "none";
    montrer(texte, "demande");
    envoyer(JSON.stringify({ texte: texte }), "application/json");
  });
  function envoyerApplis() {
    if (!appli || !appli.applis) { return; }
    try { api("/applis", { applis: JSON.parse(appli.applis()) }, function () {}); } catch (e) {}
  }
  document.addEventListener("visibilitychange", function () {
    if (document.hidden && mode === "ecoute") { mode = "veille"; arreter(); mettre("veille"); }
    majVeille();
    if (!document.hidden && serveur) { envoyerApplis(); }      // une application installée entre-temps est aussitôt connue
  });

  // ----- Ouverture
  function demarrer() {
    jeton = jeton || lire("jarvis_jeton") || null;
    choisir(trouver(lire("jarvis_profil") || "") || trouver(serveur.defaut));
  }
  appliquer();
  if (!cle) {
    bloquer("Cette tablette n'est pas encore reliée à Jarvis. Sur l'ordinateur, demande « Jarvis, montre le QR code de la tablette », puis vise-le avec l'appareil photo.");
    return;
  }
  rond.disabled = champ.disabled = $("envoi").disabled = true;
  api("/etat", null, function (d) {
    if (d && d.refus) { return refuse(); }
    if (!d || !d.ok) { return horsLigne(); }
    serveur = d;
    var gardees = "Chaque demande (le texte, et la voix quand tu parles) est aussi gardée sur le PC de la maison, rangée par profil : les "
      + d.historique + " dernières, pas plus.";
    $("donnees1").textContent = $("donnees3").textContent = $("donnees5").textContent = d.donnees;
    $("donnees2").textContent = $("donnees4").textContent = gardees;
    $("roue").className = majDisponible() ? "neuf" : "";
    envoyerApplis();
    try { if (appli && appli.reglerMicro && d.micro) { appli.reglerMicro(JSON.stringify(d.micro)); } } catch (e) {}
    var ouverture = "navigateur";       // pour le journal du PC : quelle application, et ce qu'elle sait faire
    try {
      if (appli) {
        ouverture = "application " + (appli.nom ? appli.nom() : "?") + " (n " + versionAppli() + "), micro " + (appli.micro ? appli.micro() : "?")
          + ", écoute permanente " + (peutVeiller() ? (reglages.veille ? "activée" : "coupée") : "absente");
      }
    } catch (e) {}
    api("/note", { texte: "ouverture : " + ouverture }, function () {});
    function suite() {            // dans le navigateur d'une tablette Android : l'application est proposée une fois
      if (!appli && d.apk && /Android/i.test(navigator.userAgent) && !lire("jarvis_appli_vue")) {
        ecrire("jarvis_appli_vue", "1");
        return installer();
      }
      demarrer();
    }
    if (lire("jarvis_vu")) { return suite(); }
    $("b_compris").onclick = function () { ecrire("jarvis_vu", "1"); fermer(); suite(); };
    ouvrir("p_bienvenue");
  });
})();
</script>
</body>
</html>
"""


# ---------- Le serveur (HTTPS, sur le réseau de la maison) ----------

class _Serveur(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False          # sur Windows, « réutiliser » laisserait un autre programme prendre le port

    def handle_error(self, request, client_address):
        pass                             # liaison refusée ou coupée par la tablette : rien à noter


class _Requete(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version, sys_version = "Jarvis", ""
    timeout = 30

    def log_message(self, *args):
        pass                             # rien dans le journal sur qui se connecte

    def _envoyer(self, code, corps, genre):
        self.send_response(code)
        self.send_header("Content-Type", genre)
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(corps)

    def _json(self, code, donnees):
        self._envoyer(code, json.dumps(donnees, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _cle_bonne(self):
        attendue = str(_lire().get("cle") or "")
        donnee = self.headers.get("X-Jarvis-Cle", "")
        bonne = bool(attendue) and hmac.compare_digest(attendue.encode("utf-8"), donnee.encode("utf-8"))
        if not bonne:
            time.sleep(1)                # une mauvaise clé coûte une seconde : inutile d'en essayer des milliers
        return bonne

    def do_GET(self):
        chemin = self.path.split("?")[0]
        if chemin == "/":
            self._envoyer(200, PAGE.replace("__SILENCE__", _silence()).encode("utf-8"), "text/html; charset=utf-8")
        elif chemin == "/icone.png":
            self._envoyer(200, _icone(), "image/png")
        elif chemin == "/etat":
            if self._cle_bonne():
                self._json(200, etat())
            else:
                self._json(403, {"erreur": "Clé refusée."})
        elif chemin == "/jarvis.apk":
            self._apk()
        else:
            self._envoyer(404, b"", "text/plain")

    def _apk(self):
        """L'application Android : la même pour tout le monde, elle ne contient ni clé ni adresse."""
        try:
            with open(_apk_choisie()[0] or APK, "rb") as f:
                corps = f.read()
        except OSError:
            return self._envoyer(404, b"", "text/plain")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.android.package-archive")
        self.send_header("Content-Disposition", 'attachment; filename="Jarvis-tablette.apk"')
        self.send_header("Content-Length", str(len(corps)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(corps)

    def do_POST(self):
        chemin = self.path.split("?")[0]
        if chemin not in ("/demande", "/resultat", "/voix", "/profil", "/code", "/couleurs", "/nouvelle", "/applis", "/note"):
            return self._envoyer(404, b"", "text/plain")
        try:
            longueur = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            longueur = 0
        if longueur <= 0 or longueur > (TAILLE_MAX if chemin == "/demande" else 200_000):
            self.close_connection = True
            return self._json(413, {"erreur": "Demande trop longue."})
        corps = self.rfile.read(longueur)
        if not self._cle_bonne():
            return self._json(403, {"erreur": "Cette tablette n'est plus reliée à Jarvis."})
        jeton = self.headers.get("X-Jarvis-Profil") or None
        tablette = self.headers.get("X-Jarvis-Tablette", "")
        try:
            if chemin == "/demande":
                genre = self.headers.get("Content-Type", "")
                muet = self.headers.get("X-Jarvis-Muet") == "1"
                etapes = self.headers.get("X-Jarvis-Etapes") == "1"
                if genre.startswith("application/json"):
                    resultat = repondre(texte=json.loads(corps.decode("utf-8")).get("texte"), jeton=jeton,
                                        tablette=tablette, muet=muet, etapes=etapes)
                else:
                    veille = self.headers.get("X-Jarvis-Veille", "")
                    resultat = repondre(son=corps, jeton=jeton, tablette=tablette, genre=genre, muet=muet,
                                        veille=veille if veille in ("1", "suite") else "", etapes=etapes)
            else:
                recu = json.loads(corps.decode("utf-8"))
                recu = recu if isinstance(recu, dict) else {}
                if chemin == "/resultat":
                    resultat = globals()["resultat"](recu.get("id"))
                elif chemin == "/voix":
                    resultat = voix(recu.get("id"))
                elif chemin == "/profil":
                    resultat = entrer(str(recu.get("id") or ""), recu.get("code"), jeton)
                elif chemin == "/code":
                    resultat = choisir_code(str(recu.get("id") or ""), recu.get("code"), recu.get("ancien"))
                elif chemin == "/applis":
                    resultat = garder_applis(tablette, recu.get("applis"))
                elif chemin == "/note":              # ce qui n'a pas marché sur la tablette (micro refusé...), pour le journal du PC
                    if recu.get("texte"):
                        print("Tablette (note) :", re.sub(r"[^\w :.,'()\-éèêàùç]", "?", str(recu.get("texte")))[:200])
                    resultat = {"ok": True, "micro": _micro(), "page": _version_page(), "applis": len(applis_de(tablette))}
                else:                                # le reste concerne le profil ouvert sur la tablette
                    ident = _session(jeton)
                    if ident is None:
                        resultat = {"erreur": "Choisis ton profil pour continuer.", "session": "finie"}
                    elif chemin == "/couleurs":
                        resultat = regler_couleurs(ident, recu.get("palette"), recu.get("perso"))
                    else:
                        resultat = nouvelle_conversation(ident)
        except Exception as erreur:
            print("Tablette :", erreur)
            resultat = {"erreur": "J'ai eu un souci. Essaie encore."}
        self._json(200, resultat)


def demarrer():
    """Ouvre l'accès si la tablette est activée. Renvoie True si le serveur tourne."""
    global _serveur
    if _serveur is not None:
        return True
    if not actif():
        return False
    certificat, cle = _certificat()
    serveur = _Serveur((HOTE, PORT), _Requete)
    contexte = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexte.load_cert_chain(certificat, cle)
    # la poignée de main chiffrée se fait dans le fil de chaque tablette, jamais dans celui qui accueille
    serveur.socket = contexte.wrap_socket(serveur.socket, server_side=True, do_handshake_on_connect=False)
    _serveur = serveur
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    print(f"Tablette : accès ouvert sur le réseau de la maison (port {PORT}).")
    return True


def arreter():
    global _serveur
    serveur, _serveur = _serveur, None
    if serveur is not None:
        serveur.shutdown()
        serveur.server_close()
        print("Tablette : accès fermé.")
    _fermer_conversations()


# ---------- Les demandes dites à Jarvis sur le PC ----------

def _montrer_qr(adresse, minutes=10):
    """Ouvre la fenêtre du QR code. L'adresse (qui contient la clé) passe par l'entrée standard : jamais dans
    la ligne de commande, jamais dans le journal."""
    try:
        executable = sys.executable
        if not executable.lower().endswith("pythonw.exe"):
            sans_console = os.path.join(os.path.dirname(executable), "pythonw.exe")
            executable = sans_console if os.path.exists(sans_console) else executable
        script = os.path.join(jarvis_config.DOSSIER, "jarvis_fenetre_qr.py")
        p = subprocess.Popen([executable, script], stdin=subprocess.PIPE,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        p.stdin.write(json.dumps({
            "adresse": adresse, "minutes": minutes, "titre": "Jarvis sur la tablette",
            "texte": "Vise ce code avec l'appareil photo de la tablette",
            "lignes": ["1. Ouvre le lien proposé.",
                       "2. Avertissement de sécurité : choisis « Paramètres avancés », puis « Continuer ».",
                       "3. Sur une tablette Android : installe l'application proposée par la page, puis touche "
                       "« Ouvrir dans l'application ». Sinon, dans le menu du navigateur : « Ajouter à l'écran d'accueil ».",
                       "Pendant 10 minutes, les adultes peuvent choisir leur code sur la tablette."]}).encode("utf-8"))
        p.stdin.close()
        return True
    except Exception as erreur:
        print("QR code de la tablette :", erreur)
        return False


_TABLETTE = re.compile(r"\b(?:la|ma|sa|une|ta|cette|l'accès (?:à|de) la|l'acces (?:a|de) la) ?tablette\b")
_PAS_POUR_MOI = re.compile(r"\b(?:chocolat|liste|courses|ach[èe]te|acheter|prix|cherche|recherche|vid[ée]o|youtube)\b")
_COUPER = re.compile(r"\b(?:d[ée]sactive[rs]?|coupe[rs]?|retire[rs]?|supprime[rs]?|oublie[rs]?|d[ée]connecte[rs]?|"
                     r"enl[èe]ve[rs]?|arr[êe]te[rs]?|ferme[rs]?)\b")
_ACTIVER = re.compile(r"\b(?:active[rs]?|autorise[rs]?|connecte[rs]?|relie[rs]?|associe[rs]?|installe[rs]?|branche[rs]?|"
                      r"ouvre|ouvrir)\b")
_MONTRER = re.compile(r"\b(?:montre[rs]?|affiche[rs]?|redonne|r[ée]affiche|donne)\b|\bqr\b|\bq r\b")
_QUESTION = re.compile(r"\best-ce que\b|\best[- ]elle\b|\best (?:activ|reli|connect|branch)")


def commande(t, enfant=False, invite=False):
    """« active la tablette », « montre le QR code de la tablette », « désactive la tablette ».
    Renvoie la réponse à dire, ou None si la phrase ne parle pas de l'accès de la tablette."""
    global _reglage_fin
    t = t.replace("’", "'")
    if not _TABLETTE.search(t) or _PAS_POUR_MOI.search(t):
        return None
    couper, activer_, montrer, question = (_COUPER.search(t), _ACTIVER.search(t), _MONTRER.search(t), _QUESTION.search(t))
    if not (couper or activer_ or montrer or question):
        return None
    if question and not montrer:
        return ("L'accès de la tablette est activé." if actif() and _serveur is not None
                else "L'accès de la tablette n'est pas activé.")
    if enfant or invite:
        return "Seul un adulte peut régler l'accès de la tablette."
    donnees = _lire()
    if couper:
        donnees["actif"] = False
        donnees.pop("cle", None)                     # l'ancienne clé ne servira plus jamais
        donnees.pop("sessions", None)                # ni les profils restés ouverts sur les tablettes
        _sessions.clear()
        _ecrire(donnees)
        arreter()
        return "C'est fait : la tablette n'a plus accès à Jarvis."
    if montrer and not activer_ and not actif():
        return "L'accès de la tablette n'est pas activé. Dis-moi « active la tablette » si tu le veux."
    if activer_ or not donnees.get("cle"):
        m = re.search(r"\b(?:pour|de|à|a)\s+(?!la\b|ma\b|sa\b|ta\b|une\b|cette\b)([\w\-]+)\W*$", t)
        if m:
            try:
                import jarvis_profils
                ident = jarvis_profils._trouver(m.group(1))
                prenom = (jarvis_profils._lire().get(ident, {}).get("prenom") if ident else "")
                if prenom:
                    donnees["prenom"] = prenom
            except Exception as erreur:
                print("Tablette (profil) :", erreur)
        donnees["actif"] = True
        donnees.setdefault("cle", secrets.token_urlsafe(24))
        _ecrire(donnees)
        _fermer_conversations()                      # les prochaines conversations prendront le bon prénom
    try:
        ouvert = demarrer()
    except Exception as erreur:
        print("Tablette (serveur) :", erreur)
        ouvert = False
    if not ouvert:
        return "Je n'ai pas réussi à ouvrir l'accès de la tablette. Regarde dans mon journal ce qui bloque."
    adresse = lien()
    if not adresse:
        return "L'accès est prêt, mais ce PC n'est relié à aucun réseau : je ne peux pas donner d'adresse à la tablette."
    _reglage_fin = time.time() + DUREE_REGLAGE      # un adulte est là : les codes peuvent être choisis sur la tablette
    if not _montrer_qr(adresse):
        return "L'accès de la tablette est ouvert, mais je n'arrive pas à afficher le QR code."
    pour = f" pour {donnees['prenom']}" if donnees.get("prenom") else ""
    return (f"L'accès de la tablette est ouvert{pour}. Vise le QR code à l'écran avec son appareil photo, accepte "
            "l'avertissement de sécurité, puis installe l'application proposée, ou ajoute la page à l'écran d'accueil. "
            "Si Windows demande d'autoriser Python sur le réseau, accepte pour les réseaux privés.")
