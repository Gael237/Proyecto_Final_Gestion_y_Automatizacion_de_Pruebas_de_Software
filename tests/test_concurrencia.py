import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database import Base, get_db
from main import app


@pytest.fixture()
def client_concurrente():
    # Usamos un archivo temporal en vez de :memory: para permitir
    # conexiones concurrentes reales entre hilos (como en producción).
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

    engine.dispose()
    os.close(db_fd)
    os.remove(db_path)


def test_no_sobreventa_bajo_concurrencia(client_concurrente):
    client = client_concurrente

    autobus_id = client.post("/autobuses/", json={
        "placa": "CONC001", "chofer": "Luis", "capacidad": 10
    }).json()["id"]
    viaje_id = client.post("/viajes/", json={
        "origen": "CDMX", "destino": "MTY", "fecha_salida": "2027-01-01T10:00:00",
        "precio": 500, "autobus_id": autobus_id
    }).json()["id"]

    def vender(pasajero):
        return client.post("/boletos/", json={
            "viaje_id": viaje_id, "asiento": 1, "pasajero": pasajero
        })

    with ThreadPoolExecutor(max_workers=5) as executor:
        resultados = list(executor.map(vender, [f"Pasajero{i}" for i in range(5)]))

    exitosos = [r for r in resultados if r.status_code == 201]
    conflictos = [r for r in resultados if r.status_code == 409]

    assert len(exitosos) == 1, f"Se esperaba 1 venta exitosa, hubo {len(exitosos)}"
    assert len(conflictos) == 4, f"Se esperaban 4 conflictos 409, hubo {len(conflictos)}"