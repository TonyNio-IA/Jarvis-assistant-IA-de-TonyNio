# -*- coding: utf-8 -*-
"""
JARVIS - désinstallation complète.

Réglages de Jarvis, onglet « À propos », bouton « Désinstaller Jarvis » (ou l'installateur, choix 2) :
  1. une première fenêtre demande quoi faire des fichiers personnels (tout ce que Jarvis a appris) :
     les garder dans un dossier du Bureau, ou les supprimer (avec, si on veut, une copie compressée) ;
  2. une dernière fenêtre récapitule tout ce qui va être retiré et demande d'écrire « confirmer » ;
  3. Jarvis s'arrête, puis un petit programme de Windows (PowerShell, rangé dans le dossier temporaire)
     retire tout ce que l'installateur avait mis en place : le dossier de Jarvis, les raccourcis du Bureau
     et du démarrage, le repère dans le registre, les fichiers temporaires, et, si c'est l'installateur de
     Jarvis qui les avait installés, Python, Claude Code et les composants Microsoft Visual C++.

L'installateur note ce qu'il a réellement installé (registre, clé Software\\Jarvis-TonyNio). Ce qui était déjà
sur le PC avant Jarvis, ou dont l'origine est inconnue (Jarvis installé avant cette version),
est signalé comme tel dans la fenêtre de confirmation. Toutes les cases y sont cochées d'office (choix de TonyNio :
tout revient comme avant) ; l'utilisateur décoche ce qu'il utilise pour autre chose.

Rien n'est supprimé tant que le mot « confirmer » n'a pas été écrit et le bouton cliqué.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile

import jarvis_config

CLE_REGISTRE = r"Software\Jarvis-TonyNio"
MOT = "confirmer"
NOM_DOSSIER_GARDE = "Jarvis - fichiers personnels"
# Tout ce que Jarvis a appris ou que l'utilisateur a réglé (jamais de programme)
FICHIERS_PERSONNELS = ("config.json", "ville.txt", "memoire.json", "rappels.json", "rappels_faits.json", "applications.json",
                       "notes.txt", "position.txt", "volumes.json", "liste.json", "reglages_voix.json", "enfant.json",
                       "apparence.json", "accueil.json", "profils.json", "calendrier.json", "messages.json",
                       "preferences.json", "corrections.json", "infos.json", "personnalite.json", "recette.json",
                       "vigilance.json", "cameras.json", "tablette.json")
DOSSIERS_PERSONNELS = ("profils", "tele", "mot_appel", "tablette")   # tablette : historique et réglages de la tablette
CLAUDE_EXE = os.path.expanduser(r"~\.local\bin\claude.exe")

FOND, PANNEAU, PANNEAU2 = "#05090e", "#0b121b", "#111b27"
TEXTE, DISCRET, ALERTE = "#d7e3f4", "#7d8ca3", "#ff5d6c"
POLICE = ("Segoe UI", 10)


# ---------- Où sont les choses ----------

def _dossier_windows(numero, secours):
    """Un dossier de Windows (Bureau, Démarrage...), même déplacé (OneDrive)."""
    try:
        import ctypes
        tampon = ctypes.create_unicode_buffer(600)
        if ctypes.windll.shell32.SHGetFolderPathW(None, numero, None, 0, tampon) == 0 and tampon.value:
            return tampon.value
    except Exception:
        pass
    return secours


def bureau():
    return _dossier_windows(0x10, os.path.join(os.path.expanduser("~"), "Desktop"))


def _demarrage():
    return _dossier_windows(0x07, os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup"))


def _images():
    return _dossier_windows(0x27, os.path.join(os.path.expanduser("~"), "Pictures"))


def _documents():
    return _dossier_windows(0x05, os.path.join(os.path.expanduser("~"), "Documents"))


def trace():
    """Ce que l'installateur a noté avoir installé lui-même : {"python": bool, "vc": bool, "claude": bool}."""
    notes = {"python": False, "vc": False, "claude": False}
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, CLE_REGISTRE) as cle:
            for nom, valeur in (("python", "PythonInstalle"), ("vc", "VCInstalle"), ("claude", "ClaudeInstalle")):
                try:
                    notes[nom] = str(winreg.QueryValueEx(cle, valeur)[0]) == "1"
                except OSError:
                    pass
    except Exception:
        pass
    return notes


