"""말투 경보 둘 — 원문 등급 기준 말투 적용(규칙 4-7·4-8·4-9, 마스터 11-12~11-13) 뒤에 조용히 틀리는 꼴.

    python3 tools/check_register.py            # 목록
    python3 tools/check_register.py --check    # 게이트 (기준선보다 늘면 실패)
    python3 tools/check_register.py --freeze   # 줄었을 때 기준선을 내린다

  A. 반말 문장에 듣는 이를 높이는 「-시-」 가 섞였다 — 반말(해체·하게체 끝)로 끝나는 문장인데 끝 서술어가
     「~시는·~시던·~시지·~시네」 꼴. 반말 줄은 듣는 이에게 「-시-」 를 안 쓴다(「못 가지시는 모양」 → 「못 가지는 모양」).
     ⚠ 제삼자 높임(「왕께서 오시면 좋겠어」)은 합당하므로 **경보**다 — 기준선보다 **늘 때만** 실패하고, 맞대어 본 뒤
     기준선에 올린다.
  B. 원문 대비 길이 급감 — 원문(JP) 글자수 대비 한글 글자수가 0.35 아래(원문 14자↑). 번역이 통째로 빠졌거나 문장이 잘린 꼴
     (PS1 덧붙임 검사의 반대 방향). 변수·제어코드·색 표지는 뺀 평문으로 잰다. 마찬가지로 늘 때만 실패한다.

원문은 원판 롬에서 런타임으로 읽는다(`check_ps1_extra.md_rows`). 기준선 `register_baseline.json` = 걸린 키 목록.
양성 대조 `tools/tests/test_register.py`.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_ps1_extra as pe
import common

BASE = common.GAME_DIR / "register_baseline.json"
MIN_JP = 14
RATIO = 0.35

END_PLAIN = re.compile(r"(아|어|야|지|네|걸|군|나|냐|니|까|자|라|다|게|세|오|소|구먼|구려|거든|잖아|는데|은데|ㄴ데)$")


def sentences(t: str) -> list[str]:
    t = pe.ours_text(t)
    return [x.strip() for x in re.split(r"(?<=[.!?…])\s+", t) if x.strip()]


def is_plain(s: str) -> bool:
    """반말계(해체·하게·하오·해라) — 끝이 해요·합쇼(요·니다·니까·십시오·시지요·죠)가 아니다."""
    k = re.sub(r"[\s…~～.,!?「」『』“”\"']+$", "", s)
    if not k or k.endswith(("요", "죠")) or re.search(r"(니다|니까|십시오|시오|ㅂ시다|옵소서|사옵|옵니)$", k):
        return False
    return bool(END_PLAIN.search(k))


def honor_mixed(s: str) -> bool:
    if not is_plain(s):
        return False
    k = re.sub(r"[\s…~～.,!?「」『』“”\"']+$", "", s)
    # 끝 서술어에 높임 「시」 — 마지막 어절 안(또는 앞 어절 + 모양·듯)
    last = k.split()[-1] if k.split() else k
    prev = " ".join(k.split()[-2:])
    if re.search(r"(ㅂ|읍|릅|합|납|갑|봅)시다$|이시다$", last):  # 청유 「~ㅂ시다」·서술 「이시다」는 듣는 이 높임이 아니다
        return False
    return bool(re.search(r"시(는|던|지|네|군|나|냐|니|잖아|거든|는데|고|다)", last)) or bool(
        re.search(r"시(는|ㄴ|던)\s*(모양|듯|것)", prev)
    )


def tilde_over(jp: str, ours: str) -> bool:
    """C — 물결표 `～` 를 원문보다 늘려 쓴 꼴(마스터 11-13 「～ 원본대로 한개씩」). 원문 장음 `ー` 하나를 `～` 하나로 옮기는 건 1:1 이라
    늘림이 아니다(다른 기종과 같은 판정) — `ー` 하나에 `～～` 처럼 부풀린 것만 걸린다."""
    return len(re.findall("[～~]", ours)) > len(re.findall("[～〜~ー]", jp))

# ── D: 번역이 원문 부호를 뺐나(마스터 11-13 「원문 부호는 빼지말자」) ─────────────────────────────────────────────
# 스트림 하나가 원문 한 덩이일 때만 잰다 — 원문에 {p:N}·⟨조건⟩·【화자】 마디가 끼면 여러 스트림이 이어진 것이라 쪽 단위 짝이 안 맞는다(미판정).
# 예외: `。`(종지)는 「…」「!」「?」「～」 뒤에서는 문장 끝 부호가 따로 있으니 세지 않는다. `、` 는 한국식이라 안 잰다. 범위 `～` 는 세지 않는다(숫자 사이).
JP_ELL = re.compile(r"(?:･(?:\s*[･・])*|・{2,}|…+)")  # 점 = 반각 ･ · 연속 ・・ — 「ウルフ・ビル」 가운뎃점 하나는 점이 아니다


def _jp_clean(jp: str) -> str:
    return re.sub(r"<[^>]*>", "", jp)


def jp_marks(jp: str) -> dict[str, int]:
    t = _jp_clean(jp)
    ell = 0
    for r in JP_ELL.findall(t):
        n = len(re.findall("[･・]", r)) + 3 * r.count("…")
        ell += max(1, round(n / 3))
    t2 = JP_ELL.sub("…", t)
    t2 = re.sub(r"\s+。", "。", t2)
    period = len(re.findall(r"(?<![…!！?？])。", t2))
    return {
        "ell": ell,
        "ex": len(re.findall("[!！]", t)),
        "q": len(re.findall("[?？]", t)),
        "tilde": len(re.findall(r"(?<![0-9０-９])[～〜](?![0-9０-９])", t)),
        "period": period,
    }


def ours_marks(ours: str) -> dict[str, int]:
    t = re.sub(r"<[^>]*>", " ", ours.replace("\x0c", " "))  # 제어코드는 공백 — 「나다.<01>허나」 처럼 태그가 낀 종지도 센다
    return {
        "ell": t.count("…"),
        "ex": t.count("!"),
        "q": t.count("?"),
        "tilde": len(re.findall("[～~]", t)),
        "period": len(re.findall(r"\.(?![0-9.])", t)),
    }


def _qx_clusters(t: str) -> list[str]:
    """`?`·`!` 덩어리(전각·사이 공백 통일) — 순서가 원문과 같은지 보려고(1-1 「순서는 원문 그대로」)."""
    t = t.replace("？", "?").replace("！", "!")
    t = re.sub(r"(?<=[?!])\s+(?=[?!])", "", t)
    return re.findall(r"[?!]+", t)


def qx_order_changed(jp: str, ours: str) -> bool:
    """O — 번역의 `?!` / `!?` 순서가 원문 덩어리와 다르다(원문에 없는 순서를 쓴다)."""
    jc = _qx_clusters(re.sub(r"<[^>]*>", "", jp))
    if not jc:  # 원문 쪽에 ?·! 가 없으면(조건 점프만 있는 쪽 등) 순서를 비교할 거리가 없다
        return False
    kc = _qx_clusters(re.sub(r"<[^>]*>", " ", ours))
    for pat in ("?!", "!?"):
        if any(pat in c for c in kc) and not any(pat in c for c in jc):
            return True
    return False


def single_piece(jp: str) -> bool:
    return not re.search(r"\{p:|⟨조건⟩|【", jp)


def dropped(jp: str, ours: str, page: bool = False) -> list[str]:
    """원문보다 적게 쓴 부호 부류 — E(…) Q(?) X(!) T(～) P(종지: 문장 끝 부호 총수)."""
    if (not page and not single_piece(jp)) or "<0f:" in ours or len(re.sub(r"\s|<[^>]*>", "", ours)) < 2:  # 점프(<0f:>)는 뒷 스트림으로 이어져 한 덩이가 아니다
        return []
    a, b = jp_marks(jp), ours_marks(ours)
    out = []
    for k, tag in (("ell", "E"), ("q", "Q"), ("ex", "X"), ("tilde", "T")):
        if b[k] < a[k]:
            out.append(tag)
    if qx_order_changed(jp, ours):
        out.append("O")
    if b["period"] + b["ell"] + b["q"] + b["ex"] + b["tilde"] < a["period"] + a["ell"] + a["q"] + a["ex"] + a["tilde"]:
        out.append("P")
    return out



_CALL = re.compile(r"<(?:10|15):([0-9a-f]{4,6})>")


def _expand(ours: str, streams: dict, depth: int = 0) -> str:
    """호출 코드(`<10:xxxx>`)를 부른 스트림 문안으로 펼친다 — 원문 쪽 walk_pages 가 호출을 그 자리에 이어 붙이기 때문(쪽 나눔은 한 쪽으로)."""
    if depth > 3:
        return ours

    def rep(m: re.Match) -> str:
        sub = streams.get(m.group(1), {}).get("ours", "")
        return " " + _expand(sub.replace("\x0c", " "), streams, depth + 1)

    return _CALL.sub(rep, ours)


_JUMP = re.compile(r"<0f:([0-9a-f]{4,6})>")


def _expand_jump(ours: str, streams: dict, depth: int = 0) -> str:
    """점프(`<0f:xxxx>`) 뒤 스트림을 이어 붙인다 — 원문 walk_pages 도 점프를 따라 같은 목록에 쪽을 잇는다."""
    if depth > 4:
        return ours
    return _JUMP.sub(lambda m: _expand_jump(streams.get(m.group(1), {}).get("ours", ""), streams, depth + 1), ours)


def page_drops() -> list[tuple[str, int, str]]:
    """[(스트림, 쪽, 부류)] — 쪽 수가 원문과 같은 스트림만 쪽 단위로 짝지어 잰다(다르면 미판정). 점프(`<0f:>`)는 뒷 스트림을 이어 붙여서 짝짓는다."""
    import archives
    import pairdump

    orig = common.rom()
    ob = archives.blocks(orig, archives.ARCHIVES["script"][0])
    out = []
    for f in sorted((common.GAME_DIR / "script").glob("*.json")):
        sc = int(f.stem)
        streams = json.loads(f.read_text(encoding="utf-8")).get("streams", {})
        for off, e in streams.items():
            ours = e.get("ours", "")
            if not ours:
                continue
            jp = pairdump.walk_pages(ob[sc][1], int(off, 16), False)
            kp = re.sub(r"<1e>.*?<04>", "", _expand(_expand_jump(ours, streams), streams), flags=re.S).split("\x0c")
            if len(jp) != len(kp):
                continue
            for i, (j, k) in enumerate(zip(jp, kp)):
                dd = dropped(re.sub(r"⟨조건⟩|\{p:\d+\}", "", j), k, page=True)
                if dd:
                    out.append((f"씬{sc:03d}:{off}", i, "".join(dd)))
    return out


def too_short(jp_norm: str, kr_norm: str) -> bool:
    return len(jp_norm) >= MIN_JP and len(kr_norm) / len(jp_norm) < RATIO


_RAW: dict[str, str] = {}


def raw_ours(num: str) -> str:
    """`씬NNN:off` → 정본 `ours` 원문(제어코드 포함) — 점프(<0f:>) 여부를 보려고 읽는다."""
    if not _RAW:
        for f in (common.GAME_DIR / "script").glob("*.json"):
            for off, e in json.loads(f.read_text(encoding="utf-8")).get("streams", {}).items():
                _RAW[f"씬{f.stem}:{off}"] = e.get("ours", "")
    return _RAW.get(num, "")


def scan() -> tuple[int, list[str], list[str], list[str]]:
    rows = pe.md_rows()
    a: list[str] = []
    b: list[str] = []
    c: list[str] = []
    total = 0
    for lst in rows.values():
        for num, jp, ours in lst:
            total += 1
            # 원문 줄 단위가 아니라 스트림 전체로 잰다
            t = ours
            for s in re.split(r"(?<=[.!?…])\s+", t):
                if honor_mixed(s.strip()):
                    a.append(f"A|{num}|{pe.kn(s)}")
            mj = pe.jn(jp)
            kl = len(pe.kn(t))
            if too_short(mj, pe.kn(t)):
                b.append(f"B|{num}|{len(mj)}→{kl}")
            if tilde_over(jp, t):
                c.append(f"C|{num}|～ 늘림")
    for num, pg, dd in page_drops():
        c.append(f"D|{num}#{pg}|{dd}")
    return total, a, b, c


def main() -> None:
    total, a, b, c = scan()
    keys = sorted(set(a) | set(b) | set(c))
    base = set(json.loads(BASE.read_text(encoding="utf-8")).get("keys", [])) if BASE.exists() else set()
    new = [k for k in keys if k not in base]
    gone = sorted(base - set(keys))
    print(f"  말투 경보 — 스트림 {total} · A 반말+시 {len(set(a))} · B 길이 급감 {len(set(b))} · C·D ～ 늘림·부호 뺌 {len(set(c))} · 기준선 {len(base)} · 새로 걸림 {len(new)}")
    for k in new:
        print(f"    ❌ {k}")
    if "--freeze" in sys.argv:
        BASE.write_text(json.dumps({"keys": keys}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"  기준선 {len(keys)} 로 갱신")
        return
    if gone:
        print(f"  ⚠ 기준선에 있는데 이제 안 걸림 {len(gone)} — --freeze 로 내린다")
    if "--check" in sys.argv and new:
        raise SystemExit("말투 경보 — 새로 걸린 줄을 고치거나, 맞대어 본 오탐이면 --freeze 로 기준선에 올린다")


if __name__ == "__main__":
    main()
