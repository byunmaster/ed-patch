"""문안을 이미지에 써 넣는다 — **길이 보존**.

    python3 games/ss-ed3/tools/reinsert.py --check    # 계약만 본다(안 쓴다)

블록 길이를 안 바꾼다(`docs/status.md` 5절). 모자란 바이트는 `typeset.pad_to_budget` 이
줄 끝 공백으로 채우고, **길이가 1바이트라도 달라지면 곧바로 운다.**

번역 정본은 `games/ss-ed3/script/<맵>.json` — 키는 블록 색인, 값은 우리 문안이다.
"""

import argparse
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
import banner
import common as C
import hangul_map as H
import inline_josa as IJ
import mapfile as M
import typeset as T

SCRIPT_DIR = os.path.join(C.GAME_DIR, "script")
NAME_MAX = 14  # 맵 이름 최대 — 원판 최장(`ディルトの関所`·`ドルフェスの塔`·`ラグーナ船着場`)


def _read_script(stem):
    p = os.path.join(SCRIPT_DIR, f"{stem}.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def load_script(stem):
    """`({블록 색인: 칸 안에 **물리적으로** 들어가는 문안}, 원문 지문)`.

    🔴 `_wide` 블록은 칸(원문 바이트 예산)에 안 들어가는 진짜 문안을 **맵 꼬리**에서 그린다
    (`choice_tail.py`). 정본 JSON 의 값은 진짜 문안이고 `_wide` 가 칸 안에 둘 **대역**이다 —
    이 함수는 대역을 돌려준다(재삽입·되풀이 검사 전부가 「칸 안에 뭐가 있나」를 묻기 때문).
    진짜 문안이 필요하면(`이름 검사`·조판 지문) 정본 JSON 을 그대로 읽는다 — `wide()` 도 있다.
    """
    d = _read_script(stem)
    script = {k: v for k, v in d.items() if not k.startswith("_")}
    script.update(d.get("_wide", {}))
    #   인라인 아이템 코드 뒤 병기 조사는 빌드 때 하나로 줄인다(`inline_josa.py`) — 칸 안에 **물리적으로** 들어가는 문안이다
    script = {k: IJ.resolve(v) if isinstance(v, str) else v for k, v in script.items()}
    return script, d.get("_jp", {})


def wide(stem):
    """`{블록 색인: 진짜 문안}` — 칸 밖(맵 꼬리)에서 그리는 블록."""
    d = _read_script(stem)
    return {k: d[k] for k in d.get("_wide", {})}


def jp_stamp(body):
    """원문 블록의 지문 — 우리 문안이 **그 블록**을 가리키는지 확인하는 자.

    🔴 색인만으로는 조용히 어긋난다(2026-08-25 실측). 블록 파서를 한 줄 고쳤더니
    전체 블록 수가 하나 줄었다 — 그날은 다행히 번역한 자리가 안 밀렸지만, 밀렸다면
    **번역이 엉뚱한 대사에 들어가고 빌드는 성공한다.** 저작권상 원문을 커밋할 수 없으니
    (CLAUDE.md) 남기는 것은 **해시뿐**이다.
    """
    return hashlib.sha1(body).hexdigest()[:8]


def fit(text, budget, jp_over=None, jp_text=None):
    """우리 문안을 원문 바이트 예산에 맞춘다 — `(맞춘 문안, 사유)`.

    ⚠ `jp_over` 는 **원문이 이미 넘치는 페이지**다(`typeset.overflows` 의 결과).
    `0F` 가 창을 비우지 않고 한 줄씩 스크롤하는 물건이라(2026-08-25 실측) 원문에도
    3 줄을 넘는 구간이 있다 — 저자가 그렇게 쓴 자리다. **원문만큼은 봐준다.**
    「지금 고칠 수 있는 것만 실패로 친다」(CLAUDE.md) — 원문이 그런 걸 우리가 못 고친다.

    ⚠ `ED_RULER=1` 이면 **창 계약 검사를 건너뛴다** — 눈금자를 심어 창을 재는 용도다
    (긴 줄을 일부러 넣어 「어디서 접히나 · 3 줄을 넘으면 어떻게 되나」를 화면에 묻는다).
    실측용이므로 **평소에는 켜지 않는다.**
    """
    over = [] if os.environ.get("ED_RULER") else T.overflows(text)
    if over and jp_over:
        allow = dict(jp_over)
        over = [(i, n) for i, n in over if n > max(T.WIN_ROWS, allow.get(i, 0))]
    if over:
        return None, f"창 계약을 넘는다(17×{T.WIN_ROWS}) — 페이지 {over}"
    # ⚠ 채우는 폭은 **원문이 쓴 만큼**까지 연다. 저자가 17 칸을 넘겨 한 줄로 쓴 자리가
    #   있는데(엔진이 접는다) 거기서 17 칸까지만 채우면 자리가 모자라 재삽입이 통째로
    #   거부된다 — 문안이 예산보다 **짧은데도** 실패한다(2026-08-25 세 블록에서 물렸다).
    width = T.SCREEN_COLS if T.is_narration(text) else T.WIN_COLS
    if jp_text:
        width = max(width, *(int(T.cols(x)) for x in T.lines(jp_text) or [T.WIN_COLS]))
    out = T.pad_to_budget(text, budget, width)
    if out is None:
        out = T.pad_to_budget(text, budget, width, keep_last=False)
    if out is None:
        have = T.body_bytes(text)
        return None, f"예산 {budget}B 에 못 맞춘다(문안 {have}B)"
    return out, None


NAME_STRIDE = 32  # 맵의 인물 이름표는 **32B 칸**이 이어진 표다(`0x14` 이상 화자 번호 = 표 색인) — 이름 뒤는 0 으로 비어 있다
NAME_MAX_SLOT = 24  # 그 칸 안에서 늘려 쓰는 상한(B) — 이름줄이 창 폭 안이고 NUL 종료 자리를 남긴다


def name_slots(blocks, data):
    """`{블록 색인: 칸 크기}` — 이름표 구간: 오프셋이 정확히 32B 간격으로 이어지고 **칸 뒤가 전부 0 인** 블록 2 개 이상.

    ⚠ 간격만 보면 우연히 32B 떨어진 대사 블록이 걸린다(MAP057). 이름표는 칸 뒤가 0 이고 머리가 `0000` 이다(첫 칸만 앞 포인터 꼬리)."""

    def ok(j):
        o, n = blocks[j]["off"], len(blocks[j]["body"])
        return (
            n < NAME_STRIDE
            and not any(data[o + n : o + NAME_STRIDE])
            and (blocks[j]["head"] == "0000" or j == 1)
        )

    out, run = {}, []
    for i in range(1, len(blocks) + 1):
        if (
            i < len(blocks)
            and ok(i)
            and run
            and blocks[i]["off"] - blocks[run[-1]]["off"] == NAME_STRIDE
        ):
            run.append(i)
            continue
        if len(run) >= 2:
            out.update({j: NAME_STRIDE for j in run})
        run = [i] if i < len(blocks) and ok(i) else []
    return out


def patch_blocks(data, stem, table):
    """`(새 bytes, 넣은 수, [(블록, 사유)])` — 길이 불변."""
    script, stamps = load_script(stem)
    if not script:
        return data, 0, []
    blocks = M.blocks(data)
    slots = name_slots(blocks, data)
    out = bytearray(data)
    done = 0
    bad = []
    for key, kr in script.items():
        i = int(key)
        if not 0 <= i < len(blocks):
            bad.append((key, f"블록 색인이 범위 밖({len(blocks)})"))
            continue
        blk = blocks[i]
        if M.suspect_head(blk):
            bad.append((key, "블록 시작이 밀렸다 — 먹힌 글자가 문안 앞에 남는다"))
            continue
        want = stamps.get(key)
        if want and want != jp_stamp(blk["body"]):
            bad.append((key, f"원문 지문이 다르다 — 블록이 밀렸다(기대 {want})"))
            continue
        budget = len(blk["body"])
        #   🔴 **이름표 칸은 늘려 쓴다**(마스터 10-04 「크리스엄마 → 크리스 엄마」) — 칸이 32B 인데 원문 이름은 10~16B 라 뒤가 0 이다.
        #   예산(원문 길이)에 묶이면 「크리스의 母」 10B 가 「크리스엄마」 10B 로 꽉 차 띄울 자리가 없었다. 칸 안(`NAME_MAX_SLOT`)에서
        #   **채우지 않고** 이름만 쓰고 NUL 로 닫는다(원문 이름도 길이가 제각각이다).
        if i in slots and not any(c in kr for c in "\n\f"):
            raw = H.encode_kr(kr, table)
            end = blk["off"] + slots[i]
            if len(raw) > NAME_MAX_SLOT:
                bad.append((key, f"이름이 {NAME_MAX_SLOT}B 를 넘는다({len(raw)}B)"))
                continue
            if any(data[blk["off"] + budget + 1 : end]):
                bad.append((key, "이름 칸 뒤가 비어 있지 않다 — 늘려 쓸 수 없다"))
                continue
            out[blk["off"] : end] = raw + b"\x00" * (end - blk["off"] - len(raw))
            done += 1
            continue
        if blk["off"] == M.NAME_OFF and len(raw := H.encode_kr(kr, table)) > budget:
            #   맵 이름 칸 — NUL 종료 문자열이고 뒤는 0 으로 비어 있다(88 맵 전부 30B 넘게).
            #   원판도 14B 까지 쓴다(`ディルトの関所` 등) ⇒ 뒤가 비었을 때만 NAME_MAX 까지 늘려 쓴다.
            #   🔑 「큰뱀의 등뼈」(11B)가 원문 `大蛇の背骨`(10B)를 넘어 붙여쓰기로 버티던 자리(09-28 마스터).
            #   ⚠ 예산 안이면 종전대로(공백 채움) — 88 이름의 바이트를 안 흔든다.
            end = blk["off"] + max(budget, len(raw))
            if len(raw) > NAME_MAX:
                bad.append((key, f"맵 이름이 {NAME_MAX}B 를 넘는다({len(raw)}B)"))
                continue
            if any(data[blk["off"] + budget : blk["off"] + NAME_MAX + 1]):
                bad.append((key, "맵 이름 뒤가 비어 있지 않다 — 늘려 쓸 수 없다"))
                continue
            out[blk["off"] : end] = raw + b"\x00" * (end - blk["off"] - len(raw))
            done += 1
            continue
        jp = M.text_of(blk["body"])
        #   지명 배너 — 전각 공백을 반각으로, 글자는 **한 행 내린 판**으로(`banner.py`)
        enc = table
        if banner.is_place_banner(kr):
            kr = banner.normalize(kr)
            enc = {**table, **H.load_low()}
        fitted, why = fit(kr, budget, T.overflows(jp), jp)
        if fitted is None:
            bad.append((key, why))
            continue
        raw = H.encode_kr(fitted, enc)
        if len(raw) != budget:
            bad.append((key, f"길이가 변했다 {len(raw)} != {budget}"))
            continue
        out[blk["off"] : blk["off"] + budget] = raw
        done += 1
    return bytes(out), done, bad


def main():
    #   🔴 예전엔 `sys.argv` 에서 `--check` 만 보고 **맵 이름을 통째로 무시**했다. 에이전트를
    #     여럿 굴리니 「내 맵을 검사했더니 **남이 지금 고치는 맵**이 실패로 뜬다」가 됐고,
    #     종료 코드까지 1 이라 남의 실패를 자기 것으로 알고 헛돌았다(2026-08-27 실측).
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", nargs="*", help="MAP016 … (없으면 전부)")
    ap.add_argument("--check", action="store_true", help="쓰지 않고 계약만 본다")
    a = ap.parse_args()
    check = a.check
    table = H.load()
    total = done = 0
    bad = []
    with C.open_disc(1) as d:
        for n, lba, size in d.files():
            if not C.is_map_file(n)[0]:
                continue
            stem = C.is_map_file(n)[1]
            if a.stems and stem not in a.stems:
                continue
            if not load_script(stem)[0]:
                continue
            b = d.read_extent(lba, size)
            _, k, err = patch_blocks(b, stem, table)
            total += len(load_script(stem)[0])
            done += k
            bad += [(f"{stem}[{i}]", w) for i, w in err]
    print(f"문안 {total}  넣음 {done}  실패 {len(bad)}" + ("  (검사만)" if check else ""))
    for k, w in bad[:10]:
        print(f"  ❌ {k} — {w}")
    if bad:
        raise SystemExit(1)
    print("✅ 전부 길이 보존으로 들어간다")


if __name__ == "__main__":
    main()
