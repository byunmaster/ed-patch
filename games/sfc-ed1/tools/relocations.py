"""재배치 장부 — 빌드가 **실제로 한** 재배치를 좌표·종류·사유만으로 뽑는다(원문 바이트·문장은 넣지 않는다).

왜(마스터 10-22 「재배치를 진행한 부분들도 별도로 기록해두자. 정 안되면 나중에 되돌려야할수도 있으니」):
블록을 옮기고 중계 조각을 끼우면 엔진이 실제로 읽는 길이 원판과 달라진다. ss-ed3 에서 재조판이 대사 끝에 넣은 채움 바이트가
다음 블록 호출을 막아 첫 장면 대사가 통째로 빠진 사고(10-21)가 그 부류다. 장부는 두 곳에서 쓴다.
  1. 되돌릴 때의 지도 — 어느 블록을 어디서 어디로 옮겼고 왜 그랬나.
  2. 구조 대조 검사(`check_ctrl_flow.py`)의 **허용 목록** — 롬을 걸어 본 결과 원판과 좌표가 다른 블록·중계 조각이 장부에 없으면 실패.
장부는 손으로 쓰지 않는다 — `build.py --kr` 가 빌드 칸에 `relocations.tsv` 후보를 쓰고, 커밋되는 `games/sfc-ed1/relocations.tsv`
와 다르면 게이트가 운다(`check_ctrl_flow.py --freeze` 로 갱신).

열: 블록 키 · 종류 · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면 생기는 일 (좌표는 SNES `$BB:AAAA`)
종류: 옮김(본체 이관) · 스텁(FC 중계 조각 · FD 중계) · 포인터(표 항목 재기입) · 채움(비운 자리·복원 자리) · 쪽 넘김(0건 — 아래 머리줄)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

HEADER = ["블록 키", "종류", "원래 좌표", "새 좌표", "사유", "엔진 근거", "되돌리면 생기는 일"]

# 엔진 근거 — `message.asm`($02:DC41~F22C) 디스어셈블에서 읽은 주소(text.py 머리 · script.py 머리 · build.py 주석에 이미 적힌 것만 쓴다)
EV_PTR = "표 선택 $02:DD00~ · 포인터 읽기 $02:E784(16비트만 올림) · 디스패치 $02:E216 / 표 $02:E248"
EV_CALL = "F9 절대 호출 $02:E53F(호출 틀을 안 쌓음 — $02:E7A0 안 부름) · FC 상대 호출은 같은 뱅크 rel16 · 디스패치 $02:E248"
EV_FD = "FD 는 호출이라 복귀 주소가 FD+6($02:E6BA) · 슬롯은 제어 바이트 기준 8비트 · 디스패치 $02:E248"

NO_SWITCH = "되돌릴 수단 없음 — "


def _s(off: int) -> str:
    return common.fmt(common.off2snes(off)) if off >= 0 else "-"


def rows(k: dict, pk: dict, full_place: dict, place: dict, rom: bytes, out: bytes, ptr_names, body, pinned) -> list[list[str]]:
    """장부 행. `k`=kr_items 결과 · `pk`=pack_banks 결과 · `ptr_names`=(표 이름, 번호, 원래 포인터, 새 포인터, 꼬리 여부) 목록."""
    new, orig, slices, seg_of = k["items"], k["orig_items"], k["slices"], k["seg_of"]
    seg_items: dict[int, list[int]] = {}
    for idx, si in seg_of.items():
        seg_items.setdefault(si, []).append(idx)
    R: list[list[str]] = []

    # 1. 옮김 — 본체의 모든 조각(번역·미번역 모두)이 확장 뱅크 군집으로 이관된다
    for si, (sid, a, e) in enumerate(slices):
        o0 = orig[a].off
        n0 = place.get(o0)
        if n0 is None or n0 == o0:
            continue
        jp = sum(it.size for it in orig[a:e])
        kr = sum(new[i].size for i in seg_items.get(si, []))
        st = "번역 조각" if kr != jp else "원문 크기 그대로"
        R.append(
            [
                sid,
                "옮김",
                _s(o0),
                _s(n0),
                f"본체 구간 전체를 군집 {k['comp_of'][si]} 로 이관 — {st}(원문 {jp}B → 새 {kr}B, {kr - jp:+d}B)",
                EV_PTR,
                NO_SWITCH + "한글 문안이 원문보다 길어 원 자리에 못 넣는다. 조각 단위 스위치 없음(원 자리를 비웠으므로 표·분기 목표가 함께 바뀐다)",
            ]
        )

    # 2. 스텁 — FC 중계 조각(군집 밖 목표) · FD 중계(슬롯 8비트 초과)
    for lst in k["stubs"].values():
        for key, t in lst:
            R.append(
                [
                    f"FC중계@{_s(t)}",
                    "스텁",
                    _s(t),
                    _s(place[key]),
                    "FC 호출 목표가 다른 군집(다른 뱅크) — rel16 은 같은 뱅크만 닿으므로 호출자 군집 끝에 `FC +3 · F9 목표 · FE` 8B 를 둔다",
                    EV_CALL,
                    NO_SWITCH + "되돌리면 FC 가 뱅크를 넘는 rel16 이 돼 엔진이 엉뚱한 곳을 읽는다(군집 결속으로 대체하면 군집이 32KB 를 넘는다)",
                ]
            )
    for i, it in enumerate(new):
        if it.kind == "ctrl" and it.code == 0xFD and it.relay:
            R.append(
                [
                    f"FD중계@{_s(it.off)}",
                    "스텁",
                    _s(it.off),
                    _s(pk["new_off"][i]),
                    f"FD 슬롯 거리가 8비트를 넘음 — FD 뒤에 `FA 건너뛰기` + 슬롯마다 `FA 목표`({3 + 3 * it.n_relays()}B 추가)",
                    EV_FD,
                    NO_SWITCH + "되돌리면 슬롯 오프셋이 8비트를 넘어 엉뚱한 곳으로 뛴다",
                ]
            )

    # 3. 포인터 — 메시지 표 항목 재기입(본체가 옮겨졌으므로)
    for name, idx, old, newp, tail in ptr_names:
        R.append(
            [
                f"{name}[{idx:#06x}]",
                "포인터",
                common.fmt(old),
                common.fmt(newp),
                "포인터 전용 별도 메시지(pointer_tail)" if tail else "표가 가리키는 문안이 이관됨",
                EV_PTR,
                NO_SWITCH + "옮김 행을 되돌릴 때 함께 되돌려야 한다",
            ]
        )

    # 4. 채움 — 본체를 FF 로 비운 자리 · 복원한 고정 구간
    lo, hi = common.snes2off(body[0]), common.snes2off(body[1])
    R.append(
        [
            "본체",
            "채움",
            _s(lo),
            _s(hi),
            "원래 자리를 FF 로 비움(숨은 독자 검출) — 이관한 뒤 원 자리를 읽는 길이 있으면 FF=쪽 대기 코드를 실행하게 된다",
            "FF=PAGE 코드. 이 구간으로 가는 길이 0 임은 구조 대조 검사가 롬을 걸어 확인한다(도달 0)",
            NO_SWITCH + "원 자리에 둔 채로 두면 이관과 이중 사본이 돼 낡은 일본어 문안이 읽힌다(옛 사고: 미니게임 죽은 사본)",
        ]
    )
    for a, b in pinned:
        R.append(
            [
                "고정 구간",
                "채움",
                _s(a),
                _s(b),
                "비운 본체 안에서 원문 그대로 복원한 구간(네이티브 코드가 직접 읽는다)",
                "EE 네이티브 호출·JSL 이 절대 주소로 읽음(text.py TEXT_END 주석)",
                NO_SWITCH + "복원을 끄면 그 호출이 FF 를 실행한다",
            ]
        )
    # 쪽 넘김 — 추가한 적 없음(0건)을 행으로 남기지 않고 머리줄에 적는다(render)
    return R


def render(R: list[list[str]], counts_extra: str = "") -> str:
    kinds: dict[str, int] = {}
    for r in R:
        kinds[r[1]] = kinds.get(r[1], 0) + 1
    head = (
        "# sfc-ed1 재배치 장부 — 빌드가 자동으로 뽑는다(tools/relocations.py). 손으로 고치지 않는다 · 원문 바이트·문장 없음.\n"
        "# 종류별 건수: "
        + " · ".join(f"{k} {kinds.get(k, 0)}" for k in ("옮김", "스텁", "포인터", "채움", "쪽 넘김"))
        + "  (쪽 넘김은 빌드가 추가하는 경우가 없다 — 구조 대조 검사가 0 임을 걸어서 확인한다)\n"
        "# 되돌리기 스위치: 종류·블록 어느 쪽도 없다. 이유는 행마다 적었다.\n" + counts_extra
    )
    return head + "\t".join(HEADER) + "\n" + "".join("\t".join(r) + "\n" for r in R)
