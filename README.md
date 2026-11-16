# Jarvis, assistant IA de TonyNio

Assistant vocal en français pour Windows 11. On l'appelle en disant « Jarvis », il comprend la demande, la confie à Claude (Claude Code, abonnement Claude Pro) et répond à voix haute. Un réacteur animé en bas à droite de l'écran montre ce qu'il fait.

## Ce qu'il sait faire

- Se réveiller quand une phrase commence par « Jarvis » (un petit bip indique qu'on peut parler).
- Répondre aux questions et agir sur le PC (ouvrir un programme, chercher une information...).
- Enchaîner une autre demande dans les 3 secondes sans redire « Jarvis ».
- Se souvenir de la conversation pendant 10 minutes (« Jarvis, nouvelle conversation » pour repartir de zéro).
- « Jarvis, fais-moi le point du jour » : météo de Paris, actualités, SpaceX, GTA 6, PS5 et Logic-Sunrise.
- Se mettre en pause tout seul quand l'application Claude lit un message à voix haute (touche F9).
- Démarrer avec Windows, sans fenêtre.

## Fichiers

| Fichier | Rôle |
|---|---|
| `jarvis_reacteur.py` | Point d'entrée : le réacteur animé, qui lance Jarvis |
| `jarvis_claude.py` | L'écoute, la reconnaissance vocale et le dialogue avec Claude |
| `jarvis_voix.py` | La voix naturelle « Henri » (edge-tts) |
| `jarvis_tts.py` | La voix Windows de secours |
| `requirements.txt` | Les modules Python nécessaires |

## Comment ça marche

1. **Vosk** (hors ligne) écoute en permanence et repère le mot « Jarvis ».
2. **Whisper** (modèle « base », sur le PC) retranscrit la demande plus précisément. Si Vosk et Whisper ne sont pas d'accord, les deux versions sont envoyées à Claude.
3. **Claude Code** reste ouvert en continu (modèle Sonnet) : une réponse simple arrive en 1 à 2 secondes.
4. **edge-tts** lit la réponse avec la voix d'Henri.

## Réinstaller sur un autre PC

1. Installer **Python 3.14** et **Claude Code** (connecté au compte Claude Pro).
2. Copier ces fichiers dans `C:\Jarvis`.
3. Installer les modules : `python -m pip install -r C:\Jarvis\requirements.txt`
4. Télécharger le modèle Vosk **vosk-model-small-fr-0.22** sur https://alphacephei.com/vosk/models et le décompresser dans `C:\Jarvis`.
   Le modèle Whisper se télécharge tout seul au premier lancement (dans `C:\Jarvis\whisper`).
5. Lancer : `pythonw C:\Jarvis\jarvis_reacteur.py`
6. Pour le démarrage automatique : créer un raccourci vers `pythonw.exe "C:\Jarvis\jarvis_reacteur.py"` (dossier de travail `C:\Jarvis`) et le placer dans `shell:startup`.

## Réglages utiles

En haut de `jarvis_claude.py` : `MODELE` (« sonnet » ou « opus »), `DELAI_SUITE`, `MEMOIRE_MINUTES`, `VILLE_METEO`...
En haut de `jarvis_reacteur.py` : `STYLE` (« anneau » ou « hud »), `TAILLE`, les couleurs des états...

Le journal `C:\Jarvis\jarvis.log` note tout ce que Jarvis entend et répond.
