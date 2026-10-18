param([string]$Game, [string]$Ref = 'C:\dev\wiz8-ws\games\reference', [string]$Files, [switch]$Uninstalled)
# Compares a test game folder with the pristine reference and (when installed) with the package files.
function Hashes($dir) {
    $h = @{}
    foreach ($f in Get-ChildItem -LiteralPath $dir -Recurse -File) {
        $h[$f.FullName.Substring($dir.Length + 1)] = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash
    }
    $h
}
$g = Hashes $Game; $r = Hashes $Ref
$problems = 0
if ($Uninstalled) {
    foreach ($k in $r.Keys) { if (-not $g.ContainsKey($k)) { "MISSING $k"; $problems++ } elseif ($g[$k] -ne $r[$k]) { "CHANGED $k"; $problems++ } }
    foreach ($k in $g.Keys) { if (-not $r.ContainsKey($k)) { "EXTRA $k"; $problems++ } }
    $dirsG = Get-ChildItem -LiteralPath $Game -Recurse -Directory | ForEach-Object { $_.FullName.Substring($Game.Length + 1) }
    $dirsR = Get-ChildItem -LiteralPath $Ref -Recurse -Directory | ForEach-Object { $_.FullName.Substring($Ref.Length + 1) }
    foreach ($d in $dirsG) { if ($dirsR -notcontains $d) { "EXTRA DIR $d"; $problems++ } }
    "uninstalled check: $problems problem(s), $($g.Count) files"
    return
}
$p = Hashes $Files
$manifest = Get-Content -LiteralPath "$Game\Wiz8Wide.installed.txt"
"manifest line 1: $($manifest[0]); entries: $($manifest.Count)"
foreach ($k in $p.Keys) {
    if (-not $g.ContainsKey($k)) { "NOT INSTALLED $k"; $problems++ }
    elseif ($g[$k] -ne $p[$k] -and $k -ne 'wiz8wide.ini') { "DIFFERS FROM PACKAGE $k"; $problems++ }
    if ($manifest -notcontains $k) { "NOT IN MANIFEST $k"; $problems++ }
}
$backup = "$Game\Wiz8Wide.backup"
foreach ($k in $g.Keys) {
    if ($k -like 'Wiz8Wide.backup\*') {
        $orig = $k.Substring('Wiz8Wide.backup\'.Length)
        if (-not $r.ContainsKey($orig)) { "BACKUP OF NON-ORIGINAL $orig"; $problems++ }
        elseif ($r[$orig] -ne $g[$k]) { "BACKUP DIFFERS FROM ORIGINAL $orig"; $problems++ }
    } elseif (-not $p.ContainsKey($k) -and $k -ne 'Wiz8Wide.installed.txt') {
        if (-not $r.ContainsKey($k)) { "EXTRA $k"; $problems++ }
        elseif ($r[$k] -ne $g[$k]) { "CHANGED ORIGINAL $k" }
    }
}
foreach ($k in $r.Keys) { if ($p.ContainsKey($k) -and -not $g.ContainsKey("Wiz8Wide.backup\$k")) { "NO BACKUP FOR REPLACED $k"; $problems++ } }
"installed check: $problems problem(s); package files $($p.Count)"
