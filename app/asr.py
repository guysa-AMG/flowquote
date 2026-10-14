"""Automatic speech recognition pipeline using faster-whisper and ffmpeg.

PLAN.md §6:
- Normalizes incoming audio (iOS MP4/AAC, Chrome WebM/Opus) to 16 kHz mono WAV via ffmpeg.
- Transcribes using faster-whisper with VAD filter.
- initial_prompt (capped to ~224 tokens) for common items, hotwords for rarer trade terms.
"""
import subprocess
from pathlib import Path

from app.config import settings

DEFAULT_INITIAL_PROMPT = (
    "Copper pipe 15mm, 22mm, geyser element, thermostat, callout fee, labour hours."
)
DEFAULT_HOTWORDS = "geyser, PEX, polycop, brass, compression fitting"


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
        configured_model = settings.whisper_model_path
        self.model_size = (
            str(configured_model)
            if configured_model
            else (model_size or settings.whisper_model_size)
        )
        self._model = None

    def _load_model(self):
        if self._model is None:
            # Lazy import faster_whisper to avoid startup overhead when testing without audio
            from faster_whisper import WhisperModel
            size_ok = Path(self.model_size).is_dir()
            if (
                settings.whisper_local_files_only
                and settings.whisper_model_path
                and not size_ok
            ):
                raise FileNotFoundError(
                    "Whisper weights are not installed locally. Provision model files before "
                    "starting the offline pipeline."
                )
            self._model = WhisperModel(
                self.model_size,
                device="cpu",
                compute_type="int8",
                local_files_only=settings.whisper_local_files_only,
            )
        return self._model

    def transcribe(
        self,
        audio_path: Path,
        initial_prompt: str = DEFAULT_INITIAL_PROMPT,
        hotwords: str | None = DEFAULT_HOTWORDS,
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
