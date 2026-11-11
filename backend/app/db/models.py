from sqlalchemy import Column, Integer, Text, DateTime
from datetime import datetime, timezone
from backend.app.db.database import Base


class ClinicalRecord(Base):
    __tablename__ = "clinical_records"

    id = Column(Integer, primary_key=True, index=True)
    clinical_note = Column(Text, nullable=False)
    extracted_entities = Column(Text, nullable=False)
    api_results = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)