#!/usr/bin/env python3
"""
Catalogo de hardware para estimar que modelos entran y a que velocidad.

Dos numeros por placa y nada mas:

    VRAM (GB)              cuanto entra
    ancho de banda (GB/s)  a que velocidad corre

El segundo es el que gobierna la inferencia: generar un token exige leer de
memoria todos los pesos activos, asi que el techo practico es

    tok/s ~= ancho_de_banda * eficiencia / peso_del_modelo

Por eso el catalogo no guarda TFLOPS ni nucleos CUDA: para un LLM local no
mueven la aguja.

Las cifras son las nominales de la hoja de datos del fabricante, redondeadas
a GB/s enteros. Cuando una misma placa tuvo revisiones que cambian el
resultado (GDDR5 vs GDDR6, PCIe vs SXM, 8 GB vs 16 GB) van como filas
separadas. En modulos multi-GPU (A16, K80) la fila describe **una** GPU del
modulo, que es lo que ve el runtime.

Formato: lista plana de tuplas (nombre, vram_gb, ancho_gbps). Las filas con
vram None son titulos de seccion; con eso alcanza para armar los <optgroup>
de la interfaz sin duplicar la estructura.

Consumidores:
    build_standalone.py   congela la lista dentro del HTML autonomo
    server.py             la sirve en /api/gpu-catalog y le pone ancho de
                          banda a la placa que detecta nvidia-smi
"""

import re

