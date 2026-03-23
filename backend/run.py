import multiprocessing
import uvicorn
import sys
import os

# Ensure the paths are set correctly when running as PyInstaller bundle
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys module by a flag frozen=True and sets the app 
    # path into variable _MEIPASS.
    application_path = sys._MEIPASS
    os.chdir(application_path)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))

from backend.main import app

if __name__ == "__main__":
    multiprocessing.freeze_support()
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
            
    print(f"Starting Blueprint Backend on port {port}...")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
