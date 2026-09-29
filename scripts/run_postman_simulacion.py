"""
Simulador de ejecucion tipo Newman para la coleccion de Postman de La Boletera.

Este entorno no tiene Node.js/Newman instalado, asi que este script:
  1. Lee la coleccion real postman/coleccion_boletera.postman_collection.json
     (misma fuente de verdad que se importaria en Postman).
  2. Levanta la API (uvicorn, en un hilo dentro de este mismo proceso) contra
     una base de datos SQLite limpia.
  3. Ejecuta cada request en orden via HTTP real (requests), resolviendo
     variables de coleccion ({{base_url}}, {{autobus_id}}, {{$randomInt}}, etc.)
     igual que lo haria el motor de Postman.
  4. Evalua assertions equivalentes a los pm.test(...) definidos en la
     coleccion (mismo nombre, misma condicion) y arma un resumen de
     resultados por assertion, no solo por request.
  5. Genera evidencia en reportes/: un HTML estilo Newman HTMLExtra,
     un JSON con el detalle crudo y un TXT con el resumen estilo CLI.

El servidor corre en un hilo del proceso actual (no en un subproceso aparte)
a proposito: en Windows, apagar un subproceso "en caliente" para que
coverage.py alcance a guardar sus datos requiere manipular senales de consola
(CTRL_BREAK_EVENT) que no siempre llegan de forma confiable segun la terminal.
Con un hilo, el apagado es un simple flag (`server.should_exit`) y toda la
cobertura de la API queda medida dentro del mismo proceso que orquesta todo
(ver scripts/generar_evidencia_completa.py).

Ejecutar con: .venv/Scripts/python scripts/run_postman_simulacion.py
"""
import json
import random
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from database import Base, engine  # noqa: E402
from main import app  # noqa: E402

COLLECTION_PATH = ROOT / "postman" / "coleccion_boletera.postman_collection.json"
REPORTES_DIR = ROOT / "reportes"
DB_PATH = ROOT / "boletera.db"
PORT = 8010
BASE_URL = f"http://127.0.0.1:{PORT}"


def cargar_coleccion():
    with open(COLLECTION_PATH, encoding="utf-8") as f:
        return json.load(f)


def aplanar_items(items, carpeta=""):
    """Convierte el arbol item/folder de Postman en una lista plana de requests."""
    planos = []
    for item in items:
        if "item" in item:
            planos.extend(aplanar_items(item["item"], carpeta=item["name"]))
        else:
            planos.append((carpeta, item))
    return planos


def resolver_variables(texto, variables):
    if texto is None:
        return texto

    def reemplazo(match):
        clave = match.group(1)
        if clave == "$randomInt":
            return str(random.randint(1, 999999))
        return str(variables.get(clave, match.group(0)))

    anterior = None
    actual = texto
    intentos = 0
    while actual != anterior and intentos < 5:
        anterior = actual
        actual = re.sub(r"\{\{([^{}]+)\}\}", reemplazo, actual)
        intentos += 1
    return actual


def construir_url(request, variables):
    raw = request["url"]["raw"]
    return resolver_variables(raw, variables)


def construir_body(request, variables):
    body = request.get("body")
    if not body or body.get("mode") != "raw":
        return None
    raw = resolver_variables(body["raw"], variables)
    return json.loads(raw)


# --------------------------------------------------------------------------
# Assertions equivalentes a los pm.test(...) de cada request de la coleccion.
# Cada funcion recibe (response, variables) y regresa (nombre, ok: bool).
# --------------------------------------------------------------------------

