"""
JARVIS - l'imprimante du réseau : niveaux d'encre et état.

  « Jarvis, il reste combien d'encre ? », « le niveau des cartouches »
  « Jarvis, l'imprimante est allumée ? », « comment va l'imprimante ? »

L'imprimante est trouvée par la Freebox (fabricant HP, Canon, Epson, Brother...), puis interrogée en IPP,
le langage standard des imprimantes réseau : lecture seule, sans mot de passe, rien n'est imprimé.
"""

import re
import struct
import time
import urllib.request

FABRICANTS = ("hp inc", "hewlett", "canon", "epson", "seiko epson", "brother", "lexmark", "xerox", "kyocera", "ricoh")
SEUIL_BAS = 20                   # % : en dessous, Jarvis prévient que la cartouche est presque vide
_memo = {"ip": None, "quand": 0.0}

_ENCRE = re.compile(r"\b(?:encre|cartouches?|toner)\b")
_IMPRIMANTE = re.compile(r"\bimprimante\b")
_QUESTION = re.compile(r"\b(?:combien|reste|niveau|niveaux|état|etat|comment va|allumée|allumee|marche|fonctionne|"
                       r"vide|vides|presque|quoi de neuf|prête|prete|branchée|connectée|ça va|elle va|est-ce que)\b|\?")
_COULEURS = {"black": "noir", "cyan": "cyan", "magenta": "magenta", "yellow": "jaune", "tri-color": "couleur",
             "tricolor": "couleur", "color": "couleur", "photo": "photo"}
_RAISONS = {"media-empty": "il n'y a plus de papier", "media-needed": "il faut remettre du papier",
            "media-jam": "il y a un bourrage papier", "door-open": "un capot est ouvert",
            "cover-open": "un capot est ouvert", "marker-supply-empty": "une cartouche est vide",
            "toner-empty": "le toner est vide", "paused": "l'impression est en pause", "offline": "elle est hors ligne"}


def _adresse(forcer=False):
    """IP de l'imprimante d'après la Freebox (gardée 10 minutes), ou None."""
    if _memo["ip"] and not forcer and time.time() - _memo["quand"] < 600:
        return _memo["ip"]
    import jarvis_freebox
    for h in jarvis_freebox._lire("lan/browser/pub/") or []:
        vendeur = (h.get("vendor_name") or "").lower()
        nom = (h.get("primary_name") or "").lower()
        if not h.get("active") or not (any(f in vendeur for f in FABRICANTS) or "imprim" in nom or "printer" in nom):
            continue
        ips = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4" and c.get("active")]
        if ips:
            _memo.update(ip=ips[0], quand=time.time())
            return ips[0]
    return None


def _attribut(tag, nom, valeur):
    v = valeur.encode()
    return struct.pack(">BH", tag, len(nom)) + nom.encode() + struct.pack(">H", len(v)) + v


def interroger(ip):
    """Les attributs IPP utiles de l'imprimante : {nom: [valeurs]}."""
    corps = struct.pack(">BBHI", 2, 0, 0x000B, 1) + b"\x01"           # IPP 2.0, Get-Printer-Attributes
    corps += _attribut(0x47, "attributes-charset", "utf-8") + _attribut(0x48, "attributes-natural-language", "fr")
    corps += _attribut(0x45, "printer-uri", f"ipp://{ip}/ipp/print")
    noms = ["marker-names", "marker-levels", "marker-colors", "printer-state", "printer-state-reasons",
            "printer-make-and-model"]
    corps += _attribut(0x44, "requested-attributes", noms[0])
    for n in noms[1:]:
        corps += _attribut(0x44, "", n)
    corps += b"\x03"
    req = urllib.request.Request(f"http://{ip}:631/ipp/print", data=corps, headers={"Content-Type": "application/ipp"})
    with urllib.request.urlopen(req, timeout=6) as r:
        reponse = r.read()
    pos, res, nom = 8, {}, None
    while pos < len(reponse):
        tag = reponse[pos]
        pos += 1
        if tag == 0x03:
            break
        if tag < 0x10:
            continue
        ln = struct.unpack(">H", reponse[pos:pos + 2])[0]
        pos += 2
        n = reponse[pos:pos + ln].decode("utf-8", "replace")
        pos += ln
        lv = struct.unpack(">H", reponse[pos:pos + 2])[0]
        pos += 2
        v = reponse[pos:pos + lv]
        pos += lv
        if n:
            nom = n
        valeur = struct.unpack(">i", v)[0] if tag in (0x21, 0x23) and lv == 4 else v.decode("utf-8", "replace")
        res.setdefault(nom, []).append(valeur)
    return res


