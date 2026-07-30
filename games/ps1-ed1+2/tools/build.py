"""전체 한글 패치 빌드 오케스트레이션 — 단일 최종 이미지 생성.

체인: reinsert(대사+폰트) → gfx_cards(챕터카드) → hud_names(상태창 이름판) → sys_ui(시스템 UI)
     → work/Eiyuu Densetsu (KR).bin/.cue  (테스트는 이 하나만)

체인 끝에 patch_opening_font(OPEN1.EXE 오프닝)를 FINAL 제자리 적용한다.
중간 산출물(KR Pilot / KR UI)은 빌드 후 삭제한다. 테스트 이미지를 하나로 유지.
"""

import os
import shutil
import subprocess
import sys

from common import BUILD_DIR, write_cue

TOOLS = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")
FINAL_CUE = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).cue")
KR_UI = os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR UI).bin")

# 빌드 중간·구 실험 산출물 (최종 하나만 남기고 정리)
INTERMEDIATES = ["Eiyuu Densetsu (KR Pilot)", "Eiyuu Densetsu (KR UI)"]
STALE = ["Eiyuu Densetsu (KR OP)", "Eiyuu Densetsu (Len Test)", "Eiyuu Densetsu (Test Patch)"]


def run(script):
    print(f"\n=== {script} ===")
    subprocess.run([sys.executable, os.path.join(TOOLS, script)], check=True, cwd=TOOLS)


def rm(stem):
    for ext in (".bin", ".cue"):
        p = os.path.join(BUILD_DIR, stem + ext)
        if os.path.exists(p):
            os.remove(p)


def main():
    run("reinsert_kr_pilot.py")
    run("patch_gfx_cards.py")
    run("patch_hud_names.py")
    run("patch_sys_ui.py")

    shutil.copyfile(KR_UI, FINAL)
    write_cue(FINAL_CUE, os.path.basename(FINAL))
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
    print(f"\n완료: {FINAL}\n테스트는 이 하나만: {os.path.basename(FINAL_CUE)}")


if __name__ == "__main__":
    main()
