#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
REOB patcher - Resident Evil Outbreak File 2 (JP), file 2.DAT
Applica (o toglie) patch scelte a un 2.DAT. Non modifica mai l'originale: salva un nuovo file.

  python reob_patcher.py            -> finestra
  python reob_patcher.py --cli 2.DAT out.DAT voci_zombie caution_idle ...   (senza finestra)
  python reob_patcher.py --list     -> elenco gruppi
  python reob_patcher.py --cli --suoni 2.DAT suoni.txt out.DAT   -> scrive la tabella eventi (gruppo suoni gia' applicato)

Indirizzi = RAM PS2; offset nel file 2.DAT = indirizzo - 0x543000.
Ogni patch controlla i byte originali: se non coincidono (altra versione del gioco, o gia' toccata
da altro) il gruppo e' segnato "in conflitto" e non viene scritto.
"""
import sys, struct, os

BASE = 0x543000

# ---------------------------------------------------------------- assemblatore minimo MIPS
H   = 0x56ACB0   # voce giocatore da evento animazione
RET = 0x5769A0
def j(t):   return 0x08000000 | ((t >> 2) & 0x3FFFFFF)
def jal(t): return 0x0C000000 | ((t >> 2) & 0x3FFFFFF)
def b_to(src, dst): return 0x10000000 | (((dst - (src + 4)) >> 2) & 0xFFFF)
def bne(src, dst, rs, rt): return 0x14000000 | (rs << 21) | (rt << 16) | (((dst - (src + 4)) >> 2) & 0xFFFF)
NOP = 0
MOVS_F12_F20 = 0x4600A306
def addiu(rt, rs, imm): return 0x24000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def daddu(rd, rs, rt): return (rs << 21) | (rt << 16) | (rd << 11) | 0x2D
LD_RA_SP = 0xDFBF0000
def lhu(rt, rs, imm): return 0x94000000 | (rs << 21) | (rt << 16) | imm
A0, A1, A2, A3, V0, V1, T1, S0, ZERO = 4, 5, 6, 7, 2, 3, 9, 16, 0

# zona A (0x715B10, dopo l'ultima funzione) e zona B (0x543028, padding dell'header)
SVG_Z = 0x715B10; SV_A = 0x715B30; SV_B = 0x715B38; WA = 0x715B40; C17 = 0x715B50
W1D = 0x543028; SV_1D = 0x543038; C14 = 0x543058

def words(ws): return b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in ws)

def code_blocks():
    out = {}
    out[SVG_Z] = [daddu(A0, T1, ZERO), MOVS_F12_F20, daddu(A1, S0, ZERO), addiu(A2, ZERO, 2), jal(H), addiu(A3, ZERO, 1), j(RET), NOP]
    out[SV_A]  = [j(SVG_Z), addiu(T1, ZERO, 0x1A)]
    out[SV_B]  = [j(SVG_Z), addiu(T1, ZERO, 0x26)]
    out[WA]    = [jal(0x56B150), NOP, j(SV_A), NOP]
    c = C17
    out[C17]   = [addiu(V1, ZERO, 0x17), bne(c+4, c+40, A1, V1), lhu(A2, A0, 0x212),
                  addiu(V0, ZERO, 0x36), bne(c+16, c+40, A2, V0), daddu(A1, A0, ZERO),
                  addiu(A0, ZERO, 1), daddu(A2, ZERO, ZERO), jal(H), addiu(A3, ZERO, 0x18),
                  j(0x56AB5C), LD_RA_SP]
    out[W1D]   = [jal(0x56B560), NOP, j(SV_1D), NOP]
    out[SV_1D] = [addiu(A0, ZERO, 0x18), MOVS_F12_F20, daddu(A1, S0, ZERO), daddu(A2, ZERO, ZERO), jal(H), addiu(A3, ZERO, 5), j(0x57759C), NOP]
    c = C14
    out[C14]   = [addiu(V1, ZERO, 0x33), bne(c+4, c+24, A0, V1), daddu(A2, ZERO, ZERO),
                  addiu(A0, ZERO, 70), jal(H), addiu(A3, ZERO, 0x18),
                  j(0x576FB4), LD_RA_SP]
    return out

# ---------------------------------------------------------------- gruppi
# patch = (indirizzo, byte nuovi, byte originali attesi)
GROUPS = []   # (id, titolo, descrizione, [patch])

def _code(caves, sites):
    blk = code_blocks(); p = []
    for a in caves:
        w = blk[a]; p.append((a, words(w), b"\0" * (4 * len(w))))
    for a, new, old in sites: p.append((a, words([new]), words([old])))
    return p

GROUPS.append(("voci_zombie",
    "Voce del giocatore: zombie (FF 01)",
    "Voce di dolore del giocatore quando lo morde uno zombie.",
    _code([SVG_Z, SV_A, SV_B, WA], [
        (0x576884, j(SV_A),  b_to(0x576884, RET)),
        (0x5768A4, j(SV_A),  b_to(0x5768A4, RET)),
        (0x5768C4, j(SV_B),  b_to(0x5768C4, RET)),
        (0x5768E4, j(SV_B),  b_to(0x5768E4, RET)),
        (0x57697C, j(SV_B),  b_to(0x57697C, RET)),
        (0x576998, jal(WA),  jal(0x56B150)),
    ])))
GROUPS.append(("voce_14",
    "Voce del giocatore: nemico 14 (anim 0x33)",
    "Voce del giocatore quando lo afferra la pianta (nemico 14).",
    _code([C14], [(0x576F94, j(C14), b_to(0x576F94, 0x576FB4))])))
GROUPS.append(("voce_17",
    "Voce del giocatore: nemico 17 (anim 0x36)",
    "Voce del giocatore quando lo afferra il nemico 17 (non verificata in gioco).",
    _code([C17], [(0x56A9F8, j(C17), b_to(0x56A9F8, 0x56AB5C))])))
GROUPS.append(("voce_1d",
    "Voce del giocatore: nemico 1D (anim 0x33/0x34)",
    "Voce del giocatore quando lo lancia l'elefante (nemico 1D).",
    _code([W1D, SV_1D], [(0x577594, jal(W1D), jal(0x56B560))])))

def le2(v): return struct.pack("<H", v)

def _row(a, flags, q, ida, idb): return struct.pack("<4H", flags, q, ida, idb)

_idle = [
    (0x733A2E, le2(0x82), le2(0)),       # riga 117, gambe (canale 0) = 0x82
    (0x733A36, le2(0x82), le2(0)),       # riga 118
]
for c in range(8):                       # righe di destinazione della transizione 0x2051 (riga 13 -> 494+personaggio)
    a = 0x7345F0 + 8 * c
    _idle.append((a, _row(a, 0x10, 0, 0x82, 0), _row(a, 0x20, 0, 0, 0x64)))
_idle50 = []
for c in range(8):                       # transizione 0x2050 (riga 12 -> 486+personaggio)
    a = 0x7345B0 + 8 * c
    _idle50.append((a, _row(a, 0x10, 0, 0x82, 0), _row(a, 0x20, 0, 0, 0x6B)))

_walk = [(0x732A2A, le2(0xBD), le2(3)),     # camminata avanti  (azione 3, variante 1 = Caution)
         (0x732A32, le2(0xBE), le2(4)),     # camminata indietro (azione 4)
         (0x732A3A, le2(0xBF), le2(5))]     # corsa (azione 5)

GROUPS.append(("caution",
    "Caution (arancione): animazioni complete",
    "Vecchia versione: Caution animato con le animazioni dello stage (richiede l'ID 0x82 negli sp). Esclusivo con 'pl_custom'.",
    _idle + _idle50 + _walk))

def _a0(n): return struct.pack("<I", 0x24040000 | n)       # addiu a0, zero, n  (fotogramma dell'evento sonoro)
def _a3(n): return struct.pack("<I", 0x24070000 | n)       # addiu a3, zero, n  (voce/suono dell'evento)
GROUPS.append(("danger",
    "Danger (rosso): corsa con la nuova animazione (ID 0x87) e suoni",
    "Vecchia versione: corsa Danger con l'ID 0x87 dello stage, con suoni. Esclusivo con 'pl_custom'.",
    [(0x733A8C, le2(0x87), le2(0x89)),                    # riga 0x81: ID_a
     (0x733A8E, le2(0x87), le2(0x89)),                    # riga 0x81: ID_b
     (0x732A3C, le2(0x81), le2(0x81), (le2(0x136),)),     # casella: deve restare 0x81 (0x136 = versione vecchia del patcher)
     # suoni, dispatcher CE9=0 (0x56B640)
     (0x56C4E0, _a0(0x12), _a0(0x1A)),   # passo 1 (slot di ritardo del confronto con 0x87)
     (0x56CAC8, _a0(0x2C), _a0(0x52)),   # passo 2
     (0x56CB00, _a0(5),    _a0(0x5C)),   # respiro (ramo giocatore)
     (0x56CB04, _a0(5),    _a0(0x5C)),   # respiro (ramo che cade)
     (0x56CB10, _a3(8),    _a3(0x0A)),   # voce del respiro: 8/9 come nella corsa di Fine e Caution
     (0x56CB2C, _a3(2),    _a3(3)),      # stessa cosa nel ramo NPC
     # suoni, dispatcher CE9=1 (0x570430)
     (0x5713AC, _a0(0x12), _a0(0x28)),
     (0x5718F8, _a0(0x2C), _a0(0x3C), (_a0(0x32),)),   # 0x32 = valore scritto dalla versione vecchia
     (0x571918, _a0(5),    _a0(0x2E)),
     (0x57191C, _a0(5),    _a0(0x2E)),
     (0x571928, _a3(8),    _a3(0x0A)),
     (0x571944, _a3(2),    _a3(3))]))


# ---------------------------------------------------------------- animazioni dal file del personaggio
ROW0 = 0x733680
def _rowaddr(n): return ROW0 + 8 * n
def _r(flags, q, a, b): return struct.pack("<4H", flags, q, a, b)
def _anchor(base): return _r(0x00F0, 0, 0, base)            # riga di rimando F0: riga = base + personaggio
_EMPTY, _ZERO = _r(0x0020, 0, 0, 0), _r(0, 0, 0, 0)
_C8 = _r(0x0010, 0, 0xC8, 0xC8)
def _action(lst, anchors, base, old_row, target):
    """anchors = [(riga, contenuto originale)]; base = blocco di 8 righe; target = contenuto delle 8 righe."""
    for row, old in anchors: lst.append((_rowaddr(row), _anchor(base), old))
    for c in range(8): lst.append((_rowaddr(base + c), target, old_row))
_PL = []
# Caution (ID dal personaggio)
_action(_PL, [(0x75, _r(0x10, 0, 0x82, 0))], 0x2F6, _EMPTY, _r(0x20, 0, 0x6C, 0x6C))          # idle
for c in range(8):                                                                                # transizioni verso l'idle (solo gambe)
    _PL.append((_rowaddr(0x1E6 + c), _r(0x20, 0, 0, 0x6C), _r(0x20, 0, 0, 0x6B)))
    _PL.append((_rowaddr(0x1EE + c), _r(0x20, 0, 0, 0x6C), _r(0x20, 0, 0, 0x64)))
_action(_PL, [(0x30E, _C8)], 0x2FE, _C8,    _r(0x20, 0, 0x6D, 0x6D))                              # cammina
_action(_PL, [(0x30F, _C8)], 0x306, _C8,    _r(0x20, 0, 0x6E, 0x6E))                              # indietro
_action(_PL, [(0x310, _C8)], 0x2EE, _EMPTY, _r(0x20, 0, 0x6F, 0x6F))                              # corsa
_PL += [(0x732A2A, le2(0x30E), le2(3)), (0x732DEA, le2(0x30E), le2(0xBD)),                       # caselle Caution (tabelle A e B)
        (0x732A32, le2(0x30F), le2(4)), (0x732DF2, le2(0x30F), le2(0xBE)),
        (0x732A3A, le2(0x310), le2(5)), (0x732DFA, le2(0x310), le2(0xBF))]
# Danger
_action(_PL, [(0x7D, _r(0x10, 0, 0x83, 0x83))], 0x1BE, _EMPTY, _r(0x20, 0, 0x70, 0x70))         # idle
_action(_PL, [(0x7F, _r(0x10, 0, 0x89, 0x89))], 0x2DE, _EMPTY, _r(0x20, 0, 0x75, 0x75))         # cammina
_action(_PL, [(0x80, _r(0x10, 2, 0x88, 0x88))], 0xFA2, _ZERO,  _r(0x20, 2, 0x76, 0x76))         # indietro (blocco dopo la tabella)
_action(_PL, [(0x81, _r(0x10, 0, 0x89, 0x89))], 0x2E6, _EMPTY, _r(0x20, 0, 0x77, 0x77))         # corsa
_PL.append((0x732A3C, le2(0x81), le2(0x81), (le2(0x136),)))                                       # casella Danger corsa
# Ground (a terra)
_action(_PL, [(0xB0, _r(0x10, 1, 0x84, 0x84))], 0xFAA, _ZERO, _r(0x20, 1, 0x71, 0x71))          # idle
_action(_PL, [(r, _r(0x10, 1, 0x8E, 0x8E)) for r in (0xB2, 0xB4, 0xB5)], 0xFB2, _ZERO, _r(0x20, 1, 0x72, 0x72))   # avanti
_action(_PL, [(0xB3, _r(0x10, 2, 0x8F, 0x8F))], 0xFBA, _ZERO, _r(0x20, 2, 0x73, 0x73))          # indietro
GROUPS.append(("pl_custom",
    "Caution, Danger e Ground dal file del personaggio",
    "Richiede in tutti i pl0N_pc_000 gli ID 0x6C-0x6F, 0x70, 0x75-0x77, 0x71-0x73 (sp_ids.py). Esclusivo con 'caution' e 'danger'.",
    _PL))
_HURT = []
_action(_HURT, [(0x1A1, _r(0x10, 0, 0x345, 0))], 0xFC2, _ZERO, _r(0x20, 0, 0x132, 0x132))     # hurt 0x345 -> 0x132 (busto e gambe)
_action(_HURT, [(0x1A9, _r(0x10, 0, 0x347, 0))], 0xFCA, _ZERO, _r(0x20, 0, 0x133, 0x133))     # hurt 0x347 -> 0x133
for _row_, _old_ in ((0x1A4, _r(0x10, 0, 0x346, 0x346)), (0x1AC, _r(0x10, 0, 0x348, 0x348))):  # ripara la versione precedente (0x346/0x348)
    _HURT.append((_rowaddr(_row_), _old_, _old_, (_anchor(0xFC2 if _row_ == 0x1A4 else 0xFCA),)))
GROUPS.append(("pl_hurt",
    "Hurt 0x345 e 0x347 dal file del personaggio",
    "Richiede in tutti i pl0N_pc_000 gli ID 0x132 (hurt 0x345) e 0x133 (hurt 0x347) (sp_ids.py).",
    _HURT))

# ---- suoni degli ID nuovi e tabella eventi --------------------------------------------------------------
# Il selettore 0x56A7F0 e' agganciato a un blocco di codice (ENG). Il blocco: 1) traduce gli ID del personaggio
# negli ID originali; 2) cerca l'ID nella tabella eventi (scritta da suoni.txt) e fa suonare gli eventi trovati;
# 3) se non ci sono eventi e un ID e' cambiato, chiama il dispatcher 0x56B640; 4) all'uscita rimette gli ID.
def _sltiu(rt, rs, imm): return 0x2C000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _lui(rt, imm): return 0x3C000000 | (rt << 16) | imm
def _ori(rt, rs, imm): return 0x34000000 | (rs << 21) | (rt << 16) | imm
def _lbu(rt, rs, imm): return 0x90000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _lw(rt, rs, imm): return 0x8C000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _sw(rt, rs, imm): return 0xAC000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _sh(rt, rs, imm): return 0xA4000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _sb(rt, rs, imm): return 0xA0000000 | (rs << 21) | (rt << 16) | (imm & 0xFFFF)
def _lwc1(ft, rs, imm): return 0xC4000000 | (rs << 21) | (ft << 16) | (imm & 0xFFFF)
def _swc1(ft, rs, imm): return 0xE4000000 | (rs << 21) | (ft << 16) | (imm & 0xFFFF)
def _sll(rd, rt, sa): return (rt << 16) | (rd << 11) | (sa << 6)
def _beq(src, dst, rs, rt): return 0x10000000 | (rs << 21) | (rt << 16) | (((dst - (src + 4)) >> 2) & 0xFFFF)
def _bne(src, dst, rs, rt): return 0x14000000 | (rs << 21) | (rt << 16) | (((dst - (src + 4)) >> 2) & 0xFFFF)
JR_RA = 0x03E00008
SD_RA = 0xFFBF0000
AT, SP = 1, 29
F12 = 12
SND_C = 0x739E10        # traduttore: v0 = ID nuovo -> v0 = ID originale (usa v1 e at)
SND_T = SND_C + 0x2C    # tabella ID 0x6C..0x77 -> ID originale (0 = invariato)
SND_R = SND_C + 0x38    # uscita del selettore: rimette gli ID originali
SND_OLDH = 0x739ED0     # (versioni precedenti: ingresso del selettore; ora vuoto)
ENG = 0x72A540          # blocco di codice (area da verificare libera: 0x72A540-0x72AD8F)
TBL_END = 0x72AD90
SND_TAB = bytes([0, 0x65, 0x66, 0x67, 0x83, 0x84, 0x8E, 0x8F, 0, 0x89, 0x89, 0x89])
def _asm(base, items):
    """items: parola | ('L', nome) | ('beq'|'bne', rs, rt, nome) | ('j', nome|indirizzo) ; due passate"""
    pos, lab = base, {}
    for it in items:
        if isinstance(it, tuple) and it[0] == 'L': lab[it[1]] = pos
        else: pos += 4
    out, pos = [], base
    for it in items:
        if isinstance(it, tuple) and it[0] == 'L': continue
        if isinstance(it, tuple):
            k = it[0]
            if k in ('beq', 'bne'): w = (_beq if k == 'beq' else _bne)(pos, lab[it[3]], it[1], it[2])
            else: w = j(lab[it[1]] if isinstance(it[1], str) else it[1])
        else: w = it
        out.append(w); pos += 4
    return out, lab
def _off(a, hi=0x73): return (a - (hi << 16)) & 0xFFFF
def _snd_tr():
    c = SND_C; E_ = c + 9 * 4
    return [addiu(V1, V0, -0x6C), _sltiu(AT, V1, 12), _beq(c + 8, E_, AT, ZERO), _lui(AT, 0x74), daddu(AT, AT, V1),
            _lbu(AT, AT, _off(SND_T, 0x74)), _beq(c + 24, E_, AT, ZERO), NOP, daddu(V0, AT, ZERO), JR_RA, NOP]
def _snd_hook():
    S = SND_S; T = SND_TBL
    a1, a2, a3 = 5, 6, 7
    items = [
        addiu(SP, SP, -0x10), SD_RA, _lui(AT, 0x73), _sw(A0, AT, _off(S)), _swc1(F12, AT, _off(S + 12)), _sb(ZERO, AT, _off(S + 16)),
        lhu(V0, A0, 0x1F2), _sh(V0, AT, _off(S + 4)), jal(SND_C), NOP, _sh(V0, A0, 0x1F2),
        lhu(V0, A0, 0x212), _lui(AT, 0x73), _sh(V0, AT, _off(S + 6)), jal(SND_C), NOP, _sh(V0, A0, 0x212),
        _lui(AT, 0x73), lhu(V1, AT, _off(S + 6)), _lui(a1, T >> 16), _ori(a1, a1, T & 0xFFFF),
        ('L', 'LOOP'), lhu(V0, a1, 0), ('beq', V0, ZERO, 'DONE'), NOP, ('bne', V0, V1, 'NEXT'), NOP,
        _lui(AT, 0x73), _lw(V1, AT, _off(S)), _sw(a1, AT, _off(S + 8)), addiu(V0, ZERO, 1), _sb(V0, AT, _off(S + 16)),
        _lbu(V0, a1, 4), _lwc1(F12, AT, _off(S + 12)), lhu(A0, a1, 2), _lbu(a2, a1, 5), _lbu(a3, a1, 6),
        ('beq', V0, ZERO, 'DOSTEP'), daddu(a1, V1, ZERO),
        _lbu(V0, V1, 2), ('bne', V0, ZERO, 'AFTER'), NOP, jal(0x56ACB0), NOP, ('j', 'AFTER'), NOP,
        ('L', 'DOSTEP'), jal(0x56AB70), NOP,
        ('L', 'AFTER'), _lui(AT, 0x73), _lw(a1, AT, _off(S + 8)), lhu(V1, AT, _off(S + 6)),
        ('L', 'NEXT'), addiu(a1, a1, 8), ('j', 'LOOP'), NOP,
        ('L', 'DONE'), _lui(AT, 0x73), _lbu(V0, AT, _off(S + 16)), ('beq', V0, ZERO, 'OLD'), NOP, j(0x56A8F8), NOP,
        ('L', 'OLD'), _lw(A0, AT, _off(S)), _lwc1(F12, AT, _off(S + 12)), lhu(V1, AT, _off(S + 4)), lhu(V0, A0, 0x1F2),
        ('bne', V0, V1, 'CALL'), lhu(V1, AT, _off(S + 6)), lhu(V0, A0, 0x212), ('bne', V0, V1, 'CALL'), NOP,
        j(0x56A7FC), addiu(V1, ZERO, 0xFF),
        ('L', 'CALL'), jal(0x56B640), NOP, j(0x56A8F8), NOP]
    return _asm(ENG, items)[0]
def _snd_rest():
    S = SND_S
    return [_lui(AT, 0x73), _lw(V1, AT, _off(S)), lhu(AT, AT, _off(S + 4)), _sh(AT, V1, 0x1F2),
            _lui(AT, 0x73), lhu(AT, AT, _off(S + 6)), _sh(AT, V1, 0x212), JR_RA, NOP]
SND_S = ENG + 0x1C0; SND_TBL = ENG + 0x1E0          # provvisori: la lunghezza del codice non dipende da questi valori
_n = len(_snd_hook()) * 4
SND_S = ENG + ((_n + 0x1F) & ~0xF)          # scratch (32 byte) subito dopo il codice
SND_TBL = (SND_S + 0x20 + 0xFF) & ~0xFF      # tabella eventi, 8 byte per evento, id 0 = fine
assert SND_TBL + 16 <= TBL_END
SND_MAXEV = (TBL_END - SND_TBL) // 8 - 1
def _old_snd():
    """versione precedente (traduttore nei due dispatcher): riconosciuta come 'originale' e sostituita"""
    SC, SW = 0x739E10, 0x739ED0
    T = SC + 0x44
    def tr(c):
        H_, E_ = c + 10 * 4, c + 15 * 4
        w = [addiu(V1, V0, -0x6C), _sltiu(AT, V1, 12), _beq(c + 8, H_, AT, ZERO), _lui(AT, 0x74), daddu(AT, AT, V1),
             _lbu(AT, AT, (T - 0x740000) & 0xFFFF), _beq(c + 24, H_, AT, ZERO), NOP, b_to(c + 32, E_), daddu(V0, AT, ZERO),
             addiu(V1, V0, -0x132), _sltiu(AT, V1, 2), _beq(c + 48, E_, AT, ZERO), _sll(V1, V1, 1), addiu(V0, V1, 0x346),
             JR_RA, NOP]
        return w
    tab = bytes([0, 0x65, 0x66, 0x67, 0x83, 0x84, 0x8E, 0x8F, 0, 0x89, 0x89, 0x89])
    w = [daddu(S0, A0, ZERO), jal(SC), daddu(V0, V1, ZERO), daddu(V1, V0, ZERO), j(0x56B65C), addiu(V0, ZERO, 0x26C),
         jal(SC), lhu(V0, S0, 0x212), j(0x56BB88), NOP,
         daddu(S0, A0, ZERO), jal(SC), NOP, j(0x57044C), addiu(V1, ZERO, 0x26C),
         jal(SC), lhu(V0, S0, 0x212), j(0x570978), NOP]
    return words(tr(SC)) + tab, words(w)
_V1_Z1 = bytes.fromhex("94ff43240c00612c0b0020100200a12c01002138000901002d0823007400033c2d082300649e219003002010000000000800e0032d102000cefe43240200612c0200201040180300460362240800e003000000000065666783848e8f008989890000000000656667000065660065666700000000")   # versioni precedenti
_V1_Z2 = bytes.fromhex("f0ffbd270000bfffe90c85907400013c409f24acf2018294449f22a484e71c0c00000000f20182a4120282947400013c469f22a484e71c0c00000000120282a4ff000324ffa915087400013c409f238c449f2194f20161a47400013c469f2194120261a40800e003")
_V2_Z1 = bytes.fromhex("94ff43240c00612c060020107400013c2d0823003c9e219002002010000000002d1020000800e003000000000065666783848e8f008989897400013c489f238c4c9f2194f20161a47400013c4e9f2194120261a40800e00300000000000000000000000000000000000000000000000000000000")
_V2_Z2 = bytes.fromhex("f0ffbd270000bfff7400013c489f24acf20182944c9f22a484e71c0c00000000f20182a4120282947400013c4e9f22a484e71c0c00000000120282a47400013c4c9f2394f2018294060043144e9f2394120282940300431400000000ffa91508ff00032490ad150c000000003eaa150800000000")
_SND = []
_hb = words(_snd_hook())
_new1 = (words(_snd_tr()) + SND_TAB + words(_snd_rest())).ljust(116, b"\0")
assert SND_C + 0x38 + 36 <= 0x739E90
_o1, _o2 = _old_snd()
_SND.append((SND_C, _new1, b"\0" * 116, (_o1.ljust(116, b"\0"), _V1_Z1, _V2_Z1)))
_SND.append((SND_OLDH, b"\0" * 116, b"\0" * 116, (_o2.ljust(116, b"\0"), _V1_Z2.ljust(116, b"\0"), _V2_Z2)))
_SND.append((ENG, _hb, b"\0" * len(_hb)))
_SND.append((0x56A7F0, words([j(ENG)]), words([addiu(SP, SP, -0x10)]), (words([j(0x739ED0)]),)))
_SND.append((0x56A8FC, words([j(SND_R)]), words([JR_RA]), (words([j(0x739F18)]),)))
_SND_OLD_SITES = [(0x56B654, daddu(S0, A0, ZERO), j(0x739ED0)), (0x56BB84, lhu(V0, S0, 0x212), j(0x739ED0 + 24)),
                  (0x570444, daddu(S0, A0, ZERO), j(0x739ED0 + 40)), (0x570974, lhu(V0, S0, 0x212), j(0x739ED0 + 60)),
                  (0x56B760, b_to(0x56B760, 0x56BB88), b_to(0x56B760, 0x56BB84)),
                  (0x570568, b_to(0x570568, 0x570978), b_to(0x570568, 0x570974))]
for _a, _orig, _alt in _SND_OLD_SITES:
    _SND.append((_a, words([_orig]), words([_orig]), (words([_alt]),)))     # ripara le versioni precedenti
GROUPS.append(("pl_suoni",
    "Suoni delle animazioni del personaggio",
    "Fa suonare passi e respiro agli ID 0x6C-0x77 con qualunque valore di CE9 e abilita la tabella eventi di suoni.txt (zona 0x72A540-0x72AD8F).",
    _SND))

# ---- tabella eventi da suoni.txt --------------------------------------------------------------------
# riga: ID  fotogramma  evento [argomenti]      (# = commento; fotogramma = numero del fotogramma, parte da 0)
EVENTI = {   # nome: (tipo 0=passo 1=voce, a2 = quante varianti, a3 = ID base)
    "passo": (0, 0, 0), "trascino": (0, 3, 0),
    "fiato_corsa": (1, 2, 8), "fiato_ferito": (1, 2, 0xA),
    "hurt": (1, 2, 1), "hurt_bad": (1, 0, 5), "pianta": (1, 0, 0x18), "tosse": (1, 0, 0x19),
    "sforzo": (1, 0, 0x10),     # segnaposto: voce 0x10
}
def parse_suoni(text):
    """ritorna (bytes_tabella, [messaggi]); lancia ValueError con la riga sbagliata"""
    ev = []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.split("#")[0].strip()
        if not line: continue
        p = line.split()
        try:
            if len(p) < 3: raise ValueError("servono ID, fotogramma ed evento")
            i, fr = int(p[0], 0), int(p[1], 0)
            nome = p[2].lower()
            if nome == "voce":
                if len(p) < 4: raise ValueError("'voce' vuole l'ID della voce (e, facoltativo, quante varianti)")
                ev_t = (1, int(p[4], 0) if len(p) > 4 else 0, int(p[3], 0))
            elif nome in EVENTI: ev_t = EVENTI[nome]
            else: raise ValueError("evento sconosciuto '%s' (nomi: %s, voce N [varianti])" % (nome, ", ".join(EVENTI)))
            if not (1 <= i <= 0xFFFF and 0 <= fr <= 0xFFFF): raise ValueError("ID o fotogramma fuori campo")
        except ValueError as ex:
            raise ValueError("suoni.txt riga %d: %s" % (n, ex))
        ev.append((i, fr) + ev_t)
    if len(ev) > SND_MAXEV: raise ValueError("troppi eventi: %d (massimo %d)" % (len(ev), SND_MAXEV))
    tab = b"".join(struct.pack("<HHBBBB", i, fr, t, a2, a3, 0) for i, fr, t, a2, a3 in ev)
    return tab, ["%d eventi scritti nella tabella" % len(ev)]
def write_suoni(buf, text):
    """scrive la tabella eventi nel 2.DAT (serve il gruppo pl_suoni applicato)"""
    if state(buf, "pl_suoni") != "applied":
        raise ValueError("Applica prima il gruppo 'Suoni delle animazioni del personaggio'.")
    tab, msgs = parse_suoni(text)
    out = bytearray(buf)
    o = SND_TBL - BASE; n = TBL_END - SND_TBL
    out[o:o + n] = (tab + b"\0" * 8).ljust(n, b"\0")
    return out, msgs
EXCLUSIVE = [("pl_custom", "caution"), ("pl_custom", "danger")]

GROUP_IDS = [g[0] for g in GROUPS]
def group(gid):
    for g in GROUPS:
        if g[0] == gid: return g
    raise KeyError(gid)

# ---------------------------------------------------------------- logica
def _slice(buf, addr, n):
    o = addr - BASE
    return None if o < 0 or o + n > len(buf) else bytes(buf[o:o + n])

def state(buf, gid):
    """'orig' | 'applied' | 'partial' (alcuni byte gia' a posto) | 'conflict' | 'bad'"""
    ps = group(gid)[3]
    n_o = n_a = 0
    for p in ps:
        a, new, old = p[:3]; alts = p[3] if len(p) > 3 else ()
        cur = _slice(buf, a, len(new))
        if cur is None: return "bad"
        if new == old and cur == new: continue          # patch neutra (serve solo a riparare i valori in 'alts')
        if cur == new: n_a += 1
        elif cur == old or cur in alts: n_o += 1
        else: return "conflict"
    if n_a == 0: return "orig"
    if n_o == 0: return "applied"
    return "partial"

def check_file(buf):
    if len(buf) < 0x200000 or buf[:4] != b"MWo3": return "Non sembra un 2.DAT di Outbreak File 2 (intestazione MWo3 assente o file troppo corto)."
    return None

def apply(buf, want):
    """want = {gid: True/False}. Ritorna (bytearray, [messaggi]); lancia ValueError se qualcosa e' in conflitto."""
    for a, b in EXCLUSIVE:
        if want.get(a) and want.get(b):
            raise ValueError("I gruppi '%s' e '%s' sono esclusivi: scrivono sulle stesse righe. Scegline uno." % (a, b))
    out = bytearray(buf); msgs = []; bad = []
    for gid, on in want.items():
        st = state(out, gid)
        title = group(gid)[1]
        if st in ("conflict", "bad"):
            if on: bad.append(title)
            else: msgs.append("non toccato (byte diversi, es. scritti da un gruppo esclusivo): " + title)
            continue
        if on and st in ("orig", "partial"):
            for p in group(gid)[3]: out[p[0] - BASE:p[0] - BASE + len(p[1])] = p[1]
            msgs.append("applicato: " + title)
        elif (not on) and st in ("applied", "partial"):
            for p in group(gid)[3]: out[p[0] - BASE:p[0] - BASE + len(p[2])] = p[2]
            msgs.append("tolto: " + title)
        else:
            msgs.append(("gia' applicato: " if st == "applied" else "invariato: ") + title)
    if bad: raise ValueError("Byte diversi dall'originale (altra versione o gia' modificati da altro):\n - " + "\n - ".join(bad))
    return out, msgs

def pnach_text(gids):
    L = ["// REOB patcher - gruppi: " + ", ".join(gids)]
    for gid in gids:
        L.append("// " + group(gid)[1])
        for a, new, old in [p[:3] for p in group(gid)[3]]:
            if len(new) % 4 == 0:
                for i in range(0, len(new), 4):
                    L.append("patch=1,EE,%08X,word,%08X" % (a + i, struct.unpack_from("<I", new, i)[0]))
            else:
                for i in range(0, len(new), 2):
                    L.append("patch=1,EE,%08X,short,%04X" % (a + i, struct.unpack_from("<H", new, i)[0]))
    return "\n".join(L) + "\n"

STATE_TXT = {"orig": "originale", "applied": "gia' applicata", "partial": "parziale (alcuni byte gia' applicati)", "conflict": "IN CONFLITTO (byte diversi)", "bad": "file troppo corto"}

# ---------------------------------------------------------------- riga di comando
def cli(args):
    if args and args[0] == "--list":
        for g in GROUPS: print("%-18s %s" % (g[0], g[1]))
        return 0
    if args and args[0] == "--suoni":          # --cli --suoni in.DAT suoni.txt out.DAT
        if len(args) < 4: print(__doc__); return 1
        try: out, msgs = write_suoni(open(args[1], "rb").read(), open(args[2], encoding="utf-8").read())
        except ValueError as ex: print(ex); return 1
        open(args[3], "wb").write(out); print("\n".join(msgs)); print("salvato:", args[3]); return 0
    if len(args) < 3:
        print(__doc__); return 1
    src, dst, ids = args[0], args[1], args[2:]
    buf = open(src, "rb").read()
    e = check_file(buf)
    if e: print(e); return 1
    if ids == ["tutto"]: ids = GROUP_IDS
    for i in ids:
        if i not in GROUP_IDS: print("gruppo sconosciuto:", i); return 1
    want = {g: (g in ids) for g in GROUP_IDS if g in ids}
    try: out, msgs = apply(buf, want)
    except ValueError as ex: print(ex); return 1
    open(dst, "wb").write(out); print("\n".join(msgs)); print("salvato:", dst); return 0

# ---------------------------------------------------------------- finestra
def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext
    root = tk.Tk(); root.title("REOB patcher - Outbreak File 2 (2.DAT)")
    root.geometry("760x640")
    st = {"buf": None, "path": None, "suoni": None}
    pathvar = tk.StringVar(value="(nessun file)")
    suonivar = tk.StringVar(value="(nessun suoni.txt: la tabella eventi resta com'e')")
    vars_ = {g[0]: tk.BooleanVar(value=False) for g in GROUPS}
    stlab = {}

    def log(t):
        logbox.configure(state="normal"); logbox.insert("end", t + "\n"); logbox.see("end"); logbox.configure(state="disabled")

    def refresh():
        for gid in GROUP_IDS:
            if st["buf"] is None: stlab[gid].config(text="", fg="black"); continue
            s = state(st["buf"], gid)
            other = [b if a == gid else a for a, b in EXCLUSIVE if gid in (a, b)]
            if s == "conflict" and any(state(st["buf"], o) == "applied" for o in other):
                stlab[gid].config(text="non usato: c'e' il gruppo esclusivo applicato", fg="#555"); continue
            stlab[gid].config(text=STATE_TXT[s], fg={"orig": "#555", "applied": "#0a7a0a", "partial": "#b36b00", "conflict": "#c00000", "bad": "#c00000"}[s])

    def openf():
        p = filedialog.askopenfilename(title="Scegli il 2.DAT", filetypes=[("DAT", "*.DAT *.dat"), ("Tutti", "*.*")])
        if not p: return
        buf = open(p, "rb").read(); e = check_file(buf)
        if e: messagebox.showerror("File non valido", e); return
        st["buf"], st["path"] = buf, p
        pathvar.set(p)
        for gid in GROUP_IDS: vars_[gid].set(state(buf, gid) in ("applied", "partial"))
        refresh(); log("Aperto: %s (%d byte)" % (p, len(buf)))

    def pick_suoni():
        p = filedialog.askopenfilename(title="Scegli suoni.txt", filetypes=[("Testo", "*.txt"), ("Tutti", "*.*")])
        if not p: return
        try: _, m = parse_suoni(open(p, encoding="utf-8").read())
        except ValueError as ex: messagebox.showerror("suoni.txt", str(ex)); return
        st["suoni"] = p; suonivar.set(p); log("suoni.txt: " + m[0])

    def wanted(): return {gid: vars_[gid].get() for gid in GROUP_IDS}

    def save():
        if st["buf"] is None: messagebox.showinfo("Manca il file", "Apri prima un 2.DAT."); return
        try:
            out, msgs = apply(st["buf"], wanted())
            if st["suoni"]:
                out, m2 = write_suoni(out, open(st["suoni"], encoding="utf-8").read()); msgs += m2
        except ValueError as ex: messagebox.showerror("Conflitto", str(ex)); return
        base = os.path.splitext(os.path.basename(st["path"]))[0]
        p = filedialog.asksaveasfilename(title="Salva il 2.DAT patchato", initialfile=base + "_patched.DAT", defaultextension=".DAT")
        if not p: return
        if os.path.abspath(p) == os.path.abspath(st["path"]) and not messagebox.askyesno("Sovrascrivere?", "Stai per sovrascrivere il file originale. Continuare?"): return
        open(p, "wb").write(out)
        for m in msgs: log(m)
        log("Salvato: " + p)
        st["buf"], st["path"] = bytes(out), p; pathvar.set(p); refresh()

    def pnach():
        ids = [g for g in GROUP_IDS if vars_[g].get()]
        if not ids: messagebox.showinfo("Niente da esportare", "Spunta almeno un gruppo."); return
        p = filedialog.asksaveasfilename(title="Salva .pnach", defaultextension=".pnach", initialfile="reob_patch.pnach")
        if not p: return
        open(p, "w").write(pnach_text(ids)); log("Esportato .pnach: " + p)

    top = tk.Frame(root); top.pack(fill="x", padx=10, pady=8)
    tk.Button(top, text="Apri 2.DAT...", command=openf).pack(side="left")
    tk.Label(top, textvariable=pathvar, anchor="w").pack(side="left", padx=10, fill="x", expand=True)

    sf = tk.Frame(root); sf.pack(fill="x", padx=10)
    tk.Button(sf, text="Tabella suoni (suoni.txt)...", command=pick_suoni).pack(side="left")
    tk.Label(sf, textvariable=suonivar, anchor="w", fg="#444").pack(side="left", padx=10)
    box = tk.Frame(root); box.pack(fill="both", expand=False, padx=10)
    for gid, title, desc, ps in GROUPS:
        f = tk.Frame(box, bd=1, relief="groove"); f.pack(fill="x", pady=3)
        r1 = tk.Frame(f); r1.pack(fill="x")
        tk.Checkbutton(r1, text=title, variable=vars_[gid], font=("TkDefaultFont", 10, "bold")).pack(side="left")
        stlab[gid] = tk.Label(r1, text=""); stlab[gid].pack(side="right", padx=8)
        tk.Label(f, text=desc, justify="left", wraplength=700, fg="#444").pack(anchor="w", padx=24, pady=(0, 4))

    bt = tk.Frame(root); bt.pack(fill="x", padx=10, pady=8)
    tk.Button(bt, text="Applica e salva nuovo 2.DAT...", command=save).pack(side="left")
    tk.Button(bt, text="Esporta .pnach (gruppi spuntati)...", command=pnach).pack(side="left", padx=8)
    tk.Label(root, text="Una casella spuntata = patch presente nel file di uscita; tolta = patch rimossa (se c'era).", fg="#555").pack(anchor="w", padx=10)
    logbox = scrolledtext.ScrolledText(root, height=8, state="disabled"); logbox.pack(fill="both", expand=True, padx=10, pady=8)
    root.mainloop()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("--cli", "--list"):
        sys.exit(cli(sys.argv[2:] if sys.argv[1] == "--cli" else ["--list"]))
    gui()
