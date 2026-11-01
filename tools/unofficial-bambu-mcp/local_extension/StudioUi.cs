using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
#if TEST
using System.Drawing;
using System.Windows.Forms;
#endif

// A deliberately narrow, one-request process. It never uses global mouse/keyboard
// input, arbitrary screen coordinates, WM_COMMAND, or another process's control.
internal static class StudioUi
{
    private const string DefaultExe = @"C:\Program Files\Bambu Studio\bambu-studio.exe";
    private const int MaxElements = 1600;
    private const int MaxDepth = 45;
    private static readonly JavaScriptSerializer Json = new JavaScriptSerializer { MaxJsonLength = 4000000 };
    private static bool ActionAttempted;

    [DllImport("user32.dll", SetLastError = true)] private static extern bool SetProcessDpiAwarenessContext(IntPtr context);
    [DllImport("user32.dll", SetLastError = true)] private static extern bool SetProcessDPIAware();

    [DllImport("user32.dll")] private static extern bool EnumWindows(EnumWindowProc cb, IntPtr p);
    private delegate bool EnumWindowProc(IntPtr hwnd, IntPtr p);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
    [DllImport("user32.dll")] private static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsWindowEnabled(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] private static extern IntPtr GetWindow(IntPtr hwnd, uint command);
    [DllImport("user32.dll")] private static extern bool IsChild(IntPtr parent, IntPtr child);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr hwnd, StringBuilder text, int count);
    [DllImport("user32.dll")] private static extern bool GetClientRect(IntPtr hwnd, out NativeRect rect);
    [DllImport("user32.dll")] private static extern bool GetWindowRect(IntPtr hwnd, out NativeRect rect);
    [DllImport("user32.dll", SetLastError = true)] private static extern IntPtr SendMessageTimeout(IntPtr hwnd, uint message, UIntPtr wParam, IntPtr lParam, uint flags, uint timeout, out UIntPtr result);
    [DllImport("kernel32.dll", SetLastError = true)] private static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)] private static extern bool QueryFullProcessImageName(IntPtr process, uint flags, StringBuilder name, ref uint size);
    [DllImport("kernel32.dll")] private static extern bool CloseHandle(IntPtr handle);
    [StructLayout(LayoutKind.Sequential)] private struct NativeRect { public int Left, Top, Right, Bottom; }

    private sealed class Target
    {
        public IntPtr Window;
        public uint Pid;
        public string Exe;
    }
    private sealed class Node
    {
        public AutomationElement Element;
        public Dictionary<string, object> Data;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        InitializeDpiAwareness();
        Console.InputEncoding = new UTF8Encoding(false);
        Console.OutputEncoding = new UTF8Encoding(false);
#if TEST
        if (args.Length == 1 && args[0] == "--self-test") return Fixture.Run();
#endif
        try
        {
            string input = Console.In.ReadToEnd();
            if (input.Length == 0 || input.Length > 500000) throw new InvalidOperationException("Expected one JSON request on stdin (at most 500 KB).");
            var request = Json.DeserializeObject(input) as Dictionary<string, object>;
            if (request == null) throw new InvalidOperationException("Request must be a JSON object.");
            Console.WriteLine(Json.Serialize(Execute(request)));
            return 0;
        }
        catch (Exception ex)
        {
            Console.WriteLine(Json.Serialize(Obj("ok", false, "error", ex.GetType().Name + ": " + ex.Message,
                "action_attempted", ActionAttempted, "outcome", ActionAttempted ? "uncertain_do_not_retry" : "not_dispatched")));
            return 1;
        }
    }

    private static void InitializeDpiAwareness()
    {
        // UIA bounding rectangles are physical screen pixels. Make Win32 HWND
        // geometry use the same units on scaled and mixed-DPI monitors before
        // initializing UIA or creating even the isolated fixture's controls.
        try { if (SetProcessDpiAwarenessContext(new IntPtr(-4))) return; }
        catch (EntryPointNotFoundException) { }
        catch (DllNotFoundException) { }
        // Windows versions predating per-monitor-v2 still support system-aware
        // geometry. An already-established context is left unchanged by Win32.
        try { SetProcessDPIAware(); }
        catch (EntryPointNotFoundException) { }
        catch (DllNotFoundException) { }
    }

    internal static Dictionary<string, object> Execute(Dictionary<string, object> request)
    {
        ActionAttempted = false;
        string operation = Text(request, "op", true);
        string expected = Path.GetFullPath(Text(request, "expected_exe", false) ?? DefaultExe);
#if TEST
        if (!SamePath(expected, Process.GetCurrentProcess().MainModule.FileName))
            throw new InvalidOperationException("Test helper only targets its own fixture process.");
#else
        if (!String.Equals(Path.GetFileName(expected), "bambu-studio.exe", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Only an explicit Bambu Studio executable is supported.");
#endif
        if (!File.Exists(expected)) throw new FileNotFoundException("Expected executable does not exist.");
        if (operation == "inspect")
        {
            if (!request.ContainsKey("window_id")) return ListWindows(expected);
            Target target = GetTarget(Number(request, "window_id"), expected);
            bool truncated;
            List<Node> nodes = ReadTree(target, out truncated);
            var elements = new List<object>();
            foreach (Node node in nodes) elements.Add(node.Data);
            return Obj("ok", true, "window", WindowInfo(target), "elements", elements, "truncated", truncated,
                "snapshot_id", Hash(Json.Serialize(elements)), "read_at_utc", DateTime.UtcNow.ToString("o"));
        }
        if (operation != "act") throw new InvalidOperationException("Supported operations: inspect, act.");
        Target active = GetTarget(Number(request, "window_id"), expected);
        var identity = Dict(request, "element");
        ValidateIdentity(identity);
        bool ignored;
        List<Node> fresh = ReadTree(active, out ignored);
        Node chosen = null;
        foreach (Node node in fresh)
        {
            if ((string)node.Data["token"] != Text(identity, "token", true)) continue;
            if (chosen != null) throw new InvalidOperationException("Ambiguous element token.");
            chosen = node;
        }
        if (chosen == null) throw new InvalidOperationException("Element no longer exists; inspect again.");
        foreach (string key in IdentityKeys)
            if (!String.Equals(Convert.ToString(identity[key], CultureInfo.InvariantCulture), Convert.ToString(chosen.Data[key], CultureInfo.InvariantCulture), StringComparison.Ordinal))
                throw new InvalidOperationException("Element identity changed at " + key + "; inspect again.");
        if (!(bool)chosen.Data["enabled"] || (bool)chosen.Data["offscreen"])
            throw new InvalidOperationException("Target element is disabled or offscreen.");
        // The provider may replace or hide a control between tree enumeration and
        // invocation. Recheck identity and owner immediately at the boundary.
        Recheck(active, chosen);
        string action = Text(request, "action", true);
        string value = Text(request, "value", false);
        string method = Act(active, chosen, action, value);
        return Obj("ok", true, "window", WindowInfo(active), "element", chosen.Data, "action", action,
            "method", method, "action_attempted", ActionAttempted, "outcome", ActionAttempted ? "invoked" : "already_in_requested_state");
    }

    private static readonly string[] IdentityKeys = { "token", "name", "control_type", "automation_id", "class_name", "hwnd", "parent_token", "process_id" };
    private static void ValidateIdentity(Dictionary<string, object> identity)
    {
        foreach (string key in IdentityKeys) if (!identity.ContainsKey(key) || identity[key] == null)
            throw new InvalidOperationException("Full inspected element identity required: " + key);
    }

    private static string Act(Target target, Node node, string action, string value)
    {
        AutomationElement element = node.Element;
        object pattern;
        if (action == "set_value")
        {
            if (value == null || value.Length > 10000) throw new InvalidOperationException("set_value requires a string at most 10000 characters.");
            if (!element.TryGetCurrentPattern(ValuePattern.Pattern, out pattern)) throw new InvalidOperationException("Element has no ValuePattern.");
            var input = (ValuePattern)pattern;
            if (input.Current.IsReadOnly) throw new InvalidOperationException("Element is read-only.");
            if (input.Current.Value == value) return "ValuePattern_noop";
            ActionAttempted = true;
            input.SetValue(value);
            return "ValuePattern";
        }
        if (action == "select")
        {
            if (!element.TryGetCurrentPattern(SelectionItemPattern.Pattern, out pattern)) throw new InvalidOperationException("Select requires a selectable item; expand its container and inspect first.");
            var item = (SelectionItemPattern)pattern;
            if (item.Current.IsSelected) return "SelectionItemPattern_noop";
            ActionAttempted = true;
            item.Select();
            return "SelectionItemPattern";
        }
        if (action == "expand" || action == "collapse")
        {
            if (!element.TryGetCurrentPattern(ExpandCollapsePattern.Pattern, out pattern)) throw new InvalidOperationException("Element has no ExpandCollapsePattern.");
            var expanding = (ExpandCollapsePattern)pattern;
            if (expanding.Current.ExpandCollapseState == ExpandCollapseState.LeafNode) throw new InvalidOperationException("Element is a leaf node.");
            var desired = action == "expand" ? ExpandCollapseState.Expanded : ExpandCollapseState.Collapsed;
            if (expanding.Current.ExpandCollapseState == desired) return "ExpandCollapsePattern_noop";
            ActionAttempted = true;
            if (action == "expand") expanding.Expand(); else expanding.Collapse();
            return "ExpandCollapsePattern";
        }
        if (action == "toggle")
        {
            if (value != "on" && value != "off") throw new InvalidOperationException("toggle requires explicit value 'on' or 'off'.");
            if (!element.TryGetCurrentPattern(TogglePattern.Pattern, out pattern)) throw new InvalidOperationException("Element has no TogglePattern.");
            var toggling = (TogglePattern)pattern;
            var desired = value == "on" ? ToggleState.On : ToggleState.Off;
            if (toggling.Current.ToggleState == desired) return "TogglePattern_noop";
            for (int i = 0; i < 2; i++)
            {
                Recheck(target, node);
                ActionAttempted = true;
                toggling.Toggle();
                if (toggling.Current.ToggleState == desired) return "TogglePattern";
            }
            throw new InvalidOperationException("Toggle did not reach the requested state; inspect before further action.");
        }
        if (action != "click") throw new InvalidOperationException("Supported actions: click, set_value, select, expand, collapse, toggle.");
        if (element.TryGetCurrentPattern(InvokePattern.Pattern, out pattern))
        {
            ActionAttempted = true;
            ((InvokePattern)pattern).Invoke();
            return "InvokePattern";
        }
        if (element.TryGetCurrentPattern(SelectionItemPattern.Pattern, out pattern))
        {
            var selected = (SelectionItemPattern)pattern;
            if (selected.Current.IsSelected) return "SelectionItemPattern_noop";
            ActionAttempted = true;
            selected.Select();
            return "SelectionItemPattern";
        }
        return ClickCustomWindow(target, node);
    }

    private static string ClickCustomWindow(Target target, Node node)
    {
        IntPtr hwnd = new IntPtr(Convert.ToInt64(node.Data["hwnd"], CultureInfo.InvariantCulture));
        if (hwnd == IntPtr.Zero || hwnd == target.Window) throw new InvalidOperationException("Element has no distinct child HWND and no invoke pattern.");
        string cls = Class(hwnd);
        bool custom = cls.StartsWith("wxWindow", StringComparison.OrdinalIgnoreCase);
#if TEST
        custom = custom || (cls.StartsWith("WindowsForms10.Window", StringComparison.Ordinal) && ((string)node.Data["name"]).StartsWith("WXTEST:", StringComparison.Ordinal));
#endif
        if (!custom) throw new InvalidOperationException("HWND mouse fallback is restricted to Bambu Studio custom wx controls.");
        Recheck(target, node);
        NativeRect rect, outer;
        if (!GetClientRect(hwnd, out rect) || !GetWindowRect(hwnd, out outer) || rect.Right - rect.Left < 3 || rect.Bottom - rect.Top < 3)
            throw new InvalidOperationException("Target HWND geometry is unavailable.");
        Rect bounds = elementBounds(node.Element);
        if (bounds.IsEmpty || Math.Abs(bounds.Left - outer.Left) > 4 || Math.Abs(bounds.Top - outer.Top) > 4 ||
            Math.Abs(bounds.Right - outer.Right) > 4 || Math.Abs(bounds.Bottom - outer.Bottom) > 4)
            throw new InvalidOperationException("Element bounds do not identify its own HWND.");
        int x = (rect.Right - rect.Left) / 2;
        int y = (rect.Bottom - rect.Top) / 2;
        if (x > 32767 || y > 32767) throw new InvalidOperationException("Invalid target client size.");
        IntPtr position = new IntPtr((y << 16) | (x & 65535));
        UIntPtr result;
        ActionAttempted = true;
        if (SendMessageTimeout(hwnd, 0x0201, new UIntPtr(1), position, 3, 2000, out result) == IntPtr.Zero)
            throw new InvalidOperationException("Bound mouse-down outcome unknown; do not retry automatically.");
        // A released click is sent only after the matching down was acknowledged.
        // A changed/destroyed control ends this one-shot attempt instead of replay.
        Recheck(target, node);
        if (SendMessageTimeout(hwnd, 0x0202, UIntPtr.Zero, position, 3, 2000, out result) == IntPtr.Zero)
            throw new InvalidOperationException("Bound mouse-up outcome unknown; do not retry automatically.");
        return "bound_wx_hwnd_mouse";
    }

    private static void Recheck(Target target, Node node)
    {
        GetTarget(target.Window.ToInt64(), target.Exe);
        AutomationElement.AutomationElementInformation now = node.Element.Current;
        if (now.ProcessId != target.Pid || !now.IsEnabled || now.IsOffscreen || now.IsPassword ||
            now.Name != (string)node.Data["name"] || now.AutomationId != (string)node.Data["automation_id"] ||
            now.ClassName != (string)node.Data["class_name"] || now.ControlType.ProgrammaticName != (string)node.Data["control_type"] ||
            now.NativeWindowHandle != Convert.ToInt32(node.Data["hwnd"], CultureInfo.InvariantCulture))
            throw new InvalidOperationException("Element changed before invocation.");
        IntPtr hwnd = new IntPtr(now.NativeWindowHandle);
        if (hwnd != IntPtr.Zero)
        {
            uint owner;
            GetWindowThreadProcessId(hwnd, out owner);
            if (owner != target.Pid || !IsWindow(hwnd) || !IsWindowVisible(hwnd) || !IsWindowEnabled(hwnd) || !InWindow(target.Window, hwnd))
                throw new InvalidOperationException("HWND ownership, visibility or enabled state changed.");
        }
    }

    private static Dictionary<string, object> ListWindows(string exe)
    {
        var windows = new List<object>();
        EnumWindows(delegate(IntPtr hwnd, IntPtr p)
        {
            try
            {
                if (IsWindowVisible(hwnd) && SamePath(ProcessPath(hwnd), exe))
                {
                    uint pid;
                    GetWindowThreadProcessId(hwnd, out pid);
                    windows.Add(WindowInfo(new Target { Window = hwnd, Pid = pid, Exe = exe }));
                }
            }
            catch { }
            return true;
        }, IntPtr.Zero);
        return Obj("ok", true, "expected_exe", exe, "windows", windows, "read_at_utc", DateTime.UtcNow.ToString("o"));
    }

    private static Target GetTarget(long window, string exe)
    {
        IntPtr hwnd = new IntPtr(window);
        if (!IsWindow(hwnd) || !IsWindowVisible(hwnd) || IsIconic(hwnd)) throw new InvalidOperationException("Target window is missing, hidden or minimized.");
        // A request selects a returned top-level window, never an arbitrary child.
        bool topLevel = false;
        EnumWindows(delegate(IntPtr candidate, IntPtr p) { if (candidate == hwnd) topLevel = true; return true; }, IntPtr.Zero);
        if (!topLevel) throw new InvalidOperationException("window_id must identify a top-level Bambu Studio window.");
        if (!SamePath(ProcessPath(hwnd), exe)) throw new InvalidOperationException("Window executable does not match expected_exe.");
        uint pid;
        GetWindowThreadProcessId(hwnd, out pid);
        return new Target { Window = hwnd, Pid = pid, Exe = exe };
    }

    private static List<Node> ReadTree(Target target, out bool truncated)
    {
        var nodes = new List<Node>();
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var roots = new List<IntPtr> { target.Window };
        EnumWindows(delegate(IntPtr hwnd, IntPtr p)
        {
            uint pid;
            GetWindowThreadProcessId(hwnd, out pid);
            if (hwnd != target.Window && pid == target.Pid && IsWindowVisible(hwnd) && OwnedBy(target.Window, hwnd)) roots.Add(hwnd);
            return true;
        }, IntPtr.Zero);
        foreach (IntPtr hwnd in roots)
        {
            if (nodes.Count >= MaxElements) break;
            Walk(AutomationElement.FromHandle(hwnd), "", target, nodes, visited, 0);
        }
        truncated = nodes.Count >= MaxElements;
        return nodes;
    }

    private static void Walk(AutomationElement element, string parentToken, Target target, List<Node> nodes, HashSet<string> visited, int depth)
    {
        if (element == null || depth > MaxDepth || nodes.Count >= MaxElements) return;
        string token;
        try
        {
            var c = element.Current;
            if (c.ProcessId != target.Pid) return;
            string runtime;
            try { runtime = String.Join(".", Array.ConvertAll(element.GetRuntimeId(), delegate(int n) { return n.ToString(CultureInfo.InvariantCulture); })); }
            catch { runtime = "hwnd:" + c.NativeWindowHandle.ToString(CultureInfo.InvariantCulture) + ":" + c.AutomationId + ":" + c.ClassName + ":" + c.Name; }
            token = Hash(target.Pid.ToString(CultureInfo.InvariantCulture) + ":" + target.Window.ToInt64().ToString(CultureInfo.InvariantCulture) + ":" + runtime);
            if (!visited.Add(token)) return;
            Rect bounds = c.BoundingRectangle;
            var patterns = new List<string>();
            foreach (AutomationPattern p in element.GetSupportedPatterns()) patterns.Add(p.ProgrammaticName);
            var ancestors = new List<string>();
            var parentNames = new List<string>();
            string ancestorToken = parentToken;
            for (int i = 0; ancestorToken.Length > 0 && i < MaxDepth; i++)
            {
                Node parent = nodes.Find(delegate(Node n) { return (string)n.Data["token"] == ancestorToken; });
                if (parent == null) break;
                ancestors.Add(ancestorToken);
                parentNames.Add((string)parent.Data["name"]);
                ancestorToken = (string)parent.Data["parent_token"];
            }
            var data = Obj("token", token, "parent_token", parentToken, "process_id", c.ProcessId,
                "name", Limit(c.Name, 1200), "control_type", c.ControlType.ProgrammaticName, "automation_id", c.AutomationId,
                "class_name", c.ClassName, "hwnd", (long)c.NativeWindowHandle, "enabled", c.IsEnabled,
                "offscreen", c.IsOffscreen, "keyboard_focusable", c.IsKeyboardFocusable, "has_focus", c.HasKeyboardFocus,
                "bounds", bounds.IsEmpty ? null : new double[] { bounds.X, bounds.Y, bounds.Width, bounds.Height },
                "patterns", patterns, "depth", depth, "ancestors", ancestors, "parent_names", parentNames);
            object pattern;
            if (element.TryGetCurrentPattern(ValuePattern.Pattern, out pattern))
            {
                var v = ((ValuePattern)pattern).Current;
                data["read_only"] = v.IsReadOnly;
                // Password/credential values must never enter the MCP snapshot.
                data["value"] = c.IsPassword ? "[redacted]" : Limit(v.Value, 2000);
            }
            if (element.TryGetCurrentPattern(TogglePattern.Pattern, out pattern)) data["toggle_state"] = ((TogglePattern)pattern).Current.ToggleState.ToString();
            if (element.TryGetCurrentPattern(SelectionItemPattern.Pattern, out pattern)) data["selected"] = ((SelectionItemPattern)pattern).Current.IsSelected;
            if (element.TryGetCurrentPattern(ExpandCollapsePattern.Pattern, out pattern)) data["expand_state"] = ((ExpandCollapsePattern)pattern).Current.ExpandCollapseState.ToString();
            data["password"] = c.IsPassword;
            nodes.Add(new Node { Element = element, Data = data });
        }
        catch (ElementNotAvailableException) { return; }
        catch (InvalidOperationException) { return; }
        try
        {
            AutomationElement child = TreeWalker.RawViewWalker.GetFirstChild(element);
            while (child != null && nodes.Count < MaxElements)
            {
                Walk(child, token, target, nodes, visited, depth + 1);
                child = TreeWalker.RawViewWalker.GetNextSibling(child);
            }
        }
        catch (ElementNotAvailableException) { }
        catch (InvalidOperationException) { }
    }

    private static bool InWindow(IntPtr root, IntPtr child)
    {
        if (root == child || IsChild(root, child)) return true;
        IntPtr top = child;
        for (int i = 0; i < 50; i++)
        {
            IntPtr parent = GetAncestor(top, 2);
            if (parent == IntPtr.Zero || parent == top) break;
            top = parent;
        }
        return OwnedBy(root, top);
    }
    [DllImport("user32.dll")] private static extern IntPtr GetAncestor(IntPtr hwnd, uint flags);
    private static bool OwnedBy(IntPtr root, IntPtr candidate)
    {
        for (int i = 0; i < 40; i++)
        {
            candidate = GetWindow(candidate, 4);
            if (candidate == IntPtr.Zero) return false;
            if (candidate == root || IsChild(root, candidate)) return true;
        }
        return false;
    }
    private static Rect elementBounds(AutomationElement element) { return element.Current.BoundingRectangle; }
    private static Dictionary<string, object> WindowInfo(Target t) { return Obj("window_id", t.Window.ToInt64(), "process_id", t.Pid, "title", Title(t.Window), "expected_exe", t.Exe, "enabled", IsWindowEnabled(t.Window)); }
    private static string Title(IntPtr hwnd) { var b = new StringBuilder(4096); GetWindowText(hwnd, b, b.Capacity); return b.ToString(); }
    private static string Class(IntPtr hwnd) { var b = new StringBuilder(512); GetClassName(hwnd, b, b.Capacity); return b.ToString(); }
    private static string ProcessPath(IntPtr hwnd)
    {
        uint pid;
        GetWindowThreadProcessId(hwnd, out pid);
        IntPtr process = OpenProcess(0x1000, false, pid);
        if (process == IntPtr.Zero) throw new InvalidOperationException("Cannot verify window process.");
        try
        {
            uint length = 32768;
            var b = new StringBuilder((int)length);
            if (!QueryFullProcessImageName(process, 0, b, ref length)) throw new InvalidOperationException("Cannot read process image path.");
            return Path.GetFullPath(b.ToString());
        }
        finally { CloseHandle(process); }
    }
    private static bool SamePath(string a, string b) { return String.Equals(Path.GetFullPath(a), Path.GetFullPath(b), StringComparison.OrdinalIgnoreCase); }
    private static string Hash(string s) { using (var sha = SHA256.Create()) return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(s))).Replace("-", "").ToLowerInvariant(); }
    private static string Limit(string s, int count) { return s == null ? "" : s.Length > count ? s.Substring(0, count) : s; }
    private static string Text(Dictionary<string, object> obj, string key, bool required)
    {
        object value;
        if (!obj.TryGetValue(key, out value) || value == null) { if (required) throw new InvalidOperationException("Missing " + key); return null; }
        if (!(value is string)) throw new InvalidOperationException(key + " must be a string.");
        return (string)value;
    }
    private static long Number(Dictionary<string, object> obj, string key)
    {
        object value;
        if (!obj.TryGetValue(key, out value) || value == null || value is string || value is bool) throw new InvalidOperationException("Missing or invalid integer " + key);
        long n = Convert.ToInt64(value, CultureInfo.InvariantCulture);
        if (Convert.ToDecimal(value, CultureInfo.InvariantCulture) != n || n <= 0) throw new InvalidOperationException("Invalid positive integer " + key);
        return n;
    }
    private static Dictionary<string, object> Dict(Dictionary<string, object> obj, string key)
    {
        object value;
        if (!obj.TryGetValue(key, out value) || !(value is Dictionary<string, object>)) throw new InvalidOperationException("Missing object " + key);
        return (Dictionary<string, object>)value;
    }
    internal static Dictionary<string, object> Obj(params object[] pairs)
    {
        var d = new Dictionary<string, object>(StringComparer.Ordinal);
        for (int i = 0; i < pairs.Length; i += 2) d.Add((string)pairs[i], pairs[i + 1]);
        return d;
    }

