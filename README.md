# moonraker-plr

Get a Klipper print going again after the printer board (MCU) dropped off USB.

Klipper has no power-loss recovery. When the host loses the connection to the
MCU ("Lost communication with MCU"), the MCU switches its heaters off, the bed
cools and the part lets go. This adds three things:

1. **A Moonraker component** (`plr_watchdog`) that notices the connection loss,
   waits until the MCU's serial device is back, issues `FIRMWARE_RESTART`, and
   as soon as Klippy is ready heats the **bed** back to the print's temperature.
   The nozzle stays off: it is still sitting on the part.
2. **Klipper macros** (`plr.cfg`) that save a resume point on every layer and
   resume from it: home, purge outside the print area, continue from the saved
   position in the G-code file.
3. **A prompt** on Mainsail and KlipperScreen after the restart:
   *Interrupted print – Resume / Forget*.

It only acts on connection problems. Any other shutdown (thermal runaway,
heater verification, ADC out of range, ...) is left alone: that needs a human.

## How it works

```
print running ──► PLR_SAVE on every layer change ──► variables.cfg
       │
  USB drops ──► Klippy shutdown "Lost communication with MCU"
       │
plr_watchdog ──► waits for /dev/serial/by-id/... ──► FIRMWARE_RESTART
       │
Klippy ready ──► PLR_HOLD_BED (bed back to temperature, max 2 h)
       │      └► PLR_CHECK prompt: Resume / Forget
       │
RESUME_INTERRUPTED ──► G28 ──► heat ──► purge ──► M23 / M26 <pos> / M24
```

## Install

```bash
cd ~
git clone https://github.com/JansenDevelopment/moonraker-plr.git
~/moonraker-plr/install.sh
```

`install.sh` links `plr_watchdog.py` into Moonraker's components and `plr.cfg`
into your config directory. It does not touch your config files.

### moonraker.conf

```ini
[plr_watchdog]
# the serial path from the [mcu] section of printer.cfg
mcu_path: /dev/serial/by-id/usb-1a86_USB_Serial-if00-port0
#hold_gcode: PLR_HOLD_BED
#settle_time: 3        # s to wait after the device reappears
#ready_timeout: 30     # s to wait for Klippy ready after a restart
#max_wait: 1800        # s to keep trying before giving up

[update_manager plr]
type: git_repo
primary_branch: main
path: ~/moonraker-plr
origin: https://github.com/JansenDevelopment/moonraker-plr.git
managed_services: klipper moonraker
```

### printer.cfg

```ini
[include plr.cfg]

# optional: adjust to your machine
[gcode_macro _PLR_SETTINGS]
variable_purge_y: 228          # outside the print area
variable_purge_x_start: 10
variable_purge_x_end: 200
variable_purge_e: 15
variable_hold_minutes: 120
variable_idle_timeout: 600
gcode:
```

Clear the resume point when a print ends normally, e.g. at the end of your
`END_PRINT` macro:

```
SAVE_VARIABLE VARIABLE=plr VALUE="{}"
```

With Mainsail's `CANCEL_PRINT`, clear it on cancel too:

```ini
[gcode_macro _CLIENT_VARIABLE]
variable_user_cancel_macro: "_PLR_CLEAR"
gcode:
```

### Slicer

Add to the layer-change G-code, **only after** the macros are loaded (an
unknown command aborts the print):

| slicer | setting | value |
|---|---|---|
| PrusaSlicer / SuperSlicer | After layer change G-code | `PLR_SAVE Z=[layer_z]` |
| OrcaSlicer | Layer change G-code | `PLR_SAVE Z=[layer_z]` |

## Before you rely on it

- **Your homing must not hit the part.** `RESUME_INTERRUPTED` runs `G28` with a
  part on the bed. Make sure your Z homing happens outside the print area
  (e.g. a `homing_override` that lowers Z beside the bed) and that it does not
  travel back over the bed at a low height afterwards.
- **The purge line must be outside the print area**, and move along X only.
- **Cut off the blob** the nozzle left where it stopped. The first move after
  resuming travels over the part at layer height.
- **Test it** with a short print: pull the USB cable halfway, plug it back in,
  and watch the whole chain before trusting a long print to it.

The resume starts at the beginning of the interrupted layer, so expect a
visible seam at that height.

## Status endpoint

`GET /server/plr_watchdog/status` → `mcu_path`, `mcu_present`, `recovering`,
`last_event`.

## License

GPL-3.0-or-later, like Moonraker and Klipper.
