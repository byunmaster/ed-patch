"""**주입 `%c` 쌍** — 둘째 바이트가 `0x5C` 인 SJIS 글자를 콜사이트 인자로 되살린다.

    python3 tools/inject_pairs.py            # 자리를 훑어 보고한다 (제안)
    python3 tools/inject_pairs.py --freeze   # 정본(`inject_pairs.json`)에 얼린다

## 무엇을 고치나

팔콤 툴체인은 **둘째 바이트가 `0x5C`(`\\`)인 SJIS 글자**를 문자열 리터럴에 못 넣는다
(C 소스에서 이스케이프로 먹힌다). 대신 그 자리에 `%c%c` 를 적고 **두 바이트를 인자로**
넘긴다 — `ソ`(0x835C)가 대표다:

    원본 텍스트   %c%c%cニア%c\\n…        ← 이름칸이 「ニア」로 보인다
    콜사이트      r6=2 · r7=0x83 · push 0x5C,1,6
    화면          <2> ソ ニ ア <1> … <6>  ← 실제로는 「ソニア」

우리는 이름칸을 **정본 이름으로 알아보지 못해** 그 블록을 통째로 건너뛰고 있었다
(실측 2026-09-03: 화면에 남은 일본어 8줄 중 **5줄**이 이것이다).

🔴 status 에 「구조 미상 · 0x5C 가설 기각」이라고 적혀 있었는데 **그 기각이 틀렸다.**
   근거였던 「같은 파일이 `ソ` 를 직접 넣는 자리도 있다」는 반증이 못 된다 — 씬 파일은
   `[지명 헤더][코드][텍스트]` 가 **지역 단위로 여러 번** 반복되는, 곧 **번역 단위가 여럿**인
   파일이라 자리마다 툴체인 사정이 다르다. 이 모듈은 가설이 아니라 **콜사이트 디스어셈블**로
   확정한다(PS1 이 같은 결론에 먼저 닿았다 — `reinsert_kr_pilot.SCN_ARG_PATCHES`).

## 어떻게 확정하나 — 텍스트가 아니라 **인자열**로

「글자 사이에 낀 `%c%c`」 같은 텍스트 휴리스틱은 오탐이 난다(수치 두 자리 주입 ·
이름칸 색코드가 같은 꼴이다). 그래서 **코드를 읽는다**:

1. `ptr_at`(리터럴 풀)을 `mov.l @(d,pc),r5` 로 싣는 명령을 찾는다 → 거기가 콜사이트다.
2. 거기서 `jsr` 까지 걸으며 **레지스터 값과 `mov.l Rn,@-r15` 푸시**를 따라간다.
   인자열 = `[r6, r7] + reversed(푸시)` — SH-2 ABI(r4=버퍼 · r5=서식 · r6·r7 = 인자 1·2).
3. 서식 문자열의 마크업(`%c`·`%s`·`%d`)에 인자를 **순서대로** 물린다.
   🔴 **검산이 여기 있다** — 마크업 수와 인자 수가 같아야 하고, `%s` 자리엔 포인터
      (`0x06……`)가, `%c` 자리엔 한 바이트가 와야 한다. 안 맞으면 **아무 것도 안 한다.**
4. 이웃한 `%c` 둘의 인자가 `(선두바이트, 0x5C)` 면 그게 **주입 쌍**이고, 글자는 그 두
   바이트를 cp932 로 디코드한 것이다. 후보를 찍어 맞히는 게 아니라 **읽어 낸다.**

## 어떻게 고치나 — 층이 둘이다

- **텍스트** — 쌍을 실제 글자로 되돌린 「정본 JP」로 저본·이름칸을 찾고(`restore`),
  조판이 끝난 뒤 **같은 창 꼬리에 쌍을 되돌린다**(`reinsert`).
  🔴 되돌리는 자리가 「같은 창」인 게 핵심이다 — 마크업 **순서**가 곧 인자 순서라,
     창을 넘겨 옮기면 뒤 인자가 전부 밀린다(구조 계약 ②).
- **코드** — 주입 인자를 만드는 명령의 즉치를 **`0x20`(공백)으로** 바꾼다(`arg_words`).
  그러면 되돌린 쌍이 **반각 공백 둘**을 그려 안 보인다. `mov #imm,Rn`·`mov.w @(d,pc),Rn`
  둘 다 **2바이트**라 `mov #0x20,Rn` 으로 제자리 교체다 — 재배치가 없다.
  ⚠ **그 블록을 실제로 번역했을 때만** 고친다. JP 로 남기면 `ソ` 가 그대로 나와야 한다.
  ⚠ 한 명령이 **다른 인자도 만들면** 안 고친다(레지스터 재사용). 그 명령이 만드는 인자가
    전부 주입 인자일 때만 손댄다.

## 정본과 제안

제안은 이 모듈이 매번 다시 계산하지만, **빌드가 읽는 것은 정본**(`inject_pairs.json`)이다
(루트 CLAUDE.md 제1원칙). 정본에는 **원문을 안 담는다** — 파일 · 블록 오프셋 · 마크업
번호 · 글자 하나 · 고칠 명령의 오프셋과 옛/새 워드뿐이다. 빌드는 얼린 값과 이미지가
**아직 같은지** 대조하고(`verify_site`), 어긋나면 실패시킨다.
"""

