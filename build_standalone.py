#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["llmfit>=1.1"]
# ///
"""
Genera `llmfit-standalone.html`: un unico archivo HTML autocontenido que
funciona con doble clic, sin servidor, sin Python y sin llmfit instalado.

Como funciona
-------------
Un HTML abierto con file:// no puede ejecutar nada del sistema: no hay
nvidia-smi ni llmfit, y `llmfit serve` no manda cabeceras CORS, asi que
tampoco puede consultarlo. La unica salida es **precomputar**.

Este script consulta a llmfit una vez por cada nivel de contexto y embebe
sus resultados. La memoria requerida por modelo la calcula llmfit, no
nosotros: no se reimplementa su motor, se congela su salida.

Lo que si se calcula en el cliente es la velocidad, con el modelo roofline
    tok/s ~= ancho_de_banda * eficiencia / peso_en_disco
que reproduce a llmfit con ~6% de error mediano. Va etiquetado como
aproximado en la interfaz.

Uso:
    uv run build_standalone.py
    uv run build_standalone.py --out mi.html --contexts 4096,8192,32768
"""

import argparse
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONTEXTS = [2048, 4096, 8192, 16384, 32768, 65536, 131072]

# Catalogo de hardware (VRAM y ancho de banda). Vive en gpus.py para que la
# app con servidor y el HTML autonomo ofrezcan exactamente la misma lista.
sys.path.insert(0, BASE_DIR)
try:
    from gpus import GPUS
except ImportError:
    sys.exit("[!!] falta gpus.py junto a build_standalone.py")


# --------------------------------------------------------------------------
def wait_backend(url, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=3) as r:
                if json.loads(r.read()).get("status") == "ok":
                    return True
        except Exception:
            time.sleep(1.0)
    return False


def find_llmfit():
    exe = shutil.which("llmfit")
    if exe:
        return exe
    name = "llmfit.exe" if os.name == "nt" else "llmfit"
    bindir = "Scripts" if os.name == "nt" else "bin"
    for c in (os.path.join(sys.prefix, bindir, name),
              os.path.join(os.path.expanduser("~"), ".local", "bin", name)):
        if os.path.isfile(c):
            return c
    return None


def fetch(url, ctx, limit=9000):
    q = ("/api/v1/models?limit=%d&include_too_tight=true&sort=score"
         "&max_context=%d" % (limit, ctx))
    with urllib.request.urlopen(url + q, timeout=600) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------------
def build(url, contexts):
    """Devuelve (meta, filas). Una fila por modelo, con la memoria que llmfit
    calculo para cada nivel de contexto."""
    base = None
    mem_by_ctx = {}
    moe_by_ctx = {}

    for ctx in contexts:
        print("  consultando contexto %6d ..." % ctx, end="", flush=True)
        d = fetch(url, ctx)
        models = d["models"]
        print(" %d modelos" % len(models))
        if base is None:
            base = {m["name"]: m for m in models}
        mem_by_ctx[ctx] = {m["name"]: m.get("memory_required_gb")
                           for m in models}
        # En los MoE, memory_required_gb es solo la parte que va a la VRAM
        # (los expertos activos); el resto queda en RAM del sistema. Sin este
        # segundo numero, un DeepSeek-R1 de 671B parece pedir 1,6 GB.
        moe_by_ctx[ctx] = {m["name"]: m.get("moe_offloaded_gb")
                           for m in models}

    rows, skipped = [], 0
    for name, m in base.items():
        mems = [mem_by_ctx[c].get(name) for c in contexts]
        if not any(mems):
            continue

        # llmfit no pudo determinar el tamano de estos y les pone 0.5 GB de
        # relleno: embeberlos daria un "entra holgado" falso. Se descartan.
        if not m.get("disk_size_gb") and not m.get("params_b"):
            skipped += 1
            continue

        rows.append([
            name,
            m.get("provider") or "",
            round(m.get("params_b") or 0, 2),
            m.get("best_quant") or "",
            round(m.get("disk_size_gb") or 0, 3),
            m.get("context_length") or 0,
            m.get("category") or "",
            m.get("use_case") or "",
            m.get("license") or "",
            1 if m.get("is_moe") else 0,
            m.get("capability_ids") or [],
            [round(x, 3) if x else None for x in mems],
            # 'quality' no depende de la VRAM, asi que sigue siendo valido
            # sea cual sea el hardware que elija el usuario.
            round((m.get("score_components") or {}).get("quality") or 0, 1),
            [round(moe_by_ctx[c].get(name) or 0, 3) or None for c in contexts],
        ])

    if skipped:
        print("  descartados %d modelos sin datos de tamano" % skipped)
    rows.sort(key=lambda r: -r[12])  # por calidad, desc
    return rows


def main():
    ap = argparse.ArgumentParser(description="genera el HTML autocontenido")
    ap.add_argument("--out", default=os.path.join(BASE_DIR, "llmfit-standalone.html"))
    ap.add_argument("--contexts", default=",".join(str(c) for c in DEFAULT_CONTEXTS))
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--url", default=None,
                    help="usar un llmfit serve ya corriendo en vez de arrancar uno")
    args = ap.parse_args()

    contexts = [int(c) for c in args.contexts.split(",") if c.strip()]
    proc = None

    if args.url:
        url = args.url.rstrip("/")
        if not wait_backend(url, 10):
            sys.exit("[!!] no responde el backend en %s" % url)
    else:
        exe = find_llmfit()
        if not exe:
            sys.exit("[!!] no se encontro `llmfit`. Proba:  uv run build_standalone.py")
        url = "http://127.0.0.1:%d" % args.port
        print("[..] arrancando llmfit serve en %s" % url)
        proc = subprocess.Popen(
            [exe, "serve", "--port", str(args.port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0)
                           if os.name == "nt" else 0))
        if not wait_backend(url):
            proc.terminate()
            sys.exit("[!!] llmfit no respondio a tiempo")

    try:
        with urllib.request.urlopen(url + "/api/v1/system", timeout=30) as r:
            sysinfo = json.loads(r.read())
        print("[ok] backend listo, generando snapshot")
        rows = build(url, contexts)
    finally:
        if proc and proc.poll() is None:
            proc.terminate()

    ver = subprocess.run([find_llmfit() or "llmfit", "--version"],
                         capture_output=True, text=True).stdout.strip()

    meta = {
        "generated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "llmfit_version": ver or "desconocida",
        "contexts": contexts,
        "count": len(rows),
        "built_on": sysinfo.get("system", {}).get("gpu_name") or "n/d",
    }

    tpl_path = os.path.join(BASE_DIR, "web", "standalone.tpl.html")
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()

    payload = ("const META=%s;\nconst GPUS=%s;\nconst DATA=%s;"
               % (json.dumps(meta, ensure_ascii=False),
                  json.dumps([g for g in GPUS], ensure_ascii=False),
                  json.dumps(rows, ensure_ascii=False, separators=(",", ":"))))

    # marcador en una sola linea para no romper si el template cambia
    out_html = re.sub(r"/\*\s*__DATOS__\s*\*/", lambda _: payload, tpl, count=1)
    if out_html == tpl:
        sys.exit("[!!] no se encontro el marcador /* __DATOS__ */ en el template")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out_html)

    size = os.path.getsize(args.out) / 1048576.0
    print()
    print("[ok] %s" % args.out)
    print("     %d modelos | %d niveles de contexto | %.2f MB"
          % (len(rows), len(contexts), size))
    print("     abrilo con doble clic, no necesita nada instalado")


if __name__ == "__main__":
    main()
