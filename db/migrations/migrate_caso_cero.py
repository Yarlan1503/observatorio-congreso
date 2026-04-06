#!/usr/bin/env python3
"""
migrate_caso_cero.py — Migración del caso cero al Observatorio del Congreso.

Caso: Reforma Político-Electoral de Sheinbaum, 11/mar/2026.
Idempotente: usa INSERT OR IGNORE. No modifica ni borra datos existentes.
Sin dependencias externas: solo sqlite3 de stdlib.

Uso:  python db/migrate_caso_cero.py   (desde la raíz del proyecto)
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "congreso.db")

# Fechas de la LXVI Legislatura
LEG_START = "2024-09-01"
LEG_END = "2027-08-31"


# ============================================================
# 1. person — Legisladores y actores políticos (~27 registros)
# ============================================================

PERSONS = [
    # --- Disidentes Morena: votaron EN CONTRA (3) ---
    (
        "P01",
        "Giselle Arellano Ávila",
        "1980-01-01",
        "F",
        "plurinominal",
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "La única verdadera disidente de Morena. Ex-PAN (2012-2013), "
        "ex-PT (2016-2018). Empresaria inmobiliaria en EE.UU. "
        "24 reservas al Presupuesto 2026. No tiene corriente interna identificada.",
    ),
    (
        "P02",
        "Alejandra Chedraui Peralta",
        "1989-01-01",
        "F",
        "plurinominal",
        None,
        LEG_START,
        LEG_END,
        None,
        "baja",
        "Pevemista integrada a bancada Morena desde día 1 de LXVI. "
        "Ex regidora Huixquilucan. 16 iniciativas registradas. "
        "Votó con su partido de origen (PVEM) contra la reforma.",
    ),
    (
        "P03",
        "Santy Montemayor Castillo",
        "1976-01-01",
        "F",
        "plurinominal",
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Pevemista reelecta. Pasó a bancada Morena en sept 2024. "
        "Ex priista en Q. Roo. Diputada plurinominal desde 2021. "
        "Calificada como 'la traidora más visible del bloque oficialista local' en Q. Roo.",
    ),
    # --- Disidentes Morena: AUSENTES (4) ---
    (
        "P04",
        "Olga María del Carmen Sánchez Cordero Dávila",
        "1947-01-01",
        "F",
        "plurinominal",
        4,
        LEG_START,
        LEG_END,
        "institucionalista",
        "baja",
        "Ex ministra SCJN (1995-2015, nombrada por Zedillo). "
        "Secretaria de Gobernación de AMLO (2018-2021). "
        "Senadora (2018-2024). Presidenta del Senado (2021-2022). "
        "Ausencia deliberada: estuvo en pleno pero se retiró antes de votar. "
        "Mismo patrón que en reforma judicial.",
    ),
    (
        "P05",
        "Manuel de Jesús Espino Barrientos",
        "1959-01-01",
        "M",
        "plurinominal",
        None,
        LEG_START,
        LEG_END,
        "AMLO",
        "baja",
        "Ex presidente nacional del PAN (2005-2007). Expulsado del PAN en 2011. "
        "Pasó por MC. Converso leal a AMLO con cargos importantes. "
        "Ausencia genuina: derrame cerebral oct 2025.",
    ),
    (
        "P06",
        "J. Jesús Jiménez",
        None,
        "M",
        "suplente",
        2,
        LEG_START,
        LEG_END,
        None,
        None,
        "Suplente de Napoleón Gómez Urrutia (líder SNTMMSRM). "
        "Ocupó escaño desde sept 2025. Operador sindical. "
        "Motivo de ausencia indeterminado.",
    ),
    (
        "P07",
        "Iván Peña Vidal",
        None,
        "M",
        "mayoria_relativa",
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Ex-PRD, ex-PVEM. 20 años en administración municipal tabasqueña. "
        "Coordinó campañas Morena 2018 y 2021. "
        "Diputado MR Distrito II Tabasco. Ausencia indeterminada.",
    ),
    # --- Disidente PT: votó A FAVOR (1) ---
    (
        "P08",
        "Jesús Roberto Corral Ordoñez",
        None,
        "M",
        "mayoria_relativa",
        None,
        LEG_START,
        LEG_END,
        "AMLO",
        "media",
        "Ex-PRD. Diputado federal MR Distrito IX Chihuahua por PT dentro "
        "de coalición SHH. 'Diputado prestado': electo por PT pero lealtad "
        "real al proyecto morenista. No depende de plurinominales del PT.",
    ),
    # --- Disidentes PVEM: votaron A FAVOR (12) ---
    (
        "P09",
        "José Braña Mojica",
        None,
        "M",
        "mayoria_relativa",
        None,
        LEG_START,
        LEG_END,
        "AMLO",
        "baja",
        "CASO MÁS SIMBÓLICO: Primo hermano de AMLO. Electo por Morena, "
        "migró al PVEM sept 2024. Ex diputado local PT Tamaulipas. "
        "Coordinó campaña presidencial AMLO 2006 y campaña al Senado de Villarreal 2018.",
    ),
    (
        "P10",
        "Manuel Cota Cárdenas",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        "AMLO",
        "baja",
        "Electo por Morena, migró al PVEM sept 2024. "
        "Hijo de Leonel Cota Montaño, subsecretario de Agricultura del gobierno AMLO/Sheinbaum. "
        "Portavoz del GPPVEM.",
    ),
    (
        "P11",
        "Mario López Hernández",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Electo por Morena, migró al PVEM sept 2024. "
        "Ex alcalde de Matamoros, Tamaulipas. "
        "Presión/coordinación del gobernador Villarreal.",
    ),
    (
        "P12",
        "Anabel Acosta",
        None,
        "F",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Electa por Morena, migró al PVEM sept 2024. Ex priista. "
        "Ex senadora suplente de Claudia Pavlovich. "
        "Carrera construida en entorno Pavlovich-4T.",
    ),
    (
        "P13",
        "María del Carmen Cabrera Lagunas",
        None,
        "F",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Diputada por PES en LXIV Legislatura. "
        "Secretaria de Bienestar en gobierno Evelyn Salgado (Guerrero). "
        "Lealtad vía aparato Bienestar/Morena.",
    ),
    (
        "P14",
        "Iván Marín Rangel",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Electo por Morena, migró al PVEM al inicio de legislatura. "
        "Ex Secretaría de Bienestar federal. Portavoz del GPPVEM.",
    ),
    (
        "P15",
        "Alejandro Pérez Cuéllar",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Electo por Morena, migró al PVEM al inicio de legislatura. "
        "Hermano de Cruz Pérez Cuéllar, alcalde de Ciudad Juárez (Morena).",
    ),
    (
        "P16",
        "Denisse Guzmán González",
        None,
        "F",
        "suplente",
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Suplente de diputada morenista María del Carmen Pinete "
        "(fallecida abril 2025). Posible lealtad al morenismo original.",
    ),
    (
        "P17",
        "Ruth Silva Andraca",
        None,
        "F",
        "suplente",
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Suplente de Ana María Lomelí, coordinadora de comunicación del "
        "gobierno Clara Brugada (CDMX). Vínculo con estructura morenista CDMX.",
    ),
    (
        "P18",
        "Carlos Canturosas Villarreal",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "media",
        "Tamaulipas (Nuevo Laredo). Ex panista. Ex alcalde de Nuevo Laredo. "
        "Pasó por Morena y regresó al PVEM. Su hermana Blanca Lilia Canturosas "
        "es presidenta municipal PAN actual.",
    ),
    (
        "P19",
        "Blanca Hernández Rodríguez",
        None,
        "F",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        "baja",
        "Votó a favor de todas las 162 iniciativas votadas en LXVI Legislatura "
        "antes de la reforma electoral. Patrón de lealtad casi absoluta al bloque oficialista.",
    ),
    (
        "P20",
        "Hilda Licerio Valdés",
        None,
        "F",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Profesora. Ex representante del PANAL (partido del magisterio, vinculado al SNTE). "
        "Posible lealtad al proyecto federal morenista vía vínculos magisteriales.",
    ),
    # --- Actores adicionales del Plan B y reacciones (7) ---
    (
        "P21",
        "Félix Salgado Macedonio",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Senador Morena. Dijo que los que votaron en contra 'van a pasar al muro de la traición'.",
    ),
    (
        "P22",
        "Carlos Puente Salas",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Coordinador del Grupo Parlamentario del PVEM en Diputados. "
        "Hizo los cambios en la planilla de diputados prestados. "
        "Argumentó que reformas electorales requieren consenso.",
    ),
    (
        "P23",
        "Hamlet Almaguer",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Consejero nacional de Morena. Pidió a la CNHJ investigar "
        "a Sánchez Cordero y las 3 diputadas que votaron en contra.",
    ),
    (
        "P24",
        "Reginaldo Sandoval",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Coordinador del Grupo Parlamentario del PT en Diputados. "
        "Anunció públicamente desde la tribuna que su grupo votaría en contra.",
    ),
    (
        "P25",
        "Raúl Bolaños Cacho",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Diputado PVEM. Única abstención en la votación de la reforma electoral.",
    ),
    (
        "P26",
        "Pedro Vázquez González",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Diputado PT. Denunció 'linchamiento mediático' contra su partido "
        "por defender espacios para voces minoritarias.",
    ),
    (
        "P27",
        "Manuel Velasco Coello",
        None,
        "M",
        None,
        None,
        LEG_START,
        LEG_END,
        None,
        None,
        "Coordinador del PVEM en el Senado. Advirtió a Morena: "
        "'Es decisión de cada legislador permanecer o no en los grupos parlamentarios'.",
    ),
]

PERSON_SQL = """
INSERT OR IGNORE INTO person
    (id, nombre, fecha_nacimiento, genero, curul_tipo, circunscripcion,
     start_date, end_date, corriente_interna, vulnerabilidad, observaciones)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================
