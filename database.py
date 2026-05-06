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
    name = Column(String, unique=True)
    password = Column(String) # Hash da senha
    records = relationship("ExamRecord", back_populates="user")
    markers = relationship("Marker", back_populates="user")

class Marker(Base):
    __tablename__ = "markers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)
    user_id = Column(String, ForeignKey("users.id"))
    
    records = relationship("ExamRecord", back_populates="marker")
    user = relationship("User", back_populates="markers")

class ExamRecord(Base):
    __tablename__ = "exam_records"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String)
    marker_name = Column(String) # Removido ForeignKey direto para permitir nomes iguais em users diferentes
    value = Column(Float)
    user_id = Column(String, ForeignKey("users.id"))
    
    user = relationship("User", back_populates="records")
    # Relacionamento manual ou via query no main.py, já que marker_name não é mais unique globalmente
    marker = relationship("Marker", primaryjoin="and_(ExamRecord.marker_name==Marker.name, ExamRecord.user_id==Marker.user_id)", foreign_keys=[marker_name, user_id], overlaps="records,user")

Base.metadata.create_all(bind=engine)

def init_db():
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    
    with engine.connect() as conn:
        # Migrações de colunas
        try: conn.execute(text("ALTER TABLE users ADD COLUMN password VARCHAR")); conn.commit()
        except Exception: pass
        
        try: conn.execute(text("ALTER TABLE markers ADD COLUMN user_id VARCHAR")); conn.commit()
        except Exception: pass

    db = SessionLocal()
    try:
        # Usuários padrão
        default_users = [
            {"id": "01", "name": "DANHERTZ", "password": "1234"},
            {"id": "02", "name": "GISIHERTZ", "password": "1234"}
        ]
        
        for u_data in default_users:
            user = db.query(User).filter(User.name == u_data["name"]).first()
            if not user:
                user = User(id=u_data["id"], name=u_data["name"], password=pwd_context.hash(u_data["password"]))
                db.add(user)
            elif not user.password:
                user.password = pwd_context.hash(u_data["password"])
        
        db.commit()
        
        # Vincula exames órfãos ao usuário 01 (DanHertz)
        db.execute(text("UPDATE exam_records SET user_id = '01' WHERE user_id IS NULL"))
        # Vincula marcadores órfãos ao usuário 01
        db.execute(text("UPDATE markers SET user_id = '01' WHERE user_id IS NULL"))
        db.commit()
    except Exception as e:
        print(f"Erro na migração: {e}")
    finally:
        db.close()
