"""씬 대사 블록의 **구조(제어 코드 열)** — 글자 바이트를 빼고 엔진이 해석하는 자리만 남긴다.

왜. 재배치·꼬리 옮기기·쪽 넘김·채움을 한 빌드는 글자가 아니라 **제어 바이트**를 조용히 틀린다
(ss-ed3 10-21: 채움 바이트가 다음 블록 호출을 막아 대사가 통째로 빠졌다). 문안·조판 게이트는 글자를 보고,
하네스는 한 블록씩 띄워 보므로 못 본다. 여기는 원본 블록과 빌드 블록에서 글자를 뺀 열을 짝지어 비교한다.

PS1 씬의 블록 문법(원본 전수 확인 — `work/derived/scn_jp`):
  [ %c 화자 %c ↵ ] 본문(줄은 0x0A) … [ %c ] 00 패딩(블록 길이가 4의 배수가 되도록 1~4B)
  - `%c`(25 63): 엔진이 인자를 소비하는 **창 제어**(색·대기·종단) — 개수가 호출 코드가 넘기는 인자와 맞아야 한다
  - `%s`(25 73): 이름 주입 · `%d`(25 64): 숫자 주입
  - 0x0A: 줄 바꿈 — 번역은 조판이 다시 하므로 **개수는 달라져도 된다**(창당 줄 수는 별도 게이트)
  - 00: 문자열 종단. 블록 사이 빈 틈도 00 이어야 한다(다른 값이면 앞 문자열이 이어 읽힌다)
  - 그 외 제어 바이트(0x01~0x1F, 0x0A 제외)는 그대로 열에 남긴다

토큰: C(%c) s(%s) d(%d) N(0x0A) Z(종단 00 들) x<hh>(그 외 제어 바이트). 글자(2B SJIS/한글 코드·ASCII·반각)는 뺀다.
"""

MC = b"\x25\x63"
PS = b"\x25\x73"
PD = b"\x25\x64"


def _is_lead(b):
    return 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xFC


def skeleton(raw):
    """블록 바이트 → 제어 코드 열(튜플). 글자는 건너뛴다. 끝 00 들은 `Z` 하나로 접고 개수는 별도로 센다."""
    toks = []
    i, n = 0, len(raw)
    while i < n:
        b = raw[i]
        if b == 0x25 and i + 1 < n and raw[i + 1] in (0x63, 0x73, 0x64):
            toks.append({0x63: "C", 0x73: "s", 0x64: "d"}[raw[i + 1]])
            i += 2
        elif b == 0x0A:
            toks.append("N")
            i += 1
        elif b == 0x00:
            j = i
            while j < n and raw[j] == 0x00:
                j += 1
            toks.append("Z")
            i = j
        elif b < 0x20:
            toks.append(f"x{b:02x}")
            i += 1
        elif _is_lead(b) and i + 1 < n:
            i += 2  # 2B 글자
        else:
            i += 1  # ASCII·반각 글자
    return tuple(toks)


def hard(sk):
    """개행(N)을 뺀 열 — 번역으로 개수가 달라져도 되는 토큰을 걸러 낸 **엄격 비교용** 열."""
    return tuple(t for t in sk if t != "N")


def sk_str(raw):
    """열을 짧은 문자열로 — 토큰은 한 글자(`C s d N Z`), 그 외 제어 바이트는 `<hh>`. 장부·보고용."""
    return "".join(t if len(t) == 1 else f"<{t[1:]}>" for t in skeleton(raw))


def soft(raw):
    """뒤 단계 패치가 건드린 블록용 느슨한 열 — 창 제어(%c)·주입(%s %d)만."""
    return tuple(t for t in skeleton(raw) if t in ("C", "s", "d"))


def pad_len(raw):
    """끝 00 의 개수(종단+패딩)."""
    return len(raw) - len(raw.rstrip(b"\x00"))


def end_ok(raw):
    """블록 끝 모양: 00 이 1개 이상이고 전체 길이가 4의 배수(원본 전수 규칙 — 예외 몇 곳은 호출부가 정한다)."""
    return pad_len(raw) >= 1


