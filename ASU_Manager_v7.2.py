"""
АСУ ТП — IP Менеджер v6
CustomTkinter: скругления, тёмная тема, современный дизайн
pip install customtkinter ping3
"""
import customtkinter as ctk
from tkinter import messagebox, filedialog
import tkinter as tk
import json, csv, os, subprocess, platform
import threading, time, socket, datetime, webbrowser, collections, ctypes, ipaddress

try:
    import ping3; PING3_OK = True
except ImportError:
    PING3_OK = False

# ── Настройки CTk ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

APP_TITLE  = "АСУ ТП"
APP_VER    = "v7.2"
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_FILE  = os.path.join(BASE_DIR, "asu_devices.json")
HIST_FILE  = os.path.join(BASE_DIR, "asu_history.json")
PING_TOUT  = 1.5
TAB_H      = 38
PANEL_W    = 360
PANEL_H    = 560
AUTO_IV    = {"Off":0,"30s":30,"1m":60,"2m":120,"5m":300,"10m":600}

PROTO_PORTS = {"http":80,"https":443,"modbus-tcp":502,"opc-ua":4840,
               "vnc":5900,"rdp":3389,"ssh":22,"telnet":23,"ftp":21}
TYPE_LABELS = {"plc":"ПЛК","hmi":"HMI","scada":"SCADA","modbus":"Modbus",
               "opcua":"OPC-UA","switch":"Коммутатор","camera":"Камера","other":"Прочее"}

# ── Цвета ─────────────────────────────────────────────────────────────────────
C = {
    "bg":      "#252525",   # основной фон — тёмно-серый
    "bg2":     "#2e2e2e",   # карточки
    "bg3":     "#383838",   # кнопки hover
    "card":    "#333333",   # карточки устройств
    "border":  "#444444",   # границы
    "text":    "#ffffff",   # белый текст
    "text2":   "#aaaaaa",   # серый второстепенный
    "text3":   "#666666",   # слабый серый
    "accent":  "#ff4444",   # красный акцент
    "green":   "#2ecc71",   # онлайн — зелёный
    "red":     "#ff4444",   # офлайн — красный
    "amber":   "#f5a623",   # жёлтый/оранжевый
    "purple":  "#f5a623",   # HMI — жёлтый
    "teal":    "#ff6b6b",   # SCADA — светло-красный
    "modbus":  "#2ecc71",   # Modbus — зелёный
    "opcua":   "#f5a623",   # OPC-UA — жёлтый
    "tab":     "#1a1a1a",   # полоска — почти чёрная
    "tab_text":"#ffffff",
}
TYPE_COLORS = {
    "plc":C["accent"],"hmi":C["purple"],"scada":C["teal"],
    "modbus":C["modbus"],"opcua":C["opcua"],"switch":C["text2"],
    "camera":C["amber"],"other":C["text3"],
}

# ── Пинг ──────────────────────────────────────────────────────────────────────
def tcp_ping(ip, port, timeout=PING_TOUT):
    try:
        s = socket.socket(); s.settimeout(timeout); t = time.time()
        s.connect((ip, int(port))); s.close()
        return True, int((time.time()-t)*1000)
    except: return False, None

def icmp_ping(ip, timeout=PING_TOUT):
    if not PING3_OK: return None, None
    try:
        r = ping3.ping(ip, timeout=timeout, unit="ms")
        return (True, int(r)) if r and r is not False else (False, None)
    except: return None, None

def check_host(ip, port):
    ok, ms = icmp_ping(ip)
    if ok is None: ok, ms = tcp_ping(ip, port)
    return ok, ms

