#!/usr/bin/env python3
"""**메시지 밖 바이트 보존 게이트**(11-22 마스터 「3장 요르도항구의 어부가 돌아오지 않아」 — 씬 106 스엘 어부의 이야기 깃발 세트 `14 07 01` 의 피연산자 `01` 이
「줄 첫 빈 행 제거」 패치에 걸려 `18` 로 바뀌었다. 깃발이 엉뚱한 0x1807 로 세워져 요르도 어부 귀환 조건이 영영 안 섰다. 빌드는 성공하고 단위 시험도 통과했다).

원판 씬 블록에서 **메시지 밖**(스크립트·코드 자리) 바이트는 번역이 건드릴 까닭이 거의 없다 — 건드리는 건 아래 알려진 갈래뿐이다.
구운 롬의 같은 씬 블록과 대조해, 같은 자리 바이트가 달라진 구간(run)을 갈래로 나눠 셈한다:

  A 점프 피연산자(`0F lo hi`)      — `remap_page_jumps` 가 새 쪽 머리로 옮긴다
  B 블록 머리 진입 점프(+1..2)      — `glyphdyn`/`splitload` 가 꼬리로 보낸다
  C `JSR $5815` 훅 자리            — 나레이션 게이트·시각표·대사창 단계가 코드를 갈아 낀다
  D 한 글자 화자 머리(男·女·娘)     — 이름칸을 꼬리로 뺀다
  E 줄 첫 빈 행 제거(`01`→`18`)     — 앞 바이트가 종료·쪽 옵코드일 때만
  F 일본식 부호(`81 42/41`→반각)    — `PUNCT_SITES`
  그밖                              — 기준선(`script/gap_baseline.json`)에 오른 것만 허용. 늘면 실패, 새 자리는 사유를 devlog 에 적고 `--freeze`.

🔴 **어느 갈래든 3바이트 옵코드(`10~15`)의 피연산자 꼬리를 바꾸는 건 실패**다(기준선으로도 못 덮는다) — 깃발·점프 피연산자가 달라지면 이야기가 조용히 막힌다(`0F` 점프 피연산자만 A 로 허용).

    python3 games/pce-ed1/tools/check_gap_bytes.py [--freeze]      # 구운 이미지(work/build/<꼬리표>/ed1.iso) 필요
"""

import json
import mmap
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers
import messages as M
import translate as T

BASE_FILE = Path(__file__).resolve().parent.parent / "script" / "gap_baseline.json"
FLAG_OPS = range(0x10, 0x16)


