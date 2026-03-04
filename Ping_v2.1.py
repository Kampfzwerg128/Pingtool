import subprocess
import sys
import re
import json
import os
import tkinter as tk

DEFAULT_PING_COUNT = 4
WINDOWS_DEFAULT_TIMEOUT_MS = 4000
PING_TIMEOUT_BUFFER_SECONDS = 5


def get_storage_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


HOSTS_SAVE_FILE = os.path.join(get_storage_dir(), "ping_hosts.json")


def save_hosts_to_file(hosts, file_path=HOSTS_SAVE_FILE):
    data = [{"ip": ip, "name": name} for ip, name in hosts]
    with open(file_path, "w", encoding="utf-8") as save_file:
        json.dump(data, save_file, ensure_ascii=False, indent=2)


def load_hosts_from_file(fallback_hosts, file_path=HOSTS_SAVE_FILE):
    try:
        with open(file_path, "r", encoding="utf-8") as saved_file:
            data = json.load(saved_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback_hosts

    loaded_hosts = []
    for item in data:
        if not isinstance(item, dict):
            continue
        ip = str(item.get("ip", "")).strip()
        name = str(item.get("name", "")).strip()
        if not ip:
            continue
        if not name:
            name = ip
        loaded_hosts.append((ip, name))

    return loaded_hosts or fallback_hosts


def format_host_names_for_input(hosts):
    return "\n".join(name for ip, name in hosts)


def format_host_ips_for_input(hosts):
    return "\n".join(ip for ip, name in hosts)


def parse_hosts_input(names_text, ips_text, fallback_hosts):
    names = [line.strip() for line in names_text.splitlines()]
    ips = [line.strip() for line in ips_text.splitlines()]

    parsed_hosts = []
    max_lines = max(len(names), len(ips))

    for index in range(max_lines):
        name = names[index] if index < len(names) else ""
        ip = ips[index] if index < len(ips) else ""

        if not ip:
            continue

        if not name:
            name = ip

        parsed_hosts.append((ip, name))

    return parsed_hosts or fallback_hosts


def extract_latency_stats_ms(output):
    windows_summary = re.search(
        r"(?:Minimum)\s*=\s*([0-9]+(?:[\.,][0-9]+)?)\s*ms\s*,\s*(?:Maximum)\s*=\s*([0-9]+(?:[\.,][0-9]+)?)\s*ms\s*,\s*(?:Average|Mittelwert)\s*=\s*([0-9]+(?:[\.,][0-9]+)?)\s*ms",
        output,
        re.IGNORECASE,
    )
    if windows_summary:
        min_ms = float(windows_summary.group(1).replace(",", "."))
        max_ms = float(windows_summary.group(2).replace(",", "."))
        avg_ms = float(windows_summary.group(3).replace(",", "."))
        return avg_ms, min_ms, max_ms

    linux_summary = re.search(
        r"=\s*([0-9]+(?:[\.,][0-9]+)?)/([0-9]+(?:[\.,][0-9]+)?)/([0-9]+(?:[\.,][0-9]+)?)/[0-9]+(?:[\.,][0-9]+)?\s*ms",
        output,
        re.IGNORECASE,
    )
    if linux_summary:
        min_ms = float(linux_summary.group(1).replace(",", "."))
        avg_ms = float(linux_summary.group(2).replace(",", "."))
        max_ms = float(linux_summary.group(3).replace(",", "."))
        return avg_ms, min_ms, max_ms

    values = re.findall(
        r"(?:time|zeit)\s*[=<]\s*([0-9]+(?:[\.,][0-9]+)?)\s*ms",
        output,
        re.IGNORECASE,
    )

    if values:
        parsed = [float(v.replace(",", ".")) for v in values]
        avg_ms = sum(parsed) / len(parsed)
        min_ms = min(parsed)
        max_ms = max(parsed)
        return avg_ms, min_ms, max_ms

    return None, None, None


def get_command_timeout_seconds(ping_count, timeout_ms):
    return max(10, int((ping_count * timeout_ms) / 1000) + PING_TIMEOUT_BUFFER_SECONDS)


def show_result_window(result_lines):
    window = tk.Tk()
    window.title("Ping-Ergebnisse")
    window.configure(bg="#111111")
    window.attributes("-topmost", True)
    window.lift()
    window.focus_force()

    frame = tk.Frame(window, bg="#111111", padx=12, pady=12)
    frame.pack(fill="both", expand=True)

    title_label = tk.Label(
        frame,
        text="Ping-Ergebnisse",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 12, "bold"),
        anchor="w"
    )
    title_label.pack(fill="x", pady=(0, 8))

    result_text = tk.Text(
        frame,
        bg="#111111",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
        highlightthickness=0,
        font=("Consolas", 10),
        wrap="none",
        height=max(8, len(result_lines) + 1)
    )
    result_text.tag_configure("default", foreground="#ffffff")
    result_text.tag_configure("reachable", foreground="#00ff66")
    result_text.tag_configure("unreachable", foreground="#ff4d4d")

    for line in result_lines:
        if "✗ Unerreichbar" in line:
            tag = "unreachable"
        elif "✓ Erreichbar" in line:
            tag = "reachable"
        else:
            tag = "default"
        result_text.insert("end", f"{line}\n", tag)

    result_text.config(state="disabled")
    result_text.pack(fill="both", expand=True)

    close_button = tk.Button(
        frame,
        text="Schließen",
        command=window.destroy,
        bg="#1f1f1f",
        fg="#ffffff",
        activebackground="#2a2a2a",
        activeforeground="#ffffff",
        relief="flat",
        padx=10,
        pady=4
    )
    close_button.pack(anchor="e", pady=(10, 0))

    window.update_idletasks()
    width = window.winfo_reqwidth()
    height = window.winfo_reqheight()
    x_pos = (window.winfo_screenwidth() // 2) - (width // 2)
    y_pos = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

    window.mainloop()


def show_start_window(hosts):
    initial_hosts = load_hosts_from_file(hosts)

    window = tk.Tk()
    window.title("Ping-Start")
    window.configure(bg="#111111")
    window.attributes("-topmost", True)
    window.lift()
    window.focus_force()

    frame = tk.Frame(window, bg="#111111", padx=12, pady=12)
    frame.pack(fill="both", expand=True)

    title_label = tk.Label(
        frame,
        text="Ping-Konfiguration",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 12, "bold"),
        anchor="w"
    )
    title_label.pack(fill="x", pady=(0, 8))

    settings_row = tk.Frame(frame, bg="#111111")
    settings_row.pack(fill="x", pady=(0, 8))

    ping_count_label = tk.Label(
        settings_row,
        text="Pings pro Adresse:",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 10),
        anchor="w"
    )
    ping_count_label.pack(side="left")

    ping_count_var = tk.StringVar(value=str(DEFAULT_PING_COUNT))
    ping_count_spinbox = tk.Spinbox(
        settings_row,
        from_=1,
        to=100,
        textvariable=ping_count_var,
        width=5,
        justify="center",
        bg="#1f1f1f",
        fg="#ffffff",
        insertbackground="#ffffff",
        buttonbackground="#1f1f1f",
        relief="flat",
        font=("Consolas", 10)
    )
    ping_count_spinbox.pack(side="left", padx=(8, 0))

    timeout_row = tk.Frame(frame, bg="#111111")
    timeout_row.pack(fill="x", pady=(0, 8))

    timeout_label = tk.Label(
        timeout_row,
        text="Timeout pro Ping (ms):",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 10),
        anchor="w"
    )
    timeout_label.pack(side="left")

    timeout_var = tk.StringVar(value=str(WINDOWS_DEFAULT_TIMEOUT_MS))
    timeout_spinbox = tk.Spinbox(
        timeout_row,
        from_=100,
        to=10000,
        textvariable=timeout_var,
        width=6,
        justify="center",
        bg="#1f1f1f",
        fg="#ffffff",
        insertbackground="#ffffff",
        buttonbackground="#1f1f1f",
        relief="flat",
        font=("Consolas", 10)
    )
    timeout_spinbox.pack(side="left", padx=(8, 0))

    host_input_title = tk.Label(
        frame,
        text="Ziele (pro Zeile ein Host):",
        justify="left",
        anchor="w",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 10)
    )
    host_input_title.pack(fill="x", pady=(4, 6))

    host_fields_row = tk.Frame(frame, bg="#111111")
    host_fields_row.pack(fill="both", expand=True)

    names_frame = tk.Frame(host_fields_row, bg="#111111")
    names_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))

    ips_frame = tk.Frame(host_fields_row, bg="#111111")
    ips_frame.pack(side="left", fill="both", expand=True, padx=(6, 0))

    names_label = tk.Label(
        names_frame,
        text="Name",
        justify="left",
        anchor="w",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 10)
    )
    names_label.pack(fill="x", pady=(0, 4))

    ips_label = tk.Label(
        ips_frame,
        text="IP-Adresse / Hostname",
        justify="left",
        anchor="w",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 10)
    )
    ips_label.pack(fill="x", pady=(0, 4))

    names_text_widget = tk.Text(
        names_frame,
        bg="#1f1f1f",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
        highlightthickness=0,
        font=("Consolas", 10),
        height=10,
        wrap="none"
    )
    names_text_widget.insert("1.0", format_host_names_for_input(initial_hosts))
    names_text_widget.pack(fill="both", expand=True)

    ips_text_widget = tk.Text(
        ips_frame,
        bg="#1f1f1f",
        fg="#ffffff",
        insertbackground="#ffffff",
        relief="flat",
        highlightthickness=0,
        font=("Consolas", 10),
        height=10,
        wrap="none"
    )
    ips_text_widget.insert("1.0", format_host_ips_for_input(initial_hosts))
    ips_text_widget.pack(fill="both", expand=True)

    save_status_label = tk.Label(
        frame,
        text="",
        justify="left",
        anchor="w",
        bg="#111111",
        fg="#ffffff",
        font=("Consolas", 9)
    )
    save_status_label.pack(fill="x", pady=(6, 0))

    start_config = {
        "started": False,
        "ping_count": DEFAULT_PING_COUNT,
        "timeout_ms": WINDOWS_DEFAULT_TIMEOUT_MS,
        "hosts": initial_hosts,
    }

    button_row = tk.Frame(frame, bg="#111111")
    button_row.pack(fill="x", pady=(10, 0))

    def on_save_hosts():
        hosts_to_save = parse_hosts_input(
            names_text_widget.get("1.0", "end"),
            ips_text_widget.get("1.0", "end"),
            initial_hosts,
        )
        try:
            save_hosts_to_file(hosts_to_save)
            save_status_label.config(text="Adressen gespeichert.", fg="#00ff66")
        except OSError as error:
            save_status_label.config(text=f"Speichern fehlgeschlagen: {error}", fg="#ff4d4d")

    def on_start():
        try:
            selected_count = int(ping_count_var.get())
        except ValueError:
            selected_count = DEFAULT_PING_COUNT

        try:
            selected_timeout_ms = int(timeout_var.get())
        except ValueError:
            selected_timeout_ms = WINDOWS_DEFAULT_TIMEOUT_MS

        selected_count = max(1, min(100, selected_count))
        selected_timeout_ms = max(100, min(10000, selected_timeout_ms))
        selected_hosts = parse_hosts_input(
            names_text_widget.get("1.0", "end"),
            ips_text_widget.get("1.0", "end"),
            hosts,
        )
        start_config["started"] = True
        start_config["ping_count"] = selected_count
        start_config["timeout_ms"] = selected_timeout_ms
        start_config["hosts"] = selected_hosts
        window.destroy()

    start_button = tk.Button(
        button_row,
        text="Pings starten",
        command=on_start,
        bg="#1f1f1f",
        fg="#ffffff",
        activebackground="#2a2a2a",
        activeforeground="#ffffff",
        relief="flat",
        padx=10,
        pady=4
    )
    start_button.pack(side="right")

    save_button = tk.Button(
        button_row,
        text="Adressen speichern",
        command=on_save_hosts,
        bg="#1f1f1f",
        fg="#ffffff",
        activebackground="#2a2a2a",
        activeforeground="#ffffff",
        relief="flat",
        padx=10,
        pady=4
    )
    save_button.pack(side="right", padx=(0, 8))

    window.update_idletasks()
    width = window.winfo_reqwidth()
    height = window.winfo_reqheight()
    x_pos = (window.winfo_screenwidth() // 2) - (width // 2)
    y_pos = (window.winfo_screenheight() // 2) - (height // 2)
    window.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

    window.mainloop()
    return (
        start_config["started"],
        start_config["ping_count"],
        start_config["timeout_ms"],
        start_config["hosts"],
    )

def ping_host(ip_address, ping_count, timeout_ms):
    """Ping a host and return reachability plus latency stats in ms"""
    try:
        run_kwargs = {
            "capture_output": True,
            "timeout": get_command_timeout_seconds(ping_count, timeout_ms),
        }

        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            run_kwargs["startupinfo"] = startupinfo
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

        # Windows
        if sys.platform == "win32":
            result = subprocess.run(
                ["ping", "-n", str(ping_count), "-w", str(timeout_ms), ip_address],
                **run_kwargs,
            )
        # Linux/Mac
        else:
            result = subprocess.run(
                ["ping", "-c", str(ping_count), "-W", str(max(1, timeout_ms // 1000)), ip_address],
                **run_kwargs,
            )
        if result.returncode != 0:
            return False, None, None, None

        output = (result.stdout or b"").decode(errors="ignore")

        successful_replies = re.findall(
            r"(?:time|zeit)\s*[=<]\s*([0-9]+(?:[\.,][0-9]+)?)\s*ms",
            output,
            re.IGNORECASE,
        )
        if not successful_replies:
            return False, None, None, None

        avg_ms, min_ms, max_ms = extract_latency_stats_ms(output)
        return True, avg_ms, min_ms, max_ms
    except subprocess.TimeoutExpired:
        return False, None, None, None
    except Exception as e:
        print(f"Fehler bei {ip_address}: {e}")
        return False, None, None, None

def main():
    hosts = [
        ("1.1.1.1", "cloudflare")
    ]

    started, ping_count, timeout_ms, selected_hosts = show_start_window(hosts)
    if not started:
        return
    
    print("Ping-Ergebnisse:\n")
    result_lines = []
    latencies = []
    for ip, name in selected_hosts:
        reachable, avg_ms, min_ms, max_ms = ping_host(ip, ping_count, timeout_ms)
        if reachable:
            if avg_ms is not None:
                status = (
                    f"✓ Erreichbar (Ø aus {ping_count} Pings: {avg_ms:.1f} ms, "
                    f"min: {min_ms:.1f} ms, max: {max_ms:.1f} ms)"
                )
                latencies.append(avg_ms)
            else:
                status = "✓ Erreichbar (Latenz unbekannt)"
        else:
            status = "✗ Unerreichbar"

        print(f"{name} ({ip}): {status}")
        result_lines.append(f"{name} ({ip}): {status}")

    if latencies:
        avg_latency = sum(latencies) / len(latencies)
        avg_line = f"Durchschnittslatenz: {avg_latency:.1f} ms"
    else:
        avg_line = "Durchschnittslatenz: nicht verfügbar"

    print(f"\n{avg_line}")
    result_lines.append("")
    result_lines.append(avg_line)

    show_result_window(result_lines)

if __name__ == "__main__":
    main()