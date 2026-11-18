# -*- coding: utf-8 -*-
"""
JARVIS - associer l'Apple TV à Jarvis, une seule fois.

Lance ce fichier, puis regarde la télé : un code à 4 chiffres s'y affiche, deux fois (une pour la
télécommande, une pour savoir ce qui passe). Tape chaque code ici. Les clés d'association sont rangées
dans le Gestionnaire d'identification de Windows, jamais dans un fichier.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jarvis_appletv
from jarvis_ajouter_camera import ranger


def _journal(texte):
    """Ce qui s'est passé (jamais de code ni de clé), pour comprendre un échec."""
    import time
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("[association Apple TV %d/%m %H:%M:%S] ") + texte + "\n")
    except OSError:
        pass


async def associer(ip):
    import pyatv
    from pyatv.const import Protocol
    loop = asyncio.get_running_loop()
    trouves = await pyatv.scan(loop, hosts=[ip], timeout=5)
    if not trouves:
        print("L'Apple TV ne répond pas. Elle est allumée ?")
        return False
    conf = trouves[0]
    print(f"Apple TV trouvée : {conf.name}.")
    reussi = True
    for nom in ("Companion", "AirPlay"):
        protocole = getattr(Protocol, nom)
        if not conf.get_service(protocole):
            continue
        for essai in range(3):
            association = await pyatv.pair(conf, protocole, loop, name="Jarvis")
            try:
                await association.begin()
                # la saisie se fait à côté : la connexion avec l'Apple TV reste vivante pendant qu'on tape
                code = await loop.run_in_executor(None, input,
                                                  f"\n[{'télécommande' if nom == 'Companion' else 'ce qui passe'}] "
                                                  "Tape le code à 4 chiffres affiché sur la télé, puis Entrée : ")
                code = "".join(c for c in code if c.isdigit())
                association.pin(int(code) if code else 0)
                await association.finish()
                if association.has_paired:
                    ranger(jarvis_appletv.CIBLES[nom], "Jarvis", association.service.credentials)
                    print("Associé.")
                    _journal(f"{nom} : associé")
                    break
                print("Code refusé, on recommence.")
                _journal(f"{nom} : code refusé")
            except Exception as erreur:
                print("Ça n'a pas marché :", type(erreur).__name__, erreur)
                _journal(f"{nom} : {type(erreur).__name__} {erreur}")
            finally:
                await association.close()
            await asyncio.sleep(5)                  # après un échec, l'Apple TV demande d'attendre quelques secondes
        else:
            reussi = False
    return reussi


def main():
    ip = jarvis_appletv.adresse()
    if not ip:
        print("Je ne trouve pas l'Apple TV sur le réseau.")
    else:
        print("Allume la télé sur l'Apple TV, puis attends le code.")
        ok = asyncio.run(associer(ip))
        print("\nC'est fini, tu peux fermer cette fenêtre." if ok else "\nUne étape n'a pas marché : relance ce fichier.")
    input("\nAppuie sur Entrée pour fermer.")


if __name__ == "__main__":
    main()
