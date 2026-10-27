
from datetime import datetime
from pathlib import Path

import soundfile as sf
import torch
from transformers import AutoModel, AutoProcessor


# Model configuration
MODEL_ID = "Audio8/Audio8-TTS-Preview-0.1b"
DEVICE = "cpu"
OUTPUT_DIR = "./cloned/"


def load_model():
    """Load the voice-cloning model using the CPU only."""

    print(f"Loading model: {MODEL_ID}")
    print("Device: CPU")
    print("The first load may take several minutes.")

    processor = AutoProcessor.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
    )

    model = AutoModel.from_pretrained(
        MODEL_ID,
        trust_remote_code=True,
        dtype=torch.float32,
    )

    model = model.to(DEVICE)
    model.eval()

    print("Model loaded successfully.")

    return processor, model


processor, model = load_model()


def clone_audio(
    ref_audio: str,
    ref_text: str,
    speech_to_generate: str
) -> str:

    print(f"Reference audio: {ref_audio}")
    print("Generating speech on CPU. Please wait...")

    inputs = processor(
        text=[speech_to_generate],
        reference_audio=[str(ref_audio)],
        reference_text=[ref_text],
        return_tensors="pt",
    )

    inputs = {
        name: value.to(DEVICE) if hasattr(value, "to") else value
        for name, value in inputs.items()
    }

    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=512,
            temperature=0.7,
            top_p=0.9,
            top_k=50,
            do_sample=True,
            return_dict_in_generate=True,
        )

        waveforms, waveform_lengths = model.decode_audio(output.codes)

    audio = (
        waveforms[0, :int(waveform_lengths[0])]
        .float()
        .cpu()
        .numpy()
    )

    sample_rate = model.config.codec_sample_rate

    output_dir = Path(__file__).resolve().parent / "cloned"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "cloned.wav"

    sf.write(
        str(output_path),
        audio,
        sample_rate,
    )

    output_path = output_path.resolve()

    print(f"Generated audio saved to: {output_path}")

    return str(output_path)


if __name__ == "__main__":
    reference_audio = "try.mp3"

    reference_text = (
        "Hello, this is an example of speech synthesis in english"
    )

    text_to_generate = (
        "Hello! This is a test of my cloned voice."
    )

    generated_path = clone_audio(
        ref_audio=reference_audio,
        ref_text=reference_text,
        speech_to_generate=text_to_generate,
    )

    print(f"Output path: {generated_path}")
