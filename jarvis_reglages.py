"""
JARVIS - réglages à la voix (de Jarvis et du PC).

  - le mode nuit : « active le mode nuit », « désactive le mode nuit », « parle normalement ».
    En mode nuit, Jarvis répond par écrit au-dessus du réacteur, sans voix ni bip ; les rappels et le
    réveil sonnent quand même. Il s'active tout seul aux heures choisies dans config.json (22 h à 7 h
    par défaut) ; ce qui est dit à la voix vaut jusqu'au prochain changement d'horaire ;
  - la voix : « prends une voix de femme » (Denise), « reprends la voix d'Henri » ;
  - la vitesse : « parle plus vite », « parle plus lentement », « parle à vitesse normale » ;
  - la luminosité : « monte la luminosité », « baisse la luminosité », « luminosité à 60 »,
    « luminosité au maximum » (écran d'un portable, et écrans externes qui l'acceptent par DDC/CI) ;
  - le Bluetooth : « active le Bluetooth », « coupe le Bluetooth », « le Bluetooth est activé ? ».
Chaque fonction « commande_... » renvoie la phrase à dire, ou None si la demande ne la concerne pas.
"""

import ctypes
import ctypes.wintypes
import re
import subprocess

import jarvis_voix

SANS_FENETRE = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PAS_LUMINOSITE = 15
PAS_VITESSE = 10


def _sans_jarvis(t):
    return re.sub(r"^\W*(?:jarvis\W+)?", "", t.replace("’", "'")).strip(" .!?")


# ---------- Mode nuit ----------

# Le mode nuit mal entendu (relevé dans les enregistrements) : « des actives le mode nuit »,
# « le mot de nuit », « le mois de nuit », « le moins nuit », « modnues », « active le mot de mu »...
_NUIT_MAL_ENTENDU = re.compile(r"\bmo(?:t|is|ins|de)?(?: de)? (?:nuit|nui|nuits|nu|nue|nues|mu)\b|\bmodnu\w*\b")
_DESACTIVE_MAL_ENTENDU = re.compile(r"\b(?:des|dés|d'est) ?actives?\b|\bdéactive\b")


def commande_mode_nuit(t):
    t = _sans_jarvis(t)
    t = _DESACTIVE_MAL_ENTENDU.sub("désactive", t)
    t = re.sub(r"\bh[âa]tive\b", "active", t)
    if re.search(r"\b(?:active|désactive|desactive|mets|passe|enlève|enleve|coupe|arrête|arrete|quitte|sors)\b", t):
        t = _NUIT_MAL_ENTENDU.sub("mode nuit", t)
    if not re.search(r"\bmode (?:nuit|silencieux|silence|jour)\b|\bparle normalement\b|\btu peux (?:re)?parler\b|"
                     r"\bne parle plus\b|\bchuchote\b", t):
        return None
    # une question (« est-ce que le mode nuit est activé ? », écrit parfois « … est active ») ne change jamais rien
    if (re.search(r"\b(?:est-ce que|est-ce qu'|es-tu|tu es|t'es|c'est)\b.*\bmode nuit\b|\bmode nuit\b.*\b(?:activé|actif)\s*$", t)
            and not re.search(r"\b(active|désactive|desactive|passe|mets|enlève|enleve|coupe|arrête|arrete)\b", t)
                 and not re.search(r"\b(?:peux|pourrais|veux|voudrais)\b", t)) \
            or (re.search(r"\bmode nuit (?:est|il est)\s+(?:activ[ée]e?|actif|allumé|en marche|mis)\b", t)
                and not re.search(r"\b(?:peux|pourrais|veux|voudrais|faut)\b", t)):
        return "Le mode nuit est activé : je réponds par écrit." if jarvis_voix.mode_nuit() else \
            "Le mode nuit n'est pas activé."
    arreter = re.search(r"\b(désactive|desactive|enlève|enleve|retire|arrête|arrete|coupe|quitte|sors du|stop|fin du|"
                        r"sans)\b.*\bmode (?:nuit|silencieux|silence)\b|\bparle normalement\b|\btu peux (?:re)?parler\b|"
                        r"\bmode jour\b", t)
    if arreter:
        jarvis_voix.forcer_nuit(False)
        return "Mode nuit désactivé : je parle de nouveau."
    if not re.search(r"\b(?:active|mets|passe|lance|démarre|demarre|chuchote|ne parle plus|silencieux|silence)\b"
                     r"|\ben mode (?:nuit|silencieux|silence)\b", t):
        # « le mode nuit » tout seul (souvent un mot mal entendu) : on demande plutôt que deviner
        return "Tu veux que j'active ou que je désactive le mode nuit ?"
    jarvis_voix.forcer_nuit(True)
    return "Mode nuit activé : je te réponds par écrit, au-dessus du réacteur. Les rappels sonnent quand même."


