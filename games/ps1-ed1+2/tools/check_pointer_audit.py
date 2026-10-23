#!/usr/bin/env python3
"""**체인이 끝난 최종 이미지**에서 시스템·전투 문안의 모든 포인터가 계획한 번역을 가리키는가 + 패처 쓰기 구간 겹침.

**왜.** ss-ed1+2 에서 ED2MON 시스템 문안 꼬리 영역을 두 패처가 각자 풀로 써서 뒤 단계가 앞 문구를 덮어썼고, 전투 문구 포인터 14개가
엉뚱한 문구를 가리켰다. 그 게임의 `verify_sys` 류 검증은 **자기 단계 직후·첫 포인터만** 봐서 못 잡았다(10-19). 여기는 반대로 본다 —
**빌드 체인이 전부 끝난 최종 이미지**에서, 원본의 코드 참조(`lui`+`addiu`/`ori`)마다 **같은 사이트**가 가리키는 문자열을 읽어
패처의 계획 번역(바이트)과 대조한다(전수, 첫 포인터만 아님).

검사:
  ① ED2.EXE 전투 문안 · ED2.EXE 이름 구획 · ED.EXE 이름·메시지 구획 · ED.EXE 전투 코퍼스 — 참조 대조(불일치 0 이어야 통과)
  ② ED2.EXE 시스템 문자열 제자리 — 위치 대조(지명 복원이 의도해 한 음절 늘린 2자리는 `SYS_RESTORED_OK` 로 명시 허용)
  ③ ED2MON 오버레이 참조 — 계획표에 없는 자리(색 코드로 감싼 이름 변형·개체 접미·템플릿)는 **최종 문자열 해시를 기준선에 묶는다**
     (`pointer_audit_baseline.json` — 번호·해시뿐, 문안 없음). 기준선 밖의 불일치가 생기거나 기준선의 문자열이 바뀌면 실패.
  ④ 패처 쓰기 구간 겹침 — 단계 순서대로 **메모리에서만** 재현해(이미지 불변) 앞 단계가 쓴 바이트를 뒤 단계가 다시 바꾸는지 센다.

🔴 **허용된 겹침 하나 — 암묵 계약.** ED.EXE `0x4EA0~0x4EAA`(11바이트): `patch_sys_ui` 가 메모리카드 문구 뒤에 남긴 **널 꼬리**에
`patch_items.fix_damage_particle` 이 데미지 조사 새 문자열(`%c%s%c에게 `)을 심는다. sys 문구와 그 종단은 그대로이고 참조는 새 주소를 가리켜
훼손은 아니다. 그러나 「sys 문구의 빈 꼬리를 items 가 쓴다」는 **패처 사이 암묵 계약**이다 — sys 문구가 길어져 꼬리가 사라지거나 그 꼬리를
고정 길이 버퍼로 읽는 코드가 생기면 조용히 깨진다(09-28 「빼앗았다」 선례). 그래서 이 11바이트 **밖의** 새 겹침이 생기면 실패한다.

⚠ 빌드 이미지가 없거나 패처·문안 소스보다 오래되면 통과가 아니라 **「안 쟀다」로 실패**한다(코퍼스 없음과 같다).
⚠ 문안 변경·패처 변경으로 정당하게 기준선이 바뀌면 `--freeze` 로 다시 박는다.

  python3 tools/check_pointer_audit.py            # 게이트
  python3 tools/check_pointer_audit.py --freeze   # ③ 기준선 갱신
  python3 tools/check_pointer_audit.py --allow-stale   # 진단 전용 — 오래된 이미지도 잰다
"""

import contextlib
import hashlib
import io
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("LOCK_BYPASS", "1")

GAME = os.path.dirname(HERE)
BASELINE = os.path.join(GAME, "pointer_audit_baseline.json")

# ED.EXE · ED2.EXE 공통 — RAM 0x80010000 이 파일 오프셋 0x800(헤더 뒤)
EXE_RAM_BASE = 0x80010000
EXE_HDR = 0x800

