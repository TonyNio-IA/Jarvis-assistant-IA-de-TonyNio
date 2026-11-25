# -*- coding: utf-8 -*-
"""
JARVIS - l'onglet « Claude » des réglages : savoir où en est Claude sur ce PC, l'installer et connecter le compte.

Trois états : « absent » (Claude Code n'est pas installé), « deconnecte » (installé, mais pas relié à un compte
Claude) et « connecte ». Les actions reprennent exactement celles de l'installateur (« Ajouter Claude ») :
- installer : le programme officiel d'Anthropic (https://claude.ai/install.ps1), puis la note dans le registre
  pour que la désinstallation sache que c'est Jarvis qui l'a mis ;
- connecter : « claude auth login --claudeai » ouvre le navigateur sur la page de connexion de Claude.
Rien n'est envoyé nulle part par ce module, et aucun mot de passe ne passe par Jarvis : la connexion se fait
sur le site de Claude, dans le navigateur.
"""

import json
import os
import subprocess
import time

CLAUDE_EXE = os.path.expanduser(r"~\.local\bin\claude.exe")
CLE_REGISTRE = r"Software\Jarvis-TonyNio"          # la même clé que l'installateur et la désinstallation
ADRESSE_ABONNEMENT = "https://claude.ai"
DELAI_CONNEXION_S = 300                            # 5 minutes pour se connecter dans le navigateur
DELAI_INSTALLATION_S = 900
_SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def installe():
    return os.path.exists(CLAUDE_EXE)


def connecte(delai=25):
    """Vrai si Claude est relié à un compte (« claude auth status » répond en JSON ; rien n'est gardé ni affiché)."""
    if not installe():
        return False
    try:
        r = subprocess.run([CLAUDE_EXE, "auth", "status"], capture_output=True, text=True, timeout=delai,
                           creationflags=_SANS_FENETRE, encoding="utf-8", errors="replace")
        return bool(json.loads(r.stdout or "{}").get("loggedIn"))
    except Exception:
        return False


def etat():
    """« absent », « deconnecte » ou « connecte »."""
    if not installe():
        return "absent"
    return "connecte" if connecte() else "deconnecte"


def _noter_installation():
    """Retient dans le registre que Jarvis a installé Claude Code (la désinstallation le retirera d'office)."""
    try:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLE_REGISTRE) as cle:
            winreg.SetValueEx(cle, "ClaudeInstalle", 0, winreg.REG_SZ, "1")
    except Exception as erreur:
        print("Claude (note d'installation) :", erreur)


def installer():
    """Installe Claude Code avec le programme officiel. Renvoie (réussi, message simple). Dure plusieurs minutes."""
    if installe():
        return True, "Claude Code est déjà installé."
    commande = ('$ProgressPreference=\'SilentlyContinue\'; '
                '[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; '
                'irm https://claude.ai/install.ps1 | iex')
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", commande],
                           capture_output=True, text=True, timeout=DELAI_INSTALLATION_S,
                           creationflags=_SANS_FENETRE, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "L'installation a pris trop de temps. Vérifie ta connexion Internet puis réessaie."
    except Exception as erreur:
        return False, f"L'installation n'a pas pu démarrer ({erreur})."
    if not installe():
        fin = (r.stderr or r.stdout or "").strip().splitlines()
        detail = f" ({fin[-1][:120]})" if fin else ""
        return False, ("Claude Code n'a pas pu être installé" + detail + ". Vérifie ta connexion Internet "
                       "(ou ton antivirus) puis réessaie.")
    _noter_installation()
    return True, "Claude Code est installé."


def connecter(annuler=lambda: False):
    """Ouvre la page de connexion de Claude dans le navigateur et attend que le compte soit relié.
    Renvoie (réussi, message simple)."""
    if not installe():
        return False, "Claude Code n'est pas encore installé."
    try:
        p = subprocess.Popen([CLAUDE_EXE, "auth", "login", "--claudeai"], creationflags=_SANS_FENETRE,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as erreur:
        return False, f"La connexion n'a pas pu démarrer ({erreur})."
    debut = time.time()
    try:
        while time.time() - debut < DELAI_CONNEXION_S and not annuler():
            if p.poll() is not None:
                break
            time.sleep(1.0)
    finally:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception:
                pass
    if connecte():
        return True, "Claude est relié à ton compte."
    return False, ("La connexion n'a pas abouti. Il faut un abonnement Claude (Pro ou supérieur) : "
                   "tu peux en prendre un sur claude.ai, puis réessayer.")


def deconnecter():
    """Délie le compte Claude de ce PC (« claude auth logout »). Renvoie vrai si c'est fait."""
    if not installe():
        return True
    try:
        subprocess.run([CLAUDE_EXE, "auth", "logout"], capture_output=True, timeout=30, creationflags=_SANS_FENETRE)
    except Exception:
        pass
    return not connecte()


TEXTES = {
    "absent": ("Claude n'est pas installé sur ce PC.",
               "Sans lui, Jarvis fait les commandes immédiates (heure, météo, minuteurs, applications, fenêtres, "
               "musique, mails). Avec Claude, il répond aussi à n'importe quelle question, résume une page et écrit "
               "des textes. Il faut un abonnement Claude (Pro ou supérieur) : prends-le sur claude.ai, puis clique "
               "sur « Installer Claude ». Tu préfères un autre assistant (Gemini, Mistral, ChatGPT…) ? Ouvre l'onglet « Assistants » (bêta)."),
    "deconnecte": ("Claude est installé, mais pas relié à ton compte.",
                   "Clique sur « Connecter mon compte » : ton navigateur s'ouvre sur la page de connexion de Claude. "
                   "Connecte-toi avec le compte de ton abonnement et accepte l'autorisation. Ton mot de passe ne "
                   "passe jamais par Jarvis."),
    "connecte": ("✓ Claude est relié à ton compte.",
                 "Tu peux poser n'importe quelle question à Jarvis, lui faire résumer une page ou écrire un texte."),
}
