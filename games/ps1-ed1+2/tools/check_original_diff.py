#!/usr/bin/env python3
"""원본↔빌드 바이트 diff — 우리가 건드린 자리마다 경계·혼재·종단을 본다.

마스터 지시(2026-09-13, 047 이후). 기존 게이트 셋(건너뜀 기준선·`check_scn_jp_left`·
되읽기)은 전부 **우리 표(정본)가 분모**라 표에 없거나 스캐너가 못 찾은 자리는 원리적으로
못 본다 — 레밍플러스A·`自分自身` 둘 다 그래서 숨었다. 이 검사는 반대다: **원본과 빌드를
바이트로 직접 비교**해 우리가 건드린 자리만 골라 검산한다. 분모가 "이미지 전체"가 아니라
"원본과 달라진 곳"이라 스탯 이진 자료 잡음이 안 낀다.

세 물음(마스터 원문):
  ① 경계 — 바뀐 구간이 원문 문자열의 시작에서 시작하고 종단 앞에서 끝나나
  ② 혼재 — 구간 안팎에 한글과 원문 바이트가 섞여 있나
  ③ 종단 — `0x00` 이 제대로 있나, 길이가 원문 구간을 안 넘나

그리고 **안 바뀐 구간 중 원본이 문자열인 것 = 미번역**(baseline, 0 을 요구하지 않는다 —
표기 유지·자료용으로 의도된 미번역이 있다).

⚠ **원본은 `originals/`(= `common.extract()` 기본값)에서 읽는다** — 제자리 갱신된
이미지를 다시 읽으면 비멱등이 된다(루트 CLAUDE.md 빌드 규율).

  python3 tools/check_original_diff.py ED2MON      # ED2MON0~5.BIN
  python3 tools/check_original_diff.py ED2EXE      # ED2.EXE (CORPUS 구간만)
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, ROOT, extract
from ed2_monster_review import MON

IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"
BASELINE = {
    "ED2MON": os.path.join(ROOT, "script", "ed2_origdiff_baseline.json"),
    "ED2EXE": os.path.join(ROOT, "script", "ed2exe_origdiff_baseline.json"),
}

MIN_STR_LEN = 3  # 이보다 짧은 span 은 자료(筧 류) 오탐이 많다 — 다른 게이트와 같은 문턱

# ── 한글 슬롯 SJIS 역표 ──────────────────────────────────────────────────
_KR_DECODE = {H.syllable_sjis(ch).to_bytes(2, "big"): ch for ch in H.SYLLABLES}


def _kr_pair(buf, i):
    """buf[i:i+2] 가 우리 한글 슬롯 인코딩이면 그 글자, 아니면 None."""
    return _KR_DECODE.get(bytes(buf[i : i + 2]))


# 원문 그대로 살리는 부호 — `patch_ed2_monsters.py` 의 `′`·`”`(분열체 구분) 등.
# ⚠ **결함이 아니다** — 번역명 뒤에 이 부호가 그대로 남는 게 정본 설계다. 여기서
# 걸러 두지 않으면 이 벤치의 흔한 정상 패턴이 죄다 "혼재"로 오탐된다(실측 다수).
_PRESERVED_JP_PUNCT = {"′", "”", "’", "″", "…", "‥", "、", "。", "！", "？", "・"}


def _decode_pair(buf, i):
    """buf[i:i+2] 가 디코드되는 SJIS 2바이트 문자면 그 글자(부호 포함), 아니면 None."""
    b0 = buf[i]
    if not (0x81 <= b0 <= 0x9F or 0xE0 <= b0 <= 0xFC):
        return None
    try:
        ch = buf[i : i + 2].decode("cp932")
    except UnicodeDecodeError:
        return None
    return ch if len(ch) == 1 else None


def _jp_pair(buf, i):
    """buf[i:i+2] 가 유효한(가나·한자) SJIS 2바이트면 그 글자, 아니면 None."""
    ch = _decode_pair(buf, i)
    if ch and ("぀" <= ch <= "ヿ" or "一" <= ch <= "鿿"):
        return ch
    return None


def _jp_leftover(buf, i):
    """`_jp_pair` 중 **혼재 판정 대상**만 — 원문 그대로 살리는 부호는 뺀다."""
    ch = _jp_pair(buf, i)
    if ch and ch in _PRESERVED_JP_PUNCT:
        return None
    return ch


def _is_ascii_ok(b):
    """원문·우리 문안 둘 다 그대로 쓰는 반각(공백·숫자·영문·부호) + **런타임 제어 바이트**.

    ⚠ `%c`·`%s` 는 파일 안에서 **리터럴 ASCII 두 글자**(빌드 시점 치환용, `0x25 0x63`)로
    나오는 자리와, **런타임 색·서식 코드**(단일 바이트 `0x01~0x1F`, `0x0A` 개행 포함)로
    나오는 자리가 **둘 다 있다**(실측 — `%c%s%c` 뒤에 이 단일바이트가 바로 붙는 대사가
    많다). 둘 다 원문·우리 문안이 **그대로 보존**하는 자리라 span 판정에서 문자열을
    안 끊는다.
    """
    return b == 0x0A or 0x01 <= b <= 0x1F or 0x20 <= b < 0x7F


def sjis_spans(buf, min_len=MIN_STR_LEN):
    """**널 경계가 아니라 SJIS 디코드 가능 여부**로 문자열 후보 span 을 찾는다.

    🔴 널 경계로만 정하면 047(레밍플러스A)을 놓친 그 사각과 같아진다 — 노이즈 바이트
    (0xFF 등)가 앞에 끼면 스캐너가 경계를 못 잡는다. 여기는 반대로 **디코드가 이어지는
    한** 널을 넘어가며 하나의 span 으로 묶는다(원본은 전부 일본어라 이 판정이 쉽다 —
    우리 빌드처럼 한글 슬롯 SJIS 가 섞여 있지 않다).
    """
    spans = []
    n = len(buf)
    i = 0
    start = None
    while i < n:
        b = buf[i]
        if _is_ascii_ok(b):
            if start is None:
                start = i
            i += 1
            continue
        ch = _decode_pair(buf, i) if i + 1 < n else None
        if ch:
            if start is None:
                start = i
            i += 2
            continue
        if start is not None and i - start >= min_len:
            spans.append((start, i))
        start = None
        i += 1
    if start is not None and n - start >= min_len:
        spans.append((start, n))
    return spans


def diff_runs(orig, build):
    """orig/build(같은 길이) → [(start, end)] 바이트가 다른 최대 구간."""
    runs = []
    n = min(len(orig), len(build))
    i = 0
    while i < n:
        if orig[i] != build[i]:
            j = i
            while j < n and orig[j] != build[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    return runs


def _span_index(spans):
    """[(s,e)] 리스트에서 임의의 오프셋을 담는 span 을 이분탐색으로 찾는 헬퍼."""
    import bisect

    starts = [s for s, _e in spans]

    def find(off):
        i = bisect.bisect_right(starts, off) - 1
        if 0 <= i < len(spans) and spans[i][0] <= off < spans[i][1]:
            return spans[i]
        return None

    return find


def _extend_span(buf, s, e, n, spans_lookup=None):
    """(s,e) 를 포함하는 원문 span 경계로 넓힌다.

    🔴 **뒤로 그리디 확장하면 안 된다**(2026-09-13 실측 — 고드윈2세 오탐). SJIS 뒷바이트가
    출력 가능 ASCII 범위(`c` 등)와 겹쳐서, 거꾸로 훑으면 2바이트 문자 한복판을 "글자
    하나"로 오인하고 정렬이 깨진다. **`sjis_spans()`(정방향 훑기, 안전)의 결과를 찾아
    쓰는 게 정답**이다 — 없으면(스캔 밖 등) 최후 수단으로만 그리디 확장을 쓴다.
    """
    if spans_lookup:
        hit = spans_lookup(s) or (spans_lookup(s - 1) if s > 0 else None)
        if hit and hit[0] <= s and e <= hit[1]:
            return hit
    lo = s
    while lo > 0:
        if _is_ascii_ok(buf[lo - 1]):
            lo -= 1
            continue
        if lo >= 2 and _decode_pair(buf, lo - 2):
            lo -= 2
            continue
        break
    hi = e
    while hi < n:
        if _is_ascii_ok(buf[hi]):
            hi += 1
            continue
        if hi + 1 < n and _decode_pair(buf, hi):
            hi += 2
            continue
        break
    return lo, hi


def classify_run(orig, build, s, e, spans_lookup=None):
    """바뀐 구간 (s,e) 를 원문 경계로 넓혀 ①경계 ②혼재 ③종단을 본다.

    반환: None(정상) 또는 (사유, 상세) — 사유는 "혼재"·"종단"·"경계" 중 하나.
    """
    n = len(orig)
    lo, hi = _extend_span(orig, s, e, n, spans_lookup)
    # ① 경계 — 바뀐 구간 앞뒤(lo~s, e~hi)는 원문 그대로 남아 있어야 정상(부분 치환).
    #   그 구간이 build 에서도 원문과 같은지 — 다르면 그 자체가 별도 run 으로 이미 잡히니
    #   여기서는 "구간이 원문 span 경계를 벗어나 시작/끝나는가"만 본다.
    if lo == s and hi == e:
        pass  # 바뀐 구간이 곧 전체 span — 흔한 경우, 아래서 내용만 본다
    # 빌드 쪽 내용을 처음부터 훑어 혼재·종단을 본다.
    i = lo
    saw_kr = False
    saw_jp_leftover = False
    first_null = None
    while i < len(build):
        b = build[i]
        if b == 0:
            first_null = i
            break
        if i + 1 < len(build):
            kr = _kr_pair(build, i)
            if kr:
                saw_kr = True
                i += 2
                continue
        if _is_ascii_ok(b):
            i += 1
            continue
        preserved = _decode_pair(build, i) if i + 1 < len(build) else None
        if preserved and preserved in _PRESERVED_JP_PUNCT:
            i += 2
            continue
        jp = _jp_leftover(build, i) if i + 1 < len(build) else None
        if jp:
            saw_jp_leftover = True
            i += 2
            continue
        # 완성형도 SJIS 도 아닌 바이트 — 깨진 자리(홀로 남은 뒷바이트 등)
        return ("혼재", f"{i:#x} 완성형·SJIS 어느 쪽도 아닌 바이트 {b:#04x}")
    if saw_kr and saw_jp_leftover:
        return ("혼재", f"[{lo:#x},{i:#x}) 한글과 원문 바이트가 한 구간에 섞였다")
    if first_null is None:
        return ("종단", f"[{lo:#x},…) 이 원문 구간 끝({hi:#x})까지 종단이 없다")
    if first_null > hi + 4:  # 슬롯 확장 여지를 조금 둔다
        return ("종단", f"종단이 원문 구간({hi:#x})보다 한참 뒤({first_null:#x})다 — 겹쳐 썼을 수 있다")
    return None


def _known_name_spans(label):
    """`patch_ed2_monsters.plan()` 이 이미 잡음 접두를 걷어낸 자리 — [(s,e)].

    🔴 **재사용이다, 새로 안 만든다**(마스터 지적 2026-09-13) — 이름 앞에 낀 잡음
    (`0xFF` 등)이 span 경계 계산을 흔드는 문제를 `_drop_noise_prefix` 가 이미 푼다.
    거기서 나온 (오프셋, 슬롯)을 그대로 신뢰 가능한 경계로 쓴다 — 직접 재구현하면
    같은 판단을 두 곳에 두게 된다(DRY).
    """
    if label == "ED2EXE":
        import patch_ed2_battle as PB
        import patch_ed2_sys as PS

        spans = []
        srows, sover = PS.plan()
        spans += [(off, off + slot) for off, _jp, _kr, slot, _enc in srows + sover]
        bfit, bover, _bnone = PB.plan()
        spans += [(off, off + slot) for off, _jp, _kr, slot in bfit + bover]
        return spans
    if not label.startswith("ED2MON"):
        return []
    g = int(label[len("ED2MON") :])
    import patch_ed2_monster_lines as PL
    import patch_ed2_monsters as PM

    lba = MON[g][0]
    fit, over, _none = PM.plan()
    spans = [(off, off + slot) for lba2, off, _jp, _kr, slot in fit + over if lba2 == lba]
    # ⚠ **052 재배치가 고쳐 쓴 명령어(lui/addiu) 자리도 known 이다** — 텍스트가 아니라서
    # 위 이름-슬롯 span 엔 안 잡히는데, 그리디 확장이 근처 스탯 바이트를 SJIS 히라가나로
    # 오디코드해 "혼재"로 오탐한다(2026-09-13, 마스터 QA 052 빌드 실패 실측). 타이트한
    # 명령어 워드 span 을 등록해 그리디 확장 대신 이걸 쓰게 한다.
    spans += PM.relocation_ref_spans(lba)
    # `auto_lines()`(`Xが現れた。` 류) 도 같은 잡음-접두 문제를 겪는다 — 이름 스캐너와
    # 다른 도구지만 원리는 같다(정본이 있는 자리는 그 도구의 계획을 신뢰한다).
    lfit, lmove, _lover, _lnone = PL.plan()
    spans += [(off, off + slot) for lba2, off, _jp, _kr, slot in lfit if lba2 == lba]
    spans += [(off, off + slot) for lba2, off, _jp, _kr, slot in lmove if lba2 == lba]
    # `script/ED2MON_LINES.json`(sha1 표, 동결 중)도 같은 잡음-접두 문제를 겪는다 —
    # 이 표는 `plan()` 이 없어(직접 쓰기만 한다) `check_ed2mon_readback.check_lines()` 와
    # 같은 수법(기대 바이트가 널 경계로 실재하는 자리 찾기)을 그대로 재사용한다.
    import check_ed2mon_readback as RB

    with open(RB.LINES_TABLE, encoding="utf-8") as f:
        table = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    # ⚠ **빌드 이미지는 live LBA 로 읽는다**(원본은 정적 `MON` 이 맞다 — 재배치는 빌드에서만
    # 일어난다). 2026-09-22 실측: 대사 5건을 되살리자 ED2MON3·4 가 DUMMY 로 옮겨갔는데
    # 여기가 정적 LBA 로 읽어 **옛 자리의 원문**을 보고 "미번역 127건"을 새로 만들었다.
    cur_lba, cur_size = PL._live_group_lba()[g]
    cap = (cur_size + 2047) // 2048 * 2048
    build_buf = bytes(extract(cur_lba, cap, path=IMG))
    for kr in table.values():
        want = RB._enc_lines(kr) + b"\x00"
        idx = build_buf.find(want)
        while idx >= 0:
            if idx == 0 or build_buf[idx - 1] == 0:
                spans.append((idx, idx + len(want) - 1))
                break
            idx = build_buf.find(want, idx + 1)
    return spans


def _load_original(name):
    if name == "ED2MON":
        from patch_ed2_monster_lines import _live_group_lba

        # ⚠ **원본은 정적 `MON`, 빌드는 live LBA** — 재배치는 빌드 이미지에서만 일어난다
        # (`_check_known_spans` 의 같은 주석 참조). 둘을 같은 좌표로 읽으면 재배치된
        # 그룹에서 옛 자리의 원문을 빌드 내용으로 착각한다.
        live = _live_group_lba()
        out = {}
        for g, (lba, size) in sorted(MON.items()):
            cur_lba, _cur_size = live[g]
            out[f"ED2MON{g}"] = (extract(lba, size), extract(cur_lba, size, path=IMG))
        return out
    if name == "ED2EXE":
        import patch_ed2_sys as P

        orig = extract(P.ED2_LBA, P.ED2_SIZE)
        build = extract(P.ED2_LBA, P.ED2_SIZE, path=IMG)
        return {"ED2EXE": (orig, build)}
    raise SystemExit(f"모르는 대상: {name}")


def _span_has_real_jp(orig, lo, hi):
    """확장된 span 안에 **진짜 가나 낱말**(연속 2자 이상)이 있나 — 없으면 이진 자료다.

    ⚠ `_is_ascii_ok` 가 런타임 제어 바이트(0x01~0x1F)까지 span 에 넣어 주는데,
    **스탯 표의 순수 숫자·인덱스 바이트**도 그 범위에 우연히 걸려 "문자열"로
    오판된다(실측: 그룹1 스탯 재조정 바이트가 대량으로 결함 오탐을 냈다). 이 게임
    전역에서 이미 쓰는 `is_dialog()` 규칙과 같은 문턱이다 — **가나 없으면 자료다.**

    🔴 **가나 한 글자만으로는 부족하다**(2026-09-13, 마스터 QA 052 — 재배치가 고쳐 쓴
    명령어 워드 옆 스탯 바이트가 우연히 `82 a0`(あ) 하나로 디코드돼 "혼재"로 오탐했다.
    patch-site 를 known span 으로 등록해 그 한 자리는 가렸지만, 뿌리는 **그리디가 우연한
    가나 1자로도 "진짜 텍스트"라고 믿는 것**이다 — 다음 재배치가 또 다른 자리에서 같은
    자리를 밟는다). **연속 2자(4바이트)** 를 요구한다 — 순수 이진값이 가나 낱말 모양으로
    두 번 연달아 우연히 맞을 확률은 사실상 0이다.
    """
    prev = None
    for i in range(lo, hi - 1):
        ch = _jp_pair(orig, i)
        if ch and "぀" <= ch <= "ヴ":  # 히라가나~가타카나(장음 포함)만 — 한자 단독은 자료도 흔하다
            if prev is not None and i == prev + 2:
                return True
            prev = i
    return False


def scan(name):
    """(defects, untranslated) — defects=[(파일, run, 사유, 상세)], untranslated=[(파일, span, JP)]."""
    defects, untranslated = [], []
    for label, (orig, build) in _load_original(name).items():
        orig, build = bytes(orig), bytes(build)
        orig_spans = sjis_spans(orig)
        sjis_lookup = _span_index(orig_spans)
        known = _known_name_spans(label)

        def known_lookup(off, s=None, e=None, _known=known):
            """선형 탐색 — `known` 은 세 출처를 그냥 이어 붙인 것이라 겹칠 수 있다.

            ⚠ **이분탐색(`_span_index`)을 안 쓴다** — 정렬-비중첩 전제가 깨지면 엉뚱한
            span 을 골라 오탐이 오히려 는다(실측: 2건 새로 생김). `known` 은 항목이
            적어(그룹당 수십) 선형 탐색 비용이 무시할 만하다. 대상 run(s,e) 을 **완전히
            포함하는** span 만 인정한다.
            """
            for lo, hi in _known:
                if lo <= off < hi and (s is None or (lo <= s and e <= hi)):
                    return (lo, hi)
            return None

        def lookup(off, _sl=sjis_lookup, s=None, e=None):
            return known_lookup(off, s, e) or _sl(off)
        runs = diff_runs(orig, build)
        touched = set()
        for s, e in runs:
            lo, hi = _extend_span(orig, s, e, len(orig), lookup)
            touched.add((lo, hi))
            if not _span_has_real_jp(orig, lo, hi):
                continue  # 가나 없는 자리 — 스탯·인덱스 자료일 가능성이 크다
            r = classify_run(orig, build, s, e, lookup)
            if r:
                why, detail = r
                defects.append((label, (s, e), why, detail))
        changed_spans = touched
        for s, e in orig_spans:
            if any(not (e <= lo or s >= hi) for lo, hi in changed_spans):
                continue  # 우리가 손댄 span — 위에서 이미 봤다
            if build[s:e] == orig[s:e]:
                try:
                    jp = orig[s:e].decode("cp932")
                except UnicodeDecodeError:
                    continue
                if any("぀" <= c <= "ヿ" or "一" <= c <= "鿿" for c in jp):
                    untranslated.append((label, (s, e), jp))
    return defects, untranslated


def check_baseline(name, *, strict=False):
    defects, untranslated = scan(name)
    ids = sorted(f"defect:{label}:{s:#x}" for label, (s, _e), _w, _d in defects) + sorted(
        f"untranslated:{label}:{s:#x}" for label, (s, _e), _jp in untranslated
    )
    print(
        f"  원본↔빌드 diff({name}): 결함 {len(defects)}건(경계·혼재·종단) · "
        f"미번역 {len(untranslated)}건"
    )
    for label, (s, e), why, detail in defects:
        print(f"    ❌ {label} [{s:#x},{e:#x}) {why} — {detail}")
    baseline = BASELINE[name]
    if not os.path.exists(baseline):
        print(f"    (기준선 없음 — {os.path.relpath(baseline, ROOT)} 를 만들면 회귀를 잡는다)")
        return defects, untranslated
    with open(baseline, encoding="utf-8") as f:
        base = json.load(f)
    base_ids = set(base.get("_ids", []))
    new = sorted(set(ids) - base_ids)
    gone = sorted(base_ids - set(ids))
    print(f"    기준선 {len(base_ids)}건 대비 — 새로 생김 {len(new)} · 해소됨 {len(gone)}")
    if gone:
        print(f"    ℹ 해소된 자리(기준선을 손으로 갱신할 것): {', '.join(gone)}")
    if new and strict:
        raise SystemExit(
            f"원본↔빌드 diff({name}): 새 자리가 생겼다\n"
            + "\n".join(f"  {i}" for i in new)
            + f"\n기준선: {os.path.relpath(baseline, ROOT)} (의도된 변화면 이 파일을 갱신한다)"
        )
    return defects, untranslated


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    for name in args or ["ED2MON", "ED2EXE"]:
        check_baseline(name, strict=strict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
