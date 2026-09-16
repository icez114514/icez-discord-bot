"""Offline asset build with an existing Irodori-TTS checkout, never a game runtime dependency.

Run with that checkout's Python environment and ffmpeg on PATH:
  python generate_action_voice.py --tts-root PATH --reference GREETING.wav
"""

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tts-root", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    args = parser.parse_args()
    root, reference = args.tts_root.resolve(), args.reference.resolve(strict=True)
    os.environ["HF_HOME"] = str(root / ".cache/huggingface")
    os.environ["TORCH_HOME"] = str(root / ".cache/torch")
    os.environ["HF_HUB_OFFLINE"] = "1"
    sys.path.insert(0, str(root))
    from irodori_tts.inference_runtime import (
        InferenceRuntime, RuntimeKey, SamplingRequest, download_hf_checkpoint, save_wav,
    )
    model = download_hf_checkpoint("Aratako/Irodori-TTS-v4.1-Small")
    runtime = InferenceRuntime.from_key(RuntimeKey(
        checkpoint=model, model_device="cuda", model_precision="bf16", codec_device="cuda",
    ))
    output = Path(__file__).resolve().parents[1] / "public/assets/audio"
    cues = [
        ("call", "コール。"), ("bet", "ベット。"), ("fold", "フォールド。"),
        ("check", "チェック。"), ("raise", "レイズ。"), ("allin", "オールイン。"),
    ]
    with tempfile.TemporaryDirectory() as directory:
        for index, (name, text) in enumerate(cues):
            result = runtime.synthesize(SamplingRequest(
                text=text, ref_wav=str(reference), seed=260923 if name == "allin" else 260916 + index,
                max_ref_seconds=12, duration_scale=0.85,
            ), log_fn=None)
            wav = Path(directory) / (name + ".wav")
            save_wav(str(wav), result.audio, result.sample_rate)
            subprocess.run([
                "ffmpeg", "-y", "-v", "error", "-i", str(wav), "-af",
                "silenceremove=start_periods=1:start_threshold=-48dB:start_silence=0.02,loudnorm=I=-18:TP=-2:LRA=7",
                "-ar", "48000", "-ac", "1", "-c:a", "libvorbis", "-q:a", "5",
                str(output / ("voice-" + name + ".ogg")),
            ], check=True)
            print("Generated " + name, flush=True)


if __name__ == "__main__":
    main()
