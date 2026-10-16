# 목업 고치기 지시 (CEO) — 2026-10-16

사용자 요청: "목업 고치고, 고친 부분은 표시해서 알기 쉽게 해."

## 입력
- 보드: `docs/design/ui-benchmark/50-mockup/boards/<Board>.dc.html` (이걸 직접 고친다)
- 대응표: `docs/design/ui-benchmark/50-mockup/coverage/coverage-<Board>.md` 의 `빠짐`·`문구로만` 줄, 그리고 `coverage/README.md` 의 "구현 때 꼭 고칠 것"
- 현재 소스(정확한 문구·동작 확인용): `frontend/src/...`, `frontend/src/i18n/ko.json`
- 결정 원본: `docs/design/DECISIONS.md` (특히 D25·D28·D29), 공통 규칙 `AGENTS.md`

## 무엇을 고치나 (우선순위 순)
1. **뜻이 달라진 문구**: 현재 코드의 뜻으로 되돌리되 쉬운 말은 유지. 예) 벤치마크 없음 = "근처 새 아파트 실적이 없어 종합 점수를 계산하지 않았어요", '오를 가능성'은 목표 시점을 함께 적고("목표 시점: 입주 + 1년" 등) "당첨 확률이 아니에요 · 보장 아님" 유지, 판정기 저하 띠 = 판정기를 못 쓰는 상태(미판정)로 표시, 탭 고정 띠 = 다른 탭이 열쇠를 바꿈, 재계산 띠 = "발행 순간 값과 다를 수 있음", 용어 '현재 구매가' = "확인된 할인만 뺌", 라벨 뜻 문장은 ko.json `label.help.*` 원문을 쉬운 말로 한 번만 정하고 Shell·Glossary 두 곳을 똑같이.
2. **화면이 계산·작문한 값 제거/교체**(규칙 3·5): "접수 454 ÷ 공급 73" 같은 식, 서버에 없는 평균선, 사실들을 엮어 만든 판단성 요약 문장("본 청약은 끝났고…") → 서버 필드를 그대로 나열한 사실 줄(예: "현재 적용 공고: 무순위 · 접수 상태: 접수 가능(공식 홈페이지 10.13 확인)")로 교체. 서버 API에 없는 수(예: 모순 주장 요약 "맞음 19 · 사람 검토 5")는 빼거나 [값]+"API 필요" 메모. 개수 세기(D25-3)는 허용. 판정 범위 사유는 서버 문자열 그대로.
3. **계약에 없는 필터 칩**: "실거주 의무 없음" 삭제, "되팔기 제한 곧 끝남" → 기존 필터 '이 날짜 전에 전매 종료'로 교체. 단지 찾기 기본 정렬 = 종합 점수순(D28-4), '접수 가능 먼저'는 정렬 선택지로만.
4. **눈에 보이는데 빠진 것**(coverage `빠짐` 중 화면에 보이는 것): 그려 넣는다. 예) 라벨 배지·출처 밑줄, 용어 ? 버튼, 모바일 카드 배지, 규제 항목 전체, 흐린(닫힌/꺼진) 줄, 차트 축 눈금·범례·빈 상태·"표로 보기" 펼친 표, 다크 모드는 Shell에 작은 미리보기 1개, 모바일 메뉴는 현재 3개(홈·단지 리스트·용어)로.
5. **툴팁**: 차트마다 툴팁 예시 하나를 정적 말풍선으로 그린다(내용은 현재 코드 툴팁 항목 그대로).
6. **그림으로 못 그리는 동작**(저장 중 버튼 꺼짐, URL 기억, Esc 닫기, 디바운스, 글자 수 제한, 폴링 등): 보드 맨 아래에 "구현할 때 지금 동작 그대로 유지" 상자를 만들어 coverage 번호와 함께 한 줄씩 나열.

## 고친 곳 표시 (반드시)
- helmet `<style>`에 아래 두 클래스를 추가(없으면):
  `.fix{outline:3px dashed #E0A800;outline-offset:4px}`
  `.fixtag{display:inline-flex;align-items:center;gap:4px;background:#FFD43B;color:#3D2E00;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;vertical-align:middle;white-space:nowrap}`
- 고친 블록에 `class="fix"`(기존 class가 있으면 공백으로 덧붙임)를 달고, 그 블록 안 제목 옆 또는 첫 줄에 `<span class="fixtag">고침 XX-n</span>`을 넣는다.
- 보드 코드: Shell=SH, Main=HM, Glossary=GL, Detail=DT, DetailTabs=DX, Mobile=MB, List=LS, ListTable=LT, Compare=CP, Scenario=SC, Reports=RP, Market=MK, Ops=OP, RegionNew=RN, LivingAreas=LA. 번호는 보드마다 1부터.
- 보드 맨 위(헤더 바로 아래)에 노란 안내 띠 하나: `<div class="fix" …>이 보드에서 고친 곳 n개 — 노란 점선과 '고침' 표가 붙은 곳이에요. 목록: fixes-<Board>.md</div>` (fixtag 포함).
- 기록 파일: `docs/design/ui-benchmark/50-mockup/fixes/fixes-<Board>.md`
  `| ID | 무엇을 고쳤나 | 왜 (coverage #번호 / README 항목) | 보드 위치(섹션) |`
- 대응표 갱신: 고친 줄의 상태를 `있음(고침 XX-n)` 또는 `문구로만(고침 XX-n)`으로 바꾸고, 표 끝 요약 개수도 다시 센다.

## 지킬 것
- 보드 형식 규칙(어기면 조용히 깨짐): `<script src="./support.js"></script>` 줄 유지, 모든 비빈 요소 닫기·속성 따옴표, `{{hole}}`은 점 경로만, `<tr>` 안에 sc-for/sc-if 넣지 않기, 스크립트는 classic JS `class Component extends DCLogic`. 높이가 늘면 `data-props`의 `$preview.height`를 늘린다(넉넉히).
- 숫자를 지어내지 않는다. 필요한 실데이터는 이미 보드에 있는 값이나 `contracts/fixtures`/현재 소스로 확인. 없으면 `[값]`.
- 금지어(추천·유리·불리·좋음·나쁨·싸다·비싸다·저렴·알짜·기회·사세요·넣으세요·당첨 가능·확실·보장(“보장 아님”만 허용)) 새로 쓰지 않기. 실제 기사 제목 인용은 그대로 두되 따옴표로.
- 담당 보드·그 대응표·fixes 파일 밖은 쓰지 않는다. git 명령 금지. 비밀 출력 금지.

## 최종 보고(메인으로, 짧게)
보드별: 고친 수, 새 `$preview` 높이, 아직 못 고친 것(사유). 대응표 갱신 후 빠짐 개수.
