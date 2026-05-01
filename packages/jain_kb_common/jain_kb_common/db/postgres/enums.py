import enum

from sqlalchemy import Enum as SAEnum


class AuthorKind(str, enum.Enum):
    acharya = "acharya"
    gyaani = "gyaani"
    scholar = "scholar"
    unknown = "unknown"


class AnuyogaKind(str, enum.Enum):
    prathmanuyoga = "prathmanuyoga"
    karananuyoga = "karananuyoga"
    charananuyoga = "charananuyoga"
    dravyanuyoga = "dravyanuyoga"


class IngestionSource(str, enum.Enum):
    jainkosh = "jainkosh"
    nj = "nj"
    vyakaran_vishleshan = "vyakaran_vishleshan"
    cataloguesearch = "cataloguesearch"
    cataloguesearch_chat = "cataloguesearch-chat"


class IngestionRunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    partial = "partial"
    failed = "failed"
    cancelled = "cancelled"


class CandidateStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    merged = "merged"


author_kind_sa = SAEnum(AuthorKind, name="author_kind", create_type=False)
anuyoga_kind_sa = SAEnum(AnuyogaKind, name="anuyoga_kind", create_type=False)
ingestion_source_sa = SAEnum(IngestionSource, name="ingestion_source", create_type=False)
ingestion_run_status_sa = SAEnum(IngestionRunStatus, name="ingestion_run_status", create_type=False)
candidate_status_sa = SAEnum(CandidateStatus, name="candidate_status", create_type=False)
