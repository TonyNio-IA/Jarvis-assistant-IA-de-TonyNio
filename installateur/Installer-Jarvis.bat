@echo off
rem Installateur de Jarvis, assistant IA de TonyNio : double-clique sur ce fichier.
rem https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio
setlocal
title Installer Jarvis
chcp 65001 >nul
echo.
echo   Préparation de l'installateur de Jarvis (quelques secondes)...
set "JARVIS_FICHIER=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:JARVIS_FICHIER,[Text.Encoding]::UTF8); $i=$t.IndexOf('#==JARVIS-POWERSHELL=='+'#'); Invoke-Expression $t.Substring($i)"
set "CODE=%ERRORLEVEL%"
if "%CODE%"=="99" exit /b 0
if not defined JARVIS_AUTO pause
exit /b %CODE%
#==JARVIS-POWERSHELL==#
# ---------------------------------------------------------------------------------------------
#  Installateur de Jarvis, assistant IA de TonyNio
#  Installe, met à jour ou désinstalle Jarvis. Presque tout se fait dans ton dossier personnel ;
#  seuls les composants Microsoft Visual C++ (s'ils manquent) et l'accès des tablettes au pare-feu
#  demandent l'autorisation de Windows.
#  Rien n'est installé avant ton accord.
#  https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio
# ---------------------------------------------------------------------------------------------

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
$env:PYTHONIOENCODING = 'utf-8'
# Un clic dans la fenêtre ne doit pas mettre l'installation en pause (« mode d'édition rapide » de la console)
try {
    Add-Type -Name Console -Namespace JarvisInstallateur -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int n);
[DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m);
[DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);
'@
    $entree = [JarvisInstallateur.Console]::GetStdHandle(-10); $mode = [uint32]0
    if ([JarvisInstallateur.Console]::GetConsoleMode($entree, [ref]$mode)) {
        [void][JarvisInstallateur.Console]::SetConsoleMode($entree, (($mode -band (-bnot [uint32]0x40)) -bor [uint32]0x80))
    }
} catch {}
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$VERSION_INSTALLATEUR = '1.2'
$DEPOT      = 'TonyNio-IA/Jarvis-assistant-IA-de-TonyNio'
$PYTHON_VER = '3.14.10'
$PYTHON_URL = "https://www.python.org/ftp/python/$PYTHON_VER/python-$PYTHON_VER-amd64.exe"
$VC_URL     = 'https://aka.ms/vs/17/release/vc_redist.x64.exe'      # composants Microsoft Visual C++ (site de Microsoft)
$VOSK_NOM   = 'vosk-model-small-fr-0.22'
$VOSK_URL   = "https://alphacephei.com/vosk/models/$VOSK_NOM.zip"
$VOIX_NOM   = 'vosk-model-spk-0.4'            # empreintes de voix : reconnaître qui parle (profils du foyer)
$VOIX_URL   = "https://alphacephei.com/vosk/models/$VOIX_NOM.zip"
$CLAUDE_EXE = Join-Path $env:USERPROFILE '.local\bin\claude.exe'
$CLE        = 'HKCU:\Software\Jarvis-TonyNio'
$AUTO       = [bool]$env:JARVIS_AUTO          # mode sans question (essais automatiques)
$JOURNAL    = Join-Path $env:TEMP 'Jarvis-installation.log'
$TEMP       = Join-Path $env:TEMP 'Jarvis-installation'
$PERSONNELS = 'config.json','ville.txt','memoire.json','rappels.json','applications.json','notes.txt','position.txt','volumes.json','liste.json','reglages_voix.json','mise_a_jour.json','enfant.json','salutation.date','vigilance.json','recette.json','anniversaires.date','apparence.json','accueil.json','profils.json','profils','rappels_faits.json','calendrier.json','messages.json','preferences.json','corrections.json','reprise.json','infos.json','personnalite.json','cameras.json','tele','mot_appel','Jarvis-demarrage-desactive.lnk'
$UTF8       = New-Object Text.UTF8Encoding $false
$FERMER     = $false                          # vrai quand la fenêtre de l'installateur peut se fermer sans attendre

function Noter($nom) {
    # Retient, dans le registre, ce que cet installateur a installé lui-même (Python, Visual C++, Claude Code) :
    # la désinstallation ne retirera d'office que cela, jamais ce qui était déjà sur le PC avant Jarvis.
    try {
        if (-not (Test-Path -Path $CLE)) { New-Item -Path $CLE -Force | Out-Null }
        Set-ItemProperty -Path $CLE -Name $nom -Value '1'
    } catch { Journal "Note « $nom » impossible : $($_.Exception.Message)" }
}

function Journal($texte) {
    try { Add-Content -LiteralPath $JOURNAL -Value ("[{0}] {1}" -f (Get-Date -Format 'dd/MM HH:mm:ss'), $texte) -Encoding UTF8 } catch {}
}
function Dire($texte, $couleur = 'Gray', $important = $false) { Write-Host $texte -ForegroundColor $couleur; Journal $texte; if ($FEN) { Fenetre-Ligne $texte $important } }
function Titre($texte) { Write-Host ''; Write-Host ("  " + $texte) -ForegroundColor Cyan; Journal ("== " + $texte); if ($FEN) { Fenetre-Etape $texte } }
function Bon($texte) { Dire ("  [OK] " + $texte) 'Green' }
function Attention($texte) { Dire ("  [!]  " + $texte) 'Yellow' }
function Echec($texte) { throw $texte }

# ---------- La fenêtre de l'installateur (au lieu de la console noire) ----------
# Pour un nouvel utilisateur, une console noire où défilent des lignes fait peur. L'installateur montre donc une
# vraie fenêtre : les questions avec des cases, puis une barre de progression et des phrases simples. La console
# reste cachée derrière (elle revient si la fenêtre ne peut pas s'ouvrir, ou avec JARVIS_CONSOLE=1).
$FEN = $null                 # la fenêtre de progression, quand elle est ouverte
$REPONSES = @{}              # les réponses données dans la fenêtre, lues par Demander
$ETAPE = 0
$NB_ETAPES = 8
$FOND = $null; $ACCENT = $null; $GRIS = $null

function Fenetre-Possible($malgreAuto = $false) {
    if (($AUTO -and -not $malgreAuto) -or $env:JARVIS_CONSOLE) { return $false }
    try {
        Add-Type -AssemblyName System.Windows.Forms, System.Drawing
        if (-not $script:FOND) {
            [Windows.Forms.Application]::EnableVisualStyles()
            $script:FOND = [Drawing.Color]::FromArgb(13, 27, 42)
            $script:ACCENT = [Drawing.Color]::FromArgb(79, 195, 247)
            $script:GRIS = [Drawing.Color]::FromArgb(160, 180, 200)
        }
        return $true
    } catch { return $false }
}
function Console-Visible($oui) {
    try {
        if (-not ('JarvisInstallateur.Fenetre' -as [type])) {
            Add-Type -Name Fenetre -Namespace JarvisInstallateur -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int n);
'@
        }
        [void][JarvisInstallateur.Fenetre]::ShowWindow([JarvisInstallateur.Fenetre]::GetConsoleWindow(), $(if ($oui) { 5 } else { 0 }))
    } catch {}
}
function Pomper { if ($FEN) { try { [Windows.Forms.Application]::DoEvents() } catch {} } }
function Patienter($p) { $null = $p.Handle; while (-not $p.WaitForExit(150)) { Pomper } }

