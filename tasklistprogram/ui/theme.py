"""Centralized color palettes and theming for the Tkinter UI.

`app.py` calls :func:`apply_theme`; `TaskListView` applies row/tag colors from
the active palette. Dark mode uses the ``clam`` ttk theme. Some classic widgets
in popup dialogs may remain light.
"""

LIGHT = {
    "name": "light",
    "window_bg": "#f4f5f7",
    "tree_bg": "#ffffff",
    "tree_fg": "#1a1a1a",
    "field_bg": "#ffffff",
    "selection_bg": "#2f6fdb",
    "selection_fg": "#ffffff",
    "status_fg": "#555555",
    "muted_fg": "#888888",
    "group_bg": "#cfd4da",
    "group_fg": "#1a1a1a",
    # Priority row backgrounds — soft tints so a dense list stays calm; the colored
    # emoji in the PRIO column carries the strong signal. (text uses tree_fg).
    "prio": {
        "U": "#ffd6d6", "H": "#ffe9e9", "M": "#fff1de",
        "L": "#fbf7d6", "D": "#e8f6ec", "X": "#e9eefb",
    },
    # Entry/button colors are left to the native theme in light mode.
    "entry_bg": "#ffffff",
    "entry_fg": "#1a1a1a",
    "button_bg": "#e6e8ec",
    "button_fg": "#1a1a1a",
    "heading_bg": "#e6e8ec",
    "heading_fg": "#1a1a1a",
}

DARK = {
    "name": "dark",
    "window_bg": "#1e1f22",
    "tree_bg": "#26282c",
    "tree_fg": "#e6e6e6",
    "field_bg": "#26282c",
    "selection_bg": "#3b6fb5",
    "selection_fg": "#ffffff",
    "status_fg": "#9aa0a6",
    "muted_fg": "#8a8a8a",
    "group_bg": "#3a3d42",
    "group_fg": "#f0f0f0",
    # Darker, desaturated priority backgrounds that still read as the right hue
    # under light text.
    "prio": {
        "U": "#7a2e2e", "H": "#5e3535", "M": "#5e4a2c",
        "L": "#555227", "D": "#2e4a30", "X": "#2b4760",
    },
    "entry_bg": "#2f3236",
    "entry_fg": "#e6e6e6",
    "button_bg": "#34373c",
    "button_fg": "#e6e6e6",
    "heading_bg": "#2f3236",
    "heading_fg": "#e6e6e6",
}

PALETTES = {"light": LIGHT, "dark": DARK}


def get_palette(name: str) -> dict:
    return PALETTES.get((name or "light").lower(), LIGHT)


def apply_theme(root, style, palette: dict, native_theme: str) -> None:
    """Apply a palette to the shared ttk styles.

    The caller (`app.py`) owns the root window background and classic-widget colors;
    here we only switch the ttk theme and configure ttk widget styles.
    """
    if palette["name"] == "dark":
        style.theme_use("clam")
        bg = palette["window_bg"]
        style.configure(".", background=bg, foreground=palette["tree_fg"])
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=palette["tree_fg"])
        style.configure("TCheckbutton", background=bg, foreground=palette["tree_fg"])
        style.map("TCheckbutton", background=[("active", bg)])
        style.configure("TButton", background=palette["button_bg"], foreground=palette["button_fg"])
        style.map("TButton", background=[("active", palette["heading_bg"])])
        style.configure("TEntry", fieldbackground=palette["entry_bg"], foreground=palette["entry_fg"])
        style.configure("TSpinbox", fieldbackground=palette["entry_bg"], foreground=palette["entry_fg"])
        style.configure("TCombobox", fieldbackground=palette["entry_bg"],
                        foreground=palette["entry_fg"], background=palette["button_bg"])
        style.map("TCombobox", fieldbackground=[("readonly", palette["entry_bg"])])
        style.configure("TSeparator", background=palette["heading_bg"])
    else:
        style.theme_use(native_theme)

    style.configure(
        "Treeview",
        background=palette["tree_bg"],
        fieldbackground=palette["field_bg"],
        foreground=palette["tree_fg"],
        rowheight=24,
    )
    style.configure("Treeview.Heading", font=("", 9, "bold"))
    style.map(
        "Treeview",
        background=[("selected", palette["selection_bg"])],
        foreground=[("selected", palette["selection_fg"])],
    )
