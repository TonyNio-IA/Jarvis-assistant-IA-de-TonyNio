@echo off
rem Installateur de Jarvis, assistant IA de TonyNio : double-clique sur ce fichier.
rem https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio
setlocal
title Installer Jarvis
chcp 65001 >nul
set "JARVIS_FICHIER=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:JARVIS_FICHIER,[Text.Encoding]::UTF8); $i=$t.IndexOf('#==JARVIS-POWERSHELL=='+'#'); Invoke-Expression $t.Substring($i)"
set "CODE=%ERRORLEVEL%"
if not defined JARVIS_AUTO pause
exit /b %CODE%
#==JARVIS-POWERSHELL==#
# ---------------------------------------------------------------------------------------------
#  Installateur de Jarvis, assistant IA de TonyNio
#  Installe, met à jour ou désinstalle Jarvis. Presque tout se fait dans ton dossier personnel ;
#  seuls les composants Microsoft Visual C++, s'ils manquent, demandent l'autorisation de Windows.
#  Rien n'est installé avant ton accord.
#  https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio
# ---------------------------------------------------------------------------------------------

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$VERSION_INSTALLATEUR = '1.0'
$DEPOT      = 'TonyNio-IA/Jarvis-assistant-IA-de-TonyNio'
$PYTHON_VER = '3.14.10'
$PYTHON_URL = "https://www.python.org/ftp/python/$PYTHON_VER/python-$PYTHON_VER-amd64.exe"
$VC_URL     = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'      # composants Microsoft Visual C++ (site de Microsoft)
$VOSK_NOM   = 'vosk-model-small-fr-0.22'
$VOSK_URL   = "https://alphacephei.com/vosk/models/$VOSK_NOM.zip"
$CLAUDE_EXE = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
$CLE        = 'HKCU:\Software\Jarvis-TonyNio'
$AUTO       = [bool]$env:JARVIS_AUTO          # mode sans question (essais automatiques)
$JOURNAL    = Join-Path $env:TEMP 'Jarvis-installation.log'
$TEMP       = Join-Path $env:TEMP 'Jarvis-installation'
$PERSONNELS = 'config.json','ville.txt','memoire.json','rappels.json','applications.json','notes.txt','position.txt','volumes.json','liste.json','reglages_voix.json'
$UTF8       = New-Object Text.UTF8Encoding $false

function Journal($texte) {
    try { Add-Content -LiteralPath $JOURNAL -Value ("[{0}] {1}" -f (Get-Date -Format 'dd/MM HH:mm:ss'), $texte) -Encoding UTF8 } catch {}
}
function Dire($texte, $couleur = 'Gray') { Write-Host $texte -ForegroundColor $couleur; Journal $texte }
function Titre($texte) { Write-Host ''; Write-Host ("  " + $texte) -ForegroundColor Cyan; Journal ("== " + $texte) }
function Bon($texte) { Dire ("  [OK] " + $texte) 'Green' }
function Attention($texte) { Dire ("  [!]  " + $texte) 'Yellow' }
function Echec($texte) { throw $texte }

function Demander($question, $defaut, $variable) {
    if ($AUTO) {
        $valeur = [Environment]::GetEnvironmentVariable($variable)
        if ([string]::IsNullOrWhiteSpace($valeur)) { $valeur = $defaut }
        Journal "$question -> $valeur (automatique)"
        return $valeur
    }
    $valeur = Read-Host ("  " + "$question".TrimEnd(' ', ':'))     # Read-Host ajoute lui-même « : »
    # On retire les espaces, guillemets, parenthèses ou crochets tapés autour de la réponse
    $valeur = "$valeur".Trim().Trim('"', "'", '(', ')', '[', ']', '«', '»').Trim()
    if ([string]::IsNullOrWhiteSpace($valeur)) { $valeur = $defaut }
    Journal "$question -> (réponse saisie)"
    return "$valeur"
}
function OuiNon($question, $defautOui, $variable) {
    $defaut = if ($defautOui) { 'o' } else { 'n' }
    while ($true) {
        $r = (Demander "$question Tape o (oui) ou n (non), puis Entrée. Entrée seule = $(if ($defautOui) { 'oui' } else { 'non' })" $defaut $variable).ToLower()
        if ($r -in 'o','oui','y','yes','1') { return $true }
        if ($r -in 'n','non','no','0') { return $false }
    }
}

function Telecharger($adresse, $fichier, $quoi) {
    Dire "  Téléchargement : $quoi"
    # Jusqu'à trois tentatives espacées : un raté passager du réseau (ex. : « Could not resolve host ») ne doit pas tout arrêter
    foreach ($attente in 0, 10, 30) {
        if ($attente) {
            Dire "  Le téléchargement n'a pas abouti : nouvel essai dans $attente secondes..." 'DarkYellow'
            Start-Sleep -Seconds $attente
        }
        if (Test-Path -LiteralPath $fichier) { Remove-Item -LiteralPath $fichier -Force }
        & curl.exe -L --fail --retry 2 --connect-timeout 30 -sS -o $fichier $adresse
        if ($LASTEXITCODE -eq 0 -and (Test-Path -LiteralPath $fichier) -and (Get-Item -LiteralPath $fichier).Length -ge 1000) { return }
        Journal "Téléchargement raté (code curl $LASTEXITCODE) : $adresse"
    }
    Echec "Le téléchargement a échoué : $quoi.`n  Adresse : $adresse`n  Vérifie ta connexion Internet, puis relance l'installateur. Si l'erreur persiste, l'adresse a peut-être changé : signale-le sur la page GitHub du projet."
}