def _programme_installe(ruches, motif):
    """Vrai si Windows connaît un programme installé dont le nom correspond (lecture seule du registre)."""
    try:
        import winreg
    except ImportError:
        return False
    for ruche, chemin, vue in ruches:
        try:
            with winreg.OpenKey(ruche, chemin, 0, winreg.KEY_READ | vue) as cle:
                for i in range(winreg.QueryInfoKey(cle)[0]):
                    try:
                        with winreg.OpenKey(cle, winreg.EnumKey(cle, i)) as sous:
                            if re.search(motif, str(winreg.QueryValueEx(sous, "DisplayName")[0])):
                                return True
                    except OSError:
                        continue
        except OSError:
            continue
    return False


def composants():
    """Les programmes installés à côté de Jarvis : [(clé, libellé, installé par Jarvis ?)], seulement s'ils sont là."""
    import winreg
    desinstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    notes = trace()
    liste = []
    if _programme_installe([(winreg.HKEY_CURRENT_USER, desinstall, 0)], r"^Python 3\.14\.\d+ \(64-bit\)$"):
        liste.append(("python", "Python 3.14 et les téléchargements gardés par son outil d'installation (pip)", notes["python"]))
    if os.path.exists(CLAUDE_EXE):
        liste.append(("claude", "Claude Code, ses réglages et la connexion à ton compte Claude", notes["claude"]))
    if _programme_installe([(winreg.HKEY_LOCAL_MACHINE, desinstall, winreg.KEY_WOW64_64KEY),
                            (winreg.HKEY_LOCAL_MACHINE, desinstall, winreg.KEY_WOW64_32KEY)],
                           r"^Microsoft Visual C\+\+ 20\d\d(-20\d\d)? Redistributable \(x64\)"):
        liste.append(("vc", "Les composants Microsoft Visual C++ (Windows demandera ton autorisation)", notes["vc"]))
    return liste


def personnels_presents(dossier=None):
    dossier = dossier or jarvis_config.DOSSIER
    return ([n for n in FICHIERS_PERSONNELS if os.path.isfile(os.path.join(dossier, n))],
            [n for n in DOSSIERS_PERSONNELS if os.path.isdir(os.path.join(dossier, n))])


def extras_personnels():
    """Ce que Jarvis a rangé hors de son dossier à la demande de l'utilisateur : captures d'écran, sauvegardes."""
    pistes = [os.path.join(_images(), "Jarvis"), os.path.join(_documents(), "Jarvis - sauvegardes")]
    return [p for p in pistes if os.path.isdir(p)]


def traces_diverses():
    """Fichiers temporaires et liaisons créés par Jarvis ou son installateur, hors de son dossier."""
    temp = tempfile.gettempdir()
    pistes = [os.path.join(temp, n) for n in ("Jarvis-installation.log", "Jarvis-installation", "Jarvis-mise-a-jour",
                                              "Jarvis-installateur", "jarvis-essai.txt", "jarvis-essai-erreurs.txt",
                                              "jarvis-essai-modules.py", "jarvis-essai-modules.txt",
                                              "jarvis-essai-modules-erreurs.txt")]
    try:
        pistes += [os.path.join(temp, n) for n in os.listdir(temp) if re.fullmatch(r"jarvis_\w+_\d+\.mp3", n)]
    except OSError:
        pass
    pistes.append(os.path.join(os.path.expanduser("~"), ".pyremoteplay"))      # liaison avec la PS5
    return [p for p in pistes if os.path.exists(p)]


def raccourcis():
    return [p for p in (os.path.join(bureau(), "Jarvis.lnk"), os.path.join(_demarrage(), "Jarvis.lnk")) if os.path.exists(p)]


# ---------- Fichiers personnels : les garder, ou en faire une copie compressée ----------

def garder(destination=None, dossier=None):
    """Copie les fichiers personnels dans un dossier du Bureau. Renvoie (dossier, nombre de fichiers copiés)."""
    dossier = dossier or jarvis_config.DOSSIER
    destination = destination or os.path.join(bureau(), NOM_DOSSIER_GARDE)
    fichiers, dossiers = personnels_presents(dossier)
    os.makedirs(destination, exist_ok=True)
    nombre = 0
    for nom in fichiers:
        shutil.copy2(os.path.join(dossier, nom), os.path.join(destination, nom))
        nombre += 1
    for nom in dossiers:
        for base, _, noms in os.walk(os.path.join(dossier, nom)):
            for f in noms:
                source = os.path.join(base, f)
                cible = os.path.join(destination, os.path.relpath(source, dossier))
                os.makedirs(os.path.dirname(cible), exist_ok=True)
                shutil.copy2(source, cible)
                nombre += 1
    with open(os.path.join(destination, "LISEZ-MOI.txt"), "w", encoding="utf-8") as f:
        f.write("Fichiers personnels de Jarvis, gardés lors de sa désinstallation le " + time.strftime("%d/%m/%Y") + ".\n\n"
                "Ce sont tes réglages et tout ce que Jarvis avait appris : profils et voix, mémoire, rappels, notes, listes.\n"
                "Si tu réinstalles Jarvis, laisse ce dossier sur le Bureau : l'installateur te proposera de les reprendre.\n"
                "Si tu n'en veux plus, tu peux supprimer ce dossier.\n")
    return destination, nombre


