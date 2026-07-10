"""전체 한글 패치 빌드 오케스트레이션 — 단일 최종 이미지 생성.

체인: reinsert(대사+폰트) → gfx_cards(챕터카드) → sys_ui(시스템 UI)
     → work/Eiyuu Densetsu (KR).bin/.cue  (테스트는 이 하나만)

중간 산출물(KR Pilot / KR UI)은 빌드 후 삭제한다. 테스트 이미지를 하나로 유지.
오프닝(patch_opening.py)은 OPEN1.EXE 폰트 미해결(BIOS 한자 폰트 추정)로 체인에서 제외.
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
STALE = ["Eiyuu Densetsu (KR OP)", "Eiyuu Densetsu (Len Test)",
         "Eiyuu Densetsu (Test Patch)"]


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
    run("patch_sys_ui.py")

    shutil.copyfile(KR_UI, FINAL)
    write_cue(FINAL_CUE, os.path.basename(FINAL))
    for stem in INTERMEDIATES + STALE:
        rm(stem)
    print(f"\n완료: {FINAL}\n테스트는 이 하나만: {os.path.basename(FINAL_CUE)}")


if __name__ == "__main__":
    main()
