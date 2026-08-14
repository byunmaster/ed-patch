"""전체 한글 패치 빌드 오케스트레이션 — 단일 최종 이미지 생성.

체인: reinsert(대사+폰트) → gfx_cards(챕터카드) → hud_names(상태창 이름판) → sys_ui(시스템 UI)
     → work/Eiyuu Densetsu (KR).bin/.cue  (테스트는 이 하나만)

체인 끝에 patch_opening_font(OPEN1.EXE 오프닝)를 FINAL 제자리 적용한다.
중간 산출물(KR Pilot / KR UI)은 빌드 후 삭제한다. 테스트 이미지를 하나로 유지.
"""

import glob
import os
import shutil
import subprocess
import sys

from common import BUILD_DIR, ORIG_BIN, ROOT, verify_source, write_cue

TOOLS = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
FINAL_CUE = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).cue")
KR_UI = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR UI).bin")

# 빌드 중간·구 실험 산출물 (최종 하나만 남기고 정리)
INTERMEDIATES = ["Eiyuu Densetsu (KR Pilot)", "Eiyuu Densetsu (KR UI)"]
STALE = ["Eiyuu Densetsu (KR OP)", "Eiyuu Densetsu (Len Test)", "Eiyuu Densetsu (Test Patch)"]


def run(script, *args):
    print(f"\n=== {script} ===")
    subprocess.run([sys.executable, os.path.join(TOOLS, script), *args], check=True, cwd=TOOLS)


# ── 절대 안 바뀌어야 하는 구간 ────────────────────────────────────────────
# ⚠ 표는 `common.IMMUTABLE` 이 정본이다 — **쓰기 시점 가드**(`common.write_user_data`)와
# 아래 사후 대조가 같은 표를 봐야 한다. 두 벌이면 어긋난다(DRY: 지식은 한 곳).
# 여기 남은 건 **원본과의 최종 대조**다. 쓰기 가드는 `write_user_data` 를 지나는 경로만
# 보므로, 그걸 우회하는 쓰기·재배치 사고는 이 대조가 잡는다(두 겹으로 둔다).


def check_immutable():
    """선언한 무변경 구간이 원본과 같은지 확인한다(다르면 빌드 실패)."""
    from common import IMMUTABLE, TEXT_PTR, extract

    src = glob.glob(os.path.join(ROOT, "..", "..", "originals", "jp", "ps1-ed1+2", "*.bin"))
    if not src:
        print("  ⚠ 원본 없음 — 무변경 구간 검사 건너뜀")
        return
    bad = []
    for (lba, size), regions in IMMUTABLE.items():
        orig = bytes(extract(lba, size, path=src[0]))
        now = bytes(extract(lba, size, path=FINAL))
        for name, a, b, mode in regions:
            if mode == "script":
                # 텍스트 포인터(0x8001xxxx)는 줄 재배치로 값이 바뀐다 — 커맨드 나열만 본다.
                import struct

                for o in range(a, b, 4):
                    ow = struct.unpack("<I", orig[o : o + 4])[0]
                    if ow in TEXT_PTR:
                        continue
                    if orig[o : o + 4] != now[o : o + 4]:
                        nw = struct.unpack("<I", now[o : o + 4])[0]
                        bad.append(f"{name} @0x{o:X}: {ow:08X} → {nw:08X}")
            elif orig[a:b] != now[a:b]:
                n = sum(1 for x, y in zip(orig[a:b], now[a:b], strict=True) if x != y)
                bad.append(f"{name} 0x{a:X}~0x{b:X}: {n}/{b - a}B 변경")
    if bad:
        raise SystemExit("무변경 구간이 바뀌었다:\n  " + "\n  ".join(bad))
    print(f"무변경 구간 {sum(len(v) for v in IMMUTABLE.values())}곳 확인 — 원본과 동일")


def _requa_note():
    """**인게임 확인 뒤 문안이 바뀐 자리**가 쌓여 있으면 알린다.

    ⚠ `--relock` 은 「확인한 대사가 바뀌었다」는 뜻이라 그 자리의 QA 판정이 무효가 된다.
    조용히 쌓이면 아무도 안 본다 — 실제로 2장 QA 뒤 264건이 모르는 새 바뀌어 있었다.
    """
    import json

    from common import ROOT

    q = json.load(open(os.path.join(ROOT, "locked_lines.json"), encoding="utf-8")).get("_requa", {})
    n = sum(len(v) for v in q.values())
    if n:
        per = " · ".join(f"{k} {len(v)}" for k, v in sorted(q.items()))
        print(f"\n⚠ 재검수 대기 {n}건 ({per}) — `tools/lock_lines.py --requa`")


