#!/bin/bash
export PATH=$PATH:$(pwd)/defects4j/framework/bin
cpanm --local-lib=~/perl5 local::lib && eval $(perl -I ~/perl5/lib/perl5/ -Mlocal::lib)
for LANG in en_AU.UTF-8 en_GB.UTF-8 C.UTF-8 C; do
  if locale -a 2>/dev/null | grep -q "$LANG"; then
    export LANG
    break
  fi
done
export LC_COLLATE=C

python3 experimental_setups/increment_experiment.py
python3 construct_commands_descriptions.py

current_experiment=$(tail -n 1 experimental_setups/experiments_list.txt | tr -d '\r')
experiment_logs_dir="experimental_setups/${current_experiment}/logs"

input="$1"
experiment_file="$2"
model="${3:-gpt-4o-mini}"  # Use $3 if given, otherwise default to gpt-4o-mini

dos2unix "$input"  # Convert file to Unix line endings (if needed)

bug_times_file="${experiment_logs_dir}/bug_times.csv"
if [ ! -f "${bug_times_file}" ]; then
    echo "project,bug,start_iso,start_epoch,end_iso,end_epoch,status" > "${bug_times_file}"
fi

while IFS= read -r line || [ -n "$line" ]
do
    tuple=($line)
    project_name="${tuple[0]}"
    bug_index="${tuple[1]}"
    echo "${project_name}, ${bug_index}"
    python3 prepare_ai_settings.py "${project_name}" "${bug_index}"
    python3 checkout_py.py "${project_name}" "${bug_index}"

    start_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    start_epoch=$(date -u +%s)
    echo "[${start_timestamp}] Starting bug ${project_name} #${bug_index}"

    if ./run.sh --ai-settings ai_settings.yaml --model "$model" -c -l 40 -m json_file --experiment-file "$experiment_file"; then
        status="success"
    else
        status="failure"
    fi

    end_timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    end_epoch=$(date -u +%s)
    echo "[${end_timestamp}] Finished bug ${project_name} #${bug_index}"
    echo "${project_name},${bug_index},${start_timestamp},${start_epoch},${end_timestamp},${end_epoch},${status}" >> "${bug_times_file}"
done < "$input"