def assertions_por_nombre(nombre, variables):
    r200 = lambda resp: ("Status code es 200", resp.status_code == 200)
    r422 = lambda resp: ("Status code es 422 (validacion Pydantic)", resp.status_code == 422)

    tabla = {
        "Crear autobus valido -> 200": [
            r200,
            lambda resp: ("Respuesta contiene id y placa registrada",
                          "id" in resp.json() and resp.json().get("capacidad") == 20),
        ],
        "Crear autobus con capacidad 1 (para prueba de limite) -> 200": [
            r200,
            lambda resp: ("Guarda autobus_id_capacidad_1", "id" in resp.json()),
        ],
        "Placa duplicada -> 400": [
            lambda resp: ("Status code es 400 (placa duplicada)", resp.status_code == 400),
            lambda resp: ("Mensaje de error correcto",
                          resp.json().get("detail") == "Esta placa ya está registrada"),
        ],
        "Capacidad <= 0 (valor limite invalido) -> 422": [r422],
        "Crear viaje valido -> 200": [
            r200,
            lambda resp: ("Guarda viaje_id y responde origen/destino correctos",
                          resp.json().get("origen") == "CDMX" and resp.json().get("destino") == "GDL"),
        ],
        "Crear viaje sobre autobus de capacidad 1 -> 200": [
            r200,
            lambda resp: ("Guarda viaje_id_capacidad_1", "id" in resp.json()),
        ],
        "Autobus inexistente -> 404": [
            lambda resp: ("Status code es 404", resp.status_code == 404),
            lambda resp: ("Mensaje de error correcto",
                          resp.json().get("detail") == "El autobus no existe"),
        ],
        "Fecha de salida en el pasado (valor limite invalido) -> 422": [r422],
        "Listar viajes -> 200": [
            r200,
            lambda resp: ("Responde un arreglo con al menos un viaje",
                          isinstance(resp.json(), list) and len(resp.json()) > 0),
        ],
        "Buscar viaje existente (CDMX -> GDL) -> 200": [
            r200,
            lambda resp: ("Encuentra al menos un viaje CDMX-GDL", len(resp.json()) > 0),
        ],
        "Buscar viaje sin resultados -> 200 lista vacia": [
            r200,
            lambda resp: ("Responde lista vacia", resp.json() == []),
        ],
        "Venta de boleto valida -> 201": [
            lambda resp: ("Status code es 201", resp.status_code == 201),
            lambda resp: ("Boleto creado con asiento 1",
                          resp.json().get("asiento") == 1 and resp.json().get("pasajero") == "Ana"),
        ],
        "Asiento duplicado en el mismo viaje -> 409": [
            lambda resp: ("Status code es 409 (conflicto)", resp.status_code == 409),
            lambda resp: ("Mensaje de error correcto", resp.json().get("detail") == "Asiento ya ocupado"),
        ],
        "Asiento excede capacidad del autobus (valor limite) -> 400": [
            lambda resp: ("Status code es 400", resp.status_code == 400),
            lambda resp: ("Mensaje de error correcto",
                          resp.json().get("detail") == "El asiento excede la capacidad del autobús"),
        ],
        "Asiento <= 0 (valor limite invalido) -> 422": [r422],
        "Venta de boleto sobre viaje inexistente -> 404": [
            lambda resp: ("Status code es 404", resp.status_code == 404),
            lambda resp: ("Mensaje de error correcto", resp.json().get("detail") == "Viaje no encontrado"),
        ],
        "Boletos de un viaje sin ventas -> 200 lista vacia": [
            r200,
            lambda resp: ("Responde lista vacia para el viaje capacidad 1 (sin ventas exitosas)",
                          resp.json() == []),
        ],
        "Boletos de viaje inexistente -> 404": [
            lambda resp: ("Status code es 404", resp.status_code == 404),
            lambda resp: ("Mensaje de error correcto", resp.json().get("detail") == "El viaje no existe"),
        ],
    }
    return tabla.get(nombre, [])


POST_ACCIONES = {
    "Crear autobus valido -> 200": lambda resp, v: v.__setitem__("autobus_id", resp.json()["id"]),
    "Crear autobus con capacidad 1 (para prueba de limite) -> 200":
        lambda resp, v: v.__setitem__("autobus_id_capacidad_1", resp.json()["id"]),
    "Crear viaje valido -> 200": lambda resp, v: (
        v.__setitem__("viaje_id", resp.json()["id"]),
        v.__setitem__("viaje_id_sin_boletos", resp.json()["id"]),
    ),
    "Crear viaje sobre autobus de capacidad 1 -> 200":
        lambda resp, v: v.__setitem__("viaje_id_capacidad_1", resp.json()["id"]),
}


