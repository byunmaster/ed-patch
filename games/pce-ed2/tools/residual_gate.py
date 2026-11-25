"""장면 패키지 전수 잔존 게이트 — 최종 롬에 **원본 일본어가 그대로 남은 줄**이 알려진 자리 밖에 있으면 실패한다 (10-18, 패키지 21 누락의 재발 방지).

    python3 games/pce-ed2/tools/residual_gate.py [ISO 경로]   # 기본 = 제품 이미지(common.BUILD_DIR/<꼬리표>/ed2.iso)
    python3 games/pce-ed2/tools/residual_gate.py --freeze    # 알려진 목록 `data/jp_residual.tsv` 를 지금 상태로 다시 쓴다(줄어든 것만 내린다 — 래칫)

왜: 번역 정본이 패키지 12개에서 멈춰 최종 장면(21)이 통째로 일본어로 남았는데 어떤 게이트도 못 잡았다(검사의 분모가 정본 목록 자체였다).
이 게이트의 분모는 **롬 전체**다 — 메시지 표가 정상이고 덩이가 8개 이상인 「장면 꼴 패키지」를 전부 훑는다.
  · 본편(`package.CLEAN` 13개): 원본에서 일본어(가나·한자 4자↑)가 있던 줄이 롬에서 **바이트까지 그대로**면 잔존이다. 알려진 목록에 없으면 실패.
    알려진 목록(`data/jp_residual.tsv`)에는 열쇠(`rel:메시지번호:줄`)와 분류만 둔다(원문 없음): 현재는 몬스터·보스 행동 문장(정본 후보 대기)뿐.
  · 본편 밖은 **번호와 근거**로 못 박는다(아래 상수). 장면 꼴인데 본편에도 제외 목록에도 없는 패키지가 새로 보이면 실패한다.
알려진 목록의 낡은 열쇠(이제 번역된 줄)도 실패시킨다 — 번역이 늘면 목록이 줄어야 한다.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared"))
import common
import jptext
import package

KNOWN = common.GAME_DIR / "data" / "jp_residual.tsv"
JP = re.compile(r"[ぁ-んァ-ヶ一-龥]")
MIN_JP = 1  # 줄 하나에 일본어 글자가 이만큼↑이면 잔존으로 센다 — 4 로 두면 짧은 문장(「はい」 류)이 샌다(10-18 md-ed1 발견)

# 본편 밖 — 근거는 `docs/status.md` 「장면 패키지 전수(10-18)」 · 전수표는 레포 밖(.local/work/inbox/pce-ed2/foundation/scene_census.tsv)
BATTLE_TEST = {
    16,
    17,
    18,
    19,
    28,
    29,
}  # 제목 덩이 「…バトルテスト」 · 전투 덩이 30/30/20/18/30/30 — 개발자용 전투 시험 장면, 정상 진행에서 닿는지 미확인(마스터 판단 거리)
UNDECIDED = {
    15,
    30,
    31,
    71,
    78,
    79,
    82,
    83,
    84,
    114,
    116,
    117,
}  # ED2 낱말도 지방 이름도 없다 — 내용 판정 불가(대사 줄 0)
NOT_ED2 = {  # ED2 낱말 0~1 개 · 일본 옛 지방 이름·「ヘタな絵」 류 문구 — 같은 엔진을 쓴 다른 타이틀의 잔재로 보인다(추정)
    22, 23, 24, 25, 26, 27, 34, 48, 49, 51, 52, 54, 55, 57, 58, 60, 61, 63, 64, 65, 66, 67, 68, 69, 70, 72, 73, 74, 75, 76, 77,
    80, 81, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111,
}  # fmt: skip


def scene_like(rel: int) -> bool:
    pkg = bytes(common.track_data(rel, 128))
    try:
        _t, tab = package.msg_table(pkg)
        return 5 < len(tab) < 200 and len(package.chunks(pkg)) >= 8
    except Exception:
        return False


def _built(iso: Path):
    f = open(iso, "rb")

    def track(rel: int, n: int = 128) -> bytes:
        out = []
        for i in range(n):
            f.seek((common.T2_SECTOR + rel + i) * common.RAW + common.USER_OFF)
            out.append(f.read(common.USER))
        return b"".join(out)

    return track


def _msgs(pkg: bytes) -> dict[int, bytes]:
    """메시지 번호 → 디코드한 덩이."""
    t, tab = package.msg_table(pkg)
    ch = dict(package.chunks(pkg))
    return {
        m: package.decode_chunk(pkg, p, ch[p])[0] for m, p in enumerate(tab) if p > t and p in ch
    }


def residual(rel: int, track) -> dict[str, str]:
    """{`rel:메시지:줄` → 분류} — 원본 일본어 줄이 롬에서 그대로인 곳. 분류: `행동` = 몬스터·보스 행동 문장(전투 덩이 안이거나 줄 머리가 이름 자리표 `1B`), `기타` = 그 밖."""
    po = bytes(common.track_data(rel, 128))
    pb = track(rel)
    mo, mb = _msgs(po), _msgs(pb)
    out = {}
    for m, d in mo.items():
        if m not in mb:
            continue
        lo, lb = d.split(b"\x00")[:-1], mb[m].split(b"\x00")[:-1]
        if len(lo) > 400 or len(lo) != len(lb):  # 400↑ = 패키지 꼬리(압축 자료)가 덩이로 잡힌 것
            continue
        try:
            import battle

            isb = battle.is_battle_chunk(d)
        except Exception:
            isb = False
        for li, (x, y) in enumerate(zip(lo, lb, strict=True)):
            t = re.sub(r"\{[^}]*\}|[-]", "", jptext.decode(x))
            if len(JP.findall(t)) >= MIN_JP and jp_left(y):
                out[f"{rel}:{m}:{li}"] = (
                    "행동" if (isb or b"\x1b" in x[:3]) else "기타"
                )  # 1B = 행동한 쪽 이름 자리표(이름 + 술어 꼴)
    return out


def jp_left(built: bytes) -> bool:
    """롬의 줄에 **원본 일본어 글리프**가 하나라도 남았나 — 한글 글리프 코드(리드 `F0~F9`)는 일본어 글꼴 표에 없어 `{HHHH}` 로 풀리므로 그것을 지운 나머지에 가나·한자가 있으면 남은 것이다.
    ⚠ 「줄이 원본과 바이트까지 같다」는 옛 판정은 구멍이었다 — 이름만 일본어로 남은 줄(앞 이름 + 번역된 꼬리)은 번역된 구간이 겹쳐 있어 통과했다(sfc-ed2 가 같은 구멍을 찾았다, 10-18)."""
    return bool(JP.search(re.sub(r"\{[^}]*\}|[-]", "", jptext.decode(_drop_narrow_han(built)))))

def _drop_narrow_han(b: bytes) -> bytes:
    """좁은 글꼴 한글(`narrowhan` — 리드 `FA` + 번호, 디버그 마을 목록)을 걷는다 — SJIS 로 읽으면 희귀 한자가 되어 일본어 잔존으로 오판된다. 두 바이트 글자를 앞에서부터 짝지어 읽으므로 JP 글자의 뒤 바이트 `FA` 는 건드리지 않는다."""
    out = bytearray()
    i = 0
    while i < len(b):
        c = b[i]
        if c == 0xFA:
            i += 2
        elif 0x81 <= c <= 0x9F or 0xE0 <= c <= 0xF9:  # (F0~F9 = 한글 글리프 리드 — 둘째 바이트가 `FA` 인 코드(예 F2FA)를 좁은 한글 리드로 오인해 다음 바이트를 지우던 구멍, 11-10)
            out += b[i : i + 2]
            i += 2
        else:
            out.append(c)
            i += 1
    return bytes(out)



CODE_JP = re.compile(
    rb"(?:\x82[\x9f-\xf1]|\x83[\x40-\x96]){4,}"
)  # SJIS 가나(히라가나 82 9F-F1 · 가타카나 83 40-96) 4자↑ 연속


def code_jp(pkg: bytes) -> list[int]:
    """패키지의 **메시지 표 앞 코드 영역**에 일본어 가나 문장이 남은 오프셋. 번역 단위 목록(메시지 표 목표)도 `residual()` 도 못 보는 자리다 —
    10-18 재검수에서 `JSR $403C · BIT 포인터` 인라인 문자열 4종 6곳(능력치 감소·합계 피해 …)이 롬에 그대로 있었다. 한글 글리프는 리드 `F0~F9` 라 이 패턴에 안 걸린다."""
    try:
        t, tab = package.msg_table(pkg)
        first = min(p for p in tab if p > t)
    except Exception:
        return []
    return [m.start() for m in CODE_JP.finditer(pkg[:first])]


RAW_PKGS = list(
    range(1, 128)
)  # 11-06 전 패키지로 확대(종전 31~35·40~69 — 장면 꼴 아닌 A형·자료형). 새 일본어 런이 어디서 생기든 실패
# 디버그 마을(패키지 258)과 거기서 걸어 닿는 배틀 테스트 마을(16~19, 28·29) — 제품에서 들어갈 수 있는 화면이라 일본어 잔존을 게이트로 본다(관리자 11-09).
# 258 은 번역했고 장 제목 띠 덩이(메시지 1~13 — 화면에 안 나오고, 고치면 상단 「ETC. TEST」 옆에 글자 하나가 남는다)만 남는다. 배틀 테스트 마을은 번역 전이라 알려진 목록이 곧 현재 줄 전부다(줄어들면 `--freeze`).
DEBUG_RELS = [258] + [n * 128 + 2 for n in sorted(BATTLE_TEST)]
DEBUG_KNOWN = common.GAME_DIR / "data" / "jp_residual_debug.tsv"


def debug_known() -> set[str]:
    if not DEBUG_KNOWN.exists():
        return set()
    return {ln.split("\t")[0] for ln in DEBUG_KNOWN.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")}


def debug_now(track) -> set[str]:
    out: set[str] = set()
    for r in DEBUG_RELS:
        out |= set(residual(r, track))
    return out


RAW_KNOWN = common.GAME_DIR / "data" / "jp_raw_runs.tsv"
RAW_RUN = re.compile(
    rb"(?:[\x82\x83\x88-\x9f\xe0-\xe9][\x40-\xfc]){4,}"
)  # SJIS 두 바이트 글자 4자↑ 연속(3자는 글리프 표 바이트가 우연히 걸린다)
RAW_WINDOW = (
    0xA000  # CPU 창(`$4000~$DFFF`)에 올라오는 앞 40KB — 코드·스크립트 자리(뒤는 그림·소리 자료)
)


def raw_runs(pkg: bytes) -> int:
    """패키지 앞 창 안의 **일본어(가나 포함) SJIS 런** 수 — 메시지 표가 없는 평문 스크립트·라벨이 롬에 얼마나 남았나(10-24 章間 번역 때 넓힘).
    번역한 패키지는 이 수가 줄고, 안 건드린 패키지는 같아야 한다. 새 일본어 런이 생기면 실패(알려진 수 `data/jp_raw_runs.tsv` — 수만 두고 원문은 없다)."""
    n = 0
    buf = bytearray(pkg[:RAW_WINDOW])
    try:  # 메시지 덩이는 LZ 압축 열이다 — 안의 바이트가 우연히 SJIS 가나 꼴로 읽혀도 일본어 평문이 아니다(11-09 한글 문안이 바뀔 때마다 패키지 5 에서 있다 없다 한 오탐). 덩이 구간은 0 으로 지우고 센다
        t, tab = package.msg_table(pkg)  # 메시지 표(포인터 2바이트씩)도 우연히 가나 꼴일 수 있다 — 표부터 첫 덩이 앞까지 지운다
        first = min(p for p in tab if p > t)
        buf[t : min(first, RAW_WINDOW)] = bytes(max(0, min(first, RAW_WINDOW) - t))
        for a, b in package.chunks(pkg):
            if pkg[a : a + 8] != package.SENTINEL and a < RAW_WINDOW:
                buf[a : min(b, RAW_WINDOW)] = bytes(min(b, RAW_WINDOW) - a)
    except Exception:  # 메시지 표가 없는 패키지(A형·자료형)는 지우지 않는다
        pass
    for m in RAW_RUN.finditer(bytes(buf)):
        try:
            t = m.group().decode("cp932")
        except UnicodeDecodeError:
            continue
        if re.search(r"[ぁ-んァ-ヶ]", t):
            n += 1
    return n


def raw_known() -> dict[int, int]:
    out = {}
    if RAW_KNOWN.exists():
        for ln in RAW_KNOWN.read_text(encoding="utf-8").splitlines():
            if ln and not ln.startswith("#"):
                k, v = ln.split("\t")[:2]
                out[int(k)] = int(v)
    return out


def raw_reason() -> dict[int, str]:
    """알려진 수 파일의 셋째 열 — 그 런이 화면 글자가 아니라고 판정한 사유(`--freeze` 가 보존한다)."""
    out = {}
    if RAW_KNOWN.exists():
        for ln in RAW_KNOWN.read_text(encoding="utf-8").splitlines():
            f = ln.split("\t")
            if ln and not ln.startswith("#") and len(f) >= 3:
                out[int(f[0])] = f[2]
    return out


def raw_now(track) -> dict[int, int]:
    return {n: raw_runs(track(258 + 128 * n)) for n in RAW_PKGS}


def known() -> dict[str, str]:
    out = {}
    if KNOWN.exists():
        for ln in KNOWN.read_text(encoding="utf-8").splitlines():
            if ln and not ln.startswith("#"):
                k, c = ln.split("\t")[:2]
                out[k] = c
    return out


def evaluate(iso: Path) -> tuple[list[str], dict[str, str]]:
    """(오류 목록, 지금의 본편 잔존 {열쇠: 분류}) — 빌드가 끝에서 부른다(`build.py`)."""
    track = _built(iso)
    book = sorted((r - 2) // 128 for r in package.CLEAN)
    errs = []
    excluded = BATTLE_TEST | UNDECIDED | NOT_ED2
    for n in range(1, 128):  # 분모 — 장면 꼴 패키지 전부가 본편이거나 제외 목록에 있어야 한다
        if scene_like(n * 128 + 2) and n not in book and n not in excluded:
            errs.append(
                f"패키지 {n}: 장면 꼴인데 본편(package.CLEAN)에도 제외 목록에도 없다 — 번역 대상인지 판정해 한쪽에 넣는다"
            )
    for n in sorted(excluded & set(book)):
        errs.append(f"패키지 {n}: 본편이면서 제외 목록에도 있다")
    now = {}
    for r in package.CLEAN:
        now.update(residual(r, track))
        left = code_jp(track(r))
        if left:
            errs.append(
                f"패키지 {r}: 코드 영역에 일본어 문장 {len(left)}곳 {[hex(o) for o in left[:4]]} — `codestr.py` 에 넣어 한국어로 옮긴다"
            )
    kn = known()
    key = lambda s: tuple(int(x) for x in s.split(":"))  # noqa: E731
    new = sorted(set(now) - set(kn), key=key)
    stale = sorted(set(kn) - set(now), key=key)
    if new:
        errs.append(
            f"알려진 목록 밖 잔존 {len(new)}줄 — 예: {new[:6]} (번역하거나, 근거가 있으면 분류를 정해 목록에 넣는다)"
        )
    if stale:
        errs.append(
            f"알려진 목록의 낡은 열쇠 {len(stale)}줄(이제 번역됨) — `--freeze` 로 내린다: {stale[:6]}"
        )
    dk, dn = debug_known(), debug_now(track)
    key2 = lambda s: tuple(int(x) for x in s.split(":"))  # noqa: E731
    if dn - dk:
        errs.append(f"디버그로 닿는 패키지(258·배틀 테스트)에 알려진 목록 밖 일본어 잔존 {len(dn - dk)}줄 — 예: {sorted(dn - dk, key=key2)[:6]}")
    if dk - dn:
        errs.append(f"디버그로 닿는 패키지 알려진 잔존 {len(dk - dn)}줄이 이제 번역됨 — `--freeze` 로 내린다")
    rk, rn = raw_known(), raw_now(track)
    for n in RAW_PKGS:
        if rn[n] > rk.get(n, 0):
            errs.append(
                f"패키지 {n}: 평문 일본어 런 {rn[n]}개(알려진 {rk.get(n, 0)}) — 새로 생겼다. 번역·후킹 대상인지 판정한다"
            )
        elif rn[n] < rk.get(n, 0):  # 줄어든 건 경고만 — 압축 열·자료 속 바이트의 우연 일치(11-09 한글 문안이 바뀔 때마다 있다 없다 함)라 래칫을 오탐으로 흔들지 않는다. 내리려면 `--freeze`
            print(f"  ⚠ 패키지 {n}: 평문 일본어 런이 {rk[n]}→{rn[n]} 로 줄었다 — `--freeze` 로 내리면 래칫이 조여진다")
    return errs, now


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    iso = Path(args[0]) if args else common.BUILD_DIR / common.BUILD_TAG / "ed2.iso"
    errs, now = evaluate(iso)
    if "--freeze" in sys.argv:
        bad = {k: c for k, c in now.items() if c != "행동"}
        if bad:
            print(
                f"동결 거부 — 행동 문장 밖 잔존 {len(bad)}줄(번역하거나 근거를 달아 분류를 넓힌다): {sorted(bad)[:8]}"
            )
            return 1
        lines = [
            "# 롬에 원본 일본어가 그대로 남은 줄(본편 13개) — `rel:메시지번호:줄 <TAB> 분류`. 원문 없음. 줄어들면 `residual_gate.py --freeze` 로 내린다."
        ]
        lines += [
            f"{k}\t{now[k]}" for k in sorted(now, key=lambda s: tuple(int(x) for x in s.split(":")))
        ]
        KNOWN.write_text("\n".join(lines) + "\n", encoding="utf-8")
        DEBUG_KNOWN.write_text(
            "# 디버그로 닿는 패키지(258 · 배틀 테스트 16~19·28·29)에 원본 일본어가 그대로 남은 줄 — `rel:메시지:줄`. 원문 없음. 줄어들면 `residual_gate.py --freeze` 로 내린다.\n"
            + "".join(f"{k}\n" for k in sorted(debug_now(_built(iso)), key=lambda s: tuple(int(x) for x in s.split(":")))),
            encoding="utf-8",
        )
        rn, rs = raw_now(_built(iso)), raw_reason()
        RAW_KNOWN.write_text(
            "# 평문 일본어(SJIS 가나 포함 4자↑) 런 수 — 패키지 1~127 의 앞 40KB. 원문 없음. 줄어들면 `residual_gate.py --freeze` 로 내린다.\n"
            + "".join(
                f"{n}\t{c}\t{rs.get(n, '11-06 확대 기준선 — 런 주변이 타일·표 바이트, 화면 글자 호출 미확인')}\n"
                for n, c in sorted(rn.items())
                if c
            ),
            encoding="utf-8",
        )
        print(f"{len(now)}줄 → {KNOWN.relative_to(common.ROOT)}")
        return 0
    if errs:
        print("\n".join("✖ " + e for e in errs))
        return 1
    by: dict[str, int] = {}
    for c in now.values():
        by[c] = by.get(c, 0) + 1
    print(
        f"잔존 게이트 OK — 본편 {len(package.CLEAN)}개 패키지 · 알려진 잔존 {len(now)}줄 {by} · 본편 밖 {len(BATTLE_TEST | UNDECIDED | NOT_ED2)}개(배틀 테스트 {len(BATTLE_TEST)} · 판정 불가 {len(UNDECIDED)} · 다른 타이틀 잔재 {len(NOT_ED2)})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
