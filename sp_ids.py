#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sp_ids.py - elenca e crea gli ID di animazione dei file sp_0NN.bin e dei file del personaggio plNN
(Resident Evil Outbreak File 2).

Struttura (verificata su sp_026, sp_029, pl05_pc_000):
  - header: 2 parole, poi la tabella delle sezioni (dimensione in parole, offset) a partire da 0x8
  - file sp (40 sezioni): 0..19 = banco A (maschile), 20..39 = banco B (femminile)
  - file del personaggio (20 sezioni): un solo banco, personalizzato per quel personaggio
  - ogni sezione = record da 20 byte (lower, upper, face, hand1, hand2), 0xFFFFFFFF = assente
  - ID = 100 * (sezione nel banco) + indice del record; un ID oltre la fine della sezione non esiste

Uso:
  python sp_ids.py                                  apre la finestra grafica (anche: --gui [file])
  python sp_ids.py sp_029.bin                       tutti gli ID
  python sp_ids.py sp_029.bin --free                ID liberi in tutti i banchi del file + liberi in un solo banco
  python sp_ids.py sp_029.bin --id 0x87             un solo ID, banchi affiancati
  python sp_ids.py sp_029.bin --bank A --range 0x64 0xC7
  python sp_ids.py sp_029.bin --dat 2.DAT           marca gli ID usati dalle righe della tabella del 2.DAT
  python sp_ids.py sp_029.bin --find 0x20AE14       trova di che ID e' un offset
  python sp_ids.py sp_029.bin --csv ids.csv         salva tutto in CSV
  python sp_ids.py pl05_pc_000.bin --free --altri sp_026.bin pc_001.bin
                                                    file del personaggio + confronto con altri file (sp, pc)
  python sp_ids.py --pl-cartella CARTELLA_PL --sp sp_026.bin --out CARTELLA_NUOVA
                                                    crea in ogni pl00..pl07 gli ID custom che mancano: Caution 0x6C-0x6F (copie del personaggio),
                                                    Danger 0x70 0x75-0x77, Ground 0x71-0x73, Hurt 0x132 0x133 (copie dello stage, banco A per 0-4, B per 5-7)