def classify(old_raw, new_raw):
    """번역 블록의 구조 변화 분류 → 목록. 빈 목록이면 구조 동일(개행 수 차이는 변화로 안 친다).

    - 'C수': `%c` 개수가 달라짐(창·인자 소비 변화) → 허용 목록(쪽 넘김) 대상
    - 'Cs열': `%c`·`%s`·`%d`·제어 바이트의 **순서**가 달라짐 → 허용 목록 대상(스텁 등)
    - 'Z': 종단이 없음
    """
    out = []
    a, b = hard(skeleton(old_raw)), hard(skeleton(new_raw))
    if a != b:
        if a.count("C") != b.count("C"):
            out.append("C수")
        if tuple(t for t in a if t != "C") != tuple(t for t in b if t != "C"):
            out.append("Cs열")
        if not out:
            out.append("순서")
    if not end_ok(new_raw):
        out.append("Z")
    return out


# ───────────────────────── 이미지 대조 · 장부 ─────────────────────────
import hashlib
import struct as _struct

MIPS_ADDIU, MIPS_ORI, MIPS_LUI = 0x09, 0x0D, 0x0F


def _w(data, off):
    return _struct.unpack_from("<I", data, off)[0]


def decode_ref(data, addiu_off, lui_off):
    """lui+addiu/ori 쌍이 만드는 주소(이미지 바이트에서 다시 읽는다)."""
    lui, op = _w(data, lui_off), _w(data, addiu_off)
    hi, lo = lui & 0xFFFF, op & 0xFFFF
    if op >> 26 == MIPS_ORI:
        return (hi << 16) | lo
    return (hi << 16) + (lo - 0x10000 if lo >= 0x8000 else lo)


