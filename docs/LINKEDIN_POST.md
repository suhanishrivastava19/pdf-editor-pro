# LinkedIn post (copy & paste, then add your GitHub link, screenshots and demo video)

🚀 Task 2 done at **Algoryx** — I built **PDF Editor Pro**, a desktop PDF toolkit in Python!

Instead of stopping at the 5 required features, I built 13 – all in a clean, dark/light-mode GUI:

📎 Merge · ✂️ Split · 🔄 Rotate · 🗑️ Delete · 🔀 Reorder (with drag-and-drop + live thumbnails)
📝 Extract text · 🖼️ Images ⇄ PDF · 💧 Watermark · 🔢 Page numbers
🔐 AES-256 password protection · 🔓 Unlock · 🗜️ Compress / repair · 👁️ Live page preview

What I focused on:
✅ Clean architecture – PDF logic completely separated from the UI (fully unit-testable)
✅ Graceful handling of corrupted, empty and password-protected PDFs – it never crashes
✅ Background threads so the UI stays responsive
✅ 62 automated tests (core + GUI end-to-end)
✅ CI with GitHub Actions + one-click Windows .exe build

Biggest lesson: writing tests caught a real bug – watermarks were off-centre and upside-down on rotated pages. Fixing it meant working in the page's stored coordinate space. Testing early pays off!

🛠️ Python · PyMuPDF · CustomTkinter · Pillow · PyInstaller · pytest

🔗 GitHub: <paste your repository link>

Thank you @Algoryx for the opportunity and the mentorship!

#Python #PDF #SoftwareEngineering #Internship #Algoryx #OpenSource #CustomTkinter #PyMuPDF #Automation
