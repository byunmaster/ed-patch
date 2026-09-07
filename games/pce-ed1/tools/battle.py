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

import itertools
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import lz
import messages as M

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
    import sys as _sys

    common.verify_originals()
    print("전투 컨테이너", check())
    if "--check" not in _sys.argv:  # 목록은 원문이라 게이트에선 안 찍는다
        for jp, where in sorted(names().items()):
            print(f"  {jp}  \u00d7{len(where)}")


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


def patch_blocks(
    rel: int, kr: dict[str, str], table, errors: list[str]
) -> tuple[list[dict], int, int]:
    """컨테이너 하나의 블록들에 우리 이름·문구를 박는다. (블록, 이름 칸 수, 문구 수)"""
    import font

    blocks = parse(rel)
    msgs = _msgs()
    hit = 0
    nmsg = 0
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
        nmsg += patch_msgs(data, msgs, table, errors, f"rel{rel} blk")
        b["data"] = bytes(data)
    return blocks, hit, nmsg


def apply(f, table, touched, extra: dict[str, str] | None = None) -> dict:
    """이름칸을 제자리로 갈아 끼우고 컨테이너를 다시 깐다(풀린 길이는 안 바뀐다)."""
    from shared.disc import mode1

    kr, missing = kr_names(extra)
    if missing:
        raise ValueError("몬스터 표기 미등재: " + " · ".join(missing))
    errors: list[str] = []
    n = 0
    m = 0
    for rel in CONTAINERS:
        blocks, hit, nmsg = patch_blocks(rel, kr, table, errors)
        if not (hit or nmsg):
            continue
        n += hit
        m += nmsg
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
    return {"monsters": n, "msgs": m}


def verify(iso: Path, table, extra: dict[str, str] | None = None) -> int:
    """구운 이미지에서 전투 컨테이너를 다시 풀어 **의도한 블록과 바이트로** 대조한다.

    이름을 글자로 되읽지 않는 이유: 우리 코드(리드 F0~F8)는 SJIS 가 아니라 이름 파서가 못 읽는다.
    블록 전체를 바이트로 대조하면 파서 없이도 「푼 결과가 뜻대로인가」가 닫힌다.
    """
    raw = iso.read_bytes()
    kr, _ = kr_names(extra)
    checked = 0
    for rel in CONTAINERS:
        want, hit, _ = patch_blocks(rel, kr, table, [])
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


TOKEN = re.compile(r"\{([0-9A-F]{2})\}")


def _msgs() -> dict[str, str]:
    f = common.GAME_DIR / "script" / "sys" / "battle.json"
    return json.loads(f.read_text()).get("messages", {}) if f.exists() else {}


# 블록이 자랄 수 있는 상한 — **전투 화면에서 잰 값**(2026-09-06, 슬라임전 뱅크 0x74 덤프).
# 블록은 +0x400 에 풀리고, 그 위로 게임이 실제로 쓰는 첫 자리가 **+0x0B00** 이다(그 사이 1,340B 는
# 전투 내내 0). 🔴 정적으로 「원본에서 0 이 아닌 첫 자리」로 잡았던 가설은 +0xF0A(2,826B)라
# **1,000B 나 헐거웠다** — 「0 이니 빈 자리」가 계약이 아니라는 걸 또 확인했다.
# ⚠ 잰 것은 **한 전투**다. 더 큰 전투가 +0x0B00 아래를 더 쓰면 여기가 좁아진다 — QA 에서 다시 잰다.
SAFE_UNPACKED = 0x0B00 - 0x400


