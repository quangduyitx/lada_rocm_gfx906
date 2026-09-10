#!/usr/bin/env bash
set -euo pipefail

SCRIPT_SOURCE="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_SOURCE")" && pwd)"

# Thiết lập môi trường ROCm tối ưu cho AMD Radeon Pro VII (GFX906 / Vega 20)
export HSA_OVERRIDE_GFX_VERSION=9.0.6
export ROCM_PATH=/opt/rocm
export HIP_VISIBLE_DEVICES=0
export ROCR_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF="garbage_collection_threshold:0.8,max_split_size_mb:512"
export LADA_MODEL_WEIGHTS_DIR="$SCRIPT_DIR/model_weights"

# Kiểm soát CPU threads & ngăn chặn OpenMP busy-wait spinloop
export OMP_NUM_THREADS=4
export OPENCV_FOR_THREADS_NUM=4
export OPENBLAS_NUM_THREADS=4
export MKL_NUM_THREADS=4
export OMP_WAIT_POLICY=PASSIVE

export PYTHONPATH="$SCRIPT_DIR:${PYTHONPATH:-}"
export PATH="/opt/rocm/bin:$HOME/.local/bin:$SCRIPT_DIR/.venv/bin:$PATH"
export LD_LIBRARY_PATH="/opt/rocm/lib:${LD_LIBRARY_PATH:-}"

if [ -x "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PY_CMD="$SCRIPT_DIR/.venv/bin/python3"
else
    PY_CMD="python3"
fi

exec "$PY_CMD" -m lada.cli.main "$@"
