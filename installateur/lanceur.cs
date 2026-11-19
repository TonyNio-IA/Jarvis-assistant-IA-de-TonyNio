// Lanceur de l'installateur de Jarvis, assistant IA de TonyNio.
// Il ne fait qu'une chose : sortir le fichier Installer-Jarvis.bat qu'il contient
// et le lancer dans la meme fenetre. Tout le travail est fait par ce fichier .bat.
// https://github.com/TonyNio-IA/Jarvis-assistant-IA-de-TonyNio
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;

[assembly: AssemblyTitle("Installer Jarvis")]
[assembly: AssemblyDescription("Installateur de Jarvis, assistant IA de TonyNio")]
[assembly: AssemblyProduct("Jarvis, assistant IA de TonyNio")]
[assembly: AssemblyCompany("TonyNio")]
[assembly: AssemblyCopyright("TonyNio")]
[assembly: AssemblyVersion("1.26.0.0")]
[assembly: AssemblyFileVersion("1.26.0.0")]

static class Lanceur
{
    static int Main()
    {
        try
        {
            Console.Title = "Installer Jarvis";
            string dossier = Path.Combine(Path.GetTempPath(), "Jarvis-installateur");
            Directory.CreateDirectory(dossier);
            string fichier = Path.Combine(dossier, "Installer-Jarvis.bat");
            using (Stream source = Assembly.GetExecutingAssembly().GetManifestResourceStream("Installer-Jarvis.bat"))
            {
                if (source == null)
                {
                    throw new InvalidOperationException("Le fichier d'installation est absent du lanceur.");
                }
                using (FileStream cible = new FileStream(fichier, FileMode.Create, FileAccess.Write))
                {
                    source.CopyTo(cible);
                }
            }
            ProcessStartInfo info = new ProcessStartInfo();
            info.FileName = Path.Combine(Environment.SystemDirectory, "cmd.exe");
            info.Arguments = "/c \"\"" + fichier + "\"\"";
            info.UseShellExecute = false;
            info.WorkingDirectory = dossier;
            // L'installateur range cette version (avec l'icône du réacteur) dans le dossier de Jarvis
            info.EnvironmentVariables["JARVIS_LANCEUR"] = Process.GetCurrentProcess().MainModule.FileName;
            int code;
            using (Process p = Process.Start(info))
            {
                p.WaitForExit();
                code = p.ExitCode;
            }
            try { File.Delete(fichier); } catch { }
            return code;
        }
        catch (Exception e)
        {
            Console.WriteLine("L'installateur de Jarvis n'a pas pu demarrer : " + e.Message);
            Console.WriteLine("Appuie sur Entree pour fermer.");
            Console.ReadLine();
            return 1;
        }
    }
}
