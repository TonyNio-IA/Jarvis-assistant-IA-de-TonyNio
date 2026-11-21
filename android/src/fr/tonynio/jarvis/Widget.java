package fr.tonynio.jarvis;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.BlurMaskFilter;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.RadialGradient;
import android.graphics.RectF;
import android.graphics.Shader;
import android.widget.RemoteViews;

/**
 * Le widget Jarvis de l'écran d'accueil : le rond du réacteur, que l'on agrandit en l'étirant avec le doigt
 * (l'icône d'une application, elle, a la taille que décide l'écran d'accueil). Le toucher ouvre Jarvis.
 * Il est dessiné aux trois couleurs du profil ouvert dans l'application (sinon, le dessin fourni avec elle).
 */
public class Widget extends AppWidgetProvider {
    private static final int TAILLE = 420;

    @Override
    public void onUpdate(Context contexte, AppWidgetManager gestion, int[] numeros) {
        redessiner(contexte, gestion, numeros);
    }

    /** Le profil a changé de couleurs : tous les widgets posés se redessinent. */
    static void toutRedessiner(Context contexte) {
        try {
            AppWidgetManager gestion = AppWidgetManager.getInstance(contexte);
            int[] numeros = gestion.getAppWidgetIds(new ComponentName(contexte, Widget.class));
            if (numeros != null && numeros.length > 0) redessiner(contexte, gestion, numeros);
        } catch (Exception e) {
            // pas de widget posé, ou écran d'accueil qui refuse : rien de grave
        }
    }

    private static void redessiner(Context contexte, AppWidgetManager gestion, int[] numeros) {
        Intent ouvrir = new Intent(contexte, MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        PendingIntent action = PendingIntent.getActivity(contexte, 0, ouvrir,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        String couleurs = contexte.getSharedPreferences("jarvis", Context.MODE_PRIVATE).getString("couleurs_widget", "");
        Bitmap dessin = null;
        try {
            String[] c = couleurs.split(",");
            if (c.length == 3) dessin = reacteur(Color.parseColor(c[0]), Color.parseColor(c[1]), Color.parseColor(c[2]));
        } catch (Exception e) {
            dessin = null;                           // couleur illisible : le dessin d'origine
        }
        for (int numero : numeros) {
            RemoteViews vue = new RemoteViews(contexte.getPackageName(), R.layout.widget_jarvis);
            vue.setOnClickPendingIntent(R.id.widget_jarvis, action);
            if (dessin != null) vue.setImageViewBitmap(R.id.widget_image, dessin);
            gestion.updateAppWidget(numero, vue);
        }
    }

    /** Le réacteur aux couleurs du profil : disque sombre bordé, graduations, arcs en dégradé, anneaux et cœur lumineux. */
    static Bitmap reacteur(int c1, int c2, int c3) {
        Bitmap image = Bitmap.createBitmap(TAILLE, TAILLE, Bitmap.Config.ARGB_8888);
        Canvas toile = new Canvas(image);
        float cx = TAILLE / 2f, r = TAILLE * 0.45f;
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);

        // halo autour du disque, puis le disque sombre et son liseré
        p.setShader(new RadialGradient(cx, cx, r * 1.1f, new int[]{alpha(c1, 110), alpha(c1, 0)}, new float[]{0.86f, 1f},
                Shader.TileMode.CLAMP));
        toile.drawCircle(cx, cx, r * 1.1f, p);
        p.setShader(new RadialGradient(cx, cx, r, new int[]{0xFF14223A, 0xFF0A1220, 0xFF060B13}, new float[]{0f, 0.6f, 1f},
                Shader.TileMode.CLAMP));
        toile.drawCircle(cx, cx, r, p);
        p.setShader(null);
        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(r * 0.025f);
        p.setColor(alpha(c1, 210));
        toile.drawCircle(cx, cx, r * 0.975f, p);

        // couronne de graduations (une longue toutes les 5)
        p.setStrokeCap(Paint.Cap.ROUND);
        for (int i = 0; i < 60; i++) {
            double a = Math.toRadians(i * 6);
            boolean longue = i % 5 == 0;
            float r1 = r * (longue ? 0.80f : 0.84f), r2 = r * 0.90f;
            p.setStrokeWidth(r * (longue ? 0.022f : 0.012f));
            p.setColor(alpha(longue ? c1 : c3, longue ? 230 : 140));
            toile.drawLine(cx + (float) (r1 * Math.cos(a)), cx + (float) (r1 * Math.sin(a)),
                    cx + (float) (r2 * Math.cos(a)), cx + (float) (r2 * Math.sin(a)), p);
        }

        // trois arcs lumineux en dégradé (couleur 2 vers couleur 3), avec leur halo flou
        RectF arc = new RectF(cx - r * 0.70f, cx - r * 0.70f, cx + r * 0.70f, cx + r * 0.70f);
        p.setShader(new LinearGradient(cx - r, cx - r, cx + r, cx + r, c2, c3, Shader.TileMode.CLAMP));
        Paint halo = new Paint(p);
        halo.setStrokeWidth(r * 0.12f);
        halo.setAlpha(110);
        halo.setMaskFilter(new BlurMaskFilter(r * 0.06f, BlurMaskFilter.Blur.NORMAL));
        p.setStrokeWidth(r * 0.06f);
        for (int i = 0; i < 3; i++) {
            toile.drawArc(arc, -80 + i * 120, 78, false, halo);
            toile.drawArc(arc, -80 + i * 120, 78, false, p);
        }
        p.setShader(null);

        // anneau plein, anneau en pointillés, puis le cœur
        p.setStrokeWidth(r * 0.022f);
        p.setColor(alpha(c1, 230));
        toile.drawCircle(cx, cx, r * 0.55f, p);
        p.setStrokeWidth(r * 0.014f);
        p.setColor(alpha(c3, 170));
        RectF pointilles = new RectF(cx - r * 0.44f, cx - r * 0.44f, cx + r * 0.44f, cx + r * 0.44f);
        for (int i = 0; i < 36; i += 2) toile.drawArc(pointilles, i * 10, 5, false, p);
        p.setStyle(Paint.Style.FILL);
        p.setShader(new RadialGradient(cx, cx, r * 0.36f, new int[]{Color.WHITE, alpha(c1, 230), alpha(c1, 0)},
                new float[]{0f, 0.25f, 1f}, Shader.TileMode.CLAMP));
        toile.drawCircle(cx, cx, r * 0.36f, p);
        return image;
    }

    private static int alpha(int couleur, int a) {
        return Color.argb(a, Color.red(couleur), Color.green(couleur), Color.blue(couleur));
    }
}
