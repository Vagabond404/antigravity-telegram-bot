"""
ui_helpers.py - High-Fidelity Telegram Bot UI, Markdown & HTML Rendering Engine
Provides professional Markdown to Telegram HTML conversion, real-time tool & subagent block formatting,
expandable blockquotes, snake_case safety, table alignment, resilient HTML sanitisation,
and an ultra-intuitive multi-page Telegram Control Center for Antigravity CLI.
"""

import re
import html
import logging
from typing import List, Optional, Tuple, Dict, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger("ui_helpers")

_TG_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "s", "strike", "del", "u", "ins",
    "code", "pre", "a", "blockquote", "tg-spoiler", "span",
}


def h(text: str) -> str:
    """Safe HTML entity escape."""
    return html.escape(str(text), quote=False)


def strip_all_html(text: str) -> str:
    """Remove ALL HTML tags, returning clean plain text."""
    return re.sub(r"<[^>]+>", "", text)


def sanitize_telegram_html(text: str) -> str:
    """
    Sanitise HTML for Telegram's HTML parse mode.
    Balances unclosed tags and strips unsupported HTML tags.
    """
    if not text:
        return ""

    text = text.replace("<blockquote expandable>", "\x00BQE\x00")
    text = text.replace("</blockquote>", "\x00/BQE\x00")

    result = []
    open_stack = []
    i = 0
    length = len(text)

    while i < length:
        if text[i:].startswith("\x00BQE\x00"):
            result.append("<blockquote expandable>")
            open_stack.append("blockquote")
            i += 7
            continue
        if text[i:].startswith("\x00/BQE\x00"):
            result.append("</blockquote>")
            if "blockquote" in open_stack:
                open_stack.remove("blockquote")
            i += 8
            continue

        if text[i] == "<":
            j = text.find(">", i)
            if j == -1:
                result.append("&lt;")
                i += 1
                continue

            raw_tag = text[i + 1 : j].strip()

            if raw_tag.startswith("/"):
                tag_name = raw_tag[1:].strip().lower()
                if tag_name in _TG_ALLOWED_TAGS:
                    if tag_name in open_stack:
                        idx = len(open_stack) - 1 - list(reversed(open_stack)).index(tag_name)
                        for t in reversed(open_stack[idx:]):
                            result.append(f"</{t}>")
                        open_stack = open_stack[:idx]
                i = j + 1
                continue

            m = re.match(r"^([a-zA-Z][a-zA-Z0-9-]*)", raw_tag)
            if not m:
                result.append("&lt;")
                i += 1
                continue

            tag_name = m.group(1).lower()
            if tag_name not in _TG_ALLOWED_TAGS:
                i = j + 1
                continue

            if tag_name == "a":
                href_m = re.search(r'href=["\']([^"\']*)["\']', raw_tag)
                if href_m:
                    safe_href = html.escape(href_m.group(1), quote=True)
                    result.append(f'<a href="{safe_href}">')
                    open_stack.append("a")
            elif tag_name == "code":
                cls_m = re.search(r'class=["\']([^"\']*)["\']', raw_tag)
                if cls_m:
                    safe_cls = html.escape(cls_m.group(1), quote=True)
                    result.append(f'<code class="{safe_cls}">')
                else:
                    result.append("<code>")
                open_stack.append("code")
            elif tag_name == "tg-spoiler":
                result.append("<tg-spoiler>")
                open_stack.append("tg-spoiler")
            elif tag_name == "span" and "tg-spoiler" in raw_tag:
                result.append('<span class="tg-spoiler">')
                open_stack.append("span")
            else:
                result.append(f"<{tag_name}>")
                if not raw_tag.endswith("/"):
                    open_stack.append(tag_name)

            i = j + 1
        else:
            result.append(text[i])
            i += 1

    for tag in reversed(open_stack):
        result.append(f"</{tag}>")

    return "".join(result)


def truncate_telegram_html(text: str, max_length: int = 4000) -> str:
    if len(text) <= max_length:
        return text

    cut = text[:max_length]
    last_open = cut.rfind("<")
    last_close = cut.rfind(">")
    if last_open > last_close:
        cut = cut[:last_open]

    return sanitize_telegram_html(cut) + " <i>…</i>"


