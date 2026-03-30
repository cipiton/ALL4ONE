from __future__ import annotations

from dataclasses import dataclass
from tkinter import filedialog

import customtkinter as ctk


@dataclass(slots=True)
class ProjectCreationResult:
    name: str
    description: str
    source_path: str


class ProjectCreationDialog(ctk.CTkToplevel):
    def __init__(self, master, *, title: str, labels: dict[str, str], initial_dir: str) -> None:
        super().__init__(master)
        self.title(title)
        self.geometry("640x320")
        self.minsize(560, 280)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()

        self._labels = labels
        self._initial_dir = initial_dir
        self._result: ProjectCreationResult | None = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(self, text=labels["name"]).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        self.name_entry = ctk.CTkEntry(self)
        self.name_entry.grid(row=0, column=1, sticky="ew", padx=16, pady=(16, 8))

        ctk.CTkLabel(self, text=labels["description"]).grid(row=1, column=0, sticky="nw", padx=16, pady=8)
        self.description_box = ctk.CTkTextbox(self, height=96, wrap="word")
        self.description_box.grid(row=1, column=1, sticky="nsew", padx=16, pady=8)

        ctk.CTkLabel(self, text=labels["source"]).grid(row=2, column=0, sticky="w", padx=16, pady=8)
        source_frame = ctk.CTkFrame(self, fg_color="transparent")
        source_frame.grid(row=2, column=1, sticky="ew", padx=16, pady=8)
        source_frame.grid_columnconfigure(0, weight=1)
        self.source_entry = ctk.CTkEntry(source_frame)
        self.source_entry.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        ctk.CTkButton(source_frame, text=labels["browse_file"], command=self._browse_file, width=120).grid(
            row=1, column=0, sticky="w", padx=(0, 8)
        )
        ctk.CTkButton(source_frame, text=labels["browse_folder"], command=self._browse_folder, width=120).grid(
            row=1, column=1, sticky="w"
        )

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, columnspan=2, sticky="e", padx=16, pady=(8, 16))
        ctk.CTkButton(footer, text=labels["cancel"], command=self._cancel, width=100).pack(side="left", padx=(0, 8))
        ctk.CTkButton(footer, text=labels["create"], command=self._submit, width=120).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.name_entry.focus()

    def show(self) -> ProjectCreationResult | None:
        self.wait_window()
        return self._result

    def _browse_file(self) -> None:
        selected = filedialog.askopenfilename(
            title=self._labels["browse_file"],
            initialdir=self._initial_dir,
            filetypes=[(self._labels["filetype_text"], "*.txt"), (self._labels["filetype_all"], "*.*")],
        )
        if selected:
            self.source_entry.delete(0, "end")
            self.source_entry.insert(0, selected)

    def _browse_folder(self) -> None:
        selected = filedialog.askdirectory(
            title=self._labels["browse_folder"],
            initialdir=self._initial_dir,
        )
        if selected:
            self.source_entry.delete(0, "end")
            self.source_entry.insert(0, selected)

    def _submit(self) -> None:
        self._result = ProjectCreationResult(
            name=self.name_entry.get().strip(),
            description=self.description_box.get("1.0", "end").strip(),
            source_path=self.source_entry.get().strip(),
        )
        self.destroy()

    def _cancel(self) -> None:
        self._result = None
        self.destroy()