def _nom_cartouche(nom):
    nom = nom.lower()
    for anglais, francais in _COULEURS.items():
        if anglais in nom:
            return francais
    return nom.replace(" ink", "").replace("ink", "").strip() or "inconnue"


def phrase(attributs):
    """La phrase dite par Jarvis, à partir des attributs lus."""
    noms = attributs.get("marker-names") or []
    niveaux = attributs.get("marker-levels") or []
    cartouches = [(_nom_cartouche(n), v) for n, v in zip(noms, niveaux) if isinstance(v, int)]
    morceaux = []
    for nom, niveau in cartouches:
        if niveau < 0:                                           # -1, -2, -3 : niveau inconnu pour l'imprimante
            morceaux.append(f"{nom} : niveau inconnu")
        else:
            morceaux.append(f"{nom} à {niveau} %")
    if morceaux:
        texte = "Niveaux d'encre : " + ", ".join(morceaux) + "."
    else:
        texte = "L'imprimante répond, mais elle ne donne pas ses niveaux d'encre."
    accord = {"noir": "noire"}                                  # « la cartouche noire »
    basses = [accord.get(nom, nom) for nom, niveau in cartouches if 0 <= niveau <= SEUIL_BAS]
    vides = [accord.get(nom, nom) for nom, niveau in cartouches if niveau == 0]
    if vides:
        texte += f" La cartouche {' et '.join(vides)} est vide." if len(vides) == 1 else \
            f" Les cartouches {' et '.join(vides)} sont vides."
    elif basses:
        texte += (f" La cartouche {basses[0]} est presque vide, pense à en racheter une." if len(basses) == 1 else
                  f" Les cartouches {' et '.join(basses)} sont presque vides, pense à en racheter.")
    raisons = [_RAISONS[r] for r in (attributs.get("printer-state-reasons") or [])
               if r in _RAISONS and not (r == "marker-supply-empty" and vides)]
    if raisons:
        texte += " Attention : " + ", ".join(dict.fromkeys(raisons)) + "."
    etat = (attributs.get("printer-state") or [0])[0]
    if etat == 4:
        texte += " Elle est en train d'imprimer."
    return texte


def commande(t):
    t = t.replace("’", "'").lower()
    if not (_ENCRE.search(t) or _IMPRIMANTE.search(t)):
        return None
    if not _QUESTION.search(t):
        return None                                      # « imprime ce document » : pas pour ce module
    if re.search(r"\b(?:stylo|tatouage|seiche|calamar|poulpe|chine|plume|invisible)\b|c'est quoi l'encre|"
                 r"qu'est-ce que l'encre|comment (?:on )?(?:fabrique|fait)|acheter|achète|prix|coûte|coute", t):
        return None                                      # culture générale ou achat : pour Claude
    try:
        ip = _adresse()
        if not ip:
            ip = _adresse(forcer=True)
    except Exception as erreur:
        print("Imprimante (Freebox) :", erreur)
        ip = None
    if not ip:
        return "Je ne vois pas d'imprimante allumée sur le réseau. Elle est peut-être éteinte ou en veille profonde."
    try:
        attributs = interroger(ip)
    except Exception as erreur:
        print("Imprimante :", erreur)
        _memo.update(ip=None, quand=0.0)
        return "L'imprimante ne répond pas. Elle est peut-être en train de s'allumer ou de s'éteindre."
    debut = ("Oui, l'imprimante est allumée. " if re.search(r"\b(?:allumée|allumee|marche|fonctionne|branchée|"
                                                          r"connectée|prête|prete)\b", t) else "")
    return debut + phrase(attributs)
