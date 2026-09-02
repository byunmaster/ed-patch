"""인게임 음성 자막 — **트램펄린**으로 대사창을 끼운다.

    python3 games/ss-ed3/tools/voice_sub.py --plan          # 무엇을 어디에 넣나 (안 굽는다)
    python3 games/ss-ed3/tools/voice_sub.py --apply         # 구운 이미지에 적용

🔴 **길이를 안 늘리고 포인터도 안 옮긴다.** 스크립트에 흐름 제어가 있어서 가능하다
   (`/0.BIN` 디스패치 표 `0x0600ce20`, 갈래 `0xFD`):

       FD 00 <BE32>   GOTO     32비트를 PC 에 그대로 넣는다      6바이트
       FD 01 <BE32>   CALL     복귀주소를 스택에 밀고 점프       6바이트
       FD 02          RETURN   스택에서 꺼내 PC 로               2바이트

   후킹 지점의 명령 하나(≥6바이트)를 `FD 00 <우리블록>` 으로 덮고, 우리 블록에서
   **밀어낸 명령을 그대로 실행한 뒤** 자막을 띄우고 `FD 00` 으로 돌아온다.
   ⇒ 원래 동작을 하나도 안 잃고, 스크립트 길이가 1바이트도 안 변한다.

🔴 **자막은 파일 끝 「섹터 여백」에 붙인다.** MAP076.BIN 은 119,008B 인데 디스크에서
   59섹터(120,832B)를 차지한다 — 그 1,824B 는 자기 익스텐트 안의 패딩이라 앞뒤 파일과
   안 겹친다(실측: MAP075.FON 이 LBA 22610 에서 끝나고 MAP076.ED3 가 22669 에서 시작).
   ⚠ 파일 **안**의 0런(12.5KB)은 쓰지 않는다 — 「0런 3중 검증을 통과해도 사운드 뱅크
     안이라 효과음이 조용히 깨진」 전례가 있다. 섹터 여백은 그 위험이 없다.
   ⇒ 대신 **ISO 디렉터리 레코드의 크기**를 같이 늘려야 엔진이 그만큼 읽어 온다.

✅ **인게임에서 확인했다**(2026-08-30, MAP076 순례의 아침). 자막은 대사창으로 뜨고,
   **입력으로 안 닫히며 정한 시간이 지나면 저절로 닫힌다** — 아래 `TERM_NOWAIT` 절 참조.
"""

import argparse
import json
import os
import struct
import sys
from itertools import pairwise

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import common as C
import hangul_map as H

from shared.disc import mode1

SCRIPT = os.path.join(C.GAME_DIR, "script", "voice.json")
BASE = 0x200000  # 스크립트 포인터 기준 (mapfile.BASE 와 같다)
SECTOR = 2048
GOTO = b"\xfd\x00"


def goto(file_off):
    return GOTO + struct.pack(">I", BASE + file_off)


#   🔴 **대사 한 칸은 `02 <화자ID>` 만으로는 안 뜬다.** 앞에 창을 여는 옵코드 둘이 붙는다 —
#     실측(MAP076 블록 #59, `0x1ba0c`): `FF 02 00 02` · `FF 00` · `02 16` · 본문 · `16`.
#     ⚠ 이걸 빼고 넣었더니 **스크립트는 멀쩡히 지나가는데 화면에 아무것도 안 나왔다**
#       (에뮬 램에 직접 얹어 확인, 2026-08-30). 빌드도 검사도 다 통과하는 부류의 사고다.
#     `FF 00`·`FF 02` 는 창 상태(`0x06093f20` & 63)를 보고 조건이 안 맞으면 `PC -= 2` 로
#     되돌려 **다음 프레임에 다시 시도**한다.
#
#   🔴 **창 종류를 잘못 고르면 컷신이 깨진다** — `FF 02 <종류>` 의 값이 갈린다(실측 2026-08-31):
#
#       00 02  위쪽 큰 창   🔴 배우가 복제되고 **그 뒤 스크립트가 아예 안 이어진다**
#       00 01  아래쪽 창    ✅ 이름칸·얼굴 그림 다 나오고 컷신도 정상 (실제 스크립트도 132 회 쓴다)
#       00 00  닫기
#
#     ⚠ `00 02` 로 넣었을 때 배우가 둘로 보이고 뒤 대사가 통째로 안 나왔다. 원인을
#       한참 「트램펄린」·「죽은 코드」로 오해했는데, **창 종류 한 바이트**였다.
#     ⓘ `FF 87`(위쪽 얇은 띠)도 컷신을 안 깨뜨리지만 **한 줄 22 자**에 이름칸이 없다.
WIN_OPEN = b"\xff\x02\x00\x01\xff\x00"


