#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bin_compressor.py - compressore di animazioni per i .bin di Resident Evil Outbreak (PS2)

Trascina un .bin sullo script (o lancialo da riga di comando): analizza le animazioni, ti mostra
quanto spazio si risparmia a ogni livello di aggressivita' e scrive un NUOVO .bin
(<nome>_compresso.bin) accanto all'originale, che non viene mai modificato.

Come funziona
-------------
Ogni traccia (rot/loc/scale XYZ di un nodo) e' una curva Hermite fatta di chiavi. Lo script toglie
le chiavi che la curva ricostruisce gia' da sola entro una tolleranza, e dove serve ricalcola le
tangenti delle chiavi vicine (originali, secante o minimi quadrati) per tenere la curva fedele.
L'errore e' sempre misurato contro la curva ORIGINALE (mai a cascata), quindi la tolleranza e' un
limite reale. Prima e ultima chiave di ogni traccia restano sempre: durata e loop non cambiano.

Il resto del file (header, tabella dei puntatori, blocchi non toccabili) resta com'e'; i puntatori
della tabella vengono riscritti per i nuovi offset. Formati supportati: 0x11, 0x12, 0x22.
Blocchi non riconosciuti (mostri, ecc.) vengono lasciati intatti.

Uso:
    python bin_compressor.py file.bin                  (chiede il livello)
    python bin_compressor.py file.bin --level 3        (senza domande)
    python bin_compressor.py file.bin --dry-run        (solo report)
"""
import argparse
import bisect
import heapq
import math
import os
import struct
import sys
import time

import numpy as np

# ---------------------------------------------------------------- costanti (come importer/exporter)
ROT_PRECISION = 2607.5945876
LOC_PRECISION = 16.0
SCL_PRECISION = 16.0
FACE_PRECISION = 256.0
FACE_PRECISION_ALT = 512.0

TRACK_PROP = {0x001: ("scale", 0), 0x002: ("scale", 1), 0x004: ("scale", 2),
              0x008: ("rot", 0), 0x010: ("rot", 1), 0x020: ("rot", 2),
              0x040: ("loc", 0), 0x080: ("loc", 1), 0x100: ("loc", 2)}
SECTION_START = {0x0A: 0, 0x0B: 10, 0x0C: 10, 0x0D: 10, 0x06: 22, 0x04: 28}
SECTION_NAME = {0x0A: "lower", 0x0B: "upper", 0x0C: "upper", 0x0D: "upper", 0x06: "face", 0x04: "hand"}
KEY_SIZE = {0x11: 4, 0x12: 8, 0x22: 16}

# Livelli: moltiplicatore della "unita' di tolleranza" di ogni classe di canale.
LEVELS = [
    # nome, moltiplicatore, descrizione
    ("Minimo",       0.0,  "toglie solo chiavi identiche alla curva (errore <= 1 passo di quantizzazione)"),
    ("Sicuro",       0.25, "differenze invisibili: ~0.25 gradi sulle rotazioni, ~0.1 unita' sulle posizioni"),
    ("Bilanciato",   0.6,  "~0.6 gradi / ~0.25 unita': consigliato nella maggior parte dei casi"),
    ("Aggressivo",   1.2,  "~1.2 gradi / ~0.5 unita': possibile lieve perdita di morbidezza"),
    ("Massimo",      2.5,  "~2.5 gradi / ~1 unita': per ridurre al massimo, controlla in gioco"),
]
DEFAULT_LEVEL = 3

# unita' di tolleranza (moltiplicate per il livello): gradi per le rot, unita' del rig per loc/scale
UNIT_ROT = 1.0
UNIT_ROT_FACE = 0.5
UNIT_LOC = 0.4
UNIT_LOC_ROOT = 0.2     # Node0-2: e' l'avanzamento del personaggio
UNIT_LOC_FACE = 0.1
UNIT_SCALE = 0.02


# ================================================================= parsing
def read_table(d):
    """Ritorna (desc_start, righe, fine_tabella) come Studio / Mots_Extractor."""
    if len(d) < 16:
        raise ValueError("file troppo corto")
    ds = struct.unpack_from("<I", d, 12)[0]
    if ds <= 0 or ds >= len(d):
        raise ValueError("header non riconosciuto (byte 12-15 non e' un offset valido)")
    rows, pos, mn = [], ds, len(d)
    while pos < mn and pos + 20 <= len(d):
        r = struct.unpack_from("<5I", d, pos)
        for p in r:
            if p not in (0, 0xFFFFFFFF) and p < mn:
                mn = p
        if pos >= mn:
            break
        rows.append(r)
        pos += 20
    if not rows:
        raise ValueError("tabella delle animazioni vuota")
    return ds, rows, pos


def block_header(d, p):
    """(tipo, count, size, loop, loopFrame) se in p c'e' un blocco .mot plausibile, altrimenti None."""
    if p < 0 or p + 20 > len(d):
        return None
    t, c, sz, lp, lf = struct.unpack_from("<IIIIf", d, p)
    if t not in (0x80000001, 0x80000002) or sz <= 20 or p + sz > len(d) or sz % 4:
        return None
    if (c & 0xFF) == 0 or (c & 0xFF) > 0x20:
        return None
    return t, c, sz, lp, lf


def node_div(node, prop, fmt):
    """Divisore valore int16 -> unita' (1.0 per le chiavi float 0x22)."""
    if fmt == 0x22:
        return 1.0
    if 23 <= node <= 27 and prop == "loc":
        return FACE_PRECISION_ALT if node in (24, 26) else FACE_PRECISION
    if prop == "scale":
        return SCL_PRECISION
    if prop == "loc":
        return LOC_PRECISION
    return ROT_PRECISION


