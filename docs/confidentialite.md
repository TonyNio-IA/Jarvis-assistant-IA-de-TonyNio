# Jarvis : ce qui est envoyé, et pourquoi

Jarvis est fait par une seule personne, sur son temps libre. Pour savoir ce qui marche mal chez les utilisateurs et l'améliorer pour tout le monde, Jarvis peut envoyer des rapports à son créateur. **Rien ne part sans votre accord**, sauf un compteur anonyme que vous pouvez couper.

## En bref

| Quoi | Quand | Votre accord |
| --- | --- | --- |
| Compteur anonyme | Au démarrage, puis toutes les heures | Non demandé, mais vous pouvez le couper (Réglages, rubrique « Rapports ») |
| Rapport technique | Toutes les heures, s'il y a du nouveau (et juste après une installation ou une mise à jour) | Activé par défaut (y compris, une fois, lors du passage à la 1.65 pour ceux qui l'avaient coupé), vous pouvez le couper à tout moment (Réglages, rubrique « Rapports ») : ce choix est alors gardé |
| Rapport complet | Toutes les heures, s'il y a du nouveau | Oui, seulement si vous le choisissez |
| « Signaler un problème », « Proposer une amélioration », questionnaire | Quand vous appuyez sur « Envoyer » | Oui, c'est vous qui envoyez |

## Le compteur anonyme

Un numéro propre à votre PC (depuis la version 1.63 : l'empreinte, illisible et à sens unique, de l'identifiant que Windows garde pour la machine, jamais l'identifiant lui-même ; il reste le même si vous réinstallez Jarvis et il ne dit rien de vous), la version de Jarvis, la version de Windows, le niveau de rapport choisi et, depuis la version 1.50, le type de matériel : le processeur et son nombre de cœurs, la mémoire, la carte graphique, et si le PC est un portable ou un fixe. Il sert uniquement à compter les installations et les utilisateurs actifs, et à savoir sur quels PC Jarvis tourne (par exemple pour repérer les PC trop lents). Il ne contient ni phrase, ni erreur, ni rien de ce que vous faites avec Jarvis.

Si vous donnez vous-même un nom à votre PC (« Jarvis, nomme ce PC… »), ce nom est envoyé avec le compteur. Personne n'a besoin de le faire : cela sert surtout au créateur de Jarvis pour reconnaître ses propres PC d'essai. « Jarvis, oublie le nom de ce PC » l'enlève.

## Le rapport technique

- les phrases que Jarvis n'a pas comprises ;
- les erreurs et plantages (le type d'erreur et l'endroit dans le code) ;
- les fonctions utilisées (par grandes familles : météo, minuteurs, télé…) et les temps de réponse ;
- les faux réveils (Jarvis se réveille alors qu'on ne l'appelait pas) ;
- les demandes refaites juste après, ou annulées (« stop », « non, pas ça ») ;
- les demandes que Jarvis a confiées à Claude, faute de savoir les faire seul ;
- le niveau du micro (bruit de fond) et le nom du micro ;
- le matériel du PC (processeur et nombre de cœurs, mémoire, carte graphique, taille et place libre du disque, portable ou fixe, version de Windows, taille de l'écran, échelle d'affichage de Windows et nombre d'écrans) ;
- les réglages faits ou jamais faits (oui ou non : ville, Claude, profils…), jamais leur contenu ;
- les appareils associés (combien de télés, Apple TV oui ou non…), jamais leur nom ni leurs identifiants ;
- les appareils que vous avez demandé à Jarvis de piloter et qu'il ne sait pas encore piloter : leur type seulement (par exemple « télé Samsung » ou « volets ») et le nombre de demandes ;
- les ateliers des enfants arrêtés en cours : le nom de l'atelier, comment il s'est arrêté, le nombre de questions et d'étoiles. Jamais le prénom, la voix ni les réponses de l'enfant.

## Le rapport complet

Le rapport technique, plus vos conversations avec Jarvis : ce que vous avez demandé (comme Jarvis l'a compris, avec l'autre version entendue quand la reconnaissance vocale hésite), ce qu'il a répondu, et si la réponse est venue de Jarvis lui-même ou de Claude. Cela sert à améliorer la compréhension de Jarvis. Jamais pour un profil enfant ni en mode invité.

## Ce qui n'est jamais envoyé

- votre voix et vos enregistrements ;
- vos mots de passe, identifiants et codes ;
- vos mails, votre agenda, vos contacts, vos notes, votre mémoire Jarvis ;
- tout ce qui se passe en mode invité.

Avant l'envoi, les textes sont nettoyés : les prénoms des profils et des voix apprises, la ville, le département et les villes voisines, les adresses mail, les numéros de téléphone, les codes et les chemins de dossiers sont remplacés.

## Où vont les rapports, et combien de temps

Ils sont déposés dans un dossier Google Drive privé du créateur de Jarvis, qui est seul à les lire (avec l'aide de Claude pour les analyser). Ils sont effacés automatiquement au bout de 12 mois.

Les demandes faites sur les tablettes sont comptées comme celles du PC. Pour un profil enfant, ce qu'il dit n'est jamais envoyé : seulement le genre de demande, qui a répondu et le temps de réponse.

## Vos choix

Dans les réglages de Jarvis, rubrique **« Rapports »** :

- changer le niveau (rien, technique, complet) à tout moment ;
- couper le compteur anonyme ;
- **« Je veux tester les nouvelles versions en avance »** : vous recevez les versions d'essai avant tout le monde (votre numéro anonyme est alors marqué « testeur ») ;
- **« Voir ce qui partirait »** : le prochain rapport s'ouvre, tel qu'il serait envoyé ;
- **« Effacer mes données »** : tout ce qui a été envoyé depuis votre PC est supprimé sur le dépôt. Le numéro anonyme de votre PC reste le même : si vous gardez le compteur anonyme, le PC réapparaît au signal suivant ; coupez-le dans les réglages pour ne plus rien envoyer du tout.

Si l'envoi échoue (pas d'Internet), Jarvis réessaie trois fois, puis abandonne ce rapport : rien ne s'accumule sur votre PC, et Jarvis n'est jamais bloqué.

## Contact

Pour toute question ou demande (y compris l’effacement de vos données), ouvrez un ticket : https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio/issues
