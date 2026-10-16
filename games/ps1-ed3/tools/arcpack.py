"""GMF 아카이브(`SC*.DAT`) **재배치** — 멤버가 원본 크기를 넘으면 뒤 멤버를 밀어 자리를 만든다.

대본 멤버는 한국어로 옮기면 원본보다 커질 수 있다(번역이 든 451개 중 57개, +2,246B). 문안을 줄이지 않고
(마스터 10-12 「재배치 진행하자」) **아카이브 안에서** 해결한다:

```
[TOC 32B × N][멤버 0][pad][멤버 1][pad] …     pad = 0~3B (오프셋 단위 4B 에 맞춤)
                                 ⇡ 파일 끝 ~ 섹터 끝 = 0~2047B 여유 (ISO 는 섹터 단위로 잡는다)
```

멤버가 커지면 **뒤 멤버를 그만큼 밀고**, TOC 의 오프셋·크기를 고치고, 파일 길이를 늘린다. 늘어난 길이가
**마지막 섹터 여유 안**이면 섹터 수가 안 바뀌므로 다른 파일은 하나도 안 옮긴다(ISO 디렉터리의 파일 크기만 고친다).
여유가 모자라면 같은 아카이브에서 **줄어든 멤버의 꼬리 0 채움**을 거둬 자리를 만든다 — 그래도 모자라면 **멈춘다**
(다른 파일을 옮겨야 하는 일이다).

🔴 안 건드린 멤버는 **바이트까지 같다**(위치만 밀린다). 끝에서 되읽어 검산한다(`arc_parse` → 멤버별 대조).
"""

import struct

import common

UNIT = 4  # SC*.DAT 의 오프셋 단위·멤버 정렬


class PackError(Exception):
    pass


def _a4(n):
    return (n + UNIT - 1) // UNIT * UNIT


def plan(data, replacements):
    """아카이브 재배치 계획 — 쓰지 않고 센다.

    `replacements` — {멤버 이름: 새 바이트열}. 반환: dict(
      sizes={이름: 새 크기}, grow=늘어난 총 바이트(4B 정렬), slack=마지막 섹터 여유, reclaimed=거둔 꼬리 바이트).
    예외: 여유를 다 써도 모자라면 `PackError`.
    """
    unit, ents = common.arc_parse(data)
    if unit != UNIT:
        raise PackError(f"오프셋 단위 {unit} — 이 도구는 {UNIT}B 단위 아카이브만 안다")
    names = [n for n, _, _ in ents]
    missing = set(replacements) - set(names)
    if missing:
        raise PackError(f"아카이브에 없는 멤버: {sorted(missing)[:3]}")
    sizes = {n: sz for n, _, sz in ents}
    for n, new in replacements.items():
        if len(new) > sizes[n]:
            sizes[n] = len(new)
    old_len = len(data)
    slack = -old_len % common.USER_SIZE

    def grow():
        return sum(_a4(sizes[n]) - _a4(sz) for n, _, sz in ents)

    reclaimed = 0
    if grow() > slack:
        # 줄어든 멤버의 꼬리 0 채움을 거둔다 — 큰 것부터, 필요한 만큼만.
        cand = sorted(
            ((_a4(sz) - _a4(len(replacements[n])), n) for n, _, sz in ents if n in replacements and len(replacements[n]) < sz),
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
        raise PackError(f"여유 {slack}B 에 필요 {grow()}B — 이 아카이브는 섹터가 늘어난다(다른 파일을 옮겨야 한다)")
    return {"sizes": sizes, "grow": grow(), "slack": slack, "reclaimed": reclaimed}


def repack(data, replacements):
    """(새 아카이브 바이트열, 계획). 안 바뀐 멤버는 바이트 그대로, 위치만 민다."""
    p = plan(data, replacements)
    unit, ents = common.arc_parse(data)
    sizes = p["sizes"]
    first = ents[0][1]  # 멤버 0 의 오프셋 = TOC(+패딩) 크기
    out = bytearray(data[:first])
    shift = 0
    new_ents = []
    for i, (n, off, sz) in enumerate(ents):
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
        out += b"\x00" * (new_off - len(out))  # 앞 멤버 뒤 정렬 패딩(원본 틈 그대로)
        out += chunk
        new_ents.append((n, new_off, keep))
        # 다음 멤버까지 원본 틈(정렬 패딩)을 이어 갈 만큼 shift 를 갱신한다
        shift += _a4(keep) - _a4(sz)
    old_len = len(data)
    new_len = old_len + p["grow"]
    out += b"\x00" * (new_len - len(out))
    if len(out) != new_len:
        raise PackError(f"길이가 계획과 다르다: {len(out)} (계획 {new_len})")
    # TOC — 오프셋(단위 4B)과 크기를 고친다. 이름·예약 필드는 그대로.
    for i, (n, off, keep) in enumerate(new_ents):
        pos = i * 32 + 20
        out[pos : pos + 8] = struct.pack("<II", off // UNIT, keep)
    out = bytes(out)
    verify(data, out, replacements, p)
    return out, p


def verify(old, new, replacements, p):
    """🔴 끝에서 되읽어 검산한다 — 「썼다」와 「다시 읽힌다」는 다르다."""
    u0, e0 = common.arc_parse(old)
    u1, e1 = common.arc_parse(new)
    if u1 != u0 or [n for n, _, _ in e1] != [n for n, _, _ in e0]:
        raise PackError("재배치 뒤 멤버 목록·단위가 달라졌다")
    if (len(new) + common.USER_SIZE - 1) // common.USER_SIZE != (len(old) + common.USER_SIZE - 1) // common.USER_SIZE:
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
        else:
            if got != old[o0 : o0 + s0] or s1 != s0:
                raise PackError(f"{n}: 안 건드릴 멤버가 바뀌었다")
    # 머리(TOC 이름·예약 필드·패딩) 는 오프셋·크기 필드 말고 같다.
    first = e0[0][1]
    for i in range(len(e0)):
        if old[i * 32 : i * 32 + 20] != new[i * 32 : i * 32 + 20] or old[i * 32 + 28 : i * 32 + 32] != new[i * 32 + 28 : i * 32 + 32]:
            raise PackError("TOC 의 이름·예약 필드가 바뀌었다")
    toc_end = len(e0) * 32
    if old[toc_end:first] != new[toc_end:first]:
        raise PackError("TOC 뒤 패딩이 바뀌었다")
    if len(new) != len(old) + p["grow"]:
        raise PackError("파일 길이가 계획과 다르다")
