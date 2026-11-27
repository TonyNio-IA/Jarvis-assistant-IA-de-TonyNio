# -*- coding: utf-8 -*-
"""
JARVIS - raccourci clavier pour écrire à Jarvis : Ctrl + Alt + J, depuis n'importe quelle fenêtre.

La fenêtre de discussion s'ouvre, prête pour une demande écrite (comme un clic dedans).
Le raccourci est demandé à Windows (RegisterHotKey) : Jarvis ne lit pas le clavier. S'il est déjà pris par un autre
programme, Windows le refuse : Jarvis le note dans son journal et continue sans raccourci.
"""

import ctypes
import ctypes.wintypes
import threading

ACTIF = True
TOUCHE = 0x4A                 # J
MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
WM_HOTKEY = 0x0312
NOM = "Ctrl + Alt + J"
_demarre = False
etat = "non demandé"          # pour le diagnostic : « actif », « refusé par Windows », « non demandé »


def demarrer(action):
    """Lance l'écoute du raccourci en arrière-plan ; « action » est appelée à chaque appui."""
    global _demarre
    if _demarre or not ACTIF:
        return
    _demarre = True

    def boucle():
        global etat
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, TOUCHE):
            etat = "refusé par Windows"
            print(f"(Raccourci {NOM} : déjà pris par un autre programme, Jarvis s'en passe.)")
            return
        etat = "actif"
        print(f"(Raccourci {NOM} : prêt, il ouvre la fenêtre pour écrire à Jarvis.)")
        message = ctypes.wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY:
                    try:
                        action()
                    except Exception as erreur:
                        print("Raccourci :", type(erreur).__name__, erreur)
        finally:
            user32.UnregisterHotKey(None, 1)

    threading.Thread(target=boucle, daemon=True, name="raccourci").start()


def ouvrir_saisie():
    """L'action du raccourci : la fenêtre de discussion passe devant et attend une demande écrite."""
    import jarvis_affichage
    jarvis_affichage.demande_saisie = True                 # traité par la boucle d'affichage (son propre fil)
    poignee = getattr(jarvis_affichage, "poignee_fenetre", None)
    if poignee:
        try:                                               # Windows autorise ce passage devant : il suit un raccourci
            ctypes.windll.user32.SetForegroundWindow(ctypes.c_void_p(poignee))
        except Exception:
            pass
