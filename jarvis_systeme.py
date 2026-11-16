"""
JARVIS - surveillance du PC.

Mesure en continu la charge du processeur, la mémoire utilisée, la carte
graphique et le débit du réseau (une mesure par seconde, très légère). Le réacteur les affiche, et
Jarvis peut les dire à voix haute (« Jarvis, état du PC »).

La température affichée est celle de la puce graphique, la même que dans le
Gestionnaire des tâches de Windows. Sur ce PC, la carte graphique est intégrée
au processeur : c'est donc aussi, en pratique, la température du processeur.
(La température « processeur » seule n'est pas fournie par Windows sans droits
administrateur.)
"""

import ctypes
import os
import threading
import time
from ctypes import wintypes

import psutil

mesures = {"cpu": 0.0, "ram": 0.0, "recu": 0.0, "envoye": 0.0, "pret": False,
           "gpu": None,       # carte graphique en %, ou None si Windows ne la fournit pas
           "reseau": 0.0,     # débit actuel en % du plus fort débit déjà observé sur ce PC
           "temp": None}      # température de la puce graphique en °C, ou None si indisponible
_lance = False

# Le réseau n'a pas de « 100 % » naturel : la référence est le plus fort débit observé,
# retenu d'un démarrage à l'autre (au minimum 500 ko/s pour que le bruit de fond reste bas).
FICHIER_RESEAU_MAX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reseau_max.txt")
RESEAU_MAX_MINIMUM = 500 * 1024
reseau_max = RESEAU_MAX_MINIMUM


def _ouvrir_gpu():
    """Compteur Windows de la carte graphique (le même que le Gestionnaire des tâches)."""
    try:
        import win32pdh
        requete = win32pdh.OpenQuery()
        compteur = win32pdh.AddEnglishCounter(requete, r"\GPU Engine(*)\Utilization Percentage")
        win32pdh.CollectQueryData(requete)
        return win32pdh, requete, compteur
    except Exception as erreur:
        print("Mesure de la carte graphique indisponible :", erreur)
        return None


def _lire_gpu(gpu):
    win32pdh, requete, compteur = gpu
    win32pdh.CollectQueryData(requete)
    par_type = {}
    for nom, valeur in win32pdh.GetFormattedCounterArray(compteur, win32pdh.PDH_FMT_DOUBLE).items():
        genre = nom.rsplit("engtype_", 1)[-1]
        par_type[genre] = par_type.get(genre, 0.0) + valeur
    return min(100.0, max(par_type.values(), default=0.0))


# ---------- Température de la puce graphique (même source que le Gestionnaire des tâches) ----------

class _LUID(ctypes.Structure):
    _fields_ = [("bas", wintypes.DWORD), ("haut", wintypes.LONG)]


class _ADAPTATEUR(ctypes.Structure):
    _fields_ = [("poignee", ctypes.c_uint), ("luid", _LUID),
                ("sources", ctypes.c_ulong), ("precis", wintypes.BOOL)]


class _LISTE(ctypes.Structure):
    _fields_ = [("nombre", ctypes.c_ulong), ("adaptateurs", ctypes.POINTER(_ADAPTATEUR))]


class _PERFORMANCES(ctypes.Structure):
    _fields_ = [("index", ctypes.c_ulong), ("freq_memoire", ctypes.c_ulonglong),
                ("freq_memoire_max", ctypes.c_ulonglong), ("freq_memoire_max_oc", ctypes.c_ulonglong),
                ("bande_memoire", ctypes.c_ulonglong), ("bande_pcie", ctypes.c_ulonglong),
                ("ventilateur", ctypes.c_ulong), ("puissance", ctypes.c_ulong),
                ("temperature", ctypes.c_ulong),      # en dixièmes de degré Celsius
                ("etat", ctypes.c_ubyte)]


class _REQUETE(ctypes.Structure):
    _fields_ = [("poignee", ctypes.c_uint), ("type", ctypes.c_uint),
                ("donnees", ctypes.c_void_p), ("taille", ctypes.c_uint)]


def _lire_temperature(poignee):
    perf = _PERFORMANCES()
    requete = _REQUETE(poignee, 62, ctypes.addressof(perf), ctypes.sizeof(perf))
    if ctypes.windll.gdi32.D3DKMTQueryAdapterInfo(ctypes.byref(requete)) != 0:
        return None
    degres = perf.temperature / 10
    return degres if 0 < degres < 130 else None


def _ouvrir_temperature():
    """Cherche la carte graphique qui fournit sa température. Renvoie sa poignée, ou None."""
    try:
        gdi = ctypes.windll.gdi32
        liste = _LISTE(0, None)
        if gdi.D3DKMTEnumAdapters2(ctypes.byref(liste)) != 0 or not liste.nombre:
            return None
        tableau = (_ADAPTATEUR * liste.nombre)()
        liste.adaptateurs = tableau
        if gdi.D3DKMTEnumAdapters2(ctypes.byref(liste)) != 0:
            return None
        for i in range(liste.nombre):
            if _lire_temperature(tableau[i].poignee) is not None:
                return tableau[i].poignee
    except Exception as erreur:
        print("Température indisponible :", erreur)
    return None