import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

CANON = os.path.join(common.GAME_DIR, "inject_pairs.json")
MARK = re.compile(r"%[csd]")
# SJIS 선두 바이트 — 인자가 이 범위면 「글자의 앞바이트」다(제어코드는 0x20 미만).
LEAD = tuple(list(range(0x81, 0xA0)) + list(range(0xE0, 0xFD)))
ESC = 0x5C
SPACE = 0x20
# 콜사이트를 걸어가는 최대 명령 수 — 넘으면 「못 읽었다」로 본다(추측하지 않는다).
WALK = 64


def _w(d, at):
    """BE16 — ⚠ 범위 밖이면 None. 리터럴 풀이 파일 끝에 붙은 자리가 실재한다."""
    if at < 0 or at + 2 > len(d):
        return None
    return struct.unpack(">H", d[at : at + 2])[0]


def _l(d, at):
    if at < 0 or at + 4 > len(d):
        return None
    return struct.unpack(">I", d[at : at + 4])[0]


def fmt_loads(d, ptr_at):
    """`ptr_at` 의 리터럴을 `r5`(서식 인자)로 싣는 명령들의 파일 오프셋."""
    out = []
    for a in range(0, min(ptr_at, len(d) - 1), 2):
        w = _w(d, a)
        if w is None or w >> 12 != 0xD or (w >> 8) & 0xF != 5:
            continue
        if ((a + 4) & ~3) + (w & 0xFF) * 4 == ptr_at:
            out.append(a)
    return out


def _read_regs(d, at, reg, stop):
    """`at` 에서 **뒤로** 걸으며 `reg` 에 마지막으로 쓴 명령 → `(값, 오프셋)`. 없으면 None.

    ⚠ 뒤로 걷는 건 `r6`·`r7` 뿐이다(콜사이트가 서식 적재 앞에서 세우는 경우가 있다).
      직전 `jsr` 를 만나면 멈춘다 — 그 너머는 **남의 콜사이트**다.
    """
    a = at - 2
    while a >= stop:
        w = _w(d, a)
        if w is None:
            return None
        if w & 0xF0FF == 0x400B:  # jsr @Rn — 남의 콜사이트
            return None
        got = _set_of(d, a, w)
        if got and got[0] == reg:
            return got[1], a
        a -= 2
    return None


def _set_of(d, a, w):
    """그 명령이 레지스터에 값을 쓰면 `(레지스터, 값)`. 아니면 None."""
    n = (w >> 8) & 0xF
    if w >> 12 == 0xE:  # mov #imm,Rn
        return n, w & 0xFF
    if w >> 12 == 0x9:  # mov.w @(d,pc),Rn
        v = _w(d, (a + 4) + (w & 0xFF) * 2)
        return None if v is None else (n, v)
    if w >> 12 == 0xD:  # mov.l @(d,pc),Rn
        v = _l(d, ((a + 4) & ~3) + (w & 0xFF) * 4)
        return None if v is None else (n, v)
    if w & 0xF00F == 0x6003:  # mov Rm,Rn
        return n, ("=", (w >> 4) & 0xF)
    return None


