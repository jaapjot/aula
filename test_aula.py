"""Pruebas de Aula. Se corren con:  python test_aula.py

Usan una base chica armada a mano, donde cada resultado esperado se puede
calcular con lápiz y papel, y además chequean que los datos generados sean
coherentes.
"""
import sqlite3
import unittest

import aula
import datos

HOY = "2026-10-31"


def base_chica():
    """1 grupo ($10.000), alumno A activo y alumno B dado de baja el 10-sep."""
    conn = aula.crear_base(":memory:", con_datos=False)
    conn.execute("INSERT INTO grupos VALUES (1,'Silla · lunes','Salón',0,'10:00',10000)")
    conn.execute("INSERT INTO alumnos VALUES (1,'Ana A',1,'2026-08-05',NULL)")
    conn.execute("INSERT INTO alumnos VALUES (2,'Beto B',1,'2026-08-05','2026-09-10')")
    clases = [(1, "2026-09-07", 1), (2, "2026-10-02", 0), (3, "2026-10-05", 1),
              (4, "2026-10-12", 1), (5, "2026-10-19", 1), (6, "2026-10-26", 1)]
    conn.executemany("INSERT INTO clases VALUES (?,1,?,?)", clases)
    # Ana: viene el 7/9 y el 5/10, y falta las últimas 3. Beto: viene el 7/9 y se va.
    asist = [(1, 1, 1), (1, 2, 1), (3, 1, 1), (4, 1, 0), (5, 1, 0), (6, 1, 0)]
    conn.executemany("INSERT INTO asistencias VALUES (?,?,?)", asist)
    pagos = [(1, "2026-08", 10000, "2026-08-03", "efectivo"),
             (1, "2026-10", 10000, "2026-10-04", "efectivo"),      # Ana no pagó septiembre
             (2, "2026-08", 10000, "2026-08-06", "transferencia"),
             (2, "2026-09", 10000, "2026-09-02", "transferencia")]
    conn.executemany("INSERT INTO pagos (alumno_id, periodo, monto, fecha_pago, medio) VALUES (?,?,?,?,?)", pagos)
    conn.commit()
    return conn


