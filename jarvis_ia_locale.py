# -*- coding: utf-8 -*-
"""Une IA gratuite sur le PC (Ollama), installée PAS À PAS et en douceur :
1. Jarvis vérifie d'abord que le PC le permet (mémoire, processeur, place libre, Windows) et le dit simplement ;
2. il prévient AVANT : ce qui sera téléchargé (taille lue sur le site au moment même) et que ça peut être long ;
3. il télécharge l'installateur officiel d'Ollama (ollama.com), l'utilisateur clique sur « Install » ;
4. il télécharge le modèle, avec une barre de progression et le temps restant mesuré ;
5. il le branche tout seul dans les assistants de Jarvis et pose une question d'essai.
Rien n'est envoyé ailleurs : l'IA tourne sur le PC. Gratuit. Désinstallable comme un programme normal.
Sources des chiffres (vérifiées le 27/11/2026) : docs.ollama.com/windows (Windows 10 22H2 ou plus récent, au moins
4 Go pour Ollama lui-même, modèles dans %HOMEPATH%\\.ollama, pas de droits administrateur) et ollama.com/library/gemma3
(gemma3:4b = 3,4 Go, gemma3:1b = 806 Mo)."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

URL_INSTALLATEUR = "https://ollama.com/download/OllamaSetup.exe"
API = "http://localhost:11434"
ESPACE_OLLAMA_GO = 4.0          # docs.ollama.com : « at least 4GB » pour Ollama lui-même
MARGE_GO = 3.0                  # on laisse toujours de la place à Windows
MODELES = {   # nom Ollama : (taille du téléchargement en Go, ce qu'on en dit)
    "gemma3:4b": (3.4, "Gemma 3 (4B) de Google : bon en français, pour un PC de 12 Go de mémoire ou plus"),
    "gemma3:1b": (0.8, "Gemma 3 (1B) de Google : petit et plus rapide, réponses plus simples"),
}
SANS_FENETRE = 0x08000000


# ------------------------------------------------------------------ 1. le PC le permet-il ?

def _materiel():
    try:
        import jarvis_rapports
        return jarvis_rapports._materiel()
    except Exception:
        return {}


def _build_windows():
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def deja_installe():
    chemin = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe")
    return os.path.exists(chemin) or bool(shutil.which("ollama"))


def api_prete(delai=2):
    try:
        with urllib.request.urlopen(API + "/api/version", timeout=delai) as r:
            return r.status == 200
    except Exception:
        return False


def verifier_pc(m=None, libre_go=None, build=None):
    """Décide si ce PC peut faire tourner une IA locale, et laquelle.
    Renvoie {"possible": bool, "modele": nom ou None, "raisons": [phrases simples], "avertissements": [...],
             "besoin_go": place nécessaire}. Sans effet de bord (essayée dans tests\\essai_ia_locale_166.py)."""
    m = m if m is not None else _materiel()
    build = build if build is not None else _build_windows()
    if libre_go is None:
        try:
            libre_go = shutil.disk_usage(os.path.expanduser("~")).free / 2 ** 30
        except OSError:
            libre_go = 0
    memoire = float(m.get("memoire_go") or 0)
    fils = int(m.get("fils_de_calcul") or 0)
    processeur = str(m.get("processeur") or "")
    raisons, avert = [], []
    if build and build < 19045:
        raisons.append("Windows est trop ancien : il faut Windows 10 version 22H2 ou plus récent.")
    lent = bool(re.search(r"\b(celeron|pentium|atom)\b", processeur, re.I)) or (0 < fils < 4)
    if lent:
        raisons.append("Le processeur de ce PC est trop modeste : une IA sur le PC mettrait très longtemps à répondre "
                       "et ralentirait tout le reste.")
    if memoire and memoire < 7.5:
        raisons.append(f"Ce PC a {memoire:.0f} Go de mémoire : il en faut au moins 8 pour une IA sur le PC.")
    modele = None
    if not raisons:
        if memoire >= 12 or not memoire:
            modele = "gemma3:4b"
        else:
            modele = "gemma3:1b"
            avert.append(f"Avec {memoire:.0f} Go de mémoire, je choisis le petit modèle : ses réponses seront plus "
                         "simples que celles de Claude.")
    besoin = ESPACE_OLLAMA_GO + (MODELES[modele][0] if modele else 0) + MARGE_GO
    if modele and libre_go < besoin:
        raisons.append(f"Il faut environ {besoin:.0f} Go de place libre, et il en reste {libre_go:.0f}. "
                       "Libère de la place puis réessaie.")
        modele = None
    carte = any(re.search(r"nvidia|radeon rx|\barc a\d", str(c.get("nom", "")), re.I)
                for c in (m.get("cartes_graphiques") or []))
    # processeur de portable économe (« 3500U », « i5-8250U », « Core 7 150U ») : prévu pour consommer peu, pas pour calculer vite
    econome = bool(re.search(r"\d{3,5}[uy]\b", processeur, re.I))
    if modele and not carte and econome:
        modele = "gemma3:1b"
        besoin = ESPACE_OLLAMA_GO + MODELES[modele][0] + MARGE_GO
        avert[:] = [a for a in avert if "petit modèle" not in a]
        avert.append("Ça marchera, mais lentement : ce PC a un processeur de portable prévu pour consommer peu, et pas "
                     "de carte graphique dédiée. Je choisis donc le petit modèle, et ses réponses mettront nettement plus "
                     "de temps que celles de Claude. Si tu as Claude, tu n'en as pas vraiment besoin.")
    elif modele and not carte:
        avert.append("Ce PC n'a pas de carte graphique dédiée : l'IA tournera sur le processeur, compte quelques "
                     "secondes de plus par réponse.")
    return {"possible": bool(modele), "modele": modele, "raisons": raisons, "avertissements": avert,
            "besoin_go": round(besoin, 1), "libre_go": round(libre_go, 1)}


# ------------------------------------------------------------------ 2 à 5. les étapes

def taille_distante(url=URL_INSTALLATEUR):
    """Taille réelle de l'installateur, lue sur le site (en Go), ou None."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(req, timeout=15) as r:
            n = int(r.headers.get("Content-Length") or 0)
            return n / 2 ** 30 if n else None
    except Exception:
        return None


