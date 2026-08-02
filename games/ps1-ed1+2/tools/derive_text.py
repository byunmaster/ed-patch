"""문장급 번역 텍스트 파생 — textmap(커밋) + originals/kr/dos-ed1(소장자 제공) → 번역 테이블.

체계: 저작권 있는 문안(팔콤 일문·만트라 번역문)은 리포에 담지 않는다.
  · 정발(만트라) 문안 → textmap/<class>.json 의 (파일, 오프셋, 길이) 포인터로
    소장 DOS 원본(originals/kr/dos-ed1)에서 빌드 때마다 추출
  · 우리가 쓴 번역(정발에 없는 문장) → textmap에 직접 수록(우리 저작물이라 커밋 OK)
  · 일본어 원문 → 리포 어디에도 없음. JP 키 딕셔너리는 sha1 해시 키 — 소비자가
    PS1 디스크에서 스캔한 JP 문자열을 jkey()로 해싱해 조회한다(patch_items.battle_kr 등)
  · 명칭·라벨(아이템/몬스터/지명/메뉴 등 단어 수준)은 저작권 보호 대상이 아니라
    각 도구에 그대로 둔다 — 파생 대상은 문장급만

클래스: battle(battle_text.B) · items_battle(patch_items.BATTLE) · opening(patch_opening_font.LINES).

textmap 엔트리: {"k": <jp-sha1-10 | 슬롯오프셋 hex>,
                 "src": {"f": 상대경로, "o": 오프셋, "l": 길이, "x": 조판변환 여부} 또는 "ours": <문장>,
                 "sha": <최종 문자열 sha1-8 가드>}
"""

import hashlib
import json
import os
from collections.abc import Mapping

from common import OUT_DIR, ROOT

TEXTMAP_DIR = os.path.join(ROOT, "textmap")
DERIVED_DIR = os.path.join(OUT_DIR, "text")  # ⚠ 소스 `textmap/`(커밋)과 다르다 — 이건 파생 출력
DOS_ED1 = os.path.join(ROOT, "..", "..", "originals", "kr", "dos-ed1")

CLASSES = ("battle", "items_battle", "opening", "event")


def jkey(jp):
    """JP 원문 → 해시 키 (원문을 리포에 남기지 않기 위한 조회 키)."""
    return hashlib.sha1(jp.encode("utf-8")).hexdigest()[:10]


def _guard(s):
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:8]


def transform(s):
    """정발 원문 → 우리 조판(전역 규칙: 온점·쉼표 뒤 공백 제거 — 대장 참조)."""
    for p in (",", ".", "，", "．", "。", "、"):
        while p + " " in s:
            s = s.replace(p + " ", p)
    return s


def _dos_file(rel):
    path = os.path.join(DOS_ED1, rel)
    if not os.path.exists(path):
        raise SystemExit(
            f"정발 DOS 원본 없음: originals/kr/dos-ed1/{rel}\n"
            "문장 번역 테이블은 소장 원본에서 파생됩니다 — originals/README.md 참조."
        )
    with open(path, "rb") as f:
        return f.read()


def derive(cls):
    """textmap/<cls>.json → OrderedDict(k → 최종 문자열). sha 가드로 원본 무결성 검증."""
    tm_path = os.path.join(TEXTMAP_DIR, f"{cls}.json")
    with open(tm_path, encoding="utf-8") as f:
        tm = json.load(f)
    cache, out = {}, {}
    for e in tm["entries"]:
        if "ours" in e:
            val = e["ours"]
        else:
            s = e["src"]
            if s["f"] not in cache:
                cache[s["f"]] = _dos_file(s["f"])
            val = cache[s["f"]][s["o"] : s["o"] + s["l"]].decode("euc-kr")
            if s.get("x"):
                val = transform(val)
        # 낱말 단위 교정(맞춤법·띄어쓰기·명칭 통일). ⚠ **낱말까지만** — 문장을 여기에
        # 적으면 정발 문안이 리포에 박힌다(파생 체계의 존재 이유가 사라진다).
        # 대사 트랙은 spell_fix 가 같은 일을 하는데 오프닝은 그 경로를 안 타서 따로 둔다.
        for a, b in e.get("fix", ()):
            val = val.replace(a, b)
        assert _guard(val) == e["sha"], f"{cls}:{e['k']} 파생 불일치 — 원본/textmap 확인"
        out[e["k"]] = val
    os.makedirs(DERIVED_DIR, exist_ok=True)
    with open(os.path.join(DERIVED_DIR, f"{cls}.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=0)
    return out


class JpMap(Mapping):
    """JP 원문 키로 조회되는 파생 테이블 (내부 키는 jkey 해시)."""

    def __init__(self, d):
        self._d = d

    def __getitem__(self, jp):
        try:
            return self._d[jkey(jp)]
        except KeyError:
            raise KeyError(jp) from None

    def __contains__(self, jp):
        return jkey(jp) in self._d

    def __iter__(self):
        return iter(self._d)  # 해시 키 순회 (원문 복원 불가)

    def __len__(self):
        return len(self._d)


def jp_map(cls):
    return JpMap(derive(cls))


def off_pairs(cls):
    """오프셋 키 클래스 → [(int 오프셋, 문자열)] (textmap 순서 유지)."""
    return [(int(k, 16), v) for k, v in derive(cls).items()]


if __name__ == "__main__":
    for cls in CLASSES:
        d = derive(cls)
        print(f"{cls}: {len(d)}개 파생 → out/derived/{cls}.json")
