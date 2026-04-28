#!/usr/bin/env python3

import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

SCRIPT_DIR = Path(__file__).resolve().parent


class FileMonsterGUI:
    def __init__(self, root):
        self.root = root
        root.title("FileMonster v0.1")
        root.geometry("920x680")

        self.input_path = tk.StringVar()
        self.output_dir = tk.StringVar(value=str(Path.home() / "filemonster_run"))

        self.build()

    def build(self):
        tk.Label(self.root, text="FileMonster", font=("Arial", 22, "bold")).pack(pady=8)
        tk.Label(
            self.root,
            text="PDF / image decompiler: editable SVGs, panels, text, clickable PDFs, canonical JSONL"
        ).pack()

        self.path_row("Input file/folder:", self.input_path, self.choose_input)
        self.path_row("Output folder:", self.output_dir, self.choose_output)

        buttons = tk.Frame(self.root)
        buttons.pack(fill="x", padx=8, pady=8)

        items = [
            ("1 Scan Ledger", self.stage_scan),
            ("2 Extract Text", self.stage_text),
            ("3 Extract Panels", self.stage_panels),
            ("4 Editable SVGs", self.stage_svg),
            ("5 Canonical JSONL", self.stage_canonical),
            ("Run All", self.stage_canonical),
            ("Open SVG Folder", self.open_svg_folder),
            ("Open Output Folder", self.open_output_folder),
            ("Clear Log", lambda: self.log.delete("1.0", "end")),
        ]

        for i, (label, cmd) in enumerate(items):
            tk.Button(buttons, text=label, command=cmd).grid(
                row=i // 3, column=i % 3, padx=4, pady=4, sticky="ew"
            )

        for i in range(3):
            buttons.columnconfigure(i, weight=1)

        self.log = scrolledtext.ScrolledText(self.root, height=26)
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    def path_row(self, label, var, browse_cmd):
        row = tk.Frame(self.root)
        row.pack(fill="x", padx=8, pady=6)

        tk.Label(row, text=label, width=16, anchor="w").pack(side="left")
        tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True, padx=8)
        tk.Button(row, text="Browse", command=browse_cmd).pack(side="left")

    def choose_input(self):
        path = filedialog.askdirectory(title="Choose input folder")
        if not path:
            path = filedialog.askopenfilename(title="Choose input file")
        if path:
            self.input_path.set(path)

    def choose_output(self):
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            self.output_dir.set(path)

    def paths(self):
        out = Path(self.output_dir.get()).expanduser()
        out.mkdir(parents=True, exist_ok=True)

        return {
            "input": self.input_path.get(),
            "out": out,
            "master": out / "filemonster_master.json",
            "clean_svg": out / "editable_svg",
            "canonical_jsonl": out / "filemonster_canonical_dataset.jsonl",
            "canonical_summary": out / "filemonster_canonical_summary.json",
        }

    def write(self, text):
        self.log.insert("end", text)
        self.log.see("end")
        self.root.update_idletasks()

    def require_input(self):
        if not self.input_path.get():
            messagebox.showerror("Missing input", "Choose an input file or folder first.")
            return False
        return True

    def run_commands_threaded(self, commands):
        if not self.require_input():
            return

        def worker():
            for label, cmd in commands:
                self.write("\n$ " + " ".join(map(str, cmd)) + "\n")

                try:
                    proc = subprocess.Popen(
                        [str(x) for x in cmd],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=str(SCRIPT_DIR),
                    )

                    for line in proc.stdout:
                        self.write(line)

                    code = proc.wait()
                    self.write(f"\n[exit {code}]\n")

                    if code != 0:
                        self.write(f"\nPipeline stopped at: {label}\n")
                        return

                except Exception as e:
                    self.write(f"\nERROR during {label}: {e}\n")
                    return

            self.write("\nFileMonster task complete.\n")

        threading.Thread(target=worker, daemon=True).start()

    def scan_cmd(self):
        p = self.paths()
        return (
            "Scan ledger",
            [
                SCRIPT_DIR / "filemonster_scan",
                p["input"],
                "-o", p["master"],
                "--sidecars",
                "--write-xattr",
            ],
        )

    def text_cmd(self):
        p = self.paths()
        return (
            "Extract PDF text",
            [
                SCRIPT_DIR / "fm_spatial_text_module.py",
                "--master", p["master"],
                "--granularity", "line",
            ],
        )

    def panels_cmd(self):
        p = self.paths()
        return (
            "Extract panels",
            [
                SCRIPT_DIR / "fm_layout_regions_module.py",
                "--master", p["master"],
                "--profile", "comic",
                "--crop-panels",
                "--crop-panel-group",
                "--svg",
                "--embed-page-background",
            ],
        )

    def svg_cmd(self):
        p = self.paths()
        return (
            "Build editable SVGs",
            [
                SCRIPT_DIR / "fm_panel_text_svg_export.py",
                "--master", p["master"],
                "--output-dir", p["clean_svg"],
            ],
        )

    def canonical_cmd(self):
        p = self.paths()
        return (
            "Build canonical JSONL",
            [
                SCRIPT_DIR / "fm_export_canonical_dataset.py",
                "--input-dir", p["clean_svg"],
                "--output-jsonl", p["canonical_jsonl"],
                "--output-json", p["canonical_summary"],
            ],
        )

    def stage_scan(self):
        self.run_commands_threaded([self.scan_cmd()])

    def stage_text(self):
        self.run_commands_threaded([
            self.scan_cmd(),
            self.text_cmd(),
        ])

    def stage_panels(self):
        self.run_commands_threaded([
            self.scan_cmd(),
            self.panels_cmd(),
        ])

    def stage_svg(self):
        self.run_commands_threaded([
            self.scan_cmd(),
            self.text_cmd(),
            self.panels_cmd(),
            self.svg_cmd(),
        ])

    def stage_canonical(self):
        self.run_commands_threaded([
            self.scan_cmd(),
            self.text_cmd(),
            self.panels_cmd(),
            self.svg_cmd(),
            self.canonical_cmd(),
        ])

    def open_output_folder(self):
        p = self.paths()
        subprocess.Popen(["xdg-open", str(p["out"])])

    def open_svg_folder(self):
        p = self.paths()
        subprocess.Popen(["xdg-open", str(p["clean_svg"])])


if __name__ == "__main__":
    root = tk.Tk()
    FileMonsterGUI(root)
    root.mainloop()
