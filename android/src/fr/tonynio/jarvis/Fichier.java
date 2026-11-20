package fr.tonynio.jarvis;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;

import java.io.File;
import java.io.FileNotFoundException;

/**
 * Prête à l'installateur d'Android le fichier de la mise à jour que Jarvis vient de télécharger (un seul fichier,
 * en lecture seule, le temps de l'installation). Rien d'autre de l'application n'est accessible par ici.
 */
public class Fichier extends ContentProvider {
    static final String ADRESSE = "content://fr.tonynio.jarvis.maj/Jarvis-tablette.apk";
    static final String GENRE = "application/vnd.android.package-archive";

    static File fichier(android.content.Context contexte) {
        return new File(new File(contexte.getCacheDir(), "maj"), "Jarvis-tablette.apk");
    }

    @Override
    public boolean onCreate() {
        return true;
    }

    @Override
    public ParcelFileDescriptor openFile(Uri adresse, String mode) throws FileNotFoundException {
        if (!ADRESSE.equals(adresse.toString()) || !"r".equals(mode)) {
            throw new FileNotFoundException();
        }
        return ParcelFileDescriptor.open(fichier(getContext()), ParcelFileDescriptor.MODE_READ_ONLY);
    }

    @Override
    public Cursor query(Uri adresse, String[] colonnes, String choix, String[] valeurs, String ordre) {
        if (colonnes == null) {
            colonnes = new String[]{OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE};
        }
        MatrixCursor resultat = new MatrixCursor(colonnes, 1);
        Object[] ligne = new Object[colonnes.length];
        for (int i = 0; i < colonnes.length; i++) {
            if (OpenableColumns.DISPLAY_NAME.equals(colonnes[i])) {
                ligne[i] = "Jarvis-tablette.apk";
            } else if (OpenableColumns.SIZE.equals(colonnes[i])) {
                ligne[i] = fichier(getContext()).length();
            }
        }
        resultat.addRow(ligne);
        return resultat;
    }

    @Override
    public String getType(Uri adresse) {
        return GENRE;
    }

    @Override
    public Uri insert(Uri adresse, ContentValues valeurs) {
        return null;
    }

    @Override
    public int delete(Uri adresse, String choix, String[] valeurs) {
        return 0;
    }

    @Override
    public int update(Uri adresse, ContentValues valeurs, String choix, String[] valeurs2) {
        return 0;
    }
}
