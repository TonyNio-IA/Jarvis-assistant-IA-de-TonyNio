# -*- coding: utf-8 -*-
"""
JARVIS - le coffre : ranger ou retirer un secret (mot de passe d'application, lien privé d'agenda) dans le
Gestionnaire d'identification de Windows. Rien n'est écrit dans un fichier, rien ne part sur Internet.
La lecture se fait par jarvis_mails.identifiants(cible).
"""

import ctypes
import ctypes.wintypes as wt

TAILLE_MAX = 1200          # caractères : Windows refuse un secret de plus de 2 560 octets


class _CREDENTIAL(ctypes.Structure):
    _fields_ = [("Flags", wt.DWORD), ("Type", wt.DWORD), ("TargetName", wt.LPWSTR), ("Comment", wt.LPWSTR),
                ("LastWritten", wt.FILETIME), ("CredentialBlobSize", wt.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)), ("Persist", wt.DWORD),
                ("AttributeCount", wt.DWORD), ("Attributes", ctypes.c_void_p), ("TargetAlias", wt.LPWSTR),
                ("UserName", wt.LPWSTR)]


def ranger(cible, utilisateur, secret):
    """Range (ou remplace) le secret sous le nom « cible ». Renvoie True si Windows l'a accepté."""
    if not cible or not secret or len(secret) > TAILLE_MAX:
        return False
    try:
        octets = secret.encode("utf-16-le")           # comme la commande cmdkey de Windows
        tampon = (ctypes.c_ubyte * len(octets)).from_buffer_copy(octets)
        c = _CREDENTIAL(Type=1, TargetName=cible, UserName=utilisateur or "", CredentialBlobSize=len(octets),
                        CredentialBlob=ctypes.cast(tampon, ctypes.POINTER(ctypes.c_ubyte)), Persist=2)
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIAL), wt.DWORD]
        advapi.CredWriteW.restype = wt.BOOL
        return bool(advapi.CredWriteW(ctypes.byref(c), 0))
    except Exception as erreur:
        print("Coffre :", type(erreur).__name__, erreur)
        return False


def noms(prefixe="Jarvis-"):
    """Les noms rangés dans le coffre de Windows qui commencent par ce préfixe."""
    try:
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredEnumerateW.argtypes = [wt.LPCWSTR, wt.DWORD, ctypes.POINTER(wt.DWORD),
                                          ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(_CREDENTIAL)))]
        advapi.CredEnumerateW.restype = wt.BOOL
        advapi.CredFree.argtypes = [ctypes.c_void_p]
        nombre, liste = wt.DWORD(0), ctypes.POINTER(ctypes.POINTER(_CREDENTIAL))()
        if not advapi.CredEnumerateW(prefixe + "*", 0, ctypes.byref(nombre), ctypes.byref(liste)):
            return []
        try:
            return [liste[i].contents.TargetName for i in range(nombre.value)
                    if (liste[i].contents.TargetName or "").startswith(prefixe)]
        finally:
            advapi.CredFree(liste)
    except Exception as erreur:
        print("Coffre :", type(erreur).__name__, erreur)
        return []


def tout_retirer(prefixe="Jarvis-"):
    """Retire du coffre de Windows tout ce que Jarvis y a rangé (mots de passe, liens d'agenda, jetons).
    Appelé à la désinstallation quand l'utilisateur ne garde pas ses fichiers. Renvoie le nombre de retraits."""
    if len(prefixe) < 7:                  # garde-fou : jamais un préfixe qui toucherait autre chose que Jarvis
        return 0
    return sum(1 for nom in noms(prefixe) if retirer(nom))


def retirer(cible):
    """Retire le secret rangé sous « cible ». Renvoie True s'il n'y est plus (retiré, ou déjà absent)."""
    try:
        advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi.CredDeleteW.argtypes = [wt.LPCWSTR, wt.DWORD, wt.DWORD]
        advapi.CredDeleteW.restype = wt.BOOL
        if advapi.CredDeleteW(cible, 1, 0):
            return True
        return ctypes.get_last_error() == 1168        # ERROR_NOT_FOUND : il n'y avait rien
    except Exception as erreur:
        print("Coffre :", type(erreur).__name__, erreur)
        return False
