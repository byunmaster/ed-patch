#!/usr/bin/env python3
"""**시스템·행동 로그가 평어체인가**를 최종 바이트 기준으로 잡는다.

🔴 **방향이 뒤집혔다(마스터 확정 2026-10-03 「전부 평어」).** 아래 서술(09-05~06)은 「원문이 정중이니
우리도 정중」 시절의 것이다. 지금은 **원문이 정중(`〜ました`)이어도 시스템·행동 로그는 평어체**로 간다
(전투 로그가 평어라 한 화면에서 섞여 보인다는 마스터 QA). 그래서 이 검사기는 같은 부류(런타임 주입
`%s` 블록 · 전투·아이템 코퍼스)에서 **정중 평서(`〜습니다`)가 남으면** 잡는다. 화면에 나가는 바이트를
본다는 이점(정형 블록 조립기 · textmap)은 그대로다 — `check_log_register` 가 정본만 보는 구멍을 메운다.

**왜(2026-09-05~06).** 이번 주에만 원문과 갈린 자리를 넷 찾았고 **전부 유저 QA 로만** 나왔다:
보물상자 정형 문구(`열었다`) · 아이템 획득(`얻었다`) · 포기(`포기했다`) · 전투 승패
(`승리했다`·`패했다`). 원문은 넷 다 `〜ました` 다.

기존 `check_log_register` 는 **정본(`script/*.json`)만** 봤다. 그런데 정형 블록은
`stock_build` 가 JP 원문 매칭으로 **정본을 안 타고** 조립하고, 전투·아이템 문구는 아예
`textmap/` 에 있다. ⇒ 정본을 정중으로 고쳐도 화면은 평어체였고 검사기는 통과했다.
**그래서 이 검사기는 화면에 나가는 바이트를 본다**(patcher-checklist 「화면에 나가는
바이트를 게이트로 본다」).

## 무엇을 비교하나

원문이 **정중**(`ました`·`ます`·`ません`·`です`)으로 끝나는데 우리가 **평어체**(`~었다`
·`~했다` …)로 끝나면 잡는다.

🔴 **NPC 대사는 대상이 아니다.** 한국어 말투는 인물·관계가 정하지 원문 종결어미가 정하지
않는다(`ですます` 로 말하는 병사가 한국어로 반말일 수 있다). **화자 이름표가 없는
블록**(시스템·해설·행동 로그)만 본다 — 거기서는 원문 종결이 곧 우리 종결이어야 한다.

⚠ **ED2 는 보고만 한다** — 인게임 QA 를 아직 안 돌아 문안이 흔들릴 수 있다. 지금 못 고치는 걸
실패로 치면 게이트가 늘 빨간불이 되고, 늘 빨간불인 검사는 아무도 안 본다.

⚠ `--textmap` 은 **원본 이미지를 훑는다**(전투·아이템 코퍼스는 JP 를 저장하지 않는다 —
저작권). 느리고 원본이 필요하니 **게이트에 안 넣는다.** 손으로 돌린다.

  python3 tools/check_register_vs_jp.py             # 씬 전수 (게이트)
  python3 tools/check_register_vs_jp.py --textmap   # 전투·아이템 코퍼스 (원본 필요, 느림)
"""

import io
import os
import re
import sys
from contextlib import redirect_stdout

os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from check_log_register import is_log_text
from reinsert_kr_pilot import SCN_FILES

POLITE_JP = re.compile(r"(ました|ます|ません|でした|です)[。！？\s]*$")
PLAIN_KR = re.compile(r"(었다|았다|였다|했다|한다|된다|이다)[.!?…\s]*$")
# 10-03: 우리 쪽이 **정중 평서**로 끝나면 결함이다(물음 `〜습니까?`는 도구점 주인의 말이라 뺀다).
POLITE_KR = re.compile(r"습니다[.!?…\s]*$")
# 화자 이름표 = 블록 머리의 `%c…%c` **뒤가 개행**. 조사가 오면 아이템 구간이다.
NAMEPLATE = re.compile(r"^%c[^%\n]{1,20}%c\n")


# 평어로 올린 **해설·획득 안내**(마스터 10-03) — 런타임 주입 표지가 없어 표지로는 못 가른다.
# 같은 씬에 라벨이 빈 NPC 대사(`정말 감사합니다`)가 섞여 있어서 **손으로 가려낸 목록**이다.
# 새 해설을 평어로 올리면 여기에 적는다(안 적으면 이 검사가 모른다).
LOG_EXTRA = {
    "ED1SCN1": {1174, 303, 1215},
    "ED1SCN2": {347, 322, 867, 916, 868, 421, 520, 923, 929},
    "ED1SCN3": {269, 344, 706, 1132, 119, 140, 271},
    "ED1SCN4": {408, 466, 649},
    "ED1SCN5": {1199},
    "ED1SCN6": {258, 212, 296, 260},
    "ED2SCN1": {35},
    "ED2SCN11": {167, 322},
    "ED2SCN2": {280, 335, 336, 337, 338, 372},
    "ED2SCN3": {335, 789},
    "ED2SCN4": {318, 691, 743},
    "ED2SCN5": {576, 599, 745},
    "ED2SCN7": {321, 520},
    "ED2SCN9": {347},
    "ED2SCN12": {153, 154, 155, 163},
}


