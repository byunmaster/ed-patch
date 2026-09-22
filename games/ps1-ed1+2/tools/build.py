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

from common import BUILD_DIR, ORIG_BIN, OUT_DIR, ROOT, verify_source, write_cue

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
    # ⚠ ED2MON0~5.BIN(ED2 전투 대사 오버레이) — 2026-09-13 편입. 041①이 퇴보였을 때 여기
    # 116곳이 JP 로 남아 있었는데 위 SCN 축만 보느라 아무도 몰랐다. 0 이 아니라 기준선
    # 대조다(이름 접미 변형 등 "할 일"이 섞여 있다 — 늘 빨간불을 피한다).
    check_scn_jp_left.check_mon_baseline(check_scn_jp_left.scan_mon(), strict=True)
    # 🔴 위 `scan()`은 "참조 블록·kind 분류"에 기대는 축이라, **분류 자체가 틀리면
    # 영영 못 본다**(2026-09-13, 마스터 QA 051 — ED2SCN8 jp0 이 실제 대사인데
    # `kind:"header"`(선두 지명)로 뽑혀 `mid_block_ref` 로 통째로 건너뛰었고, 표에
    # 번역이 있는데도 화면엔 원문이 그대로 나갔다. 위 scan() 은 이걸 "0곳"으로 찍었다).
    # ⇒ 분류·참조·임계값을 전혀 안 보는 별도 축 — "번역표에 값이 있는데 그 자리
    # 바이트가 원문 그대로인가"만 잰다(0을 목표로 삼는다, 문턱값 없음).
    check_scn_jp_left.check_translated_but_raw_all(strict=True)
    # 🔴 위는 "이미지 어딘가에 일본어가 있나"(분모=파일 전체) — 방향을 뒤집어 "우리가
    # 쓴 자리가 맞나"(분모=우리 표)도 본다. 047(레밍플러스A — 스캐너가 아예 못 본 이름)
    # 는 위 축으로는 원리상 안 잡힌다.
    import check_ed2mon_readback

    bad_names = check_ed2mon_readback.check_names()
    missing_lines = check_ed2mon_readback.check_lines()
    blind_names = check_ed2mon_readback.check_name_coverage()
    check_ed2mon_readback.check_baseline(bad_names, missing_lines, blind_names, strict=True)
    # 🔴 위 셋 다 "우리 표"가 분모라 표에 없는 자리는 원리적으로 못 본다(047 의 진짜
    # 교훈). 원본↔빌드를 직접 대조해 "우리가 건드린 자리"만 분모로 삼는다 — 스탯 이진
    # 자료가 많아도 잡음이 0이다.
    import check_original_diff

    check_original_diff.check_baseline("ED2MON", strict=True)
    # ED2.EXE 는 개수만 기준선으로 등록(2026-09-13) — 분류는 다음 라운드, 그래서 아직
    # 비strict(새 자리가 생겨도 보고만 하고 빌드는 안 막는다).
    check_original_diff.check_baseline("ED2EXE", strict=False)
    # 사본 개수 게이트(2026-09-15) — "고치는 원본 바이트열이 이미지에 N곳인데 바뀐
    # 게 N곳 미만이면 실패". 오늘 일곱 번 겪은 "사본이 둘" 사고의 공통 축.
    import check_copy_completeness

    if not check_copy_completeness.check():
        raise SystemExit("사본 개수 게이트 실패 — 위 출력을 본다")
    # 056 — **줄 수가 아니라 바이트**가 진짜 한계다(RE 실기, 2026-09-15). 메시지박스
    # strcpy 에 길이검사가 없어 128B 를 넘으면 ra 를 덮는다(소프트락). 반각 폭 게이트
    # (이론상 최악 `check()`)는 "보기" 축이라 비strict 로 남기고, 이건 "구조" 축이라 strict.
    import check_runtime_template_width as CRTW

    CRTW.check_byte_budget(strict=True)
    # 056 잔여 — **분모 재측정(2026-09-15)** 으로 세 번째 거짓 초과 템플릿을 걸러내자
    # 실제 초과가 0이 됐다. 0인 축을 보고로만 두면 다시 늘어도 아무도 안 본다(루트
    # CLAUDE.md) — strict 게이트로 승격. `-v` 로 상세, `--realistic` 로 단독 실행 가능.
    CRTW.check_realistic(strict=True)
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
    # ⚠ 쓰기 지문표를 비우고 시작한다 — 패처들이 **자식 프로세스**라 각자 덧붙인다
    #   (`common._flush_write_log`). 안 비우면 지난 빌드 것이 섞여 되읽기 대조가 거짓말한다.
    _wm = os.path.join(OUT_DIR, "write_manifest.json")
    if os.path.exists(_wm):
        os.remove(_wm)

    run("extract_scn.py")  # JP 대사 덤프
    run("extract_dos_kr.py")  # 정발 대사 덤프

    # 화자맵(align/*_speakers.json)은 reinsert 의 이름창 입력인데 파생물이라 낡는다 —
    # SPEAKER_DICT 를 고쳐도 빌드에 안 붙어 `ロー`가 음차 `로`로 나갔다(2026-08-02).
    # ⚠ `--speakers-only` 필수: 인자 없이 돌리면 의미정렬 `*_SCN*.json` 을 덮어쓴다.
    run("align_jp_kr.py", "--speakers-only")
    run("reinsert_kr_pilot.py")
    run("patch_gfx_cards.py")
    run("patch_hud_names.py", "ED1", "ED2")
    run("patch_sys_ui.py")
    shutil.copyfile(KR_UI, FINAL)
    write_cue(FINAL_CUE, os.path.basename(FINAL))
    # ⚠ 블록으로 안 잡히는 씬 문자열(포인터 테이블 한복판) — 배정·조판 경로 밖이라
    #   여기서만 잡힌다. 씬 재삽입·플레이트 치환 **뒤** · 최종 이미지 위에서 돈다.
    run("patch_scn_orphans.py")
    # ⚠ 창 제어값 교정 — **원판이 안 그리고 넘어가는 창**을 되살린다(문안이 아니라 기계어).
    #   씬 재삽입 뒤 최종 이미지 위에서 돈다. 코드는 재삽입해도 안 움직여 오프셋이 안정하다.
    run("patch_scn_msgctl.py")
    run("patch_ed2_sys.py")  # ED2.EXE 시스템 UI·지명 — **ED.EXE 와 사본 관계**라 따로 쓴다
    run("patch_ed2_battle.py")  # ED2.EXE 전투 문안 — 제자리 치환 + 넘치면 재배치
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
    # 온점 매달기 — 엔진의 29열 중 마지막 한 열을 **반각 부호에만** 연다(훅 둘).
    # ⚠ `reinsert_kr_pilot._hang_merge` 와 **한 몸**이다 — 하나만 켜면 되레 나빠진다.
    run("patch_hang_punct.py")
    run("patch_gfx_title.py")  # START.DAT 타이틀 로고·버튼 TIM (FINAL 제자리 갱신)
    # 동영상 EXE — 넷이 내레이션을 한 벌씩 다 들고 각자 자기 몫만 튼다(읽기 BP 실측).
    # 그래서 파일마다 **자기 슬라이스만** 넣는다. END1·END2 는 세이브가 있어야 확인이 되므로
    # 인게임 검증 뒤에 붙인다.
    run("patch_opening_font.py", "OPEN1", "OPEN2", "END1", "END2")  # 오프닝·엔딩 (FINAL 제자리)
    # 🔴 **ED2MON 을 건드리는 두 스크립트(이름·대사)가 다 돈 뒤, 딱 한 번**(2026-09-14,
    # 012 "와" 뒤 공백 — 대사 스크립트가 같은 자리를 자기 스캔으로 다시 써서 이름
    # 스크립트가 앞서 넣은 공백을 지웠다). 순서 싸움을 피하려고 맨 뒤로 뺐다.
    import patch_ed2_monsters as _pm

    n_conn = _pm.finalize_connector_space()
    if n_conn:
        print(f"ED2MON 접속사 공백 {n_conn}건")
    # 058 지명 지도 그리기(2026-09-14, 마스터 지시) — 칸 넉넉한 자리만 "늑대입"→
    # "늑대의입" 복원. 화면에서 바뀐 곳=그 자리 용도가 밝혀진다(HUD·워프·배너 등).
    import patch_sys_ui as _psu

    _psu.restore_full_place_names()
    # 058ⓑ 반각 한글 글리프 굽기(2026-09-15, RE 확정 주소) — 코드 배정(조사 훅)과
    # 글리프 픽셀은 층이 달라 따로 적용한다. 위 지명 복원과 같은 이유로 맨 뒤.
    import patch_hangul_glyph_table as _phg

    _phg.apply()
    # 058ⓑ ④ — 글리프가 구워진 뒤에야 반각 문자열이 화면에 정상으로 나간다.
    _psu.apply_halfwidth_hud_slots()
    # 073 — 같은 이유로 글리프가 구워진 뒤에. `patch_scn_headers`(위, 사피아호수 전각)가
    # 먼저 써 둔 자리를 반각 11조각으로 덮는다.
    _psu.apply_sapia_lake_hud()
    # 038 — 세레 저택 NPC 슬롯 설치 인자 한 바이트(원판 결함, RE 확정 2026-09-15).
    import patch_npc_zeni_slot as _pnz

    _pnz.apply()
    # 004 — 늑대의입 게일 3세 조형(팩 #4 10행 → 팩 #9 7행 + SCN7 a2=7, RE 확정 2026-09-22·원본 행 정정 09-24).
    # 038 과 같은 부류(NPC 설치 인자)지만 그림 데이터(ED2CHR.DAT)까지 같이 옮긴다.
    import patch_npc_gale3_sprite as _png3

    _png3.apply()
    # 076 — 몽거 전투 종료 때 필드 그림 재적재 플래그(원판의 과잉 보수값) 1→0. ED2.EXE 한 바이트.
    import patch_mongo_field_reload as _pmfr

    _pmfr.apply()
    # 065 — ED2SCN10·ED2SCN13 안 경로 라벨 사본(058ⓑ 와 같은 "사본이 둘" 부류).
    import patch_scn_route_labels as _psrl

    _psrl.apply()
    # 006/012 — HUD 지명은 **JP 원문 길이에 맞춰 인라인된 고정 길이 복사**로 실린다.
    # 우리 전각 한글이 그보다 길면 널이 안 실리거나 글자 중간에서 끊긴다(RE 확정
    # 2026-09-20). 지명 문자열을 다 쓴 **맨 뒤에** 돌아야 최종 길이를 본다.
    import patch_scn_hud_copy as _pshc

    _pshc.apply()
    for stem in INTERMEDIATES + STALE:
        rm(stem)
    check_immutable()
    check_font_generation()
    check_screen_gates()
    _requa_note()
    from common import BUILD_TAG

    movie_swap()
    print(
        f"\n완료: {FINAL}\n꼬리표 [{BUILD_TAG}] — 테스트는 이 하나만: {os.path.basename(FINAL_CUE)}"
    )


