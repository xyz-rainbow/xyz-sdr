"""List all soapy devices with bootstrapping."""
from core.soapy_runtime import bootstrap_soapy

status = bootstrap_soapy()
print(f"Bootstrap Status: sdrplay_api_ok={status.sdrplay_api_ok}, import_ok={status.import_ok}")
print(f"Devices found: {len(status.devices)}")
for i, d in enumerate(status.devices):
    print(f"Device {i}: {d}")

if status.import_ok:
    import SoapySDR
    print("\nListing directly from SoapySDR.Device.enumerate():")
    raw_devices = SoapySDR.Device.enumerate()
    print(f"Count: {len(raw_devices)}")
    for i, dev in enumerate(raw_devices):
        print(f"Raw Device {i}:")
        for k, v in dev.items():
            print(f"  {k} = {v}")
else:
    print("SoapySDR module not imported successfully.")
