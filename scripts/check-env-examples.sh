#!/usr/bin/env bash
#
# check-env-examples.sh
# Fails if any .env.example in the repo looks like it contains a real secret.
# Run manually (make check-secrets) or via the pre-commit hook.
#
set -u

repo_root="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$repo_root" ]; then
    echo "ERROR: not inside a git worktree." >&2
    exit 1
fi
cd "$repo_root" || exit 1

fail=0

examples="$(find . -name '.env.example' -not -path './.git/*' -not -path './.venv/*' 2>/dev/null)"

if [ -z "$examples" ]; then
    echo "check-env-examples: no .env.example files found."
    exit 0
fi

# 1. .env.example must be git-trackable (not excluded by .gitignore).
for f in $examples; do
    if git check-ignore -q "$f"; then
        echo "ERROR: $f is ignored by .gitignore — .env.example must be committed (un-ignore it with '!.env.example')." >&2
        fail=1
    fi
done

# 2. Hard blocklist: known real-secret patterns.
blocklist='xleuthXX|BEGIN [A-Z ]*PRIVATE KEY|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|sk-(live|test)-[A-Za-z0-9_-]{16,}|xox[baprs]-[0-9A-Za-z-]{10,}|AIza[0-9A-Za-z_-]{30,}'
if grep -rInE "$blocklist" --include='.env.example' . --exclude-dir=.git --exclude-dir=.venv; then
    echo "ERROR: real secret pattern found in .env.example file(s) above." >&2
    fail=1
fi

# 3. Heuristics on secret-ish keys: flag values that are not obvious placeholders.
while IFS= read -r f; do
    while IFS= read -r line; do
        case "$line" in
            \#*|'') continue ;;
        esac
        key="${line%%=*}"
        val="${line#*=}"
        val="${val%\"}"; val="${val#\"}"
        case "$val" in
            *changeme*|*example*|*your-*|''|'<replace-me>') continue ;;
        esac
        case "$key" in
            *PASSWORD*|*PASS*|*SECRET*|*TOKEN*|*API_KEY*|*PRIVATE_KEY*)
                if [[ ${#val} -ge 12 ]] && [[ "$val" =~ [A-Z] ]] && [[ "$val" =~ [a-z] ]] && [[ "$val" =~ [0-9] ]]; then
                    echo "ERROR: $f : $key looks like a high-entropy real secret (use a changeme_* placeholder)." >&2
                    fail=1
                elif [[ "$val" =~ ^[0-9a-fA-F]{16,}$ ]]; then
                    echo "ERROR: $f : $key looks like a raw hex/random secret (use a changeme_* placeholder)." >&2
                    fail=1
                fi
                ;;
            *DATABASE_URL*|*REDIS_URL*|*AMQP_URL*|*BROKER_URL*)
                if [[ "$val" =~ ^[a-zA-Z][a-zA-Z0-9+.-]*://([^:/@]+):([^@]+)@ ]]; then
                    user="${BASH_REMATCH[1]}"
                    pass="${BASH_REMATCH[2]}"
                    if [[ "$pass" != *changeme* && "$pass" != *example* && "$pass" != *your-* ]]; then
                        echo "ERROR: $f : $key embeds non-placeholder credentials (user '$user')." >&2
                        fail=1
                    fi
                fi
                ;;
        esac
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$f")
done <<< "$examples"

if [ "$fail" -ne 0 ]; then
    echo "check-env-examples: FAILED — fix the .env.example file(s) above before committing." >&2
    exit 1
fi

echo "check-env-examples: OK — all .env.example files contain only placeholders."
