"""
school_manager.py - School, Homework & Course Intelligence Assistant
Passively monitors authorized school group chats to:
- Automatically extract homework assignments, due dates, subjects, and teachers
- Index lessons learned and course topics for instant AI revision and tutoring
- Trigger proactive reminders the day before homework is due
- Feed relevant classroom context to the Antigravity agent
"""

import re
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from config import BASE_DIR
from memory_manager import add_or_update_memory

logger = logging.getLogger("school_manager")

SCHOOL_DATA_FILE = BASE_DIR / "school_data.json"

FRENCH_DAYS = {
    "lundi": 0,
    "mardi": 1,
    "mercredi": 2,
    "jeudi": 3,
    "vendredi": 4,
    "samedi": 5,
    "dimanche": 6,
}

SUBJECT_PATTERNS = {
    "Mathématiques": [r"\bmaths?\b", r"\bmath[eé]matiques?\b", r"\bmathematics\b", r"\balg[eè]bre\b", r"\balgebra\b", r"\bg[eé]om[eé]trie\b", r"\bgeometry\b"],
    "Français": [r"\bfran[cç]ais\b", r"\bfrench\b", r"\blitt[eé]rature\b", r"\bgrammaire\b", r"\borthographe\b"],
    "Histoire-Géo": [r"\bhistoire\b", r"\bhistory\b", r"\bg[eé]o(?:graphie)?\b", r"\bgeography\b", r"\bhg\b", r"\bsocial\s+studies\b", r"\bemc\b"],
    "Physique-Chimie": [r"\bphysique\b", r"\bphysics\b", r"\bchimie\b", r"\bchemistry\b", r"\bpc\b", r"\bsciences?\b"],
    "SVT": [r"\bsvt\b", r"\bbiologie\b", r"\bbiology\b", r"\bg[eé]ologie\b", r"\bsciences\s+de\s+la\s+vie\b"],
    "Anglais": [r"\banglais\b", r"\benglish\b", r"\blanguage\s+arts\b"],
    "Khmer": [r"\bkhmer\b", r"\bcambodian\b"],
    "Espagnol": [r"\bespagnol\b", r"\bspanish\b"],
    "Allemand": [r"\ballemand\b", r"\bgerman\b"],
    "Philosophie": [r"\bphilo(?:sophie)?\b"],
    "SES": [r"\bses\b", r"\b[eé]conomie\b", r"\beconomics\b", r"\bsocio(?:logie)?\b"],
    "Technologie / Info": [r"\btechno(?:logie)?\b", r"\binformatique\b", r"\bict\b", r"\bcomputer\b", r"\bnsi\b", r"\bsnt\b"],
    "EPS": [r"\beps\b", r"\bsport\b", r"\bpe\b", r"\bphysical\s+education\b"],
    "Arts": [r"\barts?\s+plastiques?\b", r"\bdessin\b", r"\bart\b"],
    "Musique": [r"\bmusique\b", r"\bmusic\b"],
}

HW_TRIGGER_WORDS = [
    "devoir", "devoirs", "dm", "ds", "dst", "exercice", "exercices",
    "exos", "exo", "pour demain", "à rendre", "a rendre", "évaluation",
    "evaluation", "interro", "interrogation", "contrôle", "controle",
    "faire pour", "réviser", "reviser", "leçon à apprendre", "lecon a apprendre",
    "homework", "hw", "assignment", "assignments", "task", "quiz", "test",
    "exam", "due tomorrow", "due", "to submit", "for tomorrow"
]

LESSON_TRIGGER_WORDS = [
    "aujourd'hui", "aujourdhui", "on a fait", "nous avons fait",
    "cours du", "chapitre", "leçon", "lecon", "thème", "theme",
    "au programme", "notions vues", "résumé du cours", "resume du cours",
    "today's lesson", "today's lessons", "updates for today", "lessons",
    "lesson", "review", "subject", "+subject"
]


