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

## [0.2.4] — 2026-08-20

### Agregado

- **`preparar-bundle.py` deja de re-descargar lo que ya tiene.** Cada binario
  extraído deja al lado un `.llmfit-version` con la versión del wheel del que
  salió; si coincide con la que publica PyPI, se reusa. Rearmar el ZIP completo
  pasa de **215 MB y ~1 minuto a 8 segundos** y una sola consulta de 1 KB a
  PyPI —la que dice qué versión es la actual, para no quedarse con binarios
  viejos—. `--rebajar` fuerza la descarga.

---

## [0.2.3] — 2026-08-20

Los modelos MoE mostraban solo la mitad de su memoria.

### Corregido

- **La memoria de un MoE va partida y ahora se ve entera.** llmfit planifica
  estos modelos en híbrido —expertos activos en VRAM, inactivos en la RAM del
  sistema— y devuelve las dos cifras: `memory_required_gb` y
  `moe_offloaded_gb`. La app mostraba solo la primera, así que
  `unsloth/DeepSeek-R1-GGUF` (671B) figuraba pidiendo **1,64 GB** cuando en
  realidad hay que tener cargados **16,35 GB**. Afectaba a 604 modelos de los
  8159 embebidos.
  - La tabla agrega `+ N GB RAM` bajo la cifra de VRAM.
  - El panel lateral suma la sección «Modelo MoE — la memoria va partida», con
    activos en VRAM, inactivos en RAM y total.
  - El HTML autónomo embebe `moe_offloaded_gb` por nivel de contexto (columna
    nueva en cada fila) y el resumen aclara cuántos de los que entran
    «exigen RAM aparte».
  - El CSV de las dos interfaces suma las columnas `moe_ram_offload_gb` y
    `memoria_total_gb`.
- **`moe_offload` ya no se muestra como «Solo CPU».** Era el `else` del
  clasificador de la app con servidor: 862 modelos MoE caían ahí. Ahora dicen
  **«MoE híbrido»**, que es lo que llmfit informa en `run_mode`.
- En el HTML autónomo, un MoE que entra en la VRAM se marca **«MoE + RAM»** en
  vez de «entra holgado»: entra en la placa, pero solo si además tenés esa RAM
  libre, y este archivo no conoce la RAM del equipo.

### Sin reportar upstream

- Se investigó como posible bug de llmfit y **no lo es**: está reportado y
  cerrado en [AlexsJones/llmfit#230](https://github.com/AlexsJones/llmfit/issues/230).
  El mantenedor explicó que el puntaje evalúa los dos pools por separado a
  propósito y que lo que faltaba era exponer `moe_offloaded_gb`, agregado en
  su #235. El campo estaba: quien no lo mostraba era esta app.

---

## [0.2.2] — 2026-08-20

Correcciones al catálogo en las placas de portátil, y el bug de llmfit
reportado upstream.

### Corregido

- **Anchos de banda equivocados en las RTX 50 y 30 de portátil**, verificados
  contra el VBIOS que publica TechPowerUp y las fichas de los fabricantes:
  - RTX 5070 Laptop: 448 → **384 GB/s** (128 bits a 24 Gbps; el VBIOS reporta
    1500 MHz de memoria, no 1750).
  - RTX 5060 Laptop: 448 → **384 GB/s**.
  - RTX 5080 Laptop: 768 → **896 GB/s** (256 bits a 28 Gbps).
  - RTX 3070 Ti Laptop: 512 → **448 GB/s**.
- Se agrega la **RTX 5070 Laptop de 12 GB** (mayo de 2026, mismos 384 GB/s: el
  bus sigue siendo de 128 bits, los módulos son de 3 GB).

### Agregado

- El encabezado de `gpus.py` documenta las dos trampas de las placas de
  portátil: comparten nombre con una de escritorio pero no el bus de memoria,
  y el mismo modelo cambia de velocidad según el TGP que le puso el fabricante
  del equipo (una RTX 3070 Ti Laptop va de 384 a 448 GB/s). Se lista la
  versión de plena potencia.

### Reportado upstream

- [AlexsJones/llmfit#919](https://github.com/AlexsJones/llmfit/issues/919):
  `gpu_memory_bandwidth_gbps()` compara solo el número de modelo, así que toda
  placa de portátil hereda el ancho de banda de la de escritorio homónima. A
  una RTX 5070 Laptop le asigna 672 GB/s, imposibles en un bus de 128 bits, e
  infla los tok/s hasta 1,8× en la línea móvil de las series 30, 40 y 50.

---

## [0.2.1] — 2026-08-20

Fidelidad de los datos de hardware: cada cifra de GPU dice de dónde sale.

### Cambiado

- **El ancho de banda va etiquetado como catálogo, no como medición.** Ni
  `nvidia-smi` ni `rocm-smi` lo informan: sale de una ficha nominal de
  `gpus.py`. La tira superior ahora muestra `448 GB/s · catálogo` (con el
  nombre de la ficha aplicada en el tooltip) en vez de un número pelado que
  parecía telemetría. Si el nombre que reporta el driver no coincide con
  ninguna ficha, dice `ancho de banda: sin ficha` en lugar de callarse.
- **Se muestra la discrepancia con llmfit en vez de esconderla.** llmfit tiene
  su propia tabla y no siempre distingue variantes: a una RTX 5070 Laptop le
  asigna los 672 GB/s de la de escritorio (192 bits) cuando la de portátil son
  128 bits y 448 GB/s. Cuando las dos cifras difieren más de un 5 %, el panel
  lateral muestra ambas —`672 GB/s según llmfit` y `catálogo · RTX 5070
  Laptop (8 GB) 448 GB/s`— y aclara que los tok/s de arriba los calculó llmfit
  con la suya.
- **Al simular otra placa, el panel lo dice.** La velocidad se sigue calculando
  con el ancho de banda del hardware real, porque llmfit solo acepta un
  presupuesto de VRAM; ahora esa nota aparece junto a los números, no solo en
  la tira.
- `GET /api/gpu` agrega `bandwidth_source` (`"catalogo:gpus.py"` o `null`), para
  que un consumidor de la API tampoco pueda confundir la ficha con telemetría.

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

[0.2.4]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.2.4
[0.2.3]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.2.3
[0.2.2]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.2.2
[0.2.1]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.2.1
[0.2.0]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.2.0
[0.1.0]: https://github.com/matiasagustincastro-byte/llmfit-gui/releases/tag/v0.1.0
