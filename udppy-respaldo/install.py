#!/usr/bin/env python3
"""
Instalación (pip) y verificación de dependencias en un solo archivo.

Uso:
  python install.py
  python install.py --venv
  python install.py --verify-only
  python install.py --no-pip
  python install.py --check-uvloop

systemd (solo Linux, como root):
  sudo python3 install.py --install-systemd
  sudo python3 install.py --install-systemd --enable-systemd
  sudo python3 install.py --install-systemd --systemd-listen 0.0.0.0:7400 --systemd-dns 8.8.8.8:53
  sudo python3 install.py --remove-systemd

Descarga desde GitHub (rama main, carpeta udppy/) y luego instala en ese directorio:
  python3 install.py --install-from-github --dest /opt/udppy
  sudo python3 install.py --install-from-github --dest /opt/udppy --install-systemd --enable-systemd

Script mínimo (bash; descarga install.py y delega aquí):
  curl -fsSL -o /tmp/udppy-bootstrap.sh \\
    https://raw.githubusercontent.com/josecarlosmeza/linux/main/udppy/bootstrap.sh
  chmod +x /tmp/udppy-bootstrap.sh
  sudo /tmp/udppy-bootstrap.sh --install-systemd --enable-systemd
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import os
import shlex
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

MIN_PY = (3, 9)

# Rama main del repositorio público (contenido en subcarpeta udppy/)
GITHUB_REPO_ZIP = (
    "https://github.com/josecarlosmeza/linux/archive/refs/heads/main.zip"
)


def _root() -> Path:
    return Path(__file__).resolve().parent


def download_udppy_from_github(
    dest: Path,
    *,
    zip_url: str,
    force: bool,
) -> bool:
    """
    Descarga el ZIP de la rama main y extrae solo la carpeta udppy/ en dest.
    """
    marker = dest / "udppy_server.py"
    if marker.is_file() and not force:
        _fail(
            f"Ya existe {marker}; use --force para volver a descargar o borre {dest}"
        )
        return False

    print(f"--- Descarga desde GitHub ---\n\n  URL: {zip_url}\n")
    try:
        with urlopen(zip_url, timeout=120) as resp:
            data = resp.read()
    except URLError as e:
        _fail(f"No se pudo descargar el repositorio: {e}")
        return False

    try:
        if dest.exists() and force:
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            prefix: str | None = None
            for name in zf.namelist():
                if name.endswith("udppy/install.py"):
                    prefix = name[: -len("install.py")]
                    break
            if not prefix:
                _fail("El ZIP no contiene udppy/install.py (¿rama o repo distinto?)")
                return False

            for name in zf.namelist():
                if name.endswith("/") or not name.startswith(prefix):
                    continue
                rel = name[len(prefix) :]
                if not rel or rel.startswith(".."):
                    continue
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(name) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except OSError as e:
        _fail(f"Extracción en {dest}: {e}")
        return False

    if not (dest / "install.py").is_file():
        _fail(f"Extracción incompleta: falta {dest / 'install.py'}")
        return False

    _ok(f"udppy descargado en {dest.resolve()}")
    return True


def _venv_python(root: Path) -> Path:
    if sys.platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    for name in ("python3", "python"):
        p = root / ".venv" / "bin" / name
        if p.exists():
            return p
    return root / ".venv" / "bin" / "python3"


def _running_from_project_venv(root: Path) -> bool:
    try:
        return Path(sys.executable).resolve() == _venv_python(root).resolve()
    except OSError:
        return False


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _fail(msg: str) -> None:
    print(f"  [ERROR] {msg}", file=sys.stderr)


def check_python_version() -> bool:
    if sys.version_info < MIN_PY:
        _fail(
            f"Se requiere Python {MIN_PY[0]}.{MIN_PY[1]}+; "
            f"tienes {sys.version_info.major}.{sys.version_info.minor}"
        )
        return False
    _ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
    return True


def check_stdlib() -> bool:
    mods = (
        "asyncio",
        "argparse",
        "collections",
        "logging",
        "socket",
        "struct",
        "time",
    )
    for name in mods:
        try:
            __import__(name)
        except ImportError as e:
            _fail(f"módulo estándar {name!r}: {e}")
            return False
    _ok("módulos estándar necesarios importables")
    return True


def check_project_modules() -> bool:
    root = _root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    for name in ("udppy_proto", "linux_tune", "udppy_server"):
        try:
            __import__(name)
        except ImportError as e:
            _fail(f"import {name}: {e}")
            return False
    _ok("udppy_proto, linux_tune, udppy_server")
    return True


def check_uvloop_required() -> bool:
    spec = importlib.util.find_spec("uvloop")
    if spec is None:
        _fail("uvloop no instalado (opcional en Linux: pip install uvloop)")
        return False
    try:
        import uvloop  # noqa: F401
    except ImportError as e:
        _fail(f"uvloop: {e}")
        return False
    _ok("uvloop disponible (predeterminado en Linux en udppy_server)")
    return True


def verify(*, check_uvloop: bool) -> bool:
    print("--- Verificación ---\n")
    ok = True
    ok = check_python_version() and ok
    ok = check_stdlib() and ok
    ok = check_project_modules() and ok

    if check_uvloop:
        if sys.platform.startswith("linux"):
            ok = check_uvloop_required() and ok
        else:
            print("  [INFO] --check-uvloop omitido (solo aplica en Linux)")
    else:
        if sys.platform.startswith("linux"):
            spec = importlib.util.find_spec("uvloop")
            if spec is None:
                print(
                    "  [INFO] uvloop no instalado (opcional; pip install uvloop o requirements.txt)"
                )
            else:
                _ok("uvloop instalado (opcional)")

    print()
    if ok:
        print("Resultado verificación: correcto.")
    else:
        print("Resultado verificación: errores.", file=sys.stderr)
    return ok


def run_pip_install(root: Path) -> bool:
    req = root / "requirements.txt"
    if not req.is_file():
        _fail(f"No se encuentra {req}")
        return False
    print("--- Instalación pip ---\n")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--upgrade", "pip"],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(req)],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        _fail(f"pip falló: {e}")
        return False
    print("\nInstalación pip finalizada.\n")
    return True


SYSTEMD_UNIT_NAME = "udppy-server.service"
SYSTEMD_UNIT_DIR = Path("/etc/systemd/system")


def _is_linux() -> bool:
    return sys.platform.startswith("linux")


def _systemd_exec_line(
    py: Path, server: Path, listen: str, dns: str | None, *, use_uvloop: bool
) -> str:
    parts = [str(py.resolve()), str(server.resolve()), "--listen-addr", listen]
    if dns:
        parts.extend(["--dns", dns])
    if not use_uvloop:
        parts.append("--no-uvloop")
    return " ".join(shlex.quote(p) for p in parts)


def _render_systemd_unit(
    root: Path,
    *,
    python_exe: Path,
    listen: str,
    dns: str | None,
    use_uvloop: bool,
) -> str:
    server = root / "udppy_server.py"
    exec_start = _systemd_exec_line(
        python_exe, server, listen, dns, use_uvloop=use_uvloop
    )
    lines = [
        "# Generado por install.py — administrar con: systemctl status udppy-server",
        "[Unit]",
        "Description=udppy — túnel UDP compatible con badvpn/udpgw (tun2socks)",
        "After=network-online.target",
        "Wants=network-online.target",
        "",
        "[Service]",
        "Type=simple",
        "Environment=PYTHONUNBUFFERED=1",
        f"WorkingDirectory={root.resolve()}",
        f"ExecStart={exec_start}",
        "Restart=on-failure",
        "RestartSec=3",
        "LimitNOFILE=1048576",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "",
    ]
    return "\n".join(lines)


def _require_root() -> bool:
    try:
        if os.geteuid() != 0:
            _fail("Se requiere root. Ejemplo: sudo python3 install.py --install-systemd")
            return False
    except AttributeError:
        _fail("systemd solo está soportado en Linux")
        return False
    return True


def install_systemd(
    root: Path,
    *,
    python_exe: Path,
    listen: str,
    dns: str | None,
    enable: bool,
    use_uvloop: bool,
) -> bool:
    if not _is_linux():
        _fail("--install-systemd solo aplica en Linux")
        return False
    if not _require_root():
        return False
    if not (root / "udppy_server.py").is_file():
        _fail(f"No se encuentra {root / 'udppy_server.py'}")
        return False

    unit_path = SYSTEMD_UNIT_DIR / SYSTEMD_UNIT_NAME
    body = _render_systemd_unit(
        root, python_exe=python_exe, listen=listen, dns=dns, use_uvloop=use_uvloop
    )
    try:
        unit_path.write_text(body, encoding="utf-8")
    except OSError as e:
        _fail(f"No se pudo escribir {unit_path}: {e}")
        return False

    _ok(f"unidad instalada: {unit_path}")
    try:
        subprocess.run(
            ["systemctl", "daemon-reload"],
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        _fail(f"systemctl daemon-reload: {e}")
        return False
    _ok("systemctl daemon-reload")

    print("\n  Administración (systemd):")
    print("    systemctl status udppy-server")
    print("    systemctl start|stop|restart udppy-server")
    print("    journalctl -u udppy-server -f")
    print()

    if enable:
        try:
            subprocess.run(
                ["systemctl", "enable", "--now", "udppy-server"],
                check=True,
            )
            _ok("systemctl enable --now udppy-server")
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            _fail(f"systemctl enable --now: {e}")
            return False
    else:
        print(
            "  Para activar al arranque y arrancar ahora:\n"
            "    sudo systemctl enable --now udppy-server\n"
        )

    return True


def remove_systemd() -> bool:
    if not _is_linux():
        _fail("--remove-systemd solo aplica en Linux")
        return False
    if not _require_root():
        return False
    unit_path = SYSTEMD_UNIT_DIR / SYSTEMD_UNIT_NAME
    if not unit_path.is_file():
        _fail(f"No existe {unit_path}")
        return False
    try:
        subprocess.run(
            ["systemctl", "disable", "--now", "udppy-server"],
            check=False,
        )
        unit_path.unlink()
    except OSError as e:
        _fail(f"al quitar la unidad: {e}")
        return False
    try:
        subprocess.run(["systemctl", "daemon-reload"], check=True)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        _fail(f"systemctl daemon-reload: {e}")
        return False
    _ok("unidad eliminada; servicio udppy-server deshabilitado si existía")
    return True


def _argv_without_github_flags(argv: list[str]) -> list[str]:
    """Quita --install-from-github, --dest, --github-zip-url, --force y sus valores."""
    out: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--install-from-github":
            i += 1
            continue
        if a == "--force":
            i += 1
            continue
        if a == "--dest":
            i += 2
            continue
        if a.startswith("--dest="):
            i += 1
            continue
        if a == "--github-zip-url":
            i += 2
            continue
        if a.startswith("--github-zip-url="):
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def maybe_reexec_into_venv(root: Path) -> None:
    """Si --venv y aún no estamos en .venv, crear entorno y re-ejecutar este script."""
    if _running_from_project_venv(root):
        return
    import venv

    vpy = _venv_python(root)
    if not (root / ".venv").exists():
        print("Creando entorno virtual .venv ...\n")
        venv.create(root / ".venv", with_pip=True)
    if not vpy.exists():
        _fail(f"No se encontró intérprete en {vpy}")
        sys.exit(1)
    script = str(Path(__file__).resolve())
    new_argv = [str(vpy), script] + [a for a in sys.argv[1:] if a != "--venv"]
    os.execv(str(vpy), new_argv)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Instalar dependencias (pip) y verificar el proyecto udppy"
    )
    ap.add_argument(
        "--venv",
        action="store_true",
        help="Usar o crear .venv e instalar/verificar dentro de él",
    )
    ap.add_argument(
        "--verify-only",
        action="store_true",
        help="Solo verificar, sin pip install",
    )
    ap.add_argument(
        "--no-pip",
        action="store_true",
        help="No ejecutar pip (útil tras instalar manualmente)",
    )
    ap.add_argument(
        "--check-uvloop",
        action="store_true",
        help="En Linux, fallar si uvloop no está instalado",
    )
    ap.add_argument(
        "--install-systemd",
        action="store_true",
        help="Instalar unidad systemd (Linux, root) para administrar con systemctl",
    )
    ap.add_argument(
        "--remove-systemd",
        action="store_true",
        help="Quitar la unidad systemd udppy-server (Linux, root)",
    )
    ap.add_argument(
        "--enable-systemd",
        action="store_true",
        help="Tras --install-systemd: systemctl enable --now udppy-server",
    )
    ap.add_argument(
        "--systemd-listen",
        type=str,
        default="0.0.0.0:7300",
        metavar="ADDR:PUERTO",
        help="Dirección TCP en la unidad systemd (default: 0.0.0.0:7300)",
    )
    ap.add_argument(
        "--systemd-dns",
        type=str,
        default=None,
        metavar="HOST:PUERTO",
        help="Servidor DNS para la unidad systemd (p. ej. 8.8.8.8:53)",
    )
    ap.add_argument(
        "--systemd-python",
        type=Path,
        default=None,
        metavar="RUTA",
        help="Intérprete Python en ExecStart (default: python usado al ejecutar install.py)",
    )
    ap.add_argument(
        "--systemd-no-uvloop",
        action="store_true",
        help="En la unidad systemd, añadir --no-uvloop (por defecto se usa uvloop en Linux si está instalado)",
    )
    ap.add_argument(
        "--install-from-github",
        action="store_true",
        help=(
            "Descargar udppy desde GitHub (josecarlosmeza/linux, rama main) y continuar "
            "la instalación en --dest"
        ),
    )
    ap.add_argument(
        "--dest",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Con --install-from-github: directorio donde extraer (default: ./udppy en el cwd actual)"
        ),
    )
    ap.add_argument(
        "--github-zip-url",
        type=str,
        default=GITHUB_REPO_ZIP,
        metavar="URL",
        help=f"URL del ZIP de la rama (default: repositorio público en GitHub)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Con --install-from-github: borrar dest y volver a descargar si ya existía",
    )
    args = ap.parse_args()

    if args.install_from_github:
        dest = (args.dest if args.dest is not None else Path.cwd() / "udppy").resolve()
        if not download_udppy_from_github(
            dest, zip_url=args.github_zip_url, force=args.force
        ):
            return 1
        child = [sys.executable, str(dest / "install.py")] + _argv_without_github_flags(
            sys.argv[1:]
        )
        os.execv(child[0], child)

    root = _root()

    print("=== udppy — instalación y verificación ===\n")
    print(f"Directorio: {root}\n")

    if args.venv:
        maybe_reexec_into_venv(root)

    if args.remove_systemd:
        if args.install_systemd:
            _fail("Use solo una de --remove-systemd o --install-systemd")
            return 1
        return 0 if remove_systemd() else 1

    if not args.verify_only and not args.no_pip:
        if not run_pip_install(root):
            return 1

    if not verify(check_uvloop=args.check_uvloop):
        return 1

    if args.install_systemd:
        py = args.systemd_python if args.systemd_python else Path(sys.executable)
        if not install_systemd(
            root,
            python_exe=py,
            listen=args.systemd_listen,
            dns=args.systemd_dns,
            enable=args.enable_systemd,
            use_uvloop=not args.systemd_no_uvloop,
        ):
            return 1

    print("---\nListo. Ejemplo:\n")
    print(f'  cd "{root}"')
    ex = Path(sys.executable).name
    print(
        f"  {ex} udppy_server.py --listen-addr 0.0.0.0:7300 --dns 8.8.8.8:53\n"
    )
    if _is_linux() and not args.install_systemd:
        print(
            "  Servicio systemd (opcional, como root):\n"
            "    sudo python3 install.py --install-systemd --enable-systemd\n"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
