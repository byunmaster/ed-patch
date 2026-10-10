"""씬 대사에 남은 일본어 — **화면에 나가는 바이트**를 본다 (라운드④, 보고 전용 · 마스터 10-11 「일본어는 남지 않아야 해」).

    python3 tools/check_scene_jp.py            # 남은 스트림 목록(원본 모듈 오프셋)
    python3 tools/check_scene_jp.py --check    # 남았으면 실패

정본(`script/*.json`)이 비었는지가 아니라 **빌드가 낸 모듈 바이트**를 다시 파싱해, 글자 토막에 가나·한자가 남았나
센다. 번역이 있어도 빌드가 조용히 탈락시킨 스트림은 원문이 그대로 남으므로 여기서 잡힌다. 한글은 표 0 의 한자
슬롯(코드 0x8A40~)에 들어가므로 **우리 한글 코드는 일본어로 세지 않는다.**
열쇠는 `NNN:oooo`(원본 모듈 오프셋 — 최종 바이트에선 스트림이 끝으로 옮겨져 문안 길이마다 오프셋이 바뀐다).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import archives
import common
import scene


def _is_jp(b1: int, b2: int, hangul: set[int]) -> bool:
    if ((b1 << 8) | b2) in hangul or not (0x40 <= b2 <= 0xFC and b2 != 0x7F):
        return False
    try:
        ch = bytes([b1, b2]).decode("cp932")
    except UnicodeDecodeError:
        return False
    return "぀" <= ch <= "ヿ" or "一" <= ch <= "鿿"


def stream_has_jp(st: scene.Stream, hangul: set[int]) -> bool:
    for t in st.tokens:
        if t.kind != "text":
            continue
        raw, i = t.raw, 0
        while i < len(raw):
            if scene.is_lead(raw[i]) and i + 1 < len(raw):
                if _is_jp(raw[i], raw[i + 1], hangul):
                    return True
                i += 2
            else:
                i += 1
    return False


def scan(blocks: dict[int, bytes], orig: dict[int, bytes], hangul: set[int]) -> list[str]:
    out = []
    for n, b in sorted(blocks.items()):
        o_mod = scene.parse_module(orig[n])
        mod = scene.parse_module(b, o_mod)  # 표 항목 자리는 원본이 알려 준다(새 바이트에선 문안 곁에 없다)
        offs = sorted(mod.streams)
        o_offs = sorted(o_mod.streams)
        if len(offs) != len(o_offs):
            raise SystemExit(f"블록 {n}: 스트림 수가 원본과 다르다 ({len(o_offs)} → {len(offs)})")
        for i, off in enumerate(offs):
            if stream_has_jp(mod.streams[off], hangul):
                out.append(f"{n:03d}:{o_offs[i]:04x}")
    return out


# 화면에 안 나가는 게 확실한 자리 — 경고로 세고 통과시킨다(마스터 10-11 「확실하면 warning」).
# 근거: `lea` 뒤에 `movea.w #MSG,a5`(메시지 호출)가 없는 자료 포인터가 문안처럼 파싱됐을 뿐이다.
NOT_SHOWN = {"002:012c", "011:012c", "049:0082", "075:00ab", "076:0075", "079:00b7", "080:01c3"}


def report(blocks, orig, hangul) -> list[str]:
    left = scan(blocks, orig, hangul)
    warn = [k for k in left if k in NOT_SHOWN]
    fail = [k for k in left if k not in NOT_SHOWN]
    print(
        f"  씬 화면 일본어 — 실패 {len(fail)} · 경고 {len(warn)}(자료 포인터, 화면에 안 나감)"
        f"{': ' + ' '.join(fail[:6]) + (' …' if len(fail) > 6 else '') if fail else ''}"
    )
    return fail


if __name__ == "__main__":
    import build
    import hangul as hg

    orig = common.rom()
    new = (common.BUILD_DIR / common.BUILD_TAG / "ed1-kr.bin").read_bytes()
    base = archives.ARCHIVES["script"][0]
    ob = {i: b for i, (_s, b, _e) in enumerate(archives.blocks(orig, base))}
    nb = {i: b for i, (_s, b, _e) in enumerate(archives.blocks(new, base))}
    codes = set(__import__("json").loads((common.GAME_DIR / "textmap" / "hangul_codes.json").read_text(encoding="utf-8")).values())
    left = scan(nb, ob, codes)
    print("\n".join(k + ("  (경고)" if k in NOT_SHOWN else "") for k in left))
    left = [k for k in left if k not in NOT_SHOWN]
    print(f"남은 스트림(경고 제외) {len(left)}")
    if "--check" in sys.argv and left:
        raise SystemExit(1)
