-- DDL de la base de datos Atlas Precios
-- SQLite — se crea automáticamente en data/atlas.db

CREATE TABLE IF NOT EXISTS productos (
    id                  INTEGER PRIMARY KEY,
    ean                 TEXT UNIQUE,                    -- nullable para frescos sin EAN
    nombre_normalizado  TEXT NOT NULL,
    nombre_original     TEXT,                           -- último nombre visto en el sitio
    categoria           TEXT NOT NULL,
    presentacion        TEXT,                           -- "1 L", "500 g", "por kg"
    contenido_valor     REAL,                           -- 1.0, 500, ...
    contenido_unidad    TEXT,                           -- "l", "g", "kg", "unidad"
    en_canasta          INTEGER DEFAULT 0,              -- 1 si integra la Canasta Atlas
    activo              INTEGER DEFAULT 1,
    creado_en           TEXT DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS precios (
    id              INTEGER PRIMARY KEY,
    producto_id     INTEGER NOT NULL REFERENCES productos(id),
    fecha           TEXT NOT NULL,                      -- YYYY-MM-DD
    precio_lista    REAL NOT NULL,
    precio_promo    REAL,                               -- nullable
    precio_unitario REAL,                               -- $/kg o $/l normalizado
    fuente          TEXT DEFAULT 'coto',
    UNIQUE (producto_id, fecha, fuente)
);

CREATE TABLE IF NOT EXISTS eventos (                    -- auditoría y hallazgos publicables
    id          INTEGER PRIMARY KEY,
    producto_id INTEGER REFERENCES productos(id),
    fecha       TEXT NOT NULL,
    tipo        TEXT NOT NULL,                          -- 'alta', 'baja', 'cambio_presentacion',
                                                        -- 'reemplazo_canasta', 'outlier', 'reduflacion'
    detalle     TEXT
);

-- Índices para queries frecuentes del dashboard
CREATE INDEX IF NOT EXISTS idx_precios_fecha    ON precios(fecha);
CREATE INDEX IF NOT EXISTS idx_precios_producto ON precios(producto_id, fecha);
CREATE INDEX IF NOT EXISTS idx_eventos_fecha    ON eventos(fecha);
