"""소장 공략집에서 **텍스트만** 뽑아 낱말 코퍼스를 만든다 — 표기 판정의 보조 근거.

    python3 games/ss-ed3/tools/guide_text.py        # work/review/guide_ed3.txt

🔴 **문장을 쓰려는 게 아니다.** 고유명사 **표기**를 확인할 낱말 코퍼스가 필요할 뿐이고,
   `glossary_probe` 는 「그 표기가 몇 번 쓰였나」만 센다. 산출물은 `work/review`(gitignore)에
   두고 커밋하지 않는다 — 공략집은 저작물이다.

⚠ 자료는 `.local/guide/`(머신 전용, 소장자 제공)에 있다. **없으면 조용히 건너뛴다** —
   다른 머신·CI 에서도 도구가 돌아야 한다.
⚠ 파일명이 **NFD 정규화**로 저장돼 있어 셸 글롭이 안 맞는다. 파이썬에서 NFC 로 맞춰 찾는다.
"""

import os
import re
import sys
import unicodedata
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C


def _main_tree():
    """워크트리에서도 **메인 트리**를 찾는다 — `.local` 은 거기 하나뿐이다.

    `.local` 은 머신 전용이라 워크트리마다 복제할 이유가 없다(용량도 크다). 워크트리의
    `.git` 은 파일이고 그 안에 `gitdir:` 이 적혀 있으니, 공통 git 디렉터리의 부모가
    메인 트리다.
    """
    g = os.path.join(C.ROOT, ".git")
    if os.path.isdir(g):
        return C.ROOT
    try:
        with open(g, encoding="utf-8") as f:
            gitdir = f.read().split("gitdir:", 1)[1].strip()
    except (OSError, IndexError):
        return C.ROOT
    # <메인>/.git/worktrees/<이름> → <메인>
    parts = os.path.abspath(os.path.join(C.ROOT, gitdir)).split(os.sep)
    if "worktrees" in parts:
        i = parts.index("worktrees")
        return os.sep.join(parts[: i - 1])
    return C.ROOT


GUIDE_DIR = os.path.join(_main_tree(), ".local", "guide")
OUT = os.path.join(C.REVIEW_DIR, "guide_ed3.txt")
WANT = "영웅전설 3"


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def find(kind=".hwp"):
    """`.local/guide` 에서 ED3 자료 경로 — 없으면 빈 목록."""
    if not os.path.isdir(GUIDE_DIR):
        return []
    out = []
    for e in sorted(os.scandir(GUIDE_DIR), key=lambda x: x.name):
        n = _nfc(e.name)
        if WANT in n and n.lower().endswith(kind):
            out.append(e.path)
    return out


def hwp_text(path):
    """HWP 5.0(CFB + zlib) 본문 → 문자열. 실패하면 빈 문자열."""
    try:
        import olefile
    except ImportError:
        return ""
    with olefile.OleFileIO(path) as o:
        secs = ["/".join(s) for s in o.listdir() if s[0] == "BodyText"]
        buf = bytearray()
        for s in secs:
            d = o.openstream(s).read()
            try:
                d = zlib.decompress(d, -15)  # 헤더의 압축 플래그가 켜져 있다
            except zlib.error:
                pass
            buf += d
    # ⚠ 레코드 구조를 다 풀지 않는다 — 표기만 필요하므로 **UTF-16LE 한글 런**만 건진다.
    s = buf.decode("utf-16-le", "ignore")
    return "\n".join(re.findall(r"[가-힣][가-힣0-9 ·\-~!?.,'\"()]{1,80}", s))


def main():
    paths = find(".hwp")
    if not paths:
        print(f"⏭ 공략 자료가 없다 — {GUIDE_DIR} (머신 전용, 없어도 된다)")
        return
    os.makedirs(C.REVIEW_DIR, exist_ok=True)
    total = 0
    with open(OUT, "w", encoding="utf-8") as f:
        for p in paths:
            t = hwp_text(p)
            total += len(t)
            f.write(f"# {_nfc(os.path.basename(p))}\n{t}\n")
            print(f"  {_nfc(os.path.basename(p)):<40}{len(t):>9,}자")
    print(f"\n{total:,}자 → {OUT}  (⚠ 커밋 금지)")


if __name__ == "__main__":
    main()
