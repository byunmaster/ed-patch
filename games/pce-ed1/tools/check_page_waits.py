"""쪽 대기(`05`·`03`) 종료 쌍 대조 — 원문 메시지가 `05 06`·`05 07`(쪽 대기 + 종료)로 끝나면 우리 조립(`translate.compose`)도 같은 쌍으로 끝나야 한다.

🔴 11-07 기능 투어(원판·우리 롬에 같은 입력): 상점 구매 확인(「…だね。どうもありがとう。」)이 원판은 ▽ 에서 키를 기다리는데 우리 롬은 문구가 번쩍 지나갔다 —
번역문 끝에 `\\f` 가 없어 `compose` 가 종료 앞의 `05` 를 안 냈다(트랙 전체 ~97블록). 호출한 코드가 종료 뒤에 따로 기다리지 않는 흐름(상점·여관·획득)에서만 드러난다.
쌍 수가 원판과 다르면 실패.

    python3 games/pce-ed1/tools/check_page_waits.py        # 원본 필요(씬 블록) — check.sh 가 부른다
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import containers
import font
import glyphdyn
import messages as M
import translate as T
import typeset

PAGE_T = (("op", 0x05), ("op", 0x03))


def pair_of(m: M.Message):
    if m.terminated and len(m.tokens) >= 2 and m.tokens[-2] in PAGE_T:
        return (m.tokens[-2][1], m.tokens[-1][1])
    return None


def check() -> list[str]:
    chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
    table, _ = font.build_table(chars)
    errs: list[str] = []
    seen: set[tuple[int, str]] = set()
    n = 0
    for c in containers.scan():
        for b in c["blocks"]:
            sid = b["id"]
            trs = M.load_translations(sid)
            if not trs:
                continue
            btab, _ = glyphdyn.block_table(table, sid)
            typeset.set_scene(sid)
            speakers = M.load_speakers()
            for m in M.parse(b["data"]):
                tr = trs.get(m.key)
                want = pair_of(m)
                if tr is None or want is None or (sid, m.key) in seen or tr.get("raw"):
                    continue
                seen.add((sid, m.key))
                n += 1
                got = T.compose(m, tr, btab, speakers)
                if tuple(got[-2:]) != want:
                    errs.append(f"scn{sid:03d} 메시지 {m.key}(블록 {m.start}): 원문 끝 {want[0]:02X} {want[1]:02X} → 조립 끝 {got[-2:].hex(' ')}")
    print(f"쪽 대기+종료 쌍으로 끝나는 메시지 {n}개 대조")
    return errs


if __name__ == "__main__":
    e = check()
    for x in e:
        print("✗", x)
    print("쪽 대기 쌍 위반", len(e))
    sys.exit(1 if e else 0)
