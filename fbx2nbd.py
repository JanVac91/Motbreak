#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fbx2nbd.py - Convertitore FBX -> NBD per Resident Evil Outbreak (File 1 / File 2)
================================================================================

Sostituto in Python puro (nessuna DLL, nessun SDK Autodesk) del comando
"ConvertToNBD" di OBTool.exe. Il formato e le regole di conversione sono stati
ricostruiti decompilando OBTool.exe (Ghidra) e verificati su file NBD originali.

Uso rapido (Windows: "py fbx2nbd.py ...", Linux/Mac: "python3 fbx2nbd.py ..."):

    python fbx2nbd.py  modello.fbx  modello.nbd
    python fbx2nbd.py  modello.fbx  modello.nbd  --skeleton N54.NBD
    python fbx2nbd.py  --info  file.nbd                (mostra la struttura di un NBD)
    python fbx2nbd.py  --roundtrip  file.nbd           (legge e riscrive: test del formato)

Come OBTool, cerca da solo accanto al file principale:
    modello.addon.fbx   -> secondo modello (coppia AMO/AHI aggiuntiva)
    modello.sdw         -> ombra, copiata cosi' com'e' nel blocco SDW

Differenze / migliorie rispetto a OBTool (vedi anche --help):
  * Le ossa vengono cercate per nome (Node0, Node1, ...). Il GroupId (gruppo di
    animazione: 0 gambe, 1 busto, 2 faccia, 3/4 mani) viene letto dalla proprieta'
    "GroupId" dell'FBX, oppure dalle User Defined Properties di 3ds Max
    ("GroupId = 1"); se manca viene preso dallo scheletro di riferimento
    (--skeleton) o dalla tabella standard dei personaggi a 36 nodi, invece di
    finire silenziosamente a 0 (OBTool) e rompere le animazioni del busto.
  * --skeleton FILE.NBD copia lo scheletro (AHI) esatto di un NBD originale,
    cosi' il modello e' sempre compatibile con le animazioni del gioco.
  * Scheletro come nei file originali: rotazioni di riposo a zero e posizioni
    delle ossa esatte anche se in 3ds Max/Blender le ossa sono orientate
    (--keep-bone-rotations per il comportamento di OBTool).
  * Le trasformazioni dell'oggetto (anche il pivot spostato di 3ds Max, cioe' la
    "geometric translation") vengono applicate: la mesh resta dove la vedi.
  * Pesi: massimo 4 ossa per vertice, sempre normalizzati a 100, pesi
    minuscoli scartati; le strip "a peso pieno" contengono solo triangoli
    legati al 100% allo stesso osso (OBTool ci metteva anche triangoli con
    vertici su ossa diverse).
  * Mesh senza skin ma figlie di un osso NodeN: legate automaticamente a quell'osso.
  * Texture PNG / TGA / BMP (Pillow opzionale per altri formati) o TIM2 gia'
    pronte (.tm2), con riduzione a 256 colori (median cut) se servono.
  * Messaggi di errore che dicono cosa correggere.
