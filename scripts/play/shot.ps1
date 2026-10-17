# Full-screen screenshot into docs\screens\<folder>\ (default: baseline).
# Usage: C:\dev\wiz8-ws\scripts\play\shot.ps1 [-Folder baseline] [-Delay 3]
param([string]$Folder = 'baseline', [int]$Delay = 0)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type -Namespace W -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();'
[void][W.Dpi]::SetProcessDPIAware()   # otherwise at 150% scaling the screenshot gets cropped
Start-Sleep -Seconds $Delay
$b = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Location, [System.Drawing.Point]::Empty, $b.Size)
$dir = Join-Path $PSScriptRoot "..\..\docs\screens\$Folder"
New-Item -ItemType Directory -Force $dir | Out-Null
$file = Join-Path (Resolve-Path $dir) ("{0:yyyyMMdd-HHmmss}.png" -f (Get-Date))
$bmp.Save($file, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
$file
