#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xps2outbreak.py - Modello XNALara/XPS (.xps / .mesh) -> personaggio RE Outbreak (FBX + NBD)
============================================================================================

USO: trascina uno o piu' file .xps (o .mesh) sopra questo script, oppure:
    python xps2outbreak.py modello.xps
    python xps2outbreak.py modello.xps --max-tris 11000 --blender "C:\\...\\blender.exe"
    python xps2outbreak.py modello.xps --atlas-body 512 --atlas-head 256     (default)
    python xps2outbreak.py modello.xps --no-atlas                            (texture originali)
    python xps2outbreak.py modello.xps --max-verts 3000     facoltativo: divide in mesh da max N vertici
    python xps2outbreak.py modello_OB.fbx                   FBX gia' fatto (anche ritoccato): rifa' l'NBD
                                                            con scheletro corretto -> modello_OB_fix.fbx / .nbd

Accanto a ogni file crea:
    <nome>_OB.fbx            armatura "Node0" con Node1..Node35 (scheletro Outbreak FISSO), GroupId,
                             Mesh0 = il modello, Mesh1 = segnaposto invisibile
    <nome>_OB.nbd            pronto per il gioco (serve fbx2nbd.py nella stessa cartella)
    <nome>_OB_preview.png    anteprima: T-pose con lo scheletro, pesi colorati per osso, posa di prova
    <nome>_mapping.json      quale osso XPS e' finito su quale Node: modificalo e rilancia per correggere
    <nome>_OB_corpo.png      atlas del corpo (512x512) e della testa (256x256): tutte le texture del modello
    <nome>_OB_testa.png      unite in due, con le UV rimappate (puoi ritoccarle e riconvertire l'FBX)

Cosa fa
  1. legge il file XPS (ossa, mesh, UV, normali, pesi, texture)
  2. mappa ogni osso XPS su un Node Outbreak (riconosce i nomi, es. "L Brow 1" -> Node23).
     Ossa non riconosciute (capelli, seno, gonna, accessori): seguono il primo genitore riconosciuto;
     se non ne hanno (radici separate tipo "Hair Root") vanno sul Node piu' vicino ai loro vertici.
  3. adatta la MESH allo scheletro Outbreak (che il gioco non permette di cambiare): scala, poi ogni
     segmento (coscia, stinco, braccio, avambraccio, clavicola, busto, collo) viene portato sul suo
     osso Outbreak, allungato solo lungo l'osso. Viso, mani e piedi seguono rigidi.
  4. fonde i pesi originali dell'autore sui Node: max 4 ossa per vertice, pesi < 1% tolti
  5. se il modello supera --max-tris triangoli (default 11000) lo riduce (Decimate di Blender,
     simmetrico, cuciture UV conservate)
  6. unisce tutte le texture in due atlas (corpo e vestiti / testa, capelli e occhi): di ogni texture
     entra solo la parte usata, texture ripetute comprese; spazio proporzionale ai texel originali
  7. esporta l'FBX (stesse regole di fbx_autorig) e lo converte in NBD con fbx2nbd.py. Nell'NBD lo scheletro
     viene reso uguale ai personaggi originali: Node0/1/2/22 nodi semplici (con Node1/Node2/Node22 "joint"
     il personaggio in gioco e' INVISIBILE), stesso ordine dei figli; materiali senza riflesso

Viso: sopracciglia -> Node23/Node25, palpebre/ciglia -> Node24/Node26, mascella, labbro inferiore,
lingua -> Node27, occhi e resto della testa -> Node21. Dita: pollice -> Node33/29, indice e medio ->
Node34/30, anulare e mignolo -> Node35/31, palmo -> Node32/28.
Le shape key (espressioni morph) dei modelli XPS non vengono convertite.
"""
import json
import math
import os
import struct
import subprocess
import sys

__version__ = "1.4.0"

# ------------------------------------------------------------------------------------------------
# Scheletro Outbreak (identico a fbx_autorig: T-pose del progetto) e gruppi di animazione
# ------------------------------------------------------------------------------------------------
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
PARENTS = {
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
BONE_ORDER = ["Node%d" % i for i in range(1, 36)]
MAP_FORMAT = "xps2outbreak_mapping"


def group_id(name):
    k = int(name[4:])
    return 0 if k <= 9 else 1 if k <= 21 else 2 if k <= 27 else 3 if k <= 31 else 4


# ------------------------------------------------------------------------------------------------
# Lettura XPS binario (.xps con intestazione, .mesh senza)
# ------------------------------------------------------------------------------------------------
class XpsError(Exception):
    pass


class _Rd(object):
    def __init__(self, data):
        self.d = data
        self.p = 0

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self):
        v = struct.unpack_from("<H", self.d, self.p)[0]
        self.p += 2
        return v

    def i16(self):
        v = struct.unpack_from("<h", self.d, self.p)[0]
        self.p += 2
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.d, self.p)[0]
        self.p += 4
        return v

    def f(self, n):
        v = struct.unpack_from("<%df" % n, self.d, self.p)
        self.p += 4 * n
        return v

    def s(self):
        b1 = self.u8()
        b2 = self.u8() if b1 >= 128 else 0
        n = (b1 % 128) + b2 * 128
        raw = self.d[self.p:self.p + n]
        self.p += n
        return raw.decode("utf-8-sig", "replace")


def read_xps(path):
    """-> dict(bones=[(nome, padre, (x,y,z))], meshes=[dict(...)]), coordinate XPS (Y su, fronte +Z)."""
    if path.lower().endswith(".ascii"):
        raise XpsError("i file .mesh.ascii non sono supportati: aprili in XNALara/XPS e salvali come .xps")
    r = _Rd(open(path, "rb").read())
    tangent, variable = True, False
    if struct.unpack_from("<I", r.d, 0)[0] == 323232:
        r.u32()
        vmaj, vmin = r.u16(), r.u16()
        r.s()                                   # "XNAaraL"
        nset = r.u32()
        r.s(), r.s(), r.s()                     # macchina, utente, file
        r.p += nset * 4                         # impostazioni (posa di default, flag): non servono
        tangent = vmin <= 12 and vmaj <= 2
        variable = vmaj >= 3
    bones = []
    for _ in range(r.u32()):
        name = r.s()
        par = r.i16()
        bones.append((name, par, r.f(3)))
    if not bones:
        raise XpsError("il modello non ha ossa")
    if any(b[1] >= len(bones) for b in bones):
        raise XpsError("intestazione non riconosciuta (ossa non valide): versione XPS non supportata?")
    meshes = []
    for _ in range(r.u32()):
        m = {"name": r.s() or "mesh"}
        nuv = r.u32()
        texs = []
        for _ in range(r.u32()):
            tname = r.s().replace("\\", "/").split("/")[-1]
            r.u32()
            texs.append(tname)
        m["textures"] = texs
        nv = r.u32()
        P, N, UV, BI, BW = [], [], [], [], []
        for _ in range(nv):
            P.append(r.f(3))
            N.append(r.f(3))
            r.p += 4                            # colore del vertice
            uv = None
            for k in range(nuv):
                u = r.f(2)
                if k == 0:
                    uv = u
                if tangent:
                    r.p += 16
            UV.append(uv or (0.0, 0.0))
            n = r.i16() if variable else 4
            idx = [r.i16() for _ in range(n)]
            BI.append(idx)
            BW.append(r.f(n))
        nf = r.u32()
        F = struct.unpack_from("<%dI" % (3 * nf), r.d, r.p)
        r.p += 12 * nf
        m.update(P=P, N=N, UV=UV, BI=BI, BW=BW, F=[F[i:i + 3] for i in range(0, 3 * nf, 3)])
        meshes.append(m)
    if not meshes:
        raise XpsError("il modello non ha mesh")
    return {"bones": bones, "meshes": meshes}


# ------------------------------------------------------------------------------------------------
# Riconoscimento dei nomi delle ossa
# ------------------------------------------------------------------------------------------------
def _tokens(name):
    import re
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)          # lShldrBend -> l Shldr Bend, LeftArm -> Left Arm
    s = s.lower().replace("_", " ").replace(".", " ").replace("-", " ").replace(":", " ")
    s = re.sub(r"([a-z])(\d)", r"\1 \2", s)
    s = re.sub(r"(\d)([a-z])", r"\1 \2", s)
    return s.split()


def classify(name, x):
    """Nome osso XPS -> 'NodeN' oppure None (non riconosciuto: seguira' il genitore)."""
    t = _tokens(name)
    j = "".join(t)
    has = lambda *w: any(k in t for k in w)
    sub = lambda *w: any(k in j for k in w)
    side = None
    if has("l", "left") or j.startswith("left"):
        side = "L"
    elif has("r", "right") or j.startswith("right"):
        side = "R"
    elif abs(x) > 1e-4:
        side = "L" if x > 0 else "R"          # +X = lato sinistro del personaggio
    LR = lambda l, r: (l if side == "L" else r) if side else None
    nums = [int(k) for k in t if k.isdigit()]

    if sub("finger", "thumb", "index", "pinky", "pinkie") or (has("middle", "ring", "little") and sub("finger", "hand")) \
            or (has("mid", "ring") and nums and side and not sub("brow", "lid", "eye", "lip", "spine", "neck")):
        if sub("connection", "metacarpal", "palm"):
            return LR("Node32", "Node28")
        if sub("thumb"):
            n = 1
        elif sub("index"):
            n = 2
        elif has("middle", "mid"):
            n = 3
        elif has("ring"):
            n = 4
        elif sub("pinky", "pinkie") or has("little"):
            n = 5
        else:
            n = nums[0] if nums else 0
        if n == 1:
            return LR("Node33", "Node29")
        if n in (2, 3):
            return LR("Node34", "Node30")
        if n in (4, 5):
            return LR("Node35", "Node31")
        return LR("Node32", "Node28")
    if has("hand", "palm", "carpal", "metacarpal"):
        return LR("Node32", "Node28")
    if has("wrist"):
        return LR("Node15", "Node19")
    if sub("forearm", "elbow", "lowerarm") or (has("lower") and has("arm")):
        return LR("Node14", "Node18")
    if sub("clavicle", "collar") or has("clav"):
        return LR("Node12", "Node16")
    if sub("shoulder"):
        return LR("Node13", "Node17") if 2 in nums else LR("Node12", "Node16")
    if sub("upperarm", "uparm") or has("arm", "shldr", "humerus"):
        return LR("Node13", "Node17")
    if sub("brow"):
        return LR("Node23", "Node25") or "Node21"
    if sub("lid", "lash"):
        return LR("Node24", "Node26") or "Node21"
    if sub("eye", "pupil", "iris"):
        return "Node21"
    if has("jaw", "chin", "tongue") or (sub("lip", "teeth", "mouth") and has("lower", "bottom", "down", "below")):
        return "Node27"
    if has("neck"):
        return "Node20"
    if has("head", "face", "cheek", "nose", "ear", "lip", "lips", "mouth", "smile", "skull", "forehead",
           "teeth", "temple", "nostril"):
        return "Node21"
    if has("abdomen", "waist", "belly", "stomach"):
        return "Node10"
    if has("spine", "chest", "torso", "ribs", "upperchest", "back"):
        if has("upper", "chest", "upperchest", "top", "3") or (has("spine") and 2 in nums):
            return "Node11"
        return "Node10"
    if has("thigh", "femur") or sub("upleg", "upperleg") or (has("hip") and side and not has("hips")):
        return LR("Node4", "Node7")
    if has("knee", "calf", "shin", "lowerleg", "leg", "tibia"):
        return LR("Node5", "Node8")
    if has("ankle", "foot", "toe", "toes", "heel", "ball") or sub("metatarsal", "toe"):
        return LR("Node6", "Node9")
    if has("hips", "pelvis", "hip") or (has("root") and has("body", "hips", "hip")):
        return "Node3"
    return None


# ------------------------------------------------------------------------------------------------
# Avvio fuori da Blender (drag & drop): Blender per l'FBX, poi fbx2nbd per l'NBD
# ------------------------------------------------------------------------------------------------
def find_blender(hint=None):
    import glob
    import importlib.util
    import shutil
    cands = [c for c in (hint, os.environ.get("BLENDER"), shutil.which("blender")) if c]
    pats = [r"C:\Program Files\Blender Foundation\Blender*\blender.exe",
            r"C:\Program Files (x86)\Blender Foundation\Blender*\blender.exe",
            r"C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe",
            r"C:\Program Files\Steam\steamapps\common\Blender\blender.exe",
            "/Applications/Blender.app/Contents/MacOS/Blender", "/usr/bin/blender", "/snap/bin/blender"]
    for p in pats:
        cands += sorted(glob.glob(p), reverse=True)
    for c in cands:
        if os.path.isfile(c):
            return [c, "-b", "--factory-startup", "--python", os.path.abspath(__file__), "--"]
    if importlib.util.find_spec("bpy") is not None:          # Python con il modulo bpy (pip install bpy)
        return [sys.executable, os.path.abspath(__file__)]
    return None


def pause():
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\nPremi Invio per chiudere...")
    except Exception:
        pass


def to_nbd(fbx, nbd):
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile(os.path.join(here, "fbx2nbd.py")):
        print("  ATTENZIONE: fbx2nbd.py non e' accanto a questo script: NBD non creato "
              "(convertilo a mano: fbx2nbd.py %s)" % os.path.basename(fbx))
        return False
    sys.path.insert(0, here)
    import fbx2nbd
    if fbx2nbd.main([fbx, nbd]) != 0 or not os.path.isfile(nbd):
        return False
    fix_nbd(fbx2nbd, nbd)
    return True


# gerarchia dei personaggi originali (P06_00): ordine dei figli e tipi dei nodi
STD_CHILDREN = {0: [1], 1: [2], 2: [10, 3], 3: [4, 7], 4: [5], 5: [6], 7: [8], 8: [9], 10: [11],
                11: [12, 16, 20], 12: [13], 13: [14], 14: [15], 15: [32], 16: [17], 17: [18], 18: [19],
                19: [28], 20: [21], 21: [22], 22: [23, 24, 25, 26, 27], 28: [29, 30, 31], 32: [33, 34, 35]}


def fix_nbd(fbx2nbd, path):
    """Rende scheletro e materiali uguali ai personaggi originali: Node0/1/2/22 nodi semplici, stesso ordine
    dei figli, materiali senza riflesso (come i personaggi che funzionano in gioco)."""
    nbd = fbx2nbd.read_nbd(path)
    h = fbx2nbd.nbd_slot(nbd, "AHI")
    mo = fbx2nbd.nbd_slot(nbd, "AMO")
    if h is not None and len(h.nodes) == 36:
        for n, t in zip(h.nodes, fbx2nbd.STD_TYPES_36):
            n.type = t
            n.child, n.next = -1, -1
        for par, kids in STD_CHILDREN.items():
            h.nodes[par].child = kids[0]
            for a, b in zip(kids, kids[1:]):
                h.nodes[a].next = b
    if mo is not None:
        for ma in mo.materials:
            ma.type = 0x130000
            ma.ambient = (0.08, 0.08, 0.08, 1.0)
            ma.diffuse = (1.0, 1.0, 1.0, 1.0)
            ma.specular = (0.0, 0.0, 0.0, 1.0)
            ma.power = 5.0
    data = fbx2nbd.write_nbd(nbd)
    with open(path, "wb") as fh:
        fh.write(data)
    print("  NBD sistemato: scheletro e materiali come i personaggi originali")


def launcher(argv):
    blender, files, max_tris, no_nbd = None, [], 11000, False
    atlas_body, atlas_head = 512, 256
    max_verts = 0                     # 0 = nessuna divisione in piu' mesh
    i = 0
    while i < len(argv):
        if argv[i] == "--blender" and i + 1 < len(argv):
            blender = argv[i + 1]
            i += 2
        elif argv[i] == "--max-tris" and i + 1 < len(argv):
            max_tris = int(argv[i + 1])
            i += 2
        elif argv[i] == "--atlas-body" and i + 1 < len(argv):
            atlas_body = int(argv[i + 1])
            i += 2
        elif argv[i] == "--atlas-head" and i + 1 < len(argv):
            atlas_head = int(argv[i + 1])
            i += 2
        elif argv[i] == "--max-verts" and i + 1 < len(argv):
            max_verts = int(argv[i + 1])
            i += 2
        elif argv[i] == "--no-atlas":
            atlas_body = atlas_head = 0
            i += 1
        elif argv[i] == "--no-nbd":
            no_nbd = True
            i += 1
        else:
            files.append(argv[i])
            i += 1
    if not files:
        print(__doc__)
        try:
            p = input("Trascina qui un file .xps e premi Invio: ").strip().strip('"')
        except EOFError:
            p = ""
        if p:
            files = [p]
    files = [f.strip('"') for f in files]
    if not files:
        pause()
        return 1
    cmd = find_blender(blender)
    if cmd is None:
        print("ERRORE: non trovo Blender. Indicalo con --blender \"percorso\\blender.exe\" "
              "oppure con la variabile d'ambiente BLENDER.")
        pause()
        return 1
    bad = 0
    for f in files:
        if not f.lower().endswith((".xps", ".mesh", ".fbx")) or not os.path.isfile(f):
            print("salto %s (non e' un file .xps, .mesh o .fbx)" % f)
            bad += 1
            continue
        src = os.path.abspath(f)
        stem = os.path.splitext(src)[0]
        print("=" * 70)
        if src.lower().endswith(".fbx"):
            # FBX gia' convertito (anche ritoccato a mano): divide le mesh troppo grandi e rifa' l'NBD
            stem = stem[:-3] if stem.endswith("_OB") else stem
            out = stem + "_OB_fix.fbx"
            print("Sistemo %s" % os.path.basename(src))
            job = ["--fixfbx", src, out, str(max_verts)]
        else:
            out = stem + "_OB.fbx"
            print("Conversione di %s" % os.path.basename(src))
            job = ["--xps2ob", src, out, str(max_tris), str(atlas_body), str(atlas_head), str(max_verts)]
        res = subprocess.run(cmd + job, capture_output=True, text=True, errors="replace")
        lines = [ln for ln in (res.stdout or "").splitlines() if ln.startswith("XPS2OB")]
        print("\n".join(ln.replace("XPS2OB ", "") for ln in lines))
        if not os.path.isfile(out) or res.returncode != 0:
            bad += 1
            tail = "\n".join(((res.stdout or "") + "\n" + (res.stderr or "")).strip().splitlines()[-15:])
            print("ERRORE: l'FBX non e' stato creato.\n" + tail)
            continue
        if not no_nbd:
            print("-" * 70)
            if not to_nbd(out, os.path.splitext(out)[0] + ".nbd"):
                bad += 1
    print("=" * 70)
    print("Fatto." if not bad else "Finito con %d errori." % bad)
    pause()
    return 1 if bad else 0


# ------------------------------------------------------------------------------------------------
# Dentro Blender
# ------------------------------------------------------------------------------------------------
def log(msg):
    print("XPS2OB   " + msg)


def warn(msg):
    print("XPS2OB   ATTENZIONE: " + msg)


def build_mapping(bones, verts_by_bone, override):
    """-> (auto {osso: Node o None}, risolto {osso: Node}, nodi 'primari' {Node: indice osso})"""
    nb = len(bones)
    auto = {}
    for i, (name, par, co) in enumerate(bones):
        if name in override:
            v = override[name]
            auto[name] = v if v in SKEL else None
        else:
            auto[name] = classify(name, co[0])
    depth = []
    for i in range(nb):
        d, p = 0, bones[i][1]
        while p >= 0 and d < nb:
            d += 1
            p = bones[p][1]
        depth.append(d)
    def prim():
        out = {}
        for i in sorted(range(nb), key=lambda k: (depth[k], k)):
            n = auto[bones[i][0]]
            if n and n not in out:
                out[n] = i
        return out

    primary = prim()
    # nessun polso separato (es. DAZ: lHand): la mano fa da polso
    for wr, hd in (("Node15", "Node32"), ("Node19", "Node28")):
        if wr not in primary and hd in primary:
            for nm in list(auto):
                if auto[nm] == hd:
                    auto[nm] = wr
            primary = prim()
    # ossa non riconosciute dal nome ma al posto giusto nella gerarchia: se manca il braccio ma
    # l'avambraccio c'e', il primo genitore non riconosciuto dell'avambraccio e' il braccio (ecc.)
    found_by_pos = []
    for miss, child in (("Node14", "Node15"), ("Node18", "Node19"), ("Node13", "Node14"), ("Node17", "Node18"),
                        ("Node5", "Node6"), ("Node8", "Node9"), ("Node4", "Node5"), ("Node7", "Node8")):
        if miss in primary or child not in primary:
            continue
        p = bones[primary[child]][1]
        while p >= 0 and auto[bones[p][0]] == child:          # ossa "twist" dello stesso segmento
            p = bones[p][1]
        if p >= 0 and auto[bones[p][0]] is None and bones[p][0] not in override:
            auto[bones[p][0]] = miss
            found_by_pos.append((bones[p][0], miss))
            primary = prim()
    resolved = {}
    orphans = []
    for i, (name, par, co) in enumerate(bones):
        n, p = auto[name], par
        while n is None and p >= 0:
            n = auto[bones[p][0]]
            p = bones[p][1]
        if n is None:
            orphans.append(i)
        resolved[name] = n
    return auto, resolved, primary, orphans, found_by_pos


def convert(src, out, max_tris, atlas_body=512, atlas_head=256, max_verts=0):
    import bpy
    import numpy as np
    from mathutils import Matrix

    xps = read_xps(src)
    bones, meshes = xps["bones"], xps["meshes"]
    names = [b[0] for b in bones]
    ntri0 = sum(len(m["F"]) for m in meshes)
    log("lette %d ossa, %d mesh, %d triangoli" % (len(bones), len(meshes), ntri0))

    # --- tutte le mesh in un'unica lista di vertici
    P = np.array([p for m in meshes for p in m["P"]], float)
    N = np.array([n for m in meshes for n in m["N"]], float)
    UV = np.array([u for m in meshes for u in m["UV"]], float)
    nv = len(P)
    tex_names = []
    faces, fmat = [], []
    base = 0
    for m in meshes:
        tn = m["textures"][0] if m["textures"] else ""
        if tn not in tex_names:
            tex_names.append(tn)
        mi = tex_names.index(tn)
        for a, b, c in m["F"]:
            faces.append((base + a, base + c, base + b))   # XPS e' in senso orario: inverto
            fmat.append(mi)
        base += len(m["P"])
    faces = np.array(faces, int)
    # normali: nei modelli estratti dai giochi spesso puntano verso l'interno. Il verso delle facce
    # (invertito come fa l'importer XPS) e' quello giusto: giro le normali delle mesh discordi
    flipped = 0
    base = 0
    for m in meshes:
        k = len(m["P"])
        F = faces[sum(len(mm["F"]) for mm in meshes[:meshes.index(m)]):][:len(m["F"])]
        if len(F):
            fn = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
            agree = np.sum(fn * (N[F[:, 0]] + N[F[:, 1]] + N[F[:, 2]]), axis=1)
            if np.mean(agree < 0) > 0.5:
                N[base:base + k] *= -1.0
                flipped += 1
        base += k
    if flipped:
        log("normali girate verso l'esterno in %d mesh su %d" % (flipped, len(meshes)))
    # facce con l'ordine dei vertici incoerente (comune nei modelli estratti): le giro secondo le normali,
    # altrimenti nel gioco (che non disegna il retro delle facce) diventerebbero buchi
    fn = np.cross(P[faces[:, 1]] - P[faces[:, 0]], P[faces[:, 2]] - P[faces[:, 0]])
    bad = np.sum(fn * (N[faces[:, 0]] + N[faces[:, 1]] + N[faces[:, 2]]), axis=1) < 0
    if bad.any():
        faces[bad] = faces[bad][:, [0, 2, 1]]
        log("facce girate per seguire le normali: %d su %d" % (bad.sum(), len(faces)))
    # pesi sorgente (osso XPS)
    SW = np.zeros((nv, len(bones)), np.float32)
    v = 0
    for m in meshes:
        for idx, ws in zip(m["BI"], m["BW"]):
            for b, w in zip(idx, ws):
                if 0 <= b < len(bones) and w > 0:
                    SW[v, b] += w
            v += 1
    no_w = SW.sum(1) <= 0
    if no_w.any():
        warn("%d vertici senza pesi nel file: li lego all'osso del vertice pesato piu' vicino" % no_w.sum())
        good = np.nonzero(~no_w)[0]
        for k in np.nonzero(no_w)[0]:
            j = good[np.argmin(((P[good] - P[k]) ** 2).sum(1))]
            SW[k] = SW[j]
    SW /= SW.sum(1, keepdims=True)

    # --- mappatura
    map_path = os.path.splitext(src)[0] + "_mapping.json"
    override = {}
    if os.path.isfile(map_path):
        try:
            data = json.load(open(map_path, encoding="utf-8"))
            if data.get("format") != MAP_FORMAT:
                raise ValueError("formato sconosciuto")
            override = {k: (v or None) for k, v in data.get("mapping", {}).items()}
            log("uso la mappatura di %s (%d ossa)" % (os.path.basename(map_path), len(override)))
        except Exception as e:
            warn("non riesco a leggere %s (%s): uso la mappatura automatica" % (os.path.basename(map_path), e))
            override = {}
    auto, resolved, primary, orphans, found_by_pos = build_mapping(bones, None, override)
    for bn, nd in found_by_pos:
        log("'%s' riconosciuto dalla posizione nella gerarchia: %s" % (bn, nd))
    # radici separate (es. "Hair Root"): Node con il giunto piu' vicino ai loro vertici
    for i in orphans:
        sel = SW[:, i] > 0.01
        if not sel.any():
            resolved[names[i]] = None
            continue
        cen = (P[sel] * SW[sel, i:i + 1]).sum(0) / SW[sel, i].sum()
        best = min(primary, key=lambda n: float(((np.array(bones[primary[n]][2]) - cen) ** 2).sum()))
        resolved[names[i]] = best
        log("'%s' non ha genitori riconosciuti: va su %s (giunto piu' vicino ai suoi vertici)" % (names[i], best))
    need = ["Node4", "Node5", "Node6", "Node7", "Node8", "Node9", "Node13", "Node14", "Node15",
            "Node17", "Node18", "Node19", "Node21"]
    miss = [n for n in need if n not in primary]
    DESCR = {"Node4": "coscia SX", "Node5": "ginocchio SX", "Node6": "caviglia SX", "Node7": "coscia DX",
             "Node8": "ginocchio DX", "Node9": "caviglia DX", "Node13": "braccio SX (tra spalla e gomito)",
             "Node14": "avambraccio SX", "Node15": "polso SX", "Node17": "braccio DX (tra spalla e gomito)",
             "Node18": "avambraccio DX", "Node19": "polso DX", "Node21": "testa"}
    data = {"format": MAP_FORMAT, "version": 1,
            "_info": "osso XPS -> Node Outbreak. \"\" = segue il genitore. Modifica la sezione mapping e rilancia.",
            "mapping": {n: (auto[n] or "") for n in names},
            "_risultato": {n: (resolved[n] or "") for n in names}}
    if miss:
        data["_mancanti"] = {n: DESCR.get(n, "") for n in miss}
    with open(map_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    if miss:
        raise RuntimeError("non riconosco le ossa per %s. Apri %s (accanto al file .xps) con un editor di testo: "
                           "in \"mapping\" scrivi il Node accanto all'osso giusto (es. \"lShldrBend\": \"Node13\") "
                           "e rilancia" % (", ".join("%s = %s" % (n, DESCR.get(n, n)) for n in miss),
                                           os.path.basename(map_path)))
    used = {}
    for n in names:
        if resolved[n]:
            used.setdefault(resolved[n], []).append(n)
    for node in BONE_ORDER:
        if node in used:
            lst = used[node]
            log("  %-6s <- %s" % (node, ", ".join(lst[:6]) + (" (+%d)" % (len(lst) - 6) if len(lst) > 6 else "")))

    # --- pesi sui Node
    nodes = BONE_ORDER
    col = {n: k for k, n in enumerate(nodes)}
    NW = np.zeros((nv, len(nodes)), np.float32)
    for i, n in enumerate(names):
        if resolved[n]:
            NW[:, col[resolved[n]]] += SW[:, i]
    lost = NW.sum(1) <= 1e-6
    if lost.any():
        NW[lost, col["Node3"]] = 1.0
    NW /= NW.sum(1, keepdims=True)

    # --- allineamento globale: anche a y = 94, centro del bacino in x = z = 0, fronte +Z
    J = {n: np.array(bones[i][2], float) for n, i in primary.items()}
    ground = float(P[:, 1].min())
    hipmid = (J["Node4"] + J["Node7"]) / 2
    flip = False
    toes = P[P[:, 1] < ground + 0.03 * (P[:, 1].max() - ground)]
    if len(toes) and toes[:, 2].mean() < hipmid[2] - 0.01 * (P[:, 1].max() - ground):
        flip = True
    R0 = np.diag([-1.0, 1.0, -1.0]) if flip else np.eye(3)
    if flip:
        log("il modello guarda indietro: lo giro di 180 gradi")
    s = (94.0 - 0.0) / max(1e-9, hipmid[1] - ground)

    zref = J["Node10"][2] if "Node10" in J else hipmid[2]     # profondita': centrata sulla colonna

    def g(p):
        q = (np.asarray(p, float) - np.array([hipmid[0], ground, zref])) @ R0.T
        return q * s

    P = g(P)
    N = N @ R0.T
    for n in J:
        J[n] = g(J[n])
    log("scala x%.3f (anche a y = 94), altezza %.1f" % (s, P[:, 1].max()))

    # --- trasformazioni per Node: segmento sorgente -> segmento Outbreak
    T = {n: np.array(SKEL[n], float) for n in SKEL}

    def rot_between(a, b):
        a = a / np.linalg.norm(a)
        b = b / np.linalg.norm(b)
        v = np.cross(a, b)
        c = float(a @ b)
        if np.linalg.norm(v) < 1e-9:
            return np.eye(3) if c > 0 else np.diag([-1.0, -1.0, 1.0])
        K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
        return np.eye(3) + K + K @ K * (1.0 / (1.0 + c))

    X = {}                                         # Node -> (A sorgente, M 3x3, A destinazione)

    def seg(node, tails):
        if node not in J:
            return False
        for tl in tails:
            if tl in J:
                ds, dt = J[tl] - J[node], T[tl] - T[node]
                ls, lt = np.linalg.norm(ds), np.linalg.norm(dt)
                if ls < 1e-6 or lt < 1e-6:
                    continue
                d = ds / ls
                k = float(np.clip(lt / ls, 0.5, 2.0))
                S = np.eye(3) + (k - 1.0) * np.outer(d, d)
                X[node] = (J[node], rot_between(ds, dt) @ S, T[node])
                return True
        return False

    def rigid(node, src, dst, like=None):
        M = X[like][1] if like in X else np.eye(3)
        if like in X:                              # solo rotazione, niente allungamento
            U, _, Vt = np.linalg.svd(M)
            M = U @ Vt
        X[node] = (src, M, dst)

    # in profondita' (z) ogni arto tiene la sua posizione rispetto alla colonna: forzare i perni XPS
    # su quelli Outbreak inclinerebbe il busto (i rig mettono i perni a profondita' diverse)
    for chain in (("Node4", "Node5", "Node6"), ("Node7", "Node8", "Node9"),
                  ("Node13", "Node14", "Node15", "Node32", "Node33", "Node34", "Node35"),
                  ("Node17", "Node18", "Node19", "Node28", "Node29", "Node30", "Node31")):
        if chain[0] in J:
            dz = J[chain[0]][2] - T[chain[0]][2]
            for n in chain:
                T[n] = T[n] + np.array([0.0, 0.0, dz])
    # caviglie: tengo l'altezza del modello (scarpe e tacchi restano a terra)
    for n in ("Node6", "Node9"):
        if n in J:
            T[n] = T[n] + np.array([0.0, J[n][1] - T[n][1], 0.0])
    # arti: giunto su giunto (anca, ginocchio, caviglia, spalla, gomito, polso sono punti anatomici)
    for a, b in (("Node4", ["Node5"]), ("Node5", ["Node6"]), ("Node7", ["Node8"]), ("Node8", ["Node9"]),
                 ("Node13", ["Node14"]), ("Node14", ["Node15"]), ("Node17", ["Node18"]), ("Node18", ["Node19"])):
        seg(a, b)
    rigid("Node6", J["Node6"], T["Node6"])
    rigid("Node9", J["Node9"], T["Node9"])
    rigid("Node15", J["Node15"], T["Node15"], like="Node14")
    rigid("Node19", J["Node19"], T["Node19"], like="Node18")
    # busto, clavicole, collo, testa e viso: i perni della colonna non sono punti anatomici, quindi
    # niente giunto su giunto: il busto si adatta solo tra la linea delle anche e quella delle spalle
    TORSO = {"Node3", "Node10", "Node11", "Node12", "Node16", "Node20", "Node21",
             "Node22", "Node23", "Node24", "Node25", "Node26", "Node27"}
    hs, ht = (J["Node4"] + J["Node7"]) / 2, (T["Node4"] + T["Node7"]) / 2
    ss, st = (J["Node13"] + J["Node17"]) / 2, (T["Node13"] + T["Node17"]) / 2
    d0, d1 = ht - hs, st - ss
    d0[0] = d1[0] = d0[2] = d1[2] = 0.0

    def torso(Q):
        t = np.clip((Q[:, 1] - hs[1]) / max(1e-6, ss[1] - hs[1]), 0.0, 1.0)[:, None]
        return Q + d0 * (1.0 - t) + d1 * t

    for n in TORSO:
        X[n] = None
    for n in ("Node32", "Node33", "Node34", "Node35"):
        X[n] = X["Node15"]
    for n in ("Node28", "Node29", "Node30", "Node31"):
        X[n] = X["Node19"]
    for n in BONE_ORDER:                           # Node senza giunto sorgente: come il padre
        if n not in X:
            p = PARENTS[n]
            while p and p not in X:
                p = PARENTS[p]
            X[n] = X[p] if p else None
    P2 = np.zeros_like(P)
    N2 = np.zeros_like(N)
    PT = torso(P)
    for k, n in enumerate(nodes):
        w = NW[:, k]
        if not w.any():
            continue
        if X[n] is None:
            P2 += w[:, None] * PT
            N2 += w[:, None] * N
            continue
        A, M, B = X[n]
        P2 += w[:, None] * ((P - A) @ M.T + B)
        N2 += w[:, None] * (N @ np.linalg.inv(M))   # normali: inversa trasposta
    N2 /= np.maximum(np.linalg.norm(N2, axis=1, keepdims=True), 1e-9)
    moved = np.linalg.norm(P2 - P, axis=1)
    log("adattamento allo scheletro: spostamento medio %.2f, massimo %.2f" % (moved.mean(), moved.max()))
    P, N = P2, N2

    # --- limita a 4 ossa per vertice, via i pesi < 1%
    def limit4(W):
        order = np.argsort(-W, axis=1)
        out = np.zeros_like(W)
        rows = np.arange(len(W))[:, None]
        top = order[:, :4]
        out[rows, top] = W[rows, top]
        out[out < 0.01] = 0.0
        empty = out.sum(1) <= 0
        out[empty, order[empty, 0]] = 1.0
        return out / out.sum(1, keepdims=True)

    NW = limit4(NW)

    # --- scena Blender
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scn = bpy.context.scene
    me = bpy.data.meshes.new("Mesh0")
    me.from_pydata([tuple(p) for p in P], [], [tuple(f) for f in faces])
    me.update()
    if len(me.polygons) != len(faces):
        warn("%d triangoli degeneri scartati" % (len(faces) - len(me.polygons)))
    uvl = me.uv_layers.new(name="UVMap")
    lv = np.zeros(len(me.loops), int)
    me.loops.foreach_get("vertex_index", lv)
    uvd = np.c_[UV[lv, 0], 1.0 - UV[lv, 1]]
    uvl.data.foreach_set("uv", uvd.ravel())
    pm = np.zeros(len(me.polygons), int)
    if len(me.polygons) == len(faces):
        pm = np.array(fmat)
    me.polygons.foreach_set("material_index", pm)
    try:
        me.normals_split_custom_set([tuple(N[i]) for i in lv])
    except Exception as e:
        warn("normali originali non applicate (%s)" % e)
    # materiali e texture
    xdir = os.path.dirname(src)
    files = {f.lower(): f for f in os.listdir(xdir)} if os.path.isdir(xdir) else {}
    tmpdir = None
    missing = []
    for tn in tex_names:
        mat = bpy.data.materials.new(os.path.splitext(tn)[0] or "material")
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        img = None
        fpath = os.path.join(xdir, files[tn.lower()]) if tn and tn.lower() in files else None
        if fpath:
            try:
                img = bpy.data.images.load(fpath)
            except Exception:
                img = None
        if img is None:
            missing.append(tn or "(nessuna)")
            if tmpdir is None:
                import tempfile
                tmpdir = tempfile.mkdtemp(prefix="xps2ob_")
            ph = os.path.join(tmpdir, (os.path.splitext(tn)[0] or "mancante") + ".png")
            write_png(ph, np.full((64, 64, 3), 128, np.uint8))
            img = bpy.data.images.load(ph)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        if bsdf:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        me.materials.append(mat)
    if missing:
        warn("texture non trovate accanto al file (%d): %s -> uso un grigio segnaposto. Copia le texture "
             "accanto al .xps e rilancia" % (len(missing), ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else "")))
    ob = bpy.data.objects.new("Mesh0", me)
    scn.collection.objects.link(ob)
    for n in nodes:
        ob.vertex_groups.new(name=n)
    for k, n in enumerate(nodes):
        idx = np.nonzero(NW[:, k] > 0)[0]
        vg = ob.vertex_groups[n]
        for w in np.unique(np.round(NW[idx, k], 4)):
            vg.add([int(i) for i in idx[np.round(NW[idx, k], 4) == w]], float(w), 'REPLACE')

    # --- riduzione poligoni
    ntri = len(me.polygons)
    if max_tris and ntri > max_tris:
        reduce_mesh(bpy, np, ob, max_tris, nodes)
        ntri = len(ob.data.polygons)
    else:
        log("triangoli: %d (limite %d): nessuna riduzione" % (ntri, max_tris))

    # --- texture in due atlas (corpo / testa)
    if atlas_body and atlas_head:
        make_atlas(bpy, np, ob, atlas_body, atlas_head, os.path.splitext(out)[0])

    # --- armatura (scheletro Outbreak fisso)
    arm_data = bpy.data.armatures.new("Node0")
    arm = bpy.data.objects.new("Node0", arm_data)
    scn.collection.objects.link(arm)
    arm.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    arm_data.display_type = 'STICK'
    arm.show_in_front = True
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    ebs = {}
    for n in BONE_ORDER:
        eb = arm_data.edit_bones.new(n)
        h = SKEL[n]
        L = (SKEL["Node2"][1] - h[1]) if n == "Node1" else (1.5 if int(n[4:]) >= 22 else 4.0)
        eb.head = h
        eb.tail = (h[0], h[1] + L, h[2])
        eb.roll = 0.0
        eb.use_connect = False
        ebs[n] = eb
    for n in BONE_ORDER:
        if PARENTS[n]:
            ebs[n].parent = ebs[PARENTS[n]]
    bpy.ops.object.mode_set(mode='OBJECT')
    arm["GroupId"] = 0
    for n in BONE_ORDER:
        pb = arm.pose.bones[n]
        pb.rotation_mode = 'XYZ'
        pb["GroupId"] = group_id(n)
    ob.parent = arm
    ob.matrix_parent_inverse.identity()
    ob.modifiers.new("Armature", 'ARMATURE').object = arm
    # Mesh1: segnaposto invisibile dentro la testa (lo slot esiste nei personaggi originali)
    c = np.array(SKEL["Node21"]) + np.array([0.0, 6.0, -1.0])
    m1 = bpy.data.meshes.new("Mesh1")
    m1.from_pydata([tuple(c), tuple(c + [0.3, 0, 0]), tuple(c + [0, 0.3, 0])], [], [(0, 1, 2)])
    m1.uv_layers.new(name="UVMap")
    m1.materials.append(me.materials[0])
    ob1 = bpy.data.objects.new("Mesh1", m1)
    scn.collection.objects.link(ob1)
    ob1.parent = arm
    for n in BONE_ORDER:
        ob1.vertex_groups.new(name=n)
    ob1.vertex_groups["Node21"].add([0, 1, 2], 1.0, 'REPLACE')
    ob1.modifiers.new("Armature", 'ARMATURE').object = arm
    bpy.context.view_layer.update()
    try:
        path = os.path.splitext(out)[0] + "_preview.png"
        preview(bpy, np, arm, ob, path)
        log("anteprima %s" % os.path.basename(path))
    except Exception as e:
        warn("anteprima non riuscita (%s)" % e)
    nmat = len(me.materials)
    parts = split_meshes(bpy, np, ob, max_verts)
    export_fbx(bpy, arm, parts + [ob1], out)
    log("scritto %s (%d triangoli, %d materiali, %d mesh)" % (os.path.basename(out), ntri, nmat, len(parts) + 1))
    log("mappatura salvata in %s" % os.path.basename(map_path))


def export_fbx(bpy, arm, objs, out):
    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm] + list(objs):
        o.select_set(True)
    for img in bpy.data.images:
        if img.source == 'FILE' and not img.packed_file:
            try:
                img.pack()
            except Exception:
                pass
    bpy.ops.export_scene.fbx(filepath=out, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', global_scale=1.0,
                             axis_forward='-Z', axis_up='Y', add_leaf_bones=False, primary_bone_axis='Y',
                             secondary_bone_axis='X', use_armature_deform_only=False, bake_anim=False,
                             mesh_smooth_type='FACE', use_mesh_modifiers=False, path_mode='COPY',
                             embed_textures=True, use_custom_props=True)


# ordine dei Node per riempire le mesh: zone vicine finiscono nella stessa mesh
SPLIT_ORDER = ["Node3", "Node4", "Node5", "Node6", "Node7", "Node8", "Node9", "Node10", "Node11", "Node12",
               "Node16", "Node13", "Node14", "Node15", "Node32", "Node33", "Node34", "Node35",
               "Node17", "Node18", "Node19", "Node28", "Node29", "Node30", "Node31",
               "Node20", "Node21", "Node22", "Node23", "Node24", "Node25", "Node26", "Node27", "Node1", "Node2"]


def split_meshes(bpy, np, ob, max_verts):
    """Divide Mesh0 in piu' mesh da al massimo max_verts vertici NBD ciascuna (come i personaggi originali:
    una mesh troppo grande non viene disegnata). Mesh0, poi Mesh2, Mesh3... (Mesh1 resta il segnaposto)."""
    if not max_verts or max_verts <= 0:
        return [ob]
    me = ob.data
    nl = len(me.loops)
    lv = np.zeros(nl, int)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(nl * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    try:
        nrm = np.array([c.vector[:] for c in me.corner_normals])        # Blender 4.1+
    except AttributeError:
        me.calc_normals_split()
        nrm = np.array([l.normal[:] for l in me.loops])
    # chiave del vertice NBD: posizione, UV, normale (i pesi seguono la posizione)
    keys = list(zip(lv, np.round(uv * 4096).astype(int).tolist(), np.round(nrm * 512).astype(int).tolist()))
    keys = [(a, tuple(b), tuple(c)) for a, b, c in keys]
    gname = {g.index: g.name for g in ob.vertex_groups}
    dom = []
    for v in me.vertices:
        g = max(v.groups, key=lambda x: x.weight, default=None)
        dom.append(gname[g.group] if g else "Node3")
    polys = me.polygons
    pnode = [dom[p.vertices[0]] if len({dom[x] for x in p.vertices}) == 3 else
             max(set(dom[x] for x in p.vertices), key=[dom[x] for x in p.vertices].count) for p in polys]
    groups = {}
    for fi, n in enumerate(pnode):
        groups.setdefault(n, []).append(fi)
    order = [n for n in SPLIT_ORDER if n in groups] + [n for n in groups if n not in SPLIT_ORDER]

    def nkeys(faces):
        return len({keys[l] for fi in faces for l in polys[fi].loop_indices})

    # gruppi troppo grandi da soli: tagliati a fette lungo l'altezza
    pieces = []
    cen = np.zeros((len(polys), 3))
    polys.foreach_get("center", cen.ravel())
    for n in order:
        fl = groups[n]
        if nkeys(fl) <= max_verts:
            pieces.append(fl)
            continue
        fl = sorted(fl, key=lambda f: cen[f][2])
        cur = []
        for f in fl:
            cur.append(f)
            if len(cur) % 50 == 0 and nkeys(cur) > max_verts * 0.95:
                pieces.append(cur)
                cur = []
        if cur:
            pieces.append(cur)
    chunks, cur, cur_keys = [], [], set()
    for fl in pieces:
        k = {keys[l] for fi in fl for l in polys[fi].loop_indices}
        if cur and len(cur_keys | k) > max_verts:
            chunks.append(cur)
            cur, cur_keys = [], set()
        cur = cur + fl
        cur_keys |= k
    if cur:
        chunks.append(cur)
    if len(chunks) == 1:
        log("mesh: %d vertici, una sola mesh (limite %d)" % (nkeys(chunks[0]), max_verts))
        return [ob]
    attr = np.zeros(len(polys), int)
    for ci, fl in enumerate(chunks):
        attr[fl] = ci
    sizes = [nkeys(fl) for fl in chunks]
    # separa le mesh 1..n dalla 0
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    me.attributes.new("_chunk", 'INT', 'FACE').data.foreach_set("value", attr)
    out = [ob]
    for ci in range(1, len(chunks)):
        a = np.zeros(len(ob.data.polygons), int)
        ob.data.attributes["_chunk"].data.foreach_get("value", a)
        ob.data.polygons.foreach_set("select", (a == ci).tolist())
        before = set(bpy.context.scene.objects)
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_mode(type='FACE')
        bpy.ops.object.mode_set(mode='OBJECT')
        ob.data.polygons.foreach_set("select", (a == ci).tolist())
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.separate(type='SELECTED')
        bpy.ops.object.mode_set(mode='OBJECT')
        new = [o for o in bpy.context.scene.objects if o not in before][0]
        out.append(new)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
    for o in out:
        if "_chunk" in o.data.attributes:
            o.data.attributes.remove(o.data.attributes["_chunk"])
    for i, o in enumerate(out):
        nm = "Mesh%d" % (0 if i == 0 else i + 1)               # Mesh1 = segnaposto occhi zombie
        o.name = nm
        o.data.name = nm
    log("mesh divise per restare sotto %d vertici: %s" % (
        max_verts, ", ".join("%s %d" % (o.name, n) for o, n in zip(out, sizes))))
    return out


def fix_fbx(src, out, max_verts):
    """Riprende un _OB.fbx gia' fatto (anche ritoccato a mano), divide le mesh se richiesto e lo riesporta."""
    import bpy
    import numpy as np
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=src)
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    meshes = sorted((o for o in bpy.data.objects if o.type == 'MESH'), key=lambda o: o.name)
    big = [o for o in meshes if o.name.split(".")[0] == "Mesh0"] or meshes[:1]
    rest = [o for o in meshes if o not in big]
    parts = split_meshes(bpy, np, big[0], max_verts)
    # le altre mesh (Mesh1 segnaposto...) dopo quelle nuove
    nxt = len(parts) + 1
    for o in rest:
        if o.name.split(".")[0] == "Mesh1":
            continue
        o.name = o.data.name = "Mesh%d" % nxt
        nxt += 1
    export_fbx(bpy, arm, parts + rest, out)
    log("scritto %s" % os.path.basename(out))


HEAD_NODES = {"Node21", "Node22", "Node23", "Node24", "Node25", "Node26", "Node27"}


def _img_array(np, img):
    """Immagine Blender -> array (h, w, 4) float 0..1, righe dal basso (come le UV)."""
    w, h = img.size
    if w == 0 or h == 0:
        return np.full((1, 1, 4), 0.5, np.float32)
    a = np.zeros(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def _sample(np, A, u, v):
    """Campionamento bilineare con ripetizione (wrap) di A in coordinate UV."""
    h, w = A.shape[:2]
    x = u * w - 0.5
    y = v * h - 0.5
    x0 = np.floor(x).astype(int)
    y0 = np.floor(y).astype(int)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    x0m, x1m = x0 % w, (x0 + 1) % w
    y0m, y1m = y0 % h, (y0 + 1) % h
    return ((A[y0m, x0m] * (1 - fx) + A[y0m, x1m] * fx) * (1 - fy) +
            (A[y1m, x0m] * (1 - fx) + A[y1m, x1m] * fx) * fy)


def _pack(sizes, W, H):
    """Impacchettamento "skyline" (in basso a sinistra): rettangoli (w, h) in W x H.
    -> lista di (x, y) oppure None se non ci stanno."""
    order = sorted(range(len(sizes)), key=lambda i: (-sizes[i][1], -sizes[i][0]))
    sky = [[0, 0, W]]                                    # segmenti [x, y, larghezza]
    pos = [None] * len(sizes)
    for i in order:
        w, h = sizes[i]
        best = None
        for si in range(len(sky)):
            x = sky[si][0]
            if x + w > W:
                break
            y, cover, k = 0, 0, si
            while cover < w:
                y = max(y, sky[k][1])
                cover += sky[k][2]
                k += 1
            if y + h <= H and (best is None or (y + h, x) < best[0]):
                best = ((y + h, x), x, y)
        if best is None:
            return None
        _, x, y = best
        pos[i] = (x, y)
        new, end = [], x + w
        for sx, sy, sw in sky:                             # aggiorna lo skyline
            if sx + sw <= x or sx >= end:
                new.append([sx, sy, sw])
                continue
            if sx < x:
                new.append([sx, sy, x - sx])
            if sx + sw > end:
                new.append([end, sy, sx + sw - end])
        new.append([x, y + h, w])
        new.sort()
        merged = []
        for seg in new:
            if merged and merged[-1][1] == seg[1] and merged[-1][0] + merged[-1][2] == seg[0]:
                merged[-1][2] += seg[2]
            else:
                merged.append(seg)
        sky = merged
    return pos


def make_atlas(bpy, np, ob, size_body, size_head, base):
    """Unisce tutte le texture in due atlas (corpo e testa) e rimappa le UV.
    Ogni texture contribuisce solo con la parte che il modello usa davvero (riquadro UV delle sue facce),
    texture ripetute comprese; lo spazio nell'atlas e' proporzionale ai texel originali usati."""
    me = ob.data
    nl = len(me.loops)
    uv = np.zeros(nl * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    nv = len(me.vertices)
    # vertici della testa: peso totale sui Node della testa >= 0.5
    headw = np.zeros(nv)
    hidx = {g.index for g in ob.vertex_groups if g.name in HEAD_NODES}
    for v in me.vertices:
        headw[v.index] = sum(g.weight for g in v.groups if g.group in hidx)
    pv = [list(p.vertices) for p in me.polygons]
    ploops = [list(p.loop_indices) for p in me.polygons]
    pmat = [p.material_index for p in me.polygons]
    is_head = [float(np.mean(headw[vs])) >= 0.5 for vs in pv]
    imgs = []
    for mat in me.materials:
        img = None
        if mat and mat.node_tree:
            img = next((n.image for n in mat.node_tree.nodes if n.type == 'TEX_IMAGE' and n.image), None)
        imgs.append(img)
    # pezzi: (materiale, gruppo) -> facce
    pieces = {}
    for fi, (mi, hd) in enumerate(zip(pmat, is_head)):
        pieces.setdefault((mi, hd), []).append(fi)
    arrays = {}
    plan = {False: [], True: []}
    for (mi, hd), fl in pieces.items():
        img = imgs[mi]
        if mi not in arrays:
            arrays[mi] = _img_array(np, img) if img else np.full((4, 4, 4), 0.8, np.float32)
        A = arrays[mi]
        L = np.array([li for fi in fl for li in ploops[fi]])
        lo, hi = uv[L].min(0), uv[L].max(0)
        th, tw = A.shape[:2]
        span = np.maximum(hi - lo, [1.0 / tw, 1.0 / th])
        tiles = float(np.prod(np.maximum(1.0, span)))
        plan[hd].append({"mi": mi, "faces": fl, "loops": L, "lo": lo, "span": span,
                         "texels": (span[0] * tw, span[1] * th), "tiles": tiles})
    PAD = 2
    out_imgs = {}
    for hd, size in ((False, size_body), (True, size_head)):
        items = plan[hd]
        if not items:
            continue
        # scala comune: la piu' grande che fa stare tutto (mai ingrandire oltre i texel originali)
        lo_k, hi_k = 0.0, 1.0
        best = None
        for _ in range(40):
            k = hi_k if best is None and _ == 0 else (lo_k + hi_k) / 2
            sizes = [(max(2, int(round(it["texels"][0] * k))) + 2 * PAD,
                      max(2, int(round(it["texels"][1] * k))) + 2 * PAD) for it in items]
            pos = _pack(sizes, size, size)
            if pos is not None:
                best = (k, sizes, pos)
                if _ == 0:
                    break
                lo_k = k
            else:
                hi_k = k
        if best is None:
            sizes = [(2 + 2 * PAD, 2 + 2 * PAD)] * len(items)
            pos = _pack(sizes, size, size)
            best = (0.0, sizes, pos)
            warn("atlas %s: troppi pezzi per %dx%d" % ("testa" if hd else "corpo", size, size))
        k, sizes, pos = best
        atlas = np.zeros((size, size, 4), np.float32)
        atlas[..., 3] = 1.0
        for it, (rw, rh), (x, y) in zip(items, sizes, pos):
            A = arrays[it["mi"]]
            iw, ih = rw - 2 * PAD, rh - 2 * PAD
            lo, span = it["lo"], it["span"]
            # pixel del rettangolo (bordo compreso) -> UV della texture originale
            jj = (np.arange(rw) - PAD + 0.5) / iw
            ii = (np.arange(rh) - PAD + 0.5) / ih
            U, V = np.meshgrid(lo[0] + jj * span[0], lo[1] + ii * span[1])
            ss = max(1, min(4, int(np.ceil(max(span[0] * A.shape[1] / iw, span[1] * A.shape[0] / ih)))))
            if ss > 1:                                     # riduzione forte: media di ss x ss campioni
                acc = 0
                for a in range(ss):
                    for b in range(ss):
                        acc = acc + _sample(np, A, U + (a + 0.5 - ss / 2) / ss * span[0] / iw,
                                            V + (b + 0.5 - ss / 2) / ss * span[1] / ih)
                block = acc / (ss * ss)
            else:
                block = _sample(np, A, U, V)
            atlas[y:y + rh, x:x + rw] = block
            # UV: riquadro originale -> parte interna del rettangolo
            L = it["loops"]
            uv[L, 0] = (x + PAD + (uv[L, 0] - lo[0]) / span[0] * iw) / size
            uv[L, 1] = (y + PAD + (uv[L, 1] - lo[1]) / span[1] * ih) / size
        name = "atlas_%s" % ("testa" if hd else "corpo")
        path = "%s_%s.png" % (base, "testa" if hd else "corpo")
        rgb = (np.clip(atlas[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)
        write_png(path, rgb)
        out_imgs[hd] = (name, path)
        log("atlas %s %dx%d: %d pezzi, scala %.0f%% dei texel originali -> %s"
            % ("testa" if hd else "corpo", size, size, len(items), 100 * k, os.path.basename(path)))
    me.uv_layers.active.data.foreach_set("uv", uv.ravel())
    # due materiali nuovi al posto dei vecchi
    newmats = {}
    old = list(me.materials)
    me.materials.clear()
    for hd in (False, True):
        if hd not in out_imgs:
            continue
        name, path = out_imgs[hd]
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(path)
        if bsdf:
            nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        me.materials.append(mat)
        newmats[hd] = len(me.materials) - 1
    me.polygons.foreach_set("material_index", [newmats[h] for h in is_head])
    for m in old:
        if m and m.users == 0:
            bpy.data.materials.remove(m)


def reduce_mesh(bpy, np, ob, max_tris, nodes):
    """Decimate 'Collapse' fino a <= max_tris triangoli; pesi rinormalizzati (max 4, < 1% via)."""
    import bmesh
    me = ob.data
    n0 = len(me.polygons)
    bm = bmesh.new()
    bm.from_mesh(me)
    before = len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    bm.to_mesh(me)
    bm.free()
    log("riduzione: %d triangoli > %d. Vertici saldati: %d -> %d" % (n0, max_tris, before, len(me.vertices)))
    # cuciture UV: il Decimate le rispetta
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    try:
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.seams_from_islands(mark_seams=True)
        bpy.ops.object.mode_set(mode='OBJECT')
    except Exception:
        bpy.ops.object.mode_set(mode='OBJECT')
    # Decimate uniforme: pesa l'errore geometrico, quindi i dettagli (viso, mani) si perdono per ultimi.
    # (Proteggere viso e mani con un vertex group sposta tutta la riduzione sul corpo e lo distrugge.)
    for attempt in range(3):
        cur = len(me.polygons)
        if cur <= max_tris:
            break
        mod = ob.modifiers.new("Decimate", 'DECIMATE')
        mod.decimate_type = 'COLLAPSE'
        mod.ratio = max(0.02, (max_tris * 0.97) / cur)
        mod.use_collapse_triangulate = True
        mod.use_symmetry = True
        mod.symmetry_axis = 'X'
        with bpy.context.temp_override(object=ob, active_object=ob):
            bpy.ops.object.modifier_apply(modifier=mod.name)
        log("  passo %d: %d -> %d triangoli" % (attempt + 1, cur, len(me.polygons)))
    if len(me.polygons) > max_tris:
        warn("non sono riuscito a scendere sotto %d (restano %d triangoli)" % (max_tris, len(me.polygons)))
    # normali: lisce con spigoli vivi oltre 60 gradi
    try:
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob],
                                       selected_editable_objects=[ob]):
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(60))
    except Exception:
        for p in me.polygons:
            p.use_smooth = True
    # pesi: max 4, < 1% via, normalizzati
    gid = {ob.vertex_groups[n].index: n for n in nodes}
    for v in me.vertices:
        ws = sorted(((g.weight, gid[g.group]) for g in v.groups if g.group in gid and g.weight > 0), reverse=True)
        keep = [(w, n) for w, n in ws[:4] if w >= 0.01] or ws[:1]
        tot = sum(w for w, _ in keep) or 1.0
        for w, n in ws:
            ob.vertex_groups[n].remove([v.index])
        for w, n in keep:
            ob.vertex_groups[n].add([v.index], w / tot, 'REPLACE')


TEST_POSE = {"Node13": ("Z", -62.0), "Node17": ("Z", 62.0), "Node14": ("Y", 28.0), "Node18": ("Y", -28.0),
             "Node4": ("X", -32.0), "Node5": ("X", 48.0), "Node7": ("X", 14.0), "Node8": ("X", 10.0),
             "Node10": ("Y", 10.0), "Node11": ("X", 8.0), "Node21": ("Y", -22.0),
             "Node33": ("Z", -40.0), "Node34": ("X", 50.0), "Node35": ("X", 70.0)}
TEST_MOVE = {"Node27": (0.0, -2.5, 0.0), "Node23": (0.0, 1.2, 0.0), "Node25": (0.0, 1.2, 0.0)}
NODE_COLORS = {}


def _node_color(n):
    if n not in NODE_COLORS:
        import colorsys
        k = int(n[4:])
        r, g_, b = colorsys.hsv_to_rgb((k * 0.381966) % 1.0, 0.75, 0.95)
        NODE_COLORS[n] = (int(r * 255), int(g_ * 255), int(b * 255))
    return NODE_COLORS[n]


def preview(bpy, np, arm, ob, path):
    """T-pose con lo scheletro, pesi colorati per osso (davanti), posa di prova (davanti e di lato)."""
    me = ob.data
    imgs = {}

    def tex_of(mi):
        mat = me.materials[mi] if mi < len(me.materials) else None
        img = None
        if mat and mat.node_tree:
            for n in mat.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image:
                    img = n.image
                    break
        if img is None:
            return None
        if img.name not in imgs:
            w, h = img.size
            a = np.array(img.pixels[:], np.float32).reshape(h, w, -1)
            imgs[img.name] = (a[::-1, :, :3] * 255).astype(np.uint8)
        return imgs[img.name]

    uvl = me.uv_layers.active.data if me.uv_layers.active else None
    cols, wcols = [], []
    gname = {g.index: g.name for g in ob.vertex_groups}
    dom = []
    for v in me.vertices:
        best = max(((g.weight, gname[g.group]) for g in v.groups), default=(0, "Node3"))
        dom.append(_node_color(best[1]))
    dom = np.array(dom, np.float32)
    for p in me.polygons:
        wcols.append(dom[list(p.vertices)].mean(0))
        t = tex_of(p.material_index)
        if t is None or uvl is None:
            cols.append((180, 180, 180))
            continue
        uv = np.mean([uvl[li].uv[:] for li in p.loop_indices], axis=0)
        h, w = t.shape[:2]
        cols.append(tuple(t[int((1 - uv[1] % 1.0) * h) % h, int((uv[0] % 1.0) * w) % w]))
    cols = np.array(cols, np.float32)
    wcols = np.array(wcols, np.float32)

    def geom():
        dg = bpy.context.evaluated_depsgraph_get()
        ev = ob.evaluated_get(dg)
        m = ev.to_mesh()
        P = np.array([v.co[:] for v in m.vertices])
        tris = [(list(p.vertices), i) for i, p in enumerate(m.polygons)]
        ev.to_mesh_clear()
        return P, tris

    def render(P, tris, yaw, colors, W=300, Hh=460, skel=None, zoom=None):
        th = math.radians(yaw)
        R = np.array([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])
        Q = P @ R.T
        if zoom is None:
            sc = min((Hh - 30) / max(1.0, P[:, 1].max()), (W - 16) / max(1.0, 2 * float(np.abs(Q[:, 0]).max())))
            cx, cy = 0.0, 0.0
        else:
            cx, cy, half = zoom
            sc = (W / 2 - 6) / half
        img = np.zeros((Hh, W, 3), np.float32)
        img[:] = (118, 126, 140)
        zb = np.full((Hh, W), -1e9, np.float32)
        L = np.array([0.35, 0.55, 0.75]) / np.linalg.norm([0.35, 0.55, 0.75])

        def sxy(p):
            if zoom is None:
                return W / 2 + p[..., 0] * sc, Hh - 15 - p[..., 1] * sc
            return W / 2 + (p[..., 0] - cx) * sc, Hh / 2 - (p[..., 1] - cy) * sc

        for vs, fi in tris:
            for j in range(1, len(vs) - 1):
                tri = Q[[vs[0], vs[j], vs[j + 1]]]
                n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
                ln = np.linalg.norm(n)
                if ln < 1e-12:
                    continue
                k = 0.45 + 0.55 * abs(float(n @ L) / ln)
                sx, sy = sxy(tri)
                x0, x1 = int(max(0, sx.min())), int(min(W - 1, sx.max() + 1))
                y0, y1 = int(max(0, sy.min())), int(min(Hh - 1, sy.max() + 1))
                if x1 < x0 or y1 < y0:
                    continue
                den = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
                if abs(den) < 1e-9:
                    continue
                gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
                w0 = ((sy[1] - sy[2]) * (gx - sx[2]) + (sx[2] - sx[1]) * (gy - sy[2])) / den
                w1 = ((sy[2] - sy[0]) * (gx - sx[2]) + (sx[0] - sx[2]) * (gy - sy[2])) / den
                w2 = 1 - w0 - w1
                ok = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
                z = w0 * tri[0, 2] + w1 * tri[1, 2] + w2 * tri[2, 2]
                sub = zb[y0:y1 + 1, x0:x1 + 1]
                win = ok & (z > sub)
                img[y0:y1 + 1, x0:x1 + 1][win] = colors[fi] * k
                sub[win] = z[win]
        if skel is not None:
            S = skel @ R.T
            for n, par in PARENTS.items():
                if par is None:
                    continue
                a, b = S[BONE_ORDER.index(n)], S[BONE_ORDER.index(par)]
                for t in np.linspace(0, 1, 40):
                    x, y = sxy(a * (1 - t) + b * t)
                    x, y = int(x), int(y)
                    if 0 <= x < W and 0 <= y < Hh:
                        img[max(0, y - 1):y + 1, max(0, x - 1):x + 1] = (255, 60, 40)
            for p in S:
                x, y = sxy(p)
                x, y = int(x), int(y)
                img[max(0, y - 2):y + 3, max(0, x - 2):x + 3] = (255, 230, 40)
        return np.clip(img, 0, 255).astype(np.uint8)

    P, tris = geom()
    skel = np.array([SKEL[n] for n in BONE_ORDER], float)
    head = np.array(SKEL["Node21"])
    row = [render(P, tris, 0, cols, W=460, skel=skel), render(P, tris, 0, wcols, W=460),
           render(P, tris, 0, wcols, W=230, Hh=230, zoom=(0.0, head[1] + 5.0, 13.0))]
    for n, (ax, deg) in TEST_POSE.items():
        e = [0.0, 0.0, 0.0]
        e["XYZ".index(ax)] = math.radians(deg)
        arm.pose.bones[n].rotation_euler = e
    for n, loc in TEST_MOVE.items():
        arm.pose.bones[n].location = loc
    bpy.context.view_layer.update()
    P2, tris2 = geom()
    row += [render(P2, tris2, 0, cols), render(P2, tris2, 90, cols),
            render(P2, tris2, 0, wcols, W=230, Hh=230, zoom=(0.0, head[1] + 5.0, 13.0))]
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    Hh = max(r.shape[0] for r in row)
    row = [np.pad(r, ((0, Hh - r.shape[0]), (0, 0), (0, 0)), constant_values=40) for r in row]
    write_png(path, np.concatenate(row, axis=1))


def write_png(path, rgb):
    import zlib
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    if argv and argv[0] == "--fixfbx":
        try:
            fix_fbx(argv[1], argv[2], int(argv[3]))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("XPS2OB ERRORE: %s" % e)
            sys.exit(2)
        return 0
    if argv and argv[0] == "--xps2ob":
        try:
            convert(argv[1], argv[2], int(argv[3]) if len(argv) > 3 else 11000,
                    int(argv[4]) if len(argv) > 4 else 512, int(argv[5]) if len(argv) > 5 else 256,
                    int(argv[6]) if len(argv) > 6 else 0)
        except (XpsError, RuntimeError) as e:
            print("XPS2OB ERRORE: %s" % e)
            sys.exit(2)
        except Exception as e:
            import traceback
            traceback.print_exc()
            print("XPS2OB ERRORE: %s" % e)
            sys.exit(2)
        return 0
    return launcher(argv)


if __name__ == "__main__":
    sys.exit(main())
