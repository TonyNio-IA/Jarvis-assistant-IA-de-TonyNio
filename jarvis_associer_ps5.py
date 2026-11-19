# -*- coding: utf-8 -*-
"""
JARVIS - relier une PlayStation 5 à Jarvis, une seule fois par console.

Jarvis pourra ensuite la sortir de veille et la remettre en veille (comme l'application PS Remote Play de Sony).
Deux étapes, faites par toi :
  1. te connecter à ton compte PlayStation dans le navigateur (Jarvis ne voit jamais ton mot de passe : il ne reçoit
     que l'adresse de la page d'arrivée, qui lui donne le numéro de ton compte) ;
  2. taper le code à 8 chiffres affiché par la console (Réglages > Système > Lecture à distance > Associer un appareil).
Ce qui permet de reconnaître Jarvis est gardé dans ton dossier personnel (.pyremoteplay), hors de Jarvis : jamais publié.
Module pyremoteplay (licence MIT).
"""
import os
import sys
import webbrowser

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

import jarvis_ps5

# Journal de l'association (dossier « tele », jamais publié) : ce qui s'affiche, pour comprendre un échec.
# Ce que tu tapes (adresse, code) n'y est jamais écrit : seulement sa longueur.
import builtins
import time
_JOURNAL = os.path.join(DOSSIER, "tele", "ps5_association.log")
_print, _input = builtins.print, builtins.input


def _noter(texte):
    try:
        os.makedirs(os.path.dirname(_JOURNAL), exist_ok=True)
        with open(_JOURNAL, "a", encoding="utf-8") as j:
            j.write(time.strftime("%d/%m %H:%M:%S ") + texte.replace("\n", " ") + "\n")
    except OSError:
        pass


def print(*a, **k):
    _noter(" ".join(str(x) for x in a))
    _print(*a, **k)


def input(question=""):
    _noter(question.strip())
    reponse = _input(question)
    _noter(f"   (saisie de {len(reponse.strip())} caractères)")
    return reponse


def choisir(consoles):
    if len(consoles) == 1:
        return consoles[0]
    print("Quelle console veux-tu relier ?")
    for i, (nom, ip) in enumerate(consoles, 1):
        print(f"  {i}. {nom}" + ("" if ip else "  (éteinte ou introuvable)"))
    while True:
        choix = input("Tape son numéro, puis Entrée : ").strip()
        if choix.isdigit() and 1 <= int(choix) <= len(consoles):
            return consoles[int(choix) - 1]


def main():
    jarvis_ps5.preparer_netifaces()                  # « netifaces » ne s'installe pas sur Windows : Jarvis le remplace
    from pyremoteplay import RPDevice, oauth
    import types
    # Le service de Sony met parfois près de 10 secondes à répondre, et le module n'en attend que 3 : on attend 40 s.
    # Quand Sony est surchargé, la demande reste sans réponse : on la refait jusqu'à 4 fois avec la même adresse.
    vrai = oauth.requests

    def patient(envoyer):
        def demander(url, **k):
            for essai in range(4):
                try:
                    return envoyer(url, **dict(k, timeout=30))
                except (vrai.exceptions.Timeout, vrai.exceptions.ConnectionError):
                    if essai == 3:
                        raise
                    print(f"   Sony ne répond pas, je réessaie ({essai + 2} sur 4)...")
        return demander

    oauth.requests = types.SimpleNamespace(post=patient(vrai.post), get=patient(vrai.get))
    profils = jarvis_ps5.profils()
    consoles = jarvis_ps5._consoles()
    demandee = " ".join(sys.argv[1:]).strip().lower()
    if demandee:
        consoles = [c for c in consoles if c[0].lower() == demandee] or consoles
    if not consoles:
        print("Je ne trouve aucune PS5 sur le réseau. Allume-la, puis relance.")
        return
    nom, ip = choisir(consoles)
    if not ip:
        print(f"{nom} ne répond pas. Allume-la (pas en veille), puis relance.")
        return
    console = RPDevice(ip)
    if not console.get_status() or not console.is_on:
        print(f"{nom} doit être allumée (pas en veille) pour être reliée. Allume-la, puis relance.")
        return
    print(f"Console : {nom}\n")

    if not profils.usernames:
        print("ÉTAPE 1 - Ton compte PlayStation")
        print("Une page de connexion Sony va s'ouvrir dans ton navigateur. Connecte-toi.")
        print("Tu arrives ensuite sur une page presque vide où il est écrit « redirect ».")
        print("Copie alors TOUTE l'adresse de cette page (dans la barre d'adresse) et colle-la ici.\n")
        input("Appuie sur Entrée pour ouvrir la page de connexion.")
        webbrowser.open(oauth.get_login_url())
        for _ in range(3):
            adresse = input("\nColle ici l'adresse de la page « redirect », puis Entrée : ").strip()
            _noter("   (adresse de la bonne page : " + str(adresse.startswith("https://remoteplay.dl.playstation.net/remoteplay/redirect"))
                   + ", avec un code : " + str("code=" in adresse) + ")")
            import re
            trouvee = re.search(r"https://remoteplay\.dl\.playstation\.net/remoteplay/redirect\S*", adresse)
            adresse = trouvee.group(0) if trouvee else adresse      # une lettre tapée avant l'adresse ne gêne pas
            print("Je demande ton numéro de compte à Sony, ça peut prendre jusqu'à 2 minutes s'il est surchargé...")
            try:
                if profils.new_user(adresse):
                    break
            except Exception as erreur:
                print("(", type(erreur).__name__, ")")
                if "Timeout" in type(erreur).__name__ or "Connection" in type(erreur).__name__:
                    print("Le service de Sony ne répond pas en ce moment (il est surchargé). Réessaie plus tard.")
                    return
            print("Cette adresse n'a pas été acceptée (elle ne sert qu'une fois et expire vite). Reconnecte-toi et recommence.")
            webbrowser.open(oauth.get_login_url())
        else:
            print("\nÇa n'a pas marché. Relance ce fichier pour réessayer.")
            return
        print("Compte reconnu :", profils.usernames[0])
    utilisateur = profils.usernames[0]

    print("\nÉTAPE 2 - Le code de la console")
    print("Sur la PS5 : Réglages > Système > Lecture à distance > Associer un appareil.")
    print("(Si besoin, active d'abord « Activer la Lecture à distance » dans ce même menu.)")
    for _ in range(3):
        code = input("\nTape le code à 8 chiffres affiché par la console, puis Entrée : ").replace(" ", "").strip()
        try:
            if console.register(utilisateur, code, timeout=10.0, profiles=profils):
                print(f"\nC'est fait : {nom} est reliée à Jarvis.")
                print("Pour que Jarvis puisse la rallumer, laisse-la en mode repos (pas éteinte), avec, dans")
                print("Réglages > Système > Gestion de l'énergie > Fonctionnalités disponibles en mode repos :")
                print("« Rester connecté à Internet » et « Activer la mise sous tension de la PS5 depuis le réseau ».")
                return
        except Exception as erreur:
            print("(", type(erreur).__name__, erreur, ")")
        print("Code refusé. Vérifie le code affiché (il change à chaque essai) et recommence.")
    print("\nÇa n'a pas marché. Relance ce fichier pour réessayer.")


if __name__ == "__main__":
    _noter("===== ouverture de la fenêtre =====")
    try:
        main()
    except BaseException as erreur:
        print("Erreur :", type(erreur).__name__, erreur)
    for _ in range(2):                                  # deux fois : un Entrée de trop ne ferme pas la fenêtre
        input("\nAppuie sur Entrée pour fermer.")
