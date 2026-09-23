from pydantic import BaseModel, Field, field_validator
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from database import get_db
from modelos import Autobus, Viaje, Boleto
from datetime import datetime

app = FastAPI()

class AutobusCrear(BaseModel):
    placa: str
    chofer: str
    capacidad: int = Field(gt=0, description="Debe ser mayor a 0")

class ViajeCrear(BaseModel):
    origen: str
    destino: str
    fecha_salida: datetime
    precio: float = Field(gt=0)
    autobus_id: int

    @field_validator("fecha_salida")
    @classmethod
    def fecha_no_pasada(cls, v):
        if v < datetime.now():
            raise ValueError("fecha_salida no puede ser en el pasado")
        return v

class BoletoCrear(BaseModel):
    viaje_id: int
    asiento: int = Field(gt=0, description="El asiento debe ser mayor a 0")
    pasajero: str


@app.post("/autobuses/")
def agregar_autobus(autobus: AutobusCrear, db: Session = Depends(get_db)):
    existe = db.query(Autobus).filter(Autobus.placa == autobus.placa).first()
    if existe:
        raise HTTPException(status_code=400, detail="Esta placa ya está registrada")
    nuevo = Autobus(placa=autobus.placa, chofer=autobus.chofer, capacidad=autobus.capacidad)
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@app.post("/viajes/")
def agregar_viaje(viaje: ViajeCrear, db: Session = Depends(get_db)):
    autobus_existe = db.query(Autobus).filter(Autobus.id == viaje.autobus_id).first()
    if not autobus_existe:
        raise HTTPException(status_code=404, detail="El autobus no existe")
    nuevo_viaje = Viaje(
        origen=viaje.origen, destino=viaje.destino, fecha_salida=viaje.fecha_salida,
        precio=viaje.precio, autobus_id=viaje.autobus_id
    )
    db.add(nuevo_viaje)
    db.commit()
    db.refresh(nuevo_viaje)
    return nuevo_viaje


@app.post("/boletos/", status_code=201)
def vender_boleto(boleto: BoletoCrear, db: Session = Depends(get_db)):
    viaje = db.query(Viaje).filter(Viaje.id == boleto.viaje_id).first()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    capacidad = viaje.autobus.capacidad
    if boleto.asiento > capacidad:
        raise HTTPException(status_code=400, detail="El asiento excede la capacidad del autobús")

    nuevo_boleto = Boleto(viaje_id=boleto.viaje_id, asiento=boleto.asiento, pasajero=boleto.pasajero)
    db.add(nuevo_boleto)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Asiento ya ocupado")
    db.refresh(nuevo_boleto)
    return nuevo_boleto


@app.get("/viajes/")
def listar_viajes(db: Session = Depends(get_db)):
    return db.query(Viaje).all()


@app.get("/viajes/{viaje_id}/boletos")
def boletos_vendidos(viaje_id: int, db: Session = Depends(get_db)):
    viaje_existe = db.query(Viaje).filter(Viaje.id == viaje_id).first()
    if not viaje_existe:
        raise HTTPException(status_code=404, detail="El viaje no existe")
    return db.query(Boleto).filter(Boleto.viaje_id == viaje_id).all()  # lista vacía -> 200 []


@app.get("/buscar_viaje/")
def buscar_viajes(origen: str, destino: str, db: Session = Depends(get_db)):
    viajes = db.query(Viaje).filter(Viaje.origen == origen, Viaje.destino == destino).all()
    return viajes  # lista vacía -> 200 [] (no 404)