def _log_ids(name):
    """정본에서 시스템·행동 로그 블록의 eid 집합 — 주입 표지(`\\x1a`·`\\x17`) 블록 + `LOG_EXTRA`."""
    import json
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "script" / f"{name}.json"
    ids = set(LOG_EXTRA.get(name, ()))
    if p.exists():
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            t = v.get("t", "") if isinstance(v, dict) else ""
            if "\x1a" in t or "\x17" in t or is_log_text(t):
                ids.add(int(k))
    return ids


def scan_scenes():
    out = []
    for name, _lba, _size in SCN_FILES:
        with redirect_stdout(io.StringIO()):
            rows = [(e, j, c) for _s, e, j, c, _t in R.iter_candidates((name,))]
        logs = _log_ids(name)
        for eid, jp, kr in rows:
            if int(eid) not in logs:
                continue  # 시스템·행동 로그가 아니다 — NPC 대사·말투는 인물이 정한다
            j = R.render_bytes(jp.rstrip(b"\x00"), ctrl=True)
            k = R.render_bytes(kr.rstrip(b"\x00"), ctrl=True)
            if NAMEPLATE.match(j):  # NPC 대사 — 말투는 인물이 정한다
                continue
            # 🔴 **런타임 주입(`%s`)을 가진 블록만 본다.** 이름표가 없어도 NPC 대사인
            #    블록이 있어서다(이어지는 대사 창 — `ED1SCN1:1303` 어머니의 훈계가
            #    `〜ではありません` 이라 정중으로 잡혔다. 우리 `안 된다` 는 **인물 말투**지
            #    오역이 아니다). 시스템·행동 로그는 이름·아이템을 런타임에 꽂으므로
            #    `%s` 가 표지가 된다 — 이번 주 결함 넷이 전부 이 부류였다.
            # ⚠ 한계: **주입이 없는 해설**(`문에는 자물쇠가 걸려 있습니다`)은 못 본다.
            #    그쪽은 `check_speech_level` 관할이다.
            if "%s" not in j:
                continue
            jt = re.sub(r"%[csd]", "", j).strip()
            kt = re.sub(r"%[csd]", "", k).strip()
            if not jt or not kt:
                continue
            if POLITE_KR.search(kt):
                out.append((name, eid, jt.replace("\n", " ")[-26:], kt.replace("\n", " ")[-30:]))
    return out


def scan_textmap():
    """전투·아이템 코퍼스 — 원본 이미지에서 JP 를 되찾아 대조한다(저장 안 하므로)."""
    import glob
    import json
    import pathlib

    from derive_text import jkey

    keys = {}
    for cls in ("items_battle", "battle", "battle_ed2"):
        p = pathlib.Path(__file__).resolve().parents[1] / "textmap" / f"{cls}.json"
        if not p.exists():
            continue
        for e in json.loads(p.read_text(encoding="utf-8"))["entries"]:
            val = (
                e.get("ours")
                if isinstance(e.get("ours"), str)
                else "".join(
                    x.get("ours", "") for x in e.get("parts", []) or [] if isinstance(x, dict)
                )
            )
            if val:
                keys[e["k"]] = (cls, val)
    src = glob.glob(
        str(pathlib.Path(__file__).resolve().parents[3] / "originals/jp/ps1-ed1+2/*.bin")
    )
    if not src:
        print("  ⚠ 원본 이미지가 없다 — `--textmap` 은 건너뛴다")
        return []
    with open(src[0], "rb") as f:
        data = f.read()
    pat = re.compile(rb"(?:%[csd]|[\x81-\x9f\xe0-\xef][\x40-\xfc]|[\x20-\x7e\x0a]){3,60}")
    seen, out = {}, []
    for m in pat.finditer(data):
        try:
            t = m.group().decode("cp932")
        except Exception:  # noqa: BLE001, S112 — SJIS 아닌 바이트열은 **일부러** 건너뛴다
            continue
        k = jkey(t)
        if k in keys and k not in seen:
            seen[k] = t
    for k, (cls, ours) in keys.items():
        j = seen.get(k)
        if not j:
            continue
        txt = re.sub(r"%[csd]", "", ours).strip()
        # 전투·아이템 코퍼스에는 NPC 대사(가이드·가드·왕비)가 섞여 있다 — 승패·획득·해방 같은
        # **시스템 결과 문구**만 본다(10-03).
        result = re.search(r"승리했|패했|Gold|얻었|포기했|찾았|익혔|해방|도망쳤", txt)
        if POLITE_KR.search(txt) and (result or is_log_text(txt)):
            out.append((cls, k, j.strip()[-26:], ours.strip()[-30:]))
    return out


def main():
    if "--textmap" in sys.argv:
        bad = scan_textmap()
        print(f"  {'❌' if bad else '✅'} 전투·아이템 코퍼스 — 정중 평서가 남음: {len(bad)}")
        for c, _k, j, o in bad:
            print(f"       [{c}] {j!r} → {o!r}")
        return 1 if bad else 0
    rows = scan_scenes()
    if rows:
        print(
            f"  ❌ 로그 부류에 정중 평서가 남았다(평어체여야 한다): {len(rows)}곳 (화자 없는 블록만 셌다)"
        )
        for n, e, j, k in rows[:20]:
            print(f"       {n}:{e}  JP …{j}  KR …{k}")
    else:
        print("  ✅ 로그 부류(런타임 주입 블록)가 전부 평어체다 (ED1·ED2)")
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
