# Review 2: the three patches

Scope: (a) bec/lalo `docs/re/ai_stuck.md` float readers + patch, (b) bec/tomas [`docs/re/ai_traffic.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/ai_traffic.md) patch 1 at
0x4539db, (c) bec/memo [`docs/re/ai_corner.md`](https://github.com/Caliko06/need-for-speed-underground-browser/blob/dd1146b/docs/re/ai_corner.md) one-sided jitter. Tools: capstone 5.0.7 (the repo venv has it), full-`.text` scan of `pc/Speed.exe`, `census/hopper/decomp.c`. Nothing run.
V = read at the address. The old bytes quoted below are the image bytes, hex, read from the file.

**(b) and (c) are mechanically sound.** (a) counts right but its diagnosis is wrong: the patch cannot remove the
entries it is aimed at.

## (a) lalo · 0x6b7680 (timer 0.4 s) and 0x6b7684 (speed 5.0 m/s)

| item | verdict | evidence |
|---|---|---|
| 0x6b7680 read only at 0x451c2e / 0x451eaf / 0x451ffb | **OK** | 3 operand refs in all 2.7 MB of `.text` and 3 raw dword occurrences in the whole file. No pointer table to the float. V |
| 0x6b7684 read only at 0x451c48 / 0x451c54 / 0x451ec5 / 0x45201b / 0x452027 | **OK**, 2 addresses off by one byte | 5 refs, same scan. But the 5th and 2nd are `mov eax,[0x6b7684]` whose opcode is at **0x451c55** and **0x452028**; the doc cites the last byte of the preceding `jnp`. V |
| all 8 belong to "the three stuck finders" | **OK**, naming imprecise | 0x451c2e/48/55 → `sub_451b00` (action finder, returns 0x1f4 at 0x451c9b). 0x451eaf/ec5 → `sub_451dc0`. 0x451ffb/45201b/452028 → `sub_451f10`. The last two are **boolean predicates** (`ret 4`, return al 0/1) with no direct `call` anywhere; each address appears once in the file, as a dword in a function-pointer table in `.rdata` at 0x6c9188 / 0x6c918c, next to 0x451a70/0x452070. So the data patch also moves those two, which the doc does not mention. V |
| patch bytes | **OK** | 0x6b7680 = `cdcccc3e` (0.4f) → `0000c03f` (1.5f); 0x6b7684 = `0000a040` (5.0f) → `00004040` (3.0f). Both encode as intended. V |
| timer direction (1.5 is stricter, not looser) | **OK** | 0x451c36 `test ah,1; jne skip` = fires only when age >= 0.4. V |
| `0x424b50(speed,5.0,0.001)` "can still veto, a rare escape roll" | **WRONG** | 0x424b50 is `fabs(a-b) <= eps`: `fsub; fabs; fcomp; jp; mov eax,1`. It returns 1 **only** when speed is within 0.001 of 5.0, and the caller **sets** stuck on nonzero (0x451c6d `je skip`). No randomness, no veto. Net speed test: `speed <= 5.0`. V |
| "27-38 % of entries happen at >= 5 m/s, false positives of the 0.4 s trigger" | **WRONG** | The contact branch can only set the flag with speed <= 5.0 (0x451c53 `jnp` + the equality band). An entry at 6-20 m/s came from the off-route branch (cross >= 20.0, 0x6b7690 = 20, jumps to 0x451bdb) or from modes 3/4 (0x6b7688 = 25, 0x6b768c = 20, `0x44e9c0(...)==1`, also 0x451bdb). Neither reads the two floats, so changing them leaves those reversals untouched. V |
| "the car has been within 0.4 s of a contact" | **WRONG wording** | It is "**at least** 0.4 s since the contact entry" (age >= 0.4), the opposite of "within". V |

Minor: 0x451dc0 tests the **raw** speed (no `fabs`), 0x451f10 uses `fabs`; a reversing car at -6 m/s satisfies
`speed < 5.0` and will keep flagging stuck. Only relevant if the -15/-6 m/s strength is ever touched (they said it
is out of scope). V

## (b) tomas · 12 bytes at 0x4539db

| item | verdict | evidence |
|---|---|---|
| old bytes match the image | **OK** | `8b511c 85d2 0f95c0 84c0 7418` = `mov edx,[ecx+0x1c]; test edx,edx; setne al; test al,al; je 0x4539ff`. 3+2+3+2+2 = 12. V |
| new bytes decode as claimed | **OK** | `8b4914` = `mov ecx,[ecx+0x14]`; `837904 02` = `cmp dword [ecx+4],2`; `751b` = `jne 0x4539ff`; `90 90 90`. 3+4+2+3 = 12. V |
| same length / same next instruction | **OK** | Both end at 0x4539e7 (`mov eax,edi`). No straddle, no padding needed. V |
| jump target | **OK** | old: `je` at 0x4539e5, next 0x4539e7 + 0x18 = **0x4539ff**. new: `jne` at 0x4539e2, next 0x4539e4 + 0x1b = **0x4539ff**. Same edge, same direction (jump = not exempt). V |
| registers | **OK** | ecx is dead after the block: 0x4539e7 loads `eax=edi` and calls 0x44d5f0 (this in eax), and ecx is reloaded at 0x453a31. The old code's edx/al clobbers were dead too. Nothing between 0x4539db and 0x4539e7 reads ecx. V |
| no entry into the patched range | **OK** | zero `j*`/`call` targets and zero dword pointers land in [0x4539db,0x4539e7). V |
| `[ecx+0x14]` is the entrant and `+4` is the kind | **OK** | Same chain the Pass finder already uses: `[driver+0x1d4]+0x90` → `[+0x14]` → `cmp dword [+4],2` at 0x45056b. Here ecx is exactly that object (0x4539d5) and the block is gated by `0x647b70(...)==6` at 0x4539ca. V |
| new null deref `[[ecx+0x14]+4]` | **OK**, no new mode | The old code only tested `[ecx+0x1c]`, never dereferenced. The new one dereferences unconditionally, but Pass (0x450590) and Block (0x450f9d) already do the same unguarded on the same object, behind the same `==6` gate. V |
| semantic side effect not stated | **see note** | Old: exempt when flag `[…+0x90]+0x1c` != 0 **and** my speed > 20 (0x6ccb4c), and the exemption returns -1 for the whole finder (0x453a07), i.e. no Avoid at all. New: the same early-out only for a kind-2 leader. So **every kind-1 and kind-3 car ahead becomes a normal candidate at any speed**, including traffic behind traffic. That is the intent for the player, but it feeds the 69 %-in-type-3 jam the same doc complains about. I |

## (c) memo · jitter at 0x44c667

| item | verdict | evidence |
|---|---|---|
| 0x44c667 is the `record+0x50` load | **OK** | `0fb6b6 48a07700` = `movzx esi,byte [esi+0x77a048]`, and 0x77a048 = 0x779ff8+0x50. It is the **only** reader of that byte in the image. V |
| formula `NextMod(2*(b+1)) - (b+1)` = `[-(b+1), +b]` | **OK** | 0x44c66e `inc esi`; 0x44c66f `lea edx,[esi+esi]`; 0x44c673 `call 0x4216b0` (NextMod); 0x44c678 `sub eax,esi`; 0x44c67a store to ctx+0x404. V |
| 5 s re-roll contract | **OK** | 0x77a498 is read only at 0x44c651 (the draw gate); 0x77a49c is the rubber band's, read at 0x44bdcf. Current values are BSS/tuning, unreadable here (U). V address, U value |
| "2-3 byte ASM cave" | **WRONG / overkill** | No cave. The bias is `2b c6` (2 bytes) at **0x44c678**; `90 90` there gives the 0..2b+1 window the doc itself describes. Nothing else moves. V |
| effect | **OK as stated** | Removing the bias kills the stale-behind reference and doubles the look-ahead (0..17 nodes at b=8). Risk of reading a corners' cap ~17 nodes early (over-braking) is I, not measured. |
| "no capstone in this worktree venv" | **UNSURE / blocker gone** | capstone 5.0.7 is at `/Users/angeldamian/RE-NFSU/.venv/bin/python`; that is what produced every hex above. |

## What I did not check
- Data values of the tuning table (`record+0x14`, `+0x50`, 0x77a498) — `game/` is not in this worktree.
- The runtime effect of any patch: nothing was built or run.
- The meaning of the old flag `[[driver+0x1d4]+0x90]+0x1c` (goal 5?) — UNSURE, but (b) deletes the test, so it does
  not block the patch.