class SchoolManager:
    """Manages homework tracking, course logs, and intelligent reminders."""

    def __init__(self, file_path: Path = SCHOOL_DATA_FILE):
        self.file_path = file_path
        self._data: Dict[str, Any] = {
            "homework": [],
            "lessons": [],
            "teachers": {},
            "timetable": {
                "lundi": ["Mathématiques", "Histoire-Géo", "Anglais"],
                "mardi": ["Physique-Chimie", "Français", "SVT"],
                "mercredi": ["Mathématiques", "EPS"],
                "jeudi": ["Français", "Histoire-Géo", "Espagnol"],
                "vendredi": ["Mathématiques", "Physique-Chimie", "Anglais"],
            },
            "last_reminder_date": "",
        }
        self._load()

    def _load(self) -> None:
        if self.file_path.is_file():
            try:
                raw = json.loads(self.file_path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data.update(raw)
                    return
            except Exception as e:
                logger.error(f"Error loading {self.file_path}: {e}")

    def _save(self) -> bool:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.file_path)
            return True
        except Exception as e:
            logger.error(f"Error saving {self.file_path}: {e}")
            return False

    def detect_subject(self, text: str) -> str:
        """Identify academic subject from text."""
        lower = text.lower()
        for subj, patterns in SUBJECT_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, lower):
                    return subj
        return "Général"

    def parse_due_date(self, text: str, reference_date: Optional[datetime] = None) -> Tuple[Optional[str], str]:
        """
        Extract due date (YYYY-MM-DD and friendly label) from French natural language text.
        """
        ref = reference_date or datetime.now()
        lower = text.lower()

        # Demain / Après-demain
        if "après-demain" in lower or "apres demain" in lower:
            target = ref + timedelta(days=2)
            return target.strftime("%Y-%m-%d"), target.strftime("%A %d %B").capitalize()
        if "demain" in lower:
            target = ref + timedelta(days=1)
            return target.strftime("%Y-%m-%d"), target.strftime("%A %d %B").capitalize()

        # Jour de la semaine (e.g. "pour lundi", "pour mardi prochain")
        for day_name, day_idx in FRENCH_DAYS.items():
            pattern = rf"\b(?:pour|avant|le)\s+(?:ce\s+|le\s+)?{day_name}\b"
            if re.search(pattern, lower):
                current_weekday = ref.weekday()
                days_ahead = (day_idx - current_weekday) % 7
                if days_ahead == 0:
                    days_ahead = 7
                target = ref + timedelta(days=days_ahead)
                return target.strftime("%Y-%m-%d"), f"{day_name.capitalize()} {target.strftime('%d/%m')}"

        # Date explicite: "pour le 24 octobre", "pour le 24/10"
        m_slash = re.search(r"\b(?:pour|le)\s+(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", lower)
        if m_slash:
            day, month = int(m_slash.group(1)), int(m_slash.group(2))
            year = int(m_slash.group(3)) if m_slash.group(3) else ref.year
            if year < 100:
                year += 2000
            try:
                target = datetime(year, month, day)
                return target.strftime("%Y-%m-%d"), target.strftime("%d/%m/%Y")
            except Exception:
                pass

        # Par défaut si devoir détecté sans date: prochain jour ouvré
        target = ref + timedelta(days=1)
        if target.weekday() == 5:  # Samedi -> Lundi
            target += timedelta(days=2)
        elif target.weekday() == 6:  # Dimanche -> Lundi
            target += timedelta(days=1)
        return target.strftime("%Y-%m-%d"), "Prochain cours"

    def analyze_incoming_message(
        self,
        text: str,
        sender_name: str = "",
        chat_title: str = "",
        chat_id: int = 0,
    ) -> Dict[str, Any]:
        """
        Passive analysis of incoming messages in school groups.
        Extracts homework and lesson summaries if detected.
        """
        if not text or len(text.strip()) < 8:
            return {}

        lower = text.lower()
        subject = self.detect_subject(text)
        detected_events = {}

        # 1. Homework Detection
        is_hw = any(w in lower for w in HW_TRIGGER_WORDS)
        if is_hw:
            due_iso, due_label = self.parse_due_date(text)
            hw_id = f"hw_{int(datetime.now().timestamp())}_{len(self._data['homework']) + 1}"
            hw_item = {
                "id": hw_id,
                "subject": subject,
                "description": text.strip(),
                "assigned_at": datetime.now().strftime("%Y-%m-%d"),
                "due_date": due_iso or "",
                "due_date_label": due_label,
                "sender": sender_name or "Professeur / Camarade",
                "chat_title": chat_title,
                "chat_id": chat_id,
                "status": "pending",
            }
            self._data["homework"].append(hw_item)
            detected_events["homework"] = hw_item
            logger.info(f"Homework recorded: [{subject}] Due {due_label}: {text[:60]}")

            # Store in unified memory for Antigravity AI
            try:
                add_or_update_memory(
                    fact=f"Devoir de {subject} assigné dans '{chat_title}' (Pour {due_label}) : {text[:140]}",
                    category="projet",
                    key=f"devoir_{hw_id}",
                    importance=5,
                )
            except Exception as me:
                logger.debug(f"Memory store warning: {me}")

        # 2. Lesson / Course Summary Detection
        is_lesson = any(w in lower for w in LESSON_TRIGGER_WORDS)
        if is_lesson or (subject != "Général" and len(text) > 80):
            lesson_id = f"les_{int(datetime.now().timestamp())}_{len(self._data['lessons']) + 1}"
            lesson_item = {
                "id": lesson_id,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "subject": subject,
                "summary": text.strip(),
                "sender": sender_name,
                "chat_title": chat_title,
            }
            # Keep last 50 lessons
            self._data["lessons"].append(lesson_item)
            if len(self._data["lessons"]) > 50:
                self._data["lessons"].pop(0)
            detected_events["lesson"] = lesson_item

            try:
                add_or_update_memory(
                    fact=f"Cours de {subject} le {datetime.now().strftime('%d/%m/%Y')} : {text[:160]}",
                    category="projet",
                    key=f"cours_{subject.lower()}_{datetime.now().strftime('%Y%m%d')}",
                    importance=4,
                )
            except Exception as me:
                logger.debug(f"Memory store warning: {me}")

        if detected_events:
            self._save()

        return detected_events

    def get_pending_homework(self) -> List[Dict[str, Any]]:
        return [h for h in self._data.get("homework", []) if h.get("status") == "pending"]

    def mark_homework_done(self, hw_id: str) -> bool:
        for h in self._data.get("homework", []):
            if h.get("id") == hw_id:
                h["status"] = "done"
                h["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self._save()
                return True
        return False

    def get_homework_due_soon(self, days_ahead: int = 1) -> List[Dict[str, Any]]:
        """Return pending homework due within the next N days."""
        now = datetime.now().date()
        target_dates = [(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_ahead + 1)]
        results = []
        for h in self.get_pending_homework():
            if h.get("due_date") in target_dates:
                results.append(h)
        return results

    def get_homework_due_tomorrow(self) -> List[Dict[str, Any]]:
        tomorrow = (datetime.now().date() + timedelta(days=1)).strftime("%Y-%m-%d")
        return [h for h in self.get_pending_homework() if h.get("due_date") == tomorrow]

    def has_sent_reminder_today(self) -> bool:
        today_str = datetime.now().strftime("%Y-%m-%d")
        return self._data.get("last_reminder_date") == today_str

    def mark_reminder_sent_today(self) -> None:
        self._data["last_reminder_date"] = datetime.now().strftime("%Y-%m-%d")
        self._save()

    def get_lessons_for_subject(self, subject: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieve recent lessons for a given subject."""
        subj_lower = subject.lower()
        matched = []
        for l in reversed(self._data.get("lessons", [])):
            if subj_lower in l.get("subject", "").lower() or subj_lower in l.get("summary", "").lower():
                matched.append(l)
                if len(matched) >= limit:
                    break
        return matched

    def get_school_context_for_agent(self, user_query: str) -> str:
        """
        Builds a dedicated prompt section if user asks about school, homework, or courses.
        E.g. 'Fais-moi un cours sur ce qu'on a appris aujourd'hui en maths'
        """
        lower = user_query.lower()
        is_school_query = any(k in lower for k in [
            "cours", "leçon", "lecon", "devoir", "devoirs", "appris", "maths",
            "français", "histoire", "physique", "svt", "école", "ecole", "classe"
        ])
        if not is_school_query:
            return ""

        lines = ["[INFORMATIONS SCOLAIRES EXTRAITES DU GROUPE DE L'ÉCOLE]"]
        pending = self.get_pending_homework()
        if pending:
            lines.append("📚 Devoirs en attente :")
            for h in pending[:5]:
                lines.append(f"- [{h['subject']}] Pour {h.get('due_date_label', 'bientôt')} : {h['description'][:100]}")

        # Check for specific subject
        detected_subj = self.detect_subject(user_query)
        recent_lessons = self.get_lessons_for_subject(detected_subj if detected_subj != "Général" else "", limit=3)
        if recent_lessons:
            lines.append(f"\n📖 Derniers cours & notions enregistrées ({detected_subj}) :")
            for les in recent_lessons:
                lines.append(f"- ({les['date']} - {les['subject']}) : {les['summary'][:150]}")

        lines.append(
            "\nNote : Utilise ces informations précises enregistrées depuis le groupe scolaire de l'utilisateur "
            "pour lui faire des cours sur-mesure, des fiches de révision claires et lui rappeler ses devoirs !"
        )
        return "\n".join(lines)

    def format_homework_html(self) -> str:
        pending = self.get_pending_homework()
        if not pending:
            return "🎉 <b>Aucun devoir en attente !</b> Vous êtes complètement à jour."

        lines = ["📚 <b>Liste des Devoirs en Attente :</b>\n"]
        for idx, h in enumerate(pending, 1):
            due = h.get("due_date_label") or h.get("due_date") or "Date non spécifiée"
            subj = h.get("subject", "Général")
            desc = h.get("description", "").replace("<", "&lt;").replace(">", "&gt;")
            if len(desc) > 160:
                desc = desc[:157] + "..."
            lines.append(
                f"<b>{idx}. [{subj}] Pour : {due}</b>\n"
                f"📝 <i>{desc}</i>\n"
            )
        return "\n".join(lines)


school_mgr = SchoolManager()
