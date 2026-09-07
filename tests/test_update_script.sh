#!/usr/bin/env bash
# Offline behavior tests; no real git, tmux, database or Bot is invoked.
set -euo pipefail
source_script="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/update_bot.sh"
fixture="$(mktemp -d)"
trap 'rm -rf -- "$fixture"' EXIT
cp "$source_script" "$fixture/update_bot.sh"
mkdir -p "$fixture/.git" "$fixture/.venv/bin"
touch "$fixture/.env"
printf '#!/usr/bin/env bash\necho "python $*" >> "$CALL_LOG"\n' > "$fixture/.venv/bin/python"
chmod +x "$fixture/.venv/bin/python"
export CALL_LOG="$fixture/calls" FIXTURE="$fixture"
git() {
    echo "git $*" >> "$CALL_LOG"
    case "$1" in
        rev-parse) if [[ "$2" == --git-path ]]; then echo "$FIXTURE/.git/bot-update.lock"; else echo abc123; fi ;;
        branch) echo main ;;
        status) [[ "$SCENARIO" != dirty ]] || echo ' M bot.py' ;;
        merge-base) [[ "$SCENARIO" != diverged ]] ;;
        pull) [[ "$SCENARIO" != pull_fail ]] ;;
    esac
}
tmux() {
    echo "tmux $*" >> "$CALL_LOG"
    case "$1" in
        has-session) [[ -f "$FIXTURE/running" ]] ;;
        new-session|respawn-pane) touch "$FIXTURE/running" ;;
        list-panes) echo '%1' ;;
        display-message)
            case "${*: -1}" in
                '#{pane_current_path}') echo "$FIXTURE" ;;
                '#{pane_current_command}')
                    if [[ -f "$FIXTURE/stopped" ]]; then echo bash; else echo python; fi ;;
            esac ;;
        send-keys) [[ "$SCENARIO" == stop_timeout ]] || touch "$FIXTURE/stopped" ;;
    esac
}
flock() { return 0; }
sleep() { return 0; }
readlink() { return 1; }
export -f git tmux flock sleep readlink
for SCENARIO in success existing stop_timeout dirty diverged pull_fail; do
    export SCENARIO
    rm -f "$FIXTURE/running" "$FIXTURE/stopped"
    if [[ "$SCENARIO" == existing || "$SCENARIO" == stop_timeout ]]; then touch "$FIXTURE/running"; fi
    : > "$CALL_LOG"
    if env -u TMUX bash "$FIXTURE/update_bot.sh" > "$fixture/output" 2>&1; then code=0; else code=$?; fi
    if [[ "$SCENARIO" == success || "$SCENARIO" == existing ]]; then
        [[ "$code" == 0 ]]
        grep -q 'git pull --ff-only origin main' "$CALL_LOG"
        grep -q 'python -m database check' "$CALL_LOG"
        if [[ "$SCENARIO" == existing ]]; then
            grep -q 'tmux send-keys -t %1 C-c' "$CALL_LOG"
            grep -q 'tmux respawn-pane' "$CALL_LOG"
        else
            grep -q 'tmux new-session' "$CALL_LOG"
        fi
    else
        [[ "$code" != 0 ]]
        ! grep -Eq 'tmux (new-session|respawn-pane)' "$CALL_LOG"
        ! grep -q 'python ' "$CALL_LOG"
    fi
    echo "PASS $SCENARIO"
done
