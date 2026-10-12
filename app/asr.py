"""Automatic speech recognition pipeline using faster-whisper and ffmpeg.

PLAN.md §6:
- Normalizes incoming audio (iOS MP4/AAC, Chrome WebM/Opus) to 16 kHz mono WAV via ffmpeg.
- Transcribes using faster-whisper with VAD filter.
- initial_prompt (capped to ~224 tokens) for common items, hotwords for rarer trade terms.
"""
import os
import subprocess
import tempfile
from pathlib import Path
from app.config import settings

def normalize_audio_to_wav(input_path: Path, output_path: Path) -> Path:
    """Uses ffmpeg to convert any audio container to 16 kHz mono WAV."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(input_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path

class Transcriber:
    def __init__(self, model_size: str | None = None):
        self.model_size = model_size or settings.whisper_model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            # Lazy import faster_whisper to avoid startup overhead when testing without audio
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        initial_prompt: str = "Copper pipe 15mm, 22mm, geyser element, thermostat, callout fee, labour hours.",
        hotwords: str | None = "geyser, PEX, polycop, brass, compression fitting",
    ) -> str:
        """Transcribes audio file to plain text."""
        model = self._load_model()
        segments, _ = model.transcribe(
            str(audio_path),
            vad_filter=True,
            initial_prompt=initial_prompt,
            hotwords=hotwords,
            language="en",
        )
        return " ".join(seg.text.strip() for seg in segments)