# ② 지명 복원(patch_sys_ui.restore_full_place_names, 058)이 뒤 단계에서 의도해 한 음절(2바이트) 늘린 ED2.EXE 시스템 자리
SYS_RESTORED_OK = {0x9A1F0, 0x9A478}

# ④ 허용 겹침 — 위 머리말의 암묵 계약. (파일 오프셋 반열린 구간)
ALLOWED_OVERLAP = {"ED.EXE": [(0x4EA0, 0x4EAB)], "ED2.EXE": []}
# ④ 뒤 단계(훅·글리프·이름 복사·지명 복원)가 문안 패처가 쓴 바이트를 다시 바꾼 자리 — 지명 복원 2바이트씩이 전부다.
# + `patch_battle_frag_space` 가 수치 없는 조각 참조 하나의 addiu 하위 16비트(+1, 최대 2바이트)를 공백 뒤로 돌린다(ED2.EXE 1곳)
ALLOWED_LATE_TOUCH = {"ED.EXE": 2, "ED2.EXE": 2 + 2}

# 이미지가 이 파일들보다 오래되면 「안 쟀다」
_SOURCE_GLOBS = ("patch_*.py", "reinsert_kr_pilot.py", "build.py", "hangul_map.py", "common.py")


# ── 순수 함수(합성 이미지 테스트 대상) ───────────────────────────────────────
def fo_of(addr):
    """EXE RAM 주소 → 파일 오프셋."""
    return addr - EXE_RAM_BASE + EXE_HDR


def ref_sites(buf):
    """{imm 위치: 가리키는 RAM 주소} — lui + addiu/ori 쌍."""
    from common import MIPS_ADDIU, MIPS_ORI, iter_lui_pairs

    out = {}
    for imm, _lui, _op, addr in iter_lui_pairs(bytes(buf), {MIPS_ADDIU, MIPS_ORI}):
        out[imm] = addr
    return out


def read_cstr(buf, fo):
    if fo < 0 or fo >= len(buf):
        return None
    j = buf.find(b"\x00", fo)
    return bytes(buf[fo:j]) if j >= 0 else None


def audit_refs(orig, final, expected):
    """expected: [(라벨, 원본 RAM 주소, 기대 바이트)].

    원본에서 그 주소를 가리키는 **모든** 참조 사이트를 찾고, 최종 이미지의 **같은 사이트**가 가리키는 문자열을 기대와 대조한다.
    반환 (포인터 수, 일치 수, 불일치 [(라벨, 사이트, 기대, 실제)], 참조 0건 라벨)."""
    po, pf = ref_sites(orig), ref_sites(final)
    by_addr = {}
    for imm, addr in po.items():
        by_addr.setdefault(addr, []).append(imm)
    total = ok = 0
    bad, noref = [], []
    for label, addr, exp in expected:
        imms = by_addr.get(addr, [])
        if not imms:
            noref.append(label)
            continue
        for imm in imms:
            total += 1
            a2 = pf.get(imm)
            got = read_cstr(final, fo_of(a2)) if a2 is not None else None
            if got == exp:
                ok += 1
            else:
                bad.append((label, imm, exp, got))
    return total, ok, bad, noref


def split_space_repoint(bad, allowed):
    """불일치 중 **기대 문자열이 앞 공백으로 시작하고 실제가 그 공백 뒤**인 것(patch_battle_frag_space 의 수치 없는 참조)을 가른다.
    개수가 `allowed`(EXPECT)를 넘으면 넘은 만큼은 설명 안 되는 불일치로 남긴다. 반환 (설명 안 되는 것, 공백 뒤 참조 수)."""
    keep, n = [], 0
    for label, imm, exp, got in bad:
        if n < allowed and got is not None and exp[:1] == b" " and got == exp[1:]:
            n += 1
        else:
            keep.append((label, imm, exp, got))
    return keep, n


def diff_offsets(a, b):
    n = min(len(a), len(b))
    return {i for i in range(n) if a[i] != b[i]}


