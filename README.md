# ASU IP Manager

> Compact always-on-top IP address manager for industrial automation engineers (SCADA / PLC / HMI / Modbus / OPC-UA)

![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python)
![CustomTkinter](https://img.shields.io/badge/UI-CustomTkinter-darkblue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey?logo=windows)
![License](https://img.shields.io/badge/License-MIT-green)

---

## What it does

When working with industrial equipment you constantly switch between different IP subnets and need to remember dozens of device addresses. This tool solves that:

- Lives as a **small bar in the corner of your screen**, always visible on top of other windows
- Click the arrow to **expand** the panel with all your devices
- Click away and it **collapses** back to the bar
- **Real ICMP ping** — not a browser trick, actual network check
- **One click to connect** — opens browser, VNC Viewer, RDP, SSH, PuTTY automatically
- **Subnet switcher** — changes your network adapter IP to match the device subnet (requires admin rights)

---

## Screenshots

| Collapsed bar | Expanded panel |
|---|---|
| Small bar always on top | Full device list with status |

---

## Requirements

- Windows 10 / 11
- Python 3.10 or newer — [Download](https://www.python.org/downloads/)
  - During install: check **"Add Python to PATH"**

---

## Installation

**Step 1** — Download or clone this repository:
```
git clone https://github.com/nagimAlmir/ASU-IP-Manager.git
```

**Step 2** — Put both files in the same folder:
```
ASU_Manager/
    ASU_Manager_v6.py
    SETUP_ASU_v6.bat
```

**Step 3** — Run `SETUP_ASU_v6.bat`

It will automatically:
- Check Python installation
- Install `ping3` and `customtkinter`
- Create a desktop shortcut
- Ask if you want to launch now

---

## Manual launch

```bash
pip install ping3 customtkinter
python ASU_Manager_v6.py
```

---

## Features

| Feature | Description |
|---|---|
| Real ping | ICMP ping via `ping3`, fallback to TCP |
| Device types | PLC, HMI, SCADA, Modbus, OPC-UA, Switch, Camera |
| Protocols | HTTP, HTTPS, VNC, RDP, SSH, Telnet, FTP, Modbus TCP, OPC-UA |
| Auto-ping | Automatic polling every 30s / 1m / 2m / 5m / 10m |
| Notifications | Windows toast when device goes offline or comes back |
| History | Stores last 300 ping results per device |
| Subnet switch | Changes network adapter IP via `netsh` (admin required) |
| Export / Import | JSON and CSV format |
| Groups | Group devices by location / workshop |

---

## Subnet switching

To automatically change your network adapter IP when connecting to a device:

1. Run the app **as Administrator**
2. Click the 🌐 button on any device card
3. Select your network adapter
4. Confirm the new IP — app changes it and connects automatically

---

## Files

| File | Purpose |
|---|---|
| `ASU_Manager_v6.py` | Main application |
| `SETUP_ASU_v6.bat` | Installer — run once |
| `asu_devices.json` | Your saved devices (auto-created) |
| `asu_history.json` | Ping history (auto-created) |

---

## Built with

- [Python 3](https://www.python.org/)
- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) — modern UI
- [ping3](https://github.com/kyan001/ping3) — ICMP ping

---

## License

MIT — free to use and modify