function Dossier-Installe {
    try {
        $d = (Get-ItemProperty -Path $CLE -ErrorAction Stop).Dossier
        if ($d -and (Test-Path -LiteralPath (Join-Path $d 'jarvis_gardien.py'))) { return $d }
    } catch {}
    return $null
}
function Version-Installee($dossier) {
    try {
        $ligne = Select-String -LiteralPath (Join-Path $dossier 'jarvis_claude.py') -Pattern '^VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
        if ($ligne) { return $ligne.Matches[0].Groups[1].Value }
    } catch {}
    return '?'
}
function Arreter-Jarvis {
    $n = 0
    Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like '*jarvis_gardien.py*' -or $_.CommandLine -like '*jarvis_reacteur.py*' } |
        ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $n++ } catch {} }
    if ($n) { Start-Sleep 2; Dire "  Jarvis était en marche : il a été arrêté." }
}
function Python-314 {
    $ErrorActionPreference = 'SilentlyContinue'     # une erreur d'un Python cassé ne doit pas arrêter l'installateur
    $pistes = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python314\python.exe'),
        (Join-Path $env:ProgramFiles 'Python314\python.exe')
    )
    $surChemin = Get-Command python.exe -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1
    if ($surChemin) { $pistes += $surChemin.Source }
    foreach ($p in $pistes) {
        if ($p -and (Test-Path -LiteralPath $p)) {
            $v = (& $p -c "import sys; print('%d.%d' % sys.version_info[:2])") 2>$null
            if ($v -eq '3.14') { return $p }
        }
    }
    return $null
}
function VC-Present {
    return (Test-Path -LiteralPath (Join-Path $env:WINDIR 'System32\msvcp140.dll')) -and (Test-Path -LiteralPath (Join-Path $env:WINDIR 'System32\vcruntime140_1.dll'))
}
function Installer-VC {
    # Sans ces composants de Microsoft, la reconnaissance précise (Whisper) ne se charge pas. Beaucoup de PC les ont déjà.
    if (VC-Present) { Bon "Composants Microsoft Visual C++ déjà présents."; return }
    $programme = Join-Path $TEMP 'vc_redist.x64.exe'
    try { Telecharger $VC_URL $programme "composants Microsoft Visual C++ (environ 25 Mo)" }
    catch {
        # Pas indispensables : l'installation continue sans eux
        Journal "Composants Microsoft non téléchargés : $($_.Exception.Message)"
        Attention "Les composants Microsoft Visual C++ n'ont pas pu être téléchargés : l'installation continue sans eux."
        Attention "Jarvis fonctionnera, mais comprendra moins bien (reconnaissance simple seulement)."
        Attention "Pour corriger plus tard : relance ce fichier et choisis 1 (mettre à jour ou réparer)."
        return
    }
    Dire "  Windows va te demander l'autorisation de les installer : réponds Oui." 'White'
    try {
        $p = Start-Process -FilePath $programme -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru
        if ($p.ExitCode -in 0, 3010, 1638) { Bon "Composants Microsoft Visual C++ installés." }
        else { Attention "Les composants Microsoft n'ont pas pu être installés (code $($p.ExitCode))." }
    } catch { Attention "Installation des composants Microsoft refusée ou impossible." }
    if (-not (VC-Present)) {
        Attention "Sans eux, Jarvis fonctionne quand même, mais comprend moins bien (reconnaissance simple seulement)."
        Attention "Pour corriger plus tard : relance cet installateur et réponds Oui à la demande de Windows."
    }
}
function Raccourci($chemin, $pythonw, $dossier) {
    $shell = New-Object -ComObject WScript.Shell
    $r = $shell.CreateShortcut($chemin)
    $r.TargetPath = $pythonw
    $r.Arguments = '"' + (Join-Path $dossier 'jarvis_gardien.py') + '"'
    $r.WorkingDirectory = $dossier
    $r.Description = 'Jarvis, assistant vocal'
    $icone = Join-Path $dossier 'docs\jarvis.ico'
    if (Test-Path -LiteralPath $icone) { $r.IconLocation = "$icone,0" }
    $r.Save()
}
function Chemins-Raccourcis {
    return @{
        Bureau    = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Jarvis.lnk'
        Demarrage = Join-Path ([Environment]::GetFolderPath('Startup')) 'Jarvis.lnk'
    }
}

# ---------- Récupérer les fichiers de Jarvis ----------
function Copier-Programme($dossier) {
    New-Item -ItemType Directory -Path $dossier -Force | Out-Null
    $source = $env:JARVIS_SOURCE                       # dossier local (essais avant publication)
    $etiquette = 'copie locale'
    if (-not $source) {
        $etiquette = 'main'
        try {
            $client = New-Object Net.WebClient
            $client.Headers['User-Agent'] = 'Jarvis-Installateur'
            $client.Encoding = [Text.Encoding]::UTF8
            $etiquette = ($client.DownloadString("https://api.github.com/repos/$DEPOT/releases/latest") | ConvertFrom-Json).tag_name
        } catch { Journal "Dernière version introuvable par l'API GitHub : $($_.Exception.Message)" }
        $adresse = if ($etiquette -eq 'main') { "https://github.com/$DEPOT/archive/refs/heads/main.zip" } else { "https://github.com/$DEPOT/archive/refs/tags/$etiquette.zip" }
        $zip = Join-Path $TEMP 'jarvis.zip'
        Telecharger $adresse $zip "Jarvis ($etiquette)"
        $extrait = Join-Path $TEMP 'jarvis'
        if (Test-Path -LiteralPath $extrait) { Remove-Item -LiteralPath $extrait -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $extrait -Force
        $source = (Get-ChildItem -LiteralPath $extrait -Directory | Select-Object -First 1).FullName
    }
    if (-not (Test-Path -LiteralPath (Join-Path $source 'jarvis_gardien.py'))) { Echec "Les fichiers de Jarvis sont incomplets (jarvis_gardien.py absent de $source)." }
    # Seuls les fichiers du programme sont copiés : les réglages et la mémoire ne sont jamais touchés.
    Get-ChildItem -LiteralPath $source -File | Where-Object {
        $_.Name -like 'jarvis_*.py' -or $_.Name -like '*.md' -or $_.Name -in 'requirements.txt','config.exemple.json','.gitignore'
    } | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $dossier $_.Name) -Force }
    $docs = Join-Path $source 'docs'
    if (Test-Path -LiteralPath $docs) { Copy-Item -LiteralPath $docs -Destination $dossier -Recurse -Force }
    Bon "Fichiers de Jarvis en place ($etiquette, version $(Version-Installee $dossier))."
}

