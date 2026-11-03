"""Copy to CIRCUITPY root; power-cycle after changing USB descriptors."""
import usb_cdc
import usb_hid

usb_cdc.enable(console=True, data=True)
usb_hid.enable((usb_hid.Device.MOUSE,))
