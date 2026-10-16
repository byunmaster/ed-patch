"""패키지 안의 대본 덩이를 새 내용으로 다시 싣는다 — **안 고친 덩이는 자리도 바이트도 그대로**.

덩이들은 메시지 표 뒤에 이어 붙어 있고(`package.py`), 맨 뒤에 **0xFF 채움**이 다음 데이터 앞까지 이어진다(= 꼬리 자유 공간).
고친 덩이는 ① 자기 칸에 들어가면 **제자리**(남는 꼬리는 채움) ② 안 들어가면 **칸을 비우고 자유 공간 어딘가로 이사**
(꼬리 · 비운 칸 중 들어가는 가장 작은 곳, 같으면 앞쪽) — 표 항목(13비트 주소 + 뱅크 가산)만 새 자리로 바꾼다.
들어갈 데가 없으면 빌드가 멈춘다. 이사해도 안 고친 덩이는 안 움직인다(**위치가 계약인 구간**을 건드리지 않는다).
⚠ 칸 안의 남는 꼬리는 0xFF — 디코더는 줄 수로 멈추므로 안 읽는다(게임은 덩이의 끝을 모른다). 그래서 **되읽기 검사는 길이를 줘서 푼다**.
🔴 안 고친 덩이는 원본 바이트를 그대로 싣는다(우리 인코더가 조금 촘촘해서, 다시 누르면 바꿀 까닭 없는 바이트가 바뀐다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lz
import package

FILL = 0xFF


class RepackError(Exception):
    pass


def text_region(pkg: bytes) -> tuple[int, int, list[tuple[int, int]]]:
    """(첫 덩이 시작, 채움 끝 = 쓸 수 있는 끝, 실제 덩이 목록 — 끝 표시 제외)."""
    ch = package.chunks(pkg)
    real = [(a, b) for a, b in ch if pkg[a : a + 8] != package.SENTINEL]
    sent = [a for a, b in ch if pkg[a : a + 8] == package.SENTINEL]
    if len(sent) != 1 or real[-1][1] != sent[0]:
        raise RepackError("끝 표시(0xFF 채움)가 마지막 덩이 바로 뒤에 하나여야 한다")
    end = sent[0]
    while end < len(pkg) and pkg[end] == FILL:
        end += 1
    return real[0][0], end, real


def repack(pkg: bytes, new: dict[int, bytes]) -> tuple[bytes, dict[int, int]]:
    """new = {원래 덩이 시작 오프셋: 새로 풀린 내용}. (새 패키지, {옛 시작: 새 시작} — 고친 덩이만, 제자리면 같은 값)."""
    _first, limit, real = text_region(pkg)
    T, tab = package.msg_table(pkg)
    slot_end = dict(real)
    sentinel_old = real[-1][1]
    blobs = {}
    for a, d in new.items():
        if a not in slot_end:
            raise RepackError(f"덩이 시작 {a} 가 표에 없다")
        blob = lz.encode(d)
        back, _ = lz.decode(blob + bytes(8), 0, len(d))
        assert back == d, "인코더 왕복 불일치"
        blobs[a] = blob
    out = bytearray(pkg)
    free: list[tuple[int, int]] = [(sentinel_old, limit)]
    place: dict[int, int] = {}
    deferred = []
    for a in sorted(blobs):
        b = slot_end[a]
        if len(blobs[a]) <= b - a:
            place[a] = a
            if len(blobs[a]) < b - a:
                free.append((a + len(blobs[a]), b))
        else:
            deferred.append(a)
            free.append((a, b))  # 칸을 비운다
    for a in sorted(deferred, key=lambda x: (-len(blobs[x]), x)):
        n = len(blobs[a])
        cand = sorted((e - s, s, e) for s, e in free if e - s >= n)
        if not cand:
            raise RepackError(
                f"덩이 {a}({n}B)가 들어갈 자유 공간이 없다 — 가장 큰 빈 곳 {max((e - s for s, e in free), default=0)}B"
            )
        _w, s, e = cand[0]
        free.remove((s, e))
        place[a] = s
        if s + n < e:
            free.append((s + n, e))
    for a, s in place.items():
        out[s : s + len(blobs[a])] = blobs[a]
    # 비어 있는 곳은 전부 0xFF — 쓰인 칸의 꼬리 · 비운 칸 · 꼬리 공간
    used = sorted((s, s + len(blobs[a])) for a, s in place.items())
    free_now = [(s, e) for s, e in free if e > s]
    for s, e in free_now:
        out[s:e] = bytes([FILL]) * (e - s)
    # 끝 표시 항목 — 꼬리 쪽에 쓴 덩이가 있으면 그 뒤 첫 채움으로
    tail_used = [e for s, e in used if s >= sentinel_old]
    sent_new = max(tail_used, default=sentinel_old)
    remap = {a: s for a, s in place.items()}
    remap[sentinel_old] = sent_new
    for i, p in enumerate(tab):
        if p in remap and remap[p] != p:
            q = remap[p]
            bank, addr = q >> 13, q & 0x1FFF
            out[T + 2 * i] = addr & 0xFF
            out[T + 2 * i + 1] = (bank << 5) | (addr >> 8)
    return bytes(out), place