def check_scene(rec, orig, built, orig_raw):
    """한 씬의 원본·최종 이미지·재배치 기록을 맞춘다. 반환 (findings, counts).

    findings: [(코드, 메시지)] — 비면 통과.
    orig_raw: {eid: 원본 블록 바이트}(scn_jp 에서).
    기록(rec)에 없는 구조 변화·포인터 어긋남·00 이 아닌 빈틈이 있으면 findings 에 든다."""
    f = []
    cnt = {
        "blocks": 0,
        "compared": 0,
        "struct_diff": 0,
        "explained": 0,
        "ptr": 0,
        "ptr_ok": 0,
        "gap_bytes": 0,
        "refs_unlisted": 0,
    }
    te, ovb = rec["text_end"], rec["ov_base"]
    blocks = rec["blocks"]
    cnt["blocks"] = len(blocks)
    new_start = {}
    prev_end = -1
    for eid, oo, ol, no, nl, tr, why, _h in sorted(blocks, key=lambda b: b[3]):
        new_start[eid] = (no, nl)
        if no < prev_end:
            f.append(("겹침", f"jp{eid}: 새 자리 0x{no:X} 가 앞 블록 끝 0x{prev_end:X} 안"))
        if no + nl > te:
            f.append(("범위", f"jp{eid}: 블록 끝 0x{no + nl:X} > 텍스트 끝 0x{te:X}"))
        prev_end = max(prev_end, no + nl)
    missing = set(orig_raw) - set(new_start)
    if missing:
        f.append(("누락", f"원본 블록 {len(missing)}개가 기록에 없음(예: jp{sorted(missing)[:3]})"))
    donors = rec["donors"]
    ext_base = rec["ext_base"]
    covered = bytearray(te)
    later = []  # 재삽입 직후와 바이트가 달라진 블록 — 뒤 단계 패치(지명·HUD·경로 라벨 등)가 건드린 자리
    for eid, oo, ol, no, nl, tr, why, h in blocks:
        for i in range(no, min(no + nl, te)):
            covered[i] = 1
        old = orig_raw.get(eid)
        if old is None:
            continue
        if str(eid) in donors:  # 이주 — 새 블록은 확장 영역, 제자리엔 원본이 남는다
            kind, doff, dlen = donors[str(eid)]
            new = built[doff : doff + dlen] if kind == "ext" else None
            if new is None:
                continue
            here = built[no : no + nl]
            if f"{rec['scene']}:{eid}" not in rec.get("special", []) and skeleton(here) != skeleton(
                old
            ):
                f.append(("이주제자리", f"jp{eid}: 이주 뒤 제자리 블록의 구조가 원본과 다름"))
        else:
            new = built[no : no + nl]
        if hashlib.sha1(built[no : no + nl]).hexdigest()[:10] != h:
            later.append(
                eid
            )  # 뒤 단계가 바꾼 블록 — 제어 토큰(%c %s %d)만 엄격히, 나머지는 느슨히 본다
            cnt["later"] = cnt.get("later", 0) + 1
            if soft(old) != soft(built[no : no + nl]):
                f.append(
                    (
                        "후속패치",
                        f"jp{eid}: 뒤 단계 패치가 %c/%s/%d 열을 바꿨다 {sk_str(old)}→{sk_str(built[no : no + nl])}",
                    )
                )
            cnt["compared"] += 1
            continue
        cnt["compared"] += 1
        if not end_ok(new):
            f.append(("종단", f"jp{eid}: 블록 끝에 00 종단이 없다"))
        if ol % 4 == 0 and nl % 4 != 0 and str(eid) not in donors:
            f.append(("정렬", f"jp{eid}: 길이 {nl} 가 4의 배수가 아님(원본 {ol})"))
        kinds = classify(old, new)
        if kinds:
            cnt["struct_diff"] += 1
            ent = rec["struct"].get(str(eid))
            if not ent:
                f.append(
                    (
                        "구조",
                        f"jp{eid}: 제어 코드 열이 달라졌는데 기록(허용 목록)에 없다 {kinds} {sk_str(old)}→{sk_str(new)}",
                    )
                )
            elif not ent.get("why"):
                f.append(("구조근거", f"jp{eid}: 구조 변화에 허용 근거(의도 표)가 없다 {kinds}"))
            elif ent["kinds"] != kinds:
                f.append(("구조", f"jp{eid}: 기록 {ent['kinds']} ≠ 이미지 {kinds}"))
            else:
                cnt["explained"] += 1
    # 빈틈 — 블록 밖 바이트는 00 이거나 원본 그대로여야 한다
    for i in range(te):
        if not covered[i]:
            if built[i] == 0 or built[i] == orig[i]:
                continue
            cnt["gap_bytes"] += 1
    if cnt["gap_bytes"]:
        f.append(("빈틈", f"블록 밖 바이트 {cnt['gap_bytes']}개가 00 도 원본도 아니다"))
    # 포인터
    alias, mid = rec["alias"], rec["mid"]
    listed = set()
    later_ptr = []
    stub_words = set()
    for st in rec[
        "stubs"
    ]:  # 이름 스텁 콜사이트는 lui/addiu 가 `j` 로 덮인다 — 포인터 대조에서 뺀다(스텁 검증이 따로)
        stub_words |= {st["call_off"], st["call_off"] + 4}
    for ai, li, naddr, delta, via, o_eid in rec["ptr_sites"]:
        if ai in stub_words or li in stub_words:
            listed.add((ai, li))
            continue
        cnt["ptr"] += 1
        listed.add((ai, li))
        got = decode_ref(built, ai, li)
        tgt = naddr - ovb
        ok = got == naddr
        if ok:
            if via == "b":
                no, nl = new_start[o_eid]
                ok = tgt == no + delta and (delta == 0 or delta < nl)
            elif via == "a":
                ok = tgt == new_start[alias[str(o_eid)]][0]
            elif via == "m":
                ok = tgt == new_start[mid[str(o_eid)][1]][0]
            else:  # d — 이주(확장 영역)
                master = alias.get(str(o_eid), o_eid)
                ok = str(master) in donors and tgt == donors[str(master)][1]
        if ok:
            cnt["ptr_ok"] += 1
        else:
            gt = got - ovb
            starts = [v[0] for v in new_start.values()]
            lands = (
                gt in starts
                or any(a_ <= gt < a_ + l_ for a_, l_ in new_start.values())
                or any(gt == d_[1] for d_ in donors.values())
            )
            if lands:
                cnt["ptr_later"] = cnt.get("ptr_later", 0) + 1
                later_ptr.append((o_eid, ai))
            else:
                f.append(
                    (
                        "포인터",
                        f"jp{o_eid}@0x{ai:X}: 이미지 주소 {got:#x} ≠ 기록 {naddr:#x} ({via}) — 블록 어디에도 안 닿는다",
                    )
                )
    # 목표 바이트 — 남이 점프·포인터로 들어오는 자리를 우리가 바꿨나(pce-ed1 10-22: 넘친 메시지의 점프 스텁이 원본 종료 00 을
    # 덮었는데 다른 메시지의 끝 점프가 그 00 으로 들어와 스텁 주소를 글자로 읽었다). 포인터 목표(블록 머리·블록 속 델타)의
    # 원본 바이트와 빌드 바이트가 같은 종류인지 본다 — 제어·00 은 그대로, 글자는 글자.
    obase = {b[0]: b[1] for b in blocks}
    later_set = set(later)
    done = set()
    for ai, li, naddr, delta, via, o_eid in rec["ptr_sites"]:
        if ai in stub_words or li in stub_words or via != "b" or o_eid in later_set:
            continue
        if o_eid not in new_start:
            continue
        if o_eid not in obase:
            continue
        otgt, ntgt = obase[o_eid] + delta, new_start[o_eid][0] + delta
        if (otgt, ntgt) in done or otgt >= len(orig) or ntgt >= len(built):
            continue
        done.add((otgt, ntgt))
        cnt["tgt"] = cnt.get("tgt", 0) + 1
        ob, nb_ = orig[otgt], built[ntgt]
        if ob < 0x20 or nb_ < 0x20:  # 00·개행·제어바이트 자리는 그대로여야 한다
            # 블록 머리(델타 0)는 의도 표(struct)가 이미 설명한 선두 개행 제거·이름판 얹기만 봐준다
            lead_nl = delta == 0 and ob == 0x0A and nb_ >= 0x20  # 선두 개행 제거(LEAD_NL_DROP — 의도, 개행은 hard 열에서 빠진다)
            ok = ob == nb_ or (delta == 0 and str(o_eid) in rec["struct"]) or lead_nl
            if lead_nl:
                cnt["tgt_lead_nl"] = cnt.get("tgt_lead_nl", 0) + 1
        else:
            ok = True  # 둘 다 글자(또는 % 토큰) 자리 — 글자는 번역으로 바뀐다
        if ok:
            cnt["tgt_ok"] = cnt.get("tgt_ok", 0) + 1
        else:
            f.append(
                (
                    "목표바이트",
                    f"jp{o_eid}: 포인터 목표 0x{otgt:X}→0x{ntgt:X} 의 바이트가 {ob:02X}→{nb_:02X} (제어·종단 자리가 바뀌었다)",
                )
            )
    # 코드의 j/jal 이 텍스트 영역으로 들어오는가 — 있으면 그 목표도 위처럼 봐야 한다(없으면 포인터 대조가 전부다)
    n_j = 0
    for off in range(te, len(orig) - 3, 4):
        w = _w(orig, off)
        if w >> 26 in (2, 3):
            t = ((w & 0x3FFFFFF) << 2 | 0x80000000) - ovb
            if 0 <= t < te:
                n_j += 1
    cnt["jump_into_text"] = n_j
    cnt["later_blocks"] = later
    cnt["later_ptrs"] = later_ptr
    return f, cnt, listed


