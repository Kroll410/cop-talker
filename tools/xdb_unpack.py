"""Unpack files from S.T.A.L.K.E.R. Call of Pripyat .db archives.

Format reference: OpenXRay src/xrCore/LocatorAPI.cpp, LzHuf.cpp, rt_compressor.cpp.
  chunk stream: u32 id (bit 31 = LZHUF-compressed), u32 size, data
  chunk 666 = ini header, chunk 1 = file table
  file table entry: u16 size, u32 size_real, u32 size_compr, u32 crc, name, u32 offset
  file data: stored if size_real == size_compr, otherwise LZO1X.

Usage: python xdb_unpack.py <archive.db> <out_dir> [path_prefix ...]
"""
import os
import struct
import sys

COMPRESS_MARK = 1 << 31

# ---------------------------------------------------------------- LZHUF
N, F, THRESHOLD = 4096, 60, 2
N_CHAR = 256 - THRESHOLD + F
T = N_CHAR * 2 - 1
R = T - 1
MAX_FREQ = 0x4000

D_CODE = bytes(
    [0x00] * 32 + [0x01] * 16 + [0x02] * 16 + [0x03] * 16
    + sum(([i] * 8 for i in range(0x04, 0x0C)), [])
    + sum(([i] * 4 for i in range(0x0C, 0x18)), [])
    + sum(([i] * 2 for i in range(0x18, 0x30)), [])
    + list(range(0x30, 0x40))
)
D_LEN = bytes([3] * 32 + [4] * 48 + [5] * 64 + [6] * 48 + [7] * 48 + [8] * 16)
assert len(D_CODE) == 256 and len(D_LEN) == 256


def lzhuf_decode(src: bytes) -> bytes:
    textsize = struct.unpack_from("<I", src, 0)[0]
    pos = 4
    getbuf = 0
    getlen = 0

    def fill():
        nonlocal getbuf, getlen, pos
        while getlen <= 8:
            b = src[pos] if pos < len(src) else 0
            pos += 1
            getbuf |= b << (8 - getlen)
            getlen += 8

    def getbit():
        nonlocal getbuf, getlen
        fill()
        i = getbuf
        getbuf = (getbuf << 1) & 0xFFFF
        getlen -= 1
        return (i & 0x8000) >> 15

    def getbyte():
        nonlocal getbuf, getlen
        fill()
        i = getbuf
        getbuf = (getbuf << 8) & 0xFFFF
        getlen -= 8
        return (i & 0xFF00) >> 8

    freq = [0] * (T + 1)
    prnt = [0] * (T + N_CHAR + 1)
    son = [0] * T
    for i in range(N_CHAR):
        freq[i] = 1
        son[i] = i + T
        prnt[i + T] = i
    i, j = 0, N_CHAR
    while j <= R:
        freq[j] = freq[i] + freq[i + 1]
        son[j] = i
        prnt[i] = prnt[i + 1] = j
        i += 2
        j += 1
    freq[T] = 0xFFFF
    prnt[R] = 0

    def reconst():
        j = 0
        for i in range(T):
            if son[i] >= T:
                freq[j] = (freq[i] + 1) // 2
                son[j] = son[i]
                j += 1
        i, j = 0, N_CHAR
        while j < T:
            k = i + 1
            f = freq[j] = freq[i] + freq[k]
            k = j - 1
            while f < freq[k]:
                k -= 1
            k += 1
            freq[k + 1:j + 1] = freq[k:j]
            freq[k] = f
            son[k + 1:j + 1] = son[k:j]
            son[k] = i
            i += 2
            j += 1
        for i in range(T):
            k = son[i]
            if k >= T:
                prnt[k] = i
            else:
                prnt[k] = prnt[k + 1] = i

    def update(c):
        if freq[R] == MAX_FREQ:
            reconst()
        c = prnt[c + T]
        while True:
            freq[c] += 1
            k = freq[c]
            l = c + 1
            if k > freq[l]:
                l += 1
                while k > freq[l]:
                    l += 1
                l -= 1
                freq[c] = freq[l]
                freq[l] = k
                i = son[c]
                prnt[i] = l
                if i < T:
                    prnt[i + 1] = l
                j = son[l]
                son[l] = i
                prnt[j] = c
                if j < T:
                    prnt[j + 1] = c
                son[c] = j
                c = l
            c = prnt[c]
            if c == 0:
                break

    text_buf = bytearray(b"\x20" * (N - F) + b"\x00" * (F + F))
    out = bytearray()
    r = N - F
    while len(out) < textsize:
        c = son[R]
        while c < T:
            c = son[c + getbit()]
        c -= T
        update(c)
        if c < 256:
            out.append(c)
            text_buf[r] = c
            r = (r + 1) & (N - 1)
        else:
            i = getbyte()
            cc = D_CODE[i] << 6
            jj = D_LEN[i] - 2
            while jj:
                i = (i << 1) + getbit()
                jj -= 1
            p = cc | (i & 0x3F)
            i = (r - p - 1) & (N - 1)
            for k in range(c - 255 + THRESHOLD):
                b = text_buf[(i + k) & (N - 1)]
                out.append(b)
                text_buf[r] = b
                r = (r + 1) & (N - 1)
    return bytes(out[:textsize])