"""

import math
import os
import struct
import sys
import zlib

__version__ = "1.0.2"

# =============================================================================
#  Utilita'
# =============================================================================

class ConvError(Exception):
    """Errore 'utente': il messaggio spiega cosa non va nel file di ingresso."""


_LOG_QUIET = False


def log(msg=""):
    if not _LOG_QUIET:
        print(msg)


def warn(msg):
    print("  ATTENZIONE: " + msg)


def align(n, a):
    return (n + a - 1) // a * a


# =============================================================================
#  SLD: compressione LZ a parole di 16 bit usata per le texture del blocco TEX
# =============================================================================
#  Flusso di parole u16 little endian. Ogni 16 elementi c'e' una parola di flag
#  (bit piu' alto per primo). Bit 0 = parola letterale. Bit 1 = riferimento:
#    mode = u16;  count = mode >> 11 (0 -> count nella parola seguente)
#    offset = mode & 0x7FF parole indietro.
#  Il flusso DEVE finire con un riferimento 0x0000 0x0000 (count 0): il gioco si
#  ferma solo li'. Senza, decomprime oltre la fine e va in crash.
#  (Offset 0 non compare mai nei file originali: non va usato.)

def sld_decompress(src):
    out = bytearray()
    n = len(src) // 2
    words = struct.unpack_from("<%dH" % n, src)
    pos = 0
    bleft = 0
    flag = 0
    while pos < n:
        if bleft == 0:
            flag = words[pos]
            pos += 1
            bleft = 16
            if pos >= n:
                break
        if flag & 0x8000:
            mode = words[pos]
            pos += 1
            count = mode >> 11
            if count == 0:
                count = words[pos] if pos < n else 0
                pos += 1
                if count == 0:          # 0x0000 0x0000 = fine del flusso
                    break
            off = mode & 0x7FF
            if off == 0:
                out += b"\x00\x00" * count
            else:
                p = len(out) - off * 2
                if p < 0:
                    raise ConvError("dati SLD corrotti (riferimento prima dell'inizio)")
                for _ in range(count):
                    out += out[p:p + 2]
                    p += 2
        else:
            out += struct.pack("<H", words[pos])
            pos += 1
        flag = (flag << 1) & 0xFFFF
        bleft -= 1
    return bytes(out)


def sld_compress(data):
    """Compressore LZ greedy compatibile con sld_decompress."""
    if len(data) & 1:
        data = data + b"\x00"
    n = len(data) // 2
    w = struct.unpack("<%dH" % n, data)
    WINDOW = 0x7FF
    MAXC = 0xFFFF
    out = []                      # parole
    flag_pos = -1
    flag = 0
    nbits = 16
    heads = {}                    # (w0, w1) -> lista di posizioni recenti
    i = 0

    def put(is_ref, words_):
        nonlocal flag_pos, flag, nbits
        if nbits == 16:
            if flag_pos >= 0:
                out[flag_pos] = flag
            flag_pos = len(out)
            out.append(0)
            flag = 0
            nbits = 0
        if is_ref:
            flag |= 0x8000 >> nbits
        nbits += 1
        out.extend(words_)

    while i < n:
        best_len = 0
        best_off = 0
        if i + 1 < n:
            key = (w[i], w[i + 1])
            cand = heads.get(key)
            if cand:
                for p in reversed(cand):
                    off = i - p
                    if off > WINDOW:
                        break
                    L = 2
                    lim = min(MAXC, n - i)
                    while L < lim and w[p + L] == w[i + L]:
                        L += 1
                    if L > best_len:
                        best_len, best_off = L, off
                        if L >= 64:
                            break
        if best_len >= 2:
            if best_len < 32:
                put(True, [(best_len << 11) | best_off])
            else:
                put(True, [best_off, best_len])
            adv = best_len
        else:
            put(False, [w[i]])
            adv = 1
        for k in range(i, min(i + adv, n - 1)):
            lst = heads.setdefault((w[k], w[k + 1]), [])
            lst.append(k)
            if len(lst) > 48:
                del lst[:16]
        i += adv
    put(True, [0, 0])                       # marcatore di fine flusso
    out[flag_pos] = flag
    return struct.pack("<%dH" % len(out), *out)


# =============================================================================
#  NBD: contenitore (TEX / AMO / AHI / SDW ...)
# =============================================================================
#  Intestazione: slot da 16 byte {u32 tag(3 caratteri); u32 offset; u32 size;
#  u32 count}. Gli slot hanno una posizione fissa: 0 TEX, 1 AMO, 2 AHI, 3 (vuoto),
#  4 SDW, 5 AMO aggiuntivo, 6 AHI aggiuntivo. I blocchi sono allineati a 64 byte.

SECTION_ALIGN = 0x40

T_MODEL = 0x00000001
T_MESHLIST = 0x00000002
T_MESH = 0x00000004
T_PRIMLISTS = 0x00000005
T_MATLIST = 0x00000009
T_TEXLIST = 0x0000000A
T_DATE = 0x00020000
T_STRIP_FW = 0x00030000       # strip "a peso pieno" (tutti i vertici su un solo osso)
T_STRIP_PW = 0x00040000       # strip "a peso parziale"
T_MATREF = 0x00050000
T_STRIPMAT = 0x00060000
T_VERTS = 0x00070000
T_NORMALS = 0x00080000
T_UVS = 0x000A0000
T_COLORS = 0x000B0000
T_WEIGHTS = 0x000C0000
T_RATTRIBS = 0x000F0000
T_JOINTREF = 0x00100000
T_HIER = 0xC0000000
T_ROOTLIST = 0x00000000
T_NODE = 0x40000001
T_NODE_MESH = 0x40000002
T_NODE_JOINT = 0x40000003

MAT_TYPES = {0x120000: "Constant", 0x130000: "Lambert", 0x140000: "Phong", 0x150000: "VertColors"}

RA_NAMES = ["Material", "Specular", "Cull", "Scissor", "Light", "Wrap", "UVScroll",
            "DisableFog", "FadeColor", "SpecialShader", "AlphaSrc", "AlphaDst",
            "AlphaOp", "DepthOp", "DepthWrite", "Filtering", "AddressMode"]


def _tag_to_str(t):
    return bytes((t >> (8 * i)) & 0xFF for i in range(3)).decode("latin1")


def _str_to_tag(s):
    b = s.encode("latin1")[:3].ljust(3, b"\x00")
    return b[0] | (b[1] << 8) | (b[2] << 16)


class Mesh(object):
    def __init__(self):
        self.strip_lists = []     # [(tipo 0x30000/0x40000, [[indici], ...]), ...]
        self.strip_flags = []     # bit alto del contatore per ogni strip (di solito 0)
        self.matrefs = []         # id globali dei materiali usati da questa mesh
        self.stripmat = []        # per ogni strip: indice locale in matrefs
        self.verts = []
        self.normals = None
        self.uvs = None
        self.colors = None        # RGBA float (0..255 nei file originali)
        self.weights = None       # per vertice: [(indice in jointrefs, peso 0..100), ...]
        self.jointrefs = None     # indice locale -> id nodo dello scheletro
        self.rattribs = None      # 18 u32 (RenderAttribs) oppure None
        self.order = None         # ordine dei sottoblocchi letto dal file
        self.extra = {}           # sottoblocchi sconosciuti {tipo: bytes}


class Material(object):
    def __init__(self):
        self.type = 0x130000
        self.ambient = (0.2, 0.2, 0.2, 1.0)
        self.diffuse = (0.8, 0.8, 0.8, 1.0)
        self.specular = (0.0, 0.0, 0.0, 1.0)
        self.power = 0.0
        self.texrefs = [0]
        self.pad = bytes(256 - 56)


class TexRef(object):
    def __init__(self, index=0, a=0x100, b=0x100, c=0):
        self.index, self.a, self.b, self.c = index, a, b, c
        self.pad = bytes(256 - 16)


class Model(object):
    def __init__(self):
        self.date = 0x02041700
        self.meshes = []
        self.materials = []
        self.texrefs = []
        self.order = None
        self.extra = {}


class Node(object):
    def __init__(self, nid=0):
        self.type = T_NODE
        self.id = nid
        self.parent = -1
        self.child = -1
        self.next = -1
        self.scale = (1.0, 1.0, 1.0, 1.0)
        self.rot = (0.0, 0.0, 0.0, 1.0)      # angoli di Eulero XYZ in radianti, w = 1
        self.trn = (0.0, 0.0, 0.0, 1.0)
        self.mesh_id = -1
        self.group_id = 0
        self.pad = bytes(256 - 72)


class Hierarchy(object):
    def __init__(self):
        self.roots = [0]
        self.nodes = []


class Texture(object):
    """Una texture del blocco TEX. 'raw' = blob SLD originale (riscritto identico
    se la texture non viene modificata), 'tim2' = immagine TIM2 decompressa."""
    def __init__(self, tim2=None, raw=None):
        self.tim2 = tim2
        self.raw = raw

    def get_tim2(self):
        if self.tim2 is None and self.raw is not None:
            self.tim2 = sld_decompress(self.raw)
        return self.tim2

    def get_raw(self):
        if self.raw is None:
            self.raw = sld_compress(self.tim2)
        return self.raw


class NBD(object):
    def __init__(self):
        self.slots = []           # [(tag, oggetto, count)]; tag None = slot vuoto


# ------------------------------------------------------------------- lettura

class _R(object):
    def __init__(self, d):
        self.d = d

    def hdr(self, p):
        return struct.unpack_from("<III", self.d, p)


def _read_floats(d, p, cnt, k):
    v = struct.unpack_from("<%df" % (cnt * k), d, p)
    return [tuple(v[i * k:(i + 1) * k]) for i in range(cnt)]


def _read_mesh(d, p, end):
    m = Mesh()
    m.order = []
    while p + 12 <= end:
        t, c, s = struct.unpack_from("<III", d, p)
        if s < 12 or p + s > end:
            raise ConvError("mesh: sottoblocco 0x%X con dimensione non valida" % t)
        pl = p + 12
        m.order.append(t)
        if t == T_PRIMLISTS:
            q = pl
            for _ in range(c):
                lt, lc, ls = struct.unpack_from("<III", d, q)
                strips, flags = [], []
                r = q + 12
                for _ in range(lc):
                    n = struct.unpack_from("<I", d, r)[0]
                    flags.append(n & 0x80000000)
                    n &= 0x7FFFFFFF
                    strips.append(list(struct.unpack_from("<%dI" % n, d, r + 4)))
                    r += 4 + 4 * n
                m.strip_lists.append((lt, strips))
                m.strip_flags.append(flags)
                q += ls
        elif t == T_MATREF:
            m.matrefs = list(struct.unpack_from("<%dI" % c, d, pl))
        elif t == T_STRIPMAT:
            m.stripmat = list(struct.unpack_from("<%dI" % c, d, pl))
        elif t == T_VERTS:
            m.verts = _read_floats(d, pl, c, 3)
        elif t == T_NORMALS:
            m.normals = _read_floats(d, pl, c, 3)
        elif t == T_UVS:
            m.uvs = _read_floats(d, pl, c, 2)
        elif t == T_COLORS:
            m.colors = _read_floats(d, pl, c, 4)
        elif t == T_WEIGHTS:
            m.weights = []
            q = pl
            for _ in range(c):
                n = struct.unpack_from("<I", d, q)[0]
                q += 4
                m.weights.append([struct.unpack_from("<If", d, q + 8 * j) for j in range(n)])
                q += 8 * n
        elif t == T_JOINTREF:
            m.jointrefs = list(struct.unpack_from("<%dI" % c, d, pl))
        elif t == T_RATTRIBS:
            m.rattribs = list(struct.unpack_from("<18I", d, pl))
        else:
            m.extra[t] = d[p:p + s]
        p += s
    return m


def read_model(d, base, size):
    t, c, s = struct.unpack_from("<III", d, base)
    if t != T_MODEL:
        raise ConvError("blocco AMO non valido (tipo 0x%X)" % t)
    mo = Model()
    mo.order = []
    p, end = base + 12, base + s
    while p + 12 <= end:
        t, c, s = struct.unpack_from("<III", d, p)
        pl = p + 12
        mo.order.append(t)
        if t == T_DATE:
            mo.date = struct.unpack_from("<I", d, pl)[0]
        elif t == T_MESHLIST:
            q = pl
            for _ in range(c):
                mt, mc, ms = struct.unpack_from("<III", d, q)
                if mt != T_MESH:
                    raise ConvError("lista mesh: blocco inatteso 0x%X" % mt)
                mo.meshes.append(_read_mesh(d, q + 12, q + ms))
                q += ms
        elif t == T_MATLIST:
            q = pl
            for _ in range(c):
                mt, mc, ms = struct.unpack_from("<III", d, q)
                ma = Material()
                ma.type = mt
                f = struct.unpack_from("<13f", d, q + 12)
                ma.ambient, ma.diffuse, ma.specular = f[0:4], f[4:8], f[8:12]
                ma.power = f[12]
                ntex = struct.unpack_from("<I", d, q + 12 + 52)[0]
                ma.pad = d[q + 12 + 56:q + 12 + 256]
                ma.texrefs = list(struct.unpack_from("<%dI" % ntex, d, q + 12 + 256))
                mo.materials.append(ma)
                q += ms
        elif t == T_TEXLIST:
            q = pl
            for _ in range(c):
                mt, mc, ms = struct.unpack_from("<III", d, q)
                tr = TexRef(*struct.unpack_from("<4I", d, q + 12))
                tr.pad = d[q + 12 + 16:q + ms]
                mo.texrefs.append(tr)
                q += ms
        else:
            mo.extra[t] = d[p:p + s]
        p += s
    return mo


def read_hierarchy(d, base, size):
    t, c, s = struct.unpack_from("<III", d, base)
    if t != T_HIER:
        raise ConvError("blocco AHI non valido (tipo 0x%X)" % t)
    h = Hierarchy()
    p, end = base + 12, base + s
    first = True
    while p + 12 <= end:
        t, c, s = struct.unpack_from("<III", d, p)
        if first:
            if t != T_ROOTLIST:
                raise ConvError("AHI: manca la lista delle radici")
            h.roots = list(struct.unpack_from("<%dI" % c, d, p + 12))
            first = False
        elif t in (T_NODE, T_NODE_MESH, T_NODE_JOINT):
            n = Node()
            n.type = t
            n.id, n.parent, n.child, n.next = struct.unpack_from("<4i", d, p + 12)
            f = struct.unpack_from("<12f", d, p + 28)
            n.scale, n.rot, n.trn = f[0:4], f[4:8], f[8:12]
            n.mesh_id, n.group_id = struct.unpack_from("<2i", d, p + 76)
            n.pad = d[p + 84:p + s]
            h.nodes.append(n)
        else:
            raise ConvError("AHI: blocco inatteso 0x%X" % t)
        p += s
    return h


def read_tex(d, base, size, count):
    out = []
    p, end = base, base + size
    while p + 4 <= end and (count == 0 or len(out) < count):
        rs = struct.unpack_from("<I", d, p)[0]
        if rs == 0 or p + 4 + rs > end:
            break
        out.append(Texture(raw=d[p + 4:p + 4 + rs]))
        p += 4 + rs
    return out


def read_nbd(path_or_bytes):
    d = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, "rb").read()
    nbd = NBD()
    entries = []
    o = 0
    first_off = None
    while o + 16 <= len(d):
        if first_off is not None and o >= first_off:
            break
        tag, off, size, cnt = struct.unpack_from("<IIII", d, o)
        entries.append((tag, off, size, cnt))
        if tag and (first_off is None or off < first_off):
            first_off = off
        o += 16
    if first_off is None:
        raise ConvError("intestazione NBD non valida")
    nbd.header_size = first_off
    seen_amo = 0
    for tag, off, size, cnt in entries:
        if tag == 0:
            nbd.slots.append((None, None, 0))
            continue
        name = _tag_to_str(tag)
        if name == "TEX":
            obj = read_tex(d, off, size, cnt)
        elif name == "AMO":
            obj = read_model(d, off, size)
            seen_amo += 1
        elif name == "AHI":
            obj = read_hierarchy(d, off, size)
        else:
            obj = d[off:off + size]
        nbd.slots.append((name, obj, cnt))
    # gli slot vuoti finali non servono (si ricalcolano in scrittura)
    while nbd.slots and nbd.slots[-1][0] is None:
        nbd.slots.pop()
    return nbd


# ------------------------------------------------------------------ scrittura

def _chunk(t, cnt, payload):
    return struct.pack("<III", t, cnt, 12 + len(payload)) + payload


def _pack_floats(rows, k):
    flat = [x for r in rows for x in r[:k]]
    return struct.pack("<%df" % len(flat), *flat)


def write_mesh(m):
    sub = {}
    lists = b""
    for li, (lt, strips) in enumerate(m.strip_lists):
        flags = m.strip_flags[li] if li < len(m.strip_flags) else [0] * len(strips)
        body = bytearray()
        for si, s in enumerate(strips):
            body += struct.pack("<I", len(s) | (flags[si] if si < len(flags) else 0))
            body += struct.pack("<%dI" % len(s), *s)
        lists += _chunk(lt, len(strips), bytes(body))
    sub[T_PRIMLISTS] = _chunk(T_PRIMLISTS, len(m.strip_lists), lists)
    sub[T_MATREF] = _chunk(T_MATREF, len(m.matrefs), struct.pack("<%dI" % len(m.matrefs), *m.matrefs))
    sub[T_STRIPMAT] = _chunk(T_STRIPMAT, len(m.stripmat), struct.pack("<%dI" % len(m.stripmat), *m.stripmat))
    sub[T_VERTS] = _chunk(T_VERTS, len(m.verts), _pack_floats(m.verts, 3))
    if m.normals is not None:
        sub[T_NORMALS] = _chunk(T_NORMALS, len(m.normals), _pack_floats(m.normals, 3))
    if m.uvs is not None:
        sub[T_UVS] = _chunk(T_UVS, len(m.uvs), _pack_floats(m.uvs, 2))
    if m.colors is not None:
        sub[T_COLORS] = _chunk(T_COLORS, len(m.colors), _pack_floats(m.colors, 4))
    if m.weights is not None:
        body = bytearray()
        for wl in m.weights:
            body += struct.pack("<I", len(wl))
            for j, wgt in wl:
                body += struct.pack("<If", j, wgt)
        sub[T_WEIGHTS] = _chunk(T_WEIGHTS, len(m.weights), bytes(body))
    if m.jointrefs is not None:
        sub[T_JOINTREF] = _chunk(T_JOINTREF, len(m.jointrefs),
                                 struct.pack("<%dI" % len(m.jointrefs), *m.jointrefs))
    if m.rattribs is not None:
        sub[T_RATTRIBS] = _chunk(T_RATTRIBS, 1, struct.pack("<18I", *m.rattribs))
    sub.update(m.extra)
    default_order = [T_PRIMLISTS, T_MATREF, T_STRIPMAT, T_VERTS, T_NORMALS, T_UVS,
                     T_COLORS, T_WEIGHTS, T_JOINTREF, T_RATTRIBS]
    order = [t for t in (m.order or []) if t in sub]
    order += [t for t in default_order + list(m.extra) if t in sub and t not in order]
    body = b"".join(sub[t] for t in order)
    return _chunk(T_MESH, len(order), body)


def write_model(mo):
    parts = {}
    parts[T_DATE] = _chunk(T_DATE, 1, struct.pack("<I", mo.date))
    parts[T_MESHLIST] = _chunk(T_MESHLIST, len(mo.meshes), b"".join(write_mesh(m) for m in mo.meshes))
    mats = bytearray()
    for ma in mo.materials:
        head = struct.pack("<13fI", *(tuple(ma.ambient) + tuple(ma.diffuse) + tuple(ma.specular) + (ma.power,)),
                           len(ma.texrefs))
        payload = head + ma.pad[:256 - 56].ljust(256 - 56, b"\x00") + \
            struct.pack("<%dI" % len(ma.texrefs), *ma.texrefs)
        mats += _chunk(ma.type, 1, payload)
    parts[T_MATLIST] = _chunk(T_MATLIST, len(mo.materials), bytes(mats))
    texs = bytearray()
    for tr in mo.texrefs:
        texs += _chunk(0, 1, struct.pack("<4I", tr.index, tr.a, tr.b, tr.c) +
                       tr.pad[:240].ljust(240, b"\x00"))
    parts[T_TEXLIST] = _chunk(T_TEXLIST, len(mo.texrefs), bytes(texs))
    parts.update(mo.extra)
    default_order = [T_DATE, T_MESHLIST, T_MATLIST, T_TEXLIST]
    order = [t for t in (mo.order or []) if t in parts]
    order += [t for t in default_order + list(mo.extra) if t not in order]
    return _chunk(T_MODEL, len(order), b"".join(parts[t] for t in order))


def write_hierarchy(h):
    body = _chunk(T_ROOTLIST, len(h.roots), struct.pack("<%dI" % len(h.roots), *h.roots))
    for n in h.nodes:
        payload = struct.pack("<4i12f2i", n.id, n.parent, n.child, n.next,
                              *(tuple(n.scale) + tuple(n.rot) + tuple(n.trn) + (n.mesh_id, n.group_id)))
        payload += n.pad[:184].ljust(184, b"\x00")
        body += _chunk(n.type, 1, payload)
    return _chunk(T_HIER, 1 + len(h.nodes), body)


def write_nbd(nbd):
    blobs = []
    for name, obj, cnt in nbd.slots:
        if name is None:
            blobs.append((0, b"", 0))
        elif name == "TEX":
            body = bytearray()
            for tx in obj:
                raw = tx.get_raw()
                body += struct.pack("<I", len(raw)) + raw
            blobs.append((_str_to_tag("TEX"), bytes(body), len(obj)))
        elif name == "AMO":
            blobs.append((_str_to_tag("AMO"), write_model(obj), cnt))
        elif name == "AHI":
            blobs.append((_str_to_tag("AHI"), write_hierarchy(obj), cnt))
        else:
            blobs.append((_str_to_tag(name), bytes(obj), cnt))
    nslots = len(blobs) + 1                          # + slot vuoto finale
    # file nuovi: 8 slot (0x80 byte) come OBTool; file letti: dimensione originale
    hdr_size = getattr(nbd, "header_size", None) or max(0x80, align(nslots * 16, 0x40))
    hdr_size = max(hdr_size, align(nslots * 16, 0x10))
    header = bytearray(hdr_size)
    out = bytearray(header)
    pos = hdr_size
    for i, (tag, data, cnt) in enumerate(blobs):
        if tag == 0:
            continue
        pos = align(pos, SECTION_ALIGN)
        out += bytes(pos - len(out))
        struct.pack_into("<IIII", out, i * 16, tag, pos, len(data), cnt)
        out += data
        pos += len(data)
    out += bytes(align(len(out), SECTION_ALIGN) - len(out))
    return bytes(out)


def nbd_slot(nbd, name, nth=0):
    k = 0
    for s in nbd.slots:
        if s[0] == name:
            if k == nth:
                return s[1]
            k += 1
    return None


# =============================================================================
#  Matrici 4x4 (convenzione a vettori colonna: p' = M * p, M[riga][colonna])
# =============================================================================

def m_ident():
    return [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def m_mul(a, b):
    return [[a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] + a[i][3] * b[3][j]
             for j in range(4)] for i in range(4)]


def m_chain(*ms):
    r = ms[0]
    for m in ms[1:]:
        r = m_mul(r, m)
    return r


def m_trans(v):
    m = m_ident()
    m[0][3], m[1][3], m[2][3] = v[0], v[1], v[2]
    return m


def m_scale(v):
    m = m_ident()
    m[0][0], m[1][1], m[2][2] = v[0], v[1], v[2]
    return m


def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return [[1.0, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1.0]]


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s, 0], [0, 1.0, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]]


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0, 0], [s, c, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


_ORDERS = {0: "XYZ", 1: "XZY", 2: "YZX", 3: "YXZ", 4: "ZXY", 5: "ZYX", 6: "XYZ"}


def m_euler(deg, order=0):
    """Rotazione FBX: per l'ordine 'XYZ' si applica prima X, poi Y, poi Z."""
    rx, ry, rz = (math.radians(x) for x in deg)
    mats = {"X": _rx(rx), "Y": _ry(ry), "Z": _rz(rz)}
    seq = _ORDERS.get(order, "XYZ")
    r = m_ident()
    for ax in seq:                       # R = R3 * R2 * R1
        r = m_mul(mats[ax], r)
    return r


