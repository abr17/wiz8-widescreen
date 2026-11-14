// zip_writer.h - a small ZIP archive writer for the installer's report file (setup.cpp).
//
// The installer has no dependencies and also runs under Wine, where neither PowerShell nor
// tar.exe can be counted on, so the archive is written here: plain C++, nothing from Windows
// (tests\zip_writer_test.cpp builds it on any system and tests\zip_writer_test.py checks the
// result with Python's zipfile).
//
// What it writes: an ordinary ZIP (version 2.0) that Explorer, GitHub, 7-Zip, unzip and
// Python open. Every file is one deflate stream with the fixed Huffman codes (RFC 1951, block
// type 1) and an LZ77 search over the last 32 KB; a file that does not get smaller is stored
// as it is. Text logs shrink to about a sixth, crash dumps (mostly zeros) to far less. Names
// are UTF-8 with forward slashes. No ZIP64: Add() returns false for a 65535th file, for a file
// over 2 GB and once the archive is over 2 GB; Finish() returns an empty string for an archive
// that still came to 4 GB (two files of nearly 2 GB each).

#ifndef WIZ8WIDE_ZIP_WRITER_H
#define WIZ8WIDE_ZIP_WRITER_H

#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace zipw {

inline uint32_t Crc32(const unsigned char* data, size_t size)
{
    static uint32_t table[256];
    static bool ready = false;
    if (!ready) {
        for (uint32_t i = 0; i < 256; ++i) {
            uint32_t c = i;
            for (int k = 0; k < 8; ++k) {
                c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            }
            table[i] = c;
        }
        ready = true;
    }
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < size; ++i) {
        crc = table[(crc ^ data[i]) & 0xFF] ^ (crc >> 8);
    }
    return crc ^ 0xFFFFFFFFu;
}

/* Bits go into the stream from the lowest bit of each byte up (RFC 1951, 3.1.1). */
class BitSink {
public:
    explicit BitSink(std::string* out) : out_(out), hold_(0), count_(0) {}

    /* the low `bits` bits of value, lowest first (extra bits, block header) */
    void Put(uint32_t value, int bits)
    {
        hold_ |= (uint64_t)value << count_;
        count_ += bits;
        while (count_ >= 8) {
            out_->push_back((char)(hold_ & 0xFF));
            hold_ >>= 8;
            count_ -= 8;
        }
    }

    /* a Huffman code: its highest bit goes first */
    void PutCode(uint32_t code, int bits)
    {
        uint32_t reversed = 0;
        for (int i = 0; i < bits; ++i) {
            reversed = (reversed << 1) | ((code >> i) & 1);
        }
        Put(reversed, bits);
    }

    void Flush()
    {
        if (count_ > 0) {
            out_->push_back((char)(hold_ & 0xFF));
            hold_ = 0;
            count_ = 0;
        }
    }

private:
    std::string* out_;
    uint64_t hold_;
    int count_;
};

/* A literal byte or the end-of-block symbol (256), or a length symbol (257-285), in the fixed
   Huffman code (RFC 1951, 3.2.6). */
inline void PutSymbol(BitSink* sink, int symbol)
{
    if (symbol < 144) {
        sink->PutCode(0x30 + symbol, 8);
    } else if (symbol < 256) {
        sink->PutCode(0x190 + (symbol - 144), 9);
    } else if (symbol < 280) {
        sink->PutCode(symbol - 256, 7);
    } else {
        sink->PutCode(0xC0 + (symbol - 280), 8);
    }
}

