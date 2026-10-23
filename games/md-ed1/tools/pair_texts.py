"""번호별 대사집 짝 표 — **촬영 없이** 원판 롬과 한글 롬에서 번호(스트림 포인터)마다 실제 바이트를 디코드해 나란히 놓는다.

    python3 tools/pair_texts.py [--orig 원판.bin] [--kr 한글.bin] [--out sweep/pair]

번호: 씬 = `씬NNN:원판오프셋` · 전투 = `전투NNN:원판오프셋` · 시스템 = `시스템:원판오프셋6자리` · 자막 = `자막<가족>:원판오프셋6자리`(오프닝 자막 · 엔딩 나레이션 · 엔딩 대사).
한글 쪽 자리: 씬 = 재조립 위치표(`work/build/pos.json`, ED_DUMP_POS 빌드) · 전투 = 같은 lea·자료 A 워드 자리가 가리키는 곳(연쇄는 머리 끝) ·
시스템 = `sysmsg.plan` 의 구운 위치 · 자막 = 표 머리를 부르는 `lea` 의 구운 피연산자(`captions.RELOCATE`)가 가리키는 한글 표의 같은 워드 번호. 글자는 `pairdump.walk_pages`(압축 블록은 풀린 바이트)로 읽는다 — 대본 JSON 이 아니다.
표기: 쪽 넘김 ⏎ · 줄바꿈 ¶ · 변수 `{target}`·`{item}`·`{p:n}`·`{num}`·`{josa}`·`{값}`(06 삽입) · 화자 【…】 · 조건 분기 ⟨조건⟩.
표: `pairs.tsv` 열 = 번호 · 원판 · 한글 · 표시(원판만 / 한글만 / 둘 다 빔 / 포인터 공유).
"""

import argparse
import json
import struct
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import captions
import common
import pairdump
import scene
import sysmsg

SCRIPT = archives.ARCHIVES["script"][0]


def cell(pages: list[str]) -> str:
    pages = [p.replace("\n", "¶").replace("\t", " ") for p in pages]
    if not any(p.strip("¶ ") for p in pages):
        return ""
    return " ⏎ ".join(pages)


def mark(o: str, k: str, share: bool) -> str:
    m = []
    if not o and not k:
        m.append("둘 다 빔")
    elif o and not k:
        m.append("원판만")
    elif k and not o:
        m.append("한글만")
    if share:
        m.append("포인터 공유")
    return ";".join(m)


def shared(spans: dict[str, tuple[int, int] | None]) -> set[str]:
    """한 단위(모듈·블록) 안에서 시작 자리가 같거나 다른 스트림 범위 안에 든 번호 — 꼬리·스트림을 나눠 쓰는 자리."""
    items = [(n, sp) for n, sp in spans.items() if sp]
    out: set[str] = set()
    starts: dict[int, list[str]] = defaultdict(list)
    for n, (s, _e) in items:
        starts[s].append(n)
    for ns in starts.values():
        if len(ns) > 1:
            out.update(ns)
    for n, (s, _e) in items:
        for m, (s2, e2) in items:
            if m != n and s2 < s < e2:
                out.add(n)
                break
    return out


def span_of(b: bytes, off: int | None) -> tuple[int, int] | None:
    if off is None or not 0 <= off < len(b):
        return None
    try:
        st = scene.parse_stream(b, off)
    except (ValueError, IndexError):
        return None
    return off, st.end


