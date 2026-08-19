#!/usr/bin/env python3
"""
Arma un ZIP listo para copiar a otros equipos.

Por defecto empaqueta solo los fuentes (~100 KB): el equipo destino resuelve
llmfit con `uv run`, que necesita internet la primera vez.

Con --plataformas, descarga los binarios de llmfit desde PyPI y los mete en
`bin/<sistema>-<arquitectura>/`. Ahi el destino ya no necesita internet ni uv:
alcanza con Python. Sirve para maquinas aisladas o sin permisos de instalacion.

Uso:
    python preparar-bundle.py
    python preparar-bundle.py --plataformas win_amd64,manylinux_x86_64
    python preparar-bundle.py --todas --standalone
    python preparar-bundle.py --listar
"""

import argparse
import base64
import io
import json
import os
import shutil
import sys
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PKG = "llmfit"

# Etiqueta corta -> (fragmento del nombre del wheel, carpeta destino en bin/)
# La carpeta destino debe coincidir con lo que arma find_llmfit() en server.py:
#   platform.system().lower() + "-" + platform.machine().lower()
PLATAFORMAS = {
    "win_amd64":         ("win_amd64",                 "windows-amd64"),
    "win_arm64":         ("win_arm64",                 "windows-arm64"),
    "manylinux_x86_64":  ("manylinux_2_17_x86_64",     "linux-x86_64"),
    "manylinux_aarch64": ("manylinux_2_17_aarch64",    "linux-aarch64"),
    "musllinux_x86_64":  ("musllinux_1_2_x86_64",      "linux-x86_64-musl"),
    "musllinux_aarch64": ("musllinux_1_2_aarch64",     "linux-aarch64-musl"),
    "macos_x86_64":      ("macosx_10_12_x86_64",       "darwin-x86_64"),
    "macos_arm64":       ("macosx_11_0_arm64",         "darwin-arm64"),
}

# Lo que va al ZIP siempre.
FUENTES = [
    "llmfit-gui.py", "server.py", "run.sh", "LLM-Fit.bat",
    "instalar-acceso-directo.ps1", "build_standalone.py",
    "README.md", "LICENSE",
    os.path.join("web", "index.html"),
    os.path.join("web", "standalone.tpl.html"),
]

LEEME = """\
LLM Fit GUI - que modelos LLM entran en la GPU de este equipo
=============================================================

Basado en llmfit, de Alex Jones (MIT):
    https://github.com/AlexsJones/llmfit

Este paquete: https://github.com/matiasagustincastro-byte/llmfit-gui


COMO EJECUTARLO
---------------
Elegi la primera opcion que puedas.

1) CON uv  (lo mas simple, cualquier sistema operativo)

       uv run llmfit-gui.py

   Si no tenes uv:
       Linux/macOS  curl -LsSf https://astral.sh/uv/install.sh | sh
       Windows      powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

2) CON PYTHON, SIN INTERNET  (este paquete trae los binarios)

       python llmfit-gui.py

   Windows: doble clic en LLM-Fit.bat
   Linux/macOS: ./run.sh     (si hace falta: chmod +x run.sh llmfit-gui.py)

3) SIN PYTHON Y SIN NADA

       Doble clic en llmfit-standalone.html

   Funciona en cualquier navegador, sin conexion. No detecta tu GPU:
   la elegis de una lista. El resto de los numeros son los mismos.


QUE TRAE
--------
llmfit-gui.py            la app entera en un archivo
llmfit-standalone.html   version sin conexion, doble clic
bin/<plataforma>/        binarios de llmfit para no depender de internet
server.py + web/         los fuentes, por si queres modificar
run.sh / LLM-Fit.bat     lanzadores


PLATAFORMAS INCLUIDAS EN bin/
-----------------------------
%(plataformas)s

Cada equipo toma solo el binario que le corresponde; el resto se ignora.
Si tu plataforma no esta en la lista, usa la opcion 1 (uv) o instala
llmfit con:  uv tool install -U llmfit


NOTAS
-----
- Todo corre en 127.0.0.1. No se manda nada a ningun lado.
- Los tok/s son estimaciones del modelo de llmfit, no benchmarks.
- Detalles completos en README.md
"""