class ConsultasSobreBaseChica(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = base_chica()
        cls.res = aula.analizar(cls.conn, HOY)

    def test_ingresos_mensuales(self):
        self.assertEqual([(f["periodo"], f["total"], f["pagos"]) for f in self.res["ingresos_mensuales"]],
                         [("2026-08", 20000, 2), ("2026-09", 10000, 1), ("2026-10", 10000, 1)])

    def test_asistencia_del_grupo_ignora_clases_suspendidas(self):
        g = self.res["asistencia_por_grupo"][0]
        self.assertEqual(g["clases_dictadas"], 5)       # la del 2/10 no cuenta
        self.assertEqual(g["asistencia_pct"], 50.0)     # 3 presentes de 6 registros

    def test_asistencia_mensual(self):
        self.assertEqual({f["mes"]: f["asistencia_pct"] for f in self.res["asistencia_mensual"]},
                         {"2026-09": 100.0, "2026-10": 25.0})

    def test_riesgo_de_abandono_detecta_a_ana(self):
        r = self.res["riesgo_abandono"]
        self.assertEqual([f["nombre"] for f in r], ["Ana A"])
        self.assertEqual(r[0]["ultima_asistencia"], "2026-10-05")

    def test_riesgo_no_incluye_a_quien_ya_se_dio_de_baja(self):
        self.assertNotIn("Beto B", [f["nombre"] for f in self.res["riesgo_abandono"]])

    def test_deuda_es_solo_septiembre_de_ana(self):
        d = self.res["deuda"]
        self.assertEqual(len(d), 1)
        self.assertEqual((d[0]["nombre"], d[0]["cuotas_adeudadas"], d[0]["monto_adeudado"], d[0]["primera_cuota"]),
                         ("Ana A", 1, 10000, "2026-09"))

    def test_retencion(self):
        r = self.res["retencion_por_grupo"][0]
        self.assertEqual((r["inscriptos"], r["activos"], r["retencion_pct"]), (2, 1, 50.0))

    def test_kpis(self):
        k = self.res["kpis"][0]
        self.assertEqual((k["alumnos_activos"], k["grupos"], k["asistencia_4_semanas"],
                          k["cobrado_mes"], k["clases_suspendidas"]), (1, 1, 25.0, 10000, 1))

    def test_vista_asistencia_por_alumno(self):
        filas = {f["nombre"]: dict(f) for f in self.conn.execute("SELECT * FROM v_asistencia_alumno")}
        self.assertEqual((filas["Ana A"]["clases"], filas["Ana A"]["asistencia_pct"]), (5, 40.0))
        self.assertEqual((filas["Beto B"]["clases"], filas["Beto B"]["asistencia_pct"]), (1, 100.0))

    def test_cambiar_la_fecha_de_corte_cambia_el_resultado(self):
        # A fines de septiembre Ana todavía no estaba en riesgo.
        res = aula.analizar(self.conn, "2026-09-30")
        self.assertEqual(res["riesgo_abandono"], [])


class Restricciones(unittest.TestCase):
    def setUp(self):
        self.conn = base_chica()

    def test_no_se_puede_pagar_dos_veces_el_mismo_mes(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO pagos (alumno_id, periodo, monto, fecha_pago, medio) "
                              "VALUES (1,'2026-08',10000,'2026-08-09','efectivo')")

    def test_asistencia_solo_0_o_1(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO asistencias VALUES (3, 2, 2)")

    def test_baja_no_puede_ser_anterior_al_alta(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO alumnos VALUES (9,'X',1,'2026-05-10','2026-05-01')")

    def test_alumno_necesita_un_grupo_existente(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO alumnos VALUES (9,'X',99,'2026-05-10',NULL)")

    def test_medio_de_pago_valido(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("INSERT INTO pagos (alumno_id, periodo, monto, fecha_pago, medio) "
                              "VALUES (1,'2026-11',10000,'2026-11-02','trueque')")


class DatosGenerados(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = aula.crear_base(":memory:")

    def q(self, sql):
        return [tuple(f) for f in self.conn.execute(sql)]

    def test_misma_semilla_misma_base(self):
        otra = aula.crear_base(":memory:")
        for tabla in ("alumnos", "asistencias", "pagos", "clases"):
            a = self.q(f"SELECT * FROM {tabla} ORDER BY 1,2")
            b = [tuple(f) for f in otra.execute(f"SELECT * FROM {tabla} ORDER BY 1,2")]
            self.assertEqual(a, b, tabla)

    def test_tamanos(self):
        self.assertEqual(self.q("SELECT COUNT(*) FROM alumnos")[0][0], 72)
        self.assertEqual(self.q("SELECT COUNT(*) FROM grupos")[0][0], len(datos.GRUPOS))

    def test_nombres_unicos(self):
        self.assertEqual(self.q("SELECT COUNT(DISTINCT nombre) FROM alumnos")[0][0], 72)

    def test_no_hay_asistencia_en_clases_suspendidas(self):
        n = self.q("SELECT COUNT(*) FROM asistencias a JOIN clases c ON c.id=a.clase_id WHERE c.dictada=0")[0][0]
        self.assertEqual(n, 0)

    def test_asistencia_solo_dentro_de_la_inscripcion(self):
        n = self.q("""SELECT COUNT(*) FROM asistencias a
                      JOIN clases c ON c.id=a.clase_id JOIN alumnos al ON al.id=a.alumno_id
                      WHERE c.fecha < al.fecha_alta OR (al.fecha_baja IS NOT NULL AND c.fecha > al.fecha_baja)
                         OR c.grupo_id <> al.grupo_id""")[0][0]
        self.assertEqual(n, 0)

    def test_no_hay_pagos_posteriores_a_la_baja(self):
        n = self.q("""SELECT COUNT(*) FROM pagos p JOIN alumnos al ON al.id=p.alumno_id
                      WHERE al.fecha_baja IS NOT NULL AND p.periodo > substr(al.fecha_baja,1,7)""")[0][0]
        self.assertEqual(n, 0)

    def test_el_monto_pagado_es_el_precio_del_grupo(self):
        n = self.q("""SELECT COUNT(*) FROM pagos p JOIN alumnos al ON al.id=p.alumno_id
                      JOIN grupos g ON g.id=al.grupo_id WHERE p.monto <> g.precio_mensual""")[0][0]
        self.assertEqual(n, 0)

    def test_el_informe_encuentra_casos_para_mostrar(self):
        res = aula.analizar(self.conn, datos.HOY.isoformat())
        self.assertGreater(len(res["riesgo_abandono"]), 0)
        self.assertGreater(len(res["deuda"]), 0)
        self.assertEqual(len(res["asistencia_por_grupo"]), len(datos.GRUPOS))


class Informe(unittest.TestCase):
    def test_escapa_el_html_de_los_nombres(self):
        conn = base_chica()
        conn.execute("UPDATE alumnos SET nombre='<script>alert(1)</script>' WHERE id=1")
        html = aula.render_informe(aula.analizar(conn, HOY), HOY)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_el_informe_marca_que_los_datos_son_ficticios(self):
        html = aula.render_informe(aula.analizar(base_chica(), HOY), HOY)
        self.assertIn("datos ficticios", html.lower())

    def test_formato_de_plata_argentino(self):
        self.assertEqual(aula.plata(1234567), "$ 1.234.567")
        self.assertEqual(aula.plata(0), "$ 0")


if __name__ == "__main__":
    unittest.main(verbosity=1)
