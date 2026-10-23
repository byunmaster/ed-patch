#!/usr/bin/env python3
"""**재배치 장부** — 빌드가 실제로 한 재배치(블록 옮김 · 쪽 넘김 · 채움 · 스텁/훅 · 파일 확장/이동)를 전부 `relocations.tsv` 에 남긴다(마스터 10-22
「재배치를 진행한 부분들도 별도로 기록해두자. 정 안되면 나중에 되돌려야할수도 있으니」).

    python3 tools/relocations.py --write     # 빌드 이미지 · 쓰기 장부에서 **자동으로** 뽑아 games/ss-ed1+2/relocations.tsv 를 쓴다(손으로 안 쓴다)
    python3 tools/relocations.py --check     # 빌드가 한 재배치가 커밋된 장부에 **전부** 있나(없으면 실패) — 구조 대조(`check_structure`)의 허용 목록과 같은 출처

- 원문 바이트·문장은 안 넣는다 — 좌표 · 종류 · 사유 · 엔진 근거 · 되돌리면 생기는 일만.
- 열: `블록 키 · 종류 · 원래 좌표 · 새 좌표 · 사유 · 엔진 근거 · 되돌리면`.
  키 = `<파일>#<엔트리 번호>`(`ED1SCN08#170` — 덤프 엔트리 번호) · 조각이 아닌 묶음 행은 `<파일>#*` 또는 `<도구>:<파일>@<오프셋>`.
- 종류 — `옮김`(블록을 풀로 옮기고 포인터를 돌림) · `쪽 넘김`(창 끝 0x08 추가) · `채움`(원문보다 짧아져 남은 칸 0 채움 — 파일별 묶음) ·
  `스텁`(코드·포인터를 돌리는 훅) · `확장`(파일 꼬리 섹터를 자리로) · `파일 이동`(LBA 이동).
- 되돌리기: **`옮김` 만** 스위치가 있다 — `script/relocation_off.txt` 에 블록 키를 한 줄씩 적으면(또는 환경변수 `ED_RELOC_OFF=<목록 파일>`)
  `patch_scn` 이 그 블록을 **옮기지 않는다**: 제자리 칸에 맞으면 제자리에 넣고, 안 맞으면 번역을 못 넣어(원문 일본어로 남음) 잔존 게이트가 울린다.
  나머지 종류는 「되돌리기 수단 없음」으로 적는다(이유는 행에).
- 게이트: 빌드에서 뽑은 `옮김`·`쪽 넘김`·`스텁`·`확장`·`파일 이동` 키가 장부에 없으면 실패 — 장부에만 있고 빌드엔 없는 키는 낡은 행(경고, `--write` 가 지운다).
  좌표는 마지막 `--write` 시점 값이다(문안이 바뀌면 달라진다 — 갈 때마다 `--write` 하고 diff 를 본다).
"""

import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import check_structure as S

HEAD = ["블록 키", "종류", "원래 좌표", "새 좌표", "사유", "엔진 근거", "되돌리면"]
TSV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "relocations.tsv")