def to_spans(offsets):
    """오프셋 집합 → 반열린 구간 목록."""
    out = []
    for i in sorted(offsets):
        if out and i == out[-1][1]:
            out[-1][1] = i + 1
        else:
            out.append([i, i + 1])
    return [tuple(s) for s in out]


def spans_outside(spans, allowed):
    """allowed(반열린 구간 목록) 안에 **통째로** 들지 않는 구간."""
    return [s for s in spans if not any(lo <= s[0] and s[1] <= hi for lo, hi in allowed)]


def sys_mismatch_unexplained(bad, restored_ok=SYS_RESTORED_OK):
    """② 위치 대조 불일치 중 지명 복원(+1음절 = +2바이트)으로 설명되지 않는 것."""
    out = []
    for off, exp, got in bad:
        if off in restored_ok and got is not None and len(got) == len(exp) + 2:
            continue
        out.append((off, exp, got))
    return out


def mon_signature(final_bytes):
    return hashlib.sha1(final_bytes or b"").hexdigest()[:10]


# ── 이미지·소스 신선도 ───────────────────────────────────────────────────────
def image_path():
    from common import BUILD_DIR

    return os.path.join(BUILD_DIR, "Eiyuu Densetsu (KR).bin")


def newest_source_mtime():
    import glob

    mt = 0.0
    for pat in _SOURCE_GLOBS:
        for p in glob.glob(os.path.join(HERE, pat)):
            mt = max(mt, os.path.getmtime(p))
    # ⚠ script/ 는 씬 정본(ED*SCN*.json)만 — 같은 폴더에 다른 게이트가 빌드 뒤에 쓰는 보고 파일
    #   (window_frame_over145.json)이 있어 `*.json` 으로 걸면 방금 빌드한 이미지가 늘 「낡음」으로 읽힌다.
    for sub, pat in (("textmap", "*.json"), ("script", "ED*SCN*.json")):
        for p in glob.glob(os.path.join(GAME, sub, pat)):
            mt = max(mt, os.path.getmtime(p))
    return mt


def stale_reason(img, allow_stale=False):
    if not os.path.exists(img):
        return f"빌드 이미지 없음({img}) — 먼저 build.py"
    if not allow_stale and os.path.getmtime(img) < newest_source_mtime():
        return "빌드 이미지가 패처·문안 소스보다 오래됐다 — 다시 빌드해야 잴 수 있다"
    return None


# ── ①② 참조·위치 대조 ───────────────────────────────────────────────────────
def _quiet_import(*names):
    mods = []
    with contextlib.redirect_stdout(io.StringIO()):
        for n in names:
            mods.append(__import__(n))
    return mods


def _frag_expect():
    """patch_battle_frag_space 가 공백 뒤로 돌리는 수치 없는 참조 수({EXE: n})."""
    import patch_battle_frag_space as F

    return F.EXPECT


