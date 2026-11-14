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


def truncate_telegram_html(text: str, max_length: int = 3800) -> str:
    if not text or len(text) <= max_length:
        return text or ""

    cut = text[:max(0, max_length - 15)]
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


def smart_split_html(text: str, max_length: int = 3800) -> List[str]:
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

    # Break up any overly long unbroken lines first
    safe_lines = []
    for line in text.split("\n"):
        if len(line) > max_length - 100:
            sub_step = max_length - 200
            for start_idx in range(0, len(line), sub_step):
                safe_lines.append(line[start_idx : start_idx + sub_step])
        else:
            safe_lines.append(line)

    for line in safe_lines:
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

def format_settings_summary_html(settings: dict, user_lang: str = "en") -> str:
    agent_name = settings.get("agent_name", "Antigravity Agent")
    model = settings.get("model", "auto")
    effort = settings.get("effort", "auto")
    mode = settings.get("mode", "auto-approve")
    sandbox = bool(settings.get("sandbox", False))
    multi_agent = bool(settings.get("multi_agent", True))
    verbosity = settings.get("verbosity", "normal")
    auto_files = bool(settings.get("auto_send_files", True))
    ws = settings.get("workspace_dir", "")
    extra_dirs = settings.get("extra_dirs", []) or []
    timeout = int(settings.get("timeout", 600))
    custom_instr = settings.get("custom_instructions", "").strip()
    tier = settings.get("account_tier", "auto")

    is_fr = (user_lang == "fr")

    if timeout <= 0:
        t_str = "♾️ Infini (Sans limite)" if is_fr else "♾️ Infinite (No limit)"
    elif timeout >= 3600:
        t_str = f"{timeout // 3600}h" if timeout % 3600 == 0 else f"{timeout / 3600:.1f}h"
    else:
        t_str = f"{timeout // 60} min"

    autonomy = settings.get("agent_creation_autonomy", "ask")
    if is_fr:
        autonomy_badge = {"ask": "✋ Demander", "auto": "⚡ Auto", "off": "⛔ Off"}.get(autonomy, autonomy)
        lines = [
            f"🎛️ <b>Centre de Contrôle — {h(agent_name)}</b>\n",
            f"• 🏷️ <b>Forfait Google :</b> <code>{h(tier.upper())}</code>",
            f"• 🧠 <b>Modèle IA :</b> <code>{h(model)}</code>",
            f"• 💡 <b>Réflexion (Effort) :</b> <code>{h(effort)}</code>",
            f"• 🛡️ <b>Mode d'exécution :</b> <code>{h(mode)}</code>",
            f"• 🤝 <b>Multi-Agents :</b> {'🟢 Activé' if multi_agent else '🔴 Désactivé'} | <b>Autonomie :</b> <code>{h(autonomy_badge)}</code>",
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
    else:
        autonomy_badge = {"ask": "✋ Ask", "auto": "⚡ Auto", "off": "⛔ Off"}.get(autonomy, autonomy)
        lines = [
            f"🎛️ <b>Control Center — {h(agent_name)}</b>\n",
            f"• 🏷️ <b>Google Plan:</b> <code>{h(tier.upper())}</code>",
            f"• 🧠 <b>AI Model:</b> <code>{h(model)}</code>",
            f"• 💡 <b>Effort (Reasoning):</b> <code>{h(effort)}</code>",
            f"• 🛡️ <b>Execution Mode:</b> <code>{h(mode)}</code>",
            f"• 🤝 <b>Multi-Agent Swarm:</b> {'🟢 Enabled' if multi_agent else '🔴 Disabled'} | <b>Autonomy:</b> <code>{h(autonomy_badge)}</code>",
            f"• 📦 <b>CLI Sandbox:</b> {'🟢 Enabled' if sandbox else '⚪ Disabled'}",
            f"• ⏱️ <b>Timeout:</b> <code>{t_str}</code>",
            f"• 👁️ <b>Verbosity:</b> <code>{h(verbosity)}</code>",
            f"• 📤 <b>Auto-Send Files:</b> {'🟢 Yes' if auto_files else '🔴 No'}",
            f"• 📁 <b>Workspace:</b> <code>{h(ws)}</code>" + (f" (+{len(extra_dirs)} dirs)" if extra_dirs else ""),
        ]
        if custom_instr:
            preview = custom_instr[:70] + ("…" if len(custom_instr) > 70 else "")
            lines.append(f"• 📌 <b>Custom instructions:</b> <i>{h(preview)}</i>")
        lines.append("\n<i>Click an item below to configure your agent in real time:</i>")

    return "\n".join(lines)


def get_settings_keyboard(settings: dict, user_lang: str = "en") -> InlineKeyboardMarkup:
    mode = settings.get("mode", "auto-approve")
    model = settings.get("model", "auto")
    effort = settings.get("effort", "auto")
    timeout = int(settings.get("timeout", 600))
    sandbox = bool(settings.get("sandbox", False))
    multi_agent = bool(settings.get("multi_agent", True))
    autonomy = settings.get("agent_creation_autonomy", "ask")
    verbosity = settings.get("verbosity", "normal")
    auto_files = bool(settings.get("auto_send_files", True))
    tier = settings.get("account_tier", "auto")

    is_fr = (user_lang == "fr")

    if is_fr:
        autonomy_label = {"ask": "✋ Demander", "auto": "⚡ Auto", "off": "⛔ Off"}.get(autonomy, autonomy)
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
        tier_label = {"auto": "🤖 Auto", "free": "🌱 Gratuit", "pro": "⭐ Pro", "ultra": "👑 Ultra"}.get(tier, tier)
        timeout_label = "♾️ Infini" if timeout <= 0 else (f"{timeout // 3600}h" if timeout >= 3600 else f"{timeout // 60}m")

        keyboard = [
            [InlineKeyboardButton(f"🧠 Modèle : {model}", callback_data="menu_model")],
            [
                InlineKeyboardButton(f"🏷️ Forfait : {tier_label}", callback_data="menu_tier"),
                InlineKeyboardButton(f"💡 Effort : {effort_label}", callback_data="menu_effort"),
            ],
            [
                InlineKeyboardButton(f"🛡️ Mode : {mode_label}", callback_data="menu_mode"),
                InlineKeyboardButton(f"🤝 Multi-Agents : {'ON ✅' if multi_agent else 'OFF ❌'}", callback_data="toggle_multi_agent"),
            ],
            [
                InlineKeyboardButton("🤖 Équipe (/agents)", callback_data="cmd_agents"),
                InlineKeyboardButton(f"⚙️ Autonomie : {autonomy_label}", callback_data="cycle_autonomy"),
            ],
            [
                InlineKeyboardButton(f"📦 Sandbox : {'ON 🔒' if sandbox else 'OFF 🔓'}", callback_data="toggle_sandbox"),
                InlineKeyboardButton(f"⏱️ Timeout : {timeout_label}", callback_data="menu_timeout"),
            ],
            [
                InlineKeyboardButton(f"👁️ Vue : {verb_label}", callback_data="menu_verbosity"),
                InlineKeyboardButton(f"📤 Auto-Médias : {'ON ✅' if auto_files else 'OFF ❌'}", callback_data="toggle_autofiles"),
            ],
            [
                InlineKeyboardButton("📁 Workspace & Dossiers", callback_data="menu_workspace"),
                InlineKeyboardButton("🔌 Serveurs MCP (/mcp)", callback_data="menu_mcp"),
            ],
            [
                InlineKeyboardButton("📊 Quotas & Tokens (/usage)", callback_data="cmd_usage"),
                InlineKeyboardButton("🧩 Plugins CLI (/plugins)", callback_data="menu_plugins"),
            ],
            [
                InlineKeyboardButton("🌐 Remote Control", callback_data="menu_remote"),
                InlineKeyboardButton("💬 Sessions & Historique", callback_data="menu_sessions"),
            ],
            [
                InlineKeyboardButton("✏️ Instructions Perso", callback_data="menu_persona"),
                InlineKeyboardButton("🕹️ Commandes (/commands)", callback_data="menu_commands"),
            ],
            [
                InlineKeyboardButton("👥 Utilisateurs (/users)", callback_data="auth:refresh"),
                InlineKeyboardButton("🌐 Langue / Language", callback_data="menu_language"),
            ],
            [
                InlineKeyboardButton("🔄 Maj Système (/update)", callback_data="sys_update:check"),
                InlineKeyboardButton("🔄 Par défaut", callback_data="reset_settings"),
            ],
            [
                InlineKeyboardButton("❌ Fermer", callback_data="close_menu"),
            ],
        ]
    else:
        autonomy_label = {"ask": "✋ Ask", "auto": "⚡ Auto", "off": "⛔ Off"}.get(autonomy, autonomy)
        mode_label = {"auto-approve": "⚡ Autonomous", "accept-edits": "✏️ Edits", "plan": "📋 Plan"}.get(mode, mode)
        effort_label = {
            "auto": "🤖 Auto",
            "low": "⚡ Low",
            "medium": "⚖️ Medium",
            "high": "🧠 High",
            "xhigh": "🔥 XHigh",
            "max": "🚀 Max",
        }.get(effort, effort)
        verb_label = {"compact": "🧼 Compact", "normal": "⚖️ Normal", "detailed": "🔬 Detailed"}.get(verbosity, verbosity)
        tier_label = {"auto": "🤖 Auto", "free": "🌱 Free", "pro": "⭐ Pro", "ultra": "👑 Ultra"}.get(tier, tier)
        timeout_label = "♾️ Infinite" if timeout <= 0 else (f"{timeout // 3600}h" if timeout >= 3600 else f"{timeout // 60}m")

        keyboard = [
            [InlineKeyboardButton(f"🧠 Model: {model}", callback_data="menu_model")],
            [
                InlineKeyboardButton(f"🏷️ Plan: {tier_label}", callback_data="menu_tier"),
                InlineKeyboardButton(f"💡 Effort: {effort_label}", callback_data="menu_effort"),
            ],
            [
                InlineKeyboardButton(f"🛡️ Mode: {mode_label}", callback_data="menu_mode"),
                InlineKeyboardButton(f"🤝 Multi-Agent: {'ON ✅' if multi_agent else 'OFF ❌'}", callback_data="toggle_multi_agent"),
            ],
            [
                InlineKeyboardButton("🤖 Subagents (/agents)", callback_data="cmd_agents"),
                InlineKeyboardButton(f"⚙️ Autonomy: {autonomy_label}", callback_data="cycle_autonomy"),
            ],
            [
                InlineKeyboardButton(f"📦 Sandbox: {'ON 🔒' if sandbox else 'OFF 🔓'}", callback_data="toggle_sandbox"),
                InlineKeyboardButton(f"⏱️ Timeout: {timeout_label}", callback_data="menu_timeout"),
            ],
            [
                InlineKeyboardButton(f"👁️ View: {verb_label}", callback_data="menu_verbosity"),
                InlineKeyboardButton(f"📤 Auto-Files: {'ON ✅' if auto_files else 'OFF ❌'}", callback_data="toggle_autofiles"),
            ],
            [
                InlineKeyboardButton("📁 Workspace & Dirs", callback_data="menu_workspace"),
                InlineKeyboardButton("🔌 MCP Servers (/mcp)", callback_data="menu_mcp"),
            ],
            [
                InlineKeyboardButton("📊 Token Gauges (/usage)", callback_data="cmd_usage"),
                InlineKeyboardButton("🧩 CLI Plugins (/plugins)", callback_data="menu_plugins"),
            ],
            [
                InlineKeyboardButton("🌐 Remote Control", callback_data="menu_remote"),
                InlineKeyboardButton("💬 Sessions (/sessions)", callback_data="menu_sessions"),
            ],
            [
                InlineKeyboardButton("✏️ Custom Instructions", callback_data="menu_persona"),
                InlineKeyboardButton("🕹️ Commands (/commands)", callback_data="menu_commands"),
            ],
            [
                InlineKeyboardButton("👥 Users (/users)", callback_data="auth:refresh"),
                InlineKeyboardButton("🌐 Language", callback_data="menu_language"),
            ],
            [
                InlineKeyboardButton("🔄 Update System (/update)", callback_data="sys_update:check"),
                InlineKeyboardButton("🔄 Reset to Default", callback_data="reset_settings"),
            ],
            [
                InlineKeyboardButton("❌ Close", callback_data="close_menu"),
            ],
        ]

    return InlineKeyboardMarkup(keyboard)


def get_account_tier_selection_keyboard(current_tier: str, user_lang: str = "en") -> InlineKeyboardMarkup:
    """Build selection keyboard for Google Antigravity account tier."""
    is_fr = (user_lang == "fr")
    tiers = [
        ("auto", "🤖 Auto-détection (selon Antigravity CLI)" if is_fr else "🤖 Auto-Detect (via Antigravity CLI)"),
        ("free", "🌱 Gratuit / Free (Flash uniquement, Économie de quota)" if is_fr else "🌱 Free Tier (Flash Only, Quota Preserving)"),
        ("pro", "⭐ Google AI Pro (Argon 4, Claude, Essaim Multi-Agents)" if is_fr else "⭐ Google AI Pro (Argon 4, Claude, Full Swarm)"),
        ("ultra", "👑 Ultra / Enterprise (Quotas Maximaux & Tous Modèles)" if is_fr else "👑 Ultra / Enterprise (Max Limits & All Models)"),
    ]
    keyboard = []
    for t_val, label in tiers:
        check = " ✅" if t_val == current_tier else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_tier:{t_val}")])

    back_btn = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Settings"
    keyboard.append([InlineKeyboardButton(back_btn, callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_mode_selection_keyboard(current_mode: str, user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    if is_fr:
        modes = [
            ("auto-approve", "⚡ Autonome (--dangerously-skip-permissions)"),
            ("accept-edits", "✏️ Accepter Éditions (--mode accept-edits)"),
            ("plan", "📋 Planification seule (--mode plan)"),
        ]
        btn_back = "⬅️ Retour au Centre de Contrôle"
    else:
        modes = [
            ("auto-approve", "⚡ Autonomous (--dangerously-skip-permissions)"),
            ("accept-edits", "✏️ Accept Edits (--mode accept-edits)"),
            ("plan", "📋 Plan Only (--mode plan)"),
        ]
        btn_back = "⬅️ Back to Control Center"
    keyboard = []
    for mode_val, label in modes:
        check = " ✅" if mode_val == current_mode else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_mode:{mode_val}")])
    keyboard.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def to_base_model_id(model_id: str) -> str:
    """Normalize any full model ID (with effort suffix) to its clean base model ID."""
    m = (model_id or "").strip()
    if m in ("auto", "gemini-pro-orchestrator-g1-pro"):
        return m
    for suffix in ("-xhigh", "-high", "-medium", "-low", "-max"):
        if m.endswith(suffix):
            return m[:-len(suffix)]
    return m


BASE_MODEL_LABELS: Dict[str, Tuple[str, str]] = {
    "auto": ("🤖 Auto (Routage Intelligent Tâche & Quota)", "🤖 Auto (Smart Task & Quota Routing)"),
    "gemini-pro-orchestrator-g1-pro": ("🎛️ Gemini Pro Orchestrator (Argon) [Pro/Ultra]", "🎛️ Gemini Pro Orchestrator (Argon) [Pro/Ultra]"),
    "gemini-4-hydrogen": ("🚀 Gemini 4 Hydrogen [Pro/Ultra]", "🚀 Gemini 4 Hydrogen [Pro/Ultra]"),
    "gemini-4-carbon": ("💎 Gemini 4 Carbon [Ultra]", "💎 Gemini 4 Carbon [Ultra]"),
    "gemini-4-argon": ("🧠 Gemini 4 Argon [Pro/Ultra]", "🧠 Gemini 4 Argon [Pro/Ultra]"),
    "gemini-3.8-flash": ("⚡ Gemini 3.8 Flash", "⚡ Gemini 3.8 Flash"),
    "claude-sonnet-5-5": ("📜 Claude Sonnet 5.5 [Pro/Ultra]", "📜 Claude Sonnet 5.5 [Pro/Ultra]"),
    "claude-opus-5-5": ("👑 Claude Opus 5.5 [Pro/Ultra]", "👑 Claude Opus 5.5 [Pro/Ultra]"),
    "gpt-oss-120b": ("🌐 GPT-OSS 120B", "🌐 GPT-OSS 120B"),
}

MODEL_SUPPORTED_EFFORTS: Dict[str, List[str]] = {
    "gemini-4-carbon": ["auto", "low", "medium", "high", "xhigh", "max"],
    "gemini-4-hydrogen": ["auto", "low", "medium", "high", "xhigh"],
    "gemini-4-argon": ["auto", "low", "medium", "high"],
    "gemini-3.8-flash": ["auto", "low", "medium", "high"],
    "claude-sonnet-5-5": ["auto", "low", "medium", "high"],
    "claude-opus-5-5": ["auto", "low", "medium", "high"],
    "gemini-pro-orchestrator-g1-pro": ["auto", "medium", "high"],
    "gpt-oss-120b": ["medium"],
    "auto": ["auto", "low", "medium", "high", "xhigh", "max"],
}


def get_supported_effort_levels(model_name: str) -> List[str]:
    """Return the list of effort levels supported by the given model."""
    base_id = to_base_model_id(model_name).lower()
    for k, v in MODEL_SUPPORTED_EFFORTS.items():
        if k in base_id:
            return v
    return ["auto", "low", "medium", "high", "xhigh", "max"]


def get_model_selection_keyboard(
    current_model: str,
    available_models: Optional[List[Tuple[str, str]]] = None,
    user_lang: str = "en",
    account_tier: str = "auto",
) -> InlineKeyboardMarkup:
    from agent_runner import get_cached_models
    models = available_models or get_cached_models()
    is_fr = (user_lang == "fr")
    tier = (account_tier or "auto").lower()

    # Deduplicate models by base model ID to eliminate duplicate entries for low/medium/high/xhigh
    seen_bases = set()
    deduped_models: List[Tuple[str, str]] = []

    for mod_val, label in models:
        base_id = to_base_model_id(mod_val)
        if base_id in seen_bases:
            continue
        seen_bases.add(base_id)

        if base_id in BASE_MODEL_LABELS:
            clean_label = BASE_MODEL_LABELS[base_id][0] if is_fr else BASE_MODEL_LABELS[base_id][1]
        else:
            clean_label = label
            for sfx in ("(High)", "(Medium)", "(Low)", "(XHigh)", "(Max)"):
                clean_label = clean_label.replace(sfx, "").strip()

        # Add tier lock tags for models that require a higher plan
        is_locked = False
        lock_suffix = ""
        if tier == "free" and any(k in base_id for k in ("carbon", "argon", "hydrogen", "orchestrator", "claude")):
            is_locked = True
            lock_suffix = " 🔒 [Pro]" if is_fr else " 🔒 [Pro]"
        elif tier == "pro" and "carbon" in base_id:
            is_locked = True
            lock_suffix = " 🔒 [Ultra]" if is_fr else " 🔒 [Ultra]"

        if is_locked:
            # Strip existing tier tags and append lock
            for tag in ("[Pro/Ultra]", "[Ultra]", "[Pro]"):
                clean_label = clean_label.replace(tag, "").strip()
            clean_label = f"{clean_label}{lock_suffix}"

        deduped_models.append((base_id, clean_label))

    keyboard = []
    curr_base = to_base_model_id(current_model)
    for mod_val, label in deduped_models:
        check = " ✅" if (mod_val == current_model or mod_val == curr_base) else ""
        display_btn = f"{label}{check}"
        keyboard.append([InlineKeyboardButton(display_btn, callback_data=f"set_model:{mod_val}")])

    if is_fr:
        keyboard.append([InlineKeyboardButton("💡 Régler l'Effort de Réflexion (/effort)", callback_data="menu_effort")])
        keyboard.append([InlineKeyboardButton("📊 Voir Quotas & Utilisation (/usage)", callback_data="cmd_usage")])
        keyboard.append([InlineKeyboardButton("🔄 Rafraîchir depuis Antigravity CLI", callback_data="refresh_models")])
        keyboard.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    else:
        keyboard.append([InlineKeyboardButton("💡 Adjust Reasoning Effort (/effort)", callback_data="menu_effort")])
        keyboard.append([InlineKeyboardButton("📊 View Quotas & Usage (/usage)", callback_data="cmd_usage")])
        keyboard.append([InlineKeyboardButton("🔄 Refresh from Antigravity CLI", callback_data="refresh_models")])
        keyboard.append([InlineKeyboardButton("⬅️ Back to Control Center", callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_usage_keyboard(user_lang: str = "en") -> InlineKeyboardMarkup:
    """Build interactive action buttons for the /usage dashboard."""
    if user_lang == "fr":
        btn_reset = "🔄 Réinitialiser les Verrous"
        btn_test = "⚡ Tester la Connexion"
        btn_models = "🎛️ Choisir un Modèle"
        btn_refresh = "📊 Actualiser"
    else:
        btn_reset = "🔄 Reset Cooldown Locks"
        btn_test = "⚡ Test Live Connection"
        btn_models = "🎛️ Select AI Model"
        btn_refresh = "📊 Refresh"

    keyboard = [
        [
            InlineKeyboardButton(btn_reset, callback_data="usage_reset_cooldowns"),
            InlineKeyboardButton(btn_test, callback_data="usage_test_live"),
        ],
        [
            InlineKeyboardButton(btn_models, callback_data="menu_models"),
            InlineKeyboardButton(btn_refresh, callback_data="cmd_usage"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_effort_selection_keyboard(
    current_effort: str,
    current_model: str = "auto",
    user_lang: str = "en",
) -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    all_efforts_fr = [
        ("auto", "🤖 Auto (Adapté dynamiquement au modèle)"),
        ("low", "⚡ Rapide (low — direct & ultra-réactif)"),
        ("medium", "⚖️ Équilibré (medium — analyse standard)"),
        ("high", "🧠 Profond (high — réflexion avancée)"),
        ("xhigh", "🔥 Très Profond (xhigh — raisonnement intensif)"),
        ("max", "🚀 Maximum (max — réflexion frontière)"),
    ]
    all_efforts_en = [
        ("auto", "🤖 Auto (Dynamically adapted to model)"),
        ("low", "⚡ Fast (low — fast & responsive)"),
        ("medium", "⚖️ Balanced (medium — standard reasoning)"),
        ("high", "🧠 Deep (high — advanced reasoning)"),
        ("xhigh", "🔥 Very Deep (xhigh — intensive reasoning)"),
        ("max", "🚀 Maximum (max — frontier reasoning)"),
    ]
    supported = get_supported_effort_levels(current_model)
    raw_list = all_efforts_fr if is_fr else all_efforts_en
    filtered_efforts = [item for item in raw_list if item[0] in supported]

    keyboard = []
    for eff_val, label in filtered_efforts:
        check = " ✅" if eff_val == current_effort else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_effort:{eff_val}")])

    btn_models = "🎛️ Choisir un Autre Modèle (/model)" if is_fr else "🎛️ Switch AI Model (/model)"
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"
    keyboard.append([InlineKeyboardButton(btn_models, callback_data="menu_models")])
    keyboard.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_timeout_selection_keyboard(current_timeout: int, user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    if is_fr:
        timeouts = [
            (120, "⏱️ 2 minutes"),
            (300, "⏱️ 5 minutes"),
            (600, "⏱️ 10 minutes (recommandé)"),
            (1800, "⏱️ 30 minutes"),
            (3600, "⏱️ 1 heure"),
            (0, "♾️ Infini (aucune limite — idéal pour /goal)"),
        ]
        btn_back = "⬅️ Retour au Centre de Contrôle"
    else:
        timeouts = [
            (120, "⏱️ 2 minutes"),
            (300, "⏱️ 5 minutes"),
            (600, "⏱️ 10 minutes (recommended)"),
            (1800, "⏱️ 30 minutes"),
            (3600, "⏱️ 1 hour"),
            (0, "♾️ Infinite (no limit — ideal for /goal)"),
        ]
        btn_back = "⬅️ Back to Control Center"
    keyboard = []
    for t_val, label in timeouts:
        check = " ✅" if t_val == current_timeout else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_timeout:{t_val}")])
    keyboard.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_verbosity_selection_keyboard(current_verbosity: str, user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    if is_fr:
        levels = [
            ("compact", "🧼 Compact (Masquer les blocs d'outils à la fin)"),
            ("normal", "⚖️ Normal (Afficher les outils en direct, nettoyer à la fin)"),
            ("detailed", "🔬 Détaillé (Conserver les blocs d'outils dépliables dans la réponse)"),
        ]
        btn_back = "⬅️ Retour au Centre de Contrôle"
    else:
        levels = [
            ("compact", "🧼 Compact (Hide tool blocks when done)"),
            ("normal", "⚖️ Normal (Stream live tools, clean at end)"),
            ("detailed", "🔬 Detailed (Keep collapsible tool blocks in response)"),
        ]
        btn_back = "⬅️ Back to Control Center"
    keyboard = []
    for val, label in levels:
        check = " ✅" if val == current_verbosity else ""
        keyboard.append([InlineKeyboardButton(f"{label}{check}", callback_data=f"set_verbosity:{val}")])
    keyboard.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(keyboard)


def get_agents_keyboard(settings: dict, available_agents: List[Dict[str, str]], user_lang: str = "en") -> InlineKeyboardMarkup:
    from agent_registry import agent_registry
    agents = agent_registry.list_agents(include_disabled=True)
    autonomy = settings.get("agent_creation_autonomy", "ask")
    return get_subagents_team_keyboard(agents, autonomy, user_lang=user_lang)


def get_subagents_team_keyboard(agents: List[Dict[str, Any]], autonomy: str = "ask", user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    if is_fr:
        autonomy_labels = {
            "ask": "✋ Demander (Validation)",
            "auto": "⚡ Auto (Création directe)",
            "off": "⛔ Off (Désactivé)",
        }
        btn_create = "➕ Créer un Agent"
        btn_import = "📥 Importer (.md/.zip)"
        btn_export = "📤 Exporter l'Équipe (ZIP)"
        btn_refresh = "🔄 Rafraîchir"
        btn_back = "⬅️ Retour au Centre de Contrôle"
        auto_title = "⚙️ Autonomie Création : "
    else:
        autonomy_labels = {
            "ask": "✋ Ask (Approval)",
            "auto": "⚡ Auto (Direct creation)",
            "off": "⛔ Off (Disabled)",
        }
        btn_create = "➕ Create Agent"
        btn_import = "📥 Import (.md/.zip)"
        btn_export = "📤 Export Team (ZIP)"
        btn_refresh = "🔄 Refresh"
        btn_back = "⬅️ Back to Control Center"
        auto_title = "⚙️ Creation Autonomy: "

    cur_auto_label = autonomy_labels.get(autonomy, autonomy)
    rows = []
    for ag in agents:
        name = ag.get("name", "")
        disp = ag.get("display_name", name)
        is_en = ag.get("enabled", True)
        icon = "🟢" if is_en else "⚪"
        model = ag.get("model", "auto")
        rows.append([
            InlineKeyboardButton(f"{icon} {disp} ({model})", callback_data=f"subagent_view:{name}")
        ])

    rows.append([
        InlineKeyboardButton(f"{auto_title}{cur_auto_label}", callback_data="cycle_autonomy")
    ])
    rows.append([
        InlineKeyboardButton(btn_create, callback_data="subagent_create_prompt"),
        InlineKeyboardButton(btn_import, callback_data="subagent_import_prompt"),
    ])
    rows.append([
        InlineKeyboardButton(btn_export, callback_data="subagent_export_all"),
        InlineKeyboardButton(btn_refresh, callback_data="cmd_agents"),
    ])
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_subagent_detail_keyboard(name: str, agent: Dict[str, Any], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_en = agent.get("enabled", True)
    is_fr = (user_lang == "fr")
    if is_fr:
        toggle_text = "⚪ Désactiver ce sous-agent" if is_en else "🟢 Activer ce sous-agent"
        btn_export = "📤 Exporter ce fichier (.md)"
        btn_delete = "🗑️ Supprimer ce sous-agent"
        btn_back = "⬅️ Retour à l'équipe (/agents)"
    else:
        toggle_text = "⚪ Disable this subagent" if is_en else "🟢 Enable this subagent"
        btn_export = "📤 Export this file (.md)"
        btn_delete = "🗑️ Delete this subagent"
        btn_back = "⬅️ Back to team (/agents)"
    rows = [
        [InlineKeyboardButton(toggle_text, callback_data=f"subagent_toggle:{name}")],
        [InlineKeyboardButton(btn_export, callback_data=f"subagent_export:{name}")],
        [InlineKeyboardButton(btn_delete, callback_data=f"subagent_delete:{name}")],
        [InlineKeyboardButton(btn_back, callback_data="cmd_agents")],
    ]
    return InlineKeyboardMarkup(rows)


def get_agent_creation_confirm_keyboard(temp_agent_id: str, user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    btn_confirm = "✅ Confirmer & Activer l'Agent" if is_fr else "✅ Confirm & Enable Agent"
    btn_cancel = "❌ Annuler / Refuser" if is_fr else "❌ Cancel / Reject"
    rows = [
        [
            InlineKeyboardButton(btn_confirm, callback_data=f"agent_confirm_create:{temp_agent_id}"),
            InlineKeyboardButton(btn_cancel, callback_data=f"agent_cancel_create:{temp_agent_id}"),
        ]
    ]
    return InlineKeyboardMarkup(rows)


def get_experts_keyboard(experts: Dict[str, Dict[str, Any]], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    rows = []
    for name, exp in experts.items():
        disp = exp.get("display_name", name)
        is_en = exp.get("enabled", True)
        status_icon = "✅" if is_en else "❌"
        rows.append([
            InlineKeyboardButton(f"{disp} — {status_icon}", callback_data=f"expert_view:{name}")
        ])
    btn_refresh = "🔄 Rafraîchir" if is_fr else "🔄 Refresh"
    btn_back = "⬅️ Centre de Contrôle" if is_fr else "⬅️ Control Center"
    rows.append([
        InlineKeyboardButton(btn_refresh, callback_data="cmd_experts"),
        InlineKeyboardButton(btn_back, callback_data="menu_main"),
    ])
    return InlineKeyboardMarkup(rows)


def get_expert_detail_keyboard(name: str, expert: Dict[str, Any], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_en = expert.get("enabled", True)
    is_fr = (user_lang == "fr")
    if is_fr:
        toggle_text = "❌ Désactiver cet expert" if is_en else "✅ Activer cet expert"
        btn_delete = "🗑️ Supprimer cet expert"
        btn_back = "⬅️ Retour à l'équipe d'experts"
    else:
        toggle_text = "❌ Disable this expert" if is_en else "✅ Enable this expert"
        btn_delete = "🗑️ Delete this expert"
        btn_back = "⬅️ Back to expert team"
    rows = [
        [InlineKeyboardButton(toggle_text, callback_data=f"expert_toggle:{name}")],
        [InlineKeyboardButton(btn_delete, callback_data=f"expert_delete:{name}")],
        [InlineKeyboardButton(btn_back, callback_data="cmd_experts")],
    ]
    return InlineKeyboardMarkup(rows)


def get_mcp_keyboard(servers: List[Dict[str, str]], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    rows = []
    for srv in servers[:15]:
        name = srv["name"]
        st = srv["status"]
        stype = srv["type"]
        is_en = (st == "enabled")
        icon = "🟢" if is_en else "🔴"
        action = "disable" if is_en else "enable"
        if is_fr:
            action_label = "Désactiver" if is_en else "Activer"
            label = f"{icon} {name} ({stype}) — Cliquer pour {action_label}"
        else:
            action_label = "Disable" if is_en else "Enable"
            label = f"{icon} {name} ({stype}) — Click to {action_label}"
        rows.append([
            InlineKeyboardButton(label, callback_data=f"mcp_toggle:{action}:{name}")
        ])

    if is_fr:
        rows.append([
            InlineKeyboardButton("⚡ Pack MCP Recommandés (Playwright, Firecrawl, Docker...)", callback_data="mcp_catalog")
        ])
        rows.append([
            InlineKeyboardButton("➕ Ajouter Serveur MCP", callback_data="mcp_add_prompt"),
            InlineKeyboardButton("🔄 Actualiser", callback_data="menu_mcp"),
        ])
        rows.append([InlineKeyboardButton("⬅️ Retour au Centre de Contrôle", callback_data="menu_main")])
    else:
        rows.append([
            InlineKeyboardButton("⚡ Recommended MCP Pack (Playwright, Firecrawl, Docker...)", callback_data="mcp_catalog")
        ])
        rows.append([
            InlineKeyboardButton("➕ Add MCP Server", callback_data="mcp_add_prompt"),
            InlineKeyboardButton("🔄 Refresh", callback_data="menu_mcp"),
        ])
        rows.append([InlineKeyboardButton("⬅️ Back to Control Center", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_mcp_catalog_keyboard(installed_names: List[str], user_lang: str = "en") -> InlineKeyboardMarkup:
    import config
    is_fr = (user_lang == "fr")
    rows = []
    for srv in config.RECOMMENDED_MCP_SERVERS:
        sid = srv["id"]
        is_inst = sid in installed_names
        if is_fr:
            status_badge = "✅ Déjà installé" if is_inst else "➕ Installer en 1 clic"
        else:
            status_badge = "✅ Already Installed" if is_inst else "➕ 1-Click Install"
        rows.append([
            InlineKeyboardButton(
                f"🔌 {srv['title'].split('(')[0].strip()} — {status_badge}",
                callback_data=f"mcp_quick_install:{sid}",
            )
        ])
    btn_all = "🚀 Tout installer (Pack Recommandé)" if is_fr else "🚀 Install All (Recommended Pack)"
    btn_back = "⬅️ Retour aux Serveurs MCP" if is_fr else "⬅️ Back to MCP Servers"
    rows.append([InlineKeyboardButton(btn_all, callback_data="mcp_quick_install:all_default")])
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_mcp")])
    return InlineKeyboardMarkup(rows)


def get_plugins_keyboard(plugins: List[Dict[str, str]], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    rows = []
    for pl in plugins[:12]:
        name = pl["name"]
        st = pl["status"]
        is_en = ("disable" not in st)
        icon = "🟢" if is_en else "🔴"
        action = "disable" if is_en else "enable"
        status_lbl = ("Actif" if is_en else "Inactif") if is_fr else ("Active" if is_en else "Inactive")
        rows.append([
            InlineKeyboardButton(
                f"{icon} {name} ({status_lbl})",
                callback_data=f"plugin_toggle:{action}:{name}",
            )
        ])

    btn_import_gem = "📥 Importer (Gemini)" if is_fr else "📥 Import (Gemini)"
    btn_import_cla = "📥 Importer (Claude)" if is_fr else "📥 Import (Claude)"
    btn_add = "➕ Installer un Plugin" if is_fr else "➕ Install Plugin"
    btn_refresh = "🔄 Actualiser" if is_fr else "🔄 Refresh"
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"

    rows.append([
        InlineKeyboardButton(btn_import_gem, callback_data="plugin_import:gemini"),
        InlineKeyboardButton(btn_import_cla, callback_data="plugin_import:claude"),
    ])
    rows.append([
        InlineKeyboardButton(btn_add, callback_data="plugin_install_prompt"),
        InlineKeyboardButton(btn_refresh, callback_data="menu_plugins"),
    ])
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_remote_control_keyboard(session_flag: bool, user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    btn_start = "▶️ Démarrer Démon Remote" if is_fr else "▶️ Start Remote Daemon"
    btn_stop = "⏹️ Arrêter Démon" if is_fr else "⏹️ Stop Daemon"
    btn_flag = (
        f"🔗 Flag Session --remote-control : {'ON ✅' if session_flag else 'OFF ❌'}"
        if is_fr else
        f"🔗 Session Flag --remote-control: {'ON ✅' if session_flag else 'OFF ❌'}"
    )
    btn_refresh = "🔄 Actualiser le Statut" if is_fr else "🔄 Refresh Status"
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"

    rows = [
        [
            InlineKeyboardButton(btn_start, callback_data="rc_action:start"),
            InlineKeyboardButton(btn_stop, callback_data="rc_action:stop"),
        ],
        [InlineKeyboardButton(btn_flag, callback_data="rc_action:toggle_flag")],
        [InlineKeyboardButton(btn_refresh, callback_data="menu_remote")],
        [InlineKeyboardButton(btn_back, callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(rows)


def get_sessions_keyboard(conversations: List[Dict[str, Any]], active_id: Optional[str], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    btn_new = "🧹 Démarrer une Nouvelle Session Vierge" if is_fr else "🧹 Start Fresh Blank Session"
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"
    rows = [
        [InlineKeyboardButton(btn_new, callback_data="sess_new")]
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
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_workspace_keyboard(settings: dict, user_lang: str = "en") -> InlineKeyboardMarkup:
    extra = settings.get("extra_dirs", []) or []
    is_fr = (user_lang == "fr")
    btn_change = "📂 Changer le Dossier Workspace Principal" if is_fr else "📂 Change Primary Workspace Folder"
    btn_add = "➕ Ajouter un Dossier Secondaire (--add-dir)" if is_fr else "➕ Add Secondary Directory (--add-dir)"
    btn_clear = (
        f"🗑️ Vider les Dossiers Secondaires ({len(extra)})"
        if is_fr else
        f"🗑️ Clear Secondary Directories ({len(extra)})"
    )
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"

    rows = [
        [InlineKeyboardButton(btn_change, callback_data="ws_change_prompt")],
        [InlineKeyboardButton(btn_add, callback_data="ws_add_extra_prompt")],
    ]
    if extra:
        rows.append([InlineKeyboardButton(btn_clear, callback_data="ws_clear_extra")])
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_persona_keyboard(settings: dict, user_lang: str = "en") -> InlineKeyboardMarkup:
    has_instr = bool(settings.get("custom_instructions", "").strip())
    is_fr = (user_lang == "fr")
    btn_name = "🏷️ Changer le Nom de l'Agent" if is_fr else "🏷️ Change Agent Name"
    btn_instr = "📝 Définir des Instructions Système Personnalisées" if is_fr else "📝 Set Custom System Instructions"
    btn_clear = "🗑️ Effacer les Instructions Personnalisées" if is_fr else "🗑️ Clear Custom Instructions"
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"

    rows = [
        [InlineKeyboardButton(btn_name, callback_data="persona_name_prompt")],
        [InlineKeyboardButton(btn_instr, callback_data="persona_instr_prompt")],
    ]
    if has_instr:
        rows.append([InlineKeyboardButton(btn_clear, callback_data="persona_clear_instr")])
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def format_update_check_html(info: Dict[str, Any], is_push_alert: bool = False, user_lang: str = "en") -> str:
    is_fr = (user_lang == "fr")
    if not info.get("ok"):
        if is_fr:
            return (
                "⚠️ <b>Vérification des mises à jour GitHub :</b>\n\n"
                f"<code>{h(info.get('error', 'Erreur inconnue'))}</code>\n\n"
                f"• <b>Version locale :</b> <code>v{h(info.get('local_version', '4.1.0'))}</code> (<code>{h(info.get('local_sha', ''))}</code>)\n"
                f"• <b>Antigravity CLI :</b> <code>{h(info.get('installed_agy', ''))}</code> (requis >= <code>{h(info.get('required_agy', ''))}</code>)"
            )
        else:
            return (
                "⚠️ <b>GitHub Update Check:</b>\n\n"
                f"<code>{h(info.get('error', 'Unknown error'))}</code>\n\n"
                f"• <b>Local version:</b> <code>v{h(info.get('local_version', '4.1.0'))}</code> (<code>{h(info.get('local_sha', ''))}</code>)\n"
                f"• <b>Antigravity CLI:</b> <code>{h(info.get('installed_agy', ''))}</code> (required >= <code>{h(info.get('required_agy', ''))}</code>)"
            )

    behind = int(info.get("commits_behind", 0))
    agy_needs = bool(info.get("agy_needs_update", False))
    local_ver = info.get("local_version", "4.1.0")
    remote_ver = info.get("remote_version", local_ver)
    local_sha = info.get("local_sha", "")
    remote_sha = info.get("remote_sha", "")
    inst_agy = info.get("installed_agy", "Inconnu" if is_fr else "Unknown")
    req_agy = info.get("required_agy", "1.3.0")
    changelog = info.get("changelog", "")
    commits = info.get("commits", []) or []

    if is_fr:
        agy_badge = (
            f"⚠️ Mise à jour requise (installé: <code>{h(inst_agy)}</code> ➔ requis: <code>&gt;= {h(req_agy)}</code>)"
            if agy_needs
            else f"✅ Compatible (<code>v{h(inst_agy)}</code> &gt;= <code>v{h(req_agy)}</code>)"
        )
        if behind == 0 and not agy_needs:
            return (
                "✅ <b>Votre système est 100% à jour !</b>\n\n"
                f"• 🤖 <b>Version du Bot :</b> <code>v{h(local_ver)}</code> (commit <code>{h(local_sha)}</code>)\n"
                f"• ⚡ <b>Antigravity CLI :</b> {agy_badge}\n"
                "• 🛡️ <b>Surveillance GitHub :</b> Active en arrière-plan"
            )
        title = "🚨 <b>Nouvelle Mise à Jour GitHub Détectée !</b>" if is_push_alert else "🚀 <b>Mise à Jour Disponible !</b>"
        lines = [
            f"{title}\n",
            f"• 📦 <b>Version :</b> <code>v{h(local_ver)}</code> (<code>{h(local_sha)}</code>) ➔ <b><code>v{h(remote_ver)}</code></b> (<code>{h(remote_sha)}</code>)",
            f"• ⚡ <b>Antigravity CLI :</b> {agy_badge}",
        ]
        if changelog:
            lines.append(f"• 📝 <b>Notes de version :</b> <i>{h(changelog)}</i>")
        if commits:
            lines.append(f"\n<b>📋 Nouveaux commits sur GitHub ({behind}) :</b>")
            for c in commits[:6]:
                lines.append(f"  ◦ <code>{h(c[:80])}</code>")
        lines.append(
            "\n🛡️ <i>Vos données personnelles (<code>.env</code>, <code>memory.db</code>, discussions, skills et préférences) "
            "seront intégralement sauvegardées et conservées, et le bot redémarrera tout seul sans coupure.</i>\n"
            "\n<b>Voulez-vous mettre à jour le système maintenant ?</b>"
        )
        return "\n".join(lines)
    else:
        agy_badge = (
            f"⚠️ Update required (installed: <code>{h(inst_agy)}</code> ➔ required: <code>&gt;= {h(req_agy)}</code>)"
            if agy_needs
            else f"✅ Compatible (<code>v{h(inst_agy)}</code> &gt;= <code>v{h(req_agy)}</code>)"
        )
        if behind == 0 and not agy_needs:
            return (
                "✅ <b>Your system is 100% up to date!</b>\n\n"
                f"• 🤖 <b>Bot Version:</b> <code>v{h(local_ver)}</code> (commit <code>{h(local_sha)}</code>)\n"
                f"• ⚡ <b>Antigravity CLI:</b> {agy_badge}\n"
                "• 🛡️ <b>GitHub Watcher:</b> Active in background"
            )
        title = "🚨 <b>New GitHub Update Detected!</b>" if is_push_alert else "🚀 <b>Update Available!</b>"
        lines = [
            f"{title}\n",
            f"• 📦 <b>Version:</b> <code>v{h(local_ver)}</code> (<code>{h(local_sha)}</code>) ➔ <b><code>v{h(remote_ver)}</code></b> (<code>{h(remote_sha)}</code>)",
            f"• ⚡ <b>Antigravity CLI:</b> {agy_badge}",
        ]
        if changelog:
            lines.append(f"• 📝 <b>Release notes:</b> <i>{h(changelog)}</i>")
        if commits:
            lines.append(f"\n<b>📋 New commits on GitHub ({behind}):</b>")
            for c in commits[:6]:
                lines.append(f"  ◦ <code>{h(c[:80])}</code>")
        lines.append(
            "\n🛡️ <i>Your personal data (<code>.env</code>, <code>memory.db</code>, chats, skills and preferences) "
            "will be fully preserved, and the bot will restart automatically with zero downtime.</i>\n"
            "\n<b>Would you like to update the system now?</b>"
        )
        return "\n".join(lines)


def get_update_prompt_keyboard(info: Dict[str, Any], user_lang: str = "en") -> InlineKeyboardMarkup:
    is_fr = (user_lang == "fr")
    rows = []
    if info.get("update_available"):
        remote_sha_full = info.get("remote_sha_full", "")[:12]
        btn_yes = "✅ Oui, mettre à jour maintenant" if is_fr else "✅ Yes, update now"
        btn_diff = "📂 Voir les fichiers modifiés" if is_fr else "📂 View modified files"
        btn_dismiss = "⏳ Ignorer cette version" if is_fr else "⏳ Ignore this version"
        btn_later = "⏳ Plus tard" if is_fr else "⏳ Later"

        rows.append([InlineKeyboardButton(btn_yes, callback_data="sys_update:confirm")])
        if info.get("changed_files"):
            rows.append([
                InlineKeyboardButton(btn_diff, callback_data="sys_update:files"),
                InlineKeyboardButton(btn_dismiss, callback_data=f"sys_update:dismiss:{remote_sha_full}"),
            ])
        else:
            rows.append([InlineKeyboardButton(btn_later, callback_data=f"sys_update:dismiss:{remote_sha_full}")])
    else:
        btn_recheck = "🔄 Revérifier sur GitHub" if is_fr else "🔄 Re-check GitHub"
        btn_force = "⬆️ Forcer Maj CLI (agy update)" if is_fr else "⬆️ Force CLI Update (agy update)"
        rows.append([
            InlineKeyboardButton(btn_recheck, callback_data="sys_update:check"),
            InlineKeyboardButton(btn_force, callback_data="cli_update"),
        ])
    btn_back = "⬅️ Retour au Centre de Contrôle" if is_fr else "⬅️ Back to Control Center"
    rows.append([InlineKeyboardButton(btn_back, callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)


def get_language_selection_keyboard(current_lang: str = "en") -> InlineKeyboardMarkup:
    check_en = " ✅" if current_lang == "en" else ""
    check_fr = " ✅" if current_lang == "fr" else ""
    btn_back = "⬅️ Retour au Centre de Contrôle" if current_lang == "fr" else "⬅️ Back to Control Center"
    rows = [
        [
            InlineKeyboardButton(f"🇬🇧 English (Default){check_en}", callback_data="set_lang:en"),
            InlineKeyboardButton(f"🇫🇷 Français{check_fr}", callback_data="set_lang:fr"),
        ],
        [InlineKeyboardButton(btn_back, callback_data="menu_main")],
    ]
    return InlineKeyboardMarkup(rows)