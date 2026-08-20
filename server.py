#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["llmfit>=1.1"]
# ///
"""
LLM Fit GUI - servidor local.

Levanta `llmfit serve` como backend, lo proxea (evita CORS) y agrega
telemetria de GPU en vivo, que la API de llmfit no expone
(gpu_available_gb viene null).

Forma portable de ejecutarlo (instala Python y el wheel de llmfit que
corresponda a la plataforma, sin tocar nada del sistema):

    uv run server.py

Si llmfit ya esta instalado y en el PATH, tambien corre con Python pelado:

    python server.py [--port 8080] [--llmfit-port 8787] [--no-browser]

La cabecera PEP 723 de arriba es lo que le permite a `uv` resolver la
dependencia por su cuenta; Python la ignora como comentario.
"""

import argparse
import base64
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE_DIR, "web")

LLMFIT_URL = "http://127.0.0.1:8787"
_llmfit_proc = None

# `preparar-bundle.py --unico` reemplaza la linea de abajo por el HTML de
# web/index.html en base64, produciendo una app de un solo archivo. Si
# web/index.html existe en disco tiene prioridad, asi el mismo archivo sirve
# para desarrollar y para distribuir.
EMBEDDED_UI_B64 = ""  # __UI_EMBEBIDA__


def embedded_ui():
    if not EMBEDDED_UI_B64:
        return None
    return base64.b64decode(EMBEDDED_UI_B64)


# Catalogo de placas. Mismo mecanismo que la UI: gpus.py en disco manda, y
# `--unico` deja su codigo embebido para cuando el archivo no viaja. Se
# embebe el modulo entero, no solo la tabla, porque su busqueda por nombre
# es la que le pone ancho de banda a la placa que detecta nvidia-smi.
EMBEDDED_GPUS_B64 = ""  # __GPUS_EMBEBIDOS__

_gpus = None


def gpus_mod():
    """Modulo gpus, o None si no esta ni en disco ni embebido."""
    global _gpus
    if _gpus is None:
        _gpus = False
        try:
            sys.path.insert(0, BASE_DIR)
            import gpus as m
            _gpus = m
        except ImportError:
            if EMBEDDED_GPUS_B64:
                import types
                m = types.ModuleType("gpus")
                src = base64.b64decode(EMBEDDED_GPUS_B64).decode("utf-8")
                exec(compile(src, "gpus.py", "exec"), m.__dict__)
                _gpus = m
    return _gpus or None


def gpu_catalog():
    """Lista de (nombre, vram_gb, ancho_gbps). Vacia si no hay catalogo."""
    m = gpus_mod()
    return m.GPUS if m else []


def catalog_lookup(nombre, vram_gb=None):
    """Le pone ancho de banda a una placa detectada. None si no la reconoce."""
    m = gpus_mod()
    try:
        return m.buscar(nombre, vram_gb) if m else None
    except Exception:
        return None


NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


# --------------------------------------------------------------------------
# Backend llmfit
# --------------------------------------------------------------------------
def libc_suffix():
    """Devuelve '-musl' en Alpine y similares, '' en el resto.

    Hace falta porque platform.machine() dice 'x86_64' tanto en glibc como en
    musl: sin esto, en Alpine se elegiria el binario de glibc y no arrancaria.
    """
    if platform.system() != "Linux":
        return ""
    try:
        # glibc informa su version; musl deja el campo vacio.
        if platform.libc_ver()[0]:
            return ""
    except Exception:
        pass
    import glob
    if glob.glob("/lib/ld-musl-*.so.1") or os.path.isfile("/etc/alpine-release"):
        return "-musl"
    return ""


