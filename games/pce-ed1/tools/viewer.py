"""대사 보기(디버그 전용) — 씬 블록에 「메시지를 차례로 불러 실제 창에 띄우는」 네이티브 스텁을 끼운다.

마스터 10-19 「대사보기 만들어서 진행해」(전 씬 대사 검수). 걸어가 말 걸기 대신 **블록이 열릴 때**(머리 점프) 모든 메시지를
`LDA #lo STA $10 LDA #hi STA $11 JSR $5B5B`(블록 안 이벤트 코드가 대사를 띄우는 호출 꼴 — 씬 18 등에서 실측, 메시지 시작 주소를
$10/$11 에 두고 부른다)로 하나씩 띄운다. 끝나면 원래 머리 점프로 돌아간다.

⚠ **제품 롬에는 절대 안 들어간다** — `build.py` 가 `ED_VIEWER=1` 일 때만 부른다(꼬리표는 `test-` 로 시작해야 한다).
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import messages as M

HEAD_OPS = (0x4C, 0x20)  # 블록 머리 점프(JMP · JSR) — glyphdyn.HEAD_OPS 와 같다
SHOW = 0x5B5B  # 메시지 띄우기(JSR) — ($10) = 메시지 시작
BANK = 0x2000
MARK = 0x3FF8  # 번호표 RAM(2B) — 비어 있는지는 단조 증가로 실측
SPEED = 0xC051  # 글자 찍는 속도 바이트(policy.md 「나레이션」) — 3 = 즉시


def skip_set(bid: int) -> set[int]:
    """건너뛸 메시지 번호(원본 비핀 메시지 순번) — 호출하면 안 끝나는 메시지(상점 메뉴 등)를 빼고 뒤를 찍는다. `ED_VIEWER_SKIP` = {"씬": [번호…]} JSON 경로."""
    path = os.environ.get("ED_VIEWER_SKIP")
    if not path:
        return set()
    import json

    return set(json.load(open(path)).get(str(bid), []))


def _msgs(block: bytes, bid: int):
    sk = skip_set(bid)
    return [m for i, m in enumerate(x for x in M.parse(block) if not x.pinned) if i not in sk]


def starts(block: bytes, bid: int = -1) -> list[int]:
    """띄울 메시지 시작 주소(논리) — 끝 바이트가 있는 것 + 조각(점프로 이어지는 것)도 포함한다(이어진 줄까지 보인다).
    `ED_VIEWER_ADDRS` = {"씬": [블록 안 오프셋…]} JSON 이면 그 씬은 **그 주소들만** 띄운다 — 메시지 사이 슬롯·조각(`0B は 0E` 같은 단독 가나)까지 이어서 보는 시험용."""
    import json

    custom = json.loads(os.environ.get("ED_VIEWER_ADDRS", "{}")).get(str(bid))
    if custom:
        return [M.BASE + o for o in custom]
    return [M.BASE + m.start for m in _msgs(block, bid)]


def stub(at: int, addrs: list[int], head: int) -> bytes:
    """원래 초기화(JSR) → 메시지 주소 표를 도는 고리(번호표 MARK 가 곧 색인). 메시지당 2B 라 블록이 거의 안 커진다
    (예전 펼친 꼴은 메시지당 21B 라 전 씬 빌드가 이사 자리를 넘겼다 — rel 10067+12 > 10072). 메시지는 255개 미만이어야 한다."""
    n = len(addrs)
    assert 0 < n < 256, n
    lo_at = at + 58  # 코드 길이(아래 assert)
    hi_at = lo_at + n
    code = bytearray()
    code += bytes([0x20, head & 0xFF, head >> 8])  # JSR 원래 머리(초기화) — 맵이 그려진 뒤에 띄운다
    code += bytes([0xA9, int(os.environ.get("ED_VIEWER_SPEED", "3")), 0x8D, SPEED & 0xFF, SPEED >> 8])  # 메시지 속도 = 3(즉시 찍기, $5B8A 표) — 중간 프레임이 없다. 장면 초기화 뒤에 써야 덮이지 않는다
    code += bytes([0xA9, 0x00, 0x8D, MARK & 0xFF, MARK >> 8, 0x8D, (MARK + 1) & 0xFF, (MARK + 1) >> 8])  # MARK=0
    loop = len(code)
    code += bytes([0xAE, MARK & 0xFF, MARK >> 8])  # LDX MARK
    code += bytes([0xBD, lo_at & 0xFF, lo_at >> 8, 0x85, 0x10])  # LDA lo,X STA $10
    code += bytes([0xBD, hi_at & 0xFF, hi_at >> 8, 0x85, 0x11])  # LDA hi,X STA $11
    code += bytes([0x20, SHOW & 0xFF, SHOW >> 8])  # JSR SHOW
    # 메시지가 끝난 뒤 한참(약 2~8초) 바쁜 기다림 — 쪽 대기가 없는 메시지(상점 토막 등)도 화면이 남아 있어야 찍힌다.
    # ⚠ IRQ 카운터($2249)를 기다리는 안은 멈췄다(이 문맥에선 안 올라간다, 실측) — CPU 사이클 루프로 한다
    w3 = len(code) + 2  # LDA 다음 = LDY 자리
    code += bytes([0xA9, int(os.environ.get("ED_VIEWER_WAIT", "20"))])  # LDA #20(약 1~4초) — 시험: 60 으로 하면 한 장면에 1~2번호가 더 찍힌다(실측 씬 38·40)
    code += bytes([0xA0, 0x00])  # w3: LDY #0
    w2 = len(code)
    code += bytes([0xA2, 0x00])  # w2: LDX #0
    w1 = len(code)
    code += bytes([0xCA])  # w1: DEX
    code += bytes([0xD0, (w1 - (len(code) + 2)) & 0xFF])  # BNE w1
    code += bytes([0x88])  # DEY
    code += bytes([0xD0, (w2 - (len(code) + 2)) & 0xFF])  # BNE w2
    code += bytes([0x3A])  # DEC A (HuC6280)
    code += bytes([0xD0, (w3 - (len(code) + 2)) & 0xFF])  # BNE w3(LDY 자리)
    code += bytes([0xEE, MARK & 0xFF, MARK >> 8])  # INC MARK
    code += bytes([0xAD, MARK & 0xFF, MARK >> 8, 0xC9, n])  # LDA MARK CMP #n
    rel = loop - (len(code) + 2)
    code += bytes([0xD0, rel & 0xFF])  # BNE loop
    code += bytes([0x60])  # RTS
    assert len(code) == 58, len(code)
    return bytes(code) + bytes(a & 0xFF for a in addrs) + bytes(a >> 8 for a in addrs)


def patch_block(block: bytes, orig: bytes, bid: int = -1) -> bytes:
    """`orig` = 번역 전 블록 — ⚠ 번역한 블록은 `messages.parse` 가 한글을 못 읽어 메시지를 5개밖에 못 찾는다(실측 씬 16: 원본 30 → 5).
    splice 는 **주소를 안 옮기므로**(제자리 + 끝에 이어붙임) 원본 파싱의 시작 주소가 그대로 번역본의 시작이다."""
    if block[0] not in HEAD_OPS:
        return block
    addrs = starts(orig, bid)
    if not addrs:
        return block
    head = block[1] | block[2] << 8
    at = M.BASE + len(block)
    out = bytearray(block)
    out[1:3] = at.to_bytes(2, "little")
    out += stub(at, addrs, head)
    if len(out) > BANK:
        raise ValueError(f"대사 보기 스텁이 블록을 뱅크(8KB)보다 키운다: {len(out)}B")
    return bytes(out)


def index(bid: int, orig: bytes) -> dict:
    """번호표(i) → 원본 메시지 열쇠(번역 전 파싱의 i번째 비핀 메시지 — `patch_block` 의 stub 순서와 같다)."""
    import json

    custom = json.loads(os.environ.get("ED_VIEWER_ADDRS", "{}")).get(str(bid))
    if custom:  # 시험용 주소 목록 — 열쇠는 없다(주소 그대로)
        return {"block": bid, "n": len(custom), "ok": True, "keys": [f"@{o:04X}" for o in custom], "idx": list(range(len(custom)))}
    ms = _msgs(orig, bid)
    return {"block": bid, "n": len(ms), "ok": True, "keys": [m.key for m in ms], "idx": [i for i, x in enumerate(y for y in M.parse(orig) if not y.pinned) if i not in skip_set(bid)]}
