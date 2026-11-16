"""
JARVIS - surveillance du PC.

Mesure en continu la charge du processeur, la mémoire utilisée et le débit
du réseau (une mesure par seconde, très légère). Le réacteur les affiche, et
Jarvis peut les dire à voix haute (« Jarvis, état du PC »).

La température du processeur n'est pas disponible : sur ce PC, Windows ne la
fournit pas sans un programme lancé en administrateur.
"""

import threading
import time

import psutil

mesures = {"cpu": 0.0, "ram": 0.0, "recu": 0.0, "envoye": 0.0, "pret": False}
_lance = False


def _reseau():
    recu = envoye = 0
    for nom, c in psutil.net_io_counters(pernic=True).items():
        if "loopback" in nom.lower():
            continue
        recu += c.bytes_recv
        envoye += c.bytes_sent
    return recu, envoye


def _boucle():
    psutil.cpu_percent(None)
    prec, t = _reseau(), time.time()
    while True:
        time.sleep(1)
        try:
            actuel, maintenant = _reseau(), time.time()
            dt = max(0.1, maintenant - t)
            mesures.update(cpu=psutil.cpu_percent(None),
                           ram=psutil.virtual_memory().percent,
                           recu=max(0.0, (actuel[0] - prec[0]) / dt),
                           envoye=max(0.0, (actuel[1] - prec[1]) / dt),
                           pret=True)
            prec, t = actuel, maintenant
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
