#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REOB Gameplay Editor  v0.2
Resident Evil Outbreak File 2 (JP, SLPM_656.92)

Editor per le tabelle di gameplay già documentate:
  - 0.DAT        statistiche NPC (tipo, HP, Danger, virus, velocità anim., forza)
  - 2.DAT        aspetto NPC (ad-lib/genere anim., scala, altezza, mesh)
  - 2.DAT        scala dei personaggi principali (X/Z/Y)
  - 2.DAT        attacchi dei nemici (tipo danno, vfx, presa...)
  - 2.DAT        passi (1 byte per costume)
  - SLPM_656.92  genere dei personaggi principali

Le tabelle sono definite come DATI in TABLES (in fondo alla sezione "DEFINIZIONI"):
per aggiungere una tabella scoperta basta aggiungere un blocco, senza toccare il resto.

Uso:
  python reob_gameplay_editor.py                 -> interfaccia grafica
  python reob_gameplay_editor.py --dump CARTELLA -> stampa tutte le tabelle a console
  python reob_gameplay_editor.py --dump CARTELLA --table attacks

Al primo salvataggio di ogni file viene creata una copia <file>.bak (mai sovrascritta).

Fonti: hill73n, Fothsid, UnKn0wN/NoData, Machi, Carl_Vercetti.
"""

import csv
import json
import os
import shutil
import struct
import sys

# =============================================================================
# DEFINIZIONI
# =============================================================================

# nome file -> (nome su disco, dimensione attesa dell'originale JP)
GAME_FILES = {
    "0.DAT": 117376,
    "2.DAT": 2173184,
    "SLPM_656.92": 1356096,
}

PLAYERS = ["KEVIN", "MARK", "JIM", "GEORGE", "DAVID", "ALYSSA", "YOKO", "CINDY"]

# ID modello NPC (Nxxx.NBD) -> nome   (da "NPC_gender_scaling_elevation_mesh_enable", File 2)
MODEL_NAMES = {
    0: "MACDOWELL", 1: "RODRIGUEZ", 2: "CONRAD", 3: "HUNK:B", 4: "HUNK", 5: "MIGUEL",
    6: "MIGUEL beta", 7: "LUKE", 8: "MACDOWELL beta", 9: "ARNOLD", 10: "MATT", 11: "BILLY",
    12: "HURSH", 13: "HURSH duplicate", 14: "HURSH leechman", 15: "original leechman",
    16: "PETER", 17: "MARVIN", 18: "FRED", 19: "ANDY", 20: "MARVIN wounded", 21: "JEAN",
    22: "TONY", 23: "PATRICK zombie", 24: "PATRICK", 25: "LLOYD", 26: "AUSTIN", 27: "CLINT",
    28: "BONE", 29: "BOB", 30: "JACK zombie", 31: "NATHAN", 32: "SAMUEL", 33: "MACDOWELL beta",
    34: "WILL", 35: "WILL zombie", 36: "ROGER", 37: "MACDOWELL beta", 38: "CARTER", 39: "GREG",
    40: "FROST", 41: "FROST:B", 42: "JAKE", 43: "GARY", 44: "RICHARD", 45: "MICKEY zombie",
    46: "MICKEY", 47: "AL", 48: "AXEMAN", 49: "AL:B", 50: "BEN", 51: "LUCY", 52: "REGAN",
    53: "REGAN:B", 54: "MONICA", 55: "LINDA", 56: "RITA", 57: "MACDOWELL duplicate",
    58: "MARY", 59: "KATE", 60: "MACDOWELL beta", 61: "MACDOWELL beta", 62: "DANNY",
    63: "DANNY:B", 64: "GILL", 65: "GILL:B", 69: "ETHAN duplicate", 72: "CINDY cameo WT",
    73: "KEITH", 80: "KURT", 81: "KURT:B", 82: "GARY:B", 83: "AL:C", 86: "DOROTHY",
    90: "YOKO:Z", 99: "MR.GREY", 100: "RAYMOND", 101: "ARTHUR", 102: "AARON", 103: "DORIAN",
    104: "ELLIOTT", 105: "ERIC", 106: "HARRY", 107: "MR.RED", 108: "MR.BLUE", 109: "MR.GREEN",
    110: "MR.GOLD", 111: "MR.BLACK", 112: "KARL", 113: "DUSTIN", 114: "DUSTIN alternative",
    115: "DEREK", 116: "MS.WHITE", 117: "MS.PEACH", 118: "MS.WATER", 119: "LEN",
    120: "NICOLAS", 121: "SEAN", 122: "PHILIP", 123: "DON", 124: "MATTHEW", 125: "ROBERT",
    126: "CHUCK", 127: "GINGER", 128: "LAURA", 129: "AMELIA", 130: "ETHAN", 131: "ETHAN zombie",
    132: "HOWARD", 133: "hospital zombie 1", 134: "ISAAC", 135: "hospital zombie 2",
    136: "KATHY", 137: "KATHY zombie", 138: "ELENA", 139: "ELENA zombie", 140: "FRANK",
    141: "KATHY wounded", 150: "RODNEY", 199: "CINDY missing skirt",
    200: "KEVIN cameo", 201: "MARK cameo", 202: "JIM cameo", 203: "GEORGE cameo",
    204: "DAVID cameo", 205: "ALYSSA cameo", 206: "YOKO cameo", 207: "CINDY cameo",
}

# --- enum (valore -> descrizione) -------------------------------------------
E_CHAR = {i: n.capitalize() for i, n in enumerate(PLAYERS)}
E_HP = {0: "500-800", 1: "900-1200", 2: "1300-1600", 3: "2000-2500", 4: "2600-3000",
        5: "3100-3500", 6: "3600-4000", 7: "2000-2999 (non usato)"}
E_DANGER = {0: "HP pieni", 1: "25% HP - 1 (Danger)"}
E_VIRUS = {0: "super lento", 1: "lento", 2: "più lento", 3: "medio", 4: "più veloce",
           5: "veloce", 6: "super veloce", 7: "(non usato)"}
E_ANIM = {0: "super lenta", 1: "lenta", 2: "più lenta", 3: "media", 4: "più veloce",
          5: "(non usato)", 6: "(non usato)", 7: "(non usato)"}
E_ADLIB = {0: "verde / anim. maschili", 1: "giallo / anim. femminili"}
E_GENDER = {0: "maschio", 1: "femmina"}
E_DMG = {0: "light hurt", 1: "heavy hurt", 2: "ground hurt", 3: "licker hurt",
         4: "strano (back hurt davanti)", 5: "strano (back hurt heavy)", 6: "fly",
         7: "licker hurt", 11: "nessuna reazione"}
E_VFX = {0: "niente", 1: "sangue", 2: "polvere"}
E_STEPS = {0x00: "generico", 0x10: "generico 2 (più leggero)", 0x20: "tacco femminile",
           0x30: "piedi nudi"}
E_GRAB = {0x09: "one hit kill", 0x48: "a terra", 0x81: "presa", 0x82: "presa alla gamba (zombie)",
          0x8B: "presa dalla finestra (uccide)"}

# --- etichette attacchi (offset del record in 2.DAT -> nome) ---------------
ATTACK_START = 0x1DE4CE
ATTACK_NAMES = {
    0x1DE9CE: "ZOMBIE schiaffo singolo",
    0x1DF34E: "ZOMBIE combo 1",
    0x1DF36E: "ZOMBIE combo 2",
    0x1DE50E: "ZOMBIE vomito",
    0x1DF2AE: "ZOMBIE presa normale",
    0x1DE5AE: "CANE attacco / HYENA salto",
    0x1DE6CE: "CANE presa",
    0x1DE78E: "SCISSOR TAIL attacco",
    0x1DF1EE: "HUNTER GAMMA schiaffo a terra",
    0x1DEE6E: "HUNTER GAMMA schiaffo dall'acqua",
    0x1DF4AE: "RAGNO attacco girandosi",
    0x1DEEEE: "RAGNO acido",
    0x1DEECE: "RAGNO salto",
    0x1DFECE: "HYENA attacco ravvicinato",
    0x1DF90E: "MR X combo 1",
    0x1DEAAE: "ELEFANTE pestone",
}


def F(off, typ, name, enum=None, note=""):
    """Definizione di un campo: offset nel record, tipo, nome, enum opzionale, nota."""
    return {"off": off, "type": typ, "name": name, "enum": enum, "note": note}


TABLES = [
    {
        "key": "npc_stats",
        "title": "Statistiche NPC",
        "file": "0.DAT",
        "start": 0x17080,
        "size": 12,
        "until_u16": 999,           # la tabella finisce quando npcId == 999
        "label": lambda i, rec: MODEL_NAMES.get(struct.unpack_from("<H", rec, 0)[0], "?"),
        "fields": [
            F(0, "u16", "npcId", note="xxx di Nxxx.NBD"),
            F(2, "u8", "Tipo personaggio", E_CHAR),
            F(3, "u8", "HP pool", E_HP),
            F(4, "u8", "Inizia in Danger", E_DANGER),
            F(5, "u8", "Virus rate", E_VIRUS),
            F(6, "u8", "Velocità anim.", E_ANIM),
            F(7, "u8", "byte 07 (?)", note="sempre 00"),
            F(8, "f32", "Forza", note="1.0 = 100%"),
        ],
        "note": "hill73n / Fothsid. 93 voci in File 2.",
    },
    {
        "key": "npc_look",
        "title": "Aspetto NPC",
        "file": "2.DAT",
        "start": 0x1E1140,
        "size": 20,
        "count": 209,
        "label": lambda i, rec: MODEL_NAMES.get(struct.unpack_from("<H", rec, 0)[0], "unused"),
        "fields": [
            F(0, "u16", "ID modello"),
            F(2, "u8", "Ad-lib / genere anim.", E_ADLIB),
            F(5, "u8", "byte 05 (?)", note="01 FRED/REGAN, 02 AARON"),
            F(6, "u16", "word 06 (?)", note="HP cameo? FF7F per quasi tutti"),
            F(8, "f32", "Scala", note="1.0 = standard"),
            F(12, "f32", "Altezza (offset)", note="0 = standard, negativo = più in basso"),
            F(16, "bits32", "Mesh disattivate", note="1 bit per mesh, 1 = nascosta"),
        ],
        "note": "hill73n / UnKn0wN / Fothsid.",
    },
    {
        "key": "player_scale",
        "title": "Scala personaggi",
        "file": "2.DAT",
        "start": 0x1E5540,
        "size": 12,
        "count": 8,
        "label": lambda i, rec: PLAYERS[i] if i < len(PLAYERS) else "?",
        "fields": [
            F(0, "f32", "Scala X"),
            F(4, "f32", "Scala Z"),
            F(8, "f32", "Scala Y"),
        ],
        "note": "Machi.",
    },
    {
        "key": "attacks",
        "title": "Attacchi nemici",
        "file": "2.DAT",
        "start": ATTACK_START,
        "size": 32,
        "count": 209,
        "label": lambda i, rec: ATTACK_NAMES.get(ATTACK_START + i * 32, ""),
        "fields": [
            F(0, "u8", "ID attacco", note="indice crescente (con eccezioni)"),
            F(1, "u8", "byte 01 (?)"),
            F(3, "u8", "Tipo danno / stun", E_DMG),
            F(4, "u8", "VFX", E_VFX),
            F(5, "u8", "Stato", note="effetto di stato?"),
            F(9, "u8", "byte 09 (?)", note="0 hurt, 1 = nessuna reazione? (prese)"),
            F(10, "u8", "byte 0A (?)", note="51 valori diversi: forse il danno"),
            F(12, "u8", "byte 0C (?)"),
            F(18, "u8", "byte 12 (?)"),
            F(19, "u8", "byte 13 (?)"),
            F(20, "u8", "byte 14 (?)"),
            F(22, "u16", "Presa / animazione", E_GRAB, note="82 presa gamba, 8B finestra, 09 one-hit-kill"),
            F(24, "u8", "byte 18 (?)"),
            F(25, "u8", "byte 19 (?)"),
            F(28, "u8", "byte 1C (?)"),
            F(29, "u8", "byte 1D (?)"),
            F(30, "u8", "byte 1E (?)"),
            F(31, "u8", "byte 1F (?)"),
        ],
        "note": "Carl_Vercetti. Record da 32 byte che iniziano con l'ID attacco. "
                "I byte mai usati (sempre 00) sono modificabili dall'hex grezzo.",
    },
    {
        "key": "footsteps",
        "title": "Passi",
        "file": "2.DAT",
        "start": 0x1FB000,
        "size": 1,
        "count": 40,
        "label": lambda i, rec: "%s outfit %d%s" % (PLAYERS[i // 5], i % 5 + 1,
                                                    " (non usato)" if i // 5 < 5 and i % 5 >= 3 else ""),
        "fields": [F(0, "u8", "Tipo passi", E_STEPS)],
        "note": "5 slot per personaggio, 1 byte per outfit. Uomini: 3 outfit (slot 4-5 non usati).",
    },
    {
        "key": "player_gender",
        "title": "Genere personaggi",
        "file": "SLPM_656.92",
        "start": 0x14A030,
        "size": 1,
        "count": 8,
        "label": lambda i, rec: PLAYERS[i],
        "fields": [F(0, "u8", "Genere", E_GENDER)],
        "note": "Eseguibile SLPM_656.92.",
    },
]

# =============================================================================
# NUCLEO (lettura / scrittura, nessuna dipendenza dalla GUI)
# =============================================================================

TYPE_SIZE = {"u8": 1, "u16": 2, "i16": 2, "u32": 4, "bits32": 4, "f32": 4}
TYPE_FMT = {"u8": "<B", "u16": "<H", "i16": "<h", "u32": "<I", "bits32": "<I", "f32": "<f"}


def read_field(buf, base, fld):
    return struct.unpack_from(TYPE_FMT[fld["type"]], buf, base + fld["off"])[0]


def fmt_value(fld, v):
    """Valore -> testo mostrato. Interi in esadecimale (come nell'hex editor)."""
    t = fld["type"]
    if t == "f32":
        s = ("%.6f" % v).rstrip("0").rstrip(".")
        return s if s not in ("", "-0") else "0"
    if t == "bits32":
        return "%08X" % v
    width = TYPE_SIZE[t] * 2
    s = ("%0*X" % (width, v & ((1 << (8 * TYPE_SIZE[t])) - 1)))
    if fld["enum"] is not None and v in fld["enum"]:
        s += " - " + fld["enum"][v]
    return s


def parse_value(fld, text):
    """Testo -> valore. Accetta '03', '03 - medio', '0x03'; float con . o ,"""
    t = fld["type"]
    text = text.strip()
    if t == "f32":
        v = float(text.replace(",", "."))
        struct.pack("<f", v)
        return v
    if not text:
        raise ValueError("%s: valore vuoto" % fld["name"])
    tok = text.split()[0]
    if tok.lower().startswith("0x"):
        tok = tok[2:]
    v = int(tok, 16)
    if t == "i16":
        lo, hi = -0x8000, 0x7FFF
    else:
        lo, hi = 0, (1 << (8 * TYPE_SIZE[t])) - 1
    if not lo <= v <= hi:
        raise ValueError("%s: valore fuori intervallo (%X)" % (fld["name"], v))
    return v


class GameData:
    """Contiene i file del gioco in memoria e le copie originali per il confronto."""

    def __init__(self):
        self.paths = {}     # nome -> percorso
        self.data = {}      # nome -> bytearray (modificato)
        self.orig = {}      # nome -> bytes (com'era al caricamento)
        self.warnings = []

    # -- caricamento --------------------------------------------------------
    @staticmethod
    def find_files(folder, max_depth=3):
        found = {}
        wanted = {n.upper(): n for n in GAME_FILES}
        base_depth = folder.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(folder):
            if root.count(os.sep) - base_depth >= max_depth:
                dirs[:] = []
            for f in files:
                key = wanted.get(f.upper())
                if key and key not in found:
                    found[key] = os.path.join(root, f)
        return found

    def load(self, paths):
        self.warnings = []
        for name, p in paths.items():
            with open(p, "rb") as fh:
                b = fh.read()
            exp = GAME_FILES.get(name)
            if exp and len(b) != exp:
                self.warnings.append("%s: dimensione %d, attesa %d (versione diversa?)" % (name, len(b), exp))
            self.paths[name] = p
            self.data[name] = bytearray(b)
            self.orig[name] = bytes(b)

    def has(self, name):
        return name in self.data

    # -- tabelle -------------------------------------------------------------
    def records(self, tbl):
        """Elenco degli offset assoluti dei record della tabella."""
        buf = self.data[tbl["file"]]
        offs = []
        o = tbl["start"]
        if "until_u16" in tbl:
            while o + tbl["size"] <= len(buf) and struct.unpack_from("<H", buf, o)[0] != tbl["until_u16"]:
                offs.append(o)
                o += tbl["size"]
                if len(offs) > 5000:
                    break
        else:
            for i in range(tbl["count"]):
                if o + tbl["size"] > len(buf):
                    break
                offs.append(o)
                o += tbl["size"]
        return offs

    def rec_bytes(self, tbl, off, original=False):
        src = self.orig if original else self.data
        return bytes(src[tbl["file"]][off:off + tbl["size"]])

    def set_field(self, tbl, off, fld, value):
        struct.pack_into(TYPE_FMT[fld["type"]], self.data[tbl["file"]], off + fld["off"], value)

    def set_raw(self, tbl, off, raw):
        if len(raw) != tbl["size"]:
            raise ValueError("Servono esattamente %d byte (ne hai scritti %d)" % (tbl["size"], len(raw)))
        self.data[tbl["file"]][off:off + tbl["size"]] = raw

    def is_modified(self, tbl, off):
        return self.rec_bytes(tbl, off) != self.rec_bytes(tbl, off, original=True)

    def dirty_files(self):
        return [n for n in self.data if bytes(self.data[n]) != self.orig[n]]

    # -- salvataggio ----------------------------------------------------------
    def save(self):
        saved = []
        for name in self.dirty_files():
            p = self.paths[name]
            bak = p + ".bak"
            if not os.path.exists(bak):
                shutil.copy2(p, bak)
            with open(p, "wb") as fh:
                fh.write(self.data[name])
            self.orig[name] = bytes(self.data[name])
            saved.append(name)
        return saved

    # -- CSV --------------------------------------------------------------------
    def export_csv(self, tbl, path):
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(["#", "offset", "nome"] + [f["name"] for f in tbl["fields"]] + ["hex"])
            for i, off in enumerate(self.records(tbl)):
                rec = self.rec_bytes(tbl, off)
                buf = self.data[tbl["file"]]
                w.writerow([i, "%08X" % off, tbl["label"](i, rec)]
                           + [fmt_value(f, read_field(buf, off, f)) for f in tbl["fields"]]
                           + [rec.hex(" ").upper()])

    def import_csv(self, tbl, path):
        """Applica i campi del CSV (le colonne con nome campo). Ritorna il n. di record cambiati."""
        offs = self.records(tbl)
        changed = 0
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        head = rows[0]
        col = {name: head.index(name) for name in [f["name"] for f in tbl["fields"]] if name in head}
        for r in rows[1:]:
            if not r or not r[0].strip().isdigit():
                continue
            i = int(r[0])
            if i >= len(offs):
                continue
            off = offs[i]
            before = self.rec_bytes(tbl, off)
            buf = self.data[tbl["file"]]
            for f in tbl["fields"]:
                if f["name"] in col and col[f["name"]] < len(r):
                    txt = r[col[f["name"]]]
                    if txt.strip() == "" or txt == fmt_value(f, read_field(buf, off, f)):
                        continue
                    self.set_field(tbl, off, f, parse_value(f, txt))
            if self.rec_bytes(tbl, off) != before:
                changed += 1
        return changed


# =============================================================================
# CONSOLE
# =============================================================================

def dump(folder, only=None):
    gd = GameData()
    found = gd.find_files(folder)
    if not found:
        print("Nessun file trovato in", folder)
        return
    gd.load(found)
    for w in gd.warnings:
        print("ATTENZIONE:", w)
    for tbl in TABLES:
        if only and tbl["key"] != only:
            continue
        if not gd.has(tbl["file"]):
            print("\n## %s: manca %s" % (tbl["title"], tbl["file"]))
            continue
        offs = gd.records(tbl)
        print("\n## %s  (%s @ %08X, %d record da %d byte)" % (tbl["title"], tbl["file"], tbl["start"], len(offs), tbl["size"]))
        buf = gd.data[tbl["file"]]
        for i, off in enumerate(offs):
            rec = gd.rec_bytes(tbl, off)
            vals = " | ".join("%s=%s" % (f["name"], fmt_value(f, read_field(buf, off, f))) for f in tbl["fields"])
            print("%3d %08X %-28s %s" % (i, off, tbl["label"](i, rec)[:28], vals))


# =============================================================================
# INTERFACCIA GRAFICA
# =============================================================================

def run_gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox

    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reob_gameplay_editor.json")

    def load_cfg():
        try:
            with open(cfg_path, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def save_cfg(c):
        try:
            with open(cfg_path, "w", encoding="utf-8") as fh:
                json.dump(c, fh, indent=1)
        except Exception:
            pass

    gd = GameData()
    root = tk.Tk()
    root.title("REOB Gameplay Editor - File 2 JP")
    root.geometry("1280x760")

    # ---------------- barra in alto ----------------
    top = ttk.Frame(root, padding=6)
    top.pack(fill="x")
    status = tk.StringVar(value="Scegli la cartella del gioco estratto (quella che contiene BIN\\0.DAT, BIN\\2.DAT e SLPM_656.92).")

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=6, pady=(0, 6))
    ttk.Label(root, textvariable=status, anchor="w", relief="sunken", padding=3).pack(fill="x", side="bottom")

    tabs = []   # TableTab

    class TableTab:
        def __init__(self, tbl):
            self.tbl = tbl
            self.offs = []
            self.cur = None
            self.frame = ttk.Frame(nb)
            nb.add(self.frame, text=tbl["title"])

            # sinistra: filtro + lista
            left = ttk.Frame(self.frame)
            fbar = ttk.Frame(left)
            fbar.pack(fill="x", pady=3)
            ttk.Label(fbar, text="Cerca:").pack(side="left")
            self.flt = tk.StringVar()
            self.flt.trace_add("write", lambda *a: self.refresh())
            ttk.Entry(fbar, textvariable=self.flt, width=24).pack(side="left", padx=4)
            self.only_mod = tk.BooleanVar()
            ttk.Checkbutton(fbar, text="solo modificati", variable=self.only_mod,
                            command=self.refresh).pack(side="left", padx=6)
            ttk.Button(fbar, text="Esporta CSV", command=self.export).pack(side="right", padx=2)
            ttk.Button(fbar, text="Importa CSV", command=self.import_).pack(side="right", padx=2)
            ttk.Label(left, text="%s  @ %08X  -  %s" % (tbl["file"], tbl["start"], tbl.get("note", "")),
                      foreground="#555").pack(fill="x")

            cols = ["#", "offset", "nome"] + [f["name"] for f in tbl["fields"]]
            tf = ttk.Frame(left)
            tf.pack(fill="both", expand=True)
            self.tree = ttk.Treeview(tf, columns=cols, show="headings", selectmode="browse")
            for c in cols:
                self.tree.heading(c, text=c)
                w = 40 if c == "#" else 80 if c == "offset" else 170 if c == "nome" else 110
                fld = next((f for f in tbl["fields"] if f["name"] == c), None)
                if fld is not None and fld["enum"] is not None:
                    w = 150
                self.tree.column(c, width=w, stretch=False, anchor="w")
            ys = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
            xs = ttk.Scrollbar(tf, orient="horizontal", command=self.tree.xview)
            self.tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
            self.tree.grid(row=0, column=0, sticky="nsew")
            ys.grid(row=0, column=1, sticky="ns")
            xs.grid(row=1, column=0, sticky="ew")
            tf.rowconfigure(0, weight=1)
            tf.columnconfigure(0, weight=1)
            self.tree.tag_configure("mod", background="#fff2a8")
            self.tree.bind("<<TreeviewSelect>>", lambda e: self.select())

            # destra: pannello di modifica
            right = ttk.LabelFrame(self.frame, text="Modifica record", padding=8)
            right.pack(side="right", fill="y", padx=(6, 0))
            self.title_var = tk.StringVar(value="(seleziona un record)")
            ttk.Label(right, textvariable=self.title_var, font=("TkDefaultFont", 10, "bold")).grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
            self.widgets = []
            for r, f in enumerate(tbl["fields"], start=1):
                ttk.Label(right, text=f["name"]).grid(row=r, column=0, sticky="w", pady=1)
                var = tk.StringVar()
                if f["enum"] is not None:
                    w = TYPE_SIZE[f["type"]] * 2
                    vals = ["%0*X - %s" % (w, k, v) for k, v in sorted(f["enum"].items())]
                    wd = ttk.Combobox(right, textvariable=var, values=vals, width=30)
                else:
                    wd = ttk.Entry(right, textvariable=var, width=33)
                wd.grid(row=r, column=1, sticky="w", pady=1)
                if f["note"]:
                    tip = ttk.Label(right, text=f["note"], foreground="#777", font=("TkDefaultFont", 8))
                    tip.grid(row=r, column=2, sticky="w", padx=4)
                self.widgets.append((f, var))
            r = len(tbl["fields"]) + 1
            ttk.Label(right, text="Hex grezzo").grid(row=r, column=0, sticky="nw", pady=(8, 0))
            self.raw = tk.Text(right, width=33, height=4, font=("Courier", 9), wrap="word")
            self.raw.grid(row=r, column=1, columnspan=2, sticky="w", pady=(8, 0))
            ttk.Label(right, text="Originale").grid(row=r + 1, column=0, sticky="nw")
            self.orig_var = tk.StringVar()
            ttk.Label(right, textvariable=self.orig_var, font=("Courier", 9), foreground="#777",
                      wraplength=260, justify="left").grid(row=r + 1, column=1, columnspan=2, sticky="w")
            bb = ttk.Frame(right)
            bb.grid(row=r + 2, column=0, columnspan=3, sticky="w", pady=8)
            ttk.Button(bb, text="Applica", command=self.apply).pack(side="left")
            ttk.Button(bb, text="Ripristina originale", command=self.revert).pack(side="left", padx=6)
            self.shown = {}
            # il pannello di destra va impacchettato prima, così la tabella larga non lo schiaccia
            left.pack(side="left", fill="both", expand=True)

        # -------------------------------------------------------------
        def available(self):
            return gd.has(self.tbl["file"])

        def refresh(self):
            self.tree.delete(*self.tree.get_children())
            if not self.available():
                return
            self.offs = gd.records(self.tbl)
            q = self.flt.get().strip().lower()
            buf = gd.data[self.tbl["file"]]
            for i, off in enumerate(self.offs):
                rec = gd.rec_bytes(self.tbl, off)
                name = self.tbl["label"](i, rec)
                vals = [fmt_value(f, read_field(buf, off, f)) for f in self.tbl["fields"]]
                row = [i, "%08X" % off, name] + vals
                if q and q not in " ".join(str(x) for x in row).lower():
                    continue
                mod = gd.is_modified(self.tbl, off)
                if self.only_mod.get() and not mod:
                    continue
                self.tree.insert("", "end", iid=str(i), values=row, tags=("mod",) if mod else ())
            if self.cur is not None and self.tree.exists(str(self.cur)):
                self.tree.selection_set(str(self.cur))
                self.tree.see(str(self.cur))

        def select(self):
            sel = self.tree.selection()
            if not sel:
                return
            self.cur = int(sel[0])
            self.load_editor()

        def load_editor(self):
            i = self.cur
            off = self.offs[i]
            rec = gd.rec_bytes(self.tbl, off)
            self.title_var.set("#%d  %s  @ %08X" % (i, self.tbl["label"](i, rec), off))
            buf = gd.data[self.tbl["file"]]
            self.shown = {}
            for f, var in self.widgets:
                s = fmt_value(f, read_field(buf, off, f))
                var.set(s)
                self.shown[f["name"]] = s
            self.raw.delete("1.0", "end")
            self.raw_shown = rec.hex(" ").upper()
            self.raw.insert("1.0", self.raw_shown)
            self.orig_var.set(gd.rec_bytes(self.tbl, off, original=True).hex(" ").upper())

        def apply(self):
            if self.cur is None:
                return
            off = self.offs[self.cur]
            try:
                raw_txt = " ".join(self.raw.get("1.0", "end").split()).upper()
                if raw_txt != self.raw_shown:
                    gd.set_raw(self.tbl, off, bytes.fromhex(raw_txt))
                else:
                    for f, var in self.widgets:
                        if var.get() == self.shown[f["name"]]:
                            continue   # non toccato: non riscrivere (evita arrotondamenti dei float)
                        gd.set_field(self.tbl, off, f, parse_value(f, var.get()))
            except Exception as e:
                messagebox.showerror("Valore non valido", str(e))
                return
            after_change()

        def revert(self):
            if self.cur is None:
                return
            off = self.offs[self.cur]
            gd.set_raw(self.tbl, off, gd.rec_bytes(self.tbl, off, original=True))
            after_change()

        def export(self):
            if not self.available():
                return
            p = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=self.tbl["key"] + ".csv",
                                             filetypes=[("CSV", "*.csv")])
            if p:
                gd.export_csv(self.tbl, p)
                status.set("Esportato " + p)

        def import_(self):
            if not self.available():
                return
            p = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
            if not p:
                return
            try:
                n = gd.import_csv(self.tbl, p)
            except Exception as e:
                messagebox.showerror("Import CSV", str(e))
                return
            after_change()
            status.set("Importati %d record modificati da %s (non ancora salvati)" % (n, p))

    def after_change():
        for t in tabs:
            t.refresh()
        cur = tabs[nb.index(nb.select())]
        if cur.cur is not None and cur.available():
            cur.load_editor()
        d = gd.dirty_files()
        root.title("REOB Gameplay Editor - File 2 JP" + ("  * modificato: " + ", ".join(d) if d else ""))

    def open_folder(folder=None):
        cfg = load_cfg()
        if folder is None:
            folder = filedialog.askdirectory(initialdir=cfg.get("folder") or None,
                                             title="Cartella del gioco estratto")
        if not folder:
            return
        found = GameData.find_files(folder)
        for name in GAME_FILES:
            if name not in found:
                if messagebox.askyesno("File mancante", "%s non trovato nella cartella.\nVuoi indicarlo a mano?" % name):
                    p = filedialog.askopenfilename(title="Seleziona " + name)
                    if p:
                        found[name] = p
        if not found:
            return
        gd.__init__()
        gd.load(found)
        cfg["folder"] = folder
        save_cfg(cfg)
        for t in tabs:
            t.cur = None
        after_change()
        msg = "Caricati: " + ", ".join("%s" % n for n in found)
        if gd.warnings:
            messagebox.showwarning("Attenzione", "\n".join(gd.warnings))
            msg += "   |   " + " ; ".join(gd.warnings)
        status.set(msg)

    def save():
        d = gd.dirty_files()
        if not d:
            status.set("Nessuna modifica da salvare.")
            return
        if not messagebox.askyesno("Salva", "Scrivo le modifiche su:\n" + "\n".join(gd.paths[n] for n in d)
                                   + "\n\n(alla prima scrittura viene creata una copia .bak)"):
            return
        try:
            saved = gd.save()
        except Exception as e:
            messagebox.showerror("Errore di salvataggio", str(e))
            return
        after_change()
        status.set("Salvati: " + ", ".join(saved))

    def on_close():
        if gd.dirty_files() and not messagebox.askyesno("Esci", "Ci sono modifiche non salvate. Uscire comunque?"):
            return
        root.destroy()

    ttk.Button(top, text="Apri cartella gioco...", command=open_folder).pack(side="left")
    ttk.Button(top, text="Salva", command=save).pack(side="left", padx=6)
    ttk.Label(top, text="Righe gialle = modificate rispetto al file caricato. Interi in esadecimale.",
              foreground="#555").pack(side="left", padx=12)

    for tbl in TABLES:
        tabs.append(TableTab(tbl))
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("<Control-s>", lambda e: save())

    last = load_cfg().get("folder")
    if last and os.path.isdir(last):
        root.after(100, lambda: open_folder(last))
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--dump":
        only = sys.argv[sys.argv.index("--table") + 1] if "--table" in sys.argv else None
        dump(sys.argv[2], only)
    else:
        run_gui()
