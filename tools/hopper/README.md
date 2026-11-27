# Hopper batch queries for Speed.exe

Scripts that drive the Hopper disassembler in the background to decompile **Need for Speed Underground**'s `Speed.exe` in bulk. Output lands in [`census/hopper/`](../../census/hopper) and is grepped before any new query. Why two decompilers and how they are used: [English](https://nfsu.cc/blog/en/reverse-engineering-tools-ghidra-hopper-rea.html) · [Español](https://nfsu.cc/blog/es/herramientas-ingenieria-inversa-ghidra-hopper-rea.html) · **Play: [nfsu.cc](https://nfsu.cc)**

| File | [`export.sh`](export.sh) | [`hpar.sh`](hpar.sh) | [`mkq.py`](mkq.py) | `q_*.py` |
|---|---|---|---|---|
| Does | Export every procedure to `decomp.c` + `funcs.tsv` | Run chunks on up to 6 windows (renders a missing `q_<topic>.py` itself) | Spec (`queries.json`: addresses, data, strings) to `build/hopper/q_<topic>.py` | Hand-made queries only; the rest live in `queries.json` |

Back to the [repo](../../README.md).
