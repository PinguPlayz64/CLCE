"""CLCE terminal code editor."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from prompt_toolkit import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import ConditionalContainer, VSplit
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.shortcuts import input_dialog, yes_no_dialog
from prompt_toolkit.styles import Style, merge_styles
from prompt_toolkit.styles.pygments import style_from_pygments_cls
from prompt_toolkit.widgets import Button, Label, TextArea
from pygments.lexers import TextLexer, get_lexer_for_filename
from pygments.styles import get_style_by_name
from pygments.util import ClassNotFound


def read_file(path: Path) -> str:
    """Read a UTF-8 file, or return an empty buffer for a new path."""
    if path.is_dir():
        raise IsADirectoryError(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_file(path: Path, text: str) -> None:
    """Write text to a UTF-8 file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _lexer_for(path: Path) -> PygmentsLexer:
    try:
        lexer = get_lexer_for_filename(path.name)
    except ClassNotFound:
        lexer = TextLexer()
    return PygmentsLexer(lexer.__class__)


class Editor:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path.expanduser() if path else Path("untitled.txt")
        self.text_area = TextArea(
            text=read_file(self.path),
            lexer=_lexer_for(self.path),
            line_numbers=True,
            scrollbar=True,
            wrap_lines=False,
        )
        self.save_as_active = False
        self.save_as_area = TextArea(
            text="",
            multiline=False,
            wrap_lines=False,
            accept_handler=self._accept_save_as,
        )
        self.save_format_area = TextArea(
            text="",
            multiline=False,
            wrap_lines=False,
            accept_handler=self._accept_save_as,
        )
        self.save_as_ok_button = Button(text="OK", handler=self._submit_save_as)
        self.save_as_cancel_button = Button(
            text="Cancel",
            handler=self._cancel_save_as,
        )
        self.saved_text = self.text_area.text
        self.status_message = ""
        self.bindings = self._make_bindings()
        editor_screen = HSplit(
            [
                Window(
                    FormattedTextControl(self._title),
                    height=1,
                    style="class:title",
                ),
                self.text_area,
                Window(
                    FormattedTextControl(self._status),
                    height=1,
                    style="class:status",
                ),
            ]
        )
        save_screen = HSplit(
            [
                Window(
                    FormattedTextControl(self._save_title),
                    height=1,
                    style="class:title",
                ),
                Window(height=1),
                Label(text="Save to (path):", dont_extend_height=True),
                self.save_as_area,
                Window(height=1),
                Label(
                    text="Format / extension (py, txt, js, json, etc.):",
                    dont_extend_height=True,
                ),
                self.save_format_area,
                Window(),
                VSplit(
                    [
                        Window(),
                        self.save_as_ok_button,
                        Window(width=4),
                        self.save_as_cancel_button,
                        Window(),
                    ],
                    height=1,
                ),
                Window(
                    FormattedTextControl(self._save_status),
                    height=1,
                    style="class:status",
                ),
            ]
        )
        self.app = Application(
            layout=Layout(
                HSplit(
                    [
                        ConditionalContainer(
                            content=editor_screen,
                            filter=Condition(lambda: not self.save_as_active),
                        ),
                        ConditionalContainer(
                            content=save_screen,
                            filter=Condition(lambda: self.save_as_active),
                        ),
                    ]
                ),
                focused_element=self.text_area,
            ),
            key_bindings=self.bindings,
            full_screen=True,
            mouse_support=True,
            style=merge_styles(
                [
                    style_from_pygments_cls(get_style_by_name("monokai")),
                    Style.from_dict(
                        {
                            "title": "bg:#153b3d #f3f7f6 bold",
                            "status": "bg:#153b3d #f3f7f6",
                            "status.key": "bg:#153b3d #85e0c1 bold",
                        }
                    ),
                ]
            ),
        )

    @property
    def is_dirty(self) -> bool:
        return self.text_area.text != self.saved_text

    def _title(self) -> list[tuple[str, str]]:
        marker = " *" if self.is_dirty else ""
        return [("class:title", f"  CLCE  |  {self.path}{marker}")]

    def _status(self) -> list[tuple[str, str]]:
        document = self.text_area.buffer.document
        position = f"Ln {document.cursor_position_row + 1}, Col {document.cursor_position_col + 1}"
        message = f"  {self.status_message}" if self.status_message else ""
        return [
            ("class:status", f"  {position}{message}"),
            ("class:status.key", "   F2 Save As   F3 Save   F4 Open   F5 Find   Esc Back/Quit  "),
        ]

    def _save_title(self) -> list[tuple[str, str]]:
        return [("class:title", f"  CLCE  |  {self.save_dialog_title}")]

    def _save_status(self) -> list[tuple[str, str]]:
        message = self.status_message or "Enter: save    Esc: return to editor"
        return [("class:status", f"  {message}")]

    def _make_bindings(self) -> KeyBindings:
        bindings = KeyBindings()

        @bindings.add("f3", filter=Condition(lambda: not self.save_as_active))
        def save(event) -> None:
            self._begin_save_dialog("Save")

        @bindings.add("f2", filter=Condition(lambda: not self.save_as_active))
        def save_as(event) -> None:
            self._begin_save_dialog("Save as")

        @bindings.add("f4", filter=Condition(lambda: not self.save_as_active))
        async def open_file(event) -> None:
            await self._open()

        @bindings.add("f5", filter=Condition(lambda: not self.save_as_active))
        async def find(event) -> None:
            await self._find()

        @bindings.add("escape", filter=Condition(lambda: self.save_as_active))
        def cancel_save_as(event) -> None:
            self._cancel_save_as()

        @bindings.add("escape", filter=Condition(lambda: not self.save_as_active))
        async def quit_editor(event) -> None:
            if not self.is_dirty:
                self._exit_if_not_done(event.app)
                return
            save_changes = await self._ask_yes_no(
                title="Unsaved changes",
                text="Save changes before quitting?",
            )
            if save_changes is None:
                return
            if save_changes and not self._save():
                return
            self._exit_if_not_done(event.app)

        return bindings

    @staticmethod
    def _exit_if_not_done(app) -> None:
        if not app.is_done:
            app.exit()

    @staticmethod
    def _bind_escape_to_cancel(dialog_app, cancel_result) -> None:
        bindings = KeyBindings()

        @bindings.add("escape")
        def cancel_dialog(event) -> None:
            if not dialog_app.is_done:
                dialog_app.exit(result=cancel_result)

        dialog_app.key_bindings = merge_key_bindings(
            [dialog_app.key_bindings, bindings]
        )

    async def _ask_yes_no(self, title: str, text: str) -> bool | None:
        dialog_app = yes_no_dialog(title=title, text=text)
        self._bind_escape_to_cancel(dialog_app, None)
        return await dialog_app.run_async()

    async def _ask_input(self, title: str, text: str) -> str | None:
        dialog_app = input_dialog(title=title, text=text)
        self._bind_escape_to_cancel(dialog_app, None)
        return await dialog_app.run_async()

    def _save(self) -> bool:
        try:
            write_file(self.path, self.text_area.text)
        except OSError as error:
            self.status_message = f"Could not save: {error}"
            return False
        self.saved_text = self.text_area.text
        self.status_message = f"Saved {self.path}"
        return True

    def _begin_save_dialog(self, title: str) -> None:
        self.save_dialog_title = title
        self.save_as_area.text = str(self.path)
        self.save_format_area.text = self.path.suffix.lstrip(".") or "txt"
        self.save_as_active = True
        self.app.layout.focus(self.save_as_area)

    def _accept_save_as(self, buffer) -> bool:
        self.app.layout.focus(self.save_as_ok_button)
        return True

    def _submit_save_as(self) -> None:
        selected = self.save_as_area.text.strip()
        file_format = self.save_format_area.text.strip().strip(".")
        if not file_format or any(char in file_format for char in '/\\:*?"<>|'):
            self.status_message = "Enter a valid file extension"
            self.app.layout.focus(self.save_format_area)
            return
        if not selected:
            self.status_message = "Enter a file path"
            self.app.layout.focus(self.save_as_area)
            return

        path = Path(selected).expanduser()
        try:
            path = path.with_suffix(f".{file_format}")
        except ValueError:
            self.status_message = "Enter a valid file path"
            self.app.layout.focus(self.save_as_area)
            return

        self.save_as_active = False
        self.app.layout.focus(self.text_area)
        self.path = path
        self.text_area.lexer = _lexer_for(self.path)
        self._save()

    def _cancel_save_as(self) -> None:
        self.save_as_active = False
        self.app.layout.focus(self.text_area)
        self.status_message = "Save as cancelled"

    async def _open(self) -> None:
        selected = await self._ask_input(
            title="Open file",
            text="File path:",
        )
        if not selected:
            return
        path = Path(selected).expanduser()
        try:
            text = read_file(path)
        except (OSError, UnicodeError) as error:
            self.status_message = f"Could not open: {error}"
            return
        if self.is_dirty:
            discard = await self._ask_yes_no(
                title="Unsaved changes",
                text="Discard the current changes and open another file?",
            )
            if not discard:
                return
        self.path = path
        self.text_area.text = text
        self.text_area.lexer = _lexer_for(path)
        self.saved_text = text
        self.status_message = f"Opened {path}"

    async def _find(self) -> None:
        query = await self._ask_input(
            title="Find",
            text="Search for:",
        )
        if not query:
            return
        text = self.text_area.text
        start = self.text_area.buffer.cursor_position + 1
        match = text.find(query, start)
        if match < 0:
            match = text.find(query, 0, start)
        if match < 0:
            self.status_message = f"Not found: {query}"
            return
        self.text_area.buffer.cursor_position = match
        self.status_message = f"Found: {query}"

    def run(self) -> None:
        self.app.run()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clce",
        description="Edit code files in your terminal.",
    )
    parser.add_argument("file", nargs="?", type=Path, help="file to open or create")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        Editor(args.file).run()
    except (OSError, UnicodeError) as error:
        parser.error(str(error))
    return 0


__all__ = ["Editor", "build_parser", "main", "read_file", "write_file"]