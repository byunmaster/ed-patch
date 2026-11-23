"""임시 1섹터 적재(NPC 그림·지역 자료)가 캐시가 꽉 차서 실패하면 글리프 뱅크 1 을 잠깐 빌린다(11-22 마스터 「세이브 파일 왔다갔다 하다보면 npc깨짐」).

🔴 원인(실측 — 할당 실패 출구 `$5595` 에서 잡았다): 4장 솔디스(지역 3)는 **정상 상태**가 상주 6뱅크(그룹 0 = 3 · NPC 그림 캐시 셋) + 씬 컨테이너 3 +
  지역 묶음 A 2 + B 3 = 14 — 한글판 한도(글리프 뱅크 둘이 슬롯 14·15 라 14칸)를 꼭 채운다. 엔진은 그 위에 **임시 1뱅크**를 두 자리에서 더 잡는다:
  · NPC 그림 맞추기(`$69CC` 안 `$6A63`) — 디스크에서 1섹터를 읽어 NPC 캐시로 옮기고 바로 내린다. 목록(`$C012`)의 그림마다 한 번씩.
  · 지역 자료(`$6C7E` 안 `$6CE3`) — 1섹터를 읽어 0x600B 를 `$DA00` 으로 옮기고 내린다.
  원판 16칸에서는 들어가고 14칸에서는 실패한다. 로더(`$56D8`)의 캐리를 아무도 안 봐서 그룹이 빈 채(`$378D[Y] = 0x80`)로 뱅크 0xF8(RAM)을 그림으로 옮긴다 —
  NPC 가 쓰레기 무늬로 나온다. 새로 켜서 4장 세이브를 읽어도 난다(전환 순간이 아니라 정상 상태가 꽉 찬 것이라 `earlyfree` 로는 안 고쳐진다).

고침 — 띠 「(가)안」(`band_fallback`, 마스터 11-06)과 같은 길을 임시 적재 둘에 넓힌다:
  · 두 적재 자리를 이 스텁의 먼 호출로 바꾼다. 스텁은 엔진 로더를 그대로 부르고, **실패했을 때만** 빈 그룹 번호를 받아 슬롯 15(글리프 뱅크 1, 0x87)를
    가리키게 한 뒤 엔진 로더의 읽기 자리(`$570C`)로 뛴다 — 실패한 로더는 섹터 수(`$F8`·`$378C`)·rel(`$FC~$FE`)을 세워 둔 채 돌아오므로(CD 를 아직 안 읽었다)
    거기서부터 엔진이 rel 을 슬롯 15 칸에 적고 · 0x87 로 읽고 · 실패하면 다시 읽고 · MPR6 을 되돌리고 · 캐리 0 으로 돌아온다. 호출 쪽은 평소대로 옮기고
    내린다(`$5597` — 슬롯 15 의 주인표를 0 으로, 번호를 0x80 으로. 띠와 같은 선례).
  · 빌린 섹터는 글리프 뱅크 1 의 **앞 2048B**(글자 455~568 자리)다. 빌렸다는 표시(`dirty`)를 세워 두고, 적재가 다 끝난 자리 둘에서 한 번만 디스크에서
    되돌린다(`band_fallback` 의 되돌리기 고리를 같이 쓴다):
      씬 진입(`$6617` — NPC 미리 올리기 `$6B8C` 와 지역 자료 `$6C7E` 바로 뒤) · 리더 그림 갈기(`$628B` — `$69CC` 뒤에 오는 `$6288` 머리, 부르는 길 셋이 다 지난다).
    되돌리기는 엔진이 어차피 CD 를 읽는 자리 바로 옆이라 음악·화면에 새 간섭이 없다. 그 사이에는 글자를 안 그린다.
  · 새로 켜는 길(`$664C`)은 묶음을 **맨 나중에** 올려서 임시 적재가 실패하지 않는다 — 건드리지 않는다.
  ⚠ 띠가 슬롯 15 를 빌려 띄워 둔 동안(장 제목) 이 길이 또 빌리면 띠 그림이 덮인다 — 띠가 떠 있는 동안에는 씬이 안 바뀌어 겹치지 않는다.

먼 호출(`$4FD8`)은 A·Y·플래그를 들고 나고 X 를 안 건드리며 MPR3·4 만 되돌린다 — 그래서 스텁이 돌려준 A 를 사이트의 남은 명령이 그대로 받는다.
자리: 뱅크 0x70 `+0x190A`(디버그 목록 코드 끝) ~ `+0x194F`(`earlyfree`) 69B.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import band_fallback
import earlyfree
import hook

BANK = 0x70
OFF = 0x190A
ROOM = earlyfree.OFF - OFF  # 69B
ORG = 0x6000 + OFF
SITE_BANK = 0x6A
FAR = earlyfree.FAR
LOADER = 0x56D8
LOADER_READ = 0x570C  # 로더 안 「rel 을 슬롯 칸에 적고 읽는다」 — X = 슬롯 · Y = 그룹
ALLOC_GROUP = 0x578A
GROUP_SLOT = 0x378D
BORROW_SLOT = band_fallback.BORROW_SLOT
NOP = b"\xea"

# (이름, 뱅크 0x6A 오프셋, 원판 바이트, 스텁 입구 이름, 먼 호출 뒤에 남길 바이트)
SITES = (
    ("npc", 0x0A61, bytes.fromhex("a90120d85684f8"), "load", NOP),  # LDA #1 / JSR $56D8 / STY $F8
    ("area", 0x0CE1, bytes.fromhex("a90120d8565ab98d37"), "load", b"\x5a" + NOP * 2),  # … / PHY / LDA $378D,Y — PHY 만 남긴다
    ("scene", 0x0617, bytes.fromhex("a9018562a902"), "scene", b""),  # LDA #1 / STA $62 / LDA #2 — 뒤의 STA $C046 이 A 를 받는다
    ("leader", 0x028B, bytes.fromhex("a901186df13e"), "leader", b""),  # LDA #1 / CLC / ADC $3EF1 — 뒤의 TAM #$20 이 A 를 받는다
)


def _asm() -> hook.Asm:
    a = hook.Asm(ORG)
    a.label("load")  # 먼 호출 입구 — X:Y = 레코드(엔진 로더 인자 그대로)
    a.op("JSR", "abs", "load1")
    a.op("STY", "zp", 0xF8)  # NPC 쪽 원판 명령(지역 쪽은 `$F8` 을 뒤에서 새로 세운다)
    a.op("LDA", "absy", GROUP_SLOT)  # 지역 쪽 원판 명령(NPC 쪽은 사이트가 다시 읽는다)
    a.op("RTS")
    a.label("load1")
    a.op("LDA", "imm", 1)
    a.op("JSR", "abs", LOADER)
    a.op("BCC", "rel", "done")
    a.op("JSR", "abs", ALLOC_GROUP)  # Y = 빈 그룹 번호
    a.op("BCS", "rel", "done")
    a.op("LDA", "imm", BORROW_SLOT)
    a.op("STA", "absy", GROUP_SLOT)
    a.op("TAX")
    a.op("STA", "abs", "dirty")
    a.op("JMP", "abs", LOADER_READ)
    a.label("rid")  # 빌렸으면 글리프 섹터를 되돌린다(A·X·Y 를 쓴다)
    a.op("LDA", "abs", "dirty")
    a.op("BEQ", "rel", "done")
    a.op("STZ", "abs", "dirty")
    a.op("JMP", "abs", band_fallback.restore_at())
    a.label("done")
    a.op("RTS")
    a.label("scene")  # 먼 호출 입구 — 씬 진입
    a.op("PHY")  # 원판은 여기서 Y 를 안 건드린다
    a.op("JSR", "abs", "rid")
    a.op("PLY")
    a.op("LDA", "imm", 1)
    a.op("STA", "zp", 0x62)
    a.op("LDA", "imm", 2)
    a.op("RTS")
    a.label("leader")  # 먼 호출 입구 — 리더 그림 갈기(뒤에서 X·Y 를 새로 세운다)
    a.op("JSR", "abs", "rid")
    a.op("LDA", "imm", 1)
    a.op("CLC")
    a.op("ADC", "abs", 0x3EF1)
    a.op("RTS")
    a.label("dirty")
    a.data(b"\0")
    return a


def code() -> bytes:
    b = _asm().bytes()
    assert len(b) <= ROOM, len(b)
    return b


def labels() -> dict[str, int]:
    a = _asm()
    a.bytes()
    return dict(a.labels)


def sites() -> list[tuple[str, int, bytes, bytes]]:
    """(이름, 뱅크 0x6A 오프셋, 원판 바이트, 새 바이트)"""
    lab = labels()
    out = []
    for name, off, old, entry, rest in SITES:
        new = FAR + bytes([BANK - 0x68]) + lab[entry].to_bytes(2, "little") + rest
        assert len(new) == len(old), name
        out.append((name, off, old, new))
    return out


if __name__ == "__main__":
    b = code()
    print(len(b), "B /", ROOM, "B · ORG", hex(ORG), {k: hex(v) for k, v in labels().items()})
    for name, off, old, new in sites():
        print(f"{name:7s} 0x6A:${0x6000 + off:04X} {old.hex()} → {new.hex()}")