EV_MOVE = (
    "문자열은 코드 리터럴 풀의 BE32 포인터로만 집힌다 — 번호→스크립트 함수가 포인터 목표를 NUL 까지 sprintf(ED2 0x0607B180 · ED1 0x06095BCC)로 "
    "버퍼에 담는다(`ss_scene_sweep.py` 구조 절) · 짝수 주소(`patch_scn._place`) · 비운 칸 꼬리의 0x09 는 무죄(실기, devlog 2026-09-04)"
)
EV_PAGE = (
    "버퍼 규약 08=창 끝(뒤에 02 가 오면 다음 창) — 창 열기 ED2 0x0605AA94 · 번호→창 ED2 0x06054AF8 / ED1 0x06040538 · "
    "실측: 씬 34 번호 43 에 08 을 넣자 쪽이 하나 늘었다(`patch_scn.page_split` 주석) · 구조 계약 ①②(`%c·%s·%d` 열)는 그대로"
)
EV_FILL = "NUL 이후는 엔진이 안 읽는다(포인터 목표 → NUL 까지 읽기) · 칸 꼬리 `NUL + 0 채움 + 0x09` 는 원본 꼬리 그대로(`patch_scn.rebuild` 주석)"
EV_FILE = {
    "patch_josa_hook.py": "문자열 그리기 0x0607D504 를 `jsr` 하는 리터럴 풀 6곳의 포인터를 우리 루틴으로 돌림(원 명령 불변) · r6≥IMAGE_END 일 때만 동작(docstring)",
    "patch_msgwrap.py": "prewrap(ED 0x0607CE74 · ED2 0x06064268) 본체를 어절 단위 루틴으로 덮어씀 — 556B 잎 함수 자리 그대로(docstring)",
    "patch_msgcopy.py": "전투 문구 memcpy 길이 상수 `mov #N,r6`(ED 0x0605BA00~0x0605C3B0 한 함수 · 75 갈래)를 우리 길이로 늘림(docstring)",
    "patch_namecopy.py": "이름 고정 폭 복사(언롤 `mov.b`)를 NUL 종단 루프로 교체 — 목적지 0x0609F561(docstring)",
    "patch_scn.py": "주입 `%c` 쌍의 인자 워드를 공백으로(`inject_pairs`) — 콜사이트 인자 2B",
    "expand_files.py": "파일 꼬리 섹터 = 게임이 안 읽던 영역, ISO 크기 필드만 늘림(LBA 불변) · 적재 뒤 메모리 충돌은 코드로 검산(docstring 안전 조건)",
    "relocate_files.py": "데이터 트랙 꼬리 여유로 씬 파일을 뒤로 밀고 디렉터리 LBA·크기 갱신 · 오디오 트랙 불변(docstring)",
}
REVERT = {
    "옮김": "스위치 있음 — script/relocation_off.txt 에 이 키를 적으면 옮기지 않는다(제자리에 맞으면 제자리 · 안 맞으면 번역을 못 넣어 일본어로 남는다)",
    "인수": "스위치 있음 — 이 블록의 키를 relocation_off.txt 에 적으면 늘리지 않는다(원문 칸에 안 맞아 번역을 못 넣는다). 이웃 블록이 이주해 비운 칸을 이어 쓴 것",
    "쪽 넘김": "되돌리기 수단 없음 — 쪽 가르기 표(script/key_cont.json pages)·auto_split 이 만든 것이라 개별 스위치가 없다. 되돌리면 6째 행이 ▽ 와 겹친다",
    "채움": "되돌릴 것 없음 — 원문보다 짧아진 칸을 0 으로 채운 것(문안이 곧 원인)",
    "스텁": "되돌리기 수단 없음 — 해당 패처 단계를 빼면 훅이 사라지지만 그 패처의 문안 계약(병기·고정 폭 복사)이 같이 깨진다",
    "확장": "되돌리기 수단 없음 — 꼬리 섹터 이주 풀이 사라져 이주 블록을 못 놓는다",
    "파일 이동": "되돌리기 수단 없음 — LBA 가 바뀐 뒤 단계(patch_scn)가 새 LBA 를 읽는다",
}


# 행에는 짧은 코드만 넣고 문장은 TSV 머리의 `#` 범례에 한 번만 둔다(12,359행 × 긴 문장 = 8.7MB 였다)
LEGEND = {}
for _k, _v in (("E-MOVE", EV_MOVE), ("E-PAGE", EV_PAGE), ("E-FILL", EV_FILL)):
    LEGEND[_k] = _v
for _t, _v in EV_FILE.items():
    LEGEND["E-" + _t[:-3].upper().replace("_", "-")] = _v
LEGEND["N-MOVE"] = (
    "옮김 사유 — 칸 넘침 = 새 문안이 원문 칸보다 길다 · 구간 재깔기 = 같은 구간의 이웃이 넘쳐 구간 전체를 다시 깔았다(`patch_scn._needs_pack`). "
    "새 좌표 — 확장 영역 = 원본 파일 끝 뒤(꼬리 섹터) · 원 글 구간 안 = 비운 칸·짧아진 칸 뒤"
)
_RCODE = {"옮김": "R-SWITCH", "쪽 넘김": "R-NONE-PAGE", "채움": "R-NA-FILL", "인수": "R-SWITCH", "스텁": "R-NONE-STUB", "확장": "R-NONE-EXPAND", "파일 이동": "R-NONE-LBA"}
for _k, _v in REVERT.items():
    LEGEND[_RCODE[_k]] = _v


