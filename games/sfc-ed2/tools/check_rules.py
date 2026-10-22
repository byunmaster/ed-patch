"""번역 규칙(docs/translation-rules.md) 항목별 정적 검사 — textmap 의 한국어 문안 전량 + 빌드와 같은 조판 결과.
항목마다 「본 줄 수 · 걸린 수」를 찍는다. 걸린 게 있으면 실패. 검사기가 없는 규칙은 맨 끝에 「안 잼」으로 적는다(통과로 치지 않는다)."""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import kr
import typeset

TEXTMAP = Path(__file__).resolve().parent.parent / "textmap"
FILES = ("segments", "spans", "cells", "dict", "listsplit", "opsplit")
# 의도한 자리: 크레딧·장 끝 카드는 가운데 맞춤용 앞 공백/빈 줄을 직접 둔다(raw)
# 장 끝 카드: 원판 카드 배치 그대로 빈 줄이 있다(가운데 맞춤 디자인)
BLANK_OK = {"$CABB71", "$CABE62", "$CAC11D", "$CAC705", "$CAC9B6"}
# 예외(근거): 스태프롤 말장난 줄 — 원문 그대로 「?」 뒤에 글자가 이어진다
EXEMPT = {"2-1 부호 뒤 공백 없이 글자": ("세계 최초?의 ",)}
# 제어 토큰 순서 대조의 예외(근거): 원문 구간 안에 없던 화자 머리를 우리 문안이 이 구간에서 열었다 — 앞 구간 끝의 이름 변수와 이어지는 자리
# 구간 맨 앞의 표시용 제어 바이트(NPC 말머리 표시 등 — 원문에선 글자처럼 읽히는 1~2바이트 코드)를 `<hh …>` 원시 바이트로 그대로 둔 구간: 원문 표기에는 태그로 안 나오므로 맨 앞 태그만 떼고 비교한다
RAW_PREFIX = {"$C2D63E", "$C85D29", "$C49552", "$C5A640", "$C5BFC1", "$C5BF71", "$C494E1", "$C85CF0"}
# 문안 지도에 없어도 되는 구간(근거): `$D5BD76` = 코드 바이트가 글자로 읽힌 것 · `$D7E11A` = 엔딩 원본 줄(번역본은 새 자리로 옮겨졌고 이 자리를 가리키는 포인터가 없다 — 10-20 정적 확인)
MISSING_OK = {"$D5BD76", "$D7E11A"}
CTL_EXEMPT = {"$C5521A", "$CB74B3"}
PUNCT_LEAD = re.compile(r"^[.,!?…」』)~:;]")


def kr_strings() -> list[tuple[str, str]]:
    out: list = []

    def walk(o, tag):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "kr" and isinstance(v, str):
                    out.append((tag, v))
                else:
                    walk(v, tag + "/" + str(k) if tag.count("/") < 1 else tag)
        elif isinstance(o, list):
            for v in o:
                walk(v, tag)

    for f in FILES:
        walk(json.loads((TEXTMAP / f"{f}.json").read_text(encoding="utf-8")), f)
    return out


RULES = [
    ("1-3 점 셋·가운데 점 금지", lambda t: bool(re.search(r"\.\.\.|[・･]", t))),
    ("1-1 전각 쉼표·마침표·물음·느낌표", lambda t: bool(re.search(r"[，。！？、]", t))),
    ("1-7 ～ 뒤 마침표", lambda t: "～." in t or "～。" in t),
    ("2-1 부호 뒤 공백 없이 글자", lambda t: bool(re.search(r"(?<![A-Za-z0-9])[.,!?][가-힣]", t))),
    ("2-2 부호 앞 공백", lambda t: bool(re.search(r"[가-힣A-Za-z0-9] [.,!?]", t))),
    ("3-5 병기 조사 을(를)류", lambda t: bool(re.search(r"[은는이가을를](?=\()|\([은는이가을를]\)|을\(를\)|이\(가\)|은\(는\)", t))),
    ("PUA 문자 섞임(U+E000~F8FF — PS1 붙임 공백 등 자리표시)", lambda t: bool(re.search("[\ue000-\uf8ff]", t))),
    ("가나·한자 잔존", lambda t: bool(re.search(r"[぀-ヿ一-鿿]", t))),
]