def _format_markdown_table(table_text: str) -> str:
    lines = [l.strip() for l in table_text.strip().split("\n") if l.strip()]
    if len(lines) < 2:
        return table_text

    rows = []
    for line in lines:
        if re.match(r"^\|?\s*[-:]+[-| :]*\|?$", line):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cols)

    if not rows:
        return table_text

    max_cols = max(len(r) for r in rows)
    col_widths = [0] * max_cols

    for r in rows:
        for idx, c in enumerate(r):
            col_widths[idx] = max(col_widths[idx], len(c))

    formatted_rows = []
    for idx, r in enumerate(rows):
        padded = [r[i].ljust(col_widths[i]) if i < len(r) else "".ljust(col_widths[i]) for i in range(max_cols)]
        line_str = " | ".join(padded)
        formatted_rows.append(line_str)
        if idx == 0 and len(rows) > 1:
            sep = "-+-".join("-" * col_widths[i] for i in range(max_cols))
            formatted_rows.append(sep)

    return f"<pre>{h(chr(10).join(formatted_rows))}</pre>"


def md_to_html(text: str) -> str:
    if not text:
        return ""

    code_blocks = []

    def _save_code_block(match):
        lang = (match.group(1) or "").strip().lower()
        code_content = match.group(2)
        idx = len(code_blocks)
        escaped_code = h(code_content.strip("\n"))
        if lang:
            tag = f'<pre><code class="language-{h(lang)}">{escaped_code}</code></pre>'
        else:
            tag = f"<pre>{escaped_code}</pre>"
        code_blocks.append(tag)
        return f"\x00CODEBLOCK_{idx}\x00"

    text = re.sub(r"```([a-zA-Z0-9_\-+]*)\n?(.*?)```", _save_code_block, text, flags=re.DOTALL)

    dangling_m = re.search(r"```([a-zA-Z0-9_\-+]*)\n?(.*?)$", text, flags=re.DOTALL)
    if dangling_m:
        lang = (dangling_m.group(1) or "").strip().lower()
        code_content = dangling_m.group(2)
        idx = len(code_blocks)
        escaped_code = h(code_content)
        if lang:
            tag = f'<pre><code class="language-{h(lang)}">{escaped_code}</code></pre>'
        else:
            tag = f"<pre>{escaped_code}</pre>"
        code_blocks.append(tag)
        text = text[: dangling_m.start()] + f"\x00CODEBLOCK_{idx}\x00"

    inline_codes = []

    def _save_inline_code(match):
        code_str = match.group(1)
        idx = len(inline_codes)
        inline_codes.append(f"<code>{h(code_str)}</code>")
        return f"\x00INLINECODE_{idx}\x00"

    text = re.sub(r"`([^`\n]+)`", _save_inline_code, text)

    table_blocks = []

    def _table_sub(match):
        idx = len(table_blocks)
        table_blocks.append(_format_markdown_table(match.group(0)))
        return f"\x00TABLE_{idx}\x00"

    text = re.sub(r"((?:^[ \t]*\|[^\n]+\|[ \t]*(?:\n|$)){2,})", _table_sub, text, flags=re.MULTILINE)
    text = re.sub(r"^[ \t]*(?:[-*_]){3,}[ \t]*$", "───────────────", text, flags=re.MULTILINE)

    processed_lines = []
    in_quote = False
    quote_lines = []

    for line in text.split("\n"):
        stripped = line.strip()

        if stripped.startswith("\x00TABLE_") and stripped.endswith("\x00"):
            if in_quote:
                quote_body = "\n".join(quote_lines)
                processed_lines.append(f"<blockquote>{_format_inlines(quote_body)}</blockquote>")
                quote_lines = []
                in_quote = False
            processed_lines.append(stripped)
            continue

        if stripped.startswith("&gt; "):
            stripped = "> " + stripped[5:]
        elif stripped == "&gt;":
            stripped = ">"

        if stripped.startswith("> ") or stripped == ">":
            in_quote = True
            quote_lines.append(stripped[2:] if stripped.startswith("> ") else "")
            continue
        else:
            if in_quote:
                quote_body = "\n".join(quote_lines)
                processed_lines.append(f"<blockquote>{_format_inlines(quote_body)}</blockquote>")
                quote_lines = []
                in_quote = False

        h1 = re.match(r"^#\s+(.+)$", line)
        h2 = re.match(r"^##\s+(.+)$", line)
        h3 = re.match(r"^###\s+(.+)$", line)
        h4 = re.match(r"^#{4,6}\s+(.+)$", line)

        if h1:
            processed_lines.append(f"\n<b>🔷 {_format_inlines(h1.group(1))}</b>")
        elif h2:
            processed_lines.append(f"\n<b>🔹 {_format_inlines(h2.group(1))}</b>")
        elif h3:
            processed_lines.append(f"\n<b>▪️ {_format_inlines(h3.group(1))}</b>")
        elif h4:
            processed_lines.append(f"\n<b>{_format_inlines(h4.group(1))}</b>")
        elif re.match(r"^[ \t]*[-*+][ \t]+", line):
            indent_len = len(line) - len(line.lstrip(" "))
            content = re.sub(r"^[ \t]*[-*+][ \t]+", "", line)
            bullet = "  ◦ " if indent_len >= 2 else "• "
            processed_lines.append(f"{bullet}{_format_inlines(content)}")
        elif re.match(r"^[ \t]*(\d+)\.[ \t]+", line):
            num_m = re.match(r"^[ \t]*(\d+)\.[ \t]+(.*)$", line)
            num = num_m.group(1)
            content = num_m.group(2)
            processed_lines.append(f"<b>{num}.</b> {_format_inlines(content)}")
        else:
            processed_lines.append(_format_inlines(line))

    if in_quote:
        quote_body = "\n".join(quote_lines)
        processed_lines.append(f"<blockquote>{_format_inlines(quote_body)}</blockquote>")

    result_text = "\n".join(processed_lines)

    for idx, inc in enumerate(inline_codes):
        result_text = result_text.replace(f"\x00INLINECODE_{idx}\x00", inc)
    for idx, cb in enumerate(code_blocks):
        result_text = result_text.replace(f"\x00CODEBLOCK_{idx}\x00", cb)
    for idx, tb in enumerate(table_blocks):
        result_text = result_text.replace(f"\x00TABLE_{idx}\x00", tb)

    result_text = re.sub(r"\n{3,}", "\n\n", result_text)
    return sanitize_telegram_html(result_text)


