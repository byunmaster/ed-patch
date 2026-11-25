"""정발(만트라 DOS · 윈도) 게임 문안 **대사집 추출** — 이후 표기 대조는 이 대사집을 읽는다(마스터 10-25).

    python3 tools/jeongbal_extract.py                # 다섯 판본 전부 (ed3 dos·win / ed4 dos·win / ed5 win)
    python3 tools/jeongbal_extract.py ed3/win        # 하나만
    python3 tools/jeongbal_extract.py --out <폴더>   # 기본: 메인 트리 .local/work/jeongbal

산출 `<out>/<작품>/<판본>/` 에 `corpus.tsv`(파일 · 멤버 · 오프셋(해제 후) · 품질 · 문장) · `MANIFEST.json` · `README.md`.

🔴 **산출물은 원저작물이다 — 커밋 금지**(`.local/` 아래라 git 이 모른다). 이 도구만 커밋된다.

두 컨테이너를 푼다:
- **윈도** `LB DAT\\x1a\\0` — u32 개수 · u32(0) · u32 절대 오프셋 표(개수+1). 멤버는 압축 청크 열이라
  EXE 의 해제 루틴을 unicorn 으로 돌려 푼다(`win_lb.py` — ED3 EXE 의 루틴이 ED4·ED5 데이터도 푼다, 실측).
- **DOS** `AFLB DAT\\x1a\\0` — u16 개수 · u32(0) · u16 오프셋 표(개수+1) **× 32 바이트 = 파일 오프셋**
  (ED3 DT06: 마지막 항목 27234 × 32 = 871,488 = 파일 크기). 멤버는 날것이거나 같은 LZ 압축이다.

푼 결과가 멤버 길이를 **정확히 다 소비**해야 압축으로 인정한다(날것에 해제기를 돌리면 우연히 풀리는 일이 있다).
못 풀면 날것을 그대로 훑고 MANIFEST 에 센다 — **조용히 빠지지 않는다**.

문장 = cp949 한글 런(공백·`!,.?`·숫자·`~` 허용, 한글 음절 2자 이상). 품질: A = 흔한 음절 비율 높음(대사·이름),
B = 그림·표 이진에서 우연히 걸린 잡음일 가능성이 큼.
"""

import argparse
import collections
import glob
import hashlib
import json
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common
import win_lb

# 판본 → (루트, 해제기 EXE 루트). ED5 는 repo originals/kr 에 없어 소장 컬렉션에서 직접 읽는다.
EDITIONS = {
    "ed3/dos": ("originals/kr/dos-ed3", "dos"),
    "ed3/win": ("originals/kr/win-ed3", "win"),
    "ed4/dos": ("originals/kr/dos-ed4", "dos"),
    "ed4/win": ("originals/kr/win-ed4", "win"),
    "ed5/win": ("/mnt/originals/WIN/ED5", "win"),
}
UNPACKER_EXE = "originals/kr/win-ed3/ED3_WIN.EXE"  # 이 루틴이 세 작품의 데이터를 푼다
SKIP = (
    ".wav",
    ".mid",
    ".midi",
    ".bmp",
    ".avi",
    ".mp3",
    ".ogg",
    ".dll",
    ".fon",
    ".fnt",
    ".png",
    ".jpg",
    ".gif",
    ".ico",
)
SKIPDIR = {
    "savedata",
    "save",
    "_backup",
    "_dxwnd",
    "dosbox",
    "doogie",
    "midi",
    "midi_gm",
    "wave",
    "wavedv",
    "bmp",
    "effect",
    "mount",
}
RUN = re.compile(rb"(?:[\xb0-\xc8][\xa1-\xfe]|[\x20\x21\x2c\x2e\x3f\x7e\x30-\x39])+")
PAIR = re.compile(rb"[\xb0-\xc8][\xa1-\xfe]")


def main_tree():
    """메인 트리 루트 — 워크트리엔 `.local/` 을 만들지 않는다(루트 CLAUDE.md)."""
    import subprocess

    d = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=common.REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return os.path.dirname(os.path.abspath(os.path.join(common.REPO, d)))


def scan(buf):
    """[(오프셋, 문장)] — 한글 음절 2자 이상 런."""
    out = []
    for m in RUN.finditer(buf):
        s = m.group()
        # 정렬: 런 안에서 한글 쌍을 앞에서부터 짝짓는다 — 첫 바이트가 trail 이면 한 칸 민다
        i = 0
        n = len(s)
        syl = 0
        while i < n:
            if i + 1 < n and 0xB0 <= s[i] <= 0xC8 and 0xA1 <= s[i + 1] <= 0xFE:
                syl += 1
                i += 2
            else:
                i += 1
        if syl < 2:
            continue
        try:
            t = s.decode("cp949")
        except UnicodeDecodeError:
            t = s.decode("cp949", "ignore")
        t = t.strip()
        if sum("가" <= c <= "힣" for c in t) >= 2:
            out.append((m.start(), t))
    return out


def members_win(b):
    n = struct.unpack_from("<I", b, 8)[0]
    offs = struct.unpack_from(f"<{n + 1}I", b, 16)
    return [(offs[i], offs[i + 1] - offs[i]) for i in range(n) if offs[i + 1] > offs[i]]


def members_dos(b):
    n = struct.unpack_from("<H", b, 10)[0]
    t = struct.unpack_from(f"<{n + 1}H", b, 16)
    out = []
    for i in range(n):
        if t[i + 1] > t[i]:
            out.append((t[i] * 32, (t[i + 1] - t[i]) * 32))
    return out