def pair_block(ob: bytes, kb: bytes) -> list[dict]:
    """[{off, kr_off, how, lea, words, ...}] 원판 스트림마다 한글 대응 자리."""
    rs = battle.refs(ob)
    kpos: dict[int, int | None] = {}
    out = []
    for tgt, e in rs.items():
        how, kp = None, None
        if e["lea"]:
            ins = e["lea"][0]
            kp = ins + 2 + struct.unpack(">h", kb[ins + 2 : ins + 4])[0]
            how = "lea"
        elif e["words"]:
            p = e["words"][0]
            kp = struct.unpack(">H", kb[p : p + 2])[0]
            how = "word"
        else:
            prev = next((t for t, x in rs.items() if x["stream"].end == tgt and t < tgt), None)
            if prev is not None and kpos.get(prev) not in (None, prev):
                try:
                    kp = scene.parse_stream(kb, kpos[prev]).end
                    how = "chain-moved"
                except (ValueError, IndexError):
                    kp = None
            else:
                kp = tgt
                how = "chain" if prev is not None else "inplace"
        kpos[tgt] = kp
        out.append({"off": tgt, "kr_off": kp, "how": how, "lea": e["lea"], "words": e["words"]})
    return out


def scenes(orig: bytes, kr: bytes, pos: dict) -> list[list[str]]:
    rows = []
    ob, kb = archives.blocks(orig, SCRIPT), archives.blocks(kr, SCRIPT)
    for sc in range(len(ob)):
        om, km = ob[sc][1], kb[sc][1]
        streams = scene.parse_module(om).streams
        sp = pos.get(str(sc), {})
        o_spans: dict[str, tuple[int, int] | None] = {}
        k_spans: dict[str, tuple[int, int] | None] = {}
        data = []
        for x in sorted(streams):
            num = f"씬{sc:03d}:{x:04x}"
            k_off = int(sp[hex(x)], 16) if hex(x) in sp else None
            o_txt = cell(pairdump.walk_pages(om, x, False))
            k_txt = cell(pairdump.walk_pages(km, k_off, True)) if k_off is not None else ""
            o_spans[num], k_spans[num] = span_of(om, x), span_of(km, k_off)
            data.append((num, o_txt, k_txt))
        sh = shared(o_spans) | shared(k_spans)
        rows += [[n, o, k, mark(o, k, n in sh)] for n, o, k in data]
    return rows


def battles(orig: bytes, kr: bytes) -> list[list[str]]:
    rows = []
    ob, kb = list(battle.blocks(orig)), list(battle.blocks(kr))
    for n, ((_s, jb, _e), (_s2, bb, _e2)) in enumerate(zip(ob, kb, strict=True)):
        o_spans, k_spans, data = {}, {}, []
        for it in pair_block(jb, bb):
            num = f"전투{n:03d}:{it['off']:04x}"
            o_txt = cell(pairdump.walk_pages(jb, it["off"], False, follow06=True))
            k_txt = (
                cell(pairdump.walk_pages(bb, it["kr_off"], True, follow06=True))
                if it["kr_off"] is not None
                else ""
            )
            o_spans[num], k_spans[num] = span_of(jb, it["off"]), span_of(bb, it["kr_off"])
            data.append((num, o_txt, k_txt))
        sh = shared(o_spans) | shared(k_spans)
        rows += [[a, o, k, mark(o, k, a in sh)] for a, o, k in data]
    return rows


def sysmsgs(orig: bytes, kr: bytes) -> list[list[str]]:
    import build
    import hangul

    cap: dict = {}
    orig_emit = sysmsg._emit

    def em(t, b, n):
        cap["a"] = n
        return orig_emit(t, b, n)

    sysmsg._emit = em
    tm = build.load_textmaps()
    cs = hangul.Charset(orig, build.collect_chars(tm))
    smap = {k: dict(v, ours=build.normalize(v.get("ours", ""))) for k, v in tm["smap"].items()}
    writes = sysmsg.plan(orig, smap, cs.encode, tail_at=build.SYSMSG_TAIL_AT)
    bad = [w[0] for w in writes if kr[w[1] : w[1] + len(w[2])] != w[2]]
    if bad:
        raise SystemExit(f"위치표가 한글 롬과 다르다(롬이 이 코드로 빌드된 게 아니다): {bad[:5]}")
    pos = cap["a"]
    strs = sysmsg.streams(orig)
    o_spans, k_spans, data = {}, {}, []
    for t in sorted(strs):
        num = f"시스템:{t:06x}"
        k_off = pos.get(t)
        o_txt = cell(pairdump.walk_pages(orig, t, False, follow06=True))
        k_txt = cell(pairdump.walk_pages(kr, k_off, True, follow06=True)) if k_off is not None else ""
        o_spans[num], k_spans[num] = span_of(orig, t), span_of(kr, k_off)
        data.append((num, o_txt, k_txt))
    sh = shared(o_spans) | shared(k_spans)
    return [[a, o, k, mark(o, k, a in sh)] for a, o, k in data]


