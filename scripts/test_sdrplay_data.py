"""Verify real sdrplay data and PSD calculation for TUI compatibility."""
import sys
import numpy as np

try:
    from core.soapy_runtime import find_sdrplay_api_dll
    print("Imports OK.")
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

def test_data():
    from core.soapy_runtime import bootstrap_soapy
    status = bootstrap_soapy()
    print(f"Bootstrap completed. Devices found in bootstrap: {len(status.devices)}")
    print(f"SDRplay API DLL: {find_sdrplay_api_dll()}")
    
    from core.device import SDRDevice
    from core.dsp import average_psd
    
    dev = SDRDevice(driver="sdrplay")
    print("Opening device...")
    if not dev.open():
        print("Failed to open device.")
        return
    print(f"Device opened. Driver: {dev.driver}, Sample Rate: {dev.sample_rate}")
    
    try:
        print("Starting stream...")
        dev.start_stream()
        print("Stream started. Reading samples...")
        
        # Read a few chunks and calculate PSD
        for i in range(5):
            samples = dev.read_samples(4096)
            print(f"Chunk {i}: read {len(samples)} samples. dtype: {samples.dtype}")
            if len(samples) > 0:
                print(f"  First 5 samples: {samples[:5]}")
                print(f"  Min/Max/Mean magnitude: {np.min(np.abs(samples))}, {np.max(np.abs(samples))}, {np.mean(np.abs(samples))}")
                
                # PSD
                freqs, psd = average_psd(samples, fft_size=2048, sample_rate=dev.sample_rate)
                print(f"  PSD shape: {psd.shape}, min: {np.min(psd)}, max: {np.max(psd)}, nan_count: {np.isnan(psd).sum()}")
            else:
                print("  No samples received.")
    except Exception as e:
        print(f"Error during streaming/reading: {e}")
    finally:
        print("Closing device...")
        dev.close()
        print("Device closed.")

if __name__ == "__main__":
    test_data()
