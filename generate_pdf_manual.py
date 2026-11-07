#!/usr/bin/env python3
"""
generate_pdf_manual.py - Produces a high-quality, comprehensive English PDF manual
for Antigravity Telegram Agent v5.1 using ReportLab.
"""

import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and print 'Page X of Y'
    along with running header and footer.
    """
    def __init__(self, *args, **kwargs):
        super(NumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super(NumberedCanvas, self).showPage()
        super(NumberedCanvas, self).save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Don't draw headers/footers on cover page (page 1)
        if self._pageNumber > 1:
            # Header
            self.drawString(54, letter[1] - 36, "ANTIGRAVITY TELEGRAM AGENT v5.1 — OPERATIONAL MANUAL")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(54, letter[1] - 42, letter[0] - 54, letter[1] - 42)

            # Footer
            self.line(54, 45, letter[0] - 54, 45)
            self.drawString(54, 32, "Confidential & Personal Autonomous Developer Gateway • Built with Google Antigravity CLI")
            page_str = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(letter[0] - 54, 32, page_str)

        self.restoreState()

def build_pdf(filename="Antigravity_Telegram_Agent_Manual_EN.pdf"):
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#0F172A"),
        alignment=TA_LEFT
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2563EB"),
        alignment=TA_LEFT
    )

    h1_style = ParagraphStyle(
        'Heading1_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#0F172A"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2_Custom',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'Body_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=5
    )

    bullet_style = ParagraphStyle(
        'Bullet_Custom',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#334155"),
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3
    )

    code_style = ParagraphStyle(
        'Code_Custom',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#0F172A")
    )

    callout_style = ParagraphStyle(
        'Callout_Text',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1E293B")
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#1E293B")
    )

    table_code_style = ParagraphStyle(
        'TableCode',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#0F172A")
    )

    def create_callout(text, bg_color="#EFF6FF", border_color="#3B82F6"):
        p = Paragraph(text, callout_style)
        t = Table([[p]], colWidths=[letter[0] - 108])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(bg_color)),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor(border_color)),
            ('TOPPADDING', (0,0), (-1,-1), 7),
            ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        return t

    def create_codebox(code_text):
        escaped = code_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
        p = Paragraph(escaped, code_style)
        t = Table([[p]], colWidths=[letter[0] - 108])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
        ]))
        return t

    story = []

    # =========================================================================
    # COVER / HEADER
    # =========================================================================
    story.append(Spacer(1, 15))
    story.append(Paragraph("ANTIGRAVITY TELEGRAM AGENT v5.1", title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("Complete Operational Manual: How to Use, Communicate, Customize & Master the System", subtitle_style))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2563EB"), spaceAfter=12))

    meta_text = (
        "<b>Target Engine:</b> Google Antigravity CLI (agy v1.4.12+) &nbsp;|&nbsp; "
        "<b>Architecture:</b> Warm Stream-JSON Engine &nbsp;|&nbsp; "
        "<b>Status:</b> Production Ready"
    )
    story.append(Paragraph(meta_text, ParagraphStyle('Meta', parent=body_style, fontSize=8, textColor=colors.HexColor("#64748B"))))
    story.append(Spacer(1, 10))

    exec_summary = (
        "<b>Executive Overview:</b> Antigravity Telegram Agent v5.1 bridges the gap between state-of-the-art autonomous AI "
        "engineering engines and the Telegram messaging interface. It enables software engineers and technical leaders "
        "to supervise codebases, execute terminal workflows, manage servers, schedule autonomous background routines, and "
        "orchestrate specialized subagent swarms from any mobile device or workstation with sub-second response times."
    )
    story.append(create_callout(exec_summary, "#F8FAFC", "#64748B"))
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 1: ARCHITECTURAL FOUNDATION & ZERO COLD-START
    # =========================================================================
    story.append(Paragraph("1. System Architecture & The Zero Cold-Start Engine", h1_style))
    story.append(Paragraph(
        "Standard CLI wrappers spawn a brand-new process on every single incoming prompt. In Google Antigravity CLI, "
        "initializing the runtime, loading configurations, authenticating Google identity, and registering tool catalogs takes "
        "<b>12 to 18 seconds</b> per query. Furthermore, a fresh process flushes Google AI's prompt cache, significantly increasing "
        "token costs and latency.", body_style
    ))
    story.append(Paragraph(
        "<b>Antigravity Telegram Agent v5.1 solves this via its Warm Stream-JSON Architecture:</b>", body_style
    ))
    story.append(Paragraph("• <b>Warm Persistent Process (agy_session.py):</b> A single Antigravity CLI process runs indefinitely in JSON streaming mode. User turns are delivered via standard input (stdin) and events are consumed from standard output (stdout) with zero initialization delay.", bullet_style))
    story.append(Paragraph("• <b>Prompt Cache Preservation:</b> System instructions, repository trees, and dynamic MCP schemas remain continuously cached in Google AI's memory, achieving up to 90% cost savings on recurring context.", bullet_style))
    story.append(Paragraph("• <b>Thread-Safe Asynchronous Turn Queue:</b> Inbound user messages, scheduled automation tasks, and subagent callbacks are strictly serialized to prevent race conditions or pipe deadlocks.", bullet_style))
    story.append(Paragraph("• <b>Live Multi-Stage Event Parsing:</b> The gateway decodes stream events in real time, separating internal chain-of-thought, terminal shell commands, file edits, and multi-agent delegation.", bullet_style))
    story.append(Spacer(1, 10))

    # =========================================================================
    # SECTION 2: HOW TO OPERATE THE SYSTEM VIA TELEGRAM
    # =========================================================================
    story.append(Paragraph("2. Operating the System via Telegram", h1_style))
    story.append(Paragraph(
        "Interacting with the system feels as natural as chatting with a senior staff engineer on Telegram. "
        "The interface is fortified with dynamic interactive controls and visual feedback.", body_style
    ))
    
    story.append(Paragraph("Interactive Thinking Bubble & Live Streaming", h2_style))
    story.append(Paragraph(
        "While the AI works, Telegram displays an animated status bubble with an active spinner (⣾, ⣽, ⣻). "
        "You witness the agent's thought trajectory and tool invocations as they occur. "
        "An inline <b>[🛑 Abort]</b> button lets you cancel long-running loops or misdirected commands instantly.", body_style
    ))

    story.append(Paragraph("Essential Telegram Command Matrix", h2_style))
    
    cmd_data = [
        [Paragraph("Command", table_header_style), Paragraph("Scope & Arguments", table_header_style), Paragraph("Operational Function", table_header_style)],
        [Paragraph("/start", table_code_style), Paragraph("None", table_cell_style), Paragraph("Initializes session, claims admin identity, opens dashboard.", table_cell_style)],
        [Paragraph("/settings", table_code_style), Paragraph("None", table_cell_style), Paragraph("Interactive control panel: Model, Effort, Mode, Sandboxing.", table_cell_style)],
        [Paragraph("/usage", table_code_style), Paragraph("None", table_cell_style), Paragraph("Real-time visual token gauges, cooldown timers, API ping test.", table_cell_style)],
        [Paragraph("/models", table_code_style), Paragraph("[model_name]", table_cell_style), Paragraph("Switch between Gemini 3.8 Flash, Gemini 2.5 Pro, Argon 4, Claude 3.7.", table_cell_style)],
        [Paragraph("/effort", table_code_style), Paragraph("[auto|low|med|high|max]", table_cell_style), Paragraph("Adjusts thinking reasoning budget. High/Max for architecture.", table_cell_style)],
        [Paragraph("/mode", table_code_style), Paragraph("[auto-approve|accept-edits|plan]", table_cell_style), Paragraph("Execution autonomy: Full auto, manual approvals, or plan-only.", table_cell_style)],
        [Paragraph("/tasks", table_code_style), Paragraph("None", table_cell_style), Paragraph("Inspect and manage scheduled automations, timers, and cron jobs.", table_cell_style)],
        [Paragraph("/agents", table_code_style), Paragraph("None", table_cell_style), Paragraph("Inspect, create, activate, export (ZIP), and import subagent swarms.", table_cell_style)],
        [Paragraph("/mcp", table_code_style), Paragraph("None", table_cell_style), Paragraph("Inspect connected Model Context Protocol servers and diagnostic status.", table_cell_style)],
        [Paragraph("/clear", table_code_style), Paragraph("None", table_cell_style), Paragraph("Flushes current conversational context while preserving long-term memory.", table_cell_style)],
        [Paragraph("/abort", table_code_style), Paragraph("None", table_cell_style), Paragraph("Immediately terminates active CLI execution and resets turn state.", table_cell_style)],
    ]
    
    t_cmd = Table(cmd_data, colWidths=[70, 110, letter[0] - 108 - 180])
    t_cmd.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('LEFTPADDING', (0,0), (-1,-1), 5),
        ('RIGHTPADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_cmd)
    story.append(Spacer(1, 10))

    # Media handling
    story.append(Paragraph("Multimedia & Bidirectional File Handling", h2_style))
    story.append(Paragraph(
        "The agent seamlessly ingests and generates diverse data formats:", body_style
    ))
    story.append(Paragraph("• <b>Inbound Media:</b> Drop screenshots of error traces or Figma mockups; the AI performs visual multimodal analysis. Send voice notes while on the move; the bot transcribes speech into text instructions automatically. Upload code files or ZIP archives to mount them directly into the workspace.", bullet_style))
    story.append(Paragraph("• <b>Outbound Media:</b> When the AI compiles a PDF report, renders an architecture diagram, creates a build artifact, or exports an archive, it automatically transmits the deliverable directly to your Telegram chat using <code>tg_send.py --file &lt;path&gt;</code>.", bullet_style))
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 3: HOW TO COMMUNICATE WITH THE AI
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("3. Conversational Engineering: How to Talk to the AI", h1_style))
    story.append(Paragraph(
        "Unlike generic consumer chatbots, Antigravity Telegram Agent is an autonomous engineering agent connected to your "
        "local filesystem, execution terminal, and git repositories. Communicating with precision yields extraordinary results.", body_style
    ))

    story.append(Paragraph("The Three Core Rules of Agent Prompting", h2_style))
    story.append(Paragraph("1. <b>Define Outcomes, Scope, and Boundaries:</b> State what files should be modified and what should remain untouched. Specify the test framework or coding style required.", bullet_style))
    story.append(Paragraph("2. <b>Demand Grounded Evidence & Verification:</b> Instruct the agent to run unit tests, check linter output, or verify HTTP responses before declaring completion. (e.g. <i>'Implement the endpoint and run pytest to confirm 100% pass rate.'</i>)", bullet_style))
    story.append(Paragraph("3. <b>Leverage Incremental Modularity:</b> For extensive architectural shifts, break tasks down into specification, implementation, and verification phases.", bullet_style))
    story.append(Spacer(1, 6))

    story.append(Paragraph("Specialized Operational Workflow Modes", h2_style))
    story.append(Paragraph(
        "The system ships with pre-engineered workflow commands that configure the reasoning engine on the fly:", body_style
    ))

    workflow_data = [
        [Paragraph("Mode / Slash Command", table_header_style), Paragraph("When to Use & Behavior", table_header_style)],
        [Paragraph("/plan [goal]", table_code_style), Paragraph("<b>Architectural Planning:</b> Analyzes the codebase and drafts a step-by-step verifiable blueprint without touching source code.", table_cell_style)],
        [Paragraph("/grill_me [concept]", table_code_style), Paragraph("<b>Interactive Interview:</b> Conducts a disciplined Socratic interview. Asks targeted architectural questions one by one before any code is written.", table_cell_style)],
        [Paragraph("/goal [task]", table_code_style), Paragraph("<b>Exhaustive Autonomous Execution:</b> Operates in deep pursuit mode. Verifies every step, writes unit tests, and does not stop until fully achieved.", table_cell_style)],
        [Paragraph("/boost [problem]", table_code_style), Paragraph("<b>Maximum Reasoning & Auditing:</b> Sets thinking effort to maximum, inspects edge cases, and cross-verifies logic using multi-perspective reasoning.", table_cell_style)],
        [Paragraph("/teamwork [mission]", table_code_style), Paragraph("<b>Multi-Agent Swarm Orchestration:</b> Deploys subagents in parallel to divide and conquer research, implementation, and QA simultaneously.", table_cell_style)],
    ]
    t_wf = Table(workflow_data, colWidths=[130, letter[0] - 108 - 130])
    t_wf.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_wf)
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 4: HOW TO CUSTOMIZE THE SYSTEM
    # =========================================================================
    story.append(Paragraph("4. Customization & Personalization Mastery", h1_style))
    story.append(Paragraph(
        "Antigravity Telegram Agent v5.1 provides unprecedented depth in personalizing behavior, personality, interpersonal "
        "speech rules, and specialized team structures.", body_style
    ))

    story.append(Paragraph("A. Person Profiles & Speech Tone Rules (mem.py person)", h2_style))
    story.append(Paragraph(
        "You can teach the agent exactly who individuals are, their relationship to you, and <b>how it must speak to them</b> "
        "(formal vs casual, French tutoiement vs vouvoiement):", body_style
    ))
    person_code = (
        '# Register Primary Owner with direct, technical tutoiement:\n'
        'python mem.py person add "Ange" --role "Lead Architect" --relation "Owner" \\\n'
        '  --tone "Tutoiement direct, concis, amical et technique" --aliases "ange,admin"\n\n'
        '# Register an Executive Client requiring strict formal vouvoiement:\n'
        'python mem.py person add "M. Dupont" --role "Chief Technology Officer" --relation "Client" \\\n'
        '  --tone "Vouvoiement formel, poli, rigoureux et respectueux"'
    )
    story.append(create_codebox(person_code))
    story.append(Spacer(1, 8))

    story.append(Paragraph("B. Social Graph & Relational Mapping (mem.py relate)", h2_style))
    story.append(Paragraph(
        "Track relationships between team members, partners, and contractors so the AI understands organizational context:", body_style
    ))
    relate_code = (
        'python mem.py relate "Ange" "co-founder" "Marc" --details "Co-owners of project Alpha"\n'
        'python mem.py relate "Marc" "manages" "Sophie" --details "Frontend engineering lead"\n'
        'python mem.py relate list'
    )
    story.append(create_codebox(relate_code))
    story.append(Spacer(1, 8))

    story.append(Paragraph("C. Creating Specialized Subagents (.agents/agents/*.md)", h2_style))
    story.append(Paragraph(
        "Subagents are defined as clean Markdown manifests with YAML frontmatter. Create them manually or say: "
        "<i>'Create a specialist subagent for PostgreSQL database indexing and query tuning'</i>:", body_style
    ))
    agent_manifest = (
        '---\n'
        'name: db_architect\n'
        'description: Senior PostgreSQL database architect and query optimization specialist.\n'
        'model: gemini-2.5-pro\n'
        'tools: [read_file, write_file, edit_file, run_command]\n'
        'skills: [database-architect, sql-optimization]\n'
        '---\n'
        'You are an elite database engineer. Analyze EXPLAIN ANALYZE traces, design B-Tree/GIN indexes,\n'
        'prevent N+1 query patterns, and ensure strict ACID transactional integrity.'
    )
    story.append(create_codebox(agent_manifest))
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 5: CAPABILITIES & ADVANCED FEATURES
    # =========================================================================
    story.append(PageBreak())
    story.append(Paragraph("5. Deep Capabilities & Advanced Autonomous Features", h1_style))
    story.append(Paragraph(
        "Antigravity Telegram Agent v5.1 represents the cutting edge in autonomous developer tools. "
        "Below are the primary subsystems that provide its industry-leading capabilities:", body_style
    ))

    story.append(Paragraph("1. Long-Term Hybrid Vector Memory (mem.py / memory.db)", h2_style))
    story.append(Paragraph(
        "Backed by SQLite and FastEmbed semantic embeddings, the agent retains persistent knowledge across chat resets and reboots. "
        "Categories include: <code>profile</code> (identity, hardware), <code>preferences</code> (formatting, frameworks), "
        "<code>projet</code> (git repos, active milestones), <code>infra</code> (IPs, Docker containers, ports), and "
        "<code>rules</code> (permanent operating constraints).", body_style
    ))

    story.append(Paragraph("2. Native Background Task Scheduler & Autonomous Automations (tasks.py)", h2_style))
    story.append(Paragraph(
        "The agent includes a persistent daemon worker running an independent SQLite task queue. "
        "Schedule tasks effortlessly using plain English, relative intervals, or cron schedules:", body_style
    ))
    tasks_code = (
        '# One-shot reminder in 45 minutes:\n'
        'python tasks.py add "Check staging build and verify logs" --when "in 45m" --name "check_staging"\n\n'
        '# Recurring health-check every 3 hours:\n'
        'python tasks.py add "Verify Docker containers status and report anomalies" --when "every 3h"\n\n'
        '# Daily executive morning briefing at 08:30 AM:\n'
        'python tasks.py add "Generate daily agenda, server status, and AI news brief" --when "08:30"'
    )
    story.append(create_codebox(tasks_code))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Official Google Antigravity Quotas & Cross-Family Fallback Ladder", h2_style))
    story.append(Paragraph(
        "Google Antigravity enforces strict rolling quotas for premium reasoning models. "
        "The gateway parses exact reset cooldowns from API headers and manages an automatic fallback ladder:", body_style
    ))
    fallback_box = (
        "<b>Quota Fallback Sequence:</b><br/>"
        "Claude 3.7 Sonnet &nbsp;➔&nbsp; Claude 3.5 Sonnet &nbsp;➔&nbsp; Gemini 2.5 Pro / Argon 4 &nbsp;➔&nbsp; Gemini 3.8 Flash<br/>"
        "<i>Result: Your workflows, deployments, and debugging sessions never freeze or fail due to credit exhaustion.</i>"
    )
    story.append(create_callout(fallback_box, "#EFF6FF", "#2563EB"))
    story.append(Spacer(1, 8))

    story.append(Paragraph("4. Group Chat Stealth Mode & Anti-Prompt Injection", h2_style))
    story.append(Paragraph(
        "When added to team or community Telegram groups, the bot automatically engages Stealth Observation Mode. "
        "Group members cannot trigger subagent installation, file writes, terminal execution, or prompt injections. "
        "The bot only executes privileged commands when explicitly invoked by the authenticated Administrator.", body_style
    ))

    story.append(Paragraph("5. Zero-Data-Loss Self-Updater (/update)", h2_style))
    story.append(Paragraph(
        "The agent monitors official upstream updates on GitHub. When <code>/update</code> is triggered, it creates an "
        "atomic backup of <code>.env</code>, <code>settings.json</code>, <code>memory.db</code>, and <code>.agents/</code>, "
        "pulls the new release, executes migrations, and hot-reloads the daemon without dropping active Telegram connections.", body_style
    ))
    story.append(Spacer(1, 14))

    # =========================================================================
    # SECTION 6: TROUBLESHOOTING & CHEAT SHEET
    # =========================================================================
    story.append(Paragraph("6. Troubleshooting, Best Practices & Quick Reference", h1_style))
    
    faq_data = [
        [Paragraph("Symptom / Scenario", table_header_style), Paragraph("Diagnostic Cause", table_header_style), Paragraph("Prescribed Solution", table_header_style)],
        [
            Paragraph("Bot ignores messages", table_code_style),
            Paragraph("Sender ID does not match <code>ALLOWED_USER_ID</code>.", table_cell_style),
            Paragraph("Check your Telegram user ID via @userinfobot and update <code>.env</code>.", table_cell_style)
        ],
        [
            Paragraph("Claude quota exhausted", table_code_style),
            Paragraph("Rolling token quota limit reached in Google Antigravity.", table_cell_style),
            Paragraph("Agent automatically uses Gemini Pro. View countdown in <code>/usage</code>.", table_cell_style)
        ],
        [
            Paragraph("Process looping or stuck", table_code_style),
            Paragraph("Subprocess waiting on blocking terminal prompt.", table_cell_style),
            Paragraph("Send <code>/abort</code> or tap the inline 🛑 Abort button.", table_cell_style)
        ],
        [
            Paragraph("Reset context cleanly", table_code_style),
            Paragraph("Context window full of obsolete debugging history.", table_cell_style),
            Paragraph("Send <code>/clear</code>. Long-term memory and person facts remain preserved.", table_cell_style)
        ],
    ]
    t_faq = Table(faq_data, colWidths=[100, 150, letter[0] - 108 - 250])
    t_faq.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CBD5E1")),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")]),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t_faq)
    story.append(Spacer(1, 14))

    closing_notice = (
        "<b>Security & Responsibility Notice:</b> Antigravity Telegram Agent v5.1 has full terminal and filesystem access "
        "according to your configured permissions. Keep your <code>TELEGRAM_BOT_TOKEN</code> strictly private, enforce "
        "<code>ALLOWED_USER_ID</code>, and keep workspace sandboxing enabled when running in shared environments."
    )
    story.append(create_callout(closing_notice, "#FEF2F2", "#EF4444"))

    # Build document
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"Successfully generated PDF manual: {filename}")

if __name__ == "__main__":
    output_filename = "c:/Users/ange-/Downloads/X96-Agent/Antigravity_Telegram_Agent_Manual_EN.pdf"
    build_pdf(output_filename)
