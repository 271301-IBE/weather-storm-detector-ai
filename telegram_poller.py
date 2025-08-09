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
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "Tiché hodiny ON", "callback_data": "qh:on"},
                        {"text": "Tiché hodiny OFF", "callback_data": "qh:off"},
                    ],
                    [
                        {"text": "Prahová 0.80", "callback_data": "thr:0.80"},
                        {"text": "Prahová 0.90", "callback_data": "thr:0.90"},
                    ],
                    [
                        {"text": "Graf 12h", "callback_data": "graph:12"},
                        {"text": "Graf 24h", "callback_data": "graph:24"},
                        {"text": "Graf 48h", "callback_data": "graph:48"},
                    ],
                ]
            }
            self.notifier.send_message(
                (
                    "👋 Ahoj! Jsem váš Clipron AI Weather bot.\n"
                    "Napište /pomoc pro přehled příkazů, nebo /weather pro rychlý souhrn s grafem."
                ),
                chat_id=chat_id,
                reply_markup=keyboard,
            )
            return
        if cmd.startswith("/pomoc"):
            help_text = (
                "📖 Nápověda:\n"
                "• /weather – Souhrn aktuálního počasí a graf (24h)\n"
                "• /pomoc – Tento přehled příkazů\n"
                "• /radar – Aktuální radarový snímek (ČHMÚ)\n"
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
            keyboard = {
                "inline_keyboard": [
                    [
                        {"text": "Tiché hodiny ON", "callback_data": "qh:on"},
                        {"text": "Tiché hodiny OFF", "callback_data": "qh:off"},
                    ],
                    [
                        {"text": "Prahová 0.80", "callback_data": "thr:0.80"},
                        {"text": "Prahová 0.90", "callback_data": "thr:0.90"},
                    ],
                    [
                        {"text": "Graf 12h", "callback_data": "graph:12"},
                        {"text": "Graf 24h", "callback_data": "graph:24"},
                        {"text": "Graf 48h", "callback_data": "graph:48"},
                    ],
                ]
            }
            sent = self.notifier.send_message(summary, chat_id=chat_id, reply_markup=keyboard)
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
            return

        if cmd.startswith("/radar"):
            try:
                import tempfile
                from datetime import timezone
                try:
                    from PIL import Image, ImageOps
                    pil_available = True
                except Exception:
                    pil_available = False

                # 1) Najít nejnovější dostupný snímek (výchozí 180 min po 10 min; konfigurovatelné)
                base = (self.config.chmi.radar_pattern_url or '').strip()
                if not base:
                    base = "https://opendata.chmi.cz/meteorology/weather/radar/composite/maxz/png/pacz2gmaps3.z_max3d.{date}.{time}.0.png"
                now_utc = datetime.now(timezone.utc)
                try:
                    from zoneinfo import ZoneInfo
                    tz_prg = ZoneInfo("Europe/Prague")
                except Exception:
                    tz_prg = None

                try:
                    lookback_minutes = int(os.getenv("CHMI_RADAR_LOOKBACK_MINUTES", "180"))
                except Exception:
                    lookback_minutes = 180
                lookback_minutes = max(10, min(720, lookback_minutes))  # 10 min .. 12 h

                chosen_url = None
                chosen_dt = None
                content = None
                attempts_per_tz = (lookback_minutes // 10) + 1
                tried_log = []
                for tz_name, tz in (("UTC", timezone.utc), ("Europe/Prague", tz_prg)):
                    if tz is None:
                        continue
                    base_now = now_utc if tz_name == "UTC" else datetime.now(tz)
                    for step in range(0, attempts_per_tz):
                        dt = base_now - timedelta(minutes=step * 10)
                        date_str = dt.strftime('%Y%m%d')
                        time_str = dt.strftime('%H%M')
                        candidate = base.format(date=date_str, time=time_str)
                        try:
                            resp = requests.get(candidate, timeout=12)
                            ct = resp.headers.get('Content-Type', '') if resp is not None else ''
                            tried_log.append(f"{tz_name} {date_str} {time_str} -> {resp.status_code if resp is not None else 'ERR'} {ct}")
                            if resp.ok and (ct.startswith('image') or candidate.lower().endswith('.png')):
                                chosen_url = candidate
                                chosen_dt = dt if tz_name == "UTC" else dt.astimezone(timezone.utc)
                                content = resp.content
                                break
                        except Exception as ex:
                            tried_log.append(f"{tz_name} {date_str} {time_str} -> EXC {ex.__class__.__name__}")
                            continue
                    if content is not None:
                        break

                if content is None:
                    # Fallback na pevné URL z configu
                    fixed = (self.config.chmi.radar_image_url or '').strip()
                    if not fixed:
                        # zalogovat poslední pokusy pro diagnostiku
                        try:
                            logger.debug("/radar tried: " + " | ".join(tried_log[-10:]))
                        except Exception:
                            pass
                        # poslat stručnou diagnostiku do chatu (poslední 3 kandidáty)
                        try:
                            tail = " | ".join(tried_log[-3:]) if tried_log else ""
                            msg = "❌ Radar nelze stáhnout (žádný dostupný snímek)."
                            if tail:
                                msg += f"\nDebug: {tail}"
                            self.notifier.send_message(msg, chat_id=chat_id)
                        except Exception:
                            self.notifier.send_message("❌ Radar nelze stáhnout (žádný dostupný snímek).", chat_id=chat_id)
                        return
                    r = requests.get(fixed, timeout=15)
                    if not r.ok:
                        self.notifier.send_message(f"❌ Nelze stáhnout radar ({r.status_code}).", chat_id=chat_id)
                        return
                    content = r.content
                    chosen_dt = None

                # 2) Volitelné překrytí obrysu ČR (pokud PIL dostupné)
                outline_path = (self.config.chmi.radar_outline_path or '').strip()
                with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
                    tmp.write(content)
                    tmp.flush()
                    radar_tmp_path = tmp.name

                final_path = radar_tmp_path
                extra_tmp_to_cleanup = []

                outline_disabled = (os.getenv('CHMI_OUTLINE_DISABLED', '').strip().lower() in ('1','true','yes','on'))
                if pil_available and (not outline_disabled) and outline_path and os.path.exists(outline_path):
                    try:
                        radar_img = Image.open(radar_tmp_path).convert('RGBA')
                        outline_img = Image.open(outline_path).convert('RGBA')
                        # Zmenšení a posun (konfigurovatelné přes ENV):
                        # CHMI_OUTLINE_SCALE: 0.0–1.0 (výchozí 0.85)
                        # CHMI_OUTLINE_OFFSET_X: pixely, záporné= doleva, kladné= doprava (výchozí 0)
                        # CHMI_OUTLINE_OFFSET_Y: pixely, záporné= nahoru, kladné= dolů (výchozí 30)
                        try:
                            scale = float(os.getenv('CHMI_OUTLINE_SCALE', '0.85'))
                        except Exception:
                            scale = 0.85
                        try:
                            offset_x = int(os.getenv('CHMI_OUTLINE_OFFSET_X', '0'))
                        except Exception:
                            offset_x = 0
                        try:
                            offset_y = int(os.getenv('CHMI_OUTLINE_OFFSET_Y', '30'))
                        except Exception:
                            offset_y = 30

                        scale = max(0.05, min(1.0, scale))
                        max_w = max(1, int(radar_img.width * scale))
                        max_h = max(1, int(radar_img.height * scale))

                        outline_resized = ImageOps.contain(outline_img, (max_w, max_h))
                        overlay_layer = Image.new('RGBA', radar_img.size, (0, 0, 0, 0))
                        pos_x = (radar_img.width - outline_resized.width) // 2 + offset_x
                        pos_y = (radar_img.height - outline_resized.height) // 2 + offset_y
                        # Omezit do hranic plátna
                        pos_x = max(-outline_resized.width, min(radar_img.width, pos_x))
                        pos_y = max(-outline_resized.height, min(radar_img.height, pos_y))
                        overlay_layer.paste(outline_resized, (pos_x, pos_y), mask=outline_resized)
                        composite = Image.alpha_composite(radar_img, overlay_layer)
                        composite_path = radar_tmp_path.replace('.png', '_cz.png')
                        composite.save(composite_path)
                        final_path = composite_path
                        extra_tmp_to_cleanup.append(radar_tmp_path)
                    except Exception as e:
                        logger.warning(f"Overlay outline failed: {e}")
                        final_path = radar_tmp_path

                # 3) Odeslat snímek s časovým popiskem (UTC) pokud znám
                if chosen_dt is not None:
                    caption = f"Aktuální radar (ČHMÚ) • {chosen_dt.strftime('%d.%m.%Y %H:%M')} UTC"
                else:
                    caption = "Aktuální radar (ČHMÚ)"

                self.notifier.send_photo(final_path, caption=caption, chat_id=chat_id)

                # 4) Úklid dočasných souborů
                try:
                    if os.path.exists(final_path):
                        os.remove(final_path)
                except Exception:
                    pass
                for p in extra_tmp_to_cleanup:
                    try:
                        if os.path.exists(p):
                            os.remove(p)
                    except Exception:
                        pass
            except Exception as e:
                logger.error(f"/radar error: {e}")
                self.notifier.send_message("❌ Došlo k chybě při stahování radaru.", chat_id=chat_id)
            return

    def run(self):
        while self.running:
            try:
                params = {
                    "timeout": 50,
                    "allowed_updates": json.dumps(["message", "callback_query"]),
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
                        if upd.get("callback_query"):
                            cq = upd["callback_query"]
                            data = cq.get("data")
                            msg = cq.get("message") or {}
                            chat = (msg.get("chat") or {})
                            chat_id = str(chat.get("id")) if chat.get("id") is not None else None
                            message_id = msg.get("message_id")
                            if chat_id and data:
                                try:
                                    if data.startswith("qh:"):
                                        on = data.split(":",1)[1] == "on"
                                        self.config.system.quiet_hours_enabled = on
                                        self._persist_settings()
                                        self.notifier.send_message(f"✅ Tiché hodiny {'ZAPNUTY' if on else 'VYPNUTY'}.", chat_id=chat_id, reply_to_message_id=message_id)
                                    elif data.startswith("thr:"):
                                        val = float(data.split(":",1)[1])
                                        if 0.0 <= val <= 1.0:
                                            self.config.ai.storm_confidence_threshold = val
                                            self._persist_settings()
                                            self.notifier.send_message(f"✅ Prah spolehlivosti nastaven na {val:.2f}", chat_id=chat_id, reply_to_message_id=message_id)
                                    elif data.startswith("graph:"):
                                        hours = int(data.split(":",1)[1])
                                        series = list(reversed(self.db.get_recent_weather_data(hours=hours)))[:max(60, hours*5)]
                                        if series:
                                            gen = WeatherReportGenerator(self.config)
                                            path = gen.create_multi_panel_chart_image(series, datetime.now())
                                            if path:
                                                self.notifier.send_photo(path, caption=f"Graf počasí za {hours} hodin", chat_id=chat_id, reply_to_message_id=message_id)
                                except Exception as e:
                                    logger.warning(f"Callback processing failed: {e}")
                        else:
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


