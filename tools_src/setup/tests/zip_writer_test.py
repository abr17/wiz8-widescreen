#!/usr/bin/env python3
"""Checks tools_src/setup/zip_writer.h: builds zip_writer_test.cpp, packs generated files with
it and reads the archives back with Python's zipfile (and `unzip -t` when there is one); then
what the writer must refuse: a file that takes the archive over its limit, a file without a
name, a 65535th file.

    python3 zip_writer_test.py [--rounds N] [--exe path-to-a-built-zip_writer_test]

Needs g++ (or --exe: for example a Windows build run through Wine, given as a small script).
Prints one line per check and "RESULT: n passed, m failed"; exit code 1 on a failure.
"""
import argparse
import os
import random
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
passed = failed = 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    print(("PASS " if ok else "FAIL ") + name + ((": " + detail) if detail and not ok else ""))


def log_text(rng, lines):
    words = ["[Display]", "Mode=borderless", "frame", "texture", "device", "0x00422800", "wiz8hy",
             "loaded", "hook", "ok", "Wiz8.exe+", "memory", "private", "MB", "level", "Monastery1"]
    out = []
    for i in range(lines):
        out.append("%02d:%02d:%02d.%03d [%5d] %s\r\n" % (
            i // 3600 % 24, i // 60 % 60, i % 60, rng.randrange(1000), rng.randrange(20000),
            " ".join(rng.choice(words) for _ in range(rng.randrange(2, 9)))))
    return "".join(out).encode()


