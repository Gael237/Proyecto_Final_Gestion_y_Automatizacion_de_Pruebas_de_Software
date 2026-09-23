from database import Base, engine
from modelos import Autobus, Viaje, Boleto

Base.metadata.create_all(bind=engine)