#!/usr/bin/env python3
"""**메시지 포인터 표의 모든 목표가 번역 단위 목록 안에 있나** — 목록 밖을 가리키면 거기는 일본어로 남아도 안 보인다.

sfc-ed1 이 찾았다(10-18): 번역 단위 목록이 훑는 구간 밖을 포인터 표가 가리켜 장면 대사 101개가 일본어 그대로였다.
단위 목록(덤프 `entries`)도 잔존 게이트도 **목록을 기준으로** 돌아서 원리상 못 본 자리다.

두 축을 **원본 이미지의 포인터**에서 출발해 잰다(목록을 거치지 않는다):
 A. 포인터 값(4바이트 BE, 2 정렬)이 그 파일 안의 **일본어 글 시작**(앞 바이트가 NUL·제어, 가나 2자↑)을 가리키는데 그 자리가
    덤프 엔트리 구간 `[file_offset, +raw 길이)` 밖이면 실패 — 번역 단위가 못 본 목표다.
 B. **빌드 이미지의 포인터**가 가리키는 목표가 아직 일본어 글이면 실패 — 단위 안이어도 안 들어간 것이다(옮긴 블록의 옛 칸은 아무도 안 가리키니 목표가 아니다).

판정 함수(`outside_spans` · `unchanged_jp`)는 순수 함수라 합성 데이터로 테스트한다(`tests/test_ptr_targets.py`).

    python3 tools/check_ptr_targets.py
"""

import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common
import patch_scn as P

KANA = re.compile(r"[ぁ-ゟ゠-ヿ]")


def jp_text_at(data, t):
    """`data[t:]` 가 NUL 까지 일본어 글(가나 2자↑)이면 그 글, 아니면 `None`. 앞 바이트가 글 안이면(문자열 한복판) `None`."""
    if t > 0 and data[t - 1] >= 0x20:
        return None
    try:
        txt = data[t : t + 60].split(b"\x00")[0].decode("cp932")
    except UnicodeDecodeError:
        return None
    return txt if len(txt) >= 3 and len(KANA.findall(txt)) >= 2 else None


def targets(data, base):
    """`{목표 오프셋}` — 2 정렬 4바이트 BE 값이 이 파일 안을 가리키는 자리의 목표."""
    out = set()
    for i in range(0, len(data) - 3, 2):
        t = struct.unpack(">I", data[i : i + 4])[0] - base
        if 0 < t < len(data):
            out.add(t)
    return out


def outside_spans(tg, spans):
    """[목표] 중 어느 `[시작, 끝)` 구간에도 안 드는 것."""
    return sorted(t for t in tg if not any(a <= t < b for a, b in spans))


def unchanged_jp(tg_build, built):
    """**빌드 이미지의 포인터**가 가리키는 목표 중 아직 일본어 글인 것 — 옮긴 블록의 옛 칸(아무도 안 가리킨다)은 목표가 아니다."""
    return [t for t in sorted(tg_build) if jp_text_at(built, t) is not None]


def main():
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    fo, mo = common.open_image(common.ORIG_BIN)
    fb, mb = common.open_image(dst)
    orig = {n: (l, s) for n, l, s in common.iso_files(mo)}
    total = out_a = same_b = 0
    bad = []
    for name, lba, size in common.iso_files(mb):
        if not name.endswith(".BIN") or size > 3_000_000 or name not in orig:
            continue
        got = P.load(name)
        if not got:
            continue
        base, entries = got
        o = common.read_extent(mo, *orig[name])
        b = common.read_extent(mb, lba, size)
        spans = []
        for e in entries:
            a = int(e["file_offset"], 16)
            spans.append((a, a + len(bytes.fromhex(e["raw_hex"]))))
        tg = {t for t in targets(o, base) if jp_text_at(o, t) is not None}
        total += len(tg)
        oa = outside_spans(tg, spans)
        ub = unchanged_jp(targets(b, base), b)
        out_a += len(oa)
        same_b += len(ub)
        bad += [f"A {name}@{t:#x}" for t in oa] + [f"B {name}@{t:#x}" for t in ub]
    print(f"  {'✅' if not bad else '🔴'} 메시지 포인터 목표(일본어 글) {total:,} · 번역 단위 밖 {out_a} · 빌드에서 그대로 일본어 {same_b}")
    for x in bad[:20]:
        print(f"    ❌ {x}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