def _reseau():
    recu = envoye = 0
    for nom, c in psutil.net_io_counters(pernic=True).items():
        if "loopback" in nom.lower():
            continue
        recu += c.bytes_recv
        envoye += c.bytes_sent
    return recu, envoye


def _boucle():
    global reseau_max
    psutil.cpu_percent(None)
    prec, t = _reseau(), time.time()
    gpu = _ouvrir_gpu()
    carte = _ouvrir_temperature()
    try:
        with open(FICHIER_RESEAU_MAX, encoding="utf-8") as f:
            reseau_max = max(RESEAU_MAX_MINIMUM, float(f.read()))
    except (OSError, ValueError):
        pass
    max_enregistre = reseau_max
    while True:
        time.sleep(1)
        try:
            actuel, maintenant = _reseau(), time.time()
            dt = max(0.1, maintenant - t)
            recu = max(0.0, (actuel[0] - prec[0]) / dt)
            envoye = max(0.0, (actuel[1] - prec[1]) / dt)
            prec, t = actuel, maintenant
            reseau_max = max(reseau_max, recu + envoye)
            mesures.update(cpu=psutil.cpu_percent(None),
                           ram=psutil.virtual_memory().percent,
                           recu=recu, envoye=envoye,
                           reseau=min(100.0, (recu + envoye) / reseau_max * 100),
                           pret=True)
            if reseau_max > max_enregistre * 1.05:
                max_enregistre = reseau_max
                with open(FICHIER_RESEAU_MAX, "w", encoding="utf-8") as f:
                    f.write(str(int(reseau_max)))
        except Exception:
            pass
        if gpu:
            try:
                mesures["gpu"] = _lire_gpu(gpu)
            except Exception:
                pass
        if carte is not None:
            try:
                mesures["temp"] = _lire_temperature(carte)
            except Exception:
                pass


def demarrer():
    """Lance la mesure en arrière-plan (une seule fois)."""
    global _lance
    if not _lance:
        _lance = True
        threading.Thread(target=_boucle, daemon=True).start()


def debit(octets_par_seconde):
    """Débit lisible : « 850 ko/s », « 1,2 Mo/s »."""
    ko = octets_par_seconde / 1024
    if ko < 1000:
        return f"{ko:.0f} ko/s"
    return f"{ko / 1024:.1f} Mo/s".replace(".", ",")


def _taille_parlee(octets):
    go = octets / 1024 ** 3
    if go >= 1:
        return f"{go:.1f} gigaoctets".replace(".", ",").replace(",0 ", " ")
    return f"{octets / 1024 ** 2:.0f} mégaoctets"


def _nom(processus):
    nom = processus or "inconnu"
    return nom[:-4] if nom.lower().endswith(".exe") else nom


def rapport():
    """Phrase d'état du PC : processeur, mémoire, programmes gourmands, disque."""
    processus = []
    for p in psutil.process_iter(["name"]):
        try:
            p.cpu_percent(None)
            processus.append(p)
        except Exception:
            pass
    time.sleep(0.6)
    coeurs = psutil.cpu_count() or 1
    cpu_par_nom, ram_par_nom = {}, {}
    for p in processus:
        try:
            nom = _nom(p.info["name"])
            if nom.lower() in ("system idle process", "idle"):
                continue
            cpu_par_nom[nom] = cpu_par_nom.get(nom, 0.0) + p.cpu_percent(None) / coeurs
            ram_par_nom[nom] = ram_par_nom.get(nom, 0) + p.memory_info().rss
        except Exception:
            pass
    cpu = mesures["cpu"] if mesures["pret"] else psutil.cpu_percent(0.3)
    ram = psutil.virtual_memory().percent
    phrases = [f"Le processeur est à {cpu:.0f} pour cent et la mémoire à {ram:.0f} pour cent."]
    if mesures["gpu"] is not None:
        phrases.append(f"La carte graphique est à {mesures['gpu']:.0f} pour cent.")
    if mesures["temp"] is not None:
        phrases.append(f"La température de la puce est de {mesures['temp']:.0f} degrés.")
    if cpu_par_nom:
        nom, valeur = max(cpu_par_nom.items(), key=lambda x: x[1])
        if valeur >= 3:
            phrases.append(f"Le programme qui sollicite le plus le processeur est {nom}, "
                           f"avec {valeur:.0f} pour cent.")
    if ram_par_nom:
        nom, valeur = max(ram_par_nom.items(), key=lambda x: x[1])
        phrases.append(f"Celui qui occupe le plus de mémoire est {nom}, avec {_taille_parlee(valeur)}.")
    try:
        libre = psutil.disk_usage("C:\\").free
        phrases.append(f"Il reste {_taille_parlee(libre)} libres sur le disque C.")
    except Exception:
        pass
    return " ".join(phrases)
