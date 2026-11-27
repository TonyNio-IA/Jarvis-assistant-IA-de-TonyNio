# -*- coding: utf-8 -*-
"""Bac à sable pour essayer des phrases d'ACTION sans rien faire sur le PC.

Copie les programmes de Jarvis dans un dossier temporaire (les fichiers personnels de C:\\Jarvis ne sont jamais
touchés), puis bloque, AVANT de charger Jarvis : les lancements de programmes, Internet et le réseau local (télé, PS5,
Freebox), le clavier et la souris simulés, les fenêtres (devant, déplacées, fermées), le presse-papiers, le son, la veille
et l'extinction, les fenêtres Tk, le registre en écriture et les captures d'écran. Chaque action bloquée est notée.
  python bac_a_sable.py fichier_de_phrases.txt   (une phrase par ligne)"""
import ctypes, glob, json, os, shutil, socket, subprocess, sys, tempfile

SOURCE = r"C:\Jarvis"
bloque = []


def noter(quoi):
    bloque.append(quoi)


# ---------- 1. une copie des programmes, à part ----------
DOSSIER = tempfile.mkdtemp(prefix="jarvis-bac-a-sable-")
for f in glob.glob(os.path.join(SOURCE, "jarvis_*.py")):
    shutil.copy(f, DOSSIER)
for nom in ("config.json", "ville.txt", "applications.json", "accueil.json", "reglages_voix.json", "rapports.json"):
    if os.path.exists(os.path.join(SOURCE, nom)):
        shutil.copy(os.path.join(SOURCE, nom), DOSSIER)
os.chdir(DOSSIER)
sys.path.insert(0, DOSSIER)


# ---------- 2. tout ce qui agit est bloqué ----------
class _Fini:
    returncode = 0
    stdout = b""
    stderr = b""
    pid = 0

    def communicate(self, *a, **k):
        return b"", b""

    def wait(self, *a, **k):
        return 0

    def poll(self):
        return 0

    def kill(self):
        pass


def _faux_processus(args, *a, **k):
    noter("programme : " + (" ".join(map(str, args)) if isinstance(args, (list, tuple)) else str(args))[:90])
    return _Fini()


import asyncio  # noqa: E402,F401  (chargé avant : il hérite du vrai Popen)
import ctypes.util  # noqa: E402,F401
try:
    import sounddevice  # noqa: F401  (chargé avant : il lit ses bibliothèques)
    import numpy  # noqa: F401
except Exception:
    pass


class _FauxPopen(subprocess.Popen):
    def __init__(self, args, *a, **k):
        noter("programme : " + (" ".join(map(str, args)) if isinstance(args, (list, tuple)) else str(args))[:90])
        self.returncode, self.stdout, self.stderr, self.pid, self.args = 0, None, None, 0, args
        self.stdin = None

    def communicate(self, *a, **k):
        return b"", b""

    def wait(self, *a, **k):
        return 0

    def poll(self):
        return 0

    def kill(self):
        pass

    terminate = kill

    def __del__(self):
        pass


subprocess.Popen = _FauxPopen
subprocess.run = _faux_processus
subprocess.call = lambda *a, **k: (_faux_processus(*a, **k), 0)[1]
subprocess.check_call = subprocess.call
subprocess.check_output = lambda *a, **k: (_faux_processus(*a, **k), b"")[1]
os.startfile = lambda *a, **k: noter("ouvre : " + str(a[0])[:90])
os.system = lambda *a, **k: (noter("commande : " + str(a)[:90]), 0)[1]


def _pas_de_reseau(self, *a, **k):
    raise OSError("réseau bloqué (bac à sable)")


socket.socket.connect = _pas_de_reseau
socket.socket.connect_ex = lambda self, *a, **k: 1
socket.create_connection = lambda *a, **k: _pas_de_reseau(None)

BLOQUEES = {"keybd_event", "SendInput", "mouse_event", "SetCursorPos", "PostMessageW", "PostMessageA", "SendMessageW",
            "SendMessageA", "SendMessageTimeoutW", "SetForegroundWindow", "ShowWindow", "ShowWindowAsync", "SetWindowPos",
            "MoveWindow", "LockWorkStation", "SetSuspendState", "ExitWindowsEx", "OpenClipboard", "EmptyClipboard",
            "SetClipboardData", "SystemParametersInfoW", "SetThreadExecutionState", "BringWindowToTop", "SwitchToThisWindow",
            "CloseWindow", "DestroyWindow", "SetFocus", "SetActiveWindow", "RegisterHotKey", "AttachThreadInput",
            "SetMonitorBrightness", "SetVCPFeature", "SHEmptyRecycleBinW", "InitiateSystemShutdownExW", "RegSetValueExW"}