# ───────────────────────── 재배치 장부(relocations.tsv) ─────────────────────────
# 장부는 **빌드가 실제로 한 재배치**(재삽입기가 남긴 기록 + 최종 이미지 대조)에서 자동으로 뽑는다 — 손으로 쓰지 않는다.
# 열: 블록 키 · 종류 · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면. 원문·번역 바이트는 넣지 않는다(좌표·종류·개수뿐).
LEDGER_HEAD = "블록 키\t종류\t원래 좌표\t새 좌표\t사유\t엔진 근거\t되돌리면"

_ENG_PTR = (
    "텍스트는 코드의 lui+addiu/ori 상수로만 읽힘 — find_refs·patch_word_imm 이 전 참조를 새 주소로 갱신"
    "(오버레이 베이스 ED1 0x8016A000·ED2 0x80165000, check_overlay_base 재도출), 앵커는 고정"
)
_REV_RUN = "PILOT_FIXED=1(전 블록 원 길이 고정) 또는 FIXED_RUNS 에 eid 추가 — 원 길이 초과 번역은 size 제외(일본어 유지)"
_WHY = {
    "NAME_PLATE": "이름판(이름창 앞 색코드 0x02~0x01+개행)을 새로 얹음 — 원본도 텍스트 안 단독 제어바이트를 같은 방식으로 쓴다(전 씬 실측 0x02 22회·0x03 15회, reinsert_kr_pilot.py 주석 「블록 전체 색 지정」)",
    "COLOR_WRAP": "블록 전체 색 지정(0x01~0x03 직접 박기, %c 인자 불변)",
    "COLOR_BODY": "본문만 색 지정(이름창 %c 뒤)",
    "COLOR_LEAD": "머리 색 지정",
    "COLOR_ITEM": "아이템명 색 지정",
    "FOLD_NAME": "이름창 접기(조사 붙이고 뒤 개행 제거)",
    "NL_WINS": "창 뒤 강제 개행",
    "LEAD_NL_DROP": "선두 개행 제거",
    "NAME_STUBS": "이름 헤더 스텁이 쓰는 헤더 사본 블록",
    "ED2SCN8_JP0_SPLIT": "ED2SCN8 jp0 — 이름(12B 슬롯)+널+본문이 한 널 종단 안에 있던 것을 제자리에서 두 조각으로 나눔(본문 시작 델타 12 참조 보존, reinsert_kr_pilot.py 「ED2SCN8 jp0」 주석)",
}


