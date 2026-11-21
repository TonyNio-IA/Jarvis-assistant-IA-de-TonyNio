package fr.tonynio.jarvis;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.Typeface;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.AudioFormat;
import android.media.AudioRecord;
import android.media.AudioTrack;
import android.media.MediaRecorder;
import android.net.Uri;
import android.net.http.SslCertificate;
import android.net.http.SslError;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.InputType;
import android.util.Base64;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.PermissionRequest;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.security.MessageDigest;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.HashSet;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.net.ssl.HostnameVerifier;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

/**
 * Jarvis sur la tablette.
 *
 * L'application est une fenêtre sur la page servie par le Jarvis du PC (jarvis_tablette.py) : le rond, les profils,
 * les couleurs et les réglages sont dans cette page. L'application y ajoute ce qu'un navigateur ne peut pas faire :
 * ouvrir une application de la tablette, se mettre à jour, et un écran clair quand le PC ne répond pas.
 *
 * Elle ne parle qu'à un seul PC : celui auquel elle a été reliée (adresse, clé secrète et empreinte de sa clé
 * publique, gardées dans la tablette). Elle ne contient elle-même ni adresse, ni clé, ni information personnelle.
 */
public class MainActivity extends Activity {
    private static final int FOND = 0xFF05090E, ACCENT = 0xFFFF2E97, TEXTE = 0xFFE8F4FF, GRIS = 0xFF9FB4C8, CASE = 0xFF0B131D;
    private static final Pattern HOTE = Pattern.compile("[0-9A-Za-z.\\-]{1,80}(:\\d{1,5})?");
    private static final Pattern CLE = Pattern.compile("[\\w\\-]{16,128}");
    private static final Pattern EMPREINTE = Pattern.compile("[0-9a-fA-F]{64}");
    private static final Pattern LIEN = Pattern.compile("https://([0-9A-Za-z.\\-]{1,80}(?::\\d{1,5})?)/?#cle=([\\w\\-]{16,128})");
    private static final int ESSAI_TOUTES_LES = 8000, ATTENTE_MAX = 12000;

    private SharedPreferences reglages;
    private WebView vue;
    private LinearLayout ecran;
    private TextView titre, message;
    private EditText champ;
    private Button bouton, second;
    private final Handler mains = new Handler(Looper.getMainLooper());
    private PermissionRequest demandeMicro;
    private boolean enErreur, horsLigne, mauvaisPc, visible;
    private Ecoute ecouteur;                 // le fil qui écoute le micro (null quand le micro est rendu)
    private volatile boolean veille;         // écoute permanente demandée par la page (« Jarvis, ... »)
    private volatile boolean attentif = true; // faux pendant que Jarvis réfléchit ou parle : le micro reste ouvert, rien n'est retenu
    private volatile long attentifDepuis;
    private volatile boolean direct;         // on a touché le rond : la prochaine phrase est une demande
    private volatile int ordre;              // 1 : finir la phrase en cours et l'envoyer ; 2 : l'abandonner
    private volatile long debutDirect;
    private volatile boolean majEnCours;
    // Réglages du micro, donnés par le PC (tablette.json) : ils s'ajustent sans refaire l'application
    private volatile int sourceMicro = MediaRecorder.AudioSource.CAMCORDER;   // la source qui donne la voix la plus nette (mesuré)
    private volatile double facteurVoix = 4, seuilMini = 0.004;
    private volatile boolean bilans;         // pendant un réglage du micro : les niveaux mesurés sont envoyés au journal du PC
    private volatile int silenceVeille = 800, silenceRond = 1000;
    // Le mot « Jarvis » reconnu par la tablette elle-même (modèles pris sur le PC relié). Sans lui : le PC décide, phrase par phrase
    private volatile MotAppel detecteur;
    private volatile float seuilMot = 0.5f;
    private volatile boolean chargementMot;
    private volatile String empreinteMot = "";
    private volatile long echecMot;
    private volatile long sourdJusqua;       // pendant le bip de réveil : ce n'est pas une voix
    private volatile int volumeSons = 100;   // le volume réglé dans la page (0 à 100)
    private volatile boolean sonsCoupes;     // mode silencieux ou mode nuit : pas de bip
    private short[] sonReveil, sonFin, sonSonnerie;
    private volatile boolean parole;         // Jarvis parle : « Jarvis » lui coupe la parole (le reste n'est pas écouté)
    // Pendant qu'il parle, sa propre voix couvre la tienne : un seuil un peu plus haut qu'au repos (0,8 était trop exigeant)
    private static final float SEUIL_PAROLE = 0.7f;

    private final Runnable nouvelEssai = new Runnable() {
        @Override
        public void run() {
            if (horsLigne && visible && relie()) {
                charger(false);
            }
        }
    };

    private final Runnable tropLong = new Runnable() {
        @Override
        public void run() {
            if (!horsLigne && ecran.getVisibility() == View.VISIBLE && relie() && champ.getVisibility() != View.VISIBLE) {
                ecranHorsLigne();                             // le PC ne répond pas : on le dit, et on continue d'essayer
            }
        }
    };

    // ---------- Vie de l'application ----------

