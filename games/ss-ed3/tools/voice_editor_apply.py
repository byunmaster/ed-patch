"""편집기에서 바꾼 음성 자막(초상·대사)을 `voice.json` 에 반영한다.

    python3 games/ss-ed3/tools/voice_editor_apply.py edits.json            # 무엇이 바뀌나만 본다
    python3 games/ss-ed3/tools/voice_editor_apply.py edits.json --write    # voice.json 에 쓴다

`edits.json` 은 편집기가 내는 목록이다. 항목은 `voice_editor_data.py` 의 `scene`·`idx` 로 칸을 가리키고 아래만 읽는다(없는 키는 안 건드린다):

    kr      자막 문안 — 줄바꿈은 `\\n`. 빈 줄이면 거부한다(단 코멘트에 「제거」가 있고 kr 이 빈 문안이면 그 줄을 지운다 — 시계 장면만).
    face    초상 번호(전역 인물 0~0x13). `null`·"none" = 얼굴 없음, "default" = speaker 로 되돌림.
    expr    표정 번호(기본 0).
    spk_id / spk_name   화자 변경 — `speaker`(번호, None 이면 지움) · `who`(이름표 글자).
    ts / te 자막 열림·닫힘 시각(초, 음성 0초 기준) — 시계 장면(items)만: `t`·`dur` 로 쓴다. hooks 장면은 알리기만 한다.
    comment 코멘트 — 읽기만 하고 voice.json 에는 안 쓴다(보고용).
    (idx 가 `a…` 문자열인 항목은 편집기에서 **추가한 줄**의 고침이다 — `--adds` 목록의 같은 `aid` 줄에 덧씌운다.)
    pos     대사창 위치 — "top"(원판 위 창) · "bottom"(기본). bottom 이면 키를 지운다(미리 싣기와 무관하게 어느 장면에나 쓴다).

🔴 **얼굴이 못 뜨는 장면(미리 싣기 없음 — V02·V07·V09)에는 `face` 를 거부한다.** 음성 중엔 CD 가 음성 것이라 로드가 안 끝나 영영 안 뜬다
(`voice_sub.by_map` 도 같은 이유로 빌드를 멈춘다). 장면의 (얼굴, 표정) 조합이 엔진 캐시 8칸을 넘어도 거부한다.
초상을 바꾸면 그 장면 미리 싣기의 `wait`(얼굴 수 × 20 + 10 프레임, 모자랄 때만 올린다 — 낮추지 않는다)도 같이 다시 센다.
문안은 폭·줄 수를 여기서 안 잰다 — 빌드 게이트가 잰다(`build.py`).
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import voice_sub as VS


def refs(ent):
    """자막이 있는 칸의 **원본 dict** 목록 — `voice_editor_data.slots` 와 같은 순서."""
    if ent.get("items"):
        return list(ent["items"])
    return [h for h in ent["hooks"] if h.get("lines") and not h.get("preload")]


def preload_of(ent):
    if (ent.get("clock") or {}).get("preload"):
        return ent["clock"]["preload"]
    for h in ent["hooks"]:
        if h.get("preload"):
            return h
    return None


def merge_adds(adds, edits):
    """`(추가 줄 목록, 기존 줄 edits)` — idx 가 `a…` 인 edits 를 같은 `aid` 의 추가 줄에 덧씌워 합친다."""
    byid = {a["aid"]: dict(a) for a in adds}
    plain = []
    for e in edits:
        if str(e["idx"]).startswith("a"):
            if e["idx"] in byid:
                byid[e["idx"]].update({k: v for k, v in e.items() if k not in ("scene", "idx", "at")})
        else:
            plain.append(e)
    return list(byid.values()), plain


def add_items(doc, adds):
    """편집기에서 추가한 줄을 `items` 에 시각 순서로 끼운다 — 시계(items) 장면만. `(들어간 수, 메모)`."""
    n, notes = 0, []
    for a in adds:
        vid = a["scene"]
        if vid not in doc or vid.startswith("_") or not doc[vid].get("items"):
            raise SystemExit(f"{vid}: 줄 추가는 시계(items) 장면만 된다")
        lines = str(a.get("kr", "")).split("\n")
        if not lines or any(not x.strip() for x in lines):
            raise SystemExit(f"{vid} {a['aid']}: 추가한 줄의 문안이 비었다")
        ts, te = float(a["ts"]), float(a["te"])
        if te <= ts:
            raise SystemExit(f"{vid} {a['aid']}: 닫힘({te}) 이 열림({ts}) 보다 앞이다")
        it = {"t": round(ts, 2), "who": str(a.get("spk_name") or ""), "lines": lines, "dur": round(te - ts, 2)}
        if a.get("spk_id") is not None:
            it["speaker"] = int(a["spk_id"])
        if a.get("pos") == "top":
            it["pos"] = "top"
        if a.get("face") is not None:
            if preload_of(doc[vid]) is None:
                raise SystemExit(f"{vid} {a['aid']}: 이 장면은 미리 싣기가 없어 얼굴을 못 쓴다(얼굴 불가)")
            f = int(a["face"])
            if not 0 <= f < VS.GLOBAL_CAST:
                raise SystemExit(f"{vid} {a['aid']}: 얼굴 {f} 은 전역 인물이 아니다")
            it["face"] = f
            if int(a.get("expr", 0)):
                it["expr"] = int(a["expr"])
        items = doc[vid]["items"]
        i = next((k for k, x in enumerate(items) if x.get("t", 0) > it["t"]), len(items))
        items.insert(i, it)
        n += 1
    return n, notes


def apply(doc, edits, adds=()):
    """`(바뀐 칸 수, 메모 목록)` — `doc` 을 제자리에서 고친다. 거부 사유가 있으면 `SystemExit`.

    `adds` = 편집기에서 추가한 줄. 기존 줄 edits(idx 번호는 **추가 전** 순서)를 먼저 적용하고 추가 줄을 끼운다."""
    adds, edits = merge_adds(list(adds), edits)
    changed, notes = 0, []
    # 문안이 빈 추가 줄 = 아직 받아쓰기 전의 자리표시 — 넣지 않고 알린다
    pending = [a for a in adds if not str(a.get("kr", "")).strip()]
    adds = [a for a in adds if str(a.get("kr", "")).strip()]
    for a in pending:
        notes.append(f"{a['scene']} 추가 줄 {a['aid']}({a['ts']}~{a['te']}s, {a.get('spk_name')}): 문안이 비어 건너뜀 — 받아쓰기 필요")
    removed = []
    touched = set()
    for e in edits:
        vid, idx = e["scene"], int(e["idx"])
        if vid not in doc or vid.startswith("_"):
            raise SystemExit(f"{vid}: 없는 장면")
        sl = refs(doc[vid])
        if not 1 <= idx <= len(sl):
            raise SystemExit(f"{vid} #{idx}: 칸이 없다(1~{len(sl)})")
        it, before = sl[idx - 1], json.dumps(sl[idx - 1], ensure_ascii=False, sort_keys=True)
        if e.get("kr") == "" and "제거" in str(e.get("comment", "")):
            removed.append((vid, idx))  # 줄 제거 요청(코멘트 「제거」 + 빈 문안) — 번호가 밀리지 않게 마지막에 지운다
            touched.add(vid)
            continue
        if "kr" in e:
            lines = [x.strip() for x in str(e["kr"]).split("\n")]  # 줄 끝·첫머리 공백은 편집기에서 딸려 온 것 — 버린다
            if not lines or any(not x.strip() for x in lines):
                raise SystemExit(f"{vid} #{idx}: 빈 줄이 든 문안은 못 받는다")
            it["lines"] = lines
        if "spk_name" in e or "spk_id" in e:
            # 화자 변경(편집기 10-17) — 번호는 전역 인물(<0x14)이나 그 맵의 이름표, 없으면(None) 이름만 둔다
            sid = e.get("spk_id")
            if sid is None:
                it.pop("speaker", None)
            else:
                it["speaker"] = int(sid)
            if e.get("spk_name"):
                it["who"] = str(e["spk_name"])
        if "ts" in e or "te" in e:
            if "t" not in it:
                notes.append(f"{vid} #{idx}: 시각은 hooks 장면이라 손으로 옮겨야 한다(ts/te 건너뜀)")
            else:
                ts = float(e.get("ts", it["t"]))
                te = float(e.get("te", it["t"] + it.get("dur", 0)))
                if te <= ts:
                    raise SystemExit(f"{vid} #{idx}: 닫힘({te}) 이 열림({ts}) 보다 앞이다")
                it["t"] = round(ts, 2)
                it["dur"] = round(te - ts, 2)
        if "pos" in e:
            if e["pos"] not in ("top", "bottom"):
                raise SystemExit(f"{vid} #{idx}: pos 는 top/bottom 이다 — {e['pos']!r}")
            if e["pos"] == "top":
                it["pos"] = "top"
            else:
                it.pop("pos", None)
        if "face" in e or "expr" in e:
            no_preload = preload_of(doc[vid]) is None
            if no_preload and "face" in e:
                raise SystemExit(
                    f"{vid} #{idx}: 이 장면은 미리 싣기가 없어 얼굴을 못 쓴다(얼굴 불가)"
                )
            f = e.get("face", "default")
            if "face" not in e and no_preload:
                notes.append(f"{vid} #{idx}: 표정만 바꿨지만 이 장면은 얼굴이 안 떠 건너뜀(미리 싣기 없음)")
                f = "keep"
            elif "face" not in e:
                # 표정만 바꾼 편집 — 얼굴은 지금 값(없으면 speaker)을 그대로 둔다. "default" 로 읽으면 표정이 통째로 버려진다
                base = it["face"] if "face" in it else it.get("speaker")
                if base is None or not isinstance(base, int) or base >= VS.GLOBAL_CAST:
                    notes.append(f"{vid} #{idx}: 표정만 바꿨지만 이 줄엔 얼굴이 없어 건너뜀")
                    f = "keep"
                else:
                    f = base
            if f == "keep":
                pass
            elif f == "default":
                it.pop("face", None)
                it.pop("expr", None)
            elif f in (None, "none"):
                it["face"] = None
                it.pop("expr", None)
            else:
                f = int(f)
                if not 0 <= f < VS.GLOBAL_CAST:
                    raise SystemExit(
                        f"{vid} #{idx}: 얼굴 {f} 은 전역 인물이 아니다(0~{VS.GLOBAL_CAST - 1})"
                    )
                it["face"] = f
                it["expr"] = int(e.get("expr", 0))
                if it["expr"] == 0:
                    it.pop("expr")
        touched.add(vid)
        if json.dumps(it, ensure_ascii=False, sort_keys=True) != before:
            changed += 1
    for vid, idx in sorted(removed, reverse=True):
        it = refs(doc[vid])[idx - 1]
        if not doc[vid].get("items"):
            raise SystemExit(f"{vid} #{idx}: 줄 제거는 시계(items) 장면만 된다")
        doc[vid]["items"].remove(it)
        changed += 1
        notes.append(f"{vid} #{idx} 줄을 지웠다")
    if adds:
        k, more = add_items(doc, adds)
        changed += k
        notes += more
        notes.append(f"추가한 줄 {k}개를 끼웠다")
        touched |= {a["scene"] for a in adds}
    for vid in sorted(touched):
        pre = preload_of(doc[vid])
        if pre is None:
            continue
        faces = {VS.face(h) for h in refs(doc[vid])} - {(VS.NO_FACE, 0)}
        if len(faces) > VS.FACE_CACHE:
            raise SystemExit(
                f"{vid}: (얼굴, 표정) 조합 {len(faces)} 종이 엔진 캐시({VS.FACE_CACHE} 칸)를 넘는다 — 줄여야 한다"
            )
        # 얼굴 한 장 ~20프레임(10-16 V18 실측) — 12/장은 모자랐다. 손으로 늘려 둔 wait 는 낮추지 않는다(올리기만).
        want = 20 * len(faces) + 10
        if (pre.get("wait") or 0) < want and (doc[vid].get("clock") or {}).get("preload"):
            notes.append(f"{vid}: 미리 싣기 wait {pre.get('wait')} → {want}(조합 {len(faces)} 종)")
            pre["wait"] = want
        elif pre.get("wait") is not None and pre.get("wait") < want:
            notes.append(
                f"{vid}: ⚠ 미리 싣기 wait {pre['wait']} < 권장 {want}(조합 {len(faces)} 종) — 손으로 정한 장면이라 안 고쳤다"
            )
    return changed, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edits")
    ap.add_argument("--adds", help="편집기 `adds` 목록 JSON — 추가한 줄(없으면 생략)")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    edits = json.load(open(a.edits, encoding="utf-8"))
    doc = json.load(open(VS.SCRIPT, encoding="utf-8"))
    adds = json.load(open(a.adds, encoding="utf-8")) if a.adds else []
    n, notes = apply(doc, edits, adds)
    print(f"편집 {len(edits)}건 · 실제로 바뀐 칸 {n}")
    for x in notes:
        print(" ", x)
    if a.write:
        with open(VS.SCRIPT, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("voice.json 에 썼다 — 다음은 build.py · check.sh")
    else:
        print("(미리보기 — 쓰려면 --write)")


if __name__ == "__main__":
    main()