def pypi_urls():
    url = "https://pypi.org/pypi/%s/json" % PKG
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read())
    return data["info"]["version"], data["urls"]


def bajar_binario(urls, fragmento, destino_dir):
    """Descarga el wheel de esa plataforma y extrae el ejecutable llmfit."""
    match = next((u for u in urls if fragmento in u["filename"]), None)
    if not match:
        return None, "no hay wheel con '%s'" % fragmento

    with urllib.request.urlopen(match["url"], timeout=300) as r:
        blob = r.read()

    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        # El ejecutable vive en <pkg>-<ver>.data/scripts/llmfit[.exe]
        cands = [n for n in z.namelist()
                 if "/scripts/" in n.replace("\\", "/")
                 and os.path.basename(n).lower() in ("llmfit", "llmfit.exe")]
        if not cands:
            return None, "el wheel no trae el ejecutable"
        nombre = os.path.basename(cands[0])
        os.makedirs(destino_dir, exist_ok=True)
        salida = os.path.join(destino_dir, nombre)
        with z.open(cands[0]) as src, open(salida, "wb") as dst:
            shutil.copyfileobj(src, dst)

    if not salida.endswith(".exe"):
        os.chmod(salida, 0o755)
    return salida, None


def generar_unico(salida):
    """Funde server.py + web/index.html en un solo .py ejecutable.

    El HTML va en base64 para no pelearse con comillas ni escapes. server.py
    prefiere web/index.html si existe en disco, asi que el archivo generado
    tambien sirve dentro del proyecto durante el desarrollo.
    """
    src = io_open(os.path.join(BASE_DIR, "server.py"))
    html = open(os.path.join(BASE_DIR, "web", "index.html"), "rb").read()
    b64 = base64.b64encode(html).decode("ascii")

    marcador = 'EMBEDDED_UI_B64 = ""  # __UI_EMBEBIDA__'
    if marcador not in src:
        sys.exit("[!!] no se encontro el marcador __UI_EMBEBIDA__ en server.py")

    nuevo = src.replace(marcador, 'EMBEDDED_UI_B64 = "%s"' % b64, 1)

    # Shebang de uv: en Linux/macOS el archivo queda ejecutable directo
    # (./llmfit-gui.py) y uv resuelve Python y llmfit solo. No afecta a
    # Windows ni a `python llmfit-gui.py`, que ignoran el shebang.
    nuevo = nuevo.replace("#!/usr/bin/env python3",
                          "#!/usr/bin/env -S uv run --script", 1)

    # Verificacion antes de escribir: que siga siendo Python valido.
    import ast
    ast.parse(nuevo)

    with open(salida, "w", encoding="utf-8", newline="\n") as f:
        f.write(nuevo)
    if os.name != "nt":
        os.chmod(salida, 0o755)

    kb = os.path.getsize(salida) / 1024.0
    print("[ok] %s  (%.0f KB)" % (salida, kb))
    print("     un solo archivo: no necesita la carpeta web/")
    print()
    print("     ejecutalo igual en Linux y en Windows:")
    print("         uv run %s" % os.path.basename(salida))
    print("     en Linux/macOS tambien anda directo:")
    print("         chmod +x %s && ./%s"
          % (os.path.basename(salida), os.path.basename(salida)))


