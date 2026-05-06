#!/bin/bash

E_BADARGS=65
if [ $# -lt 1 ]; then
    echo "Usage: $(basename "$0") <input> [timeLimit]"
    exit $E_BADARGS
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
input=$1
shift

timeLimit="${VRP_TIME_LIMIT:-295}"
if [ $# -gt 0 ]; then
    timeLimit=$1
    shift
fi

"$SCRIPT_DIR/solver" "$input" --time-limit "$timeLimit" "$@"
