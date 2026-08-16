#!/usr/bin/env python3
"""**블록 추출기가 못 본 씬 문자열**을 제자리 치환한다 — 마지막 잔여 일본어.

**왜.** 재삽입은 씬을 「블록」으로 갈라 다루는데, 대사가 **포인터 테이블·이진 덩어리
한복판에 박혀 있으면 블록으로 안 잡힌다.** 그런 문자열은 배정도 조판도 못 받고 화면에
일본어로 그대로 나간다. ED2 를 체인에 올렸을 때 아홉이 그랬다(2026-08-16).

`check_scn_jp_left` 는 이걸 「원문 대조 실패(블록 경계 밖일 수 있다)」로 보고한다 —
같은 원문을 가진 **블록이 하나도 없어서**(동일블록 0) 사본 복사로도 못 메운다.

**방법은 플레이트와 같다.** 널종단 문자열을 **길이 안에서** 제자리 치환한다. 바이트가
한 칸도 안 밀리므로 포인터·구조를 못 깨뜨린다. 넘치면 assert 로 죽는다 — 조용히
건너뛰면 화면에 일본어가 남는데 빌드는 성공하는, 이 레포가 가장 경계하는 꼴이 된다.

⚠ **원문은 리포에 안 남긴다**(저작권 규칙). `script/ED2_ORPHANS.json` 은 JP sha1 앞
10자를 키로 쓰고 값은 **우리 문안**뿐이다 — 원문은 소장 원본에서 파생해 대조한다.

  python3 tools/patch_scn_orphans.py          # 이미지 제자리 치환
"""

import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("LOCK_BYPASS", "1")

import hangul_map as H
from common import BUILD_DIR, extract, write_user_data
from patch_sys_ui import _scn_layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE = os.path.join(ROOT, "script", "ED2_ORPHANS.json")
IMG = f"{BUILD_DIR}/Eiyuu Densetsu (KR).bin"


def _enc(kr):
    """한글은 슬롯 SJIS, 나머지(`%c`·개행·부호)는 원래 바이트."""
    out = bytearray()
    for ch in kr:
        if "가" <= ch <= "힣":
            out += H.encode_kr(ch)
        elif ch == "\n":
            out.append(0x0A)
        else:
            out += ch.encode("shift_jis")
    return bytes(out)


def _by_key(data):
    """이미지 안의 널종단 조각 → {sha1키: 문자열}.

    ⚠ **앞을 널로 못 자른다.** 대상이 「이진 덩어리 한복판에 박힌 문자열」이라 앞 널부터
    잘라 내면 이진이 딸려 와 해시가 안 맞는다(9개 중 1개만 걸렸다). 끝은 널이 맞으므로
    **꼬리를 여러 시작점에서 떠서** 전부 해시한다 — 조각이 짧아 비용은 무시할 만하다.
    """
    found = {}
    for part in bytes(data).split(b"\x00"):
        # ⚠ 상한을 240B 로 잡았더니 셋이 빠졌다(앞 이진까지 288~362B, 실측).
        #   대상 문자열 자체는 짧아도 **앞에 붙은 이진이 길다** — 조각 길이로 자르면 안 된다.
        if not (4 <= len(part) <= 1024):
            continue
        for i in range(len(part) - 3):
            try:
                s = part[i:].decode("cp932")
            except UnicodeDecodeError:
                continue
            found.setdefault(hashlib.sha1(s.encode()).hexdigest()[:10], s)
    return found


def main():
    with open(TABLE, encoding="utf-8") as f:
        kr_by_key = json.load(f)
    total = 0
    with open(IMG, "r+b") as f:
        for name, lba, size in _scn_layout():
            # ⚠ **ED2 씬만** 본다. 표가 ED2 것인데 전 씬에 돌렸더니 같은 원문(보물상자
            # 정형문 등)이 ED1 에도 있어 **ED1 이미지가 바뀌었다**(2026-08-16 실측:
            # ED1SCN1·SCN4 sha1 변화). ED1 은 조판을 거친 정식 경로로 이미 처리되는
            # 층이라, 이 거친 제자리 치환이 끼어들면 안 된다.
            if not name.startswith("ED2"):
                continue
            data = bytearray(extract(lba, size, path=IMG))
            here = _by_key(data)
            n = 0
            for key, kr in kr_by_key.items():
                jp = here.get(key)
                if jp is None:
                    continue
                jb, kb = jp.encode("cp932"), _enc(kr)
                assert len(kb) <= len(jb), f"{name} {kr[:12]!r}: {len(kb)}B > {len(jb)}B"
                for m in list(re.finditer(re.escape(jb), bytes(data))):
                    i, e = m.start(), m.end()
                    if e < len(data) and data[e] != 0:
                        continue  # 널종단이 아니면 남의 문자열 한복판이다
                    data[i:e] = kb.ljust(len(jb), b"\x00")
                    n += 1
            if n:
                secs = write_user_data(f, lba, data, label=f"씬 잔여 문자열 ({name})")
                print(f"  {name}: 잔여 문자열 {n}곳 (섹터 {secs}개)")
                total += n
    print(f"씬 잔여 문자열 치환 {total}곳")
    return 0


if __name__ == "__main__":
    sys.exit(main())
