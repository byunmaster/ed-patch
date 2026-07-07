# originals/

원본 게임 데이터. **전부 gitignore** — 클론 후 직접 소장본에서 채워야 도구가 동작한다.

```
originals/
  kr/            번역 저본: 국내 정발판(만트라) — 모든 타깃의 공통 기반
                 ED1/ (SINDLL/*.DLL = 대사), ED2/ (SCENA/*.DLL = 대사), ED3/, ED4/
  ps1-eiyuu12/   PS1 영웅전설 1+2 (SLPS-01323) 타깃 원본 이미지
                 "Legend of Heroes I & II, The - Eiyuu Densetsu (Japan).bin/.cue"
                 (단일 트랙 MODE2/2352, 252,498,960 bytes)
```

- 번역 저본은 `kr/` 아래 판본별 폴더 — DOS판은 `ED1`, 윈도우 정발판은 `ED1_WIN`처럼
  `_WIN` 포스트픽스(실제 정발 표기 관례를 따름). 타깃 원본은 `games/` 폴더명과 동일하게.
- 패치 빌드 출력은 각 게임의 `work/`, 분석 산출물은 `out/` — 여긴 원본만.
