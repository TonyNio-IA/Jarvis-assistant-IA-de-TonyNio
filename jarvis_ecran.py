"""
JARVIS - voir l'écran et le texte copié.

  « qu'est-ce qu'il y a à l'écran ? », « explique-moi cette erreur à l'écran », « lis l'écran »
      -> Jarvis photographie la fenêtre active (ou tout l'écran) et Claude regarde l'image.
  « résume ce que j'ai copié », « traduis le texte copié en anglais », « explique le texte sélectionné »
      -> le texte du presse-papiers est donné à Claude avec la demande.
  « corrige le texte copié » -> le texte corrigé est remis dans le presse-papiers : il suffit de coller.
  « lis ce que j'ai copié » -> Jarvis le lit à voix haute (sans Claude).

Les images sont enregistrées dans C:\\Jarvis\\ecran (jamais envoyé sur GitHub) et remplacées à chaque fois.
"""

import ctypes
import ctypes.wintypes
import math
import os
import re
import time

DOSSIER = r"C:\Jarvis\ecran"
COTE_MAX = 1568          # au-delà, l'image est réduite (Claude ne voit pas plus fin)
HAUTEUR_MORCEAU = 2000   # une fenêtre plus haute est découpée en plusieurs images, pour que le texte reste lisible
TEXTE_MAX = 8000         # nombre de caractères du presse-papiers donnés à Claude au maximum

# Accès à Windows propres à ce fichier : ses réglages ne touchent pas ceux des autres fichiers de Jarvis
user32, gdi32, kernel32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32"), ctypes.WinDLL("kernel32")
user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT)]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateCompatibleBitmap.restype = ctypes.c_void_p
gdi32.CreateCompatibleBitmap.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.GetClipboardData.restype = ctypes.c_void_p
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]


class _ENTETE(ctypes.Structure):
    _fields_ = [("taille", ctypes.c_uint32), ("largeur", ctypes.c_int32), ("hauteur", ctypes.c_int32),
                ("plans", ctypes.c_uint16), ("bits", ctypes.c_uint16), ("compression", ctypes.c_uint32),
                ("taille_image", ctypes.c_uint32), ("x", ctypes.c_int32), ("y", ctypes.c_int32),
                ("couleurs", ctypes.c_uint32), ("importantes", ctypes.c_uint32)]


# ---------- Capture de l'écran ----------

def _zone(tout_ecran):
    ex, ey = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    el, eh = user32.GetSystemMetrics(78), user32.GetSystemMetrics(79)
    if not tout_ecran:
        import jarvis_fenetres
        hwnd = jarvis_fenetres.active()
        if hwnd:
            r = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            x, y = max(ex, r.left), max(ey, r.top)
            l, h = min(ex + el, r.right) - x, min(ey + eh, r.bottom) - y
            if l > 200 and h > 150:
                return x, y, l, h, jarvis_fenetres.nom_court(hwnd)
    return ex, ey, el, eh, None


