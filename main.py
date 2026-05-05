from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Response, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional
import database as db
from pydantic import BaseModel
import pandas as pd
import io
import logging
import uuid
from passlib.context import CryptContext

# Segurança
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Configura logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializa o banco
db.init_db()

app = FastAPI()

# Pydantic Models
class UserLogin(BaseModel):
    name: str
    password: str

class UserCreate(BaseModel):
    name: str
    password: str

class MarkerBase(BaseModel):
    name: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None

class MarkerResponse(MarkerBase):
    id: int
    class Config: from_attributes = True

class ExamCreate(BaseModel):
    date: str
    marker_name: str
    value: float

class ExamResponse(BaseModel):
    id: int
    date: Optional[str] = None
    marker_name: Optional[str] = None
    value: Optional[float] = None
    user_id: Optional[str] = None
    class Config: from_attributes = True

class BulkUpdateMarker(BaseModel):
    exam_ids: List[int]
    new_marker_name: str

# DB Dependency
def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

# Auth Dependency
def get_current_user_id(x_user_id: Optional[str] = Header(None)):
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Usuário não autenticado")
    return x_user_id

@app.post("/api/login")
def login(data: UserLogin, session: Session = Depends(get_db)):
    user = session.query(db.User).filter(db.User.name == data.name.upper()).first()
    if not user or not pwd_context.verify(data.password, user.password):
        raise HTTPException(status_code=401, detail="Usuário ou senha inválidos")
    return {"user_id": user.id, "name": user.name}

@app.post("/api/register")
def register(data: UserCreate, session: Session = Depends(get_db)):
    name_upper = data.name.strip().upper()
    existing = session.query(db.User).filter(db.User.name == name_upper).first()
    if existing:
        raise HTTPException(status_code=400, detail="Este nome de usuário já existe")
    
    new_user = db.User(
        id=str(uuid.uuid4()),
        name=name_upper,
        password=pwd_context.hash(data.password)
    )
    session.add(new_user)
    session.commit()
    return {"status": "ok", "user_id": new_user.id}