_CTL = re.compile(r"<(?!E[01]:)[^>]*>")


def ctl_seq(t: str) -> list[str]:
    """문안의 제어 토큰 순서(사전 토큰 `<E0:n>`·`<E1:n>` 제외)."""
    return _CTL.findall(t)


def main() -> None:
    src = common.rom_bytes()
    texts = kr_strings()
    fails = 0
    print(f"문안 {len(texts):,}줄(segments·spans·cells·dict·listsplit·opsplit) 대상")
    for name, fn in RULES:
        hit = [(g, t) for g, t in texts if fn(t) and t not in EXEMPT.get(name, ())]
        fails += len(hit)
        print(f"  {name}: 본 {len(texts):,} · 걸림 {len(hit)}")
        for g, t in hit[:5]:
            print(f"      {g} {t[:60]!r}")
    # 2-11·2-12
    import check_ellipsis

    o: list = []
    for f in sorted(TEXTMAP.glob("*.json")):
        check_ellipsis.walk(json.loads(f.read_text(encoding="utf-8")), [f.name], o)
    print(f"  2-11·2-12 … 뒤 공백·?! 순서: 본 {len(texts):,}+ · 걸림 {len(o)}")
    fails += len(o)
    # 조판 결과(빌드와 같은 길) — 대사 $C2~$CB 비-raw
    import segs

    seg_map, _, dict_map = build.collect_texts(src)
    names = build.dict_names(src, dict_map)
    e1w = build.e1_texts(src, seg_map)
    sg = {segs.seg_id(a): (a, b) for a, b in segs.segments(src)}
    seen = {"2-3 줄 머리 고아 부호": 0, "2-4 빈 줄": 0, "2-5 줄 첫 공백": 0, "폭 50단위 초과": 0}
    bad = {k: [] for k in seen}
    n = 0
    for key, v in sorted(seg_map.items()):
        a, _ = sg[key]
        if not (0xC2 <= (common.off2snes(a) >> 16) <= 0xCB) or v.get("raw"):
            continue
        n += 1
        t = typeset.typeset(build.resolve_josa(v["kr"], names), {**names, **e1w, **build.call_texts(v["kr"], a, seg_map, sg)})
        t = re.sub(r"<1e>.*?<04>\n?", "", t, flags=re.S)
        for pi, page in enumerate(t.split("<05>")):
            lines = page.split("\n")
            for i, ln in enumerate(lines):
                body = re.sub(r"<[^>]*>", "", re.sub(r"<E([01]):(\d+)>", lambda m: names.get(f"E{m.group(1)}:{m.group(2)}", "가"), ln))
                if body.strip() == "" and 0 < i < len(lines) - 1 and key not in BLANK_OK:
                    bad["2-4 빈 줄"].append(key)
                if body.startswith(" ") and not (pi == 0 and i == 0):  # 구간 맨 앞 공백 = 앞 구간 끝의 이름·수치 변수에 이어 붙는 자리(「Gold」·「말이군요」)
                    bad["2-5 줄 첫 공백"].append(key)
                if PUNCT_LEAD.match(body) and not body.startswith("…") and not (pi == 0 and i == 0) and not re.fullmatch(r"[?!]+", body):  # 구간 맨 앞 부호 = 앞 구간 끝의 이름(변수) 뒤를 잇는 조각
                    bad["2-3 줄 머리 고아 부호"].append(key)
                if sum(typeset.width(x, names) for x in typeset._TOK.findall(ln)) > typeset.LINE_UNITS:
                    bad["폭 50단위 초과"].append(key)
    for k, l in bad.items():
        l = sorted(set(l))
        fails += len(l)
        print(f"  {k}(조판 결과): 본 대사 {n:,}구간 · 걸림 {len(l)}" + (" " + " ".join(l[:8]) if l else ""))
    # 제어 토큰 순서 대조(sfc-ed1 발견 — 반입 때 분기·화자표가 본문 뒤로 밀리는 꼴): 구간마다 원문과 우리 문안의 제어 토큰 순서가 같아야 한다.
    # 사전 토큰(`<E0:n>`·`<E1:n>`)은 번역이 어미로 풀거나 이름을 글자로 적을 수 있어 비교에서 뺀다. 나머지(`<04>` `<05>` `<08>` `<1e>` `<1f>` …)는 한 개도 빠지거나 바뀌면 안 된다.
    ctl_order = []
    for key, v in sorted(seg_map.items()):
        a, b = sg[key]
        if key in CTL_EXEMPT:
            continue
        kr_t = re.sub(r"^<[0-9a-f ]+>", "", v["kr"]) if key in RAW_PREFIX else v["kr"]
        if ctl_seq(segs.notation(src, a, b)) != ctl_seq(kr_t):
            ctl_order.append(key)
    fails += len(ctl_order)
    print(f"  제어 토큰 순서(원문 대조): 본 {len(seg_map):,}구간 · 걸림 {len(ctl_order)}" + (" " + " ".join(ctl_order[:8]) if ctl_order else ""))
    # 문안 지도에 없는 구간에 일본어가 남았나(10-20 qa: 상점 「팔기」 질문 등 8구간이 지도에서 빠진 채 일본어로 나갔다 — 일본어 잔존 게이트는 지도에 있는 구간만 분모로 봐서 이 구멍을 못 봤다)
    miss_jp = []
    for a_, b_ in sorted(segs.segments(src)):
        k_ = segs.seg_id(a_)
        if k_ in seg_map or k_ in MISSING_OK:
            continue
        if re.search(r"[ぁ-ん一-龥]{3,}", segs.notation(src, a_, b_)):
            miss_jp.append(k_)
    fails += len(miss_jp)
    print(f"  문안 지도에 없는 구간의 일본어(가나·한자 3자↑): 본 구간 {len(sg):,} · 걸림 {len(miss_jp)}" + (" " + " ".join(miss_jp[:8]) if miss_jp else ""))
    # 구운 글리프끼리 같은 비트맵이면 실패(ss-ed1+2 발견 — 행 맞춤으로 쉼표 꼬리 행이 잘려 쉼표가 마침표와 같은 모양으로 구워졌다)
    import hangul_font
    import font

    used = set()
    for _g, txt in texts:
        for tk in kr._TOK.finditer(txt):
            if tk.group(5) and tk.group(5) != "\n":
                used.add(tk.group(5))
    dup: list = []
    full = {}
    for c in sorted(x for x in used if ord(x) > 0x7E):
        full.setdefault(hangul_font.glyph12(c), []).append(c)
    dup += [v for v in full.values() if len(v) > 1]
    built = common.BUILD_DIR / "sfc-ed2" / "Dragon Slayer - Eiyuu Densetsu 2 (KR).sfc"
    if built.exists():  # 반각은 구운 롬의 표에서 읽는다(원본 글꼴 파일이 아니라)
        bb = built.read_bytes()
        half = {}
        for c in sorted(x for x in used if 0x21 <= ord(x) <= 0x7E):
            code = 0x22 if c == "?" else ord(c)
            a0 = font.HALF_BASE + (code - 0x20) * font.HALF_STRIDE
            half.setdefault(bytes(bb[a0 : a0 + font.HALF_STRIDE]), []).append(c)
        dup += [v for v in half.values() if len(v) > 1]
    fails += len(dup)
    print(f"  글리프 비트맵 중복(전각 원천·반각 구운 롬): 본 {len(used)}자 · 걸림 {len(dup)}" + (f" {dup[:4]}" if dup else "") + ("" if built.exists() else " (구운 롬 없어 반각은 못 잼)"))
    print("  안 잼: 2-8 가운데 맞춤 픽셀(크레딧·카드는 직접 배치) · 2-10 한 줄 문장(전투 조각은 런타임 줄바꿈) · 2-13 쉼표 한국식(판단) · 3-1 맞춤법(공용 spellcheck 미연결) · 3-2 화자 이름 띄어쓰기 · 3-4 지명 칸/대화(이름 검사가 맡음) · 3-7 스태프롤(수동) · 4-x 문체")
    if fails:
        sys.exit(f"규칙 위반 {fails}곳")
    print("규칙 위반 0")


if __name__ == "__main__":
    main()
