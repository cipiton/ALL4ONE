from __future__ import annotations

from pathlib import Path
from tkinter import ttk
from typing import Callable

import customtkinter as ctk


class ProjectTreePane(ctk.CTkFrame):
    DEFAULT_WIDTH = 248
    COLLAPSED_WIDTH = 40
    TREE_STYLE = "FakeAgent.Treeview"
    HIDDEN_INTERNAL_NAMES = {"project.json", "project_state.json", "continuity_log.json", "intermediate"}
    PROTECTED_INTERNAL_NAMES = {"project.json", "project_state.json", "continuity_log.json", "intermediate"}

    def __init__(
        self,
        master,
        *,
        translator: Callable[[str], str],
        open_path_callback: Callable[[Path], None],
        import_file_callback: Callable[[], None],
        import_folder_callback: Callable[[], None],
        delete_callback: Callable[[], None],
        toggle_callback: Callable[[], None],
        show_internal_files: bool = False,
    ) -> None:
        super().__init__(master, width=self.DEFAULT_WIDTH)
        self._t = translator
        self._open_path = open_path_callback
        self._import_file = import_file_callback
        self._import_folder = import_folder_callback
        self._delete = delete_callback
        self._toggle = toggle_callback
        self._project_root: Path | None = None
        self._path_by_item: dict[str, Path] = {}
        self._collapsed = False
        self._show_internal_files = show_internal_files
        self.grid_propagate(False)

        self._configure_tree_style()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 6))
        self.header_frame.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(
            self.header_frame,
            text=self._t("project.tree.label"),
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        self.toggle_button = ctk.CTkButton(
            self.header_frame,
            text="▸",
            width=28,
            height=28,
            command=self._toggle,
            fg_color="transparent",
            hover_color=("gray78", "gray24"),
        )
        self.toggle_button.grid(row=0, column=1, sticky="e")

        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(2, weight=1)

        self.summary_label = ctk.CTkLabel(
            self.content_frame,
            text=self._t("project.tree.empty"),
            anchor="w",
            justify="left",
            text_color=("gray45", "#cbd5e1"),
        )
        self.summary_label.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 4))

        self.drop_hint_label = ctk.CTkLabel(
            self.content_frame,
            text=self._t("project.tree.drop_hint"),
            anchor="w",
            justify="left",
            wraplength=208,
            text_color=("gray50", "#94a3b8"),
        )
        self.drop_hint_label.grid(row=1, column=0, sticky="ew", padx=2, pady=(0, 8))

        self.tree_container = ctk.CTkFrame(self.content_frame, fg_color=("#f5f7fa", "#1f2937"))
        self.tree_container.grid(row=2, column=0, sticky="nsew")
        self.tree_container.grid_columnconfigure(0, weight=1)
        self.tree_container.grid_rowconfigure(0, weight=1)
        self.tree_container.grid_rowconfigure(1, weight=0)

        self.tree = ttk.Treeview(
            self.tree_container,
            show="tree",
            style=self.TREE_STYLE,
            selectmode="browse",
        )
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        self.tree.column("#0", width=320, stretch=True)
        self.tree.bind("<Double-1>", self._handle_open)

        self.vertical_scrollbar = ctk.CTkScrollbar(self.tree_container, orientation="vertical", command=self.tree.yview)
        self.vertical_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 8), pady=(8, 0))
        self.horizontal_scrollbar = ctk.CTkScrollbar(self.tree_container, orientation="horizontal", command=self.tree.xview)
        self.horizontal_scrollbar.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        self.tree.configure(
            yscrollcommand=self.vertical_scrollbar.set,
            xscrollcommand=self.horizontal_scrollbar.set,
        )

        actions = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        actions.grid_columnconfigure((0, 1), weight=1)

        self.import_file_button = ctk.CTkButton(
            actions,
            text=self._t("project.tree.import_file"),
            command=self._import_file,
            height=30,
        )
        self.import_file_button.grid(row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 6))
        self.import_folder_button = ctk.CTkButton(
            actions,
            text=self._t("project.tree.import_folder"),
            command=self._import_folder,
            height=30,
        )
        self.import_folder_button.grid(row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 6))
        self.open_button = ctk.CTkButton(
            actions,
            text=self._t("project.tree.open"),
            command=self.open_selected,
            height=30,
        )
        self.open_button.grid(row=1, column=0, sticky="ew", padx=(0, 4))
        self.open_folder_button = ctk.CTkButton(
            actions,
            text=self._t("project.tree.open_folder"),
            command=self.open_selected_folder,
            height=30,
        )
        self.open_folder_button.grid(row=1, column=1, sticky="ew", padx=(4, 0))
        self.delete_button = ctk.CTkButton(
            actions,
            text=self._t("project.tree.delete"),
            command=self._delete,
            height=30,
            fg_color=("#ef4444", "#7f1d1d"),
            hover_color=("#dc2626", "#991b1b"),
        )
        self.delete_button.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.set_collapsed(False)

    def drop_widgets(self) -> list[object]:
        widgets: list[object] = [
            self,
            self.header_frame,
            self.toggle_button,
            self.content_frame,
            self.tree_container,
            self.tree,
            self.summary_label,
            self.drop_hint_label,
        ]
        return widgets

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        if collapsed:
            self.configure(width=self.COLLAPSED_WIDTH)
            self.title_label.grid_remove()
            self.content_frame.grid_remove()
            self.toggle_button.configure(text="◂")
        else:
            self.configure(width=self.DEFAULT_WIDTH)
            self.title_label.grid()
            self.content_frame.grid()
            self.toggle_button.configure(text="▸")

    def set_project_root(self, root: Path | None) -> None:
        self._project_root = root
        self.refresh()

    def set_show_internal_files(self, show_internal_files: bool) -> None:
        self._show_internal_files = show_internal_files
        self.refresh()

    def refresh(self) -> None:
        expanded = self._expanded_paths()
        selected = self.selected_path()
        self.tree.delete(*self.tree.get_children())
        self._path_by_item.clear()

        if self._project_root is None or not self._project_root.exists():
            self.summary_label.configure(text=self._t("project.tree.empty"))
            return

        self.summary_label.configure(
            text=self._t("project.tree.summary", name=self._project_root.name)
        )
        root_item = self._insert_path("", self._project_root, expanded=expanded, open_by_default=True)
        self._populate_children(root_item, self._project_root, expanded)
        self._restore_selection(selected)

    def selected_path(self) -> Path | None:
        selected_items = self.tree.selection()
        if not selected_items:
            return None
        return self._path_by_item.get(selected_items[0])

    def path_at_y(self, y: int) -> Path | None:
        item_id = self.tree.identify_row(y)
        if not item_id:
            return None
        return self._path_by_item.get(item_id)

    def open_selected(self) -> None:
        target = self.selected_path()
        if target is None:
            target = self._project_root
        if target is None:
            return
        self._open_path(target)

    def open_selected_folder(self) -> None:
        target = self.selected_path()
        if target is None:
            target = self._project_root
        if target is None:
            return
        self._open_path(target if target.is_dir() else target.parent)

    def _handle_open(self, _event) -> None:
        self.open_selected()

    def _expanded_paths(self) -> set[str]:
        expanded: set[str] = set()
        for item in self.tree.get_children():
            self._collect_expanded(item, expanded)
        return expanded

    def _collect_expanded(self, item: str, expanded: set[str]) -> None:
        path = self._path_by_item.get(item)
        if path is not None and self.tree.item(item, "open"):
            expanded.add(str(path))
        for child in self.tree.get_children(item):
            self._collect_expanded(child, expanded)

    def _insert_path(
        self,
        parent: str,
        path: Path,
        *,
        expanded: set[str],
        open_by_default: bool = False,
    ) -> str:
        item = self.tree.insert(
            parent,
            "end",
            text=path.name or str(path),
            open=open_by_default or str(path) in expanded,
        )
        self._path_by_item[item] = path
        return item

    def _populate_children(self, parent_item: str, directory: Path, expanded: set[str]) -> None:
        try:
            children = sorted(
                directory.iterdir(),
                key=lambda path: (not path.is_dir(), path.name.casefold()),
            )
        except OSError:
            return

        for child in children:
            if not self._show_internal_files and self.is_internal_path(child):
                continue
            child_item = self._insert_path(parent_item, child, expanded=expanded)
            if child.is_dir():
                self._populate_children(child_item, child, expanded)

    def _restore_selection(self, selected: Path | None) -> None:
        if selected is None:
            return
        selected_key = str(selected)
        for item, path in self._path_by_item.items():
            if str(path) == selected_key:
                self.tree.selection_set(item)
                self.tree.focus(item)
                self.tree.see(item)
                return

    def _configure_tree_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            self.TREE_STYLE,
            background="#111827",
            fieldbackground="#111827",
            foreground="#e5e7eb",
            borderwidth=0,
            relief="flat",
            rowheight=24,
        )
        style.map(
            self.TREE_STYLE,
            background=[("selected", "#2563eb")],
            foreground=[("selected", "#f8fafc")],
        )
        style.configure(
            f"{self.TREE_STYLE}.Heading",
            background="#0f172a",
            foreground="#cbd5e1",
            relief="flat",
        )

    def is_internal_path(self, path: Path) -> bool:
        if self._project_root is None:
            return False
        try:
            relative = path.resolve().relative_to(self._project_root.resolve())
        except Exception:
            return False
        parts = relative.parts
        if not parts:
            return False
        return parts[0] in self.HIDDEN_INTERNAL_NAMES

    def is_protected_path(self, path: Path) -> bool:
        if self._project_root is None:
            return False
        try:
            relative = path.resolve().relative_to(self._project_root.resolve())
        except Exception:
            return False
        parts = relative.parts
        if not parts:
            return False
        return parts[0] in self.PROTECTED_INTERNAL_NAMES
