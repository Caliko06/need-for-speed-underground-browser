#!/usr/bin/env python3
"""census/systems.tsv: one row per function of pc/Speed.exe: addr, system, confidence, how, evidence.

Re-run:  .venv/bin/python tools/census/systems.py [--sample N --seed S]
Read-only on the game; writes only census/systems.tsv (and prints counts). ~1 min, no Hopper needed.
Method (docs/re/systems_method.md): evidence per function from (1) strings and string tables it references,
(2) import call sites, (3) addresses named in docs / patches / q_*.py, then (4) call-graph, function-pointer, shared
global and address-neighbour propagation with a confidence that decays; seeds are never overridden by propagation.
Rules live in tools/census/sys_rules.py. Inputs: pc/Speed.exe, census/hopper/{funcs.tsv,decomp.c},
census/ghidra/decomp_*.c, census/imports_sites.tsv, build/gen/f*.c (only for the lifted list), docs/, tools/hopper/q_*.py."""
import bisect, collections, glob, json, math, os, random, re, struct, sys
import pefile, capstone
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sys_rules as RU

SYSTEMS = ['canon', 'track', 'traffic', 'rivals', 'car', 'camera', 'render', 'hud', 'audio', 'assets', 'props', 'input',
           'runtime', 'online', 'unknown']
BASE, TEXT_END, DATA_LO, DATA_HI = 0x400000, 0x696ea8, 0x697000, 0x795000
CRT_LO, CRT_HI = 0x672000, 0x6830a0   # MSVC CRT proper; the import thunks start at 0x6830aa
H = lambda a: '0x%06x' % a


# ---------------------------------------------------------------- inputs
def load_funcs():
    starts, names = [], {}
    for l in open(R + '/census/hopper/funcs.tsv').read().split('\n')[1:]:
        if l:
            f = l.split('\t'); a = int(f[0], 16); starts.append(a); names[a] = f[1]
    hopper = set(starts)
    lifted = set()
    for fn in glob.glob(R + '/build/gen/f*.c') + [R + '/build/gen/abk.c']:
        if os.path.exists(fn):
            lifted.update(int(m, 16) for m in re.findall(r'^[a-z_0-9 ]+ f_([0-9a-f]{6})\(', open(fn, errors='replace').read(), re.M))
    if not lifted: lifted = set(hopper)
    starts = sorted(hopper | lifted)   # the lifter also starts functions Hopper folds into a neighbour (jump-table cases, data seeds)
    return starts, names, lifted, hopper


def sweep(img, starts):
    """Capstone linear sweep per function range: data refs (imm/disp in .rdata/.data), direct calls, jumps, code pointers."""
    cs = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32); cs.detail = True
    sset = set(starts); out = {}
    for i, a in enumerate(starts):
        e = min(starts[i + 1] if i + 1 < len(starts) else TEXT_END, TEXT_END)
        code = img[a - BASE:e - BASE + 15]; off = 0; over = False
        refs, calls, jmps, cptr = set(), set(), set(), set()
        n = x87 = ind = 0
        while off < e - a:
            got = False
            for ins in cs.disasm(code[off:], a + off):
                if ins.address >= e: off = e - a; break
                got = True; off = ins.address + ins.size - a; n += 1; m = ins.mnemonic
                if off > e - a: over = True
                if m[0] == 'f' and m != 'fs': x87 += 1
                if m == 'call' or m == 'jmp' or m[0] == 'j':
                    o = ins.operands
                    if o and o[0].type == X86_OP_IMM:
                        (calls if m == 'call' else jmps).add(o[0].imm & 0xffffffff)
                    elif m == 'call': ind += 1
                    continue
                for o in ins.operands:
                    v = (o.imm if o.type == X86_OP_IMM else o.mem.disp if o.type == X86_OP_MEM else None)
                    if v is None: continue
                    v &= 0xffffffff
                    if DATA_LO <= v < DATA_HI: refs.add(v)
                    elif v in sset and v != a: cptr.add(v)
            if off < e - a and not got: off += 1
        out[a] = dict(over=over, end=e, n=n, x87=x87, ind=ind, refs=refs, calls=calls, jmps={j for j in jmps if j in sset and j != a}, cptr=cptr)
    return out


