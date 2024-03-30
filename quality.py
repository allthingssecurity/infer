import os
import soundfile as sf
import pyloudnorm as pyln
import noisereduce as nr
import numpy as np


def adjust_loudness_and_denoise(audio_path, target_loudness=-23.0):
    """
    Adjust the loudness of an audio file to a target loudness level and denoise it.

    Parameters:
    - audio_path: Path to the input audio file.
    - target_loudness: Desired loudness level in LUFS. Default is -23.0 LUFS.

    Returns:
    - Path to the adjusted and denoised audio file.
    """
    # Load the audio file
    data, rate = sf.read(audio_path)
    
    # Perform noise reduction
    # Assuming the first 0.5 seconds of the audio can be considered as noise sample
    noise_sample = data[:int(rate*0.5)]
    data_denoised = nr.reduce_noise(audio_clip=data, noise_clip=noise_sample, verbose=False)
    
    # Measure the current loudness of the denoised audio
    meter = pyln.Meter(rate)  # create BS.1770 meter
    current_loudness = meter.integrated_loudness(data_denoised)

    # Calculate the required gain
    gain = target_loudness - current_loudness
    linear_gain = 10 ** (gain / 20)

    # Apply the gain
    data_adjusted = data_denoised * linear_gain

    # Construct the path for the adjusted audio file
    dir_name = os.path.dirname(audio_path)
    base_name, ext = os.path.splitext(os.path.basename(audio_path))
    adjusted_audio_path = os.path.join(dir_name, f"{base_name}_adjusted_denoised{ext}")

    # Save the adjusted audio file
    sf.write(adjusted_audio_path, data_adjusted, rate)

    return adjusted_audio_path




def adjust_loudness(audio_path, target_loudness=-23.0):
    """
    Adjust the loudness of an audio file to a target loudness level.

    Parameters:
    - audio_path: Path to the input audio file.
    - target_loudness: Desired loudness level in LUFS. Default is -23.0 LUFS.

    Returns:
    - Path to the adjusted audio file.
    """
    # Load the audio file
    data, rate = sf.read(audio_path)

    # Measure the current loudness
    meter = pyln.Meter(rate)  # create BS.1770 meter
    current_loudness = meter.integrated_loudness(data)

    # Calculate the required gain
    gain = target_loudness - current_loudness
    linear_gain = 10 ** (gain / 20)

    # Apply the gain
    data_adjusted = data * linear_gain

    # Construct the path for the adjusted audio file
    dir_name = os.path.dirname(audio_path)
    base_name, ext = os.path.splitext(os.path.basename(audio_path))
    adjusted_audio_path = os.path.join(dir_name, f"{base_name}_adjusted{ext}")

    # Save the adjusted audio file
    sf.write(adjusted_audio_path, data_adjusted, rate)

    return adjusted_audio_path

