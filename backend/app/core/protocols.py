"""백엔드 모듈 사이 계약 — 내부 프로토콜 (RA §4-3, 계약 2026-10-09.3, WP0 소유).

구현 에이전트는 이 파일의 docstring만 보고 구현한다. 각 Protocol의 docstring은 RA §4-3 표의 "규칙" 열과
그 규칙을 지키는 데 필요한 계약 세부를 옮긴 것이다.

DTO는 손으로 만들지 않는다: ``contracts/schemas/*.json`` → ``app.core.contracts_gen`` (pydantic v2 생성물)을
그대로 쓴다. 여기서는 이름만 다시 내보낸다(ComponentScore = ScoreComponent, RequirementResult =
RequirementPreSet).

| Protocol | 구현 WP | 모듈 |
| --- | --- | --- |
| Collector | WP1 | app.collectors.<source> |
| Parser, Resolver | WP2 | app.normalize |
| JudgeAdapter, ClaimSplitter | WP3 | app.judge |
| ScoreEngine, RequirementPrecalc | WP4 | app.analysis |
| Exporter | WP8 | app.reports |
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, Protocol, runtime_checkable

from app.core.contracts_gen import (
    Claim,
    ComplexScoreInput,
    FieldCandidate,
    JudgmentEnvelope,
    RawDocument,
    Region,
    RequirementPre,
    RequirementPreSet,
    ResolvedFields,
    Scenario,
    ScoreComponent,
    ScoreInputs,
    ScoreRunResult,
    ScoreTotal,
    Snapshot,
)

__all__ = [
    "CONTRACT_VERSION",
    "JUDGE_TOOLS",
    "Claim",
    "ClaimSplitter",
    "Collector",
    "ComplexScoreInput",
    "ComponentScore",
    "ExportFormat",
    "Exporter",
    "FieldCandidate",
    "JudgeAdapter",
    "JudgePayload",
    "JudgeTool",
    "JudgeUnavailable",
    "JudgmentEnvelope",
    "Parser",
    "RawDocument",
    "Region",
    "RequirementPre",
    "RequirementPrecalc",
    "RequirementResult",
    "ResolvedFields",
    "Resolver",
    "Scenario",
    "ScoreEngine",
    "ScoreInputs",
    "ScoreRunResult",
    "ScoreTotal",
    "Snapshot",
    "canonical_hash_json",
    "canonical_value",
    "input_hash",
]

CONTRACT_VERSION: Final = "2026-10-09.5"

JudgeTool = Literal["screen", "extract", "audit", "classify", "compare", "noul", "rerank", "decide", "verify"]
JUDGE_TOOLS: Final[tuple[JudgeTool, ...]] = (
    "screen",
    "extract",
    "audit",
    "classify",
    "compare",
    "noul",
    "rerank",
    "decide",
    "verify",
)

JudgePayload = dict[str, Any]
"""판정기에 보내는 payload(JSON 객체). judge/guard.py를 통과한 공개 분양 정보만 담는다."""

ExportFormat = Literal["html", "pdf"]
"""보고서 형식 (DECISIONS D4). md·docx 없음."""

ComponentScore = ScoreComponent
"""score_component 1행 = 구성 점수 1개 (contracts/schemas/score_component.json)."""

RequirementResult = RequirementPreSet
"""요건 사전 계산 결과 {access, regulation, funds: RequirementPre} (contracts/schemas/decision.json)."""


class JudgeUnavailable(Exception):
    """판정기를 쓸 수 없음(프로세스 기동 실패·연결 끊김·타임아웃·프로토콜 오류).

    JudgeAdapter가 던지는 예외는 이것 하나뿐이다. 판정기의 review·escaped·blocked 같은 '판정 결과'는
    예외가 아니라 봉투(status)로 돌려준다. 이 예외를 받은 쪽(WP7 degraded.py)은 수집·정규화를 계속하고
    degraded 모드로 전환한다(snapshot.degraded=true, 점수 미계산, 화면 배너, 복구 후 rejudge 자동 등록 — T18).
    던지기 전에 어댑터는 judgment_log에 status='error' 행을 남긴다(실패도 데이터).
    """


def canonical_value(obj: Any) -> Any:
    """hash 용 정준 값(R3 minor 10). 같은 '값'이면 같은 JSON 이 되도록 숫자 표기를 맞춘다.

    - 정수와 같은 실수·Decimal 은 정수로: ``1``·``1.0``·``Decimal("1.00")`` → ``1`` (``-0.0`` → ``0``).
    - 정수가 아닌 Decimal 은 float 로(``Decimal("0.10")`` → ``0.1``; float 와 같은 표기). float 정밀도를 넘는
      Decimal 자릿수는 버려진다 — payload 숫자는 확률·비율·금액(원 정수)이라 문제없다.
    - NaN·±Infinity(float·Decimal)는 ``ValueError`` — JSON 이 아니고 같은 값 비교도 안 된다.
    - bool 은 bool 그대로(int 의 하위형이지만 정수로 바꾸지 않는다). dict 키는 문자열이어야 한다.
    - tuple 은 list 와 같다. 그 밖의 형은 ``TypeError``(조용히 str() 하지 않는다).
    """
    if obj is None or isinstance(obj, bool | str):
        return obj
    if isinstance(obj, int):
        return int(obj)
    if isinstance(obj, float):
        if not math.isfinite(obj):
            raise ValueError(f"canonical JSON: 유한하지 않은 수 {obj!r}")
        return int(obj) if obj.is_integer() else obj
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise ValueError(f"canonical JSON: 유한하지 않은 수 {obj!r}")
        if obj == obj.to_integral_value():
            return int(obj)
        return canonical_value(float(obj))
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError(f"canonical JSON: 키는 문자열이어야 한다 ({type(k).__name__})")
            out[k] = canonical_value(v)
        return out
    if isinstance(obj, list | tuple):
        return [canonical_value(v) for v in obj]
    raise TypeError(f"canonical JSON: 지원하지 않는 형 {type(obj).__name__}")


def canonical_hash_json(obj: Any) -> str:
    """hash 키용 canonical JSON 문자열: ``canonical_value`` + 키 정렬, 구분자 (',', ':'), ensure_ascii=False,
    allow_nan=False. ``input_hash`` 와 judgment_log.input_len 이 같은 정의를 쓴다."""
    return json.dumps(
        canonical_value(obj), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def input_hash(tool: JudgeTool, purpose: str, payload: JudgePayload, adapter_version: str) -> str:
    """같은 입력 재호출 금지의 키 (judgment_log.input_hash, UNIQUE).

    ``'sha256:' + sha256(canonical_hash_json({tool, purpose, payload, adapter_version}))``.
    canonical JSON = 키 정렬, 구분자 (',', ':'), ensure_ascii=False, allow_nan=False, UTF-8,
    숫자 정준화(``canonical_value``: 1 = 1.0 = Decimal('1'), Decimal('0.5') = 0.5, NaN·Infinity 거부).
    정준화는 정수와 같은 실수만 바꾸므로 정수가 아닌 값·문자열만 담은 기존 payload 의 hash 는 그대로다.
    adapter_version이 바뀌면(판정기 서버 버전·모델 포함, DECISIONS D6) 모든 hash가 바뀌어
    전체 재판정 1회가 된다.
    WP3 cache.py와 WP5 시나리오 미리보기(cache_hits 계산)가 같은 정의를 쓰도록 여기 한 곳에 둔다.
    """
    doc = {"tool": tool, "purpose": purpose, "payload": payload, "adapter_version": adapter_version}
    return "sha256:" + hashlib.sha256(canonical_hash_json(doc).encode("utf-8")).hexdigest()


@runtime_checkable
class Collector(Protocol):
    """소스 1종의 수집기 (WP1). ``fetch(region, snapshot, since) -> list[RawDocument]``.

    규칙
    - 멱등: 같은 sha256이면 저장하지 않는다(raw_document.sha256 UNIQUE). 이미 있는 원문은 기존 행을 돌려준다.
      같은 입력으로 두 번 실행해도 raw_document 행 수가 늘지 않는다(T17).
    - 실패도 데이터: 403·5xx는 ``RawDocument(http_status=403, path=None)``, DNS 실패·타임아웃은
      ``http_status=None, error_text='DNS'|'timeout'``으로 반환한다. 예외로 삼키지 않는다.
      실패 행의 sha256 규칙과 error_text 값 목록은 contracts/schemas/raw_document.json(같은 날 재시도는
      중복 없음, 날마다 한 행).
    - robots·속도 제한·재시도·백오프는 ``app.core.http``가 강제한다 — 수집기가 우회하지 않는다.
      robots 차단 원인은 ``FetchResult.robots_reason``(다시 요청하지 않는다). 키 인증 공식 API 호스트
      (``HTTP_ROBOTS_EXEMPT_HOSTS``)는 robots 검사 예외(2026-10-09.2).
    - 표 JSON 은 ``table_path``, 수집기 부가 정보는 ``meta``(json)에 둔다(2026-10-09.2).
    - 지역은 region 행으로만 안다(sido_codes·sigungu_codes·legal_dong_codes). 지역명을 코드에 두지 않는다.
      청약홈 목록은 sido_codes로 조회하고 주소를 legal_dong 이름으로 매칭해 region.legal_dong_codes 안의 것만
      남긴다(매칭 실패는 버리지 않고 inclusion_class='범위 경계' 후보로 넘긴다, D2-6).
    - since: 이 시각(ISO) 이후 바뀐 것만(가능한 소스만). None이면 전부.
    - 공식 홈페이지는 httpx → 실패·동적이면 Playwright 렌더 → 스크린샷 + DOM 텍스트 + image_hash.
    - 원문 파일은 RAW_DIR/{source_kind}/{yyyy-mm-dd}/{sha256}.{ext}.
    - 개인정보·로그인 필요 자료는 수집하지 않는다.
    """

    def fetch(self, region: Region, snapshot: Snapshot, since: str | None) -> list[RawDocument]: ...


@runtime_checkable
class Parser(Protocol):
    """원문 → 필드 후보 (WP2). ``parse(raw) -> list[FieldCandidate]``.

    규칙
    - 후보는 (entity, field, value_text, value, source_rank, label, excerpt). 원문 발췌(excerpt) 필수 —
      출처 없는 숫자는 하나도 남기지 않는다. 가능하면 excerpt_start/end(원문 텍스트 오프셋)를 채운다.
    - 금액은 원 단위 정수(만원 표기는 ×10,000), 면적 ㎡ 소수 2자리, 날짜 ISO. value_text는 원문 표기 그대로.
    - source_rank는 RA §3 표: 세대수·면적·일정·경쟁률 = 청약홈 상세(1) > 공고문(2) > 언론(3);
      가격·발코니·옵션·납부·전매·거주의무 = 공고문 최신(1) > 청약홈(2) > 언론(3).
    - 정규식·표 파서가 실패한 필드는 needs_extract=True로 표시해 판정기 extract payload로 넘긴다
      (파서가 판단하지 않는다).
    - 실패한 원문(http_status≠200, 스캔 PDF)은 빈 목록 또는 label='확인 불가'(reason='스캔' 등) 후보를 낸다.
    - OCR 원문(error_text 'ocr'·'ocr_partial:<p>')에서 읽은 값은 label='추정', reason='OCR'(표시 '추정(OCR)')
      이고 수치·날짜 필드는 needs_extract=True — 판정기 extract/audit 를 반드시 거친다(D5-4, R3 C3).
    - observed_on = 원문이 말하는 시점(공고일 등). 공식 홈페이지 접수 문구는 entity='intake_status',
      field='status_text' 후보로 낸다(분류하지 않는다, 2026-10-09.2).
    """

    def parse(self, raw: RawDocument) -> list[FieldCandidate]: ...


@runtime_checkable
class Resolver(Protocol):
    """상충 해결 (WP2). ``resolve(candidates) -> ResolvedFields``.

    규칙
    - RA §3 우선순위로 (entity, entity_id|entity_key, field)마다 후보 하나를 chosen으로 정한다. 나머지는
      chosen=false로 provenance에 보관한다(삭제하지 않음).
    - 값이 다른 후보가 둘 이상이면 conflict_group('<entity>:<id 또는 key>:<field>')으로 묶는다.
    - needs_compare=True는 '1차·1차 상충'만: 값이 다른 최상위 후보 둘이 모두 primary이고 source_rank가 같아
      우선순위로 가를 수 없을 때. 1차 vs 2차, 또는 rank가 다른 1차끼리(청약홈 상세 vs 공고문 세대수, T5)는
      compare 없이 rank 1 채택. 둘 다 2차면 병기하고 판정 미사용.
    - needs_compare 그룹은 **채택 보류**(R3 M1): provenance 의 대표 행(최신)만 chosen=true(reason 머리
      '출처 상충 — compare 대기')이고, ``ResolvedFields.chosen`` 에는 값 없는 label='확인 불가' 후보(같은
      reason)를 낸다 → 사실 테이블 값 없음(점수 미사용). compare 결과로만 채택한다(contradicts → 공고문,
      same_fact·different_facts → 우선순위 대표; review·degraded → 보류 유지
      — ``normalize.judged.apply_compare``).
    - 판정기를 직접 부르지 않는다. compare는 WP3가 needs_compare 그룹에 대해 부른다.
    """

    def resolve(self, candidates: list[FieldCandidate]) -> ResolvedFields: ...


@runtime_checkable
class JudgeAdapter(Protocol):
    """판정기 어댑터 (WP3: JevMcpAdapter, MockAdapter).

    9개 메서드 ``<tool>(payload, purpose) -> JudgmentEnvelope``.

    규칙
    - 호출 전 ``input_hash(tool, purpose, payload, adapter_version)``로 judgment_log를 조회한다.
      있으면(status가 error가 아니면) 판정기를 부르지 않고 그 행을 ``cached=True`` 봉투로 돌려준다.
      없으면 호출하고 judgment_log에 기록한 뒤 ``cached=False`` 봉투를 돌려준다.
      같은 payload 2회 → 실제 호출 1회(T17).
    - 모든 호출은 성공·실패 불문 judgment_log 행을 가진다(judgment_seq).
      status='error' 행은 같은 hash로 재시도할 때 새 행을 넣지 않고 갱신한다(input_hash UNIQUE).
    - 예외는 ``JudgeUnavailable`` 하나로. review·escaped·blocked는 예외가 아니라 봉투 status.
    - payload는 판정기에 보내기 전 judge/guard.py를 통과해야 한다(전화번호·주민번호·이메일·환경변수 값 → 거부,
      status='blocked' 행, T14). 로그에는 payload 원문 금지 — input_hash와 길이만.
    - 임계값을 넘기지 않는다: JEV 기본값을 그대로 쓰고, 응답의 임계값·decision을 raw(output_json)에
      그대로 저장한다(DECISIONS D6).
      adapter_version = '<어댑터 코드 버전>+jev-mcp@<initialize.serverInfo.version>+<응답 model>'
      (2026-10-09.2, D6 보강: 모델이 바뀌어도 재판정. 모델을 아직 모르면 '+<model>' 없이).
    - result는 도구별 정규화 모양
      (contracts/schemas/judgment_envelope.json $defs: ScreenResult … VerifyResult).
    - MockAdapter: contracts/fixtures/<fixture>/judgments/ 에서 input_hash로 녹화를 찾고,
      없으면 status='review' 봉투를 돌려준다(테스트가 조용히 통과하지 않게).
    - 메서드는 동기다(worker 스레드에서 호출). MCP 클라이언트가 비동기면 구현 내부에서 이벤트 루프를 돌린다.
    """

    @property
    def adapter_version(self) -> str: ...

    def screen(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def extract(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def audit(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def classify(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def compare(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def noul(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def rerank(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def decide(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...

    def verify(self, payload: JudgePayload, purpose: str) -> JudgmentEnvelope: ...


@runtime_checkable
class ClaimSplitter(Protocol):
    """원자 주장 분할 (WP3). ``split(text) -> list[Claim]``.

    규칙
    - 1 사실 = 1 주장. 접속사('이고', '및', '·', '그리고' 등)와 열거를 나누고, 숫자가 2개 이상이면 분할한다.
    - "3개는 unlikely이고 나머지는 uncertain" → 주장 2개 이상(T6). 복합 문장을 그대로 verify에 보내지 않는다.
    - 규칙 기반 문자열 처리다(LLM·판정기 호출 없음). 원문 순서대로 ordinal을 0부터 매긴다.
    - section·snapshot_id·complex_id는 호출자가 키워드로 넘기면 각 Claim에 채운다.
      verify_status·judgment_seq는 None.
    """

    def split(
        self,
        text: str,
        *,
        section: str = "",
        snapshot_id: int | None = None,
        complex_id: int | None = None,
    ) -> list[Claim]: ...


@runtime_checkable
class ScoreEngine(Protocol):
    """점수 엔진 (WP4). ``run(snapshot, scenario, inputs) -> ScoreRunResult``.

    규칙
    - 순수 함수: DB·네트워크·시계 접근 없음. 같은 inputs = 같은 결과(소수 자리까지).
    - 각 component에 formula_text(식을 값으로 채운 문자열, 빈 문자열 금지)와 label·reason을 채운다(RA §6-4).
    - 판정 값은 봉투 status가 ok인 것만 쓴다. noul p10이 review·escaped면 그 단지 total=None('미판정').
    - rerank 값은 inputs.rerank.judgment_seq 한 호출의 것만(§6-5 고정 앵커). prev가 있으면 delta 채움.
    - 종합 S = Σ w_i s_i를 10진(Decimal) 연산으로 계산하고 원값을 ScoreTotal.total에 둔다(표시 반올림은 API).
    - 동점: total 내림차순(동률이면 complex_id 오름차순) 정렬, 그룹 리더와 |ΔS| < 0.05인 뒤따르는 단지는 같은
      rank(경쟁 순위)·같은 tie_group. 원값으로 비교한다.
    - unstable: 민감도 12변형(±0.10, 나머지 비례 재정규화) 중 하나라도 TOP 5 집합(rank ≤ 5 전부)이
      바뀌면 그 집합에 들어오거나 나간 단지 True (RA §6-6, contracts/schemas/sensitivity.json).
    - scenario.weights에 move_in이 있으면(A·D) liquidity 대신 s_movein = clamp(10 − 2×입주까지 연수, 0, 10).
      scenario.policy.p10_horizon의 사다리를 p10 성분에 쓴다(C = asof_plus_5y).
    - inputs.complexes[].fixed_components가 있으면 그 성분은 식을 건너뛰고 고정값을 쓴다(회귀 (a)단계,
      contracts/fixtures/incheon_gimpo_2026-10-08/expected_scores.json 재현 — T1).
    """

    def run(self, snapshot: Snapshot, scenario: Scenario, inputs: ScoreInputs) -> ScoreRunResult: ...


@runtime_checkable
class RequirementPrecalc(Protocol):
    """요건 사전 계산 (WP4). ``evaluate(complex, scenario) -> {access, regulation, funds}``.

    규칙 (RA §6-7, 규칙 코드는 contracts/schemas/scenario.json RequirementRule)
    - 세 요건 각각 status(충족/미충족/미입력/확인 불가) + 근거 숫자 문자열(evidence)을 만든다. 예:
      '접수 가능(공식 팝업 2026-10-07); 전매 종료 2028-09 < 매도 시작 2030-03 → 충족',
      '거주의무 0개월, 재당첨 제한 미적용(비규제) → 충족',
      '계약금 7,490만 ≤ 자기자본 1억; 잔금 부족 0 → 충족 (중도금 이자후불제)'.
    - 접근 가능성: intake_status '가능' and path≠unofficial_ref
      (A: 가점제 공급, B·D: 무순위·임의·선착순 공식 경로, C: 전매 종료 ≤ asof_date + holding_years).
      접수 상태 '확인 불가'면 status '확인 불가'.
    - 자금: P_mid × 계약금% ≤ 자기자본 and P_mid − 대출한도 − 자기자본 ≤ 0. 자기자본·한도가 None이면 '미입력'.
    - 결과는 decide payload의 증거에 그대로 삽입되고 decision.req_*_pre에 저장된다.
      판정기 결과와 다르면 mismatch.
    - asof_date(YYYY-MM-DD)는 키워드로 받는다(전매 종료·입주까지 기간 계산). 순수 함수.
    """

    def evaluate(
        self, complex: ComplexScoreInput, scenario: Scenario, *, asof_date: str
    ) -> RequirementResult: ...


@runtime_checkable
class Exporter(Protocol):
    """보고서 내보내기 (WP8). ``render(snapshot, fmt, compare_snapshot=None) -> Path``.

    규칙 (DECISIONS D4가 RA §4-3의 '32KB 분할'을 대체)
    - fmt='html': 단일 자립 HTML(CSS·ECharts 번들 인라인, 외부 URL 리소스 0). 섹션 §1~§11(+지역 추가 장) +
      부록 A 판정 로그 · B 참고자료, 섹션마다 앵커가 있고 단독으로 열린다. 차트 option은 WP4 결과에서 생성.
    - fmt='pdf': 같은 HTML을 Playwright chromium ``page.pdf()``로 인쇄(weasyprint 미사용).
    - 부록 B 참고자료 URL 전수, 형식 유효. §8 숫자는 score_total과 같아야 한다.
    - compare_snapshot이 있으면 두 스냅샷 파생 테이블 diff 장을 붙인다.
    - 스냅샷에 claim.verify_status='contradicted'가 남아 있으면 생성을 거부한다(예외 또는 잡 failed + 사유).
    - 반환값은 생성한 파일 경로. 판정기를 부르지 않는다.
    """

    def render(
        self, snapshot: Snapshot, fmt: ExportFormat, compare_snapshot: Snapshot | None = None
    ) -> Path: ...
