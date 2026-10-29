"""Comprobaciones sobre el sitio ya construido (carpeta site/).

Uso:  python tools/check_site.py [carpeta_site] [prefijo_base]
Comprueba enlaces internos, imágenes, CSS y JS bajo la ruta base del
repositorio y busca secretos. Si no se indica, el prefijo base y el dominio
se leen de "site_url" en mkdocs.yml, así que no dependen del nombre del repo.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urldefrag, urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent


def site_url() -> str:
    """Devuelve el site_url de mkdocs.yml (p. ej. https://usuario.github.io/Repo/)."""
    text = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    m = re.search(r"^site_url:\s*(\S+)\s*$", text, re.MULTILINE)
    if not m:
        raise RuntimeError("mkdocs.yml no define site_url")
    return m.group(1).strip("\"'")


def default_base() -> str:
    """Prefijo de ruta bajo el que se publica el sitio (p. ej. /Repo/)."""
    path = urlparse(site_url()).path or "/"
    return path if path.endswith("/") else path + "/"


def default_origin() -> str:
    """Dominio del sitio publicado (p. ej. https://usuario.github.io)."""
    u = urlparse(site_url())
    return f"{u.scheme}://{u.netloc}"


SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
]
FORBIDDEN_NAMES = {".env", "id_rsa", "id_ed25519"}
FORBIDDEN_SUFFIXES = (".pem", ".key", ".bak", ".orig", ".swp", ".pfx", ".crt")


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs: list[tuple[str, str]] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "a" and a.get("href"):
            self.refs.append(("a", a["href"]))
        elif tag in ("img", "script", "source") and a.get("src"):
            self.refs.append((tag, a["src"]))
        elif tag == "link" and a.get("href") and a.get("rel") in ("stylesheet", "icon", "shortcut icon"):
            self.refs.append(("link", a["href"]))


def _target_file(site: Path, base: str, url_path: str) -> Path | None:
    if not url_path.startswith(base):
        return None
    rel = unquote(url_path[len(base):])
    p = site / rel
    if p.is_dir() or rel == "" or rel.endswith("/"):
        p = p / "index.html"
    return p


def check_links(site: Path, base: str | None = None) -> list[str]:
    base = base or default_base()
    errors: list[str] = []
    host = "http://localhost"
    pages = sorted(site.rglob("*.html"))
    for page in pages:
        rel = page.relative_to(site).as_posix()
        if rel == "404.html":
            continue  # se sirve en cualquier ruta; se revisa aparte
        page_url = host + base + (rel[:-len("index.html")] if rel.endswith("index.html") else rel)
        parser = _Refs()
        parser.feed(page.read_text(encoding="utf-8"))
        for kind, ref in parser.refs:
            if ref.startswith(("mailto:", "tel:", "data:", "javascript:")):
                continue
            absolute = urljoin(page_url, ref)
            u = urlparse(absolute)
            if u.netloc != "localhost":
                if kind in ("script", "link") and u.scheme in ("http", "https"):
                    errors.append(f"{rel}: recurso externo no permitido: {ref}")
                continue
            clean, frag = urldefrag(absolute)
            target = _target_file(site, base, urlparse(clean).path)
            if target is None:
                errors.append(f"{rel}: enlace fuera de la ruta base {base}: {ref}")
            elif not target.is_file():
                errors.append(f"{rel}: no existe el destino de {ref}")
            elif frag and target.suffix == ".html":
                ids = _Refs()
                ids.feed(target.read_text(encoding="utf-8"))
                if unquote(frag) not in ids.ids:
                    errors.append(f"{rel}: ancla inexistente #{frag} en {ref}")
    return errors


def check_404(site: Path, base: str | None = None) -> list[str]:
    base = base or default_base()
    p = site / "404.html"
    if not p.is_file():
        return ["falta 404.html"]
    text = p.read_text(encoding="utf-8")
    errs = []
    if "Volver al inicio" not in text:
        errs.append("404.html no contiene el enlace «Volver al inicio»")
    if f'href="{default_origin()}{base}"' not in text:
        errs.append("404.html no enlaza al inicio con la dirección completa")
    return errs


def check_secrets(site: Path) -> list[str]:
    errors = []
    for f in site.rglob("*"):
        if not f.is_file():
            continue
        if f.name in FORBIDDEN_NAMES or f.name.endswith(FORBIDDEN_SUFFIXES):
            errors.append(f"archivo prohibido publicado: {f.relative_to(site)}")
            continue
        if f.suffix in (".html", ".md", ".txt", ".json", ".xml", ".js", ".css", ".svg", ".yml"):
            text = f.read_text(encoding="utf-8", errors="ignore")
            for pat in SECRET_PATTERNS:
                if pat.search(text):
                    errors.append(f"posible secreto en {f.relative_to(site)}")
    return errors


def main(argv: list[str]) -> int:
    site = Path(argv[1] if len(argv) > 1 else "site")
    base = argv[2] if len(argv) > 2 else default_base()
    errors = check_links(site, base) + check_404(site, base) + check_secrets(site)
    for e in errors:
        print("ERROR:", e)
    print(f"{len(list(site.rglob('*.html')))} páginas revisadas, {len(errors)} problemas.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