# ---------- Voix et vitesse ----------


# En mode nuit, quelqu'un qui demande à Jarvis de parler (« parle un peu », « pourquoi tu ne parles plus »,
# « rallume le micro ») ne sait pas qu'il est en mode nuit : on lui dit pourquoi et comment en sortir.
_POURQUOI_SILENCE = re.compile(
    r"\bparle (?:un peu|un coup|à voix haute|a voix haute|moi)\b"
    r"|\bparle(?:s)? (?:pas|plus)\b(?! (?:vite|lentement|fort|doucement|bas|haut))"
    r"|\bpourquoi (?:tu|vous|il) (?:ne |n')?(?:parle|réponds|reponds|répond|repond|dis)"
    r"|\bpourquoi\b.*\b(?:par écrit|par ecrit|en écrit|en ecrit)\b"
    r"|\b(?:rallume|ralume|ralumer|rallumer|réactive|reactive|remets|remet)\b.*\bmicro\b"
    r"|\bje (?:ne )?t'entends (?:pas|plus)\b"
    r"|\b(?:réponds|reponds|répondre|repondre)\b.*\b(?:voix|oral)\b")


def commande_pourquoi_silence(t):
    """En mode nuit seulement : explique pourquoi Jarvis répond par écrit et comment le désactiver."""
    if not jarvis_voix.mode_nuit():
        return None
    t = _sans_jarvis(t)
    if not _POURQUOI_SILENCE.search(t):
        return None
    texte = "Je suis en mode nuit, donc je réponds par écrit. Dis « désactive le mode nuit » pour que je reparle."
    if jarvis_voix.jarvis_config.HEURES_NUIT:
        texte += (" Les horaires de nuit me remettent en silence tout seuls : pour les enlever, "
                  "règle « Mode nuit automatique » dans les réglages, onglet Apparence.")
    return texte


def commande_voix(t):
    t = _sans_jarvis(t)
    # « parle » est souvent entendu « par le » ou « par là » (« par le plus vite », « par là, à vitesse normale »)
    t = re.sub(r"^par (?:le|là|la)\b[\s,]*(?:à |a )?(?=plus |moins |vitesse |lentement|normalement)", "parle ", t)
    if re.search(r"\b(?:voix (?:de |d')?(?:femme|féminine|feminine|fille)|voix de denise|denise|"
                 r"(?:change|changer|change de|autre) voix)\b", t) and re.search(r"\b(voix|denise)\b", t) \
            and not re.search(r"\b(henri|homme|masculine)\b", t):
        if re.search(r"\b(change|changer|autre)\b", t) and not re.search(r"\b(femme|féminine|feminine|fille|denise)\b", t):
            voix = "henri" if jarvis_voix.VOIX == jarvis_voix.VOIXS["denise"] else "denise"
        else:
            voix = "denise"
        jarvis_voix.regler_voix(voix=voix)
        return "Voilà ma nouvelle voix." if voix == "denise" else "Je reprends la voix d'Henri."
    if re.search(r"\b(?:voix (?:d'|de )?(?:homme|masculine|garçon|garcon)|voix d'henri|voix de henri|"
                 r"reprends (?:ta|la) voix|ta voix normale|ancienne voix|henri)\b", t) and re.search(r"\b(voix|henri)\b", t):
        jarvis_voix.regler_voix(voix="henri")
        return "Je reprends la voix d'Henri."
    if not re.search(r"\b(?:parle|parles|parler|lis|cause|débit|debit|voix)\b", t):
        return None
    actuelle = int(jarvis_voix.VITESSE.rstrip("%"))
    if re.search(r"\b(?:vitesse normale|normalement|vitesse habituelle|comme avant)\b", t):
        jarvis_voix.regler_voix(vitesse=jarvis_voix.VITESSE_NORMALE)
        return "Je reprends ma vitesse normale."
    if re.search(r"\b(?:plus vite|plus rapidement|accélère|accelere|moins lentement)\b", t):
        if actuelle >= 50:
            return "Je parle déjà le plus vite possible."
        jarvis_voix.regler_voix(vitesse=actuelle + PAS_VITESSE)
        return "D'accord, je parle plus vite."
    if re.search(r"\b(?:plus lentement|moins vite|ralentis|plus doucement|lentement)\b", t):
        if actuelle <= -30:
            return "Je parle déjà le plus lentement possible."
        jarvis_voix.regler_voix(vitesse=actuelle - PAS_VITESSE)
        return "D'accord, je parle plus lentement."
    return None


