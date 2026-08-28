#!/usr/bin/env python3
"""번역 페이로드 — **새턴 전용 블록**을 별도 에이전트에게 넘긴다.

## 왜 있나

새턴 씬 블록의 저본은 PS1 사전(`line_dict.json`)인데, **781줄은 거기 없다**(실측
2026-08-29). 763 은 PS1 트리에 원문조차 없는 **이식판 고유 문안**이고(새턴 세이브 메시지 ·
반각 가타카나 UI · 본체에 든 ED2 프롤로그 · 포트끼리 갈린 대사), 19 는 그쪽이 저작권
분류상 **일부러 막은** 것이다. 어느 쪽이든 **기다려서 들어오지 않는다** — 우리가 쓴다.

## 🔴 왜 별도 에이전트인가

정발(만트라 DOS)을 저본으로 쓰지 않는다는 게 이 레포 규율이고, **페이로드로 가리는 것만
으로는 부족하다** — 같은 세션에서 앞서 정발 문안을 읽었으면 문맥이 이미 오염된다
(PS1 실측 2026-08-19). 이 파일이 그 경계다. 번역은 **그 문안을 본 적 없는** 에이전트가
하고, 검수는 문맥을 든 세션이 한다.

⚠ 이웃 문맥으로 **PS1 사전의 우리 문안**은 준다 — 그건 우리가 쓴 것만 담긴 창구라
(`patcher-checklist.md` 10-D) 오염원이 아니고, **인물 말투를 잇는 데 필요하다.**

  python3 tools/translate_payload.py                 # 현황만
  python3 tools/translate_payload.py --write [파일…] # work/review/translate/*.json
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "..", "shared"),
)

import common
import patch_scn as S
import patch_ui as U
import typeset_scn as T
from text.line_key import key as line_key

OUT = os.path.join(common.REVIEW_DIR, "translate")
JA = re.compile(r"[぀-ゟ゠-ヿ㐀-䶵一-鿿]")
CTX = 3  # 앞뒤로 보여 줄 이웃 수


def _screen(jp):
    """화면에 나갈 일본어인가 — 서식 문자열·파일명은 번역 대상이 아니다(659건)."""
    return bool(JA.search(re.sub(r"%[csd]|\n|\x00", "", jp)))


SENT = re.compile(r"[。！？!?…」』･・ー]")
# 🔴 **바이너리를 글자로 잘못 읽은 것** — 포인터·좌표가 cp932 로 우연히 풀린 자리다
#    (`CAﾃy7烙` · `/F/f/VO"ﾐJ舶封@`). 번역기에 주면 뜻을 지어낸다. 특징은 **반각 가나와
#    한자·기호가 뒤섞이고 조사가 없다**는 것이다.
HALFKANA = re.compile(r"[\uff61-\uff9f]")
KANA = re.compile(r"[぀-ゟ゠-ヿ]")


def is_dialogue(jp):
    """대사인가 — **번역 에이전트에게 줄 것만** 고른다.

    🔴 페이로드에 **성격이 다른 셋**이 섞여 들어온다(실측 2026-08-29: 355 중 94):

      · 마법서 이름 23종(`〜の書`) · 성 이름 — **이름 정본**(`shared/glossary`) 몫이다
      · `戦う` · `戦闘設定` · `オートバトル` · `ロード中 ...` — **시스템 문구**
        (`script/system.json` → `patch_ui`) 몫이다. ⚠ 상태 약어(`跳`·`毒`)는 **고정폭 표**라
        아예 손대면 안 된다(patch_ui 주석)
      · `CAﾃy7烙` · `/F/f/VO"ﾐJ舶封@` — 바이너리를 글자로 잘못 읽은 것. 텍스트가 아니다

    이것들을 대사 번역기에 주면 **표기 정본을 안 보고 새로 지어낸다.** 문장인 것만 준다.
    """
    body = re.sub(r"%[csd]|\n|\x00", "", jp).strip()
    if not body:
        return False
    # 오독은 반각 가나가 섞이는데 전각 가나(조사)가 없다 — 일본어 문장이면 조사가 있다
    if HALFKANA.search(body) and not KANA.search(body):
        return False
    # ⚠ `%c` 로 닫히면 **메시지 블록**이다 — 메뉴 라벨은 마크업 없이 홀로 놓인다
    return "\n" in jp or "%c" in jp or bool(SENT.search(body)) or len(body) > 18


def _speaker(jp, names):
    """화자 이름(정본 표기). 못 고르면 빈 문자열."""
    texts, marks = T.split(jp)
    if not marks:
        return ""
    sp = T.speaker_slot(texts, marks)
    if sp is None:
        return ""
    return names.get(texts[sp], texts[sp])


def rows(canon, names, mm):
    """`{파일: [줄…]}` — 번역할 줄과 그 이웃(문맥)."""
    out, labels = {}, []
    for path, _lba, _size in common.iso_files(mm):
        if not S.SCN_RE.match(path):
            continue
        got = S.load(path)
        if not got:
            continue
        _base, ents = got
        mine = S.owned_elsewhere(path)
        seq = []
        for e in ents:
            jp = e.get("text", "")
            if not jp or int(e["file_offset"], 16) in mine:
                continue
            k = line_key(jp)
            seq.append((k, jp, canon.get(k)))
        todo = [i for i, (_k, jp, kr) in enumerate(seq) if kr is None and _screen(jp)]
        if not todo:
            continue
        want = set()
        for i in todo:
            want |= set(range(max(0, i - CTX), min(len(seq), i + CTX + 1)))
        seen, lines = set(), []
        for i in sorted(want):
            k, jp, kr = seq[i]
            if i in todo:
                if k in seen:  # 같은 원문은 한 번만 — 문안도 하나다
                    continue
                seen.add(k)
                if not is_dialogue(jp):
                    labels.append({"file": path, "jp": jp})
                    continue
                _texts, marks = T.split(jp)
                lines.append(
                    {
                        "key": k,
                        "화자": _speaker(jp, names),
                        "jp": jp,
                        "인자": ["%" + m for m in marks if m in "sd"],
                        "번역": "",
                    }
                )
            elif kr:
                lines.append({"문맥": kr, "화자": _speaker(jp, names)})
        out[path] = lines
    return out, labels


def main():
    write = "--write" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    canon = S.load_canon()
    names = T._names()
    _f, mm = common.open_image()
    got, labels = rows(canon, names, mm)
    mm.close()
    _f.close()
    if only:
        got = {p: v for p, v in got.items() if any(o in p for o in only)}
    n = sum(sum(1 for r in v if "번역" in r) for v in got.values())
    print(f"  번역 대상 {n:,}줄 · {len(got)}파일 (같은 원문은 한 번만)")
    print(f"  ⏭ 대사가 아니라 뺀 것 {len(labels):,} — 이름 정본·시스템 문구·오독 (`is_dialogue`)")
    for p, v in sorted(got.items(), key=lambda kv: -sum(1 for r in kv[1] if "번역" in r))[:8]:
        print(f"    {sum(1 for r in v if '번역' in r):4}  {p}")
    if not write:
        print("\n  `--write` 로 페이로드를 뜬다 — work/review/translate/")
        return 0
    os.makedirs(OUT, exist_ok=True)
    for p, v in got.items():
        dst = os.path.join(OUT, p.strip("/").replace("/", "_").replace(".BIN", "") + ".json")
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(v, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "_labels.json"), "w", encoding="utf-8") as f:
        json.dump(labels, f, ensure_ascii=False, indent=1)
    print(f"  → {OUT}  (뺀 것은 `_labels.json` — 사람이 어느 표로 갈지 정한다)")
    return 0


if __name__ == "__main__":
    common.verify_source()
    U.slot_plan  # noqa: B018  (임포트 순서를 고정한다 — patch_scn 이 슬롯 계획을 쓴다)
    sys.exit(main())
