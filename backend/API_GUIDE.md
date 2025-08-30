# Meeting Transcriber API Guide

A FastAPI-based service for audio transcription with speaker diarization and AI-powered meeting notes generation.

## Quick Start

1. **Activate virtual environment and start the server:**
   ```bash
   cd backend
   
   # IMPORTANT: Activate virtual environment first
   source venv/bin/activate  # On macOS/Linux
   # venv\Scripts\activate    # On Windows
   
   # Start the API server
   python start_server.py
   ```

2. **Access the API:**
   - **API Documentation**: http://localhost:8000/docs
   - **Health Check**: http://localhost:8000/
   - **Base API URL**: http://localhost:8000/api/v1

## API Endpoints

### 1. Health Check
```http
GET /
```
Returns server status and version information.

### 2. Upload Audio for Transcription
```http
POST /api/v1/transcribe
Content-Type: multipart/form-data
```

**Parameters:**
- `file`: Audio file (supports: wav, mp3, m4a, mp4, ogg, flac)

**Query Parameters (Optional Overrides):**
- `whisper_model`: Override Whisper model (e.g., `small.en`, `medium.en`, `large-v2`)
- `compute_type`: Override compute type (e.g., `int8`, `float16`, `float32`)
- `use_diarization`: Override speaker diarization setting (`true`/`false`)

**Headers (Optional Overrides):**
- `X-HuggingFace-Token`: Override HuggingFace token for speaker diarization

**Response:**
```json
{
  "task_id": "uuid-string",
  "status": "processing",
  "config_overrides": {
    "whisper_model": "small.en",
    "compute_type": "int8",
    "use_diarization": true,
    "hf_token": "hf_..."
  }
}
```

### 3. Get Transcription Status/Result
```http
GET /api/v1/transcribe/{task_id}
```

**Response (Processing):**
```json
{
  "task_id": "uuid-string",
  "status": "processing",
  "created_at": "2025-08-29T07:20:54.192433"
}
```

**Response (Completed):**
```json
{
  "task_id": "uuid-string",
  "status": "completed",
  "created_at": "2025-08-29T07:20:54.192433",
  "completed_at": "2025-08-29T07:22:15.123456",
  "result": {
    "language": "en",
    "language_probability": 1.0,
    "segments": [
      {
        "start": 0.54,
        "end": 4.34,
        "text": "externally we'll find if we need...",
        "speaker": "SPEAKER_01"
      }
    ]
  }
}
```

### 4. Generate Meeting Notes
```http
POST /api/v1/generate-notes/{task_id}
```

**Parameters:**
- `task_id`: ID of a completed transcription task

**Query Parameters (Optional Overrides):**
- `template`: Custom template for note generation
- `ollama_model`: Override Ollama model (e.g., `llama2:13b`, `mistral`, `codellama`)
- `ollama_base_url`: Override Ollama base URL (default: `http://localhost:11434`)

**Response:**
```json
{
  "task_id": "uuid-string",
  "transcription_created_at": "2025-08-29T07:20:54.192433",
  "notes_result": {
    "status": "completed",
    "notes": "# Meeting Summary\n\n## Key Points\n...",
    "generated_at": "2025-08-29T07:25:30.123456",
    "model_used": "llama2:13b",
    "base_url_used": "http://localhost:11434",
    "transcript_length": 46
  }
}
```

### 5. Check Ollama Status
```http
GET /api/v1/ollama/status
```

**Response:**
```json
{
  "status": "available",
  "base_url": "http://localhost:11434",
  "configured_model": "llama2:13b",
  "available_models": ["llama2:13b", "mistral:latest"]
}
```

## Configuration

The API uses environment variables from `.env` file:

```ini
# Whisper Settings
WHISPER_MODEL=medium.en
COMPUTE_TYPE=int8

# Speaker Diarization
USE_SPEAKER_DIARIZATION=true
HUGGINGFACE_TOKEN=your_token_here

# Ollama Settings
OLLAMA_MODEL=llama2:13b
OLLAMA_BASE_URL=http://localhost:11434

# File Settings
UPLOAD_FOLDER=uploads
MAX_FILE_SIZE=52428800  # 50MB
```

## Usage Examples

### Python Example
```python
import requests
import time

# Upload audio file
with open('meeting.m4a', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/transcribe',
        files={'file': f}
    )
    task_id = response.json()['task_id']

# Wait for transcription to complete
while True:
    response = requests.get(f'http://localhost:8000/api/v1/transcribe/{task_id}')
    status = response.json()['status']
    
    if status == 'completed':
        transcript = response.json()['result']
        break
    elif status == 'error':
        print("Transcription failed:", response.json()['error'])
        break
    
    time.sleep(5)  # Wait 5 seconds before checking again

# Generate meeting notes
notes_response = requests.post(f'http://localhost:8000/api/v1/generate-notes/{task_id}')
meeting_notes = notes_response.json()['notes_result']['notes']
print(meeting_notes)
```

### cURL Examples
```bash
# Upload audio with default settings
curl -X POST "http://localhost:8000/api/v1/transcribe" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@meeting.m4a"

# Upload audio with configuration overrides
curl -X POST "http://localhost:8000/api/v1/transcribe?whisper_model=medium.en&compute_type=float16&use_diarization=true" \
  -H "Content-Type: multipart/form-data" \
  -H "X-HuggingFace-Token: your_token_here" \
  -F "file=@meeting.m4a"

# Check status
curl -X GET "http://localhost:8000/api/v1/transcribe/{task_id}"

# Generate notes with default settings
curl -X POST "http://localhost:8000/api/v1/generate-notes/{task_id}"

# Generate notes with configuration overrides
curl -X POST "http://localhost:8000/api/v1/generate-notes/{task_id}?ollama_model=mistral&ollama_base_url=http://localhost:11434"

# Check Ollama status
curl -X GET "http://localhost:8000/api/v1/ollama/status"
```

## Prerequisites & Setup

1. **Virtual Environment Setup**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On macOS/Linux
   pip install -r requirements.txt
   ```

2. **HuggingFace Token**: Required for speaker diarization
   - Get token from: https://huggingface.co/settings/tokens
   - Add to `backend/.env`: `HUGGINGFACE_TOKEN=your_token_here`

3. **Ollama**: Required for meeting notes generation
   ```bash
   # Install Ollama
   brew install ollama  # macOS
   
   # Start service
   ollama serve
   
   # Pull model
   ollama pull llama2:13b
   ```

## Troubleshooting

### Common Startup Issues:

1. **Import Errors**: 
   ```bash
   # Solution: Activate virtual environment
   cd backend
   source venv/bin/activate
   python start_server.py
   ```

2. **Port Already in Use**:
   ```bash
   # Solution: Kill existing processes
   lsof -ti:8000 | xargs kill -9
   ```

3. **Slow Processing**: 
   ```bash
   # Solution: Disable diarization temporarily
   # In backend/.env:
   USE_SPEAKER_DIARIZATION=false
   ```

## Features

- ✅ **High-accuracy transcription** using Faster Whisper
- ✅ **Speaker diarization** with pyannote.audio
- ✅ **Multiple audio formats** supported
- ✅ **Async processing** with task tracking
- ✅ **AI meeting notes** generation using Ollama
- ✅ **RESTful API** with automatic documentation
- ✅ **Error handling** and status tracking

## Error Handling

The API returns appropriate HTTP status codes:
- `200`: Success
- `400`: Bad Request (invalid file type, task not ready, etc.)
- `404`: Task not found
- `500`: Internal server error
- `503`: Service unavailable (Ollama not running)

All error responses include a `detail` field with the error message.
