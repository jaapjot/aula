"""Aula: crea la base, corre las consultas y genera el informe HTML.

Uso:
    python aula.py                 # crea aula.db, genera datos y escribe informe.html
    python aula.py --hoy 2026-10-31
"""
import argparse
import re
import sqlite3
from html import escape
from pathlib import Path

import datos

AQUI = Path(__file__).resolve().parent
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


# ---------------------------------------------------------------- base de datos
def crear_base(ruta=":memory:", con_datos=True):
    if ruta != ":memory:" and Path(ruta).exists():
        Path(ruta).unlink()
    conn = sqlite3.connect(ruta)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript((AQUI / "schema.sql").read_text(encoding="utf-8"))
    if con_datos:
        datos.generar(conn)
    return conn


def cargar_consultas(ruta=None):
    """Lee consultas.sql y devuelve {nombre: sql}."""
    texto = (ruta or AQUI / "consultas.sql").read_text(encoding="utf-8")
    partes = re.split(r"^-- name:\s*(\w+)\s*$", texto, flags=re.MULTILINE)
    return {partes[i]: partes[i + 1].strip() for i in range(1, len(partes), 2)}


def correr(conn, consultas, nombre, hoy):
    return [dict(f) for f in conn.execute(consultas[nombre], {"hoy": hoy})]


def analizar(conn, hoy):
    consultas = cargar_consultas()
    return {n: correr(conn, consultas, n, hoy) for n in consultas}


# ---------------------------------------------------------------- formato
def plata(n):
    return "$ " + f"{int(n):,}".replace(",", ".")


def mes_corto(periodo):
    return MESES[int(periodo[5:7]) - 1]


def fecha_corta(iso):
    return f"{int(iso[8:10])} {MESES[int(iso[5:7]) - 1]}" if iso else "—"


# ---------------------------------------------------------------- gráficos SVG
MESES_LARGO = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
               "septiembre", "octubre", "noviembre", "diciembre"]


def mes_largo(periodo):
    return MESES_LARGO[int(periodo[5:7]) - 1]


def grafico_piruletas(filas, clave_x, clave_y, formato):
    """Un palito y un punto por mes: el dato se lee sin tapar nada."""
    ancho, alto, margen = 640, 240, 34
    if not filas:
        return ""
    mx = max(f[clave_y] for f in filas) or 1
    paso = (ancho - 2 * margen) / len(filas)
    base = alto - margen
    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Ingresos cobrados por mes">']
    partes.append(f'<line class="base" x1="{margen}" x2="{ancho - margen}" y1="{base}" y2="{base}"/>')
    for i, f in enumerate(filas):
        x = margen + i * paso + paso / 2
        y = base - (alto - 2 * margen - 14) * f[clave_y] / mx
        partes.append(f'<line class="palito" x1="{x:.1f}" x2="{x:.1f}" y1="{base}" y2="{y:.1f}"/>')
        partes.append(f'<circle class="dato" cx="{x:.1f}" cy="{y:.1f}" r="6.5"/>')
        partes.append(f'<text class="val" x="{x:.1f}" y="{y - 14:.1f}" text-anchor="middle">{formato(f[clave_y])}</text>')
        partes.append(f'<text class="eje" x="{x:.1f}" y="{alto - 10}" text-anchor="middle">{mes_corto(f[clave_x])}</text>')
    partes.append("</svg>")
    return "".join(partes)


