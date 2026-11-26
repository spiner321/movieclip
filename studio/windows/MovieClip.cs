using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

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
            if (args.Length == 2 && args[0] == "--pick-folder")
                return PickFolder(args[1]);
            if (args.Length == 1 && args[0] == "--pick-files")
                return PickFiles();

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
                        Form editor = null;
                        Action open = () =>
                        {
                            if (editor == null || editor.IsDisposed)
                                editor = CreateEditor(address);
                            editor.Show();
                            if (editor.WindowState == FormWindowState.Minimized)
                                editor.WindowState = FormWindowState.Normal;
                            editor.Activate();
                        };
                        menu.Items.Add("편집기 열기", null, (sender, e) => RunAction(open));
                        menu.Items.Add("결과 폴더 열기", null, (sender, e) => RunAction(() => OpenOutput(address)));
                        menu.Items.Add("종료", null, (sender, e) => Application.ExitThread());
                        tray.Text = "MovieClip Studio";
                        tray.Icon = icon ?? SystemIcons.Application;
                        tray.ContextMenuStrip = menu;
                        tray.DoubleClick += (sender, e) => RunAction(open);
                        tray.Visible = true;
                        open();
                        Application.Run();
                        if (editor != null) editor.Dispose();
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
        start.EnvironmentVariables["MOVIECLIP_LAUNCHER"] = Application.ExecutablePath;
        start.EnvironmentVariables["MOVIECLIP_OPEN_DIALOG"] = "1";
        return Process.Start(start);
    }

    private static Form CreateEditor(Uri address)
    {
        var window = new Form
        {
            Text = "MovieClip Studio",
            BackColor = Color.FromArgb(21, 21, 28),
            ClientSize = new Size(1300, 820),
            MinimumSize = new Size(740, 520),
            StartPosition = FormStartPosition.CenterScreen,
            AutoScaleMode = AutoScaleMode.Dpi
        };
        var browser = new WebView2 { Dock = DockStyle.Fill, DefaultBackgroundColor = window.BackColor };
        window.Controls.Add(browser);
        window.Shown += async (sender, e) =>
        {
            try
            {
                string profile = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "MovieClip Studio", "WebView2");
                CoreWebView2Environment environment = await CoreWebView2Environment.CreateAsync(null, profile);
                if (window.IsDisposed) return;
                await browser.EnsureCoreWebView2Async(environment);
                if (window.IsDisposed) return;
                var core = browser.CoreWebView2;
                core.NavigationStarting += (view, navigation) =>
                {
                    Uri next;
                    navigation.Cancel = !Uri.TryCreate(navigation.Uri, UriKind.Absolute, out next) ||
                        next.Scheme != address.Scheme || next.Host != address.Host || next.Port != address.Port;
                };
                core.NewWindowRequested += (view, request) => request.Handled = true;
                core.WebMessageReceived += (view, message) => ReceiveFiles(core, address, message);
                core.Navigate(address.AbsoluteUri);
            }
            catch (Exception error)
            {
                if (!window.IsDisposed)
                {
                    ShowError(error);
                    window.Close();
                }
            }
        };
        return window;
    }

    private static void ReceiveFiles(CoreWebView2 core, Uri address, CoreWebView2WebMessageReceivedEventArgs message)
    {
        if (!address.Equals(new Uri(message.Source)) || message.WebMessageAsJson != "\"movieclip-drop\"")
            return;
        var paths = new List<string>();
        foreach (object item in message.AdditionalObjects)
        {
            var nativeFile = item as CoreWebView2File;
            if (nativeFile != null) paths.Add(nativeFile.Path);
            else if (item is FileInfo) paths.Add(((FileInfo)item).FullName);
        }
        core.PostWebMessageAsJson(new JavaScriptSerializer().Serialize(new { type = "movieclip-drop", paths }));
    }

    private static int PickFolder(string initial)
    {
        using (var dialog = new FolderBrowserDialog())
        {
            dialog.Description = "영상 저장 폴더를 선택하세요.";
            dialog.SelectedPath = Directory.Exists(initial) ? initial : Root;
            if (ShowPicker(dialog) == DialogResult.OK)
                WritePickerResult(dialog.SelectedPath);
            return 0;
        }
    }

    private static int PickFiles()
    {
        using (var dialog = new OpenFileDialog())
        {
            dialog.Title = "영상 파일 열기";
            dialog.Filter = "동영상 파일|*.mp4;*.mkv;*.mov;*.avi;*.webm;*.m4v;*.mts;*.m2ts;*.ts;*.mxf;*.flv;*.wmv;*.vob;*.mpg;*.mpeg|모든 파일|*.*";
            dialog.Multiselect = true;
            dialog.RestoreDirectory = true;
            if (ShowPicker(dialog) == DialogResult.OK)
                WritePickerResult(string.Join("\n", dialog.FileNames));
            return 0;
        }
    }

    private static DialogResult ShowPicker(CommonDialog dialog)
    {
        using (var owner = new Form { TopMost = true, ShowInTaskbar = false, Opacity = 0 })
        {
            owner.Show();
            return dialog.ShowDialog(owner);
        }
    }

    private static void WritePickerResult(string value)
    {
        using (var output = new StreamWriter(Console.OpenStandardOutput(), new System.Text.UTF8Encoding(false)))
            output.Write(value);
    }

    private static void OpenOutput(Uri address)
    {
        using (var client = new System.Net.WebClient())
        {
            client.Proxy = null;
            client.Encoding = System.Text.Encoding.UTF8;
            string directory = client.DownloadString(new Uri(address, "/api/output-directory"));
            Directory.CreateDirectory(directory);
            Process.Start("explorer.exe", "\"" + directory + "\"");
        }
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
