# originals/

원본 게임 데이터. **전부 gitignore** — 클론 후 직접 소장본에서 채워야 도구가 동작한다.

```
originals/
  ED2/             만트라 DOS 정발판 (ED2MAIN.EXE, SCENA/*.DLL, MAP/, BGM/ ...)
  pc98-eiyuu2/     PC98 일판 원본 (Dragon Slayer: Eiyuu Densetsu II) — 동작 레퍼런스
                   HDI 하드디스크 이미지. PC98 파티션 구조라 별도 파서/툴로 추출.
```

## 채우는 법

이미 [eiyuu-densetsu-kr](../../eiyuu-densetsu-kr) 레포에 원본을 소장 중이면
심볼릭 링크로 재사용할 수 있다:

```bash
ln -s ../../eiyuu-densetsu-kr/originals/kr/ed2            originals/ED2
ln -s ../../eiyuu-densetsu-kr/originals/pc98-eiyyu2       originals/pc98-eiyuu2
```

원본 파일은 어떤 경우에도 커밋하지 않는다.