def movie_swap():
    """🔬 **검증 전용** — 동영상 EXE 구획을 통째로 갈아 **부팅 직후 엔딩을 본다**.

        ED_BUILD_TAG=ps1-ending-qa ED_MOVIE_SWAP="OPEN1=END1,OPEN2=END2" python3 tools/build.py

    **왜 문안 치환(`ED_OPENING_TEXT_AS`)으로는 부족한가.** 그건 글자만 갈아끼우므로 **배경이
    오프닝 것**이다(유저 지적 2026-08-22). 엔딩 그림 위에서 봐야 잡히는 게 있고 — 밝은 배경의
    가독성 · 그림과 겹치는 자리 — 게다가 오프닝 슬롯이 50뿐이라 ED1 엔딩 59줄 중 **9줄이
    아예 안 보였다.** 구획째 얹으면 둘 다 없어진다.

    네 파일이 **같은 크기(96,256B = 47섹터)** 라 자리를 그대로 맞바꿀 수 있다.
    ⚠ 한글 패치가 **끝난 뒤** 복사한다 — 원본 END1 을 얹으면 일본어 엔딩을 보게 된다.
    🔴 배포 빌드에 절대 켜지 않는다. 환경변수라 커밋물에 안 남고, 꼬리표를 갈라 짓는다.
    """
    spec = os.environ.get("ED_MOVIE_SWAP", "")
    pairs = [kv.split("=", 1) for kv in spec.split(",") if "=" in kv]
    if not pairs:
        return
    import common
    from patch_opening_font import GAMES, SIZE

    for dst, src in pairs:
        assert dst in GAMES and src in GAMES, f"모르는 동영상 EXE: {dst}={src}"
        lba = GAMES[dst]["lba"]
        data = common.extract(GAMES[src]["lba"], SIZE, FINAL)
        # ⚠ 이 파일은 **통째로** 갈리므로 자기 무변경 구간(OPEN1 포인터 표 등)도 당연히
        #   바뀐다. 가드를 약하게 만들지 않고 **그 파일의 선언만 이 순간 내려놓는다** —
        #   쓰기 경로는 그대로고(EDC/ECC·지문·되읽기 대장 다 탄다), 다른 구간 가드는 산다.
        #   🔴 이게 「게이트 우회」가 아닌 이유: 우회는 **검사만 끄고 같은 일을 하는 것**이고,
        #      여기는 **하는 일 자체가 다르다**(패치가 아니라 파일 교체). 그래서 범위를
        #      교체 대상 하나로 좁히고, 무엇을 내려놓았는지 찍고, 끝나면 되돌린다.
        #   ⚠ 선언이 **없는** 파일도 있다(OPEN2) — 없는 걸 찾으려다 터졌다. 있으면 내려놓는다.
        key = next((k for k in common.IMMUTABLE if k[0] == lba), None)
        held = common.IMMUTABLE.pop(key) if key else []
        if held:
            print(f"  🔬 {dst} 무변경 선언 {len(held)}건을 이 쓰기 동안만 내려놓는다")
        try:
            with open(FINAL, "r+b") as f:
                n = common.write_user_data(f, lba, data, label=f"🔬 {dst} ← {src}")
        finally:
            if key:
                common.IMMUTABLE[key] = held
        print(f"  🔬 동영상 구획 교체: {dst}(LBA {lba}) ← {src} — 섹터 {n}")


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
