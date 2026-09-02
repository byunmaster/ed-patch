# games/ps1-ed3+4 — [kr] PS1 영웅전설 III·IV 한글패치

트랙 **kr** (일본 원판 한글 번역). 루트 규칙은 `../../CLAUDE.md`, 이 파일엔 이 게임 것만 둔다.

| 디스크 | 타이틀                                          | 원본                 |
| ------ | ----------------------------------------------- | -------------------- |
| `ed3`  | 『白き魔女 もうひとつの英雄たちの物語』(1998)   | `originals/jp/ps1-ed3` |
| `ed4`  | 『朱紅い雫』(1999)                              | `originals/jp/ps1-ed4` |

## 왜 한 코드베이스에 둘인가

**이미지는 둘인데 엔진이 하나다.** 둘 다 GMF 이식(`M01.DAT` 안에 `TIM\GMF_S.TIM`)이고
아카이브 TOC · 문자 코드표 · 대본이 앉은 자리가 같은 규격이다. 갈라 두면 그 공통층이
`shared/` 로 올라가야 하는데, `shared/` 는 main 에서만 고치므로 **모든 공통 작업이 main 의
심부름 커밋**이 된다(루트 CLAUDE.md 「💡 문서를 가른 건…」과 같은 이유).

⚠ 대신 **디스크별로 갈리는 것은 인자로 받는다** — `common.DISCS` · `charmap_<disc>.json` ·
`work/derived/<disc>/`. 「ed3 에서 됐으니 ed4 도 되겠지」로 넘어가지 않는다. 실제로
카나 코드표부터 갈렸다(`textenc.DROPPED`).

⚠ `ps1-ed1+2` 와는 **엔진이 다르다.** 물려받는 건 플랫폼 층(MODE2/2352 · EDC/ECC · MIPS)뿐이고
대본 규격은 완전히 다르다 — 저쪽은 생 SJIS, 이쪽은 자체 16비트 코드다.

## 대본이 앉은 자리 (실측 2026-09-03)

```
/SCE0~8/SC*.DAT   (ED3, 76개)   ┐ GMF 아카이브
/A~K,O/SC*.DAT    (ED4, 188개)  ┘ TOC 32B = 이름[20] + u32 off + u32 size + u32 예약
   └ 멤버 ..\DATA\*.BIN (ED3) · ..\BIN\*.BIN (ED4)  ← 대본은 여기, **압축 아님**
```

⚠ **TOC 의 off 단위가 파일마다 다르다** — `SC*.DAT` 은 4바이트 워드, `M01.DAT` 은 2048 섹터.
잘못 잡으면 예외가 아니라 **빈 슬라이스**가 나온다. `common.arc_parse` 가 검증해서 고른다.

### 문자 코드 — SJIS 가 아니다

16비트 자체 코드이고, 표는 **JIS X 0208 순서에서 그 게임이 안 쓰는 글자를 뺀 목록**이다.

```
0x0000~0x000F  제어 (0x01 개행 · 0x02 문장끝)      0xFFFF  블록 구분
0x0010~0x003E  기호·숫자 (JIS 1·3구 중 쓰는 것)
0x003F~        히라가나(JIS 4구) → 가타카나(5구) → 한자(16구~)  ⚠ 전부 이어진 한 배열
```

- **표는 `charmap_<disc>.json` 이 정본**이고 통로는 `textenc.py` 하나다. 저수준으로 바로
  디코드하지 않는다(체크리스트 4-C).
- 카나 블록만 `textenc.DROPPED` 로 계산한다 — 값은 **닻에서 유도**했고
  `tools/tests/test_kana_block.py` 가 그 셈을 다시 세운다.
- 🔴 **「무엇이 빠졌나」를 눈대중으로 정하지 않는다.** 처음에 가타카나 탈락을 손으로
  가정했다가 주인공 이름이 「ジヤラオ」로 읽혔다(2026-09-03). 닻으로 유도하면 안 틀린다.

## 도구

```bash
python3 tools/dump_arc.py    --disc ed3 --list   # 아카이브·멤버 목록
python3 tools/dump_script.py --disc ed3          # 대본 런 → work/derived/<disc>/script/
python3 tools/solve_charmap.py --disc ed3 --fill-jis --write   # 코드표 정본 갱신(제안 단계)
python3 tools/coverage.py    --disc ed3          # 표가 대본의 몇 %를 읽나
sh check.sh                                      # 이 게임의 커밋 전 게이트
```

⚠ `solve_charmap.py` 는 **비결정적 제안**이다(새턴 ED3 JP 덤프가 있어야 돈다).
빌드는 `charmap_<disc>.json` 정본만 읽는다 — 로제타가 없는 머신에서도 같은 바이트가 나온다.