# 2. membership — Pertenencia a organizaciones (~63 registros)
# ============================================================

MEMBERSHIPS = [
    # --- P01 Giselle Arellano ---
    (
        "M01",
        "P01",
        "O01",
        "militante",
        "Militante Morena desde 2024",
        LEG_START,
        None,
        None,
    ),
    ("M02", "P01", "O08", "diputado", "Diputada plurinominal", LEG_START, None, None),
    (
        "M03",
        "P01",
        "O04",
        "militante",
        "Militante PAN 2012-2013",
        "2012-01-01",
        "2013-12-31",
        None,
    ),
    (
        "M04",
        "P01",
        "O02",
        "militante",
        "Militante PT 2016-2018",
        "2016-01-01",
        "2018-12-31",
        None,
    ),
    # --- P02 Alejandra Chedraui ---
    (
        "M05",
        "P02",
        "O03",
        "militante",
        "Militante PVEM desde 2015",
        "2015-01-01",
        None,
        None,
    ),
    (
        "M06",
        "P02",
        "O08",
        "diputado",
        "Diputada en bancada Morena (integrada)",
        LEG_START,
        None,
        "O03",
    ),
    # --- P03 Santy Montemayor ---
    ("M07", "P03", "O03", "militante", "Militante PVEM", "2024-01-01", None, None),
    (
        "M08",
        "P03",
        "O08",
        "diputado",
        "Diputada en bancada Morena (reasignada sept 2024)",
        LEG_START,
        None,
        "O03",
    ),
    # --- P04 Olga Sánchez Cordero ---
    (
        "M09",
        "P04",
        "O08",
        "diputado",
        "Diputada plurinominal, Morena",
        LEG_START,
        None,
        None,
    ),
    (
        "M10",
        "P04",
        "O09",
        "senador",
        "Senadora por Lista Nacional (2 periodos)",
        "2018-09-01",
        "2024-08-31",
        None,
    ),
    ("M11", "P04", "O08", "coordinador", None, LEG_START, None, None),
    # --- P05 Manuel Espino ---
    (
        "M12",
        "P05",
        "O01",
        "militante",
        "Militante Morena desde 2021",
        "2021-01-01",
        None,
        None,
    ),
    (
        "M13",
        "P05",
        "O08",
        "diputado",
        "Diputado plurinominal, Morena",
        LEG_START,
        None,
        None,
    ),
    (
        "M14",
        "P05",
        "O04",
        "militante",
        "Militante PAN 1978-2011 (expulsado)",
        "1978-01-01",
        "2011-12-31",
        None,
    ),
    (
        "M15",
        "P05",
        "O06",
        "militante",
        "Militante MC 2015-2018",
        "2015-01-01",
        "2018-12-31",
        None,
    ),
    # --- P06 J. Jesús Jiménez ---
    (
        "M16",
        "P06",
        "O01",
        "suplente",
        "Suplente de N. Gómez Urrutia, Morena",
        "2025-09-01",
        None,
        None,
    ),
    (
        "M17",
        "P06",
        "O08",
        "suplente",
        "Diputado suplente, circunscripción 2",
        "2025-09-01",
        None,
        None,
    ),
    # --- P07 Iván Peña Vidal ---
    ("M18", "P07", "O01", "militante", "Militante Morena", "2024-01-01", None, None),
    (
        "M19",
        "P07",
        "O08",
        "diputado",
        "Diputado MR Distrito II Tabasco",
        LEG_START,
        None,
        None,
    ),
    (
        "M20",
        "P07",
        "O07",
        "militante",
        "Ex-PRD (precandidato 2009)",
        "2000-01-01",
        "2010-12-31",
        None,
    ),
    (
        "M21",
        "P07",
        "O03",
        "militante",
        "Ex-PVEM (candidato municipal 2015)",
        "2012-01-01",
        "2018-12-31",
        None,
    ),
    # --- P08 Jesús Roberto Corral Ordoñez ---
    ("M22", "P08", "O02", "militante", "Militante PT", "2024-01-01", None, None),
    (
        "M23",
        "P08",
        "O08",
        "diputado",
        "Diputado MR Distrito IX Chihuahua",
        LEG_START,
        None,
        "O01",
    ),
    ("M24", "P08", "O07", "militante", "Ex-PRD", "2000-01-01", "2015-12-31", None),
    # --- P09 José Braña Mojica ---
    (
        "M25",
        "P09",
        "O03",
        "militante",
        "Militante PVEM (migrado de Morena sept 2024)",
        LEG_START,
        None,
        None,
    ),
    (
        "M26",
        "P09",
        "O08",
        "diputado",
        "Diputado MR Tamaulipas, bancada PVEM",
        LEG_START,
        None,
        "O01",
    ),
    # --- P10 Manuel Cota Cárdenas ---
    (
        "M27",
        "P10",
        "O03",
        "militante",
        "Militante PVEM (migrado de Morena sept 2024)",
        LEG_START,
        None,
        None,
    ),
    (
        "M28",
        "P10",
        "O08",
        "diputado",
        "Diputado BCS, bancada PVEM",
        LEG_START,
        None,
        "O01",
    ),
    # --- P11 Mario López Hernández ---
    (
        "M29",
        "P11",
        "O03",
        "militante",
        "Militante PVEM (migrado de Morena sept 2024)",
        LEG_START,
        None,
        None,
    ),
    (
        "M30",
        "P11",
        "O08",
        "diputado",
        "Diputado Tamaulipas, bancada PVEM",
        LEG_START,
        None,
        "O01",
    ),
    # --- P12 Anabel Acosta ---
    (
        "M31",
        "P12",
        "O03",
        "militante",
        "Militante PVEM (migrada de Morena sept 2024)",
        LEG_START,
        None,
        None,
    ),
    (
        "M32",
        "P12",
        "O08",
        "diputado",
        "Diputada Sonora, bancada PVEM",
        LEG_START,
        None,
        "O01",
    ),
    # --- P13 María del Carmen Cabrera Lagunas ---
    ("M33", "P13", "O03", "militante", "Militante PVEM", LEG_START, None, None),
    (
        "M34",
        "P13",
        "O08",
        "diputado",
        "Diputada Guerrero, bancada PVEM",
        LEG_START,
        None,
        None,
    ),
    # --- P14 Iván Marín Rangel ---
    (
        "M35",
        "P14",
        "O03",
        "militante",
        "Militante PVEM (migrado de Morena sept 2024)",
        LEG_START,
        None,
        None,
    ),
    (
        "M36",
        "P14",
        "O08",
        "diputado",
        "Diputado EdoMéx, bancada PVEM",
        LEG_START,
        None,
        "O01",
    ),
    # --- P15 Alejandro Pérez Cuéllar ---
    (
        "M37",
        "P15",
        "O03",
        "militante",
        "Militante PVEM (migrado de Morena sept 2024)",
        LEG_START,
        None,
        None,
    ),
    (
        "M38",
        "P15",
        "O08",
        "diputado",
        "Diputado Chihuahua, bancada PVEM",
        LEG_START,
        None,
        "O01",
    ),
    # --- P16 Denisse Guzmán González ---
    (
        "M39",
        "P16",
        "O03",
        "militante",
        "Militante PVEM (suplente de morenista fallecida)",
        "2025-04-01",
        None,
        None,
    ),
    (
        "M40",
        "P16",
        "O08",
        "suplente",
        "Diputada suplente, bancada PVEM",
        "2025-04-01",
        None,
        None,
    ),
    # --- P17 Ruth Silva Andraca ---
    (
        "M41",
        "P17",
        "O03",
        "militante",
        "Militante PVEM (suplente de Lomelí)",
        LEG_START,
        None,
        None,
    ),
    (
        "M42",
        "P17",
        "O08",
        "suplente",
        "Diputada suplente CDMX, bancada PVEM",
        LEG_START,
        None,
        None,
    ),
    # --- P18 Carlos Canturosas Villarreal ---
    (
        "M43",
        "P18",
        "O03",
        "militante",
        "Militante PVEM (regresó al Verde)",
        LEG_START,
        None,
        None,
    ),
    (
        "M44",
        "P18",
        "O08",
        "diputado",
        "Diputado Tamaulipas, bancada PVEM",
        LEG_START,
        None,
        None,
    ),
    # --- P19 Blanca Hernández Rodríguez ---
    ("M45", "P19", "O03", "militante", "Militante PVEM", LEG_START, None, None),
    ("M46", "P19", "O08", "diputado", "Diputada, bancada PVEM", LEG_START, None, None),
    # --- P20 Hilda Licerio Valdés ---
    (
        "M47",
        "P20",
        "O03",
        "militante",
        "Militante PVEM (ex PANAL/SNTE)",
        LEG_START,
        None,
        None,
    ),
    ("M48", "P20", "O08", "diputado", "Diputada, bancada PVEM", LEG_START, None, None),
    # --- P21 Félix Salgado Macedonio ---
    ("M49", "P21", "O01", "militante", "Senador Morena", LEG_START, None, None),
    ("M50", "P21", "O09", "senador", "Senador Morena", LEG_START, None, None),
    # --- P22 Carlos Puente Salas ---
    ("M51", "P22", "O03", "militante", "Coordinador GPPVEM", LEG_START, None, None),
    (
        "M52",
        "P22",
        "O03",
        "coordinador",
        "Coordinador Grupo Parlamentario PVEM en Diputados",
        LEG_START,
        None,
        None,
    ),
    # --- P23 Hamlet Almaguer ---
    (
        "M53",
        "P23",
        "O01",
        "militante",
        "Consejero nacional Morena",
        LEG_START,
        None,
        None,
    ),
    (
        "M54",
        "P23",
        "O01",
        "consejero",
        "Consejero nacional de Morena",
        LEG_START,
        None,
        None,
    ),
    # --- P24 Reginaldo Sandoval ---
    ("M55", "P24", "O02", "militante", "Coordinador GPPT", LEG_START, None, None),
    (
        "M56",
        "P24",
        "O02",
        "coordinador",
        "Coordinador Grupo Parlamentario PT en Diputados",
        LEG_START,
        None,
        None,
    ),
    # --- P25 Raúl Bolaños Cacho ---
    ("M57", "P25", "O03", "militante", "Diputado PVEM", LEG_START, None, None),
    ("M58", "P25", "O08", "diputado", "Diputado, bancada PVEM", LEG_START, None, None),
    # --- P26 Pedro Vázquez González ---
    ("M59", "P26", "O02", "militante", "Diputado PT", LEG_START, None, None),
    ("M60", "P26", "O08", "diputado", "Diputado, bancada PT", LEG_START, None, None),
    # --- P27 Manuel Velasco Coello ---
    (
        "M61",
        "P27",
        "O03",
        "militante",
        "Coordinador PVEM Senado",
        LEG_START,
        None,
        None,
    ),
    (
        "M62",
        "P27",
        "O03",
        "coordinador",
        "Coordinador Grupo Parlamentario PVEM en Senado",
        LEG_START,
        None,
        None,
    ),
    ("M63", "P27", "O09", "senador", "Senador PVEM", LEG_START, None, None),
]

