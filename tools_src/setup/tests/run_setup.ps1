param([string]$Exe, [string[]]$SetupArgs, [string]$Answer = 'yes')
# Runs the installer with arguments, reads each message box text and answers it.
Add-Type @'
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public static class Dlg {
  public delegate bool EnumProc(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc p, IntPtr l);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetDlgItemText(IntPtr h, int id, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern IntPtr GetDlgItem(IntPtr h, int id);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint m, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  public static IntPtr Find(uint pid) {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p);
      var sb = new StringBuilder(64); GetClassName(h, sb, 64);
      if (p == pid && sb.ToString() == "#32770" && IsWindowVisible(h)) { found = h; return false; } return true; }, IntPtr.Zero);
    return found; }
}
'@
$p = Start-Process -FilePath $Exe -ArgumentList $SetupArgs -PassThru
while (-not $p.HasExited) {
    $h = [Dlg]::Find([uint32]$p.Id)
    if ($h -ne [IntPtr]::Zero) {
        Start-Sleep -Milliseconds 300
        $sb = New-Object Text.StringBuilder 4096
        [void][Dlg]::GetDlgItemText($h, 0xFFFF, $sb, 4096)
        "BOX: " + $sb.ToString()
        $yes = [Dlg]::GetDlgItem($h, 6)
        $id = if ($yes -ne [IntPtr]::Zero) { if ($Answer -eq 'yes') { 6 } else { 7 } } else { 1 }
        if ([Dlg]::GetDlgItem($h, $id) -eq [IntPtr]::Zero) { $id = 2 }
        [void][Dlg]::PostMessage($h, 0x0111, [IntPtr]$id, [IntPtr]::Zero)
        Start-Sleep -Milliseconds 500
    }
    Start-Sleep -Milliseconds 200
}
"EXIT: " + $p.ExitCode