def _x(v):
    return f"0x{v:X}"


def ledger_rows(recs, layout, gate):
    """재배치 장부 행 목록(정렬·결정적). recs={씬: 기록} · layout=scn_layout.json · gate={씬: check_scene 의 cnt}."""
    rows = []

    def add(key, kind, old, new, why, eng, rev):
        rows.append((key, kind, old, new, why, eng, rev))

    for name in sorted(recs):
        rec = recs[name]
        blocks = rec["blocks"]
        by_old = sorted(blocks, key=lambda b: b[1])
        L = layout.get(name, {})
        # ① 옮김(파일)
        if rec["new_size"] > rec["orig_size"]:
            add(
                name,
                "옮김(파일)",
                f"LBA {rec['orig_lba']} · {rec['orig_size']}B",
                f"LBA {L.get('lba', '?')} · {L.get('size', rec['new_size'])}B",
                f"번역·확장 영역으로 파일이 {rec['new_size'] - rec['orig_size']}B 커져 원 섹터 수를 넘음 → DUMMY.;1 영역으로 이사",
                "ISO 디렉터리 레코드(BIN_DIR_LBA)의 LBA·크기(양 엔디언)를 갱신 — 엔진은 ISO 경로로 로드(ED.EXE 0xC3F4~ 경로 문자열 실증, reinsert_kr_pilot.main)",
                "확장 영역을 끄면(PILOT_NO_DONOR=1 · PILOT_NO_STUBS=all) 원 크기 안에서 굽는다 — 이주 블록은 제외돼 일본어로 남는다",
            )
        # ② 옮김(구간) — 블록이 실제로 움직인 자유 구간
        for rs, re_, n, pad, fixed in rec["runs"]:
            inside = [b for b in by_old if rs <= b[1] < re_]
            if not inside:
                continue
            moved = [b for b in inside if b[3] != b[1] or b[4] != b[2]]
            if not moved:
                continue
            first, last = inside[0], inside[-1]
            nlast = max(inside, key=lambda b: b[3] + b[4])
            add(
                f"{name}:jp{first[0]}~jp{last[0]}",
                "옮김(구간)",
                f"{_x(rs)}-{_x(re_)}",
                f"{_x(min(b[3] for b in inside))}-{_x(nlast[3] + nlast[4])}",
                f"번역 길이가 원문과 달라 앵커 사이 구간 {n}블록을 앞에서부터 다시 채움(옮긴 블록 {len(moved)} · 끝 00 채움 {pad}B)",
                _ENG_PTR,
                _REV_RUN,
            )
        # ③ 채움 — 앵커 접미/접두 꼬리 제자리 덮어쓰기
        for kind, eid, nlen, pad in rec["pin_ovr"]:
            b = next(b for b in blocks if b[0] == eid)
            add(
                f"{name}:jp{eid}",
                "채움",
                f"{_x(b[1])}+{b[2]}B",
                f"{_x(b[3])}+{nlen}B(+00 {pad}B)",
                f"앵커 {'접미' if kind == 'room' else '접두'} 블록 — 앵커 시작/끝 위치를 못 움직이므로 번역을 제자리에 덮고 남는 {pad}B 를 00 으로 채움",
                "앵커(lui+lw 점프 테이블)는 절대 주소로 읽혀 이동 불가 — rebuild() 주석(앵커 고정)",
                "블록 번역 제외(PILOT_EXCLUDE_EIDS=씬:eid) — 원문 그대로",
            )
        tot_pad = sum(r[3] for r in rec["runs"])
        if tot_pad:
            add(
                name,
                "채움",
                f"구간 {len(rec['runs'])}",
                f"00 {tot_pad}B",
                "구간 끝에 남는 바이트를 00 으로 채워 다음 앵커 위치를 고정(블록 사이 빈틈도 00)",
                "문자열 종단이 00 — 빈틈이 00 이 아니면 앞 문자열이 이어 읽힌다(구조 대조 검사가 빈틈 전수 확인)",
                "PILOT_FIXED=1 이면 블록마다 원 길이로 채움",
            )
        # ④ 옮김(이주)
        for eid, (kind, off, ln) in sorted(rec["donors"].items(), key=lambda x: int(x[0])):
            b = next(b for b in blocks if str(b[0]) == eid)
            add(
                f"{name}:jp{eid}",
                "옮김(이주)",
                f"{_x(b[1])}+{b[2]}B",
                f"{'파일 꼬리 확장 영역' if kind == 'ext' else 'ED.EXE 0런'} {_x(off)}+{ln}B",
                "번역이 원 자리(구간 용량·중간 참조)에 안 들어가 확장 영역으로 이주 — 원본 JP 바이트는 제자리에 남음",
                "선두(delta 0) 참조만 새 주소로 돌림; 내부(delta) 참조는 JP 바이트를 그대로 읽음 — 오버레이 RAM 상한 안(OVERLAY_RAM_LIMIT)",
                "PILOT_NO_DONOR=1 — 이주 없음(그 블록은 제외돼 일본어 유지)",
            )
        # ⑤ 스텁
        for st in rec["stubs"]:
            add(
                f"{name}:jp{st['eid']}",
                "스텁",
                f"호출점 {_x(st['call_off'])}",
                f"헤더 사본 {_x(st['blk_off'])}+{st['blk_len']}B · 스텁 {_x(st['stub_off'])}+56B",
                "이름 헤더(%c%s%c) 호출부를 확장 영역 MIPS 스텁(sprintf 호출)으로 갈아 끼워 화자 이름을 띄움",
                f"호출점을 `j 스텁` 으로 교체 · 스텁은 sprintf {_x(st['sprintf'])} 호출 뒤 `j {_x(st['resume'])}`(원 흐름 재개)",
                f"PILOT_NO_STUBS={name}:{st['eid']} — 원판 방식(이름 없이)",
            )
        if rec["args"]:
            es = sorted({a[0] for a in rec["args"]})
            add(
                f"{name}:jp{'+jp'.join(map(str, es))}",
                "스텁(인자)",
                f"코드 워드 {len(rec['args'])}개",
                "같은 자리(워드 값만 변경)",
                "주입 %c 쌍 블록의 콜사이트 인자(0x83/0x5C)를 공백으로 바꿈 — 번역이 실제로 들어간 블록만",
                "번역이 들어갈 때만 적용(원본 인자를 보존해야 원판 문자 ソ 가 그대로 나온다) — SCN_ARG_PATCHES 주석",
                "해당 블록 번역 제외(PILOT_EXCLUDE_EIDS)하면 자동 미적용",
            )
        # ⑥ 포인터
        pm = rec["ptr_moved"]
        add(
            name,
            "포인터",
            f"참조 {len(rec['ptr_sites'])}건",
            f"주소가 바뀐 참조 {sum(pm.values())}건(블록 {len(pm)})",
            "블록이 옮겨져 그 블록을 읽는 lui+addiu/ori 상수를 새 주소로 갱신",
            _ENG_PTR,
            "되돌림 수단 없음(블록 이동을 되돌리면 자동으로 원 주소 — 위 PILOT_FIXED)",
        )
        for k, (delta, master) in sorted(rec["mid"].items(), key=lambda x: int(x[0])):
            add(
                f"{name}:jp{k}",
                "포인터",
                f"표머리 사본 +{delta}",
                f"대표 jp{master} 로 리타깃",
                "[포인터 표][대사] 사본 — 대표 블록이 번역돼 살아 있어 사본은 포인터만 대표로 돌림(공간 0)",
                "MID_ALIAS/stock_mid — 내용이 같은 정형 블록",
                "PILOT_NO_ALIAS=1",
            )
        for k, master in sorted(rec["alias"].items(), key=lambda x: int(x[0])):
            add(
                f"{name}:jp{k}",
                "포인터",
                "선두 참조",
                f"대표 jp{master} 로 리타깃",
                "보물상자류 정형 블록 — size 로 밀려난 사본을 생존 사본으로 포인터만 돌림",
                "stock_alias — 블록 선두 참조(delta 0)만 대상, 원본 바이트는 제자리",
                "PILOT_NO_ALIAS=1",
            )
        # ⑦ 제어 바이트 변화(의도 표에 든 것)
        for eid, ent in sorted(rec["struct"].items(), key=lambda x: int(x[0])):
            b = next(b for b in blocks if str(b[0]) == eid)
            add(
                f"{name}:jp{eid}",
                "제어바이트",
                f"열 {ent['old']}",
                f"열 {ent['new']}",
                " · ".join(_WHY.get(w, w) for w in ent["why"]) or "근거 없음",
                "제어 코드 열(%c %s %d 개행 종단 제어바이트)을 원본과 짝지어 본 구조 대조 — scn_structure.classify",
                f"{'/'.join(ent['why'])} 표에서 해당 eid 를 빼면 원판 열",
            )
        # ⑧ 뒤 단계 패치(재삽입 뒤 patch_sys_ui·patch_scn_* 등이 건드린 블록)
        g = gate.get(name, {})
        lb = g.get("later_blocks", [])
        if lb:
            add(
                name,
                "후속패치",
                f"블록 {len(lb)}개",
                "같은 자리(바이트만 변경)",
                "재삽입 직후와 최종 이미지의 바이트가 다른 블록 — 지명·HUD 반각 슬롯·경로 라벨 등 뒤 단계 패치가 씀. jp"
                + ",".join(map(str, sorted(lb))),
                "%c %s %d 열은 원본과 같음(구조 대조가 확인) — patch_sys_ui · patch_scn_hud_copy · patch_scn_msgctl · patch_scn_orphans · patch_scn_route_labels",
                "각 패치 도구를 build.py 체인에서 빼면 원 바이트(되돌림 수단은 도구별)",
            )
        for o_eid, ai in g.get("later_ptrs", []):
            add(
                f"{name}:jp{o_eid}",
                "포인터(후속)",
                f"코드 {_x(ai)}",
                "블록 시작으로 재지정",
                "재삽입이 준 새 주소를 뒤 단계 패치가 다시 잡음(최종 이미지는 블록 시작을 가리킴)",
                "patch_scn_hud_copy.REPOINT — HUD 참조가 대사 블록 0 의 이름칸(오프셋 0)을 재활용하는데 재삽입이 그 참조까지 이주지로 옮겨 이름칸+본문 합본을 읽게 됨 → 원 이름칸을 가리키게 되돌림(그 파일 주석 ⓑ)",
                "patch_scn_hud_copy 를 체인에서 뺌",
            )
    rows.sort(key=lambda r: (r[0].split(":")[0], r[1], r[0]))
    return rows


def ledger_text(rows):
    lines = [LEDGER_HEAD]
    for r in rows:
        lines.append("\t".join(c.replace("\t", " ").replace("\n", " ") for c in r))
    return "\n".join(lines) + "\n"
