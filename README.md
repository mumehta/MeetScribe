<div align="center">
  <h1>🎙️ Meeting Transcriber & AI Notes Generator</h1>
  <p>
    <strong>Local, Private, and Powerful</strong> - Transcribe meetings and generate AI-powered notes with full control over your data
  </p>
  <p>
    <a href="#-quick-start">Quick Start</a> •
    <a href="#-features">Features</a> •
    <a href="#-setup">Setup</a> •
    <a href="#-documentation">Documentation</a> •
    <a href="#-troubleshooting">Help</a>
  </p>
  <p><small>Created and maintained by Munish Mehta</small></p>
</div>

## 🌟 Key Features

### 🎙️ Transcription
- High-accuracy audio transcription using Whisper
- Support for multiple audio formats (MP3, WAV, M4A, etc.)
- Configurable model sizes (small, medium, large)
- Automatic audio format conversion

### 👥 Speaker Diarization
- Identify different speakers in conversations
- Configurable diarization settings
- Visual speaker separation in transcripts

### 🤖 AI-Powered Analysis
- Generate meeting summaries
- Extract action items and key points
- Local LLM integration via Ollama
- Customizable note templates

### ⚙️ Developer Friendly
- RESTful API with OpenAPI documentation
- Containerized deployment ready
- Detailed logging and monitoring
- Extensible architecture



## 📝 Output Format

### Transcript Example (with timestamps):
```
[0:00:00 - 0:00:04,920000] Speaker 1: First speaker's text
[0:00:05,000000 - 0:00:10,000000] Speaker 2: Second speaker's text
```

### Without Timestamps:
```
Speaker 1: First speaker's text
Speaker 2: Second speaker's text
```

### Meeting Notes Example:
```markdown
# Meeting Summary - [Date]

## Key Points
- First key discussion point
- Second key takeaway

## Action Items
- [ ] Task 1 (Owner: @mumehta)
- [ ] Task 2 (Due: YYYY-MM-DD)
```

## 🚀 Quick Start

### 1. Clone & Setup
```bash
git clone <repository-url>
cd MeetScribe
cp backend/.env_example backend/.env
# Edit .env with your Hugging Face token
make venv-activate
```

### 2. Start Services
```bash
# Start both services in separate terminals
make start-servers
```

### 3. Process Your First Meeting
```bash
make process FILE=path/to/your/meeting.m4a
```

## 🛠️ Prerequisites

### 1. Python Environment
- Python 3.8+ with virtual environment (venv)
- FFmpeg (for audio processing)
- `make` command (usually pre-installed on Unix-like systems)