#   🔴 **화자 ID 는 이름표의 색인이다.** 아무 값이나 쓰면 창은 열리는데 **글자가 안 그려진다** —
#     실측으로 `02 01` 이 그랬다(빈 창만 떴다 닫혔다). 실제 대사가 쓰는 값이어야 한다.
#   이름표는 맵 안의 **32 바이트 간격 표**다. MAP076 은 `0x1a0ae` + 색인×0x20:
#     0x14 쥬리오아빠 · 0x15 쥬리오엄마 · 0x16 크리스아빠 · 0x17 크리스엄마 · 0x18 톨타 촌장 ·
#     0x19 로그 · 0x1a 픽 · 0x1b 치아나 · 0x1c 스콜 · 0x1d 페르나부인 · 0x1e 도구점 테르노 · 0x1f 키리
#   ⚠ **맵마다 표가 다르다** — 다른 장면에 넣을 땐 그 맵의 표를 다시 읽는다.
SPEAKER = 0x15  # 쥬리오엄마 — V01 장면의 화자

#   🔴 **자막은 「입력으로 안 닫히고 시간이 지나면 저절로 닫히는」 창이어야 한다**(유저 확정).
#     음성이 흐르는 동안 떠 있어야 하고, 플레이어가 무심코 누른 버튼에 사라지면 안 된다.
#     실측으로 끝맺음 바이트가 그걸 가른다(2026-08-30):
#
#       본문 뒤 `10 00`  → **입력 대기**. 진짜 대사가 쓰는 것이고, C 를 누르면 닫힌다.
#       본문 뒤 `00`     → 대기 없음. 그대로 두면 **안 닫히니** 시간과 닫기를 우리가 준다.
#
#     ⚠ mapfile 의 `term`(`0x16`·`0x14`)은 **끝맺음이 아니다** — 그건 그저 블록 뒤 바이트다.
#       그걸 끝맺음으로 넣었더니 메시지 처리기가 상위 니블만 보고(`and #240`) 본문으로 여겨
#       계속 읽어 나갔다(읽기 브레이크포인트로 확인).
#     ⚠ 창은 **`FF 02 00 00` 이 닫는다** — 진짜 대사도 끝맺음 뒤에 늘 이게 온다.
TERM_NOWAIT = b"\x00"  # 입력 대기 없음
WIN_CLOSE = b"\xff\x02\x00\x00"


#   🔴 **유지 시간을 우리가 주면 안 된다.** `FF 35` 로 붙잡으면 그만큼 **장면이 늘어지는데
#     음성은 제 속도로 흐른다** — 줄이 늘수록 어긋난다(2026-08-31).
#   ⇒ 대신 **열어 둔 채 다음 후킹에서 닫고 새로 연다.** 끝맺음이 `00` 이면 창은 저절로
#     안 닫히므로, 자막이 떠 있는 시간 = **원작이 그 자리에 둔 `FF 35` 대기**가 된다.
#     그 대기가 음성과 맞는다는 건 실측으로 확인했다(V01: 다섯 자리가 ±0.8 초).
#   ⇒ 장면에 더해지는 시간은 **0** 이고, 싱크를 우리가 계산할 일도 없다.
#   🔴 **자막을 게임 대사창으로 그리면 컷신과 얽힌다.** 창 열기는 창이 준비될 때까지
#     스크립트를 멈추는데(`PC -= 2` 되돌림) 배우 태스크는 계속 돌아, 걸어 들어오던 배우가
#     둘로 남는다. 창 종류를 바꿔도(`00 01`·`00 02`) 마찬가지였다(실측 2026-08-31).
#     ⓘ 레퍼런스의 선례 둘도 **게임 대사 시스템을 안 쓴다** — PS2 「제로3」은 프레임버퍼
#       스왑을 후킹해 매 프레임 직접 그리고, PC엔진 「악마성」은 스프라이트로 직접 그린다
#       (`docs/reference/worklog-consoles.md`). 최종형은 그쪽이다.
#   ⇒ 그 전 단계로 **`FF 87`(위쪽 얇은 띠)** 를 쓴다 — 엔진의 「알림」 계통이라 대사창과
#     경로가 다르고, 실측에서 복제가 안 났다.
#     ⚠ **한 줄 22 자**다. 넘으면 통째로 안 그려진다(잘리지 않는다).
BAND = b"\xff\x87\x00\x00"
BAND_END = b"\x00\x09"
BAND_MAX = 22