# ---------- Luminosité ----------

class _ECRAN_PHYSIQUE(ctypes.Structure):
    _fields_ = [("poignee", ctypes.wintypes.HANDLE), ("description", ctypes.c_wchar * 128)]


def _ecrans_ddc():
    """Écrans réglables par DDC/CI (souvent les écrans externes) : liste de (poignée, min, actuel, max)."""
    dxva2 = ctypes.windll.dxva2
    user32 = ctypes.windll.user32
    # Types précisés : sur Windows 64 bits, une poignée passée sans type peut être tronquée
    dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.wintypes.HMONITOR, ctypes.POINTER(ctypes.wintypes.DWORD)]
    dxva2.GetPhysicalMonitorsFromHMONITOR.argtypes = [ctypes.wintypes.HMONITOR, ctypes.wintypes.DWORD, ctypes.c_void_p]
    for f in (dxva2.GetMonitorBrightness, dxva2.SetMonitorBrightness, dxva2.DestroyPhysicalMonitor):
        f.argtypes = None
    dxva2.DestroyPhysicalMonitor.argtypes = [ctypes.wintypes.HANDLE]
    dxva2.SetMonitorBrightness.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
    dxva2.GetMonitorBrightness.argtypes = [ctypes.wintypes.HANDLE] + [ctypes.POINTER(ctypes.wintypes.DWORD)] * 3
    moniteurs = []
    rappel = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.wintypes.HMONITOR, ctypes.wintypes.HDC,
                                ctypes.POINTER(ctypes.wintypes.RECT), ctypes.wintypes.LPARAM)
    user32.EnumDisplayMonitors(None, None, rappel(lambda h, dc, r, p: moniteurs.append(h) or 1), 0)
    ecrans = []
    for h in moniteurs:
        nombre = ctypes.wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(h, ctypes.byref(nombre)) or not nombre.value:
            continue
        tableau = (_ECRAN_PHYSIQUE * nombre.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(h, nombre.value, tableau):
            continue
        for e in tableau:
            mini, actuel, maxi = ctypes.wintypes.DWORD(), ctypes.wintypes.DWORD(), ctypes.wintypes.DWORD()
            if dxva2.GetMonitorBrightness(e.poignee, ctypes.byref(mini), ctypes.byref(actuel), ctypes.byref(maxi)):
                ecrans.append((e.poignee, mini.value, actuel.value, maxi.value))
            else:
                dxva2.DestroyPhysicalMonitor(e.poignee)
    return ecrans


def _powershell(script, delai=15):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, timeout=delai, creationflags=SANS_FENETRE)
    return r.stdout.strip()


def _luminosite_portable(niveau=None):
    """Luminosité de l'écran intégré d'un portable (par WMI) : renvoie la valeur actuelle, ou None s'il n'y en a pas."""
    try:
        if niveau is None:
            sortie = _powershell("(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness "
                                 "-ErrorAction Stop | Select-Object -First 1).CurrentBrightness")
        else:
            sortie = _powershell("Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightnessMethods "
                                 f"-ErrorAction Stop | ForEach-Object {{ Invoke-CimMethod -InputObject $_ "
                                 f"-MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness=[byte]{niveau}}} "
                                 f"| Out-Null }}; {niveau}")
        return int(sortie) if sortie.strip().isdigit() else None
    except Exception:
        return None


def luminosite():
    """(valeur actuelle en pour cent, nombre d'écrans réglables)."""
    valeurs = []
    portable = _luminosite_portable()
    if portable is not None:
        valeurs.append(portable)
    ecrans = []
    try:
        ecrans = _ecrans_ddc()
        for _, mini, actuel, maxi in ecrans:
            valeurs.append(round(100 * (actuel - mini) / max(1, maxi - mini)))
    finally:
        for poignee, *_ in ecrans:
            ctypes.windll.dxva2.DestroyPhysicalMonitor(poignee)
    return (round(sum(valeurs) / len(valeurs)) if valeurs else None), len(valeurs)