def hopper_graph(starts):
    """callers/callees from the Hopper export (census/hopper/decomp.c) and the literal strings of both decompilers."""
    sset = set(starts); callers = collections.defaultdict(set); callees = collections.defaultdict(set)
    strs = collections.defaultdict(set); body = {}
    hdr = re.compile(r'^// ([0-9a-f]{8}) (\S+)$'); lit = re.compile(r'"((?:[^"\\]|\\.)*)"')
    cur = None
    def cont(a):
        i = bisect.bisect_right(starts, a) - 1
        return starts[i] if i >= 0 else None
    for line in open(R + '/census/hopper/decomp.c', errors='replace'):
        m = hdr.match(line)
        if m: cur = int(m.group(1), 16); body[cur] = []; continue
        if cur is None: continue
        if line.startswith('// callers:'):
            for x in line[11:].split(): callers[cur].add(cont(int(x.rstrip('?'), 16)))
        elif line.startswith('// callees:'):
            for x in line[11:].split():
                v = int(x.rstrip('?'), 16)
                if v in sset: callees[cur].add(v)
        else:
            body[cur].append(line)
            for s in lit.findall(line): strs[cur].add(s)
    gh = re.compile(r'^// ([0-9a-f]{8}) FUN_'); cur = None
    for fn in sorted(glob.glob(R + '/census/ghidra/decomp_*.c')):
        for line in open(fn, errors='replace'):
            m = gh.match(line)
            if m: cur = int(m.group(1), 16); continue
            if cur is not None and '"' in line:
                for s in lit.findall(line): strs[cur].add(s)
    return callers, callees, strs


def cont_factory(starts):
    def cont(a):
        if a < starts[0] or a >= TEXT_END: return None
        return starts[bisect.bisect_right(starts, a) - 1]
    return cont


# ---------------------------------------------------------------- evidence
class Ev:
    """evidence[f] = list of (system, weight, how, text)"""
    def __init__(self): self.d = collections.defaultdict(list)
    def add(self, f, s, w, how, text):
        # the statically linked MSVC CRT (file I/O, math, locale) is runtime whatever API or string it touches;
        # only a doc/q_/patch line that names the function itself can say otherwise
        if CRT_LO <= f < CRT_HI and how in ('string', 'strtab', 'import') and s != 'runtime': s, text = 'runtime', 'CRT band: ' + text
        self.d[f].append((s, w, how, text))


def classify_string(s, addr=None):
    for sysm, w, rx in RU.STRING_RULES:
        if rx.search(s): return sysm, w
    if addr is not None:                      # no word of its own: the library whose string pool it sits in
        for lo, hi, sysm in RU.BANDS:
            if lo <= addr < hi: return sysm, 2
    return None


def pe_strings(img):
    out = {}
    for m in re.finditer(rb'(?<![\x20-\x7e])[\x20-\x7e]{4,}(?=\0)', img):
        s = m.group().decode()
        if sum(c.isalpha() for c in s) >= 3 and m.start() >= DATA_LO - BASE: out[m.start() + BASE] = s
    return out