def run_pointer_audit(img):
    """반환 ([(이름, 항목, 포인터, 일치, 불일치목록, 참조0건)], ED2 시스템 위치 대조 불일치[(off, exp, got)])."""
    from common import extract

    PI, EB, ES = _quiet_import("patch_items", "patch_ed2_battle", "patch_ed2_sys")
    rows = []

    # ED2.EXE 전투 문안
    o2 = extract(EB.ED2_LBA, EB.ED2_SIZE)
    f2 = extract(EB.ED2_LBA, EB.ED2_SIZE, path=img)
    with contextlib.redirect_stdout(io.StringIO()):
        fit, over, _none = EB.plan()
    exp = [(("ED2전투", fo), PI.ram_of(fo), EB._enc(kr)) for fo, _jp, kr, _slot in fit + over]
    t, k, bad, nr = audit_refs(o2, f2, exp)
    bad, sp = split_space_repoint(bad, _frag_expect()["ED2.EXE"])
    k += sp  # 수치 없는 조각 참조는 공백 뒤를 가리키는 게 정상(patch_battle_frag_space)
    rows.append(("ED2.EXE 전투 문안", len(exp), t, k, bad, nr))

    # ED2.EXE 이름 구획
    with contextlib.redirect_stdout(io.StringIO()):
        canon = ES.apply_canon()
    names = ES._walk(o2, 0x800, 0xF44)
    exp = []
    for off, jp in names:
        kr = canon.get(jp)
        exp.append(
            (("ED2이름", off), PI.ram_of(off), ES._enc(kr) if kr else jp.encode("shift_jis"))
        )
    t, k, bad, nr = audit_refs(o2, f2, exp)
    rows.append(("ED2.EXE 이름 구획", len(exp), t, k, bad, nr))

    # ED2.EXE 시스템 문자열 — 위치 기준(참조 무관)
    with contextlib.redirect_stdout(io.StringIO()):
        sys_rows, _over2 = ES.plan()
    sys_bad = []
    ok = 0
    for off, _jp, _kr, _slot, enc in sys_rows:
        got = read_cstr(f2, off)
        if got == enc:
            ok += 1
        else:
            sys_bad.append((off, enc, got))
    rows.append(("ED2.EXE 시스템 제자리", len(sys_rows), len(sys_rows), ok, sys_bad, []))

    # ED.EXE 이름·메시지 구획 + 전투 코퍼스
    o1 = extract(PI.ED_LBA, PI.ED_SIZE)
    f1 = extract(PI.ED_LBA, PI.ED_SIZE, path=img)
    exp = []

    def rep(rng, tr, label):
        for off, jp in PI.scan_names(o1, *rng):
            exp.append(((label, off), PI.ram_of(off), PI.enc(tr(jp))))

    rep(PI.BLOB_EQ, PI.NAMES.__getitem__, "장비도구")
    rep(PI.BLOB_MAGIC, PI.NAMES.__getitem__, "마법")
    rep(PI.SEC, PI.NAMES.__getitem__, "전투테이블")
    rep(PI.MONSTER, PI.monster_kr, "몬스터")
    b = PI.BATTLE.__getitem__
    for rng, lab in (
        (PI.CHAPTER, "챕터"),
        (PI.ARENA, "격투장"),
        (PI.BTL_MSG, "전투메시지"),
        (PI.BTL_MSG2, "입수"),
        (PI.FRAG, "조각"),
        (PI.EVT, "이벤트이름"),
    ):
        rep(rng, b, lab)
    rep(PI.FRAG_TACHI, lambda _: "\x01들", "たち")
    t, k, bad, nr = audit_refs(o1, f1, exp)
    rows.append(("ED.EXE 이름·메시지 구획", len(exp), t, k, bad, nr))

    exp = []
    for fo, _e, jp in PI.corpus_strings(o1):
        kr = PI.BATTLE_OFF_KR.get(fo) or PI.battle_kr(jp)
        exp.append((("ED1전투", fo), PI.ram_of(fo), PI.enc(kr)))
    t, k, bad, nr = audit_refs(o1, f1, exp)
    bad, sp = split_space_repoint(bad, _frag_expect()["ED.EXE"])
    k += sp
    rows.append(("ED.EXE 전투 코퍼스", len(exp), t, k, bad, nr))
    return rows, sys_bad


