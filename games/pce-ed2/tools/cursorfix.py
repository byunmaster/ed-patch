"""선택 커서 틀 오른쪽 끝을 4px 오른쪽으로(11-07 정적 전수 ⓑ).

목록 커서는 스프라이트 여섯 개(왼쪽 끝 · 가운데 16px 넷 · 좌우 반전 오른쪽 끝)이고, 모양은 뱅크 0x69 `$9099` 근처의 스프라이트 묶음 표가 정한다
(`ff 00 00 02 <N> 00 …` 뒤 5바이트 항목들 — 마지막 항목이 반전된 오른쪽 끝, 첫 바이트가 x 오프셋). 도구 「사용」 목록의 커서는 N=6 묶음이고 오른쪽 끝 x 오프셋이 `0x45` 다.
원판 아이템 이름은 최장 7칸(84px)이라 맞았지만, 띄어쓰기를 품은 한글 이름 넷(「성스러운 지팡이」 등)은 88px 라 틀이 끝 글자 오른쪽 4px 를 가렸다
(「길모아의 무지개」 가 「…무지기」 로 읽혔다). 그래서 이 묶음의 오른쪽 끝 오프셋만 `0x49` 로 옮긴다 — 가운데 조각은 그대로 겹쳐 덮는다.
찾은 길: 목록을 열고 VDC 데이터 포트(`$0002`)에 오른쪽 끝 x(213)를 쓰는 순간에 쓰기 BP → 범용 스프라이트 묶음 그리기 루틴(`$5F40`) → `($12)` 가 가리키는 묶음.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import layout

CAP = (0x69, 0x109A)  # N=6 묶음의 오른쪽 끝 항목 첫 바이트(x 오프셋)
CAP_ORIG = 0x45
CAP_NEW = 0x49
CONTEXT = (
    0x69,
    0x1084,
)  # `06 00 3f 01 00 00 00 … 45 00 00 08 00` — 묶음 머리부터 오른쪽 끝 항목까지 25B
CONTEXT_ORIG = bytes.fromhex("06003f010000002f010000001f010000000f010000004500000800")


def fix(prog: layout.Prog) -> None:
    ctx = prog.o(CONTEXT[0], CONTEXT[1], len(CONTEXT_ORIG))
    assert ctx == CONTEXT_ORIG, f"커서 묶음 원본 바이트가 기대와 다르다 {ctx.hex()}"
    assert prog.o(*CAP, 1) == bytes([CAP_ORIG])
    prog.put(
        CAP[0],
        CAP[1],
        bytes([CAP_NEW]),
        "선택 커서 틀(N=6 묶음) 오른쪽 끝 +4px — 띄어쓰기 포함 아이템 이름 88px 수용",
    )
