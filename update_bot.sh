#!/usr/bin/env bash
# Run with: bash ~/icez-discord-bot/update_bot.sh
set -Eeuo pipefail

main() {
    local root python session=discordbot pane current command old_head launch pid i
    local -a panes
    root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
    cd -- "$root"
    python="$root/.venv/bin/python"
    for command in git tmux flock; do
        command -v "$command" >/dev/null || { echo "Missing command: $command" >&2; return 1; }
    done
    [[ -x "$python" && -f .env ]] || { echo 'Missing .venv/bin/python or .env; complete setup first.' >&2; return 1; }
    exec 9>"$(git rev-parse --git-path bot-update.lock)"
    flock -n 9 || { echo 'Another update is already running.' >&2; return 1; }
    if [[ -n "${TMUX:-}" ]]; then
        current="$(tmux display-message -p '#S')"
        [[ "$current" != "$session" ]] || {
            echo 'Open a separate Termux session and run this script outside discordbot.' >&2
            return 1
        }
    fi
    [[ "$(git branch --show-current)" == main ]] || { echo 'Expected branch main; no changes made.' >&2; return 1; }
    [[ -z "$(git status --porcelain)" ]] || { echo 'Local changes found. Commit or move them before updating.' >&2; return 1; }
    echo 'Checking origin/main...'
    git fetch origin main
    git merge-base --is-ancestor HEAD origin/main || { echo 'Local main has diverged or has unpushed commits; no restart performed.' >&2; return 1; }
    old_head="$(git rev-parse HEAD)"
    pane=''
    if tmux has-session -t "=$session" 2>/dev/null; then
        mapfile -t panes < <(tmux list-panes -s -t "=$session" -F '#{pane_id}')
        [[ "${#panes[@]}" == 1 ]] || { echo 'discordbot must contain exactly one pane; no restart performed.' >&2; return 1; }
        pane="${panes[0]}"
        current="$(tmux display-message -p -t "$pane" '#{pane_current_path}')"
        [[ "$current" == "$root" ]] || { echo 'discordbot points to another directory; no restart performed.' >&2; return 1; }
        command="$(tmux display-message -p -t "$pane" '#{pane_current_command}')"
        case "$command" in
            python|python3|python3.*)
                echo 'Stopping Bot with Ctrl+C...'
                tmux send-keys -t "$pane" C-c
                for ((i=0; i<30; i++)); do
                    if ! tmux has-session -t "=$session" 2>/dev/null; then pane=''; break; fi
                    command="$(tmux display-message -p -t "$pane" '#{pane_current_command}')"
                    case "$command" in bash|zsh|fish|sh) break ;; esac
                    sleep 1
                done
                if [[ -n "$pane" ]]; then
                    case "$command" in bash|zsh|fish|sh) ;; *) echo 'Bot did not stop within 30 seconds; update cancelled.' >&2; return 1 ;; esac
                fi
                ;;
            bash|zsh|fish|sh) ;;
            *) echo "Unexpected process in discordbot: $command; no restart performed." >&2; return 1 ;;
        esac
    fi
    # Do not start a second instance if a Bot was launched outside tmux.
    for pid in /proc/[0-9]*; do
        [[ -r "$pid/cmdline" ]] || continue
        [[ "$(readlink "$pid/cwd" 2>/dev/null || true)" == "$root" ]] || continue
        if tr '\0' '\n' < "$pid/cmdline" 2>/dev/null | grep -Fxq -e bot.py -e "$root/bot.py"; then
            echo 'A project Bot is still running outside the managed pane; stop it first.' >&2
            return 1
        fi
    done
    trap 'echo "Update failed. Bot may be stopped; fix the error and rerun this script. No database migration was performed." >&2' ERR
    echo 'Updating code and dependencies...'
    git pull --ff-only origin main
    "$python" -m pip install -r requirements.txt
    "$python" bot.py --check
    "$python" -m database check
    if command -v termux-wake-lock >/dev/null; then termux-wake-lock; fi
    printf -v launch 'exec %q -u bot.py' "$python"
    # Close the update lock descriptor in the new Bot process.
    launch+=" 9>&-"
    if [[ -n "$pane" ]] && tmux has-session -t "=$session" 2>/dev/null; then
        tmux respawn-pane -k -t "$pane" -c "$root" "$launch" 9>&-
    else
        tmux new-session -d -s "$session" -c "$root" "$launch" 9>&-
    fi
    sleep 2
    tmux has-session -t "=$session" || { echo 'Bot exited during startup. Run .venv/bin/python bot.py to inspect the error.' >&2; return 1; }
    echo "Updated: $old_head -> $(git rev-parse --short HEAD)"
    echo 'Bot process started. Check Discord login with: tmux attach -t discordbot'
}

main "$@"
