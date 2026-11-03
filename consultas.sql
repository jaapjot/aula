-- Aula · consultas de análisis
-- Cada consulta empieza con "-- name: <nombre>" y la carga aula.py.
-- Parámetro común: :hoy (fecha de corte, formato AAAA-MM-DD).

-- name: ingresos_mensuales
-- Dinero cobrado por mes de cuota y cantidad de pagos.
SELECT periodo, SUM(monto) AS total, COUNT(*) AS pagos
FROM pagos
GROUP BY periodo
ORDER BY periodo;

-- name: asistencia_por_grupo
-- Porcentaje de presentes sobre las clases efectivamente dictadas.
SELECT g.id,
       g.nombre,
       g.sede,
       COUNT(DISTINCT c.id)  AS clases_dictadas,
       COUNT(DISTINCT a.alumno_id) AS alumnos,
       ROUND(100.0 * SUM(a.presente) / COUNT(*), 1) AS asistencia_pct
FROM grupos g
JOIN clases c      ON c.grupo_id = g.id AND c.dictada = 1 AND c.fecha <= :hoy
JOIN asistencias a ON a.clase_id = c.id
GROUP BY g.id
ORDER BY asistencia_pct DESC;

-- name: asistencia_mensual
-- Evolución de la asistencia general mes a mes.
SELECT substr(c.fecha, 1, 7) AS mes,
       ROUND(100.0 * SUM(a.presente) / COUNT(*), 1) AS asistencia_pct
FROM clases c
JOIN asistencias a ON a.clase_id = c.id
WHERE c.dictada = 1 AND c.fecha <= :hoy
GROUP BY mes
ORDER BY mes;

-- name: riesgo_abandono
-- Alumnos activos que faltaron a sus últimas 3 clases.
-- ROW_NUMBER numera las clases de cada alumno de la más nueva a la más vieja.
WITH ultimas AS (
    SELECT a.alumno_id,
           a.presente,
           c.fecha,
           ROW_NUMBER() OVER (PARTITION BY a.alumno_id ORDER BY c.fecha DESC) AS rn
    FROM asistencias a
    JOIN clases c ON c.id = a.clase_id
    WHERE c.dictada = 1 AND c.fecha <= :hoy
)
SELECT al.id,
       al.nombre,
       g.nombre AS grupo,
       (SELECT MAX(c2.fecha)
          FROM asistencias a2
          JOIN clases c2 ON c2.id = a2.clase_id
         WHERE a2.alumno_id = al.id AND a2.presente = 1) AS ultima_asistencia
FROM ultimas u
JOIN alumnos al ON al.id = u.alumno_id
JOIN grupos g   ON g.id = al.grupo_id
WHERE u.rn <= 3 AND al.fecha_baja IS NULL
GROUP BY al.id
HAVING COUNT(*) = 3 AND SUM(u.presente) = 0
ORDER BY ultima_asistencia;

-- name: deuda
-- Cuotas esperadas (un mes por cada mes que el alumno estuvo inscripto)
-- que no tienen un pago. La CTE recursiva genera la lista de meses.
WITH RECURSIVE meses(periodo) AS (
    SELECT (SELECT MIN(substr(fecha_alta, 1, 7)) FROM alumnos)
    UNION ALL
    SELECT strftime('%Y-%m', date(periodo || '-01', '+1 month'))
    FROM meses
    WHERE periodo < strftime('%Y-%m', :hoy)
),
esperadas AS (
    SELECT al.id AS alumno_id, m.periodo, g.precio_mensual
    FROM alumnos al
    JOIN grupos g ON g.id = al.grupo_id
    JOIN meses m  ON m.periodo >= substr(al.fecha_alta, 1, 7)
                 AND (al.fecha_baja IS NULL OR m.periodo <= substr(al.fecha_baja, 1, 7))
)
SELECT al.id,
       al.nombre,
       g.nombre AS grupo,
       COUNT(*) AS cuotas_adeudadas,
       SUM(e.precio_mensual) AS monto_adeudado,
       MIN(e.periodo) AS primera_cuota
FROM esperadas e
LEFT JOIN pagos p ON p.alumno_id = e.alumno_id AND p.periodo = e.periodo
JOIN alumnos al   ON al.id = e.alumno_id
JOIN grupos g     ON g.id = al.grupo_id
WHERE p.id IS NULL AND al.fecha_baja IS NULL
GROUP BY al.id
ORDER BY cuotas_adeudadas DESC, monto_adeudado DESC, al.nombre;

-- name: retencion_por_grupo
-- Cuántos alumnos siguen activos sobre el total que alguna vez se inscribió.
SELECT g.nombre,
       COUNT(*) AS inscriptos,
       SUM(al.fecha_baja IS NULL) AS activos,
       ROUND(100.0 * SUM(al.fecha_baja IS NULL) / COUNT(*), 1) AS retencion_pct
FROM grupos g
JOIN alumnos al ON al.grupo_id = g.id
GROUP BY g.id
ORDER BY retencion_pct DESC;

-- name: kpis
-- Números de cabecera del informe.
SELECT
    (SELECT COUNT(*) FROM alumnos WHERE fecha_baja IS NULL)                      AS alumnos_activos,
    (SELECT COUNT(*) FROM grupos)                                                AS grupos,
    (SELECT ROUND(100.0 * SUM(a.presente) / COUNT(*), 1)
       FROM asistencias a JOIN clases c ON c.id = a.clase_id
      WHERE c.dictada = 1 AND c.fecha > date(:hoy, '-28 days') AND c.fecha <= :hoy) AS asistencia_4_semanas,
    (SELECT COALESCE(SUM(monto), 0) FROM pagos WHERE periodo = strftime('%Y-%m', :hoy)) AS cobrado_mes,
    (SELECT COUNT(*) FROM clases WHERE dictada = 0 AND fecha <= :hoy)           AS clases_suspendidas;