class Track:
    __slots__ = ("t_type", "fmt", "tid", "node", "prop", "raw", "F", "V", "C0", "C1",
                 "linear", "rpu", "unit_raw", "floor_raw", "removals", "limits", "block_label",
                 "section")

    def keys_bytes(self, keep=None, C0=None, C1=None):
        F, V = self.F, self.V
        C0 = self.C0 if C0 is None else C0
        C1 = self.C1 if C1 is None else C1
        if keep is None:
            keep = np.ones(len(F), bool)
        n = int(keep.sum())
        ksz = KEY_SIZE[self.fmt]
        out = bytearray(struct.pack("<III", self.t_type, n, 12 + n * ksz))
        if self.fmt == 0x11:
            arr = np.zeros(n, dtype=[("v", "<i2"), ("f", "<i2")])
            arr["v"] = np.rint(V[keep]); arr["f"] = np.rint(F[keep])
        elif self.fmt == 0x12:
            arr = np.zeros(n, dtype=[("v", "<i2"), ("f", "<i2"), ("c0", "<i2"), ("c1", "<i2")])
            arr["v"] = np.rint(V[keep]); arr["f"] = np.rint(F[keep])
            arr["c0"] = np.clip(np.rint(C0[keep]), -32768, 32767)
            arr["c1"] = np.clip(np.rint(C1[keep]), -32768, 32767)
        else:
            arr = np.zeros(n, dtype=[("v", "<f4"), ("f", "<f4"), ("c0", "<f4"), ("c1", "<f4")])
            arr["v"] = V[keep]; arr["f"] = F[keep]; arr["c0"] = C0[keep]; arr["c1"] = C1[keep]
        out += arr.tobytes()
        return bytes(out)


class Block:
    def __init__(self, off, header, nodes):
        self.off = off
        self.header = header          # bytes (20)
        self.nodes = nodes            # lista di ('stub', bytes) | ('node', n_type, [tracks])
        self.size = struct.unpack_from("<I", header, 8)[0]

    def tracks(self):
        for nd in self.nodes:
            if nd[0] == "node":
                for t in nd[3]:
                    if t.F is not None:
                        yield t