def find_llmfit():
    """Ubica el binario llmfit en cualquier plataforma.

    Orden: PATH -> el entorno del interprete actual (cubre `uv run`, venv y
    pipx, donde el script puede no heredar el PATH del entorno) -> rutas
    tipicas de uv / cargo / scoop / homebrew.
    """
    name = "llmfit.exe" if os.name == "nt" else "llmfit"
    bindir = "Scripts" if os.name == "nt" else "bin"
    home = os.path.expanduser("~")

    # Binario vendorizado junto al proyecto: tiene prioridad sobre el PATH
    # para que un equipo sin internet ni uv funcione copiando la carpeta.
    plat = "%s-%s" % (platform.system().lower(), platform.machine().lower())
    for cand in (os.path.join(BASE_DIR, "bin", plat + libc_suffix(), name),
                 os.path.join(BASE_DIR, "bin", plat, name),
                 os.path.join(BASE_DIR, "bin", name)):
        if os.path.isfile(cand):
            if os.name != "nt":
                os.chmod(cand, 0o755)   # el bit de ejecucion se pierde al zipear
            return cand

    exe = shutil.which("llmfit")
    if exe:
        return exe

    candidates = [
        os.path.join(sys.prefix, bindir, name),
        os.path.join(os.path.dirname(sys.executable), name),
        os.path.join(home, ".local", "bin", name),
        os.path.join(home, ".cargo", "bin", name),
        os.path.join(home, "scoop", "shims", name),
        "/opt/homebrew/bin/llmfit",
        "/usr/local/bin/llmfit",
    ]
    for c in candidates:
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def port_open(host, port, timeout=0.6):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def llmfit_healthy():
    try:
        with urllib.request.urlopen(LLMFIT_URL + "/health", timeout=3) as r:
            return json.loads(r.read()).get("status") == "ok"
    except Exception:
        return False