def _format_inlines(text: str) -> str:
    if not text:
        return ""

    link_placeholders = []

    def _save_link(m):
        label = m.group(1)
        url = m.group(2).strip()
        idx = len(link_placeholders)
        if url.startswith("file://"):
            clean_path = url.replace("file:///", "").replace("file://", "")
            link_placeholders.append(f"<code>{h(label)}</code>")
        elif url.startswith("http://") or url.startswith("https://"):
            link_placeholders.append(f'<a href="{h(url)}">{h(label)}</a>')
        else:
            link_placeholders.append(f"<code>{h(label)}</code>")
        return f"\x00LINK_{idx}\x00"

    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _save_link, text)

    url_placeholders = []

    def _save_url(m):
        raw_url = m.group(0)
        idx = len(url_placeholders)
        url_placeholders.append(f'<a href="{h(raw_url)}">{h(raw_url)}</a>')
        return f"\x00URL_{idx}\x00"

    text = re.sub(r"https?://[^\s<>\"']+", _save_url, text)

    text = h(text)

    text = re.sub(r"\*\*\*([^*\n]+)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"(?<!\w)___([^_\n]+)___(?!\w)", r"<b><i>\1</i></b>", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)__([^_\n]+)__(?!\w)", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", text)
    text = re.sub(r"\|\|([^|\n]+)\|\|", r"<tg-spoiler>\1</tg-spoiler>", text)

    for idx, u in enumerate(url_placeholders):
        text = text.replace(f"\x00URL_{idx}\x00", u)
    for idx, l in enumerate(link_placeholders):
        text = text.replace(f"\x00LINK_{idx}\x00", l)

    return text


TOOL_ICONS = {
    "run_command": "⚙️",
    "view_file": "📄",
    "write_to_file": "✏️",
    "replace_file_content": "✏️",
    "multi_replace_file_content": "✏️",
    "search_web": "🔍",
    "read_url_content": "🌐",
    "find_by_name": "📂",
    "grep_search": "🔎",
    "list_dir": "📁",
    "generate_image": "🎨",
    "invoke_subagent": "🤖",
    "define_subagent": "🧩",
    "manage_subagents": "🤖",
    "send_message": "💬",
    "call_mcp_tool": "🔌",
    "schedule": "⏰",
    "manage_task": "📋",
}


def format_tool_call_html(
    tool_name: str,
    args: Optional[dict] = None,
    result: Optional[str] = None,
    is_error: bool = False,
) -> str:
    icon = TOOL_ICONS.get(tool_name, "🔧")
    status = "❌" if is_error else ("✅" if result is not None else "⏳")
    args_parts = []
    if args:
        for k, v in list(args.items())[:3]:
            v_str = str(v)
            if len(v_str) > 80:
                v_str = v_str[:80] + "…"
            args_parts.append(f"<code>{h(k)}</code>: <i>{h(v_str)}</i>")
    args_html = "\n".join(args_parts)

    result_html = ""
    if result is not None:
        r = str(result).strip()
        if len(r) > 350:
            r = r[:350] + "…"
        result_html = f"\n<pre>{h(r)}</pre>"

    body = f"{icon} <b>{h(tool_name)}</b> {status}"
    if args_html:
        body += f"\n{args_html}"
    if result_html:
        body += result_html
    return f"<blockquote expandable>{body}</blockquote>"


def smart_split_html(text: str, max_length: int = 4000) -> List[str]:
    if not text:
        return ["<i>(Réponse vide)</i>"]

    text = sanitize_telegram_html(text)
    if len(text) <= max_length:
        return [text]

    chunks = []
    current_lines = []
    current_len = 0
    in_pre = False
    pre_lang = ""

    for line in text.split("\n"):
        line_len = len(line) + 1
        if "<pre" in line:
            in_pre = True
            m = re.search(r'class="language-([a-z0-9_-]+)"', line)
            pre_lang = m.group(1) if m else ""
        if "</pre>" in line:
            in_pre = False

        if current_len + line_len > max_length and current_lines:
            if in_pre:
                current_lines.append("</pre>")
            chunk = sanitize_telegram_html("\n".join(current_lines))
            chunks.append(chunk)
            current_lines = []
            current_len = 0
            if in_pre:
                opener = f'<pre><code class="language-{pre_lang}">' if pre_lang else "<pre>"
                current_lines.append(opener)
                current_len += len(opener) + 1

        current_lines.append(line)
        current_len += line_len

    if current_lines:
        if in_pre:
            current_lines.append("</pre>")
        chunk = sanitize_telegram_html("\n".join(current_lines))
        chunks.append(chunk)

    return chunks or [sanitize_telegram_html(text[:max_length])]


# =============================================================================
# Interactive Telegram Control Center Keyboards
# =============================================================================

def format_settings_summary_html(settings: dict) -> str:
    agent_name = settings.get("agent_name", "Antigravity Agent")
    model = settings.get("model", "gemini-4-argon-medium")
    effort = settings.get("effort", "auto")
    mode = settings.get("mode", "auto-approve")
    sandbox = bool(settings.get("sandbox", False))
    multi_agent = bool(settings.get("multi_agent", True))
    agent_prof = settings.get("agent_profile", "") or "Principal (Auto)"
    verbosity = settings.get("verbosity", "normal")
    auto_files = bool(settings.get("auto_send_files", True))
    ws = settings.get("workspace_dir", "")
    extra_dirs = settings.get("extra_dirs", []) or []
    timeout = int(settings.get("timeout", 600))
    custom_instr = settings.get("custom_instructions", "").strip()

    if timeout <= 0:
        t_str = "♾️ Infini (Sans limite)"
    elif timeout >= 3600:
        t_str = f"{timeout // 3600}h" if timeout % 3600 == 0 else f"{timeout / 3600:.1f}h"
    else:
        t_str = f"{timeout // 60} min"

    lines = [
        f"🎛️ <b>Centre de Contrôle — {h(agent_name)}</b>\n",
        f"• 🧠 <b>Modèle IA :</b> <code>{h(model)}</code>",
        f"• 💡 <b>Réflexion (Effort) :</b> <code>{h(effort)}</code>",
        f"• 🛡️ <b>Mode d'exécution :</b> <code>{h(mode)}</code>",
        f"• 🤝 <b>Multi-Agents :</b> {'🟢 Activé' if multi_agent else '🔴 Désactivé'} (Profil: <code>{h(agent_prof)}</code>)",
        f"• 📦 <b>Sandbox CLI :</b> {'🟢 Activé' if sandbox else '⚪ Désactivé'}",
        f"• ⏱️ <b>Timeout :</b> <code>{t_str}</code>",
        f"• 👁️ <b>Affichage Outils :</b> <code>{h(verbosity)}</code>",
        f"• 📤 <b>Envoi Auto Médias :</b> {'🟢 Oui' if auto_files else '🔴 Non'}",
        f"• 📁 <b>Workspace :</b> <code>{h(ws)}</code>" + (f" (+{len(extra_dirs)} rép.)" if extra_dirs else ""),
    ]
    if custom_instr:
        preview = custom_instr[:70] + ("…" if len(custom_instr) > 70 else "")
        lines.append(f"• 📌 <b>Instructions perso :</b> <i>{h(preview)}</i>")

    lines.append("\n<i>Cliquez sur une catégorie ci-dessous pour configurer l'agent en direct :</i>")
    return "\n".join(lines)


def get_settings_keyboard(settings: dict) -> InlineKeyboardMarkup:
    mode = settings.get("mode", "auto-approve")
    model = settings.get("model", "gemini-4-argon-medium")
    effort = settings.get("effort", "auto")
    timeout = int(settings.get("timeout", 600))
    sandbox = bool(settings.get("sandbox", False))
    multi_agent = bool(settings.get("multi_agent", True))
    verbosity = settings.get("verbosity", "normal")
    auto_files = bool(settings.get("auto_send_files", True))

    mode_label = {"auto-approve": "⚡ Autonome", "accept-edits": "✏️ Éditions", "plan": "📋 Plan"}.get(mode, mode)
    effort_label = {
        "auto": "🤖 Auto",
        "low": "⚡ Low",
        "medium": "⚖️ Medium",
        "high": "🧠 High",
        "xhigh": "🔥 XHigh",
        "max": "🚀 Max",
    }.get(effort, effort)
    verb_label = {"compact": "🧼 Compact", "normal": "⚖️ Normal", "detailed": "🔬 Détaillé"}.get(verbosity, verbosity)

    if timeout <= 0:
        timeout_label = "♾️ Infini"
    elif timeout >= 3600:
        timeout_label = f"{timeout // 3600}h"
    else:
        timeout_label = f"{timeout // 60}m"

    keyboard = [
        [InlineKeyboardButton(f"🧠 Modèle : {model}", callback_data="menu_model")],
        [
            InlineKeyboardButton(f"💡 Effort : {effort_label}", callback_data="menu_effort"),
            InlineKeyboardButton(f"🛡️ Mode : {mode_label}", callback_data="menu_mode"),
        ],
        [
            InlineKeyboardButton(f"🤝 Multi-Agents : {'ON ✅' if multi_agent else 'OFF ❌'}", callback_data="menu_agents"),
            InlineKeyboardButton(f"📦 Sandbox : {'ON 🔒' if sandbox else 'OFF 🔓'}", callback_data="toggle_sandbox"),
        ],
        [
            InlineKeyboardButton(f"⏱️ Timeout : {timeout_label}", callback_data="menu_timeout"),
            InlineKeyboardButton(f"👁️ Vue : {verb_label}", callback_data="menu_verbosity"),
        ],
        [
            InlineKeyboardButton(f"📤 Auto-Médias : {'ON ✅' if auto_files else 'OFF ❌'}", callback_data="toggle_autofiles"),
            InlineKeyboardButton("📁 Workspace & Dossiers", callback_data="menu_workspace"),
        ],
        [
            InlineKeyboardButton("🔌 Serveurs MCP", callback_data="menu_mcp"),
            InlineKeyboardButton("🧩 Plugins CLI", callback_data="menu_plugins"),
        ],
        [
            InlineKeyboardButton("🌐 Remote Control", callback_data="menu_remote"),
            InlineKeyboardButton("💬 Sessions & Historique", callback_data="menu_sessions"),
        ],
        [
            InlineKeyboardButton("✏️ Personnaliser Agent", callback_data="menu_persona"),
            InlineKeyboardButton("🕹️ Commandes (/commands)", callback_data="menu_commands"),
        ],
        [
            InlineKeyboardButton("⬆️ Maj Antigravity CLI", callback_data="cli_update"),
            InlineKeyboardButton("👥 Utilisateurs", callback_data="auth:refresh"),
        ],
        [
            InlineKeyboardButton("🔄 Par défaut", callback_data="reset_settings"),
            InlineKeyboardButton("❌ Fermer", callback_data="close_menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_mode_selection_keyboard(current_mode: str) -> InlineKeyboardMarkup:
    modes = [
        ("auto-approve", "⚡ Autonome (--dangerously-skip-permissions)"),
        ("accept-edits", "✏️ Accepter Éditions (--mode accept-edits)"),
        ("plan", "📋 Planification seule (--mode plan)"),
    ]
    keyboard = []
    for mode_val, label in modes:
        check = " ✅" if mode_val == current_mode else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_mode:{mode_val}")])
    keyboard.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_model_selection_keyboard(
    current_model: str,
    available_models: Optional[List[Tuple[str, str]]] = None,
) -> InlineKeyboardMarkup:
    from agent_runner import get_cached_models
    models = available_models or get_cached_models()

    keyboard = []
    for mod_val, label in models:
        check = " ✅" if mod_val == current_model else ""
        display_btn = f"{label} ({mod_val}){check}" if label != mod_val else f"{mod_val}{check}"
        if len(display_btn) > 58:
            display_btn = f"{label[:45]}{check}"
        keyboard.append([InlineKeyboardButton(display_btn, callback_data=f"set_model:{mod_val}")])

    keyboard.append([InlineKeyboardButton("🔄 Rafraîchir depuis Antigravity CLI (agy models)", callback_data="refresh_models")])
    keyboard.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_effort_selection_keyboard(current_effort: str) -> InlineKeyboardMarkup:
    efforts = [
        ("auto", "🤖 Auto (Adapté automatiquement au modèle)"),
        ("low", "⚡ Rapide (low — direct & ultra-réactif)"),
        ("medium", "⚖️ Équilibré (medium — analyse standard)"),
        ("high", "🧠 Profond (high — réflexion avancée)"),
        ("xhigh", "🔥 Très Profond (xhigh — raisonnement intensif)"),
        ("max", "🚀 Maximum (max — capacité de réflexion maximale)"),
    ]
    keyboard = []
    for eff_val, label in efforts:
        check = " ✅" if eff_val == current_effort else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_effort:{eff_val}")])
    keyboard.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_timeout_selection_keyboard(current_timeout: int) -> InlineKeyboardMarkup:
    timeouts = [
        (120, "⏱️ 2 minutes"),
        (300, "⏱️ 5 minutes"),
        (600, "⏱️ 10 minutes (recommandé)"),
        (1800, "⏱️ 30 minutes"),
        (3600, "⏱️ 1 heure"),
        (0, "♾️ Infini (aucune limite — idéal pour /goal)"),
    ]
    keyboard = []
    for t_val, label in timeouts:
        check = " ✅" if t_val == current_timeout else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_timeout:{t_val}")])
    keyboard.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_verbosity_selection_keyboard(current_verbosity: str) -> InlineKeyboardMarkup:
    levels = [
        ("compact", "🧼 Compact (Masquer les blocs d'outils à la fin)"),
        ("normal", "⚖️ Normal (Afficher les outils en direct, nettoyer à la fin)"),
        ("detailed", "🔬 Détaillé (Conserver les blocs d'outils dépliables dans la réponse)"),
    ]
    keyboard = []
    for val, label in levels:
        check = " ✅" if val == current_verbosity else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_verbosity:{val}")])
    keyboard.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_agents_keyboard(settings: dict, available_agents: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    multi_on = bool(settings.get("multi_agent", True))
    curr_prof = settings.get("agent_profile", "")

    rows = [
        [
            InlineKeyboardButton(
                f"🤝 Orchestration Multi-Agents : {'ACTIVÉE ✅' if multi_on else 'DÉSACTIVÉE ❌'}",
                callback_data="toggle_multi_agent",
            )
        ]
    ]
    for ag in available_agents[:8]:
        name = ag.get("name", "")
        desc = ag.get("description", "")
        check = " ✅" if name == curr_prof else ""
        label = f"🤖 {desc}{check}" if not name else f"🤖 {name} — {desc[:28]}{check}"
        rows.append([InlineKeyboardButton(label, callback_data=f"set_agent:{name}")])

    rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_mcp_keyboard(servers: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    for srv in servers[:15]:
        name = srv["name"]
        st = srv["status"]
        stype = srv["type"]
        is_en = (st == "enabled")
        icon = "🟢" if is_en else "🔴"
        action = "disable" if is_en else "enable"
        rows.append([
            InlineKeyboardButton(
                f"{icon} {name} ({stype}) — Cliquer pour {'Désactiver' if is_en else 'Activer'}",
                callback_data=f"mcp_toggle:{action}:{name}",
            )
        ])

    rows.append([
        InlineKeyboardButton("➕ Ajouter Serveur MCP", callback_data="mcp_add_prompt"),
        InlineKeyboardButton("🔄 Actualiser", callback_data="menu_mcp"),
    ])
    rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_plugins_keyboard(plugins: List[Dict[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    for pl in plugins[:12]:
        name = pl["name"]
        st = pl["status"]
        is_en = ("disable" not in st)
        icon = "🟢" if is_en else "🔴"
        action = "disable" if is_en else "enable"
        rows.append([
            InlineKeyboardButton(
                f"{icon} {name} ({'Actif' if is_en else 'Inactif'})",
                callback_data=f"plugin_toggle:{action}:{name}",
            )
        ])

    rows.append([
        InlineKeyboardButton("📥 Importer (Gemini)", callback_data="plugin_import:gemini"),
        InlineKeyboardButton("📥 Importer (Claude)", callback_data="plugin_import:claude"),
    ])
    rows.append([
        InlineKeyboardButton("➕ Installer un Plugin", callback_data="plugin_install_prompt"),
        InlineKeyboardButton("🔄 Actualiser", callback_data="menu_plugins"),
    ])
    rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_remote_control_keyboard(session_flag: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("▶️ Démarrer Démon Remote", callback_data="rc_action:start"),
            InlineKeyboardButton("⏹️ Arrêter Démon", callback_data="rc_action:stop"),
        ],
        [
            InlineKeyboardButton(
                f"🔗 Flag Session --remote-control : {'ON ✅' if session_flag else 'OFF ❌'}",
                callback_data="rc_action:toggle_flag",
            )
        ],
        [InlineKeyboardButton("🔄 Actualiser le Statut", callback_data="menu_remote")],
        [InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(rows)


def get_sessions_keyboard(conversations: List[Dict[str, Any]], active_id: Optional[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🧹 Démarrer une Nouvelle Session Vierge", callback_data="sess_new")]
    ]
    for conv in conversations[:8]:
        cid = conv.get("id", "")
        title = conv.get("title", "Session")[:32]
        turns = conv.get("turns", 1)
        check = " 🟢" if cid and cid == active_id else ""
        rows.append([
            InlineKeyboardButton(
                f"💬 {title} ({turns}t){check}",
                callback_data=f"sess_load:{cid}",
            )
        ])
    rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_workspace_keyboard(settings: dict) -> InlineKeyboardMarkup:
    extra = settings.get("extra_dirs", []) or []
    rows = [
        [InlineKeyboardButton("📂 Changer le Dossier Workspace Principal", callback_data="ws_change_prompt")],
        [InlineKeyboardButton("➕ Ajouter un Dossier Secondaire (--add-dir)", callback_data="ws_add_extra_prompt")],
    ]
    if extra:
        rows.append([InlineKeyboardButton(f"🗑️ Vider les Dossiers Secondaires ({len(extra)})", callback_data="ws_clear_extra")])
    rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_persona_keyboard(settings: dict) -> InlineKeyboardMarkup:
    has_instr = bool(settings.get("custom_instructions", "").strip())
    rows = [
        [InlineKeyboardButton("🏷️ Changer le Nom de l'Agent", callback_data="persona_name_prompt")],
        [InlineKeyboardButton("📝 Définir des Instructions Système Personnalisées", callback_data="persona_instr_prompt")],
    ]
    if has_instr:
        rows.append([InlineKeyboardButton("🗑️ Effacer les Instructions Personnalisées", callback_data="persona_clear_instr")])
    rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)