def regler_luminosite(pour_cent):
    """Règle tous les écrans qui l'acceptent ; renvoie le nombre d'écrans réglés."""
    pour_cent = max(0, min(100, int(pour_cent)))
    regles = 0
    if _luminosite_portable() is not None and _luminosite_portable(pour_cent) is not None:
        regles += 1
    ecrans = []
    try:
        ecrans = _ecrans_ddc()
        for poignee, mini, _, maxi in ecrans:
            if ctypes.windll.dxva2.SetMonitorBrightness(poignee, mini + round((maxi - mini) * pour_cent / 100)):
                regles += 1
    finally:
        for poignee, *_ in ecrans:
            ctypes.windll.dxva2.DestroyPhysicalMonitor(poignee)
    return regles


def commande_luminosite(t):
    t = _sans_jarvis(t)
    if not re.search(r"\b(?:luminosité|luminosite|lumière de l'écran|lumiere de l'ecran|écran plus clair|"
                     r"écran plus sombre|ecran plus clair|ecran plus sombre)\b", t):
        return None
    actuelle, nombre = luminosite()
    if actuelle is None:
        return "Je ne peux pas régler la luminosité de cet écran : il ne l'accepte pas depuis Windows."
    m = re.search(r"\b(\d{1,3})\s*(?:%|pour ?cent)?\s*$", t)
    if re.search(r"\b(?:maximum|max|à fond|a fond|au plus fort)\b", t):
        cible = 100
    elif re.search(r"\b(?:minimum|min|au plus faible|au plus bas)\b", t):
        cible = 10
    elif m and re.search(r"\b(?:à|a|sur|mets|règle|regle)\b", t):
        cible = int(m.group(1))
    elif re.search(r"\b(?:monte|augmente|plus fort|plus clair|plus lumineux|éclaircis|eclaircis)\b", t):
        cible = actuelle + PAS_LUMINOSITE
    elif re.search(r"\b(?:baisse|diminue|moins fort|plus sombre|moins lumineux|assombris)\b", t):
        cible = actuelle - PAS_LUMINOSITE
    elif re.search(r"\b(?:quelle|combien|niveau)\b", t):
        return f"La luminosité est à {actuelle} pour cent."
    else:
        return None
    cible = max(5, min(100, cible))
    if not regler_luminosite(cible):
        return "Je n'ai pas réussi à régler la luminosité."
    return f"Luminosité à {cible} pour cent."


# ---------- Bluetooth ----------

_RADIO = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$methode = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Attendre($op, $type) { $t = $methode.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus, Windows.System.Devices, ContentType = WindowsRuntime] | Out-Null
Attendre ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Attendre ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | Where-Object { $_.Kind -eq 'Bluetooth' } | Select-Object -First 1
if (-not $bt) { 'AUCUN'; return }
if ('ETAT' -ne 'LIRE') { Attendre ($bt.SetStateAsync('ETAT')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null; Start-Sleep -Milliseconds 400 }
$bt.State.ToString()
"""


def bluetooth(etat=None):
    """Lit (etat=None) ou règle (« On » / « Off ») le Bluetooth. Renvoie « On », « Off », « AUCUN » ou ""."""
    return _powershell(_RADIO.replace("ETAT", etat or "LIRE"), delai=20)


def commande_bluetooth(t):
    t = _sans_jarvis(t)
    if not re.search(r"\b(?:bluetooth|blue tooth|bloutouze|blutooth|bleu ?tout)\b", t):
        return None
    if re.search(r"\b(?:éteins|eteins|coupe|désactive|desactive|arrête|arrete|stoppe|enlève|enleve)\b", t):
        etat, voulu = "Off", "coupé"
    elif re.search(r"\b(?:allume|active|mets|lance|démarre|demarre|rallume|réactive|reactive)\b", t):
        etat, voulu = "On", "activé"
    else:
        etat, voulu = None, None
    try:
        resultat = bluetooth(etat)
    except Exception as erreur:
        print("Bluetooth :", erreur)
        return "Je n'arrive pas à régler le Bluetooth."
    if resultat == "AUCUN":
        return "Je ne trouve pas de Bluetooth sur ce PC."
    if etat is None:
        return "Le Bluetooth est activé." if resultat == "On" else "Le Bluetooth est coupé."
    if resultat != etat:
        return "Windows n'a pas accepté de changer le Bluetooth."
    return f"Bluetooth {voulu}."


def rapide(t):
    t = _sans_jarvis(t)
    return bool(re.search(r"\bmode nuit\b|\bbluetooth\b|\bluminosit", t))