def sauvegarde(destination=None, dossier=None):
    """Copie compressée des fichiers personnels, sur le Bureau. Renvoie le chemin du fichier .zip."""
    dossier = dossier or jarvis_config.DOSSIER
    destination = destination or bureau()
    fichiers, dossiers = personnels_presents(dossier)
    os.makedirs(destination, exist_ok=True)
    chemin = os.path.join(destination, "Jarvis-sauvegarde-" + time.strftime("%Y-%m-%d_%Hh%M") + ".zip")
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        for nom in fichiers:
            z.write(os.path.join(dossier, nom), nom)
        for nom in dossiers:
            for base, _, noms in os.walk(os.path.join(dossier, nom)):
                for f in noms:
                    complet = os.path.join(base, f)
                    z.write(complet, os.path.relpath(complet, dossier))
    return chemin


# ---------- Le programme qui retire tout, une fois Jarvis arrêté ----------
# Il tourne hors du dossier de Jarvis (qu'il supprime). Garde-fous : il ne supprime qu'un vrai dossier de Jarvis
# (avec jarvis_gardien.py), jamais un disque, le dossier personnel ni Windows ; les autres fichiers doivent porter
# le nom de Jarvis ; la clé du registre doit être celle de Jarvis.
SCRIPT = r'''param([string]$Plan)
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try { $Host.UI.RawUI.WindowTitle = 'Désinstallation de Jarvis' } catch {}
$p = Get-Content -LiteralPath $Plan -Raw -Encoding UTF8 | ConvertFrom-Json
$faits = New-Object Collections.ArrayList
$problemes = New-Object Collections.ArrayList
$ic = [StringComparison]::OrdinalIgnoreCase
function Dire($t) { Write-Host ("  " + $t) }
function Fait($t) { [void]$faits.Add($t); Dire ("[OK] " + $t) }
function Probleme($t) { [void]$problemes.Add($t); Dire ("[!]  " + $t) }
function Fin($titre) {
    $texte = $titre
    if ($faits.Count) { $texte += "`n`nRetiré :`n - " + ($faits -join "`n - ") }
    if ($p.garde) { $texte += "`n`nTes fichiers personnels sont gardés ici :`n" + $p.garde }
    if ($p.zip) { $texte += "`n`nCopie compressée de tes fichiers personnels :`n" + $p.zip }
    if ($problemes.Count) { $texte += "`n`nÀ finir à la main :`n - " + ($problemes -join "`n - ") }
    if ($p.resultat) { try { [IO.File]::WriteAllText([string]$p.resultat, $texte, (New-Object Text.UTF8Encoding $false)) } catch {} }
    if (-not $p.silencieux) {
        try {
            Add-Type -AssemblyName System.Windows.Forms
            $devant = New-Object Windows.Forms.Form -Property @{ TopMost = $true }
            [void][Windows.Forms.MessageBox]::Show($devant, $texte, 'Jarvis', 'OK', $(if ($problemes.Count) { 'Warning' } else { 'Information' }))
        } catch {}
    }
}
function Sous($chemin, $racine) { return $racine -and ([string]$chemin).StartsWith(([string]$racine).TrimEnd('\') + '\', $ic) }
function Supprimer($chemin) {
    # Renvoie $true si le fichier ou le dossier n'existe plus
    if (-not (Test-Path -LiteralPath $chemin)) { return $true }
    for ($i = 0; $i -lt 15 -and (Test-Path -LiteralPath $chemin); $i++) {
        if (Test-Path -LiteralPath $chemin -PathType Container) { & cmd.exe /c rd /s /q "$chemin" 2>$null | Out-Null }
        else { Remove-Item -LiteralPath $chemin -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $chemin) { Start-Sleep -Seconds 2 }
    }
    return -not (Test-Path -LiteralPath $chemin)
}
function Lancer-Desinstalleur($entree) {
    $pr = Start-Process -FilePath cmd.exe -ArgumentList ('/c "' + $entree.QuietUninstallString + '"') -Wait -PassThru -WindowStyle Hidden
    return $pr.ExitCode
}

Write-Host ''
Write-Host '  Désinstallation de Jarvis' -ForegroundColor Cyan
Write-Host ''

# 1. Garde-fous sur le dossier
$d = [IO.Path]::GetFullPath([string]$p.dossier).TrimEnd('\')
$profil = $env:USERPROFILE.TrimEnd('\')
$windows = $env:WINDIR.TrimEnd('\')
$interdit = ($d.Length -le 3) -or ($d -ieq $profil) -or (Sous $profil $d) -or ($d -ieq $windows) -or (Sous $d $windows) -or
            ($env:ProgramFiles -and ($d -ieq $env:ProgramFiles.TrimEnd('\'))) -or
            -not (Test-Path -LiteralPath (Join-Path $d 'jarvis_gardien.py'))
if ($interdit) {
    Probleme "le dossier $d n'a pas été reconnu comme un dossier de Jarvis : rien n'a été supprimé"
    Fin "La désinstallation de Jarvis n'a pas commencé."
    exit 1
}

# 2. Arrêter Jarvis (le gardien d'abord, sinon il le relance), sans toucher aux autres programmes
Dire 'Arrêt de Jarvis...'
$tous = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$cibles = @($tous | Where-Object { $_.Name -in 'python.exe', 'pythonw.exe' -and $_.ProcessId -ne $PID -and (
    ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($d + '\', $ic)) -or
    ($_.CommandLine -and $_.CommandLine.IndexOf($d + '\', $ic) -ge 0)) })
# ... et tout programme lancé depuis le dossier lui-même (l'installateur rangé là, par exemple) : il bloquerait la suppression
$cibles += @($tous | Where-Object { $_.ProcessId -ne $PID -and $_.Name -notin 'python.exe', 'pythonw.exe' -and $_.ExecutablePath -and $_.ExecutablePath.StartsWith($d + '\', $ic) })
$ids = @($cibles | ForEach-Object { $_.ProcessId })
$enfants = @($tous | Where-Object { $_.Name -in 'claude.exe', 'python.exe', 'pythonw.exe' -and $_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids -and $_.ProcessId -ne $PID })
foreach ($c in (@($cibles | Where-Object { $_.CommandLine -like '*jarvis_gardien*' }) + @($cibles | Where-Object { $_.CommandLine -notlike '*jarvis_gardien*' }) + $enfants)) {
    try { Stop-Process -Id $c.ProcessId -Force -ErrorAction Stop } catch {}
}
if ($ids.Count) { Start-Sleep -Seconds 2 }
Set-Location -LiteralPath $env:TEMP

# 3. Raccourcis (Bureau, démarrage de Windows)
$retires = 0
foreach ($lien in @($p.raccourcis)) {
    if ($lien -and ((Split-Path -Leaf $lien) -match '^Jarvis.*\.lnk$') -and (Test-Path -LiteralPath $lien)) {
        if (Supprimer $lien) { $retires++ } else { Probleme "raccourci non supprimé : $lien" }
    }
}
if ($retires) { Fait "les raccourcis de Jarvis (Bureau, démarrage de Windows)" }

# 3 bis. La règle du pare-feu pour les tablettes (Windows demande l'autorisation), seulement si elle existe
try { & netsh.exe advfirewall firewall show rule name="Jarvis - tablettes" | Out-Null } catch {}
if ($LASTEXITCODE -eq 0) {
    Dire "Retrait de l'accès des tablettes au pare-feu : Windows demande ton autorisation, réponds Oui..."
    try {
        $pr = Start-Process -FilePath netsh.exe -ArgumentList 'advfirewall firewall delete rule name="Jarvis - tablettes"' -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        if ($pr.ExitCode -eq 0) { Fait "l'accès des tablettes dans le pare-feu de Windows" } else { Probleme "règle « Jarvis - tablettes » du pare-feu non retirée" }
    } catch { Probleme "règle « Jarvis - tablettes » du pare-feu non retirée (autorisation refusée)" }
}

# 4. Claude Code
if ($p.claude) {
    Dire 'Retrait de Claude Code...'
    $base = Join-Path $profil '.local'
    Get-CimInstance Win32_Process -Filter "Name='claude.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.ExecutablePath -and (Sous $_.ExecutablePath $base) } |
        ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
    $reste = $false
    foreach ($c in (Join-Path $base 'bin\claude.exe'), (Join-Path $base 'share\claude'), (Join-Path $base 'state\claude'),
                   (Join-Path $profil '.claude'), (Join-Path $profil '.claude.json'), (Join-Path $profil '.claude.json.backup')) {
        if (-not (Supprimer $c)) { $reste = $true; Probleme "non supprimé : $c" }
    }
    foreach ($vide in (Join-Path $base 'bin'), (Join-Path $base 'share'), (Join-Path $base 'state'), $base) {
        if ((Test-Path -LiteralPath $vide) -and -not (Get-ChildItem -LiteralPath $vide -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $vide -Force -ErrorAction SilentlyContinue }
    }
    if (-not $reste) { Fait "Claude Code, ses réglages et la connexion à ton compte" }
}

# 5. Python (désinstalleur officiel), puis ce que pip avait gardé
if ($p.python) {
    $motif = '^Python 3\.14\.\d+ \(64-bit\)$'
    $cle = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
    $e = Get-ItemProperty $cle -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match $motif -and $_.QuietUninstallString } | Select-Object -First 1
    if ($e) {
        Dire 'Désinstallation de Python (une à deux minutes)...'
        [void](Lancer-Desinstalleur $e)
        if (Get-ItemProperty $cle -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match $motif }) {
            Probleme "Python n'a pas pu être désinstallé : Paramètres de Windows, Applications, Applications installées"
        } else {
            foreach ($c in (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314'), (Join-Path $env:LOCALAPPDATA 'pip\cache')) { [void](Supprimer $c) }
            foreach ($vide in (Join-Path $env:LOCALAPPDATA 'Programs\Python'), (Join-Path $env:LOCALAPPDATA 'pip')) {
                if ((Test-Path -LiteralPath $vide) -and -not (Get-ChildItem -LiteralPath $vide -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $vide -Force -ErrorAction SilentlyContinue }
            }
            Fait "Python 3.14"
        }
    } else { Probleme "Python : désinstalleur introuvable (Paramètres de Windows, Applications, Applications installées)" }
}

# 6. Composants Microsoft Visual C++ (Windows demande l'autorisation)
if ($p.vc) {
    $motif = '^Microsoft Visual C\+\+ 20\d\d(-20\d\d)? Redistributable \(x64\)'
    $e = Get-ItemProperty 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*', 'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*' -ErrorAction SilentlyContinue |
         Where-Object { $_.DisplayName -match $motif -and $_.QuietUninstallString } | Select-Object -First 1
    if ($e) {
        Dire "Désinstallation des composants Microsoft Visual C++ : Windows demande ton autorisation, réponds Oui..."
        try { [void](Lancer-Desinstalleur $e) } catch {}
        if (Test-Path -LiteralPath (Join-Path $env:WINDIR 'System32\vcruntime140_1.dll')) {
            Probleme "les composants Microsoft Visual C++ sont toujours là (autorisation refusée, ou un autre programme s'en sert)"
        } else { Fait "les composants Microsoft Visual C++" }
    } else { Probleme "composants Microsoft Visual C++ : désinstalleur introuvable (Paramètres de Windows, Applications)" }
}

# 7. Fichiers temporaires, liaisons, et fichiers personnels rangés hors du dossier (si demandé)
$nombre = 0
foreach ($c in @($p.autres)) {
    if (-not $c) { continue }
    $c = [IO.Path]::GetFullPath([string]$c)
    $nom = Split-Path -Leaf $c
    $permis = ((Sous $c $profil) -or (Sous $c $env:TEMP)) -and ($nom -match '(?i)jarvis' -or $nom -eq '.pyremoteplay')
    if (-not $permis) { Probleme "par sécurité, non supprimé : $c"; continue }
    if (Test-Path -LiteralPath $c) { if (Supprimer $c) { $nombre++ } else { Probleme "non supprimé : $c" } }
}
if ($nombre) { Fait "les fichiers temporaires et les autres traces de Jarvis ($nombre)" }

# 8. Repère dans le registre
if ($p.cle -and ([string]$p.cle) -like 'HKCU:\Software\Jarvis-TonyNio*' -and (Test-Path -Path $p.cle)) {
    Remove-Item -Path $p.cle -Recurse -Force -ErrorAction SilentlyContinue
    if (Test-Path -Path $p.cle) { Probleme "repère du registre non supprimé : $($p.cle)" } else { Fait "le repère de Jarvis dans le registre de Windows" }
}

# 9. Le dossier de Jarvis
Dire "Suppression du dossier $d..."
if (Supprimer $d) { Fait "Jarvis et tout son dossier ($d)" }
else { Probleme "le dossier $d n'a pas pu être supprimé en entier (un fichier est encore utilisé) : supprime-le à la main après avoir redémarré le PC" }

# 10. Ce programme s'efface lui-même, puis le bilan
$ici = $PSScriptRoot
if ($ici -and ((Split-Path -Leaf $ici) -like 'Jarvis-desinstallation*')) {
    Start-Process -FilePath cmd.exe -WindowStyle Hidden -ArgumentList ('/c ping -n 5 127.0.0.1 >nul & rd /s /q "' + $ici + '"')
}
if ($problemes.Count) { Fin "Jarvis est désinstallé, mais il reste quelque chose à finir." }
else { Fin "Jarvis est désinstallé. Ce PC est revenu comme avant son installation." }
exit $(if ($problemes.Count) { 2 } else { 0 })
'''


