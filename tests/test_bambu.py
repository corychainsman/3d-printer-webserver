import json
from pathlib import Path

import pytest

from app import bambu
from app.bambu import BambuClient, ImplicitFTP_TLS, ams_trays_from_status, print_state_from_status, printer_busy_reason
from tests.conftest import status_payload


def test_ams_trays_from_status_flattens_multiple_ams_units():
    trays = ams_trays_from_status(status_payload())

    assert [tray.slot for tray in trays] == [0, 1, 2]
    assert trays[0].ams_id == "0"
    assert trays[0].tray_id == "0"
    assert trays[0].filament_type == "PLA"
    assert trays[0].label == "AMS 0 slot 0: PLA #F7D959FF"
    assert trays[1].filament_type == "PETG"
    assert trays[2].label == "AMS 1 slot 0: ABS"


def test_ams_trays_from_status_handles_missing_ams_data():
    assert ams_trays_from_status({"print": {}}) == []
    assert ams_trays_from_status({}) == []


def test_printer_busy_reason_classifies_ready_and_busy_states():
    for state in ["IDLE", "FINISH", "FAILED", "UNKNOWN", ""]:
        assert printer_busy_reason(status_payload(state=state)) is None

    for state in ["RUNNING", "PREPARE", "PAUSE", "SLICING"]:
        reason = printer_busy_reason(status_payload(state=state))
        assert state in reason
        assert "wait for the current job" in reason


def test_print_state_from_status_normalizes_missing_and_lowercase_state():
    assert print_state_from_status(status_payload(state="running")) == "RUNNING"
    assert print_state_from_status({"print": {}}) == ""
    assert print_state_from_status({}) == ""


def test_bambu_client_ams_trays_uses_request_status(monkeypatch):
    client = BambuClient("host", "serial", "code")
    monkeypatch.setattr(client, "request_status", lambda: status_payload())

    assert [tray.label for tray in client.ams_trays()] == [
        "AMS 0 slot 0: PLA #F7D959FF",
        "AMS 0 slot 1: PETG #FFFFFFFF",
        "AMS 1 slot 0: ABS",
    ]


def test_start_print_payload_maps_selected_ams_slot_and_plate(monkeypatch):
    client = BambuClient("host", "SERIAL", "code")
    published = {}

    class Info:
        def wait_for_publish(self, timeout):
            published["wait_timeout"] = timeout

    class FakeMqtt:
        def connect(self, host, port, keepalive):
            published["connect"] = (host, port, keepalive)

        def subscribe(self, topic, qos):
            published["subscribe"] = (topic, qos)

        def loop_start(self):
            published["loop_started"] = True

        def publish(self, topic, payload, qos):
            published["topic"] = topic
            published["payload"] = json.loads(payload)
            published["qos"] = qos
            client._last_ack = {"print": {"command": "project_file", "result": "success"}}
            client._last_report = status_payload(state="PREPARE")
            client._ack_event.set()
            return Info()

        def loop_stop(self):
            published["loop_stopped"] = True

        def disconnect(self):
            published["disconnect"] = True

    monkeypatch.setattr(client, "_client", lambda: FakeMqtt())

    result = client.start_print("file:///sdcard/cache/job.3mf", ams_slot=5, plate_index=2, timeout=0.25)

    payload = published["payload"]["print"]
    assert result == {
        "sent": True,
        "started": True,
        "printer_state": "PREPARE",
        "ack": {"print": {"command": "project_file", "result": "success"}},
    }
    assert payload["url"] == "file:///sdcard/cache/job.3mf"
    assert payload["param"] == "Metadata/plate_2.gcode"
    assert payload["subtask_name"] == "job"
    assert payload["file"] == ""
    assert payload["md5"] == ""
    assert payload["bed_type"] == "auto"
    assert payload["use_ams"] is True
    assert payload["ams_mapping"] == [5]
    assert published["topic"] == "device/SERIAL/request"
    assert published["wait_timeout"] == 0.25