/* A copy of `length` (3-258) bytes from `distance` (1-32768) bytes back. */
inline void PutMatch(BitSink* sink, int length, int distance)
{
    static const int kLengthBase[29] = {3,  4,  5,  6,  7,  8,  9,  10, 11,  13,  15,  17,  19,  23, 27,
                                        31, 35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258};
    static const int kLengthBits[29] = {0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2,
                                        2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0};
    static const int kDistBase[30] = {1,   2,   3,   4,   5,   7,    9,    13,   17,   25,
                                      33,  49,  65,  97,  129, 193,  257,  385,  513,  769,
                                      1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577};
    static const int kDistBits[30] = {0, 0, 0, 0, 1, 1, 2, 2,  3,  3,  4,  4,  5,  5,  6,
                                      6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13};
    int l = 28;
    while (kLengthBase[l] > length) {
        --l;
    }
    PutSymbol(sink, 257 + l);
    sink->Put((uint32_t)(length - kLengthBase[l]), kLengthBits[l]);
    int d = 29;
    while (kDistBase[d] > distance) {
        --d;
    }
    sink->PutCode((uint32_t)d, 5);
    sink->Put((uint32_t)(distance - kDistBase[d]), kDistBits[d]);
}

/* data as one raw deflate stream (no zlib or gzip wrapper), appended to *out */
inline void Deflate(const unsigned char* data, size_t size, std::string* out)
{
    const int kWindow = 32768;
    const int kMinMatch = 3;
    const int kMaxMatch = 258;
    const int kHashBits = 15;
    const int kMaxChain = 48; /* earlier places tried for one position */
    BitSink sink(out);
    sink.Put(1, 1); /* the last block */
    sink.Put(1, 2); /* fixed Huffman codes */
    /* head: the latest position with a given hash of three bytes; prev: for a position, the
       one before it with the same hash. Positions are stored +1, 0 = none. */
    std::vector<uint32_t> head((size_t)1 << kHashBits, 0);
    std::vector<uint32_t> prev(kWindow, 0);
    auto hash = [&](size_t i) {
        uint32_t v = (uint32_t)data[i] | ((uint32_t)data[i + 1] << 8) | ((uint32_t)data[i + 2] << 16);
        return (v * 2654435761u) >> (32 - kHashBits);
    };
    auto insert = [&](size_t i) {
        if (i + kMinMatch <= size) {
            uint32_t h = hash(i);
            prev[i % kWindow] = head[h];
            head[h] = (uint32_t)(i + 1);
        }
    };
    size_t i = 0;
    while (i < size) {
        int best = 0;
        int best_distance = 0;
        if (i + kMinMatch <= size) {
            size_t limit = size - i < (size_t)kMaxMatch ? size - i : (size_t)kMaxMatch;
            uint32_t at = head[hash(i)];
            for (int chain = 0; at != 0 && chain < kMaxChain; ++chain) {
                size_t pos = at - 1;
                if (i - pos > (size_t)kWindow) {
                    break;
                }
                if (data[pos + best] == data[i + best]) {
                    size_t n = 0;
                    while (n < limit && data[pos + n] == data[i + n]) {
                        ++n;
                    }
                    if ((int)n > best) {
                        best = (int)n;
                        best_distance = (int)(i - pos);
                        if (n == limit) {
                            break;
                        }
                    }
                }
                /* still the link written for pos: its slot is next written for pos + kWindow,
                   which is not before i */
                at = prev[pos % kWindow];
            }
        }
        if (best >= kMinMatch) {
            PutMatch(&sink, best, best_distance);
            for (int k = 0; k < best; ++k) {
                insert(i + k);
            }
            i += best;
        } else {
            PutSymbol(&sink, data[i]);
            insert(i);
            ++i;
        }
    }
    PutSymbol(&sink, 256); /* end of block */
    sink.Flush();
}

