#!/usr/bin/env python3
"""Spec -> build/hopper/q_<topic>.py (rendered from q_template.py), for hpar.sh (it renders a missing topic by itself).
Spec JSON: {"<topic>": {"q": "...", "addrs": ["0x4b5c00"], "data": ["0x777cc8"], "strings": ["Player Too Slow"], "deep": 1}}.
tools/hopper/queries.json holds the topics already run; a spec with "strings" always gets DEEP.
A string is found in pc/Speed.exe (exact, NUL-ended) and becomes a DATA address; DEEP=1 then also decompiles every
procedure that references a DATA address (at most 16 per topic), so a topic can start from a name alone.
usage: .venv/bin/python tools/hopper/mkq.py [spec.json [topic ...]]   (default spec: queries.json; prints the topics, for hpar.sh)
Output goes to $HOP_REPO (default: this repo)/build/hopper/."""
import json, os, re, sys
H = os.path.dirname(os.path.abspath(__file__))
R = os.environ.get('HOP_REPO') or os.path.dirname(os.path.dirname(H))
tpl = open(f'{H}/q_template.py').read()
DEEP = '''
seen = set(ADDRS)
for a in DATA:
    for x in refs(a):
        p = proc(x)
        if p is None or len(seen) >= len(ADDRS) + 16: continue
        e = p.getEntryPoint()
        if e in seen: continue
        seen.add(e); n += 1
        f.write('\\n==== 0x%x %s (refs data 0x%x)\\n' % (e, doc.getNameAtAddress(e) or '', a))
        try: f.write((p.decompile() or '(no pseudocode)') + '\\n')
        except Exception as x: f.write('(decompile failed: %s)\\n' % x)
        f.write('callers: %s\\n' % '; '.join(where(r) for r in refs(e)))
        f.flush()
'''
OLD = ['# Use Hopper for what Ghidra does not give: bodies Ghidra lacks or splits differently, or a second reading when',
       "# Ghidra's pseudocode looks wrong. Offsets/writers/callers: Ghidra first (tools/rea/gpar.sh: scalar, xref, callers)."]
out = []; spec = json.load(open(sys.argv[1] if len(sys.argv) > 1 else f'{H}/queries.json'))
os.makedirs(f'{R}/build/hopper', exist_ok=True)
for t in sys.argv[2:] or spec:
    s = spec[t]
    data = [int(a, 16) for a in s.get('data', [])]
    if s.get('strings'):
        import pefile
        img = pefile.PE(f'{R}/pc/Speed.exe').get_memory_mapped_image()
    for st in s.get('strings', []):
        for m in re.finditer(re.escape(st.encode()) + b'\0', img):
            if m.start() == 0 or img[m.start() - 1] == 0: data.append(m.start() + 0x400000)
    code = tpl
    notes = (OLD if s.get('oldhdr') else []) + s.get('note', [])   # per-topic header comments from the old clones
    code = re.sub(r"^OUT = .*$", lambda _: '\n'.join(notes + [f"OUT = '{R}/build/hopper/{t}.txt'"]), code, flags=re.M)
    code = re.sub(r"^Q = .*$", 'Q = ' + repr(s['q']), code, flags=re.M)
    code = re.sub(r"^ADDRS = .*$", 'ADDRS = [' + ', '.join(s.get('addrs', [])) + ']', code, flags=re.M)
    code = re.sub(r"^DATA = .*$", 'DATA = [' + ', '.join(hex(a) for a in data) + ']', code, flags=re.M)
    if s.get('deep') or s.get('strings'): code = code.replace("f.write('\\nDONE", DEEP.strip('\n') + "\nf.write('\\nDONE", 1)
    open(f'{R}/build/hopper/q_{t}.py', 'w').write(code)
    out.append(t)
print(' '.join(out))
