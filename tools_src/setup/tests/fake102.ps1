param([string]$Game, [switch]$Format2)
# Turns an installed 1.0.1 into what a hypothetical 1.0.2 install would look like: version line
# 1.0.2, a new file, a new folder with a file, and one more replaced original (backed up).
$m = "$Game\Wiz8Wide.installed.txt"
$lines = [Collections.Generic.List[string]](Get-Content -LiteralPath $m)
if ($lines[0] -notlike '`*version=*') { throw "unexpected first line: $($lines[0])" }
$lines[0] = '*version=1.0.2'
if ($Format2) { $lines.Insert(1, '*format=2') }
Set-Content -LiteralPath "$Game\Data\WIDE\NEW102.STI" -Value 'fake 1.0.2 file'
New-Item -ItemType Directory -Force "$Game\Data\NEW102" | Out-Null
Set-Content -LiteralPath "$Game\Data\NEW102\EXTRA.TXT" -Value 'fake 1.0.2 folder file'
$orig = 'Wiz8Patch2001_12_23_README.txt'
New-Item -ItemType Directory -Force "$Game\Wiz8Wide.backup" | Out-Null
Copy-Item -LiteralPath "$Game\$orig" -Destination "$Game\Wiz8Wide.backup\$orig"
Set-Content -LiteralPath "$Game\$orig" -Value 'replaced by fake 1.0.2'
$lines.AddRange([string[]]@('+Data\NEW102', 'Data\NEW102\EXTRA.TXT', 'Data\WIDE\NEW102.STI', $orig))
[IO.File]::WriteAllText($m, ($lines -join "`r`n") + "`r`n", (New-Object Text.UTF8Encoding $false))
"faked 1.0.2" + $(if ($Format2) { ' (format 2)' } else { '' }) + ": " + ((Get-Content -LiteralPath $m -TotalCount 2) -join ' | ')
