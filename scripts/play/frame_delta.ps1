# Frame rate of the original: reads the m_frame_delta field from Wiz8.exe memory
# of g_game_time_accumulator (0x006598bc, offset 0x28; unit = 0.1 s).
#   powershell -File frame_delta.ps1 [-Seconds 2] [-Name Wiz8]
# Only reads memory of our own running game process.
param([double]$Seconds = 2, [string]$Name = 'Wiz8', [int]$Global = 0x006598bc)
Add-Type -Namespace W8 -Name Mem -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern System.IntPtr OpenProcess(int access, bool inherit, int pid);
[DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(System.IntPtr h, System.IntPtr addr, byte[] buf, int size, out int read);
[DllImport("kernel32.dll")] public static extern bool CloseHandle(System.IntPtr h);
'@ -ErrorAction SilentlyContinue
$p = Get-Process $Name -ErrorAction Stop | Select-Object -First 1
$h = [W8.Mem]::OpenProcess(0x0410, $false, $p.Id)
$buf = New-Object byte[] 4; $n = 0
function ReadU32([long]$a) { [void][W8.Mem]::ReadProcessMemory($h, [IntPtr]$a, $buf, 4, [ref]$n); [BitConverter]::ToUInt32($buf, 0) }
function ReadF32([long]$a) { [void][W8.Mem]::ReadProcessMemory($h, [IntPtr]$a, $buf, 4, [ref]$n); [BitConverter]::ToSingle($buf, 0) }
$acc = ReadU32 $Global
$elapsedAddr = $acc + 0x30
$sw = [Diagnostics.Stopwatch]::StartNew()
$e0 = ReadF32 $elapsedAddr
$samples = New-Object System.Collections.Generic.List[float]
while ($sw.Elapsed.TotalSeconds -lt $Seconds) { $samples.Add((ReadF32 ($acc + 0x28))); Start-Sleep -Milliseconds 1 }
$e1 = ReadF32 $elapsedAddr
[void][W8.Mem]::CloseHandle($h)
$nz = $samples | Where-Object { $_ -gt 0 }
$avg = if ($nz) { ($nz | Measure-Object -Average).Average } else { 0 }
'frame_delta: samples={0} nonzero={1} avg={2:N4} min={3:N4} max={4:N4} (0.1 s units)' -f $samples.Count, @($nz).Count, $avg, ($nz | Measure-Object -Minimum).Minimum, ($nz | Measure-Object -Maximum).Maximum
'game time elapsed {0:N3} units over {1:N2} s; approx fps {2:N0}' -f ($e1 - $e0), $sw.Elapsed.TotalSeconds, $(if ($avg -gt 0) { 10 / $avg } else { 0 })
