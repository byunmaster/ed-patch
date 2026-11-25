"""전 몬스터·보스 전투 완료 시험(마스터 10-24) — 원판 「バトルテスト」 마을(패키지 16~19)의 번호판으로 전투를 골라 **끝까지 도는지**만 본다(촬영 없음 · 멈춤만 기록).

길(롬 수정 0, 제품 롬 그대로): 필드 SELECT 1초 → WARP → 「디버그 마을」(ETC. TEST, 패키지 2) → 왼쪽 길 NPC 셋째(말 걸면 「序章１章バトル / ２章３章バトル / ４章バトル / 終章バトル」 메뉴) → 패키지 16~19 마을 → 첫 NPC(번호판 000~) → 번호 → 전투.
힘 보강: 디버그 메뉴 LVL 항목을 I 로 연타(레벨 +1, 약 10번에 한 레벨 — 레벨 96 에서 HP 9999).
통과 = 전투 뒤 시험 마을(필드)로 돌아옴(검은 배경 비율로 판정) · 멈춤 = 프레임 상자 안에 못 돌아옴(화면 한 장 + 상태 저장).
한계: 「전투 → 승리 처리 → 시험 마을 복귀」까지다 — 보스 전투 뒤 실제 이벤트로 넘어가는 경로는 못 본다.

    python3 battle_run.py --iso <ed2.iso> --out <폴더> [--pkgs 16,17] [--budget 5000] [--levels 700]
촬영 칸을 줄 서서 쓴다: `sh scripts/capture.sh python3 games/pce-ed2/tools/battle_run.py …`
"""

import argparse
import ctypes as C
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pceview
from PIL import Image

PKG_CHOICE = {16: 0, 17: 1, 18: 2, 19: 3}  # 시험 마을 NPC 메뉴 순서
GRID_COLS = 5


def step_up(e) -> None:
    e.hold("up")
    e.run(8)
    e.hold(None)
    e.run(10)


def black_frac(img) -> float:
    """전투 화면 위쪽(몬스터 자리) 검은 비율 — 필드는 풀·길이라 낮다."""
    r = img[60:125, 36:200].astype(int)
    return float(((r.sum(axis=2)) < 60).mean())


def window_open(img) -> bool:
    """필드 위 창(디버그 메뉴 · 대사 · 메인 메뉴 — 주황 테두리) 여부."""
    r = img[45:215, 28:215].astype(int)
    return (
        int(((r[..., 0] > 200) & (r[..., 1] > 40) & (r[..., 1] < 130) & (r[..., 2] < 70)).sum())
        > 150
    )


def close_windows(e, limit: int = 12) -> None:
    """창이 보이는 동안만 II — 창이 없을 때 II 는 메인 메뉴를 연다."""
    for _ in range(limit):
        if not window_open(e.frame_img):
            return
        e.press("ii", 3, 25)


def has_text_box(img) -> bool:
    """대사·로그 창(주황 테두리) 여부."""
    r = img[135:215, 28:215].astype(int)
    return (
        int(((r[..., 0] > 200) & (r[..., 1] > 40) & (r[..., 1] < 130) & (r[..., 2] < 70)).sum())
        > 150
    )


def to_etc_town(e) -> None:
    """서장 필드 → 디버그 메뉴 → WARP → 디버그 마을."""
    e.hold("select")
    e.run(70)  # 진입키는 1초(60프레임) 이어서 — 짧게 누르면 안 열린다
    e.hold(None)
    e.run(30)
    e.press("i", 4, 40)
    e.press("i", 4, 200)
    e.run(200)


def level_up(e, presses: int) -> None:
    """디버그 메뉴 LVL 항목을 I 로 연타한다(레벨 +1 / 약 10번)."""
    e.hold("select")
    e.run(70)
    e.hold(None)
    e.run(30)
    e.press("down", 3, 12)
    for _ in range(presses):
        e.press("i", 3, 22)
    close_windows(e)


def enter_pkg(e, pkg: int) -> None:
    """디버그 마을의 NPC 셋째에게 말 걸어 시험 마을(패키지 16~19)로."""
    for _ in range(7):
        step_up(e)
    e.press(
        "left", 3, 30
    )  # 닿기만 해도 4지 메뉴가 열린다(I 는 필요 없다 — 한 번 더 누르면 첫 항목이 골라진다)
    for _ in range(PKG_CHOICE[pkg]):
        e.press("down", 4, 20)
    e.press("i", 3, 10)
    e.run(320)


def open_grid(e) -> None:
    """시험 마을 첫 NPC 에게 말 걸어 번호판을 연다."""
    for _ in range(3):
        step_up(e)
    e.press("left", 3, 15)
    e.press("i", 3, 40)


