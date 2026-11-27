"""Essai : un .bat lancé avec la console cachée (comme la mise à jour 1.42) affiche-t-il quand même une fenêtre claire ?
Un faux installateur ouvre un petit formulaire pendant 6 secondes ; on cherche ensuite une fenêtre visible
portant son titre, et on vérifie qu'aucune fenêtre de console n'est visible pour ce processus."""
import os
import subprocess
import tempfile
import time

dossier = tempfile.mkdtemp()
lot = os.path.join(dossier, "faux.bat")
with open(lot, "w", encoding="utf-8", newline="") as f:
    f.write('@echo off\r\npowershell -NoProfile -STA -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; '
            '$f=New-Object Windows.Forms.Form; $f.Text=\'ESSAI-JARVIS-FENETRE\'; $f.TopMost=$true; '
            '$t=New-Object Windows.Forms.Timer; $t.Interval=6000; $t.Add_Tick({$f.Close()}); $t.Start(); '
            '$f.ShowDialog() | Out-Null"\r\n')
p = subprocess.Popen([os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), "/c", lot],
                     cwd=dossier, creationflags=0x08000000)
time.sleep(3)
vu = subprocess.run(["powershell", "-NoProfile", "-Command",
                     "(Get-Process | Where-Object { $_.MainWindowTitle -eq 'ESSAI-JARVIS-FENETRE' }).Count"],
                    capture_output=True, text=True).stdout.strip()
consoles = subprocess.run(["powershell", "-NoProfile", "-Command",
                           "(Get-Process cmd,conhost -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*faux.bat*' }).Count"],
                          capture_output=True, text=True).stdout.strip()
p.wait(timeout=20)
print("fenêtre claire visible :", vu, "| console visible :", consoles)
ok = vu not in ("", "0") and consoles in ("", "0")
print("RESULTAT :", "TOUT EST BON" if ok else "ECHEC")
