# Jarvis, assistant IA de TonyNio

**Version actuelle : 1.12**

Assistant vocal en français pour Windows 11. On l'appelle en disant « Jarvis », il comprend la demande, la confie à Claude (Claude Code, abonnement Claude Pro) et répond à voix haute. Un réacteur animé en bas à droite de l'écran montre ce qu'il fait.

## Ce qu'il sait faire

- Se réveiller quand une phrase commence par « Jarvis » (un petit bip indique qu'on peut parler).
- Répondre aux questions et agir sur le PC (ouvrir un programme, chercher une information...).
- Enchaîner une autre demande dans les 3 secondes sans redire « Jarvis ».
- Se souvenir de la conversation pendant 10 minutes (« Jarvis, nouvelle conversation » pour repartir de zéro).
- « Jarvis, fais-moi le point du jour » : météo de ta ville, actualités, SpaceX, GTA 6, PS5 et Logic-Sunrise.
  La ville se règle dans `ville.txt` (fichier gardé sur le PC, jamais publié : `Nom;latitude;longitude`).
  Il le prépare en arrière-plan et le lit dès qu'il est prêt ; « Jarvis, annule le point du jour » l'arrête.
  (Réglage `POINT_DU_JOUR_AUTO = True` pour qu'il le prépare tout seul au premier démarrage du matin.)
- Réponse immédiate, sans Claude, pour : l'heure, la date, la météo (aujourd'hui, demain, après-demain, via Open-Meteo), le volume, la musique (pause, suivant, précédent), les minuteurs et rappels (« rappelle-moi dans 20 minutes de sortir le linge »), l'ouverture d'applications courantes et le verrouillage du PC.
- « Jarvis, répète » : il redit sa dernière réponse.
- Rappels à heure fixe : « rappelle-moi à 18 h d'appeler le garage », « réveille-moi demain à 7 h », « quels sont mes rappels », « annule mes rappels ». Ils sont conservés si le PC redémarre.
- « Ferme Chrome », « fais une capture d'écran », « cherche le fichier facture », « ouvre WinRAR » (toute application du menu Démarrer).
- Routines : « Jarvis, bonjour » (date, heure, météo, rappels du jour, état du PC) et « Jarvis, bonne nuit » (ferme les applications et met le PC en veille, après confirmation).
- Dictée : « Jarvis, dicte : je serai là dans dix minutes » tape la phrase dans la fenêtre active ; « appuie sur entrée » valide.
- Musique : « Jarvis, mets Get Lucky de Daft Punk » ou « mets de la musique » lance la lecture sur YouTube.
- « Éteins l'ordinateur », « redémarre l'ordinateur », « mets l'ordinateur en veille » : Jarvis demande toujours confirmation, et l'extinction peut être annulée pendant 30 secondes.
- « Jarvis, état du PC » (ou « pourquoi ça rame ») : processeur, mémoire, programme le plus gourmand, place sur le disque.
- Fenêtres : « mets Imou en plein écran », « réduis la fenêtre », « mets Chrome à gauche » (à droite, en haut, en bas), « mets Imou au premier plan », « ferme la fenêtre », « affiche le bureau ». Le nom d'une application ouverte est reconnu même mal entendu.
- « Jarvis, note que... » et « Jarvis, lis mes notes » (fichier `notes.txt`).
- Mémoire durable : « Jarvis, retiens que... », « qu'est-ce que tu as retenu ? », « oublie que... », « efface toute ta mémoire » (avec confirmation). Jarvis garde aussi le fil des derniers échanges : il sait de quoi vous parliez même après un redémarrage. Tout reste dans `memoire.json`, sur le PC.
- Sous le réacteur : l'heure, les mots compris au fil de l'écoute, puis la charge du processeur, la mémoire et le débit du réseau en temps réel.
- Autour du réacteur : une couronne de graduations qui dessine le spectre du son (ta voix quand il écoute, la sienne quand il répond).
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
| `jarvis_memoire.py` | La mémoire durable (faits retenus, derniers échanges) |
| `jarvis_fenetres.py` | La gestion des fenêtres à la voix (agrandir, réduire, placer, fermer) |
| `jarvis_affichage.py` | L'affichage rapide du réacteur et du panneau (pygame, 60 images/s) |
| `jarvis_systeme.py` | La surveillance du PC (processeur, mémoire, carte graphique, réseau) |
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
| 1.12 | Le son du PC est baissé pendant que tu parles à Jarvis, et il n'écoute plus de suite quand une vidéo ou de la musique joue ; Claude connaît les fenêtres ouvertes ; gestion des fenêtres à la voix ; applications déjà ouvertes reconnues même mal entendues ; réponses courtes (« oui », « non ») mieux comprises ; corrections après essais : « mets l'application en grand écran » ne lance plus une vidéo, les demandes doubles (« ferme ça et ouvre Chrome ») vont à Claude en entier, « Jarvis » redit en cours de conversation relance l'écoute, réveil et « éteins » mieux reconnus |
| 1.11 | Mémoire durable (faits retenus à la demande, fil des derniers échanges) ; écoute plus fine (le bip ne coupe plus le début de la demande, « mets » mieux compris, réaction en 0,1 s) ; mots affichés pendant l'écoute ; couronne de spectre, halo, onde de réveil et heure dans l'affichage ; ville de la météo réglable dans un fichier local |
| 1.10 | Rappels à heure fixe conservés au redémarrage, fermeture d'applications, capture d'écran, recherche de fichier, extinction / redémarrage / veille avec confirmation, ouverture des applications du menu Démarrer ; réveil plus tolérant ; panneau agrandi ; voix un peu plus rapide |
| 1.09 | Jauge de température (celle de la puce graphique, comme dans le Gestionnaire des tâches) |
| 1.08 | Le contour extérieur du réacteur ondule lui aussi |
| 1.07 | Correction : le réacteur reste de nouveau au premier plan ; jauge réseau calée sur le débit mesuré de la connexion |
| 1.06 | Affichage réécrit avec pygame : 60 images par seconde quand Jarvis est actif ; jauges GPU et réseau |
| 1.05 | Panneau sous le réacteur plus compact, style affichage de bord (jauges segmentées) ; le réacteur retient sa position |
| 1.04 | Processeur, mémoire et réseau affichés sous le réacteur, « état du PC », notes vocales, Jarvis 3 fois plus léger en veille, démarrage en 3 secondes |
| 1.03 | Claude allégé (environ 4 fois moins de quota), météo, minuteurs et musique sans Claude, voix par morceaux, réacteur réactif au son, sous-titre |
| 1.02 | Point du jour à la demande et annulable, filtre des phrases inventées par Whisper |
| 1.01 | Commandes instantanées, interruption « stop », point du jour automatique |
| 1.0 | Première sauvegarde : écoute, Claude en continu, voix Henri, réacteur animé |
