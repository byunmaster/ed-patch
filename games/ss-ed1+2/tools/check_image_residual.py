#!/usr/bin/env python3
"""**이미지 전체 잔존 게이트** — 원문 일본어 글이 최종 이미지에 **분모 밖에서** 남았나.

    python3 tools/check_image_residual.py            # 검사 (늘면 실패)
    python3 tools/check_image_residual.py --freeze   # 기준선을 현재 값으로 (줄었을 때만)
    python3 tools/check_image_residual.py --list     # 파일별 개수

## 왜 있나 (2026-10-18)
반각 가타카나 몬스터 이름 5칸(`ﾄﾞﾗｽﾄｺﾞｰｽﾄＡ` 등)이 **조용히 번역에서 빠져** 화면에 나갔다. 「남은 일본어」 게이트
(`scan_untranslated`)는 ① 포인터가 가리키는 자리만 문자열로 치고 ② 반각 가나를 내부 키로 뺐기 때문에 둘 다 놓쳤다.
⇒ 포인터·표·덤프를 거치지 않고 **이미지 바이트에서 직접** 일본어 글 덩이를 센다.

## 무엇을 세나
- **전각 덩이** — SJIS 2바이트 글자(가나·한자·일본식 부호) 8자↑ 이어진 것 중 **가나가 4자↑**. 그림·코드가 우연히 SJIS 로
  읽히는 노이즈는 가나 비율이 낮아 걸러진다(가나 리드 `82/83` 는 전체 리드의 3%).
- **반각 가나 덩이** — `ﾄﾞﾗｽ…` 처럼 반각 가나 4자↑(앞이 NUL·제어 문자). 전각으로 정규화한 뒤 센다.
## 기준선 = 래칫 (`image_residual_baseline.json`)
파일마다 지금 개수를 적는다 — **원문이 아직 남은 곳(미번역 씬·도달 불가 자료)도 그대로 들어간다.** 개수가 **늘면** 실패,
줄면 `--freeze`. 새 파일에 덩이가 생겨도 실패. 문안(JP)은 담지 않는다(개수만).
⚠ 기준선을 올려서 통과시키는 건 게이트 우회다 — 늘어난 이유를 먼저 본다(`--list`).
"""

import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import common

BASELINE = os.path.join(common.GAME_DIR, "image_residual_baseline.json")
LEAD = rb"[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]"
# 🔴 **문장 길이까지 센다**(2026-10-18, md-ed1·sfc-ed2 발견) — 런 최소 길이가 12자면 짧은 문장(「…が現れた。」 11자)이 샌다.
#    실측: 8자/가나 4 → 3,144덩이 · 5자/가나 2 → 6,279덩이(노이즈 폭증은 ED1INIT·씬 파일의 그림·표 — 래칫이라 늘기만 보므로 무방).
MIN_RUN, MIN_KANA = 5, 2
FULL = re.compile(b"(?:" + LEAD + b"){%d,}" % MIN_RUN)
HALF = re.compile(rb"(?<![\x80-\xff])[\xa6-\xdf]{4,}")
KANA = re.compile(r"[ぁ-ゟ゠-ヿ]")
PARAMS = {"min_run": MIN_RUN, "min_kana": MIN_KANA}
TEXT_EXT = (".BIN",)  # 그림·자료(.DAT/.DG2/.CEL …)는 SJIS 로 우연히 읽히는 노이즈뿐이라 안 본다


def count_runs(data):
    """`(전각 덩이 수, 반각 가나 덩이 수)` — 바이트열 하나."""
    full = 0
    for m in FULL.finditer(data):
        try:
            t = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if len(KANA.findall(t)) >= MIN_KANA:
            full += 1
    half = 0
    for m in HALF.finditer(data):
        before = data[m.start() - 1 : m.start()] if m.start() else b"\x00"
        after = data[m.end() : m.end() + 1]
        if before and before[0] >= 0x20:  # NUL·제어 문자 뒤에서 시작해야 글이다
            continue
        if after and after[0] >= 0x20 and not 0x81 <= after[0] <= 0x9F:  # 끝도 NUL·제어·전각 글자여야 한다
            continue
        try:
            t = unicodedata.normalize("NFKC", m.group().decode("cp932"))
        except UnicodeDecodeError:
            continue
        if len(KANA.findall(t)) >= 3:
            half += 1
    return full, half


