from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Response
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

# Configura logs para vermos no 'fly logs'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Inicializa o banco
db.init_db()

app = FastAPI()
DEFAULT_USER_ID = "01"

# Pydantic Models mais flexíveis para evitar Erro 500
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

@app.get("/api/markers", response_model=List[MarkerResponse])
def get_markers(session: Session = Depends(get_db)):
    return session.query(db.Marker).all()

@app.post("/api/markers", response_model=MarkerResponse)
def create_marker(marker: MarkerBase, session: Session = Depends(get_db)):
    name_upper = marker.name.strip().upper()
    db_marker = session.query(db.Marker).filter(db.Marker.name == name_upper).first()
    if db_marker:
        db_marker.min_value = marker.min_value
        db_marker.max_value = marker.max_value
    else:
        db_marker = db.Marker(name=name_upper, min_value=marker.min_value, max_value=marker.max_value)
        session.add(db_marker)
    session.commit()
    session.refresh(db_marker)
    return db_marker

@app.put("/api/markers/{marker_id}", response_model=MarkerResponse)
def update_marker(marker_id: int, marker_data: MarkerBase, session: Session = Depends(get_db)):
    db_marker = session.query(db.Marker).filter(db.Marker.id == marker_id).first()
    if not db_marker:
        raise HTTPException(status_code=404, detail="Marcador não encontrado")
    
    new_name = marker_data.name.strip().upper()
    old_name = db_marker.name
    
    # Se o nome mudou, precisamos atualizar os registros vinculados
    if new_name != old_name:
        # Verifica se o novo nome já existe em outro ID
        existing = session.query(db.Marker).filter(db.Marker.name == new_name).first()
        if existing:
            raise HTTPException(status_code=400, detail="Já existe outro marcador com este nome")
        
        # Atualiza o nome no marcador
        db_marker.name = new_name
        # Cascata manual para exam_records (caso o SQLite não esteja configurado para tal)
        session.query(db.ExamRecord).filter(db.ExamRecord.marker_name == old_name).update(
            {db.ExamRecord.marker_name: new_name},
            synchronize_session=False
        )
    
    db_marker.min_value = marker_data.min_value
    db_marker.max_value = marker_data.max_value
    
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

@app.get("/api/exams", response_model=List[ExamResponse])
def get_exams(session: Session = Depends(get_db)):
    # Traz todos os exames para diagnosticar o que há no banco
    exams = session.query(db.ExamRecord).order_by(db.ExamRecord.date.desc()).all()
    logger.info(f"Total de exames encontrados no banco: {len(exams)}")
    return exams

@app.post("/api/exams", response_model=ExamResponse)
def create_exam(exam: ExamCreate, session: Session = Depends(get_db)):
    marker_name_upper = exam.marker_name.strip().upper()
    marker = session.query(db.Marker).filter(db.Marker.name == marker_name_upper).first()
    if not marker:
        raise HTTPException(status_code=404, detail="Marcador não cadastrado")
    
    db_exam = db.ExamRecord(
        date=exam.date,
        marker_name=marker_name_upper,
        value=exam.value,
        user_id=DEFAULT_USER_ID
    )
    session.add(db_exam)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Erro ao salvar exame: {e}")
        # Tenta sem user_id como último recurso
        db_exam.user_id = None
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

@app.post("/api/exams/bulk-update-marker")
def bulk_update_marker(data: BulkUpdateMarker, session: Session = Depends(get_db)):
    new_marker = session.query(db.Marker).filter(db.Marker.name == data.new_marker_name.upper()).first()
    if not new_marker:
        raise HTTPException(status_code=404, detail="Marcador de destino não encontrado")
    
    session.query(db.ExamRecord).filter(db.ExamRecord.id.in_(data.exam_ids)).update(
        {db.ExamRecord.marker_name: data.new_marker_name.upper()},
        synchronize_session=False
    )
    session.commit()
    return {"status": "ok", "updated_count": len(data.exam_ids)}

@app.post("/api/import-csv")
async def import_csv(file: UploadFile = File(...), session: Session = Depends(get_db)):
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
        marker = session.query(db.Marker).filter(db.Marker.name == marker_name).first()
        if not marker:
            marker = db.Marker(name=marker_name)
            session.add(marker)
            session.commit()
        
        new_record = db.ExamRecord(
            date=str(row['data']).strip(),
            marker_name=marker_name,
            value=float(row['valor']),
            user_id=DEFAULT_USER_ID
        )
        session.add(new_record)
        count += 1
    
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Erro no commit do CSV: {e}")
        raise HTTPException(status_code=500, detail="Erro ao salvar dados no banco")
        
    return {"status": "ok", "imported": count}

@app.post("/api/import-json")
async def import_json(file: UploadFile = File(...), session: Session = Depends(get_db)):
    content = await file.read()
    try:
        import json
        data = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao ler JSON: {e}")

    # Importar Marcadores
    markers_count = 0
    if "markers" in data:
        for m in data["markers"]:
            name_upper = m["name"].strip().upper()
            db_marker = session.query(db.Marker).filter(db.Marker.name == name_upper).first()
            if db_marker:
                db_marker.min_value = m.get("min_value")
                db_marker.max_value = m.get("max_value")
            else:
                db_marker = db.Marker(name=name_upper, min_value=m.get("min_value"), max_value=m.get("max_value"))
                session.add(db_marker)
            markers_count += 1
        session.commit()

    # Importar Exames
    exams_count = 0
    if "exams" in data:
        for e in data["exams"]:
            marker_name_upper = e["marker_name"].strip().upper()
            # Verifica se já existe um registro idêntico para evitar duplicatas simples
            exists = session.query(db.ExamRecord).filter(
                db.ExamRecord.date == e["date"],
                db.ExamRecord.marker_name == marker_name_upper,
                db.ExamRecord.value == e["value"]
            ).first()
            
            if not exists:
                new_exam = db.ExamRecord(
                    date=e["date"],
                    marker_name=marker_name_upper,
                    value=e["value"],
                    user_id=DEFAULT_USER_ID
                )
                session.add(new_exam)
                exams_count += 1
        session.commit()

    return {"status": "ok", "markers_imported": markers_count, "exams_imported": exams_count}

@app.delete("/api/danger-reset-db")
def reset_db(session: Session = Depends(get_db)):
    db.Base.metadata.drop_all(bind=db.engine)
    db.Base.metadata.create_all(bind=db.engine)
    db.init_db()
    return {"status": "banco resetado"}

@app.get("/api/export-json")
def export_json(session: Session = Depends(get_db)):
    markers = session.query(db.Marker).all()
    exams = session.query(db.ExamRecord).all()
    
    data = {
        "markers": [{"name": m.name, "min_value": m.min_value, "max_value": m.max_value} for m in markers],
        "exams": [{"date": e.date, "marker_name": e.marker_name, "value": e.value} for e in exams]
    }
    return JSONResponse(
        content=data, 
        headers={"Content-Disposition": "attachment; filename=blood_exams_backup.json"}
    )

@app.get("/api/export-csv")
def export_csv(session: Session = Depends(get_db)):
    exams = session.query(db.ExamRecord).all()
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
