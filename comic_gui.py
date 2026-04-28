#!/usr/bin/env python3
"""
FileMonster Comic GUI v0.1

Simple GUI wrapper for fm_comic_cornucopia_engine.py
"""

import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from fm_comic_cornucopia_engine import ComicCornucopiaEngine


class ComicGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("FileMonster Comic Cornucopia")
        self.root.geometry("900x650")

        self.input_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "comic_cornucopia_output"))

        self.build()

    def build(self):
        title = tk.Label(
            self.root,
            text="FileMonster Comic Cornucopia",
            font=("Arial", 22, "bold")
        )
        title.pack(pady=10)

        subtitle = tk.Label(
            self.root,
            text="PDF / image / folder → SVG pages, panels, text objects, JSON, JSONL"
        )
        subtitle.pack(pady=2)

        self.path_row("Input:", self.input_path, self.choose_input)
        self.path_row("Output:", self.output_dir, self.choose_output)

        buttons = tk.Frame(self.root)
        buttons.pack(fill="x", padx=10, pady=10)

        tk.Button(
            buttons,
            text="Run Comic Cornucopia",
            command=self.run_engine,
            height=2
        ).pack(side="left", fill="x", expand=True, padx=5)

        tk.Button(
            buttons,
            text="Open Output Folder",
            command=self.open_output,
            height=2
        ).pack(side="left", fill="x", expand=True, padx=5)

        tk.Button(
            buttons,
            text="Clear Log",
            command=lambda: self.log.delete("1.0", "end"),
            height=2
        ).pack(side="left", fill="x", expand=True, padx=5)

        self.log = scrolledtext.ScrolledText(self.root, height=26)
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def path_row(self, label, var, command):
        row = tk.Frame(self.root)
        row.pack(fill="x", padx=10, pady=6)

        tk.Label(row, text=label, width=10, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=command).pack(side="left")

    def choose_input(self):
        path = filedialog.askopenfilename(
            title="Choose comic PDF or image",
            filetypes=[
                ("Supported files", "*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("PDF files", "*.pdf"),
                ("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                ("All files", "*.*"),
            ],
        )

        if not path:
            path = filedialog.askdirectory(title="Choose folder of images")

        if path:
            self.input_path.set(path)

    def choose_output(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_dir.set(path)

    def write(self, text):
        self.log.insert("end", str(text) + "\n")
        self.log.see("end")
        self.root.update_idletasks()

    def validate(self):
        if not self.input_path.get().strip():
            messagebox.showerror("Missing input", "Choose a PDF, image, or image folder first.")
            return False

        if not self.output_dir.get().strip():
            messagebox.showerror("Missing output", "Choose an output folder first.")
            return False

        return True

    def run_engine(self):
        if not self.validate():
            return

        input_path = self.input_path.get().strip()
        output_dir = self.output_dir.get().strip()

        self.write("Starting Comic Cornucopia...")
        self.write(f"Input:  {input_path}")
        self.write(f"Output: {output_dir}")

        def worker():
            try:
                engine = ComicCornucopiaEngine(
                    input_path=input_path,
                    output_dir=output_dir,
                    log_callback=self.write,
                )
                engine.run()
                self.write("Done. The cornucopia has spilled its treasure.")
            except Exception as e:
                self.write(f"ERROR: {e}")
                messagebox.showerror("Cornucopia failed", str(e))

        threading.Thread(target=worker, daemon=True).start()

    def open_output(self):
        out = Path(self.output_dir.get()).expanduser()
        out.mkdir(parents=True, exist_ok=True)

        try:
            import os
            import subprocess
            import sys

            if sys.platform.startswith("win"):
                os.startfile(out)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(out)])
            else:
                subprocess.Popen(["xdg-open", str(out)])
        except Exception as e:
            messagebox.showerror("Could not open folder", str(e))


def main():
    root = tk.Tk()
    app = ComicGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
