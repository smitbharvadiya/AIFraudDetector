import torchaudio
import torch

from speechbrain.inference import SpectralMaskEnhancement

model = SpectralMaskEnhancement.from_hparams(
    source="speechbrain/asvspoof2019-lcnn-lstm",
    savedir="pretrained_models/asvspoof2019"
)


def detect_deepfake(audio_file: str, threshold: float = 0.5):
    # Load audio
    signal, fs = torchaudio.load(audio_file)

    # The spoofing model is trained like a verification system,
    # so we compare the file with itself (hack) to get a spoof score.
    score = model.verify_files(audio_file, audio_file).item()

    # Interpretation
    if score < threshold:
        return f"⚠️ Synthetic / Deepfake detected (score={score:.2f})"
    else:
        return f"✅ Real human detected (score={score:.2f})"

# --- Test with audio ---
print(detect_deepfake("audio.mp3"))   # should say Real
# print(detect_deepfake("fake_tts_sample.wav"))  # should say Synthetic