Creazione (blocchi placeholder in fondo al file + record compilati; l'originale non viene toccato):
  python sp_ids.py sp_029.bin --crea 0x87 --tipi-m lu --tipi-f luf --out sp_029_new.bin
  python sp_ids.py pl05_pc_000.bin --crea 0x6C --tipi luh --out pl05_new.bin
     tipi: l=lower(10 ossa) u=upper(12) f=face(6) h=hand1+hand2(4+4); --condividi = A e B puntano agli stessi blocchi
"""
import sys, os, re, struct, argparse, csv

ROWS0, NROWS = 0x733680, 842       # tabella delle righe nel 2.DAT (indirizzi RAM)
DAT_BASE = 0x543000
F = 0xFFFFFFFF
FIELDS = ("lower", "upper", "face", "hand1", "hand2")
BONES = {"lower": 10, "upper": 12, "face": 6, "hand1": 4, "hand2": 4}
FIELD_IDX = {"lower": 0, "upper": 1, "face": 2, "hand1": 3, "hand2": 4}
LETTER = {"l": ("lower",), "u": ("upper",), "f": ("face",), "h": ("hand1", "hand2")}
BANKNAME = {"A": "A (maschile)", "B": "B (femminile)", "P": "personaggio"}

# ------------------------------------------------------------------ lettura
def read_sections(d):
    """Lista (dimensione_in_parole, offset). Il numero di sezioni si ricava dall'offset della prima."""
    if len(d) < 16: return []
    first = struct.unpack_from("<I", d, 12)[0]
    if first < 16 or first > len(d) or (first - 8) % 8: return []
    n = (first - 8) // 8
    if n not in (20, 40): return []
    secs = []
    for k in range(n):
        s, o = struct.unpack_from("<2I", d, 8 + 8 * k)
        if o > len(d) or s > 0x10000: return []
        secs.append((s, o))
    return secs

def kind(secs):
    return "sp" if len(secs) == 40 else ("pl" if len(secs) == 20 else None)

def banks_of(secs):
    return ("A", "B") if len(secs) == 40 else ("P",)

def bank_of_section(secs, k):
    if len(secs) == 40: return "A" if k < 20 else "B"
    return "P"

def block_info(d, off):
    """(ossa, dimensione) se off e' l'inizio di un blocco (intestazione 0x80000001/2)."""
    if off == F: return None
    if off + 12 > len(d): return "fuori file"
    h, nb, sz = struct.unpack_from("<III", d, off)
    if h in (0x80000001, 0x80000002): return (nb, sz)
    return "non e' un blocco"

def records(d):
    secs = read_sections(d); out = []
    for k, (s, o) in enumerate(secs):
        if not s: continue
        for j in range(s * 4 // 20):
            addr = o + 20 * j
            if addr + 20 > len(d): break
            offs = struct.unpack_from("<5I", d, addr)
            out.append(dict(sec=k, bank=bank_of_section(secs, k), idx=j, id=100 * (k % 20) + j,
                            addr=addr, offs=offs, free=all(x == F for x in offs)))
    return out

def by_id(recs):
    m = {}
    for r in recs: m.setdefault(r["id"], {})[r["bank"]] = r
    return m

def dat_used_ids(path):
    d = open(path, "rb").read(); used = set()
    for n in range(NROWS):
        p = ROWS0 + 8 * n - DAT_BASE
        if p + 8 > len(d): break
        r = struct.unpack_from("<4H", d, p)
        for v in (r[2], r[3]):
            if v & 0xFFF: used.add(v & 0xFFF)
    return used

def other_used(paths):
    """{id: ["sp_026 A", "pc_001", ...]} = dove l'ID ha un record USATO negli altri file."""
    res = {}
    for p in paths:
        d = open(p, "rb").read()
        if not read_sections(d): raise ValueError("%s: non sembra un file sp/pl (tabella delle sezioni non trovata)" % p)
        nm = os.path.splitext(os.path.basename(p))[0]; multi = len(read_sections(d)) == 40
        for r in records(d):
            if not r["free"]: res.setdefault(r["id"], []).append(nm + (" " + r["bank"] if multi else ""))
    return res

def ranges(ids):
    ids = sorted(ids); out = []; s = p = None
    for i in ids:
        if s is None: s = p = i
        elif i == p + 1: p = i
        else: out.append((s, p)); s = p = i
    if s is not None: out.append((s, p))
    return out

def fr(ids):
    return ", ".join(("0x%X" % x) if x == y else ("0x%X-0x%X" % (x, y)) for x, y in ranges(ids)) or "-"

def fmt_off(d, x):
    if x == F: return "-"
    bi = block_info(d, x)
    tag = "%d ossa" % bi[0] if isinstance(bi, tuple) else "?"
    return "0x%X (%s)" % (x, tag)

# ------------------------------------------------------------------ scrittura (placeholder)
def shortest_blocks(d, recs, bank):
    """Per ogni tipo, il blocco (offset, lunghezza) piu' corto del banco: e' il placeholder da copiare.
    La dimensione scritta nell'intestazione e' la lunghezza totale del blocco (intestazione compresa)."""
    best = {}
    for r in recs:
        if r["bank"] != bank: continue
        for t, fi in FIELD_IDX.items():
            o = r["offs"][fi]
            if o == F or o + 12 > len(d): continue
            h, nb, sz = struct.unpack_from("<III", d, o)
            if h != 0x80000002 or nb != BONES[t] or sz < 12 or o + sz > len(d): continue
            if t not in best or sz < best[t][1]: best[t] = (o, sz)
    return best

def types_of(letters):
    out = []
    for c in letters:
        for t in LETTER[c]: out.append(t)
    return out

def make_animation(d, recs, anim_id, tipi, condividi=False):
    """tipi = {"A": "lu", "B": "luf"} oppure {"P": "luh"} (lettere l/u/f/h; banco assente o "" = non scrivere).
    Ritorna (bytearray nuovo, [righe di resoconto]). Lancia ValueError se qualcosa non va."""
    m = by_id(recs).get(anim_id, {})
    banks = [b for b in ("A", "B", "P") if tipi.get(b)]
    if not banks: raise ValueError("Nessun banco selezionato.")
    for b in banks:
        r = m.get(b)
        if r is None: raise ValueError("ID 0x%X: nel banco %s il record non esiste (la sezione e' piu' corta)." % (anim_id, BANKNAME[b]))
        if not r["free"]: raise ValueError("ID 0x%X: nel banco %s e' gia' USATO." % (anim_id, BANKNAME[b]))
        if any(c not in LETTER for c in tipi[b]) or "l" not in tipi[b]: raise ValueError("Tipi non validi per il banco %s (lettere l/u/f/h, almeno 'l')." % BANKNAME[b])
    share = condividi and len(banks) == 2
    if share and sorted(tipi[banks[0]]) != sorted(tipi[banks[1]]):
        raise ValueError("Per condividere i blocchi i tipi dei due banchi devono essere uguali.")
    out = bytearray(d); rep = []; made = {}
    sbs = {b: shortest_blocks(d, recs, b) for b in banks}
    for b in banks:
        offs = [F] * 5
        for t in types_of(tipi[b]):
            if share and b == banks[1]:
                pos, sz = made[(banks[0], t)]
            else:
                if t not in sbs[b]: raise ValueError("Nel banco %s non c'e' nessun blocco %s da copiare." % (BANKNAME[b], t))
                o, sz = sbs[b][t]
                while len(out) % 4: out.append(0)
                pos = len(out); out.extend(d[o:o + sz]); made[(b, t)] = (pos, sz)
            offs[FIELD_IDX[t]] = pos
            rep.append("banco %s %-5s -> 0x%X (%d byte, %d ossa)%s" % (BANKNAME[b], t, pos, sz, BONES[t], "  [condiviso]" if share and b == banks[1] else ""))
        struct.pack_into("<5I", out, m[b]["addr"], *offs)
        rep.append("banco %s: record 0x%X dell'ID 0x%X compilato" % (BANKNAME[b], m[b]["addr"], anim_id))
    # verifica: rileggo il file nuovo
    o2 = bytes(out); r2 = by_id(records(o2))[anim_id]
    for b in banks:
        for t in types_of(tipi[b]):
            bi = block_info(o2, r2[b]["offs"][FIELD_IDX[t]])
            if not (isinstance(bi, tuple) and bi[0] == BONES[t]): raise ValueError("verifica fallita su banco %s %s" % (b, t))
    rep.append("file: %d -> %d byte (0x%X -> 0x%X)" % (len(d), len(out), len(d), len(out)))
    return out, rep


# ------------------------------------------------------------------ animazioni custom per ogni personaggio
# (nome, nuovo ID, sorgente del placeholder): "pl" = il file del personaggio, "sp" = lo stage dato come sorgente
CUSTOM = (("caution_idle", 0x6C, "pl", 0x64), ("caution_walk", 0x6D, "pl", 0x65), ("caution_rear", 0x6E, "pl", 0x66), ("caution_run", 0x6F, "pl", 0x67),
          ("danger_idle", 0x70, "sp", 0x83), ("danger_walk", 0x75, "sp", 0x89), ("danger_rear", 0x76, "sp", 0x88), ("danger_run", 0x77, "sp", 0x89),
          ("ground_idle", 0x71, "sp", 0x84), ("ground_forward", 0x72, "sp", 0x8E), ("ground_rear", 0x73, "sp", 0x8F),
          ("hurt_1", 0x132, "sp", 0x346), ("hurt_2", 0x133, "sp", 0x348))
CUSTOM8 = CUSTOM                       # nome vecchio
def bank_of_character(n): return "A" if n <= 4 else "B"      # personaggi 0-4 maschi (banco A), 5-7 femmine (banco B)

def _copy_block(src, out, o):
    """Appende a out una copia del blocco che parte a o nel file src; ritorna (nuovo offset, lunghezza)."""
    bi = block_info(src, o)
    if not isinstance(bi, tuple): raise ValueError("blocco non valido a 0x%X" % o)
    sz = bi[1]
    if sz < 12 or o + sz > len(src): raise ValueError("blocco a 0x%X fuori dal file" % o)
    while len(out) % 4: out.append(0)
    pos = len(out); out.extend(src[o:o + sz]); return pos, sz

def make_custom(d, sp=None, bank=None, custom=CUSTOM):
    """File del personaggio -> (bytearray nuovo, [(nome, id, campo, offset, lunghezza)], [ID saltati perche' gia' presenti]).
    Placeholder: copie dei blocchi del record sorgente (personaggio o stage). Gli ID gia' usati nel file non vengono toccati."""
    secs = read_sections(d)
    if len(secs) != 20: raise ValueError("non e' un file del personaggio (20 sezioni)")
    m = by_id(records(d)); msp = by_id(records(sp)) if sp is not None else None
    out = bytearray(d); rep = []; skipped = []
    face_src = m.get(0x67, {}).get("P")
    for name, nid, kind_, sid in custom:
        r = m.get(nid, {}).get("P")
        if r is None: raise ValueError("ID 0x%X (%s): il record non esiste in questo file (sezione troppo corta)" % (nid, name))
        if not r["free"]: skipped.append((name, nid)); continue
        if kind_ == "pl":
            srcfile = d; src = m.get(sid, {}).get("P")
            if src is None or src["free"]: raise ValueError("ID sorgente 0x%X (%s): manca nel file del personaggio" % (sid, name))
        else:
            if msp is None: raise ValueError("%s: serve uno sp come sorgente" % name)
            srcfile = sp; src = msp.get(sid, {}).get(bank)
            if src is None or src["free"]: raise ValueError("ID sorgente 0x%X (%s): manca nello sp, banco %s" % (sid, name, bank))
        offs = [F] * 5
        for fi in range(5):
            o = src["offs"][fi]
            if o != F and not isinstance(block_info(srcfile, o), tuple):
                if kind_ == "pl":
                    offs[fi] = o; rep.append((name, nid, FIELDS[fi], o, 0)); continue   # valore anomalo del personaggio: ricopiato
                raise ValueError("ID sorgente 0x%X (%s): blocco %s non valido nello sp" % (sid, name, FIELDS[fi]))
            if kind_ == "pl" and o == F and fi == 2 and face_src is not None and not face_src["free"] and isinstance(block_info(d, face_src["offs"][2]), tuple):
                o = face_src["offs"][2]
            if o == F: continue
            pos, sz = _copy_block(srcfile, out, o); offs[fi] = pos
            rep.append((name, nid, FIELDS[fi], pos, sz))
        struct.pack_into("<5I", out, r["addr"], *offs)
    # verifica: rileggo
    o2 = bytes(out); m2 = by_id(records(o2)); m0 = m
    for name, nid, kind_, sid in custom:
        r = m2[nid]["P"]
        if r["free"]: raise ValueError("verifica fallita su 0x%X" % nid)
        if (name, nid) in skipped: continue
        for fi, x in enumerate(r["offs"]):
            if x == F: continue
            bi = block_info(o2, x)
            if not isinstance(bi, tuple):
                srcr = m0.get(sid, {}).get("P") if kind_ == "pl" else None
                if srcr is not None and srcr["offs"][fi] == x: continue
                raise ValueError("verifica fallita su 0x%X %s" % (nid, FIELDS[fi]))
            if bi[0] != BONES[FIELDS[fi]]: raise ValueError("verifica fallita su 0x%X %s" % (nid, FIELDS[fi]))
    for nid in range(0x64, 0x6C):          # gli ID originali non devono cambiare
        if nid in m and m2[nid]["P"]["offs"] != m[nid]["P"]["offs"]: raise ValueError("verifica fallita: ID originale 0x%X cambiato" % nid)
    return out, rep, skipped

def make_custom8(d, custom=None):         # compatibilita': solo le animazioni che vengono dal personaggio
    out, rep, sk = make_custom(d, None, None, [c for c in CUSTOM if c[2] == "pl"])
    return out, rep

def pl_cartella(indir, outdir, sp_path=None):
    """Cerca i file pl00..pl07 (*pl0N_pc_000*.bin) in indir, scrive le copie con le animazioni custom in outdir
    e un CSV con gli offset. sp_path = sp dello stage da cui copiare i placeholder di Danger, Ground e Hurt."""
    sp = None
    if sp_path:
        sp = open(sp_path, "rb").read()
        if len(read_sections(sp)) != 40: raise ValueError("%s non sembra un file sp (40 sezioni)" % sp_path)
    found = {}
    for fn in sorted(os.listdir(indir)):
        mt = re.search(r"pl0([0-7])_pc_000", fn, re.I)
        if mt and fn.lower().endswith(".bin"): found.setdefault(int(mt.group(1)), []).append(fn)
    if not found: raise ValueError("Nessun file pl0N_pc_000*.bin in " + indir)
    custom = CUSTOM if sp is not None else tuple(c for c in CUSTOM if c[2] == "pl")
    rep = [] if sp is not None else ["ATTENZIONE: nessuno sp come sorgente, creo solo le animazioni di Caution"]
    csvrows = []
    for n in range(8):
        if n not in found: rep.append("pl0%d: MANCA (nessun file trovato)" % n); continue
        fn = max(found[n], key=lambda f: os.path.getmtime(os.path.join(indir, f)))
        if len(found[n]) > 1: rep.append("pl0%d: trovati %d file, uso il piu' recente: %s" % (n, len(found[n]), fn))
        d = open(os.path.join(indir, fn), "rb").read()
        try: out, blocks, skipped = make_custom(d, sp, bank_of_character(n), custom)
        except ValueError as e: rep.append("pl0%d (%s): ERRORE %s" % (n, fn, e)); continue
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, fn), "wb").write(out)
        made = sorted({nid for _, nid, _, _, _ in blocks})
        rep.append("pl0%d: %s  %d -> %d byte, creati %d ID%s" % (n, fn, len(d), len(out), len(made),
                   (", gia' presenti (non toccati): " + ", ".join("0x%X" % i for _, i in skipped)) if skipped else ""))
        for name, nid, campo, pos, sz in blocks: csvrows.append((fn, "pl0%d" % n, name, "0x%X" % nid, campo, "0x%X" % pos, sz if sz else "valore anomalo copiato dal sorgente"))
    if csvrows:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "pl_custom_offsets.csv"), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["file", "personaggio", "animazione", "id", "campo", "offset", "lunghezza"]); w.writerows(csvrows)
        rep.append("scritto %s" % os.path.join(outdir, "pl_custom_offsets.csv"))
    return rep

