# Main-thread stack of a hung/stopped Wiz8.exe (hybrid): original addresses
# are mapped to functions via port annotations, wiz8hy.dll addresses via wiz8hy.map.
#   powershell -File scripts\hybrid\stack_retail.ps1 [-StackDwords 2000]
param([int]$StackDwords = 3000, [string]$Name = 'Wiz8')
$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class W8Dbg2 {
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
}
'@ -ErrorAction SilentlyContinue
$p = Get-Process $Name -ErrorAction Stop | Select-Object -First 1
$t = $p.Threads | Sort-Object StartTime | Select-Object -First 1
$hp = [W8Dbg2]::OpenProcess(0x0410, $false, $p.Id)
$ht = [W8Dbg2]::OpenThread(0x005A, $false, $t.Id)
[void][W8Dbg2]::SuspendThread($ht)
$ctx = New-Object W8Dbg2+WOW64_CONTEXT
$ctx.FloatSave = New-Object byte[] 112; $ctx.ExtendedRegisters = New-Object byte[] 512; $ctx.ContextFlags = 0x10007
[void][W8Dbg2]::Wow64GetThreadContext($ht, [ref]$ctx)
$buf = New-Object byte[] ($StackDwords * 4); $n = 0
[void][W8Dbg2]::ReadProcessMemory($hp, [IntPtr][long]$ctx.Esp, $buf, $buf.Length, [ref]$n)
[void][W8Dbg2]::ResumeThread($ht)
$dll = $p.Modules | Where-Object { $_.ModuleName -eq 'wiz8hy.dll' } | Select-Object -First 1
$dllBase = if ($dll) { [long]$dll.BaseAddress } else { 0 }
$vals = @(('{0:x8}' -f $ctx.Eip))
for ($i = 0; $i -lt $n / 4; $i++) { $vals += ('{0:x8}' -f [BitConverter]::ToUInt32($buf, $i * 4)) }
$env:PYTHONIOENCODING = 'utf-8'
$vals | & python -I (Join-Path $PSScriptRoot 'symbolize.py') ('{0:x}' -f $dllBase)
