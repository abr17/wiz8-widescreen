# w8diff: comparing port functions with the original Wiz8.exe

> Internal tool: requires a built port (`scripts\build\build-decomp.ps1`). The results below are from the 2026-10-13 run, before the latest changes.

The harness calls the same game function **in the original Wiz8.exe** (GOG 1.2.4) and
**in our Wiz8Runtime.exe build** with identical inputs and compares the result:
return value, modified memory, exceptions, triggered asserts.
Any mismatch is a place where the port behaves differently from the original.

## How it works

* The core is `decomp/src/w8diff/w8diff_core.c` (C, MSVC x86, `__try` + `__asm`).
  * It is compiled into the port: `RenderFrame` calls `W8DiffPortPoll()` once per frame
    (enabled by `wiz8wide.ini` `[Debug] DiffHarness=1`).
  * It is brought into the original by `w8diff.dll` (`scripts/w8diff/build_dll.ps1`, same
    MSVC). With `wiz8ws.ini` `[Debug] DiffHarness=1`, `version.dll` (the patch) installs a hook
    on `RenderFrame` (0x00426790) and calls `W8DiffRetailPoll` once per frame.
* Both sides wait for the file `w8diff_<retail|port>.req`, read the plan
  `w8diff_plan_<proc>.txt`, wait 60 frames on the game's main screen, run the cases
  (~150 ms per frame) and write `w8diff_out_<proc>.txt`, and at the end `w8diff_done_<proc>.txt`.
* Each case: apply `set/setb/setp/fill` (remembering the old bytes), `srand(seed)`,
  set the FPU control word, call the function under `__try`, record eax/edx/st0,
  the changed bytes of the `cap` regions, the line numbers of asserts (srAssertFail is hooked),
  and **roll all memory back**. Cases are independent.
* The game loads the same save via the `/LOAD` switch (the script puts the chosen
  save into `Saves\Quick 1.SAV`), so the world state is identical.

## Running

```
powershell -File scripts\w8diff\build_dll.ps1          # w8diff.dll (after changing the core)
powershell -File scripts\build\build-decomp.ps1              # the port (core inside)
powershell -File build.ps1                             # version.dll
powershell -File scripts\w8diff\run.ps1 -Specs smoke,gameplay_code [-Save "Before Bayjin"]
```

`run.ps1` installs fresh builds into `games\work`, generates plans, runs the original,
then the port, compares (`scripts/w8diff/compare.py`) and writes
`build\w8diff\report.txt` (per function, first mismatches with their inputs) and `report.json`.

Character corpus (49 characters from player saves): `build\w8diff\corpus\*.bin`,
built with `run.ps1 -Corpus -Save "<name>"`.

## How to write a spec (`scripts/w8diff/specs/<name>.py`)

A module with a `cases(ctx)` function. Example: `specs/gameplay_code.py`.

```python
def cases(ctx):
    calc = ctx.fn(0x004ee220)                     # function address in the original
    for i in range(ctx.n(300)):
        r = ctx.rng('calc', i)                    # deterministic random.Random
        c = ctx.case('calcattacks.%d' % i, calc, conv='c', ret='v')
        party = ctx.set_party(c, r)               # 8 party slots = corpus characters
        slot, blob, name = party[r.randrange(6)]
        blob.u32(0xe5 + 4, r.randrange(1, 126))   # change a field (offsets - layout.ps1)
        c.set(ctx.char(slot), bytes(blob))
        c.arg(ctx.char(slot))
        c.cap(ctx.char(slot), 0x1862, 'char')     # compare the character after the call
```

### ctx
* `ctx.fn(retail_addr, port_symbol=None)` - function by the address from `// FUNCTION: WIZ8`.
  The port address is looked up in `build\vc2022\Wiz8Runtime.map`. If the function is inlined (not in
  the map), it cannot be called; test its caller instead.
* `ctx.g(name)` - address of a global variable by its name from `// GLOBAL: WIZ8`.
* `ctx.char(slot)` - `g_status.buffers.Char[slot]` (W8Character, 0x1862 bytes).
* `ctx.scratch(n)` - n-th buffer 0..7 of 0x10000 bytes, zeroed before each case.
* `ctx.rng(*key)`, `ctx.n(count)` (scaled by `--scale`), `ctx.pick_char(rng)`,
  `ctx.set_party(case, rng, slots=range(8))`.

### Addr (an address, computed separately in each exe)
`ctx.g('g_status') + 4` - offset; `.deref()` - read a dword; chains:
`(ctx.g('g_item_records')).deref() + item_id * 0x1bf`.

### Case
* `conv`: `'c'` cdecl, `'s'` stdcall, `'t'` thiscall (first arg = this),
  `'f'` fastcall (first two args = ecx, edx). Look at `ret N` and `ecx` in the asm.
