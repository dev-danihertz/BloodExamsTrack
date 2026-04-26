from sqlalchemy import Column, Integer, String, Float, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./blood_exams.db")

engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Marker(Base):
    __tablename__ = "markers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    records = relationship("ExamRecord", back_populates="marker", cascade="all, delete-orphan")

class ExamRecord(Base):
    __tablename__ = "exam_records"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String)
    marker_name = Column(String, ForeignKey("markers.name"))
    value = Column(Float)
    
    marker = relationship("Marker", back_populates="records")

Base.metadata.drop_all(bind=engine) # Limpando para garantir nova estrutura
Base.metadata.create_all(bind=engine)
