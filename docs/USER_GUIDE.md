# User Guide

## Opening a document
Click **Open PDF…** (or press `Ctrl+O`). Encrypted files ask for a password.
Damaged files are reported clearly – if a file can be repaired you'll be warned and can use
**Compress / repair** to save a clean copy.

## Tools

| Tool | How to use |
|---|---|
| **Merge PDFs** | *Add…* files, order them with *Move up/down*, click **Merge**, choose where to save. The currently open file is pre-added. |
| **Split PDF** | Choose *one file per page*, *every N pages* or *custom ranges* (`1-3;4;5-9`), pick an output folder. |
| **Rotate pages** | Pick the direction, enter pages (`all`, `1-3,5`) or press *Use current page only*. |
| **Delete pages** | Enter the pages to remove (`2`, `4-6`, `9-`). At least one page must remain. |
| **Reorder pages** | Select a page → *Move up/down*, *To top/bottom*, or drag it. A thumbnail shows the selected page. |
| **Extract text** | Optionally enter pages, click **Extract**, then copy or save as `.txt`. |
| **Images → PDF** | Add images, order them, choose *A4 (fit)* or *Original size*. |
| **PDF → Images** | Choose PNG/JPG, DPI (72–300), pages and an output folder. |
| **Add watermark** | Set text, size, opacity, angle, colour and pages. |
| **Add page numbers** | One click – adds "Page X of Y" at the bottom of each page. |
| **Protect with password** | Enter and confirm a password; choose whether printing/copying is allowed (AES-256). |
| **Remove password** | Enter the current password to save an unlocked copy. |
| **Compress / repair** | Saves an optimised copy and shows how much space was saved. |

After each operation you can open the result immediately.

## Page-range syntax
| Input | Meaning |
|---|---|
| `all` or empty | every page |
| `3` | page 3 |
| `1-4` | pages 1 to 4 |
| `8-` | page 8 to the end |
| `1-3,7,10-` | combinations |

## Navigation
* Preview: ◀ ▶ buttons, type a page number + Enter, `←/→` keys, mouse wheel to scroll.
* Zoom: − / + buttons, `Ctrl`+wheel, **Fit width**.
* Theme: *System / Light / Dark* (bottom-left).

## Troubleshooting
| Problem | Fix |
|---|---|
| "No module named tkinter" (Linux) | `sudo apt install python3-tk` |
| "No text found" | The PDF is a scan (images). OCR is not included. |
| Output file locked (Windows) | Close it in other viewers, or choose another name. |
| Something failed | See `~/.pdf_editor_pro/logs/pdf_editor.log` |