def _class_of(node, prop):
    """(unita' di tolleranza, e' una rotazione/posizione ...)."""
    if prop == "rot":
        return UNIT_ROT_FACE if 22 <= node <= 27 else UNIT_ROT
    if prop == "loc":
        if node in (0, 1, 2):
            return UNIT_LOC_ROOT
        if 23 <= node <= 27:
            return UNIT_LOC_FACE
        return UNIT_LOC
    return UNIT_SCALE


def parse_block(d, off, label=""):
    h = block_header(d, off)
    if not h:
        return None
    t, c, sz, lp, lf = h
    start_node = SECTION_START.get(c & 0xFF)
    if start_node is None:
        return None
    end = off + sz
    pos = off + 20
    nodes = []
    node_idx = start_node
    for _ in range(c):
        if pos + 4 > end:
            return None
        n_type = struct.unpack_from("<I", d, pos)[0]
        if n_type < 0x80000000:
            nodes.append(("stub", d[pos:pos + 4]))
            pos += 4
            node_idx += 1
            continue
        if pos + 12 > end:
            return None
        n_type, n_sub, n_size = struct.unpack_from("<III", d, pos)
        if n_size < 12 or pos + n_size > end:
            return None
        tp, nend, tracks = pos + 12, pos + n_size, []
        for _ in range(n_sub):
            if tp + 12 > nend:
                return None
            t_type, t_keys, t_size = struct.unpack_from("<III", d, tp)
            if t_size < 12 or tp + t_size > nend:
                return None
            fmt, tid = (t_type >> 16) & 0xFF, t_type & 0xFFF
            tr = Track()
            tr.t_type, tr.fmt, tr.tid, tr.node = t_type, fmt, tid, node_idx
            tr.raw = d[tp:tp + t_size]
            tr.F = tr.V = tr.C0 = tr.C1 = None
            tr.removals = []
            tr.section = SECTION_NAME.get(c & 0xFF, "?")
            tr.block_label = label
            ksz = KEY_SIZE.get(fmt)
            if ksz and tid in TRACK_PROP and t_keys >= 1 and t_size == 12 + t_keys * ksz:
                body = d[tp + 12: tp + t_size]
                if fmt == 0x11:
                    a = np.frombuffer(body, dtype=[("v", "<i2"), ("f", "<i2")])
                    V, F = a["v"].astype(float), a["f"].astype(float)
                    C0 = C1 = np.zeros(t_keys)
                elif fmt == 0x12:
                    a = np.frombuffer(body, dtype=[("v", "<i2"), ("f", "<i2"), ("c0", "<i2"), ("c1", "<i2")])
                    V, F = a["v"].astype(float), a["f"].astype(float)
                    C0, C1 = a["c0"].astype(float), a["c1"].astype(float)
                else:
                    a = np.frombuffer(body, dtype=[("v", "<f4"), ("f", "<f4"), ("c0", "<f4"), ("c1", "<f4")])
                    V, F = a["v"].astype(float), a["f"].astype(float)
                    C0, C1 = a["c0"].astype(float), a["c1"].astype(float)
                if np.all(np.isfinite(V)) and np.all(np.isfinite(F)) and np.all(np.diff(F) > 0):
                    prop = TRACK_PROP[tid][0]
                    tr.prop = prop
                    tr.F, tr.V, tr.C0, tr.C1 = F, V, C0.copy(), C1.copy()
                    tr.linear = (fmt == 0x11)
                    div = node_div(node_idx, prop, fmt)
                    tr.rpu = abs(div)                        # raw per unita' (radiante per le rot)
                    unit = _class_of(node_idx, prop)
                    unit_raw = (math.radians(unit) if prop == "rot" else unit) * tr.rpu
                    tr.unit_raw = unit_raw
                    tr.floor_raw = 1.0 if fmt != 0x22 else 1e-4
            tracks.append(tr)
            tp += t_size
        if tp != nend:
            return None
        nodes.append(("node", n_type, n_sub, tracks))
        pos = nend
        node_idx += 1
    if pos != end:
        return None
    blk = Block(off, d[off:off + 20], nodes)
    blk.label = label
    return blk


