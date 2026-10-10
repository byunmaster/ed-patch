"""블록 161(미니게임) 스트림 밖 자료 — 배우 이름 레코드 둘(`ff`+이름+`06`)과 능력치 배분 라벨 넷(`20`+글자+`00`). scene.py 가 못 본다.

    python3 tools/actor_names.py --check

같은 길이로 덮는다(뒤 오프셋 불변). 세리오스 레코드는 재조립이 스트림으로 읽어 옮기므로 꼴로 찾는다.
이름은 정본(`shared/canon`)에서 읽는다(게임 폴더에 JP→KR 표를 안 둔다) — 여기엔 원문 열쇠와 자리만 있다.
이 레코드를 가리키는 lea·bsr 의 10B 어긋남은 따로다(블록 161 STALE_SHIFT 몫, 손대지 않았다 — docs/devlog.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

sys.path.insert(0, str(common.ROOT))
from shared import canon

BLOCK = 161
# (자리, 원문) — 자리의 `ff` 바로 뒤가 이름, 이름 뒤는 `06`
LABELS = ["攻撃力", "防御力", "すばやさ", "残り"]  # 능력치 배분 라벨 — `20`+글자+`00`, 스트림 밖(앞 `ＨＰ` 는 전각 그대로)
RECORDS = [(0x954, "セリオス"), (0x964, "海賊")]


def _kr(jp: str) -> str:
    kr = canon.lookup(jp, None, "ed1")
    if not kr:
        raise SystemExit(f"블록 161 배우 이름 {jp}: 정본에 없다")
    return kr


def chars() -> set[str]:
    return {c for jp in [j for _a, j in RECORDS] + LABELS for c in _kr(jp)}


def new_block(orig: bytes, cs) -> bytes:
    """`orig` 는 재조립을 거친 블록일 수 있다 — 세리오스 쪽은 스트림으로 읽혀 새 자리로 옮겨 가고(옛 자리는 0),
    해적 쪽은 제자리다. 그래서 자리가 아니라 `ff`+이름+`06` 꼴을 찾아 **딱 하나**일 때 같은 길이로 덮는다."""
    out = bytearray(orig)
    for _at, jp in RECORDS:
        old = jp.encode("cp932")
        pat = b"\xff" + old + b"\x06"
        if out.count(pat) != 1:
            raise SystemExit(
                f"블록 161 배우 이름 {jp}: 레코드가 {out.count(pat)}곳이다(하나여야 한다)"
            )
        new = cs.encode(_kr(jp))
        if len(new) != len(old):
            raise SystemExit(
                f"블록 161 배우 이름 {jp}: 길이가 안 맞는다 {len(new)}B ≠ {len(old)}B ({_kr(jp)})"
            )
        at = out.index(pat) + 1
        out[at : at + len(old)] = new
    for jp in LABELS:
        old = jp.encode("cp932")
        pat = b"\x20" + old + b"\x00"
        if out.count(pat) != 1:
            raise SystemExit(f"블록 161 라벨 {jp}: {out.count(pat)}곳이다(하나여야 한다)")
        new = cs.encode(_kr(jp))
        if len(new) > len(old):
            raise SystemExit(f"블록 161 라벨 {jp}: 길이가 넘는다 {len(new)}B > {len(old)}B ({_kr(jp)})")
        at = out.index(pat) + 1
        out[at : at + len(old)] = new + b" " * (len(old) - len(new))  # 모자란 만큼은 뒤를 공백으로 채운다
    return bytes(out)


if __name__ == "__main__":
    for at, jp in RECORDS:
        print(f"  {at:#x} {jp} → {_kr(jp)} ({len(jp.encode('cp932'))}B)")