# ── ③ ED2MON 오버레이 ───────────────────────────────────────────────────────
def run_mon_audit(img):
    """반환 (포인터 합계, 계획 일치 수, 접두 중간 수, {"그룹:오프셋": 최종문자열해시} — 계획과 다른 자리)."""
    from common import extract

    with contextlib.redirect_stdout(io.StringIO()):
        import patch_ed2_monster_lines as L
        import patch_ed2_monsters as N
        from ed2_monster_review import MON

        fitL, moveL, _overL, _noneL = L.plan()
        fitN, _overN, _noneN = N.plan()
    live = L._live_group_lba(img)
    with open(L.SHA_TABLE, encoding="utf-8") as f:
        sha = json.load(f)
    sha = {k: v for k, v in sha.items() if not k.startswith("_")}
    by_lba = {lba: g for g, (lba, _s) in MON.items()}
    exp = {}
    for lba, off, _jp, kr, _slot in fitN:
        exp.setdefault((by_lba[lba], off), []).append(kr)
    for lba, off, _jp, kr, _slot in fitL + moveL:
        exp.setdefault((by_lba[lba], off), []).append(kr)

    def encs(kr):
        v = {L._enc(kr)}
        if kr.endswith("."):
            v.add(L._enc(kr[:-1]))
        return v

    total = ok = interior = 0
    unplanned = {}
    for g, (lba, osize) in sorted(MON.items()):
        orig = bytes(extract(lba, osize))
        clba, csize = live[g]
        cap = (csize + 2047) // 2048 * 2048
        fin = bytes(extract(clba, cap, path=img))
        refs, _ = L.overlay_refs(orig)
        for T, sites in sorted(refs.items()):
            j = orig.find(b"\x00", T)
            if T >= len(orig) or j < 0 or j == T:
                continue
            s = orig[T:j]
            try:
                st = s.decode("cp932")
            except Exception:  # noqa: BLE001,S112 — 디코드 안 되는 바이트열은 문자열이 아니다
                continue
            if not L.JP.search(st):
                continue
            new_t = set()
            for imm, lui, op in sites:
                w = struct.unpack_from("<I", fin, imm)[0]
                wl = struct.unpack_from("<I", fin, lui)[0]
                iv = w & 0xFFFF
                if op == L.MIPS_ADDIU and iv & 0x8000:
                    iv -= 0x10000
                new_t.add(((wl & 0xFFFF) << 16) + iv - L.BASE)
            total += len(sites)
            planned = list(exp.get((g, T), []))
            k10 = hashlib.sha1(st.encode()).hexdigest()[:10]
            if k10 in sha:
                planned.append(sha[k10])
            key = f"{g}:{T:#x}"
            if len(new_t) > 1:  # 같은 원문 사이트들이 서로 다른 새 주소 — 공유 lui 오염
                unplanned[key] = "multi-target"
                continue
            nt = next(iter(new_t))
            fj = fin.find(b"\x00", nt)
            got = fin[nt:fj] if 0 <= nt < len(fin) and fj >= 0 else None
            is_start = T == 0 or orig[T - 1] == 0
            if got == s and not planned:
                continue  # 계획 없음 + 원문 유지 — 일본어 잔존 게이트 몫
            if not is_start and not planned:
                interior += len(sites)
                continue
            cands = set()
            for kr in planned:
                cands |= encs(kr)
            if got in cands:
                ok += len(sites)
            elif got == s:
                continue  # 계획은 있으나 슬롯 부족으로 원문 유지(건너뜀) — 일본어 잔존 게이트 몫
            else:
                unplanned[key] = mon_signature(got)
    return total, ok, interior, unplanned


# ── ④ 쓰기 구간 겹침(메모리 재현) ───────────────────────────────────────────
def _run_src(mod, fn, repl, cut):
    """패처의 main/apply 를 **파일 대신 메모리 버퍼**에서 돌리도록 소스를 잘라 붙인다(이미지 불변)."""
    import inspect

    src = inspect.getsource(getattr(mod, fn))
    for a, b in repl:
        assert a in src, (fn, a)
        src = src.replace(a, b)
    assert cut in src, (fn, cut)
    src = src[: src.index(cut)]
    if fn == "apply":
        src = src.replace("def apply(", "def _sim_apply(", 1) + "\n    return buf\n"
    else:
        src = src.replace("def " + fn + "(", "def _sim_" + fn + "(", 1) + "\n    return ed\n"
    ns = dict(vars(mod))
    exec(compile(src, "<sim>", "exec"), ns)  # noqa: S102 — 패처 소스를 메모리 버퍼용으로 잘라 붙인다(이미지 불변)
    return ns["_sim_" + fn]


