# CLCE

CLCE (Command Line Code Editor) is a lightweight, full-screen code editor for your terminal.

## Run

```powershell
python -m pip install -e .
clce path\to\file.py
```

You can also start with a blank `untitled.txt` buffer by running `clce` without a path.

## Keys

| Key | Action |
| --- | --- |
| `F2` | Save as (choose path and format) |
| `F3` | Save (choose path and format) |
| `F4` | Open a file |
| `F5` | Find text |
| `Esc` | Back from a popup or quit from the editor |

Syntax highlighting is selected from the file extension. The editor uses UTF-8 for file input and output.
Both save commands open a dialog where you can choose a destination path and file extension, such as `py`, `js`, or `txt`.