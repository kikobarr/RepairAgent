#!/usr/bin/env bash

function find_python_command() {
    if command -v python &> /dev/null
    then
        echo "python"
    elif command -v python3 &> /dev/null
    then
        echo "python3"
    else
        echo "Python not found. Please install Python."
        exit 1
    fi
}

PYTHON_CMD=$(find_python_command)

# Replication Modification: OpenAI API key
# Originally, the OpenAI API key is hardcoded in the repo by using set_api_key.py.
# Then `git update-index` was used on each of those files to prevent the API key from being published.
# As modified, the OpenAI API key is added only to the root in .env. The files access the API key using the python-dotenv tool.
export OPENAI_KEY="${OPENAI_API_KEY}"
if $PYTHON_CMD -c "import sys; sys.exit(sys.version_info < (3, 10))"; then
    $PYTHON_CMD scripts/check_requirements.py requirements.txt
    if [ $? -eq 1 ]
    then
        echo Installing missing packages...
        $PYTHON_CMD -m pip install -r requirements.txt
    fi
    $PYTHON_CMD -m autogpt "$@"
    # Replication Modification: Non-interactive terminal compatible
    # The original line is intended for interactive terminals to allow the user to read output before the terminal closes.
    # The Kubernetes terminal is a non-interactive terminal and returns an error at this line.
    # read -p "Press any key to continue..."
else
    echo "Python 3.10 or higher is required to run Auto GPT."
fi
