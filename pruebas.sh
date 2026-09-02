#!/usr/bin/env bash
# Corre las pruebas. Sin argumentos, todas; con uno, solo ese módulo.
#   ./pruebas.sh              todas
#   ./pruebas.sh scheduler    solo tests/test_scheduler.py
set -euo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -gt 0 ]; then
  exec python3 -m unittest -v "tests.test_$1"
fi
exec python3 -m unittest discover -s tests -t . "$@"
