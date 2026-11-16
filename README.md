# Jarvis, assistant IA de TonyNio

**Version actuelle : 1.04**

Assistant vocal en français pour Windows 11. On l'appelle en disant « Jarvis », il comprend la demande, la confie à Claude (Claude Code, abonnement Claude Pro) et répond à voix haute. Un réacteur animé en bas à droite de l'écran montre ce qu'il fait.

## Ce qu'il sait faire

- Se réveiller quand une phrase commence par « Jarvis » (un petit bip indique qu'on peut parler).
- Répondre aux questions et agir sur le PC (ouvrir un programme, chercher une information...).
- Enchaîner une autre demande dans les 3 secondes sans redire « Jarvis ».
- Se souvenir de la conversation pendant 10 minutes (« Jarvis, nouvelle conversation » pour repartir de zéro).
- « Jarvis, fais-moi le point du jour » : météo de Paris, actualités, SpaceX, GTA 6, PS5 et Logic-Sunrise.
  Il le prépare en arrière-plan et le lit dès qu'il est prêt ; « Jarvis, annule le point du jour » l'arrête.
  (Réglage `POINT_DU_JOUR_AUTO = True` pour qu'il le prépare tout seul au premier démarrage du matin.)
- Réponse immédiate, sans Claude, pour : l'heure, la date, la météo (aujourd'hui, demain, après-demain, via Open-Meteo), le volume, la musique (pause, suivant, précédent), les minuteurs et rappels (« rappelle-moi dans 20 minutes de sortir le linge »), l'ouverture d'applications courantes et le verrouillage du PC.
- « Jarvis, répète » : il redit sa dernière réponse.
- « Jarvis, état du PC » (ou « pourquoi ça rame ») : processeur, mémoire, programme le plus gourmand, place sur le disque.
- « Jarvis, note que... » et « Jarvis, lis mes notes » (fichier `notes.txt`).
- Sous le réacteur : ce que Jarvis a compris, la charge du processeur, la mémoire et le débit du réseau en temps réel.
- « Stop », « Jarvis, stop » ou « Tais-toi » pendant qu'il parle : il se tait.
- Se mettre en pause tout seul quand l'application Claude lit un message à voix haute (touche F9).
- Démarrer avec Windows, sans fenêtre.

## Fichiers

| Fichier | Rôle |
|---|---|
| `jarvis_reacteur.py` | Point d'entrée : le réacteur animé, qui lance Jarvis |
| `jarvis_claude.py` | L'écoute, la reconnaissance vocale et le dialogue avec Claude |
| `jarvis_voix.py` | La voix naturelle « Henri » (edge-tts) |
| `jarvis_commandes.py` | Les commandes instantanées (heure, date, volume, applications) |
| `jarvis_systeme.py` | La surveillance du PC (processeur, mémoire, réseau) |
| `jarvis_tts.py` | La voix Windows de secours |
| `requirements.txt` | Les modules Python nécessaires |

## Comment ça marche

1. **Vosk** (hors ligne) écoute en permanence et repère le mot « Jarvis ».
2. **Whisper** (modèle « base », sur le PC) retranscrit la demande plus précisément. Si Vosk et Whisper ne sont pas d'accord, les deux versions sont envoyées à Claude.
3. **Claude Code** reste ouvert en continu (modèle Sonnet) : une réponse simple arrive en 1 à 2 secondes.
   Il est lancé en version allégée (sans extensions, quatre outils seulement) : environ 4 fois moins de quota par question.
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

En haut de `jarvis_claude.py` : `MODELE` et `MODELE_POINT_DU_JOUR` (« sonnet » ou « opus »), `DELAI_SUITE`, `MEMOIRE_MINUTES`, `VILLE_METEO`...
En haut de `jarvis_reacteur.py` : `STYLE` (« anneau » ou « hud »), `TAILLE`, les couleurs des états...

Le journal `C:\Jarvis\jarvis.log` note tout ce que Jarvis entend et répond.

## Versions

| Version | Contenu |
|---|---|
| 1.04 | Processeur, mémoire et réseau affichés sous le réacteur, « état du PC », notes vocales, Jarvis 3 fois plus léger en veille, démarrage en 3 secondes |
| 1.03 | Claude allégé (environ 4 fois moins de quota), météo, minuteurs et musique sans Claude, voix par morceaux, réacteur réactif au son, sous-titre |
| 1.02 | Point du jour à la demande et annulable, filtre des phrases inventées par Whisper |
| 1.01 | Commandes instantanées, interruption « stop », point du jour automatique |
| 1.0 | Première sauvegarde : écoute, Claude en continu, voix Henri, réacteur animé |