function Nouvelle-Fenetre($titre, $largeur, $hauteur) {
    $f = New-Object Windows.Forms.Form
    $f.Text = $titre
    $f.StartPosition = 'CenterScreen'
    $f.FormBorderStyle = 'FixedDialog'
    $f.MaximizeBox = $false
    $f.MinimizeBox = $true
    $f.BackColor = $FOND
    $f.ForeColor = [Drawing.Color]::White
    $f.Font = New-Object Drawing.Font('Segoe UI', 10)
    $f.AutoScaleMode = 'Font'
    $f.ClientSize = New-Object Drawing.Size($largeur, $hauteur)
    $f.TopMost = $true
    try {
        if ($env:JARVIS_LANCEUR -and (Test-Path -LiteralPath $env:JARVIS_LANCEUR)) {
            $f.Icon = [Drawing.Icon]::ExtractAssociatedIcon($env:JARVIS_LANCEUR)
        }
    } catch {}
    return $f
}
# --- Habillage des fenêtres : bandeau avec le réacteur, cartes arrondies, boutons arrondis, barre d'avancement.
# Chaque dessin est fait dans un « try » : si Windows refuse un effet, la fenêtre reste lisible, seulement plus simple.
function Fenetre-Tampon($controle) {
    # dessin sans scintillement (propriété protégée de Windows Forms)
    try {
        [Windows.Forms.Control].GetProperty('DoubleBuffered', [Reflection.BindingFlags]'NonPublic,Instance').SetValue($controle, $true, $null)
    } catch {}
}
function Fenetre-Ajuster($f) {
    # petit écran (ou grande échelle d'affichage) : la fenêtre ne dépasse jamais de l'écran, elle défile
    try {
        $haut = [Windows.Forms.Screen]::PrimaryScreen.WorkingArea.Height
        if ($env:JARVIS_ESSAI_ECRAN) { $haut = [int]$env:JARVIS_ESSAI_ECRAN }       # essais : hauteur d'écran simulée
        if ($f.Height -gt $haut) {
            $f.AutoScroll = $true
            $f.ClientSize = New-Object Drawing.Size(($f.ClientSize.Width + 20), [Math]::Max(240, $haut - 60))
        }
    } catch {}
}
function Fenetre-Entete($f, $titre, $sousTitre, $hauteur = 88) {
    $p = New-Object Windows.Forms.Panel
    $p.Location = New-Object Drawing.Point(0, 0)
    $p.Size = New-Object Drawing.Size($f.ClientSize.Width, $hauteur)
    $p.BackColor = [Drawing.Color]::FromArgb(16, 34, 54)
    $p.Tag = @{ T = "$titre"; S = "$sousTitre" }
    $p.Anchor = 'Top,Left,Right'                  # petit écran : le bandeau suit la largeur de la fenêtre qui défile
    Fenetre-Tampon $p
    $p.Add_Paint({
        try {
            $g = $_.Graphics
            $g.SmoothingMode = 'AntiAlias'
            $g.TextRenderingHint = 'ClearTypeGridFit'
            $l = $this.Width; $h = $this.Height
            $zone = New-Object Drawing.Rectangle 0, 0, $l, $h
            $fondu = New-Object Drawing.Drawing2D.LinearGradientBrush($zone, [Drawing.Color]::FromArgb(24, 52, 84), [Drawing.Color]::FromArgb(11, 23, 37), [single]0)
            $g.FillRectangle($fondu, $zone); $fondu.Dispose()
            # le réacteur de Jarvis : un halo, un anneau, un cœur
            $cx = 52; $cy = [int]($h / 2)
            $halo = New-Object Drawing.Drawing2D.GraphicsPath
            $halo.AddEllipse(($cx - 34), ($cy - 34), 68, 68)
            $lueur = New-Object Drawing.Drawing2D.PathGradientBrush($halo)
            $lueur.CenterColor = [Drawing.Color]::FromArgb(150, 79, 195, 247)
            $lueur.SurroundColors = [Drawing.Color[]]@([Drawing.Color]::FromArgb(0, 79, 195, 247))
            $g.FillPath($lueur, $halo); $lueur.Dispose(); $halo.Dispose()
            $anneau = New-Object Drawing.Pen([Drawing.Color]::FromArgb(79, 195, 247), 3)
            $g.DrawEllipse($anneau, ($cx - 21), ($cy - 21), 42, 42)
            $anneau.Width = 2; $anneau.Color = [Drawing.Color]::FromArgb(170, 225, 250)
            $g.DrawEllipse($anneau, ($cx - 13), ($cy - 13), 26, 26)
            for ($a = 0; $a -lt 360; $a += 45) {
                $rad = $a * [Math]::PI / 180
                $g.DrawLine($anneau, [single]($cx + 15 * [Math]::Cos($rad)), [single]($cy + 15 * [Math]::Sin($rad)), [single]($cx + 19 * [Math]::Cos($rad)), [single]($cy + 19 * [Math]::Sin($rad)))
            }
            $anneau.Dispose()
            $coeur = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(235, 250, 255))
            $g.FillEllipse($coeur, ($cx - 7), ($cy - 7), 14, 14); $coeur.Dispose()
            # titre et sous-titre
            $d = $this.Tag
            $grand = New-Object Drawing.Font('Segoe UI', 16, [Drawing.FontStyle]::Bold)
            $petit = New-Object Drawing.Font('Segoe UI', 9.5)
            $blanc = New-Object Drawing.SolidBrush([Drawing.Color]::White)
            $doux = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(170, 195, 220))
            $lignes = @("$($d.S)" -split "`n").Count
            $haut = [int](($h - 34 - 18 * $lignes) / 2)
            $g.DrawString($d.T, $grand, $blanc, [single]96, [single]$haut)
            $g.DrawString($d.S, $petit, $doux, (New-Object Drawing.RectangleF 98, ($haut + 34), ($l - 116), (18 * $lignes + 4)))
            $grand.Dispose(); $petit.Dispose(); $blanc.Dispose(); $doux.Dispose()
            # filet lumineux sous le bandeau
            $bas = New-Object Drawing.Rectangle 0, ($h - 2), $l, 2
            $filet = New-Object Drawing.Drawing2D.LinearGradientBrush($bas, [Drawing.Color]::FromArgb(79, 195, 247), [Drawing.Color]::FromArgb(0, 79, 195, 247), [single]0)
            $g.FillRectangle($filet, $bas); $filet.Dispose()
        } catch {}
    })
    $f.Controls.Add($p)
    return $p
}
function Fenetre-Carte($f, $x, $y, $l, $h) {
    # un bloc aux coins arrondis, un peu plus clair que le fond : les éléments posés dedans prennent sa couleur
    $p = New-Object Windows.Forms.Panel
    $p.Location = New-Object Drawing.Point($x, $y)
    $p.Size = New-Object Drawing.Size($l, $h)
    $p.BackColor = [Drawing.Color]::FromArgb(22, 40, 60)
    Fenetre-Tampon $p
    $p.Add_Paint({
        try {
            $g = $_.Graphics
            $g.SmoothingMode = 'AntiAlias'
            $g.Clear($this.Parent.BackColor)
            $k = 20; $d = $this.Width - 1; $b = $this.Height - 1
            $c = New-Object Drawing.Drawing2D.GraphicsPath
            $c.AddArc(0, 0, $k, $k, 180, 90); $c.AddArc(($d - $k), 0, $k, $k, 270, 90)
            $c.AddArc(($d - $k), ($b - $k), $k, $k, 0, 90); $c.AddArc(0, ($b - $k), $k, $k, 90, 90); $c.CloseFigure()
            $fond = New-Object Drawing.SolidBrush($this.BackColor)
            $bord = New-Object Drawing.Pen([Drawing.Color]::FromArgb(40, 66, 94), 1)
            $g.FillPath($fond, $c); $g.DrawPath($bord, $c)
            $fond.Dispose(); $bord.Dispose(); $c.Dispose()
        } catch {}
    })
    $f.Controls.Add($p)
    return $p
}
function Etiquette($f, $texte, $x, $y, $l, $h, $taille = 10, $gras = $false, $couleur = $null) {
    $e = New-Object Windows.Forms.Label
    $e.Text = $texte
    $e.Location = New-Object Drawing.Point($x, $y)
    $e.Size = New-Object Drawing.Size($l, $h)
    $e.Font = New-Object Drawing.Font('Segoe UI', $taille, $(if ($gras) { [Drawing.FontStyle]::Bold } else { [Drawing.FontStyle]::Regular }))
    if ($couleur) { $e.ForeColor = $couleur }
    $f.Controls.Add($e)
    return $e
}
function Case($f, $texte, $x, $y, $l, $coche) {
    $c = New-Object Windows.Forms.CheckBox
    $c.Text = $texte
    $c.Location = New-Object Drawing.Point($x, $y)
    $c.Size = New-Object Drawing.Size($l, 44)
    $c.Checked = [bool]$coche
    $f.Controls.Add($c)
    return $c
}
function Saisie($f, $x, $y, $l) {
    # champ de saisie sombre aux coins arrondis ; son contour s'allume quand on écrit dedans
    $cadre = New-Object Windows.Forms.Panel
    $cadre.Location = New-Object Drawing.Point($x, $y)
    $cadre.Size = New-Object Drawing.Size($l, 34)
    $cadre.BackColor = [Drawing.Color]::FromArgb(10, 21, 34)
    $cadre.Tag = $false
    Fenetre-Tampon $cadre
    $cadre.Add_Paint({
        try {
            $g = $_.Graphics
            $g.SmoothingMode = 'AntiAlias'
            $g.Clear($this.Parent.BackColor)
            $k = 12; $d = $this.Width - 1; $b = $this.Height - 1
            $c = New-Object Drawing.Drawing2D.GraphicsPath
            $c.AddArc(0, 0, $k, $k, 180, 90); $c.AddArc(($d - $k), 0, $k, $k, 270, 90)
            $c.AddArc(($d - $k), ($b - $k), $k, $k, 0, 90); $c.AddArc(0, ($b - $k), $k, $k, 90, 90); $c.CloseFigure()
            $fond = New-Object Drawing.SolidBrush($this.BackColor)
            $bord = New-Object Drawing.Pen($(if ($this.Tag) { [Drawing.Color]::FromArgb(79, 195, 247) } else { [Drawing.Color]::FromArgb(58, 88, 120) }), $(if ($this.Tag) { 2 } else { 1 }))
            $g.FillPath($fond, $c); $g.DrawPath($bord, $c)
            $fond.Dispose(); $bord.Dispose(); $c.Dispose()
        } catch {}
    })
    $cadre.Add_Click({ try { $this.Controls[0].Focus() } catch {} })
    $s = New-Object Windows.Forms.TextBox
    $s.BorderStyle = 'None'
    $s.BackColor = $cadre.BackColor
    $s.ForeColor = [Drawing.Color]::White
    $s.Font = New-Object Drawing.Font('Segoe UI', 11)
    $s.Location = New-Object Drawing.Point(10, 7)
    $s.Size = New-Object Drawing.Size(($l - 20), 22)
    $s.Add_Enter({ try { $this.Parent.Tag = $true; $this.Parent.Invalidate() } catch {} })
    $s.Add_Leave({ try { $this.Parent.Tag = $false; $this.Parent.Invalidate() } catch {} })
    $cadre.Controls.Add($s)
    $f.Controls.Add($cadre)
    return $s
}
function Bouton($f, $texte, $x, $y, $l, $principal) {
    $b = New-Object Windows.Forms.Button
    $b.Text = $texte
    $b.Location = New-Object Drawing.Point($x, $y)
    $b.Size = New-Object Drawing.Size($l, 38)
    $b.FlatStyle = 'Flat'
    $b.FlatAppearance.BorderSize = 0
    $b.FlatAppearance.BorderColor = $ACCENT
    $b.Cursor = [Windows.Forms.Cursors]::Hand
    $b.Tag = @{ P = [bool]$principal; H = $false }
    if ($principal) { $b.BackColor = $ACCENT; $b.ForeColor = $FOND; $b.Font = New-Object Drawing.Font('Segoe UI', 10, [Drawing.FontStyle]::Bold) }
    $b.Add_MouseEnter({ try { $this.Tag.H = $true; $this.Invalidate() } catch {} })
    $b.Add_MouseLeave({ try { $this.Tag.H = $false; $this.Invalidate() } catch {} })
    $b.Add_Paint({
        # bouton aux coins arrondis : dégradé bleu pour le bouton principal, simple contour pour l'autre
        try {
            $g = $_.Graphics
            $g.SmoothingMode = 'AntiAlias'
            $g.TextRenderingHint = 'ClearTypeGridFit'
            $g.Clear($this.Parent.BackColor)
            $k = 16; $d = $this.Width - 1; $bas = $this.Height - 1
            $c = New-Object Drawing.Drawing2D.GraphicsPath
            $c.AddArc(0, 0, $k, $k, 180, 90); $c.AddArc(($d - $k), 0, $k, $k, 270, 90)
            $c.AddArc(($d - $k), ($bas - $k), $k, $k, 0, 90); $c.AddArc(0, ($bas - $k), $k, $k, 90, 90); $c.CloseFigure()
            $zone = New-Object Drawing.Rectangle 0, 0, $this.Width, $this.Height
            if ($this.Tag.P) {
                $haut = $(if ($this.Tag.H) { [Drawing.Color]::FromArgb(150, 222, 252) } else { [Drawing.Color]::FromArgb(96, 204, 250) })
                $fond = New-Object Drawing.Drawing2D.LinearGradientBrush($zone, $haut, [Drawing.Color]::FromArgb(38, 150, 240), [single]90)
                $g.FillPath($fond, $c); $fond.Dispose()
                $encre = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(6, 18, 32))
            } else {
                $fond = New-Object Drawing.SolidBrush($(if ($this.Tag.H) { [Drawing.Color]::FromArgb(34, 60, 88) } else { [Drawing.Color]::FromArgb(18, 34, 52) }))
                $bord = New-Object Drawing.Pen([Drawing.Color]::FromArgb(79, 195, 247), 1)
                $g.FillPath($fond, $c); $g.DrawPath($bord, $c); $fond.Dispose(); $bord.Dispose()
                $encre = New-Object Drawing.SolidBrush([Drawing.Color]::White)
            }
            if ($this.Focused) {
                $tour = New-Object Drawing.Pen([Drawing.Color]::FromArgb(200, 255, 255, 255), 1)
                $g.DrawPath($tour, $c); $tour.Dispose()
            }
            $milieu = New-Object Drawing.StringFormat
            $milieu.Alignment = 'Center'; $milieu.LineAlignment = 'Center'
            $g.DrawString($this.Text, $this.Font, $encre, (New-Object Drawing.RectangleF 0, 0, $this.Width, $this.Height), $milieu)
            $encre.Dispose(); $milieu.Dispose(); $c.Dispose()
        } catch {}
    })
    $f.Controls.Add($b)
    return $b
}

