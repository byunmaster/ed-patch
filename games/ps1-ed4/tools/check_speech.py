"""말투 게이트 셋(번역 규칙 4-16 ③ ④ + 길이 급감) — 대본 문안 전수를 `names_corpus.pairs()` 로 읽는다.

    python3 tools/check_speech.py            # 검사(실패 시 종료 코드 1)
    python3 tools/check_speech.py --freeze   # 래칫 기준선을 지금 값으로 내린다(줄었을 때만)

  ① 대사 2인칭 「그대」 0 — 반말→너 · 하게→자네 · 존대 윗사람엔 2인칭 빼고 호칭(규칙 4-16 ④, 마스터 11-12). 「그대로」는 부사라 뺀다. 실패.
  ② 반말·하게 줄의 듣는 이 「-시-」 섞임 — 「모르시나?」·「해 보시지」 꼴. 제3자 높임(「돌아가셨어」)은 괜찮아 글자만으로 못 가르니 **기준선 래칫**(늘면 실패).
  ③ 원문 대비 길이 급감 — 원문 12자↑인데 한국어가 원문의 0.35배 미만이면 번역 누락 의심. **기준선 래칫**.
양성 대조(`selftest`)가 가짜 줄에서 셋 다 잡는지 먼저 확인한다.
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", ".."))

BASE = os.path.join(HERE, "..", "speech_baseline.json")
GUDAE = re.compile(r"그대(?!로)")
# 반말·하게로 끝나는 줄의 마지막 문장 — 합쇼·해요·하오 꼴이면 높임이 정상이라 뺀다
POLITE_END = re.compile(r"(니다|니까|십시오|요|죠|소|오|서|구려|옵소서)[\s.!?…~」』”’)]*$")
HON = re.compile(
    r"[가-힣]시[어는던면지나니겠냐군네]|[가-힣]셨|[가-힣]셔|계시[는던고며지나다네]|오시[는지]|(?<!혹)(?<!모)시[?!.…]"
)
CTRL = re.compile(r"⟦[^⟧]*⟧|%[a-zA-Z0-9]+|[\s\n↵・…。、．.,!?！？ー〜～\u0000-\u001f\ufffd]")


def gudae(kr):
    return bool(GUDAE.search(kr))


def honorific_in_banmal(kr):
    last = kr.replace("\n", " ").strip().split("↵")[-1]
    if POLITE_END.search(last):
        return False
    return bool(HON.search(last))


def len_drop(jp, kr):
    j, k = len(CTRL.sub("", jp)), len(CTRL.sub("", kr))
    return (
        j >= 12 and k < 0.35 * j
    )  # 점·말줄임·부호는 세지 않는다(「・・・・・」는 「…」로 줄어도 정상)


def selftest():
    assert gudae("그대가 왔군.") and not gudae("그대로 둬.")
    assert honorific_in_banmal("자네… 모르시나?") and honorific_in_banmal("그 대사 한번 해 보시지.")
    assert not honorific_in_banmal("그렇게 하세요.") and not honorific_in_banmal("돌아가셨습니다.")
    assert len_drop("これはとても長い日本語の文章です。", "응.") and not len_drop(
        "これは短い。", "응."
    )


def scan():
    import names_corpus

    g, h, l = [], [], []
    for pos, jp, kr, kind in names_corpus.pairs():
        if kind != names_corpus.DIALOG or not kr:
            continue
        if gudae(kr):
            g.append((pos, kr))
        if honorific_in_banmal(kr):
            h.append((pos, kr))
        if len_drop(jp, kr):
            l.append((pos, kr))
    return g, h, l


def main():
    selftest()
    g, h, l = scan()
    base = {"honorific_banmal": 10**9, "len_drop": 10**9}
    if os.path.exists(BASE):
        with open(BASE) as f:
            base = json.load(f)
    now = {"honorific_banmal": len(h), "len_drop": len(l)}
    print(
        f"  그대 {len(g)} · 반말+「-시-」 {len(h)} (기준선 {base['honorific_banmal']}) · 길이 급감 {len(l)} (기준선 {base['len_drop']})"
    )
    if "--freeze" in sys.argv:
        out = {k: min(now[k], base[k]) for k in now}
        with open(BASE, "w") as f:
            json.dump(out, f, indent=1)
            f.write("\n")
        print("  기준선 갱신", out)
        return 0
    bad = 0
    for pos, kr in g[:20]:
        print("    ✗ 그대", pos, kr[:40])
        bad += 1
    for k, L in (("honorific_banmal", h), ("len_drop", l)):
        if now[k] > base[k]:
            print(f"    ✗ {k} 늘었다 {base[k]} → {now[k]}")
            for pos, kr in L[:10]:
                print("      ", pos, kr[:40])
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