def string_evidence(ev, img, starts, sw, hstrs):
    strs = pe_strings(img)
    cls = {a: classify_string(s, a) for a, s in strs.items()}
    # unclassified strings take the system of the classified strings around them in the pool (same object file)
    addrs = sorted(strs); pool = {}
    for i, a in enumerate(addrs):
        if cls[a] is None:
            near = [cls[addrs[j]] for j in (i - 2, i - 1, i + 1, i + 2) if 0 <= j < len(addrs) and abs(addrs[j] - a) < 160 and cls[addrs[j]]]
            c = collections.Counter(n[0] for n in near)
            if c and c.most_common(1)[0][1] >= 2 and c.most_common(1)[0][0] not in ('runtime',): pool[a] = (c.most_common(1)[0][0], 1)
    cls = {a: (cls[a] or pool.get(a)) for a in strs}
    # pointer tables: runs of dwords in .data/.rdata that point at strings
    sa = set(strs); tabs = []; cur = []
    for off in range(DATA_LO - BASE, min(len(img), DATA_HI - BASE) - 3, 4):
        v = struct.unpack_from('<I', img, off)[0]
        if v in sa: cur.append((off + BASE, v))
        else:
            if len(cur) >= 3: tabs.append(cur)
            cur = []
    if len(cur) >= 3: tabs.append(cur)
    users = collections.Counter()
    for f, v in sw.items():
        for r in v['refs']:
            if r in sa: users[r] += 1
    for f, v in sw.items():
        seen = set()
        for r in v['refs']:
            c = cls.get(r) if r in sa else None
            if c and r not in seen:
                seen.add(r); w = c[1] * min(1.0, 3.0 / max(1, users[r]))
                ev.add(f, c[0], w, 'string', '%s@%s' % (strs[r][:40], H(r)))
        for t in tabs:
            lo, hi = t[0][0], t[-1][0] + 4
            if any(lo <= r < hi for r in v['refs']):
                votes = collections.Counter(cls[s][0] for _, s in t if cls.get(s))
                if votes:
                    sysm, k = votes.most_common(1)[0]
                    if k >= max(2, 0.5 * len(t)):
                        ev.add(f, sysm, 1.5, 'strtab', '%d/%d strings (%s...) in table %s' % (k, len(t), strs[t[0][1]][:24], H(lo)))
    # literal strings seen in the decompilers but not found above (inline literals with other addresses)
    for f, ss in hstrs.items():
        if f in sw and not any(e[2] == 'string' for e in ev.d.get(f, [])):
            for s in ss:
                c = classify_string(s)
                if c: ev.add(f, c[0], c[1] * 0.8, 'string', '"%s" (decompile)' % s[:40])


def import_evidence(ev, cont):
    path = R + '/census/imports_sites.tsv'
    seen = set()
    for l in open(path):
        if l.startswith('#') or l.startswith('site_address'): continue
        f = l.rstrip('\n').split('\t')
        imp = f[2]
        for fn in {int(x, 16) for x in f[1].split(';')}:   # a shared tail lists every owner
            if (fn, imp) in seen: continue
            seen.add((fn, imp))
            for sysm, rx in RU.IMPORT_RULES:
                if rx.search(imp):
                    w = 3 if sysm in ('render', 'input', 'audio', 'online') else 1.5 if sysm == 'assets' else 0.4
                    ev.add(fn, sysm, w, 'import', imp); break


