"""전투 데이터 컨테이너 — 몬스터 레코드(이름 포함)를 뜯고 되쓴다.

씬 컨테이너(`containers.py`)와 **형식이 다르다**:

    씬   rel 1,252~1,620  디렉터리 5B 항목 `id, src(2), 풀린길이(2)` + 0xFF 끝
    전투 rel 162~209      디렉터리 4B 항목 `src(2), 풀린길이(2)` — **끝 표시가 없다.**
                          디렉터리 길이는 첫 항목의 src 가 준다(src[0] − 0x6000 = 디렉터리 바이트 수).

블록을 풀면 **64B 몬스터 레코드**가 이어지고 `FF FF FF FF` 로 끝난다. 뒤에는 전투 코드와
씬 문법 문구(「…が現れた。」)가 붙는다. 레코드 뒷칸 16B 가 이름이다 —
`이름 06` + 00 패딩으로, 화자 레코드(`sysstrings.read_speakers`)·HUD 지명과 같은 꼴이다.

⚠ 되쓰기는 **풀린 길이를 안 바꾼다**(레코드가 고정폭이라 이름칸만 갈아 끼운다). 압축 크기는
바뀌므로 컨테이너를 다시 깐다 — 그래서 `pack()` 이 디렉터리까지 새로 쓴다.
"""

import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import lz

BASE = 0x6000  # 컨테이너가 올라가는 논리 주소
REC = 64  # 몬스터 레코드
NAME_OFF, NAME_LEN = 48, 16
LOAD_ADDR = 0xC400  # 전투 블록이 올라가는 논리 주소(간접 이름 주소의 기준, 실측)
SPAN = 8 * common.USER  # 컨테이너 하나가 차지하는 칸(8섹터 간격, 실측)
CONTAINERS = (162, 170, 178, 186, 194, 202)
EXPECT = {"containers": 6, "blocks": 100, "records": 259, "names": 224}


def parse(rel: int) -> list[dict]:
    """컨테이너 하나 → 블록 목록. 형태가 안 맞거나 하나라도 안 풀리면 예외."""
    raw = common.track_data(rel, 8)
    dl = (raw[0] | raw[1] << 8) - BASE
    if dl <= 0 or dl % 4 or dl > 0x200:
        raise ValueError(f"rel {rel}: 디렉터리 길이 {dl} 가 이상하다")
    ents = [(raw[i] | raw[i + 1] << 8, raw[i + 2] | raw[i + 3] << 8) for i in range(0, dl, 4)]
    blocks = []
    for src, ln in ents:
        out, used = lz.decode(raw[src - BASE :], ln)
        blocks.append({"src": src, "len": ln, "packed": used, "data": out})
    return blocks


def _name(data: bytes, nm: bytes) -> tuple[str, int | None, str] | None:
    """이름칸 → (글자, 간접 대상 offset|None, 간접 뒤에 붙은 꼬리).

    긴 이름은 칸(16B)에 안 들어가므로 `23 주소(2)` **간접**으로 둔다. 주소 기준은 블록이
    올라가는 $C400(실측: 블록 안 +0x255 ↔ $C655). 간접 뒤에 개체 꼬리가 붙는다 —
    「<긴 이름>Ａ」 꼴이라 이어 붙여 읽고, 되쓸 땐 **대상 문자열만** 갈아 끼운다.
    """
    out, ind, tail = "", None, ""
    i = 0
    while i < len(nm):
        c = nm[i]
        if c == 0x06:
            return out, ind, tail
        if c == 0x23:
            off = (nm[i + 1] | nm[i + 2] << 8) - LOAD_ADDR
            if not 0 <= off < len(data) or ind is not None:
                return None
            try:
                seg = data[off:].split(b"\x06")[0].decode("cp932")
            except UnicodeDecodeError:
                return None
            out += seg
            ind = off
            i += 3
            continue
        if c < 0x24 or nm[i + 1] < 0x20:
            # 이름칸이 아니다 — 긴 이름을 담아 두는 칸을 레코드로 오독한 것이다(실측 rel 186 blk9)
            return None
        try:
            ch = nm[i : i + 2].decode("cp932")
        except UnicodeDecodeError:
            return None
        out += ch
        if ind is not None:
            tail += ch
        i += 2
    return None


