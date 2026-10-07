"""시스템 메시지 **본문 속**에 적힌 고유명사가 정본과 갈렸나 — 표가 아니라 산문을 본다.

    python3 tools/check_prose_glossary.py

## 왜 있나 (라운드⑥ 착수, 2026-10-07)

`check_glossary.py`(「정본」)는 **표 레코드**(이름 칸 하나 = 값 하나)만 본다. 그런데
`script/system.json`의 전투 로그는 **손으로 쓴 문장**이라 아이템·주문 이름이 **산문 속에**
박혀 있다 — `"%c헤르닐드%c은(는) 불꽃의 지팡이를 ...치켜들었다"` 처럼. 글로서리가
`炎の杖`→`불의 지팡이`로 확정돼도 이 문장은 **자동으로 안 따라온다** — 손으로 그 문장을
다시 쳐야 한다. 실측(2026-10-07): 「불꽃의 지팡이」(정본 「불의 지팡이」) · 「인퍼스」
(정본 「인파스」) 둘이 산문 속에 남아 있었다. 표 검사(`check_glossary.py`)는 둘 다
통과했다 — 표가 아니라 산문이라 안 걸렸다.

🔴 **같은 날 겪은 커버리지 사고.** 처음엔 `sys_rows()`의 6번째 값(`pre`, 「앞바이트」)을
JP 원문으로 잘못 썼다 — `pre`는 JP 매칭 **앞에 남은 처리 안 된 바이트**일 뿐이라
대부분(1,143 중 1,135자리)이 빈 바이트열이었다. 그래서 이 게이트가 몇 달째 "잔존 0건"을
찍어 왔지만 실제로 **대조 가능한 자리는 8곳뿐**이었다 — "달디아"의 옛 표기
(`ダルディア`→`다루디아`, 정본 `달디아`)가 그 1,135자리 사각에 숨어 있다가 관리자의
전수 훑기(grep)로 잡혔다(`c8426052ca3b1ae2`). `sys_rows()`를 고쳐 실제 JP(`jp`, 9번째
값)를 돌려주게 하고, 이 게이트도 그걸 쓰도록 바꿨다 — 이제 **1,143자리 전부**가 대조
대상이다(패처-체크리스트 4-B「검사기 자신의 커버리지」).

## 방법

`patch_ui.sys_rows()`가 **원본 이미지에서 찾은 JP 원문**(9번째 값 `jp`)과 **우리 KR**
(`script/system.json`)을 짝지어 돌려준다(시스템 메시지 재배치용으로 이미 쓰던 값이다).
그 JP 원문에 글로서리 아이템·몬스터·인명 용어가 **부분 문자열로** 나오면, 같은 자리의
KR 에도 **그 용어의 지금 정본 번역**이 부분 문자열로 있어야 한다 — 없으면 그 문장이 옛
표기를 그대로 쓰고 있다는 뜻이다.

⚠ **부분 문자열 대조라 오탐이 있을 수 있다** — 짧은 용어가 다른 낱말 안에 우연히 끼면
  걸릴 수 있다(실측: 인명 `ラルフ`가 지명 `ラルファ` 안에 끼어 걸린 적 있다). 걸리면
  그 줄을 눈으로 본다 — 사람이 본 뒤 **진짜 문제만** `ALLOW`(아래)에서 뺀다.

## `ALLOW` — 눈으로 본 오탐·의도된 갈림 (전수 커버리지 전환 직후 1회 심사, 2026-10-07)

커버리지를 1,143자리 전부로 넓히자 32건이 걸렸다 — 전부 사람이 읽어 갈랐다:
- **진짜 문제 2건은 고쳤다**(이 커밋에 포함) — `ダルディア`→`다루디아`(관리자 발견) ·
  `ジャーデイン`→`쟈딘`(이 전수 과정에서 같이 발견, 정본은 `자데인`).
- **나머지 30건은 전부 부분 문자열 오탐이거나 의도된 갈림**이고 그 사유를 아래 목록
  each 줄 주석에 적는다. 새 항목은 **반드시 사람이 다시 눈으로 보고** 사유를 적은 뒤에만
  여기 추가한다 — 사유 없이 범위를 넓히면 이 게이트가 또 조용히 멀어진다.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
        "shared",
    ),
)

import canon
import common
import glossary
import patch_ui as U

CATEGORIES = ("item", "monster", "person")  # 사전(고유명사) — 라벨·화자 호칭은 아래 정본에서

# 🔴 (path, base) 로 콕 집는다 — 용어로 통째 빼면 다른 자리의 진짜 문제까지 같이 숨는다.
ALLOW = {
    # 'カース' — 범주 갈림: 아이템 '커스' · 몬스터 '카스'(유저 확정 2026-09-05).
    ("/ED.BIN", 0x30C30),
    ("/ED.BIN", 0x30C38),
    ("/ED.BIN", 0x30C44),
    ("/ED.BIN", 0x33034),
    # '男'(바위 사나이) · '女'(행운의 여신) · 'ホー'(오크혼) — 복합 고유명사 안의 한
    # 글자/음절이 일반 낱말과 우연히 겹친다. 이미 올바르게 번역돼 있다.
    ("/ED.BIN", 0x33188),
    ("/ED.BIN", 0x3319C),
    ("/ED.BIN", 0x33514),
    # 'ラルフ'(인명 랄프) — 지명 'ラルファ'(랄파) 안에 접두사로 낀다.
    ("/ED.BIN", 0x4025C),
    # 'ニュート'(뉴트) — UI 문자열 'メニュートップ'(메뉴 처음) 안의 'メニュー' 에 낀다.
    ("/ED.BIN", 0x4CBA4),
    ("/ED2.BIN", 0x3B920),
    # 'はい'(예) — '吐いた'(토했다)·'けはい'(기척) 등 무관한 활용형 속에 흔히 낀다.
    ("/ED2.BIN", 0x182CC),
    ("/ED2.BIN", 0x20CA8),  # 같은 자리에 'レス'(아이템)도 겹쳐 걸린다 — 바로 아래
    ("/BIN/ED2MON03.BIN", 0x1894),
    ("/BIN/ED2MON03.BIN", 0x1F90),
    ("/BIN/ED2MON03.BIN", 0x436C),
    ("/BIN/ED2MON06.BIN", 0x2B04),
    ("/BIN/ED2MON09.BIN", 0x1500),
    # 'レス'(아이템 '레스') — 'ブレス'(브레스/숨결) 안에 접미사로 낀다.
    ("/BIN/ED2MON09.BIN", 0x1500),
    # '炎の騎士' vs '불꽃의기사' — 이 게임 몬스터 복합명은 붙여 쓴다('해왕기사'도 같다),
    # 정본 쪽 공백은 일반 표기일 뿐 이 게임 표기 규칙이 아니다.
    ("/BIN/ED2MON02.BIN", 0xBF0),
    # 🔴 정정(2026-10-07, 공용 이름 검사로 발견) — 木人·プルダーム·杖使い·ドラストゴースト
    #    넷은 **공용 글로서리 'monster' 키가 실제로 있었다**(나무인간·플다암·지팡이술사·
    #    드러스트유령). 위 "derive_encounters.py 가 진짜 정본" 판단이 틀렸다 — 마스터
    #    판정으로 사전 표기에 맞춰 8곳을 고쳤다(판정표 A). 그 넷의 ALLOW 항목은 뺐다.
    ("/BIN/ED2MON05.BIN", 0x1D1C),  # 雷娘 → 뇌랑(이건 그대로 — 아래 사유)
    ("/BIN/ED2MON08.BIN", 0x1780),  # 子ども → 새끼(동물 문맥, '아이' 아님)
    # 'ブラムナ' — 범주 갈림: 아이템/주문 '프람나' · 몬스터 '브람나'(카스/커스와 같은 부류).
    ("/BIN/ED2MON05.BIN", 0x350),
    ("/BIN/ED2MON08.BIN", 0x3908),
    ("/BIN/ED2MON08.BIN", 0x39F4),
    # 'ロー' — 'サイレント・ロード'(사일런트로드) 안의 'ロード' 에 접두사로 낀다.
    ("/BIN/ED2MON10.BIN", 0x980),
}


def terms():
    """{JP 용어: 지금 정본 KR} — 셋 다 합친다(먼저 온 카테고리가 이긴다)."""
    out = {}
    for cat in CATEGORIES:
        for jp, kr in glossary.table(cat).items():
            if kr:
                out.setdefault(jp, kr)
    # 메뉴 라벨(ui)·화자 호칭(speaker)은 정본(`shared/canon`, 사전 적용 2단계 — 사전은 고유명사만)
    for cat in ("ui", "speaker"):
        for title in ("ed1", "ed2"):
            for jp, kr in canon.table(cat, title).items():
                # 한 글자 HUD 라벨(`眠`·`毒`…)·문장형 라벨(`何もない`)은 낱말이 아니라 산문에 우연히 낀다 —
                # 사전 `ui` 시절에도 이 게이트의 용어가 아니었다(정본으로 옮기며 늘어난 것).
                if kr and len(jp) > 1 and "@" not in jp and jp != "何もない":
                    out.setdefault(jp, kr)
    return out


def check():
    t = terms()
    f0, mm0 = common.open_image()
    try:
        sysm = U.sys_rows(mm0)
    finally:
        mm0.close()
        f0.close()
    bad, allowed = [], 0
    seen_allow = set()
    for path, _lba, _size, base, _span, _pre, kr, _ptrs, jp in sysm:
        for term_jp, canon_kr in t.items():
            if term_jp in jp and canon_kr not in kr:
                if (path, base) in ALLOW:
                    seen_allow.add((path, base))
                    continue
                bad.append((path, base, term_jp, canon_kr, kr))
    allowed = len(seen_allow)
    stale_allow = ALLOW - seen_allow
    return len(sysm), len(t), bad, allowed, stale_allow


def main():
    n, nterms, bad, allowed, stale_allow = check()
    mark = "✅" if not bad else "❌"
    print(
        f"     {mark} 시스템 메시지 산문 사전 대조 {n:,}자리(전부 JP 대조 가능) × 용어 {nterms:,}개"
        f" — 잔존 {len(bad)}건 (눈으로 본 오탐·갈림 {allowed}곳 제외)"
    )
    for path, base, jp, canon_kr, kr in bad[:10]:
        print(f"        🔴 {path} 0x{base:X}: {jp!r}→{canon_kr!r} 인데 {kr!r}")
    if stale_allow:
        print(
            f"        ℹ ALLOW 중 이번엔 안 걸린 자리 {len(stale_allow)}곳 — 문안이 바뀌었을 수 있다, 목록을 정리해도 된다"
        )
    if bad:
        raise SystemExit(f"산문 속 고유명사 {len(bad)}건이 정본과 갈렸다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