def doc_evidence(ev, sw, starts, cont, strs_by_addr):
    """addresses written in docs, patches.py comments and q_*.py: the function containing a code address, or the
    functions that reference a data address."""
    dref = collections.defaultdict(list)
    for f, v in sw.items():
        for r in v['refs']: dref[r].append(f)
    def funcs_of(a):
        if BASE <= a < TEXT_END:
            c = cont(a); return [c] if c else []
        return [f for f in dref.get(a, [])] if len(dref.get(a, [])) <= 6 else []
    pat = re.compile(r'(?:0x|sub_|f_)([0-9a-f]{6})\b')
    prose = lambda txt: [(s, len(rx.findall(txt))) for s, rx in RU.PROSE if rx.search(txt)]
    cnt = 0
    def prose_pick(txt):
        c = prose(txt.lower())
        if not c: return None
        c.sort(key=lambda x: -x[1]); return c[0][0] if len(c) == 1 or c[0][1] > c[1][1] else None
    for rel, fixed in RU.DOC_SYSTEM.items():
        p = R + '/' + rel
        if not os.path.exists(p): continue
        for ln, line in enumerate(open(p, errors='replace'), 1):
            addrs = {int(x, 16) for x in pat.findall(line)}
            if not addrs: continue
            if not fixed and len(addrs) > 3: continue      # a table row of many addresses in a mixed doc: the words do not fit each one
            sysm = fixed or prose_pick(line)
            if not sysm: continue
            if fixed and prose_pick(line) in ('hud', 'audio', 'camera', 'input', 'online') and prose_pick(line) != fixed: sysm = prose_pick(line)
            for a in addrs:
                for f in funcs_of(a):
                    ev.add(f, sysm, 3 if fixed else 1.5, 'doc', '%s:%d names %s' % (rel.replace('docs/', ''), ln, H(a))); cnt += 1
    # patches.py comment blocks: first address of a block, text classified by prose keywords
    txt = open(R + '/tools/recomp/patches.py').read().split('\n'); blocks = []; cur = []
    for l in txt:
        if re.match(r'\s*# PATCH', l): cur = [l]; blocks.append(cur)
        elif cur and re.match(r'\s*#', l): cur.append(l)
        else: cur = []
    for b in blocks:
        t = ' '.join(x.strip('# ') for x in b)
        t = re.sub(r'\((?:\+ ?)?(?:caves?|mask|data|weight|constant|0x57cfc7)[^)]*\)', ' ', t)  # caves are padding inside other functions
        sysm = RU.PATCH_SYSTEM.get(int(pat.findall(t)[0], 16)) if pat.findall(t) else None
        if not sysm: sysm = prose_pick(t)
        if not sysm: continue
        head = re.split(r'[A-Za-z]{3,}', t.split('PATCH:', 1)[1], 1)[0]   # only the addresses of the PATCH line itself
        for a in {int(x, 16) for x in pat.findall(head)}:
            for f in funcs_of(a): ev.add(f, sysm, 3, 'patch', 'patches.py PATCH %s (%s)' % (pat.findall(t)[0], H(a)))
    # q_*.py: ADDRS and DATA lists are the functions a question was about
    qs = [(os.path.basename(p)[:-3], open(p, errors='replace').read()) for p in sorted(glob.glob(R + '/tools/hopper/q_*.py'))]
    for t, s in json.load(open(R + '/tools/hopper/queries.json')).items():   # the topics mkq.py renders for hpar.sh
        qs.append(('q_' + t, 'ADDRS = [%s]\nDATA = [%s]' % (', '.join(s.get('addrs', [])), ', '.join(s.get('data', [])))))
    for topic, t in qs:
        sysm = next((s for rx, s in RU.Q_SYSTEM if re.match(rx + r'\b', topic) or re.match(rx, topic)), None)
        if not sysm: continue
        m = re.findall(r'^(?:ADDRS|DATA) = \[([^\]]*)\]', t, re.M)
        for blob in m:
            for a in {int(x, 16) for x in re.findall(r'0x([0-9a-f]+)', blob)}:
                for f in funcs_of(a): ev.add(f, sysm, 2, 'qfile', '%s.py asks about %s' % (topic, H(a)))


# ---------------------------------------------------------------- arbitration and propagation
def arbitrate(items):
    """-> (system, conf, how, evidence text, strength) from a list of (system, w, how, text)"""
    tot = collections.Counter()
    for s, w, h, t in items: tot[s] += w
    top, sc = tot.most_common(1)[0]
    share = sc / sum(tot.values())
    if sc >= 3 and share >= 0.6: conf, st = 'high', 1.0
    elif sc >= 1.4 and share >= 0.5: conf, st = 'med', 0.7
    else: conf, st = 'low', 0.4
    mine = sorted((i for i in items if i[0] == top), key=lambda i: -i[1])
    hows = sorted({i[2] for i in mine}, key=lambda h: ['string', 'strtab', 'import', 'patch', 'doc', 'qfile'].index(h))
    txt = '; '.join('%s' % i[3] for i in mine[:3])
    if len(mine) > 3: txt += '; +%d more' % (len(mine) - 3)
    if share < 1: txt += ' [vs ' + ','.join('%s %.1f' % (s, w) for s, w in tot.most_common(3)[1:]) + ']'
    return top, conf, '+'.join(hows), txt, st