def build_block(blk, chosen_level_fn):
    """Ricostruisce i byte del blocco; chosen_level_fn(track) -> (keep, C0, C1) o None per lasciare uguale."""
    body = bytearray()
    for nd in blk.nodes:
        if nd[0] == "stub":
            body += nd[1]
            continue
        _, n_type, n_sub, tracks = nd
        tb = bytearray()
        for t in tracks:
            res = chosen_level_fn(t) if t.F is not None else None
            tb += t.keys_bytes(*res) if res is not None else t.raw
        body += struct.pack("<III", n_type, n_sub, 12 + len(tb)) + tb
    hdr = bytearray(blk.header)
    struct.pack_into("<I", hdr, 8, 20 + len(body))
    return bytes(hdr) + bytes(body)


# ================================================================= riduzione delle chiavi
def hermite_eval(F, V, C0, C1, S, linear):
    i = np.clip(np.searchsorted(F, S, side="right") - 1, 0, len(F) - 2)
    h = F[i + 1] - F[i]
    t = np.clip((S - F[i]) / h, 0.0, 1.0)
    v0, v1 = V[i], V[i + 1]
    if linear:
        out = v0 + (v1 - v0) * t
    else:
        t2, t3 = t * t, t * t * t
        out = ((2 * t3 - 3 * t2 + 1) * v0 + (t3 - 2 * t2 + t) * h * C1[i]
               + (-2 * t3 + 3 * t2) * v1 + (t3 - t2) * h * C0[i + 1])
    out = np.where(S <= F[0], V[0], out)
    return np.where(S >= F[-1], V[-1], out)


def reduce_track(tr, tmax):
    """Greedy: toglie ripetutamente la chiave la cui rimozione costa meno (errore massimo contro la
    curva originale), finche' il costo supera tmax. Salva in tr.removals la lista
    (k, a, b, m0, m1, errore_massimo_corrente)."""
    F, V = tr.F, tr.V
    C0, C1 = tr.C0.copy(), tr.C1.copy()
    n = len(F)
    tr.removals = []
    if n < 3:
        return
    S = np.arange(F[0], F[-1] + 1e-9, 0.5)
    O = hermite_eval(F, V, tr.C0, tr.C1, S, tr.linear)
    IL = np.searchsorted(S, F - 1e-9, side="left")
    IR = np.searchsorted(S, F + 1e-9, side="right")
    int_fmt = tr.fmt != 0x22
    linear = tr.linear

    def best(a, b):
        s = S[IL[a]:IR[b]]
        o = O[IL[a]:IR[b]]
        h = F[b] - F[a]
        t = (s - F[a]) / h
        if linear:
            e = float(np.max(np.abs(o - (V[a] + (V[b] - V[a]) * t))))
            return e, 0.0, 0.0
        t2 = t * t
        t3 = t2 * t
        resid = o - ((2 * t3 - 3 * t2 + 1) * V[a] + (-2 * t3 + 3 * t2) * V[b])
        B0 = (t3 - 2 * t2 + t) * h
        B1 = (t3 - t2) * h
        sec = (V[b] - V[a]) / h
        a00, a01, a11 = float(B0 @ B0), float(B0 @ B1), float(B1 @ B1)
        det = a00 * a11 - a01 * a01
        if det > 1e-12 * max(a00 * a11, 1e-30):
            r0, r1 = float(B0 @ resid), float(B1 @ resid)
            ls0 = (a11 * r0 - a01 * r1) / det
            ls1 = (a00 * r1 - a01 * r0) / det
        else:
            ls0 = ls1 = sec
        m0 = np.array([C1[a], sec, ls0])
        m1 = np.array([C0[b], sec, ls1])
        if int_fmt:
            m0 = np.clip(np.rint(m0), -32768, 32767)
            m1 = np.clip(np.rint(m1), -32768, 32767)
        E = np.abs(resid[None, None, :] - m0[:, None, None] * B0 - m1[None, :, None] * B1).max(axis=2)
        i, j = np.unravel_index(int(np.argmin(E)), E.shape)
        return float(E[i, j]), float(m0[i]), float(m1[j])

    prev = list(range(-1, n - 1))
    nxt = list(range(1, n + 1))
    nxt[-1] = -1
    ver = [0] * n
    dead = [False] * n
    info = {}
    heap = []

    def push(k):
        a, b = prev[k], nxt[k]
        if a < 0 or b < 0:
            return
        e, m0, m1 = best(a, b)
        info[k] = (m0, m1, a, b)
        heapq.heappush(heap, (e, k, ver[k]))

    for k in range(1, n - 1):
        push(k)
    runmax = 0.0
    while heap:
        e, k, v = heapq.heappop(heap)
        if dead[k] or ver[k] != v:
            continue
        if e > tmax:
            break
        m0, m1, a, b = info[k]
        C1[a], C0[b] = m0, m1
        dead[k] = True
        nxt[a], prev[b] = b, a
        runmax = max(runmax, e)
        tr.removals.append((k, a, b, m0, m1, runmax))
        for x in (a, b):
            ver[x] += 1
            push(x)


