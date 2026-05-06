#!/bin/bash

E_BADARGS=65
if [ $# -ne 3 ]; then
    echo "Usage: $(basename "$0") <inputFolder/> <timeLimit> <logFile>"
    echo "Description:"
    echo -e "\tCalls ./run.sh for every file in inputFolder/."
    echo -e "\tEach run is subject to the given time limit in seconds."
    echo -e "\tLast line of each run is appended to logFile."
    echo -e "\tFailed runs are recorded with -- for time and result."
    echo -e "\tAborts if logFile already exists."
    exit $E_BADARGS
fi

inputFolder=$1
timeLimit=$2
logFile=$3
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

lastChar="${inputFolder: -1}"
if [ "$lastChar" != "/" ]; then
    inputFolder="$inputFolder/"
fi

if [ -f "$logFile" ]; then
    echo "Logfile $logFile already exists, terminating."
    exit 1
fi

touch "$logFile"

internalTimeLimit=$timeLimit
if [[ "$timeLimit" =~ ^[0-9]+$ ]] && [ "$timeLimit" -gt 2 ]; then
    internalTimeLimit=$((timeLimit - 2))
fi

for f in "$inputFolder"*.*; do
    [ -e "$f" ] || continue
    fullFileName=$(realpath "$f")
    outputFile=$(mktemp "${TMPDIR:-/tmp}/p5run.XXXXXX")
    echo "Running $fullFileName"

    timeout "$timeLimit" "$SCRIPT_DIR/run.sh" "$fullFileName" "$internalTimeLimit" > "$outputFile"
    returnValue="$?"
    if [ "$returnValue" = 0 ]; then
        tail -1 "$outputFile" >> "$logFile"
    else
        echo "Error"
        instance=$(basename "$fullFileName")
        echo "{\"Instance\": \"$instance\", \"Time\": \"--\", \"Result\": \"--\", \"Solution\": \"--\"}" >> "$logFile"
    fi
    rm -f "$outputFile"
done
