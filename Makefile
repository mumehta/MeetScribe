# Meeting Transcriber API Makefile
# Comprehensive automation and individual API call targets

# Configuration
API_BASE_URL := http://localhost:8000
OLLAMA_BASE_URL := http://localhost:11434
UPLOADS_DIR := uploads
OUTPUT_DIR := finaloutput
BACKEND_DIR := backend
VENV_PYTHON := $(BACKEND_DIR)/venv/bin/python
HELPER_SCRIPT := $(BACKEND_DIR)/bin/helper.py

# Set Python path to include backend directory
PYTHONPATH := $(shell pwd)/$(BACKEND_DIR):$(PYTHONPATH)
export PYTHONPATH

# Colors for output
RED := \033[0;31m

# Virtual Environment Management
.PHONY: venv-activate
venv-activate:
	@if [ -f "$(BACKEND_DIR)/venv/bin/activate" ]; then \
		echo "$(GREEN)✅ Virtual environment found$(NC)"; \
		echo "$(YELLOW)📦 Checking/updating requirements...$(NC)"; \
		. $(BACKEND_DIR)/venv/bin/activate && \
		pip install --upgrade pip && \
		pip install -r $(BACKEND_DIR)/requirements.txt || { echo "$(RED)❌ Failed to update requirements$(NC)"; exit 1; }; \
		echo "$(GREEN)✅ Requirements up to date$(NC)"; \
	else \
		echo "$(YELLOW)🚀 Creating virtual environment...$(NC)"; \
		python3 -m venv $(BACKEND_DIR)/venv || { echo "$(RED)❌ Failed to create virtual environment$(NC)"; exit 1; }; \
		echo "$(GREEN)✅ Virtual environment created$(NC)"; \
		echo "$(YELLOW)📦 Installing requirements...$(NC)"; \
		. $(BACKEND_DIR)/venv/bin/activate && \
		pip install --upgrade pip && \
		pip install -r $(BACKEND_DIR)/requirements.txt || { echo "$(RED)❌ Failed to install requirements$(NC)"; exit 1; }; \
		echo "$(GREEN)✅ Requirements installed$(NC)"; \
	fi
	@echo "$(GREEN)✅ Virtual environment is ready$(NC)"; \
	echo "Run this command in your shell to activate it:"; \
	echo "$(YELLOW)source $(BACKEND_DIR)/venv/bin/activate$(NC)"

.PHONY: venv-deactivate
venv-deactivate:
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		echo "$(YELLOW)🛑 Deactivating virtual environment...$(NC)"; \
		deactivate; \
		echo "$(GREEN)✅ Virtual environment deactivated$(NC)"; \
	else \
		echo "$(YELLOW)No active virtual environment to deactivate$(NC)"; \
	fi

GREEN := \033[0;32m
YELLOW := \033[1;33m
BLUE := \033[0;34m
PURPLE := \033[0;35m
CYAN := \033[0;36m
WHITE := \033[1;37m
NC := \033[0m

# Default target
.DEFAULT_GOAL := help

# Help target
.PHONY: help
help:
	@echo "$(PURPLE)$(WHITE)"
	@echo "╔══════════════════════════════════════════════════════════════╗"
	@echo "║                  🎙️  MEETING TRANSCRIBER 🎙️                 ║"
	@echo "║                      Makefile Targets                        ║"
	@echo "╚══════════════════════════════════════════════════════════════╝"
	@echo "$(NC)"
	@echo "$(CYAN)🚀 Main Targets:$(NC)"
	@echo "  $(GREEN)start-servers$(NC)     - Start both servers (Ollama + Uvicorn)"
	@echo "  $(GREEN)stop-servers$(NC)      - Stop both servers"
	@echo ""
	@echo "$(CYAN)🐍 Virtual Environment:$(NC)"
	@echo "  $(GREEN)venv-activate$(NC)    - Create and activate virtual environment"
	@echo "  $(GREEN)venv-deactivate$(NC)  - Deactivate the current virtual environment"
	@echo ""
	@echo "$(CYAN)📤 Upload & Processing:$(NC)"
	@echo "  $(GREEN)upload FILE=<path>$(NC) - Upload audio file and get task ID"
	@echo "  $(GREEN)status TASK=<id>$(NC)   - Check processing status"
	@echo ""
	@echo "$(CYAN)🎯 Transcription:$(NC)"
	@echo "  $(GREEN)transcribe TASK=<id>$(NC) - Start transcription and wait for completion"
	@echo "  $(GREEN)trans-status TASK=<id>$(NC) - Check transcription status"
	@echo ""
	@echo "$(CYAN)📝 Meeting Notes:$(NC)"
	@echo "  $(GREEN)notes TASK=<id>$(NC)     - Generate meeting notes"
	@echo "  $(GREEN)notes-ollama TASK=<id> MODEL=<name>$(NC) - Generate notes with custom Ollama model"
	@echo ""
	@echo "$(CYAN)🔧 Helper Script:$(NC)"
	@echo "  $(GREEN)helper <cmd>$(NC)     - Run helper script directly (e.g., 'make helper upload file.wav')"
	@echo ""
	@echo "$(CYAN)🧹 Cleanup:$(NC)"
	@echo "  $(GREEN)clean TASK=<id>$(NC)     - Clean up intermediate files"
	@echo ""
	@echo "$(YELLOW)Note: Set HUGGINGFACE_TOKEN environment variable for diarization support$(NC)"
	@echo "  $(GREEN)clean-all$(NC)        - Clean all temporary files"
	@echo ""
	@echo "$(CYAN)🔄 Complete Workflows:$(NC)"
	@echo "  $(GREEN)process FILE=<path>$(NC) - Complete workflow: upload → transcribe → notes"
	@echo ""
	@echo "$(CYAN)🛠️  Utilities:$(NC)"
	@echo "  $(GREEN)check-servers$(NC)     - Check server status"
	@echo "  $(GREEN)install$(NC)          - Install dependencies"
	@echo "  $(GREEN)logs$(NC)             - Show recent logs"
	@echo ""
	@echo "$(CYAN)🚀 Server Management:$(NC)"
	@echo "  $(GREEN)start-uvicorn$(NC)     - Start the Uvicorn server"
	@echo "  $(GREEN)stop-uvicorn$(NC)      - Stop the Uvicorn server"
	@echo "  $(GREEN)start-ollama$(NC)      - Start the Ollama server"
	@echo "  $(GREEN)stop-ollama$(NC)       - Stop the Ollama server"

# Start both servers
.PHONY: start-servers
start-servers: start-ollama start-uvicorn
	@echo "$(GREEN)✅ All servers started$(NC)"

# Stop both servers
.PHONY: stop-servers
stop-servers: stop-ollama stop-uvicorn
	@echo "$(GREEN)✅ All servers stopped$(NC)"

.PHONY: start-ollama
start-ollama:
	@echo "$(BLUE)🔍 Checking Ollama server...$(NC)"
	@if curl -s --max-time 5 $(OLLAMA_BASE_URL)/api/tags > /dev/null 2>&1; then \
		echo "$(GREEN)✅ Ollama server already running$(NC)"; \
	else \
		echo "$(YELLOW)🚀 Starting Ollama server...$(NC)"; \
		nohup ollama serve > logs/ollama.log 2>&1 & \
		echo "⏳ Waiting for Ollama server to start..."; \
		for i in $$(seq 1 30); do \
			if curl -s --max-time 5 $(OLLAMA_BASE_URL)/api/tags > /dev/null 2>&1; then \
				echo "$(GREEN)✅ Ollama server started$(NC)"; \
				break; \
			fi; \
			sleep 1; \
		done; \
	fi

.PHONY: stop-ollama
stop-ollama:
	@echo "$(YELLOW)🛑 Stopping Ollama server...$(NC)"
	@pkill -f "ollama serve" || true
	@echo "$(GREEN)✅ Ollama server stopped$(NC)"

.PHONY: start-uvicorn
start-uvicorn:
	@echo "$(BLUE)🔍 Checking uvicorn server...$(NC)"
	@if curl -s --max-time 5 $(API_BASE_URL)/health > /dev/null 2>&1; then \
		echo "$(GREEN)✅ Uvicorn server already running$(NC)"; \
	else \
		echo "$(YELLOW)🚀 Starting uvicorn server...$(NC)"; \
		cd $(BACKEND_DIR) && \
		if [ -f "venv/bin/activate" ]; then \
			. venv/bin/activate && \
			nohup python start_server.py > ../logs/uvicorn.log 2>&1 & \
			echo "⏳ Waiting for uvicorn server to start..."; \
			for i in $$(seq 1 30); do \
				if curl -s --max-time 5 $(API_BASE_URL)/health > /dev/null 2>&1; then \
					echo "$(GREEN)✅ Uvicorn server started$(NC)"; \
					echo "$(GREEN)🌐 Server URL: $(API_BASE_URL)$(NC)"; \
					echo "$(CYAN)📚 API Docs:    $(API_BASE_URL)/docs$(NC)"; \
					echo "$(YELLOW)💡 Use 'make stop-uvicorn' to stop the server$(NC)"; \
					exit 0; \
				fi; \
				sleep 1; \
			done; \
			echo "$(RED)❌ Failed to start Uvicorn server$(NC)"; \
			echo "Check $(BACKEND_DIR)/logs/uvicorn.log for details"; \
			exit 1; \
		else \
			echo "$(RED)❌ Virtual environment not found in $(BACKEND_DIR)/venv$(NC)"; \
			echo "Run 'make venv-activate' to create and activate the virtual environment"; \
			exit 1; \
		fi; \
	fi

# Upload audio file
.PHONY: stop-uvicorn
stop-uvicorn:
	@echo "$(YELLOW)🛑 Stopping Uvicorn server...$(NC)"
	@pkill -f "python.*start_server.py" || true
	@echo "$(GREEN)✅ Uvicorn server stopped$(NC)"

# make upload FILE=recording.m4a
# or make upload FILE=uploads/recording.m4a
.PHONY: upload
upload:
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: Please specify a file with FILE=path/to/file$(NC)"; \
		exit 1; \
	fi
	@echo "$(CYAN)Uploading $(FILE) using Python helper...$(NC)"
	@$(VENV_PYTHON) $(HELPER_SCRIPT) upload "$(FILE)" --api-base-url "$(API_BASE_URL)" | jq -r '.task_id' | tee .last_task_id
	@echo "$(GREEN)✓ Upload started. Task ID saved to .last_task_id$(NC)"

# Check processing status
.PHONY: status
status:
	@TASK_ID=""; \
	if [ -n "$(TASK)" ]; then \
		TASK_ID="$(TASK)"; \
		echo "$$TASK_ID" > .last_task_id; \
		echo "$(CYAN)Using provided Task ID: $$TASK_ID$(NC)"; \
	elif [ -f .last_task_id ]; then \
		TASK_ID=$$(cat .last_task_id); \
		echo "$(CYAN)Using saved Task ID: $$TASK_ID$(NC)"; \
	else \
		echo "$(RED)Error: No task ID provided and .last_task_id not found$(NC)"; \
		exit 1; \
	fi; \
	echo "$(BLUE)🔍 Checking processing status for: $$TASK_ID$(NC)"; \
	RESPONSE=$$(curl -s "$(API_BASE_URL)/api/v1/audio-processing/$$TASK_ID"); \
	STATUS=$$(echo "$$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error"); \
	echo "$(CYAN)📊 Status: $$STATUS$(NC)"; \
	if [ "$$STATUS" = "completed" ]; then \
		echo "$(GREEN)✅ Processing completed$(NC)"; \
	elif [ "$$STATUS" = "error" ]; then \
		ERROR=$$(echo "$$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null || echo "Unknown error"); \
		echo "$(RED)❌ Processing failed: $$ERROR$(NC)"; \
		exit 1; \
	else \
		echo "$(YELLOW)⏳ Processing in progress...$(NC)"; \
	fi

# Wait for processing completion
.PHONY: wait-processing
wait-processing:
	@TASK_ID=""; \
	if [ -n "$(TASK)" ]; then \
		TASK_ID="$(TASK)"; \
		echo "$$TASK_ID" > .last_task_id; \
		echo "$(CYAN)Using provided Task ID: $$TASK_ID$(NC)"; \
	elif [ -f .last_task_id ]; then \
		TASK_ID=$$(cat .last_task_id); \
		echo "$(CYAN)Using saved Task ID: $$TASK_ID$(NC)"; \
	else \
		echo "$(RED)Error: No task ID provided and .last_task_id not found$(NC)"; \
		exit 1; \
	fi; \
	echo "$(YELLOW)⏳ Waiting for processing to complete...$(NC)"; \
	for i in $$(seq 1 60); do \
		RESPONSE=$$(curl -s "$(API_BASE_URL)/api/v1/audio-processing/$$TASK_ID"); \
		STATUS=$$(echo "$$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null || echo "error"); \
		if [ "$$STATUS" = "completed" ]; then \
			echo "$(GREEN)✅ Processing completed$(NC)"; \
			break; \
		elif [ "$$STATUS" = "error" ]; then \
			ERROR=$$(echo "$$RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('error', 'Unknown error'))" 2>/dev/null || echo "Unknown error"); \
			echo "$(RED)❌ Processing failed: $$ERROR$(NC)"; \
			echo "$$RESPONSE" | jq .; \
			exit 1; \
		fi; \
		if [ $$((i % 10)) -eq 0 ]; then \
			echo "$(YELLOW)⏳ Still processing... ($$i/60 checks)$(NC)"; \
		fi; \
		sleep 5; \
	done; \
	if [ "$$STATUS" != "completed" ]; then \
		echo "$(RED)❌ Processing timeout after 5 minutes$(NC)"; \
		echo "$$RESPONSE" | jq .; \
		exit 1; \
	fi

# Start transcription
# make transcribe
# or make transcribe TASK=8e577582-d3bd-42ca-938e-ef488d8adec4
.PHONY: transcribe
transcribe:
	@TASK_ID=""; \
	if [ -n "$(TASK)" ]; then \
		TASK_ID="$(TASK)"; \
		echo "$$TASK_ID" > .last_task_id; \
		echo "$(CYAN)Using provided Task ID: $$TASK_ID$(NC)"; \
	elif [ -f .last_task_id ]; then \
		TASK_ID=$$(cat .last_task_id); \
		echo "$(CYAN)Using saved Task ID: $$TASK_ID$(NC)"; \
	else \
		echo "Enter processing task_id:"; \
		read -p "Task ID: " TASK_ID; \
		if [ -z "$$TASK_ID" ]; then \
			echo "$(RED)❌ Task ID cannot be empty$(NC)"; \
			exit 1; \
		fi; \
		echo "$$TASK_ID" > .last_task_id; \
	fi; \
	{ \
		echo "$(BLUE)🎯 Starting transcription for: $$TASK_ID$(NC)"; \
		echo "$(YELLOW)⏳ Transcription in progress...$(NC)"; \
		TIMESTAMP=$$(date +%Y%m%d_%H%M%S); \
		OUTPUT_FILE="backend/intermediate/transcription_$${TIMESTAMP}.json"; \
		mkdir -p backend/intermediate; \
		set -e; \
		if ! $(VENV_PYTHON) $(HELPER_SCRIPT) transcribe "$$TASK_ID" \
			--api-base-url "$(API_BASE_URL)" \
			$(if $(HUGGINGFACE_TOKEN),--hf-token "$(HUGGINGFACE_TOKEN)") \
			$(if $(WHISPER_MODEL),--whisper-model "$(WHISPER_MODEL)") \
			$(if $(COMPUTE_TYPE),--compute-type "$(COMPUTE_TYPE)") > "$$OUTPUT_FILE.raw" 2>&1; then \
			echo "$(RED)❌ Transcription failed. Raw log: $$OUTPUT_FILE.raw$(NC)"; \
			exit 1; \
		fi; \
		if jq . "$$OUTPUT_FILE.raw" >/dev/null 2>&1; then \
			jq . "$$OUTPUT_FILE.raw" > "$$OUTPUT_FILE"; \
			rm -f "$$OUTPUT_FILE.raw"; \
			ln -sf "$$OUTPUT_FILE" backend/intermediate/transcription_latest.json; \
			TRANSCRIPTION_ID=$$(jq -r '.task_id // .transcription_task_id // .id // empty' "$$OUTPUT_FILE"); \
			if [ -z "$$TRANSCRIPTION_ID" ]; then \
				TRANSCRIPTION_ID="$${OUTPUT_FILE%.*}"; \
			fi; \
			echo "$$TRANSCRIPTION_ID" > .last_transcription_id; \
			echo "$(CYAN)📊 Status: completed$(NC)"; \
			echo "$(GREEN)✓ Generated transcription id: $$TRANSCRIPTION_ID and stored in .last_transcription_id$(NC)"; \
		else \
			mv "$$OUTPUT_FILE.raw" "backend/intermediate/transcription_$${TIMESTAMP}.txt"; \
			echo "$(RED)❌ Invalid JSON. Raw saved: backend/intermediate/transcription_$${TIMESTAMP}.txt$(NC)"; \
			exit 1; \
		fi; \
	}

# Generate meeting notes
.PHONY: notes
notes:
	@TRANSCRIPTION_ID=""; \
	if [ -n "$(TASK)" ]; then \
		TRANSCRIPTION_ID="$(TASK)"; \
		echo "$$TRANSCRIPTION_ID" > .last_transcription_id; \
		echo "$(CYAN)Using provided Transcription ID: $$TRANSCRIPTION_ID$(NC)"; \
	elif [ -f .last_transcription_id ]; then \
		TRANSCRIPTION_ID=$$(cat .last_transcription_id); \
		echo "$(CYAN)Using saved Transcription ID: $$TRANSCRIPTION_ID$(NC)"; \
	else \
		echo "$(RED)Error: No transcription ID provided and .last_transcription_id not found$(NC)"; \
		exit 1; \
	fi; \
	echo "$(YELLOW)Generating meeting notes...$(NC)"; \
	set -e; \
	$(VENV_PYTHON) $(HELPER_SCRIPT) generate-notes "$$TRANSCRIPTION_ID" \
		--api-base-url "$(API_BASE_URL)" \
		$(if $(TEMPLATE),--template "$(TEMPLATE)") \
		$(if $(OLLAMA_MODEL),--ollama-model "$(OLLAMA_MODEL)") \
		$(if $(OLLAMA_BASE_URL),--ollama-base-url "$(OLLAMA_BASE_URL)") > /dev/null; \
	NOTES_FILE=$$(ls -t finaloutput/meeting_notes_*.md 2>/dev/null | head -n1); \
	if [ -n "$$NOTES_FILE" ]; then \
		echo "$(BLUE)📝 Meeting notes saved to: $$NOTES_FILE$(NC)"; \
		echo "$(GREEN)✓ Meeting notes generated!$(NC)"; \
	else \
		echo "$(RED)Error: Could not locate generated meeting notes file in finaloutput/$(NC)"; \
		exit 1; \
	fi

.PHONY: notes-ollama
notes-ollama:
	@if [ -z "$(MODEL)" ]; then \
		echo "$(RED)Error: Please specify a model with MODEL=name$(NC)"; \
		exit 1; \
	fi
	@make notes TASK="$(TASK)" OLLAMA_MODEL="$(MODEL)"

# Cleanup task
.PHONY: clean
clean:
	@TASK_ID=""; \
	if [ -n "$(TASK)" ]; then \
		TASK_ID="$(TASK)"; \
		echo "$(CYAN)Using provided Task ID: $$TASK_ID$(NC)"; \
	elif [ -f .last_task_id ]; then \
		TASK_ID=$$(cat .last_task_id); \
		echo "$(CYAN)Using saved Task ID: $$TASK_ID$(NC)"; \
	else \
		echo "$(YELLOW)⚠️  No Task ID available. Skipping remote API cleanup.$(NC)"; \
	fi; \
	echo "$(CYAN)Cleaning up local artifacts...$(NC)"; \
	rm -rf backend/intermediate/* 2>/dev/null || true; \
	rm -f backend/server.log 2>/dev/null || true; \
	rm -rf logs/* 2>/dev/null || true; \
	rm -f .last_task_id .last_transcription_id 2>/dev/null || true; \
	echo "$(GREEN)✓ Cleanup completed!$(NC)"

# Remove everything including final outputs
.PHONY: clean-all
clean-all:
	@echo "$(CYAN)Running standard cleanup...$(NC)"; \
	$(MAKE) clean $(if $(TASK),TASK=$(TASK)) --no-print-directory || true; \
	echo "$(CYAN)Removing generated final outputs...$(NC)"; \
	rm -rf finaloutput/* 2>/dev/null || true; \
	echo "$(GREEN)✓ Full cleanup completed!$(NC)"

# Complete processing workflow
.PHONY: process
process:
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)❌ Error: FILE parameter required$(NC)"; \
		echo "$(CYAN)Usage: make process FILE=path/to/audio.mp3$(NC)"; \
		exit 1; \
	fi
	@echo "$(PURPLE)🚀 Starting complete processing workflow for: $(FILE)$(NC)"
	@$(MAKE) start-servers
	@$(MAKE) upload FILE=$(FILE)
	@TASK_ID=$$(cat .last_task_id); \
	$(MAKE) wait-processing TASK=$$TASK_ID && \
	$(MAKE) transcribe TASK=$$TASK_ID && \
	$(MAKE) notes TASK=$$TASK_ID && \
	$(MAKE) clean TASK=$$TASK_ID
	@echo "$(GREEN)🎉 Complete workflow finished successfully!$(NC)"
	@echo "$(CYAN)📄 Check $(OUTPUT_DIR)/ for results$(NC)"

# Check server status
.PHONY: check-servers
check-servers:
	@echo "$(BLUE)🔍 Checking server status...$(NC)"
	@echo -n "Ollama server: "
	@if curl -s --max-time 5 $(OLLAMA_BASE_URL)/api/tags > /dev/null 2>&1; then \
		echo "$(GREEN)✅ Running$(NC)"; \
	else \
		echo "$(RED)❌ Not running$(NC)"; \
	fi
	@echo -n "Uvicorn server: "
	@if curl -s --max-time 5 $(API_BASE_URL)/health > /dev/null 2>&1; then \
		echo "$(GREEN)✅ Running$(NC)"; \
	else \
		echo "$(RED)❌ Not running$(NC)"; \
	fi

# Install dependencies
.PHONY: install
install:
	@echo "$(BLUE)📦 Installing dependencies...$(NC)"
	@pip3 install -r requirements_auto.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

# Show logs
.PHONY: logs
logs:
	@echo "$(BLUE)📋 Recent logs:$(NC)"
	@if [ -d logs ]; then \
		find logs -name "*.log" -type f -exec ls -lt {} + | head -5 | while read line; do \
			echo "$(CYAN)$$line$(NC)"; \
		done; \
		echo "$(YELLOW)Use 'tail -f logs/<logfile>' to follow logs$(NC)"; \
	else \
		echo "$(YELLOW)No logs directory found$(NC)"; \
	fi

# Helper script target
.PHONY: helper
helper:
	@if [ -z "$(cmd)" ]; then \
		echo "$(CYAN)Available commands:$(NC)"; \
		echo "  upload <file> [--api-base-url URL]"; \
		echo "  transcribe <task_id> [--hf-token TOKEN] [--whisper-model MODEL] [--compute-type TYPE]"; \
		echo "  generate-notes <task_id> [--ollama-model MODEL] [--ollama-base-url URL] [--template TEMPLATE]"; \
		exit 1; \
	fi
	@$(VENV_PYTHON) $(HELPER_SCRIPT) $(cmd) $(filter-out $@,$(MAKECMDGOALS))
	@if [ -d logs ]; then \
		find logs -name "*.log" -type f -mtime +7 -delete; \
		echo "$(GREEN)✅ Old log files cleaned$(NC)"; \
	fi
	@if [ -d $(UPLOADS_DIR)/processed ]; then \
		echo "$(YELLOW)Found processed files in $(UPLOADS_DIR)/processed$(NC)"; \
		echo "$(CYAN)Run 'rm -rf $(UPLOADS_DIR)/processed' to remove them$(NC)"; \
	fi
	@echo "$(GREEN)✅ Cleanup completed$(NC)"

# Create necessary directories
.PHONY: setup
setup:
	@echo "$(BLUE)📁 Setting up directories...$(NC)"
	@mkdir -p $(UPLOADS_DIR) $(OUTPUT_DIR) logs
	@echo "$(GREEN)✅ Directories created$(NC)"

# Ensure directories exist for all targets
# $(UPLOADS_DIR) $(OUTPUT_DIR) logs:
# 	@mkdir -p $@