def telecharger(url, chemin, progres):
    """progres(fait_octets, total_octets)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Jarvis"})
    with urllib.request.urlopen(req, timeout=60) as r, open(chemin + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        fait = 0
        while True:
            bloc = r.read(1 << 20)
            if not bloc:
                break
            f.write(bloc)
            fait += len(bloc)
            progres(fait, total)
    os.replace(chemin + ".part", chemin)


def tirer_modele(modele, progres):
    """Télécharge le modèle par l'API d'Ollama ; progres(fait, total, statut)."""
    corps = json.dumps({"model": modele, "stream": True}).encode()
    req = urllib.request.Request(API + "/api/pull", data=corps, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=3600) as r:
        for ligne in r:
            try:
                d = json.loads(ligne)
            except ValueError:
                continue
            if d.get("error"):
                raise RuntimeError(d["error"])
            progres(d.get("completed") or 0, d.get("total") or 0, d.get("status") or "")
            if d.get("status") == "success":
                return True
    return False


def brancher(modele):
    """Ajoute Ollama aux assistants de Jarvis (une seule fois). Renvoie l'id du compte."""
    import jarvis_assistants as a
    for c in a.charger()["comptes"]:
        if c.get("fournisseur") == "ollama":
            a.modifier_compte(c["id"], modele=modele, actif=True, pause_jusqua=0, derniere_erreur="")
            return c["id"]
    ok, message, cid = a.ajouter_compte("ollama", "", modele=modele)
    if not ok:
        raise RuntimeError(message)
    return cid


def duree_restante(fait, total, debut):
    ecoule = time.time() - debut
    if fait <= 0 or total <= 0 or ecoule < 3:
        return ""
    reste = (total - fait) * ecoule / fait
    if reste < 60:
        return "moins d'une minute"
    if reste < 3600:
        return f"environ {round(reste / 60)} minutes"
    return f"environ {reste / 3600:.1f} heures".replace(".", ",")


# ------------------------------------------------------------------ la fenêtre