#if TEST
    private static class Fixture
    {
        private static int Clicks, CustomClicks, Failures;
        private static readonly List<object> Results = new List<object>();
        internal static int Run()
        {
            Application.EnableVisualStyles();
            var form = new Form { Text = "StudioUi isolated fixture", Width = 430, Height = 350, ShowInTaskbar = false, StartPosition = FormStartPosition.CenterScreen };
            var enabled = new Button { Text = "Enabled test", AccessibleName = "Enabled test", Left = 20, Top = 20, Width = 150 };
            var disabled = new Button { Text = "Disabled test", AccessibleName = "Disabled test", Enabled = false, Left = 200, Top = 20, Width = 150 };
            var edit = new TextBox { AccessibleName = "Edit test", Left = 20, Top = 65, Width = 200, Text = "before" };
            var toggle = new CheckBox { AccessibleName = "Toggle test", Text = "Toggle test", Left = 20, Top = 105, Width = 150 };
            var choices = new ComboBox { AccessibleName = "Choice test", Left = 200, Top = 105, Width = 150, DropDownStyle = ComboBoxStyle.DropDownList };
            choices.Items.AddRange(new object[] { "Choice A", "Choice B" }); choices.SelectedIndex = 0;
            var tabs = new TabControl { AccessibleName = "Tabs test", Left = 200, Top = 155, Width = 180, Height = 100 };
            tabs.TabPages.Add(new TabPage("Page A") { AccessibleName = "Page A" });
            tabs.TabPages.Add(new TabPage("Page B") { AccessibleName = "Page B" });
            var custom = new Panel { AccessibleName = "WXTEST: mouse", Left = 20, Top = 150, Width = 160, Height = 45, BackColor = Color.Silver };
            var customLabel = new Label { Text = "Custom panel click", Dock = DockStyle.Fill, Enabled = false };
            custom.Controls.Add(customLabel);
            enabled.Click += delegate { Interlocked.Increment(ref Clicks); };
            custom.MouseUp += delegate { Interlocked.Increment(ref CustomClicks); };
            form.Controls.AddRange(new Control[] { enabled, disabled, edit, toggle, choices, tabs, custom });
            form.Shown += delegate
            {
                long hwnd = form.Handle.ToInt64();
                var worker = new Thread(delegate()
                {
                    try
                    {
                        string exe = Process.GetCurrentProcess().MainModule.FileName;
                        Test("list_windows", delegate { var r = Execute(Obj("op", "inspect", "expected_exe", exe)); return ((List<object>)r["windows"]).Count == 1; });
                        var snapshot = Execute(Obj("op", "inspect", "expected_exe", exe, "window_id", hwnd));
                        Test("inspect_own_window", delegate { return ((List<object>)snapshot["elements"]).Count >= 6; });
                        var button = Find(snapshot, "Enabled test");
                        Test("invoke_button", delegate { Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", button, "action", "click")); Thread.Sleep(100); return Clicks == 1; });
                        var disabledNode = Find(snapshot, "Disabled test");
                        Test("reject_disabled", delegate { return Rejected(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", disabledNode, "action", "click")); });
                        var input = Find(snapshot, "Edit test");
                        Test("set_value", delegate { Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", input, "action", "set_value", "value", "after")); return (string)Find(Execute(Obj("op", "inspect", "expected_exe", exe, "window_id", hwnd)), "Edit test")["value"] == "after"; });
                        var checkbox = Find(snapshot, "Toggle test");
                        Test("toggle_on", delegate { Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", checkbox, "action", "toggle", "value", "on")); return (string)Find(Execute(Obj("op", "inspect", "expected_exe", exe, "window_id", hwnd)), "Toggle test")["toggle_state"] == "On"; });
                        Test("toggle_idempotent", delegate { var r = Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", checkbox, "action", "toggle", "value", "on")); return !(bool)r["action_attempted"]; });
                        Test("expand_combo", delegate { var combo = Find(snapshot, "Choice test", "ControlType.ComboBox"); Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", combo, "action", "expand")); return (string)Find(Execute(Obj("op", "inspect", "expected_exe", exe, "window_id", hwnd)), "Choice test", "ControlType.ComboBox")["expand_state"] == "Expanded"; });
                        Test("collapse_combo", delegate { var combo = Find(snapshot, "Choice test", "ControlType.ComboBox"); Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", combo, "action", "collapse")); return (string)Find(Execute(Obj("op", "inspect", "expected_exe", exe, "window_id", hwnd)), "Choice test", "ControlType.ComboBox")["expand_state"] == "Collapsed"; });
                        Test("select_tab", delegate { var tab = Find(snapshot, "Page B", "ControlType.TabItem"); Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", tab, "action", "select")); return (bool)Find(Execute(Obj("op", "inspect", "expected_exe", exe, "window_id", hwnd)), "Page B", "ControlType.TabItem")["selected"]; });
                        Test("parent_chain", delegate { var parentNames = (List<string>)button["parent_names"]; return parentNames.Contains("StudioUi isolated fixture"); });
                        var panel = Find(snapshot, "WXTEST: mouse");
                        Test("bound_custom_panel", delegate { var r = Execute(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", panel, "action", "click")); Thread.Sleep(100); return (string)r["method"] == "bound_wx_hwnd_mouse" && CustomClicks == 1; });
                        var stale = new Dictionary<string, object>(button); stale["name"] = "forged";
                        Test("reject_stale_identity", delegate { return Rejected(Obj("op", "act", "expected_exe", exe, "window_id", hwnd, "element", stale, "action", "click")); });
                        Test("reject_wrong_exe", delegate { return Rejected(Obj("op", "inspect", "expected_exe", DefaultExe, "window_id", hwnd)); });
                    }
                    catch (Exception ex) { Failures++; Results.Add(Obj("name", "fixture_exception", "passed", false, "error", ex.ToString())); }
                    finally { form.BeginInvoke((Action)delegate { form.Close(); }); }
                });
                worker.SetApartmentState(ApartmentState.MTA);
                worker.IsBackground = true;
                worker.Start();
            };
            Application.Run(form);
            Console.WriteLine(Json.Serialize(Obj("ok", Failures == 0, "failed", Failures, "tests", Results)));
            return Failures == 0 ? 0 : 1;
        }
        private static Dictionary<string, object> Find(Dictionary<string, object> snapshot, string name)
        { return Find(snapshot, name, null); }
        private static Dictionary<string, object> Find(Dictionary<string, object> snapshot, string name, string controlType)
        {
            Dictionary<string, object> found = null;
            foreach (object item in (List<object>)snapshot["elements"])
            {
                var node = (Dictionary<string, object>)item;
                if ((string)node["name"] != name || (controlType != null && (string)node["control_type"] != controlType)) continue;
                if (found != null) throw new InvalidOperationException("Duplicate fixture name: " + name);
                found = node;
            }
            if (found == null) throw new InvalidOperationException("Missing fixture element: " + name);
            return found;
        }
        private static bool Rejected(Dictionary<string, object> request) { try { Execute(request); return false; } catch { return !ActionAttempted; } }
        private static void Test(string name, Func<bool> test)
        {
            try { bool passed = test(); if (!passed) Failures++; Results.Add(Obj("name", name, "passed", passed)); }
            catch (Exception ex) { Failures++; Results.Add(Obj("name", name, "passed", false, "error", ex.GetType().Name + ": " + ex.Message)); }
        }
    }
#endif
}