def records(data: bytes) -> list[dict]:
    """블록 앞머리의 64B 레코드 표 — `FF FF FF FF` 앞까지."""
    out = []
    for a in range(0, len(data) - REC + 1, REC):
        if data[a : a + 4] == b"\xff\xff\xff\xff":
            break
        r = _name(data, data[a + NAME_OFF : a + NAME_OFF + NAME_LEN])
        if r is None:
            break
        name, ind, tail = r
        out.append({"off": a, "jp": name, "ind": ind, "tail": tail})
    return out


def scan() -> list[dict]:
    return [{"rel": rel, "blocks": parse(rel)} for rel in CONTAINERS]


def names() -> dict[str, list[tuple[int, int, int]]]:
    """JP 이름 → [(rel, 블록 index, 레코드 offset)…]"""
    out: dict[str, list[tuple[int, int, int]]] = {}
    for c in scan():
        for bi, b in enumerate(c["blocks"]):
            for r in records(b["data"]):
                out.setdefault(r["jp"], []).append((c["rel"], bi, r["off"]))
    return out


def pack(blocks: list[dict]) -> bytes:
    """블록들 → 컨테이너 바이트(디렉터리 + LZ). 원본과 같은 순서로 깐다."""
    dl = len(blocks) * 4
    body = bytearray()
    dirbuf = bytearray()
    for b in blocks:
        enc = lz.encode(b["data"])
        dirbuf += (BASE + dl + len(body)).to_bytes(2, "little") + len(b["data"]).to_bytes(
            2, "little"
        )
        body += enc
    out = bytes(dirbuf) + bytes(body)
    if len(out) > SPAN:
        raise ValueError(f"컨테이너가 {len(out)}B — 칸 {SPAN}B 를 넘는다")
    return out


def check() -> dict:
    cs = scan()
    nb = sum(len(c["blocks"]) for c in cs)
    nr = sum(len(records(b["data"])) for c in cs for b in c["blocks"])
    nm = names()
    got = {"containers": len(cs), "blocks": nb, "records": nr, "names": len(nm)}
    if got != EXPECT:
        raise SystemExit(f"분모가 달라졌다: {got} ≠ {EXPECT}")
    return got


if __name__ == "__main__":
    common.verify_originals()
    print(check())
    for jp, where in sorted(names().items()):
        print(f"  {jp}  ×{len(where)}")


# ─── 표기 · 되쓰기 ──────────────────────────────────────────────────────────
def _norm(s: str) -> str:
    """사전 대조용 정규화. PCE 는 장음을 `－`(전각 하이픈)로 적고 사전엔 반각 가나 표기가 섞여 있다."""
    s = unicodedata.normalize("NFKC", s)
    for a, b in (("-", "ー"), ("−", "ー"), ("―", "ー"), (" ", ""), ("・", "")):
        s = s.replace(a, b)
    return s


def kr_names(extra: dict[str, str] | None = None) -> tuple[dict[str, str], list[str]]:
    """JP 이름 → 우리 표기. 정본은 `shared/glossary`(몬스터·인물), `extra` 가 덮어쓴다.

    Ａ~Ｄ·♀♂ 꼬리는 개체 구분이라 표기에서 그대로 살린다 — 사전엔 밑말만 있다.
    """
    g = json.loads((common.ROOT / "shared" / "glossary" / "eiyuu.json").read_text())["categories"]
    idx: dict[str, str] = {}
    for cat in ("monster", "person"):
        for k, v in g[cat].items():
            idx.setdefault(_norm(k), v)
    for k, v in (extra or {}).items():
        idx[_norm(k)] = v
    out, missing = {}, []
    for jp in names():
        hit = idx.get(_norm(jp))
        if hit is None and jp and jp[-1] in "ＡＢＣＤ♀♂":
            base = idx.get(_norm(jp[:-1]))
            hit = None if base is None else base + jp[-1]
        if hit is None:
            missing.append(jp)
        else:
            out[jp] = hit
    return out, sorted(missing)


