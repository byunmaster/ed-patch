# shared/fonts

한글화 공용 폰트 에셋. 모두 SIL OFL 1.1 — 패치 임베딩·재배포 허용 (라이선스 파일 동봉).

| 폰트                        | 격자   | 파일             | 출처                                | 용도                        |
| --------------------------- | ------ | ---------------- | ----------------------------------- | --------------------------- |
| Galmuri11 (+Bold·Condensed) | 11×11  | `Galmuri11*.bdf` | <https://github.com/quiple/galmuri> | PS1 영웅전설 1+2 (11×11 셀) |
| Galmuri7 / 9 / 14 / Mono    | 7~14px | `Galmuri*.bdf`   | 〃                                  | 다른 셀 크기 예비           |
| Neo둥근모                   | 16×16  | `neodgm.ttf`     | <https://github.com/neodgm/neodgm>  | 16px 폰트 플랫폼용 예비     |

- Galmuri는 **BDF**(비트맵 원본)를 사용 — 변환기(`games/ps1-eiyuu12/tools/hangul_font.py`)가
  도트를 무손실 파싱한다. TTF/WOFF가 필요하면 출처 릴리스에서 받을 것.
- 릴리스 크레딧에 폰트 저작자 표기 필수: Galmuri © quiple (OFL), Neo둥근모 © Eunbin Jeong (OFL).