def patch_msgs(data: bytearray, msgs: dict[str, str], table, errors: list[str], where: str) -> int:
    """전투 문구를 갈아 끼운다. **자리를 안 옮기고**, 넘치면 `0F` 로 블록 꼬리에 잇는다.

    자리에 들어가면 제자리에 쓴다. 넘치면 원래 자리엔 `0F <주소>` 셋만 남기고 **문안 전체**를
    블록 끝에 덧붙인다. 블록의 풀린 길이는 디렉터리가 들고 있어 우리가 늘릴 수 있다.

    🔴 **원작은 전투 문구에서 이 문법을 사실상 안 쓴다**(2026-09-07 전수, pc98 중계로 다시 셈).
    원작 전투 블록의 `0F` 173개 중 **문구 본문의 옵코드 자리에 선 것은 0**이고, 뒤 2B 가 그 블록
    안 주소로 읽히는 건 둘(rel 194 blk#12)뿐인데 **우리가 손대는 단위 밖**이다.
    ⇒ 그러니 「원작도 쓴다」가 아니라 **「화면에서 도는 걸 봤다」가 유일한 근거**다 —
    「슬라임이 나타났다.」가 이 경로로 들어가 인게임에 떴다(`docs/img/battle-appear-kr.png`).
    ⚠ 확인된 건 **등장 문구 계열**이다. 다른 계열(데미지·승리·주문)은 호출 자리가 달라
    **화면으로 따로 봐야 한다.** 안 보고 늘리면 pc98 이 사흘을 태운 그 자리다.

    ⚠ 꼬리(원래 자리의 남은 바이트)는 **원본 그대로** 둔다 — 참조 스캔이 못 본 참조가 조각
    중간을 가리켜도 최악이 「그 자리만 일본어」다.
    """
    from sysbuild import encode_tokens

    n = 0
    for u in msg_units(bytes(data)):
        kr = msgs.get(msg_key(u["body"]))
        if not kr:
            continue
        jp_tok = TOKEN.findall(render(u["body"]))
        if TOKEN.findall(kr) != jp_tok:
            errors.append(f"{where} +{u['off']:04X} 「{kr}」 제어코드가 원문과 다르다 {jp_tok}")
            continue
        enc = encode_tokens(kr, table)
        if u["term"] is not None:
            enc += bytes([u["term"]])
        if len(enc) <= u["room"]:
            data[u["off"] : u["off"] + len(enc)] = enc
            n += 1
            continue
        # 넘친다 — `0F` 로 잇는다
        if u["room"] < 3:
            errors.append(
                f"{where} +{u['off']:04X} 「{kr}」 자리가 {u['room']}B 라 0F 도 못 넣는다"
            )
            continue
        if len(data) + len(enc) > SAFE_UNPACKED:
            errors.append(
                f"{where} +{u['off']:04X} 「{kr}」 블록이 {len(data) + len(enc)}B 로 자란다"
                f" — 상한 {SAFE_UNPACKED}B"
            )
            continue
        tgt = LOAD_ADDR + len(data)
        data += enc
        data[u["off"] : u["off"] + 3] = bytes([0x0F, tgt & 0xFF, tgt >> 8])
        n += 1
    return n


def glyph_chars(extra: dict[str, str] | None = None) -> set[str]:
    import font

    kr, _ = kr_names(extra)
    chars = {c for v in kr.values() for c in v if font.needs_glyph(c)}
    for v in _msgs().values():
        chars |= {c for c in TOKEN.sub("", v) if font.needs_glyph(c)}
    return chars


# ─── 전투 문구 ─────────────────────────────────────────────────────────────
# 레코드 표 뒤에는 전투 코드와 씬 문법 문구(「…が現れた。」)가 섞여 있다. 경계를 어떻게 잡나:
#
#   **범위**는 탐욕 스캔이 준다 — 글자(≥0x24, 2B)와 사이에 낀 제어코드를 먹다가,
#   다음이 글자가 아닌 제어코드를 만나면 그것이 **종단**이다.
#   **자르는 자리**는 코드가 가리키는 주소가 준다 — 한 덩이 안을 가리키는 참조가 있으면
#   거기서 끊는다(공유 조각이다. sysmsg 의 `0F` 이어쓰기와 같은 사정).
#
# ⚠ 참조 스캔은 **분할 즉치만** 본다(`LDA #lo / STA / LDA #hi / STA`). 표·계산으로 가리키는
#   자리는 못 본다 — 그래서 되쓰기는 **자리를 안 옮긴다**. 못 본 참조가 있어도 최악이
#   「그 조각만 일본어로 남는다」이지 깨지지 않는다.
SPLIT_PTR = re.compile(rb"\xa9(.)(?:\x85(.)|\x8d(..))\xa9(.)(?:\x85(.)|\x8d(..))", re.DOTALL)
MSG_TERM = 0x24  # 이 값 미만은 제어코드
# 글자 사이에 낄 수 있는 제어코드 — **피연산자가 없고 문장을 안 끝내는 것만**이다.
# 🔴 `0F/10~15` 는 뒤에 주소 2B 를 달고 다닌다. 낀 제어코드로 보면 **주소 바이트가 글자로 읽혀**
#    문구에 딸려 들어오고, 되쓰면 점프 주소를 덮는다(실측 「の左{0F}鞍」).
# 🔴 `00·03·05·06·07·0A` 는 **문장 끝**이다(status 3절). 이걸 낀 코드로 보면 **별개 문장 둘이 한
#    단위로 뭉치고**, 게임이 뒤 문장을 따로 가리키면 우리 `0F` 를 안 거쳐 **그 문장만 일본어로
#    남는다** — 인게임에서 「スライムが現れた。」로 발각(2026-09-06). 문장 끝은 단위를 끊는다.
INLINE_OPS = frozenset({0x01, 0x02, 0x04, 0x0B, 0x0E, 0x1E, 0x1F, 0x20, 0x22})


