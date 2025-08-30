from datetime import datetime

def generate_human_readable_timestamp() -> str:
    """
    Generate a human-readable timestamp for file naming.
    Format: 28_aug_2025_07_00_pm
    """
    now = datetime.now()
    
    # Format: day_month_year_hour_minute_am/pm
    day = now.strftime("%d")
    month = now.strftime("%b").lower()
    year = now.strftime("%Y")
    time = now.strftime("%I_%M_%p").lower()
    
    return f"{day}_{month}_{year}_{time}"

def generate_transcription_filename(timestamp: str) -> str:
    """
    Generate a filename for transcription output.
    Format: transcribed_28_aug_2025_07_00_pm.md
    """
    return f"transcribed_{timestamp}.md"

def generate_meeting_notes_filename(timestamp: str) -> str:
    """
    Generate a filename for meeting notes output.
    Format: meeting_notes_28_aug_2025_07_00_pm.md
    """
    return f"meeting_notes_{timestamp}.md"
