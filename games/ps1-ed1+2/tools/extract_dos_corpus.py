#!/usr/bin/env python3
"""정발(만트라 DOS) 한글 문자열 대사집 — 원본 전 파일을 CP949 한글 런으로 훑는다.
사용: python3 games/ps1-ed1+2/tools/extract_dos_corpus.py   → 메인 트리 .local/work/jeongbal/<ed1|ed2>/dos/{corpus.tsv,MANIFEST.json,README.md}
corpus.tsv 열: 파일(상대경로) · 자리(0x오프셋) · 문장(런, 제어코드 자리에서 끊김) · 신뢰(T 신뢰 출처 / N 노이즈 — 그림·글꼴·런타임 DLL 속 우연한 한글 바이트열)
산출물은 정발 문안이라 커밋 금지(.local 은 git 이 모른다). 이 도구만 커밋한다.
"""
import hashlib, json, os, re, sys
import subprocess
_COMMON = subprocess.run(["git", "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                         cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
HERE = os.path.join(os.path.dirname(os.path.abspath(_COMMON)), ".local", "work", "jeongbal")
ORIG = os.environ.get("ORIG_KR", os.path.join(os.path.dirname(os.path.abspath(_COMMON)), "originals", "kr"))
# 신뢰 출처 — 대사·이름 문안이 실제로 든 파일. 나머지(그림·글꼴·BGI/DPMI/RTM·세팅)는 노이즈 표시.
TRUST = {"SINDLL", "MONDLL", "SCENA", "MON", "MONHEAD.DAT", "ED1MAIN.EXE", "ED2MAIN.EXE", "OPEN.EXE",
         "OPENING.EXE", "ENDING.EXE", "ENDING.DLL", "DATA", "ENDING", "OPENING"}
SKIP_EXT = {".FNT": "글꼴", ".BGX": "그림", ".BGI": "그림 드라이버", ".B1": "그림", ".G1": "그림", ".R1": "그림",
            ".400": "그림", ".PCX": "그림", ".MID": "음악", ".MDI": "음악", ".VOC": "소리", ".WAV": "소리"}
SKIP_PREFIX = ("SAVEDATA",)
SKIP_DIR = {"CD": "ED2 CD 사본 디렉터리(중복)", "BGM": "음악", "SOUND": "소리"}
pat = re.compile(rb"(?:[\xb0-\xc8][\xa1-\xfe])(?:[\xb0-\xc8][\xa1-\xfe]| (?=[\xb0-\xc8])|[0-9a-zA-Z.,!?~'\-](?=[\xb0-\xc8][\xa1-\xfe]))*")
def main():
    for key, g in (("ed1", "dos-ed1"), ("ed2", "dos-ed2")):
        root = os.path.join(ORIG, g)
        out = os.path.join(HERE, key, "dos"); os.makedirs(out, exist_ok=True)
        rows, man = [], {"game": g, "read": {}, "skipped": {}}
        for dp, _, fs in sorted(os.walk(root)):
            for f in sorted(fs):
                p = os.path.join(dp, f); rel = os.path.relpath(p, root)
                top = rel.split(os.sep)[0]; ext = os.path.splitext(f)[1].upper()
                why = SKIP_DIR.get(top) if os.sep in rel else None
                why = why or SKIP_EXT.get(ext) or ("세이브" if f.upper().startswith(SKIP_PREFIX) else None)
                if why:
                    man["skipped"][rel] = why; continue
                b = open(p, "rb").read(); n = 0; chars = 0
                for m in pat.finditer(b):
                    try: s = m.group().decode("cp949")
                    except UnicodeDecodeError: continue
                    rows.append((rel, hex(m.start()), s, "T" if (top in TRUST or rel in TRUST) else "N")); n += 1; chars += len(s)
                man["read"][rel] = {"sha1": hashlib.sha1(b).hexdigest(), "runs": n, "chars": chars, "trust": "T" if (top in TRUST or rel in TRUST) else "N"}
        with open(os.path.join(out, "corpus.tsv"), "w", encoding="utf-8") as fo:
            for r in rows: fo.write("\t".join(r) + "\n")
        man["total_runs"] = len(rows); man["total_chars"] = sum(len(r[2]) for r in rows)
        json.dump(man, open(os.path.join(out, "MANIFEST.json"), "w"), ensure_ascii=False, indent=1)
        open(os.path.join(out, "README.md"), "w").write(
            f"# 정발 {key.upper()} 대사집\n\n다시 뽑기: `python3 games/ps1-ed1+2/tools/extract_dos_corpus.py` (원본 `originals/kr/{g}`).\n"
            "열: 파일 · 자리 · 문장 · 신뢰(T/N). 한글 런 단위(제어코드에서 끊김)라 한 대사가 여러 줄일 수 있다. "
            "못 읽은 파일과 이유는 MANIFEST.json 의 skipped. **그림·글꼴 안의 우연한 한글 바이트열은 노이즈**일 수 있다 — "
            "신뢰 T = SINDLL·MONDLL·SCENA·MON·MONHEAD.DAT·게임 본체 EXE 등, N = 노이즈(MANIFEST 파일 단위 표시). 커밋 금지.\n")
        print(key, len(rows), "runs", len(man["read"]), "files read", len(man["skipped"]), "skipped")


if __name__ == "__main__":
    main()
