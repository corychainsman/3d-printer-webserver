# Test Cases

These are the logical paths covered by the automated test suite. The tests are unit-style: printer, slicer, FTPS, and MQTT boundaries are mocked or faked.

## Printer Status And AMS

- Status success returns flattened AMS tray data with slot, AMS id, tray id, label, filament type, and color.
- Status failure returns a 502-style error without leaking local credentials.
- Empty or missing AMS data returns an empty tray list.
- Multiple AMS units are flattened into stable global slots in reported order.
- Filament labels include a color hex value when the printer reports one.
- Printer states `IDLE`, `FINISH`, `FAILED`, `UNKNOWN`, or missing state are allowed.
- Active or unknown-active states such as `RUNNING`, `PREPARE`, `PAUSE`, or `SLICING` are treated as busy.
- `/api/status` includes printer state, busy flag, and busy reason while preserving the tray list.

## Print Handoff

- Empty file list is rejected.
- Non-STL filenames are rejected case-insensitively.
- Per-file arrays must match the file count for copies and X/Y/Z rotations.
- Copy counts must be between 1 and 99.
- Printer status polling failure returns a 502-style error.
- Busy printer returns a 409-style conflict before transform, slice, upload, or start-print calls.
- Missing selected AMS slot returns a 400-style error.
- Uploaded filenames are reduced to a basename before writing to disk.
- Each uploaded STL is transformed with its matching X/Y/Z rotation.
- Transformed STL paths, original filenames, and per-file copy counts are passed to the slicer.
- Job-level infill and wall settings are passed to the slicer.
- Selected AMS filament type is passed to the slicer.
- Slicer errors return a 500-style error and do not upload or start a print.
- Upload/start-print errors return a 502-style error.
- Successful jobs upload exactly one 3MF and start the printer with the selected global AMS slot.
- Successful responses report file count, total part count, selected filament label, local project path, remote URL, and printer result.

## Slicer

- No STL inputs are rejected.
- Filament profile resolution checks exact, lowercase, space-to-underscore, then fallback paths.
- Missing slicer binary, machine profile, process profile, or filament profile is reported before slicing.
- Each STL is duplicated according to its copy count before invoking the slicer.
- Duplicate filenames are sanitized while preserving deterministic source ordering.
- CLI command includes arrange, machine profile, process profile, filament profile, infill percent, wall loops, slice plate index, export path, and duplicated STL paths.
- `xvfb-run -a` is prepended when configured.
- Slicer failure reports the exit code, command, and trailing slicer output.

## STL Transform

- ASCII STLs are rotated and shifted so their minimum Z is on the bed.
- Binary STLs are rotated and shifted so their minimum Z is on the bed.
- Degenerate triangles do not crash normal recalculation.
- Binary STL triangle counts and attribute bytes are preserved.

## Browser Contract

- The file input accepts multiple STL files and the visible button says `Add STL`.
- Adding STL files appends to the current entry list instead of replacing it.
- File entries have stable IDs independent of row position.
- Removing an entry filters by stable ID and cannot be undone by a delayed `arrayBuffer()` parse.
- Removing the last entry clears the viewer and restores the empty preview message.
- Per-STL copies and X/Y/Z rotation fields are present and wired to preview rearrangement.
- Submit builds `FormData` from the current `fileEntries` order with files, copies, X/Y/Z rotations, job infill, job walls, and AMS slot.
- Empty client-side submit is blocked with a visible error message.
- AMS tray placeholders always render eight rows before status arrives.
- AMS colors are normalized before swatch display.
- The first available AMS tray is selected by default.
- Printer busy status is represented in the window title.
- Viewer has X, Y, 45 degree, Z, zoom in, zoom out, and Fit controls.
- X/Y controls toggle signs; 45 degree control cycles top-corner views.
- Initial loaded STL view uses the `-X/-Y` 45 degree corner preset.
- Viewer orbit uses Z-up camera orientation and disables screen-space panning.
- Fit mode changes preset camera framing to loaded objects.
- Build plate grid is a high-resolution canvas texture.
- Theme selector switches system.css and 98.css without changing form behavior.
