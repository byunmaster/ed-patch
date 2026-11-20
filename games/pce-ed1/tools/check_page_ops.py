"""쪽 옵코드 중복 대조 — 우리 조립(`translate.compose`)에 **글 없이 이어진 쪽 넘김 둘**(`05 05` · `05 03` · `03 05` · `03 03`)이 원문 메시지보다 많은 곳을 센다.

🔴 11-20 마스터 QA(리버시 「아예 빈 대사창」): 번역 문안 끝에 `\\f`(쪽 넘김)를 달았는데 원문 끝에도 쪽 옵코드(`05`)가 있어 조립이 **둘 다 냈다**(`개일세.<05><05>`) —
키 대기 ▽ 가 두 번 떠서 둘째가 빈 창이었다. 같은 부류(문안 끝·중간의 \\f 가 원문 옵코드와 겹침)를 정적으로 세어 늘면 실패한다.

    python3 games/pce-ed1/tools/check_page_ops.py        # 원본 필요(씬 블록) — check.sh 가 부른다
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

PAGE = {0x05, 0x03}


def ctrl_runs(b: bytes) -> list[int]:
    """바이트열 → 제어 바이트 순서(글자·인자는 `X` 로 접는다). 두 바이트 글자(리드 ≥ 0x24)는 건너뛴다."""
    out, i = [], 0
    while i < len(b):
        c = b[i]
        if c >= 0x24:
            out.append(-1)
            i += 2
            continue
        out.append(c)
        i += 2 if c == 0x09 else 1
    return out


def dup_pages(seq: list[int]) -> int:
    """글(-1)·다른 옵코드 없이 이어진 쪽 넘김 쌍의 수."""
    return sum(1 for a, b in zip(seq, seq[1:]) if a in PAGE and b in PAGE)


def page_before_end(seq: list[int]) -> int:
    """쪽 넘김 바로 뒤에 종료(`00`·`06`·`07`)가 오는 수 — 원문에 없는 끝 쪽 넘김이 생기면 마지막에 빈 창이 한 번 더 뜬다."""
    return sum(1 for a, b in zip(seq, seq[1:]) if a in PAGE and b in (0x00, 0x06, 0x07))


def header_join(m, cs: list[int], last_px: int = 0) -> bool:
    """이름이 따로 한 줄(머리 개행)인 메시지의 본문이 원문에서 꽉 찬 줄로 문장을 끝냈는데(자동 줄넘김에 기대 다음 이름이 새 줄에서 시작), 우리 조립이 개행·쪽 넘김·종료 없이 끝나는가 — 마스터 11-21 「노인 화자명이 개행되어야 해」."""
    if m.speaker is None or not m.tokens or m.tokens[0] != ("op", 1) or any(t == ("op", 1) for t in m.tokens[1:]):
        return False
    if m.tokens[-1] is not None and isinstance(m.tokens[-1], tuple):  # 끝 옵코드가 있으면(쪽·종료·개행) 원문이 정한다
        return False
    body = m.jp.lstrip("\n")
    if len(body) < typeset.FULL or body.rstrip("\n")[-1:] not in "。？！":
        return False
    return bool(cs) and cs[-1] == -1 and last_px <= typeset.FULL * 12 - 12  # 마지막 줄이 이미 꽉 차면 인터프리터가 스스로 넘긴다


def orig_seq(m: M.Message) -> list[int]:
    seq: list[int] = []
    for t in m.tokens:
        seq.append(t[1] if isinstance(t, tuple) else -1)
    return seq


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
                if tr is None or (sid, m.key) in seen or tr.get("raw"):
                    continue
                seen.add((sid, m.key))
                n += 1
                out = T.compose(m, tr, btab, speakers)
                got, want = dup_pages(ctrl_runs(out)), dup_pages(orig_seq(m))
                cs = ctrl_runs(out)
                inv = {v: k for k, v in btab.items()}
                txt, i = [], 0
                while i < len(out):
                    if out[i : i + 2] == font.HALF_SPACE:
                        txt.append(" ")
                        i += 2
                    elif out[i : i + 2] in inv:
                        txt.append(inv[out[i : i + 2]])
                        i += 2
                    elif out[i] in (0x01, 0x05, 0x03):
                        txt.append("\n")
                        i += 1
                    else:
                        i += 1
                last_px = T._line_px("".join(txt).split("\n")[-1])
                if header_join(m, cs, last_px):
                    errs.append(f"씬 {sid} {m.key}: 이름 줄 뒤 꽉 찬 본문이 끝 개행 없이 끝나 다음 화자 이름이 같은 줄에 붙는다(원문은 자동 줄넘김): {tr['t'][-24:]!r}")
                if page_before_end(ctrl_runs(out)) > page_before_end(orig_seq(m)):
                    errs.append(f"씬 {sid} {m.key}: 원문에 없는 끝 쪽 넘김(종료 바로 앞) — 마지막에 빈 창이 한 번 더 뜬다: {tr['t'][-24:]!r}")
                if got > want:
                    errs.append(f"씬 {sid} {m.key}: 쪽 넘김이 글 없이 이어졌다 {got} > 원문 {want} — 문안 끝/중간의 \\f 가 원문 옵코드와 겹쳤다: {tr['t'][-24:]!r}")
    print(f"쪽 옵코드 중복 대조: 메시지 {n}개(씬×열쇠), 위반 {len(errs)}")
    return errs


def check_headers() -> list[str]:
    """열≠0 화자 머리 0 — 앞 메시지가 열린 채 이어지는데 다음 메시지가 화자 머리(이름 줄)로 시작하는 쌍이 **조립 파이프라인(`translate.header_nl_pass`) 뒤에도** 남아 있으면 실패
    (마스터 11-21 「그만둬!!세리오스」). 조립 직후(패스 전) 건수도 알린다."""
    chars = glyphdyn.forced_chars() | (T.all_glyph_chars() & set(font._order_canon()))
    table, _ = font.build_table(chars)
    errs: list[str] = []
    raw = 0
    for c in containers.scan():
        for b in c["blocks"]:
            sid = b["id"]
            trs = M.load_translations(sid)
            if not trs:
                continue
            btab, _ = glyphdyn.block_table(table, sid)
            typeset.set_scene(sid)
            speakers = M.load_speakers()
            edits = [(m, T.compose(m, trs[m.key], btab, speakers)) for m in T.with_added_speakers(sid, M.parse(b["data"])) if m.key in trs]
            raw += len(T.open_before_header(edits))
            for i in T.open_before_header(T.header_nl_pass(edits)):
                errs.append(f"씬 {sid} {edits[i][0].key[:8]}: 화자 머리가 앞 글 줄 끝(열≠0)에 붙는다")
    print(f"열≠0 화자 머리: 조립 직후 {raw}곳 → 패스 뒤 {len(errs)}곳")
    return errs


def main() -> int:
    errs = check() + check_headers()
    for e in errs[:80]:
        print("  ✗", e)
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
