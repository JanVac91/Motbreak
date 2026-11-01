#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
character_gen.py
================
Generatore di personaggi low-poly (UMANI e ZOMBIE) in T-pose per Resident Evil Outbreak,
modellati sullo scheletro Node1..Node35 del progetto. Esporta OBJ + MTL + texture PNG.

Si usa in due modi:
  - GUI:            python3 character_gen.py            (senza argomenti si apre la finestra)
  - riga di comando: python3 character_gen.py --kind umano --sex femmina --type lavoratore ...

Parametri
  --kind     umano | zombie
  --sex      maschio | femmina
  --type     poliziotto | civile | lavoratore
  --sub      (solo lavoratore) infermiere | dottore | cuoco | meccanico | random
  --skin     random | bianco | nero
  --hair     random | nero | castano | biondo | rosso | grigio | bianco | #rrggbb
  --eyes     random | marrone | nocciola | azzurro | verde | grigio | #rrggbb
  --quality  (solo umani) low | medium | high  -> 3000 / 6000 / 9000 triangoli al massimo
  --tris     tetto di triangoli personalizzato (umani 1500..9000, zombie 150..500)
  --seed     numero per ripetere lo stesso personaggio      --count N  quanti ne generi
  --out      cartella di uscita
  --skeleton BVH in T-pose: posizioni, nomi e gerarchia delle ossa (consigliato con --fbx)
  --fbx      esporta anche <nome>.fbx riggato: armatura "Node0" con le ossa del BVH, pesi automatici
             (giunture sfumate, mandibola, viso, dita), texture incorporata. Serve Blender installato:
             lo cerco da solo, altrimenti --blender "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe"

FBX in Blender: File > Import > FBX con le impostazioni predefinite (Automatic Bone Orientation spento).
Ogni osso ha la testa sul joint del BVH e la coda verso +Y del gioco, roll 0: a riposo i suoi assi locali
sono gli assi del gioco, come nel BVH, quindi le rotazioni XYZ di un .mot o di un BVH valgono uguali.

Sistema di riferimento (uguale al BVH in T-pose): Y verso l'alto, il personaggio guarda +Z,
+X = lato sinistro (SX) del personaggio, unita' del rig (bacino a y = 110, piedi a y = 0).
In Blender: File > Import > Wavefront (.obj), Forward = Z, Up = Y.

Umani: occhi (Eye_L/Eye_R), sopracciglia (Node23/Node25), palpebre (Node24/Node26) e mandibola
(Node27) sono gruppi separati e posizionati sui joint dello scheletro, cosi' si possono riggare per
le espressioni. Mani: pollice separato + un unico blocco per le altre quattro dita.
Zombie: stile PS1, faccia disegnata sulla texture 64x64, flat shading, massimo 500 triangoli.
"""
import argparse
import colorsys
import math
import os
import random
import struct
import sys
import zlib

import numpy as np

# ---------------------------------------------------------------------------------------------
# Scheletro (posizioni a riposo dal BVH in T-pose del progetto)
# ---------------------------------------------------------------------------------------------
SKEL = {
    "Node1": (0.000, 0.000, 0.000), "Node2": (0.000, 110.000, 0.000), "Node3": (0.000, 110.000, 0.000),
    "Node4": (7.814, 94.000, 0.000), "Node5": (7.814, 52.913, 1.000), "Node6": (7.814, 13.028, -1.000),
    "Node7": (-7.814, 94.000, 0.000), "Node8": (-7.814, 52.913, 1.000), "Node9": (-7.814, 13.028, -1.000),
    "Node10": (0.000, 111.000, 0.000), "Node11": (0.000, 123.958, -0.079),
    "Node12": (7.321, 143.754, -1.255), "Node13": (15.497, 143.754, -1.255),
    "Node14": (40.272, 143.754, -2.336), "Node15": (65.642, 143.754, -1.536),
    "Node16": (-7.321, 143.754, -1.255), "Node17": (-15.497, 143.754, -1.255),
    "Node18": (-40.272, 143.754, -2.336), "Node19": (-65.642, 143.754, -1.536),
    "Node20": (0.000, 147.648, -1.048), "Node21": (0.000, 155.077, -1.048), "Node22": (0.000, 155.078, -1.048),
    "Node23": (3.000, 162.524, 6.952), "Node24": (3.055, 161.678, 6.935),
    "Node25": (-3.000, 162.524, 6.952), "Node26": (-3.000, 161.678, 6.952),
    "Node27": (0.000, 157.537, -0.311),
    "Node28": (-66.643, 143.754, -1.536), "Node29": (-69.943, 142.554, 1.464),
    "Node30": (-75.543, 145.254, 0.931), "Node31": (-75.243, 144.954, -2.736),
    "Node32": (66.643, 143.754, -1.536), "Node33": (69.943, 142.554, 1.464),
    "Node34": (75.543, 145.254, 0.932), "Node35": (75.243, 144.954, -2.736),
}
J = {k: np.array(v, float) for k, v in SKEL.items()}

# Gerarchia usata per il rig quando non si carica un BVH (la stessa struttura di Struttura-Scheletro.txt).
# Caricando il BVH in T-pose (--skeleton / campo della GUI) gerarchia, nomi e posizioni vengono da li'.
DEFAULT_PARENTS = {
    "Node1": None, "Node2": "Node1", "Node3": "Node2",
    "Node4": "Node3", "Node5": "Node4", "Node6": "Node5", "Node7": "Node3", "Node8": "Node7", "Node9": "Node8",
    "Node10": "Node2", "Node11": "Node10",
    "Node12": "Node11", "Node13": "Node12", "Node14": "Node13", "Node15": "Node14",
    "Node16": "Node11", "Node17": "Node16", "Node18": "Node17", "Node19": "Node18",
    "Node20": "Node11", "Node21": "Node20", "Node22": "Node21",
    "Node23": "Node22", "Node24": "Node22", "Node25": "Node22", "Node26": "Node22", "Node27": "Node22",
    "Node28": "Node19", "Node29": "Node28", "Node30": "Node28", "Node31": "Node28",
    "Node32": "Node15", "Node33": "Node32", "Node34": "Node32", "Node35": "Node32",
}
SKEL_PARENTS = dict(DEFAULT_PARENTS)          # nome -> genitore, nell'ordine del BVH
SKEL_SOURCE = ["scheletro incorporato"]


def read_bvh_skeleton(path):
    """(posizioni a riposo {nome: xyz}, genitori {nome: genitore}) dalla gerarchia di un BVH."""
    stack, out, parents = [], {}, {}
    with open(path) as fh:
        for ln in fh:
            t = ln.split()
            if not t:
                continue
            if t[0] == "MOTION":
                break
            if t[0] in ("ROOT", "JOINT"):
                stack.append(t[1])
            elif t[0] == "End":
                stack.append(None)
            elif t[0] == "OFFSET":
                name = stack[-1]
                if name is not None:
                    off = np.array([float(x) for x in t[1:4]])
                    parent = next((s for s in reversed(stack[:-1]) if s is not None), None)
                    out[name] = off if parent is None else out[parent] + off
                    parents[name] = parent
            elif t[0] == "}" and stack:
                stack.pop()
    return out, parents


def load_skeleton(path):
    """Legge posizioni a riposo e gerarchia da un BVH e sostituisce quelle incorporate."""
    out, parents = read_bvh_skeleton(path)
    missing = [k for k in SKEL if k not in out]
    if missing:
        raise ValueError("BVH incompleto, mancano: " + ", ".join(missing[:6]))
    J.clear()
    for k, v in SKEL.items():
        J[k] = np.array(v, float)
    for k in out:
        J[k] = out[k]
    SKEL_PARENTS.clear()
    SKEL_PARENTS.update(parents)
    SKEL_SOURCE[0] = os.path.basename(path)


def reset_skeleton():
    J.clear()
    for k, v in SKEL.items():
        J[k] = np.array(v, float)
    SKEL_PARENTS.clear()
    SKEL_PARENTS.update(DEFAULT_PARENTS)
    SKEL_SOURCE[0] = "scheletro incorporato"


# ---------------------------------------------------------------------------------------------
# Colori
# ---------------------------------------------------------------------------------------------
def hex_rgb(s):
    s = s.strip().lstrip("#")
    if len(s) != 6:
        raise ValueError(f"colore non valido: {s}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))


def shade(c, k):
    return tuple(max(0, min(255, int(round(c[i] * k)))) for i in range(3))


def jitter(c, rng, amt=0.06):
    k = 1.0 + rng.uniform(-amt, amt)
    return shade(c, k)


# ---------------------------------------------------------------------------------------------
# PNG
# ---------------------------------------------------------------------------------------------
def png_bytes(rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def write_png(path, rgb):
    with open(path, "wb") as fh:
        fh.write(png_bytes(np.ascontiguousarray(rgb)))


# ---------------------------------------------------------------------------------------------
# Atlas texture: tinte unite 4x4 px + tessere dipinte (volto, decalcomanie, linee delle dita...)
# ---------------------------------------------------------------------------------------------
class Atlas:
    def __init__(self, size):
        self.size = size
        self.img = np.zeros((size, size, 3), np.uint8)
        self.img[:, :] = (255, 0, 255)             # magenta: un UV fuori posto si nota subito
        self.cx = self.cy = self.rowh = 0
        self.sw = {}
        self.tiles = {}

    def _alloc(self, w, h):
        if self.cx + w > self.size:
            self.cx, self.cy, self.rowh = 0, self.cy + self.rowh, 0
        if self.cy + h > self.size:
            raise OverflowError("atlas texture pieno")
        x, y = self.cx, self.cy
        self.cx += w
        self.rowh = max(self.rowh, h)
        return x, y

    def swatch(self, name, rgb):
        """UV (u, v) del centro di una tinta unita; la crea la prima volta."""
        if name not in self.sw:
            x, y = self._alloc(4, 4)
            self.img[y:y + 4, x:x + 4] = rgb
            self.sw[name] = ((x + 2) / self.size, 1.0 - (y + 2) / self.size)
        return self.sw[name]

    def tile(self, name, w, h, painter):
        """Tessera w x h dipinta da painter(arr) con bordo di 1 px replicato. Ritorna (u0, v_basso, u1, v_alto)."""
        if name not in self.tiles:
            x, y = self._alloc(w + 2, h + 2)
            inner = self.img[y + 1:y + 1 + h, x + 1:x + 1 + w]
            painter(inner)
            blk = self.img[y:y + h + 2, x:x + w + 2]
            blk[0, 1:-1] = inner[0]
            blk[-1, 1:-1] = inner[-1]
            blk[:, 0] = blk[:, 1]
            blk[:, -1] = blk[:, -2]
            s = float(self.size)
            self.tiles[name] = ((x + 1) / s, 1.0 - (y + 1 + h) / s, (x + 1 + w) / s, 1.0 - (y + 1) / s)
        return self.tiles[name]


def paint_rows(rows, pal):
    def fn(arr):
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                arr[r, c] = pal[ch]
    return fn


# ---------------------------------------------------------------------------------------------
# Mesh e primitive
# ---------------------------------------------------------------------------------------------
class Mesh:
    def __init__(self):
        self.tris = []         # (gruppo, (a, b, c), (uv, uv, uv), (na, nb, nc))
        self.prio = {}         # gruppo -> priorita' di taglio (0 = essenziale)

    def tri(self, g, pts, uvs, nrms, ref, inward=False):
        a, b, c = (np.asarray(p, float) for p in pts)
        fn = np.cross(b - a, c - a)
        ln = float(np.linalg.norm(fn))
        if ln < 1e-9:
            return
        cen = (a + b + c) / 3.0
        outward = float(np.dot(fn, cen - np.asarray(ref, float))) > 0
        swapped = outward == inward
        uvs = tuple(uvs)
        if swapped:
            b, c = c, b
            uvs = (uvs[0], uvs[2], uvs[1])
            fn = -fn
        if nrms is None:
            n = fn / ln
            nrms = (n, n, n)
        elif swapped:
            nrms = (nrms[0], nrms[2], nrms[1])
        self.tris.append((g, (a, b, c), uvs, tuple(nrms)))

    def groups(self):
        out = {}
        for t in self.tris:
            out[t[0]] = out.get(t[0], 0) + 1
        return out

    def set_prio(self, g, p):
        self.prio[g] = max(p, self.prio.get(g, 0))

    def trim_to(self, budget):
        """Toglie i gruppi opzionali (priorita' piu' alta per prima) finche' si rientra nel budget."""
        removed = []
        while len(self.tris) > budget:
            cand = [g for g, p in self.prio.items() if p > 0 and g in self.groups()]
            if not cand:
                break
            g = max(cand, key=lambda k: (self.prio[k], k))
            self.tris = [t for t in self.tris if t[0] != g]
            removed.append(g)
        return removed

    def pack(self):
        n = len(self.tris)
        P = np.zeros((n, 3, 3))
        N = np.zeros((n, 3, 3))
        UV = np.zeros((n, 3, 2))
        for i, (_, p, uv, nr) in enumerate(self.tris):
            P[i] = p
            N[i] = nr
            UV[i] = uv
        return P, N, UV


