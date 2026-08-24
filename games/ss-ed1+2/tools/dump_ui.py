"""HUD·시스템 메뉴 문자열을 자리·여유와 함께 뜬다 → work/derived/ui_jp.json.

본편 UI 는 별도 파일이 아니라 **본체 둘(`ED.BIN`·`ED2.BIN`) 안**에 있다. 그런데 대사와
달리 **고정폭 레코드 표**다 — 포인터(BE32 리터럴 풀)는 **표의 첫 항목만** 가리키고 나머지는
코드가 색인으로 집는다(실측: `ＯＮ`·`ＯＦＦ` 는 가리키는 포인터가 아예 없다).

🔴 그래서 **레코드 폭이 딱딱한 제약**이다. 문안을 늘려 다음 칸을 침범하면 포인터는 멀쩡한데
   메뉴가 통째로 밀린다 — 빌드도 검사도 통과하고 화면만 깨진다. 여기서 `stride` 를 정본으로
   두고 재삽입기가 매번 대조한다.

표 정의는 손으로 적는다(포인터·정렬로 자동 검출을 시도했으나 stride 를 2배로 잡는 오검출이
났다 — 표가 71개나 나오고 그중 진짜는 스물 남짓이었다). 대신 **원본 문자열을 같이 박아**
사전조건으로 쓴다 — 원본이 우리 생각과 다르면 그 자리에서 실패한다.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common

# ── 표 정의 ────────────────────────────────────────────────────────────────
# (이름, ED.BIN 오프셋, ED2.BIN 오프셋, stride, 항목수)
#   ⚠ ED1·ED2 는 같은 표를 각자 갖는다. 배치가 어긋나 **차이가 일정하지 않다**
#     (ED2 의 능력치 표에 `呪文能力` 이 하나 더 있어 뒤가 10B 씩 밀린다) — 그래서 둘 다 적는다.
#   ⚠ 항목수가 다른 표는 `n2` 로 따로 준다.
TABLES = [
    # 이름                  ED       ED2      stride  n   n2
    ("필드 메뉴", 0x84368, 0x6993C, 10, 7, None),
    ("전투 명령", 0x843AE, 0x69982, 10, 8, None),
    ("전멸 후 선택", 0x843FE, 0x699D2, 20, 3, None),
    ("시스템 메뉴", 0x8443A, 0x69A0E, 10, 3, None),
    ("전투설정 제목", 0x84458, 0x69A2C, 10, 1, None),
    ("능력치", 0x84462, 0x69A36, 10, 6, 7),
    ("전투설정 항목", 0x8449E, 0x69A7C, 15, 6, None),
    ("자동전투 ON/OFF", 0x844F8, 0x69AD6, 8, 2, None),
    ("자동회복 ON/OFF", 0x84508, 0x69AE6, 8, 2, None),
    ("전투주문 사용", 0x84518, 0x69AF6, 10, 2, None),
    ("회복주문 사용", 0x8452C, 0x69B0A, 10, 2, None),
    ("회복아이템 사용", 0x84540, 0x69B1E, 10, 2, None),
    ("전원 설정", 0x84554, 0x69B32, 8, 2, None),
    ("환경설정 항목", 0x84564, 0x69B42, 15, 6, None),
    ("자동이동 ON/OFF", 0x845BE, 0x69B9C, 8, 2, None),
    ("레벨업 오토/수동", 0x845CE, 0x69BAC, 8, 2, None),
    ("EP 표시", 0x845DE, 0x69BBC, 8, 2, None),
    ("BGM ON/OFF", 0x845EE, 0x69BCC, 8, 2, None),
    ("이동 속도", 0x845FE, 0x69BDC, 8, 3, None),
    ("메시지 속도", 0x84616, 0x69BF4, 8, 4, None),
    ("예/아니오", 0x84636, 0x69C14, 8, 2, None),
    ("상점 매매", 0x84646, 0x69C24, 10, 2, None),
    ("장비 비교 항목", 0x8465A, None, 10, 5, None),
    ("전투설정/도망", 0x8468C, 0x69C38, 10, 2, None),
    # HUD — 상태이상 한 글자. 레코드가 4B 라 **한 자를 넘길 수 없다.**
    ("HUD 상태이상", 0x570BC, 0x390B0, 4, 6, None),
    ("HUD HP", 0x570A4, None, 4, 1, None),
]

# ── 지명 표 — 여기는 **정본이 다르다** ────────────────────────────────────────
# 메뉴 라벨은 같은 JP 가 자리마다 다른 말이 되지만(`強さ` = 상태/강함/힘) 지명은 안 그렇다.
# 그래서 표+색인이 아니라 **`shared/glossary` 의 평탄한 JP→KR** 로 옮긴다 — 대사·오프닝과
# 같은 표기를 쓰게 되고 우리가 목록을 손으로 들 필요도 없다.
# ⚠ 판마다 표가 둘이다 — **짧은 꼴**(`ルディア`)과 **긴 꼴**(`ルディアの町`). 하나만 고치면
#   한 화면 안에서 두 말을 한다.
# ⚠ 반각 가나 표(`ED.BIN` 0x84CCE~ `ｴﾙｱｽﾀ`·`ﾍﾞﾙｶﾞM`)는 **내부 키다** — 화면에 안 나온다.
#   글자가 지명처럼 보인다고 건드리면 자료를 부순다.
#   (이름, ED 오프셋, ED2 오프셋, stride, ED 칸수, ED2 칸수, 정본 범주)
GLOSSARY_TABLES = [
    ("지명", 0x84762, 0x69F41, 14, 48, 47, "place"),
    # ⚠ ED2 긴꼴은 **36칸**이다. 37 로 세면 마지막 레코드가 짧은꼴 표 머리(0x69F41)를
    #   물어 `エルアスタ` 를 덮는다 — `tools/tests/test_ui.py` 의 겹침 검사가 잡았다.
    ("지명 긴꼴", 0x84C8E, 0x69CF2, 16, 4, 36, "place"),
]

# ── 파티 기본 이름 — 새 게임 때 세이브로 복사되고 HUD 왼쪽 위에 뜬다 ──────────────
# ⚠ **stride 가 일정하지 않다.** 필드가 「이름 + 널 하나 이상 + 4바이트 정렬 패딩」이라
#   이름 길이에 따라 8B·12B 로 갈린다(`ロー` 4B→8B, `セリオス` 8B→12B). 여덟뿐이라
#   자리를 그대로 적는다.
#   (파일키, 오프셋, 필드길이)
PERSON_SLOTS = [
    ("ED", 0x438, 12),
    ("ED", 0x444, 12),
    ("ED", 0x450, 8),
    ("ED", 0x458, 8),
    ("ED2", 0x404, 12),
    ("ED2", 0x410, 12),
    ("ED2", 0x41C, 12),
    ("ED2", 0x428, 12),
]

FILES = {"ED": "/ED.BIN", "ED2": "/ED2.BIN"}
OUT = os.path.join(common.OUT_DIR, "ui_jp.json")


def read_table(buf, off, stride, n):
    """레코드 n 개 — `(원문, 자리, 여유바이트)`. 여유 = stride − (본문 + 널 1)."""
    out = []
    for i in range(n):
        p = off + i * stride
        rec = buf[p : p + stride]
        end = rec.find(b"\x00")
        assert end >= 0, f"0x{p:06x}: 레코드 안에 널이 없다 — stride {stride} 가 틀렸다"
        out.append((rec[:end].decode("cp932"), p, stride - end - 1))
    return out


def collect():
    tables = {}
    for key, path in FILES.items():
        buf = common.extract(path)
        col = 1 if key == "ED" else 2
        specs = [(nm, e1, e2, st, a, b) for nm, e1, e2, st, a, b in TABLES]
        specs += [(nm, e1, e2, st, a, b) for nm, e1, e2, st, a, b, _c in GLOSSARY_TABLES]
        for name, ed, ed2, stride, n, n2 in specs:
            off = (ed, ed2)[col - 1]
            if off is None:
                continue
            cnt = n2 if (col == 2 and n2) else n
            recs = read_table(buf, off, stride, cnt)
            tables[f"{key}/{name}"] = {
                "file": path,
                "offset": f"0x{off:06x}",
                "stride": stride,
                "records": [
                    {"i": i, "at": f"0x{p:06x}", "jp": t, "slack": s}
                    for i, (t, p, s) in enumerate(recs)
                ],
            }
    return tables


def main():
    common.verify_source()
    tables = collect()
    os.makedirs(common.OUT_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(
            {"_doc": "HUD·시스템 메뉴 원문 — dump_ui.py 산출", "tables": tables},
            f,
            ensure_ascii=False,
            indent=1,
        )
    n = sum(len(t["records"]) for t in tables.values())
    print(f"표 {len(tables)} · 레코드 {n} → {OUT}")
    # 폭 요약 — 한글 몇 자까지 들어가나 (전각 2B, 널 1B)
    for k, t in tables.items():
        cap = (t["stride"] - 1) // 2
        jp = " ".join(r["jp"].replace("　", "·") for r in t["records"])
        print(f"  {k:24s} stride{t['stride']:3d} 한글 {cap}자까지  {jp}")


if __name__ == "__main__":
    main()
