"""Navegación automática para Bitácora SAD.

Construye el menú lateral (práctica > apartado > documentos) a partir de las
carpetas y los archivos Markdown de docs/practicas/. No hace falta front matter
ni editar listas de navegación.

Reglas (ver README.md):
- El primer H1 fuera de bloques de código es el título del documento y es el
  nombre con el que se enlaza en el menú y en la página de inicio.
- Los prefijos numéricos (01-, 02_...) ordenan y no se muestran.
- index.md es opcional y actúa como portada de su práctica o apartado; su
  contenido se completa con la lista de lo que contiene.
- Carpetas sin Markdown, carpetas de recursos, archivos ocultos y enlaces
  simbólicos no entran en el menú (los enlaces simbólicos tampoco se publican).
- En docs/index.md, los marcadores <!-- practicas --> y <!-- documentos -->
  se sustituyen por la vista de prácticas y por la lista de todos los documentos.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path

log = logging.getLogger("mkdocs.hooks.autonav")

PREFIX_RE = re.compile(r"^(\d+)[-_.\s]+")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
ATX_RE = re.compile(r"^ {0,3}#[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")
SETEXT_RE = re.compile(r"^ {0,3}=+[ \t]*$")

# Carpetas de recursos: nunca son secciones del menú.
RESOURCE_DIRS = {
    "assets", "img", "images", "imagenes", "imágenes", "recursos", "media",
    "videos", "vídeos", "adjuntos", "capturas", "stylesheets", "javascripts",
}

HOME = "index.md"
HOME_LABEL = "Inicio"
PRACTICAS_DIR = "practicas"
MARK_PRACTICAS = "<!-- practicas -->"
MARK_DOCUMENTOS = "<!-- documentos -->"


# --------------------------------------------------------------------------
# Utilidades de texto
# --------------------------------------------------------------------------
def _plain(text: str) -> str:
    """Quita marcas Markdown sencillas de un título."""
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[`*_]{1,3}", "", text)
    return text.strip()


def first_h1(text: str) -> str | None:
    """Devuelve el primer H1 válido (ignora bloques de código y front matter)."""
    lines = text.lstrip("\ufeff").splitlines()
    i = 0
    if lines and lines[0].strip() == "---":
        for j in range(1, len(lines)):
            if lines[j].strip() in ("---", "..."):
                i = j + 1
                break
    fence: tuple[str, int] | None = None
    prev = ""
    in_comment = False
    for line in lines[i:]:
        if in_comment:
            if "-->" in line:
                in_comment = False
            prev = ""
            continue
        m = FENCE_RE.match(line)
        if fence is None and m:
            fence = (m.group(1)[0], len(m.group(1)))
            prev = ""
            continue
        if fence is not None:
            stripped = line.strip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= fence[1]:
                fence = None
            continue
        if line.lstrip().startswith("<!--") and "-->" not in line:
            in_comment = True
            continue
        if line.startswith(("    ", "\t")) and not prev.strip():
            prev = line
            continue  # bloque de código indentado
        m = ATX_RE.match(line)
        if m:
            title = _plain(m.group(1))
            if title:
                return title
        elif SETEXT_RE.match(line) and prev.strip() and not prev.startswith("#"):
            title = _plain(prev)
            if title:
                return title
        prev = line
    return None


def first_paragraph(text: str) -> str | None:
    """Primer párrafo de texto plano tras el H1 (para las tarjetas de inicio)."""
    seen_h1 = False
    para: list[str] = []
    for line in text.lstrip("\ufeff").splitlines():
        s = line.strip()
        if not seen_h1:
            if ATX_RE.match(line):
                seen_h1 = True
            continue
        if not s:
            if para:
                break
            continue
        if s.startswith(("#", ">", "-", "*", "|", "<", "`", "!", "=")) or s[0].isdigit():
            if para:
                break
            continue
        para.append(s)
    return _plain(" ".join(para)) if para else None


def clean_label(name: str) -> str:
    """Etiqueta legible a partir de un nombre de archivo o carpeta."""
    stem = name[:-3] if name.lower().endswith(".md") else name
    stem = PREFIX_RE.sub("", stem)
    stem = re.sub(r"[-_]+", " ", stem).strip()
    return stem[:1].upper() + stem[1:] if stem else name


def sort_key(name: str) -> tuple:
    m = PREFIX_RE.match(name)
    base = unicodedata.normalize("NFKD", PREFIX_RE.sub("", name)).casefold()
    return (0, int(m.group(1)), base, name) if m else (1, 0, base, name)


# --------------------------------------------------------------------------
# Descubrimiento
# --------------------------------------------------------------------------
def _is_safe(path: Path, docs_root: Path) -> bool:
    """False para ocultos, enlaces simbólicos o rutas que salen de docs/."""
    if path.name.startswith(".") or path.is_symlink():
        return False
    try:
        path.resolve().relative_to(docs_root.resolve())
    except ValueError:
        return False
    return True


def _read(path: Path) -> str:
    try:
        return path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return ""


def _read_title(path: Path) -> str | None:
    return first_h1(_read(path))


def _dir_entries(directory: Path, docs_root: Path):
    dirs, files = [], []
    for child in sorted(directory.iterdir(), key=lambda p: sort_key(p.name)):
        if not _is_safe(child, docs_root):
            continue
        if child.is_dir():
            if child.name.lower() in RESOURCE_DIRS or child.name.startswith("_"):
                continue
            dirs.append(child)
        elif child.suffix.lower() == ".md" and child.name.lower() != "index.md":
            files.append(child)
    return dirs, files


def _children(directory: Path, docs_root: Path) -> list:
    """Hijos de una carpeta en formato `nav` de MkDocs (sin su index.md)."""
    dirs, files = _dir_entries(directory, docs_root)
    out = []
    for item in sorted(dirs + files, key=lambda p: sort_key(p.name)):
        if item.is_dir():
            sub = _section(item, docs_root)
            if sub:
                out.append({sub[0]: sub[1]})
        else:
            rel = item.relative_to(docs_root).as_posix()
            out.append({_read_title(item) or clean_label(item.name): rel})
    return out


def _section(directory: Path, docs_root: Path):
    """Devuelve (etiqueta, [hijos]) o None si la carpeta no tiene Markdown."""
    index = directory / "index.md"
    has_index = index.is_file() and _is_safe(index, docs_root)
    children = _children(directory, docs_root)
    if not children and not has_index:
        return None  # carpeta vacía (o solo recursos): no aparece
    if has_index:
        label = _read_title(index) or clean_label(directory.name)
        children.insert(0, index.relative_to(docs_root).as_posix())
    else:
        label = clean_label(directory.name)
    return label, children


def _practicas(docs_root: Path) -> list:
    """Lista de prácticas: [{etiqueta: [hijos]}, ...] (los hijos son apartados y documentos)."""
    base = docs_root / PRACTICAS_DIR
    if not base.is_dir() or not _is_safe(base, docs_root):
        return []
    return _children(base, docs_root)


def build_nav(docs_dir: str | Path) -> list:
    """Menú: Inicio y, debajo, cada práctica con sus apartados y documentos."""
    docs_root = Path(docs_dir)
    nav: list = []
    home = docs_root / HOME
    if home.is_file() and _is_safe(home, docs_root):
        nav.append({HOME_LABEL: HOME})
    nav.extend(_practicas(docs_root))
    return nav


# --------------------------------------------------------------------------
# Recorridos sobre la estructura del menú
# --------------------------------------------------------------------------
def _is_index(path: str) -> bool:
    return path.endswith("index.md")


def count_documents(nav) -> int:
    total = 0
    for item in nav:
        if isinstance(item, str):
            total += 0 if _is_index(item) else 1
        elif isinstance(item, dict):
            for value in item.values():
                total += count_documents(value) if isinstance(value, list) else (
                    0 if _is_index(value) else 1)
    return total


def _landing(children: list) -> str | None:
    """Página a la que lleva una sección: su index.md o, si no, su primer documento."""
    for child in children:
        if isinstance(child, str):
            return child
        for value in child.values():
            target = _landing(value) if isinstance(value, list) else value
            if target:
                return target
    return None


def documents(nav, trail: tuple[str, ...] = ()):
    """Recorre todos los documentos en orden de menú: (título, ruta, camino de secciones)."""
    for item in nav:
        if isinstance(item, str):
            continue  # index.md de la sección: no es un documento
        for label, value in item.items():
            if isinstance(value, list):
                yield from documents(value, trail + (label,))
            elif not _is_index(value):
                yield label, value, trail


def _rel(target: str, page_uri: str) -> str:
    """Enlace relativo (formato Markdown, con .md) desde una página a otra."""
    start = os.path.dirname(page_uri) or "."
    return Path(os.path.relpath(target, start)).as_posix()


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


# --------------------------------------------------------------------------
# Contenido generado
# --------------------------------------------------------------------------
def render_practicas(docs_root: Path, page_uri: str = HOME) -> str:
    """Vista de prácticas: una tarjeta por práctica con sus apartados."""
    practicas = _practicas(docs_root)
    if not practicas:
        return "Todavía no hay prácticas publicadas.\n"
    cards = []
    for item in practicas:
        for label, value in item.items():
            if not isinstance(value, list):  # documento suelto en practicas/
                continue
            href = _rel(_landing(value), page_uri)
            lines = [f"-   **[{label}]({href})**", ""]
            index = next((c for c in value if isinstance(c, str) and _is_index(c)), None)
            desc = first_paragraph(_read(docs_root / index)) if index else None
            if desc:
                lines += [f"    {desc}", ""]
            apartados = [(l, v) for c in value if isinstance(c, dict) for l, v in c.items()
                         if isinstance(v, list)]
            for a_label, a_children in apartados:
                a_href = _rel(_landing(a_children), page_uri)
                n = count_documents([{a_label: a_children}])
                lines.append(f"    - [{a_label}]({a_href}) · {_plural(n, 'documento', 'documentos')}")
            if apartados:
                lines.append("")
            else:
                n = count_documents([{label: value}])
                lines += [f"    {_plural(n, 'documento', 'documentos')}", ""]
            cards.append("\n".join(lines))
    return '<div class="grid cards" markdown>\n\n' + "\n\n".join(cards) + "\n\n</div>\n"


def render_documentos(docs_root: Path, page_uri: str = HOME) -> str:
    """Galería de todos los documentos: un widget compacto por documento (título interno + ubicación)."""
    cards = []
    for label, path, trail in documents(_practicas(docs_root)):
        ruta = " › ".join(trail)
        lines = [f"-   [{label}]({_rel(path, page_uri)})"]
        if ruta:
            lines += ["", f'    <span class="doc-ruta">{ruta}</span>']
        cards.append("\n".join(lines))
    if not cards:
        return "Todavía no hay documentos publicados.\n"
    return '<div class="grid cards doc-grid" markdown>\n\n' + "\n\n".join(cards) + "\n\n</div>\n"


def _render_tree(children: list, page_uri: str, depth: int = 0) -> list[str]:
    pad = "    " * depth
    out = []
    for item in children:
        if isinstance(item, str):
            continue
        for label, value in item.items():
            if isinstance(value, list):
                target = _landing(value)
                head = f"[{label}]({_rel(target, page_uri)})" if target else label
                out.append(f"{pad}- **{head}**")
                out.extend(_render_tree(value, page_uri, depth + 1))
            else:
                out.append(f"{pad}- [{label}]({_rel(value, page_uri)})")
    return out


def render_contenido(docs_root: Path, page_uri: str) -> str:
    """Lista de lo que contiene la carpeta de un index.md (práctica o apartado)."""
    directory = (docs_root / page_uri).parent
    children = _children(directory, docs_root)
    lines = _render_tree(children, page_uri)
    return "\n".join(lines) + "\n" if lines else ""


# --------------------------------------------------------------------------
# Eventos de MkDocs
# --------------------------------------------------------------------------
def on_files(files, config):
    docs_root = Path(config["docs_dir"])

    # 1) Seguridad: no publicar enlaces simbólicos ni nada fuera de docs/.
    for f in list(files):
        src = Path(f.abs_src_path) if f.abs_src_path else None
        # Solo se vigilan los archivos de docs/ (no los del tema ni los generados).
        if src is None or not f.src_dir or Path(f.src_dir) != docs_root:
            continue
        unsafe = False
        cur = src
        while cur != docs_root and cur != cur.parent:
            if cur.is_symlink():
                unsafe = True
                break
            cur = cur.parent
        if not unsafe:
            try:
                src.resolve().relative_to(docs_root.resolve())
            except ValueError:
                unsafe = True
        if unsafe:
            log.info("Se omite (enlace simbólico o fuera de docs/): %s", f.src_uri)
            files.remove(f)

    # 2) Menú automático (se recalcula en cada compilación).
    config["nav"] = build_nav(docs_root)
    return files


def on_page_markdown(markdown, page, config, files):
    docs_root = Path(config["docs_dir"])
    uri = page.file.src_uri
    if uri == HOME:
        return (markdown
                .replace(MARK_PRACTICAS, render_practicas(docs_root, uri))
                .replace(MARK_DOCUMENTOS, render_documentos(docs_root, uri)))
    if uri.startswith(f"{PRACTICAS_DIR}/") and uri.endswith("/index.md"):
        contenido = render_contenido(docs_root, uri)
        if contenido:
            return markdown.rstrip() + "\n\n## Contenido\n\n" + contenido
    return markdown