def built_track(iso: Path) -> bytes:
    with open(iso, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return b"".join(
            mm[(common.T2_SECTOR + rel) * common.RAW + common.USER_OFF : (common.T2_SECTOR + rel) * common.RAW + common.USER_OFF + common.USER]
            for rel in range(common.T2_LEN)
        )


def runs_of(o: bytes, n: bytes, inmsg: bytearray) -> list[tuple[int, int]]:
    runs: list[list[int]] = []
    for i in range(min(len(o), len(n))):
        if inmsg[i] or o[i] == n[i]:
            continue
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    return [(a, b) for a, b in runs]


def classify(o: bytes, n: bytes, a: int, b: int) -> str:
    # A — 0F 점프 피연산자
    if b - a <= 1 and ((a >= 1 and o[a - 1] == M.JUMP) or (a >= 2 and o[a - 2] == M.JUMP)):
        return "A"
    # B — 블록 머리 진입 점프
    if a in (1, 2) and o[0] == 0x4C:
        return "B"
    # C — JSR $5815 훅
    if (a >= 1 and o[a - 1] == 0x20 and o[a : a + 2] == b"\x15\x58") or o[max(0, a - 3) : b + 1].find(b"\x20\x15\x58") >= 0:
        return "C"
    # C2 — 코드 훅(JSR·NOP 채움으로 코드 몇 줄을 갈아 끼움 — 씬 2·18 나레이션 게이트 등)
    if bytes(n[a : b + 1]).find(b"\xea\xea\xea") >= 0 or (a >= 1 and n[a - 1] == 0x20) or 0x20 in n[a : min(b + 1, a + 2)]:
        return "C"
    # H — 3바이트 옵코드를 꼬리로 옮기고 그 자리를 `0F` 점프로(씬 69 합류 효과음) — 점프 목적지 앞쪽 8바이트 안에 원래 옵코드 바이트가 그대로 있어야 한다
    if b - a == 2 and n[a] == M.JUMP:
        tgt = (n[a + 1] | n[a + 2] << 8) - M.BASE
        if 0 <= tgt < len(n) and bytes(o[a : b + 1]) in bytes(n[tgt : tgt + 10]):
            return "H"
    # D — 한 글자 화자 머리(1F 이름 04) 앞 2~3바이트
    if o[a] == 0x1F and b - a == 2 and b + 1 < len(o) and o[b + 1] == 0x04:
        return "D"
    # E — 줄 첫 빈 행 제거: `01`→`18`
    if a == b and o[a] == T.NL and n[a] == T.NOP_OP and a >= 3 and o[a - 1] in T.BLANK_ROW_BEFORE and o[a - 2] not in FLAG_OPS:  # 🔴 `1x 07 01`(깃발 피연산자)는 빈 행이 아니다
        return "E"
    if a == b and o[a] == T.NL and n[a] == T.NOP_OP and a >= 4 and o[a + 1] == 0x09 and o[a + 3] == 0x1D:
        return "E"
    # F — 일본식 부호
    if b - a == 1 and bytes(o[a : b + 1]) in (b"\x81\x42", b"\x81\x41") and bytes(n[a : b + 1]) in (b"\xf0\x27", b"\xf0\x25"):
        return "F"
    return "?"


def operand_tail_hit(o: bytes, a: int, b: int) -> bool:
    """diff 가 3바이트 옵코드(10~15)의 피연산자 두 바이트를 건드리나 — 점프(0F)는 제외."""
    for p in range(a, b + 1):
        for k in (1, 2):
            if p - k >= 0 and o[p - k] in FLAG_OPS:
                return True
    return False


def scan(track: bytes | None = None) -> tuple[dict[str, int], list[str], list[str]]:
    """(갈래별 셈, 금지 위반 목록, 기준선 밖 「그밖」 목록)"""
    orig: dict[int, bytes] = {}
    for c in containers.scan():
        for blk in c["blocks"]:
            orig.setdefault(blk["id"], blk["data"])
    new_found = containers.scan(track if track is not None else built_track(common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"))
    count: dict[str, int] = {}
    forbidden: list[str] = []
    other: list[str] = []
    seen: set[tuple[int, int, int]] = set()
    for c in new_found:
        for blk in c["blocks"]:
            sid, n = blk["id"], blk["data"]
            o = orig.get(sid)
            if o is None:
                continue
            try:
                msgs = M.parse(o)
            except Exception:  # noqa: BLE001
                continue
            inmsg = bytearray(len(o))
            for m in msgs:
                inmsg[m.start : m.end] = b"\x01" * (m.end - m.start)
            for a, b in runs_of(o, n, inmsg):
                cls = classify(o, n, a, b)
                key = (sid, a, b)
                if key in seen:
                    continue
                seen.add(key)
                count[cls] = count.get(cls, 0) + 1
                tag = f"scn{sid:03d}+{a:#06x}"
                ctx = f"orig {o[max(0, a - 3) : b + 4].hex()} → 롬 {n[max(0, a - 3) : b + 4].hex()}"
                # 금지 — 3바이트 옵코드 피연산자 꼬리를 바꿈(점프 피연산자 A 만 예외, 훅 C 는 코드 자리라 따로)
                if cls not in ("A", "B", "C", "H") and operand_tail_hit(o, a, b) and o[a - 1] != M.JUMP:
                    forbidden.append(f"{tag} 옵코드(10~15) 피연산자 변경 {ctx}")
                if cls == "?":
                    other.append(f"{tag} {ctx}")
    return count, forbidden, other


def main() -> int:
    freeze = "--freeze" in sys.argv
    iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print(f"❌ 구운 이미지가 없다 — 빌드 먼저({iso})")
        return 1
    count, forbidden, other = scan()
    print("메시지 밖 바이트 대조 — " + " ".join(f"{k}={v}" for k, v in sorted(count.items())))
    base = set(json.loads(BASE_FILE.read_text("utf-8"))) if BASE_FILE.exists() else set()
    keys = {x.split(" orig ")[0] for x in other}
    bad = 0
    for f in forbidden:
        print(f"  ✘ {f}")
        bad += 1
    new = sorted(keys - base)
    for k in new:
        print(f"  ✘ 기준선 밖 변경 {k} — 의도한 패치면 사유를 devlog 에 적고 --freeze")
        bad += 1
    if freeze:
        if forbidden:
            print("  ⚠ 금지 위반이 있어 기준선을 못 갱신한다")
            return 1
        BASE_FILE.write_text(json.dumps(sorted(keys), ensure_ascii=False, indent=1) + "\n", "utf-8")
        print(f"  ✓ 기준선 {len(keys)}건 기록")
        return 0
    gone = sorted(base - keys)
    if gone:
        print(f"  ℹ 기준선에서 사라진 {len(gone)}건 — 고쳐졌으면 --freeze 로 내린다")
    print("✅ 메시지 밖 바이트 보존" if not bad else f"❌ {bad}건")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