function Installer-Modules($dossier, $python) {
    $env_py = Join-Path $dossier 'python-env\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $env_py)) {
        Dire "  Création de l'espace Python réservé à Jarvis..."
        & $python -m venv (Join-Path $dossier 'python-env') | Out-Host
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $env_py)) { Echec "Impossible de créer l'espace Python de Jarvis." }
    }
    Dire "  Installation des modules (quelques minutes, environ 600 Mo)..."
    & $env_py -m pip install --disable-pip-version-check --no-warn-script-location --progress-bar off -r (Join-Path $dossier 'requirements.txt') | Out-Host
    if ($LASTEXITCODE -ne 0) { Echec "L'installation des modules Python a échoué (voir les lignes ci-dessus). Relance l'installateur ; si l'erreur revient, signale-la sur GitHub." }
    Bon "Modules Python installés."
    return $env_py
}

function Installer-Vosk($dossier) {
    $cible = Join-Path $dossier $VOSK_NOM
    if (Test-Path -LiteralPath (Join-Path $cible 'am')) { Bon "Modèle vocal déjà présent."; return }
    $zip = Join-Path $TEMP 'vosk.zip'
    Telecharger $VOSK_URL $zip "modèle de reconnaissance vocale (environ 40 Mo)"
    Expand-Archive -LiteralPath $zip -DestinationPath $dossier -Force
    if (-not (Test-Path -LiteralPath (Join-Path $cible 'am'))) { Echec "Le modèle vocal n'a pas pu être décompressé dans $cible." }
    Bon "Modèle vocal installé."
}

function Ecrire-Reglages($dossier, $prenom, $ville) {
    $config = Join-Path $dossier 'config.json'
    if (Test-Path -LiteralPath $config) { Bon "Réglages déjà présents : conservés." }
    else {
        $texte = [IO.File]::ReadAllText((Join-Path $dossier 'config.exemple.json'), [Text.Encoding]::UTF8)
        $propre = ($prenom -replace '["\\\r\n]', '').Trim()
        if (-not $propre) { $propre = 'Alex' }
        $texte = [regex]::Replace($texte, '"prenom"\s*:\s*"[^"]*"', ('"prenom": "' + $propre.Replace('$', '$$') + '"'))
        [IO.File]::WriteAllText($config, $texte, $UTF8)
        Bon "Réglages créés (prénom : $propre). Tu pourras les modifier dans config.json."
    }
    $fichierVille = Join-Path $dossier 'ville.txt'
    if ((Test-Path -LiteralPath $fichierVille) -or -not $ville) { return }
    try {
        $client = New-Object Net.WebClient
        $client.Encoding = [Text.Encoding]::UTF8
        $r = ($client.DownloadString('https://geocoding-api.open-meteo.com/v1/search?count=1&language=fr&name=' + [uri]::EscapeDataString($ville)) | ConvertFrom-Json).results
        if (-not $r) { Attention "Ville « $ville » introuvable : la météo sera celle de Paris. Tu pourras la régler dans ville.txt."; return }
        $ic = [Globalization.CultureInfo]::InvariantCulture
        $ligne = '{0};{1};{2}' -f ($ville -replace ';', ' '), ([double]$r[0].latitude).ToString('0.####', $ic), ([double]$r[0].longitude).ToString('0.####', $ic)
        [IO.File]::WriteAllText($fichierVille, $ligne + "`r`n", $UTF8)
        Bon "Ville de la météo : $ville ($($r[0].admin1), $($r[0].country))."
    } catch { Attention "La ville n'a pas pu être vérifiée (pas de réponse du service météo) : la météo sera celle de Paris." }
}

function Installer-Claude {
    if (Test-Path -LiteralPath $CLAUDE_EXE) { Bon "Claude Code déjà installé." }
    else {
        Dire "  Installation de Claude Code (programme officiel d'Anthropic, environ 370 Mo : plusieurs minutes)..."
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "`$ProgressPreference='SilentlyContinue'; irm https://claude.ai/install.ps1 | iex" | Out-Host
        if (-not (Test-Path -LiteralPath $CLAUDE_EXE)) {
            Attention "Claude Code n'a pas pu être installé. Jarvis fonctionnera avec les commandes immédiates. Tu pourras réessayer en relançant ce fichier (« Ajouter Claude »)."
            return
        }
        Bon "Claude Code installé."
        Dire "  (Les messages en anglais ci-dessus viennent de l'installation officielle de Claude Code."
        Dire "   S'ils parlent de « PATH », tu peux les ignorer : Jarvis trouve Claude tout seul.)"
    }
    if ($AUTO) { return }
    Connecter-Claude
}

function Claude-Connecte {
    # « claude auth status » répond en JSON ; on n'en garde que « connecté ou non » (rien n'est affiché ni gardé)
    $ErrorActionPreference = 'SilentlyContinue'
    if (-not (Test-Path -LiteralPath $CLAUDE_EXE)) { return $false }
    try { return [bool](((& $CLAUDE_EXE auth status 2>$null) | Out-String) | ConvertFrom-Json).loggedIn } catch { return $false }
}