def pick(e, n: int) -> None:
    for _ in range(n // GRID_COLS):
        e.press("down", 3, 8)
    for _ in range(n % GRID_COLS):
        e.press("right", 3, 8)
    e.press("i", 3, 10)


class PtrProbe:
    """게임의 호출 스택 저장 포인터(뱅크 0x68 +0x1563)를 상태 덩어리에서 읽는다 — `layout.GAME_SCRATCH` 의 깊이 근거(전투 중 최댓값)."""

    def __init__(self, e, iso: str):
        prog = pceview.iso_pkg(iso, 130, sectors=40)
        b = self.blob(e)
        self.base = None
        for off in range(0x1800, 0x7000, 0x400):
            k = prog[off : off + 64]
            if len(set(k)) < 12:
                continue
            i = b.find(k)
            if i >= 0 and b.find(k, i + 1) < 0:
                self.base = i - off
                break
        if self.base is None:
            raise RuntimeError("뱅크 0x68 위치를 상태 덩어리에서 못 찾았다")

    @staticmethod
    def blob(e) -> bytes:
        n = e.core.retro_serialize_size()
        buf = C.create_string_buffer(n)
        e.core.retro_serialize(buf, n)
        return buf.raw

    def read(self, e) -> int:
        return self.blob(e)[self.base + 0x1563]


def fight(
    e, budget: int, shots: tuple[Path, str] | None = None, probe: "PtrProbe | None" = None
) -> tuple[str, int, int]:
    """번호를 고른 뒤 전투를 돌린다. (결과, 쓴 프레임, 스택 포인터 최댓값) — 결과: 통과 · 멈춤 · 게임오버(필드로 못 돌아오고 시작 화면류)."""
    used = 0
    seen_battle = False
    pmax = 0
    while used < budget:
        e.press("i", 3, 17)
        used += 20
        img = e.frame_img
        if probe:
            pmax = max(pmax, probe.read(e))
        if shots and used in (100, 240, 400):
            Image.fromarray(img).save(shots[0] / f"shot_{shots[1]}_{used}.png")
        bf = black_frac(img)
        if bf > 0.5:
            seen_battle = True
        elif seen_battle and bf < 0.15 and not has_text_box(img):
            e.run(40)
            used += 40
            if black_frac(e.frame_img) < 0.15 and not has_text_box(e.frame_img):
                return "통과", used, pmax
    return "멈춤", used, pmax


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iso", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--bram", default="/root/save/pce-ed2/ed2.e42dc6b34ced533663e83bcdb21e7a7d.sav")
    ap.add_argument("--pkgs", default="16,17,18,19")
    ap.add_argument("--counts", default="16:30,17:30,18:20,19:18")
    ap.add_argument("--budget", type=int, default=5000)
    ap.add_argument("--levels", type=int, default=700, help="LVL 연타 횟수(약 10번 = 1레벨)")
    ap.add_argument(
        "--shots", action="store_true", help="전투 시작 100·240·400 프레임 화면을 저장(검증용)"
    )
    ap.add_argument(
        "--ptr", action="store_true", help="전투마다 스택 저장 포인터 최댓값을 잰다(느려진다)"
    )
    ap.add_argument("--only", default="", help="pkg:번호,… 만")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cue = str(Path(a.iso).with_suffix(".cue"))
    counts = {int(k): int(v) for k, v in (x.split(":") for x in a.counts.split(","))}
    only = {tuple(map(int, x.split(":"))) for x in a.only.split(",") if x}
    e = pceview.boot_field(cue, a.bram)
    probe = PtrProbe(e, a.iso) if a.ptr else None
    to_etc_town(e)
    level_up(e, a.levels)
    e.save(str(out / "etc_strong.state"))
    rows = []
    for pkg in [int(x) for x in a.pkgs.split(",")]:
        e.load(str(out / "etc_strong.state"))
        enter_pkg(e, pkg)
        open_grid(e)
        gstate = out / f"grid_{pkg}.state"
        e.save(str(gstate))
        for n in range(counts[pkg] - 1, -1, -1):  # 보스(큰 번호)부터
            if only and (pkg, n) not in only:
                continue
            e.load(str(gstate))
            pick(e, n)
            t0 = time.time()
            res, used, pmax = fight(
                e, a.budget, (out, f"{pkg}_{n:03d}") if a.shots else None, probe
            )
            rows.append((pkg, n, res, used, pmax))
            print(f"{pkg}:{n:03d} {res} {used}f ptr={pmax:#x} {time.time() - t0:.0f}s", flush=True)
            if res != "통과":
                Image.fromarray(e.frame_img).save(out / f"stall_{pkg}_{n:03d}.png")
                e.save(str(out / f"stall_{pkg}_{n:03d}.state"))
            with open(out / "results.tsv", "w") as f:
                f.write("패키지\t번호\t결과\t프레임\t스택포인터최대\n")
                f.writelines("\t".join(map(str, r)) + "\n" for r in rows)
    ok = sum(1 for r in rows if r[2] == "통과")
    print(f"합계 {len(rows)} · 통과 {ok} · 멈춤 {len(rows) - ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
