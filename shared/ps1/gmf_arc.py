"""GMF 아카이브(`SC*.DAT` · `M0*.DAT`) — TOC 파싱과 재배치(ED3·ED4 공통).

TOC 엔트리 32B = 이름[20] + u32 off + u32 size + u32 예약.
⚠ **off 의 단위가 파일마다 다르다** — `SC*.DAT` 은 4바이트 워드, `M01.DAT` 은 2048 섹터.
  단위를 잘못 잡으면 예외가 아니라 **빈 슬라이스**가 나와 조용히 0바이트 멤버가 된다
  (실측 2026-09-03: 595 멤버가 전부 빈 채로 통계까지 돌았다). 그래서 검증해서 고른다.
"""

import struct

ARC_UNITS = (4, 2048, 1, 2)
UNIT = 4  # SC*.DAT 의 오프셋 단위·멤버 정렬
SECTOR_DATA = 2048


class ArchiveError(Exception):
    pass


class PackError(Exception):
    pass


def arc_parse(data):
    """(unit, [(이름, 오프셋, 크기)]) — 단위는 파일 전체가 성립하는 것으로 고른다."""
    ents = []
    for i in range(0, len(data) - 31, 32):
        nm = data[i : i + 20].rstrip(b"\x00")
        if not nm or nm[0] == 0:
            break
        off, size, _ = struct.unpack("<III", data[i + 20 : i + 32])
        ents.append((nm.decode("ascii", "replace"), off, size))
    if not ents:
        raise ArchiveError("TOC 가 비었다")
    toc = len(ents) * 32
    for u in ARC_UNITS:
        offs = [o * u for _, o, _ in ents]
        if offs[0] < toc or offs != sorted(offs):
            continue
        if any(o + s > len(data) for o, (_, _, s) in zip(offs, ents, strict=True)):
            continue
        return u, [(n, o, s) for (n, _, s), o in zip(ents, offs, strict=True)]
    raise ArchiveError(f"오프셋 단위를 못 정했다 (엔트리 {len(ents)}, 길이 {len(data)})")


def arc_members(data):
    """{이름: (오프셋, 크기)} — 멤버 이름은 `..\\DATA\\FT0000.BIN` 식 원본 경로다."""
    _, ents = arc_parse(data)
    return {n: (o, s) for n, o, s in ents}


# ── 재배치 ──────────────────────────────────────────────────────────────────
# 멤버가 원본 크기를 넘으면 뒤 멤버를 밀어 자리를 만든다. 늘어난 길이가 **마지막 섹터 여유 안**이면 섹터 수가
# 안 바뀌므로 다른 파일은 안 옮긴다. 여유가 모자라면 줄어든 멤버의 꼬리 0 채움을 거둔다 — 그래도 모자라면 멈춘다.
# 🔴 안 건드린 멤버는 **바이트까지 같다**(위치만 밀린다). 끝에서 되읽어 검산한다(`verify`).


def _a4(n):
    return (n + UNIT - 1) // UNIT * UNIT


def plan(data, replacements):
    """재배치 계획(쓰지 않고 센다) — dict(sizes, grow, slack, reclaimed). 여유가 모자라면 `PackError`."""
    unit, ents = arc_parse(data)
    if unit != UNIT:
        raise PackError(f"오프셋 단위 {unit} — 이 도구는 {UNIT}B 단위 아카이브만 안다")
    names = [n for n, _, _ in ents]
    missing = set(replacements) - set(names)
    if missing:
        raise PackError(f"아카이브에 없는 멤버: {sorted(missing)[:3]}")
    sizes = {n: sz for n, _, sz in ents}
    for n, new in replacements.items():
        sizes[n] = max(sizes[n], len(new))
    slack = -len(data) % SECTOR_DATA

    def grow():
        return sum(_a4(sizes[n]) - _a4(sz) for n, _, sz in ents)

    reclaimed = 0
    if grow() > slack:
        cand = sorted(
            (
                (_a4(sz) - _a4(len(replacements[n])), n)
                for n, _, sz in ents
                if n in replacements and len(replacements[n]) < sz
            ),
            reverse=True,
        )
        for gain, n in cand:
            if grow() <= slack:
                break
            if gain <= 0:
                continue
            reclaimed += gain
            sizes[n] = len(replacements[n])
    if grow() > slack:
        raise PackError(
            f"여유 {slack}B 에 필요 {grow()}B — 이 아카이브는 섹터가 늘어난다(다른 파일을 옮겨야 한다)"
        )
    return {"sizes": sizes, "grow": grow(), "slack": slack, "reclaimed": reclaimed}


