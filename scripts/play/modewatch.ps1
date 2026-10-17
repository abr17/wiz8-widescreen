# Watches the monitor mode (resolution) for N seconds and prints each change.
# Used to verify borderless mode: when it works correctly the mode never changes.
#   .\modewatch.ps1 -Seconds 40
param([int]$Seconds = 40, [int]$IntervalMs = 200)
Add-Type -Namespace W8 -Name Mode -MemberDefinition @'
[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
[DllImport("gdi32.dll")] public static extern int GetDeviceCaps(System.IntPtr hdc, int index);
[DllImport("user32.dll")] public static extern System.IntPtr GetDC(System.IntPtr hwnd);
[DllImport("user32.dll")] public static extern int ReleaseDC(System.IntPtr hwnd, System.IntPtr hdc);
'@ -ErrorAction SilentlyContinue
[void][W8.Mode]::SetProcessDPIAware()
$last = ''
$sw = [Diagnostics.Stopwatch]::StartNew()
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
    $dc = [W8.Mode]::GetDC([IntPtr]::Zero)
    # DESKTOPHORZRES=118, DESKTOPVERTRES=117, BITSPIXEL=12 — actual monitor mode
    $m = '{0}x{1}x{2}' -f [W8.Mode]::GetDeviceCaps($dc, 118), [W8.Mode]::GetDeviceCaps($dc, 117), [W8.Mode]::GetDeviceCaps($dc, 12)
    [void][W8.Mode]::ReleaseDC([IntPtr]::Zero, $dc)
    if ($m -ne $last) { '{0,6:N1}s  {1}' -f $sw.Elapsed.TotalSeconds, $m; $last = $m }
    Start-Sleep -Milliseconds $IntervalMs
}
