"""sfc-ed2 한국어 인코딩 — 번역 표기 → 롬 바이트, 글리프 배정.

번역 문안은 `textmap/*.json`(커밋되는 우리 문안 — 원문은 안 싣는다. 구간은 시작 주소 + 원문 바이트 sha1 앞 8자로 짝을 지킨다).
표기: 글자 그대로 · 개행 = `$01` · `<hh>` = 제어 바이트 · `<E0:n>` `<E1:n>` = 사전 참조 · `<pad:N>` = 지금까지 N 바이트가 되게 전각 공백으로 채움.
  · ASCII `$21~$7E`·공백 `$20` = 반각 1바이트(반각 글꼴) — 숫자·영문·`!?.,` 는 반각이 번역 규칙(공백·ASCII 부호 반각)
  · 그 밖(한글·`…`·`「」`·전각 공백 등) = 전각 2바이트 글리프, 색인은 `allocate` 가 배정한다
글리프 배정은 **결정적**이다: 쓰인 글자를 코드포인트 순으로 정렬해 빈 색인에 오름차순으로 채운다.
빈 색인 = 원본 글리프 뒤(`FIRST_FREE`=1284 ~ 2047) — 번역이 끝나 일본어 글자가 안 남으면 그 자리도 쓸 수 있다(`census` 가 서면, 미구현).
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common

TEXTMAP = common.GAME_DIR / "textmap"
FIRST_FREE = 1284
LAST_SLOT = 0x7EF  # 0x7F0~0x7F3 은 가짜 조사 글리프(런타임 조사 훅)
FULLWIDTH_SPACE = "　"

HALF_OK = set(" !?-.,0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")  # 반각 글꼴에 실제 모양이 있는 ASCII
JOSA_PAIRS = (("은", "는"), ("이", "가"), ("을", "를"), ("과", "와"))  # 런타임 조사 쌍(받침 있음, 없음) — patches.JOSA_BASE+k
JOSA_CHARS = {c for p in JOSA_PAIRS for c in p}
_RUN = re.compile(r"\{\*([^{}/]+)/([^{}/]+)\}")
_TOK = re.compile(r"\{\*[^{}/]+/[^{}/]+\}|<(?:E([01]):(\d+)|([0-9a-fA-F]{2}(?: [0-9a-fA-F]{2})*)|pad:(\d+))>|(.)", re.S)


def load(name: str) -> dict:
    p = TEXTMAP / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def chars_of(text: str) -> set[str]:
    """전각 글리프가 필요한 글자."""
    out = set(JOSA_CHARS) if _RUN.search(text) else set()
    for m in _TOK.finditer(text):
        c = m.group(5)
        if c is not None and c != "\n" and not (0x20 <= ord(c) <= 0x7E):
            out.add(c)
    return out


class Chars(dict):
    """글자 → 쓰인 문안 수. `|=` 로 집합을 더하면 센다(희귀 글자부터 밀어내려고)."""

    def __ior__(self, other):
        for c in other:
            self[c] = self.get(c, 0) + 1
        return self


DROPPED: list[str] = []  # 빈 색인이 모자라 못 배정한 글자(희귀한 것부터) — 번역 중간 빌드에서만 생긴다. build.py --strict 는 이게 있으면 죽는다


def allocate(chars, slots=None, lenient=False) -> dict[str, int]:
    """글자 → 글리프 색인. slots = 쓸 수 있는 색인 목록(오름차순) — 기본은 일본어와 안 겹치는 빈 자리. 글자는 코드 포인트 순(결정적).
    lenient 면 자리가 모자랄 때 덜 쓰이는 글자를 공백(0)으로 두고 DROPPED 에 적는다(번역이 끝나 일본어 자리가 풀리기 전의 중간 빌드)."""
    freq = chars if isinstance(chars, dict) else {}
    cs = sorted(set(chars) - {FULLWIDTH_SPACE})
    slots = list(slots) if slots is not None else list(range(FIRST_FREE, LAST_SLOT + 1))
    DROPPED.clear()
    if len(cs) > len(slots):
        if not lenient:
            raise SystemExit(f"글리프 {len(cs)}자 > 빈 색인 {len(slots)}")
        order = sorted(cs, key=lambda c: (-freq.get(c, 0), c))
        DROPPED.extend(order[len(slots) :])
        cs = sorted(order[: len(slots)])
    alloc = {c: slots[i] for i, c in enumerate(cs)}
    for c in DROPPED:
        alloc[c] = 0
    alloc[FULLWIDTH_SPACE] = 0  # 원본 글리프 0 = 전각 공백
    return alloc


def encode(text: str, alloc: dict[str, int]) -> bytes:
    out = bytearray()
    for m in _TOK.finditer(text):
        if m.group(0).startswith("{*"):
            r = _RUN.fullmatch(m.group(0))
            k = JOSA_PAIRS.index((r.group(1), r.group(2)))
            out += (0x8000 + 0x7F0 + k).to_bytes(2, "big")
        elif m.group(1) is not None:
            out += bytes([0xE0 + int(m.group(1)), int(m.group(2))])
        elif m.group(3) is not None:
            out += bytes(int(x, 16) for x in m.group(3).split())
        elif m.group(4) is not None:  # `<pad:N>` — 지금까지 N 바이트가 되게 전각 공백($8000)·반각 공백으로 채운다(고정 칸 정렬)
            n = int(m.group(4))
            if len(out) > n:
                raise SystemExit(f"<pad:{n}> 인데 이미 {len(out)}B")
            while n - len(out) >= 2:
                out += b"\x80\x00"
            if n - len(out) == 1:
                out.append(0x20)
        else:
            c = m.group(5)
            if c == "\n":
                out.append(0x01)
            elif 0x20 <= ord(c) <= 0x7E:
                if c not in HALF_OK:
                    raise SystemExit(f"반각 글리프가 없는 ASCII {c!r} — 전각 글자를 쓰거나 반각 글꼴(patches.HALF_GLYPHS)에 그린다")
                out.append(0x22 if c == "?" else ord(c))
            else:
                out += (0x8000 + alloc[c]).to_bytes(2, "big")
    return bytes(out)
