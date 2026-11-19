# -*- coding: utf-8 -*-
"""
JARVIS - associer le Freebox Player POP (Android TV) à Jarvis, une seule fois.

Lance ce fichier, puis regarde la télé : un code de 6 caractères s'y affiche. Tape-le ici.
Jarvis crée alors son propre certificat (dossier « tele », jamais publié) et peut ensuite piloter le Player :
allumer, éteindre, volume, chaînes, pause... Comme la télécommande de l'application Google TV.
"""
import asyncio
import os
import sys

DOSSIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, DOSSIER)

import jarvis_tele


async def associer(ip):
    from androidtvremote2 import AndroidTVRemote, InvalidAuth, CannotConnect, ConnectionClosed
    os.makedirs(jarvis_tele.DOSSIER_CERT, exist_ok=True)
    tele = AndroidTVRemote("Jarvis", jarvis_tele.CERT, jarvis_tele.CLE, ip)
    await tele.async_generate_cert_if_missing()
    try:
        await tele.async_connect()
        print("Le Player est déjà associé à Jarvis : rien à faire.")
        tele.disconnect()
        return True
    except InvalidAuth:
        pass
    except (CannotConnect, ConnectionClosed) as erreur:
        print("Je n'arrive pas à joindre le Player :", erreur)
        return False
    for essai in range(3):
        await tele.async_start_pairing()
        code = input("\nRegarde la télé : tape ici le code affiché (6 caractères), puis Entrée : ").strip()
        try:
            await tele.async_finish_pairing(code)
            print("Associé !")
            await tele.async_connect()
            print("Connexion réussie au Player.")
            tele.disconnect()
            return True
        except InvalidAuth:
            print("Code refusé, on recommence (un nouveau code va s'afficher).")
        except ConnectionClosed:
            print("La télé a fermé la fenêtre du code, on recommence.")
    return False


def _noter_associee(appareil):
    """Retient dans tele/teles.json que cette télé est associée (Jarvis s'y connecte alors dès son démarrage)."""
    import json
    try:
        with open(jarvis_tele.FICHIER_TELES, encoding="utf-8-sig") as f:
            donnees = json.load(f)
        for tele in donnees.get("teles", []):
            if tele.get("appareil", "").lower() == appareil.lower():
                tele["associee"] = True
        with open(jarvis_tele.FICHIER_TELES, "w", encoding="utf-8") as f:
            json.dump(donnees, f, ensure_ascii=False, indent=1)
    except (OSError, ValueError) as erreur:
        print("Réglage des télés non mis à jour :", erreur)


def main():
    appareil = sys.argv[1] if len(sys.argv) > 1 else None        # une autre télé que le Player (voir tele/teles.json)
    nom = appareil or "Freebox Player POP"
    ip = jarvis_tele.adresse(appareil=appareil)
    if not ip:
        print(f"Je ne trouve pas {nom} sur le réseau. La télé est allumée ?")
    else:
        print(f"{nom} trouvé. Allume la télé, puis attends le code.")
        ok = asyncio.run(associer(ip))
        if ok and appareil:
            _noter_associee(appareil)
        print("\nC'est fini, tu peux fermer cette fenêtre." if ok else "\nÇa n'a pas marché : relance ce fichier.")
    input("\nAppuie sur Entrée pour fermer.")


if __name__ == "__main__":
    main()