class Writer {
public:
    /* name: UTF-8, folders separated by '/'. dos_time, dos_date: the file's time in the
       MS-DOS format (seconds/2 | minutes << 5 | hours << 11; day | month << 5 | (year-1980) << 9).
       limit: when not 0, the file is added only if the archive stays within that many bytes.
       The directory entries of the files before it (46 bytes and the name each, written by
       Finish()) are not counted: a caller with a hard limit leaves room for them.
       False (nothing added): over the limit, or over the limits of a plain ZIP. */
    bool Add(const std::string& name, const std::string& bytes, uint16_t dos_time, uint16_t dos_date,
             size_t limit = 0)
    {
        if (entries_.size() >= 65534 || name.empty() || name.size() > 65535 ||
            bytes.size() > 0x7FFFFFFFu || archive_.size() > 0x7FFFFFFFu) {
            return false;
        }
        Entry entry;
        entry.name = name;
        entry.time = dos_time;
        entry.date = dos_date;
        entry.crc = Crc32((const unsigned char*)bytes.data(), bytes.size());
        entry.size = (uint32_t)bytes.size();
        entry.offset = (uint32_t)archive_.size();
        std::string packed;
        if (!bytes.empty()) {
            packed.reserve(bytes.size() / 2 + 64);
            Deflate((const unsigned char*)bytes.data(), bytes.size(), &packed);
        }
        bool stored = bytes.empty() || packed.size() >= bytes.size();
        entry.method = stored ? 0 : 8;
        entry.packed = (uint32_t)(stored ? bytes.size() : packed.size());
        /* 30 and 46 bytes: the two headers of a file; 22: the end record */
        if (limit != 0 && archive_.size() + 76 + 2 * entry.name.size() + entry.packed + 22 > limit) {
            return false;
        }
        Put32(&archive_, 0x04034b50); /* local file header */
        PutCommon(&archive_, entry);
        Put16(&archive_, (uint16_t)entry.name.size());
        Put16(&archive_, 0); /* no extra field */
        archive_ += entry.name;
        archive_ += stored ? bytes : packed;
        entries_.push_back(entry);
        return true;
    }

    /* The whole archive; the writer is empty afterwards. */
    std::string Finish()
    {
        size_t start = archive_.size();
        for (const Entry& entry : entries_) {
            Put32(&archive_, 0x02014b50); /* central directory header */
            Put16(&archive_, 20);         /* made by: MS-DOS attributes, ZIP 2.0 */
            PutCommon(&archive_, entry);
            Put16(&archive_, (uint16_t)entry.name.size());
            Put16(&archive_, 0); /* extra field */
            Put16(&archive_, 0); /* comment */
            Put16(&archive_, 0); /* disk number */
            Put16(&archive_, 0); /* internal attributes */
            Put32(&archive_, 0x20); /* external attributes: an ordinary file */
            Put32(&archive_, entry.offset);
            archive_ += entry.name;
        }
        size_t size = archive_.size() - start;
        bool fits = start <= 0xFFFFFFFEu && size <= 0xFFFFFFFEu;
        Put32(&archive_, 0x06054b50); /* end of central directory */
        Put16(&archive_, 0);
        Put16(&archive_, 0);
        Put16(&archive_, (uint16_t)entries_.size());
        Put16(&archive_, (uint16_t)entries_.size());
        Put32(&archive_, (uint32_t)size);
        Put32(&archive_, (uint32_t)start);
        Put16(&archive_, 0); /* comment */
        std::string result;
        if (fits) {
            result.swap(archive_);
        }
        archive_.clear();
        entries_.clear();
        return result;
    }

private:
    struct Entry {
        std::string name;
        uint16_t time;
        uint16_t date;
        uint16_t method;
        uint32_t crc;
        uint32_t size;
        uint32_t packed;
        uint32_t offset;
    };

    static void Put16(std::string* out, uint16_t value)
    {
        out->push_back((char)(value & 0xFF));
        out->push_back((char)(value >> 8));
    }

    static void Put32(std::string* out, uint32_t value)
    {
        Put16(out, (uint16_t)(value & 0xFFFF));
        Put16(out, (uint16_t)(value >> 16));
    }

    /* the fields the local header and the central directory share */
    static void PutCommon(std::string* out, const Entry& entry)
    {
        Put16(out, 20);     /* needs ZIP 2.0 (deflate) */
        Put16(out, 0x0800); /* names are UTF-8 */
        Put16(out, entry.method);
        Put16(out, entry.time);
        Put16(out, entry.date);
        Put32(out, entry.crc);
        Put32(out, entry.packed);
        Put32(out, entry.size);
    }

    std::string archive_;
    std::vector<Entry> entries_;
};

} // namespace zipw

#endif