def propagate(starts, label, callers, callees, sw, vt_edges, eh_parent, funclets=frozenset()):
    """label: f -> dict(system, conf, how, text, st). Adds propagated labels in rounds. Votes: callers (1/sqrt n),
    callees (0.5), function-pointer table peers and pieces of one function (0.5 / 1.5), exception-unwind funclets and their
    owner (2.0), and the nearest tagged functions in link order (0.6 decaying with distance)."""
    ncall = {f: len(callers.get(f, ())) for f in starts}
    pos = {f: i for i, f in enumerate(starts)}
    SEEDS = ('string', 'strtab', 'import', 'patch', 'doc', 'qfile')
    for rnd in range(1, 9):
        new = {}
        seedidx = [pos[f] for f in starts if f in label and label[f]['conf'] in ('high', 'med') and label[f]['how'].split('+')[0] in SEEDS]
        for f in starts:
            if f in label: continue
            votes = collections.defaultdict(float); why = collections.defaultdict(list); wsum = 0.0
            def add(g, w, kind):
                nonlocal wsum
                if kind in ('caller', 'callee', 'fnptr'): w *= max(0.25, 1.0 / (1.0 + abs(g - f) / 0x20000))   # modules are contiguous: far edges are API use
                s = label[g]['system']; votes[s] += w; wsum += w; why[s].append((w, kind, g))
            for g in callers.get(f, ()):
                if g in label and g != f: add(g, label[g]['st'] / math.sqrt(max(1, ncall[f])), 'caller')
            for g in callees.get(f, ()):
                if g in label and g != f: add(g, 0.5 * label[g]['st'], 'callee')
            for g, k in vt_edges.get(f, ()):
                if g in label and g != f: add(g, (1.5 if k == 'frag' else 0.5) * label[g]['st'], 'piece' if k == 'frag' else 'fnptr')
            for g in eh_parent.get(f, ()):
                if g in label: add(g, 2.0 * label[g]['st'], 'unwind-owner')
            if CRT_LO <= f < CRT_HI:                     # link-order prior: this band is the CRT
                votes['runtime'] += 2.0; wsum += 2.0; why['runtime'].append((2.0, 'crt-band', f))
            if f not in funclets:
                k = bisect.bisect_left(seedidx, pos[f])
                for j2 in (k - 2, k - 1, k, k + 1):
                    if 0 <= j2 < len(seedidx):
                        g = starts[seedidx[j2]]; d = abs(seedidx[j2] - pos[f])
                        if g != f and d <= 10: add(g, 1.0 * label[g]['st'] / (1 + d / 3.0), 'near(%d)' % d)
            if not votes: continue
            csys = {label[g]['system'] for g in callers.get(f, ()) if g in label and label[g]['conf'] in ('high', 'med')}
            if f not in funclets and ncall[f] >= 3 and len(csys) >= 3 and 'runtime' not in csys:
                new[f] = dict(system='runtime', conf='low', how='hub', st=0.35,
                              text='called from %d systems (%s)' % (len(csys), ','.join(sorted(csys))[:60])); continue
            top = max(votes, key=votes.get); tv = votes[top]; share = tv / wsum
            if tv < 0.45 or share < 0.55: continue
            st = min(0.65, 0.8 * share * min(1.0, tv / 0.6))
            ws = sorted(why[top], reverse=True)[:3]
            new[f] = dict(system=top, conf='med' if (tv >= 0.9 and share >= 0.7 and rnd <= 2 and sw[f]['n'] > 8) else 'low', how='graph%d' % rnd, st=st,
                          text='round %d, %.0f%% of %.1f: %s' % (rnd, 100 * share, wsum, ', '.join('%s %s' % (kd, H(g)) for _, kd, g in ws)))
        if not new: break
        label.update(new)
    return label