MEMBERSHIP_SQL = """
INSERT OR IGNORE INTO membership
    (id, person_id, org_id, rol, label, start_date, end_date, on_behalf_of)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================
# 3. post — Cargos legislativos (~24 registros)
# ============================================================

POSTS = [
    # Diputados Cámara (O08)
    ("T01", "O08", "A32", "Diputada plurinominal, Zacatecas", LEG_START, LEG_END),
    ("T02", "O08", "A09", "Diputada plurinominal, CDMX", LEG_START, LEG_END),
    ("T03", "O08", "A23", "Diputada plurinominal, Quintana Roo", LEG_START, LEG_END),
    ("T04", "O08", "A09", "Diputada plurinominal, CDMX, Circ. 4", LEG_START, LEG_END),
    ("T05", "O08", "A10", "Diputado plurinominal, Durango", LEG_START, LEG_END),
    ("T06", "O08", None, "Diputado suplente, Circunscripción 2", LEG_START, LEG_END),
    ("T07", "O08", "A27", "Diputado MR Distrito II, Tabasco", LEG_START, LEG_END),
    ("T08", "O08", "A06", "Diputado MR Distrito IX, Chihuahua", LEG_START, LEG_END),
    ("T09", "O08", "A28", "Diputado MR, Tamaulipas", LEG_START, LEG_END),
    ("T10", "O08", "A03", "Diputado, Baja California Sur", LEG_START, LEG_END),
    ("T11", "O08", "A28", "Diputado, Tamaulipas", LEG_START, LEG_END),
    ("T12", "O08", "A26", "Diputada, Sonora", LEG_START, LEG_END),
    ("T13", "O08", "A13", "Diputada, Guerrero", LEG_START, LEG_END),
    ("T14", "O08", "A11", "Diputado, Estado de México", LEG_START, LEG_END),
    ("T15", "O08", "A06", "Diputado, Chihuahua", LEG_START, LEG_END),
    ("T16", "O08", None, "Diputada suplente", LEG_START, LEG_END),
    ("T17", "O08", "A09", "Diputada suplente, CDMX", LEG_START, LEG_END),
    ("T18", "O08", "A28", "Diputado, Tamaulipas", LEG_START, LEG_END),
    ("T19", "O08", None, "Diputada, bancada PVEM", LEG_START, LEG_END),
    ("T20", "O08", None, "Diputada, bancada PVEM", LEG_START, LEG_END),
    ("T21", "O08", None, "Diputado, bancada PVEM", LEG_START, LEG_END),
    ("T22", "O08", None, "Diputado, bancada PT", LEG_START, LEG_END),
    # Senadores (O09)
    ("T23", "O09", None, "Senador Morena", LEG_START, LEG_END),
    ("T24", "O09", None, "Senador PVEM", LEG_START, LEG_END),
]

POST_SQL = """
INSERT OR IGNORE INTO post
    (id, org_id, area_id, label, start_date, end_date)