* `ret`: `'v'` void, `'i'` int32, `'b'`/`'u8'` al only, `'i8'`, `'u16'`, `'i16'`,
  `'q'` edx:eax, `'f'` float in st0 (compared as float32), `'d'` double in st0,
  `'p'` pointer (32 bytes at it are compared), `'w'`/`'c'` wide/narrow string.
  Struct returned through a hidden pointer: pass `ctx.scratch(k)` as the first
  argument (after `this` for thiscall) and `cap` it.
* `c.arg(v)` - int, `Addr`, `F32(x)`, `F64(x)` (two slots).
* `c.set(addr, bytes)`, `c.setb(addr, bytes)` (large repeating blocks),
  `c.setp(addr, value_addr)` (write an address - e.g. a pointer to a struct in
  scratch), `c.fill(addr, len, byte)`, `c.keep(addr, len)` - all of it is rolled back.
* `c.cap(addr, len, name, ignore=[offsets of dword pointers])` - compare the changes.
* `c.dump(addr, len, name)` - compare the bytes after the call in full.
* `c.note(**kw)` - labels for the report.

### Rules (otherwise you get false mismatches or crashes)
1. **All inputs must be identical in both exes.** Put characters from the corpus
   (`set_party`); scalar globals that the function reads (difficulty, mode
   flags, time, gXStatus...) must be `set` explicitly. Do not rely on things that change on their own:
   monster positions, timers, camera, animations.
2. Pointers differ between the exes: in `cap` specify `ignore` for pointer fields,
   and pass a pointer to a struct via `setp`, not as a number.
3. Whatever the function writes must be covered by `cap` (otherwise we will not see the mismatch).
4. Do not test: opening windows/dialogs/screens, loading files, movies, sound as the
   main effect, creating/deleting world objects, combat start/end, level change,
   input. Such functions will break the game state for the following cases.
5. 100-400 cases per function: ordinary values + boundaries from the code
   (0, 1, comparison thresholds, maximum, negatives for signed values).
6. Checking a spec without the game:
   `python -I scripts\w8diff\gen_plan.py --specs <name> --out build\w8diff\check\<name> --meta build\w8diff\check\<name>\meta.json --no-ready`
7. Field offsets - `powershell -File scripts\w8diff\layout.ps1 -Header wiz8/layouts/character.h -Expr "offsetof(W8Character, skills); sizeof(W8Character)"`
   (several headers separated by commas, expressions separated by `;`).

## Plan and output format
Described in the header of `w8diff_core.c`.

## Floating-point noise
VC6 kept intermediate values in 80-bit x87 registers; MSVC 2022 rounds to
float on every assignment. So float results can differ in the last
bits (NormalizeAngle(1.0): original 1.0000002, port 1.0). The comparison treats a difference
of up to 4 ULP (float) or 1e-9 relative (double) as "fp-noise" and does not record it as a
mismatch. For float fields in memory, specify `floats=[offsets]` in `cap`/`dump`.
For a full comparison of a region without rollback, use `keep` + `dump`.

## Hangs
Before each call the core writes `S <id>`. If the output does not grow for 45 s and the last
line is `S ...` (or the game crashed), `run.ps1` marks the case HANG/CRASH, kills the game
and restarts it with the plan `resume <N>`. Example: NormalizeAngle(NaN) in the original
loops forever, the port returns NaN.

## Run results (2026-10-13)

32 specs, 754 functions, ~173 thousand cases (`run_all.ps1`, batches of 4).

| Run | Cases with mismatches | What was done |
|---|---|---|
| 1 | 6 682 | analysis by agents: 116 port bugs, 42 x87 precision, 19 spec errors |
| 2 | 667 | androids in character slots, reading "non-canonical" bools |
| 3 | 1 | SNaN in the input: the original quiets it by loading through x87, the port copies it as is |

Main causes worth remembering for new specs and port changes:
* "Before Bayjin" has no live monsters (`plsMonsterList->iNumUsed == 0`, `data[]` is
  heap garbage). A spec that needs live monsters sets `SAVE = 'Before Nessie'`.
* The original compares `highest_condition` as unsigned (`jb/jae`): `W8Condition` is now
  `enum : unsigned int`.
* x87 intermediate values (function result in st0, `fild`/`fmul` before a single `fstp`)
  are kept in `double` in the port; the FPU of both exes is 53-bit (`cw-native 027f`), so
  the match is bit-exact. Truncation to int is like VC6 `_ftol` (low word of int64).
* A `bool` argument that the original tests as a byte (`test al,al`) is read through
  `volatile unsigned char`: otherwise MSVC assumes it is 0/1 and folds the check.
* An android is only a hired NPC: a character slot has `XChar.npc_index = -1`, while
  `CalcAttacks` calls `GetNpcState(npc_index)`; the spec gives such a slot
  an index within the array bounds.
* An exception inside a function leaves a half-done state that the rollback does not
  restore; a single crash can corrupt later cases of the same run.
* `compare.py` reconstructs floats from the old bytes (the core writes `off:new/old`)
  and itself treats the character recovery fields (`0xb69..0xba9`) as floats.