def iniciar_servidor():
    # Pre-importar el modulo del loop factory en el hilo principal ANTES de
    # arrancar el hilo del servidor: hacer el primer import de un submodulo
    # (uvicorn.loops.*) desde un hilo secundario dispara un KeyError interno
    # en el import system de Python 3.14 (carrera entre hilos en
    # importlib._bootstrap._find_and_load_unlocked). Con el modulo ya en
    # sys.modules, uvicorn solo lo reutiliza sin volver a importarlo.
    import uvicorn.loops.asyncio  # noqa: F401

    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", loop="asyncio")
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    return server, hilo


def detener_servidor(server, hilo):
    server.should_exit = True
    hilo.join(timeout=5)


def esperar_servidor(url, intentos=40, espera=0.25):
    for _ in range(intentos):
        try:
            r = requests.get(url, timeout=1)
            if r.status_code < 500:
                return True
        except requests.exceptions.ConnectionError:
            time.sleep(espera)
    return False


def main():
    REPORTES_DIR.mkdir(exist_ok=True)
    engine.dispose()
    if DB_PATH.exists():
        DB_PATH.unlink()

    print(f"[setup] Creando base de datos limpia en {DB_PATH.name}")
    Base.metadata.create_all(bind=engine)

    print(f"[setup] Levantando la API con uvicorn (en un hilo) en {BASE_URL} ...")
    server, hilo = iniciar_servidor()

    variables = {}
    coleccion = cargar_coleccion()
    for v in coleccion.get("variable", []):
        variables[v["key"]] = v["value"]
    variables["base_url"] = BASE_URL

    # Emula el pre-request script de la coleccion: la placa unica se genera
    # UNA sola vez y se congela, para que el request de "placa duplicada"
    # reutilice el mismo valor (si se re-expandiera {{$randomInt}} en cada
    # uso, nunca habria una duplicidad real que probar).
    variables["placa_unica"] = f"ABC-{random.randint(1, 999999)}"

    resultados = []
    try:
        if not esperar_servidor(f"{BASE_URL}/viajes/"):
            raise RuntimeError("La API no respondio a tiempo; revisa el log de uvicorn.")

        requests_planas = aplanar_items(coleccion["item"])
        print(f"[run] Ejecutando {len(requests_planas)} requests de la coleccion...\n")

        for carpeta, item in requests_planas:
            nombre = item["name"]
            req = item["request"]
            metodo = req["method"]
            url = construir_url(req, variables)
            body = construir_body(req, variables)

            inicio = time.perf_counter()
            resp = requests.request(metodo, url, json=body, timeout=5)
            duracion_ms = round((time.perf_counter() - inicio) * 1000, 1)

            if nombre in POST_ACCIONES:
                POST_ACCIONES[nombre](resp, variables)

            checks = []
            for fn in assertions_por_nombre(nombre, variables):
                try:
                    label, ok = fn(resp)
                except Exception as exc:
                    label, ok = (f"Error evaluando assertion: {exc}", False)
                checks.append({"nombre": label, "ok": ok})

            try:
                cuerpo_resp = resp.json()
            except ValueError:
                cuerpo_resp = resp.text

            resultado = {
                "carpeta": carpeta,
                "nombre": nombre,
                "metodo": metodo,
                "url": url,
                "status": resp.status_code,
                "tiempo_ms": duracion_ms,
                "checks": checks,
                "response_body": cuerpo_resp,
            }
            resultados.append(resultado)

            ok_total = all(c["ok"] for c in checks) if checks else True
            estado = "PASS" if ok_total else "FAIL"
            print(f"  [{estado}] {carpeta} / {nombre}  ({metodo} -> {resp.status_code}, {duracion_ms} ms)")
            for c in checks:
                marca = "OK " if c["ok"] else "X  "
                print(f"        {marca} {c['nombre']}")
    finally:
        detener_servidor(server, hilo)
        engine.dispose()
        for _ in range(10):
            try:
                if DB_PATH.exists():
                    DB_PATH.unlink()
                break
            except PermissionError:
                time.sleep(0.3)

    total_requests = len(resultados)
    total_checks = sum(len(r["checks"]) for r in resultados)
    checks_ok = sum(1 for r in resultados for c in r["checks"] if c["ok"])
    checks_fail = total_checks - checks_ok
    tiempo_total = round(sum(r["tiempo_ms"] for r in resultados), 1)

    resumen = {
        "generado": datetime.now(timezone.utc).isoformat(),
        "coleccion": coleccion["info"]["name"],
        "total_requests": total_requests,
        "total_assertions": total_checks,
        "assertions_ok": checks_ok,
        "assertions_fail": checks_fail,
        "tiempo_total_ms": tiempo_total,
        "resultados": resultados,
    }

    (REPORTES_DIR / "reporte_newman.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    escribir_reporte_html(resumen)
    escribir_resumen_txt(resumen)

    print("\n===== Resumen =====")
    print(f"Requests ejecutados: {total_requests}")
    print(f"Assertions:          {total_checks} (ok: {checks_ok}, fallidas: {checks_fail})")
    print(f"Tiempo total:        {tiempo_total} ms")
    print("Reportes generados en reportes/: reporte_newman.html, reporte_newman.json, resumen_ejecucion.txt")

    return 0 if checks_fail == 0 else 1


def escribir_resumen_txt(resumen):
    lineas = []
    lineas.append(f"Coleccion: {resumen['coleccion']}")
    lineas.append(f"Generado (UTC): {resumen['generado']}")
    lineas.append("")
    lineas.append(f"{'Metodo':7} {'Status':7} {'Tiempo(ms)':11} Request")
    lineas.append("-" * 90)
    for r in resumen["resultados"]:
        lineas.append(f"{r['metodo']:7} {r['status']:<7} {r['tiempo_ms']:<11} {r['carpeta']} / {r['nombre']}")
        for c in r["checks"]:
            marca = "PASS" if c["ok"] else "FAIL"
            lineas.append(f"        [{marca}] {c['nombre']}")
    lineas.append("-" * 90)
    lineas.append(
        f"Total requests: {resumen['total_requests']} | "
        f"Total assertions: {resumen['total_assertions']} | "
        f"OK: {resumen['assertions_ok']} | "
        f"Fallidas: {resumen['assertions_fail']} | "
        f"Tiempo total: {resumen['tiempo_total_ms']} ms"
    )
    (REPORTES_DIR / "resumen_ejecucion.txt").write_text("\n".join(lineas), encoding="utf-8")


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Reporte de pruebas de API - {coleccion}</title>
<style>
  :root {{
    --ok: #16a34a; --fail: #dc2626; --bg: #0f172a; --panel: #1e293b; --text: #e2e8f0; --muted: #94a3b8;
  }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #f1f5f9; color: #0f172a; margin: 0; padding: 0; }}
  header {{ background: var(--bg); color: white; padding: 28px 36px; }}
  header h1 {{ margin: 0 0 6px 0; font-size: 22px; }}
  header p {{ margin: 0; color: var(--muted); font-size: 13px; }}
  .summary {{ display: flex; gap: 16px; padding: 20px 36px; flex-wrap: wrap; }}
  .card {{ background: white; border-radius: 10px; padding: 16px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.12); min-width: 140px; }}
  .card .num {{ font-size: 26px; font-weight: 700; }}
  .card .label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: .04em; }}
  .card.ok .num {{ color: var(--ok); }}
  .card.fail .num {{ color: var(--fail); }}
  main {{ padding: 0 36px 40px 36px; }}
  .folder {{ margin-top: 28px; }}
  .folder h2 {{ font-size: 15px; text-transform: uppercase; letter-spacing: .05em; color: #475569; border-bottom: 2px solid #cbd5e1; padding-bottom: 6px; }}
  .request {{ background: white; border-radius: 8px; margin: 12px 0; box-shadow: 0 1px 2px rgba(0,0,0,.08); overflow: hidden; }}
  .request-head {{ display: flex; align-items: center; gap: 12px; padding: 12px 18px; border-left: 5px solid var(--ok); }}
  .request-head.fail {{ border-left-color: var(--fail); }}
  .method {{ font-weight: 700; font-size: 12px; background: #e2e8f0; padding: 3px 8px; border-radius: 4px; }}
  .status {{ font-weight: 700; font-size: 13px; }}
  .status.s2 {{ color: var(--ok); }}
  .status.s4 {{ color: #d97706; }}
  .time {{ margin-left: auto; color: #64748b; font-size: 12px; }}
  .checks {{ padding: 4px 18px 14px 18px; }}
  .check {{ font-size: 13px; padding: 3px 0; }}
  .check.ok::before {{ content: '\\2713  '; color: var(--ok); font-weight: 700; }}
  .check.fail::before {{ content: '\\2717  '; color: var(--fail); font-weight: 700; }}
  .url {{ font-family: Consolas, monospace; font-size: 12px; color: #475569; padding: 0 18px 10px 18px; word-break: break-all; }}
  footer {{ text-align: center; padding: 24px; color: #94a3b8; font-size: 12px; }}
</style>
</head>
<body>
<header>
  <h1>{coleccion}</h1>
  <p>Reporte generado el {generado} (UTC) &mdash; simulacion de ejecucion Newman via HTTP real contra la API (Node.js/Newman no disponible en el entorno de ejecucion)</p>
</header>
<div class="summary">
  <div class="card"><div class="num">{total_requests}</div><div class="label">Requests</div></div>
  <div class="card"><div class="num">{total_assertions}</div><div class="label">Assertions</div></div>
  <div class="card ok"><div class="num">{assertions_ok}</div><div class="label">Passed</div></div>
  <div class="card fail"><div class="num">{assertions_fail}</div><div class="label">Failed</div></div>
  <div class="card"><div class="num">{tiempo_total_ms} ms</div><div class="label">Tiempo total</div></div>
</div>
<main>
{folders}
</main>
<footer>La Boletera &mdash; Suite de pruebas de API (Postman collection + ejecucion automatizada)</footer>
</body>
</html>
"""


def escribir_reporte_html(resumen):
    por_carpeta = {}
    for r in resumen["resultados"]:
        por_carpeta.setdefault(r["carpeta"], []).append(r)

    bloques = []
    for carpeta, items in por_carpeta.items():
        filas = []
        for r in items:
            ok_total = all(c["ok"] for c in r["checks"]) if r["checks"] else True
            clase_status = "s2" if 200 <= r["status"] < 300 else "s4"
            checks_html = "".join(
                f'<div class="check {"ok" if c["ok"] else "fail"}">{c["nombre"]}</div>'
                for c in r["checks"]
            )
            filas.append(f"""
            <div class="request">
              <div class="request-head {'' if ok_total else 'fail'}">
                <span class="method">{r['metodo']}</span>
                <strong>{r['nombre']}</strong>
                <span class="status {clase_status}">{r['status']}</span>
                <span class="time">{r['tiempo_ms']} ms</span>
              </div>
              <div class="url">{r['url']}</div>
              <div class="checks">{checks_html}</div>
            </div>
            """)
        bloques.append(f'<div class="folder"><h2>{carpeta}</h2>{"".join(filas)}</div>')

    html = HTML_TEMPLATE.format(
        coleccion=resumen["coleccion"],
        generado=resumen["generado"],
        total_requests=resumen["total_requests"],
        total_assertions=resumen["total_assertions"],
        assertions_ok=resumen["assertions_ok"],
        assertions_fail=resumen["assertions_fail"],
        tiempo_total_ms=resumen["tiempo_total_ms"],
        folders="".join(bloques),
    )
    (REPORTES_DIR / "reporte_newman.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