function Fenetre-Choix-Double($carte, $x, $y, $titre, $largeurTitre, $premier, $largeur1, $second, $largeur2) {
    # Un titre suivi de deux choix (un seul à la fois), sur une ligne. Renvoie les deux boutons ; le premier est coché.
    [void](Etiquette $carte $titre $x ($y + 5) $largeurTitre 20 9 $false $GRIS)
    $groupe = New-Object Windows.Forms.Panel             # son propre groupe : les deux paires ne se décochent pas l'une l'autre
    $groupe.Location = New-Object Drawing.Point(($x + $largeurTitre), $y)
    $groupe.Size = New-Object Drawing.Size(($largeur1 + $largeur2 + 4), 30)
    $carte.Controls.Add($groupe)
    $boutons = @()
    $gauche = 0
    foreach ($paire in @(@($premier, $largeur1), @($second, $largeur2))) {
        $r = New-Object Windows.Forms.RadioButton
        $r.Text = $paire[0]
        $r.Font = New-Object Drawing.Font('Segoe UI', 9.5)
        $r.Location = New-Object Drawing.Point($gauche, 2)
        $r.Size = New-Object Drawing.Size($paire[1], 26)
        $groupe.Controls.Add($r)
        $boutons += $r
        $gauche += $paire[1] + 4
    }
    $boutons[0].Checked = $true
    return $boutons
}

function Fenetre-Questions($gardes) {
    # Les trois petites questions d'une nouvelle installation, dans une seule fenêtre. Renvoie $true pour installer.
    $f = Nouvelle-Fenetre 'Installer Jarvis' 600 560
    Console-Visible $false
    $script:FERMER = $true                      # console cachée : elle se fermera toute seule à la fin
    $carteFond = [Drawing.Color]::FromArgb(22, 40, 60)
    [void](Fenetre-Entete $f 'Bienvenue dans Jarvis' ("Ton assistant vocal en français. Réponds à ces petites questions, puis clique sur`n" +
                                                      "« Installer » : tout le reste se fait tout seul (10 à 20 minutes selon le PC).") 96)
    # 1. Qui es-tu ?
    $c1 = Fenetre-Carte $f 24 108 552 124
    [void](Etiquette $c1 "Ton prénom" 16 10 170 20 9 $false $GRIS)
    $prenom = Saisie $c1 16 36 170
    [void](Etiquette $c1 'Ta ville, pour la météo' 200 10 210 20 9 $false $GRIS)
    $ville = Saisie $c1 200 36 210
    [void](Etiquette $c1 'Code postal' 424 10 112 20 9 $false $GRIS)
    $codePostal = Saisie $c1 424 36 112
    $codePostal.MaxLength = 5                      # le code postal départage les villes qui portent le même nom
    # la voix de Jarvis et la façon dont il s'adresse à toi : choisies ici, Jarvis n'a plus à les demander ensuite
    $choixVoix = Fenetre-Choix-Double $c1 16 84 'Voix' 46 "d'homme" 86 'de femme' 92
    $choixVous = Fenetre-Choix-Double $c1 280 84 'Jarvis me' 74 'tutoie' 76 'vouvoie' 90
    # 2. Les options
    $c2 = Fenetre-Carte $f 24 ($c1.Bottom + 10) 552 $(if ($gardes) { 226 } else { 182 })
    $claude = Case $c2 "J'ai un abonnement Claude (Pro ou supérieur) : Jarvis pourra répondre à toutes mes questions" 16 6 520 $false
    [void](Etiquette $c2 ("Sans abonnement, Jarvis répond déjà à l'heure, la météo, les minuteurs, les rappels, la musique " +
                          "et aux commandes du PC. Tu pourras ajouter Claude plus tard.") 35 50 500 36 9 $false $GRIS)
    $demarrage = Case $c2 'Lancer Jarvis au démarrage de Windows' 16 88 520 $true
    # le rapport technique aide à corriger Jarvis : coché d'office, on peut le décocher (ou choisir « Complet » plus tard)
    $rapport = Case $c2 'Envoyer un rapport technique pour aider à améliorer Jarvis (conseillé, sans tes conversations)' 16 132 520 $true
    $reprendre = $null
    if ($gardes) {
        $reprendre = Case $c2 "Reprendre mes fichiers personnels d'une ancienne installation (réglages, profils, mémoire)" 16 176 520 $true
    }
    # 3. Ce qui sera installé
    $liste = @('Jarvis et son modèle de voix (environ 800 Mo en tout)')
    if (-not (Python-314)) { $liste += 'Python, le langage de Jarvis (dans ton dossier personnel)' }
    $liste += 'Un raccourci « Jarvis » sur le Bureau'
    $avecAccord = -not (VC-Present)
    $y = $c2.Bottom + 10
    $h3 = 20 + 17 * ($liste.Count + 1) + $(if ($avecAccord) { 38 } else { 0 })
    $c3 = Fenetre-Carte $f 24 $y 552 $h3
    [void](Etiquette $c3 'Ce qui sera installé' 16 9 520 18 9 $true $ACCENT)
    [void](Etiquette $c3 ('•  ' + ($liste -join "`n•  ")) 16 28 520 (17 * $liste.Count) 9 $false $GRIS)
    if ($avecAccord) {
        # la demande de Windows, en vert et à part, pour qu'on ne la manque pas
        [void](Etiquette $c3 '•  Des composants de Microsoft : Windows demandera ton accord, clique sur le bouton « Oui »' 16 (30 + 17 * $liste.Count) 520 36 9 $true ([Drawing.Color]::FromArgb(90, 235, 125)))
    }
    $yb = $c3.Bottom + 14
    $installer = Bouton $f 'Installer' 326 $yb 130 $true
    $annuler = Bouton $f 'Annuler' 466 $yb 110 $false
    $f.ClientSize = New-Object Drawing.Size(600, ($yb + 38 + 16))
    $installer.DialogResult = 'OK'
    $annuler.DialogResult = 'Cancel'
    $f.AcceptButton = $installer
    $f.CancelButton = $annuler
    $f.Add_Shown({ $prenom.Focus() })
    Fenetre-Ajuster $f
    if ($f.ShowDialog() -ne 'OK') { return $false }
    $script:REPONSES['JARVIS_PRENOM'] = $prenom.Text.Trim()
    $script:REPONSES['JARVIS_VILLE'] = $ville.Text.Trim()
    $script:REPONSES['JARVIS_CP'] = $codePostal.Text.Trim()
    $script:REPONSES['JARVIS_VOIX'] = $(if ($choixVoix[1].Checked) { 'femme' } else { 'homme' })
    $script:REPONSES['JARVIS_VOUS'] = $(if ($choixVous[1].Checked) { 'vous' } else { 'tu' })
    $script:REPONSES['JARVIS_CLAUDE'] = $(if ($claude.Checked) { 'o' } else { 'n' })
    $script:REPONSES['JARVIS_RAPPORT'] = $(if ($rapport.Checked) { 'technique' } else { 'aucun' })
    if ($reprendre) { $script:REPONSES['JARVIS_REPRENDRE'] = $(if ($reprendre.Checked) { 'o' } else { 'n' }) }
    $script:REPONSES['JARVIS_OK'] = 'o'
    if (-not $demarrage.Checked) { $env:JARVIS_DEMARRAGE = 'n' }
    return $true
}

function Fenetre-Choix($version, $dossier, $sansClaude, $claudeInstalle) {
    # Jarvis est déjà installé : mettre à jour, désinstaller, ajouter Claude, ou rien. Renvoie '1', '2', '3' ou '0'.
    $f = Nouvelle-Fenetre 'Installer Jarvis' 540 330
    Console-Visible $false
    $script:FERMER = $true
    [void](Fenetre-Entete $f "Jarvis $version est déjà installé" "Dossier : $dossier`nQue veux-tu faire ?" 92)
    $choix = @()
    $textes = @('Mettre à jour (ou réparer) — tes réglages et ta mémoire sont gardés', 'Désinstaller Jarvis')
    if ($sansClaude) { $textes += $(if ($claudeInstalle) { 'Connecter Claude à mon compte' } else { 'Ajouter Claude (demande un abonnement Claude)' }) }
    $carte = Fenetre-Carte $f 24 106 492 (20 + 36 * $textes.Count)
    $y = 10
    foreach ($t in $textes) {
        $r = New-Object Windows.Forms.RadioButton
        $r.Text = $t
        $r.Location = New-Object Drawing.Point(16, $y)
        $r.Size = New-Object Drawing.Size(460, 30)
        $carte.Controls.Add($r)
        $choix += $r
        $y += 36
    }
    $choix[0].Checked = $true
    $yb = $carte.Bottom + 16
    $ok = Bouton $f 'Continuer' 266 $yb 130 $true
    $non = Bouton $f 'Fermer' 406 $yb 110 $false
    $f.ClientSize = New-Object Drawing.Size(540, ($yb + 38 + 16))
    $ok.DialogResult = 'OK'
    $non.DialogResult = 'Cancel'
    $f.AcceptButton = $ok
    $f.CancelButton = $non
    Fenetre-Ajuster $f
    if ($f.ShowDialog() -ne 'OK') { return '0' }
    for ($i = 0; $i -lt $choix.Count; $i++) { if ($choix[$i].Checked) { $script:REPONSES['JARVIS_OK'] = 'o'; return [string]($i + 1) } }
    return '0'
}