VALUES (?, ?, ?, ?, ?, ?)
"""


# ============================================================
# 4. motion — Iniciativas legislativas (2 registros)
# ============================================================

MOTIONS = [
    (
        "Y01",
        "Iniciativa de Claudia Sheinbaum para modificar 11 artículos de la "
        "Constitución en materia político-electoral. Incluía: eliminación de "
        "diputados plurinominales, reducción de financiamiento público a "
        "partidos, eliminación de 32 senadurías de representación proporcional.",
        "reforma_constitucional",
        "mayoria_calificada",
        "rechazada",
        "2026-03-11",
        "LXVI Legislatura",
        None,
    ),
    (
        "Y02",
        "Iniciativa mixta: reformas constitucionales + leyes secundarias. "
        "Ejes: menos privilegios (topes salariales, recortes a instituciones "
        "electorales) + más participación (revocación de mandato adelantada). "
        "Retira puntos explosivos: no se tocan plurinominales, financiamiento "
        "ni senadurías de RP.",
        "reforma_constitucional",
        "mayoria_calificada",
        "pendiente",
        "2026-03-17",
        "LXVI Legislatura",
        None,
    ),
]

MOTION_SQL = """
INSERT OR IGNORE INTO motion
    (id, texto, clasificacion, requirement, result, date, legislative_session, fuente_url)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================
