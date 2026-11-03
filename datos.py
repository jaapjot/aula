"""Generador de datos ficticios para Aula.

Todos los nombres y números son inventados. La semilla fija hace que dos
ejecuciones produzcan exactamente la misma base, así los resultados del informe
son reproducibles.
"""
import random
from datetime import date, timedelta

INICIO = date(2026, 3, 2)      # primer lunes de clases
FIN = date(2026, 10, 30)       # última fecha con datos
HOY = FIN

GRUPOS = [
    # nombre, sede, día (0 = lunes), hora, precio mensual (pesos ficticios)
    ("Silla · lunes 10:00", "Salón comunitario", 0, "10:00", 14000),
    ("Silla · martes 15:00", "Centro de jubilados", 1, "15:00", 14000),
    ("Silla · miércoles 10:00", "Salón comunitario", 2, "10:00", 14000),
    ("Suave · jueves 09:00", "Club del barrio", 3, "09:00", 16000),
    ("Suave · viernes 11:00", "Club del barrio", 4, "11:00", 16000),
    ("Equilibrio · viernes 16:00", "Centro de jubilados", 4, "16:00", 18000),
]

NOMBRES = ["Ana", "Beatriz", "Carlos", "Dora", "Elena", "Fabián", "Graciela", "Héctor",
           "Irma", "Jorge", "Karina", "Luis", "Marta", "Norma", "Osvaldo", "Perla",
           "Raúl", "Silvia", "Tomás", "Úrsula", "Víctor", "Zulema", "Alicia", "Rubén",
           "Mabel", "Aníbal", "Nélida", "Julio", "Rosa", "Ernesto"]
APELLIDOS = ["Acosta", "Benítez", "Cabrera", "Domínguez", "Escobar", "Fernández", "Giménez",
             "Herrera", "Ibáñez", "Juárez", "Luna", "Medina", "Núñez", "Ortiz", "Pereyra",
             "Quiroga", "Ríos", "Sosa", "Toledo", "Vega", "Villalba", "Zárate", "Molina", "Paz"]
MEDIOS = ["efectivo", "transferencia", "mercado pago"]


def _sumar_meses(periodo, n):
    anio, mes = map(int, periodo.split("-"))
    total = anio * 12 + (mes - 1) + n
    return f"{total // 12}-{total % 12 + 1:02d}"


def _meses(desde, hasta):
    p = desde
    while p <= hasta:
        yield p
        p = _sumar_meses(p, 1)


def generar(conn, semilla=2026, n_alumnos=72):
    """Llena la base (con el esquema ya creado) con datos ficticios."""
    rnd = random.Random(semilla)
    cur = conn.cursor()

    cur.executemany(
        "INSERT INTO grupos (nombre, sede, dia_semana, hora, precio_mensual) VALUES (?,?,?,?,?)",
        GRUPOS,
    )
    precios = {i + 1: g[4] for i, g in enumerate(GRUPOS)}

    # --- Clases: una por semana por grupo; ~1 de cada 14 se suspende. ---
    for gid, g in enumerate(GRUPOS, start=1):
        dia = INICIO + timedelta(days=g[2])
        while dia <= FIN:
            dictada = 0 if rnd.random() < 0.07 else 1
            cur.execute("INSERT INTO clases (grupo_id, fecha, dictada) VALUES (?,?,?)",
                        (gid, dia.isoformat(), dictada))
            dia += timedelta(days=7)

    # --- Alumnos: nombres únicos, altas concentradas en marzo, ~18 % de bajas. ---
    combos = [f"{n} {a}" for n in NOMBRES for a in APELLIDOS]
    rnd.shuffle(combos)
    alumnos = []
    for i in range(n_alumnos):
        gid = (i % len(GRUPOS)) + 1
        alta = INICIO + timedelta(days=int(rnd.triangular(0, 150, 5)))
        baja = None
        if rnd.random() < 0.18:
            baja = alta + timedelta(days=rnd.randint(35, 160))
            if baja > FIN - timedelta(days=14):
                baja = None
        alumnos.append({
            "id": i + 1, "nombre": combos[i], "gid": gid, "alta": alta, "baja": baja,
            "p": min(0.97, max(0.4, rnd.gauss(0.78, 0.12))),
        })
    cur.executemany(
        "INSERT INTO alumnos (id, nombre, grupo_id, fecha_alta, fecha_baja) VALUES (?,?,?,?,?)",
        [(a["id"], a["nombre"], a["gid"], a["alta"].isoformat(),
          a["baja"].isoformat() if a["baja"] else None) for a in alumnos],
    )

    # --- Asistencia: sólo clases dictadas durante la inscripción. ---
    clases = cur.execute("SELECT id, grupo_id, fecha FROM clases WHERE dictada = 1 ORDER BY fecha").fetchall()
    por_alumno = {}
    for a in alumnos:
        propias = [(cid, f) for cid, gid, f in clases
                   if gid == a["gid"] and f >= a["alta"].isoformat()
                   and (a["baja"] is None or f <= a["baja"].isoformat())]
        por_alumno[a["id"]] = propias

    # Algunos alumnos activos dejan de venir en las últimas semanas (riesgo de abandono).
    activos = [a for a in alumnos if a["baja"] is None and len(por_alumno[a["id"]]) > 10]
    en_riesgo = {a["id"]: rnd.randint(3, 5) for a in rnd.sample(activos, 5)}

    filas = []
    for a in alumnos:
        propias = por_alumno[a["id"]]
        for idx, (cid, _) in enumerate(propias):
            faltan_al_final = en_riesgo.get(a["id"], 0)
            if faltan_al_final and idx >= len(propias) - faltan_al_final:
                presente = 0
            else:
                presente = 1 if rnd.random() < a["p"] else 0
            filas.append((cid, a["id"], presente))
    cur.executemany("INSERT INTO asistencias (clase_id, alumno_id, presente) VALUES (?,?,?)", filas)

    # --- Pagos: una cuota por mes inscripto; unos pocos alumnos adeudan los últimos meses. ---
    ultimo_periodo = HOY.strftime("%Y-%m")
    morosos = {a["id"]: rnd.randint(2, 4) for a in rnd.sample(
        [a for a in alumnos if a["baja"] is None], 7)}
    pagos = []
    for a in alumnos:
        desde = a["alta"].strftime("%Y-%m")
        hasta = min(ultimo_periodo, a["baja"].strftime("%Y-%m")) if a["baja"] else ultimo_periodo
        periodos = list(_meses(desde, hasta))
        for k, per in enumerate(periodos):
            if a["id"] in morosos and k >= len(periodos) - morosos[a["id"]]:
                continue
            if rnd.random() < 0.04:       # olvido puntual
                continue
            anio, mes = map(int, per.split("-"))
            dia_pago = date(anio, mes, rnd.randint(1, 12))
            pagos.append((a["id"], per, precios[a["gid"]], dia_pago.isoformat(), rnd.choice(MEDIOS)))
    cur.executemany(
        "INSERT INTO pagos (alumno_id, periodo, monto, fecha_pago, medio) VALUES (?,?,?,?,?)", pagos)
    conn.commit()