### 2. Hugging Face Account & Model Access
1. Create a free account at [Hugging Face](https://huggingface.co/)
2. Accept the terms of use for these models (requires email verification):
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) (required for diarization)
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0) (required for speaker diarization to work)
3. Generate an access token (not required for fully offline mode):
   - Go to [Hugging Face Settings > Access Tokens](https://huggingface.co/settings/tokens)
   - Create a new token with "Read" access
   - Add this token to your `.env` file (see Configuration section below)

### 3. Ollama Setup (for AI Meeting Notes)
1. Install Ollama on your system:
   ```bash
   # macOS
   brew install ollama
   
   # Linux
   curl -fsSL https://ollama.com/install.sh | sh
   ```
2. Download the recommended models (choose based on your system's capabilities):
   ```bash
   # For most systems (balanced performance/quality)
   ollama pull llama2:13b
   
   # For more powerful systems (better quality)
   ollama pull gpt-oss:20b
   ```
3. Start the Ollama server (required for meeting notes generation):
   ```bash
   ollama serve
   ```
   Keep this terminal window open and running in the background.

### 4. FastAPI Server
- The application uses Uvicorn to serve the FastAPI backend
- The server will be started automatically during setup
- Runs on `http://localhost:8000` by default

### 5. Environment Configuration
1. Rename `.env_example` to `.env` in the backend directory:
   ```bash
   cp backend/.env_example backend/.env
   ```
2. Edit `.env` and configure the following (see Offline Mode below for a tokenless, offline setup):
   - `HUGGINGFACE_TOKEN`: Your Hugging Face access token
   - Adjust other parameters as needed (model sizes, paths, etc.)

## 🔧 Makefile Commands

### Development
```bash
make venv-activate    # Create and activate virtual environment
make install          # Install dependencies
make format           # Format code with black and isort
make lint             # Run linters
make test             # Run tests
```

### Server Management
```bash
make start-uvicorn    # Start FastAPI (Uvicorn) server
make start-ollama     # Start Ollama server
make start-servers    # Start both servers
```

### Processing
```bash
make process FILE=path/to/audio.m4a  # Complete pipeline
make upload FILE=...                 # Upload audio only
make transcribe TASK=<id>            # Transcribe uploaded audio
make notes TASK=<id>                 # Generate notes from transcript
```

### Cleanup
```bash
make clean        # Remove temporary files
make clean-all    # Remove all generated files
```

## 🤝 Contributing

Contributions are welcome! Please follow these steps:
1. Fork the repository
2. Create a feature branch
3. Submit a pull request

Please ensure your code follows the project's style and includes appropriate tests.

## 📄 License

MIT License

Copyright (c) 2025 Munish Mehta

Permission is hereby granted...

## 🙏 Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) for speech recognition
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) for speaker diarization
- [Ollama](https://ollama.ai/) for local LLM inference
- [FastAPI](https://fastapi.tiangolo.com/) for the API framework

## 📋 Detailed Setup Guide

### 1. Python Environment
- Python 3.8+ with virtual environment (venv)
- FFmpeg (for audio processing)
- `make` command (usually pre-installed on Unix-like systems)

### 2. Hugging Face Setup
1. Create a free account at [Hugging Face](https://huggingface.co/)
2. Accept the terms of use for these models (requires email verification):
   - [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
   - [pyannote/segmentation-3.0](https://huggingface.co/pyannote/segmentation-3.0)
3. Generate and configure your access token in `.env`

### 3. Ollama Setup
```bash
# Install Ollama
brew install ollama  # macOS
# OR
curl -fsSL https://ollama.com/install.sh | sh  # Linux

# Download models
ollama pull llama2:13b  # Recommended for most systems
ollama pull gpt-oss:20b  # For more powerful systems
```

## 📚 Documentation

### User Guides
- [Complete User Guide](./backend/USER_WORKFLOW.md)
- [API Reference](./backend/API_GUIDE.md)
- [Makefile Commands](#-makefile-commands)

### Project Information
- [Contributing](CONTRIBUTING.md) - How to contribute
- [Code of Conduct](CODE_OF_CONDUCT.md) - Community guidelines
- [License](LICENSE) - Usage terms

## 🛠️ Configuration

### Environment Variables
Edit `backend/.env` to configure:
- `HUGGINGFACE_TOKEN`: Your Hugging Face access token
- `WHISPER_MODEL`: Model size (tiny, base, small, medium, large)
- `COMPUTE_TYPE`: Default is "int8"
- `LANGUAGE`: Default is "en"
- `PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH`: Base local path to your offline pyannote model cache (see Offline Mode)

### Speaker Diarization Modes (offline | online | auto)

The backend supports three diarization modes via `DIARIZATION_MODE`:

- __offline__: Strictly use local files. No internet calls. Requires a local cache of the pyannote model.
- __online__: Always load from Hugging Face Hub. Requires `HUGGINGFACE_TOKEN` and acceptance of model terms.
- __auto__: Try offline first; if that fails and a token is available, fallback to online.

Common variables (for all modes):
- `USE_SPEAKER_DIARIZATION=true|false` — enable/disable diarization
- `PYANNOTE_SEGMENTATION_MODEL` — default: `pyannote/speaker-diarization-3.1` (can be left as default)
- `DIARIZATION_MODE=offline|online|auto`

Offline-specific requirements:
- `PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH` must point to the base model directory (not a snapshots subdirectory), e.g.:
  `~/.cache/huggingface/pyannote/sd3.1/pyannote-models/models--pyannote--speaker-diarization-3.1`
  The app automatically reads `refs/main` to resolve `snapshots/<sha>/config.yaml`. Do not append `snapshots/...` in `.env`.
- No token is required in strict offline mode.

Online-specific requirements:
- `HUGGINGFACE_TOKEN` must be set.
- You must accept the terms for the models on Hugging Face:
  - https://huggingface.co/pyannote/speaker-diarization-3.1
  - https://huggingface.co/pyannote/segmentation-3.0

Auto mode behavior:
- First attempts the offline load using your local cache.
- If offline fails and a token is available, it falls back to online load.
- If no token is available, it remains offline-only.

Examples

Offline:
```ini
USE_SPEAKER_DIARIZATION=true
DIARIZATION_MODE=offline
PYANNOTE_SEGMENTATION_MODEL=pyannote/speaker-diarization-3.1
PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH=~/.cache/huggingface/pyannote/sd3.1/pyannote-models/models--pyannote--speaker-diarization-3.1
# HUGGINGFACE_TOKEN is not required for offline
```

Online:
```ini
USE_SPEAKER_DIARIZATION=true
DIARIZATION_MODE=online
HUGGINGFACE_TOKEN=your_hf_token_here
PYANNOTE_SEGMENTATION_MODEL=pyannote/speaker-diarization-3.1
# PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH is optional in pure online mode
```

Auto (offline-first with online fallback if token is present):
```ini
USE_SPEAKER_DIARIZATION=true
DIARIZATION_MODE=auto
PYANNOTE_SEGMENTATION_MODEL=pyannote/speaker-diarization-3.1
PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH=~/.cache/huggingface/pyannote/sd3.1/pyannote-models/models--pyannote--speaker-diarization-3.1
HUGGINGFACE_TOKEN=your_hf_token_here  # Optional; enables online fallback
```

### Performance Tuning
- **For better quality**: Use `gpt-oss:20b` (requires more resources)
- **For balanced performance**: Use `llama2:13b` (recommended for most systems)
- **For faster transcription**: Use smaller Whisper models (`base.en`, `small.en`)
- Detailed endpoint documentation
- Request/response examples
- Authentication and headers
- Advanced configuration options

## 🔧 Advanced Configuration

### Manual Server Startup
```bash
# Start services individually
make start-ollama    # Start Ollama service
make start-uvicorn   # Start FastAPI (Uvicorn) server
```

### Manual Virtual Environment Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

**Check server status**:
```bash
make check-servers
```

### Step 3: Complete Workflow

**Option A: Full Automated Workflow**
```bash
make process FILE=path/to/your/audio.m4a
```

**Option B: Step-by-Step Workflow**

1. **Upload audio file**:
   ```bash
   make upload FILE=path/to/your/audio.m4a
   # Returns: processing_task_id
   ```

2. **Check processing status**:
   ```bash
   make status TASK=<processing_task_id>
   # Wait for status: "completed"
   ```

3. **Start transcription**:
   ```bash
   make transcribe TASK=<processing_task_id>
   # Returns: transcription_task_id
   ```

4. **Check transcription status**:
   ```bash
   make trans-status TASK=<transcription_task_id>
   # Wait for completion
   ```

5. **Generate meeting notes**:
   ```bash
   make notes TASK=<transcription_task_id>
   ```

### Step 4: Additional Options

**Change Ollama model**:
```bash
make notes-ollama TASK=<transcription_task_id> MODEL=mistral
```

**Clean up files**:
```bash
make clean TASK=<task_id>     # Clean specific task
make clean-all                # Clean all temporary files
```

**View logs**:
```bash
make logs
```

**Stop servers**:
```bash
make stop-servers
```

## Configuration

1. **Get a HuggingFace Token**:
   - Go to [HuggingFace Settings > Access Tokens](https://huggingface.co/settings/tokens)

2. **Configure Environment Variables**:
   Update `backend/.env` file:

```ini
# Whisper Settings
WHISPER_MODEL=tiny.en  # Options: tiny.en, small.en, medium.en, large
COMPUTE_TYPE=int8

# Speaker Diarization Settings
USE_SPEAKER_DIARIZATION=true
HUGGINGFACE_TOKEN=your_token_here
PYANNOTE_SEGMENTATION_MODEL=pyannote/speaker-diarization

# Output Format
SHOW_TIMESTAMPS=false

# Meeting Notes - Ollama Settings
OLLAMA_MODEL=llama2:13b
OLLAMA_BASE_URL=http://localhost:11434
MAX_FILE_SIZE=52428800  # 50MB in bytes
```

**Environment Variable Priority**:
The application checks system environment variables first, then falls back to `.env` file values for:
- `HUGGINGFACE_TOKEN`
- `OLLAMA_MODEL` 
- `OLLAMA_BASE_URL`

## Manual Server Management

If you prefer manual control instead of Makefile targets:

```bash
cd backend

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate    # On Windows

# Start the API server with logging options
python -m app.main --log-level INFO --reload
```

**Server Information**:
- API Server: http://localhost:8000
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/

**CLI Options**:
```bash
python -m app.main --help
# Options: --log-level, --host, --port, --reload
```

## Troubleshooting

### Common Issues:

1. **Import Errors**: Make sure virtual environment is activated:
   ```bash
   make venv-activate
   # or manually: source backend/venv/bin/activate
   ```

2. **Servers Not Running**: Check and start servers:
   ```bash
   make check-servers
   make start-servers
   ```

3. **Port Already in Use**: Stop and restart servers:
   ```bash
   make stop-servers
   make start-servers
   # or kill processes: lsof -ti:8000 | xargs kill -9
   ```

4. **Slow Processing**: Disable speaker diarization in `.env`:
   ```bash
   USE_SPEAKER_DIARIZATION=false
   ```

5. **Task Not Found**: Check task IDs and status:
   ```bash
   make status TASK=<processing_task_id>
   make trans-status TASK=<transcription_task_id>
   ```

6. **Ollama Issues**: Ensure Ollama is running and model is available:
   ```bash
   make start-ollama
   ollama list  # Check available models
   ```

7. **Log Debugging**: View detailed logs:
   ```bash
   make logs
   # or start with debug logging: python -m app.main --log-level DEBUG
   ```

## API Usage

The API provides a 3-step workflow:

### 1. Upload Audio File
```bash
curl -X POST "http://localhost:8000/api/v1/upload-audio" \
  -F "file=@your_audio.m4a"
```
**Returns**: `processing_task_id`

### 2. Check Processing Status
```bash
curl "http://localhost:8000/api/v1/audio-processing/{processing_task_id}"
```
**Wait for**: `status: "completed"`

### 3. Start Transcription
```bash
curl -X POST "http://localhost:8000/api/v1/transcribe/{processing_task_id}"
```
**Returns**: `transcription_task_id`

### 4. Check Transcription Status
```bash
curl "http://localhost:8000/api/v1/transcribe/{transcription_task_id}"
```
**Wait for**: Transcription results

### 5. Generate Meeting Notes
```bash
curl -X POST "http://localhost:8000/api/v1/generate-notes/{transcription_task_id}"
```

Optional query parameters:
- `template` — custom output template
- `ollama_model` — override model (e.g., llama2:13b, mistral)
- `ollama_base_url` — override Ollama base URL

Example with overrides:
```bash
curl -X POST "http://localhost:8000/api/v1/generate-notes/{transcription_task_id}?template=concise&ollama_model=llama2:13b"
```

### 6. Cleanup (Optional)
Use Makefile targets:

- `make clean TASK=<task_id>`  — Clean specific task files
- `make clean-all`             — Clean all temporary files

## Makefile Quick Reference

**Essential Commands**:
```bash
make help              # Show all available targets
make start-servers     # Start Ollama + API servers
make check-servers     # Check server status
make process FILE=<path>  # Complete workflow
make stop-servers      # Stop all servers
```

**Step-by-Step Commands**:
```bash
make upload FILE=<path>           # Upload audio file
make status TASK=<id>             # Check processing status
make transcribe TASK=<id>         # Start transcription
make trans-status TASK=<id>       # Check transcription status
make notes TASK=<id>              # Generate meeting notes
make notes-ollama TASK=<id> MODEL=<name>  # Use custom model
```

**Utilities**:
```bash
make venv-activate     # Setup virtual environment
make install          # Install dependencies
make logs             # View recent logs
make clean TASK=<id>  # Clean specific task
make clean-all        # Clean all files
```

## File Structure

```
MeetScribe/
├── backend/                    # API backend
│   ├── venv/                  # Virtual environment (REQUIRED)
│   ├── .env                   # Configuration file
│   ├── start_server.py        # Server startup script
│   ├── requirements.txt       # Python dependencies
│   ├── intermediate/          # Temporary processing files
│   └── app/                   # Application code
├── uploads/                   # User uploaded files
├── finaloutput/              # Generated transcripts & notes
│   ├── transcribed_[timestamp].txt
│   └── meeting_notes_[timestamp].txt
└── frontend/                 # Frontend code (future)
```

## Output Files

Final outputs are saved to `finaloutput/` with human-readable timestamps:

- **Transcripts**: `transcribed_29_aug_2025_09_30_pm.txt`
- **Meeting Notes**: `meeting_notes_29_aug_2025_09_30_pm.txt`

**Supported Audio Formats**: wav, mp3, m4a, mp4, ogg, flac

## Performance Optimization

**For Faster Processing**:
1. Use smaller Whisper models (`tiny.en` vs `small.en`)
2. Disable speaker diarization temporarily: `USE_SPEAKER_DIARIZATION=false`
3. Use faster diarization models: `pyannote/speaker-diarization` vs `pyannote/speaker-diarization-3.1`

**Processing Times** (3-minute audio):
- Without diarization: 30 seconds - 2 minutes
- With diarization: 5-15 minutes (CPU-dependent)

## Important Notes

- **Virtual Environment**: Always activate `backend/venv` before starting the server
- **First Run**: Downloads Whisper and (if not using Offline Mode) diarization models
- **HuggingFace Token**: Not required when using fully offline diarization setup
- **Ollama**: Must be running for meeting notes generation
- **File Cleanup**: Use Makefile targets (`make clean` / `make clean-all`) to manage disk space

## 📦 Offline Mode (Pyannote Diarization Without Internet)

You can run speaker diarization fully offline using pre-downloaded pyannote models. The backend will resolve the correct snapshot locally and will not attempt any network calls.

### Step 1: Prepare Local Model Cache

1. Create the cache directory:
   ```bash
   mkdir -p ~/.cache/huggingface/pyannote/sd3.1
   ```
2. Unzip the provided archive into that directory while preserving structure:
   ```bash
   unzip pynode-model/pyannote-models.zip -d ~/.cache/huggingface/pyannote/sd3.1
   ```
   After extraction, you should have a path like:
   `~/.cache/huggingface/pyannote/sd3.1/pyannote-models/models--pyannote--speaker-diarization-3.1/`

### Step 2: Configure .env

Edit `backend/.env` and set the base local path (do NOT append `snapshots/latest`):

```ini
# Enable diarization if desired
USE_SPEAKER_DIARIZATION=true

# Point to the base models directory; the app resolves the actual snapshot via refs/main
PYANNOTE_SEGMENTATION_MODEL_LOCAL_PATH=~/.cache/huggingface/pyannote/sd3.1/pyannote-models/models--pyannote--speaker-diarization-3.1

# When using fully offline mode, HUGGINGFACE_TOKEN can be omitted
# HUGGINGFACE_TOKEN=
```

Notes:
- The app reads `refs/main` inside the model folder to find the correct `snapshots/<hash>` and validate `config.yaml`.
- Offline mode is enforced internally (`HF_HUB_OFFLINE` and `TRANSFORMERS_OFFLINE`) to prevent network access during inference.

### Step 3: Start Services and Run

```bash
make venv-activate
make start-servers
make process FILE=path/to/your/meeting.m4a
```

If diarization is disabled or not needed, set `USE_SPEAKER_DIARIZATION=false`.

## License

This project is open source and available under the [MIT License](LICENSE).
