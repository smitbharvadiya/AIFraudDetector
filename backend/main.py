import os
import io
import time
import queue
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd
import soundfile as sf
from groq import Groq
from dotenv import load_dotenv
from faster_whisper import WhisperModel
from fraudIntent import detect_intent   # <-- fraud detection added

# ====================== Config ======================
SAMPLE_RATE       = 16000
CHANNELS          = 1
BLOCK_SECONDS     = 0.25
CHUNK_SECONDS     = 3.0
OVERLAP_SECONDS   = 0.5
MODEL             = "whisper-large-v3"
LANGUAGE          = "en"
PRINT_EMPTY       = False
INPUT_DEVICE      = None
LOG_DEVICES_ONCE  = False
# ====================================================

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))
if not os.getenv("GROQ_API_KEY"):
    raise RuntimeError("Missing GROQ_API_KEY. Put it in .env or your environment.")

frames_per_block   = int(SAMPLE_RATE * BLOCK_SECONDS)
frames_per_chunk   = int(SAMPLE_RATE * CHUNK_SECONDS)
frames_per_overlap = int(SAMPLE_RATE * OVERLAP_SECONDS)

audio_q: "queue.Queue[np.ndarray]" = queue.Queue()
stop_flag = threading.Event()

@dataclass
class Chunk:
    idx: int
    pcm: np.ndarray  # float32 [-1, 1], mono

def list_devices():
    print("\n=== Audio Devices ===")
    print(sd.query_devices())
    print("=====================\n")

def audio_callback(indata, frames, time_info, status):
    if status:
        print("Audio status:", status)
    audio_q.put(indata.copy())

def start_input_stream():
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=frames_per_block,
        callback=audio_callback,
        device=INPUT_DEVICE,
    )
    stream.start()
    return stream

def encode_wav_bytes(pcm_f32: np.ndarray) -> io.BytesIO:
    if pcm_f32.ndim > 1:
        pcm_f32 = pcm_f32.reshape(-1)

    buf = io.BytesIO()
    pcm_2d = pcm_f32.astype(np.float32).reshape(-1, 1)
    sf.write(buf, pcm_2d, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    buf.seek(0)
    buf.name = "chunk.wav"  # type: ignore[attr-defined]
    return buf

# -------- Smart de-duplication ----------
def _longest_overlap_suffix_prefix(prev_tail: str, new_text: str) -> int:
    max_k = min(len(prev_tail), len(new_text))
    for k in range(max_k, 0, -1):
        if prev_tail[-k:] == new_text[:k]:
            return k
    return 0

class LivePrinter:
    def __init__(self, tail_keep_chars: int = 200):
        self.tail_keep_chars = tail_keep_chars
        self._printed = ""   
    
    def print_delta(self, new_text: str):
        new_text = (new_text or "").strip()
        if not new_text and not PRINT_EMPTY:
            return

        prev_tail = self._printed[-self.tail_keep_chars:] if self._printed else ""
        skip = _longest_overlap_suffix_prefix(prev_tail, new_text)
        delta = new_text[skip:].strip()

        if delta:
            print(delta, flush=True)
            # ---- Fraud detection integration ----
            result = detect_intent(delta)
            if result["rule_score"] > 0:
                print("   🚨 Fraud Alert:", result)
            # -------------------------------------
            self._printed += (("\n" if self._printed and not self._printed.endswith("\n") else "") + delta)
# ---------------------------------------------------

def uploader_worker():
    chunk_idx = 0
    leftover = np.empty((0, CHANNELS), dtype=np.float32)
    printer = LivePrinter()

    print(f"Transcribing (chunked)… chunk={CHUNK_SECONDS:.1f}s, overlap={OVERLAP_SECONDS:.1f}s. Press Ctrl+C to stop.\n")
    while not stop_flag.is_set():
        try:
            block = audio_q.get(timeout=0.1)
        except queue.Empty:
            continue

        acc = block if leftover.size == 0 else np.concatenate([leftover, block], axis=0)

        while len(acc) >= frames_per_chunk:
            current = acc[:frames_per_chunk]
            acc = acc[frames_per_chunk - frames_per_overlap:]

            mono = current.flatten().astype(np.float32)
            wav_buf = encode_wav_bytes(mono)
            wav_buf.name = f"chunk_{chunk_idx}.wav"  # type: ignore[attr-defined]

            try:
                resp_text = client.audio.transcriptions.create(
                    file=wav_buf,
                    model=MODEL,
                    language=LANGUAGE,
                    response_format="text",
                )
                text = resp_text if isinstance(resp_text, str) else getattr(resp_text, "text", "")
                if text.strip() or PRINT_EMPTY:
                    print(f"[{chunk_idx:05d}] ", end="", flush=True)
                    printer.print_delta(text)
            except Exception as e:
                print(f"[{chunk_idx:05d}] Transcription error: {e}")

            chunk_idx += 1
        leftover = acc

def transcribe_live():
    if LOG_DEVICES_ONCE:
        list_devices()
    stream = start_input_stream()
    t = threading.Thread(target=uploader_worker, daemon=True)
    t.start()
    try:
        while True:
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        stop_flag.set()
        stream.stop()
        stream.close()

# ------------------ AUDIO FILE -------------------
def transcribe_file(file_path: str):
    model_size = "small.en"
    model = WhisperModel(model_size, device="cpu", compute_type="float32")
    segments, info = model.transcribe(file_path, language="en", beam_size=2)

    print(f"\n🔎 Processing file: {file_path}")
    for segment in segments:
        text = segment.text.strip()
        if text:
            print(">>", text)
            result = detect_intent(text)
            if result["rule_score"] > 0:
                print("   🚨 Fraud Alert:", result)

# ------------------ MAIN -------------------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, help="Path to audio file")
    parser.add_argument("--live", action="store_true", help="Enable live mic transcription")
    args = parser.parse_args()

    if args.file:
        transcribe_file(args.file)
    elif args.live:
        transcribe_live()
    else:
        print("Usage:")
        print("   python transcribe.py --file audio.mp3")
        print("   python transcribe.py --live")
