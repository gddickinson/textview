"""Named color palettes used throughout the viewer.

Each theme provides background/foreground/selection/current-line colors plus
the name of a Pygments style to pair with for syntax highlighting.
"""

THEMES = {
    "Light": {
        "bg": "#ffffff",
        "fg": "#1f1f1f",
        "selection_bg": "#cce4ff",
        "selection_fg": "#000000",
        "current_line": "#f0f0f0",
        "line_number_bg": "#f5f5f5",
        "line_number_fg": "#888888",
        "accent": "#0a66c2",
        "pygments_style": "default",
    },
    "Dark": {
        "bg": "#1e1e1e",
        "fg": "#e6e6e6",
        "selection_bg": "#264f78",
        "selection_fg": "#ffffff",
        "current_line": "#2a2d2e",
        "line_number_bg": "#252526",
        "line_number_fg": "#808080",
        "accent": "#4ea3ff",
        "pygments_style": "monokai",
    },
    "Solarized Dark": {
        "bg": "#002b36",
        "fg": "#93a1a1",
        "selection_bg": "#073642",
        "selection_fg": "#fdf6e3",
        "current_line": "#073642",
        "line_number_bg": "#002b36",
        "line_number_fg": "#586e75",
        "accent": "#268bd2",
        "pygments_style": "solarized-dark",
    },
    "Solarized Light": {
        "bg": "#fdf6e3",
        "fg": "#586e75",
        "selection_bg": "#eee8d5",
        "selection_fg": "#073642",
        "current_line": "#eee8d5",
        "line_number_bg": "#fdf6e3",
        "line_number_fg": "#93a1a1",
        "accent": "#268bd2",
        "pygments_style": "solarized-light",
    },
    "Monokai": {
        "bg": "#272822",
        "fg": "#f8f8f2",
        "selection_bg": "#49483e",
        "selection_fg": "#f8f8f2",
        "current_line": "#3e3d32",
        "line_number_bg": "#272822",
        "line_number_fg": "#90908a",
        "accent": "#a6e22e",
        "pygments_style": "monokai",
    },
    "Dracula": {
        "bg": "#282a36",
        "fg": "#f8f8f2",
        "selection_bg": "#44475a",
        "selection_fg": "#f8f8f2",
        "current_line": "#44475a",
        "line_number_bg": "#282a36",
        "line_number_fg": "#6272a4",
        "accent": "#bd93f9",
        "pygments_style": "dracula",
    },
    "Nord": {
        "bg": "#2e3440",
        "fg": "#d8dee9",
        "selection_bg": "#434c5e",
        "selection_fg": "#eceff4",
        "current_line": "#3b4252",
        "line_number_bg": "#2e3440",
        "line_number_fg": "#4c566a",
        "accent": "#88c0d0",
        "pygments_style": "nord",
    },
    "Sepia": {
        "bg": "#f4ecd8",
        "fg": "#5b4636",
        "selection_bg": "#e8d8b8",
        "selection_fg": "#3a2b20",
        "current_line": "#ebe2cc",
        "line_number_bg": "#ede4cc",
        "line_number_fg": "#8a7a60",
        "accent": "#a05a2c",
        "pygments_style": "tango",
    },
    "High Contrast": {
        "bg": "#000000",
        "fg": "#ffffff",
        "selection_bg": "#ffd700",
        "selection_fg": "#000000",
        "current_line": "#1a1a1a",
        "line_number_bg": "#000000",
        "line_number_fg": "#ffff00",
        "accent": "#00ff00",
        "pygments_style": "github-dark",
    },
    "GitHub": {
        "bg": "#ffffff",
        "fg": "#24292e",
        "selection_bg": "#c8e1ff",
        "selection_fg": "#000000",
        "current_line": "#f6f8fa",
        "line_number_bg": "#ffffff",
        "line_number_fg": "#959da5",
        "accent": "#0366d6",
        "pygments_style": "default",
    },
}


def theme_names():
    return list(THEMES.keys())


def get_theme(name):
    return THEMES.get(name, THEMES["Solarized Dark"])