# ── История ───────────────────────────────────────────────────────────────────
class HistoryStore:
    MAX = 300
    def __init__(self):
        self._d = {}
        if os.path.exists(HIST_FILE):
            try:
                for k,v in json.load(open(HIST_FILE,encoding="utf-8")).items():
                    self._d[k] = collections.deque(v, maxlen=self.MAX)
            except: pass
    def save(self):
        try: json.dump({k:list(v) for k,v in self._d.items()},
                       open(HIST_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        except: pass
    def add(self, did, status, ms):
        k = str(did)
        if k not in self._d: self._d[k] = collections.deque(maxlen=self.MAX)
        self._d[k].append({"ts":datetime.datetime.now().strftime("%d.%m %H:%M:%S"),
                            "status":status,"ms":ms})
    def get(self, did, n=100):
        return list(self._d.get(str(did),[]))[-n:]

HISTORY = HistoryStore()

# ── Уведомления ───────────────────────────────────────────────────────────────
def notify(title, msg):
    try:
        if platform.system() == "Windows":
            ps = (f'[Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,'
                  f'ContentType=WindowsRuntime]|Out-Null\n'
                  f'$t=[Windows.UI.Notifications.ToastTemplateType]::ToastText02\n'
                  f'$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent($t)\n'
                  f'$x.GetElementsByTagName("text")[0].AppendChild($x.CreateTextNode("{title}"))|Out-Null\n'
                  f'$x.GetElementsByTagName("text")[1].AppendChild($x.CreateTextNode("{msg}"))|Out-Null\n'
                  f'$n=[Windows.UI.Notifications.ToastNotification]::new($x)\n'
                  f'[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("IP ASU").Show($n)')
            subprocess.Popen(["powershell","-WindowStyle","Hidden","-Command",ps],
                             creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    except: pass

# ── Права и смена IP ──────────────────────────────────────────────────────────
def is_admin():
    try: return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except: return False

def get_adapters():
    """
    Возвращает ВСЕ сетевые адаптеры включая без IP.
    Используем PowerShell Get-NetAdapter — показывает все интерфейсы.
    """
    result = []

    # Способ 1: PowerShell — все адаптеры включая без IP
    try:
        ps = (
            "Get-NetAdapter | "
            "ForEach-Object {"
            "    $name = $_.Name;"
            "    $ip = (Get-NetIPAddress -InterfaceIndex $_.ifIndex "
            "           -AddressFamily IPv4 -ErrorAction SilentlyContinue"
            "           | Select-Object -First 1 -ExpandProperty IPAddress);"
            "    if (-not $ip) { $ip = 'Не назначен' };"
            "    $name + '|' + $ip"
            "}"
        )
        r = subprocess.run(
            ["powershell","-NoProfile","-NonInteractive","-Command", ps],
            capture_output=True, encoding="utf-8",
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        for line in r.stdout.splitlines():
            line = line.strip()
            if "|" in line:
                parts = line.split("|", 1)
                if len(parts) == 2:
                    name, ip = parts[0].strip(), parts[1].strip()
                    if name and not any(a["name"]==name for a in result):
                        result.append({"name": name, "ip": ip})
    except: pass

    # Способ 2: netsh как запасной
    if not result:
        try:
            r = subprocess.run(["netsh","interface","ip","show","address"],
                               capture_output=True, encoding="cp866",
                               creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            name = None
            for line in r.stdout.splitlines():
                l = line.strip()
                if '"' in l and ("интерфейс" in l.lower() or "Настройка" in l
                                 or "interface" in l.lower()):
                    name = l.split('"')[1]
                elif name and ("IP-адрес" in l or "IP Address" in l):
                    ip = l.split()[-1].strip()
                    try:
                        ipaddress.ip_address(ip)
                        if not any(a["name"]==name for a in result):
                            result.append({"name":name,"ip":ip})
                    except: pass
        except: pass

    # Способ 3: socket резерв
    if not result:
        try:
            import socket as _s
            hostname = _s.gethostname()
            ips = _s.getaddrinfo(hostname, None, _s.AF_INET)
            for item in ips:
                ip = item[4][0]
                if ip != "127.0.0.1":
                    result.append({"name": f"Адаптер ({ip})", "ip": ip})
        except: pass

    return result

def set_adapter_ip(adapter, new_ip, mask="255.255.255.0"):
    if not is_admin(): return False, "Нет прав администратора"
    try:
        r = subprocess.run(["netsh","interface","ip","set","address",
                            f"name={adapter}","source=static",
                            f"address={new_ip}",f"mask={mask}"],
                           capture_output=True, encoding="cp866",
                           creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if r.returncode == 0: return True, f"IP изменён: {new_ip}"
        return False, (r.stderr or r.stdout).strip()
    except Exception as e: return False, str(e)

def suggest_ip(device_ip):
    try:
        p = device_ip.split(".")
        if len(p) == 4: return f"{p[0]}.{p[1]}.{p[2]}.200"
    except: pass
    return "192.168.1.200"

# ── Данные ────────────────────────────────────────────────────────────────────
DEMO = []

def load_devices():
    if os.path.exists(DATA_FILE):
        try: return json.load(open(DATA_FILE,encoding="utf-8"))
        except: pass
    return [dict(d) for d in DEMO]

def save_devices(devs):
    try: json.dump(devs,open(DATA_FILE,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    except: pass

# ── Запуск программ ───────────────────────────────────────────────────────────
def launch(proto, ip, port, app=None):
    OS = platform.system(); CNW = getattr(subprocess,"CREATE_NO_WINDOW",0)
    try:
        if proto in ("http","https","ftp"): webbrowser.open(f"{proto}://{ip}:{port}")
        elif proto == "vnc":
            if OS == "Windows":
                for exe in ["vncviewer.exe","tvnviewer.exe"]:
                    for d in [r"C:\Program Files\RealVNC\VNC Viewer",
                               r"C:\Program Files\TightVNC"]:
                        fp = os.path.join(d,exe)
                        if os.path.exists(fp):
                            subprocess.Popen([fp,f"{ip}:{port}"],creationflags=CNW); return
            subprocess.Popen(["vncviewer",f"{ip}:{port}"])
        elif proto == "rdp":
            if OS == "Windows": subprocess.Popen(["mstsc",f"/v:{ip}:{port}"],creationflags=CNW)
        elif proto == "ssh":
            if OS == "Windows":
                p = r"C:\Program Files\PuTTY\putty.exe"
                if os.path.exists(p): subprocess.Popen([p,"-ssh",ip,"-P",str(port)],creationflags=CNW)
                else: subprocess.Popen(["cmd","/k",f"ssh {ip} -p {port}"])
        elif proto == "telnet":
            if OS == "Windows": subprocess.Popen(["cmd","/k",f"telnet {ip} {port}"])
        elif proto in ("modbus-tcp","opc-ua"):
            txt = f"opc.tcp://{ip}:{port}" if proto=="opc-ua" else f"{ip}:{port}"
            if app: app.copy(txt)
    except Exception as e: messagebox.showerror("Ошибка",str(e))

# ── Диалог добавления/редактирования ─────────────────────────────────────────
class DeviceDlg(ctk.CTkToplevel):
    def __init__(self, parent, device=None, groups=None):
        super().__init__(parent)
        self.result = None; self.device = device or {}; self.groups = groups or []
        self.title("Добавить устройство" if not device else "Редактировать")
        self.resizable(False,False)
        self.grab_set(); self.attributes("-topmost",True)
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        w,h = 440,500; self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self._build()

    def _build(self):
        d = self.device
        self.v_ip    = ctk.StringVar(value=d.get("ip",""))
        self.v_name  = ctk.StringVar(value=d.get("name",""))
        self.v_group = ctk.StringVar(value=d.get("group",""))
        self.v_note  = ctk.StringVar(value=d.get("note",""))
        self.v_port  = ctk.StringVar(value=str(d.get("port",80)))
        self.v_type  = ctk.StringVar(value=TYPE_LABELS.get(d.get("type","plc"),"ПЛК"))
        self.v_proto = ctk.StringVar(value=d.get("proto","http"))

        # Заголовок
        ctk.CTkLabel(self, text="Новое устройство" if not d else d.get("name",""),
                     font=ctk.CTkFont(size=16,weight="bold")).pack(
                         anchor="w", padx=20, pady=(16,4))
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).pack(fill="x", padx=20, pady=(0,8))

        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=20)

        def field(parent, label, var, row=0, col=0, colspan=1):
            ctk.CTkLabel(parent, text=label, font=ctk.CTkFont(size=11),
                         text_color=C["text2"]).grid(row=row*2, column=col, columnspan=colspan,
                                                      sticky="w", pady=(8,2))
            e = ctk.CTkEntry(parent, textvariable=var, height=36,
                              font=ctk.CTkFont(size=12), corner_radius=8)
            e.grid(row=row*2+1, column=col, columnspan=colspan, sticky="ew",
                   padx=(0,8) if col==0 else (0,0))
            return e

        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        field(f,"IP-адрес *",self.v_ip, row=0, col=0, colspan=2)
        field(f,"Название *",self.v_name, row=1, col=0, colspan=2)

        # Тип
        ctk.CTkLabel(f, text="Тип", font=ctk.CTkFont(size=11),
                     text_color=C["text2"]).grid(row=4, column=0, sticky="w", pady=(8,2))
        self._cb_type = ctk.CTkComboBox(f, variable=self.v_type, height=36,
                                         values=list(TYPE_LABELS.values()),
                                         corner_radius=8, state="readonly")
        self._cb_type.grid(row=5, column=0, sticky="ew", padx=(0,8))

        # Протокол
        ctk.CTkLabel(f, text="Протокол", font=ctk.CTkFont(size=11),
                     text_color=C["text2"]).grid(row=4, column=1, sticky="w", pady=(8,2))
        self._cb_proto = ctk.CTkComboBox(f, variable=self.v_proto, height=36,
                                          values=list(PROTO_PORTS.keys()),
                                          corner_radius=8, state="readonly",
                                          command=lambda _: self.v_port.set(
                                              str(PROTO_PORTS.get(self.v_proto.get(),80))))
        self._cb_proto.grid(row=5, column=1, sticky="ew")

        field(f,"Порт", self.v_port, row=3, col=0)
        field(f,"Цех / Группа", self.v_group, row=3, col=1)
        field(f,"Заметка (пароль, прошивка...)", self.v_note, row=4, col=0, colspan=2)

        # Кнопки
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).pack(fill="x", padx=20, pady=8)
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0,16))
        ctk.CTkButton(bf, text="Отмена", command=self.destroy,
                      fg_color="transparent", border_width=1,
                      border_color=C["border"], text_color=C["text2"],
                      hover_color=C["border"], height=36,
                      corner_radius=8).pack(side="right", padx=(8,0))
        ctk.CTkButton(bf, text="Сохранить", command=self._save,
                      height=36, corner_radius=8).pack(side="right")

    def _save(self):
        ip = self.v_ip.get().strip(); nm = self.v_name.get().strip()
        if not ip or not nm:
            messagebox.showerror("Ошибка","IP и Название обязательны",parent=self); return
        tkey = next((k for k,v in TYPE_LABELS.items() if v==self.v_type.get()),"other")
        proto = self.v_proto.get()
        try: port = int(self.v_port.get())
        except: port = PROTO_PORTS.get(proto,80)
        self.result = {"id":self.device.get("id",int(time.time()*1000)),
                       "ip":ip,"name":nm,"type":tkey,"proto":proto,"port":port,
                       "group":self.v_group.get().strip(),"note":self.v_note.get().strip(),
                       "status":"unknown","ping_ms":None}
        self.destroy()

# ── Диалог смены подсети ──────────────────────────────────────────────────────
class SubnetDlg(ctk.CTkToplevel):
    def __init__(self, parent, device):
        super().__init__(parent)
        self.device = device
        self.title("Смена подсети")
        self.resizable(False,False)
        self.attributes("-topmost",True); self.grab_set()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        w,h = 420,340; self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        self._build()

    def _build(self):
        d = self.device
        ctk.CTkLabel(self, text=f"Подключение к {d['name']}",
                     font=ctk.CTkFont(size=15,weight="bold")).pack(anchor="w",padx=20,pady=(16,2))
        ctk.CTkLabel(self, text=f"IP устройства: {d['ip']}:{d['port']}",
                     text_color=C["text2"],font=ctk.CTkFont(size=11)).pack(anchor="w",padx=20)
        ctk.CTkFrame(self, height=1, fg_color=C["border"]).pack(fill="x",padx=20,pady=8)

        f = ctk.CTkFrame(self, fg_color="transparent")
        f.pack(fill="both", expand=True, padx=20)

        self.adapters = get_adapters()
        names = [f"{a['name']}  ({a['ip']})" for a in self.adapters]
        self.v_adapter = ctk.StringVar(value="-- Выберите адаптер --")
        names = ["-- Выберите адаптер --"] + (names or ["Нет адаптеров"])

        ctk.CTkLabel(f, text="Сетевой адаптер", text_color=C["text2"],
                     font=ctk.CTkFont(size=11)).pack(anchor="w", pady=(0,4))
        ctk.CTkComboBox(f, variable=self.v_adapter, values=names,
                         state="readonly", height=36, corner_radius=8).pack(fill="x")

        row = ctk.CTkFrame(f, fg_color="transparent")
        row.pack(fill="x", pady=(8,0))
        row.columnconfigure(0,weight=1); row.columnconfigure(1,weight=1)

        self.v_ip   = ctk.StringVar(value=suggest_ip(d["ip"]))
        self.v_mask = ctk.StringVar(value="255.255.255.0")
        for col,lbl,var in [(0,"Новый IP для вас",self.v_ip),(1,"Маска",self.v_mask)]:
            ctk.CTkLabel(row,text=lbl,text_color=C["text2"],
                         font=ctk.CTkFont(size=11)).grid(row=0,column=col,sticky="w",padx=(0,8) if col==0 else 0)
            ctk.CTkEntry(row,textvariable=var,height=36,corner_radius=8,
                         font=ctk.CTkFont(family="Courier New",size=11)
                         ).grid(row=1,column=col,sticky="ew",padx=(0,8) if col==0 else 0,pady=(4,0))

        self.st = ctk.CTkLabel(f, text="", font=ctk.CTkFont(size=11))
        self.st.pack(anchor="w", pady=(8,0))

        ctk.CTkFrame(self, height=1, fg_color=C["border"]).pack(fill="x",padx=20,pady=8)
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(fill="x", padx=20, pady=(0,16))
        ctk.CTkButton(bf, text="Отмена", command=self.destroy,
                      fg_color="transparent", border_width=1,
                      border_color=C["border"], text_color=C["text2"],
                      hover_color=C["border"], height=36, corner_radius=8
                      ).pack(side="right", padx=(8,0))
        ctk.CTkButton(bf, text="Сменить IP и подключиться", command=self._apply,
                      height=36, corner_radius=8).pack(side="right")

    def _apply(self):
        chosen = self.v_adapter.get()
        if chosen == "-- Выберите адаптер --" or not chosen:
            self.st.configure(text="Выберите адаптер!",text_color=C["amber"]); return
        names = [f"{a['name']}  ({a['ip']})" for a in self.adapters]
        try: idx = names.index(chosen)
        except: self.st.configure(text="Выберите адаптер",text_color=C["amber"]); return
        new_ip = self.v_ip.get().strip(); mask = self.v_mask.get().strip()
        try: ipaddress.ip_address(new_ip)
        except: self.st.configure(text="Неверный IP",text_color=C["red"]); return
        self.st.configure(text="Меняю IP...",text_color=C["amber"]); self.update()
        def run():
            ok,msg = set_adapter_ip(self.adapters[idx]["name"],new_ip,mask)
            if ok:
                self.after(0,lambda:self.st.configure(text=f"✓ {msg}",text_color=C["green"]))
                time.sleep(1.5)
                self.after(0,lambda:launch(self.device["proto"],self.device["ip"],self.device["port"]))
                self.after(2500,self.destroy)
            else:
                self.after(0,lambda:self.st.configure(text=f"✗ {msg}",text_color=C["red"]))
        threading.Thread(target=run,daemon=True).start()

# ── Карточка устройства ───────────────────────────────────────────────────────
class DeviceCard(ctk.CTkFrame):
    def __init__(self, parent, device, app):
        super().__init__(parent, corner_radius=12, fg_color=C["card"],
                         border_width=1, border_color=C["border"])
        self.device = device; self.app = app
        self._build()

    def _build(self):
        d = self.device
        color = TYPE_COLORS.get(d["type"], C["text3"])

        # Строка 1: статус + имя + тег + кнопки
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10,4))

        # Статус точка
        self.dot = ctk.CTkLabel(top, text="●", font=ctk.CTkFont(size=10),
                                  text_color=C["text3"], width=16)
        self.dot.pack(side="left")

        # Имя
        ctk.CTkLabel(top, text=d["name"], font=ctk.CTkFont(size=12,weight="bold"),
                     text_color=C["text"]).pack(side="left", padx=(4,0))

        # Тег типа
        tag = ctk.CTkFrame(top, corner_radius=6, fg_color=C["bg3"])
        tag.pack(side="left", padx=(8,0))
        ctk.CTkLabel(tag, text=TYPE_LABELS.get(d["type"],"?"),
                     font=ctk.CTkFont(size=10,weight="bold"),
                     text_color=color, padx=6, pady=2).pack()

        # Кнопки управления
        for txt,col,cmd in [("✕",C["red"],   lambda:self.app.delete_device(d["id"])),
                             ("📋",C["teal"],  lambda:self.app.show_history(d["id"])),
                             ("✎",C["accent"], lambda:self.app.edit_device(d["id"]))]:
            ctk.CTkButton(top, text=txt, width=26, height=22, corner_radius=6,
                          fg_color="transparent", text_color=C["text3"],
                          hover_color=C["border"], font=ctk.CTkFont(size=11),
                          command=cmd).pack(side="right", padx=1)

        # Строка 2: IP + пинг + кнопки действий
        bot = ctk.CTkFrame(self, fg_color="transparent")
        bot.pack(fill="x", padx=12, pady=(0,10))

        ctk.CTkLabel(bot, text=f"{d['ip']}:{d['port']}",
                     font=ctk.CTkFont(family="Courier New",size=12,weight="bold"),
                     text_color=C["text2"]).pack(side="left")

        self.ms_lbl = ctk.CTkLabel(bot, text="", width=60,
                                    font=ctk.CTkFont(size=11,weight="bold"),
                                    text_color=C["text3"])
        self.ms_lbl.pack(side="left", padx=(8,0))

        # Кнопки действий
        brf = ctk.CTkFrame(bot, fg_color="transparent")
        brf.pack(side="right")

        def ibtn(text, color, cmd):
            ctk.CTkButton(brf, text=text, width=30, height=26, corner_radius=7,
                          fg_color=C["bg3"], text_color=color,
                          hover_color=C["border"], font=ctk.CTkFont(size=12,weight="bold"),
                          command=cmd).pack(side="left", padx=1)

        if platform.system() == "Windows":
            ibtn("🌐", C["teal"], lambda: SubnetDlg(self.app,d))
        ibtn("⟳", C["amber"], lambda: self.app.ping_one(d["id"]))
        p = d["proto"]
        if p in ("http","https","ftp"):
            ibtn("↗", C["accent"], lambda p=p,i=d["ip"],po=d["port"]: launch(p,i,po,self.app))
        elif p in ("vnc","rdp","ssh","telnet"):
            ibtn("▶", C["green"], lambda: launch(p,d["ip"],d["port"],self.app))
        elif p in ("modbus-tcp","opc-ua"):
            fc = C["modbus"] if p=="modbus-tcp" else C["opcua"]
            t  = "opc.tcp://" if p=="opc-ua" else ""
            ibtn("⎘", fc, lambda t=t: self.app.copy(f"{t}{d['ip']}:{d['port']}"))

        if d.get("note"):
            ctk.CTkLabel(self, text=f"📝 {d['note']}",
                         font=ctk.CTkFont(size=10), text_color=C["text3"],
                         anchor="w").pack(fill="x", padx=12, pady=(0,8))

        self.update_status()

    def update_status(self):
        d = self.device; s = d.get("status","unknown"); ms = d.get("ping_ms")
        if s == "online":
            self.dot.configure(text_color=C["green"])
            self.ms_lbl.configure(text=f"{ms}мс" if ms else "ОК", text_color=C["green"])
            self.configure(border_color=C["green"])
        elif s == "offline":
            self.dot.configure(text_color=C["red"])
            self.ms_lbl.configure(text="Офлайн", text_color=C["red"])
            self.configure(border_color=C["red"])
        elif s == "checking":
            self.dot.configure(text_color=C["amber"])
            self.ms_lbl.configure(text="...", text_color=C["amber"])
            self.configure(border_color=C["amber"])
        else:
            self.dot.configure(text_color=C["text3"])
            self.ms_lbl.configure(text="", text_color=C["text3"])
            self.configure(border_color=C["border"])

# ── Главное окно ──────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        # Скругление углов окна
        if platform.system() == "Windows":
            try:
                from ctypes import windll, c_int, byref, sizeof
                DWMWA_WINDOW_CORNER_PREFERENCE = 33
                DWMWCP_ROUND = 2
                self.update()
                hwnd = windll.user32.GetParent(self.winfo_id())
                windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
                    byref(c_int(DWMWCP_ROUND)), sizeof(c_int))
            except: pass

        self.devices        = load_devices()
        self.current_filter = "all"
        self.search_var     = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh())
        self.notif_var      = ctk.BooleanVar(value=True)
        self.autopng_var    = ctk.StringVar(value="Off")
        self._cards         = {}
        self._auto_job      = None
        self._expanded      = False
        self._fullscreen    = False
        self._drag_ox = 0; self._drag_oy = 0

        sw = self.winfo_screenwidth()
        self._px = sw - PANEL_W - 10; self._py = 0
        self.geometry(f"{PANEL_W}x{TAB_H}+{self._px}+{self._py}")

        self._build_tab()
        self._build_panel()

        # Скрывать при потере фокуса
        self.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Unmap>", lambda e: None)
        self.protocol("WM_DELETE_WINDOW", self._quit)

    # ── Потеря фокуса = свернуть ──────────────────────────────────────────────
    def _on_focus_out(self, e):
        if not self._expanded: return
        # Не сворачивать если открыт диалог
        self.after(300, self._check_focus)

    def _check_focus(self):
        try:
            # Проверяем есть ли активный Toplevel диалог
            for w in self.winfo_children():
                if isinstance(w, ctk.CTkToplevel) and w.winfo_viewable():
                    return  # Диалог открыт — не сворачиваем
            focused = self.focus_get()
            if focused is None:
                self._collapse()
        except: pass

    # ── Компактная полоска ────────────────────────────────────────────────────
    def _build_tab(self):
        self.tab = ctk.CTkFrame(self, height=TAB_H, corner_radius=0,
                                 fg_color=C["tab"])
        self.tab.pack(fill="x"); self.tab.pack_propagate(False)

        # Точка статуса
        self.tab_dot = ctk.CTkLabel(self.tab, text="●",
                                     font=ctk.CTkFont(size=8),
                                     text_color=C["green"], width=14)
        self.tab_dot.pack(side="left", padx=(10,2))

        # Название
        ctk.CTkLabel(self.tab, text=f"АСУ ТП {APP_VER}",
                     font=ctk.CTkFont(size=10,weight="bold"),
                     text_color=C["tab_text"]).pack(side="left")

        # Счётчики
        self.lbl_on  = ctk.CTkLabel(self.tab, text="▲0",
                                     font=ctk.CTkFont(size=8,weight="bold"),
                                     text_color=C["green"])
        self.lbl_on.pack(side="left", padx=(10,0))
        self.lbl_off = ctk.CTkLabel(self.tab, text="▼0",
                                     font=ctk.CTkFont(size=8,weight="bold"),
                                     text_color=C["red"])
        self.lbl_off.pack(side="left", padx=(4,0))

        # Кнопки (компактные)
        for txt,col,cmd in [("×",C["red"],    self._quit),
                             ("□",C["tab_text"],self._toggle_fs),
                             ("↺",C["tab_text"],self.ping_all),
                             ("+",C["tab_text"],self.add_device)]:
            ctk.CTkButton(self.tab, text=txt, width=30, height=26,
                          corner_radius=6, fg_color="transparent",
                          text_color=col, hover_color=C["bg3"],
                          font=ctk.CTkFont(size=13),
                          command=cmd).pack(side="right", padx=2)

        # Стрелка сворачивания
        self.arrow = ctk.CTkButton(self.tab, text="▾", width=30, height=26,
                                    corner_radius=6, fg_color="transparent",
                                    text_color=C["tab_text"], hover_color=C["bg3"],
                                    font=ctk.CTkFont(size=14),
                                    command=self.toggle)
        self.arrow.pack(side="right", padx=(0,2))

        # Перетаскивание
        self.tab.bind("<ButtonPress-1>",  self._drag_start)
        self.tab.bind("<B1-Motion>",      self._drag_move)

    # ── Панель ────────────────────────────────────────────────────────────────
    def _build_panel(self):
        self.panel = ctk.CTkFrame(self, corner_radius=0, fg_color=C["bg"])

        # Поиск
        sf = ctk.CTkFrame(self.panel, fg_color="transparent")
        sf.pack(fill="x", padx=8, pady=(8,4))
        self.search_entry = ctk.CTkEntry(
            sf, textvariable=self.search_var,
            placeholder_text="🔍  Поиск: имя, IP, цех...",
            height=34, corner_radius=10,
            font=ctk.CTkFont(size=12))
        self.search_entry.pack(fill="x")

        # Фильтры
        fr = ctk.CTkFrame(self.panel, fg_color="transparent")
        fr.pack(fill="x", padx=8, pady=(0,6))
        self._fbts = {}
        for lbl,key in [("Все","all"),("ПЛК","plc"),("HMI","hmi"),
                         ("SCADA","scada"),("Modbus","modbus"),
                         ("OPC","opcua"),("🟢","__on"),("🔴","__off")]:
            b = ctk.CTkButton(fr, text=lbl, width=36, height=26,
                               corner_radius=8, font=ctk.CTkFont(size=10,weight="bold"),
                               fg_color=C["bg2"], text_color=C["text2"],
                               hover_color=C["bg3"],
                               command=lambda k=key: self._set_filter(k))
            b.pack(side="left", padx=2)
            self._fbts[key] = b
        self._set_filter("all", update=False)

        # Настройки
        sp = ctk.CTkFrame(self.panel, corner_radius=8, fg_color=C["bg2"])
        sp.pack(fill="x", padx=8, pady=(0,6))
        ctk.CTkLabel(sp, text="Автопинг:", font=ctk.CTkFont(size=11),
                     text_color=C["text2"]).pack(side="left", padx=(10,4), pady=6)
        cb = ctk.CTkComboBox(sp, variable=self.autopng_var,
                              values=list(AUTO_IV.keys()),
                              width=80, height=28, corner_radius=8,
                              font=ctk.CTkFont(size=11),
                              command=lambda _: self._restart_auto())
        cb.pack(side="left", pady=6)
        ctk.CTkCheckBox(sp, text="🔔", variable=self.notif_var,
                         width=40, height=28,
                         font=ctk.CTkFont(size=12)).pack(side="left", padx=(10,0))

        # Экспорт/Импорт
        btm = ctk.CTkFrame(self.panel, corner_radius=8, fg_color=C["bg2"])
        btm.pack(fill="x", padx=8, pady=(0,6))
        for txt,cmd in [("↓ Экспорт",self.export_dev),("↑ Импорт",self.import_dev)]:
            ctk.CTkButton(btm, text=txt, command=cmd, height=28,
                          corner_radius=8, fg_color="transparent",
                          text_color=C["text2"], hover_color=C["bg3"],
                          font=ctk.CTkFont(size=11)
                          ).pack(side="left", padx=4, pady=4)
        if not PING3_OK:
            ctk.CTkLabel(btm, text="⚠ pip install ping3",
                         text_color=C["amber"],
                         font=ctk.CTkFont(size=10)).pack(side="right", padx=8)

        ctk.CTkFrame(self.panel, height=1, fg_color=C["border"]).pack(fill="x", padx=8)

        # Прокручиваемый список
        self.scroll = ctk.CTkScrollableFrame(self.panel, fg_color="transparent",
                                              corner_radius=0)
        self.scroll.pack(fill="both", expand=True, padx=0, pady=4)

    # ── Разворачивание / Сворачивание ─────────────────────────────────────────
    def toggle(self):
        if self._expanded: self._collapse()
        else: self._expand()

    def _expand(self):
        self._expanded = True
        self.arrow.configure(text="▴")
        self.panel.pack(fill="both", expand=True)
        self._refresh()
        self.geometry(f"{PANEL_W}x{PANEL_H}+{self._px}+{self._py}")
        self.lift()
        self.focus_force()

    def _collapse(self):
        self._expanded = False
        self._fullscreen = False
        self.arrow.configure(text="▾")
        self.panel.pack_forget()
        self.geometry(f"{PANEL_W}x{TAB_H}+{self._px}+{self._py}")

    def _toggle_fs(self):
        if not self._expanded: self._expand(); return
        if self._fullscreen:
            self._fullscreen = False
            sw = self.winfo_screenwidth()
            self._px = sw-PANEL_W-10; self._py = 0
            self.geometry(f"{PANEL_W}x{PANEL_H}+{self._px}+{self._py}")
        else:
            self._fullscreen = True
            sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
            self._px = 0; self._py = 0
            self.geometry(f"{sw}x{sh}+0+0")

    # ── Перетаскивание ────────────────────────────────────────────────────────
    def _drag_start(self, e):
        self._drag_ox = e.x_root - self._px
        self._drag_oy = e.y_root - self._py

    def _drag_move(self, e):
        if self._fullscreen: return
        self._px = e.x_root - self._drag_ox
        self._py = max(0, e.y_root - self._drag_oy)
        h = PANEL_H if self._expanded else TAB_H
        self.geometry(f"{PANEL_W}x{h}+{self._px}+{self._py}")

    # ── Фильтры ───────────────────────────────────────────────────────────────
    def _set_filter(self, key, update=True):
        self.current_filter = key
        for k,b in self._fbts.items():
            if k == key:
                b.configure(fg_color=C["accent"], text_color="#fff")
            else:
                b.configure(fg_color=C["bg2"], text_color=C["text2"])
        if update: self._refresh()

    def _visible(self, d):
        key = self.current_filter
        q   = self.search_var.get().lower()
        # Убираем placeholder из поиска
        if key == "__on"  and d["status"] != "online":  return False
        if key == "__off" and d["status"] != "offline": return False
        if key not in ("all","__on","__off") and d["type"] != key: return False
        if q and q not in d["ip"] and q not in d["name"].lower() \
              and q not in d.get("group","").lower() \
              and q not in d.get("note","").lower(): return False
        return True

    # ── Карточки ──────────────────────────────────────────────────────────────
    def _refresh(self):
        if not hasattr(self,"scroll"): return
        for w in self.scroll.winfo_children(): w.destroy()
        self._cards.clear()
        visible = [d for d in self.devices if self._visible(d)]
        if not visible:
            ctk.CTkLabel(self.scroll, text="Устройств не найдено",
                         text_color=C["text3"],
                         font=ctk.CTkFont(size=12)).pack(pady=30)
        else:
            for d in visible:
                card = DeviceCard(self.scroll, d, self)
                card.pack(fill="x", padx=8, pady=4)
                self._cards[d["id"]] = card
        self._update_stats()

    def _update_card(self, did):
        if did in self._cards:
            self._cards[did].update_status()

    def _update_stats(self):
        on  = sum(1 for d in self.devices if d["status"]=="online")
        off = sum(1 for d in self.devices if d["status"]=="offline")
        self.lbl_on.configure(text=f"▲{on}")
        self.lbl_off.configure(text=f"▼{off}")
        self.tab_dot.configure(text_color=C["red"] if off>0 else C["green"])

    # ── Пинг ──────────────────────────────────────────────────────────────────
    def ping_one(self, did):
        d = next((x for x in self.devices if x["id"]==did), None)
        if not d: return
        prev = d.get("status","unknown"); d["status"] = "checking"
        self._update_card(did); self._update_stats()
        def run():
            ok,ms = check_host(d["ip"],d["port"])
            new = "online" if ok else "offline"
            d["status"] = new; d["ping_ms"] = ms
            HISTORY.add(did,new,ms); HISTORY.save()
            if self.notif_var.get() and prev not in ("unknown","checking") and prev!=new:
                if new=="offline": notify(f"⛔ {d['name']} недоступен",f"IP: {d['ip']}")
                else: notify(f"✅ {d['name']} онлайн",f"IP: {d['ip']}")
            save_devices(self.devices)
            self.after(0, lambda: self._update_card(did))
            self.after(0, self._update_stats)
        threading.Thread(target=run,daemon=True).start()

    def ping_all(self):
        for d in self.devices: self.ping_one(d["id"])

    def _restart_auto(self):
        if self._auto_job: self.after_cancel(self._auto_job); self._auto_job = None
        secs = AUTO_IV.get(self.autopng_var.get(),0)
        if secs > 0: self._sched(secs)

    def _sched(self, secs):
        self.ping_all()
        self._auto_job = self.after(secs*1000, lambda: self._sched(secs))

    # ── CRUD ──────────────────────────────────────────────────────────────────
    def _groups(self):
        return sorted({d.get("group","") for d in self.devices if d.get("group")})

    def add_device(self):
        dlg = DeviceDlg(self, groups=self._groups())
        self.wait_window(dlg)
        if dlg.result:
            self.devices.append(dlg.result); save_devices(self.devices)
            if self._expanded: self._refresh()
            self._update_stats()

    def edit_device(self, did):
        d = next((x for x in self.devices if x["id"]==did), None)
        if not d: return
        dlg = DeviceDlg(self, device=dict(d), groups=self._groups())
        self.wait_window(dlg)
        if dlg.result:
            idx = next(i for i,x in enumerate(self.devices) if x["id"]==did)
            self.devices[idx] = dlg.result; save_devices(self.devices)
            if self._expanded: self._refresh()

    def delete_device(self, did):
        if not messagebox.askyesno("Удалить","Удалить устройство?",parent=self): return
        self.devices = [d for d in self.devices if d["id"]!=did]
        save_devices(self.devices)
        if self._expanded: self._refresh()
        self._update_stats()

    def show_history(self, did):
        d = next((x for x in self.devices if x["id"]==did), None)
        if not d: return
        win = ctk.CTkToplevel(self)
        win.title(f"История — {d['name']}")
        win.geometry("500x420"); win.attributes("-topmost",True)
        ctk.CTkLabel(win, text=f"История: {d['name']}",
                     font=ctk.CTkFont(size=14,weight="bold")).pack(anchor="w",padx=16,pady=(14,2))
        ctk.CTkLabel(win, text=f"IP: {d['ip']}:{d['port']}",
                     text_color=C["text2"],font=ctk.CTkFont(size=11)).pack(anchor="w",padx=16)
        import tkinter.ttk as ttk
        frame = ctk.CTkFrame(win,fg_color="transparent")
        frame.pack(fill="both",expand=True,padx=8,pady=8)
        tree = ttk.Treeview(frame,columns=("Время","Статус","Пинг"),show="headings")
        for c,w in zip(("Время","Статус","Пинг"),[140,130,80]):
            tree.heading(c,text=c); tree.column(c,width=w,anchor="center")
        sb = ttk.Scrollbar(frame,orient="vertical",command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); tree.pack(fill="both",expand=True)
        recs = HISTORY.get(d["id"])
        if not recs: tree.insert("","end",values=("—","Нет данных","—"))
        else:
            for r in reversed(recs):
                s=r["status"]
                tree.insert("","end",values=(r["ts"],
                    "Онлайн" if s=="online" else "Офлайн",
                    str(r["ms"]) if r.get("ms") else "—"))

    def copy(self, text):
        self.clipboard_clear(); self.clipboard_append(text); self.update()

    def export_dev(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON","*.json"),("CSV","*.csv")],
            initialfile=f"asu-ip-{datetime.date.today()}.json", parent=self)
        if not path: return
        if path.endswith(".csv"):
            fields = ["id","ip","name","type","proto","port","group","note"]
            with open(path,"w",newline="",encoding="utf-8-sig") as f:
                w = csv.DictWriter(f,fieldnames=fields); w.writeheader()
                for d in self.devices: w.writerow({k:d.get(k,"") for k in fields})
        else:
            json.dump(self.devices,open(path,"w",encoding="utf-8"),ensure_ascii=False,indent=2)
        messagebox.showinfo("Экспорт",f"Сохранено:\n{path}",parent=self)

    def import_dev(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON/CSV","*.json *.csv")],parent=self)
        if not path: return
        try:
            nd = []
            if path.endswith(".csv"):
                for row in csv.DictReader(open(path,"r",encoding="utf-8-sig")):
                    nd.append({"id":int(time.time()*1000)+len(nd),
                               "ip":row.get("ip",""),"name":row.get("name","?"),
                               "type":row.get("type","other"),"proto":row.get("proto","http"),
                               "port":int(row.get("port",80) or 80),
                               "group":row.get("group",""),"note":row.get("note",""),
                               "status":"unknown","ping_ms":None})
            else: nd = json.load(open(path,"r",encoding="utf-8"))
        except Exception as e:
            messagebox.showerror("Ошибка",str(e),parent=self); return
        existing = {d["ip"] for d in self.devices}; added = 0
        for d in nd:
            if d.get("ip") and d["ip"] not in existing:
                d["status"]="unknown"; d["ping_ms"]=None
                self.devices.append(d); existing.add(d["ip"]); added+=1
        save_devices(self.devices)
        if self._expanded: self._refresh()
        self._update_stats()
        messagebox.showinfo("Импорт",f"Добавлено: {added}",parent=self)

    def _quit(self):
        if self._auto_job: self.after_cancel(self._auto_job)
        save_devices(self.devices); HISTORY.save(); self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
