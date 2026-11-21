package fr.tonynio.jarvis;

import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtSession;
import ai.onnxruntime.TensorInfo;

import java.io.File;
import java.nio.FloatBuffer;
import java.util.Collections;
import java.util.Random;

/**
 * Le détecteur du mot « Jarvis », dans la tablette : elle reconnaît le mot elle-même, sans rien envoyer au PC.
 *
 * C'est le même calcul que sur le PC (jarvis_motappel.py, repris d'openWakeWord, licence Apache 2.0) : toutes les
 * 80 millièmes de seconde, le son passe dans trois modèles (spectrogramme, traits, mot) et il en sort une note de 0 à 1.
 * Les trois modèles ne sont pas dans l'application : la tablette les prend sur le PC auquel elle est reliée.
 */
final class MotAppel implements AutoCloseable {
    static final int BLOC = 1280;                    // 80 ms à 16 kHz : la cadence du modèle
    static final String[] FICHIERS = {"melspectrogram.onnx", "embedding_model.onnx", "jarvis.onnx"};
    private static final int LIGNES = 76, BANDES = 32, TRAITS = 96, RECOUVREMENT = 480;

    private final OrtEnvironment env = OrtEnvironment.getEnvironment();
    private final OrtSession mel, emb, mot;
    private final String entreeMot;
    private final int trames;
    private final float[] depart;                    // les traits d'un bruit de fond, comme openWakeWord au démarrage
    private final float[] spectre = new float[LIGNES * BANDES];
    private final float[] traits;
    private final float[] son = new float[RECOUVREMENT + BLOC];
    private final short[] attente = new short[BLOC];
    private int enAttente, notes;

    MotAppel(File dossier) throws Exception {
        OrtSession.SessionOptions options = new OrtSession.SessionOptions();
        options.setInterOpNumThreads(1);
        options.setIntraOpNumThreads(1);
        mel = env.createSession(new File(dossier, FICHIERS[0]).getPath(), options);
        emb = env.createSession(new File(dossier, FICHIERS[1]).getPath(), options);
        mot = env.createSession(new File(dossier, FICHIERS[2]).getPath(), options);
        entreeMot = mot.getInputNames().iterator().next();
        long[] forme = ((TensorInfo) mot.getInputInfo().get(entreeMot).getInfo()).getShape();
        trames = forme.length > 1 && forme[1] > 0 ? (int) forme[1] : 16;
        traits = new float[trames * TRAITS];
        depart = new float[trames * TRAITS];
        Random hasard = new Random(0);
        float[] bruit = new float[16000 * 4];
        for (int i = 0; i < bruit.length; i++) {
            bruit[i] = hasard.nextInt(2000) - 1000;
        }
        float[] image = spectrogramme(bruit);
        int lignes = image.length / BANDES, fenetres = 0;
        float[] fenetre = new float[LIGNES * BANDES];
        for (int i = 0; i + LIGNES <= lignes; i += 8) {
            fenetres++;
        }
        int rang = 0;
        for (int i = 0; i + LIGNES <= lignes; i += 8, rang++) {
            if (rang < fenetres - trames) {
                continue;                             // seules les dernières servent
            }
            System.arraycopy(image, i * BANDES, fenetre, 0, fenetre.length);
            System.arraycopy(depart, TRAITS, depart, 0, depart.length - TRAITS);
            System.arraycopy(trait(fenetre), 0, depart, depart.length - TRAITS, TRAITS);
        }
        reinitialiser();
    }

    /** Repart de zéro : rien de ce qui a été entendu avant ne compte plus. */
    void reinitialiser() {
        java.util.Arrays.fill(son, 0f);
        java.util.Arrays.fill(spectre, 1f);
        System.arraycopy(depart, 0, traits, 0, depart.length);
        enAttente = 0;
        notes = 0;                                    // les 5 premières notes valent 0
    }

    private float[] sortie(OrtSession modele, String entree, float[] valeurs, long[] forme) throws Exception {
        try (OnnxTensor tenseur = OnnxTensor.createTensor(env, FloatBuffer.wrap(valeurs), forme);
             OrtSession.Result resultat = modele.run(Collections.singletonMap(entree, tenseur))) {
            FloatBuffer lu = ((OnnxTensor) resultat.get(0)).getFloatBuffer();
            float[] recu = new float[lu.remaining()];
            lu.get(recu);
            return recu;
        }
    }

    private float[] spectrogramme(float[] echantillons) throws Exception {
        float[] image = sortie(mel, "input", echantillons, new long[]{1, echantillons.length});
        for (int i = 0; i < image.length; i++) {
            image[i] = image[i] / 10f + 2f;
        }
        return image;
    }

    private float[] trait(float[] fenetre) throws Exception {
        return sortie(emb, "input_1", fenetre, new long[]{1, LIGNES, BANDES, 1});
    }

    /** Du son du micro (16 kHz, 16 bits). Renvoie la meilleure note des blocs de 80 ms terminés (0 s'il n'y en a pas). */
    float ecouter(short[] echantillons, int nombre) throws Exception {
        float meilleure = 0f;
        int lu = 0;
        while (lu < nombre) {
            int pris = Math.min(BLOC - enAttente, nombre - lu);
            System.arraycopy(echantillons, lu, attente, enAttente, pris);
            enAttente += pris;
            lu += pris;
            if (enAttente == BLOC) {
                enAttente = 0;
                meilleure = Math.max(meilleure, bloc());
            }
        }
        return meilleure;
    }

    private float bloc() throws Exception {
        System.arraycopy(son, BLOC, son, 0, RECOUVREMENT);          // la fin du bloc d'avant, pour le spectrogramme
        for (int i = 0; i < BLOC; i++) {
            son[RECOUVREMENT + i] = attente[i];
        }
        float[] image = spectrogramme(son.clone());
        int recu = Math.min(image.length, spectre.length);
        System.arraycopy(spectre, recu, spectre, 0, spectre.length - recu);
        System.arraycopy(image, image.length - recu, spectre, spectre.length - recu, recu);
        float[] nouveau = trait(spectre.clone());
        System.arraycopy(traits, TRAITS, traits, 0, traits.length - TRAITS);
        System.arraycopy(nouveau, 0, traits, traits.length - TRAITS, TRAITS);
        float note = sortie(mot, entreeMot, traits.clone(), new long[]{1, trames, TRAITS})[0];
        notes++;
        return notes <= 5 ? 0f : note;
    }

    @Override
    public void close() {
        try {
            mel.close();
            emb.close();
            mot.close();
        } catch (Exception erreur) {
            // déjà fermé
        }
    }
}