def args_of(d, ptr_at):
    """콜사이트의 **인자열** → `[(값, 만든 명령의 오프셋 또는 None)]`. 못 읽으면 None.

    🔴 추측하지 않는다 — 서식 적재부터 `jsr` 까지 한 번에 안 닿거나, `r6`·`r7` 을 못 찾으면
       None 을 준다. 부르는 쪽은 그 블록을 **원본 그대로** 둔다.
    """
    loads = fmt_loads(d, ptr_at)
    if len(loads) != 1:
        return None
    at = loads[0]
    reg = {}  # 레지스터 → (값, 만든 오프셋)
    push = []
    a = at + 2
    end = min(len(d) - 1, at + WALK * 2)
    while a < end:
        w = _w(d, a)
        if w is None:
            return None
        if w & 0xF0FF == 0x400B:  # jsr @Rn — 여기서 인자가 굳는다
            break
        if w & 0xF00F == 0x2006 and (w >> 8) & 0xF == 15:  # mov.l Rm,@-r15
            m = (w >> 4) & 0xF
            if m not in reg:
                # ⚠ 서식 적재 **앞에서** 세운 레지스터다(`%s` 이름 포인터가 흔하다).
                #   뒤로 걸어 찾되, 직전 `jsr` 를 넘으면 **모르는 인자**로 둔다.
                #   🔴 여기서 통째로 포기하면 안 된다 — 콜사이트가 **분기 목적지**인 자리가
                #      있어(점프 표에서 들어온다) 선행 코드가 그 경로의 것이 아니다.
                #      우리가 필요한 건 주입 쌍의 두 인자뿐이라, 나머지는 몰라도 된다.
                reg[m] = _read_regs(d, at, m, max(0, at - WALK * 2)) or (None, None)
            push.append(reg[m])
        else:
            got = _set_of(d, a, w)
            if got:
                n, v = got
                if isinstance(v, tuple):  # mov Rm,Rn
                    if v[1] not in reg:
                        reg.pop(n, None)
                        a += 2
                        continue
                    reg[n] = reg[v[1]]
                else:
                    reg[n] = (v, a)
        a += 2
    else:
        return None
    out = []
    for r in (6, 7):
        out.append(
            reg[r] if r in reg else (_read_regs(d, at, r, max(0, at - WALK * 2)) or (None, None))
        )
    return out + list(reversed(push))


def marks(text):
    """서식 문자열의 마크업 목록 → `[(문자 위치, '%c'|'%s'|'%d')]`."""
    return [(m.start(), m.group(0)) for m in MARK.finditer(text)]


def pairs_of(text, args):
    """**주입 쌍** → `[(마크업 번호, 글자, 앞바이트를 만든 오프셋, 뒷바이트를 만든 오프셋)]`.

    ⚠ 인자열이 마크업과 안 맞으면 빈 목록이다 — 「모르면 안 건드린다」.
    """
    mk = marks(text)
    if args is None or len(args) != len(mk):
        return []
    for (_p, kind), (v, _off) in zip(mk, args, strict=True):
        if v is None:  # 못 읽은 인자 — 쌍만 아니면 상관없다
            continue
        if kind == "%c" and not 0 <= v < 0x100:
            return []
        if kind in ("%s", "%d") and v < 0x100:
            return []  # 인자가 밀렸다 — 우리가 잘못 읽은 것이다
    out = []
    for i in range(len(mk) - 1):
        (p0, k0), (p1, k1) = mk[i], mk[i + 1]
        if k0 != "%c" or k1 != "%c" or p1 != p0 + 2:
            continue  # 붙어 있지 않으면 쌍이 아니다
        (v0, o0), (v1, o1) = args[i], args[i + 1]
        if v0 not in LEAD or v1 != ESC:
            continue
        try:
            ch = bytes([v0, v1]).decode("cp932")
        except UnicodeDecodeError:
            continue
        out.append((i, ch, o0, o1))
    return out


