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
                 "src": {"f": 상대경로, "o": 오프셋, "l": 길이, "x": 조판변환, "nl": \x01→개행}
                   또는 "ours": <문장>
                   또는 "parts": [<src 조각> | {"ours": …}, …]  ← 정발+우리 문안 혼합 슬롯,
                 "fix": [[a, b], …]  낱말 단위 교정(표기 통일 등)
                 "sha": <최종 문자열 sha1-8 가드>}
"""

import hashlib
import json
import os
import re
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


# 부호 앞 공백 제거 — **대사 트랙과 같은 표기 방침**이다(유저 승인 2026-07-24, 재확인 08-09
# "`!!` 앞에 공백은 없는 것으로 통일하자"). 정발은 `파열했다 !!` 처럼 띄운 자리와 안 띄운
# 자리가 섞여 있어서, 파생 단계에서 한 번에 맞춘다. ⚠ 말줄임 `...` 앞 공백은 정발의 의도적
# 호흡이라 건드리지 않는다 — 그래서 `\.(?!\.)`.
_PUNCT_SP = re.compile(r"[ ]+(?=[!?,]|\.(?!\.))")


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


def ours_keys(cls):
    """`ours` 만으로 만들어지는(= 정발 대응이 아직 없는) 엔트리 키 집합.

    진단용이다 — 이걸 JP 로 되돌려 빌드하면 **인게임에서 일본어로 보이는 자리 = 자체 번역**이
    된다(유저 제안 2026-08-09). 정발 전환이 어디까지 왔는지 플레이하며 바로 보인다.
    """
    tm_path = os.path.join(TEXTMAP_DIR, f"{cls}.json")
    with open(tm_path, encoding="utf-8") as f:
        tm = json.load(f)
    return {e["k"] for e in tm["entries"] if "ours" in e}


def derive(cls):
    """textmap/<cls>.json → OrderedDict(k → 최종 문자열). sha 가드로 원본 무결성 검증."""
    tm_path = os.path.join(TEXTMAP_DIR, f"{cls}.json")
    with open(tm_path, encoding="utf-8") as f:
        tm = json.load(f)
    cache, out = {}, {}

    def piece(s):
        """{src} 한 조각 → 문자열. `ours` 키면 우리 문안 그대로."""
        if "ours" in s:
            return s["ours"]
        if s["f"] not in cache:
            cache[s["f"]] = _dos_file(s["f"])
        v = cache[s["f"]][s["o"] : s["o"] + s["l"]].decode("euc-kr")
        if s.get("nl"):
            v = v.replace("\x01", "\n")  # DOS 표시 개행 마커 → 개행
        return transform(v) if s.get("x") else v

    for e in tm["entries"]:
        if "ours" in e:
            val = e["ours"]
        elif "parts" in e:
            # 정발 문장 + 우리 문안이 한 슬롯에 섞이는 자리(챕터 클리어: 정발 해방 문구 +
            # PS1 전용 EP 획득 줄). 정발 몫은 포인터로 두어야 리포에 문안이 안 남는다.
            val = "".join(piece(s) for s in e["parts"])
        else:
            val = piece(e["src"])
        # 낱말 단위 교정(맞춤법·띄어쓰기·명칭 통일). ⚠ **낱말까지만** — 문장을 여기에
        # 적으면 정발 문안이 리포에 박힌다(파생 체계의 존재 이유가 사라진다).
        # 대사 트랙은 spell_fix 가 같은 일을 하는데 오프닝은 그 경로를 안 타서 따로 둔다.
        for a, b in e.get("fix", ()):
            val = val.replace(a, b)
        val = _PUNCT_SP.sub("", val)
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