def dump_like(rng, size):
    # mostly zeros with islands of data, like a crash dump
    data = bytearray(size)
    for _ in range(size // 4096):
        at = rng.randrange(size)
        chunk = rng.randbytes(rng.randrange(1, 600))
        data[at:at + len(chunk)] = chunk[:max(0, size - at)]
    return bytes(data)


def far_repeat(rng, distance):
    # the same 300 bytes again exactly `distance` bytes later (the window is 32768); bytes
    # under 144 only: those cost 8 bits each, so the file gets smaller only if the repeat is found
    block = bytes(rng.randrange(144) for _ in range(300))
    return block + bytes(rng.randrange(144) for _ in range(distance - 300)) + block + b"tail"


def cases(rng):
    yield "empty.txt", b""
    yield "one.bin", b"\x00"
    yield "two.bin", b"ab"
    yield "three.bin", b"abc"
    yield "same257.bin", b"a" * 257
    yield "same258.bin", b"a" * 258
    yield "same259.bin", b"a" * 259
    yield "same261.bin", b"a" * 261
    yield "same100k.bin", b"\xff" * 100000
    yield "allbytes.bin", bytes(range(256)) * 3
    yield "high.bin", bytes(range(144, 256)) * 50
    yield "random1k.bin", rng.randbytes(1000)
    yield "random300k.bin", rng.randbytes(300000)
    yield "zeros5m.bin", bytes(5 * 1024 * 1024)
    yield "wiz8ws.log", log_text(rng, 4000)
    yield "Wiz8Logs/2026-11-12_13-14-15/wiz8hy.log", log_text(rng, 300)
    yield "Wiz8Logs/crash-2026-11-12_13-14-15.dmp", dump_like(rng, 3 * 1024 * 1024)
    yield "far32767.bin", far_repeat(rng, 32767)
    yield "far32768.bin", far_repeat(rng, 32768)
    yield "far32769.bin", far_repeat(rng, 32769)
    yield "far70000.bin", far_repeat(rng, 70000)
    yield "Dll/srDD_D3D11.log", log_text(rng, 80)
    yield "журнал.txt", "привет\r\n".encode() * 40


def fuzz_case(rng):
    kind = rng.randrange(6)
    size = rng.choice([0, 1, 2, 3, 4, 5, 17, 255, 256, 257, 258, 259, 1000, 4096, 40000, 70000])
    size = max(0, size + rng.randrange(-2, 3))
    if kind == 0:
        return rng.randbytes(size)
    if kind == 1:
        return bytes(rng.choice(b"ab") for _ in range(size))
    if kind == 2:
        unit = rng.randbytes(rng.randrange(1, 40))
        return (unit * (size // len(unit) + 1))[:size]
    if kind == 3:
        return log_text(rng, size // 60 + 1)[:size]
    if kind == 4:
        return dump_like(rng, size) if size else b""
    parts = []
    total = 0
    while total < size:
        piece = rng.choice([rng.randbytes(rng.randrange(1, 300)), bytes(rng.randrange(1, 700)),
                            b"x" * rng.randrange(1, 600)])
        if parts and rng.random() < 0.4:
            piece = rng.choice(parts)
        parts.append(piece)
        total += len(piece)
    return b"".join(parts)[:size]


def pack(exe, work, files, name):
    code, path, err, _ = pack_limited(exe, work, files, name, None)
    return code, path, err


def pack_limited(exe, work, files, name, limit):
    """Packs with the archive limit given to every Add (None: without one, a refused file is an
    error). Also returns the names the test program reports as refused."""
    lines = []
    written = {}
    for entry, data in files:
        # one input file per distinct content: the 65535 entries of the count test share one
        if data not in written:
            written[data] = os.path.join(work, "in%d.bin" % len(written))
            with open(written[data], "wb") as f:
                f.write(data)
        lines.append(entry + "\t" + written[data] + "\n")
    listing = os.path.join(work, "list.txt")
    with open(listing, "w", encoding="utf-8", newline="") as f:
        f.writelines(lines)
    command = list(exe) + [os.path.join(work, name), listing] + ([str(limit)] if limit is not None else [])
    done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    refused = [line[len("refused: "):] for line in done.stdout.splitlines() if line.startswith("refused: ")]
    return done.returncode, os.path.join(work, name), done.stderr.strip(), refused


def verify(path, files):
    """'' when the archive holds exactly the files, otherwise what is wrong"""
    try:
        with zipfile.ZipFile(path) as z:
            bad = z.testzip()
            if bad:
                return "bad CRC in " + bad
            if z.namelist() != [n for n, _ in files]:
                return "names differ: %r" % z.namelist()[:5]
            for (name, data), info in zip(files, z.infolist()):
                if z.read(info) != data:
                    return "content differs: " + name
                if info.file_size != len(data):
                    return "size differs: " + name
                if info.date_time != (2026, 11, 12, 13, 14, 16):
                    return "time differs: %r" % (info.date_time,)
                if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                    return "method %d" % info.compress_type
                if info.compress_size > max(info.file_size, 0):
                    return "packed larger than the file: " + name
    except Exception as e:  # noqa: BLE001 - any failure to read is the finding
        return "cannot read: %r" % e
    return ""


def limits(exe, work, rng):
    """What Writer::Add refuses: a file that takes the archive over `limit`, an empty name, and
    the 65535th file."""
    log = ("limit.log", log_text(rng, 200))
    code, path, err = pack(exe, work, [log], "limit.zip")
    size = os.path.getsize(path) if code == 0 else 0
    check("limit: an archive of one file to measure (%d bytes)" % size, code == 0, err)
    if code:
        return
    for limit, fits in ((size, True), (size - 1, False)):
        want = [log] if fits else []
        code, path, err, refused = pack_limited(exe, work, [log], "limit.zip", limit)
        problem = verify(path, want) if code == 0 else "not packed: " + err
        if not problem and refused != ([] if fits else [log[0]]):
            problem = "refused: %r" % refused
        if not problem and os.path.getsize(path) > limit:
            problem = "the archive has %d bytes" % os.path.getsize(path)
        check("limit: %d bytes for an archive of %d: the file %s"
              % (limit, size, "goes in" if fits else "is refused"), problem == "", problem)
    # a file that does not fit is refused, the smaller one after it still goes in
    first = ("Wiz8Logs/a.log", log_text(rng, 300))
    large = ("Wiz8Logs/b.dmp", rng.randbytes(5000))
    small = ("Wiz8Logs/c.log", b"short\r\n")
    code, path, err = pack(exe, work, [first, small], "limit.zip")
    limit = os.path.getsize(path) + 100 if code == 0 else 0
    code, path, err, refused = pack_limited(exe, work, [first, large, small], "limit.zip", limit)
    problem = verify(path, [first, small]) if code == 0 else "not packed: " + err
    if not problem and refused != [large[0]]:
        problem = "refused: %r" % refused
    if not problem and os.path.getsize(path) > limit:
        problem = "the archive has %d bytes, over the limit of %d" % (os.path.getsize(path), limit)
    check("limit: of three files the one that does not fit is refused, the next goes in",
          problem == "", problem)
    code, path, err = pack(exe, work, [("", b"no name")], "noname.zip")
    check("a file without a name is refused", code == 1 and "cannot add" in err, "exit %d %s" % (code, err))
    # no ZIP64: 65534 files at most; with a limit that nothing reaches the refusal is reported
    many = [("n/%d" % i, b"") for i in range(65535)]
    code, path, err, refused = pack_limited(exe, work, many, "many.zip", 1 << 30)
    problem = verify(path, many[:65534]) if code == 0 else "not packed: " + err
    if not problem and refused != [many[65534][0]]:
        problem = "refused: %r" % refused[:3]
    check("the 65535th file is refused, the 65534 before it are read back", problem == "", problem)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=300)
    parser.add_argument("--exe", nargs="+")
    parser.add_argument("--seed", type=int, default=8)
    options = parser.parse_args()
    work = tempfile.mkdtemp(prefix="zipw_")
    try:
        exe = options.exe
        if not exe:
            built = os.path.join(work, "zip_writer_test")
            done = subprocess.run(["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                                   os.path.join(HERE, "zip_writer_test.cpp"), "-o", built],
                                  capture_output=True, text=True)
            check("build (g++ -Wall -Wextra -Werror)", done.returncode == 0, done.stderr[-600:])
            if done.returncode:
                return
            exe = [built]
        rng = random.Random(options.seed)
        files = list(cases(rng))
        code, path, err = pack(exe, work, files, "all.zip")
        check("all cases in one archive: packed", code == 0, err)
        problem = verify(path, files) if code == 0 else "not packed"
        check("all cases in one archive: read back by Python", problem == "", problem)
        if code == 0 and shutil.which("unzip"):
            done = subprocess.run(["unzip", "-tq", path], capture_output=True, text=True)
            check("all cases in one archive: unzip -t", done.returncode == 0, done.stdout[-300:])
        if code == 0:
            with zipfile.ZipFile(path) as z:
                sizes = {i.filename: (i.file_size, i.compress_size, i.compress_type) for i in z.infolist()}
            log = sizes["wiz8ws.log"]
            check("a log shrinks to under a third (%d -> %d)" % log[:2], log[1] * 3 < log[0])
            zeros = sizes["zeros5m.bin"]
            check("zeros shrink to under 1/100 (%d -> %d)" % zeros[:2], zeros[1] * 100 < zeros[0])
            dump = sizes["Wiz8Logs/crash-2026-11-12_13-14-15.dmp"]
            check("a dump-like file shrinks to under a third (%d -> %d)" % dump[:2], dump[1] * 3 < dump[0])
            rnd = sizes["random300k.bin"]
            check("random bytes are stored as they are", rnd[2] == zipfile.ZIP_STORED and rnd[0] == rnd[1])
            far = sizes["far32768.bin"], sizes["far32769.bin"]
            check("a repeat 32768 bytes back is found, 32769 is not (%d, %d)" % (far[0][1], far[1][1]),
                  far[1][1] - far[0][1] > 250)
        for name, data in files[:9]:
            code, path, err = pack(exe, work, [(name, data)], "single.zip")
            problem = verify(path, [(name, data)]) if code == 0 else "not packed: " + err
            check("alone in an archive: %s (%d bytes)" % (name, len(data)), problem == "", problem)
        code, path, err = pack(exe, work, [], "none.zip")
        problem = verify(path, []) if code == 0 else "not packed: " + err
        check("an archive with no files", problem == "", problem)
        bad = 0
        first = ""
        for round_number in range(options.rounds):
            batch = [("f%d/%d.bin" % (round_number, k), fuzz_case(rng)) for k in range(rng.randrange(1, 6))]
            code, path, err = pack(exe, work, batch, "fuzz.zip")
            problem = verify(path, batch) if code == 0 else "not packed: " + err
            if problem:
                bad += 1
                if not first:
                    first = "round %d: %s" % (round_number, problem)
                    shutil.copy(path, os.path.join(tempfile.gettempdir(), "zipw_failed.zip"))
        check("%d random archives read back by Python" % options.rounds, bad == 0, first)
        limits(exe, work, rng)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        print("RESULT: %d passed, %d failed" % (passed, failed))
        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
