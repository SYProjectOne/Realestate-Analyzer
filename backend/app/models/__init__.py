"""SQLAlchemy 모델 (WP0 소유, 계약 2026-10-09.7).

contracts/migrations/versions/(0001_init … 0007_r3b_closing) head 와 1:1.

다른 WP는 읽기만 한다. 컬럼이 더 필요하면 계약 변경 요청(AGENTS.md)으로.
"""

from app.models.analysis import Decision, Ladder, Scenario, ScoreComponent, ScoreRun, ScoreTotal
from app.models.base import NAMING_CONVENTION, Base
from app.models.complex import Competition, Complex, ComplexType, IntakeStatus, PaymentTerms, RemainingEvent
from app.models.judgment import Claim, FactDemotion, JudgmentLog
from app.models.market import Benchmark, Catalyst, CatalystLink, ComparableSet, RtmsTrade, Supply, Unsold
from app.models.ops import ChangeEvent, ChecklistItem, HumanCheck, JobRun, ShareLink
from app.models.raw import FieldProvenance, RawDocument
from app.models.reference import AdminDong, AdminLegalMap, HouseholdStat, LegalDong
from app.models.region import Region, Snapshot, SnapshotView, SnapshotViewUnit

__all__ = [
    "NAMING_CONVENTION",
    "AdminDong",
    "AdminLegalMap",
    "Base",
    "Benchmark",
    "Catalyst",
    "CatalystLink",
    "ChangeEvent",
    "ChecklistItem",
    "Claim",
    "ComparableSet",
    "Competition",
    "Complex",
    "ComplexType",
    "Decision",
    "FactDemotion",
    "FieldProvenance",
    "HouseholdStat",
    "HumanCheck",
    "IntakeStatus",
    "JobRun",
    "JudgmentLog",
    "Ladder",
    "LegalDong",
    "PaymentTerms",
    "RawDocument",
    "Region",
    "RemainingEvent",
    "RtmsTrade",
    "Scenario",
    "ScoreComponent",
    "ScoreRun",
    "ScoreTotal",
    "ShareLink",
    "Snapshot",
    "SnapshotView",
    "SnapshotViewUnit",
    "Supply",
    "Unsold",
]