def is_char(data: bytes, i: int) -> bool:
    """전각 SJIS 두 바이트인가.

    ⚠ 인터프리터 자체는 「≥0x24 면 2바이트 글자」로만 보지만 **스캔에는 그 규칙을 못 쓴다** —
    포인터 표(`40 C5 46 C5 …`)가 글자로 읽혀 코드가 문구에 딸려 들어온다(실측: 792단위 중
    391이 그런 쓰레기였다). 스캔은 **유효한 전각 코드**만 글자로 센다.
    """
    if i + 1 >= len(data):
        return False
    a, b = data[i], data[i + 1]
    if not ((0x81 <= a <= 0x9F or 0xE0 <= a <= 0xEF) and 0x40 <= b <= 0xFC and b != 0x7F):
        return False
    try:  # 유효한 리드/트레일 안에도 **미정의 코드**가 있다 — 그게 걸리면 글자 시작이 한 칸 밀린 것이다
        data[i : i + 2].decode("cp932")
    except UnicodeDecodeError:
        return False
    return True


def code_refs(data: bytes) -> set[int]:
    """블록 코드가 분할 즉치로 가리키는, **글자로 시작하는** 블록 안 오프셋."""
    out = set()
    for m in SPLIT_PTR.finditer(data):
        lo, hi = m.group(1)[0], m.group(4)[0]
        z1 = m.group(2)[0] if m.group(2) else (m.group(3)[0] | m.group(3)[1] << 8)
        z2 = m.group(5)[0] if m.group(5) else (m.group(6)[0] | m.group(6)[1] << 8)
        if z2 != z1 + 1:
            continue
        off = (lo | hi << 8) - LOAD_ADDR
        if 0 <= off < len(data) - 1 and is_char(data, off):
            out.add(off)
    return out


BRANCH_OPS = frozenset(range(0x0F, 0x16))
"""주소 2바이트를 데리고 다니는 옵코드 — 0F 점프 · 10 호출 · 11/12 조건 · 13/14 플래그 · 15 기계어.

🔴 **주소 바이트가 유효한 전각 코드면 런 머리로 딸려 들어온다.** 거기에 우리 문안을 쓰면
점프가 쓰레기 주소로 가서 **화면이 아니라 진행이 깨진다**(pc98 이 같은 자리에서 물렸다,
중계 2026-09-07). ⚠ `0F` 하나만 보면 놓친다 — 실측 7자리 중 여섯이 `10` 이었다.
"""


def branch_operands(data: bytes) -> set[int]:
    """분기 옵코드의 주소 바이트 자리. **주소가 이 블록 안을 가리킬 때만** 센다.

    ⚠ 둘째 축이 없으면 전투 청크에 널린 데이터 `0F`(대개 `CMP #$0F` 즉치)를 통째로 오탐한다.
    """
    out = set()
    for i, c in enumerate(data[: len(data) - 2]):
        if c not in BRANCH_OPS:
            continue
        tgt = data[i + 1] | (data[i + 2] << 8)
        if LOAD_ADDR <= tgt < LOAD_ADDR + len(data):
            out.add(i + 1)
            out.add(i + 2)
    return out


