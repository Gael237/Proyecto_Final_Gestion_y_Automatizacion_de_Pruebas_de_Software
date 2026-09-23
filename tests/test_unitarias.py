import pytest
from pydantic import ValidationError
from main import BoletoCrear, AutobusCrear, ViajeCrear
from datetime import datetime, timedelta

def test_asiento_negativo_invalido():
    with pytest.raises(ValidationError):
        BoletoCrear(viaje_id=1, asiento=-1, pasajero="Juan")

def test_asiento_cero_invalido():
    with pytest.raises(ValidationError):
        BoletoCrear(viaje_id=1, asiento=0, pasajero="Juan")

def test_asiento_positivo_valido():
    b = BoletoCrear(viaje_id=1, asiento=5, pasajero="Juan")
    assert b.asiento == 5

def test_capacidad_cero_invalida():
    with pytest.raises(ValidationError):
        AutobusCrear(placa="ABC123", chofer="Luis", capacidad=0)

def test_fecha_pasada_invalida():
    with pytest.raises(ValidationError):
        ViajeCrear(
            origen="CDMX", destino="GDL",
            fecha_salida=datetime.now() - timedelta(days=1),
            precio=300, autobus_id=1
        )

def test_fecha_futura_valida():
    v = ViajeCrear(
        origen="CDMX", destino="GDL",
        fecha_salida=datetime.now() + timedelta(days=1),
        precio=300, autobus_id=1
    )
    assert v.precio == 300