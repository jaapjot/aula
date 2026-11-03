-- Aula · esquema de la base de datos (SQLite)
-- Modelo: un alumno pertenece a un grupo; cada grupo tiene clases semanales;
-- por cada clase dictada se registra la asistencia de los alumnos inscriptos;
-- cada alumno paga una cuota por mes.

PRAGMA foreign_keys = ON;

CREATE TABLE grupos (
    id               INTEGER PRIMARY KEY,
    nombre           TEXT    NOT NULL UNIQUE,
    sede             TEXT    NOT NULL,
    dia_semana       INTEGER NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),  -- 0 = lunes
    hora             TEXT    NOT NULL CHECK (hora GLOB '[0-2][0-9]:[0-5][0-9]'),
    precio_mensual   INTEGER NOT NULL CHECK (precio_mensual > 0)
);

CREATE TABLE alumnos (
    id          INTEGER PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    grupo_id    INTEGER NOT NULL REFERENCES grupos(id),
    fecha_alta  TEXT    NOT NULL CHECK (fecha_alta GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]'),
    fecha_baja  TEXT    CHECK (fecha_baja IS NULL OR fecha_baja >= fecha_alta)
);

CREATE TABLE clases (
    id        INTEGER PRIMARY KEY,
    grupo_id  INTEGER NOT NULL REFERENCES grupos(id),
    fecha     TEXT    NOT NULL,
    dictada   INTEGER NOT NULL CHECK (dictada IN (0, 1)),   -- 0 = suspendida (feriado, lluvia…)
    UNIQUE (grupo_id, fecha)
);

CREATE TABLE asistencias (
    clase_id   INTEGER NOT NULL REFERENCES clases(id),
    alumno_id  INTEGER NOT NULL REFERENCES alumnos(id),
    presente   INTEGER NOT NULL CHECK (presente IN (0, 1)),
    PRIMARY KEY (clase_id, alumno_id)
);

CREATE TABLE pagos (
    id          INTEGER PRIMARY KEY,
    alumno_id   INTEGER NOT NULL REFERENCES alumnos(id),
    periodo     TEXT    NOT NULL CHECK (periodo GLOB '[0-9][0-9][0-9][0-9]-[0-1][0-9]'),  -- mes que se paga
    monto       INTEGER NOT NULL CHECK (monto > 0),
    fecha_pago  TEXT    NOT NULL,
    medio       TEXT    NOT NULL CHECK (medio IN ('efectivo', 'transferencia', 'mercado pago')),
    UNIQUE (alumno_id, periodo)          -- no se puede pagar dos veces el mismo mes
);

-- Los accesos más comunes son por grupo y por alumno.
CREATE INDEX idx_alumnos_grupo   ON alumnos(grupo_id);
CREATE INDEX idx_clases_grupo    ON clases(grupo_id, fecha);
CREATE INDEX idx_asist_alumno    ON asistencias(alumno_id);

-- Asistencia de cada alumno sobre las clases dictadas que le tocaron.
CREATE VIEW v_asistencia_alumno AS
SELECT al.id AS alumno_id,
       al.nombre,
       g.nombre AS grupo,
       COUNT(*)  AS clases,
       SUM(a.presente) AS presentes,
       ROUND(100.0 * SUM(a.presente) / COUNT(*), 1) AS asistencia_pct
FROM alumnos al
JOIN grupos g       ON g.id = al.grupo_id
JOIN asistencias a  ON a.alumno_id = al.id
JOIN clases c       ON c.id = a.clase_id AND c.dictada = 1
GROUP BY al.id;
