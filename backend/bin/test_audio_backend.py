#!/usr/bin/env python3
"""
Test script for audio backend functionality.

This script tests the audio processing capabilities including file I/O and decoding.
"""

import os
import asyncio
import numpy as np
from pathlib import Path
from gtts import gTTS
from pydub import AudioSegment
import tempfile
import sys
import io

# Add project root to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
sys.path.insert(0, project_root)

from app.services.transcription_service import transcription_service

def create_test_audio_file(filename, text="This is a test recording containing a 440Hz tone. The tone is commonly known as musical note A4. It serves as a standard for musical pitch.", lang='en'):
    """Create a test audio file with spoken text."""
    # Create output directory if it doesn't exist
    output_dir = Path("test_audio")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / filename
    
    try:
        # Generate speech using gTTS
        tts = gTTS(text=text, lang=lang, slow=False)
        
        # Save to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as fp:
            temp_path = fp.name
            tts.save(temp_path)
        
        # Convert to WAV format
        audio = AudioSegment.from_mp3(temp_path)
        audio.export(output_path, format="wav")
        
        # Clean up temporary file
        os.unlink(temp_path)
        
        print(f"✓ Created test audio file with speech at: {os.path.abspath(output_path)}")
        return str(output_path)
        
    except Exception as e:
        print(f"Error creating test audio: {str(e)}")
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return None

# from backend.test_audio.generate_test_audio import generate_diarization_audio

async def test_audio_processing():
    try:
        # Use the user-provided audio file for testing
        print("Using user-provided audio file for diarization test...")
        # Correctly construct the path to the user-provided audio file
        script_dir = Path(__file__).parent
        test_file = script_dir / "test_audio" / "recording.m4a"

        if not os.path.exists(test_file):
            raise RuntimeError(f"Failed to find test audio file at {test_file}")

        # Initialize the transcription service
        print("\nInitializing transcription service...")
        if not hasattr(transcription_service, 'model') or transcription_service.model is None:
            await transcription_service.initialize_models()
        print("✓ Transcription service initialized")

        # Transcribe the audio file
        print("\nTranscribing audio...")
        result = await transcription_service.process_audio(test_file)

        # Display transcription results
        print("\n=== Transcription Results ===")
        print(f"Detected language: {result['language']} (confidence: {result['language_probability']*100:.1f}%)")

        if 'segments' in result and result['segments']:
            print("\nSegments:")
            for i, segment in enumerate(result['segments']):
                speaker = segment.get('speaker', f'Speaker {i+1}')
                print(f"[{segment['start']:.2f}s - {segment['end']:.2f}s] {speaker}: {segment['text']}")

        # Save transcription to a file
        output_dir = Path("test_audio")
        output_txt_path = output_dir / "transcription.txt"
        with open(output_txt_path, "w") as f:
            if 'segments' in result and result['segments']:
                for segment in result['segments']:
                    speaker = segment.get('speaker', 'UNKNOWN')
                    f.write(f"{speaker}:{segment['text']}\n")
        print(f"\nTranscription saved to: {output_txt_path}")
        print(f"\n✓ Audio file at: {os.path.abspath(test_file)}")
        
        return True

    except Exception as e:
        print(f"\nError: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(test_audio_processing())