def check_font_generation():
    """이미지에 실린 폰트가 **지금 글리프 계획으로 구운 것과 같은가**(세대 결박).

    ⚠ 계획(`hangul_map.SYLLABLES`)은 폰트 블록·본문 인코딩·조사 훅 테이블 **셋의 계약**이다.
    계획이 순수 함수라 한 실행 안에서는 안 어긋나지만, 단독 실행·A/B 로 이미지를 조각조각
    갱신하면 낡은 폰트 위에 새 계획으로 덧쓸 수 있다 — 실패하지 않고 글자가 뒤바뀐다.
    """
    from hangul_font import verify_image_font

    verify_image_font(FINAL)
    print("글리프 계획 세대 확인 — 이미지 폰트가 지금 계획과 같다")


def rm(stem):
    for ext in (".bin", ".cue"):
        p = os.path.join(BUILD_DIR, stem + ext)
        if os.path.exists(p):
            os.remove(p)


def _why_excluded():
    """탈락 사유를 게이트 메시지에 붙인다 — **원인까지 한 번에 말한다.**

    ⚠ 재삽입기가 `excluded_<씬>.json` 에 사유를 이미 남기는데, 게이트는 「일본어가 남았다」
    까지만 말했다. 그래서 가운뎃점(`·`) 하나가 `encode` 로 탈락했을 때 파일을 따로 열어야
    원인이 나왔다(2026-08-12 실측). 사유는 셋이다:

    - `encode` — **폰트에 없는 글자.** `·`(가운뎃점) 가 실제로 그랬다. `,` 나 `~` 로 쓴다
    - `size`   — 문안이 원본 블록보다 길다. 줄이거나 창을 나눈다
    - `fmt_drop` — `%s`·`%d` 인자 센티널(`\\x1a`·`\\x1b`)을 잃었다. **보이지 않는 제어문자**다
    """
    import json as _json

    from common import OUT_DIR

    rows = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, "excluded_*.json"))):
        scn = os.path.basename(p)[len("excluded_") : -len(".json")]
        with open(p, encoding="utf-8") as f:
            for eid, why in _json.load(f).items():
                rows.append(f"    {scn} jp{eid}: {why}")
    if not rows:
        return "  (탈락 기록이 없다 — 원문 잔존은 미이관 블록일 수 있다)"
    return (
        "  탈락 사유(encode=폰트에 없는 글자 · size=너무 김 · fmt_drop=인자 유실):\n"
        + "\n".join(rows)
    )


def check_screen_gates():
    """**화면에 나가는 바이트**를 보는 게이트 — 빌드가 성공해도 여기서 걸린다.

    ⚠ 이 세션에서 같은 성격의 사고를 두 번 냈다(2026-08-12). **둘 다 빌드는 성공했고
    단위 테스트도 통과했다** — 블록이 조용히 탈락하고 화면엔 원문이 그대로 남았다:

    - 해설 문체 방침을 시스템 메시지(`to_plain`)까지 적용 → 문안이 두 글자 길어져
      SCN6 정형 블록 10건이 `size` 로 탈락
    - `백돌이 ␛개.` 를 다듬다 `␛`(`%d` 인자)를 날림 → 2블록 `fmt_drop` 탈락

    ⇒ **프리커밋이 아니라 빌드에 둔다.** 두 검사 모두 빌드 산출물을 읽어야 하고,
    커밋은 명시할 때만 하지만 빌드는 매번 돌기 때문이다.
    """
    import check_scn_jp_left
    import script_draft
    from patch_sys_ui import SCN_FILES

    left = []
    for name, _lba, _size in SCN_FILES:
        _n, hits = check_scn_jp_left.scan(name, verbose=False)
        if hits:
            left.append(f"{name} {len(hits)}곳")
    if left:
        raise SystemExit(
            "화면에 일본어가 남았다 — 블록이 탈락했다: " + " · ".join(left) + "\n" + _why_excluded()
        )
    if script_draft.check_sentinels():
        raise SystemExit("번역 정본이 `%s`·`%d` 인자를 잃었다 — 그 블록은 fmt_drop 으로 탈락한다")


