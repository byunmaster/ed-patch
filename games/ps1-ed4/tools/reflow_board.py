"""게시판 의뢰문 재조판 — 줄이 폭을 넘는 의뢰를 어절 단위로 다시 끊어 `ui_ed4.json`·`ui_frag_ed4.json` 에 쓴다(문안 불변, 줄 구분만).

    python3 tools/reflow_board.py            # 계획만 출력
    python3 tools/reflow_board.py --apply    # 쓴다
못 들어가는 의뢰(낱말을 줄여야만 드는 것)는 건드리지 않고 목록으로만 낸다 — 마스터 판정 대상.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_text as B
import hangul
import uitext


SUMMARY_PATH = os.path.join(B.common.ROOT, "board_summary_ed4.json")


def summaries():
    """의뢰 번호 → 새 요약(명사형 한 줄, 마스터 11-06)."""
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["summary"].items()}


def signatures():
    """의뢰 번호 → 의뢰인 서명 줄(마지막 슬롯, 본문과 섞지 않는다)."""
    with open(SUMMARY_PATH, encoding="utf-8") as f:
        return {int(k): v for k, v in json.load(f)["signature"].items()}


def plan(board, limit=B.LIMIT):
    """[(의뢰 번호, [(키 오프셋, 종류, 옛, 새)])], [(의뢰 번호, 사유)] — 요약은 표대로 바꾸고 본문은 넘칠 때만 다시 끊는다."""
    todo, fail = [], []
    summ = summaries()
    sigs = signatures()
    for q, a1, a2, _b in board.quests():
        texts = board.texts(a1, a2)
        head = summ.get(q, texts[0])
        body = texts[1:]
        sig = sigs.get(q)
        if sig:  # 서명 줄은 본문에서 떼어 마지막 슬롯에 그대로 둔다(옛 재조판이 본문 끝에 붙여 놓았으면 되뗀다)
            lines = list(body)
            if lines[-1] == sig:
                lines.pop()
            else:
                assert lines[-1].endswith(" " + sig), (q, lines)
                lines[-1] = lines[-1][: -len(sig)].rstrip()
            n_main = len(body) - 1
            lines = [" ".join(t for t in lines if t)] + [""] * (n_main - 1)  # 줄 구분은 새로 정한다
            nb, why = B.reflow(head, lines, limit)
            if nb is None:
                fail.append((q, why))  # 서명이 본문에 붙은 채여도 그대로 둔다 — 마스터 판정(R3) 대기
                nb = None
            body = list(nb) + [sig] if nb else texts[1:]
        elif any(B.px(t) > limit for t in body):
            nb, why = B.reflow(head, body, limit)
            if nb is None:
                fail.append((q, why))  # 본문은 그대로 — 마스터 판정(R3) 대기
            else:
                body = nb
        new = [head] + body
        edits = []
        for k, (old, nw) in enumerate(zip(texts, new, strict=True)):
            if old != nw:
                off, kind, _t = board.slot(a1 + k)
                edits.append((off, kind, old, nw))
        if edits:
            todo.append((q, edits))
    return todo, fail


def _ui_replace(path_text, off, old, new):
    """`"0xOFF": { … "kr": "old" … }` 의 kr 값만 바꾼다(JSON 왕복은 사설 영역 글자를 망가뜨린다)."""
    key = f'"0x{off:06X}": {{'
    i = path_text.index(key)
    j = path_text.index("}", i)
    block = path_text[i:j]
    want = f'"kr": {json.dumps(old, ensure_ascii=False)}'
    assert block.count(want) == 1, (off, old)
    return (
        path_text[:i]
        + block.replace(want, f'"kr": {json.dumps(new, ensure_ascii=False)}')
        + path_text[j:]
    )


def main():
    board = B.Board()
    todo, fail = plan(board)
    n_edit = sum(len(e) for _q, e in todo)
    print(f"재조판 {len(todo)}건(줄 {n_edit}) · 못 드는 것 {len(fail)}건")
    for q, why in fail:
        print(f"  ✗ 의뢰 {q}: {why}")
    if "--apply" not in sys.argv:
        return 0
    with open(B.UI_PATH, encoding="utf-8") as f:
        ui_text = f.read()
    with open(B.FRAG_PATH, encoding="utf-8") as f:
        frag = json.load(f)
    table = hangul.load()
    seen = {}
    for _q, edits in todo:
        for off, kind, old, new in edits:
            if off in seen:
                assert seen[off] == new, (off, seen[off], new)  # 공유 문자열은 같은 새 값이어야 한다
                continue
            seen[off] = new
            if kind == "ui":
                ui_text = _ui_replace(ui_text, off, old, new)
            else:
                row = frag["rows"][f"0x{off:06X}"]
                assert row["kr"] == old
                row["kr"] = new
                if len(uitext.kr_codes(new, table)) > row["n"]:
                    row["grow"] = True
    with open(B.UI_PATH, "w", encoding="utf-8") as f:
        f.write(ui_text)
    with open(B.FRAG_PATH, "w", encoding="utf-8") as f:
        json.dump(frag, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("썼다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
