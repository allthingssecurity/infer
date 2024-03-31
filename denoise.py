import argparse
import torch
from df.enhance import enhance, init_df, load_audio, save_audio
from df.io import resample

def denoise_audio(input_audio_path: str, output_audio_path: str) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, df, _ = init_df("./DeepFilterNet2", config_allow_defaults=True)
    model = model.to(device=device).eval()
    sr = 48000  # Adjust based on your model's requirements
    sample, meta = load_audio(input_audio_path, sr)
    sample = sample.to(device)

    # Denoise the audio
    enhanced = enhance(model, df, sample)

    # Apply fading in to the start of the enhanced audio
    lim = torch.linspace(0.0, 1.0, int(sr * 0.15)).unsqueeze(0)
    lim = torch.cat((lim, torch.ones(1, enhanced.shape[1] - lim.shape[1])), dim=1)
    enhanced = enhanced * lim

    # Resample if necessary
    if meta.sample_rate != sr:
        enhanced = resample(enhanced, sr, meta.sample_rate)
        sr = meta.sample_rate

    # Save the denoised audio
    save_audio(output_audio_path, enhanced.cpu(), sr)
    print(f"Denoised audio saved to: {output_audio_path}")

def main():
    parser = argparse.ArgumentParser(description="Denoise audio files using DeepFilterNet.")
    parser.add_argument("input_audio_path", type=str, help="Path to the input audio file.")
    parser.add_argument("output_audio_path", type=str, help="Path for saving the denoised audio file.")
    
    args = parser.parse_args()
    denoise_audio(args.input_audio_path, args.output_audio_path)

if __name__ == "__main__":
    main()
