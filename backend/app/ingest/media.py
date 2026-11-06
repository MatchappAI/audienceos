"""Local media processing: FFmpeg (bundled) for audio extraction and frame sampling, faster-whisper for transcription.

Nothing here touches the network except the one-time Whisper model download (cached in runtime/whisper).
"""
import json
import logging
import re
import subprocess
from pathlib import Path

from .. import config, settings_store

log = logging.getLogger("audienceos.media")
_whisper_cache: dict[str, object] = {}


def ffmpeg_exe() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe_duration(path: Path) -> float | None:
    # ffmpeg -i prints duration on stderr; avoids needing a separate ffprobe binary.
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", p.stderr)
    if not m:
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def has_audio_stream(path: Path) -> bool:
    p = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=60)
    return "Audio:" in p.stderr


def extract_audio(src: Path, dest: Path) -> Path:
    """Convert any audio/video into 16 kHz mono WAV for Whisper."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
           "-f", "wav", str(dest)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if p.returncode != 0 or not dest.exists():
        raise RuntimeError(f"Could not extract audio: {p.stderr.strip()[:300] or 'unknown FFmpeg error'}")
    return dest


def sample_frames(src: Path, out_dir: Path, duration: float | None) -> list[tuple[float, Path]]:
    """Take a small number of evenly spaced frames (max MAX_FRAMES_PER_VIDEO) to avoid wasted compute."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if not duration or duration <= 0:
        duration = 10.0
    n = max(1, min(config.MAX_FRAMES_PER_VIDEO, int(duration // 20) + 1))
    frames = []
    for i in range(n):
        t = duration * (i + 0.5) / n
        dest = out_dir / f"frame_{i:02d}.jpg"
        cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src),
               "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(dest)]
        p = subprocess.run(cmd, capture_output=True, timeout=120)
        if p.returncode == 0 and dest.exists():
            frames.append((round(t, 1), dest))
    return frames


def _model():
    name = settings_store.get("whisper_model") or "base"
    if name not in _whisper_cache:
        from faster_whisper import WhisperModel
        _whisper_cache[name] = WhisperModel(name, device="cpu", compute_type="int8",
                                            download_root=str(config.WHISPER_DIR))
    return name, _whisper_cache[name]


def transcribe(wav: Path, progress=None) -> dict:
    import wave

    import numpy as np
    name, model = _model()
    # Decode our own 16 kHz mono WAV (avoids depending on PyAV's file decoding).
    with wave.open(str(wav), "rb") as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segments, info = model.transcribe(audio, vad_filter=True, beam_size=1)
    out, texts = [], []
    total = info.duration or 1
    for s in segments:
        out.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
        texts.append(s.text.strip())
        if progress:
            progress(min(0.99, s.end / total))
    return {"engine": f"faster-whisper {name} (local)", "language": info.language,
            "text": " ".join(texts).strip(), "segments": out, "duration": info.duration}


def fmt_ts(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def transcript_with_timestamps(segments: list[dict]) -> str:
    return "\n".join(f"[{fmt_ts(s['start'])}] {s['text']}" for s in segments)


def whisper_ready() -> bool:
    name = settings_store.get("whisper_model") or "base"
    return any(config.WHISPER_DIR.glob(f"models--Systran--faster-whisper-{name}"))


def status() -> dict:
    try:
        exe = ffmpeg_exe()
    except Exception as e:  # pragma: no cover
        return {"ffmpeg": False, "ffmpeg_error": str(e), "whisper_model_downloaded": whisper_ready()}
    return {"ffmpeg": Path(exe).exists(), "whisper_model": settings_store.get("whisper_model"),
            "whisper_model_downloaded": whisper_ready()}


def frames_json(frames) -> str:
    return json.dumps([{"t": t, "path": str(p)} for t, p in frames])