def eh_owners(img, starts, sw):
    """MSVC exception-unwind code at the end of .text: `mov eax, FuncInfo; jmp __CxxFrameHandler` thunks, referenced by the
    function that owns them, and the cleanup/catch funclets named by the FuncInfo unwind and try tables.
    Returns funclet/thunk -> [owner function]."""
    sset = set(starts); u32 = lambda a: struct.unpack_from('<I', img, a - BASE)[0] if 0 <= a - BASE <= len(img) - 4 else 0
    thunks = {}
    for f in starts:
        b = img[f - BASE:f - BASE + 10]
        if len(b) == 10 and b[0] == 0xb8 and b[5] == 0xe9:
            thunks[f] = (struct.unpack_from('<I', b, 1)[0], (f + 10 + struct.unpack_from('<i', b, 6)[0]) & 0xffffffff)
    if not thunks: return {}
    handler = collections.Counter(h for _, h in thunks.values()).most_common(1)[0][0]
    thunks = {f: fi for f, (fi, h) in thunks.items() if h == handler and u32(fi) in (0x19930520, 0x19930521, 0x19930522)}
    users = collections.defaultdict(set)
    for f in starts:
        for c in sw[f]['cptr']: users[c].add(f)
    out = collections.defaultdict(list)
    for t, fi in thunks.items():
        own = [o for o in users.get(t, ()) if o not in thunks]
        if not own: continue
        out[t] = own
        n, um, ntry, tm = u32(fi + 4), u32(fi + 8), u32(fi + 12), u32(fi + 16)
        acts = set()
        if 0 < n < 200 and DATA_LO <= um < DATA_HI:
            acts.update(u32(um + 8 * k + 4) for k in range(n))
        if 0 < ntry < 50 and DATA_LO <= tm < DATA_HI:
            for k in range(ntry):
                nc, ha = u32(tm + 20 * k + 12), u32(tm + 20 * k + 16)
                if 0 < nc < 20 and DATA_LO <= ha < DATA_HI:
                    acts.update(u32(ha + 16 * c + 12) for c in range(nc))
        for a in acts:
            if a in sset and a not in thunks: out[a] = own
    return dict(out)


def data_affinity(starts, label, sw, loose=False):
    """globals touched by few functions: untagged ones follow the tagged users"""
    users = collections.defaultdict(set)
    for f in starts:
        for r in sw[f]['refs']:
            if r >= 0x6d4000: users[r].add(f)      # writable globals only; .rdata constants are shared by everything
    changed = True; rounds = 0
    while changed and rounds < 3:
        changed = False; rounds += 1; new = {}
        for f in starts:
            if f in label: continue
            votes = collections.Counter(); wsum = 0; ex = []
            for r in sw[f]['refs']:
                us = users.get(r, ())
                if len(us) < 2 or len(us) > 40: continue
                for g in us:
                    if g != f and g in label and (loose or label[g]['conf'] in ('high', 'med')) and label[g]['system'] != 'unknown':
                        w = (1.0 if label[g]['conf'] != 'low' else 0.5) / math.sqrt(len(us)); votes[label[g]['system']] += w; wsum += w; ex.append(r)
            if not votes: continue
            top, tv = votes.most_common(1)[0]
            if (tv >= 0.45 if loose else tv >= 0.9) and tv / wsum >= 0.7:
                new[f] = dict(system=top, conf='low', how='data', st=0.3, text='shares %d globals with %s functions (e.g. %s)' % (len(set(ex)), top, H(ex[0])))
        if new: label.update(new); changed = True
    return label


def neighbours(starts, label):
    """link order: a function between two functions of one system (and nothing else tagged between) is probably theirs"""
    new = {}
    idx = {f: i for i, f in enumerate(starts)}
    tagged = [f for f in starts if f in label and label[f]['conf'] in ('high', 'med')]
    for f in starts:
        if f in label: continue
        i = bisect.bisect_left(tagged, f)
        if 0 < i < len(tagged):
            a, b = tagged[i - 1], tagged[i]
            if label[a]['system'] == label[b]['system'] and idx[b] - idx[a] <= 8 and label[a]['system'] not in ('runtime',):
                new[f] = dict(system=label[a]['system'], conf='low', how='neighbour', st=0.25,
                              text='between %s and %s (both %s)' % (H(a), H(b), label[a]['system']))
    label.update(new)
    return label