def main():
    # ⚠ **원본이 그 덤프인지 먼저 확인한다.** 오프셋·LBA 가 전부 한 덤프에 결박돼 있어
    # 다른 리비전을 넣으면 실패하지 않고 **망가진 이미지가 나온다**(mcpads 패처들의 CRC 경고
    # + 명시적 탈출구를 옮겼다). 알고도 계속하려면 `ALLOW_NONCANONICAL_SRC=1`.
    if os.path.exists(ORIG_BIN):
        verify_source()
    else:
        print("  ⚠ 원본 없음 — 지문 확인 건너뜀")

    # ⚠ 테스트 이미지는 **항상 하나만** 남긴다(CLAUDE.md). 중간 산출물은 체인 끝에서 지우는데,
    # 도구를 단독 실행하면(예: reinsert 만 돌려 A/B) 그게 남는다 — 시작할 때도 한 번 치운다.
    for stem in INTERMEDIATES + STALE:
        rm(stem)
    for p in glob.glob(os.path.join(BUILD_DIR, "*.failed")):  # 지난 실패 잔재
        os.remove(p)

    # 원본 덤프(derived/scn_jp · derived/dos_kr)도 파생물이라 낡는다. 추출기가 바뀌면
    # 덤프와 커밋된 정본(align_map·align_overrides)이 어긋나 빌드가 죽는다 — 머신을 옮겨
    # 낡은 덤프를 안고 왔더니 `T_024#7` 의 `{p}` 페이지가 사라져 chain 이 IndexError 로
    # 터졌다(2026-08-09). 둘 합쳐 1.3초라 매번 새로 뜬다(결정적, 원본 읽기 전용).
    run("extract_scn.py")  # JP 대사 덤프
    run("extract_dos_kr.py")  # 정발 대사 덤프

    # 화자맵(align/*_speakers.json)은 reinsert 의 이름창 입력인데 파생물이라 낡는다 —
    # SPEAKER_DICT 를 고쳐도 빌드에 안 붙어 `ロー`가 음차 `로`로 나갔다(2026-08-02).
    # ⚠ `--speakers-only` 필수: 인자 없이 돌리면 의미정렬 `*_SCN*.json` 을 덮어쓴다.
    run("align_jp_kr.py", "--speakers-only")
    run("reinsert_kr_pilot.py")
    run("patch_gfx_cards.py")
    run("patch_hud_names.py")
    run("patch_sys_ui.py")

    shutil.copyfile(KR_UI, FINAL)
    write_cue(FINAL_CUE, os.path.basename(FINAL))
    run("patch_ed2_sys.py")
    run(
        "patch_ed2_battle.py"
    )  # ED2.EXE 전투 문안 — 제자리 치환만(재배치 미구현)  # ED2.EXE 시스템 UI·지명 — **ED.EXE 와 사본 관계**라 따로 쓴다
    run("patch_ed2_monsters.py")  # ED2MON0~5.BIN 몬스터 이름 — 제자리 치환만
    run("patch_ed2_monster_lines.py")  # ED2MON0~5.BIN 전투 대사 — 제자리 치환만
    run("patch_items.py")  # ED.EXE 아이템·마법명 (FINAL 제자리 갱신)
    # 줄머리 공백 훅(patch_battle_wrap.py)은 **미채택 확정**(2026-07-23 유저 결정, 보류 아님).
    # 구현·검증까지 끝냈으나 ①differential로 인트로 정지와 무관함이 확인돼 실익이 없었고
    # ②매 문자 분기를 거는 런타임 비용·리스크보다, 화면을 보고 그때그때 텍스트 데이터를
    # 고치는 편이 낫다는 판단(공백→개행 교체 = battle[9·27·345] 방식).
    # 훅 코드는 렌더러 규명 자산이라 참고용으로만 보존한다 — 되살릴 계획 없음.
    run(
        "patch_josa_hook.py"
    )  # 동적 조사 훅 — 병기(은(는)) → 정확 조사(2026-07-27 인게임 검증 통과)
    run("patch_gfx_title.py")  # START.DAT 타이틀 로고·버튼 TIM (FINAL 제자리 갱신)
    run("patch_opening_font.py")  # OPEN1.EXE 오프닝 폰트+텍스트 (FINAL 제자리 갱신)
    for stem in INTERMEDIATES + STALE:
        rm(stem)
    check_immutable()
    check_font_generation()
    check_screen_gates()
    _requa_note()
    from common import BUILD_TAG

    print(f"\n완료: {FINAL}\n꼬리표 [{BUILD_TAG}] — 테스트는 이 하나만: {os.path.basename(FINAL_CUE)}")


if __name__ == "__main__":
    # ⚠ 실패하면 산출물을 **무효화**한다. 낡은 이미지가 남아 있으면 다음 조사에서 그걸
    #   정상으로 오해한다(2026-08-02 실측 — 실패한 빌드의 옛 이미지를 덤프해 오진했다).
    try:
        main()
    except BaseException:
        for p in (FINAL, FINAL_CUE):
            if os.path.exists(p):
                os.rename(p, p + ".failed")
        print(f"\n⚠ 빌드 실패 — 산출물을 *.failed 로 무효화했다 ({BUILD_DIR})")
        raise
