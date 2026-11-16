"""**확인용 롬 `ss-ed3-voicecheck`** — 맵에 들어가면 그 맵의 음성 장면(V##)이 시작하는 스텁(관리자 11-06).

    ED_VOICECHECK=1 ED_BUILD_TAG=ss-ed3-voicecheck python3 games/ss-ed3/tools/build.py

🔴 왜: V## 싱크 확인은 세이브스테이트로 하면 안 된다(RAM 안 코드·글까지 그 빌드로 굳는다). 장면을 걸어서 밟는 자연 트리거는 아직 못 풀었다.
   이벤트 시작 루틴(`0x0600FDC0` = 「이벤트 r4 번 시작」)은 맵 입장 때 `r4 = 입장 이벤트(보통 0)` 로 불린다. 그 호출의 풀 리터럴(`0x0600A518`)을
   이 스텁으로 바꿔, **현재 맵이 표에 있으면 r4 를 그 V 의 이벤트 색인으로 갈아 끼우고**(필요한 진행 깃발도 맞춘다) 원래 루틴으로 뛴다.
   마스터는 디버그 맵 설정(`X+Y+Z` → 맵 설정)으로 그 맵에 들어가기만 하면 된다(좌표는 `COORD`).

스텁은 **코드 예약 칸**(`codearea.VCHK`)에 앉고 `/0.BIN` 에서는 풀 리터럴 4B 만 바뀐다 — 그 밖 바이트·자막 시각은 제품 롬과 같다(섹터 비교 `check`).
맵 식별 = **`*(0x00200074)`(헤더 #25 이벤트 표의 절대 주소)** — 호출 시점엔 맵 번호 변수가 아직 0 이라(캐시 우회로 읽어도 0, 실측) 못 쓰고, 적재된 헤더 포인터가 맵마다 달라 열쇠가 된다. 이벤트 색인은 맵 헤더 #25 표 기준 **부호 있는** 색인(음수 = 앞 대화 스크립트 칸).
"""

import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import codearea as CA
import subtitle_stub as SS

BASE = SS.BASE
CALL_LIT = 0x0600A518  # `FDC0` 호출의 풀 리터럴(맵 입장 이벤트)
CALL_LIT_ORIG = 0x0600FDC0
KEYPTR = 0x20200074  # 적재된 맵 헤더 #25(이벤트 표) 포인터 칸 — 값이 맵마다 다르다
FLAGS = 0x002FFCE4  # 타입 0 진행 깃발 바이트열 — 깃발 N = +(N>>3) 비트 N&7 · 🔴 타입 1·2 는 다른 배열(타입 2 = 0x2FFD64 = FLAGS + 0x80, 평가기 `0x0600D6F4` 실측)

