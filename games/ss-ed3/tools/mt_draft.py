"""외부 모델(gemini-cli)에게 **초벌**을 시키고, 계약을 통과한 것만 받는다.

    python3 games/ss-ed3/tools/mt_draft.py MAP008              # 초벌 → work/review/mt_MAP008.json
    python3 games/ss-ed3/tools/mt_draft.py MAP008 --apply      # 통과분을 script/ 로
    python3 games/ss-ed3/tools/mt_draft.py MAP008 --batch 40   # 한 번에 던지는 블록 수

🔴 **번역이 어려운 게 아니라 계약이 어렵다.** 이 게임의 대사는 원문과 **같은 바이트**에
들어가야 하고(길이 불변), 창은 17 전각 × 3 줄이며, `0D`(줄바꿈)·`0F`(대기점) 개수를
원문과 맞춰야 한다. 실측: 어느 길이 구간이든 **다섯에 하나는 예산이 빠듯하다**
(101B 이상 구간은 여유 중앙값이 11.5% 뿐이다). 그래서 「한 번 번역시키고 끝」이 아니라
**검사 → 초과분만 「N 바이트 줄여라」로 되던지기**를 반복한다. `verify` 는 우리가 이미
쓰는 것과 같은 자(`typeset.overflows` · 바이트 예산 · 구조)다.

⚠ **초벌은 정본이 아니다.** 통과한 것도 `script/<MAP>.json` 의 `_mt` 에 이름이 남아
「아직 사람이 안 본 자리」임을 표시한다 — 말투와 문맥은 기계가 못 맞춘다(같은 대사를
다른 인물이 말하는 자리, 앞뒤 블록을 봐야 화자가 정해지는 자리).

⚠ 산출물은 `work/review/` 다 — **원문을 담으므로 커밋하지 않는다.**

🔴 **무료 등급은 호출 수가 자원이다.** 실측(2026-08-25): API 키 모드의 free tier 는
   `limit: 20` 이고 소진되면 「exhausted your **daily** quota」가 나온다 — 분당이 아니라
   **하루**다. 그래서 배치를 크게 잡아 **맵 하나를 한두 번에** 끝낸다(`--batch` 기본 120).
   한도를 늘리려면 CLI 를 **OAuth 로그인**으로 돌리거나(Code Assist 무료 등급이 훨씬 크다)
   AI Studio 에서 키를 새로 받아 `GEMINI_API_KEY` 로 준다. ⚠ 로그인은 브라우저가 필요하다.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import reinsert as R
import typeset as T

GEMINI = os.environ.get("GEMINI_BIN", "gemini")
MODEL = os.environ.get("GEMINI_MODEL", "")  # 비우면 각 경로의 기본 모델
API_KEY = os.environ.get("GEMINI_API_KEY", "")
API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
GAME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_ROUNDS = 3
MAX_429 = 5

# 🔴 응답을 **스키마로 강제한다** — 이 파이프라인에서 제일 잘 깨지는 자리가 「JSON 이 아닌
#   답이 온다」였다. 키가 동적이라 객체로는 스키마를 못 쓰므로 **배열 + id** 로 받는다.
SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {"id": {"type": "STRING"}, "kr": {"type": "STRING"}},
        "required": ["id", "kr"],
    },
}


def budget_bytes(s):
    """우리 문안이 차지할 바이트 — 반각(ASCII)은 1, 그 밖은 2, 제어는 1."""
    return sum(1 if (c in "\n\f" or ord(c) < 0x80) else 2 for c in s)


def glossary_for(jp_all):
    """그 맵에 **실제로 나오는** 고유명사만 추린다 — 정본 전량을 던지면 프롬프트만 커진다."""
    p = os.path.join(GAME, "glossary_manual.json")
    with open(p, encoding="utf-8") as f:
        cats = json.load(f)["categories"]
    out = {}
    for c in cats.values():
        for jp, kr in c.items():
            if jp in jp_all:
                out[jp] = kr if isinstance(kr, str) else kr.get("kr")
    return out


RULES = """너는 세가새턴 RPG 『백의 마녀 — 또 하나의 영웅전설』의 일→한 번역가다.
아래 규칙은 **화면에 안 나오면 번역이 아니다**. 어기면 그 문안은 버려진다.

[길이] 각 항목에는 바이트 예산이 있다. 한글·한자·전각기호 = 2바이트, 반각(ASCII) = 1바이트,
  줄바꿈/대기점 = 1바이트. **예산을 넘기면 안 된다.** 남는 건 괜찮다(자동으로 채운다).
[공백] 어절 공백은 **반각 스페이스**(ASCII 0x20)로 쓴다. 전각 공백은 쓰지 않는다.
  (창에서 반각은 0.5칸, 전각은 1칸이다. 전각으로 쓰면 예산이 곧바로 터진다.)