def run_overlap(img):
    """반환 {EXE: {"겹침": 구간[], "뒤단계": 문안 패처 바이트와 겹친 수, ...}}."""
    from common import extract

    P, PI, ES, EB = _quiet_import(
        "patch_sys_ui", "patch_items", "patch_ed2_sys", "patch_ed2_battle"
    )
    res = {}
    q = io.StringIO()

    # ED.EXE: sys_ui → items
    o1 = extract(PI.ED_LBA, PI.ED_SIZE)
    with contextlib.redirect_stdout(q):
        sim_sys = _run_src(
            P,
            "main",
            [
                (
                    '    if not os.path.exists(SRC):\n        raise SystemExit(f"KR Pilot 이미지 없음 — reinsert_kr_pilot.py 먼저 실행\\n  기대: {SRC}")\n',
                    "",
                ),
                ("ed = bytearray(extract(ED_LBA, ED_SIZE, path=SRC))", "ed = bytearray(ED_IN)"),
            ],
            "    shutil.copyfile(SRC, DST)",
        )
        sim_sys.__globals__["ED_IN"] = bytes(o1)
        s1 = bytes(sim_sys())
    sys_diff = diff_offsets(o1, s1)
    with contextlib.redirect_stdout(q):
        sim_it = _run_src(
            PI,
            "main",
            [
                (
                    '    if not os.path.exists(TARGET):\n        raise SystemExit(f"대상 이미지 없음: {TARGET} — build.py 먼저")\n',
                    "",
                ),
                ("ed = bytearray(extract(ED_LBA, ED_SIZE, path=TARGET))", "ed = bytearray(ED_IN)"),
            ],
            "    with open(TARGET",
        )
        sim_it.__globals__["ED_IN"] = s1
        i1 = bytes(sim_it())
    it_diff = diff_offsets(s1, i1)
    f1 = extract(PI.ED_LBA, PI.ED_SIZE, path=img)
    late1 = diff_offsets(i1, f1) & (sys_diff | it_diff)
    res["ED.EXE"] = {"overlap": to_spans(sys_diff & it_diff), "late": len(late1)}

    # ED2.EXE: sys → battle
    o2 = extract(EB.ED2_LBA, EB.ED2_SIZE)
    with contextlib.redirect_stdout(q):
        sim_es = _run_src(
            ES,
            "apply",
            [("buf = bytearray(extract(ED2_LBA, ED2_SIZE, path=IMG))", "buf = bytearray(ED2_IN)")],
            "    with open(IMG",
        )
        sim_es.__globals__["ED2_IN"] = bytes(o2)
        s2 = bytes(sim_es())
    sd = diff_offsets(o2, s2)
    with contextlib.redirect_stdout(q):
        fit, over_b, _none = EB.plan()
        b2 = bytearray(s2)
        EB.relocate(b2, fit, over_b)
    bd = diff_offsets(s2, bytes(b2))
    f2 = extract(EB.ED2_LBA, EB.ED2_SIZE, path=img)
    late2 = diff_offsets(bytes(b2), f2) & (sd | bd)
    res["ED2.EXE"] = {"overlap": to_spans(sd & bd), "late": len(late2)}
    return res


# ── 기준선 ──────────────────────────────────────────────────────────────────
def load_baseline():
    if not os.path.exists(BASELINE):
        return None
    with open(BASELINE, encoding="utf-8") as f:
        return json.load(f).get("mon_unplanned", {})