def _frames(cs, up, axis=None):
    n = len(cs)
    T, U, V = [], [], []
    if axis is not None:
        ax = np.asarray(axis, float) / np.linalg.norm(axis)
        if np.dot(cs[-1] - cs[0], ax) < 0:
            ax = -ax
    for i in range(n):
        if axis is not None:
            t = ax
        else:
            t = cs[min(i + 1, n - 1)] - cs[max(i - 1, 0)]
            ln = np.linalg.norm(t)
            t = t / ln if ln > 1e-9 else np.array([0.0, 1.0, 0.0])
        u = up - np.dot(up, t) * t
        if np.linalg.norm(u) < 1e-6:
            alt = np.array([0.0, 0.0, 1.0]) if abs(t[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
            u = alt - np.dot(alt, t) * t
        u = u / np.linalg.norm(u)
        T.append(t)
        U.append(u)
        V.append(np.cross(t, u))
    return T, U, V


def smooth_stations(stations, k):
    """Inserisce k stazioni tra ogni coppia (Catmull-Rom su centro e raggi)."""
    if k <= 0 or len(stations) < 2:
        return list(stations)
    vals = [np.array(list(c) + [ru, rv], float) for c, ru, rv in stations]
    out = []
    for i in range(len(vals) - 1):
        p0 = vals[max(i - 1, 0)]
        p1, p2 = vals[i], vals[i + 1]
        p3 = vals[min(i + 2, len(vals) - 1)]
        for j in range(k + 1):
            t = j / (k + 1)
            v = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
                       + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
            out.append(v)
    out.append(vals[-1])
    return [(tuple(v[:3]), max(float(v[3]), 1e-3), max(float(v[4]), 1e-3)) for v in out]


def lerp_station(a, b, t):
    ca, cb = np.array(a[0], float), np.array(b[0], float)
    return (tuple(ca + (cb - ca) * t), a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def station_at(stations, s):
    """Stazione interpolata alla frazione s (0..1) della lunghezza."""
    cs = [np.array(st[0], float) for st in stations]
    lens = [0.0]
    for i in range(1, len(cs)):
        lens.append(lens[-1] + float(np.linalg.norm(cs[i] - cs[i - 1])))
    tot = lens[-1] or 1.0
    d = s * tot
    for i in range(len(cs) - 1):
        if lens[i] - 1e-9 <= d <= lens[i + 1] + 1e-9:
            seg = (lens[i + 1] - lens[i]) or 1.0
            return lerp_station(stations[i], stations[i + 1], (d - lens[i]) / seg)
    return stations[-1]


def cut_stations(stations, s0, s1):
    """Sotto-catena di stazioni tra le frazioni s0 e s1 (con estremi interpolati)."""
    cs = [np.array(st[0], float) for st in stations]
    lens = [0.0]
    for i in range(1, len(cs)):
        lens.append(lens[-1] + float(np.linalg.norm(cs[i] - cs[i - 1])))
    tot = lens[-1] or 1.0
    out = [station_at(stations, s0)]
    for i in range(1, len(stations) - 1):
        if s0 + 1e-6 < lens[i] / tot < s1 - 1e-6:
            out.append(stations[i])
    out.append(station_at(stations, s1))
    return out


X3, Y3, Z3 = np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), np.array([0, 0, 1.0])


def sweep(m, g, uv, stations, up, n=8, cap0=False, cap1=False, smooth=True, inward=False, axis=None):
    """Prisma/tubo lungo una catena di stazioni (centro, ru, rv). ru e' lungo la proiezione di 'up'.
    axis: se dato, tutti gli anelli restano perpendicolari a quell'asse (es. orizzontali per la testa).
    g e uv possono essere liste (una voce per tratto tra due stazioni): un solo tubo continuo con piu' gruppi/materiali."""
    up = np.asarray(up, float)
    gl = g if isinstance(g, (list, tuple)) else None
    ul = uv if (isinstance(uv, list) and uv and isinstance(uv[0], (list, tuple))) else None
    if len(stations) < 2:
        return
    cs = [np.array(s[0], float) for s in stations]
    T, U, V = _frames(cs, up, axis)
    th0, sc = math.pi / n, 1.0 / math.cos(math.pi / n)
    rings, nrms = [], []
    for i, (c, ru, rv) in enumerate(stations):
        pts, nr = [], []
        for k in range(n):
            th = th0 + 2.0 * math.pi * k / n
            ct, st = math.cos(th), math.sin(th)
            pts.append(cs[i] + sc * ru * ct * U[i] + sc * rv * st * V[i])
            nv = (ct / max(ru, 1e-3)) * U[i] + (st / max(rv, 1e-3)) * V[i]
            nv = nv / np.linalg.norm(nv)
            nr.append(-nv if inward else nv)
        rings.append(pts)
        nrms.append(nr)
    if smooth and len(rings) >= 2:                 # normali che tengono conto anche della pendenza lungo la catena
        R = len(rings)
        for i in range(R):
            for k in range(n):
                dr = rings[i][(k + 1) % n] - rings[i][(k - 1) % n]
                dc = rings[min(i + 1, R - 1)][k] - rings[max(i - 1, 0)][k]
                nv = np.cross(dr, dc)
                ln = np.linalg.norm(nv)
                if ln < 1e-9:
                    continue
                nv = nv / ln
                if np.dot(nv, nrms[i][k] if not inward else -nrms[i][k]) < 0:
                    nv = -nv
                nrms[i][k] = -nv if inward else nv
    for i in range(len(rings) - 1):
        ref = (cs[i] + cs[i + 1]) / 2.0
        if np.linalg.norm(cs[i + 1] - cs[i]) < 1e-6:          # gradino (es. orlo della manica): anello piatto
            bigger_first = stations[i][1] + stations[i][2] > stations[i + 1][1] + stations[i + 1][2]
            ref = cs[i] - T[i] if bigger_first else cs[i] + T[i]
        g_i = gl[i] if gl else g
        uv_i = ul[i] if ul else uv
        for k in range(n):
            k2 = (k + 1) % n
            a, b, c, d = rings[i][k], rings[i][k2], rings[i + 1][k2], rings[i + 1][k]
            flat = np.linalg.norm(cs[i + 1] - cs[i]) < 1e-6
            if smooth and not flat:
                na, nb, nc, nd = nrms[i][k], nrms[i][k2], nrms[i + 1][k2], nrms[i + 1][k]
                m.tri(g_i, (a, b, c), (uv_i, uv_i, uv_i), (na, nb, nc), ref, inward)
                m.tri(g_i, (a, c, d), (uv_i, uv_i, uv_i), (na, nc, nd), ref, inward)
            else:
                m.tri(g_i, (a, b, c), (uv_i, uv_i, uv_i), None, ref, inward)
                m.tri(g_i, (a, c, d), (uv_i, uv_i, uv_i), None, ref, inward)
    for ring, cen, ref, on, gg, uu in ((rings[0], cs[0], cs[1], cap0, gl[0] if gl else g, ul[0] if ul else uv),
                                       (rings[-1], cs[-1], cs[-2], cap1, gl[-1] if gl else g, ul[-1] if ul else uv)):
        if on:
            for k in range(n):
                m.tri(gg, (cen, ring[k], ring[(k + 1) % n]), (uu, uu, uu), None, ref, inward)


def box(m, g, uv, center, half):
    cx, cy, cz = center
    hx, hy, hz = half
    sweep(m, g, uv, [((cx, cy - hy, cz), hx, hz), ((cx, cy + hy, cz), hx, hz)], X3, 4, True, True, smooth=False)


def ellipsoid(m, g, uv, center, radii, segs=8, rings=5, smooth=True):
    c = np.array(center, float)
    rx, ry, rz = radii
    grid, nr = [], []
    for j in range(rings):
        ph = math.pi * j / (rings - 1)
        row, nrow = [], []
        for k in range(segs):
            th = 2.0 * math.pi * (k + 0.5) / segs
            d = np.array([math.sin(ph) * math.cos(th), math.cos(ph), math.sin(ph) * math.sin(th)])
            row.append(c + d * np.array([rx, ry, rz]))
            nv = np.array([d[0] / rx, d[1] / ry, d[2] / rz])
            nrow.append(nv / np.linalg.norm(nv))
        grid.append(row)
        nr.append(nrow)
    for j in range(rings - 1):
        for k in range(segs):
            k2 = (k + 1) % segs
            a, b, cc, d = grid[j][k], grid[j][k2], grid[j + 1][k2], grid[j + 1][k]
            if smooth:
                m.tri(g, (a, b, cc), (uv,) * 3, (nr[j][k], nr[j][k2], nr[j + 1][k2]), c)
                m.tri(g, (a, cc, d), (uv,) * 3, (nr[j][k], nr[j + 1][k2], nr[j + 1][k]), c)
            else:
                m.tri(g, (a, b, cc), (uv,) * 3, None, c)
                m.tri(g, (a, cc, d), (uv,) * 3, None, c)


def decal_curved(m, g, rect, xs, y0, y1, zfunc, front=True, off=0.12):
    """Decalcomania verticale che segue la superficie: una colonna per ogni x in xs (crescenti)."""
    u0, vb, u1, vt = rect
    sgn = 1.0 if front else -1.0
    span = (xs[-1] - xs[0]) or 1.0
    ref_n = np.array([0, 0, sgn])
    for i in range(len(xs) - 1):
        xa, xb = xs[i], xs[i + 1]
        za, zb = zfunc(xa) + sgn * off, zfunc(xb) + sgn * off
        ua = u0 + (u1 - u0) * ((xa - xs[0]) / span)
        ub = u0 + (u1 - u0) * ((xb - xs[0]) / span)
        if not front:                      # visto da dietro l'asse x e' invertito
            ua, ub = u1 - (ua - u0), u1 - (ub - u0)
        p00, p10 = (xa, y0, za), (xb, y0, zb)
        p11, p01 = (xb, y1, zb), (xa, y1, za)
        cen = np.mean([p00, p10, p11, p01], axis=0)
        ref = cen - ref_n
        m.tri(g, (p00, p10, p11), ((ua, vb), (ub, vb), (ub, vt)), None, ref)
        m.tri(g, (p00, p11, p01), ((ua, vb), (ub, vt), (ua, vt)), None, ref)


# ---------------------------------------------------------------------------------------------
# Pose di anteprima (non cambiano l'OBJ): mandibola aperta, occhi chiusi, sopracciglia
# ---------------------------------------------------------------------------------------------
def _rot_matrix(axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def posed(m, rules):
    """rules: lista di (prefisso_gruppo, pivot, asse, gradi, traslazione). Ritorna una copia della mesh."""
    out = Mesh()
    out.prio = dict(m.prio)
    for g, pts, uvs, nr in m.tris:
        for pref, pivot, axis, deg, tr in rules:
            if g.startswith(pref):
                R = _rot_matrix(axis, deg)
                pv = np.asarray(pivot, float)
                pts = tuple(R @ (p - pv) + pv + np.asarray(tr, float) for p in pts)
                nr = tuple(R @ n for n in nr)
                break
        out.tris.append((g, pts, uvs, nr))
    return out


# ---------------------------------------------------------------------------------------------
# OBJ / MTL
# ---------------------------------------------------------------------------------------------
BONE_NOTES = {
    "Node23": "sopracciglio SX", "Node25": "sopracciglio DX", "Node24": "palpebra SX", "Node26": "palpebra DX",
    "Node27": "mandibola", "Eye_L": "occhio SX (centro = pivot)", "Eye_R": "occhio DX (centro = pivot)",
}


def write_obj(m, outdir, name, atlas, pivots=None, info_lines=None):
    os.makedirs(outdir, exist_ok=True)
    vi, ti, ni = {}, {}, {}
    vs, ts, ns = [], [], []

    def get(table, store, key, val):
        if key not in table:
            table[key] = len(store) + 1
            store.append(val)
        return table[key]

    groups, order = {}, []
    for g, pts, uvs, nr in m.tris:
        face = []
        for p, uv, n in zip(pts, uvs, nr):
            a = get(vi, vs, tuple(np.round(p, 4)), p)
            b = get(ti, ts, (round(uv[0], 5), round(uv[1], 5)), uv)
            c = get(ni, ns, tuple(np.round(n, 4)), n)
            face.append((a, b, c))
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append(face)
    L = [f"# {name} - {len(m.tris)} triangoli", f"mtllib {name}.mtl", f"o {name}"]
    L += [f"v {p[0]:.4f} {p[1]:.4f} {p[2]:.4f}" for p in vs]
    L += [f"vt {t[0]:.5f} {t[1]:.5f}" for t in ts]
    L += [f"vn {n[0]:.4f} {n[1]:.4f} {n[2]:.4f}" for n in ns]
    L += ["usemtl char_mat", "s 1"]
    for g in order:
        L.append(f"g {g}")
        for f in groups[g]:
            L.append("f " + " ".join(f"{a}/{b}/{c}" for a, b, c in f))
    with open(os.path.join(outdir, name + ".obj"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    with open(os.path.join(outdir, name + ".mtl"), "w") as fh:
        fh.write(f"newmtl char_mat\nKa 1 1 1\nKd 1 1 1\nKs 0 0 0\nd 1\nillum 1\nmap_Kd {name}_tex.png\n")
    write_png(os.path.join(outdir, name + "_tex.png"), atlas.img)
    G = [f"Gruppi di {name}.obj ({len(m.tris)} triangoli)", ""]
    if info_lines:
        G += info_lines + [""]
    G.append("gruppo                         triangoli  osso suggerito / pivot")
    for g in order:
        if g.startswith("Eye_"):
            bone, note = "Node22", BONE_NOTES.get(g, "")
        elif g.startswith("Node"):
            bone = g.split("_")[0]
            note = BONE_NOTES.get(bone, "")
        else:
            bone, note = "", ""
        piv = (pivots or {}).get(g)
        if piv is None and bone in J and g.startswith("Node"):
            piv = J[bone]
        pivs = "pivot (%.2f, %.2f, %.2f)" % tuple(piv) if piv is not None else ""
        G.append(f"{g:<30} {len(groups[g]):>6}   {bone:<7} {note} {pivs}".rstrip())
    with open(os.path.join(outdir, name + "_gruppi.txt"), "w") as fh:
        fh.write("\n".join(G) + "\n")
    return order


# ---------------------------------------------------------------------------------------------
# Anteprima renderizzata (z-buffer, texture "nearest", normali interpolate)
# ---------------------------------------------------------------------------------------------
def render_view(m, tex, yaw, scale, W, H, cx=0.0, cy=88.0, packed=None):
    P, N, UV = packed if packed is not None else m.pack()
    th = math.radians(yaw)
    c, s = math.cos(th), math.sin(th)
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    Pr = P @ R.T
    Nr = N @ R.T
    img = np.zeros((H, W, 3), np.float32)
    top, bot = np.array([96, 108, 126], np.float32), np.array([150, 158, 170], np.float32)
    img[:] = top + (bot - top) * (np.arange(H, dtype=np.float32) / max(H - 1, 1))[:, None, None]
    zbuf = np.full((H, W), -1e9, np.float32)
    L1 = np.array([0.35, 0.55, 0.75]); L1 /= np.linalg.norm(L1)
    L2 = np.array([-0.6, 0.2, 0.5]); L2 /= np.linalg.norm(L2)
    TS = tex.shape[0]
    SX = W / 2.0 + (Pr[:, :, 0] - cx) * scale
    SY = H / 2.0 - (Pr[:, :, 1] - cy) * scale
    for i in range(len(Pr)):
        sx, sy = SX[i], SY[i]
        x0, x1 = int(max(0, math.floor(sx.min()))), int(min(W - 1, math.ceil(sx.max())))
        y0, y1 = int(max(0, math.floor(sy.min()))), int(min(H - 1, math.ceil(sy.max())))
        if x1 < x0 or y1 < y0:
            continue
        den = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
        if abs(den) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((sy[1] - sy[2]) * (gx - sx[2]) + (sx[2] - sx[1]) * (gy - sy[2])) / den
        w1 = ((sy[2] - sy[0]) * (gx - sx[2]) + (sx[0] - sx[2]) * (gy - sy[2])) / den
        w2 = 1 - w0 - w1
        ok = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not ok.any():
            continue
        z = w0 * Pr[i, 0, 2] + w1 * Pr[i, 1, 2] + w2 * Pr[i, 2, 2]
        sub = zbuf[y0:y1 + 1, x0:x1 + 1]
        win = ok & (z > sub)
        if not win.any():
            continue
        u = w0 * UV[i, 0, 0] + w1 * UV[i, 1, 0] + w2 * UV[i, 2, 0]
        v = w0 * UV[i, 0, 1] + w1 * UV[i, 1, 1] + w2 * UV[i, 2, 1]
        tx = np.clip((u * TS).astype(int), 0, TS - 1)
        ty = np.clip(((1 - v) * TS).astype(int), 0, TS - 1)
        nx = w0 * Nr[i, 0, 0] + w1 * Nr[i, 1, 0] + w2 * Nr[i, 2, 0]
        ny = w0 * Nr[i, 0, 1] + w1 * Nr[i, 1, 1] + w2 * Nr[i, 2, 1]
        nz = w0 * Nr[i, 0, 2] + w1 * Nr[i, 1, 2] + w2 * Nr[i, 2, 2]
        ln = np.sqrt(nx * nx + ny * ny + nz * nz) + 1e-9
        d1 = np.maximum(0.0, (nx * L1[0] + ny * L1[1] + nz * L1[2]) / ln)
        d2 = np.maximum(0.0, (nx * L2[0] + ny * L2[1] + nz * L2[2]) / ln)
        k = (0.40 + 0.55 * d1 + 0.18 * d2)[..., None]
        col = tex[ty, tx].astype(np.float32) * k
        region = img[y0:y1 + 1, x0:x1 + 1]
        region[win] = col[win]
        sub[win] = z[win]
    return np.clip(img, 0, 255).astype(np.uint8)


def render_sheet(m, tex, views=(0, 40, 90, 180), scale=2.45, W=430, H=500):
    packed = m.pack()
    tiles = [render_view(m, tex, y, scale, W, H, 0.0, 88.0, packed) for y in views]
    return np.concatenate([np.concatenate(tiles[:2], axis=1), np.concatenate(tiles[2:4], axis=1)], axis=0)


def render_head(m, tex, yaws=(0, 35), scale=15.0, W=330, H=330, cy=161.5):
    packed = m.pack()
    return np.concatenate([render_view(m, tex, y, scale, W, H, 0.0, cy, packed) for y in yaws], axis=1)


# ---------------------------------------------------------------------------------------------
# Tabelle di colori
# ---------------------------------------------------------------------------------------------
HAIR_COL = {"nero": (24, 20, 18), "castano": (78, 50, 32), "biondo": (214, 180, 112),
            "rosso": (150, 62, 34), "grigio": (140, 140, 146), "bianco": (228, 228, 226)}
EYE_COL = {"marrone": (96, 60, 36), "nocciola": (134, 98, 52), "azzurro": (92, 148, 206),
           "verde": (76, 134, 88), "grigio": (132, 142, 152)}
SKIN_BIANCO = [(246, 222, 200), (240, 208, 180), (232, 196, 164), (222, 182, 148), (210, 168, 132)]
SKIN_NERO = [(150, 104, 74), (128, 88, 62), (104, 70, 48), (84, 56, 40), (66, 44, 32)]
SUBS = ("infermiere", "dottore", "cuoco", "meccanico")
HAIRSTYLES = ("random", "corti", "lunghi", "codino")
_HS_MAP = {"corti": "short", "lunghi": "long", "codino": "tail"}
TYPES = ("poliziotto", "civile", "lavoratore")
BOTTOM_STYLES = ("random", "pantaloni", "pantaloncini", "gonna")
TOP_STYLES = ("random", "maglietta", "maglia", "canotta", "giacca")
FOOT_STYLES = ("random", "scarpe", "stivali")
CIVIL_TOPS = [(176, 62, 62), (62, 110, 170), (70, 130, 82), (200, 168, 62), (122, 84, 150), (96, 96, 102),
              (214, 210, 198), (190, 110, 60)]
CIVIL_BOTTOMS = [(58, 78, 120), (150, 132, 96), (34, 34, 40), (96, 70, 50), (70, 80, 70)]
CIVIL_SHOES = [(236, 236, 236), (88, 60, 38), (24, 24, 28), (150, 40, 40)]


class Spec:
    def __init__(self, kind="umano", sex="maschio", type="poliziotto", sub="random", skin="random",
                 hair="random", eyes="random", quality="medium", tris=None, seed=0, hairstyle="random",
                 bottom_style="random", top_style="random", footwear="random"):
        self.kind, self.sex, self.type, self.sub = kind, sex, type, sub
        self.skin, self.hair, self.eyes, self.quality = skin, hair, eyes, quality
        self.tris, self.seed, self.hairstyle = tris, int(seed), hairstyle
        self.bottom_style, self.top_style, self.footwear = bottom_style, top_style, footwear

    def copy(self, **kw):
        s = Spec(self.kind, self.sex, self.type, self.sub, self.skin, self.hair, self.eyes, self.quality, self.tris, self.seed,
                 self.hairstyle, self.bottom_style, self.top_style, self.footwear)
        for k, v in kw.items():
            setattr(s, k, v)
        return s


def _color_choice(value, table, rng, choices):
    v = (value or "random").strip().lower()
    if v == "random":
        name = rng.choice(choices)
        return name, table[name]
    if v in table:
        return v, table[v]
    return "custom", hex_rgb(v)


def make_plan(spec):
    """Tutte le scelte casuali, fatte una sola volta (restano uguali a ogni livello di dettaglio)."""
    rng = random.Random(spec.seed * 7919 + 13)
    kind = "zombie" if str(spec.kind).lower().startswith("z") else "umano"
    human = kind == "umano"
    sex = "f" if str(spec.sex).lower().startswith("f") else "m"
    typ = str(spec.type).lower()
    if typ not in TYPES:
        raise ValueError(f"tipo non valido: {spec.type} (usa {', '.join(TYPES)})")
    sub = None
    if typ == "lavoratore":
        sub = str(spec.sub or "random").lower()
        if sub in ("random", "", "none"):
            sub = rng.choice(SUBS)
        if sub not in SUBS:
            raise ValueError(f"sotto-tipo non valido: {spec.sub} (usa {', '.join(SUBS)})")
    skin_name = str(spec.skin or "random").lower()
    if skin_name == "random":
        skin_name = rng.choice(["bianco", "nero"])
    if skin_name not in ("bianco", "nero"):
        raise ValueError("colore pelle: random, bianco o nero")
    tone = rng.choice(SKIN_BIANCO if skin_name == "bianco" else SKIN_NERO)
    hair_choices = (["nero"] * 6 + ["castano"] * 2 + ["grigio"]) if skin_name == "nero" else \
                   (["nero"] * 3 + ["castano"] * 4 + ["biondo"] * 2 + ["rosso", "grigio"])
    hair_name, hair = _color_choice(spec.hair, HAIR_COL, rng, hair_choices)
    eye_choices = (["marrone"] * 6 + ["nocciola"]) if skin_name == "nero" else \
                  (["marrone"] * 3 + ["nocciola", "azzurro", "azzurro", "verde", "grigio"])
    eye_name, eye = _color_choice(spec.eyes, EYE_COL, rng, eye_choices)

    # ----- scelte guardaroba civile (validate sempre, usate solo per typ == "civile")
    bottom_req = str(getattr(spec, "bottom_style", "random") or "random").lower()
    if bottom_req not in BOTTOM_STYLES:
        raise ValueError("vestiti (gambe): " + ", ".join(BOTTOM_STYLES))
    top_req = str(getattr(spec, "top_style", "random") or "random").lower()
    if top_req not in TOP_STYLES:
        raise ValueError("vestiti (busto): " + ", ".join(TOP_STYLES))
    foot_req = str(getattr(spec, "footwear", "random") or "random").lower()
    if foot_req not in FOOT_STYLES:
        raise ValueError("calzature: " + ", ".join(FOOT_STYLES))

    # ----- vestiti
    o = {"extras": [], "hat": None, "coat": False, "skirt_hem": None, "shorts_end": None, "boots": False, "sleeve": 0.93}
    o["accent"] = (18, 18, 22)
    o["collar"] = (120, 150, 190)
    if typ == "poliziotto":
        o.update(top=(34, 48, 86), bottom=(30, 38, 66), shoe=(18, 18, 22), hat="police", collar=(34, 48, 86),
                 extras=["belt", "holster", "radio", "cuffs", "tie", "badge", "nametag", "epaulets", "collar"])
    elif typ == "civile":
        top_col = rng.choice(CIVIL_TOPS)
        bottom_col = rng.choice(CIVIL_BOTTOMS)
        bottom_candidates = ["pantaloni", "pantaloncini"] + (["gonna"] if sex == "f" else [])
        bottom_weights = [0.55, 0.20, 0.25] if sex == "f" else [0.75, 0.25]
        bottom_sel = bottom_req if bottom_req != "random" else rng.choices(bottom_candidates, weights=bottom_weights)[0]
        top_sel = top_req if top_req != "random" else rng.choices(
            ["maglietta", "maglia", "canotta", "giacca"], weights=[0.40, 0.33, 0.15, 0.12])[0]
        foot_sel = foot_req if foot_req != "random" else rng.choices(["scarpe", "stivali"], weights=[0.72, 0.28])[0]
        skirt = bottom_sel == "gonna"
        shorts = bottom_sel == "pantaloncini"
        jacket = top_sel == "giacca"
        sleeve = {"maglietta": 0.36, "maglia": 0.93, "canotta": 0.05, "giacca": 0.93}[top_sel]
        o.update(top=top_col, bottom=rng.choice(CIVIL_TOPS + CIVIL_BOTTOMS) if skirt else bottom_col,
                 shoe=rng.choice(CIVIL_SHOES), sleeve=sleeve, collar=mix(top_col, (240, 240, 240), 0.35))
        if skirt:
            o["skirt_hem"] = rng.choice([72.0, 64.0])
        if shorts:
            o["shorts_end"] = 0.40
        o["boots"] = foot_sel == "stivali"
        ex = ["collar", "cuffs_pants", "laces"]
        if not skirt and not shorts and rng.random() < 0.7:
            ex.append("belt")
        if rng.random() < 0.4:
            ex.append("pocket")
        if jacket:
            ex += ["jacket", "vneck"]
            o["coat"] = True
        o["extras"] = ex
        o["collar"] = shade(top_col, 0.82)
        o["belt_col"] = (92, 58, 36)
        o["buckle"] = (176, 178, 184)
        o["sole"] = (232, 232, 228)
    elif sub == "infermiere":
        scrub = rng.choice([(80, 170, 176), (96, 164, 214), (110, 180, 140)])
        o.update(top=scrub, bottom=scrub, shoe=(236, 236, 236), sleeve=0.36, extras=["pocket", "cross", "vneck"],
                 hat="nurse" if sex == "f" else None, collar=mix(scrub, (255, 255, 255), 0.4))
    elif sub == "dottore":
        o.update(top=(236, 236, 232), bottom=(58, 60, 70), shoe=(20, 20, 24), coat=True, shirt=(130, 168, 204),
                 extras=["coat_tail", "stetho", "nametag", "vneck", "pocket"], collar=(236, 236, 232), accent=(40, 52, 96))
    elif sub == "cuoco":
        o.update(top=(240, 240, 238), bottom=(52, 52, 60), shoe=(20, 20, 24), hat="toque", collar=(240, 240, 238),
                 extras=["buttons", "neckerchief"], red=(176, 44, 44))
    else:  # meccanico
        cov = rng.choice([(48, 84, 150), (70, 96, 70), (150, 70, 40)])
        o.update(top=cov, bottom=cov, shoe=(88, 60, 38), hat="mech", accent=rng.choice([(170, 50, 40), (30, 40, 80)]),
                 extras=["grease", "belt"], collar=mix(cov, (0, 0, 0), 0.15))
    o.setdefault("shirt", (130, 168, 204))
    o.setdefault("belt_col", (18, 18, 22))
    o.setdefault("buckle", (214, 174, 58))
    o.setdefault("sole", (42, 42, 48))
    o.setdefault("red", (176, 44, 44))

    # ----- capelli
    hs_req = str(getattr(spec, "hairstyle", "random") or "random").lower()
    if hs_req not in HAIRSTYLES:
        raise ValueError("capelli (taglio): " + ", ".join(HAIRSTYLES))
    hs_rand = rng.choice(["short", "short", "short", "tail"]) if sex == "m" else rng.choice(["long", "long", "tail", "short"])
    hair_style = _HS_MAP.get(hs_req, hs_rand)

    cols = {"skin": tone, "lip": mix(tone, (170, 70, 70), 0.32), "cheekin": mix(shade(tone, 0.6), (70, 22, 26), 0.35), "mouthin": (60, 18, 22), "teeth": (232, 228, 214),
            "eyewhite": (240, 240, 234), "iris": eye, "pupil": (10, 10, 12), "hair": hair, "brow": shade(hair, 0.85),
            "black": (18, 18, 22), "metal": (84, 86, 96), "gold": (214, 174, 58), "white": (238, 238, 234),
            "sole": o["sole"], "belt": o["belt_col"], "buckle": o["buckle"], "lace": (236, 236, 232),
            "hem": shade(o["top"], 0.82), "cuff": shade(o["bottom"], 0.8), "tie_band": (30, 30, 34), "top": o["top"], "bottom": o["bottom"], "shoe": o["shoe"], "accent": o["accent"],
            "collar": o["collar"], "shirt": o["shirt"], "red": o["red"], "grime": (60, 50, 44)}
    plan = {"kind": kind, "human": human, "sex": sex, "type": typ, "sub": sub, "skin_name": skin_name,
            "hair_name": hair_name, "eye_name": eye_name, "outfit": o, "hair_style": hair_style,
            "seed": spec.seed, "cols": cols}

    if human:
        q = {"low": 3000, "medium": 6000, "high": 9000}.get(str(spec.quality).lower())
        if q is None:
            raise ValueError("quality: low, medium o high")
        plan["budget"] = int(max(1500, min(9000, spec.tris))) if spec.tris else q
    else:
        plan["budget"] = int(max(150, min(500, spec.tris))) if spec.tris else 500
        # tinta zombie: pelle livida, occhi lattiginosi, vestiti sporchi
        z = shade(mix(tone, (112, 132, 104), 0.5), 0.9)
        cols["skin"] = z
        cols["lip"] = mix(z, (90, 40, 40), 0.5)
        cols["hair"] = shade(mix(hair, (70, 66, 60), 0.4), 0.8)
        cols["brow"] = cols["hair"]
        cols["iris"] = mix(eye, (214, 214, 170), 0.55)
        dirty = lambda c: shade(mix(c, (86, 74, 62), 0.35), 0.82)
        for k in ("top", "bottom", "shoe", "collar", "shirt", "hem", "cuff", "belt"):
            cols[k] = dirty(cols[k])
        if hs_req == "random":
            plan["hair_style"] = rng.choice(["none", "short", "short", "long"]) if sex == "m" else rng.choice(["short", "long", "long", "tail"])
        o["sleeve_end"] = {"L": o["sleeve"] if rng.random() < 0.6 else rng.uniform(0.3, 0.7),
                           "R": o["sleeve"] if rng.random() < 0.6 else rng.uniform(0.3, 0.7)}
        plan["shoe_missing"] = rng.choice([None, None, "L", "R"])
        plan["face"] = {"mouth": rng.randint(0, 2), "wound": rng.randint(0, 2), "drip": rng.random() < 0.6}
        dec = []
        for i in range(rng.randint(3, 5)):
            dec.append({"k": rng.choice(["blood", "blood", "tear", "bite"]), "x": rng.uniform(-6.5, 6.5),
                        "y": rng.uniform(116.0, 140.0), "front": rng.random() < 0.7, "w": rng.uniform(3.6, 5.6)})
        plan["decals"] = dec
    if human:
        o["sleeve_end"] = {"L": o["sleeve"], "R": o["sleeve"]}
    return plan


# ---------------------------------------------------------------------------------------------
# Livelli di dettaglio
# ---------------------------------------------------------------------------------------------
def lod_for(human, level):
    if human:
        i = max(0, min(11, level))
        pick = lambda t: t[i]
        return {"nl": pick([8, 8, 10, 10, 12, 12, 14, 16, 18, 20, 22, 24]),
                "ns": pick([0, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 5]),
                "hn": pick([12, 12, 12, 16, 16, 16, 16, 20, 20, 20, 24, 24]),
                "hs": pick([1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3]),
                "eye": pick([8, 8, 10, 10, 12, 12, 14, 14, 16, 16, 18, 20]),
                "lip": pick([5, 5, 5, 6, 6, 7, 7, 8, 8, 9, 10, 10]),
                "level": i}
    i = max(0, min(3, level))
    return {"nl": [4, 5, 6, 8][i], "ns": 0, "hn": 6, "hs": 0, "eye": 0, "lip": 0, "level": i}


# ---------------------------------------------------------------------------------------------
# Tabelle anatomiche: (y, semi-larghezza, semi-profondita') - m/f
# ---------------------------------------------------------------------------------------------
TORSO_ST = {
    "m": [(111, 9.4, 5.4), (118, 9.8, 5.7), (127, 11.4, 6.4), (135, 12.2, 6.7), (141, 12.2, 6.2), (144.4, 10.4, 5.2), (147.0, 5.0, 4.2)],
    "f": [(111, 8.0, 5.0), (118, 8.3, 5.3), (127, 10.8, 7.7), (135, 11.8, 8.3), (141, 11.2, 7.0), (144.4, 9.6, 5.6), (147.0, 4.6, 4.2)],
}
PELVIS_ST = {
    "m": [(112.5, 10.2, 5.9), (103.0, 11.0, 6.7), (95.5, 10.8, 6.5)],
    "f": [(112.5, 8.8, 5.3), (103.0, 11.6, 7.4), (95.5, 11.2, 7.0)],
}
# testa: (y, semi-larghezza, z_dietro, z_davanti)
_HM = [(150.9, 1.9, 1.6, 6.3), (152.6, 4.2, -3.2, 7.3), (155.0, 6.1, -7.4, 7.9), (156.4, 6.7, -8.6, 8.05),
       (157.6, 7.2, -9.5, 8.1), (161.0, 8.0, -10.5, 8.0), (165.0, 8.4, -10.8, 7.5), (169.0, 8.0, -10.3, 6.2),
       (172.3, 5.9, -8.0, 3.6), (174.3, 2.6, -4.8, 0.8)]
# testa in stile anime: cranio tondo e ampio, guance che scendono a un mento piccolo
HEAD_ST = {"m": _HM, "f": [(y, hx * 0.95, zb * 0.97, zf * 0.985) for y, hx, zb, zf in _HM]}
_ZM = [(151.2, 2.4, 0.8, 6.2), (155.0, 6.2, -7.6, 7.8), (161.0, 8.0, -10.4, 7.8), (168.0, 7.8, -10.0, 6.4), (173.6, 3.4, -5.6, 1.6)]
HEAD_ZOMBIE = {"m": _ZM, "f": [(y, hx * 0.95, zb * 0.97, zf * 0.985) for y, hx, zb, zf in _ZM]}


def interp_rows(rows, y):
    rows = sorted(rows)
    if y <= rows[0][0]:
        return rows[0][1:]
    if y >= rows[-1][0]:
        return rows[-1][1:]
    for a, b in zip(rows, rows[1:]):
        if a[0] <= y <= b[0]:
            t = (y - a[0]) / (b[0] - a[0])
            return tuple(a[i] * (1 - t) + b[i] * t for i in range(1, len(a)))
    return rows[-1][1:]


def head_stations(table):
    return [((0.0, y, (zb + zf) / 2.0), hx, (zf - zb) / 2.0) for y, hx, zb, zf in table]


def head_dims_fn(table, k=6):
    dense = smooth_stations(head_stations(table), k)
    rows = [(c[1], ru, c[2], rv) for c, ru, rv in dense]       # y, hx, zc, rv
    return lambda y: interp_rows(rows, y)


# ---------------------------------------------------------------------------------------------
# Tessere dipinte
# ---------------------------------------------------------------------------------------------
BADGE_ROWS = [".dddddd.", "dggggggd", "dggddggd", "dgdggdgd", "dggddggd", ".dggggd.", "..dggd..", "...dd..."]
CROSS_ROWS = ["........", "...rr...", "...rr...", ".rrrrrr.", ".rrrrrr.", "...rr...", "...rr...", "........"]
VNECK_ROWS = ["ssssssss", ".ssssss.", ".ssssss.", "..ssss..", "..ssss..", "...ss...", "...ss...", "........"]
POCKET_ROWS = ["dddddddd", "d......d", "d......d", "d......d", "d......d", "d......d", "dddddddd", "........"]
NAME_ROWS = ["dddddddddddd", "dggggggggggd", "dggggggggggd", "dddddddddddd"]
STAIN_ROWS = ["..dd....", ".dddd.d.", "dddddddd", ".dddddd.", "..dddd..", ".ddd.dd.", "..d..d..", "........"]


def pal_bg(bg, **kw):
    d = {".": bg}
    d.update(kw)
    return d


def paint_blob(kind, bg, seed, size=8):
    rng = random.Random(seed)

    def fn(arr):
        arr[:] = bg
        if kind == "blood":
            for _ in range(18):
                x, y = rng.randint(0, size - 1), rng.randint(0, size - 1)
                c = rng.choice([(96, 16, 18), (132, 22, 24), (70, 12, 14)])
                arr[y, x] = c
                if x + 1 < size and rng.random() < 0.7:
                    arr[y, x + 1] = c
                if y + 1 < size and rng.random() < 0.6:
                    arr[y + 1, x] = c
        elif kind == "tear":
            skin = BLOB_SKIN[0]
            for y in range(size):
                for x in range(size):
                    if (x - 3.5) ** 2 / 9.0 + (y - 3.5) ** 2 / 10.0 < 1.0 + rng.uniform(-0.45, 0.35):
                        arr[y, x] = skin
                        if rng.random() < 0.18:
                            arr[y, x] = shade(skin, 0.6)
            for x in range(size):
                if rng.random() < 0.5:
                    arr[rng.randint(0, size - 1), x] = (96, 16, 18)
        elif kind == "bite":
            skin = BLOB_SKIN[0]
            for y in range(size):
                for x in range(size):
                    if (x - 3.5) ** 2 + (y - 3.5) ** 2 < 8.5 + rng.uniform(-2, 1.5):
                        arr[y, x] = (118, 20, 22)
            arr[3:5, 3:5] = (60, 8, 10)
            for k in range(4):
                arr[rng.randint(1, 6), rng.randint(1, 6)] = shade(skin, 0.7)
    return fn


BLOB_SKIN = [(150, 160, 130)]


def paint_zombie_face(arr, plan):
    cols = plan["cols"]
    f = plan["face"]
    skin, white = cols["skin"], (212, 212, 178)
    arr[:] = skin
    arr[13:, :] = shade(skin, 0.92)
    socket = shade(skin, 0.42)
    for x0 in (2, 9):
        arr[5:9, x0:x0 + 5] = socket
        arr[6:8, x0 + 1:x0 + 4] = white
        arr[6, x0 + 2] = cols["iris"]
    arr[3, 2:6] = cols["brow"]
    arr[3, 10:14] = cols["brow"]
    arr[9:11, 7:9] = shade(skin, 0.78)
    my = 12
    if f["mouth"] == 0:
        arr[my:my + 3, 4:12] = (50, 14, 16)
        arr[my, 4:12:2] = (222, 216, 190)
        arr[my + 2, 5:11:2] = (222, 216, 190)
    elif f["mouth"] == 1:
        arr[my:my + 4, 5:11] = (50, 14, 16)
        arr[my, 5:11:2] = (222, 216, 190)
    else:
        arr[my:my + 2, 3:13] = (50, 14, 16)
        arr[my, 3:13:3] = (222, 216, 190)
    if f["drip"]:
        arr[my + 3:16, 6] = (112, 18, 20)
        arr[my + 4:16, 9] = (96, 14, 16)
    if f["wound"] == 1:
        arr[9:12, 12:15] = (110, 20, 24)
        arr[10, 13] = (60, 8, 10)
    elif f["wound"] == 2:
        arr[2:5, 11:14] = (118, 22, 24)


def paint_fingers(skin):
    def fn(arr):                                    # 16 (lunghezza) x 8 (larghezza)
        arr[:] = skin
        dark = shade(skin, 0.62)
        for r in (2, 4, 6):
            arr[r, 2:] = dark
        arr[:, 0:1] = shade(skin, 0.85)
    return fn


# ----- occhi in stile anime (tessere dipinte; l'occhio SX e' dipinto, il DX usa la tessera specchiata)
def paint_sclera(cols):
    def fn(arr):                                    # 24 x 16: bianco a mandorla su pelle, ombra della palpebra
        skin, white = cols["skin"], cols["eyewhite"]
        arr[:] = skin
        h, w = arr.shape[:2]
        for r in range(h):
            for c in range(w):
                u = (c + 0.5) / w * 2 - 1
                v = (r + 0.5) / h * 2 - 1          # -1 in alto
                top = -0.80 + 0.31 * u * u
                bot = 0.80 - 0.55 * u * u
                if top <= v <= bot and abs(u) < 0.97:
                    arr[r, c] = white
                    if v < top + 0.32:
                        arr[r, c] = shade(white, 0.80)
        lash = shade(cols["brow"], 0.55)
        for c in range(w // 2, w):                  # rima inferiore (lato esterno)
            u = (c + 0.5) / w * 2 - 1
            r = int(min(h - 1, ((0.80 - 0.55 * u * u) + 1) / 2 * h))
            arr[r, c] = mix(lash, skin, 0.35)
        arr[h // 2 - 1:h // 2 + 2, 0] = mix(skin, (200, 110, 110), 0.5)
    return fn


def paint_iris(cols):
    def fn(arr):                                    # 12 x 14: iride sfumata, pupilla, riflessi
        h, w = arr.shape[:2]
        iris, white = cols["iris"], cols["eyewhite"]
        arr[:] = white
        for r in range(h):
            for c in range(w):
                u = (c + 0.5) / w * 2 - 1
                v = (r + 0.5) / h * 2 - 1
                d = u * u + v * v
                if d <= 1.0:
                    k = 0.42 + 0.95 * (v + 1) / 2   # scura in alto, chiara in basso
                    col = shade(iris, min(1.35, k))
                    if d > 0.78:
                        col = shade(iris, 0.38)     # contorno
                    if (u / 0.36) ** 2 + (v / 0.5) ** 2 <= 1.0:
                        col = (14, 12, 16)
                    arr[r, c] = col
        arr[2:4, 2:5] = (255, 255, 255)
        arr[h - 4, w - 4] = (240, 240, 240)
    return fn


def paint_lid(cols):
    def fn(arr):                                    # 24 x 24: pelle con piega; in basso le ciglia (piu' spesse all'esterno)
        h, w = arr.shape[:2]
        skin = cols["skin"]
        arr[:] = skin
        lash = shade(cols["brow"], 0.3)
        for c in range(w):
            u = (c + 0.5) / w
            cr = int(h * 0.66 + 4.0 * (u - 0.5) ** 2 * 4)
            if 0.18 < u < 0.9:
                arr[cr, c] = shade(skin, 0.86)
            thick = 3 + int(3.0 * max(0.0, u - 0.4) / 0.6)
            arr[h - thick:h, c] = lash
            if u > 0.88:
                arr[h - thick - 2:h - 1, c] = lash
        arr[h - 3:h, 0:2] = mix(lash, skin, 0.4)
    return fn


def paint_zombie_face_anime(arr, plan):
    """32 x 32 (x: -6.4..6.4, y: 152.2..168 dall'alto in basso). Occhi grandi lattiginosi, occhiaie."""
    cols = plan["cols"]
    f = plan["face"]
    skin = cols["skin"]
    h, w = arr.shape[:2]
    arr[:] = skin
    arr[28:, :] = shade(skin, 0.9)
    milky = mix(cols["iris"], (226, 226, 200), 0.5)
    socket = shade(skin, 0.55)
    lash = shade(cols["brow"], 0.45)
    for cx, flip in ((8, -1), (24, 1)):
        for r in range(9, 19):
            for c in range(cx - 6, cx + 6):
                u, v = (c + 0.5 - cx) / 5.6, (r + 0.5 - 13.5) / 4.6
                if u * u + v * v <= 1.25:
                    arr[r, c] = socket
                if u * u * 0.9 + v * v <= 0.78:
                    arr[r, c] = (214, 210, 186)
                if (u - 0.05 * flip) ** 2 * 1.8 + (v - 0.05) ** 2 * 1.3 <= 0.36:
                    arr[r, c] = milky
        arr[9:11, cx - 5:cx + 5] = lash
        arr[11, cx + 3 * flip] = lash
        arr[13, cx - 1:cx + 1] = shade(milky, 0.75)
        arr[19:21, cx - 4:cx + 4] = shade(skin, 0.62)        # occhiaie
        arr[6, cx - 4:cx + 4] = cols["brow"]
        arr[5, cx - 2 + 2 * flip:cx + 2 + 2 * flip] = cols["brow"]
    arr[18:20, 15:17] = shade(skin, 0.72)
    my = 23
    if f["mouth"] == 0:
        arr[my:my + 3, 11:21] = (52, 14, 16)
        arr[my, 11:21:2] = (222, 216, 190)
        arr[my + 2, 12:20:2] = (222, 216, 190)
    elif f["mouth"] == 1:
        arr[my:my + 4, 12:20] = (52, 14, 16)
        arr[my, 12:20:2] = (222, 216, 190)
    else:
        arr[my:my + 2, 10:22] = (52, 14, 16)
        arr[my, 10:22:3] = (222, 216, 190)
    arr[my - 1, 11:21] = cols["lip"]
    if f["drip"]:
        arr[my + 3:32, 14] = (112, 18, 20)
        arr[my + 4:32, 18] = (96, 14, 16)
    if f["wound"] == 1:
        arr[16:21, 25:30] = (110, 20, 24)
        arr[18, 27] = (60, 8, 10)
    elif f["wound"] == 2:
        arr[2:7, 20:26] = (118, 22, 24)


# ---------------------------------------------------------------------------------------------
# Costruzione del personaggio
# ---------------------------------------------------------------------------------------------
class Build:
    def __init__(self, plan, level):
        self.p = plan
        self.human = plan["human"]
        self.sex = plan["sex"]
        self.L = lod_for(self.human, level)
        self.nl, self.ns = self.L["nl"], self.L["ns"]
        self.lvl = self.L["level"]
        self.m = Mesh()
        self.A = Atlas(256 if self.human else 128)
        self.smooth = self.human
        self.o = plan["outfit"]
        self.pivots = {}
        self.tst, self.pst = TORSO_ST[self.sex], PELVIS_ST[self.sex]
        self.head_tab = HEAD_ST[self.sex] if self.human else HEAD_ZOMBIE[self.sex]
        self.hd = head_dims_fn(self.head_tab, self.L["hs"] if self.human else 0)
        self.build_all()

    # ----- utilita'
    def mat(self, name):
        return self.A.swatch(name, self.p["cols"][name])

    def opt(self, group, prio):
        self.m.set_prio(group, prio)

    def tdims(self, y):
        return interp_rows(self.tst, y)

    def pdims(self, y):
        return interp_rows(self.pst, y)

    def bdims(self, y):
        return self.tdims(y) if y >= 111.0 else self.pdims(y)

    def tz(self, y, x=0.0, front=True):
        hx, hz = self.bdims(y)
        z = hz * math.sqrt(max(0.0, 1.0 - (x / hx) ** 2)) if self.human else hz
        return z if front else -z

    def limb(self, g, stations, up, mats, n=None, cap0=False, cap1=False):
        n = n or self.nl
        st = smooth_stations(stations, self.ns)
        prev = 0.0
        for i, (s_end, name, grow) in enumerate(mats):
            seg = st if (prev <= 1e-6 and s_end >= 0.999) else cut_stations(st, prev, s_end)
            if grow:
                seg = [(c, ru + grow, rv + grow) for c, ru, rv in seg]
            sweep(self.m, g, self.mat(name), seg, up, n, cap0 and i == 0, cap1 and i == len(mats) - 1, self.smooth)
            prev = s_end

    def chain(self, parts, up, s_split=None, mat_a="top", mat_b="skin", grow_a=0.0, n=None):
        """Un solo tubo continuo per tutto l'arto (niente crepe a gomito/ginocchio/orlo).
        parts: [(gruppo, stazioni), ...] consecutivi; s_split: frazione di lunghezza dove si passa da mat_a a mat_b."""
        n = n or self.nl
        ctrl, marks = [], []
        for gi, (g, st) in enumerate(parts):
            for j, s_ in enumerate(st):
                if gi > 0 and j == 0:
                    continue
                ctrl.append(s_)
            marks.append(len(ctrl) - 1)
        st = smooth_stations(ctrl, self.ns)
        jidx = [m_ * (self.ns + 1) for m_ in marks]
        cs = [np.array(s_[0]) for s_ in st]
        L = [0.0]
        for i in range(1, len(cs)):
            L.append(L[-1] + float(np.linalg.norm(cs[i] - cs[i - 1])))
        tot = L[-1] or 1.0
        frac = [l_ / tot for l_ in L]
        seg_part = [next(p_ for p_, j in enumerate(jidx) if i < j) for i in range(len(st) - 1)]
        out, seg_g, seg_m = [], [], []
        if s_split is None or s_split >= 0.999 or s_split <= 0.001:
            only = mat_a if (s_split is None or s_split >= 0.999) else mat_b
            gr = grow_a if only == mat_a else 0.0
            out = [(c, ru + gr, rv + gr) for c, ru, rv in st]
            seg_g = [parts[p_][0] for p_ in seg_part]
            seg_m = [self.mat(only)] * len(seg_g)
        else:
            for i in range(len(st)):
                if i > 0:
                    a_, b_ = frac[i - 1], frac[i]
                    gp = parts[seg_part[i - 1]][0]
                    if a_ + 1e-4 < s_split < b_ - 1e-4:
                        c, ru, rv = station_at(st, s_split)
                        out.append((c, ru + grow_a, rv + grow_a)); seg_g.append(gp); seg_m.append(self.mat(mat_a))
                        out.append((c, ru, rv)); seg_g.append(gp); seg_m.append(self.mat(mat_b))
                        seg_g.append(gp); seg_m.append(self.mat(mat_b))
                    else:
                        seg_g.append(gp)
                        seg_m.append(self.mat(mat_a) if b_ <= s_split + 1e-4 else self.mat(mat_b))
                c, ru, rv = st[i]
                gr = grow_a if frac[i] <= s_split + 1e-4 else 0.0
                out.append((c, ru + gr, rv + gr))
        sweep(self.m, seg_g, seg_m, out, up, n, False, False, self.smooth)
        c0, c1 = np.array(out[0][0], float), np.array(out[1][0], float)
        self.last_root = (c0, (c1 - c0) / (np.linalg.norm(c1 - c0) + 1e-12))
        return st, frac

    # ----- saldatura: foro nella superficie + cucitura tra due anelli (vertici condivisi)
    @staticmethod
    def _k(p):
        return tuple(np.round(np.asarray(p, float), 4))

    def normal_map(self, groups):
        acc = {}
        for g, pts, uvs, nr in self.m.tris:
            if g in groups:
                for p, n in zip(pts, nr):
                    acc.setdefault(self._k(p), []).append(np.asarray(n, float))
        out = {}
        for k, v in acc.items():
            s = np.sum(v, axis=0)
            out[k] = s / (np.linalg.norm(s) + 1e-9)
        return out

    def cut_hole(self, group, vpred, fpred=None):
        """Toglie i triangoli di 'group' con tutti i vertici dentro vpred(p) (oppure, se dato, fpred(centroide, normale));
        ritorna il bordo del foro come anello ordinato."""
        keep, rem = [], []
        for t_ in self.m.tris:
            if t_[0] == group:
                ps = [np.asarray(p, float) for p in t_[1]]
                if fpred is not None:
                    fn = np.cross(ps[1] - ps[0], ps[2] - ps[0])
                    hit = fpred(sum(ps) / 3.0, fn / (np.linalg.norm(fn) + 1e-12))
                else:
                    hit = all(vpred(p) for p in ps)
                if hit:
                    rem.append(t_)
                    continue
            keep.append(t_)
        if not rem:
            return None
        cnt, pos = {}, {}
        for t_ in rem:
            ks = [self._k(p) for p in t_[1]]
            for p, k in zip(t_[1], ks):
                pos[k] = np.asarray(p, float)
            for i in range(3):
                e = tuple(sorted((ks[i], ks[(i + 1) % 3])))
                cnt[e] = cnt.get(e, 0) + 1
        bnd = [e for e, c in cnt.items() if c == 1]
        adj = {}
        for a, b in bnd:
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        loops, seen = [], set()
        for s in adj:
            if s in seen:
                continue
            loop, prev, cur = [s], None, s
            seen.add(s)
            while True:
                nxt = [v for v in adj[cur] if v != prev and v not in seen]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                seen.add(cur)
                loop.append(cur)
            loops.append(loop)
        loop = max(loops, key=len)
        if len(loop) < 3 or len(loops) > 1:
            return None
        self.m.tris = keep
        return [pos[k] for k in loop]

    def ring_of(self, group, root):
        """L'anello d'attacco dell'ultimo tubo: i vertici del gruppo sul piano (centro, tangente) della prima stazione."""
        c0, t0 = root
        pts = {}
        for g, ps, uvs, nr in self.m.tris:
            if g == group:
                for p in ps:
                    p = np.asarray(p, float)
                    if abs(float(np.dot(p - c0, t0))) < 2e-3 and np.linalg.norm(p - c0) < 15.0:
                        pts[self._k(p)] = p
        return list(pts.values())

    def zipper(self, g, uv, A, B, center, axis, nmap, ref):
        """Cuce due anelli chiusi A e B (ordinati per angolo attorno all'asse) con una striscia di triangoli."""
        axis = np.asarray(axis, float) / np.linalg.norm(axis)
        e1 = np.cross(axis, [0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.cross(axis, [1.0, 0.0, 0.0])
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(axis, e1)
        c = np.asarray(center, float)
        ang = lambda p: math.atan2(float(np.dot(p - c, e2)), float(np.dot(p - c, e1)))
        # A: anello del foro nell'ordine del bordo (non riordinato), orientato come gli angoli crescenti
        A = list(A)
        aa = list(np.unwrap([ang(p) for p in A]))
        if aa[-1] < aa[0]:
            A = A[::-1]
            aa = list(np.unwrap([ang(p) for p in A]))
        B = sorted(B, key=ang)
        bb = [ang(p) for p in B]
        a0 = aa[0]
        j0 = min(range(len(B)), key=lambda j: abs(((bb[j] - a0 + math.pi) % (2 * math.pi)) - math.pi))
        B = B[j0:] + B[:j0]
        bb = bb[j0:] + bb[:j0]
        b0 = a0 + ((bb[0] - a0 + math.pi) % (2 * math.pi)) - math.pi
        bb = [b0] + [b0 + ((x - b0) % (2 * math.pi)) for x in bb[1:]]
        na, nb = len(A), len(B)
        i = j = 0

        def nrm(p, face):
            return nmap.get(self._k(p), face)

        def emit(p, q, r):
            p, q, r = (np.asarray(v, float) for v in (p, q, r))
            fn = np.cross(q - p, r - p)
            ln = np.linalg.norm(fn)
            if ln < 1e-9:
                return
            fn = fn / ln
            if np.dot(fn, (p + q + r) / 3 - ref) < 0:
                fn = -fn
            self.m.tri(g, (p, q, r), (uv, uv, uv), (nrm(p, fn), nrm(q, fn), nrm(r, fn)), ref)

        while i < na or j < nb:
            an = aa[i + 1] if i + 1 < na else aa[0] + 2 * math.pi
            bn = bb[j + 1] if j + 1 < nb else bb[0] + 2 * math.pi
            if j >= nb or (i < na and an <= bn):
                emit(A[i % na], B[j % nb], A[(i + 1) % na])
                i += 1
            else:
                emit(A[i % na], B[j % nb], B[(j + 1) % nb])
                j += 1

    def torso_decal(self, key, painter, w, h, cx, cy, dw, dh, front=True, cols=3, group="Node10_torso"):
        rect = self.A.tile(key, w, h, painter)
        xs = [cx - dw / 2 + dw * i / cols for i in range(cols + 1)]
        decal_curved(self.m, group, rect, xs, cy - dh / 2, cy + dh / 2, lambda x: self.tz(cy, x, front), front)

    # ----- ordine di costruzione
    def build_all(self):
        self.torso()
        self.arms()
        self.legs()
        if self.human:
            self.head_human()
        else:
            self.head_zombie()
        self.hair()
        self.hat()
        self.extras()
        if not self.human:
            self.zombie_decals()

    # ----- busto, bacino, collo
    def torso(self):
        m, n = self.m, (self.nl if self.human else 4)
        tst = self.tst if self.human else [self.tst[i] for i in (0, 2, 4, 6)]
        sweep(m, "Node10_torso", self.mat("top"), smooth_stations([((0, y, 0), hx, hz) for y, hx, hz in tst], self.ns),
              X3, n, False, True, self.smooth)
        sweep(m, "Node3_hips", self.mat("bottom"), smooth_stations([((0, y, 0), hx, hz) for y, hx, hz in self.pst], self.ns),
              X3, n, False, False, self.smooth)
        self.n_body = n
        r = 3.0 if self.sex == "m" else 2.5
        sweep(m, "Node20_neck", self.mat("skin"),
              smooth_stations([((0, 142.8, 0.0), r * 1.15, r * 1.1), ((0, 153.0, 0.2), r * 0.95, r * 0.95)], self.ns), X3,
              self.nl if self.human else 4, False, False, self.smooth)

    # ----- braccia e mani
    def arms(self):
        k = 0.88 if self.sex == "m" else 0.78
        grow = 0.22 if self.human else 0.0
        for side, names in (("L", ("Node13", "Node14", "Node15")), ("R", ("Node17", "Node18", "Node19"))):
            sh, el, wr = (J[n] for n in names)
            sx = 1.0 if sh[0] > 0 else -1.0
            # foro nel fianco del torso alla spalla
            r0y, r0z = 4.7 * k * 1.12, 4.5 * k * 1.12
            ysh = min(sh[1] - 0.6, self.tst[-2][0] + 0.8)
            if self.human:
                hole = self.cut_hole("Node10_torso", lambda p, sx=sx, sh=sh, ry=r0y, rz=r0z, ysh=ysh:
                                     p[0] * sx > 0.72 * self.tdims(p[1])[0] and p[1] < self.tst[-2][0] + 1.3 and
                                     ((p[1] - ysh) / ry) ** 2 + ((p[2] - sh[2]) / rz) ** 2 < 1.0)
            if self.human and hole is None:
                hole = self.cut_hole("Node10_torso", None, lambda c, fn, sx=sx, ysh=ysh, ry=r0y, rz=r0z, sh=sh:
                                     c[0] * sx > 0.6 * self.tdims(c[1])[0] and fn[0] * sx > 0.45 and
                                     abs(c[1] - ysh) < ry and abs(c[2] - sh[2]) < rz)
            if not self.human:                        # torso a scatola: si toglie la faccia laterale all'altezza della spalla
                hole = self.cut_hole("Node10_torso", None, lambda c, fn, sx=sx: c[0] * sx > 0.4 * self.tdims(c[1])[0]
                                     and fn[0] * sx > 0.5 and c[1] > 139.0)
            xr = max([abs(p[0]) for p in hole] + [11.0]) + 0.7 if hole else 11.5
            up_st = [((sx * xr, sh[1], sh[2]), 4.7 * k, 4.5 * k), (tuple(sh), 5.0 * k, 4.8 * k),
                     (tuple((sh + el) / 2), 4.3 * k, 4.1 * k), (tuple(el), 3.7 * k, 3.6 * k)]
            if not self.human:
                up_st = [up_st[0], up_st[2], up_st[3]]
            fo_st = [(tuple(el), 3.7 * k, 3.6 * k), (tuple((el + wr) / 2), 3.5 * k, 3.3 * k),
                     ((wr[0] - sx * 1.0, wr[1], wr[2]), 2.7 * k, 2.4 * k)]
            g_up, g_fo = f"{names[0]}_upperarm_{side}", f"{names[1]}_forearm_{side}"
            s_end = self.o["sleeve_end"][side]
            st, frac = self.chain([(g_up, up_st), (g_fo, fo_st)], Y3, s_end, "top", "skin", grow)
            root = self.last_root
            # orlo della manica (corta) o polsino (lunga)
            if self.human:
                f = s_end if s_end < 0.999 else 0.95
                c, ru, rv = station_at(st, max(0.03, min(0.97, f)))
                c = np.array(c)
                f_el = frac[(self.ns + 1) * (len(up_st) - 1)]
                g_h = f"{names[0]}_upperarm_hem_{side}" if f <= f_el else f"{names[1]}_forearm_hem_{side}"
                hem = [(tuple(c - np.array([sx * 0.9, 0, 0])), ru + grow + 0.28, rv + grow + 0.28),
                       (tuple(c + np.array([sx * 0.2, 0, 0])), ru + grow + 0.32, rv + grow + 0.32)]
                sweep(self.m, g_h, self.mat("hem"), hem, Y3, self.nl, False, False, True)
                self.opt(g_h, 3)
            if hole:
                ring = self.ring_of(g_up, root)
                nmap = self.normal_map({"Node10_torso", g_up})
                c0 = np.array([sx * (xr - 1.2), float(np.mean([p[1] for p in hole])), float(np.mean([p[2] for p in hole]))])
                self.zipper(g_up, self.mat("top" if s_end > 0.001 else "skin"), hole, ring, c0, X3, nmap, c0)
            self.hand(side, sx, wr)

    def hand(self, side, sx, wr):
        m, human = self.m, self.human
        y0, z0 = wr[1], wr[2]
        skin = self.mat("skin")
        n = 6 if human else 4
        wb = "Node15" if sx > 0 else "Node19"
        tb = "Node33" if sx > 0 else "Node29"        # pollice (Node33 SX / Node29 DX)
        fb = "Node34" if sx > 0 else "Node30"        # blocco delle quattro dita
        sweep(m, f"{wb}_hand_{side}", skin, [((sx * 64.0, y0, z0), 1.55, 2.9), ((sx * 69.6, y0, z0 + 0.1), 1.5, 3.1)],
              Y3, n, False, False, human)
        fst = [((sx * 69.4, y0, z0 + 0.1), 1.45, 3.0), ((sx * 74.6, y0, z0), 1.3, 2.8), ((sx * 79.3, y0, z0 - 0.1), 0.95, 2.3)]
        g = f"{fb}_fingers_{side}"
        sweep(m, g, skin, fst if human else [fst[0], fst[2]], Y3, 4, True, True, False)
        if human:                                   # linee tra le dita: tessera dipinta su dorso e palmo
            rect = self.A.tile("fingers", 16, 8, paint_fingers(self.p["cols"]["skin"]))
            u0, vb, u1, vt = rect
            for yy, flip in ((y0 + 3.04, False), (y0 - 3.04, True)):
                xa, xb = sx * 70.6, sx * 79.0
                za, zb = z0 - 2.6, z0 + 2.6
                p = [(xa, yy, za), (xb, yy, za), (xb, yy, zb), (xa, yy, zb)]
                uv = [(u0, vb), (u1, vb), (u1, vt), (u0, vt)]
                ref = np.array([(xa + xb) / 2, y0, z0])
                m.tri(g, (p[0], p[1], p[2]), (uv[0], uv[1], uv[2]), None, ref)
                m.tri(g, (p[0], p[2], p[3]), (uv[0], uv[2], uv[3]), None, ref)
        th = [((sx * 66.4, y0 - 0.9, z0 + 2.4), 1.05, 1.05), ((sx * 69.0, y0 - 1.3, z0 + 4.3), 0.9, 0.9),
              ((sx * 72.4, y0 - 1.2, z0 + 5.6), 0.7, 0.7)]
        sweep(m, f"{tb}_thumb_{side}", skin, th if human else th[::2], Y3, 6 if human else 3, False, True, human)

    # ----- gambe e piedi
    def legs(self):
        k = 0.9 if self.sex == "m" else 0.84
        skirt = self.o.get("skirt_hem")
        shorts_end = self.o.get("shorts_end") if not skirt else None
        leg_mat = "skin" if skirt else "bottom"
        grow = 0.2 if (self.human and not skirt) else 0.0
        # bordo inferiore del bacino diviso in due anelli (uno per coscia) con un vertice al cavallo
        yb = self.pst[-1][0]
        pel = {}
        for g, ps, uvs, nr in self.m.tris:
            if g == "Node3_hips":
                for p in ps:
                    if abs(p[1] - yb) < 1e-4:
                        pel[self._k(p)] = np.asarray(p, float)
        pel = list(pel.values())
        crotch = np.array([0.0, yb - 1.4, 0.0])
        loops = {"L": [p for p in pel if p[0] > -1e-6] + [crotch], "R": [p for p in pel if p[0] < 1e-6] + [crotch]}
        nmap_p = self.normal_map({"Node3_hips"})
        pmat = self.mat("bottom")
        for zs in (1, -1):                               # chiude le tacche davanti e dietro tra le due gambe
            lft = [p for p in pel if p[0] > 1e-6 and p[2] * zs > 0]
            rgt = [p for p in pel if p[0] < -1e-6 and p[2] * zs > 0]
            if lft and rgt and not any(abs(p[0]) < 1e-6 and p[2] * zs > 0 for p in pel):
                pl, pr = min(lft, key=lambda p: p[0]), max(rgt, key=lambda p: p[0])
                ref = np.array([0.0, yb + 6.0, 0.0])
                fn = np.cross(pr - pl, crotch - pl)
                fn = fn / (np.linalg.norm(fn) + 1e-9)
                if np.dot(fn, (pl + pr + crotch) / 3 - ref) < 0:
                    fn = -fn
                self.m.tri("Node3_hips", (pl, pr, crotch), (pmat,) * 3,
                           (nmap_p.get(self._k(pl), fn), nmap_p.get(self._k(pr), fn), fn), ref)
        for side, (hn, kn, an) in (("L", ("Node4", "Node5", "Node6")), ("R", ("Node7", "Node8", "Node9"))):
            h, kk, a = J[hn], J[kn], J[an]
            ytop = yb - 2.2
            thigh = [((h[0], ytop, h[2]), 5.8 * k, 5.8 * k), ((h[0], 76.0, 0.4), 5.5 * k, 5.5 * k), (tuple(kk), 4.5 * k, 4.6 * k)]
            shin = [(tuple(kk), 4.5 * k, 4.6 * k), ((kk[0], 40.0, 0.0), 4.3 * k, 4.4 * k), ((a[0], a[1] - 1.5, a[2]), 3.3 * k, 3.3 * k)]
            g_th = f"{hn}_thigh_{side}"
            if shorts_end:
                st, _ = self.chain([(g_th, thigh), (f"{kn}_shin_{side}", shin)], X3, shorts_end, "bottom", "skin", grow)
            else:
                st, _ = self.chain([(g_th, thigh), (f"{kn}_shin_{side}", shin)], X3, None, leg_mat, leg_mat, grow)
            ring = self.ring_of(g_th, self.last_root)
            nmap = self.normal_map({"Node3_hips", g_th})
            cl = np.array([h[0], yb - 1.0, h[2]])
            loop = sorted(loops[side], key=lambda p, cl=cl: math.atan2(p[0] - cl[0], p[2] - cl[2]))
            self.zipper(g_th, self.mat(leg_mat), loop, ring, cl, Y3, nmap, cl)
            if shorts_end:                            # orlo dei pantaloncini a meta' coscia
                f = max(0.05, min(0.95, shorts_end))
                c, ru, rv = station_at(st, f)
                g_h = f"{hn}_shorts_hem_{side}"
                sweep(self.m, g_h, self.mat("hem"), [((c[0], c[1] + 1.1, c[2]), ru + grow + 0.35, rv + grow + 0.35),
                                                      ((c[0], c[1] - 0.6, c[2]), ru + grow + 0.3, rv + grow + 0.3)],
                      X3, self.nl if self.human else 4, False, False, self.smooth)
                self.opt(g_h, 3)
            if not skirt and not shorts_end and (self.human or self.lvl >= 2):
                g = f"{kn}_cuff_{side}"
                sweep(self.m, g, self.mat("cuff"), [((a[0], a[1] - 2.6, a[2]), 3.3 * k + grow + 0.45, 3.3 * k + grow + 0.45),
                                                    ((a[0], a[1] + 0.6, a[2]), 3.3 * k + grow + 0.4, 3.3 * k + grow + 0.4)],
                      X3, self.nl if self.human else 4, False, True, self.smooth)
                self.opt(g, 3)
            self.foot(side, an, a)

    def foot(self, side, an, a):
        ax = a[0]
        missing = self.p.get("shoe_missing") == side
        mname = "skin" if missing else "shoe"
        if self.human:
            st = [((ax, 5.0, -5.8), 2.9, 4.6), ((ax, 5.4, -3.6), 3.5, 5.3), ((ax, 5.0, 2.8), 3.9, 5.0),
                  ((ax, 4.0, 9.4), 3.8, 3.9), ((ax, 3.1, 13.4), 3.2, 2.8), ((ax, 2.7, 14.6), 2.0, 1.8)]
            n = self.nl
        else:
            st = [((ax, 5.2, -5.4), 3.7, 5.2), ((ax, 3.4, 13.8), 3.5, 3.2)]
            n = 4
        sweep(self.m, f"{an}_foot_{side}", self.mat(mname), smooth_stations(st, self.ns), X3, n, True, True, self.smooth)
        if not missing and self.o.get("boots"):       # stivaletto: gambale che sale dalla caviglia a meta' stinco
            g = f"{an}_boot_{side}"
            bst = [((ax, 3.0, -1.0), 3.7, 4.6), ((ax, 10.0, -0.4), 3.3, 3.7), ((ax, 23.0, 0.0), 2.9, 2.9)]
            sweep(self.m, g, self.mat("shoe"), bst if self.human else [bst[0], bst[2]],
                  X3, self.nl if self.human else 4, True, False, self.smooth)
            self.opt(g, 3)
        if not missing and self.human:
            sweep(self.m, f"{an}_sole_{side}", self.mat("sole"), [((ax, 1.1, -5.8), 4.1, 1.1), ((ax, 1.1, 13.9), 3.9, 1.1)],
                  X3, 4, True, True, False)
            if "laces" in self.o["extras"]:
                g = f"{an}_laces_{side}"
                for z in (4.6, 6.6, 8.6):
                    yt = interp_rows([(zz, yy + rv) for (_, yy, zz), ru, rv in [((s_[0][0], s_[0][1], s_[0][2]), s_[1], s_[2]) for s_ in st]], z)[0]
                    box(self.m, g, self.mat("lace"), (ax, yt - 0.1, z), (1.7, 0.2, 0.32))
                self.opt(g, 5)

    # ----- testa (stile anime): utilita' di superficie
    def front_z(self, y, x):
        """z della superficie frontale della testa: poligono dell'anello alla quota y."""
        hx, zc, rv = self.hd(y)
        n = self.L["hn"]
        sc = 1.0 / math.cos(math.pi / n)
        pts = [(sc * hx * math.cos(math.pi / n + 2 * math.pi * k / n), sc * rv * math.sin(math.pi / n + 2 * math.pi * k / n))
               for k in range(n)]
        best = None
        for i in range(n):
            (x0, z0), (x1, z1) = pts[i], pts[(i + 1) % n]
            if (x0 - x) * (x1 - x) <= 0 and abs(x1 - x0) > 1e-9:
                z = z0 + (z1 - z0) * (x - x0) / (x1 - x0)
                if z > 0 and (best is None or z > best):
                    best = z
        return zc + (best if best is not None else 0.0)

    def patch(self, g, rect, x0, x1, y0, y1, nx, ny, off, flip=False, smooth=True):
        """Tessera dipinta adagiata sulla faccia: griglia nx*ny che segue la superficie, off(x, y) = distacco."""
        u0, vb, u1, vt = rect
        if flip:
            u0, u1 = u1, u0
        xs = np.linspace(x0, x1, nx + 1)
        y0f = y0 if callable(y0) else (lambda x: y0)
        P = np.array([[(x, y0f(x) + (y1 - y0f(x)) * j / ny, 0.0) for x in xs] for j in range(ny + 1)])
        for j in range(ny + 1):
            for i in range(nx + 1):
                P[j, i, 2] = self.front_z(P[j, i, 1], P[j, i, 0]) + off(P[j, i, 0], P[j, i, 1])
        UV = [[(u0 + (u1 - u0) * i / nx, vb + (vt - vb) * j / ny) for i in range(nx + 1)] for j in range(ny + 1)]
        N = np.zeros_like(P)
        for j in range(ny + 1):
            for i in range(nx + 1):
                dx = P[j, min(i + 1, nx)] - P[j, max(i - 1, 0)]
                dy = P[min(j + 1, ny), i] - P[max(j - 1, 0), i]
                n = np.cross(dx, dy)
                n = n / (np.linalg.norm(n) + 1e-9)
                N[j, i] = n if n[2] >= 0 else -n
        for j in range(ny):
            for i in range(nx):
                q = [(j, i), (j, i + 1), (j + 1, i + 1), (j + 1, i)]
                pts = [P[a_, b_] for a_, b_ in q]
                uvs = [UV[a_][b_] for a_, b_ in q]
                nr = [N[a_, b_] for a_, b_ in q]
                ref = np.mean(pts, axis=0) - np.array([0, 0, 1.0])
                self.m.tri(g, (pts[0], pts[1], pts[2]), (uvs[0], uvs[1], uvs[2]), (nr[0], nr[1], nr[2]) if smooth else None, ref)
                self.m.tri(g, (pts[0], pts[2], pts[3]), (uvs[0], uvs[2], uvs[3]), (nr[0], nr[2], nr[3]) if smooth else None, ref)

    # ----- testa umana: parti separate per le espressioni
    def head_human(self):
        m, L = self.m, self.L
        n, hs = L["hn"], L["hs"]
        skin = self.mat("skin")
        dense = smooth_stations(head_stations(self.head_tab), hs)
        up = [st for st in dense if st[0][1] >= 156.4 - 1e-6]
        low = [(c[1], ru, c[2] - rv, c[2] + rv) for c, ru, rv in dense if c[1] <= 156.4 + 1e-6]
        # cranio: calotta alta + tubo posteriore basso; mandibola = blocco del mento davanti alla cerniera (niente "pacman")
        # mandibola = parte bassa della testa, stessa superficie: i vertici della giuntura sono condivisi (pelle continua,
        # da sfumare col weight paint) tranne lungo la bocca, dove c'e' un taglio: aprendo si apre solo la bocca.
        chin = [st for st in dense if st[0][1] <= 156.4 + 1e-6]
        sweep(m, "Node21_head", skin, up, X3, n, False, True, True, axis=Y3)
        k0 = len(m.tris)
        sweep(m, "Node27_jaw", skin, chin, X3, n, True, False, True, axis=Y3)
        yj = chin[-1][0][1]
        zmid = chin[-1][0][2]
        for i in range(k0, len(m.tris)):
            g_, pts_, uvs_, nr_ = m.tris[i]
            new = []
            for p_ in pts_:
                if abs(p_[1] - yj) < 1e-4 and abs(p_[0]) < 2.45 and p_[2] > zmid:
                    p_ = np.array([p_[0], yj - 0.004, p_[2]])
                new.append(p_)
            m.tris[i] = (g_, tuple(new), uvs_, nr_)
        self.mouth_seam = yj
        fz = self.front_z
        # interno della bocca (visibile solo a bocca aperta)
        def sack(y):
            zf = min(fz(y, 0.0), fz(y, 2.2), fz(y, -2.2)) - 0.55
            return ((0, y, (zf - 3.0) / 2.0), 2.2, (zf + 3.0) / 2.0)
        sweep(m, "Node21_head_mouth", self.mat("mouthin"), [sack(155.0), sack(157.6)], X3, max(8, n // 2), True, True, False,
              axis=Y3)
        # labbra (separate: superiore sulla testa, inferiore sulla mandibola)
        ln = L["lip"]
        lw = 2.3
        xs = np.linspace(-lw, lw, ln)
        up_pts, lo_pts = [], []
        for x in xs:
            up_pts.append(((x, 156.72 + 0.2 * (1 - abs(x) / lw), fz(156.75, x) + 0.16), 0.42, 0.45))
            lo_pts.append(((x, 156.08 - 0.26 * (1 - (x / lw) ** 2), fz(156.0, x) + 0.16), 0.48, 0.48))
        ln_n = 6 if self.lvl >= 2 else 4
        sweep(m, "Node21_lip", self.mat("lip"), up_pts, Y3, ln_n, True, True, True)
        sweep(m, "Node27_jaw_lip", self.mat("lip"), lo_pts, Y3, ln_n, True, True, True)
        if self.lvl >= 3:
            for g, y in (("Node21_teeth", 156.42), ("Node27_jaw_teeth", 156.0)):
                pts = [((x, y, fz(y, x) - 0.9), 0.5, 0.3) for x in np.linspace(-1.9, 1.9, max(4, ln - 1))]
                sweep(m, g, self.mat("teeth"), pts, Y3, 4, True, True, False)
        # naso piccolo
        sweep(m, "Node21_nose", skin, [((0, 160.6, fz(160.6, 0) - 0.3), 0.35, 0.3), ((0, 159.3, fz(159.3, 0) + 0.55), 0.55, 0.42)],
              X3, 6, False, True, True)
        # orecchie piccole
        hx, zc, rv = self.hd(160.6)
        for side, sx in (("L", 1), ("R", -1)):
            ellipsoid(m, f"Node21_ear_{side}", skin, (sx * (hx + 0.25), 160.6, zc - 0.7), (0.6, 2.0, 1.25), 6 + self.lvl // 4, 5, True)
        # occhi anime: bianco (statico), iride Eye_L/Eye_R (si muove), palpebra con ciglia (Node24/Node26)
        rs = self.A.tile("sclera", 24, 16, paint_sclera(self.p["cols"]))
        ri = self.A.tile("iris", 12, 14, paint_iris(self.p["cols"]))
        rl = self.A.tile("lid", 24, 24, paint_lid(self.p["cols"]))
        gx, gy = 2 + self.lvl // 3, 2 + self.lvl // 4
        EW, EH0, EH1 = 1.85, 1.3, 1.4                     # semi-larghezza, sotto, sopra (bianco dell'occhio)
        for side, sx, lid_b, brow_b in (("L", 1, "Node24", "Node23"), ("R", -1, "Node26", "Node25")):
            ex, ey = sx * 3.2, 161.9
            bulge = lambda x, y, ex=ex: 0.04 + 0.07 * max(0.0, 1 - ((x - ex) / EW) ** 2 - ((y - ey) / 1.35) ** 2)
            flip = sx < 0
            self.patch(f"Node22_eyewhite_{side}", rs, ex - EW, ex + EW, ey - EH0, ey + EH1, gx + 1, gy, bulge, flip)
            ix = ex - sx * 0.08
            self.patch(f"Eye_{side}", ri, ix - 1.02, ix + 1.02, ey - 1.08, ey + 1.12, gx, gy,
                       lambda x, y, b=bulge: b(x, y) + 0.03, flip)
            # palpebra: il bordo inferiore segue l'arco superiore del bianco (le ciglia sono dipinte li')
            lid_lo = lambda x, ex=ex: ey + EH1 - 0.32 - 0.42 * ((x - ex) / EW) ** 2
            self.patch(f"{lid_b}_eyelid_{side}", rl, ex - EW - 0.1, ex + EW + 0.1, lid_lo, ey + 3.95, gx + 1, max(2, gy),
                       lambda x, y: 0.19, flip)
            # perno della palpebra: centro del cerchio che meglio segue il profilo della faccia sopra l'occhio
            yy = np.linspace(ey - 1.6, ey + 3.6, 9)
            zz = np.array([fz(y, ex) for y in yy])
            A_ = np.c_[2 * yy, 2 * zz, np.ones_like(yy)]
            sol = np.linalg.lstsq(A_, yy ** 2 + zz ** 2, rcond=None)[0]
            yc, zc0 = float(sol[0]), float(sol[1])
            rad = math.sqrt(max(1.0, sol[2] + yc * yc + zc0 * zc0))
            if not (2.0 < rad < 60.0) or zc0 > fz(ey, ex):
                yc, zc0, rad = ey, fz(ey, ex) - 6.0, 6.0
            self.lid_angle = math.degrees(2.55 / rad)
            self.pivots[f"Eye_{side}"] = (ex, ey, fz(ey, ex) - 1.4)
            self.pivots[f"{lid_b}_eyelid_{side}"] = (ex, yc, zc0)
            kb = 4 + self.lvl // 3
            pts = []
            for i in range(kb):
                t = i / (kb - 1)
                x = 1.5 + 3.5 * t
                y = 164.7 + 0.45 * math.sin(math.pi * t) - 0.35 * t
                pts.append(((sx * x, y, fz(y, x) + 0.2), 0.3 * (1 - 0.4 * t), 0.22))
            sweep(m, f"{brow_b}_eyebrow_{side}", self.mat("brow"), pts, Y3, 6 if self.lvl >= 4 else 4, True, True, self.lvl >= 4)

    # ----- testa zombie (stessa forma, low poly; faccia dipinta)
    def head_zombie(self):
        st = head_stations(self.head_tab)
        sweep(self.m, "Node21_head", self.mat("skin"), st, X3, self.L["hn"], True, True, False, axis=Y3)
        rect = self.A.tile("face", 32, 32, lambda arr: paint_zombie_face_anime(arr, self.p))
        u0, vb, u1, vt = rect
        rows = [152.2, 155.0, 161.0, 168.0]
        grid = []
        for y in rows:
            hw = min(6.4, self.hd(y)[0] * 0.97)
            row = []
            for x in (-hw, 0.0, hw):
                p = np.array([x, y, self.front_z(y, x) + 0.05])
                uv = (u0 + (u1 - u0) * (x + 6.4) / 12.8, vb + (vt - vb) * (y - 152.2) / 15.8)
                row.append((p, uv))
            grid.append(row)
        for j in range(len(rows) - 1):
            for i in range(2):
                q = [grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]]
                ref = np.mean([e[0] for e in q], axis=0) - np.array([0, 0, 1.0])
                self.m.tri("Node21_head", (q[0][0], q[1][0], q[2][0]), (q[0][1], q[1][1], q[2][1]), None, ref)
                self.m.tri("Node21_head", (q[0][0], q[2][0], q[3][0]), (q[0][1], q[2][1], q[3][1]), None, ref)

    # ----- capelli a ciocche (corti / lunghi / codino)
    def hair(self):
        style = self.p["hair_style"]
        if style in (None, "none"):
            return
        human, m, L = self.human, self.m, self.L
        mat = self.mat("hair")
        rng = random.Random(self.p["seed"] * 13 + 7)
        n_ring = L["hn"]
        over = lambda y: max(self.hd(y)[0], self.hd(y)[2]) * (1.0 / math.cos(math.pi / n_ring) - 1.0)
        base = 0.32 if human else 0.25

        def sp(y, ang, extra=0.0):
            hx, zc, rv = self.hd(y)
            o = base + over(y) + extra
            a = math.radians(ang)
            return np.array([(hx + o) * math.sin(a), y, zc + (rv + o) * math.cos(a)])

        lvl = self.lvl
        K = (5 if lvl >= 6 else 4) if human else 2
        side_n = 4 if human else 3

        grp = {"g": "Node21_hair"}

        def clump(p0, pm, p1, w, th, extra_pts=()):
            p0, pm, p1 = (np.asarray(p, float) for p in (p0, pm, p1))
            ctrl = 2 * pm - (p0 + p1) / 2
            pts = [(1 - t) ** 2 * p0 + 2 * (1 - t) * t * ctrl + t * t * p1 for t in np.linspace(0, 1, K)]
            pts += [np.asarray(e, float) for e in extra_pts]
            T = pts[-1] - pts[0]
            hx, zc, rv = self.hd(min(max(p0[1], 151.0), 174.0))
            Nn = p0 - np.array([0.0, p0[1], zc])
            upv = np.cross(T, Nn)
            if np.linalg.norm(upv) < 1e-6:
                upv = X3
            cnt = len(pts)
            st = [(tuple(p), max(0.08, w * (1 - 0.85 * (i / (cnt - 1)) ** 1.3) / 2), max(0.06, th * (1 - 0.55 * i / (cnt - 1)) / 2))
                  for i, p in enumerate(pts)]
            sweep(m, grp["g"], mat, st, upv, side_n, False, True, human)

        # calotta: copre cranio e nuca, lascia libera la fronte
        ybot = {"short": 160.2, "long": 158.0, "tail": 160.2}.get(style, 160.0)
        ys = list(np.linspace(ybot, 173.4, 6 + lvl // 3)) if human else [ybot, 168.0, 171.6]
        st = []
        for y in ys:
            hx, zc, rv = self.hd(y)
            o = base + over(y)
            zb, zf = zc - rv - o, zc + rv + o
            k = min(1.0, max(0.0, (y - 167.0) / 2.6))
            zfh = (zc + 0.2 * rv) * (1 - k) + zf * k
            st.append(((0, y, (zb + zfh) / 2.0), hx + o, (zfh - zb) / 2.0))
        hx, zc, rv = self.hd(174.0)
        st.append(((0, 174.3 + base + 0.25, zc), hx * 0.5, rv * 0.5))
        if human or not self.o["hat"]:                    # zombie col cappello: la calotta non serve (risparmio triangoli)
            sweep(m, "Node21_hair", mat, st, X3, n_ring, False, True, human, axis=Y3)
        if not human:
            self.opt("Node21_hair", 1.4 if self.o["hat"] else 1)
        # frangia
        nb = min(13, 8 + lvl // 2) if human else 2
        for i in range(nb):
            t = i / (nb - 1)
            ang = -64 + 128 * t + rng.uniform(-4, 4)
            ry = 172.4 - 2.2 * abs(ang) / 64
            tip_y = rng.uniform(163.7, 165.2) if abs(ang) < 40 else rng.uniform(163.4, 165.4)
            ang_t = ang * 0.95 + rng.uniform(-5, 5)
            clump(sp(ry, ang, 0.05), sp((ry + tip_y) / 2, (ang + ang_t) / 2, 0.32), sp(tip_y, ang_t, 0.1),
                  rng.uniform(2.7, 3.3) if human else 4.6, 0.6 if human else 0.8)
        # ciocche laterali davanti alle orecchie
        for sx in (1, -1):
            nside = (2 if lvl >= 5 else 1) if human else (0 if style == "short" else 1)
            for j in range(nside):
                ang = sx * (74 + 9 * j)
                tip = {"short": 159.2, "long": 149.5 - 2 * j, "tail": 152.5 - j}[style]
                p0, p1 = sp(168.5, ang, 0.05), sp(max(tip, 152.0), ang + sx * 6, 0.5)
                if tip < 152.0:
                    p1 = p1 + np.array([sx * 0.4, tip - 152.0, 0.6])
                clump(p0, (p0 + p1) / 2 + np.array([sx * 0.7, 0, 0.3]), p1, 2.3 if human else 3.4, 0.6)
        # tempie: coprono il bordo della calotta sopra le orecchie
        if human or lvl >= 2:
            for sx in (1, -1):
                for j in range(2 if human else 1):
                    ang = sx * (96 + 12 * j)
                    p0 = sp(170.5, ang, 0.05)
                    p1 = sp(158.6 - 0.8 * j, ang + sx * 4, 0.35)
                    clump(p0, (p0 + p1) / 2 + np.array([sx * 0.5, 0, 0]), p1, 3.0 if human else 4.4, 0.65)
        # dietro (zombie: gruppo a parte, sacrificabile se il budget e' stretto)
        if not human:
            grp["g"] = "Node21_hair_back"
            self.opt("Node21_hair_back", 1.5)
        if style == "short":
            nk = (6 + lvl // 2) if human else 2
            for i in range(nk):
                ang = 100 + 160 * i / max(1, nk - 1) + rng.uniform(-5, 5)
                tip = rng.uniform(155.6, 157.8)
                clump(sp(171.8, ang), sp(164.0, ang, 0.45), sp(tip, ang + rng.uniform(-6, 6), 0.25), 3.4 if human else 5.0, 0.75)
        elif style == "long":
            nk = (8 + lvl // 2) if human else 3
            for i in range(nk):
                t = i / max(1, nk - 1)
                ang = 102 + 156 * t + rng.uniform(-4, 4)
                p0, pm, p1 = sp(171.6, ang), sp(163.0, ang, 0.55), sp(155.0, ang, 0.7)
                if 125 <= ang <= 235:
                    tip = rng.uniform(132.0, 140.0)
                    drop = p1 + np.array([0.0, tip - 155.0, -0.6])
                else:
                    tip = rng.uniform(146.0, 149.0)
                    drop = p1 + np.array([math.copysign(1.4, math.sin(math.radians(ang))), tip - 155.0, -1.4])
                if human:
                    clump(p0, pm, p1, 2.9, 0.75, extra_pts=[(p1 + drop) / 2, drop])
                else:
                    clump(p0, pm, drop, 5.2, 0.8)
        elif style == "tail":
            tie = sp(166.0, 180, 0.4)
            nk = (6 + lvl // 3) if human else 0
            for i in range(nk):
                ang = 110 + 140 * i / max(1, nk - 1)
                ry = 171.6 if abs(ang - 180) < 40 else 164.5
                p0 = sp(ry, ang)
                clump(p0, (p0 + tie) / 2 + 0.5 * (p0 - np.array([0, p0[1], 0])) / 12.0, tie, 3.0 if human else 5.0, 0.7)
            d = np.array([0, 0, -1.0])
            sweep(m, grp["g"], self.mat("tie_band"), [(tuple(tie + d * 0.3), 1.2, 1.2), (tuple(tie + d * 1.4), 1.25, 1.25)],
                  d, 6 if human else 4, False, False, human)
            ntl = (4 + lvl // 4) if human else 2
            for j in range(ntl):
                a = 2 * math.pi * j / ntl
                o = np.array([0.7 * math.cos(a), 0.7 * math.sin(a), 0])
                p0 = tie + d * 1.2 + o
                pm = tie + np.array([o[0] * 1.6, -4.0 + o[1], -3.6])
                p1 = tie + np.array([o[0] * 2.2 + rng.uniform(-0.8, 0.8), -18.0 + rng.uniform(-2, 2), -2.4])
                clump(p0, pm, p1, 2.4 if human else 3.6, 1.0)

    # ----- cappelli
    def hat(self):
        h = self.o["hat"]
        if not h:
            return
        m, human = self.m, self.human
        dy = 2.6                                          # testa piu' alta: il cappello sale
        hx, zc, rv = self.hd(167.5 + dy)
        ru, rvv = hx + 1.6, rv + 1.3
        n = max(8, self.nl) if human else 4
        g = "Node21_hat"
        top = self.mat("top")
        if h == "police":
            if human:
                sweep(m, g, self.mat("black"), [((0, 169.5, zc), ru + 0.25, rvv + 0.25), ((0, 171.1, zc), ru + 0.25, rvv + 0.25)],
                      X3, n, False, False, human)
            cap = [((0, 169.9, zc), ru, rvv), ((0, 174.5, zc), ru - 0.4, rvv - 0.4), ((0, 177.6, zc), ru - 1.5, rvv - 1.4)]
            sweep(m, g, top, cap if human else [cap[0], cap[2]], X3, n, False, True, human)
            sweep(m, g, self.mat("black"), [((0, 170.9, zc + rvv - 0.4), ru * 0.8, 0.5), ((0, 170.1, zc + rvv + 4.2), ru * 0.72, 0.4)],
                  X3, 4, True, True, False)
            rect = self.A.tile("capbadge", 8, 8, paint_rows(BADGE_ROWS, pal_bg(self.p["cols"]["top"], g=(232, 192, 62), d=(150, 112, 30))))
            decal_curved(m, g, rect, [-1.7, 1.7], 171.7, 174.1, lambda x: zc + rvv - 0.2, True, 0.18)
        elif h == "nurse":
            sweep(m, g, self.mat("white"), [((0, 172.9, zc + 0.8), 6.4, 5.0), ((0, 175.3, zc + 0.6), 5.5, 4.1)], X3, n, False, True, human)
        elif h == "toque":
            sweep(m, g, self.mat("white"), [((0, 170.2, zc), hx + 1.0, rv + 0.9), ((0, 175.9, zc), hx + 1.4, rv + 1.3)], X3, n, False, False, human)
            ellipsoid(m, g, self.mat("white"), (0, 179.6, zc), (hx + 3.0, 4.6, rv + 2.8), max(6, n), 5 if human else 4, human)
        elif h == "mech":
            acc = self.mat("accent")
            sweep(m, g, acc, [((0, 169.8, zc), ru, rvv), ((0, 174.0, zc), ru - 0.5, rvv - 0.5), ((0, 176.2, zc), ru - 2.2, rvv - 2.0)],
                  X3, n, False, True, human)
            sweep(m, g, acc, [((0, 170.6, zc + rvv - 0.5), ru * 0.75, 0.45), ((0, 169.4, zc + rvv + 3.6), ru * 0.7, 0.35)], X3, 4, True, True, False)
        self.opt(g, 1)

    # ----- accessori e dettagli dell'uniforme
    def extras(self):
        o, m, human = self.o, self.m, self.human
        ex = o["extras"]
        n = self.nl if human else 5
        skirt = o.get("skirt_hem")
        if skirt:
            st = [((0, 108.6, 0), 9.4, 6.2), ((0, 100.0, 0), 12.6, 8.4), ((0, skirt, 0), 14.8, 9.6)]
            sweep(m, "Node3_skirt", self.mat("bottom"), smooth_stations(st, max(0, self.ns - 1)) if human else [st[0], st[2]],
                  X3, n if human else 4, False, True, self.smooth)
        if "coat_tail" in ex:
            st = [((0, 105.0, 0), 13.0, 9.0), ((0, 88.0, 0), 14.0, 9.2), ((0, 70.0, 0), 14.8, 9.6)]
            sweep(m, "Node3_coat", self.mat("top"), smooth_stations(st, max(0, self.ns - 1)) if human else [st[0], st[2]],
                  X3, n if human else 4, False, True, self.smooth)
        if "jacket" in ex:                            # giacca corta sopra la maglia (si vede alla scollatura)
            hx1, hz1 = self.tdims(142.0)
            hx2, hz2 = self.tdims(118.0)
            st = [((0, 146.5, 0), hx1 + 1.0, hz1 + 1.0), ((0, 130.0, 0), hx2 + 1.15, hz2 + 1.15),
                  ((0, 108.0, 0), hx2 + 1.25, hz2 + 1.3)]
            sweep(m, "Node10_jacket", self.mat("top"), smooth_stations(st, max(0, self.ns - 1)) if human else [st[0], st[2]],
                  X3, n if human else 4, False, True, self.smooth)
            self.opt("Node10_jacket", 2)
        if "collar" in ex:
            sweep(m, "Node20_collar", self.mat("collar"), smooth_stations(
                [((0, 143.9, 0.3), 5.7, 5.5), ((0, 147.8, 0.3), 4.9, 4.7)], self.ns), X3, n, False, False, self.smooth)
            self.opt("Node20_collar", 2)
        if "belt" in ex:
            hx, hz = self.pdims(109.8)
            bc = self.mat("belt")
            sweep(m, "Node3_belt", bc, [((0, 107.8, 0), hx + 0.55, hz + 0.55), ((0, 111.8, 0), hx + 0.35, hz + 0.35)], X3, n, False, False, self.smooth)
            box(m, "Node3_belt", self.mat("buckle"), (0, 109.8, hz + 0.7), (2.0, 1.7, 0.35))
            if human:
                box(m, "Node3_belt", self.mat("belt"), (0, 109.8, hz + 0.95), (1.2, 0.9, 0.2))
            self.opt("Node3_belt", 2)
        if "holster" in ex:
            hx, _ = self.pdims(100.5)
            box(m, "Node7_holster", self.mat("black"), (-(hx + 2.5), 100.5, 0.6), (1.8, 6.8, 3.4))
            box(m, "Node7_holster", self.mat("metal"), (-(hx + 2.5), 108.6, -1.0), (1.4, 2.0, 1.8))
            self.opt("Node7_holster", 4)
        if "cuffs" in ex:
            box(m, "Node3_belt", self.mat("black"), (2.5, 109.8, -(self.pdims(109.8)[1] + 1.2)), (2.2, 2.4, 0.9))
            self.opt("Node3_belt", 3)
        if "radio" in ex:
            box(m, "Node11_radio", self.mat("metal"), (9.0, 138.8, self.tz(138.8, 9.0) + 0.7), (1.8, 2.4, 0.9))
            self.opt("Node11_radio", 5)
        if "tie" in ex:
            box(m, "Node11_tie", self.mat("accent"), (0, 134.2, self.tz(134.2) + 0.5), (1.1, 7.0, 0.4))
            box(m, "Node11_tie", self.mat("accent"), (0, 141.4, self.tz(141.4) + 0.5), (1.5, 1.2, 0.5))
            self.opt("Node11_tie", 3)
        if "epaulets" in ex:
            for side, sx in (("L", 1), ("R", -1)):
                box(m, f"Node13_epaulet_{side}", self.mat("black"), (sx * 13.2, 149.0, -1.2), (3.2, 0.5, 2.6))
                self.opt(f"Node13_epaulet_{side}", 6)
        if "badge" in ex:
            rect = self.A.tile("badge", 8, 8, paint_rows(BADGE_ROWS, pal_bg(self.p["cols"]["top"], g=(232, 192, 62), d=(150, 112, 30))))
            xs = [4.9, 6.2, 7.5, 8.7] if human else [4.9, 8.7]
            decal_curved(m, "Node10_torso", rect, xs, 130.3, 134.7, lambda x: self.tz(132.5, x), True)
        if "nametag" in ex:
            if human:
                box(m, "Node11_nametag", self.mat("gold"), (-6.8, 133.5, self.tz(133.5, -6.8) + 0.3), (2.6, 0.6, 0.25))
                self.opt("Node11_nametag", 2)
        if "pocket" in ex:
            rect = self.A.tile("pocket", 8, 8, paint_rows(POCKET_ROWS, pal_bg(self.p["cols"]["top"], d=shade(self.p["cols"]["top"], 0.7))))
            xs = [5.4, 6.6, 7.8, 9.0] if human else [5.4, 9.0]
            decal_curved(m, "Node10_torso", rect, xs, 128.0, 132.8, lambda x: self.tz(130.4, x), True)
        if "cross" in ex:
            rect = self.A.tile("cross", 8, 8, paint_rows(CROSS_ROWS, pal_bg(self.p["cols"]["top"], r=(200, 50, 50))))
            xs = [-8.8, -7.6, -6.4, -5.2] if human else [-8.8, -5.2]
            decal_curved(m, "Node10_torso", rect, xs, 129.0, 133.0, lambda x: self.tz(131.0, x), True)
        if "vneck" in ex:
            shirt = self.p["cols"]["shirt"] if self.o["coat"] else shade(self.p["cols"]["top"], 0.75)
            rect = self.A.tile("vneck", 8, 8, paint_rows(VNECK_ROWS, pal_bg(self.p["cols"]["top"], s=shirt)))
            xs = [-3.6, -1.2, 1.2, 3.6] if human else [-3.6, 3.6]
            decal_curved(m, "Node10_torso", rect, xs, 133.0, 144.0, lambda x: self.tz(139.0, x), True)
        if "stetho" in ex and human:
            pts = []
            for px, py in ((-5.2, 145.0), (-6.6, 139.0), (-4.6, 132.0), (0.0, 128.4), (4.6, 132.0), (6.6, 139.0), (5.2, 145.0)):
                z = 0.5 if py >= 145 else self.tz(py, px) + 0.55
                pts.append(((px, py, z), 0.45, 0.45))
            sweep(m, "Node11_stetho", self.mat("black"), smooth_stations(pts, 1 if self.lvl >= 4 else 0), Y3, 6, True, True, True)
            ellipsoid(m, "Node11_stetho", self.mat("metal"), (0, 127.8, self.tz(127.8) + 0.9), (1.1, 1.1, 0.6), 8, 4, True)
        if "buttons" in ex:
            for y in range(118, 142, 5 if human else 7):
                for bx in (-1.2, 1.2):
                    box(m, "Node11_buttons", self.mat("metal"), (bx, y, self.tz(y, bx) + 0.3), (0.5, 0.5, 0.28))
            self.opt("Node11_buttons", 4)
        if "neckerchief" in ex:
            sweep(m, "Node20_neckerchief", self.mat("red"), [((0, 144.0, 0.4), 5.2, 5.0), ((0, 146.6, 0.4), 4.7, 4.5)], X3, n, False, False, self.smooth)
            self.opt("Node20_neckerchief", 3)
        if "grease" in ex:
            for i, (gx, gy) in enumerate(((-4.0, 131.0), (3.5, 117.0))):
                rect = self.A.tile(f"stain{i}", 8, 8, paint_rows(STAIN_ROWS, pal_bg(self.p["cols"]["top"], d=self.p["cols"]["grime"])))
                xs = [gx - 2.5 + 5.0 * j / 3 for j in range(4)] if human else [gx - 2.5, gx + 2.5]
                decal_curved(m, "Node10_torso", rect, xs, gy - 2.5, gy + 2.5, lambda x, gy=gy: self.tz(gy, x), True)

    # ----- danni dello zombie (decalcomanie su busto)
    def zombie_decals(self):
        for i, d in enumerate(self.p["decals"]):
            seed = self.p["seed"] * 31 + i
            BLOB_SKIN[0] = shade(self.p["cols"]["skin"], 1.05)
            rect = self.A.tile(f"{d['k']}{i}", 8, 8, paint_blob(d["k"], self.p["cols"]["top"], seed))
            w = d["w"]
            xs = [d["x"] - w / 2, d["x"] + w / 2]
            decal_curved(self.m, "Node10_torso", rect, xs, d["y"] - w / 2, d["y"] + w / 2,
                         lambda x, d=d: self.tz(d["y"], x, d["front"]), d["front"], 0.14 + 0.01 * i)


# ---------------------------------------------------------------------------------------------
# Generazione: sceglie il livello di dettaglio piu' alto che rientra nel budget
# ---------------------------------------------------------------------------------------------
def generate(spec):
    plan = make_plan(spec)
    budget = plan["budget"]
    top = 11 if plan["human"] else 3
    cache = {}

    def build(lv):
        if lv not in cache:
            cache[lv] = Build(plan, lv)
        return cache[lv]

    lo, hi, best = 0, top, 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if len(build(mid).m.tris) <= budget:
            best, lo = mid, mid + 1
        else:
            hi = mid - 1
    b = build(best)
    removed = b.m.trim_to(budget)
    return {"plan": plan, "build": b, "mesh": b.m, "atlas": b.A, "level": best, "tris": len(b.m.tris),
            "budget": budget, "removed": removed, "pivots": b.pivots, "name": char_name(plan)}


def char_name(plan):
    t = plan["sub"] or plan["type"]
    return f"{'umano' if plan['human'] else 'zombie'}_{t}_{'f' if plan['sex'] == 'f' else 'm'}_{plan['seed']:04d}"


def info_for(r):
    p = r["plan"]
    L = [f"tipo: {'umano' if p['human'] else 'zombie'} / {p['type']}" + (f" / {p['sub']}" if p["sub"] else ""),
         f"sesso: {'femmina' if p['sex'] == 'f' else 'maschio'}   pelle: {p['skin_name']}   seed: {p['seed']}",
         f"capelli: {p['hair_name']} ({ {'short': 'corti', 'long': 'lunghi', 'tail': 'codino'}.get(p['hair_style'], p['hair_style']) })   occhi: {p['eye_name']}",
         f"triangoli: {r['tris']} (limite {r['budget']})   livello di dettaglio: {r['level']}",
         f"texture: {r['atlas'].size}x{r['atlas'].size}   unita' del rig, Y su, fronte +Z, +X = lato sinistro"]
    if p["human"]:
        L.append(f"palpebre (Node24/Node26): chiusura = rotazione attorno a X di ~{getattr(r['build'], 'lid_angle', 20):.0f} gradi sul pivot indicato")
        L.append("occhi (Eye_L/Eye_R): solo l'iride si muove; il bianco e' nel gruppo Node22_eyewhite (fisso)")
        L.append("mandibola (Node27): apertura = rotazione attorno a X sul pivot di Node27 (8-14 gradi). La pelle tra testa e")
        L.append("  mandibola e' continua (vertici condivisi) tranne il taglio della bocca: sfuma i pesi verso le orecchie")
    if r["removed"]:
        L.append("tolti per il budget: " + ", ".join(r["removed"]))
    return L


def expression_rules(r, brow=0.6):
    """Pose rigide di prova (palpebre, sopracciglia). La mandibola si apre con jaw_open_soft."""
    pv = r["pivots"]
    lid = getattr(r["build"], "lid_angle", 20.0)
    rules = []
    for g, nm in (("Node24", "Node24_eyelid_L"), ("Node26", "Node26_eyelid_R")):
        rules.append((g, pv[nm], "x", lid, (0, 0, 0)))
    for g in ("Node23", "Node25"):
        rules.append((g, (0, 0, 0), "x", 0.0, (0, brow, 0)))
    return rules


def jaw_open_soft(m, seam, deg=11.0):
    """Apre la mandibola con pesi sfumati (come un weight paint): davanti pesa 1, verso le orecchie scende a 0,
    i vertici della giuntura restano con la testa tranne quelli del taglio della bocca."""
    pv = np.asarray(J["Node27"], float)
    out = Mesh()
    out.prio = dict(m.prio)

    def weight(g, p):
        if g.startswith("Node27_jaw_"):
            return 1.0
        if not g.startswith("Node27_jaw"):
            return 0.0
        if seam - 0.01 < p[1] < seam - 0.001:          # taglio della bocca
            return 1.0
        if abs(p[1] - seam) < 1e-4:                     # giuntura condivisa con la testa
            return 0.0
        wz = min(1.0, max(0.0, (p[2] + 1.0) / 6.0))
        wz = wz * wz * (3 - 2 * wz)
        wy = min(1.0, max(0.0, (seam - p[1]) / 0.9))
        return wz * min(1.0, 0.35 + wy)

    for g, pts, uvs, nr in m.tris:
        if g.startswith("Node27"):
            np_, nn_ = [], []
            for p, n in zip(pts, nr):
                R = _rot_matrix("x", deg * weight(g, p))
                np_.append(R @ (np.asarray(p) - pv) + pv)
                nn_.append(R @ np.asarray(n))
            out.tris.append((g, tuple(np_), uvs, tuple(nn_)))
        else:
            out.tris.append((g, pts, uvs, nr))
    return out


def preview_images(r, expressions=True):
    """Ritorna {nome: array RGB}."""
    m, tex = r["mesh"], r["atlas"].img
    out = {"sheet": render_sheet(m, tex)}
    if r["plan"]["human"]:
        out["head"] = render_head(m, tex, yaws=(0, 35, 90), W=300, H=300)
        if expressions:
            ex = jaw_open_soft(posed(m, expression_rules(r)), r["build"].mouth_seam)
            out["expression"] = render_head(ex, tex, yaws=(0, 35), W=300, H=300)
    else:
        out["head"] = render_head(m, tex, yaws=(0, 35), W=300, H=300)
    return out


def save_character(r, outdir, previews=True, fbx=False, blender=None):
    folder = os.path.join(outdir, r["name"])
    info = info_for(r)
    if fbx:
        info += [f"FBX: armatura Node0 con le ossa del BVH ({SKEL_SOURCE[0]}), pesi automatici, texture incorporata.",
                 "  In Blender: File > Import > FBX con le impostazioni predefinite (Automatic Bone Orientation spento)."]
    write_obj(r["mesh"], folder, r["name"], r["atlas"], r["pivots"], info)
    files = [os.path.join(folder, r["name"] + e) for e in (".obj", ".mtl", "_tex.png", "_gruppi.txt")]
    data = None
    if fbx:
        fpath, data = export_fbx(r, folder, blender)
        files.append(fpath)
    if previews:
        imgs = preview_images(r)
        if fbx:
            pm = posed_mesh(data, TEST_POSE)
            imgs["rig_pose"] = render_sheet(pm, r["atlas"].img, views=(0, 35, 90, 160))
        for k, img in imgs.items():
            pth = os.path.join(folder, f"{r['name']}_prev_{k}.png")
            write_png(pth, img)
            files.append(pth)
    return folder, files


# ---------------------------------------------------------------------------------------------
# Rig: ossa dal BVH, pesi automatici, export FBX tramite Blender
# ---------------------------------------------------------------------------------------------
# Ogni osso ha la testa sul joint del BVH e la coda in verticale (+Y del gioco), con roll 0: la sua
# orientazione a riposo coincide con gli assi del gioco, come nel BVH. Cosi' le rotazioni di un .mot o
# di un BVH si applicano agli stessi assi. Le ossa non sono collegate (use_connect = False).
BLEND_CANDIDATES = {
    "Node3": ("Node3", "Node10", "Node4", "Node7"),
    "Node10": ("Node3", "Node10", "Node11", "Node12", "Node16", "Node20"),
    "Node11": ("Node3", "Node10", "Node11", "Node12", "Node16", "Node20"),
    "Node12": ("Node11", "Node12", "Node13"), "Node16": ("Node11", "Node16", "Node17"),
    "Node13": ("Node11", "Node12", "Node13", "Node14"), "Node17": ("Node11", "Node16", "Node17", "Node18"),
    "Node14": ("Node13", "Node14", "Node15"), "Node18": ("Node17", "Node18", "Node19"),
    "Node15": ("Node14", "Node15"), "Node19": ("Node18", "Node19"),
    "Node4": ("Node3", "Node4", "Node5"), "Node7": ("Node3", "Node7", "Node8"),
    "Node5": ("Node4", "Node5", "Node6"), "Node8": ("Node7", "Node8", "Node9"),
    "Node6": ("Node5", "Node6"), "Node9": ("Node8", "Node9"),
    "Node20": ("Node11", "Node20", "Node21"),
}
OWN_BONE_BOOST = 2.0                       # l'osso del gruppo pesa un po' di piu' degli altri candidati


def bone_segment(b):
    """Segmento (inizio, fine) usato per misurare la distanza di un vertice da un osso."""
    p = J[b]
    sx = 1.0 if p[0] >= 0 else -1.0
    ends = {"Node3": lambda: (J["Node4"] + J["Node7"]) / 2.0, "Node10": lambda: J["Node11"], "Node11": lambda: J["Node20"],
            "Node12": lambda: J["Node13"], "Node16": lambda: J["Node17"], "Node13": lambda: J["Node14"],
            "Node17": lambda: J["Node18"], "Node14": lambda: J["Node15"], "Node18": lambda: J["Node19"],
            "Node15": lambda: p + np.array([sx * 5.0, 0, 0]), "Node19": lambda: p + np.array([sx * 5.0, 0, 0]),
            "Node4": lambda: J["Node5"], "Node7": lambda: J["Node8"], "Node5": lambda: J["Node6"], "Node8": lambda: J["Node9"],
            "Node6": lambda: np.array([p[0], 3.0, 13.5]), "Node9": lambda: np.array([p[0], 3.0, 13.5]),
            "Node20": lambda: J["Node21"], "Node21": lambda: p + np.array([0, 16.0, 0])}
    return p, (ends[b]() if b in ends else p + np.array([0, 1.0, 0]))


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-9), 0.0, 1.0)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def group_bone(g):
    """Osso principale di un gruppo dell'OBJ (Eye_L/Eye_R -> Node22)."""
    if g.startswith("Eye_"):
        return "Node22"
    head = g.split("_")[0]
    return head if head in J else "Node21"


BODY_PARTS = ("_torso", "_hips", "_upperarm_L", "_upperarm_R", "_forearm_L", "_forearm_R", "_thigh_L", "_thigh_R",
              "_shin_L", "_shin_R", "_neck", "_hand_L", "_hand_R", "_foot_L", "_foot_R")


def is_body_group(g):
    """Pelle/superficie principale del corpo (non un vestito sovrapposto o un accessorio)."""
    return g.startswith("Node") and g[g.index("_"):] in BODY_PARTS if "_" in g else False


def rig_bones():
    """[(nome, genitore, testa, coda)] nell'ordine della gerarchia (genitore prima del figlio)."""
    names = [n for n in SKEL_PARENTS if n in J]
    order, seen = [], set()

    def visit(n):
        if n in seen:
            return
        par = SKEL_PARENTS.get(n)
        if par in J and par in SKEL_PARENTS:
            visit(par)
        seen.add(n)
        order.append(n)
    for n in names:
        visit(n)
    out = []
    for n in order:
        par = SKEL_PARENTS.get(n)
        head = np.asarray(J[n], float)
        kids = [k for k in order if SKEL_PARENTS.get(k) == n]
        if n == "Node1" and "Node2" in J and J["Node2"][1] - head[1] > 1.0:
            length = float(J["Node2"][1] - head[1])         # Node1 -> Node2: la coda di Node1 e' la testa di Node2
        elif n in ("Node22", "Node23", "Node24", "Node25", "Node26", "Node27") or not kids:
            length = 1.5
        else:
            length = 4.0
        out.append((n, par if par in J else None, head, head + np.array([0.0, length, 0.0])))
    return out


def rig_weights(r):
    """Mesh a vertici unici con i pesi per osso. Ritorna un dict pronto per Blender."""
    m = r["mesh"]
    key = lambda p: tuple(np.round(np.asarray(p, float), 4))
    vidx, verts, vgroups = {}, [], []
    loops, uvs, nrms, tri_group = [], [], [], []
    for g, pts, uv, nr in m.tris:
        face = []
        for p in pts:
            k = key(p)
            if k not in vidx:
                vidx[k] = len(verts)
                verts.append(np.asarray(p, float))
                vgroups.append([])
            i = vidx[k]
            if g not in vgroups[i]:
                vgroups[i].append(g)
            face.append(i)
        loops.append(face)
        uvs.append([list(map(float, u)) for u in uv])
        nrms.append([list(map(float, n)) for n in nr])
        tri_group.append(g)
    V = np.array(verts)
    nv = len(V)
    W = [dict() for _ in range(nv)]
    blend = np.zeros(nv, bool)
    seam = getattr(r["build"], "mouth_seam", None)

    def jaw_w(g, p):
        if g.startswith("Node27_jaw_"):
            return 1.0
        if seam is None:
            return 1.0
        if seam - 0.01 < p[1] < seam - 0.001:
            return 1.0
        if abs(p[1] - seam) < 1e-4:
            return 0.0
        wz = min(1.0, max(0.0, (p[2] + 1.0) / 6.0))
        wz = wz * wz * (3 - 2 * wz)
        wy = min(1.0, max(0.0, (seam - p[1]) / 0.9))
        return wz * min(1.0, 0.35 + wy)

    # 1) parti rigide (testa, viso, dita) e mandibola
    for i in range(nv):
        gs = vgroups[i]
        rigid = [g for g in gs if group_bone(g) not in BLEND_CANDIDATES]
        if not rigid:
            blend[i] = True
            continue
        g = sorted(rigid)[0]
        b = group_bone(g)
        if g.startswith("Node22_eyewhite"):
            b = "Node21"                                  # il bianco resta fermo con la testa, l'iride va con Node22
        if b == "Node27" and "Node21" in J:
            w = jaw_w(g, V[i]) if all(x.startswith("Node27") for x in gs) else 0.0
            if w > 0:
                W[i]["Node27"] = w
            if w < 1:
                W[i]["Node21"] = 1.0 - w
        else:
            W[i][b] = 1.0
    # 2) corpo saldato e vestiti: distanza dai segmenti delle ossa candidate della regione
    segs = {b: bone_segment(b) for b in set(sum((list(v) for v in BLEND_CANDIDATES.values()), [])) if b in J}
    idx = np.nonzero(blend)[0]
    if len(idx):
        by_cand = {}
        for i in idx:
            own = group_bone(sorted(vgroups[i])[0])
            cands = tuple(sorted(set(sum((list(BLEND_CANDIDATES[group_bone(g)]) for g in vgroups[i]), []))))
            by_cand.setdefault((cands, own), []).append(i)
        for (cands, own), ids in by_cand.items():
            ids = np.array(ids)
            P = V[ids]
            cs = [b for b in cands if b in segs]
            D = np.stack([_seg_dist(P, *segs[b]) for b in cs], axis=1)
            Wm = 1.0 / (D * D + 0.25) ** 2
            for j, b in enumerate(cs):
                if b == own:
                    Wm[:, j] *= OWN_BONE_BOOST
            Wm /= Wm.sum(axis=1, keepdims=True)
            for row, i in enumerate(ids):
                W[i] = {b: float(Wm[row, j]) for j, b in enumerate(cs)}
        # levigatura sulla mesh saldata (solo tra vertici del corpo)
        nb = [set() for _ in range(nv)]
        for a, b, c in loops:
            for x, y in ((a, b), (b, c), (c, a)):
                if blend[x] and blend[y]:
                    nb[x].add(y)
                    nb[y].add(x)
        for _ in range(2):
            new = []
            for i in range(nv):
                if not blend[i] or not nb[i]:
                    new.append(W[i])
                    continue
                acc = {b: 0.5 * w for b, w in W[i].items()}
                k = 0.5 / len(nb[i])
                for j in nb[i]:
                    for b, w in W[j].items():
                        acc[b] = acc.get(b, 0.0) + k * w
                new.append(acc)
            W = new
        # accessori e vestiti sovrapposti (orli, colletto, cintura, giacca, decalcomanie, spalline...):
        # copiano i pesi della pelle piu' vicina, cosi' si muovono insieme alla superficie sotto
        body = np.array([blend[i] and all(is_body_group(g) for g in vgroups[i]) for i in range(nv)])
        over = np.nonzero(blend & ~body)[0]
        bidx = np.nonzero(body)[0]
        if len(over) and len(bidx):
            BV = V[bidx]
            for s in range(0, len(over), 256):
                chunk = over[s:s + 256]
                d2 = ((V[chunk][:, None, :] - BV[None, :, :]) ** 2).sum(axis=2)
                k = 3
                part = np.argpartition(d2, k, axis=1)[:, :k]
                for row, i in enumerate(chunk):
                    acc, tot = {}, 0.0
                    for j in part[row]:
                        wj = 1.0 / (d2[row, j] + 0.05)
                        tot += wj
                        for b, w in W[bidx[j]].items():
                            acc[b] = acc.get(b, 0.0) + wj * w
                    W[i] = {b: w / tot for b, w in acc.items()}
        # gonna e camice: davanti e dietro, al centro tra le gambe, il tessuto segue la media delle due cosce
        for i in over:
            if not any(g in ("Node3_skirt", "Node3_coat") for g in vgroups[i]):
                continue
            wd = W[i]
            legs = sum(wd.get(b, 0.0) for b in ("Node4", "Node5", "Node6", "Node7", "Node8", "Node9"))
            if legs <= 0:
                continue
            fl = 0.5 + 0.5 * max(-1.0, min(1.0, V[i][0] / 7.0))        # +X = gamba sinistra (Node4)
            rest = {b: w for b, w in wd.items() if b not in ("Node4", "Node5", "Node6", "Node7", "Node8", "Node9")}
            rest["Node4"] = rest.get("Node4", 0.0) + legs * fl
            rest["Node7"] = rest.get("Node7", 0.0) + legs * (1.0 - fl)
            W[i] = rest
    # 3) al massimo 4 ossa per vertice, pesi < 1% tolti, somma 1
    for i in range(nv):
        top = sorted(W[i].items(), key=lambda kv: -kv[1])[:4]
        top = [(b, w) for b, w in top if w >= 0.01] or top[:1]
        s = sum(w for _, w in top)
        W[i] = {b: w / s for b, w in top}
    groups = {}
    for i, wd in enumerate(W):
        for b, w in wd.items():
            groups.setdefault(b, []).append([i, round(w, 5)])
    bones = [{"name": n, "parent": p, "head": [float(x) for x in h], "tail": [float(x) for x in t]} for n, p, h, t in rig_bones()]
    return {"name": r["name"], "verts": V.tolist(), "tris": loops, "uv": uvs, "normals": nrms, "tri_group": tri_group,
            "weights": groups, "bones": bones, "flat": not r["plan"]["human"], "armature": "Node0",
            "skeleton": SKEL_SOURCE[0]}


def deform_rig(data, pose):
    """Skinning lineare dei vertici con una posa {osso: (asse, gradi)} (rotazioni locali, assi del gioco).
    Serve per l'anteprima e per i controlli; Blender fa lo stesso calcolo."""
    bones = {b["name"]: b for b in data["bones"]}
    order = [b["name"] for b in data["bones"]]
    M = {}
    for n in order:
        b = bones[n]
        h = np.array(b["head"])
        R = np.eye(3)
        if n in pose:
            ax, deg = pose[n]
            R = _rot_matrix(ax, deg)
        L = np.eye(4)
        L[:3, :3] = R
        L[:3, 3] = h - R @ h                              # rotazione attorno alla testa
        par = b["parent"]
        M[n] = (M[par] @ L) if par in M else L
    V = np.array(data["verts"])
    Vh = np.c_[V, np.ones(len(V))]
    out = np.zeros_like(V)
    for b, lst in data["weights"].items():
        if b not in M:
            continue
        ii = np.array([e[0] for e in lst])
        ww = np.array([e[1] for e in lst])
        out[ii] += ww[:, None] * (Vh[ii] @ M[b].T)[:, :3]
    return out, M


def posed_mesh(data, pose):
    """Mesh (per il renderer di anteprima) deformata con deform_rig."""
    P, M = deform_rig(data, pose)
    nv = len(data["verts"])
    dom, dw = [None] * nv, [-1.0] * nv                    # osso piu' pesante di ogni vertice (per ruotare le normali)
    for b, lst in data["weights"].items():
        for i, w in lst:
            if w > dw[i]:
                dom[i], dw[i] = b, w
    out = Mesh()
    for t, (a, b, c) in enumerate(data["tris"]):
        pts = (P[a], P[b], P[c])
        fn = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        ln = np.linalg.norm(fn)
        if ln < 1e-12:
            continue
        fn = fn / ln
        if data["flat"]:
            nr = (fn, fn, fn)
        else:
            nr = []
            for k, vi in enumerate((a, b, c)):
                R = M[dom[vi]][:3, :3] if dom[vi] in M else np.eye(3)
                n = R @ np.array(data["normals"][t][k])
                nr.append(n / (np.linalg.norm(n) + 1e-12))
        out.tris.append((data["tri_group"][t], pts, tuple(tuple(u) for u in data["uv"][t]), tuple(nr)))
    return out


TEST_POSE = {"Node13": ("z", -62.0), "Node17": ("z", 62.0), "Node14": ("y", 28.0), "Node18": ("y", -28.0),
             "Node4": ("x", -32.0), "Node5": ("x", 48.0), "Node7": ("x", 14.0), "Node8": ("x", 10.0),
             "Node10": ("y", 10.0), "Node11": ("x", 8.0), "Node21": ("y", -22.0), "Node27": ("x", 12.0)}


# ----- lato Blender -------------------------------------------------------------------------
def blender_build(json_path, fbx_path, blend_path=None):
    """Eseguito DENTRO Blender (blender -b --python character_gen.py -- --blender-build dati.json uscita.fbx)
    oppure con il modulo bpy. Crea armatura, mesh, gruppi di vertici, materiale ed esporta l'FBX."""
    import json
    import bpy
    with open(json_path) as fh:
        d = json.load(fh)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    scn.render.fps = 60
    # armatura (dati nello spazio del gioco, Y su; l'oggetto e' ruotato di 90 gradi su X per stare in piedi in Blender)
    arm_data = bpy.data.armatures.new(d["armature"])
    arm = bpy.data.objects.new(d["armature"], arm_data)
    scn.collection.objects.link(arm)
    arm.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    arm_data.display_type = 'STICK'
    arm.show_in_front = True
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = {}
    for b in d["bones"]:
        eb = arm_data.edit_bones.new(b["name"])
        eb.head = b["head"]
        eb.tail = b["tail"]
        eb.roll = 0.0
        eb.use_connect = False
        eb.use_deform = True
        ebs[b["name"]] = eb
    for b in d["bones"]:
        if b["parent"] and b["parent"] in ebs:
            ebs[b["name"]].parent = ebs[b["parent"]]
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
    # mesh
    me = bpy.data.meshes.new(d["name"])
    me.from_pydata([tuple(v) for v in d["verts"]], [], [tuple(t) for t in d["tris"]])
    me.validate(clean_customdata=False)
    uvl = me.uv_layers.new(name="UVMap")
    flat_uv = [u for tri in d["uv"] for u in tri]
    for li, lp in enumerate(me.loops):
        uvl.data[li].uv = flat_uv[li]
    for poly in me.polygons:
        poly.use_smooth = not d["flat"]
    if not d["flat"]:
        me.normals_split_custom_set([tuple(n) for tri in d["normals"] for n in tri])
    ob = bpy.data.objects.new(d["name"], me)
    scn.collection.objects.link(ob)
    ob.parent = arm
    for bname, lst in d["weights"].items():
        vg = ob.vertex_groups.new(name=bname)
        for i, w in lst:
            vg.add([i], w, 'REPLACE')
    for b in d["bones"]:                                  # un gruppo (anche vuoto) per ogni osso, come nei rig del gioco
        if b["name"] not in ob.vertex_groups:
            ob.vertex_groups.new(name=b["name"])
    mod = ob.modifiers.new("Armature", 'ARMATURE')
    mod.object = arm
    # materiale con la texture (filtro "Closest", pixel netti come nel gioco)
    mat = bpy.data.materials.new(d["name"] + "_mat")
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    for k, v in (("Roughness", 1.0), ("Specular IOR Level", 0.0), ("Specular", 0.0)):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    tex_path = os.path.join(os.path.dirname(os.path.abspath(json_path)), d["name"] + "_tex.png")
    img = bpy.data.images.load(tex_path)
    tn = nt.nodes.new('ShaderNodeTexImage')
    tn.image = img
    tn.interpolation = 'Closest'
    nt.links.new(tn.outputs["Color"], bsdf.inputs["Base Color"])
    me.materials.append(mat)
    # export
    bpy.ops.object.select_all(action='DESELECT')
    arm.select_set(True)
    ob.select_set(True)
    bpy.ops.export_scene.fbx(filepath=fbx_path, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', global_scale=1.0,
                             axis_forward='-Z', axis_up='Y', add_leaf_bones=False, primary_bone_axis='Y',
                             secondary_bone_axis='X', use_armature_deform_only=False, bake_anim=False,
                             mesh_smooth_type='OFF' if d["flat"] else 'FACE', use_mesh_modifiers=False,
                             path_mode='COPY', embed_textures=True, use_custom_props=False)
    if blend_path:
        img.pack()
        bpy.ops.wm.save_as_mainfile(filepath=blend_path, compress=True)
    return fbx_path


def find_blender(hint=None):
    """Comando per eseguire blender_build: Blender installato, oppure questo Python se ha il modulo bpy."""
    import glob
    import importlib.util
    import shutil
    cands = []
    if hint:
        cands.append(hint)
    env = os.environ.get("BLENDER")
    if env:
        cands.append(env)
    w = shutil.which("blender")
    if w:
        cands.append(w)
    pats = [r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
            r"C:\Program Files (x86)\Blender Foundation\Blender*\blender.exe",
            os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Steam\steamapps\common\Blender\blender.exe"),
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
            "/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender", "/snap/bin/blender"]
    for p in pats:
        cands += sorted(glob.glob(p), reverse=True)
    for c in cands:
        if c and os.path.isfile(c):
            return ("blender", c)
    if importlib.util.find_spec("bpy") is not None:
        return ("bpy", sys.executable)
    return None


def export_fbx(r, folder, blender=None, keep_json=False):
    """Scrive <nome>.fbx (mesh + armatura Node0 + pesi + texture incorporata) nella cartella del personaggio."""
    import json
    import subprocess
    runner = find_blender(blender)
    if runner is None:
        raise RuntimeError("Per l'FBX serve Blender: non l'ho trovato. Indica il percorso di blender.exe "
                           "(campo 'Blender' nella GUI o --blender da riga di comando).")
    data = rig_weights(r)
    jpath = os.path.join(folder, r["name"] + "_rig.json")
    fpath = os.path.join(folder, r["name"] + ".fbx")
    with open(jpath, "w") as fh:
        json.dump(data, fh)
    me = os.path.abspath(__file__)
    if runner[0] == "blender":
        cmd = [runner[1], "-b", "--factory-startup", "--python", me, "--", "--blender-build", jpath, fpath]
    else:
        cmd = [runner[1], me, "--blender-build", jpath, fpath]
    if os.path.exists(fpath):
        os.remove(fpath)
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if not keep_json:
        try:
            os.remove(jpath)
        except OSError:
            pass
    if not os.path.isfile(fpath):
        tail = "\n".join((res.stdout + "\n" + res.stderr).strip().splitlines()[-12:])
        raise RuntimeError("Blender non ha creato l'FBX.\n" + tail)
    return fpath, data


# ---------------------------------------------------------------------------------------------
# Controlli automatici
# ---------------------------------------------------------------------------------------------
HUMAN_GROUPS = ("Eye_L", "Eye_R", "Node23_eyebrow_L", "Node25_eyebrow_R", "Node24_eyelid_L", "Node26_eyelid_R", "Node27_jaw")


JOINT_GROUPS = ("Node10_torso", "Node13_upperarm", "Node17_upperarm", "Node14_forearm", "Node18_forearm",
                "Node3_hips", "Node4_thigh", "Node7_thigh", "Node5_shin", "Node8_shin")


def weld_errors(m):
    """Bordi aperti o spigoli doppi alle giunture braccia-torso, gambe-bacino, gomiti e ginocchia."""
    tris = [t for t in m.tris if t[0].startswith(JOINT_GROUPS) and "_hem" not in t[0]]
    keys = [[tuple(np.round(p, 4)) for p in t[1]] for t in tris]
    par = {}

    def f(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for ks in keys:
        for k in ks[1:]:
            par[f(k)] = f(ks[0])
    size = {}
    for ks in keys:
        size[f(ks[0])] = size.get(f(ks[0]), 0) + 1
    cnt = {}
    for ks in keys:
        if size[f(ks[0])] < 30:                      # decalcomanie: pezzi separati per costruzione
            continue
        for i in range(3):
            e = tuple(sorted((ks[i], ks[(i + 1) % 3])))
            cnt[e] = cnt.get(e, 0) + 1

    def expected(e):                                 # bordi aperti previsti: collo, polsi, caviglie, vita
        p = (np.array(e[0]) + np.array(e[1])) / 2
        return (p[1] > 146.0 and abs(p[0]) < 6.5) or abs(p[0]) > 60 or p[1] < 14 or (110.5 < p[1] < 113.2 and abs(p[0]) < 12.5)
    opened = sum(1 for e, n in cnt.items() if n == 1 and not expected(e))
    doubled = sum(1 for e, n in cnt.items() if n > 2)
    return opened, doubled


def check_result(r):
    errs = []
    p, m = r["plan"], r["mesh"]
    if r["tris"] > r["budget"]:
        errs.append(f"budget superato {r['tris']}>{r['budget']}")
    if p["human"]:
        grp = m.groups()
        for g in HUMAN_GROUPS:
            if g not in grp:
                errs.append("manca il gruppo " + g)
        if r["tris"] < r["budget"] * 0.6:
            errs.append(f"umano troppo povero: {r['tris']} su {r['budget']}")
    if p["hair_style"] not in (None, "none") and "Node21_hair" in r["removed"]:
        errs.append("capelli tolti per il budget")
    op, nm = weld_errors(m)
    if op or nm:
        errs.append(f"giunture: {op} bordi aperti, {nm} spigoli doppi")
    P, N, UV = m.pack()
    if not np.isfinite(P).all():
        errs.append("vertici non finiti")
    if UV.min() < -1e-6 or UV.max() > 1 + 1e-6:
        errs.append("UV fuori da 0..1")
    if np.abs(np.linalg.norm(N, axis=2) - 1).max() > 1e-3:
        errs.append("normali non unitarie")
    errs += rig_errors(r)
    return errs


def rig_errors(r):
    """Pesi: ogni vertice pesato, somma 1, al massimo 4 ossa, ossa esistenti; posa di prova senza esplosioni."""
    errs = []
    d = rig_weights(r)
    nv = len(d["verts"])
    s = np.zeros(nv)
    cnt = np.zeros(nv, int)
    names = {b["name"] for b in d["bones"]}
    for b, lst in d["weights"].items():
        if b not in names:
            errs.append(f"peso su un osso che non esiste: {b}")
        for i, w in lst:
            s[i] += w
            cnt[i] += 1
    if (cnt == 0).any():
        errs.append(f"{int((cnt == 0).sum())} vertici senza pesi")
    if np.abs(s - 1).max() > 1e-3:
        errs.append("pesi che non sommano a 1")
    if cnt.max() > 4:
        errs.append("piu' di 4 ossa su un vertice")
    P, _ = deform_rig(d, TEST_POSE)
    V = np.array(d["verts"])
    if not np.isfinite(P).all():
        errs.append("posa di prova non finita")
    else:
        # nella posa di prova nessun triangolo deve allungarsi in modo assurdo (pesi sbagliati = punte e strappi)
        T = np.array(d["tris"])
        e0 = np.linalg.norm(V[T[:, 1]] - V[T[:, 0]], axis=1) + np.linalg.norm(V[T[:, 2]] - V[T[:, 1]], axis=1)
        e1 = np.linalg.norm(P[T[:, 1]] - P[T[:, 0]], axis=1) + np.linalg.norm(P[T[:, 2]] - P[T[:, 1]], axis=1)
        bad = int((e1 > 3.0 * e0 + 1.0).sum())
        if bad:
            errs.append(f"posa di prova: {bad} triangoli stirati")
    return errs


def run_checks(verbose=True):
    bad = 0
    combos = []
    for kind in ("umano", "zombie"):
        for sex in ("maschio", "femmina"):
            for typ, sub in (("poliziotto", None), ("civile", None), ("lavoratore", "infermiere"), ("lavoratore", "dottore"),
                             ("lavoratore", "cuoco"), ("lavoratore", "meccanico")):
                combos.append((kind, sex, typ, sub))
    for kind, sex, typ, sub in combos:
        for skin in ("bianco", "nero"):
            for q in (("low", "medium", "high") if kind == "umano" else ("-",)):
                hs = HAIRSTYLES[(len(typ) + len(skin) + len(q)) % 4]
                sp = Spec(kind, sex, typ, sub or "random", skin, quality=q if q != "-" else "medium", seed=3, hairstyle=hs)
                r = generate(sp)
                e = check_result(r)
                if verbose:
                    print(("OK  " if not e else "ERR ") + f"{kind:6} {sex:7} {typ}/{sub or '-':10} {skin:6} {q:6} tris={r['tris']:5}/{r['budget']} lv={r['level']} {e or ''}")
                bad += bool(e)
    a, b = generate(Spec(seed=5)), generate(Spec(seed=5))
    same = a["tris"] == b["tris"] and all(np.allclose(x[1], y[1]) for x, y in zip(a["mesh"].tris, b["mesh"].tris))
    if verbose:
        print("determinismo per seed:", "OK" if same else "ERRORE")
    bad += (0 if same else 1)
    # guardaroba civile: ogni valore di gambe/busto/calzature provato almeno una volta
    bst_l = [s for s in BOTTOM_STYLES if s != "random"]
    top_l = [s for s in TOP_STYLES if s != "random"]
    foo_l = [s for s in FOOT_STYLES if s != "random"]
    n = max(len(bst_l), len(top_l), len(foo_l))
    wardrobe = [(bst_l[i % len(bst_l)], top_l[i % len(top_l)], foo_l[i % len(foo_l)]) for i in range(n)]
    for kind in ("umano", "zombie"):
        for sex in ("maschio", "femmina"):
            for bst, tps, foo in wardrobe:
                sp = Spec(kind, sex, "civile", skin="bianco", quality="medium", seed=11,
                          bottom_style=bst, top_style=tps, footwear=foo)
                r = generate(sp)
                e = check_result(r)
                if verbose:
                    print(("OK  " if not e else "ERR ") + f"{kind:6} {sex:7} civile {bst}/{tps}/{foo} tris={r['tris']:5}/{r['budget']} {e or ''}")
                bad += bool(e)
    return bad


# ---------------------------------------------------------------------------------------------
# Riga di comando
# ---------------------------------------------------------------------------------------------
def norm_sex(s):
    return "femmina" if str(s).lower().startswith("f") else "maschio"


def parse_args(argv):
    ap = argparse.ArgumentParser(description="Generatore di umani e zombie low-poly per RE Outbreak (OBJ + MTL + PNG)")
    ap.add_argument("--kind", default="umano", choices=["umano", "zombie"])
    ap.add_argument("--sex", default="maschio", choices=["maschio", "femmina", "m", "f"])
    ap.add_argument("--type", default="poliziotto", choices=list(TYPES))
    ap.add_argument("--sub", default="random", choices=["random"] + list(SUBS))
    ap.add_argument("--skin", default="random", choices=["random", "bianco", "nero"])
    ap.add_argument("--hair", default="random", help="random | " + " | ".join(HAIR_COL) + " | #rrggbb")
    ap.add_argument("--eyes", default="random", help="random | " + " | ".join(EYE_COL) + " | #rrggbb")
    ap.add_argument("--hairstyle", default="random", choices=list(HAIRSTYLES), help="taglio di capelli")
    ap.add_argument("--bottom", default="random", choices=list(BOTTOM_STYLES), help="vestiti gambe (solo civile)")
    ap.add_argument("--top", default="random", choices=list(TOP_STYLES), help="vestiti busto (solo civile)")
    ap.add_argument("--footwear", default="random", choices=list(FOOT_STYLES), help="calzature (solo civile)")
    ap.add_argument("--quality", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--tris", type=int, default=None, help="tetto triangoli (umani 1500..9000, zombie 150..500)")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--out", default="output_personaggi")
    ap.add_argument("--skeleton", default=None, help="BVH in T-pose per leggere le posizioni dei joint")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--fbx", action="store_true", help="esporta anche l'FBX riggato (armatura Node0 + pesi), serve Blender")
    ap.add_argument("--blender", default=None, help="percorso di blender.exe (se non lo trovo da solo)")
    ap.add_argument("--check", action="store_true", help="prova tutte le combinazioni")
    ap.add_argument("--gui", action="store_true")
    return ap.parse_args(argv)


def cli(argv):
    a = parse_args(argv)
    if a.skeleton:
        load_skeleton(a.skeleton)
    if a.check:
        return 1 if run_checks() else 0
    if a.fbx and find_blender(a.blender) is None:
        print("Per --fbx serve Blender e non l'ho trovato: indica il percorso con --blender \"C:\\...\\blender.exe\"")
        return 1
    base = a.seed if a.seed is not None else random.randrange(1, 9000)
    for i in range(max(1, a.count)):
        sp = Spec(a.kind, norm_sex(a.sex), a.type, a.sub, a.skin, a.hair, a.eyes, a.quality, a.tris, base + i, a.hairstyle,
                  a.bottom, a.top, a.footwear)
        r = generate(sp)
        folder, files = save_character(r, a.out, not a.no_preview, a.fbx, a.blender)
        print(f"{r['name']}: {r['tris']} triangoli (limite {r['budget']}) -> {folder}" + ("  [+ FBX]" if a.fbx else ""))
    return 0


# ---------------------------------------------------------------------------------------------
# Interfaccia grafica (tkinter)
# ---------------------------------------------------------------------------------------------
def gui():
    import base64
    import queue
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Generatore personaggi - RE Outbreak")
    V = {k: tk.StringVar(value=v) for k, v in dict(kind="umano", sex="maschio", type="poliziotto", sub="random",
                                                   skin="random", hair="random", eyes="random", quality="medium", hairstyle="random",
                                                   bottom="random", top="random", footwear="random",
                                                   seed="", count="1", out=os.path.abspath("output_personaggi"),
                                                   skel="", blender="").items()}
    found = find_blender()
    if found and found[0] == "blender":
        V["blender"].set(found[1])
    want_fbx = tk.BooleanVar(value=found is not None)
    frm = ttk.Frame(root, padding=10)
    frm.grid(row=0, column=0, sticky="nsew")
    rows = [("Tipo di personaggio", "kind", ["umano", "zombie"]), ("Sesso", "sex", ["maschio", "femmina"]),
            ("Categoria", "type", list(TYPES)), ("Lavoratore (sotto-tipo)", "sub", ["random"] + list(SUBS)),
            ("Colore pelle", "skin", ["random", "bianco", "nero"]),
            ("Colore capelli", "hair", ["random"] + list(HAIR_COL)), ("Capelli (taglio)", "hairstyle", list(HAIRSTYLES)),
            ("Colore occhi", "eyes", ["random"] + list(EYE_COL)),
            ("Qualita' (solo umani)", "quality", ["low", "medium", "high"]),
            ("Vestiti gambe (solo civile)", "bottom", list(BOTTOM_STYLES)),
            ("Vestiti busto (solo civile)", "top", list(TOP_STYLES)),
            ("Calzature (solo civile)", "footwear", list(FOOT_STYLES))]
    widgets = {}
    for i, (lab, key, vals) in enumerate(rows):
        ttk.Label(frm, text=lab).grid(row=i, column=0, sticky="w", pady=2)
        cb = ttk.Combobox(frm, textvariable=V[key], values=vals, state="readonly", width=20)
        cb.grid(row=i, column=1, sticky="w", pady=2)
        widgets[key] = cb
    r0 = len(rows)
    ttk.Label(frm, text="Seed (vuoto = casuale)").grid(row=r0, column=0, sticky="w")
    ttk.Entry(frm, textvariable=V["seed"], width=12).grid(row=r0, column=1, sticky="w")
    ttk.Label(frm, text="Quanti personaggi").grid(row=r0 + 1, column=0, sticky="w")
    ttk.Spinbox(frm, from_=1, to=200, textvariable=V["count"], width=8).grid(row=r0 + 1, column=1, sticky="w")
    ttk.Label(frm, text="Cartella di uscita").grid(row=r0 + 2, column=0, sticky="w")
    ttk.Entry(frm, textvariable=V["out"], width=30).grid(row=r0 + 2, column=1, sticky="w")
    ttk.Button(frm, text="Sfoglia...", command=lambda: V["out"].set(filedialog.askdirectory() or V["out"].get())).grid(row=r0 + 2, column=2)
    ttk.Label(frm, text="Scheletro BVH (opzionale)").grid(row=r0 + 3, column=0, sticky="w")
    ttk.Entry(frm, textvariable=V["skel"], width=30).grid(row=r0 + 3, column=1, sticky="w")
    ttk.Button(frm, text="Scegli...", command=lambda: V["skel"].set(filedialog.askopenfilename(filetypes=[("BVH", "*.bvh")]) or V["skel"].get())).grid(row=r0 + 3, column=2)
    ttk.Checkbutton(frm, text="Esporta anche FBX riggato (serve Blender)", variable=want_fbx).grid(row=r0 + 4, column=0, columnspan=3, sticky="w", pady=(6, 0))
    ttk.Label(frm, text="Blender (blender.exe)").grid(row=r0 + 5, column=0, sticky="w")
    ttk.Entry(frm, textvariable=V["blender"], width=30).grid(row=r0 + 5, column=1, sticky="w")
    ttk.Button(frm, text="Scegli...", command=lambda: V["blender"].set(filedialog.askopenfilename(
        title="Scegli blender.exe", filetypes=[("Blender", "blender*"), ("Tutti i file", "*")]) or V["blender"].get())).grid(row=r0 + 5, column=2)
    r0 += 2
    status = tk.StringVar(value="Pronto." if found or not want_fbx.get() else "Pronto. (Blender non trovato: per l'FBX indica blender.exe)")
    ttk.Label(frm, textvariable=status, wraplength=330, foreground="#333").grid(row=r0 + 6, column=0, columnspan=3, sticky="w", pady=6)
    prog = ttk.Progressbar(frm, mode="determinate")
    prog.grid(row=r0 + 5, column=0, columnspan=3, sticky="ew", pady=4)

    def refresh(*_):
        human = V["kind"].get() == "umano"
        civile = V["type"].get() == "civile"
        widgets["quality"].configure(state="readonly" if human else "disabled")
        widgets["sub"].configure(state="readonly" if V["type"].get() == "lavoratore" else "disabled")
        for key in ("bottom", "top", "footwear"):
            widgets[key].configure(state="readonly" if civile else "disabled")
            if not civile:
                V[key].set("random")
    V["kind"].trace_add("write", refresh)
    V["type"].trace_add("write", refresh)
    refresh()

    img_label = ttk.Label(root)
    img_label.grid(row=0, column=1, padx=8, pady=8)
    state = {"photo": None, "busy": False}
    q = queue.Queue()

    def spec_from_form(seed):
        return Spec(V["kind"].get(), V["sex"].get(), V["type"].get(), V["sub"].get(), V["skin"].get(), V["hair"].get(),
                    V["eyes"].get(), V["quality"].get(), None, seed, V["hairstyle"].get(),
                    V["bottom"].get(), V["top"].get(), V["footwear"].get())

    def seed_value():
        t = V["seed"].get().strip()
        return int(t) if t else random.randrange(1, 9000)

    def show(img):
        h, w = img.shape[:2]
        maxh = max(300, root.winfo_screenheight() - 160)
        f = int(math.ceil(h / maxh)) if h > maxh else 1
        if f > 1:
            img = np.ascontiguousarray(img[::f, ::f])
        state["photo"] = tk.PhotoImage(data=base64.b64encode(png_bytes(img)).decode("ascii"), format="PNG")
        img_label.configure(image=state["photo"])

    def worker(kind, specs, out, skel, fbx, blender):
        try:
            if skel:
                load_skeleton(skel)
            else:
                reset_skeleton()
            if fbx and kind != "preview" and find_blender(blender) is None:
                raise RuntimeError("Per l'FBX serve Blender e non l'ho trovato: indica blender.exe nel campo 'Blender', "
                                   "oppure togli la spunta 'Esporta anche FBX'.")
            for i, sp in enumerate(specs):
                r = generate(sp)
                if kind == "preview":
                    q.put(("img", preview_images(r)["sheet"], f"{r['name']}: {r['tris']} triangoli (limite {r['budget']})"))
                else:
                    if fbx:
                        q.put(("prog", i + 0.5, len(specs), f"{r['name']}: rig ed export FBX in Blender..."))
                    folder, _ = save_character(r, out, True, fbx, blender)
                    q.put(("prog", i + 1, len(specs), f"{r['name']}: {r['tris']} triangoli" + (" + FBX" if fbx else "")))
                    if i == len(specs) - 1:
                        q.put(("img", preview_images(r)["sheet"], f"Fatto. Salvato in {out}"))
            q.put(("done",))
        except Exception as e:                       # mostra l'errore invece di bloccarsi
            import traceback
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_gen_errori.log"), "w") as fh:
                    traceback.print_exc(file=fh)
            except OSError:
                pass
            q.put(("err", str(e)))

    def poll():
        try:
            while True:
                it = q.get_nowait()
                if it[0] == "img":
                    show(it[1]); status.set(it[2])
                elif it[0] == "prog":
                    prog.configure(maximum=it[2], value=it[1]); status.set(it[3])
                elif it[0] == "err":
                    messagebox.showerror("Errore", it[1]); status.set("Errore.")
                    state["busy"] = False
                    btn_gen.configure(state="normal"); btn_prev.configure(state="normal")
                    prog.configure(value=0)
                elif it[0] == "done":
                    state["busy"] = False; btn_gen.configure(state="normal"); btn_prev.configure(state="normal")
        except queue.Empty:
            pass
        root.after(100, poll)

    def start(kind):
        if state["busy"]:
            return
        try:
            n = max(1, int(V["count"].get())) if kind == "gen" else 1
            base = seed_value()
        except ValueError:
            messagebox.showerror("Errore", "Seed e quantita' devono essere numeri interi."); return
        state["busy"] = True
        status.set("Sto generando..."); prog.configure(value=0)
        btn_gen.configure(state="disabled"); btn_prev.configure(state="disabled")
        specs = [spec_from_form(base + i) for i in range(n)]
        threading.Thread(target=worker, args=("preview" if kind == "prev" else "gen", specs, V["out"].get(), V["skel"].get().strip(),
                                              want_fbx.get(), V["blender"].get().strip() or None), daemon=True).start()

    btn_prev = ttk.Button(frm, text="Anteprima", command=lambda: start("prev"))
    btn_prev.grid(row=r0 + 4, column=0, pady=6, sticky="ew")
    btn_gen = ttk.Button(frm, text="Genera e salva", command=lambda: start("gen"))
    btn_gen.grid(row=r0 + 4, column=1, columnspan=2, pady=6, sticky="ew")
    ttk.Button(frm, text="Seed casuale", command=lambda: V["seed"].set(str(random.randrange(1, 9000)))).grid(row=r0 - 2, column=2)
    poll()
    root.mainloop()


def _pause(msg):
    print(msg)
    try:
        if sys.stdin and sys.stdin.isatty():
            input("Premi Invio per chiudere...")
    except Exception:
        pass


def run_gui():
    try:
        import tkinter  # noqa: F401
    except ImportError:
        _pause("tkinter non e' installato in questo Python, quindi la finestra non puo' aprirsi.\n"
               "  Windows: reinstalla Python da python.org spuntando 'tcl/tk and IDLE'.\n"
               "  Linux:   sudo apt install python3-tk\n"
               "Intanto puoi usare la riga di comando: python character_gen.py --help")
        return 1
    try:
        gui()
    except Exception:
        import traceback
        log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "character_gen_errori.log")
        with open(log, "w") as fh:
            traceback.print_exc(file=fh)
        traceback.print_exc()
        _pause(f"La GUI si e' chiusa per un errore (dettagli in {log}).")
        return 1
    return 0


def main():
    argv = sys.argv[1:]
    if "--" in argv:                                   # lanciato da Blender: blender -b --python character_gen.py -- ...
        argv = argv[argv.index("--") + 1:]
    if argv and argv[0] == "--blender-build":
        blender_build(argv[1], argv[2], argv[3] if len(argv) > 3 else None)
        return 0
    if not argv or "--gui" in argv:
        return run_gui()
    return cli(argv)


if __name__ == "__main__":
    sys.exit(main())
