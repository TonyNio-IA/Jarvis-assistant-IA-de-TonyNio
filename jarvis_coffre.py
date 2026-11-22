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
