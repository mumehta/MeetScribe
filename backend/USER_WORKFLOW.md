# Meeting Transcriber - User Workflow

This document explains the user workflow for transcribing audio files and generating AI meeting notes.

## Quick Start with Makefile (Recommended)

**Prerequisites**: Ensure servers are running and virtual environment is active:
```bash
make start-servers     # Start Ollama + API servers
make check-servers     # Verify both servers are running
```

**Complete Workflow in One Command**:
```bash
make process FILE=path/to/your/audio.m4a
```

**Step-by-Step Workflow**:
```bash
make upload FILE=path/to/audio.m4a        # Upload & convert
make status TASK=<processing_task_id>     # Check processing
make transcribe TASK=<processing_task_id> # Start transcription
make trans-status TASK=<transcription_task_id>  # Check transcription
make notes TASK=<transcription_task_id>   # Generate meeting notes
```

**Additional Options**:
```bash
make notes-ollama TASK=<id> MODEL=mistral  # Use different model
make clean TASK=<id>                       # Clean specific task
make clean-all                             # Clean all files
make logs                                  # View system logs
```

## API Workflow (Advanced Users)

The system provides a 3-step process:
1. **Upload & Convert Audio** → Analyze file and convert to standard format
2. **Transcribe Audio** → Get transcription with speaker identification
3. **Generate Notes** → Create AI-powered meeting summary from transcription

## Step 1: Upload Audio for Processing

**API Call:**
```http
POST /api/v1/upload-audio
Content-Type: multipart/form-data
```

**What you send:**
- Audio file (supports: wav, mp3, m4a, mp4, ogg, flac)

**What you get back immediately:**
```json
{
  "processing_task_id": "e490919f-5993-4207-9740-d3bbaf606ae5",
  "status": "analyzing",
  "message": "Audio file uploaded successfully. Analysis and conversion in progress."
}
```

**What happens:**
- File is analyzed for format, duration, quality
- File is converted to standard format (16kHz, mono, WAV)
- Conversion happens in background

## Step 2: Check Processing Status

**API Call:**
```http
GET /api/v1/audio-processing/{processing_task_id}
```

**Response when completed:**
```json
{
  "task_id": "e490919f-5993-4207-9740-d3bbaf606ae5",
  "status": "completed",
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:30:15Z",
  "file_info": {
    "original_format": "m4a",
    "file_size_mb": 12.5,
    "duration_seconds": 1800,
    "codec": "aac",
    "sample_rate": 44100,
    "channels": 2
  },
  "converted_file": "/path/to/converted.wav"
}
```

## Step 3: Start Transcription

**API Call:**
```http
POST /api/v1/transcribe/{processing_task_id}
```

**What you get back:**
```json
{
  "transcription_task_id": "a123b456-7890-1234-5678-90abcdef1234",
  "status": "processing",
  "processing_task_id": "e490919f-5993-4207-9740-d3bbaf606ae5",
  "config_overrides": {},
  "audio_file_info": {
    "original_format": "m4a",
    "file_size_mb": 12.5,
    "duration_seconds": 1800
  }
}
```

**Key Points:**
- ✅ **Instant Response**: You get a `task_id` (UUID) immediately
- 🔄 **Async Processing**: Transcription happens in the background
- 📝 **No File Returned**: The system processes internally, no `.txt` file returned directly

## Step 4: Check Transcription Status

**API Call:**
```http
GET /api/v1/transcribe/{transcription_task_id}
```

**While Processing:**
```json
{
  "task_id": "e490919f-5993-4207-9740-d3bbaf606ae5",
  "status": "processing",
  "created_at": "2025-08-29T07:39:49.935437"
}
```

**When Complete:**
```json
{
  "task_id": "e490919f-5993-4207-9740-d3bbaf606ae5",
  "status": "completed",
  "created_at": "2025-08-29T07:39:49.935437",
  "completed_at": "2025-08-29T07:41:15.123456",
  "result": {
    "language": "en",
    "language_probability": 1.0,
    "segments": [
      {
        "start": 0.54,
        "end": 4.34,
        "text": "externally we'll find if we need...",
        "speaker": "SPEAKER_01"
      },
      {
        "start": 4.34,
        "end": 8.10,
        "text": "external but if you don't find...",
        "speaker": "SPEAKER_01"
      }
    ]
  }
}
```

## Step 5: Generate AI Meeting Notes

**API Call:**
```http
POST /api/v1/generate-notes/{transcription_task_id}
```

**What you get back:**
```json
{
  "task_id": "a123b456-7890-1234-5678-90abcdef1234",
  "notes": {
    "summary": "Team discussed project timeline and resource allocation...",
    "key_points": [
      "Project deadline moved to March 15th",
      "Additional developer needed for frontend"
    ],
    "action_items": [
      "John to hire frontend developer by Feb 1st",
      "Sarah to update project timeline"
    ],
    "participants": ["SPEAKER_00", "SPEAKER_01", "SPEAKER_02"]
  }
}
```

## Complete Example Workflow

### Using cURL

```bash
# Step 1: Upload audio file
curl -X POST "http://localhost:8000/api/v1/upload-audio" \
  -F "file=@meeting.m4a"

# Response: {"processing_task_id": "abc-123-def", "status": "processing"}

# Step 2: Check status (repeat until completed)
curl -X GET "http://localhost:8000/api/v1/audio-processing/abc-123-def"

# Step 3: Start transcription
curl -X POST "http://localhost:8000/api/v1/transcribe/abc-123-def"

# Step 4: Check transcription status (repeat until completed)
curl -X GET "http://localhost:8000/api/v1/transcribe/trans-456-def"

# Step 5: Generate meeting notes
curl -X POST "http://localhost:8000/api/v1/generate-notes/trans-456-def"
```