# ------------------------------------------------------------------ GUI
def gui(path=None):
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk(); root.title("sp_ids - ID animazioni dei file sp e del personaggio (Resident Evil Outbreak File 2)"); root.geometry("1180x700")
    st = dict(d=None, recs=[], ids={}, dat=None, sp=None, banks=("A", "B"), altri=None, altri_nomi=[])
    top = ttk.Frame(root); top.pack(fill="x", padx=6, pady=4)
    lab = ttk.Label(top, text="Nessun file aperto"); lab.pack(side="left")
    flt = tk.StringVar(value="tutti"); q = tk.StringVar()
    bar = ttk.Frame(root); bar.pack(fill="x", padx=6)
    cols = ("id", "dec", "b1", "b2", "dat", "altri")
    tv = ttk.Treeview(root, columns=cols, show="headings", height=16, selectmode="browse")
    for c, t, w in (("id", "ID (hex)", 80), ("dec", "ID (dec)", 70), ("b1", "Banco A (maschile)", 200), ("b2", "Banco B (femminile)", 200),
                    ("dat", "Riga 2.DAT", 80), ("altri", "Usato negli altri file", 300)):
        tv.heading(c, text=t); tv.column(c, width=w, anchor="w")
    sb = ttk.Scrollbar(root, orient="vertical", command=tv.yview); tv.configure(yscrollcommand=sb.set)
    tv.pack(side="top", fill="both", expand=True, padx=(6, 0)); sb.place(relx=1.0, rely=0.12, relheight=0.45, anchor="ne")
    tv.tag_configure("comune", background="#e3f6e3"); tv.tag_configure("solo", background="#fff0c8")
    tv.tag_configure("mix", background="#ffd9d9"); tv.tag_configure("altrove", background="#e6e6ff")
    det = tk.Text(root, height=11, font=("Consolas", 10)); det.pack(fill="x", padx=6, pady=4)
    FILTRI = ("tutti", "liberi (in tutti i banchi)", "liberi anche negli altri file", "usati", "attenzione (banchi diversi)")

    def stato(r):
        if r is None: return "assente"
        return "libero" if r["free"] else "usato"
    def headings():
        if st["banks"] == ("P",):
            tv.heading("b1", text="Personaggio (banco unico)"); tv["displaycolumns"] = ("id", "dec", "b1", "dat", "altri")
        else:
            tv.heading("b1", text="Banco A (maschile)"); tv.heading("b2", text="Banco B (femminile)"); tv["displaycolumns"] = cols
    def rows():
        out = []
        for i in sorted(st["ids"]):
            ss = [stato(st["ids"][i].get(b)) for b in st["banks"]]
            if all(s == "libero" for s in ss): kd = "comune"
            elif "libero" in ss and "usato" in ss: kd = "mix"
            elif "libero" in ss: kd = "solo"
            else: kd = "usati"
            out.append((i, ss, kd))
        return out
    def refill(*_):
        tv.delete(*tv.get_children())
        f = flt.get(); text = q.get().strip().lower(); n = 0
        try: want = int(text, 0) if text else None
        except ValueError: want = None
        for i, ss, kd in rows():
            alt = (st["altri"] or {}).get(i, [])
            if f == FILTRI[1] and kd != "comune": continue
            if f == FILTRI[2] and (kd != "comune" or alt): continue
            if f == FILTRI[3] and "usato" not in ss: continue
            if f == FILTRI[4] and kd not in ("mix", "solo"): continue
            if want is not None and i != want: continue
            dat = "" if st["dat"] is None else ("si" if i in st["dat"] else "no")
            altri = "" if st["altri"] is None else (", ".join(alt) if alt else "no")
            tag = "altrove" if (kd == "comune" and alt) else kd
            vals = ("0x%X" % i, i, ss[0], ss[1] if len(ss) > 1 else "", dat, altri)
            tv.insert("", "end", iid=str(i), values=vals, tags=((tag,) if tag in ("comune", "solo", "mix", "altrove") else ())); n += 1
        extra = (" | confronto con: " + ", ".join(st["altri_nomi"])) if st["altri_nomi"] else ""
        lab.config(text="%s [%s] - %d ID mostrati%s" % (st["sp"] or "", "file sp" if st["banks"] != ("P",) else "file del personaggio", n, extra))
    def show(*_):
        sel = tv.selection()
        det.delete("1.0", "end")
        if not sel: return
        i = int(sel[0]); m = st["ids"][i]; d = st["d"]
        det.insert("end", "ID 0x%X (%d)\n" % (i, i))
        for b in st["banks"]:
            r = m.get(b); nm = BANKNAME[b]
            if r is None: det.insert("end", "  Banco %s: record inesistente (sezione piu' corta)\n" % nm); continue
            det.insert("end", "  Banco %s: record 0x%X - %s\n" % (nm, r["addr"], "LIBERO" if r["free"] else "USATO"))
            for fi, x in enumerate(r["offs"]):
                if x != F: det.insert("end", "        %-6s %s\n" % (FIELDS[fi], fmt_off(d, x)))
        if len(st["banks"]) == 2 and "A" in m and "B" in m and m["A"]["free"] != m["B"]["free"]:
            det.insert("end", "  ATTENZIONE: usato in un banco e libero nell'altro.\n")
        if st["altri"] is not None:
            alt = st["altri"].get(i, [])
            det.insert("end", "  Negli altri file: %s\n" % (("USATO in " + ", ".join(alt)) if alt else "libero ovunque"))
    tv.bind("<<TreeviewSelect>>", show)
    def load(p):
        try: d = open(p, "rb").read()
        except OSError as e: messagebox.showerror("Errore", str(e)); return
        secs = read_sections(d)
        if not secs: messagebox.showerror("Errore", "Non sembra un file sp o del personaggio (tabella delle sezioni non trovata)."); return
        st.update(d=d, recs=records(d), sp=p, banks=banks_of(secs)); st["ids"] = by_id(st["recs"]); headings(); refill()
    def open_sp():
        p = filedialog.askopenfilename(title="Apri sp_0NN.bin o file del personaggio", filetypes=[("bin", "*.bin"), ("tutti", "*.*")])
        if p: load(p)
    def open_dat():
        p = filedialog.askopenfilename(title="Apri 2.DAT (opzionale)", filetypes=[("DAT", "*.DAT *.dat"), ("tutti", "*.*")])
        if p:
            try: st["dat"] = dat_used_ids(p)
            except OSError as e: messagebox.showerror("Errore", str(e)); return
            refill()
    def open_altri():
        ps = filedialog.askopenfilenames(title="Altri file da confrontare (sp, pc_xxx, altri personaggi)", filetypes=[("bin", "*.bin"), ("tutti", "*.*")])
        if not ps: return
        try: st["altri"] = other_used(list(ps))
        except (OSError, ValueError) as e: messagebox.showerror("Errore", str(e)); return
        st["altri_nomi"] = [os.path.basename(x) for x in ps]; refill()
    def copy_offsets():
        sel = tv.selection()
        if not sel: return
        i = int(sel[0]); t = []
        for b in st["banks"]:
            r = st["ids"][i].get(b)
            if r: t.append("ID 0x%X banco %s: " % (i, BANKNAME[b]) + ", ".join("%s 0x%X" % (FIELDS[k], x) for k, x in enumerate(r["offs"]) if x != F))
        root.clipboard_clear(); root.clipboard_append("\n".join(t))
    def export_csv():
        if not st["recs"]: return
        p = filedialog.asksaveasfilename(defaultextension=".csv")
        if not p: return
        with open(p, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["id_hex", "banco", "record", "stato"] + list(FIELDS) + ["usato_negli_altri_file"])
            for r in st["recs"]:
                alt = "" if st["altri"] is None else " ".join(st["altri"].get(r["id"], []))
                w.writerow(["0x%X" % r["id"], BANKNAME[r["bank"]], "0x%X" % r["addr"], "libero" if r["free"] else "usato"] + [("" if x == F else "0x%X" % x) for x in r["offs"]] + [alt])
    def crea():
        sel = tv.selection()
        if not st["d"]: messagebox.showinfo("sp_ids", "Apri prima un file."); return
        if not sel: messagebox.showinfo("sp_ids", "Seleziona un ID nella tabella."); return
        i = int(sel[0]); w = tk.Toplevel(root); w.title("Crea animazione ID 0x%X" % i); w.transient(root)
        msg = "ID 0x%X: scrive blocchi placeholder in fondo al file e compila i record.\nI blocchi sono copie dei piu' corti gia' presenti nel banco (da sostituire con Motbreak Studio)." % i
        alt = (st["altri"] or {}).get(i)
        if alt: msg += "\n\nATTENZIONE: l'ID e' USATO in " + ", ".join(alt) + "."
        ttk.Label(w, text=msg, justify="left").pack(padx=10, pady=8)
        vs = {}
        for b in st["banks"]:
            fr_ = ttk.LabelFrame(w, text="Banco " + BANKNAME[b]); fr_.pack(fill="x", padx=10, pady=4)
            vs[b] = {k: tk.BooleanVar(value=(k in ("lower", "upper"))) for k in ("lower", "upper", "face", "hand")}
            vs[b]["on"] = tk.BooleanVar(value=True)
            if len(st["banks"]) > 1: ttk.Checkbutton(fr_, text="scrivi in questo banco", variable=vs[b]["on"]).pack(anchor="w")
            for k, txt in (("lower", "lower (10 ossa)"), ("upper", "upper (12 ossa)"), ("face", "face (6 ossa)"), ("hand", "hand1 + hand2 (4 + 4 ossa)")):
                ttk.Checkbutton(fr_, text=txt, variable=vs[b][k]).pack(anchor="w")
        sh = tk.BooleanVar(value=False)
        if len(st["banks"]) > 1:
            ttk.Checkbutton(w, text="stessa animazione per maschio e femmina (A e B puntano agli stessi blocchi)", variable=sh).pack(anchor="w", padx=10)
        def go():
            tipi = {}
            for b in st["banks"]:
                if vs[b]["on"].get(): tipi[b] = "".join(c for c, k in (("l", "lower"), ("u", "upper"), ("f", "face"), ("h", "hand")) if vs[b][k].get())
            try: out, rep = make_animation(st["d"], st["recs"], i, tipi, sh.get())
            except ValueError as e: messagebox.showerror("Non posso", str(e), parent=w); return
            base, ext = os.path.splitext(os.path.basename(st["sp"]))
            p = filedialog.asksaveasfilename(parent=w, title="Salva il nuovo file (l'originale non viene toccato)", defaultextension=ext or ".bin", initialfile=base + "_new" + (ext or ".bin"))
            if not p: return
            open(p, "wb").write(out)
            txt = "\n".join(rep); w.destroy()
            messagebox.showinfo("Fatto", "Salvato %s\n\n%s" % (p, txt)); root.clipboard_clear(); root.clipboard_append(txt)
            load(p)
        ttk.Button(w, text="Crea e salva...", command=go).pack(pady=8)
    def custom8():
        a = filedialog.askdirectory(title="Cartella con i file pl00..pl07 (pl0N_pc_000)")
        if not a: return
        spf = filedialog.askopenfilename(title="sp dello stage da cui copiare Danger, Ground e Hurt (annulla = solo Caution)", filetypes=[("sp", "*.bin"), ("tutti", "*.*")])
        b = filedialog.askdirectory(title="Cartella di destinazione (i file originali non vengono toccati)")
        if not b: return
        if os.path.abspath(a) == os.path.abspath(b): messagebox.showerror("Errore", "La cartella di destinazione deve essere diversa."); return
        try: rep = pl_cartella(a, b, spf or None)
        except (OSError, ValueError) as e: messagebox.showerror("Errore", str(e)); return
        txt = "\n".join(rep); messagebox.showinfo("Fatto", txt); root.clipboard_clear(); root.clipboard_append(txt)
    for t, c in (("Apri file...", open_sp), ("Apri 2.DAT...", open_dat), ("Confronta con altri file...", open_altri), ("Animazioni custom (cartella pl)...", custom8),
                 ("Copia offset", copy_offsets), ("Esporta CSV...", export_csv), ("Crea animazione...", crea)):
        ttk.Button(bar, text=t, command=c).pack(side="left", padx=2, pady=2)
    ttk.Label(bar, text="  Filtro:").pack(side="left")
    cb = ttk.Combobox(bar, textvariable=flt, state="readonly", width=28, values=FILTRI); cb.pack(side="left"); cb.bind("<<ComboboxSelected>>", refill)
    ttk.Label(bar, text="  Cerca ID:").pack(side="left")
    e = ttk.Entry(bar, textvariable=q, width=8); e.pack(side="left"); e.bind("<Return>", refill)
    ttk.Label(bar, text="  Cerca offset:").pack(side="left")
    qo = tk.StringVar(); eo = ttk.Entry(bar, textvariable=qo, width=10); eo.pack(side="left")
    def find_off(*_):
        if not st["d"]: return
        try: v = int(qo.get().strip(), 0)
        except ValueError: return
        det.delete("1.0", "end"); n = 0
        for r in st["recs"]:
            for fi, x in enumerate(r["offs"]):
                if x == v:
                    n += 1; det.insert("end", "offset 0x%X = campo %s dell'ID 0x%X (%d), banco %s, record 0x%X\n" % (v, FIELDS[fi], r["id"], r["id"], BANKNAME[r["bank"]], r["addr"]))
        if not n: det.insert("end", "offset 0x%X: nessun record lo usa (file lungo 0x%X)\n" % (v, len(st["d"])))
    eo.bind("<Return>", find_off)
    if path: load(path)
    root.mainloop()