    @Override
    protected void onCreate(Bundle etat) {
        super.onCreate(etat);
        reglages = getSharedPreferences("jarvis", MODE_PRIVATE);
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        construire();
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED
                && !reglages.getBoolean("micro_demande", false)) {       // au premier lancement : le droit de parler à Jarvis
            reglages.edit().putBoolean("micro_demande", true).apply();
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 3);
        }
        if (!recevoirLien(getIntent())) {
            demarrer();
        }
    }

    @Override
    protected void onNewIntent(Intent intention) {
        super.onNewIntent(intention);
        setIntent(intention);
        recevoirLien(intention);
    }

    @Override
    protected void onResume() {
        super.onResume();
        visible = true;
        vue.onResume();
        reglerEcoute();
        if (horsLigne) {
            mains.removeCallbacks(nouvelEssai);
            mains.postDelayed(nouvelEssai, 500);
        }
    }

    @Override
    protected void onPause() {
        visible = false;
        direct = false;
        reglerEcoute();
        mains.removeCallbacks(nouvelEssai);
        vue.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        visible = false;
        reglerEcoute();
        mains.removeCallbacksAndMessages(null);
        vue.destroy();
        super.onDestroy();
    }

    // ---------- Ce qui est gardé : le PC auquel la tablette est reliée ----------

    private String hote() {
        return reglages.getString("hote", "");
    }

    private boolean relie() {
        return !hote().isEmpty() && !reglages.getString("cle", "").isEmpty();
    }

    private void garder(String hote, String cle, String empreinte) {
        reglages.edit().putString("hote", hote).putString("cle", cle)
                .putString("empreinte", empreinte == null ? "" : empreinte.toLowerCase()).apply();
    }

    /** Le lien « Ouvrir dans l'application » de la page de Jarvis : jarvis://relier?h=adresse&c=clé&e=empreinte */
    private boolean recevoirLien(Intent intention) {
        Uri lien = intention == null ? null : intention.getData();
        if (lien == null || !"jarvis".equals(lien.getScheme()) || !"relier".equals(lien.getHost())) {
            return false;
        }
        final String h = lien.getQueryParameter("h"), c = lien.getQueryParameter("c");
        final String e = lien.getQueryParameter("e") == null ? "" : lien.getQueryParameter("e");
        if (h == null || c == null || !HOTE.matcher(h).matches() || !CLE.matcher(c).matches()
                || !(e.isEmpty() || EMPREINTE.matcher(e).matches())) {
            Toast.makeText(this, "Ce lien n'est pas un lien de Jarvis.", Toast.LENGTH_LONG).show();
            return false;
        }
        if (relie() && !h.equals(hote())) {              // déjà reliée à un autre PC : on demande avant de changer
            new AlertDialog.Builder(this)
                    .setTitle("Relier à un autre Jarvis ?")
                    .setMessage("Cette tablette est déjà reliée à un Jarvis. Veux-tu la relier à celui-ci à la place ?")
                    .setNegativeButton("Non", null)
                    .setPositiveButton("Oui", (d, q) -> {
                        garder(h, c, e);
                        demarrer();
                    })
                    .show();
            if (vue.getUrl() == null) {
                demarrer();
            }
            return true;
        }
        garder(h, c, e);
        demarrer();
        return true;
    }

    private void demarrer() {
        if (relie()) {
            charger(true);
        } else {
            ecranRelier("");
        }
    }

    private void charger(boolean annoncer) {
        mains.removeCallbacks(nouvelEssai);
        mauvaisPc = false;
        if (annoncer) {
            horsLigne = false;
            montrer("Jarvis", "Connexion à Jarvis…", null, null, null, null, false);
            mains.removeCallbacks(tropLong);
            mains.postDelayed(tropLong, ATTENTE_MAX);
        }
        vue.loadUrl("https://" + hote() + "/#cle=" + reglages.getString("cle", ""));
    }

    // ---------- Écrans de l'application (quand la page de Jarvis n'est pas là) ----------

    private int dp(int valeur) {
        return Math.round(valeur * getResources().getDisplayMetrics().density);
    }

    private Button fabriquerBouton(boolean plein) {
        Button b = new Button(this);
        b.setAllCaps(false);
        b.setTextSize(17);
        b.setTextColor(plein ? FOND : GRIS);
        b.setBackgroundColor(plein ? ACCENT : CASE);
        b.setTypeface(Typeface.DEFAULT, plein ? Typeface.BOLD : Typeface.NORMAL);
        LinearLayout.LayoutParams place = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(54));
        place.topMargin = dp(14);
        b.setLayoutParams(place);
        return b;
    }

    private void construire() {
        FrameLayout racine = new FrameLayout(this);
        racine.setBackgroundColor(FOND);

        vue = new WebView(this);
        vue.setBackgroundColor(FOND);
        WebSettings s = vue.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);       // Jarvis répond à voix haute sans qu'on touche l'écran
        s.setSupportZoom(false);
        s.setTextZoom(100);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        vue.setWebViewClient(new Navigation());
        vue.setWebChromeClient(new Droits());
        vue.addJavascriptInterface(new Pont(), "JarvisApp");
        racine.addView(vue, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));

        ecran = new LinearLayout(this);
        ecran.setOrientation(LinearLayout.VERTICAL);
        ecran.setGravity(Gravity.CENTER);
        ecran.setBackgroundColor(FOND);
        ecran.setClickable(true);
        ecran.setPadding(dp(28), dp(28), dp(28), dp(28));

        LinearLayout colonne = new LinearLayout(this);
        colonne.setOrientation(LinearLayout.VERTICAL);
        colonne.setGravity(Gravity.CENTER_HORIZONTAL);

        titre = new TextView(this);
        titre.setTextSize(24);
        titre.setTextColor(ACCENT);
        titre.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        titre.setGravity(Gravity.CENTER);
        colonne.addView(titre);

        message = new TextView(this);
        message.setTextSize(17);
        message.setTextColor(TEXTE);
        message.setLineSpacing(dp(4), 1f);
        message.setGravity(Gravity.CENTER);
        message.setPadding(0, dp(18), 0, dp(8));
        colonne.addView(message);

        champ = new EditText(this);
        champ.setHint("Ou colle ici le lien de Jarvis");
        champ.setHintTextColor(0xFF7D93A8);
        champ.setTextColor(TEXTE);
        champ.setTextSize(16);
        champ.setSingleLine(true);
        champ.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        colonne.addView(champ, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        bouton = fabriquerBouton(true);
        colonne.addView(bouton);
        second = fabriquerBouton(false);
        colonne.addView(second);

        ecran.addView(colonne, new LinearLayout.LayoutParams(Math.min(dp(480), getResources().getDisplayMetrics().widthPixels - dp(56)),
                ViewGroup.LayoutParams.WRAP_CONTENT));
        racine.addView(ecran, new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(racine);
    }

    private void montrer(String grand, String texte, String nom1, final Runnable action1, String nom2, final Runnable action2,
                         boolean avecChamp) {
        titre.setText(grand);
        message.setText(texte);
        champ.setVisibility(avecChamp ? View.VISIBLE : View.GONE);
        bouton.setVisibility(nom1 == null ? View.GONE : View.VISIBLE);
        second.setVisibility(nom2 == null ? View.GONE : View.VISIBLE);
        bouton.setText(nom1);
        second.setText(nom2);
        bouton.setOnClickListener(action1 == null ? null : v -> action1.run());
        second.setOnClickListener(action2 == null ? null : v -> action2.run());
        ecran.setVisibility(View.VISIBLE);
    }

    private void ecranRelier(String remarque) {
        horsLigne = false;
        mains.removeCallbacks(nouvelEssai);
        montrer("Relier cette tablette à Jarvis",
                (remarque.isEmpty() ? "" : remarque + "\n\n")
                        + "1. Sur l'ordinateur, dis « Jarvis, montre le QR code de la tablette ».\n\n"
                        + "2. Vise le QR code avec l'appareil photo de la tablette, ouvre le lien et accepte l'avertissement de sécurité.\n\n"
                        + "3. Dans la page qui s'ouvre, touche la roue des réglages, « Installer l'application », "
                        + "puis « Ouvrir dans l'application ».",
                "Relier avec le lien collé", () -> {
                    Matcher m = LIEN.matcher(champ.getText().toString().trim());
                    if (!m.matches()) {
                        Toast.makeText(this, "Ce n'est pas le lien de Jarvis (il commence par https:// et finit par la clé).",
                                Toast.LENGTH_LONG).show();
                        return;
                    }
                    garder(m.group(1), m.group(2), "");
                    champ.setText("");
                    demarrer();
                },
                relie() ? "Annuler" : null, relie() ? () -> charger(true) : null, true);
    }

    private void ecranHorsLigne() {
        horsLigne = true;
        if (mauvaisPc) {
            montrer("Ce n'est pas le bon Jarvis",
                    "L'ordinateur qui répond à cette adresse n'est pas celui auquel la tablette est reliée. "
                            + "Si Jarvis a été réinstallé, relie de nouveau la tablette avec le QR code.",
                    "Réessayer", () -> charger(true), "Relier de nouveau", () -> ecranRelier(""), false);
            return;
        }
        montrer("Je n'arrive pas à joindre Jarvis",
                "Vérifie que l'ordinateur est allumé, que Jarvis tourne, et que la tablette est sur le Wi-Fi de la maison "
                        + "(ou reliée par le VPN).\n\nJe réessaie tout seul.",
                "Réessayer", () -> charger(true), "Relier de nouveau", () -> ecranRelier(""), false);
        mains.removeCallbacks(nouvelEssai);
        if (visible) {
            mains.postDelayed(nouvelEssai, ESSAI_TOUTES_LES);
        }
    }

    // ---------- La page de Jarvis ----------

    private static String hexa(byte[] octets) {
        StringBuilder texte = new StringBuilder();
        for (byte o : octets) {
            texte.append(String.format("%02x", o & 0xFF));
        }
        return texte.toString();
    }

    private static String empreinte(X509Certificate certificat) throws Exception {
        return hexa(MessageDigest.getInstance("SHA-256").digest(certificat.getPublicKey().getEncoded()));
    }

    /** L'empreinte de la clé publique présentée par le PC (null si elle est illisible). */
    private static String empreinte(SslCertificate certificat) {
        try {
            X509Certificate x509 = null;
            if (Build.VERSION.SDK_INT >= 29) {
                x509 = certificat.getX509Certificate();
            }
            if (x509 == null) {
                byte[] octets = SslCertificate.saveState(certificat).getByteArray("x509-certificate");
                if (octets == null) {
                    return null;
                }
                x509 = (X509Certificate) CertificateFactory.getInstance("X.509").generateCertificate(new ByteArrayInputStream(octets));
            }
            return empreinte(x509);
        } catch (Exception erreur) {
            return null;
        }
    }

    private class Navigation extends WebViewClient {
        @Override
        public void onPageStarted(WebView v, String adresse, android.graphics.Bitmap icone) {
            enErreur = false;
        }

        @Override
        public void onPageFinished(WebView v, String adresse) {
            if (!enErreur && adresse != null && adresse.startsWith("https://")) {
                horsLigne = false;
                mains.removeCallbacks(nouvelEssai);
                mains.removeCallbacks(tropLong);
                ecran.setVisibility(View.GONE);
            }
        }

        @Override
        public void onReceivedError(WebView v, WebResourceRequest demande, WebResourceError erreur) {
            if (demande.isForMainFrame()) {
                enErreur = true;
                ecranHorsLigne();
            }
        }

        /** Le certificat de Jarvis est fabriqué par lui : on l'accepte seulement si c'est bien la clé du PC relié. */
        @Override
        public void onReceivedSslError(WebView v, SslErrorHandler suite, SslError erreur) {
            String attendue = reglages.getString("empreinte", "");
            String recue = empreinte(erreur.getCertificate());
            Uri adresse = Uri.parse(erreur.getUrl() == null ? "" : erreur.getUrl());
            if (recue != null && hote().equals(adresse.getAuthority())) {
                if (attendue.isEmpty()) {                     // reliée par un lien collé : la première clé vue est gardée
                    reglages.edit().putString("empreinte", recue).apply();
                    suite.proceed();
                    return;
                }
                if (attendue.equalsIgnoreCase(recue)) {
                    suite.proceed();
                    return;
                }
                mauvaisPc = true;
            }
            suite.cancel();
            enErreur = true;
            mains.post(MainActivity.this::ecranHorsLigne);
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest demande) {
            Uri adresse = demande.getUrl();
            if ("https".equals(adresse.getScheme()) && hote().equals(adresse.getAuthority())) {
                return false;                                 // la page de Jarvis, et elle seule, s'ouvre ici
            }
            ouvrirDehors(adresse.toString());
            return true;
        }
    }

    private class Droits extends WebChromeClient {
        @Override
        public void onPermissionRequest(final PermissionRequest demande) {
            runOnUiThread(() -> {
                boolean micro = false;
                for (String quoi : demande.getResources()) {
                    micro |= PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(quoi);
                }
                Uri origine = demande.getOrigin();
                if (!micro || origine == null || !hote().equals(origine.getAuthority())) {
                    demande.deny();
                } else if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    demande.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                } else {
                    demandeMicro = demande;
                    requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 1);
                }
            });
        }
    }

    @Override
    public void onRequestPermissionsResult(int numero, String[] droits, int[] reponses) {
        super.onRequestPermissionsResult(numero, droits, reponses);
        boolean accorde = reponses.length > 0 && reponses[0] == PackageManager.PERMISSION_GRANTED;
        if (numero == 2) {                                    // demandé au moment de parler : on écoute, ou on le dit
            if (accorde) {
                ecouter();
            } else {
                vue.evaluateJavascript("window.jarvisMicro&&window.jarvisMicro('refus')", null);
            }
            return;
        }
        if (numero == 3) {                                    // demandé au lancement : l'écoute permanente peut commencer
            reglerEcoute();
            return;
        }
        PermissionRequest demande = demandeMicro;
        demandeMicro = null;
        if (numero != 1 || demande == null) {
            return;
        }
        if (reponses.length > 0 && reponses[0] == PackageManager.PERMISSION_GRANTED) {
            demande.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
        } else {
            demande.deny();
        }
    }

    private void ouvrirDehors(String adresse) {
        try {
            Uri lien = Uri.parse(adresse);
            if ("http".equals(lien.getScheme()) || "https".equals(lien.getScheme())) {
                startActivity(new Intent(Intent.ACTION_VIEW, lien).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            }
        } catch (Exception erreur) {
            Toast.makeText(this, "Je n'ai pas pu ouvrir le navigateur.", Toast.LENGTH_LONG).show();
        }
    }

    // ---------- Le micro : l'application écoute elle-même et donne chaque phrase à la page ----------
    // Deux façons d'écouter : « direct » (on a touché le rond : la phrase qui suit est une demande) et « veille »
    // (écoute permanente tant que l'application est à l'écran : chaque phrase est donnée au PC, qui ne répond que
    // si elle contient « Jarvis »). Rien n'est gardé sur la tablette.

    private boolean microPermis() {
        return checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED;
    }

    /** Lance ou arrête le fil d'écoute selon ce qui est demandé. Jamais deux fils à la fois : le micro ne se partage pas,
     *  un nouveau fil n'est lancé qu'une fois le précédent terminé (il rappelle cette fonction en finissant). */
    private void reglerEcoute() {
        boolean besoin = visible && (veille || direct) && microPermis();
        if (ecouteur != null && ecouteur.fini) {
            ecouteur = null;
        }
        if (besoin && ecouteur == null) {
            ecouteur = new Ecoute();
            ecouteur.start();
        } else if (!besoin && ecouteur != null) {
            ecouteur.tourne = false;
        }
    }

    private void ecouter() {
        if (!microPermis()) {
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, 2);
            return;
        }
        ordre = 0;
        debutDirect = System.currentTimeMillis();
        sourdJusqua = debutDirect + DUREE_BIP;
        sonner(true);                                         // comme sur le PC : un bip, et Jarvis écoute
        direct = true;
        reglerEcoute();
    }

    // ---------- Les deux petits sons du PC : le bip de réveil (deux notes qui montent) et « j'ai entendu » (deux notes qui descendent) ----------

    // Le bip (0,22 s), le temps qu'Android le lance et son écho dans la pièce : pendant ce temps, le son est gardé
    // (le début d'une demande dite aussitôt n'est pas perdu) mais ne compte pas comme une voix
    private static final int DUREE_BIP = 450;

    private static short[] notes(double[][] partition, double volume, boolean eteint) {
        int total = 0;
        for (double[] note : partition) {
            total += (int) (44100 * note[1]);
        }
        short[] son = new short[total + 2205];                // un peu de silence à la fin : le son n'est pas coupé net
        int place = 0;
        for (double[] note : partition) {
            int nombre = (int) (44100 * note[1]);
            for (int i = 0; i < nombre; i++) {
                double t = i / 44100.0;
                double enveloppe = eteint ? Math.min(1, t / 0.005) * Math.exp(-t * 22)
                        : Math.min(1, Math.min(t / 0.008, (note[1] - t) / 0.03));
                son[place++] = (short) (32767 * volume * Math.sin(2 * Math.PI * note[0] * t) * enveloppe);
            }
        }
        return son;
    }

    private void sonner(boolean reveil) {
        if (sonsCoupes || volumeSons <= 0) {
            return;
        }
        jouer(reveil ? 0 : 1, volumeSons);
    }

    /** genre : 0 le bip de réveil, 1 « j'ai entendu », 2 la sonnerie d'un minuteur (elle sonne même en mode silencieux). */
    private void jouer(int genre, int volume) {
        try {
            if (sonReveil == null) {                          // les mêmes notes et le même volume que sur le PC
                sonReveil = notes(new double[][]{{880, 0.09}, {1320, 0.13}}, 0.4, false);
                sonFin = notes(new double[][]{{988, 0.05}, {659, 0.09}}, 0.4 * 0.56, true);
                sonSonnerie = notes(new double[][]{{1319, 0.13}, {1047, 0.13}, {1319, 0.13}, {1047, 0.13}, {1319, 0.13}, {1047, 0.2}}, 0.5, false);
            }
            short[] son = genre == 0 ? sonReveil : genre == 1 ? sonFin : sonSonnerie;
            final int volumeSons = volume;
            final AudioTrack piste = new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                    .setAudioFormat(new AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                            .setSampleRate(44100).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                    .setBufferSizeInBytes(son.length * 2).setTransferMode(AudioTrack.MODE_STATIC).build();
            piste.write(son, 0, son.length);
            piste.setVolume(Math.min(1f, volumeSons / 100f));
            piste.play();
            mains.postDelayed(piste::release, 600 + son.length / 44);
        } catch (Exception erreur) {
            // pas de son : l'animation du rond suffit
        }
    }

    // ---------- Le mot « Jarvis » : les modèles sont pris sur le PC relié, puis la tablette écoute seule ----------

    private HttpsURLConnection liaison(String chemin) throws Exception {
        HttpsURLConnection liaison = (HttpsURLConnection) new URL("https://" + hote() + chemin).openConnection();
        liaison.setSSLSocketFactory(liaisonSure());
        liaison.setHostnameVerifier(new HostnameVerifier() {
            @Override
            public boolean verify(String nom, SSLSession s) {
                return true;                                  // le PC est reconnu à sa clé (liaisonSure), pas à son nom
            }
        });
        liaison.setRequestProperty("X-Jarvis-Cle", reglages.getString("cle", ""));
        liaison.setConnectTimeout(10000);
        liaison.setReadTimeout(30000);
        return liaison;
    }

    private void recevoirFichier(String chemin, File fichier) throws Exception {
        File provisoire = new File(fichier.getPath() + ".recu");
        HttpsURLConnection liaison = liaison(chemin);
        try (InputStream entree = liaison.getInputStream(); OutputStream sortie = new FileOutputStream(provisoire)) {
            byte[] tampon = new byte[65536];
            int lus;
            while ((lus = entree.read(tampon)) > 0) {
                sortie.write(tampon, 0, lus);
            }
        }
        if (provisoire.length() < 1000 || !provisoire.renameTo(fichier)) {
            throw new java.io.IOException("fichier incomplet");
        }
    }

    /** voulue : l'empreinte des modèles du PC (vide : ce PC n'a pas de détecteur, la tablette fait sans). */
    private void preparerMot(final String voulue) {
        if (voulue.isEmpty()) {
            detecteur = null;
            empreinteMot = "";
            return;
        }
        if (chargementMot || (detecteur != null && voulue.equals(empreinteMot))
                || (voulue.equals(empreinteMot) && System.currentTimeMillis() - echecMot < 600000)) {
            return;                                           // déjà prêt, en cours, ou raté il y a moins de dix minutes
        }
        chargementMot = true;
        empreinteMot = voulue;
        new Thread(() -> {
            try {
                File dossier = new File(getFilesDir(), "mot_appel");
                boolean complet = voulue.equals(reglages.getString("mot_appel", ""));
                for (String nom : MotAppel.FICHIERS) {
                    complet &= new File(dossier, nom).length() > 1000;
                }
                if (!complet) {
                    dossier.mkdirs();
                    for (String nom : MotAppel.FICHIERS) {
                        recevoirFichier("/motappel/" + nom, new File(dossier, nom));
                    }
                    reglages.edit().putString("mot_appel", voulue).apply();
                }
                long debut = System.currentTimeMillis();
                detecteur = new MotAppel(dossier);            // l'ancien, s'il y en avait un, est laissé au ramasse-miettes
                echecMot = 0;
                noter("mot d'appel : détecteur prêt dans la tablette (" + (System.currentTimeMillis() - debut) + " ms)");
            } catch (Throwable erreur) {
                detecteur = null;
                echecMot = System.currentTimeMillis();
                reglages.edit().remove("mot_appel").apply();
                noter("mot d'appel : indisponible dans la tablette (" + erreur + ")");
            } finally {
                chargementMot = false;
            }
        }).start();
    }

    private void arreterEcoute(boolean envoyer) {
        if (direct) {
            ordre = envoyer ? 1 : 2;
        }
    }

    /** Une ligne pour le journal du PC (jamais ce qui est dit : seulement l'état du micro et des niveaux). */
    private void noter(final String texte) {
        mains.post(() -> vue.evaluateJavascript("window.jarvisNote&&window.jarvisNote(" + JSONObject.quote(texte) + ")", null));
    }

    private void donner(final byte[] pcm, final boolean demande) {
        String son = "";
        if (pcm != null && pcm.length > 0) {
            byte[] wav = new byte[44 + pcm.length];
            java.nio.ByteBuffer e = java.nio.ByteBuffer.wrap(wav).order(java.nio.ByteOrder.LITTLE_ENDIAN);
            e.put("RIFF".getBytes()).putInt(36 + pcm.length).put("WAVEfmt ".getBytes()).putInt(16).putShort((short) 1)
                    .putShort((short) 1).putInt(16000).putInt(32000).putShort((short) 2).putShort((short) 16)
                    .put("data".getBytes()).putInt(pcm.length).put(pcm);
            son = Base64.encodeToString(wav, Base64.NO_WRAP);
        }
        final String texte = "window.jarvisSon&&window.jarvisSon('" + son + "','audio/wav'," + demande + ")";
        mains.post(() -> vue.evaluateJavascript(texte, null));
    }

    private class Ecoute extends Thread {
        volatile boolean tourne = true, fini;
        private boolean panne;
        private android.media.audiofx.AcousticEchoCanceler antiEcho;

        @Override
        public void run() {
            AudioRecord micro = null;
            try {
                int taille = Math.max(AudioRecord.getMinBufferSize(16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT), 32000);
                micro = new AudioRecord(sourceMicro, 16000, AudioFormat.CHANNEL_IN_MONO,
                        AudioFormat.ENCODING_PCM_16BIT, taille);
                String gain = "sans réglage du gain";
                try {                                                        // la tablette règle elle-même le volume du micro, si elle sait le faire
                    if (android.media.audiofx.AutomaticGainControl.isAvailable()) {
                        android.media.audiofx.AutomaticGainControl reglage = android.media.audiofx.AutomaticGainControl.create(micro.getAudioSessionId());
                        if (reglage != null) {
                            reglage.setEnabled(true);
                            gain = "gain automatique " + (reglage.getEnabled() ? "activé" : "refusé");
                        }
                    }
                } catch (Exception erreur) {
                    gain = "gain automatique impossible";
                }
                try {                                                        // l'anti-écho retire du micro la voix de Jarvis lui-même :
                    if (android.media.audiofx.AcousticEchoCanceler.isAvailable()) {   // on l'entend mieux dire « Jarvis » pendant qu'il parle
                        antiEcho = android.media.audiofx.AcousticEchoCanceler.create(micro.getAudioSessionId());
                        if (antiEcho != null) {
                            antiEcho.setEnabled(true);
                            gain += ", anti-écho " + (antiEcho.getEnabled() ? "activé" : "refusé");
                        }
                    } else {
                        gain += ", pas d'anti-écho";
                    }
                } catch (Exception erreur) {
                    gain += ", anti-écho impossible";
                }
                micro.startRecording();
                noter(gain);
                noter("micro ouvert (source " + sourceMicro + ", état " + micro.getState() + ", enregistrement " + micro.getRecordingState() + ")");
                double plusFort = 0;
                long dernierBilan = System.currentTimeMillis();
                int envoyees = 0;
                short[] bloc = new short[1280];                              // 80 millièmes de seconde
                java.util.ArrayDeque<byte[]> avant = new java.util.ArrayDeque<>();   // la demi-seconde d'avant la voix
                java.io.ByteArrayOutputStream phrase = null;
                double plancher = -1;
                int deSuite = 0;
                long dernierSon = 0, debutPhrase = 0, voixCumulee = 0;
                boolean etaitDirect = false;
                MotAppel motVu = null;                                       // le détecteur de « Jarvis » en service
                boolean motPret = false, tempsDit = false;
                long tempsMot = 0;
                int blocsMot = 0;
                float noteHaute = 0;
                long dernierBruit = 0;
                boolean enCoupure = false;
                float noteParole = 0;
                java.util.ArrayDeque<short[]> calme = new java.util.ArrayDeque<>();   // le son d'avant le premier bruit
                while (tourne && (veille || direct)) {
                    int lus = micro.read(bloc, 0, bloc.length);
                    if (lus <= 0) {
                        continue;
                    }
                    double somme = 0;
                    byte[] octets = new byte[lus * 2];
                    for (int i = 0; i < lus; i++) {
                        double v = bloc[i] / 32768.0;
                        somme += v * v;
                        octets[2 * i] = (byte) bloc[i];
                        octets[2 * i + 1] = (byte) (bloc[i] >> 8);
                    }
                    double niveau = Math.sqrt(somme / lus);
                    long maintenant = System.currentTimeMillis();
                    boolean enDirect = direct;
                    if (enDirect && !etaitDirect && phrase != null && voixCumulee < 400) {
                        phrase = null;                                       // on vient de toucher le rond : on repart de zéro
                    }
                    etaitDirect = enDirect;
                    boolean sourd = enDirect && maintenant < sourdJusqua;    // le bip de réveil sonne : ce n'est pas quelqu'un qui parle
                    if (enDirect) {
                        motPret = false;
                    }
                    if (phrase == null && (enDirect || attentif) && !sourd) {
                        plancher = plancher < 0 || niveau < plancher ? niveau : plancher * 0.98 + niveau * 0.02;   // bruit de la pièce
                    }
                    // le micro d'une tablette est faible : le seuil suit surtout le bruit de la pièce
                    double seuil = Math.max(seuilMini, plancher * facteurVoix);
                    boolean voix = niveau > seuil && !sourd;
                    plusFort = Math.max(plusFort, niveau);
                    if (maintenant - dernierBilan > 15000) {
                        if (bilans) noter(String.format(java.util.Locale.US, "micro : niveau le plus fort %.4f, bruit %.4f, seuil %.4f, phrases envoyées %d"
                                        + (motVu == null ? ", sans détecteur" : ", mot d'appel : note la plus haute %.2f, %.1f ms par bloc"),
                                plusFort, plancher, seuil, envoyees, noteHaute, blocsMot == 0 ? 0.0 : tempsMot / 1e6 / blocsMot));
                        plusFort = 0;
                        noteHaute = 0;
                        dernierBilan = maintenant;
                    }
                    if (enDirect) {
                        final double montre = Math.min(1.0, niveau * 8);
                        mains.post(() -> vue.evaluateJavascript("window.jarvisNiveau&&window.jarvisNiveau(" + montre + ")", null));
                    }
                    MotAppel mot = detecteur;
                    boolean coupure = parole && !attentif && mot != null;    // Jarvis parle : seul « Jarvis » est guetté, pour lui couper la parole
                    if (enCoupure && !coupure) {                             // fin de sa réponse : la note la plus haute, pour régler le seuil
                        noter(String.format(java.util.Locale.US, "mot d'appel pendant la réponse : note la plus haute %.2f (seuil %.2f)",
                                noteParole, Math.max(seuilMot, SEUIL_PAROLE)));
                    }
                    if (coupure && !enCoupure) {
                        noteParole = 0;
                    }
                    enCoupure = coupure;
                    if (!enDirect && !coupure && (!attentif || maintenant - attentifDepuis < 400)) {
                        phrase = null;                                       // Jarvis parle : on n'écoute pas sa propre voix
                        avant.clear();
                        deSuite = 0;
                        motPret = false;
                        calme.clear();
                        continue;
                    }
                    if (!enDirect && mot != null) {
                        // En veille, comme sur le PC : la tablette guette le mot « Jarvis » elle-même. Rien n'est gardé, rien n'est envoyé.
                        phrase = null;
                        avant.clear();
                        deSuite = 0;
                        // Pièce silencieuse : aucun calcul (la tablette chauffe moins, la batterie dure plus). Au premier bruit,
                        // le détecteur repart avec les 0,6 seconde d'avant, puis il suit tant qu'il y a du bruit
                        if (niveau > Math.max(seuilMini * 0.5, plancher * 2) || coupure) {
                            dernierBruit = maintenant;
                        }
                        if (maintenant - dernierBruit > 1500) {
                            motPret = false;
                            calme.addLast(java.util.Arrays.copyOf(bloc, lus));
                            if (calme.size() > 8) {
                                calme.removeFirst();
                            }
                            continue;
                        }
                        float note = 0;
                        try {
                            if (!motPret || mot != motVu) {
                                mot.reinitialiser();
                                motPret = true;
                                motVu = mot;
                                for (short[] ancien : calme) {
                                    mot.ecouter(ancien, ancien.length);
                                }
                            }
                            calme.clear();
                            long depart = System.nanoTime();
                            note = mot.ecouter(bloc, lus);
                            tempsMot += System.nanoTime() - depart;
                            blocsMot++;
                        } catch (Throwable erreur) {
                            detecteur = null;                                // sans détecteur, le PC reprend la main
                            motVu = null;
                            noter("mot d'appel : en panne dans la tablette (" + erreur + ")");
                            continue;
                        }
                        noteHaute = Math.max(noteHaute, note);
                        if (coupure) {
                            noteParole = Math.max(noteParole, note);
                        }
                        if (!tempsDit && blocsMot >= 250) {                  // une fois, après 20 secondes : la tablette suit-elle le rythme ?
                            tempsDit = true;
                            noter(String.format(java.util.Locale.US, "mot d'appel : %.1f ms de calcul par bloc de 80 ms", tempsMot / 1e6 / blocsMot));
                        }
                        // pendant que Jarvis parle, le seuil est plus haut : sa propre voix ne doit pas le réveiller
                        if (note >= (coupure ? Math.max(seuilMot, SEUIL_PAROLE) : seuilMot) && veille) {    // on a dit « Jarvis » : le bip, et la demande est écoutée
                            motPret = false;
                            noter(String.format(java.util.Locale.US, "mot d'appel : réveil (note %.2f)", note));
                            ordre = 0;
                            debutDirect = maintenant;
                            sourdJusqua = maintenant + DUREE_BIP;
                            direct = true;
                            sonner(true);
                            mains.post(() -> vue.evaluateJavascript("window.jarvisReveil&&window.jarvisReveil()", null));
                        }
                        continue;
                    }
                    int recu = ordre;
                    if (enDirect && recu == 2) {                             // abandon : rien n'est envoyé
                        ordre = 0;
                        direct = false;
                        phrase = null;
                        continue;
                    }
                    if (phrase == null) {
                        avant.addLast(octets);
                        if (avant.size() > 10) {                             // 0,8 seconde : le début du mot « Jarvis » n'est pas coupé
                            avant.removeFirst();
                        }
                        deSuite = voix ? deSuite + 1 : 0;
                        if (deSuite >= 2) {                                  // quelqu'un parle : la phrase commence
                            phrase = new java.io.ByteArrayOutputStream();
                            for (byte[] morceau : avant) {
                                phrase.write(morceau, 0, morceau.length);
                            }
                            avant.clear();
                            debutPhrase = dernierSon = maintenant;
                            voixCumulee = 160;
                            deSuite = 0;
                        } else if (enDirect && (recu == 1 || maintenant - debutDirect > 7000)) {
                            ordre = 0;
                            direct = false;
                            noter(String.format(java.util.Locale.US, "demande au rond : aucune voix (niveau le plus fort %.4f, seuil %.4f)", plusFort, seuil));
                            donner(null, true);                              // rien n'a été dit
                        }
                        continue;
                    }
                    phrase.write(octets, 0, octets.length);
                    if (voix) {
                        dernierSon = maintenant;
                        voixCumulee += 80;
                    }
                    long silence = maintenant - dernierSon, duree = maintenant - debutPhrase;
                    if ((enDirect && recu == 1) || silence > (enDirect ? silenceRond : silenceVeille) || duree > (enDirect ? 20000 : 12000)) {
                        byte[] pcm = phrase.toByteArray();
                        phrase = null;
                        if (enDirect) {
                            if (voixCumulee < 300 && recu != 1 && maintenant - debutDirect < 7000) {
                                continue;                                    // un petit bruit, ou la fin du bip : la demande est toujours attendue
                            }
                            ordre = 0;
                            direct = false;
                            noter("demande : " + voixCumulee + " ms de voix, " + duree + " ms en tout");
                            if (voixCumulee >= 300) {
                                sonner(false);                               // « j'ai entendu », comme sur le PC
                            }
                            donner(voixCumulee >= 300 ? pcm : null, true);
                        } else if (voixCumulee >= 500 && veille) {           // un simple bruit n'est pas envoyé
                            envoyees++;
                            donner(pcm, false);
                        }
                    }
                }
            } catch (Exception erreur) {
                panne = true;
                noter("micro en panne : " + erreur);
                if (direct) {
                    direct = false;
                    mains.post(() -> vue.evaluateJavascript("window.jarvisMicro&&window.jarvisMicro('panne')", null));
                }
            } finally {
                if (micro != null) {
                    try {
                        micro.stop();
                    } catch (Exception erreur) {
                        // pas démarré
                    }
                    micro.release();                                         // le micro est rendu
                    if (antiEcho != null) {
                        antiEcho.release();
                    }
                }
                final boolean attendre = panne;
                mains.postDelayed(() -> {                                    // relancé si on en a encore besoin
                    fini = true;
                    reglerEcoute();
                }, attendre ? 5000 : 0);
            }
        }
    }

    // ---------- Ce que la page peut demander à l'application ----------

    private class Pont {
        /** Le numéro de cette application (comparé à celui que propose le PC). */
        @JavascriptInterface
        public String version() {
            try {
                return String.valueOf(getPackageManager().getPackageInfo(getPackageName(), 0).versionCode);
            } catch (Exception erreur) {
                return "0";
            }
        }

        /** Les trois couleurs du profil ouvert : le widget de l'écran d'accueil se redessine avec elles. */
        @JavascriptInterface
        public void couleurs(String c1, String c2, String c3) {
            String valeur = c1 + "," + c2 + "," + c3;
            if (valeur.equals(reglages.getString("couleurs_widget", ""))) return;
            reglages.edit().putString("couleurs_widget", valeur).apply();
            Widget.toutRedessiner(getApplicationContext());
        }

        /** Les applications que l'on peut lancer sur cette tablette : [{"nom", "paquet"}]. */
        @JavascriptInterface
        public String applis() {
            JSONArray liste = new JSONArray();
            try {
                PackageManager pm = getPackageManager();
                Intent lanceurs = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
                List<ResolveInfo> trouvees = pm.queryIntentActivities(lanceurs, 0);
                HashSet<String> vus = new HashSet<>();
                for (ResolveInfo info : trouvees) {
                    String paquet = info.activityInfo.packageName;
                    if (paquet.equals(getPackageName()) || !vus.add(paquet)) {
                        continue;
                    }
                    JSONObject appli = new JSONObject();
                    appli.put("nom", String.valueOf(info.loadLabel(pm)));
                    appli.put("paquet", paquet);
                    liste.put(appli);
                }
            } catch (Exception erreur) {
                // liste vide : Jarvis répondra qu'il ne trouve pas l'application
            }
            return liste.toString();
        }

        /** Écoute la demande avec le micro de la tablette ; la page reçoit le son par window.jarvisSon. */
        @JavascriptInterface
        public void ecouter() {
            runOnUiThread(MainActivity.this::ecouter);
        }

        @JavascriptInterface
        public void arreterEcoute(final boolean envoyer) {
            runOnUiThread(() -> MainActivity.this.arreterEcoute(envoyer));
        }

        /** Écoute permanente (« Jarvis, ... ») : la page la demande quand elle attend, et la coupe quand Jarvis répond. */
        @JavascriptInterface
        public void ecouteVeille(final boolean active) {
            runOnUiThread(() -> {
                veille = active;
                if (active) {                                 // l'écran reste allumé : écran éteint, Android ferme le micro
                    getWindow().addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                } else {
                    getWindow().clearFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
                }
                reglerEcoute();
            });
        }

        /** La page attend-elle une demande ? Sinon (Jarvis réfléchit ou parle), le micro reste ouvert mais rien n'est retenu. */
        @JavascriptInterface
        public void attentif(final boolean oui) {
            if (oui && !attentif) {
                attentifDepuis = System.currentTimeMillis();
            }
            attentif = oui;
        }

        /** Réglages du micro envoyés par le PC : {"source", "facteur", "seuil", "silence"}. */
        @JavascriptInterface
        public void reglerMicro(final String reglage) {
            runOnUiThread(() -> {
                try {
                    JSONObject r = new JSONObject(reglage);
                    int source = r.optInt("source", sourceMicro);
                    facteurVoix = Math.max(1.2, Math.min(20, r.optDouble("facteur", facteurVoix)));
                    seuilMini = Math.max(0.0001, Math.min(0.1, r.optDouble("seuil", seuilMini)));
                    silenceVeille = Math.max(400, Math.min(3000, r.optInt("silence", silenceVeille)));
                    silenceRond = Math.max(400, Math.min(3000, r.optInt("silence_rond", silenceRond)));
                    bilans = r.optBoolean("bilan", false);
                    JSONObject mot = r.optJSONObject("mot");                 // le détecteur de « Jarvis » du PC, s'il en a un
                    seuilMot = (float) Math.max(0.1, Math.min(0.99, mot == null ? 0.5 : mot.optDouble("seuil", 0.5)));
                    preparerMot(mot == null ? "" : mot.optString("empreinte", ""));
                    if (source != sourceMicro && source >= 0 && source <= 10) {
                        sourceMicro = source;
                        if (ecouteur != null) {               // le micro sera rouvert avec la nouvelle source
                            ecouteur.tourne = false;
                        }
                    }
                } catch (Exception erreur) {
                    // réglage illisible : on garde l'actuel
                }
            });
        }

        /** Le volume réglé dans la page (0 à 100), et les modes sans bip (silencieux, nuit). */
        @JavascriptInterface
        public void reglerSons(final int volume, final boolean coupes) {
            volumeSons = Math.max(0, Math.min(100, volume));
            sonsCoupes = coupes;
        }

        /** Jarvis parle-t-il ? Pendant sa réponse, dire « Jarvis » lui coupe la parole. */
        @JavascriptInterface
        public void parole(final boolean oui) {
            parole = oui;
        }

        /** La sonnerie d'un minuteur arrivé au bout. */
        @JavascriptInterface
        public void sonnerie() {
            jouer(2, Math.max(volumeSons, 50));
        }

        /** La batterie de la tablette : {"niveau": 0 à 100, "charge": branchée ?}. */
        @JavascriptInterface
        public String batterie() {
            try {
                Intent etat = registerReceiver(null, new android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED));
                int niveau = etat.getIntExtra(android.os.BatteryManager.EXTRA_LEVEL, -1);
                int echelle = etat.getIntExtra(android.os.BatteryManager.EXTRA_SCALE, 100);
                boolean charge = etat.getIntExtra(android.os.BatteryManager.EXTRA_PLUGGED, 0) != 0;
                return "{\"niveau\":" + (niveau < 0 ? -1 : Math.round(niveau * 100f / Math.max(1, echelle))) + ",\"charge\":" + charge + "}";
            } catch (Exception erreur) {
                return "{\"niveau\":-1,\"charge\":false}";
            }
        }

        /** Le mot « Jarvis » est-il reconnu par la tablette elle-même ? (« oui », « bientôt » pendant le chargement, « non ») */
        @JavascriptInterface
        public String motAppel() {
            return detecteur != null ? "oui" : chargementMot ? "bientôt" : "non";
        }

        /** Le droit d'utiliser le micro est-il accordé ? */
        @JavascriptInterface
        public String micro() {
            return microPermis() ? "permis" : "pas permis";
        }

        /** Le nom de cette version de l'application (1.01, 1.02...). */
        @JavascriptInterface
        public String nom() {
            try {
                return getPackageManager().getPackageInfo(getPackageName(), 0).versionName;
            } catch (Exception erreur) {
                return "";
            }
        }

        @JavascriptInterface
        public void ouvrir(final String paquet) {
            runOnUiThread(() -> {
                try {
                    Intent lancement = getPackageManager().getLaunchIntentForPackage(paquet);
                    if (lancement != null) {
                        startActivity(lancement);
                        return;
                    }
                } catch (Exception erreur) {
                    // message ci-dessous
                }
                Toast.makeText(MainActivity.this, "Je n'ai pas pu ouvrir cette application.", Toast.LENGTH_LONG).show();
            });
        }

        @JavascriptInterface
        public void lien(final String adresse) {
            runOnUiThread(() -> ouvrirDehors(adresse));
        }

        @JavascriptInterface
        public void mettreAJour() {
            runOnUiThread(MainActivity.this::mettreAJour);
        }

        @JavascriptInterface
        public void desinstaller() {
            runOnUiThread(() -> {
                try {
                    startActivity(new Intent(Intent.ACTION_DELETE, Uri.parse("package:" + getPackageName())));
                } catch (Exception erreur) {
                    startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS, Uri.parse("package:" + getPackageName())));
                }
            });
        }

        /** La clé de cette tablette n'est plus acceptée par le PC : on repart de l'écran « relier ». */
        @JavascriptInterface
        public void oublier() {
            runOnUiThread(() -> ecranRelier("Cette tablette n'est plus reliée à Jarvis."));
        }
    }

    // ---------- Mise à jour : la nouvelle application est prise sur le PC relié, Android demande de confirmer ----------

    private void annoncer(final String texte) {
        runOnUiThread(() -> vue.evaluateJavascript("window.jarvisMaj&&window.jarvisMaj(" + JSONObject.quote(texte) + ")", null));
    }

    /** Ce qui n'a pas marché est affiché dans la roue et envoyé au journal du PC. */
    private void signaler(final String affiche, final String detail) {
        annoncer(affiche);
        runOnUiThread(() -> vue.evaluateJavascript(
                "window.jarvisNote&&window.jarvisNote(" + JSONObject.quote("mise à jour, " + affiche + ", " + detail) + ")", null));
    }

    private SSLSocketFactory liaisonSure() throws Exception {
        final String attendue = reglages.getString("empreinte", "");
        TrustManager gardien = new X509TrustManager() {
            @Override
            public void checkClientTrusted(X509Certificate[] chaine, String genre) throws CertificateException {
                throw new CertificateException("refusé");
            }

            @Override
            public void checkServerTrusted(X509Certificate[] chaine, String genre) throws CertificateException {
                try {
                    if (chaine != null && chaine.length > 0 && !attendue.isEmpty()
                            && attendue.equalsIgnoreCase(empreinte(chaine[0]))) {
                        return;                               // c'est bien la clé du PC relié
                    }
                } catch (Exception erreur) {
                    // refus ci-dessous
                }
                throw new CertificateException("ce n'est pas le Jarvis relié");
            }

            @Override
            public X509Certificate[] getAcceptedIssuers() {
                return new X509Certificate[0];
            }
        };
        SSLContext contexte = SSLContext.getInstance("TLS");
        contexte.init(null, new TrustManager[]{gardien}, null);
        return contexte.getSocketFactory();
    }

    private void mettreAJour() {
        if (!getPackageManager().canRequestPackageInstalls()) {
            annoncer("Autorise Jarvis, puis recommence");
            Toast.makeText(this, "Autorise Jarvis à installer sa mise à jour, puis reviens et touche de nouveau « Mise à jour ».",
                    Toast.LENGTH_LONG).show();
            try {
                startActivity(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:" + getPackageName())));
            } catch (Exception erreur) {
                // l'écran n'existe pas sur cette tablette : rien de plus à faire
            }
            return;
        }
        if (majEnCours) {
            return;                                           // un seul téléchargement à la fois
        }
        majEnCours = true;
        annoncer("Téléchargement…");
        final String adresse = "https://" + hote() + "/jarvis.apk";
        new Thread(() -> {
            try {
                HttpsURLConnection liaison = (HttpsURLConnection) new URL(adresse).openConnection();
                liaison.setSSLSocketFactory(liaisonSure());
                liaison.setHostnameVerifier(new HostnameVerifier() {
                    @Override
                    public boolean verify(String nom, SSLSession s) {
                        return true;                          // le PC est reconnu à sa clé (ci-dessus), pas à son nom
                    }
                });
                liaison.setConnectTimeout(10000);
                liaison.setReadTimeout(30000);
                File recu = Fichier.fichier(this);
                recu.getParentFile().mkdirs();
                try (InputStream entree = liaison.getInputStream(); OutputStream sortie = new FileOutputStream(recu)) {
                    byte[] tampon = new byte[65536];
                    int lus;
                    while ((lus = entree.read(tampon)) > 0) {
                        sortie.write(tampon, 0, lus);
                    }
                }
                // l'installateur d'Android prend la suite, comme pour un fichier téléchargé : il demande de confirmer
                final Intent installer = new Intent(Intent.ACTION_VIEW)
                        .setDataAndType(Uri.parse(Fichier.ADRESSE), Fichier.GENRE)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                runOnUiThread(() -> {
                    majEnCours = false;
                    try {
                        startActivity(installer);
                        annoncer("Confirme dans la fenêtre d'Android");
                    } catch (Exception erreur) {
                        signaler("Android n'a pas ouvert l'installation", String.valueOf(erreur));
                    }
                });
            } catch (Exception erreur) {
                majEnCours = false;
                signaler("Le téléchargement a échoué", String.valueOf(erreur));
            }
        }).start();
    }
}