def repack(data, replacements):
    """(새 아카이브 바이트열, 계획). 안 바뀐 멤버는 바이트 그대로, 위치만 민다."""
    p = plan(data, replacements)
    _unit, ents = arc_parse(data)
    sizes = p["sizes"]
    first = ents[0][1]
    out = bytearray(data[:first])
    shift = 0
    new_ents = []
    for n, off, sz in ents:
        new_off = off + shift
        body = replacements.get(n)
        if body is None:
            body = data[off : off + sz]
        keep = sizes[n]
        if len(body) > keep:
            raise PackError(f"{n}: 새 멤버 {len(body)}B 가 계획 크기 {keep}B 보다 크다")
        chunk = bytes(body).ljust(keep, b"\x00")
        if len(out) > new_off:
            raise PackError(f"{n}: 앞 멤버가 {len(out) - new_off}B 겹친다")
        out += b"\x00" * (new_off - len(out))
        out += chunk
        new_ents.append((n, new_off, keep))
        shift += _a4(keep) - _a4(sz)
    new_len = len(data) + p["grow"]
    out += b"\x00" * (new_len - len(out))
    if len(out) != new_len:
        raise PackError(f"길이가 계획과 다르다: {len(out)} (계획 {new_len})")
    for i, (_n, off, keep) in enumerate(new_ents):
        pos = i * 32 + 20
        out[pos : pos + 8] = struct.pack("<II", off // UNIT, keep)
    out = bytes(out)
    verify(data, out, replacements, p)
    return out, p


def verify(old, new, replacements, p):
    """🔴 끝에서 되읽어 검산한다 — 「썼다」와 「다시 읽힌다」는 다르다."""
    u0, e0 = arc_parse(old)
    u1, e1 = arc_parse(new)
    if u1 != u0 or [n for n, _, _ in e1] != [n for n, _, _ in e0]:
        raise PackError("재배치 뒤 멤버 목록·단위가 달라졌다")
    if (len(new) + SECTOR_DATA - 1) // SECTOR_DATA != (len(old) + SECTOR_DATA - 1) // SECTOR_DATA:
        raise PackError("섹터 수가 바뀌었다 — 다른 파일을 옮겨야 하는 일이다")
    prev_end = e1[0][1]
    for (n, o0, s0), (_, o1, s1) in zip(e0, e1, strict=True):
        if o1 % UNIT or o1 < prev_end:
            raise PackError(f"{n}: 오프셋 {o1} 가 정렬·순서에 안 맞는다")
        prev_end = o1 + s1
        got = new[o1 : o1 + s1]
        if n in replacements:
            if got != bytes(replacements[n]).ljust(s1, b"\x00"):
                raise PackError(f"{n}: 새 멤버가 되읽은 것과 다르다")
        elif got != old[o0 : o0 + s0] or s1 != s0:
            raise PackError(f"{n}: 안 건드릴 멤버가 바뀌었다")
    first = e0[0][1]
    for i in range(len(e0)):
        if (
            old[i * 32 : i * 32 + 20] != new[i * 32 : i * 32 + 20]
            or old[i * 32 + 28 : i * 32 + 32] != new[i * 32 + 28 : i * 32 + 32]
        ):
            raise PackError("TOC 의 이름·예약 필드가 바뀌었다")
    toc_end = len(e0) * 32
    if old[toc_end:first] != new[toc_end:first]:
        raise PackError("TOC 뒤 패딩이 바뀌었다")
    if len(new) != len(old) + p["grow"]:
        raise PackError("파일 길이가 계획과 다르다")
