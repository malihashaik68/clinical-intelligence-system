from sqlalchemy import Column, Integer, Text
from backend.app.db.database import Base


class ClinicalRecord(Base):
    __tablename__ = "clinical_records"

    id = Column(Integer, primary_key=True, index=True)
    clinical_note = Column(Text)
    extracted_entities = Column(Text)
    api_results = Column(Text)