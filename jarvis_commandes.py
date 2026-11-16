"""
JARVIS - commandes instantanées.

Ces demandes simples sont traitées directement sur le PC, sans passer par Claude :
la réponse est immédiate et ton quota Claude est économisé.
  - l'heure et la date ;
  - le volume (monter, baisser, régler à un pourcentage, couper, remettre) ;
  - ouvrir une application ou un dossier courant.
Tout ce qui n'est pas reconnu ici est envoyé à Claude, comme avant.
"""

import os
import re
import time

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

PAS_VOLUME = 10   # pourcentage ajouté ou retiré par « monte le son » / « baisse le son »

DOSSIER_PERSO = os.path.expanduser("~")

# mots-clés -> (ce qu'il faut ouvrir, nom prononcé)
APPLICATIONS = [
    (r"chrome|navigateur|google", "chrome", "Chrome"),
    (r"calculatrice|calculette", "calc", "la calculatrice"),
    (r"bloc[- ]?notes?", "notepad", "le bloc-notes"),
    (r"gestionnaire des t[aâ]ches", "taskmgr", "le gestionnaire des tâches"),
    (r"param[eè]tres|r[eé]glages", "ms-settings:", "les paramètres"),
    (r"t[eé]l[eé]chargements?", os.path.join(DOSSIER_PERSO, "Downloads"), "tes téléchargements"),
    (r"documents?", os.path.join(DOSSIER_PERSO, "Documents"), "tes documents"),
    (r"images?|photos?", os.path.join(DOSSIER_PERSO, "Pictures"), "tes images"),
    (r"explorateur|mes fichiers|fichiers", "explorer", "l'explorateur de fichiers"),
    (r"youtube", "https://www.youtube.com", "YouTube"),
]

NOMBRES = {"dix": 10, "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50,
           "soixante": 60, "soixante-dix": 70, "soixante dix": 70,
           "quatre-vingt": 80, "quatre vingt": 80, "quatre-vingts": 80,
           "quatre-vingt-dix": 90, "quatre vingt dix": 90, "cent": 100, "zéro": 0}


# ---------- Heure et date ----------

def _heure():
    t = time.localtime()
    h, m = t.tm_hour, t.tm_min
    if h == 0:
        debut = "minuit"
    elif h == 12:
        debut = "midi"
    else:
        debut = f"{h} heure{'s' if h > 1 else ''}"
    return f"Il est {debut}{f' {m}' if m else ''}."


def _date():
    t = time.localtime()
    jour = "premier" if t.tm_mday == 1 else str(t.tm_mday)
    return f"Nous sommes le {JOURS[t.tm_wday]} {jour} {MOIS[t.tm_mon - 1]} {t.tm_year}."


# ---------- Volume ----------

def _volume():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume


def _nombre(texte):
    m = re.search(r"(\d{1,3})", texte)
    if m:
        return int(m.group(1))
    for mot in sorted(NOMBRES, key=len, reverse=True):
        if re.search(rf"\b{mot}\b", texte):
            return NOMBRES[mot]
    return None


def _commande_volume(t):
    if not re.search(r"\b(son|volume|sourdine|muet)\b", t):
        return None
    v = _volume()
    actuel = round(v.GetMasterVolumeLevelScalar() * 100)
    if re.search(r"\b(coupe|couper|sourdine|muet|mute)\b", t) and not re.search(r"\b(remets|remet|réactive|rétablis)\b", t):
        v.SetMute(1, None)
        return "Le son est coupé."
    if re.search(r"\b(remets|remet|réactive|rétablis|rallume)\b", t):
        v.SetMute(0, None)
        return f"Le son est remis, à {actuel} pour cent."
    nombre = _nombre(t)
    if nombre is not None and re.search(r"\b(à|a|sur)\b", t):
        cible = max(0, min(100, nombre))
    elif re.search(r"\b(monte|monter|augmente|augmenter|plus fort)\b", t):
        cible = min(100, actuel + PAS_VOLUME)
    elif re.search(r"\b(baisse|baisser|diminue|diminuer|moins fort)\b", t):
        cible = max(0, actuel - PAS_VOLUME)
    elif re.search(r"\b(quel|combien)\b", t):
        return f"Le volume est à {actuel} pour cent."
    else:
        return None
    v.SetMute(0, None)
    v.SetMasterVolumeLevelScalar(cible / 100, None)
    return f"Volume à {cible} pour cent."


# ---------- Applications ----------

def _commande_ouvrir(t):
    m = re.search(r"\b(ouvre|ouvrir|ouvres|lance|lancer|lances|démarre|démarrer)\b(.*)", t)
    if not m:
        return None
    reste = m.group(2)
    # Une demande plus complexe (« ouvre Chrome et cherche... ») reste pour Claude
    if re.search(r"\b(et|puis|pour|avec|sur|dans)\b", reste):
        return None
    for motif, cible, nom in APPLICATIONS:
        if re.search(rf"\b(?:{motif})\b", reste):
            os.startfile(cible)
            return f"J'ouvre {nom}."
    return None


# ---------- Point d'entrée ----------

def commande_instantanee(textes):
    """
    textes : les retranscriptions de la demande (Whisper et Vosk).
    Renvoie la réponse à dire, ou None si la demande doit aller à Claude.
    """
    for brut in textes:
        if not brut:
            continue
        t = brut.lower().replace("’", "'").strip(" .!?")
        try:
            if re.search(r"\bquelle heure\b", t) and not re.search(r"\b(à|au|aux|en)\s+\w", t):
                return _heure()
            if re.search(r"\b(quel jour|quelle date|on est le combien|nous sommes le combien)\b", t) \
                    and not re.search(r"\b(sera|était|demain|hier)\b", t):
                return _date()
            reponse = _commande_volume(t)
            if reponse:
                return reponse
            reponse = _commande_ouvrir(t)
            if reponse:
                return reponse
        except Exception as erreur:
            print("Commande instantanée impossible :", erreur)
            return None
    return None