function Fenetre-Progression($titre) {
    if ($FEN -or -not (Fenetre-Possible ($AUTO -and $env:JARVIS_FENETRE_MAJ -eq '1'))) { return }   # mise à jour lancée par Jarvis : la fenêtre montre l'avancée
    $f = Nouvelle-Fenetre 'Installer Jarvis' 600 478
    $f.ControlBox = $false                      # pas de croix pendant l'installation : elle s'arrêterait au milieu
    $f.TopMost = $false                         # le navigateur (connexion à Claude) doit pouvoir passer devant
    [void](Fenetre-Entete $f $titre "Tout se fait tout seul : laisse cette fenêtre ouverte jusqu'à la fin." 84)
    $etape = Etiquette $f 'Préparation...' 24 98 552 26 12 $true
    # barre d'avancement arrondie, en dégradé bleu
    $barre = New-Object Windows.Forms.Panel
    $barre.Location = New-Object Drawing.Point(24, 130)
    $barre.Size = New-Object Drawing.Size(552, 14)
    $barre.Tag = @{ V = 0; M = [Math]::Max(1, $NB_ETAPES) }
    Fenetre-Tampon $barre
    $barre.Add_Paint({
        try {
            $g = $_.Graphics
            $g.SmoothingMode = 'AntiAlias'
            $g.Clear($this.Parent.BackColor)
            $h = $this.Height - 1
            foreach ($passe in 0, 1) {
                $l = $(if ($passe) { [int](($this.Width - 1) * [Math]::Min(1.0, $this.Tag.V / $this.Tag.M)) } else { $this.Width - 1 })
                if ($l -lt $h) { if ($passe) { continue }; $l = $h }
                $c = New-Object Drawing.Drawing2D.GraphicsPath
                $c.AddArc(0, 0, $h, $h, 90, 180); $c.AddArc(($l - $h), 0, $h, $h, 270, 180); $c.CloseFigure()
                if ($passe) {
                    $zone = New-Object Drawing.Rectangle 0, 0, ($l + 1), ($h + 1)
                    $fond = New-Object Drawing.Drawing2D.LinearGradientBrush($zone, [Drawing.Color]::FromArgb(38, 150, 240), [Drawing.Color]::FromArgb(120, 220, 252), [single]0)
                } else { $fond = New-Object Drawing.SolidBrush([Drawing.Color]::FromArgb(24, 44, 66)) }
                $g.FillPath($fond, $c); $fond.Dispose(); $c.Dispose()
            }
        } catch {}
    })
    $f.Controls.Add($barre)
    $detail = Etiquette $f '' 24 152 552 42 10 $false $GRIS
    $carte = Fenetre-Carte $f 24 200 552 212
    $texte = New-Object Windows.Forms.RichTextBox
    $texte.DetectUrls = $false
    $texte.Multiline = $true
    $texte.ReadOnly = $true
    $texte.ScrollBars = 'Vertical'
    $texte.Location = New-Object Drawing.Point(12, 10)
    $texte.Size = New-Object Drawing.Size(530, 192)
    $texte.BackColor = $carte.BackColor
    $texte.ForeColor = [Drawing.Color]::White
    $texte.BorderStyle = 'None'
    $texte.Font = New-Object Drawing.Font('Segoe UI', 9)
    $carte.Controls.Add($texte)
    $bouton = Bouton $f 'Terminer' 446 424 130 $true
    $bouton.Visible = $false
    $bouton.Add_Click({ $this.FindForm().Close() })
    Fenetre-Ajuster $f
    $f.Show()
    Console-Visible $false
    $script:FEN = @{ Form = $f; Etape = $etape; Barre = $barre; Detail = $detail; Texte = $texte; Bouton = $bouton }
    Pomper
}
function Fenetre-Barre($valeur) {
    try { $FEN.Barre.Tag.V = $valeur; $FEN.Barre.Invalidate() } catch {}
}
function Fenetre-Ligne($texte, $important = $false) {
    # $important : consigne à ne pas manquer (« clique sur Oui »), écrite en vert
    $t = "$texte".Trim()
    if (-not $t -or $t -match '^-{5,}$') { return }
    try {
        $VERT = [Drawing.Color]::FromArgb(90, 235, 125); $GRIS_ = [Drawing.Color]::FromArgb(160, 180, 200)
        $FEN.Detail.ForeColor = $(if ($important) { $VERT } else { $GRIS_ })
        $FEN.Detail.Text = $t
        $FEN.Texte.SelectionStart = $FEN.Texte.TextLength
        $FEN.Texte.SelectionLength = 0
        $FEN.Texte.SelectionColor = $(if ($important) { $VERT } else { [Drawing.Color]::White })
        $FEN.Texte.AppendText($t + "`r`n")
        $FEN.Texte.ScrollToCaret()
    } catch {}
    Pomper
}
function Fenetre-Etape($texte) {
    $script:ETAPE++
    try {
        Fenetre-Barre ([Math]::Min($ETAPE, $NB_ETAPES))
        $FEN.Etape.Text = $texte
    } catch {}
    Pomper
}
function Fenetre-Fin($titre) {
    # La fenêtre reste ouverte : on lit « À retenir », puis on clique sur Terminer
    try {
        Fenetre-Barre $NB_ETAPES
        $FEN.Etape.Text = $titre
        $FEN.Etape.ForeColor = [Drawing.Color]::FromArgb(79, 195, 247)       # le vert reste réservé aux consignes « clique sur Oui »
        $FEN.Detail.ForeColor = [Drawing.Color]::White
        $FEN.Detail.Text = $(if ($AUTO) { 'Jarvis redémarre tout seul : cette fenêtre se ferme.' } else { 'Lis « À RETENIR » ci-dessous, puis clique sur Terminer.' })
        $FEN.Bouton.Visible = $true
        $FEN.Form.ControlBox = $true
        $FEN.Form.AcceptButton = $FEN.Bouton
        $FEN.Texte.SelectionStart = $FEN.Texte.Text.Length
        $FEN.Texte.ScrollToCaret()
        $limite = (Get-Date).AddSeconds(8)
        while ($FEN.Form.Visible) {
            [Windows.Forms.Application]::DoEvents(); Start-Sleep -Milliseconds 80
            if ($AUTO -and (Get-Date) -gt $limite) { $FEN.Form.Close() }       # mise à jour automatique : personne ne clique
        }
    } catch {}
    $script:FEN = $null
}
function Fenetre-Erreur($message) {
    if (-not (Fenetre-Possible)) { return }
    try {
        if ($FEN) { $FEN.Form.Hide() }
        Console-Visible $true                   # la console montre aussi l'erreur, et attend une touche pour se fermer
        [void][Windows.Forms.MessageBox]::Show(("L'installation s'est arrêtée :`n`n" + $message +
            "`n`nTu peux relancer l'installateur : il reprendra sans rien casser.`nJournal : $JOURNAL"),
            'Installer Jarvis', 'OK', 'Warning')
    } catch {}
    $script:FEN = $null
}

function Demander($question, $defaut, $variable) {
    if ($variable -and $REPONSES.ContainsKey($variable)) {     # déjà répondu dans la fenêtre
        $valeur = $REPONSES[$variable]
        if ([string]::IsNullOrWhiteSpace($valeur)) { $valeur = $defaut }
        Journal "$question -> (réponse de la fenêtre)"
        return "$valeur"
    }
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

function Pip($env_py, $arguments, $quoi) {
    # pip travaille dans l'ombre : ses lignes techniques (en anglais) vont dans le journal, et une ligne
    # « ... toujours en cours » rassure toutes les 30 secondes. Renvoie le code de sortie de pip.
    $sortie = Join-Path $TEMP 'pip-sortie.txt'
    $erreurs = Join-Path $TEMP 'pip-erreurs.txt'
    $p = Start-Process -FilePath $env_py -ArgumentList $arguments -WindowStyle Hidden -PassThru `
         -RedirectStandardOutput $sortie -RedirectStandardError $erreurs
    $null = $p.Handle                                  # sans cela, le code de sortie peut rester vide
    $debut = Get-Date
    $prochaine = 30
    while (-not $p.WaitForExit(200)) {
        Pomper
        $ecoule = (Get-Date) - $debut
        if ($ecoule.TotalSeconds -lt $prochaine) { continue }
        $prochaine += 30
        Dire ("  ... {0} : toujours en cours ({1} min {2:00} s)" -f $quoi, [int][math]::Floor($ecoule.TotalMinutes), $ecoule.Seconds)
    }
    $p.WaitForExit()
    foreach ($f in $sortie, $erreurs) {
        Get-Content -LiteralPath $f -Encoding UTF8 -ErrorAction SilentlyContinue | ForEach-Object { Journal "pip | $_" }
    }
    if ($p.ExitCode -ne 0) {
        Get-Content -LiteralPath $erreurs -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -Last 8 |
            ForEach-Object { Dire "    $_" 'DarkGray' }
    }
    return $p.ExitCode
}

function Controle-Applications {
    # « Contrôle intelligent des applications » (Windows 11) : il vérifie un à un les fichiers de Jarvis, ce qui peut
    # rendre l'installation et le premier démarrage beaucoup plus longs (vu sur un portable : 107 s pour un seul module)
    try {
        $etat = (Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\CI\Policy' -Name VerifiedAndReputablePolicyState -ErrorAction Stop).VerifiedAndReputablePolicyState
    } catch { return }
    Journal "Contrôle intelligent des applications : $etat (0 désactivé, 1 activé, 2 évaluation)"
    if ($etat -in 1, 2) {
        Attention "Le « Contrôle intelligent des applications » de Windows est $(if ($etat -eq 1) { 'activé' } else { 'en évaluation' }) sur ce PC."
        Dire "       Il vérifie un à un les fichiers de Jarvis : l'installation et le premier démarrage peuvent être"
        Dire "       bien plus longs que d'habitude (jusqu'à 20 minutes). C'est normal : ne ferme pas cette fenêtre."
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
        $p = Start-Process -FilePath curl.exe -ArgumentList ('-L --fail --retry 2 --connect-timeout 30 -sS -o "' + $fichier + '" "' + $adresse + '"') -WindowStyle Hidden -PassThru
        Patienter $p
        $LASTEXITCODE = $p.ExitCode
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
    Dire "  Windows va te demander l'autorisation de les installer : clique sur le bouton « Oui » (Entrée seule répondrait « Non »)." 'Green' $true
    try {
        $p = Start-Process -FilePath $programme -ArgumentList '/install','/quiet','/norestart' -Wait -PassThru
        if ($p.ExitCode -in 0, 3010) { Noter 'VCInstalle' }       # 1638 : une version plus récente était déjà là
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

# ---------- Fichiers personnels gardés lors d'une désinstallation ----------
function Fichiers-Gardes {
    # Le dossier « Jarvis - fichiers personnels » du Bureau, sinon la copie compressée la plus récente, sinon rien
    $ErrorActionPreference = 'SilentlyContinue'
    $bureau = [Environment]::GetFolderPath('Desktop')
    $d = if ($env:JARVIS_GARDES) { $env:JARVIS_GARDES } else { Join-Path $bureau 'Jarvis - fichiers personnels' }
    if ($d -like '*.zip') { if (Test-Path -LiteralPath $d) { return $d } else { return $null } }
    if ((Test-Path -LiteralPath $d -PathType Container) -and (Get-ChildItem -LiteralPath $d -Force | Where-Object { $_.Name -in $PERSONNELS } | Select-Object -First 1)) { return $d }
    if ($env:JARVIS_GARDES) { return $null }
    $zip = Get-ChildItem -LiteralPath $bureau -Filter 'Jarvis-sauvegarde-*.zip' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($zip) { return $zip.FullName }
    return $null
}
function Reprendre-Fichiers($source, $dossier) {
    # Seuls des fichiers personnels connus sont repris : jamais de programme ni de raccourci
    try {
        $origine = $source
        if ($source -like '*.zip') {
            $origine = Join-Path $TEMP 'fichiers-gardes'
            if (Test-Path -LiteralPath $origine) { Remove-Item -LiteralPath $origine -Recurse -Force }
            Expand-Archive -LiteralPath $source -DestinationPath $origine -Force
        }
        $n = 0
        Get-ChildItem -LiteralPath $origine -Force | Where-Object { $_.Name -in $PERSONNELS -and $_.Name -notlike '*.lnk' } | ForEach-Object {
            Copy-Item -LiteralPath $_.FullName -Destination $dossier -Recurse -Force
            $n++
        }
        Bon "Tes fichiers personnels sont repris ($n éléments). Tu peux garder ou supprimer « $(Split-Path -Leaf $source) » sur le Bureau."
    } catch {
        Journal "Reprise des fichiers personnels : $($_.Exception.Message)"
        Attention "Tes fichiers personnels n'ont pas pu être repris. Ils sont toujours ici : $source"
    }
}

# ---------- Récupérer les fichiers de Jarvis ----------
function Version-Stable-Choisie($client) {
    # installation-stable.txt (à la racine du dépôt, branche main) : l'étiquette de la version publiée par laquelle commence
    # une PREMIÈRE installation (ex. v1.47). Rien d'exploitable (fichier absent, illisible, « latest », étiquette inconnue,
    # pas de réseau) : on renvoie $null et l'installateur prend la dernière version publiée, comme avant.
    $adresse = if ($env:JARVIS_URL_VERSION_STABLE) { $env:JARVIS_URL_VERSION_STABLE } else { "https://raw.githubusercontent.com/$DEPOT/main/installation-stable.txt" }
    try {
        $lignes = @($client.DownloadString($adresse) -split "`n" | ForEach-Object { $_.Trim() } | Where-Object { $_ -and -not $_.StartsWith('#') })
        $choisie = if ($lignes.Count) { [string]$lignes[0] } else { '' }
        if ($choisie -match '^v\d+(\.\d+){1,3}$') {
            # la version existe-t-elle ? (son archive répond : pas l'API de GitHub, limitée à 60 appels par heure et par adresse)
            $p = Start-Process -FilePath curl.exe -ArgumentList ('-L --head --fail --silent --connect-timeout 20 --max-time 40 -o NUL "https://github.com/' + $DEPOT + '/archive/refs/tags/' + $choisie + '.zip"') -WindowStyle Hidden -PassThru -Wait
            if ($p.ExitCode -eq 0) {
                Journal "Première installation : version stable choisie $choisie."
                return $choisie
            }
            Journal "La version stable choisie ($choisie) est introuvable (code curl $($p.ExitCode)) : dernière version publiée à la place."
        } elseif ($choisie) { Journal "installation-stable.txt : « $choisie » n'est pas une étiquette de version : dernière version publiée à la place." }
    } catch { Journal "Version stable non lue ($($_.Exception.Message)) : dernière version publiée à la place." }
    return $null
}

