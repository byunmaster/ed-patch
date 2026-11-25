# hotfix/ — 핫픽스 시험 경로 (v1.2.1 후보)

배포판(v1.2.0)은 잠겨 있다. 여기 문안은 **`ED_HOTFIX=1` 일 때만** 제품 정본 위에 덮인다 — 끄면(기본) 제품 롬 바이트는 한 비트도 안 바뀐다.
적용(제품 정본에 넣기)·조판 지문 재동결·락 갱신은 마스터 판단이다(마스터 10-28 「PS1 I·II 수정은 늘 시험 경로 + 핫픽스 목록」).

    ED_HOTFIX=1 ED_BUILD_TAG=test-hotfix python3 tools/build.py      # → work/build/test-hotfix/

- `script/<씬>.json` — 씬 대사 블록 덮어쓰기. 키 = 블록 번호, 값 = `script/` 와 같은 꼴(`t` 문안, `s` 화자). 블록 단위 통째 교체.
  이 블록의 확정 락 위반은 시험 빌드에서만 건너뛴다(`reinsert_kr_pilot.hotfix_eids`).
- `textmap/<클래스>.json` — 실행파일 문구(전투·이벤트·오프닝)의 `derive_text.derive()` 값 덮어쓰기. 키 = textmap 키(sha 앞 10자).
  `textmap/monster_lines_ed2.json` 만 예외 — ED2 몬스터 전투 대사 손표(`dict_tables.monster_lines_ed2`) 위에 덮는다. 키 = 원문.
- 정합 테스트 `tools/tests/test_hotfix_overlay.py` — 덮는 블록이 정본에 있고 실제로 다른지.