function Connecter-Claude {
    if (Claude-Connecte) { Bon "Claude est déjà connecté à ton compte."; return }
    Dire ''
    Dire "  Dernière étape pour Claude : la connexion à ton compte Claude." 'White'
    Dire "    1. Ton navigateur va s'ouvrir sur la page de connexion de Claude."
    Dire "       Sur un PC neuf, il montre peut-être d'abord son propre écran d'accueil : passe-le"
    Dire "       (sur Microsoft Edge : « Commencer sans vos données »)."
    Dire "    2. Connecte-toi au compte Claude de ton abonnement, puis accepte l'autorisation."
    Dire "    3. Reviens dans cette fenêtre : la suite se fait toute seule."
    Dire "  Les messages en anglais qui vont s'afficher viennent du programme de Claude : c'est normal."
    Dire "  Si le navigateur ne s'ouvre pas, copie dans ton navigateur l'adresse qui va s'afficher."
    Read-Host "  Appuie sur Entrée pour commencer" | Out-Null
    $ErrorActionPreference = 'Continue'
    try { & $CLAUDE_EXE auth login --claudeai } catch { Journal "Connexion à Claude : $($_.Exception.Message)" }
    try { $Host.UI.RawUI.WindowTitle = 'Installer Jarvis' } catch {}     # Claude renomme la fenêtre « claude »
    if (Claude-Connecte) { Bon "Claude est connecté à ton compte." }
    else { Attention "La connexion à Claude n'a pas abouti. Pour la refaire : relance ce fichier et choisis 3 (« Connecter Claude »)." }
}

function Essai-Python($env_py, $dossier, $instructions, $delai = 120) {
    # Lance un petit essai Python et attend au plus $delai secondes : l'installateur ne peut pas rester bloqué ici.
    # Renvoie ce que l'essai a affiché, ou $null s'il a échoué ou n'a pas fini à temps.
    $sortie = Join-Path $env:TEMP 'jarvis-essai.txt'
    $erreurs = Join-Path $env:TEMP 'jarvis-essai-erreurs.txt'
    try {
        $p = Start-Process -FilePath $env_py -ArgumentList ('-c "' + $instructions + '"') -WorkingDirectory $dossier -WindowStyle Hidden -PassThru -RedirectStandardOutput $sortie -RedirectStandardError $erreurs
        $null = $p.Handle                 # sans cela, Windows PowerShell ne renvoie pas le code de fin du programme
        if (-not $p.WaitForExit($delai * 1000)) { try { $p.Kill() } catch {}; Journal "Essai trop long : $instructions"; return $null }
        if ($p.ExitCode -ne 0) { Journal ("Essai en échec : $instructions | " + ((Get-Content -LiteralPath $erreurs -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 2) -join ' ')); return $null }
        $texte = (Get-Content -LiteralPath $sortie -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 1)
        if ($texte) { return "$texte" } else { return 'ok' }
    } catch { Journal "Essai impossible : $($_.Exception.Message)"; return $null }
}

function Verifier-Modules($env_py, $dossier) {
    # Charge les modules un par un en affichant l'avancée. La toute première fois, le chargement peut prendre
    # plusieurs minutes sans occuper le processeur (mesuré sur un Windows 11 neuf : 4 min, dont 130 s pour « av ») ;
    # les protections de Windows examinent sans doute chaque nouveau fichier. Ce n'est pas une panne.
    $modules = 'numpy','sounddevice','vosk','pygame','psutil','pycaw.pycaw','av','edge_tts','faster_whisper','jarvis_config'
    $script = Join-Path $env:TEMP 'jarvis-essai-modules.py'
    $sortie = Join-Path $env:TEMP 'jarvis-essai-modules.txt'
    $erreurs = Join-Path $env:TEMP 'jarvis-essai-modules-erreurs.txt'
    $code = "import os, sys, time`nos.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'`nsys.path.insert(0, os.getcwd())`nfor nom in ['" + ($modules -join "','") + "']:`n" +
            "    debut = time.time()`n    try:`n        __import__(nom)`n        print('OK', nom, round(time.time() - debut, 1), flush=True)`n" +
            "    except BaseException as e:`n        print('ECHEC', nom, type(e).__name__, str(e).replace(chr(10), ' ')[:300], flush=True)`n"
    [IO.File]::WriteAllText($script, $code, $UTF8)
    Remove-Item -LiteralPath $sortie, $erreurs -Force -ErrorAction SilentlyContinue
    $debut = Get-Date
    $lignes = @()
    $fini = $false
    try {
        $p = Start-Process -FilePath $env_py -ArgumentList ('"' + $script + '"') -WorkingDirectory $dossier -WindowStyle Hidden -PassThru -RedirectStandardOutput $sortie -RedirectStandardError $erreurs
        $null = $p.Handle
        $vus = -1
        while ($true) {
            $fini = $p.WaitForExit(1000)
            # Seules les lignes « OK ... » ou « ECHEC ... » comptent (certains modules écrivent leur propre message)
            $lignes = @(Get-Content -LiteralPath $sortie -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -match '^(OK|ECHEC) ' })
            if ($lignes.Count -ne $vus) { $vus = $lignes.Count; Write-Host ("`r  Modules vérifiés : {0} sur {1}..." -f $vus, $modules.Count) -NoNewline }
            if ($fini -or ((Get-Date) - $debut).TotalSeconds -gt 900) { break }
        }
        Write-Host ''
        if (-not $fini) { try { $p.Kill() } catch {} }
    } catch { Write-Host ''; Journal "Vérification des modules impossible : $($_.Exception.Message)" }
    $duree = [int]((Get-Date) - $debut).TotalSeconds
    foreach ($l in $lignes) { Journal "Module : $l" }
    $echecs = @($lignes | Where-Object { $_ -like 'ECHEC *' })
    $whisper = @($echecs | Where-Object { $_ -like 'ECHEC faster_whisper *' })
    $autres = @($echecs | Where-Object { $_ -notlike 'ECHEC faster_whisper *' })
    if ($lignes.Count -lt $modules.Count) {
        $dernier = if ($lignes.Count) { ($lignes[-1] -split ' ')[1] } else { 'aucun' }
        Journal "Vérification des modules interrompue après $duree s (dernier module : $dernier). Erreurs : $((Get-Content -LiteralPath $erreurs -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 3) -join ' ')"
        if ($fini) { Attention "La vérification des modules s'est arrêtée en cours de route : relance ce fichier et choisis 1 (mettre à jour ou réparer)." }
        else {
            Attention "La vérification des modules n'est pas finie au bout de 15 minutes. Ce n'est pas forcément une panne"
            Attention "(Windows examine peut-être encore les nouveaux fichiers). Si Jarvis ne démarre pas, relance ce fichier et choisis 1."
        }
        return
    }
    if ($autres.Count) {
        $noms = ($autres | ForEach-Object { ($_ -split ' ')[1] }) -join ', '
        Attention "Module de Jarvis qui ne se charge pas : $noms. Relance ce fichier et choisis 1 (mettre à jour ou réparer)."
    } else { Bon "Les modules de Jarvis se chargent." }
    if ($whisper.Count) { Attention "Reconnaissance précise (Whisper) indisponible : il manque sans doute les composants Microsoft Visual C++. Jarvis utilisera la reconnaissance simple." }
    else { Bon "Reconnaissance précise (Whisper) disponible." }
    if ($duree -ge 60) {
        Dire ("  Cette première vérification a pris {0} min {1:00} s. C'est normal sur un PC neuf : les protections de Windows" -f [int][Math]::Floor($duree / 60), ($duree % 60))
        Dire "  examinent sans doute chaque nouveau fichier la première fois. Les lancements suivants de Jarvis sont bien plus rapides."
    }
}

