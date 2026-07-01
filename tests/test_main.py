from pathlib import Path

import pytest
from fastapi import HTTPException

from app import main
from app.slicer import SlicerError
from tests.conftest import ascii_stl, status_payload, upload_file


class FakeClient:
    def __init__(self, status=None, status_exc=None, upload_exc=None, start_exc=None):
        self.status = status if status is not None else status_payload()
        self.status_exc = status_exc
        self.upload_exc = upload_exc
        self.start_exc = start_exc
        self.uploaded = []
        self.started = []

    def request_status(self):
        if self.status_exc:
            raise self.status_exc
        return self.status

    def upload_project(self, project_path):
        if self.upload_exc:
            raise self.upload_exc
        self.uploaded.append(project_path)
        return "ftp://cache/project.3mf"

    def start_print(self, remote_url, ams_slot, plate_index):
        if self.start_exc:
            raise self.start_exc
        self.started.append({"remote_url": remote_url, "ams_slot": ams_slot, "plate_index": plate_index})
        return {"sent": True, "ack": {"print": {"result": "success"}}}


def _install_fake_client(monkeypatch, client):
    monkeypatch.setattr(main, "bambu_client", lambda settings: client)
    return client


def test_status_returns_trays_and_busy_metadata(settings, monkeypatch):
    client = _install_fake_client(monkeypatch, FakeClient(status=status_payload(state="RUNNING")))

    response = main.status(settings)

    assert client.uploaded == []
    assert response["printer_state"] == "RUNNING"
    assert response["busy"] is True
    assert "RUNNING" in response["busy_reason"]
    assert len(response["trays"]) == 3
    assert response["trays"][0] == {
        "slot": 0,
        "ams_id": "0",
        "tray_id": "0",
        "label": "AMS 0 slot 0: PLA #F7D959FF",
        "filament_type": "PLA",
        "color": "F7D959FF",
    }


def test_status_failure_returns_http_502(settings, monkeypatch):
    _install_fake_client(monkeypatch, FakeClient(status_exc=RuntimeError("offline")))

    with pytest.raises(HTTPException) as exc:
        main.status(settings)

    assert exc.value.status_code == 502
    assert exc.value.detail == "offline"


def test_print_job_success_hands_off_multiple_stls(settings, monkeypatch):
    client = _install_fake_client(monkeypatch, FakeClient())
    rotations = []
    sliced = {}

    def fake_rotate(source, destination, rx, ry, rz):
        rotations.append((Path(source).name, Path(destination).name, rx, ry, rz))
        Path(destination).write_bytes(Path(source).read_bytes() + b"\ntransformed")

    def fake_slice_stls(settings, stls, filament_type, infill_density, wall_loops):
        project = settings.job_dir / "project.3mf"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_bytes(b"project")
        sliced.update(
            {
                "stls": stls,
                "filament_type": filament_type,
                "infill_density": infill_density,
                "wall_loops": wall_loops,
            }
        )
        return project

    monkeypatch.setattr(main, "rotate_and_place_on_bed", fake_rotate)
    monkeypatch.setattr(main, "slice_stls", fake_slice_stls)

    response = main.print_job(
        files=[
            upload_file("first.stl", ascii_stl().encode("utf-8")),
            upload_file("../second.STL", ascii_stl().encode("utf-8")),
        ],
        infill_density=23,
        wall_loops=4,
        copy_counts=[2, 3],
        rot_x=[10, 20],
        rot_y=[30, 40],
        rot_z=[50, 60],
        ams_slot=1,
        settings=settings,
    )

    assert [rotation[2:] for rotation in rotations] == [(10, 30, 50), (20, 40, 60)]
    assert [stl.original_filename for stl in sliced["stls"]] == ["first.stl", "second.STL"]
    assert [stl.copy_count for stl in sliced["stls"]] == [2, 3]
    assert all(stl.path.name.endswith((".stl", ".STL")) for stl in sliced["stls"])
    assert sliced["filament_type"] == "PETG"
    assert sliced["infill_density"] == 23
    assert sliced["wall_loops"] == 4
    assert client.uploaded == [settings.job_dir / "project.3mf"]
    assert client.started == [{"remote_url": "ftp://cache/project.3mf", "ams_slot": 1, "plate_index": settings.default_plate_index}]
    assert response["message"] == "Sent 2 STL file(s), 5 total part(s), using AMS 0 slot 1: PETG #FFFFFFFF"
    assert response["remote_url"] == "ftp://cache/project.3mf"
    assert response["printer_result"] == {"sent": True, "ack": {"print": {"result": "success"}}}


