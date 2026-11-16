#!/usr/bin/env python3
"""구운 롬의 블록을 **실제로 풀어** 점프를 따라가며 화면에 찍힐 글을 디코드한다 — 낀 옵코드 점프 17곳(11-06).

번역 정본 모델로 검증하면 「정본은 멀쩡한데 롬 바이트에서만 깨지는」 꼴을 놓친다(씬 46 「없어졌있습니다」). 그래서 구운 이미지에서 컨테이너를
다시 풀고(LZ), 씬 블록의 메시지 시작(화자 머리)에서 읽기 시작해 `0F` 를 따라간 글을 글리프 표로 되읽는다.
갈래 ① = 호스트 머리부터(정상 흐름) · 갈래 ② = 앞 메시지(화자 머리 + 옵코드)에서 `0F` 로 꼬리 본체에 진입. 판정: 갈래 ② 본문이 갈래 ① 본문의
꼬리(끝부분)와 같고, 모르는 글자 코드가 없어야 한다. 원판 칸은 같은 읽기를 원본 블록에 SJIS 로 한 것.

    python3 games/pce-ed1/tools/jump_readout.py [--table out.md]   # 표를 쓰고 판정 (구운 이미지 필요)
"""

import glob
import mmap
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common
import containers
import credits_kr
import font
import glyphdyn
import messages as M
import translate

SCENES = (21, 25, 29, 46, 58, 72, 76, 113, 122, 129, 163, 192, 193, 194, 195, 196, 201)
OPS3 = set(M.OTHER_OPS) | {0x0F}


