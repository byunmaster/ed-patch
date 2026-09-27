"""토큰 경계가 엔진과 같은가 — **분기 인자를 글자로 먹지 않았나**. (상주 게이트)

    python3 tools/check_refs.py            # 세 축을 재서 보여 준다
    python3 tools/check_refs.py --check    # 게이트

왜 세우나 — pc98-ed1 이 2026-09-07 에 **남의 분기 주소를 덮어쓰는** 결함을 찾았다. 덤퍼가 옵코드의
주소 바이트를 「다음 텍스트 런의 머리」로 먹어 버려서, 문안을 쓰면 점프가 쓰레기 주소로 가
**진행이 깨진다** — 빌드도 정적 게이트도 초록인 채로. 대량 채우기 전에 md-ed1 에서 이 축을 세운다.

축 셋(2026-09-07 실측: 셋 다 깨끗하다):

1. **참조 목적지가 텍스트 런 한복판인가** — 대본 992 참조 중 **0**, 전투도 0.
   머리가 아닌 98 은 전부 `code`(엔진 함수 호출)이고 **스트림 밖**으로 나간다(모듈 코드다).
2. **스트림이 남의 토큰 한복판에서 시작하나** — 13 있다. 다만 재조립기가 **모든 스트림을** 꼬리로
   옮기며 참조를 다시 매기므로 겹침이 **사본 둘로 풀린다**(빌드 롬으로 확인: 블록 161 의 안 채운
   스트림이 제 문안 그대로 새 자리에 산다). ⇒ 결함이 아니라 **성질**이라 수만 굳혀 둔다.
3. 🔴 **길이를 추측한 옵코드가 문안에 나오나** — `0xF8` 은 표에선 1 인데 핸들러가 `(a1)+` 로 하나를
   더 읽는다(`tools/scene.py` 주석). 지금은 **한 번도 안 나오므로** 추측이 안 걸린다. 나오기
   시작하면 그 순간이 pc98 과 같은 자리다 — **게이트를 세워 둔다.**
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import battle
import common
import scene

KNOWN_JSON = common.GAME_DIR / "textmap" / "ref_shape.json"
GUESSED = {0xF8}  # 길이를 흐름으로만 아는 코드 — 문안에 나오면 멈춘다


def scan() -> dict:
    d = common.rom()
    midtext: list[str] = []
    overlap: list[str] = []
    guessed: list[str] = []
    refs = 0

    def walk(tag: str, streams, block: int):
        nonlocal refs
        heads = {t.off for st in streams for t in st.tokens}
        texts = [(t.off, len(t.raw)) for st in streams for t in st.tokens if t.kind == "text"]
        for st in streams:
            for t in st.tokens:
                if t.code in GUESSED:
                    guessed.append(f"{tag}:{block}:{t.off:04x} <{t.code:02x}>")
                if not t.ref or t.target is None:
                    continue
                refs += 1
                if t.target in heads:
                    continue
                if any(o < t.target < o + n for o, n in texts):
                    midtext.append(f"{tag}:{block}:{t.off:04x} <{t.code:02x}> → {t.target:04x}")
        starts = {st.start for st in streams}
        for st in streams:
            for t in st.tokens:
                for s in starts:
                    if t.off < s < t.off + len(t.raw):
                        overlap.append(f"{tag}:{block}:{st.start:04x}⊃{s:04x}")

    for n, (_s, b, _e) in enumerate(archives.blocks(d, archives.ARCHIVES["script"][0])):
        walk("script", list(scene.parse_module(b).streams.values()), n)
    bmap = json.loads(battle.MAP_JSON.read_text(encoding="utf-8"))
    for n, (_s, b, _e) in enumerate(battle.blocks(d)):
        sts = []
        for tgt, e in battle.refs(b).items():
            st = e["stream"]
            ent = bmap.get(battle.pos_key(st, n, tgt)) or bmap.get(battle.jp_key(st)) or {}
            sts.append(battle.drop_goto(st, ent.get("ours") or ""))  # 재삽입과 같은 판단
        walk("battle", sts, n)
    return {
        "refs": refs,
        "midtext": sorted(midtext),
        "overlap": sorted(overlap),
        "guessed": sorted(guessed),
    }


def main() -> None:
    r = scan()
    known = json.loads(KNOWN_JSON.read_text(encoding="utf-8")) if KNOWN_JSON.exists() else {}
    if "--freeze" in sys.argv:
        KNOWN_JSON.write_text(
            json.dumps({"overlap": r["overlap"]}, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8",
        )
        print(f"  {KNOWN_JSON}: 겹치는 짝 {len(r['overlap'])} 굳힘")
        return
    new_overlap = [x for x in r["overlap"] if x not in known.get("overlap", [])]
    print(
        f"  참조 {r['refs']} · 글자 한복판 {len(r['midtext'])} · "
        f"겹치는 짝 {len(r['overlap'])}(새 {len(new_overlap)}) · 추측 길이 옵코드 {len(r['guessed'])}"
    )
    bad = []
    for x in r["midtext"]:
        bad.append(f"🔴 분기 목적지가 글자 한복판 — {x}")
    for x in r["guessed"]:
        bad.append(f"🔴 길이를 추측한 옵코드가 문안에 나온다 — {x} (scene.ARGS 를 실물로 확인한다)")
    for x in new_overlap:
        bad.append(f"⚠ 새로 겹치는 스트림 — {x} (재조립이 사본으로 푸는지 확인하고 --freeze)")
    for b in bad:
        print(f"    {b}")
    if "--check" in sys.argv and bad:
        raise SystemExit("토큰 경계 검사 실패")


if __name__ == "__main__":
    main()