def preparer(garder_dans=None, fichier_zip=None, retirer=(), supprimer_extras=False, dossier=None, liens=None,
             autres=None, cle="HKCU:\\" + CLE_REGISTRE, silencieux=False, resultat=None):
    """Écrit le programme de désinstallation et son plan dans le dossier temporaire. Renvoie la commande à lancer.
    retirer : parmi « python », « vc », « claude ». Les autres paramètres servent aux essais (dossier factice)."""
    travail = tempfile.mkdtemp(prefix="Jarvis-desinstallation-")
    if autres is None:
        autres = traces_diverses() + (extras_personnels() if supprimer_extras else [])
    plan = {"dossier": dossier or jarvis_config.DOSSIER, "raccourcis": raccourcis() if liens is None else list(liens),
            "autres": list(autres), "cle": cle, "garde": garder_dans or "", "zip": fichier_zip or "",
            "python": "python" in retirer, "vc": "vc" in retirer, "claude": "claude" in retirer,
            "silencieux": bool(silencieux), "resultat": resultat or ""}
    script, fichier_plan = os.path.join(travail, "desinstaller.ps1"), os.path.join(travail, "plan.json")
    with open(script, "w", encoding="utf-8-sig") as f:          # avec BOM : PowerShell lit bien les accents
        f.write(SCRIPT)
    with open(fichier_plan, "w", encoding="utf-8") as f:
        json.dump(plan, f, ensure_ascii=False, indent=1)
    return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Plan", fichier_plan]


