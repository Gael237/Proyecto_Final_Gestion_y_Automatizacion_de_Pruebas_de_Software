# La Boletera - Bus Booking API

## Caso de estudio
Backend REST (FastAPI + SQLAlchemy + SQLite) para venta de boletos de autobús. El
módulo crítico es la venta de boletos (`POST /boletos/`), que originalmente tenía
tres riesgos de calidad: una condición de carrera que permitía sobreventa del mismo
asiento, un contrato HTTP inconsistente (códigos `404` donde debían ser `409` o
`200 []`) y falta de validación de valores límite (capacidad, asiento, fecha).

## Objetivo e hipótesis
**Objetivo general:** dotar al módulo de venta de boletos de una suite de pruebas
automatizadas (caja blanca y caja negra) que detecte y prevenga regresiones sobre
los riesgos identificados, integrada a un pipeline de CI.

**Hipótesis de testing:** si se implementan pruebas unitarias sobre los validadores,
pruebas de integración sobre el contrato HTTP, una prueba de concurrencia dirigida y
pruebas de API (Postman/Newman) que verifiquen el contrato desde afuera, entonces los
riesgos de la matriz quedarán cubiertos y cualquier regresión futura será detectada
sin depender de pruebas manuales exploratorias.

Detalle completo, evolución del caso, decisiones técnicas y evidencia de ejecución:
ver [docs/portafolio.md](./docs/portafolio.md).

## Cronograma
Ver [CRONOGRAMA.md](./CRONOGRAMA.md)

## Tablero Trello
https://trello.com/b/upqa6AWl/boletera-de-autobuses

## Cómo correr las pruebas

Pruebas unitarias, de integración y de concurrencia (pytest):
```bash
pip install -r requirements.txt
python -m pytest --cov=main --cov=modelos --cov-report=term-missing tests/
```

Pruebas de API (colección de Postman `postman/coleccion_boletera.postman_collection.json`):
```bash
# Con Node.js/Newman instalado:
npx newman run postman/coleccion_boletera.postman_collection.json

# Sin Node.js (runner en Python que ejecuta la misma colección via HTTP real):
python scripts/run_postman_simulacion.py
```

Todo junto (pytest + pruebas de API) con cobertura combinada y dashboard HTML:
```bash
python scripts/generar_evidencia_completa.py
```

La evidencia de la última corrida (reportes HTML/JSON, cobertura combinada) queda en
[reportes/](./reportes/).

## Pipeline CI/CD
Ver pestaña Actions del repositorio.