def test_start_print_raises_when_printer_does_not_leave_ready_state(monkeypatch):
    client = BambuClient("host", "SERIAL", "code")

    class Info:
        def wait_for_publish(self, timeout):
            pass

    class FakeMqtt:
        def connect(self, host, port, keepalive):
            pass

        def subscribe(self, topic, qos):
            pass

        def loop_start(self):
            pass

        def publish(self, topic, payload, qos):
            return Info()

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

    monkeypatch.setattr(client, "_client", lambda: FakeMqtt())

    with pytest.raises(RuntimeError) as exc:
        client.start_print("file:///sdcard/cache/job.3mf", ams_slot=0, timeout=0)

    assert "did not start printing" in str(exc.value)


def test_start_print_raises_immediately_when_printer_rejects_command(monkeypatch):
    client = BambuClient("host", "SERIAL", "code")

    class Info:
        def wait_for_publish(self, timeout):
            pass

    class FakeMqtt:
        def connect(self, host, port, keepalive):
            pass

        def subscribe(self, topic, qos):
            pass

        def loop_start(self):
            pass

        def publish(self, topic, payload, qos):
            client._last_ack = {
                "print": {
                    "command": "project_file",
                    "result": "failed",
                    "reason": "mqtt message verify failed",
                }
            }
            client._ack_event.set()
            return Info()

        def loop_stop(self):
            pass

        def disconnect(self):
            pass

    monkeypatch.setattr(client, "_client", lambda: FakeMqtt())

    with pytest.raises(RuntimeError) as exc:
        client.start_print("file:///sdcard/cache/job.3mf", ams_slot=0, timeout=1)

    assert str(exc.value) == "Printer rejected MQTT print command: mqtt message verify failed"


def test_upload_project_uses_implicit_ftps_and_creates_remote_dir(monkeypatch, tmp_path):
    local_file = tmp_path / "plate.3mf"
    local_file.write_bytes(b"3mf")
    calls = []

    class FakeFtp:
        def __init__(self, context):
            self.context = context
            self.cwd_calls = 0
            self.encoding = None

        def connect(self, host, port, timeout):
            calls.append(("connect", host, port, timeout))

        def login(self, user, password):
            calls.append(("login", user, password))

        def prot_p(self):
            calls.append(("prot_p",))

        def cwd(self, remote_dir):
            calls.append(("cwd", remote_dir))
            self.cwd_calls += 1
            if self.cwd_calls == 1:
                raise RuntimeError("missing")

        def mkd(self, remote_dir):
            calls.append(("mkd", remote_dir))

        def storbinary(self, command, handle):
            calls.append(("storbinary", command, handle.read()))

        def quit(self):
            calls.append(("quit",))

    monkeypatch.setattr(bambu, "ImplicitFTP_TLS", FakeFtp)
    monkeypatch.setattr(bambu.time, "time", lambda: 12345)

    remote_url = BambuClient("host", "serial", "code").upload_project(local_file, remote_dir="/cache")

    assert remote_url == "file:///sdcard/cache/12345-plate.3mf"
    assert ("connect", "host", 990, 30) in calls
    assert ("login", "bblp", "code") in calls
    assert ("mkd", "/cache") in calls
    assert ("storbinary", "STOR 12345-plate.3mf", b"3mf") in calls


def test_implicit_ftps_reuses_control_tls_session_for_data_channel(monkeypatch):
    calls = {}

    class FakeContext:
        def wrap_socket(self, conn, server_hostname=None, session=None):
            calls["wrap_socket"] = (conn, server_hostname, session)
            return "wrapped-data-connection"

    class FakeSock:
        session = "control-session"

    def fake_ntransfercmd(self, cmd, rest=None):
        calls["ntransfercmd"] = (cmd, rest)
        return "plain-data-connection", 128

    monkeypatch.setattr(bambu.FTP, "ntransfercmd", fake_ntransfercmd)
    ftp = ImplicitFTP_TLS.__new__(ImplicitFTP_TLS)
    ftp.context = FakeContext()
    ftp.host = "printer.local"
    ftp.sock = FakeSock()
    ftp._prot_p = True

    conn, size = ftp.ntransfercmd("STOR plate.3mf")

    assert conn == "wrapped-data-connection"
    assert size == 128
    assert calls["ntransfercmd"] == ("STOR plate.3mf", None)
    assert calls["wrap_socket"] == ("plain-data-connection", "printer.local", "control-session")