GPUS = [
    # ======================================================================
    # NVIDIA - GeForce
    # ======================================================================
    ("--- GeForce RTX 50 - Blackwell (escritorio) ---", None, None),
    ("RTX 5090 (32 GB)", 32, 1792),
    ("RTX 5090 D (32 GB)", 32, 1792),
    ("RTX 5080 (16 GB)", 16, 960),
    ("RTX 5070 Ti (16 GB)", 16, 896),
    ("RTX 5070 (12 GB)", 12, 672),
    ("RTX 5060 Ti 16 GB", 16, 448),
    ("RTX 5060 Ti 8 GB", 8, 448),
    ("RTX 5060 (8 GB)", 8, 448),
    ("RTX 5050 (8 GB)", 8, 320),

    ("--- GeForce RTX 50 - Blackwell (portatil) ---", None, None),
    ("RTX 5090 Laptop (24 GB)", 24, 896),
    ("RTX 5080 Laptop (16 GB)", 16, 768),
    ("RTX 5070 Ti Laptop (12 GB)", 12, 672),
    ("RTX 5070 Laptop (8 GB)", 8, 448),
    ("RTX 5060 Laptop (8 GB)", 8, 448),
    ("RTX 5050 Laptop (8 GB)", 8, 384),

    ("--- GeForce RTX 40 - Ada (escritorio) ---", None, None),
    ("RTX 4090 (24 GB)", 24, 1008),
    ("RTX 4090 D (24 GB)", 24, 1008),
    ("RTX 4080 Super (16 GB)", 16, 736),
    ("RTX 4080 (16 GB)", 16, 717),
    ("RTX 4070 Ti Super (16 GB)", 16, 672),
    ("RTX 4070 Ti (12 GB)", 12, 504),
    ("RTX 4070 Super (12 GB)", 12, 504),
    ("RTX 4070 (12 GB)", 12, 504),
    ("RTX 4060 Ti 16 GB", 16, 288),
    ("RTX 4060 Ti 8 GB", 8, 288),
    ("RTX 4060 (8 GB)", 8, 272),

    ("--- GeForce RTX 40 - Ada (portatil) ---", None, None),
    ("RTX 4090 Laptop (16 GB)", 16, 576),
    ("RTX 4080 Laptop (12 GB)", 12, 432),
    ("RTX 4070 Laptop (8 GB)", 8, 256),
    ("RTX 4060 Laptop (8 GB)", 8, 256),
    ("RTX 4050 Laptop (6 GB)", 6, 192),

    ("--- GeForce RTX 30 - Ampere (escritorio) ---", None, None),
    ("RTX 3090 Ti (24 GB)", 24, 1008),
    ("RTX 3090 (24 GB)", 24, 936),
    ("RTX 3080 Ti (12 GB)", 12, 912),
    ("RTX 3080 12 GB", 12, 912),
    ("RTX 3080 10 GB", 10, 760),
    ("RTX 3070 Ti (8 GB)", 8, 608),
    ("RTX 3070 (8 GB)", 8, 448),
    ("RTX 3060 Ti (8 GB)", 8, 448),
    ("RTX 3060 12 GB", 12, 360),
    ("RTX 3060 8 GB", 8, 240),
    ("RTX 3050 8 GB", 8, 224),
    ("RTX 3050 6 GB", 6, 168),

    ("--- GeForce RTX 30 - Ampere (portatil) ---", None, None),
    ("RTX 3080 Ti Laptop (16 GB)", 16, 512),
    ("RTX 3080 Laptop 16 GB", 16, 448),
    ("RTX 3080 Laptop 8 GB", 8, 448),
    ("RTX 3070 Ti Laptop (8 GB)", 8, 512),
    ("RTX 3070 Laptop (8 GB)", 8, 448),
    ("RTX 3060 Laptop (6 GB)", 6, 336),
    ("RTX 3050 Ti Laptop (4 GB)", 4, 192),
    ("RTX 3050 Laptop (4 GB)", 4, 192),

    ("--- GeForce RTX 20 - Turing ---", None, None),
    ("TITAN RTX (24 GB)", 24, 672),
    ("RTX 2080 Ti (11 GB)", 11, 616),
    ("RTX 2080 Super (8 GB)", 8, 496),
    ("RTX 2080 (8 GB)", 8, 448),
    ("RTX 2070 Super (8 GB)", 8, 448),
    ("RTX 2070 (8 GB)", 8, 448),
    ("RTX 2060 Super (8 GB)", 8, 448),
    ("RTX 2060 12 GB", 12, 336),
    ("RTX 2060 6 GB", 6, 336),
    ("RTX 2080 Super Laptop (8 GB)", 8, 496),
    ("RTX 2070 Laptop (8 GB)", 8, 448),
    ("RTX 2060 Laptop (6 GB)", 6, 336),

    ("--- GeForce GTX 16 - Turing ---", None, None),
    ("GTX 1660 Ti (6 GB)", 6, 288),
    ("GTX 1660 Super (6 GB)", 6, 336),
    ("GTX 1660 (6 GB)", 6, 192),
    ("GTX 1650 Super (4 GB)", 4, 192),
    ("GTX 1650 GDDR6 (4 GB)", 4, 192),
    ("GTX 1650 GDDR5 (4 GB)", 4, 128),
    ("GTX 1630 (4 GB)", 4, 96),

    ("--- GeForce GTX 10 - Pascal ---", None, None),
    ("TITAN Xp (12 GB)", 12, 548),
    ("TITAN X Pascal (12 GB)", 12, 480),
    ("GTX 1080 Ti (11 GB)", 11, 484),
    ("GTX 1080 (8 GB)", 8, 320),
    ("GTX 1070 Ti (8 GB)", 8, 256),
    ("GTX 1070 (8 GB)", 8, 256),
    ("GTX 1060 6 GB", 6, 192),
    ("GTX 1060 3 GB", 3, 192),
    ("GTX 1050 Ti (4 GB)", 4, 112),
    ("GTX 1050 (2 GB)", 2, 112),

    ("--- GeForce GTX 900 - Maxwell ---", None, None),
    ("TITAN X Maxwell (12 GB)", 12, 336),
    ("GTX 980 Ti (6 GB)", 6, 336),
    ("GTX 980 (4 GB)", 4, 224),
    ("GTX 970 (4 GB)", 4, 196),
    ("GTX 960 (2 GB)", 2, 112),

    # ======================================================================
    # NVIDIA - estaciones de trabajo (RTX PRO / RTX / Quadro)
    # ======================================================================
    ("--- RTX PRO - Blackwell (estacion de trabajo) ---", None, None),
    ("RTX PRO 6000 Blackwell Workstation (96 GB)", 96, 1792),
    ("RTX PRO 6000 Blackwell Max-Q (96 GB)", 96, 1792),
    ("RTX PRO 5000 Blackwell (72 GB)", 72, 1344),
    ("RTX PRO 5000 Blackwell (48 GB)", 48, 1344),
    ("RTX PRO 4500 Blackwell (32 GB)", 32, 896),
    ("RTX PRO 4000 Blackwell (24 GB)", 24, 672),
    ("RTX PRO 4000 Blackwell SFF (24 GB)", 24, 432),
    ("RTX PRO 2000 Blackwell (16 GB)", 16, 288),

    ("--- RTX PRO - Blackwell (portatil) ---", None, None),
    ("RTX PRO 5000 Blackwell Laptop (24 GB)", 24, 896),
    ("RTX PRO 4000 Blackwell Laptop (24 GB)", 24, 768),
    ("RTX PRO 3000 Blackwell Laptop (12 GB)", 12, 672),
    ("RTX PRO 2000 Blackwell Laptop (12 GB)", 12, 448),
    ("RTX PRO 1000 Blackwell Laptop (8 GB)", 8, 448),
    ("RTX PRO 500 Blackwell Laptop (8 GB)", 8, 384),

    ("--- RTX - Ada (estacion de trabajo) ---", None, None),
    ("RTX 6000 Ada (48 GB)", 48, 960),
    ("RTX 5880 Ada (48 GB)", 48, 960),
    ("RTX 5000 Ada (32 GB)", 32, 576),
    ("RTX 4500 Ada (24 GB)", 24, 432),
    ("RTX 4000 Ada (20 GB)", 20, 360),
    ("RTX 4000 SFF Ada (20 GB)", 20, 280),
    ("RTX 2000 Ada (16 GB)", 16, 224),

    ("--- RTX - Ada (portatil) ---", None, None),
    ("RTX 5000 Ada Laptop (16 GB)", 16, 576),
    ("RTX 4000 Ada Laptop (12 GB)", 12, 432),
    ("RTX 3500 Ada Laptop (12 GB)", 12, 432),
    ("RTX 3000 Ada Laptop (8 GB)", 8, 256),
    ("RTX 2000 Ada Laptop (8 GB)", 8, 256),
    ("RTX 1000 Ada Laptop (6 GB)", 6, 192),
    ("RTX 500 Ada Laptop (4 GB)", 4, 192),

    ("--- RTX A - Ampere (estacion de trabajo) ---", None, None),
    ("RTX A6000 (48 GB)", 48, 768),
    ("RTX A5500 (24 GB)", 24, 768),
    ("RTX A5000 (24 GB)", 24, 768),
    ("RTX A4500 (20 GB)", 20, 640),
    ("RTX A4000 (16 GB)", 16, 448),
    ("RTX A2000 12 GB", 12, 288),
    ("RTX A2000 6 GB", 6, 288),

    ("--- RTX A - Ampere (portatil) ---", None, None),
    ("RTX A5500 Laptop (16 GB)", 16, 512),
    ("RTX A5000 Laptop (16 GB)", 16, 448),
    ("RTX A4000 Laptop (8 GB)", 8, 384),
    ("RTX A3000 Laptop (12 GB)", 12, 384),
    ("RTX A2000 Laptop (8 GB)", 8, 192),

    ("--- Quadro - Turing / Volta / Pascal ---", None, None),
    ("Quadro RTX 8000 (48 GB)", 48, 672),
    ("Quadro RTX 6000 (24 GB)", 24, 672),
    ("Quadro RTX 5000 (16 GB)", 16, 448),
    ("Quadro RTX 4000 (8 GB)", 8, 416),
    ("Quadro GV100 (32 GB)", 32, 870),
    ("Quadro GP100 (16 GB)", 16, 717),
    ("Quadro P6000 (24 GB)", 24, 432),
    ("Quadro P5000 (16 GB)", 16, 288),
    ("Quadro M6000 (24 GB)", 24, 317),

    # ======================================================================
    # NVIDIA - centro de datos
    # ======================================================================
    ("--- Centro de datos - Blackwell ---", None, None),
    ("GB300 Grace Blackwell Ultra (576 GB)", 576, 16000),
    ("B300 / Blackwell Ultra (288 GB)", 288, 8000),
    ("GB200 Grace Blackwell (384 GB)", 384, 16000),
    ("B200 SXM (192 GB)", 192, 8000),
    ("B100 SXM (192 GB)", 192, 8000),
    ("RTX PRO 6000 Blackwell Server (96 GB)", 96, 1792),
    ("DGX Spark - GB10 (128 GB unificados)", 128, 273),

    ("--- Centro de datos - Hopper ---", None, None),
    ("H200 SXM (141 GB)", 141, 4800),
    ("H200 NVL (141 GB)", 141, 4800),
    ("GH200 Grace Hopper (144 GB)", 144, 4900),
    ("GH200 Grace Hopper (96 GB)", 96, 4000),
    ("H100 NVL (94 GB)", 94, 3900),
    ("H100 SXM (80 GB)", 80, 3350),
    ("H100 PCIe (80 GB)", 80, 2000),
    ("H800 SXM (80 GB)", 80, 3350),
    ("H800 PCIe (80 GB)", 80, 2000),
    ("H20 (141 GB)", 141, 4800),
    ("H20 (96 GB)", 96, 4000),

    ("--- Centro de datos - Ada ---", None, None),
    ("L40S (48 GB)", 48, 864),
    ("L40 (48 GB)", 48, 864),
    ("L20 (48 GB)", 48, 864),
    ("L4 (24 GB)", 24, 300),
    ("L2 (24 GB)", 24, 300),

    ("--- Centro de datos - Ampere ---", None, None),
    ("A100 SXM (80 GB)", 80, 2039),
    ("A100 PCIe (80 GB)", 80, 1935),
    ("A100 SXM (40 GB)", 40, 1555),
    ("A100 PCIe (40 GB)", 40, 1555),
    ("A800 SXM (80 GB)", 80, 2039),
    ("A800 PCIe (80 GB)", 80, 1935),
    ("A40 (48 GB)", 48, 696),
    ("A30 (24 GB)", 24, 933),
    ("A10 (24 GB)", 24, 600),
    ("A16 - por GPU (16 GB)", 16, 200),
    ("A2 (16 GB)", 16, 200),

    ("--- Centro de datos - Volta / Turing / Pascal ---", None, None),
    ("V100S PCIe (32 GB)", 32, 1134),
    ("V100 SXM2 (32 GB)", 32, 900),
    ("V100 PCIe (32 GB)", 32, 900),
    ("V100 SXM2 (16 GB)", 16, 900),
    ("V100 PCIe (16 GB)", 16, 900),
    ("T4 (16 GB)", 16, 320),
    ("P100 PCIe (16 GB)", 16, 732),
    ("P100 PCIe (12 GB)", 12, 549),
    ("P40 (24 GB)", 24, 346),
    ("P4 (8 GB)", 8, 192),
    ("M40 (24 GB)", 24, 288),
    ("K80 - por GPU (12 GB)", 12, 240),

    ("--- NVIDIA embebida - Jetson (memoria unificada) ---", None, None),
    ("Jetson AGX Thor (128 GB)", 128, 273),
    ("Jetson AGX Orin (64 GB)", 64, 205),
    ("Jetson AGX Orin (32 GB)", 32, 205),
    ("Jetson Orin NX (16 GB)", 16, 102),
    ("Jetson Orin Nano Super (8 GB)", 8, 102),
    ("Jetson Orin Nano (8 GB)", 8, 68),
    ("Jetson AGX Xavier (32 GB)", 32, 137),
    ("Jetson Xavier NX (8 GB)", 8, 60),

    # ======================================================================
    # AMD
    # ======================================================================
    ("--- AMD Radeon (escritorio) ---", None, None),
    ("RX 9070 XT (16 GB)", 16, 645),
    ("RX 9070 (16 GB)", 16, 645),
    ("RX 9060 XT 16 GB", 16, 322),
    ("RX 7900 XTX (24 GB)", 24, 960),
    ("RX 7900 XT (20 GB)", 20, 800),
    ("RX 7900 GRE (16 GB)", 16, 576),
    ("RX 7800 XT (16 GB)", 16, 624),
    ("RX 7700 XT (12 GB)", 12, 432),
    ("RX 7600 XT (16 GB)", 16, 288),
    ("RX 7600 (8 GB)", 8, 288),
    ("RX 6950 XT (16 GB)", 16, 576),
    ("RX 6900 XT (16 GB)", 16, 512),
    ("RX 6800 XT (16 GB)", 16, 512),
    ("RX 6700 XT (12 GB)", 12, 384),
    ("RX 6600 (8 GB)", 8, 224),

    ("--- AMD Radeon PRO / Instinct ---", None, None),
    ("Radeon PRO W7900 (48 GB)", 48, 864),
    ("Radeon PRO W7800 (32 GB)", 32, 576),
    ("Radeon PRO W6800 (32 GB)", 32, 512),
    ("Radeon PRO VII (16 GB)", 16, 1024),
    ("Instinct MI355X (288 GB)", 288, 8000),
    ("Instinct MI325X (256 GB)", 256, 6000),
    ("Instinct MI300X (192 GB)", 192, 5300),
    ("Instinct MI250X (128 GB)", 128, 3277),
    ("Instinct MI210 (64 GB)", 64, 1638),
    ("Instinct MI100 (32 GB)", 32, 1229),

    # ======================================================================
    # Intel
    # ======================================================================
    ("--- Intel Arc ---", None, None),
    ("Arc B580 (12 GB)", 12, 456),
    ("Arc B570 (10 GB)", 10, 380),
    ("Arc A770 16 GB", 16, 560),
    ("Arc A770 8 GB", 8, 512),
    ("Arc A750 (8 GB)", 8, 512),
    ("Arc A580 (8 GB)", 8, 512),
    ("Arc Pro B60 (24 GB)", 24, 456),
    ("Arc Pro A60 (12 GB)", 12, 192),

    # ======================================================================
    # Apple Silicon (memoria unificada)
    # ======================================================================
    ("--- Apple Silicon (memoria unificada) ---", None, None),
    ("M4 Max (128 GB)", 128, 546),
    ("M4 Max (48 GB)", 48, 546),
    ("M4 Pro (24 GB)", 24, 273),
    ("M4 (16 GB)", 16, 120),
    ("M3 Ultra (512 GB)", 512, 819),
    ("M3 Ultra (96 GB)", 96, 819),
    ("M3 Max (128 GB)", 128, 400),
    ("M3 Max (48 GB)", 48, 400),
    ("M3 Pro (18 GB)", 18, 150),
    ("M3 (16 GB)", 16, 102),
    ("M2 Ultra (192 GB)", 192, 800),
    ("M2 Ultra (96 GB)", 96, 800),
    ("M2 Max (96 GB)", 96, 400),
    ("M2 Max (32 GB)", 32, 400),
    ("M2 Pro (16 GB)", 16, 200),
    ("M2 (16 GB)", 16, 100),
    ("M1 Ultra (128 GB)", 128, 800),
    ("M1 Max (64 GB)", 64, 400),
    ("M1 Max (32 GB)", 32, 400),
    ("M1 Pro (16 GB)", 16, 200),
    ("M1 (16 GB)", 16, 68),

    # ======================================================================
    # Sin GPU
    # ======================================================================
    ("--- Sin GPU (solo CPU) ---", None, None),
    ("CPU - RAM DDR5 doble canal (32 GB)", 32, 80),
    ("CPU - RAM DDR5 doble canal (64 GB)", 64, 80),
    ("CPU - RAM DDR4 doble canal (32 GB)", 32, 50),
    ("CPU - RAM DDR5 cuadruple canal (128 GB)", 128, 160),
    ("CPU - servidor 8 canales DDR5 (256 GB)", 256, 300),
]