def thr_raw(tr, level_idx):
    return max(LEVELS[level_idx][1] * tr.unit_raw, tr.floor_raw)


def removals_for(tr, level_idx):
    """Quante rimozioni (prefisso) rispettano la soglia del livello."""
    if not tr.removals:
        return 0
    thr = thr_raw(tr, level_idx)
    runs = [r[5] for r in tr.removals]
    return bisect.bisect_right(runs, thr + 1e-12)


def apply_level(tr, level_idx):
    """(keep, C0, C1) del livello scelto."""
    n = removals_for(tr, level_idx)
    keep = np.ones(len(tr.F), bool)
    C0, C1 = tr.C0.copy(), tr.C1.copy()
    for k, a, b, m0, m1, _ in tr.removals[:n]:
        keep[k] = False
        C1[a], C0[b] = m0, m1
    return keep, C0, C1


# ================================================================= analisi del file
class Analysis:
    pass


def analyze(d, progress=True):
    A = Analysis()
    ds, rows, tend = read_table(d)
    A.ds, A.rows, A.tend = ds, rows, tend
    refs = sorted({p for r in rows for p in r if p not in (0, 0xFFFFFFFF)})
    A.refs = refs
    refset = set(refs)
    # segmentazione dell'area dati: blocchi validi in sequenza e tratti grezzi tra l'uno e l'altro
    segs = []                         # [start, end, kind('block'|'raw'), parsed Block o None]
    pos = tend
    first_ptr = refs[0] if refs else len(d)
    if first_ptr < tend:
        raise ValueError("puntatore dentro la tabella: struttura non riconosciuta")
    while pos < len(d):
        if block_header(d, pos) and (pos in refset or True):
            sz = struct.unpack_from("<I", d, pos + 8)[0]
            segs.append([pos, pos + sz, "block", None])
            pos += sz
        else:
            s = pos
            pos += 4
            while pos < len(d) and not (block_header(d, pos) or pos in refset):
                pos += 4
            if pos > len(d):
                pos = len(d)
            segs.append([s, pos, "raw", None])
    A.segs = segs
    # un puntatore deve cadere all'inizio di un segmento
    starts = {s[0] for s in segs}
    bad = [p for p in refs if p not in starts]
    if bad:
        raise ValueError(f"{len(bad)} puntatori non cadono all'inizio di un blocco (es. 0x{bad[0]:X}): formato non gestito")
    for s in segs:
        s.append(s[0] in refset)       # referenziato?
    A.referenced = [s for s in segs if s[4]]
    A.unref_bytes = sum(s[1] - s[0] for s in segs if not s[4])
    A.unref_blocks = sum(1 for s in segs if not s[4] and s[2] == "block")
    # parse dei blocchi referenziati
    t0 = time.time()
    tracks = []
    n_unparsed = 0
    for i, s in enumerate(A.referenced):
        if s[2] != "block":
            n_unparsed += 1
            continue
        blk = parse_block(d, s[0], label=f"0x{s[0]:X}")
        if blk is None:
            n_unparsed += 1
            continue
        s[3] = blk
        tracks.extend(blk.tracks())
    A.tracks = tracks
    A.n_unparsed = n_unparsed
    A.total_keys = sum(len(t.F) for t in tracks)
    tmax_lv = len(LEVELS) - 1
    done = 0
    for t in tracks:
        reduce_track(t, thr_raw(t, tmax_lv))
        done += 1
        if progress and (done % 200 == 0 or done == len(tracks)):
            print(f"\r  analisi tracce: {done}/{len(tracks)}  ({time.time() - t0:.0f}s)", end="", flush=True)
    if progress:
        print()
    return A