def scan(dst):
    f, mm = common.open_image(dst)
    out = {}
    try:
        for name, lba, size in common.iso_files(mm):
            if not name.endswith(TEXT_EXT) or size > 3_000_000:
                continue
            full, half = count_runs(common.read_extent(mm, lba, size))
            if full or half:
                out[name] = [full, half]
    finally:
        mm.close()
        f.close()
    return out


def main():
    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    now = scan(dst)
    if "--list" in sys.argv:
        for n, (a, b) in sorted(now.items(), key=lambda kv: -sum(kv[1])):
            print(f"  {n}: 전각 {a} · 반각 {b}")
    if "--freeze" in sys.argv:
        old = json.load(open(BASELINE)) if os.path.exists(BASELINE) else {}
        same_params = old.get("_params") == PARAMS
        reasons = old.get("_reasons", [])
        old = {k: v for k, v in old.items() if not k.startswith("_")}
        grew = {n: (old.get(n), v) for n, v in now.items() if same_params and n in old and any(x > y for x, y in zip(v, old[n]))}
        # 🔴 기준선을 **올리는** 건 항목별 사유를 파일에 남길 때만이다(`--reason "…"`) — 환경변수 한 줄로 통과시키는 문은 두지 않는다(게이트 우회 금지).
        #    사유는 「옮긴 블록의 옛 칸 · 포인터 0 · check_ptr_targets 가 살아 있는 쪽을 봄」 꼴로, 기준선 diff 에 그대로 남는다.
        reason = sys.argv[sys.argv.index("--reason") + 1] if "--reason" in sys.argv else None
        assert not grew or reason, f"늘어난 파일이 있다 — 사유 없이는 기준선을 올리지 않는다(`--reason`): {grew}"
        for n, (o, v) in grew.items():
            reasons.append({"file": n, "from": o, "to": v, "reason": reason})
        json.dump({"_params": PARAMS, "_reasons": reasons, **now}, open(BASELINE, "w"), ensure_ascii=False, indent=0, sort_keys=True)
        print(f"  기준선 기록 — 파일 {len(now)} · 전각 {sum(v[0] for v in now.values())} · 반각 {sum(v[1] for v in now.values())}")
        return
    base = json.load(open(BASELINE)) if os.path.exists(BASELINE) else None
    if base is None:
        raise SystemExit("🔴 image_residual_baseline.json 이 없다 — `--freeze` 로 먼저 만든다")
    base.pop("_reasons", None)
    if base.pop("_params", None) != PARAMS:
        raise SystemExit("🔴 기준선이 다른 문턱값으로 만들어졌다 — 문턱을 바꿨으면 `--freeze` 로 다시 세운다(한 번만, 늘어난 이유를 먼저 본다)")
    bad = []
    for n, v in now.items():
        b = base.get(n, [0, 0])
        if v[0] > b[0] or v[1] > b[1]:
            bad.append(f"  {n}: 전각 {v[0]}(기준 {b[0]}) · 반각 {v[1]}(기준 {b[1]})")
    tf, th = sum(v[0] for v in now.values()), sum(v[1] for v in now.values())
    if bad:
        raise SystemExit("🔴 이미지에 원문 일본어 덩이가 기준선보다 늘었다:\n" + "\n".join(bad))
    shrunk = sum(1 for n, b in base.items() if n not in now or any(x < y for x, y in zip(now[n], b)))
    print(
        f"  ✅ 이미지 잔존 일본어 덩이 — 전각 {tf} · 반각 {th} (기준선 이하"
        + (f" · 줄어든 파일 {shrunk} → `--freeze` 로 내려도 된다)" if shrunk else ")")
    )


if __name__ == "__main__":
    main()
