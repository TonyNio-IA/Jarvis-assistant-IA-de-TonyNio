import sys, os, time, socket, subprocess
sys.path.insert(0, r"C:\Jarvis"); os.chdir(r"C:\Jarvis")
socket.socket.bind = lambda *a, **k: None; socket.socket.listen = lambda *a, **k: None
import jarvis_reacteur, jarvis_affichage, jarvis_reglages_ui as R
import tkinter as tk
R._ecrire = lambda d: None
orig = tk.Tk
def tous(w):
    yield w
    for c in w.winfo_children():
        yield from tous(c)
def espion(*a, **k):
    racine = orig(*a, **k)
    racine.geometry("+10+10")
    def etape1():
        for w in list(tous(racine)):
            if isinstance(w, tk.Label) and w.cget("text").strip() == "À propos":
                w.event_generate("<Button-1>")
                break
        racine.after(800, etape2)
    def etape2():
        for w in list(tous(racine)):
            if isinstance(w, tk.Label) and w.cget("text") == "Vérifier les mises à jour":
                w.event_generate("<Button-1>")
                break
        racine.after(5000, etape3)
    def etape3():
        textes = [w.cget("text") for w in list(tous(racine)) if isinstance(w, tk.Label)]
        print("etat:", [t for t in textes if "jour" in t or "GitHub" in t or "version" in t.lower()], flush=True)
        racine.lift(); racine.attributes("-topmost", True); racine.update()
        x, y, w, h = racine.winfo_rootx(), racine.winfo_rooty(), racine.winfo_width(), racine.winfo_height()
        os.makedirs(r"C:\Jarvis\tests\rendus", exist_ok=True)
        subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", r"C:\Jarvis\tests\capture_zone.ps1", str(x), str(y), str(w), str(h), r"C:\Jarvis\tests\rendus\a_propos.png"])
        racine.destroy()
    racine.after(1500, etape1)
    return racine
tk.Tk = espion
R._fenetre_principale()
