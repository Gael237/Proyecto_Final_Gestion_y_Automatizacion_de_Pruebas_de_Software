"""
Orquestador de evidencia para el portafolio tecnico.

Corre, dentro de UN SOLO proceso Python medido por coverage.py:
  1. La suite de pytest (unitarias + integracion + concurrencia).
  2. La suite de pruebas de API: la coleccion de Postman ejecutada via HTTP
     real contra un servidor uvicorn levantado en un hilo (ver
     scripts/run_postman_simulacion.py).

Al correr todo en el mismo proceso se evita tener que combinar datos de
cobertura entre procesos (y los problemas de apagar subprocesos "en
caliente" en Windows), midiendo de una sola vez cuanto codigo de main.py y
modelos.py cubren, en conjunto, las pruebas de caja blanca y las de caja
negra (API).

Genera evidencia en reportes/: pytest_resultado.txt, reporte_newman.html,
reporte_newman.json, resumen_ejecucion.txt, cobertura_combinada.txt y la
carpeta cobertura_html/ (dashboard de cobertura navegable).

Ejecutar con: .venv/Scripts/python scripts/generar_evidencia_completa.py
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import coverage
import pytest

ROOT = Path(__file__).resolve().parent.parent
# ROOT debe ir primero: tests/conftest.py hace "from database import ...", y
# eso solo resuelve si la raiz del proyecto esta en sys.path (igual que pasa
# cuando se corre `python -m pytest` con cwd=ROOT).
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
REPORTES_DIR = ROOT / "reportes"


class _Tee(io.TextIOBase):
    """Escribe a la consola real y a un buffer en memoria al mismo tiempo."""

    def __init__(self, consola):
        self._consola = consola
        self.buffer = io.StringIO()

    def write(self, s):
        self._consola.write(s)
        self.buffer.write(s)
        return len(s)

    def flush(self):
        self._consola.flush()


def correr_pytest():
    print("== 1/2 Pruebas unitarias + integracion + concurrencia (pytest) ==")
    tee = _Tee(sys.__stdout__)
    with redirect_stdout(tee):
        codigo = pytest.main(["-v", str(ROOT / "tests")])
    (REPORTES_DIR / "pytest_resultado.txt").write_text(tee.buffer.getvalue(), encoding="utf-8")
    return codigo


def correr_pruebas_api():
    print("\n== 2/2 Pruebas de API (coleccion Postman via HTTP real, servidor en hilo) ==")
    import run_postman_simulacion as api_sim
    return api_sim.main()


def main():
    REPORTES_DIR.mkdir(exist_ok=True)

    cov = coverage.Coverage(source=["main", "modelos"])
    cov.start()
    try:
        rc_pytest = correr_pytest()
        rc_api = correr_pruebas_api()
    finally:
        cov.stop()
        cov.save()

    print("\n== Cobertura combinada (pytest + pruebas de API) ==")
    destino_txt = REPORTES_DIR / "cobertura_combinada.txt"
    with open(destino_txt, "w", encoding="utf-8") as f:
        cov.report(show_missing=True, file=f)
    print(destino_txt.read_text(encoding="utf-8"))

    carpeta_html = REPORTES_DIR / "cobertura_html"
    cov.html_report(directory=str(carpeta_html))
    # coverage.py escribe su propio .gitignore ("*") dentro de la carpeta de
    # salida para que nadie lo suba a git por accidente; en este proyecto SI
    # queremos versionar el dashboard como evidencia, asi que se elimina.
    (carpeta_html / ".gitignore").unlink(missing_ok=True)
    print(f"Dashboard de cobertura HTML generado en {carpeta_html}/index.html")

    if rc_pytest != 0 or rc_api != 0:
        print("\nATENCION: alguna suite reporto fallas, revisa reportes/ para el detalle.")
        return 1

    print("\nEvidencia generada correctamente en reportes/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