def test_print_job_rejects_empty_file_list_before_printer_access(settings, monkeypatch):
    monkeypatch.setattr(main, "bambu_client", lambda settings: pytest.fail("printer should not be touched"))

    with pytest.raises(HTTPException) as exc:
        main.print_job([], 15, 2, [], [], [], [], 0, settings)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Upload at least one STL file"


def test_print_job_rejects_mismatched_file_metadata_before_printer_access(settings, monkeypatch):
    monkeypatch.setattr(main, "bambu_client", lambda settings: pytest.fail("printer should not be touched"))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Each STL needs copies and X/Y/Z rotation values"


def test_print_job_rejects_non_stl_before_printer_access(settings, monkeypatch):
    monkeypatch.setattr(main, "bambu_client", lambda settings: pytest.fail("printer should not be touched"))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.obj")], 15, 2, [1], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Upload only STL files"


@pytest.mark.parametrize("copy_count", [0, 100])
def test_print_job_rejects_copy_count_outside_supported_range(settings, monkeypatch, copy_count):
    monkeypatch.setattr(main, "bambu_client", lambda settings: pytest.fail("printer should not be touched"))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [copy_count], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Copies must be between 1 and 99"


def test_print_job_status_failure_returns_502(settings, monkeypatch):
    _install_fake_client(monkeypatch, FakeClient(status_exc=TimeoutError("status timeout")))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [1], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 502
    assert exc.value.detail == "Printer status failed: status timeout"


def test_print_job_busy_printer_returns_409_before_slicing_or_upload(settings, monkeypatch):
    client = _install_fake_client(monkeypatch, FakeClient(status=status_payload(state="RUNNING")))
    monkeypatch.setattr(main, "rotate_and_place_on_bed", lambda *args: pytest.fail("transform should not run"))
    monkeypatch.setattr(main, "slice_stls", lambda *args, **kwargs: pytest.fail("slice should not run"))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [1], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 409
    assert "RUNNING" in exc.value.detail
    assert client.uploaded == []
    assert client.started == []


def test_print_job_missing_ams_slot_returns_400(settings, monkeypatch):
    _install_fake_client(monkeypatch, FakeClient())

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [1], [0], [0], [0], 99, settings)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Selected AMS slot is not available"


def test_print_job_transform_failure_returns_400_and_stops(settings, monkeypatch):
    client = _install_fake_client(monkeypatch, FakeClient())
    monkeypatch.setattr(main, "rotate_and_place_on_bed", lambda *args: (_ for _ in ()).throw(ValueError("bad mesh")))
    monkeypatch.setattr(main, "slice_stls", lambda *args, **kwargs: pytest.fail("slice should not run"))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [1], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Could not transform part.stl: bad mesh"
    assert client.uploaded == []
    assert client.started == []


def test_print_job_slicer_failure_returns_500_and_does_not_upload(settings, monkeypatch):
    client = _install_fake_client(monkeypatch, FakeClient())
    monkeypatch.setattr(main, "rotate_and_place_on_bed", lambda source, destination, *args: Path(destination).write_bytes(b"ok"))
    monkeypatch.setattr(main, "slice_stls", lambda *args, **kwargs: (_ for _ in ()).throw(SlicerError("slice failed")))

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [1], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 500
    assert exc.value.detail == "slice failed"
    assert client.uploaded == []
    assert client.started == []


@pytest.mark.parametrize("client", [FakeClient(upload_exc=RuntimeError("upload failed")), FakeClient(start_exc=RuntimeError("start failed"))])
def test_print_job_upload_or_start_failure_returns_502(settings, monkeypatch, client):
    _install_fake_client(monkeypatch, client)
    monkeypatch.setattr(main, "rotate_and_place_on_bed", lambda source, destination, *args: Path(destination).write_bytes(b"ok"))

    def fake_slice(settings, stls, filament_type, infill_density, wall_loops):
        project = settings.job_dir / "project.3mf"
        project.parent.mkdir(parents=True, exist_ok=True)
        project.write_bytes(b"project")
        return project

    monkeypatch.setattr(main, "slice_stls", fake_slice)

    with pytest.raises(HTTPException) as exc:
        main.print_job([upload_file("part.stl")], 15, 2, [1], [0], [0], [0], 0, settings)

    assert exc.value.status_code == 502
    assert exc.value.detail in {"upload failed", "start failed"}
