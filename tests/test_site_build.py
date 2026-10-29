"""Construye el sitio de producción y lo comprueba bajo la ruta base de site_url (mkdocs.yml)."""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import autonav
import check_site

ROOT = Path(__file__).resolve().parent.parent
BASE = check_site.default_base()  # derivado de site_url: no depende del nombre del repo


def documentos_reales():
    """Documentos que hay de verdad en docs/ (título interno, ruta .md), sin fijar nombres de archivo."""
    return [(titulo, ruta) for titulo, ruta, _ in autonav.documents(autonav._practicas(ROOT / "docs"))]


def html_de(site, ruta_md):
    return site / (ruta_md[:-3] + "/index.html")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("build") / "site"
    res = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "-d", str(out)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    return out


def test_paginas_principales_existen(site):
    for rel in ("index.html", "404.html"):
        assert (site / rel).is_file(), rel
    for gone in ("equipo", "organizacion", "contribuir"):
        assert not (site / gone).exists(), gone


def test_todos_los_documentos_se_publican(site):
    docs = documentos_reales()
    assert docs, "no hay documentos en docs/practicas/"
    for titulo, ruta in docs:
        page = html_de(site, ruta)
        assert page.is_file(), f"{ruta} no se ha publicado en {page}"
        assert titulo in page.read_text(encoding="utf-8")


def test_inicio_tiene_practicas_y_todos_los_documentos(site):
    page = (site / "index.html").read_text(encoding="utf-8")
    assert "Prácticas" in page and "Todos los documentos" in page
    # Cada documento se nombra por su título interno (H1) en la galería.
    for titulo, _ in documentos_reales():
        assert titulo in page, titulo
    assert "doc-grid" in page


def test_enlaces_recursos_y_ancla_bajo_ruta_base(site):
    assert check_site.check_links(site, BASE) == []


def test_404_coherente(site):
    assert check_site.check_404(site, BASE) == []


def test_sin_secretos_ni_archivos_internos(site):
    assert check_site.check_secrets(site) == []
    for name in (".env", "mkdocs.yml", "requirements.txt", ".git"):
        assert not (site / name).exists()


def test_sin_recursos_externos(site):
    index = (site / "index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in index
    assert "google-analytics" not in index


def test_documento_nuevo_se_publica_sin_tocar_navegacion(tmp_path):
    work = tmp_path / "proyecto"
    shutil.copytree(ROOT, work, ignore=shutil.ignore_patterns(".venv", "site", ".git", "__pycache__", ".pytest_cache"))
    nuevo = work / "docs/practicas/02-prueba/01-apartado/Instalación con tilde.md"
    nuevo.parent.mkdir(parents=True)
    nuevo.write_text("# Título interno nuevo\n\n## Subtítulo\n", encoding="utf-8")
    out = tmp_path / "site"
    res = subprocess.run([sys.executable, "-m", "mkdocs", "build", "-d", str(out)],
                         cwd=work, capture_output=True, text=True)
    assert res.returncode == 0, res.stdout + res.stderr
    idx = (out / "index.html").read_text(encoding="utf-8")
    assert "Prueba" in idx                      # tarjeta de la práctica nueva
    assert "Título interno nuevo" in idx        # el documento se nombra por su H1
    assert check_site.check_links(out, BASE) == []
