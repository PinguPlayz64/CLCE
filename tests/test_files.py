import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from clce import Editor, read_file, write_file
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit
from prompt_toolkit.keys import Keys


class FileOperationTests(unittest.TestCase):
    def test_read_missing_file_returns_empty_buffer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new.py"
            self.assertEqual(read_file(path), "")

    def test_write_file_creates_parent_and_round_trips_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "sample.py"
            content = "print('hello')\n"
            write_file(path, content)
            self.assertEqual(read_file(path), content)

    def test_read_directory_fails_clearly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(IsADirectoryError):
                read_file(Path(directory))

    def test_editor_initializes_clean_and_tracks_edits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            editor = Editor(Path(directory) / "sample.py")
            self.assertFalse(editor.is_dirty)
            editor.text_area.text = "print('ready')"
            self.assertTrue(editor.is_dirty)

    def test_editor_commands_use_function_keys(self) -> None:
        editor = Editor()
        key_by_action = {
            binding.handler.__name__: binding.keys[0]
            for binding in editor.bindings.bindings
        }
        self.assertEqual(key_by_action["save_as"], Keys.F2)
        self.assertEqual(key_by_action["save"], Keys.F3)
        self.assertEqual(key_by_action["open_file"], Keys.F4)
        self.assertEqual(key_by_action["find"], Keys.F5)
        self.assertEqual(key_by_action["quit_editor"], Keys.Escape)
        self.assertEqual(key_by_action["cancel_save_as"], Keys.Escape)

    def test_escape_cancels_input_dialog(self) -> None:
        class DialogApp:
            is_done = False
            key_bindings = KeyBindings()
            exit_result = "not cancelled"

            def exit(self, result=None) -> None:
                self.is_done = True
                self.exit_result = result

        dialog_app = DialogApp()
        Editor._bind_escape_to_cancel(dialog_app, None)
        escape_binding = next(
            binding
            for binding in dialog_app.key_bindings.bindings
            if binding.handler.__name__ == "cancel_dialog"
        )
        escape_binding.handler(SimpleNamespace())

        self.assertTrue(dialog_app.is_done)
        self.assertIsNone(dialog_app.exit_result)

    def test_escape_cancels_quit_confirmation_without_exiting(self) -> None:
        editor = Editor()
        editor.text_area.text = "unsaved changes"
        editor._ask_yes_no = AsyncMock(return_value=None)

        class App:
            is_done = False
            exit_calls = 0

            def exit(self) -> None:
                self.is_done = True
                self.exit_calls += 1

        app = App()
        quit_binding = next(
            binding
            for binding in editor.bindings.bindings
            if binding.handler.__name__ == "quit_editor"
        )
        asyncio.run(quit_binding.handler(SimpleNamespace(app=app)))

        self.assertEqual(app.exit_calls, 0)
        self.assertTrue(editor.is_dirty)

    def test_repeated_quit_exit_only_exits_once(self) -> None:
        editor = Editor()

        class App:
            is_done = False
            exit_calls = 0

            def exit(self) -> None:
                self.exit_calls += 1
                self.is_done = True

        app = App()
        editor._exit_if_not_done(app)
        editor._exit_if_not_done(app)
        self.assertEqual(app.exit_calls, 1)

    def test_editor_save_writes_buffer_and_clears_dirty_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.py"
            editor = Editor(path)
            editor.text_area.text = "print('saved')\n"
            self.assertTrue(editor._save())
            self.assertEqual(read_file(path), "print('saved')\n")
            self.assertFalse(editor.is_dirty)

    def test_save_dialog_saves_to_selected_path_and_format(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "renamed.py"
            editor = Editor()
            editor.text_area.text = "print('renamed')\n"
            editor._begin_save_dialog("Save as")
            editor.save_as_area.text = str(Path(directory) / "renamed.txt")
            editor.save_format_area.text = "py"
            editor._submit_save_as()

            self.assertEqual(editor.path, path)
            self.assertEqual(read_file(path), "print('renamed')\n")
            self.assertFalse(editor.is_dirty)

    def test_save_and_save_as_open_the_shared_destination_dialog(self) -> None:
        editor = Editor()
        binding_by_name = {
            binding.handler.__name__: binding
            for binding in editor.bindings.bindings
        }

        class Event:
            pass

        binding_by_name["save"].handler(Event())
        self.assertTrue(editor.save_as_active)
        self.assertEqual(editor.save_dialog_title, "Save")

        editor._cancel_save_as()
        binding_by_name["save_as"].handler(Event())
        self.assertTrue(editor.save_as_active)
        self.assertEqual(editor.save_dialog_title, "Save as")

    def test_save_dialog_uses_full_screen_editor_view(self) -> None:
        editor = Editor()
        editor._begin_save_dialog("Save")

        self.assertTrue(editor.app.full_screen)
        self.assertIsInstance(editor.app.layout.container, HSplit)

    def test_invalid_format_keeps_save_dialog_open(self) -> None:
        editor = Editor()
        editor._begin_save_dialog("Save")
        editor.save_as_area.text = "output.py"
        editor.save_format_area.text = "../py"

        editor._submit_save_as()

        self.assertTrue(editor.save_as_active)
        self.assertNotEqual(editor.path, Path("output.py"))

    def test_escape_cancels_save_as_without_quitting(self) -> None:
        editor = Editor()
        original_path = editor.path
        editor._begin_save_dialog("Save as")
        cancel_binding = next(
            binding
            for binding in editor.bindings.bindings
            if binding.handler.__name__ == "cancel_save_as"
        )
        cancel_binding.handler(None)

        self.assertFalse(editor.save_as_active)
        self.assertEqual(editor.path, original_path)


if __name__ == "__main__":
    unittest.main()