# ---------------------------------------------------------------- LZO1X
def lzo1x_decompress(src: bytes, out_len: int) -> bytes:
    out = bytearray()
    ip = 0

    def copy_match(m_pos, n):
        for _ in range(n):
            out.append(out[m_pos])
            m_pos += 1

    def run_length(t, base):
        nonlocal ip
        if t == 0:
            while src[ip] == 0:
                t += 255
                ip += 1
            t += base + src[ip]
            ip += 1
        return t

    state = "loop"
    t = 0
    if src[0] > 17:
        t = src[0] - 17
        ip = 1
        if t < 4:
            state = "match_next"
        else:
            out += src[ip:ip + t]
            ip += t
            state = "first_literal_run"

    while True:
        if state == "loop":
            t = src[ip]
            ip += 1
            if t >= 16:
                state = "match"
                continue
            t = run_length(t, 15)
            out += src[ip:ip + t + 3]
            ip += t + 3
            state = "first_literal_run"
            continue

        if state == "first_literal_run":
            t = src[ip]
            ip += 1
            if t >= 16:
                state = "match"
                continue
            m_pos = len(out) - (1 + 0x0800) - (t >> 2) - (src[ip] << 2)
            ip += 1
            copy_match(m_pos, 3)
            state = "match_done"
            continue

        if state == "match":
            if t >= 64:
                m_pos = len(out) - 1 - ((t >> 2) & 7) - (src[ip] << 3)
                ip += 1
                copy_match(m_pos, (t >> 5) - 1 + 2)
            elif t >= 32:
                t = run_length(t & 31, 31)
                m_pos = len(out) - 1 - (struct.unpack_from("<H", src, ip)[0] >> 2)
                ip += 2
                copy_match(m_pos, t + 2)
            elif t >= 16:
                m_pos = len(out) - ((t & 8) << 11)
                t = run_length(t & 7, 7)
                m_pos -= struct.unpack_from("<H", src, ip)[0] >> 2
                ip += 2
                if m_pos == len(out):
                    break  # end of stream
                m_pos -= 0x4000
                copy_match(m_pos, t + 2)
            else:
                m_pos = len(out) - 1 - (t >> 2) - (src[ip] << 2)
                ip += 1
                copy_match(m_pos, 2)
            state = "match_done"
            continue

        if state == "match_done":
            t = src[ip - 2] & 3
            if t == 0:
                state = "loop"
                continue
            state = "match_next"
            continue

        if state == "match_next":
            out += src[ip:ip + t]
            ip += t
            t = src[ip]
            ip += 1
            state = "match"
            continue

    if len(out) != out_len:
        raise ValueError(f"LZO size mismatch: got {len(out)}, expected {out_len}")
    return bytes(out)


# ---------------------------------------------------------------- archive
def read_chunks(data: bytes):
    pos = 0
    chunks = {}
    while pos + 8 <= len(data):
        cid, size = struct.unpack_from("<II", data, pos)
        pos += 8
        body = data[pos:pos + size]
        pos += size
        if cid & COMPRESS_MARK:
            body = lzhuf_decode(body)
        chunks[cid & ~COMPRESS_MARK] = body
    return chunks


def list_files(table: bytes):
    pos = 0
    while pos < len(table):
        (size,) = struct.unpack_from("<H", table, pos)
        pos += 2
        size_real, size_compr, crc = struct.unpack_from("<III", table, pos)
        name_len = size - 16
        name = table[pos + 12:pos + 12 + name_len].decode("cp1251")
        (offset,) = struct.unpack_from("<I", table, pos + 12 + name_len)
        pos += size
        yield name, size_real, size_compr, offset


def main():
    archive, out_dir, *prefixes = sys.argv[1:]
    prefixes = [p.lower().replace("/", "\\") for p in prefixes]
    with open(archive, "rb") as fh:
        data = fh.read()
    chunks = read_chunks(data)
    if 666 in chunks:
        print(chunks[666].decode("cp1251", "replace").strip())
    count = 0
    for name, size_real, size_compr, offset in list_files(chunks[1]):
        if prefixes and not any(name.lower().startswith(p) for p in prefixes):
            continue
        if size_real == 0 and size_compr == 0:
            continue  # folder entry
        raw = data[offset:offset + size_compr]
        body = raw if size_real == size_compr else lzo1x_decompress(raw, size_real)
        dest = os.path.join(out_dir, name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(body)
        count += 1
    print(f"extracted {count} files")


if __name__ == "__main__":
    main()