def extract(ed, root, unpacker, log):
    files = []
    for p in sorted(glob.glob(os.path.join(root, "**", "*"), recursive=True)):
        if os.path.isfile(p):
            files.append(p)
    rows = []
    man = {"files": {}, "unreadable": [], "chars": 0, "sentences": 0}
    for p in files:
        rel = os.path.relpath(p, root)
        if set(rel.lower().split(os.sep)[:-1]) & SKIPDIR:
            man["unreadable"].append(
                {"file": rel, "why": "세이브·백업·에뮬 폴더 — 정발 문안이 아님"}
            )
            continue
        if rel.lower().endswith(SKIP) or os.path.getsize(p) > 64 << 20:
            man["unreadable"].append({"file": rel, "why": "미디어·글꼴·너무 큼 — 훑지 않음"})
            continue
        b = open(p, "rb").read()
        info = {
            "bytes": len(b),
            "kind": "raw",
            "members": 0,
            "unpacked": 0,
            "raw_members": 0,
            "sentences": 0,
        }
        mem = None
        if b[:6] == b"LB DAT":
            info["kind"] = "LB DAT"
            mem = members_win(b)
        elif b[:8] == b"AFLB DAT":
            info["kind"] = "AFLB DAT"
            mem = members_dos(b)
        if mem is None:
            for off, t in scan(b):
                rows.append((rel, "-", off, t))
                info["sentences"] += 1
        else:
            info["members"] = len(mem)
            for k, (o, l) in enumerate(mem):
                chunk = b[o : o + l]
                r = unpacker.unpack(chunk) if l >= 3 else None
                pad = 31 if info["kind"] == "AFLB DAT" else 0
                if r and 0 < r[1] <= l and l - r[1] <= pad and len(r[0]) > 0:
                    data = r[0]
                    info["unpacked"] += 1
                else:
                    data = chunk
                    info["raw_members"] += 1
                for off, t in scan(data):
                    rows.append((rel, k, off, t))
                    info["sentences"] += 1
        man["files"][rel] = info
        man["sentences"] += info["sentences"]
        log(
            f"  {ed} {rel}: {info['kind']} 멤버 {info['members']} (해제 {info['unpacked']} · 날것 {info['raw_members']}) 문장 {info['sentences']}"
        )
    return rows, man


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="*", help="예: ed3/win (생략하면 전부)")
    ap.add_argument("--out", default=os.path.join(main_tree(), ".local", "work", "jeongbal"))
    a = ap.parse_args()
    unpacker = win_lb.Unpacker(win_lb.Exe(os.path.join(common.REPO, UNPACKER_EXE)))
    eds = a.only or list(EDITIONS)
    allrows = {}
    for ed in eds:
        root, _ = EDITIONS[ed]
        root = root if os.path.isabs(root) else os.path.join(common.REPO, root)
        if not os.path.isdir(root):
            print(f"{ed}: 폴더 없음 {root}")
            continue
        print(f"== {ed}")
        rows, man = extract(ed, root, unpacker, print)
        allrows[ed] = (rows, man, root)
    # 품질 — 전 판본 긴 런에서 흔한 음절 700 개
    cnt = collections.Counter()
    for rows, _, _ in allrows.values():
        for _, _, _, t in rows:
            if sum("가" <= c <= "힣" for c in t) >= 8:
                cnt.update(c for c in t if "가" <= c <= "힣")
    common_syl = {c for c, _ in cnt.most_common(700)}
    for ed, (rows, man, root) in allrows.items():
        d = os.path.join(a.out, *ed.split("/"))
        os.makedirs(d, exist_ok=True)
        qa = 0
        chars = 0
        with open(os.path.join(d, "corpus.tsv"), "w", encoding="utf-8") as f:
            f.write("파일\t멤버\t오프셋(해제 후)\t품질\t문장\n")
            for rel, k, off, t in rows:
                syl = [c for c in t if "가" <= c <= "힣"]
                q = "A" if syl and sum(c in common_syl for c in syl) / len(syl) >= 0.7 else "B"
                qa += q == "A"
                chars += len(t)
                f.write(f"{rel}\t{k}\t{off:x}\t{q}\t{t}\n")
        man["chars"] = chars
        man["sentences_quality_A"] = qa
        man["root"] = (
            root if not root.startswith(common.REPO) else os.path.relpath(root, common.REPO)
        )
        man["source_files_sha1"] = {
            rel: hashlib.sha1(open(os.path.join(root, rel), "rb").read()).hexdigest()
            for rel in man["files"]
            if man["files"][rel]["bytes"] < 200 << 20
        }
        json.dump(
            man,
            open(os.path.join(d, "MANIFEST.json"), "w", encoding="utf-8"),
            ensure_ascii=False,
            indent=1,
        )
        open(os.path.join(d, "README.md"), "w", encoding="utf-8").write(
            f"# {ed} 정발 대사집\n\n`python3 games/ps1-ed3/tools/jeongbal_extract.py {ed}` 로 다시 뽑는다(메인 트리 `.local/work/jeongbal`).\n"
            "컨테이너 해제 방법은 도구 머리말. 🔴 원저작물 — 커밋 금지.\n"
            f"문장 {man['sentences']:,} (품질 A {qa:,}) · 글자 {chars:,}.\n"
        )
        print(f"{ed}: 문장 {man['sentences']:,} · A {qa:,} · 글자 {chars:,} → {d}")


if __name__ == "__main__":
    main()
