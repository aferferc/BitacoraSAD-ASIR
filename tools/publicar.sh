#!/usr/bin/env bash
# Crea el repositorio en GitHub (si no existe), sube el proyecto y activa Pages.
# Uso:  bash tools/publicar.sh            (desde la carpeta del proyecto)
# No usa "push --force", no borra nada y no pide tokens: la autenticación la hace "gh auth login".
set -euo pipefail

OWNER="${OWNER:-aferferc}"
REPO="${REPO:-BitacoraSAD-ASIR}"

command -v git >/dev/null || { echo "Falta git: sudo apt install git"; exit 1; }
command -v gh  >/dev/null || { echo "Falta GitHub CLI: sudo apt install gh   (y luego: gh auth login)"; exit 1; }
gh auth status >/dev/null 2>&1 || { echo "No has iniciado sesión. Ejecuta: gh auth login"; exit 1; }

CUENTA="$(gh api user --jq .login)"
echo "Cuenta autenticada en GitHub: $CUENTA"
if [ "$CUENTA" != "$OWNER" ]; then
  echo "Aviso: la cuenta ($CUENTA) no es la prevista ($OWNER)."
  read -r -p "¿Continuar con $CUENTA? [s/N] " r; [[ "$r" =~ ^[sS]$ ]] || exit 1
  OWNER="$CUENTA"
fi

if gh repo view "$OWNER/$REPO" >/dev/null 2>&1; then
  echo "El repositorio $OWNER/$REPO YA EXISTE. No se sobrescribe nada."
  echo "Revisa su contenido o usa otro nombre:  REPO=OtroNombre bash tools/publicar.sh"
  exit 1
fi

echo
echo "Se va a crear el repositorio PÚBLICO $OWNER/$REPO: todos sus archivos serán visibles por cualquiera."
read -r -p "¿Confirmas? [s/N] " r; [[ "$r" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 1; }

[ -d .git ] || git init -b main
git add -A
git diff --cached --quiet || git commit -m "Proyecto inicial: Bitácora SAD"
gh repo create "$OWNER/$REPO" --public --source . --remote origin --push \
  --description "Bitácora SAD · Laboratorio de Base de Datos · 2.º ASIR · IES Gonzalo Nazareno"

# Activar GitHub Pages con "GitHub Actions" como origen.
gh api -X POST "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || gh api -X PUT "repos/$OWNER/$REPO/pages" -f build_type=workflow >/dev/null 2>&1 \
  || echo "No se pudo activar Pages automáticamente: Settings → Pages → Source: GitHub Actions."

echo
echo "Hecho. Sigue el despliegue en: https://github.com/$OWNER/$REPO/actions"
echo "Dirección prevista (aún sin comprobar): https://$OWNER.github.io/$REPO/"
