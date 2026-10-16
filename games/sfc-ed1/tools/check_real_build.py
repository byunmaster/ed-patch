"""제품 롬을 **실제로 굽는** 게이트 — `check.sh` 의 rc 0 이 「보고하는 그 롬」을 뜻하게 한다.

`build.py --check`·`--project` 는 쓰기 직전까지만 간다. 정본 이름이 칸보다 길어 쓰기 경로(전투 UI 등)가
죽어도 rc 0 이고 낡은 롬이 그대로 남아 「초록」으로 보고될 수 있다(md-ed2 발견, 10-18).
그래서 여기서: ① 낡은 이미지·`.failed` 를 먼저 지우고 ② `build.py --kr` 을 제품 꼬리표로 돌려
③ 종료 코드 0 · `.failed` 없음 · 이미지 하나 · manifest 해시 일치 가 아니면 실패한다.
시험용 환경 변수(`ED_DEBUG`·`ED_BUILD_TAG`·`ED_VWF`)는 걷어 낸다 — 시험 칸에 굽고 초록을 말하면 안 된다.

  python3 tools/check_real_build.py
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KR_NAME = "Dragon Slayer - Eiyuu Densetsu (KR).sfc"
TEST_ENV = ("ED_DEBUG", "ED_BUILD_TAG", "ED_VWF")


def clean(d: Path) -> int:
    """낡은 이미지·실패 산출물을 지운다(manifest 포함). 지운 수."""
    n = 0
    if d.is_dir():
        for p in [*d.glob("*.sfc*"), d / "manifest.json"]:
            if p.is_file():
                p.unlink()
                n += 1
    return n


def verify(d: Path, rc: int) -> str | None:
    """굽고 난 뒤 칸을 본다. 문제면 사유, 정상이면 None."""
    if rc != 0:
        return f"build.py --kr 종료 코드 {rc}"
    failed = sorted(p.name for p in d.glob("*.failed"))
    if failed:
        return f"실패 산출물 {failed}"
    imgs = sorted(p.name for p in d.glob("*.sfc"))
    if imgs != [KR_NAME]:
        return f"산출물이 기대와 다르다: {imgs}"
    mf = d / "manifest.json"
    if not mf.is_file():
        return "manifest.json 이 없다"
    want = json.loads(mf.read_text(encoding="utf-8")).get("output_sha1")
    got = hashlib.sha1((d / KR_NAME).read_bytes()).hexdigest()
    if want != got:
        return f"manifest 해시 {want} ≠ 파일 {got}"
    return None


def main() -> int:
    sys.path.insert(0, str(HERE))
    for k in TEST_ENV:
        os.environ.pop(k, None)
    import common

    d = common.BUILD_DIR / common.BUILD_TAG
    clean(d)
    rc = subprocess.run(
        [sys.executable, str(HERE / "build.py"), "--kr"], stdout=subprocess.DEVNULL, check=False
    ).returncode
    why = verify(d, rc)
    if why:
        print(f"❌ 제품 롬 실빌드 실패 — {why}")
        return 1
    print(
        f"제품 롬 실빌드 OK: {KR_NAME} sha1 {hashlib.sha1((d / KR_NAME).read_bytes()).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
