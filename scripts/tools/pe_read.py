"""Read bytes/dwords from a PE at a virtual address. Read-only.
python pe_read.py <file.exe> <va> <count_dwords>"""
import struct
import sys

path, va, count = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
data = open(path, 'rb').read()
pe = struct.unpack_from('<I', data, 0x3c)[0]
nsec = struct.unpack_from('<H', data, pe + 6)[0]
opt = struct.unpack_from('<H', data, pe + 20)[0]
base = struct.unpack_from('<I', data, pe + 24 + 28)[0]
sec = pe + 24 + opt
for i in range(nsec):
    name, vsize, vaddr, rsize, raddr = struct.unpack_from('<8sIIII', data, sec + i * 40)
    if vaddr <= va - base < vaddr + max(vsize, rsize):
        off = raddr + (va - base - vaddr)
        for k in range(count):
            print('%08x: %08x' % (va + 4 * k, struct.unpack_from('<I', data, off + 4 * k)[0]))
        break
