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

# ====================== Config ======================
SAMPLE_RATE       = 16000      # Whisper-friendly
CHANNELS          = 1          # Mono recommended
BLOCK_SECONDS     = 0.25       # Audio callback block size (lower -> lower latency)
CHUNK_SECONDS     = 3.0        # Main chunk length sent to API (2-4s is a good range)
OVERLAP_SECONDS   = 0.5        # Overlap between chunks to preserve context
MODEL             = "whisper-large-v3"
LANGUAGE          = "en"
PRINT_EMPTY       = False      # If True, prints even empty/silent results
INPUT_DEVICE      = None       # None = default device; or set device index/name (e.g., "Stereo Mix" on Windows)
LOG_DEVICES_ONCE  = False      # Set True to print devices list on start
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
    # indata shape: (frames, channels), dtype float32 in [-1, 1]
    if status:
        # xruns, overloads, etc.
        print("Audio status:", status)
    audio_q.put(indata.copy())

def start_input_stream():
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=frames_per_block,
        callback=audio_callback,
        device=INPUT_DEVICE,  # None uses default device
    )
    stream.start()
    return stream

def encode_wav_bytes(pcm_f32: np.ndarray) -> io.BytesIO:
    """
    Encode float32 mono PCM [-1,1] into 16-bit PCM WAV (in-memory).
    """
    if pcm_f32.ndim > 1:
        pcm_f32 = pcm_f32.reshape(-1)

    buf = io.BytesIO()
    # soundfile expects shape (nframes, channels)
    pcm_2d = pcm_f32.astype(np.float32).reshape(-1, 1)
    sf.write(buf, pcm_2d, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    buf.seek(0)
    # Give the buffer a 'name' so some SDKs can infer filename/mimetype
    if not hasattr(buf, "name"):
        buf.name = "chunk.wav"  # type: ignore[attr-defined]
    return buf

# -------- Smart de-duplication of overlap ----------
def _longest_overlap_suffix_prefix(prev_tail: str, new_text: str) -> int:
    """
    Find the longest overlap where the suffix of prev_tail equals the prefix of new_text.
    Returns the number of characters to skip from new_text.
    """
    max_k = min(len(prev_tail), len(new_text))
    for k in range(max_k, 0, -1):
        if prev_tail[-k:] == new_text[:k]:
            return k
    return 0

class LivePrinter:
    """
    Keeps a rolling tail of printed text and only prints the non-duplicate delta
    when overlap causes repeated words across chunks.
    """
    def __init__(self, tail_keep_chars: int = 200):
        self.tail_keep_chars = tail_keep_chars
        self._printed = ""   # full printed text (can grow large)
    
    def print_delta(self, new_text: str):
        new_text = (new_text or "").strip()
        if not new_text and not PRINT_EMPTY:
            return

        # Tail of previously printed text to compare
        prev_tail = self._printed[-self.tail_keep_chars:] if self._printed else ""
        skip = _longest_overlap_suffix_prefix(prev_tail, new_text)
        delta = new_text[skip:].strip()

        if delta:
            print(delta, flush=True)
            self._printed += (("\n" if self._printed and not self._printed.endswith("\n") else "") + delta)
# ---------------------------------------------------

def uploader_worker():
    """
    Accumulates audio blocks into a buffer, slices CHUNK_SECONDS with OVERLAP,
    sends to Groq, and prints de-duplicated results as they arrive.
    """
    chunk_idx = 0
    leftover = np.empty((0, CHANNELS), dtype=np.float32)
    printer = LivePrinter()

    print(f"Transcribing (chunked)… chunk={CHUNK_SECONDS:.1f}s, overlap={OVERLAP_SECONDS:.1f}s. Press Ctrl+C to stop.\n")
    while not stop_flag.is_set():
        # 1) Pull an audio block from the queue (or time out to check stop flag)
        try:
            block = audio_q.get(timeout=0.1)  # (frames, channels), float32
        except queue.Empty:
            continue

        # 2) Accumulate into a working buffer
        acc = block if leftover.size == 0 else np.concatenate([leftover, block], axis=0)

        # 3) While we have enough frames for a full chunk, slice and send
        while len(acc) >= frames_per_chunk:
            current = acc[:frames_per_chunk]  # full chunk
            # Keep overlap frames at the end for next iteration
            acc = acc[frames_per_chunk - frames_per_overlap:]

            # Flatten to mono and encode to WAV
            mono = current.flatten().astype(np.float32)
            wav_buf = encode_wav_bytes(mono)
            wav_buf.name = f"chunk_{chunk_idx}.wav"  # type: ignore[attr-defined]

            try:
                # Use "text" for the lowest-latency simple output
                resp_text = client.audio.transcriptions.create(
                    file=wav_buf,
                    model=MODEL,
                    language=LANGUAGE,
                    response_format="text",
                )
                text = resp_text if isinstance(resp_text, str) else getattr(resp_text, "text", "")
                if text.strip() or PRINT_EMPTY:
                    # Print only the delta (avoid duplicate overlap text)
                    print(f"[{chunk_idx:05d}] ", end="", flush=True)
                    printer.print_delta(text)
            except Exception as e:
                print(f"[{chunk_idx:05d}] Transcription error: {e}")

            chunk_idx += 1

        # 4) Save leftovers for the next loop
        leftover = acc

def main():
    if LOG_DEVICES_ONCE:
        list_devices()

    # Start audio capture
    stream = start_input_stream()

    # Start uploader/transcriber thread
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

if __name__ == "__main__":
    main()



# # from faster_whisper import WhisperModel

# # model_size = "small.en"

# # model = WhisperModel(model_size, device="cpu", compute_type="float32")

# # segments, info = model.transcribe("audio.mp3", language="en", beam_size=2)

# # for segment in segments:
# #     print(segment.text)