def level_stats(A, li):
    removed_keys = 0
    removed_bytes = 0
    worst = {"rot": 0.0, "loc": 0.0, "scale": 0.0}
    for t in A.tracks:
        n = removals_for(t, li)
        removed_keys += n
        removed_bytes += n * KEY_SIZE[t.fmt]
        if n:
            e = t.removals[n - 1][5] / t.rpu
            if t.prop == "rot":
                e = math.degrees(e)
            worst[t.prop] = max(worst[t.prop], e)
    return removed_keys, removed_bytes, worst


# ================================================================= scrittura
def build_output(d, A, li, drop_unref):
    """Nuovo file con il livello li. Ritorna (bytes, mappa vecchio offset -> nuovo)."""
    out_data = bytearray()
    remap = {}
    base = A.tend
    for s in A.segs:
        start, end, kind, blk, referenced = s
        if not referenced and drop_unref:
            continue
        remap[start] = base + len(out_data)
        if blk is not None:
            out_data += build_block(blk, lambda t: apply_level(t, li))
        else:
            out_data += d[start:end]
    new = bytearray(d[:A.tend])
    # tabella: stessi byte con i puntatori rimappati
    pos = A.ds
    while pos < A.tend:
        for j in range(5):
            p = struct.unpack_from("<I", new, pos + 4 * j)[0]
            if p not in (0, 0xFFFFFFFF):
                struct.pack_into("<I", new, pos + 4 * j, remap[p])
        pos += 20
    new += out_data
    return bytes(new), remap


def verify(d, A, new, remap, li, drop_unref):
    """Controlli sul file scritto. Ritorna (ok, messaggi, errore massimo per classe)."""
    msgs = []
    ok = True
    try:
        ds2, rows2, tend2 = read_table(new)
    except Exception as e:
        return False, [f"il nuovo file non si rilegge: {e}"], {}
    if ds2 != A.ds or tend2 != A.tend or len(rows2) != len(A.rows):
        ok = False
        msgs.append("tabella diversa dall'originale (numero/posizione righe)")
    for r_old, r_new in zip(A.rows, rows2):
        for po, pn in zip(r_old, r_new):
            if po in (0, 0xFFFFFFFF):
                if po != pn:
                    ok = False
                    msgs.append("slot vuoto modificato")
            elif remap.get(po) != pn:
                ok = False
                msgs.append("puntatore non coerente")
    if new[:A.ds] != d[:A.ds]:
        ok = False
        msgs.append("header modificato")
    # ogni blocco riletto: header uguale (tipo, count, loop) e stessa struttura di tracce
    worst = {"rot": 0.0, "loc": 0.0, "scale": 0.0}
    n_checked = 0
    for s in A.referenced:
        if s[3] is None:
            continue
        old = s[3]
        nb = parse_block(new, remap[s[0]], label="verifica")
        if nb is None:
            ok = False
            msgs.append(f"blocco 0x{s[0]:X} non si rilegge")
            continue
        h_old = struct.unpack_from("<IIIIf", old.header)
        h_new = struct.unpack_from("<IIIIf", nb.header)
        if (h_old[0], h_old[1], h_old[3], h_old[4]) != (h_new[0], h_new[1], h_new[3], h_new[4]):
            ok = False
            msgs.append(f"header del blocco 0x{s[0]:X} cambiato")
        to, tn = list(old.tracks()), list(nb.tracks())
        if len(to) != len(tn):
            ok = False
            msgs.append(f"blocco 0x{s[0]:X}: numero tracce diverso")
            continue
        for a, b in zip(to, tn):
            n_checked += 1
            if a.t_type != b.t_type or a.F[0] != b.F[0] or a.F[-1] != b.F[-1]:
                ok = False
                msgs.append("traccia con estremi cambiati")
                continue
            S = np.arange(a.F[0], a.F[-1] + 1e-9, 0.5)
            o = hermite_eval(a.F, a.V, a.C0, a.C1, S, a.linear)
            c = hermite_eval(b.F, b.V, b.C0, b.C1, S, b.linear)
            e = float(np.max(np.abs(o - c))) if len(S) else 0.0
            if e > thr_raw(a, li) + 1e-6 + (0.0 if a.fmt == 0x22 else 1e-9):
                ok = False
                msgs.append(f"traccia fuori tolleranza ({a.section} Node{a.node}): {e:.3f} raw")
            eu = e / a.rpu
            if a.prop == "rot":
                eu = math.degrees(eu)
            worst[a.prop] = max(worst[a.prop], eu)
    msgs.append(f"{n_checked} tracce riconfrontate con l'originale")
    return ok, msgs, worst