def _ev(tool):
    return "E-" + tool[:-3].upper().replace("_", "-")


def _name(path):
    """`/BIN/ED1SCN08.BIN` → `ED1SCN08` · `/ED2.BIN` → `ED2`."""
    return os.path.basename(path)[:-4]


def _key(path, key):
    return f"{_name(path)}{key}"


def _hx(v):
    return f"0x{v:X}"


def _scan_all():
    """빌드 이미지·원본·덤프에서 파일별 `(이주, 쪽 넘김, 통계)` — 구조 대조와 같은 판정."""
    import common
    import patch_scn as P

    dst = os.path.join(common.BUILD_DIR, os.path.basename(common.ORIG_BIN))
    fo, mo = common.open_image(common.ORIG_BIN)
    fb, mb = common.open_image(dst)
    orig = {n: (lba, s) for n, lba, s in common.iso_files(mo)}
    out = []
    for name, lba, size in common.iso_files(mb):
        if name not in orig or size > 3_000_000 or not P.SCN_RE.match(name):
            continue
        got = P.load(name)
        if not got:
            continue
        base, entries = got
        o = common.read_extent(mo, *orig[name])
        b = common.read_extent(mb, lba, size)
        st, bad, moved, pages = S.scan_file(o, b, base, entries, None)
        out.append((name, len(o), st, moved, pages, entries, base, o, b))
    return out


def _ledger_rows():
    import common

    rows = []
    try:
        with open(common.LEDGER, encoding="utf-8") as lf:
            for ln in lf:
                r = json.loads(ln)
                if r.get("o") is not None:
                    rows.append(r)
    except FileNotFoundError:
        pass
    return rows


def build_rows():
    """빌드에서 장부 행 전량을 **자동으로** 뽑는다 → `[행 7열]`(정렬됨)."""
    rows = []
    scans = _scan_all()
    for name, osize, st, moved, pages, entries, base, o, b in scans:
        for key, off, t, n, new_n in moved:
            why = f"칸 넘침 {new_n}B>{n}B" if new_n > n else f"구간 재깔기 {new_n}B≤{n}B"
            where = "확장 영역" if t >= osize else "원 글 구간 안"
            ptrs = next((len(e.get("ptr_at", [])) for e in entries if f"#{e['entry_id']}" == key), 0)
            rows.append([_key(name, key), "옮김", _hx(off), _hx(t), f"{why}; {where}; 포인터 {ptrs}곳", "E-MOVE", _RCODE["옮김"]])
        for key, off, n, new_n in st.get("_인수", []):
            rows.append([_key(name, key), "인수", _hx(off), _hx(off), f"제자리 {new_n}B>{n}B — 이주한 이웃 칸을 이어 씀(구간 재깔기)", "E-MOVE", _RCODE["인수"]])
        for key, off, t, dp in pages:
            rows.append([_key(name, key), "쪽 넘김", _hx(off), _hx(t), f"창 5행 한도 초과로 창 끝(08) {dp}개 추가", "E-PAGE", _RCODE["쪽 넘김"]])
        if st.get("채움 블록"):
            rows.append(
                [f"{_name(name)}#*", "채움", "-", "-", f"제자리 {st['채움 블록']}블록 뒤 0 채움 {st['채움 바이트']}B(원문보다 짧아진 만큼)", "E-FILL", _RCODE["채움"]]
            )
    # 스텁·확장·파일 이동 — 쓰기 장부(도구 · 파일 오프셋 · 라벨)에서
    seen = set()
    for r in _ledger_rows():
        tool, label = r["t"], r["l"]
        if tool in ("patch_josa_hook.py", "patch_msgwrap.py", "patch_msgcopy.py", "patch_namecopy.py") or (tool == "patch_scn.py" and "주입 인자" in label):
            f = label.split(" ")[0]
            key = f"{tool[:-3]}:{_name(f) if f.startswith('/') else f}@{_hx(r['o'])}"
            kind = "스텁"
        elif tool == "expand_files.py":
            f = label.split(" ")[0]
            key, kind = f"expand_files:{_name(f)}", "확장"
        elif tool == "relocate_files.py":
            f = label.split(" ")[0]
            key, kind = f"relocate_files:{_name(f)}", "파일 이동"
        else:
            continue
        if kind in ("확장", "파일 이동") and key in seen:
            continue
        seen.add(key)
        rows.append([key, kind, _hx(r["o"]), _hx(r["o"]), f"{label[len(label.split(' ')[0]) + 1:]} ({r['n']}B)", _ev(tool), _RCODE[kind]])
    rows.sort(key=lambda x: (x[1], x[0], x[2]))
    return rows