def m_inv(m):
    """Inversa generale 4x4 (Gauss-Jordan)."""
    a = [list(row) + [1.0 if i == j else 0.0 for j in range(4)] for i, row in enumerate(m)]
    for c in range(4):
        piv = max(range(c, 4), key=lambda r: abs(a[r][c]))
        if abs(a[piv][c]) < 1e-12:
            return m_ident()
        a[c], a[piv] = a[piv], a[c]
        pv = a[c][c]
        a[c] = [x / pv for x in a[c]]
        for r in range(4):
            if r != c and a[r][c] != 0.0:
                f = a[r][c]
                a[r] = [x - f * y for x, y in zip(a[r], a[c])]
    return [row[4:] for row in a]


def m_apply(m, v, w=1.0):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2] + m[0][3] * w,
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2] + m[1][3] * w,
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2] + m[2][3] * w)


def m_apply3(m, v):
    return (m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2])


def m_transpose(m):
    return [[m[j][i] for j in range(4)] for i in range(4)]


def m_decompose(m):
    """-> (traslazione, euler XYZ in gradi, scala) come FbxAMatrix::GetT/GetR/GetS."""
    t = (m[0][3], m[1][3], m[2][3])
    cols = [(m[0][i], m[1][i], m[2][i]) for i in range(3)]
    s = [math.sqrt(c[0] ** 2 + c[1] ** 2 + c[2] ** 2) for c in cols]
    det = (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
           m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
           m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))
    if det < 0:
        s[0] = -s[0]
    r = [[m[i][j] / (s[j] if s[j] else 1.0) for j in range(3)] for i in range(3)]
    # R = Rz * Ry * Rx  ->  r[2][0] = -sin(y)
    sy = -r[2][0]
    sy = max(-1.0, min(1.0, sy))
    y = math.asin(sy)
    if abs(sy) < 0.9999999:
        x = math.atan2(r[2][1], r[2][2])
        z = math.atan2(r[1][0], r[0][0])
    else:
        x = math.atan2(-r[1][2], r[1][1])
        z = 0.0
    return t, (math.degrees(x), math.degrees(y), math.degrees(z)), tuple(s)


# =============================================================================
#  Lettore FBX (binario 7.x e ASCII 7.x) in Python puro
# =============================================================================

