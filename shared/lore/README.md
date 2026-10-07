# shared/lore — 공략집 사실 사전

마스터 소장 국내 공략집(`.local/keep/guide/`)에서 **사실만** 뽑아 구조화한 참고 사전이다.
인물·지명·주문·아이템·몬스터·장(章)을 id 로 묶고, 모든 값에 출처(공략·쪽)를 단다.
편마다 한 파일이다 — `ed1.json` · `ed2.json` · `ed3.json` · `ed4.json`.

`shared/glossary/` 와 다르다. 정본(glossary)은 **JP → 우리 표기**를 정하는 자리고,
이 사전은 **공략이 무엇을 어떻게 적었나**의 기록이다. 정본을 고치는 근거 자료로 쓰되
이 사전이 정본을 대신하지 않는다.

## 🔴 저작권 경계 — 사실만

공략 본문은 잡지·블로그의 저작물이다. 이 레포는 공개돼 있으므로:

- 담는 것: 이름 · 수치(HP·가격 등) · 효과 · 위치 · 관계 · 등장 장 · 상점 품목
- 안 담는 것: 공략 문장 · 공략 순서 서술 · 엔딩·대사 인용
- `effect`·`role`·`note` 는 **우리 말로 쓴 40자 안팎 요약**이다. 원문 문장을 옮겨 오지 않는다.
- 원본 스캔·텍스트는 `.local/keep/guide/` 에만 있다(gitignore, 손대지 않는다).

## 꼴 (공통 — ED1 기준, 편마다 다른 점은 아래)

- `_doc` · `sources`(짧은 id → 파일·제목·발행처·호수·기준 판본)
- `persons` · `places` · `spells` · `items` · `monsters` · `chapters` · `misc`
- 레코드 공통: `id`(영문 슬러그, 다른 코드가 참조하는 안정 키) · `name` · `glossary` · `src: [{guide, loc}]`
  · `alt: [{field, value, src, note?}]` · `note?` · `unsure?`
- **갈리면 버리지 않는다** — 대표값 하나를 두고 나머지는 `alt` 에 출처째 남긴다.
  `field: "name"` 은 표기 이형, 그 밖은 같은 이름의 필드(`hp`·`join_level` …)의 다른 값.
- 판독이 안 되면 값은 `null`, `unsure: true` 와 `note`.
- 범주별 필드: persons(`role`·`aliases`·`relations`·`first_chapter`) · places(`kind`·`region`·`chapter`·`shops`)
  · spells(`type`·`max_level`·`mp`·`effect`·`learned`·`jp_msx`) · items(`kind`·`effect`·`price`·`where`)
  · monsters(`hp`·`exp`·`gold`·`where`·`boss`).
- `loc`: txt 는 절(`§8 제2장`), pdf 는 지면 인쇄 쪽(`p.132`), 이미지 묶음은 `img05 p.90`.

## 편마다 다른 점

| 편 | 대표 표기 | 범주·필드 차이 | 출처 주의 |
| --- | --- | --- | --- |
| ED1 | 우리 정본 | 기본 꼴 · `spells.jp_msx` | `gameworld`(1991)는 **MSX2 일본판** 기준 잡지 음역 → `alt` 전용 |
| ED2 | 우리 정본 | `items.atk`/`def`/`sell` · `spells.type_by_src` · `jp_md` · `jp_map` · 장 0=서장~5=종장 | `gameworld` 는 **메가드라이브 일본판** 기준(`MD 잡지 표기`) · 일본어 지도 소책자는 `gw_map` |
| ED3 | 공략 정발 표기(**잠정**) | `spells` 대신 `magic`(`school`·`mp`) · `merchants` 신설 · places 에 `country`·`shrine` · 장 0=서장~8 | `hwp` 는 新英雄伝説3(Windows) 기준 팬 공략 → `alt` 전용 |
| ED4 | 공략 정발 표기(**잠정**) | `magic` · `classes` 신설 · items `stats{…}` · monsters `appearances`·`element`·`jp_win` · persons `age`·`hire_cost` | `hwp` 앞 표 = 정발, 뒤 스토리 = Windows판(`edition: "win"`) — 한 출처에 층이 둘 |

- ED1·ED2 는 같은 대상이면 `ed1.json` 의 id 를 다시 쓴다(`serios` · `gale` …).
- 같은 스캔이 PDF 와 이미지 폴더에 겹치면 **하나로만 인용**한다(어느 쪽을 읽었는지 `sources` 에 적는다).

## ⚠ 표기 주의

- 🔴 **ED1·ED2** 대표 표기 = 우리 고유명사 정본(shared/glossary). 정발은 근거·이형으로만, 우리가 교정한 것은 우리 것을 따른다.
  (마스터 판정) 정발 공략 표기는 `alt` 로 내리고 `note: 정발 표기 — 우리 정본이 교정` 을 단다.
  레코드의 `glossary` 가 정본 대응(`{cat, jp, value}`)이고, `null` 이면 정본에 없는 이름이다 —
  그때만 공략 표기가 대표이며, 정본에 넣을지는 마스터께 묻는다.
- 정본에 없는 이름의 대표 표기는 **정발(만트라 DOS) 기반 공략들의 다수 표기**다. 공략 표기가 곧
  정발 화면 표기는 아니다 — 잡지 오식이 섞인다(`note: 오기 추정`). 화면 캡처(HUD·대사창)에서
  읽은 값이 본문보다 믿을 만하다.
- 🔴 **ED3·ED4** 는 씬 작업 전이라 공략의 정발 표기가 **잠정** 대표다(마스터 10-06 「우선 공략집기반으로 만들고 나중에 작업하면서 고유명사는 변경될수도 있어」). `glossary` 는 참고용 — 정본으로 덮지 않는다. 새턴 ED3(`games/ss-ed3`)에는 이미 번역된 이름이 있으니 ED3 씬 작업 때 대조한다.
- ED1 `gameworld`(1991)는 **MSX2 일본판** 기준이라 정발보다 앞선 잡지 자체 음역이다(`온리크`·`프래트`·
  `카자미의 탑`). 정발 근거로 쓰지 않는다 — `alt` 에만 싣고 note 로 표시했다.
- 스크린샷 HP 는 피해를 입은 뒤 숫자일 수 있다. note 에 적었다.

## 정본과 대조

```bash
python3 shared/lore/check_glossary.py ed1          # (a) 정본에 없는 것 (b) 다른 표기 (c) 건수
python3 shared/lore/check_glossary.py ed3 --json   # 편 이름을 인자로
```

사전엔 JP 가 없으므로 KR 표기(공백 제거)로 맞추고, 지명 접미 차이는 같은 것으로 본다.
보고만 한다 — 정본은 고치지 않는다.

## 다시 만들 때

`ed<N>.json` 은 빌더 스크립트(스크래치)로 만들었다 — 레포에는 결과 JSON 만 둔다. 고칠 때는
JSON 을 직접 고치고, 같은 이유를 `note` 에 남긴다. 새 공략을 더하면 `sources` 에 id 를 새로 단다.
