from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import List, Optional
import database as db
from pydantic import BaseModel
import pandas as pd
import io

app = FastAPI()

# Pydantic Models
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

class ExamResponse(ExamCreate):
    id: int
    class Config: from_attributes = True

# DB Dependency
def get_db():
    database = db.SessionLocal()
    try:
        yield database
    finally:
        database.close()

# Marker Endpoints
@app.get("/api/markers", response_model=List[MarkerResponse])
def get_markers(session: Session = Depends(get_db)):
    return session.query(db.Marker).all()

@app.post("/api/markers", response_model=MarkerResponse)
def create_marker(marker: MarkerBase, session: Session = Depends(get_db)):
    db_marker = session.query(db.Marker).filter(db.Marker.name == marker.name).first()
    if db_marker:
        db_marker.min_value = marker.min_value
        db_marker.max_value = marker.max_value
    else:
        db_marker = db.Marker(**marker.dict())
        session.add(db_marker)
    session.commit()
    session.refresh(db_marker)
    return db_marker

@app.delete("/api/markers/{marker_id}")
def delete_marker(marker_id: int, session: Session = Depends(get_db)):
    marker = session.query(db.Marker).filter(db.Marker.id == marker_id).first()
    if marker:
        session.delete(marker)
        session.commit()
    return {"status": "ok"}

# Exam Endpoints
@app.get("/api/exams", response_model=List[ExamResponse])
def get_exams(session: Session = Depends(get_db)):
    return session.query(db.ExamRecord).order_by(db.ExamRecord.date.desc()).all()

@app.post("/api/exams", response_model=ExamResponse)
def create_exam(exam: ExamCreate, session: Session = Depends(get_db)):
    marker = session.query(db.Marker).filter(db.Marker.name == exam.marker_name).first()
    if not marker:
        raise HTTPException(status_code=404, detail="Marcador não cadastrado")
    db_exam = db.ExamRecord(**exam.dict())
    session.add(db_exam)
    session.commit()
    session.refresh(db_exam)
    return db_exam

@app.put("/api/exams/{exam_id}", response_model=ExamResponse)
def update_exam(exam_id: int, exam: ExamCreate, session: Session = Depends(get_db)):
    db_exam = session.query(db.ExamRecord).filter(db.ExamRecord.id == exam_id).first()
    if not db_exam:
        raise HTTPException(status_code=404, detail="Exame não encontrado")
    for key, value in exam.dict().items():
        setattr(db_exam, key, value)
    session.commit()
    session.refresh(db_exam)
    return db_exam

@app.delete("/api/exams/{exam_id}")
def delete_exam(exam_id: int, session: Session = Depends(get_db)):
    db_exam = session.query(db.ExamRecord).filter(db.ExamRecord.id == exam_id).first()
    if db_exam:
        session.delete(db_exam)
        session.commit()
    return {"status": "ok"}

# CSV Import
@app.post("/api/import-csv")
async def import_csv(file: UploadFile = File(...), session: Session = Depends(get_db)):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    required_columns = ['data', 'marcador', 'valor']
    if not all(col in df.columns for col in required_columns):
        raise HTTPException(status_code=400, detail="Colunas do CSV devem ser: data, marcador, valor")
    
    count = 0
    for _, row in df.iterrows():
        marker_name = str(row['marcador']).strip()
        marker = session.query(db.Marker).filter(db.Marker.name == marker_name).first()
        if not marker:
            marker = db.Marker(name=marker_name)
            session.add(marker)
            session.commit()
            session.refresh(marker)
        
        new_record = db.ExamRecord(
            date=str(row['data']).strip(),
            marker_name=marker_name,
            value=float(row['valor'])
        )
        session.add(new_record)
        count += 1
    session.commit()
    return {"status": "ok", "imported": count}

# Serve static files
@app.get("/")
def read_index():
    return FileResponse("static/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
