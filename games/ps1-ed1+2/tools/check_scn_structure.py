#!/usr/bin/env python3
"""**씬 대사 블록의 구조(제어 코드 열)를 원본과 짝지어 대조** + 재배치 장부(`relocations.tsv`) 검증.

**왜.** 재배치·꼬리 옮기기·쪽 넘김·채움은 글자가 아니라 **제어 바이트**를 조용히 틀린다. ss-ed3(10-21)에서 재조판 때
대사 끝에 넣은 채움 바이트(FF FF)가 다음 블록 호출을 막아 새 게임 첫 장면에서 대사가 통째로 빠졌다 — 문안·조판 게이트는
글자를 보고, 하네스·qa 는 블록을 한 장씩 띄워 보므로 **연속 재생에서만** 드러났다. 여기는 글자를 뺀 제어 코드 열만
원본 블록과 최종 이미지 블록으로 짝지어 비교한다(전 씬 19개 · 전 블록).

PS1 씬 블록 문법·토큰 정의는 `scn_structure.py` 머리말. 검사 항목:
  ① 블록 열 대조 — 원본 ↔ 최종 이미지. %c/%s/%d·제어바이트·종단이 달라지면 **허용 표(빌드의 의도 오버라이드 표
     NAME_PLATE·COLOR_*·FOLD_NAME … + 특수 블록)에 든 것만** 통과. 개행(0x0A)은 조판이 다시 하므로 개수 차이를 안 친다.
  ② 종단·정렬 — 모든 블록 끝에 00 이 있고, 4의 배수였던 블록은 4의 배수.
  ③ 빈틈 — 블록 밖 바이트는 00 이거나 원본 그대로. (채움 바이트가 00 이 아니면 앞 문자열이 이어 읽힌다)
  ④ 포인터 — 재삽입이 고친 모든 lui+addiu/ori 를 **최종 이미지에서 다시 읽어** 새 블록 시작(+원래 델타)을 가리키는지.
     이주·표머리 사본·정형 사본 리타깃도 같이 맞춘다. 뒤 단계 패치가 다시 잡은 자리는 블록에 닿으면 「포인터(후속)」로 센다.
  ⑤ 뒤 단계 패치 — 재삽입 직후와 바이트가 달라진 블록(지명·HUD 슬롯·경로 라벨 등)은 %c/%s/%d 열만 엄격히 본다.
  ⑥ 장부 — 재삽입기가 **실제로 한 재배치**를 기록(`work/derived/scn_reloc.json`)하고, 거기서 `relocations.tsv` 를
     자동으로 뽑는다. 커밋된 장부와 다르면 실패(장부에 없는 재배치가 빌드에 있거나 그 반대) — 의도했으면
     `--update-ledger` 로 갱신하고 diff 를 본다. 손으로 쓰지 않는다.

되돌리기: 종류별 환경 변수 스위치(`PILOT_FIXED` · `PILOT_NO_DONOR` · `PILOT_NO_ALIAS` · `PILOT_NO_STUBS=씬:eid` ·
`PILOT_EXCLUDE_EIDS`)를 장부의 「되돌리면」 열에 적었다. 스위치가 없는 종류는 그렇게 적혀 있다.

⚠ 빌드가 없거나(재배치 기록 없음) 기록과 이미지가 엇갈리면 통과가 아니라 **「안 쟀다」로 실패**한다.

  python3 tools/check_scn_structure.py                  # 게이트
  python3 tools/check_scn_structure.py -v               # 허용 목록 전량
  python3 tools/check_scn_structure.py --update-ledger  # 장부 갱신(빌드가 바뀐 게 의도일 때)
"""

import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import scn_structure as SS

LEDGER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "relocations.tsv"
)


