#!/usr/bin/env python3
"""**시스템·행동 로그의 문체가 원문 등급과 같은가**를 최종 바이트 기준으로 잡는다(번역 규칙 4-17 — 마스터 11-15).

🔴 **방향이 다시 돌아왔다.** 09-05~06 「원문이 정중이니 우리도 정중」 → 10-03 「전부 평어」(평어가 남지 않게 정중을 잡았다) →
**11-15 「전투로그 등도 원문방향으로」**: 원문 끝이 `〜ました/ます` 인데 우리가 평서(`~었다`)면, 원문이 `〜た` 인데 우리가 존대(`~습니다`)면 잡는다.
화면에 나가는 바이트(정형 블록 조립기·textmap 포함)를 보고, 핫픽스 시험 경로(`ED_HOTFIX=1`) 값으로 잰다 — 제품(v1.2.0)은 잠겨 있다.

화자 이름표가 없는 `%s` 주입 블록(시스템·행동 로그)과 전투·아이템 코퍼스만 본다(NPC 대사는 인물이 정한다).
`--textmap` 은 원본 이미지를 훑는다(느림·게이트 밖).

  python3 tools/check_register_vs_jp.py             # 씬 전수 (게이트)
  python3 tools/check_register_vs_jp.py --textmap   # 전투·아이템 코퍼스 (원본 필요, 느림)
"""

import io
import os
import re
import sys
from contextlib import redirect_stdout

os.environ.setdefault("LOCK_BYPASS", "1")
os.environ.setdefault("ED_HOTFIX", "1")  # 핫픽스 시험 경로 값으로 잰다(import 전에 정해야 한다)

import reinsert_kr_pilot as R
from reinsert_kr_pilot import SCN_FILES

POLITE_JP = re.compile(r"(ました|ます|ません|でした|です)[。！？\s]*$")
PLAIN_JP = re.compile(r"(?<!まし)(?<!でし)(た|だ)[。！？\s]*$")
PLAIN_KR = re.compile(r"(었다|았다|였다|했다|한다|된다|이다)[.!?…\s]*$")
# 10-03: 우리 쪽이 **정중 평서**로 끝나면 결함이다(물음 `〜습니까?`는 도구점 주인의 말이라 뺀다).
POLITE_KR = re.compile(r"습니다[.!?…\s]*$")
# 화자 이름표 = 블록 머리의 `%c…%c` **뒤가 개행**. 조사가 오면 아이템 구간이다.
NAMEPLATE = re.compile(r"^%c[^%\n]{1,20}%c\n")


def _log_ids(name):
    """정본에서 시스템·행동 로그 블록의 eid 집합 — 주입 표지(`\\x1a`·`\\x17`) 블록."""
    import json
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "script" / f"{name}.json"
    ids = set()
    if p.exists():
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            t = v.get("t", "") if isinstance(v, dict) else ""
            if "\x1a" in t or "\x17" in t:
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
            if (POLITE_JP.search(jt) and PLAIN_KR.search(kt)) or (PLAIN_JP.search(jt) and POLITE_KR.search(kt)):
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
            hp = p.parent.parent / "hotfix" / "textmap" / f"{cls}.json"  # 핫픽스 시험 경로 값이 나가는 문안이다
            if hp.exists():
                val = json.loads(hp.read_text(encoding="utf-8")).get(e["k"], val)
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
        result = re.search(r"승리했|패했|Gold|얻었|포기했|찾았|익혔", txt)
        jtail = j.replace("\x00", "").strip()
        if result and ((POLITE_JP.search(jtail) and PLAIN_KR.search(txt)) or (PLAIN_JP.search(jtail) and POLITE_KR.search(txt))):
            out.append((cls, k, j.strip()[-26:], ours.strip()[-30:]))
    return out


def main():
    if "--textmap" in sys.argv:
        bad = scan_textmap()
        print(f"  {'❌' if bad else '✅'} 전투·아이템 코퍼스 — 원문 등급과 다른 줄: {len(bad)}")
        for c, _k, j, o in bad:
            print(f"       [{c}] {j!r} → {o!r}")
        return 1 if bad else 0
    rows = scan_scenes()
    if rows:
        print(
            f"  ❌ 로그 부류 문체가 원문 등급과 다르다(4-17 — 원문 ました→존댓말 · 원문 た→평서): {len(rows)}곳 (화자 없는 블록만 셌다)"
        )
        for n, e, j, k in rows[:20]:
            print(f"       {n}:{e}  JP …{j}  KR …{k}")
    else:
        print("  ✅ 로그 부류(런타임 주입 블록)가 전부 원문 등급이다 (ED1·ED2)")
    return 1 if rows else 0


if __name__ == "__main__":
    sys.exit(main())