def captions_rows(orig: bytes, kr: bytes) -> list[list[str]]:
    """오프닝 자막 · 엔딩 나레이션 · 엔딩 대사 — 워드 스크립트 표(오프코드 0)마다 원판 문안과 한글 문안.
    한글 표는 `lea` 피연산자가 새로 가리키는 자리이고, 워드 번호가 같으면 같은 자막이다. 글꼴 코드(`<fd..>`·`<fe..>`)는 지운다."""
    import re

    def clean(pages: list[str]) -> str:
        return cell([re.sub(r"<f[de][0-9a-f]{2}>", "", p) for p in pages])

    o_spans: dict[str, tuple[int, int] | None] = {}
    k_spans: dict[str, tuple[int, int] | None] = {}
    data, seen = [], set()
    for fam, tabs in captions.RELOCATE.items():
        for obase, site in tabs:
            kbase = struct.unpack(">I", kr[site : site + 4])[0]
            ow, kw = captions.words(orig, obase), captions.words(kr, kbase)
            if len(ow) != len(kw):
                raise SystemExit(f"자막 표 {obase:#x} 워드 수가 다르다: {len(ow)} ≠ {len(kw)}")
            for (_p, op, oa), (_q, _kop, ka) in zip(ow, kw, strict=True):
                if op != 0:
                    continue
                ot, kt = obase + oa, kbase + ka
                num = f"자막{fam}:{ot:06x}"
                if num in seen:
                    continue
                seen.add(num)
                o_spans[num], k_spans[num] = span_of(orig, ot), span_of(kr, kt)
                data.append(
                    (num, clean(pairdump.walk_pages(orig, ot, False)), clean(pairdump.walk_pages(kr, kt, True)))
                )
    sh = shared(o_spans) | shared(k_spans)
    return [[a, o, k, mark(o, k, a in sh)] for a, o, k in data]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--orig", default=str(common.ORIG_ROM))
    ap.add_argument("--kr", required=True, help="한글 제품 롬(work/build/<꼬리표>/ed1-kr.bin)")
    ap.add_argument("--pos", default=str(common.BUILD_DIR / "pos.json"))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.out:
        out = Path(a.out)
    else:
        gc = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        out = Path(gc).parent / ".local" / "work" / "inbox" / "md-ed1" / "sweep" / "pair"
    out.mkdir(parents=True, exist_ok=True)
    orig, kr = Path(a.orig).read_bytes(), Path(a.kr).read_bytes()
    pos = json.loads(Path(a.pos).read_text())
    rows = scenes(orig, kr, pos) + battles(orig, kr) + sysmsgs(orig, kr) + captions_rows(orig, kr)
    head = ["번호", "원판", "한글", "표시"]
    (out / "pairs.tsv").write_text(
        "\n".join("\t".join(r) for r in [head, *rows]) + "\n", encoding="utf-8"
    )
    cnt: dict[str, int] = defaultdict(int)
    for r in rows:
        cnt[r[0].split(":")[0].rstrip("0123456789")] += 1
        for m in r[3].split(";"):
            if m:
                cnt[f"표시:{m}"] += 1
    print(json.dumps(dict(cnt), ensure_ascii=False, indent=1))
    print(f"{len(rows)}행 → {out / 'pairs.tsv'}")


if __name__ == "__main__":
    main()
