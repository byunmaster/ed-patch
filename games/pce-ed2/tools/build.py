"""pce-ed2 빌드 — 원본을 그대로 복사한 뒤 **선언한 자리만** 고쳐 쓴다 (pce-ed1 `build.py` 와 같은 규율).

    python3 games/pce-ed2/tools/build.py --edits work/edits_poc.json   # 개발/PoC 입력(커밋 안 함)
    python3 games/pce-ed2/tools/build.py --edits … --trim             # 트랙 1~2 만(에뮬용, 123MB)

규율(루트 CLAUDE.md 「빌드 규율」 · docs/patcher-checklist.md):
  · 원본은 읽기만(지문 확인) · 출력은 새 파일 · 실패하면 산출물을 `*.failed` 로 무효화
  · 쓰기는 `shared.disc.mode1.write_at`(EDC/ECC 재계산 + `expect` 사전조건)로만
  · 🔴 **데이터 트랙 거울**(rel 2~12,285 ↔ +36,864)은 **두 사본을 같은 바이트로** 쓴다(어느 쪽이 읽히는지 미확정)
  · **무변경 구간**: 쓰겠다고 선언한 섹터 밖은 원본과 byte 대조 · **덮어쓰기 장부** · **되읽기**(덩이 경계 · 글리프 풀)

편집 입력(PoC): [{"pkg": rel, "find_hex": 풀린 대본의 바이트열(패키지 안에서 정확히 한 번), "replace_text": 우리 문안 | "replace_hex": …}]
  — 문안의 한글은 글리프 풀에 실린다(번호순 = 코드포인트순, 결정적). 공백은 게임의 `60`.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import battle
import chapter
import codestr
import common
import ctrllines
import debugmode
import dialogue
import endcard
import ending
import ending_sub
import cardart
import syscard
import endtest
import font
import hook
import hudplate
import syscardcheck
import labels
import layout
import lz
import opening_sub
import package
import repack
import residual_gate
import systext
import wrap
import longline
import narrow

from shared.disc import mode1

MIRROR = 36864
MIRROR_SPAN = (2, 12286)  # 거울이 같은 rel 범위(common.py 게이트가 확인)
PKG_SECTORS = 128  # 패키지 칸(간격) — 실제 로드는 78섹터지만 칸 전체를 다룬다


MISSING_LABELS: set[str] = (
    set()
)  # 정본에 없어 못 바꾼 라벨 문구(원문 일본어 — 관리자 후보, work/review 로만 쓴다)


class BuildError(Exception):
    pass


class Writer:
    """쓰기 장부 · 무변경 대조용 섹터 집합 · 거울 이중 쓰기를 한 곳에 모은다."""

    def __init__(self, f):
        self.f = f
        self.spans: list[
            tuple[int, bytes, str]
        ] = []  # (선형 바이트, 새 바이트, 라벨) — 덮어쓰기 검사용
        self.touched: set[int] = set()  # 파일 섹터(LBA)

    @staticmethod
    def mirrored(linear: int, n: int) -> bool:
        lo, hi = MIRROR_SPAN
        return lo * common.USER <= linear and linear + n <= hi * common.USER

    def put(self, linear: int, new: bytes, expect: bytes | None, label: str) -> None:
        """선형 유저 데이터 바이트 `linear`(= rel×2048+오프셋)에 쓴다. 거울이 있으면 거울에도 같은 바이트."""
        targets = [linear]
        if self.mirrored(linear, len(new)):
            targets.append(linear + MIRROR * common.USER)
        for t in targets:
            lba = common.T2_SECTOR + t // common.USER
            off = t % common.USER
            mode1.write_at(
                self.f,
                lba,
                1 << 40,
                off,
                new,
                label=label + (" (거울)" if t != linear else ""),
                expect=expect,
            )
            self.spans.append((t, new, label))
            first = common.T2_SECTOR + t // common.USER
            last = common.T2_SECTOR + (t + len(new) - 1) // common.USER
            self.touched.update(range(first, last + 1))

    def verify(self, iso: Path) -> int:
        """**다 쓴 뒤에도 각 쓰기의 바이트가 그대로인가** — 뒤 단계가 앞 단계를 덮었으면 운다."""
        errs = []
        with open(iso, "rb") as f:
            for lin, data, label in self.spans:
                got = bytearray()
                lba, off = divmod(lin, common.USER)
                while len(got) < len(data):
                    f.seek((common.T2_SECTOR + lba) * common.RAW + common.USER_OFF)
                    got += f.read(common.USER)[off:]
                    lba, off = lba + 1, 0
                if bytes(got[: len(data)]) != data:
                    errs.append(f"「{label}」 @{lin} 가 덮였다")
        if errs:
            raise BuildError("쓴 바이트가 나중에 덮였다:\n  " + "\n  ".join(errs[:10]))
        return len(self.spans)


def load_edits(path: Path):
    return json.loads(path.read_text())


def family_rels() -> list[int]:
    """장 제목 덩이를 가진 패키지의 rel(앞 사본). 머리표(`4c ×3`) 섹터를 훑어 첫 덩이가 장 제목 꼴인 것만."""
    out = []
    for rel in range(2, MIRROR_SPAN[1]):
        u = common.user_sector(rel)
        if not (u[0] == 0x4C and u[3] == 0x4C and u[6] == 0x4C):
            continue
        pkg = bytes(common.track_data(rel, PKG_SECTORS))
        try:
            _t, tab = package.msg_table(pkg)
            if len(tab) < 14 or len(set(tab[1:14])) != 1:
                continue
            ch = dict(package.chunks(pkg))
            d, _ = package.decode_chunk(pkg, tab[1], ch[tab[1]])
        except (IndexError, KeyError, ValueError):
            continue
        if not chapter.is_chapter_chunk(d):
            continue
        try:
            repack.text_region(pkg)
        except repack.RepackError:
            print(
                f"  ⚠ 패키지 rel {rel}: 끝 표시 꼴이 달라 장 제목을 못 고친다(건너뜀 — status 「남은 일」)"
            )
            continue
        out.append(rel)
    return out


class TableFit(Exception):
    """지역 글리프 표가 패키지 꼬리에 안 들어간다."""


def _place_table(new: bytearray, local: list[str], T: int, limit: int) -> None:
    """지역 글리프 표(18B × n)를 꼬리 채움(0xFF)의 **한 뱅크 안**에 놓고 메시지 표 항목 0 에 포인터를 쓴다.
    ⚠ `new` 의 메시지 표를 다시 풀지 않는다 — 덩이를 옮기면 가장 작은 포인터가 뒤로 밀려 표 길이를 잘못 읽는다. 표 위치 `T` · 채움 끝 `limit` 은 원본에서 받는다."""
    sent = limit
    while sent > T and new[sent - 1] == 0xFF:
        sent -= 1
    n = len(local) * font.PACKED_BYTES
    ts = limit - n
    if (ts >> 13) != ((ts + n - 1) >> 13):  # 뱅크 경계를 넘으면 경계 바로 아래로 내린다
        ts = (((ts + n - 1) >> 13) << 13) - n
    if ts < sent + 8:  # 끝 표시 8바이트(0xFF)는 남긴다
        raise TableFit(f"지역 글리프 {len(local)}자({n}B)가 꼬리 {limit - sent}B 에 안 들어간다")
    for k, ch in enumerate(local):
        new[ts + k * font.PACKED_BYTES : ts + (k + 1) * font.PACKED_BYTES] = font.pack(font.glyph(ch), font.flags(ch))
    bank, off = ts >> 13, ts & 0x1FFF
    new[T], new[T + 1] = off & 0xFF, (bank << 5) | (off >> 8)


def _plan_one(rel, raw, tab: font.GlyphTable, dialogue_allowed: set[str] | None, local: list[str]):
    """패키지 하나의 새 바이트 — `local` 은 이 패키지의 지역 글리프(정렬됨, 코드 = S + 순번)."""
    dialogue.reset_marks()
    S = len(tab.map) if tab.map is not None else 0
    tab.local = {ch: S + k for k, ch in enumerate(local)}
    pkg = bytes(common.track_data(rel, PKG_SECTORS))
    ch = [(a, b) for a, b in package.chunks(pkg) if pkg[a : a + 8] != package.SENTINEL]
    decoded = {a: package.decode_chunk(pkg, a, b)[0] for a, b in ch}
    orig_decoded = dict(decoded)
    for a, d in orig_decoded.items():
        if chapter.is_chapter_chunk(d):  # 장 제목 띠(장 카드)
            decoded[a] = chapter.edit(d, tab)
        elif systext.is_menu_chunk(d):  # 상점·예/아니오 메뉴 덩이
            decoded[a] = systext.edit_menu_chunk(d, tab, MISSING_LABELS)
        else:  # 지명 라벨(패널 지명 · 왕국·도시 목록) — 정본에 없는 문구는 MISSING_LABELS 에 모은다
            decoded[a] = labels.edit_chunk(d, tab, MISSING_LABELS)
        if battle.is_battle_chunk(d):  # 전투 덩이 — 나타남·행동 줄을 정본 battle 틀로
            decoded[a] = battle.edit_chunk(decoded[a], tab, MISSING_LABELS)
        if not chapter.is_chapter_chunk(d):  # 장 끝 카드(정본 문안)
            decoded[a] = endcard.edit_chunk(decoded[a], tab)
            if EDIT_ANY_LABELS:  # 전투 덩이의 몬스터 이름 등 — 용량 때문에 링 창 확대(status A안) 전까지 끈다
                decoded[a] = labels.edit_any_lines(decoded[a], tab, MISSING_LABELS, dialogue.covered(rel, a))
        if dialogue_allowed is not None and not chapter.is_chapter_chunk(d):
            decoded[a] = dialogue.edit_chunk(rel, a, decoded[a], tab, dialogue_allowed | set(local))
        if not chapter.is_chapter_chunk(d):  # 제어(이름·항목·수·쪽 넘김)가 낀 줄 — 틀 번역(수령·상점·보물상자·화자 머리줄 …)
            decoded[a] = ctrllines.edit_chunk(d, decoded[a], tab, dialogue.STATS)
    for e in (x for x in raw if x["pkg"] == rel):  # PoC 찾아 바꾸기
        find = bytes.fromhex(e["find_hex"])
        hits = [(a, d.count(find)) for a, d in decoded.items() if find in d]
        if len(hits) != 1 or hits[0][1] != 1:
            raise BuildError(f"패키지 {rel}: 찾는 바이트가 정확히 한 번이 아니다 {hits} — {find.hex()}")
        a = hits[0][0]
        rep = bytes.fromhex(e["replace_hex"]) if "replace_hex" in e else tab.enc(e["replace_text"])
        decoded[a] = decoded[a].replace(find, rep)
    changed = {a: d for a, d in decoded.items() if d != orig_decoded[a]}
    try:
        new, place = repack.repack(pkg, changed)
    except repack.RepackError as ex:
        raise BuildError(f"패키지 {rel}: {ex}") from ex
    if dialogue_allowed is not None and any(sp.rel == rel for sp in codestr.SPECS):  # 코드 영역의 일본어 문장(메시지 표 밖) — 0xFF 패딩으로 옮기고 포인터를 돌린다
        nb = bytearray(new)
        try:
            codestr.apply(rel, pkg, nb, tab)
        except (ValueError, KeyError) as ex:  # KeyError = 글자가 풀 밖 — package_chars 에 넣었으니 일어나면 안 된다
            raise BuildError(f"패키지 {rel}: 코드 문자열 — {ex}") from ex
        new = bytes(nb)
    if local:
        nb = bytearray(new)
        T0, _tb = package.msg_table(pkg)
        _place_table(nb, local, T0, repack.text_region(pkg)[1])
        new = bytes(nb)
    return pkg, new, place, changed


def _pkg_caps(raw, tab: font.GlyphTable) -> dict[int, int]:
    """패키지마다 **전부 번역했을 때** 꼬리에 남는 자리로 담을 수 있는 지역 글리프 수 — 정적 풀을 누구에게 먼저 줄지 정하는 눈금이다."""
    allc = set().union(*dialogue.package_chars().values()) if dialogue.package_chars() else set()
    tmp = font.GlyphTable()
    tmp.map = {c: i for i, c in enumerate(sorted(set(tab.chars) | allc))}  # 길이만 맞으면 되는 가짜 번호 — 압축률이 조금 다를 수 있다
    caps = {}
    dialogue.KEEP_MARKS = False  # 용량 눈금은 타이밍 제어 없이 잰다(타이밍은 패키지별로 나중에 살릴 수 있을 만큼만)
    for rel in sorted(dialogue.package_chars()):
        try:
            pkg, new, _pl, _ch = _plan_one(rel, raw, tmp, set(tmp.map), [])
        except BuildError:
            caps[rel] = 0
            continue
        _f, limit, real = repack.text_region(pkg)
        free = limit
        while free > 0 and new[free - 1] == 0xFF:
            free -= 1
        caps[rel] = max(0, min(255, (limit - free - 24) // font.PACKED_BYTES))
    dialogue.KEEP_MARKS = True
    return caps


def _missing_chars(rel, static: set[str]):
    """이 패키지에서 번역할 수 있는 줄이 정적 풀 밖에서 더 쓰는 글자 → 줄 수(내림차순 · 코드포인트순 목록)."""
    from collections import Counter

    pkg = bytes(common.track_data(rel, PKG_SECTORS))
    cnt: Counter = Counter()
    for a, b in package.chunks(pkg):
        if pkg[a : a + 8] == package.SENTINEL:
            continue
        d = package.decode_chunk(pkg, a, b)[0]
        for _li, _p, spk, txt in dialogue.candidates(rel, a, d):
            cnt.update(set(c for c in "".join(txt + (spk or "")) if c not in " \u3000\n\f§") - static)
    for c in codestr.chars_by_pkg().get(rel, set()) - static:  # 코드 영역 문장의 글자는 줄 하나가 아니라 필수다 — 맨 앞에
        cnt[c] += 10_000
    return [c for c, _n in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))]


def _search_local(rel, raw, tab: font.GlyphTable, static: set[str]):
    """지역 글리프 수 L 을 이분 탐색한다 — 더 많은 글자 → 더 많은 줄 번역 → 커지는 문안·표가 패키지에 들어가는 가장 큰 L."""
    ranked = _missing_chars(rel, static)
    lo, hi = 0, min(len(ranked), 255)
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        local = sorted(ranked[:mid])
        dialogue.STATS.clear()
        dialogue.UNFIT.clear()
        try:
            res = _plan_one(rel, raw, tab, static, local)
        except (BuildError, TableFit):
            hi = mid - 1
            continue
        best = (res, dict(dialogue.STATS), mid, dict(dialogue.UNFIT))
        lo = mid + 1
    return best


POOL_MARGIN = 3  # 정적 풀 용량에서 덜어 두는 글자 수 — 수집 단계 이후 늘어나는 글자(시스템 배치 · 전투 줄)의 여유
import os as _os
EDIT_ANY_LABELS = _os.environ.get("ED_ANY_LABELS") != "0"  # 전투 덩이 몬스터 이름 라벨 등 — 용량이 모자라 꺼 뒀으나 11×11 묶음 풀 이후 들어간다(10-16 실측). 끄려면 ED_ANY_LABELS=0
MARKS_PARTIAL: list[tuple[int, int]] = []  # (패키지, 살린 줄 수) — 공간이 모자라 연출 타이밍 제어를 일부만 살린 패키지


def _plan_with_local(rel, raw, tab: font.GlyphTable, static: set[str]):
    """연출 타이밍 제어(`10`/`11`)를 전부 살린 채로 먼저 풀어 보고, 번역 줄 수가 줄면(공간 부족) 타이밍 제어를 끈 쪽과 비교한다.
    끈 쪽이 줄 수가 많으면, **번역 줄 수를 안 잃는 한 가장 많은 줄(앞 줄부터)의 타이밍 제어를 살린다**(이분 탐색) — 다 끄지 않는다."""
    dialogue.MARK_LINES = None
    dialogue.KEEP_MARKS = True
    a = _search_local(rel, raw, tab, static)
    dialogue.KEEP_MARKS = False
    b = _search_local(rel, raw, tab, static)
    dialogue.KEEP_MARKS = True
    if a is None and b is None:
        raise BuildError(f"패키지 {rel}: 지역 글리프 없이도 안 들어간다")
    if b is not None and (a is None or a[1].get("번역", 0) < b[1].get("번역", 0)):
        want = b[1].get("번역", 0)
        lo, hi, best = 0, 2000, b
        while lo <= hi:
            mid = (lo + hi) // 2
            dialogue.MARK_LINES = mid
            c = _search_local(rel, raw, tab, static)
            if c is not None and c[1].get("번역", 0) >= want:
                best, lo = c, mid + 1
            else:
                hi = mid - 1
        dialogue.MARK_LINES = None
        MARKS_PARTIAL.append((rel, hi))  # hi = 타이밍 제어를 살린 줄 수(마지막으로 들어간 값)
        return best
    return a


def plan_packages(raw, tab: font.GlyphTable, dialogue_allowed: set[str] | None = None, local: bool = False) -> dict:
    """패키지마다 새 바이트를 계획한다. 수집 단계(`tab.map is None`)에선 글자만 모은다. 반환 {rel: (원본, 새, 배치, 바뀐 덩이)}.
    `local` = 확정 단계에서 패키지별 지역 글리프 표를 이분 탐색으로 정한다(정적 풀은 `tab.map`)."""
    rels = sorted(set(family_rels()) | {e["pkg"] for e in raw})
    out = {}
    totals: dict = {}
    all_unfit: dict = {}
    nlocal = 0
    for rel in rels:
        if local and dialogue_allowed is not None:
            res, st, mid, unfit = _plan_with_local(rel, raw, tab, dialogue_allowed)
            out[rel] = res
            nlocal += mid
            all_unfit.update(unfit)
            for k, v in st.items():
                totals[k] = totals.get(k, 0) + v
        else:
            out[rel] = _plan_one(rel, raw, tab, dialogue_allowed, [])
    if local:
        print(f"  연출 타이밍 제어를 일부만 살린 패키지(공간 부족, 패키지·살린 줄 수): {MARKS_PARTIAL}")
        dialogue.STATS.clear()
        dialogue.STATS.update(totals)
        dialogue.UNFIT.clear()
        dialogue.UNFIT.update(all_unfit)
        print(f"  패키지 지역 글리프 합계 {nlocal}자")
    return out


def apply_pkg_edits(w: Writer, plan: dict) -> dict:
    """계획대로 쓴다. 반환: 되읽기 대조용 {rel: (새 패키지 바이트, {새 시작: 풀린 내용})}."""
    intended = {}
    for rel, (pkg, new, place, changed) in sorted(plan.items()):
        diff = [i for i in range(len(pkg)) if pkg[i] != new[i]]
        if not diff:
            continue
        lo, hi = diff[0], diff[-1] + 1
        w.put(rel * common.USER + lo, new[lo:hi], pkg[lo:hi], f"package rel {rel} text +{lo}")
        intended[rel] = (new, {place[a]: d for a, d in changed.items()})
    moved = sum(1 for _p, _n, place, _c in plan.values() for a, s in place.items() if a != s)
    print(f"  패키지 {len(intended)}개 · 덩이 이사 {moved}")
    return intended


def plan_program(tab: font.GlyphTable, glyph24: list[bytes] | None, chars: list[str] | None = None) -> layout.Prog:
    """본 프로그램 패치 계획 — 후킹 자리 예약 → 시스템 문구 배치 → (확정 단계에서) 글리프 풀. 수집 단계는 글리프 풀을 안 앉힌다."""
    prog = layout.Prog()
    systext.reclaim_dead(prog)  # 죽은 전투 디버그 문구 271B → 글리프 풀
    hook.reserve(prog)
    wrap.reserve(prog)
    longline.reserve(prog)
    narrow.reserve(prog)
    systext.MISSING.clear()
    systext.OVERFLOW.clear()
    systext.plan(prog, tab)
    if glyph24 is not None:
        flags = [font.flags(c) for c in chars] if chars else None
        josa_idx = [tab.map[c] for pair in font.JOSA for c in pair] if tab.map else None
        seen_bm: dict[bytes, str] = {}
        for ch_, g_ in zip(chars or [], glyph24, strict=False):  # 구운 글리프끼리 같은 비트맵이면 실패(ss-ed1+2 10-20: 쉼표가 마침표와 같은 비트맵으로 구워져 3,983곳이 전부 마침표였다)
            if g_ in seen_bm:
                raise BuildError(f"구운 글리프끼리 같은 비트맵: 「{seen_bm[g_]}」 = 「{ch_}」")
            seen_bm[g_] = ch_
        hook.install(prog, glyph24, flags, josa_idx)
        wrap.install(prog)
        longline.install(prog)
        narrow.install(prog)
    return prog


def write_review() -> None:
    """관리자에게 올릴 후보(정본에 없는 문구 · 칸을 넘는 라벨)를 work/review 로만 쓴다 — 원문이라 커밋하지 않는다."""
    lines = [f"[패키지 라벨] {x}" for x in sorted(MISSING_LABELS)]
    lines += [
        f"[칸 초과] {k} → {v[0]} ({v[1]}px > {v[2]}px)" for k, v in sorted(labels.OVERFLOW.items())
    ]
    lines += [
        f"[뱅크 자리 부족] {b:02X}+{o:04X} {old}B → {new}B  {jp}"
        for b, o, old, new, jp in sorted(systext.OVERFLOW)
    ]
    for k, v in sorted(systext.MISSING.items()):
        lines += [f"[시스템 {k}] {x}" for x in sorted(v)]
    if not lines:
        return
    out = common.REVIEW_DIR / "missing_labels.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"  정본에 없거나 칸을 넘는 라벨 {len(lines)}개 → {out.relative_to(common.ROOT)} (관리자 후보)"
    )


def apply_program(w: Writer, prog: layout.Prog, glyph24: list[bytes]) -> None:
    for lin, new, old, label in prog.spans():
        w.put(lin, new, old, f"prog {label}")
    print(
        f"  본 프로그램 쓰기 {len(prog.spans())}곳 · 글리프 풀 {len(glyph24)}자 · 남은 자유 공간 {sum(r[2] for r in prog.runs_left())}B"
    )


def verify_readback(iso: Path, intended: dict, prog: layout.Prog) -> None:
    """구운 이미지를 다시 읽어: 패키지가 의도한 바이트이고(거울 포함) · 고친 덩이가 의도대로 풀리고 · 글리프 풀이 `font` 와 같다."""

    def track(rel, n):
        with open(iso, "rb") as f:
            out = bytearray()
            for i in range(n):
                f.seek((common.T2_SECTOR + rel + i) * common.RAW + common.USER_OFF)
                out += f.read(common.USER)
        return bytes(out)

    n = 0
    for rel, (want, chunks) in sorted(intended.items()):
        for r in [rel] + ([rel + MIRROR] if MIRROR_SPAN[0] <= rel < MIRROR_SPAN[1] else []):
            got = track(r, PKG_SECTORS)
            if got != want:
                raise BuildError(f"되읽기: rel {r} 패키지가 의도와 다르다")
            for start, d in chunks.items():
                back, _ = lz.decode(got, start, len(d))
                if back != d:
                    raise BuildError(f"되읽기: rel {r} 덩이 {start} 가 의도와 다르다")
                n += 1
    spans = prog.spans()
    for lin, new, _old, label in spans:
        rel = lin // common.USER
        got = track(rel, (lin % common.USER + len(new) + common.USER - 1) // common.USER)[
            lin % common.USER :
        ][: len(new)]
        if got != new:
            raise BuildError(f"되읽기: 프로그램 「{label}」 가 다르다")
    print(f"  되읽기 OK (고친 덩이 {n} · 프로그램 쓰기 {len(spans)})")


def verify_immutable(iso: Path, touched: set[int], limit_sectors: int | None) -> None:
    """선언한 섹터 밖은 원본과 byte 동일해야 한다."""
    n = 0
    with open(common.ORIG_ISO, "rb") as a, open(iso, "rb") as b:
        chunk = 4096 * common.RAW
        lba = 0
        while True:
            x = a.read(chunk)
            y = b.read(chunk)
            if limit_sectors is not None and lba * common.RAW >= limit_sectors * common.RAW:
                break
            if not y:
                break
            x = x[: len(y)]
            if x != y:
                for i in range(0, len(y), common.RAW):
                    if (
                        x[i : i + common.RAW] != y[i : i + common.RAW]
                        and (lba + i // common.RAW) not in touched
                    ):
                        raise BuildError(
                            f"무변경 구간이 바뀌었다: 파일 섹터 {lba + i // common.RAW}"
                        )
            lba += chunk // common.RAW
            n = lba
    print(f"  무변경 대조 OK (허용 {len(touched)}섹터 밖 동일, 대조 {n}섹터)")


def build(edits_path: Path | None, trim: bool, dialogue_on: bool = True) -> Path:
    common.verify_originals()
    # 🔴 잘라 낸 에뮬용(트랙 1~2)은 배포용 칸에 두지 않는다 — 오디오 트랙이 빠진 이미지가 파일서버로 나가 BGM 이 안 났다(10-12)
    out_dir = common.BUILD_DIR / (common.BUILD_TAG + ("-trim" if trim else ""))
    out_dir.mkdir(parents=True, exist_ok=True)
    iso = out_dir / f"{common.ROM_STEM}.iso"
    cue = out_dir / f"{common.ROM_STEM}.cue"
    for p in (iso, cue, out_dir / f"{common.ROM_STEM}.iso.failed"):
        if p.exists():
            p.unlink()
    try:
        _build(edits_path, iso, cue, trim, dialogue_on)
    except Exception:
        if iso.exists():
            iso.rename(out_dir / f"{common.ROM_STEM}.iso.failed")
        raise
    return iso


def check_full_layout(iso: Path, cue: Path) -> None:
    """전 트랙 이미지 계약 — 원본과 같은 크기 · 같은 트랙 구성(24트랙, 오디오 포함). 오디오 바이트는 무변경 대조(verify_immutable)가 지킨다."""
    if iso.stat().st_size != common.ORIG_ISO.stat().st_size:
        raise BuildError(f"이미지 크기가 원본과 다르다: {iso.stat().st_size} ≠ {common.ORIG_ISO.stat().st_size}")
    want = common.ORIG_CUE.read_text().replace(common.ORIG_ISO.name.upper(), f"{common.ROM_STEM}.iso")
    if cue.read_text() != want:
        raise BuildError("cue 가 원본 트랙 구성과 다르다")
    n = want.count("TRACK ")
    if n != 24:
        raise BuildError(f"트랙 수 {n} ≠ 24")


def _build(edits_path, iso: Path, cue: Path, trim: bool, dialogue_on: bool = True) -> None:
    limit = common.T2_SECTOR + common.T2_LEN  # 트랙 1~2 의 파일 섹터 수
    if trim:
        with open(common.ORIG_ISO, "rb") as a, open(iso, "wb") as b:
            b.write(a.read(limit * common.RAW))
        cue.write_text(
            f'FILE "{common.ROM_STEM}.iso" BINARY\n  TRACK 01 AUDIO\n    INDEX 01 00:00:00\n'
            "  TRACK 02 MODE1/2352\n    PREGAP 00:03:00\n    INDEX 01 00:44:71\n"
        )
    else:
        shutil.copyfile(common.ORIG_ISO, iso)
        text = common.ORIG_CUE.read_text().replace(common.ORIG_ISO.name.upper(), f"{common.ROM_STEM}.iso")
        if f"{common.ROM_STEM}.iso" not in text:
            raise BuildError("cue 의 FILE 이름을 못 바꿨다")
        cue.write_text(text)
        check_full_layout(iso, cue)
    raw = load_edits(edits_path) if edits_path else []
    def attempt(margin: int):
        """한 번의 계획 — 정적 풀 여유 `margin` 으로 글자를 고르고 끝까지 계획한다. 풀이 넘치면 `hook.PoolOverflow`."""
        tab = font.GlyphTable()
        plan_packages(raw, tab)  # ① 수집 — 글자를 모은다(패키지 · 시스템 문구)
        prog0 = plan_program(tab, None)
        allowed = None
        if dialogue_on:  # 대사 — 글리프 풀 예산 안에서 쓸 글자를 정하고, 그 글자만 쓰는 줄을 번역한다
            cap = hook.pool_capacity(prog0) - margin
            caps = _pkg_caps(raw, tab)
            allowed = dialogue.choose(set(tab.chars), cap - len(tab.chars), caps)
            plan_packages(raw, tab, allowed)
        dialogue.STATS.clear()
        dialogue.UNFIT.clear()
        MARKS_PARTIAL.clear()
        chars = tab.freeze()  # ② 번호 확정(코드포인트순, 결정적)
        glyph24 = [font.glyph(ch) for ch in chars]
        plan = plan_packages(raw, tab, set(tab.map), local=dialogue_on)  # ③ 같은 계획을 진짜 코드로 다시(+ 패키지별 지역 글리프)
        prog = plan_program(tab, glyph24, chars)
        return tab, plan, prog, glyph24, chars

    margin = POOL_MARGIN
    while True:  # 정적 풀이 넘치면(수집 뒤 늘어난 글자) 여유를 그만큼 늘려 처음부터 다시 — 상수 여유가 모자라도 빌드가 안 깨진다
        try:
            tab, plan, prog, glyph24, chars = attempt(margin)
            break
        except hook.PoolOverflow as e:
            if not dialogue_on:
                raise
            margin += e.over
            print(f"  글리프 풀 {e.over}자 초과 — 여유를 {margin} 로 늘려 다시 고른다")
    if dialogue_on:  # 정적 풀에 **쓰이지 않은 허용 글자·여유**가 남는다(허용 글자 중 실제 번역에 안 쓰인 것 + 안전 여유) — 여유를 줄여 가며(음수 포함) 들어가는 한 가장 많은 글자를 정적으로 둔다. 정적이 되면 그 글자는 패키지 지역 글리프(16B 씩)에서 빠져 연출 멈춤(3B 씩)이 산다(10-20 1282 멈춤)
        for step in (8, 4, 2, 1):
            while margin - step >= POOL_MARGIN - 16:
                try:
                    tab2, plan2, prog2, glyph242, chars2 = attempt(margin - step)
                except hook.PoolOverflow:
                    break
                margin -= step
                tab, plan, prog, glyph24, chars = tab2, plan2, prog2, glyph242, chars2
        print(f"  글리프 풀 여유 {margin} · 정적 글리프 {len(chars)}자")
    if dialogue_on:
        print(f"  대사 줄: 번역 {dialogue.STATS['번역']} · 글리프 예산 밖(원문 유지) {dialogue.STATS['예산 밖']} · 18 인자 불가 {dialogue.STATS['18 인자 불가']} · 화자 정본 없음 {sum(1 for v in dialogue.UNFIT.values() if v.startswith('화자'))}")
        (common.REVIEW_DIR / "dialogue_unfit.tsv").write_text(
            "\n".join(f"{k}\t{v}" for k, v in sorted(dialogue.UNFIT.items())) + "\n", encoding="utf-8"
        )
    with open(iso, "r+b") as f:
        w = Writer(f)
        apply_program(w, prog, glyph24)
        intended = apply_pkg_edits(w, plan)
        opening_sub.apply(w)  # 오프닝 나레이션 자막(모듈 rel 4098 — 본 프로그램과 다른 이미지)
        ending_sub.apply(w)  # 대관식 성우 대사 자막(패키지 38 — ADPCM 셀 데이터 + 뱅크 0x86 코드)
        ending.apply(w)  # 엔딩 스태프롤(패키지 41) — 분야 라벨·엔딩 대사 번역 + 자체 글리프 후킹
        syscard.apply(w)  # 시스템 카드·백업 RAM 안내문 넷(패키지 20) — 번역 + 자체 글리프 후킹
        cardart.apply(w)  # 그 화면의 그림 글자(간판 만실·여관 · 말풍선 헉 — 패키지 20 LZSS 덩이)
        hudplate.apply(w)  # HUD 판 라벨 「アト」 → 「남다」(마스터 도트, pce-ed1 정본 그대로 — 판 타일 묶음 rel 186)
        if syscardcheck.enabled():  # 마스터 확인용(꼬리표 syscard-check) — 새 게임이 카드 안내 화면으로 간다
            syscardcheck.apply(w)
        if endtest.enabled():  # 엔딩 직행 시험 빌드(환경 변수 ED_ENDING_TEST=1 — 정본 빌드엔 안 들어간다)
            endtest.apply(w)
        if debugmode.enabled():  # 디버그 빌드(ED_DEBUG=1 + test-* 꼬리표 — 제품 롬엔 안 들어간다)
            debugmode.apply(w)
    write_review()
    if systext.INTERIOR_WARN:
        print(f"  ⚠ 문자열 안쪽 쓰기 짝을 못 찾음 {len(systext.INTERIOR_WARN)}곳: {systext.INTERIOR_WARN[:6]}")
    print(f"  덮어쓰기 없음 (쓰기 구간 {w.verify(iso)})")
    verify_immutable(iso, w.touched, limit if trim else None)
    verify_readback(iso, intended, prog)
    bad = mode1.selftest(
        iso, lbas=(common.T2_SECTOR + 2, common.T2_SECTOR + 386, common.T2_SECTOR + 4098)
    )
    if bad:
        raise BuildError(f"EDC/ECC 자기검증 실패: {bad}")
    if dialogue_on and not trim and not common.BUILD_TAG.startswith("test-"):  # 10-18 장면 패키지 전수 잔존 게이트(패키지 21 누락 재발 방지)
        errs, now = residual_gate.evaluate(iso)
        if errs:
            raise BuildError("잔존 게이트: " + " / ".join(errs))
        print(f"  잔존 게이트 OK (본편 {len(package.CLEAN)}개 패키지 · 알려진 잔존 {len(now)}줄)")
    import romtag

    romtag.stamp(str(iso))
    print(f"빌드 OK: {iso}  sha1 {common.sha1_of(iso)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", type=Path, help="PoC 편집 입력 JSON (work/ 아래, 커밋 안 함)")
    ap.add_argument("--trim", action="store_true", help="트랙 1~2 만(에뮬용)")
    ap.add_argument("--no-dialogue", action="store_true", help="대사 번역을 뺀다(글리프 풀 예산 안에서 PS1 정본이 같은 줄만 번역한다)")
    a = ap.parse_args()
    build(a.edits, a.trim, not a.no_dialogue)


if __name__ == "__main__":
    main()