class FbxNode(object):
    __slots__ = ("name", "props", "children")

    def __init__(self, name, props=None, children=None):
        self.name = name
        self.props = props if props is not None else []
        self.children = children if children is not None else []

    def find(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def find_all(self, name):
        return [c for c in self.children if c.name == name]

    def value(self, name, default=None):
        c = self.find(name)
        if c is None or not c.props:
            return default
        return c.props[0]


_ARR = {ord("f"): ("f", 4), ord("d"): ("d", 8), ord("l"): ("q", 8), ord("i"): ("i", 4), ord("b"): ("b", 1)}


def _parse_fbx_binary(d):
    version = struct.unpack_from("<I", d, 23)[0]
    wide = version >= 7500
    hfmt, hlen = ("<QQQ", 24) if wide else ("<III", 12)

    def read_node(p):
        end, nprops, plen = struct.unpack_from(hfmt, d, p)
        nlen = d[p + hlen]
        if end == 0:
            return None, p + hlen + 1
        name = d[p + hlen + 1:p + hlen + 1 + nlen].decode("utf-8", "replace")
        q = p + hlen + 1 + nlen
        props = []
        for _ in range(nprops):
            tc = d[q]
            q += 1
            if tc == 0x59:   # Y
                props.append(struct.unpack_from("<h", d, q)[0]); q += 2
            elif tc == 0x43:  # C
                props.append(bool(d[q])); q += 1
            elif tc == 0x49:  # I
                props.append(struct.unpack_from("<i", d, q)[0]); q += 4
            elif tc == 0x46:  # F
                props.append(struct.unpack_from("<f", d, q)[0]); q += 4
            elif tc == 0x44:  # D
                props.append(struct.unpack_from("<d", d, q)[0]); q += 8
            elif tc == 0x4C:  # L
                props.append(struct.unpack_from("<q", d, q)[0]); q += 8
            elif tc in (0x53, 0x52):  # S, R
                ln = struct.unpack_from("<I", d, q)[0]; q += 4
                raw = d[q:q + ln]; q += ln
                props.append(raw.decode("utf-8", "replace") if tc == 0x53 else bytes(raw))
            elif tc in _ARR:
                fmt, sz = _ARR[tc]
                ln, enc, clen = struct.unpack_from("<III", d, q); q += 12
                raw = d[q:q + clen]; q += clen
                if enc == 1:
                    raw = zlib.decompress(raw)
                vals = struct.unpack("<%d%s" % (ln, fmt), raw[:ln * sz])
                props.append(list(vals) if tc != 0x62 else [bool(v) for v in vals])
            else:
                raise ConvError("FBX binario: tipo di proprieta' sconosciuto %r" % chr(tc))
        children = []
        while q < end:
            ch, q2 = read_node(q)
            if ch is None:
                q = q2
                break
            children.append(ch)
            q = q2
        return FbxNode(name, props, children), end

    p = 27
    top = []
    while p < len(d):
        n, p2 = read_node(p)
        if n is None:
            break
        top.append(n)
        p = p2
    return FbxNode("", [], top), version


def _parse_fbx_ascii(text):
    toks = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
        elif ch == ";":
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif ch == '"':
            j = text.find('"', i + 1)
            if j < 0:
                raise ConvError("FBX ASCII: stringa non chiusa")
            toks.append(("S", text[i + 1:j].replace("&quot;", '"')))
            i = j + 1
        elif ch in "{},":
            toks.append((ch, ch))
            i += 1
        elif ch == "*":
            j = i + 1
            while j < n and text[j].isdigit():
                j += 1
            toks.append(("*", int(text[i + 1:j] or 0)))
            i = j
        else:
            j = i
            while j < n and text[j] not in " \t\r\n{},;\"":
                j += 1
            w = text[i:j]
            i = j
            if w.endswith(":"):
                toks.append(("N", w[:-1]))
            else:
                try:
                    if any(c in w for c in ".eE") and not w.isalpha():
                        toks.append(("V", float(w)))
                    else:
                        toks.append(("V", int(w)))
                except ValueError:
                    toks.append(("S", w))

    pos = [0]

    def parse_nodes(stop_on_brace):
        out = []
        while pos[0] < len(toks):
            k, v = toks[pos[0]]
            if k == "}":
                if stop_on_brace:
                    pos[0] += 1
                    return out
                pos[0] += 1
                continue
            if k != "N":
                pos[0] += 1
                continue
            pos[0] += 1
            node = FbxNode(v)
            # valori
            arr_len = None
            while pos[0] < len(toks):
                k2, v2 = toks[pos[0]]
                if k2 in ("S", "V"):
                    node.props.append(v2)
                    pos[0] += 1
                elif k2 == "*":
                    arr_len = v2
                    pos[0] += 1
                elif k2 == ",":
                    pos[0] += 1
                else:
                    break
            if pos[0] < len(toks) and toks[pos[0]][0] == "{":
                pos[0] += 1
                node.children = parse_nodes(True)
            if arr_len is not None:
                a = node.find("a")
                node.props = [list(a.props) if a is not None else []]
                node.children = []
            out.append(node)
        return out

    return FbxNode("", [], parse_nodes(False)), None


def parse_fbx(path):
    d = open(path, "rb").read()
    if d[:20] == b"Kaydara FBX Binary  ":
        root, ver = _parse_fbx_binary(d)
    else:
        try:
            text = d.decode("utf-8")
        except UnicodeDecodeError:
            text = d.decode("latin1")
        if "FBXHeaderExtension" not in text[:4000] and "Objects" not in text:
            raise ConvError("%s non sembra un file FBX" % path)
        root, ver = _parse_fbx_ascii(text)
        v = root.find("FBXHeaderExtension")
        ver = v.value("FBXVersion", 7000) if v else 7000
    return root, ver


def _p70(node):
    """Properties70 -> {nome: (tipo, flags, [valori])}"""
    out = {}
    if node is None:
        return out
    pp = node.find("Properties70") or node.find("Properties60")
    if pp is None:
        return out
    for p in pp.children:
        if p.name not in ("P", "Property") or not p.props:
            continue
        if p.name == "P":
            name, typ = p.props[0], p.props[1] if len(p.props) > 1 else ""
            flags = p.props[3] if len(p.props) > 3 else ""
            vals = p.props[4:]
        else:  # FBX 6.x
            name, typ = p.props[0], p.props[1] if len(p.props) > 1 else ""
            flags = p.props[2] if len(p.props) > 2 else ""
            vals = p.props[3:]
        out[name] = (typ, flags, vals)
    return out


def _clean_name(s):
    if not isinstance(s, str):
        return str(s)
    if "\x00\x01" in s:
        return s.split("\x00\x01")[0]
    if "::" in s:
        return s.split("::", 1)[1]
    return s


class FbxModel(object):
    def __init__(self, oid, name, mtype, props):
        self.id = oid
        self.name = name
        self.mtype = mtype
        self.props = props
        self.parent = None
        self.children = []
        self.geometry = None
        self.materials = []
        self.attr_type = None
        self._local = None
        self._global = None

    def p(self, name, default):
        v = self.props.get(name)
        if v is None or not v[2]:
            return default
        return v[2]

    def local_matrix(self):
        if self._local is None:
            T = self.p("Lcl Translation", [0, 0, 0])
            R = self.p("Lcl Rotation", [0, 0, 0])
            S = self.p("Lcl Scaling", [1, 1, 1])
            roff = self.p("RotationOffset", [0, 0, 0])
            rpiv = self.p("RotationPivot", [0, 0, 0])
            soff = self.p("ScalingOffset", [0, 0, 0])
            spiv = self.p("ScalingPivot", [0, 0, 0])
            active = self.p("RotationActive", [0])[0]
            order = int(self.p("RotationOrder", [0])[0]) if active else 0
            pre = self.p("PreRotation", [0, 0, 0]) if active else [0, 0, 0]
            post = self.p("PostRotation", [0, 0, 0]) if active else [0, 0, 0]
            Rpre = m_euler(pre, 0)
            Rpost = m_euler(post, 0)
            self._local = m_chain(m_trans(T), m_trans(roff), m_trans(rpiv), Rpre, m_euler(R, order),
                                  m_inv(Rpost), m_trans([-x for x in rpiv]), m_trans(soff),
                                  m_trans(spiv), m_scale(S), m_trans([-x for x in spiv]))
        return self._local

    def global_matrix(self):
        if self._global is None:
            loc = self.local_matrix()
            self._global = m_mul(self.parent.global_matrix(), loc) if self.parent else loc
        return self._global

    def geometric_matrix(self):
        gt = self.p("GeometricTranslation", [0, 0, 0])
        gr = self.p("GeometricRotation", [0, 0, 0])
        gs = self.p("GeometricScaling", [1, 1, 1])
        return m_chain(m_trans(gt), m_euler(gr, 0), m_scale(gs))

    def user_int(self, name):
        """Proprieta' utente intera (FBX) oppure riga 'name = N' nelle User Defined
        Properties di 3ds Max (stringa UDP3DSMAX)."""
        lname = name.lower()
        for k, (typ, flags, vals) in self.props.items():
            if k.lower() == lname and vals:
                try:
                    return int(round(float(vals[0])))
                except (TypeError, ValueError):
                    pass
        udp = self.props.get("UDP3DSMAX")
        if udp and udp[2] and isinstance(udp[2][0], str):
            for line in udp[2][0].replace("&cr;", "\n").replace("&lf;", "\n").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip().lower() == lname:
                        try:
                            return int(round(float(v.strip())))
                        except ValueError:
                            pass
        return None


class FbxScene(object):
    def __init__(self, path):
        self.path = path
        root, self.version = parse_fbx(path)
        if self.version and int(self.version) < 7000:
            raise ConvError("%s e' un FBX vecchio (versione %s): riesportalo come FBX 2011 o piu' recente"
                            % (path, self.version))
        objs = root.find("Objects")
        if objs is None:
            raise ConvError("%s: sezione Objects mancante" % path)
        gs = _p70(root.find("GlobalSettings"))
        self.unit_scale = float(gs.get("UnitScaleFactor", ("", "", [1.0]))[2][0]) if "UnitScaleFactor" in gs else 1.0
        self.up_axis = int(gs.get("UpAxis", ("", "", [1]))[2][0]) if "UpAxis" in gs else 1
        self.objects = {}
        self.models = []
        self.geometries = []
        self.materials = []
        self.textures = []
        self.videos = {}
        self.clusters = {}
        self.skins = {}
        for o in objs.children:
            if not o.props:
                continue
            oid = o.props[0]
            name = _clean_name(o.props[1]) if len(o.props) > 1 else ""
            sub = o.props[2] if len(o.props) > 2 else ""
            if o.name == "Model":
                m = FbxModel(oid, name, sub, _p70(o))
                self.objects[oid] = m
                self.models.append(m)
            elif o.name == "Geometry" and sub == "Mesh":
                g = {"id": oid, "name": name, "node": o, "skin": None, "model": None}
                self.objects[oid] = g
                self.geometries.append(g)
            elif o.name == "Material":
                mat = {"id": oid, "name": name, "props": _p70(o),
                       "shading": str(o.value("ShadingModel", "") or ""), "textures": {}}
                self.objects[oid] = mat
                self.materials.append(mat)
            elif o.name == "Texture":
                tx = {"id": oid, "name": name, "file": o.value("FileName") or "",
                      "rel": o.value("RelativeFilename") or "", "video": None}
                p = _p70(o)
                if not tx["file"] and "Path" in p and p["Path"][2]:
                    tx["file"] = p["Path"][2][0]
                self.objects[oid] = tx
                self.textures.append(tx)
            elif o.name == "Video":
                content = o.value("Content")
                if isinstance(content, str) and content:
                    import base64
                    try:
                        content = base64.b64decode(content)
                    except Exception:
                        content = None
                v = {"id": oid, "file": o.value("Filename") or o.value("FileName") or "",
                     "rel": o.value("RelativeFilename") or "",
                     "content": content if isinstance(content, (bytes, bytearray)) and content else None}
                self.objects[oid] = v
                self.videos[oid] = v
            elif o.name == "Deformer" and sub == "Skin":
                sk = {"id": oid, "clusters": [], "geometry": None}
                self.objects[oid] = sk
                self.skins[oid] = sk
            elif o.name == "Deformer" and sub == "Cluster":
                cl = {"id": oid, "name": name,
                      "indexes": list(o.value("Indexes", []) or []),
                      "weights": list(o.value("Weights", []) or []), "link": None}
                self.objects[oid] = cl
                self.clusters[oid] = cl
            elif o.name == "NodeAttribute":
                self.objects[oid] = {"id": oid, "attr": sub or (o.value("TypeFlags") or "")}
        # connessioni
        conns = root.find("Connections")
        for c in (conns.children if conns else []):
            if c.name != "C" or len(c.props) < 3:
                continue
            src, dst = c.props[1], c.props[2]
            prop = c.props[3] if len(c.props) > 3 else ""
            s, t = self.objects.get(src), self.objects.get(dst)
            if s is None:
                continue
            if isinstance(s, FbxModel):
                if dst == 0:
                    continue
                if isinstance(t, FbxModel):
                    s.parent = t
                    t.children.append(s)
                elif isinstance(t, dict) and t.get("id") in self.clusters:
                    t["link"] = s
                continue
            if not isinstance(s, dict):
                continue
            sid = s["id"]
            if sid in self.clusters and t is not None and isinstance(t, dict) and dst in self.skins:
                t["clusters"].append(s)
            elif sid in self.skins and isinstance(t, dict) and "node" in t:
                t["skin"] = s
                s["geometry"] = t
            elif "node" in s and isinstance(t, FbxModel):
                t.geometry = s
                s["model"] = t
            elif "shading" in s and isinstance(t, FbxModel):
                t.materials.append(s)
            elif "rel" in s and "video" in s and isinstance(t, dict) and "shading" in t:
                t["textures"].setdefault(prop or "DiffuseColor", s)
            elif sid in self.videos and isinstance(t, dict) and "video" in t:
                t["video"] = s
            elif "attr" in s and isinstance(t, FbxModel):
                t.attr_type = s["attr"]

    def find_model(self, name):
        for m in self.models:
            if m.name == name:
                return m
        ln = name.lower()
        for m in self.models:
            nm = m.name.lower()
            if nm == ln or nm.endswith(":" + ln):
                return m
        return None


# ---------------------------------------------------------------- geometria

def _layer(geo_node, name):
    els = geo_node.find_all(name)
    if not els:
        return None
    els.sort(key=lambda e: e.props[0] if e.props and isinstance(e.props[0], int) else 0)
    return els[0]


def _layer_getter(el, data_name, index_name, k, npoly_vert, cp_of_pv, poly_of_pv):
    """Ritorna f(pv) -> tupla di k float per ogni 'polygon vertex'."""
    if el is None:
        return None
    data = el.value(data_name)
    if not data:
        return None
    mapping = str(el.value("MappingInformationType", "ByPolygonVertex"))
    ref = str(el.value("ReferenceInformationType", "Direct"))
    idx = el.value(index_name)
    use_idx = ref in ("IndexToDirect", "Index") and idx

    def item(i):
        if use_idx:
            i = idx[i] if 0 <= i < len(idx) else -1
        if i < 0 or (i + 1) * k > len(data):
            return None
        return tuple(data[i * k:(i + 1) * k])

    if mapping in ("ByPolygonVertex",):
        return lambda pv: item(pv)
    if mapping in ("ByControlPoint", "ByVertice", "ByVertex"):
        return lambda pv: item(cp_of_pv[pv])
    if mapping == "ByPolygon":
        return lambda pv: item(poly_of_pv[pv])
    if mapping == "AllSame":
        return lambda pv: item(0)
    return None


def read_geometry(g):
    node = g["node"]
    verts = node.value("Vertices", []) or []
    cps = [tuple(verts[i * 3:i * 3 + 3]) for i in range(len(verts) // 3)]
    pvi = node.value("PolygonVertexIndex", []) or []
    polys = []
    cp_of_pv, poly_of_pv = [], []
    cur = []
    for k, v in enumerate(pvi):
        last = v < 0
        cp = ~v if last else v
        cur.append(k)
        cp_of_pv.append(cp)
        poly_of_pv.append(len(polys))
        if last:
            polys.append(cur)
            cur = []
    if cur:
        polys.append(cur)
    npv = len(pvi)
    normal = _layer_getter(_layer(node, "LayerElementNormal"), "Normals", "NormalsIndex", 3, npv, cp_of_pv, poly_of_pv)
    uv = _layer_getter(_layer(node, "LayerElementUV"), "UV", "UVIndex", 2, npv, cp_of_pv, poly_of_pv)
    color = _layer_getter(_layer(node, "LayerElementColor"), "Colors", "ColorIndex", 4, npv, cp_of_pv, poly_of_pv)
    mat_el = _layer(node, "LayerElementMaterial")
    poly_mat = [0] * len(polys)
    if mat_el is not None:
        mats = mat_el.value("Materials", []) or []
        mapping = str(mat_el.value("MappingInformationType", "AllSame"))
        if mapping == "AllSame":
            poly_mat = [mats[0] if mats else 0] * len(polys)
        else:
            poly_mat = [mats[i] if i < len(mats) else 0 for i in range(len(polys))]
    return {"cps": cps, "polys": polys, "cp_of_pv": cp_of_pv, "normal": normal, "uv": uv,
            "color": color, "poly_mat": poly_mat}


def triangulate(poly_pv, positions):
    """Poligono (lista di polygon-vertex) -> triangoli. Ear clipping sul piano
    di massima proiezione; ventaglio come ripiego."""
    n = len(poly_pv)
    if n < 3:
        return []
    if n == 3:
        return [tuple(poly_pv)]
    if n == 4:
        # come l'SDK FBX: diagonale 0-2, salvo quad concavi (allora 1-3)
        a, b, c, d = poly_pv
        pa, pb, pc, pd = (positions[x] for x in poly_pv)

        def nrm(p, q, r):
            u = [q[i] - p[i] for i in range(3)]
            v = [r[i] - p[i] for i in range(3)]
            return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])

        n1, n2 = nrm(pa, pb, pc), nrm(pa, pc, pd)
        if sum(n1[i] * n2[i] for i in range(3)) >= 0:
            return [(a, b, c), (a, c, d)]
        return [(a, b, d), (b, c, d)]
    pts = [positions[x] for x in poly_pv]
    nx = ny = nz = 0.0
    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        nx += (p[1] - q[1]) * (p[2] + q[2])
        ny += (p[2] - q[2]) * (p[0] + q[0])
        nz += (p[0] - q[0]) * (p[1] + q[1])
    ax = max(range(3), key=lambda i: abs((nx, ny, nz)[i]))
    i0, i1 = [(1, 2), (2, 0), (0, 1)][ax]
    sign = 1.0 if (nx, ny, nz)[ax] >= 0 else -1.0
    p2 = [(p[i0], p[i1]) for p in pts]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    idx = list(range(n))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n:
        guard += 1
        found = False
        for k in range(len(idx)):
            ia, ib, ic = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = p2[ia], p2[ib], p2[ic]
            if cross(a, b, c) * sign <= 0:
                continue
            inside = False
            for j in idx:
                if j in (ia, ib, ic):
                    continue
                p = p2[j]
                if (cross(a, b, p) * sign >= 0 and cross(b, c, p) * sign >= 0 and cross(c, a, p) * sign >= 0):
                    inside = True
                    break
            if inside:
                continue
            tris.append((poly_pv[ia], poly_pv[ib], poly_pv[ic]))
            idx.pop(k)
            found = True
            break
        if not found:
            break
    if len(idx) == 3:
        tris.append(tuple(poly_pv[i] for i in idx))
    elif len(idx) > 3:
        for k in range(1, len(idx) - 1):
            tris.append((poly_pv[idx[0]], poly_pv[idx[k]], poly_pv[idx[k + 1]]))
    return tris


# =============================================================================
#  Immagini: PNG / TGA / BMP in Python puro (Pillow se installato per il resto)
# =============================================================================

def _png_decode(d):
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ConvError("PNG non valido")
    p = 8
    idat = bytearray()
    plte = trns = None
    w = h = bd = ct = il = 0
    while p < len(d):
        ln = struct.unpack_from(">I", d, p)[0]
        typ = d[p + 4:p + 8]
        body = d[p + 8:p + 8 + ln]
        p += 12 + ln
        if typ == b"IHDR":
            w, h, bd, ct, _, _, il = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"tRNS":
            trns = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    if il:
        raise ConvError("PNG interlacciato non supportato: salvalo senza interlacciamento "
                        "(o installa Pillow: pip install pillow)")
    raw = zlib.decompress(bytes(idat))
    chans = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    bpp_bits = chans * bd
    stride = (w * bpp_bits + 7) // 8
    bpp = max(1, bpp_bits // 8)
    out = bytearray(h * stride)
    prev = bytearray(stride)
    q = 0
    for y in range(h):
        ft = raw[q]
        line = bytearray(raw[q + 1:q + 1 + stride])
        q += 1 + stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out[y * stride:(y + 1) * stride] = line
        prev = line
    rgba = bytearray(w * h * 4)

    def sample(row, x, bits):
        if bits == 8:
            return row[x]
        if bits == 16:
            return row[2 * x]
        per = 8 // bits
        byte = row[x // per]
        shift = 8 - bits * (x % per + 1)
        return (byte >> shift) & ((1 << bits) - 1)

    for y in range(h):
        row = out[y * stride:(y + 1) * stride]
        for x in range(w):
            o = (y * w + x) * 4
            if ct == 3:
                i = sample(row, x, bd)
                r, g, b = plte[i * 3:i * 3 + 3]
                a = trns[i] if trns and i < len(trns) else 255
            elif ct in (0, 4):
                if bd == 16:
                    gval = row[x * chans * 2]
                    a = row[x * chans * 2 + 2] if ct == 4 else 255
                elif bd == 8:
                    gval = row[x * chans]
                    a = row[x * chans + 1] if ct == 4 else 255
                else:
                    gval = sample(row, x, bd) * 255 // ((1 << bd) - 1)
                    a = 255
                r = g = b = gval
            else:
                s = 2 if bd == 16 else 1
                base = x * chans * s
                r, g, b = row[base], row[base + s], row[base + 2 * s]
                a = row[base + 3 * s] if ct == 6 else 255
            rgba[o:o + 4] = bytes((r, g, b, a))
    return w, h, bytes(rgba)


def _tga_decode(d):
    idlen, cmtype, itype = d[0], d[1], d[2]
    cmstart, cmlen, cmbits = struct.unpack_from("<HHB", d, 3)
    w, h, bits, desc = struct.unpack_from("<HHBB", d, 12)
    p = 18 + idlen
    pal = None
    if cmtype == 1:
        pbytes = (cmbits + 7) // 8
        pal = []
        for i in range(cmlen):
            pal.append(d[p + i * pbytes:p + (i + 1) * pbytes])
        p += cmlen * pbytes
    bpp = (bits + 7) // 8
    npix = w * h
    pixels = []
    if itype in (1, 2, 3):
        for i in range(npix):
            pixels.append(d[p + i * bpp:p + (i + 1) * bpp])
    elif itype in (9, 10, 11):
        while len(pixels) < npix:
            c = d[p]
            p += 1
            if c & 0x80:
                px = d[p:p + bpp]
                p += bpp
                pixels.extend([px] * ((c & 0x7F) + 1))
            else:
                k = (c & 0x7F) + 1
                for _ in range(k):
                    pixels.append(d[p:p + bpp])
                    p += bpp
    else:
        raise ConvError("TGA: tipo %d non supportato" % itype)

    def conv(px, nb):
        if nb == 8 and itype in (3, 11):
            return (px[0], px[0], px[0], 255)
        if nb == 16 or nb == 15:
            v = px[0] | (px[1] << 8)
            return (((v >> 10) & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, (v & 31) * 255 // 31,
                    255 if (nb == 15 or v & 0x8000) else 0)
        if nb == 24:
            return (px[2], px[1], px[0], 255)
        return (px[2], px[1], px[0], px[3])

    rgba = bytearray(npix * 4)
    top = bool(desc & 0x20)
    for i, px in enumerate(pixels[:npix]):
        if pal is not None:
            px = pal[px[0] - cmstart] if 0 <= px[0] - cmstart < len(pal) else pal[0]
            c = conv(px, cmbits)
        else:
            c = conv(px, bits)
        x, y = i % w, i // w
        if not top:
            y = h - 1 - y
        o = (y * w + x) * 4
        rgba[o:o + 4] = bytes(c)
    if bits == 32 and not any(rgba[3::4]):          # alpha tutto a zero = alpha non usato
        rgba[3::4] = b"\xff" * npix
    return w, h, bytes(rgba)


def _bmp_decode(d):
    if d[:2] != b"BM":
        raise ConvError("BMP non valido")
    off = struct.unpack_from("<I", d, 10)[0]
    hsz = struct.unpack_from("<I", d, 14)[0]
    w, h, _, bits, comp = struct.unpack_from("<iiHHI", d, 18)
    if comp not in (0, 3):
        raise ConvError("BMP compresso non supportato (salvalo come PNG)")
    top = h < 0
    h = abs(h)
    pal = []
    if bits <= 8:
        ncol = struct.unpack_from("<I", d, 46)[0] or (1 << bits)
        for i in range(ncol):
            b, g, r, _ = d[14 + hsz + i * 4:14 + hsz + i * 4 + 4]
            pal.append((r, g, b, 255))
    stride = (w * bits + 31) // 32 * 4
    rgba = bytearray(w * h * 4)
    for y in range(h):
        row = d[off + y * stride:off + (y + 1) * stride]
        yy = y if top else h - 1 - y
        for x in range(w):
            if bits == 8:
                c = pal[row[x]]
            elif bits == 4:
                c = pal[(row[x // 2] >> (4 if x % 2 == 0 else 0)) & 15]
            elif bits == 24:
                c = (row[x * 3 + 2], row[x * 3 + 1], row[x * 3], 255)
            elif bits == 32:
                c = (row[x * 4 + 2], row[x * 4 + 1], row[x * 4], row[x * 4 + 3])
            else:
                raise ConvError("BMP a %d bit non supportato" % bits)
            o = (yy * w + x) * 4
            rgba[o:o + 4] = bytes(c)
    if bits == 32 and not any(rgba[3::4]):
        rgba[3::4] = b"\xff" * (w * h)
    return w, h, bytes(rgba)


def load_image_bytes(data, name=""):
    """-> (w, h, RGBA top-down)"""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return _png_decode(data)
        if data[:2] == b"BM":
            return _bmp_decode(data)
        if name.lower().endswith(".tga"):
            return _tga_decode(data)
    except ConvError:
        pass
    try:
        from PIL import Image  # opzionale
        import io
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        return im.size[0], im.size[1], im.tobytes()
    except ImportError:
        raise ConvError("formato immagine non supportato per '%s': usa PNG, TGA o BMP "
                        "(oppure installa Pillow: pip install pillow)" % name)
    except Exception as e:
        raise ConvError("impossibile leggere l'immagine '%s' (%s)" % (name, e))


def resize_nearest(w, h, rgba, nw, nh):
    out = bytearray(nw * nh * 4)
    for y in range(nh):
        sy = min(h - 1, y * h // nh)
        for x in range(nw):
            sx = min(w - 1, x * w // nw)
            o, s = (y * nw + x) * 4, (sy * w + sx) * 4
            out[o:o + 4] = rgba[s:s + 4]
    return bytes(out)


# =============================================================================
#  TIM2 (immagine PS2): 8 bit indicizzata, palette RGBA32 256 colori (CSM1)
# =============================================================================

def _median_cut(colors_counts, k=256):
    """colors_counts: {rgba: conteggio} -> (palette, {rgba: indice}). Ogni colore va
    nella palette del 'box' in cui finisce, quindi non serve cercare il piu' vicino."""
    def info(box):
        rng = []
        for ch in range(4):
            vals = [c[0][ch] for c in box]
            rng.append(max(vals) - min(vals))
        best = max(range(4), key=lambda i: rng[i])
        return [box, rng[best] if len(box) > 1 else -1, best]

    boxes = [info(list(colors_counts.items()))]
    while len(boxes) < k:
        bi = max(range(len(boxes)), key=lambda i: boxes[i][1])
        box, rng, ch = boxes[bi]
        if rng <= 0:
            break
        boxes.pop(bi)
        box.sort(key=lambda c: c[0][ch])
        tot = sum(c[1] for c in box)
        acc, cut = 0, 1
        for i, c in enumerate(box):
            acc += c[1]
            if acc >= tot / 2:
                cut = max(1, min(len(box) - 1, i + 1))
                break
        boxes.append(info(box[:cut]))
        boxes.append(info(box[cut:]))
    pal, lut = [], {}
    for box, _, _ in boxes:
        tot = sum(c[1] for c in box) or 1
        pal.append(tuple(int(round(sum(c[0][ch] * c[1] for c in box) / tot)) for ch in range(4)))
        for c, _ in box:
            lut[c] = len(pal) - 1
    return pal, lut


def make_tim2(w, h, rgba):
    px = [tuple(rgba[i:i + 4]) for i in range(0, len(rgba), 4)]
    counts = {}
    for c in px:
        counts[c] = counts.get(c, 0) + 1
    if len(counts) <= 256:
        pal = sorted(counts)
        lut = {c: i for i, c in enumerate(pal)}
    else:
        log("    %d colori -> riduzione a 256 (median cut)" % len(counts))
        pal, lut = _median_cut(counts, 256)
    pal = list(pal) + [(0, 0, 0, 0)] * (256 - len(pal))
    img = bytes(lut[c] for c in px)
    # palette in ordine CSM1: in ogni gruppo di 32 colori si scambiano 8..15 e 16..23
    sw = list(pal)
    for b in range(0, 256, 32):
        sw[b + 8:b + 16], sw[b + 16:b + 24] = pal[b + 16:b + 24], pal[b + 8:b + 16]
    clut = b"".join(bytes(c) for c in sw)
    n = w * h
    head = b"TIM2" + struct.pack("<BBH", 4, 0, 1) + bytes(8)
    pic = struct.pack("<IIIHHBBBBHH", n + 0x430, 0x400, n, 0x30, 0x100, 0, 1, 3, 5, w, h)
    pic += bytes(0x30 - len(pic))
    return head + pic + img + clut


def tim2_info(d):
    if d[:4] != b"TIM2":
        return None
    tot, clutsz, imgsz, hdrsz, clutcols, pfmt, nmip, cltt, imgt, w, h = \
        struct.unpack_from("<IIIHHBBBBHH", d, 16)
    return {"w": w, "h": h, "imgtype": imgt, "clut": clutcols}


def _is_pot(v):
    return v > 0 and (v & (v - 1)) == 0


def _next_pot(v):
    p = 1
    while p < v:
        p <<= 1
    return min(p, 1024)


def texture_from_file(path, data=None, fix_size=True):
    """File immagine (o TIM2) -> bytes TIM2 per il blocco TEX."""
    name = os.path.basename(path)
    if data is None:
        data = open(path, "rb").read()
    if data[:4] == b"TIM2":
        info = tim2_info(data)
        log("    %s: TIM2 gia' pronta %dx%d" % (name, info["w"], info["h"]))
        return data
    w, h, rgba = load_image_bytes(data, name)
    if fix_size and (not _is_pot(w) or not _is_pot(h) or w > 1024 or h > 1024):
        nw, nh = _next_pot(w), _next_pot(h)
        warn("%s e' %dx%d: la PS2 vuole lati potenza di 2 (max 1024). Ridimensiono a %dx%d."
             % (name, w, h, nw, nh))
        rgba = resize_nearest(w, h, rgba, nw, nh)
        w, h = nw, nh
    log("    %s: %dx%d" % (name, w, h))
    return make_tim2(w, h, rgba)


# =============================================================================
#  Triangle strip
# =============================================================================
#  Convenzione del gioco: nella strip [v0 v1 v2 v3 ...] il triangolo k e'
#  (vk, vk+1, vk+2) se k e' pari, (vk+1, vk, vk+2) se k e' dispari: cosi'
#  l'orientamento (e quindi il culling) di ogni triangolo resta quello originale.

def stripify(tris, max_len=0, max_bones=0, bones_of=None):
    """tris: lista di (a, b, c). Ritorna lista di strip (liste di indici)."""
    tris = [t for t in tris if t[0] != t[1] and t[1] != t[2] and t[0] != t[2]]
    edge = {}
    for ti, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            edge.setdefault(e, []).append(ti)
    used = [False] * len(tris)

    def third(ti, p, q):
        a, b, c = tris[ti]
        for x, y, z in ((a, b, c), (b, c, a), (c, a, b)):
            if x == p and y == q:
                return z
        return None

    def neighbours(ti):
        a, b, c = tris[ti]
        k = 0
        for e in ((b, a), (c, b), (a, c)):
            for tj in edge.get(e, ()):
                if not used[tj]:
                    k += 1
        return k

    def grow(seq, simulate):
        """Estende la strip seq; se simulate non marca i triangoli."""
        taken = []
        bones = set()
        if bones_of is not None:
            for v in seq:
                bones |= bones_of(v)
        while True:
            if max_len and len(seq) >= max_len:
                break
            k = len(seq) - 2               # indice del prossimo triangolo
            p, q = seq[-2], seq[-1]
            # triangolo k: pari -> (p, q, n), dispari -> (q, p, n)
            e = (p, q) if k % 2 == 0 else (q, p)
            nxt = None
            for tj in edge.get(e, ()):
                if not used[tj] and tj not in taken:
                    nxt = tj
                    break
            if nxt is None:
                break
            n = third(nxt, e[0], e[1])
            if n is None or n in (p, q):
                break
            if bones_of is not None and max_bones:
                nb = bones | bones_of(n)
                if len(nb) > max_bones:
                    break
                bones = nb
            seq.append(n)
            taken.append(nxt)
        if not simulate:
            for tj in taken:
                used[tj] = True
        return taken

    strips = []
    order = sorted(range(len(tris)), key=neighbours)
    for start in order:
        if used[start]:
            continue
        a, b, c = tris[start]
        best = None
        for rot in ((a, b, c), (b, c, a), (c, a, b)):
            used[start] = True
            seq = list(rot)
            n = len(grow(seq, True))
            used[start] = False
            if best is None or n > best[0]:
                best = (n, rot)
        used[start] = True
        seq = list(best[1])
        grow(seq, False)
        strips.append(seq)
    return strips


def strip_triangles(s):
    for k in range(len(s) - 2):
        a, b, c = s[k], s[k + 1], s[k + 2]
        if a != b and b != c and a != c:
            yield (a, b, c) if k % 2 == 0 else (b, a, c)


# =============================================================================
#  Conversione FBX -> modello NBD
# =============================================================================

# GroupId standard dello scheletro dei personaggi (36 nodi, es. N54.NBD):
# 0 = gambe/bacino, 1 = busto/braccia/testa, 2 = faccia, 3 = mano sinistra, 4 = mano destra
STD_GROUPS_36 = [0] * 10 + [1] * 12 + [2] * 6 + [3] * 4 + [4] * 4

# tipi di nodo dello stesso scheletro: Node0-2 e Node22 sono nodi semplici, gli altri joint
STD_TYPES_36 = [T_NODE] * 3 + [T_NODE_JOINT] * 19 + [T_NODE] + [T_NODE_JOINT] * 13

JOINT_TYPES = ("limbnode", "limb", "root", "skeleton")


class Options(object):
    def __init__(self):
        self.skeleton = None          # Hierarchy di riferimento (da un NBD originale)
        self.scale = 1.0
        self.max_influences = 4
        self.min_weight = 1.0         # percentuale sotto cui un peso viene scartato
        self.strip_max_len = 0
        self.strip_max_bones = 0
        self.obtool_compat = False
        self.keep_bone_rotations = False
        self.auto_scale = True
        self.fix_texture_size = True
        self.texture_size_fields = None   # None = 256x256 come OBTool
        self.placeholder = False
        self.extra_tex_dirs = []


def _f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def _model_kind(m):
    t = (m.attr_type or m.mtype or "").lower()
    if t in JOINT_TYPES:
        return T_NODE_JOINT
    if t == "mesh" or m.geometry is not None:
        return T_NODE_MESH
    return T_NODE


def collect_skeleton_models(scene):
    bones = []
    i = 0
    while True:
        m = scene.find_model("Node%d" % i)
        if m is None:
            break
        bones.append(m)
        i += 1
    # nodi NodeK oltre un "buco" nella numerazione: OBTool si fermava senza dirlo
    extra = []
    for m in scene.models:
        nm = m.name.split(":")[-1]
        if nm.lower().startswith("node") and nm[4:].isdigit() and int(nm[4:]) >= len(bones):
            extra.append(nm)
    if extra:
        warn("nella numerazione delle ossa manca Node%d: ignoro %s" % (len(bones), ", ".join(sorted(extra)[:8])))
    return bones


def build_hierarchy(scene, bones, opts):
    """Scheletro AHI. Con --skeleton si copia quello di riferimento; altrimenti si
    ricostruisce dalle ossa NodeN dell'FBX con le stesse regole di OBTool."""
    index = {id(m): i for i, m in enumerate(bones)}
    if opts.skeleton is not None:
        h = opts.skeleton
        if bones and len(bones) != len(h.nodes):
            warn("l'FBX ha %d ossa NodeN, lo scheletro di riferimento %d: uso quello di riferimento"
                 % (len(bones), len(h.nodes)))
        return Hierarchy_copy(h), index
    if not bones:
        raise ConvError("nessun osso 'Node0' trovato nell'FBX. Le ossa devono chiamarsi Node0, Node1, ... "
                        "(come le esporta OBTool) oppure usa --skeleton FILE.NBD per prendere lo scheletro "
                        "da un NBD originale.")
    h = Hierarchy()
    h.nodes = []
    missing_gid = []
    rotated = []
    for i, m in enumerate(bones):
        n = Node(i)
        n.type = _model_kind(m)
        if n.type == T_NODE_MESH:
            n.type = T_NODE
        par = m.parent
        while par is not None and id(par) not in index:
            par = par.parent
        n.parent = index[id(par)] if par is not None else -1
        kids = [index[id(c)] for c in m.children if id(c) in index]
        n.child = kids[0] if kids else -1
        # 'next' fratello: assegnato sotto
        n._kids = kids
        if opts.keep_bone_rotations:
            # esattamente come OBTool: rotazione locale, traslazione locale
            # (per i joint espressa negli assi del padre)
            loc = m.local_matrix()
            t, r, s = m_decompose(loc)
            if n.type == T_NODE_JOINT:
                pg = m.parent.global_matrix() if m.parent else m_ident()
                prs = [row[:] for row in pg]
                prs[0][3] = prs[1][3] = prs[2][3] = 0.0
                t = m_apply3(m_transpose(m_inv(prs)), t)
        else:
            # come i file originali del gioco: rotazioni a zero e traslazione =
            # posizione del nodo meno quella del padre, negli assi del mondo
            g = m.global_matrix()
            gp = (g[0][3], g[1][3], g[2][3])
            if par is not None:
                pg = par.global_matrix()
                gp = (gp[0] - pg[0][3], gp[1] - pg[1][3], gp[2] - pg[2][3])
            _, rr, _ = m_decompose(g)
            if any(abs(x) > 0.01 for x in rr):
                rotated.append(m.name)
            t, r, s = gp, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        sc = opts.scale
        z = lambda x: _f32(x) + 0.0                  # niente -0.0
        n.trn = (z(t[0] * sc), z(t[1] * sc), z(t[2] * sc), 1.0)
        n.rot = (z(math.radians(r[0])), z(math.radians(r[1])), z(math.radians(r[2])), 1.0)
        n.scale = (z(s[0]), z(s[1]), z(s[2]), 1.0)
        gid = m.user_int("GroupId")
        if gid is None:
            missing_gid.append(i)
            gid = STD_GROUPS_36[i] if len(bones) == 36 else 0
        n.group_id = gid
        h.nodes.append(n)
    for n in h.nodes:
        for a, b in zip(n._kids, n._kids[1:]):
            h.nodes[a].next = b
        del n._kids
    h.roots = [n.id for n in h.nodes if n.parent == -1] or [0]
    if len(h.nodes) == 36 and all(n.type == T_NODE_JOINT for n in h.nodes):
        # es. Blender esporta tutto come ossa: ripristino i tipi dello scheletro standard
        for n, t in zip(h.nodes, STD_TYPES_36):
            n.type = t
    if missing_gid:
        if len(bones) == 36:
            warn("GroupId mancante su %d ossa (es. Node%d): uso la tabella standard dei personaggi "
                 "(0 gambe, 1 busto, 2 faccia, 3/4 mani)" % (len(missing_gid), missing_gid[0]))
        else:
            warn("GroupId mancante su %d ossa (es. Node%d) e scheletro non standard (%d ossa): "
                 "messo a 0. Le animazioni potrebbero muovere male il modello; usa --skeleton "
                 "con un NBD originale." % (len(missing_gid), missing_gid[0], len(bones)))
    if rotated:
        log("    nota: %d ossa sono ruotate nell'FBX (es. %s): nel NBD le rotazioni di riposo vanno a "
            "zero come nei personaggi originali, le posizioni restano esatte "
            "(--keep-bone-rotations per tenerle)" % (len(rotated), rotated[0]))
    for m in bones:
        if not opts.keep_bone_rotations:
            break
        S = m.p("Lcl Scaling", [1, 1, 1])
        if any(abs(x - 1.0) > 1e-4 for x in S):
            warn("l'osso %s ha una scala diversa da 1 (%s): azzera la scala in 3ds Max (Reset XForm)"
                 % (m.name, ", ".join("%.3g" % x for x in S)))
            break
    return h, index


def Hierarchy_copy(h):
    import copy
    return copy.deepcopy(h)


class TextureBank(object):
    """Elenco globale delle texture (condiviso tra modello principale e addon)."""
    def __init__(self, opts):
        self.opts = opts
        self.keys = []
        self.items = []          # Texture

    def _resolve(self, scene, tx):
        cand = []
        base = os.path.dirname(os.path.abspath(scene.path))
        for f in (tx.get("file"), tx.get("rel")):
            if not f:
                continue
            f2 = f.replace("\\", "/")
            cand.append(f2)
            cand.append(os.path.join(base, f2))
            bn = f2.split("/")[-1]
            cand.append(os.path.join(base, bn))
            for sub in ("textures", "Textures", "maps", "tex"):
                cand.append(os.path.join(base, sub, bn))
            for d in self.opts.extra_tex_dirs:
                cand.append(os.path.join(d, bn))
        seen = []
        for c in cand:
            if c in seen:
                continue
            seen.append(c)
            if os.path.isfile(c):
                return c, None, seen
            stem = os.path.splitext(c)[0]
            for ext in (".tm2", ".TM2", ".png", ".PNG", ".tga", ".TGA", ".bmp", ".BMP"):
                if os.path.isfile(stem + ext):
                    return stem + ext, None, seen
        v = tx.get("video")
        if v and v.get("content"):
            return (v.get("file") or v.get("rel") or tx.get("file") or "embedded"), v["content"], seen
        return None, None, seen

    def index_for(self, scene, tx):
        path, data, tried = self._resolve(scene, tx)
        key = os.path.normcase(os.path.abspath(path)) if path and data is None else \
            ("embedded", tx.get("file") or tx.get("rel"))
        if key in self.keys:
            return self.keys.index(key)
        if path is None:
            msg = ("texture non trovata: '%s'. Cercata in:\n      " % (tx.get("file") or tx.get("rel"))) + \
                "\n      ".join(tried[:6])
            if not self.opts.placeholder:
                raise ConvError(msg + "\n    Copia l'immagine accanto all'FBX oppure usa --placeholder.")
            warn(msg + "\n    Uso una texture grigia segnaposto.")
            tim = make_tim2(64, 64, b"\x80\x80\x80\xff" * 4096)
        else:
            tim = texture_from_file(path, data, self.opts.fix_texture_size)
        self.keys.append(key)
        self.items.append(Texture(tim2=tim))
        return len(self.items) - 1

    def placeholder_index(self):
        key = ("placeholder",)
        if key in self.keys:
            return self.keys.index(key)
        self.keys.append(key)
        self.items.append(Texture(tim2=make_tim2(64, 64, b"\xff\xff\xff\xff" * 4096)))
        return len(self.items) - 1


def _mat_color(props, names, default):
    for n in names:
        v = props.get(n)
        if v and len(v[2]) >= 3:
            try:
                return tuple(float(x) for x in v[2][:3])
            except (TypeError, ValueError):
                pass
    return default


def _mat_scalar(props, names, default):
    for n in names:
        v = props.get(n)
        if v and v[2]:
            try:
                return float(v[2][0])
            except (TypeError, ValueError):
                pass
    return default


def build_materials(scene, texbank):
    """Tutti i materiali della scena -> (lista Material NBD, mappa id FBX -> indice)."""
    mats, mapping = [], {}
    for fm in scene.materials:
        props = fm["props"]
        ma = Material()
        ma.type = 0x130000                      # "MaterialLambert", come OBTool
        amb = _mat_color(props, ("AmbientColor", "Ambient"), (0.2, 0.2, 0.2))
        dif = _mat_color(props, ("DiffuseColor", "Diffuse"), (0.8, 0.8, 0.8))
        ma.ambient = tuple(_f32(x) for x in amb) + (1.0,)
        ma.diffuse = tuple(_f32(x) for x in dif) + (1.0,)
        if fm["shading"] == "Phong":            # confronto esatto come OBTool (Max scrive "phong")
            spe = _mat_color(props, ("SpecularColor", "Specular"), (0.0, 0.0, 0.0))
            ma.specular = tuple(_f32(x) for x in spe) + (1.0,)
            ma.power = _f32(_mat_scalar(props, ("ShininessExponent", "Shininess"), 5.0))
        else:
            ma.specular = (0.0, 0.0, 0.0, 1.0)
            ma.power = 5.0
        tx = fm["textures"].get("DiffuseColor") or fm["textures"].get("Diffuse")
        if tx is None and fm["textures"]:
            tx = list(fm["textures"].values())[0]
        if tx is None:
            warn("il materiale '%s' non ha una texture diffuse: uso una texture bianca" % fm["name"])
            ti = texbank.placeholder_index()
        else:
            ti = texbank.index_for(scene, tx)
        ma.texrefs = [ti]                      # indice nella TextureList (= indice TEX)
        mapping[fm["id"]] = len(mats)
        mats.append(ma)
    return mats, mapping


def _process_weights(raw, opts):
    """[(osso, peso 0..1)] -> tuple ordinata [(osso, percentuale)] normalizzata a 100."""
    acc = {}
    for b, w in raw:
        if w > 0:
            acc[b] = acc.get(b, 0.0) + w
    if not acc:
        return ()
    tot = sum(acc.values())
    items = sorted(((b, w / tot * 100.0) for b, w in acc.items()), key=lambda x: (-x[1], x[0]))
    kept = [it for it in items if it[1] >= opts.min_weight] or items[:1]
    kept = kept[:opts.max_influences]
    tot = sum(w for _, w in kept)
    out = [(b, round(w / tot * 100.0, 2)) for b, w in kept]
    diff = round(100.0 - sum(w for _, w in out), 2)
    if diff:
        out[0] = (out[0][0], round(out[0][1] + diff, 2))
    return tuple((b, _f32(w)) for b, w in out)


def build_mesh(scene, model, bone_index, mat_mapping, default_mat, opts, stats):
    geo = read_geometry(model.geometry)
    cps = geo["cps"]
    if not geo["polys"]:
        return None
    G = m_mul(model.global_matrix(), model.geometric_matrix())
    sc = opts.scale
    if opts.obtool_compat:
        # OBTool: v' = (inversa della globale)^T, solo 3x3, senza traslazione
        A = m_transpose(m_inv(model.global_matrix()))
        A[0][3] = A[1][3] = A[2][3] = 0.0
        P, N = A, A
    else:
        P = G
        N = m_transpose(m_inv([row[:3] + [0.0] for row in G[:3]] + [[0, 0, 0, 1.0]]))
        Gn = model.global_matrix()
        tr = (Gn[0][3], Gn[1][3], Gn[2][3])
        if model.geometry.get("skin") and any(abs(x) > 1e-3 for x in tr):
            warn("la mesh '%s' ha l'oggetto spostato di (%.2f, %.2f, %.2f): la tengo dove si vede "
                 "nella scena (OBTool ignorava lo spostamento; --obtool-compat per fare come lui)"
                 % ((model.name,) + tr))
    world = [m_apply(P, v) for v in cps]
    world = [(_f32(x * sc), _f32(y * sc), _f32(z * sc)) for x, y, z in world]

    # ---- pesi per punto di controllo
    cp_w = [[] for _ in cps]
    skin = model.geometry.get("skin")
    skinned = False
    if skin and skin["clusters"]:
        skinned = True
        lost = set()
        for cl in skin["clusters"]:
            link = cl.get("link")
            bid = bone_index.get(id(link)) if link is not None else None
            if bid is None and link is not None:
                nm = link.name.split(":")[-1]
                if nm.lower().startswith("node") and nm[4:].isdigit():
                    bid = int(nm[4:])
            if bid is None:
                lost.add(link.name if link is not None else cl["name"])
                continue
            for ci, w in zip(cl["indexes"], cl["weights"]):
                if 0 <= ci < len(cps):
                    cp_w[ci].append((bid, w))
        if lost:
            warn("mesh '%s': ossa della skin che non sono NodeN, ignorate: %s"
                 % (model.name, ", ".join(sorted(lost)[:6])))
    else:
        par = model.parent
        while par is not None and id(par) not in bone_index:
            par = par.parent
        if par is not None:
            skinned = True
            b = bone_index[id(par)]
            cp_w = [[(b, 1.0)] for _ in cps]
            log("    mesh '%s' senza skin: legata al 100%% all'osso %s" % (model.name, par.name))
        else:
            warn("la mesh '%s' non ha skin e non e' figlia di un osso: restera' ferma (non animata)"
                 % model.name)
    cp_wp = [_process_weights(w, opts) for w in cp_w] if skinned else None
    if skinned:
        unweighted = sum(1 for w in cp_wp if not w)
        if unweighted:
            # come peso prendo quello del vertice pesato piu' vicino (OBTool li lasciava senza pesi)
            weighted = [i for i, w in enumerate(cp_wp) if w]
            if weighted:
                fixed = list(cp_wp)
                for i, w in enumerate(cp_wp):
                    if not w:
                        p = cps[i]
                        j = min(weighted, key=lambda k: (cps[k][0] - p[0]) ** 2 + (cps[k][1] - p[1]) ** 2 +
                                (cps[k][2] - p[2]) ** 2)
                        fixed[i] = cp_wp[j]
                cp_wp = fixed
                warn("mesh '%s': %d vertici senza pesi nella skin -> uso i pesi del vertice piu' vicino"
                     % (model.name, unweighted))
        many = sum(1 for w in cp_w if len({b for b, _ in w}) > opts.max_influences)
        if many:
            stats["over4"] = stats.get("over4", 0) + many

    # ---- materiali locali
    local_mats = [mat_mapping[m["id"]] for m in model.materials if m["id"] in mat_mapping]
    if not local_mats:
        local_mats = [default_mat()]

    # ---- vertici unici e triangoli
    vkey = {}
    vdata = []
    tris_by_group = {}
    normal_get, uv_get, col_get = geo["normal"], geo["uv"], geo["color"]
    cp_of_pv = geo["cp_of_pv"]

    def corner(pv):
        cp = cp_of_pv[pv]
        pos = world[cp]
        if normal_get:
            nv = normal_get(pv) or (0.0, 0.0, 1.0)
            nn = m_apply3(N, nv)
            if not opts.obtool_compat:
                ln = math.sqrt(nn[0] ** 2 + nn[1] ** 2 + nn[2] ** 2) or 1.0
                nn = (nn[0] / ln, nn[1] / ln, nn[2] / ln)
            nn = tuple(_f32(x) for x in nn)
        else:
            nn = None
        if uv_get:
            u = uv_get(pv) or (0.0, 0.0)
            uv = (_f32(u[0]), _f32(1.0 - u[1]))
        else:
            uv = None
        if col_get:
            c = col_get(pv) or (0.0, 0.0, 0.0, 1.0)
            col = tuple(_f32(max(0.0, min(1.0, x)) * 255.0) for x in c[:4])
        else:
            col = (0.0, 0.0, 0.0, 255.0)
        wts = cp_wp[cp] if cp_wp is not None else ()
        key = (pos, nn, uv, col, wts)
        vi = vkey.get(key)
        if vi is None:
            vi = len(vdata)
            vkey[key] = vi
            vdata.append(key)
        return vi

    pos_by_pv = [world[cp_of_pv[pv]] for pv in range(len(cp_of_pv))]
    ntri = 0
    for pi, poly in enumerate(geo["polys"]):
        lm = geo["poly_mat"][pi] if pi < len(geo["poly_mat"]) else 0
        if not (0 <= lm < len(local_mats)):
            lm = 0
        for (a, b, c) in triangulate(poly, pos_by_pv):
            va, vb, vc = corner(a), corner(b), corner(c)
            if va == vb or vb == vc or va == vc:
                continue
            ntri += 1
            if cp_wp is None:
                gkey = (0, lm, -1)
            else:
                wa, wb, wc = vdata[va][4], vdata[vb][4], vdata[vc][4]
                if len(wa) == 1 and len(wb) == 1 and len(wc) == 1 and wa[0][0] == wb[0][0] == wc[0][0]:
                    gkey = (0, lm, wa[0][0])
                else:
                    gkey = (1, lm, -1)
            tris_by_group.setdefault(gkey, []).append((va, vb, vc))

    # ---- strip
    def bones_of(v):
        return {b for b, _ in vdata[v][4]}

    lists = {0: [], 1: []}
    smat = {0: [], 1: []}
    for gkey in sorted(tris_by_group):
        kind, lm, _ = gkey
        strips = stripify(tris_by_group[gkey], opts.strip_max_len,
                          opts.strip_max_bones if kind == 1 else 0,
                          bones_of if (kind == 1 and opts.strip_max_bones) else None)
        lists[kind].extend(strips)
        smat[kind].extend([lm] * len(strips))
    # ---- riordino dei vertici per prima apparizione nelle strip (come i file originali)
    remap = {}
    for kind in (0, 1):
        for s in lists[kind]:
            for v in s:
                if v not in remap:
                    remap[v] = len(remap)
    order = sorted(remap, key=remap.get)
    m = Mesh()
    m.strip_lists = [(T_STRIP_FW, [[remap[v] for v in s] for s in lists[0]])]
    m.strip_flags = [[0] * len(lists[0])]
    if lists[1]:
        m.strip_lists.append((T_STRIP_PW, [[remap[v] for v in s] for s in lists[1]]))
        m.strip_flags.append([0] * len(lists[1]))
    m.matrefs = local_mats
    m.stripmat = smat[0] + smat[1]
    m.verts = [vdata[v][0] for v in order]
    m.normals = [vdata[v][1] or (0.0, 0.0, 1.0) for v in order] if normal_get else None
    m.uvs = [vdata[v][2] or (0.0, 0.0) for v in order] if uv_get else [(0.0, 0.0)] * len(order)
    m.colors = [vdata[v][3] for v in order]
    if cp_wp is not None:
        used = sorted({b for v in order for b, _ in vdata[v][4]})
        jl = {b: i for i, b in enumerate(used)}
        m.jointrefs = used
        m.weights = [[(jl[b], w) for b, w in vdata[v][4]] for v in order]
    # RenderAttribs dalle proprieta' RA_* (come OBTool)
    en = model.user_int("RA_EnableRenderAttribs")
    if en:
        m.rattribs = [0x10000] + [(model.user_int("RA_" + n) or 0) & 0xFFFFFFFF for n in RA_NAMES]
    stats["tris"] = stats.get("tris", 0) + ntri
    log("    %-14s %5d vertici  %5d triangoli  %4d strip (%d peso pieno, %d parziale)  %d ossa"
        % (model.name[:14], len(m.verts), ntri, len(m.stripmat), len(lists[0]), len(lists[1]),
           len(m.jointrefs or [])))
    return m


def auto_scale(scene, bones, opts):
    """Lo scheletro standard ha il bacino (Node2) a circa 110 unita' da terra. Se l'FBX e'
    10, 100, 1000... volte piu' grande o piu' piccolo (tipico: Blender con la scala x100 su
    armatura e mesh) correggo la scala di una potenza di 10. Ritorna una copia di opts."""
    import copy
    o = copy.copy(opts)
    if not opts.auto_scale or len(bones) < 3:
        return o
    g = bones[2].global_matrix()
    h = math.sqrt(g[0][3] ** 2 + g[1][3] ** 2 + g[2][3] ** 2) * opts.scale
    if h < 1e-6:
        return o
    r = math.log10(110.0 / h)
    k = int(round(r))
    if k != 0 and abs(r - k) < 0.35:
        o.scale = opts.scale * (10.0 ** k)
        log("    scala: il bacino (Node2) e' a %.6g invece di ~110 -> moltiplico tutto per %g "
            "(--no-auto-scale per disattivare)" % (h, 10.0 ** k))
    elif abs(r) > 0.35:
        warn("il bacino (Node2) e' a %.6g da terra invece di ~110: controlla la scala (--scale)" % h)
    return o


def convert_scene(scene, texbank, opts, label="modello"):
    log("  %s: %s" % (label, os.path.basename(scene.path)))
    if abs(scene.unit_scale - 1.0) > 1e-6:
        log("    unita' del file: 1 = %g cm (UnitScaleFactor) - valori usati cosi' come sono, "
            "come OBTool; usa --scale per cambiarli" % scene.unit_scale)
    bones = collect_skeleton_models(scene)
    opts = auto_scale(scene, bones, opts)
    hier, bone_index = build_hierarchy(scene, bones, opts)
    if opts.skeleton is not None:
        # ossa dell'FBX -> id per nome
        bone_index = {}
        for m in scene.models:
            nm = m.name.split(":")[-1]
            if nm.lower().startswith("node") and nm[4:].isdigit():
                bone_index[id(m)] = int(nm[4:])
    log("    scheletro: %d nodi%s" % (len(hier.nodes), " (da --skeleton)" if opts.skeleton else ""))
    mats, mat_mapping = build_materials(scene, texbank)
    default_holder = []

    def default_mat():
        if not default_holder:
            if mats:
                warn("una mesh non ha materiali: uso il primo materiale della scena")
                default_holder.append(0)
            else:
                ma = Material()
                ma.texrefs = [texbank.placeholder_index()]
                mats.append(ma)
                default_holder.append(len(mats) - 1)
        return default_holder[0]

    # mesh: nome "MeshN" -> posizione N (come OBTool), le altre a seguire
    mesh_models = [m for m in scene.models if m.geometry is not None]
    if not mesh_models:
        raise ConvError("%s: nessuna mesh trovata" % scene.path)
    slots = {}
    rest = []
    for mm in mesh_models:
        nm = mm.name.split(":")[-1]
        if nm[:4].lower() == "mesh" and nm[4:].isdigit() and int(nm[4:]) not in slots:
            slots[int(nm[4:])] = mm
        else:
            rest.append(mm)
    nxt = 0
    for mm in rest:
        while nxt in slots:
            nxt += 1
        slots[nxt] = mm
    if sorted(slots) != list(range(len(slots))):
        warn("numerazione MeshN con buchi (%s): le mesh vengono compattate"
             % ", ".join(str(k) for k in sorted(slots)))
    stats = {}
    mo = Model()
    for k in sorted(slots):
        me = build_mesh(scene, slots[k], bone_index, mat_mapping, default_mat, opts, stats)
        if me is not None:
            mo.meshes.append(me)
    if stats.get("over4"):
        warn("%d vertici avevano piu' di %d ossa: tenute le %d piu' influenti e rinormalizzate"
             % (stats["over4"], opts.max_influences, opts.max_influences))
    mo.materials = mats
    return mo, hier


def convert(fbx_path, out_path, opts, addon_path=None, shadow_path=None):
    log("fbx2nbd %s" % __version__)
    texbank = TextureBank(opts)
    scene = FbxScene(fbx_path)
    main_model, main_hier = convert_scene(scene, texbank, opts, "modello principale")
    addon = None
    if addon_path:
        sc2 = FbxScene(addon_path)
        addon = convert_scene(sc2, texbank, opts, "modello addon")
    log("  texture: %d" % len(texbank.items))
    for mo in [main_model] + ([addon[0]] if addon else []):
        a, b = opts.texture_size_fields or (0x100, 0x100)
        mo.texrefs = [TexRef(i, a, b, 0) for i in range(len(texbank.items))]
    nbd = NBD()
    nbd.slots = [("TEX", texbank.items, len(texbank.items)), ("AMO", main_model, 0), ("AHI", main_hier, 0)]
    if shadow_path or addon:
        nbd.slots.append((None, None, 0))
        if shadow_path:
            nbd.slots.append(("SDW", open(shadow_path, "rb").read(), 0))
            log("  ombra: %s" % os.path.basename(shadow_path))
        else:
            nbd.slots.append((None, None, 0))
        if addon:
            nbd.slots.append(("AMO", addon[0], 0))
            nbd.slots.append(("AHI", addon[1], 0))
    data = write_nbd(nbd)
    with open(out_path, "wb") as f:
        f.write(data)
    log("Fatto: %s (%d byte)" % (out_path, len(data)))
    return nbd


# =============================================================================
#  --info : descrizione leggibile di un NBD
# =============================================================================

def describe_nbd(path):
    nbd = read_nbd(path)
    print("%s" % path)
    for si, (name, obj, cnt) in enumerate(nbd.slots):
        if name is None:
            continue
        if name == "TEX":
            print("  [%d] TEX: %d texture" % (si, len(obj)))
            for i, t in enumerate(obj):
                info = tim2_info(t.get_tim2()) or {}
                print("       #%d %sx%s  (%d byte compressi)" % (i, info.get("w"), info.get("h"), len(t.raw or b"")))
        elif name == "AMO":
            print("  [%d] AMO: %d mesh, %d materiali, %d texture-ref" % (si, len(obj.meshes), len(obj.materials), len(obj.texrefs)))
            for i, m in enumerate(obj.meshes):
                ns = [len(ss) for _, ss in m.strip_lists]
                mx = max((len(s) for _, ss in m.strip_lists for s in ss), default=0)
                maxinf = max((len(w) for w in (m.weights or [])), default=0)
                print("       mesh %d: %d vertici, strip %s (max %d indici), materiali %s, ossa %s, max %d pesi/vertice%s"
                      % (i, len(m.verts), "+".join(map(str, ns)), mx, m.matrefs,
                         m.jointrefs if m.jointrefs is not None else "-", maxinf,
                         ", RenderAttribs" if m.rattribs else ""))
            for i, ma in enumerate(obj.materials):
                print("       materiale %d: %s diff=(%.2f %.2f %.2f) tex=%s" % (
                    i, MAT_TYPES.get(ma.type, hex(ma.type)), ma.diffuse[0], ma.diffuse[1], ma.diffuse[2], ma.texrefs))
            print("       texture-ref: %s" % [(t.index, t.a, t.b) for t in obj.texrefs])
        elif name == "AHI":
            print("  [%d] AHI: %d nodi, radici %s" % (si, len(obj.nodes), obj.roots))
            names = {T_NODE: "nodo", T_NODE_JOINT: "joint", T_NODE_MESH: "mesh"}
            for n in obj.nodes:
                print("       Node%-3d %-5s padre %3d  gruppo %d  pos (%.2f %.2f %.2f)%s" % (
                    n.id, names.get(n.type, hex(n.type)), n.parent, n.group_id, n.trn[0], n.trn[1], n.trn[2],
                    "  rot (%.3f %.3f %.3f)" % n.rot[:3] if any(abs(x) > 1e-6 for x in n.rot[:3]) else ""))
        else:
            print("  [%d] %s: %d byte" % (si, name, len(obj)))


# =============================================================================
#  Riga di comando
# =============================================================================

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="fbx2nbd",
        description="Converte un FBX (3ds Max, OBTool, Blender...) in un .NBD di Resident Evil Outbreak.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Esempi:\n"
               "  fbx2nbd.py jill.fbx jill.nbd\n"
               "  fbx2nbd.py jill.fbx jill.nbd --skeleton N54.NBD\n"
               "  fbx2nbd.py --info N54.NBD\n")
    ap.add_argument("input", nargs="?", help="file .fbx da convertire")
    ap.add_argument("output", nargs="?", help="file .nbd da creare (default: stesso nome .nbd)")
    ap.add_argument("--info", metavar="NBD", help="mostra la struttura di un file NBD ed esce")
    ap.add_argument("--roundtrip", metavar="NBD", help="legge e riscrive un NBD e controlla che sia identico")
    ap.add_argument("--skeleton", metavar="NBD", help="copia lo scheletro (AHI) da un NBD originale")
    ap.add_argument("--addon", metavar="FBX", help="modello aggiuntivo (default: <nome>.addon.fbx se esiste)")
    ap.add_argument("--shadow", metavar="SDW", help="file ombra (default: <nome>.sdw se esiste)")
    ap.add_argument("--no-addon", action="store_true", help="non cercare <nome>.addon.fbx / <nome>.sdw")
    ap.add_argument("--scale", type=float, default=1.0, help="moltiplica posizioni e ossa (default 1)")
    ap.add_argument("--no-auto-scale", action="store_true",
                    help="non correggere da solo la scala quando il bacino non e' a ~110")
    ap.add_argument("--max-influences", type=int, default=4, help="ossa massime per vertice (default 4)")
    ap.add_argument("--min-weight", type=float, default=1.0, help="pesi sotto questa percentuale vengono scartati (default 1)")
    ap.add_argument("--strip-max-len", type=int, default=0, help="lunghezza massima di una strip (0 = nessun limite)")
    ap.add_argument("--strip-max-bones", type=int, default=0, help="ossa massime per strip a peso parziale (0 = nessun limite)")
    ap.add_argument("--texdir", action="append", default=[], help="cartella in cui cercare le texture (ripetibile)")
    ap.add_argument("--placeholder", action="store_true", help="texture mancanti -> segnaposto grigio invece di errore")
    ap.add_argument("--keep-texture-size", action="store_true", help="non ridimensionare texture non potenza di 2")
    ap.add_argument("--keep-bone-rotations", action="store_true",
                    help="tieni le rotazioni di riposo delle ossa (come OBTool) invece di azzerarle")
    ap.add_argument("--obtool-compat", action="store_true",
                    help="trasforma vertici e ossa esattamente come OBTool (implica --keep-bone-rotations)")
    ap.add_argument("-q", "--quiet", action="store_true", help="meno messaggi")
    a = ap.parse_args(argv)
    global _LOG_QUIET
    _LOG_QUIET = a.quiet
    try:
        if a.info:
            describe_nbd(a.info)
            return 0
        if a.roundtrip:
            src = open(a.roundtrip, "rb").read()
            out = write_nbd(read_nbd(src))
            same = out == src
            print("%s: riscrittura %s" % (a.roundtrip, "IDENTICA" if same else "DIVERSA (%d vs %d byte)" % (len(out), len(src))))
            return 0 if same else 1
        if not a.input:
            ap.print_help()
            return 1
        out = a.output or os.path.splitext(a.input)[0] + ".nbd"
        opts = Options()
        opts.scale = a.scale
        opts.auto_scale = not a.no_auto_scale
        opts.max_influences = max(1, a.max_influences)
        opts.min_weight = a.min_weight
        opts.strip_max_len = a.strip_max_len
        opts.strip_max_bones = a.strip_max_bones
        opts.placeholder = a.placeholder
        opts.fix_texture_size = not a.keep_texture_size
        opts.obtool_compat = a.obtool_compat
        opts.keep_bone_rotations = a.keep_bone_rotations or a.obtool_compat
        opts.extra_tex_dirs = a.texdir
        if a.skeleton:
            sk = nbd_slot(read_nbd(a.skeleton), "AHI")
            if sk is None:
                raise ConvError("%s non contiene uno scheletro AHI" % a.skeleton)
            opts.skeleton = sk
        stem = os.path.splitext(a.input)[0]
        addon = a.addon or (None if a.no_addon or not os.path.isfile(stem + ".addon.fbx") else stem + ".addon.fbx")
        shadow = a.shadow or (None if a.no_addon or not os.path.isfile(stem + ".sdw") else stem + ".sdw")
        if not a.no_addon and os.path.isfile(stem + ".effect.fbx"):
            warn("trovato %s: i modelli 'stanza/effetto' non sono supportati, lo ignoro" % (stem + ".effect.fbx"))
        convert(a.input, out, opts, addon, shadow)
        return 0
    except ConvError as e:
        print("ERRORE: %s" % e)
        return 2
    except (IOError, OSError) as e:
        print("ERRORE: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
