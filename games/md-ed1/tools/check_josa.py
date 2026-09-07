"""조사 일치 검사 — 훅이 붙을 자리에 붙었나, 병기가 남았나. (P2 상주 게이트)

    python3 tools/check_josa.py          # 자리 목록
    python3 tools/check_josa.py --check  # 게이트(알려진 예외 밖이면 실패)
    python3 tools/check_josa.py --freeze # 지금 남은 병기를 예외로 굳힌다

보는 축 넷:

1. **조사 코드의 짝** — `<eb p>` 는 바로 앞이 `<02>`(배우 이름), `<ec p>` 는 `<0e>`(아이템)이어야 한다.
   핸들러가 **이름을 스스로 찾아** 끝 글자를 보기 때문에, 앞의 삽입 코드가 다르면 엉뚱한 이름의
   종성으로 조사가 갈린다(`tools/josa.py`).
2. **p 범위** — 0 은/는 · 1 이/가 · 2 을/를.
3. **손으로 쓴 조사** — `<02>은` 처럼 이름 삽입 **바로 뒤에 조사 글자**가 오면 훅을 안 쓴 자리다.
   이름은 런타임에 바뀌므로 종성을 정적으로 맞출 수 없다.
4. **남은 병기** — `을(를)` 류. 이름 출처가 달라 아직 훅을 못 붙인 자리들이라 **목록으로 굳혀** 두고,
   늘면 운다.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

KNOWN_JSON = common.GAME_DIR / "textmap" / "josa_sites.json"
PAIRED = {"eb": "02", "ec": "0e"}
BYUNGI = re.compile(r"은\(는\)|이\(가\)|을\(를\)|과\(와\)|으로\(로\)")
HOOK = re.compile(r"<(eb|ec)(0[0-9a-f])>")
LITERAL = re.compile(r"<(02|0e|0b)>(은|는|이|가|을|를|과|와)(?![\w(])")


def canon() -> list[tuple[str, str, str]]:
    """[(파일, 자리, 문안)] — 정본 전량."""
    out = []
    # ⚠ `draft_md_only.json` 은 뺀다 — **골격 없는 조각**이라 `<0e>` 가 그 안에 없다(스트림 토큰이다).
    # 짝은 펼친 뒤에 본다 — `tools/draft.py --propose` 가 같은 규칙으로 검사한다.
    for f in sorted(
        f
        for f in glob.glob(str(common.GAME_DIR / "textmap" / "*.json"))
        + glob.glob(str(common.GAME_DIR / "script" / "*.json"))
        if Path(f).name != "draft_md_only.json"
    ):
        j = json.loads(Path(f).read_text(encoding="utf-8"))
        name = Path(f).name

        def walk(o, path, name=name):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k == "ours" and isinstance(v, str):
                        out.append((name, path, v))
                    else:
                        walk(v, f"{path}/{k}")
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    walk(v, f"{path}[{i}]")

        walk(j, "")
    return out


def scan() -> tuple[list[str], list[str]]:
    """(오류, 남은 병기 자리)."""
    errs, byungi = [], []
    for name, path, txt in canon():
        for m in HOOK.finditer(txt):
            kind, p = m.group(1), int(m.group(2), 16)
            if (p & 0x0F) > 2 or (kind == "ec" and p > 2):
                errs.append(
                    f"{name}{path}: <{kind}{m.group(2)}> — 하위 니블은 0~2, ec 는 상위 니블 없음"
                )
            before = txt[: m.start()]
            # `<eb>` 는 `<02>`(배우 포인터) 또는 `<09 nn>`(파티 번호로 그린 이름) 뒤에 온다 —
            # 후자는 p 의 상위 니블로 번호를 같이 준다(`tools/josa.py`).
            ok = before.endswith(f"<{PAIRED[kind]}>") or (
                kind == "eb"
                and re.search(r"<09[0-9a-f]{2}>$", before)
                and int(m.group(2), 16) >= 0x10
            )
            if not ok:
                tail = before[-6:]
                errs.append(f"{name}{path}: <{kind}…> 앞이 <{PAIRED[kind]}> 가 아니다 (…{tail})")
        for m in LITERAL.finditer(txt):
            errs.append(f"{name}{path}: 이름 뒤에 손으로 쓴 조사 <{m.group(1)}>{m.group(2)}")
        for m in BYUNGI.finditer(txt):
            byungi.append(f"{name}{path}:{m.group(0)}")
    return errs, sorted(byungi)


def main() -> None:
    errs, byungi = scan()
    known = json.loads(KNOWN_JSON.read_text(encoding="utf-8")) if KNOWN_JSON.exists() else []
    if "--freeze" in sys.argv:
        KNOWN_JSON.write_text(
            json.dumps(byungi, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        print(f"  {KNOWN_JSON}: 남은 병기 {len(byungi)} 굳힘")
        return
    new = [b for b in byungi if b not in known]
    print(
        f"  조사 — 병기 {len(byungi)} (알려진 {len(known)} · 새 {len(new)}) · 짝 오류 {len(errs)}"
    )
    for e in errs:
        print(f"    ❌ {e}")
    for b in new:
        print(f"    새 병기 {b}")
    if "--check" in sys.argv:
        if errs or new:
            raise SystemExit("조사 검사 실패 — 훅을 붙이거나 tools/check_josa.py --freeze")
    elif not errs:
        for b in byungi:
            print(f"    {b}")


if __name__ == "__main__":
    main()
