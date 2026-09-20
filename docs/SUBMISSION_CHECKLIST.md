# Task 2 – Submission checklist

## Required by the task
- [x] Python 3.11+
- [x] Object-Oriented Programming (`PDFService`, `ToolDialog`, `PreviewPanel`, `PDFEditorApp` …)
- [x] PyMuPDF / Pillow / CustomTkinter
- [x] Modular architecture (`core/` vs `gui/`)
- [x] Logging & exception handling
- [x] `requirements.txt`
- [x] Readable folder structure
- [x] ≥ 5 features → **13 implemented**
- [x] Graceful handling of corrupted PDFs
- [x] `README.md`, project documentation (`docs/`)

## You still need to do (I can't do these for you)
1. [ ] Create a **public GitHub repository** and push (commands below).
2. [ ] Get the **executable build**: push a tag `v1.0.0` → GitHub Actions builds `PDFEditorPro.exe`
       (or run `python build_exe.py` on your Windows PC). Attach it to a GitHub Release.
3. [ ] Put your real GitHub link in `docs/LINKEDIN_POST.md`, add 2–3 screenshots and publish the **LinkedIn post (mandatory)**.
4. [ ] Replace `<your-username>` in `README.md`.
5. [ ] Submit: Repository URL + LinkedIn post link (+ Release URL) before the Week-2 deadline.

## Push to GitHub
```bash
cd pdf-editor-pro
git init
git add .
git commit -m "feat: PDF Editor Pro - complete Task 2"
git branch -M main
git remote add origin https://github.com/<your-username>/pdf-editor-pro.git
git push -u origin main

# build the Windows exe + release
git tag v1.0.0
git push origin v1.0.0
```
