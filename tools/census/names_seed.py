#!/usr/bin/env python3
"""Seed the function-name registry from the PC addresses this repo's notes already mention.

Scanned (source of meaning, PC addresses only):
  docs/*.md, docs/openworld/*.md          every line
  tools/recomp/patches.py                 every line
  tools/hopper/q_*.py                     comments and docstrings only
  HANDOFF.md                              every line
  census/ghidra/*.txt                     header lines (starting with '#')
Counted, never tabled (source=ref, other build, PS2 addresses): ref/docs/re/*.md

Function table: census/hopper/funcs.tsv (start addresses and names). Byte sizes come from
census/ghidra/funcs_*.tsv where present. Where no size is known, the end of a function is the next start.

Writes census/names_seed.tsv and census/names_seed_summary.txt. Stdlib only, run with:
    python3 -I tools/census/names_seed.py
"""
import ast
import bisect
import collections
import io
import os
import subprocess
import sys
import re
import tokenize
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LO, HI = 0x401000, 0x697000
ADDR_RE = re.compile(r'(?<![0-9A-Za-z_])0x([0-9a-f]{6})(?![0-9A-Za-z_])')
UPPER_RE = re.compile(r'(?<![0-9A-Za-z_])0[xX]([0-9a-fA-F]{6})(?![0-9A-Za-z_])')
SNIPPET_MAX = 200
TSV_OUT = ROOT / 'census/names_seed.tsv'
SUMMARY_OUT = ROOT / 'census/names_seed_summary.txt'

variant_count = collections.Counter()  # in-range mentions in uppercase or 0X form (not captured)


def hits(seg, line, lineno):
    """Yield (addr, lineno, physical line, column) for each in-range 0x mention inside seg."""
    for m in ADDR_RE.finditer(seg):
        a = int(m.group(1), 16)
        if LO <= a <= HI:
            yield a, lineno, line, line.find(m.group(0))
    for m in UPPER_RE.finditer(seg):
        a = int(m.group(1), 16)
        if LO <= a <= HI and not ADDR_RE.fullmatch(m.group(0)):
            variant_count[lineno] += 1


def iter_mentions(path, mode):
    text = path.read_text(encoding='utf-8', errors='replace')
    lines = text.split('\n')
    if mode == 'lines':
        for n, line in enumerate(lines, 1):
            yield from hits(line, line, n)
    elif mode == 'headers':
        for n, line in enumerate(lines, 1):
            if line.startswith('#'):
                yield from hits(line, line, n)
    elif mode == 'code_notes':
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            tree = ast.parse(text, filename=str(path))
        doc_lines = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)):
                    doc_lines.update(range(first.lineno, first.end_lineno + 1))
        for n in sorted(doc_lines):
            yield from hits(lines[n - 1], lines[n - 1], n)
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                n = tok.start[0]
                yield from hits(tok.string, lines[n - 1], n)
    else:
        raise ValueError(mode)