#   (맵, 이벤트 색인, 깃발 바이트 오프셋, 켤 비트 마스크, 끌 비트 마스크) — V## · 들어갈 좌표(디버그 맵 설정)
#   🔴 색인은 원판 맵의 헤더 #25 표에서 구했다(`test_voicecheck` 가 원본이 있으면 다시 확인한다).
TABLE = [
    ("V02", 2, 0x15E60, 1, 0, 0x00, 0x00, (25, 38)),
    ("V03", 5, 0x0FF7C, 3, 0, 0x00, 0x00, (21, 71)),
    ("V04", 6, 0x1D714, 1, 9, 0x04, 0x08, (41, 7)),  # 깃발 0x4a 켬 · 0x4b 끔(`FD 03` 뛰는 조건을 거짓으로)
    ("V05", 14, 0x1C8B4, -37, 128 + 0x13, 0x20, 0x00, (58, 47)),  # 타입 2 깃발 0x09d(= 0x2FFD64 + 19, 비트 5) 켬 — 깃발 N 칸은 타입 0 기준 +0x93
    ("V06", 15, 0x1C404, -6, 0, 0x00, 0x00, (193, 134)),
    ("V07", 17, 0x11D08, -20, 0, 0x00, 0x00, (135, 78)),
    ("V08", 19, 0x14A30, -23, 0, 0x00, 0x00, (70, 96)),
    ("V09", 35, 0x10A94, -13, 0, 0x00, 0x00, (142, 90)),
    ("V10", 31, 0x1B004, -21, 62, 0x80, 0x00, (232, 15)),  # 깃발 0x1f7(503) 켬 — 스크립트 머리 `FD 03` 이 이 깃발 없으면 바로 끝낸다(`FF FF`). 켜면 병사 방 장면이 돈다
    ("V11", 56, 0x1BBB8, -21, 0, 0x00, 0x00, (38, 192)),
    ("V12", 60, 0x17118, -3, 106, 0x02, 0x00, (93, 40)),  # 깃발 0x351 켬
    ("V13", 46, 0x14DEC, -15, 0, 0x00, 0x00, (50, 178)),
    ("V14", 47, 0x16D04, -3, 0, 0x00, 0x00, (179, 54)),
    ("V15", 49, 0x14874, -30, 0, 0x00, 0x00, (68, 87)),
    ("V16", 66, 0x0C7D4, -22, 0, 0x00, 0x00, (51, 50)),
    #   후크 장면(V01·V17~V19) — 색인 = 후크(음성 앞 스텁) 위치 바로 앞에서 시작하는 이벤트 칸(헤더 #25 표 키 뒤쪽은 양수 색인). 좌표는 시도값
    ("V01", 76, 0x1D01C, 6, 0, 0x00, 0x00, (58, 47)),  # 색인 5 는 맵 이동 전환 칸(검은 화면 대기) — 음성은 도착 이벤트 6 에서 시작
    ("V17", 83, 0x15438, 9, 0, 0x00, 0x00, (190, 75)),
    ("V18", 3, 0x142E8, 2, 0, 0x00, 0x00, (58, 47)),
    ("V19", 52, 0x152C8, 1, 0, 0x00, 0x00, (58, 47)),
]
#   표 열쇠 = 맵 파일 안 오프셋 + 0x200000 (헤더 #25 가 가리키는 절대 주소) — 맵 번호는 호출 시점에 아직 없다.
#   🔴 **후크 장면은 처음부터 보면 `c` 를 수십 번 눌러야 한다**(V17 64번 · V19 98번 — 실측 11-07) — 그래서 이 행들은 **음성 앞 후크 자리에서 곧장 시작**한다:
#     색인 칸이 `0x80` 이면 나머지 세 바이트(깃발 오프셋·켜기·끄기 칸)는 「열쇠 − 시작 오프셋」 24비트이고, 스텁은 이벤트 시작 루틴을 안 부르고 VM 시작 포인터
#     (`*(0x0609408C)`)에 `열쇠 − 그 값` 을 직접 쓰고 돌아온다. 후크 자리는 원본 옵코드 낱말 경계(`FD 00` 점프가 놓인 자리)라 안전하다.
#     앞 대사·연출이 빠져 배경에 인물이 없을 수 있다 — 음성·자막만 보는 용도다. 후크는 열쇠(표 시작)보다 앞에 있다(넷 다).
ABS = {"V17": 0x1436E, "V18": 0x13CFE, "V19": 0x145A4}  # 맵 파일 안 오프셋(`script/voice.json` 첫 후크)
VMPTR = 0x0609408C  # 스크립트 VM 의 현재 스크립트 포인터
ROW = 8  # 열쇠(u32) · 색인 · 깃발 오프셋 · 켜기 · 끄기


def table_bytes():
    out = b""
    for v, _m, key, ev, off, on, clr, _xy in TABLE:
        if v in ABS:
            d = key - ABS[v]
            assert 0 < d < 1 << 24
            out += struct.pack(">IB", 0x200000 + key, 0x80) + d.to_bytes(3, "big")
        else:
            out += struct.pack(">IbBBB", 0x200000 + key, ev, off, on, clr)
    return out + b"\x00\x00\x00\x00"


