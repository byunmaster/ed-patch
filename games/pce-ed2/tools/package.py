"""씬 패키지 — 머리표 · 메시지 포인터 표 · 대본 덩이(LZ 스트림) 파서.

패키지(128섹터 간격, 보통 78섹터 로드)는 뱅크 하나 단위로 CD RAM 에 올라가고(`$41` = 첫 뱅크),
맨 앞 8KB 뱅크의 `$8000` 에 **3바이트 머리표**(`4c`로 시작하는 JMP 3개 뒤)가 있다.
엔진 루틴 `$4743`(뱅크 0x68)이 항목 n 을 `[상대 뱅크][lo][hi]` 로 읽는다 — 3n 위치.
포인터 부호화(`$46EF`): `hi` 윗 3비트 = 첫 뱅크에서 더할 뱅크 수, 아래 5비트 = 뱅크 안 `$8000|hi<<8|lo` 주소.
→ 패키지 안 바이트 오프셋 = 뱅크번호*8192 + ((hi&0x1F)<<8 | lo).
머리표 항목 4 = **메시지 포인터 표**(2바이트씩, `$AF` = 메시지 번호). 번호 하나가 LZ 덩이 하나를 가리키고
(`$7DA2` → `$7D84` → `$5796`), 줄은 덩이 안에서 앞에서부터 `00` 을 세어 고른다.
덩이의 끝 = 다음 덩이 시작(덩이는 이어 붙어 있고 각자 링을 새로 시작한다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import lz

BANK = 8192
MSG_ENTRY = 4  # 머리표 항목 번호 — 메시지 포인터 표


def ptr(b: bytes, i: int) -> tuple[int, int]:
    """(상대 뱅크 항목, 바이트 오프셋) — 3바이트 머리표 항목 i."""
    rel_bank, lo, hi = b[3 * i], b[3 * i + 1], b[3 * i + 2]
    return rel_bank, (rel_bank + (hi >> 5)) * BANK + ((hi & 0x1F) << 8 | lo)


def msg_table(pkg: bytes) -> tuple[int, list[int]]:
    """(표 위치, 메시지 번호별 덩이 시작 오프셋 — 0 = 비었음)."""
    _rb, T = ptr(pkg, MSG_ENTRY)
    limit = len(pkg)
    out = []
    i = 0
    while T + 2 * i + 1 < limit:
        lo, hi = pkg[T + 2 * i], pkg[T + 2 * i + 1]
        p = (hi >> 5) * BANK + ((hi & 0x1F) << 8 | lo)
        out.append(p)
        if p > T:
            limit = min(limit, p)
        i += 1
        if T + 2 * i >= limit:
            break
    return T, out


def chunks(pkg: bytes) -> list[tuple[int, int]]:
    """(시작, 끝) — 중복 제거 · 시작 순. 마지막 덩이의 끝은 패키지 끝."""
    T, tab = msg_table(pkg)
    starts = sorted({p for p in tab if p > T})
    ends = [
        starts[k + 1] if k + 1 < len(starts) else _last_end(pkg, starts[k])
        for k in range(len(starts))
    ]
    return list(zip(starts, ends, strict=True))


def _last_end(pkg: bytes, start: int) -> int:
    """마지막 덩이의 끝 — 뒤에 이어지는 영(0) 32바이트 런 직전(패딩)."""
    m = pkg.find(bytes(32), start)
    return len(pkg) if m < 0 else m


def decode_chunk(pkg: bytes, start: int, end: int) -> tuple[bytes, int]:
    """덩이 하나를 푼다 — 입력 위치가 end 에 닿을 때까지."""
    out = bytearray()
    last = start
    try:
        hit = None  # 끝에 닿은 토큰 — 그 토큰이 내는 바이트는 끝까지 받는다(되참조는 입력을 먼저 다 읽는다)
        for b, pos, _w, _r in lz.walk(pkg, start):
            if hit is not None and pos != hit:
                break
            out.append(b)
            last = pos
            if pos >= end:
                hit = pos
    except IndexError:
        pass
    return bytes(out), last


SENTINEL = b"\xff" * 8  # 표가 가리키는 패딩 — 마지막 덩이 뒤의 채움(표의 끝 표시)


def audit(rel: int) -> dict:
    """패키지 하나를 훑는다 — 덩이가 각자 **다음 시작에 정확히 닿으면** 포인터 표가 맞다는 뜻이다."""
    pkg = common.track_data(rel, 128)
    ok = bad = sent = lines = 0
    for a, b in chunks(pkg):
        if pkg[a : a + 8] == SENTINEL:
            sent += 1
            continue
        d, pos = decode_chunk(pkg, a, b)
        if pos == b:
            ok += 1
        else:
            bad += 1
        lines += d.count(0)
    return {"rel": rel, "ok": ok, "bad": bad, "sentinel": sent, "lines": lines}


# 마을·성 계열 패키지(앞 사본, 128섹터 간격) — 전 덩이가 정확히 닿는 것만 못 박는다.
# 뒤쪽 패키지(전투·던전 등)는 머리표 4번의 뜻이 다르거나 표가 더 길다 — 아직 모른다(status).
CLEAN = [386, 514, 642, 770, 898, 1026, 1154, 1282, 1410, 1538, 1666, 1794]


def check() -> None:
    for rel in CLEAN:
        r = audit(rel)
        assert r["bad"] == 0 and r["ok"] > 0 and r["sentinel"] == 1, (
            f"패키지 {rel} 덩이 경계 불일치: {r}"
        )
    print(f"패키지 {len(CLEAN)}개 — 덩이 경계가 전부 정확히 닿는다")


if __name__ == "__main__":
    common.verify_originals()
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        check()
    else:
        rel = int(sys.argv[1]) if len(sys.argv) > 1 else 386
        print(audit(rel))