def es_titulo(fila):
    return fila[1] is None


def modelos():
    """Solo las placas, sin los titulos de seccion."""
    return [g for g in GPUS if not es_titulo(g)]


# --------------------------------------------------------------------------
# Busqueda por nombre
# --------------------------------------------------------------------------
# nvidia-smi devuelve "NVIDIA GeForce RTX 4070 Ti SUPER", el catalogo dice
# "RTX 4070 Ti Super (16 GB)". Normalizar y comparar por tokens evita tener
# que mantener una tabla de alias que envejece con cada lanzamiento.
_RUIDO = ("nvidia", "geforce", "quadro", "tesla", "amd", "radeon", "intel",
          "apple", "graphics", "generation", "gpu")

_CAPACIDAD = re.compile(r"\d+\s*(gb|gib|mb|mib)\b")


def _tokens(txt):
    """Nombre -> conjunto de palabras comparables.

    Se descarta la capacidad ("16 GB", "80GB") porque no distingue modelos
    sino variantes del mismo modelo, y esas las desempata la VRAM medida.
    """
    txt = (txt or "").lower()
    txt = _CAPACIDAD.sub(" ", txt)
    for palabra in _RUIDO:
        txt = txt.replace(palabra, " ")
    txt = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in txt)
    return set(txt.split())


