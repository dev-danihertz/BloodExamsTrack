from sqlalchemy import Column, Integer, String, Float, ForeignKey, create_engine, text, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, foreign
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
    
    user = relationship("User", back_populates="markers")

class ExamRecord(Base):
    __tablename__ = "exam_records"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(String)
    marker_name = Column(String)
    value = Column(Float)
    user_id = Column(String, ForeignKey("users.id"))
    
    user = relationship("User", back_populates="records")

Base.metadata.create_all(bind=engine)

def init_db():
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    
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
            {"id": "01", "name": "DANHERTZ", "password": "drh-1985"},
            {"id": "02", "name": "GISIHERTZ", "password": "gbh-1986"}
        ]
        
        for u_data in default_users:
            user = db.query(User).filter(User.name == u_data["name"]).first()
            if not user:
                hashed_pw = pwd_context.hash(u_data["password"])
                user = User(id=u_data["id"], name=u_data["name"], password=hashed_pw)
                db.add(user)
            else:
                hashed_pw = pwd_context.hash(u_data["password"])
                user.password = hashed_pw
        
        db.commit()
        
        # Vincula exames órfãos ao usuário 01 (DanHertz)
        db.execute(text("UPDATE exam_records SET user_id = '01' WHERE user_id IS NULL"))
        # Vincula marcadores órfãos ao usuário 01
        db.execute(text("UPDATE markers SET user_id = '01' WHERE user_id IS NULL"))
        db.commit()
    except Exception as e:
        import traceback
        print(f"Erro na migração detalhado: {e}")
        traceback.print_exc()
    finally:
        db.close()
