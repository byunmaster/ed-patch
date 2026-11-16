"""화자 표 — 대사 블록 앞의 `12 NN`·`13 NN`(메시지 해석 전 이름창 연산)을 **개체 레코드**와 짝지어 읽는다.

해석기 역분석(10-24, `0x80045be8` VM 연산 `0F` 핸들러 + 연산 `12`/`13` 핸들러 `0x80046f4c`):
  · `12 NN` — 이름창에 쓸 개체 번호 `NN` 을 전역(`0x801EF9AA`)에 둔다. `13 NN` 은 `NN|0x8000`(파티원·시스템 이름표 쪽 표).
  · 이어지는 VM `0F` 가 메시지 창을 열 때 그 개체의 이름 문자열(개체 구조체 +0x28 의 색인)을 이름창에 그린다.
멤버 머리(스크립트 앞)에 **개체 레코드**가 이어진다: `<2B> ff ff <6B> [0F pad <u16 이름 색인>] <2B>` — 이름이 없으면 12바이트, 있으면 16바이트.
개체 번호는 이 레코드를 순서대로 1부터 센 것이다(`12 02` = 둘째 레코드 — 서장 올레시아·에스페리우스·승병으로 맞췄다).
⚠ NPC 말 걸기(개체가 자기 스크립트를 돌릴 때)는 해석기가 자동으로 그 개체 이름을 쓴다 — 그런 블록엔 `12 NN` 이 없어 화자를 못 읽는다(`None`).
"""

import struct


def entities(mem):
    """[(레코드 시작, 이름 색인 또는 None)] — 개체 번호 1부터 순서대로."""
    n = len(mem)
    s = None
    for p in range(
        8, min(n - 4, 400), 2
    ):  # 첫 `ff ff` 레코드 — 이어지는 레코드가 둘 이상일 때만 믿는다
        if mem[p + 2 : p + 4] != b"\xff\xff":
            continue
        t, k = p, 0
        while t + 12 <= n and mem[t + 2 : t + 4] == b"\xff\xff":
            t += 16 if mem[t + 10] == 0x0F else 12
            k += 1
        if k >= 2:
            s = p
            break
    out = []
    while s is not None and s + 12 <= n and mem[s + 2 : s + 4] == b"\xff\xff":
        if mem[s + 10] == 0x0F:
            out.append((s, struct.unpack_from("<H", mem, s + 12)[0]))
            s += 16
        else:
            out.append((s, None))
            s += 12
    return out


def speaker_of(mem, st, ents=None):
    """스트림 `st`(`typeset.message_streams` 한 건) 앞 `12 NN`/`13 NN` → ('n', 이름 색인) · ('x', 개체 번호) · ('p', NN) · None."""
    p = st["p0"]
    if p < 2 or mem[p - 2] not in (0x12, 0x13):
        return None
    nn = mem[p - 1]
    if mem[p - 2] == 0x13:
        return ("p", nn)
    ents = ents if ents is not None else entities(mem)
    if 1 <= nn <= len(ents):
        idx = ents[nn - 1][1]
        return ("n", idx) if idx is not None else ("x", nn)
    return ("x", nn)


# 파티원·핵심 인물 이름표(`13 NN` — 실행파일 표 `0x80081F74`, 13개). 이름은 번역 정본(정본 canon person)에서 읽는다 — 여기엔 원문 순서만 둔다.
PARTY = (
    "アヴィン",
    "マイル",
    "ミューズ",
    "マーティ",
    "ルキアス",
    "エレノア",
    "アルチェム",
    "ダグラス",
    "ラエル",
    "コンロッド",
    "ルティス",
    "ガウェイン",
    "ミッシェル",
)  # copyright:ok 인물 이름표(단어 수준)