def built_track(iso: Path) -> bytes:
    with open(iso, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        return b"".join(
            mm[(common.T2_SECTOR + rel) * common.RAW + common.USER_OFF : (common.T2_SECTOR + rel) * common.RAW + common.USER_OFF + common.USER]
            for rel in range(common.T2_LEN)
        )


def inverse_table(sid: int) -> dict[bytes, str]:
    chars = glyphdyn.forced_chars() | (translate.all_glyph_chars() & set(font._order_canon()))
    chars |= credits_kr.chars()
    table, _ = font.build_table(chars)
    btab, _dyn = glyphdyn.block_table(table, sid)
    inv: dict[bytes, str] = {}
    for ch, code in btab.items():
        inv[code] = ch
        try:
            inv[font.variant(code)] = ch
        except Exception:  # noqa: BLE001 — 변형 코드가 없는 칸
            pass
    return inv


def read(buf: bytes, pos: int, inv: dict[bytes, str] | None, limit: int = 3000, stop_at_op: bool = True) -> tuple[str, list[int], int]:
    """`pos` 부터 종료까지 읽는다 — (글, 따라간 점프 목적지들, 모르는 코드 수). inv 가 None 이면 원판(SJIS)."""
    out: list[str] = []
    jumps: list[int] = []
    unknown = 0
    steps = 0
    while steps < limit and 0 <= pos < len(buf):
        steps += 1
        b = buf[pos]
        if b in (0x00, 0x06, 0x07):
            break
        if b == 0x1F:  # 화자 머리 — 04 까지
            q = pos + 1
            name = bytearray()
            while q < len(buf) and buf[q] != 0x04 and len(name) < 40:  # 이름 읽기도 `0F` 를 따라간다(긴 이름 머리는 재배치로 이름 중간에서 이어진다)
                if buf[q] == 0x0F:
                    q = (buf[q + 1] | buf[q + 2] << 8) - M.BASE
                    jumps.append(q)
                    continue
                name.append(buf[q])
                q += 1
            out.append("〔" + _head(bytes(name), inv) + "〕")
            pos = q + 1
        elif b == 0x09:
            out.append(f"<공용{buf[pos + 1]}>")
            pos += 2
        elif b == 0x01:
            out.append("\n")
            pos += 1
        elif b in (0x03, 0x05):
            out.append(" ¶ ")
            pos += 2 if b == 0x03 else 1
        elif b == 0x0F:
            t = (buf[pos + 1] | buf[pos + 2] << 8) - M.BASE
            jumps.append(t)
            pos = t
        elif stop_at_op and (b in OPS3 or b in M.OTHER_OPS) and any(t.strip("〔〕\n ") and not t.startswith("<op") for t in out if not t.startswith("〔")):
            break  # 글을 읽은 뒤 만나는 글 밖 옵코드 = 이 메시지의 끝(다음은 스크립트)
        elif b in OPS3 or b in M.OTHER_OPS:
            n = 3 if b in OPS3 else 1 + M.OTHER_OPS[b]
            out.append(f"<op{b:02X}>")
            pos += n
        elif b in M.TEXT_OPS:
            pos += 1 + M.TEXT_OPS[b]
        else:
            s = pos
            while pos < len(buf) and buf[pos] not in (0x00, 0x01, 0x03, 0x04, 0x05, 0x06, 0x07, 0x09, 0x0F, 0x1F) and buf[pos] not in OPS3:
                pos += 2 if (inv is not None and buf[pos] >= 0xF0) or (inv is None and (0x81 <= buf[pos] <= 0x9F or 0xE0 <= buf[pos] <= 0xEA)) else 1
            seg = buf[s:pos]
            txt, u = _dec2(seg, inv)
            unknown += u
            out.append(txt)
    return "".join(out), jumps, unknown


def _head(seg: bytes, inv) -> str:
    """화자 머리 — 원문 이름(SJIS)이거나 한글 표 코드(런타임 이름표는 SJIS 그대로 두는 경우가 있다)."""
    txt, u = _dec2(seg, inv)
    return txt if u == 0 else seg.decode("cp932", "replace")


def _dec2(seg: bytes, inv) -> tuple[str, int]:
    out, unknown, i = [], 0, 0
    while i < len(seg):
        if inv is None:
            if seg[i] >= 0x81 and i + 1 < len(seg):
                out.append(seg[i : i + 2].decode("cp932", "replace"))
                i += 2
            else:
                out.append(seg[i : i + 1].decode("cp932", "replace"))
                i += 1
            continue
        two = seg[i : i + 2]
        if two == font.HALF_SPACE:
            out.append(" ")
            i += 2
        elif two in inv:
            out.append(inv[two])
            i += 2
        elif seg[i] == 0xF9:  # 동적 조사 토큰
            out.append("<조사>")
            i += 2
        elif two == b"\x81\x40":
            out.append("　")
            i += 2
        elif seg[i] < 0x80:
            out.append(chr(seg[i]) if 0x20 <= seg[i] < 0x7F else f"<{seg[i]:02X}>")
            i += 1
        else:
            out.append(f"<?{two.hex()}>")
            unknown += 1
            i += 2
    return "".join(out), unknown


def header_korean(r: str) -> bool:
    """읽은 글(`read` 결과)의 화자 머리 〔…〕 가 한글인가 — 원문(SJIS) 이름이 그대로 나가면 False."""
    h = re.match(r"〔([^〕]*)〕", r)
    return bool(h) and bool(re.search("[가-힣]", h.group(1))) and "<?" not in h.group(1)


def cases() -> list[dict]:
    """원본 블록에서 (화자 머리/글 없음 + 옵코드 + 0F → 호스트 한가운데) 갈래 — 호스트 목록을 비운 파서로 「조각내기 전」 호스트를 찾는다."""
    out = []
    saved = M.OP_JUMP_HOSTS
    for sid in SCENES:
        f = glob.glob(str(common.OUT_DIR / "text" / f"*_{sid:03d}.bin"))[0]
        b = Path(f).read_bytes()
        M.OP_JUMP_HOSTS = frozenset()
        try:
            ms0 = M.parse(b)
        finally:
            M.OP_JUMP_HOSTS = saved
        for m in ms0:
            e = m.end
            if m.terminated or e + 5 >= len(b) or b[e] not in M.OP3 or b[e + 3] != M.JUMP:
                continue
            w = (b[e + 4] | b[e + 5] << 8) - M.BASE
            host = next((t for t in ms0 if t.start < w < t.end), None)
            if host is None or host.key not in saved:
                continue
            has_text = any(isinstance(t, str) for t in m.tokens)
            if has_text and b[w] != 0x00:
                continue  # 글 + 옵코드 + 점프는 목적지가 공유 종료(00)일 때만 — 씬 196
            out.append({"sid": sid, "A": m.start, "host": host.start, "target": w, "orig": b, "term": has_text})
    return out


def run(iso: Path) -> tuple[list[dict], list[str]]:
    track = built_track(iso)
    found = containers.scan(track)
    blocks: dict[int, list[tuple[int, bytes]]] = {}
    for c in found:
        for blk in c["blocks"]:
            blocks.setdefault(blk["id"], []).append((c["rel"], blk["data"]))
    rows, bad = [], []
    invs: dict[int, dict] = {}
    for c in cases():
        sid = c["sid"]
        cand = [d for _r, d in blocks.get(sid, []) if d != c["orig"]]  # 원본과 같은 사본(참조표 쪽에 남은 것)은 번역본이 아니다
        if not cand:
            bad.append(f"씬 {sid}: 구운 이미지에 번역된 블록이 없다")
            continue
        nb = max(cand, key=lambda d: len(d))
        inv = invs.setdefault(sid, inverse_table(sid))
        o1, _, _ = read(c["orig"], c["host"], None)
        o2, _, _ = read(c["orig"], c["A"], None)
        r1, j1, u1 = read(nb, c["host"], inv)
        r2, j2, u2 = read(nb, c["A"], inv, stop_at_op=not c.get("term"))
        body1 = re.sub(r"^〔[^〕]*〕", "", r1).lstrip("\n")
        body2 = re.sub(r"^〔[^〕]*〕", "", r2).replace("<op12>", "").replace("<op11>", "").replace("<op14>", "").lstrip("\n")
        h1 = re.match(r"〔([^〕]*)〕", r1)
        h2 = re.match(r"〔([^〕]*)〕", r2)
        if not (header_korean(r2) and (h1 is None or header_korean(r1))):  # 두 갈래의 화자 머리는 한글이어야 한다(원문 이름이 화면에 나가면 안 된다 — 씬 72 처럼 원문이 두 이름을 쓰는 곳도 있어 같을 것까지는 요구 안 함)
            bad.append(f"씬 {sid} 점프 {c['A']}→{c['target']}: 화자 머리가 한글이 아니거나 두 갈래가 다르다 ({r1[:12]!r} / {r2[:12]!r})")
        if c.get("term"):  # 목적지가 공유 종료 — 롬에서도 그 자리가 00 이고 갈래 ② 가 제 글로 끝나야 한다
            ok = nb[c["target"]] == 0x00 and u1 == 0 and u2 == 0 and bool(body2.strip()) and bool(c["target"] in j2)
            rows.append({"sid": sid, "A": c["A"], "host": c["host"], "target": c["target"], "o1": o1, "o2": o2, "r1": r1, "r2": r2, "ok": ok, "u": u1 + u2})
            if not ok:
                bad.append(f"씬 {sid} 점프 {c['A']}→{c['target']}: 공유 종료 자리가 롬에서 00 이 아니거나 읽기가 어긋난다")
            continue
        ok = bool(body2.strip()) and u1 == 0 and u2 == 0 and body1.replace("\n", " ").replace(" ¶ ", " ").strip().endswith(body2.replace("\n", " ").replace(" ¶ ", " ").strip())
        rows.append({"sid": sid, "A": c["A"], "host": c["host"], "target": c["target"], "o1": o1, "o2": o2, "r1": r1, "r2": r2, "ok": ok, "u": u1 + u2})
        if not ok:
            bad.append(f"씬 {sid} 점프 {c['A']}→{c['target']}: 갈래 ② 본문이 갈래 ① 의 꼬리와 다르다(또는 모르는 코드 {u1 + u2})")
    return rows, bad


def _blocks(found, sid, orig):
    cand = [d for c in found for b in c["blocks"] if b["id"] == sid for d in [b["data"]] if d != orig]
    return max(cand, key=len) if cand else None


def audit_all(track_found) -> tuple[int, int, list[str]]:
    """① 머리뿐인 메시지(화자 머리 + 옵코드/점프)의 화자 이름이 롬에서도 한글 코드인가(점프로 닿는 머리의 일본어 이름이 화면에 나가던 것, 11-06)
    ② 바로 붙은 `0F` 로 합친 메시지(공유 꼬리 점프를 이은 17곳 — 「돈이 조금 없어졌있습니다」 부류)를 롬에서 읽은 글 == 번역 정본 이은 문장인가."""
    bad: list[str] = []
    n_head = n_join = skipped = 0
    for f in sorted(glob.glob(str(common.OUT_DIR / "text" / "*.bin"))):
        sid = int(re.search(r"_(\d+)\.bin$", f).group(1))
        sp = common.GAME_DIR / "script" / f"scn{sid:03d}.json"
        if not sp.exists():
            continue
        b = Path(f).read_bytes()
        nb = _blocks(track_found, sid, b)
        if nb is None:
            continue
        import json

        tr = json.loads(sp.read_text("utf-8"))["messages"]
        inv = None
        for m in M.parse(b):
            e = m.end
            if m.terminated or e + 3 >= len(b):
                continue
            if m.speaker is not None and not any(isinstance(t, str) for t in m.tokens) and (b[e] == M.JUMP or (b[e] in M.OP3 and b[e + 3] == M.JUMP)):
                inv = inv or inverse_table(sid)
                r, _j, _u = read(nb, m.start, inv, stop_at_op=False, limit=40)  # 재배치된 머리는 `0F` 로 따라간다
                hd = re.match(r"〔([^〕]*)〕", r)
                n_head += 1
                if hd is None or not re.search("[가-힣]", hd.group(1)) or "<?" in hd.group(1):
                    bad.append(f"씬 {sid} 머리뿐인 메시지 {m.start}: 화자 머리가 롬에서 한글로 안 읽힌다 ({r[:30]!r})")
            elif any(isinstance(t, str) for t in m.tokens) and b[e] == M.JUMP:
                w = (b[e + 1] | b[e + 2] << 8) - M.BASE
                if not any(t.start < w < t.end for t in M.parse(b)) and False:
                    continue
        # 바로 붙은 점프를 이은 메시지 — 파서가 합친 것(끝이 점프 3B 를 먹은 메시지)
        for m in M.parse(b):
            if b[m.end - 3 : m.end - 2] != bytes([M.JUMP]) or m.end - 3 <= m.start or not any(isinstance(t, str) for t in m.tokens):
                continue
            t = (tr.get(m.key) or {}).get("t")
            if not t or re.search("은/는|이/가|을/를|과/와|으로/로|아/야|이랑/랑|<", t):
                skipped += 1
                continue
            inv = inv or inverse_table(sid)
            r, _j, u = read(nb, m.start, inv, stop_at_op=True)
            got = re.sub(r"<[^>]*>|〔[^〕]*〕|[\s¶]", "", r)
            want = re.sub(r"[\s\f]", "", font.ligate(t))
            n_join += 1
            if u or not got.startswith(want):
                bad.append(f"씬 {sid} 이은 메시지 {m.start}({m.key[:8]}): 롬에서 읽은 글이 정본과 다르다 — {got[:30]!r} ≠ {want[:30]!r}")
    return n_head, n_join, bad


def table(rows: list[dict]) -> str:
    esc = lambda s: s.replace("\n", "⏎").replace("|", "∣")  # noqa: E731
    out = ["# 낀 옵코드 점프 — 구운 롬 실제 디코드(원판 이어 읽기 대조)\n", "| 씬 | 점프 | 원판 ① | 원판 ② | 롬 ① | 롬 ② | 판정 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        out.append(f"| {r['sid']} | {r['A']}→{r['target']} | {esc(r['o1'])[:60]} | {esc(r['o2'])[:60]} | {esc(r['r1'])[:80]} | {esc(r['r2'])[:80]} | {'✅' if r['ok'] else '❌'} |")
    return "\n".join(out) + "\n"


def main() -> int:
    iso = common.BUILD_DIR / common.BUILD_TAG / "ed1.iso"
    if not iso.exists():
        print("구운 이미지가 없다 —", iso)
        return 1
    rows, bad = run(iso)
    n_head, n_join, bad2 = audit_all(containers.scan(built_track(iso)))
    bad += bad2
    print(f"머리뿐인 메시지 화자 머리 한글 {n_head}곳 · 이은 메시지 롬 대조 {n_join}곳")
    if "--table" in sys.argv:
        Path(sys.argv[sys.argv.index("--table") + 1]).write_text(table(rows))
    print(f"낀 옵코드 점프 롬 되읽기 — {len(rows)}곳 · 어긋남 {len(bad)}")
    for x in bad:
        print("  ❌", x)
    return 1 if bad or len(rows) < 17 else 0


if __name__ == "__main__":
    raise SystemExit(main())