def fenetre(demo=False):
    import tkinter as tk
    from tkinter import ttk
    f = tk.Tk()
    f.title("Jarvis – une IA gratuite sur ton PC")
    larg = min(720, f.winfo_screenwidth() - 60)
    haut = min(560, f.winfo_screenheight() - 100)
    f.geometry(f"{larg}x{haut}+{max(0, (f.winfo_screenwidth() - larg) // 2)}+{max(0, (f.winfo_screenheight() - haut) // 3)}")
    f.minsize(420, 360)
    police = ("Segoe UI", 11)
    titre = tk.Label(f, font=("Segoe UI", 14, "bold"), anchor="w", justify="left")
    titre.pack(fill="x", padx=16, pady=(14, 6))
    texte = tk.Label(f, font=police, anchor="nw", justify="left")
    texte.pack(fill="both", expand=True, padx=16)
    f.bind("<Configure>", lambda e: texte.config(wraplength=max(300, f.winfo_width() - 40)))
    barre = ttk.Progressbar(f, maximum=1000)
    detail = tk.Label(f, font=("Segoe UI", 10), anchor="w", fg="#555")
    boutons = tk.Frame(f)
    boutons.pack(fill="x", padx=16, pady=14)
    etat = {"annule": False}

    def montrer(t, corps, actions=()):
        titre.config(text=t)
        texte.config(text=corps)
        for b in boutons.winfo_children():
            b.destroy()
        for nom, fonction, principal in actions:
            tk.Button(boutons, text=nom, font=police, command=fonction, padx=12,
                      bg="#2e7d32" if principal else None, fg="white" if principal else None).pack(side="right", padx=4)

    def progression(visible):
        if visible:
            barre.pack(fill="x", padx=16, before=boutons)
            detail.pack(fill="x", padx=16, before=boutons)
        else:
            barre.pack_forget()
            detail.pack_forget()

    def plus_tard():
        etat["annule"] = True
        f.destroy()

    import queue
    a_faire = queue.Queue()            # le travail de fond ne touche jamais la fenêtre lui-même (Tk n'aime pas ça)

    def dans_la_fenetre(fonction, *args):
        a_faire.put((fonction, args))

    def vider():
        try:
            while True:
                fonction, args = a_faire.get_nowait()
                fonction(*args)
        except queue.Empty:
            pass
        except tk.TclError:
            return
        f.after(100, vider)
    f.after(100, vider)

    # --- étape 1 : vérification
    v = verifier_pc()
    if api_prete() or deja_installe():
        v["deja"] = True
    if not v["possible"]:
        montrer("Ton PC ne permet pas d'installer une IA sur le PC",
                "J'ai vérifié ton ordinateur :\n\n• " + "\n• ".join(v["raisons"]) +
                "\n\nCe n'est pas grave : Jarvis continue de marcher comme avant, avec Claude ou les autres assistants "
                "gratuits en ligne (onglet Assistants des réglages).", [("Fermer", f.destroy, True)])
        f.mainloop()
        return
    modele = v["modele"]
    taille_inst = None if v.get("deja") or demo else taille_distante()
    total = MODELES[modele][0] + (0 if v.get("deja") else (taille_inst or 0))
    lignes = ["Bonne nouvelle : ton PC le permet. Voici ce qui va se passer, étape par étape :", ""]
    if not v.get("deja"):
        lignes.append("1. Je télécharge Ollama, le programme gratuit qui fait tourner l'IA"
                      + (f" ({taille_inst:.1f} Go)".replace(".", ",") if taille_inst else "") + ".")
        lignes.append("2. Une fenêtre d'installation d'Ollama s'ouvre : tu cliques sur « Install », c'est tout.")
    else:
        lignes.append("Ollama est déjà sur ton PC : je passe directement au modèle.")
    lignes.append(f"{'3' if not v.get('deja') else '1'}. Je télécharge le modèle d'IA : {MODELES[modele][1]} "
                  f"({MODELES[modele][0]:.1f} Go).".replace(".", ",", 1))
    lignes.append(f"{'4' if not v.get('deja') else '2'}. Je le branche tout seul dans Jarvis et je fais un essai.")
    lignes += ["", f"À télécharger en tout : environ {total:.1f} Go. Place nécessaire : {v['besoin_go']:.0f} Go "
                   f"(il t'en reste {v['libre_go']:.0f}).".replace(".", ",", 1),
               "Selon ta connexion, ça peut prendre de quelques minutes à plus d'une heure : je t'afficherai le temps "
               "restant. Tu peux continuer à utiliser ton PC pendant ce temps.",
               "C'est gratuit, rien de ce que tu demandes ne sort de ton PC, et tu pourras l'enlever comme n'importe "
               "quel programme (Paramètres > Applications > Ollama)."]
    if v["avertissements"]:
        lignes += [""] + ["⚠ " + a for a in v["avertissements"]]

    def lancer():
        if demo:
            montrer("Démonstration", "Mode démonstration : rien n'est téléchargé.", [("Fermer", f.destroy, True)])
            return
        threading.Thread(target=travail, daemon=True).start()

    def travail():
        try:
            if not v.get("deja"):
                dossier = tempfile.mkdtemp(prefix="jarvis-ollama-")
                chemin = os.path.join(dossier, "OllamaSetup.exe")
                debut = time.time()
                dans_la_fenetre(montrer, "Étape 1 : téléchargement d'Ollama", "Je télécharge le programme officiel "
                                "depuis ollama.com.", [("Annuler", plus_tard, False)])
                dans_la_fenetre(progression, True)

                def p1(fait, tot):
                    if etat["annule"]:
                        raise RuntimeError("annulé")
                    if tot:
                        dans_la_fenetre(barre.config, {"value": 1000 * fait / tot})
                        dans_la_fenetre(detail.config, {"text": f"{fait / 2**20:.0f} Mo sur {tot / 2**20:.0f} Mo – "
                                                                f"{duree_restante(fait, tot, debut)}"})
                telecharger(URL_INSTALLATEUR, chemin, p1)
                dans_la_fenetre(progression, False)
                dans_la_fenetre(montrer, "Étape 2 : installation d'Ollama",
                                "La fenêtre d'installation d'Ollama va s'ouvrir.\n\nClique sur « Install », puis attends "
                                "la fin. Je continue tout seul dès qu'Ollama est prêt (je surveille).",
                                [("Annuler", plus_tard, False)])
                subprocess.Popen([chemin])
                limite = time.time() + 20 * 60
                while not api_prete() and time.time() < limite and not etat["annule"]:
                    time.sleep(3)
                if not api_prete():
                    raise RuntimeError("Ollama ne s'est pas lancé. Si tu as fermé l'installation, relance-moi plus tard.")
            debut = time.time()
            dans_la_fenetre(montrer, "Étape 3 : téléchargement du modèle d'IA",
                            f"Je télécharge {MODELES[modele][1]}.", [("Annuler", plus_tard, False)])
            dans_la_fenetre(progression, True)

            def p2(fait, tot, statut):
                if etat["annule"]:
                    raise RuntimeError("annulé")
                if tot:
                    dans_la_fenetre(barre.config, {"value": 1000 * fait / tot})
                    dans_la_fenetre(detail.config, {"text": f"{fait / 2**30:.2f} Go sur {tot / 2**30:.2f} Go – "
                                                            f"{duree_restante(fait, tot, debut)}".replace(".", ",")})
            tirer_modele(modele, p2)
            dans_la_fenetre(progression, False)
            dans_la_fenetre(montrer, "Étape 4 : branchement dans Jarvis", "Je branche l'IA et je lui pose une "
                            "question d'essai (la première réponse peut prendre une minute, le temps qu'elle se charge).")
            brancher(modele)
            import jarvis_assistants as a
            t0 = time.time()
            reponse, nom, erreur = a.demander("Dis bonjour en une seule phrase courte, en français.")
            if not reponse:
                raise RuntimeError(erreur or "pas de réponse à l'essai")
            dans_la_fenetre(montrer, "C'est prêt !",
                            f"Réponse d'essai ({time.time() - t0:.0f} s) : « {reponse} »\n\nQuand Claude n'est pas là "
                            "ou n'a plus de quota, Jarvis demandera à cette IA, sur ton PC. Tu la retrouves dans "
                            "l'onglet Assistants des réglages.", [("Fermer", f.destroy, True)])
        except Exception as erreur:
            if etat["annule"]:
                return
            dans_la_fenetre(progression, False)
            dans_la_fenetre(montrer, "Ça n'a pas marché cette fois",
                            f"{erreur}\n\nRien n'est cassé : Jarvis marche comme avant. Tu peux réessayer plus tard en "
                            "disant : Jarvis, installe une IA gratuite sur mon PC.", [("Fermer", f.destroy, True)])

    montrer("Une IA gratuite sur ton PC", "\n".join(lignes),
            [("Installer", lancer, True), ("Pas maintenant", plus_tard, False)])
    f.mainloop()