def patch_blocks(rel: int, kr: dict[str, str], table, errors: list[str]) -> tuple[list[dict], int]:
    """컨테이너 하나의 블록들에 우리 이름을 박는다. (블록, 갈아 끼운 칸 수)"""
    import font

    blocks = parse(rel)
    hit = 0
    for b in blocks:
        data = bytearray(b["data"])
        targets: dict[int, str] = {}
        for r in records(bytes(data)):
            name = kr.get(r["jp"])
            if not name:
                continue
            if r["ind"] is not None:
                # 간접이면 **대상 문자열**을 갈아 끼운다 — 칸에는 주소와 꼬리가 그대로 남는다.
                base = name[: len(name) - len(r["tail"])] if r["tail"] else name
                old = targets.setdefault(r["ind"], base)
                if old != base:
                    errors.append(f"간접 이름 충돌 rel{rel} +{r['ind']:04X}: {old} vs {base}")
                continue
            enc = font.encode(name, table) + b"\x06"
            if len(enc) > NAME_LEN:
                errors.append(f"몬스터 「{r['jp']}」→「{name}」 {len(enc)}B > {NAME_LEN}B")
                continue
            a = r["off"] + NAME_OFF
            data[a : a + NAME_LEN] = enc + b"\0" * (NAME_LEN - len(enc))
            hit += 1
        for off, base in targets.items():
            room = len(bytes(data[off:]).split(b"\x06")[0]) + 1
            enc = font.encode(base, table) + b"\x06"
            if len(enc) > room:
                errors.append(f"긴 이름 「{base}」 {len(enc)}B > {room}B (rel{rel} +{off:04X})")
                continue
            data[off : off + len(enc)] = enc
            hit += 1
        b["data"] = bytes(data)
    return blocks, hit


def apply(f, table, touched, extra: dict[str, str] | None = None) -> dict:
    """이름칸을 제자리로 갈아 끼우고 컨테이너를 다시 깐다(풀린 길이는 안 바뀐다)."""
    from shared.disc import mode1

    kr, missing = kr_names(extra)
    if missing:
        raise ValueError("몬스터 표기 미등재: " + " · ".join(missing))
    errors: list[str] = []
    n = 0
    for rel in CONTAINERS:
        blocks, hit = patch_blocks(rel, kr, table, errors)
        if not hit:
            continue
        n += hit
        nsec = (max(b["src"] - BASE + b["packed"] for b in parse(rel)) - 1) // common.USER + 1
        new = pack(blocks)
        # ⚠ 칸은 **원본이 쓰던 섹터 수**다 — 로더가 그만큼만 읽으므로 넘기면 조용히 잘린다.
        room = nsec * common.USER
        if len(new) > room:
            errors.append(f"rel {rel} 컨테이너 {len(new)}B > 칸 {room}B({nsec}섹터)")
            continue
        lba = common.T2_SECTOR + rel
        mode1.write_at(
            f,
            lba,
            common.USER * 8,
            0,
            new,
            label=f"battle rel{rel}",
            expect=common.track_data(rel, 8)[: len(new)],
        )
        for i in range((len(new) - 1) // common.USER + 1):
            touched.append((lba + i, 1))
    if errors:
        raise ValueError("전투 이름 " + str(len(errors)) + "건:\n  " + "\n  ".join(errors))
    return {"monsters": n}


def verify(iso: Path, table, extra: dict[str, str] | None = None) -> int:
    """구운 이미지에서 전투 컨테이너를 다시 풀어 **의도한 블록과 바이트로** 대조한다.

    이름을 글자로 되읽지 않는 이유: 우리 코드(리드 F0~F8)는 SJIS 가 아니라 이름 파서가 못 읽는다.
    블록 전체를 바이트로 대조하면 파서 없이도 「푼 결과가 뜻대로인가」가 닫힌다.
    """
    raw = iso.read_bytes()
    kr, _ = kr_names(extra)
    checked = 0
    for rel in CONTAINERS:
        want, hit = patch_blocks(rel, kr, table, [])
        if not hit:
            continue
        cont = b"".join(
            raw[(common.T2_SECTOR + rel + i) * common.RAW + 16 :][: common.USER] for i in range(8)
        )
        dl = (cont[0] | cont[1] << 8) - BASE
        ents = [
            (cont[i] | cont[i + 1] << 8, cont[i + 2] | cont[i + 3] << 8) for i in range(0, dl, 4)
        ]
        if len(ents) != len(want):
            raise ValueError(f"rel {rel}: 되읽은 블록 {len(ents)} ≠ {len(want)}")
        for (src, ln), w in zip(ents, want, strict=True):
            got, _ = lz.decode(cont[src - BASE :], ln)
            if got != w["data"]:
                raise ValueError(f"rel {rel} src{src:04X}: 되읽은 블록이 뜻과 다르다")
            checked += 1
    return checked


def glyph_chars(extra: dict[str, str] | None = None) -> set[str]:
    import font

    kr, _ = kr_names(extra)
    return {c for v in kr.values() for c in v if font.needs_glyph(c)}