# 5. vote_event — Eventos de votación (2 registros)
# ============================================================

VOTE_EVENTS = [
    (
        "VE01",
        "Y01",
        "2026-03-11",
        "O08",
        "rechazada",
        None,
        501,
        "LXVI",
        "mayoria_calificada",
    ),
    (
        "VE02",
        "Y02",
        "2026-03-17",
        "O09",
        "pendiente",
        None,
        None,
        "LXVI",
        "mayoria_calificada",
    ),
]

VOTE_EVENT_SQL = """
INSERT OR IGNORE INTO vote_event
    (id, motion_id, start_date, organization_id, result, sitl_id,
     voter_count, legislatura, requirement)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================
# 6. vote — Votos individuales (~24 registros)
# ============================================================

VOTES = [
    # --- Disidentes Morena ---
    ("V01", "VE01", "P01", "en_contra", "Morena"),
    ("V02", "VE01", "P02", "en_contra", "Morena"),
    ("V03", "VE01", "P03", "en_contra", "Morena"),
    ("V04", "VE01", "P04", "ausente", "Morena"),
    ("V05", "VE01", "P05", "ausente", "Morena"),
    ("V06", "VE01", "P06", "ausente", "Morena"),
    ("V07", "VE01", "P07", "ausente", "Morena"),
    # --- Disidente PT ---
    ("V08", "VE01", "P08", "a_favor", "PT"),
    # --- Disidentes PVEM ---
    ("V09", "VE01", "P09", "a_favor", "PVEM"),
    ("V10", "VE01", "P10", "a_favor", "PVEM"),
    ("V11", "VE01", "P11", "a_favor", "PVEM"),
    ("V12", "VE01", "P12", "a_favor", "PVEM"),
    ("V13", "VE01", "P13", "a_favor", "PVEM"),
    ("V14", "VE01", "P14", "a_favor", "PVEM"),
    ("V15", "VE01", "P15", "a_favor", "PVEM"),
    ("V16", "VE01", "P16", "a_favor", "PVEM"),
    ("V17", "VE01", "P17", "a_favor", "PVEM"),
    ("V18", "VE01", "P18", "a_favor", "PVEM"),
    ("V19", "VE01", "P19", "a_favor", "PVEM"),
    ("V20", "VE01", "P20", "a_favor", "PVEM"),
    # --- Abstención ---
    ("V21", "VE01", "P25", "abstencion", "PVEM"),
    # --- Coordinadores que votaron en contra ---
    ("V22", "VE01", "P22", "en_contra", "PVEM"),
    ("V23", "VE01", "P24", "en_contra", "PT"),
    ("V24", "VE01", "P26", "en_contra", "PT"),
]

VOTE_SQL = """
INSERT OR IGNORE INTO vote
    (id, vote_event_id, voter_id, option, "group")