function Verifier($dossier, $env_py) {
    Titre "Vérifications"
    Dire "  Quelques essais (une à deux minutes en général ; plus longtemps sur un PC lent, la première fois)..."
    Verifier-Modules $env_py $dossier
    $micro = Essai-Python $env_py $dossier "import sounddevice as sd; print(sd.query_devices(kind='input')['name'])" 60
    if ($micro) { Bon "Micro détecté : $micro" }
    else { Attention "Aucun micro détecté. Jarvis en a besoin pour t'entendre : branche un micro, puis relance Jarvis." }
    if (-not $env:JARVIS_SANS_VOIX) {
        if (Essai-Python $env_py $dossier "import jarvis_voix; jarvis_voix.speak('Bonjour. Je suis Jarvis. Tout est en place.')" 60) { Bon "Voix : tu devrais avoir entendu Jarvis." }
        else { Attention "La voix n'a pas pu être testée (pas de haut-parleur ou pas d'Internet)." }
    }
}

function Ranger-Installateur($dossier) {
    # Range une copie de l'installateur dans le dossier de Jarvis, pour mettre à jour, réparer ou désinstaller plus tard.
    # Si c'est la version .exe (avec l'icône du réacteur) qui a été lancée, c'est elle qui est rangée.
    $nom = 'Installer-Jarvis.bat'
    try {
        $source = $env:JARVIS_FICHIER
        if ($env:JARVIS_LANCEUR -and (Test-Path -LiteralPath $env:JARVIS_LANCEUR)) { $source = $env:JARVIS_LANCEUR; $nom = 'Installer-Jarvis.exe' }
        if ($source -and (Test-Path -LiteralPath $source)) {
            $cible = Join-Path $dossier $nom
            if ([IO.Path]::GetFullPath($source) -ne [IO.Path]::GetFullPath($cible)) {
                Copy-Item -LiteralPath $source -Destination $cible -Force
                Unblock-File -LiteralPath $cible -ErrorAction SilentlyContinue   # déjà accepté une fois : Windows ne le redemandera pas
            }
            if ($nom -like '*.exe') { Remove-Item -LiteralPath (Join-Path $dossier 'Installer-Jarvis.bat') -Force -ErrorAction SilentlyContinue }
        }
    } catch { Journal "Copie de l'installateur impossible : $($_.Exception.Message)" }
    return $nom
}

function Supprimer-Apres($chemins, $dossierFinal) {
    # L'installateur lancé depuis le dossier de Jarvis ne peut pas s'effacer pendant qu'il tourne :
    # un petit programme caché attend que cette fenêtre soit fermée, puis le supprime (et le dossier, s'il le faut).
    $parent = (Get-CimInstance Win32_Process -Filter "ProcessId=$PID").ParentProcessId
    $liste = ($chemins | ForEach-Object { "'" + $_.Replace("'", "''") + "'" }) -join ','
    $final = if ($dossierFinal) { "'" + $dossierFinal.Replace("'", "''") + "'" } else { '$null' }
    $commande = "Wait-Process -Id $parent -ErrorAction SilentlyContinue; " +
                "foreach (`$f in @($liste)) { for (`$i = 0; `$i -lt 60 -and (Test-Path -LiteralPath `$f); `$i++) { Start-Sleep 1; Remove-Item -LiteralPath `$f -Force -ErrorAction SilentlyContinue } }; " +
                "`$d = $final; if (`$d -and (Test-Path -LiteralPath `$d)) { Remove-Item -LiteralPath `$d -Recurse -Force -ErrorAction SilentlyContinue }"
    $code = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($commande))
    Start-Process powershell.exe -WindowStyle Hidden -ArgumentList "-NoProfile -ExecutionPolicy Bypass -EncodedCommand $code"
}

