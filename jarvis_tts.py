
import json
import os
import queue
import re
import sys
import time
import subprocess
import sounddevice as sd
from vosk import Model, KaldiRecognizer

MODEL_PATH = r"C:\Jarvis\vosk-model-small-fr-0.22"
SAMPLE_RATE = 16000

audio_queue = queue.Queue()


def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio :", status, file=sys.stderr)
    audio_queue.put(bytes(indata))


def speak(text):
    print("JARVIS :", text)

    powershell_script = """
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice = $speaker.GetInstalledVoices() |
    Where-Object { $_.VoiceInfo.Culture.Name -like 'fr-*' } |
    Select-Object -First 1

if ($voice) {
    $speaker.SelectVoice($voice.VoiceInfo.Name)
}

$speaker.Speak($env:JARVIS_TEXTE)
$speaker.Dispose()
"""

    # Le texte est transmis par une variable d'environnement :
    # il peut contenir des apostrophes ou des guillemets sans casser la commande.
    environnement = os.environ.copy()
    environnement["JARVIS_TEXTE"] = text

    try:
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                powershell_script
            ],
            check=True,
            env=environnement,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    except Exception as error:
        print("Erreur vocale :", error)


def main():
    print("Chargement du modèle français...")
    model = Model(MODEL_PATH)
    recognizer = KaldiRecognizer(model, SAMPLE_RATE)

    print("\nJARVIS EST EN ÉCOUTE PERMANENTE.")
    print("Dis simplement : Jarvis")
    print("Appuie sur Ctrl + C pour arrêter.\n")

    try:
        with sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=4000,
            device=None,
            dtype="int16",
            channels=1,
            callback=audio_callback
        ):
            while True:
                data = audio_queue.get()

                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    phrase = result.get("text", "").lower()

                    if phrase:
                        print("Entendu :", phrase)

                        if re.search(r"\bjarvis\b", phrase):
                            speak("Oui, je t'écoute")

                            recognizer.Reset()

                            time.sleep(0.3)

                            while not audio_queue.empty():
                                try:
                                    audio_queue.get_nowait()
                                except queue.Empty:
                                    break

    except KeyboardInterrupt:
        print("\nArrêt de Jarvis.")

    except Exception as error:
        print("\nErreur :", error)


if __name__ == "__main__":
    main()
