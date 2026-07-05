import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gui.app import RoboticArmApp


def main():
    try:
        app = RoboticArmApp()
        app.mainloop()
    except Exception as e:
        import traceback
        from tkinter import messagebox
        traceback.print_exc()
        try:
            messagebox.showerror("Error Fatal", f"{e}\n\nVer consola para detalles.")
        except Exception:
            pass


if __name__ == "__main__":
    main()