[구조] `\\n`(줄바꿈)과 `\\f`(대기점)의 **개수를 원문과 똑같이** 유지한다. 위치도 원문을 따른다.
  `\\f` 는 새 창이 아니라 「여기서 입력을 기다리고, 뒤가 한 줄씩 스크롤해 이어진다」는 뜻이다.
[창] 대사창은 17 전각 × 3 줄이다. 엔진이 17 칸에서 자동으로 접는다.
  한 `\\f` 구간이 3 줄을 넘지 않게 한다(원문이 이미 넘는 자리는 원문만큼은 괜찮다).
[문자] 게임이 쓰는 글자만 쓴다 — `・・・`(가운뎃점 3개, `…` 금지) · `〜`(`~` 금지).
[조각] 앞이 잘린 듯한 항목은 **앞에 숫자·아이템 이름이 런타임에 붙는 조각**이다.
  (예: `でいいよ。` → 「(금액)이면 되겠어」) 이런 자리는 **조사를 타지 않게** 쓴다.
  「을/를」·「이/가」·「은/는」이 앞말 받침에 따라 갈리는 표현을 피하고, 쉼표로 끊거나
  받침과 무관한 표현을 쓴다. (좋은 예: `を手に入れた。` → 「, 손에 넣었다.」)
[말투] 화자에 맞춘다. 쥬리오(소년, 반말) · 크리스(소녀, 반말) · 어른/촌장/현자(하게체·하십시오체) ·
  병사(거친 반말). 존댓말과 반말을 한 항목 안에서 섞지 않는다.
[표기] 아래 고유명사 표는 **그대로** 쓴다.