def read_committed():
    if not os.path.exists(TSV):
        return []
    with open(TSV, encoding="utf-8") as f:
        lines = f.read().split("\n")
    return [ln.split("\t") for ln in lines if ln and not ln.startswith("#") and not ln.startswith(HEAD[0])]


def allowed_moves():
    """커밋된 장부의 `옮김` 행 → `{(파일 경로, '#번호')}` — 구조 대조(`check_structure`)의 허용 목록."""
    out = set()
    for r in read_committed():
        if len(r) >= 2 and r[1] == "옮김":
            nm, _, num = r[0].partition("#")
            path = f"/BIN/{nm}.BIN" if nm.startswith(("ED1SCN", "ED2SCN", "ED2MON")) else f"/{nm}.BIN"
            out.add((path, f"#{num}"))
    return out


LEDGER_KINDS = ("스텁", "확장", "파일 이동")


def write():
    rows = build_rows()
    # 🔴 스텁·확장·파일 이동은 **쓰기 장부**에서 뽑는데, 증분 빌드(앞 회차 이미지 사본 위에서 바뀐 토막만 쓴다)에선 이번에 안 쓴 행이 빠진다(실측: 같은 코드로 117 → 99행).
    #    그래서 이 세 종류는 **기존 장부 행을 지우지 않고 합친다**(깨끗한 빌드에서만 새로 완성된다 — `ED_CLEAN` 없이 지우려면 파일을 지우고 `--write`).
    have = {(r[0], r[1]) for r in rows}
    for r in read_committed():
        if r[1] in LEDGER_KINDS and (r[0], r[1]) not in have:
            rows.append(r)
    rows.sort(key=lambda x: (x[1], x[0], x[2]))
    with open(TSV, "w", encoding="utf-8") as f:
        for k, v in sorted(LEGEND.items()):
            f.write(f"# {k}: {v}\n")
        f.write("\t".join(HEAD) + "\n")
        for r in rows:
            f.write("\t".join(x.replace("\t", " ").replace("\n", " ") for x in r) + "\n")
    cnt = {}
    for r in rows:
        cnt[r[1]] = cnt.get(r[1], 0) + 1
    print(f"재배치 장부 {len(rows):,}행 → {os.path.relpath(TSV)} · " + " · ".join(f"{k} {v:,}" for k, v in cnt.items()))


def check():
    now = build_rows()
    have = {(r[0], r[1]) for r in read_committed()}
    nowk = {(r[0], r[1]) for r in now}
    missing = sorted(nowk - have)
    stale = sorted(k for k in have - nowk if k[1] not in LEDGER_KINDS)
    cnt = {}
    for r in now:
        cnt[r[1]] = cnt.get(r[1], 0) + 1
    mark = "✅" if not missing else "🔴"
    print(
        f"  {mark} 재배치 장부 — 빌드의 재배치 {len(now):,}행(" + " · ".join(f"{k} {v:,}" for k, v in cnt.items()) + f") · 장부에 없음 {len(missing)} · 낡은 행 {len(stale)}"
    )
    for k, kind in missing[:15]:
        print(f"    ❌ 장부에 없는 재배치 [{kind}] {k}")
    if missing:
        print("    → `python3 tools/relocations.py --write` 로 장부를 갱신하고 diff 를 본다(의도한 재배치인지)")
    return 1 if missing else 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        write()
    else:
        sys.exit(check())