VALUES (?, ?, ?, ?, ?)
"""


# ============================================================
# 7. count — Conteos por grupo (12 registros)
# ============================================================

COUNTS = [
    ("C01", "VE01", "a_favor", 249, "O01"),
    ("C02", "VE01", "en_contra", 3, "O01"),
    ("C03", "VE01", "ausente", 4, "O01"),
    ("C04", "VE01", "a_favor", 12, "O03"),
    ("C05", "VE01", "en_contra", 49, "O03"),
    ("C06", "VE01", "abstencion", 1, "O03"),
    ("C07", "VE01", "a_favor", 1, "O02"),
    ("C08", "VE01", "en_contra", 50, "O02"),
    ("C09", "VE01", "en_contra", 72, "O04"),
    ("C10", "VE01", "en_contra", 35, "O05"),
    ("C11", "VE01", "en_contra", 27, "O06"),
    ("C12", "VE01", "en_contra", 1, "O07"),
]

COUNT_SQL = """
INSERT OR IGNORE INTO count
    (id, vote_event_id, option, value, group_id)
VALUES (?, ?, ?, ?, ?)
"""


# ============================================================
# 8. relacion_poder — Redes de poder informales (18 registros)
# ============================================================

RELACIONES = [
    # --- Familiar ---
    (
        "RP01",
        "actor_externo",
        "AE01",
        "person",
        "P09",
        "familiar",
        5,
        None,
        None,
        None,
        "Primo hermano. Madre de Braña es Lucía Mojica Obrador, prima de AMLO.",
    ),
    # --- Presión ---
    (
        "RP02",
        "actor_externo",
        "AE02",
        "person",
        "P09",
        "presion",
        4,
        None,
        None,
        None,
        "Coordinación. Braña coordinó campaña al Senado de Villarreal 2018.",
    ),
    (
        "RP03",
        "actor_externo",
        "AE02",
        "person",
        "P11",
        "presion",
        3,
        None,
        None,
        None,
        "Coordinación. Ex alcalde de Matamoros bajo influencia tamaulipeca.",
    ),
    (
        "RP04",
        "actor_externo",
        "AE02",
        "person",
        "P18",
        "presion",
        3,
        None,
        None,
        None,
        "Coordinación. Vínculo con aparato político tamaulipeco aliado a 4T.",
    ),
    (
        "RP05",
        "actor_externo",
        "AE03",
        "person",
        "P13",
        "presion",
        3,
        None,
        None,
        None,
        "Cabrera fue Secretaria de Bienestar en gobierno de Salgado (Guerrero).",
    ),
    (
        "RP06",
        "actor_externo",
        "AE04",
        "person",
        "P17",
        "presion",
        3,
        None,
        None,
        None,
        "Silva es suplente de coordinadora de comunicación de Brugada.",
    ),
    (
        "RP07",
        "actor_externo",
        "AE06",
        "person",
        "P12",
        "presion",
        3,
        None,
        None,
        None,
        "Acosta fue senadora suplente de Pavlovich.",
    ),
    # --- Familiar (hermanos) ---
    (
        "RP08",
        "actor_externo",
        "AE05",
        "person",
        "P15",
        "familiar",
        4,
        None,
        None,
        None,
        "Hermanos. Cruz es alcalde de Cd. Juárez, Alejandro es diputado.",
    ),
    # --- Influencia ---
    (
        "RP09",
        "actor_externo",
        "AE01",
        "organization",
        "O01",
        "influencia",
        5,
        None,
        None,
        None,
        "AMLO construyó la arquitectura de diputados prestados durante su sexenio.",
    ),
    (
        "RP10",
        "actor_externo",
        "AE01",
        "organization",
        "O10",
        "influencia",
        5,
        None,
        None,
        None,
        "La coalición fue construida como sistema de intercambio de lealtades bajo AMLO.",
    ),
    (
        "RP14",
        "actor_externo",
        "AE07",
        "organization",
        "O01",
        "influencia",
        4,
        None,
        None,
        None,
        "Coordinador GPP Morena. Arquitecto del Plan B. Operador legislativo clave.",
    ),
    (
        "RP17",
        "actor_externo",
        "AE13",
        "organization",
        "O03",
        "influencia",
        4,
        None,
        None,
        None,
        "Presidenta nacional PVEM. Negocia desde posición de fuerza: 14 senadores son margen de victoria.",
    ),
    (
        "RP18",
        "actor_externo",
        "AE12",
        "organization",
        "O02",
        "influencia",
        4,
        None,
        None,
        None,
        "Dirigente nacional PT. Firme acuerdo Plan B tras 6 días de negociación.",
    ),
    # --- Conflicto ---
    (
        "RP11",
        "person",
        "P04",
        "organization",
        "O01",
        "conflicto",
        3,
        None,
        None,
        None,
        "Ausencia deliberada en reforma electoral y judicial. Posicionamiento institucional autónomo.",
    ),
    # --- Clientelismo ---
    (
        "RP12",
        "organization",
        "O03",
        "organization",
        "O01",
        "clientelismo",
        4,
        None,
        None,
        None,
        "PVEM provee curules a Morena a cambio de posiciones en el gobierno. Relación asimétrica.",
    ),
    (
        "RP13",
        "organization",
        "O02",
        "organization",
        "O01",
        "clientelismo",
        3,
        None,
        None,
        None,
        "PT provee curules a Morena. PT mantiene disciplina férrea (50/51 en contra).",
    ),
    # --- Alianza ---
    (
        "RP15",
        "actor_externo",
        "AE10",
        "organization",
        "O03",
        "alianza",
        4,
        None,
        None,
        None,
        "Principal negociadora técnica con PT y PVEM para Plan B.",
    ),
    (
        "RP16",
        "actor_externo",
        "AE10",
        "organization",
        "O02",
        "alianza",
        4,
        None,
        None,
        None,
        "Negoció acuerdo Plan B con PT y PVEM (12-15 marzo 2026).",
    ),
]

RELACION_SQL = """
INSERT OR IGNORE INTO relacion_poder
    (id, source_type, source_id, target_type, target_id, tipo, peso,
     start_date, end_date, fuente, nota)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================