def io_open(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def main():
    ap = argparse.ArgumentParser(description="arma un ZIP distribuible")
    ap.add_argument("--plataformas", default="",
                    help="lista separada por comas (ver --listar)")
    ap.add_argument("--todas", action="store_true",
                    help="vendorizar el binario de todas las plataformas")
    ap.add_argument("--standalone", action="store_true",
                    help="incluir tambien llmfit-standalone.html si existe")
    ap.add_argument("--listar", action="store_true",
                    help="mostrar las plataformas disponibles y salir")
    ap.add_argument("--unico", action="store_true",
                    help="generar llmfit-gui.py: la app entera en un archivo")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if args.unico:
        generar_unico(args.out or os.path.join(BASE_DIR, "llmfit-gui.py"))
        return

    if args.listar:
        print("plataformas disponibles:\n")
        for k, (frag, dest) in PLATAFORMAS.items():
            print("  %-19s -> bin/%s" % (k, dest))
        return

    if args.todas:
        elegidas = list(PLATAFORMAS)
    else:
        elegidas = [p.strip() for p in args.plataformas.split(",") if p.strip()]

    desconocidas = [p for p in elegidas if p not in PLATAFORMAS]
    if desconocidas:
        sys.exit("[!!] plataforma desconocida: %s\n     probá --listar"
                 % ", ".join(desconocidas))

    version = "n/d"
    vendorizados = []

    if elegidas:
        print("[..] consultando PyPI")
        version, urls = pypi_urls()
        print("[ok] llmfit %s" % version)
        for p in elegidas:
            frag, dest = PLATAFORMAS[p]
            destino = os.path.join(BASE_DIR, "bin", dest)
            print("  %-19s ..." % p, end="", flush=True)
            ruta, err = bajar_binario(urls, frag, destino)
            if err:
                print(" ERROR: %s" % err)
                continue
            mb = os.path.getsize(ruta) / 1048576.0
            print(" %.1f MB -> bin/%s/%s" % (mb, dest, os.path.basename(ruta)))
            vendorizados.append(os.path.relpath(ruta, BASE_DIR))

    faltantes = [f for f in FUENTES if not os.path.isfile(os.path.join(BASE_DIR, f))]
    if faltantes:
        sys.exit("[!!] faltan archivos del proyecto: %s" % ", ".join(faltantes))

    incluir = list(FUENTES) + vendorizados
    if args.standalone:
        sa = "llmfit-standalone.html"
        if os.path.isfile(os.path.join(BASE_DIR, sa)):
            incluir.append(sa)
        else:
            print("[!] no existe %s todavia; generalo con build_standalone.py" % sa)

    sufijo = "-offline" if vendorizados else ""
    if args.todas:
        sufijo = "-completo"
    out = args.out or os.path.join(BASE_DIR, "LLM-Fit%s.zip" % sufijo)

    lista_plat = "\n".join(
        "  bin/%-22s %s" % (PLATAFORMAS[p][1], p) for p in elegidas
    ) or "  (ninguna: hace falta uv o llmfit instalado)"

    def ejecutable(rel):
        """Lo que en Linux/macOS tiene que salir del unzip con +x."""
        rel = rel.replace("\\", "/")
        return (rel.startswith("bin/") or rel.endswith(".sh")
                or rel == "llmfit-gui.py")

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in incluir:
            arc = os.path.join("LLM-Fit", rel).replace("\\", "/")
            datos = open(os.path.join(BASE_DIR, rel), "rb").read()
            info = zipfile.ZipInfo(arc, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3          # Unix, para que se lean los permisos
            modo = 0o755 if ejecutable(rel) else 0o644
            info.external_attr = modo << 16
            z.writestr(info, datos)

        info = zipfile.ZipInfo("LLM-Fit/LEEME-PRIMERO.txt",
                               date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3
        info.external_attr = 0o644 << 16
        z.writestr(info, (LEEME % {"plataformas": lista_plat}).replace("\n", "\r\n"))

    mb = os.path.getsize(out) / 1048576.0
    print()
    print("[ok] %s  (%.2f MB, %d archivos)" % (out, mb, len(incluir) + 1))
    if vendorizados:
        print("     incluye el binario de llmfit: el destino NO necesita")
        print("     internet ni uv, solo Python 3.8+")
    else:
        print("     el destino necesita uv (o llmfit ya instalado)")
        print("     para vendorizar el binario:  --plataformas win_amd64")


if __name__ == "__main__":
    main()