출력은 **JSON 배열 하나만**. 설명·머리말·코드펜스를 붙이지 마라.
입력의 각 항목마다 `{"id": "<입력의 id 그대로>", "kr": "<번역문>"}` 을 하나씩 낸다.
입력에 있는 id 를 하나도 빠뜨리지 마라."""


def build_prompt(payload, gloss, retry_note=""):
    items = [{"id": k, "jp": v["jp"], "budget": v["budget"]} for k, v in payload.items()]
    return (
        RULES
        + "\n\n[고유명사]\n"
        + json.dumps(gloss, ensure_ascii=False)
        + (f"\n\n[다시]\n{retry_note}" if retry_note else "")
        + "\n\n[입력] `budget` 이 그 항목의 바이트 예산이다.\n"
        + json.dumps(items, ensure_ascii=False)
    )


def _rest(prompt):
    """REST 직접 호출 — 구조화 출력을 쓰고 429 를 우리가 물러선다."""
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
                "temperature": 0.3,
            },
        }
    ).encode()
    url = API_URL.format(m=MODEL or "gemini-2.5-flash")
    wait = 8
    for _ in range(MAX_429):
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "x-goog-api-key": API_KEY},
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read())
            return d["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise RuntimeError(
                    f"HTTP {e.code}: {e.read()[:300].decode(errors='replace')}"
                ) from None
            print(f"    · 한도(429) — {wait}초 물러선다")
            time.sleep(wait)
            wait *= 2
    raise RuntimeError("429 가 이어진다 — 한도가 풀린 뒤에 다시 돌린다")


def _cli(prompt):
    """gemini-cli 폴백 — 키가 없을 때. ⚠ 구조화 출력이 없어 파싱이 깨질 수 있다.

    ⚠ **CLI 는 429 를 제 방식대로 재시도하다 죽는다.** 무료 등급은 분당 한도가 낮아서
    (실측: `limit: 20`) 배치를 몇 번만 던져도 걸린다. 그래서 응답에 적힌 대기 시간을
    읽어 **우리가 물러선다** — 이게 API 를 직접 부르는 편이 나은 이유이기도 하다.
    """
    cmd = [GEMINI, "-p", prompt] + (["-m", MODEL] if MODEL else [])
    wait = 30.0
    for _ in range(MAX_429):
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, check=False)
        both = (r.stdout or "") + (r.stderr or "")
        if r.returncode == 0 and "[" in r.stdout:
            return r.stdout
        if "429" in both or "uota" in both:  # Quota / quota
            m = re.search(r"retry in ([\d.]+)s", both)
            w = min(120.0, float(m.group(1)) + 5) if m else wait
            print(f"    · 한도(429) — {w:.0f}초 물러선다")
            time.sleep(w)
            wait = min(120.0, wait * 1.5)
            continue
        raise RuntimeError(f"응답이 없다: {both.strip()[-300:]}")
    raise RuntimeError("429 가 이어진다 — 한도가 풀린 뒤에 다시 돌린다")


def ask(payload, gloss, retry_note=""):
    """한 배치를 던지고 `{키: 번역}` 을 받는다."""
    txt = (_rest if API_KEY else _cli)(build_prompt(payload, gloss, retry_note))
    i, j = txt.find("["), txt.rfind("]")
    if i < 0 or j < 0:
        raise RuntimeError(f"JSON 배열이 아니다: {txt[:300]}")
    return {x["id"]: x["kr"] for x in json.loads(txt[i : j + 1]) if x.get("id")}


def verify(kr, item):
    """`(사유, 넘긴 바이트)` — 통과면 `(None, 0)`."""
    jp, budget = item["jp"], item["budget"]
    got = budget_bytes(kr)
    if got > budget:
        return f"{got - budget}바이트 넘는다(예산 {budget}, 문안 {got})", got - budget
    if kr.count("\n") != jp.count("\n") or kr.count("\f") != jp.count("\f"):
        return (
            f"구조가 다르다 — 원문 줄바꿈 {jp.count(chr(10))}·대기점 {jp.count(chr(12))}, "
            f"문안 {kr.count(chr(10))}·{kr.count(chr(12))}"
        ), 0
    allow = dict(T.overflows(jp))
    over = [(i, n) for i, n in T.overflows(kr) if n > max(T.WIN_ROWS, allow.get(i, 0))]
    if over:
        return f"창을 넘는다(17×3) — 페이지 {over}", 0
    return None, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    # 🔴 **호출 수가 곧 한도다.** 무료 등급은 하루 한도가 낮아서(실측 2026-08-25:
    #   `limit: 20`, 「exhausted your daily quota」) 블록을 잘게 나눠 던지면 맵 하나도
    #   못 끝낸다. 배치를 크게 잡아 **맵 하나를 한두 번에** 끝내는 쪽이 맞다.
    ap.add_argument("--batch", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0, help="이만큼만(시험용)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    todo_p = os.path.join(C.REVIEW_DIR, f"todo_{a.stem}.json")
    if not os.path.exists(todo_p):
        raise SystemExit(f"검토표가 없다 — 먼저: progress.py --todo {a.stem}")
    with open(todo_p, encoding="utf-8") as f:
        todo = json.load(f)
    out_p = os.path.join(C.REVIEW_DIR, f"mt_{a.stem}.json")

    if a.apply:
        with open(out_p, encoding="utf-8") as f:
            got = json.load(f)
        sp = os.path.join(R.SCRIPT_DIR, f"{a.stem}.json")
        d = {}
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as f:
                d = json.load(f)
        mt = set(d.get("_mt", []))
        n = 0
        for k, v in got.items():
            if k in d or k not in todo:
                continue
            if verify(v, todo[k])[0]:
                continue
            d[k], n = v, n + 1
            mt.add(k)
        out = {k: d[k] for k in sorted((x for x in d if not x.startswith("_")), key=int)}
        out["_jp"] = d.get("_jp", {})
        out["_mt"] = sorted(mt, key=int)
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(f"{a.stem} — 초벌 {n} 반영 (사람이 안 본 자리는 `_mt` 에 남는다)")
        return

    keys = sorted(todo, key=int)[: a.limit or None]
    gloss = glossary_for("".join(todo[k]["jp"] for k in keys))
    how = (
        f"REST · {MODEL or 'gemini-2.5-flash'} · 구조화 출력"
        if API_KEY
        else f"gemini-cli · {MODEL or '기본 모델'} (키가 없다)"
    )
    print(f"{a.stem} — 블록 {len(keys)} · 고유명사 {len(gloss)} · 배치 {a.batch} · {how}")

    done, failed = {}, {}
    for s in range(0, len(keys), a.batch):
        chunk = keys[s : s + a.batch]
        payload = dict.fromkeys(chunk)
        note = ""
        for rnd in range(MAX_ROUNDS):
            try:
                got = ask({k: todo[k] for k in payload}, gloss, note)
            except Exception as e:  # noqa: BLE001 — 한 배치가 죽어도 나머지는 돈다
                print(f"  ❌ 배치 {s // a.batch + 1} 회차 {rnd + 1}: {e}")
                break
            bad = {}
            for k in list(payload):
                v = got.get(k)
                if not isinstance(v, str) or not v:
                    bad[k] = "응답에 없다"
                    continue
                why, _ = verify(v, todo[k])
                if why:
                    bad[k] = why
                else:
                    done[k] = v
            if not bad:
                break
            payload = dict.fromkeys(bad)
            note = "아래 항목이 규칙을 어겼다. **더 짧게** 다시 써라:\n" + "\n".join(
                f"  {k}: {w}" for k, w in bad.items()
            )
            print(
                f"  배치 {s // a.batch + 1} 회차 {rnd + 1} — 통과 {len(chunk) - len(bad)}/{len(chunk)}"
            )
        else:
            failed.update(dict.fromkeys(payload, "회차를 다 썼다"))
        print(f"  배치 {s // a.batch + 1}/{-(-len(keys) // a.batch)} — 누적 통과 {len(done)}")

    os.makedirs(C.REVIEW_DIR, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False, indent=1)
    rate = len(done) / len(keys) * 100 if keys else 0
    print(f"\n통과 {len(done)}/{len(keys)} ({rate:.1f}%) · 못 맞춘 것 {len(failed)} → {out_p}")
    print(f"반영하려면: mt_draft.py {a.stem} --apply")


if __name__ == "__main__":
    main()
