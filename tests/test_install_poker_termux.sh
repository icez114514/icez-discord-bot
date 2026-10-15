#!/usr/bin/env bash
# Offline installer contracts: no pkg/pip/npm command or real NPC is executed.
set -euo pipefail

source_script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/install_poker_termux.sh"
temp_root="$(cd "${TMPDIR:-/tmp}" && pwd -P)"
fixture="$(mktemp -d "$temp_root/poker-install-test.XXXXXX")"
cleanup() {
    case "$fixture" in "$temp_root"/poker-install-test.*) rm -rf -- "$fixture" ;; esac
}
trap cleanup EXIT
cp "$source_script" "$fixture/install_poker_termux.sh"
mkdir -p "$fixture/poker"
export FIXTURE="$fixture" CALL_LOG="$fixture/calls" PREFIX=/fake/termux

cat > "$fixture/fake-python" <<'PYTHON'
#!/usr/bin/env bash
set -eu
echo "poker-python $*" >> "$CALL_LOG"
if [[ "${1:-}" == -c && "$2" == *sys.version_info* ]]; then
    echo 3.14
elif [[ "${1:-}" == -m && "${2:-}" == pip ]]; then
    if [[ "$SCENARIO" == pip_fail && "$*" == *requirements-termux.txt* ]]; then exit 1; fi
elif [[ "${1:-}" == - ]]; then
    cat >/dev/null
    [[ "$SCENARIO" != npc_fail ]]
fi
PYTHON
chmod +x "$fixture/fake-python"

python() {
    echo "system-python $*" >> "$CALL_LOG"
    if [[ "$1" == -c ]]; then
        if [[ "$SCENARIO" == wrong_python ]]; then echo 3.13; else echo 3.14; fi
    elif [[ "$1" == -m && "$2" == venv ]]; then
        mkdir -p "$FIXTURE/poker/.venv/bin"
        cp "$FIXTURE/fake-python" "$FIXTURE/poker/.venv/bin/python"
        printf 'include-system-site-packages = true\n' > "$FIXTURE/poker/.venv/pyvenv.cfg"
    fi
}
uname() { if [[ "$SCENARIO" == wrong_arch ]]; then echo x86_64; else echo aarch64; fi; }
pkg() { echo "pkg $*" >> "$CALL_LOG"; }
npm() { echo "npm $*" >> "$CALL_LOG"; }
export -f python uname pkg npm

for SCENARIO in success existing wrong_python wrong_arch private_venv pip_fail npc_fail; do
    export SCENARIO
    : > "$CALL_LOG"
    if [[ "$SCENARIO" == private_venv ]]; then
        printf 'include-system-site-packages = false\n' > "$fixture/poker/.venv/pyvenv.cfg"
    elif [[ -f "$fixture/poker/.venv/pyvenv.cfg" ]]; then
        printf 'include-system-site-packages = true\n' > "$fixture/poker/.venv/pyvenv.cfg"
    fi
    if bash "$fixture/install_poker_termux.sh" > "$fixture/output" 2>&1; then code=0; else code=$?; fi
    case "$SCENARIO" in
        success|existing)
            [[ "$code" == 0 ]]
            grep -q 'pkg install .*python-numpy python-cryptography' "$CALL_LOG"
            grep -q 'pip install --no-build-isolation --no-deps --no-binary=eval7 eval7==0.1.10' "$CALL_LOG"
            grep -q 'pip install --only-binary=numpy,cryptography,pydantic-core -r' "$CALL_LOG"
            grep -q 'poker-python -I -c' "$CALL_LOG"
            grep -q 'poker-python -$' "$CALL_LOG"
            grep -q 'npm .* run build' "$CALL_LOG"
            if [[ "$SCENARIO" == existing ]]; then ! grep -q 'system-python -m venv' "$CALL_LOG"; fi
            ;;
        *)
            [[ "$code" != 0 ]]
            ! grep -q '^npm ' "$CALL_LOG"
            if [[ "$SCENARIO" == wrong_* ]]; then ! grep -q '^pkg ' "$CALL_LOG"; fi
            ;;
    esac
    ! grep -Eq 'database (init|migrate)|poker (migrate|serve)|bot.py' "$CALL_LOG"
    echo "PASS $SCENARIO"
done
