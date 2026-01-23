# roura-agent

Local-first AI coding agent CLI powered by Ollama.

## Setup
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

## Configure Ollama
export OLLAMA_BASE_URL="http://10.1.50.3:11434"
export OLLAMA_MODEL="qwen2.5-coder:32b-32k"

## Run
cd /path/to/repo
roura-agent chat