def ensure_llmfit(port):
    """Arranca `llmfit serve` si no esta corriendo. Devuelve (ok, mensaje)."""
    global _llmfit_proc

    if llmfit_healthy():
        return True, "backend llmfit ya estaba corriendo en %s" % LLMFIT_URL

    if port_open("127.0.0.1", port):
        return False, ("el puerto %d esta ocupado por otro proceso que no "
                       "responde /health" % port)

    exe = find_llmfit()
    if not exe:
        return False, ("no se encontro el binario `llmfit`. Instalalo con:\n"
                       "       uv tool install -U llmfit\n"
                       "    o  scoop install llmfit")

    print("[llmfit] iniciando backend: %s serve --port %d" % (exe, port))
    _llmfit_proc = subprocess.Popen(
        [exe, "serve", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=NO_WINDOW,
    )

    # El primer arranque carga un catalogo de ~10 MB: damos margen.
    deadline = time.time() + 90
    while time.time() < deadline:
        if _llmfit_proc.poll() is not None:
            return False, ("el proceso llmfit termino con codigo %s"
                           % _llmfit_proc.returncode)
        if llmfit_healthy():
            return True, "backend llmfit levantado en %s" % LLMFIT_URL
        time.sleep(1.0)
    return False, "timeout esperando a que llmfit responda /health"


# --------------------------------------------------------------------------
# Telemetria de GPU en vivo
# --------------------------------------------------------------------------
_gpu_cache = {"ts": 0.0, "data": None}
_gpu_lock = threading.Lock()


def _run(cmd, timeout=6):
    try:
        out = subprocess.run(cmd, capture_output=True, text=True,
                             timeout=timeout, creationflags=NO_WINDOW)
        return out.stdout if out.returncode == 0 else None
    except Exception:
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_nvidia():
    """NVIDIA discreta: Windows y Linux, x64 y ARM (incluido Jetson con
    nvidia-smi disponible)."""
    fields = ("name,memory.total,memory.used,memory.free,"
              "utilization.gpu,temperature.gpu")
    out = _run(["nvidia-smi", "--query-gpu=" + fields,
                "--format=csv,noheader,nounits"])
    if not out:
        return None
    gpus = []
    for idx, line in enumerate(out.strip().splitlines()):
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 6:
            continue
        gpus.append({
            "index": idx,
            "name": parts[0],
            "vendor": "NVIDIA",
            "unified": False,
            "total_gb": (_num(parts[1]) or 0) / 1024.0,
            "used_gb": (_num(parts[2]) or 0) / 1024.0,
            "free_gb": (_num(parts[3]) or 0) / 1024.0,
            "util_pct": _num(parts[4]),
            "temp_c": _num(parts[5]),
        })
    return gpus or None


def read_amd():
    """AMD ROCm (mayormente Linux x64/ARM). El JSON de rocm-smi cambia de
    forma entre versiones, asi que buscamos las claves por substring."""
    out = _run(["rocm-smi", "--showmeminfo", "vram", "--showuse",
                "--showtemp", "--json"])
    if not out:
        return None
    try:
        data = json.loads(out)
    except ValueError:
        return None

    def pick(d, *needles):
        for k, v in d.items():
            kl = k.lower()
            if all(n in kl for n in needles):
                return _num(v)
        return None

    gpus = []
    for idx, (card, info) in enumerate(sorted(data.items())):
        if not isinstance(info, dict):
            continue
        total_b = pick(info, "vram", "total", "memory")
        used_b = pick(info, "vram", "used", "memory")
        if total_b is None:
            continue
        total = total_b / 1073741824.0
        used = (used_b or 0) / 1073741824.0
        gpus.append({
            "index": idx,
            "name": (info.get("Card series") or info.get("Card Series")
                     or card),
            "vendor": "AMD",
            "unified": False,
            "total_gb": total,
            "used_gb": used,
            "free_gb": max(0.0, total - used),
            "util_pct": pick(info, "gpu", "use"),
            "temp_c": pick(info, "temperature", "junction") or pick(info, "temperature", "edge"),
        })
    return gpus or None


def read_apple():
    """Apple Silicon: memoria unificada, la GPU comparte el pool con el
    sistema, asi que la 'VRAM libre' es la RAM libre."""
    if platform.system() != "Darwin":
        return None

    total_b = _num((_run(["sysctl", "-n", "hw.memsize"]) or "").strip())
    if not total_b:
        return None
    chip = (_run(["sysctl", "-n", "machdep.cpu.brand_string"]) or "Apple Silicon").strip()

    # vm_stat informa en paginas; sumamos lo que el sistema puede ceder.
    free_b = None
    vm = _run(["vm_stat"])
    if vm:
        page = 4096
        first = vm.splitlines()[0] if vm.splitlines() else ""
        if "page size of" in first:
            page = int(_num(first.split("page size of")[1].split()[0]) or 4096)
        pages = {}
        for line in vm.splitlines()[1:]:
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            n = _num(v.strip().rstrip("."))
            if n is not None:
                pages[k.strip().lower()] = n
        free_pages = sum(pages.get(k, 0) for k in
                         ("pages free", "pages inactive", "pages speculative"))
        if free_pages:
            free_b = free_pages * page

    total = total_b / 1073741824.0
    free = (free_b / 1073741824.0) if free_b else None
    return [{
        "index": 0,
        "name": chip,
        "vendor": "Apple",
        "unified": True,
        "total_gb": total,
        "used_gb": (total - free) if free is not None else None,
        "free_gb": free if free is not None else total,
        "util_pct": None,
        "temp_c": None,
    }]


# Se prueban en orden; el primero que responda gana.
DETECTORS = (("nvidia-smi", read_nvidia),
             ("rocm-smi", read_amd),
             ("apple-unified", read_apple))


def read_gpu(max_age=2.0):
    """Lectura cacheada para que el polling del frontend no sature las
    herramientas del vendor."""
    with _gpu_lock:
        cached = _gpu_cache["data"]
        if cached is not None and time.time() - _gpu_cache["ts"] < max_age:
            return cached

    gpus, source = None, None
    for name, fn in DETECTORS:
        try:
            gpus = fn()
        except Exception:
            gpus = None
        if gpus:
            source = name
            break

    # nvidia-smi y rocm-smi no informan ancho de banda, y es el numero que
    # decide la velocidad. Lo saca el catalogo a partir del nombre: es un
    # valor nominal, no una medicion, y va marcado como tal para que nadie
    # -- interfaz ni consumidor de la API -- lo confunda con telemetria.
    for g in gpus or []:
        fila = catalog_lookup(g.get("name"), g.get("total_gb"))
        g["catalog_name"] = fila[0] if fila else None
        g["bandwidth_gbps"] = fila[2] if fila else None
        g["bandwidth_source"] = "catalogo:gpus.py" if fila else None

    data = {"gpus": gpus or [], "available": bool(gpus), "source": source}

    with _gpu_lock:
        _gpu_cache["ts"] = time.time()
        _gpu_cache["data"] = data
    return data


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
MISSING_UI_HTML = """<!doctype html><meta charset="utf-8">
<title>Falta la interfaz</title>
<body style="font:15px/1.7 system-ui;background:#0b0f17;color:#e6edf7;padding:40px">
<h2 style="color:#f0b429">Falta <code>web/index.html</code></h2>
<p>El servidor arranco bien, pero no encuentra la interfaz. Se esperaba en:</p>
<pre style="background:#121826;padding:12px;border-radius:6px">%s</pre>
<p>Copia la <b>carpeta completa</b> del proyecto, no solo <code>server.py</code>:</p>
<pre style="background:#121826;padding:12px;border-radius:6px">server.py
web/index.html</pre>
</body>"""

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # el ruido del polling tapa los mensajes utiles

    # -- helpers ----------------------------------------------------------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass

    def _proxy(self, path, method="GET", payload=None):
        """Reenvia a llmfit serve. `path` ya incluye query string."""
        req = urllib.request.Request(LLMFIT_URL + path, method=method)
        if payload is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, data=payload, timeout=180) as r:
                ctype = r.headers.get("Content-Type",
                                      "application/json; charset=utf-8")
                self._send(r.status, r.read(), ctype)
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            self._send(e.code, {"error": "llmfit respondio %d" % e.code,
                                "detail": detail})
        except Exception as e:
            self._send(502, {"error": "no se pudo contactar al backend llmfit",
                             "detail": str(e)})

    def _serve_static(self, path):
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        full = os.path.normpath(os.path.join(WEB_DIR, rel))
        if not full.startswith(WEB_DIR) or not os.path.isfile(full):
            if rel == "index.html":
                ui = embedded_ui()
                if ui is not None:
                    self._send(200, ui, "text/html; charset=utf-8")
                    return
                # Error tipico al copiar server.py suelto sin la carpeta web/.
                self._send(500, MISSING_UI_HTML % WEB_DIR, "text/html; charset=utf-8")
                return
            self._send(404, {"error": "no encontrado"})
            return
        ext = os.path.splitext(full)[1].lower()
        with open(full, "rb") as f:
            self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))

    # -- rutas ------------------------------------------------------------
    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path, query = parsed.path, parsed.query

        if path == "/api/gpu":
            self._send(200, read_gpu())
        elif path == "/api/gpu-catalog":
            self._send(200, {"gpus": gpu_catalog()})
        elif path == "/api/status":
            self._send(200, {"llmfit": llmfit_healthy(), "llmfit_url": LLMFIT_URL})
        elif path.startswith("/llmfit/"):
            self._proxy(path[len("/llmfit"):] + (("?" + query) if query else ""))
        else:
            self._serve_static(path)

    def do_POST(self):
        parsed = urllib.parse.urlsplit(self.path)
        if not parsed.path.startswith("/llmfit/"):
            self._send(404, {"error": "no encontrado"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        payload = self.rfile.read(length) if length else b"{}"
        target = parsed.path[len("/llmfit"):]
        if parsed.query:
            target += "?" + parsed.query
        self._proxy(target, method="POST", payload=payload)


# --------------------------------------------------------------------------
# Apertura de la interfaz
# --------------------------------------------------------------------------
CHROMIUM_CANDIDATES = {
    "nt": [
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "posix": ["google-chrome", "google-chrome-stable", "chromium",
              "chromium-browser", "microsoft-edge", "brave-browser"],
}


def _from_app_paths(exe_name):
    """Windows registra la ruta real de los navegadores en 'App Paths'. Es mas
    fiable que adivinar rutas: cubre instalaciones por usuario y no estandar."""
    try:
        import winreg
    except ImportError:
        return None
    key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\%s" % exe_name
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key) as k:
                path = winreg.QueryValue(k, None)
                if path and os.path.isfile(path):
                    return path
        except OSError:
            continue
    return None


def find_chromium():
    if os.name == "nt":
        for exe in ("chrome.exe", "msedge.exe"):
            p = _from_app_paths(exe)
            if p:
                return p
        for c in CHROMIUM_CANDIDATES["nt"]:
            p = os.path.expandvars(c)
            if "%" not in p and os.path.isfile(p):
                return p
        return None
    if platform.system() == "Darwin":
        for p in CHROMIUM_CANDIDATES["darwin"]:
            if os.path.isfile(p):
                return p
    for name in CHROMIUM_CANDIDATES["posix"]:
        p = shutil.which(name)
        if p:
            return p
    return None


def open_ui(url, app_window=False):
    """Abre la interfaz. En modo aplicacion queda sin barra de direcciones,
    como una app de escritorio; si no hay Chromium, cae al navegador normal."""
    if app_window:
        exe = find_chromium()
        if exe:
            try:
                subprocess.Popen([exe, "--app=" + url, "--window-size=1500,950"],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return
            except Exception:
                pass
    webbrowser.open(url)


def main():
    global LLMFIT_URL

    ap = argparse.ArgumentParser(description="GUI local para llmfit")
    ap.add_argument("--port", type=int, default=8080, help="puerto de la GUI")
    ap.add_argument("--llmfit-port", type=int, default=8787,
                    help="puerto del backend llmfit serve")
    ap.add_argument("--no-browser", action="store_true",
                    help="no abrir el navegador automaticamente")
    ap.add_argument("--app-window", action="store_true",
                    help="abrir en ventana tipo aplicacion (sin barra de "
                         "direcciones) si hay Chrome, Edge o Chromium")
    args = ap.parse_args()

    LLMFIT_URL = "http://127.0.0.1:%d" % args.llmfit_port

    print("=" * 62)
    print(" LLM Fit GUI")
    print("=" * 62)

    ok, msg = ensure_llmfit(args.llmfit_port)
    print(("[ok] " if ok else "[!!] ") + msg)
    if not ok:
        print("\nLa GUI abre igual, pero el listado de modelos va a fallar")
        print("hasta que el backend responda.\n")

    gpu = read_gpu()
    if gpu["available"]:
        for g in gpu["gpus"]:
            print("[gpu] %s - %.2f GB libres de %.2f GB (%s%s%s)"
                  % (g["name"], g["free_gb"] or 0, g["total_gb"], gpu["source"],
                     ", memoria unificada" if g.get("unified") else "",
                     ", %d GB/s" % g["bandwidth_gbps"]
                     if g.get("bandwidth_gbps") else ""))
    else:
        print("[gpu] sin telemetria (no hay nvidia-smi / rocm-smi):")
        print("      se usa la VRAM total que reporta llmfit")

    url = "http://127.0.0.1:%d/" % args.port
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as e:
        print("\n[!!] no se pudo abrir el puerto %d: %s" % (args.port, e))
        sys.exit(1)

    srv.daemon_threads = True
    print("\n  GUI lista en  ->  %s" % url)
    print("  Ctrl+C para salir\n")

    # Se abre desde aca, y no desde el lanzador, porque a esta altura el
    # servidor ya esta escuchando: asi no hay carrera contra el arranque.
    if not args.no_browser:
        threading.Timer(0.5, lambda: open_ui(url, args.app_window)).start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\ncerrando...")
    finally:
        srv.server_close()
        if _llmfit_proc and _llmfit_proc.poll() is None:
            _llmfit_proc.terminate()
            print("backend llmfit detenido")


if __name__ == "__main__":
    main()
