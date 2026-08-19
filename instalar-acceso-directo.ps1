<#
    Crea accesos directos para lanzar LLM Fit con doble clic.

    Uso:
        powershell -ExecutionPolicy Bypass -File instalar-acceso-directo.ps1

    Opciones:
        -SoloEscritorio     no tocar el menu Inicio
        -Desinstalar        borrar los accesos directos creados

    No instala nada ni modifica el registro: solo crea archivos .lnk.
#>
param(
    [switch]$SoloEscritorio,
    [switch]$Desinstalar
)

$ErrorActionPreference = 'Stop'

$raiz     = Split-Path -Parent $MyInvocation.MyCommand.Path
$bat      = Join-Path $raiz 'LLM-Fit.bat'
$nombre   = 'LLM Fit.lnk'
$escrit   = Join-Path ([Environment]::GetFolderPath('Desktop')) $nombre
$inicio   = Join-Path ([Environment]::GetFolderPath('Programs')) $nombre

if ($Desinstalar) {
    foreach ($p in @($escrit, $inicio)) {
        if (Test-Path $p) { Remove-Item $p -Force; Write-Host "[ok] borrado $p" }
    }
    Write-Host "`nListo. La carpeta del proyecto no se toco."
    exit 0
}

if (-not (Test-Path $bat)) {
    Write-Error "No se encontro LLM-Fit.bat junto a este script ($raiz)."
}

# Aviso temprano: sin ninguno de los dos, el acceso directo no va a funcionar.
$tieneUv     = [bool](Get-Command uv     -ErrorAction SilentlyContinue)
$tienePython = [bool](Get-Command python -ErrorAction SilentlyContinue)
if (-not $tieneUv -and -not $tienePython) {
    Write-Warning "No se encontro ni uv ni Python en el PATH."
    Write-Warning "El acceso directo se va a crear igual, pero antes de usarlo instala uv:"
    Write-Warning '  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"'
}

function New-Acceso($destino) {
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($destino)
    $lnk.TargetPath       = $bat
    $lnk.WorkingDirectory = $raiz
    $lnk.Description      = 'Que modelos LLM entran en la GPU de esta maquina'
    # 7 = minimizada: la consola queda fuera del paso, pero visible en la
    # barra de tareas para poder cerrarla y apagar el servidor.
    $lnk.WindowStyle      = 7
    $lnk.IconLocation     = "$env:SystemRoot\System32\SHELL32.dll,15"
    $lnk.Save()
    Write-Host "[ok] $destino"
}

New-Acceso $escrit
if (-not $SoloEscritorio) {
    New-Acceso $inicio
}

Write-Host ""
Write-Host "Listo. Doble clic en 'LLM Fit' del escritorio."
Write-Host "La app abre en su propia ventana; para cerrarla, cerra tambien"
Write-Host "la consola minimizada (asi se apaga el backend llmfit)."
if (-not $SoloEscritorio) {
    Write-Host "Tambien podes buscarlo como 'LLM Fit' en el menu Inicio y anclarlo."
}