# ================================================================= interfaccia
def fmt_size(n):
    return f"{n:,}".replace(",", ".") + " B"


def ask(prompt, default=None):
    try:
        s = input(prompt).strip()
    except EOFError:
        s = ""
    return s if s else (str(default) if default is not None else "")


def out_path_for(path):
    stem, ext = os.path.splitext(path)
    cand = f"{stem}_compresso{ext or '.bin'}"
    i = 2
    while os.path.exists(cand):
        cand = f"{stem}_compresso{i}{ext or '.bin'}"
        i += 1
    return cand


def process(path, args):
    print("=" * 72)
    print(f"File: {path}")
    with open(path, "rb") as f:
        d = f.read()
    try:
        A = analyze(d)
    except ValueError as e:
        print(f"  ERRORE: {e}")
        return False
    if not A.tracks:
        print("  Nessuna traccia comprimibile trovata (mostri o formato non gestito).")
        return False

    anim_bytes = sum(s[1] - s[0] for s in A.referenced)
    print(f"  {len(A.rows)} righe in tabella, {len(A.referenced)} blocchi referenziati "
          f"({fmt_size(anim_bytes)}), {len(A.tracks)} tracce con {A.total_keys} chiavi")
    if A.n_unparsed:
        print(f"  {A.n_unparsed} blocchi non riconosciuti (mostri o altro): lasciati intatti")
    if A.unref_bytes:
        print(f"  Dati NON referenziati dalla tabella: {fmt_size(A.unref_bytes)} "
              f"({A.unref_blocks} blocchi .mot orfani + spazio vuoto)")

    print()
    print(f"  {'Liv':<4}{'Nome':<12}{'Chiavi tolte':>14}{'Risparmio':>14}{'Nuovo file':>14}"
          f"{'Err. rot':>10}{'Err. pos':>10}")
    stats = []
    for li, (name, _, desc) in enumerate(LEVELS):
        k, b, w = level_stats(A, li)
        stats.append((k, b, w))
        print(f"  {li + 1:<4}{name:<12}{k:>8} ({100 * k / A.total_keys:4.1f}%)"
              f"{fmt_size(b):>14}{fmt_size(len(d) - b):>14}{w['rot']:>9.2f}°{w['loc']:>9.2f}u")
    print()
    for li, (name, _, desc) in enumerate(LEVELS):
        print(f"   {li + 1} = {name}: {desc}")
    print("   (errore = scarto massimo dalla curva originale, rot in gradi, pos in unita' del rig)")
    print()

    if args.level is not None:
        li = args.level - 1
    else:
        if args.dry_run:
            return True
        while True:
            s = ask(f"Livello di aggressivita' [1-{len(LEVELS)}, Invio = {DEFAULT_LEVEL}, 0 = esci]: ", DEFAULT_LEVEL)
            if s == "0" or s.lower() in ("q", "esci"):
                print("Nessun file scritto.")
                return True
            if s.isdigit() and 1 <= int(s) <= len(LEVELS):
                li = int(s) - 1
                break
            print("  Valore non valido.")
    if args.dry_run:
        return True

    drop = args.drop_unreferenced
    if A.unref_bytes and args.level is None and not args.drop_unreferenced:
        s = ask(f"Rimuovo anche i {fmt_size(A.unref_bytes)} non referenziati (residui)? [s/N]: ", "n")
        drop = s.lower() in ("s", "si", "sì", "y", "yes")

    new, remap = build_output(d, A, li, drop)
    ok, msgs, worst = verify(d, A, new, remap, li, drop)
    if not ok:
        print("\n  VERIFICA FALLITA, file NON scritto:")
        for m in msgs[:10]:
            print("   -", m)
        return False

    out = args.output if (args.output and len(args.files) == 1) else out_path_for(path)
    with open(out, "wb") as f:
        f.write(new)

    # riepilogo per sezione (lower/upper/face/hand)
    by_sec = {}
    for t in A.tracks:
        n = removals_for(t, li)
        rec = by_sec.setdefault(t.section, [0, 0])
        rec[0] += len(t.F)
        rec[1] += n
    print(f"\nLivello {li + 1} ({LEVELS[li][0]}): {fmt_size(len(d))} -> {fmt_size(len(new))} "
          f"(-{fmt_size(len(d) - len(new))}, {100 * (len(d) - len(new)) / len(d):.1f}%)")
    for sec in ("lower", "upper", "face", "hand"):
        if sec in by_sec:
            tot, rem = by_sec[sec]
            print(f"   {sec:<6} chiavi {tot:>6} -> {tot - rem:>6}  (-{100 * rem / tot:.0f}%)")
    print(f"Errore massimo verificato: rot {worst['rot']:.3f}°, pos {worst['loc']:.3f}u")
    if drop and A.unref_bytes:
        print(f"Rimossi {fmt_size(A.unref_bytes)} di dati non referenziati")
    elif A.unref_bytes:
        print(f"Dati non referenziati lasciati intatti ({fmt_size(A.unref_bytes)})")
    for m in msgs:
        print("  ✓", m)
    print(f"\nScritto: {out}\nL'originale non e' stato toccato.")
    return True


