#!/bin/bash

########################################
############# CSCI 2951-O ##############
########################################
E_BADARGS=65
if [ $# -ne 3 ]; then
    echo "Usage: $(basename "$0") <inputFolder/> <timeLimit> <logFile>"
    echo "Description:"
    echo -e "\t Calls ./run.sh for every file in inputFolder/."
    echo -e "\t Each run is subject to the given time limit in seconds."
    echo -e "\t Last line of each run is appended to logFile."
    echo -e "\t Failed runs are recorded with -- for time and result."
    echo -e "\t Aborts if logFile already exists."
    exit $E_BADARGS
fi

inputFolder=$1
timeLimit=$2
logFile=$3

# Append trailing slash if missing
lastChar="${inputFolder: -1}"
if [ "$lastChar" != "/" ]; then
    inputFolder="$inputFolder/"
fi

[ -f "$logFile" ] && echo "Logfile $logFile already exists, terminating." && exit 1

touch "$logFile"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in "$inputFolder"*.*; do
    fullFileName=$(realpath "$f")
    echo "Running $fullFileName"
    timeout "$timeLimit" "$SCRIPT_DIR/run.sh" "$fullFileName" > output.tmp
    returnValue="$?"
    if [ "$returnValue" = 0 ]; then
        tail -1 output.tmp >> "$logFile"
    else
        echo "Error"
        instance=$(basename "$fullFileName")
        echo "{\"Instance\": \"$instance\", \"Time\": \"--\", \"Result\": \"--\"}" >> "$logFile"
    fi
    rm -f output.tmp
done