def _identificadores(toks):
    """Los tokens con digitos son los que nombran al modelo: 4090, h100, m3.
    Sin uno en comun no hay coincidencia posible, por mas palabras sueltas
    que compartan."""
    return {t for t in toks if any(c.isdigit() for c in t)}


def buscar(nombre, vram_gb=None):
    """Busca la placa mas parecida a `nombre`. Devuelve la tupla o None.

    Con `vram_gb` (la que reporto el sistema) desempata entre variantes de
    distinta memoria: una 4060 Ti de 16 GB y una de 8 GB comparten nombre en
    nvidia-smi pero no ancho de banda.
    """
    objetivo = _tokens(nombre)
    ids = _identificadores(objetivo)
    if not ids:
        return None

    mejor, mejor_puntaje = None, 0.0
    for fila in modelos():
        cand = _tokens(fila[0])
        if not (ids & _identificadores(cand)):
            continue
        comunes = objetivo & cand
        # Precision pesa mas que cobertura: lo que el catalogo dice de mas
        # ("Laptop", "SXM", "Ti") es justo lo que separa a un modelo de otro,
        # mientras que lo que sobra en la consulta suele ser ruido del driver.
        precision = len(comunes) / float(len(cand))
        cobertura = len(comunes) / float(len(objetivo))
        puntaje = 0.65 * precision + 0.35 * cobertura
        if vram_gb is not None and fila[1]:
            # +/- 1 GB de margen: nvidia-smi informa 8188 MiB para 8 GB.
            puntaje += 0.25 if abs(fila[1] - vram_gb) <= 1.0 else -0.15
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = fila, puntaje

    # Umbral bajo pero no nulo: preferimos "no se" a inventar un ancho de
    # banda que despues aparece como dato duro en la interfaz.
    return mejor if mejor_puntaje >= 0.45 else None


def ancho_de_banda(nombre, vram_gb=None):
    fila = buscar(nombre, vram_gb)
    return fila[2] if fila else None


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            fila = buscar(arg)
            print("%-40s -> %s" % (arg, fila[0] if fila else "sin coincidencia"))
    else:
        titulos = [g for g in GPUS if es_titulo(g)]
        print("%d placas en %d secciones" % (len(modelos()), len(titulos)))
        for t in titulos:
            print("  " + t[0])