def restore(text, pairs):
    """쌍을 실제 글자로 되돌린 **정본 JP** 와, 되돌릴 창 번호 → `(jp, [창 번호])`.

    창 번호 = 그 쌍 **앞에 있는 `%c` 의 수**. `reinsert` 가 그 창의 꼬리에 쌍을 되돌리면
    마크업 **번호가 그대로**라 인자 순서가 안 바뀐다(구조 계약 ②).
    """
    if not pairs:
        return text, []
    mk = marks(text)
    out, tails, shift = text, [], 0
    for i, ch, *_rest in sorted(pairs):
        # 🔴 창 번호는 **지워 가는 중간 결과**에서 센다. 원본에서 세면 앞 쌍이 지워진 만큼
        #    어긋나 **뒤 쌍이 다른 창에 붙는다**(실측: 두 쌍짜리 블록에서 2·6 이 나왔는데
        #    옳은 값은 2·4 였다 — 이름칸 쌍이 본문 창으로 갔다).
        p = mk[i][0] - shift
        tails.append(out[:p].count("%c"))
        out = out[:p] + ch + out[p + 4 :]
        shift += 4 - len(ch)
    return out, tails


def reinsert(built, tails):
    """되돌린 쌍을 **같은 창 꼬리**에 다시 넣는다 — `%c` 총수·순서가 원본과 같아진다."""
    if not tails:
        return built
    segs = built.split("%c")
    for w in tails:
        if w >= len(segs):
            return None  # 조판이 창을 잃었다 — 넣지 않는다
        segs[w] += "%c%c"
    return "%c".join(segs)


def arg_words(d, args, pairs):
    """주입 인자를 **공백으로** 바꾸는 명령 패치 → `[(오프셋, 옛 워드, 새 워드)]`.

    ⚠ 한 명령이 **다른 인자도 만들면** 그 자리는 안 고친다(레지스터 재사용). 고치면
      엉뚱한 인자가 공백이 되어 창 전환·색이 어긋난다.
    """
    want = set()
    for _i, _ch, o0, o1 in pairs:
        want.update((o0, o1))
    if None in want:
        return None
    for off, (_v, o) in enumerate(args):
        if o in want and args[off][0] not in LEAD and args[off][0] != ESC:
            return None  # 같은 명령이 제어코드도 만든다
    out = []
    for off in sorted(want):
        w = _w(d, off)
        if w is None:
            return None
        n = (w >> 8) & 0xF
        if w >> 12 not in (0xE, 0x9):  # mov #imm,Rn · mov.w @(d,pc),Rn
            return None
        out.append((off, w, 0xE000 | (n << 8) | SPACE))
    return out


def site_key(path, off):
    return f"{path}@{off:#x}"


