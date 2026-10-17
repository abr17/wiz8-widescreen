# Screenshot of the game window's client area (for windowed and full-screen modes, where
# the in-game GShot does not work). pwsh -File scripts\play\win_shot.ps1 <out.png> [-Width 1280]
param([string]$Out, [int]$Width = 1280)
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public class W8WinShot {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetClientRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ClientToScreen(IntPtr h, ref POINT p);
  public struct RECT { public int L, T, R, B; } public struct POINT { public int X, Y; } }
'@
[W8WinShot]::SetProcessDPIAware() | Out-Null
$h = (Get-Process Wiz8 | Select-Object -First 1).MainWindowHandle
$r = New-Object W8WinShot+RECT; [W8WinShot]::GetClientRect($h, [ref]$r) | Out-Null
$p = New-Object W8WinShot+POINT; [W8WinShot]::ClientToScreen($h, [ref]$p) | Out-Null
$b = [Drawing.Bitmap]::new($r.R, $r.B); $g = [Drawing.Graphics]::FromImage($b)
$g.CopyFromScreen($p.X, $p.Y, 0, 0, $b.Size)
$hgt = [int]($r.B * $Width / $r.R)
$s = [Drawing.Bitmap]::new($Width, $hgt); $g2 = [Drawing.Graphics]::FromImage($s)
$g2.InterpolationMode = 'HighQualityBicubic'; $g2.DrawImage($b, 0, 0, $Width, $hgt)
$s.Save($Out); "client $($r.R)x$($r.B) at $($p.X),$($p.Y)"
