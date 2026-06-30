import html
import shutil
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from .bambu import BambuClient
from .config import Settings, get_settings
from .slicer import SlicerError, StlInput, slice_stls
from .stl_transform import rotate_and_place_on_bed

app = FastAPI(title="Bambu Phone Print")


def bambu_client(settings: Settings) -> BambuClient:
    return BambuClient(
        host=settings.bambu_host,
        serial=settings.bambu_serial,
        access_code=settings.bambu_access_code,
        mqtt_port=settings.bambu_mqtt_port,
        ftps_port=settings.bambu_ftps_port,
    )


@app.get("/", response_class=HTMLResponse)
def index(settings: Settings = Depends(get_settings)) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Bambu Phone Print</title>
  <link id="systemTheme" rel="stylesheet" href="https://sakofchit.github.io/system.css/system.css" />
  <link id="win98Theme" rel="stylesheet" href="https://jdan.github.io/98.css/98.css" disabled />
  <style>
    :root {{
      color-scheme: light;
      font-family: Chicago_12, Chicago, Geneva, system-ui, sans-serif;
      background: var(--sys-color-grey, #bfbfbf);
      color: #000;
    }}
    body {{ margin: 0; padding: 18px; background: var(--sys-color-grey, #bfbfbf); }}
    body.theme-win98 {{ background: #008080; }}
    main {{ max-width: 1120px; margin: 0 auto; }}
    .print-window {{ margin: 0; min-width: 0; width: 100%; }}
    .print-window .title-bar {{ margin: 0; }}
    .print-window .title {{
      max-width: min(72vw, 620px);
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 1rem;
    }}
    .win-controls {{ display: none; }}
    .theme-win98 .mac-control {{ display: none; }}
    .theme-win98 .win-controls {{ display: flex; }}
    .theme-win98 .print-window .title {{
      margin: 0;
      padding: 0;
      font-family: "Pixelated MS Sans Serif", Arial, sans-serif;
      font-size: 11px;
      font-weight: 700;
      background: transparent;
      color: #fff;
      line-height: 1;
    }}
    .print-window .window-pane {{
      padding: 14px;
      overflow: visible;
      height: auto;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .theme-win98 .print-window .window-pane {{
      font-family: "Pixelated MS Sans Serif", Arial, sans-serif;
      font-size: 11px;
      padding: 12px;
    }}
    form {{
      background: #fff;
      margin-bottom: 16px;
    }}
    .theme-win98 form {{ background: silver; }}
    .workspace {{
      display: grid;
      grid-template-columns: minmax(0, 1.45fr) minmax(300px, .75fr);
      gap: 18px;
      align-items: start;
    }}
    .panel {{ min-width: 0; }}
    .section-head {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .section-title {{ margin: 0; font-family: Chicago; font-size: 1rem; color: #000; }}
    .summary {{ color: #000; font-size: .86rem; white-space: nowrap; }}
    label {{ display: block; margin: 0 0 6px; font-weight: 650; }}
    .ams-label {{ margin-top: 14px; margin-bottom: 10px; }}
    .upload-row {{
      display: grid;
      gap: 6px;
      margin-bottom: 12px;
    }}
    .upload-meta {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      min-width: 0;
    }}
    .upload-meta label {{ margin: 0; }}
    .file-picker-row {{
      display: flex;
      align-items: center;
      width: 100%;
    }}
    .file-input {{
      position: absolute;
      inline-size: 1px;
      block-size: 1px;
      opacity: 0;
      pointer-events: none;
    }}
    .file-trigger {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 38px;
      padding: 0 16px;
      background: #fff;
      color: #000;
      font-weight: 750;
      cursor: pointer;
      white-space: nowrap;
      width: 100%;
      box-sizing: border-box;
    }}
    .theme-win98 .file-trigger {{
      min-height: 26px;
      padding: 4px 12px;
      font-weight: 400;
    }}
    .file-trigger.btn {{
      border: 2px solid #000;
      box-shadow: inset 0 0 0 2px #fff, inset 0 0 0 4px #000;
    }}
    .theme-win98 .file-trigger.btn {{
      border: 2px outset #fff;
      box-shadow: 1px 1px 0 #000;
    }}
    input, select, button {{
      width: 100%;
      box-sizing: border-box;
      font: inherit;
      min-height: 38px;
      border-radius: 0;
      border: 1.5px solid #000;
      padding: 6px 8px;
      background: #fff;
      color: #000;
    }}
    .theme-win98 input, .theme-win98 select, .theme-win98 button {{
      min-height: 23px;
      border: revert;
      padding: revert;
    }}
    input[type="range"] {{ padding: 0; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .tray-list {{
      --tray-row-height: 44px;
      --tray-gap: 8px;
      display: grid;
      gap: var(--tray-gap);
      height: calc(var(--tray-row-height) * 8 + var(--tray-gap) * 7);
      overflow: auto;
      padding: 8px;
      border: 1.5px solid #000;
      background: #fff;
    }}
    .theme-win98 .tray-list {{
      border: inset 2px #fff;
      padding: 6px;
    }}
    .tray-option {{
      display: flex;
      align-items: center;
      gap: 10px;
      width: 100%;
      height: var(--tray-row-height);
      min-height: var(--tray-row-height);
      padding: 9px 10px;
      border: 1.5px solid #000;
      border-radius: 0;
      background: #fff;
      color: #000;
      text-align: left;
      font: inherit;
    }}
    .theme-win98 .tray-option {{
      min-height: var(--tray-row-height);
      border: 0;
      padding: 4px 6px;
      box-shadow: none;
    }}
    .tray-option[aria-pressed="true"] {{
      background: #000;
      color: #fff;
      box-shadow: none;
    }}
    .theme-win98 .tray-option[aria-pressed="true"] {{
      background: navy;
      color: #fff;
    }}
    .tray-option.placeholder {{
      color: #666;
      border-style: dashed;
      pointer-events: none;
    }}
    .swatch {{
      width: 18px;
      height: 18px;
      flex: 0 0 18px;
      border-radius: 50%;
      border: 1.5px solid #000;
      background: linear-gradient(135deg, #f4f4f4, #a8a8a8);
    }}
    .tray-text {{ overflow-wrap: anywhere; }}
    .hex {{ color: inherit; }}
    .preview {{
      position: relative;
      height: 390px;
      margin: 12px 0 14px;
      overflow: hidden;
      border: 2px solid #000;
      border-radius: 0;
      background: #e9ece5;
    }}
    .theme-win98 .preview {{ border: inset 2px #fff; }}
    #previewCanvas {{ display: block; width: 100%; height: 100%; }}
    .view-controls {{
      position: absolute;
      top: 8px;
      right: 8px;
      display: flex;
      gap: 6px;
      z-index: 2;
    }}
    .view-controls button, .menu-button, .menu-popover button {{
      width: auto;
      min-height: 0;
      padding: 4px 9px;
      border-radius: 0;
      border: 1.5px solid #000;
      background: #fff;
      color: #000;
      font: inherit;
      line-height: 1;
    }}
    .theme-win98 .view-controls button, .theme-win98 .menu-button, .theme-win98 .menu-popover button {{
      min-height: 23px;
      padding: 2px 8px;
      border: revert;
      background: revert;
      line-height: normal;
    }}
    .view-controls button {{ font-weight: 750; }}
    .view-controls button[aria-pressed="true"] {{
      background: #000;
      color: #fff;
      box-shadow: none;
    }}
    .theme-win98 .view-controls button[aria-pressed="true"] {{
      background: navy;
      color: #fff;
    }}
    .preview-empty {{
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      padding: 18px;
      color: #000;
      font-weight: 650;
      text-align: center;
      text-shadow: 0 1px 0 rgba(255,255,255,.35);
      pointer-events: none;
    }}
    .file-list {{
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }}
    .file-row {{
      display: grid;
      gap: 8px;
      padding: 10px;
      border: 1.5px solid #000;
      border-radius: 0;
      background: #fff;
    }}
    .theme-win98 .file-row {{
      border: inset 2px #fff;
      background: silver;
    }}
    .file-row-head {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      align-items: center;
      gap: 10px;
    }}
    .file-controls {{
      display: grid;
      grid-template-columns: repeat(4, minmax(66px, 1fr));
      gap: 8px;
    }}
    .job-settings {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .file-menu {{ position: relative; justify-self: end; align-self: center; display: flex; align-items: center; }}
    .menu-button {{ min-width: 34px; height: 34px; font-weight: 750; display: inline-flex; align-items: center; justify-content: center; }}
    .menu-popover {{
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      display: none;
      min-width: 120px;
      padding: 6px;
      border: 1.5px solid #000;
      border-radius: 0;
      background: #fff;
      box-shadow: 2px 2px 0 #000;
      z-index: 3;
    }}
    .theme-win98 .menu-popover {{
      border: outset 2px #fff;
      box-shadow: 1px 1px 0 #000;
      background: silver;
    }}
    .file-menu.open .menu-popover {{ display: block; }}
    .menu-popover button {{
      width: 100%;
      text-align: left;
      color: #000;
      background: transparent;
      border: 0;
    }}
    .menu-popover button:hover, .menu-popover button:focus {{
      background: #000;
      color: #fff;
    }}
    .file-name {{
      overflow-wrap: anywhere;
      font-weight: 650;
      font-size: .95rem;
    }}
    .file-row label {{ margin: 0 0 4px; font-size: .82rem; }}
    .file-row input {{ min-height: 38px; padding: 7px 8px; }}
    .action-panel {{
      position: sticky;
      top: 14px;
    }}
    @media (max-width: 620px) {{
      body {{ padding: 14px; }}
      .upload-meta {{ display: grid; gap: 3px; }}
      .file-picker-row {{ align-items: stretch; }}
      .workspace {{ display: block; }}
      .preview {{ height: 300px; }}
      .file-controls {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .job-settings {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .action-panel {{ position: static; margin-top: 16px; }}
    }}
    @media (min-width: 621px) and (max-width: 980px) {{
      .workspace {{ grid-template-columns: 1fr; }}
      .file-controls {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
      .action-panel {{ position: static; }}
    }}
    #submit {{
      margin-top: 14px;
      min-height: 46px;
      width: 100%;
      background: #000;
      color: #fff;
      border: 2px solid #000;
      box-shadow: 0 0 0 3px #fff, 0 0 0 5px #000;
      font-weight: 750;
      font-size: 1.05rem;
    }}
    #submit:disabled {{ color: #777; }}
    .theme-win98 #submit {{
      min-height: 34px;
      background: #000080;
      color: #fff;
      border: 2px outset #fff;
      box-shadow: 1px 1px 0 #000;
      font-size: 12px;
      font-weight: 700;
    }}
    .theme-win98 #submit:active {{ border-style: inset; }}
    .hint, #message {{ color: #000; font-size: .92rem; margin-bottom: 0; }}
    .error {{ color: #000; font-weight: 750; }}
    .ok {{ color: #000; font-weight: 750; }}
    .theme-select-row {{
      display: grid;
      gap: 6px;
      margin-top: 12px;
    }}
  </style>
</head>
<body class="theme-system">
<main>
  <form id="printForm" class="window print-window">
    <div class="title-bar">
      <button aria-label="Close" class="close mac-control" type="button"></button>
      <h1 id="windowTitle" class="title title-bar-text">Checking printer...</h1>
      <div class="title-bar-controls win-controls" aria-hidden="true">
        <button aria-label="Minimize" type="button"></button>
        <button aria-label="Maximize" type="button"></button>
        <button aria-label="Close" type="button"></button>
      </div>
      <button aria-label="Resize" class="resize mac-control" type="button"></button>
    </div>
    <div class="separator"></div>
    <div class="window-pane">
      <div class="workspace">
      <section class="panel">
        <div class="upload-row">
          <div class="upload-meta">
            <label for="files">STL file(s)</label>
            <input id="files" class="file-input" type="file" accept=".stl,model/stl" multiple />
          </div>
          <div class="file-picker-row">
            <label for="files" class="file-trigger btn">Add STL</label>
          </div>
        </div>
        <div class="preview">
          <canvas id="previewCanvas"></canvas>
          <div class="view-controls" aria-label="Camera views">
            <button class="btn" type="button" id="viewX" title="View along X axis">+X</button>
            <button class="btn" type="button" id="viewY" title="View along Y axis">+Y</button>
            <button class="btn" type="button" id="viewIso" title="Cycle top corner views">45&deg;</button>
            <button class="btn" type="button" id="viewZ" title="View from above">Z</button>
            <button class="btn" type="button" id="zoomIn" title="Zoom in">+</button>
            <button class="btn" type="button" id="zoomOut" title="Zoom out">-</button>
            <button class="btn" type="button" id="fitView" title="Fit preset views to loaded objects" aria-pressed="false">Fit</button>
          </div>
          <div id="previewEmpty" class="preview-empty">Choose STL files to preview the arranged plate</div>
        </div>
        <div id="fileList" class="file-list"></div>
      </section>

      <aside class="panel action-panel">
        <div class="job-settings">
          <div>
            <label for="infill">Infill %</label>
            <input id="infill" name="infill_density" type="number" min="0" max="100" step="1" value="{settings.default_infill_density}" />
          </div>
          <div>
            <label for="walls">Walls</label>
            <input id="walls" name="wall_loops" type="number" min="1" max="10" step="1" value="{settings.default_wall_loops}" />
          </div>
        </div>
        <label for="slot" class="ams-label">AMS filament</label>
        <input id="slot" name="ams_slot" type="hidden" required />
        <div id="slotList" class="tray-list"></div>
        <button id="submit" class="btn btn-default default" type="submit">Slice and Print</button>
        <p id="message"></p>
        <div class="theme-select-row">
          <label for="themeSelect">Interface</label>
          <select id="themeSelect">
            <option value="system">Macintosh System</option>
            <option value="win98">Windows 98</option>
          </select>
        </div>
      </aside>
      </div>
    </div>
  </form>
</main>
<script type="module">
import * as THREE from "https://esm.sh/three@0.165.0";
import {{ STLLoader }} from "https://esm.sh/three@0.165.0/examples/jsm/loaders/STLLoader.js";
import {{ OrbitControls }} from "https://esm.sh/three@0.165.0/examples/jsm/controls/OrbitControls.js";

const statusEl = document.querySelector("#windowTitle");
const slotEl = document.querySelector("#slot");
const slotListEl = document.querySelector("#slotList");
const formEl = document.querySelector("#printForm");
const msgEl = document.querySelector("#message");
const submitEl = document.querySelector("#submit");
const filesEl = document.querySelector("#files");
const fileListEl = document.querySelector("#fileList");
const infillEl = document.querySelector("#infill");
const wallsEl = document.querySelector("#walls");
const previewCanvas = document.querySelector("#previewCanvas");
const previewEmpty = document.querySelector("#previewEmpty");
const viewXEl = document.querySelector("#viewX");
const viewYEl = document.querySelector("#viewY");
const viewIsoEl = document.querySelector("#viewIso");
const viewZEl = document.querySelector("#viewZ");
const zoomInEl = document.querySelector("#zoomIn");
const zoomOutEl = document.querySelector("#zoomOut");
const fitViewEl = document.querySelector("#fitView");
const themeSelectEl = document.querySelector("#themeSelect");
const systemThemeEl = document.querySelector("#systemTheme");
const win98ThemeEl = document.querySelector("#win98Theme");
const loader = new STLLoader();
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 2000);
camera.up.set(0, 0, 1);
const renderer = new THREE.WebGLRenderer({{ canvas: previewCanvas, antialias: true, alpha: true }});
const controls = new OrbitControls(camera, previewCanvas);
const plate = new THREE.Group();
let fileEntries = [];
let fileEntrySeq = 0;
const viewSigns = {{ x: 1, y: 1 }};
let isoIndex = 3;
let fitToObjects = false;
scene.add(new THREE.HemisphereLight(0xffffff, 0x6f776f, 2.4));
scene.add(plate);
controls.enableDamping = true;
controls.screenSpacePanning = false;
controls.target.set(0, 0, 0);

function applyTheme(theme) {{
  const selectedTheme = theme === "win98" ? "win98" : "system";
  document.body.classList.toggle("theme-win98", selectedTheme === "win98");
  document.body.classList.toggle("theme-system", selectedTheme === "system");
  systemThemeEl.disabled = selectedTheme !== "system";
  win98ThemeEl.disabled = selectedTheme !== "win98";
  themeSelectEl.value = selectedTheme;
  localStorage.setItem("bambu-phone-print-theme", selectedTheme);
  requestAnimationFrame(resizePreview);
}}

applyTheme(localStorage.getItem("bambu-phone-print-theme") || "system");

function makeBuildPlateTexture() {{
  const canvas = document.createElement("canvas");
  canvas.width = 4096;
  canvas.height = 4096;
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#d8ddd4";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const step = canvas.width / 70;
  for (let index = 0; index <= 70; index++) {{
    const pos = Math.round(index * step) + 0.5;
    const isTenMm = index % 2 === 0;
    ctx.strokeStyle = isTenMm ? "rgba(126, 135, 128, 0.62)" : "rgba(184, 191, 181, 0.58)";
    ctx.lineWidth = isTenMm ? 1.6 : 1;
    ctx.beginPath();
    ctx.moveTo(pos, 0);
    ctx.lineTo(pos, canvas.height);
    ctx.moveTo(0, pos);
    ctx.lineTo(canvas.width, pos);
    ctx.stroke();
  }}
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = Math.min(renderer.capabilities.getMaxAnisotropy(), 16);
  texture.minFilter = THREE.LinearMipmapLinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = true;
  return texture;
}}

const bed = new THREE.Mesh(
  new THREE.BoxGeometry(350, 350, 2),
  new THREE.MeshStandardMaterial({{ map: makeBuildPlateTexture(), roughness: 0.82 }})
);
bed.position.z = -1.2;
plate.add(bed);

function resizePreview() {{
  const rect = previewCanvas.getBoundingClientRect();
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(rect.width, rect.height, false);
  camera.aspect = rect.width / Math.max(rect.height, 1);
  camera.updateProjectionMatrix();
}}

function clearPreviewModels() {{
  for (const child of [...plate.children]) {{
    if (child !== bed) plate.remove(child);
  }}
}}

function previewBounds() {{
  const targets = plate.children.filter((child) => child !== bed);
  const box = new THREE.Box3();
  if (fitToObjects && targets.length) {{
    for (const child of targets) box.expandByObject(child);
  }} else {{
    box.setFromObject(plate);
  }}
  const sphere = new THREE.Sphere();
  box.getBoundingSphere(sphere);
  return sphere;
}}

function cameraFrame() {{
  const targets = plate.children.filter((child) => child !== bed);
  const targetBox = new THREE.Box3();
  const frameBox = new THREE.Box3();
  if (targets.length) {{
    for (const child of targets) {{
      targetBox.expandByObject(child);
      frameBox.expandByObject(child);
    }}
    if (!fitToObjects) frameBox.expandByObject(bed);
  }} else {{
    targetBox.setFromObject(bed);
    frameBox.copy(targetBox);
  }}
  const targetSphere = new THREE.Sphere();
  const frameSphere = new THREE.Sphere();
  targetBox.getBoundingSphere(targetSphere);
  frameBox.getBoundingSphere(frameSphere);
  return {{ targetSphere, frameSphere }};
}}

function arrangePreview() {{
  clearPreviewModels();
  if (!fileEntries.length) return;
  previewEmpty.style.display = "none";
  const arranged = [];
  const margin = 12;
  for (const entry of fileEntries) {{
    const count = Math.max(1, Math.min(99, Number.parseInt(entry.input.value || "1", 10)));
    entry.input.value = String(count);
    const geometry = entry.geometry.clone();
    geometry.rotateX(THREE.MathUtils.degToRad(Number.parseFloat(entry.rotX.value || "0")));
    geometry.rotateY(THREE.MathUtils.degToRad(Number.parseFloat(entry.rotY.value || "0")));
    geometry.rotateZ(THREE.MathUtils.degToRad(Number.parseFloat(entry.rotZ.value || "0")));
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const size = new THREE.Vector3();
    const center = new THREE.Vector3();
    box.getSize(size);
    box.getCenter(center);
    geometry.translate(-center.x, -center.y, -box.min.z);
    geometry.computeBoundingBox();
    geometry.boundingBox.getSize(size);
    for (let copy = 0; copy < count; copy++) {{
      arranged.push({{ geometry, size, color: entry.color }});
    }}
  }}
  if (!arranged.length) return;
  const maxX = Math.max(...arranged.map((item) => item.size.x));
  const maxY = Math.max(...arranged.map((item) => item.size.y));
  const maxZ = Math.max(...arranged.map((item) => item.size.z));
  const columns = Math.max(1, Math.ceil(Math.sqrt(arranged.length)));
  const rows = Math.max(1, Math.ceil(arranged.length / columns));
  const stepX = Math.max(maxX + margin, 18);
  const stepY = Math.max(maxY + margin, 18);
  const totalX = (columns - 1) * stepX;
  const totalY = (rows - 1) * stepY;
  arranged.forEach((item, index) => {{
    const material = new THREE.MeshStandardMaterial({{ color: item.color, metalness: 0.02, roughness: 0.55 }});
    const mesh = new THREE.Mesh(item.geometry, material);
    const col = index % columns;
    const row = Math.floor(index / columns);
    mesh.position.set(col * stepX - totalX / 2, row * stepY - totalY / 2, 0);
    plate.add(mesh);
  }});
  setCornerView(2, false);
}}

function setAxisView(axis, sign = 1) {{
  const {{ targetSphere, frameSphere }} = cameraFrame();
  const targetZ = Math.max(targetSphere.center.z, 0);
  const distance = Math.max(fitToObjects ? 36 : 320, frameSphere.radius * (fitToObjects ? 2.6 : 2.2));
  controls.target.set(targetSphere.center.x, targetSphere.center.y, targetZ);
  if (axis === "x") camera.position.set(targetSphere.center.x + sign * distance, targetSphere.center.y, targetZ);
  if (axis === "y") camera.position.set(targetSphere.center.x, targetSphere.center.y + sign * distance, targetZ);
  if (axis === "z") camera.position.set(targetSphere.center.x, targetSphere.center.y, targetZ + distance);
  camera.up.set(0, 0, 1);
  if (axis === "z") camera.up.set(0, 1, 0);
  controls.minDistance = Math.max(1, frameSphere.radius * 0.15);
  controls.maxDistance = Math.max(800, frameSphere.radius * 8);
  controls.update();
}}

function toggleAxis(axis, button) {{
  const sign = viewSigns[axis];
  setAxisView(axis, sign);
  viewSigns[axis] = -sign;
  button.textContent = `${{viewSigns[axis] > 0 ? "+" : "-"}}${{axis.toUpperCase()}}`;
}}

function setCornerView(index = isoIndex, advance = true) {{
  const corners = [
    [1, 1],
    [-1, 1],
    [-1, -1],
    [1, -1],
  ];
  const [sx, sy] = corners[index % corners.length];
  if (advance) isoIndex = (index + 1) % corners.length;
  const {{ targetSphere, frameSphere }} = cameraFrame();
  const distance = Math.max(fitToObjects ? 42 : 360, frameSphere.radius * (fitToObjects ? 2.8 : 2.1));
  const targetZ = Math.max(targetSphere.center.z, 0);
  controls.target.set(targetSphere.center.x, targetSphere.center.y, targetZ);
  camera.position.set(targetSphere.center.x + sx * distance * 0.72, targetSphere.center.y + sy * distance * 0.72, targetZ + distance * 0.58);
  camera.up.set(0, 0, 1);
  controls.minDistance = Math.max(1, frameSphere.radius * 0.15);
  controls.maxDistance = Math.max(800, frameSphere.radius * 8);
  controls.update();
}}

function zoomBy(factor) {{
  const direction = new THREE.Vector3().subVectors(camera.position, controls.target);
  direction.multiplyScalar(factor);
  camera.position.copy(controls.target).add(direction);
  controls.update();
}}

function toggleFitView() {{
  fitToObjects = !fitToObjects;
  fitViewEl.setAttribute("aria-pressed", fitToObjects ? "true" : "false");
}}

async function loadPreviewFile() {{
  const files = [...(filesEl.files || [])];
  if (!files.length) {{
    return;
  }}
  previewEmpty.textContent = "Loading preview...";
  previewEmpty.style.display = "grid";
  for (const file of files) {{
    const index = fileEntrySeq++;
    const row = document.createElement("div");
    row.className = "file-row";
    const name = document.createElement("div");
    name.className = "file-name";
    name.textContent = file.name;
    const makeNumber = (id, labelText, name, value, min, max) => {{
      const wrap = document.createElement("div");
      const label = document.createElement("label");
      label.setAttribute("for", id);
      label.textContent = labelText;
      const input = document.createElement("input");
      input.id = id;
      input.name = name;
      input.type = "number";
      input.min = min;
      input.max = max;
      input.step = "1";
      input.value = value;
      input.addEventListener("input", () => {{
        arrangePreview();
      }});
      wrap.append(label, input);
      return {{ wrap, input }};
    }};
    const copies = makeNumber(`copies-${{index}}`, "Copies", "copy_counts", "1", "1", "99");
    const rotX = makeNumber(`rot-x-${{index}}`, "Rot X", "rot_x", "0", "-360", "360");
    const rotY = makeNumber(`rot-y-${{index}}`, "Rot Y", "rot_y", "0", "-360", "360");
    const rotZ = makeNumber(`rot-z-${{index}}`, "Rot Z", "rot_z", "0", "-360", "360");
    const menu = document.createElement("div");
    menu.className = "file-menu";
    const menuButton = document.createElement("button");
    menuButton.type = "button";
    menuButton.className = "menu-button btn";
    menuButton.setAttribute("aria-label", `Actions for ${{file.name}}`);
    menuButton.textContent = "...";
    const popover = document.createElement("div");
    popover.className = "menu-popover";
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "btn";
    removeButton.textContent = "Remove";
    popover.append(removeButton);
    menu.append(menuButton, popover);
    menuButton.addEventListener("click", (event) => {{
      event.stopPropagation();
      for (const openMenu of fileListEl.querySelectorAll(".file-menu.open")) {{
        if (openMenu !== menu) openMenu.classList.remove("open");
      }}
      menu.classList.toggle("open");
    }});
    removeButton.addEventListener("click", () => {{
      fileEntries = fileEntries.filter((entry) => entry.file !== file);
      row.remove();
      menu.classList.remove("open");
      if (!fileEntries.length) {{
        clearPreviewModels();
        previewEmpty.textContent = "Choose STL files to preview the arranged plate";
        previewEmpty.style.display = "grid";
      }} else {{
        arrangePreview();
      }}
    }});
    const head = document.createElement("div");
    head.className = "file-row-head";
    head.append(name, menu);
    const controls = document.createElement("div");
    controls.className = "file-controls";
    controls.append(copies.wrap, rotX.wrap, rotY.wrap, rotZ.wrap);
    row.append(head, controls);
    fileListEl.appendChild(row);
    const buffer = await file.arrayBuffer();
    fileEntries.push({{
      file,
      input: copies.input,
      rotX: rotX.input,
      rotY: rotY.input,
      rotZ: rotZ.input,
      geometry: loader.parse(buffer),
      color: [0x70b7a1, 0x8ab6d6, 0xd69a7e, 0xa893c7, 0xc2b85d][index % 5],
    }});
  }}
  filesEl.value = "";
  arrangePreview();
}}

function animatePreview() {{
  resizePreview();
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(animatePreview);
}}

filesEl.addEventListener("change", loadPreviewFile);
viewXEl.addEventListener("click", () => toggleAxis("x", viewXEl));
viewYEl.addEventListener("click", () => toggleAxis("y", viewYEl));
viewIsoEl.addEventListener("click", () => setCornerView());
viewZEl.addEventListener("click", () => setAxisView("z"));
zoomInEl.addEventListener("click", () => zoomBy(0.78));
zoomOutEl.addEventListener("click", () => zoomBy(1.28));
fitViewEl.addEventListener("click", toggleFitView);
themeSelectEl.addEventListener("change", () => applyTheme(themeSelectEl.value));
document.addEventListener("click", () => {{
  for (const openMenu of fileListEl.querySelectorAll(".file-menu.open")) openMenu.classList.remove("open");
}});
window.addEventListener("resize", resizePreview);
animatePreview();

function normalizeColor(color) {{
  if (!color) return null;
  const hex = String(color).replace("#", "").slice(0, 8);
  if (!/^[0-9a-fA-F]{{6}}([0-9a-fA-F]{{2}})?$/.test(hex)) return null;
  return hex;
}}

function trayLabel(tray) {{
  const color = normalizeColor(tray.color);
  const base = `AMS ${{tray.ams_id}} slot ${{tray.tray_id}}: ${{tray.filament_type}}`;
  return color ? `${{base}} #${{color}}` : base;
}}

function chooseTray(slot) {{
  slotEl.value = slot;
  for (const button of slotListEl.querySelectorAll(".tray-option")) {{
    button.setAttribute("aria-pressed", button.dataset.slot === String(slot) ? "true" : "false");
  }}
}}

function renderPlaceholderTrays(text = "Loading AMS tray...") {{
  slotListEl.innerHTML = "";
  for (let index = 0; index < 8; index++) {{
    const button = document.createElement("button");
    button.type = "button";
    button.className = "tray-option placeholder";
    button.setAttribute("aria-pressed", "false");

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.className = "tray-text";
    label.textContent = `${{text}} ${{index + 1}}`;

    button.append(swatch, label);
    slotListEl.appendChild(button);
  }}
}}

async function loadStatus() {{
  try {{
    const res = await fetch("/api/status");
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Status failed");
    slotListEl.innerHTML = "";
    for (const tray of data.trays) {{
      const color = normalizeColor(tray.color);
      const button = document.createElement("button");
      button.type = "button";
      button.className = "tray-option";
      button.dataset.slot = tray.slot;
      button.setAttribute("aria-pressed", "false");
      button.addEventListener("click", () => chooseTray(tray.slot));

      const swatch = document.createElement("span");
      swatch.className = "swatch";
      swatch.setAttribute("aria-hidden", "true");
      if (color) swatch.style.background = `#${{color.slice(0, 6)}}`;

      const text = document.createElement("span");
      text.className = "tray-text";
      text.textContent = trayLabel(tray);

      button.append(swatch, text);
      slotListEl.appendChild(button);
    }}
    if (data.trays.length) chooseTray(data.trays[0].slot);
    statusEl.textContent = data.trays.length ? `Ready | ${{data.trays.length}} AMS trays | {html.escape(settings.bambu_host)}` : `No AMS trays | {html.escape(settings.bambu_host)}`;
    statusEl.classList.toggle("ok", Boolean(data.trays.length));
    statusEl.classList.toggle("error", !data.trays.length);
  }} catch (err) {{
    statusEl.textContent = err.message;
    statusEl.classList.remove("ok");
    statusEl.classList.add("error");
  }}
}}

formEl.addEventListener("submit", async (event) => {{
  event.preventDefault();
  if (!fileEntries.length) {{
    msgEl.textContent = "Choose at least one STL file";
    msgEl.className = "error";
    return;
  }}
  const data = new FormData();
  data.append("infill_density", infillEl.value);
  data.append("wall_loops", wallsEl.value);
  for (const entry of fileEntries) {{
    data.append("files", entry.file, entry.file.name);
    data.append("copy_counts", entry.input.value);
    data.append("rot_x", entry.rotX.value);
    data.append("rot_y", entry.rotY.value);
    data.append("rot_z", entry.rotZ.value);
  }}
  data.append("ams_slot", slotEl.value);
  submitEl.disabled = true;
  msgEl.textContent = "Uploading and slicing...";
  msgEl.className = "";
  try {{
    const res = await fetch("/api/print", {{ method: "POST", body: data }});
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Print failed");
    msgEl.textContent = data.message;
    msgEl.className = "ok";
  }} catch (err) {{
    msgEl.textContent = err.message;
    msgEl.className = "error";
  }} finally {{
    submitEl.disabled = false;
  }}
}});

renderPlaceholderTrays();
loadStatus();
</script>
</body>
</html>"""


@app.get("/api/status")
def status(settings: Settings = Depends(get_settings)):
    try:
        trays = bambu_client(settings).ams_trays()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "trays": [
            {
                "slot": tray.slot,
                "ams_id": tray.ams_id,
                "tray_id": tray.tray_id,
                "label": tray.label,
                "filament_type": tray.filament_type,
                "color": tray.color,
            }
            for tray in trays
        ]
    }


@app.post("/api/print")
def print_job(
    files: list[UploadFile] = File(...),
    infill_density: int = Form(..., ge=0, le=100),
    wall_loops: int = Form(..., ge=1, le=10),
    copy_counts: list[int] = Form(...),
    rot_x: list[float] = Form(...),
    rot_y: list[float] = Form(...),
    rot_z: list[float] = Form(...),
    ams_slot: int = Form(..., ge=0),
    settings: Settings = Depends(get_settings),
):
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one STL file")
    if not (len(files) == len(copy_counts) == len(rot_x) == len(rot_y) == len(rot_z)):
        raise HTTPException(status_code=400, detail="Each STL needs copies and X/Y/Z rotation values")
    for uploaded in files:
        if not uploaded.filename or not uploaded.filename.lower().endswith(".stl"):
            raise HTTPException(status_code=400, detail="Upload only STL files")
    for count in copy_counts:
        if count < 1 or count > 99:
            raise HTTPException(status_code=400, detail="Copies must be between 1 and 99")

    client = bambu_client(settings)
    try:
        trays = client.ams_trays()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Printer status failed: {exc}") from exc

    selected = next((tray for tray in trays if tray.slot == ams_slot), None)
    if selected is None:
        raise HTTPException(status_code=400, detail="Selected AMS slot is not available")

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.job_dir.mkdir(parents=True, exist_ok=True)
    stl_inputs: list[StlInput] = []
    for index, uploaded in enumerate(files):
        original_name = Path(uploaded.filename or f"model-{index + 1}.stl").name
        upload_path = settings.upload_dir / f"{uuid.uuid4().hex}-{original_name}"
        transformed_path = settings.upload_dir / f"{uuid.uuid4().hex}-transformed-{original_name}"
        with upload_path.open("wb") as handle:
            shutil.copyfileobj(uploaded.file, handle)
        try:
            rotate_and_place_on_bed(upload_path, transformed_path, rot_x[index], rot_y[index], rot_z[index])
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not transform {original_name}: {exc}") from exc
        stl_inputs.append(
            StlInput(
                path=transformed_path,
                original_filename=original_name,
                copy_count=copy_counts[index],
            )
        )

    try:
        project_path = slice_stls(
            settings=settings,
            stls=stl_inputs,
            filament_type=selected.filament_type,
            infill_density=infill_density,
            wall_loops=wall_loops,
        )
        remote_url = client.upload_project(project_path)
        result = client.start_print(remote_url, ams_slot=selected.slot, plate_index=settings.default_plate_index)
    except SlicerError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    total_parts = sum(copy_counts)
    return {
        "message": f"Sent {len(files)} STL file(s), {total_parts} total part(s), using {selected.label}",
        "project": str(project_path),
        "remote_url": remote_url,
        "printer_result": result,
    }
