"""조판 축 일람 + 양성 대조 + 「부호 뒤 공백」(2-1) 게이트 — 마스터 10-31 「첫칸공백·고아부호·빈줄개행·여러 창 균등 분배 …」.

    python3 games/ss-ed3/tools/check_typeset_axes.py            # 축 × 영역 표
    python3 games/ss-ed3/tools/check_typeset_axes.py --check    # 양성 대조 실패 · 부호 뒤 공백(대장 밖) → rc 1

🔴 축은 새로 만들지 않는다 — 이미 게이트인 둘을 **한 표로 묶어** 어느 축이 어디까지 보는지 드러낸다(DRY):
  · `check_typeset6.py`  ① 고아 부호·폭 초과(2-3·넘침) · ② 빈 줄 개행(2-4) · ③ 줄 첫 칸 공백(2-5) · ④ 조사가 줄머리(2-6 낱말 속 접힘)
  · `check_linebreak.py` a 쪽 끝 한 어절 고아 · b 덩어리 가르는 쪽 · h 마지막 창 한 어절 · h2 창 줄 수 치우침(2-16 ③)
  · 여기: **부호 뒤 공백**(2-1) — `, . ! ?` 바로 뒤에 글자가 붙은 곳. 지금까지 어느 게이트도 세지 않았다.
측정 대상은 JSON 문안이지만 그 문안이 곧 구운 바이트다 — `check_no_loss`(글자열)·`check_structure`(제어 열)가 이미지 ↔ 문안을 같게 묶는다.
🔴 **양성 대조**: 알려진 나쁜 문자열을 각 검출기에 먹여 실제로 걸리는지 본다 — 검출기가 조용히 죽어 「0 건」이 나오는 사고를 막는다.
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_linebreak as LB
import check_typeset6 as C6
import typeset as T

GLUE = re.compile(r"[,.!?](?=[가-힣A-Za-z])")
#   원판 구분자 「、」 를 반각 쉼표로 옮긴 **데이터 문자열**(마법 이름 목록 — 대사창에 안 뜬다, 칸 폭이 정해진 자리)과 라벨 `%c.없음`.
#   화면 미확인 — 마스터 판정 대기(`devlog` 10-31).
ACCEPT_GLUE = {"MAP031[1]", "MAP032[1]", "MAP034[1]", "MAP037[1]", "MAP044[1]", "MAP084[1]", "menu:%c.없음"}


#   규칙별 정규식 — 이름 변수(`<01><xx>`)는 글자 하나로 본다(그 앞뒤 공백·부호는 정상이다)
RULES = {
    "2-1 부호 뒤 공백": GLUE,
    "2-2 부호 앞 공백": re.compile(r"\s[,.!?]"),
    "2-11 … 뒤 붙임": re.compile(r"[가-힣A-Za-z0-9…!?.]…(?=[가-힣A-Za-z0-9])"),
    "2-12 ?!… 순서": re.compile(r"[?!]…"),
}
#   「흑…흑…」 · 「라…우…알…」 꼴 — … 가 낱말 사이에 붙는 **의성어·더듬기**(원판도 낱말마다 점을 끊어 쓴 자리, 규칙 2-11 은 말이 이어지는 경우의 규칙). 화면 미확인.
ACCEPT_2_11 = {"MAP055[91]", "MAP072[214]", "MAP020[387]", "MAP020[443]", "MAP033[200]", "MAP040[36]", "MAP040[59]", "MAP040[60]"}


def rule_hits():
    """`{규칙: [(열쇠, 줄)]}` — 전 영역 줄 단위."""
    out = {n: [] for n in RULES}
    for _area, key, text, _w in C6.blocks():
        t = re.sub(r"<01><[0-9A-Fa-f]{2}>", "가", text)
        for ln in re.split(r"[\n\f\r]", T.visible(t)):
            for n, rx in RULES.items():
                if rx.search(ln) and not (n.startswith("2-2") and "..." in ln):
                    out[n].append((key, ln))
    return out


def glue_hits():
    return rule_hits()["2-1 부호 뒤 공백"]


def named_first_page_rows():
    """`[(열쇠, 줄 수)]` — 이름 줄이 뜨는 대사창인데 **첫 쪽 본문이 3줄 이상**이고 원판 첫 쪽은 2줄 이내였던 것.
    🔴 이름 창은 본문 2줄까지다 — 3줄을 넣으면 엔진이 **이름 줄을 그리지 않는다**(10-31 실측: MAP008#86 쪽을 합쳐 3줄이 되자 「로레」가 사라졌다,
    촬영 전수에서 원판엔 이름이 있고 우리는 없는 블록 87 중 줄 수가 원인인 33+). 이름 창 = 화자 머리 `02` 블록 − `window_unnamed.json`(원판도 이름 없는 창).
    원판 첫 쪽이 3줄이던 블록은 원판도 이름이 안 뜨는 설계라 센다 하지 않는다."""
    import glob
    import json

    import common as C
    import mapfile as M

    with open(os.path.join(C.GAME_DIR, "script", "window_unnamed.json"), encoding="utf-8") as f:
        unnamed = set(json.load(f)["blocks"])
    out = []
    for fp in sorted(glob.glob(os.path.join(C.GAME_DIR, "script", "MAP*.json"))):
        stem = os.path.basename(fp)[:-5]
        with open(fp, encoding="utf-8") as f:
            doc = json.load(f)
        with C.open_disc(1) as d:
            blocks = M.blocks(d.read(f"/MAP/{stem}.BIN"))
        for k, v in doc.items():
            if k.startswith("_") or not isinstance(v, str) or not blocks[int(k)]["head"].startswith("02"):
                continue
            if f"{stem}#{k}" in unnamed:
                continue
            rows = len([x for x in v.split("\f")[0].split("\n") if x.strip()])
            first = bytes(blocks[int(k)]["body"]).split(b"\x0f")[0]
            orig_rows = len([x for x in first.split(b"\x0d") if x.strip(b"\x00\x1a \x10")])
            if rows >= 3 and orig_rows <= 2:
                out.append((f"{stem}#{k}", rows))
    return out


def positive_controls():
    """`[(이름, 걸렸나)]` — 검출기마다 알려진 나쁜 문자열 하나."""
    nm = LB.names()
    two_pages = "가나다 라마바 사아자 차카타 파하\n거너더 러머버 서어저\f루무부 수우주 푸후흐 바바바\n좋아요"
    return [
        ("③ 첫 칸 공백", "③" in C6.check(" 안녕하세요")),
        ("② 빈 줄 개행", "②" in C6.check("안녕\n\n하세요")),
        ("① 폭 초과", "①" in C6.check("가" * 20)),
        ("④ 조사가 줄머리", "④" in C6.check("《제목》\n을 읽을까?")),
        ("h 마지막 창 한 어절", bool(LB.scan("가나다 라마바 사아자 차카타\n파하 거너더\f좋아요하", nm)["h"])),
        ("부호 뒤 공백", bool(GLUE.search("가,나다"))),
        ("부호 뒤 공백 — 정상은 안 걸림", not GLUE.search("가, 나다. 라마!")),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    ctl = positive_controls()
    for name, ok in ctl:
        print(f"  양성 대조 {'✅' if ok else '🔴'} {name}")
    got = C6.findings()
    acc = C6.load_accept()
    by_rule = {}
    for k in got:
        r = k.rsplit("|", 1)[1][0]
        by_rule.setdefault(r, [0, 0])
        by_rule[r][0] += 1
        by_rule[r][1] += k in acc
    names = {"①": "고아 부호·폭 초과", "②": "빈 줄 개행", "③": "줄 첫 칸 공백", "④": "조사가 줄머리(낱말 속 접힘)"}
    for r in "①②③④":
        n, ok = by_rule.get(r, [0, 0])
        print(f"  축 {r} {names[r]:<16} 걸린 {n} · 대장(설계·원판 배치) {ok} · 새로 {n - ok}")
    n, tot, blk, _ = LB.measure()
    print(
        f"  축 h/a/b/h2 (여러 창 분배) — 마지막 창 한 어절 {tot['h']} · 쪽 끝 한 어절 고아 {tot['a']} · 덩어리 가르는 쪽 {tot['b']} · 창 줄 수 치우침 {tot['h2']} (기준선 이하 게이트)"
    )
    nm3 = named_first_page_rows()
    print(f"  축 이름 창 첫 쪽 3줄+(이름 줄이 사라짐) — 걸린 {len(nm3)}")
    for k, r in nm3[:20]:
        print(f"    ✗ {k}  첫 쪽 {r}줄")
    hits = rule_hits()
    new = []
    for n, lst in hits.items():
        acc = ACCEPT_GLUE if n.startswith("2-1 ") else ACCEPT_2_11 if n.startswith("2-11") else set()
        nn = [(k, ln) for k, ln in lst if k not in acc]
        print(f"  축 {n} — 걸린 {len(lst)} · 대장 {len(lst) - len(nn)} · 새로 {len(nn)}")
        new += nn
    for k, ln in new[:20]:
        print(f"    ✗ {k}  {ln}")
    if a.check and (not all(ok for _, ok in ctl) or new or nm3):
        print("  ❌ 조판 축 — 양성 대조가 죽었거나 부호 뒤 공백이 대장 밖에서 새로 생겼다")
        sys.exit(1)


if __name__ == "__main__":
    main()
