#!/usr/bin/env python3
"""**씬 대사**에 일본어가 남았는지 센다 — 그리고 왜 남았는지까지 짚는다.

⚠ 전투 코퍼스·이름 테이블·UI 는 `check_jp_left.py` 가 본다. 여기는 **SCN 오버레이 대사**만 —
층이 달라 판정 방식도 다르다(저쪽은 코드 참조로 문자열을 모으고, 여기는 블록 포인터를 본다).

⚠ 이건 `todo_untranslated`(손이 필요한 블록)와 **다른 층**이다. 배정이 붙어도 게이트에서
빠지거나 정형 빌더가 그 꼴을 못 알아보면 JP 가 그대로 나간다. 실제로 「파생값이 전부
한국어인 걸 확인했다」고 적어 둔 자리 여럿이 이미지에선 일본어였다(2026-08-10).
**파생값을 본 것과 이미지에 들어간 것을 본 것은 다르다.**

⚠ 재배치 뒤 자유 구간에는 **원본 꼬리가 그대로 남는다** — 포인터가 안 가리키면 화면에
안 나오는 죽은 바이트다. 그래서 **참조되는 블록만** 본다. 가나만 보고 한자는 넘긴다
(지명·이름 슬롯에 정상으로 남는 한자가 있다).

  python3 tools/check_scn_jp_left.py            # 전 씬 + ED2MON
  python3 tools/check_scn_jp_left.py ED1SCN3    # 한 씬(사유까지)

🔴 **`ED2MON0~5.BIN`(ED2 전투 대사 오버레이) 도 여기서 본다**(2026-09-13 편입). 041①이
퇴보였을 때(qa.txt) 이 파일군에 JP 잔존 116곳이 있었는데 **게이트가 이 파일군을 한 번도
스캔한 적이 없었다** — SCN 축만 보고 있었다. `scan_mon()`이 그 구멍을 메운다.
⚠ **0 을 요구하지 않는다** — 기준선(`ed2mon_jp_left_baseline.json`, 조판 지문과 같은 꼴)과
대조해 **늘면 실패**한다. 지금도 이름 접미 변형(D/E/F 등, 032/037② 스캔이 안 닿은 자리)
6곳이 남아 있다 — 그건 「할 일」이지 새로 만든 「실패」가 아니라서 기준선에 넣었다.
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import reinsert_kr_pilot as R
from common import BUILD_DIR, OUT_DIR, extract
from ed2_monster_review import MON, decode_sjis
from lock_lines import SETTLED, load_lock
from patch_ed2_monster_lines import is_dialog, overlay_refs
from patch_ed2_monsters import CANON, _enc
from patch_sys_ui import _scn_layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
MON_BASELINE = os.path.join(ROOT, "script", "ed2mon_jp_left_baseline.json")
MON_NAME_LIVE_JP_BASELINE = os.path.join(ROOT, "script", "ed2mon_name_live_jp_baseline.json")

# 전각 가타카나 → 반각(JIS X 0201, `0xA1~0xDF`) 대응표(2026-09-14, 마스터 QA 051 —
# 「이슈타~이즈」 HUD 가 **반각**으로 따로 있었는데 전각 SJIS 검색만 해서 못 봤다).
# 탁점(゛)·반탁점(゜)이 붙은 글자는 **반각 두 글자**(바탕+탁점)로 풀린다.
_HW_BASE = "。「」、・ヲァィゥェォャュョッーアイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワン"
_HW_DAKU = "ガギグゲゴザジズゼゾダヂヅデドバビブベボ"
_HW_HAN = "パピプペポ"
_FULL_TO_HALF = {c: chr(0xFF61 + i) for i, c in enumerate(_HW_BASE)}
# 탁점 글자(ガ 등)는 청음행(カ 등)의 반각 + 반각 탁점(ﾞ)으로 유도한다.
_FULL_TO_HALF.update(
    {
        jp: _FULL_TO_HALF[base] + "ﾞ"
        for jp, base in zip(_HW_DAKU, "カキクケコサシスセソタチツテトハヒフヘホ", strict=True)
    }
)
_FULL_TO_HALF.update({jp: _FULL_TO_HALF["ハヒフヘホ"[i]] + "ﾟ" for i, jp in enumerate(_HW_HAN)})
_FULL_TO_HALF["ヴ"] = "ｳﾞ"  # ウ+゛


def _to_halfwidth(jp):
    """전각 문자열을 반각(JIS X 0201) 코드포인트 열로 — 매핑 없는 글자가 있으면 `None`."""
    out = []
    for ch in jp:
        h = _FULL_TO_HALF.get(ch)
        if h is None:
            return None
        out.append(h)
    return "".join(out)


KANA = re.compile(r"[ぁ-ゟァ-ヺ]")


def why_left(scene, eid, raw, tr, ov, am, settled):
    """이 블록이 왜 일본어로 남았나 — 층을 갈라 이름 붙인다."""
    if eid is None:
        return "원문 대조 실패(블록 경계 밖일 수 있다)"
    why = []
    if str(eid) in settled:
        why.append("판정완료")
    if str(eid) in ov:
        why.append("오버라이드")
    if str(eid) in am:
        why.append("배정 정본")
    if eid in tr:
        try:
            _, w = R.build_candidate(raw[eid], tr[eid], eid)
            why.append(f"게이트 제외:{w}" if w else "⚠ 번역이 있는데 JP — 배치 단계 제외 의심")
        except Exception as e:  # noqa: BLE001
            why.append(f"빌드 예외 {type(e).__name__}")
    else:
        why.append("번역 없음")
    return " · ".join(why)


def scan_translated_but_raw(scene):
    """번역이 있는데 빌드 이미지 **제 위치**에 원문 바이트가 그대로인 곳.

    ⚠ **`scan()`(위)과 분모가 다르다.** `scan()`은 "참조되는 블록"·`kind` 분류에 기대는데,
    분류가 틀리면(`kind:"header"` = 이름판 취급) 그 자리는 **영영 안 본다** — ED2SCN8
    엔트리 0(`イシュタやあ こんにちは。`)이 실제 대사인데 "선두 지명 헤더"로 뽑혀
    `reinsert_kr_pilot` 이 안전장치(`mid_block_ref`)로 통째로 건너뛰었고, 표에 번역이
    있는데도 화면엔 원문이 그대로 나갔다(2026-09-13, 마스터 QA 051). 이 게이트는 그걸
    "0곳"으로 찍고 있었다.
    ⇒ **분류·참조·임계값을 전혀 안 본다** — 딱 하나만 잰다: 그 엔트리 자리(`file_offset`)에
    원본 그대로의 바이트가 남아 있는데 우리 번역표엔 값이 있는가. 있거나 없거나라
    문턱값이 필요 없고, "header"든 "gap"이든 "block"이든 분류가 뭐든 상관없이 잡힌다.

    ⚠ **여러 곳에서 같은 문안을 재사용하는 사본 dedup 은 예외다**(정형 블록·표머리
    사본·`chain` 재사용 등 — 종류가 여럿이라 하나하나 나열하면 또 사각이 생긴다).
    죽은 사본은 **제 위치에 원문이 그대로 남는 게 정상**이다(아무도 그 자리를 안
    읽는다) — 그래서 "분류"로 거르지 않고 **최종 이미지에서 그 자리를 여전히 가리키는
    내부 참조가 있는가**로 가른다. 참조가 살아 있으면 실제로 화면에 나가는 것이고
    (051 이 그랬다 — 외부(ED2.EXE 코드)참조는 이 파이프라인이 못 바꾸니 안 옮겨진
    블록은 그 참조가 그대로 남는다), 참조가 없으면 재배치가 이미 다른 곳으로
    돌려놨다는 뜻이라 죽은 바이트다.
    """
    lba, size = next((a, b) for n, a, b in _scn_layout() if n == scene)
    data = bytes(extract(lba, size, path=IMG))
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{scene}.json"), encoding="utf-8"))
    text_end = int(doc["source"]["text_end"], 16)
    tr, _, _ = R.load_translations(scene.replace("SCN", "_SCN"), scene)
    with R.overlay_for(scene):
        base = R.ov_base()
        live_offs = {a - base for _, _, _, a in R.find_refs(data, text_end)}
    hits = []
    for e in doc["entries"]:
        eid = e["entry_id"]
        if eid not in tr or not e.get("raw_hex"):
            continue
        off = int(e["file_offset"], 16)
        if off not in live_offs:
            continue  # 아무도 안 가리키는 자리 — 재배치로 이미 다른 곳에 살아 있다
        raw = bytes.fromhex(e["raw_hex"])
        if data[off : off + len(raw)] == raw:
            hits.append((eid, off, e.get("text", "")))
    return hits


def check_translated_but_raw_all(*, strict=True):
    """전 씬에 `scan_translated_but_raw` 를 돌려 하나라도 있으면 실패시킨다(0 이 목표)."""
    all_hits = []
    for name, _, _ in _scn_layout():
        for eid, off, text in scan_translated_but_raw(name):
            all_hits.append((name, eid, off, text))
    print(f"  번역 있는데 원문 그대로(자리 직접 대조) {len(all_hits)}곳")
    if all_hits:
        lines = [
            f"    {name} jp{eid} @0x{off:X}  {text[:50]!r}" for name, eid, off, text in all_hits
        ]
        msg = "번역표엔 값이 있는데 빌드 이미지 제 위치엔 원문이 그대로다\n" + "\n".join(lines)
        if strict:
            raise SystemExit(msg)
        print("    ⚠ " + msg.replace("\n", "\n    "))
    return len(all_hits)


def scan(scene, verbose):
    lba, size = next((a, b) for n, a, b in _scn_layout() if n == scene)
    data = bytes(extract(lba, size, path=IMG))
    doc = json.load(open(os.path.join(OUT_DIR, "scn_jp", f"{scene}.json"), encoding="utf-8"))
    te = int(doc["source"]["text_end"], 16)
    # ⚠ 베이스는 **게임마다 다르다** — 씬 이름으로 세우고 그 안에서 참조를 뜬다
    # (`R.ov_base()` 는 세워야만 답한다. ED1 값으로 폴백하면 조용히 틀린다).
    with R.overlay_for(scene):
        base = R.ov_base()
        refs = sorted({a - base for _, _, _, a in R.find_refs(data, te)})
    raw = {e["entry_id"]: bytes.fromhex(e["raw_hex"]) for e in doc["entries"] if e.get("raw_hex")}
    tr = ov = am = settled = None
    hits = []
    for off in refs:
        end = data.find(b"\x00", off)
        if end < 0 or end - off > 400:
            end = off + 400
        body = data[off:end]
        if not KANA.search(body.decode("cp932", "ignore")):
            continue
        if tr is None:  # 필요할 때만 무겁게 연다
            tr, _, _ = R.load_translations(scene.replace("SCN", "_SCN"), scene)
            ov = json.load(open(os.path.join(ROOT, "align_overrides.json"), encoding="utf-8")).get(
                scene, {}
            )
            am = json.load(open(os.path.join(ROOT, "align_map.json"), encoding="utf-8")).get(
                scene, {}
            )
            settled = set(load_lock().get(SETTLED, {}).get(scene, {}))
        eid = next((i for i, r in raw.items() if r.rstrip(b"\x00") == body), None)
        hits.append((off, eid, body.decode("cp932", "ignore")))
        if verbose:
            tag = f"jp{eid}" if eid is not None else "?"
            print(f"  🔴 0x{off:X}  {tag:<8} {why_left(scene, eid, raw, tr, ov, am, settled)}")
            print(f"        {hits[-1][2][:64]!r}")
    return len(refs), hits


def scan_mon():
    """ED2MON0~5.BIN 전량에서 JP 잔존을 센다 — {id: 텍스트}, id = "group:offset(hex)".

    `patch_ed2_monster_lines.is_dialog()` 를 그대로 쓴다 — 이 파일은 코드+데이터 오버레이라
    나이브 가나 스캔은 이진 자료를 문자열로 오독한 잡음을 낸다(실측 836건, 필터 적용 후 6건.
    `is_dialog` 가 이미 그 셋을 가른다: 3글자 미만·사용자 영역·가나 비율).

    ⚠ **그래서 이 게이트는 세 글자 미만 일본어를 원리적으로 못 본다** — 필터를 풀면 잡음
    836건으로 돌아간다(늘 빨간불이 더 나쁘다). 012(`と` 한 글자가 붉은슬라임 분열 메시지에
    남았던 것)가 그 부류였고, 이 게이트가 아니라 되읽기로 잡혔다(2026-09-13). 짧은 조각이
    의심되면 **이 게이트를 믿지 말고 손으로 센다.**
    """
    hits = {}
    for group, (lba, size) in sorted(MON.items()):
        data = bytes(extract(lba, size, path=IMG))
        i = 0
        while i < len(data) - 1:
            if data[i] == 0:
                i += 1
                continue
            j = data.find(b"\x00", i)
            if j < 0:
                break
            s = decode_sjis(data[i:j]) if 2 <= j - i <= 200 else None
            if s and is_dialog(s):
                hits[f"{group}:{i:#x}"] = s
            i = j + 1
    return hits


def check_mon_baseline(hits, *, strict=False):
    """`scan_mon()` 결과를 기준선과 대조 — 조판 지문과 같은 꼴(늘 찍고, 늘면 실패, 줄면 알린다).

    0 을 목표로 삼지 않는다 — 이름 접미 변형(D/E/F 등)처럼 **지금 고칠 수 있는 게 아직
    아닌** 잔여가 섞여 있고, 늘 빨간불이면 아무도 안 본다.
    """
    print(f"  ED2MON0~5.BIN 전량: JP 잔존 {len(hits)}곳")
    if not os.path.exists(MON_BASELINE):
        print(
            f"    (기준선 없음 — {os.path.relpath(MON_BASELINE, ROOT)} 를 만들어 두면 회귀를 잡는다)"
        )
        return
    with open(MON_BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    base_ids = set(base["_ids"])
    ids = set(hits)
    new = sorted(ids - base_ids)
    gone = sorted(base_ids - ids)
    print(f"    기준선 {len(base_ids)}건 대비 — 새로 생김 {len(new)} · 해소됨 {len(gone)}")
    if gone:
        print(f"    ℹ 해소된 자리(기준선을 손으로 갱신할 것): {', '.join(gone)}")
    if new:
        lines = [f"      {i}  {hits[i]!r}" for i in new]
        msg = (
            "ED2MON0~5.BIN: 새로 JP 가 남은 자리가 생겼다\n"
            + "\n".join(lines)
            + (
                f"\n기준선: {os.path.relpath(MON_BASELINE, ROOT)} (의도된 변화면 이 파일을 갱신한다)"
            )
        )
        if strict:
            raise SystemExit(msg)
        print("    ⚠ " + msg.replace("\n", "\n    "))


def check_mon_name_coverage(*, strict=True):
    """몬스터 이름 정본(전 종)이 **최종 이미지 어딘가에 최소 1곳** 읽히나.

    🔴 052 회귀(2026-09-14, 마스터 QA RE 재현)의 교훈 — 재배치 도구가 둘 이상이면 서로의
    꼬리를 지울 수 있고, 그 결과는 **"옛 자리도 새 자리도 없음"**이라 이름 슬롯·재배치
    경로 어느 쪽을 봐도 안 잡힌다(둘 다 "나는 정상적으로 처리했다"고 믿는다). 유일한
    방어선은 **원인이 아니라 결과를 보는 것** — 종마다 "이미지 어딘가에서 읽히는가"만
    묻는다. 도구가 몇 개든, 원인이 무엇이든 이 축 하나로 다 잡힌다.

    ⚠ **접미 변형(A/B/′/″ 등)은 안 가른다** — 종(줄기) 하나가 어느 변형으로든 한 곳만
    읽히면 통과. 정확한 변형별 커버리지는 052/053의 몫이고, 이 게이트는 "그 종이
    통째로 사라졌나"만 본다(가장 싼 값에 가장 넓은 방어선).
    """
    with open(CANON, encoding="utf-8") as f:
        canon = json.load(f)
    missing = []
    for stem, kr in sorted(canon.items()):
        want = _enc(kr)
        found = False
        for group, (lba, size) in sorted(MON.items()):
            cap = (size + 2047) // 2048 * 2048
            buf = bytes(extract(lba, cap, path=IMG))
            if want in buf:
                found = True
                break
        if not found:
            missing.append((stem, kr))
    print(f"  몬스터 이름 정본 {len(canon)}종 — 이미지에서 안 읽히는 종 {len(missing)}개")
    if missing:
        lines = [f"    {stem} → {kr}" for stem, kr in missing]
        msg = "몬스터 이름이 이미지 어디에도 없다(옛 자리도 새 자리도 아님)\n" + "\n".join(lines)
        if strict:
            raise SystemExit(msg)
        print("  ⚠ " + msg.replace("\n", "\n  "))
    return len(missing)


def check_mon_name_no_live_jp(*, strict=True):
    """ⓐ 정본 JP 이름 전량을 **최종 이미지**에서 세어, **살아 있는 참조**가 있는 자리가
    있으면 실패시킨다(2026-09-14, 마스터 QA 052/047/012 재발 방지 셋 중 첫째).

    🔴 **`check_mon_name_coverage`(위)와 방향이 반대다** — 그건 "KR 이 어딘가에 있나"만
    보고 JP 잔존은 안 본다. 이건 "JP 원문이 아직 살아서 참조되는 자리가 있나"를 본다.
    분모는 **정본 JP 이름 전량**이지 우리 KR 표가 아니다 — 우리 표에 없는 이름이 남아도
    잡아야 047(레밍플러스A — 표에 없어 아예 안 보였다)류를 다시 막는다.

    🔴 **전각 SJIS 뿐 아니라 반각 가타카나(JIS X 0201)도 같이 찾는다**(2026-09-14,
    마스터 QA 051 — 「이슈타~이즈」HUD 가 반각으로 따로 있었는데 전각 검색만 해서
    영영 안 보였다. 인코딩 층을 건너뛴 검색 다섯째 사례). `_to_halfwidth()`로 반각
    변환이 되는 이름만 추가로 찾는다(변환 불가 — 한자 등 — 는 전각만).

    `overlay_refs()`(재배치가 실제로 쓰는 그 함수)를 **최종 빌드 버퍼**에 직접 돌려
    lui/addiu 가 가리키는 자리를 얻는다 — 재배치 뒤에도 참조는 늘 갱신돼 있으니 이
    버퍼 하나로 "지금 진짜로 읽히는 자리"가 나온다. 원본 자리는 재배치 시 0 으로
    비워지므로(`_relocate`) 옛 자리에 원본이 남아 있어도 참조가 없으면 죽은 것이다.

    ⚠ **죽은 잔존(참조 없는 JP)은 기준선으로 눌러 둔다** — 0 을 강요하면 늘 빨간불이
    된다(조판 지문·`check_original_diff`와 같은 꼴). 늘면 실패, 줄면 알린다.
    """
    with open(CANON, encoding="utf-8") as f:
        canon = json.load(f)  # {JP: KR}
    hits = []
    for group, (lba, size) in sorted(MON.items()):
        cap = (size + 2047) // 2048 * 2048
        buf = bytes(extract(lba, cap, path=IMG))
        refs, _lui_use = overlay_refs(buf)
        for jp in canon:
            needles = [jp.encode("cp932")]
            hw = _to_halfwidth(jp)
            if hw:
                needles.append(hw.encode("cp932"))
            for jpb in needles:
                idx = buf.find(jpb)
                while idx >= 0:
                    if idx in refs:
                        hits.append(f"{group}:{idx:#x}:{jp}")
                    idx = buf.find(jpb, idx + 1)
    print(f"  몬스터 JP 이름 {len(canon)}종 — 살아 있는 참조를 가진 JP 잔존 {len(hits)}곳")
    if not os.path.exists(MON_NAME_LIVE_JP_BASELINE):
        print(
            f"    (기준선 없음 — {os.path.relpath(MON_NAME_LIVE_JP_BASELINE, ROOT)} 를 만들면 회귀를 잡는다)"
        )
        return len(hits)
    with open(MON_NAME_LIVE_JP_BASELINE, encoding="utf-8") as f:
        base = json.load(f)
    base_ids = set(base["_ids"])
    ids = set(hits)
    new = sorted(ids - base_ids)
    gone = sorted(base_ids - ids)
    print(f"    기준선 {len(base_ids)}건 대비 — 새로 생김 {len(new)} · 해소됨 {len(gone)}")
    if gone:
        print(f"    ℹ 해소된 자리(기준선을 손으로 갱신할 것): {', '.join(gone)}")
    if new:
        msg = (
            "몬스터 JP 이름이 살아 있는 참조와 함께 남았다(화면에 뜬다)\n"
            + "\n".join(f"      {i}" for i in new)
            + f"\n기준선: {os.path.relpath(MON_NAME_LIVE_JP_BASELINE, ROOT)} (의도된 변화면 이 파일을 갱신한다)"
        )
        if strict:
            raise SystemExit(msg)
        print("    ⚠ " + msg.replace("\n", "\n    "))
    return len(hits)


def check_mon_name_null_terminated(*, strict=True):
    """ⓑ 몬스터 **이름 테이블**(`patch_ed2_monsters.plan()`) 항목이 최종 이미지에서
    이름 바로 뒤가 `0x00` 인가(052 재발 방지 둘째).

    052 는 정확히 이걸 어겼다 — 재배치된 이름 뒤에 널이 아예 없어 다음 레코드가
    이어 그려졌다. `check_mon_name_coverage`(위)는 "어딘가에 있나"만 보고 종단은
    안 본다 — 있어도 뒤가 안 닫히면 화면은 여전히 깨진다.

    ⚠ **분모는 `plan()`의 fit+over 뿐이다 — 정본 전량이 아니다.** 정본 중엔
    사일런트로드·브람나퀸처럼 **이름 테이블을 거치지 않고** 대사 문장에 직접
    박히는 유일 보스명이 있다 — 그런 이름은 원래 뒤에 다른 글자가 이어지는 게
    정상이라(문장의 일부다) 종단 요구가 성립하지 않는다. `plan()`에 뜬 것만
    "테이블 슬롯"이라 종단 계약이 있다.
    """
    from patch_ed2_monsters import _dedup_over
    from patch_ed2_monsters import plan as mon_plan

    fit, over, _none = mon_plan()
    lba_to_group = {lba: g for g, (lba, _s) in MON.items()}
    missing = []
    for lba, off, jp, kr, _slot in fit:
        group = lba_to_group[lba]
        size = MON[group][1]
        cap = (size + 2047) // 2048 * 2048
        buf = bytes(extract(lba, cap, path=IMG))
        want = _enc(kr)
        end = off + len(want)
        if end >= len(buf) or buf[end] != 0:
            missing.append((group, off, jp, kr, "fit"))
    for lba, d in _dedup_over(over).items():
        group = lba_to_group[lba]
        size = MON[group][1]
        cap = (size + 2047) // 2048 * 2048
        buf = bytes(extract(lba, cap, path=IMG))
        for off2, jp, kr, _slot in d.values():
            # ⚠ **앞 경계는 안 본다** — `_relocate`가 재배치 꼬리를 잇는 시작점("실제
            # 쓰인 끝")은 섹터 슬랙에 남은 **원판 잔여 비영 바이트**로 밀릴 수 있고
            # (실측: 불꽃의기사A·육지해파리A 둘 다 이름 바로 앞이 `e0 03` 이었다 —
            # 우리가 쓴 게 아니라 원판 슬랙, 아무도 안 읽는다), 그건 052 가 어긴
            # 계약(**뒤**가 0x00 인가)과 무관하다. 뒤만 본다.
            want = _enc(kr)
            idx = buf.find(want)
            ok = False
            while idx >= 0:
                end = idx + len(want)
                if end < len(buf) and buf[end] == 0:
                    ok = True
                    break
                idx = buf.find(want, idx + 1)
            if not ok:
                missing.append((group, off2, jp, kr, "over(재배치 꼬리)"))
    print(
        f"  몬스터 이름 테이블 종단(뒤 0x00) — 못 닫힌 항목 {len(missing)}개 (분모 {len(fit) + len(over)})"
    )
    if missing:
        lines = [f"    ED2MON{g}:{off:#x} {jp} → {kr} ({why})" for g, off, jp, kr, why in missing]
        msg = "이름 테이블 항목 뒤가 0x00 으로 안 닫힌다\n" + "\n".join(lines)
        if strict:
            raise SystemExit(msg)
        print("  ⚠ " + msg.replace("\n", "\n  "))
    return len(missing)


def check_mon_name_across_color_codes(*, strict=True):
    """ⓒ `%c`(런타임 색 전환 리터럴)를 건너뛰고 이어 붙이면 정본과 일치하는가
    (012 재발 방지 셋째).

    012 는 이름이 `%c%c` 로 갈린 자리(색 전환 삽입 구간)에서 우리가 옮긴 값이
    통짜 검색으로는 안 걸렸고, 손으로 친 hex 리터럴에서 음절 하나("임")가 빠진
    채로도 아무 게이트에 안 걸렸다. 여기서는 canon KR 이름의 **각 글자 사이에
    `%c` 가 0~2개 끼어도 되는 느슨한 패턴**으로 찾는다 — 이게 하나도 안 걸리면
    그 이름은 이미지 어디에도(색전환 삽입 형태로도) 없다는 뜻이라 실패시킨다.

    ⚠ **`check_mon_name_coverage`(통짜 검색)의 상위 집합이다** — 통짜로 걸리면 이것도
    당연히 걸린다. 이게 따로 필요한 이유는 통짜로는 못 찾는(색전환이 실제로 낀) 자리도
    보기 위해서다. ⚠ **분열 변형(′/″ 등 canon 에 없는 접미)은 이 축의 대상이 아니다**
    — canon 은 종(줄기) 이름만 담으므로, 분열 표기 자체의 정확성은 `patch_ed2_monsters
    .SPLIT_SLIME_MSGS` 의 byte-assert 가 별도로 지킨다(재배치 전 원본 대조라 손 탄
    자리를 이미 막는다).
    """
    with open(CANON, encoding="utf-8") as f:
        canon = json.load(f)
    missing = []
    for stem, kr in sorted(canon.items()):
        chars = [_enc(c) for c in kr]
        pat = re.escape(chars[0])
        for c in chars[1:]:
            pat += rb"(?:%c){0,2}" + re.escape(c)
        rx = re.compile(pat)
        found = False
        for lba, size in sorted(MON.values()):
            cap = (size + 2047) // 2048 * 2048
            buf = bytes(extract(lba, cap, path=IMG))
            if rx.search(buf):
                found = True
                break
        if not found:
            missing.append((stem, kr))
    print(f"  몬스터 이름 %c 건너뛰고 이어 붙이기 — 못 찾은 종 {len(missing)}개")
    if missing:
        lines = [f"    {stem} → {kr}" for stem, kr in missing]
        msg = "%c 를 건너뛰어도 정본 이름이 이미지 어디에도 없다\n" + "\n".join(lines)
        if strict:
            raise SystemExit(msg)
        print("  ⚠ " + msg.replace("\n", "\n  "))
    return len(missing)


def main():
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    total = 0
    for name, _, _ in _scn_layout():
        if want and name not in want:
            continue
        n_ref, hits = scan(name, verbose=bool(want))
        total += len(hits)
        print(f"  {name}: 참조 블록 {n_ref} · 살아있는 가나 {len(hits)}곳")
    print(f"\n화면에 나오는 일본어 {total}곳")
    if not want:
        check_mon_baseline(scan_mon())
        check_translated_but_raw_all(strict=True)
        check_mon_name_coverage(strict=True)
        check_mon_name_no_live_jp(strict=True)
        check_mon_name_null_terminated(strict=True)
        check_mon_name_across_color_codes(strict=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
