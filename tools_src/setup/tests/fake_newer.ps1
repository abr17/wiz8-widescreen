param([string]$Game, [string]$Version, [switch]$Format2)
# Turns an installed package into what a hypothetical newer install would look like: version line
# $Version (test_all.ps1 passes VERSION with the last number + 1), a new file, a new folder with a
# file, and one more replaced original (backed up).
$m = "$Game\Wiz8Wide.installed.txt"
$lines = [Collections.Generic.List[string]](Get-Content -LiteralPath $m)
if ($lines[0] -notlike '`*version=*') { throw "unexpected first line: $($lines[0])" }
$lines[0] = "*version=$Version"
if ($Format2) { $lines.Insert(1, '*format=2') }
Set-Content -LiteralPath "$Game\Data\WIDE\NEWER.STI" -Value "fake $Version file"
New-Item -ItemType Directory -Force "$Game\Data\NEWER" | Out-Null
Set-Content -LiteralPath "$Game\Data\NEWER\EXTRA.TXT" -Value "fake $Version folder file"
$orig = 'Wiz8Patch2001_12_23_README.txt'
New-Item -ItemType Directory -Force "$Game\Wiz8Wide.backup" | Out-Null
Copy-Item -LiteralPath "$Game\$orig" -Destination "$Game\Wiz8Wide.backup\$orig"
Set-Content -LiteralPath "$Game\$orig" -Value "replaced by fake $Version"
$lines.AddRange([string[]]@('+Data\NEWER', 'Data\NEWER\EXTRA.TXT', 'Data\WIDE\NEWER.STI', $orig))
[IO.File]::WriteAllText($m, ($lines -join "`r`n") + "`r`n", (New-Object Text.UTF8Encoding $false))
"faked $Version" + $(if ($Format2) { ' (format 2)' } else { '' }) + ": " + ((Get-Content -LiteralPath $m -TotalCount 2) -join ' | ')
