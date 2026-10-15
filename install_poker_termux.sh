#!/usr/bin/env bash
# First-time native Termux installation. Run outside the poker service session.
set -Eeuo pipefail

main() {
    local root poker_python command version
    root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
    cd -- "$root"
    for command in pkg python npm uname; do
        command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; return 1; }
    done
    [[ -n "${PREFIX:-}" ]] || { echo 'Run this installer inside Termux.' >&2; return 1; }
    [[ "$(uname -m)" == aarch64 ]] || { echo 'This installer requires ARM64 (aarch64).' >&2; return 1; }
    version="$(python -c 'import sys; print("%s.%s" % sys.version_info[:2])')"
    [[ "$version" == 3.14 ]] || { echo "This installer requires Python 3.14; found $version." >&2; return 1; }

    trap 'echo "Poker installation failed. Resolve the error before initializing or starting the website." >&2' ERR
    echo 'Installing native Termux libraries and the C compiler...'
    pkg update
    pkg install -y python-pip python-numpy python-cryptography clang make pkg-config libffi
    version="$(python -c 'import sys; print("%s.%s" % sys.version_info[:2])')"
    [[ "$version" == 3.14 ]] || { echo 'Termux Python changed; this installer requires Python 3.14.' >&2; return 1; }

    poker_python="$root/poker/.venv/bin/python"
    if [[ -e "$root/poker/.venv" ]]; then
        [[ -x "$poker_python" ]] && grep -qx 'include-system-site-packages = true' "$root/poker/.venv/pyvenv.cfg" || {
            echo 'Existing poker/.venv must be a Termux venv with system-site-packages enabled.' >&2
            return 1
        }
    else
        python -m venv --system-site-packages "$root/poker/.venv"
    fi
    version="$("$poker_python" -c 'import sys; print("%s.%s" % sys.version_info[:2])')"
    [[ "$version" == 3.14 ]] || { echo 'Existing poker/.venv uses another Python version.' >&2; return 1; }

    echo 'Checking the native packages provided by Termux...'
    "$poker_python" -I -c 'import numpy, cryptography, cffi; from cryptography.hazmat.primitives.ciphers import Cipher; assert numpy.dot([1, 2], [3, 4]) == 11; print("Termux native packages: numpy=" + numpy.__version__ + " cryptography=" + cryptography.__version__ + " cffi=" + cffi.__version__)'

    echo 'Installing poker dependencies in poker/.venv...'
    "$poker_python" -m pip install -r "$root/poker/requirements-build.txt"
    # Regenerate eval7's bundled C code for 3.14 instead of using an old wheel.
    # Explicit libpython linkage is needed for native extensions on Android.
    LDFLAGS="${LDFLAGS:-} -L$PREFIX/lib -lpython3.14" \
        "$poker_python" -m pip install --no-build-isolation --no-deps --no-binary=eval7 eval7==0.1.10
    "$poker_python" -m pip install --only-binary=:all: -r "$root/poker/requirements-termux.txt"
    "$poker_python" -m pip check

    echo 'Checking native imports and the actual fixed NPC subprocess...'
    "$poker_python" -I -c 'import numpy, eval7, pydantic_core; from cryptography.hazmat.primitives.ciphers import Cipher; print("Native dependencies ready")'
    "$poker_python" - <<'PY'
import asyncio
from poker.npc import NPC
from poker.operations import require_sqlite
from types import SimpleNamespace

async def main():
    require_sqlite(SimpleNamespace(environment="production"))
    npc = NPC()
    try:
        await npc.start()
        print("Fixed NPC ready")
    finally:
        await npc.close()

asyncio.run(main())
PY

    echo 'Building the website...'
    npm --prefix "$root/poker_web" ci
    npm --prefix "$root/poker_web" run build
    echo 'Poker dependencies and website build ready.'
    echo 'Next: configure .env and follow poker/TERMUX.md to initialize and start the website.'
}

main "$@"