def grafico_linea(filas, clave_x, clave_y):
    ancho, alto, margen = 640, 240, 40
    if len(filas) < 2:
        return ""
    valores = [f[clave_y] for f in filas]
    lo, hi = min(60, min(valores) - 5), 100
    paso = (ancho - 2 * margen) / (len(filas) - 1)
    pts = []
    for i, f in enumerate(filas):
        x = margen + i * paso
        y = alto - margen - (alto - 2 * margen) * (f[clave_y] - lo) / (hi - lo)
        pts.append((x, y, f))
    partes = [f'<svg viewBox="0 0 {ancho} {alto}" role="img" aria-label="Asistencia mensual">']
    for ref in (lo, (lo + hi) / 2, hi):
        y = alto - margen - (alto - 2 * margen) * (ref - lo) / (hi - lo)
        partes.append(f'<line class="guia" x1="{margen}" x2="{ancho - margen}" y1="{y:.1f}" y2="{y:.1f}"/>')
        partes.append(f'<text class="eje" x="{margen - 8}" y="{y + 4:.1f}" text-anchor="end">{ref:.0f}%</text>')
    partes.append('<polyline class="linea" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in pts) + '"/>')
    for x, y, f in pts:
        partes.append(f'<circle class="punto" cx="{x:.1f}" cy="{y:.1f}" r="5"/>')
        partes.append(f'<text class="val" x="{x:.1f}" y="{y - 12:.1f}" text-anchor="middle">{f[clave_y]:.0f}%</text>')
        partes.append(f'<text class="eje" x="{x:.1f}" y="{alto - 10}" text-anchor="middle">{mes_corto(f[clave_x] + "-01")}</text>')
    partes.append("</svg>")
    return "".join(partes)


# ---------------------------------------------------------------- informe
# Diseño editorial: papel crema, tinta azul y terracota; sin tarjetas, con filetes y numerales grandes.
CSS = """
:root{color-scheme:light;--papel:#f6f1e7;--tinta:#1f2a44;--dim:#6d665a;--linea:#d8cdb8;--acc:#c4533b;--acc2:#2f4b7c;--suave:#ebe3d2}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--papel:#17150f;--tinta:#efe7d6;--dim:#a39b88;--linea:#3a3528;--acc:#e8836b;--acc2:#8fb0e8;--suave:#221f16}}
*{box-sizing:border-box}
body{margin:0;background:var(--papel);color:var(--tinta);font:16px/1.6 "Segoe UI",Verdana,sans-serif}
main{max-width:1020px;margin:0 auto;padding:48px 24px 72px}
.serif,h1,h2,.num{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
header{border-bottom:3px double var(--tinta);padding-bottom:22px}
.sobre{letter-spacing:.18em;text-transform:uppercase;font-size:.72rem;color:var(--acc);margin:0 0 6px}
h1{font-size:clamp(3rem,9vw,5.6rem);line-height:1;margin:0;font-weight:700;letter-spacing:-.02em}
.baja{color:var(--dim);margin:10px 0 0;max-width:46ch}
.aviso{display:inline-block;margin-top:16px;padding:2px 10px;background:var(--acc);color:var(--papel);font-size:.75rem;letter-spacing:.06em}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--linea)}
.kpi{padding:22px 18px 20px 0;margin-right:18px;border-right:1px solid var(--linea)}
.kpi:last-child{border-right:0}
.num{display:block;font-size:clamp(1.8rem,4.4vw,2.7rem);line-height:1.1;font-weight:700}
.kpi:nth-child(odd) .num{color:var(--acc)}.kpi:nth-child(even) .num{color:var(--acc2)}
.kpi span:last-child{color:var(--dim);font-size:.82rem}
.bloque{display:grid;grid-template-columns:240px 1fr;gap:36px;padding:34px 0;border-bottom:1px solid var(--linea)}
.n{font-family:Georgia,serif;font-style:italic;color:var(--acc);font-size:.95rem}
h2{font-size:1.55rem;line-height:1.2;margin:2px 0 10px}
.lectura{color:var(--dim);font-size:.9rem;margin:0}
.lectura b{color:var(--tinta)}
svg{width:100%;height:auto;display:block}
.palito{stroke:var(--acc);stroke-width:2}.dato{fill:var(--acc)}
.linea{fill:none;stroke:var(--acc2);stroke-width:2.5}.punto{fill:var(--papel);stroke:var(--acc2);stroke-width:2.5}
.val{fill:var(--tinta);font-size:12px}.eje{fill:var(--dim);font-size:12px}
.base{stroke:var(--tinta);stroke-width:1.5}.guia{stroke:var(--linea);stroke-width:1;stroke-dasharray:3 4}
.fila{display:grid;grid-template-columns:minmax(150px,1.1fr) 3fr 52px;gap:14px;align-items:center;padding:9px 0;border-bottom:1px dotted var(--linea);font-size:.92rem}
.pista{position:relative;height:2px;background:var(--linea)}
.pista i{position:absolute;top:50%;width:13px;height:13px;margin:-6.5px 0 0 -6.5px;border-radius:50%;background:var(--acc2)}
.fila:first-of-type .pista i{background:var(--acc)}
.pct{text-align:right;font-family:Georgia,serif;font-weight:700}
.escala{display:flex;justify-content:space-between;color:var(--dim);font-size:.72rem;margin:2px 0 0 calc(min(150px,26%) + 14px)}
table{width:100%;border-collapse:collapse;font-size:.92rem}
th{text-align:left;font-weight:normal;color:var(--dim);font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;padding:0 6px 8px 0;border-bottom:2px solid var(--tinta)}
td{padding:9px 6px 9px 0;border-bottom:1px dotted var(--linea)}
th.d,td.d{text-align:right;padding-right:0}
.alerta{color:var(--acc);font-weight:600}.vacio{color:var(--dim);font-style:italic}
.dos{display:grid;grid-template-columns:1fr 1fr;gap:36px}
.dos>div h3{font-family:Georgia,serif;font-size:1.05rem;margin:0 0 2px}
.dos>div p{color:var(--dim);font-size:.85rem;margin:0 0 12px}
footer{padding-top:22px;color:var(--dim);font-size:.8rem}
@media(max-width:820px){.bloque{grid-template-columns:1fr;gap:16px}.dos{grid-template-columns:1fr}
.kpis{grid-template-columns:1fr 1fr}.kpi:nth-child(2){border-right:0}.kpi{border-bottom:1px solid var(--linea)}
.fila{grid-template-columns:1fr 52px}.fila .pista{grid-column:1/-1;order:3}.escala{margin-left:0}th{letter-spacing:0;padding-right:10px}th.d{padding-right:0}}
"""


def _tabla(cabeceras, filas, vacio):
    if not filas:
        return f'<p class="vacio">{vacio}</p>'
    th = "".join(f'<th class="{c}">{escape(t)}</th>' for t, c in cabeceras)
    trs = "".join("<tr>" + "".join(f'<td class="{c}">{v}</td>' for v, c in fila) + "</tr>" for fila in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def lecturas(res):
    """Frases que resumen cada gráfico, calculadas con los mismos datos."""
    ing, asis, gr = res["ingresos_mensuales"], res["asistencia_mensual"], res["asistencia_por_grupo"]
    k = res["kpis"][0]
    mejor = max(ing, key=lambda f: f["total"])
    sube = max(asis, key=lambda f: f["asistencia_pct"])
    baja = min(asis, key=lambda f: f["asistencia_pct"])
    return {
        "ingresos": f"<b>{mes_largo(mejor['periodo']).capitalize()}</b> fue el mejor mes, con {plata(mejor['total'])} "
                    f"en {mejor['pagos']} pagos. Cada cuota se cuenta en el mes al que corresponde, no en el que se cobró.",
        "asistencia": f"Fue más alta en <b>{mes_largo(sube['mes'] + '-01')}</b> ({sube['asistencia_pct']:.0f}%) y más baja en "
                      f"<b>{mes_largo(baja['mes'] + '-01')}</b> ({baja['asistencia_pct']:.0f}%). Solo se cuentan clases dictadas.",
        "grupos": (f"<b>{escape(gr[0]['nombre'])}</b> es el grupo que más viene y <b>{escape(gr[-1]['nombre'])}</b> el que menos: "
                   f"{gr[0]['asistencia_pct'] - gr[-1]['asistencia_pct']:.0f} puntos de diferencia."
                   if len(gr) > 1 else "Hay un solo grupo, así que no hay con qué compararlo."),
        "riesgo": f"<b>{len(res['riesgo_abandono'])}</b> de {k['alumnos_activos']} alumnos activos faltaron a sus últimas 3 clases. "
                  f"Conviene escribirles antes de que se pierdan.",
        "deuda": f"<b>{len(res['deuda'])}</b> alumnos activos deben al menos una cuota. Se muestran los 12 con más cuotas pendientes.",
    }


def render_informe(res, hoy):
    k = res["kpis"][0]
    L = lecturas(res)
    deuda_total = sum(f["monto_adeudado"] for f in res["deuda"])
    filas_grupo = "".join(
        f'<div class="fila"><span>{escape(g["nombre"])}</span>'
        f'<div class="pista"><i style="left:{max(0, min(100, (g["asistencia_pct"] - 50) * 2)):.1f}%"></i></div>'
        f'<span class="pct">{g["asistencia_pct"]:.0f}%</span></div>'
        for g in res["asistencia_por_grupo"]
    )
    riesgo = _tabla(
        [("Alumno", ""), ("Grupo", ""), ("Última vez", "d")],
        [[(escape(f["nombre"]), ""), (escape(f["grupo"]), ""), (fecha_corta(f["ultima_asistencia"]), "d alerta")]
         for f in res["riesgo_abandono"]],
        "Nadie faltó a sus últimas 3 clases.",
    )
    deuda = _tabla(
        [("Alumno", ""), ("Cuotas", "d"), ("Adeuda", "d")],
        [[(escape(f["nombre"]), ""), (str(f["cuotas_adeudadas"]), "d" + (" alerta" if f["cuotas_adeudadas"] >= 3 else "")),
          (plata(f["monto_adeudado"]), "d")] for f in res["deuda"][:12]],
        "No hay cuotas adeudadas.",
    )
    retencion = _tabla(
        [("Grupo", ""), ("Inscriptos", "d"), ("Activos", "d"), ("Retención", "d")],
        [[(escape(f["nombre"]), ""), (str(f["inscriptos"]), "d"), (str(f["activos"]), "d"), (f'{f["retencion_pct"]:.0f}%', "d")]
         for f in res["retencion_por_grupo"]],
        "Sin datos.",
    )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Aula · informe de grupos</title><style>{CSS}</style></head>
<body><main>
<header><p class="sobre">Informe de gestión · corte al {fecha_corta(hoy)} de {hoy[:4]}</p>
<h1>Aula</h1>
<p class="baja">Grupos, asistencia y cobranzas de un taller con clases semanales, leídos desde una base SQL.</p>
<span class="aviso">DATOS FICTICIOS · demostración</span></header>

<div class="kpis">
<div class="kpi"><span class="num">{k["alumnos_activos"]}</span><span>alumnos activos en {k["grupos"]} grupos</span></div>
<div class="kpi"><span class="num">{k["asistencia_4_semanas"]:.0f}%</span><span>asistencia, últimas 4 semanas</span></div>
<div class="kpi"><span class="num">{plata(k["cobrado_mes"])}</span><span>cobrado del mes en curso</span></div>
<div class="kpi"><span class="num">{plata(deuda_total)}</span><span>en cuotas adeudadas</span></div>
</div>

<div class="bloque"><div><span class="n">01</span><h2>Lo que se cobra</h2><p class="lectura">{L["ingresos"]}</p></div>
<div>{grafico_piruletas(res["ingresos_mensuales"], "periodo", "total", lambda v: f"{v / 1000:.0f} mil")}</div></div>

<div class="bloque"><div><span class="n">02</span><h2>Quién viene</h2><p class="lectura">{L["asistencia"]}</p></div>
<div>{grafico_linea(res["asistencia_mensual"], "mes", "asistencia_pct")}</div></div>

<div class="bloque"><div><span class="n">03</span><h2>Cada grupo, comparado</h2><p class="lectura">{L["grupos"]}</p></div>
<div>{filas_grupo}<div class="escala"><span>50%</span><span>75%</span><span>100%</span></div></div></div>

<div class="bloque"><div><span class="n">04</span><h2>A quién llamar</h2><p class="lectura">{L["riesgo"]}</p></div>
<div class="dos"><div><h3>En riesgo de abandonar</h3><p>Faltaron a las últimas 3 clases.</p>{riesgo}</div>
<div><h3>Cuotas adeudadas</h3><p>{L["deuda"]}</p>{deuda}</div></div></div>

<div class="bloque"><div><span class="n">05</span><h2>Quién se queda</h2><p class="lectura">Alumnos que siguen activos sobre todos los que se inscribieron en cada grupo.</p></div>
<div>{retencion}</div></div>

<footer>Generado con aula.py desde una base SQLite. {k["clases_suspendidas"]} clases suspendidas no se cuentan en la asistencia.
Ningún dato corresponde a personas reales.</footer>
</main></body></html>"""


# ---------------------------------------------------------------- programa principal
def main(argv=None):
    ap = argparse.ArgumentParser(description="Genera la base de Aula y su informe.")
    ap.add_argument("--hoy", default=datos.HOY.isoformat(), help="fecha de corte AAAA-MM-DD")
    ap.add_argument("--db", default=str(AQUI / "aula.db"))
    ap.add_argument("--salida", default=str(AQUI / "informe.html"))
    a = ap.parse_args(argv)

    conn = crear_base(a.db)
    res = analizar(conn, a.hoy)
    Path(a.salida).write_text(render_informe(res, a.hoy), encoding="utf-8")
    k = res["kpis"][0]
    print(f"Base: {a.db}")
    print(f"Informe: {a.salida}")
    print(f"{k['alumnos_activos']} alumnos activos · asistencia 4 semanas {k['asistencia_4_semanas']}% · "
          f"en riesgo: {len(res['riesgo_abandono'])} · con deuda: {len(res['deuda'])}")
    conn.close()


if __name__ == "__main__":
    main()