# ---------- Les trois actions ----------
function Installer($dossierExistant) {
    $maj = [bool]$dossierExistant
    Titre $(if ($maj) { "Mise à jour de Jarvis" } else { "Installation de Jarvis" })

    # 1. Le PC convient-il ?
    $os = [Environment]::OSVersion.Version
    if (-not [Environment]::Is64BitOperatingSystem) { Echec "Jarvis demande un Windows 64 bits." }
    if ($os.Build -lt 22000) { Attention "Jarvis est prévu pour Windows 11. Sur ce Windows, certaines fonctions peuvent ne pas marcher." }
    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Echec "L'outil de téléchargement de Windows (curl) est introuvable." }
    if (-not $env:JARVIS_SOURCE) {
        & curl.exe -sS -I --connect-timeout 15 -o NUL "https://github.com/$DEPOT"
        if ($LASTEXITCODE -ne 0) { Echec "Pas de connexion à Internet (GitHub injoignable). Connecte le PC, puis relance l'installateur." }
    }

    if ($maj) {
        $dossier = $dossierExistant
        Dire "  Jarvis $(Version-Installee $dossier) est installé dans $dossier."
        Dire "  La mise à jour remplace le programme. Tes réglages, ta mémoire et tes rappels sont conservés."
        if (-not (OuiNon "Mettre Jarvis à jour maintenant ?" $true 'JARVIS_OK')) { Dire "  Rien n'a été modifié."; return }
        $avecClaude = Test-Path -LiteralPath $CLAUDE_EXE
        $prenom = ''; $ville = ''; $auDemarrage = Test-Path -LiteralPath (Chemins-Raccourcis).Demarrage
    } else {
        Dire "  Bienvenue. Deux questions, puis l'installation se fait toute seule."
        Dire ''
        $prenom = Demander "Ton prénom (Jarvis t'appellera ainsi), puis Entrée" 'Alex' 'JARVIS_PRENOM'
        # Le reste se règle plus tard : la ville en le disant à Jarvis, le dossier et le démarrage par défaut
        $ville = ''
        $dossier = if ($env:JARVIS_DOSSIER) { $env:JARVIS_DOSSIER } else { 'C:\Jarvis' }
        $dossier = [IO.Path]::GetFullPath($dossier.Trim('"'))
        if (-not $env:JARVIS_DOSSIER -and (Test-Path -LiteralPath $dossier) -and (Get-ChildItem -LiteralPath $dossier -Force | Select-Object -First 1) -and -not (Test-Path -LiteralPath (Join-Path $dossier 'jarvis_gardien.py'))) {
            $dossier = Join-Path $env:LOCALAPPDATA 'Jarvis'        # C:\Jarvis est déjà pris par autre chose
        }
        $auDemarrage = $env:JARVIS_DEMARRAGE -notin 'n','non','0'
        Dire ''
        Dire "  Jarvis répond seul à l'heure, la météo, les minuteurs, les fenêtres, la musique."
        Dire "  Pour les questions libres, il utilise Claude Code, qui demande un abonnement Claude (Pro ou supérieur)."
        $avecClaude = OuiNon "As-tu un abonnement Claude et veux-tu l'utiliser avec Jarvis ?" $false 'JARVIS_CLAUDE'
        if ((Test-Path -LiteralPath $dossier) -and (Get-ChildItem -LiteralPath $dossier -Force | Select-Object -First 1) -and -not (Test-Path -LiteralPath (Join-Path $dossier 'jarvis_gardien.py'))) {
            Echec "Le dossier $dossier existe déjà et contient autre chose. Choisis un dossier vide ou nouveau."
        }
        $libre = (Get-PSDrive -Name ([IO.Path]::GetPathRoot($dossier).Substring(0, 1))).Free
        if ($libre -lt 3GB) { Echec ("Il faut environ 3 Go libres sur le disque ; il n'y en a que {0:N1}." -f ($libre / 1GB)) }
    }

    # 2. Annoncer, puis attendre l'accord
    $python = Python-314
    if (-not $maj) {
        Titre "Ce qui va être installé"
        Dire "  - Jarvis, dans $dossier"
        if (-not $python) { Dire "  - Python $PYTHON_VER (depuis python.org), dans ton dossier personnel" }
        if (-not (VC-Present)) { Dire "  - Les composants Microsoft Visual C++ (depuis microsoft.com) : Windows demandera ton autorisation" }
        Dire "  - Les modules Python de Jarvis, dans son propre dossier (environ 600 Mo)"
        Dire "  - Le modèle de reconnaissance vocale Vosk (environ 40 Mo)"
        if ($avecClaude -and -not (Test-Path -LiteralPath $CLAUDE_EXE)) { Dire "  - Claude Code (depuis claude.ai, environ 370 Mo)" }
        Dire "  - Un raccourci « Jarvis » sur le Bureau$(if ($auDemarrage) { ' et au démarrage de Windows' })"
        Dire "  Au premier lancement, Jarvis téléchargera aussi son second modèle vocal (Whisper, environ 150 Mo)."
        Dire ''
        if (-not (OuiNon "Lancer l'installation ?" $true 'JARVIS_OK')) { Dire "  Installation annulée : rien n'a été installé."; return }
    }
    New-Item -ItemType Directory -Path $TEMP -Force | Out-Null
    Arreter-Jarvis

    # 3. Python
    Titre "Python"
    if ($python) { Bon "Python 3.14 déjà présent." }
    else {
        $programme = Join-Path $TEMP "python-$PYTHON_VER-amd64.exe"
        Telecharger $PYTHON_URL $programme "Python $PYTHON_VER (environ 30 Mo)"
        Dire "  Installation de Python (une à deux minutes)..."
        $p = Start-Process -FilePath $programme -ArgumentList '/quiet','InstallAllUsers=0','PrependPath=0','Include_launcher=0','Include_test=0','Include_doc=0' -Wait -PassThru
        $python = Python-314
        if (-not $python) { Echec "Python n'a pas pu être installé (code $($p.ExitCode)). Installe Python 3.14 depuis https://www.python.org/downloads/ puis relance l'installateur." }
        Bon "Python $PYTHON_VER installé."
    }

    Installer-VC

    # 4 à 7. Jarvis, ses modules, le modèle vocal, les réglages
    Titre "Jarvis"
    Copier-Programme $dossier
    $env_py = Installer-Modules $dossier $python
    Installer-Vosk $dossier
    Ecrire-Reglages $dossier $prenom $ville

    # 8. Claude
    if ($avecClaude -and -not $maj) { Titre "Claude"; Installer-Claude }

    # 9. Raccourcis et repère d'installation
    Titre "Raccourcis"
    $pythonw = Join-Path $dossier 'python-env\Scripts\pythonw.exe'
    $liens = Chemins-Raccourcis
    Raccourci (Join-Path $dossier 'Jarvis.lnk') $pythonw $dossier
    Raccourci $liens.Bureau $pythonw $dossier
    if ($auDemarrage) { Raccourci $liens.Demarrage $pythonw $dossier }
    New-Item -Path $CLE -Force | Out-Null
    Set-ItemProperty -Path $CLE -Name Dossier -Value $dossier
    Set-ItemProperty -Path $CLE -Name Version -Value (Version-Installee $dossier)
    $fichierInstallateur = Ranger-Installateur $dossier
    $nomInstallateur = if ($fichierInstallateur -like '*.exe') { "« Installer-Jarvis » (l'icône du réacteur)" } else { "« Installer-Jarvis.bat »" }
    Bon "Raccourci « Jarvis » créé sur le Bureau$(if ($auDemarrage) { ' et au démarrage de Windows' })."

    # 10. Essais, puis lancement
    Verifier $dossier $env_py
    Titre $(if ($maj) { "Mise à jour terminée" } else { "Installation terminée" })
    Dire "  Jarvis $(Version-Installee $dossier) est installé dans $dossier." 'White'
    if (-not (Test-Path -LiteralPath $CLAUDE_EXE)) {
        Dire ''
        Dire "  Claude n'est pas installé : Jarvis répond aux commandes immédiates (heure, météo, minuteurs, fenêtres, musique)." 'White'
        Dire "  Pour ajouter Claude plus tard, et lui poser toutes tes questions :"
        Dire "    1. Prends un abonnement Claude (Pro ou supérieur) sur https://claude.ai"
        Dire "    2. Double-clique sur le fichier $nomInstallateur que tu as téléchargé. Si tu l'as effacé, une copie est"
        Dire "       rangée dans $dossier (pour ouvrir ce dossier : touche Windows + R, tape $dossier, puis Entrée)."
        Dire "    3. Tape 3 (« Ajouter Claude »), puis Entrée, et suis les indications"
        Dire ''
    } elseif (-not $AUTO -and -not (Claude-Connecte)) {
        Dire ''
        Dire "  Claude est installé mais pas connecté à ton compte : double-clique sur $nomInstallateur" 'White'
        Dire "  (une copie est rangée dans $dossier), puis tape 3 (« Connecter Claude »)." 'White'
        Dire ''
    }
    Dire "  Pour lui parler : dis « Jarvis », attends le bip, puis ta demande. Exemple : « Jarvis, quelle heure est-il ? »"
    Dire "  Pour la météo de chez toi, dis-lui une fois : « Jarvis, ma ville est Toulouse » (avec le nom de ta ville)."
    Dire "  Jarvis se lance avec Windows. Pour l'empêcher : supprime le raccourci « Jarvis » du dossier Démarrage (touche Windows + R, puis shell:startup)."
    Dire "  Clic droit sur le réacteur pour l'arrêter. Pour mettre à jour ou désinstaller : relance ce fichier"
    Dire "  (une copie est rangée dans $dossier : touche Windows + R, tape $dossier, puis Entrée)."
    if (-not $env:JARVIS_SANS_LANCEMENT) {
        Start-Process -FilePath (Join-Path $dossier 'Jarvis.lnk')
        Dire "  Jarvis démarre (le premier lancement prend une minute ou deux : il télécharge Whisper)." 'Green'
    }
    try { Copy-Item -LiteralPath $JOURNAL -Destination (Join-Path $dossier 'installation.log') -Force } catch {}
}

