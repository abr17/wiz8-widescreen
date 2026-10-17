# Game screenshot with boosted brightness (like the owner "cranking up gamma") - to find seams.
#   pwsh -File scripts\play\boost_shot.ps1 <shot.jpg> <out.png> [-Gamma 0.45] [-Width 1280] [-Crop "x,y,w,h"]
param([string]$In, [string]$Out, [double]$Gamma = 0.45, [int]$Width = 1280, [string]$Crop = '')
Add-Type -AssemblyName System.Drawing
$src = [Drawing.Bitmap]::new((Resolve-Path $In).Path)
if ($Crop) {
    $c = $Crop -split ',' | ForEach-Object { [int]$_ }
    $tmp = $src.Clone([Drawing.Rectangle]::new($c[0], $c[1], $c[2], $c[3]), $src.PixelFormat)
    $src.Dispose(); $src = $tmp
}
$h = [int]($src.Height * $Width / $src.Width)
$bmp = [Drawing.Bitmap]::new($Width, $h, [Drawing.Imaging.PixelFormat]::Format24bppRgb)
$g = [Drawing.Graphics]::FromImage($bmp); $g.InterpolationMode = 'HighQualityBicubic'
$g.DrawImage($src, 0, 0, $Width, $h); $g.Dispose(); $src.Dispose()
$lut = New-Object byte[] 256
for ($i = 0; $i -lt 256; $i++) { $lut[$i] = [byte][Math]::Min(255, [Math]::Round([Math]::Pow($i / 255.0, $Gamma) * 255)) }
$rect = [Drawing.Rectangle]::new(0, 0, $Width, $h)
$data = $bmp.LockBits($rect, 'ReadWrite', $bmp.PixelFormat)
$n = $data.Stride * $h; $buf = New-Object byte[] $n
[Runtime.InteropServices.Marshal]::Copy($data.Scan0, $buf, 0, $n)
for ($i = 0; $i -lt $n; $i++) { $buf[$i] = $lut[$buf[$i]] }
[Runtime.InteropServices.Marshal]::Copy($buf, 0, $data.Scan0, $n)
$bmp.UnlockBits($data)
$bmp.Save($Out); $bmp.Dispose()