@app.get("/api/markers", response_model=List[MarkerResponse])
def get_markers(session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return session.query(db.Marker).filter(db.Marker.user_id == user_id).all()

@app.post("/api/markers", response_model=MarkerResponse)
def create_marker(marker: MarkerBase, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    name_upper = marker.name.strip().upper()
    db_marker = session.query(db.Marker).filter(db.Marker.name == name_upper, db.Marker.user_id == user_id).first()
    if db_marker:
        db_marker.min_value = marker.min_value
        db_marker.max_value = marker.max_value
    else:
        db_marker = db.Marker(name=name_upper, min_value=marker.min_value, max_value=marker.max_value, user_id=user_id)
        session.add(db_marker)
    session.commit()
    session.refresh(db_marker)
    return db_marker

@app.put("/api/markers/{marker_id}", response_model=MarkerResponse)
def update_marker(marker_id: int, marker_data: MarkerBase, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    db_marker = session.query(db.Marker).filter(db.Marker.id == marker_id, db.Marker.user_id == user_id).first()
    if not db_marker:
        raise HTTPException(status_code=404, detail="Marcador não encontrado")
    
    new_name = marker_data.name.strip().upper()
    old_name = db_marker.name
    
    if new_name != old_name:
        existing = session.query(db.Marker).filter(db.Marker.name == new_name, db.Marker.user_id == user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Já existe outro marcador com este nome")
        
        db_marker.name = new_name
        session.query(db.ExamRecord).filter(db.ExamRecord.marker_name == old_name, db.ExamRecord.user_id == user_id).update(
            {db.ExamRecord.marker_name: new_name},
            synchronize_session=False
        )
    
    db_marker.min_value = marker_data.min_value
    db_marker.max_value = marker_data.max_value
    
    session.commit()
    session.refresh(db_marker)
    return db_marker

@app.delete("/api/markers/{marker_id}")
def delete_marker(marker_id: int, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    marker = session.query(db.Marker).filter(db.Marker.id == marker_id, db.Marker.user_id == user_id).first()
    if marker:
        # Excluir exames vinculados também
        session.query(db.ExamRecord).filter(db.ExamRecord.marker_name == marker.name, db.ExamRecord.user_id == user_id).delete()
        session.delete(marker)
        session.commit()
    return {"status": "ok"}

@app.get("/api/exams", response_model=List[ExamResponse])
def get_exams(session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    return session.query(db.ExamRecord).filter(db.ExamRecord.user_id == user_id).order_by(db.ExamRecord.date.desc()).all()

@app.post("/api/exams", response_model=ExamResponse)
def create_exam(exam: ExamCreate, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    marker_name_upper = exam.marker_name.strip().upper()
    marker = session.query(db.Marker).filter(db.Marker.name == marker_name_upper, db.Marker.user_id == user_id).first()
    if not marker:
        raise HTTPException(status_code=404, detail="Marcador não cadastrado")
    
    db_exam = db.ExamRecord(
        date=exam.date,
        marker_name=marker_name_upper,
        value=exam.value,
        user_id=user_id
    )
    session.add(db_exam)
    session.commit()
    session.refresh(db_exam)
    return db_exam

@app.put("/api/exams/{exam_id}", response_model=ExamResponse)
def update_exam(exam_id: int, exam: ExamCreate, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    db_exam = session.query(db.ExamRecord).filter(db.ExamRecord.id == exam_id, db.ExamRecord.user_id == user_id).first()
    if not db_exam:
        raise HTTPException(status_code=404, detail="Exame não encontrado")
    
    db_exam.date = exam.date
    db_exam.marker_name = exam.marker_name.strip().upper()
    db_exam.value = exam.value
    
    session.commit()
    session.refresh(db_exam)
    return db_exam

@app.delete("/api/exams/{exam_id}")
def delete_exam(exam_id: int, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    db_exam = session.query(db.ExamRecord).filter(db.ExamRecord.id == exam_id, db.ExamRecord.user_id == user_id).first()
    if db_exam:
        session.delete(db_exam)
        session.commit()
    return {"status": "ok"}

@app.post("/api/exams/bulk-update-marker")
def bulk_update_marker(data: BulkUpdateMarker, session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    new_marker = session.query(db.Marker).filter(db.Marker.name == data.new_marker_name.upper(), db.Marker.user_id == user_id).first()
    if not new_marker:
        raise HTTPException(status_code=404, detail="Marcador de destino não encontrado")
    
    session.query(db.ExamRecord).filter(db.ExamRecord.id.in_(data.exam_ids), db.ExamRecord.user_id == user_id).update(
        {db.ExamRecord.marker_name: data.new_marker_name.upper()},
        synchronize_session=False
    )
    session.commit()
    return {"status": "ok", "updated_count": len(data.exam_ids)}

@app.post("/api/import-csv")
async def import_csv(file: UploadFile = File(...), session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler CSV: {e}")

    required_columns = ['data', 'marcador', 'valor']
    if not all(col in df.columns for col in required_columns):
        raise HTTPException(status_code=400, detail="Colunas do CSV devem ser: data, marcador, valor")
    
    count = 0
    for _, row in df.iterrows():
        marker_name = str(row['marcador']).strip().upper()
        marker = session.query(db.Marker).filter(db.Marker.name == marker_name, db.Marker.user_id == user_id).first()
        if not marker:
            marker = db.Marker(name=marker_name, user_id=user_id)
            session.add(marker)
            session.commit()
        
        new_record = db.ExamRecord(
            date=str(row['data']).strip(),
            marker_name=marker_name,
            value=float(row['valor']),
            user_id=user_id
        )
        session.add(new_record)
        count += 1
    
    session.commit()
    return {"status": "ok", "imported": count}

@app.post("/api/import-json")
async def import_json(file: UploadFile = File(...), session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    content = await file.read()
    try:
        import json
        data = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler JSON: {e}")

    markers_count = 0
    if "markers" in data:
        for m in data["markers"]:
            name_upper = m["name"].strip().upper()
            db_marker = session.query(db.Marker).filter(db.Marker.name == name_upper, db.Marker.user_id == user_id).first()
            if db_marker:
                db_marker.min_value = m.get("min_value")
                db_marker.max_value = m.get("max_value")
            else:
                db_marker = db.Marker(name=name_upper, min_value=m.get("min_value"), max_value=m.get("max_value"), user_id=user_id)
                session.add(db_marker)
            markers_count += 1
        session.commit()

    exams_count = 0
    if "exams" in data:
        for e in data["exams"]:
            marker_name_upper = e["marker_name"].strip().upper()
            exists = session.query(db.ExamRecord).filter(
                db.ExamRecord.date == e["date"],
                db.ExamRecord.marker_name == marker_name_upper,
                db.ExamRecord.value == e["value"],
                db.ExamRecord.user_id == user_id
            ).first()
            
            if not exists:
                new_exam = db.ExamRecord(
                    date=e["date"],
                    marker_name=marker_name_upper,
                    value=e["value"],
                    user_id=user_id
                )
                session.add(new_exam)
                exams_count += 1
        session.commit()

    return {"status": "ok", "markers_imported": markers_count, "exams_imported": exams_count}

@app.delete("/api/danger-reset-db")
def reset_db(session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    # Reseta apenas os dados do usuário logado
    session.query(db.ExamRecord).filter(db.ExamRecord.user_id == user_id).delete()
    session.query(db.Marker).filter(db.Marker.user_id == user_id).delete()
    session.commit()
    return {"status": "dados do usuário resetados"}

@app.get("/api/export-json")
def export_json(session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    markers = session.query(db.Marker).filter(db.Marker.user_id == user_id).all()
    exams = session.query(db.ExamRecord).filter(db.ExamRecord.user_id == user_id).all()
    
    data = {
        "markers": [{"name": m.name, "min_value": m.min_value, "max_value": m.max_value} for m in markers],
        "exams": [{"date": e.date, "marker_name": e.marker_name, "value": e.value} for e in exams]
    }
    return JSONResponse(
        content=data, 
        headers={"Content-Disposition": "attachment; filename=blood_exams_backup.json"}
    )

@app.get("/api/export-csv")
def export_csv(session: Session = Depends(get_db), user_id: str = Depends(get_current_user_id)):
    exams = session.query(db.ExamRecord).filter(db.ExamRecord.user_id == user_id).all()
    df = pd.DataFrame([
        {"data": e.date, "marcador": e.marker_name, "valor": e.value} 
        for e in exams
    ])
    
    output = io.StringIO()
    df.to_csv(output, index=False)
    
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=blood_exams.csv"}
    )

@app.get("/")
def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