def band(body):
    """위쪽 띠 자막 — `FF 87` + 본문 + 끝맺음. 화자 이름칸은 없다."""
    if len(body) > BAND_MAX:
        raise SystemExit(f"띠 한 줄은 {BAND_MAX}자까지다({len(body)}자): {body!r}")
    if "\n" in body:
        raise SystemExit(f"띠는 한 줄만 된다: {body!r}")
    return BAND + H.encode_kr(body) + BAND_END


def block(body, speaker=SPEAKER, hold=None):
    """자막 한 칸 — 앞 창을 닫고 · 새 창을 열고 · 본문(입력 대기 없음).

    ⚠ **닫기를 여기서 안 한다.** 다음 자막이 닫는다.
    ⚠ 단 **장면의 마지막 자막**은 뒤에 후킹할 자리가 없어 그대로 남는다 — 그때만
      `hold`(초)를 줘서 `FF 35` + 닫기를 붙인다. 한 번뿐이라 늘어지는 시간이 무해하다.
    """
    out = WIN_CLOSE + WIN_OPEN + bytes((0x02, speaker)) + H.encode_kr(body) + TERM_NOWAIT
    if hold:
        out += b"\xff\x35" + struct.pack(">H", max(1, min(0xFFFF, round(hold * 60)))) + WIN_CLOSE
    return out


#   🔴 **후킹 지점의 길이는 「그 처리기가 PC 에 쓰는 자리를 전부」 보고 정한다.**
#     표를 믿지 말 것 — 자리마다 길이가 다른 옵코드가 실재한다(`FF 36`·`FF 0A`,
#     `script_ops.py` 참조). 지금 쓰는 `FF 07`(`0x1bc7c`)은 처리기 `0x06011608` 안에서
#     PC 저장이 **`0x0601170c` 한 곳뿐이고 거기서 항상 `+12`** 라 분기와 무관하게
#     2+12=14 고정이다(2026-08-30 확인). 다른 자리로 옮길 땐 같은 검산을 다시 한다.
def plan_one(raw, hooks):
    """`(붙일 바이트, [(오프셋, 덮을 바이트)])` — 트램펄린 **여러 벌**.

    자막이 한 줄이 아니라 장면 내내 여러 번 뜨므로, 후킹도 대사마다 하나씩 건다.
    붙이는 블록은 **옛 파일 끝부터 차례로** 쌓고, 각 후킹은 자기 블록으로 점프한다.
    """
    n = len(raw)
    pad_room = (-n) % SECTOR
    tail, patches = bytearray(), []
    for h in hooks:
        if h["len"] < len(GOTO) + 4:
            raise SystemExit(f"{h['off']:#x}: 후킹 지점이 짧다({h['len']}B) — GOTO 6B 가 안 든다")
        here = n + len(tail)  # 이 벌이 놓일 자리
        tail += raw[h["off"] : h["off"] + h["len"]]  # 밀어낸 명령 그대로
        if not h["lines"]:
            tail += WIN_CLOSE  # 마지막 자막을 닫는 자리
        for j, t in enumerate(h["lines"]):
            last = j == len(h["lines"]) - 1
            if h.get("style", "band") == "band":
                tail += band(t)
            else:
                tail += block(t, h.get("speaker", SPEAKER), h.get("hold") if last else None)
        tail += goto(h["off"] + h["len"])  # 밀어낸 명령 **뒤**로 복귀
        patches.append((h["off"], goto(here)))
    if len(tail) > pad_room:
        raise SystemExit(f"여백 부족: 필요 {len(tail)}B · 여유 {pad_room}B")
    #   ⚠ 후킹끼리 겹치면 서로를 덮는다 — 6 바이트씩 잡아 두고 본다
    seen = sorted((h["off"], h["off"] + len(GOTO) + 4) for h in hooks)
    for (a1, b1), (a2, _) in pairwise(seen):
        if a2 < b1:
            raise SystemExit(f"후킹 지점이 겹친다: {a1:#x} 와 {a2:#x}")
    return bytes(tail), patches