# 9. evento_politico — Eventos políticos (3 registros)
# ============================================================

EVENTOS = [
    (
        "EP01",
        "2026-03-11",
        "votacion",
        "Rechazo de la Reforma Político-Electoral en la Cámara de Diputados. "
        "259 a favor, 234 en contra, 1 abstención. No se alcanzó la mayoría "
        "calificada de 334 (2/3). PVEM y PT votaron en contra.",
        "Monreal anuncia Plan B. Sheinbaum pierde primera reforma constitucional importante.",
        None,
        "Y01",
    ),
    (
        "EP02",
        "2026-03-12",
        "acuerdo",
        "Sheinbaum reúne a líderes de Morena, PT y PVEM en Palacio Nacional "
        "(~6 horas). Rosa Icela Rodríguez negocia directamente. Monreal confirma "
        "que requerirá mayoría calificada.",
        "Inicio de negociación del Plan B.",
        None,
        "Y02",
    ),
    (
        "EP03",
        "2026-03-15",
        "acuerdo",
        "Se sella acuerdo formal en Gobernación: Morena, PT y PVEM firman "
        "respaldo al Plan B. Alberto Anaya (PT): 'estamos 100% con la Presidenta'. "
        "Karen Castrejón (PVEM): 'un paso importante para fortalecer nuestra democracia'.",
        "Plan B viable en Senado (87/86 votos, margen de 1).",
        None,
        "Y02",
    ),
]