def text_runs(data: bytes, start: int) -> list[tuple[int, int, int | None]]:
    """(시작, 본문 끝, 종단바이트|None) — start 부터 훑는다."""
    out = []
    i = start
    n = len(data)
    operands = branch_operands(data)
    while i < n - 1:
        if i in operands:  # 분기 주소는 글자가 아니다 — 머리로 삼으면 점프를 덮어쓴다
            i += 1
            continue
        if not is_char(data, i):
            i += 1
            continue
        j, chars = i, 0
        while j < n - 1:
            if is_char(data, j):
                j += 2
                chars += 1
                continue
            if chars and data[j] in INLINE_OPS and is_char(data, j + 1):  # 낀 제어코드
                j += 1
                continue
            break
        if chars >= 3:
            term = data[j] if j < n and data[j] < MSG_TERM else None
            out.append((i, j, term))
            i = j + 1
        else:
            i += 1
    return out


def msg_units(data: bytes) -> list[dict]:
    """전투 문구 단위. 탐욕 범위를 **코드 참조에서 끊어** 공유 조각을 지킨다."""
    start = len(records(data)) * REC
    refs = code_refs(data)
    out = []
    for a, b, term in text_runs(data, start):
        cuts = sorted({a} | {r for r in refs if a < r < b}) + [b]
        for k, (lo, hi) in enumerate(itertools.pairwise(cuts)):
            last = k == len(cuts) - 2
            out.append(
                {
                    "off": lo,
                    "body": data[lo:hi],
                    "term": term if last else None,
                    "room": (hi - lo) + (1 if last and term is not None else 0),
                }
            )
    return out


def render(body: bytes) -> str:
    """본문 → 사람이 읽는 꼴. 제어코드는 `{XX}` 로 둔다(sysbuild.encode_tokens 와 짝)."""
    out = []
    i = 0
    while i < len(body):
        if body[i] >= MSG_TERM:
            out.append(body[i : i + 2].decode("cp932", errors="replace"))
            i += 2
        else:
            out.append(f"{{{body[i]:02X}}}")
            i += 1
    return "".join(out)


def msg_key(body: bytes) -> str:
    """문구 열쇠 — **제어코드를 포함한** 원문의 해시(`shared/text/line_key`).

    ⚠ 원문은 정본에 안 담는다(루트 「저작권」) — 그래서 열쇠가 정본의 키다.
    ⚠ sysmsg 는 토큰을 뺀 원문으로 열쇠를 만드는데 **여기선 포함**한다. 같은 글이라도 `{02}`(행위자
    이름)·`{01}`(개행) 자리가 다른 단위가 있어서, 토큰을 빼면 320개로 뭉쳐 **한 문안이 다른 자리에
    쓰이며 토큰을 잃는다**(실측: 337 → 320). 타이틀 공용 사전과는 열쇠가 갈리지만 그 재사용률은
    3.2% 라 정확성을 택했다.
    """
    return M.jp_key(render(body))


def msg_jp(body: bytes) -> str:
    """열쇠를 만들 때 쓰는 「토큰 없는 원문」. 덤프에만 쓴다(커밋 금지)."""
    out = []
    i = 0
    while i < len(body):
        if is_char(body, i):
            out.append(body[i : i + 2].decode("cp932"))
            i += 2
        else:
            i += 1
    return "".join(out)


def dump_messages() -> int:
    """열쇠↔원문 대조표를 `work/derived/battle/` 로 — ⚠ 원문이라 커밋하지 않는다."""
    out_dir = common.OUT_DIR / "battle"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = {}
    for c in scan():
        for k, b in enumerate(c["blocks"]):
            for u in msg_units(b["data"]):
                jp = msg_jp(u["body"])
                key = msg_key(u["body"])
                r = rows.setdefault(
                    key, {"jp": jp, "tokens": render(u["body"]), "room": u["room"], "at": []}
                )
                r["room"] = min(r["room"], u["room"])
                r["at"].append(f"{c['rel']}:{k}:{u['off']:04X}")
    (out_dir / "messages.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    return len(rows)