def lancer(commande, cache=False):
    """Lance le programme de désinstallation, détaché de Jarvis (qu'il va arrêter)."""
    drapeaux = 0x08000000 if cache else getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10)
    return subprocess.Popen(commande, cwd=tempfile.gettempdir(), creationflags=drapeaux, close_fds=True)


# ---------- Ce qui est écrit dans la fenêtre de confirmation ----------

def recapitulatif(garder_fichiers, avec_zip, dossier=None):
    """Les lignes du récapitulatif : ce qui sera retiré dans tous les cas."""
    dossier = dossier or jarvis_config.DOSSIER
    lignes = [f"Jarvis et tout son dossier ({dossier}) : le programme, ses modules, ses modèles vocaux, ses journaux "
              "et les enregistrements de voix",
              "Les raccourcis « Jarvis » du Bureau et du démarrage de Windows : Jarvis ne se lancera plus avec Windows",
              "Le repère de Jarvis dans le registre de Windows et ses fichiers temporaires"]
    if os.path.exists(os.path.join(os.path.expanduser("~"), ".pyremoteplay")):
        lignes.append("La liaison avec la PlayStation 5")
    if garder_fichiers:
        lignes.append(f"Tes fichiers personnels ne sont PAS supprimés : ils seront rangés dans le dossier « {NOM_DOSSIER_GARDE} » "
                      "sur le Bureau")
    else:
        extras = extras_personnels()
        lignes.append("Tes fichiers personnels : réglages, profils et voix, mémoire, rappels, notes, listes"
                      + (", ainsi que tes captures d'écran et tes sauvegardes faites par Jarvis" if extras else "")
                      + (" (une copie compressée sera posée sur le Bureau)" if avec_zip else " (sans copie : ce sera définitif)"))
    return lignes


