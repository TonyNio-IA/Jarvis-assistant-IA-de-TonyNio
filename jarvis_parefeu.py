# -*- coding: utf-8 -*-
"""
JARVIS - le pare-feu de Windows et les tablettes.

Pour qu'une tablette joigne Jarvis, Windows doit laisser entrer les connexions sur le port de Jarvis.
Une seule règle, nommée « Jarvis - tablettes » : seulement ce port, seulement depuis les réseaux de la maison
(adresses privées : Wi-Fi de la maison, VPN de la box). Elle est ajoutée par l'installateur, ou à la voix
(« Jarvis, autorise les tablettes ») ; Windows demande une seule fois l'autorisation. La désinstallation la retire.
Lire la règle ne demande aucune autorisation.
"""
import ipaddress
import socket
import subprocess

NOM_REGLE = "Jarvis - tablettes"
PORT = 47826
RESEAUX = "LocalSubnet,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
_SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _netsh(*args):
    r = subprocess.run(["netsh", "advfirewall", "firewall", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", creationflags=_SANS_FENETRE, timeout=20)
    return r.returncode, r.stdout


def regle_presente():
    """Vrai si la règle « Jarvis - tablettes » existe et est active."""
    try:
        code, sortie = _netsh("show", "rule", f"name={NOM_REGLE}")
        return code == 0 and NOM_REGLE in sortie
    except Exception:
        return False


def parefeu_actif():
    """Vrai si le pare-feu de Windows est allumé pour au moins un type de réseau (sinon, rien n'est bloqué)."""
    try:
        r = subprocess.run(["netsh", "advfirewall", "show", "allprofiles", "state"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", creationflags=_SANS_FENETRE, timeout=20)
        import re
        return bool(re.search(r"\b(?:ON|ACTIF|ACTIVÉ|ACTIVE)\b", r.stdout.upper()))
    except Exception:
        return True


def _eleve(commande):
    """Lance une commande netsh avec l'autorisation de Windows (une fenêtre « Oui / Non » s'affiche). Attend sa fin."""
    ps = ("$p = Start-Process -FilePath netsh -ArgumentList '" + commande.replace("'", "''") + "' -Verb RunAs "
          "-WindowStyle Hidden -Wait -PassThru; exit $p.ExitCode")
    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                       creationflags=_SANS_FENETRE, timeout=300)
    return r.returncode


def ajouter():
    """Ajoute la règle (Windows demande l'autorisation). Renvoie vrai si elle est en place ensuite."""
    if regle_presente():
        return True
    try:
        _eleve(f'advfirewall firewall add rule name="{NOM_REGLE}" dir=in action=allow protocol=TCP '
               f'localport={PORT} remoteip={RESEAUX} profile=any')
    except Exception as erreur:
        print("Pare-feu : ajout impossible :", erreur)
    return regle_presente()


def retirer():
    """Retire la règle (désinstallation). Renvoie vrai si elle n'existe plus."""
    if not regle_presente():
        return True
    try:
        _eleve(f'advfirewall firewall delete rule name="{NOM_REGLE}"')
    except Exception as erreur:
        print("Pare-feu : retrait impossible :", erreur)
    return not regle_presente()


def adresse_locale():
    """L'adresse de ce PC sur le réseau de la maison (celle que la tablette doit joindre), ou ""."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 9))             # aucun paquet ne part : on demande seulement la route
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return ""


def diagnostic():
    """Ce qui peut empêcher une tablette de joindre Jarvis, en phrases simples (liste vide si tout va bien)."""
    soucis = []
    ip = adresse_locale()
    if not ip or ip.startswith("127."):
        soucis.append("Ce PC n'est relié à aucun réseau : branche-le au Wi-Fi ou à la box.")
    else:
        try:
            if not ipaddress.ip_address(ip).is_private:
                soucis.append("Ce PC n'est pas sur un réseau de maison (son adresse n'est pas privée) : "
                              "la tablette ne pourra pas le joindre.")
        except ValueError:
            pass
    if parefeu_actif() and not regle_presente():
        soucis.append("Pour être sûr que le pare-feu de Windows laisse passer la tablette, dis « Jarvis, autorise les tablettes ».")
    return soucis


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "ajouter":
        sys.exit(0 if ajouter() else 1)
    if len(sys.argv) > 1 and sys.argv[1] == "retirer":
        sys.exit(0 if retirer() else 1)
    print("règle présente :", regle_presente(), "| pare-feu actif :", parefeu_actif(), "| adresse :", adresse_locale())
    print("diagnostic :", diagnostic() or "rien à signaler")
