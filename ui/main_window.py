from __future__ import annotations

import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk

from .backend_adapter import GuiBackend, GuiOutputCard, GuiRunRequest, GuiRuntimeInputField, GuiSkillOption
from .assistant_worker import AssistantWorker
from .chat_router import current_runtime_field, is_question_like, should_route_to_workflow
from .chat_state import ChatMessage, ChatSessionState
from .conversation_store import ConversationStore
from .llm_client import AssistantRequest
from .prompt_builder import build_llm_messages
from .settings_manager import AppSettings, SettingsManager
from .worker import GuiWorker, WorkerEvent
from .workspace_manager import WorkspaceManager


class MainWindow(ctk.CTk):
    def __init__(self, repo_root: Path) -> None:
        super().__init__()
        self.repo_root = repo_root.resolve()
        self.backend = GuiBackend(self.repo_root)
        self.settings_manager = SettingsManager(self.repo_root)
        self.settings = self.settings_manager.load()
        self.settings_manager.apply(self.settings)
        self.workspace_manager = WorkspaceManager(self.settings.workspace_root)

        self.skills = self.backend.load_skills()
        self.skills_by_id = {skill.skill_id: skill for skill in self.skills}
        self.skill_names = [skill.display_name for skill in self.skills]
        self.skill_name_to_id = {skill.display_name: skill.skill_id for skill in self.skills}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.conversation_buttons: dict[str, ctk.CTkButton] = {}
        self.chat_sessions: dict[str, ChatSessionState] = {}
        self.conversation_store = ConversationStore()
        self.bible_path_by_label: dict[str, str] = {}
        self.selected_skill_id: str | None = None
        self.current_conversation_id: str | None = None
        self.selected_page = "run"
        self.selected_project_name = self.settings.last_project_name
        self.running_conversation_id: str | None = None

        self.event_queue: Queue[WorkerEvent] = Queue()
        self.worker: GuiWorker | None = None
        self.assistant_worker: AssistantWorker | None = None
        self.last_output_dir: Path | None = None

        self.workspace_root_var = ctk.StringVar(value=self.settings.workspace_root)
        self.project_var = ctk.StringVar(value=self.settings.last_project_name)
        self.project_inputs_var = ctk.StringVar()
        self.project_outputs_var = ctk.StringVar()
        self.output_path_var = ctk.StringVar(value=self.settings.default_output_path)
        self.status_var = ctk.StringVar(value="Ready")
        self.skill_title_var = ctk.StringVar(value="Select a skill")
        self.skill_selector_var = ctk.StringVar(value=self.skill_names[0] if self.skill_names else "")
        self.skill_description_var = ctk.StringVar(value="Choose a workflow from the top selector to start a guided run.")
        self.sidebar_workflow_summary_var = ctk.StringVar(
            value="Pick a workflow to see what it does, what input it expects, and where its outputs will go."
        )
        self.sidebar_input_var = ctk.StringVar(value="Input: File path, folder path, or brief depending on the workflow.")
        self.sidebar_output_hint_var = ctk.StringVar(value="Workflow output: Results are written into the active output folder.")
        self.sidebar_project_var = ctk.StringVar(value="Project: No active project")
        self.sidebar_output_var = ctk.StringVar(value="Output: Not set")
        self.provider_var = ctk.StringVar(value=self.settings.provider)
        self.model_var = ctk.StringVar(value=self.settings.model)
        self.api_key_var = ctk.StringVar(value=self.settings.api_key)
        self.base_url_var = ctk.StringVar(value=self.settings.base_url)
        self.show_api_key_var = ctk.BooleanVar(value=False)

        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")

        self.title("Fake Agent")
        self.geometry("1220x800")
        self.minsize(1080, 720)

        self._load_saved_conversations()
        self._build_ui()
        self._show_page("run")
        self._refresh_projects(select_name=self.settings.last_project_name)
        self._restore_initial_conversation()
        self._refresh_api_key_placeholder()
        self.after(150, self._poll_worker_events)

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
            text="Fake Agent",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        self.conversation_section = ctk.CTkFrame(self.sidebar)
        self.conversation_section.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.conversation_section.grid_columnconfigure(0, weight=1)
        self.conversation_section.grid_rowconfigure(2, weight=1)
        self._build_conversation_list()

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
        self.run_tab.grid_columnconfigure(0, weight=1)
        self.run_tab.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(self.run_tab)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header_frame,
            text="Skill",
            font=ctk.CTkFont(size=16, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))

        selector_row = ctk.CTkFrame(header_frame, fg_color="transparent")
        selector_row.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        selector_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(selector_row, text="Current Skill", anchor="w").grid(row=0, column=0, sticky="w", padx=(0, 10))
        self.skill_selector = ctk.CTkComboBox(
            selector_row,
            variable=self.skill_selector_var,
            values=self.skill_names or [""],
            state="readonly",
            command=self._on_skill_dropdown_changed,
        )
        self.skill_selector.grid(row=0, column=1, sticky="ew")
        self._build_skill_sidebar()

        thread_frame = ctk.CTkFrame(self.run_tab)
        thread_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        thread_frame.grid_columnconfigure(0, weight=1)
        thread_frame.grid_rowconfigure(0, weight=1)

        self.chat_history = ctk.CTkScrollableFrame(thread_frame)
        self.chat_history.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.chat_history.grid_columnconfigure(0, weight=1)

        composer_frame = ctk.CTkFrame(self.run_tab)
        composer_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        composer_frame.grid_columnconfigure(0, weight=1)
        composer_frame.grid_columnconfigure(1, weight=0)

        input_frame = ctk.CTkFrame(composer_frame, fg_color="transparent")
        input_frame.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=12)
        input_frame.grid_columnconfigure(0, weight=1)
        input_frame.grid_rowconfigure(0, weight=1)

        self.chat_input = ctk.CTkTextbox(input_frame, height=68, wrap="word")
        self.chat_input.grid(row=0, column=0, sticky="ew")
        self.chat_input.bind("<Return>", self._on_send_shortcut)
        self.chat_input.bind("<Shift-Return>", self._on_newline_shortcut)
        self.send_button = ctk.CTkButton(
            input_frame,
            text="Send",
            command=self._submit_chat_input,
            width=76,
            height=28,
        )
        self.send_button.place(relx=1.0, rely=1.0, x=-8, y=-8, anchor="se")

        action_frame = ctk.CTkFrame(composer_frame, fg_color="transparent")
        action_frame.grid(row=0, column=1, sticky="e", padx=(0, 12), pady=12)
        left_actions = ctk.CTkFrame(action_frame, fg_color="transparent")
        left_actions.pack(side="left", padx=(0, 8))
        browse_button_width = 126
        self.browse_file_button = ctk.CTkButton(
            left_actions,
            text="Browse File",
            command=self._browse_input_file,
            width=browse_button_width,
            height=30,
        )
        self.browse_file_button.pack(anchor="e", pady=(0, 8))
        self.browse_folder_button = ctk.CTkButton(
            left_actions,
            text="Browse Folder",
            command=self._browse_input_folder,
            width=browse_button_width,
            height=30,
        )
        self.browse_folder_button.pack(anchor="e")
        self.open_output_button = ctk.CTkButton(
            action_frame,
            text="Open\nOutput",
            command=self._open_output_folder,
            width=68,
            height=68,
            fg_color="#f59e0b",
            hover_color="#d97706",
            text_color="#111827",
        )
        self.open_output_button.pack(side="left")


    def _build_settings_tab(self) -> None:
        self.settings_tab.grid_columnconfigure(0, weight=1)
        self.settings_tab.grid_rowconfigure(0, weight=1)

        body = ctk.CTkScrollableFrame(self.settings_tab)
        body.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        body.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(body, text="LLM Provider").grid(row=0, column=0, sticky="w", padx=12, pady=(12, 6))
        self.provider_combo = ctk.CTkComboBox(
            body,
            variable=self.provider_var,
            values=["openrouter", "openai"],
            state="readonly",
            command=lambda _value: self._refresh_api_key_placeholder(),
        )
        self.provider_combo.grid(row=0, column=1, sticky="ew", padx=12, pady=(12, 6))

        ctk.CTkLabel(body, text="Model").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        ctk.CTkEntry(body, textvariable=self.model_var).grid(row=1, column=1, sticky="ew", padx=12, pady=6)

        ctk.CTkLabel(body, text="API Key").grid(row=2, column=0, sticky="w", padx=12, pady=6)
        api_frame = ctk.CTkFrame(body, fg_color="transparent")
        api_frame.grid(row=2, column=1, sticky="ew", padx=12, pady=6)
        api_frame.grid_columnconfigure(0, weight=1)
        self.api_key_entry = ctk.CTkEntry(api_frame, textvariable=self.api_key_var, show="*")
        self.api_key_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkSwitch(
            api_frame,
            text="Show",
            variable=self.show_api_key_var,
            command=self._toggle_api_key_visibility,
        ).grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(body, text="Base URL").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        ctk.CTkEntry(body, textvariable=self.base_url_var).grid(row=3, column=1, sticky="ew", padx=12, pady=6)

        workspace_section = ctk.CTkFrame(body)
        workspace_section.grid(row=4, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 6))
        workspace_section.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            workspace_section,
            text="Workspace",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(workspace_section, text="Workspace Root").grid(row=1, column=0, sticky="w", padx=12, pady=6)
        ctk.CTkEntry(workspace_section, textvariable=self.workspace_root_var).grid(
            row=1, column=1, sticky="ew", padx=12, pady=6
        )
        ctk.CTkButton(
            workspace_section,
            text="Browse Workspace",
            command=self._browse_workspace,
            width=150,
        ).grid(row=1, column=2, sticky="e", padx=12, pady=6)

        ctk.CTkLabel(workspace_section, text="Active Project").grid(row=2, column=0, sticky="w", padx=12, pady=6)
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
        ctk.CTkButton(project_buttons, text="Refresh", command=self._refresh_projects, width=90).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(project_buttons, text="New Project", command=self._create_project, width=110).pack(side="left")

        ctk.CTkLabel(workspace_section, text="Project Inputs").grid(row=3, column=0, sticky="w", padx=12, pady=6)
        inputs_frame = ctk.CTkFrame(workspace_section, fg_color="transparent")
        inputs_frame.grid(row=3, column=1, columnspan=2, sticky="ew", padx=12, pady=6)
        inputs_frame.grid_columnconfigure(0, weight=1)
        self.project_inputs_entry = ctk.CTkEntry(inputs_frame, textvariable=self.project_inputs_var)
        self.project_inputs_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.project_inputs_entry.configure(state="disabled")
        ctk.CTkButton(
            inputs_frame,
            text="Open",
            command=self._open_project_inputs_folder,
            width=90,
        ).grid(row=0, column=1)

        ctk.CTkLabel(workspace_section, text="Project Outputs").grid(row=4, column=0, sticky="w", padx=12, pady=6)
        outputs_frame = ctk.CTkFrame(workspace_section, fg_color="transparent")
        outputs_frame.grid(row=4, column=1, columnspan=2, sticky="ew", padx=12, pady=(6, 12))
        outputs_frame.grid_columnconfigure(0, weight=1)
        self.project_outputs_entry = ctk.CTkEntry(outputs_frame, textvariable=self.project_outputs_var)
        self.project_outputs_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.project_outputs_entry.configure(state="disabled")
        ctk.CTkButton(
            outputs_frame,
            text="Open",
            command=self._open_project_folder,
            width=90,
        ).grid(row=0, column=1, padx=(0, 8))
        ctk.CTkButton(
            outputs_frame,
            text="Open Outputs",
            command=self._open_output_folder,
            width=120,
        ).grid(row=0, column=2)

        ctk.CTkLabel(body, text="Fallback Output Root").grid(row=5, column=0, sticky="w", padx=12, pady=(10, 6))
        output_frame = ctk.CTkFrame(body, fg_color="transparent")
        output_frame.grid(row=5, column=1, sticky="ew", padx=12, pady=(10, 6))
        output_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(output_frame, textvariable=self.output_path_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 8)
        )
        ctk.CTkButton(output_frame, text="Browse", command=self._browse_output_folder, width=100).grid(
            row=0, column=1
        )

        ctk.CTkButton(body, text="Save Settings", command=self._save_settings, width=160).grid(
            row=6, column=1, sticky="e", padx=12, pady=(16, 12)
        )

    def _build_logs_tab(self) -> None:
        self.logs_tab.grid_columnconfigure(0, weight=1)
        self.logs_tab.grid_rowconfigure(0, weight=1)

        self.logs_textbox = ctk.CTkTextbox(self.logs_tab, wrap="word")
        self.logs_textbox.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.logs_textbox.configure(state="disabled")

        ctk.CTkButton(self.logs_tab, text="Clear Logs", command=self._clear_logs, width=140).grid(
            row=1, column=0, sticky="e", padx=12, pady=(0, 12)
        )

    def _build_conversation_list(self) -> None:
        ctk.CTkLabel(
            self.conversation_section,
            text="Conversations",
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))
        ctk.CTkButton(
            self.conversation_section,
            text="New Conversation",
            command=self._create_new_conversation_for_selected_skill,
            height=32,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        self.conversation_list = ctk.CTkScrollableFrame(self.conversation_section)
        self.conversation_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self.conversation_list.grid_columnconfigure(0, weight=1)

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

    def _build_sidebar_nav(self, parent: ctk.CTkFrame) -> None:
        nav_items = [
            ("run", "\u25b6 Run"),
            ("settings", "\u2699 Settings"),
            ("logs", "\U0001f4c4 Logs"),
        ]
        for row, (page_name, label) in enumerate(nav_items):
            button = ctk.CTkButton(
                parent,
                text=label,
                anchor="w",
                fg_color="transparent",
                hover_color=("gray78", "gray24"),
                command=lambda name=page_name: self._show_page(name),
            )
            button.grid(row=row, column=0, sticky="ew", pady=(0 if row == 0 else 8, 0))
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
            button.configure(fg_color=("gray72", "gray28") if current_name == page_name else "transparent")

    def _load_saved_conversations(self) -> None:
        conversations, active_conversation_id = self.conversation_store.load()
        self.chat_sessions.clear()
        for conversation in conversations:
            if conversation.skill_id not in self.skills_by_id:
                continue
            conversation.skill_name = self.skills_by_id[conversation.skill_id].display_name
            conversation.execution_in_progress = False
            self.chat_sessions[conversation.id] = conversation
        self.current_conversation_id = active_conversation_id if active_conversation_id in self.chat_sessions else None

    def _restore_initial_conversation(self) -> None:
        if self.current_conversation_id and self.current_conversation_id in self.chat_sessions:
            self._select_conversation(self.current_conversation_id)
            return
        if self.chat_sessions:
            latest = self._sorted_conversations()[0]
            self._select_conversation(latest.id)
            return

        default_skill_id = self.settings.default_skill_id
        if default_skill_id not in self.skills_by_id and self.skills:
            default_skill_id = self.skills[0].skill_id
        if default_skill_id:
            self._create_conversation_for_skill(default_skill_id, switch=True)

    def _select_skill(self, skill_id: str) -> None:
        if skill_id not in self.skills_by_id:
            return
        target = self._latest_conversation_for_skill(skill_id)
        if target is None:
            target = self._create_conversation_for_skill(skill_id, switch=False)
        self._select_conversation(target.id)

    def _select_conversation(self, conversation_id: str) -> None:
        conversation = self.chat_sessions.get(conversation_id)
        if conversation is None or conversation.skill_id not in self.skills_by_id:
            return

        skill = self.skills_by_id[conversation.skill_id]
        self.current_conversation_id = conversation.id
        self.selected_skill_id = conversation.skill_id
        self.skill_selector_var.set(skill.display_name)
        self.skill_title_var.set(skill.display_name)
        self.skill_description_var.set(self._shorten_text(skill.description or "No description available.", limit=180))
        self.sidebar_workflow_summary_var.set(self._build_workflow_summary(skill))
        self.sidebar_input_var.set(self._build_input_expectation(skill))
        self.sidebar_output_hint_var.set(self._build_output_expectation(skill))
        self._apply_conversation_project(conversation)
        self._refresh_run_context()
        self._refresh_chat_view()
        self._refresh_conversation_list()
        self._update_composer_state()
        self._persist_gui_state()
        self._save_conversations()
        self._show_page("run")

    def _create_new_conversation_for_selected_skill(self) -> None:
        skill = self._selected_skill()
        if skill is None:
            messagebox.showwarning("Run", "Choose a skill first.")
            return
        if self.worker is not None and self.worker.is_alive():
            messagebox.showwarning("Run", "Wait for the current job to finish before starting a new conversation.")
            return
        conversation = self._create_conversation_for_skill(skill.skill_id, switch=True)
        self._select_conversation(conversation.id)
        self._clear_chat_input()

    def _create_conversation_for_skill(self, skill_id: str, *, switch: bool) -> ChatSessionState:
        skill = self.skills_by_id[skill_id]
        project_name = self.project_var.get().strip()
        timestamp = self._display_timestamp()
        conversation = ChatSessionState(
            id=uuid.uuid4().hex,
            title=f"{skill.display_name} - {timestamp}",
            skill_id=skill.skill_id,
            skill_name=skill.display_name,
            project_name=project_name,
        )
        self.chat_sessions[conversation.id] = conversation
        intro = self._build_initial_conversation_message(skill, project_name)
        self._append_chat_message(conversation.id, "assistant", intro)
        self._prompt_for_primary_input(skill, conversation)
        self._save_conversations(active_conversation_id=conversation.id if switch else self.current_conversation_id)
        self._refresh_conversation_list()
        return conversation

    def _latest_conversation_for_skill(self, skill_id: str) -> ChatSessionState | None:
        matches = [conversation for conversation in self.chat_sessions.values() if conversation.skill_id == skill_id]
        if not matches:
            return None
        return sorted(matches, key=lambda item: item.updated_at, reverse=True)[0]

    def _sorted_conversations(self) -> list[ChatSessionState]:
        return sorted(self.chat_sessions.values(), key=lambda item: item.updated_at, reverse=True)

    def _current_conversation(self) -> ChatSessionState | None:
        if self.current_conversation_id is None:
            return None
        return self.chat_sessions.get(self.current_conversation_id)

    def _refresh_conversation_list(self) -> None:
        for child in self.conversation_list.winfo_children():
            child.destroy()
        self.conversation_buttons.clear()

        for row, conversation in enumerate(self._sorted_conversations()):
            updated_label = self._format_timestamp_for_title(conversation.updated_at)
            subtitle = self._shorten_text(
                f"{conversation.skill_name} | {conversation.project_name or 'No project'} | {updated_label}",
                limit=56,
            )
            row_frame = ctk.CTkFrame(
                self.conversation_list,
                fg_color=("gray72", "gray28") if conversation.id == self.current_conversation_id else "transparent",
            )
            row_frame.grid(row=row, column=0, sticky="ew", padx=4, pady=4)
            row_frame.grid_columnconfigure(0, weight=1)

            button = ctk.CTkButton(
                row_frame,
                text=f"{self._shorten_text(conversation.title, limit=28)}\n{subtitle}",
                anchor="w",
                height=52,
                fg_color="transparent",
                hover_color=("gray78", "gray24"),
                command=lambda conversation_id=conversation.id: self._select_conversation(conversation_id),
            )
            button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            ctk.CTkButton(
                row_frame,
                text="✎",
                width=28,
                height=28,
                fg_color="transparent",
                hover_color=("gray78", "gray24"),
                command=lambda conversation_id=conversation.id: self._rename_conversation(conversation_id),
            ).grid(row=0, column=1, sticky="ne", padx=(0, 4), pady=4)
            ctk.CTkButton(
                row_frame,
                text="✕",
                width=28,
                height=28,
                fg_color="transparent",
                hover_color=("#fca5a5", "#7f1d1d"),
                command=lambda conversation_id=conversation.id: self._delete_conversation(conversation_id),
            ).grid(row=0, column=2, sticky="ne", pady=4)
            self.conversation_buttons[conversation.id] = button

    def _save_conversations(self, *, active_conversation_id: str | None = None) -> None:
        active_id = active_conversation_id if active_conversation_id is not None else self.current_conversation_id
        conversations = self._sorted_conversations()
        self.conversation_store.save(conversations, active_id)

    def _rename_conversation(self, conversation_id: str | None = None) -> None:
        conversation = self.chat_sessions.get(conversation_id) if conversation_id else self._current_conversation()
        if conversation is None:
            messagebox.showwarning("Rename Conversation", "Choose a conversation first.")
            return
        dialog = ctk.CTkInputDialog(text="Enter a new conversation title:", title="Rename Conversation")
        new_title = dialog.get_input()
        if new_title in (None, ""):
            return
        cleaned = " ".join(new_title.split()).strip()
        if not cleaned:
            messagebox.showwarning("Rename Conversation", "Conversation title cannot be empty.")
            return
        conversation.title = cleaned
        conversation.touch()
        self._refresh_conversation_list()
        self._save_conversations()

    def _delete_conversation(self, conversation_id: str | None = None) -> None:
        conversation = self.chat_sessions.get(conversation_id) if conversation_id else self._current_conversation()
        if conversation is None:
            messagebox.showwarning("Delete Conversation", "Choose a conversation first.")
            return
        if self.worker is not None and self.worker.is_alive() and self.running_conversation_id == conversation.id:
            messagebox.showwarning("Delete Conversation", "Wait for the current workflow to finish before deleting this conversation.")
            return
        if not messagebox.askyesno("Delete Conversation", f"Delete conversation?\n\n{conversation.title}"):
            return

        deleted_skill_id = conversation.skill_id
        self.chat_sessions.pop(conversation.id, None)
        self.current_conversation_id = None
        replacement = self._latest_conversation_for_skill(deleted_skill_id)
        if replacement is None and self.chat_sessions:
            replacement = self._sorted_conversations()[0]
        if replacement is None:
            default_skill_id = deleted_skill_id if deleted_skill_id in self.skills_by_id else (self.skills[0].skill_id if self.skills else "")
            if default_skill_id:
                replacement = self._create_conversation_for_skill(default_skill_id, switch=False)
        self._refresh_conversation_list()
        self._save_conversations(active_conversation_id=replacement.id if replacement else None)
        if replacement is not None:
            self._select_conversation(replacement.id)

    def _display_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H-%M")

    def _format_timestamp_for_title(self, timestamp: str) -> str:
        cleaned = timestamp.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(cleaned).strftime("%Y-%m-%d %H-%M")
        except ValueError:
            return "Conversation"

    def _apply_conversation_project(self, conversation: ChatSessionState) -> None:
        project_name = conversation.project_name.strip()
        if project_name:
            self._apply_project_selection(project_name, update_conversation=False)
        else:
            self._refresh_run_context()

    def _submit_chat_input(self, preset_text: str | None = None) -> None:
        skill = self._selected_skill()
        if skill is None:
            messagebox.showwarning("Run", "Choose a skill from the sidebar first.")
            return
        session = self._current_conversation()
        if session is None:
            session = self._create_conversation_for_skill(skill.skill_id, switch=True)
            self.current_conversation_id = session.id
        if session.execution_in_progress or session.assistant_reply_pending:
            messagebox.showwarning("Run", "A workflow is already running.")
            return

        text = (preset_text if preset_text is not None else self.chat_input.get("1.0", "end")).strip()
        if not text:
            messagebox.showwarning("Run", "Enter a reply or choose a file/folder first.")
            return
        if preset_text is None:
            self._clear_chat_input()

        self._append_chat_message(session.id, "user", text)
        if self._should_use_llm_reply(skill, session, text):
            self._start_llm_reply(skill, session, text)
            self._refresh_chat_view()
            return
        try:
            self._handle_chat_reply(skill, session, text)
        except ValueError as exc:
            self._append_chat_message(session.id, "error", str(exc))
        self._refresh_chat_view()

    def _handle_chat_reply(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> None:
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
            self._capture_existing_path(text, "Please provide a valid adaptation plan file.")
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
        raise ValueError("This conversation is not ready for a new reply yet.")

    def _capture_primary_input(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> None:
        session.input_path = ""
        session.direct_text = ""

        candidate = text.strip().strip('"')
        if candidate:
            path = Path(candidate).expanduser()
            if path.exists():
                resolved = str(path.resolve())
                if path.is_dir() and not skill.supports_folder_input:
                    raise ValueError("This skill does not accept folder input.")
                if path.is_file() and not skill.supports_file_input:
                    raise ValueError("This skill does not accept file input.")
                session.input_path = resolved
            elif skill.supports_text_input:
                session.direct_text = text.strip()
            else:
                raise ValueError("Please provide an existing file or folder path for this skill.")

        if not session.input_path and not session.direct_text:
            raise ValueError("Please provide a valid file path, folder path, or direct text input.")

        if skill.skill_id == "rewriting":
            self._prompt_for_rewriting_mode(skill, session)
            return
        if skill.startup_mode == "explicit_step_selection":
            self._prompt_for_step_selection(skill, session)
            return
        self._prompt_for_next_runtime_or_confirmation(skill, session)

    def _capture_step_selection(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> None:
        raw_value = text.strip().lower()
        if raw_value in {"auto", "default", ""}:
            if skill.allow_auto_route:
                session.selected_step_number = None
            elif skill.default_step_number is not None:
                session.selected_step_number = skill.default_step_number
            else:
                raise ValueError("Please reply with a valid step number.")
        else:
            try:
                step_number = int(text.strip().split(" ", 1)[0])
            except ValueError as exc:
                raise ValueError("Please reply with `auto` or a step number such as `1`.") from exc
            valid_steps = {step.number for step in skill.step_summaries}
            if step_number not in valid_steps:
                raise ValueError("That step number is not available for this skill.")
            session.selected_step_number = step_number

        self._prompt_for_next_runtime_or_confirmation(skill, session)

    def _capture_rewriting_mode(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> None:
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
            raise ValueError("Reply with `1`, `2`, `3`, or the full rewriting mode name.")
        session.rewriting_mode = mode

        if mode in {"build_bible", "build_bible_and_rewrite"}:
            self._prompt_for_rewriting_plan(skill, session)
            return
        self._prompt_for_rewriting_bible(skill, session)

    def _capture_runtime_value(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> None:
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

    def _handle_run_confirmation(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> None:
        normalized = text.strip().lower()
        if normalized in {"restart", "reset", "new"}:
            self._create_new_conversation_for_selected_skill()
            return
        if normalized not in {"run", "start", "yes", "y", "go"}:
            raise ValueError("Reply `run` to start, or `restart` to begin again.")
        self._start_run(skill, session)

    def _should_use_llm_reply(self, skill: GuiSkillOption, session: ChatSessionState, text: str) -> bool:
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

    def _start_llm_reply(self, skill: GuiSkillOption, session: ChatSessionState, user_message: str) -> None:
        settings = AppSettings(
            provider=self.provider_var.get().strip().lower(),
            model=self.model_var.get().strip(),
            api_key=self.api_key_var.get().strip(),
            base_url=self.base_url_var.get().strip(),
            default_output_path=self.output_path_var.get().strip() or self.settings.default_output_path,
            default_skill_id=self.selected_skill_id or "",
            workspace_root=self.workspace_root_var.get().strip() or self.settings.workspace_root,
            last_project_name=self.project_var.get().strip(),
        )
        session.assistant_reply_pending = True
        session.touch()
        self._save_conversations()
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

    def _prompt_for_primary_input(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        if skill.supports_text_input:
            prompt = (
                "Send the source for this workflow.\n"
                "You can paste a file path, a folder path, or direct text here.\n"
                "Use Browse File or Browse Folder if that is easier."
            )
        else:
            prompt = (
                "Send the source for this workflow.\n"
                "Paste an existing file path or folder path here.\n"
                "Use Browse File or Browse Folder if that is easier."
            )
        self._push_prompt(skill.skill_id, session, "awaiting_input", prompt)

    def _prompt_for_step_selection(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        default_step = skill.default_step_number
        if default_step is None and skill.step_summaries:
            default_step = skill.step_summaries[0].number

        lines = ["Available steps:"]
        for step in skill.step_summaries:
            suffix = " (default)" if step.number == default_step else ""
            detail = f" - {step.description}" if getattr(step, "description", "") else ""
            lines.append(f"{step.number}. {step.title}{suffix}{detail}")
        lines.append("Reply with the step number. You can also reply `default`.")
        self._push_prompt(skill.skill_id, session, "awaiting_step", "\n".join(lines))

    def _prompt_for_rewriting_mode(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        prompt = (
            "Choose a rewriting mode.\n"
            "1. build_bible\n"
            "2. rewrite_with_bible\n"
            "3. build_bible_and_rewrite (default)"
        )
        self._push_prompt(skill.skill_id, session, "awaiting_rewriting_mode", prompt)

    def _prompt_for_rewriting_plan(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        self._push_prompt(
            skill.skill_id,
            session,
            "awaiting_rewriting_plan",
            "Send the adaptation plan file path for the rewriting workflow.",
        )

    def _prompt_for_rewriting_bible(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        self._reload_bible_choices()
        if not self.bible_path_by_label:
            raise ValueError("No refresh bible was found in the current output roots. Build one first or choose a different project.")
        lines = ["Available refresh bibles:"]
        for index, (label, path) in enumerate(self.bible_path_by_label.items(), start=1):
            lines.append(f"{index}. {label} - {path}")
        lines.append("Reply with the bible number or paste the bible file path directly.")
        self._push_prompt(skill.skill_id, session, "awaiting_rewriting_bible", "\n".join(lines))

    def _prompt_for_rewriting_supplemental(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        self._push_prompt(
            skill.skill_id,
            session,
            "awaiting_rewriting_supplemental",
            "Optional: send a supplemental script file or folder path, or reply `skip`.",
        )

    def _prompt_for_next_runtime_or_confirmation(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
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
                suffix = " (default)" if choice == field.default else ""
                prompt_lines.append(f"{index}. {choice}{suffix}")
            prompt_lines.append("Reply with the number or the choice text.")
        elif field.default not in (None, ""):
            prompt_lines.append(f"Default: {field.default}")
        if not field.required:
            prompt_lines.append("Reply `skip` to leave this blank.")
        self._push_prompt(skill.skill_id, session, "awaiting_runtime", "\n".join(prompt_lines))

    def _prompt_for_ready_to_run(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        output_root = self._effective_output_root()
        input_summary = session.input_path or self._shorten_text(session.direct_text)
        lines = [
            "Everything is ready.",
            f"Input: {input_summary}",
            f"Output root: {output_root}",
        ]
        if session.selected_step_number is not None:
            lines.append(f"Start step: {session.selected_step_number}")
        if skill.skill_id == "rewriting":
            lines.append(f"Rewriting mode: {session.rewriting_mode}")
        lines.append("Reply `run` to start, or `restart` to begin again.")
        self._push_prompt(skill.skill_id, session, "ready_to_run", "\n".join(lines))

    def _push_prompt(self, skill_id: str, session: ChatSessionState, stage: str, text: str) -> None:
        session.stage = stage
        session.current_prompt = text
        session.touch()
        self._append_chat_message(session.id, "assistant", text)

    def _filtered_runtime_fields(self, skill: GuiSkillOption, session: ChatSessionState) -> list[GuiRuntimeInputField]:
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
            raise ValueError(f"Please provide a value for: {field.prompt}")
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
                raise ValueError("Please reply with one of the listed numbers or choice values.")
            return normalized_choice
        if field.field_type == "int":
            try:
                int(value)
            except ValueError as exc:
                raise ValueError("Please reply with a whole number.") from exc
            return value
        if field.field_type == "bool":
            lowered = value.lower()
            if lowered not in {"1", "0", "true", "false", "yes", "no", "y", "n", "on", "off"}:
                raise ValueError("Please reply with yes/no, true/false, or 1/0.")
            return value
        return value

    def _start_run(self, skill: GuiSkillOption, session: ChatSessionState) -> None:
        if self.worker is not None and self.worker.is_alive():
            raise ValueError("A workflow is already running. Wait for it to finish first.")
        if not self.model_var.get().strip():
            messagebox.showwarning("Run", "Model is empty. Save settings first.")
            raise ValueError("Model is empty. Open Settings and save a model first.")
        if not self.api_key_var.get().strip():
            messagebox.showwarning("Run", "API key is empty. Save settings first.")
            raise ValueError("API key is empty. Open Settings and save an API key first.")

        outputs_root = self._effective_output_root()
        outputs_root.mkdir(parents=True, exist_ok=True)
        request = GuiRunRequest(
            skill_id=skill.skill_id,
            input_path=session.input_path,
            outputs_root=str(outputs_root),
            direct_text=session.direct_text,
            selected_step_number=session.selected_step_number,
            runtime_values=dict(session.runtime_values),
            auto_accept_review_steps=True,
            rewriting_mode=session.rewriting_mode if skill.skill_id == "rewriting" else "",
            rewriting_plan_path=session.rewriting_plan_path,
            rewriting_bible_path=session.rewriting_bible_path,
            rewriting_supplemental_path=session.rewriting_supplemental_path,
        )

        self._persist_gui_state()
        session.execution_in_progress = True
        session.stage = "running"
        session.touch()
        self.running_conversation_id = session.id
        self.status_var.set("Running...")
        self._update_composer_state()
        self._append_chat_message(
            session.id,
            "status",
            "Running now. Progress will stream into Logs, and results will appear here when the workflow finishes.",
        )
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
            elif event_type == "result":
                self._handle_worker_result(payload)
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
                self.running_conversation_id = None
                self._update_composer_state()
            elif event_type == "assistant_finished":
                self.assistant_worker = None
                self._update_composer_state()

        self.after(150, self._poll_worker_events)

    def _handle_worker_result(self, result) -> None:
        conversation_id = self.running_conversation_id
        if conversation_id is None:
            return
        session = self.chat_sessions.get(conversation_id)
        if session is None:
            return

        session.execution_in_progress = False
        session.latest_result = result
        session.touch()
        self.last_output_dir = result.session_dir
        self.status_var.set(f"Finished with {result.success_count} success(es) and {result.failure_count} failure(s).")
        summary = f"Run complete. Output folder:\n{result.session_dir}"
        self._append_chat_message(conversation_id, "result", summary, output_cards=result.output_cards)
        session.reset_for_new_run()
        skill = self.skills_by_id.get(session.skill_id)
        if skill is not None:
            self._append_chat_message(
                conversation_id,
                "assistant",
                "Send another file, folder, or brief when you want to start a new run with this skill.",
            )
            session.current_prompt = "Send another file, folder, or brief when you want to start a new run with this skill."
        if self.current_conversation_id == conversation_id:
            self._refresh_chat_view()
        self._refresh_conversation_list()
        self._save_conversations()

        if result.failure_count == 0:
            messagebox.showinfo("Run Complete", f"Output saved to:\n{result.session_dir}")
        else:
            messagebox.showwarning(
                "Run Finished with Errors",
                f"Output folder:\n{result.session_dir}\n\nFailures: {result.failure_count}",
            )

    def _handle_worker_error(self, error_message: str) -> None:
        conversation_id = self.running_conversation_id
        if conversation_id is not None:
            session = self.chat_sessions.get(conversation_id)
            if session is not None:
                session.execution_in_progress = False
                session.stage = "awaiting_input"
                session.current_prompt = "The run failed. Fix the issue and send a new input when you are ready."
                session.touch()
                self._append_chat_message(conversation_id, "error", error_message)
                self._append_chat_message(
                    conversation_id,
                    "assistant",
                    "The run failed. Fix the issue and send a new input when you are ready.",
                )
                if self.current_conversation_id == conversation_id:
                    self._refresh_chat_view()
                self._refresh_conversation_list()
                self._save_conversations()
        self.status_var.set("Failed")
        messagebox.showerror("Run Failed", error_message)

    def _handle_assistant_result(self, conversation_id: str, reply_text: str) -> None:
        session = self.chat_sessions.get(conversation_id)
        if session is None:
            return
        session.assistant_reply_pending = False
        session.touch()
        self._append_chat_message(conversation_id, "assistant", reply_text)
        if self.current_conversation_id == conversation_id:
            self._refresh_chat_view()
        self._refresh_conversation_list()
        self._save_conversations()

    def _handle_assistant_error(self, conversation_id: str, error_text: str) -> None:
        session = self.chat_sessions.get(conversation_id)
        if session is None:
            return
        session.assistant_reply_pending = False
        session.touch()
        message = (
            "I couldn't generate a helper reply right now.\n"
            f"{error_text}\n"
            "You can still continue using the structured workflow inputs."
        )
        self._append_chat_message(conversation_id, "error", message)
        if self.current_conversation_id == conversation_id:
            self._refresh_chat_view()
        self._refresh_conversation_list()
        self._save_conversations()

    def _refresh_chat_view(self) -> None:
        for child in self.chat_history.winfo_children():
            child.destroy()

        session = self._current_conversation()
        if session is None:
            return
        for message in session.messages:
            self._render_chat_message(message)
        if session.execution_in_progress:
            self._render_inline_progress_card()
        elif session.assistant_reply_pending:
            self._render_inline_progress_card(label="Thinking", description="")
        self._scroll_chat_to_end()

    def _render_chat_message(self, message: ChatMessage) -> None:
        outer = ctk.CTkFrame(self.chat_history, fg_color="transparent")
        outer.pack(fill="x", padx=12, pady=8)
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=1)

        role = message.role
        bubble_color = ("#f3f4f6", "#24262b")
        text_color = ("#111827", "#f3f4f6")
        role_label = "Assistant"
        column = 0
        sticky = "w"
        pad_x = (0, 140)
        border_color = ("#d1d5db", "#3f4754")

        if role == "user":
            bubble_color = ("#dbeafe", "#1f4f86")
            text_color = ("#0f172a", "#eff6ff")
            role_label = "You"
            column = 1
            sticky = "e"
            pad_x = (140, 0)
            border_color = ("#93c5fd", "#2d6ab3")
        elif role == "status":
            bubble_color = ("#f3f4f6", "#2d323a")
            text_color = ("#374151", "#d1d5db")
            role_label = "Status"
            border_color = ("#d1d5db", "#4b5563")
        elif role == "error":
            bubble_color = ("#fee2e2", "#5f2020")
            text_color = ("#991b1b", "#fecaca")
            role_label = "Error"
            border_color = ("#fca5a5", "#7f1d1d")
        elif role == "result":
            bubble_color = ("#dcfce7", "#193b2b")
            text_color = ("#14532d", "#dcfce7")
            role_label = "Result"
            pad_x = (0, 90)
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

        ctk.CTkLabel(
            bubble,
            text=role_label,
            anchor="w",
            text_color=("gray45", "#cbd5e1") if role not in {"error", "result"} else text_color,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            bubble,
            text=message.text,
            justify="left",
            anchor="w",
            wraplength=720,
            text_color=text_color,
        ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))

        for index, card in enumerate(message.output_cards, start=2):
            self._render_output_card(bubble, index, card)

    def _render_output_card(self, parent: ctk.CTkFrame, row: int, card: GuiOutputCard) -> None:
        card_frame = ctk.CTkFrame(
            parent,
            fg_color=("white", "#111827"),
            border_width=1,
            border_color=("#bbf7d0", "#2f855a"),
        )
        card_frame.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 12))
        card_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card_frame,
            text=card.title,
            font=ctk.CTkFont(size=15, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            card_frame,
            text=str(card.path),
            text_color="gray60",
            justify="left",
            anchor="w",
            wraplength=660,
        ).grid(row=1, column=0, sticky="ew", padx=12)
        if card.preview_text:
            ctk.CTkLabel(
                card_frame,
                text=card.preview_text,
                justify="left",
                anchor="w",
                wraplength=660,
            ).grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 6))

        actions = ctk.CTkFrame(card_frame, fg_color="transparent")
        actions.grid(row=3, column=0, sticky="w", padx=12, pady=(0, 12))
        ctk.CTkButton(actions, text="Open", command=lambda p=card.path: self._open_path(p), width=80).pack(
            side="left", padx=(0, 8)
        )
        ctk.CTkButton(
            actions,
            text="Open Folder",
            command=lambda p=card.output_dir: self._open_path(p),
            width=110,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Preview",
            command=lambda c=card: self._preview_output_card(c),
            width=90,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Copy",
            command=lambda c=card: self._copy_output_card(c),
            width=80,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Save As",
            command=lambda c=card: self._save_output_card_as(c),
            width=90,
        ).pack(side="left")

    def _render_inline_progress_card(
        self,
        *,
        label: str = "Running",
        description: str = "The workflow is still running. Full logs continue updating in the Logs page.",
    ) -> None:
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

        ctk.CTkLabel(
            bubble,
            text=label,
            anchor="w",
            text_color=("gray45", "#cbd5e1"),
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 2))
        row = 1
        if description.strip():
            ctk.CTkLabel(
                bubble,
                text=description,
                justify="left",
                anchor="w",
                wraplength=620,
                text_color=("#374151", "#d1d5db"),
            ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 8))
            row = 2

        progress = ctk.CTkProgressBar(bubble, mode="indeterminate")
        progress.grid(row=row, column=0, sticky="ew", padx=14, pady=(0, 12))
        progress.start()

    def _append_chat_message(
        self,
        conversation_id: str,
        role: str,
        text: str,
        *,
        output_cards: list[GuiOutputCard] | None = None,
    ) -> None:
        session = self.chat_sessions.get(conversation_id)
        if session is None:
            return
        session.messages.append(ChatMessage(role=role, text=text, output_cards=output_cards or []))
        session.touch()
        self._save_conversations()

    def _update_composer_state(self) -> None:
        enabled = (
            self.current_conversation_id is not None
            and not (self.worker is not None and self.worker.is_alive())
            and not (self.assistant_worker is not None and self.assistant_worker.is_alive())
        )
        state = "normal" if enabled else "disabled"
        self.chat_input.configure(state=state)
        self.send_button.configure(state=state)
        self.browse_file_button.configure(state=state)
        self.browse_folder_button.configure(state=state)
        self.open_output_button.configure(state=state)

    def _refresh_run_context(self) -> None:
        project_name = self.project_var.get().strip() or "No active project"
        output_root = self._effective_output_root()
        self.sidebar_project_var.set(f"Project: {project_name}")
        self.sidebar_output_var.set(f"Output: {self._shorten_text(str(output_root), limit=96)}")

    def _save_settings(self) -> None:
        provider = self.provider_var.get().strip().lower()
        model = self.model_var.get().strip()
        api_key = self.api_key_var.get().strip()
        base_url = self.base_url_var.get().strip()
        default_output_path = self.output_path_var.get().strip()
        workspace_root = self.workspace_root_var.get().strip()

        if not provider:
            messagebox.showwarning("Settings", "Please choose an LLM provider.")
            return
        if not model:
            messagebox.showwarning("Settings", "Please enter a model name.")
            return
        if not api_key:
            messagebox.showwarning("Settings", "Please enter an API key.")
            return
        if not default_output_path:
            messagebox.showwarning("Settings", "Please enter a fallback output path.")
            return
        if not workspace_root:
            messagebox.showwarning("Settings", "Please choose a workspace root.")
            return

        self.workspace_manager.set_workspace_root(workspace_root)
        selected_skill = self._selected_skill()
        settings = AppSettings(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            default_output_path=default_output_path,
            default_skill_id=selected_skill.skill_id if selected_skill else "",
            workspace_root=workspace_root,
            last_project_name=self.project_var.get().strip(),
        )
        self.settings_manager.save(settings)
        self.settings = settings
        self._refresh_projects(select_name=self.project_var.get().strip())
        self._refresh_run_context()
        messagebox.showinfo("Settings", "Settings saved.")

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
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            self._refresh_run_context()
            return

        self.workspace_manager.set_workspace_root(workspace_root)
        self.workspace_manager.ensure_workspace_root()
        project_names = [project.name for project in self.workspace_manager.list_projects()]
        self.project_combo.configure(values=project_names or [""])

        target_name = select_name or self.project_var.get().strip()
        if target_name and target_name in project_names:
            self._apply_project_selection(target_name)
        elif project_names:
            self._apply_project_selection(project_names[0])
        else:
            self.project_var.set("")
            self.selected_project_name = ""
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            self._persist_gui_state()
            self._refresh_run_context()

    def _on_project_changed(self, project_name: str) -> None:
        self._apply_project_selection(project_name)

    def _apply_project_selection(self, project_name: str, *, update_conversation: bool = True) -> None:
        if not project_name:
            self.selected_project_name = ""
            self.project_inputs_var.set("")
            self.project_outputs_var.set("")
            conversation = self._current_conversation()
            if update_conversation and conversation is not None:
                conversation.project_name = ""
                conversation.touch()
                self._refresh_conversation_list()
                self._save_conversations()
            self._persist_gui_state()
            self._refresh_run_context()
            return
        project = self.workspace_manager.get_project(project_name)
        project.inputs_dir.mkdir(parents=True, exist_ok=True)
        project.outputs_dir.mkdir(parents=True, exist_ok=True)
        self.project_var.set(project.name)
        self.selected_project_name = project.name
        self.project_inputs_var.set(str(project.inputs_dir))
        self.project_outputs_var.set(str(project.outputs_dir))
        self.last_output_dir = project.outputs_dir
        conversation = self._current_conversation()
        if update_conversation and conversation is not None:
            conversation.project_name = project.name
            conversation.touch()
            self._refresh_conversation_list()
            self._save_conversations()
        self._persist_gui_state()
        self._refresh_run_context()

    def _create_project(self) -> None:
        dialog = ctk.CTkInputDialog(text="Enter a novel/project name:", title="New Project")
        project_name = dialog.get_input()
        if project_name in (None, ""):
            return
        try:
            project = self.workspace_manager.create_project(project_name)
        except ValueError as exc:
            messagebox.showwarning("New Project", str(exc))
            return
        self._refresh_projects(select_name=project.name)
        messagebox.showinfo("New Project", f"Created project folder:\n{project.root}")

    def _toggle_api_key_visibility(self) -> None:
        self.api_key_entry.configure(show="" if self.show_api_key_var.get() else "*")

    def _refresh_api_key_placeholder(self) -> None:
        self.api_key_entry.configure(placeholder_text=f"{self.provider_var.get().upper()} API key")

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
        selected = filedialog.askdirectory(title="Choose workspace root")
        if selected:
            self.workspace_root_var.set(selected)
            self._refresh_projects(select_name=self.project_var.get().strip())

    def _browse_input_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose input file",
            initialdir=self._preferred_input_directory(),
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if selected:
            self._submit_chat_input(selected)

    def _browse_input_folder(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose input folder",
            initialdir=self._preferred_input_directory(),
        )
        if selected:
            self._submit_chat_input(selected)

    def _browse_output_folder(self) -> None:
        selected = filedialog.askdirectory(title="Choose fallback output folder")
        if selected:
            self.output_path_var.set(selected)
            self._persist_gui_state()
            self._refresh_run_context()

    def _open_project_inputs_folder(self) -> None:
        project = self._active_project()
        if project is None:
            messagebox.showwarning("Project Inputs", "Choose or create a project first.")
            return
        project.inputs_dir.mkdir(parents=True, exist_ok=True)
        self._open_path(project.inputs_dir)

    def _open_project_folder(self) -> None:
        project = self._active_project()
        if project is None:
            messagebox.showwarning("Open Project Folder", "Choose or create a project first.")
            return
        project.root.mkdir(parents=True, exist_ok=True)
        self._open_path(project.root)

    def _open_output_folder(self) -> None:
        target = self.last_output_dir or self._effective_output_root()
        target_path = Path(target).expanduser().resolve()
        if not target_path.exists():
            messagebox.showwarning("Open Output Folder", f"Path does not exist:\n{target_path}")
            return
        self._open_path(target_path)

    def _open_path(self, path: Path) -> None:
        if not path.exists():
            messagebox.showwarning("Open Path", f"Path does not exist:\n{path}")
            return
        opener = getattr(os, "startfile", None)
        if callable(opener):
            opener(path)  # type: ignore[misc]
        else:
            messagebox.showinfo("Open Path", str(path))

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
            raise ValueError("Please reply with a listed bible number.")
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
            raise ValueError("That path does not exist.")
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
        self.status_var.set("Copied result to clipboard.")

    def _save_output_card_as(self, card: GuiOutputCard) -> None:
        if not card.path.exists():
            messagebox.showwarning("Save As", f"Referenced output file no longer exists:\n{card.path}")
            return
        selected = filedialog.asksaveasfilename(
            title="Save output as",
            initialfile=card.path.name,
        )
        if not selected:
            return
        shutil.copy2(card.path, selected)
        self.status_var.set(f"Saved copy to {selected}")

    def _preview_output_card(self, card: GuiOutputCard) -> None:
        preview_text = self._load_output_text(card.path)
        if not preview_text:
            messagebox.showinfo("Preview", f"No text preview is available for:\n{card.path}")
            return
        preview_window = ctk.CTkToplevel(self)
        preview_window.title(card.title)
        preview_window.geometry("760x520")
        preview_window.grid_columnconfigure(0, weight=1)
        preview_window.grid_rowconfigure(0, weight=1)

        textbox = ctk.CTkTextbox(preview_window, wrap="word")
        textbox.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
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

    def _build_workflow_summary(self, skill: GuiSkillOption) -> str:
        parts: list[str] = []
        if skill.startup_mode == "explicit_step_selection":
            parts.append("You will choose the starting step during the chat.")
        elif skill.allow_auto_route:
            parts.append("The app can route to the default starting step automatically.")
        if skill.supports_text_input:
            parts.append("You can ask questions or provide a short brief directly in chat.")
        parts.append("Use the conversation below to provide inputs step by step.")
        return self._shorten_text(" ".join(parts), limit=260)

    def _build_input_expectation(self, skill: GuiSkillOption) -> str:
        input_parts: list[str] = []
        if skill.supports_file_input:
            input_parts.append("file")
        if skill.supports_folder_input:
            input_parts.append("folder")
        if skill.supports_text_input:
            input_parts.append("brief text")

        if input_parts:
            joined = ", ".join(input_parts)
        else:
            joined = "workflow input"

        extensions = ", ".join(skill.input_extensions[:4]) if skill.input_extensions else "supported files"
        return self._shorten_text(f"Input: Send a {joined}. Supported source types: {extensions}.", limit=220)

    def _build_output_expectation(self, skill: GuiSkillOption) -> str:
        output_hints = {
            "novel_adaptation_plan": "Workflow output: Writes an adaptation-plan package for downstream scripting.",
            "novel_to_drama_script": "Workflow output: Writes episode script files for the selected episode range or mode.",
            "rewriting": "Workflow output: Writes refresh bible assets and/or rewritten script text into the output folder.",
            "story_creation": "Workflow output: Writes an original story package and planning documents.",
            "large_novel_processor": "Workflow output: Writes chapters, chunks, and an index for downstream use.",
            "recap_analysis": "Workflow output: Writes a recap-fit analysis report.",
            "recap_production": "Workflow output: Writes recap script, asset, and image-config materials.",
            "novel2script": "Workflow output: Writes the multi-step script-production deliverables for this run.",
        }
        return self._shorten_text(
            output_hints.get(
                skill.skill_id,
                "Workflow output: Writes generated files into the active output folder for this project.",
            ),
            limit=220,
        )

    def _build_initial_conversation_message(self, skill: GuiSkillOption, project_name: str) -> str:
        output_root = self._effective_output_root()
        lines = [
            skill.display_name,
            "",
            skill.description.strip() or "This workflow is ready to run.",
            self._build_workflowSummary_for_intro(skill),
            self._build_input_expectation(skill),
            self._build_output_expectation(skill),
            f"Project: {project_name or 'No active project'}",
            f"Output: {output_root}",
        ]
        return "\n".join(line for line in lines if line is not None).strip()

    def _build_workflowSummary_for_intro(self, skill: GuiSkillOption) -> str:
        startup_note = ""
        if skill.startup_mode == "explicit_step_selection":
            startup_note = "You will choose the starting step during the chat."
        elif skill.allow_auto_route:
            startup_note = "The app can route to the default starting step automatically."
        if skill.supports_text_input:
            extra = "You can ask questions or provide a short brief directly in chat."
            return " ".join(part for part in (startup_note, extra) if part).strip()
        return startup_note.strip()

    def _shorten_text(self, text: str, *, limit: int = 90) -> str:
        cleaned = " ".join(text.split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[:limit].rstrip() + "..."

    def _clear_chat_input(self) -> None:
        self.chat_input.delete("1.0", "end")

    def _scroll_chat_to_end(self) -> None:
        canvas = getattr(self.chat_history, "_parent_canvas", None)
        if canvas is None:
            return
        self.after(25, lambda: canvas.yview_moveto(1.0))

    def _on_send_shortcut(self, _event: Any) -> str:
        self._submit_chat_input()
        return "break"

    def _on_newline_shortcut(self, _event: Any) -> str:
        return None