def build(at):
    """`(코드+풀 bytes, 라벨)` — `at` 에 앉는다."""
    a = SS.Asm(at)
    a.movl_pc(1, "keyptr")  # r1 = 0x00200074
    a.movl_at(1, 1)  # r1 = 헤더 #25 절대 주소(맵마다 다르다)
    a.movl_pc(2, "tab")
    a.label("L")
    a.movl_at(0, 2)  # mov.l @r2,r0 — 표의 열쇠
    a._e(0x2008)  # tst r0,r0 (끝 표지 0)
    a._e(0x8900)  # bt done  (아래에서 고친다)
    pos_bt_done = len(a.w) - 1
    a.cmp_eq(0, 1)  # cmp/eq r1,r0
    a._e(0x8900)  # bt found
    pos_bt_found = len(a.w) - 1
    a._e(0xA000)  # bra L
    pos_bra = len(a.w) - 1
    a.add(2, ROW)  # (지연 슬롯) r2 += 8
    a.label("found")
    a._e(0x8424)  # mov.b @(4,r2),r0   (이벤트 색인 — 0x80 = 후크 자리에서 곧장 시작)
    a._e(0x6403)  # mov r0,r4
    a._e(0x8880)  # cmp/eq #-128,r0
    a._e(0x8900)  # bt abs (아래에서 고친다)
    pos_bt_abs = len(a.w) - 1
    a._e(0x8425)  # mov.b @(5,r2),r0   (깃발 오프셋)
    a._e(0x630C)  # extu.b r0,r3 — 깃발 오프셋은 부호 없는 바이트(타입 2 배열은 +0x80 이상)
    a.movl_pc(5, "flags")
    a._e(0x353C)  # add r3,r5
    a._e(0x6050)  # mov.b @r5,r0
    a._e(0x6603)  # mov r0,r6
    a._e(0x8426)  # mov.b @(6,r2),r0   (켤 비트)
    a._e(0x260B)  # or r0,r6
    a._e(0x8427)  # mov.b @(7,r2),r0   (끌 비트)
    a._e(0x6007)  # not r0,r0
    a._e(0x2609)  # and r0,r6
    a._e(0x6063)  # mov r6,r0
    a._e(0x2500)  # mov.b r0,@r5
    a.label("done")
    a.movl_pc(0, "orig")
    a._e(0x402B)  # jmp @r0
    a._e(0x0009)  # nop
    a.label("abs")
    a._e(0x5021)  # mov.l @(4,r2),r0   0x80·dd·dd·dd
    a._e(0x4018)  # shll8 r0
    a._e(0x4019)  # shlr8 r0 → 24비트 거리
    a.movl_at(1, 2)  # mov.l @r2,r1  = 열쇠(절대)
    a._e(0x3108)  # sub r0,r1  → r1 = 열쇠 − 거리 = 후크 절대 주소
    a.movl_pc(0, "vmptr")
    a._e(0x2012)  # mov.l r1,@r0 — VM 스크립트 포인터
    a._e(0x000B)  # rts
    a._e(0x0009)  # nop
    #   분기 변위 고치기 — bt/bra: 변위 = (목표 − (자리+4)) / 2
    def disp(pos, target):
        here = at + pos * 2
        d = (target - (here + 4)) // 2
        return d

    a.w[pos_bt_done] = 0x8900 | (disp(pos_bt_done, a.lbl["done"]) & 0xFF)
    a.w[pos_bt_found] = 0x8900 | (disp(pos_bt_found, a.lbl["found"]) & 0xFF)
    a.w[pos_bt_abs] = 0x8900 | (disp(pos_bt_abs, a.lbl["abs"]) & 0xFF)
    a.w[pos_bra] = 0xA000 | (disp(pos_bra, a.lbl["L"]) & 0xFFF)
    #   풀(4 정렬)
    while a.at() % 4:
        a._e(0x0009)
    pool = {}
    tab_at = a.at() + 5 * 4  # 풀 다섯 칸(keyptr · flags · orig_lit · vmptr · tab 주소) 바로 뒤에 표가 온다
    for name, val in (("keyptr", KEYPTR), ("flags", FLAGS), ("orig", CALL_LIT_ORIG), ("vmptr", VMPTR), ("tab", tab_at)):
        pool[name] = a.at()
        a._e(val >> 16)
        a._e(val & 0xFFFF)
    assert a.at() == tab_at
    tb = table_bytes()
    for i in range(0, len(tb), 2):
        a._e(int.from_bytes((tb[i : i + 2] + b"\x00")[:2], "big"))
    #   pc 상대 적재 변위 고치기: 변위 = (풀 − ((자리 & ~3) + 4)) / 4
    for idx, name, kind in a.fix:
        here = at + idx * 2
        d = (pool[name] - ((here & ~3) + 4)) // 4
        assert 0 <= d < 256 and (pool[name] - ((here & ~3) + 4)) % 4 == 0, (name, d)
        a.w[idx] |= d
    blob = b"".join(struct.pack(">H", w) for w in a.w)
    assert len(blob) <= CA.VCHK_ROOM, len(blob)
    return blob


def patch(data):
    """`/0.BIN` 의 풀 리터럴 하나만 바꾸고 스텁은 코드 예약 칸에 둔다."""
    out = bytearray(data)
    blob = build(CA.VCHK)
    CA.put(out, BASE, CA.VCHK, blob)
    off = CALL_LIT - BASE
    assert out[off : off + 4] == struct.pack(">I", CALL_LIT_ORIG), "호출 리터럴이 예상과 다르다"
    out[off : off + 4] = struct.pack(">I", CA.VCHK)
    return bytes(out)


def coord_table():
    return [(v, f"MAP{m:03d}", xy) for v, m, _k, _ev, _o, _on, _c, xy in TABLE]


if __name__ == "__main__":
    b = build(CA.VCHK)
    print(f"스텁 {len(b)}B @ {CA.VCHK:#x} (여유 {CA.VCHK_ROOM - len(b)}B)")
    for v, m, xy in coord_table():
        print(f"  {v}  {m}  들어갈 좌표 X={xy[0]} Y={xy[1]}")
