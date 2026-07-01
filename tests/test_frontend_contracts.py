from app.main import index


def _html(settings):
    return index(settings)


def _submit_handler(html):
    start = html.index('formEl.addEventListener("submit"')
    end = html.index("renderPlaceholderTrays();", start)
    return html[start:end]


def test_upload_control_accepts_multiple_stls_and_appends(settings):
    html = _html(settings)

    assert 'id="files"' in html
    assert 'accept=".stl,model/stl"' in html
    assert "multiple" in html
    assert "Add STL" in html
    assert "fileNameDisplay" not in html
    assert "filesEl.addEventListener(\"change\", loadPreviewFile)" in html
    assert "filesEl.value = \"\";" in html


def test_file_rows_have_stable_remove_identity_and_async_parse_guard(settings):
    html = _html(settings)

    assert "let fileEntrySeq = 0;" in html
    assert "const removedEntryIds = new Set();" in html
    assert "const entryId = fileEntrySeq++;" in html
    assert "row.dataset.entryId = String(entryId);" in html
    assert "menuButton.dataset.entryId = String(entryId);" in html
    assert "removedEntryIds.add(entryId);" in html
    assert "fileEntries = fileEntries.filter((entry) => entry.id !== entryId);" in html
    assert "if (removedEntryIds.has(entryId)) continue;" in html
    assert "clearPreviewModels();" in html
    assert "Choose STL files to preview the arranged plate" in html


def test_per_file_controls_and_submit_formdata_contract(settings):
    html = _html(settings)
    submit_handler = _submit_handler(html)

    assert '"Copies", "copy_counts", "1", "1", "99"' in html
    assert '"Rot X", "rot_x", "0", "-360", "360"' in html
    assert '"Rot Y", "rot_y", "0", "-360", "360"' in html
    assert '"Rot Z", "rot_z", "0", "-360", "360"' in html
    assert "input.addEventListener(\"input\", () =>" in html
    assert "const formData = new FormData();" in submit_handler
    assert 'formData.append("infill_density", infillEl.value);' in submit_handler
    assert 'formData.append("wall_loops", wallsEl.value);' in submit_handler
    assert 'formData.append("files", entry.file, entry.file.name);' in submit_handler
    assert 'formData.append("copy_counts", entry.input.value);' in submit_handler
    assert 'formData.append("rot_x", entry.rotX.value);' in submit_handler
    assert 'formData.append("rot_y", entry.rotY.value);' in submit_handler
    assert 'formData.append("rot_z", entry.rotZ.value);' in submit_handler
    assert 'formData.append("ams_slot", slotEl.value);' in submit_handler
    assert 'body: formData' in submit_handler
    assert 'fetch("/api/print/progress"' in submit_handler
    assert "res.body.getReader();" in submit_handler
    assert "new TextDecoder();" in submit_handler
    assert 'event.type === "progress"' in submit_handler
    assert "msgEl.textContent = event.message;" in submit_handler
    assert "Print workflow ended without a printer start confirmation" in submit_handler
    assert "await loadStatus();" in submit_handler
    assert "const data = await res.json();" not in submit_handler
    assert "Choose at least one STL file" in submit_handler


def test_ams_status_placeholders_color_swatches_and_busy_title(settings):
    html = _html(settings)

    assert 'fetch("/api/status")' in html
    assert 'renderPlaceholderTrays();' in html
    assert "setInterval(loadStatus, 5000);" in html
    assert "for (let index = 0; index < 8; index++)" in html
    assert "normalizeColor(tray.color)" in html
    assert "if (color) swatch.style.background" in html
    assert "if (data.trays.length) chooseTray(data.trays[0].slot);" in html
    assert "data.busy" in html
    assert "Busy:" in html
    assert "statusEl.classList.toggle(\"error\", Boolean(data.busy) || !data.trays.length);" in html


def test_viewer_controls_camera_presets_fit_and_grid_texture(settings):
    html = _html(settings)

    for control_id in ["viewX", "viewY", "viewIso", "viewZ", "zoomIn", "zoomOut", "fitView"]:
        assert f'id="{control_id}"' in html
    assert "camera.up.set(0, 0, 1);" in html
    assert "controls.screenSpacePanning = false;" in html
    assert "const viewSigns = { x: 1, y: 1 };" in html
    assert "viewXEl.addEventListener(\"click\", () => toggleAxis(\"x\", viewXEl));" in html
    assert "viewYEl.addEventListener(\"click\", () => toggleAxis(\"y\", viewYEl));" in html
    assert "viewIsoEl.addEventListener(\"click\", () => setCornerView());" in html
    assert "setCornerView(2, false);" in html
    assert "fitToObjects = !fitToObjects;" in html
    assert 'fitViewEl.setAttribute("aria-pressed", fitToObjects ? "true" : "false");' in html
    assert "canvas.width = 4096;" in html
    assert "const step = canvas.width / 70;" in html
    assert "const isTenMm = index % 2 === 0;" in html
    assert "texture.generateMipmaps = true;" in html


def test_theme_selector_switches_system_css_and_98_css(settings):
    html = _html(settings)

    assert "https://sakofchit.github.io/system.css/system.css" in html
    assert "https://jdan.github.io/98.css/98.css" in html
    assert 'id="themeSelect"' in html
    assert "Macintosh System" in html
    assert "Windows 98" in html
    assert "localStorage.setItem(\"bambu-phone-print-theme\", selectedTheme);" in html
    assert "systemThemeEl.disabled = selectedTheme !== \"system\";" in html
    assert "win98ThemeEl.disabled = selectedTheme !== \"win98\";" in html
