# Atlas Precios 📊

> Monitor de precios de supermercados argentinos con pipeline de datos automatizado, índice propio de inflación y (próximamente) modelo predictivo.

### [Ver dashboard en vivo →](https://preciosargentina2026-hzmu5aufmjjbsieqf7ek7d.streamlit.app)

[![scrape-diario](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/scrape.yml/badge.svg)](https://github.com/licgermancardenas-crypto/precios_argentina2026/actions/workflows/scrape.yml)
[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://preciosargentina2026-hzmu5aufmjjbsieqf7ek7d.streamlit.app)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![SQLite](https://img.shields.io/badge/DB-SQLite-lightgrey)

---

## ¿Qué es esto?

Todos los días a las 06:00 (hora Argentina), un robot entra a Coto Digital, anota los precios de **26 productos básicos** y los guarda en una base de datos histórica.

Con esos datos construyo el **Índice Canasta Atlas**: el costo de comprar esa canasta fija, expresado en base 100 al día de inicio. Funciona como un mini-IPC privado con resolución diaria, algo que no existe públicamente.

**El pitch en una frase:** *"Un sistema automatizado que mide la inflación de una canasta de supermercado en tiempo real, con datos propios relevados diariamente."*

---

## Pipeline

```
Coto Digital (web)
      │
      ▼
  [scraper/coto.py]  ← Playwright, delays 2-4s, reintentos con backoff
      │
      ▼
 data/raw/YYYY-MM-DD.json   ← snapshot crudo, NUNCA se modifica
      │
      ▼
 [pipeline/normalize.py]   ← matching por EAN, normalización, detección de reduflación
      │
      ▼
   data/atlas.db (SQLite)
      │
      ▼
 [dashboard/app.py]  ← Streamlit (en construcción)
```

Automatizado con **GitHub Actions** (cron diario). El badge arriba muestra si el scraper corrió exitosamente hoy.

---

## Canasta Atlas — 26 productos, 6 categorías

| # | Producto | Presentación | Categoría |
|---|----------|--------------|-----------|
| 1 | Leche entera La Serenísima | 1 L | Lácteos |
| 2 | Yogur bebible Ser o SanCor frutilla | 900 g / 1 L | Lácteos |
| 3 | Queso cremoso La Paulina | por kg | Lácteos |
| 4 | Manteca La Serenísima | 200 g | Lácteos |
| 5 | Huevos blancos | maple x 12 | Lácteos |
| 6 | Aceite de girasol Natura o Cocinero | 1.5 L | Almacén |
| 7 | Arroz largo fino Gallo o Molinos Ala | 1 kg | Almacén |
| 8 | Fideos secos Matarazzo o Lucchetti | 500 g | Almacén |
| 9 | Harina de trigo 000 Morixe | 1 kg | Almacén |
| 10 | Azúcar Ledesma | 1 kg | Almacén |
| 11 | Yerba mate Playadito o Taragüí | 1 kg | Almacén |
| 12 | Café molido La Virginia o Cabrales | 250 g | Almacén |
| 13 | Puré de tomate Arcor o Cica | 520 g | Almacén |
| 14 | Sal fina Celusal | 500 g | Almacén |
| 15 | Pan lactal Bimbo o Fargo | ~460 g | Panificados |
| 16 | Galletitas Criollitas o Traviata | pack 3 u. | Panificados |
| 17 | Carne picada común | por kg | Carnes |
| 18 | Pollo entero | por kg | Carnes |
| 19 | Paleta cocida (fiambre) | por kg | Carnes |
| 20 | Coca-Cola | 2.25 L | Bebidas |
| 21 | Agua sin gas Villavicencio | 2 L | Bebidas |
| 22 | Cerveza Quilmes | 1 L retornable | Bebidas |
| 23 | Detergente Magistral | 500 ml | Limpieza |
| 24 | Lavandina Ayudín | 1 L | Limpieza |
| 25 | Papel higiénico Higienol o Elite | pack 4 u. | Limpieza |
| 26 | Jabón en polvo Skip o Ala | 800 g / 900 ml | Limpieza |

---

## Metodología del índice

- **Base 100** en el día de inicio. La variación refleja el costo relativo de comprar la misma canasta.
- **Forward fill** máximo 7 días si un producto no aparece ese día (precio último conocido).
- **Encadenamiento**: si un producto se reemplaza (desapareció >7 días), el índice se encadena para no generar una discontinuidad artificial.
- **Reduflación**: si el EAN mantiene precio (±2%) pero el contenido baja, se registra como evento `reduflacion` — hallazgo publicable.

---

## Roadmap

| Versión | Estado | Alcance |
|---------|--------|---------|
| v1 MVP | 🔨 En construcción | Pipeline Coto + Índice Canasta + Dashboard básico |
| v2 | ⏳ Pendiente | Comparador entre cadenas (Día, Carrefour) |
| v2.5 | ⏳ Pendiente | Índices por categoría + API/CSV público |
| v3 ML | ⏳ Pendiente | Forecasting (Prophet) + detección de anomalías + regresores externos (IPC, dólar, eventos de calendario) |
| v4 Agente | ⏳ Pendiente | LLM que responde preguntas sobre la base en lenguaje natural |

---

## Stack técnico

- **Scraping:** Python 3.11 + Playwright
- **Storage:** SQLite (crudo en JSON, procesado en DB)
- **Automatización:** GitHub Actions (cron diario)
- **Dashboard:** Streamlit
- **ML (v3):** Prophet + scikit-learn

---

## Decisiones técnicas

**¿Por qué guardar el crudo antes de normalizar?**
El dato crudo nunca se toca. Si hay un bug en la normalización, se reprocesa todo desde los JSON sin perder nada. Es la diferencia entre un pipeline reproducible y uno frágil.

**¿Por qué SQLite y no Postgres?**
Para un pipeline de un solo writer diario con ~30 productos × N cadenas, SQLite en WAL mode es más que suficiente y elimina toda la infraestructura de servidor. Se migra cuando haya razón real para hacerlo.

**¿Por qué EAN como clave de matching?**
El EAN es el identificador más estable en retail. Los nombres de productos cambian, las URLs cambian, los SKUs internos cambian. El EAN no.

---

## Consideración ética y legal

Este proyecto realiza scraping de **baja frecuencia** (una vez por día, por cadena) sobre **precios públicos** de productos de consumo masivo. No se recopilan datos personales. El objetivo es analítico y de interés público: construir una serie histórica de inflación minorista con resolución diaria que no existe en fuentes abiertas.

---

## Estructura del proyecto

```
precios_argentina2026/
├── scraper/
│   ├── coto.py          # lógica de scraping de Coto Digital
│   └── config.py        # canasta, URLs, constantes
├── pipeline/
│   ├── normalize.py     # crudo → SQLite
│   └── schema.sql       # DDL de la base de datos
├── dashboard/
│   └── app.py           # Streamlit
├── data/
│   └── raw/             # snapshots crudos diarios (JSON)
├── notebooks/           # análisis exploratorio (cuando haya ≥3 semanas de datos)
├── .github/workflows/
│   └── scrape.yml       # cron diario
└── requirements.txt
```

---

*Proyecto de portfolio — Atlas Analytics · Germán Cárdenas*
