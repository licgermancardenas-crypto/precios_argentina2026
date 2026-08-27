# Atlas Precios 📊

> Sistema automatizado que mide la inflación de una canasta de supermercado en Argentina **en tiempo real**, con datos propios relevados diariamente en 4 cadenas — índice propio, comparador de precios, datos abiertos y un agente que responde en lenguaje natural.

### [Ver dashboard en vivo →](https://preciosargentina2026-hzmu5aufmjjbsieqf7ek7d.streamlit.app)

[![scrape-diario](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/scrape.yml/badge.svg)](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/scrape.yml)
[![tests](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/tests.yml/badge.svg)](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/tests.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://preciosargentina2026-hzmu5aufmjjbsieqf7ek7d.streamlit.app)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![SQLite](https://img.shields.io/badge/DB-SQLite-lightgrey)
![CC BY 4.0](https://img.shields.io/badge/datos-CC%20BY%204.0-green)

---

## ¿Qué es esto?

Todos los días a las 06:00 (hora Argentina), un robot releva los precios de una **canasta fija de 45 productos básicos** en **Coto, Día, Carrefour y Jumbo**, y los guarda en una base histórica. Con esos datos:

- construyo el **Índice Canasta Atlas** — un mini-IPC privado con resolución diaria que no existe públicamente;
- **adelanto la inflación oficial**: el IPC de INDEC se publica con ~6 semanas de rezago, así que el índice funciona como un *nowcast* del mes en curso;
- **comparo precios entre cadenas** producto por producto (¿dónde conviene comprar?);
- **publico los datos abiertos** (CSV/JSON, CC BY 4.0);
- y respondo preguntas sobre la base **en lenguaje natural** con un agente LLM.

**El pitch en una frase:** *"Datos propios de inflación minorista, relevados a diario, convertidos en un índice, un comparador y una API abierta — todo automatizado y reproducible."*

---

## Qué demuestra este proyecto

| Área | Cómo |
|------|------|
| **Data engineering** | Pipeline reproducible *raw-first*: el crudo nunca se toca, la DB se reconstruye desde los JSON. Idempotente, multi-cadena, matching por EAN. |
| **Automatización / DevOps** | GitHub Actions releva 4 cadenas, normaliza, exporta y commitea la data **sola**, todos los días, con **control de calidad** que alerta si una cadena falla. |
| **Rigor analítico** | Detecté y corregí bugs de datos que inflaban el índice **+157% semanal** (falso) antes de publicar nada. Metodología del índice documentada y defendible, **con tests** que cubren los guards de sanidad, el matching por EAN y el cálculo del índice. |
| **ML aplicado con honestidad** | Forecasting con Prophet detrás de un *guard de datos*: no publica proyecciones sobre series demasiado cortas. |
| **Aplicaciones LLM** | Agente text-to-SQL (Claude Opus 4.8) con tool de **solo lectura** y doble capa de seguridad. |
| **Producto** | Dashboard público (Streamlit) con 5 vistas + datos abiertos consumibles por terceros. |

---

## Un hallazgo real (por qué el rigor importa)

El primer índice que calculé daba **+157% en una semana** — imposible. La causa no era inflación: el scraper capturaba un `precio_promo` corrupto (la API devolvía valores ×80). El precio de lista estaba limpio; el promo era basura. Con el campo correcto, la inflación real de la canasta fue **~+2% semanal** — coherente.

Ese patrón se repitió al sumar Jumbo, cuyo `ListPrice` VTEX venía ×80 respecto del precio efectivo. La lección quedó en el código: **guards de sanidad en dos capas** (scraper y pipeline) que descartan cualquier valor implausible antes de que contamine la serie. Un índice publicable se gana validando los datos, no confiando en ellos.

**Y el segundo hallazgo fue descubrir que el primero estaba mal.** Ese ×80 de Jumbo no era corrupción: el factor era **82,645 clavado** en 37 de los 39 productos de la canasta, y 82,645 = 100 / 1,21. Jumbo publica su `ListPrice` **neto de IVA y en centavos**. Descartarlo como basura tenía un costo silencioso: el scraper caía a `PriceWithoutDiscount`, que en Jumbo replica el precio efectivo, así que **cuando Jumbo hacía una promo, el precio con descuento quedaba registrado como precio de lista** — justo la contaminación que el índice evita al no usar nunca el promo. Hoy `_precio_regular()` decodifica las dos lecturas posibles y se queda con la plausible: descartar un dato ruidoso es más barato que entenderlo, y a veces sale más caro.

---

## Pipeline

```
Coto (Constructor.io API)   Día / Carrefour / Jumbo (VTEX API)
      │                              │
      ▼                              ▼
 [scraper/coto.py]            [scraper/vtex.py]     ← HTTP puro, delays 2-4s, EAN fijado
      │                              │
      └──────────────┬───────────────┘
                     ▼
      data/raw/{cadena}/YYYY-MM-DD.json   ← snapshot crudo, NUNCA se modifica
                     │
                     ▼
        [pipeline/normalize.py]   ← matching por EAN (unifica cadenas),
                     │              guards de sanidad, reduflación, outliers
                     ▼
             data/atlas.db (SQLite)   ← precios con columna `fuente`
                     │
      ┌──────────────┼───────────────┬────────────────────┐
      ▼              ▼               ▼                    ▼
 [export.py]   [forecast.py]   [dashboard/app.py]   [agent/preguntar.py]
 datos abiertos  Prophet+       índice · comparador   text-to-SQL
 (CSV/JSON)      anomalías       proyección           (Claude Opus 4.8)
```

Todo orquestado por **GitHub Actions** (cron diario). El badge arriba muestra si el relevamiento corrió hoy.

---

## Canasta Atlas — 45 productos, 6 categorías

Lácteos y huevos, almacén, panificados, carnes, bebidas y limpieza. El EAN de cada producto se **congela** en el primer relevamiento y es la clave de matching entre cadenas.

| Categoría | Productos (ej.) |
|-----------|-----------------|
| **Lácteos** | Leche La Serenísima, yogur Ser, queso cremoso La Paulina, manteca, huevos |
| **Almacén** | Aceite Natura, arroz Molinos Ala, fideos Matarazzo, harina Morixe, azúcar Ledesma, yerba Taragüi, café La Virginia, puré Arcor, sal Celusal |
| **Panificados** | Pan Bimbo, galletitas Traviata |
| **Carnes** | Carne picada, pollo entero, paleta cocida |
| **Bebidas** | Coca-Cola 2.25 L, agua Villavicencio, cerveza Quilmes |
| **Limpieza** | Detergente Magistral, lavandina Ayudín, papel Higienol, jabón en polvo Ala |

> La lista completa con presentaciones y EAN vive en [`scraper/config.py`](scraper/config.py).

---

## Fotos de producto

El dashboard muestra la foto de cada producto en cada cadena (tab *Comparar con fotos*).

- **No se descargan ni se versionan.** Se guarda la URL de la CDN del retailer en la tabla `imagenes` y el navegador la pide directo. Las fotos son assets de los supermercados: la licencia CC BY 4.0 de Atlas cubre la serie de precios que construimos, no las imágenes de ellos.
- **Se piden miniaturas, no el original.** Coto sirve variantes por carpeta (`/large/` → `/medium/`) y las tres cadenas VTEX insertando `-ANCHO-ALTO` en el id. Una vista pasa de ~270 KB por foto a ~9 KB.
- **Coto es la excepción y va por el servidor.** Su CDN negocia contenido: cuando el navegador manda `Accept: image/webp` responde `Content-Type: image/webp` con bytes JPEG, y Chrome bloquea la respuesta (`ERR_BLOCKED_BY_ORB`) incluso desde el mismo origen. Esas se traen desde Python —que recibe el `image/jpeg` correcto— y se embeben cacheadas por 24 h.

---

## Metodología del índice

- **Base 100** en el día de inicio. La variación refleja el costo relativo de comprar la misma canasta.
- **Índice encadenado** (*matched pairs*): entre dos días consecutivos se comparan solo los productos con precio en **ambos** días, y los ratios se encadenan — `I_t = I_(t-1) · Σp_t / Σp_(t-1)`. Un producto que aparece o desaparece no mueve el índice por composición, y las altas empiezan a aportar el día que tienen par (no quedan excluidas para siempre, como pasaba con la suma sobre serie completa: con 45 productos relevados el índice corría sobre 23).
- **Frescos de balanza fuera del índice**: los productos vendidos por kilo (`peso_variable=1` en `precios.csv`) se relevan y se publican, pero no entran al índice. Su precio publicado es el de una pieza cuyo peso cambia entre relevamientos: la paleta cocida pasó de $14.559 a $24.265 y volvió a $14.999 sin que se moviera el $/kg, y ese único producto movía el índice ±8%.
- **`costo_canasta`**: el nivel en pesos a composición constante, anclado en el último día (el costo real de comprar la canasta hoy) y reconstruido hacia atrás con el índice.
- **Solo `precio_lista`**, nunca el promo (ver *Un hallazgo real*).
- **Total + 6 categorías**: cada categoría tiene su propio índice base 100.
- **Reduflación**: si el EAN mantiene precio (±2%) pero el contenido baja, se registra como evento `reduflacion`.

---

## Comparador de cadenas

Mismo producto (match por **EAN**), precio de cada cadena, lado a lado. Hallazgo consistente: **no hay una cadena que gane en todo** — el "más barato" se reparte por producto, así que conviene combinar. Los frescos de balanza (queso x kg, pollo) no cross-matchean por EAN y quedan fuera de la comparación, a propósito, para no comparar peras con peras-distintas.

También hay una vista de **precio por unidad ($/kg, $/litro, $/unidad)** — normaliza por contenido (`pipeline/unidades.py` parsea la presentación) para responder "¿dónde está el kg de café / litro de aceite más barato?", más allá del tamaño del envase.

### Hallazgos publicables

El pipeline destila dos tipos de hallazgo sobre datos limpios (`pipeline/hallazgos.py` → `hallazgos.json`):

- **Dispersión de precios**: el *mismo* producto cuesta hasta **~2×** según la cadena. Ejemplos reales del último relevamiento: un vino tinto a mitad de precio en una cadena vs otra, azúcar +43%, agua +56% — todos con EAN idéntico. Dispersión media ~15%.
- **La inflación no es la misma en cada cadena**: un índice encadenado por cadena sobre los **25 productos presentes en las 4** (base 100 al primer día compartido) da **1,58 puntos de spread** en 33 días — Carrefour +1,83% contra Jumbo +0,25% comprando exactamente lo mismo. El control por canasta común no es un detalle: medida sobre su **propia** canasta Carrefour figura **bajando 1,27%**, porque matchea 34 productos contra los 27 de Día y cada índice corre sobre una canasta distinta. El signo se da vuelta. El dashboard publica **las dos columnas juntas**, porque sola, la controlada esconde por qué hace falta controlar. *Alcance de la afirmación:* 33 días alcanzan para mostrar que el spread existe, no para decir que es estructural — eso se sabrá si el orden entre cadenas se sostiene a los 60-90 días. La vista respeta un guard de 30 días comunes, igual que el forecast.
- **Reduflación / cambios de presentación**: eventos que detecta el pipeline (mismo EAN, precio estable, baja el contenido). La detección corre **solo en la cadena de referencia y deduplicada** — antes disparaba falsos positivos porque distintas cadenas reportan el contenido de forma distinta; ese ruido está corregido.

---

## Forecasting (v3) — honesto por diseño

El módulo de proyección usa **Prophet**, pero detrás de un *guard de datos*: con menos de 30 días de historia **no** publica un pronóstico (sería ruido con un intervalo de confianza falso) — muestra "acumulando historia N/30" y se activa solo cuando hay datos. En paralelo ingiere **regresores externos** — dólar oficial/blue (diario, dolarapi.com) e **IPC INDEC** (mensual, API de datos.gob.ar) — y detecta anomalías del índice. El dashboard contrasta nuestro índice con la inflación oficial y lee el forecast precomputado: no depende de Prophet.

---

## Datos abiertos

El pipeline exporta cada día a `data/public/` (licencia **CC BY 4.0**). Las URLs *raw* de GitHub funcionan como API estática:

| Archivo | Contenido |
|---------|-----------|
| `precios.csv` | Serie completa de precios (todas las cadenas) |
| `indice_canasta.csv` / `.json` | Índice base 100 diario: total + 6 categorías |
| `comparador.csv` | Último precio por cadena de cada producto + cuál conviene |
| `regresores.csv` | Series externas: dólar oficial/blue (diario) + IPC INDEC (mensual) |
| `forecast.json` | Proyección + anomalías (o estado "insuficiente") |
| `comparativa_ipc.json` | Índice Canasta vs IPC oficial (nowcast del mes + histórico mensual) |
| `hallazgos.json` | Dispersión de precios entre cadenas + eventos (reduflación) |
| `qc.json` | Control de calidad del relevamiento (productos por cadena + estado) |
| `metadata.json` | Esquema, cadenas, rango de fechas, licencia |

También descargables desde el dashboard.

---

## Preguntá en lenguaje natural (v4)

Agente **text-to-SQL** con Claude Opus 4.8: traduce tu pregunta a SQL, la ejecuta contra la base (solo lectura) y responde citando los números.

```bash
pip install -r requirements-agent.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m agent.preguntar "¿qué cadena es la más barata para la canasta?"
python -m agent.preguntar "¿cuánto subió la categoría lácteos esta semana?"
```

CLI local: corre con **tu** API key, no toca el deploy del dashboard ni expone costos públicos. La tool de consulta es de **solo lectura** — guard que rechaza toda escritura *y* apertura de SQLite en modo `ro` (defensa en dos capas).

---

## Roadmap

| Versión | Estado | Alcance |
|---------|--------|---------|
| v1 MVP | ✅ | Pipeline + Índice Canasta + Dashboard |
| v2 | ✅ | Comparador entre 4 cadenas — Coto + Día + Carrefour + Jumbo |
| v2.5 | ✅ | Índices por categoría + datos abiertos (CSV/JSON) |
| v3 ML | ✅ | Forecasting (Prophet) + anomalías + regresores. Se **activa solo** al superar 30 días de historia |
| v4 Agente | ✅ | Agente text-to-SQL (Claude Opus 4.8) en lenguaje natural |

---

## Stack técnico

- **Scraping:** Python 3.11, HTTP puro (`urllib`) contra las APIs de Constructor.io (Coto) y VTEX (Día/Carrefour/Jumbo) — sin navegador headless, más estable que parsear HTML.
- **Storage:** SQLite (crudo en JSON, procesado en DB).
- **Análisis:** pandas.
- **Automatización:** GitHub Actions (cron diario).
- **Dashboard:** Streamlit + Plotly.
- **ML (v3):** Prophet.
- **Agente (v4):** Anthropic SDK — Claude Opus 4.8, tool use.

---

## Tests

Suite de tests (`tests/`) sobre la lógica crítica del pipeline — se corren en CI en cada push, junto al linter **ruff**:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/ruff check .   # linter (pyflakes + orden de imports)
.venv/bin/pytest         # o: python -m unittest discover -s tests
```

> **Usá un entorno virtual, no el Python del sistema.** En Debian/Ubuntu recientes `pip install --user` falla con `externally-managed-environment` (PEP 668), y si el intérprete del sistema ya tiene una versión vieja de Streamlit los tests fallan por el entorno y no por el código: `width="stretch"` no existe antes de la 1.49, así que el smoke test del dashboard explota contra un `requirements.txt` que pide `streamlit>=1.58`. Si `python -m venv` se queja de `ensurepip`, o instalás `python3-venv`, o usás [uv](https://github.com/astral-sh/uv): `uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt`.

Cubren:
- **Guards de sanidad** — el promo corrupto de Coto se descarta, y el `ListPrice` de Jumbo se decodifica en sus dos codificaciones (neto de IVA en centavos, o en pesos) en vez de tirarse.
- **Matching por EAN** — mismo EAN entre cadenas = mismo producto; fallback por nombre para frescos.
- **Índice** — filtra por `fuente` (no mezcla cadenas), encadena sobre productos pareados (un alta no lo mueve por composición) y excluye los frescos de balanza.
- **Miniaturas** — la derivación de URL de cada CDN (Coto por carpeta, VTEX por `-ANCHO-ALTO` en el id) y el ruteo de la que hay que traer por servidor.
- **Agente** — la tool SQL rechaza toda escritura e inyección.
- **Integración end-to-end** — un snapshot crudo de ejemplo corre por el pipeline real (`normalize`) y se verifica matching por EAN, guard de promo, `en_canasta` e índice multi-cadena.

---

## Decisiones técnicas

**¿Por qué guardar el crudo antes de normalizar?**
El dato crudo nunca se toca. Si hay un bug en la normalización, se reprocesa todo desde los JSON sin perder nada. Es la diferencia entre un pipeline reproducible y uno frágil.

**¿Por qué HTTP directo y no un navegador headless?**
Las cadenas exponen APIs JSON públicas (Constructor.io, VTEX). Consumirlas es más rápido, más estable y menos frágil que renderizar y parsear HTML.

**¿Por qué SQLite y no Postgres?**
Para un pipeline de un solo writer diario con 45 productos × 4 cadenas, SQLite en WAL mode sobra y elimina toda la infraestructura de servidor. Se migra cuando haya razón real.

**¿Por qué EAN como clave de matching?**
El EAN es el identificador más estable en retail. Los nombres cambian, las URLs cambian, los SKUs internos cambian. El EAN no — y es el mismo código en todas las cadenas, lo que hace posible el comparador.

---

## Consideración ética y legal

Scraping de **baja frecuencia** (una vez por día, por cadena) sobre **precios públicos** de productos de consumo masivo. No se recopilan datos personales. El objetivo es analítico y de interés público: una serie histórica de inflación minorista con resolución diaria que no existe en fuentes abiertas.

---

## Estructura del proyecto

```
precios_argentina2026/
├── scraper/
│   ├── __main__.py      # orquestador: python -m scraper [cadenas...]
│   ├── base.py          # helpers compartidos (paths, delays, snapshot)
│   ├── coto.py          # scraping de Coto (Constructor.io)
│   ├── vtex.py          # scraping genérico VTEX (Día, Carrefour, Jumbo)
│   └── config.py        # canasta (EAN fijado), registro de cadenas
├── pipeline/
│   ├── normalize.py     # crudo → SQLite (multi-cadena, matching por EAN)
│   ├── regresores.py    # ingesta de series externas (dólar) — v3
│   ├── forecast.py      # Prophet + anomalías, con guard de datos — v3
│   ├── export.py        # SQLite → data/public/ (CSV/JSON abiertos)
│   └── schema.sql       # DDL de la base de datos
├── agent/
│   └── preguntar.py     # CLI text-to-SQL con Claude Opus 4.8 — v4
├── dashboard/
│   └── app.py           # Streamlit (5 vistas)
├── data/
│   ├── raw/{cadena}/    # snapshots crudos diarios por cadena (JSON)
│   └── public/          # datos abiertos exportados (CSV/JSON, CC BY 4.0)
├── tests/               # suite de tests (unittest / pytest)
├── notebooks/           # análisis exploratorio (EDA del índice)
├── .github/workflows/
│   ├── scrape.yml       # cron diario de relevamiento
│   └── tests.yml        # CI: corre los tests en cada push
├── requirements.txt          # dashboard + pipeline
├── requirements-ml.txt       # Prophet (forecasting)
├── requirements-agent.txt    # Anthropic SDK (agente v4)
└── requirements-dev.txt      # pytest (tests)
```

---

*Proyecto de portfolio — Atlas Analytics · Germán Cárdenas*
