"""제어 코드 대조 게이트 — 원판 대본의 **색·흐름·이름 삽입·수 그리기 연산**이 제품 이미지에 같은 자리로 남았는지 바이트로 본다.

    python3 tools/check_ctrl_codes.py [--image 제품.bin]

배경(pce-ed1 10-29): 원문의 색 전환 옵코드를 번역 조립기가 한 번도 안 내 35메시지가 엉뚱한 색으로 나왔는데, 빌드·게이트·짝 표 어느 것도 못 잡았다.
ED4 의 제어는 둘 층이다 — ① 스크립트 구간(멤버 머리~글자 표 시작)의 VM·메시지 연산(`05`~`08` 이름·수 삽입 · `10` 이상 색…) ② 글자 코드열 안의 `0xEEEE`(수 그리기 + 인자 둘 — 값은 상수 합이라, 번역이 숫자를 전각 글리프·한글 수사로 풀어 쓴 조각에선 빠질 수 있다).
재삽입은 글자 표만 갈아 끼우므로 ①은 **바이트 그대로**여야 하고(예외 하나: 선택지 창 연산 `3B` 의 열 바이트 — 의도한 넓히기, `choice.py`), ②는 제품 것이 원판 것의 부분열(지어내기·값 바꾸기 금지)이어야 한다.
세는 것: 표 규격 멤버의 스크립트 구간 바이트 · 메시지 스트림(해석기가 걷는 그대로, 출력 자리 뺀 연산 바이트) · 조각별 `0xEEEE` 인자열.
`--image` 를 안 주면 제품 이미지(`work/build`)를 쓰고, 없으면 건너뛴다(⏭ — 통과가 아니다).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import reinsert
from shared.ps1 import gmf_arc
from shared.ps1 import gmf_script as sm

NUM = 0xEEEE
TERM = 0xFFFF
CHOICE_OP = 0x3B


def stream_ops(mem):
    """[(첫 출력 색인, 출력 수, 연산 바이트)] — 메시지 스트림마다 출력 자리(`0F` + u16)를 뺀 나머지."""
    out = []
    for st in sm.message_streams(mem):
        skip = set()
        for q, _v in st["prints"]:
            skip.update((q, q + 1))
            if mem[q - 1] == 0x0F:
                skip.add(q - 1)
        b = bytes(mem[i] for i in range(st["p0"], st["end"]) if i not in skip)
        out.append((st["prints"][0][1] if st["prints"] else -1, len(st["prints"]), b))
    return out


def nums(codes):
    """조각 코드열의 `0xEEEE` 덩이(+ 인자 둘)."""
    out, i = [], 0
    while i < len(codes) and codes[i] != TERM:
        if codes[i] == NUM:
            out.append(tuple(codes[i : i + 3]))
            i += 3
        else:
            i += 1
    return out


def compare(jm, km):
    """(문제 목록) — 한 멤버의 원판·제품 바이트 대조. 항목은 (부류, 설명)."""
    bad = []
    bj, bk = sm.text_base(jm), sm.text_base(km)
    if bj != bk:
        return [("스크립트 구간 길이", f"{bj}→{bk}")]
    for i in range(bj):
        if jm[i] != km[i] and not (i >= 2 and jm[i - 2] == CHOICE_OP):
            bad.append(("스크립트 바이트", f"+{i:#x} {jm[i]:02x}→{km[i]:02x}"))
    if stream_ops(jm) != stream_ops(km):
        bad.append(("메시지 스트림 연산", "스트림 연산 열이 다르다"))
    sj, sk = reinsert.member_segments(jm), reinsert.member_segments(km)
    for i, c in enumerate(sj):
        if i < len(sk) and not subseq(nums(sk[i]), nums(c)):
            bad.append(("수 그리기 코드", f"조각 {i}"))
    return bad


def subseq(a, b):
    """a 가 b 의 부분열인가 — 제품의 `0xEEEE` 덩이는 원판 것을 순서대로 일부 남긴 것이어야 한다(새로 지어내거나 값을 바꾸면 안 된다)."""
    it = iter(b)
    return all(x in it for x in a)


def members(img):
    with common.open_disc(img) as d:
        for path, (lba, size) in common.iso_files(img).items():
            if "/SC" not in path or not path.endswith(common.ARCHIVE_EXT) or size < 64:
                continue
            try:
                data = d.read_extent(lba, size)
                _, ents = gmf_arc.arc_parse(data)
            except gmf_arc.ArchiveError:
                continue
            for nm, off, sz in ents:
                if "\\BIN\\" in nm and nm.endswith(".BIN") and sz >= 8:
                    yield (path, nm), bytes(data[off : off + sz])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=os.path.join(common.BUILD_DIR, "Eiyuu Densetsu IV (KR).bin"))
    a = ap.parse_args(argv)
    if not os.path.exists(a.image):
        print(f"⏭ 제품 이미지가 없다({a.image}) — 제어 코드 대조를 건너뛴다(통과 아님)")
        return 0
    common.verify_source()
    jp = dict(members(common.orig_bin()))
    n = nb = nstream = nnum = 0
    probs = []
    for key, km in members(a.image):
        jm = jp.get(key)
        if jm is None:
            continue
        try:
            if sm.layout(jm) != sm.LAYOUT_TABLE:
                continue
            bad = compare(jm, km)
            nstream += len(stream_ops(jm))
            nb += sm.text_base(jm)
            nnum += sum(len(nums(c)) for c in reinsert.member_segments(jm))
        except Exception as e:  # noqa: BLE001 — 파서가 못 읽는 멤버도 센다(통과로 치지 않는다)
            bad = [("읽기 실패", repr(e))]
        n += 1
        probs += [(key, b) for b in bad]
    # 양성 대조 — 한 바이트를 일부러 틀어 대조기가 잡는지(안 잡으면 이 게이트가 장님이다)
    key, jm = next((k, m) for k, m in jp.items() if sm.layout(m) == sm.LAYOUT_TABLE and stream_ops(m))
    forged = bytearray(jm)
    forged[sm.text_base(jm) - 4] ^= 0x10
    if not compare(jm, bytes(forged)):
        print("🔴 양성 대조 실패 — 틀어 놓은 바이트를 못 잡는다")
        return 1
    print(f"  분모: 표 규격 멤버 {n} · 스크립트 구간 {nb:,}B · 메시지 스트림 {nstream:,} · 수 그리기 {nnum:,}")
    for key, (cls, msg) in probs[:20]:
        print(f"  🔴 {key[1].split(chr(92))[-1]} {cls}: {msg}")
    print(f"  제어 코드 갈림 {len(probs)}건 (양성 대조 ✓)")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
