# Sample EIP and part of the stack of a hung Wiz8Runtime.exe thread (32-bit process)
# several times and map the addresses to functions via build\vc2022\Wiz8Runtime.map.
#   pwsh -File sample_eip.ps1 [-Samples 8] [-StackDwords 400]
# Only reads our own game's memory (Suspend/Resume for milliseconds).
param([int]$Samples = 8, [int]$StackDwords = 400, [string]$Name = 'Wiz8Runtime')
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class W8Dbg {
    [StructLayout(LayoutKind.Sequential)]
    public struct WOW64_CONTEXT {
        public uint ContextFlags, Dr0, Dr1, Dr2, Dr3, Dr6, Dr7;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 112)] public byte[] FloatSave;
        public uint SegGs, SegFs, SegEs, SegDs, Edi, Esi, Ebx, Edx, Ecx, Eax, Ebp, Eip, SegCs, EFlags, Esp, SegSs;
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 512)] public byte[] ExtendedRegisters;
    }
    [DllImport("kernel32.dll")] public static extern IntPtr OpenThread(int access, bool inherit, int id);
    [DllImport("kernel32.dll")] public static extern IntPtr OpenProcess(int access, bool inherit, int id);
    [DllImport("kernel32.dll")] public static extern int SuspendThread(IntPtr h);
    [DllImport("kernel32.dll")] public static extern int ResumeThread(IntPtr h);
    [DllImport("kernel32.dll")] public static extern bool Wow64GetThreadContext(IntPtr h, ref WOW64_CONTEXT ctx);
    [DllImport("kernel32.dll")] public static extern bool ReadProcessMemory(IntPtr h, IntPtr addr, byte[] buf, int size, out int read);
    [DllImport("kernel32.dll")] public static extern bool CloseHandle(IntPtr h);
}
'@ -ErrorAction SilentlyContinue
$p = Get-Process $Name -ErrorAction Stop | Select-Object -First 1
$t = $p.Threads | Sort-Object TotalProcessorTime -Descending | Select-Object -First 1
$hp = [W8Dbg]::OpenProcess(0x0410, $false, $p.Id)
$ht = [W8Dbg]::OpenThread(0x005A, $false, $t.Id)   # SUSPEND_RESUME | GET_CONTEXT | QUERY_INFORMATION
$addrs = New-Object System.Collections.Generic.List[string]
for ($s = 0; $s -lt $Samples; $s++) {
    [void][W8Dbg]::SuspendThread($ht)
    $ctx = New-Object W8Dbg+WOW64_CONTEXT
    $ctx.FloatSave = New-Object byte[] 112; $ctx.ExtendedRegisters = New-Object byte[] 512
    $ctx.ContextFlags = 0x10007   # WOW64_CONTEXT_FULL
    [void][W8Dbg]::Wow64GetThreadContext($ht, [ref]$ctx)
    $buf = New-Object byte[] ($StackDwords * 4); $n = 0
    [void][W8Dbg]::ReadProcessMemory($hp, [IntPtr][long]$ctx.Esp, $buf, $buf.Length, [ref]$n)
    [void][W8Dbg]::ResumeThread($ht)
    $line = 'eip={0:x8} esp={1:x8}' -f $ctx.Eip, $ctx.Esp
    $addrs.Add(('{0:x8}' -f $ctx.Eip))
    if ($s -eq 0) {
        for ($i = 0; $i -lt $n / 4; $i++) {
            $v = [BitConverter]::ToUInt32($buf, $i * 4)
            if ($v -ge 0x401000 -and $v -lt 0x600000) { $addrs.Add(('{0:x8}' -f $v)) }
        }
    }
    $line
    Start-Sleep -Milliseconds 150
}
[void][W8Dbg]::CloseHandle($ht); [void][W8Dbg]::CloseHandle($hp)
$env:PYTHONIOENCODING = 'utf-8'
& python -I (Join-Path $PSScriptRoot 'map_lookup.py') (Join-Path $PSScriptRoot '..\..\build\vc2022\Wiz8Runtime.map') @($addrs | Select-Object -Unique -First 60)
