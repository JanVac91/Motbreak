#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daz2ob.py - Personaggio DAZ Genesis 8 (FBX) -> FBX pronto per RE Outbreak (scheletro Node0..Node35)
==================================================================================================

USO
    python daz2ob.py                 apre la finestra (serve Blender 4.1 o piu' recente installato)
    python daz2ob.py --job lavoro.json      conversione senza finestra (il JSON lo salva la finestra)
    python daz2ob.py --job lavoro.json --nbd     ... e poi anche gli NBD

Cartelle: tutto va in  personaggi/<nome>/  accanto a daz2ob.py: <nome>.json (outfit e scelte, si riapre
dall'elenco "Personaggio") e una sottocartella per ogni outfit con FBX, texture, anteprima e NBD.
Anteprima 3D: pulsante "Anteprima 3D nel browser": l'outfit finito (riduzioni, pulizia, capelli, ciglia) con
pose di prova; si aggiorna da sola quando cambi qualcosa nella finestra (pochi secondi; il corpo si prepara
una volta sola, circa mezzo minuto). Non salva niente.
NBD: copia fbx2nbd.py accanto a daz2ob.py; dopo la conversione (o col pulsante "Converti in NBD") ogni FBX
diventa un NBD con scheletro e materiali come i personaggi originali.

Cosa fa (tutto in Blender, in background)
  1. importa l'FBX esportato da DAZ (Genesis 8 / 8.1, con i vestiti)
  2. mette il personaggio in T-pose con lo scheletro DAZ (braccia e gambe allineate a quelle di Outbreak)
  3. pesi: ogni osso DAZ viene sommato sul Node Outbreak (tabella DAZ_MAP qui sotto), es.
     sopracciglio centrale -> Node23/25, interno/esterno al 30% (il resto alla testa), palpebre superiori
     -> Node24/26, mascella, labbro inferiore, mento, lingua -> Node27, dita -> Node33/34/35 e 29/30/31
  4. adatta il modello allo scheletro Outbreak (fisso, non si tocca): scala, poi braccia e gambe portate sulle
     ossa OB; braccia centrate sulle ossa, spalle alzate (8 gradi, regolabile) e polso come P06 (anello
     meta' Node15 e meta' Node32: il polso non si rompe)
  5. corpo DAZ diviso in zone, ognuna ridotta al suo numero di triangoli SENZA toccare i bordi tra le
     zone (niente crepe tra faccia e corpo): corpo 4500, faccia 2880, orecchie 200, unghie 450,
     bocca 70, eyesocket 60 (solo gli angoli verso il naso), occhi quasi intatti (via la parte dietro).
     Eliminati: denti, ciglia, eye moisture, cornea (in DAZ e' trasparente).
     Normali copiate dal modello originale: il modello ridotto resta liscio.
  6. texture: atlas 512 per corpo, faccia, occhi (e capelli), atlas 256 per ogni outfit. Braccio e gamba
     destri usano la texture di quelli sinistri (come fai a mano), cosi' c'e' piu' spazio per il resto.
  7. per ogni outfit scelto nella finestra un FBX: Mesh0 faccia, Mesh1 segnaposto (o il capo scelto),
     Mesh2 corpo, Mesh3 orecchie, poi occhi, unghie, eyesocket, bocca, capelli, vestiti.
     Opzione: toglie il corpo nascosto sotto i vestiti di quell'outfit.
     Espressione neutra (scheda con le opzioni del viso): angoli della bocca e sopracciglia su/giu' in mm,
     simmetrici; la faccia prende quella forma prima della conversione (scheletro OB invariato).
     Pulsante "Colore" di ogni capo: texture personalizzata (stessa UV dell'originale) e colore di tutto
     il capo, per quell'outfit (nell'anteprima 3D il colore cambia subito).
     Materiali: ambient 20,20,20, diffuse 255,255,255, speculare 0.
  8. accanto a ogni FBX: le texture PNG, un'anteprima (davanti, dietro, viso, posa di prova) e un
     resoconto con triangoli e vertici di ogni mesh.

  9. strati: i capi interni vengono spinti sotto quelli esterni e le parti coperte tolte (ordine automatico
     per distanza dalla pelle, modificabile con le frecce); per ogni capo si sceglie se toglie la pelle
     sotto; la pelle si toglie solo nelle zone scelte e lasciando un bordo attorno a scolli e orli.
 11. per ogni capo dell'outfit: "Posizione..." (spostamento e scala, es. anelli e bracciali fuori posto) e
     "Rigido" (accessori: ogni pezzo si muove come un blocco unico sul suo osso, senza deformarsi).
 10. capi trasparenti (opacita' 0-100) e ciglia: due texture per outfit in tutto. Le ciglia stanno nell'atlas
     del corpo, i capi trasparenti in quello dei vestiti; l'alpha c'e' solo li' e le loro mesh hanno un
     materiale "_trasp" che usa la stessa immagine (come in 3ds Max). Mesh trasparenti in fondo all'elenco.
"""
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zlib

__version__ = "3.2.1"
TAG = "DAZ2OB "

# ------------------------------------------------------------------------------------------------
# Scheletro Outbreak (cm, Y su, fronte +Z) - identico a xps2outbreak / personaggi originali
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


def group_id(name):
    k = int(name[4:])
    return 0 if k <= 9 else 1 if k <= 21 else 2 if k <= 27 else 3 if k <= 31 else 4


# ------------------------------------------------------------------------------------------------
# Ossa DAZ Genesis 8 -> Node Outbreak.  Valore: Node, oppure lista [(Node, quota), ...] (somma 1).
# Chiave senza lato: "l"/"r" davanti al nome (lShin) sceglie il Node sinistro/destro (L, R).
# Ossa non in tabella: seguono il genitore (sopra il collo: testa, Node21).
# ------------------------------------------------------------------------------------------------
def _lr(l, r):
    return {"L": l, "R": r}


DAZ_MAP = {
    "hip": "Node3", "pelvis": "Node3",
    "ThighBend": _lr("Node4", "Node7"), "ThighTwist": _lr("Node4", "Node7"),
    "Shin": _lr("Node5", "Node8"),
    "Foot": _lr("Node6", "Node9"), "Metatarsals": _lr("Node6", "Node9"), "Toe": _lr("Node6", "Node9"),
    "BigToe": _lr("Node6", "Node9"), "SmallToe1": _lr("Node6", "Node9"), "SmallToe2": _lr("Node6", "Node9"),
    "SmallToe3": _lr("Node6", "Node9"), "SmallToe4": _lr("Node6", "Node9"),
    "abdomenLower": "Node10", "abdomenUpper": "Node11", "chestLower": "Node11", "chestUpper": "Node11",
    "Pectoral": _lr("Node11", "Node11"),
    "Collar": _lr("Node12", "Node16"),
    "ShldrBend": _lr("Node13", "Node17"), "ShldrTwist": _lr("Node13", "Node17"),
    "ForearmBend": _lr("Node14", "Node18"), "ForearmTwist": _lr("Node14", "Node18"),
    "Hand": _lr("Node32", "Node28"),                       # palmo (nei personaggi OB Node15 = solo polso)
    "Carpal1": _lr("Node32", "Node28"), "Carpal2": _lr("Node32", "Node28"),
    "Carpal3": _lr("Node32", "Node28"), "Carpal4": _lr("Node32", "Node28"),
    "Thumb1": _lr("Node33", "Node29"), "Thumb2": _lr("Node33", "Node29"), "Thumb3": _lr("Node33", "Node29"),
    "Index1": _lr("Node34", "Node30"), "Index2": _lr("Node34", "Node30"), "Index3": _lr("Node34", "Node30"),
    "Mid1": _lr("Node34", "Node30"), "Mid2": _lr("Node34", "Node30"), "Mid3": _lr("Node34", "Node30"),
    "Ring1": _lr("Node35", "Node31"), "Ring2": _lr("Node35", "Node31"), "Ring3": _lr("Node35", "Node31"),
    "Pinky1": _lr("Node35", "Node31"), "Pinky2": _lr("Node35", "Node31"), "Pinky3": _lr("Node35", "Node31"),
    "neckLower": "Node20", "neckUpper": "Node21", "head": "Node21",
    "upperFaceRig": "Node21", "lowerFaceRig": "Node21", "upperTeeth": "Node21",
    # mascella: tutto quello che si apre con la bocca
    "lowerJaw": "Node27", "lowerTeeth": "Node27", "tongue01": "Node27", "tongue02": "Node27",
    "tongue03": "Node27", "tongue04": "Node27", "Chin": "Node27", "BelowJaw": "Node27",
    "LipLowerMiddle": "Node27", "LipLowerInner": _lr("Node27", "Node27"), "LipLowerOuter": _lr("Node27", "Node27"),
    "LipBelow": "Node27",
    # zone di passaggio: in parte con la mascella
    "LipCorner": "MIX:Node27:0.5",
    "NasolabialMouthCorner": "MIX:Node27:0.3", "NasolabialLower": "MIX:Node27:0.5",
    "CheekLower": "MIX:Node27:0.3", "JawClench": "MIX:Node27:0.5",
    # sopracciglia: centrale tutto, interno/esterno in parte (BROW_SIDE, dalla finestra)
    "BrowMid": _lr("Node23", "Node25"), "BrowInner": "BROW", "BrowOuter": "BROW", "CenterBrow": "Node21",
    # palpebre superiori -> Node24/26; angoli e palpebre inferiori restano con la testa
    "EyelidUpper": _lr("Node24", "Node26"), "EyelidUpperInner": _lr("Node24", "Node26"),
    "EyelidUpperOuter": _lr("Node24", "Node26"),
    "EyelidInner": "Node21", "EyelidOuter": "Node21", "EyelidLower": "Node21",
    "EyelidLowerInner": "Node21", "EyelidLowerOuter": "Node21",
    "Eye": "Node21", "Ear": "Node21",
}
FACE_REST = ("MidNoseBridge", "SquintInner", "SquintOuter", "CheekUpper", "Nose", "Nostril", "LipBelowNose",
             "LipNasolabialCrease", "NasolabialUpper", "NasolabialMiddle", "LipUpperMiddle", "LipUpperOuter",
             "LipUpperInner")
for _k in FACE_REST:
    DAZ_MAP.setdefault(_k, "Node21")


def _split_side(name):
    """'lShldrBend' -> ('L', 'ShldrBend'); 'lowerJaw' -> (None, 'lowerJaw')."""
    nm = re.sub(r"(\.\d+|_\d+)$", "", name)
    if nm in DAZ_MAP:
        return None, nm
    if len(nm) > 1 and nm[0] in "lr" and nm[1].isupper() and nm[1:] in DAZ_MAP:
        return nm[0].upper(), nm[1:]
    return None, nm


LIP27 = [1.0]           # quota di LipLowerMiddle sulla mascella (Node27); il resto alla testa


def daz_lookup(name, brow_side=0.3):
    """Osso DAZ -> [(Node, quota)] oppure None (non riconosciuto)."""
    side, key = _split_side(name)
    if key not in DAZ_MAP:
        return None
    if key == "LipLowerMiddle" and LIP27[0] < 1.0:
        q = max(0.0, LIP27[0])
        return [("Node27", q), ("Node21", 1.0 - q)] if q > 0 else [("Node21", 1.0)]
    v = DAZ_MAP[key]
    if isinstance(v, dict):
        return [(v[side or "L"], 1.0)]
    if v == "BROW":
        n = "Node23" if side != "R" else "Node25"
        return [(n, brow_side), ("Node21", 1.0 - brow_side)] if brow_side < 1.0 else [(n, 1.0)]
    if v.startswith("MIX:"):
        _, node, q = v.split(":")
        q = float(q)
        return [(node, q), ("Node21", 1.0 - q)]
    return [(v, 1.0)]


# zone del corpo Genesis 8 (nomi dei materiali DAZ) -> parti finali
PARTS = [("face", ("Face", "Lips")), ("body", ("Torso", "Arms", "Legs")), ("ears", ("Ears",)),
         ("eyes", ("Sclera", "Irises", "Pupils")), ("nails", ("Fingernails", "Toenails")),
         ("eyesocket", ("EyeSocket",)), ("mouth", ("Mouth",))]
DELETE_ZONES = ("Teeth", "EyeMoisture", "Cornea")
# preset: (triangoli corpo e faccia, triangoli vestiti per outfit)
PRESETS = {"Outbreak": (6000, 2000), "Normale": (8000, 3000), "HD": (9000, 4000)}
# come si divide il totale "corpo e faccia" tra le zone
ZONE_SHARE = [("face", 0.33), ("body", 0.43), ("feet", 0.09), ("nails", 0.05), ("eyes", 0.055),
              ("ears", 0.023), ("mouth", 0.008), ("eyesocket", 0.007)]
ZONE_LABEL = {"face": "faccia", "body": "corpo", "feet": "piedi", "nails": "unghie", "eyes": "occhi",
              "ears": "orecchie", "mouth": "bocca", "eyesocket": "eyesocket"}
HAIR_LEVELS = [("Bassi", 500), ("Medi", 750), ("Alti", 1000)]     # lavori vecchi (ora: percentuale)
HAIR_LIB_MAX = 2500     # capelli aggiunti alla libreria: al massimo tanti triangoli


def preset_targets(total):
    tot = sum(q for _, q in ZONE_SHARE)
    return {k: int(round(total * q / tot)) for k, q in ZONE_SHARE}


DEFAULT_TARGETS = preset_targets(8000)
# densita' relativa nell'atlas (lo spazio va con la radice)
IMPORTANCE = {"Face": 14.0, "Lips": 14.0, "Sclera": 10.0, "Irises": 30.0, "Pupils": 10.0, "Ears": 2.0,
              "EyeSocket": 2.0, "Mouth": 0.5, "Teeth": 0.8, "Fingernails": 0.3, "Toenails": 0.3, "hair": 2.0}
PART_ORDER = ["face", "MESH1", "body", "ears", "eyes", "nails", "eyesocket", "mouth", "hair"]
DEFAULT_JOB = {"targets": DEFAULT_TARGETS, "preset": "Normale", "budget_limit": 12000, "atlas_base": 512, "atlas_outfit": 256, "mirror_limbs": True,
               "brow_side": 0.3, "hair_file": "", "hair_tex": "", "hair_reserve": 128, "outfits": [],
               "preview": True, "ambient": 20, "margin_mm": 3.0, "joint_smooth": 1.0,
               "weights_from_body": True}


def zone_name(matname):
    return re.sub(r"(\.\d+)$", "", matname or "")


def clean_name(objname):
    s = re.sub(r"\.\d+$", "", objname)
    s = re.sub(r"\.Shape$", "", s)
    s = re.sub(r"_\d+$", "", s)
    return s.strip() or objname


# ================================================================================================
#                                     DENTRO BLENDER
# ================================================================================================
def log(msg):
    print(TAG + msg, flush=True)


def warn(msg):
    print(TAG + "ATTENZIONE: " + msg, flush=True)


PNG_LEVEL = [9]          # compressione dei PNG (l'anteprima usa 1: piu' veloce)


def write_png(path, rgb):
    h, w = rgb.shape[:2]
    ct = 6 if (rgb.ndim == 3 and rgb.shape[2] == 4) else 2          # RGBA o RGB
    raw = b"".join(b"\x00" + rgb[y].tobytes() for y in range(h))

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ct, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, PNG_LEVEL[0])) + chunk(b"IEND", b""))


def read_png_rgb(path):
    """PNG/JPG -> array (h, w, 3) uint8, riga 0 = alto (usa Blender per leggerlo)."""
    import bpy
    import numpy as np
    img = bpy.data.images.load(path)
    a = _img_array(img, 4096)
    bpy.data.images.remove(img)
    return (np.clip(a[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)


def _img_array(img, maxdim=1024):
    """Immagine Blender -> array (h, w, 4) float32, righe dal basso (come le UV). Ridotta a maxdim."""
    import numpy as np
    w, h = img.size
    if w == 0 or h == 0:
        return None
    if max(w, h) > maxdim:
        k = maxdim / float(max(w, h))
        img.scale(max(1, int(w * k)), max(1, int(h * k)))
        w, h = img.size
    a = np.zeros(w * h * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(h, w, 4)


def bl_to_ob(np, P):
    """Mondo Blender (m, Z su, fronte -Y) -> Outbreak (cm, Y su, fronte +Z)."""
    return np.c_[P[:, 0], P[:, 2], -P[:, 1]] * 100.0


def world_coords(np, o):
    me = o.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    M = np.array(o.matrix_world)
    return co @ M[:3, :3].T + M[:3, 3]


def material_image(mat):
    """(immagine del colore, colore RGB) del materiale."""
    if mat is None:
        return None, (0.8, 0.8, 0.8)
    col = (0.8, 0.8, 0.8)
    img = None
    if mat.node_tree:
        bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf:
            inp = bsdf.inputs.get("Base Color")
            if inp is not None:
                if inp.is_linked:
                    nd = inp.links[0].from_node
                    if nd.type == 'TEX_IMAGE' and nd.image:
                        img = nd.image
                else:
                    col = tuple(inp.default_value[:3])
        if img is None:
            for n in mat.node_tree.nodes:
                if n.type == 'TEX_IMAGE' and n.image and any(l.to_socket.name == "Base Color"
                                                              for l in n.outputs[0].links):
                    img = n.image
    else:
        col = tuple(mat.diffuse_color[:3])
    return img, col


def find_scene_parts(bpy):
    arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not arms or not meshes:
        raise RuntimeError("nell'FBX non trovo l'armatura o le mesh di DAZ")

    def score(o):
        zs = {zone_name(m.name) for m in o.data.materials if m}
        return (len(zs & {"Face", "Torso", "Arms", "Legs"}), len(o.vertex_groups))
    body = max(meshes, key=score)
    if score(body)[0] < 3:
        raise RuntimeError("non trovo il corpo Genesis 8 (materiali Face, Torso, Arms, Legs)")
    arm = body.find_armature() or arms[0]
    lashes, others = [], []
    for o in meshes:
        if o is body:
            continue
        if "eyelash" in o.name.lower() or "brow" in clean_name(o.name).lower():
            lashes.append(o)
        else:
            others.append(o)
    return arm, body, lashes, others


def is_hair(o):
    n = o.name.lower()
    if "hair" in n or "capell" in n or "ponytail" in n:
        return True
    bones = [g.name for g in o.vertex_groups]
    return bool(bones) and all(_split_side(b)[1] in ("head", "neckUpper", "neckLower", "chestUpper") or
                               daz_lookup(b) is None for b in bones) and len(o.data.polygons) > 20000


# ------------------------------------------------------------------------------------------------
# Analisi (per la finestra): elenco dei capi con miniature
# ------------------------------------------------------------------------------------------------
def scan(fbx, outdir):
    import bpy
    import numpy as np
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(outdir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log("leggo %s" % os.path.basename(fbx))
    bpy.ops.import_scene.fbx(filepath=fbx)
    arm, body, lashes, others = find_scene_parts(bpy)
    zones = {}
    pm = np.zeros(len(body.data.polygons), int)
    body.data.polygons.foreach_get("material_index", pm)
    for i, m in enumerate(body.data.materials):
        zones[zone_name(m.name if m else "")] = zones.get(zone_name(m.name if m else ""), 0) + int((pm == i).sum())
    PB = bl_to_ob(np, world_coords(np, body))
    FB = tri_faces(body.data)
    sil = None
    try:
        sil = raster(np, PB, FB, 120, 200, None, mid=PB)
    except Exception as e:
        warn("miniature non create (%s)" % e)
    items = []
    names = set()
    bvh_body = None
    try:
        from mathutils.bvhtree import BVHTree
        bvh_body = BVHTree.FromPolygons([tuple(p) for p in PB], [tuple(f) for f in FB])
    except Exception as e:
        warn("distanza dei capi dalla pelle non calcolata (%s)" % e)
    for o in sorted(others, key=lambda o: clean_name(o.name).lower()):
        nm = clean_name(o.name)
        base, k = nm, 2
        while nm in names:
            nm = "%s (%d)" % (base, k)
            k += 1
        names.add(nm)
        tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
        thumb = ""
        if sil is not None and tris < 120000:
            try:
                P = bl_to_ob(np, world_coords(np, o))
                F = tri_faces(o.data)
                if len(F) > 40000:
                    F = F[::max(1, len(F) // 40000)]
                img = raster(np, P, F, 120, 200, sil, mid=PB, color=(235, 140, 60))
                thumb = os.path.join(outdir, "thumb_%03d.png" % len(items))
                write_png(thumb, img)
            except Exception as e:
                warn("miniatura di %s non riuscita (%s)" % (nm, e))
        depth = 0.0
        if bvh_body is not None:
            # distanza media dalla pelle: dice in che ordine stanno i capi (dall'interno all'esterno)
            Pg = bl_to_ob(np, world_coords(np, o))
            dd = []
            for p in Pg[::max(1, len(Pg) // 600)]:
                hit = bvh_body.find_nearest(tuple(p), 40.0)
                dd.append(hit[3] if hit[0] is not None else 40.0)
            depth = round(float(np.mean(dd)), 3) if dd else 0.0
        items.append({"name": nm, "object": o.name, "tris": tris, "verts": len(o.data.vertices), "depth": depth,
                      "lens": [o.data.materials[i].name for i in lens_materials(o)],
                      "materials": [m.name for m in o.data.materials if m], "hair": is_hair(o), "thumb": thumb})
        log("capo: %s (%d triangoli)" % (nm, tris))
    res = {"version": __version__, "fbx": fbx, "armature": arm.name, "bones": len(arm.data.bones),
           "body": body.name, "body_zones": zones, "eyelashes": [o.name for o in lashes], "garments": items}
    # testa adattata allo scheletro OB: serve all'anteprima dei capelli nella finestra
    try:
        for o in lashes + others:
            bpy.data.objects.remove(o, do_unlink=True)
        log("preparo la testa per l'anteprima dei capelli...")
        prepare(bpy, np, arm, body, [], 0.3, 0.0)
        T = body_arrays(np, body)
        np.savez_compressed(os.path.join(outdir, "head.npz"), V=T["V"], F=T["F"], N=T["N"], DOM=T["DOM"])
        res["head"] = os.path.join(outdir, "head.npz")
        res["look"] = make_look_mesh(bpy, np, body, os.path.join(outdir, "look.npz"))
    except Exception as e:
        warn("testa per l'anteprima non preparata (%s)" % e)
    with open(os.path.join(outdir, "scan.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, ensure_ascii=False)
    log("analisi finita: %d capi" % len(items))


def tri_faces(me):
    import numpy as np
    out = []
    for p in me.polygons:
        vs = list(p.vertices)
        for j in range(1, len(vs) - 1):
            out.append((vs[0], vs[j], vs[j + 1]))
    return np.array(out, int).reshape(-1, 3)


def raster(np, P, F, W, H, base, mid, color=(150, 150, 155)):
    """Miniatura frontale: base = immagine precedente (zbuffer incluso) su cui disegnare."""
    lo, hi = mid.min(0), mid.max(0)
    sc = min((H - 10) / max(1e-6, hi[1] - lo[1]), (W - 8) / max(1e-6, hi[0] - lo[0]))
    sx = W / 2 + (P[:, 0] - (lo[0] + hi[0]) / 2) * sc
    sy = H - 5 - (P[:, 1] - lo[1]) * sc
    if base is None:
        img = np.zeros((H, W, 3), np.float32)
        img[:] = (40, 44, 52)
        zb = np.full((H, W), -1e30, np.float32)
    else:
        img, zb = base[0].astype(np.float32).copy(), base[1].copy()
        img = img * 0.55 + np.array([40, 44, 52]) * 0.45            # corpo smorzato sotto il capo
    L = np.array([0.3, 0.5, 0.8])
    L /= np.linalg.norm(L)
    T = P[F]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    sh = 0.35 + 0.65 * np.abs(n @ L) / (np.linalg.norm(n, axis=1) + 1e-12)
    col = np.array(color, np.float32)
    for i in range(len(F)):
        X = sx[F[i]]
        Y = sy[F[i]]
        x0, x1 = max(0, int(X.min())), min(W - 1, int(X.max()) + 1)
        y0, y1 = max(0, int(Y.min())), min(H - 1, int(Y.max()) + 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((Y[1] - Y[2]) * (gx - X[2]) + (X[2] - X[1]) * (gy - Y[2])) / den
        w1 = ((Y[2] - Y[0]) * (gx - X[2]) + (X[0] - X[2]) * (gy - Y[2])) / den
        w2 = 1 - w0 - w1
        ok = (w0 >= -0.01) & (w1 >= -0.01) & (w2 >= -0.01)
        z = w0 * T[i, 0, 2] + w1 * T[i, 1, 2] + w2 * T[i, 2, 2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        win = ok & (z > sub)
        img[y0:y1 + 1, x0:x1 + 1][win] = col * sh[i]
        sub[win] = z[win]
    out = np.clip(img, 0, 255).astype(np.uint8)
    if base is None:
        return out, zb
    return out


# ------------------------------------------------------------------------------------------------
# T-pose con lo scheletro DAZ
# ------------------------------------------------------------------------------------------------
def ob_dir_to_bl(v):
    from mathutils import Vector
    return Vector((v[0], -v[2], v[1]))


def tpose(bpy, arm, shoulder_lift=0.0):
    from mathutils import Matrix, Quaternion
    pb = arm.pose.bones
    mw = arm.matrix_world

    def turn(bn, axis_ob, deg):
        if bn not in pb or not deg:
            return
        h = mw @ pb[bn].head
        q = Quaternion(ob_dir_to_bl(axis_ob), math.radians(deg))
        R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
        pb[bn].matrix = mw.inverted() @ R @ mw @ pb[bn].matrix
        bpy.context.view_layer.update()

    # spalle piu' alte (come fai in 3ds Max): clavicola su di N gradi; il braccio viene poi rimesso
    # orizzontale qui sotto (= compensato di -N gradi), cosi' sale solo la spalla
    if shoulder_lift:
        turn("lCollar", (0.0, 0.0, 1.0), shoulder_lift)
        turn("rCollar", (0.0, 0.0, 1.0), -shoulder_lift)

    def aim(bn, child, a, b):
        if bn not in pb or child not in pb:
            warn("osso %s o %s mancante: T-pose incompleta" % (bn, child))
            return
        h = mw @ pb[bn].head
        c = mw @ pb[child].head
        cur = (c - h)
        tgt = ob_dir_to_bl(tuple(SKEL[b][i] - SKEL[a][i] for i in range(3)))
        if cur.length < 1e-9:
            return
        q = cur.normalized().rotation_difference(tgt.normalized())
        R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
        pb[bn].matrix = mw.inverted() @ R @ mw @ pb[bn].matrix
        bpy.context.view_layer.update()
        return math.degrees(q.angle)

    done = []
    for s, n in (("l", ("Node13", "Node14", "Node15")), ("r", ("Node17", "Node18", "Node19"))):
        a = aim(s + "ShldrBend", s + "ForearmBend", n[0], n[1])
        b = aim(s + "ForearmBend", s + "Hand", n[1], n[2])
        done.append("%s braccio %.0f / avambraccio %.0f gradi" % ("SX" if s == "l" else "DX", a or 0, b or 0))
    for s, n in (("l", ("Node4", "Node5", "Node6")), ("r", ("Node7", "Node8", "Node9"))):
        a = aim(s + "ThighBend", s + "Shin", n[0], n[1])
        b = aim(s + "Shin", s + "Foot", n[1], n[2])
        done.append("%s coscia %.0f / stinco %.0f gradi" % ("SX" if s == "l" else "DX", a or 0, b or 0))
    log("T-pose: " + ", ".join(done) + (", spalle alzate di %.0f gradi" % shoulder_lift if shoulder_lift else ""))


FACE_PRESETS = [("Neutra", {}),
                ("Sorriso leggero", {"mouth": 1.5, "brow_mid": 0.5}),
                ("Sorriso", {"mouth": 3.0, "brow_in": 0.5, "brow_mid": 1.0, "brow_out": 0.5}),
                ("Serio", {"mouth": -0.5, "brow_in": -1.0, "brow_mid": -0.5}),
                ("Triste", {"mouth": -2.0, "brow_in": 2.5, "brow_mid": 0.5, "brow_out": -1.5}),
                ("Preoccupato", {"mouth": -1.0, "brow_in": 2.0, "brow_mid": 1.0, "brow_out": -0.5}),
                ("Arrabbiato", {"mouth": -1.5, "brow_in": -3.0, "brow_mid": -1.0, "brow_out": 1.0}),
                ("Sorpreso", {"brow_in": 3.0, "brow_mid": 3.5, "brow_out": 2.5}),
                ("Annoiato", {"mouth": -1.0, "brow_in": -1.0, "brow_mid": -1.5, "brow_out": -1.5})]
FACE_KEYS = [("mouth", "Angoli della bocca", "su = sorriso, giu' = broncio"),
             ("brow_in", "Sopracciglia interne", "su = triste/sorpreso, giu' = arrabbiato"),
             ("brow_mid", "Sopracciglia centrali", ""),
             ("brow_out", "Sopracciglia esterne", "giu' = triste")]
# ossa DAZ mosse da ogni cursore: (osso senza l/r, quota del movimento); su = +Y Outbreak, in mm
FACE_BONES = {"mouth": [("LipCorner", 1.0), ("LipUpperOuter", 0.35), ("LipLowerOuter", 0.45)],
              "brow_in": [("BrowInner", 1.0)],
              "brow_mid": [("BrowMid", 1.0)],
              "brow_out": [("BrowOuter", 1.0)]}


def face_expression(bpy, arm, fx):
    """Espressione neutra: sposta su/giu' le ossa del viso DAZ (simmetriche) prima di congelare la posa.
    fx = {"mouth": mm, "brow_in": mm, "brow_mid": mm, "brow_out": mm}. Lo scheletro Outbreak non cambia."""
    from mathutils import Matrix
    fx = {k: float(v) for k, v in (fx or {}).items() if k in FACE_BONES and abs(float(v or 0)) > 1e-3}
    if not fx:
        return
    pb = arm.pose.bones
    mw = arm.matrix_world
    moved = {}
    for k, mm in fx.items():
        for b, q in FACE_BONES[k]:
            for side in ("l", "r"):
                moved[side + b] = moved.get(side + b, 0.0) + mm * q
        if k == "brow_in":
            moved["CenterBrow"] = moved.get("CenterBrow", 0.0) + mm * 0.5
    miss = []
    for bn, mm in moved.items():
        if bn not in pb:
            miss.append(bn)
            continue
        d = ob_dir_to_bl((0.0, mm / 1000.0, 0.0))          # mm -> m (mondo Blender)
        pb[bn].matrix = mw.inverted() @ Matrix.Translation(d) @ mw @ pb[bn].matrix
        bpy.context.view_layer.update()
    log("espressione neutra: %s" % ", ".join("%s %+.1f mm" % (dict((a, b) for a, b, _ in FACE_KEYS)[k].lower(), v)
                                             for k, v in fx.items()) +
        (" (ossa mancanti: %s)" % ", ".join(miss) if miss else ""))


FX_SCALE = [1.0]          # scala della testa nell'adattamento allo scheletro OB (per gli spostamenti dell'espressione)


def face_expression_fields(np, o, arm=None):
    """Pesi DAZ del viso -> per ogni cursore dell'espressione, quanto si sposta ogni vertice (0..1 x mm), salvato
    come attributo della mesh ("fx_mouth", ...): sopravvive a riduzioni e separazioni. L'espressione si applica
    poi a ogni outfit sommando questi spostamenti, senza rifare la preparazione."""
    me = o.data
    nv = len(me.vertices)
    gi = {g.name: g.index for g in o.vertex_groups}
    moved = {}                                          # osso -> [(cursore, quota)]
    for k, bones in FACE_BONES.items():
        for b, q in bones:
            for side in ("l", "r"):
                moved.setdefault(side + b, []).append((k, q))
        if k == "brow_in":
            moved.setdefault("CenterBrow", []).append((k, 0.5))
    want = {}
    for gname, idx in gi.items():
        # come in DAZ: un osso spostato si porta dietro i figli (es. CenterBrow -> sopracciglia interne -> ...)
        chain = [gname]
        if arm is not None and gname in arm.data.bones:
            b = arm.data.bones[gname].parent
            while b is not None:
                chain.append(b.name)
                b = b.parent
        acc = [kq for c in chain for kq in moved.get(c, ())]
        if acc:
            want[idx] = acc
    vals = {k: np.zeros(nv, np.float32) for k in FACE_BONES}
    for v in me.vertices:
        for g in v.groups:
            for k, q in want.get(g.group, ()):
                vals[k][v.index] += g.weight * q
    n = 0
    for k, a in vals.items():
        name = "fx_" + k
        if name in me.attributes:
            me.attributes.remove(me.attributes[name])
        at = me.attributes.new(name, 'FLOAT', 'POINT')
        at.data.foreach_set("value", a)
        n += int((a > 0.01).sum())
    return vals


def apply_face_expression(np, o, fx):
    """Espressione neutra di questo outfit: vertici spostati su/giu' (Y Outbreak) di valore_mm x peso del cursore."""
    me = o.data
    fx = {k: float(v) for k, v in (fx or {}).items() if k in FACE_BONES and abs(float(v or 0)) > 1e-3}
    if not fx or not len(me.vertices):
        return False
    dy = np.zeros(len(me.vertices))
    for k, mm in fx.items():
        at = me.attributes.get("fx_" + k)
        if at is None:
            continue
        a = np.zeros(len(me.vertices), np.float32)
        at.data.foreach_get("value", a)
        dy += a * (mm / 10.0) * FX_SCALE[0]
    if not dy.any():
        return False
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    co[:, 1] += dy
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    return True


def apply_armature(bpy, objs):
    for o in objs:
        for k in [m for m in o.modifiers if m.type == 'ARMATURE']:
            if o.data.shape_keys:
                with bpy.context.temp_override(object=o, active_object=o):
                    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)
            with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o],
                                           selected_editable_objects=[o]):
                bpy.ops.object.modifier_apply(modifier=k.name)


# ------------------------------------------------------------------------------------------------
# Pesi DAZ -> Node
# ------------------------------------------------------------------------------------------------
def bone_table(arm, brow_side, neck_y_ob):
    """{osso DAZ: [(Node, quota)]} per tutte le ossa dell'armatura (anche quelle non in tabella)."""
    import numpy as np
    bones = arm.data.bones
    mw = arm.matrix_world
    head_y = {b.name: float(bl_to_ob(np, np.array([(mw @ b.head_local)[:]]))[0, 1]) for b in bones}
    head_x = {b.name: float(bl_to_ob(np, np.array([(mw @ b.head_local)[:]]))[0, 0]) for b in bones}
    out, unknown = {}, []

    def res(b):
        if b.name in out:
            return out[b.name]
        r = daz_lookup(b.name, brow_side)
        if r is None:
            unknown.append(b.name)
            if b.parent is None:
                r = [("Node3", 1.0)]
            else:
                r = res(b.parent)
                if head_y[b.name] > neck_y_ob and all(n in ("Node11", "Node20") for n, _ in r):
                    r = [("Node21", 1.0)]                   # capelli/accessori sopra il collo
                elif [n for n, _ in r] == ["Node3"] and abs(head_x[b.name]) > 2.0:
                    r = [("Node4" if head_x[b.name] > 0 else "Node7", 1.0)]   # gonna: segue la coscia
        out[b.name] = r
        return r
    for b in bones:
        res(b)
    return out, unknown


def node_weights(np, o, table):
    """Matrice (vertici, 35) dei pesi sui Node, normalizzata."""
    nv = len(o.data.vertices)
    W = np.zeros((nv, len(BONE_ORDER)), np.float32)
    col = {n: i for i, n in enumerate(BONE_ORDER)}
    gmap = {}
    for g in o.vertex_groups:
        r = table.get(g.name)
        if r is None:
            r = daz_lookup(g.name) or None
        gmap[g.index] = r
    for v in o.data.vertices:
        for g in v.groups:
            r = gmap.get(g.group)
            if not r or g.weight <= 0:
                continue
            for n, q in r:
                W[v.index, col[n]] += g.weight * q
    empty = W.sum(1) <= 1e-6
    return W, empty


def fill_empty_weights(np, P, W, empty, refP, refW):
    """Vertici senza pesi: copiano il vertice pesato piu' vicino (stesso oggetto o corpo)."""
    if not empty.any():
        return W
    from mathutils.kdtree import KDTree
    kd = KDTree(len(refP))
    for i, p in enumerate(refP):
        kd.insert(p, i)
    kd.balance()
    for i in np.nonzero(empty)[0]:
        _, j, _ = kd.find(P[i])
        W[i] = refW[j]
    return W


def limit4(np, W):
    order = np.argsort(-W, axis=1)
    out = np.zeros_like(W)
    rows = np.arange(len(W))[:, None]
    top = order[:, :4]
    out[rows, top] = W[rows, top]
    s = out.sum(1, keepdims=True)
    s[s <= 0] = 1.0
    out = out / s
    out[out < 0.01] = 0.0
    empty = out.sum(1) <= 0
    out[empty, order[empty, 0]] = 1.0
    return out / out.sum(1, keepdims=True)


def set_node_groups(np, o, W):
    o.vertex_groups.clear()
    for n in BONE_ORDER:
        o.vertex_groups.new(name=n)
    Wr = np.round(W, 4)
    for k, n in enumerate(BONE_ORDER):
        idx = np.nonzero(Wr[:, k] > 0)[0]
        if not len(idx):
            continue
        vg = o.vertex_groups[n]
        vals = Wr[idx, k]
        for w in np.unique(vals):
            vg.add(idx[vals == w].tolist(), float(w), 'REPLACE')


def get_node_weights(np, o):
    W = np.zeros((len(o.data.vertices), len(BONE_ORDER)), np.float32)
    gi = {g.index: BONE_ORDER.index(g.name) for g in o.vertex_groups if g.name in BONE_ORDER}
    for v in o.data.vertices:
        for g in v.groups:
            if g.group in gi:
                W[v.index, gi[g.group]] = g.weight
    return W


# ------------------------------------------------------------------------------------------------
# Adattamento allo scheletro Outbreak (come xps2outbreak: scala, arti giunto su giunto, busto in altezza)
# ------------------------------------------------------------------------------------------------
def rot_between(np, a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else np.diag([-1.0, -1.0, 1.0])
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1.0 / (1.0 + c))


def fit_transforms(np, J, ground, arms_on_bones=False):
    """J: {Node: posizione DAZ (cm OB)} -> funzione (P, NW) -> P adattato.
    arms_on_bones: braccia centrate sulle ossa OB anche in profondita' (come i personaggi originali, es. P06);
    altrimenti tengono la profondita' DAZ rispetto alla colonna (finiscono qualche cm dietro le ossa)."""
    hipmid = (J["Node4"] + J["Node7"]) / 2
    s = 94.0 / max(1e-6, hipmid[1] - ground)
    zref = J["Node10"][2] if "Node10" in J else hipmid[2]
    off = np.array([hipmid[0], ground, zref])

    def g(p):
        return (np.asarray(p, float) - off) * s
    JJ = {n: g(p) for n, p in J.items()}
    T = {n: np.array(SKEL[n], float) for n in SKEL}
    X = {}

    def seg(node, tail):
        if node not in JJ or tail not in JJ:
            return
        ds, dt = JJ[tail] - JJ[node], T[tail] - T[node]
        ls, lt = np.linalg.norm(ds), np.linalg.norm(dt)
        if ls < 1e-6 or lt < 1e-6:
            return
        d = ds / ls
        k = float(np.clip(lt / ls, 0.5, 2.0))
        S = np.eye(3) + (k - 1.0) * np.outer(d, d)
        X[node] = (JJ[node], rot_between(np, ds, dt) @ S, T[node])

    def rigid(node, like=None):
        if node not in JJ:
            return
        M = np.eye(3)
        if like in X:
            U, _, Vt = np.linalg.svd(X[like][1])
            M = U @ Vt
        X[node] = (JJ[node], M, T[node])

    for chain in (("Node4", "Node5", "Node6"), ("Node7", "Node8", "Node9"),
                  ("Node13", "Node14", "Node15", "Node32", "Node33", "Node34", "Node35"),
                  ("Node17", "Node18", "Node19", "Node28", "Node29", "Node30", "Node31")):
        if chain[0] in JJ:
            if arms_on_bones and chain[0] in ("Node13", "Node17"):
                continue
            dz = JJ[chain[0]][2] - T[chain[0]][2]
            for n in chain:
                T[n] = T[n] + np.array([0.0, 0.0, dz])
    for n in ("Node6", "Node9"):
        if n in JJ:
            T[n] = T[n] + np.array([0.0, JJ[n][1] - T[n][1], 0.0])
    for a, b in (("Node4", "Node5"), ("Node5", "Node6"), ("Node7", "Node8"), ("Node8", "Node9"),
                 ("Node13", "Node14"), ("Node14", "Node15"), ("Node17", "Node18"), ("Node18", "Node19")):
        seg(a, b)
    rigid("Node6")
    rigid("Node9")
    rigid("Node15", like="Node14")
    rigid("Node19", like="Node18")
    hs, ht = (JJ["Node4"] + JJ["Node7"]) / 2, (T["Node4"] + T["Node7"]) / 2
    ss, st = (JJ["Node13"] + JJ["Node17"]) / 2, (T["Node13"] + T["Node17"]) / 2
    d0, d1 = ht - hs, st - ss
    d0[0] = d1[0] = d0[2] = d1[2] = 0.0
    for n in ("Node3", "Node10", "Node11", "Node12", "Node16", "Node20", "Node21", "Node22", "Node23",
              "Node24", "Node25", "Node26", "Node27"):
        X[n] = None
    for n in ("Node32", "Node33", "Node34", "Node35"):
        X[n] = X.get("Node15")
    for n in ("Node28", "Node29", "Node30", "Node31"):
        X[n] = X.get("Node19")
    for n in BONE_ORDER:
        if n not in X:
            p = PARENTS[n]
            while p and p not in X:
                p = PARENTS[p]
            X[n] = X[p] if p else None
    info = "scala x%.3f (anca a 94 cm), braccia x%.2f, gambe x%.2f" % (
        s / 100.0 * 100.0,
        np.linalg.norm(T["Node15"] - T["Node13"]) / max(1e-6, np.linalg.norm(JJ["Node15"] - JJ["Node13"])),
        np.linalg.norm(T["Node6"] - T["Node4"]) / max(1e-6, np.linalg.norm(JJ["Node6"] - JJ["Node4"])))

    def apply(P, NW):
        P = g(P)
        t = np.clip((P[:, 1] - hs[1]) / max(1e-6, ss[1] - hs[1]), 0.0, 1.0)[:, None]
        PT = P + d0 * (1.0 - t) + d1 * t
        P2 = np.zeros_like(P)
        tot = NW.sum(1, keepdims=True)
        tot[tot <= 0] = 1.0
        Wn = NW / tot
        for k, n in enumerate(BONE_ORDER):
            w = Wn[:, k]
            if not w.any():
                continue
            if X[n] is None:
                P2 += w[:, None] * PT
            else:
                A, M, B = X[n]
                P2 += w[:, None] * ((P - A) @ M.T + B)
        none = NW.sum(1) <= 0
        P2[none] = PT[none]
        return P2

    def rigid(P, n):
        """Tutto il capo con la trasformazione di un solo Node e senza allungamenti: si sposta come un blocco
        (anelli, bracciali, orecchini...)."""
        P = g(P)
        if X[n] is None:
            c = P.mean(0)
            t = float(np.clip((c[1] - hs[1]) / max(1e-6, ss[1] - hs[1]), 0.0, 1.0))
            return P + d0 * (1.0 - t) + d1 * t
        A, M, B = X[n]
        U, _, Vt = np.linalg.svd(M)
        return (P - A) @ (U @ Vt).T + B
    apply.rigid = rigid
    return apply, info, JJ


# ------------------------------------------------------------------------------------------------
# Operazioni sulle mesh
# ------------------------------------------------------------------------------------------------
def set_mesh_coords(np, o, P_ob):
    """Mette nel mesh le coordinate Outbreak; l'oggetto diventa 'Y su' (rotazione X 90 come l'armatura)."""
    from mathutils import Matrix
    o.parent = None
    o.matrix_world = Matrix.Rotation(math.pi / 2.0, 4, 'X')
    o.data.vertices.foreach_set("co", np.asarray(P_ob, np.float32).ravel())
    o.data.update()


class EditMode(object):
    """with EditMode(bpy, o): ... (oggetto attivo e selezionato, modalita' modifica)."""
    def __init__(self, bpy, o):
        self.bpy, self.o = bpy, o

    def __enter__(self):
        bpy = self.bpy
        if bpy.context.object and bpy.context.object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        for x in bpy.context.selected_objects:
            x.select_set(False)
        bpy.context.view_layer.objects.active = self.o
        self.o.select_set(True)
        bpy.ops.object.mode_set(mode='EDIT')
        return self

    def __exit__(self, *a):
        self.bpy.ops.object.mode_set(mode='OBJECT')
        return False


def select_faces(np, o, mask):
    me = o.data
    me.polygons.foreach_set("select", np.asarray(mask, bool))
    vs = np.zeros(len(me.vertices), bool)
    lv = np.zeros(len(me.loops), int)
    me.loops.foreach_get("vertex_index", lv)
    ls = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get("loop_start", ls)
    lt = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get("loop_total", lt)
    pidx = np.repeat(np.arange(len(me.polygons)), lt)
    vs[lv[np.asarray(mask, bool)[pidx]]] = True
    me.vertices.foreach_set("select", vs)
    ev = np.zeros(len(me.edges) * 2, int)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    me.edges.foreach_set("select", vs[ev[:, 0]] & vs[ev[:, 1]])


def poly_mats(np, me):
    pm = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get("material_index", pm)
    return pm


def delete_faces(bpy, np, o, mask):
    if not np.any(mask):
        return 0
    select_faces(np, o, mask)
    with EditMode(bpy, o):
        bpy.ops.mesh.select_mode(type='FACE', use_extend=False, use_expand=False)
        o.data.update()
    select_faces(np, o, mask)
    with EditMode(bpy, o):
        bpy.ops.mesh.delete(type='FACE')
    return int(np.sum(mask))


SPECKS = [True, 3, 0.5]       # pezzetti isolati: togli?, al massimo triangoli, al massimo cm2


def remove_specks(bpy, np, o, max_tris=None, max_area=None):
    """Toglie vertici e spigoli sciolti, facce con area quasi zero e i pezzetti staccati piccoli
    (<= max_tris triangoli e < max_area cm2: frammenti della riduzione, triangoli volanti nei capelli).
    Coordinate della mesh in cm. -> (pezzetti, triangoli, vertici sciolti)"""
    import bmesh
    if not len(o.data.polygons):
        return 0, 0, 0
    max_tris = SPECKS[1] if max_tris is None else max_tris
    max_area = SPECKS[2] if max_area is None else max_area
    me = o.data
    ar = np.zeros(len(me.polygons))
    me.polygons.foreach_get("area", ar)
    nt = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get("loop_total", nt)
    nt -= 2
    ls = np.zeros(len(me.polygons), int)
    me.polygons.foreach_get("loop_start", ls)
    lv = np.zeros(len(me.loops), int)
    me.loops.foreach_get("vertex_index", lv)
    comp = mesh_components(np, o)
    fc = comp[lv[ls]]
    ncomp = int(comp.max()) + 1 if len(comp) else 0
    ctri = np.bincount(fc, weights=nt, minlength=ncomp)
    carea = np.bincount(fc, weights=ar, minlength=ncomp)
    small = (ctri > 0) & (ctri <= max_tris) & (carea < max_area) & bool(SPECKS[0])
    if small.sum() == (ctri > 0).sum():               # tutto l'oggetto e' piccolo: non lo svuoto
        small[:] = False
    kill = small[fc] | (ar < 1e-6)
    n_isl, n_tri = int(small.sum()), int(nt[kill].sum())
    if kill.any():
        delete_faces(bpy, np, o, kill)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    le = [e for e in bm.edges if not e.link_faces]
    lv_ = [v for v in bm.verts if not v.link_faces]
    if le:
        bmesh.ops.delete(bm, geom=le, context='EDGES')
    lv_ = [v for v in bm.verts if not v.link_faces]
    nlv = len(lv_)
    if lv_:
        bmesh.ops.delete(bm, geom=lv_, context='VERTS')
    bm.to_mesh(o.data)
    bm.free()
    o.data.update()
    return n_isl, n_tri, nlv


def specks_log(name, r):
    if any(r):
        log("  %s: tolti %d pezzetti isolati (%d triangoli), %d vertici sciolti" % (name, r[0], r[1], r[2]))


def triangulate(bpy, o):
    with EditMode(bpy, o):
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')


def tri_count(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def decimate_zone(bpy, np, o, mat_ids, target, symmetry=True):
    return decimate_mask(bpy, np, o, lambda: np.isin(poly_mats(np, o.data), list(mat_ids)), target, symmetry)


def decimate_mask(bpy, np, o, mask_fn, target, symmetry=True):
    """Riduce solo le facce scelte da mask_fn() (ricalcolata a ogni passo); i vertici condivisi con il resto
    del mesh restano fermi, cosi' tra le zone non si aprono crepe. -> triangoli finali."""
    me = o.data
    cur = 0
    for it in range(4):
        pm_sel = np.asarray(mask_fn(), bool)
        cur = int(pm_sel.sum())
        if cur <= target * 1.03 or cur == 0:
            break
        nv = len(me.vertices)
        inR = np.zeros(nv, bool)
        outR = np.zeros(nv, bool)
        ls = np.zeros(len(me.polygons), int)
        me.polygons.foreach_get("loop_start", ls)
        lt = np.zeros(len(me.polygons), int)
        me.polygons.foreach_get("loop_total", lt)
        lv = np.zeros(len(me.loops), int)
        me.loops.foreach_get("vertex_index", lv)
        pidx = np.repeat(np.arange(len(me.polygons)), lt)
        inR[lv[pm_sel[pidx]]] = True
        outR[lv[~pm_sel[pidx]]] = True
        vs = inR & ~outR
        me.vertices.foreach_set("select", vs)
        me.edges.foreach_set("select", np.zeros(len(me.edges), bool))
        me.polygons.foreach_set("select", np.zeros(len(me.polygons), bool))
        with EditMode(bpy, o):
            bpy.ops.mesh.select_mode(type='VERT', use_extend=False, use_expand=False)
        me.vertices.foreach_set("select", vs)
        me.edges.foreach_set("select", np.zeros(len(me.edges), bool))
        me.polygons.foreach_set("select", np.zeros(len(me.polygons), bool))
        with EditMode(bpy, o):
            bpy.ops.mesh.decimate(ratio=max(0.02, min(1.0, target / float(cur))), use_symmetry=symmetry,
                                  symmetry_axis='X')
        new = int(np.asarray(mask_fn(), bool).sum())
        if new >= cur * 0.995:                   # non scende piu' (bordi bloccati)
            cur = new
            break
        cur = new
    return cur


def decimate_inside(bpy, np, o, target, symmetry=True):
    """Riduce tutto l'oggetto tenendo fermi i bordi aperti (giunture con le altre parti: niente crepe)."""
    me = o.data
    for it in range(4):
        cur = tri_count(o)
        if cur <= target * 1.03 or cur == 0:
            break
        ev = np.zeros(len(me.edges) * 2, int)
        me.edges.foreach_get("vertices", ev)
        le = np.zeros(len(me.loops), int)
        me.loops.foreach_get("edge_index", le)
        cnt = np.bincount(le, minlength=len(me.edges))
        vs = np.ones(len(me.vertices), bool)
        vs[ev.reshape(-1, 2)[cnt == 1].ravel()] = False
        me.vertices.foreach_set("select", vs)
        me.edges.foreach_set("select", np.zeros(len(me.edges), bool))
        me.polygons.foreach_set("select", np.zeros(len(me.polygons), bool))
        with EditMode(bpy, o):
            bpy.ops.mesh.select_mode(type='VERT', use_extend=False, use_expand=False)
        me.vertices.foreach_set("select", vs)
        me.edges.foreach_set("select", np.zeros(len(me.edges), bool))
        me.polygons.foreach_set("select", np.zeros(len(me.polygons), bool))
        with EditMode(bpy, o):
            bpy.ops.mesh.decimate(ratio=max(0.02, min(1.0, target / float(cur))), use_symmetry=symmetry,
                                  symmetry_axis='X')
        if tri_count(o) >= cur * 0.995:
            break
    return tri_count(o)


def mirror_limb_uvs(np, o, zone_ids):
    """Braccio e gamba destri (x<0) prendono le UV di quelli sinistri: nell'atlas ne serve uno solo."""
    from mathutils.kdtree import KDTree
    me = o.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    pm = poly_mats(np, me)
    sel = np.isin(pm, list(zone_ids))
    left_v = set()
    for p in me.polygons:
        if sel[p.index]:
            for v in p.vertices:
                if co[v, 0] > 0.05:
                    left_v.add(v)
    left_v = sorted(left_v)
    if not left_v:
        return 0, 0
    kd = KDTree(len(left_v))
    for i, v in enumerate(left_v):
        kd.insert(co[v], i)
    kd.balance()
    uvl = me.uv_layers.active.data
    uv = np.zeros(len(me.loops) * 2)
    uvl.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    face_of = {}
    for p in me.polygons:
        if sel[p.index] and all(co[v, 0] > 0.05 for v in p.vertices):
            face_of[frozenset(p.vertices)] = p.index
    mirror = {}
    done = fail = 0
    for p in me.polygons:
        if not sel[p.index] or not all(co[v, 0] < -0.05 for v in p.vertices):
            continue
        mv = []
        for v in p.vertices:
            if v not in mirror:
                q = co[v].copy()
                q[0] = -q[0]
                _, i, d = kd.find(q)
                mirror[v] = left_v[i] if d < 0.6 else -1
            mv.append(mirror[v])
        g = face_of.get(frozenset(mv)) if -1 not in mv else None
        if g is None:
            fail += 1
            continue
        gp = me.polygons[g]
        lmap = {me.loops[li].vertex_index: li for li in gp.loop_indices}
        for li in p.loop_indices:
            uv[li] = uv[lmap[mirror[me.loops[li].vertex_index]]]
        done += 1
    uvl.foreach_set("uv", uv.ravel())
    return done, fail


def separate_parts(bpy, np, o, groups):
    """groups: [(nome, set di indici materiale)] -> {nome: oggetto}."""
    out = {}
    for name, ids in groups:
        pm = poly_mats(np, o.data)
        mask = np.isin(pm, list(ids))
        if not mask.any():
            continue
        if mask.all():
            o.name = name
            out[name] = o
            break
        before = set(bpy.data.objects)
        with EditMode(bpy, o):
            bpy.ops.mesh.select_mode(type='FACE', use_extend=False, use_expand=False)
        select_faces(np, o, mask)
        with EditMode(bpy, o):
            bpy.ops.mesh.separate(type='SELECTED')
        new = [x for x in bpy.data.objects if x not in before][0]
        new.name = name
        new.data.name = name
        out[name] = new
    return out


def clean_unused_materials(o):
    me = o.data
    used = sorted({p.material_index for p in me.polygons})
    if len(used) == len(me.materials):
        return
    mats = [me.materials[i] for i in used]
    remap = {old: new for new, old in enumerate(used)}
    idx = [remap[p.material_index] for p in me.polygons]
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", idx)


def transfer_normals(bpy, o, src):
    """Normali personalizzate copiate dal modello originale (stesse coordinate): resta liscio."""
    me = o.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    try:
        me.use_auto_smooth = True                       # Blender < 4.1
    except AttributeError:
        pass
    mod = o.modifiers.new("normali", 'DATA_TRANSFER')
    mod.object = src
    mod.use_loop_data = True
    mod.data_types_loops = {'CUSTOM_NORMAL'}
    mod.loop_mapping = 'POLYINTERP_NEAREST'
    mod.use_object_transform = True
    try:
        with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o], selected_editable_objects=[o]):
            bpy.ops.object.modifier_apply(modifier=mod.name)
    except Exception as e:
        o.modifiers.remove(mod)
        warn("normali non copiate su %s (%s)" % (o.name, e))


def cleanup_weights(np, o):
    W = get_node_weights(np, o)
    set_node_groups(np, o, limit4(np, W))


def duplicate(bpy, o, name):
    n = o.copy()
    n.data = o.data.copy()
    n.name = name
    n.data.name = name
    for c in o.users_collection:
        c.objects.link(n)
    return n


# ------------------------------------------------------------------------------------------------
# Atlas: tutte le texture di piu' oggetti in un'unica immagine
# ------------------------------------------------------------------------------------------------
def _sample(np, A, u, v):
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
    """Prova piu' ordini (altezza, area, larghezza, lato maggiore) e tiene il primo che ci sta."""
    keys = (lambda i: (-sizes[i][1], -sizes[i][0]), lambda i: -sizes[i][0] * sizes[i][1],
            lambda i: (-sizes[i][0], -sizes[i][1]), lambda i: -max(sizes[i]))
    for kf in keys:
        pos = _pack1(sizes, W, H, sorted(range(len(sizes)), key=kf))
        if pos is not None:
            return pos
    return None


def _pack1(sizes, W, H, order):
    sky = [[0, 0, W]]
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
        for sx, sy, sw in sky:
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


def uv_islands(np, me, key_of_poly):
    """Isole UV (facce collegate da spigoli con le stesse UV e la stessa immagine) -> lista di liste."""
    uv = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    par = list(range(len(me.polygons)))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    edges = {}
    for p in me.polygons:
        li = list(p.loop_indices)
        vs = [me.loops[l].vertex_index for l in li]
        n = len(vs)
        for j in range(n):
            a, b = vs[j], vs[(j + 1) % n]
            ua, ub = uv[li[j]], uv[li[(j + 1) % n]]
            if a > b:
                a, b, ua, ub = b, a, ub, ua
            k = (a, b)
            ent = (p.index, round(ua[0], 5), round(ua[1], 5), round(ub[0], 5), round(ub[1], 5))
            if k in edges:
                q = edges[k]
                if q[1:] == ent[1:] and key_of_poly[q[0]] == key_of_poly[p.index]:
                    ra, rb = find(q[0]), find(p.index)
                    if ra != rb:
                        par[ra] = rb
            else:
                edges[k] = ent
    groups = {}
    for i in range(len(par)):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values()), uv


class AtlasPiece(object):
    def __init__(self, key):
        self.key = key
        self.loops = []          # [(oggetto, array indici loop)]
        self.lo = None
        self.hi = None
        self.area3d = 0.0
        self.uvarea = 0.0
        self.imp = 0.0
        self.label = ""


def build_atlas(bpy, np, objs, size, out_png, mat_name, imp_of=None, reserve=None, maxdim=1024, ambient=20,
                region=None, alpha=False, per_object=False, recolor=None, want_masks=False):
    """Unisce le texture usate da objs in un atlas size x size; rimappa le UV; un solo materiale.
    imp_of(nome materiale) -> importanza (densita' relativa). reserve = (lato px, immagine RGB o None).
    Ritorna dict con informazioni (rettangolo riservato, scala).
    region = (x, y, lato) in pixel (dal basso) di un atlas size x size gia' esistente: impacchetta solo li'
    dentro (es. i capelli nello spazio riservato); niente file ne' materiale, ritorna il riquadro in 'patch'.
    per_object: ogni oggetto ha i suoi pezzi (anche se usa la stessa immagine di un altro), cosi' si colora da solo.
    recolor = {nome oggetto: colore (come adjust_colors)}; want_masks: info["objmask"] = {nome: maschera, riga 0 = alto}."""
    ox, oy = (region[0], region[1]) if region else (0, 0)
    P = region[2] if region else size
    imp_of = imp_of or (lambda n: 1.0)
    images = {}               # chiave -> (array h,w,4 o None, colore, dimensione originale)
    pieces = []
    for o in objs:
        me = o.data
        if not len(me.polygons):
            continue
        if me.uv_layers.active is None:                 # capo senza UV (raro): una mappa vuota
            me.uv_layers.new(name="UVMap")
        keys = []
        own = (o.name,) if per_object else ()
        op = float(o.get("_opacity", 1.0)) if alpha and not o.get("_opaque") else 1.0
        if alpha and o.get("_alpha_boost"):
            op = op * float(o["_alpha_boost"])          # >1: alpha rinforzato (poi limitato a 1)
        for m in me.materials:
            img, col = material_image(m)
            tag = (str(m["_atlas_tag"]),) if m is not None and m.get("_atlas_tag") else ()
            aimg = material_alpha_image(m) if alpha and not o.get("_opaque") else None
            if aimg is not None and aimg.size[0] == 0:
                aimg = None
            if img is not None and img.size[0] > 0:
                k = ("img", img.name, aimg.name if aimg else "", op) + own + tag
                if k not in images:
                    images[k] = (img, col, tuple(img.size), aimg, op)
            elif aimg is not None:                       # solo trasparenza (es. ciglia: colore fisso)
                k = ("alpha", aimg.name, tuple(round(c, 3) for c in col), op) + own
                images[k] = (None, col, tuple(aimg.size), aimg, op)
            else:
                k = ("col", tuple(round(c, 3) for c in col), op) + own
                images[k] = (None, col, (4, 4), None, op)
            keys.append((k, (m.get("_zone") if m is not None else None) or zone_name(m.name if m else "")))
        pm = poly_mats(np, me)
        kp = [keys[i][0] if i < len(keys) else ("col", (0.8, 0.8, 0.8)) for i in pm]
        isl, o_uv = uv_islands(np, me, kp)
        # area 3D e UV per faccia
        for faces in isl:
            k = kp[faces[0]]
            loops = np.array([l for f in faces for l in me.polygons[f].loop_indices])
            if k[0] in ("img", "alpha"):
                sh = np.floor(o_uv[loops].min(0) + 1e-6)
                if sh.any():
                    o_uv[loops] -= sh
            pc = AtlasPiece(k)
            pc.loops.append((o, loops))
            pc.lo, pc.hi = o_uv[loops].min(0), o_uv[loops].max(0)
            a3 = au = 0.0
            for f in faces:
                p = me.polygons[f]
                a3 += p.area
                li = list(p.loop_indices)
                for j in range(1, len(li) - 1):
                    a, b, c = o_uv[li[0]], o_uv[li[j]], o_uv[li[j + 1]]
                    au += abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2
            pc.area3d, pc.uvarea = a3, au
            zn = keys[pm[faces[0]]][1] if pm[faces[0]] < len(keys) else ""
            pc.imp = imp_of(zn)
            pc.label = zn
            pieces.append(pc)
        _UVCACHE[o.name] = o_uv
    # unisce le isole della stessa immagine che si sovrappongono (es. braccio destro = sinistro)
    def merge(pred):
        changed = True
        while changed:
            changed = False
            for i in range(len(pieces)):
                for j in range(i + 1, len(pieces)):
                    a, b = pieces[i], pieces[j]
                    if a.key != b.key or not pred(a, b):
                        continue
                    a.loops += b.loops
                    a.lo = np.minimum(a.lo, b.lo)
                    a.hi = np.maximum(a.hi, b.hi)
                    a.area3d += b.area3d
                    a.uvarea += b.uvarea
                    a.imp = max(a.imp, b.imp)
                    pieces.pop(j)
                    changed = True
                    break
                if changed:
                    break

    def overlap(a, b):
        ix = max(0.0, min(a.hi[0], b.hi[0]) - max(a.lo[0], b.lo[0]))
        iy = max(0.0, min(a.hi[1], b.hi[1]) - max(a.lo[1], b.lo[1]))
        sa = max(1e-12, (a.hi[0] - a.lo[0]) * (a.hi[1] - a.lo[1]))
        sb = max(1e-12, (b.hi[0] - b.lo[0]) * (b.hi[1] - b.lo[1]))
        return ix * iy >= 0.35 * min(sa, sb) or a.key[0] == "col"
    merge(overlap)
    PAD, MINPX = 2, 3

    def densities():
        # densita' sorgente (pixel per cm) di ogni pezzo
        for pc in pieces:
            img, col, (tw, th) = images[pc.key][:3]
            span = np.maximum(pc.hi - pc.lo, 1e-6)
            pc.span = span
            pc.src_px = (span[0] * tw, span[1] * th)
            if pc.key[0] == "col":
                pc.dens = None
            else:
                pc.dens = math.sqrt(max(1e-12, pc.uvarea * tw * th) / max(1e-9, pc.area3d))
    densities()
    mult = [1.0] * len(pieces)

    def sizes_for(k):
        out = []
        for i, pc in enumerate(pieces):
            if pc.dens is None:
                out.append((MINPX + 1 + 2 * PAD, MINPX + 1 + 2 * PAD))
                continue
            f = min(1.0, k * mult[i] * math.sqrt(max(0.05, pc.imp)) / pc.dens)
            out.append((max(MINPX, int(round(pc.src_px[0] * f))) + 2 * PAD,
                        max(MINPX, int(round(pc.src_px[1] * f))) + 2 * PAD))
        if reserve:
            out.append((reserve[0], reserve[0]))
        return out

    def search():
        lo_k, hi_k = 0.0, 1000.0
        best = None
        for _ in range(24):
            k = (lo_k + hi_k) / 2
            sz = sizes_for(k)
            pos = _pack(sz, P, P)
            if pos is not None:
                best = (k, sz, pos)
                lo_k = k
            else:
                hi_k = k
        return best
    n0 = len(pieces)
    best = search()
    if best is None:
        # troppi pezzi: unisco tutte le isole della stessa immagine (un rettangolo per immagine)
        merge(lambda a, b: True)
        densities()
        mult = [1.0] * len(pieces)
        best = search()
        if best is not None:
            log("  atlas %dx%d: %d pezzi non ci stavano, uniti per immagine -> %d" % (P, P, n0, len(pieces)))
    if best is None:
        PAD, MINPX = 1, 2                          # ultima prova: bordi e pezzi minimi piu' piccoli
        best = search()
        if best is not None:
            log("  atlas %dx%d: pezzi ridotti al minimo (%d)" % (P, P, len(pieces)))
    if best is None:
        what = "riquadro dei capelli %dx%d nell'atlas %dx%d" % (P, P, size, size) if region else "atlas %dx%d" % (size, size)
        names = sorted(set(short_name(o.name) for o in objs))
        raise RuntimeError("%s: %d pezzi di texture non ci stanno nemmeno al minimo (%d dopo l'unione). Oggetti: %s. "
                           "Prova con un atlas piu' grande o meno materiali." % (what, n0, len(pieces), ", ".join(names[:8])))
    k, sz, pos = best
    # spazio rimasto vuoto: ingrandisco i pezzi uno alla volta (prima i piu' importanti) finche' ci stanno
    def used(szs):
        return sum(w * h for w, h in szs) / float(P * P)
    fill0 = used(sz)
    memo_key = (P, len(pieces), tuple(round(pc.imp or 0, 3) for pc in pieces), mat_name or "")
    if memo_key in PACK_MEMO:                    # stesso atlas di prima (stessi pezzi): stesso ingrandimento
        mult[:] = PACK_MEMO[memo_key]
        sz2 = sizes_for(k)
        pos2 = _pack(sz2, P, P)
        if pos2 is not None:
            sz, pos = sz2, pos2
            memo_key = None
        else:
            mult[:] = [1.0] * len(pieces)
    order_imp = [] if memo_key is None else sorted(range(len(pieces)), key=lambda i: -(pieces[i].imp or 0) * (pieces[i].src_px[0] * pieces[i].src_px[1]
                                                                                  if pieces[i].dens is not None else 0))
    if "_corpo_base" not in (mat_name or ""):     # l'atlas del corpo si fa una volta sola: li' tutti i pezzi
        order_imp = order_imp[:12]               # vestiti (si rifanno a ogni modifica): i pezzi grandi
    for _ in range(3):
        grown = False
        for i in order_imp:
            if pieces[i].dens is None:
                continue
            old = mult[i]
            mult[i] = old * 1.15
            sz2 = sizes_for(k)
            if sz2[i] == sz[i]:                    # gia' alla risoluzione originale: non cresce
                mult[i] = old
                continue
            pos2 = _pack(sz2, P, P)
            if pos2 is None:
                mult[i] = old
            else:
                sz, pos, grown = sz2, pos2, True
        if not grown:
            break
    if memo_key is not None:
        if len(PACK_MEMO) > 200:
            PACK_MEMO.clear()
        PACK_MEMO[memo_key] = list(mult)
    if used(sz) > fill0 + 0.005:
        log("  atlas %dx%d: spazio usato %d%% -> %d%%" % (size, size, 100 * fill0, 100 * used(sz)))
    atlas = np.zeros((P, P, 4), np.float32)
    rects = {}
    filled = np.zeros((P, P), bool)
    trmask = np.zeros((P, P), bool)              # pixel dei pezzi trasparenti (alpha vero); altrove pieno
    arrays = {}
    def samp(A, U, V_, span, iw, ih):
        ss = max(1, min(4, int(np.ceil(max(span[0] * A.shape[1] / iw, span[1] * A.shape[0] / ih)))))
        if ss == 1:
            return _sample(np, A, U, V_)
        acc = 0
        for a in range(ss):
            for b in range(ss):
                acc = acc + _sample(np, A, U + (a + 0.5 - ss / 2) / ss * span[0] / iw,
                                    V_ + (b + 0.5 - ss / 2) / ss * span[1] / ih)
        return acc / (ss * ss)
    for pc, (rw, rh), (x, y) in zip(pieces, sz, pos):
        img, col, _, aimg, op = images[pc.key]
        iw, ih = rw - 2 * PAD, rh - 2 * PAD
        if alpha and (aimg is not None or abs(op - 1.0) > 0.001):
            trmask[y:y + rh, x:x + rw] = True
        if img is None and aimg is not None:            # colore fisso, trasparenza dalla mappa
            if aimg.name not in arrays:
                arrays[aimg.name] = alpha_array(aimg, maxdim)
            A = arrays[aimg.name]
            lo, span = pc.lo, pc.span
            jj = (np.arange(rw) - PAD + 0.5) / iw
            ii = (np.arange(rh) - PAD + 0.5) / ih
            U, V_ = np.meshgrid(lo[0] + jj * span[0], lo[1] + ii * span[1])
            atlas[y:y + rh, x:x + rw, :3] = col
            atlas[y:y + rh, x:x + rw, 3] = samp(A, U, V_, span, iw, ih)[..., 0] * op
        elif img is None:
            atlas[y:y + rh, x:x + rw, :3] = col
            atlas[y:y + rh, x:x + rw, 3] = op
        else:
            if pc.key not in arrays:
                arrays[pc.key] = _img_array(img, maxdim)
            A = arrays[pc.key]
            lo, span = pc.lo, pc.span
            jj = (np.arange(rw) - PAD + 0.5) / iw
            ii = (np.arange(rh) - PAD + 0.5) / ih
            U, V = np.meshgrid(lo[0] + jj * span[0], lo[1] + ii * span[1])
            ss = max(1, min(4, int(np.ceil(max(span[0] * A.shape[1] / iw, span[1] * A.shape[0] / ih)))))
            if ss > 1:
                acc = 0
                for a in range(ss):
                    for b in range(ss):
                        acc = acc + _sample(np, A, U + (a + 0.5 - ss / 2) / ss * span[0] / iw,
                                            V + (b + 0.5 - ss / 2) / ss * span[1] / ih)
                block = acc / (ss * ss)
            else:
                block = _sample(np, A, U, V)
            atlas[y:y + rh, x:x + rw] = block
            if alpha:
                if aimg is not None:
                    if aimg.name not in arrays:
                        arrays[aimg.name] = alpha_array(aimg, maxdim)
                    jj = (np.arange(rw) - PAD + 0.5) / iw
                    ii = (np.arange(rh) - PAD + 0.5) / ih
                    U, V_ = np.meshgrid(lo[0] + jj * span[0], lo[1] + ii * span[1])
                    atlas[y:y + rh, x:x + rw, 3] = samp(arrays[aimg.name], U, V_, span, iw, ih)[..., 0] * op
                else:
                    atlas[y:y + rh, x:x + rw, 3] = block[..., 3] * op
        filled[y:y + rh, x:x + rw] = True
        for o, L in pc.loops:
            rects.setdefault(o.name, []).append((x, y, rw, rh))
            uv = _UVCACHE[o.name]
            uv[L, 0] = (ox + x + PAD + (uv[L, 0] - pc.lo[0]) / pc.span[0] * iw) / size
            uv[L, 1] = (oy + y + PAD + (uv[L, 1] - pc.lo[1]) / pc.span[1] * ih) / size
    info = {"scale": k, "pieces": len(pieces)}
    if reserve:
        rx, ry = pos[-1]
        rs = reserve[0]
        if reserve[1] is not None:
            R = reserve[1]
            yy = (np.arange(rs) * R.shape[0] / rs).astype(int)
            xx = (np.arange(rs) * R.shape[1] / rs).astype(int)
            atlas[ry:ry + rs, rx:rx + rs, :3] = R[::-1][yy][:, xx][:, :, :3] / 255.0
        else:
            ch = ((np.arange(rs)[:, None] // 8 + np.arange(rs)[None, :] // 8) % 2) * 0.15 + 0.4
            atlas[ry:ry + rs, rx:rx + rs, :3] = ch[..., None]
        filled[ry:ry + rs, rx:rx + rs] = True
        # rettangolo in pixel con l'origine in alto a sinistra (come in Photoshop)
        info["reserve_px"] = (rx, size - ry - rs, rs, rs)
        info["reserve_xy"] = (rx, ry, rs)
        info["reserve_uv"] = (rx / size, ry / size, (rx + rs) / size, (ry + rs) / size)
    filled0 = filled.copy()
    # bordo: i pixel vuoti prendono il colore del vicino (niente aloni neri sui bordi delle UV)
    for _ in range(6):
        if filled.all():
            break
        src = atlas.copy()
        f2 = filled.copy()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = np.roll(np.roll(filled, dy, 0), dx, 1)
            take = ~f2 & sh
            atlas[take] = np.roll(np.roll(src, dy, 0), dx, 1)[take]
            f2 |= take
        filled = f2
    rgb = (np.clip(atlas[::-1, :, :3], 0, 1) * 255 + 0.5).astype(np.uint8)
    info["size"] = size

    def objmask(names):
        M = np.zeros((P, P), np.float32)
        for nm in names:
            for x, y, rw, rh in rects.get(nm, ()):
                M[y:y + rh, x:x + rw] = 1.0
        return M[::-1]
    if want_masks:
        info["objmask"] = {nm: objmask([nm]) > 0.5 for nm in rects}
    groups = {}
    for nm, p in (recolor or {}).items():                 # stesso colore (capo + lenti): una sola mediana
        if p and nm in rects:
            groups.setdefault(json.dumps(p, sort_keys=True), (p, []))[1].append(nm)
    for p, names in groups.values():
        rgb = adjust_colors(np, rgb, p, objmask(names))
    if region:
        for o in objs:
            if o.name in _UVCACHE:
                o.data.uv_layers.active.data.foreach_set("uv", _UVCACHE.pop(o.name).ravel())
        info["patch"] = rgb
        return info
    if alpha:
        a = np.where(trmask, np.where(filled0, np.clip(atlas[..., 3], 0.0, 1.0), 0.0), 1.0)[::-1]
        info["transparent_px"] = int(trmask.sum())
        info["rgba"] = np.concatenate([rgb, (np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)[..., None]], axis=2)
        write_png(out_png, info["rgba"])
    else:
        write_png(out_png, rgb)
    img = bpy.data.images.load(out_png)
    mat = make_material(bpy, mat_name, img, ambient)
    for o in objs:
        me = o.data
        if o.name in _UVCACHE:
            me.uv_layers.active.data.foreach_set("uv", _UVCACHE.pop(o.name).ravel())
        old = list(me.materials)
        me.materials.clear()
        me.materials.append(mat)
        me.polygons.foreach_set("material_index", [0] * len(me.polygons))
        for m in old:
            if m and m.users == 0:
                bpy.data.materials.remove(m)
    info["rgb"] = rgb
    info["material"] = mat
    return info


_UVCACHE = {}
PACK_MEMO = {}


def make_material(bpy, name, img, ambient=20, alpha=False):
    mat = bpy.data.materials.new(name)
    try:
        mat.use_nodes = True
    except Exception:
        pass
    nt = mat.node_tree
    bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    if bsdf:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        for nm, val in (("Roughness", 1.0), ("Specular IOR Level", 0.0), ("Specular", 0.0), ("Metallic", 0.0)):
            if nm in bsdf.inputs:
                try:
                    bsdf.inputs[nm].default_value = val
                except Exception:
                    pass
        if alpha and "Alpha" in bsdf.inputs:            # come in 3ds Max: stessa texture, alpha attivato
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            try:
                mat.blend_method = 'BLEND'
            except Exception:
                pass
    return mat


# ------------------------------------------------------------------------------------------------
# FBX: materiali come li vuole Outbreak (ambient 20,20,20 - diffuse bianco - niente speculare)
# L'esportatore FBX di Blender scrive lo speculare uguale al colore base e l'ambient a fattore 0:
# correggo direttamente i valori nel file binario (stessa lunghezza, nessun altro cambiamento).
# ------------------------------------------------------------------------------------------------
def patch_fbx_materials(path, ambient=20):
    d = bytearray(open(path, "rb").read())
    if not d.startswith(b"Kaydara FBX Binary"):
        return 0
    ver = struct.unpack_from("<I", d, 23)[0]
    big = ver >= 7500
    a = ambient / 255.0
    want = {b"AmbientColor": (a, a, a), b"AmbientFactor": (1.0,), b"DiffuseColor": (1.0, 1.0, 1.0),
            b"DiffuseFactor": (1.0,), b"SpecularColor": (0.0, 0.0, 0.0), b"SpecularFactor": (0.0,),
            b"Shininess": (5.0,), b"ShininessExponent": (5.0,), b"ReflectionFactor": (0.0,),
            b"EmissiveFactor": (0.0,)}
    count = [0]
    SIZES = {"Y": 2, "C": 1, "I": 4, "F": 4, "D": 8, "L": 8}

    def node(off, path):
        if big:
            end, nprops, _ = struct.unpack_from("<QQQ", d, off)
            p = off + 24
        else:
            end, nprops, _ = struct.unpack_from("<III", d, off)
            p = off + 12
        if end == 0:
            return None
        nl = d[p]
        name = bytes(d[p + 1:p + 1 + nl])
        p += 1 + nl
        props = []
        for _ in range(nprops):
            t = chr(d[p])
            p += 1
            if t in SIZES:
                props.append((t, p))
                p += SIZES[t]
            elif t in "fdlib":
                ln, enc, cl = struct.unpack_from("<III", d, p)
                props.append((t, None))
                p += 12 + cl
            elif t in "SR":
                ln = struct.unpack_from("<I", d, p)[0]
                props.append((t, bytes(d[p + 4:p + 4 + ln])))
                p += 4 + ln
            else:
                raise ValueError("FBX: tipo di proprieta' sconosciuto %r" % t)
        if name == b"P" and len(path) >= 2 and path[-2] == b"Material" and path[-1] == b"Properties70" \
                and props and props[0][0] == "S" and props[0][1] in want:
            vals = want[props[0][1]]
            nums = [x for x in props[4:] if x[0] in ("D", "F")]
            for (t, po), v in zip(nums, vals):
                struct.pack_into("<d" if t == "D" else "<f", d, po, v)
            count[0] += 1
        while p < end:
            r = node(p, path + [name])
            if r is None:
                break
            p = r
        return end

    off = 27
    while off < len(d):
        r = node(off, [])
        if r is None:
            break
        off = r
    with open(path, "wb") as fh:
        fh.write(d)
    return count[0]


# ------------------------------------------------------------------------------------------------
# Armatura Outbreak, export
# ------------------------------------------------------------------------------------------------
def build_armature(bpy):
    arm_data = bpy.data.armatures.new("Node0")
    arm = bpy.data.objects.new("Node0", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    arm.rotation_euler = (math.pi / 2.0, 0.0, 0.0)
    arm_data.display_type = 'STICK'
    with EditMode(bpy, arm):
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
    arm["GroupId"] = 0
    for n in BONE_ORDER:
        pb = arm.pose.bones[n]
        pb.rotation_mode = 'XYZ'
        pb["GroupId"] = group_id(n)
    return arm


def attach(o, arm):
    from mathutils import Matrix
    o.parent = arm
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.matrix_basis = Matrix.Identity(4)
    for m in list(o.modifiers):
        o.modifiers.remove(m)
    o.modifiers.new("Armature", 'ARMATURE').object = arm
    for n in BONE_ORDER:
        if n not in o.vertex_groups:
            o.vertex_groups.new(name=n)


def export_fbx(bpy, arm, objs, out, ambient):
    bpy.ops.object.select_all(action='DESELECT')
    for o in [arm] + list(objs):
        o.select_set(True)
    bpy.context.view_layer.objects.active = arm
    for img in bpy.data.images:
        if img.source == 'FILE' and not img.packed_file and img.users:
            try:
                img.pack()
            except Exception:
                pass
    scn = bpy.context.scene
    if scn.world is None:
        scn.world = bpy.data.worlds.new("World")
    a = ambient / 255.0
    scn.world.color = (a, a, a)
    bpy.ops.export_scene.fbx(filepath=out, use_selection=True, object_types={'ARMATURE', 'MESH'},
                             apply_unit_scale=True, apply_scale_options='FBX_SCALE_NONE', global_scale=1.0,
                             axis_forward='-Z', axis_up='Y', add_leaf_bones=False, primary_bone_axis='Y',
                             secondary_bone_axis='X', use_armature_deform_only=False, bake_anim=False,
                             mesh_smooth_type='OFF', use_mesh_modifiers=False, path_mode='COPY',
                             embed_textures=True, use_custom_props=True)
    n = patch_fbx_materials(out, ambient)
    if not n:
        warn("materiali dell'FBX non corretti (formato inatteso): imposta ambient/diffuse a mano")


def nbd_vertex_count(np, o):
    """Vertici che avra' la mesh nell'NBD: uno per ogni combinazione posizione + UV + normale."""
    me = o.data
    nl = len(me.loops)
    if not nl:
        return 0
    lv = np.zeros(nl, int)
    me.loops.foreach_get("vertex_index", lv)
    uv = np.zeros(nl * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    try:
        nr = np.array([c.vector[:] for c in me.corner_normals])
    except AttributeError:
        me.calc_normals_split()
        nr = np.array([l.normal[:] for l in me.loops])
    keys = np.c_[lv, np.round(uv.reshape(-1, 2) * 4096), np.round(nr * 256)]
    return len(np.unique(keys, axis=0))


# ------------------------------------------------------------------------------------------------
# Anteprima
# ------------------------------------------------------------------------------------------------
TEST_POSE = {"Node13": ("Z", -62.0), "Node17": ("Z", 62.0), "Node14": ("Y", 28.0), "Node18": ("Y", -28.0),
             "Node4": ("X", -32.0), "Node5": ("X", 48.0), "Node7": ("X", 14.0), "Node8": ("X", 10.0),
             "Node10": ("Y", 10.0), "Node11": ("X", 8.0), "Node21": ("Y", -22.0),
             "Node33": ("Z", -40.0), "Node34": ("X", 50.0), "Node35": ("X", 70.0)}
TEST_MOVE = {"Node27": (0.0, -2.5, 0.0), "Node23": (0.0, 0.8, 0.0), "Node25": (0.0, 0.8, 0.0)}
BENT_POSE = {"Node13": ("Z", -70.0), "Node17": ("Z", 70.0), "Node14": ("Y", 110.0), "Node18": ("Y", -110.0),
             "Node4": ("X", -75.0), "Node5": ("X", 95.0), "Node7": ("X", -20.0), "Node8": ("X", 40.0)}


def render_tex(np, P, F, UV, TEXI, texs, yaw=0.0, W=300, H=480, zoom=None, fcol=None):
    th = math.radians(yaw)
    R = np.array([[math.cos(th), 0, math.sin(th)], [0, 1, 0], [-math.sin(th), 0, math.cos(th)]])
    Q = P @ R.T
    if zoom is None:
        y0_, y1_ = Q[:, 1].min(), Q[:, 1].max()
        sc = min((H - 16) / max(1e-6, y1_ - y0_), (W - 10) / max(1e-6, 2 * np.abs(Q[:, 0]).max()))
        cx, cy = 0.0, (y0_ + y1_) / 2
    else:
        cx, cy, half = zoom
        sc = (min(W, H) / 2 - 4) / half
    sx = W / 2 + (Q[:, 0] - cx) * sc
    sy = H / 2 - (Q[:, 1] - cy) * sc
    img = np.zeros((H, W, 3), np.float32)
    img[:] = (112, 120, 134)
    zb = np.full((H, W), -1e30, np.float32)
    L = np.array([0.35, 0.55, 0.75])
    L /= np.linalg.norm(L)
    T = Q[F]
    n = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    sh = 0.5 + 0.5 * np.clip((n @ L) / (np.linalg.norm(n, axis=1) + 1e-12), 0, 1)
    vis = n[:, 2] > 0                                    # il gioco non disegna il retro delle facce
    for i in np.nonzero(vis)[0]:
        X = sx[F[i]]
        Y = sy[F[i]]
        x0, x1 = max(0, int(X.min())), min(W - 1, int(X.max()) + 1)
        y0, y1 = max(0, int(Y.min())), min(H - 1, int(Y.max()) + 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((Y[1] - Y[2]) * (gx - X[2]) + (X[2] - X[1]) * (gy - Y[2])) / den
        w1 = ((Y[2] - Y[0]) * (gx - X[2]) + (X[0] - X[2]) * (gy - Y[2])) / den
        w2 = 1 - w0 - w1
        ok = (w0 >= -1e-3) & (w1 >= -1e-3) & (w2 >= -1e-3)
        z = w0 * T[i, 0, 2] + w1 * T[i, 1, 2] + w2 * T[i, 2, 2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        win = ok & (z > sub)
        if not win.any():
            continue
        if fcol is not None:
            c = np.asarray(fcol[i], np.float32)
        else:
            t = texs[TEXI[i]]
            u = w0 * UV[i, 0, 0] + w1 * UV[i, 1, 0] + w2 * UV[i, 2, 0]
            v = w0 * UV[i, 0, 1] + w1 * UV[i, 1, 1] + w2 * UV[i, 2, 1]
            px = (np.mod(u[win], 1.0) * t.shape[1]).astype(int) % t.shape[1]
            py = ((1 - np.mod(v[win], 1.0)) * t.shape[0]).astype(int) % t.shape[0]
            c = t[py, px].astype(np.float32)
            if t.shape[2] == 4:                         # trasparenza: come l'alpha test del gioco
                keep = c[:, 3] >= 100
                ww = np.zeros_like(win)
                ww[win] = keep
                win = ww
                c = c[keep]
        if c.ndim == 2 and c.shape[1] == 4:
            c = c[:, :3]
        img[y0:y1 + 1, x0:x1 + 1][win] = c * sh[i]
        sub[win] = z[win]
    return np.clip(img, 0, 255).astype(np.uint8)


def _node_color(n):
    import colorsys
    k = int(n[4:])
    r, g, b = colorsys.hsv_to_rgb((k * 0.381966) % 1.0, 0.75, 0.95)
    return (int(r * 255), int(g * 255), int(b * 255))


def preview(bpy, np, arm, objs, texmap, path):
    """texmap: {nome materiale: immagine RGB (riga 0 = alto)}."""
    def gather(evaluated):
        P, F, UV, TI, WC = [], [], [], [], []
        texs, tidx = [], {}
        dg = bpy.context.evaluated_depsgraph_get()
        off = 0
        for o in objs:
            src = o.evaluated_get(dg) if evaluated else o
            me = src.to_mesh() if evaluated else o.data
            co = np.zeros(len(me.vertices) * 3)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3)
            uv = np.zeros(len(me.loops) * 2)
            me.uv_layers.active.data.foreach_get("uv", uv)
            uv = uv.reshape(-1, 2)
            mname = o.data.materials[0].name if o.data.materials else ""
            if mname not in tidx:
                tidx[mname] = len(texs)
                texs.append(texmap.get(mname, np.full((2, 2, 3), 180, np.uint8)))
            gname = {g.index: g.name for g in o.vertex_groups}
            dom = []
            for v in o.data.vertices:
                b = max(((g.weight, gname[g.group]) for g in v.groups if g.group in gname), default=(0, "Node3"))
                dom.append(_node_color(b[1]))
            dom = np.array(dom, np.float32)
            for p in me.polygons:
                li = list(p.loop_indices)
                vs = list(p.vertices)
                for j in range(1, len(vs) - 1):
                    F.append((vs[0] + off, vs[j] + off, vs[j + 1] + off))
                    UV.append(uv[[li[0], li[j], li[j + 1]]])
                    TI.append(tidx[mname])
                    WC.append(dom[[vs[0], vs[j], vs[j + 1]]].mean(0))
            P.append(co)
            off += len(co)
            if evaluated:
                src.to_mesh_clear()
        return np.vstack(P), np.array(F), np.array(UV), np.array(TI), texs, np.array(WC)

    P, F, UV, TI, texs, WC = gather(False)
    hy = SKEL["Node21"][1] + 6.0
    row = [render_tex(np, P, F, UV, TI, texs, 0), render_tex(np, P, F, UV, TI, texs, 180),
           render_tex(np, P, F, UV, TI, texs, 0, W=300, H=300, zoom=(0.0, hy, 13.0)),
           render_tex(np, P, F, UV, TI, texs, 35, W=300, H=300, zoom=(4.0, hy, 13.0))]
    for n, (ax, deg) in TEST_POSE.items():
        e = [0.0, 0.0, 0.0]
        e["XYZ".index(ax)] = math.radians(deg)
        arm.pose.bones[n].rotation_euler = e
    for n, loc in TEST_MOVE.items():
        arm.pose.bones[n].location = loc
    bpy.context.view_layer.update()
    P2, F2, UV2, TI2, texs2, WC2 = gather(True)
    row += [render_tex(np, P2, F2, UV2, TI2, texs2, 0), render_tex(np, P2, F2, UV2, TI2, texs2, 0, fcol=WC2),
            render_tex(np, P2, F2, UV2, TI2, texs2, 0, W=300, H=300, zoom=(0.0, hy, 13.0), fcol=WC2)]
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    for n, (ax, deg) in BENT_POSE.items():
        e = [0.0, 0.0, 0.0]
        e["XYZ".index(ax)] = math.radians(deg)
        arm.pose.bones[n].rotation_euler = e
    bpy.context.view_layer.update()
    P3, F3, UV3, TI3, texs3, _ = gather(True)
    el = arm.pose.bones["Node14"].head
    kn = arm.pose.bones["Node5"].head
    row += [render_tex(np, P3, F3, UV3, TI3, texs3, 0), render_tex(np, P3, F3, UV3, TI3, texs3, 90),
            render_tex(np, P3, F3, UV3, TI3, texs3, -30, W=300, H=300,
                       zoom=(el[0] * math.cos(math.radians(-30)) + el[2] * math.sin(math.radians(-30)), el[1], 13.0)),
            render_tex(np, P3, F3, UV3, TI3, texs3, 90, W=300, H=300,
                       zoom=(kn[2], kn[1], 16.0))]
    for pb in arm.pose.bones:
        pb.rotation_euler = (0, 0, 0)
        pb.location = (0, 0, 0)
    bpy.context.view_layer.update()
    H = max(r.shape[0] for r in row)
    row = [np.pad(r, ((0, H - r.shape[0]), (0, 2), (0, 0)), constant_values=30) for r in row]
    write_png(path, np.concatenate(row, axis=1))


# ------------------------------------------------------------------------------------------------
# Conversione completa
# ------------------------------------------------------------------------------------------------
def garment_names(others):
    out, names = {}, set()
    for o in sorted(others, key=lambda o: clean_name(o.name).lower()):
        nm = clean_name(o.name)
        base, k = nm, 2
        while nm in names:
            nm = "%s (%d)" % (base, k)
            k += 1
        names.add(nm)
        out[nm] = o
    return out


JOINTS = {"Node3": "pelvis", "Node4": "lThighBend", "Node5": "lShin", "Node6": "lFoot", "Node7": "rThighBend",
          "Node8": "rShin", "Node9": "rFoot", "Node10": "abdomenLower", "Node11": "chestLower",
          "Node12": "lCollar", "Node13": "lShldrBend", "Node14": "lForearmBend", "Node15": "lHand",
          "Node16": "rCollar", "Node17": "rShldrBend", "Node18": "rForearmBend", "Node19": "rHand",
          "Node20": "neckLower", "Node21": "head", "Node27": "lowerJaw"}


def import_hair(bpy, np, path, tex_path):
    before = set(bpy.data.objects)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise RuntimeError("capelli: formato non supportato (%s), usa .obj o .fbx" % ext)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("capelli: nel file %s non ci sono mesh" % os.path.basename(path))
    for o in meshes:
        apply_armature(bpy, [o])
    if len(meshes) > 1:
        with bpy.context.temp_override(object=meshes[0], active_object=meshes[0], selected_objects=meshes,
                                       selected_editable_objects=meshes):
            bpy.ops.object.join()
    hair = meshes[0]
    for o in new:
        if o is not hair and o.name in bpy.data.objects:
            bpy.data.objects.remove(o, do_unlink=True)
    P = world_coords(np, hair)
    ext_ = P.max(0) - P.min(0)
    k = 100.0 if ext_.max() < 5.0 else 1.0
    P = np.c_[P[:, 0], P[:, 2], -P[:, 1]] * k
    set_mesh_coords(np, hair, P)
    hair.name = hair.data.name = "hair"
    set_node_groups(np, hair, np.tile(np.eye(len(BONE_ORDER), dtype=np.float32)[BONE_ORDER.index("Node21")],
                                      (len(P), 1)))
    if not hair.data.uv_layers:
        hair.data.uv_layers.new(name="UVMap")
    if tex_path:
        img = bpy.data.images.load(tex_path)
        hair.data.materials.clear()
        hair.data.materials.append(make_material(bpy, "capelli", img))
    if not hair.data.materials:
        hair.data.materials.append(make_material(bpy, "capelli", None))
    cy = (P[:, 1].min() + P[:, 1].max()) / 2
    log("capelli: %s, %d triangoli, altezza %.0f..%.0f cm%s" % (
        os.path.basename(path), tri_count(hair), P[:, 1].min(), P[:, 1].max(),
        " (convertiti da metri)" if k == 100.0 else ""))
    if not 140.0 < cy < 200.0:
        warn("i capelli non sono all'altezza della testa (centro a %.0f cm): controlla posizione e unita' "
             "del file" % cy)
    return hair


def split_budget(np, objs, budget, shares=None):
    """Triangoli per capo: quote in percentuale (dalla finestra; uguali se mancano), mai piu' degli originali:
    quello che avanza va agli altri capi in proporzione alla loro quota."""
    if shares is None:
        area = np.ones(len(objs))
    else:
        area = np.array([max(0.0, float(x)) for x in shares]) + 1e-9
    tris = np.array([tri_count(o) for o in objs], float)
    alloc = np.zeros(len(objs))
    free = np.ones(len(objs), bool)
    left = float(budget)
    for _ in range(len(objs) + 1):
        if not free.any() or left <= 0:
            break
        share = left * area * free / area[free].sum()
        cap = free & (share + alloc >= tris)
        if not cap.any():
            alloc[free] += share[free]
            break
        left -= (tris[cap] - alloc[cap]).sum()
        alloc[cap] = tris[cap]
        free &= ~cap
    return [int(max(min(t, 40), a)) for a, t in zip(alloc, tris)]


def decimate_object(bpy, o, target):
    """Decimate 'Collapse' fino a target triangoli: prima simmetrico, se si blocca senza simmetria."""
    for sym in (True, False):
        for _ in range(4):
            cur = tri_count(o)
            if cur <= target * 1.03:
                return tri_count(o)
            mod = o.modifiers.new("Decimate", 'DECIMATE')
            mod.decimate_type = 'COLLAPSE'
            mod.ratio = max(0.01, target / float(cur))
            mod.use_collapse_triangulate = True
            mod.use_symmetry = sym
            mod.symmetry_axis = 'X'
            with bpy.context.temp_override(object=o, active_object=o, selected_objects=[o],
                                           selected_editable_objects=[o]):
                bpy.ops.object.modifier_apply(modifier=mod.name)
            if tri_count(o) >= cur * 0.97:
                break
    return tri_count(o)


# fasce di passaggio dei pesi: (osso genitore, osso figlio, giuntura, verso dell'arto, larghezza base cm)
JOINT_BANDS = [("Node13", "Node14", "Node14", ("Node14", "Node15"), 10.0, "gomito SX"),
               ("Node17", "Node18", "Node18", ("Node18", "Node19"), 10.0, "gomito DX"),
               ("Node4", "Node5", "Node5", ("Node5", "Node6"), 9.0, "ginocchio SX"),
               ("Node7", "Node8", "Node8", ("Node8", "Node9"), 9.0, "ginocchio DX"),
               ("Node12", "Node13", "Node13", ("Node13", "Node14"), 6.0, "spalla SX"),
               ("Node16", "Node17", "Node17", ("Node17", "Node18"), 6.0, "spalla DX"),
               ("Node14", "Node32", "Node15", ("Node14", "Node15"), 4.0, "polso SX"),
               ("Node18", "Node28", "Node19", ("Node18", "Node19"), 4.0, "polso DX")]


SHOULDER_BAND = [6.0, 0.0]
SHOULDER_MODE = ["no", 4.0]      # pesi della spalla: "liscia" (smooth), "p06" (copiati da P06), "no"          # larghezza della fascia della spalla, spostamento verso il gomito (cm)


def smooth_joints(np, P, W, scale):
    """Pesi sfumati attorno a gomiti, ginocchia, spalle e polsi: invece del passaggio secco di DAZ (che
    in DAZ e' corretto dai morph automatici, assenti nel gioco) il peso passa dal genitore al figlio
    lungo una fascia larga 'larghezza x scale' centrata sulla giuntura. Il giunto piegato resta pieno."""
    if scale <= 0:
        return W
    col = {n: i for i, n in enumerate(BONE_ORDER)}
    tot = W.sum(1)
    for a, b, j, (d0, d1), width, _ in JOINT_BANDS:
        J = np.array(SKEL[j], float)
        d = np.array(SKEL[d1], float) - np.array(SKEL[d0], float)
        d /= np.linalg.norm(d)
        if j in ("Node13", "Node17"):
            width = SHOULDER_BAND[0]
            J = J + d * SHOULDER_BAND[1]
        hw = width * scale / 2.0
        ia, ib = col[a], col[b]
        ab = W[:, ia] + W[:, ib]
        rel = P - J
        sd = rel @ d
        radial = np.linalg.norm(rel - sd[:, None] * d, axis=1)
        sel = (ab > 0) & (ab >= 0.6 * tot) & (np.abs(sd) < hw) & (radial < 14.0)
        if not sel.any():
            continue
        t = np.clip((sd[sel] + hw) / (2 * hw), 0.0, 1.0)
        f = t * t * (3 - 2 * t)
        W[sel, ib] = ab[sel] * f
        W[sel, ia] = ab[sel] * (1 - f)
    return W


# Spalle di un personaggio originale (P06, gia' sullo scheletro OB): superficie e pesi, per copiarne i pesi
P06_SHOULDER = json.loads('''{"V":[[-6.83,155.02,-4.89],[-7.57,155.32,-3.22],[-8.2,157.09,-4.44],[6.58,154.46,-4.0],[8.14,156.82,-4.53],[7.13,154.86,-1.84],[5.87,152.75,-4.46],[4.93,153.91,-5.36],[4.11,154.25,-6.44],[-2.63,152.52,-7.01],[-2.5,152.81,-7.33],[-3.63,153.47,-6.95],[-4.52,156.74,-8.76],[-8.14,157.04,-5.31],[-6.01,154.32,-6.46],[-5.53,153.24,-5.41],[-5.26,153.35,-5.76],[-8.49,159.35,0.17],[-7.75,158.16,1.09],[-6.03,157.6,0.58],[-6.81,158.14,2.21],[8.45,159.35,0.17],[6.18,158.17,-2.62],[8.13,157.05,0.46],[6.65,156.2,-0.39],[7.75,156.27,0.38],[7.2,155.18,2.02],[7.72,156.73,0.81],[-7.53,154.14,-1.59],[-8.01,154.46,-0.4],[-9.17,157.6,-1.14],[-8.18,157.34,0.15],[7.8,155.48,0.72],[-3.92,152.67,-5.64],[-5.23,152.91,-3.55],[-7.45,154.54,-4.41],[-5.8,158.27,-2.37],[6.03,157.78,0.58],[7.75,158.16,1.09],[6.82,158.14,2.21],[-7.08,153.81,1.51],[-7.7,155.3,0.48],[-6.72,153.95,-3.67],[-6.51,153.22,-1.99],[6.13,153.23,-0.73],[6.25,153.54,-2.38],[6.71,153.92,-1.34],[-7.01,155.87,-0.54],[-7.74,156.23,0.36],[-7.46,156.88,0.68],[-6.32,155.15,1.74],[3.65,153.1,-6.3],[3.27,152.53,-6.51],[4.33,156.68,-9.43],[2.8,152.77,-6.79],[-0.0,152.11,-7.14],[2.16,154.24,-8.89],[-1.79,154.22,-8.93],[-3.8,156.64,-9.5],[-5.4,153.17,-4.75],[7.11,154.27,-5.03],[7.97,156.9,-5.55],[5.31,153.88,-6.28],[4.0,152.55,-5.73],[9.1,157.46,-0.83],[7.68,154.88,-2.68],[8.17,154.86,-0.32],[6.87,153.81,1.85],[7.05,153.86,0.49],[-4.09,153.18,-6.69],[11.01,132.57,10.71],[10.83,130.92,11.03],[13.06,130.16,6.43],[-11.01,132.57,10.71],[-13.06,130.16,6.43],[-10.83,130.92,11.03],[6.83,137.04,8.88],[5.89,141.11,6.71],[0.09,136.49,8.62],[-6.83,137.04,8.88],[-5.89,141.11,6.71],[-6.78,141.09,-9.58],[0.0,141.44,-8.4],[0.0,146.94,-7.13],[6.78,141.09,-9.58],[4.03,155.85,-3.6],[-4.03,155.65,-3.6],[5.14,154.82,0.85],[3.84,152.91,-3.6],[4.92,151.69,0.84],[4.06,150.02,-4.17],[4.98,147.87,1.37],[-5.13,154.82,0.85],[-6.08,155.46,2.2],[-3.54,152.83,4.58],[-4.2,153.36,5.6],[-2.87,152.54,6.93],[-3.94,153.62,7.03],[-3.17,153.17,7.76],[-3.58,155.69,8.38],[-2.51,154.84,8.81],[0.0,153.04,-5.53],[0.0,150.05,-6.14],[-3.83,152.81,-3.61],[-4.92,151.69,0.84],[-3.41,152.75,3.15],[-3.07,150.61,3.12],[0.0,151.53,4.86],[-0.0,149.39,4.36],[3.09,150.61,3.12],[-4.93,157.46,7.72],[-5.85,157.49,6.04],[-5.12,154.43,5.83],[-2.84,146.41,3.62],[-4.97,147.87,1.37],[-4.04,150.07,-4.17],[-2.28,154.03,8.72],[-2.17,152.73,8.64],[-1.1,151.68,8.59],[-1.91,151.91,7.08],[-0.0,151.36,7.82],[0.0,151.61,6.14],[1.91,151.91,7.08],[3.54,152.83,4.58],[2.87,152.54,6.93],[4.21,153.36,5.6],[3.94,153.62,7.03],[5.1,154.43,5.83],[5.81,157.49,6.04],[6.07,155.46,2.2],[4.92,157.46,7.72],[-1.67,153.62,9.07],[0.0,151.47,8.61],[1.1,151.68,8.59],[2.89,146.41,3.62],[3.4,152.75,3.27],[-0.01,145.05,3.78],[2.46,154.84,8.81],[2.37,154.03,8.72],[3.11,153.17,7.76],[3.58,155.69,8.38],[2.17,152.73,8.64],[1.69,153.62,9.07],[-17.71,138.77,-1.48],[-16.17,138.86,-5.35],[-15.76,134.74,-0.57],[-13.22,133.6,-6.06],[-12.06,127.73,-4.62],[-10.2,128.11,-6.44],[30.01,145.07,-5.68],[29.73,147.11,-1.74],[22.21,145.19,-5.74],[24.31,147.25,-1.41],[18.98,146.14,-6.02],[20.12,148.28,-1.37],[15.66,146.53,-6.28],[15.84,148.94,-1.25],[10.76,146.68,-6.76],[10.76,148.21,-1.05],[-30.23,138.89,-1.48],[-29.7,141.43,2.55],[-22.05,140.87,2.63],[-30.28,144.9,1.78],[-21.8,145.48,1.71],[-24.31,147.25,-1.41],[-18.76,146.11,2.19],[-20.12,148.28,-1.37],[-15.84,148.94,-1.25],[-15.66,146.53,-6.28],[-10.76,146.68,-6.76],[-14.79,141.86,-8.05],[7.07,148.79,-2.49],[11.07,147.18,1.45],[4.81,145.77,4.23],[-7.07,148.79,-2.49],[-11.07,147.18,1.45],[-4.81,145.77,4.23],[-11.41,146.04,3.14],[-5.19,143.93,4.97],[0.04,140.58,6.56],[-14.57,129.1,0.62],[-10.76,148.21,-1.05],[-29.93,140.15,-5.68],[-24.62,138.91,-5.02],[-21.92,142.0,-6.58],[-19.27,139.01,-5.1],[-19.25,142.01,-7.19],[-14.55,135.19,2.13],[0.0,143.99,5.33],[5.31,143.8,5.15],[11.41,146.04,3.14],[11.81,141.42,5.15],[12.11,136.83,7.32],[13.77,135.66,5.0],[14.55,135.19,2.13],[14.39,129.1,0.63],[15.68,134.74,-0.57],[12.08,127.73,-4.61],[13.12,133.6,-6.07],[10.21,128.11,-6.51],[6.32,132.38,-9.32],[-4.96,147.23,-6.72],[-7.92,148.0,-4.74],[-11.25,141.43,-9.02],[-6.32,132.38,-9.32],[14.79,141.86,-8.05],[19.25,142.01,-7.19],[21.92,142.0,-6.58],[29.98,142.61,-6.37],[29.93,140.15,-5.68],[30.23,138.89,-1.48],[16.17,138.86,-5.35],[19.27,139.01,-5.1],[17.61,138.77,-1.48],[23.47,138.56,-1.51],[17.41,141.27,3.42],[11.25,141.43,-9.02],[4.96,147.23,-6.72],[5.99,132.57,12.26],[-15.25,143.04,3.55],[-11.81,141.42,5.15],[-17.41,141.27,3.42],[-12.98,137.56,6.27],[-13.77,135.66,5.0],[-12.11,136.83,7.32],[15.61,146.37,2.36],[18.76,146.11,2.19],[15.25,143.04,3.55],[-15.61,146.37,2.36],[22.05,140.87,2.63],[21.8,145.48,1.71],[29.7,141.43,2.55],[30.28,144.9,1.78],[7.92,148.0,-4.74],[24.62,138.91,-5.02],[12.92,137.51,6.23],[-23.47,138.56,-1.51],[-29.73,147.11,-1.74],[-30.01,145.07,-5.68],[-22.21,145.19,-5.74],[-18.98,146.14,-6.02],[-29.98,142.61,-6.37]],"W":[[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[21,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[11,1.0]],[[20,0.5],[21,0.5]],[[20,0.5],[21,0.5]],[[21,1.0]],[[20,0.75],[21,0.25]],[[20,0.8],[21,0.2]],[[20,0.75],[21,0.25]],[[11,0.9],[20,0.1]],[[21,1.0]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.75],[27,0.25]],[[21,0.3],[27,0.7]],[[20,0.75],[21,0.25]],[[20,0.75],[21,0.25]],[[20,0.75],[21,0.25]],[[20,0.8],[21,0.2]],[[21,1.0]],[[20,0.8],[21,0.2]],[[20,0.5],[21,0.5]],[[20,0.75],[21,0.25]],[[20,0.8],[21,0.2]],[[21,0.9],[27,0.1]],[[21,0.9],[27,0.1]],[[21,0.2],[27,0.8]],[[11,0.9],[20,0.1]],[[11,0.9],[20,0.1]],[[20,0.75],[21,0.25]],[[21,0.3],[27,0.7]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[21,0.9],[27,0.1]],[[21,0.2],[27,0.8]],[[21,0.9],[27,0.1]],[[21,0.3],[27,0.7]],[[21,0.2],[27,0.8]],[[21,0.2],[27,0.8]],[[11,0.9],[20,0.1]],[[21,1.0]],[[11,0.9],[20,0.1]],[[21,0.3],[27,0.7]],[[21,0.3],[27,0.7]],[[21,0.2],[27,0.8]],[[21,0.75],[27,0.25]],[[21,0.2],[27,0.8]],[[21,0.3],[27,0.7]],[[16,0.5],[17,0.5]],[[11,0.2],[16,0.8]],[[11,0.7],[16,0.3]],[[11,0.75],[16,0.25]],[[11,0.9],[16,0.1]],[[11,0.9],[16,0.1]],[[12,0.02],[13,0.98]],[[12,0.02],[13,0.98]],[[12,0.2],[13,0.8]],[[12,0.1],[13,0.9]],[[12,0.25],[13,0.75]],[[12,0.25],[13,0.75]],[[12,0.75],[13,0.25]],[[12,0.75],[13,0.25]],[[11,0.5],[12,0.5]],[[11,0.5],[12,0.5]],[[16,0.05],[17,0.95]],[[16,0.03],[17,0.97]],[[16,0.15],[17,0.85]],[[16,0.02],[17,0.98]],[[16,0.1],[17,0.9]],[[16,0.1],[17,0.9]],[[16,0.25],[17,0.75]],[[16,0.25],[17,0.75]],[[16,0.75],[17,0.25]],[[16,0.75],[17,0.25]],[[11,0.5],[16,0.5]],[[11,0.05],[16,0.75],[17,0.2]],[[11,0.75],[12,0.25]],[[11,0.25],[12,0.75]],[[11,0.9],[20,0.1]],[[11,0.75],[16,0.25]],[[11,0.25],[16,0.75]],[[11,0.9],[20,0.1]],[[11,0.25],[16,0.75]],[[11,0.9],[20,0.1]],[[11,0.9],[20,0.1]],[[11,0.8],[16,0.2]],[[11,0.5],[16,0.5]],[[16,0.02],[17,0.98]],[[16,0.1],[17,0.9]],[[16,0.2],[17,0.8]],[[16,0.5],[17,0.5]],[[16,0.3],[17,0.7]],[[11,0.7],[16,0.3]],[[11,0.9],[20,0.1]],[[11,0.9],[20,0.1]],[[11,0.25],[12,0.75]],[[11,0.5],[12,0.4],[13,0.1]],[[11,0.6],[12,0.4]],[[11,0.8],[12,0.2]],[[11,0.7],[12,0.3]],[[11,0.8],[12,0.2]],[[11,0.7],[12,0.3]],[[11,0.9],[12,0.1]],[[11,0.75],[12,0.25]],[[11,0.9],[12,0.1]],[[10,0.1],[11,0.9]],[[11,0.5],[16,0.5]],[[11,0.75],[16,0.25]],[[11,0.5],[16,0.5]],[[10,0.1],[11,0.9]],[[11,0.05],[12,0.75],[13,0.2]],[[12,0.3],[13,0.7]],[[12,0.2],[13,0.8]],[[12,0.02],[13,0.98]],[[12,0.02],[13,0.98]],[[12,0.05],[13,0.95]],[[11,0.2],[12,0.8]],[[12,0.4],[13,0.6]],[[12,0.5],[13,0.5]],[[12,0.2],[13,0.8]],[[12,0.6],[13,0.4]],[[11,0.5],[12,0.5]],[[11,0.5],[12,0.5]],[[10,0.1],[11,0.9]],[[11,0.5],[16,0.4],[17,0.1]],[[11,0.5],[16,0.5]],[[16,0.6],[17,0.4]],[[11,0.7],[16,0.3]],[[11,0.8],[16,0.2]],[[11,0.6],[16,0.4]],[[12,0.75],[13,0.25]],[[12,0.25],[13,0.75]],[[11,0.5],[12,0.4],[13,0.1]],[[16,0.75],[17,0.25]],[[12,0.15],[13,0.85]],[[12,0.1],[13,0.9]],[[12,0.03],[13,0.97]],[[12,0.02],[13,0.98]],[[11,0.75],[12,0.25]],[[12,0.1],[13,0.9]],[[11,0.7],[12,0.3]],[[16,0.2],[17,0.8]],[[16,0.02],[17,0.98]],[[16,0.02],[17,0.98]],[[16,0.25],[17,0.75]],[[16,0.25],[17,0.75]],[[16,0.02],[17,0.98]]],"F":[[0,1,2],[3,4,5],[6,7,8],[9,10,11],[13,12,14],[13,14,15],[15,14,16],[18,17,19],[18,19,20],[22,23,24],[24,23,25],[24,25,26],[26,25,27],[1,28,2],[2,28,29],[2,29,30],[30,29,31],[22,5,23],[23,5,32],[33,11,16],[16,11,0],[16,0,15],[15,0,34],[15,34,35],[1,0,36],[36,0,11],[22,21,37],[37,21,38],[37,38,39],[40,28,41],[41,28,1],[41,1,31],[31,1,36],[17,36,19],[0,42,1],[1,42,43],[44,45,46],[46,45,3],[46,3,5],[36,47,31],[31,47,48],[31,48,49],[49,48,50],[36,17,47],[47,17,49],[47,49,50],[51,52,8],[8,52,53],[26,27,24],[24,27,22],[8,3,22],[22,3,5],[52,51,54],[54,51,55],[54,55,56],[56,55,57],[35,34,13],[13,34,0],[13,0,2],[59,34,15],[34,15,59],[11,12,9],[9,12,58],[9,58,10],[10,58,57],[10,57,55],[17,31,49],[8,6,3],[3,6,60],[3,60,61],[61,60,62],[61,62,53],[53,62,63],[53,63,8],[8,63,62],[8,62,7],[7,62,6],[31,17,30],[28,40,29],[29,40,41],[29,41,31],[5,4,65],[65,4,64],[65,64,66],[66,64,32],[66,32,67],[67,5,68],[68,5,65],[68,65,66],[56,53,54],[21,23,64],[64,23,32],[66,67,68],[22,27,21],[21,27,25],[21,25,23],[67,32,5],[12,11,69],[69,11,33],[69,33,16],[48,47,50],[61,4,3],[54,53,52],[15,35,13],[6,62,60],[69,16,12],[12,16,14],[70,71,72],[73,74,75],[76,77,78],[79,78,80],[82,81,83],[82,83,84],[8,22,85],[36,11,86],[22,37,85],[85,37,87],[85,87,88],[88,87,89],[88,89,90],[90,89,91],[36,86,19],[19,86,92],[19,92,93],[93,92,94],[93,94,95],[95,94,96],[95,96,97],[97,96,98],[97,98,99],[99,98,100],[8,85,51],[101,85,88],[101,88,102],[102,88,90],[86,101,103],[86,103,92],[92,103,104],[92,104,105],[105,104,106],[105,106,107],[107,106,108],[107,108,109],[110,111,97],[97,111,112],[97,112,95],[95,112,93],[113,106,114],[114,106,104],[114,104,115],[115,104,103],[115,103,102],[102,103,101],[99,110,97],[116,100,98],[116,98,117],[117,98,96],[117,96,118],[118,96,119],[118,119,120],[120,119,121],[120,121,122],[122,121,123],[122,123,124],[124,123,125],[124,125,126],[126,125,127],[126,127,128],[128,127,129],[128,129,39],[39,129,37],[19,93,20],[20,93,112],[20,112,111],[131,116,117],[133,132,120],[133,120,122],[134,91,109],[109,91,89],[109,89,135],[135,89,87],[135,87,123],[123,87,129],[123,129,125],[125,129,127],[109,108,136],[136,108,106],[136,106,113],[109,136,134],[137,138,139],[137,139,140],[140,139,126],[140,126,130],[130,126,128],[141,133,124],[141,124,139],[139,124,126],[96,94,119],[119,94,121],[94,105,121],[121,105,107],[121,107,135],[135,107,109],[139,138,141],[141,138,142],[118,120,132],[133,122,124],[94,92,105],[37,129,87],[123,121,135],[143,144,145],[145,144,146],[145,146,147],[147,146,148],[150,149,151],[150,151,152],[152,151,153],[152,153,154],[154,153,155],[154,155,156],[156,155,157],[156,157,158],[160,159,161],[160,161,162],[162,161,163],[162,163,164],[164,163,165],[164,165,166],[166,165,167],[166,167,168],[168,167,169],[168,169,170],[158,171,172],[172,171,91],[172,91,173],[173,91,134],[173,134,136],[115,174,114],[114,174,175],[114,175,176],[176,175,177],[176,177,178],[178,177,80],[178,80,179],[179,80,78],[179,78,77],[90,91,171],[147,180,145],[175,174,181],[159,182,183],[183,182,184],[183,184,185],[185,184,186],[185,186,144],[144,186,170],[143,145,187],[187,145,180],[187,180,74],[113,176,136],[136,176,188],[136,188,173],[173,188,189],[173,189,190],[190,189,77],[190,77,191],[191,77,76],[191,76,192],[192,76,70],[192,70,193],[193,70,72],[193,72,194],[194,72,195],[194,195,196],[196,195,197],[196,197,198],[198,197,199],[198,199,200],[83,81,201],[201,81,169],[201,169,202],[202,169,181],[202,181,174],[170,169,203],[203,169,81],[203,81,204],[144,170,146],[146,170,203],[146,203,204],[157,155,205],[205,155,153],[205,153,206],[206,153,151],[206,151,207],[207,151,208],[207,208,209],[205,206,211],[211,206,212],[211,212,213],[213,212,214],[215,194,213],[213,194,196],[213,196,211],[211,196,198],[211,198,205],[205,198,216],[205,216,157],[157,216,84],[157,84,217],[217,84,83],[217,83,90],[90,83,102],[177,219,220],[220,219,221],[220,221,222],[222,221,223],[222,223,224],[224,223,73],[224,73,79],[158,172,156],[156,172,225],[156,225,226],[226,225,227],[226,227,215],[221,219,165],[165,219,228],[165,228,167],[167,228,175],[167,175,181],[143,187,221],[221,187,223],[213,229,215],[215,229,230],[215,230,226],[226,230,152],[226,152,154],[213,214,229],[229,214,210],[229,210,231],[227,225,190],[190,225,172],[90,171,233],[233,171,158],[233,158,157],[200,84,216],[200,216,198],[190,172,173],[210,214,234],[234,214,212],[234,212,207],[207,212,206],[174,115,202],[202,115,201],[73,223,74],[74,223,187],[79,80,220],[220,80,177],[227,191,215],[215,191,235],[215,235,193],[193,235,192],[191,227,190],[236,143,161],[161,143,221],[161,221,163],[163,221,165],[219,177,228],[228,177,175],[167,181,169],[236,161,159],[159,183,236],[236,183,185],[236,185,143],[143,185,144],[176,113,114],[102,83,115],[115,83,201],[79,220,224],[224,220,222],[156,226,154],[152,230,232],[232,230,229],[232,229,231],[210,234,209],[209,234,207],[191,192,235],[193,194,215],[70,76,218],[238,237,239],[239,237,164],[239,164,240],[240,164,166],[240,166,168],[189,188,179],[179,188,178],[146,204,148],[168,170,240],[240,170,186],[240,186,239],[239,186,184],[239,184,241],[241,184,182],[152,232,150],[151,149,208],[179,77,189],[157,217,233],[233,217,90],[178,188,176],[237,162,164],[239,241,238]]}''')


def shoulders_from_p06(np, P, W):
    """Pesi di spalla e ascella presi da P06 (personaggio originale: si deforma bene con le animazioni del
    gioco): ogni vertice della zona prende i pesi del punto piu' vicino della spalla di P06 (interpolati sul
    triangolo), sfumati verso i pesi propri ai bordi della zona."""
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    SV = np.array(P06_SHOULDER["V"], float)
    SF = np.array(P06_SHOULDER["F"], int)
    SW = np.zeros((len(SV), W.shape[1]))
    for i, row in enumerate(P06_SHOULDER["W"]):
        for n, w in row:
            if 1 <= n <= W.shape[1]:
                SW[i, n - 1] = w
    bvh = BVHTree.FromPolygons([tuple(v) for v in SV], [tuple(f) for f in SF])
    f = np.zeros(len(P))
    for side, j in ((1, "Node13"), (-1, "Node17")):
        d = P - np.array(SKEL[j], float)
        dy = np.where(d[:, 1] < 0, d[:, 1] * 0.7, d[:, 1] * 1.3)
        r = np.sqrt(d[:, 0] ** 2 + dy ** 2 + d[:, 2] ** 2)
        g = np.clip((12.0 - r) / 5.0, 0.0, 1.0)
        f = np.maximum(f, g * g * (3 - 2 * g))
    shc = [BONE_ORDER.index(n) for n in SHOULDER_SET]
    W = W.copy()
    n_ok = 0
    for i in np.nonzero(f > 0)[0]:
        if W[i, shc].sum() < 0.5 * W[i].sum():
            continue
        loc, nrm, fi, dist = bvh.find_nearest(Vector(P[i]), 6.0)
        if loc is None:
            continue
        a, b, c = SF[fi]
        A, B, C = (Vector(SV[k]) for k in (a, b, c))
        # coordinate baricentriche del punto sul triangolo
        v0, v1, v2 = B - A, C - A, loc - A
        d00, d01, d11, d20, d21 = v0.dot(v0), v0.dot(v1), v1.dot(v1), v2.dot(v0), v2.dot(v1)
        den = d00 * d11 - d01 * d01
        if abs(den) < 1e-12:
            continue
        bb = (d11 * d20 - d01 * d21) / den
        cc = (d00 * d21 - d01 * d20) / den
        aa = 1.0 - bb - cc
        wp = aa * SW[a] + bb * SW[b] + cc * SW[c]
        if wp.sum() <= 0:
            continue
        wp = wp / wp.sum() * W[i].sum()
        k = f[i] * float(np.clip((6.0 - dist) / 3.0, 0.0, 1.0))
        W[i] = W[i] * (1 - k) + wp * k
        n_ok += 1
    log("spalle: pesi presi da P06 su %d vertici" % n_ok)
    return W


SHOULDER_SET = ("Node10", "Node11", "Node12", "Node13", "Node20", "Node16", "Node17")


def mesh_components(np, o):
    """Pezzi staccati della mesh -> numero del pezzo per ogni vertice."""
    n = len(o.data.vertices)
    par = np.arange(n)

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a
    e = np.zeros(len(o.data.edges) * 2, int)
    o.data.edges.foreach_get("vertices", e)
    for a, b in e.reshape(-1, 2):
        ra, rb = find(a), find(b)
        if ra != rb:
            par[ra] = rb
    roots = np.array([find(i) for i in range(n)])
    _, comp = np.unique(roots, return_inverse=True)
    return comp


def mesh_neighbors(np, o):
    """Spigoli della mesh -> (a, b) array per la media dei vicini."""
    e = np.zeros(len(o.data.edges) * 2, int)
    o.data.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    return np.concatenate([e[:, 0], e[:, 1]]), np.concatenate([e[:, 1], e[:, 0]])


def smooth_shoulders(np, o, P, W, strength=1.0, iters=40):
    """Pesi di spalla e ascella sfumati sulla superficie (come lo smooth dei pesi di Blender): il passaggio
    busto / clavicola / braccio si allarga, di piu' sotto il braccio (ascella) che sopra. Cosi' quando il
    braccio va avanti o giu' la spalla resta tonda e il braccio non si stringe vicino all'ascella."""
    if strength <= 0:
        return W
    a, b = mesh_neighbors(np, o)
    cols = [BONE_ORDER.index(n) for n in SHOULDER_SET]
    deg = np.bincount(a, minlength=len(P)).astype(float)
    deg[deg == 0] = 1.0
    f = np.zeros(len(P))
    for side, j in ((1, "Node13"), (-1, "Node17")):
        J = np.array(SKEL[j], float)
        d = P - J
        dy = np.where(d[:, 1] < 0, d[:, 1] * 0.6, d[:, 1] * 1.4)        # piu' larga sotto (ascella), stretta sopra
        dx = np.where(np.sign(d[:, 0]) == side, d[:, 0] * 0.9, d[:, 0] * 1.6)  # verso il braccio piu' che verso il collo
        r = np.sqrt(dx ** 2 + dy ** 2 + d[:, 2] ** 2)
        g = np.clip((13.0 - r) / 6.0, 0.0, 1.0)
        f = np.maximum(f, g * g * (3 - 2 * g))
    sub = W[:, cols].astype(float)
    tot = sub.sum(1, keepdims=True)
    on = (f > 0) & (tot[:, 0] > 0.5 * np.maximum(W.sum(1), 1e-9))
    k = (0.5 * f * min(1.0, strength))[:, None] * on[:, None]
    for _ in range(int(iters * max(1.0, strength))):
        avg = np.zeros_like(sub)
        np.add.at(avg, a, sub[b])
        avg /= deg[:, None]
        sub = sub + k * (avg - sub)
    s2 = sub.sum(1, keepdims=True)
    s2[s2 <= 0] = 1.0
    sub = sub / s2 * tot
    W = W.copy()
    W[:, cols] = np.where(on[:, None], sub, W[:, cols])
    return W


def wrist_like_p06(np, P, W):
    """Polso come i personaggi originali (P06): avambraccio tutto sull'avambraccio fino al polso, poi un anello
    stretto meta' polso (Node15) e meta' mano (Node32), poi la mano. Senza Node15 la mano gira di colpo
    attorno al polso e il polso si 'rompe'."""
    col = {n: i for i, n in enumerate(BONE_ORDER)}
    for fa, wr, hd, nxt in (("Node14", "Node15", "Node32", "Node14"), ("Node18", "Node19", "Node28", "Node18")):
        J = np.array(SKEL[wr], float)
        d = J - np.array(SKEL[nxt], float)
        d /= np.linalg.norm(d)
        rel = P - J
        sd = rel @ d
        radial = np.linalg.norm(rel - sd[:, None] * d, axis=1)
        ifa, iwr, ihd = col[fa], col[wr], col[hd]
        arm = W[:, ifa] + W[:, iwr] + W[:, ihd]
        sel = (arm > 0.6 * W.sum(1)) & (radial < 7.0) & (sd > -4.0) & (sd < 4.0)
        if not sel.any():
            continue
        x = sd[sel]
        hand = np.clip((x + 2.5) / 2.0, 0.0, 1.0)            # da -2.5 a -0.5 cm: avambraccio -> polso/mano
        hand = hand * hand * (3 - 2 * hand)
        half = np.clip((2.5 - x) / 1.5, 0.0, 1.0)             # fino a +1 cm meta' Node15, poi sfuma fino a +2.5
        a = arm[sel]
        W[sel, ifa] = a * (1 - hand)
        W[sel, iwr] = a * hand * 0.5 * half
        W[sel, ihd] = a * hand * (1 - 0.5 * half)
    return W


def _bvh_of(objs):
    from mathutils.bvhtree import BVHTree
    verts, polys, off = [], [], 0
    for g in objs:
        me = g.data
        verts += [v.co.copy() for v in me.vertices]
        polys += [[i + off for i in p.vertices] for p in me.polygons]
        off += len(me.vertices)
    return BVHTree.FromPolygons(verts, polys) if polys else None, polys


def weights_from_body(np, g, srcs, near=1.5, far=6.0):
    """Il vestito copia i pesi della pelle piu' vicina (fino a 'near' cm del tutto, sfumando fino a 'far'):
    pelle e stoffa si muovono insieme e non si compenetrano. Le parti lontane (gonne larghe) tengono i pesi DAZ."""
    bvh, polys = _bvh_of(srcs)
    if bvh is None:
        return 0
    Ws = np.vstack([get_node_weights(np, o) for o in srcs])
    Ps = np.vstack([np.array([v.co[:] for v in o.data.vertices]) for o in srcs])
    W = get_node_weights(np, g)
    n = 0
    for v in g.data.vertices:
        loc, nrm, fi, d = bvh.find_nearest(v.co, far)
        if loc is None:
            continue
        t = min(1.0, max(0.0, (far - d) / (far - near)))
        if t <= 0:
            continue
        vs = polys[fi]
        dd = np.linalg.norm(Ps[vs] - np.array(loc[:]), axis=1) + 1e-4
        k = (1.0 / dd) / (1.0 / dd).sum()
        W[v.index] = t * (k[:, None] * Ws[vs]).sum(0) + (1 - t) * W[v.index]
        n += 1
    set_node_groups(np, g, limit4(np, W))
    return n


def skin_vs_garments(np, body, garments, margin=0.3, room=None):
    """Pelle e vestiti: -> (facce del corpo del tutto coperte, vertici spinti dentro).
    Coperto = un capo davanti alla pelle (entro 4 cm) oppure la pelle che esce dal capo (fino a 3 cm).
    I vertici coperti vengono anche spinti sotto il capo di almeno 'margin' cm, cosi' nelle facce di
    bordo che restano la pelle non buca il vestito."""
    bvh, _ = _bvh_of(garments)
    me = body.data
    nv = len(me.vertices)
    if bvh is None:
        return np.zeros(len(me.polygons), bool), 0
    covered = np.zeros(nv, bool)
    push = np.zeros(nv)
    for v in me.vertices:
        p, n = v.co, v.normal
        # pelle che esce da un capo (il capo e' dietro la pelle): controllato sempre, anche se davanti
        # c'e' un altro strato (es. piede che buca la tomaia sotto la suola)
        # (solo pochi mm: una suola o un capo piu' lontano dietro la pelle non e' una compenetrazione)
        loc, nrm, idx, dist = bvh.ray_cast(p + n * 0.05, -n, 0.85)
        if loc is not None and nrm.dot(n) > 0.2:
            covered[v.index] = True
            push[v.index] = dist - 0.05 + margin
        loc, nrm, idx, dist = bvh.ray_cast(p - n * 0.3, n, 4.3)
        if loc is not None and nrm.dot(n) > 0.2:
            covered[v.index] = True
            gap = dist - 0.3
            if gap < margin:
                push[v.index] = max(push[v.index], margin - gap)
    if room is not None:                        # spinta totale massima per vertice (tutti i passaggi)
        push = np.minimum(push, room)
        room -= push
    else:
        push = np.minimum(push, 1.2)
    co = np.zeros(nv * 3)
    me.vertices.foreach_get("co", co)
    nr = np.zeros(nv * 3)
    me.vertices.foreach_get("normal", nr)
    co = co.reshape(-1, 3) - nr.reshape(-1, 3) * push[:, None]
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    mask = np.array([all(covered[i] for i in p.vertices) for p in me.polygons], bool)
    return mask, int((push > 0).sum())


ZONE_NODES = {"neck": ("Node20",), "torso": ("Node3", "Node10", "Node11"),
              "arms": tuple("Node%d" % i for i in list(range(12, 20)) + list(range(28, 36))),
              "legs": ("Node4", "Node5", "Node7", "Node8"), "feet": ("Node6", "Node9")}
ZONE_NAMES_IT = {"neck": "collo", "torso": "busto e bacino", "arms": "braccia e mani", "legs": "gambe", "feet": "piedi"}


def garment_depth(np, g, parts):
    """Distanza media del capo dalla pelle: piu' piccola = strato piu' interno."""
    srcs = [o for o in (parts.get("body"), parts.get("face")) if o is not None]
    bvh, _ = _bvh_of(srcs)
    if bvh is None:
        return 0.0
    vs = g.data.vertices
    step = max(1, len(vs) // 800)
    d = []
    for i in range(0, len(vs), step):
        loc, nrm, fi, dist = bvh.find_nearest(vs[i].co, 30.0)
        d.append(dist if loc is not None else 30.0)
    return float(np.mean(d)) if d else 0.0


def skin_cull_mask(np, obj, cutters, zones=None, margin=3.0):
    """Facce di obj (pelle o capo interno) del tutto coperte dai 'cutters', da togliere.
    zones: zone del corpo in cui si puo' togliere (None = tutte); margin: cm di pelle lasciati attorno ai
    bordi aperti dei capi (scollo, maniche, orli, spacchi), dove altrimenti si vedrebbe il buco."""
    from mathutils.kdtree import KDTree
    cutters = [c for c in cutters if len(c.data.polygons)]
    bvh, _ = _bvh_of(cutters) if cutters else (None, None)
    me = obj.data
    nv = len(me.vertices)
    if bvh is None or nv == 0:
        return np.zeros(len(me.polygons), bool)
    cov = np.zeros(nv, bool)
    for v in me.vertices:
        p, n = v.co, v.normal
        loc, nrm, idx, dist = bvh.ray_cast(p - n * 0.3, n, 4.3)
        if loc is not None and nrm.dot(n) > 0.2:
            cov[v.index] = True
            continue
        loc, nrm, idx, dist = bvh.ray_cast(p + n * 0.05, -n, 0.85)
        if loc is not None and nrm.dot(n) > 0.2:
            cov[v.index] = True
    if zones is not None:
        ok_nodes = [BONE_ORDER.index(n) for z in zones for n in ZONE_NODES.get(z, ())]
        dom = get_node_weights(np, obj).argmax(1)
        cov &= np.isin(dom, ok_nodes)
    # bordo: un numero (cm) o uno per zona {"neck": 2, "torso": 3, ...} (zona del Node dominante del vertice)
    if isinstance(margin, dict):
        dom_ = get_node_weights(np, obj).argmax(1)
        mv = np.full(nv, 3.0)
        for z, nodes in ZONE_NODES.items():
            if z in margin:
                mv[np.isin(dom_, [BONE_ORDER.index(n) for n in nodes])] = float(margin[z])
    else:
        mv = np.full(nv, float(margin))
    if mv.max() > 0:
        edge_pts = []
        for g in cutters:
            gm = g.data
            cnt = {}
            for p in gm.polygons:
                vs = list(p.vertices)
                for j in range(len(vs)):
                    e = tuple(sorted((vs[j], vs[(j + 1) % len(vs)])))
                    cnt[e] = cnt.get(e, 0) + 1
            for (a, b), c in cnt.items():
                if c == 1:
                    edge_pts.append(gm.vertices[a].co.copy())
                    edge_pts.append((gm.vertices[a].co + gm.vertices[b].co) * 0.5)
        if edge_pts:
            kd = KDTree(len(edge_pts))
            for i, p in enumerate(edge_pts):
                kd.insert(p, i)
            kd.balance()
            for v in me.vertices:
                if cov[v.index] and kd.find(v.co)[2] < mv[v.index]:
                    cov[v.index] = False
    return np.array([all(cov[i] for i in p.vertices) for p in me.polygons], bool)


def cull_hidden(np, body, garments, maxdist=4.0):
    """Toglie le facce del corpo coperte dai vestiti (raggio lungo la normale che incontra un capo
    rivolto dalla stessa parte entro maxdist cm). Restano le facce con almeno un vertice scoperto."""
    from mathutils.bvhtree import BVHTree
    verts, polys, off = [], [], 0
    for g in garments:
        me = g.data
        verts += [v.co.copy() for v in me.vertices]
        polys += [[i + off for i in p.vertices] for p in me.polygons]
        off += len(me.vertices)
    if not polys:
        return 0
    bvh = BVHTree.FromPolygons(verts, polys)
    me = body.data
    covered = np.zeros(len(me.vertices), bool)
    for v in me.vertices:
        n = v.normal
        loc, nrm, idx, dist = bvh.ray_cast(v.co - n * 0.3, n, maxdist)
        if loc is not None and nrm.dot(n) > 0.2:
            covered[v.index] = True
    mask = np.array([all(covered[i] for i in p.vertices) for p in me.polygons], bool)
    return mask


def make_dummy(bpy, np, mat):
    c = np.array(SKEL["Node21"]) + np.array([0.0, 6.0, -1.0])
    V = [tuple(c), tuple(c + [0.3, 0, 0]), tuple(c + [0, 0.3, 0])]
    me = bpy.data.meshes.new("dummy")
    me.from_pydata(V, [], [(0, 1, 2)])
    me.uv_layers.new(name="UVMap")
    if mat:
        me.materials.append(mat)
    o = bpy.data.objects.new("dummy", me)
    bpy.context.scene.collection.objects.link(o)
    W = np.zeros((3, len(BONE_ORDER)), np.float32)
    W[:, BONE_ORDER.index("Node21")] = 1.0
    set_node_groups(np, o, W)
    return o


def safe_name(s):
    s = re.sub(r"[^A-Za-z0-9_\-]+", "_", s.strip())
    return s.strip("_") or "outfit"


# ------------------------------------------------------------------------------------------------
# Colori naturali: Tonalita'/Saturazione/Luminosita' come in Photoshop, con "Colora"
# parametri: {"mode": "regola"|"colora", "h": .., "s": .., "l": .., "amount": 0..100}
#   regola: h -180..180 (spostamento), s e l -100..100 (come Photoshop)
#   colora: h 0..360, s 0..100 (tinta unica); l -100..100 = luminosita' media voluta (chiaroscuro conservato)
# ------------------------------------------------------------------------------------------------
COLOR_PRESETS = {
    "capelli": [("Biondo cenere", {"mode": "colora", "h": 42, "s": 18, "l": 35}),
                ("Biondo dorato", {"mode": "colora", "h": 40, "s": 48, "l": 38}),
                ("Biondo fragola", {"mode": "colora", "h": 25, "s": 50, "l": 30}),
                ("Castano chiaro", {"mode": "colora", "h": 28, "s": 38, "l": 5}),
                ("Castano scuro", {"mode": "colora", "h": 22, "s": 32, "l": -30}),
                ("Nero", {"mode": "colora", "h": 220, "s": 6, "l": -62}),
                ("Rosso ramato", {"mode": "colora", "h": 16, "s": 62, "l": -5}),
                ("Grigio", {"mode": "colora", "h": 30, "s": 4, "l": 15}),
                ("Bianco", {"mode": "colora", "h": 40, "s": 5, "l": 60})],
    "occhi": [("Azzurro", {"mode": "colora", "h": 205, "s": 45, "l": 10}),
              ("Blu", {"mode": "colora", "h": 220, "s": 60, "l": -10}),
              ("Verde", {"mode": "colora", "h": 105, "s": 38, "l": -5}),
              ("Nocciola", {"mode": "colora", "h": 35, "s": 45, "l": -10}),
              ("Marrone", {"mode": "colora", "h": 25, "s": 50, "l": -35}),
              ("Grigio", {"mode": "colora", "h": 210, "s": 10, "l": 5})],
    "labbra": [("Rosa", {"mode": "colora", "h": 350, "s": 40, "l": 0, "amount": 70}),
               ("Rosso", {"mode": "colora", "h": 357, "s": 70, "l": -15, "amount": 85}),
               ("Bordeaux", {"mode": "colora", "h": 342, "s": 55, "l": -40, "amount": 85}),
               ("Nude", {"mode": "colora", "h": 18, "s": 30, "l": 5, "amount": 60}),
               ("Prugna", {"mode": "colora", "h": 320, "s": 35, "l": -30, "amount": 80})],
    "unghie": [("Rosso", {"mode": "colora", "h": 357, "s": 75, "l": -10}),
               ("Rosa", {"mode": "colora", "h": 345, "s": 45, "l": 20}),
               ("Nero", {"mode": "colora", "h": 0, "s": 0, "l": -70}),
               ("Bianco", {"mode": "colora", "h": 30, "s": 5, "l": 60}),
               ("Naturale", {"mode": "colora", "h": 15, "s": 25, "l": 15})],
    "trucco": [("Smoky nero", {"mode": "colora", "h": 0, "s": 0, "l": -55, "amount": 60}),
               ("Marrone", {"mode": "colora", "h": 25, "s": 40, "l": -35, "amount": 50}),
               ("Viola", {"mode": "colora", "h": 280, "s": 40, "l": -25, "amount": 50}),
               ("Blu", {"mode": "colora", "h": 215, "s": 45, "l": -20, "amount": 50}),
               ("Oro", {"mode": "colora", "h": 45, "s": 55, "l": 10, "amount": 45})],
    "vestiti": [("Nero", {"mode": "colora", "h": 220, "s": 5, "l": -70, "amount": 100}),
                ("Bianco", {"mode": "colora", "h": 40, "s": 4, "l": 65, "amount": 100}),
                ("Grigio", {"mode": "colora", "h": 220, "s": 5, "l": -10, "amount": 100}),
                ("Rosso", {"mode": "colora", "h": 357, "s": 70, "l": -15, "amount": 100}),
                ("Blu scuro", {"mode": "colora", "h": 222, "s": 55, "l": -45, "amount": 100}),
                ("Jeans", {"mode": "colora", "h": 212, "s": 40, "l": -20, "amount": 100}),
                ("Verde militare", {"mode": "colora", "h": 75, "s": 25, "l": -35, "amount": 100}),
                ("Cammello", {"mode": "colora", "h": 33, "s": 40, "l": 5, "amount": 100}),
                ("Marrone", {"mode": "colora", "h": 25, "s": 40, "l": -40, "amount": 100})],
}


def rgb_to_hls(np, rgb):
    c = rgb.astype(np.float32) / 255.0
    r, g, b = c[..., 0], c[..., 1], c[..., 2]
    mx, mn = c.max(-1), c.min(-1)
    l = (mx + mn) / 2
    d = mx - mn
    s = np.where(d < 1e-6, 0.0, np.where(l < 0.5, d / np.maximum(mx + mn, 1e-6), d / np.maximum(2 - mx - mn, 1e-6)))
    dd = np.maximum(d, 1e-6)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    h = np.where(d < 1e-6, 0.0, h)
    return h % 1.0, l, s


def hls_to_rgb(np, h, l, s):
    q = np.where(l < 0.5, l * (1 + s), l + s - l * s)
    p = 2 * l - q

    def ch(t):
        t = t % 1.0
        return np.where(t < 1 / 6, p + (q - p) * 6 * t, np.where(t < 0.5, q, np.where(t < 2 / 3, p + (q - p) * (2 / 3 - t) * 6, p)))
    out = np.stack([ch(h + 1 / 3), ch(h), ch(h - 1 / 3)], -1)
    return (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)


def adjust_colors(np, rgb, p, mask=None, med=None):
    """rgb uint8 (..., 3) -> uint8. mask (stessa forma senza canali) 0..1 = dove applicare.
    med: luminosita' media gia' calcolata (es. su piu' texture insieme); se manca, quella dentro mask."""
    if not p:
        return rgb
    rgb = rgb[..., :3]
    h, l, s = rgb_to_hls(np, rgb)
    sel = mask > 0.004 if mask is not None else np.ones(h.shape, bool)
    if not sel.any():
        return rgb
    L = float(p.get("l", 0)) / 100.0
    if p.get("mode") == "colora":
        h = np.full_like(h, (float(p.get("h", 0)) % 360) / 360.0)
        s = np.full_like(s, max(0.0, min(1.0, float(p.get("s", 0)) / 100.0)))
        # luminosita': stessa forma (chiaroscuro) ma con la media voluta
        if med is None:
            med = float(np.median(l[sel])) if sel.any() else 0.5
        target = 0.5 + 0.45 * L
        k = target / max(med, 0.02)
        l = np.clip(l * k, 0, 1) if k <= 1 else 1 - np.clip((1 - l) * ((1 - target) / max(1 - med, 0.02)), 0, 1)
    else:
        h = (h + float(p.get("h", 0)) / 360.0) % 1.0
        S = float(p.get("s", 0)) / 100.0
        s = np.clip(s * (1 + S) if S < 0 else s + (1 - s) * S, 0, 1)
        l = np.clip(l * (1 + L) if L < 0 else l + (1 - l) * L, 0, 1)
    out = hls_to_rgb(np, h, l, s).astype(np.float32)
    a = float(p.get("amount", 100)) / 100.0
    w = (mask if mask is not None else np.ones(h.shape, np.float32)) * a
    return np.clip(rgb.astype(np.float32) * (1 - w[..., None]) + out * w[..., None], 0, 255).astype(np.uint8)


# --- maschere nell'atlas (dove stanno iride, labbra, unghie, trucco occhi) -----------------------
BROW_NODES = ("Node23", "Node25")


def brow_vertex_weight(np, o):
    """0..1 per vertice: quanto il vertice e' nella zona delle sopracciglia (ossa Node23/25)."""
    W = get_node_weights(np, o)
    w = W[:, BONE_ORDER.index("Node23")] + W[:, BONE_ORDER.index("Node25")]
    return np.clip((w - 0.12) / 0.3, 0.0, 1.0)


def brows_own_piece(bpy, np, face, factor):
    """Sopracciglia con un loro pezzo nell'atlas, a risoluzione 'factor' volte quella della faccia:
    le facce della zona delle sopracciglia passano su copie dei loro materiali con un'etichetta propria."""
    me = face.data
    bw = brow_vertex_weight(np, face)
    cand = np.array([bw[list(p.vertices)].mean() >= 0.3 for p in me.polygons])
    if not cand.any():
        return 0
    pm = poly_mats(np, me)
    # dentro la zona delle ossa (che arriva a meta' fronte) le sopracciglia sono le facce piu' scure della pelle
    uvl = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uvl)
    uvl = uvl.reshape(-1, 2)
    arrs = {}
    lum = np.full(len(me.polygons), np.nan)
    for f in np.nonzero(cand)[0]:
        p = me.polygons[f]
        m = me.materials[pm[f]] if pm[f] < len(me.materials) else None
        img = material_image(m)[0] if m is not None else None
        if img is None:
            continue
        if img.name not in arrs:
            arrs[img.name] = _img_array(img, 1024)
        A = arrs[img.name]
        if A is None:
            continue
        uv = uvl[list(p.loop_indices)]
        pts = np.vstack([uv, uv.mean(0, keepdims=True)])
        c = _sample(np, A, np.mod(pts[:, 0], 1.0), np.mod(pts[:, 1], 1.0))[:, :3]
        lum[f] = float((c @ np.array([0.299, 0.587, 0.114])).min())
    ok = ~np.isnan(lum)
    sel = np.zeros(len(me.polygons), bool)
    if ok.sum() >= 10:
        med = float(np.median(lum[ok]))
        sel = ok & (lum < med * 0.85)
        # un anello di facce attorno (bordo morbido), sempre dentro la zona delle ossa
        vs = set(v for f in np.nonzero(sel)[0] for v in me.polygons[f].vertices)
        sel |= cand & np.array([any(v in vs for v in p.vertices) for p in me.polygons])
    if sel.sum() < 6:                                   # texture senza sopracciglia scure: tutta la zona
        sel = np.array([bw[list(p.vertices)].mean() >= 0.5 for p in me.polygons])
    if not sel.any():
        return 0
    newidx = {}
    for mi in sorted(set(pm[sel].tolist())):
        m = me.materials[mi]
        if m is None:
            continue
        m2 = m.copy()
        m2["_atlas_tag"] = "brows"
        m2["_zone"] = "Brows"
        me.materials.append(m2)
        newidx[mi] = len(me.materials) - 1
    idx = pm.copy()
    for f in np.nonzero(sel)[0]:
        idx[f] = newidx.get(pm[f], pm[f])
    me.polygons.foreach_set("material_index", idx.tolist())
    IMPORTANCE["Brows"] = IMPORTANCE.get("Face", 14.0) * factor * factor
    return int(sel.sum())


def _blur(np, A, sigma):
    """Sfocatura gaussiana separabile di un'immagine (h, w, c) float."""
    r = max(1, int(round(sigma * 3)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    P = np.pad(A, ((r, r), (r, r), (0, 0)), mode="edge")
    T = sum(k[i] * P[i:i + A.shape[0], :, :] for i in range(2 * r + 1))
    return sum(k[i] * T[:, i:i + A.shape[1], :] for i in range(2 * r + 1))


def enhance_brows(np, rgb, mask, amount):
    """Sopracciglia rinforzate dopo la riduzione: nitidezza, contrasto con la pelle intorno e un po' piu'
    scure dove sono gia' piu' scure della pelle. amount 0..100, solo dentro mask (0..1, riga 0 = alto)."""
    a = max(0.0, min(1.0, amount / 100.0))
    if a <= 0 or mask is None or not (mask > 0.01).any():
        return rgb
    ys, xs = np.nonzero(mask > 0.01)
    y0, y1 = max(0, ys.min() - 12), min(rgb.shape[0], ys.max() + 13)
    x0, x1 = max(0, xs.min() - 12), min(rgb.shape[1], xs.max() + 13)
    X = rgb[y0:y1, x0:x1, :3].astype(np.float32)
    fine = _blur(np, X, 0.8)
    wide = _blur(np, X, 4.0)
    Y = X + (X - fine) * (1.8 * a)                               # nitidezza
    Y = wide + (Y - wide) * (1.0 + 0.9 * a)                      # contrasto con la pelle intorno
    lum = X.mean(2)
    dark = np.clip((wide.mean(2) - lum) / 35.0, 0.0, 1.0)       # piu' scuro della pelle: e' sopracciglio
    Y = Y * (1.0 - 0.3 * a * dark)[..., None]
    m = mask[y0:y1, x0:x1, None]
    out = rgb.copy()
    out[y0:y1, x0:x1, :3] = np.clip(X * (1 - m) + Y * m, 0, 255).astype(np.uint8)
    return out


def raster_mask(np, size, UVc, Wc):
    """Triangoli UV (n,3,2) in 0..1 con pesi agli angoli (n,3) -> maschera size x size, riga 0 = alto."""
    M = np.zeros((size, size), np.float32)
    for (a, b, c), (wa, wb, wc) in zip(UVc * size, Wc):
        if wa <= 0 and wb <= 0 and wc <= 0:
            continue
        X = np.array([a[0], b[0], c[0]])
        Y = np.array([size - a[1], size - b[1], size - c[1]])
        x0, x1 = max(0, int(X.min()) - 1), min(size - 1, int(X.max()) + 1)
        y0, y1 = max(0, int(Y.min()) - 1), min(size - 1, int(Y.max()) + 1)
        if x1 < x0 or y1 < y0:
            continue
        den = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
        if abs(den) < 1e-9:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((Y[1] - Y[2]) * (gx - X[2]) + (X[2] - X[1]) * (gy - Y[2])) / den
        w1 = ((Y[2] - Y[0]) * (gx - X[2]) + (X[0] - X[2]) * (gy - Y[2])) / den
        w2 = 1 - w0 - w1
        ok = (w0 >= -0.15) & (w1 >= -0.15) & (w2 >= -0.15)             # un pixel di margine
        val = np.clip(w0, 0, 1) * wa + np.clip(w1, 0, 1) * wb + np.clip(w2, 0, 1) * wc
        val = val / np.maximum(np.clip(w0, 0, 1) + np.clip(w1, 0, 1) + np.clip(w2, 0, 1), 1e-6)
        sub = M[y0:y1 + 1, x0:x1 + 1]
        sub[ok] = np.maximum(sub[ok], val[ok])
    return M


def makeup_weight(np, P, eyes, lid=None, ext=0.0):
    """Trucco occhi: 0 = palpebra mobile (vertici delle ossa delle palpebre, Node24/26); ext < 0 restringe
    verso la linea delle ciglia, ext > 0 allarga verso il sopracciglio (fino a -1 / +1)."""
    if lid is None:
        return makeup_ring(np, P, eyes) * max(0.0, 1.0 + ext)
    lid = np.clip(np.asarray(lid, float), 0, 1)
    if ext < 0:
        thr = 0.05 + 0.85 * (-ext)
        return np.clip((lid - thr) / 0.15, 0, 1).astype(np.float32)
    base = np.clip((lid - 0.03) / 0.3, 0, 1)
    if ext > 0:
        base = np.maximum(base, ext * makeup_ring(np, P, eyes))
    return base.astype(np.float32)


def makeup_ring(np, P, eyes):
    """Peso del trucco occhi su ogni vertice: palpebra superiore (ombretto) e un filo sotto l'occhio,
    sfumato verso sopracciglio e naso."""
    w = np.zeros(len(P), np.float32)
    for side, (c, r) in eyes.items():
        c = np.asarray(c, float)
        d = P - c
        same = np.sign(P[:, 0]) == np.sign(c[0])
        front = d[:, 2] > -0.3 * r
        ex = d[:, 0] / (1.25 * r)                   # ellisse piu' larga che alta
        ey = d[:, 1] / r
        dist = np.sqrt(ex ** 2 + ey ** 2)
        lid = np.clip((1.6 - dist) / 0.45, 0, 1) * np.clip((dist - 0.6) / 0.12, 0, 1)
        up = np.where(ey >= -0.1, 1.0, np.clip(0.35 + (ey + 0.1) * 0.6, 0, 0.35))      # sotto: solo un filo
        nose = np.clip((np.abs(P[:, 0]) - (abs(c[0]) - 1.35 * r)) / (0.5 * r), 0, 1)
        w = np.maximum(w, lid * up * nose * front * same)
    return w


def region_masks(np, size, V, F, UVc, FZ, eyes):
    """V vertici, F triangoli, UVc UV degli angoli (n,3,2), FZ zona di ogni triangolo (nomi DAZ)."""
    FZ = np.asarray(FZ)
    out = {}
    for key, zones in (("iris", ("Irises",)), ("lips", ("Lips",)), ("nails", ("Fingernails", "Toenails"))):
        sel = np.isin(FZ, zones)
        out[key] = raster_mask(np, size, UVc[sel], np.ones((int(sel.sum()), 3))) if sel.any() else None
    out["_mk"] = (size, V, F, UVc, FZ, eyes)
    return out


def makeup_mask(np, masks, lid, ext=0.0):
    size, V, F, UVc, FZ, eyes = masks["_mk"]
    sel = np.isin(np.asarray(FZ), ("Face",))
    if not sel.any() or not eyes:
        return None
    wv = makeup_weight(np, V, eyes, lid, ext)
    Wc = wv[F[sel]]
    keep = Wc.max(1) > 0
    return raster_mask(np, size, UVc[sel][keep], Wc[keep]) if keep.any() else None


def apply_looks(np, rgb, masks, looks, lid=None):
    """looks: {"iris": p, "lips": p, "nails": p, "makeup": p} -> atlas ricolorato.
    Per il trucco p["ext"] (-100..100) restringe/allarga la zona; lid = pesi delle palpebre per vertice."""
    out = rgb
    for key in ("iris", "lips", "nails", "makeup"):
        p = (looks or {}).get(key)
        if not p:
            continue
        if key == "makeup":
            ck = ("_mkc", float(p.get("ext", 0)))
            if ck not in masks:
                masks[ck] = makeup_mask(np, masks, lid, float(p.get("ext", 0)) / 100.0)
            m = masks[ck]
        else:
            m = masks.get(key)
        if m is not None:
            out = adjust_colors(np, out, p, m)
    return out


def lid_weights(np, objs):
    """Peso delle palpebre superiori (Node24 + Node26) per ogni vertice degli oggetti, in ordine."""
    out = []
    for o in objs:
        W = get_node_weights(np, o)
        out.append(W[:, BONE_ORDER.index("Node24")] + W[:, BONE_ORDER.index("Node26")])
    return np.concatenate(out) if out else None


def eye_centers(np, V, F, FZ):
    """Centro e raggio di ogni occhio (dalla sclera)."""
    FZ = np.asarray(FZ)
    eyes = {}
    sel = np.isin(FZ, ("Sclera",))
    if not sel.any():
        return eyes
    vv = np.unique(F[sel[:len(F)]] if len(sel) == len(F) else F)
    P = V[vv]
    for side in (1, -1):
        q = P[np.sign(P[:, 0]) == side]
        if len(q) >= 8:
            # sfera che passa meglio per i punti (va bene anche con la meta' dietro gia' tolta)
            A = np.c_[2 * q, np.ones(len(q))]
            sol = np.linalg.lstsq(A, (q ** 2).sum(1), rcond=None)[0]
            c = sol[:3]
            r = float(np.sqrt(max(1e-6, sol[3] + c @ c)))
            if not 0.5 < r < 2.5:                   # sfera strana: centro del riquadro
                c = (q.min(0) + q.max(0)) / 2
                r = float(np.median(np.linalg.norm(q - c, axis=1)))
            eyes[side] = (c, r)
    return eyes


def mesh_arrays(np, objs, zones_of=None):
    """Oggetti -> V, F (triangoli), UVc (n,3,2), FZ zona di ogni triangolo."""
    V, F, UVc, FZ = [], [], [], []
    off = 0
    for o in objs:
        me = o.data
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        uv = np.zeros(len(me.loops) * 2)
        me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        zl = zones_of.get(o.name) if zones_of else None
        mz = [zone_name(m.name if m else "") for m in me.materials]
        for p in me.polygons:
            li = list(p.loop_indices)
            vs = list(p.vertices)
            z = zl[p.index] if zl is not None else (mz[p.material_index] if p.material_index < len(mz) else "")
            for j in range(1, len(vs) - 1):
                F.append((vs[0] + off, vs[j] + off, vs[j + 1] + off))
                UVc.append(uv[[li[0], li[j], li[j + 1]]])
                FZ.append(z)
        V.append(co.reshape(-1, 3))
        off += len(me.vertices)
    return np.vstack(V), np.array(F, int).reshape(-1, 3), np.array(UVc, float).reshape(-1, 3, 2), np.array(FZ)


def poly_zones(o):
    """Zona DAZ di ogni poligono (da conservare prima dell'atlas, che unisce i materiali)."""
    mz = [zone_name(m.name if m else "") for m in o.data.materials]
    return [mz[p.material_index] if p.material_index < len(mz) else "" for p in o.data.polygons]


# ------------------------------------------------------------------------------------------------
# Preparazione comune (conversione e analisi): T-pose, pesi sui Node, adattamento allo scheletro OB
# ------------------------------------------------------------------------------------------------
def flatten_feet(bpy, arm, body=None, ankle_deg=0.0, toes_deg=0.0):
    """Scarpe chiuse: rotazioni del piede e di tutti i suoi figli (metatarsi, dita) azzerate; poi, se la posa del
    tacco e' "cotta" nello scheletro a riposo, il piede ruota attorno alla caviglia finche' la pianta e' piatta
    (tallone e avampiede alla stessa altezza)."""
    import numpy as np
    from mathutils import Matrix, Quaternion, Vector
    pb = arm.pose.bones
    done = []
    for root in ("lFoot", "rFoot"):
        if root not in pb:
            continue
        stack = [pb[root]]
        while stack:
            b = stack.pop()
            b.rotation_quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
            b.rotation_euler = (0.0, 0.0, 0.0)
            b.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)
            done.append(b.name)
            stack.extend(b.children)
    bpy.context.view_layer.update()
    log("scarpe chiuse: piede piatto (rotazioni azzerate su %d ossa: %s)" % (len(done), ", ".join(done[:8]) +
                                                                          (" ..." if len(done) > 8 else "")))
    if body is None:
        return
    gi = {g.name: g.index for g in body.vertex_groups}
    nv = len(body.data.vertices)
    W = {}
    for gname in ("lFoot", "rFoot", "lMetatarsals", "rMetatarsals", "lToe", "rToe"):
        W[gname] = np.zeros(nv)
    for side in "lr":                                    # dita: tutte le ossa sotto lToe/rToe
        if side + "Toe" in pb:
            stack = list(pb[side + "Toe"].children)
            while stack:
                b = stack.pop()
                W[b.name] = np.zeros(nv)
                stack.extend(b.children)
    want = {gi[n]: n for n in W if n in gi}
    toes_of = {side: [n for n in W if n == side + "Toe" or (n.startswith(side) and "Toe" in n and n != side + "Toe")]
               for side in "lr"}
    for v in body.data.vertices:
        for g in v.groups:
            n = want.get(g.group)
            if n:
                W[n][v.index] = g.weight
    mw = arm.matrix_world

    def posed():
        dg = bpy.context.evaluated_depsgraph_get()
        eo = body.evaluated_get(dg)
        me = eo.to_mesh()
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        eo.to_mesh_clear()
        M = np.array(body.matrix_world)
        co = co.reshape(-1, 3)
        return co @ M[:3, :3].T + M[:3, 3]
    out = []
    for side, lab in (("l", "SX"), ("r", "DX")):
        foot = side + "Foot"
        if foot not in pb or foot not in gi:
            continue
        heel_w = W[foot]
        fore_w = W[side + "Metatarsals"] + W[side + "Toe"]
        if (heel_w > 0.5).sum() < 10 or (fore_w > 0.5).sum() < 10:
            continue
        total = 0.0
        for _ in range(3):
            P = posed()
            hp, fp = P[heel_w > 0.5], P[fore_w > 0.5]
            heel = hp[np.argsort(hp[:, 2])[:30]].mean(0)            # i 30 punti piu' bassi (Z su in Blender)
            ball = fp[np.argsort(fp[:, 2])[:30]].mean(0)
            d = Vector(tuple(ball - heel))
            flat = Vector((d.x, d.y, 0.0))
            if flat.length < 1e-6:
                break
            ang = math.degrees(d.angle(flat))
            if ang < 1.0 or (abs(total) < 1e-6 and ang < 4.0):
                break
            q = d.rotation_difference(flat)
            h = mw @ pb[foot].head
            R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
            pb[foot].matrix = mw.inverted() @ R @ mw @ pb[foot].matrix
            bpy.context.view_layer.update()
            total += ang if ball[2] < heel[2] else -ang
        if abs(total) > 0.5:
            out.append("%s %.0f gradi" % (lab, total))
        # dita: ruotate al contrario finche' la loro parte bassa e' appoggiata come l'avampiede
        toe = side + "Toe"
        toe_w = sum(W[n] for n in toes_of[side] if n in W)
        meta_w = W[side + "Metatarsals"]
        if toe in pb and (toe_w > 0.5).sum() >= 10 and (meta_w > 0.5).sum() >= 10:
            tt = 0.0
            for _ in range(3):
                P = posed()
                mp, tp_ = P[meta_w > 0.5], P[toe_w > 0.5]
                ball = mp[np.argsort(mp[:, 2])[:30]].mean(0)
                tip = tp_[np.argsort(tp_[:, 2])[:30]].mean(0)
                d = Vector(tuple(tip - ball))
                flat = Vector((d.x, d.y, 0.0))
                if flat.length < 1e-6:
                    break
                ang = math.degrees(d.angle(flat))
                if ang < 1.0:
                    break
                q = d.rotation_difference(flat)
                h = mw @ pb[toe].head
                R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
                pb[toe].matrix = mw.inverted() @ R @ mw @ pb[toe].matrix
                bpy.context.view_layer.update()
                tt += ang if tip[2] > ball[2] else -ang
            if abs(tt) > 0.5:
                out.append("dita %s %.0f gradi" % (lab, tt))
        # ritocchi a mano: caviglia e dita+metatarso (gradi, + = punta in su)
        for bone, deg in ((foot, ankle_deg), (side + "Metatarsals", toes_deg)):
            if abs(deg) < 0.05 or bone not in pb:
                continue
            P = posed()
            hp = P[heel_w > 0.5]
            fp = P[fore_w > 0.5]
            fwd = Vector(tuple(fp.mean(0) - hp.mean(0)))
            fwd.z = 0.0
            if fwd.length < 1e-6:
                continue
            axis = fwd.normalized().cross(Vector((0.0, 0.0, 1.0)))
            q = Quaternion(axis, math.radians(deg))
            h = mw @ pb[bone].head
            R = Matrix.Translation(h) @ q.to_matrix().to_4x4() @ Matrix.Translation(-h)
            pb[bone].matrix = mw.inverted() @ R @ mw @ pb[bone].matrix
            bpy.context.view_layer.update()
    if out:
        log("scarpe chiuse: pianta del piede raddrizzata (%s)" % ", ".join(out))
    if abs(ankle_deg) > 0.05 or abs(toes_deg) > 0.05:
        log("scarpe chiuse: ritocco a mano caviglia %+.0f, dita e metatarso %+.0f gradi" % (ankle_deg, toes_deg))


def prepare(bpy, np, arm, body, garments, brow_side=0.3, joint_smooth=1.0, shoulder_lift=0.0, arms_on_bones=False,
            rigid=(), face=None, flat_feet=False, feet_adj=(0.0, 0.0)):
    if flat_feet:
        flatten_feet(bpy, arm, body, float(feet_adj[0]), float(feet_adj[1]))
    tpose(bpy, arm, shoulder_lift)
    face_expression(bpy, arm, face)              # (solo per chi la chiede qui; gli outfit la applicano dopo)
    fxv = face_expression_fields(np, body, arm)
    keep = [body] + list(garments)
    apply_armature(bpy, keep)
    mw = arm.matrix_world
    J = {}
    for n, b in JOINTS.items():
        if b in arm.pose.bones:
            J[n] = bl_to_ob(np, np.array([(mw @ arm.pose.bones[b].head)[:]]))[0]
    miss = [JOINTS[n] for n in ("Node4", "Node5", "Node6", "Node7", "Node8", "Node9", "Node13", "Node14",
                                "Node15", "Node17", "Node18", "Node19", "Node10") if n not in J]
    if miss:
        raise RuntimeError("ossa Genesis 8 mancanti: %s (e' un Genesis 8?)" % ", ".join(miss))
    neck_y = J["Node20"][1] if "Node20" in J else J["Node21"][1] - 5.0
    table, unknown = bone_table(arm, brow_side, neck_y)
    if unknown:
        log("ossa non in tabella (seguono il genitore): %s" % ", ".join(unknown[:12]) +
            (" ... (+%d)" % (len(unknown) - 12) if len(unknown) > 12 else ""))
    data = {}
    for o in keep:
        W, empty = node_weights(np, o, table)
        data[o.name] = [bl_to_ob(np, world_coords(np, o)), W, empty]
    PB, WB, EB = data[body.name]
    if EB.any():
        WB = fill_empty_weights(np, PB, WB, EB, PB[~EB], WB[~EB])
        data[body.name][1] = WB
    for o in garments:
        P, W, E = data[o.name]
        if E.any():
            data[o.name][1] = fill_empty_weights(np, P, W, E, PB, WB)
            log("%s: %d vertici senza pesi -> presi dal corpo" % (clean_name(o.name), int(E.sum())))
    fit, info, JJ = fit_transforms(np, J, float(PB[:, 1].min()), arms_on_bones)
    log("adattamento allo scheletro Outbreak: " + info)
    rigid_names = {o.name for o in rigid}
    PB2 = fit(PB, WB) if rigid_names else None
    for o in keep:
        P, W, _ = data[o.name]
        if o.name in rigid_names:
            # accessorio rigido: ogni pezzo staccato (es. i due orecchini) e' un blocco unico che segue il
            # suo osso dominante, con peso 100% su quell'osso
            comp = mesh_components(np, o)
            P2 = np.zeros_like(P)
            W1 = np.zeros_like(W)
            used = []
            moves = []
            for ci in range(int(comp.max()) + 1 if len(comp) else 0):
                sel = comp == ci
                k = int(np.argmax(W[sel].sum(0)))
                if BONE_ORDER[k] in FACE_NODES:           # occhiali, maschere...: con la testa, non con
                    k = BONE_ORDER.index("Node21")         # palpebre, sopracciglia o mascella
                Q, nb = follow_skin(np, P[sel], PB, PB2)
                if Q is None:
                    Q = fit.rigid(P[sel], BONE_ORDER[k])
                P2[sel] = Q
                W1[sel, k] = 1.0
                used.append(BONE_ORDER[k])
                moves.append(float(np.linalg.norm(Q.mean(0) - P[sel].mean(0))))
            set_mesh_coords(np, o, P2)
            set_node_groups(np, o, W1)
            for m in list(o.modifiers):
                o.modifiers.remove(m)
            log("%s: accessorio rigido, %d pezzi su %s, segue la pelle vicina (spostato di %s cm)" % (
                clean_name(o.name), len(used), ", ".join(sorted(set(used))),
                "/".join("%.1f" % m for m in moves[:6])))
            continue
        P2 = fit(P, W)
        if o is body:                                  # scala della testa: per gli spostamenti dell'espressione
            sel = sum(fxv.values()) > 0.05
            if sel.sum() > 10:
                FX_SCALE[0] = float(np.mean(P2[sel].std(0) / np.maximum(P[sel].std(0), 1e-6)))
        set_mesh_coords(np, o, P2)
        s = W.sum(1, keepdims=True)
        s[s <= 0] = 1.0
        Wf = smooth_joints(np, P2, W / s, joint_smooth)
        if arms_on_bones:
            Wf = wrist_like_p06(np, P2, Wf)
        if o is body and SHOULDER_MODE[0] == "liscia":
            Wf = smooth_shoulders(np, o, P2, Wf, SHOULDER_MODE[1])
        elif o is body and SHOULDER_MODE[0] == "p06":
            Wf = smooth_shoulders(np, o, P2, shoulders_from_p06(np, P2, Wf), 0.4)
        set_node_groups(np, o, Wf)
        for m in list(o.modifiers):
            o.modifiers.remove(m)
    bpy.data.objects.remove(arm, do_unlink=True)
    if joint_smooth > 0:
        log("pesi sfumati su gomiti, ginocchia, spalle e polsi (fascia x%.1f)" % joint_smooth)


INNER_ZONES = ("Sclera", "Irises", "Pupils", "Mouth", "EyeSocket", "Teeth", "EyeMoisture", "Cornea",
               "Fingernails", "Toenails")
HEAD_NODES = ("Node21", "Node22", "Node23", "Node24", "Node25", "Node26", "Node27")


def body_arrays(np, o):
    """Corpo adattato -> dict V (cm OB), F triangoli (solo pelle esterna), N normali dei vertici,
    DOM Node dominante di ogni vertice (indice in BONE_ORDER)."""
    me = o.data
    V = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", V)
    V = V.reshape(-1, 3)
    zones = [zone_name(m.name if m else "") for m in me.materials]
    F = []
    for p in me.polygons:
        if zones and p.material_index < len(zones) and zones[p.material_index] in INNER_ZONES:
            continue
        vs = list(p.vertices)
        for j in range(1, len(vs) - 1):
            F.append((vs[0], vs[j], vs[j + 1]))
    F = np.array(F, int).reshape(-1, 3)
    W = get_node_weights(np, o)
    return {"V": V, "F": F, "N": vert_normals(np, V, F), "DOM": W.argmax(1)}


def vert_normals(np, V, F):
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N = np.zeros_like(V)
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)


# ------------------------------------------------------------------------------------------------
# Capelli: libreria e adattamento automatico alla testa
# ------------------------------------------------------------------------------------------------
def fill_transparent(np, rgba):
    """Pixel trasparenti (in gioco sarebbero pieni): prendono il colore dei pixel pieni vicini."""
    rgb = rgba[..., :3].astype(np.float32)
    if rgba.shape[2] < 4:
        return rgb.astype(np.uint8)
    solid = rgba[..., 3] >= 128
    if solid.all() or not solid.any():
        return rgb.astype(np.uint8)
    for _ in range(256):
        if solid.all():
            break
        acc = np.zeros_like(rgb)
        cnt = np.zeros(solid.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            s2 = np.roll(np.roll(solid, dy, 0), dx, 1)
            acc += np.roll(np.roll(rgb, dy, 0), dx, 1) * s2[..., None]
            cnt += s2
        new = ~solid & (cnt > 0)
        rgb[new] = acc[new] / cnt[new][:, None]
        solid = solid | new
    return np.clip(rgb, 0, 255).astype(np.uint8)


def shrink_tex(np, a, maxdim=1024):
    h, w = a.shape[:2]
    k = int(math.ceil(max(h, w) / float(maxdim)))
    if k <= 1:
        return a
    h2, w2 = h // k, w // k
    return a[:h2 * k, :w2 * k].reshape(h2, k, w2, k, -1).mean(axis=(1, 3)).astype(a.dtype)


def image_rgba(np, img, maxdim=1024):
    """Immagine Blender -> RGBA uint8, riga 0 = alto."""
    a = _img_array(img, maxdim)
    if a is None:
        return np.full((4, 4, 4), 200, np.uint8)
    return (np.clip(a[::-1], 0, 1) * 255 + 0.5).astype(np.uint8)


# --- lettura NBD (per prendere capelli e testa da un personaggio gia' finito) --------------------
def _sld(src):
    out = bytearray()
    n = len(src) // 2
    w = struct.unpack_from("<%dH" % n, src)
    pos = bleft = flag = 0
    while pos < n:
        if bleft == 0:
            flag = w[pos]
            pos += 1
            bleft = 16
            if pos >= n:
                break
        if flag & 0x8000:
            mode = w[pos]
            pos += 1
            cnt = mode >> 11
            if cnt == 0:
                cnt = w[pos] if pos < n else 0
                pos += 1
                if cnt == 0:
                    break
            off = mode & 0x7FF
            if off == 0:
                out += b"\x00\x00" * cnt
            else:
                p = len(out) - off * 2
                for _ in range(cnt):
                    out += out[p:p + 2]
                    p += 2
        else:
            out += struct.pack("<H", w[pos])
            pos += 1
        flag = (flag << 1) & 0xFFFF
        bleft -= 1
    return bytes(out)


def _tim2_rgba(np, d):
    if d[:4] != b"TIM2":
        return None
    p = 128 if d[5] == 1 else 16
    tot, clutsz, imgsz, hdrsz, clutcols, pfmt, nmip, cltt, imgt, w, h = struct.unpack_from("<IIIHHBBBBHH", d, p)
    if imgt == 5 and clutcols == 256:
        idx = np.frombuffer(d, np.uint8, w * h, p + hdrsz).reshape(h, w)
        pal = np.frombuffer(d, np.uint8, 1024, p + hdrsz + imgsz).reshape(256, 4).copy()
        if not (cltt & 0x80):
            q = pal.copy()
            for b in range(0, 256, 32):
                q[b + 8:b + 16], q[b + 16:b + 24] = pal[b + 16:b + 24], pal[b + 8:b + 16]
            pal = q
        out = pal[idx].copy()
    elif imgt == 4 and clutcols == 16:
        raw = np.frombuffer(d, np.uint8, w * h // 2, p + hdrsz)
        idx = np.empty(w * h, np.uint8)
        idx[0::2], idx[1::2] = raw & 15, raw >> 4
        pal = np.frombuffer(d, np.uint8, 64, p + hdrsz + imgsz).reshape(16, 4)
        out = pal[idx.reshape(h, w)].copy()
    else:
        return None
    a = out[..., 3].astype(np.int32)
    out[..., 3] = np.clip(a * 2, 0, 255) if a.max() <= 128 else a      # alpha PS2 0..128
    return out


def read_nbd_meshes(np, path):
    """-> (lista mesh {V, N, UV, T triangoli, J pesi dominanti (id nodo)}, lista texture RGBA)."""
    d = open(path, "rb").read()
    entries, o, first = [], 0, None
    while o + 16 <= len(d) and (first is None or o < first):
        tag, off, size, cnt = struct.unpack_from("<IIII", d, o)
        if tag and (first is None or off < first):
            first = off
        entries.append((tag, off, size, cnt))
        o += 16
    texs, meshes, mats, texref = [], [], [], []
    for tag, off, size, cnt in entries:
        name = bytes((tag >> (8 * i)) & 0xFF for i in range(3))
        if name == b"TEX":
            p, end = off, off + size
            while p + 4 <= end and (cnt == 0 or len(texs) < cnt):
                rs = struct.unpack_from("<I", d, p)[0]
                if rs == 0 or p + 4 + rs > end:
                    break
                texs.append(_tim2_rgba(np, _sld(d[p + 4:p + 4 + rs])))
                p += 4 + rs
        elif name == b"AMO" and not meshes:
            t, c, s = struct.unpack_from("<III", d, off)
            p, end = off + 12, off + s
            while p + 12 <= end:
                t, c, s = struct.unpack_from("<III", d, p)
                pl = p + 12
                if t == 0x2:
                    q = pl
                    for _ in range(c):
                        mt, mc, ms = struct.unpack_from("<III", d, q)
                        meshes.append(_nbd_mesh(np, d, q + 12, q + ms))
                        q += ms
                elif t == 0x9:
                    q = pl
                    for _ in range(c):
                        mt, mc, ms = struct.unpack_from("<III", d, q)
                        ntex = struct.unpack_from("<I", d, q + 64)[0]
                        mats.append(list(struct.unpack_from("<%dI" % ntex, d, q + 12 + 256)))
                        q += ms
                elif t == 0xA:
                    q = pl
                    for _ in range(c):
                        mt, mc, ms = struct.unpack_from("<III", d, q)
                        texref.append(struct.unpack_from("<I", d, q + 12)[0])
                        q += ms
                p += s
    for m in meshes:                                 # materiale -> texture
        m["tex"] = []
        for g in m["matrefs"]:
            tr = mats[g][0] if g < len(mats) and mats[g] else 0
            m["tex"].append(texref[tr] if tr < len(texref) else tr)
    return meshes, texs


def _nbd_mesh(np, d, p, end):
    m = {"strips": [], "stripmat": [], "matrefs": [0]}
    while p + 12 <= end:
        t, c, s = struct.unpack_from("<III", d, p)
        if s < 12 or p + s > end:
            break
        pl = p + 12
        if t == 0x5:
            q = pl
            for _ in range(c):
                lt, lc, ls = struct.unpack_from("<III", d, q)
                r = q + 12
                for _ in range(lc):
                    n = struct.unpack_from("<I", d, r)[0] & 0x7FFFFFFF
                    m["strips"].append(list(struct.unpack_from("<%dI" % n, d, r + 4)))
                    r += 4 + 4 * n
                q += ls
        elif t == 0x50000:
            m["matrefs"] = list(struct.unpack_from("<%dI" % c, d, pl))
        elif t == 0x60000:
            m["stripmat"] = list(struct.unpack_from("<%dI" % c, d, pl))
        elif t == 0x70000:
            m["V"] = np.frombuffer(d, "<f4", c * 3, pl).reshape(c, 3).astype(float)
        elif t == 0x80000:
            m["N"] = np.frombuffer(d, "<f4", c * 3, pl).reshape(c, 3).astype(float)
        elif t == 0xA0000:
            m["UV"] = np.frombuffer(d, "<f4", c * 2, pl).reshape(c, 2).astype(float)
        elif t == 0xC0000:
            ws, q = [], pl
            for _ in range(c):
                n = struct.unpack_from("<I", d, q)[0]
                q += 4
                ws.append([struct.unpack_from("<If", d, q + 8 * j) for j in range(n)])
                q += 8 * n
            m["W"] = ws
        elif t == 0x100000:
            m["JR"] = list(struct.unpack_from("<%dI" % c, d, pl))
        p += s
    tris, tm = [], []
    for si, s_ in enumerate(m["strips"]):
        ml = m["stripmat"][si] if si < len(m["stripmat"]) else 0
        for k in range(len(s_) - 2):
            a, b, c = s_[k], s_[k + 1], s_[k + 2]
            if a != b and b != c and a != c:
                tris.append((a, b, c) if k % 2 == 0 else (b, a, c))
                tm.append(ml)
    m["T"] = np.array(tris, int).reshape(-1, 3)
    m["TM"] = np.array(tm, int)
    jr = m.get("JR") or [21]
    m["J"] = np.array([jr[max(w, key=lambda x: x[1])[0]] if w else 21 for w in m.get("W", [])], int) \
        if m.get("W") else np.full(len(m.get("V", [])), 21)
    return m


def hair_from_nbd(np, path, mesh_index=-1):
    meshes, texs = read_nbd_meshes(np, path)
    if not meshes:
        raise RuntimeError("nell'NBD non trovo mesh")
    if mesh_index < 0:
        # capelli: la mesh che arriva piu' in alto tra quelle legate soprattutto alla testa (Node21)
        cand = []
        for i, m in enumerate(meshes):
            if len(m.get("V", [])) < 30:
                continue
            share = float(np.mean(m["J"] == 21))
            if share >= 0.5:
                cand.append((m["V"][:, 1].max(), len(m["V"]), i))
        if not cand:
            raise RuntimeError("non riconosco la mesh dei capelli: indicala a mano (numero della mesh)")
        mesh_index = max(cand)[2]
    hm = meshes[mesh_index]
    log("capelli presi dalla Mesh%d (%d vertici, %d triangoli)" % (mesh_index, len(hm["V"]), len(hm["T"])))
    UVc = hm["UV"][hm["T"]].copy()
    UVc[..., 1] = 1.0 - UVc[..., 1]
    tex_ids = sorted(set(hm["tex"][k] if k < len(hm["tex"]) else 0 for k in set(hm["TM"].tolist())))
    TEX = []
    FT = np.zeros(len(hm["T"]), int)
    for j, tid in enumerate(tex_ids):
        t = texs[tid] if tid < len(texs) and texs[tid] is not None else np.full((8, 8, 4), 128, np.uint8)
        TEX.append(t)
        for k in range(len(hm["tex"])):
            if hm["tex"][k] == tid:
                FT[hm["TM"] == k] = j
    # testa su cui erano montati: vertici delle altre mesh legati alla testa
    SV, SN, SJ = [], [], []
    for i, m in enumerate(meshes):
        if i == mesh_index or len(m.get("V", [])) < 30:
            continue
        sel = np.isin(m["J"], [21, 22, 23, 24, 25, 26, 27])
        if sel.any():
            SV.append(m["V"][sel])
            SN.append(m.get("N", np.zeros_like(m["V"]))[sel])
            SJ.append(m["J"][sel])
    out = {"V": hm["V"].copy(), "F": hm["T"], "UV": UVc, "FT": FT, "TEX": TEX}
    if SV:
        out["SV"], out["SN"], out["SJ"] = np.vstack(SV), np.vstack(SN), np.concatenate(SJ)
    return out


def hair_from_file(bpy, np, path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".obj":
        try:
            bpy.ops.wm.obj_import(filepath=path)
        except AttributeError:
            bpy.ops.import_scene.obj(filepath=path)
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise RuntimeError("formato non supportato (%s): usa .nbd, .fbx o .obj" % ext)
    meshes = [o for o in bpy.data.objects if o.type == 'MESH']
    if not meshes:
        raise RuntimeError("nel file non ci sono mesh")
    apply_armature(bpy, meshes)
    V, F, UV, FT, TEX, keys = [], [], [], [], [], {}
    off = 0
    for o in meshes:
        me = o.data
        P = world_coords(np, o)
        uv = np.zeros(len(me.loops) * 2)
        if me.uv_layers:
            me.uv_layers.active.data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        tix = []
        for m in me.materials:
            img, col = material_image(m)
            k = img.name if img is not None else ("col", tuple(round(c, 3) for c in col))
            if k not in keys:
                keys[k] = len(TEX)
                if img is not None:
                    TEX.append(image_rgba(np, img))
                else:
                    TEX.append(np.full((8, 8, 4), [int(c * 255) for c in col] + [255], np.uint8))
            tix.append(keys[k])
        if not tix:
            keys.setdefault("vuoto", len(TEX))
            if len(TEX) == keys["vuoto"]:
                TEX.append(np.full((8, 8, 4), 128, np.uint8))
            tix = [keys["vuoto"]]
        for p in me.polygons:
            li = list(p.loop_indices)
            vs = list(p.vertices)
            for j in range(1, len(vs) - 1):
                F.append((vs[0] + off, vs[j] + off, vs[j + 1] + off))
                UV.append(uv[[li[0], li[j], li[j + 1]]])
                FT.append(tix[min(p.material_index, len(tix) - 1)])
        V.append(P)
        off += len(P)
        log("  %s: %d triangoli" % (o.name, sum(len(p.vertices) - 2 for p in me.polygons)))
    V = np.vstack(V)
    k = 100.0 if (V.max(0) - V.min(0)).max() < 5.0 else 1.0
    V = np.c_[V[:, 0], V[:, 2], -V[:, 1]] * k
    return {"V": V, "F": np.array(F, int), "UV": np.array(UV, float), "FT": np.array(FT, int), "TEX": TEX}


def save_hair(np, h, path):
    arrs = {"V": h["V"], "F": h["F"], "UV": h["UV"], "FT": h["FT"], "NT": np.array([len(h["TEX"])])}
    for i, t in enumerate(h["TEX"]):
        arrs["TEX%d" % i] = fill_transparent(np, shrink_tex(np, t, 1024))
    for k in ("SV", "SN", "SJ"):
        if k in h:
            arrs[k] = h[k]
    np.savez_compressed(path, **arrs)


def load_hair(np, path):
    d = np.load(path)
    h = {k: d[k] for k in ("V", "F", "UV", "FT")}
    h["TEX"] = [d["TEX%d" % i] for i in range(int(d["NT"][0]))]
    for k in ("SV", "SN", "SJ"):
        if k in d.files:
            h[k] = d[k]
    return h


def reduce_hair(bpy, np, h, target):
    """Capelli della libreria (array) ridotti a target triangoli con il Decimate di Blender (UV e texture restano)."""
    o = hair_object(bpy, np, h, np.asarray(h["V"], float), "_hlib")
    if len(o.data.polygons) != len(h["F"]):
        warn("capelli: facce doppie o degeneri, riduzione saltata")
        _remove_obj(bpy, o)
        return h
    decimate_object(bpy, o, target)
    V, F, UVc, _ = mesh_arrays(np, [o])
    FT = np.array([p.material_index for p in o.data.polygons for _ in range(len(p.vertices) - 2)], int)
    out = dict(h, V=V, F=F, UV=UVc, FT=FT)
    _remove_obj(bpy, o)
    return out


def _remove_obj(bpy, o):
    me, mats = o.data, list(o.data.materials)
    bpy.data.objects.remove(o, do_unlink=True)
    if me.users == 0:
        bpy.data.meshes.remove(me)
    for m in mats:
        if m is not None and m.users == 0:
            for n in (m.node_tree.nodes if m.node_tree else []):
                if n.type == 'TEX_IMAGE' and n.image is not None and n.image.users <= 1:
                    bpy.data.images.remove(n.image)
            bpy.data.materials.remove(m)


_LIBTRIS = {}


def lib_tris(path):
    """Triangoli di un capello della libreria (.npz) letti dall'intestazione, senza caricare i dati."""
    import zipfile
    try:
        k = (path, os.path.getmtime(path))
    except OSError:
        return 0
    if k not in _LIBTRIS:
        n = 0
        try:
            with zipfile.ZipFile(path) as z:
                head = z.open("F.npy").read(256).decode("latin1")
            m = re.search(r"'shape':\s*\((\d+)", head)
            n = int(m.group(1)) if m else 0
        except Exception:
            n = 0
        _LIBTRIS[k] = n
    return _LIBTRIS[k]


def hairlib_add(src, name, libdir, mesh_index=-1):
    import bpy
    import numpy as np
    os.makedirs(libdir, exist_ok=True)
    log("aggiungo alla libreria: %s" % os.path.basename(src))
    if src.lower().endswith(".nbd"):
        h = hair_from_nbd(np, src, mesh_index)
    else:
        h = hair_from_file(bpy, np, src)
    path = os.path.join(libdir, safe_name(name) + ".npz")
    if len(h["F"]) > HAIR_LIB_MAX:
        n0 = len(h["F"])
        h = reduce_hair(bpy, np, h, HAIR_LIB_MAX)
        log("  ridotti per la libreria: %d -> %d triangoli (massimo %d)" % (n0, len(h["F"]), HAIR_LIB_MAX))
    save_hair(np, h, path)
    h = load_hair(np, path)
    V = h["V"] - [0.5 * (h["V"][:, 0].min() + h["V"][:, 0].max()), 0, 0]
    texs = [t[..., :3] for t in h["TEX"]]
    imgs = [render_tex(np, V, h["F"], h["UV"], h["FT"], texs, y, W=150, H=170) for y in (0, 90)]
    write_png(os.path.splitext(path)[0] + ".png", np.concatenate(imgs, axis=1))
    log("salvato %s: %d triangoli%s" % (os.path.basename(path), len(h["F"]),
                                      ", con la testa di origine" if "SV" in h else " (senza testa di origine)"))


def recolor(np, rgb, hexcol):
    """Tinta: stesso chiaroscuro della texture, colore scelto (#rrggbb)."""
    c = np.array([int(hexcol[i:i + 2], 16) for i in (1, 3, 5)], np.float32)
    lum = rgb[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    m = max(1.0, float(np.median(lum)))
    k = 0.3 + 0.7 * (lum / m)
    return np.clip(c[None, None, :] * k[..., None], 0, 255).astype(np.uint8)


def prepare_hair_textures(np, h, tint="", tex_override=None):
    """La texture piu' usata dai capelli puo' essere sostituita e/o tinta."""
    if not h["TEX"]:
        return h
    main = int(np.bincount(h["FT"], minlength=len(h["TEX"])).argmax())
    if tex_override is not None:
        h["TEX"][main] = tex_override
    if tint:
        h["TEX"][main] = recolor(np, h["TEX"][main], tint)
    return h


def fit_hair(np, h, T, gap=0.4):
    """Adatta i capelli h (V in cm OB) alla testa T (body_arrays). Ritorna V nuovo e una descrizione.
    1) scala e posizione: con la testa di origine la allineo alla nuova; senza, allineo l'interno dei
       capelli a nuca e lati della testa nuova (ICP con scala per asse);
    2) con la testa di origine i capelli tengono la stessa distanza dalla testa, punto per punto;
    3) niente dentro testa e spalle: spinti fuori di 'gap' cm, spostamento sfumato sui vicini."""
    from mathutils.kdtree import KDTree
    from mathutils.bvhtree import BVHTree
    TV, TF, TN, DOM = T["V"], T["F"], T["N"], T["DOM"]
    hid = [BONE_ORDER.index(n) for n in HEAD_NODES]
    head = np.isin(DOM, hid) & np.isin(np.arange(len(TV)), np.unique(TF))
    bro = np.isin(DOM, [BONE_ORDER.index("Node23"), BONE_ORDER.index("Node25")])
    brow = float(TV[bro, 1].mean()) if bro.any() else SKEL["Node23"][1]
    TS = head & ((TV[:, 1] > brow + 1.5) | ((TV[:, 1] > brow - 6.0) & (TN[:, 2] < -0.2)))
    A, AN = TV[TS], TN[TS]
    if len(A) < 20:
        raise RuntimeError("testa del personaggio non trovata per adattare i capelli")
    HV = np.asarray(h["V"], float)

    def kd_of(P):
        kd = KDTree(len(P))
        for i, p in enumerate(P):
            kd.insert(p, i)
        kd.balance()
        return kd

    def solve(Xs, Ys):
        s, t = np.ones(3), np.zeros(3)
        for k in range(3):
            x, y = Xs[:, k], Ys[:, k]
            vx = float(np.var(x))
            s[k] = float(np.mean((x - x.mean()) * (y - y.mean()))) / vx if vx > 1e-9 else 1.0
        sm = float(np.mean(s))
        s = np.clip(s, sm * 0.88, sm * 1.12)
        for k in range(3):
            t[k] = float(np.mean(Ys[:, k] - s[k] * Xs[:, k]))
        return s, t

    src = "SV" in h and len(h["SV"]) > 50
    if src:
        S, SN, SJ = np.asarray(h["SV"], float), np.asarray(h["SN"], float), np.asarray(h["SJ"])
        sb = np.isin(SJ, [23, 25])
        sbrow = float(S[sb, 1].mean()) if sb.any() else S[:, 1].max() - 12.0
        SS = S[(S[:, 1] > sbrow + 1.5) | ((S[:, 1] > sbrow - 6.0) & (SN[:, 2] < -0.2))]
        sc = (A[:, 0].max() - A[:, 0].min()) / max(1e-6, SS[:, 0].max() - SS[:, 0].min())
        s = np.full(3, sc)
        t = np.array([0.0, A[:, 1].max() - sc * SS[:, 1].max(),
                      A[:, 2].mean() - sc * SS[:, 2].mean()])
        kdA = kd_of(A)
        for _ in range(30):
            P = SS * s + t
            pairs = [kdA.find(p) for p in P]
            d = np.array([q[2] for q in pairs])
            ok = d < max(1.0, 3.0 * float(np.median(d)))
            s, t = solve(SS[ok], A[[q[1] for q in pairs]][ok])
        how = "con la testa di origine"
    else:
        top = HV[:, 1].max()
        xw = HV[:, 0].max() - HV[:, 0].min()
        band = HV[:, 1] > top - 0.6 * xw
        cw = HV[band, 0].max() - HV[band, 0].min()
        sc = (A[:, 0].max() - A[:, 0].min() + 2.0) / max(1e-6, cw)
        s = np.full(3, sc)
        up = A[A[:, 1] > brow + 1.5]
        t = np.array([-sc * 0.5 * (HV[band, 0].max() + HV[band, 0].min()),
                      A[:, 1].max() + 1.0 - sc * top,
                      up[:, 2].mean() - sc * HV[band, 2].mean()])
        tgt = A + AN * gap
        for _ in range(40):
            P = HV * s + t
            kd = kd_of(P)
            pairs = [kd.find(a) for a in A]
            d = np.array([q[2] for q in pairs])
            ok = d < max(1.0, 3.0 * float(np.median(d)))
            idx = np.array([q[1] for q in pairs])[ok]
            s, t = solve(HV[idx], tgt[ok])
        how = "dalla forma dei capelli (nessuna testa di origine)"
    H = HV * s + t
    keepf = TF
    bvh = BVHTree.FromPolygons([tuple(v) for v in TV], [tuple(f) for f in keepf])
    delta = np.zeros_like(H)
    if src:
        Sx = S * s + t
        kdS = kd_of(Sx)
        SNn = SN / np.maximum(np.linalg.norm(SN, axis=1, keepdims=True), 1e-9)
        for i, p in enumerate(H):
            q, j, ds = kdS.find(p)
            if ds > 5.0:
                continue
            sds = float(np.dot(p - np.array(q[:]), SNn[j]))
            loc, nrm, fi, dt = bvh.find_nearest(p, 8.0)
            if loc is None:
                continue
            sdt = float(np.dot(p - np.array(loc[:]), np.array(nrm[:])))
            w = max(0.0, 1.0 - abs(sds) / 5.0)
            delta[i] = (sds - sdt) * np.array(nrm[:]) * w
    # vicini sul mesh dei capelli (per sfumare gli spostamenti)
    F = np.asarray(h["F"])
    E = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    deg = np.bincount(E.ravel(), minlength=len(H)).astype(float)

    def smooth(D, it=8):
        for _ in range(it):
            acc = np.zeros_like(D)
            np.add.at(acc, E[:, 0], D[E[:, 1]])
            np.add.at(acc, E[:, 1], D[E[:, 0]])
            D = 0.5 * D + 0.5 * acc / np.maximum(deg, 1)[:, None]
        return D

    def collide(P):
        out = np.zeros_like(P)
        for i, p in enumerate(P):
            loc, nrm, fi, d = bvh.find_nearest(p, 6.0)
            if loc is None:
                continue
            n = np.array(nrm[:])
            sd = float(np.dot(p - np.array(loc[:]), n))
            if sd < gap:
                out[i] = (gap - sd) * n
        return out
    delta = smooth(delta + collide(H + delta))
    H = H + delta
    for _ in range(2):                                  # quello che resta dentro: spinto fuori senza sfumare
        c = collide(H)
        if not c.any():
            break
        H = H + c
    inside = int(np.count_nonzero(np.linalg.norm(collide(H), axis=1) > 0.05))
    info = "adattati %s: scala %.2f (%.2f %.2f %.2f), altezza %.0f..%.0f cm%s" % (
        how, float(np.mean(s)), s[0], s[1], s[2], H[:, 1].min(), H[:, 1].max(),
        ", %d vertici ancora vicini alla pelle" % inside if inside else "")
    return H, info


def hair_object(bpy, np, h, V, name="hair"):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(p) for p in V], [], [tuple(f) for f in h["F"]])
    me.update()
    uvl = me.uv_layers.new(name="UVMap")
    if len(me.polygons) == len(h["F"]):
        uvl.data.foreach_set("uv", np.asarray(h["UV"], float).reshape(-1).tolist())
        me.polygons.foreach_set("material_index", np.asarray(h["FT"]).tolist())
    for i, t in enumerate(h["TEX"]):
        hh, ww = t.shape[:2]
        img = bpy.data.images.new("hair_tex%d" % i, ww, hh)
        a = np.concatenate([t[::-1, :, :3].astype(np.float32) / 255.0, np.ones((hh, ww, 1), np.float32)], axis=2)
        img.pixels.foreach_set(a.ravel())
        me.materials.append(make_material(bpy, "hair", img))
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    o = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(o)
    from mathutils import Matrix
    o.matrix_world = Matrix.Rotation(math.pi / 2.0, 4, 'X')
    return o


def hair_weights(np, o, follow_torso=True):
    """Testa (Node21); con follow_torso i capelli lunghi scendono per gradi: dalle orecchie alla nuca passano
    al collo (Node20), sotto la nuca al busto (Node11). Cosi' quando la testa o il collo si piegano indietro
    le ciocche sulla schiena non ci entrano dentro (seguono il collo e il busto, non la testa)."""
    V = np.array([v.co[:] for v in o.data.vertices])
    W = np.zeros((len(V), len(BONE_ORDER)), np.float32)
    i21, i20, i11 = BONE_ORDER.index("Node21"), BONE_ORDER.index("Node20"), BONE_ORDER.index("Node11")
    W[:, i21] = 1.0
    if follow_torso:
        y = V[:, 1]
        ear = SKEL["Node21"][1] + 3.0                 # circa all'altezza delle orecchie
        nape = SKEL["Node20"][1] + 1.0                # nuca
        low = SKEL["Node20"][1] - 9.0                 # sotto: tutto sul busto
        back = np.clip((SKEL["Node21"][2] + 2.0 - V[:, 2]) / 4.0, 0.0, 1.0)   # dietro la testa: segue il collo prima
        a = np.clip((ear - y) / max(1e-6, ear - nape), 0.0, 1.0)
        a = a * a * (3 - 2 * a)
        b = np.clip((nape - y) / max(1e-6, nape - low), 0.0, 1.0)
        b = b * b * (3 - 2 * b)
        w20 = a * (0.35 + 0.45 * back) * (1.0 - b)
        w11 = b * 0.9
        w21 = np.clip(1.0 - w20 - w11, 0.0, 1.0)
        W[:, i21], W[:, i20], W[:, i11] = w21, w20, w11
    set_node_groups(np, o, limit4(np, W))


def hair_off_back(np, V, T, gap=1.0):
    """Ciocche sotto la nuca staccate dalla schiena/spalle di almeno 'gap' cm (spostamento sfumato)."""
    from mathutils.bvhtree import BVHTree
    V = np.asarray(V, float).copy()
    low = V[:, 1] < SKEL["Node20"][1] + 1.0
    if not low.any():
        return V, 0
    bvh = BVHTree.FromPolygons([tuple(v) for v in T["V"]], [tuple(f) for f in T["F"]])
    moved = 0
    for i in np.nonzero(low)[0]:
        loc, nrm, fi, d = bvh.find_nearest(V[i], gap + 1.0)
        if loc is None:
            continue
        n = np.array(nrm[:])
        sd = float(np.dot(V[i] - np.array(loc[:]), n))
        if sd < gap:
            V[i] = V[i] + (gap - sd) * n
            moved += 1
    return V, moved


def hair_tris_of(cfg, n0=None):
    """Triangoli dei capelli nell'outfit: percentuale di quelli della libreria (n0), o i vecchi livelli;
    poi la riduzione totale dell'outfit (total_pct)."""
    if cfg.get("pct") is not None and n0:
        tg = n0 * max(1.0, min(100.0, float(cfg["pct"]))) / 100.0
    elif cfg.get("tris"):
        tg = int(cfg["tris"])
    else:
        tg = dict(HAIR_LEVELS).get(cfg.get("level", "Alti"), 1000)
    tg = tg * max(5.0, min(100.0, float(cfg.get("total_pct", 100.0)))) / 100.0
    return max(40, int(round(tg)))


def build_hair(bpy, np, cfg, T, cache=None):
    """Capelli dalla libreria per un outfit -> oggetto (o None).
    cfg: {"lib": file .npz, "level": Bassi/Medi/Alti, "tex": texture sostitutiva, "color": parametri colore,
          "autofit", "follow"}. cache: dict o cartella per non rifare l'adattamento (uguale per tutti gli outfit)."""
    path = (cfg or {}).get("lib") or ""
    if not path:
        return None
    if not os.path.isfile(path):
        warn("capelli: %s non trovato" % path)
        return None
    h = load_hair(np, path)
    h["TEX"] = hair_textures(np, cfg, h["TEX"], h["FT"], h["UV"])
    hmed = hair_median(np, h["TEX"], hair_used_masks(np, h["TEX"], h["UV"], h["FT"]))
    auto = bool(cfg.get("autofit", True))
    key = "%s_%d" % (safe_name(os.path.splitext(os.path.basename(path))[0]), int(auto))
    V = None
    if isinstance(cache, dict):
        V = cache.get(key)
    elif isinstance(cache, str) and os.path.isfile(os.path.join(cache, "fit_%s.npy" % key)):
        V = np.load(os.path.join(cache, "fit_%s.npy" % key))
        if len(V) != len(h["V"]):
            V = None
    if V is None:
        if auto:
            V, info = fit_hair(np, h, T)
            log("capelli %s: %s" % (os.path.splitext(os.path.basename(path))[0], info))
        else:
            V = np.asarray(h["V"], float)
            log("capelli %s: usati cosi' come sono (non adattati)" % os.path.basename(path))
        if isinstance(cache, dict):
            cache[key] = V
        elif isinstance(cache, str):
            os.makedirs(cache, exist_ok=True)
            np.save(os.path.join(cache, "fit_%s.npy" % key), V)
    Vf = np.asarray(V, float)
    topm = Vf[:, 1] > SKEL["Node21"][1]
    hc = Vf[topm].mean(0) if topm.any() else Vf.mean(0)       # centro del ritocco (come manual_hair_adjust)
    V = manual_hair_adjust(np, V, h["F"], cfg, T)
    if cfg.get("follow", True):
        V, nb = hair_off_back(np, V, T, 1.0)
        if nb:
            log("capelli: %d punti staccati dalla schiena" % nb)
    o = hair_object(bpy, np, h, V)
    n0 = tri_count(o)
    tg = hair_tris_of(cfg, n0)
    if n0 > tg:
        decimate_object(bpy, o, tg)
    specks_log("capelli", remove_specks(bpy, np, o))
    hair_weights(np, o, cfg.get("follow", True))
    o["_hair_info"] = "%d -> %d triangoli" % (n0, tri_count(o))
    o["_hair_med"] = hmed                               # per i colori nel browser (stessa media dell'export)
    one = float(cfg.get("scale", 100.0))
    o["_adj"] = [float(x) for x in hc] + [float(cfg.get(k, one)) / 100.0 for k in ("sx", "sy", "sz")] + \
        [float(cfg.get(k, 0.0)) for k in ("dx", "dy", "dz")]   # per il ritocco in tempo reale nel browser
    o["_adjkey"] = "hair"
    return o


def hair_used_masks(np, TEX, UV, FT, n=6):
    """Per ogni texture dei capelli: i pixel usati davvero dalle ciocche (campioni dentro i triangoli UV,
    allargati di un pixel). Riga 0 = alto, come le immagini."""
    UV = np.asarray(UV, float).reshape(-1, 3, 2)
    FT = np.asarray(FT, int)
    a, b = np.meshgrid(np.arange(n + 1), np.arange(n + 1))
    keep = (a + b) <= n
    w1, w2 = (a[keep] / float(n)), (b[keep] / float(n))
    w0 = 1.0 - w1 - w2
    out = []
    for i, t in enumerate(TEX):
        h, w = t.shape[:2]
        M = np.zeros((h, w), bool)
        sel = FT == i
        if sel.any():
            U = UV[sel]
            P = U[:, 0, None, :] * w0[None, :, None] + U[:, 1, None, :] * w1[None, :, None] + U[:, 2, None, :] * w2[None, :, None]
            P = np.mod(P.reshape(-1, 2), 1.0)
            x = np.clip((P[:, 0] * w).astype(int), 0, w - 1)
            y = np.clip(((1.0 - P[:, 1]) * h).astype(int), 0, h - 1)
            M[y, x] = True
            M2 = M.copy()
            M2[1:] |= M[:-1]
            M2[:-1] |= M[1:]
            M2[:, 1:] |= M[:, :-1]
            M2[:, :-1] |= M[:, 1:]
            M = M2
        out.append(M)
    return out


def hair_median(np, TEX, masks):
    """Luminosita' media (mediana) dei capelli su tutte le texture insieme, solo sui pixel usati."""
    vals = []
    for t, m in zip(TEX, masks):
        if m.any():
            _, l, _ = rgb_to_hls(np, t[..., :3][m])
            vals.append(l)
    return float(np.median(np.concatenate(vals))) if vals else 0.5


def hair_textures(np, cfg, TEX, FT, UV=None):
    """Texture dei capelli con la texture sostitutiva (sulla principale) e il colore scelto (su TUTTE le texture,
    con la stessa luminosita' media, calcolata solo sui pixel usati dalle ciocche)."""
    TEX = list(TEX)
    if not TEX:
        return TEX
    main = int(np.bincount(np.asarray(FT, int), minlength=len(TEX)).argmax())
    if cfg.get("tex"):
        try:
            TEX[main] = read_png_rgb(cfg["tex"])
        except Exception as e:
            warn("texture capelli non letta (%s)" % e)
    if cfg.get("color"):
        masks = hair_used_masks(np, TEX, UV, FT) if UV is not None else [np.ones(t.shape[:2], bool) for t in TEX]
        med = hair_median(np, TEX, masks)
        TEX = [adjust_colors(np, t[..., :3], cfg["color"], med=med) for t in TEX]
    return TEX


def manual_hair_adjust(np, V, F, cfg, T, gap=0.4):
    """Ritocco a mano dalla finestra: scala (%) attorno alla testa e spostamento in cm (x destra/sinistra del
    personaggio, y su/giu', z avanti/indietro); poi quello che finisce dentro la pelle viene rispinto fuori."""
    one = float(cfg.get("scale", 100.0))                 # lavori vecchi: scala unica
    sc = np.array([float(cfg.get(k, one)) for k in ("sx", "sy", "sz")]) / 100.0
    off = np.array([float(cfg.get("dx", 0.0)), float(cfg.get("dy", 0.0)), float(cfg.get("dz", 0.0))])
    if np.abs(sc - 1.0).max() < 1e-4 and not off.any():
        return V
    V = np.asarray(V, float)
    top = V[:, 1] > SKEL["Node21"][1]
    c = V[top].mean(0) if top.any() else V.mean(0)
    V = c + (V - c) * sc + off
    from mathutils.bvhtree import BVHTree
    bvh = BVHTree.FromPolygons([tuple(v) for v in T["V"]], [tuple(f) for f in T["F"]])
    for _ in range(2):
        moved = 0
        for i, p in enumerate(V):
            loc, nrm, fi, d = bvh.find_nearest(p, 6.0)
            if loc is None:
                continue
            n = np.array(nrm[:])
            sd = float(np.dot(p - np.array(loc[:]), n))
            if sd < gap:
                V[i] = p + (gap - sd) * n
                moved += 1
        if not moved:
            break
    log("capelli ritoccati a mano: scala %.0f/%.0f/%.0f%%, spostamento %.1f %.1f %.1f cm" % (
        sc[0] * 100, sc[1] * 100, sc[2] * 100, off[0], off[1], off[2]))
    return V


LENS_WORDS = ("lens", "glass", "lente", "lenti", "vetro", "visor", "visier", "goggle")


def material_scalar_alpha(m):
    """Opacita' fissa del materiale (DAZ 'Opacity' -> Alpha del Principled). Mappe alpha (pizzi, ritagli): 1."""
    if m is None or not m.node_tree:
        return 1.0
    b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if b is None or "Alpha" not in b.inputs or b.inputs["Alpha"].is_linked:
        return 1.0
    return float(b.inputs["Alpha"].default_value)


def lens_materials(o):
    """Indici dei materiali 'lente' di un capo: opacita' bassa in DAZ o nome tipo lens/glass/lente/vetro.
    -> {indice: opacita'}. Solo se il capo ha anche materiali normali (la montatura): un capo tutto 'velato'
    (opacita' impostata in DAZ su tutti i materiali) resta intero, si rende trasparente con la casella Trasp."""
    out = {}
    for i, m in enumerate(o.data.materials):
        if m is None:
            continue
        a = material_scalar_alpha(m)
        if a < 0.9 or any(w in m.name.lower() for w in LENS_WORDS):
            out[i] = min(a, 0.35) if a >= 0.9 else a
    if not out or not len(o.data.polygons):
        return {}
    import numpy as np
    pm = np.zeros(len(o.data.polygons), int)
    o.data.polygons.foreach_get("material_index", pm)
    if np.isin(pm, list(out)).all():
        return {}
    return out


def follow_skin(np, P, PB, PB2, radius=3.0):
    """Trasformazione rigida (rotazione + spostamento + piccola scala) che porta i vertici del corpo vicini
    al pezzo P (PB prima, PB2 dopo l'adattamento) nella nuova posizione: il pezzo resta appoggiato dove era.
    Ritorna (P trasformato, numero di vertici del corpo usati) oppure (None, n) se ce ne sono troppo pochi."""
    from mathutils.kdtree import KDTree
    kd = KDTree(len(PB))
    for i, q in enumerate(PB):
        kd.insert(q, i)
    kd.balance()
    idx = set()
    for q in P[::max(1, len(P) // 400)]:
        for _, i, d in kd.find_range(q, radius):
            idx.add(i)
    if len(idx) < 8:                                   # lontano dalla pelle: i piu' vicini comunque
        for q in P[::max(1, len(P) // 50)]:
            for _, i, d in kd.find_n(q, 6):
                idx.add(i)
    idx = np.array(sorted(idx))
    if len(idx) < 8:
        return None, len(idx)
    A, B = PB[idx], PB2[idx]
    ca, cb = A.mean(0), B.mean(0)
    A0, B0 = A - ca, B - cb
    U, S, Vt = np.linalg.svd(B0.T @ A0 / len(idx))
    D = np.eye(3)
    if np.linalg.det(U @ Vt) < 0:
        D[2, 2] = -1.0
    R = U @ D @ Vt
    var = (A0 ** 2).sum() / len(idx)
    sc = float(np.clip(np.trace(np.diag(S) @ D) / max(var, 1e-9), 0.9, 1.1))
    return (P - ca) @ (sc * R).T + cb, len(idx)


NODE_LABELS = {"Node1": "radice", "Node2": "anche", "Node3": "bacino", "Node4": "coscia sx", "Node5": "stinco sx",
               "Node6": "piede sx", "Node7": "coscia dx", "Node8": "stinco dx", "Node9": "piede dx",
               "Node10": "addome", "Node11": "petto", "Node12": "clavicola sx", "Node13": "braccio sx",
               "Node14": "avambraccio sx", "Node15": "mano sx", "Node16": "clavicola dx", "Node17": "braccio dx",
               "Node18": "avambraccio dx", "Node19": "mano dx", "Node20": "collo", "Node21": "testa",
               "Node22": "viso", "Node23": "sopracciglio", "Node24": "palpebra", "Node25": "sopracciglio",
               "Node26": "palpebra", "Node27": "mascella", "Node28": "dita dx", "Node29": "dita dx",
               "Node30": "dita dx", "Node31": "pollice dx", "Node32": "dita sx", "Node33": "dita sx",
               "Node34": "dita sx", "Node35": "pollice sx"}

FIXED_ZONES = ("eyes", "ears", "mouth", "eyesocket", "nails")   # uguali per tutti gli outfit
FACE_MAX = 3516          # faccia Genesis 8 intera (ogni outfit la riduce col suo cursore)
BODY_MAX = 10000         # corpo + piedi dopo l'importazione (ogni outfit lo riduce col suo cursore)
FACE_NODES = ("Node22", "Node23", "Node24", "Node25", "Node26", "Node27")


def rigid_garments(job):
    """Capi segnati come accessori rigidi in almeno un outfit (valgono per tutto il personaggio)."""
    out = set()
    for of in job.get("outfits") or []:
        out |= set(of.get("rigid") or [])
    return sorted(out)


def garment_texture(bpy, ob, path):
    """Texture personalizzata per tutto il capo (stessa UV dell'originale): sostituisce l'immagine del colore
    in tutti i materiali della copia (i materiali vengono copiati: l'originale non cambia)."""
    img = bpy.data.images.load(path, check_existing=True)
    me = ob.data
    if not len(me.materials):
        me.materials.append(None)
    for i, m in enumerate(list(me.materials)):
        m2 = m.copy() if m is not None else bpy.data.materials.new("_tex_" + ob.name)
        try:
            m2.use_nodes = True
        except Exception:
            pass
        nt = m2.node_tree
        bsdf = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if bsdf is None:
            bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        inp = bsdf.inputs["Base Color"]
        nd = inp.links[0].from_node if inp.is_linked else None
        if nd is None or nd.type != 'TEX_IMAGE':
            nd = nt.nodes.new("ShaderNodeTexImage")
            nt.links.new(nd.outputs["Color"], inp)
        nd.image = img
        me.materials[i] = m2
    return img


def garment_styles(of):
    """{capo: {"tex": file, "color": colore}} dell'outfit (solo i capi con qualcosa di impostato)."""
    out = {}
    for g, st in (of.get("style") or {}).items():
        st = {k: v for k, v in (st or {}).items() if v}
        if st:
            out[g] = st
    return out


def adjust_garment(np, o, adj):
    """Ritocco a mano di un capo nell'outfit: scala (%) attorno al suo centro e spostamento in cm
    (dx destra/sinistra del personaggio, dy su/giu', dz avanti/indietro)."""
    adj = adj or {}
    sc = float(adj.get("scale", 100.0)) / 100.0
    off = np.array([float(adj.get(k, 0.0)) for k in ("dx", "dy", "dz")])
    me = o.data
    if not len(me.vertices):
        return
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    c = (co.min(0) + co.max(0)) / 2
    o["_adj"] = [float(x) for x in c] + [sc, sc, sc] + [float(x) for x in off]   # per il browser
    if abs(sc - 1.0) < 1e-4 and not off.any():
        return
    co = c + (co - c) * sc + off
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    log("  %s ritoccato: scala %.0f%%, spostamento %.1f %.1f %.1f cm" % (o.name[3:], sc * 100, off[0], off[1], off[2]))


def cull_margins(of):
    """Bordo di pelle lasciato attorno ai capi, per zona (cm). Vecchi lavori: un valore solo per tutte."""
    one = float(of.get("cull_margin", 3.0))
    m = {z: one for z in ZONE_NODES}
    m.update({z: float(v) for z, v in (of.get("cull_margins") or {}).items() if z in ZONE_NODES})
    return m


def scalp_mode(cfg):
    """Pelle della testa sotto i capelli: 'colora' (default), 'togli', 'niente'."""
    m = (cfg or {}).get("scalp")
    if m in ("colora", "togli", "niente"):
        return m
    return "colora" if (cfg or {}).get("cull", True) else "niente"


def hair_cfg_from_job(job):
    """Compatibilita': capelli scritti nel lavoro (versione 1.2) invece che nell'outfit."""
    if not job.get("hair_lib"):
        return None
    lvl = {500: "Bassi", 750: "Medi"}.get(int(job.get("hair_tris", 1000)), "Alti")
    col = None
    if job.get("hair_tint"):
        hx = job["hair_tint"]
        import colorsys
        r, g, b = (int(hx[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
        col = {"mode": "colora", "h": hh * 360, "s": ss * 100, "l": (ll - 0.5) / 0.45 * 100}
    return {"lib": job["hair_lib"], "level": lvl, "tex": job.get("hair_tex", ""), "color": col,
            "autofit": job.get("hair_autofit", True), "follow": job.get("hair_follow", True),
            "cull": job.get("hair_cull_scalp", True)}


def scalp_paint(np, parts, hair, T, size):
    """Pelle della testa sotto i capelli -> maschera nell'atlas (size x size, riga 0 = alto), 0..1.
    Si colora col colore dei capelli: tra una ciocca e l'altra si vede 'capello' invece della pelle o
    dello sfondo (se la pelle venisse tolta)."""
    bvh, _ = _bvh_of([hair])
    M = np.zeros((size, size), np.float32)
    if bvh is None:
        return M
    bro = T["V"][np.isin(T["DOM"], [BONE_ORDER.index("Node23"), BONE_ORDER.index("Node25")])]
    brow = float(bro[:, 1].mean()) if len(bro) else SKEL["Node23"][1]
    for o in parts:
        me = o.data
        W = get_node_weights(np, o)
        headv = np.isin(W.argmax(1), [BONE_ORDER.index(n) for n in HEAD_NODES])
        wv = np.zeros(len(me.vertices), np.float32)
        for v in me.vertices:
            if not headv[v.index]:
                continue
            p, n = v.co, v.normal
            if not (p.y > brow + 2.0 or (n.z < -0.2 and p.y > brow - 8.0)):
                continue
            loc, nrm, idx, dist = bvh.find_nearest(p, 3.0)
            if loc is None:
                continue
            hit = bvh.ray_cast(p - n * 0.2, n, 4.0)[0] is not None
            wv[v.index] = 1.0 if (hit or dist < 1.5) else max(0.0, (3.0 - dist) / 1.5)
        if not wv.any():
            continue
        V, F, UVc, _ = mesh_arrays(np, [o])
        sel = wv[F].max(1) > 0
        M = np.maximum(M, raster_mask(np, size, UVc[sel], wv[F[sel]]))
    return M


def scalp_cull(bpy, np, parts, hair, T):
    """Pelle della testa del tutto coperta dai capelli (sopra la fronte e dietro): tolta."""
    bvh, _ = _bvh_of([hair])
    if bvh is None:
        return 0
    bro = T["V"][np.isin(T["DOM"], [BONE_ORDER.index("Node23"), BONE_ORDER.index("Node25")])]
    brow = float(bro[:, 1].mean()) if len(bro) else SKEL["Node23"][1]
    tot = 0
    for o in parts:
        me = o.data
        W = get_node_weights(np, o)
        headv = np.isin(W.argmax(1), [BONE_ORDER.index(n) for n in HEAD_NODES])
        cov = np.zeros(len(me.vertices), bool)
        for v in me.vertices:
            if not headv[v.index]:
                continue
            p, n = v.co, v.normal
            if not (p.z > -99 and (p.y > brow + 3.0 or (n.z < -0.2 and p.y > brow - 8.0))):
                continue
            loc, nrm, idx, dist = bvh.ray_cast(p - n * 0.2, n, 4.0)
            if loc is not None:
                loc2, _, _, _ = bvh.ray_cast(loc + n * 0.05, n, 3.0)       # due strati: coperto davvero
                cov[v.index] = loc2 is not None or dist < 1.5
        mask = np.array([all(cov[i] for i in p.vertices) for p in me.polygons], bool)
        tot += delete_faces(bpy, np, o, mask)
    return tot


# ------------------------------------------------------------------------------------------------
# Capelli low poly ricavati dai capelli DAZ (migliaia di strisce trasparenti): guscio pieno + texture stampata
# ------------------------------------------------------------------------------------------------
def material_alpha_image(mat):
    """Immagine collegata all'Alpha del materiale (trasparenza delle ciocche), o None."""
    if mat is None or not mat.node_tree:
        return None
    bsdf = next((n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if bsdf is not None and "Alpha" in bsdf.inputs and bsdf.inputs["Alpha"].is_linked:
        lk = bsdf.inputs["Alpha"].links[0]
        nd = lk.from_node
        if nd.type == 'TEX_IMAGE' and nd.image:
            # uscita "Alpha" del nodo: il canale alpha dell'immagine; uscita "Color": mappa in grigio (rosso)
            _ALPHA_CH[nd.image.name] = 3 if lk.from_socket.name == "Alpha" else 0
            return nd.image
    return None


_ALPHA_CH = {}


def alpha_array(img, maxdim=1024):
    """Mappa di trasparenza -> array (h, w, 1) dal canale giusto (alpha dell'immagine o grigio)."""
    A = _img_array(img, maxdim)
    if A is None:
        return None
    ch = _ALPHA_CH.get(img.name, 0)
    return A[..., ch:ch + 1]


def _sample_tex(np, A, uv):
    """A (h, w, c) righe dal basso; uv (n, 2) con ripetizione -> (n, c) (pixel piu' vicino)."""
    h, w = A.shape[:2]
    x = (np.mod(uv[:, 0], 1.0) * w).astype(int) % w
    y = (np.mod(uv[:, 1], 1.0) * h).astype(int) % h
    return A[y, x]


ALPHA_CUT = 0.3          # ciocca "piena" (le mappe ridotte sfumano i fili sottili)


def hair_shell(bpy, np, hair, T, target=3000, voxel=0.5, tex_size=512):
    """Capelli DAZ gia' adattati allo scheletro OB (oggetto) -> dict libreria (V, F, UV, FT, TEX).
    1) punti sulle ciocche solo dove la texture e' piena (alpha >= 0.5)
    2) volume a voxel, chiuso (dilata/erodi) e senza cavita' interne -> superficie
    3) via la superficie interna che tocca la testa, lisciatura, riduzione a 'target' triangoli
    4) UV e texture: ogni pixel prende il colore della prima ciocca piena che si incontra andando verso la testa."""
    from mathutils.bvhtree import BVHTree
    me = hair.data
    nv = len(me.vertices)
    co = np.zeros(nv * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    uvl = np.zeros(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uvl)
    uvl = uvl.reshape(-1, 2)
    # triangoli con UV e materiale
    tri, tuv, tmat = [], [], []
    for p in me.polygons:
        li = list(p.loop_indices)
        vs = list(p.vertices)
        for j in range(1, len(vs) - 1):
            tri.append((vs[0], vs[j], vs[j + 1]))
            tuv.append(uvl[[li[0], li[j], li[j + 1]]])
            tmat.append(p.material_index)
    tri = np.array(tri, int)
    tuv = np.array(tuv, float)
    tmat = np.array(tmat, int)
    cols, alphas = [], []
    for m in me.materials:
        img, col = material_image(m)
        a = _img_array(img, 2048) if img is not None else None
        cols.append(a if a is not None else np.array([[list(col) + [1.0]]], np.float32))
        ai = material_alpha_image(m)
        aa = alpha_array(ai, 2048) if ai is not None else None
        alphas.append(aa)
    log("capelli DAZ: %d triangoli, %d materiali" % (len(tri), len(me.materials)))
    # 1) campioni sulle ciocche, in proporzione all'area
    P0, P1, P2 = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(P1 - P0, P2 - P0), axis=1)
    nsamp = int(min(1500000, max(200000, area.sum() / (voxel * voxel) * 6)))
    rng = np.random.default_rng(7)
    ti = rng.choice(len(tri), nsamp, p=area / area.sum())
    r1, r2 = rng.random(nsamp), rng.random(nsamp)
    s = np.sqrt(r1)
    b0, b1, b2 = 1 - s, s * (1 - r2), s * r2
    pts = P0[ti] * b0[:, None] + P1[ti] * b1[:, None] + P2[ti] * b2[:, None]
    suv = tuv[ti, 0] * b0[:, None] + tuv[ti, 1] * b1[:, None] + tuv[ti, 2] * b2[:, None]
    keep = np.ones(nsamp, bool)
    for mi, A in enumerate(alphas):
        sel = tmat[ti] == mi
        if A is not None and sel.any():
            keep[sel] = _sample_tex(np, A, suv[sel])[:, 0] >= ALPHA_CUT
    pts = pts[keep]
    # via la calotta e le radici attaccate alla pelle (in DAZ sono sfumate: qui coprirebbero la fronte)
    # punti attaccati alla pelle: sul viso sotto le sopracciglia si tolgono (radici sfumate sulla fronte);
    # altrove (calotta piatta, nuca) si portano appena fuori dalla cute, cosi' il guscio copre la testa
    bvh0 = BVHTree.FromPolygons([tuple(v) for v in T["V"]], [tuple(f) for f in T["F"]])
    near = np.zeros(len(pts), bool)
    drop = np.zeros(len(pts), bool)
    brow_y = SKEL["Node23"][1] + 1.5
    head_z = SKEL["Node21"][2]
    MIN_UP = 0.45
    for i, p in enumerate(pts):
        loc, nrm, fi, dd = bvh0.find_nearest(p, 0.6)
        if loc is None:
            continue
        near[i] = True
        if p[1] < brow_y and p[2] > head_z + 4.0:         # davanti al viso, sotto le sopracciglia
            drop[i] = True
        else:
            pts[i] = np.array(loc[:]) + np.array(nrm[:]) * MIN_UP
    pts = pts[~drop]
    log("punti sulle ciocche piene: %d su %d (%d attaccati alla pelle: %d portati sopra la cute, %d sul viso tolti)" % (
        len(pts), nsamp, int(near.sum()), int(near.sum() - drop.sum()), int(drop.sum())))
    if len(pts) < 100:
        raise RuntimeError("i capelli sembrano tutti trasparenti: non riesco a ricavarne la forma")
    # 2) voxel
    lo = pts.min(0) - 3 * voxel
    dims = np.ceil((pts.max(0) + 3 * voxel - lo) / voxel).astype(int) + 1
    occ = np.zeros(dims, bool)
    ijk = np.floor((pts - lo) / voxel).astype(int)
    occ[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True

    def dil(g, n=1):
        for _ in range(n):
            g2 = g.copy()
            g2[1:, :, :] |= g[:-1, :, :]
            g2[:-1, :, :] |= g[1:, :, :]
            g2[:, 1:, :] |= g[:, :-1, :]
            g2[:, :-1, :] |= g[:, 1:, :]
            g2[:, :, 1:] |= g[:, :, :-1]
            g2[:, :, :-1] |= g[:, :, 1:]
            g = g2
        return g

    def ero(g, n=1):
        return ~dil(~g, n)
    occ = ero(dil(occ, 2), 1)                         # chiude i buchi tra le ciocche
    # cavita' interne (non raggiungibili da fuori): piene
    out = np.zeros(dims, bool)
    out[0, :, :] = out[-1, :, :] = out[:, 0, :] = out[:, -1, :] = out[:, :, 0] = out[:, :, -1] = True
    out &= ~occ
    for _ in range(int(dims.sum())):
        o2 = dil(out, 1) & ~occ
        if (o2 == out).all():
            break
        out = o2
    occ = ~out
    # superficie: facce tra voxel pieni e vuoti, con la normale verso il vuoto
    cid = lambda i, j, k: (i * (dims[1] + 1) + j) * (dims[2] + 1) + k
    quads = []
    pad = np.zeros(dims + 2, bool)
    pad[1:-1, 1:-1, 1:-1] = occ
    for ax in range(3):
        u, v = (ax + 1) % 3, (ax + 2) % 3                # cross(u, v) = +ax
        a = np.moveaxis(pad, ax, 0)                       # assi rimasti nell'ordine originale
        rest = [x for x in range(3) if x != ax]
        for arr, sign in ((a[1:-1] & ~a[2:], 1), (a[1:-1] & ~a[:-2], -1)):
            idx = np.argwhere(arr[:, 1:-1, 1:-1])
            if not len(idx):
                continue
            I = idx[:, 0] + (1 if sign > 0 else 0)
            other = {rest[0]: idx[:, 1], rest[1]: idx[:, 2]}
            corners = [(0, 0), (1, 0), (1, 1), (0, 1)] if sign > 0 else [(0, 0), (0, 1), (1, 1), (1, 0)]
            q = []
            for du, dv in corners:
                c = np.zeros((len(I), 3), int)
                c[:, ax] = I
                c[:, u] = other[u] + du
                c[:, v] = other[v] + dv
                q.append(cid(c[:, 0], c[:, 1], c[:, 2]))
            quads.append(np.stack(q, 1))
    quads = np.vstack(quads)
    used, inv = np.unique(quads.ravel(), return_inverse=True)
    quads = inv.reshape(-1, 4)
    ii = used // ((dims[1] + 1) * (dims[2] + 1))
    jj = (used // (dims[2] + 1)) % (dims[1] + 1)
    kk = used % (dims[2] + 1)
    VV = lo + np.c_[ii, jj, kk] * voxel
    log("volume: %dx%dx%d voxel da %.1f cm, superficie %d quadrati" % (dims[0], dims[1], dims[2], voxel, len(quads)))
    sm = bpy.data.meshes.new("guscio")
    sm.from_pydata([tuple(p) for p in VV], [], [tuple(q) for q in quads])
    sm.update()
    so = bpy.data.objects.new("guscio", sm)
    bpy.context.scene.collection.objects.link(so)
    so.matrix_world = hair.matrix_world.copy()
    with EditMode(bpy, so):
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=voxel * 0.01)
        bpy.ops.mesh.normals_make_consistent(inside=False)
    # superficie pulita (i voxel che si toccano solo per uno spigolo bloccherebbero la riduzione)
    rm = so.modifiers.new("remesh", 'REMESH')
    rm.mode = 'VOXEL'
    rm.voxel_size = voxel * 0.8
    try:
        rm.use_smooth_shade = True
    except AttributeError:
        pass
    with bpy.context.temp_override(object=so, active_object=so, selected_objects=[so], selected_editable_objects=[so]):
        bpy.ops.object.modifier_apply(modifier=rm.name)
    mod = so.modifiers.new("liscia", 'SMOOTH')
    mod.factor = 0.8
    mod.iterations = 25
    with bpy.context.temp_override(object=so, active_object=so, selected_objects=[so], selected_editable_objects=[so]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    # 3) via la superficie interna (rivolta verso la testa, vicina alla pelle)
    TV, TF = T["V"], T["F"]
    bvh = BVHTree.FromPolygons([tuple(v) for v in TV], [tuple(f) for f in TF])
    neck = SKEL["Node20"][1]
    me2 = so.data
    inner = np.zeros(len(me2.polygons), bool)
    for p in me2.polygons:
        c, n = p.center, p.normal
        hit = bvh.ray_cast(c + n * 0.05, n, 2.5)
        if hit[0] is None:
            continue
        loc, nrm, fi, d = bvh.find_nearest(c, 4.0)
        near = loc is not None and (d < 1.2 or np.dot(np.array((c - loc)[:]), np.array(nrm[:])) < 0)
        if near or c.y > neck:
            inner[p.index] = True
    n_in = delete_faces(bpy, np, so, inner)
    log("tolta la superficie interna verso la testa: %d facce" % n_in)
    # via anche le parti del guscio senza ciocche vere vicino (riga, viso scoperto, spazi tra le ciocche)
    from mathutils.kdtree import KDTree
    sub = pts[::max(1, len(pts) // 200000)]
    kd = KDTree(len(sub))
    for i, p in enumerate(sub):
        kd.insert(p, i)
    kd.balance()
    # (solo staccate dalla testa: sulla calotta i punti attaccati alla pelle li ho tolti io, li' il guscio serve)
    far = np.zeros(len(so.data.polygons), bool)
    for p in so.data.polygons:
        if kd.find(p.center)[2] > 1.6 * voxel + 0.4:
            loc, _, _, d = bvh.find_nearest(p.center, 2.5)
            far[p.index] = loc is None
    n_far = delete_faces(bpy, np, so, far)
    log("tolte le parti senza ciocche vicino (lontane dalla testa): %d facce" % n_far)
    # 3b) guscio stretto sui capelli veri: ogni vertice scende lungo la normale fino alla prima ciocca piena
    #     (via lo spessore in piu' dei voxel); dove non trova ciocche resta dov'e' (niente buchi)
    hb0 = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(t) for t in tri])

    def opaque_at(idx, loc):
        a, b, c = tri[idx]
        pa, pb, pc = co[a], co[b], co[c]
        v0, v1, v2 = pb - pa, pc - pa, np.array(loc[:]) - pa
        d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
        d20, d21 = v2 @ v0, v2 @ v1
        dn = d00 * d11 - d01 * d01
        if abs(dn) < 1e-12:
            return True
        bb = (d11 * d20 - d01 * d21) / dn
        cc = (d00 * d21 - d01 * d20) / dn
        uvh = tuv[idx, 0] * (1 - bb - cc) + tuv[idx, 1] * bb + tuv[idx, 2] * cc
        al = alphas[tmat[idx]]
        return al is None or _sample_tex(np, al, uvh[None])[0, 0] >= ALPHA_CUT
    me2 = so.data
    me2.update()
    nvs = len(me2.vertices)
    VS = np.zeros(nvs * 3)
    me2.vertices.foreach_get("co", VS)
    VS = VS.reshape(-1, 3)
    NS = np.zeros(nvs * 3)
    me2.vertices.foreach_get("normal", NS)
    NS = NS.reshape(-1, 3)
    from mathutils import Vector
    tgt = VS.copy()
    hitm = np.zeros(nvs, bool)
    reach = 3.0 * voxel + 1.0                           # quanto puo' scendere al massimo (cm)
    for i in range(nvs):
        n = Vector(tuple(-NS[i]))
        org = Vector(tuple(VS[i])) - n * 0.3            # parte poco fuori dal guscio
        travel = 0.0
        for _ in range(8):
            loc, _n, idx, dd = hb0.ray_cast(org, n, reach + 0.3 - travel)
            if loc is None:
                break
            travel += dd
            if opaque_at(idx, loc):
                q = np.array(loc[:])
                ln, _a, _b, dh = bvh.find_nearest(loc, 0.4)
                if ln is None:                            # non sulla pelle
                    tgt[i] = q + NS[i] * 0.08            # appena fuori dalla ciocca
                    hitm[i] = True
                break
            org = loc + n * 0.02
    # spostamento lisciato (niente vertici che saltano): media con i vicini, piu' volte
    disp = np.where(hitm[:, None], tgt - VS, 0.0)
    ev = np.zeros(len(me2.edges) * 2, int)
    me2.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    w = hitm.astype(float)
    for _ in range(15):
        acc = np.zeros_like(disp)
        cnt = np.zeros(nvs)
        accw = np.zeros(nvs)
        np.add.at(acc, ev[:, 0], disp[ev[:, 1]])
        np.add.at(acc, ev[:, 1], disp[ev[:, 0]])
        np.add.at(cnt, ev[:, 0], 1)
        np.add.at(cnt, ev[:, 1], 1)
        np.add.at(accw, ev[:, 0], w[ev[:, 1]])
        np.add.at(accw, ev[:, 1], w[ev[:, 0]])
        sm_d = (disp + acc) / (1 + cnt)[:, None]
        sm_w = (w + accw) / (1 + cnt)
        disp = np.where(hitm[:, None], disp * 0.5 + sm_d * 0.5, sm_d / np.maximum(sm_w, 1e-6)[:, None] * sm_w[:, None])
        w = np.maximum(w, sm_w)
    VS2 = VS + disp
    me2.vertices.foreach_set("co", VS2.ravel())
    me2.update()
    mod = so.modifiers.new("liscia2", 'SMOOTH')          # superficie morbida (le ciocche sono a strati)
    mod.factor = 0.6
    mod.iterations = 8
    with bpy.context.temp_override(object=so, active_object=so, selected_objects=[so], selected_editable_objects=[so]):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    inward = np.einsum("ij,ij->i", -(VS2 - VS), NS)
    log("guscio stretto sulle ciocche: %d vertici su %d agganciati, spessore tolto in media %.2f cm (max %.2f)" % (
        int(hitm.sum()), nvs, float(inward[hitm].mean()) if hitm.any() else 0.0,
        float(inward.max()) if nvs else 0.0))
    # buchi rimasti (piccoli): chiusi; le aperture grandi (viso, collo, sotto) restano
    with EditMode(bpy, so):
        bpy.ops.mesh.select_mode(type='EDGE')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.mesh.select_non_manifold(extend=False, use_wire=False, use_boundary=True, use_multi_face=False,
                                         use_non_contiguous=False, use_verts=False)
        bpy.ops.mesh.fill_holes(sides=int(12.0 / (voxel * 0.8)))
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.normals_make_consistent(inside=False)
    triangulate(bpy, so)
    n0 = tri_count(so)
    for sym in (True, False):
        for _ in range(4):
            cur = tri_count(so)
            if cur <= target * 1.03:
                break
            mod = so.modifiers.new("Decimate", 'DECIMATE')
            mod.decimate_type = 'COLLAPSE'
            mod.ratio = max(0.01, target / float(cur))
            mod.use_collapse_triangulate = True
            mod.use_symmetry = sym
            with bpy.context.temp_override(object=so, active_object=so, selected_objects=[so],
                                           selected_editable_objects=[so]):
                bpy.ops.object.modifier_apply(modifier=mod.name)
            if tri_count(so) >= cur * 0.97:
                break
    # pezzi del guscio staccati e piccoli (anelli, frammenti): via
    comp = mesh_components(np, so)
    me3 = so.data
    ar = np.zeros(len(me3.polygons))
    me3.polygons.foreach_get("area", ar)
    ls = np.zeros(len(me3.polygons), int)
    me3.polygons.foreach_get("loop_start", ls)
    lv = np.zeros(len(me3.loops), int)
    me3.loops.foreach_get("vertex_index", lv)
    fc = comp[lv[ls]]
    carea = np.bincount(fc, weights=ar)
    small = carea < 0.04 * carea.sum()
    if small.any() and not small.all():
        n_sm = delete_faces(bpy, np, so, small[fc])
        log("guscio: tolti %d pezzi staccati piccoli (%d facce)" % (int(small.sum()), n_sm))
    log("guscio: %d -> %d triangoli" % (n0, tri_count(so)))
    # 4) UV e texture stampata dalle ciocche vere
    if not so.data.uv_layers:
        so.data.uv_layers.new(name="UVMap")
    V, F, UVc, _ = mesh_arrays(np, [so])
    # UV sferiche attorno alla testa: un'isola sola, cucitura dietro, polo sulla sommita'
    cen = np.array([0.0, SKEL["Node21"][1] + 8.0, float(np.median(V[:, 2]))])
    rel = V[F] - cen
    az = (np.arctan2(rel[..., 0], -rel[..., 2]) / (2 * math.pi)) % 1.0       # 0 = dietro, 0.5 = davanti
    pol = np.arccos(np.clip(rel[..., 1] / np.maximum(np.linalg.norm(rel, axis=2), 1e-6), -1, 1))
    u = az.copy()
    wrap = (u.max(1) - u.min(1)) > 0.5                 # triangoli a cavallo della cucitura
    u[wrap] = np.where(u[wrap] < 0.5, u[wrap] + 1.0, u[wrap])
    UVc = np.stack([u, 1.0 - pol / math.pi], axis=2)
    hb = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(t) for t in tri])
    size = tex_size
    img = np.zeros((size, size, 3), np.float32)
    got = np.zeros((size, size), bool)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)
    from mathutils import Vector
    stat = {"raggi": 0, "vuoto": 0, "trasparente": 0}
    for t in range(len(F)):
        A = UVc[t] * size
        X, Y = A[:, 0], A[:, 1]
        x0, x1 = max(0, int(X.min())), min(2 * size - 1, int(X.max()) + 1)
        y0, y1 = max(0, int(Y.min())), min(size - 1, int(Y.max()) + 1)
        den = (Y[1] - Y[2]) * (X[0] - X[2]) + (X[2] - X[1]) * (Y[0] - Y[2])
        if abs(den) < 1e-9 or x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((Y[1] - Y[2]) * (gx - X[2]) + (X[2] - X[1]) * (gy - Y[2])) / den
        w1 = ((Y[2] - Y[0]) * (gx - X[2]) + (X[0] - X[2]) * (gy - Y[2])) / den
        w2 = 1 - w0 - w1
        ok = (w0 >= -0.02) & (w1 >= -0.02) & (w2 >= -0.02)
        if not ok.any():
            continue
        Pp = (w0[ok, None] * V[F[t, 0]] + w1[ok, None] * V[F[t, 1]] + w2[ok, None] * V[F[t, 2]])
        n = Vector(tuple(-fn[t]))
        ys, xs = (gy[ok] - 0.5).astype(int), (gx[ok] - 0.5).astype(int) % size
        for p, yy, xx in zip(Pp, ys, xs):
            stat["raggi"] += 1
            org = Vector(tuple(p)) - n * 0.6
            for _ in range(6):                        # prima ciocca piena andando verso la testa
                loc, nrm, idx, d = hb.ray_cast(org, n, 5.0)
                if loc is None:
                    stat["vuoto"] += 1
                    break
                a, b, c = tri[idx]
                pa, pb, pc = co[a], co[b], co[c]
                v0, v1, v2 = pb - pa, pc - pa, np.array(loc[:]) - pa
                d00, d01, d11 = v0 @ v0, v0 @ v1, v1 @ v1
                d20, d21 = v2 @ v0, v2 @ v1
                dn = d00 * d11 - d01 * d01
                if abs(dn) < 1e-12:
                    break
                bb = (d11 * d20 - d01 * d21) / dn
                cc = (d00 * d21 - d01 * d20) / dn
                uvh = tuv[idx, 0] * (1 - bb - cc) + tuv[idx, 1] * bb + tuv[idx, 2] * cc
                mi = tmat[idx]
                al = alphas[mi]
                if al is None or _sample_tex(np, al, uvh[None])[0, 0] >= ALPHA_CUT:
                    img[yy, xx] = _sample_tex(np, cols[mi], uvh[None])[0, :3]
                    got[yy, xx] = True
                    break
                stat["trasparente"] += 1
                org = loc + n * 0.02
    log("texture stampata: %d pixel dalle ciocche vere (%s)" % (int(got.sum()), stat))
    # pixel senza ciocca: colore dei vicini (poi il medio)
    if got.any():
        mean = img[got].mean(0)
        for _ in range(64):
            if got.all():
                break
            acc = np.zeros_like(img)
            cnt = np.zeros(got.shape, np.float32)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                s2 = np.roll(np.roll(got, dy, 0), dx, 1)
                acc += np.roll(np.roll(img, dy, 0), dx, 1) * s2[..., None]
                cnt += s2
            new = ~got & (cnt > 0)
            img[new] = acc[new] / cnt[new][:, None]
            got |= new
        img[~got] = mean
    # ciocche: sfumatura lungo la caduta dei capelli (asse v), poco di lato -> strisce come fili
    acc = np.zeros_like(img)
    for dy in range(-6, 7):
        acc += np.roll(img, dy, 0) * (1.0 - abs(dy) / 7.0)
    img = acc / sum(1.0 - abs(dy) / 7.0 for dy in range(-6, 7))
    blur = sum(np.roll(img, dx, 1) for dx in range(-3, 4)) / 7.0
    lum = img.mean(2, keepdims=True)
    lumb = blur.mean(2, keepdims=True)
    k = np.clip((lum + 1.2 * (lum - lumb)) / np.maximum(lum, 1e-3), 0.4, 1.8)
    img = np.clip(img * k, 0, 1)                       # fili piu' marcati, stesso colore (niente righe rosse)
    tex = (np.clip(img[::-1], 0, 1) * 255 + 0.5).astype(np.uint8)
    out = {"V": V, "F": F, "UV": UVc, "FT": np.zeros(len(F), int), "TEX": [tex]}
    bpy.data.objects.remove(so, do_unlink=True)
    return out


def hairshell_add(fbx, garment, name, libdir, target=3000):
    """Capelli DAZ dell'FBX -> capelli low poly nella libreria (con la testa del personaggio come riferimento)."""
    import bpy
    import numpy as np
    os.makedirs(libdir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log("leggo %s" % os.path.basename(fbx))
    bpy.ops.import_scene.fbx(filepath=fbx)
    arm, body, lashes, others = find_scene_parts(bpy)
    byname = garment_names(others)
    if garment not in byname:
        raise RuntimeError("nell'FBX non c'e' '%s'" % garment)
    hair = byname[garment]
    for o in lashes + [o for n, o in byname.items() if n != garment]:
        bpy.data.objects.remove(o, do_unlink=True)
    prepare(bpy, np, arm, body, [hair], 0.3, 0.0)
    T = body_arrays(np, body)
    h = hair_shell(bpy, np, hair, T, target)
    # testa del personaggio come riferimento (per adattarli poi ad altri personaggi)
    head = np.isin(T["DOM"], [BONE_ORDER.index(n) for n in HEAD_NODES])
    h["SV"], h["SN"] = T["V"][head], T["N"][head]
    h["SJ"] = np.array([int(BONE_ORDER[i][4:]) for i in T["DOM"][head]])
    path = os.path.join(libdir, safe_name(name) + ".npz")
    save_hair(np, h, path)
    h = load_hair(np, path)
    Vt = h["V"] - [0.5 * (h["V"][:, 0].min() + h["V"][:, 0].max()), 0, 0]
    imgs = [render_tex(np, Vt, h["F"], h["UV"], h["FT"], [t[..., :3] for t in h["TEX"]], y, W=150, H=170) for y in (0, 90)]
    write_png(os.path.splitext(path)[0] + ".png", np.concatenate(imgs, axis=1))
    log("salvato %s: %d triangoli, con la testa del personaggio" % (os.path.basename(path), len(h["F"])))


def make_look_mesh(bpy, np, body, path):
    """Testa, spalle e braccia con le texture vere (atlas 512) per l'anteprima colorata della finestra."""
    o = duplicate(bpy, body, "_look")
    me = o.data
    zones = [zone_name(m.name if m else "") for m in me.materials]
    pm = poly_mats(np, me)
    cen = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    bad = np.array([zones[i] in DELETE_ZONES + ("Mouth",) for i in pm]) | (cen[:, 1] < SKEL["Node11"][1] + 6)
    delete_faces(bpy, np, o, bad)
    triangulate(bpy, o)
    zl = {o.name: poly_zones(o)}
    lid = lid_weights(np, [o])
    ab = build_atlas(bpy, np, [o], 512, path[:-4] + ".png", "_look", imp_of=lambda z: IMPORTANCE.get(z, 1.0))
    V, F, UVc, FZ = mesh_arrays(np, [o], zl)
    eyes = eye_centers(np, V, F, FZ)
    hand = V[V[:, 0] > SKEL["Node15"][0] - 2.0]
    np.savez_compressed(path, V=V, F=F, UV=UVc, FZ=FZ, RGB=ab["rgb"], LID=lid,
                        EYES=np.array([list(eyes[k][0]) + [eyes[k][1]] for k in (1, -1) if k in eyes]),
                        HAND=hand.mean(0) if len(hand) else np.array(SKEL["Node32"]))
    bpy.data.objects.remove(o, do_unlink=True)
    log("anteprima colori: testa e mani pronte")
    return path


def _look_data(np, job, mem):
    """Testa con texture, maschere, palpebre: lette una volta sola (il server le tiene in memoria)."""
    path = job["look"]
    key = (path, os.path.getmtime(path))
    if mem.get("look_key") != key:
        d = np.load(path)
        V, F, UVc, FZ, rgb = d["V"], d["F"], d["UV"], d["FZ"], d["RGB"]
        eyes = {}
        for row in d["EYES"]:
            eyes[1 if row[0] > 0 else -1] = (row[:3], float(row[3]))
        masks = region_masks(np, rgb.shape[0], V, F, UVc, FZ, eyes)
        lid = d["LID"] if "LID" in d.files else None          # analisi fatte con la 1.4: niente palpebre
        mem["look"] = {"V": V, "F": F, "UV": UVc, "FZ": FZ, "RGB": rgb, "eyes": eyes, "masks": masks, "LID": lid,
                       "HAND": np.asarray(d["HAND"], float)}
        mem["look_key"] = key
        mem.pop("look_tex", None)
    return mem["look"]


def _head_data(np, job, mem):
    path = job["head"]
    key = (path, os.path.getmtime(path))
    if mem.get("head_key") != key:
        h = np.load(path)
        mem["head"] = {"V": h["V"], "F": h["F"], "N": h["N"], "DOM": h["DOM"]}
        mem["head_key"] = key
        mem["hair"] = {}
        mem["fit"] = {}
    return mem["head"]


def _hair_geometry(bpy, np, hc, T, job, mem):
    """Capelli adattati e ridotti per l'anteprima: la geometria non dipende dal colore, quindi resta in memoria
    e cambiando solo il colore si rifanno le texture e basta."""
    gk = json.dumps([hc.get("lib"), os.path.getmtime(hc["lib"]), hc.get("level", "Alti"), hc.get("pct"),
                     hc.get("total_pct"), bool(hc.get("autofit", True)),
                     bool(hc.get("follow", True))] + [round(float(hc.get(k, hc.get("scale", 100.0) if k[0] == "s" else 0.0)), 1)
                                                      for k in ("sx", "sy", "sz", "dx", "dy", "dz")])
    cache = mem.setdefault("hair", {})
    if gk not in cache:
        o = build_hair(bpy, np, dict(hc, color=None, tex=""), T, mem.setdefault("fit", {}))
        if o is None:
            return None
        HV, HF, HUV, _ = mesh_arrays(np, [o])
        mi = np.array([p.material_index for p in o.data.polygons for _ in range(len(p.vertices) - 2)], int)
        h = load_hair(np, hc["lib"])
        cache.clear()                                    # basta l'ultima: i capelli scelti adesso
        cache[gk] = {"V": HV, "F": HF, "UV": HUV, "MI": mi, "TEX": [shrink_tex(np, t[..., :3], 512) for t in h["TEX"]],
                     "FT": h["FT"], "info": o["_hair_info"]}
        me = o.data
        bpy.data.objects.remove(o, do_unlink=True)
        if me.users == 0:
            bpy.data.meshes.remove(me)
        for img in list(bpy.data.images):
            if img.users == 0:
                bpy.data.images.remove(img)
        log("capelli: %s" % cache[gk]["info"])
    return cache[gk]


def look_preview(job, mem=None):
    """Anteprima dell'outfit per la finestra: testa con texture vera, capelli e colori scelti.
    10 riquadri 240x300: 8 giri attorno alla testa (0..7), il viso da vicino (8), la mano (9).
    job["views"]: quali riquadri disegnare (default tutti); job["outdir_views"]: un PNG per riquadro
    (v0.png ... v9.png) invece della striscia unica job["out"]."""
    import bpy
    import numpy as np
    if mem is None:
        mem = {}
        bpy.ops.wm.read_factory_settings(use_empty=True)
    L = _look_data(np, job, mem)
    V, F, UVc = L["V"], L["F"], L["UV"]
    looks = dict(job.get("looks") or {})
    looks["iris"] = job.get("eyes_color")
    tk = json.dumps(looks, sort_keys=True)
    if mem.get("look_tex", (None,))[0] != tk:
        rgb = apply_looks(np, L["RGB"], L["masks"], looks, L["LID"])
        mem["look_tex"] = (tk, rgb)
    rgb = mem["look_tex"][1]
    texs = [rgb]
    P, FF, UU, TI = [V], [F], [UVc], [np.zeros(len(F), int)]
    hc = dict(job.get("hair") or {})
    if hc.get("lib") and os.path.isfile(hc["lib"]):
        T = _head_data(np, job, mem)
        g = _hair_geometry(bpy, np, hc, T, job, mem)
        if g is not None:
            ht = hair_textures(np, hc, g["TEX"], g["FT"])
            P.append(g["V"])
            FF.append(g["F"] + len(V))
            UU.append(g["UV"])
            TI.append(g["MI"] + len(texs))
            texs += [t[..., :3] for t in ht]
    P = np.vstack(P)
    FA = np.vstack(FF)
    UA = np.vstack(UU)
    TA = np.concatenate(TI)
    views = job.get("views")
    views = list(range(10)) if views is None else [int(v) for v in views]
    cy = SKEL["Node21"][1] + 3.0
    eyes = L["eyes"]
    out = {}
    for vi in views:
        if vi < 8:
            out[vi] = render_tex(np, P, FA, UA, TA, texs, vi * 45, W=240, H=300, zoom=(0.0, cy, 21.0))
        elif vi == 8:
            ey = float(np.mean([e[0][1] for e in eyes.values()])) if eyes else SKEL["Node24"][1]
            out[vi] = render_tex(np, P, FA, UA, TA, texs, 0, W=240, H=300, zoom=(0.0, ey - 3.0, 7.5))
        else:
            # mano sinistra vista dall'alto (le unghie stanno sopra, la mano e' col palmo in giu')
            hc_ = L["HAND"]
            near = np.linalg.norm(V - hc_, axis=1) < 14
            keep = near[F].all(1)
            th = math.radians(75)
            Rx = np.array([[1, 0, 0], [0, math.cos(th), -math.sin(th)], [0, math.sin(th), math.cos(th)]])
            Q = (V - hc_) @ Rx.T
            out[vi] = render_tex(np, Q, F[keep], UVc[keep], np.zeros(int(keep.sum()), int), [rgb], 0, W=240, H=300,
                                 zoom=(2.0, 0.0, 9.0))
    if job.get("outdir_views"):
        os.makedirs(job["outdir_views"], exist_ok=True)
        for vi, img in out.items():
            write_png(os.path.join(job["outdir_views"], "v%d.png" % vi), img)
    else:
        blank = np.full((300, 240, 3), 112, np.uint8)
        write_png(job["out"], np.concatenate([out.get(i, blank) for i in range(10)], axis=1))
    log("anteprima pronta")


def server():
    """Blender sempre aperto per le anteprime della finestra: un comando JSON per riga su stdin,
    risposta "FATTO <id> <codice>". Testa, capelli adattati e texture restano in memoria."""
    import bpy
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mem = {}
    PNG_LEVEL[0] = 1
    print(TAG + "PRONTO", flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid, rc = "?", 0
        try:
            req = json.loads(line)
            rid = req.get("id", "?")
            if req.get("cmd") == "quit":
                break
            if req.get("cmd") == "look":
                look_preview(req["job"], mem)
            elif req.get("cmd") == "hair":
                hair_preview(req["job"], mem)
            elif req.get("cmd") == "outfit3d":
                job = dict(req["job"])
                job["outdir"] = req["dir"]
                job["outfit_folders"] = False
                of = next((o for o in job.get("outfits") or [] if o.get("name") == req.get("outfit")), None)
                if of is None:
                    of = {"name": "base", "garments": [], "mesh1": "", "tris": 0, "cull_body": False}
                t0 = time.time()
                convert(job, mem, preview=of)
                log("anteprima 3D pronta in %.1f s" % (time.time() - t0))
            else:
                raise RuntimeError("comando sconosciuto %r" % req.get("cmd"))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(TAG + "ERRORE: %s" % e, flush=True)
            rc = 2
        print(TAG + "FATTO %s %d" % (rid, rc), flush=True)
    return 0


def hair_preview(job, mem=None):
    """Anteprima per la finestra: capelli adattati sulla testa del personaggio, 8 viste in una striscia."""
    import bpy
    import numpy as np
    if mem is None:
        mem = {}
        bpy.ops.wm.read_factory_settings(use_empty=True)
    T = _head_data(np, job, mem)
    if not job.get("hair_lib"):
        raise RuntimeError("scegli dei capelli dalla libreria")
    g = _hair_geometry(bpy, np, {"lib": job["hair_lib"], "level": job.get("level", "Alti"),
                                 "autofit": job.get("hair_autofit", True), "follow": True}, T, job, mem)
    HV, HF, HUV, HT = g["V"], g["F"], g["UV"], g["MI"]
    texs = [t[..., :3] for t in g["TEX"]]
    TV, TF = T["V"], T["F"]
    keep = TF[(TV[TF][:, :, 1].min(1) > SKEL["Node11"][1] + 6)]
    skin = np.array([224, 172, 140], np.uint8)
    texs.append(np.tile(skin, (2, 2, 1)))
    P = np.vstack([TV, HV])
    F = np.vstack([keep, np.array(HF) + len(TV)])
    UV = np.vstack([np.zeros((len(keep), 3, 2)), np.asarray(HUV)])
    TI = np.concatenate([np.full(len(keep), len(texs) - 1), np.asarray(HT)])
    cy = SKEL["Node21"][1] + 2.0
    views = [render_tex(np, P, F, UV, TI, texs, yaw, W=240, H=300, zoom=(0.0, cy, 24.0)) for yaw in range(0, 360, 45)]
    write_png(job["out"], np.concatenate(views, axis=1))
    log("anteprima capelli pronta")


def _convert_base(job):
    import bpy
    import numpy as np
    SHOULDER_BAND[0] = float(job.get("shoulder_band", 6.0))
    SHOULDER_MODE[0] = job.get("shoulder_mode", "no")
    LIP27[0] = float(job.get("lip_lower_node27", 1.0))
    sp = job.get("specks") or {}
    SPECKS[:] = [bool(sp.get("on", True)), int(sp.get("tris", 3)), float(sp.get("area", 0.5))]
    SHOULDER_MODE[1] = float(job.get("shoulder_smooth", 4.0))
    SHOULDER_BAND[1] = float(job.get("shoulder_shift", 0.0) if job.get("arms_p06", True) else 0.0)
    t = dict(DEFAULT_TARGETS)
    t.update(job.get("targets") or {})
    # corpo: ogni outfit lo porta al suo numero dopo la pulizia; qui si riduce meno (c'e' margine per tutti)
    # (anche la faccia: qui resta intera, ogni outfit la riduce col suo cursore)
    fq = G8_MAX["feet"] / float(G8_MAX["body"] + G8_MAX["feet"])
    t["feet"], t["body"] = int(round(BODY_MAX * fq)), int(round(BODY_MAX * (1 - fq)))
    t["face"] = 10 ** 6
    log("corpo nella preparazione: %d triangoli, faccia intera (poi ogni outfit li porta ai suoi numeri)" % BODY_MAX)
    fbx, outdir = job["fbx"], job["outdir"]
    name = safe_name(job.get("name") or os.path.splitext(os.path.basename(fbx))[0])
    amb = int(job.get("ambient", 20))
    os.makedirs(outdir, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    log("leggo %s" % os.path.basename(fbx))
    bpy.ops.import_scene.fbx(filepath=fbx)
    arm, body, lashes, others = find_scene_parts(bpy)
    byname = garment_names(others)
    outfits = job.get("outfits") or []
    needed = []
    for of in outfits:
        for g in of.get("garments", []) + ([of["mesh1"]] if of.get("mesh1") else []):
            if g not in byname:
                warn("outfit '%s': il capo '%s' non c'e' nell'FBX" % (of.get("name"), g))
            elif g not in needed:
                needed.append(g)
    keep_lashes = bool(job.get("keep_lashes", False)) and lashes
    for o in (lashes if not keep_lashes else []) + [o for n, o in byname.items() if n not in needed]:
        bpy.data.objects.remove(o, do_unlink=True)
    garments = {n: byname[n] for n in needed}
    prepare(bpy, np, arm, body, list(garments.values()) + (list(lashes) if keep_lashes else []),
            float(job.get("brow_side", 0.3)),
            float(job.get("joint_smooth", 1.0)), float(job.get("shoulder_lift", 8.0)),
            bool(job.get("arms_p06", True)), [garments[g] for g in rigid_garments(job) if g in garments],
            None, bool(job.get("_flat_feet")), job.get("_feet_adj") or (0.0, 0.0))
    log("altezza del corpo adattato: %.1f cm" % max(v.co.y for v in body.data.vertices))
    lashes_base = None
    if keep_lashes:
        lo_ = lashes[0]
        if len(lashes) > 1:
            with bpy.context.temp_override(object=lo_, active_object=lo_, selected_objects=list(lashes),
                                           selected_editable_objects=list(lashes)):
                bpy.ops.object.join()
        lz = [zone_name(m.name if m else "") for m in lo_.data.materials]
        delete_faces(bpy, np, lo_, np.array([lz[i] in DELETE_ZONES for i in poly_mats(np, lo_.data)], bool))
        triangulate(bpy, lo_)
        n0 = tri_count(lo_)
        decimate_object(bpy, lo_, int(job.get("lash_tris", 150)))
        cleanup_weights(np, lo_)
        lo_.data.polygons.foreach_set("use_smooth", [True] * len(lo_.data.polygons))
        lo_.name = lo_.data.name = "_ciglia_base"
        lashes_base = lo_
        log("ciglia: %d -> %d triangoli (trasparenti, si muovono con le palpebre)" % (n0, tri_count(lo_)))

    # --- corpo: zone, pulizia, riduzione
    me = body.data
    zones = [zone_name(m.name if m else "") for m in me.materials]
    zid = lambda names: {i for i, z in enumerate(zones) if z in names}
    pm = poly_mats(np, me)
    keep_teeth = bool(job.get("keep_teeth", False))
    DZ = tuple(z for z in DELETE_ZONES if not (keep_teeth and z == "Teeth"))
    n = delete_faces(bpy, np, body, np.isin(pm, list(zid(DZ))))
    log("tolti %seye moisture e cornea (%d facce)" % ("" if keep_teeth else "denti, ", n))
    if job.get("mirror_limbs", True):
        ok, ko = mirror_limb_uvs(np, body, zid(("Arms", "Legs")))
        log("braccio e gamba destri sulla texture dei sinistri: %d facce (%d senza corrispondenza)" % (ok, ko))
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    pm = poly_mats(np, me)
    cen = np.zeros(len(me.polygons) * 3)
    me.polygons.foreach_get("center", cen)
    cen = cen.reshape(-1, 3)
    scl = np.isin(pm, list(zid(("Sclera",))))
    eyes = {}
    for side in (1, -1):
        sel = scl & (np.sign(cen[:, 0]) == side)
        if sel.any():
            vv = np.unique([v for p in np.nonzero(sel)[0] for v in me.polygons[p].vertices])
            c = co[vv].mean(0)
            eyes[side] = (c, float(np.linalg.norm(co[vv] - c, axis=1).max()))
    dele = np.zeros(len(pm), bool)
    eye_ids = zid(("Sclera", "Irises", "Pupils"))
    sock_ids = zid(("EyeSocket",))
    for i in range(len(pm)):
        side = 1 if cen[i, 0] >= 0 else -1
        if side not in eyes:
            continue
        c, r = eyes[side]
        if pm[i] in eye_ids and cen[i, 2] < c[2] - 0.05 * r:
            dele[i] = True
        elif pm[i] in sock_ids and abs(cen[i, 0]) > abs(c[0]) - 0.3 * r:
            dele[i] = True
    n = delete_faces(bpy, np, body, dele)
    log("occhi: tolta la parte dietro; eyesocket: tenuti solo gli angoli verso il naso (%d facce tolte)" % n)
    triangulate(bpy, body)
    with EditMode(bpy, body):
        bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.mesh.remove_doubles(threshold=0.0005)
    hi = duplicate(bpy, body, "_originale")
    T = body_arrays(np, hi)                           # testa e spalle per adattare i capelli
    known = set()
    groups = []
    for part, zn in PARTS + ([("teeth", ("Teeth",))] if keep_teeth else []):
        ids = zid(zn)
        known |= ids
        groups.append((part, ids))
    if keep_teeth:
        t["teeth"] = int(job.get("teeth_tris", 200))
    extra = set(range(len(zones))) - known - zid(DZ)
    if extra:
        log("zone in piu' nel corpo, messe con il corpo: %s" % ", ".join(sorted({zones[i] for i in extra})))
        groups = [(p, ids | extra) if p == "body" else (p, ids) for p, ids in groups]
    feet_nodes = [BONE_ORDER.index("Node6"), BONE_ORDER.index("Node9")]

    def feet_faces(ids):
        dom = get_node_weights(np, body).argmax(1)
        isf = np.isin(dom, feet_nodes)
        zm = np.isin(poly_mats(np, me), list(ids))
        cnt = np.array([sum(isf[v] for v in p.vertices) for p in me.polygons])
        return zm & (cnt >= 2)
    tot_base = 0
    for part, ids in groups:
        cur = int(np.isin(poly_mats(np, me), list(ids)).sum())
        if cur == 0:
            continue
        if part == "body":
            fm = lambda: feet_faces(ids)
            rm = lambda: np.isin(poly_mats(np, me), list(ids)) & ~feet_faces(ids)
            for lab, mf, tg in (("piedi", fm, int(t.get("feet", 800))), ("corpo", rm, int(t["body"]))):
                c0 = int(mf().sum())
                c1 = decimate_mask(bpy, np, body, mf, tg) if tg < c0 else c0
                tot_base += c1
                log("%-9s %5d -> %5d triangoli (obiettivo %d)" % (lab, c0, c1, tg))
            continue
        if part == "eyes" and "eyes" not in t:
            tg = int(cur * float(t.get("eyes_ratio", 0.85)))
        else:
            tg = int(t.get(part, cur))
        new = decimate_zone(bpy, np, body, ids, tg) if tg < cur else cur
        tot_base += new
        log("%-9s %5d -> %5d triangoli (obiettivo %d)%s" % (ZONE_LABEL.get(part, part), cur, new, tg,
            "  [i bordi con le zone vicine restano fermi]" if new > tg * 1.1 else ""))
    parts = separate_parts(bpy, np, body, groups)
    hiparts = separate_parts(bpy, np, hi, [("_hi_" + p, ids) for p, ids in groups])
    for p, o in parts.items():
        clean_unused_materials(o)
        src = hiparts.get("_hi_" + p)
        if src is not None:
            transfer_normals(bpy, o, src)
        cleanup_weights(np, o)
    for o in hiparts.values():
        bpy.data.objects.remove(o, do_unlink=True)
    # denti: uniti alla bocca (stessa mesh, texture nell'atlas del corpo); pesi gia' giusti dalla tabella DAZ:
    # arcata superiore sulla testa (Node21), inferiore e lingua sulla mascella (Node27)
    if "teeth" in parts:
        th = parts.pop("teeth")
        if "mouth" in parts:
            mo = parts["mouth"]
            with bpy.context.temp_override(object=mo, active_object=mo, selected_objects=[mo, th],
                                           selected_editable_objects=[mo, th]):
                bpy.ops.object.join()
        else:
            parts["mouth"] = th
        log("denti uniti alla bocca: %d triangoli" % tri_count(parts["mouth"]))
    # --- capelli: ogni outfit ha i suoi (o nessuno); nell'atlas del corpo c'e' uno spazio fisso per loro
    legacy = hair_cfg_from_job(job)
    outfits_run = outfits or [{"name": "base", "garments": [], "mesh1": "", "tris": 0, "cull_body": False}]
    for of in outfits_run:
        if "hair" not in of and legacy:
            of["hair"] = dict(legacy)
    any_hair = any((of.get("hair") or {}).get("lib") for of in outfits_run)
    size_b = int(job.get("atlas_base", 512))
    reserve = None
    if any_hair:
        reserve = (int(job.get("hair_slot") or round(size_b * 0.33)), None)
    elif int(job.get("hair_reserve", 0)) > 0:
        rimg = None
        if job.get("hair_tex"):
            try:
                rimg = read_png_rgb(job["hair_tex"])
            except Exception as e:
                warn("texture capelli non letta (%s)" % e)
        reserve = (int(job["hair_reserve"]), rimg)
    # --- atlas del corpo (base comune) e maschere di iride, labbra, unghie, trucco
    base_objs = [parts[p] for p in ("face", "body", "ears", "eyes", "nails", "eyesocket", "mouth") if p in parts]
    zones_of = {o.name: poly_zones(o) for o in base_objs}
    import tempfile
    tmpd = tempfile.mkdtemp(prefix="daz2ob_")
    # le ciglia (uguali per tutti gli outfit) stanno nell'atlas del corpo: una texture in meno in memoria.
    # L'atlas ha l'alpha solo sulle ciglia; il loro materiale "trasparente" usa la stessa immagine.
    for o in base_objs:
        o["_opaque"] = True
    if lashes_base is not None:
        lashes_base["_opacity"] = 1.0
        lashes_base["_alpha_boost"] = 4.0          # peli sottili: rimpiccioliti sparirebbero
    lash_z = {zone_name(m.name if m else "") for m in lashes_base.data.materials} if lashes_base is not None else set()
    brows = job.get("brows") or {}
    bmode = brows.get("mode", "no")
    bamt = float(brows.get("amount", 50))
    if bmode == "atlas" and parts.get("face") is not None:
        bf = 1.0 + 2.0 * bamt / 100.0                 # 0 -> 1x, 50 -> 2x, 100 -> 3x
        nb = brows_own_piece(bpy, np, parts["face"], bf)
        log("sopracciglia: pezzo proprio nell'atlas a %.1fx la risoluzione della faccia (%d facce)" % (bf, nb))
    ab = build_atlas(bpy, np, base_objs + ([lashes_base] if lashes_base is not None else []), size_b,
                     os.path.join(tmpd, "base.png"), "%s_corpo_base" % name,
                     imp_of=lambda z: 2.5 if z in lash_z else IMPORTANCE.get(z, 1.0), reserve=reserve, ambient=amb,
                     alpha=lashes_base is not None)
    base_alpha = ab["rgba"][..., 3] if "rgba" in ab else None
    log("atlas corpo %dx%d: %d pezzi%s" % (size_b, size_b, ab["pieces"], ", con le ciglia (alpha)" if base_alpha is not None else ""))
    if "reserve_px" in ab:
        x, y, w, h = ab["reserve_px"]
        log("spazio per i capelli nell'atlas: x %d, y %d, %dx%d pixel (origine in alto a sinistra)" % (x, y, w, h))
    MV, MF, MUV, MZ = mesh_arrays(np, base_objs, zones_of)
    eyes = eye_centers(np, MV, MF, MZ)
    masks = region_masks(np, size_b, MV, MF, MUV, MZ, eyes)
    LID = lid_weights(np, base_objs)
    if bmode == "rinforza" and parts.get("face") is not None and bamt > 0:
        FV, FF, FUV, _ = mesh_arrays(np, [parts["face"]])
        bw = brow_vertex_weight(np, parts["face"])
        bm = raster_mask(np, size_b, FUV, bw[FF])
        ab["rgb"] = enhance_brows(np, ab["rgb"], bm, bamt)
        if "rgba" in ab:
            ab["rgba"][..., :3] = ab["rgb"]
        log("sopracciglia rinforzate (%d%%): %d pixel" % (bamt, int((bm > 0.5).sum())))
    base_rgb = ab["rgb"]
    texmap = {}
    dummy = make_dummy(bpy, np, ab["material"])

    # --- armatura Outbreak e outfit
    oarm = build_armature(bpy)
    base_order = [("face", parts.get("face")), ("MESH1", dummy), ("body", parts.get("body")),
                  ("ears", parts.get("ears")), ("eyes", parts.get("eyes")), ("nails", parts.get("nails")),
                  ("eyesocket", parts.get("eyesocket")), ("mouth", parts.get("mouth"))]
    results = []
    limit = int(job.get("budget_limit", 0) or 0)
    margin = float(job.get("margin_mm", 3.0)) / 10.0
    hair_cache = {}
    root_out = outdir
    return dict(locals())


def _convert_outfit(ctx, of, export=True):
    """Un outfit sulla base gia' pronta (_convert_base). export=False: niente FBX, ritorna i dati per
    l'anteprima 3D (mesh finali e pelle tolta)."""
    bpy, np, job = ctx["bpy"], ctx["np"], ctx["job"]
    LID, T, ab, base_order, base_rgb = ctx["LID"], ctx["T"], ctx["ab"], ctx["base_order"], ctx["base_rgb"]
    dummy, garments, hair_cache, lashes_base = ctx["dummy"], ctx["garments"], ctx["hair_cache"], ctx["lashes_base"]
    masks, name, oarm, parts, size_b, texmap = ctx["masks"], ctx["name"], ctx["oarm"], ctx["parts"], ctx["size_b"], ctx["texmap"]
    base_alpha = ctx.get("base_alpha")
    sp = job.get("specks") or {}
    SPECKS[:] = [bool(sp.get("on", True)), int(sp.get("tris", 3)), float(sp.get("area", 0.5))]
    amb = int(job.get("ambient", 20))
    limit = int(job.get("budget_limit", 0) or 0)
    margin = float(job.get("margin_mm", 3.0)) / 10.0
    root_out = job["outdir"]
    if job.get("eyes_color") != ctx.get("eyes_done"):
        ctx["base_rgb_eyes"] = apply_looks(np, base_rgb, masks, {"iris": job["eyes_color"]}) if job.get("eyes_color") else base_rgb
        ctx["eyes_done"] = job.get("eyes_color")
        if job.get("eyes_color"):
            log("occhi ricolorati (per tutto il personaggio)")
    base_rgb = ctx.get("base_rgb_eyes", base_rgb)
    oname = safe_name(of.get("name", "outfit"))
    outdir = os.path.join(root_out, oname) if job.get("outfit_folders") else root_out
    os.makedirs(outdir, exist_ok=True)
    glist = [g for g in of.get("garments", []) if g in garments]
    m1 = of.get("mesh1") or ""
    if m1 and m1 in garments and m1 not in glist:
        glist.append(m1)
    log("=" * 60)
    log("outfit '%s': %s" % (oname, ", ".join(glist) or "(nessun capo)"))
    temp = []
    removed = []
    copies = {}
    lens_objs = {}
    glive = None
    pc = ctx.setdefault("pc", {})                       # anteprima: pezzi finiti riusabili al prossimo aggiornamento
    hitA = False
    keyA = None
    m1_used = False
    transp = {g: float(v) for g, v in (of.get("transparent") or {}).items() if g in glist}
    no_cull = set(of.get("no_cull") or [])
    tp = max(5.0, min(100.0, float(of.get("total_pct", 100.0) or 100.0))) / 100.0   # riduzione totale dell'outfit
    if tp < 0.999:
        log("  riduzione totale dell'outfit: %d%% di tutte le mesh" % round(tp * 100))
    if glist:
        srcs = [garments[g] for g in glist]
        budget = int(of.get("tris", 3000))
        sh = of.get("shares") or {}
        shares = [float(sh.get(g, 100.0 / len(glist))) for g in glist]
        gt = of.get("gtris") or {}
        if gt and all(g in gt for g in glist):            # lavori salvati con la 2.1
            alloc = [min(int(gt[g]), tri_count(garments[g])) for g in glist]
            shares = [100.0 * a / max(1, sum(alloc)) for a in alloc]
        else:
            alloc = split_budget(np, srcs, budget, shares)
        if tp < 0.999:
            alloc = [max(20, int(a * tp)) for a in alloc]
        gcache = ctx.setdefault("gcache", {})            # capi gia' ridotti (anteprima: si riusano)
        styles = garment_styles(of)
        bodyp = [o for o in (parts.get("body"), parts.get("face")) if o is not None]
        # anteprima: se nulla dei capi e' cambiato (si sono toccati solo capelli, colori, corpo...) si riusano
        # i capi finiti e il loro atlas dell'aggiornamento precedente
        keyA = json.dumps([oname, glist, [int(a) for a in alloc], of.get("lenses"), {g: (styles.get(g) or {}).get("tex")
                           for g in glist}, of.get("adjust"), bool(job.get("weights_from_body", True)),
                           rigid_garments(job), of.get("rigid"), of.get("rigid_bone"), transp, of.get("layers"),
                           sorted(no_cull), cull_margins(of), margin, int(job.get("atlas_outfit", 256)), tp, list(SPECKS)],
                          sort_keys=True, default=str)
        hitA = (not export and pc.get("A_key") == keyA and
                all(o_.name in bpy.data.objects for o_ in pc["A"]["objs"]))
        if hitA:
            for g in glist:
                copies[g] = duplicate(bpy, pc["A"]["copies"][g], "_g_" + safe_name(g))
                temp.append(copies[g])
                if g in pc["A"]["lens"]:
                    lens_objs[g] = duplicate(bpy, pc["A"]["lens"][g], "_lenti_" + safe_name(g))
                    temp.append(lens_objs[g])
            for rc, owner in pc["A"]["removed"]:
                removed.append((duplicate(bpy, rc, rc.name.replace("_pc_", "_")), copies[owner]))
            log("  capi uguali all'aggiornamento di prima: riusati (%s)" % ", ".join(glist))
        for g, src, tg, q in ([] if hitA else zip(glist, srcs, alloc, shares)):
            lmode = (of.get("lenses") or {}).get(g, "trasparenti")
            ck = (g, int(tg), lmode)
            hit = gcache.get(ck)
            if hit is not None and hit[0].name in bpy.data.objects:
                c = duplicate(bpy, hit[0], "_g_" + safe_name(g))
                lc = duplicate(bpy, hit[1], "_lenti_" + safe_name(g)) if hit[1] is not None else None
                before, after = hit[2], hit[3]
            else:
                c = duplicate(bpy, src, "_g_" + safe_name(g))
                lc = None
                lm = lens_materials(c)
                if lm and lmode != "opache":
                    isl = np.isin(poly_mats(np, c.data), list(lm))
                    if lmode == "trasparenti" and isl.any():
                        lc = duplicate(bpy, c, "_lenti_" + safe_name(g))
                        delete_faces(bpy, np, lc, ~isl)
                        nl0 = tri_count(lc)
                        decimate_object(bpy, lc, max(40, min(nl0, int(tg * 0.15))))
                        lc["_opacity"] = max(0.15, min(1.0, min(lm.values())))
                        lc["_opaque"] = False
                        log("  %s: lenti trasparenti al %d%% (%d -> %d triangoli)" % (g, 100 * lc["_opacity"], nl0, tri_count(lc)))
                    n_l = delete_faces(bpy, np, c, isl)
                    if lmode == "togli":
                        log("  %s: lenti tolte (%d facce)" % (g, n_l))
                before = tri_count(c)
                after = decimate_object(bpy, c, tg)
                transfer_normals(bpy, c, src)
                if len(gcache) > 60:
                    for k_, v_ in list(gcache.items()):
                        for ob_ in v_[:2]:
                            if ob_ is not None and ob_.name in bpy.data.objects:
                                bpy.data.objects.remove(ob_, do_unlink=True)
                    gcache.clear()
                gcache[ck] = (duplicate(bpy, c, "_cache_" + safe_name(g)),
                              duplicate(bpy, lc, "_cache_l_" + safe_name(g)) if lc is not None else None, before, after)
            temp.append(c)
            specks_log(g, remove_specks(bpy, np, c))
            if lc is not None:
                remove_specks(bpy, np, lc)
            gst = styles.get(g) or {}
            if gst.get("tex"):
                if os.path.isfile(gst["tex"]):
                    garment_texture(bpy, c, gst["tex"])
                    log("  %s: texture %s" % (g, os.path.basename(gst["tex"])))
                else:
                    log("  %s: ATTENZIONE texture non trovata (%s), uso l'originale" % (g, gst["tex"]))
            # ritocco a mano dopo la riduzione: spostare un capo non rifa' la riduzione
            adj = (of.get("adjust") or {}).get(g)
            for ob_ in (c, lc):
                if ob_ is None:
                    continue
                adjust_garment(np, ob_, adj)
                ob_["_adjkey"] = "g:" + g
                if job.get("weights_from_body", True) and g not in rigid_garments(job):
                    weights_from_body(np, ob_, bodyp)
                rb = (of.get("rigid_bone") or {}).get(g)
                if rb in BONE_ORDER and g in (of.get("rigid") or []):
                    W1 = np.zeros((len(ob_.data.vertices), len(BONE_ORDER)), np.float32)
                    W1[:, BONE_ORDER.index(rb)] = 1.0          # tutto il capo al 100% su quell'osso
                    set_node_groups(np, ob_, W1)
                    if ob_ is c:
                        log("  %s: legato al 100%% a %s (%s)" % (g, rb, NODE_LABELS.get(rb, "")))
                cleanup_weights(np, ob_)
            if lc is not None:
                temp.append(lc)
                lens_objs[g] = lc
            copies[g] = c
            log("  %-28s %3.0f%%  %6d -> %5d triangoli%s%s" % (g[:28], q, before, after,
                "  trasparente %d%%" % transp[g] if g in transp else "", "  (gia' ridotto)" if hit is not None else ""))
        # strati: dall'interno all'esterno (dalla finestra, o per distanza dalla pelle)
        order = [g for g in (of.get("layers") or []) if g in copies]
        order += sorted([g for g in glist if g not in order], key=lambda g: garment_depth(np, copies[g], parts))
        if len(order) > 1 and not hitA:
            log("  strati (dall'interno): %s" % " < ".join(order))
            for i, g in enumerate(order[:-1]):
                outer = [copies[x] for x in order[i + 1:] if x not in transp]
                if not outer:
                    continue
                room = np.full(len(copies[g].data.vertices), 1.0)
                _, pushed = skin_vs_garments(np, copies[g], outer, margin, room)
                skin_vs_garments(np, copies[g], outer, margin, room)
                cutters = [copies[x] for x in order[i + 1:] if x not in transp and x not in no_cull]
                cut = 0
                if cutters:
                    mask = skin_cull_mask(np, copies[g], cutters, None, cull_margins(of))
                    if not export and mask.any():
                        removed.append((removed_copy(bpy, np, copies[g], mask, "_tolto_" + safe_name(g)), copies[g]))
                    cut = delete_faces(bpy, np, copies[g], mask)
                if pushed or cut:
                    log("  %s sotto gli strati esterni: %d vertici spinti, %d facce nascoste tolte" % (g, pushed, cut))
    # vestiti: opachi e trasparenti nello stesso atlas (alpha solo sui trasparenti, che hanno un loro
    # materiale "trasparente" sulla stessa immagine, come in 3ds Max); mesh trasparenti in fondo
    trans_objs = []
    if glist:
        for g in glist:
            if g in transp:
                copies[g]["_opacity"] = max(0.0, min(1.0, transp[g] / 100.0))
                copies[g]["_opaque"] = False
                trans_objs.append(copies[g])
            else:
                copies[g]["_opaque"] = True
        trans_objs += [lens_objs[g] for g in glist if g in lens_objs]
        if hitA:
            glive = pc["A"]["glive"]
            texmap.update(pc["A"]["tex"])
        else:
            size_o = int(job.get("atlas_outfit", 256))
            png_o = os.path.join(outdir, "%s_%s_vestiti.png" % (name, oname))
            gobj = {g: [copies[g].name] + ([lens_objs[g].name] if g in lens_objs else []) for g in glist}
            recol = {} if not export else {nm: styles[g]["color"] for g in glist if (styles.get(g) or {}).get("color")
                                           for nm in gobj[g]}
            ao = build_atlas(bpy, np, [copies[g] for g in glist] + [lens_objs[g] for g in glist if g in lens_objs],
                             size_o, png_o, "%s_%s" % (name, oname), ambient=amb,
                             alpha=bool(trans_objs), per_object=True, recolor=recol, want_masks=not export)
            if recol:
                log("  colori dei capi: %s" % ", ".join(g for g in glist if (styles.get(g) or {}).get("color")))
            if not export:                                    # anteprima: maschere dei capi per i colori nel browser
                gnames = glist[:16]
                gm = np.zeros((size_o, size_o, 3), np.uint8)
                h_, l_, s_ = rgb_to_hls(np, ao["rgb"])
                gmed = []
                for i, g in enumerate(gnames):
                    M = np.zeros((size_o, size_o), bool)
                    for nm in gobj[g]:
                        if nm in ao["objmask"]:
                            M |= ao["objmask"][nm]
                    gm[M, 0] = i + 1
                    gmed.append(float(np.median(l_[M])) if M.any() else 0.5)
                glive = {"m3": gm, "gnames": gnames, "gmed": gmed, "gmats": [ao["material"].name]}
            texmap[ao["material"].name] = ao.get("rgba", ao["rgb"])
            if trans_objs:
                tmat = make_material(bpy, "%s_%s_trasp" % (name, oname), material_image(ao["material"])[0], amb, alpha=True)
                texmap[tmat.name] = ao["rgba"]
                if glive:
                    glive["gmats"].append(tmat.name)
                for o in trans_objs:
                    o.data.materials.clear()
                    o.data.materials.append(tmat)
            log("  atlas vestiti %dx%d: %d pezzi%s -> %s" % (size_o, size_o, ao["pieces"],
                " (con alpha sui capi trasparenti)" if trans_objs else "", os.path.basename(png_o)))
            if not export:                                # da riusare al prossimo aggiornamento
                for o_ in pc.get("A", {}).get("objs", []):
                    if o_.name in bpy.data.objects:
                        bpy.data.objects.remove(o_, do_unlink=True)
                keep = {"copies": {}, "lens": {}, "removed": [], "objs": [], "glive": glive,
                        "tex": {k_: texmap[k_] for k_ in [ao["material"].name] + ([tmat.name] if trans_objs else [])}}
                for g in glist:
                    keep["copies"][g] = duplicate(bpy, copies[g], "_pc_g_" + safe_name(g))
                    keep["objs"].append(keep["copies"][g])
                    if g in lens_objs:
                        keep["lens"][g] = duplicate(bpy, lens_objs[g], "_pc_l_" + safe_name(g))
                        keep["objs"].append(keep["lens"][g])
                for rc, owner in removed:
                    og = next((g for g in copies if copies[g] is owner), None)
                    if og is not None:
                        d_ = duplicate(bpy, rc, "_pc_" + rc.name.lstrip("_"))
                        keep["removed"].append((d_, og))
                        keep["objs"].append(d_)
                pc["A"], pc["A_key"] = keep, keyA
    lash_copy = None
    if lashes_base is not None:
        lash_copy = duplicate(bpy, lashes_base, "_ciglia")
        temp.append(lash_copy)
        if tp < 0.999:
            decimate_object(bpy, lash_copy, max(20, int(tri_count(lash_copy) * tp)))
        trans_objs.append(lash_copy)
    # capelli dell'outfit
    hcfg = of.get("hair") or {}
    # anteprima 3D: colori (occhi, labbra, unghie, trucco, capelli) applicati dal browser in tempo reale:
    # qui la texture resta senza colori e si mandano le maschere delle zone
    live = not export
    hmask = np.zeros((size_b, size_b), np.float32) if live else None
    hcfg_t = dict(hcfg, total_pct=tp * 100.0)
    hair = build_hair(bpy, np, dict(hcfg_t, color=None) if live else hcfg_t, T, hair_cache) if hcfg.get("lib") else None
    rgb = (ctx["base_rgb"] if live else base_rgb).copy()
    if hair is not None:
        temp.append(hair)
        rx, ry, rs = ab["reserve_xy"]
        hp = build_atlas(bpy, np, [hair], size_b, None, None, imp_of=lambda z: 1.0, region=(rx, ry, rs))
        rgb[size_b - ry - rs:size_b - ry, rx:rx + rs] = hp["patch"]
        if live:
            hmask[size_b - ry - rs:size_b - ry, rx:rx + rs] = 1.0
        log("  capelli %s: %s%s" % (os.path.splitext(os.path.basename(hcfg["lib"]))[0], hair["_hair_info"],
                                    ", colore cambiato" if hcfg.get("color") else ""))
        if scalp_mode(hcfg) == "colora":
            sm = scalp_paint(np, [o for o in (parts.get("face"), parts.get("body")) if o is not None], hair, T, size_b)
            if sm.any():
                pat = hp["patch"].reshape(-1, 3).astype(np.float32)
                hcol = np.median(pat, 0) * 0.8                   # sotto le ciocche: un po' in ombra
                rgb = np.clip(rgb * (1 - sm[..., None]) + hcol * sm[..., None], 0, 255).astype(np.uint8)
                log("  pelle della testa sotto i capelli colorata come i capelli (%d pixel)" % int((sm > 0.5).sum()))
                if live:
                    hmask = np.maximum(hmask, sm)
    looks = of.get("looks") or {}
    live_info = None
    if live:
        ext = float((looks.get("makeup") or {}).get("ext", 0))
        ck = ("_mkc", ext)
        if ck not in masks:
            masks[ck] = makeup_mask(np, masks, LID, ext / 100.0)
        chans = [masks.get("lips"), masks.get("nails"), masks[ck], masks.get("iris")]
        z = np.zeros((size_b, size_b), np.float32)
        mka = np.stack([c if c is not None else z for c in chans], axis=2)
        h_, l_, s_ = rgb_to_hls(np, rgb[..., :3])
        med = {}
        for key, m in (("lips", chans[0]), ("nails", chans[1]), ("makeup", chans[2]), ("iris", chans[3]), ("hair", hmask)):
            sel = m > 0.004 if m is not None else None
            med[key] = float(np.median(l_[sel])) if sel is not None and sel.any() else 0.5
        if hair is not None and hair.get("_hair_med") is not None:
            med["hair"] = float(hair["_hair_med"])
        live_info = {"m1": (np.clip(mka, 0, 1) * 255 + 0.5).astype(np.uint8),
                     "m2": (np.clip(np.stack([hmask, z, z], axis=2), 0, 1) * 255 + 0.5).astype(np.uint8), "med": med}
        if glive:
            live_info.update(glive)
    elif any(looks.get(k) for k in ("lips", "nails", "makeup")):
        rgb = apply_looks(np, rgb, masks, {k: looks.get(k) for k in ("lips", "nails", "makeup")}, LID)
        log("  colori: %s" % ", ".join(lab for k, lab in (("lips", "labbra"), ("nails", "unghie"),
                                                           ("makeup", "trucco occhi")) if looks.get(k)))
    png_b = os.path.join(outdir, "%s_%s_corpo.png" % (name, oname))
    if base_alpha is not None:
        rgb = np.concatenate([rgb[..., :3], base_alpha[..., None]], axis=2)
    write_png(png_b, rgb)
    bimg = bpy.data.images.load(png_b)
    omat = make_material(bpy, "%s_%s_corpo" % (name, oname), bimg, amb)
    texmap[omat.name] = rgb
    if lash_copy is not None:
        lmat = make_material(bpy, "%s_%s_corpo_trasp" % (name, oname), bimg, amb, alpha=True)
        texmap[lmat.name] = rgb
        lash_copy.data.materials.clear()
        lash_copy.data.materials.append(lmat)
    final = []
    for key, src in base_order:
        if key == "MESH1":
            if m1 and m1 in copies and m1 not in transp:
                final.append(copies[m1])
                m1_used = True
            else:
                c = duplicate(bpy, dummy, "_dummy")
                temp.append(c)
                final.append(c)
            continue
        if src is None or not len(src.data.polygons):
            continue
        keyB = None
        if key == "body" and not export and not (hair is not None and scalp_mode(hcfg) == "togli"):
            # corpo dopo pelle spinta, pulizia e riduzione: dipende solo dai capi e da queste impostazioni
            keyB = json.dumps([keyA, of.get("body_tris"), of.get("cull_body", True), of.get("cull_zones"),
                               cull_margins(of), margin, tp], sort_keys=True, default=str)
            if pc.get("B_key") == keyB and all(o_.name in bpy.data.objects for o_ in pc["B"]["objs"]):
                c = duplicate(bpy, pc["B"]["c"], "_b_body")
                temp.append(c)
                for rc in pc["B"]["removed"]:
                    removed.append((duplicate(bpy, rc, "_tolta_pelle"), c))
                log("  corpo uguale all'aggiornamento di prima: riusato (%d triangoli)" % tri_count(c))
                final.append(c)
                continue
        ftg = None
        if key == "face" and of.get("face_tris"):
            ftg = int(of["face_tris"])
        if key != "body" and (tp < 0.999 or (ftg is not None and ftg < tri_count(src) * 0.97)):
            # parte ridotta per questo outfit (faccia: cursore; tutte: riduzione totale), tenuta in memoria
            tcache = ctx.setdefault("tcache", {})
            tk_ = (key, round(tp, 3), ftg)
            hit = tcache.get(tk_)
            if hit is None or hit.name not in bpy.data.objects:
                hit = duplicate(bpy, src, "_cache_t_" + key)
                n0 = tri_count(hit)
                n1 = decimate_inside(bpy, np, hit, max(12, int(min(n0, ftg or n0) * tp)))
                transfer_normals(bpy, hit, src)
                if len(tcache) > 40:
                    for o_ in tcache.values():
                        if o_.name in bpy.data.objects:
                            bpy.data.objects.remove(o_, do_unlink=True)
                    tcache.clear()
                tcache[tk_] = hit
                log("  %s: %d -> %d triangoli" % (ZONE_LABEL.get(key, key), n0, n1))
            c = duplicate(bpy, hit, "_b_" + key)
        else:
            c = duplicate(bpy, src, "_b_" + key)
        temp.append(c)
        if job.get("face_expr") and key != "body" and apply_face_expression(np, c, job["face_expr"]) and key == "face":
            log("  espressione neutra: %s" % ", ".join("%s %+.1f mm" % (k_, float(v_)) for k_, v_ in job["face_expr"].items()))
        if key in ("face", "body") and hair is not None and scalp_mode(hcfg) == "togli":
            n = scalp_cull(bpy, np, [c], hair, T)
            if n:
                log("  %s: tolte %d facce di pelle coperte dai capelli" % ("faccia" if key == "face" else "corpo", n))
        if key == "body" and copies:
            solid = [copies[g] for g in glist if g not in transp]
            room = np.full(len(c.data.vertices), 1.2)
            pushed = 0
            if solid:
                _, pushed = skin_vs_garments(np, c, solid, margin, room)
                for _ in range(2):
                    _, p2 = skin_vs_garments(np, c, solid, margin, room)
                    if not p2:
                        break
            log("  pelle spinta sotto i vestiti: %d vertici (margine %.1f mm, massimo 12 mm)" % (pushed, margin * 10))
            cutters = [copies[g] for g in glist if g not in transp and g not in no_cull]
            if of.get("cull_body", True) and cutters:
                zones = of.get("cull_zones") or {}
                allowed = [z for z in ("neck", "torso", "arms", "legs", "feet") if zones.get(z, True)]
                mask = skin_cull_mask(np, c, cutters, allowed, cull_margins(of))
                if not export and mask.any():
                    removed.append((removed_copy(bpy, np, c, mask, "_tolta_pelle"), c))
                n = delete_faces(bpy, np, c, mask)
                cm = cull_margins(of)
                log("  corpo nascosto sotto i vestiti: tolte %d facce (zone e bordo: %s)" % (
                    n, ", ".join("%s %.1f cm" % (ZONE_NAMES_IT[z], cm[z]) for z in allowed) or "nessuna"))
        if key == "body":
            # triangoli del corpo di questo outfit: contano la pelle rimasta visibile (dopo la pulizia)
            bt = of.get("body_tris")
            if bt is None:
                tt = ctx["t"]
                bt = int(job.get("targets", {}).get("body", tt.get("body", 0))) + int(job.get("targets", {}).get("feet", tt.get("feet", 0)))
            bt = max(200, int(int(bt) * tp))
            n0 = tri_count(c)
            if n0 > bt * 1.03:
                n1 = decimate_inside(bpy, np, c, bt)
                transfer_normals(bpy, c, src)
                log("  corpo dell'outfit (pelle visibile): %d -> %d triangoli (obiettivo %d)" % (n0, n1, bt))
            else:
                log("  corpo dell'outfit (pelle visibile): %d triangoli (obiettivo %d)" % (n0, bt))
            if keyB is not None:
                for o_ in pc.get("B", {}).get("objs", []):
                    if o_.name in bpy.data.objects:
                        bpy.data.objects.remove(o_, do_unlink=True)
                kb = {"c": duplicate(bpy, c, "_pc_body"), "removed": []}
                for rc, owner in removed:
                    if owner is c:
                        kb["removed"].append(duplicate(bpy, rc, "_pc_tolta_pelle"))
                kb["objs"] = [kb["c"]] + kb["removed"]
                pc["B"], pc["B_key"] = kb, keyB
        final.append(c)
    if hair is not None:
        final.append(hair)
    for o in final:
        if o.data.materials and o.data.materials[0].name.startswith("%s_corpo_base" % name):
            o.data.materials[0] = omat
        elif o is hair:
            o.data.materials.clear()
            o.data.materials.append(omat)
            o.data.polygons.foreach_set("material_index", [0] * len(o.data.polygons))
    # capi nell'ordine dell'elenco della finestra (strati, frecce), trasparenti compresi; ciglia in fondo
    lay = [g for g in (of.get("layers") or []) if g in glist]
    lay += [g for g in glist if g not in lay]
    for g in lay:
        if not (m1_used and g == m1):
            final.append(copies[g])
        if g in lens_objs:
            final.append(lens_objs[g])
    if lash_copy is not None:
        final.append(lash_copy)
    LAB = {"_b_face": "faccia", "_b_body": "corpo", "_b_ears": "orecchie", "_b_eyes": "occhi", "_b_nails": "unghie",
           "_b_eyesocket": "eyesocket", "_b_mouth": "bocca", "_dummy": "segnaposto", "_ciglia": "ciglia"}
    for o in final:
        base = o.name.split(".")[0]
        lab = LAB.get(base) or ("capelli" if o is hair else next((g for g in copies if copies[g] is o), None) or
                                next((g + " (lenti)" for g in lens_objs if lens_objs[g] is o), base))
        o["_label"] = lab
    for i, o in enumerate(final):
        o.name = "Mesh%d" % i
        o.data.name = "Mesh%d" % i
        attach(o, oarm)
    out = os.path.join(outdir, "%s_%s.fbx" % (name, oname))
    if not export:
        data = preview_data(bpy, np, final, removed, texmap, outdir, live_info,
                            [omat.name] + ([lmat.name] if lash_copy is not None else []))
        for o in temp + [r for r, _ in removed]:
            if o.name in bpy.data.objects:
                d = o.data
                bpy.data.objects.remove(o, do_unlink=True)
                if d.users == 0:
                    bpy.data.meshes.remove(d)
        return data
    export_fbx(bpy, oarm, final, out, amb)
    tot = 0
    lines = []
    for o in final:
        tr = tri_count(o)
        tot += tr
        lines.append("  %-7s %5d triangoli %5d vertici NBD  %s" % (o.name, tr, nbd_vertex_count(np, o),
                                                                   o.data.materials[0].name if o.data.materials else ""))
    for ln in lines:
        log(ln)
    log("  totale %d triangoli -> %s" % (tot, os.path.basename(out)))
    if limit and tot > limit:
        warn("outfit '%s': %d triangoli, oltre il limite di %d" % (oname, tot, limit))
    if job.get("preview", True):
        try:
            pv = os.path.splitext(out)[0] + "_anteprima.png"
            preview(bpy, np, oarm, final, texmap, pv)
            log("  anteprima -> %s" % os.path.basename(pv))
        except Exception as e:
            import traceback
            traceback.print_exc()
            warn("anteprima non riuscita (%s)" % e)
    with open(os.path.splitext(out)[0] + "_resoconto.txt", "w", encoding="utf-8") as fh:
        fh.write("daz2ob %s - %s\n" % (__version__, os.path.basename(out)))
        fh.write("\n".join(lines) + "\n  totale %d triangoli\n" % tot)
    for o in temp:
        if o.name in bpy.data.objects:
            d = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if d.users == 0:
                bpy.data.meshes.remove(d)
    return out, tot


def removed_copy(bpy, np, obj, mask, name):
    """Copia delle sole facce che stanno per essere tolte (per mostrarle in rosso nell'anteprima 3D)."""
    c = duplicate(bpy, obj, name)
    delete_faces(bpy, np, c, ~np.asarray(mask, bool))
    return c


def preview_data(bpy, np, final, removed, texmap, outdir, live=None, body_mats=()):
    """Mesh finali dell'outfit -> scene.json (intestazione) + scene.bin (dati binari) + texture PNG in outdir,
    per l'anteprima 3D del browser. Coordinate Outbreak (cm, Y su), pesi: le 4 ossa piu' forti per vertice.
    live: maschere e mediane per i colori applicati dal browser in tempo reale (texture del corpo senza colori)."""
    os.makedirs(outdir, exist_ok=True)
    texfiles = {}
    meshes = []
    blob = bytearray()

    def put(a, dt):
        off = len(blob)
        blob.extend(np.ascontiguousarray(a, dt).tobytes())
        while len(blob) % 4:
            blob.append(0)
        return off
    for kind, objs in (("mesh", [(o, None) for o in final]), ("tolta", removed)):
        for o, src in objs:
            me = o.data
            if not len(me.polygons):
                continue
            V, F, UVc, _ = mesh_arrays(np, [o])
            # vertici per angolo (UV diverse sulle cuciture): niente indici condivisi, piu' semplice
            P = V[F].reshape(-1, 3)
            UV = UVc.reshape(-1, 2)
            W = get_node_weights(np, o)
            top = np.argsort(-W, axis=1)[:, :4]
            tw = np.take_along_axis(W, top, 1)
            s = tw.sum(1, keepdims=True)
            s[s <= 0] = 1.0
            tw = tw / s
            J = top[F].reshape(-1, 4) + 1                       # BONE_ORDER[0] = Node1
            JW = tw[F].reshape(-1, 4)
            tex, alpha, body = "", False, False
            mat = me.materials[me.polygons[0].material_index] if me.materials else None
            if kind == "mesh" and mat is not None and mat.name in texmap:
                if mat.name not in texfiles:
                    arr = texmap[mat.name]
                    fn = "t%d.png" % len(texfiles)
                    write_png(os.path.join(outdir, fn), arr)
                    texfiles[mat.name] = (fn, arr.shape[2] == 4 and zone_name(mat.name).endswith("_trasp"))
                tex, alpha = texfiles[mat.name]
                body = mat.name in body_mats
            label = o.get("_label", "")
            extra = {}
            if kind == "mesh" and o.get("_adj") is not None and o.get("_adjkey"):
                extra = {"adj": [float(x) for x in o["_adj"]], "adjkey": str(o["_adjkey"])}
            meshes.append(dict(extra, **{"name": ("%s  %s" % (o.name, label)).strip() if kind == "mesh" else o.name.lstrip("_"),
                           "id": o.name if kind == "mesh" else "", "src": src.name if src is not None else "",
                           "kind": kind, "tex": tex, "alpha": alpha, "body": body, "tris": int(len(F)), "n": int(len(P)),
                           "P": put(P, "<f4"), "UV": put(UV, "<f4"), "J": put(J, "u1"), "W": put(JW, "<f4")}))
    sk = {"pos": [list(SKEL["Node%d" % i]) if i else [0.0, 0.0, 0.0] for i in range(36)],
          "parent": [-1] + [int(PARENTS["Node%d" % i][4:]) if PARENTS["Node%d" % i] else 0 for i in range(1, 36)]}
    head = {"meshes": meshes, "skeleton": sk, "bin": "scene.bin"}
    if live is not None:
        write_png(os.path.join(outdir, "m1.png"), live["m1"])
        write_png(os.path.join(outdir, "m2.png"), live["m2"])
        head["looks"] = {"mask1": "m1.png", "mask2": "m2.png", "med": live["med"]}
        if live.get("m3") is not None:
            write_png(os.path.join(outdir, "m3.png"), live["m3"])
            head["looks"].update({"mask3": "m3.png", "gnames": live["gnames"], "gmed": live["gmed"],
                                  "gtex": [texfiles[m][0] for m in live["gmats"] if m in texfiles]})
    import hashlib                                     # il browser non riscarica le texture uguali a prima
    head["hash"] = {}
    for fn in sorted(set([m["tex"] for m in meshes if m["tex"]] + [v for k, v in (head.get("looks") or {}).items()
                                                                 if k.startswith("mask")])):
        try:
            with open(os.path.join(outdir, fn), "rb") as fh:
                head["hash"][fn] = hashlib.md5(fh.read()).hexdigest()
        except OSError:
            pass
    with open(os.path.join(outdir, "scene.bin"), "wb") as fh:
        fh.write(bytes(blob))
    with open(os.path.join(outdir, "scene.json"), "w", encoding="utf-8") as fh:
        json.dump(head, fh)
    tot = sum(m["tris"] for m in meshes if m["kind"] == "mesh")
    log("anteprima 3D: %d mesh, %d triangoli (%d KB)" % (sum(1 for m in meshes if m["kind"] == "mesh"), tot,
                                                         len(blob) // 1024))
    return {"dir": outdir, "tris": tot}


def base_key(job):
    """Impostazioni che cambiano la base (corpo, ossa, atlas): se uguali, la base in memoria si riusa."""
    skip = ("outfits", "outdir", "name", "preview", "make_nbd", "eyes_color", "budget_limit", "margin_mm", "hairlib",
            "version", "outfit_folders", "atlas_outfit", "atlas_trasp", "collection", "specks", "face_expr")
    k = {a: b for a, b in job.items() if a not in skip}
    gs = set()
    for of in job.get("outfits") or []:
        gs |= set(of.get("garments") or []) | ({of["mesh1"]} if of.get("mesh1") else set())
    k["_capi"] = sorted(gs)
    k["_fbx_t"] = os.path.getmtime(job["fbx"]) if os.path.isfile(job.get("fbx", "")) else 0
    k["_any_hair"] = any((o.get("hair") or {}).get("lib") for o in job.get("outfits") or [])
    k["_rigid"] = rigid_garments(job)
    return json.dumps(k, sort_keys=True, default=str)


def convert(job, mem=None, preview=None):
    """Tutti gli outfit del lavoro -> FBX. mem: memoria del server (la base resta pronta tra una richiesta e
    l'altra); preview: un outfit da calcolare solo per l'anteprima 3D (niente file)."""
    def feet_spec(of):
        if not of.get("flat_feet"):
            return (False, 0.0, 0.0)
        return (True, round(float(of.get("feet_ankle", 0.0)), 1), round(float(of.get("feet_toes", 0.0)), 1))

    def get_base(spec):
        # piede piatto (scarpe chiuse) fa parte della preparazione del corpo: una base per ogni scelta
        jb = dict(job, _flat_feet=bool(spec[0]), _feet_adj=[spec[1], spec[2]] if spec[0] else [0.0, 0.0])
        key = base_key(jb)
        ctx = mem.get("base") if (mem is not None and mem.get("base_key") == key) else None
        if ctx is None and mem is not None and mem.get("base_key"):
            try:                                       # perche' si rifa': cosa e' cambiato dall'ultima volta
                a_, b_ = json.loads(mem["base_key"]), json.loads(key)
                diff = sorted(k_ for k_ in set(a_) | set(b_) if a_.get(k_) != b_.get(k_))
                why = {"_flat_feet": "piede piatto", "_feet_adj": "ritocco del piede", "face_expr": "espressione",
                       "brows": "sopracciglia", "_capi": "capi usati negli outfit", "_any_hair": "capelli si/no",
                       "_rigid": "capi rigidi", "targets": "parti fisse", "_fbx_t": "FBX modificato", "fbx": "FBX"}
                log("preparazione del personaggio di nuovo: cambiato %s" % ", ".join(why.get(k_, k_) for k_ in diff))
            except Exception:
                pass
        if ctx is None:
            if mem is not None:
                mem.pop("base", None)
            ctx = _convert_base(jb)
            if mem is not None:
                mem["base"], mem["base_key"] = ctx, key
        else:
            log("base del personaggio gia' pronta in memoria")
        ctx["job"] = job
        return ctx
    if preview is not None:
        return _convert_outfit(get_base(feet_spec(preview)), preview, export=False)
    results = []
    outs = job.get("outfits") or []
    legacy = hair_cfg_from_job(job)
    for of in outs:
        if "hair" not in of and legacy:
            of["hair"] = dict(legacy)
    if not outs:
        ctx = get_base((False, 0.0, 0.0))
        outs = ctx["outfits_run"]
    flags = []
    for of in outs:                                    # nell'ordine degli outfit (la prima base e' magari gia' pronta)
        if feet_spec(of) not in flags:
            flags.append(feet_spec(of))
    for spec in flags:
        ctx = get_base(spec)
        for of in [o for o in outs if feet_spec(o) == spec]:
            results.append(_convert_outfit(ctx, of, True))
    log("=" * 60)
    log("fatto: %d FBX in %s" % (len(results), job["outdir"]))
    return results

def main_blender(argv):
    try:
        if argv[0] == "--daz2ob-scan":
            scan(argv[1], argv[2])
        elif argv[0] == "--daz2ob-job":
            with open(argv[1], encoding="utf-8") as fh:
                job = json.load(fh)
            convert(job)
        elif argv[0] == "--daz2ob-hairadd":
            hairlib_add(argv[1], argv[2], argv[3], int(argv[4]) if len(argv) > 4 else -1)
        elif argv[0] == "--daz2ob-hairprev":
            with open(argv[1], encoding="utf-8") as fh:
                hair_preview(json.load(fh))
        elif argv[0] == "--daz2ob-hairshell":
            hairshell_add(argv[1], argv[2], argv[3], argv[4], int(argv[5]) if len(argv) > 5 else 3000)
        elif argv[0] == "--daz2ob-lookprev":
            with open(argv[1], encoding="utf-8") as fh:
                look_preview(json.load(fh))
        elif argv[0] == "--daz2ob-server":
            return server()
        return 0
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(TAG + "ERRORE: %s" % e, flush=True)
        return 2


# ================================================================================================
#                                  FUORI DA BLENDER: finestra
# ================================================================================================
SETTINGS = os.path.join(os.path.expanduser("~"), ".daz2ob.json")


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
            return c
    if importlib.util.find_spec("bpy") is not None:
        return "python-bpy"
    return None


def blender_cmd(exe):
    me = os.path.abspath(__file__)
    if exe == "python-bpy":
        return [sys.executable, me]
    return [exe, "-b", "--factory-startup", "--python", me, "--"]


def run_blender(exe, args, on_line):
    """Lancia Blender in background; on_line(testo) per ogni messaggio. -> codice di uscita."""
    flags = 0x08000000 if os.name == "nt" else 0           # niente finestra nera su Windows
    p = subprocess.Popen(blender_cmd(exe) + args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, errors="replace", creationflags=flags)
    tail = []
    for line in p.stdout:
        line = line.rstrip("\n")
        tail = (tail + [line])[-25:]
        if line.startswith(TAG):
            on_line(line[len(TAG):])
    p.wait()
    if p.returncode != 0 and not any(l.startswith(TAG + "ERRORE") for l in tail):
        on_line("ERRORE: Blender si e' chiuso con codice %d. Ultime righe:\n  " % p.returncode + "\n  ".join(tail[-12:]))
    return p.returncode


VIEWER_HTML = r"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>daz2ob anteprima 3D</title>
<style>
  :root { --bg:#1d2026; --panel:#262a32; --line:#3a404b; --text:#e6e8ec; --muted:#9aa2b1; --acc:#e0913a; --red:#e04848; }
  * { box-sizing: border-box; }
  html, body { margin:0; height:100%; background:var(--bg); color:var(--text); font:13px/1.4 system-ui, "Segoe UI", sans-serif; }
  #wrap { display:flex; height:100%; }
  #view { flex:1; position:relative; min-width:0; }
  canvas { width:100%; height:100%; display:block; cursor:grab; }
  canvas:active { cursor:grabbing; }
  #side { width:290px; background:var(--panel); border-left:1px solid var(--line); overflow-y:auto; padding:12px 14px; }
  h1 { font-size:15px; margin:0 0 2px; }
  h2 { font-size:11px; text-transform:uppercase; letter-spacing:.06em; color:var(--muted); margin:16px 0 6px; font-weight:600; }
  #status { color:var(--muted); min-height:18px; }
  #status.busy { color:var(--acc); }
  #status.err { color:var(--red); white-space:pre-wrap; }
  .row { display:flex; align-items:center; gap:6px; margin:3px 0; }
  .row label { flex:1; cursor:pointer; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .row .n { color:var(--muted); font-variant-numeric:tabular-nums; }
  .row.iso label { color:var(--acc); font-weight:600; }
  .row .rem { color:var(--red); font-size:12px; }
  .btns { display:flex; flex-wrap:wrap; gap:5px; }
  button { background:#323844; color:var(--text); border:1px solid var(--line); border-radius:5px; padding:5px 9px; font:inherit; cursor:pointer; }
  button:hover { border-color:var(--acc); }
  button.on { background:var(--acc); color:#1d2026; border-color:var(--acc); }
  .sw { width:10px; height:10px; border-radius:2px; display:inline-block; }
  #hud { position:absolute; left:10px; bottom:8px; color:var(--muted); font-size:12px; pointer-events:none; }
  #big { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; color:var(--muted); font-size:15px; pointer-events:none; text-align:center; padding:20px; }
  input[type=range] { width:100%; }
  @media (max-width:700px) { #wrap { flex-direction:column; } #side { width:auto; height:45%; border-left:0; border-top:1px solid var(--line); } }
</style>
</head>
<body>
<div id="wrap">
  <div id="view"><canvas id="c"></canvas><div id="big">In attesa dell'anteprima dalla finestra di daz2ob...</div>
    <div id="hud">trascina: ruota &nbsp;·&nbsp; rotella: zoom &nbsp;·&nbsp; tasto destro / Maiusc: sposta</div></div>
  <div id="side">
    <h1 id="title">Anteprima 3D</h1>
    <div id="status"></div>
    <h2>Vista</h2>
    <div class="btns">
      <button data-v="front">Davanti</button><button data-v="back">Dietro</button><button data-v="side">Lato</button>
      <button data-v="face">Viso</button><button data-v="arm">Spalla</button><button data-v="hand">Mano</button><button data-v="feet">Piedi</button>
    </div>
    <h2>Mostra</h2>
    <div class="row"><input type="checkbox" id="tex" checked><label for="tex">Texture</label></div>
    <div class="row"><input type="checkbox" id="wire"><label for="wire">Triangoli (wireframe)</label></div>
    <div class="row"><input type="checkbox" id="removed" checked><label for="removed"><span class="sw" style="background:var(--red)"></span> Parti tolte dalla pulizia</label></div>
    <div class="row"><input type="checkbox" id="bones"><label for="bones">Scheletro</label></div>
    <h2>Posa di prova</h2>
    <div class="btns" id="poses"></div>
    <div class="row" style="margin-top:6px"><input type="checkbox" id="anim"><label for="anim">Anima (va e viene dalla T-pose)</label></div>
    <div class="row"><span style="color:var(--muted)">Quanto</span><input type="range" id="amt" min="0" max="100" value="100"></div>
    <h2>Mesh <span id="tot" style="text-transform:none;letter-spacing:0"></span></h2>
    <div style="color:var(--muted);font-size:12px;margin-bottom:6px">Clic sul nome: vedi solo quella mesh e, in rosso, cosa le viene tolto (anche sotto gli altri capi).</div>
    <div id="isobar" style="display:none;margin-bottom:6px">
      <div class="row"><input type="checkbox" id="ghost" checked><label for="ghost">Altre mesh in trasparenza</label></div>
      <button id="showall">Mostra tutto</button>
    </div>
    <div id="meshes"></div>
  </div>
</div>
<script>
"use strict";
const $ = (id) => document.getElementById(id);
const cv = $("c");
const gl = cv.getContext("webgl", { antialias: true, alpha: false });
if (!gl) { $("big").textContent = "Il browser non supporta WebGL."; }

// ------------------------------------------------------------------ shader
function sh(type, src) { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw gl.getShaderInfoLog(s); return s; }
function prog(vs, fs) { const p = gl.createProgram(); gl.attachShader(p, sh(gl.VERTEX_SHADER, vs)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p); if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw gl.getProgramInfoLog(p); return p; }
const P = prog(`
  attribute vec3 pos; attribute vec3 nrm; attribute vec2 uv;
  uniform mat4 mvp; varying vec2 vuv; varying vec3 vn;
  void main(){ vuv = uv; vn = nrm; gl_Position = mvp * vec4(pos, 1.0); }`, `
  precision highp float;
  uniform sampler2D tex; uniform int useTex; uniform vec4 col; uniform vec3 ldir; uniform int alphaTest; uniform float opacity;
  uniform int isBody; uniform sampler2D mk1; uniform sampler2D mk2;
  uniform vec4 lk[5]; uniform vec3 lkh[5];     // colori: acceso, modo (1 = colora), intensita', mediana | tonalita', sat., lum.
  uniform int isGarm; uniform sampler2D mk3; uniform vec4 gk[16]; uniform vec3 gkh[16];   // colori dei capi
  varying vec2 vuv; varying vec3 vn;
  vec3 rgb2hls(vec3 c){
    float mx = max(c.r, max(c.g, c.b)), mn = min(c.r, min(c.g, c.b));
    float l = (mx + mn) * 0.5, d = mx - mn, s = 0.0, h = 0.0;
    if (d > 1e-6) {
      s = l < 0.5 ? d / max(mx + mn, 1e-6) : d / max(2.0 - mx - mn, 1e-6);
      if (mx == c.r) h = mod((c.g - c.b) / d, 6.0); else if (mx == c.g) h = (c.b - c.r) / d + 2.0; else h = (c.r - c.g) / d + 4.0;
      h = fract(h / 6.0);
    }
    return vec3(h, l, s);
  }
  float chn(float p, float q, float t){ t = fract(t);
    if (t < 1.0/6.0) return p + (q - p) * 6.0 * t; if (t < 0.5) return q; if (t < 2.0/3.0) return p + (q - p) * (2.0/3.0 - t) * 6.0; return p; }
  vec3 hls2rgb(float h, float l, float s){ float q = l < 0.5 ? l * (1.0 + s) : l + s - l * s; float p = 2.0 * l - q;
    return vec3(chn(p, q, h + 1.0/3.0), chn(p, q, h), chn(p, q, h - 1.0/3.0)); }
  vec3 adj(vec3 c, vec4 a, vec3 hsl){            // come adjust_colors di daz2ob
    vec3 x = rgb2hls(c); float h = x.x, l = x.y, s = x.z, L = hsl.z / 100.0;
    if (a.y > 0.5) {
      h = fract(hsl.x / 360.0); s = clamp(hsl.y / 100.0, 0.0, 1.0);
      float target = 0.5 + 0.45 * L, k = target / max(a.w, 0.02);
      l = k <= 1.0 ? clamp(l * k, 0.0, 1.0) : 1.0 - clamp((1.0 - l) * ((1.0 - target) / max(1.0 - a.w, 0.02)), 0.0, 1.0);
    } else {
      h = fract(h + hsl.x / 360.0); float S = hsl.y / 100.0;
      s = S < 0.0 ? clamp(s * (1.0 + S), 0.0, 1.0) : clamp(s + (1.0 - s) * S, 0.0, 1.0);
      l = L < 0.0 ? clamp(l * (1.0 + L), 0.0, 1.0) : clamp(l + (1.0 - l) * L, 0.0, 1.0);
    }
    return clamp(hls2rgb(h, l, s), 0.0, 1.0);
  }
  void main(){
    vec2 tuv = vec2(vuv.x, 1.0 - vuv.y);
    vec4 c = useTex == 1 ? texture2D(tex, tuv) : col;
    if (useTex == 1 && isBody == 1) {
      vec4 m1 = texture2D(mk1, tuv); float m2 = texture2D(mk2, tuv).r;
      float mk[5]; mk[0] = m1.a; mk[1] = m2; mk[2] = m1.r; mk[3] = m1.g; mk[4] = m1.b;   // occhi, capelli, labbra, unghie, trucco
      for (int i = 0; i < 5; i++) {
        if (lk[i].x > 0.5 && mk[i] > 0.004) c.rgb = mix(c.rgb, adj(c.rgb, lk[i], lkh[i]), mk[i] * lk[i].z);
      }
    }
    if (useTex == 1 && isGarm == 1) {
      float gi = floor(texture2D(mk3, tuv).r * 255.0 + 0.5) - 1.0;
      for (int i = 0; i < 16; i++) {
        if (float(i) == gi && gk[i].x > 0.5) c.rgb = mix(c.rgb, adj(c.rgb, gk[i], gkh[i]), gk[i].z);
      }
    }
    if (alphaTest == 1 && c.a < 0.03) discard;
    vec3 n = normalize(vn);
    float d = abs(dot(n, ldir));
    float l = 0.42 + 0.62 * d;
    gl_FragColor = vec4(c.rgb * l, (alphaTest == 1 ? c.a : 1.0) * opacity);
  }`);
const PL = prog(`attribute vec3 pos; uniform mat4 mvp; void main(){ gl_Position = mvp * vec4(pos,1.0); gl_PointSize = 6.0; }`,
  `precision mediump float; uniform vec4 col; void main(){ gl_FragColor = col; }`);
const A = { pos: gl.getAttribLocation(P, "pos"), nrm: gl.getAttribLocation(P, "nrm"), uv: gl.getAttribLocation(P, "uv") };
const U = {}; for (const k of ["mvp", "tex", "useTex", "col", "ldir", "alphaTest", "opacity", "isBody", "mk1", "mk2", "lk", "lkh", "isGarm", "mk3", "gk", "gkh"])
  U[k] = gl.getUniformLocation(P, k);
// colori dalla finestra di daz2ob: occhi, capelli, labbra, unghie, trucco (tempo reale, niente Blender)
const LOOK_KEYS = ["iris", "hair", "lips", "nails", "makeup"];
let looks = {}, lookKey = "";
function lookUniforms() {
  const a = new Float32Array(20), h = new Float32Array(15);
  LOOK_KEYS.forEach((k, i) => {
    const p = looks[k], med = (S && S.med && S.med[k] != null) ? S.med[k] : 0.5;
    if (p) { a.set([1, p.mode === "regola" ? 0 : 1, (p.amount != null ? p.amount : 100) / 100, med], i * 4);
             h.set([p.h || 0, p.s || 0, p.l || 0], i * 3); }
    else a.set([0, 0, 0, med], i * 4);
  });
  return [a, h];
}
function garmUniforms() {
  const a = new Float32Array(64), h = new Float32Array(48), gl_ = (looks && looks.garments) || {};
  ((S && S.gnames) || []).forEach((g, i) => {
    const p = gl_[g], med = S.gmed && S.gmed[i] != null ? S.gmed[i] : 0.5;
    if (p) { a.set([1, p.mode === "regola" ? 0 : 1, (p.amount != null ? p.amount : 100) / 100, med], i * 4);
             h.set([p.h || 0, p.s || 0, p.l || 0], i * 3); }
    else a.set([0, 0, 0, med], i * 4);
  });
  return [a, h];
}
const UL = { mvp: gl.getUniformLocation(PL, "mvp"), col: gl.getUniformLocation(PL, "col"), pos: gl.getAttribLocation(PL, "pos") };

// ------------------------------------------------------------------ matematica
function mul(a, b) { const o = new Float32Array(16); for (let i = 0; i < 4; i++) for (let j = 0; j < 4; j++) {
  let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + j] * b[i * 4 + k]; o[i * 4 + j] = s; } return o; }
function persp(fov, asp, n, f) { const t = 1 / Math.tan(fov / 2); return new Float32Array([t / asp,0,0,0, 0,t,0,0, 0,0,(f + n) / (n - f),-1, 0,0,2 * f * n / (n - f),0]); }
function lookAt(e, c, up) {
  let z = [e[0]-c[0], e[1]-c[1], e[2]-c[2]]; let l = Math.hypot(...z); z = z.map(v => v / l);
  let x = [up[1]*z[2]-up[2]*z[1], up[2]*z[0]-up[0]*z[2], up[0]*z[1]-up[1]*z[0]]; l = Math.hypot(...x); x = x.map(v => v / l);
  const y = [z[1]*x[2]-z[2]*x[1], z[2]*x[0]-z[0]*x[2], z[0]*x[1]-z[1]*x[0]];
  return new Float32Array([x[0],y[0],z[0],0, x[1],y[1],z[1],0, x[2],y[2],z[2],0,
    -(x[0]*e[0]+x[1]*e[1]+x[2]*e[2]), -(y[0]*e[0]+y[1]*e[1]+y[2]*e[2]), -(z[0]*e[0]+z[1]*e[1]+z[2]*e[2]), 1]); }
function rot3(ax, deg) { const l = Math.hypot(...ax), x = ax[0]/l, y = ax[1]/l, z = ax[2]/l, t = deg * Math.PI / 180, c = Math.cos(t), s = Math.sin(t), C = 1 - c;
  return [c + x*x*C, x*y*C - z*s, x*z*C + y*s,  y*x*C + z*s, c + y*y*C, y*z*C - x*s,  z*x*C - y*s, z*y*C + x*s, c + z*z*C]; }
function m3mul(a, b) { const o = new Array(9); for (let i = 0; i < 3; i++) for (let j = 0; j < 3; j++) o[i*3+j] = a[i*3]*b[j] + a[i*3+1]*b[3+j] + a[i*3+2]*b[6+j]; return o; }
function m3v(m, v) { return [m[0]*v[0]+m[1]*v[1]+m[2]*v[2], m[3]*v[0]+m[4]*v[1]+m[5]*v[2], m[6]*v[0]+m[7]*v[1]+m[8]*v[2]]; }
const I3 = [1,0,0, 0,1,0, 0,0,1];

// ------------------------------------------------------------------ pose (gradi, assi del mondo Outbreak: X sinistra del personaggio, Y su, Z avanti)
const POSES = {
  "T-pose": {},
  "Braccia giu'": { 13: [[[0,0,1], -72]], 17: [[[0,0,1], 72]], 14: [[[0,1,0], -12]], 18: [[[0,1,0], 12]] },
  "Mano al petto": { 13: [[[0,0,1], -58], [[0,1,0], -38]], 14: [[[0,1,0], -112]], 15: [[[1,0,0], 25]], 17: [[[0,0,1], 68]], 18: [[[0,1,0], 15]],
                     10: [[[1,0,0], 8]], 4: [[[1,0,0], -12]], 5: [[[1,0,0], 18]], 7: [[[1,0,0], -6]], 8: [[[1,0,0], 10]] },
  "Braccia avanti": { 13: [[[0,1,0], -80]], 17: [[[0,1,0], 80]], 14: [[[0,1,0], -25]], 18: [[[0,1,0], 25]] },
  "Braccia su": { 13: [[[0,0,1], 70]], 17: [[[0,0,1], -70]], 12: [[[0,0,1], 12]], 16: [[[0,0,1], -12]] },
  "Polsi piegati": { 13: [[[0,0,1], -70]], 17: [[[0,0,1], 70]], 15: [[[1,0,0], 70], [[0,0,1], -40]], 19: [[[1,0,0], -70], [[0,0,1], 40]],
                     32: [[[1,0,0], 30]], 28: [[[1,0,0], 30]], 33: [[[0,1,0], -30]], 29: [[[0,1,0], 30]] },
  "Corsa": { 4: [[[1,0,0], -45]], 5: [[[1,0,0], 70]], 7: [[[1,0,0], 30]], 8: [[[1,0,0], 25]], 6: [[[1,0,0], -15]],
             13: [[[0,0,1], -70], [[0,1,0], 35]], 14: [[[0,1,0], -80]], 17: [[[0,0,1], 70], [[0,1,0], 35]], 18: [[[0,1,0], 80]], 10: [[[0,1,0], 10]] },
  "Accovacciata": { 4: [[[1,0,0], -95]], 5: [[[1,0,0], 120]], 7: [[[1,0,0], -95]], 8: [[[1,0,0], 120]], 6: [[[1,0,0], -25]], 9: [[[1,0,0], -25]],
                    10: [[[1,0,0], 20]], 13: [[[0,0,1], -60], [[0,1,0], -30]], 17: [[[0,0,1], 60], [[0,1,0], 30]] },
  "Testa e viso": { 21: [[[0,1,0], 35], [[1,0,0], 15]], 27: [[[1,0,0], 18]], 24: [[[1,0,0], 25]], 26: [[[1,0,0], 25]] },
  "Occhi chiusi": { move: { 24: [0, -1.4, 0.15], 26: [0, -1.4, 0.15], 23: [0, -0.55, 0.1], 25: [0, -0.55, 0.1] } },
  "Bocca aperta": { move: { 27: [0, -1.1, 0] }, 27: [[[1,0,0], 12]] },
};

// ------------------------------------------------------------------ scena
let S = null, version = -1, loading = false, pose = "T-pose", animT = 0, lastPoseKey = "", iso = "";
const cam = { yaw: 0, pitch: 0.08, dist: 330, tx: 0, ty: 88, tz: 0 };
const VIEWS = { front: [0, 0.08, 330, 0, 88, 0], back: [Math.PI, 0.08, 330, 0, 88, 0], side: [Math.PI / 2, 0.06, 330, 0, 88, 0],
  face: [0.25, 0.05, 55, 0, 160, 2], arm: [0.6, 0.2, 110, 20, 135, 0], hand: [0.35, 0.6, 60, 62, 138, 0], feet: [0.5, 0.35, 85, 0, 12, 2] };
function setView(k) { const v = VIEWS[k]; [cam.yaw, cam.pitch, cam.dist, cam.tx, cam.ty, cam.tz] = v; }
document.querySelectorAll("[data-v]").forEach(b => b.onclick = () => setView(b.dataset.v));
for (const k in POSES) { const b = document.createElement("button"); b.textContent = k; b.onclick = () => { pose = k; markPose(); }; $("poses").appendChild(b); }
function markPose() { for (const b of $("poses").children) b.classList.toggle("on", b.textContent === pose); }
markPose();

function b64(s, T) { const bin = atob(s); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new T(u.buffer); }

async function loadScene(ver, dir) {
  loading = true;
  try {
    const r = await fetch("files/" + ver + "/scene.json"); const d = await r.json();
    const buf = await (await fetch("files/" + ver + "/" + (d.bin || "scene.bin"))).arrayBuffer();
    const texs = {};
    const H = d.hash || {};
    const getTex = async (fn, nearest) => {                 // stessa texture di prima (stesso hash): si riusa
      const h = H[fn];
      if (h && TEXC[h]) return TEXC[h];
      const t = await loadTex("files/" + ver + "/" + fn, nearest);
      if (h && t) { TEXC[h] = t; TEXN.push(h); while (TEXN.length > 24) { const o = TEXN.shift(); if (TEXC[o]) { gl.deleteTexture(TEXC[o]); delete TEXC[o]; } } }
      return t;
    };
    for (const m of d.meshes) if (m.tex && !(m.tex in texs)) texs[m.tex] = await getTex(m.tex);
    let mk1 = null, mk2 = null;
    if (d.looks) { mk1 = await getTex(d.looks.mask1); mk2 = await getTex(d.looks.mask2); }
    const mk3 = d.looks && d.looks.mask3 ? await getTex(d.looks.mask3, true) : null;
    const gtex = (d.looks && d.looks.gtex) || [];
    const old = S;
    S = { skel: d.skeleton, meshes: [], mk1, mk2, med: d.looks ? d.looks.med : null,
          mk3, gnames: d.looks ? d.looks.gnames : null, gmed: d.looks ? d.looks.gmed : null };
    for (const m of d.meshes) {
      const n = m.n;
      const P0 = new Float32Array(buf, m.P, n * 3), UV = new Float32Array(buf, m.UV, n * 2);
      const J = new Uint8Array(buf, m.J, n * 4), W = new Float32Array(buf, m.W, n * 4);
      const mesh = { name: m.name, id: m.id || "", src: m.src || "", kind: m.kind, tris: m.tris, alpha: m.alpha, body: !!m.body, garm: gtex.indexOf(m.tex) >= 0,
        adj: m.adj || null, adjkey: m.adjkey || "", P0src: P0, adjNow: "",
        tex: texs[m.tex] || null,
        P0, J, W, P: new Float32Array(P0.length), N: new Float32Array(P0.length),
        bp: gl.createBuffer(), bn: gl.createBuffer(), bu: gl.createBuffer(), bl: null, nl: 0, visible: true };
      gl.bindBuffer(gl.ARRAY_BUFFER, mesh.bu); gl.bufferData(gl.ARRAY_BUFFER, UV, gl.STATIC_DRAW);
      // spigoli per il wireframe
      const L = new Uint16Array(n * 2); for (let t = 0; t < n; t += 3) { L.set([t,t+1, t+1,t+2, t+2,t], t * 2); }
      mesh.bl = gl.createBuffer(); gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.bl);
      if (n < 65536) { gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, L, gl.STATIC_DRAW); mesh.nl = L.length; }
      if (old) { const o = old.meshes.find(x => x.name === m.name && x.kind === m.kind); if (o) mesh.visible = o.visible; }
      S.meshes.push(mesh);
    }
    if (old) for (const m of old.meshes) { gl.deleteBuffer(m.bp); gl.deleteBuffer(m.bn); gl.deleteBuffer(m.bu); gl.deleteBuffer(m.bl); }
    lastPoseKey = "";
    buildList();
    $("big").style.display = "none";
  } catch (e) { setStatus("Anteprima non leggibile: " + e, "err"); }
  loading = false;
}
const TEXC = {}, TEXN = [];
function loadTex(url, nearest) { return new Promise((ok) => { const im = new Image(); im.onload = () => {
  const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, t);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, im);
  const f = nearest ? gl.NEAREST : gl.LINEAR;
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, f); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, f);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  ok(t); }; im.onerror = () => ok(null); im.src = url; }); }

function buildList() {
  const box = $("meshes"); box.innerHTML = "";
  let tot = 0;
  if (iso && !S.meshes.some(m => m.id === iso)) iso = "";
  for (const m of S.meshes) {
    if (m.kind !== "mesh") continue;
    tot += m.tris;
    const rem = S.meshes.filter(r => r.kind === "tolta" && r.src === m.id).reduce((a, r) => a + r.tris, 0);
    const row = document.createElement("div"); row.className = "row" + (iso === m.id ? " iso" : "");
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = m.visible;
    cb.onchange = () => { m.visible = cb.checked; };
    const lb = document.createElement("label"); lb.textContent = m.name; lb.title = "clic: vedi solo questa mesh";
    lb.onclick = () => { iso = (iso === m.id) ? "" : m.id; buildList(); };
    const n = document.createElement("span"); n.className = "n"; n.textContent = m.tris;
    row.append(cb, lb);
    if (rem) { const r = document.createElement("span"); r.className = "rem"; r.textContent = "-" + rem; r.title = "triangoli tolti dalla pulizia"; row.append(r); }
    row.append(n); box.appendChild(row);
  }
  $("tot").textContent = "· " + tot + " triangoli";
  $("isobar").style.display = iso ? "block" : "none";
}
$("showall").onclick = () => { iso = ""; buildList(); };

// ------------------------------------------------------------------ skinning (come il gioco: somma pesata delle ossa)
function boneMats(amt) {
  const sk = S.skel, def = POSES[pose] || {}, M = [];
  const world = (n) => {
    if (M[n]) return M[n];
    let R = I3; for (const [ax, deg] of (Array.isArray(def[n]) ? def[n] : [])) R = m3mul(rot3(ax, deg * amt), R);
    const p = sk.pos[n]; const Rp = m3v(R, p);
    const mv = (def.move && def.move[n]) || [0, 0, 0];                 // spostamento (ossa del viso)
    let loc = { R, t: [p[0] - Rp[0] + mv[0] * amt, p[1] - Rp[1] + mv[1] * amt, p[2] - Rp[2] + mv[2] * amt] };
    const par = sk.parent[n];
    if (par >= 0 && par !== n) { const W = world(par); const tt = m3v(W.R, loc.t);
      loc = { R: m3mul(W.R, R), t: [tt[0] + W.t[0], tt[1] + W.t[1], tt[2] + W.t[2]] }; }
    return (M[n] = loc);
  };
  for (let i = 0; i < sk.pos.length; i++) world(i);
  return M;
}
// ritocchi di capelli e capi applicati subito (scala attorno al centro + spostamento), prima del calcolo di Blender
function liveAdjust() {
  if (!S) return false;
  const A = (looks && looks.adjust) || {};
  let changed = false;
  for (const m of S.meshes) {
    if (!m.adj || !m.adjkey) continue;
    let p = null;
    if (m.adjkey === "hair") {
      const h = A.hair || {};
      p = [(h.sx ?? 100) / 100, (h.sy ?? 100) / 100, (h.sz ?? 100) / 100, h.dx || 0, h.dy || 0, h.dz || 0];
    } else if (m.adjkey.startsWith("g:")) {
      const g = (A.garments || {})[m.adjkey.slice(2)] || {};
      const sc = (g.scale ?? 100) / 100;
      p = [sc, sc, sc, g.dx || 0, g.dy || 0, g.dz || 0];
    }
    if (!p) continue;
    const key = p.join(",");
    if (key === m.adjNow) continue;
    m.adjNow = key; changed = true;
    const a = m.adj, c = [a[0], a[1], a[2]], s0 = [a[3], a[4], a[5]], o0 = [a[6], a[7], a[8]];
    const same = [0, 1, 2].every(k => Math.abs(s0[k] - p[k]) < 1e-6 && Math.abs(o0[k] - p[k + 3]) < 1e-6);
    if (same) { m.P0 = m.P0src; continue; }
    const src = m.P0src, out = new Float32Array(src.length);
    for (let i = 0; i < src.length; i += 3) {
      for (let k = 0; k < 3; k++) {
        const orig = c[k] + (src[i + k] - c[k] - o0[k]) / (s0[k] || 1);     // prima del ritocco usato da Blender
        out[i + k] = c[k] + (orig - c[k]) * p[k] + p[k + 3];                // con il ritocco di adesso
      }
    }
    m.P0 = out;
  }
  return changed;
}
function skin(amt) {
  const M = boneMats(amt);
  for (const m of S.meshes) {
    const P0 = m.P0, P = m.P, J = m.J, W = m.W, n = P0.length / 3;
    for (let i = 0; i < n; i++) {
      const x = P0[i*3], y = P0[i*3+1], z = P0[i*3+2]; let ox = 0, oy = 0, oz = 0;
      for (let k = 0; k < 4; k++) { const w = W[i*4+k]; if (w <= 0) continue; const B = M[J[i*4+k]]; const R = B.R;
        ox += w * (R[0]*x + R[1]*y + R[2]*z + B.t[0]); oy += w * (R[3]*x + R[4]*y + R[5]*z + B.t[1]); oz += w * (R[6]*x + R[7]*y + R[8]*z + B.t[2]); }
      P[i*3] = ox; P[i*3+1] = oy; P[i*3+2] = oz;
    }
    const N = m.N;
    for (let t = 0; t < n; t += 3) {
      const a = t*3, b = a + 3, c = a + 6;
      const ux = P[b]-P[a], uy = P[b+1]-P[a+1], uz = P[b+2]-P[a+2], vx = P[c]-P[a], vy = P[c+1]-P[a+1], vz = P[c+2]-P[a+2];
      let nx = uy*vz - uz*vy, ny = uz*vx - ux*vz, nz = ux*vy - uy*vx; const l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
      for (const q of [a, b, c]) { N[q] = nx; N[q+1] = ny; N[q+2] = nz; }
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, m.bp); gl.bufferData(gl.ARRAY_BUFFER, P, gl.DYNAMIC_DRAW);
    gl.bindBuffer(gl.ARRAY_BUFFER, m.bn); gl.bufferData(gl.ARRAY_BUFFER, N, gl.DYNAMIC_DRAW);
  }
  S.M = M;
}

// ------------------------------------------------------------------ disegno
const boneBuf = gl.createBuffer();
function frame(ts) {
  requestAnimationFrame(frame);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const w = cv.clientWidth * dpr | 0, h = cv.clientHeight * dpr | 0;
  if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
  gl.viewport(0, 0, w, h);
  gl.clearColor(0.43, 0.46, 0.52, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
  if (!S) return;
  let amt = $("amt").value / 100;
  if ($("anim").checked) amt *= 0.5 - 0.5 * Math.cos(ts / 900);
  const key = pose + "|" + amt.toFixed(3);
  if (liveAdjust()) lastPoseKey = "";
  if (key !== lastPoseKey) { skin(amt); lastPoseKey = key; }
  const cp = Math.cos(cam.pitch);
  const eye = [cam.tx + cam.dist * Math.sin(cam.yaw) * cp, cam.ty + cam.dist * Math.sin(cam.pitch), cam.tz + cam.dist * Math.cos(cam.yaw) * cp];
  const mvp = mul(persp(0.5, w / h, 2, 3000), lookAt(eye, [cam.tx, cam.ty, cam.tz], [0, 1, 0]));
  const ld = [eye[0]-cam.tx, eye[1]-cam.ty + 40, eye[2]-cam.tz]; const ll = Math.hypot(...ld);
  gl.useProgram(P);
  gl.uniformMatrix4fv(U.mvp, false, mvp); gl.uniform3f(U.ldir, ld[0]/ll, ld[1]/ll, ld[2]/ll);
  const [la, lh] = lookUniforms();
  gl.uniform4fv(U.lk, la); gl.uniform3fv(U.lkh, lh);
  const [ga, gh] = garmUniforms(); gl.uniform4fv(U.gk, ga); gl.uniform3fv(U.gkh, gh);
  if (S.mk3) { gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, S.mk3); gl.uniform1i(U.mk3, 3); }
  if (S.mk1) { gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, S.mk1); gl.uniform1i(U.mk1, 1);
               gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, S.mk2); gl.uniform1i(U.mk2, 2); }
  gl.enable(gl.DEPTH_TEST); gl.enable(gl.CULL_FACE); gl.cullFace(gl.BACK); gl.frontFace(gl.CCW);
  const useTex = $("tex").checked, wire = $("wire").checked, showRem = $("removed").checked;
  const draw = (m, pass) => {
    gl.bindBuffer(gl.ARRAY_BUFFER, m.bp); gl.enableVertexAttribArray(A.pos); gl.vertexAttribPointer(A.pos, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, m.bn); gl.enableVertexAttribArray(A.nrm); gl.vertexAttribPointer(A.nrm, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, m.bu); gl.enableVertexAttribArray(A.uv); gl.vertexAttribPointer(A.uv, 2, gl.FLOAT, false, 0, 0);
    const red = m.kind === "tolta";
    const t = useTex && m.tex && !red;
    gl.uniform1i(U.useTex, t ? 1 : 0);
    gl.uniform4f(U.col, red ? 0.9 : 0.78, red ? 0.22 : 0.76, red ? 0.22 : 0.74, 1);
    gl.uniform1i(U.alphaTest, t && m.alpha ? 1 : 0);
    gl.uniform1i(U.isBody, t && m.body && S.mk1 ? 1 : 0);
    gl.uniform1i(U.isGarm, t && m.garm && S.mk3 ? 1 : 0);
    gl.uniform1f(U.opacity, pass === "ghost" ? 0.13 : (red ? (iso ? 0.9 : 0.75) : 1.0));
    if (t) { gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, m.tex); gl.uniform1i(U.tex, 0); }
    gl.drawArrays(gl.TRIANGLES, 0, m.P.length / 3);
    if (wire && m.nl && pass !== "ghost") {
      gl.uniform1i(U.useTex, 0); gl.uniform4f(U.col, 0.05, 0.05, 0.08, 1); gl.uniform1i(U.alphaTest, 0); gl.uniform1f(U.opacity, 1);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, m.bl); gl.drawElements(gl.LINES, m.nl, gl.UNSIGNED_SHORT, 0);
    }
  };
  if (iso) {
    // una mesh sola: quello che resta normale, quello che le viene tolto in rosso, le altre come fantasmi
    gl.disable(gl.BLEND); gl.depthMask(true);
    for (const m of S.meshes) if (m.kind === "mesh" && m.id === iso && !m.alpha) draw(m);
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.CULL_FACE);
    for (const m of S.meshes) if (m.kind === "mesh" && m.id === iso && m.alpha) draw(m);
    for (const m of S.meshes) if (m.kind === "tolta" && m.src === iso) draw(m);
    if ($("ghost").checked) {
      gl.depthMask(false);
      for (const m of S.meshes) if (m.visible && m.kind === "mesh" && m.id !== iso) draw(m, "ghost");
    }
    gl.depthMask(true); gl.disable(gl.BLEND);
    drawBones(mvp);
    return;
  }
  // pieni, poi trasparenti (come il gioco, che li disegna per ultimi), poi le parti tolte sopra
  gl.disable(gl.BLEND); gl.depthMask(true);
  for (const m of S.meshes) if (m.visible && m.kind === "mesh" && !m.alpha) draw(m);
  gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
  gl.depthMask(false); gl.disable(gl.CULL_FACE);
  for (const m of S.meshes) if (m.visible && m.kind === "mesh" && m.alpha) draw(m);
  // le parti tolte stanno sotto i vestiti: spinte un filo indietro, cosi' non spuntano dai bordi
  gl.enable(gl.POLYGON_OFFSET_FILL); gl.polygonOffset(4, 4);
  if (showRem) for (const m of S.meshes) if (m.visible && m.kind === "tolta") draw(m);
  gl.disable(gl.POLYGON_OFFSET_FILL);
  gl.depthMask(true); gl.disable(gl.BLEND);
  drawBones(mvp);
}
function drawBones(mvp) {
  if ($("bones").checked && S.M) {
    const sk = S.skel, pts = [], lines = [];
    const wp = (i) => { const B = S.M[i]; const v = m3v(B.R, sk.pos[i]); return [v[0] + B.t[0], v[1] + B.t[1], v[2] + B.t[2]]; };
    for (let i = 2; i < sk.pos.length; i++) { const q = wp(i); pts.push(...q); const p = sk.parent[i]; if (p >= 1) lines.push(...wp(p), ...q); }
    gl.useProgram(PL); gl.uniformMatrix4fv(UL.mvp, false, mvp); gl.disable(gl.DEPTH_TEST);
    gl.bindBuffer(gl.ARRAY_BUFFER, boneBuf); gl.enableVertexAttribArray(UL.pos);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(lines), gl.DYNAMIC_DRAW); gl.vertexAttribPointer(UL.pos, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(UL.col, 1, 0.35, 0.2, 1); gl.drawArrays(gl.LINES, 0, lines.length / 3);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pts), gl.DYNAMIC_DRAW); gl.vertexAttribPointer(UL.pos, 3, gl.FLOAT, false, 0, 0);
    gl.uniform4f(UL.col, 1, 0.85, 0.2, 1); gl.drawArrays(gl.POINTS, 0, pts.length / 3);
    gl.enable(gl.DEPTH_TEST);
  }
}
requestAnimationFrame(frame);

// ------------------------------------------------------------------ mouse
let drag = null;
cv.addEventListener("contextmenu", e => e.preventDefault());
cv.addEventListener("pointerdown", e => { drag = { x: e.clientX, y: e.clientY, pan: e.button === 2 || e.shiftKey }; cv.setPointerCapture(e.pointerId); });
cv.addEventListener("pointerup", () => drag = null);
cv.addEventListener("pointermove", e => {
  if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
  if (drag.pan) { const k = cam.dist / 600; cam.tx -= dx * k * Math.cos(cam.yaw); cam.tz += dx * k * Math.sin(cam.yaw); cam.ty += dy * k; }
  else { cam.yaw -= dx * 0.008; cam.pitch = Math.max(-1.4, Math.min(1.4, cam.pitch + dy * 0.008)); }
});
cv.addEventListener("wheel", e => { e.preventDefault(); cam.dist = Math.max(15, Math.min(900, cam.dist * Math.exp(e.deltaY * 0.0012))); }, { passive: false });

// ------------------------------------------------------------------ aggiornamento dalla finestra di daz2ob
function setStatus(t, cls) { const s = $("status"); s.textContent = t; s.className = cls || ""; }
async function poll() {
  try {
    const r = await fetch("state?t=" + Date.now()); const st = await r.json();
    $("title").textContent = st.title || "Anteprima 3D";
    if (st.busy) setStatus(st.busy, "busy");
    else if (st.error) setStatus(st.error, "err");
    else setStatus(st.info || "", "");
    if (st.looks) looks = st.looks;
    if (st.version !== version && st.version >= 0 && !loading) { version = st.version; await loadScene(st.version); }
  } catch (e) { setStatus("La finestra di daz2ob e' chiusa: l'anteprima non si aggiorna piu'.", "err"); }
  setTimeout(poll, 350);
}
poll();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ NBD con fbx2nbd.py (accanto a questo script)
STD_CHILDREN = {0: [1], 1: [2], 2: [10, 3], 3: [4, 7], 4: [5], 5: [6], 7: [8], 8: [9], 10: [11],
                11: [12, 16, 20], 12: [13], 13: [14], 14: [15], 15: [32], 16: [17], 17: [18], 18: [19],
                19: [28], 20: [21], 21: [22], 22: [23, 24, 25, 26, 27], 28: [29, 30, 31], 32: [33, 34, 35]}


def fbx2nbd_module():
    """Importa fbx2nbd.py dalla cartella di questo script (None se manca)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if not os.path.isfile(os.path.join(here, "fbx2nbd.py")):
        return None
    if here not in sys.path:
        sys.path.insert(0, here)
    import importlib
    import fbx2nbd
    return importlib.reload(fbx2nbd)


def to_nbd(fbx, nbd, ambient=20, on_line=print):
    """FBX -> NBD con fbx2nbd.py, poi scheletro e materiali come i personaggi originali (tipi dei nodi, ordine
    dei figli, ambient, niente riflesso). -> True se riuscito."""
    import contextlib
    import io
    mod = fbx2nbd_module()
    if mod is None:
        on_line("ERRORE: fbx2nbd.py non e' nella cartella di daz2ob.py: copialo li' e riprova")
        return False

    class _W(io.TextIOBase):
        def __init__(self):
            self.buf = ""

        def write(self, t):
            self.buf += t
            while "\n" in self.buf:
                ln, self.buf = self.buf.split("\n", 1)
                if ln.strip():
                    on_line("  " + ln.rstrip())
            return len(t)
    w = _W()
    try:
        with contextlib.redirect_stdout(w):
            rc = mod.main([fbx, nbd, "--no-addon", "-q"])
        if rc != 0 or not os.path.isfile(nbd):
            on_line("ERRORE: %s non convertito" % os.path.basename(fbx))
            return False
        nb = mod.read_nbd(nbd)
        h = mod.nbd_slot(nb, "AHI")
        mo = mod.nbd_slot(nb, "AMO")
        if h is not None and len(h.nodes) == 36:
            for n, t in zip(h.nodes, mod.STD_TYPES_36):
                n.type = t
                n.child, n.next = -1, -1
            for par, kids in STD_CHILDREN.items():
                h.nodes[par].child = kids[0]
                for a, b in zip(kids, kids[1:]):
                    h.nodes[a].next = b
        if mo is not None:
            k = max(0, min(255, int(ambient))) / 255.0
            for ma in mo.materials:
                ma.type = 0x130000
                ma.ambient = (k, k, k, 1.0)
                ma.diffuse = (1.0, 1.0, 1.0, 1.0)
                ma.specular = (0.0, 0.0, 0.0, 1.0)
                ma.power = 5.0
        with open(nbd, "wb") as fh:
            fh.write(mod.write_nbd(nb))
    except Exception as e:
        on_line("ERRORE: %s non convertito (%s)" % (os.path.basename(fbx), e))
        return False
    on_line("NBD: %s (%d KB)" % (os.path.basename(nbd), os.path.getsize(nbd) // 1024))
    return True


def outfit_fbx_files(job):
    """FBX degli outfit di un lavoro (quelli che esistono)."""
    name = safe_name(job.get("name") or os.path.splitext(os.path.basename(job.get("fbx", "x")))[0])
    outs = job.get("outfits") or [{"name": "base"}]
    fs = [os.path.join(job["outdir"], safe_name(o.get("name", "outfit")) if job.get("outfit_folders") else "",
                       "%s_%s.fbx" % (name, safe_name(o.get("name", "outfit")))) for o in outs]
    return [f for f in fs if os.path.isfile(f)]


def load_settings():
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_settings(d):
    try:
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
    except Exception:
        pass


# triangoli massimi delle zone di un Genesis 8 (per stimare il totale nella finestra)
G8_MAX = {"face": 3516, "body": 17256, "feet": 3424, "ears": 868, "eyes": 576, "nails": 1956, "mouth": 1956,
          "eyesocket": 124}


def outfit_prefix(name):
    """'casual+sera__TiedShirt' -> (['casual', 'sera'], 'TiedShirt'); senza prefisso -> ([], nome).
    Il prefisso si mette in DAZ nel nome del capo (vedi daz2ob_nomi.dsa)."""
    if "__" not in name:
        return [], name
    pre, short = name.split("__", 1)
    outs = [p.strip() for p in pre.split("+") if p.strip()]
    return (outs, short.strip() or name) if outs else ([], name)


def short_name(name):
    return outfit_prefix(name)[1]


def split_shares(budget, items):
    """items: [(nome, triangoli originali, quota %)] -> {nome: triangoli} (come split_budget)."""
    alloc = {n: 0.0 for n, _, _ in items}
    free = {n for n, _, _ in items}
    left = float(budget)
    q = {n: max(0.0, s) + 1e-9 for n, _, s in items}
    orig = {n: t for n, t, _ in items}
    for _ in range(len(items) + 1):
        if not free or left <= 0:
            break
        tot = sum(q[n] for n in free)
        share = {n: left * q[n] / tot for n in free}
        cap = {n for n in free if alloc[n] + share[n] >= orig[n]}
        if not cap:
            for n in free:
                alloc[n] += share[n]
            break
        for n in cap:
            left -= orig[n] - alloc[n]
            alloc[n] = orig[n]
        free -= cap
    return {n: int(max(min(orig[n], 40), alloc[n])) for n in alloc}


def gui():
    import colorsys
    import tempfile
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

    st = load_settings()
    root = tk.Tk()
    root.title("DAZ -> Outbreak  (daz2ob %s)" % __version__)
    root.geometry("1360x940")
    root.minsize(1180, 820)
    V = {}

    def var(name, value, kind=tk.StringVar):
        V[name] = kind(value=value)
        return V[name]

    here = os.path.dirname(os.path.abspath(__file__))
    var("fbx", st.get("fbx", ""))
    var("blender", st.get("blender") or find_blender() or "")
    var("collection", os.path.join(here, "personaggi"))           # fissa: tutto accanto a daz2ob.py
    var("name", "")
    var("preset", st.get("preset", "Normale"))
    T0 = preset_targets(PRESETS.get(V["preset"].get(), (8000, 3000))[0])
    T0.update(st.get("targets", {}) if V["preset"].get() == "Custom" else {})
    for k, _ in ZONE_SHARE:
        var("t_" + k, str(T0.get(k, 0)))
    var("limit", str(st.get("budget_limit", 12000)))
    var("atlas_base", str(st.get("atlas_base", 512)))
    var("atlas_outfit", str(st.get("atlas_outfit", 256)))
    var("brow_side", str(st.get("brow_side", 0.3)))
    var("mirror", st.get("mirror_limbs", True), tk.BooleanVar)
    var("ambient", str(st.get("ambient", 20)))
    var("margin_mm", str(st.get("margin_mm", 3.0)))
    var("joint_smooth", str(st.get("joint_smooth", 1.0)))
    var("wfb", st.get("weights_from_body", True), tk.BooleanVar)
    var("hairlib", st.get("hairlib") or os.path.join(here, "libreria_capelli"))
    var("libsel", "(nessuno)")
    var("hair_slot", str(st.get("hair_slot", 170)))
    var("hair_reserve", str(st.get("hair_reserve", 128)))
    var("auto_prev", True, tk.BooleanVar)
    var("keep_lashes", st.get("keep_lashes", True), tk.BooleanVar)
    var("lash_tris", str(st.get("lash_tris", 150)))
    var("keep_teeth", st.get("keep_teeth", False), tk.BooleanVar)
    var("acc_quota", str(st.get("acc_quota", 25)))
    var("teeth_tris", str(st.get("teeth_tris", 200)))
    var("atlas_trasp", str(st.get("atlas_trasp", 256)))
    var("make_nbd", st.get("make_nbd", True), tk.BooleanVar)
    var("arms_p06", st.get("arms_p06", True), tk.BooleanVar)
    var("shoulder_lift", str(st.get("shoulder_lift", 8)))
    var("shoulder_shift", str(st.get("shoulder_shift", 0)))
    SHMODES = [("no", "come DAZ"), ("liscia", "sfumati"), ("p06", "copiati da P06")]
    var("shoulder_mode", dict(SHMODES).get(st.get("shoulder_mode", "no"), SHMODES[0][1]))
    var("shoulder_smooth", str(st.get("shoulder_smooth", 4.0)))
    var("lip27", float(st.get("lip_lower_node27", 1.0)), tk.DoubleVar)
    spk = st.get("specks") or {}
    var("spk_on", bool(spk.get("on", True)), tk.BooleanVar)
    var("spk_tris", str(spk.get("tris", 3)))
    var("spk_area", str(spk.get("area", 0.5)))
    for k_, _, _ in FACE_KEYS:
        var("fx_" + k_, 0.0, tk.DoubleVar)
    BROW_MODES = [("no", "normali"), ("atlas", "pezzo proprio nell'atlas (piu' pixel)"),
                  ("rinforza", "rinforzate (contrasto e nitidezza)")]
    var("brow_mode", BROW_MODES[0][1])
    var("brow_amt", 50.0, tk.DoubleVar)
    state = {"real": {}, "scan": None, "outfits": [], "thumbs": {}, "busy": False, "tmp": tempfile.mkdtemp(prefix="daz2ob_"),
             "orig": {}, "lock": False, "prev": None, "prev_i": 0, "eyes": None, "after": None, "pending": False,
             "libprev": None, "libprev_i": 0, "depth": {}, "iname": {}, "pv": {"key": None, "imgs": {}}, "srv": None}

    def outdir():
        return os.path.join(V["collection"].get().strip(), safe_name(V["name"].get().strip() or "personaggio"))

    def char_json(nm=None):
        nm = safe_name(nm or V["name"].get().strip() or "personaggio")
        return os.path.join(V["collection"].get().strip(), nm, nm + ".json")

    def browse(name, kind="open", types=None):
        p = filedialog.askdirectory() if kind == "dir" else filedialog.askopenfilename(filetypes=types or [("Tutti", "*")])
        if p:
            prev = V[name].get()
            V[name].set(p)
            # il nome segue l'FBX, se era vuoto o era quello preso dall'FBX di prima (non scritto a mano)
            if name == "fbx" and (not V["name"].get() or
                                  V["name"].get() == safe_name(os.path.splitext(os.path.basename(prev))[0])):
                V["name"].set(safe_name(os.path.splitext(os.path.basename(p))[0]))
        return p

    # ------------------------------------------------------------------ controllo colore (come Photoshop)
    class ColorBox(object):
        """Tonalita'/Saturazione/Luminosita' con "Colora" e preset naturali."""

        def __init__(self, parent, title, kind, amount=False):
            self.kind, self.amount, self.cb = kind, amount, None
            f = self.frame = ttk.LabelFrame(parent, text=title, padding=4)
            self.on = tk.BooleanVar(value=False)
            self.col = tk.BooleanVar(value=True)
            self.pre = tk.StringVar(value="")
            r1 = ttk.Frame(f)
            r1.pack(fill="x")
            ttk.Checkbutton(r1, text="Cambia colore", variable=self.on, command=self.changed).pack(side="left")
            c = ttk.Combobox(r1, textvariable=self.pre, values=[n for n, _ in COLOR_PRESETS[kind]], state="readonly", width=15)
            c.pack(side="left", padx=4)
            c.bind("<<ComboboxSelected>>", lambda e: self.preset())
            ttk.Checkbutton(r1, text="Colora (tinta unica)", variable=self.col, command=self.mode_changed).pack(side="left", padx=4)
            self.sw = tk.Label(r1, text="      ", relief="sunken", bg="#888888")
            self.sw.pack(side="left", padx=4)
            r2 = ttk.Frame(f)
            r2.pack(fill="x")
            self.sc, self.val = {}, {}
            keys = [("h", "Tonalita'"), ("s", "Saturazione"), ("l", "Luminosita'")] + ([("amount", "Intensita'")] if amount else [])
            for i, (k, t) in enumerate(keys):
                ttk.Label(r2, text=t).grid(row=0, column=i, sticky="w", padx=3)
                s = ttk.Scale(r2, from_=0, to=100, orient="horizontal", length=105,
                              command=lambda v, k=k: self.moved(k))
                s.grid(row=1, column=i, padx=3)
                s.bind("<ButtonRelease-1>", lambda e: self.changed())
                lb = ttk.Label(r2, text="0", width=5)
                lb.grid(row=2, column=i)
                self.sc[k], self.val[k] = s, lb
            self.ranges(True)
            self.put(None, False)                        # spento finche' non lo accendi tu

        def ranges(self, colora):
            self.sc["h"].configure(from_=0 if colora else -180, to=360 if colora else 180)
            self.sc["s"].configure(from_=0 if colora else -100, to=100)
            self.sc["l"].configure(from_=-100, to=100)
            if self.amount:
                self.sc["amount"].configure(from_=0, to=100)

        def moved(self, k):
            self.val[k].configure(text="%d" % round(float(self.sc[k].get())))
            self.swatch()

        def swatch(self):
            if not self.on.get():
                self.sw.configure(bg="#888888")
                return
            h, s, l = (float(self.sc[k].get()) for k in ("h", "s", "l"))
            if self.col.get():
                r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, 0.5 + 0.45 * l / 100.0, s / 100.0)
            else:
                r, g, b = colorsys.hls_to_rgb(((30 + h) % 360) / 360.0, min(1, max(0, 0.5 + 0.3 * l / 100.0)),
                                              min(1, max(0, 0.35 + 0.35 * s / 100.0)))
            self.sw.configure(bg="#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255)))

        def put(self, p, notify=True):
            state["lock"] = True
            self.on.set(bool(p))
            p = p or {"mode": "colora", "h": 30, "s": 30, "l": 0, "amount": 100}
            self.col.set(p.get("mode", "colora") == "colora")
            self.ranges(self.col.get())
            for k in self.sc:
                self.sc[k].set(float(p.get(k, 100 if k == "amount" else 0)))
                self.moved(k)
            state["lock"] = False
            self.swatch()
            if notify:
                self.changed()

        def get(self):
            if not self.on.get():
                return None
            p = {"mode": "colora" if self.col.get() else "regola"}
            for k in self.sc:
                p[k] = round(float(self.sc[k].get()), 1)
            return p

        def preset(self):
            p = dict(COLOR_PRESETS[self.kind])[self.pre.get()]
            self.put(dict(p, amount=p.get("amount", 100)) if self.amount else p)

        def mode_changed(self):
            self.put({"mode": "colora" if self.col.get() else "regola",
                      "h": 30 if self.col.get() else 0, "s": 30 if self.col.get() else 0, "l": 0, "amount": 100})

        def changed(self):
            self.swatch()
            if not state["lock"] and self.cb:
                self.cb()

    # ------------------------------------------------------------------ in alto
    top = ttk.Frame(root, padding=8)
    top.pack(fill="x")
    top.columnconfigure(1, weight=1)
    ttk.Label(top, text="FBX esportato da DAZ").grid(row=0, column=0, sticky="w")
    ttk.Entry(top, textvariable=V["fbx"]).grid(row=0, column=1, sticky="ew", padx=4)
    ttk.Button(top, text="Sfoglia...", command=lambda: browse("fbx", types=[("FBX", "*.fbx *.FBX")])).grid(row=0, column=2)
    btn_scan = ttk.Button(top, text="1. Analizza")
    btn_scan.grid(row=0, column=3, padx=(8, 0))
    ttk.Label(top, text="Blender (4.1 o piu' recente)").grid(row=1, column=0, sticky="w")
    ttk.Entry(top, textvariable=V["blender"]).grid(row=1, column=1, sticky="ew", padx=4)
    ttk.Button(top, text="Sfoglia...", command=lambda: browse("blender", types=[("Blender", "blender*"), ("Tutti", "*")])).grid(row=1, column=2)
    ttk.Label(top, text="Personaggio").grid(row=3, column=0, sticky="w")
    rown = ttk.Frame(top)
    rown.grid(row=3, column=1, sticky="ew", padx=4)
    cb_name = ttk.Combobox(rown, textvariable=V["name"], width=26)
    cb_name.pack(side="left")
    ttk.Label(rown, text="  scegli dall'elenco per riaprire un personaggio della collezione, o scrivi un nome nuovo",
              foreground="#666").pack(side="left")
    lbl_dir = ttk.Label(top, text="", foreground="#666")
    lbl_dir.grid(row=4, column=1, sticky="w", padx=4)
    V["name"].trace_add("write", lambda *a: lbl_dir.configure(text="Uscita: " + outdir()))
    V["collection"].trace_add("write", lambda *a: lbl_dir.configure(text="Uscita: " + outdir()))

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8)
    tab_o = ttk.Frame(nb, padding=4)
    tab_b = ttk.Frame(nb, padding=8)
    tab_h = ttk.Frame(nb, padding=8)
    nb.add(tab_o, text="  Outfit  ")
    nb.add(tab_b, text="  Corpo e budget  ")
    nb.add(tab_h, text="  Libreria capelli  ")

    # ================================================================== scheda Outfit
    pan = ttk.PanedWindow(tab_o, orient="horizontal")
    pan.pack(fill="both", expand=True)
    left = ttk.LabelFrame(pan, text="Capi nell'FBX (Ctrl/Maiusc + clic)", padding=4)
    mid = ttk.LabelFrame(pan, text="Outfit (un FBX per ogni outfit)", padding=4)
    prv = ttk.LabelFrame(pan, text="Anteprima", padding=4)
    pan.add(left, weight=2)
    pan.add(mid, weight=4)
    pan.add(prv, weight=0)
    ttk.Style().configure("Thumb.Treeview", rowheight=70)
    tree = ttk.Treeview(left, columns=("tris",), selectmode="extended", style="Thumb.Treeview", height=5)
    tree.heading("#0", text="Capo")
    tree.heading("tris", text="Triangoli")
    tree.column("#0", width=200)
    tree.column("tris", width=70, anchor="e")
    sb = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")
    olist = tk.Listbox(mid, height=4, exportselection=False)
    olist.pack(fill="x")
    ob = ttk.Frame(mid)
    ob.pack(fill="x", pady=3)
    sub = ttk.Notebook(mid)
    sub.pack(fill="both", expand=True)
    t_v = ttk.Frame(sub, padding=6)
    t_c = ttk.Frame(sub, padding=6)
    t_k = ttk.Frame(sub, padding=6)
    sub.add(t_v, text=" Vestiti ")
    sub.add(t_c, text=" Capelli ")
    sub.add(t_k, text=" Colori ")

    def scrollable(outer):
        """Contenuto che scorre (rotellina o barra) se la finestra e' bassa."""
        cv = tk.Canvas(outer, highlightthickness=0, borderwidth=0)
        sbar = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        inner = ttk.Frame(cv)
        win = cv.create_window(0, 0, window=inner, anchor="nw")
        cv.configure(yscrollcommand=sbar.set)
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>", lambda e: cv.itemconfigure(win, width=e.width))
        cv.pack(side="left", fill="both", expand=True)
        sbar.pack(side="left", fill="y")

        def wheel(e):
            if inner.winfo_height() > cv.winfo_height():
                cv.yview_scroll(-1 if (getattr(e, "delta", 0) > 0 or getattr(e, "num", 0) == 4) else 1, "units")
        for w_ in (cv, inner):
            w_.bind("<Enter>", lambda e: (root.bind_all("<MouseWheel>", wheel), root.bind_all("<Button-4>", wheel),
                                          root.bind_all("<Button-5>", wheel)))
            w_.bind("<Leave>", lambda e: (root.unbind_all("<MouseWheel>"), root.unbind_all("<Button-4>"),
                                          root.unbind_all("<Button-5>")))
        return inner
    t_c = scrollable(t_c)
    t_k = scrollable(t_k)
    lbl_est = tk.Label(mid, text="", anchor="w", justify="left", font=("TkDefaultFont", 9, "bold"))
    lbl_est.pack(fill="x", pady=(4, 0))

    # --- sotto-scheda Vestiti
    t_v.columnconfigure(1, weight=1)
    lbl_g = ttk.Label(t_v, text="", wraplength=470, justify="left")
    lbl_g.grid(row=0, column=0, columnspan=3, sticky="w")
    ttk.Label(t_v, text="Mesh1").grid(row=1, column=0, sticky="w")
    v_m1 = tk.StringVar()
    cb_m1 = ttk.Combobox(t_v, textvariable=v_m1, state="readonly", width=36)
    cb_m1.grid(row=1, column=1, sticky="w")
    ttk.Label(t_v, text="Triangoli").grid(row=2, column=0, sticky="nw")
    v_tris = tk.StringVar(value="3000")                # (non piu' usato: c'e' il cursore Vestiti)
    v_face = tk.DoubleVar(value=float(FACE_MAX))
    v_body = tk.DoubleVar(value=float(BODY_MAX))
    v_gar = tk.DoubleVar(value=3000.0)
    v_hpct = tk.DoubleVar(value=100.0)
    fq = ttk.Frame(t_v)
    fq.grid(row=2, column=1, columnspan=2, sticky="w")
    q_lab, q_sc = {}, {}
    for i_, (k_, t_, var_, lo_, hi_) in enumerate((("face", "Faccia", v_face, 300, FACE_MAX),
                                                  ("body", "Corpo (pelle visibile)", v_body, 300, BODY_MAX),
                                                  ("gar", "Vestiti (somma dei capi)", v_gar, 100, 3000),
                                                  ("hair", "Capelli %", v_hpct, 5, 100))):
        ttk.Label(fq, text=t_).grid(row=i_, column=0, sticky="w")
        sc_ = ttk.Scale(fq, from_=lo_, to=hi_, orient="horizontal", length=230, variable=var_,
                        command=lambda v, var_=var_, k_=k_: (var_.set(round(float(v)) if k_ == "hair"
                                                                   else round(float(v) / 10) * 10), quota_labels()))
        sc_.grid(row=i_, column=1, padx=4)
        q_sc[k_] = sc_
        q_lab[k_] = ttk.Label(fq, text="", width=30)
        q_lab[k_].grid(row=i_, column=2, sticky="w")
    ftr = ttk.Frame(t_v)
    ftr.grid(row=3, column=1, columnspan=2, sticky="w", pady=(2, 0))
    ttk.Label(ftr, text="Riduzione totale %").pack(side="left")
    v_ttot = tk.StringVar(value="100")
    sp_tt = ttk.Spinbox(ftr, from_=5, to=100, increment=5, textvariable=v_ttot, width=5)
    sp_tt.pack(side="left", padx=4)
    lbl_ttot = ttk.Label(ftr, text="", foreground="#555")
    lbl_ttot.pack(side="left")
    v_cull = tk.BooleanVar(value=True)
    fcull = ttk.Frame(t_v)
    fcull.grid(row=4, column=0, columnspan=3, sticky="w")
    ttk.Checkbutton(fcull, text="Togli la pelle nascosta sotto i vestiti", variable=v_cull).grid(row=0, column=0,
                                                                                                    columnspan=10, sticky="w")
    v_flat = tk.BooleanVar(value=False)
    ttk.Label(fcull, text="   in queste zone, lasciando un bordo attorno ai capi (cm):",
              foreground="#555").grid(row=1, column=0, columnspan=10, sticky="w")
    v_fa, v_ft = tk.DoubleVar(value=0.0), tk.DoubleVar(value=0.0)
    ffr = ttk.Frame(t_v)
    ffr.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
    ttk.Checkbutton(ffr, text="Scarpe chiuse: piede piatto", variable=v_flat).pack(side="left")
    ttk.Label(ffr, text="   ritocco (gradi, + = punta su):  caviglia").pack(side="left")
    lb_fa = ttk.Label(ffr, text="+0", width=4)
    ttk.Scale(ffr, from_=-30, to=30, orient="horizontal", length=120, variable=v_fa,
              command=lambda v: (v_fa.set(round(float(v))), lb_fa.configure(text="%+d" % v_fa.get()))).pack(side="left", padx=3)
    lb_fa.pack(side="left")
    ttk.Label(ffr, text="  dita e metatarso").pack(side="left")
    lb_ft = ttk.Label(ffr, text="+0", width=4)
    ttk.Scale(ffr, from_=-30, to=30, orient="horizontal", length=120, variable=v_ft,
              command=lambda v: (v_ft.set(round(float(v))), lb_ft.configure(text="%+d" % v_ft.get()))).pack(side="left", padx=3)
    lb_ft.pack(side="left")
    v_zone, v_cm = {}, {}
    for i, (z, lab) in enumerate((("neck", "collo"), ("torso", "busto"), ("arms", "braccia"), ("legs", "gambe"),
                                  ("feet", "piedi"))):
        v_zone[z] = tk.BooleanVar(value=True)
        v_cm[z] = tk.StringVar(value="3")
        ttk.Checkbutton(fcull, text=lab, variable=v_zone[z]).grid(row=2, column=2 * i, sticky="w", padx=(14 if i == 0 else 8, 0))
        ttk.Spinbox(fcull, from_=0, to=10, increment=0.5, textvariable=v_cm[z], width=4).grid(row=2, column=1 + 2 * i)
    ttk.Label(t_v, text="Dall'interno all'esterno (frecce: ordine di strati e mesh). Pelle = toglie la pelle sotto, "
                        "Acc. = accessorio", foreground="#555").grid(row=6, column=0, columnspan=3, sticky="w", pady=(6, 0))
    sl_frame = ttk.Frame(t_v)
    sl_frame.grid(row=7, column=0, columnspan=3, sticky="ew")
    sl_frame.columnconfigure(3, weight=1)
    grow = {}
    NOM1 = "(segnaposto, come i personaggi originali)"
    sliders = {}

    # --- sotto-scheda Capelli
    v_hair = tk.StringVar(value="(nessuno)")
    v_level = tk.StringVar(value="Alti")        # solo per i lavori vecchi
    v_htex = tk.StringVar(value="")
    v_auto = tk.BooleanVar(value=True)
    v_follow = tk.BooleanVar(value=True)
    v_hcull = tk.StringVar(value="colorata come i capelli")
    SCALP = [("colora", "colorata come i capelli"), ("togli", "tolta"), ("niente", "lasciata com'e'")]
    rc = ttk.Frame(t_c)
    rc.pack(fill="x")
    ttk.Label(rc, text="Capelli").pack(side="left")
    cb_ohair = ttk.Combobox(rc, textvariable=v_hair, state="readonly", width=26)
    cb_ohair.pack(side="left", padx=4)
    othumb = ttk.Label(rc)
    othumb.pack(side="left", padx=6)
    rl = ttk.Frame(t_c)
    rl.pack(fill="x", pady=3)
    ttk.Label(rl, text="Dettaglio: cursore \"Capelli %\" nella scheda Vestiti", foreground="#555").pack(side="left")

    def hair_lib_tris(name):
        try:
            return lib_tris(lib_path(name)) if name and name != "(nessuno)" else 0
        except NameError:                              # finestra non ancora completa
            return 0

    def hair_pct_label():
        quota_labels()

    def quota_labels():
        n = hair_lib_tris(v_hair.get())
        p_ = float(v_hpct.get())
        q_lab["hair"].configure(text=("%d%% = %d tri (libreria %d)" % (p_, round(n * p_ / 100.0), n)) if n else
                                ("%d%% (nessun capello)" % p_ if v_hair.get() in ("", "(nessuno)") else "%d%%" % p_))
        q_lab["face"].configure(text="%d tri (max %d)" % (v_face.get(), FACE_MAX))
        q_lab["body"].configure(text="%d tri (max %d)" % (v_body.get(), BODY_MAX))
        of_ = cur_outfit()
        gm = garments_max(of_) if of_ else 0
        q_sc["gar"].configure(to=max(200, gm))
        q_lab["gar"].configure(text="%d tri (max %d)" % (v_gar.get(), gm))

    def level_to_pct(h):
        """Lavori vecchi (Bassi/Medi/Alti): la percentuale che da' lo stesso numero di triangoli."""
        if h.get("pct") is not None:
            return float(h["pct"])
        n = hair_lib_tris(h.get("name", ""))
        want = dict(HAIR_LEVELS).get(h.get("level", "Alti"), 1000)
        return float(min(100, max(5, round(100.0 * want / n)))) if n else 100.0
    rt = ttk.Frame(t_c)
    rt.pack(fill="x", pady=3)
    ttk.Label(rt, text="Texture (vuoto = la sua)").pack(side="left")
    ttk.Entry(rt, textvariable=v_htex, width=30).pack(side="left", padx=4, fill="x", expand=True)
    ttk.Button(rt, text="Sfoglia...", command=lambda: (v_htex.set(filedialog.askopenfilename(
        filetypes=[("Immagini", "*.png *.jpg *.jpeg *.tga *.bmp"), ("Tutti", "*")]) or v_htex.get()), store_outfit())).pack(side="left")
    hair_color = ColorBox(t_c, "Colore dei capelli", "capelli")
    hair_color.frame.pack(fill="x", pady=4)
    fpos = ttk.LabelFrame(t_c, text="Ritocco della posizione (dopo l'adattamento automatico)", padding=4)
    fpos.pack(fill="x", pady=2)
    pos_sc, pos_lb = {}, {}
    for i, (k, lab, lo_, hi_) in enumerate((("sx", "Larghezza %", 80, 125), ("sy", "Altezza %", 80, 125),
                                             ("sz", "Profondita' %", 80, 125), ("dx", "Destra/sinistra cm", -4, 4),
                                             ("dy", "Su/giu' cm", -4, 4), ("dz", "Avanti/indietro cm", -4, 4))):
        ttk.Label(fpos, text=lab).grid(row=(i // 3) * 3, column=i % 3, sticky="w", padx=3)
        sc_ = ttk.Scale(fpos, from_=lo_, to=hi_, orient="horizontal", length=130,
                        command=lambda v, k=k: pos_lb[k].configure(text=("%.0f" if k[0] == "s" else "%+.1f") % float(v)))
        sc_.grid(row=(i // 3) * 3 + 1, column=i % 3, padx=3)
        sc_.bind("<ButtonRelease-1>", lambda e: store_soft())
        lb_ = ttk.Label(fpos, text="")
        lb_.grid(row=(i // 3) * 3 + 2, column=i % 3)
        pos_sc[k], pos_lb[k] = sc_, lb_

    def put_pos(h):
        for k in pos_sc:
            v = float(h.get(k, h.get("scale", 100.0) if k[0] == "s" else 0.0))
            pos_sc[k].set(v)
            pos_lb[k].configure(text=("%.0f" if k[0] == "s" else "%+.1f") % v)

    def reset_pos():
        put_pos({})
        store_soft()
    ttk.Button(fpos, text="Reimposta", command=reset_pos).grid(row=1, column=3, padx=6)
    ttk.Button(t_c, text="Crea capelli low poly dai capelli DAZ selezionati a sinistra...",
               command=lambda: make_shell()).pack(anchor="w", pady=(4, 2))
    for txt, v in (("Adatta automaticamente alla testa", v_auto), ("Parti lunghe (code) seguono il busto", v_follow)):
        ttk.Checkbutton(t_c, text=txt, variable=v).pack(anchor="w")
    rsc = ttk.Frame(t_c)
    rsc.pack(anchor="w", pady=2)
    ttk.Label(rsc, text="Pelle della testa sotto i capelli:").pack(side="left")
    ttk.Combobox(rsc, textvariable=v_hcull, values=[b for _, b in SCALP], state="readonly", width=24).pack(side="left", padx=4)
    ttk.Label(rsc, text="(colorata: tra le ciocche non si vede ne' pelle ne' sfondo)", foreground="#666").pack(side="left")

    # --- sotto-scheda Colori
    eyes_color = ColorBox(t_k, "Occhi (uguali per tutti gli outfit)", "occhi")
    eyes_color.frame.pack(fill="x")
    lips_color = ColorBox(t_k, "Labbra", "labbra", amount=True)
    lips_color.frame.pack(fill="x", pady=2)
    nails_color = ColorBox(t_k, "Unghie", "unghie")
    nails_color.frame.pack(fill="x", pady=2)
    makeup_color = ColorBox(t_k, "Trucco occhi (palpebra)", "trucco", amount=True)
    makeup_color.frame.pack(fill="x", pady=2)
    fext = ttk.Frame(makeup_color.frame)
    fext.pack(fill="x", pady=(4, 0))
    ttk.Label(fext, text="Area del trucco:  stretta").pack(side="left")
    v_ext = tk.DoubleVar(value=0.0)
    sc_ext = ttk.Scale(fext, from_=-100, to=100, orient="horizontal", length=220, variable=v_ext,
                       command=lambda v: lb_ext.configure(text="%+d" % round(float(v))))
    sc_ext.pack(side="left", padx=4)
    ttk.Label(fext, text="larga").pack(side="left")
    lb_ext = ttk.Label(fext, text="+0", width=5)
    lb_ext.pack(side="left", padx=4)
    ttk.Label(fext, text="(0 = palpebra mobile)", foreground="#666").pack(side="left")
    sc_ext.bind("<ButtonRelease-1>", lambda e: store_soft())

    # --- anteprima
    # (l'anteprima piccola della finestra non c'e' piu': resta solo quella 3D nel browser; i widget restano
    #  creati ma nascosti, cosi' il resto del codice non cambia)
    canvas = tk.Canvas(prv, width=240, height=300, bg="#707888", highlightthickness=0)
    rr = ttk.Frame(prv)
    btn_lp = ttk.Button(prv, text="Aggiorna anteprima")

    def show_view(i):
        state["prev_i"] = i % 8
        imgs = state["pv"]["imgs"]
        canvas.delete("all")
        if state["prev_i"] in imgs:
            canvas.create_image(0, 0, image=imgs[state["prev_i"]], anchor="nw")
        elif state["pv"]["key"] is not None:
            canvas.create_text(120, 150, text="...", fill="white", font=("TkDefaultFont", 16))
            request_views([state["prev_i"]])
    ttk.Button(rr, text="< Ruota", command=lambda: show_view(state["prev_i"] - 1)).pack(side="left", expand=True, fill="x")
    ttk.Button(rr, text="Ruota >", command=lambda: show_view(state["prev_i"] + 1)).pack(side="left", expand=True, fill="x")
    canvas.bind("<Button-1>", lambda e: show_view(state["prev_i"] + (1 if e.x > 120 else -1)))
    V["auto_prev"].set(False)
    ttk.Label(prv, text="Outfit finito in 3D,\nsi aggiorna da solo\nmentre modifichi.", justify="left").pack(anchor="w", pady=(0, 6))
    ttk.Button(prv, text="Anteprima 3D nel browser", command=lambda: open_3d()).pack(fill="x", ipady=8)
    lbl_pv = ttk.Label(prv, text="", foreground="#666")
    lbl_pv.pack(anchor="w")

    # ------------------------------------------------------------------ logica outfit
    def tree_name(i):
        return state["iname"].get(i) or tree.item(i, "text").replace("  (capelli DAZ)", "").strip()

    def sel_garments():
        return [tree_name(i) for i in tree.selection()]

    def cur_outfit():
        s = olist.curselection()
        return state["outfits"][s[0]] if s and s[0] < len(state["outfits"]) else None

    def preset_garment_tris():
        p = V["preset"].get()
        return PRESETS[p][1] if p in PRESETS else 3000

    def targets():
        out = {}
        for k, _ in ZONE_SHARE:
            try:
                out[k] = int(V["t_" + k].get())
            except ValueError:
                out[k] = 0
        return out

    def base_estimate():
        return sum(min(v, G8_MAX.get(k, v)) for k, v in targets().items())

    def ival(name, dv=0):
        try:
            return int(float(V[name].get()))
        except (ValueError, KeyError):
            return dv

    def fixed_estimate():
        """Occhi, orecchie, bocca, eyesocket, unghie, denti e ciglia: uguali per tutti gli outfit."""
        t = targets()
        n = sum(min(t.get(k, 0), G8_MAX.get(k, 10 ** 6)) for k in FIXED_ZONES)
        if V["keep_teeth"].get():
            n += ival("teeth_tris", 200)
        if V["keep_lashes"].get():
            n += ival("lash_tris", 150)
        return n

    def garments_max(of):
        return int(sum(state["orig"].get(g, 0) for g in (of or {}).get("garments", [])))

    def ensure_tris(of):
        """Triangoli di faccia, corpo e vestiti dell'outfit (cursori); se mancano: al massimo."""
        of.setdefault("face_tris", FACE_MAX)
        if of.get("body_tris") is None:
            of["body_tris"] = BODY_MAX
        if of.get("tris_v29") is None:                # lavori di prima: vestiti al massimo
            of["tris"] = garments_max(of) or int(of.get("tris", 3000))
            of["tris_v29"] = True
        of["face_tris"] = int(min(FACE_MAX, max(100, int(of["face_tris"]))))
        of["body_tris"] = int(min(BODY_MAX, max(100, int(of["body_tris"]))))
        gm = garments_max(of)
        if gm:
            of["tris"] = int(min(gm, int(of["tris"])))
        return of

    def hair_estimate(of):
        h = (of or {}).get("hair") or {}
        if not h.get("name"):
            return 0
        n = hair_lib_tris(h["name"])
        if h.get("pct") is not None and n:
            return int(round(n * float(h["pct"]) / 100.0))
        return min(n or 10 ** 6, dict(HAIR_LEVELS).get(h.get("level", "Alti"), 1000))

    def total_pct(of):
        try:
            return max(5.0, min(100.0, float((of or {}).get("total_pct", 100.0) or 100.0)))
        except ValueError:
            return 100.0

    def ensure_shares(of):
        """Quote dei capi in % (somma 100). Lavori della 2.1 (triangoli per capo): convertiti in quote."""
        gt = of.pop("gtris", None)
        if gt and set(gt) == set(of["garments"]):
            tot = float(sum(gt.values())) or 1.0
            of["shares"] = {g: 100.0 * gt[g] / tot for g in of["garments"]}
            of["tris"] = int(tot)
        sh = of.setdefault("shares", {})
        for g in of["garments"]:
            sh.setdefault(g, 100.0 / len(of["garments"]))
        for g in [g for g in sh if g not in of["garments"]]:
            sh.pop(g)
        tot = sum(sh[g] for g in of["garments"]) or 1.0
        for g in of["garments"]:
            sh[g] = sh[g] * 100.0 / tot
        return sh

    def outfit_alloc(of):
        ensure_tris(of)
        sh = ensure_shares(of)
        items = [(g, state["orig"].get(g, 10 ** 6), sh.get(g, 0.0)) for g in of["garments"]]
        return split_shares(of.get("tris", 3000), items) if items else {}

    def scale_gtris(of, total):
        of["tris"] = int(total)

    def full_estimate(of):
        ensure_tris(of)
        return fixed_estimate() + of["face_tris"] + hair_estimate(of) + of["body_tris"] + sum(outfit_alloc(of).values())

    def estimate(of):
        return int(round(full_estimate(of) * total_pct(of) / 100.0))

    def limit():
        try:
            return int(V["limit"].get())
        except ValueError:
            return 0

    def refresh_estimate(*_):
        of = cur_outfit()
        lines = []
        for o in state["outfits"]:
            e = estimate(o)
            ensure_tris(o)
            rl = state["real"].get(o["name"])
            lines.append("%s: ~%d (faccia %d + occhi ecc. %d + corpo %d + vestiti %d + capelli %d%s)%s" % (
                o["name"], e, o["face_tris"], fixed_estimate(), o["body_tris"], sum(outfit_alloc(o).values()),
                hair_estimate(o), (", poi totale al %d%%" % total_pct(o)) if total_pct(o) < 99.5 else "",
                ("  -> reale %d (%s)" % rl) if rl else ""))
        over = False
        lbl_est.configure(text=("Triangoli per outfit (stima prima della pulizia; reale = ultima anteprima "
                                "o conversione):\n" + "\n".join(lines)) if lines else
                          "Stima: corpo e faccia ~%d" % base_estimate(), fg="#c0392b" if over else "#1e6b30")
        if of is not None:
            full = full_estimate(of)
            quota_labels()
            lbl_ttot.configure(text="~%d -> ~%d tri" % (full, estimate(of)) if total_pct(of) < 99.5 else
                               "(100%% = ~%d tri)" % full)
            hair_pct_label()
            al = outfit_alloc(of)
            for g, (sc, lab) in sliders.items():
                lab.configure(text="%3.0f%%  %5d tri" % (of["shares"].get(g, 0), al.get(g, 0)))
        tot_lbl.configure(text="Occhi, orecchie, bocca, eyesocket, unghie, denti e ciglia: ~%d triangoli" % fixed_estimate())

    def layer_order(of):
        """Ordine degli strati (dall'interno): quello scelto con le frecce, altrimenti per distanza dalla pelle."""
        lay = [g for g in (of.get("layers") or []) if g in of["garments"]]
        rest = sorted([g for g in of["garments"] if g not in lay], key=lambda g: state["depth"].get(g, 0.0))
        of["layers"] = lay + rest
        return of["layers"]

    def adjust_dialog(g):
        """Spostamento e scala di un capo in questo outfit (es. anelli e bracciali fuori posto)."""
        of = cur_outfit()
        if of is None:
            return
        cur = dict((of.get("adjust") or {}).get(g) or {})
        dlg = tk.Toplevel(root)
        dlg.title("Posizione: %s (%s)" % (short_name(g), of["name"]))
        dlg.transient(root)
        dlg.geometry("+%d+%d" % (root.winfo_rootx() + 380, root.winfo_rooty() + 300))
        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both")
        ttk.Label(frm, text="%s nell'outfit '%s'. L'anteprima 3D si aggiorna quando lasci il cursore." % (
            short_name(g), of["name"]), foreground="#555").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        scs = {}

        def save(*_):
            v = {k: round(float(scs[k][0].get()), 2 if k != "scale" else 1) for k in scs}
            o2 = cur_outfit()
            if o2 is None:
                return
            if abs(v["scale"] - 100) < 0.05 and not any(abs(v[k]) > 0.001 for k in ("dx", "dy", "dz")):
                (o2.get("adjust") or {}).pop(g, None)
            else:
                o2.setdefault("adjust", {})[g] = v
            store_soft()

        def show(k):
            val = float(scs[k][0].get())
            scs[k][1].configure(text=("%.0f %%" if k == "scale" else "%+.1f cm") % val)
        for i, (k, lab, lo_, hi_, dv) in enumerate((("dx", "Destra / sinistra", -5, 5, 0.0), ("dy", "Su / giu'", -5, 5, 0.0),
                                                     ("dz", "Avanti / indietro", -5, 5, 0.0), ("scale", "Scala", 50, 150, 100.0))):
            ttk.Label(frm, text=lab).grid(row=i + 1, column=0, sticky="w")
            sc_ = ttk.Scale(frm, from_=lo_, to=hi_, orient="horizontal", length=260, command=lambda v, k=k: show(k))
            sc_.grid(row=i + 1, column=1, padx=6, pady=2)
            lb_ = ttk.Label(frm, text="", width=9)
            lb_.grid(row=i + 1, column=2, sticky="w")
            scs[k] = (sc_, lb_)
            sc_.set(float(cur.get(k, dv)))
            show(k)
            sc_.bind("<ButtonRelease-1>", save)
        bf = ttk.Frame(frm)
        bf.grid(row=6, column=0, columnspan=3, pady=(8, 0), sticky="e")

        def reset():
            for k, (sc_, _) in scs.items():
                sc_.set(100.0 if k == "scale" else 0.0)
                show(k)
            save()

        def nudge(k, d):
            sc_ = scs[k][0]
            sc_.set(float(sc_.get()) + d)
            show(k)
            save()
        fine = ttk.Frame(frm)
        fine.grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(fine, text="Passo fine (1 mm):").pack(side="left")
        for k, lab in (("dx", "x"), ("dy", "y"), ("dz", "z")):
            ttk.Button(fine, text=lab + " -", width=4, command=lambda k=k: nudge(k, -0.1)).pack(side="left", padx=(6, 0))
            ttk.Button(fine, text=lab + " +", width=4, command=lambda k=k: nudge(k, 0.1)).pack(side="left")
        ttk.Button(bf, text="Reimposta", command=reset).pack(side="left", padx=4)
        ttk.Button(bf, text="Chiudi", command=lambda: (save(), dlg.destroy(), build_sliders(cur_outfit()),
                                                      refresh_estimate())).pack(side="left")

    def style_dialog(g):
        """Texture personalizzata (stessa UV) e colore di tutto il capo, in questo outfit."""
        of = cur_outfit()
        if of is None:
            return
        cur = dict((of.get("style") or {}).get(g) or {})
        dlg = tk.Toplevel(root)
        dlg.title("Texture e colore: %s (%s)" % (short_name(g), of["name"]))
        dlg.transient(root)
        dlg.geometry("+%d+%d" % (root.winfo_rootx() + 340, root.winfo_rooty() + 260))
        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill="both")
        ttk.Label(frm, text="%s nell'outfit '%s'. Il colore si vede subito nell'anteprima 3D; la texture dopo "
                  "l'aggiornamento." % (short_name(g), of["name"]), foreground="#555",
                  wraplength=430).pack(anchor="w", pady=(0, 6))
        tf = ttk.LabelFrame(frm, text="Texture personalizzata (stessa UV dell'originale, per tutto il capo)", padding=4)
        tf.pack(fill="x")
        v_tex = tk.StringVar(value=cur.get("tex", ""))
        ttk.Entry(tf, textvariable=v_tex, width=44).pack(side="left", fill="x", expand=True)

        def save(*_):
            o2 = cur_outfit()
            if o2 is None:
                return
            st = {"tex": v_tex.get().strip(), "color": cbox.get()}
            st = {k: v for k, v in st.items() if v}
            if st:
                o2.setdefault("style", {})[g] = st
            else:
                (o2.get("style") or {}).pop(g, None)
            store_soft()

        def pick():
            f = filedialog.askopenfilename(parent=dlg, title="Texture per " + short_name(g),
                                           filetypes=[("Immagini", "*.png *.jpg *.jpeg *.tga *.bmp *.tif *.tiff"), ("Tutti", "*")])
            if f:
                v_tex.set(f)
                save()
        ttk.Button(tf, text="Sfoglia...", command=pick).pack(side="left", padx=4)
        ttk.Button(tf, text="Togli", command=lambda: (v_tex.set(""), save())).pack(side="left")
        cbox = ColorBox(frm, "Colore di tutto il capo", "vestiti", amount=True)
        cbox.frame.pack(fill="x", pady=(8, 0))
        cbox.put(cur.get("color"), False)
        cbox.cb = save
        bf = ttk.Frame(frm)
        bf.pack(anchor="e", pady=(8, 0))
        ttk.Button(bf, text="Chiudi", command=lambda: (save(), dlg.destroy(), build_sliders(cur_outfit()))).pack(side="left")

    def move_layer(g, d):
        of = cur_outfit()
        if of is None:
            return
        lay = layer_order(of)
        i = lay.index(g)
        j = i + d
        if 0 <= j < len(lay):
            lay[i], lay[j] = lay[j], lay[i]
            build_sliders(of)
            refresh_estimate()

    def build_sliders(of):
        for w in sl_frame.winfo_children():
            w.destroy()
        sliders.clear()
        grow.clear()
        if of is None:
            return
        sh = ensure_shares(of)
        tr = of.get("transparent") or {}
        nc = set(of.get("no_cull") or [])
        rg = set(of.get("rigid") or [])
        ac = set(of.get("acc") or [])
        adj = of.get("adjust") or {}
        for c, t in ((2, "Capo"), (3, "Quota"), (5, "Pelle"), (6, "Trasp. %"), (8, "Acc."), (9, "Rigido"),
                     (12, "Lenti"), (13, "Osso")):
            ttk.Label(sl_frame, text=t, foreground="#555").grid(row=0, column=c, columnspan=2 if c == 6 else 1, sticky="w")
        for r, g in enumerate(layer_order(of), start=1):
            ttk.Button(sl_frame, text="\u2191", width=2, command=lambda g=g: move_layer(g, -1)).grid(row=r, column=0)
            ttk.Button(sl_frame, text="\u2193", width=2, command=lambda g=g: move_layer(g, 1)).grid(row=r, column=1)
            ttk.Label(sl_frame, text=("%d. " % r) + short_name(g)[:18]).grid(row=r, column=2, sticky="w", padx=(2, 4))
            sc = ttk.Scale(sl_frame, from_=0, to=100, orient="horizontal", length=110)
            sc.set(sh[g])
            sc.grid(row=r, column=3, sticky="ew", padx=4)
            lab = ttk.Label(sl_frame, text="", width=11)
            lab.grid(row=r, column=4, sticky="w")
            v_nc = tk.BooleanVar(value=g not in nc)
            ttk.Checkbutton(sl_frame, variable=v_nc, command=store_soft).grid(row=r, column=5)
            v_tr = tk.BooleanVar(value=g in tr)
            v_op = tk.StringVar(value=str(int(tr.get(g, 60))))
            ttk.Checkbutton(sl_frame, variable=v_tr, command=store_soft).grid(row=r, column=6, sticky="e")
            sp = ttk.Spinbox(sl_frame, from_=0, to=100, increment=5, textvariable=v_op, width=4, command=store_soft)
            sp.grid(row=r, column=7, sticky="w")
            sp.bind("<FocusOut>", lambda e: store_soft())
            sp.bind("<Return>", lambda e: store_soft())
            v_ac = tk.BooleanVar(value=g in ac)
            ttk.Checkbutton(sl_frame, variable=v_ac, command=store_soft).grid(row=r, column=8)
            v_rg = tk.BooleanVar(value=g in rg)

            def on_rigid(v_rg=v_rg, v_ac=v_ac):
                if v_rg.get():
                    v_ac.set(True)                       # un accessorio rigido e' anche un accessorio
                store_soft()
                root.after_idle(lambda: build_sliders(cur_outfit()))   # mostra/nasconde il menu dell'osso
            ttk.Checkbutton(sl_frame, variable=v_rg, command=on_rigid).grid(row=r, column=9)
            a_ = adj.get(g) or {}
            moved = abs(float(a_.get("scale", 100)) - 100) > 0.01 or any(abs(float(a_.get(k, 0))) > 0.001 for k in ("dx", "dy", "dz"))
            ttk.Button(sl_frame, text=("Sposta*" if moved else "Sposta"), width=7,
                       command=lambda g=g: adjust_dialog(g)).grid(row=r, column=10, padx=(4, 0))
            styled = bool(((of.get("style") or {}).get(g) or {}))
            ttk.Button(sl_frame, text=("Colore*" if styled else "Colore"), width=7,
                       command=lambda g=g: style_dialog(g)).grid(row=r, column=11, padx=(2, 0))
            if (state.get("lens") or {}).get(g):
                LMODES = [("trasparenti", "trasparenti"), ("togli", "togli"), ("opache", "opache")]
                v_ln = tk.StringVar(value=(of.get("lenses") or {}).get(g, "trasparenti"))
                cl = ttk.Combobox(sl_frame, textvariable=v_ln, values=[b for _, b in LMODES], state="readonly", width=10)
                cl.grid(row=r, column=12, padx=(4, 0))

                def on_lens(e=None, g=g, v_ln=v_ln):
                    o2 = cur_outfit()
                    if o2 is not None:
                        o2.setdefault("lenses", {})[g] = v_ln.get()
                        store_soft()
                cl.bind("<<ComboboxSelected>>", on_lens)
            if g in rg:
                BONES = ["automatico"] + ["%s %s" % (n, NODE_LABELS[n]) for n in BONE_ORDER]
                cur_b = (of.get("rigid_bone") or {}).get(g)
                v_bn = tk.StringVar(value=next((b for b in BONES if b.split()[0] == cur_b), "automatico"))
                cbn = ttk.Combobox(sl_frame, textvariable=v_bn, values=BONES, state="readonly", width=16)
                cbn.grid(row=r, column=13, padx=(4, 0))

                def on_bone(e=None, g=g, v_bn=v_bn):
                    o2 = cur_outfit()
                    if o2 is None:
                        return
                    b = v_bn.get().split()[0]
                    if b in BONE_ORDER:
                        o2.setdefault("rigid_bone", {})[g] = b
                    else:
                        (o2.get("rigid_bone") or {}).pop(g, None)
                    store_soft()
                cbn.bind("<<ComboboxSelected>>", on_bone)
            sliders[g] = (sc, lab)
            grow[g] = (v_nc, v_tr, v_op, v_rg, v_ac)
            sc.configure(command=lambda val, g=g: on_slider(g, float(val)))

    def on_slider(g, val):
        """Quote collegate: la somma resta 100%, gli altri capi si adattano in proporzione."""
        if state["lock"]:
            return
        of = cur_outfit()
        if of is None:
            return
        sh = ensure_shares(of)
        others = [x for x in of["garments"] if x != g]
        if not others:
            val = 100.0
        old = sum(sh[x] for x in others)
        rest = 100.0 - val
        for x in others:
            sh[x] = rest * sh[x] / old if old > 1e-6 else rest / len(others)
        sh[g] = val
        state["lock"] = True
        for x in others:
            sliders[x][0].set(sh[x])
        state["lock"] = False
        refresh_estimate()

    def refresh_outfits(select=None):
        olist.delete(0, "end")
        for of in state["outfits"]:
            olist.insert("end", "%s  (%d capi%s)" % (of["name"], len(of["garments"]),
                                                    ", capelli: %s" % of["hair"]["name"] if (of.get("hair") or {}).get("name") else ""))
        if select is not None and state["outfits"]:
            olist.selection_clear(0, "end")
            olist.selection_set(select)
            olist.see(select)
        show_outfit()

    def show_outfit(*_):
        of = cur_outfit()
        state["lock"] = True
        if of is None:
            lbl_g.configure(text="Seleziona i capi a sinistra e premi \"Nuovo outfit\".")
            cb_m1.configure(values=[])
            v_m1.set("")
            state["lock"] = False
            build_sliders(None)
            refresh_estimate()
            return
        lbl_g.configure(text="Capi: " + ", ".join(short_name(g) for g in of["garments"]))
        cb_m1.configure(values=[NOM1] + of["garments"])
        v_m1.set(of.get("mesh1") or NOM1)
        v_tris.set(str(of.get("tris", preset_garment_tris())))
        ensure_tris(of)
        v_face.set(of["face_tris"])
        v_body.set(of["body_tris"])
        v_gar.set(of["tris"])
        v_ttot.set(("%.0f" % total_pct(of)))
        v_cull.set(bool(of.get("cull_body", True)))
        v_flat.set(bool(of.get("flat_feet", False)))
        v_fa.set(float(of.get("feet_ankle", 0.0)))
        v_ft.set(float(of.get("feet_toes", 0.0)))
        lb_fa.configure(text="%+d" % v_fa.get())
        lb_ft.configure(text="%+d" % v_ft.get())
        cz = of.get("cull_zones") or {}
        for z in v_zone:
            v_zone[z].set(bool(cz.get(z, True)))
        for z, v in cull_margins(of).items():
            if z in v_cm:
                v_cm[z].set(("%.1f" % v).rstrip("0").rstrip("."))
        h = of.get("hair") or {}
        v_hair.set(h.get("name") or "(nessuno)")
        v_level.set(h.get("level", "Alti"))
        v_hpct.set(level_to_pct(h))
        hair_pct_label()
        v_htex.set(h.get("tex", ""))
        v_auto.set(h.get("autofit", True))
        v_follow.set(h.get("follow", True))
        v_hcull.set(dict(SCALP)[scalp_mode(h)])
        put_pos(h)
        state["lock"] = False
        hair_color.put(h.get("color"), False)
        lk = of.get("looks") or {}
        lips_color.put(lk.get("lips"), False)
        nails_color.put(lk.get("nails"), False)
        makeup_color.put(lk.get("makeup"), False)
        v_ext.set(float((lk.get("makeup") or {}).get("ext", 0.0)))
        lb_ext.configure(text="%+d" % round(v_ext.get()))
        show_othumb()
        build_sliders(of)
        refresh_estimate()

    def store_outfit(*_):
        if sync_outfit():
            refresh_estimate()
            schedule_preview()

    def sync_outfit():
        """Copia nei dati dell'outfit quello che c'e' nella finestra (senza effetti collaterali)."""
        of = cur_outfit()
        if of is None or state["lock"]:
            return False
        m1 = v_m1.get()
        of["mesh1"] = "" if (not m1 or m1 == NOM1) else m1
        of["face_tris"] = int(v_face.get())
        of["body_tris"] = int(v_body.get())
        of["tris"] = int(v_gar.get())
        of["tris_v29"] = True
        try:
            of["total_pct"] = max(5.0, min(100.0, float(v_ttot.get())))
        except ValueError:
            pass
        of["cull_body"] = bool(v_cull.get())
        of["flat_feet"] = bool(v_flat.get())
        of["feet_ankle"] = round(float(v_fa.get()))
        of["feet_toes"] = round(float(v_ft.get()))
        of["cull_zones"] = {z: bool(v.get()) for z, v in v_zone.items()}
        cm = {}
        for z, v in v_cm.items():
            try:
                cm[z] = max(0.0, float(v.get()))
            except ValueError:
                pass
        of["cull_margins"] = cm
        if grow and set(grow) == set(of["garments"]):
            of["no_cull"] = [g for g, (v_nc, _, _, _, _) in grow.items() if not v_nc.get()]
            of["rigid"] = [g for g, (_, _, _, v_rg, _) in grow.items() if v_rg.get()]
            of["acc"] = [g for g, (_, _, _, _, v_ac) in grow.items() if v_ac.get()]
            tr = {}
            for g, (_, v_tr, v_op, _, _) in grow.items():
                if v_tr.get():
                    try:
                        tr[g] = max(0, min(100, int(float(v_op.get()))))
                    except ValueError:
                        tr[g] = 60
            of["transparent"] = tr
        hn = v_hair.get()
        of["hair"] = {"name": "" if hn == "(nessuno)" else hn, "pct": round(float(v_hpct.get())), "tex": v_htex.get().strip(),
                      "color": hair_color.get(), "autofit": bool(v_auto.get()), "follow": bool(v_follow.get()),
                      "scalp": {b: a for a, b in SCALP}.get(v_hcull.get(), "colora")}
        for k in pos_sc:
            of["hair"][k] = round(float(pos_sc[k].get()), 1)
        of["hair"].pop("scale", None)
        mk = makeup_color.get()
        if mk:
            mk["ext"] = round(float(v_ext.get()))
        of["looks"] = {"lips": lips_color.get(), "nails": nails_color.get(), "makeup": mk}
        state["eyes"] = eyes_color.get()
        return True

    def store_soft(*_):
        if not state["lock"]:
            store_outfit()
    for w in (hair_color, lips_color, nails_color, makeup_color, eyes_color):
        w.cb = store_soft
    cb_m1.bind("<<ComboboxSelected>>", store_soft)
    for v in (v_face, v_body, v_gar, v_ttot, v_cull, v_flat, v_fa, v_ft, v_hpct, v_auto, v_follow, v_hcull) + tuple(v_zone.values()) + tuple(v_cm.values()):
        v.trace_add("write", store_soft)
    olist.bind("<<ListboxSelect>>", lambda e: (show_outfit(), schedule_preview()))

    def on_hair_pick(*_):
        show_othumb()
        store_soft()
    cb_ohair.bind("<<ComboboxSelected>>", on_hair_pick)

    def show_othumb():
        p = os.path.join(V["hairlib"].get(), v_hair.get() + ".png")
        if v_hair.get() != "(nessuno)" and os.path.isfile(p):
            try:
                state["othumb"] = tk.PhotoImage(file=p).subsample(2, 2)
                othumb.configure(image=state["othumb"])
                return
            except Exception:
                pass
        othumb.configure(image="")

    def new_outfit():
        g = sel_garments()
        if not g:
            messagebox.showinfo("daz2ob", "Seleziona prima i capi dell'outfit nella lista a sinistra.")
            return
        nm = simpledialog.askstring("Nuovo outfit", "Nome dell'outfit:", parent=root,
                                    initialvalue="outfit%d" % (len(state["outfits"]) + 1))
        if not nm:
            return
        prev = cur_outfit()
        state["outfits"].append({"name": nm, "garments": g, "mesh1": "", "tris": preset_garment_tris(),
                                 "tris_auto": True, "cull_body": True, "shares": {x: 100.0 / len(g) for x in g},
                                 "layers": sorted(g, key=lambda x: state["depth"].get(x, 0.0)),
                                 "hair": dict(prev["hair"]) if prev and prev.get("hair") else {},
                                 "looks": dict(prev["looks"]) if prev and prev.get("looks") else {}})
        refresh_outfits(len(state["outfits"]) - 1)
        schedule_preview()

    def update_outfit():
        of = cur_outfit()
        g = sel_garments()
        if of is None or not g:
            return
        of["garments"] = g
        of["shares"] = {x: 100.0 / len(g) for x in g}
        of["layers"] = [x for x in (of.get("layers") or []) if x in g]
        of["transparent"] = {x: v for x, v in (of.get("transparent") or {}).items() if x in g}
        of["no_cull"] = [x for x in (of.get("no_cull") or []) if x in g]
        of["rigid"] = [x for x in (of.get("rigid") or []) if x in g]
        of["style"] = {x: v for x, v in (of.get("style") or {}).items() if x in g}
        of["rigid_bone"] = {x: v for x, v in (of.get("rigid_bone") or {}).items() if x in g}
        of["acc"] = [x for x in (of.get("acc") or []) if x in g]
        of["lenses"] = {x: v for x, v in (of.get("lenses") or {}).items() if x in g}
        of["adjust"] = {x: v for x, v in (of.get("adjust") or {}).items() if x in g}
        if of.get("mesh1") not in g:
            of["mesh1"] = ""
        refresh_outfits(state["outfits"].index(of))

    def rename_outfit():
        of = cur_outfit()
        if of is None:
            return
        nm = simpledialog.askstring("Rinomina", "Nuovo nome:", parent=root, initialvalue=of["name"])
        if nm:
            of["name"] = nm
            refresh_outfits(state["outfits"].index(of))

    def del_outfit():
        of = cur_outfit()
        if of is not None:
            state["outfits"].remove(of)
            refresh_outfits()

    def equal_shares():
        """Parti uguali: la 'quota accessori' (es. 25%) divisa tra gli accessori, il resto tra i capi principali."""
        of = cur_outfit()
        if of is None or not of["garments"]:
            return
        store_outfit()
        acc = [g for g in of["garments"] if g in set(of.get("acc") or [])]
        main = [g for g in of["garments"] if g not in acc]
        try:
            q = max(0.0, min(100.0, float(V["acc_quota"].get())))
        except ValueError:
            q = 25.0
        if not acc or not main:
            q = 100.0 if acc else 0.0
        sh = {}
        for g in main:
            sh[g] = (100.0 - q) / len(main)
        for g in acc:
            sh[g] = q / len(acc)
        of["shares"] = sh
        build_sliders(of)
        refresh_estimate()

    def pick_outfit_garments():
        of = cur_outfit()
        if of is not None:
            tree.selection_set([i for i in tree.get_children() if tree_name(i) in of["garments"]])
    for txt, fn in (("Nuovo outfit", new_outfit), ("Sostituisci i capi", update_outfit),
                    ("Mostra i capi", pick_outfit_garments), ("Parti uguali", equal_shares)):
        ttk.Button(ob, text=txt, command=fn).pack(side="left", padx=(0, 3))
    ttk.Label(ob, text="accessori").pack(side="left")
    ttk.Spinbox(ob, from_=0, to=100, increment=5, textvariable=V["acc_quota"], width=4).pack(side="left", padx=(2, 0))
    ttk.Label(ob, text="%").pack(side="left", padx=(0, 8))
    for txt, fn in (("Rinomina", rename_outfit), ("Elimina", del_outfit)):
        ttk.Button(ob, text=txt, command=fn).pack(side="left", padx=(0, 3))

    # ================================================================== scheda Corpo e budget
    fb = ttk.LabelFrame(tab_b, text="Parti fisse (uguali per tutti gli outfit; faccia, corpo, vestiti e capelli: "
                                    "nella scheda Vestiti di ogni outfit)", padding=6)
    fb.pack(fill="x")
    r1 = ttk.Frame(fb)
    r1.pack(fill="x", pady=4)
    zone_entries = []
    for i, k in enumerate(FIXED_ZONES):
        ttk.Label(r1, text=ZONE_LABEL[k]).grid(row=0, column=i, sticky="w", padx=4)
        e = ttk.Entry(r1, textvariable=V["t_" + k], width=7)
        e.grid(row=1, column=i, sticky="w", padx=4)
        zone_entries.append(e)
        V["t_" + k].trace_add("write", lambda *a: refresh_estimate())
    tot_lbl = ttk.Label(fb, text="")
    tot_lbl.pack(anchor="w")
    fo = ttk.LabelFrame(tab_b, text="Texture, pesi e vestiti", padding=6)
    fo.pack(fill="x")
    rr1 = ttk.Frame(fo)
    rr1.pack(fill="x")
    ttk.Label(rr1, text="Atlas corpo").pack(side="left")
    ttk.Combobox(rr1, textvariable=V["atlas_base"], values=["256", "512", "1024"], width=6, state="readonly").pack(side="left", padx=4)
    ttk.Label(rr1, text="  Atlas vestiti").pack(side="left")
    ttk.Combobox(rr1, textvariable=V["atlas_outfit"], values=["128", "256", "512"], width=6, state="readonly").pack(side="left", padx=4)
    ttk.Checkbutton(rr1, text="Braccio e gamba destri sulla texture dei sinistri", variable=V["mirror"]).pack(side="left", padx=10)
    ttk.Label(rr1, text="Ambient").pack(side="left")
    ttk.Entry(rr1, textvariable=V["ambient"], width=4).pack(side="left", padx=4)
    rr2 = ttk.Frame(fo)
    rr2.pack(fill="x", pady=4)
    ttk.Label(rr2, text="Sopracciglia interne/esterne").pack(side="left")
    ttk.Entry(rr2, textvariable=V["brow_side"], width=5).pack(side="left", padx=4)
    ttk.Label(rr2, text="  Morbidezza giunture (x, 0 = pesi DAZ)").pack(side="left")
    ttk.Entry(rr2, textvariable=V["joint_smooth"], width=5).pack(side="left", padx=4)
    ttk.Label(rr2, text="  Margine pelle-vestiti (mm)").pack(side="left")
    ttk.Entry(rr2, textvariable=V["margin_mm"], width=5).pack(side="left", padx=4)
    ttk.Checkbutton(rr2, text="Vestiti con i pesi della pelle sotto", variable=V["wfb"]).pack(side="left", padx=10)
    rr3 = ttk.Frame(fo)
    rr3.pack(fill="x", pady=4)
    ttk.Label(rr3, text="Spazio per i capelli nell'atlas del corpo (pixel)").pack(side="left")
    ttk.Entry(rr3, textvariable=V["hair_slot"], width=6).pack(side="left", padx=4)
    ttk.Label(rr3, text="   Senza capelli in nessun outfit: spazio vuoto riservato (pixel, 0 = no)").pack(side="left")
    ttk.Entry(rr3, textvariable=V["hair_reserve"], width=6).pack(side="left", padx=4)
    rr4 = ttk.Frame(fo)
    rr4.pack(fill="x", pady=4)
    ttk.Checkbutton(rr4, text="Tieni le ciglia (trasparenti), triangoli:", variable=V["keep_lashes"]).pack(side="left")
    ttk.Entry(rr4, textvariable=V["lash_tris"], width=6).pack(side="left", padx=4)
    ttk.Label(rr4, text="   (ciglia nell'atlas del corpo, capi trasparenti in quello dei vestiti: 2 texture per outfit)",
              foreground="#666").pack(side="left")
    rr5 = ttk.Frame(fo)
    rr5.pack(fill="x", pady=4)
    ttk.Checkbutton(rr5, text="Tieni i denti (uniti alla bocca), triangoli:", variable=V["keep_teeth"]).pack(side="left")
    ttk.Entry(rr5, textvariable=V["teeth_tris"], width=6).pack(side="left", padx=4)
    fa = ttk.LabelFrame(tab_b, text="Braccia e spalle", padding=6)
    fa.pack(fill="x", pady=(6, 0))
    ttk.Checkbutton(fa, text="Braccia centrate sulle ossa e polso come i personaggi originali (P06)",
                    variable=V["arms_p06"]).pack(side="left")
    ttk.Label(fa, text="   Alza le spalle (gradi)").pack(side="left")
    ttk.Entry(fa, textvariable=V["shoulder_lift"], width=5).pack(side="left", padx=4)
    ttk.Label(fa, text="  Spalla: il braccio inizia piu' in fuori di (cm)").pack(side="left")
    ttk.Entry(fa, textvariable=V["shoulder_shift"], width=5).pack(side="left", padx=4)
    fa2 = ttk.Frame(tab_b, padding=(6, 2))
    fa2.pack(fill="x")
    ttk.Label(fa2, text="Pesi di spalla e ascella:").pack(side="left")
    ttk.Combobox(fa2, textvariable=V["shoulder_mode"], values=[b for _, b in SHMODES], state="readonly",
                 width=22).pack(side="left", padx=4)
    ttk.Label(fa2, text="  quanto sfumati (0.5 - 4)").pack(side="left")
    e_smooth = ttk.Entry(fa2, textvariable=V["shoulder_smooth"], width=5)
    e_smooth.pack(side="left", padx=4)
    # con "come DAZ" lo sfumato non si usa: campo grigio
    V["shoulder_mode"].trace_add("write", lambda *a: e_smooth.configure(
        state="disabled" if V["shoulder_mode"].get() == "come DAZ" else "normal"))
    e_smooth.configure(state="disabled" if V["shoulder_mode"].get() == "come DAZ" else "normal")
    fl2 = ttk.LabelFrame(tab_b, text="Viso", padding=6)
    fl2.pack(fill="x", pady=(6, 0))
    ttk.Label(fl2, text="Labbro inferiore centrale (LipLowerMiddle) sulla mascella Node27:").pack(side="left")
    ttk.Scale(fl2, from_=0.0, to=1.0, orient="horizontal", length=180, variable=V["lip27"],
              command=lambda v: lb27.configure(text="%.2f" % float(v))).pack(side="left", padx=4)
    lb27 = ttk.Label(fl2, text="%.2f" % V["lip27"].get(), width=5)
    lb27.pack(side="left")
    ttk.Label(fl2, text="(il resto va alla testa, Node21)", foreground="#666").pack(side="left")
    fbr = ttk.Frame(tab_b, padding=(6, 4))
    fbr.pack(fill="x")
    ttk.Label(fbr, text="Sopracciglia (dipinte nella texture):").pack(side="left")
    ttk.Combobox(fbr, textvariable=V["brow_mode"], values=[b for _, b in BROW_MODES], state="readonly",
                 width=34).pack(side="left", padx=4)
    ttk.Scale(fbr, from_=0, to=100, orient="horizontal", length=150, variable=V["brow_amt"],
              command=lambda v: (V["brow_amt"].set(round(float(v) / 5) * 5), brow_lab())).pack(side="left", padx=4)
    lbl_br = ttk.Label(fbr, text="", width=26, foreground="#555")
    lbl_br.pack(side="left")

    def brow_lab(*_):
        m_ = {b: a for a, b in BROW_MODES}.get(V["brow_mode"].get(), "no")
        a_ = float(V["brow_amt"].get())
        lbl_br.configure(text={"no": "", "atlas": "risoluzione %.1fx della faccia" % (1 + 2 * a_ / 100),
                               "rinforza": "rinforzo %d%%" % a_}[m_])
    V["brow_mode"].trace_add("write", brow_lab)
    brow_lab()
    fx_f = ttk.LabelFrame(tab_b, text="Espressione neutra (mm, uguale a destra e sinistra; ricalcola il personaggio)",
                          padding=6)
    fx_f.pack(fill="x", pady=(6, 0))
    fx_lab = {}
    pre_f = ttk.Frame(fx_f)
    pre_f.grid(row=len(FACE_KEYS) + 1, column=0, columnspan=4, sticky="w", pady=(4, 0))
    ttk.Label(pre_f, text="Preset:").pack(side="left")
    v_fxpre = tk.StringVar(value="")
    cb_fx = ttk.Combobox(pre_f, textvariable=v_fxpre, values=[n for n, _ in FACE_PRESETS], state="readonly", width=16)
    cb_fx.pack(side="left", padx=4)
    ttk.Label(pre_f, text="(sposta i cursori: poi puoi ritoccarli)", foreground="#666").pack(side="left")

    def fx_preset(e=None):
        p_ = dict(FACE_PRESETS).get(v_fxpre.get(), {})
        for k_, _, _ in FACE_KEYS:
            V["fx_" + k_].set(float(p_.get(k_, 0.0)))
            fx_show(k_)
    cb_fx.bind("<<ComboboxSelected>>", fx_preset)

    def fx_show(k_):
        fx_lab[k_].configure(text="%+.1f" % V["fx_" + k_].get())
    for i_, (k_, t_, h_) in enumerate(FACE_KEYS):
        ttk.Label(fx_f, text=t_).grid(row=i_, column=0, sticky="w")
        ttk.Scale(fx_f, from_=-5.0, to=5.0, orient="horizontal", length=220, variable=V["fx_" + k_],
                  command=lambda v, k_=k_: (V["fx_" + k_].set(round(float(v) * 2) / 2), fx_show(k_))).grid(row=i_, column=1, padx=4)
        fx_lab[k_] = ttk.Label(fx_f, text="", width=5)
        fx_lab[k_].grid(row=i_, column=2, sticky="w")
        fx_show(k_)
        ttk.Label(fx_f, text=h_, foreground="#666").grid(row=i_, column=3, sticky="w", padx=(6, 0))

    def fx_reset():
        for k_, _, _ in FACE_KEYS:
            V["fx_" + k_].set(0.0)
            fx_show(k_)
    ttk.Button(fx_f, text="Azzera", command=fx_reset).grid(row=len(FACE_KEYS), column=1, sticky="w", padx=4, pady=(4, 0))
    fsp = ttk.Frame(tab_b, padding=(6, 4))
    fsp.pack(fill="x")
    ttk.Checkbutton(fsp, text="Togli pezzetti isolati da capelli e capi: al massimo", variable=V["spk_on"]).pack(side="left")
    ttk.Spinbox(fsp, from_=1, to=50, increment=1, textvariable=V["spk_tris"], width=4).pack(side="left", padx=3)
    ttk.Label(fsp, text="triangoli e meno di").pack(side="left")
    ttk.Spinbox(fsp, from_=0.05, to=20, increment=0.1, textvariable=V["spk_area"], width=5).pack(side="left", padx=3)
    ttk.Label(fsp, text="cm2 (sempre: vertici e spigoli sciolti)", foreground="#666").pack(side="left")
    fn = ttk.LabelFrame(tab_b, text="NBD", padding=6)
    fn.pack(fill="x", pady=6)
    ttk.Checkbutton(fn, text="Dopo la conversione crea anche gli NBD (con fbx2nbd.py, da mettere accanto a daz2ob.py)",
                    variable=V["make_nbd"]).pack(side="left")

    # ================================================================== scheda Libreria capelli
    hl = ttk.Frame(tab_h)
    hl.pack(side="left", fill="both", expand=True)
    hr = ttk.LabelFrame(tab_h, text="Anteprima sulla testa del personaggio", padding=6)
    hr.pack(side="left", fill="y", padx=(8, 0))
    rowl = ttk.Frame(hl)
    rowl.pack(fill="x")
    ttk.Label(rowl, text="Libreria").pack(side="left")
    ttk.Entry(rowl, textvariable=V["hairlib"], width=50).pack(side="left", padx=4, fill="x", expand=True)
    ttk.Button(rowl, text="Sfoglia...", command=lambda: (browse("hairlib", "dir"), refresh_lib())).pack(side="left")
    rowc = ttk.Frame(hl)
    rowc.pack(fill="x", pady=6)
    ttk.Label(rowc, text="Capelli").pack(side="left")
    cb_lib = ttk.Combobox(rowc, textvariable=V["libsel"], state="readonly", width=30)
    cb_lib.pack(side="left", padx=4)
    ttk.Button(rowc, text="Aggiungi alla libreria...", command=lambda: add_hair()).pack(side="left", padx=4)
    ttk.Button(rowc, text="Elimina", command=lambda: del_hair()).pack(side="left")
    ttk.Button(rowc, text="Crea dai capelli DAZ...", command=lambda: make_shell()).pack(side="left", padx=4)
    thumb_lbl = ttk.Label(hl)
    thumb_lbl.pack(anchor="w")
    ttk.Label(hl, text="I capelli si scelgono e si colorano in ogni outfit (scheda Outfit > Capelli).\n"
                       "Da NBD: prendo i capelli e la testa su cui erano montati (adattamento piu' preciso).\n"
                       "Da FBX/OBJ: solo i capelli, posizione e scala li trovo dalla forma.\n"
                       "Crea dai capelli DAZ: seleziona i capelli DAZ nella scheda Outfit (lista a sinistra), poi premi\n"
                       "il pulsante: ne ricavo un guscio low poly con la loro forma e il loro colore.",
              justify="left", foreground="#555").pack(anchor="w", pady=8)
    lcanvas = tk.Canvas(hr, width=240, height=300, bg="#707888", highlightthickness=0)
    lcanvas.pack()
    lrow = ttk.Frame(hr)
    lrow.pack(fill="x", pady=4)
    btn_prev = ttk.Button(hr, text="Anteprima 3D")
    btn_prev.pack(fill="x")

    def show_lview(i):
        if state["libprev"] is None:
            return
        state["libprev_i"] = i % 8
        lcanvas.delete("all")
        lcanvas.create_image(-240 * state["libprev_i"], 0, image=state["libprev"], anchor="nw")
    ttk.Button(lrow, text="< Ruota", command=lambda: show_lview(state["libprev_i"] - 1)).pack(side="left", expand=True, fill="x")
    ttk.Button(lrow, text="Ruota >", command=lambda: show_lview(state["libprev_i"] + 1)).pack(side="left", expand=True, fill="x")
    lcanvas.bind("<Button-1>", lambda e: show_lview(state["libprev_i"] + (1 if e.x > 120 else -1)))

    def lib_entries():
        d = V["hairlib"].get()
        return sorted(os.path.splitext(f)[0] for f in os.listdir(d) if f.lower().endswith(".npz")) if os.path.isdir(d) else []

    def refresh_lib(select=None):
        names = lib_entries()
        cb_lib.configure(values=["(nessuno)"] + names)
        cb_ohair.configure(values=["(nessuno)"] + names)
        if select:
            V["libsel"].set(select)
        elif V["libsel"].get() not in names:
            V["libsel"].set(names[0] if names else "(nessuno)")
        show_hair_thumb()

    def show_hair_thumb(*_):
        p = os.path.join(V["hairlib"].get(), V["libsel"].get() + ".png")
        if os.path.isfile(p):
            try:
                state["hthumb"] = tk.PhotoImage(file=p)
                thumb_lbl.configure(image=state["hthumb"])
                return
            except Exception:
                pass
        thumb_lbl.configure(image="")
    cb_lib.bind("<<ComboboxSelected>>", show_hair_thumb)

    def add_hair():
        src = filedialog.askopenfilename(title="Capelli da aggiungere",
                                         filetypes=[("NBD, FBX, OBJ", "*.nbd *.NBD *.fbx *.FBX *.obj *.OBJ")])
        if not src:
            return
        nm = simpledialog.askstring("Libreria capelli", "Nome dei capelli:", parent=root,
                                    initialvalue=safe_name(os.path.splitext(os.path.basename(src))[0]))
        if not nm:
            return
        args = ["--daz2ob-hairadd", src, nm, V["hairlib"].get()]
        if src.lower().endswith(".nbd"):
            mi = simpledialog.askstring("Libreria capelli", "Numero della mesh dei capelli nell'NBD\n"
                                        "(vuoto = la trovo da solo):", parent=root)
            if mi and mi.strip().isdigit():
                args.append(mi.strip())
        run_bg(args, "Aggiungo i capelli alla libreria...", lambda rc: refresh_lib(safe_name(nm)) if rc == 0 else None)

    def make_shell():
        fbx = V["fbx"].get().strip()
        g = [x.replace("  (capelli DAZ)", "").strip() for x in sel_garments()]
        if state["scan"] is None or len(g) != 1:
            messagebox.showinfo("daz2ob", "Dopo l'analisi, seleziona a sinistra UN capo: i capelli DAZ da trasformare.")
            return
        nm = simpledialog.askstring("Capelli dai capelli DAZ", "Nome per la libreria:", parent=root,
                                    initialvalue=safe_name(g[0]) + "_lowpoly")
        if not nm:
            return

        def done(rc):
            if rc == 0:
                refresh_lib(safe_name(nm))
                of = cur_outfit()
                if of is not None:
                    v_hair.set(safe_name(nm))
                    show_othumb()
                    store_soft()
        run_bg(["--daz2ob-hairshell", fbx, g[0], nm, V["hairlib"].get(), "3000"],
               "Creo i capelli dai capelli DAZ (un minuto o due)...", done)

    def del_hair():
        nm = V["libsel"].get()
        if nm in ("", "(nessuno)") or not messagebox.askyesno("daz2ob", "Elimino '%s' dalla libreria?" % nm):
            return
        for ext in (".npz", ".png"):
            p = os.path.join(V["hairlib"].get(), nm + ext)
            if os.path.isfile(p):
                os.remove(p)
        refresh_lib()

    def lib_path(name):
        return os.path.join(V["hairlib"].get(), name + ".npz") if name and name != "(nessuno)" else ""

    def preview_lib():
        if not state["scan"] or not state["scan"].get("head"):
            messagebox.showinfo("daz2ob", "Prima premi \"1. Analizza\": serve la testa del personaggio.")
            return
        lib = lib_path(V["libsel"].get())
        if not lib:
            return
        out = os.path.join(state["tmp"], "lib%d.png" % len(os.listdir(state["tmp"])))
        tlog("Anteprima dei capelli...")

        def done(rc):
            if rc == 0 and os.path.isfile(out):
                state["libprev"] = tk.PhotoImage(file=out)
                show_lview(0)
            elif rc != 0:
                tlog("ATTENZIONE: anteprima dei capelli non riuscita")
        server().ask("hair", {"head": state["scan"]["head"], "hair_lib": lib, "level": "Alti", "out": out}, done)
    btn_prev.configure(command=preview_lib)

    # ------------------------------------------------------------------ anteprima dell'outfit
    def schedule_preview(*_):
        if not V["auto_prev"].get() or not state["scan"] or not state["scan"].get("look"):
            return
        if web.get("url") and time.time() - web.get("seen", 0) < 8:
            return                                     # c'e' l'anteprima 3D aperta: Blender lavora solo per quella
        if state["after"]:
            root.after_cancel(state["after"])
        state["after"] = root.after(900, run_preview)

    class PreviewServer(object):
        """Blender sempre aperto per le anteprime: risponde in uno o due secondi invece di riaprirsi ogni volta.
        Una richiesta alla volta; se ne arrivano altre mentre lavora resta solo l'ultima per tipo."""

        def __init__(self, exe):
            self.exe, self.p, self.n = exe, None, 0
            self.cb, self.queue, self.running = {}, [], None
            self.err = []
            self.kind, self.t0 = None, time.time()

        def alive(self):
            return self.p is not None and self.p.poll() is None

        def start(self):
            flags = 0x08000000 if os.name == "nt" else 0
            self.p = subprocess.Popen(blender_cmd(self.exe) + ["--daz2ob-server"], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                                      creationflags=flags, bufsize=1)
            threading.Thread(target=self.reader, args=(self.p,), daemon=True).start()

        def reader(self, p):
            for line in p.stdout:
                line = line.rstrip("\n")
                if not line.startswith(TAG):
                    self.err = (self.err + [line])[-12:]
                    continue
                msg = line[len(TAG):]
                if msg.startswith("FATTO "):
                    _, rid, rc = msg.split()
                    ui(lambda rid=rid, rc=int(rc): self.finished(rid, rc))
                elif msg.startswith("ERRORE"):
                    det = [ln for ln in self.err if ln.strip() and not ln.startswith(("FBX", "(bpy", "export"))][-6:]
                    tlog("anteprima: " + msg + ("\n  " + "\n  ".join(det) if det else ""))
                elif msg != "PRONTO" and self.running is not None:
                    # registro del Blender dell'anteprima: nella finestra, con i secondi dall'inizio della richiesta
                    dt = time.time() - self.t0
                    tlog("[3D %5.1fs] %s" % (dt, msg.strip()))
                    if self.kind == "outfit3d":
                        web["busy"] = "Blender (%.0f s): %s" % (dt, busy_text(msg))
            ui(lambda: self.died(p))

        def died(self, p):
            if p is self.p and self.running is not None:
                tlog("ATTENZIONE: il Blender delle anteprime si e' chiuso:\n  " + "\n  ".join(self.err[-8:]))
                rid = self.running
                self.running = None
                self.finished(rid, 2)

        def ask(self, kind, job, cb):
            self.queue = [q for q in self.queue if q[0] != kind] + [(kind, job, cb)]
            self.pump()

        def pump(self):
            if self.running is not None or not self.queue:
                return
            if not self.alive():
                try:
                    self.start()
                except Exception as e:
                    tlog("ERRORE: non riesco ad avviare Blender per le anteprime (%s)" % e)
                    q = self.queue
                    self.queue = []
                    for _, _, cb in q:
                        cb(2)
                    return
            kind, job, cb = self.queue.pop(0)
            self.kind, self.t0 = kind, time.time()
            self.n += 1
            rid = str(self.n)
            self.cb[rid] = cb
            self.running = rid
            lbl_pv.configure(text="Blender sta disegnando...")
            try:
                req = dict(job, id=rid, cmd=kind) if job.get("__raw__") else {"id": rid, "cmd": kind, "job": job}
                self.p.stdin.write(json.dumps(req) + "\n")
                self.p.stdin.flush()
            except Exception:
                self.running = None
                self.p = None
                cb(2)
                self.pump()

        def finished(self, rid, rc):
            cb = self.cb.pop(rid, None)
            if rid == self.running:
                self.running = None
            lbl_pv.configure(text="")
            if cb:
                cb(rc)
            self.pump()

        def stop(self):
            try:
                if self.alive():
                    self.p.stdin.write('{"cmd": "quit"}\n')
                    self.p.stdin.flush()
            except Exception:
                pass

    def busy_text(msg):
        """Riga del registro di Blender -> cosa sta facendo, per la barra del browser."""
        m = msg.strip()
        if m.startswith("preparazione del personaggio di nuovo"):
            return "rifa' la preparazione del personaggio (" + m.split(":", 1)[-1].strip() + ")"
        if m.startswith("leggo "):
            return "prepara il personaggio: legge l'FBX"
        for a, b in (("T-pose", "prepara il personaggio: T-pose"), ("adattamento allo scheletro", "prepara il personaggio: scheletro"),
                     ("atlas corpo", "prepara il personaggio: texture del corpo"), ("faccia ", "prepara il personaggio: riduzioni"),
                     ("outfit '", "aggiorna l'outfit"), ("capelli", "capelli"), ("atlas vestiti", "texture dei vestiti"),
                     ("corpo nascosto", "pulizia della pelle"), ("anteprima 3D:", "invia al browser")):
            if m.startswith(a) or m.lstrip().startswith(a):
                return b
        return m[:70]

    def server():
        exe = V["blender"].get().strip()
        sv = state["srv"]
        if sv is None or sv.exe != exe:
            if sv is not None:
                sv.stop()
            sv = state["srv"] = PreviewServer(exe)
        return sv

    def preview_job():
        of = cur_outfit() or {}
        h = dict(of.get("hair") or {})
        h["lib"] = lib_path(h.get("name", ""))
        return {"look": state["scan"]["look"], "head": state["scan"]["head"], "hair": h,
                "eyes_color": eyes_color.get(), "looks": of.get("looks") or {}}

    # ------------------------------------------------------------------ anteprima 3D nel browser
    web = {"version": -1, "dirs": {}, "busy": "", "error": "", "info": "", "title": "", "seen": 0.0, "url": "",
           "last": None, "n": 0, "looks": {}}

    def web_start():
        if web["url"]:
            return web["url"]
        import http.server

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                path = self.path.split("?")[0]
                body, ctype = None, "application/octet-stream"
                if path in ("/", "/index.html"):
                    body, ctype = VIEWER_HTML.encode("utf-8"), "text/html; charset=utf-8"
                elif path == "/state":
                    web["seen"] = time.time()
                    body = json.dumps({k: web[k] for k in ("version", "busy", "error", "info", "title", "looks")}).encode("utf-8")
                    ctype = "application/json"
                elif path.startswith("/files/"):
                    parts = path.split("/")
                    try:
                        d = web["dirs"].get(int(parts[2]))
                        f = os.path.join(d, os.path.basename(parts[3])) if d else ""
                        if f and os.path.isfile(f):
                            body = open(f, "rb").read()
                            ctype = ("image/png" if f.endswith(".png") else "application/octet-stream"
                                     if f.endswith(".bin") else "application/json")
                    except (ValueError, IndexError):
                        body = None
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        web["url"] = "http://127.0.0.1:%d/" % srv.server_address[1]
        return web["url"]

    def open_3d():
        if not state["scan"]:
            messagebox.showinfo("daz2ob", "Prima premi \"1. Analizza\".")
            return
        import webbrowser
        url = web_start()
        web["last"] = None
        webbrowser.open(url)
        web["seen"] = time.time()
        tlog("Anteprima 3D nel browser: %s" % url)
        check_3d()

    def check_3d():
        """Ogni secondo e mezzo: se la pagina e' aperta e qualcosa e' cambiato, ricalcola l'outfit."""
        if web["url"] and time.time() - web["seen"] < 8 and state["scan"]:
            sync_outfit()                     # cosi' la chiave non cambia al primo ritocco
            try:
                job = make_job(False)
            except ValueError:
                job = None
            of = cur_outfit()
            if job is not None:
                oname = of["name"] if of else ""
                # i colori li applica la pagina in tempo reale: non servono a Blender
                lk = dict((of or {}).get("looks") or {})
                web["looks"] = {"iris": job.get("eyes_color"), "hair": ((of or {}).get("hair") or {}).get("color"),
                                "lips": lk.get("lips"), "nails": lk.get("nails"), "makeup": lk.get("makeup"),
                                "garments": {g_: v_.get("color") for g_, v_ in ((of or {}).get("style") or {}).items()
                                             if v_.get("color")},
                                # ritocchi di capelli e capi: la pagina li applica subito, Blender poi rifa' il calcolo
                                "adjust": {"hair": {k_: v_ for k_, v_ in ((of or {}).get("hair") or {}).items()
                                                    if k_ in ("sx", "sy", "sz", "dx", "dy", "dz")},
                                           "garments": (of or {}).get("adjust") or {}}}
                jk = json.loads(json.dumps(job))
                jk.pop("eyes_color", None)
                for o_ in jk.get("outfits") or []:
                    (o_.get("hair") or {}).pop("color", None)
                    mk = (o_.get("looks") or {}).get("makeup") or {}
                    o_["looks"] = {"makeup_ext": mk.get("ext", 0) if mk else None}
                    o_["style"] = {g_: v_.get("tex") for g_, v_ in (o_.get("style") or {}).items() if v_.get("tex")}
                key = json.dumps([jk, oname], sort_keys=True)
                # si manda a Blender solo quando la modifica e' ferma da mezzo secondo (cursori trascinati:
                # niente calcoli intermedi in coda)
                now = time.time()
                if key == web["last"]:
                    web["pend_key"] = None
                    if web["busy"] == "modifica in corso...":
                        web["busy"] = ""
                if key != web["last"]:
                    if key != web.get("pend_key"):
                        web["pend_key"], web["pend_t"] = key, now
                        web["busy"] = web["busy"] or "modifica in corso..."
                    elif now - web["pend_t"] >= 0.5:
                        web["last"] = key
                        web["pend_key"] = None
                        request_3d(job, oname)
        if web["url"]:
            if web.get("timer"):
                root.after_cancel(web["timer"])
            web["timer"] = root.after(250, check_3d)

    def request_3d(job, oname):
        web["n"] += 1
        d = os.path.join(state["tmp"], "3d_%d" % web["n"])
        first = not web["dirs"]
        web["busy"] = ("Blender prepara il personaggio (la prima volta, o se cambi corpo o capi, circa un minuto)..."
                       if first else "Blender aggiorna l'outfit '%s'..." % oname)
        web["title"] = "%s - %s" % (job.get("name", ""), oname or "base")

        def done(rc, d=d, oname=oname):
            if rc == 0 and os.path.isfile(os.path.join(d, "scene.json")):
                v = web["version"] + 1
                web["dirs"][v] = d
                for k in [k for k in web["dirs"] if k < v - 3]:
                    shutil.rmtree(web["dirs"].pop(k), ignore_errors=True)
                web["version"] = v
                web["error"] = ""
                web["info"] = "Outfit '%s' aggiornato alle %s" % (oname or "base", time.strftime("%H:%M:%S"))
                try:
                    hd = json.load(open(os.path.join(d, "scene.json"), encoding="utf-8"))
                    state["real"][oname] = (sum(m["tris"] for m in hd["meshes"] if m["kind"] == "mesh"),
                                            "anteprima " + time.strftime("%H:%M"))
                    refresh_estimate()
                except Exception:
                    pass
            elif rc != 0:
                web["error"] = "Anteprima non riuscita: guarda il registro nella finestra di daz2ob."
            if not any(q[0] == "outfit3d" for q in server().queue):
                web["busy"] = ""
        server().ask("outfit3d", {"__raw__": True, "job": job, "outfit": oname, "dir": d}, done)

    def request_views(views, prefetch=False):
        pv = state["pv"]
        key = pv["key"]
        if key is None:
            return
        job = json.loads(key)
        d = os.path.join(state["tmp"], "pv%d" % len(os.listdir(state["tmp"])))
        job.update(views=list(views), outdir_views=d)

        def done(rc):
            if pv["key"] != key:                         # nel frattempo e' cambiato qualcosa
                return
            if rc == 0:
                for vi in views:
                    f = os.path.join(d, "v%d.png" % vi)
                    if os.path.isfile(f):
                        img = tk.PhotoImage(file=f)
                        pv["imgs"][vi] = img
                show_view(state["prev_i"])
                missing = [i for i in range(8) if i not in pv["imgs"]]
                if missing and not prefetch:             # le altre viste con calma, mentre guardi questa
                    request_views(missing, True)
        server().ask("look", job, done)

    def run_preview():
        state["after"] = None
        if not state["scan"] or not state["scan"].get("look"):
            messagebox.showinfo("daz2ob", "Prima premi \"1. Analizza\".")
            return
        key = json.dumps(preview_job(), sort_keys=True)
        if key == state["pv"]["key"] and state["pv"]["imgs"]:
            return
        state["pv"] = {"key": key, "imgs": {}}
        request_views([state["prev_i"]])
    btn_lp.configure(command=run_preview)

    # ------------------------------------------------------------------ in basso
    bot = ttk.Frame(root, padding=(8, 4))
    btn_go = ttk.Button(bot, text="2. Converti")
    btn_go.pack(side="right")
    btn_nbd = ttk.Button(bot, text="Converti in NBD")
    btn_nbd.pack(side="right", padx=(6, 0))
    btn_open = ttk.Button(bot, text="Apri la cartella del personaggio")
    btn_open.pack(side="right", padx=6)
    ttk.Button(bot, text="Salva il lavoro...", command=lambda: save_job(True)).pack(side="left")
    ttk.Button(bot, text="Carica il lavoro...", command=lambda: load_job()).pack(side="left", padx=6)
    logw = scrolledtext.ScrolledText(root, height=7, font=("Consolas", 9))
    logw.pack(side="bottom", fill="x", expand=False, padx=8, pady=(0, 6), before=nb)
    bot.pack(side="bottom", fill="x", before=nb)

    def ui(fn):
        root.after(0, fn)

    def tlog(msg):
        ui(lambda: (logw.insert("end", msg + "\n"), logw.see("end")))
        m_ = re.search(r"outfit '(.+?)': ", msg)
        if m_:
            state["log_of"] = m_.group(1)
        m_ = re.search(r"totale (\d+) triangoli -> ", msg)
        if m_ and state.get("log_of"):
            nm_ = next((o["name"] for o in state["outfits"] if safe_name(o["name"]) == state["log_of"]), state["log_of"])
            state["real"][nm_] = (int(m_.group(1)), "conversione " + time.strftime("%H:%M"))
            ui(refresh_estimate)

    def busy(on):
        state["busy"] = on
        for b in (btn_scan, btn_go, btn_nbd):
            b.configure(state="disabled" if on else "normal")

    def run_bg(args, msg, after=None, clear=True, quiet=False):
        exe = V["blender"].get().strip()
        if not exe:
            messagebox.showerror("daz2ob", "Non trovo Blender: indicalo nel campo 'Blender'.")
            return
        if state["busy"]:
            return
        busy(True)
        if clear:
            logw.delete("1.0", "end")
        tlog(msg)

        def work():
            rc = run_blender(exe, args, (lambda m: None) if quiet else tlog)

            def done():
                busy(False)
                if quiet and rc != 0:
                    tlog("ATTENZIONE: anteprima non riuscita (codice %d)" % rc)
                if after:
                    after(rc)
            ui(done)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------------ analisi
    def fill_tree(res):
        tree.delete(*tree.get_children())
        state["thumbs"].clear()
        state["iname"] = {}
        state["orig"] = {g["name"]: g["tris"] for g in res["garments"]}
        state["depth"] = {g["name"]: g.get("depth", 0.0) for g in res["garments"]}
        state["lens"] = {g["name"]: g.get("lens") or [] for g in res["garments"]}
        for g in res["garments"]:
            img = None
            if g.get("thumb") and os.path.isfile(g["thumb"]):
                try:
                    img = tk.PhotoImage(file=g["thumb"]).subsample(3, 3)
                    state["thumbs"][g["name"]] = img
                except Exception:
                    img = None
            kw = {"image": img} if img else {}
            outs, short = outfit_prefix(g["name"])
            iid = tree.insert("", "end", text="  " + short + ("  [%s]" % ", ".join(outs) if outs else "") +
                              ("  (capelli DAZ)" if g.get("hair") else ""), values=(g["tris"],), **kw)
            state["iname"][iid] = g["name"]
        names = {g["name"] for g in res["garments"]}
        if not state["outfits"]:
            groups = {}
            for g in res["garments"]:
                for o_ in outfit_prefix(g["name"])[0]:
                    groups.setdefault(o_, []).append(g["name"])
            for oname, gl in groups.items():
                state["outfits"].append({"name": oname, "garments": gl, "mesh1": "", "tris": preset_garment_tris(),
                                         "tris_auto": True, "cull_body": True, "shares": {x: 100.0 / len(gl) for x in gl},
                                         "layers": sorted(gl, key=lambda x: state["depth"].get(x, 0.0)),
                                         "hair": {}, "looks": {}})
            if groups:
                tlog("Outfit creati dai nomi dei capi in DAZ: %s" % ", ".join(
                    "%s (%d capi)" % (k, len(v)) for k, v in groups.items()))
                refresh_outfits(0)
        for of in state["outfits"]:
            miss = [x for x in of["garments"] if x not in names]
            if miss:
                tlog("ATTENZIONE: l'outfit '%s' contiene capi non presenti in questo FBX: %s" % (of["name"], ", ".join(miss)))
        refresh_estimate()

    def scan():
        fbx = V["fbx"].get().strip()
        if not os.path.isfile(fbx):
            messagebox.showerror("daz2ob", "Scegli l'FBX esportato da DAZ.")
            return
        if not V["name"].get():
            V["name"].set(safe_name(os.path.splitext(os.path.basename(fbx))[0]))
        if not state["outfits"]:
            for side in (char_json(), os.path.splitext(fbx)[0] + "_daz2ob.json"):
                if os.path.isfile(side):
                    try:
                        apply_job(json.load(open(side, encoding="utf-8")), keep_fbx=True)
                        tlog("caricati gli outfit salvati in %s" % side)
                    except Exception as e:
                        tlog("ATTENZIONE: %s non letto (%s)" % (side, e))
                    break
        out = os.path.join(state["tmp"], "scan%d" % len(os.listdir(state["tmp"])))

        def done(rc):
            try:
                res = json.load(open(os.path.join(out, "scan.json"), encoding="utf-8"))
            except Exception:
                res = None
            if res:
                state["scan"] = res
                new_names = {g["name"] for g in res["garments"]}
                old = {x for of in state["outfits"] for x in of.get("garments", []) + [of.get("mesh1") or ""] if x}
                if old and not (old & new_names):
                    # personaggio diverso: via gli outfit dell'altro (restano salvati nella sua cartella)
                    prev = V["name"].get()
                    state["outfits"] = []
                    state["real"] = {}
                    nm_ = safe_name(os.path.splitext(os.path.basename(fbx))[0])
                    if prev == state.get("scan_name", prev) or not prev:
                        V["name"].set(nm_)
                    tlog("Personaggio nuovo (nessun capo in comune con gli outfit di '%s'): outfit vecchi tolti "
                         "dalla finestra (restano salvati)." % prev)
                    for side in (char_json(), os.path.splitext(fbx)[0] + "_daz2ob.json"):
                        if os.path.isfile(side):
                            try:
                                apply_job(json.load(open(side, encoding="utf-8")), keep_fbx=True)
                                tlog("caricati gli outfit salvati in %s" % side)
                            except Exception as e:
                                tlog("ATTENZIONE: %s non letto (%s)" % (side, e))
                            break
                    refresh_outfits(None)
                state["scan_name"] = V["name"].get()
                fill_tree(res)
                tlog("Corpo Genesis 8 trovato. " + ("Controlla gli outfit (o creane altri: seleziona i capi a sinistra e "
                     "premi \"Nuovo outfit\")." if state["outfits"] else
                     "Ora crea gli outfit: seleziona i capi a sinistra e premi \"Nuovo outfit\"."))
                state["pv"] = {"key": None, "imgs": {}}
                refresh_outfits(0 if state["outfits"] else None)
                schedule_preview()
            elif rc == 0:
                tlog("ERRORE: analisi non riuscita")
        run_bg(["--daz2ob-scan", fbx, out], "Analizzo l'FBX con Blender (mezzo minuto circa)...", done)
    btn_scan.configure(command=scan)

    # ------------------------------------------------------------------ lavoro (json)
    def make_job(store=True):
        def num(name, cast=int):
            try:
                return cast(V[name].get())
            except ValueError:
                raise ValueError("valore non valido: %s = %r" % (name, V[name].get()))
        if store:
            store_outfit()
        outs = []
        for o in state["outfits"]:
            ensure_tris(o)
            o2 = dict(o)
            h = dict(o.get("hair") or {})
            h["lib"] = lib_path(h.get("name", ""))
            o2["hair"] = h
            outs.append(o2)
        return {"version": __version__, "fbx": V["fbx"].get().strip(), "outdir": outdir(),
                "outfit_folders": True, "arms_p06": bool(V["arms_p06"].get()),
                "shoulder_lift": num("shoulder_lift", float), "shoulder_shift": num("shoulder_shift", float),
                "shoulder_mode": {b: a for a, b in SHMODES}.get(V["shoulder_mode"].get(), "no"),
                "shoulder_smooth": num("shoulder_smooth", float), "lip_lower_node27": round(float(V["lip27"].get()), 2),
                "face_expr": {k_: round(float(V["fx_" + k_].get()), 1) for k_, _, _ in FACE_KEYS
                              if abs(float(V["fx_" + k_].get())) > 0.01},
                "brows": ({"mode": {b: a for a, b in BROW_MODES}.get(V["brow_mode"].get(), "no"),
                           "amount": round(float(V["brow_amt"].get()))}
                          if V["brow_mode"].get() != BROW_MODES[0][1] else {}),
                "keep_lashes": bool(V["keep_lashes"].get()),
                "specks": {"on": bool(V["spk_on"].get()), "tris": num("spk_tris"), "area": num("spk_area", float)},
                "lash_tris": num("lash_tris"), "keep_teeth": bool(V["keep_teeth"].get()), "teeth_tris": num("teeth_tris"),
                "acc_quota": num("acc_quota", float), "atlas_trasp": num("atlas_trasp"), "make_nbd": bool(V["make_nbd"].get()),
                "name": V["name"].get().strip(), "preset": V["preset"].get(), "targets": targets(),
                "budget_limit": num("limit"), "atlas_base": num("atlas_base"), "atlas_outfit": num("atlas_outfit"),
                "mirror_limbs": bool(V["mirror"].get()), "brow_side": num("brow_side", float),
                "hair_slot": num("hair_slot"), "hair_reserve": num("hair_reserve"), "ambient": num("ambient"),
                "margin_mm": num("margin_mm", float), "joint_smooth": num("joint_smooth", float),
                "weights_from_body": bool(V["wfb"].get()), "eyes_color": eyes_color.get(),
                "outfits": outs, "preview": True, "hairlib": V["hairlib"].get()}

    def apply_job(job, keep_fbx=False):
        if job.get("fbx") and not (keep_fbx and V["fbx"].get()):
            V["fbx"].set(job["fbx"])
        if job.get("name"):
            V["name"].set(job["name"])
        if job.get("preset"):
            V["preset"].set(job["preset"])
        for k, v in (job.get("targets") or {}).items():
            if "t_" + k in V:
                V["t_" + k].set(str(v))
        for k, vk in (("budget_limit", "limit"), ("atlas_base", "atlas_base"), ("atlas_outfit", "atlas_outfit"),
                      ("brow_side", "brow_side"), ("hair_reserve", "hair_reserve"), ("ambient", "ambient"),
                      ("margin_mm", "margin_mm"), ("joint_smooth", "joint_smooth"), ("hair_slot", "hair_slot"),
                      ("hairlib", "hairlib"), ("lash_tris", "lash_tris"), ("atlas_trasp", "atlas_trasp"), ("teeth_tris", "teeth_tris"), ("acc_quota", "acc_quota"),
                      ("shoulder_lift", "shoulder_lift"), ("shoulder_shift", "shoulder_shift"),
                      ("shoulder_smooth", "shoulder_smooth")):
            if job.get(k) is not None:
                V[vk].set(str(job[k]))
        for k, vk in (("mirror_limbs", "mirror"), ("weights_from_body", "wfb"), ("keep_lashes", "keep_lashes"),
                      ("keep_teeth", "keep_teeth"),
                      ("arms_p06", "arms_p06"),
                      ("make_nbd", "make_nbd")):
            if k in job:
                V[vk].set(bool(job[k]))
        if job.get("shoulder_mode"):
            V["shoulder_mode"].set(dict(SHMODES).get(job["shoulder_mode"], SHMODES[0][1]))
        if job.get("specks"):
            V["spk_on"].set(bool(job["specks"].get("on", True)))
            V["spk_tris"].set(str(job["specks"].get("tris", 3)))
            V["spk_area"].set(str(job["specks"].get("area", 0.5)))
        if job.get("lip_lower_node27") is not None:
            V["lip27"].set(float(job["lip_lower_node27"]))
            lb27.configure(text="%.2f" % V["lip27"].get())
        bj = job.get("brows") or {}
        V["brow_mode"].set(dict(BROW_MODES).get(bj.get("mode", "no"), BROW_MODES[0][1]))
        V["brow_amt"].set(float(bj.get("amount", 50)))
        brow_lab()
        fxj = job.get("face_expr") or {}
        for k_, _, _ in FACE_KEYS:
            V["fx_" + k_].set(float(fxj.get(k_, 0.0)))
            fx_show(k_)
        eyes_color.put(job.get("eyes_color"), False)
        state["outfits"] = []
        for o in job.get("outfits", []):
            o = dict(o)
            h = dict(o.get("hair") or {})
            if h.get("lib") and not h.get("name"):
                h["name"] = os.path.splitext(os.path.basename(h["lib"]))[0]
            h.pop("lib", None)
            o["hair"] = h
            state["outfits"].append(o)
        refresh_estimate()
        refresh_lib()
        refresh_outfits(0 if state["outfits"] else None)

    def save_job(ask=False):
        try:
            job = make_job()
        except ValueError as e:
            messagebox.showerror("daz2ob", str(e))
            return None
        path = char_json()
        if ask:
            path = filedialog.asksaveasfilename(defaultextension=".json", initialfile=os.path.basename(path) or "lavoro.json",
                                                filetypes=[("Lavoro daz2ob", "*.json")])
            if not path:
                return None
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(job, fh, indent=1, ensure_ascii=False)
        except Exception as e:
            tlog("ATTENZIONE: lavoro non salvato (%s)" % e)
        refresh_chars()
        save_settings({"fbx": job["fbx"], "blender": V["blender"].get(),
                       "keep_lashes": job["keep_lashes"], "lash_tris": job["lash_tris"],
                       "keep_teeth": job["keep_teeth"], "teeth_tris": job["teeth_tris"], "acc_quota": job["acc_quota"],
                       "atlas_trasp": job["atlas_trasp"], "make_nbd": job["make_nbd"], "arms_p06": job["arms_p06"],
                       "shoulder_lift": job["shoulder_lift"], "shoulder_shift": job["shoulder_shift"],
                       "shoulder_mode": job["shoulder_mode"], "shoulder_smooth": job["shoulder_smooth"],
                       "lip_lower_node27": job["lip_lower_node27"], "specks": job["specks"],
                       "preset": job["preset"], "targets": job["targets"], "budget_limit": job["budget_limit"],
                       "atlas_base": job["atlas_base"], "atlas_outfit": job["atlas_outfit"],
                       "brow_side": job["brow_side"], "mirror_limbs": job["mirror_limbs"],
                       "hair_reserve": job["hair_reserve"], "hair_slot": job["hair_slot"], "ambient": job["ambient"],
                       "margin_mm": job["margin_mm"], "joint_smooth": job["joint_smooth"],
                       "weights_from_body": job["weights_from_body"], "hairlib": V["hairlib"].get()})
        return path, job

    def load_job():
        p = filedialog.askopenfilename(filetypes=[("Lavoro daz2ob", "*.json")])
        if p:
            try:
                apply_job(json.load(open(p, encoding="utf-8")))
                tlog("caricato %s" % p)
            except Exception as e:
                messagebox.showerror("daz2ob", str(e))

    def ask_over(over):
        dlg = tk.Toplevel(root)
        dlg.title("Limite superato")
        dlg.transient(root)
        dlg.grab_set()
        res = {"v": None}
        txt = "Questi outfit superano il limite di %d triangoli:\n\n" % limit() + "\n".join(
            "  %s: ~%d (vestiti %d -> %d per restare nel limite)" % (
                o["name"], estimate(o), o.get("tris", 0), max(200, limit() - base_estimate() - hair_estimate(o)))
            for o in over)
        ttk.Label(dlg, text=txt, justify="left", padding=12).pack()
        bf = ttk.Frame(dlg, padding=8)
        bf.pack()

        def pick(v):
            res["v"] = v
            dlg.destroy()
        ttk.Button(bf, text="Converti lo stesso", command=lambda: pick("go")).pack(side="left", padx=4)
        ttk.Button(bf, text="Riduci i vestiti", command=lambda: pick("reduce")).pack(side="left", padx=4)
        ttk.Button(bf, text="Annulla", command=lambda: pick(None)).pack(side="left", padx=4)
        root.wait_window(dlg)
        return res["v"]

    def go():
        if state["scan"] is None:
            messagebox.showinfo("daz2ob", "Prima premi \"1. Analizza\".")
            return
        if not state["outfits"] and not messagebox.askyesno("daz2ob", "Nessun outfit: esporto solo la base (corpo nudo)?"):
            return
        store_outfit()
        for o in state["outfits"]:
            ensure_tris(o)
        r = save_job()
        if r is None:
            return
        path, job = r

        def done(rc):
            if rc == 0:
                tlog("Finito. Gli FBX, le texture e le anteprime sono in %s" % job["outdir"])
                if job.get("make_nbd"):
                    make_nbds(job)
        run_bg(["--daz2ob-job", path], "Conversione in corso (uno o due minuti)...", done, clear=False)
    btn_go.configure(command=go)

    def make_nbds(job=None):
        if job is None:
            try:
                job = make_job()
            except ValueError as e:
                messagebox.showerror("daz2ob", str(e))
                return
        if fbx2nbd_module() is None:
            messagebox.showerror("daz2ob", "Non trovo fbx2nbd.py: copialo nella cartella di daz2ob.py\n(%s)"
                                 % os.path.dirname(os.path.abspath(__file__)))
            return
        files = outfit_fbx_files(job)
        if not files:
            messagebox.showinfo("daz2ob", "Nessun FBX da convertire in %s: prima premi \"2. Converti\"." % job["outdir"])
            return
        if state["busy"]:
            return
        busy(True)
        tlog("Creo gli NBD (%d)..." % len(files))

        def work():
            ok = 0
            for f in files:
                tlog("%s:" % os.path.basename(f))
                ok += bool(to_nbd(f, os.path.splitext(f)[0] + ".nbd", job.get("ambient", 20), tlog))
            ui(lambda: (busy(False), tlog("NBD creati: %d su %d, in %s" % (ok, len(files), job["outdir"]))))
        threading.Thread(target=work, daemon=True).start()
    btn_nbd.configure(command=lambda: make_nbds())

    def refresh_chars():
        d = V["collection"].get().strip()
        names = []
        if os.path.isdir(d):
            names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n, n + ".json")))
        cb_name.configure(values=names)

    def open_char(*_):
        p = char_json(V["name"].get())
        if not os.path.isfile(p):
            return
        try:
            job = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("daz2ob", "%s non letto (%s)" % (p, e))
            return
        state["outfits"] = []
        apply_job(job)
        tlog("aperto %s" % p)
        if os.path.isfile(V["fbx"].get()):
            scan()
        else:
            tlog("ATTENZIONE: l'FBX di questo personaggio non c'e' piu' (%s): sceglilo e premi Analizza" % V["fbx"].get())
    cb_name.bind("<<ComboboxSelected>>", open_char)

    def open_out():
        d = outdir()
        if d and os.path.isdir(d):
            if os.name == "nt":
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open" if sys.platform != "darwin" else "open", d])
    btn_open.configure(command=open_out)
    refresh_estimate()
    refresh_lib()
    refresh_chars()
    refresh_outfits()
    lbl_dir.configure(text="Uscita: " + outdir())
    if not V["blender"].get():
        tlog("Non trovo Blender: indica blender.exe nel campo 'Blender'.")
    if fbx2nbd_module() is None:
        tlog("Nota: fbx2nbd.py non e' accanto a daz2ob.py: gli NBD non si possono creare finche' non ce lo copi.")

    def on_close():
        if state["srv"] is not None:
            state["srv"].stop()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


def main():
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    if argv and argv[0] in ("--daz2ob-scan", "--daz2ob-job", "--daz2ob-hairadd", "--daz2ob-hairprev",
                            "--daz2ob-lookprev", "--daz2ob-hairshell", "--daz2ob-server"):
        return main_blender(argv)
    if argv and argv[0] == "--job" and len(argv) > 1:
        exe = find_blender(argv[3] if len(argv) > 3 and argv[2] == "--blender" else None)
        if exe is None:
            print("ERRORE: non trovo Blender (usa --blender percorso\\blender.exe)")
            return 1
        rc = run_blender(exe, ["--daz2ob-job", os.path.abspath(argv[1])], print)
        with open(argv[1], encoding="utf-8") as fh:
            job = json.load(fh)
        if rc == 0 and (job.get("make_nbd") or "--nbd" in argv):
            for f in outfit_fbx_files(job):
                if not to_nbd(f, os.path.splitext(f)[0] + ".nbd", job.get("ambient", 20)):
                    rc = 2
        return rc
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