def main():
    ap = argparse.ArgumentParser(description="Compressore di animazioni per i .bin di RE Outbreak")
    ap.add_argument("files", nargs="*", help="uno o piu' .bin (puoi trascinarli sullo script)")
    ap.add_argument("--level", type=int, choices=range(1, len(LEVELS) + 1),
                    help="livello 1-5 senza domande (1 minimo ... 5 massimo)")
    ap.add_argument("-o", "--output", help="file di uscita (solo con un file in ingresso)")
    ap.add_argument("--drop-unreferenced", action="store_true",
                    help="rimuove i dati non referenziati dalla tabella")
    ap.add_argument("--dry-run", action="store_true", help="mostra solo il report, non scrive nulla")
    ap.add_argument("--no-pause", action="store_true", help="non aspettare Invio alla fine")
    args = ap.parse_args()

    files = [f.strip('"') for f in args.files]
    interactive = not files
    if interactive:
        print("Trascina qui un file .bin (o incolla il percorso) e premi Invio.")
        s = ask("File: ")
        if not s:
            return
        files = [s.strip('"')]
    args.files = files
    status = 0
    for p in files:
        if not os.path.isfile(p):
            print(f"File non trovato: {p}")
            status = 1
            continue
        try:
            if not process(p, args):
                status = 1
        except Exception as e:      # mai uscire di colpo: la finestra deve restare leggibile
            print(f"\nERRORE inatteso: {type(e).__name__}: {e}")
            status = 1
    if not args.no_pause and (interactive or args.level is None) and sys.stdin and sys.stdin.isatty():
        input("\nPremi Invio per chiudere...")
    sys.exit(status)


if __name__ == "__main__":
    main()
