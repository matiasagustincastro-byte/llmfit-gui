# Changelog

Todos los cambios notables de este proyecto quedan acá.

El formato sigue a [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el versionado es [SemVer](https://semver.org/lang/es/). Las versiones son las
de **esta GUI**, no las de [llmfit](https://github.com/AlexsJones/llmfit), que
es el motor de estimación y va por su cuenta.

Al tocar `server.py`, `web/index.html` o `gpus.py` hay que regenerar el archivo
único, o la app distribuida sigue sirviendo la versión vieja:

```bash
python preparar-bundle.py --unico     # regenera llmfit-gui.py
uv run build_standalone.py            # regenera llmfit-standalone.html
```

---

## [0.2.0] — 2026-08-20

Catálogo de placas propio. Antes había 45 GPUs escritas a mano dentro de
`build_standalone.py` y solo las veía la versión sin conexión; ahora son 247 en
un módulo compartido, y la app con servidor también las usa.

### Agregado

- **`gpus.py`: catálogo de 247 placas** con VRAM y ancho de banda, en 28
  secciones. **188 son NVIDIA y cubren todas las líneas**:
  - GeForce RTX 50 / 40 / 30 / 20 y GTX 16 / 10 / 900, escritorio y portátil
    (las variantes Laptop van aparte: una 4090 de notebook tiene 16 GB y 576 GB/s,
    no 24 GB y 1008 GB/s).
  - Estación de trabajo: RTX PRO Blackwell (6000 / 5000 / 4500 / 4000 / 2000),
    RTX Ada (6000 / 5880 / 5000 / 4500 / 4000 / 2000), RTX A Ampere
    (A6000 / A5500 / A5000 / A4500 / A4000 / A2000) y Quadro RTX / GV100 / P6000.
  - Centro de datos: GB300, B300, GB200, B200, B100, H200, GH200, H100 (SXM /
    PCIe / NVL), H800, H20, L40S / L40 / L20 / L4 / L2, A100 (40 y 80 GB, SXM y
    PCIe), A800, A40, A30, A10, A16, A2, V100 / V100S, T4, P100, P40, P4, M40, K80.
  - Jetson (AGX Thor, AGX Orin, Orin NX, Orin Nano, Xavier) y DGX Spark.
  - Se conservan y amplían AMD (Radeon RX 9000/7000/6000, PRO W7000, Instinct
    MI355X…MI100), Intel Arc, Apple Silicon (M1 a M4, hasta M3 Ultra de 512 GB)
    y perfiles de solo-CPU.
- **Selector «Simular otra placa» en la app con servidor.** Responde «¿y si
  tuviera una H200?» sin tenerla: se le pasa a llmfit la VRAM de la placa
  elegida y re-puntúa el catálogo entero contra ese presupuesto. La tira
  superior aclara que los tok/s siguen siendo los del hardware real, porque
  llmfit no acepta un ancho de banda arbitrario.
- **`GET /api/gpu-catalog`**, que sirve el catálogo al frontend.
- **Ancho de banda en la telemetría en vivo.** `nvidia-smi` y `rocm-smi` no lo
  informan; `gpus.py` lo deduce del nombre de la placa. `/api/gpu` ahora agrega
  `catalog_name` y `bandwidth_gbps` por GPU, y aparece en la tira y en el log
  de arranque.
- **Búsqueda de placa por nombre** (`gpus.buscar`), tolerante a cómo la nombra
  cada driver: `"NVIDIA GeForce RTX 4070 Ti SUPER"` → `RTX 4070 Ti Super`,
  `"NVIDIA A100-SXM4-80GB"` → `A100 SXM (80 GB)`. Compara por tokens, exige que
  coincida el identificador del modelo (`4090`, `h100`, `m3`) para no inventar
  parecidos, y usa la VRAM medida para desempatar variantes homónimas
  (4060 Ti de 8 y de 16 GB).
- **Filtro de texto sobre el selector de GPU** en las dos interfaces: con 247
  placas agrupadas en `<optgroup>`, buscar «h100» es más rápido que scrollear.

### Cambiado

- `build_standalone.py` ya no define el catálogo: lo importa de `gpus.py`.
- El selector de GPU del HTML autónomo pasa de una lista plana con separadores
  deshabilitados a `<optgroup>` por familia, y cada opción muestra su ancho de
  banda.
- `preparar-bundle.py --unico` embebe **el módulo `gpus.py` entero**, no solo la
  tabla, para que la app de un solo archivo conserve la búsqueda por nombre.
  `gpus.py` también viaja suelto en los ZIP.
- Los topes de los campos numéricos suben (VRAM a 1024 GB, ancho de banda a
  20 000 GB/s): un GB300 son 576 GB y 16 TB/s, y no entraban en los anteriores.

---

## [0.1.0] — 2026-08-18

Primera versión.

### Agregado

- **App con servidor** (`server.py` + `web/index.html`): levanta `llmfit serve`,
  lo proxea para esquivar CORS y suma lo que su API no da.
  - VRAM libre real en vivo vía `nvidia-smi` / `rocm-smi` / memoria unificada en
    macOS, cacheada 2 s, usable como presupuesto para el ranking.
  - Semáforo por modelo (Perfecto / Bueno / Justo / CPU offload / No entra) con
    barra de ocupación.
  - Plan de hardware por modelo: mínimo vs recomendado, los tres modos de
    ejecución con su tok/s y el ahorro de cuantizar el KV cache.
  - Exportación a CSV de lo que se está viendo, con los filtros aplicados.
- **Versión sin conexión** (`build_standalone.py` + `web/standalone.tpl.html`):
  un HTML de 1,4 MB, ~8100 modelos y 7 niveles de contexto precomputados con
  llmfit. La memoria requerida sale congelada de llmfit; los tok/s se calculan
  en el navegador con `ancho_de_banda × 0,55 ÷ peso_en_disco` y van etiquetados
  como aproximados.
- **Distribución** (`preparar-bundle.py`): ZIP de fuentes, ZIP offline con los
  binarios de llmfit por plataforma, y `--unico` para fundir todo en
  `llmfit-gui.py`.
- Lanzadores `run.sh`, `LLM-Fit.bat` e `instalar-acceso-directo.ps1`.
- Interfaz en español, sin build ni dependencias JS.

[0.2.0]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.2.0
[0.1.0]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.1.0
