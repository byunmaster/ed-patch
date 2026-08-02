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

from common import BUILD_DIR, ROOT, write_cue

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


# ── 절대 안 바뀌어야 하는 구간 (파일 오프셋, 반열림) ──────────────────────
# 최종 이미지를 원본과 byte 대조한다. **실패로 끝난 빌드가 남긴 낡은 이미지를 정상으로
# 오해**하거나, 클리어 범위를 잘못 잡아 남의 자료를 지우는 사고를 잡는다 — 둘 다 실제로
# 겪었다(2026-08-02: OPEN1 포인터 테이블 0x938~0x973 말소).
# mode: "bytes" = 통째로 동일 · "script" = 텍스트 포인터 슬롯만 예외(재packing 으로 정당히 바뀜)
IMMUTABLE = {
    # (LBA, 크기): [(이름, 시작, 끝, mode), …]
    (69, 96256): [
        ("OPEN1 포인터 테이블", 0x938, 0x974, "bytes"),
        ("OPEN1 ED2 오프닝 내레이션", 0xEF0, 0x1B14, "bytes"),
        ("OPEN1 표시 스크립트 커맨드", 0x145A0, 0x147BC, "script"),
    ],
}


def check_immutable():
    """선언한 무변경 구간이 원본과 같은지 확인한다(다르면 빌드 실패)."""
    from common import extract

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
                    if 0x80010000 <= ow < 0x80011000:
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


def rm(stem):
    for ext in (".bin", ".cue"):
        p = os.path.join(BUILD_DIR, stem + ext)
        if os.path.exists(p):
            os.remove(p)


def main():
    # ⚠ 테스트 이미지는 **항상 하나만** 남긴다(CLAUDE.md). 중간 산출물은 체인 끝에서 지우는데,
    # 도구를 단독 실행하면(예: reinsert 만 돌려 A/B) 그게 남는다 — 시작할 때도 한 번 치운다.
    for stem in INTERMEDIATES + STALE:
        rm(stem)
    for p in glob.glob(os.path.join(BUILD_DIR, "*.failed")):  # 지난 실패 잔재
        os.remove(p)

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
    check_immutable()
    print(f"\n완료: {FINAL}\n테스트는 이 하나만: {os.path.basename(FINAL_CUE)}")


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
