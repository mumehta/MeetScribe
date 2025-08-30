#!/usr/bin/env python3
"""
Generate a test audio file with multiple speakers for testing diarization.
"""
import os
from pathlib import Path
from gtts import gTTS
from pydub import AudioSegment
from pydub.effects import speedup
import pyttsx3
import tempfile

def generate_diarization_audio(output_dir: str = "test_audio"):
    """Generate a test audio file for speaker diarization with male and female voices."""
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)

    engine = pyttsx3.init()
    voices = engine.getProperty('voices')

    # Find a male and a female voice
    male_voice = None
    female_voice = None
    for voice in voices:
        if voice.gender == 'male' and not male_voice:
            male_voice = voice.id
        elif voice.gender == 'female' and not female_voice:
            female_voice = voice.id
    
    # Fallback if specific genders are not found
    if not male_voice:
        male_voice = voices[0].id
    if not female_voice:
        female_voice = voices[1].id if len(voices) > 1 else voices[0].id

    speakers = [
        {"text": "Hello. I'm the first speaker. This is a test of the speaker diarization system.", "voice": female_voice, "file": Path(tempfile.gettempdir()) / "temp1.aiff"},
        {"text": "Hello. I'm the second speaker. This is a test of the speaker diarization system.", "voice": male_voice, "file": Path(tempfile.gettempdir()) / "temp2.aiff"}
    ]

    engine = pyttsx3.init()

    # Queue both save_to_file commands before running the event loop
    for speaker in speakers:
        engine.setProperty('voice', speaker['voice'])
        engine.save_to_file(speaker['text'], str(speaker['file']))
    
    # Run the event loop once to process all queued commands
    engine.runAndWait()
    engine.stop()

    audio_segments = []
    for speaker in speakers:
        segment = AudioSegment.from_file(speaker['file'])
        segment += 6 # Increase volume
        audio_segments.append(segment)
        os.remove(speaker['file'])

    silence = AudioSegment.silent(duration=500)
    combined_audio = audio_segments[0] + silence + audio_segments[1]

    output_file = output_path / "diarization_test.wav"
    combined_audio.export(output_file, format="wav")

    print(f"✓ Generated test audio file at: {os.path.abspath(output_file)}")
    print("  - First speaker: 0.0s - 5.0s")
    print("  - Second speaker: 5.5s - 10.5s")

    return str(output_file.resolve())

if __name__ == "__main__":
    generate_diarization_audio()