function Copier-Programme($dossier) {
    New-Item -ItemType Directory -Path $dossier -Force | Out-Null
    $miseAJour = Test-Path -LiteralPath (Join-Path $dossier 'jarvis_gardien.py')       # Jarvis est déjà là : c'est une mise à jour
    $source = $env:JARVIS_SOURCE                       # dossier local (essais avant publication)
    $etiquette = 'copie locale'
    if (-not $source) {
        $etiquette = 'main'
        try {
            $client = New-Object Net.WebClient
            $client.Headers['User-Agent'] = 'Jarvis-Installateur'
            $client.Encoding = [Text.Encoding]::UTF8
            # JARVIS_ETIQUETTE : la version voulue (une pre-version pour un testeur volontaire) ; sinon la derniere publiee
            if ($env:JARVIS_ETIQUETTE) { $etiquette = $env:JARVIS_ETIQUETTE }
            else {
                if (-not $miseAJour) {                 # première installation : la version stable choisie, sinon la dernière
                    $choisie = Version-Stable-Choisie $client
                    if ($choisie) { $etiquette = $choisie }
                }
                if ($etiquette -eq 'main') { $etiquette = ($client.DownloadString("https://api.github.com/repos/$DEPOT/releases/latest") | ConvertFrom-Json).tag_name }
            }
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
        $_.Name -like 'jarvis_*.py' -or $_.Name -like '*.md' -or $_.Name -in 'requirements.txt','requirements-ps5.txt','config.exemple.json','.gitignore'
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
    Dire "  Installation des modules de Jarvis (environ 600 Mo : 3 à 10 minutes selon le PC et la connexion)..."
    Dire "  Ne ferme pas la fenêtre : une ligne « toujours en cours » s'affiche de temps en temps."
    $code = Pip $env_py ('-m pip install --disable-pip-version-check --no-warn-script-location --progress-bar off -r "' + (Join-Path $dossier 'requirements.txt') + '"') "Modules de Jarvis"
    if ($code -ne 0) { Echec "L'installation des modules de Jarvis a échoué (le détail est dans le journal : $JOURNAL). Vérifie la connexion à Internet, puis relance l'installateur ; si l'erreur revient, signale-la sur GitHub." }
    Bon "Modules Python installés."
    Installer-Modules-PS5 $dossier $env_py
    return $env_py
}

function Installer-Modules-PS5($dossier, $env_py) {
    # Pilotage de la PlayStation 5 (allumer, mettre en veille). Ces modules s'installent sans leurs dépendances
    # (« --no-deps ») : l'une d'elles, « netifaces », ne s'installe pas sur Windows avec Python 3.14, et Jarvis la remplace
    # lui-même. Cette étape n'arrête jamais l'installation : en cas d'échec, seule la lecture de l'état de la PS5 reste.
    $liste = Join-Path $dossier 'requirements-ps5.txt'
    if (-not (Test-Path -LiteralPath $liste)) { return }
    Dire "  Installation des modules de la PlayStation 5..."
    $ErrorActionPreference = 'Continue'
    try {
        $ok = ((Pip $env_py ('-m pip install --disable-pip-version-check --no-warn-script-location --progress-bar off --no-deps -r "' + $liste + '"') "Modules de la PlayStation 5") -eq 0)
    } catch { $ok = $false; Journal "Modules PS5 : $($_.Exception.Message)" }
    if ($ok) { Bon "Modules de la PlayStation 5 installés." }
    else {
        Attention "Les modules de la PlayStation 5 n'ont pas pu être installés : l'installation continue sans eux."
        Attention "Jarvis dira quand même si la PS5 est allumée. Pour réessayer : relance ce fichier et choisis 1."
    }
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

function Installer-Vosk-Voix($dossier) {
    # Petit modèle des empreintes de voix (environ 13 Mo) : Jarvis reconnaît qui parle et passe tout seul sur son profil
    # (« Jarvis, apprends ma voix »). Facultatif : en cas d'échec, l'installation continue sans lui.
    $cible = Join-Path $dossier $VOIX_NOM
    if (Test-Path -LiteralPath (Join-Path $cible 'final.ext.raw')) { Bon "Modèle des empreintes de voix déjà présent."; return }
    try {
        $zip = Join-Path $TEMP 'vosk-voix.zip'
        Telecharger $VOIX_URL $zip "modèle des empreintes de voix (environ 13 Mo)"
        Expand-Archive -LiteralPath $zip -DestinationPath $dossier -Force
        if (-not (Test-Path -LiteralPath (Join-Path $cible 'final.ext.raw'))) { throw "fichiers absents après décompression" }
        Bon "Modèle des empreintes de voix installé (reconnaissance de qui parle)."
    } catch {
        Journal "Modèle des empreintes de voix : $($_.Exception.Message)"
        Attention "Le modèle des empreintes de voix n'a pas pu être installé : l'installation continue sans lui."
        Attention "Jarvis marche normalement, mais ne reconnaîtra pas qui parle. Pour réessayer : relance ce fichier et choisis 1."
    }
}

# ---------- La ville de la météo : nom + code postal ----------
# Avant, l'installateur prenait le premier résultat du monde entier pour le nom tapé : « bouret » donnait une commune de
# Roumanie, et « saint-martin » l'une des communes de ce nom, au hasard. Maintenant : l'annuaire officiel des
# communes françaises d'abord (avec le code postal quand il est donné), le reste du monde ensuite.
function Ville-Simple($t) {
    $s = "$t".ToLowerInvariant().Normalize([Text.NormalizationForm]::FormD)
    $s = [regex]::Replace($s, '\p{Mn}', '')
    $s = [regex]::Replace($s, '[^a-z0-9]+', ' ').Trim()
    $s = [regex]::Replace($s, '\bste\b', 'sainte')
    return [regex]::Replace($s, '\bst\b', 'saint')
}
function Ville-Ressemblance($a, $b) {
    # 1 = même nom ; sinon la part de lettres communes (distance d'édition rapportée à la longueur)
    $a = Ville-Simple $a; $b = Ville-Simple $b
    if (-not $a -or -not $b) { return 0.0 }
    if ($a -eq $b) { return 1.0 }
    $n = $a.Length; $m = $b.Length
    $avant = New-Object int[] ($m + 1)
    for ($j = 0; $j -le $m; $j++) { $avant[$j] = $j }
    for ($i = 1; $i -le $n; $i++) {
        $ligne = New-Object int[] ($m + 1)
        $ligne[0] = $i
        for ($j = 1; $j -le $m; $j++) {
            $cout = $(if ($a[$i - 1] -eq $b[$j - 1]) { 0 } else { 1 })
            $ligne[$j] = [Math]::Min([Math]::Min($avant[$j] + 1, $ligne[$j - 1] + 1), $avant[$j - 1] + $cout)
        }
        $avant = $ligne
    }
    return 1.0 - ($avant[$m] / [double][Math]::Max($n, $m))
}
function Ville-Lire($adresse) {
    # Une page d'un service de villes, avec un délai court : l'installation n'attend pas un service en panne
    $demande = [Net.WebRequest]::Create($adresse)
    $demande.Timeout = 12000
    $demande.UserAgent = 'Jarvis-Installateur'
    $reponse = $demande.GetResponse()
    try {
        $lecteur = New-Object IO.StreamReader($reponse.GetResponseStream(), [Text.Encoding]::UTF8)
        return $lecteur.ReadToEnd()
    } finally { $reponse.Close() }
}
function Communes-France($requete) {
    # Annuaire officiel des communes françaises (geo.api.gouv.fr). Liste vide si rien, ou si le service ne répond pas.
    try {
        $texte = Ville-Lire ("https://geo.api.gouv.fr/communes?$requete&fields=nom,centre,population,departement,codesPostaux&format=json")
        return @($texte | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { $_.centre -and $_.nom })
    } catch { Journal "Annuaire des communes ($requete) : $($_.Exception.Message)"; return @() }
}
function Ville-Resultat($commune, $note) {
    $cp = @($commune.codesPostaux)[0]
    $ou = @($commune.departement.nom, $cp) | Where-Object { $_ }
    return @{ Nom = [string]$commune.nom; Lat = [double]$commune.centre.coordinates[1]; Lon = [double]$commune.centre.coordinates[0]
              Ou = ($ou -join ', '); Note = $note }
}
function Trouver-Ville($ville, $codePostal) {
    # Renvoie @{ Nom; Lat; Lon; Ou; Note } ou $null. « Note » : une phrase à montrer quand le choix n'est pas certain.
    $nom = "$ville".Trim()
    $cp = "$codePostal" -replace '\D', ''
    if ($cp.Length -ne 5) { $cp = '' }
    $plusieurs = $null
    # 1. Le code postal : la commune de ce code qui porte (à peu près) ce nom
    if ($cp) {
        $communes = @(Communes-France "codePostal=$cp")
        if ($communes.Count) {
            if ($nom) {
                $meilleure = @($communes | Sort-Object { Ville-Ressemblance $nom $_.nom } -Descending)[0]
                if ((Ville-Ressemblance $nom $meilleure.nom) -ge 0.6) { return Ville-Resultat $meilleure '' }
                $debut = @($communes | Where-Object { (Ville-Simple $_.nom).StartsWith((Ville-Simple $nom) + ' ') })
                if ($debut.Count -eq 1) { return Ville-Resultat $debut[0] '' }
            } elseif ($communes.Count -eq 1) { return Ville-Resultat $communes[0] '' }
            $plusieurs = @($communes | Sort-Object { [int]$_.population } -Descending)[0]
            if (-not $nom) {
                return Ville-Resultat $plusieurs ("Plusieurs communes ont le code postal $cp : j'ai pris la plus peuplée. Si ce n'est pas la tienne, dis « Jarvis, ma ville est … » avec son nom.")
            }
        }
    }
    # 2. Le nom, parmi les communes françaises
    if ($nom) {
        $simple = Ville-Simple $nom
        $communes = @(Communes-France ("nom=" + [uri]::EscapeDataString($simple) + "&boost=population&limit=10"))
        $departement = $(if ($cp) { $(if ($cp.StartsWith('97') -or $cp.StartsWith('98')) { $cp.Substring(0, 3) } else { $cp.Substring(0, 2) }) } else { '' })
        if ($departement) {
            $duCoin = @($communes | Where-Object { $_.departement.code -eq $departement })
            if ($duCoin.Count) { $communes = $duCoin }
        }
        $exactes = @($communes | Where-Object { (Ville-Simple $_.nom) -eq $simple } | Sort-Object { [int]$_.population } -Descending)
        if ($exactes.Count -eq 1) {
            $note = $(if ($cp -and @($exactes[0].codesPostaux) -notcontains $cp) { "Le code postal $cp ne correspond pas à $($exactes[0].nom) : j'ai gardé la ville." } else { '' })
            return Ville-Resultat $exactes[0] $note
        }
        if ($exactes.Count -gt 1) {
            return Ville-Resultat $exactes[0] ("Il existe $($exactes.Count) communes nommées $($exactes[0].nom) : j'ai pris la plus peuplée. Si ce n'est pas la tienne, dis « Jarvis, ma ville est $($exactes[0].nom), » suivi de ton code postal.")
        }
        $proches = @($communes | Sort-Object { Ville-Ressemblance $nom $_.nom } -Descending)
        if ($proches.Count -and (Ville-Ressemblance $nom $proches[0].nom) -ge 0.75) {
            return Ville-Resultat $proches[0] ("Je n'ai pas trouvé « $nom » : j'ai pris « $($proches[0].nom) ». Si ce n'est pas ta ville, dis « Jarvis, ma ville est … ».")
        }
        $debut = @($communes | Where-Object { (Ville-Simple $_.nom).StartsWith($simple + ' ') } | Sort-Object { [int]$_.population } -Descending)
        if ($plusieurs) {
            return Ville-Resultat $plusieurs ("Je n'ai pas trouvé « $nom » avec le code postal $cp : j'ai pris la commune la plus peuplée de ce code. Si ce n'est pas la tienne, dis « Jarvis, ma ville est … ».")
        }
        # 3. Ailleurs dans le monde (une ville de France passe d'abord, puis le nom le plus proche)
        try {
            $r = @((Ville-Lire ('https://geocoding-api.open-meteo.com/v1/search?count=10&language=fr&format=json&name=' + [uri]::EscapeDataString($nom)) | ConvertFrom-Json).results | Where-Object { $_ })
            $memes = @($r | Where-Object { (Ville-Simple $_.name) -eq $simple })
            $choix = @($memes | Where-Object { $_.country_code -eq 'FR' })[0]
            if (-not $choix) { $choix = $memes[0] }
            if (-not $choix -and $debut.Count) {
                return Ville-Resultat $debut[0] ("Je n'ai pas trouvé « $nom » : j'ai pris « $($debut[0].nom) ». Si ce n'est pas ta ville, dis « Jarvis, ma ville est … ».")
            }
            if (-not $choix) { $choix = @($r | Where-Object { $_.country_code -eq 'FR' })[0] }
            if (-not $choix) { $choix = $r[0] }
            if ($choix) {
                $ou = @($choix.admin1, $choix.country) | Where-Object { $_ }
                $note = $(if ((Ville-Simple $choix.name) -ne $simple) { "Je n'ai pas trouvé « $nom » : j'ai pris « $($choix.name) ». Si ce n'est pas ta ville, dis « Jarvis, ma ville est … »." } else { '' })
                return @{ Nom = [string]$choix.name; Lat = [double]$choix.latitude; Lon = [double]$choix.longitude; Ou = ($ou -join ', '); Note = $note }
            }
        } catch { Journal "Recherche de la ville dans le monde : $($_.Exception.Message)" }
        if ($debut.Count) {
            return Ville-Resultat $debut[0] ("Je n'ai pas trouvé « $nom » : j'ai pris « $($debut[0].nom) ». Si ce n'est pas ta ville, dis « Jarvis, ma ville est … ».")
        }
    }
    return $null
}

function Ecrire-Rapport($dossier, $choix) {
    # La case « rapport technique » de l'installateur. Ceux qui avaient choisi « Complet » restent en « Complet ».
    if ($choix -notin @('technique', 'aucun')) { return }
    $fichier = Join-Path $dossier 'rapports.json'
    $d = $null
    if (Test-Path -LiteralPath $fichier) {
        try { $d = [IO.File]::ReadAllText($fichier, [Text.Encoding]::UTF8) | ConvertFrom-Json } catch { $d = $null }
    }
    if (-not $d) { $d = New-Object PSObject }
    if ($choix -eq 'technique' -and $d.niveau -eq 'complet') { Bon 'Rapports : « Complet », comme avant.'; return }
    $maintenant = [double]([DateTimeOffset]::Now.ToUnixTimeMilliseconds()) / 1000
    $d | Add-Member -NotePropertyName niveau -NotePropertyValue $choix -Force
    $d | Add-Member -NotePropertyName choisi_le -NotePropertyValue $maintenant -Force
    $d | Add-Member -NotePropertyName bascule_165 -NotePropertyValue $true -Force
    if ($choix -eq 'aucun') { $d | Add-Member -NotePropertyName refuse_le -NotePropertyValue $maintenant -Force }
    if ($d.PSObject.Properties['par_defaut']) { $d.PSObject.Properties.Remove('par_defaut') }
    try {
        [IO.File]::WriteAllText($fichier, ($d | ConvertTo-Json -Depth 6), $UTF8)
        Bon $(if ($choix -eq 'technique') { 'Rapport technique activé (tu peux le changer dans les Réglages, rubrique Rapports).' } else { 'Rapports : aucun.' })
    } catch { Attention "Le choix des rapports n'a pas pu être enregistré : Jarvis le demandera au premier démarrage." }
}

function Ecrire-Reglages($dossier, $prenom, $ville, $codePostal = '', $voix = '', $vous = '') {
    $config = Join-Path $dossier 'config.json'
    if (Test-Path -LiteralPath $config) { Bon "Réglages déjà présents : conservés." }
    else {
        $texte = [IO.File]::ReadAllText((Join-Path $dossier 'config.exemple.json'), [Text.Encoding]::UTF8)
        $propre = ($prenom -replace '["\\\r\n]', '').Trim()
        if (-not $propre) { $propre = 'Alex' }
        if ($propre -ceq $propre.ToLower()) { $propre = (Get-Culture).TextInfo.ToTitleCase($propre) }   # « alex » -> « Alex »
        $texte = [regex]::Replace($texte, '"prenom"\s*:\s*"[^"]*"', ('"prenom": "' + $propre.Replace('$', '$$') + '"'))
        [IO.File]::WriteAllText($config, $texte, $UTF8)
        Bon "Réglages créés (prénom : $propre). Tu pourras les changer en disant « Jarvis, ouvre les réglages »."
        # nouvel utilisateur : Jarvis fera connaissance pendant les premières conversations (voix, tutoiement...)
        # ... sauf pour ce qui a déjà été choisi dans l'installateur : la voix et le tutoiement ou le vouvoiement
        $faites = @()
        $accueil = '{"nouveau": true'
        $v = "$voix".Trim().ToLower()
        $voixChoisie = $(if ($v -match '^(f|femme|denise)') { 'denise' } elseif ($v -match '^(h|homme|henri)') { 'henri' } else { '' })
        if ($voixChoisie) {
            $faites += '"voix"'
            $fichierVoix = Join-Path $dossier 'reglages_voix.json'
            if (-not (Test-Path -LiteralPath $fichierVoix)) {
                [IO.File]::WriteAllText($fichierVoix, ('{"voix": "' + $voixChoisie + '", "vitesse": 12, "nuit": null}'), $UTF8)
            }
        }
        $t = "$vous".Trim().ToLower()
        $vousChoisi = $(if ($t -match '^(v|vous|vouvoie)') { 'true' } elseif ($t -match '^(t|tu|tutoie)') { 'false' } else { '' })
        if ($vousChoisi) { $faites += '"tutoiement"'; $accueil += ', "vous": ' + $vousChoisi }
        if ($faites.Count) { $accueil += ', "faites": [' + ($faites -join ', ') + ']' }
        [IO.File]::WriteAllText((Join-Path $dossier 'accueil.json'), ($accueil + '}'), $UTF8)
        $dit = @()
        if ($voixChoisie) { $dit += "parlera avec une voix $(if ($voixChoisie -eq 'denise') { 'de femme' } else { "d'homme" })" }
        if ($vousChoisi) { $dit += "te $(if ($vousChoisi -eq 'true') { 'vouvoiera' } else { 'tutoiera' })" }
        if ($dit.Count) { Bon ("Jarvis " + ($dit -join ' et ') + ".") }
    }
    $fichierVille = Join-Path $dossier 'ville.txt'
    if ((Test-Path -LiteralPath $fichierVille) -or -not ("$ville$codePostal".Trim())) { return }
    try {
        $trouvee = Trouver-Ville $ville $codePostal
        if (-not $trouvee) { Attention "Ville « $("$ville $codePostal".Trim()) » introuvable : la météo sera celle de Paris. Plus tard, dis « Jarvis, ma ville est … » (avec le nom de ta ville)."; return }
        $ic = [Globalization.CultureInfo]::InvariantCulture
        $ligne = '{0};{1};{2}' -f ($trouvee.Nom -replace ';', ' '), $trouvee.Lat.ToString('0.####', $ic), $trouvee.Lon.ToString('0.####', $ic)
        [IO.File]::WriteAllText($fichierVille, $ligne + "`r`n", $UTF8)
        Bon "Ville de la météo : $($trouvee.Nom)$(if ($trouvee.Ou) { " ($($trouvee.Ou))" })."
        if ($trouvee.Note) { Attention $trouvee.Note }
    } catch { Attention "La ville n'a pas pu être vérifiée (pas de réponse du service) : la météo sera celle de Paris. Plus tard, dis « Jarvis, ma ville est … »." }
}

function Installer-Claude {
    if (Test-Path -LiteralPath $CLAUDE_EXE) { Bon "Claude Code déjà installé." }
    else {
        Dire "  Installation de Claude Code (programme officiel d'Anthropic, environ 370 Mo : plusieurs minutes)..."
        # Les messages (en anglais) de l'installation officielle vont dans le journal : ils parlent de « PATH », ce qui
        # inquiétait pour rien (Jarvis trouve Claude tout seul)
        $sortieClaude = Join-Path $TEMP 'claude-installation.txt'
        $p = Start-Process -FilePath powershell.exe -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference=''SilentlyContinue''; irm https://claude.ai/install.ps1 | iex"' `
             -WindowStyle Hidden -PassThru -RedirectStandardOutput $sortieClaude -RedirectStandardError ($sortieClaude + '.err')
        Patienter $p
        foreach ($f in $sortieClaude, ($sortieClaude + '.err')) {
            Get-Content -LiteralPath $f -Encoding UTF8 -ErrorAction SilentlyContinue | ForEach-Object { Journal "claude | $_" }
        }
        if (-not (Test-Path -LiteralPath $CLAUDE_EXE)) {
            Attention "Claude Code n'a pas pu être installé. Jarvis fonctionnera avec les commandes immédiates. Tu pourras réessayer en relançant ce fichier (« Ajouter Claude »)."
            return
        }
        Noter 'ClaudeInstalle'
        Bon "Claude Code installé."
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
    $ErrorActionPreference = 'Continue'
    if ($FEN) {
        [void][Windows.Forms.MessageBox]::Show($FEN.Form, ("Dernière étape : la connexion à ton compte Claude.`n`n" +
            "1. Clique sur OK : ton navigateur s'ouvre sur la page de connexion de Claude (une petite fenêtre noire " +
            "de Claude s'ouvre aussi : laisse-la, elle se fermera toute seule).`n" +
            "2. Connecte-toi au compte de ton abonnement, puis accepte l'autorisation.`n" +
            "3. Reviens ici : la suite se fait toute seule."), 'Installer Jarvis', 'OK', 'Information')
        try { $p = Start-Process -FilePath $CLAUDE_EXE -ArgumentList 'auth','login','--claudeai' -PassThru; Patienter $p }
        catch { Journal "Connexion à Claude : $($_.Exception.Message)" }
    } else {
        Read-Host "  Appuie sur Entrée pour commencer" | Out-Null
        try { & $CLAUDE_EXE auth login --claudeai } catch { Journal "Connexion à Claude : $($_.Exception.Message)" }
    }
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
        $limite = (Get-Date).AddSeconds($delai)
        while (-not $p.WaitForExit(200) -and (Get-Date) -lt $limite) { Pomper }
        if (-not $p.HasExited) { try { $p.Kill() } catch {}; Journal "Essai trop long : $instructions"; return $null }
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
    $code = "import ctypes, os, sys, time`nk = ctypes.windll.kernel32`nk.SetErrorMode(k.GetErrorMode() | 0x8001)`nos.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'`nsys.path.insert(0, os.getcwd())`nfor nom in ['" + ($modules -join "','") + "']:`n" +
            "    debut = time.time()`n    try:`n        __import__(nom)`n        print('OK', nom, round(time.time() - debut, 1), flush=True)`n" +
            "    except BaseException as e:`n        fichier = getattr(e, 'path', None) or ''`n        t = e.__traceback__`n        while t is not None and t.tb_next is not None:`n            t = t.tb_next`n        if not fichier and t is not None:`n            for v in list(t.tb_frame.f_locals.values()):`n                if isinstance(v, str) and v.lower().endswith(('.dll', '.pyd')): fichier = v`n        print('ECHEC', nom, type(e).__name__, str(e).replace(chr(10), ' ')[:300], fichier, flush=True)`n"
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
            Pomper
            # Seules les lignes « OK ... » ou « ECHEC ... » comptent (certains modules écrivent leur propre message)
            $lignes = @(Get-Content -LiteralPath $sortie -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -match '^(OK|ECHEC) ' })
            if ($lignes.Count -ne $vus) {
                $vus = $lignes.Count
                Write-Host ("`r  Modules vérifiés : {0} sur {1}..." -f $vus, $modules.Count) -NoNewline
                if ($FEN) { try { $FEN.Detail.Text = ("Vérification : {0} modules sur {1}..." -f $vus, $modules.Count) } catch {} }
            }
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
    if ($whisper.Count) {
        if (($whisper -join ' ') -match '4551|contr.le d.application|application control') {
            Attention "Reconnaissance précise (Whisper) indisponible : Windows (Contrôle intelligent des applications) bloque un de ses fichiers."
            Attention "Jarvis utilisera la reconnaissance simple : les commandes courantes (heure, météo, minuteur) marchent, les phrases libres seront moins bien comprises."
        } else { Attention "Reconnaissance précise (Whisper) indisponible : il manque sans doute les composants Microsoft Visual C++. Jarvis utilisera la reconnaissance simple." }
    }
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
    if (Test-Path -LiteralPath (Join-Path $dossier 'requirements-ps5.txt')) {
        if (Essai-Python $env_py $dossier "import jarvis_ps5; jarvis_ps5.preparer_netifaces(); import pyremoteplay, pyremoteplay.profile, pyremoteplay.ddp; print('ok')" 120) {
            Bon "Pilotage de la PlayStation 5 disponible (à relier une fois : « Jarvis, relie la PS5 »)."
        } else { Attention "Pilotage de la PlayStation 5 indisponible : Jarvis dira seulement si elle est allumée." }
    }
    $micro = Essai-Python $env_py $dossier "import sounddevice as sd; n = sd.query_devices(kind='input')['name']; l = [d['name'] for d in sd.query_devices() if d['max_input_channels'] > 0 and len(d['name']) > len(n) and d['name'].startswith(n)]; print(max(l, key=len) if l else n)" 60
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
function Autoriser-Tablettes {
    # Ouvre au pare-feu de Windows le port de Jarvis, pour les tablettes du réseau de la maison seulement.
    $nom = 'Jarvis - tablettes'
    try { & netsh.exe advfirewall firewall show rule name="$nom" | Out-Null } catch {}
    if ($LASTEXITCODE -eq 0) { return }
    if ($AUTO) { return }                          # mise à jour automatique : personne pour répondre à Windows
    Titre "Tablettes"
    Dire "  Pour que les tablettes de la maison puissent joindre Jarvis, Windows va demander une autorisation : clique sur le bouton « Oui » (Entrée seule répondrait « Non »)." 'Green' $true
    $regle = 'advfirewall firewall add rule name="' + $nom + '" dir=in action=allow protocol=TCP localport=47826 ' +
             'remoteip=LocalSubnet,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16 profile=any'
    try {
        $p = Start-Process -FilePath netsh.exe -ArgumentList $regle -Verb RunAs -WindowStyle Hidden -Wait -PassThru
        if ($p.ExitCode -eq 0) { Bon "Pare-feu : les tablettes de la maison peuvent joindre Jarvis." }
        else { Attention "Le pare-feu n'a pas été réglé. Plus tard, dis « Jarvis, autorise les tablettes »." }
    } catch {
        Attention "Autorisation refusée : les tablettes ne pourront pas joindre Jarvis. Plus tard, dis « Jarvis, autorise les tablettes »."
    }
}

function Installer($dossierExistant) {
    $maj = [bool]$dossierExistant
    Titre $(if ($maj) { "Mise à jour de Jarvis" } else { "Installation de Jarvis" })

    # 1. Le PC convient-il ?
    $os = [Environment]::OSVersion.Version
    if (-not [Environment]::Is64BitOperatingSystem) { Echec "Jarvis demande un Windows 64 bits." }
    if ($os.Build -lt 22000) { Attention "Jarvis est prévu pour Windows 11. Sur ce Windows, certaines fonctions peuvent ne pas marcher." }
    if (-not (Get-Command curl.exe -ErrorAction SilentlyContinue)) { Echec "L'outil de téléchargement de Windows (curl) est introuvable." }
    Controle-Applications
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
        $prenom = ''; $ville = ''; $codePostal = ''; $voix = ''; $vous = ''; $auDemarrage = Test-Path -LiteralPath (Chemins-Raccourcis).Demarrage
    } else {
        $gardesVus = Fichiers-Gardes
        if ((Fenetre-Possible) -and -not (Fenetre-Questions $gardesVus)) { Dire "  Installation annulée : rien n'a été installé."; return }
        Dire "  Bienvenue. Trois petites questions (ton prénom, ta ville, et Claude), puis l'installation se fait toute seule."
        Dire ''
        # Fichiers personnels gardés lors d'une désinstallation (dossier ou copie compressée sur le Bureau)
        $gardes = Fichiers-Gardes
        $reprendre = $false
        if ($gardes) {
            Dire "  Des fichiers personnels d'une ancienne installation de Jarvis ont été trouvés :" 'White'
            Dire "    $gardes"
            $reprendre = OuiNon "Les reprendre (tes réglages, les profils et les voix, la mémoire, les rappels, les notes) ?" (-not $AUTO) 'JARVIS_REPRENDRE'
            Dire ''
        }
        $prenom = ''
        if (-not $reprendre) { $prenom = Demander "Ton prénom (Jarvis t'appellera ainsi), puis Entrée" 'Alex' 'JARVIS_PRENOM' }
        # La ville, pour la météo (sinon Paris). Le dossier et le démarrage avec Windows restent ceux par défaut.
        $ville = Demander "Ta ville, pour la météo (ou Entrée seule pour la donner plus tard)" '' 'JARVIS_VILLE'
        $codePostal = Demander "Ton code postal, pour trouver la bonne ville (ou Entrée seule)" '' 'JARVIS_CP'
        $voix = Demander "La voix de Jarvis : tape h (voix d'homme) ou f (voix de femme), ou Entrée seule pour choisir plus tard" '' 'JARVIS_VOIX'
        $vous = Demander "Jarvis te tutoie ou te vouvoie ? Tape t (tutoie) ou v (vouvoie), ou Entrée seule pour choisir plus tard" '' 'JARVIS_VOUS'
        $dossier = if ($env:JARVIS_DOSSIER) { $env:JARVIS_DOSSIER } else { 'C:\Jarvis' }
        $dossier = [IO.Path]::GetFullPath($dossier.Trim('"'))
        if (-not $env:JARVIS_DOSSIER -and (Test-Path -LiteralPath $dossier) -and (Get-ChildItem -LiteralPath $dossier -Force | Select-Object -First 1) -and -not (Test-Path -LiteralPath (Join-Path $dossier 'jarvis_gardien.py'))) {
            $dossier = Join-Path $env:LOCALAPPDATA 'Jarvis'        # C:\Jarvis est déjà pris par autre chose
        }
        $auDemarrage = $env:JARVIS_DEMARRAGE -notin 'n','non','0'
        Dire ''
        Dire "  Sans abonnement, Jarvis répond seul à ses commandes immédiates : l'heure, la météo, les minuteurs et les rappels,"
        Dire "  la musique, les fenêtres et les applications du PC."
        Dire "  Avec un abonnement Claude (Pro ou supérieur), il fait beaucoup plus : de vraies conversations, des réponses à"
        Dire "  toutes tes questions, et tout ce qui demande de réfléchir, de rédiger ou de chercher sur Internet."
        Dire "  Sans cet abonnement, tu auras donc accès à moins de fonctionnalités de Jarvis." 'White'
        Dire "  Tu pourras le relier plus tard, quand tu voudras, en relançant cet installateur."
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
        if (-not (VC-Present)) { Dire "  - Les composants Microsoft Visual C++ (depuis microsoft.com) : Windows demandera ton autorisation, clique sur le bouton « Oui »" 'Green' $true }
        Dire "  - Les modules Python de Jarvis, dans son propre dossier (environ 600 Mo), y compris ceux de la PlayStation 5"
        Dire "  - Le modèle de reconnaissance vocale Vosk (environ 40 Mo) et celui qui reconnaît qui parle (environ 13 Mo)"
        if ($avecClaude -and -not (Test-Path -LiteralPath $CLAUDE_EXE)) { Dire "  - Claude Code (depuis claude.ai, environ 370 Mo)" }
        Dire "  - Un raccourci « Jarvis » sur le Bureau$(if ($auDemarrage) { ' et au démarrage de Windows' })"
        Dire "  Au premier lancement, Jarvis téléchargera aussi son second modèle vocal (Whisper, environ 150 Mo)."
        Dire ''
        if (-not (OuiNon "Lancer l'installation ?" $true 'JARVIS_OK')) { Dire "  Installation annulée : rien n'a été installé."; return }
    }
    New-Item -ItemType Directory -Path $TEMP -Force | Out-Null
    Fenetre-Progression $(if ($maj) { 'Mise à jour de Jarvis' } else { 'Installation de Jarvis' })
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
        Noter 'PythonInstalle'
        Bon "Python $PYTHON_VER installé."
    }

    Installer-VC

    # 4 à 7. Jarvis, ses modules, le modèle vocal, les réglages
    Titre "Jarvis"
    Copier-Programme $dossier
    $env_py = Installer-Modules $dossier $python
    Installer-Vosk $dossier
    Installer-Vosk-Voix $dossier
    if (-not $maj -and $reprendre) {
        Reprendre-Fichiers $gardes $dossier
        if (-not (Test-Path -LiteralPath (Join-Path $dossier 'config.json'))) { $prenom = Demander "Ton prénom (Jarvis t'appellera ainsi), puis Entrée" 'Alex' 'JARVIS_PRENOM' }
    }
    Ecrire-Reglages $dossier $prenom $ville $codePostal $voix $vous
    if (-not $maj -and $REPONSES.ContainsKey('JARVIS_RAPPORT')) { Ecrire-Rapport $dossier $REPONSES['JARVIS_RAPPORT'] }

    # 8. Claude
    if ($avecClaude -and -not $maj) { Titre "Claude"; Installer-Claude }

    # 9. Raccourcis et repère d'installation
    Titre "Raccourcis"
    $pythonw = Join-Path $dossier 'python-env\Scripts\pythonw.exe'
    $liens = Chemins-Raccourcis
    Raccourci (Join-Path $dossier 'Jarvis.lnk') $pythonw $dossier
    Raccourci $liens.Bureau $pythonw $dossier
    if ($auDemarrage) { Raccourci $liens.Demarrage $pythonw $dossier }
    if (-not (Test-Path -Path $CLE)) { New-Item -Path $CLE -Force | Out-Null }     # sans effacer ce qui y est déjà noté
    Set-ItemProperty -Path $CLE -Name Dossier -Value $dossier
    Set-ItemProperty -Path $CLE -Name Version -Value (Version-Installee $dossier)
    $fichierInstallateur = Ranger-Installateur $dossier
    $nomInstallateur = if ($fichierInstallateur -like '*.exe') { "« Installer-Jarvis » (l'icône du réacteur)" } else { "« Installer-Jarvis.bat »" }
    Bon "Raccourci « Jarvis » créé sur le Bureau$(if ($auDemarrage) { ' et au démarrage de Windows' })."

    # 9 bis. Pare-feu : une seule autorisation de Windows, pour les tablettes de la maison
    Autoriser-Tablettes

    # 10. Essais, puis lancement
    Verifier $dossier $env_py
    Titre $(if ($maj) { "Mise à jour terminée" } else { "Installation terminée" })
    Dire "  Jarvis $(Version-Installee $dossier) est installé dans $dossier." 'White'
    if (-not (Test-Path -LiteralPath $CLAUDE_EXE)) {
        Dire ''
        Dire "  Claude n'est pas installé : Jarvis répond aux commandes immédiates (heure, météo, minuteurs, fenêtres, musique)." 'White'
        Dire "  Pour ajouter Claude plus tard, et lui poser toutes tes questions :"
        Dire "    1. Prends un abonnement Claude (Pro ou supérieur) sur https://claude.ai"
        Dire "    2. Dis « Jarvis, ouvre les réglages », va dans l'onglet « Assistants », clique sur « Installer Claude »,"
        Dire "       puis sur « Connecter mon compte »."
        Dire "    Autre façon : double-clique sur le fichier $nomInstallateur (une copie est rangée dans $dossier)"
        Dire "    et choisis « Ajouter Claude »."
        Dire ''
    } elseif (-not $AUTO -and -not (Claude-Connecte)) {
        Dire ''
        Dire "  Claude est installé mais pas connecté à ton compte : dis « Jarvis, ouvre les réglages », va dans l'onglet" 'White'
        Dire "  « Assistants » et clique sur « Connecter mon compte ». Autre façon : double-clique sur $nomInstallateur" 'White'
        Dire "  (une copie est rangée dans $dossier) et choisis « Connecter Claude à mon compte »." 'White'
        Dire ''
    }
    Dire ''
    Dire '  ------------------------------------------------------------' 'Cyan'
    Dire '   À RETENIR' 'Cyan'
    Dire '  ------------------------------------------------------------' 'Cyan'
    Dire "   Lui parler : dis « Jarvis », attends le bip, puis ta demande. Exemple : « Jarvis, quelle heure est-il ? »" 'White'
    if (-not (Test-Path -LiteralPath (Join-Path $dossier 'ville.txt'))) {
        Dire "   La météo de chez toi : dis-lui une fois « Jarvis, ma ville est Toulouse » (avec le nom de ta ville)."
    }
    Dire "   Ses réglages : dis « Jarvis, ouvre les réglages ». Tu y choisis aussi s'il se lance avec Windows (onglet Système)."
    Dire "   L'arrêter : clic droit sur le réacteur."
    Dire "   Le mettre à jour : dis « Jarvis, mets-toi à jour », ou relance ce fichier."
    Dire "   Le désinstaller : dans ses réglages, onglet « À propos », bouton « Désinstaller Jarvis » (ou relance ce fichier)." 'White'
    Dire "   Tout ce qui a été installé pour lui est alors retiré, après ta confirmation, et Windows revient comme avant."
    Dire "   Une copie de cet installateur est rangée dans $dossier (touche Windows + R, tape $dossier, puis Entrée)."
    Dire '  ------------------------------------------------------------' 'Cyan'
    if (-not $env:JARVIS_SANS_LANCEMENT) {
        Start-Process -FilePath (Join-Path $dossier 'Jarvis.lnk')
        Dire "  Jarvis démarre (le premier lancement prend une minute ou deux : il prépare sa reconnaissance vocale)." 'Green'
    }
    try { Copy-Item -LiteralPath $JOURNAL -Destination (Join-Path $dossier 'installation.log') -Force } catch {}
    if ($FEN) {                             # la fenêtre attend : on lit « À RETENIR », puis Terminer
        Fenetre-Fin $(if ($maj) { 'Mise à jour terminée !' } else { 'Installation terminée !' })
        $script:FERMER = $true
    } elseif (-not $AUTO) {                 # la console attend aussi, pour qu'on puisse lire « À RETENIR »
        Dire ''
        Read-Host "  Appuie sur Entrée pour fermer cette fenêtre" | Out-Null
        $script:FERMER = $true
    }
}

function Desinstaller($dossier) {
    Titre "Désinstallation de Jarvis"
    Dire "  Jarvis est installé dans $dossier."
    # La désinstallation complète se fait dans la fenêtre de Jarvis (jarvis_desinstaller.py) : elle demande quoi faire
    # des fichiers personnels, montre tout ce qui sera retiré (Python et Claude Code compris, s'ils ont été installés
    # pour Jarvis) et attend le mot « confirmer ». Sans elle (ancienne version, essais automatiques) : méthode simple.
    $fenetre = Join-Path $dossier 'jarvis_desinstaller.py'
    $pythonw = Join-Path $dossier 'python-env\Scripts\pythonw.exe'
    if (-not $AUTO -and (Test-Path -LiteralPath $fenetre) -and (Test-Path -LiteralPath $pythonw)) {
        Dire "  La fenêtre de désinstallation de Jarvis s'ouvre : suis ses indications." 'White'
        Dire "  Elle te demande si tu veux garder tes fichiers personnels, puis une dernière confirmation."
        Dire "  Rien n'est supprimé avant cette confirmation. Cette fenêtre noire va se fermer toute seule."
        Start-Process -FilePath $pythonw -ArgumentList ('"' + $fenetre + '"') -WorkingDirectory $env:TEMP
        Start-Sleep -Seconds 6
        $script:FERMER = $true
        return
    }
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
        if (Fenetre-Possible) { $script:REPONSES['JARVIS_ACTION'] = Fenetre-Choix (Version-Installee $existant) $existant $sansClaude $claudeInstalle }
        $choix = Demander "Ton choix, puis Entrée" '0' 'JARVIS_ACTION'
        if ($choix -eq '1') { Installer $existant }
        elseif ($choix -eq '2') { Desinstaller $existant }
        elseif ($choix -eq '3' -and $sansClaude) {
            Fenetre-Progression 'Ajout de Claude'
            Ajouter-Claude $existant
            if ($FEN) { Fenetre-Fin 'Terminé !'; $script:FERMER = $true }
        }
        else { Dire "  Rien n'a été modifié." }
    }
} catch {
    $code = 1
    Write-Host ''
    Write-Host ("  ERREUR : " + $_.Exception.Message) -ForegroundColor Red
    Journal ("ERREUR : " + $_.Exception.Message + " | " + $_.ScriptStackTrace)
    Write-Host "  L'installation s'est arrêtée. Tu peux relancer ce fichier : il reprendra sans rien casser." -ForegroundColor Yellow
    Write-Host "  Journal : $JOURNAL" -ForegroundColor DarkGray
    Fenetre-Erreur $_.Exception.Message
} finally {
    try { if (Test-Path -LiteralPath $TEMP) { Remove-Item -LiteralPath $TEMP -Recurse -Force -ErrorAction SilentlyContinue } } catch {}
}
Write-Host ''
if ($FERMER -and -not $code) { exit 99 }      # 99 : la fenêtre se ferme sans « Appuyez sur une touche »
exit $code
