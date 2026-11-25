"""말투 경보(마스터 11-13 밤샘) — 구운 대사 문안(`check_punct.corpus` 와 같은 줄)을 훑는다. 음성 자막(오프닝·대관식)은 안 본다.

 · 그대 금지(규칙 4-16) — 대사에 2인칭 「그대」(그대로 제외)가 있으면 실패
 · 길이 급감 경보 — 원문 가나·한자 20자↑ 줄이 한글 글자 수 1/4 미만이면 실패(문장 통째 누락·잘림 의심)
 · 부호 누락 경보(11-13 「원문 부호는 빼지말자」) — 번역의 `?`·`…`(원문 점 n→round(n/3))·`～`·문장 끝 부호 수가 원문보다 적으면 실패. 호격 쉼표(「왕자님,」)·음절 끊기·원판 점열처럼 판정이 갈려 남긴 줄은 `data/punct_loss_known.tsv` 에 열쇠+부류로 적는다(없던 줄이 새로 생기면 실패)
 · 반말 줄의 「-시-」 — 반말 끝(~지·~네·~군·~어·~다)에 높임 `시`가 섞인 문장을 세기만 한다(제3자 높임은 정상이라 실패로 안 친다)
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))

GEUDAE = re.compile(r"그대(?!로)")
HON = re.compile(r"(요|죠|니다|니까|십시오|시오|옵소서)[.?!…~]*$")
SI_PLAIN = re.compile(r"시(?:었|겠)?(?:어|지|네|군|나|냐|는가|는구나|려나|다)[.?!…~]*$")
JP_CH = re.compile(r"[ぁ-ゖァ-ヺ一-鿿]")
KO_CH = re.compile(r"[가-힣A-Za-z0-9]")


def geudae(t: str) -> bool:
    return bool(GEUDAE.search(t))


def shrunk(jp: str, ko: str, min_jp: int = 20, ratio: float = 0.25) -> bool:
    """원문(제어 코드 뗀 평문) 가나·한자 글자 수 대비 한글 글자 수가 너무 적은가."""
    jl = len(JP_CH.findall(jp))
    return jl >= min_jp and len(KO_CH.findall(ko)) < ratio * jl


def lost(jp: str, ko: str) -> list[str]:
    """원문 대비 번역이 뺀 부호 부류 — `?` · `…` · `～` · `.`(문장 끝 부호 전체 수)."""
    out = []
    if len(re.findall(r"[？?]", jp)) > ko.count("?"):
        out.append("?")
    dots = sum(3 if c == "…" else 1 for c in jp if c in "･・…")
    if round(dots / 3) > ko.count("…"):
        out.append("…")
    if len(re.findall(r"[～〜]", jp)) > ko.count("～"):
        out.append("～")
    if len(re.findall(r"[。！？!?]", jp)) > len(re.findall(r"[.?!]|…+|～", ko)):
        out.append(".")
    return out


def known_loss() -> set[tuple[str, str]]:
    f = Path(__file__).resolve().parents[1] / "data" / "punct_loss_known.tsv"
    out = set()
    if f.exists():
        for ln in f.read_text(encoding="utf-8").splitlines():
            c = ln.split("\t")
            if len(c) >= 2 and not ln.startswith("#"):
                out.add((c[0], c[1]))
    return out


def plain_si(sentence: str) -> bool:
    s = sentence.strip()
    return bool(SI_PLAIN.search(s)) and not HON.search(s)


def main() -> int:
    import common
    import dialogue
    import jptext
    import package
    from check_punct import corpus  # noqa: F401  (같은 말뭉치를 쓴다는 표지)

    bad, si, n = [], 0, 0
    known = known_loss()
    loss = []
    for rel in sorted(dialogue.package_chars()):
        pkg = bytes(common.track_data(rel, 128))
        for a, b in package.chunks(pkg):
            if pkg[a : a + 8] == package.SENTINEL:
                continue
            d = package.decode_chunk(pkg, a, b)[0]
            lines = d.split(b"\x00")
            for li, _p, _spk, txt in dialogue.candidates(rel, a, d):
                n += 1
                key = f"{rel}:{a}:{li}"
                if geudae(txt):
                    bad.append((key, "그대 금지(4-16)", txt))
                if shrunk(re.sub(r"\{[^}]*\}", "", jptext.decode(lines[li])), txt):
                    bad.append((key, "원문 대비 길이 급감", txt))
                jpl = re.sub(r"\{[^}]*\}", "", jptext.decode(lines[li]))
                for tag in lost(jpl, txt):
                    if (key, tag) not in known:
                        bad.append((key, f"부호 누락({tag}) — 원문보다 적음", txt))
                    loss.append((key, tag))
                flat = re.sub(r"\{[^}]*\}", "", txt.replace("§", " ").replace("\f", " ").replace("↵", " ").replace("⏎", " "))
                si += sum(plain_si(x) for x in dialogue.kr_sentences(flat))
    for k, w, t in bad[:25]:
        print(f"  ✗ {k} {w}: {t[:60]}")
    print(f"  말투 경보 [pce-ed2] — 대사 {n}줄 · 어긋남 {len(bad)} · 부호 누락 기록 {len(loss)}(알려진 {len(known)}) · 반말 줄 「-시-」 {si}문장(참고 — 제3자 높임 포함)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