def capturer(tout_ecran=False):
    """Photographie la fenêtre active (ou tout l'écran). Renvoie (liste des images, nom de la fenêtre ou None)."""
    import pygame
    x, y, l, h, nom = _zone(tout_ecran)
    ecran = user32.GetDC(None)
    memoire = gdi32.CreateCompatibleDC(ecran)
    image = gdi32.CreateCompatibleBitmap(ecran, l, h)
    ancien = gdi32.SelectObject(memoire, image)
    try:
        gdi32.BitBlt(memoire, 0, 0, l, h, ecran, x, y, 0x00CC0020 | 0x40000000)
        entete = _ENTETE(ctypes.sizeof(_ENTETE), l, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        tampon = ctypes.create_string_buffer(l * h * 4)
        gdi32.SelectObject(memoire, ancien)
        gdi32.GetDIBits(memoire, image, 0, h, tampon, ctypes.byref(entete), 0)
    finally:
        gdi32.DeleteObject(image)
        gdi32.DeleteDC(memoire)
        user32.ReleaseDC(None, ecran)
    # Windows donne les couleurs dans l'ordre bleu-vert-rouge, avec une transparence à ignorer
    import numpy as np
    couleurs = np.frombuffer(tampon, dtype=np.uint8).reshape(h, l, 4)[:, :, 2::-1]
    surface = pygame.image.frombuffer(couleurs.tobytes(), (l, h), "RGB")
    os.makedirs(DOSSIER, exist_ok=True)
    for ancien_fichier in os.listdir(DOSSIER):
        try:
            os.remove(os.path.join(DOSSIER, ancien_fichier))
        except OSError:
            pass
    chemins = []
    nombre = max(1, math.ceil(h / HAUTEUR_MORCEAU))
    for i in range(nombre):
        haut = h * i // nombre
        morceau = surface.subsurface((0, haut, l, h * (i + 1) // nombre - haut))
        ml, mh = morceau.get_size()
        echelle = min(1.0, COTE_MAX / max(ml, mh))
        sortie = morceau
        if echelle < 1:
            sortie = pygame.transform.smoothscale(sortie, (int(ml * echelle), int(mh * echelle)))
        chemin = os.path.join(DOSSIER, f"ecran_{i + 1}.png" if nombre > 1 else "ecran.png")
        pygame.image.save(sortie, chemin)
        chemins.append(chemin)
    return chemins, nom


# ---------- Presse-papiers ----------

def lire_presse_papiers():
    """Le texte copié (ou "" s'il n'y en a pas)."""
    for _ in range(5):                       # une autre application peut l'occuper un court instant
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return ""
    try:
        poignee = user32.GetClipboardData(13)
        if not poignee:
            return ""
        adresse = kernel32.GlobalLock(poignee)
        if not adresse:
            return ""
        try:
            return ctypes.wstring_at(adresse)
        finally:
            kernel32.GlobalUnlock(poignee)
    finally:
        user32.CloseClipboard()


def ecrire_presse_papiers(texte):
    donnees = (texte.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")
    for _ in range(5):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        poignee = kernel32.GlobalAlloc(0x0002, len(donnees))
        adresse = kernel32.GlobalLock(poignee)
        ctypes.memmove(adresse, donnees, len(donnees))
        kernel32.GlobalUnlock(poignee)
        return bool(user32.SetClipboardData(13, poignee))
    finally:
        user32.CloseClipboard()


def copier_selection():
    """Appuie sur Ctrl + C dans la fenêtre active, pour prendre le texte sélectionné."""
    for code, drapeau in ((0x11, 0), (0x43, 0), (0x43, 2), (0x11, 2)):
        user32.keybd_event(code, 0, drapeau, 0)
    time.sleep(0.25)


# ---------- Ce qui est ajouté à la demande envoyée à Claude ----------

_ECRAN = (r"\b(à l'écran|sur l'écran|sur mon écran|mon écran|l'écran|cet écran|ce que tu vois|"
          r"ce qui est affiché|ce qu'il y a d'affiché|que vois-tu|tu vois quoi|regarde ça|regarde ceci|"
          r"cette (erreur|fenêtre|page|image|photo)|ce (message|tableau|graphique|texte) (à l'écran|affiché))\b")
_TOUT_ECRAN = r"\b(tout l'écran|écran entier|l'écran en entier|tout mon écran|le bureau)\b"
_COPIE = (r"\b(copiée?s?|presse[- ]papiers?|sélectionnée?s?|sélection|surlignée?s?)\b")
_SELECTION = r"\b(sélectionnée?s?|sélection|surlignée?s?)\b"
_LIRE_COPIE = r"^\W*(?:jarvis\W+)?(?:lis|lis-moi|lire|relis|dis-moi)\b.*\b(copiée?s?|presse[- ]papiers?)\b"
_BALISE = re.compile(r"\[\[COPIE\]\](.*?)\[\[/COPIE\]\]", re.S)
CONSIGNE = ("Quand une note t'indique une capture d'écran, lis l'image avec l'outil Read avant de répondre, "
            "puis réponds à la voix, brièvement. Quand une note te donne un texte copié et que TonyNio veut "
            "le corriger, le traduire ou le réécrire, mets le nouveau texte, et lui seul, entre [[COPIE]] et "
            "[[/COPIE]] (Jarvis le placera dans le presse-papiers), suivi d'une courte phrase à dire ; "
            "s'il veut un résumé ou une explication, réponds simplement à la voix. ")


def lecture_directe(t):
    """« lis ce que j'ai copié » : renvoie le texte à lire à voix haute, ou None."""
    if not re.search(_LIRE_COPIE, t) or re.search(r"\b(résume|traduis|corrige|explique)\b", t):
        return None
    texte = " ".join(lire_presse_papiers().split())
    if not texte:
        return "Le presse-papiers ne contient pas de texte."
    return texte if len(texte) <= 900 else texte[:900].rsplit(" ", 1)[0] + "… Le texte continue, je m'arrête là."


def complement(t):
    """Note ajoutée devant la demande pour Claude : capture d'écran et/ou texte copié. "" si rien à ajouter."""
    note = ""
    if re.search(_ECRAN, t) and not re.search(r"\bcapture\b", t):
        try:
            chemins, nom = capturer(bool(re.search(_TOUT_ECRAN, t)))
            quoi = f"de la fenêtre « {nom} »" if nom else "de tout l'écran"
            note += (f"(Capture {quoi} de TonyNio, prise à l'instant"
                     + (", en " + str(len(chemins)) + " images de haut en bas" if len(chemins) > 1 else "")
                     + " : " + " ; ".join(chemins) + ".) ")
        except Exception as erreur:
            print("Capture de l'écran impossible :", erreur)
    if re.search(_COPIE, t):
        if re.search(_SELECTION, t):
            copier_selection()
        texte = lire_presse_papiers().strip()
        if texte:
            if len(texte) > TEXTE_MAX:
                texte = texte[:TEXTE_MAX] + " […]"
            note += "(Texte copié par TonyNio, entre les trois guillemets : \"\"\"" + texte + "\"\"\") "
        else:
            note += "(Le presse-papiers de TonyNio ne contient aucun texte.) "
    return note


def appliquer_copie(reponse):
    """Si Claude a renvoyé un texte entre [[COPIE]] et [[/COPIE]], le met dans le presse-papiers.
    Renvoie ce qu'il reste à dire à voix haute."""
    m = _BALISE.search(reponse)
    if not m:
        return reponse
    reste = _BALISE.sub(" ", reponse).strip()
    if ecrire_presse_papiers(m.group(1).strip()):
        print("Presse-papiers : texte remplacé (%d caractères)." % len(m.group(1).strip()))
        return reste or "C'est fait, le texte est dans le presse-papiers : tu peux le coller."
    return "Je n'ai pas réussi à mettre le texte dans le presse-papiers."
