import tkinter as tk
from tkinter import simpledialog


def ask_password(title="Se requieren permisos", message="Ingrese su contraseña para acceder al Bluetooth:"):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    password = simpledialog.askstring(
        title, message, show="*", parent=root,
    )
    root.destroy()
    return password or ""


if __name__ == "__main__":
    pw = ask_password()
    if pw:
        print(pw)