def snippet(line, col):
    raw = line.replace('\t', ' ')
    lead = len(raw) - len(raw.lstrip())
    s = raw.strip()
    if len(s) <= SNIPPET_MAX:
        return s
    p = max(0, col - lead)
    start = max(0, min(p - SNIPPET_MAX // 2, len(s) - SNIPPET_MAX))
    return s[start:start + SNIPPET_MAX]


def load_functions():
    names = {}
    with (ROOT / 'census/hopper/funcs.tsv').open(encoding='utf-8') as f:
        next(f)
        for line in f:
            p = line.rstrip('\n').split('\t')
            if p and p[0]:
                names[int(p[0], 16)] = p[1] if len(p) > 1 else ''
    sizes = {}
    for path in sorted((ROOT / 'census/ghidra').glob('funcs_*.tsv')):
        with path.open(encoding='utf-8') as f:
            next(f)
            for line in f:
                p = line.rstrip('\n').split('\t')
                if len(p) >= 7 and p[6].isdigit() and int(p[6]) > 0:
                    sizes[int(p[0], 16)] = int(p[6])
    return names, sizes


def main():
    names, sizes = load_functions()
    starts = sorted(names)
    ends = {s: s + sizes[s] for s in starts if s in sizes}

    def classify(a):
        i = bisect.bisect_right(starts, a) - 1
        if i < 0:
            return 'no', ''
        s = starts[i]
        if a == s:
            return 'yes', s
        end = ends.get(s)
        if end is None:
            end = starts[i + 1] if i + 1 < len(starts) else HI + 1
        return ('inside' if a < end else 'no'), s

    # tools/hopper/queries.json topics are rendered into build/hopper/q_*.py (what hpar.sh runs), so they are scanned too
    subprocess.run([sys.executable, str(ROOT / 'tools/hopper/mkq.py')], check=True, stdout=subprocess.DEVNULL, env=dict(os.environ, HOP_REPO=str(ROOT)))
    # PC table: docs, openworld docs, patches, hopper q-scripts, HANDOFF, ghidra headers
    groups = [
        ('docs', sorted((ROOT / 'docs').glob('*.md')), 'lines'),
        ('docs/openworld', sorted((ROOT / 'docs/openworld').glob('*.md')), 'lines'),
        ('patches', [ROOT / 'tools/recomp/patches.py'], 'lines'),
        ('hopper_q', sorted((ROOT / 'tools/hopper').glob('q_*.py')) + sorted((ROOT / 'build/hopper').glob('q_*.py')), 'code_notes'),
        ('handoff', [ROOT / 'HANDOFF.md'], 'lines'),
        ('ghidra_headers', sorted((ROOT / 'census/ghidra').glob('*.txt')), 'headers'),
    ]
    rows = []  # (addr, in_funcs, func_start, source, line, snippet)
    files_scanned = collections.Counter()
    for group, paths, mode in groups:
        for path in paths:
            rel = path.relative_to(ROOT).as_posix()
            files_scanned[group] += 1
            for a, lineno, line, col in iter_mentions(path, mode):
                cls, s = classify(a)
                rows.append((a, cls, s, rel, lineno, snippet(line, col)))

    rows.sort(key=lambda r: (r[0], r[3], r[4]))
    with TSV_OUT.open('w', encoding='utf-8', newline='\n') as f:
        f.write('addr\tin_funcs\tfunc_start\tsource\tline\tsnippet\n')
        for a, cls, s, src, n, snip in rows:
            f.write(f'{a:08x}\t{cls}\t{f"{s:08x}" if s != "" else ""}\t{src}\t{n}\t{snip}\n')

    # ref: counted only, other build (PS2 addresses) -> not in the table
    ref_files = sorted((ROOT / 'ref/docs/re').glob('*.md'))
    ref_hits = []
    for path in ref_files:
        for a, _, _, _ in iter_mentions(path, 'lines'):
            ref_hits.append(a)
    ref_mentions = len(ref_hits)
    ref_distinct = len(set(ref_hits))

    # lifted functions: census/speed_exe_functions.tsv (no header; kinds call/data/entry)
    lifted = []
    with (ROOT / 'census/speed_exe_functions.tsv').open(encoding='utf-8') as f:
        for line in f:
            p = line.rstrip('\n').split('\t')
            if len(p) >= 2 and p[0]:
                lifted.append((int(p[0], 16), p[1]))
    kinds = collections.Counter(k for _, k in lifted)
    addr_mentioned = {r[0] for r in rows}
    covered_starts = {r[2] for r in rows if r[1] in ('yes', 'inside')}
    exact_starts = {r[0] for r in rows if r[1] == 'yes'}

    def lifted_cov(entries):
        exact = sum(1 for a in entries if a in addr_mentioned)
        body = sum(1 for a in entries if a in covered_starts)
        return exact, body

    all_entries = [a for a, _ in lifted]
    call_entries = [a for a, k in lifted if k == 'call']
    exact_all, body_all = lifted_cov(all_entries)
    exact_call, body_call = lifted_cov(call_entries)

    cls_counts = collections.Counter(r[1] for r in rows)
    cls_distinct = collections.defaultdict(set)
    for r in rows:
        cls_distinct[r[1]].add(r[0])
    per_source = collections.Counter(r[3] for r in rows)
    top15 = sorted(per_source.items(), key=lambda kv: (-kv[1], kv[0]))[:15]
    names_nonsub = sum(1 for s, n in names.items() if n and not n.startswith('sub_'))
    names_blank = sum(1 for s, n in names.items() if not n)

    lines = [
        'names_seed summary (generated by tools/census/names_seed.py)',
        '',
        f'total mentions (PC table rows): {len(rows)}',
        f'distinct addresses: {len(addr_mentioned)}',
        f'distinct function starts covered (mention at start, in_funcs=yes): {len(exact_starts)}',
        f'distinct function starts covered (start or body, yes+inside): {len(covered_starts)}',
        '',
        'mentions by in_funcs:',
    ]
    for cls in ('yes', 'inside', 'no'):
        lines.append(f'  {cls}: {cls_counts.get(cls, 0)} mentions, {len(cls_distinct.get(cls, set()))} distinct addresses')
    lines += [
        '',
        f'lifted functions (census/speed_exe_functions.tsv): {len(lifted)} rows, kinds {dict(sorted(kinds.items()))}',
        f'  rows with a mention at exactly that address: {exact_all} of {len(all_entries)}',
        f'  rows with a mention at start or in body (funcs.tsv): {body_all} of {len(all_entries)}',
        f'  call-kind rows with a mention at exactly that address: {exact_call} of {len(call_entries)}',
        f'  call-kind rows with a mention at start or in body: {body_call} of {len(call_entries)}',
        '  NOTE: census/lift_report.json and docs/coverage.md give 13,739 lifted (14,354 seeds minus 615 dropped);'
        ' no subset of speed_exe_functions.tsv has that size, so the 13,739 set was not reproduced.',
        '',
        'top 15 source files by mentions:',
    ]
    for src, n in top15:
        lines.append(f'  {n:6d}  {src}')
    lines += [
        '',
        'files scanned per group:',
    ]
    for group, _, _ in groups:
        lines.append(f'  {group}: {files_scanned[group]} files')
    lines += [
        '',
        f'ref (source=ref, other build, counted only, not in names_seed.tsv): {len(ref_files)} files, '
        f'{ref_mentions} mentions, {ref_distinct} distinct addresses',
        '',
        'function table notes:',
        f'  census/hopper/funcs.tsv rows: {len(names)}; named (not sub_): {names_nonsub}; blank name: {names_blank}',
        f'  starts with a byte size from census/ghidra/funcs_*.tsv: {len(ends)} of {len(starts)}; '
        'the rest use the next start as end',
        f'  in-range uppercase or 0X mentions not captured by the lowercase 0x rule: {sum(variant_count.values())}',
        '  bare 8-digit hex without 0x is not captured (only 0x mentions are in the spec)',
        '  census/ghidra/menu_xrefs.txt: only its # header lines are scanned, as the spec says; its body has 0x'
        ' xref lines that are not scanned',
    ]
    with SUMMARY_OUT.open('w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'wrote {TSV_OUT} ({len(rows)} rows)')
    print(f'wrote {SUMMARY_OUT}')


if __name__ == '__main__':
    main()
