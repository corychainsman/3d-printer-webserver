import json
import ssl
import time
import uuid
from dataclasses import dataclass
from ftplib import FTP, FTP_TLS
from pathlib import Path
from threading import Event, Lock
from typing import Any

import paho.mqtt.client as mqtt


@dataclass(frozen=True)
class AmsTray:
    slot: int
    ams_id: str
    tray_id: str
    label: str
    filament_type: str
    color: str | None


READY_GCODE_STATES = {"", "IDLE", "FINISH", "FAILED", "UNKNOWN"}


def print_state_from_status(status: dict[str, Any]) -> str:
    print_status = status.get("print", {})
    if not isinstance(print_status, dict):
        return ""
    return str(print_status.get("gcode_state") or "").upper()


def printer_busy_reason(status: dict[str, Any]) -> str | None:
    state = print_state_from_status(status)
    if state in READY_GCODE_STATES:
        return None
    return f"Printer is busy ({state}); wait for the current job to finish before sending another print"


def ams_trays_from_status(status: dict[str, Any]) -> list[AmsTray]:
    print_status = status.get("print", {})
    ams = print_status.get("ams", {}) if isinstance(print_status, dict) else {}
    units = ams.get("ams", []) if isinstance(ams, dict) else []
    trays: list[AmsTray] = []
    slot = 0
    for unit in units:
        ams_id = str(unit.get("id", len(trays)))
        for tray in unit.get("tray", []):
            filament_type = str(tray.get("tray_type") or tray.get("tray_sub_brands") or "unknown")
            tray_id = str(tray.get("id", slot))
            color = tray.get("tray_color")
            label = f"AMS {ams_id} slot {tray_id}: {filament_type}"
            if color:
                label = f"{label} #{str(color).lstrip('#')}"
            trays.append(
                AmsTray(
                    slot=slot,
                    ams_id=ams_id,
                    tray_id=tray_id,
                    label=label,
                    filament_type=filament_type,
                    color=color,
                )
            )
            slot += 1
    return trays


class ImplicitFTP_TLS(FTP_TLS):
    def connect(self, host: str = "", port: int = 0, timeout: float | None = None, source_address=None):
        if host:
            self.host = host
        if port:
            self.port = port
        if timeout is not None:
            self.timeout = timeout
        self.sock = self.context.wrap_socket(
            socket_create_connection((self.host, self.port), self.timeout, source_address),
            server_hostname=self.host,
        )
        self.af = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        conn, size = FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn,
                server_hostname=self.host,
                session=self.sock.session,
            )
        return conn, size


def socket_create_connection(address, timeout=None, source_address=None):
    import socket

    return socket.create_connection(address, timeout, source_address)


class BambuClient:
    def __init__(self, host: str, serial: str, access_code: str, mqtt_port: int = 8883, ftps_port: int = 990):
        self.host = host
        self.serial = serial
        self.access_code = access_code
        self.mqtt_port = mqtt_port
        self.ftps_port = ftps_port
        self.report_topic = f"device/{serial}/report"
        self.request_topic = f"device/{serial}/request"
        self._last_report: dict[str, Any] | None = None
        self._last_ack: dict[str, Any] | None = None
        self._report_event = Event()
        self._ack_event = Event()
        self._lock = Lock()

    def _client(self) -> mqtt.Client:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set("bblp", self.access_code)
        client.tls_set(cert_reqs=ssl.CERT_NONE)
        client.tls_insecure_set(True)

        def on_message(_client, _userdata, msg):
            payload = json.loads(msg.payload.decode("utf-8", errors="replace"))
            with self._lock:
                if "print" in payload:
                    self._last_report = payload
                    self._report_event.set()
                    if payload["print"].get("command"):
                        self._last_ack = payload
                        self._ack_event.set()

        client.on_message = on_message
        return client

    def request_status(self, timeout: float = 12.0) -> dict[str, Any]:
        sequence_id = str(uuid.uuid4())
        payload = {"pushing": {"sequence_id": sequence_id, "command": "pushall"}}
        client = self._client()
        self._report_event.clear()
        client.connect(self.host, self.mqtt_port, keepalive=30)
        client.subscribe(self.report_topic, qos=0)
        client.loop_start()
        try:
            client.publish(self.request_topic, json.dumps(payload), qos=0)
            if not self._report_event.wait(timeout):
                raise TimeoutError("Timed out waiting for printer status report")
            with self._lock:
                if not self._last_report:
                    raise RuntimeError("Printer did not return a status report")
                return self._last_report
        finally:
            client.loop_stop()
            client.disconnect()

    def ams_trays(self) -> list[AmsTray]:
        return ams_trays_from_status(self.request_status())

    def upload_project(self, local_file: Path, remote_dir: str = "/cache") -> str:
        remote_name = f"{int(time.time())}-{local_file.name}"
        context = ssl._create_unverified_context()
        ftp = ImplicitFTP_TLS(context=context)
        ftp.encoding = "utf-8"
        ftp.connect(self.host, self.ftps_port, timeout=30)
        ftp.login("bblp", self.access_code)
        ftp.prot_p()
        try:
            try:
                ftp.cwd(remote_dir)
            except Exception:
                ftp.mkd(remote_dir)
                ftp.cwd(remote_dir)
            with local_file.open("rb") as handle:
                ftp.storbinary(f"STOR {remote_name}", handle)
        finally:
            ftp.quit()
        return f"ftp://{remote_dir.strip('/')}/{remote_name}"

    def start_print(self, project_url: str, ams_slot: int, plate_index: int = 1, timeout: float = 12.0) -> dict[str, Any]:
        sequence_id = "0"
        payload = {
            "print": {
                "sequence_id": sequence_id,
                "command": "project_file",
                "param": f"Metadata/plate_{plate_index}.gcode",
                "project_id": "0",
                "subtask_id": "0",
                "task_id": "0",
                "url": project_url,
                "profile_id": "0",
                "timelapse": False,
                "bed_leveling": True,
                "flow_cali": False,
                "vibration_cali": False,
                "layer_inspect": True,
                "use_ams": True,
                "ams_mapping": [ams_slot],
            }
        }
        client = self._client()
        self._ack_event.clear()
        client.connect(self.host, self.mqtt_port, keepalive=30)
        client.subscribe(self.report_topic, qos=0)
        client.loop_start()
        try:
            info = client.publish(self.request_topic, json.dumps(payload), qos=1)
            info.wait_for_publish(timeout=timeout)
            if not self._ack_event.wait(timeout):
                return {"sent": True, "ack": None}
            with self._lock:
                return {"sent": True, "ack": self._last_ack}
        finally:
            client.loop_stop()
            client.disconnect()
