# Atlas Precios 📊

> Sistema automatizado que mide la inflación de una canasta de supermercado en Argentina **en tiempo real**, con datos propios relevados diariamente en 4 cadenas — índice propio, comparador de precios, datos abiertos y un agente que responde en lenguaje natural.

### [Ver dashboard en vivo →](https://preciosargentina2026-hzmu5aufmjjbsieqf7ek7d.streamlit.app)

[![scrape-diario](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/scrape.yml/badge.svg)](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/scrape.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://preciosargentina2026-hzmu5aufmjjbsieqf7ek7d.streamlit.app)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![SQLite](https://img.shields.io/badge/DB-SQLite-lightgrey)
![CC BY 4.0](https://img.shields.io/badge/datos-CC%20BY%204.0-green)

---

## ¿Qué es esto?

Todos los días a las 06:00 (hora Argentina), un robot releva los precios de una **canasta fija de 26 productos básicos** en **Coto, Día, Carrefour y Jumbo**, y los guarda en una base histórica. Con esos datos:

- construyo el **Índice Canasta Atlas** — un mini-IPC privado con resolución diaria que no existe públicamente;
- **comparo precios entre cadenas** producto por producto (¿dónde conviene comprar?);
- **publico los datos abiertos** (CSV/JSON, CC BY 4.0);
- y respondo preguntas sobre la base **en lenguaje natural** con un agente LLM.

**El pitch en una frase:** *"Datos propios de inflación minorista, relevados a diario, convertidos en un índice, un comparador y una API abierta — todo automatizado y reproducible."*

---

## Qué demuestra este proyecto

| Área | Cómo |
|------|------|
| **Data engineering** | Pipeline reproducible *raw-first*: el crudo nunca se toca, la DB se reconstruye desde los JSON. Idempotente, multi-cadena, matching por EAN. |
| **Automatización / DevOps** | GitHub Actions releva 4 cadenas, normaliza, exporta y commitea la data **sola**, todos los días. |
| **Rigor analítico** | Detecté y corregí bugs de datos que inflaban el índice **+157% semanal** (falso) antes de publicar nada. Metodología del índice documentada y defendible. |
| **ML aplicado con honestidad** | Forecasting con Prophet detrás de un *guard de datos*: no publica proyecciones sobre series demasiado cortas. |
| **Aplicaciones LLM** | Agente text-to-SQL (Claude Opus 4.8) con tool de **solo lectura** y doble capa de seguridad. |
| **Producto** | Dashboard público (Streamlit) con 5 vistas + datos abiertos consumibles por terceros. |

---

## Un hallazgo real (por qué el rigor importa)

El primer índice que calculé daba **+157% en una semana** — imposible. La causa no era inflación: el scraper capturaba un `precio_promo` corrupto (la API devolvía valores ×80). El precio de lista estaba limpio; el promo era basura. Con el campo correcto, la inflación real de la canasta fue **~+2% semanal** — coherente.

Ese patrón se repitió al sumar Jumbo (su `ListPrice` VTEX venía ×80 inflado). La lección quedó en el código: **guards de sanidad en dos capas** (scraper y pipeline) que descartan cualquier valor implausible antes de que contamine la serie. Un índice publicable se gana validando los datos, no confiando en ellos.

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

## Canasta Atlas — 26 productos, 6 categorías

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

## Metodología del índice

- **Base 100** en el día de inicio. La variación refleja el costo relativo de comprar la misma canasta.
- **Canasta fija**: se calcula sobre los productos con **serie completa** (precio todos los días) de la cadena de referencia. Así ningún producto que aparece o desaparece mueve el índice por composición — solo se mide precio.
- **Solo `precio_lista`**, nunca el promo (ver *Un hallazgo real*).
- **Total + 6 categorías**: cada categoría tiene su propio índice base 100.
- **Reduflación**: si el EAN mantiene precio (±2%) pero el contenido baja, se registra como evento `reduflacion`.

---

## Comparador de cadenas

Mismo producto (match por **EAN**), precio de cada cadena, lado a lado. Hallazgo consistente: **no hay una cadena que gane en todo** — el "más barato" se reparte por producto, así que conviene combinar. Los frescos de balanza (queso x kg, pollo) no cross-matchean por EAN y quedan fuera de la comparación, a propósito, para no comparar peras con peras-distintas.

---

## Forecasting (v3) — honesto por diseño

El módulo de proyección usa **Prophet**, pero detrás de un *guard de datos*: con menos de 30 días de historia **no** publica un pronóstico (sería ruido con un intervalo de confianza falso) — muestra "acumulando historia N/30" y se activa solo cuando hay datos. En paralelo ingiere **regresores externos** (dólar oficial/blue, diario) y detecta anomalías del índice. El dashboard lee el resultado precomputado: no depende de Prophet.

---

## Datos abiertos

El pipeline exporta cada día a `data/public/` (licencia **CC BY 4.0**). Las URLs *raw* de GitHub funcionan como API estática:

| Archivo | Contenido |
|---------|-----------|
| `precios.csv` | Serie completa de precios (todas las cadenas) |
| `indice_canasta.csv` / `.json` | Índice base 100 diario: total + 6 categorías |
| `comparador.csv` | Último precio por cadena de cada producto + cuál conviene |
| `regresores.csv` | Series externas (dólar oficial/blue) |
| `forecast.json` | Proyección + anomalías (o estado "insuficiente") |
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

## Decisiones técnicas

**¿Por qué guardar el crudo antes de normalizar?**
El dato crudo nunca se toca. Si hay un bug en la normalización, se reprocesa todo desde los JSON sin perder nada. Es la diferencia entre un pipeline reproducible y uno frágil.

**¿Por qué HTTP directo y no un navegador headless?**
Las cadenas exponen APIs JSON públicas (Constructor.io, VTEX). Consumirlas es más rápido, más estable y menos frágil que renderizar y parsear HTML.

**¿Por qué SQLite y no Postgres?**
Para un pipeline de un solo writer diario con 26 productos × 4 cadenas, SQLite en WAL mode sobra y elimina toda la infraestructura de servidor. Se migra cuando haya razón real.

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
├── notebooks/           # análisis exploratorio (EDA del índice)
├── .github/workflows/scrape.yml   # cron diario
├── requirements.txt          # dashboard + pipeline
├── requirements-ml.txt       # Prophet (forecasting)
└── requirements-agent.txt    # Anthropic SDK (agente v4)
```

---

*Proyecto de portfolio — Atlas Analytics · Germán Cárdenas*