_COMMANDE = re.compile(r"\b(?:installe|installer|mets|ajoute)(?:[- ]moi)? (?:une |l')?(?:ia|intelligence artificielle|"
                       r"ollama)(?: gratuite)?(?: (?:sur|dans) (?:mon|le|ce) (?:pc|ordinateur|ordi))?\b|\binstalle ollama\b")


def commande(t):
    import unicodedata
    s = "".join(c for c in unicodedata.normalize("NFD", (t or "").lower()) if unicodedata.category(c) != "Mn")
    if not _COMMANDE.search(s) or re.search(r"\b(?:comment|pourquoi|c'est quoi|est ce que)\b", s):
        return None
    try:
        import jarvis_enfant
        import jarvis_extras
        if jarvis_enfant.actif() or jarvis_extras.invite():
            return "Installer un programme, c'est pour les adultes de la maison : demande à un parent."
    except Exception:
        pass
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    subprocess.Popen([pythonw if os.path.exists(pythonw) else sys.executable, os.path.abspath(__file__)],
                     creationflags=SANS_FENETRE)
    return ("J'ouvre l'installation pas à pas. Je vérifie d'abord que ton PC le permet, et je te dis tout avant de "
            "télécharger quoi que ce soit.")


if __name__ == "__main__":
    fenetre(demo="--demo" in sys.argv)
