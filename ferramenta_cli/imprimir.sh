#!/usr/bin/env bash
# Atalho de execucao. Usa o .venv se existir, senao o python3 do sistema.
cd "$(dirname "$0")"
if [ -x ".venv/bin/python" ]; then
    exec ./.venv/bin/python imprime_termica.py "$@"
else
    exec python3 imprime_termica.py "$@"
fi
