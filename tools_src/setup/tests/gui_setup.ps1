param([string]$Exe, [string]$Folder, [ValidateSet('none', 'install', 'uninstall')][string]$Click = 'none', [string]$Shot, [string]$Answer = 'yes', [string]$BoxShot,
      [ValidateSet('keep', 'on', 'off')][string]$Diag = 'keep')
# Opens the installer window, types the folder, reads the install button, status texts and the
# diagnostics checkbox, optionally sets that checkbox (-Diag on|off, as the player would),
# optionally takes a window-only screenshot, optionally presses a button and answers the boxes.
Add-Type -ReferencedAssemblies System.Drawing @'
using System; using System.Text; using System.Runtime.InteropServices; using System.Drawing;
public static class G {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetDlgItemText(IntPtr h, int id, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h, int id);
  [DllImport("user32.dll")] public static extern bool IsWindowEnabled(IntPtr h);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, string l);
  [DllImport("user32.dll")] public static extern IntPtr SendMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr dc, uint f);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
  public static IntPtr Find(uint pid, string cls) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
      var sb = new StringBuilder(64); GetClassName(h, sb, 64);
      if (p == pid && sb.ToString() == cls && IsWindowVisible(h)) { found = h; return false; } return true; }, IntPtr.Zero);
    return found; }
  public static string Text(IntPtr h) { var sb = new StringBuilder(1024); GetWindowText(h, sb, 1024); return sb.ToString(); }
  public static string Item(IntPtr h, int id) { var sb = new StringBuilder(4096); GetDlgItemText(h, id, sb, 4096); return sb.ToString(); }
  public static void Shot(IntPtr h, string path) {
    RECT r; GetWindowRect(h, out r);
    using (var bmp = new Bitmap(r.R - r.L, r.B - r.T)) {
      using (var g = Graphics.FromImage(bmp)) { IntPtr dc = g.GetHdc(); PrintWindow(h, dc, 2); g.ReleaseHdc(dc); }
      bmp.Save(path, System.Drawing.Imaging.ImageFormat.Png); } }
}
'@
function Boxes($p) {
    # answers every message box until none appears for 3 s (the first one may take up to 20 s;
    # after a question answered "yes" the install runs first, so its done box gets up to 60 s)
    $seen = 0; $idle = 0; $limit = 15
    while (($seen -eq 0 -and $idle -lt 100) -or ($seen -gt 0 -and $idle -lt $limit)) {
        $h = [G]::Find([uint32]$p.Id, '#32770')
        if ($h -ne [IntPtr]::Zero) {
            Start-Sleep -Milliseconds 300
            "BOX [" + [G]::Text($h) + "]: " + [G]::Item($h, 0xFFFF)
            if ($BoxShot -and $seen -eq 0) { [G]::Shot($h, $BoxShot); "BOXSHOT: $BoxShot" }
            $yes = [G]::GetDlgItem($h, 6) -ne [IntPtr]::Zero
            $id = if ($yes) { if ($Answer -eq 'yes') { 6 } else { 7 } } else { 1 }
            if ($yes) { "  -> answered $Answer" }
            $limit = if ($yes -and $Answer -eq 'yes') { 300 } else { 15 }
            if ([G]::GetDlgItem($h, $id) -eq [IntPtr]::Zero) { $id = 2 }
            [void][G]::PostMessage($h, 0x0111, [IntPtr]$id, [IntPtr]::Zero)
            Start-Sleep -Milliseconds 500
            $seen++; $idle = 0
            continue
        }
        Start-Sleep -Milliseconds 200
        $idle++
    }
    if ($seen -eq 0) { 'no message box' }
}
function Report($w) {
    "TITLE: " + [G]::Text($w)
    "BUTTON: " + [G]::Item($w, 102)
    "UNINSTALL enabled: " + [G]::IsWindowEnabled([G]::GetDlgItem($w, 103))
    "STATUS: " + ([G]::Item($w, 105) -replace "`r`n", ' | ')
    $box = [G]::GetDlgItem($w, 106)
    # BM_GETCHECK
    "DIAG: checked " + ([int][G]::SendMessage($box, 0x00F0, [IntPtr]::Zero, [IntPtr]::Zero) -eq 1) + ", enabled " + [G]::IsWindowEnabled($box)
}
[void][G]::SetProcessDPIAware()
$p = Start-Process -FilePath $Exe -PassThru
$w = [IntPtr]::Zero
for ($i = 0; $i -lt 50 -and $w -eq [IntPtr]::Zero; $i++) { Start-Sleep -Milliseconds 200; $w = [G]::Find([uint32]$p.Id, 'Wiz8WideSetup') }
if ($w -eq [IntPtr]::Zero) { 'no window'; return }
$combo = [G]::GetDlgItem($w, 100)
[void][G]::SendMessage($combo, 0x000C, [IntPtr]::Zero, $Folder)               # WM_SETTEXT
[void][G]::SendMessage($w, 0x0111, [IntPtr](100 -bor (5 -shl 16)), $combo)    # CBN_EDITCHANGE
Start-Sleep -Milliseconds 300
Report $w
if ($Diag -ne 'keep') {
    # BM_SETCHECK: the installer reads the box only when Install is pressed
    $box = [G]::GetDlgItem($w, 106)
    [void][G]::SendMessage($box, 0x00F1, [IntPtr]$(if ($Diag -eq 'on') { 1 } else { 0 }), [IntPtr]::Zero)
    "DIAG set ${Diag}: checked " + ([int][G]::SendMessage($box, 0x00F0, [IntPtr]::Zero, [IntPtr]::Zero) -eq 1)
}
if ($Shot) { [G]::Shot($w, $Shot); "SHOT: $Shot" }
if ($Click -ne 'none') {
    $id = if ($Click -eq 'install') { 102 } else { 103 }
    [void][G]::PostMessage($w, 0x0111, [IntPtr]$id, [IntPtr]::Zero)
    Boxes $p
    Start-Sleep -Milliseconds 500
    "-- after --"
    Report $w
}
[void][G]::PostMessage($w, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)               # WM_CLOSE
$p.WaitForExit(5000) | Out-Null
"EXIT: " + $p.ExitCode
