"""
Convierte docs/portafolio.md a un PDF con buen formato (docs/portafolio_tecnico.pdf).

Flujo: Markdown -> HTML (python-markdown, con extension de tablas y bloques de
codigo con fences) -> PDF (xhtml2pdf, 100% Python, sin depender de binarios
externos como wkhtmltopdf/pandoc/LaTeX que este entorno no tiene instalados).

Se registran copias locales de fuentes de Windows (Arial/Consolas, copiadas a
scripts/_fonts/ y NO versionadas en git) para que los acentos, signos de
interrogacion invertidos y demas caracteres del espanol se vean correctos (la
fuente por defecto de reportlab/xhtml2pdf es Helvetica, que no trae esos
glifos). Si scripts/_fonts/ no existe, este script la crea copiando las
fuentes desde C:/Windows/Fonts la primera vez.

Ejecutar con: .venv/Scripts/python scripts/generar_pdf_portafolio.py
"""
import shutil
import sys
from pathlib import Path

import markdown
from xhtml2pdf import pisa
from xhtml2pdf.config.resources import PERMISSIVE_POLICY

ROOT = Path(__file__).resolve().parent.parent
ORIGEN = ROOT / "docs" / "portafolio.md"
DESTINO = ROOT / "docs" / "portafolio_tecnico.pdf"

FUENTES_LOCALES = Path(__file__).resolve().parent / "_fonts"
FUENTES_WINDOWS = Path("C:/Windows/Fonts")


def asegurar_fuentes_locales():
    FUENTES_LOCALES.mkdir(exist_ok=True)
    for nombre in ("arial.ttf", "arialbd.ttf", "consola.ttf"):
        destino = FUENTES_LOCALES / nombre
        if not destino.exists():
            shutil.copyfile(FUENTES_WINDOWS / nombre, destino)

CSS = """
@font-face {{
    font-family: "Cuerpo";
    src: url("{arial}");
}}
@font-face {{
    font-family: "CuerpoNegrita";
    src: url("{arialbd}");
}}
@font-face {{
    font-family: "Monoespaciada";
    src: url("{consola}");
}}
@page {{
    size: letter;
    margin: 2.2cm 1.8cm 2.2cm 1.8cm;
    @frame footer {{
        -pdf-frame-content: pie_pagina;
        bottom: 1cm; margin-left: 1.8cm; margin-right: 1.8cm; height: 1cm;
    }}
}}
body {{ font-family: "Cuerpo"; font-size: 9.5pt; line-height: 1.35; color: #1a1a1a; }}
h1 {{ font-family: "CuerpoNegrita"; font-size: 19pt; color: #0f172a; border-bottom: 2px solid #0f172a;
      padding-bottom: 6px; margin-top: 0; }}
h2 {{ font-family: "CuerpoNegrita"; font-size: 14pt; color: #0f172a; margin-top: 22px;
      border-bottom: 1px solid #94a3b8; padding-bottom: 3px; }}
h3 {{ font-family: "CuerpoNegrita"; font-size: 11.5pt; color: #1e293b; margin-top: 14px; }}
p {{ margin: 6px 0; text-align: justify; }}
a {{ color: #1d4ed8; }}
strong {{ font-family: "CuerpoNegrita"; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 8.5pt; }}
th {{ background-color: #0f172a; color: white; padding: 5px 7px; text-align: left;
      font-family: "CuerpoNegrita"; }}
td {{ padding: 4px 7px; border: 1px solid #cbd5e1; }}
tr:nth-child(even) td {{ background-color: #f1f5f9; }}
pre {{ background-color: #0f172a; color: #e2e8f0; padding: 8px 10px; font-size: 8pt;
       font-family: "Monoespaciada"; -pdf-word-wrap: CJK; }}
code {{ font-family: "Monoespaciada"; background-color: #e2e8f0; padding: 1px 3px; font-size: 8.5pt; }}
pre code {{ background-color: transparent; padding: 0; color: #e2e8f0; }}
blockquote {{ border-left: 4px solid #94a3b8; margin: 8px 0; padding: 2px 12px; color: #334155;
              font-style: italic; }}
ul, ol {{ margin: 4px 0 8px 0; padding-left: 18px; }}
li {{ margin: 2px 0; }}
img {{ width: 100%; margin: 8px 0; border: 1px solid #cbd5e1; }}
#pie_pagina {{ font-size: 8pt; color: #64748b; text-align: center; }}
"""

PORTADA = """
<div style="text-align:center; margin-top:170px;">
  <div style="font-size:11pt; color:#64748b; letter-spacing:2px;">PORTAFOLIO TECNICO</div>
  <div style="font-size:26pt; font-family:'CuerpoNegrita'; color:#0f172a; margin-top:14px;">
    La Boletera
  </div>
  <div style="font-size:13pt; color:#334155; margin-top:6px;">
    Aseguramiento de Calidad y Automatizacion de Pruebas de Software
  </div>
  <div style="font-size:10pt; color:#64748b; margin-top:60px;">
    Pruebas unitarias &middot; integracion &middot; concurrencia &middot; API (Postman/Newman)
  </div>
</div>
<pdf:nextpage />
"""


def construir_html():
    texto_md = ORIGEN.read_text(encoding="utf-8")
    cuerpo_html = markdown.markdown(
        texto_md,
        extensions=["tables", "fenced_code", "sane_lists", "toc"],
    )

    fuentes = {
        "arial": (FUENTES_LOCALES / "arial.ttf").as_posix(),
        "arialbd": (FUENTES_LOCALES / "arialbd.ttf").as_posix(),
        "consola": (FUENTES_LOCALES / "consola.ttf").as_posix(),
    }
    css = CSS.format(**fuentes)

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>{css}</style></head>
<body>
{PORTADA}
{cuerpo_html}
<pdf:pagenumber id="pie_pagina" />
</body></html>"""


def main():
    asegurar_fuentes_locales()
    html = construir_html()
    with open(DESTINO, "wb") as f:
        resultado = pisa.CreatePDF(
            src=html.encode("utf-8"),
            dest=f,
            encoding="utf-8",
            path=str(ORIGEN.parent) + "/",  # base para resolver img/*.png relativas a docs/
            resource_policy=PERMISSIVE_POLICY,  # contenido propio y de confianza, no input externo
        )

    if resultado.err:
        print(f"Se generaron {resultado.err} error(es) al construir el PDF.")
        return 1

    print(f"PDF generado en {DESTINO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