### Using Python

```python
import requests
import time

# Step 1: Upload audio
with open('meeting.m4a', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/api/v1/upload-audio',
        files={'file': f}
    )
    processing_task_id = response.json()['processing_task_id']
    print(f"Processing Task ID: {processing_task_id}")

# Step 2: Wait for processing to complete
while True:
    response = requests.get(f'http://localhost:8000/api/v1/audio-processing/{processing_task_id}')
    status = response.json()['status']
    
    if status == 'completed':
        print("Processing completed!")
        break
    elif status == 'error':
        print("Processing failed:", response.json()['error'])
        exit(1)
    
    print("Still processing...")
    time.sleep(5)

# Step 3: Start transcription
response = requests.post(f'http://localhost:8000/api/v1/transcribe/{processing_task_id}')
transcription_task_id = response.json()['transcription_task_id']
print(f"Transcription Task ID: {transcription_task_id}")

# Step 4: Wait for transcription to complete
while True:
    response = requests.get(f'http://localhost:8000/api/v1/transcribe/{transcription_task_id}')
    status = response.json()['status']
    
    if status == 'completed':
        transcript = response.json()['result']
        print("Transcription completed!")
        break
    elif status == 'error':
        print("Transcription failed:", response.json()['error'])
        exit(1)
    
    print("Still processing...")
    time.sleep(5)

# Step 5: Generate meeting notes
notes_response = requests.post(f'http://localhost:8000/api/v1/generate-notes/{transcription_task_id}')
meeting_notes = notes_response.json()['notes_result']
print("\n=== Meeting Notes ===")
print(meeting_notes)
```

## Important Notes

### Data Flow
- **No File Exchange**: You don't receive or send `.txt` files
- **Memory Storage**: Transcription is stored in server memory using `task_id`
- **JSON Responses**: All data exchanged via JSON API responses

### Task IDs
- **Processing Task ID**: From step 1 (audio upload/conversion)
- **Transcription Task ID**: From step 3 (transcription)
- **Save both IDs** - you need them for the workflow
- Use Processing Task ID to start transcription
- Use Transcription Task ID to get results and generate notes

### File Handling
- Files are analyzed and converted to standard format (16kHz, mono, WAV)
- No need to pre-process your audio files
- Everything works through the API with task IDs
- Files are processed and stored temporarily on the server
- Use cleanup endpoint to remove files when done

### Processing Time
- Audio analysis/conversion: Usually 5-15 seconds
- Transcription: Depends on audio length (roughly 1:4 ratio - 10min audio = ~2.5min processing)
- AI Notes: Usually 10-30 seconds
- Check status periodically rather than waiting

### Error Handling
- If processing fails, the status will show "error" with details
- If transcription fails, the status will show "error" with details
- If Ollama service is not running, meeting notes will fail
- Invalid file types are rejected immediately

### Cleanup
- Use Makefile targets after transcription and notes are complete:
  - `make clean` — removes intermediate files, logs, and last ID files
  - `make clean-all` — also removes all files in `finaloutput/`

## Quick Example Workflow

```bash
# 1. Upload and process audio file
curl -X POST "http://localhost:8000/api/v1/upload-audio" \
  -F "file=@meeting.m4a"
# Returns: {"processing_task_id": "proc123...", "status": "analyzing"}

# 2. Check processing status (repeat until completed)
curl "http://localhost:8000/api/v1/audio-processing/proc123..."
# Returns: processing status and file info

# 3. Start transcription
curl -X POST "http://localhost:8000/api/v1/transcribe/proc123..."
# Returns: {"transcription_task_id": "trans456...", "status": "processing"}

# 4. Check transcription status (repeat until completed)
curl "http://localhost:8000/api/v1/transcribe/trans456..."
# Returns: transcription when ready

# 5. Generate meeting notes
curl -X POST "http://localhost:8000/api/v1/generate-notes/trans456..."
# Returns: AI-generated meeting summary

# 6. Clean up files (Makefile)
make clean
```

## Configuration Overrides

You can override default settings for transcription:

```bash
# Override Whisper model and disable diarization
curl -X POST "http://localhost:8000/api/v1/transcribe/proc123...?whisper_model=medium.en&use_diarization=false"

# Override with HuggingFace token for diarization
curl -X POST "http://localhost:8000/api/v1/transcribe/proc123..." \
  -H "X-HuggingFace-Token: your_token_here"
```

Available overrides:
- `whisper_model`: Model size (tiny.en, small.en, medium.en, large)
- `compute_type`: Processing type (int8, float16, float32)
- `use_diarization`: Enable/disable speaker identification (true/false)
- `X-HuggingFace-Token`: Header for HuggingFace access token

## Summary

1. **Upload** → Get `processing_task_id`
2. **Poll Status** → Wait for processing to complete
3. **Start Transcription** → Get `transcription_task_id`
4. **Poll Transcription Status** → Wait for transcription to complete
5. **Generate Meeting Notes** → Use `transcription_task_id`

The workflow is designed for async processing with JSON API responses, not file-based exchanges.
