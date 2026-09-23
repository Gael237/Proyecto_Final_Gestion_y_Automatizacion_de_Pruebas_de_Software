def crear_autobus(client, placa="ABC123", capacidad=2):
    return client.post("/autobuses/", json={"placa": placa, "chofer": "Luis", "capacidad": capacidad})

def crear_viaje(client, autobus_id):
    return client.post("/viajes/", json={
        "origen": "CDMX", "destino": "GDL",
        "fecha_salida": "2027-01-01T10:00:00", "precio": 350, "autobus_id": autobus_id
    })

def test_flujo_completo_venta_boleto(client):
    autobus_id = crear_autobus(client).json()["id"]
    viaje_id = crear_viaje(client, autobus_id).json()["id"]

    r = client.post("/boletos/", json={"viaje_id": viaje_id, "asiento": 1, "pasajero": "Ana"})
    assert r.status_code == 201

def test_asiento_duplicado_devuelve_409(client):
    autobus_id = crear_autobus(client).json()["id"]
    viaje_id = crear_viaje(client, autobus_id).json()["id"]
    client.post("/boletos/", json={"viaje_id": viaje_id, "asiento": 1, "pasajero": "Ana"})

    r = client.post("/boletos/", json={"viaje_id": viaje_id, "asiento": 1, "pasajero": "Beto"})
    assert r.status_code == 409  # antes era 404, contrato incorrecto

def test_asiento_excede_capacidad(client):
    autobus_id = crear_autobus(client, capacidad=1).json()["id"]
    viaje_id = crear_viaje(client, autobus_id).json()["id"]

    r = client.post("/boletos/", json={"viaje_id": viaje_id, "asiento": 5, "pasajero": "Ana"})
    assert r.status_code == 400

def test_viaje_inexistente_en_boletos_devuelve_404(client):
    r = client.get("/viajes/9999/boletos")
    assert r.status_code == 404

def test_boletos_vendidos_lista_vacia_devuelve_200(client):
    autobus_id = crear_autobus(client, placa="XYZ999").json()["id"]
    viaje_id = crear_viaje(client, autobus_id).json()["id"]

    r = client.get(f"/viajes/{viaje_id}/boletos")
    assert r.status_code == 200
    assert r.json() == []  # antes era 404, ahora es correcto

def test_placa_duplicada_devuelve_400(client):
    crear_autobus(client, placa="REPETIDA")
    r = crear_autobus(client, placa="REPETIDA")
    assert r.status_code == 400