EVENTO_SQL = """
INSERT OR IGNORE INTO evento_politico
    (id, fecha, tipo, descripcion, consecuencia, fuente_url, motion_id)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


# ============================================================
# Funciones de población por tabla
# ============================================================


def populate_table(conn, sql, data, table_name):
    """Insertar registros con INSERT OR IGNORE y devolver conteo."""
    cur = conn.cursor()
    inserted = 0
    for row in data:
        cur.execute(sql, row)
        if cur.rowcount > 0:
            inserted += 1
    total = cur.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    print(f"[migrate] {table_name}: insertados {inserted} (total en BD: {total})")
    return inserted


def populate_persons(conn):
    return populate_table(conn, PERSON_SQL, PERSONS, "person")


def populate_memberships(conn):
    return populate_table(conn, MEMBERSHIP_SQL, MEMBERSHIPS, "membership")


def populate_posts(conn):
    return populate_table(conn, POST_SQL, POSTS, "post")


def populate_motions(conn):
    return populate_table(conn, MOTION_SQL, MOTIONS, "motion")


def populate_vote_events(conn):
    return populate_table(conn, VOTE_EVENT_SQL, VOTE_EVENTS, "vote_event")


def populate_votes(conn):
    return populate_table(conn, VOTE_SQL, VOTES, "vote")


def populate_counts(conn):
    return populate_table(conn, COUNT_SQL, COUNTS, "count")


def populate_relaciones_poder(conn):
    return populate_table(conn, RELACION_SQL, RELACIONES, "relacion_poder")


def populate_eventos_politicos(conn):
    return populate_table(conn, EVENTO_SQL, EVENTOS, "evento_politico")


# ============================================================
# Verificación
# ============================================================


def verify(conn):
    """Ejecutar queries de integridad referencial básica."""
    cur = conn.cursor()
    print("\n--- Verificación de integridad ---")

    checks = [
        ("person", "SELECT COUNT(*) FROM person"),
        ("membership", "SELECT COUNT(*) FROM membership"),
        ("post", "SELECT COUNT(*) FROM post"),
        ("motion", "SELECT COUNT(*) FROM motion"),
        ("vote_event", "SELECT COUNT(*) FROM vote_event"),
        ("vote", "SELECT COUNT(*) FROM vote"),
        ("count", "SELECT COUNT(*) FROM count"),
        ("relacion_poder", "SELECT COUNT(*) FROM relacion_poder"),
        ("evento_politico", "SELECT COUNT(*) FROM evento_politico"),
    ]

    for label, sql in checks:
        total = cur.execute(sql).fetchone()[0]
        print(f"  {label}: {total}")

    # Distribución de votos VE01
    print()
    print("  Distribución votos VE01:")
    cur.execute(
        "SELECT v.option, COUNT(*) FROM vote v WHERE v.vote_event_id='VE01' GROUP BY v.option"
    )
    for row in cur.fetchall():
        print(f"    {row[0]}: {row[1]}")

    # Personas con vulnerabilidad registrada
    print()
    print("  Personas con vulnerabilidad registrada:")
    cur.execute(
        "SELECT p.nombre, p.curul_tipo, p.vulnerabilidad "
        "FROM person p WHERE p.vulnerabilidad IS NOT NULL"
    )
    for row in cur.fetchall():
        print(f"    {row[0]} ({row[1]}): {row[2]}")

    # Orphan check: votos sin persona
    print()
    orphans = cur.execute(
        "SELECT v.id FROM vote v LEFT JOIN person p ON v.voter_id = p.id WHERE p.id IS NULL"
    ).fetchall()
    if orphans:
        print(f"  [ERROR] Votos huérfanos: {[r[0] for r in orphans]}")
    else:
        print("  Orphan check (votes→person): OK (0 huérfanos)")

    # FK check: membership → person
    orphans_m = cur.execute(
        "SELECT m.id FROM membership m LEFT JOIN person p ON m.person_id = p.id WHERE p.id IS NULL"
    ).fetchall()
    if orphans_m:
        print(f"  [ERROR] Memberships huérfanos: {[r[0] for r in orphans_m]}")
    else:
        print("  Orphan check (membership→person): OK (0 huérfanos)")

    # FK check: count → organization
    orphans_c = cur.execute(
        "SELECT c.id FROM count c "
        "LEFT JOIN organization o ON c.group_id = o.id "
        "WHERE c.group_id IS NOT NULL AND o.id IS NULL"
    ).fetchall()
    if orphans_c:
        print(f"  [ERROR] Counts con org inexistente: {[r[0] for r in orphans_c]}")
    else:
        print("  Orphan check (count→organization): OK (0 huérfanos)")


# ============================================================
# Main
# ============================================================


def main():
    print("=" * 60)
    print("Observatorio del Congreso — Migración Caso Cero")
    print("  Reforma Político-Electoral de Sheinbaum (11/mar/2026)")
    print("=" * 60)

    if not os.path.exists(DB_PATH):
        print(f"\n[ERROR] Base de datos no encontrada: {DB_PATH}")
        print("  Ejecuta primero: python db/init_db.py")
        return 1

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")

    # FK check
    fk_status = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    print(f"\n[migrate] Foreign keys: {'ON' if fk_status else 'OFF'}")

    # Poblar tablas en orden de dependencias
    print("\n--- Poblando datos ---")

    populate_persons(conn)
    populate_memberships(conn)  # depende de person, organization
    populate_posts(conn)  # depende de organization, area
    populate_motions(conn)
    populate_vote_events(conn)  # depende de motion, organization
    populate_votes(conn)  # depende de vote_event, person
    populate_counts(conn)  # depende de vote_event, organization
    populate_relaciones_poder(conn)  # depende de person, organization, actor_externo
    populate_eventos_politicos(conn)  # depende de motion

    conn.commit()

    # Verificación
    verify(conn)

    conn.close()

    print("\n" + "=" * 60)
    print("Migración completada exitosamente")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
