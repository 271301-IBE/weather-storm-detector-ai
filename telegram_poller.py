"""Telegram polling service using getUpdates (no public webhook required).

Starts a background thread that long-polls Telegram for new messages and
handles commands like /weather by sending a summary and optional chart.
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import Config
from storage import WeatherDatabase
from telegram_notifier import TelegramNotifier
from pdf_generator import WeatherReportGenerator

logger = logging.getLogger(__name__)

_poller_started = False


class TelegramPoller:
    def __init__(self, config: Config, offset_file: str = "telegram_offset.txt"):
        self.config = config
        self.db = WeatherDatabase(config)
        self.notifier = TelegramNotifier(config)
        self.base_url = f"https://api.telegram.org/bot{self.config.telegram.bot_token}"
        self.running = False
        self.offset_file = offset_file
        self.last_update_id: Optional[int] = self._load_offset()
        self.thread: Optional[threading.Thread] = None
        self.settings_file = "settings_override.json"

    def _load_offset(self) -> Optional[int]:
        try:
            if os.path.exists(self.offset_file):
                with open(self.offset_file, "r", encoding="utf-8") as f:
                    value = f.read().strip()
                    return int(value) if value else None
        except Exception as e:
            logger.warning(f"Could not read Telegram offset file: {e}")
        return None

    def _save_offset(self, update_id: int):
        try:
            with open(self.offset_file, "w", encoding="utf-8") as f:
                f.write(str(update_id))
        except Exception as e:
            logger.warning(f"Could not write Telegram offset file: {e}")

    def _load_settings(self):
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    s = json.load(f)
                qh = s.get("quiet_hours_enabled")
                if isinstance(qh, bool):
                    self.config.system.quiet_hours_enabled = qh
                qhs = s.get("quiet_hours_start")
                qhe = s.get("quiet_hours_end")
                if isinstance(qhs, str):
                    self.config.system.quiet_hours_start = qhs
                if isinstance(qhe, str):
                    self.config.system.quiet_hours_end = qhe
                thr = s.get("storm_confidence_threshold")
                if isinstance(thr, (int, float)):
                    self.config.ai.storm_confidence_threshold = float(thr)
                logger.info("Loaded settings overrides from settings_override.json")
        except Exception as e:
            logger.warning(f"Failed to load settings overrides: {e}")

    def _persist_settings(self):
        try:
            payload = {
                "quiet_hours_enabled": bool(self.config.system.quiet_hours_enabled),
                "quiet_hours_start": self.config.system.quiet_hours_start,
                "quiet_hours_end": self.config.system.quiet_hours_end,
                "storm_confidence_threshold": float(self.config.ai.storm_confidence_threshold),
            }
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist settings: {e}")

    def _record_user_event(self, event_type: str):
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_storm_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        weather_data_json TEXT,
                        chmi_warnings_json TEXT,
                        ai_confidence REAL,
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO user_storm_events (timestamp, event_type, weather_data_json, chmi_warnings_json, ai_confidence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (datetime.now().isoformat(), event_type, json.dumps([]), json.dumps([]), None)
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to record user event {event_type}: {e}")

    def start(self):
        if self.running:
            return
        # load persisted overrides if present
        self._load_settings()
        self.running = True
        self.thread = threading.Thread(target=self.run, name="TelegramPoller", daemon=True)
        self.thread.start()
        logger.info("Telegram getUpdates poller started")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def _compose_weather_summary(self) -> str:
        # Aktuální podmínky
        current_text = "N/A"
        try:
            with self.db.get_connection(read_only=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT timestamp, temperature, humidity, pressure, wind_speed, precipitation, description
                    FROM weather_data ORDER BY timestamp DESC LIMIT 1
                    """
                )
                row = cur.fetchone()
                if row and row[1] is not None:
                    current_text = (
                        f"Nyní: {row[6] or ''} | Teplota {row[1]:.1f}°C, Vlhkost {row[2]:.0f}%, "
                        f"Tlak {row[3]:.0f} hPa, Vítr {row[4]:.1f} m/s, Srážky {row[5]:.1f} mm"
                    )
                elif row:
                    current_text = f"Nyní: {row[6] or ''}"
        except Exception:
            pass

        # Další předpokládaná bouřka
        storm_line = "Bouřka se neočekává"
        try:
            with self.db.get_connection(read_only=True) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT prediction_timestamp, confidence, created_at
                    FROM thunderstorm_predictions ORDER BY created_at DESC LIMIT 1
                    """
                )
                p = cur.fetchone()
                if p:
                    try:
                        predicted_dt = datetime.fromisoformat(p[0])
                        if predicted_dt > datetime.now():
                            storm_line = f"Bouřka ▶ {predicted_dt.strftime('%d.%m %H:%M')} (spolehlivost {float(p[1])*100:.0f}%)"
                    except Exception:
                        pass
        except Exception:
            pass

        # ČHMÚ výstrahy
        try:
            from chmi_warnings import ChmiWarningMonitor
            chmi_monitor = ChmiWarningMonitor(self.config)
            warnings = chmi_monitor.get_all_active_warnings()
            region_hits = []
            for w in warnings:
                desc = getattr(w, 'area_description', '') or ''
                if 'jihomorav' in desc.lower() or 'brno' in desc.lower():
                    region_hits.append(w)
            if region_hits:
                chmi_line = "ČHMÚ: " + ", ".join([f"{w.event} ({w.color})" for w in region_hits[:5]])
            else:
                chmi_line = "ČHMÚ: žádné pro region"
        except Exception:
            chmi_line = "ČHMÚ: nedostupné"

        # Blesky (poslední hodina)
        try:
            with self.db.get_connection(read_only=True) as conn:
                cur = conn.cursor()
                one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
                try:
                    cur.execute(
                        """
                        SELECT COALESCE(SUM(total_strikes),0), COALESCE(SUM(nearby_strikes),0), MIN(closest_strike_distance)
                        FROM lightning_activity_summary WHERE hour_timestamp > ?
                        """,
                        (one_hour_ago,)
                    )
                    row = cur.fetchone()
                    lt_line = f"Blesky: celkem {row[0] or 0}, v okolí {row[1] or 0}, nejbližší {row[2]:.1f} km" if row and row[2] is not None else f"Blesky: celkem {row[0] or 0}, v okolí {row[1] or 0}"
                except Exception:
                    cur.execute(
                        """
                        SELECT COUNT(*), COUNT(CASE WHEN distance_from_brno <= 50 THEN 1 END), MIN(distance_from_brno)
                        FROM lightning_strikes WHERE timestamp > ?
                        """,
                        (one_hour_ago,)
                    )
                    row = cur.fetchone()
                    lt_line = f"Blesky: celkem {row[0] or 0}, v okolí {row[1] or 0}, nejbližší {row[2]:.1f} km" if row and row[2] is not None else f"Blesky: celkem {row[0] or 0}, v okolí {row[1] or 0}"
        except Exception:
            lt_line = "Blesky: nedostupné"

        summary_text = (
            f"<b>{self.config.weather.city_name}</b> • {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
            f"{current_text}\n{storm_line}\n{chmi_line}\n{lt_line}"
        )
        return summary_text

    def _handle_command(self, chat_id: str, text: str):
        cmd = (text or "").strip().lower()
        if cmd.startswith("/start"):
            self.notifier.send_message(
                (
                    "👋 Ahoj! Jsem váš Clipron AI Weather bot.\n"
                    "Napište /pomoc pro přehled příkazů, nebo /weather pro rychlý souhrn s grafem."
                ),
                chat_id=chat_id,
            )
            return
        if cmd.startswith("/pomoc"):
            help_text = (
                "📖 Nápověda:\n"
                "• /weather – Souhrn aktuálního počasí a graf (24h)\n"
                "• /pomoc – Tento přehled příkazů\n"
                "• /nastaveni status – Zobrazit stav tichých hodin a prahu spolehlivosti\n"
                "• /nastaveni tiche_hodiny on|off – Zapnout/vypnout tiché hodiny\n"
                "• /nastaveni prah 0–1 – Nastavit prah spolehlivosti (např. 0.85)\n"
                "• Učení: pošlete zprávu ‚déšť‘, ‚krupobití‘, nebo ‚bez_bouře‘\n"
            )
            self.notifier.send_message(help_text, chat_id=chat_id)
            return
        if cmd.startswith("/nastaveni"):
            parts = cmd.split()
            if len(parts) == 1 or parts[1] == "status":
                status_msg = (
                    f"🔧 Nastavení:\n"
                    f"• Tiché hodiny: {'ZAPNUTO' if self.config.system.quiet_hours_enabled else 'VYPNUTO'} ({self.config.system.quiet_hours_start}–{self.config.system.quiet_hours_end})\n"
                    f"• Prah spolehlivosti: {self.config.ai.storm_confidence_threshold:.2f}"
                )
                self.notifier.send_message(status_msg, chat_id=chat_id)
                return
            if parts[1] == "tiche_hodiny" and len(parts) >= 3:
                val = parts[2]
                if val in ("on", "zapnout", "zapnuto"):
                    self.config.system.quiet_hours_enabled = True
                    self._persist_settings()
                    self.notifier.send_message("✅ Tiché hodiny ZAPNUTY.", chat_id=chat_id)
                    return
                if val in ("off", "vypnout", "vypnuto"):
                    self.config.system.quiet_hours_enabled = False
                    self._persist_settings()
                    self.notifier.send_message("✅ Tiché hodiny VYPNUTY.", chat_id=chat_id)
                    return
                self.notifier.send_message("❌ Neplatná hodnota. Použijte on/off.", chat_id=chat_id)
                return
            if parts[1] == "prah" and len(parts) >= 3:
                try:
                    val = float(parts[2].replace(',', '.'))
                    if 0.0 <= val <= 1.0:
                        self.config.ai.storm_confidence_threshold = val
                        self._persist_settings()
                        self.notifier.send_message(
                            f"✅ Prah spolehlivosti nastaven na {val:.2f}", chat_id=chat_id
                        )
                        return
                except Exception:
                    pass
                self.notifier.send_message("❌ Zadejte číslo v intervalu 0–1 (např. 0.85).", chat_id=chat_id)
                return
            self.notifier.send_message("❔ Použití: /nastaveni status | tiche_hodiny on|off | prah 0.85", chat_id=chat_id)
            return
        if cmd in ("déšť", "dest", "déšt", "dést", "rain"):
            self._record_user_event("rain_now")
            self.notifier.send_message("✔️ Díky! Zaznamenal jsem událost: déšť.", chat_id=chat_id)
            return
        if cmd in ("krupobití", "krupobiti", "hail"):
            self._record_user_event("hail_now")
            self.notifier.send_message("✔️ Díky! Zaznamenal jsem událost: krupobití.", chat_id=chat_id)
            return
        if cmd in ("bez_bouře", "bez-bouře", "bez_boure", "no_storm", "clear"):
            self._record_user_event("no_storm")
            self.notifier.send_message("✔️ Rozumím. Zaznamenal jsem: bez bouře.", chat_id=chat_id)
            return
        if cmd.startswith("/weather"):
            logger.info(f"Polling: handling /weather for chat_id={chat_id}")
            summary = self._compose_weather_summary()
            sent = self.notifier.send_message(summary, chat_id=chat_id)
            logger.info(f"Polling: /weather text sent ok={sent}")
            # Try to send chart
            try:
                series = list(reversed(self.db.get_recent_weather_data(hours=24)))[:120]
                if series:
                    gen = WeatherReportGenerator(self.config)
                    img_path = gen.create_chart_image(series, datetime.now())
                    if img_path:
                        photo_ok = self.notifier.send_photo(img_path, caption="Graf počasí za 24 hodin", chat_id=chat_id)
                        logger.info(f"Polling: /weather photo sent ok={photo_ok}")
            except Exception as e:
                logger.warning(f"Polling: chart send failed: {e}")

    def run(self):
        while self.running:
            try:
                params = {
                    "timeout": 50,
                    "allowed_updates": json.dumps(["message"]),
                }
                if self.last_update_id is not None:
                    params["offset"] = self.last_update_id + 1
                resp = requests.get(f"{self.base_url}/getUpdates", params=params, timeout=60)
                if not resp.ok:
                    logger.warning(f"getUpdates HTTP {resp.status_code}: {resp.text}")
                    time.sleep(2)
                    continue
                data = resp.json()
                if not data.get("ok"):
                    logger.warning(f"getUpdates not ok: {data}")
                    time.sleep(2)
                    continue
                updates = data.get("result", [])
                if not updates:
                    continue
                for upd in updates:
                    try:
                        self.last_update_id = max(self.last_update_id or 0, upd.get("update_id", 0))
                        msg = upd.get("message") or {}
                        text = msg.get("text")
                        chat = msg.get("chat") or {}
                        chat_id = str(chat.get("id")) if chat.get("id") is not None else None
                        logger.debug(f"Polling: update {upd.get('update_id')} chat_id={chat_id} text={text!r}")
                        if chat_id and text and text.startswith('/'):
                            self._handle_command(chat_id, text)
                    finally:
                        if self.last_update_id:
                            self._save_offset(self.last_update_id)
            except Exception as e:
                logger.error(f"Polling error: {e}")
                time.sleep(3)


def start_telegram_polling(config: Config):
    global _poller_started
    if _poller_started:
        return
    poller = TelegramPoller(config)
    poller.start()
    _poller_started = True
    return poller


