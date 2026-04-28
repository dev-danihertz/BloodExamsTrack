from sqlalchemy import Column, Integer, String, Float, ForeignKey, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./blood_exams.db")

engine = create_engine(DB_PATH, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    name = Column(String)
    records = relationship("ExamRecord", back_populates="user")

class Marker(Base):
    __tablename__ = "markers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    records = relationship("ExamRecord", back_populates="marker")

class ExamRecord(Base):
    __tablename__ = "exam_records"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String)
    marker_name = Column(String, ForeignKey("markers.name"))
    value = Column(Float)
    user_id = Column(String, ForeignKey("users.id"), nullable=True) # Permitir nulo temporariamente
    
    marker = relationship("Marker", back_populates="records")
    user = relationship("User", back_populates="records")

Base.metadata.create_all(bind=engine)

def init_db():
    # Tenta adicionar a coluna. Se falhar, segue em frente.
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE exam_records ADD COLUMN user_id VARCHAR"))
            conn.commit()
        except Exception:
            pass

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == "01").first()
        if not user:
            user = User(id="01", name="DanHertz")
            db.add(user)
            db.commit()
        
        # Tenta vincular o que for possível
        db.execute(text("UPDATE exam_records SET user_id = '01' WHERE user_id IS NULL"))
        db.commit()
    except Exception:
        pass
    finally:
        db.close()