def leftovers(starts, label, sw, callers, eh, img, mis_owner):
    for f in starts:
        if f in label: continue
        v = sw[f]
        b = img[f - BASE:f - BASE + 10]
        if b[:1] in (b'\xcc', b'\x90'):
            label[f] = dict(system='runtime', conf='low', how='padding', st=0.05, text='starts on int3/nop padding (alignment bytes between functions), no code')
        elif f in mis_owner and label.get(mis_owner[f][0], {}).get('system', 'unknown') != 'unknown':
            o = label[mis_owner[f][0]]
            label[f] = dict(system=o['system'], conf='low', how='piece-of', st=0.2, text='starts inside an instruction of %s (%s)' % (H(mis_owner[f][0]), o['system']))
        elif f in eh or (b[:1] == b'\xb8' and b[5:6] == b'\xe9'):
            label[f] = dict(system='runtime', conf='low', how='eh-glue', st=0.1, text='compiler unwind/handler glue; owners mixed or untagged (%s)' % (' '.join(H(o) for o in eh.get(f, [])[:3]) or 'none'))
        elif v['x87'] and not v['calls'] and not v['refs'] and len(callers.get(f, ())) >= 2:
            label[f] = dict(system='runtime', conf='low', how='math', st=0.2, text='x87 leaf, no calls or globals, %d callers' % len(callers.get(f, ())))
        elif v['n'] <= 12 and not v['calls'] and not v['refs'] and len(callers.get(f, ())) >= 3:
            label[f] = dict(system='runtime', conf='low', how='leaf', st=0.2, text='%d-instruction leaf, %d callers' % (v['n'], len(callers.get(f, ()))))
        else:
            label[f] = dict(system='unknown', conf='low', how='none', st=0.0, text='no string, import, doc or graph evidence')
    return label


# ---------------------------------------------------------------- main
def build():
    starts, names, lifted, hopper = load_funcs()
    pe = pefile.PE(R + '/pc/Speed.exe'); img = pe.get_memory_mapped_image()
    cont = cont_factory(starts)
    sw = sweep(img, starts)
    hcallers, hcallees, hstrs = hopper_graph(starts)
    callees = collections.defaultdict(set); callers = collections.defaultdict(set)
    for f in starts:
        s = {c for c in sw[f]['calls'] | sw[f]['jmps'] | sw[f]['cptr'] | hcallees.get(f, set()) if c in sw and c != f}
        for c in s: callees[f].add(c); callers[c].add(f)
    for g, cs_ in hcallers.items():
        for c in cs_:
            if c and c != g and g in sw: callers[g].add(c); callees[c].add(g)
    # function-pointer tables (vtables): neighbours in one table are peers; the code that points at the table owns them
    vt = collections.defaultdict(set); sset = set(starts); cur = []
    runs = []
    for off in range(DATA_LO - BASE, min(len(img), DATA_HI - BASE) - 3, 4):
        v = struct.unpack_from('<I', img, off)[0]
        if v in sset: cur.append((off + BASE, v))
        else:
            if len(cur) >= 2: runs.append(cur)
            cur = []
    for run in runs:
        lo, hi = run[0][0], run[-1][0] + 4
        mem = [v for _, v in run]
        for a in mem:
            for b in mem:
                if a != b: vt[a].add((b, 'peer'))
        for f in starts:
            if any(lo <= r < hi for r in sw[f]['refs']):
                for a in mem: vt[f].add((a, 'ptr')); vt[a].add((f, 'ptr'))
    vt_edges = {f: list(s) for f, s in vt.items()}
    for i, f in enumerate(starts):       # a start Hopper does not know is usually a piece of the function before it
        if f not in hopper and i > 0 and f < 0x684000: vt_edges.setdefault(f, []).append((starts[i - 1], 'frag')); vt_edges.setdefault(starts[i - 1], []).append((f, 'frag'))
    ev = Ev()
    string_evidence(ev, img, starts, sw, hstrs)
    import_evidence(ev, cont)
    doc_evidence(ev, sw, starts, cont, None)
    eh = eh_owners(img, starts, sw)
    mis = {}
    for i in range(len(starts) - 1):    # a start inside the instruction before it (lifter data seed): bytes of that function
        if sw[starts[i]]['over'] and starts[i + 1] not in eh:
            root = mis[starts[i]][0] if starts[i] in mis else starts[i]   # chains of seeds inside one instruction stream
            mis[starts[i + 1]] = [root]
    # a catch/cleanup funclet runs inside its owner's frame: the strings it names are the owner's strings
    for fl in [f for f in eh if f not in mis]:
        for e in [e for e in ev.d.get(fl, []) if e[2] == 'string']:
            for o in eh[fl][:1]:
                if o in sw and o != fl: ev.add(o, e[0], 0.8 * e[1], 'string', 'via unwind funclet %s: %s' % (H(fl), e[3]))
    label = {}
    for f, items in ev.d.items():
        if f in sw:
            s, c, h, t, st = arbitrate(items); label[f] = dict(system=s, conf=c, how=h, text=t, st=st)
    nseed = len(label)
    eh.update(mis)
    propagate(starts, label, callers, callees, sw, vt_edges, eh, frozenset(f for f in eh if f not in mis))
    npropagated = len(label) - nseed
    data_affinity(starts, label, sw)
    neighbours(starts, label)
    data_affinity(starts, label, sw, loose=True)
    # a second graph pass over what data/neighbour tagging added is not done: those are low and stay leaves
    leftovers(starts, label, sw, callers, eh, img, mis)
    return starts, names, lifted, label, dict(seed=nseed, graph=npropagated, hopper=hopper, eh=len(eh), mis=len(mis))


