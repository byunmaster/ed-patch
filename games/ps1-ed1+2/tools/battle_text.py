"""ED1 전투 코퍼스 번역 테이블 — patch_items.apply_battle()이 사용.

몬스터 행동·조우·상태이상·보스전 대사 ~530종. 번역 원칙:
  · 정발 MONDLL(몬스터별 문장)·SINDLL 원문이 있으면 그대로/어투 유지
  · %s 뒤 조사는 병기(은(는)·을(를)·이(가)) — 이름 고정 문장(골드 등)은 정확 조사
  · 표기: 몬스터=patch_items.MONSTERS, 아이템=NAMES(워프의 날개·대형검 등),
    데미지·무리·나타났다·공격해 왔다(DOS 어투), 폰리그→온리크 교정(대장 규칙)
키는 JP 원문. apply_battle이 코드 참조를 정본으로 전투 문자열을 전수 수집하고
번역 누락 시 빌드를 멈추므로(assert), 이 표는 참조된 전투 문자열을 빠짐없이 덮어야 한다.
표시명(スライム 등)은 patch_items.monster_kr 폴백으로 풀리므로 여기 없어도 된다.
"""

from derive_text import jp_map

# {JP문장 → KR문장} 499종 — 문안은 리포에 없음: textmap/battle.json(포인터+우리 번역)
# + 소장 정발 원본(originals/kr/dos-ed1)에서 빌드 시 파생. 원문 키는 sha1 해시 조회.
B = jp_map("battle")
