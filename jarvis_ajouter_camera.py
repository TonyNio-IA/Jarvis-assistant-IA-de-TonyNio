# -*- coding: utf-8 -*-
"""
JARVIS - relier une caméra Imou (ou Dahua) à Jarvis, sans que personne d'autre ne voie son code.

Lance ce programme, donne un nom simple (« jardin », « portail »…), puis tape le code de sécurité de la caméra
(étiquette sous la caméra, ou le mot de passe que tu lui as donné dans l'application Imou). Le code ne s'affiche
pas pendant la frappe. Le programme l'essaie sur chaque caméra du réseau, trouve celle qui l'accepte, puis range
le code dans le Gestionnaire d'identification de Windows (cible « Jarvis-Camera-… »). Le nom et la caméra
choisie sont notés dans cameras.json (sans aucun code), gardé sur ce PC et jamais publié.
"""
import ctypes
import ctypes.wintypes as wt
import getpass
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jarvis_config
import jarvis_freebox

FICHIER = jarvis_config.chemin("cameras.json")
FABRICANTS = ("dahua", "huacheng", "imou")


class CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD), ("CredentialBlob", ctypes.c_void_p),
                ("Persist", wt.DWORD), ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wt.LPWSTR), ("UserName", wt.LPWSTR)]


def ranger(cible, utilisateur, secret):
    blob = secret.encode("utf-16-le")
    tampon = ctypes.create_string_buffer(blob, len(blob))
    c = CREDENTIAL(Type=1, TargetName=cible, UserName=utilisateur, CredentialBlobSize=len(blob),
                   CredentialBlob=ctypes.cast(tampon, ctypes.c_void_p), Persist=2)
    return bool(ctypes.windll.advapi32.CredWriteW(ctypes.byref(c), 0))


def cameras_du_reseau():
    liste = []
    for h in jarvis_freebox._lire("lan/browser/pub/") or []:
        if not h.get("active") or not any(m in (h.get("vendor_name") or "").lower() for m in FABRICANTS):
            continue
        mac = (h.get("l2ident") or {}).get("id", "").lower()
        ips = [c["addr"] for c in (h.get("l3connectivities") or []) if c.get("af") == "ipv4" and c.get("active")]
        if mac and ips:
            liste.append({"mac": mac, "ip": ips[0], "modele": h.get("primary_name", "")})
    return liste


def code_accepte(ip, code):
    import av
    adresse = (f"rtsp://admin:{urllib.parse.quote(code, safe='')}@{ip}:554/cam/realmonitor?channel=1&subtype=1")
    try:
        with av.open(adresse, options={"rtsp_transport": "tcp", "stimeout": "4000000", "timeout": "4000000"}, timeout=6):
            return True
    except Exception:
        return False


def main():
    print("Recherche des caméras sur le réseau…")
    cameras = cameras_du_reseau()
    if not cameras:
        print("Aucune caméra trouvée sur le réseau."); return
    try:
        with open(FICHIER, encoding="utf-8") as f:
            reglees = json.load(f)
    except (OSError, ValueError):
        reglees = {}
    deja = {v["mac"] for v in reglees.values()}
    print(f"{len(cameras)} caméras trouvées, dont {sum(1 for c in cameras if c['mac'] in deja)} déjà reliées.\n")
    while True:
        nom = input("Nom de la caméra (ex. jardin), ou Entrée pour terminer : ").strip().lower()
        if not nom:
            break
        code = getpass.getpass("Code de sécurité (rien ne s'affiche pendant la frappe) : ").strip()
        if not code:
            continue
        print("Essai sur chaque caméra…")
        trouvee = next((c for c in cameras if c["mac"] not in deja and code_accepte(c["ip"], code)), None)
        if not trouvee:
            print("Aucune caméra n'accepte ce code. Vérifie-le (majuscules comprises) et recommence.\n")
            continue
        if ranger("Jarvis-Camera-" + trouvee["mac"], nom, code):
            reglees[nom] = {"mac": trouvee["mac"], "modele": trouvee["modele"]}
            deja.add(trouvee["mac"])
            with open(FICHIER, "w", encoding="utf-8") as f:
                json.dump(reglees, f, ensure_ascii=False, indent=1)
            print(f"C'est fait : « {nom} » est reliée ({trouvee['modele']}).\n")
        else:
            print("Le code n'a pas pu être rangé dans Windows.\n")
    print("Caméras reliées :", ", ".join(reglees) or "aucune")
    input("Appuie sur Entrée pour fermer.")


if __name__ == "__main__":
    main()