def load_plan():
    if not os.path.exists(SCRIPT):
        raise SystemExit(f"자막 정본이 없다: {SCRIPT}")
    with open(SCRIPT, encoding="utf-8") as f:
        return json.load(f)


def dir_record(d, path_in_iso):
    """`(레코드가 든 섹터 LBA, 그 섹터 안 오프셋)` — 그 파일의 ISO 디렉터리 레코드 자리.

    ⚠ 디렉터리는 **여러 섹터**다(`/MAP` 은 352 항목). 익스텐트 첫 섹터만 읽고 오프셋을
      그대로 쓰면 엉뚱한 자리를 고친다 — 섹터 단위로 쪼개 돌려준다.
    """
    want = path_in_iso.rsplit("/", 1)[1].encode("ascii")
    root = d.pvd()[156 : 156 + 34]
    stack = [(int.from_bytes(root[2:6], "little"), int.from_bytes(root[10:14], "little"), "")]
    while stack:
        lba, size, path = stack.pop()
        data = d.read_extent(lba, size)
        pos = 0
        while pos < len(data):
            rl = data[pos]
            if rl == 0:
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            rec = data[pos : pos + rl]
            name = rec[33 : 33 + rec[32]]
            full = f"{path}/{name.decode('ascii', 'replace').split(';')[0]}"
            if name not in (b"\x00", b"\x01"):
                if rec[25] & 0x02:
                    stack.append(
                        (
                            int.from_bytes(rec[2:6], "little"),
                            int.from_bytes(rec[10:14], "little"),
                            full,
                        )
                    )
                elif full == path_in_iso and name.split(b";")[0] == want:
                    return lba + pos // SECTOR, pos % SECTOR
            pos += rl
    raise KeyError(path_in_iso)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--disc", type=int, default=1)
    a = ap.parse_args()
    if not (a.plan or a.apply):
        ap.error("--plan 또는 --apply")

    doc = load_plan()
    with C.open_disc(a.disc) as d:
        for key, ent in sorted(doc.items()):
            if key.startswith("_"):
                continue
            iso = f"/MAP/{ent['map']}.BIN"
            _, lba, size = d.find(iso)
            raw = d.read_extent(lba, size)
            hooks = ent.get("hooks") or [{**ent["hook"], "lines": ent["lines"]}]
            tail, patches = plan_one(raw, hooks)
            print(f"── {key}  {iso}  {size:,}B → {size + len(tail):,}B  (여백 {(-size) % SECTOR}B)")
            at = size
            for h in hooks:
                print(f"   후킹 {h['off']:#07x} ({h['len']}B) → {at:#07x}")
                for t in h["lines"]:
                    print(f"        {t!r}")
                at += (
                    h["len"]
                    + sum(
                        len(band(t) if h.get("style", "band") == "band" else block(t))
                        for t in h["lines"]
                    )
                    + (14 if h.get("hold") else 0)
                    + (len(WIN_CLOSE) if not h["lines"] else 0)
                    + len(GOTO)
                    + 4
                )
            if not a.apply:
                continue
            img = os.path.join(C.BUILD_DIR, f"Shiroki Majo (KR) (Disc {a.disc}).bin")
            if not os.path.exists(img):
                raise SystemExit(f"{img} 가 없다 — 먼저 build.py")
            drl, dro = dir_record(d, iso)
            with open(img, "r+b") as f:
                for off, by in patches:
                    mode1.write_at(f, lba, size, off, by, label=f"{key} 후킹")
                mode1.write_at(f, lba, size + len(tail), size, tail, label=f"{key} 자막")
                #   디렉터리 레코드의 크기(양끝 엔디언 8바이트)를 늘린다
                rec = d.read_extent(drl, SECTOR)[dro : dro + 34]  # 그 섹터 하나만 읽는다
                new = struct.pack("<I", size + len(tail)) + struct.pack(">I", size + len(tail))
                assert rec[10:18] == struct.pack("<I", size) + struct.pack(">I", size), rec[
                    10:18
                ].hex()
                mode1.write_at(f, drl, SECTOR, dro + 10, new, label=f"{key} 디렉터리")
            print("   ✅ 적용")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
