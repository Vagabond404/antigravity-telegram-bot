"""
audio_transcriber.py - High-Reliability Audio & Voice Note Transcriber
Converts and transcribes Telegram voice notes (.ogg Opus) and audio files (.mp3, .m4a, .wav)
using pure Python soundfile and SpeechRecognition (Google Speech Recognition engine)
with automatic 25s chunking for long recordings, language fallbacks, and zero external binary dependencies.
"""

import io
import logging
from pathlib import Path
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger("audio_transcriber")

# Map short codes to SpeechRecognition Google locale tags
LANG_TO_GOOGLE_LOCALE = {
    "en": "en-US",
    "fr": "fr-FR",
    "es": "es-ES",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-BR",
    "ru": "ru-RU",
    "ja": "ja-JP",
    "zh": "zh-CN",
    "ar": "ar-SA",
}


def _transcribe_chunk_with_fallback(
    recognizer,
    audio_obj,
    primary_locale: str,
    fallback_locale: Optional[str] = None
) -> Tuple[str, str]:
    """Transcribe an AudioData chunk trying primary locale, then fallback locale if silence/unrecognized."""
    try:
        text = recognizer.recognize_google(audio_obj, language=primary_locale)
        if text and text.strip():
            return text.strip(), primary_locale
    except Exception as e:
        logger.debug(f"Primary locale ({primary_locale}) failed: {e}")

    if fallback_locale and fallback_locale != primary_locale:
        try:
            text = recognizer.recognize_google(audio_obj, language=fallback_locale)
            if text and text.strip():
                return text.strip(), fallback_locale
        except Exception as e:
            logger.debug(f"Fallback locale ({fallback_locale}) failed: {e}")

    return "", primary_locale


def transcribe_audio_file(
    file_path: Path,
    preferred_lang: str = "en",
    chunk_seconds: float = 25.0
) -> Tuple[str, str]:
    """
    Transcribe a local audio or voice file.
    Returns: (transcribed_text, detected_locale)
    """
    path = Path(file_path)
    if not path.is_file():
        return "", "en-US"

    try:
        import soundfile as sf
        import speech_recognition as sr
    except ImportError as e:
        logger.error(f"Missing required audio library: {e}")
        return "", "en-US"

    try:
        data, samplerate = sf.read(str(path))
    except Exception as e:
        logger.error(f"soundfile failed to read {path}: {e}")
        # Try fallback using ffmpeg CLI if installed
        try:
            import subprocess
            wav_tmp = path.with_suffix(".temp.wav")
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", str(wav_tmp)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            data, samplerate = sf.read(str(wav_tmp))
            wav_tmp.unlink(missing_ok=True)
        except Exception as ex2:
            logger.error(f"ffmpeg conversion fallback also failed: {ex2}")
            return "", "en-US"

    # Convert stereo/multi-channel to mono
    if len(data.shape) > 1:
        data = np.mean(data, axis=1)

    total_samples = len(data)
    duration_secs = total_samples / float(samplerate)
    logger.info(f"Loaded audio {path.name}: {duration_secs:.2f}s, {samplerate}Hz")

    primary_locale = LANG_TO_GOOGLE_LOCALE.get((preferred_lang or "en").lower().strip(), "en-US")
    fallback_locale = "fr-FR" if primary_locale == "en-US" else "en-US"

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    chunk_samples = int(chunk_seconds * samplerate)
    if chunk_samples <= 0:
        chunk_samples = total_samples

    chunks = [data[i:i + chunk_samples] for i in range(0, total_samples, chunk_samples)]
    transcribed_segments = []
    effective_locale = primary_locale

    for idx, chunk in enumerate(chunks):
        if len(chunk) < int(0.5 * samplerate):
            continue  # Ignore fragments smaller than 0.5s

        buf = io.BytesIO()
        try:
            sf.write(buf, chunk, samplerate, format="WAV", subtype="PCM_16")
            buf.seek(0)
            with sr.AudioFile(buf) as source:
                aud = recognizer.record(source)
                txt, used_loc = _transcribe_chunk_with_fallback(
                    recognizer,
                    aud,
                    primary_locale=effective_locale,
                    fallback_locale=fallback_locale if idx == 0 else None
                )
                if txt:
                    transcribed_segments.append(txt)
                    if idx == 0:
                        effective_locale = used_loc
        except Exception as ce:
            logger.debug(f"Chunk {idx} processing notice: {ce}")

    full_text = " ".join(transcribed_segments).strip()
    return full_text, effective_locale
