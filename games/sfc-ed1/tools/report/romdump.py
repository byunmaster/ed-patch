#!/usr/bin/env python3
"""**롬에서 뽑은 번호별 대사집 짝 표** — 원판(JP 원본 롬)과 한글(지금 HEAD 제품 롬)에서 메시지 번호마다 실제 바이트를 읽어 디코드해 `pairs.tsv` 로 나란히 둔다.

    python3 games/sfc-ed1/tools/report/romdump.py [--out <pair 폴더>] [--kr <제품 롬>] [--kr-manifest <manifest.json>]

대본 JSON 이 아니라 구운 롬이다(마스터 10-20 「A 원문캡쳐는 중단 — 롬에서 번호별 대사집」). 촬영·에뮬레이터 없이 롬 파일만 읽는다.
범위: 메시지 포인터 표 넷 전부 — 대사(main 2,906 = 0000~0B59) · 전투·행동(alt2 343 = 2000~2156) · 시스템(alt1 90 = 6000~6059) · 필드 문구 등(alt3 19 = 8000~8012).

## 읽는 법(엔진과 같은 규칙)
 · 포인터 표(`text.MSG_TABLES`, 3바이트 LoROM 주소)에서 번호의 시작 오프셋을 읽고, **메시지 끝 `$FF`**(또는 `$E4`)까지 **실행되는 경로 그대로** 따라간다.
 · 쪽 넘김 `$E0` = `⏎` · 줄바꿈 `$CF` = `↵` · 메시지 끝 = `■` · 이름·도구 치환 `{name:D6}`·`{num:DC}` · 사전 `{글자}` · 조사 `{josa:이/가}` · 나머지 제어 `<이름 인자>`.
 · 호출 `$FC`(상대)·`$F9`(절대)는 호출 대상을 **펼쳐** `⟨호출: …⟩`, 호출표 `$FD`는 슬롯마다 `⟨분기1: …⟩⟨분기2: …⟩`, 조건(`$F0~$F7`)이 붙은 점프·호출은 `⟨조건 IF_SET:07 → …⟩`(참인 경로)로 펼친 뒤 아래로 이어 읽는다.
 · 점프표 `$FB` 는 슬롯마다 `⟨선택1: …⟩…` 로 펼치고 끝낸다. 무조건 점프 `$FA` 는 그 자리로 이어 읽는다(`→`).
## 표시(자동)
 원판만 = 원판엔 글자가 있고 한글이 비었다 · 한글만 = 반대 · 둘 다 빔 = 둘 다 글자가 없다(제어만) · 포인터 공유 = 그 롬의 같은 표에서 다른 번호와 포인터가 같다(원판·한글 중 어느 한쪽이라도).
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import text  # noqa: E402,I001  (common 보다 먼저 — shared/text 와 이름이 겹친다)
import common  # noqa: E402
import encode  # noqa: E402

MAX_OUT = 12000  # 한 번호의 출력 상한(글자) — 넘으면 `…[잘림]`
MAX_DEPTH = 4
COND = set(range(0xF0, 0xF8))  # 조건 — 거짓이면 다음 항목을 건너뜀


class Rom:
    def __init__(self, kind: str, data: bytes, kr_manifest: dict | None = None):
        self.kind, self.d = kind, data
        self.tables = {}
        for name, (addr, n) in text.MSG_TABLES.items():
            base = common.snes2off(addr)
            self.tables[name] = [
                common.snes2off(data[base + 3 * i] | (data[base + 3 * i + 1] << 8) | (data[base + 3 * i + 2] << 16)) for i in range(n)
            ]
        self.anchors = {p for t in self.tables.values() for p in t}
        if kind == "jp":
            self.res = text.resolver(data)
        else:
            import namesrc

            self.dm = namesrc.dict_map()
            self.rep = kr_manifest.get("repertoire") or _find(kr_manifest, "repertoire")
            self.raw = {v: k for k, v in encode.KR_TABLE.items() if v < 0xCF and k != "\n"}
            if not self.rep:
                raise SystemExit("한글 manifest 에 repertoire 가 없다")

    # ── 항목 하나 읽기 → (문자열, 다음 오프셋, 종류, 코드, 인자 바이트) ──
    def item(self, i: int):
        d = self.d
        c = d[i]
        if self.kind == "kr" and c in encode.LEADS and i + 1 < len(d):
            nx = d[i + 1]
            if c == encode.JOSA_LEAD and nx >= encode.JOSA_BASE:
                k = nx - encode.JOSA_BASE
                return "{josa:" + (encode.JOSA_PAIRS[k] if k < len(encode.JOSA_PAIRS) else str(k)) + "}", i + 2, "char", c, b""
            idx = encode.LEADS.index(c) * 256 + nx
            ch = self.rep[idx] if idx < len(self.rep) else ""
            return (ch or f"[{c:02X}{nx:02X}]"), i + 2, "char", c, b""
        if c < 0xD0:
            if c == text.NEWLINE:
                return "↵", i + 1, "nl", c, b""
            s = text.TABLE[c] if self.kind == "jp" else self.raw.get(c, f"[{c:02X}]")
            return s, i + 1, "char", c, b""
        if c in text.DICT_TABLES:
            arg = d[i + 1]
            idx = arg & 0x7F if c == 0xD0 else arg
            if self.kind == "jp":
                try:
                    s = "{" + text.decode(self.res(c, idx), self.res, 1) + "}"
                except (IndexError, ValueError, KeyError):
                    s = f"<{c:02X} {arg:02X}>"
            else:
                e = self.dm.get(f"{c:02X}:{idx:02X}") or {}
                s = "{" + (e.get("kr") or f"{c:02X}:{idx:02X}") + "}"
            return s, i + 2, "dict", c, bytes([arg])
        if c < 0xE0:
            return (f"{{num:{c:02X}}}" if c == 0xDC else f"{{name:{c:02X}}}"), i + 1, "subst", c, b""
        k = text.ARGLEN.get(c, 0)
        if c in (0xFB, 0xFD):  # 슬롯 열 — 다음 앵커(포인터 목표·분기 목표)까지만(script._parse 와 같은 규칙)
            for j in range(1, k + 1):
                if (i + j) in self.anchors:
                    k = j - 1
                    break
        return "", i + 1 + k, "ctrl", c, d[i + 1 : i + 1 + k]

    def rel(self, i: int, a: bytes) -> int:
        return script_rel16(i, a[0] | (a[1] << 8))


def script_rel16(off: int, o16: int) -> int:
    a = common.off2snes(off)
    dd = o16 if o16 < 0x8000 else o16 - 0x10000
    return common.snes2off((a & 0xFF0000) | ((a + dd) & 0xFFFF))


def _find(d, key):
    if isinstance(d, dict):
        if key in d:
            return d[key]
        for v in d.values():
            r = _find(v, key)
            if r:
                return r
    return None


def walk(rom: Rom, start: int, depth: int = 0, seen: frozenset = frozenset(), until_return: bool = False) -> str:
    """start 부터 메시지 끝(`$FF`·`$E4`) 또는 (호출 안이면) `$FE` 까지 실행 경로대로 펼친다."""
    out: list[str] = []
    i = start
    pend = None  # 직전 조건
    steps = 0
    d = rom.d
    visited: set[int] = set()
    while i < len(d) and steps < 4000 and sum(map(len, out)) < MAX_OUT:
        steps += 1
        if i in seen or i in visited:  # 같은 경로에서 이미 지난 항목 — 되돌이(반복 메뉴·상점 루프)는 한 번만 펼친다
            out.append("⟨반복⟩")
            break
        visited.add(i)
        s, nxt, kind, c, args = rom.item(i)
        if kind in ("char", "nl", "dict", "subst"):
            out.append(s)
            pend = None
            i = nxt
            continue
        name = text.CTRL_NAME.get(c, f"{c:02X}")
        if c == 0xFF:
            out.append("■")
            break
        if c == 0xE4:
            out.append("■4")
            break
        if c == 0xE0:
            out.append("⏎")
            i = nxt
            pend = None
            continue
        if c == 0xFE:
            if until_return:
                break
            out.append("⟨RETURN⟩")
            break
        if c in COND:
            pend = f"{name}:{args.hex()}"
            nc = d[nxt] if nxt < len(d) else 0
            if nc not in (0xFA, 0xFC, 0xF9):  # 다음이 점프·호출이면 아래 `⟨조건 … → …⟩` 가 대신한다
                out.append(f"⟨{pend}⟩")
            i = nxt
            continue
        if c in (0xFA, 0xFC, 0xF9):
            if c == 0xF9:
                addr = args[0] | (args[1] << 8) | (args[2] << 16)
                tgt = common.snes2off(addr) if (addr & 0x8000) else -1
            else:
                tgt = rom.rel(i, args)
            ok = 0 <= tgt < len(d) and depth < MAX_DEPTH
            if c == 0xFA:
                if pend:  # 조건 점프 — 참인 경로를 펼치고 아래로 이어 읽는다
                    out.append("⟨조건 " + pend + " → " + (walk(rom, tgt, depth + 1, seen | visited) if ok else "…") + "⟩")
                    pend = None
                    i = nxt
                    continue
                out.append("→")
                if not ok:
                    break
                i = tgt
                seen = seen | visited
                continue
            # 호출
            body = walk(rom, tgt, depth + 1, seen | visited, True) if ok else "…"
            out.append(("⟨조건 " + pend + " 호출: " if pend else "⟨호출: ") + body + "⟩")
            pend = None
            i = nxt
            continue
        if c in (0xFD, 0xFB):
            k = len(args)
            alts = []
            for n, b in enumerate(args, 1):
                tgt = i + b
                if tgt < i + 1 + k or tgt >= len(d):  # 슬롯 열 뒤가 아니면 죽은 슬롯
                    continue
                if depth >= MAX_DEPTH:
                    alts.append(f"⟨{'분기' if c == 0xFD else '선택'}{n}: …⟩")
                    continue
                alts.append(f"⟨{'분기' if c == 0xFD else '선택'}{n}: " + walk(rom, tgt, depth + 1, seen | visited, c == 0xFD) + "⟩")
            out.append("".join(alts) if alts else f"<{name} {args.hex()}>")
            pend = None
            if c == 0xFB:
                break
            i = nxt
            continue
        out.append(f"<{name}" + (" " + args.hex() if args else "") + ">")
        pend = None
        i = nxt
    t = "".join(out)
    if len(t) > MAX_OUT:
        t = t[:MAX_OUT] + "…[잘림]"
    return t


def has_text(s: str) -> bool:
    """사람이 읽을 글자가 있나 — 호출·분기·조건 머리말·제어·변수 자리표를 걷어 낸다."""
    import re

    t = re.sub(r"⟨(?:조건 [^⟩]*?(?:→|호출:)|호출:|분기\d+:|선택\d+:|[A-Z_0-9]+:[0-9a-f]+⟩?)\s?", "", s)
    t = re.sub(r"<[^>]*>|\{(?:name|num|josa):[^}]*\}|[⏎↵■→⟩⟨]|■4|\[잘림\]|반복|순환|RETURN", "", t)
    return bool(t.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    root = common.GAME_DIR.parents[1]
    ap.add_argument("--out", type=Path, default=root / ".local" / "work" / "inbox" / "sfc-ed1" / "sweep" / "pair")
    ap.add_argument("--jp", type=Path, default=common.ORIG_ROM)
    ap.add_argument("--kr", type=Path, default=None, help="한글 제품 롬(기본: work/build 의 제품 칸)")
    a = ap.parse_args()
    slot = None
    if a.kr is None:
        cands = [m.parent for m in sorted(common.BUILD_DIR.glob("*/manifest.json")) if m.parent.name not in ("test-debug", "debug") and list(m.parent.glob("*.sfc"))]
        if not cands:
            raise SystemExit("제품 롬 빌드 칸이 없다 — `sh scripts/check.sh` 로 굽거나 --kr 로 지정")
        slot = cands[0]
        a.kr = next(slot.glob("*.sfc"))
    else:
        slot = a.kr.parent
    man = json.loads((slot / "manifest.json").read_text(encoding="utf-8"))
    jb, kb = a.jp.read_bytes(), a.kr.read_bytes()
    jp, kr = Rom("jp", jb), Rom("kr", kb, man)
    base = {"main": 0, "alt2": 0x2000, "alt1": 0x6000, "alt3": 0x8000}
    rows = []
    cnt = {"원판만": 0, "한글만": 0, "둘 다 빔": 0, "포인터 공유": 0}
    shared_j = {n: {p for p in set(t) if t.count(p) > 1} for n, t in jp.tables.items()}
    shared_k = {n: {p for p in set(t) if t.count(p) > 1} for n, t in kr.tables.items()}
    total = 0
    for name in ("main", "alt2", "alt1", "alt3"):
        for i in range(len(jp.tables[name])):
            total += 1
            pj, pk = jp.tables[name][i], kr.tables[name][i]
            js, ks = walk(jp, pj), walk(kr, pk)
            hj, hk = has_text(js), has_text(ks)
            marks = []
            if pj in shared_j[name] or pk in shared_k[name]:
                marks.append("포인터 공유")
            if hj and not hk:
                marks.append("원판만")
            elif hk and not hj:
                marks.append("한글만")
            elif not hj and not hk:
                marks.append("둘 다 빔")
            for m in marks:
                cnt[m] += 1
            rows.append((f"{base[name] + i:04X}", js, ks, ",".join(marks)))
    a.out.mkdir(parents=True, exist_ok=True)

    def cell(s: str) -> str:
        return s.replace("\t", " ").replace("\n", " ").replace("\r", "")

    with (a.out / "pairs.tsv").open("w", encoding="utf-8") as f:
        f.write("번호\t원판\t한글\t표시\n")
        for r in rows:
            f.write("\t".join(cell(x) for x in r) + "\n")
    info = {
        "jp_rom": str(a.jp.name),
        "jp_sha1": hashlib.sha1(jb).hexdigest(),
        "kr_rom": str(a.kr.name),
        "kr_sha1": hashlib.sha1(kb).hexdigest(),
        "total": total,
        "표시별": cnt,
    }
    (a.out / "romdump.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(info, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