def freeze(unplanned):
    doc = {
        "_doc": "check_pointer_audit ③ — ED2MON 오버레이에서 계획표에 없는 포인터 자리(색 코드 이름 변형·개체 접미·템플릿)의 "
        "최종 문자열 해시. 번호·해시뿐이다(문안 없음). 기준선 밖의 불일치·해시 변화는 실패.",
        "mon_unplanned": dict(sorted(unplanned.items())),
    }
    with open(BASELINE, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")


# ── 게이트 ──────────────────────────────────────────────────────────────────
def main(argv):
    allow_stale = "--allow-stale" in argv
    img = image_path()
    why = stale_reason(img, allow_stale)
    if why:
        print(f"  ❌ 안 쟀다 — {why}")
        return 1
    fail = 0

    try:
        rows, _sys_bad = run_pointer_audit(img)
    except Exception as e:  # noqa: BLE001 — 패처 구조가 바뀌어 대조를 못 꾸림: 조용히 통과시키지 않는다
        print(f"  ❌ 포인터 대조를 못 돌렸다(패처 구조 변경?) — {type(e).__name__}: {e}")
        return 1
    tot_ptr = 0
    for name, n, total, ok, bad, noref in rows:
        tot_ptr += total
        if name == "ED2.EXE 시스템 제자리":
            bad = sys_mismatch_unexplained(bad)
        if bad:
            fail = 1
            print(
                f"  ❌ {name}: 항목 {n} · 포인터 {total} · 일치 {ok} · 설명 안 되는 불일치 {len(bad)}"
            )
            for b in bad[:6]:
                print(f"       {b[0]!r}")
        if noref and name != "ED2.EXE 시스템 제자리":
            print(f"     ⚠ {name}: 코드 참조 0건 {len(noref)} (위치 기준 패처가 아니면 확인)")
    # 대표 한 줄
    print(
        f"  {'❌' if fail else '✅'} 문안 포인터 대조 — 포인터 {tot_ptr} · 불일치 {'있음' if fail else 0}"
    )

    try:
        mon_total, mon_ok, mon_interior, unplanned = run_mon_audit(img)
    except Exception as e:  # noqa: BLE001 — 못 돌리면 실패다
        print(f"  ❌ ED2MON 오버레이 대조를 못 돌렸다 — {type(e).__name__}: {e}")
        return 1
    if "--freeze" in argv:
        freeze(unplanned)
        print(f"  기준선을 새로 박았다 — ED2MON 계획 밖 자리 {len(unplanned)}")
        return 0
    base = load_baseline()
    if base is None:
        print(f"  ❌ 기준선 파일이 없다({os.path.basename(BASELINE)}) — `--freeze` 로 박는다")
        return 1
    new = sorted(k for k in unplanned if k not in base)
    changed = sorted(k for k in unplanned if k in base and base[k] != unplanned[k])
    gone = sorted(k for k in base if k not in unplanned)
    if new or changed:
        fail = 1
        print(f"  ❌ ED2MON 포인터: 기준선 밖 불일치 {len(new)} · 문자열 변화 {len(changed)}")
        for k in (new + changed)[:8]:
            print(f"       {k}")
    else:
        extra = f" · 기준선을 내릴 수 있다({len(gone)})" if gone else ""
        print(
            f"  ✅ ED2MON 오버레이 포인터 {mon_total} · 계획 일치 {mon_ok} · 접두 중간 {mon_interior} · "
            f"기준선 고정 {len(unplanned)}{extra}"
        )

    try:
        ov = run_overlap(img)
    except Exception as e:  # noqa: BLE001 — 못 재면 실패다
        print(f"  ❌ 쓰기 구간 겹침을 못 쟀다(패처 소스 구조 변경?) — {type(e).__name__}: {e}")
        return 1
    allowed_total = 0
    for exe, r in ov.items():
        out = spans_outside(r["overlap"], ALLOWED_OVERLAP[exe])
        allowed_total += len(r["overlap"]) - len(out)
        if out:
            fail = 1
            print(
                f"  ❌ {exe} 패처 쓰기 구간 새 겹침: "
                + ", ".join(f"{lo:#x}~{hi:#x}" for lo, hi in out)
            )
        if r["late"] > ALLOWED_LATE_TOUCH[exe]:
            fail = 1
            print(
                f"  ❌ {exe}: 뒤 단계가 문안 패처가 쓴 바이트를 다시 바꾼 곳 {r['late']} > 허용 {ALLOWED_LATE_TOUCH[exe]}"
            )
    if not fail:
        print(
            f"  ✅ 패처 쓰기 구간 겹침 — 허용된 암묵 계약 {allowed_total}(ED.EXE 0x4EA0~0x4EAA) · 새 겹침 0"
        )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