def write(starts, lifted, label):
    os.makedirs(R + '/census', exist_ok=True)
    with open(R + '/census/systems.tsv', 'w') as f:
        f.write('# Made by tools/census/systems.py (docs/re/systems_method.md). addr = function start; one row per Hopper function start.\n')
        f.write('addr\tsystem\tconfidence\thow\tevidence\n')
        for a in starts:
            L = label[a]
            f.write('%s\t%s\t%s\t%s\t%s\n' % (H(a), L['system'], L['conf'], L['how'], L['text'].replace('\t', ' ').replace('\n', ' ')))


def counts(starts, lifted, label):
    t = collections.defaultdict(collections.Counter)
    for a in starts:
        if a in lifted: t[label[a]['system']][label[a]['conf']] += 1
    lines = ['| system | high | med | low | total | %% |', '|---|---|---|---|---|---|']
    tot = sum(sum(c.values()) for c in t.values())
    for s in SYSTEMS:
        c = t.get(s, collections.Counter()); n = sum(c.values())
        lines.append('| %s | %d | %d | %d | %d | %.1f |' % (s, c['high'], c['med'], c['low'], n, 100.0 * n / tot))
    g = collections.Counter(); [g.update(c) for c in t.values()]
    lines.append('| all | %d | %d | %d | %d | 100 |' % (g['high'], g['med'], g['low'], tot))
    return '\n'.join(lines)


def sample(starts, lifted, label, n, seed, maxlines=28):
    """seeded random sample of lifted functions, with the Hopper decompile head, for a manual read"""
    rnd = random.Random(seed); pick = sorted(rnd.sample(sorted(lifted), n))
    print('SAMPLE seed=%d n=%d' % (seed, n))
    body = {}; cur = None; hdr = re.compile(r'^// ([0-9a-f]{8}) (\S+)$')
    want = set(pick)
    # a start Hopper does not have: show the code of the Hopper function that contains it
    cont = cont_factory(starts)
    for line in open(R + '/census/hopper/decomp.c', errors='replace'):
        m = hdr.match(line)
        if m: cur = int(m.group(1), 16); body[cur] = []; continue
        if cur is not None: body[cur].append(line.rstrip())
    for a in pick:
        L = label[a]; src = a if a in body else max((k for k in body if k <= a), default=None)
        print('\n#### %s  TAG %s/%s [%s] %s%s' % (H(a), L['system'], L['conf'], L['how'], L['text'][:200], '' if src == a else '  (inside Hopper %s)' % H(src)))
        txt = body.get(src, [])
        print('\n'.join(l for l in txt[:maxlines] if l.strip()))

if __name__ == '__main__':
    args = sys.argv[1:]
    starts, names, lifted, label, info = build()
    hopper = info['hopper']
    write(starts, lifted, label)
    print('unwind funclets/thunks or misaligned seeds with an owner: %d (misaligned %d)' % (info['eh'], info['mis']))
    print('functions %d, lifted %d, lifted with a row %d, seeds %d, graph-propagated %d' % (len(starts), len(lifted), len(lifted & set(label)), info['seed'], info['graph']))
    print(counts(starts, lifted, label))
    if '--sample' in args:
        i = args.index('--sample'); n = int(args[i + 1]); seed = int(args[args.index('--seed') + 1]) if '--seed' in args else 1
        sample(starts, lifted, label, n, seed)
    hw = collections.Counter(L['how'].split('+')[0] for L in label.values()); print(dict(hw))
