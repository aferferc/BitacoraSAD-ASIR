# Bitácora SAD

**Laboratorio de Base de Datos · 2.º ASIR · IES Gonzalo Nazareno · Curso 2026/27**

Blog técnico sencillo con la documentación de las prácticas. Es un sitio estático (MkDocs + Material for MkDocs) que se publica en GitHub Pages: <https://aferferc.github.io/BitacoraSAD-ASIR/>

## Qué tiene

- **Página de inicio** con la vista de *Prácticas* (con sus apartados) y la lista de *Todos los documentos*.
- **Barra lateral izquierda** con el árbol de documentos, plegable:

  ```text
  Práctica
    Apartado
      Documento
  ```
- Cada documento se nombra por su **título interno** (el primer `#` del archivo).
- Buscador, copiar código y tema oscuro estilo terminal.

## Cómo añadir contenido

**Subir un `.md` es suficiente**: el menú y la página de inicio se generan solos.

```text
docs/
├── index.md                              ← página de inicio
└── practicas/
    └── 01-servidores-clientes/           ← práctica
        ├── index.md                      ← portada de la práctica (opcional)
        └── 01-oracle/                    ← apartado
            ├── index.md                  ← portada del apartado (opcional)
            └── instalacion.md            ← documento
```

| Quiero… | Dónde |
|---|---|
| Añadir un documento | `docs/practicas/<práctica>/<apartado>/documento.md` |
| Añadir un apartado | Carpeta nueva dentro de la práctica, con algún `.md` |
| Añadir una práctica | Carpeta nueva en `docs/practicas/`, con algún `.md` |

Reglas:

- El **primer `#`** del archivo es su título. Sin `#`, se usa el nombre del archivo.
- `01-`, `02-`… ordenan y no se muestran.
- `index.md` es opcional. Su primer `#` da nombre a la práctica o apartado, y el primer párrafo se usa como descripción en la página de inicio. La lista de lo que contiene se añade sola.
- Las carpetas vacías, las de imágenes (`capturas/`, `imagenes/`, `assets/`…), los archivos ocultos y las carpetas que empiezan por `_` no salen en el menú.
- Las imágenes van junto al documento (p. ej. `capturas/foto.png`).
- Las listas anidadas necesitan **4 espacios** de sangría.
- Nunca se publican contraseñas, tokens, claves privadas ni capturas con datos privados.

## Desarrollo local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
mkdocs serve                       # http://127.0.0.1:8000/BitacoraSAD-ASIR/
python -m pytest -q                # pruebas (opcionales)
mkdocs build                       # construir en site/
python tools/check_site.py site    # comprobar enlaces y recursos (opcional)
```

Configuración en `mkdocs.yml`, estilos en `docs/assets/extra.css` y generación del menú en `hooks/autonav.py`.

## Publicar

Cada cambio que llega a `main` ejecuta `.github/workflows/pages.yml` (construcción → despliegue). En **Settings → Pages → Source** debe estar elegido **GitHub Actions**. La primera vez puede usarse `bash tools/publicar.sh`.
