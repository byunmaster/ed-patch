"""말투·길이 경보 둘(마스터 11-13 밤샘 정적 일) — 문안 전량을 원문과 맞대 센다.

  A. 반말 줄 듣는 이 「-시-」 — 반말 말끝(~시겠어·~시는데·~시네·~시군·~시지·~시나 …)에 높임 「-시-」가 낀 문장.
     (마스터 11-12 「반말 말끝 + -시-」 제거.) 제3자 높임(이시구먼·계시네·대단하시네)과 동사 「마시다」는 사람이 읽고 `ALLOW_SI` 에 올린 것만 통과한다 —
     목록에 없는 새 줄이 생기면 운다.
  B. 원문 대비 길이 급감 — 원문 보이는 글자(가나·한자·영숫자, 점줄 제외)가 14자 이상인데 번역 보이는 글자가 그 40% 미만인 구간.
     (문장이 통째로 빠진 번역 누락 경보.) 번역에 사전 구절 토큰 `<E1:n>` 이 든 구간은 펼친 길이를 모르므로 건너뛴다.

  C. 말줄임 개수(규칙 1-3) — 원문 점 줄(・·･·… 연속) 하나가 `…` round(n/3)(최소 1)개여야 한다. 원문·번역의 점 줄 수가 같은 구간만 짝지어 센다
     (줄 재배치로 수가 달라진 구간은 사람 몫). 마스터 11-13 문장부호 전수 검토.
  E. 원문 부호 빠짐(마스터 11-13 「원문 부호는 빼지말자」) — 구간의 `!`·`?`·`～`·`…` 개수가 원문보다 적으면 운다.
     원문 `!"`=!? (반각 글꼴 `?`=$22) · `…`=점 줄 round(n/3)(낱점 `・` 하나·고유명 가운뎃점은 안 센다) · `～`=기호 `～`(장음 `ー` 는 한국어가 모음 겹침으로 옮겨 안 센다).
     정당한 예외는 `ALLOW_MARK`(사람이 읽고 올린 (구간, 부호)).
D. `!?`/`?!` 순서는 **원문 순서 그대로**(원문 `!"`=!? · `"!`=?!, 반각 글꼴 `?`=$22) · 전각 ！？·합자 ⁉‼.

양성 대조(`--selftest`, 기본 실행에도 먼저 돈다): 알려진 나쁜 꼴을 일부러 넣어 둘 다 잡히는지 본다 — 못 잡으면 검사기가 죽은 것이다.

    python3 games/sfc-ed2/tools/check_register.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build
import common
import kr
import script
import segs

E_ = re.compile(r"<E([01]):(\d+)>")
HEAD = re.compile(r"<1e>.*?<04>", re.S)
SI = re.compile(r"[가-힣]*(?:시|세)(?:겠)?(?:는데|네|군|지|어|나|려나|는가|던데|겠군|구먼)$")
# 사람이 읽고 통과시킨 것 — (낱말). 제3자 높임 · 동사 「마시다」 · 혼잣말 · 문장 끝이 아닌 꼴.
ALLOW_SI = {"마시겠나", "마시겠어", "왕자님이시구먼", "계시네", "주시겠지", "성가시겠군", "자라시어", "놔주시지", "대단하시네", "혹시나"}
MIN_JP, RATIO = 14, 0.4
ALLOW_MARK = {("$C536AF", "?"), ("$CACF37", "～")}  # $C536AF: 원문 「<품목>？ もう持てねえ…」 — `？` 는 앞 품목 토큰 줄 것이라 이 문장엔 없다 · $CACF37: 범위 「5～6世代」 = 「대여섯 세대」(한국어 표기, 마스터 11-13 예외)
JP_DOTS = re.compile(r"[・･…]+")
KO_DOTS = re.compile(r"…+")
BAD_MARK = re.compile(r"[！？⁉‼⁈]|(?<![.\d])\.\.(?!\.)")  # 전각·합자
Q_OF = "\""  # 원판 반각 글꼴에서 `?` 는 $22(= ASCII `"` 자리) — 원문 `!"` = 느낌표 먼저, `"!` = 물음표 먼저(status.md)


def corpus():
    d = common.rom_bytes()
    jd = {f"{t}:{n}": x for t, n, x in script.dict_entries(d)}
    kd = build.dict_names(d, kr.load("dict"))
    tm = kr.load("segments")
    keep = set(kr.load("keep").get("ids", []))
    for a, b in segs.segments(d):
        sid = segs.seg_id(a)
        if sid in keep or sid not in tm:
            continue
        jp = E_.sub(lambda m: jd.get(f"E{m.group(1)}:{m.group(2)}", ""), segs.notation(d, a, b))
        yield sid, jp, tm[sid]["kr"], E_.sub(lambda m: kd.get(f"E{m.group(1)}:{m.group(2)}", ""), tm[sid]["kr"])


def si_hits(ko: str) -> list[str]:
    out = []
    for sent in re.split(r"(?<=[.?!…])\s*|<05>|\n", HEAD.sub("", ko)):
        s = sent.strip().rstrip(".?!…~ ")
        if not s:
            continue
        w = s.split(" ")[-1]
        if SI.match(w) and not w.endswith("세요"):
            out.append(w)
    return out


def vis(s: str, jp: bool) -> int:
    s = re.sub(r"<[^>]*>|\{[^}]*\}", "", HEAD.sub("", s))
    s = re.sub(r"[\s　・…\.。、！？!?～ー]", "", s)
    return len(s)


def length_drop(jp: str, ko_raw: str, ko: str) -> bool:
    if "<E1:" in ko_raw:
        return False
    j = vis(jp, True)
    return j >= MIN_JP and vis(ko, False) < RATIO * j


def dots_bad(jp: str, ko_raw: str) -> list[tuple[int, int]]:
    """(기대 …개수, 실제) — 점 줄 수가 같을 때만. 기대 = round(원문 점 수 / 3), 최소 1."""
    j = [len(x) for x in JP_DOTS.findall(re.sub(r"<[^>]*>", "", jp))]
    k = [len(x) for x in KO_DOTS.findall(re.sub(r"<[^>]*>", "\x01", ko_raw))]
    if len(j) != len(k):
        return []
    return [(max(1, int(n / 3 + 0.5)), a) for n, a in zip(j, k) if max(1, int(n / 3 + 0.5)) != a]


def mark_counts(jp: str, is_jp: bool) -> dict[str, int]:
    t = re.sub(r"<[^>]*>|\{[^}]*\}", "", jp)
    if is_jp:
        t = re.sub(r"・( ?・)+", lambda m: "…" * max(1, int(m.group().count("・") / 3 + 0.5)), t)
        return {"!": len(re.findall("[!！]", t)), "?": len(re.findall('["？?]', t)), "…": t.count("…"), "～": t.count("～")}
    return {m: t.count(m) for m in "!?…～"}


def marks_bad(jp: str, ko: str) -> list[tuple[str, int, int]]:
    j, k = mark_counts(jp, True), mark_counts(ko, False)
    return [(m, j[m], k[m]) for m in j if k[m] < j[m]]


def order_bad(jp: str, ko_raw: str) -> list[str]:
    """번역의 `?!` 수가 원문 `"!`(물음표 먼저) 수보다 많으면 순서가 뒤집힌 것."""
    j = re.sub(r"<[^>]*>", "", jp)
    out = []
    if ko_raw.count("?!") > j.count('"!') + j.count("？！"):  # 원문에 없는 `?!`(= 순서 뒤집힘)만 — 번역이 부호를 줄이는 건 문안 판단이라 안 센다
        out.append("?!")
    return out


def selftest() -> None:
    assert marks_bad("えっ !\" ああ ・・・", "어 아아") == [("!", 1, 0), ("?", 1, 0), ("…", 1, 0)], "자체 점검 실패 — 부호 빠짐 경보가 죽었다"
    assert not marks_bad("フ ・ フレイア ・・", "프, 프레이아…") and not marks_bad("う～ん", "으～음"), "자체 점검 실패 — 부호 빠짐 정상을 잡았다"
    assert order_bad('えっ!" ああ', "어?! 아아") == ["?!"], "자체 점검 실패 — 부호 순서 경보가 죽었다"
    assert not order_bad('えっ!" ああ', "어!? 아아"), "자체 점검 실패 — 부호 순서 정상을 잡았다"
    assert dots_bad("あ・・・・・・・・", "아…………") == [(3, 4)], "자체 점검 실패 — 말줄임 개수 경보가 죽었다"
    assert not dots_bad("あ・・・・・・", "아……"), "자체 점검 실패 — 말줄임 개수 정상을 잡았다"
    assert BAD_MARK.search("어？ 뭐") and BAD_MARK.search("오시게..") and not BAD_MARK.search("어!? 뭐"), "자체 점검 실패 — 전각 부호 경보가 죽었다"
    assert si_hits("그건 못 가지시는데."), "자체 점검 실패 — -시- 경보가 죽었다"
    assert si_hits("에이, 가시겠어?") == ["가시겠어"], "자체 점검 실패 — -시- 경보가 죽었다"
    assert not si_hits("어서 오세요."), "자체 점검 실패 — 존댓말을 잡았다"
    assert length_drop("いらっしゃいませ。なんの ご用でしょうか？", "무슨 일이십니까?", "무슨 일이십니까?"), "자체 점검 실패 — 길이 경보가 죽었다"
    assert not length_drop("いらっしゃいませ。なんの ご用でしょうか？", "<E1:4> 무슨 일이십니까?", " 무슨 일이십니까?"), "자체 점검 실패 — 사전 구절 예외"


def main() -> int:
    selftest()
    bad = 0
    n = 0
    for sid, jp, ko_raw, ko in corpus():
        n += 1
        for w in si_hits(ko):
            if w not in ALLOW_SI:
                print(f"  ❌ 반말 말끝 + -시- {sid} 「{w}」")
                bad += 1
        for want, got in dots_bad(jp, ko_raw):
            print(f"  ❌ 말줄임 개수 {sid} 기대 …×{want} 실제 …×{got}")
            bad += 1
        for m, jn, kn in marks_bad(jp, ko):
            if (sid, m) not in ALLOW_MARK:
                print(f"  ❌ 원문 부호 빠짐 {sid} 「{m}」 원문 {jn} → 번역 {kn}")
                bad += 1
        for o in order_bad(jp, ko_raw):
            print(f"  ❌ 부호 순서가 원문과 다름 {sid} 「{o}」")
            bad += 1
        for m in BAD_MARK.finditer(ko_raw):
            print(f"  ❌ 물음·느낌표 꼴 {sid} 「{m.group()}」")
            bad += 1
        if length_drop(jp, ko_raw, ko):
            print(f"  ❌ 원문 대비 길이 급감 {sid} 원문 {vis(jp, True)}자 → {vis(ko, False)}자")
            bad += 1
    print(f"말투·길이 경보 — 구간 {n} · 반말+「-시-」·길이 급감·말줄임 개수·부호 꼴 위반 {bad} (양성 대조 통과)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
