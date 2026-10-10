"""시스템 문자열 표 — **사전·정본에서 읽는다**. 게임 폴더에 JP→KR 표를 두지 않는다(마스터 10-08 「자기 표 0」).

종전 `script/system.json`(원문 키 → 우리 문안, 165줄)은 걷었다. 문안은 공용 정본(`shared/canon/ed3.json` — ui·speaker·system·battle)과
고유명사(`shared/canon/nouns/ed3.json`)가 갖고, 이 게임이 가진 건 **엔진 쪽 사정**뿐이다 — `script/system_keys.json`:

    {"<절>": [[엔진 원문 열쇠, 앞 공백, 뒤 공백, 줄바꿈표지, (정본에 없는 값)], …]}

  · 원문 열쇠 = 그 문자열이 이미지에 박힌 꼴(앞 들여쓰기·`\\r`·종결 바이트 포함). 값이 없는 **목록**이라 표가 아니다.
  · 앞·뒤 공백 = 화면 칸 정렬용 배치(안내 화면 가운데 정렬 등 — `center_notice.py` 가 계산한다). 문안이 아니다.
  · 줄바꿈표지 = N 이면 정본 값의 N 번째 공백 자리가 엔진 줄바꿈(`\\r`)이다.
  · 다섯째 칸(선택) = 정본·사전에 아직 없는 열쇠의 임시 값(관리자에게 후보로 보낸 것) — 정본에 오르면 지운다. 지금은 쓰는 곳이 없다.

종결 바이트(`\\x0f`·`\\x10`·`\\x00` …)는 원문 열쇠 끝에서 그대로 가져온다. 자리표(`%d`·`%s`)는 열쇠의 것을 순서대로 값에 꽂는다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C

sys.path.insert(0, os.path.join(C.ROOT, "shared"))
import canon as CN

KEYS = os.path.join(C.GAME_DIR, "script", "system_keys.json")
TITLE = "ed3"
_CTL = re.compile(r"[\x00-\x09\x0b-\x1f]")
_TOK = re.compile(r"%\d*[sd]")
_SLOT = re.compile(r"\{(?:name|item|spell|n|m|unit)\}")
_TAIL = re.compile(r"[\x00-\x1f]+$")
_cache = {}
FOLD = -1  # 줄바꿈표지 값 — 어절 접기 문구(위 `build`)
FOLD_MARK = "\x1f"  # 접기 표지 바이트 — 스텁이 `%s` 바로 뒤에서 본다


def norm(raw):
    """엔진 원문 → 정본 열쇠 꼴 — 제어·줄바꿈·바깥 공백을 벗기고 자리표를 하나로 모은다."""
    return _TOK.sub("\0", _CTL.sub("", raw.replace("\r", ""))).strip(" ")


def _index():
    """`{정규화 열쇠: [(출처, 값)]}` — 정본 전 범주 + 사전 전 범주."""
    if "idx" not in _cache:
        idx = {}
        for src, cats in (
            ("canon", CN.load(TITLE)["categories"]),
            ("dict", CN.nouns(TITLE)["categories"]),
        ):
            for cat, t in cats.items():
                for k, v in t.items():
                    if isinstance(v, str):
                        idx.setdefault(_SLOT.sub("\0", k).strip(" "), []).append((src, cat, v))
        _cache["idx"] = idx
    return _cache["idx"]


def body(raw, prefer="canon"):
    """원문 열쇠 → 정본 값(자리표 `{..}` 가 든 채) 또는 `None`."""
    hits = _index().get(norm(raw))
    if not hits:
        return None
    hits = sorted(hits, key=lambda h: h[0] != prefer)
    return hits[0][2]


def _fill(val, raw):
    """정본 값의 자리표 `{name}` 들을 원문 열쇠의 `%d`·`%s` 로 순서대로 바꾼다."""
    toks = iter(_TOK.findall(raw))
    return _SLOT.sub(lambda m: next(toks), val)


def build(raw, lead, trail, nl, override=None, prefer="canon"):
    """엔진 열쇠 하나의 값 — 앞공백 + 정본 값 + 뒤공백 + 종결 바이트."""
    val = override if override is not None else body(raw, prefer)
    if val is None:
        return None
    val = _fill(val, raw)
    if nl == FOLD:
        #   🔴 로그성 문구 — 줄바꿈 자리를 **실행 중에** 정한다(조사 훅 스텁 `patch_josa_hook` 의 접기 단계). 첫 `%s` 앞 공백을 걷고
        #     `%s` 바로 뒤에 접기 표지(0x1F)를 단다 — 스텁이 표지를 보면 「공백 + 이름 + 뒷말」을 한 덩이로 만들어 어절 경계에서만 접는다.
        #     표지는 화면에 안 나간다(스텁이 서식 꼬리를 종결 바이트로 잘라 낸다) — 스텁이 안 돌면 표지 글자 하나가 보일 뿐 문안은 같다.
        val = val.replace(" %s", "%s" + FOLD_MARK, 1)
    elif nl:  # nl 번째 공백이 엔진 줄바꿈
        at = -1
        for _ in range(nl):
            at = val.index(" ", at + 1)
        val = val[:at] + "\r" + val[at + 1 :]
    m = _TAIL.search(raw)
    return " " * lead + val + " " * trail + (m.group(0) if m else "")


def sections():
    """`{절: {원문: 우리 문안}}` — 옛 `system.json` 과 같은 꼴. 정본에 없어 값이 안 나오는 열쇠는 빠진다."""
    if "sec" not in _cache:
        with open(KEYS, encoding="utf-8") as f:
            doc = json.load(f)
        out = {}
        for sec, items in doc.items():
            if sec.startswith("_"):
                continue
            t = {}
            for it in items:
                raw, lead, trail, nl = it[0], it[1], it[2], it[3]
                ov = it[4] if len(it) > 4 else None
                v = build(raw, lead, trail, nl, ov, "dict" if sec == "person" else "canon")
                if v is not None:
                    t[raw] = v
            out[sec] = t
        _cache["sec"] = out
    return _cache["sec"]


def missing():
    """정본·사전에 없어 값이 안 나오는 열쇠 — `[(절, 원문)]`. 있으면 후보를 관리자에게."""
    with open(KEYS, encoding="utf-8") as f:
        doc = json.load(f)
    have = sections()
    return [(s, it[0]) for s, items in doc.items() if not s.startswith("_") for it in items if it[0] not in have.get(s, {})]
