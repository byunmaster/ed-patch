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

from common import WORK_DIR, write_cue

TOOLS = os.path.dirname(os.path.abspath(__file__))
FINAL = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR).bin")
FINAL_CUE = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR).cue")
KR_UI = os.path.join(WORK_DIR, "Eiyuu Densetsu (KR UI).bin")

# 빌드 중간·구 실험 산출물 (최종 하나만 남기고 정리)
INTERMEDIATES = ["Eiyuu Densetsu (KR Pilot)", "Eiyuu Densetsu (KR UI)"]
STALE = ["Eiyuu Densetsu (KR OP)", "Eiyuu Densetsu (Len Test)", "Eiyuu Densetsu (Test Patch)"]


def run(script):
    print(f"\n=== {script} ===")
    subprocess.run([sys.executable, os.path.join(TOOLS, script)], check=True, cwd=TOOLS)


def rm(stem):
    for ext in (".bin", ".cue"):
        p = os.path.join(WORK_DIR, stem + ext)
        if os.path.exists(p):
            os.remove(p)


def main():
    run("reinsert_kr_pilot.py")
    run("patch_gfx_cards.py")
    run("patch_hud_names.py")
    run("patch_sys_ui.py")

    shutil.copyfile(KR_UI, FINAL)
    write_cue(FINAL_CUE, os.path.basename(FINAL))
    run("patch_opening_font.py")  # OPEN1.EXE 오프닝 폰트+텍스트 (FINAL 제자리 갱신)
    for stem in INTERMEDIATES + STALE:
        rm(stem)
    print(f"\n완료: {FINAL}\n테스트는 이 하나만: {os.path.basename(FINAL_CUE)}")


if __name__ == "__main__":
    main()