class _Dll:
    def __init__(self, nom, vraie):
        self._nom, self._vraie = nom, vraie

    def __getitem__(self, fonction):
        return self.__getattr__(fonction)

    def __getattr__(self, fonction):
        if fonction in BLOQUEES:
            def bloquee(*a, **k):
                noter(f"{self._nom}.{fonction}")
                return 1
            return bloquee
        return getattr(self._vraie, fonction)


class _Windll:
    def __init__(self, vraie):
        self._vraie = vraie

    def __getattr__(self, nom):
        return _Dll(nom, getattr(self._vraie, nom))


ctypes.windll = _Windll(ctypes.windll)
_WinDLL = ctypes.WinDLL
ctypes.WinDLL = lambda nom, *a, **k: _Dll(nom, _WinDLL(nom, *a, **k))

import winreg
winreg.SetValueEx = lambda *a, **k: noter("registre : écriture")
winreg.DeleteValue = lambda *a, **k: noter("registre : effacement")
import webbrowser
webbrowser.open = lambda *a, **k: noter("navigateur : " + str(a[0])[:80])
try:
    import tkinter
    class _PasDeTk:
        def __init__(self, *a, **k):
            noter("fenêtre Tk")
            raise RuntimeError("fenêtre bloquée (bac à sable)")
    tkinter.Tk = _PasDeTk
    tkinter.Toplevel = _PasDeTk
except Exception:
    pass
try:
    from pycaw import pycaw

    class _FauxVolume:                     # le vrai volume n'est jamais touché : on note ce qui aurait été fait
        def GetMasterVolumeLevelScalar(self):
            return 0.5

        def SetMasterVolumeLevelScalar(self, v, *a):
            noter(f"son : volume à {round(v * 100)}")

        def SetMute(self, m, *a):
            noter("son : coupé" if m else "son : remis")

        def GetMute(self):
            return 0

    class _FauxHautParleur:
        EndpointVolume = _FauxVolume()

    pycaw.AudioUtilities.GetSpeakers = staticmethod(lambda *a, **k: _FauxHautParleur())
    pycaw.AudioUtilities.GetAllSessions = staticmethod(lambda *a, **k: [])
except Exception:
    pass
try:
    from PIL import ImageGrab
    ImageGrab.grab = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("capture bloquée"))
except Exception:
    pass
try:
    import comtypes.client
    comtypes.client.CreateObject = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("automatisation bloquée"))
except Exception:
    pass
try:
    import sounddevice
    sounddevice.play = lambda *a, **k: noter("son : lecture")
except Exception:
    pass

# ---------- 3. Jarvis, comme sur un PC sans Claude ----------
import jarvis_claude_reglages
jarvis_claude_reglages.installe = lambda: False
import jarvis_commandes as c
import jarvis_assistants
jarvis_assistants.utilisable_maintenant = lambda: False
SECOURS = ("Je n'ai pas Claude", "C'est ce que dit Wikipédia", "Je n'ai pas Claude sur ce PC")


def essayer(phrase):
    del bloque[:]
    try:
        r = c.commande_instantanee([phrase], annoncer=lambda *a, **k: None)
    except Exception as e:
        r = f"ERREUR {type(e).__name__}: {e}"
    c._attente = None
    if not r:            # sans Claude, une application introuvable reçoit quand même une réponse de Jarvis
        try:
            r = jarvis_assistants.reponse_action(phrase, False)
        except Exception:
            r = None
    traitee = bool(r) and not str(r).startswith(SECOURS) and "Wikipédia" not in str(r)
    return traitee, r, list(bloque)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    phrases = [l.strip() for l in open(sys.argv[1], encoding="utf-8") if l.strip() and not l.startswith("#")]
    resultats = []
    for p in phrases:
        traitee, r, actions = essayer(p)
        resultats.append({"phrase": p, "traitee": traitee, "reponse": r, "actions": actions})
    sortie = sys.argv[2] if len(sys.argv) > 2 else os.path.join(SOURCE, "tests", "bac_a_sable_resultats.json")
    json.dump(resultats, open(sortie, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    n = sum(r["traitee"] for r in resultats)
    print(f"{n} / {len(resultats)} demandes traitées sans Claude.")
    for r in resultats:
        if not r["traitee"]:
            print("  NON :", r["phrase"], "->", (str(r["reponse"]) or "")[:90])
    shutil.rmtree(DOSSIER, ignore_errors=True)
