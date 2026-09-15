"""조판 지문 — 이 게임 몫 (`scripts/check/typeset_fingerprint.py` 가 부른다).

## 왜 이 파일이 게임 아래 있나

공용 도구는 「지문을 대조하고 얼린다」만 알고, **「이 게임의 화면 문안이 무엇에 기대나」**는
게임마다 다르다(루트 `CLAUDE.md` 「게임 얘기를 이 파일에 쓰지 않는다」).

## `ss-ed1+2` 를 그대로 베끼지 않은 이유 — **값으로 확인했다**

관리자가 「같은 새턴·같은 조판기라 그쪽이 제일 싸게 베낄 수 있다」고 알렸는데, 둘 다
**엔진이 글자 단위로 접는다**는 점은 같지만 **숫자 계약이 다르다**(ss-ed1+2 는 전각 14 자 ·
7 행, ss-ed3 는 전각 17 슬롯 · 3 행 — `docs/status.md` 4 절). **그리고 무엇보다, ss-ed3 의
줄바꿈은 `shared/` 를 안 쓴다** — `tools/typeset.py` 가 전부 게임 로컬 코드다(krwrap 같은
공용 조판기가 없다). 실측: `shared/text/krwrap.py` 가 바뀐 라운드 ⑥ 직전 리베이스에서
**재빌드 지문(디스크 sha1)이 두 장 다 그대로**였다(devlog 참조) — ss-ed1+2 식 지문을 그대로
베꼈다면 **krwrap 을 조판기에 태우는 함수가 없어 곧바로 죽었을 것**이다.

## 무엇을 재나 — 새턴 ED3 가 `shared/` 에서 쓰는 건 **하나뿐**

    shared.text.josa.batchim   조사 훅이 굽는 종성 비트표 → 이름 뒤 을(를)·은(는)·이(가)

⚠ **`shared.text.sjis`·`shared.disc`·`shared.fonts` 는 안 잰다** — 이것들은 **원문을 읽거나
구조를 다루는 데만** 쓰인다(덤프·재삽입 좌표). 우리 한글 문안을 만들거나 화면에 놓는 자리에
안 들어간다 — 흔들려도 **다른 게이트**(라운드트립·섹터 무결성)가 먼저 운다.
⚠ **`shared/glossary/` 도 아직 안 읽는다**(고유명사는 `glossary_manual.json`, 승격은
main 머지 시점 — `docs/status.md` 「남은 일」 4). 승격되면 이 지문에 구역을 더한다.

그래서 구역은 둘로 가른다:

  script/*.json 전량   화면에 나갈 **완성 문안**(엔진이 접는 건 로컬 코드라 문안 자체가
                       이미 최종형이다 — 우리가 굽는 조판기를 또 태울 이유가 없다)
  시스템/조사표         `batchim()` 을 **전체 완성형 슬롯**에 태운 결과. 여기가 흔들리면
                       `/0.BIN` 에 굽는 비트표가 바뀌어 화면 조사가 조용히 갈린다

⚠ 재는 건 **바이트가 아니라 문안**이다 — 재삽입 좌표(오프셋·LBA)는 안 본다. 그건 빌드가
  매번 다시 재고 다른 게이트가 잡는다. 좌표까지 재면 원본 여유가 한 칸만 달라져도 지문이
  울어 아무도 안 보는 알림이 된다(ss-ed1+2 문서의 같은 경고).
"""

import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
import common as C
import patch_josa_hook as J

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")


def _flatten(v, path, acc):
    """JSON 값을 `(경로, 문자열)` 쌍으로 편다 — `_` 로 시작하는 키(주석·메타)는 뺀다."""
    if isinstance(v, str):
        acc.append(f"{path}\x00{v}")
    elif isinstance(v, dict):
        for k, vv in v.items():
            if not k.startswith("_"):
                _flatten(vv, f"{path}/{k}", acc)
    elif isinstance(v, list):
        for i, vv in enumerate(v):
            _flatten(vv, f"{path}/{i}", acc)
    # 그 외(숫자·불리언·None)는 화면 문안이 아니라 조판과 무관 — 뺀다


def _h(parts):
    h = hashlib.sha1()
    for p in sorted(parts):
        h.update(p.encode())
        h.update(b"\x01")
    return h.hexdigest()[:12]


def fingerprint():
    """`{구역: sha1[:12]}` — 화면에 나갈 문안 전량 + 조사표."""
    out = {}
    paths = sorted(glob.glob(os.path.join(SCRIPT_DIR, "*.json"))) + sorted(
        glob.glob(os.path.join(SCRIPT_DIR, "book", "*.json"))
    )
    for p in paths:
        name = os.path.relpath(p, SCRIPT_DIR)
        if name == "sys_coverage_accept.json":
            continue  # 사유 대장이지 화면 문안이 아니다
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
        acc = []
        _flatten(doc, name, acc)
        if acc:
            out[name] = _h(acc)

    # 🔴 조사표 — `shared.text.josa.batchim` 이 흔들리면 이 값이 운다
    out["시스템/조사표"] = hashlib.sha1(J.bit_table()).hexdigest()[:12]
    return out


if __name__ == "__main__":
    # 🔴 인자를 안 받는다 — 조용히 삼키지 않는다(ss-ed1+2 typeset_fp.py 와 같은 함정).
    if len(sys.argv) > 1:
        sys.exit(
            f"  ⛔ 이 파일은 인자를 안 받는다 ({' '.join(sys.argv[1:])}) — 값을 보여 줄 뿐이다.\n"
            "     얼리려면: python3 scripts/check/typeset_fingerprint.py --game ss-ed3 --freeze"
        )
    fp = fingerprint()
    print(f"  {len(fp)}구역")
    for k, v in sorted(fp.items()):
        print(f"  {v}  {k}")
