"""원판 문안 사본 게이트 — 구운 롬에 **색인이 안 가리키는 원판 압축 블록**이 일본어를 든 채 남았나(마스터 11-17 전 게임 점검).

    python3 tools/check_orphan_copies.py

배경: PCE I 에서 원판 디스크에 대사 블록 사본이 우리가 고친 자리 밖(맵별 레코드 안)에 따로 있었고, 정상 진행이 그 사본을 읽어
장면 전체가 일본어로 나왔다. 빌드·게이트는 「고친 자리」만 분모로 봐서 못 잡았다. md-ed1 에서는 같은 꼴이 **색인 밖 원판 블록**으로 나온다 —
대본 아카이브를 앞에서부터 다시 채우고 남은 뒤쪽에 원판 압축 블록이 통째로 남은 것(마지막 대본 블록 224: 새 사본은 꼬리로 가고 원판은 제자리).
`check_residual_jp` 는 압축 바이트가 가나로 안 읽혀 못 본다. 그래서 여기서:

  ① 구운 롬 전체에서 LZ 블록 체인을 색인 없이 찾아(`archives.scan_chains`) **일곱 아카이브 색인이 가리키는 블록을 뺀** 나머지를 푼다.
  ② 푼 결과에 **원판 문안 아카이브(대본·전투·시스템)에서 뽑은 가나·한자 5자↑ 런**이 하나라도 있으면 실패(원판 사본).
  ③ 롬 본체 바이트에서도 원판 문안 런(8자↑, 비압축 사본)을 찾는다.

읽히는 길: 블록은 색인(BE32 오프셋 표)으로만 불리고 색인 밖 블록을 가리키는 주소 값은 롬 어디에도 없다(실측 11-17, 0x191098) —
그래도 **지운다**(빌드가 남는 구간을 0xFF 로 채운다). 구운 빌드 롬이 없으면 「안 쟀다」로 알리고 통과한다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import lz

TEXT_ARCHIVES = ("script", "battle", "sys")
RUN = re.compile(rb"(?:[\x81-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]){5,}")


def jp_runs(b: bytes) -> list[bytes]:
    out = []
    for m in RUN.finditer(b):
        try:
            s = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in s):
            out.append(m.group())
    return out


def fingerprints(orig: bytes) -> set[bytes]:
    fp: set[bytes] = set()
    for n in TEXT_ARCHIVES:
        for _s, data, _e in archives.blocks(orig, archives.ARCHIVES[n][0]):
            fp.update(jp_runs(data))
    return fp


def orphans(rom: bytes) -> list[tuple[int, int]]:
    """색인이 안 가리키는 LZ 블록 (시작, 끝)."""
    live = {s for _n, (b, _c, _t) in archives.ARCHIVES.items() for s, _d, _e in archives.blocks(rom, b)}
    return [
        (s, e)
        for ch in archives.scan_chains(rom, 0x080000, common.FREE_TAIL[0])
        for s, e, _n in ch
        if s not in live
    ]


def find(orig: bytes, rom: bytes) -> list[str]:
    fp = fingerprints(orig)
    bad = []
    for s, e in orphans(rom):
        try:
            data, _ = lz.decode(rom, s)
        except (ValueError, IndexError):
            continue
        hit = [r for r in jp_runs(data) if r in fp]
        if hit:
            bad.append(f"색인 밖 원판 블록 0x{s:X}~0x{e:X}: 원판 문안 런 {len(hit)}개 — {hit[0].decode('cp932')[:12]}")
    for r in sorted(fp, key=len, reverse=True):
        if len(r) >= 16:
            i = rom.find(r)
            if i >= 0:
                bad.append(f"롬 본체 0x{i:X} 에 원판 문안 사본(비압축): {r.decode('cp932')[:12]}")
    return bad


def main() -> int:
    p = common.BUILD_DIR / common.BUILD_TAG.replace("/", "_") / "ed1-kr.bin"
    if not p.exists():
        print("  원판 문안 사본 — 구운 빌드 롬이 없어 안 쟀다")
        return 0
    bad = find(common.rom(), p.read_bytes())
    print(f"  원판 문안 사본 {len(bad)}개 (색인 밖 압축 블록 · 롬 본체 비압축 사본)")
    for b in bad:
        print("  ❌ " + b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