def load():
    from check_scn_jp_left import IMG
    from common import OUT_DIR, extract

    p = os.path.join(OUT_DIR, "scn_reloc.json")
    if not os.path.exists(p):
        print(f"  ❌ 안 쟀다 — 재배치 기록 없음({p}) · build.py 를 먼저 돌린다")
        return None
    if not os.path.exists(IMG):
        print(f"  ❌ 안 쟀다 — 최종 이미지 없음({IMG})")
        return None
    recs = json.load(open(p, encoding="utf-8"))["scenes"]
    layout = json.load(open(os.path.join(OUT_DIR, "scn_layout.json"), encoding="utf-8"))
    out = {}
    for name, rec in recs.items():
        L = layout.get(name)
        if not L or L["lba"] != rec.get("new_lba") or L["size"] != rec["new_size"]:
            print(
                f"  ❌ {name}: 재배치 기록이 scn_layout.json 과 다르다(낡은 기록) — 빌드를 다시 돌린다"
            )
            return None
        doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{name}.json"), encoding="utf-8"))
        raw = {
            e["entry_id"]: bytes.fromhex(e["raw_hex"])
            for e in doc["entries"]
            if e.get("raw_hex") and e["kind"] != "gap"
        }
        orig = bytes(extract(rec["orig_lba"], rec["orig_size"]))
        built = bytes(extract(L["lba"], L["size"], path=IMG))
        out[name] = (rec, orig, built, raw)
    return recs, layout, out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    verbose = "-v" in argv
    loaded = load()
    if loaded is None:
        return 1
    recs, layout, scenes = loaded
    bad = []
    tot = collections.Counter()
    gate = {}
    allow = collections.Counter()
    for name in sorted(scenes, key=lambda n: (n[:3], int(n.split("SCN")[1]))):
        rec, orig, built, raw = scenes[name]
        f, cnt, _listed = SS.check_scene(rec, orig, built, raw)
        gate[name] = cnt
        for k, v in cnt.items():
            if isinstance(v, int):
                tot[k] += v
        for st in f:
            bad.append(f"{name} {st[0]}: {st[1]}")
        for ent in rec["struct"].values():
            for w in ent["why"]:
                allow[f"제어바이트·{w}"] += 1
        allow["이주"] += len(rec["donors"])
        allow["스텁(이름 헤더)"] += len(rec["stubs"])
        allow["스텁(인자 패치 워드)"] += len(rec["args"])
        allow["포인터 리타깃(표머리 사본)"] += len(rec["mid"])
        allow["포인터 리타깃(정형 사본)"] += len(rec["alias"])
        allow["앵커 접미·접두 제자리 덮어쓰기(채움)"] += len(rec["pin_ovr"])
        allow["후속패치 블록"] += len(cnt.get("later_blocks", []))
        allow["포인터(후속)"] += len(cnt.get("later_ptrs", []))
    nb = tot["blocks"]
    print(
        f"  구조 대조 [ps1-ed1+2] — 대조 블록 {tot['compared']}/{nb} (씬 {len(scenes)}) · "
        f"어긋남 {len(bad)} · 포인터 {tot['ptr_ok']}/{tot['ptr']} 일치 · 빈틈 이상 {tot['gap_bytes']}B"
    )
    print(
        f"    목표 바이트(남이 포인터로 들어오는 자리의 제어·종단) {tot['tgt_ok']}/{tot['tgt']} 일치"
        f"(선두 개행 제거 {tot['tgt_lead_nl']} 허용) · 코드 j/jal 이 텍스트로 들어옴 {tot['jump_into_text']}건"
    )
    print(
        "    허용 목록: " + " · ".join(f"{k} {v}" for k, v in sorted(allow.items()) if v)
        if any(allow.values())
        else "    허용 목록: 없음"
    )
    if verbose:
        for name in sorted(scenes):
            rec = scenes[name][0]
            for eid, ent in sorted(rec["struct"].items(), key=lambda x: int(x[0])):
                print(
                    f"      · {name} jp{eid} {ent['kinds']} {ent['old']}→{ent['new']} ({'/'.join(ent['why'])})"
                )
    for b in bad[:40]:
        print(f"    ❌ {b}")
    # 장부
    rows = SS.ledger_rows(recs, layout, gate)
    text = SS.ledger_text(rows)
    kinds = collections.Counter(r[1] for r in rows)
    print(
        "  재배치 장부 relocations.tsv — "
        + " · ".join(f"{k} {v}" for k, v in sorted(kinds.items()))
        + f" (총 {len(rows)}행)"
    )
    if "--update-ledger" in argv:
        with open(LEDGER, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"    장부 갱신: {LEDGER}")
    elif not os.path.exists(LEDGER):
        print("    ❌ 장부 파일이 없다 — `--update-ledger` 로 만들어 커밋한다")
        bad.append("ledger-missing")
    else:
        cur = open(LEDGER, encoding="utf-8").read()
        if cur != text:
            a, b = set(cur.splitlines()), set(text.splitlines())
            print(
                f"    ❌ 장부가 빌드와 다르다 — 빌드에만 있는 행 {len(b - a)} · 장부에만 있는 행 {len(a - b)} "
                "(의도한 재배치면 `--update-ledger` 후 diff 를 본다)"
            )
            for r in sorted(b - a)[:5]:
                print(f"       + {r[:160]}")
            for r in sorted(a - b)[:5]:
                print(f"       - {r[:160]}")
            bad.append("ledger-diff")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
