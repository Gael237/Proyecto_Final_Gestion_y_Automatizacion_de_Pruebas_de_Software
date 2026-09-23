from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base

class Autobus(Base):
    __tablename__ = "autobuses"
    id = Column(Integer, primary_key=True, index=True)
    placa = Column(String, unique=True)
    chofer = Column(String)
    capacidad = Column(Integer)
    viajes = relationship("Viaje", back_populates="autobus")

class Viaje(Base):
    __tablename__ = "viajes"
    id = Column(Integer, primary_key=True, index=True)
    origen = Column(String)
    destino = Column(String)
    fecha_salida = Column(DateTime)
    precio = Column(Float)
    autobus_id = Column(Integer, ForeignKey("autobuses.id"))
    autobus = relationship("Autobus", back_populates="viajes")
    boletos = relationship("Boleto", back_populates="viaje")

class Boleto(Base):
    __tablename__ = "boletos"
    __table_args__ = (UniqueConstraint("viaje_id", "asiento", name="uq_viaje_asiento"),)
    id = Column(Integer, primary_key=True, index=True)
    asiento = Column(Integer)
    pasajero = Column(String)
    viaje_id = Column(Integer, ForeignKey("viajes.id"))
    viaje = relationship("Viaje", back_populates="boletos")