def load_canon():
    """정본 → `{열쇠: {glyphs, words}}`. 없으면 빈 것."""
    if not os.path.exists(CANON):
        return {}
    with open(CANON, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def verify_sites(d, entries, sites, path=""):
    """🔴 **쓰기 사전조건** — 얼린 정본이 아직 이미지와 같은가(체크리스트 2).

    자리가 어긋난 채로 쓰면 **엉뚱한 명령을 공백으로 바꾼다** — 창 전환이나 색 인자가
    날아가 화면이 조용히 망가진다. 그래서 셋을 다 본다:
      ① 그 블록이 아직 그 오프셋에 있다  ② 마크업 자리에 `%c%c` 가 붙어 있다
      ③ 고칠 명령의 **옛 워드**가 그대로다
    """
    by = {int(e["file_offset"], 16): e for e in entries}
    for off, site in sites.items():
        e = by.get(off)
        assert e is not None, f"{path} 주입 자리 0x{off:X}: 블록이 없다 — 정본을 다시 얼려라"
        mk = marks(e.get("text", ""))
        for i, ch in site["glyphs"].items():
            i = int(i)
            assert i + 1 < len(mk), f"{path} 0x{off:X}: 마크업 {i} 가 없다"
            (p0, k0), (p1, k1) = mk[i], mk[i + 1]
            assert k0 == k1 == "%c" and p1 == p0 + 2, f"{path} 0x{off:X}: 마크업 {i} 가 쌍이 아니다"
            assert len(ch) == 1, f"{path} 0x{off:X}: 되살릴 글자가 하나가 아니다"
        for a, (w0, _w1) in site["words"].items():
            a = int(a, 16)
            assert _w(d, a) == int(w0, 16), (
                f"{path} 0x{off:X}: 명령 0x{a:X} 가 {int(w0, 16):#06x} 가 아니다 — 정본이 낡았다"
            )


def scan(d, entries):
    """그 파일의 주입 자리 → `[(entry, pairs, words)]`. 코드로 확정된 것만."""
    out = []
    for e in entries:
        text = e.get("text", "")
        if "%c%c" not in text:
            continue
        ptrs = e.get("ptr_at") or []
        if len(ptrs) != 1:
            continue
        args = args_of(d, int(ptrs[0], 16) if isinstance(ptrs[0], str) else ptrs[0])
        pairs = pairs_of(text, args)
        if not pairs:
            continue
        words = arg_words(d, args, pairs)
        if not words:
            continue
        out.append((e, pairs, words))
    return out


def _pretty(doc):
    """가장 안쪽 표는 **한 줄로** 접어 쓴다 — 그냥 `indent` 로 뽑으면 값 하나가 다섯 줄이 된다."""
    out = ["{"]
    keys = list(doc)
    for n, k in enumerate(keys):
        v = doc[k]
        tail = "" if n == len(keys) - 1 else ","
        if k == "_doc":
            out.append(f" {json.dumps(k)}: [")
            for i, line in enumerate(v):
                out.append(
                    f"  {json.dumps(line, ensure_ascii=False)}" + ("," if i < len(v) - 1 else "")
                )
            out.append(f" ]{tail}")
            continue
        out.append(f" {json.dumps(k)}: {{")
        items = list(v.items())
        for i, (a, b) in enumerate(items):
            c = "" if i == len(items) - 1 else ","
            out.append(f"  {json.dumps(a)}: {json.dumps(b, ensure_ascii=False)}{c}")
        out.append(f" }}{tail}")
    out.append("}")
    return "\n".join(out) + "\n"


def main():
    freeze = "--freeze" in sys.argv
    common.verify_source()
    _f, mm = common.open_image()
    from patch_scn import SCN_RE, load

    found = {}
    for path, lba, size in common.iso_files(mm):
        if not SCN_RE.match(path):
            continue
        got = load(path)
        if not got:
            continue
        d = bytes(common.read_extent(mm, lba, size))
        for e, pairs, words in scan(d, got[1]):
            off = int(e["file_offset"], 16)
            found[site_key(path, off)] = {
                "file": path,
                "at": f"{off:#x}",
                # 마크업 번호 → 되살릴 글자
                "glyphs": {str(i): ch for i, ch, _a, _b in pairs},
                # 고칠 명령: 오프셋 → [옛 워드, 새 워드]
                "words": {f"{o:#x}": [f"{w0:#06x}", f"{w1:#06x}"] for o, w0, w1 in words},
            }
            glyphs = "".join(ch for _i, ch, _a, _b in pairs)
            where = " ".join(f"{o:#x}" for o, _a, _b in words)
            print(f"  {path} 0x{off:X}  {glyphs}  명령 {where}")
    mm.close()
    _f.close()
    print(f"주입 자리 {len(found)}곳")
    if freeze:
        doc = {
            "_doc": [
                "**주입 `%c` 쌍의 정본** — `tools/inject_pairs.py --freeze` 가 찍는다.",
                "둘째 바이트가 0x5C 인 SJIS 글자를 콜사이트 인자로 넘기는 자리다(모듈 주석).",
                "🔴 제안이 아니라 정본이다 — 빌드는 이 값과 이미지가 아직 같은지 대조한다.",
                "⚠ 원문은 안 담는다 — 파일·블록 오프셋·마크업 번호·글자 하나·명령 워드뿐이다.",
            ]
        }
        doc.update(dict(sorted(found.items())))
        with open(CANON, "w", encoding="utf-8") as fh:
            fh.write(_pretty(doc))
        print(f"  ✅ 정본에 얼렸다 — {os.path.relpath(CANON, common.GAME_DIR)}")
    else:
        print("  (`--freeze` 로 정본에 얼린다)")


if __name__ == "__main__":
    main()
