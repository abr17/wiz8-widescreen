# Go to the name page of character creation (priest, human, female).
# . play.ps1 before calling. Coordinates are in pixels of the 1280x800 downscaled screenshot.
function G([int]$sx, [int]$sy) { Click640 ([int]($sx * 0.6 - 64)) ([int]($sy * 0.6)) }
# New game with premade characters: the first 6 in the list (Mira is already created), "Normal", no intro movie.
function Start-QuickParty {
    Click640 323 205; Start-Sleep 5
    G 820 113; Start-Sleep -Milliseconds 700
    for ($i = 0; $i -lt 6; $i++) { G 800 580; Start-Sleep 2 }
    G 845 752; Start-Sleep 4
    G 902 145; Start-Sleep -Milliseconds 500
    G 845 752; Start-Sleep 10
    Key 'ESC' 80; Start-Sleep 22
}
function Goto-NamePage {
    Click640 323 205; Start-Sleep 5                     # new game -> party
    G 800 538; Start-Sleep 4                            # create character
    for ($i = 0; $i -lt 12; $i++) { G 755 113; Start-Sleep -Milliseconds 250 }   # class: priest
    G 755 198; Start-Sleep -Milliseconds 400            # race: human
    G 755 284; Start-Sleep -Milliseconds 400; G 755 284; Start-Sleep -Milliseconds 400  # gender: female
    foreach ($p in @(@(175, 15), @(198, 10), @(245, 5), @(128, 5), @(222, 3))) { for ($i = 0; $i -lt $p[1]; $i++) { G 1125 $p[0]; Start-Sleep -Milliseconds 100 } }
    G 1135 775; Start-Sleep 3                           # -> spells
    G 900 593; Start-Sleep -Milliseconds 500; G 900 571; Start-Sleep -Milliseconds 500
    G 1135 775; Start-Sleep 3                           # -> skills
    foreach ($p in @(@(781, 308), @(781, 448), @(1140, 100))) { for ($i = 0; $i -lt 5; $i++) { G $p[0] $p[1]; Start-Sleep -Milliseconds 120 } }
    G 1135 775; Start-Sleep 3                           # -> portrait and name
}