function Desinstaller($dossier) {
    Titre "Désinstallation de Jarvis"
    Dire "  Jarvis est installé dans $dossier."
    if (-not (OuiNon "Désinstaller Jarvis de ce PC ?" $false 'JARVIS_OK')) { Dire "  Rien n'a été modifié."; return }
    $garder = -not (OuiNon "Supprimer aussi tes réglages, sa mémoire, tes rappels et tes notes ?" $false 'JARVIS_TOUT_SUPPRIMER')
    # Garde-fou : on ne supprime qu'un vrai dossier de Jarvis, jamais un disque ni le dossier personnel
    $complet = [IO.Path]::GetFullPath($dossier).TrimEnd('\')
    if ($complet.Length -le 3 -or $complet -eq $env:USERPROFILE.TrimEnd('\') -or -not (Test-Path -LiteralPath (Join-Path $complet 'jarvis_gardien.py'))) {
        Echec "Par sécurité, le dossier $complet n'est pas supprimé automatiquement."
    }
    Arreter-Jarvis
    $liens = Chemins-Raccourcis
    foreach ($lien in $liens.Bureau, $liens.Demarrage) { if (Test-Path -LiteralPath $lien) { Remove-Item -LiteralPath $lien -Force } }
    # L'installateur en cours d'utilisation, s'il est rangé dans le dossier, sera effacé après la fermeture de la fenêtre
    $plusTard = @(@($env:JARVIS_LANCEUR, $env:JARVIS_FICHIER) | Where-Object {
        $_ -and (Test-Path -LiteralPath $_) -and ([IO.Path]::GetFullPath($_)).StartsWith($complet + '\', [StringComparison]::OrdinalIgnoreCase) } |
        ForEach-Object { [IO.Path]::GetFullPath($_) })
    Set-Location $env:TEMP
    $restes = 0
    Get-ChildItem -LiteralPath $complet -Force | Where-Object { -not (($garder -and $_.Name -in $PERSONNELS) -or $_.FullName -in $plusTard) } | ForEach-Object {
        try { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction Stop } catch { $restes++; Journal "Non supprimé : $($_.TargetObject)" }
    }
    if ($plusTard.Count) { Supprimer-Apres $plusTard $(if ($garder) { $null } else { $complet }) }
    elseif (-not $garder) { Remove-Item -LiteralPath $complet -Recurse -Force -ErrorAction SilentlyContinue }
    if ($restes) { Attention "Certains fichiers n'ont pas pu être supprimés (voir le journal) : supprime le dossier $complet à la main." }
    elseif ($garder) { Bon "Jarvis est désinstallé. Tes réglages et sa mémoire sont gardés dans $complet." }
    else { Bon "Jarvis et toutes ses données sont supprimés." }
    if ($plusTard.Count) { Dire "  Le fichier de l'installateur, encore ouvert, s'effacera tout seul quand tu fermeras cette fenêtre." }
    Remove-Item -Path $CLE -Recurse -Force -ErrorAction SilentlyContinue
    Dire "  Python et Claude Code ne sont pas désinstallés : d'autres programmes peuvent s'en servir."
    Dire "  Pour les retirer : Paramètres de Windows, Applications, Applications installées."
}

function Ajouter-Claude($dossier) {
    $installe = Test-Path -LiteralPath $CLAUDE_EXE
    Titre $(if ($installe) { "Connexion de Claude" } else { "Ajout de Claude" })
    Dire "  Claude Code permet à Jarvis de répondre aux questions libres. Il demande un abonnement Claude (Pro ou supérieur)."
    if (-not (OuiNon $(if ($installe) { "Connecter Claude à ton compte maintenant ?" } else { "Installer Claude Code maintenant ?" }) $true 'JARVIS_OK')) { Dire "  Rien n'a été modifié."; return }
    New-Item -ItemType Directory -Path $TEMP -Force | Out-Null
    Installer-Claude
    if (Test-Path -LiteralPath $CLAUDE_EXE) {
        Arreter-Jarvis
        if (-not $env:JARVIS_SANS_LANCEMENT) { Start-Process -FilePath (Join-Path $dossier 'Jarvis.lnk') }
        Bon "Jarvis redémarre avec Claude."
    }
}

# ---------- Déroulement ----------
$code = 0
try {
    Journal "===== Installateur $VERSION_INSTALLATEUR ====="
    Write-Host ''
    Write-Host '  ============================================================' -ForegroundColor Cyan
    Write-Host '   JARVIS, assistant vocal en français pour Windows 11' -ForegroundColor Cyan
    Write-Host "   Installateur $VERSION_INSTALLATEUR   (version alpha, en cours de développement)" -ForegroundColor Cyan
    Write-Host '  ============================================================' -ForegroundColor Cyan
    $existant = Dossier-Installe
    if (-not $existant) { Installer $null }
    else {
        Dire ''
        Dire "  Jarvis $(Version-Installee $existant) est déjà installé sur ce PC ($existant)." 'White'
        $claudeInstalle = Test-Path -LiteralPath $CLAUDE_EXE
        $sansClaude = -not ($claudeInstalle -and (Claude-Connecte))
        Dire "    1. Mettre à jour (ou réparer)"
        Dire "    2. Désinstaller"
        if ($sansClaude) {
            if ($claudeInstalle) { Dire "    3. Connecter Claude à ton compte (pour les questions libres)" }
            else { Dire "    3. Ajouter Claude (pour les questions libres ; demande un abonnement Claude)" }
        }
        Dire "    0. Ne rien faire"
        $choix = Demander "Ton choix, puis Entrée" '0' 'JARVIS_ACTION'
        if ($choix -eq '1') { Installer $existant }
        elseif ($choix -eq '2') { Desinstaller $existant }
        elseif ($choix -eq '3' -and $sansClaude) { Ajouter-Claude $existant }
        else { Dire "  Rien n'a été modifié." }
    }
} catch {
    $code = 1
    Write-Host ''
    Write-Host ("  ERREUR : " + $_.Exception.Message) -ForegroundColor Red
    Journal ("ERREUR : " + $_.Exception.Message + " | " + $_.ScriptStackTrace)
    Write-Host "  L'installation s'est arrêtée. Tu peux relancer ce fichier : il reprendra sans rien casser." -ForegroundColor Yellow
    Write-Host "  Journal : $JOURNAL" -ForegroundColor DarkGray
} finally {
    try { if (Test-Path -LiteralPath $TEMP) { Remove-Item -LiteralPath $TEMP -Recurse -Force -ErrorAction SilentlyContinue } } catch {}
}
Write-Host ''
exit $code
