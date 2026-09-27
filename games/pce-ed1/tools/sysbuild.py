"""시스템 문구 되쓰기 — 정본(`script/sys/`) + 공용 사전(`shared/glossary`)을 본 프로그램 이미지에 **제자리**로.

정본:
    script/sys/names.json   {"items": {JP: KR}, "spells": …, "files": …, "speakers": …, "chapter": {JP: KR}}
                            — 사전(shared/glossary/eiyuu.json)이 정본이고 여기는 **덮어쓰기/보충**(폭 초과·미등재)
    script/sys/labels.json  {JP(토큰 포함 원문): KR(토큰 포함)}   메뉴 라벨
    script/sys/sysmsg.json  {열쇠: KR(토큰 포함)}                시스템 메시지 본문(앞뒤 옵코드는 도구가 보존)
    script/sys/screens.json {"뱅크:오프셋": [줄…]}              부팅·파일 선택 화면(줄 수는 원본 그대로)

규칙(2026-09-05): 주소를 안 옮긴다.
    고정폭 표 — 폭 안에서 원래 패딩 방식으로(아이템·주문 0x20 오른쪽 정렬 · 파일 지명 전각 공백)
    라벨 — 원래 길이 안, 남는 자리 00
    시스템 메시지 — 앞뒤 옵코드 보존, 본문 교체. 짧아졌는데 원문이 다음 단위로 흘러가면 `0F 다음주소` 로 잇는다
    (씬 인터프리터·단순 렌더러 둘 다 <0x20 에서 멈추므로 안전). 넘치면 빌드 실패 — 문안을 줄인다.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import common
import font
import freespace
import sysstrings as S

from shared.disc import mode1

SYS_DIR = common.GAME_DIR / "script" / "sys"
TOK = re.compile(r"\{([0-9A-Fa-f]+)\}")
TERMINAL_OPS = {
    0x00,
    0x03,
    0x06,
    0x07,
    0x0A,
    0x0D,
}  # 0A·0D 도 단위 끝에서만 나온다(실측) — 되돌아가는 옵코드로 본다


class SysError(Exception):
    pass


def glossary() -> dict[str, str]:
    """JP → 우리 표기. **공용 `glossary.all_names()` 가 준다** — 우리가 정본을 훑지 않는다.

    🔴 옛 판은 정본을 **평평하게** 훑어 `_aliases` 의 값(`強さ@전투커맨드` 꼴)까지 표시 문안으로
    셌다(2026-09-08 실측: 게이트가 「정본에 없는 글자 `@능티`」로 울었다). **게임마다 「밑줄로
    시작하는 절은 건너뛴다」를 알 게 아니라** 공용이 `categories` 만 준다.
    """
    import glossary as G  # shared/ (common 이 sys.path 에 올린다)

    return {jp: kr for _c, jp, kr in G.all_names()}


def _load(name):
    p = SYS_DIR / name
    return json.loads(p.read_text()) if p.exists() else {}


def all_glyph_chars() -> set[str]:
    chars = set()
    names = _load("names.json")
    gl = glossary()
    for fam in S.FIXED:
        for r in S.read_fixed(fam):
            kr = names.get(fam, {}).get(r["jp"], gl.get(r["jp"]))
            if kr:
                chars |= {c for c in kr if font.needs_glyph(c)}
    for fam, reader in (("speakers", S.read_speakers), ("chapter", S.read_chapter)):
        for r in reader():
            kr = names.get(fam, {}).get(r["jp"], gl.get(r["jp"]))
            if kr:
                chars |= {c for c in kr if font.needs_glyph(c)}
    for k, v in _load("labels.json").items():
        if k != "_doc" and v is not None:  # null = 원본 유지로 판정한 것
            chars |= {c for c in TOK.sub("", v) if font.needs_glyph(c)}
    for v in _load("sysmsg.json").get("messages", {}).values():
        chars |= {c for c in TOK.sub("", v) if font.needs_glyph(c)}
    for k, v in _load("screens.json").items():
        if not k.startswith("_"):
            chars |= {c for line in v for c in line if font.needs_glyph(c)}
    for k, v in _load("extras.json").items():
        if not k.startswith("_"):
            chars |= {c for t in v for c in t if font.needs_glyph(c)}
    for k, v in _load("inline.json").items():
        if not k.startswith("_"):
            chars |= {c for c in v if font.needs_glyph(c)}
    return chars


def encode_tokens(text: str, table) -> bytes:
    """`{XX}` 토큰은 그 바이트로, 나머지는 font.encode."""
    out = bytearray()
    pos = 0
    for m in TOK.finditer(text):
        out += font.encode(text[pos : m.start()], table)
        out += bytes.fromhex(m.group(1))
        pos = m.end()
    out += font.encode(text[pos:], table)
    return bytes(out)


def _write(f, bank, off, data, expect, label, touched):
    rel, o = S.bank_rel(bank, off)
    lba = common.T2_SECTOR + rel
    mode1.write_at(f, lba, common.USER * 2, o, data, label=label, expect=expect)
    for i in range((o + len(data) - 1) // common.USER + 1):
        touched.append((lba + i, 1))


def _read(f, bank, off, n) -> bytes:
    """이미지에서 뱅크 오프셋의 유저 데이터를 읽는다(섹터 경계를 걸쳐도 된다)."""
    out = bytearray()
    while len(out) < n:
        rel, o = S.bank_rel(bank, off + len(out))
        f.seek((common.T2_SECTOR + rel) * common.RAW + common.USER_OFF + o)
        out += f.read(min(n - len(out), common.USER - o))
    return bytes(out)


def check_keys(errors: list[str]) -> dict[str, int]:
    """🔴 **정본에 있는데 아무 데도 안 맞는 열쇠**를 잡는다.

    문안을 써 놨는데 열쇠가 한 글자 어긋나면 **조용히 아무 일도 안 일어난다** — 빌드도 게이트도
    초록불인데 화면만 일본어다. 실측(2026-09-06): `labels.json` 셋이 그 상태였다
    (`はい` ↔ 읽히는 꼴 `{04}{02}はい` · `{09}{02}` ↔ `{0902}` · 「プレイ時間」 뒤 `：　：` 누락).
    ⚠ 반대쪽(원문에 있는데 정본에 없는 것)은 **할 일**이지 실패가 아니다 — 여기선 안 본다.
    """
    seen = {}
    labels = _load("labels.json")
    lb = S.read_labels()
    keys = {r["jp"] for r in lb} | {f"@{r['addr']:04X}" for r in lb}
    stray = [k for k in labels if k != "_doc" and k not in keys]
    seen["labels"] = len(stray)
    errors += [f"labels.json 열쇠가 아무 라벨과도 안 맞는다: {k!r}" for k in stray]

    msgs = _load("sysmsg.json").get("messages", {})
    mk = {r["key"] for r in S.read_sysmsg()}
    stray = [k for k in msgs if k not in mk]
    seen["sysmsg"] = len(stray)
    errors += [f"sysmsg.json 열쇠가 아무 메시지와도 안 맞는다: {k!r}" for k in stray]

    scr = _load("screens.json")
    sk = {c["key"] for c in S.read_screens()}
    stray = [k for k in scr if not k.startswith("_") and k not in sk]
    seen["screens"] = len(stray)
    errors += [f"screens.json 열쇠가 아무 화면과도 안 맞는다: {k!r}" for k in stray]

    ex = _load("extras.json")
    ek = {g["key"] for g in S.read_extras()}
    stray = [k for k in ex if not k.startswith("_") and k not in ek]
    seen["extras"] = len(stray)
    errors += [f"extras.json 열쇠가 아무 덩이와도 안 맞는다: {k!r}" for k in stray]

    import battle as B

    bt = _load("battle.json").get("messages", {})
    if bt:
        live = {
            B.msg_key(u["body"])
            for c in B.scan()
            for b in c["blocks"]
            for u in B.msg_units(b["data"])
        }
        stray = [k for k in bt if k not in live]
        seen["battle"] = len(stray)
        errors += [f"battle.json 열쇠가 아무 문구와도 안 맞는다: {k!r}" for k in stray]

    inl = _load("inline.json")
    ik = {r["key"] for r in S.read_inline()}
    stray = [k for k in inl if not k.startswith("_") and k not in ik]
    seen["inline"] = len(stray)
    errors += [f"inline.json 열쇠가 없다: {k!r}" for k in stray]

    names = _load("names.json")
    for fam in ("items", "spells", "files", "places"):
        jp = {r["jp"] for r in S.read_fixed(fam)}
        stray = [k for k in names.get(fam, {}) if k not in jp]
        seen[fam] = len(stray)
        errors += [f"names.json[{fam}] 열쇠가 표에 없다: {k!r}" for k in stray]
    return seen


def apply(f, table, touched) -> dict:
    names = _load("names.json")
    gl = glossary()
    stats = {}
    errors: list[str] = []
    check_keys(errors)  # 정본에 써 놓고 안 붙는 열쇠부터 잡는다

    def kr_of(fam, jp):
        return names.get(fam, {}).get(jp, gl.get(jp))

    # 고정폭 표
    for fam, (bank, base, stride, w, _n, pad, _tail) in S.FIXED.items():
        b = S.bank_bytes(bank)
        cnt = 0
        for r in S.read_fixed(fam):
            kr = kr_of(fam, r["jp"])
            if not kr or not r["jp"]:
                continue
            enc = font.encode(kr, table)
            if len(enc) > w:
                errors.append(f"{fam} 「{r['jp']}」→「{kr}」 {len(enc)}B > {w}B")
                continue
            if fam == "files":
                new = enc + pad * ((w - len(enc)) // 2)
            elif fam == "places":
                # HUD 이름칸: 「이름 06」 + 00 패딩. 12B 를 꽉 채우면 06 을 안 쓴다
                # (렌더러 `$92A0` 가 06 까지 스캔하고, 없으면 12B 를 끝으로 본다)
                new = enc if len(enc) == w else enc + b"\x06" + b"\0" * (w - len(enc) - 1)
            else:
                new = S._pad_right_align(enc, w, pad)
            off = base + r["i"] * stride
            _write(f, bank, off, new, b[off : off + w], f"{fam}[{r['i']}]", touched)
            cnt += 1
        stats[fam] = cnt
    # 공용 화자(64B 슬롯) · 장 제목(32B, 0x20 패딩)
    b74 = S.bank_bytes(0x74)
    cnt = 0
    for r in S.read_speakers():
        kr = kr_of("speakers", r["jp"])
        if kr:
            enc = font.encode(kr, table) + b"\x06"
            # 🔴 64B 슬롯은 **캐릭터 레코드**다(이름 16B + 능력치 48B). 이름 칸 16B 만 쓴다 —
            #    슬롯을 통째로 썼다가 능력치가 0 이 돼 HUD 에 파티원 넷이 떴다(2026-09-05).
            if len(enc) > 16:
                raise SysError(f"speaker {kr} 가 이름 칸 16B 를 넘는다")
            off = 0x330 + r["i"] * 64
            _write(
                f,
                0x74,
                off,
                enc + b"\0" * (16 - len(enc)),
                b74[off : off + 16],
                f"speaker[{r['i']}]",
                touched,
            )
            cnt += 1
    stats["speakers"] = cnt
    for r in S.read_chapter():
        kr = kr_of("chapter", r["jp"])
        if kr:
            enc = font.encode(kr, table)
            raw = bytes.fromhex(r["raw"])
            if len(enc) > len(raw):
                raise SysError("chapter 제목이 32B 를 넘는다")
            lead = (len(raw) - len(enc)) // 2
            new = b" " * lead + enc + b" " * (len(raw) - len(enc) - lead)
            _write(f, 0x74, 0x198, new, raw, "chapter", touched)
            stats["chapter"] = 1
    # 라벨
    labels = _load("labels.json")
    b6d = S.bank_bytes(0x6D)
    cnt = 0
    for r in S.read_labels():
        kr = labels.get(
            f"@{r['addr']:04X}", labels.get(r["jp"])
        )  # 같은 JP 가 뜻이 다를 때 주소로 덮는다
        if kr is None:  # 미판정이거나 **원본 유지로 판정**(null) — 둘 다 안 건드린다
            continue
        enc = encode_tokens(kr, table)
        if len(enc) > r["room"]:
            errors.append(f"label 「{r['jp']}」→「{kr}」 {len(enc)}B > {r['room']}B")
            continue
        # ⚠ 00 으로 채우면 안 된다 — 상태 화면은 라벨을 00 개수로 세어 찾는다(실측: 지혜 뒤 라벨이 비었다).
        #   전각 공백으로 채운다(왼쪽 정렬이라 안 보인다). 남는 길이가 홀수면 문안을 다시 맞춘다.
        rest = r["room"] - len(enc)
        if rest % 2:
            errors.append(
                f"label 「{r['jp']}」→「{kr}」 남는 {rest}B 가 홀수 — 전각 공백으로 못 채운다"
            )
            continue
        new = enc + b"\x81\x40" * (rest // 2)
        _write(
            f,
            0x6D,
            r["off"],
            new,
            b6d[r["off"] : r["off"] + r["room"]],
            f"label {r['addr']:04X}",
            touched,
        )
        cnt += 1
    stats["labels"] = cnt
    # 시스템 메시지
    msgs = _load("sysmsg.json").get("messages", {})
    cnt = 0
    plan = []  # (r, 새 바이트(패딩 전), 원본)
    spills = []  # 자리를 넘는 조각 — 다른 단위의 남는 00 자리로 옮기고 `0F` 로 뛴다
    for r in S.read_sysmsg():
        kr = msgs.get(r["key"])
        if kr is None:
            continue
        lead = b"".join(bytes.fromhex(t) for t in r["lead"])
        tail = b"".join(bytes.fromhex(t) for t in r["tail"])
        body = encode_tokens(kr, table)
        new = lead + body + tail
        orig = b6d[r["off"] : r["off"] + r["room"]]
        core_len = len(orig.rstrip(b"\xff").rstrip(b"\0"))
        # 원문이 방을 꽉 채웠고(패딩 00 없음) 꼬리가 종료·점프가 아니면 다음 단위로 흘러가는 조각이다
        flows_on = core_len == r["room"] and not (
            tail and (tail[-1] in TERMINAL_OPS or tail[-3:-2] == b"\x0f")
        )
        if len(new) < core_len and flows_on:
            nxt = 0x8000 + r["off"] + core_len
            new += bytes([0x0F, nxt & 0xFF, nxt >> 8])
        if len(new) > r["room"]:
            # 🔑 **옮겨 싣기**(2026-09-24) — 조각 「は」(3·4B)에 「은/는 」(조사 2B + 공백 2B)이 안 들어가
            #    「아그니쟈는세리오스에」로 붙었다. 원 자리엔 `0F 새주소`(3B)만 남긴다.
            #    ⚠ `0F` 는 씬 인터프리터만 따라간다 — 전투 문구 경로(`$7047`)는 그 인터프리터다(09-06 트레이스).
            #    🆕 09-26: **흘러가는 조각도** 옮긴다 — 새 자리 끝에 `0F 원래_다음주소` 를 붙여 돌아온다
            #    (「에」→「에게」, 전투 「X에 N의 데미지」가 뒤 조각으로 이어진다).
            if r["room"] >= 3:
                if flows_on:
                    nxt = 0x8000 + r["off"] + core_len
                    new = lead + body + tail + bytes([0x0F, nxt & 0xFF, nxt >> 8])
                spills.append((r, new, orig))
                continue
            errors.append(
                f"sysmsg {r['addr']:04X} 「{r['jp']}」→「{kr}」 {len(new)}B > {r['room']}B{' (0F 이어쓰기 3B 포함)' if flows_on else ''}"
            )
            continue
        plan.append([r, new, orig])
    # 남는 자리: 우리가 쓴 단위의 끝(종료·점프 뒤)부터 방 끝까지 00 — 한 칸 띄우고 쓴다
    slack = sorted(
        (p[0]["off"] + len(p[1]) + 1, p[0]["off"] + p[0]["room"], i) for i, p in enumerate(plan)
    )
    extra: dict[int, bytearray] = {}  # plan 번호 → 덧붙일 바이트(끝 뒤 한 칸부터)
    # 🆕 09-26: 자투리가 모자라면 **선언한 빈 공간**(freespace.SPANS)으로 — 원본 기대 바이트부터 검산
    pool = freespace.Pool(freespace.spans())
    pool.check_original(S.bank_bytes)
    pool_writes = []  # (Span, 뱅크 안 오프셋, 바이트)
    spilled = {}  # 자투리로 옮긴 조각: 주소 → (새 논리 주소, 바이트)
    for r, new, orig in spills:
        for k, (lo, hi, i) in enumerate(slack):
            if hi - lo >= len(new):
                tgt = 0x8000 + lo
                extra.setdefault(i, bytearray()).extend(new)
                slack[k] = (lo + len(new), hi, i)
                spilled[r["addr"]] = (tgt, new)
                plan.append([r, bytes([0x0F, tgt & 0xFF, tgt >> 8]), orig])
                stats["sysmsg_spill"] = stats.get("sysmsg_spill", 0) + 1
                break
        else:
            got = pool.alloc(0x6D, len(new))
            if got is None:
                errors.append(
                    f"sysmsg {r['addr']:04X} 「{r['jp']}」 {len(new)}B — 옮겨 실을 빈자리가 없다"
                )
                continue
            span, off = got
            tgt = 0x8000 + off
            pool_writes.append((span, off, new, r))
            plan.append([r, bytes([0x0F, tgt & 0xFF, tgt >> 8]), orig])
            stats["sysmsg_pool"] = stats.get("sysmsg_pool", 0) + 1
    for span, off, data, r in pool_writes:
        _write(
            f,
            span.bank,
            off,
            data,
            bytes([span.fill]) * len(data)
            if span.fill is not None
            else S.bank_bytes(span.bank)[off : off + len(data)],
            f"sysmsg {r['addr']:04X} → 빈 공간 {span.bank:#x}+{off:#x}",
            touched,
        )
    moved = {r["addr"]: (0x8000 + off, data) for _s, off, data, r in pool_writes}
    moved.update(spilled)
    inplace = {}  # 제자리 조각: 주소 → 바이트(패딩 전)
    for i, (r, new, orig) in enumerate(plan):
        if r["addr"] not in moved:
            inplace[r["addr"]] = (r, bytes(new))
        if i in extra:
            new = new + b"\0" + bytes(extra[i])
        new += b"\0" * (r["room"] - len(new))
        assert len(new) == r["room"], (r["addr"], len(new), r["room"])
        _write(f, 0x6D, r["off"], new, orig, f"sysmsg {r['addr']:04X}", touched)
        cnt += 1
    # 되읽기 게이트 — **글 소실 없음**(관리자 공유 09-27: PS1·ps1-ed3+4 에서 조판·이주가 꼬리 글을 조용히 잃었다).
    # 모든 조각이 이미지에 **바이트 그대로** 있어야 한다: 제자리면 그 자리에, 옮겼으면 원 자리 = `0F 새주소` + 새 자리에.
    for addr, (r, data) in inplace.items():
        if _read(f, 0x6D, r["off"], len(data)) != data:
            raise SysError(f"sysmsg {addr:04X} 제자리 되읽기 실패 — 글이 사라졌다")
    for addr, (tgt, data) in moved.items():
        r = next(x for x in S.read_sysmsg() if x["addr"] == addr)
        head = _read(f, 0x6D, r["off"], 3)
        body = _read(f, 0x6D, tgt - 0x8000, len(data))
        if head != bytes([0x0F, tgt & 0xFF, tgt >> 8]) or body != data:
            raise SysError(f"sysmsg {addr:04X} 옮겨 싣기 되읽기 실패")
    stats["sysmsg"] = cnt
    # 부팅·파일 선택 화면 — 화면 총 길이를 지킨다(코드가 화면 머리를 절대주소로 가리킨다).
    # 줄 수·col·row 는 원본 그대로 쓰고, 남는 자리는 마지막 줄 뒤에 전각 공백으로 채운다.
    screens = _load("screens.json")
    cnt = 0
    for sc in S.read_screens():
        kr = screens.get(sc["key"])
        if kr is None:
            continue
        if len(kr) != len(sc["lines"]):
            errors.append(f"screen {sc['key']} 줄 수 {len(kr)} ≠ 원본 {len(sc['lines'])}")
            continue
        enc = [font.encode(t, table) for t in kr]
        for ln, t, e in zip(sc["lines"], kr, enc, strict=True):
            if ln["col"] + len(e) // 2 > S.SCREEN_COLS:
                errors.append(
                    f"screen {sc['key']} col{ln['col']} 「{t}」 {ln['col'] + len(e) // 2}칸 > {S.SCREEN_COLS}칸"
                )
        total = sum(3 + len(e) for e in enc) + 1
        if total > sc["room"]:
            errors.append(f"screen {sc['key']} {total}B > {sc['room']}B")
            continue
        enc[-1] += b"\x81\x40" * ((sc["room"] - total) // 2)
        if (sc["room"] - total) % 2:
            errors.append(
                f"screen {sc['key']} 남는 {sc['room'] - total}B 가 홀수 — 전각 공백으로 못 채운다"
            )
            continue
        new = b"".join(
            bytes([ln["col"], ln["row"]]) + e + b"\0"
            for ln, e in zip(sc["lines"], enc, strict=True)
        )
        new += b"\xff"
        assert len(new) == sc["room"], sc["key"]
        b78 = S.bank_bytes(sc["bank"])
        _write(
            f,
            sc["bank"],
            sc["off"],
            new,
            b78[sc["off"] : sc["off"] + sc["room"]],
            f"screen {sc['key']}",
            touched,
        )
        cnt += 1
    stats["screens"] = cnt
    # 오마케 모듈(사운드 테스트 · 도감 메뉴) — rel 458~459 의 00 종단 목록.
    # 🔴 포인터 표가 없고 **00 을 세어** 찾으므로 항목 수를 지키고, 남는 자리는 00 으로 채운다
    #    (전각 공백으로 채우면 마지막 항목 뒤에 빈칸이 붙어 보인다).
    extras = _load("extras.json")
    d458 = common.track_data(S.EXTRAS_REL, 2)
    cnt = 0
    for g in S.read_extras():
        items = extras.get(g["key"])
        if items is None:
            continue
        if len(items) != len(g["items"]):
            errors.append(f"extras[{g['key']}] 항목 {len(items)} ≠ 원본 {len(g['items'])}")
            continue
        blob = b"".join(font.encode(t, table) + b"\0" for t in items)
        if len(blob) > g["room"]:
            errors.append(f"extras[{g['key']}] {len(blob)}B > {g['room']}B")
            continue
        blob += b"\0" * (g["room"] - len(blob))
        lba = common.T2_SECTOR + S.EXTRAS_REL
        mode1.write_at(
            f,
            lba,
            common.USER * 2,
            g["off"],
            blob,
            label=f"extras {g['key']}",
            expect=d458[g["off"] : g["off"] + g["room"]],
        )
        for i in range(g["off"] // common.USER, (g["off"] + g["room"] - 1) // common.USER + 1):
            touched.append((lba + i, 1))
        cnt += 1
    stats["extras"] = cnt
    # 코드 안 낱개 문자열 — 「이름 06」, 06 뒤는 코드라 그 앞까지만 쓴다(남는 자리는 원본 그대로)
    inline = _load("inline.json")
    cnt = 0
    for r in S.read_inline():
        kr = inline.get(r["key"])
        if not kr:
            continue
        enc = font.encode(kr, table) + b"\x06"
        if len(enc) > r["room"]:
            errors.append(f"inline[{r['key']}] 「{kr}」 {len(enc)}B > {r['room']}B")
            continue
        b = S.bank_bytes(r["bank"])
        _write(
            f,
            r["bank"],
            r["off"],
            enc,
            b[r["off"] : r["off"] + len(enc)],
            f"inline {r['key']}",
            touched,
        )
        cnt += 1
    stats["inline"] = cnt
    if errors:
        raise SysError(
            "시스템 문구 " + str(len(errors)) + "건이 자리를 넘는다:\n  " + "\n  ".join(errors)
        )
    return stats