# ---------- Les deux fenêtres ----------

def ouvrir(parent=None):
    """Ouvre la fenêtre « Désinstaller Jarvis ». parent : la fenêtre des réglages (sinon, fenêtre seule)."""
    import tkinter as tk
    from tkinter import messagebox

    autonome = parent is None
    racine = tk.Tk() if autonome else parent
    if autonome:
        racine.withdraw()
    sc = max(1.0, racine.winfo_fpixels("1i") / 96.0)

    def px(v):
        return int(round(v * sc))
    choix = {"garder": True, "zip": True}

    def fenetre(titre_fenetre, largeur):
        f = tk.Toplevel(racine)
        f.title(titre_fenetre)
        f.configure(bg=FOND)
        f.resizable(False, False)
        for icone in (jarvis_config.chemin("docs", "jarvis.ico"), jarvis_config.chemin("installateur", "jarvis.ico")):
            try:
                f.iconbitmap(icone)
                break
            except Exception:
                continue
        try:                                          # barre de titre sombre (Windows 10/11)
            import ctypes
            f.update_idletasks()
            sombre = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.windll.user32.GetParent(f.winfo_id()), 20, ctypes.byref(sombre), 4)
        except Exception:
            pass
        cadre = tk.Frame(f, bg=PANNEAU, highlightthickness=1, highlightbackground="#1b2838")
        cadre.pack(fill="both", expand=True, padx=14, pady=14)
        f._largeur = px(largeur)
        return f, cadre

    def placer(f):
        f.update_idletasks()
        l, h = max(f._largeur, f.winfo_reqwidth()), f.winfo_reqheight()
        f.geometry(f"{l}x{h}+{max(0, (f.winfo_screenwidth() - l) // 2)}+{max(0, (f.winfo_screenheight() - h) // 3)}")
        if not autonome:
            f.transient(racine)
        f.lift()
        f.focus_force()
        f.grab_set()

    def texte(cadre, contenu, couleur=TEXTE, police=POLICE, haut=6, largeur=560, gauche=20):
        e = tk.Label(cadre, text=contenu, bg=PANNEAU, fg=couleur, font=police, wraplength=px(largeur), justify="left")
        e.pack(anchor="w", padx=gauche, pady=(haut, 0))
        return e

    def bouton(parent_b, libelle, action, couleur=None):
        b = tk.Label(parent_b, text=libelle, bg=couleur or "#1b2838", fg="#0b0f14" if couleur else TEXTE,
                     font=("Segoe UI Semibold", 10), padx=16, pady=7, cursor="hand2")
        b.actif = True
        b.bind("<Button-1>", lambda e: action() if b.actif else None)
        return b

    def fermer(f):
        try:
            f.grab_release()
        except Exception:
            pass
        f.destroy()
        if autonome:
            racine.destroy()

    def premiere():
        f, cadre = fenetre("Jarvis - Désinstaller", 620)
        texte(cadre, "Désinstaller Jarvis", police=("Segoe UI Semibold", 15), haut=16)
        texte(cadre, "Jarvis va être retiré de ce PC, avec tout ce qui a été installé pour lui. Avant cela, que veux-tu faire "
                     "de tes fichiers personnels, c'est-à-dire tout ce que Jarvis a appris : tes réglages, les profils et les "
                     "voix, sa mémoire, tes rappels, tes notes et tes listes ?", couleur=DISCRET)
        variable = tk.StringVar(f, "garder" if choix["garder"] else "supprimer")
        avec_zip = tk.BooleanVar(f, choix["zip"])
        commun = dict(bg=PANNEAU, fg=TEXTE, selectcolor=PANNEAU2, activebackground=PANNEAU, activeforeground=TEXTE,
                      font=POLICE, anchor="w", justify="left", wraplength=px(520), highlightthickness=0, bd=0)

        def maj():
            case.configure(state="normal" if variable.get() == "supprimer" else "disabled")
        tk.Radiobutton(cadre, text=f"Les garder. Ils seront rangés dans le dossier « {NOM_DOSSIER_GARDE} » sur le Bureau. "
                                   "Si tu réinstalles Jarvis un jour, l'installateur te proposera de les reprendre.",
                       variable=variable, value="garder", command=maj, **commun).pack(anchor="w", padx=20, pady=(14, 0))
        tk.Radiobutton(cadre, text="Les supprimer avec le reste.", variable=variable, value="supprimer", command=maj,
                       **commun).pack(anchor="w", padx=20, pady=(10, 0))
        case = tk.Checkbutton(cadre, text="Poser quand même une copie compressée sur le Bureau, au cas où tu changerais d'avis.",
                              variable=avec_zip, disabledforeground=DISCRET, **commun)
        case.pack(anchor="w", padx=46, pady=(4, 0))
        maj()
        bas = tk.Frame(cadre, bg=PANNEAU)
        bas.pack(fill="x", padx=16, pady=18)

        def suite():
            choix["garder"], choix["zip"] = variable.get() == "garder", bool(avec_zip.get())
            f.grab_release()
            f.destroy()
            derniere()
        bouton(bas, "Continuer", suite, couleur="#8fb8ff").pack(side="right", padx=4)
        bouton(bas, "Annuler", lambda: fermer(f)).pack(side="right", padx=4)
        f.protocol("WM_DELETE_WINDOW", lambda: fermer(f))
        placer(f)

    def derniere():
        f, cadre = fenetre("Jarvis - Dernière confirmation", 660)
        texte(cadre, "Dernière confirmation", police=("Segoe UI Semibold", 15), haut=16)
        texte(cadre, "Voici tout ce qui va être retiré de ce PC :", couleur=DISCRET, largeur=600)
        for ligne in recapitulatif(choix["garder"], choix["zip"]):
            texte(cadre, "•  " + ligne, haut=5, largeur=590, gauche=28)
        cases = {}
        liste = composants()
        if liste:
            texte(cadre, "Installés avec Jarvis (décoche ce que tu utilises pour autre chose) :", couleur=DISCRET, haut=12, largeur=600)
        for cle, libelle, par_jarvis in liste:
            cases[cle] = tk.BooleanVar(f, True)       # tout est coché d'office ; à l'utilisateur de décocher ce qu'il garde
            tk.Checkbutton(cadre, text=libelle + ("" if par_jarvis else " — déjà là avant Jarvis, ou origine inconnue"),
                           variable=cases[cle], bg=PANNEAU, fg=TEXTE, selectcolor=PANNEAU2, activebackground=PANNEAU,
                           activeforeground=TEXTE, font=POLICE, anchor="w", justify="left", wraplength=px(570),
                           highlightthickness=0, bd=0).pack(anchor="w", padx=24, pady=(3, 0))
        texte(cadre, "Tout ce que Jarvis a installé est retiré, et Windows revient comme avant son installation : plus de "
                     "lancement au démarrage, plus de raccourcis, plus aucune trace dans le registre.", haut=12, largeur=600)
        texte(cadre, f"Cette action est définitive. Pour confirmer, écris  {MOT}  dans le champ ci-dessous.", couleur=ALERTE,
              police=("Segoe UI Semibold", 10), haut=12, largeur=600)
        saisie = tk.StringVar(f)
        champ = tk.Entry(cadre, textvariable=saisie, bg=PANNEAU2, fg=TEXTE, insertbackground=TEXTE, relief="flat",
                         font=("Segoe UI", 12), highlightthickness=1, highlightbackground="#2a3a50", highlightcolor=ALERTE)
        champ.pack(fill="x", padx=20, pady=(8, 0), ipady=6)
        etat = texte(cadre, "", couleur=DISCRET, haut=6, largeur=600)
        bas = tk.Frame(cadre, bg=PANNEAU)
        bas.pack(fill="x", padx=16, pady=(8, 18))

        def desinstaller():
            if saisie.get().strip().lower() != MOT:
                return
            valider.actif = False
            valider.configure(bg="#1b2838", fg=DISCRET, cursor="arrow")
            champ.configure(state="disabled")
            etat.configure(text="Préparation : je mets tes fichiers de côté…" if (choix["garder"] or choix["zip"]) else "Préparation…")
            f.update_idletasks()
            try:
                garde = garder()[0] if choix["garder"] else None
                copie = sauvegarde() if (choix["zip"] and not choix["garder"]) else None
                commande = preparer(garder_dans=garde, fichier_zip=copie, retirer=[c for c, v in cases.items() if v.get()],
                                    supprimer_extras=not choix["garder"])
            except Exception as erreur:
                messagebox.showerror("Jarvis", f"La désinstallation n'a pas commencé : {erreur}\n\nRien n'a été supprimé.", parent=f)
                fermer(f)
                return
            if not choix["garder"]:               # rien de Jarvis ne reste dans le coffre de Windows (mots de passe
                try:                              # de la boîte mail, lien de l'agenda, jetons des appareils)
                    import jarvis_coffre
                    jarvis_coffre.tout_retirer()
                except Exception as erreur:
                    print("Désinstallation (coffre de Windows) :", erreur)
            etat.configure(text="Jarvis s'arrête. Une fenêtre montre la suite, puis un message te dira que c'est fini.")
            f.update_idletasks()
            lancer(commande)

        def surveiller(*_):
            bon = saisie.get().strip().lower() == MOT
            if valider.actif or bon:
                valider.actif = bon
                valider.configure(bg=ALERTE if bon else "#1b2838", fg="#0b0f14" if bon else DISCRET,
                                  cursor="hand2" if bon else "arrow")
        valider = bouton(bas, "Désinstaller Jarvis", desinstaller)
        valider.actif = False
        valider.configure(fg=DISCRET, cursor="arrow")
        valider.pack(side="right", padx=4)
        saisie.trace_add("write", surveiller)
        champ.bind("<Return>", lambda e: desinstaller())

        def retour():
            f.grab_release()
            f.destroy()
            premiere()
        bouton(bas, "Annuler", lambda: fermer(f)).pack(side="right", padx=4)
        bouton(bas, "Retour", retour).pack(side="left", padx=4)
        f.protocol("WM_DELETE_WINDOW", lambda: fermer(f))
        placer(f)
        champ.focus_set()

    premiere()
    if autonome:
        racine.mainloop()


if __name__ == "__main__":
    ouvrir()
