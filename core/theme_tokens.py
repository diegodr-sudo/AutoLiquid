"""Tokens visuais compartilhados pela interface."""

STEP_COLORS = ["#4f46e5", "#0f766e", "#c2410c", "#1d4ed8", "#be185d"]
LISTA_TEMAS = ["claro", "navy", "colorido"]

STATUS_STYLE = {
    "aguardando": ("Aguardando", "#9ca3af", "transparent"),
    "executando": ("Executando", "#d97706", "transparent"),
    "sucesso": ("Concluído", "#059669", "transparent"),
    "alerta": ("Com alertas", "#d97706", "transparent"),
    "pulado": ("Pulado", "#9ca3af", "transparent"),
    "erro": ("Erro", "#dc2626", "transparent"),
}

TC = {
    "claro": {
        "bg": "#f5f6f8", "card": "#ffffff", "card_alt": "#f8fafc",
        "border": "#e2e5eb", "border_dim": "#edf0f4",
        "text": "#111827", "text2": "#1f2937",
        "muted": "#5a6478", "dim": "#8b95a5",
        "accent": "#4f46e5", "accent_h": "#4338ca",
        "surface": "#eef0f4",
        "green": "#059669", "yellow": "#d97706", "red": "#dc2626",
        "info_fonte": "#0369a1", "info_nat": "#92400e", "info_ateste": "#065f46",
        "log_bg": "#1e293b", "log_fg": "#94a3b8",
    },
    "navy": {
        "bg": "#0d1117", "card": "#161b22", "card_alt": "#1c2128",
        "border": "#30363d", "border_dim": "#21262d",
        "text": "#e6edf3", "text2": "#c9d1d9",
        "muted": "#8b949e", "dim": "#6e7681",
        "accent": "#6366f1", "accent_h": "#4f46e5",
        "surface": "#010409",
        "green": "#3fb950", "yellow": "#d29922", "red": "#f85149",
        "info_fonte": "#a5f3fc", "info_nat": "#fde68a", "info_ateste": "#6ee7b7",
        "log_bg": "#010409", "log_fg": "#8b949e",
    },
    "colorido": {
        "bg": "#faf5ff", "card": "#ffffff", "card_alt": "#f5f3ff",
        "border": "#ddd6fe", "border_dim": "#ede9fe",
        "text": "#1e1b4b", "text2": "#312e81",
        "muted": "#6b21a8", "dim": "#7c3aed",
        "accent": "#7c3aed", "accent_h": "#6d28d9",
        "surface": "#ede9fe",
        "green": "#059669", "yellow": "#d97706", "red": "#dc2626",
        "info_fonte": "#0e7490", "info_nat": "#92400e", "info_ateste": "#065f46",
        "log_bg": "#2d1b69", "log_fg": "#c4b5fd",
    },
}
