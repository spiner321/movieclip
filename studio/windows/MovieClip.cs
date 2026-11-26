using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: System.Reflection.AssemblyTitle("MovieClip Studio")]
[assembly: System.Reflection.AssemblyProduct("MovieClip Studio")]
[assembly: System.Reflection.AssemblyVersion("1.0.0.0")]

internal static class MovieClip
{
    private static readonly string Root = AppDomain.CurrentDomain.BaseDirectory;
    private static readonly string Output = Path.Combine(Root, "exports");

    [STAThread]
    private static int Main(string[] args)
    {
        bool healthCheck = args.Length == 1 && args[0] == "--check";
        Application.EnableVisualStyles();
        try
        {
            using (Process engine = StartEngine())
            {
                try
                {
                    Task<string> startup = engine.StandardOutput.ReadLineAsync();
                    if (!startup.Wait(TimeSpan.FromSeconds(20)))
                        throw new InvalidOperationException("편집 엔진을 시작하는 데 시간이 너무 오래 걸립니다.");
                    Uri address;
                    string line = startup.Result ?? "";
                    const string prefix = "MovieClip ";
                    if (!line.StartsWith(prefix, StringComparison.Ordinal) ||
                        !Uri.TryCreate(line.Substring(prefix.Length), UriKind.Absolute, out address) ||
                        address.Scheme != "http" || address.Host != "127.0.0.1")
                    {
                        throw new InvalidOperationException("편집 엔진을 시작하지 못했습니다.\n" + engine.StandardError.ReadToEnd());
                    }

                    if (healthCheck)
                    {
                        using (var client = new System.Net.WebClient())
                        {
                            client.Proxy = null;
                            return client.DownloadString(new Uri(address, "/api/health")).Contains("\"ready\": true") ? 0 : 1;
                        }
                    }

                    using (var menu = new ContextMenuStrip())
                    using (var tray = new NotifyIcon())
                    using (var icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath))
                    {
                        menu.Items.Add("편집기 열기", null, (sender, e) => RunAction(() => OpenEditor(address)));
                        menu.Items.Add("결과 폴더 열기", null, (sender, e) => RunAction(OpenOutput));
                        menu.Items.Add("종료", null, (sender, e) => Application.ExitThread());
                        tray.Text = "MovieClip Studio";
                        tray.Icon = icon ?? SystemIcons.Application;
                        tray.ContextMenuStrip = menu;
                        tray.DoubleClick += (sender, e) => RunAction(() => OpenEditor(address));
                        tray.Visible = true;
                        OpenEditor(address);
                        Application.Run();
                        tray.Visible = false;
                    }
                }
                finally
                {
                    engine.StandardInput.Close();
                    if (!engine.WaitForExit(6000))
                    {
                        engine.Kill();
                        engine.WaitForExit();
                    }
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            if (!healthCheck) ShowError(error);
            return 1;
        }
    }

    private static Process StartEngine()
    {
        string runtime = Path.Combine(Root, "runtime");
        string app = Path.Combine(runtime, "app");
        string ffmpeg = Path.Combine(runtime, "ffmpeg");
        var start = new ProcessStartInfo
        {
            FileName = Path.Combine(runtime, "python", "python.exe"),
            WorkingDirectory = app,
            Arguments = "-B movieclip_studio.py --port 0 --exit-with-stdin --output-dir \"" + Output + "\"",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardInput = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        start.EnvironmentVariables["PATH"] = ffmpeg + Path.PathSeparator + Environment.SystemDirectory;
        return Process.Start(start);
    }

    private static void OpenEditor(Uri address)
    {
        string[] locations = {
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData)
        };
        foreach (string browser in new[] { @"Microsoft\Edge\Application\msedge.exe", @"Google\Chrome\Application\chrome.exe" })
        {
            foreach (string location in locations)
            {
                string file = Path.Combine(location, browser);
                if (File.Exists(file))
                {
                    Process.Start(file, "--app=" + address.AbsoluteUri);
                    return;
                }
            }
        }
        Process.Start(address.AbsoluteUri);
    }

    private static void OpenOutput()
    {
        Directory.CreateDirectory(Output);
        Process.Start("explorer.exe", "\"" + Output + "\"");
    }

    private static void RunAction(Action action)
    {
        try { action(); }
        catch (Exception error) { ShowError(error); }
    }

    private static void ShowError(Exception error)
    {
        MessageBox.Show(error.Message, "MovieClip Studio", MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
