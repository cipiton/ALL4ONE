from __future__ import annotations

import os
import shutil
import ctypes
import textwrap
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from engine.app_paths import get_app_root, get_bundle_root
from .backend_adapter import GuiBackend, GuiOutputCard, GuiRunRequest, GuiRuntimeInputField, GuiSkillOption
from .assistant_worker import AssistantWorker
from .chat_router import current_runtime_field, is_question_like, should_route_to_workflow
from .chat_state import ChatMessage
from .dragdrop import DnDWindow, extract_drop_paths, register_file_drop
from .i18n import Localizer
from .llm_client import AssistantRequest
from .project_creation_dialog import ProjectCreationDialog
from .project_models import ProjectState
from .project_store import ProjectStore
from .project_tree import ProjectTreePane
from .prompt_builder import build_llm_messages
from .settings_manager import AppSettings, SettingsManager
from .worker import GuiWorker, WorkerEvent, WorkerPrompt
from .workspace_manager import WorkspaceManager


class MainWindow(DnDWindow):
    OUTPUT_FULL_CHAR_THRESHOLD = 2400
    OUTPUT_FULL_LINE_THRESHOLD = 60
    OUTPUT_PREVIEW_CHAR_LIMIT = 1400
    OUTPUT_PREVIEW_LINE_LIMIT = 18

    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self.repo_root = repo_root.resolve()
        self.backend = GuiBackend(self.repo_root)
        self.settings_manager = SettingsManager(self.repo_root)
        self.settings = self.settings_manager.load()
        self.localizer = Localizer(self.settings.language)
        self.settings_manager.apply(self.settings)
        self.workspace_manager = WorkspaceManager(self.settings.workspace_root)
        self.selected_skill_id: str | None = None

        self.skills: list[GuiSkillOption] = []
        self.skills_by_id: dict[str, GuiSkillOption] = {}
        self.skill_names: list[str] = []
        self.skill_name_to_id: dict[str, str] = {}
        self._reload_skill_options()
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.nav_row_frames: dict[str, ctk.CTkFrame] = {}
        self.nav_icon_labels: dict[str, ctk.CTkLabel] = {}
        self.project_buttons: dict[str, ctk.CTkButton] = {}
        self.projects: dict[str, ProjectState] = {}
        self.project_store = ProjectStore(self.workspace_manager)
        self.bible_path_by_label: dict[str, str] = {}
        self.current_project_id: str | None = None
        self.selected_page = "run"
        self.selected_project_name = self.settings.last_project_name
        self.running_project_id: str | None = None

        self.event_queue: Queue[WorkerEvent] = Queue()
        self.worker: GuiWorker | None = None
        self.assistant_worker: AssistantWorker | None = None
        self.last_output_dir: Path | None = None
        self.help_window: ctk.CTkToplevel | None = None
        self.workspace_section_expanded = False
        self.project_tree_expanded = True
        self._chat_wrap_width = 0
        self._chat_layout_refresh_after_id: str | None = None
        self._chat_refresh_in_progress = False
        self._tree_drag_path: Path | None = None
        self._tree_drag_badge: ctk.CTkLabel | None = None
        self._composer_drop_hover_active = False
        self._run_button_hover_active = False
        self._windows_scroll_lines: int | None = None

        self.workspace_root_var = ctk.StringVar(value=self.settings.workspace_root)
        self.project_var = ctk.StringVar(value=self.settings.last_project_name)
        self.project_inputs_var = ctk.StringVar()
        self.project_outputs_var = ctk.StringVar()
        self.output_path_var = ctk.StringVar(value=self.settings.default_output_path)
        self.status_var = ctk.StringVar(value=self._t("status.ready"))
        self.skill_title_var = ctk.StringVar(value=self._t("warning.choose_skill_first"))
        self.project_title_var = ctk.StringVar(value=self._t("project.status.empty"))
        self.project_description_var = ctk.StringVar(value=self._t("project.header.description_fallback"))
        self.project_summary_var = ctk.StringVar(value="")
        self.selected_skill_info_var = ctk.StringVar(value=self._t("project.skill_info.empty"))
        self.skill_selector_var = ctk.StringVar(value=self.skill_names[0] if self.skill_names else "")
        self.sidebar_project_var = ctk.StringVar(value=self._t("workflow.intro.project", project=self._t("common.no_project")))
        self.sidebar_output_var = ctk.StringVar(value=self._t("workflow.intro.output", path="-"))
        self.provider_var = ctk.StringVar(value=self.settings.provider)
        self.model_var = ctk.StringVar(value=self.settings.model)
        self.api_key_var = ctk.StringVar(value=self.settings.api_key)
        self.base_url_var = ctk.StringVar(value=self.settings.base_url)
        self.language_var = ctk.StringVar(value=self.localizer.language_label(self.settings.language))
        self.show_api_key_var = ctk.BooleanVar(value=False)
        self.auto_accept_review_steps_var = ctk.BooleanVar(value=self.settings.auto_accept_review_steps)
        self.show_internal_project_files_var = ctk.BooleanVar(value=self.settings.show_internal_project_files)
        self.output_display_mode_var = ctk.StringVar(value=self._output_display_mode_label(self.settings.output_display_mode))

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title(self._t("app.title"))
        self.geometry("1220x800")
        self.minsize(1080, 720)

        self._load_saved_projects()
        self._build_ui()
        self._show_page("run")
        self._refresh_projects(select_name=self.settings.last_project_name)
        self._restore_initial_project()
        self._refresh_api_key_placeholder()
        self.after(150, self._poll_worker_events)

    def _t(self, key: str, **kwargs: object) -> str:
        return self.localizer.t(key, **kwargs)

    def _language_code(self) -> str:
        return self.localizer.language_code_from_label(self.language_var.get())

    def _apply_language(self, language: str) -> None:
        self.localizer.set_language(language)
        self._reload_skill_options()
        self.language_var.set(self.localizer.language_label(self.localizer.language))
        self.output_display_mode_var.set(self._output_display_mode_label(self.settings.output_display_mode))
        self.title(self._t("app.title"))

    def _output_display_mode_label(self, mode: str) -> str:
        mapping = {
            "hybrid": self._t("settings.output_mode.hybrid"),
            "full": self._t("settings.output_mode.full"),
            "preview": self._t("settings.output_mode.preview"),
        }
        return mapping.get(mode, mapping["hybrid"])

    def _output_display_mode_code(self) -> str:
        label = self.output_display_mode_var.get()
        reverse = {
            self._t("settings.output_mode.hybrid"): "hybrid",
            self._t("settings.output_mode.full"): "full",
            self._t("settings.output_mode.preview"): "preview",
        }
        return reverse.get(label, "hybrid")

    def _reload_skill_options(self) -> None:
        current_skill_id = self.selected_skill_id
        self.skills = self.backend.load_skills(self.localizer.language)
        self.skills_by_id = {skill.skill_id: skill for skill in self.skills}
        self.skill_names = [skill.display_name for skill in self.skills]
        self.skill_name_to_id = {skill.display_name: skill.skill_id for skill in self.skills}
        if current_skill_id in self.skills_by_id:
            self.selected_skill_id = current_skill_id
        elif self.settings.default_skill_id in self.skills_by_id:
            self.selected_skill_id = self.settings.default_skill_id
        elif self.skills:
            self.selected_skill_id = self.skills[0].skill_id
        else:
            self.selected_skill_id = None

    def _rebuild_ui(self) -> None:
        current_page = self.selected_page
        current_project_id = self.current_project_id
        current_logs = ""
        if hasattr(self, "logs_textbox"):
            current_logs = self.logs_textbox.get("1.0", "end")
        self._close_help_window()

        if hasattr(self, "sidebar"):
            self.sidebar.destroy()
        if hasattr(self, "content_container"):
            self.content_container.destroy()

        self.nav_buttons.clear()
        self.nav_row_frames.clear()
        self.nav_icon_labels.clear()
        self.project_buttons.clear()
        self._build_ui()

        if current_logs.strip():
            self._append_log(current_logs)
        self._refresh_projects(select_name=self.project_var.get().strip())
        if current_project_id and current_project_id in self.projects:
            self._select_project(current_project_id)
        else:
            self._restore_initial_project()
        self._refresh_api_key_placeholder()
        self._show_page(current_page)

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=250)
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(16, 8), pady=16)
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(1, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text=self._t("app.title"),
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        self.project_section = ctk.CTkFrame(self.sidebar)
        self.project_section.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.project_section.grid_columnconfigure(0, weight=1)
        self.project_section.grid_rowconfigure(2, weight=1)
        self._build_project_list()

        nav_section = ctk.CTkFrame(self.sidebar)
        nav_section.grid(row=2, column=0, sticky="sew", padx=12, pady=(0, 12))
        nav_section.grid_columnconfigure(0, weight=1)
        self._build_sidebar_nav(nav_section)

        self.content_container = ctk.CTkFrame(self)
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        self.run_tab = ctk.CTkFrame(self.content_container)
        self.settings_tab = ctk.CTkFrame(self.content_container)
        self.logs_tab = ctk.CTkFrame(self.content_container)
        for frame in (self.run_tab, self.settings_tab, self.logs_tab):
            frame.grid(row=0, column=0, sticky="nsew")

        self._build_run_tab()
        self._build_settings_tab()
        self._build_logs_tab()

    def _build_run_tab(self) -> None:
        self.run_tab.grid_columnconfigure(0, weight=5)
        self.run_tab.grid_columnconfigure(1, weight=0, minsize=ProjectTreePane.DEFAULT_WIDTH)
        self.run_tab.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(self.run_tab)
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10, pady=(10, 6))
        header_frame.grid_columnconfigure(0, weight=1)
        self.workspace_toggle_button = ctk.CTkButton(
            header_frame,
            text="",
            anchor="w",
            fg_color="transparent",
            hover_color=("gray78", "gray24"),
            command=self._toggle_workspace_section,
        )
        self.workspace_toggle_button.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        project_name_label = ctk.CTkLabel(
            header_frame,
            textvariable=self.project_title_var,
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        )
        project_name_label.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 2))

        ctk.CTkLabel(
            header_frame,
            textvariable=self.project_summary_var,
            anchor="w",
            justify="left",
            wraplength=820,
            text_color=("gray45", "#cbd5e1"),
        ).grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))

        selector_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        selector_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 6))
        selector_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(selector_row, text=self._t("project.header.current_skill"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )
        self.skill_selector = ctk.CTkComboBox(
            selector_row,
            variable=self.skill_selector_var,
            values=self.skill_names or [""],
            state="readonly",
            command=self._on_skill_dropdown_changed,
        )
        self.skill_selector.grid(row=0, column=1, sticky="ew")
        self.run_skill_button = ctk.CTkButton(
            selector_row,
            text=self._t("project.header.run"),
            command=self._on_run_skill_button,
            width=96,
        )
        self.run_skill_button.grid(row=0, column=2, sticky="e", padx=(10, 0))
        self.run_skill_button.bind("<Enter>", self._on_run_button_enter, add="+")
        self.run_skill_button.bind("<Leave>", self._on_run_button_leave, add="+")

        self.workspace_details_frame = ctk.CTkFrame(header_frame, fg_color="transparent")
        self.workspace_details_frame.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 10))
        self.workspace_details_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.workspace_details_frame,
            textvariable=self.project_description_var,
            anchor="w",
            justify="left",
            wraplength=860,
            text_color=("gray35", "#d1d5db"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 6))

        ctk.CTkLabel(
            self.workspace_details_frame,
            text=self._t("project.skill_info.label"),
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
            text_color=("gray45", "#cbd5e1"),
        ).grid(row=1, column=0, sticky="w", pady=(0, 2))
        ctk.CTkLabel(
            self.workspace_details_frame,
            textvariable=self.selected_skill_info_var,
            anchor="w",
            justify="left",
            wraplength=860,
            text_color=("gray35", "#d1d5db"),
        ).grid(row=2, column=0, sticky="ew")

        self._update_workspace_section_visibility()

        thread_frame = ctk.CTkFrame(self.run_tab)
        thread_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=(0, 6))
        thread_frame.grid_columnconfigure(0, weight=1)
        thread_frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            thread_frame,
            text=self._t("project.activity.label"),
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))

        self.chat_history = ctk.CTkScrollableFrame(thread_frame)
        self.chat_history.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.chat_history.grid_columnconfigure(0, weight=1)
        self.chat_history.bind("<Configure>", self._schedule_chat_layout_refresh)
        self._bind_chat_scroll_widget(self.chat_history)
        chat_canvas = getattr(self.chat_history, "_parent_canvas", None)
        if chat_canvas is not None:
            self._bind_chat_scroll_widget(chat_canvas)

        self.project_tree_pane = ProjectTreePane(
            self.run_tab,
            translator=self._t,
            open_path_callback=self._open_path,
            import_file_callback=self._add_project_source_file,
            import_folder_callback=self._add_project_source_folder,
            delete_callback=self._delete_selected_project_tree_item,
            toggle_callback=self._toggle_project_tree,
            show_internal_files=self.show_internal_project_files_var.get(),
        )
        self.project_tree_pane.grid(row=1, column=1, sticky="nsew", padx=(6, 10), pady=(0, 6))
        self.project_tree_pane.tree.bind("<ButtonPress-1>", self._start_tree_item_drag, add="+")
        self._apply_project_tree_layout()

        self.composer_frame = ctk.CTkFrame(self.run_tab)
        self.composer_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))
        self.composer_frame.grid_columnconfigure(0, weight=1)
        self.composer_frame.grid_columnconfigure(1, weight=0)
        self.composer_frame.configure(border_width=0, border_color=("gray70", "#334155"))

        self.input_frame = ctk.CTkFrame(self.composer_frame, fg_color="transparent")
        self.input_frame.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=12)
        self.input_frame.grid_columnconfigure(0, weight=1)
        self.input_frame.grid_rowconfigure(0, weight=1)

        self.chat_input = ctk.CTkTextbox(self.input_frame, height=68, wrap="word")
        self.chat_input.grid(row=0, column=0, sticky="ew")
        self.chat_input.bind("<Return>", self._on_send_shortcut)
        self.chat_input.bind("<Shift-Return>", self._on_newline_shortcut)
        self.send_button = ctk.CTkButton(
            self.input_frame,
            text=self._t("run.button.send"),
            command=self._submit_chat_input,
            width=76,
            height=28,
        )
        self.send_button.place(relx=1.0, rely=1.0, x=-8, y=-8, anchor="se")

        action_frame = ctk.CTkFrame(self.composer_frame, fg_color="transparent")
        action_frame.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=12)
        left_actions = ctk.CTkFrame(action_frame, fg_color="transparent")
        left_actions.pack(side="left", padx=(0, 8))
        browse_button_width = 126
        self.browse_file_button = ctk.CTkButton(
            left_actions,
            text=self._t("run.button.browse_file"),
            command=self._browse_input_file,
            width=browse_button_width,
            height=30,
        )
        self.browse_file_button.pack(anchor="e", pady=(0, 8))
        self.browse_folder_button = ctk.CTkButton(
            left_actions,
            text=self._t("run.button.browse_folder"),
            command=self._browse_input_folder,
            width=browse_button_width,
            height=30,
        )
        self.browse_folder_button.pack(anchor="e")
        self.open_output_button = ctk.CTkButton(
            action_frame,
            text=self._t("run.button.open_output"),
            command=self._open_output_folder,
            width=68,
            height=68,
            fg_color="#f59e0b",
            hover_color="#d97706",
            text_color="#111827",
        )
        self.open_output_button.pack(side="left")

        self._configure_drop_targets()


    def _build_settings_tab(self) -> None:
        self.settings_tab.grid_columnconfigure(0, weight=1)
        self.settings_tab.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self.settings_tab)
        body.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body, text=self._t("settings.language")).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        self.language_combo = ctk.CTkComboBox(
            body,
            variable=self.language_var,
            values=self.localizer.language_options(),
            state="readonly",
        )
        self.language_combo.grid(row=0, column=1, sticky="ew", padx=12, pady=(12, 6))

        ctk.CTkLabel(body, text=self._t("settings.llm_provider")).grid(row=1, column=0, sticky="w", padx=12, pady=6)
        self.provider_combo = ctk.CTkComboBox(
            body,
            variable=self.provider_var,
            values=["openrouter", "openai"],
            state="readonly",
            command=lambda _value: self._refresh_api_key_placeholder(),
        )
        self.provider_combo.grid(row=1, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(body, text=self._t("settings.model")).grid(row=2, column=0, sticky="w", padx=12, pady=6)
        ctk.CTkEntry(body, textvariable=self.model_var).grid(row=2, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(body, text=self._t("settings.api_key")).grid(row=3, column=0, sticky="w", padx=12, pady=6)
        api_frame = ctk.CTkFrame(body, fg_color="transparent")
        api_frame.grid(row=3, column=1, sticky="ew", padx=12, pady=6)
        api_frame.grid_columnconfigure(0, weight=1)
        self.api_key_entry = ctk.CTkEntry(api_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkSwitch(
            api_frame,
            text=self._t("settings.show_api_key"),
            variable=self.show_api_key_var,
            command=self._toggle_api_key_visibility,
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(body, text=self._t("settings.base_url")).grid(row=4, column=0, sticky="w", padx=12, pady=6)
        ctk.CTkEntry(body, textvariable=self.base_url_var).grid(row=4, column=1, sticky="ew", padx=12, pady=6)

        review_frame = ctk.CTkFrame(body, fg_color="transparent")
        review_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=(6, 2))
        review_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            review_frame,
            text=self._t("settings.auto_accept_review_steps"),
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkSwitch(
            review_frame,
            text=self._t("settings.enabled"),
            variable=self.auto_accept_review_steps_var,
        ).grid(row=0, column=1, sticky="e")

        internal_files_frame = ctk.CTkFrame(body, fg_color="transparent")
        internal_files_frame.grid(row=6, column=0, columnspan=2, sticky="ew", padx=12, pady=(2, 8))
        internal_files_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            internal_files_frame,
            text=self._t("settings.show_internal_project_files"),
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkSwitch(
            internal_files_frame,
            text=self._t("settings.enabled"),
            variable=self.show_internal_project_files_var,
            command=self._on_toggle_show_internal_project_files,
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(body, text=self._t("settings.output_display_mode")).grid(row=7, column=0, sticky="w", padx=12, pady=(2, 8))
        self.output_display_mode_combo = ctk.CTkComboBox(
            body,
            variable=self.output_display_mode_var,
            values=[
                self._t("settings.output_mode.hybrid"),
                self._t("settings.output_mode.full"),
                self._t("settings.output_mode.preview"),
            ],
            state="readonly",
        )
        self.output_display_mode_combo.grid(row=7, column=1, sticky="ew", padx=12, pady=(2, 8))

        workspace_section = ctk.CTkFrame(body)
        workspace_section.grid(row=8, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))
        workspace_section.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            workspace_section,
            text=self._t("settings.workspace_section"),
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(workspace_section, text=self._t("settings.workspace_root")).grid(
            row=1, column=0, sticky="w", padx=12, pady=6
        )
        ctk.CTkEntry(workspace_section, textvariable=self.workspace_root_var).grid(
            row=1, column=1, sticky="ew", padx=12, pady=6
        )
        ctk.CTkButton(
            workspace_section,
            text=self._t("settings.browse_workspace"),
            command=self._browse_workspace,
            width=150,
        ).grid(row=1, column=2, sticky="e", padx=12, pady=6)

        ctk.CTkLabel(workspace_section, text=self._t("settings.active_project")).grid(
            row=2, column=0, sticky="w", padx=12, pady=6
        )
        self.project_combo = ctk.CTkComboBox(
            workspace_section,
            variable=self.project_var,
            values=[""],
            state="readonly",
            command=self._on_project_changed,
        )
        self.project_combo.grid(row=2, column=1, sticky="ew", padx=12, pady=6)
        project_buttons = ctk.CTkFrame(workspace_section, fg_color="transparent")
        project_buttons.grid(row=2, column=2, sticky="e", padx=12, pady=6)
        ctk.CTkButton(project_buttons, text=self._t("settings.refresh_projects"), command=self._refresh_projects, width=90).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(project_buttons, text=self._t("settings.new_project"), command=self._create_project, width=110).pack(side="left")

        ctk.CTkLabel(workspace_section, text=self._t("settings.project_inputs")).grid(
            row=3, column=0, sticky="w", padx=12, pady=6
        )
        inputs_frame = ctk.CTkFrame(workspace_section, fg_color="transparent")
        inputs_frame.grid(row=3, column=1, columnspan=2, sticky="ew", padx=12, pady=6)
        inputs_frame.grid_columnconfigure(0, weight=1)
        self.project_inputs_entry = ctk.CTkEntry(inputs_frame, textvariable=self.project_inputs_var)
        self.project_inputs_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.project_inputs_entry.configure(state="disabled")
        ctk.CTkButton(
            inputs_frame,
            text=self._t("settings.open"),
            command=self._open_project_inputs_folder,
            width=90,
        ).grid(row=0, column=1)

        ctk.CTkLabel(workspace_section, text=self._t("settings.project_outputs")).grid(
            row=4, column=0, sticky="w", padx=12, pady=6
        )
        outputs_frame = ctk.CTkFrame(workspace_section, fg_color="transparent")
        outputs_frame.grid(row=4, column=1, columnspan=2, sticky="ew", padx=12, pady=(6, 12))
        outputs_frame.grid_columnconfigure(0, weight=1)
        self.project_outputs_entry = ctk.CTkEntry(outputs_frame, textvariable=self.project_outputs_var)
        self.project_outputs_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.project_outputs_entry.configure(state="disabled")
        ctk.CTkButton(
            outputs_frame,
            text=self._t("settings.open"),
            command=self._open_project_folder,
            width=90,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            outputs_frame,
            text=self._t("settings.open_outputs"),
            command=self._open_output_folder,
            width=120,
        ).grid(row=0, column=2)

        ctk.CTkLabel(body, text=self._t("settings.fallback_output_root")).grid(
            row=9, column=0, sticky="w", padx=12, pady=(10, 6)
        )
        output_frame = ctk.CTkFrame(body, fg_color="transparent")
        output_frame.grid(row=9, column=1, sticky="ew", padx=12, pady=(10, 6))
        output_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(output_frame, textvariable=self.output_path_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ctk.CTkButton(output_frame, text=self._t("settings.browse"), command=self._browse_output_folder, width=100).grid(
            row=0, column=1
        )

        footer_actions = ctk.CTkFrame(body, fg_color="transparent")
        footer_actions.grid(row=10, column=1, sticky="e", padx=12, pady=(16, 12))
        ctk.CTkButton(
            footer_actions,
            text=self._t("settings.help"),
            command=self._open_help_window,
            width=120,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            footer_actions,
            text=self._t("settings.save"),
            command=self._save_settings,
            width=160,
        ).pack(side="left")

    def _build_logs_tab(self) -> None:
        self.logs_tab.grid_columnconfigure(0, weight=1)
        self.logs_tab.grid_rowconfigure(0, weight=1)

        self.logs_textbox = ctk.CTkTextbox(self.logs_tab, wrap="word")
        self.logs_textbox.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.logs_textbox.configure(state="disabled")

        ctk.CTkButton(self.logs_tab, text=self._t("logs.clear"), command=self._clear_logs, width=140).grid(
            row=1, column=0, sticky="e", padx=12, pady=(0, 12)
        )

    def _build_project_list(self) -> None:
        ctk.CTkLabel(
            self.project_section,
            text=self._t("sidebar.projects"),
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkButton(
            self.project_section,
            text=self._t("sidebar.new_project"),
            command=self._create_project,
            height=32,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.project_list = ctk.CTkScrollableFrame(self.project_section)
        self.project_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.project_list.grid_columnconfigure(0, weight=1)

    def _build_skill_sidebar(self) -> None:
        self.skill_selector.configure(values=self.skill_names or [""])
        if self.selected_skill_id:
            skill = self.skills_by_id.get(self.selected_skill_id)
            if skill is not None:
                self.skill_selector_var.set(skill.display_name)

    def _on_skill_dropdown_changed(self, display_name: str) -> None:
        skill_id = self.skill_name_to_id.get(display_name)
        if skill_id is not None:
            self._select_skill(skill_id)

    def _run_selected_skill(self) -> None:
        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.no_project"))
            return
        skill = self._selected_skill()
        if skill is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.choose_skill_from_header_first"))
            return
        if project.execution_in_progress or (self.worker is not None and self.worker.is_alive()):
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.workflow_running"))
            return
        if project.assistant_reply_pending or (self.assistant_worker is not None and self.assistant_worker.is_alive()):
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.workflow_running"))
            return

        project.selected_skill_id = skill.skill_id
        project.selected_skill_name = skill.display_name
        project.reset_for_new_skill_run()
        self._append_project_intro(project, skill)
        self._refresh_project_workspace()
        self._refresh_chat_view()
        self._refresh_project_list()
        self._update_composer_state()
        self._save_current_project()

    def _on_run_skill_button(self) -> None:
        mode = self._run_button_mode()
        if mode == "running":
            self._request_stop_workflow()
            return
        if mode == "stopping":
            return
        self._run_selected_skill()

    def _on_run_button_enter(self, _event: Any) -> None:
        self._run_button_hover_active = True
        self._update_run_button_state()

    def _on_run_button_leave(self, _event: Any) -> None:
        self._run_button_hover_active = False
        self._update_run_button_state()

    def _run_button_mode(self) -> str:
        worker_alive = self.worker is not None and self.worker.is_alive()
        assistant_alive = self.assistant_worker is not None and self.assistant_worker.is_alive()
        session = self._current_project()
        if session is not None and worker_alive and self.running_project_id == session.id:
            if session.stage == "cancelling":
                return "stopping"
            return "running"
        if worker_alive or assistant_alive:
            return "busy"
        return "idle"

    def _update_run_button_state(self) -> None:
        if not hasattr(self, "run_skill_button"):
            return

        mode = self._run_button_mode()
        base_fg = ("#3b82f6", "#2563eb")
        base_hover = ("#2563eb", "#1d4ed8")
        stop_fg = ("#f59e0b", "#d97706")
        stop_hover = ("#ef4444", "#dc2626")
        stopping_fg = ("#6b7280", "#475569")

        if mode == "running":
            hover_stop = self._run_button_hover_active
            self.run_skill_button.configure(
                state="normal",
                text=self._t("project.header.stop") if hover_stop else self._t("project.header.running"),
                fg_color=stop_fg if hover_stop else stopping_fg,
                hover_color=stop_hover if hover_stop else stop_fg,
                text_color="#f8fafc",
            )
            return
        if mode == "stopping":
            self.run_skill_button.configure(
                state="disabled",
                text=self._t("project.header.stopping"),
                fg_color=stopping_fg,
                hover_color=stopping_fg,
                text_color="#f8fafc",
            )
            return
        if mode == "busy":
            self.run_skill_button.configure(
                state="disabled",
                text=self._t("project.header.run"),
                fg_color=base_fg,
                hover_color=base_hover,
                text_color="#f8fafc",
            )
            return
        self.run_skill_button.configure(
            state="normal" if self.current_project_id is not None else "disabled",
            text=self._t("project.header.run"),
            fg_color=base_fg,
            hover_color=base_hover,
            text_color="#f8fafc",
        )

    def _request_stop_workflow(self) -> None:
        project = self._current_project()
        worker = self.worker
        if project is None or worker is None or not worker.is_alive() or self.running_project_id != project.id:
            return
        if not messagebox.askyesno(self._t("dialog.stop_workflow"), self._t("warning.stop_workflow_confirm")):
            return

        project.stage = "cancelling"
        project.current_prompt = self._t("chat.run_cancelling")
        project.current_choices = []
        project.touch()
        self.status_var.set(self._t("status.cancelling"))
        self._append_chat_message(project.id, "status", self._t("project.activity.run_cancelling"))
        self._refresh_chat_view()
        self._refresh_project_workspace()
        self._refresh_project_list()
        self._update_composer_state()
        self._save_current_project()
        worker.request_cancel()

    def _build_sidebar_nav(self, parent: ctk.CTkFrame) -> None:
        nav_items = [
            ("run", "📁", self._t("nav.run")),
            ("settings", "⚙", self._t("nav.settings")),
            ("logs", "📄", self._t("nav.logs")),
        ]
        for row, (page_name, icon_text, label) in enumerate(nav_items):
            row_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_frame.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 8, 0))
            row_frame.grid_columnconfigure(1, weight=1)
            icon_label = ctk.CTkLabel(
                row_frame,
                text=icon_text,
                width=24,
                anchor="w",
                text_color=("gray20", "#e5e7eb"),
            )
            icon_label.grid(row=0, column=0, sticky="w", padx=(10, 4))
            button = ctk.CTkButton(
                row_frame,
                text=label,
                anchor="w",
                fg_color="transparent",
                hover_color=("gray78", "gray24"),
                command=lambda name=page_name: self._show_page(name),
            )
            button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
            row_frame.bind("<Button-1>", lambda _event, name=page_name: self._show_page(name), add="+")
            icon_label.bind("<Button-1>", lambda _event, name=page_name: self._show_page(name), add="+")
            self.nav_row_frames[page_name] = row_frame
            self.nav_icon_labels[page_name] = icon_label
            self.nav_buttons[page_name] = button

    def _show_page(self, page_name: str) -> None:
        pages = {
            "run": self.run_tab,
            "settings": self.settings_tab,
            "logs": self.logs_tab,
        }
        target = pages.get(page_name)
        if target is None:
            return
        self.selected_page = page_name
        target.tkraise()
        for current_name, button in self.nav_buttons.items():
            active = current_name == page_name
            button.configure(fg_color=("gray72", "gray28") if active else "transparent")
            row_frame = self.nav_row_frames.get(current_name)
            if row_frame is not None:
                row_frame.configure(fg_color=("gray72", "gray28") if active else "transparent")

    def _toggle_workspace_section(self) -> None:
        self.workspace_section_expanded = not self.workspace_section_expanded
        self._update_workspace_section_visibility()

    def _update_workspace_section_visibility(self) -> None:
        if hasattr(self, "workspace_details_frame"):
            if self.workspace_section_expanded:
                self.workspace_details_frame.grid()
            else:
                self.workspace_details_frame.grid_remove()
        if hasattr(self, "workspace_toggle_button"):
            arrow = "▾" if self.workspace_section_expanded else "▸"
            self.workspace_toggle_button.configure(text=f"{arrow} {self._t('project.header.title')}")

    def _toggle_project_tree(self) -> None:
        self.project_tree_expanded = not self.project_tree_expanded
        self._apply_project_tree_layout()

    def _apply_project_tree_layout(self) -> None:
        if not hasattr(self, "project_tree_pane"):
            return
        min_width = ProjectTreePane.DEFAULT_WIDTH if self.project_tree_expanded else ProjectTreePane.COLLAPSED_WIDTH
        self.run_tab.grid_columnconfigure(1, minsize=min_width)
        self.project_tree_pane.set_collapsed(not self.project_tree_expanded)
        self.project_tree_pane.grid_configure(padx=(6 if self.project_tree_expanded else 2, 10))

    def _configure_drop_targets(self) -> None:
        chat_widgets = self._composer_drop_widgets()
        for widget in chat_widgets:
            register_file_drop(widget, self._handle_chat_drop)
        if hasattr(self, "project_tree_pane"):
            for widget in self.project_tree_pane.drop_widgets():
                register_file_drop(widget, self._handle_project_tree_drop)
        self.bind_all("<Motion>", self._track_tree_drag_hover, add="+")
        self.bind_all("<ButtonRelease-1>", self._handle_global_tree_release)

    def _composer_drop_widgets(self) -> list[object]:
        return [
            self.composer_frame,
            self.input_frame,
            self.chat_input,
            getattr(self.chat_input, "_textbox", None),
        ]

    def _widget_in_composer(self, widget: object | None) -> bool:
        current = widget
        composer_widgets = {item for item in self._composer_drop_widgets() if item is not None}
        while current is not None:
            if current in composer_widgets:
                return True
            current = getattr(current, "master", None)
        return False

    def _start_tree_item_drag(self, event: Any) -> None:
        if not hasattr(self, "project_tree_pane"):
            self._tree_drag_path = None
            self._hide_tree_drag_badge()
            return
        self._tree_drag_path = self.project_tree_pane.path_at_y(event.y)
        self._set_composer_drop_hover(False)
        if self._tree_drag_path is None:
            self._hide_tree_drag_badge()
            return
        self._show_tree_drag_badge(self._tree_drag_path.name)
        self._move_tree_drag_badge(getattr(event, "x_root", 0), getattr(event, "y_root", 0))

    def _track_tree_drag_hover(self, event: Any) -> None:
        if self._tree_drag_path is None:
            if self._composer_drop_hover_active:
                self._set_composer_drop_hover(False)
            self._hide_tree_drag_badge()
            return
        self._move_tree_drag_badge(getattr(event, "x_root", 0), getattr(event, "y_root", 0))
        target_widget = self.winfo_containing(getattr(event, "x_root", 0), getattr(event, "y_root", 0))
        self._set_composer_drop_hover(self._widget_in_composer(target_widget))

    def _handle_global_tree_release(self, event: Any) -> None:
        path = self._tree_drag_path
        self._set_composer_drop_hover(False)
        self._hide_tree_drag_badge()
        if path is None or not path.exists():
            return

        target_widget = self.winfo_containing(getattr(event, "x_root", 0), getattr(event, "y_root", 0))
        if not self._widget_in_composer(target_widget):
            self._tree_drag_path = None
            return

        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.no_project"))
            self._tree_drag_path = None
            return

        message = self._t("project.drop.chat_tree_added", name=path.name)
        self.status_var.set(message)
        self._append_chat_message(project.id, "status", message)
        self._tree_drag_path = None
        self._submit_chat_input(str(path))

    def _set_composer_drop_hover(self, active: bool) -> None:
        if self._composer_drop_hover_active == active or not hasattr(self, "composer_frame"):
            return
        self._composer_drop_hover_active = active
        if active:
            self.composer_frame.configure(
                border_width=1,
                border_color=("#60a5fa", "#3b82f6"),
            )
        else:
            self.composer_frame.configure(
                border_width=0,
                border_color=("gray70", "#334155"),
            )

    def _show_tree_drag_badge(self, text: str) -> None:
        if self._tree_drag_badge is None or not self._tree_drag_badge.winfo_exists():
            self._tree_drag_badge = ctk.CTkLabel(
                self,
                text="",
                fg_color=("#e5e7eb", "#111827"),
                text_color=("#111827", "#f8fafc"),
                corner_radius=12,
                padx=10,
                pady=6,
            )
        self._tree_drag_badge.configure(text=f"  {text}")
        self._tree_drag_badge.lift()
        self._tree_drag_badge.place(x=-9999, y=-9999)

    def _move_tree_drag_badge(self, x_root: int, y_root: int) -> None:
        if self._tree_drag_badge is None or not self._tree_drag_badge.winfo_exists():
            return
        x = x_root - self.winfo_rootx() + 16
        y = y_root - self.winfo_rooty() + 16
        self._tree_drag_badge.place(x=x, y=y)

    def _hide_tree_drag_badge(self) -> None:
        if self._tree_drag_badge is not None and self._tree_drag_badge.winfo_exists():
            self._tree_drag_badge.place_forget()

    def _handle_chat_drop(self, event: Any) -> str:
        paths = extract_drop_paths(self, getattr(event, "data", ""))
        if not paths:
            return "break"
        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.no_project"))
            return "break"

        path = paths[0]
        if not path.exists():
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.drop_missing"))
            return "break"

        key = "project.drop.chat_multi" if len(paths) > 1 else "project.drop.chat_added"
        message = self._t(key, name=path.name)
        self.status_var.set(message)
        self._append_chat_message(project.id, "status", message)
        self._submit_chat_input(str(path))
        return "break"

    def _handle_project_tree_drop(self, event: Any) -> str:
        paths = extract_drop_paths(self, getattr(event, "data", ""))
        if not paths:
            return "break"
        try:
            imported = self._import_paths_into_project(paths)
        except ValueError as exc:
            messagebox.showwarning(self._t("dialog.run"), str(exc))
            return "break"

        project = self._current_project()
        if project is not None:
            for item in imported:
                message = self._t("project.drop.imported", name=item.name)
                self.status_var.set(message)
                self._append_chat_message(project.id, "status", message)
        self._refresh_project_workspace()
        self._refresh_project_list()
        return "break"

    def _on_toggle_show_internal_project_files(self) -> None:
        self._refresh_project_tree()

    def _load_saved_projects(self) -> None:
        self.projects = {project.id: project for project in self.project_store.list_projects()}
        self.current_project_id = None

    def _restore_initial_project(self) -> None:
        target = None
        if self.selected_project_name:
            target = next((item for item in self.projects.values() if item.name == self.selected_project_name), None)
        if target is None and self.projects:
            target = self._sorted_projects()[0]
        if target is not None:
            self._select_project(target.id)
            return

        default_skill_id = self.settings.default_skill_id
        if default_skill_id not in self.skills_by_id and self.skills:
            default_skill_id = self.skills[0].skill_id
        if default_skill_id in self.skills_by_id:
            self.selected_skill_id = default_skill_id
            self.skill_selector_var.set(self.skills_by_id[default_skill_id].display_name)
        self._refresh_project_workspace()
        self._refresh_project_list()
        self._update_composer_state()

    def _select_skill(self, skill_id: str) -> None:
        if skill_id not in self.skills_by_id:
            return
        project = self._current_project()
        if project is not None and (project.execution_in_progress or project.assistant_reply_pending):
            current_skill = self.skills_by_id.get(self.selected_skill_id or "")
            if current_skill is not None:
                self.skill_selector_var.set(current_skill.display_name)
            return

        skill = self.skills_by_id[skill_id]
        self.selected_skill_id = skill_id
        self.skill_selector_var.set(skill.display_name)
        if project is not None:
            project.selected_skill_id = skill.skill_id
            project.selected_skill_name = skill.display_name
            project.reset_for_new_skill_run()
            self.project_store.save(project)
            self._refresh_project_workspace()
            self._refresh_project_list()
            self._update_composer_state()
        else:
            self._refresh_project_workspace()
        self._persist_gui_state()

    def _select_project(self, project_id: str) -> None:
        project = self.projects.get(project_id)
        if project is None:
            return
        self.current_project_id = project.id
        self.selected_project_name = project.name
        self.project_var.set(project.name)
        self.project_title_var.set(project.name)
        self.project_description_var.set(project.description or self._t("project.header.description_fallback"))
        self.project_inputs_var.set(project.inputs_path)
        self.project_outputs_var.set(project.outputs_path)
        self.last_output_dir = Path(project.outputs_path)

        target_skill_id = project.selected_skill_id or self.selected_skill_id or self.settings.default_skill_id
        if target_skill_id not in self.skills_by_id and self.skills:
            target_skill_id = self.skills[0].skill_id
        if target_skill_id in self.skills_by_id:
            self.selected_skill_id = target_skill_id
            skill = self.skills_by_id[target_skill_id]
            project.selected_skill_id = skill.skill_id
            project.selected_skill_name = skill.display_name
            self.skill_selector_var.set(skill.display_name)

        self._refresh_project_workspace()
        self._refresh_chat_view()
        self._refresh_project_list()
        self._update_composer_state()
        self._persist_gui_state()
        self.project_store.save(project)
        self._show_page("run")

    def _sorted_projects(self) -> list[ProjectState]:
        return sorted(self.projects.values(), key=lambda item: item.updated_at, reverse=True)

    def _current_project(self) -> ProjectState | None:
        if self.current_project_id is None:
            return None
        return self.projects.get(self.current_project_id)

    def _refresh_project_list(self) -> None:
        for child in self.project_list.winfo_children():
            child.destroy()
        self.project_buttons.clear()

        for row, project in enumerate(self._sorted_projects()):
            row_frame = ctk.CTkFrame(
                self.project_list,
                fg_color=("gray72", "gray28") if project.id == self.current_project_id else "transparent",
            )
            row_frame.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
            row_frame.grid_columnconfigure(0, weight=1)

            button = ctk.CTkButton(
                row_frame,
                text=self._shorten_text(project.name, limit=28),
                anchor="w",
                height=40,
                fg_color="transparent",
                hover_color=("gray78", "gray24"),
                command=lambda project_id=project.id: self._select_project(project_id),
            )
            button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ctk.CTkButton(
                row_frame,
                text="✕",
                width=28,
                height=28,
                fg_color="transparent",
                hover_color=("#fca5a5", "#7f1d1d"),
                command=lambda project_id=project.id: self._delete_project(project_id),
            ).grid(row=0, column=1, sticky="ne", pady=4)
            self.project_buttons[project.id] = button

    def _save_current_project(self) -> None:
        project = self._current_project()
        if project is not None:
            self.project_store.save(project)

    def _delete_project(self, project_id: str) -> None:
        project = self.projects.get(project_id)
        if project is None:
            return
        if self.worker is not None and self.worker.is_alive() and self.running_project_id == project.id:
            messagebox.showwarning(self._t("project.delete.title"), self._t("warning.project_delete_running"))
            return
        if not messagebox.askyesno(self._t("project.delete.title"), self._t("project.delete.confirm", name=project.name)):
            return
        self.project_store.delete(project)
        self.projects.pop(project.id, None)
        self.current_project_id = None
        self.selected_project_name = ""
        replacement = self._sorted_projects()[0] if self.projects else None
        self._refresh_project_list()
        if replacement is not None:
            self._select_project(replacement.id)
        else:
            self.project_title_var.set(self._t("project.status.empty"))
            self.project_description_var.set(self._t("project.header.description_fallback"))
            self.selected_skill_info_var.set(self._selected_skill_info_text())
            self.project_summary_var.set("")
            self._refresh_chat_view()
            self._update_composer_state()

    def _display_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H-%M")

    def _format_timestamp_for_title(self, timestamp: str) -> str:
        cleaned = timestamp.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d %H-%M")
        except ValueError:
            return self._t("common.conversation")

    def _refresh_project_workspace(self) -> None:
        project = self._current_project()
        if project is None:
            self.project_title_var.set(self._t("project.status.empty"))
            self.project_description_var.set(self._t("project.header.description_fallback"))
            self.selected_skill_info_var.set(self._selected_skill_info_text())
            self.project_summary_var.set("")
            self._refresh_project_tree()
            self._refresh_run_context()
            self._update_run_button_state()
            return

        self.project_title_var.set(project.name)
        self.project_description_var.set(project.description or self._t("project.header.description_fallback"))
        self.selected_skill_info_var.set(self._selected_skill_info_text())
        self.project_summary_var.set(self._project_summary(project))
        self._refresh_project_tree()
        self._refresh_run_context()
        self._update_run_button_state()

    def _refresh_project_tree(self) -> None:
        if not hasattr(self, "project_tree_pane"):
            return
        project = self._current_project()
        self.project_tree_pane.set_show_internal_files(self.show_internal_project_files_var.get())
        root = project.project_root() if project is not None else None
        self.project_tree_pane.set_project_root(root)

    def _project_summary(self, project: ProjectState) -> str:
        lines = [
            self._t("project.summary.project", name=project.name),
            self._t("project.summary.source_count", count=len(project.source_inputs)),
            self._t("project.summary.output", path=self._shorten_text(project.outputs_path, limit=88)),
            self._t("project.summary.next_step", value=self._recommended_next_step(project)),
        ]
        return " | ".join(lines)

    def _selected_skill_info_text(self) -> str:
        skill = self._selected_skill()
        if skill is None:
            return self._t("project.skill_info.empty")

        lines = [skill.display_name]
        if skill.description.strip():
            lines.extend(["", skill.description.strip()])

        workflow_hint = self._skill_workflow_hint(skill)
        if workflow_hint:
            lines.extend(["", self._t("project.skill_info.workflow", value=workflow_hint)])

        input_hint = self._skill_input_hint(skill)
        if input_hint:
            lines.append(self._t("project.skill_info.input", value=input_hint))

        output_hint = self._skill_output_hint(skill)
        if output_hint:
            lines.append(self._t("project.skill_info.output", value=output_hint))
        return "\n".join(lines).strip()

    def _recommended_next_step(self, project: ProjectState) -> str:
        if not project.source_inputs:
            return self._t("common.needs_input")
        if project.latest_result is None:
            skill = self.skills_by_id.get(project.selected_skill_id or "")
            if skill is not None:
                return skill.display_name
        if self.skills:
            return self.skills[0].display_name
        return self._t("common.ready")

    def _append_project_intro(self, project: ProjectState, skill: GuiSkillOption) -> None:
        intro = self._build_initial_conversation_message(skill, project.name)
        self._append_chat_message(project.id, "assistant", intro)
        self._prompt_for_primary_input(skill, project)

    def _submit_chat_input(self, preset_text: str | None = None) -> None:
        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.no_project"))
            return
        skill = self._selected_skill()
        if skill is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.choose_skill_from_header_first"))
            return
        if project.selected_skill_id != skill.skill_id:
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.run_skill_first"))
            return
        if project.execution_in_progress and project.stage != "waiting_for_input":
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.workflow_running"))
            return
        if project.assistant_reply_pending:
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.workflow_running"))
            return
        if project.stage == "idle" and not project.current_prompt.strip():
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.run_skill_first"))
            return

        text = (preset_text if preset_text is not None else self.chat_input.get("1.0", "end")).strip()
        if not text:
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.enter_reply_first"))
            return
        if preset_text is None:
            self._clear_chat_input()

        self._append_chat_message(project.id, "user", text)
        if project.execution_in_progress and project.stage == "waiting_for_input":
            self._submit_worker_reply(project, text)
            self._refresh_chat_view()
            return
        if self._should_use_llm_reply(skill, project, text):
            self._start_llm_reply(skill, project, text)
            self._refresh_chat_view()
            return
        try:
            self._handle_chat_reply(skill, project, text)
        except ValueError as exc:
            self._append_chat_message(project.id, "error", str(exc))
        self._refresh_chat_view()

    def _handle_chat_reply(self, skill: GuiSkillOption, session: ProjectState, text: str) -> None:
        stage = session.stage
        if stage == "awaiting_input":
            self._capture_primary_input(skill, session, text)
            return
        if stage == "awaiting_step":
            self._capture_step_selection(skill, session, text)
            return
        if stage == "awaiting_rewriting_mode":
            self._capture_rewriting_mode(skill, session, text)
            return
        if stage == "awaiting_rewriting_plan":
            self._capture_existing_path(text, self._t("workflow.error.invalid_adaptation_plan"))
            session.rewriting_plan_path = self._normalize_existing_path(text)
            self._prompt_for_rewriting_supplemental(skill, session)
            return
        if stage == "awaiting_rewriting_bible":
            session.rewriting_bible_path = self._resolve_bible_selection(text)
            self._prompt_for_next_runtime_or_confirmation(skill, session)
            return
        if stage == "awaiting_rewriting_supplemental":
            session.rewriting_supplemental_path = self._resolve_optional_existing_path(text)
            self._prompt_for_next_runtime_or_confirmation(skill, session)
            return
        if stage == "awaiting_runtime":
            self._capture_runtime_value(skill, session, text)
            return
        if stage == "ready_to_run":
            self._handle_run_confirmation(skill, session, text)
            return
        raise ValueError(self._t("workflow.error.not_ready"))

    def _capture_primary_input(self, skill: GuiSkillOption, session: ProjectState, text: str) -> None:
        session.input_path = ""
        session.direct_text = ""

        normalized = text.strip().lower()
        if normalized in {"default", "1"} and session.source_inputs:
            candidate_path = Path(session.source_inputs[0].path)
            if not candidate_path.exists():
                raise ValueError(self._t("project.error.source_missing"))
            candidate = str(candidate_path)
        elif text.strip().isdigit() and session.source_inputs:
            index = int(text.strip())
            if not 1 <= index <= len(session.source_inputs):
                raise ValueError(self._t("project.error.source_number"))
            candidate_path = Path(session.source_inputs[index - 1].path)
            if not candidate_path.exists():
                raise ValueError(self._t("project.error.source_missing"))
            candidate = str(candidate_path)
        else:
            candidate = text.strip().strip('"')
        if candidate:
            path = Path(candidate).expanduser()
            if path.exists():
                resolved = str(path.resolve())
                if path.is_dir() and not skill.supports_folder_input:
                    raise ValueError(self._t("workflow.error.skill_no_folder"))
                if path.is_file() and not skill.supports_file_input:
                    raise ValueError(self._t("workflow.error.skill_no_file"))
                session.input_path = resolved
            elif skill.supports_text_input:
                session.direct_text = text.strip()
            else:
                raise ValueError(self._t("workflow.error.path_required"))

        if not session.input_path and not session.direct_text:
            raise ValueError(self._t("workflow.error.valid_input_required"))

        if skill.skill_id == "rewriting":
            self._prompt_for_rewriting_mode(skill, session)
            return
        if skill.startup_mode == "explicit_step_selection":
            self._prompt_for_step_selection(skill, session)
            return
        self._prompt_for_next_runtime_or_confirmation(skill, session)

    def _capture_step_selection(self, skill: GuiSkillOption, session: ProjectState, text: str) -> None:
        raw_value = text.strip().lower()
        if raw_value in {"auto", "default", ""}:
            if skill.allow_auto_route:
                session.selected_step_number = None
            elif skill.default_step_number is not None:
                session.selected_step_number = skill.default_step_number
            else:
                raise ValueError(self._t("workflow.error.step_required"))
        else:
            try:
                step_number = int(text.strip().split(" ", 1)[0])
            except ValueError as exc:
                raise ValueError(self._t("workflow.error.step_auto_or_number")) from exc
            valid_steps = {step.number for step in skill.step_summaries}
            if step_number not in valid_steps:
                raise ValueError(self._t("workflow.error.step_unavailable"))
            session.selected_step_number = step_number

        self._prompt_for_next_runtime_or_confirmation(skill, session)

    def _capture_rewriting_mode(self, skill: GuiSkillOption, session: ProjectState, text: str) -> None:
        normalized = text.strip().lower()
        mapping = {
            "1": "build_bible",
            "build_bible": "build_bible",
            "build bible": "build_bible",
            "2": "rewrite_with_bible",
            "rewrite_with_bible": "rewrite_with_bible",
            "rewrite with bible": "rewrite_with_bible",
            "3": "build_bible_and_rewrite",
            "build_bible_and_rewrite": "build_bible_and_rewrite",
            "build bible and rewrite": "build_bible_and_rewrite",
            "auto": "build_bible_and_rewrite",
            "default": "build_bible_and_rewrite",
        }
        mode = mapping.get(normalized)
        if mode is None:
            raise ValueError(self._t("workflow.error.rewriting_mode_invalid"))
        session.rewriting_mode = mode

        if mode in {"build_bible", "build_bible_and_rewrite"}:
            self._prompt_for_rewriting_plan(skill, session)
            return
        self._prompt_for_rewriting_bible(skill, session)

    def _capture_runtime_value(self, skill: GuiSkillOption, session: ProjectState, text: str) -> None:
        fields = self._filtered_runtime_fields(skill, session)
        if session.runtime_field_index >= len(fields):
            self._prompt_for_ready_to_run(skill, session)
            return

        field = fields[session.runtime_field_index]
        value = self._normalize_runtime_value(field, text)
        if value == "":
            session.runtime_values.pop(field.name, None)
        else:
            session.runtime_values[field.name] = value
        session.runtime_field_index += 1
        self._prompt_for_next_runtime_or_confirmation(skill, session)

    def _handle_run_confirmation(self, skill: GuiSkillOption, session: ProjectState, text: str) -> None:
        normalized = text.strip().lower()
        if normalized in {"2", "restart", "reset", "new"}:
            session.reset_for_new_skill_run()
            self._append_project_intro(session, skill)
            self._refresh_chat_view()
            self._refresh_project_workspace()
            return
        if normalized not in {"1", "run", "start", "yes", "y", "go"}:
            raise ValueError(self._t("workflow.error.run_confirmation"))
        self._start_run(skill, session)

    def _should_use_llm_reply(self, skill: GuiSkillOption, session: ProjectState, text: str) -> bool:
        if should_route_to_workflow(skill, session, text):
            return False
        if is_question_like(text):
            return True
        if session.stage == "awaiting_runtime":
            field = current_runtime_field(skill, session)
            if field is not None and field.field_type == "text":
                return False
        if session.stage in {"awaiting_input", "awaiting_runtime", "ready_to_run", "awaiting_step", "awaiting_rewriting_mode"}:
            return True
        return False

    def _start_llm_reply(self, skill: GuiSkillOption, session: ProjectState, user_message: str) -> None:
        settings = AppSettings(
            provider=self.provider_var.get().strip().lower(),
            model=self.model_var.get().strip(),
            api_key=self.api_key_var.get().strip(),
            base_url=self.base_url_var.get().strip(),
            language=self._language_code(),
            auto_accept_review_steps=self.auto_accept_review_steps_var.get(),
            show_internal_project_files=self.show_internal_project_files_var.get(),
            output_display_mode=self._output_display_mode_code(),
            default_output_path=self.output_path_var.get().strip() or self.settings.default_output_path,
            default_skill_id=self.selected_skill_id or "",
            workspace_root=self.workspace_root_var.get().strip() or self.settings.workspace_root,
            last_project_name=self.project_var.get().strip(),
        )
        session.assistant_reply_pending = True
        session.touch()
        self.project_store.save(session)
        self._update_composer_state()
        request = AssistantRequest(
            repo_root=self.repo_root,
            settings=settings,
            messages=build_llm_messages(
                skill=skill,
                session=session,
                project_name=self.project_var.get().strip(),
                output_root=self._effective_output_root(),
                user_message=user_message,
            ),
        )
        self.assistant_worker = AssistantWorker(request, session.id, self.event_queue)
        self.assistant_worker.start()

    def _prompt_for_primary_input(self, skill: GuiSkillOption, session: ProjectState) -> None:
        prompt_lines = [self._skill_starter_prompt(skill)]
        input_hint = self._skill_input_hint(skill)
        if input_hint and input_hint != prompt_lines[0]:
            prompt_lines.extend(["", input_hint])
        if session.source_inputs:
            prompt_lines.extend(
                [
                    "",
                    self._t("project.prompt.attached_sources"),
                    *[f"{index}. {source.name}" for index, source in enumerate(session.source_inputs, start=1)],
                    self._t("project.prompt.reply_source_number"),
                    self._t("project.prompt.source_default"),
                ]
            )
        self._push_prompt(skill.skill_id, session, "awaiting_input", "\n".join(prompt_lines))

    def _prompt_for_step_selection(self, skill: GuiSkillOption, session: ProjectState) -> None:
        default_step = skill.default_step_number
        if default_step is None and skill.step_summaries:
            default_step = skill.step_summaries[0].number

        lines = [self._t("workflow.prompt.available_steps")]
        for step in skill.step_summaries:
            suffix = self._t("common.default_suffix") if step.number == default_step else ""
            detail = f" - {step.description}" if getattr(step, "description", "") else ""
            lines.append(f"{step.number}. {step.title}{suffix}{detail}")
        lines.append(self._t("workflow.prompt.reply_with_step"))
        self._push_prompt(skill.skill_id, session, "awaiting_step", "\n".join(lines))

    def _prompt_for_rewriting_mode(self, skill: GuiSkillOption, session: ProjectState) -> None:
        prompt = self._t("workflow.prompt.rewriting_mode")
        self._push_prompt(skill.skill_id, session, "awaiting_rewriting_mode", prompt)

    def _prompt_for_rewriting_plan(self, skill: GuiSkillOption, session: ProjectState) -> None:
        self._push_prompt(
            skill.skill_id,
            session,
            "awaiting_rewriting_plan",
            self._t("workflow.prompt.rewriting_plan"),
        )

    def _prompt_for_rewriting_bible(self, skill: GuiSkillOption, session: ProjectState) -> None:
        self._reload_bible_choices()
        if not self.bible_path_by_label:
            raise ValueError(self._t("workflow.error.rewriting_bible_missing"))
        lines = [self._t("workflow.prompt.rewriting_bibles")]
        for index, (label, path) in enumerate(self.bible_path_by_label.items(), start=1):
            lines.append(f"{index}. {label} - {path}")
        lines.append(self._t("workflow.prompt.rewriting_bible_reply"))
        self._push_prompt(skill.skill_id, session, "awaiting_rewriting_bible", "\n".join(lines))

    def _prompt_for_rewriting_supplemental(self, skill: GuiSkillOption, session: ProjectState) -> None:
        self._push_prompt(
            skill.skill_id,
            session,
            "awaiting_rewriting_supplemental",
            self._t("workflow.prompt.rewriting_supplemental"),
        )

    def _prompt_for_next_runtime_or_confirmation(self, skill: GuiSkillOption, session: ProjectState) -> None:
        fields = self._filtered_runtime_fields(skill, session)
        if session.runtime_field_index >= len(fields):
            self._prompt_for_ready_to_run(skill, session)
            return

        field = fields[session.runtime_field_index]
        prompt_lines = [field.prompt]
        if field.help_text:
            prompt_lines.append(field.help_text)
        if field.choices:
            for index, choice in enumerate(field.choices, start=1):
                suffix = self._t("common.default_suffix") if choice == field.default else ""
                prompt_lines.append(f"{index}. {choice}{suffix}")
            prompt_lines.append(self._t("workflow.prompt.runtime_reply_choice"))
        elif field.default not in (None, ""):
            prompt_lines.append(self._t("workflow.prompt.runtime_default", value=field.default))
        if not field.required:
            prompt_lines.append(self._t("workflow.prompt.runtime_skip"))
        self._push_prompt(skill.skill_id, session, "awaiting_runtime", "\n".join(prompt_lines))

    def _prompt_for_ready_to_run(self, skill: GuiSkillOption, session: ProjectState) -> None:
        output_root = self._effective_output_root()
        input_summary = session.input_path or self._shorten_text(session.direct_text)
        lines = [
            self._t("workflow.prompt.ready_title"),
            self._t("workflow.prompt.ready_input", value=input_summary),
            self._t("workflow.prompt.ready_output", value=output_root),
        ]
        if session.selected_step_number is not None:
            lines.append(self._t("workflow.prompt.ready_step", value=session.selected_step_number))
        if skill.skill_id == "rewriting":
            lines.append(self._t("workflow.prompt.ready_rewriting_mode", value=session.rewriting_mode))
        lines.append(self._t("workflow.prompt.ready_reply"))
        self._push_prompt(skill.skill_id, session, "ready_to_run", "\n".join(lines))

    def _push_prompt(self, skill_id: str, session: ProjectState, stage: str, text: str) -> None:
        session.stage = stage
        session.current_prompt = text
        session.touch()
        self._append_chat_message(session.id, "assistant", text)

    def _filtered_runtime_fields(self, skill: GuiSkillOption, session: ProjectState) -> list[GuiRuntimeInputField]:
        selected_step = session.selected_step_number
        fields: list[GuiRuntimeInputField] = []
        for field in skill.runtime_inputs:
            if selected_step is not None and field.step_numbers and selected_step not in field.step_numbers:
                continue
            fields.append(field)
        return fields

    def _normalize_runtime_value(self, field: GuiRuntimeInputField, text: str) -> str:
        value = text.strip()
        if not value and field.default not in (None, ""):
            value = str(field.default)
        if value.lower() == "skip":
            value = ""

        if field.required and not value:
            raise ValueError(self._t("workflow.error.runtime_required", prompt=field.prompt))
        if not value:
            return ""

        if field.field_type == "choice":
            if value.isdigit():
                index = int(value)
                if 1 <= index <= len(field.choices):
                    return field.choices[index - 1]
            choices = {choice.casefold(): choice for choice in field.choices}
            normalized_choice = choices.get(value.casefold())
            if normalized_choice is None:
                raise ValueError(self._t("workflow.error.runtime_choice"))
            return normalized_choice
        if field.field_type == "int":
            try:
                int(value)
            except ValueError as exc:
                raise ValueError(self._t("workflow.error.runtime_int")) from exc
            return value
        if field.field_type == "bool":
            lowered = value.lower()
            if lowered not in {"1", "0", "true", "false", "yes", "no", "y", "n", "on", "off"}:
                raise ValueError(self._t("workflow.error.runtime_bool"))
            return value
        return value

    def _start_run(self, skill: GuiSkillOption, session: ProjectState) -> None:
        if self.worker is not None and self.worker.is_alive():
            raise ValueError(self._t("warning.workflow_running"))
        if not self.model_var.get().strip():
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.model_empty_save_first"))
            raise ValueError(self._t("workflow.error.model_empty"))
        if not self.api_key_var.get().strip():
            messagebox.showwarning(self._t("dialog.run"), self._t("warning.api_key_empty_save_first"))
            raise ValueError(self._t("workflow.error.api_key_empty"))

        outputs_root = self._effective_output_root()
        outputs_root.mkdir(parents=True, exist_ok=True)
        request = GuiRunRequest(
            skill_id=skill.skill_id,
            input_path=session.input_path,
            outputs_root=str(outputs_root),
            direct_text=session.direct_text,
            selected_step_number=session.selected_step_number,
            runtime_values=dict(session.runtime_values),
            auto_accept_review_steps=self.auto_accept_review_steps_var.get(),
            rewriting_mode=session.rewriting_mode if skill.skill_id == "rewriting" else "",
            rewriting_plan_path=session.rewriting_plan_path,
            rewriting_bible_path=session.rewriting_bible_path,
            rewriting_supplemental_path=session.rewriting_supplemental_path,
        )

        self._persist_gui_state()
        session.execution_in_progress = True
        session.stage = "running"
        session.touch()
        self.running_project_id = session.id
        self.status_var.set(self._t("status.running"))
        self._update_composer_state()
        self._append_log(f"\n=== Run started: {skill.display_name} ===\n")
        self.worker = GuiWorker(self.backend, request, self.event_queue)
        self.worker.start()

    def _poll_worker_events(self) -> None:
        while True:
            try:
                event_type, payload = self.event_queue.get_nowait()
            except Empty:
                break

            if event_type == "log":
                self._append_log(str(payload))
            elif event_type == "preview":
                self._handle_worker_preview(payload)
            elif event_type == "awaiting_input":
                self._handle_worker_prompt(payload)
            elif event_type == "input_resumed":
                self._handle_worker_resumed()
            elif event_type == "result":
                self._handle_worker_result(payload)
            elif event_type == "cancelled":
                self._handle_worker_cancelled()
            elif event_type == "error":
                self._handle_worker_error(str(payload))
            elif event_type == "assistant_result":
                conversation_id, reply_text = payload
                self._handle_assistant_result(str(conversation_id), str(reply_text))
            elif event_type == "assistant_error":
                conversation_id, error_text, _traceback_text = payload
                self._handle_assistant_error(str(conversation_id), str(error_text))
            elif event_type == "finished":
                self.worker = None
                self.running_project_id = None
                self._update_composer_state()
            elif event_type == "assistant_finished":
                self.assistant_worker = None
                self._update_composer_state()

        self.after(150, self._poll_worker_events)

    def _handle_worker_preview(self, payload: Any) -> None:
        project_id = self.running_project_id
        if project_id is None or not isinstance(payload, dict):
            return

        title = str(payload.get("title", "")).strip()
        preview_text = str(payload.get("text", "")).strip()
        full_text = str(payload.get("full_text", "")).strip() or preview_text
        payload_kind = str(payload.get("kind", "preview")).strip().lower()
        if not title or not preview_text:
            return

        _, inline_text = self._choose_output_display_text(
            full_text=full_text,
            preview_text=preview_text,
            force_full=(payload_kind == "full_output"),
        )
        body = f"{title}\n\n{inline_text}"
        self._append_chat_message(project_id, "preview", body)
        if self.current_project_id == project_id:
            self._refresh_chat_view()
        self._refresh_project_list()
        self._save_current_project()

    def _handle_worker_prompt(self, payload: WorkerPrompt) -> None:
        project_id = self.running_project_id
        if project_id is None:
            return
        session = self.projects.get(project_id)
        if session is None:
            return

        session.execution_in_progress = True
        session.stage = "waiting_for_input"
        session.current_prompt = payload.prompt
        session.current_choices = list(payload.choices)
        session.touch()
        self.status_var.set(self._t("status.waiting_input"))
        self._append_chat_message(project_id, "assistant", payload.prompt)
        if self.current_project_id == project_id:
            self._refresh_chat_view()
        self._refresh_project_workspace()
        self._refresh_project_list()
        self._update_composer_state()
        self._save_current_project()

    def _handle_worker_resumed(self) -> None:
        project_id = self.running_project_id
        if project_id is None:
            return
        session = self.projects.get(project_id)
        if session is None:
            return
        session.execution_in_progress = True
        session.stage = "running"
        session.current_prompt = ""
        session.current_choices = []
        session.touch()
        self.status_var.set(self._t("status.running"))
        if self.current_project_id == project_id:
            self._refresh_chat_view()
        self._refresh_project_workspace()
        self._refresh_project_list()
        self._update_composer_state()
        self._save_current_project()

    def _handle_worker_result(self, result) -> None:
        project_id = self.running_project_id
        if project_id is None:
            return
        session = self.projects.get(project_id)
        if session is None:
            return

        session.execution_in_progress = False
        session.latest_result = result
        session.touch()
        self.last_output_dir = result.session_dir
        self.status_var.set(
            self._t("status.finished", success_count=result.success_count, failure_count=result.failure_count)
        )
        summary = self._t("info.output_saved_to", path=result.session_dir)
        self._append_chat_message(project_id, "result", summary, output_cards=result.output_cards)
        skill = self.skills_by_id.get(session.selected_skill_id)
        self._append_chat_message(
            project_id,
            "status",
            self._t("project.activity.run_finished", skill=skill.display_name if skill else "", path=result.session_dir),
        )
        session.reset_for_new_skill_run()
        if skill is not None:
            self._append_chat_message(
                project_id,
                "assistant",
                self._t("chat.next_run_prompt"),
            )
            session.current_prompt = self._t("chat.next_run_prompt")
        if self.current_project_id == project_id:
            self._refresh_chat_view()
        self._refresh_project_workspace()
        self._refresh_project_list()
        self._save_current_project()

        if result.failure_count == 0:
            messagebox.showinfo(self._t("dialog.run_complete"), self._t("info.output_saved_to", path=result.session_dir))
        else:
            messagebox.showwarning(
                self._t("dialog.run_finished_with_errors"),
                self._t("info.run_finished_with_errors", path=result.session_dir, count=result.failure_count),
            )

    def _handle_worker_cancelled(self) -> None:
        project_id = self.running_project_id
        if project_id is not None:
            session = self.projects.get(project_id)
            if session is not None:
                session.execution_in_progress = False
                session.stage = "idle"
                session.current_prompt = ""
                session.current_choices = []
                session.touch()
                self._append_chat_message(project_id, "status", self._t("project.activity.run_cancelled"))
                if self.current_project_id == project_id:
                    self._refresh_chat_view()
                self._refresh_project_workspace()
                self._refresh_project_list()
                self._save_current_project()
        self.status_var.set(self._t("status.cancelled"))

    def _handle_worker_error(self, error_message: str) -> None:
        project_id = self.running_project_id
        if project_id is not None:
            session = self.projects.get(project_id)
            if session is not None:
                session.execution_in_progress = False
                session.stage = "awaiting_input"
                session.current_prompt = self._t("chat.run_failed_retry")
                session.touch()
                self._append_chat_message(project_id, "error", error_message)
                self._append_chat_message(
                    project_id,
                    "assistant",
                    self._t("chat.run_failed_retry"),
                )
                self._append_chat_message(project_id, "error", self._t("project.activity.run_failed"))
                if self.current_project_id == project_id:
                    self._refresh_chat_view()
                self._refresh_project_workspace()
                self._refresh_project_list()
                self._save_current_project()
        self.status_var.set(self._t("status.failed"))
        messagebox.showerror(self._t("dialog.run_failed"), error_message)

    def _handle_assistant_result(self, conversation_id: str, reply_text: str) -> None:
        session = self.projects.get(conversation_id)
        if session is None:
            return
        session.assistant_reply_pending = False
        session.touch()
        self._append_chat_message(conversation_id, "assistant", reply_text)
        if self.current_project_id == conversation_id:
            self._refresh_chat_view()
        self._refresh_project_list()
        self._save_current_project()

    def _handle_assistant_error(self, conversation_id: str, error_text: str) -> None:
        session = self.projects.get(conversation_id)
        if session is None:
            return
        session.assistant_reply_pending = False
        session.touch()
        message = self._t("chat.helper_reply_failed", error=error_text)
        self._append_chat_message(conversation_id, "error", message)
        if self.current_project_id == conversation_id:
            self._refresh_chat_view()
        self._refresh_project_list()
        self._save_current_project()

    def _refresh_chat_view(self) -> None:
        if self._chat_refresh_in_progress:
            return
        self._chat_refresh_in_progress = True
        try:
            for child in self.chat_history.winfo_children():
                child.destroy()

            session = self._current_project()
            if session is None:
                self._render_chat_message(ChatMessage(role="status", text=self._t("project.activity.empty")))
                self._refresh_chat_scrollregion()
                return
            if not session.messages:
                self._render_chat_message(ChatMessage(role="status", text=self._t("project.activity.empty")))
                self._refresh_chat_scrollregion()
                self._scroll_chat_to_end()
                return
            for message in session.messages:
                self._render_chat_message(message)
            if session.execution_in_progress and session.stage != "waiting_for_input":
                self._render_inline_progress_card()
            elif session.assistant_reply_pending:
                self._render_inline_progress_card(label=self._t("chat.thinking"), description="")
            self._refresh_chat_scrollregion()
            self._scroll_chat_to_end()
        finally:
            self._chat_refresh_in_progress = False

    def _schedule_chat_layout_refresh(self, _event: Any = None) -> None:
        width = self.chat_history.winfo_width()
        if width > 1:
            self._chat_wrap_width = width

    def _refresh_chat_layout(self) -> None:
        self._chat_layout_refresh_after_id = None
        return

    def _chat_text_wraplength(self, role: str) -> int:
        available_width = self.chat_history.winfo_width() or self.run_tab.winfo_width() or 860
        ratio = 0.86
        if role == "user":
            ratio = 0.74
        elif role in {"result", "preview"}:
            ratio = 0.92
        elif role in {"status", "error"}:
            ratio = 0.80
        return max(240, int(available_width * ratio) - 44)

    def _chat_bubble_pad_x(self, role: str) -> tuple[int, int]:
        available_width = self.chat_history.winfo_width() or self.run_tab.winfo_width() or 860
        if role == "user":
            left_margin = max(44, min(140, int(available_width * 0.16)))
            return (left_margin, 0)
        if role in {"result", "preview"}:
            right_margin = max(32, min(90, int(available_width * 0.08)))
            return (0, right_margin)
        if role in {"status", "error"}:
            right_margin = max(40, min(110, int(available_width * 0.10)))
            return (0, right_margin)
        right_margin = max(44, min(120, int(available_width * 0.11)))
        return (0, right_margin)

    def _render_chat_message(self, message: ChatMessage) -> None:
        outer = ctk.CTkFrame(self.chat_history, fg_color="transparent")
        outer.pack(fill="x", padx=12, pady=8)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)
        self._bind_chat_scroll_widget(outer)

        role = message.role
        bubble_color = ("#f3f4f6", "#24262b")
        text_color = ("#111827", "#f3f4f6")
        role_label = self._t("chat.role.assistant")
        column = 0
        sticky = "w"
        pad_x = self._chat_bubble_pad_x(role)
        border_color = ("#d1d5db", "#3f4754")

        if role == "user":
            bubble_color = ("#dbeafe", "#1f4f86")
            text_color = ("#0f172a", "#eff6ff")
            role_label = self._t("chat.role.user")
            column = 1
            sticky = "e"
            pad_x = self._chat_bubble_pad_x(role)
            border_color = ("#93c5fd", "#2d6ab3")
        elif role == "status":
            bubble_color = ("#f3f4f6", "#2d323a")
            text_color = ("#374151", "#d1d5db")
            role_label = self._t("chat.role.status")
            pad_x = self._chat_bubble_pad_x(role)
            border_color = ("#d1d5db", "#4b5563")
        elif role == "error":
            bubble_color = ("#fee2e2", "#5f2020")
            text_color = ("#991b1b", "#fecaca")
            role_label = self._t("chat.role.error")
            pad_x = self._chat_bubble_pad_x(role)
            border_color = ("#fca5a5", "#7f1d1d")
        elif role == "result":
            bubble_color = ("#dcfce7", "#193b2b")
            text_color = ("#14532d", "#dcfce7")
            role_label = self._t("chat.role.result")
            pad_x = self._chat_bubble_pad_x(role)
            border_color = ("#86efac", "#2d6a4f")
        elif role == "preview":
            bubble_color = ("#dcfce7", "#193b2b")
            text_color = ("#14532d", "#dcfce7")
            role_label = self._t("chat.role.preview")
            pad_x = self._chat_bubble_pad_x(role)
            border_color = ("#86efac", "#2d6a4f")

        bubble = ctk.CTkFrame(
            outer,
            fg_color=bubble_color,
            corner_radius=16,
            border_width=1,
            border_color=border_color,
        )
        bubble.grid(row=0, column=column, sticky=sticky, padx=pad_x)
        bubble.grid_columnconfigure(0, weight=1)
        self._bind_chat_scroll_widget(bubble)

        body_row = 0
        if role != "user":
            role_widget = ctk.CTkLabel(
                bubble,
                text=role_label,
                anchor="w",
                text_color=("gray45", "#cbd5e1") if role not in {"error", "result", "preview"} else text_color,
                font=ctk.CTkFont(size=12, weight="bold"),
            )
            role_widget.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
            self._bind_chat_scroll_widget(role_widget)
            body_row = 1
        if role == "preview":
            self._render_preview_body(
                bubble,
                row=body_row,
                text=message.text,
                background=bubble_color,
                foreground=text_color,
            )
        else:
            body_widget = self._build_selectable_chat_text(
                bubble,
                message.text,
                role=role,
                background=bubble_color,
                foreground=text_color,
            )
            body_widget.grid(
                row=body_row,
                column=0,
                sticky="ew",
                padx=14,
                pady=((12, 10) if role == "user" else (0, 10)),
            )
            self._bind_chat_scroll_widget(body_widget)

        for index, card in enumerate(message.output_cards, start=body_row + 1):
            self._render_output_card(bubble, index, card)

    def _build_selectable_chat_text(
        self,
        parent: ctk.CTkFrame,
        text: str,
        *,
        role: str,
        background: str | tuple[str, str],
        foreground: str | tuple[str, str],
    ) -> tk.Text:
        bg_color = parent._apply_appearance_mode(background)
        fg_color = parent._apply_appearance_mode(foreground)
        max_wrap_chars = max(24, self._chat_text_wraplength(role) // 8)
        width_chars = self._chat_text_width_chars(text, max_wrap_chars)
        display_lines = self._estimate_chat_text_lines(text, width_chars)
        widget = tk.Text(
            parent,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            spacing1=0,
            spacing2=0,
            spacing3=0,
            bg=bg_color,
            fg=fg_color,
            insertbackground=fg_color,
            selectbackground="#2563eb",
            selectforeground="#f8fafc",
            font=("Segoe UI", 12),
            cursor="xterm",
            width=width_chars,
            height=display_lines,
        )
        widget.insert("1.0", text)
        widget.configure(state="disabled")
        self._bind_chat_scroll_widget(widget)
        return widget

    def _render_preview_body(
        self,
        parent: ctk.CTkFrame,
        *,
        row: int,
        text: str,
        background: str | tuple[str, str],
        foreground: str | tuple[str, str],
    ) -> None:
        title, content = self._split_preview_text(text)
        if title:
            title_widget = ctk.CTkLabel(
                parent,
                text=title,
                anchor="w",
                justify="left",
                text_color=foreground,
                font=ctk.CTkFont(size=14, weight="bold"),
            )
            title_widget.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 8))
            self._bind_chat_scroll_widget(title_widget)
            row += 1

        preview_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#111827"),
            border_width=1,
            border_color=("#bbf7d0", "#2d6a4f"),
        )
        preview_frame.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 12))
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)

        bg_color = preview_frame._apply_appearance_mode(("white", "#111827"))
        fg_color = preview_frame._apply_appearance_mode(foreground)
        max_wrap_chars = max(32, self._chat_text_wraplength("preview") // 8)
        width_chars = max_wrap_chars
        display_lines = self._estimate_chat_text_lines(content, width_chars)
        visible_lines = min(max(6, min(display_lines, 16)), 16)

        preview_text = tk.Text(
            preview_frame,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=10,
            spacing1=0,
            spacing2=0,
            spacing3=0,
            bg=bg_color,
            fg=fg_color,
            insertbackground=fg_color,
            selectbackground="#2563eb",
            selectforeground="#f8fafc",
            font=("Segoe UI", 12),
            cursor="xterm",
            width=width_chars,
            height=visible_lines,
        )
        preview_scrollbar = ctk.CTkScrollbar(preview_frame, orientation="vertical", command=preview_text.yview)
        preview_text.configure(yscrollcommand=preview_scrollbar.set)
        preview_text.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        preview_scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 8), pady=8)
        preview_text.insert("1.0", content)
        preview_text.configure(state="disabled")

    def _split_preview_text(self, text: str) -> tuple[str, str]:
        normalized = text.strip()
        if not normalized:
            return "", ""
        if "\n\n" in normalized:
            title, content = normalized.split("\n\n", 1)
            return title.strip(), content.strip()
        lines = normalized.splitlines()
        if len(lines) > 1:
            return lines[0].strip(), "\n".join(lines[1:]).strip()
        return "", normalized

    def _should_show_full_output(self, text: str) -> bool:
        normalized = text.strip()
        if not normalized:
            return False
        line_count = len(normalized.splitlines())
        return len(normalized) <= self.OUTPUT_FULL_CHAR_THRESHOLD and line_count <= self.OUTPUT_FULL_LINE_THRESHOLD

    def _build_output_preview_text(self, full_text: str, preview_text: str = "") -> str:
        candidate = preview_text.strip() or full_text.strip()
        if not candidate:
            return ""
        lines = candidate.splitlines()
        truncated_by_lines = len(lines) > self.OUTPUT_PREVIEW_LINE_LIMIT
        if truncated_by_lines:
            lines = lines[: self.OUTPUT_PREVIEW_LINE_LIMIT]
        rendered = "\n".join(lines).strip()
        if len(rendered) > self.OUTPUT_PREVIEW_CHAR_LIMIT:
            rendered = rendered[: self.OUTPUT_PREVIEW_CHAR_LIMIT].rstrip()
            truncated_by_lines = True
        if truncated_by_lines or (full_text.strip() and rendered != full_text.strip()):
            return rendered.rstrip() + "..."
        return rendered

    def _choose_output_display_text(
        self,
        *,
        full_text: str,
        preview_text: str = "",
        force_full: bool = False,
    ) -> tuple[str, str]:
        normalized_full = full_text.strip()
        normalized_preview = preview_text.strip()
        if force_full and normalized_full:
            return "full", normalized_full

        mode = self._output_display_mode_code()
        if mode == "full":
            return "full", normalized_full or normalized_preview
        if mode == "preview":
            return "preview", self._build_output_preview_text(normalized_full, normalized_preview)
        if normalized_full and self._should_show_full_output(normalized_full):
            return "full", normalized_full
        return "preview", self._build_output_preview_text(normalized_full, normalized_preview)

    def _chat_text_width_chars(self, text: str, max_wrap_chars: int) -> int:
        lines = text.splitlines() or [text]
        longest_line = max((len(line) for line in lines), default=1)
        return max(4, min(max_wrap_chars, longest_line if longest_line > 0 else 1))

    def _estimate_chat_text_lines(self, text: str, wrap_chars: int) -> int:
        paragraphs = text.splitlines() or [text]
        line_count = 0
        wrapped_line_detected = False
        for paragraph in paragraphs:
            if not paragraph:
                line_count += 1
                continue
            wrapped = textwrap.wrap(
                paragraph,
                width=max(1, wrap_chars),
                replace_whitespace=False,
                drop_whitespace=False,
                break_long_words=True,
                break_on_hyphens=False,
            )
            used_lines = max(1, len(wrapped))
            if used_lines > 1:
                wrapped_line_detected = True
            line_count += used_lines
        if wrapped_line_detected or "\n" in text:
            line_count += 1
        return max(1, line_count)

    def _render_output_card(self, parent: ctk.CTkFrame, row: int, card: GuiOutputCard) -> None:
        card_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#111827"),
            border_width=1,
            border_color=("#bbf7d0", "#2f855a"),
        )
        card_frame.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 12))
        card_frame.grid_columnconfigure(0, weight=1)
        self._bind_chat_scroll_widget(card_frame)

        title_widget = ctk.CTkLabel(
            card_frame,
            text=card.title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        )
        title_widget.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self._bind_chat_scroll_widget(title_widget)
        path_widget = ctk.CTkLabel(
            card_frame,
            text=str(card.path),
            text_color="gray60",
            justify="left",
            anchor="w",
            wraplength=self._chat_text_wraplength("result") - 32,
        )
        path_widget.grid(row=1, column=0, sticky="ew", padx=12)
        self._bind_chat_scroll_widget(path_widget)

        full_text = self._load_output_text(card.path)
        display_mode, inline_text = self._choose_output_display_text(
            full_text=full_text,
            preview_text=card.preview_text,
        )
        next_row = 2
        if inline_text:
            self._render_output_content_block(
                card_frame,
                row=next_row,
                text=inline_text,
                mode=display_mode,
            )
            next_row += 2

        actions = ctk.CTkFrame(card_frame, fg_color="transparent")
        actions.grid(row=next_row, column=0, sticky="w", padx=12, pady=(12, 12))
        self._bind_chat_scroll_widget(actions)
        ctk.CTkButton(actions, text=self._t("settings.open"), command=lambda p=card.path: self._open_path(p), width=80).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            actions,
            text=self._t("result.open_folder"),
            command=lambda p=card.output_dir: self._open_path(p),
            width=110,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text=self._t("result.view_full"),
            command=lambda c=card: self._preview_output_card(c),
            width=90,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text=self._t("common.copy"),
            command=lambda c=card: self._copy_output_card(c),
            width=80,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text=self._t("dialog.save_as"),
            command=lambda c=card: self._save_output_card_as(c),
            width=90,
        ).pack(side="left")

    def _render_output_content_block(
        self,
        parent: ctk.CTkFrame,
        *,
        row: int,
        text: str,
        mode: str,
    ) -> None:
        label_key = "result.inline_full" if mode == "full" else "result.inline_preview"
        ctk.CTkLabel(
            parent,
            text=self._t(label_key),
            font=ctk.CTkFont(size=12, weight="bold"),
            anchor="w",
            text_color=("gray45", "#cbd5e1"),
        ).grid(row=row, column=0, sticky="w", padx=12, pady=(10, 4))

        content_frame = ctk.CTkFrame(
            parent,
            fg_color=("#f8fafc", "#0f172a"),
            border_width=1,
            border_color=("#bbf7d0", "#2d6a4f"),
        )
        content_frame.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 0))
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)
        self._bind_chat_scroll_widget(content_frame)

        bg_color = content_frame._apply_appearance_mode(("#f8fafc", "#0f172a"))
        fg_color = content_frame._apply_appearance_mode(("#14532d", "#dcfce7"))
        max_wrap_chars = max(32, self._chat_text_wraplength("result") // 8)
        visible_lines = min(max(4, self._estimate_chat_text_lines(text, max_wrap_chars)), 16)
        textbox = tk.Text(
            content_frame,
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=10,
            pady=10,
            spacing1=0,
            spacing2=0,
            spacing3=0,
            bg=bg_color,
            fg=fg_color,
            insertbackground=fg_color,
            selectbackground="#2563eb",
            selectforeground="#f8fafc",
            font=("Segoe UI", 12),
            cursor="xterm",
            width=max_wrap_chars,
            height=visible_lines,
        )
        scrollbar = ctk.CTkScrollbar(content_frame, orientation="vertical", command=textbox.yview)
        textbox.configure(yscrollcommand=scrollbar.set)
        textbox.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(6, 8), pady=8)
        textbox.insert("1.0", text)
        textbox.configure(state="disabled")
        self._bind_chat_scroll_widget(textbox)

    def _render_inline_progress_card(
        self,
        *,
        label: str = "",
        description: str = "",
    ) -> None:
        if not label:
            label = self._t("chat.running")
        if not description:
            description = self._t("chat.running_description")
        outer = ctk.CTkFrame(self.chat_history, fg_color="transparent")
        outer.pack(fill="x", padx=12, pady=8)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        bubble = ctk.CTkFrame(
            outer,
            fg_color=("#f3f4f6", "#2d323a"),
            corner_radius=16,
            border_width=1,
            border_color=("#d1d5db", "#4b5563"),
        )
        bubble.grid(row=0, column=0, sticky="w", padx=(0, 140))
        bubble.grid_columnconfigure(0, weight=1)
        self._bind_chat_scroll_widget(outer)
        self._bind_chat_scroll_widget(bubble)

        label_widget = ctk.CTkLabel(
            bubble,
            text=label,
            anchor="w",
            text_color=("gray45", "#cbd5e1"),
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        label_widget.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        self._bind_chat_scroll_widget(label_widget)
        row = 1
        if description.strip():
            description_widget = ctk.CTkLabel(
                bubble,
                text=description,
                justify="left",
                anchor="w",
                wraplength=self._chat_text_wraplength("status"),
                text_color=("#374151", "#d1d5db"),
            )
            description_widget.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
            self._bind_chat_scroll_widget(description_widget)
            row = 2

        progress = ctk.CTkProgressBar(bubble, mode="indeterminate")
        progress.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 12))
        progress.start()
        self._bind_chat_scroll_widget(progress)

    def _append_chat_message(
        self,
        conversation_id: str,
        role: str,
        text: str,
        *,
        output_cards: list[GuiOutputCard] | None = None,
    ) -> None:
        session = self.projects.get(conversation_id)
        if session is None:
            return
        session.messages.append(ChatMessage(role=role, text=text, output_cards=output_cards or []))
        session.touch()
        self.project_store.save(session)

    def _update_composer_state(self) -> None:
        session = self._current_project()
        waiting_for_worker_input = (
            session is not None
            and session.execution_in_progress
            and session.stage == "waiting_for_input"
        )
        enabled = (
            self.current_project_id is not None
            and not ((self.worker is not None and self.worker.is_alive()) and not waiting_for_worker_input)
            and not (self.assistant_worker is not None and self.assistant_worker.is_alive())
        )
        state = "normal" if enabled else "disabled"
        self.chat_input.configure(state=state)
        self.send_button.configure(state=state)
        self.browse_file_button.configure(state=state)
        self.browse_folder_button.configure(state=state)
        self.open_output_button.configure(state=state)
        self._update_run_button_state()

    def _submit_worker_reply(self, session: ProjectState, text: str) -> None:
        worker = self.worker
        if worker is None or not worker.is_alive():
            raise ValueError(self._t("workflow.error.not_ready"))
        session.stage = "running"
        session.current_prompt = ""
        session.current_choices = []
        session.touch()
        self.status_var.set(self._t("status.running"))
        worker.submit_input(text)
        self._update_composer_state()
        self._save_current_project()

    def _refresh_run_context(self) -> None:
        project_name = self.project_var.get().strip() or self._t("common.no_project")
        output_root = self._effective_output_root()
        self.sidebar_project_var.set(self._t("workflow.intro.project", project=project_name))
        self.sidebar_output_var.set(
            self._t("workflow.intro.output", path=self._shorten_text(str(output_root), limit=96))
        )

    def _save_settings(self) -> None:
        provider = self.provider_var.get().strip().lower()
        model = self.model_var.get().strip()
        api_key = self.api_key_var.get().strip()
        base_url = self.base_url_var.get().strip()
        language = self._language_code()
        auto_accept_review_steps = self.auto_accept_review_steps_var.get()
        show_internal_project_files = self.show_internal_project_files_var.get()
        output_display_mode = self._output_display_mode_code()
        default_output_path = self.output_path_var.get().strip()
        workspace_root = self.workspace_root_var.get().strip()

        if not provider:
            messagebox.showwarning(self._t("dialog.settings"), self._t("warning.choose_provider"))
            return
        if not model:
            messagebox.showwarning(self._t("dialog.settings"), self._t("warning.enter_model"))
            return
        if not api_key:
            messagebox.showwarning(self._t("dialog.settings"), self._t("warning.enter_api_key"))
            return
        if not default_output_path:
            messagebox.showwarning(self._t("dialog.settings"), self._t("warning.enter_output_path"))
            return
        if not workspace_root:
            messagebox.showwarning(self._t("dialog.settings"), self._t("warning.choose_workspace_root"))
            return

        self.workspace_manager.set_workspace_root(workspace_root)
        selected_skill = self._selected_skill()
        settings = AppSettings(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            language=language,
            auto_accept_review_steps=auto_accept_review_steps,
            show_internal_project_files=show_internal_project_files,
            output_display_mode=output_display_mode,
            default_output_path=default_output_path,
            default_skill_id=selected_skill.skill_id if selected_skill else "",
            workspace_root=workspace_root,
            last_project_name=self.project_var.get().strip(),
        )
        self.settings_manager.save(settings)
        self.settings = settings
        self._apply_language(language)
        self._rebuild_ui()
        self._refresh_projects(select_name=self.project_var.get().strip())
        self._refresh_run_context()
        messagebox.showinfo(self._t("dialog.settings"), self._t("info.settings_saved"))

    def _delete_selected_project_tree_item(self) -> None:
        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.project_tree_delete"), self._t("project.error.no_project"))
            return
        target = self.project_tree_pane.selected_path() if hasattr(self, "project_tree_pane") else None
        if target is None:
            messagebox.showwarning(self._t("dialog.project_tree_delete"), self._t("warning.project_tree_choose_item"))
            return
        if target.resolve() == project.project_root().resolve():
            messagebox.showwarning(self._t("dialog.project_tree_delete"), self._t("warning.project_tree_delete_protected"))
            return
        if hasattr(self, "project_tree_pane") and self.project_tree_pane.is_protected_path(target):
            messagebox.showwarning(self._t("dialog.project_tree_delete"), self._t("warning.project_tree_delete_protected"))
            return
        if not target.exists():
            messagebox.showwarning(self._t("dialog.project_tree_delete"), self._t("warning.path_missing", path=target))
            self._refresh_project_tree()
            return

        confirm_key = "project.tree.delete_confirm_folder" if target.is_dir() else "project.tree.delete_confirm_file"
        if not messagebox.askyesno(
            self._t("dialog.project_tree_delete"),
            self._t(confirm_key, name=target.name),
        ):
            return

        try:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        except OSError as exc:
            messagebox.showwarning(self._t("dialog.project_tree_delete"), self._t("warning.project_tree_delete_failed", error=exc))
            return

        self.project_store.refresh_sources(project)
        self.status_var.set(self._t("project.tree.delete_success", name=target.name))
        self._append_chat_message(project.id, "status", self._t("project.tree.delete_success", name=target.name))
        self._refresh_project_workspace()
        self._refresh_project_list()

    def _persist_gui_state(self) -> None:
        selected_skill = self._selected_skill()
        self.settings_manager.save_gui_state(
            workspace_root=self.workspace_root_var.get().strip(),
            last_project_name=self.project_var.get().strip(),
            default_skill_id=selected_skill.skill_id if selected_skill else "",
            default_output_path=self.output_path_var.get().strip(),
        )

    def _refresh_projects(self, _value: str | None = None, *, select_name: str = "") -> None:
        workspace_root = self.workspace_root_var.get().strip()
        if not workspace_root:
            self.project_combo.configure(values=[""])
            self.project_var.set("")
            self.projects.clear()
            self.current_project_id = None
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            self._refresh_project_list()
            self._refresh_project_workspace()
            self._refresh_run_context()
            return

        self.workspace_manager.set_workspace_root(workspace_root)
        self.workspace_manager.ensure_workspace_root()
        self.project_store = ProjectStore(self.workspace_manager)
        loaded_projects = self.project_store.list_projects()
        self.projects = {project.id: project for project in loaded_projects}
        project_names = [project.name for project in loaded_projects]
        self.project_combo.configure(values=project_names or [""])
        self._refresh_project_list()

        target_name = select_name or self.project_var.get().strip()
        if target_name and target_name in project_names:
            self._apply_project_selection(target_name)
        elif project_names:
            self._apply_project_selection(project_names[0])
        else:
            self.project_var.set("")
            self.selected_project_name = ""
            self.current_project_id = None
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            self._persist_gui_state()
            self._refresh_project_workspace()
            self._refresh_run_context()

    def _on_project_changed(self, project_name: str) -> None:
        self._apply_project_selection(project_name)

    def _apply_project_selection(self, project_name: str, *, update_conversation: bool = True) -> None:
        if not project_name:
            self.selected_project_name = ""
            self.current_project_id = None
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            self._persist_gui_state()
            self._refresh_project_workspace()
            self._refresh_run_context()
            return

        target = next((item for item in self.projects.values() if item.name == project_name), None)
        if target is None:
            self.selected_project_name = ""
            self.current_project_id = None
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            self._refresh_project_workspace()
            return

        self._select_project(target.id)

    def _create_project(self) -> None:
        dialog = ProjectCreationDialog(
            self,
            title=self._t("dialog.new_project"),
            labels={
                "name": self._t("project.creation.name"),
                "description": self._t("project.creation.description"),
                "source": self._t("project.creation.source"),
                "browse_file": self._t("project.sources.add_file"),
                "browse_folder": self._t("project.sources.add_folder"),
                "create": self._t("project.creation.create"),
                "cancel": self._t("project.creation.cancel"),
                "filetype_text": self._t("filedialog.filetype_text"),
                "filetype_all": self._t("filedialog.filetype_all"),
            },
            initial_dir=self._preferred_input_directory(),
        )
        result = dialog.show()
        if result is None:
            return
        project_name = result.name.strip()
        if not project_name:
            messagebox.showwarning(self._t("dialog.new_project"), self._t("warning.project_name_empty"))
            return
        try:
            selected_skill = self._selected_skill()
            project = self.project_store.create_project(
                name=project_name,
                description=result.description,
                source_path=result.source_path,
                selected_skill_id=selected_skill.skill_id if selected_skill else "",
                selected_skill_name=selected_skill.display_name if selected_skill else "",
            )
        except ValueError as exc:
            messagebox.showwarning(self._t("dialog.new_project"), str(exc))
            return
        self.projects[project.id] = project
        self._refresh_projects(select_name=project.name)
        messagebox.showinfo(self._t("dialog.new_project"), self._t("info.new_project_created", path=project.project_root()))

    def _add_project_source_file(self) -> None:
        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.no_project"))
            return
        selected = filedialog.askopenfilename(
            title=self._t("project.sources.add_file"),
            initialdir=self._preferred_input_directory(),
            filetypes=[
                (self._t("filedialog.filetype_text"), "*.txt"),
                (self._t("filedialog.filetype_all"), "*.*"),
            ],
        )
        if not selected:
            return
        self._import_paths_into_project([Path(selected)])

    def _add_project_source_folder(self) -> None:
        project = self._current_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.run"), self._t("project.error.no_project"))
            return
        selected = filedialog.askdirectory(
            title=self._t("project.sources.add_folder"),
            initialdir=self._preferred_input_directory(),
        )
        if not selected:
            return
        self._import_paths_into_project([Path(selected)])

    def _import_paths_into_project(self, raw_paths: list[Path]) -> list[Path]:
        project = self._current_project()
        if project is None:
            raise ValueError(self._t("project.error.no_project"))

        imported: list[Path] = []
        for raw_path in raw_paths:
            candidate = raw_path.expanduser()
            if not candidate.exists():
                raise ValueError(self._t("project.error.drop_missing"))
            source = self.project_store.attach_source(project, candidate)
            imported.append(Path(source.path))

        self._refresh_project_workspace()
        self._refresh_project_list()
        self._save_current_project()
        return imported

    def _toggle_api_key_visibility(self) -> None:
        self.api_key_entry.configure(show="" if self.show_api_key_var.get() else "*")

    def _refresh_api_key_placeholder(self) -> None:
        self.api_key_entry.configure(placeholder_text=f"{self.provider_var.get().upper()} {self._t('settings.api_key')}")

    def _reload_bible_choices(self) -> None:
        labels: list[str] = []
        self.bible_path_by_label.clear()
        for root in self._rewriting_search_roots():
            for label, path in self.backend.list_rewriting_bibles(root):
                display = f"{label} [{Path(path).parent.name}]"
                if display in self.bible_path_by_label:
                    continue
                labels.append(display)
                self.bible_path_by_label[display] = path

    def _rewriting_search_roots(self) -> list[Path]:
        roots: list[Path] = []
        effective_output = self._effective_output_root()
        roots.append(effective_output)
        fallback = self.output_path_var.get().strip()
        if fallback:
            fallback_path = Path(fallback).expanduser().resolve()
            if fallback_path not in roots:
                roots.append(fallback_path)
        repo_outputs = (self.repo_root / "outputs").resolve()
        if repo_outputs not in roots:
            roots.append(repo_outputs)
        return roots

    def _browse_workspace(self) -> None:
        selected = filedialog.askdirectory(title=self._t("filedialog.workspace_root"))
        if selected:
            self.workspace_root_var.set(selected)
            self._refresh_projects(select_name=self.project_var.get().strip())

    def _browse_input_file(self) -> None:
        selected = filedialog.askopenfilename(
            title=self._t("filedialog.input_file"),
            initialdir=self._preferred_input_directory(),
            filetypes=[
                (self._t("filedialog.filetype_text"), "*.txt"),
                (self._t("filedialog.filetype_all"), "*.*"),
            ],
        )
        if selected:
            self._submit_chat_input(selected)

    def _browse_input_folder(self) -> None:
        selected = filedialog.askdirectory(
            title=self._t("filedialog.input_folder"),
            initialdir=self._preferred_input_directory(),
        )
        if selected:
            self._submit_chat_input(selected)

    def _browse_output_folder(self) -> None:
        selected = filedialog.askdirectory(title=self._t("filedialog.output_root"))
        if selected:
            self.output_path_var.set(selected)
            self._persist_gui_state()
            self._refresh_run_context()

    def _open_project_inputs_folder(self) -> None:
        project = self._active_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.project_inputs"), self._t("warning.choose_project_first"))
            return
        project.inputs_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(project.inputs_dir)

    def _open_project_folder(self) -> None:
        project = self._active_project()
        if project is None:
            messagebox.showwarning(self._t("dialog.open_project_folder"), self._t("warning.choose_project_first"))
            return
        project.root.mkdir(parents=True, exist_ok=True)
        self._open_path(project.root)

    def _open_output_folder(self) -> None:
        target = self.last_output_dir or self._effective_output_root()
        target_path = Path(target).expanduser().resolve()
        if not target_path.exists():
            messagebox.showwarning(self._t("dialog.open_output_folder"), self._t("warning.path_missing", path=target_path))
            return
        self._open_path(target_path)

    def _open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showwarning(self._t("dialog.open_path"), self._t("warning.path_missing", path=path))
            return
        opener = getattr(os, "startfile", None)
        if callable(opener):
            opener(path)  # type: ignore[misc]
        else:
            messagebox.showinfo(self._t("dialog.open_path"), self._t("info.open_path_fallback", path=path))

    def _append_log(self, text: str) -> None:
        self.logs_textbox.configure(state="normal")
        self.logs_textbox.insert("end", text)
        self.logs_textbox.see("end")
        self.logs_textbox.configure(state="disabled")

    def _clear_logs(self) -> None:
        self.logs_textbox.configure(state="normal")
        self.logs_textbox.delete("1.0", "end")
        self.logs_textbox.configure(state="disabled")

    def _selected_skill(self) -> GuiSkillOption | None:
        if self.selected_skill_id is None:
            return None
        return self.skills_by_id.get(self.selected_skill_id)

    def _active_project(self):
        project_name = self.project_var.get().strip()
        if not project_name:
            return None
        return self.workspace_manager.get_project(project_name)

    def _effective_output_root(self) -> Path:
        project = self._active_project()
        if project is not None:
            project.outputs_dir.mkdir(parents=True, exist_ok=True)
            return project.outputs_dir.resolve()
        fallback = self.output_path_var.get().strip() or self.settings.default_output_path
        return Path(fallback).expanduser().resolve()

    def _preferred_input_directory(self) -> str:
        project = self._active_project()
        if project is not None:
            project.inputs_dir.mkdir(parents=True, exist_ok=True)
            return str(project.inputs_dir)
        workspace_root = self.workspace_root_var.get().strip()
        if workspace_root:
            return workspace_root
        return str(self.repo_root)

    def _resolve_bible_selection(self, text: str) -> str:
        raw_value = text.strip()
        if raw_value.isdigit():
            selected = int(raw_value)
            options = list(self.bible_path_by_label.values())
            if 1 <= selected <= len(options):
                return options[selected - 1]
            raise ValueError(self._t("workflow.error.bible_number"))
        if raw_value in self.bible_path_by_label:
            return self.bible_path_by_label[raw_value]
        return self._normalize_existing_path(raw_value)

    def _resolve_optional_existing_path(self, text: str) -> str:
        raw_value = text.strip()
        if raw_value.lower() in {"skip", "none", ""}:
            return ""
        return self._normalize_existing_path(raw_value)

    def _normalize_existing_path(self, raw_path: str) -> str:
        candidate = Path(raw_path.strip().strip('"')).expanduser()
        if not candidate.exists():
            raise ValueError(self._t("workflow.error.path_not_found"))
        return str(candidate.resolve())

    def _capture_existing_path(self, raw_path: str, error_message: str) -> None:
        try:
            self._normalize_existing_path(raw_path)
        except ValueError as exc:
            raise ValueError(error_message) from exc

    def _copy_output_card(self, card: GuiOutputCard) -> None:
        payload = self._load_output_text(card.path)
        if not payload:
            payload = str(card.path)
        self.clipboard_clear()
        self.clipboard_append(payload)
        self.status_var.set(self._t("status.copied"))

    def _save_output_card_as(self, card: GuiOutputCard) -> None:
        if not card.path.exists():
            messagebox.showwarning(self._t("dialog.save_as"), self._t("warning.output_missing", path=card.path))
            return
        selected = filedialog.asksaveasfilename(
            title=self._t("filedialog.save_output_as"),
            initialfile=card.path.name,
        )
        if not selected:
            return
        shutil.copy2(card.path, selected)
        self.status_var.set(self._t("status.saved_copy", path=selected))

    def _preview_output_card(self, card: GuiOutputCard) -> None:
        preview_text = self._load_output_text(card.path)
        if not preview_text:
            messagebox.showinfo(self._t("dialog.preview"), self._t("warning.preview_unavailable", path=card.path))
            return
        preview_window = ctk.CTkToplevel(self)
        preview_window.title(card.title)
        preview_window.geometry("760x520")
        preview_window.grid_columnconfigure(0, weight=1)
        preview_window.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(
            preview_window,
            fg_color=("white", "#111827"),
            border_width=1,
            border_color=("#bbf7d0", "#2d6a4f"),
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            frame,
            text=card.title,
            anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))

        textbox = ctk.CTkTextbox(frame, wrap="word")
        textbox.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        textbox.insert("1.0", preview_text)
        textbox.configure(state="disabled")

    def _load_output_text(self, path: Path) -> str:
        if path.suffix.lower() not in {".txt", ".md", ".json", ".csv", ".yaml", ".yml"}:
            return ""
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                return path.read_text(encoding="utf-8-sig")
            except OSError:
                return ""
        except OSError:
            return ""

    def _open_help_window(self) -> None:
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.focus()
            self.help_window.lift()
            return

        readme_path = self._resolve_help_readme_path()
        if readme_path is None:
            messagebox.showwarning(self._t("dialog.help"), self._t("warning.help_missing"))
            return

        try:
            readme_text = readme_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                readme_text = readme_path.read_text(encoding="utf-8-sig")
            except OSError as exc:
                messagebox.showwarning(self._t("dialog.help"), self._t("warning.help_open_failed", error=exc))
                return
        except OSError as exc:
            messagebox.showwarning(self._t("dialog.help"), self._t("warning.help_open_failed", error=exc))
            return

        self.help_window = ctk.CTkToplevel(self)
        self.help_window.title(self._t("dialog.help"))
        self.help_window.geometry("980x760")
        self.help_window.minsize(760, 520)
        self.help_window.grid_columnconfigure(0, weight=1)
        self.help_window.grid_rowconfigure(0, weight=1)
        self.help_window.protocol("WM_DELETE_WINDOW", self._close_help_window)

        textbox = ctk.CTkTextbox(self.help_window, wrap="word")
        textbox.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        textbox.insert("1.0", readme_text)
        textbox.configure(state="disabled")
        textbox.see("1.0")

    def _close_help_window(self) -> None:
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.destroy()
        self.help_window = None

    def _resolve_help_readme_path(self) -> Path | None:
        candidates: list[Path] = []
        for root in (get_bundle_root(self.repo_root), get_app_root(self.repo_root), self.repo_root):
            candidate = root / "README.md"
            if candidate not in candidates:
                candidates.append(candidate)
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _build_workflow_summary(self, skill: GuiSkillOption) -> str:
        parts: list[str] = []
        if skill.startup_mode == "explicit_step_selection":
            parts.append(self._t("workflow.summary.explicit_step"))
        elif skill.allow_auto_route:
            parts.append(self._t("workflow.summary.auto_route"))
        if skill.supports_text_input:
            parts.append(self._t("workflow.summary.text_input"))
        parts.append(self._t("workflow.summary.use_chat"))
        return self._shorten_text(" ".join(parts), limit=260)

    def _skill_workflow_hint(self, skill: GuiSkillOption) -> str:
        if skill.workflow_hint.strip():
            return self._shorten_text(skill.workflow_hint.strip(), limit=260)
        return self._build_workflow_summary(skill)

    def _build_input_expectation(self, skill: GuiSkillOption) -> str:
        input_parts: list[str] = []
        if skill.supports_file_input:
            input_parts.append(self._t("workflow.input.file"))
        if skill.supports_folder_input:
            input_parts.append(self._t("workflow.input.folder"))
        if skill.supports_text_input:
            input_parts.append(self._t("workflow.input.brief_text"))

        if input_parts:
            joined = ", ".join(input_parts)
        else:
            joined = self._t("workflow.input.generic")

        extensions = ", ".join(skill.input_extensions[:4]) if skill.input_extensions else self._t("workflow.input.supported_files")
        return self._shorten_text(self._t("workflow.input.expectation", items=joined, extensions=extensions), limit=220)

    def _skill_input_hint(self, skill: GuiSkillOption) -> str:
        if skill.input_hint.strip():
            return self._shorten_text(skill.input_hint.strip(), limit=220)
        return self._build_input_expectation(skill)

    def _build_output_expectation(self, skill: GuiSkillOption) -> str:
        output_hints = {
            "novel_adaptation_plan": self._t("workflow.output.novel_adaptation_plan"),
            "novel_to_drama_script": self._t("workflow.output.novel_to_drama_script"),
            "rewriting": self._t("workflow.output.rewriting"),
            "story_creation": self._t("workflow.output.story_creation"),
            "large_novel_processor": self._t("workflow.output.large_novel_processor"),
            "recap_analysis": self._t("workflow.output.recap_analysis"),
            "recap_production": self._t("workflow.output.recap_production"),
            "novel2script": self._t("workflow.output.novel2script"),
        }
        return self._shorten_text(
            output_hints.get(
                skill.skill_id,
                self._t("workflow.output.default"),
            ),
            limit=220,
        )

    def _skill_output_hint(self, skill: GuiSkillOption) -> str:
        if skill.output_hint.strip():
            return self._shorten_text(skill.output_hint.strip(), limit=220)
        return self._build_output_expectation(skill)

    def _skill_starter_prompt(self, skill: GuiSkillOption) -> str:
        if skill.starter_prompt.strip():
            return skill.starter_prompt.strip()
        if skill.supports_text_input:
            return self._t("workflow.prompt.primary_input.with_text")
        return self._t("workflow.prompt.primary_input.path_only")

    def _build_initial_conversation_message(self, skill: GuiSkillOption, project_name: str) -> str:
        output_root = self._effective_output_root()
        lines = [
            skill.display_name,
            "",
            skill.description.strip() or self._t("workflow.intro.ready"),
            self._skill_workflow_hint(skill),
            self._skill_input_hint(skill),
            self._skill_output_hint(skill),
            self._t("workflow.intro.project", project=project_name or self._t("common.no_project")),
            self._t("workflow.intro.output", path=output_root),
        ]
        return "\n".join(line for line in lines if line is not None).strip()

    def _build_workflowSummary_for_intro(self, skill: GuiSkillOption) -> str:
        startup_note = ""
        if skill.startup_mode == "explicit_step_selection":
            startup_note = self._t("workflow.summary.explicit_step")
        elif skill.allow_auto_route:
            startup_note = self._t("workflow.summary.auto_route")
        if skill.supports_text_input:
            extra = self._t("workflow.summary.text_input")
            return " ".join(part for part in (startup_note, extra) if part).strip()
        return startup_note.strip()

    def _shorten_text(self, text: str, *, limit: int = 90) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit].rstrip() + "..."

    def _clear_chat_input(self) -> None:
        self.chat_input.delete("1.0", "end")

    def _bind_chat_scroll_widget(self, widget: object | None) -> None:
        if widget is None:
            return
        binder = getattr(widget, "bind", None)
        if not callable(binder):
            return
        try:
            binder("<MouseWheel>", self._on_chat_mousewheel, add="+")
            binder("<Button-4>", self._on_chat_mousewheel_linux, add="+")
            binder("<Button-5>", self._on_chat_mousewheel_linux, add="+")
        except Exception:
            return

    def _on_chat_mousewheel(self, event: Any) -> str:
        canvas = getattr(self.chat_history, "_parent_canvas", None)
        if canvas is None:
            return "break"
        delta = getattr(event, "delta", 0)
        if delta == 0:
            return "break"
        direction = -1 if delta > 0 else 1
        notches = max(1, int(round(abs(delta) / 120)))
        scroll_lines = self._windows_mousewheel_lines()
        if scroll_lines == -1:
            canvas.yview_scroll(direction * notches, "pages")
        else:
            canvas.yview_scroll(
                direction * notches * max(1, scroll_lines) * self._chat_scroll_units_per_line(),
                "units",
            )
        return "break"

    def _on_chat_mousewheel_linux(self, event: Any) -> str:
        canvas = getattr(self.chat_history, "_parent_canvas", None)
        if canvas is None:
            return "break"
        num = getattr(event, "num", 0)
        if num == 4:
            canvas.yview_scroll(-3 * self._chat_scroll_units_per_line(), "units")
        elif num == 5:
            canvas.yview_scroll(3 * self._chat_scroll_units_per_line(), "units")
        return "break"

    def _windows_mousewheel_lines(self) -> int:
        if os.name != "nt":
            return 3
        cached_lines = getattr(self, "_windows_scroll_lines", None)
        if cached_lines is not None:
            return cached_lines
        try:
            SPI_GETWHEELSCROLLLINES = 0x0068
            WHEEL_PAGESCROLL = 0xFFFFFFFF
            lines = ctypes.c_uint()
            ok = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
                SPI_GETWHEELSCROLLLINES,
                0,
                ctypes.byref(lines),
                0,
            )
            if ok:
                value = int(lines.value)
                self._windows_scroll_lines = -1 if value == WHEEL_PAGESCROLL else max(1, value)
            else:
                self._windows_scroll_lines = 3
        except Exception:
            self._windows_scroll_lines = 3
        return self._windows_scroll_lines

    def _chat_scroll_units_per_line(self) -> int:
        return 4

    def _refresh_chat_scrollregion(self) -> None:
        canvas = getattr(self.chat_history, "_parent_canvas", None)
        if canvas is None:
            return
        try:
            canvas.update_idletasks()
            bbox = canvas.bbox("all")
            if bbox is not None:
                canvas.configure(scrollregion=bbox)
        except Exception:
            return

    def _scroll_chat_to_end(self, _event: Any = None) -> None:
        canvas = getattr(self.chat_history, "_parent_canvas", None)
        if canvas is None:
            return
        def move() -> None:
            self._refresh_chat_scrollregion()
            canvas.yview_moveto(1.0)
        self.after_idle(move)

    def _on_send_shortcut(self, _event: Any) -> str:
        self._submit_chat_input()
        return "break"

    def _on_newline_shortcut(self, _event: Any) -> str:
        return None