# ------------------------------------------------------------------ riga di comando
def main():
    ap = argparse.ArgumentParser(description="Elenco ID di un file sp o del personaggio", formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("sp", nargs="?"); ap.add_argument("--gui", action="store_true")
    ap.add_argument("--bank", choices=("A", "B", "P", "all"), default="all")
    ap.add_argument("--free", action="store_true", help="solo record liberi"); ap.add_argument("--used", action="store_true", help="solo record usati")
    ap.add_argument("--id", type=lambda x: int(x, 0)); ap.add_argument("--range", nargs=2, type=lambda x: int(x, 0), metavar=("DA", "A"))
    ap.add_argument("--dat", help="2.DAT: segna gli ID usati dalle righe della tabella"); ap.add_argument("--csv")
    ap.add_argument("--altri", nargs="+", metavar="FILE", help="altri file (sp, pc_xxx, altri personaggi): segna dove l'ID e' gia' usato")
    ap.add_argument("--find", type=lambda x: int(x, 0), help="offset di un blocco: dice di quale ID e'")
    ap.add_argument("--crea", type=lambda x: int(x, 0), help="ID da creare: scrive i blocchi placeholder in fondo al file e compila i record")
    ap.add_argument("--tipi", default="lu", help="file del personaggio: lettere l/u/f/h (default lu)")
    ap.add_argument("--tipi-m", default="lu", help="file sp, banco A maschile: lettere l/u/f/h (default lu)")
    ap.add_argument("--tipi-f", default="lu", help="file sp, banco B femminile (default lu; vuoto = non scrivere)")
    ap.add_argument("--condividi", action="store_true"); ap.add_argument("--out")
    ap.add_argument("--pl-cartella", metavar="DIR", help="cartella con pl00..pl07: crea le animazioni custom in ogni file; serve --out DIR2 (e --sp per Danger, Ground, Hurt)")
    ap.add_argument("--sp", dest="sp_src", metavar="SP", help="con --pl-cartella: sp dello stage da cui copiare i placeholder di Danger, Ground e Hurt")
    a = ap.parse_args()
    if a.pl_cartella:
        if not a.out: print("Serve --out CARTELLA_DESTINAZIONE."); return 1
        if os.path.abspath(a.pl_cartella) == os.path.abspath(a.out): print("La destinazione deve essere diversa dalla cartella di partenza."); return 1
        try: print("\n".join(pl_cartella(a.pl_cartella, a.out, a.sp_src)))
        except (OSError, ValueError) as e: print("ERRORE:", e); return 1
        return 0
    if a.gui or not a.sp: return gui(a.sp)
    d = open(a.sp, "rb").read()
    secs = read_sections(d)
    if not secs: print("Non sembra un file sp o del personaggio (tabella delle sezioni non trovata)."); return 1
    banks = banks_of(secs); tipo = kind(secs)
    recs = records(d); ids = by_id(recs)
    used_dat = dat_used_ids(a.dat) if a.dat else None
    try: alt = other_used(a.altri) if a.altri else None
    except ValueError as e: print("ERRORE:", e); return 1

    if a.crea is not None:
        if not a.out: print("Serve --out nuovo_file.bin (l'originale non viene toccato)."); return 1
        tipi = {"A": a.tipi_m, "B": a.tipi_f} if tipo == "sp" else {"P": a.tipi}
        try: out, rep = make_animation(d, recs, a.crea, tipi, a.condividi)
        except ValueError as e: print("ERRORE:", e); return 1
        if alt and alt.get(a.crea): print("ATTENZIONE: l'ID 0x%X e' USATO anche in: %s" % (a.crea, ", ".join(alt[a.crea])))
        open(a.out, "wb").write(out); print("\n".join(rep)); print("scritto", a.out); return 0

    if a.find is not None:
        n = 0
        for r in recs:
            for fi, x in enumerate(r["offs"]):
                if x == a.find:
                    n += 1; print("offset 0x%X = campo %s del record ID 0x%X (%d), banco %s, sezione %d, indice %d, record a 0x%X"
                                  % (a.find, FIELDS[fi], r["id"], r["id"], BANKNAME[r["bank"]], r["sec"], r["idx"], r["addr"]))
        if not n: print("offset 0x%X: nessun record lo usa (file lungo 0x%X)%s" % (a.find, len(d), "; e' oltre la fine del file" if a.find >= len(d) else ""))
        return 0

    sel = [r for r in recs if (a.bank == "all" or r["bank"] == a.bank)]
    if a.id is not None: sel = [r for r in sel if r["id"] == a.id]
    if a.range: sel = [r for r in sel if a.range[0] <= r["id"] <= a.range[1]]
    if a.free: sel = [r for r in sel if r["free"]]
    if a.used: sel = [r for r in sel if not r["free"]]

    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f); w.writerow(["id_hex", "id_dec", "banco", "sezione", "indice", "record_addr", "stato", "usato_da_righe_dat"] + list(FIELDS) + ["usato_negli_altri_file"])
            for r in sel:
                w.writerow(["0x%X" % r["id"], r["id"], BANKNAME[r["bank"]], r["sec"], r["idx"], "0x%X" % r["addr"], "libero" if r["free"] else "usato",
                            ("si" if r["id"] in used_dat else "no") if used_dat is not None else ""] + [("" if x == F else "0x%X" % x) for x in r["offs"]]
                           + [" ".join(alt.get(r["id"], [])) if alt is not None else ""])
        print("scritto", a.csv, "(%d record)" % len(sel))

    print("%s: %d byte, %d sezioni - %s" % (a.sp, len(d), len(secs), "file sp (banco A maschile: 0-19, banco B femminile: 20-39)" if tipo == "sp" else "file del personaggio (banco unico)"))
    if a.altri: print("confronto con: " + ", ".join(os.path.basename(x) for x in a.altri))

    if a.free:
        free = {b: {r["id"] for r in sel if r["bank"] == b and r["free"]} for b in banks}
        exist = {b: {r["id"] for r in recs if r["bank"] == b} for b in banks}
        com = set.intersection(*free.values()) if free else set()
        what = "in comune a A e B" if tipo == "sp" else "nel file del personaggio"
        print("\nID liberi %s (%d)%s:" % (what, len(com), " - sicuri per una nuova animazione, vanno scritti in tutti e due i banchi" if tipo == "sp" else ""))
        print("  " + fr(com))
        if used_dat is not None:
            nu = [i for i in com if i not in used_dat]
            print("  di cui non usati da nessuna riga del 2.DAT (%d): %s" % (len(nu), fr(nu)))
        if alt is not None:
            ok = [i for i in com if i not in alt]; ko = sorted(i for i in com if i in alt)
            print("  di cui liberi anche negli altri file (%d): %s" % (len(ok), fr(ok)))
            if ko:
                print("  liberi qui ma USATI negli altri file (%d):" % len(ko))
                for i in ko: print("    ID 0x%X: %s" % (i, ", ".join(alt[i])))
        if tipo == "sp":
            for b, o in (("A", "B"), ("B", "A")):
                only = sorted(free[b] - free[o])
                if only:
                    print("\nLiberi solo nel banco %s (%d) - NON utilizzabili in comune:" % (BANKNAME[b], len(only)))
                    for i in only:
                        print("  ID 0x%X: %s" % (i, "nel banco %s il record non esiste (sezione piu' corta)" % o if i not in exist[o] else "nel banco %s e' USATO" % o))
        for b in banks:
            ks = [k for k in range(len(secs)) if bank_of_section(secs, k) == b and secs[k][0]]
            print("\nID disponibili nel banco %s, per sezione: " % BANKNAME[b] + "; ".join("%d: 0x%X-0x%X" % (k % 20, 100 * (k % 20), 100 * (k % 20) + secs[k][0] * 4 // 20 - 1) for k in ks))
        return 0

    if a.id is not None and a.bank == "all":
        m = ids.get(a.id, {})
        print("\nID 0x%X (%d)" % (a.id, a.id))
        for b in banks:
            r = m.get(b)
            if r is None: print("  Banco %s: record inesistente (sezione troppo corta)" % BANKNAME[b]); continue
            print("  Banco %s: record 0x%X - %s%s" % (BANKNAME[b], r["addr"], "LIBERO" if r["free"] else "USATO",
                  "" if used_dat is None else "  [riga 2.DAT: %s]" % ("si" if r["id"] in used_dat else "no")))
            for fi, x in enumerate(r["offs"]):
                if x != F: print("        %-6s %s" % (FIELDS[fi], fmt_off(d, x)))
        if tipo == "sp":
            if len(m) < 2: print("  ATTENZIONE: ID presente in un solo banco.")
            elif m["A"]["free"] != m["B"]["free"]: print("  ATTENZIONE: usato in un banco e libero nell'altro (un personaggio dell'altro sesso non troverebbe l'animazione).")
        if alt is not None: print("  Negli altri file: %s" % (("USATO in " + ", ".join(alt[a.id])) if a.id in alt else "libero ovunque"))
        return 0

    last = None
    for r in sel:
        key = (r["bank"], r["sec"])
        if key != last:
            last = key; print("\n== Banco %s - sezione %d (gruppo %d, IDs da 0x%X) - inizio sezione 0x%X ==" % (BANKNAME[r["bank"]], r["sec"], r["sec"] % 20, 100 * (r["sec"] % 20), secs[r["sec"]][1]))
        mark = ""
        if used_dat is not None: mark += "  [riga 2.DAT: %s]" % ("si" if r["id"] in used_dat else "no")
        if alt is not None and r["id"] in alt: mark += "  [usato in: %s]" % ", ".join(alt[r["id"]])
        if r["free"]:
            print("  ID 0x%03X (%4d)  record 0x%X  LIBERO%s" % (r["id"], r["id"], r["addr"], mark))
        else:
            print("  ID 0x%03X (%4d)  record 0x%X  USATO%s" % (r["id"], r["id"], r["addr"], mark))
            for fi, x in enumerate(r["offs"]):
                if x != F: print("        %-6s %s" % (FIELDS[fi], fmt_off(d, x)))
    nfree = sum(1 for r in recs if r["free"]); print("\nTotale record: %d, liberi: %d, usati: %d" % (len(recs), nfree, len(recs) - nfree))
    return 0

if __name__ == "__main__":
    sys.exit(main())
