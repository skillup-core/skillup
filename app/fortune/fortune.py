"""
Daily Fortune App

Displays a daily fortune based on birth date and time (Saju).
Fortune index is calculated using traditional Korean Ganjji system.
"""

import os
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import List
from datetime import datetime

from lib.baseapp import BaseApp
from lib.appmgr import register_app_class


_RES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')

# Language ID mapping (see docs/list.md)
_LANG_KO = 0
_LANG_EN = 1


def _load_res(lang_num: int) -> List[str]:
    path = os.path.join(_RES_DIR, f'res{lang_num}.dat')
    if not os.path.exists(path):
        return []
    with open(path, 'rb') as f:
        data = f.read()
    return zlib.decompress(data).decode('utf-8').split('\n')


def _load_fortunes() -> List[tuple]:
    ko = _load_res(_LANG_KO)
    en = _load_res(_LANG_EN)
    return list(zip(ko, en))


# ---------------------------------------------------------------------------
# Fortune calculation (ported from original cccopy fortune app)
# ---------------------------------------------------------------------------

EARTHLY_BRANCHES = ['ja', 'chuk', 'in', 'myo', 'jin', 'sa', 'o', 'mi', 'sin', 'yu', 'sul', 'hae']
HEAVENLY_STEMS = ['gap', 'eul', 'byeong', 'jeong', 'mu', 'gi', 'gyeong', 'sin', 'im', 'gye']


def _get_gan_ji_year(year):
    offset = (year - 4) % 60
    gan = offset % 10
    ji = offset % 12
    return gan, ji


def _get_gan_ji_month(year, month):
    year_gan = (year - 4) % 10
    base = (year_gan % 5) * 2
    month_gan = (base + month - 1) % 10
    month_ji = (month + 1) % 12
    return month_gan, month_ji


def _get_gan_ji_day(year, month, day):
    a = (14 - month) // 12
    y = year - a
    m = month + 12 * a - 2
    days_since_base = (
        (year - 1900) * 365
        + (year - 1900) // 4
        + sum([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][:month - 1])
        + day
    )
    if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
        if month > 2:
            days_since_base += 1
    gan = (days_since_base + 6) % 10
    ji = (days_since_base + 8) % 12
    return gan, ji


def _get_gan_ji_hour(day_gan, hour):
    base = (day_gan % 5) * 2
    hour_index = (hour + 1) // 2 % 12
    hour_gan = (base + hour_index) % 10
    hour_ji = hour_index
    return hour_gan, hour_ji


def calculate_fortune_index(birth_yyyymmddhh: str, today_yyyymmdd: str, total: int) -> int:
    """Calculate fortune index from birth date/time and today's date."""
    birth_year = int(birth_yyyymmddhh[0:4])
    birth_month = int(birth_yyyymmddhh[4:6])
    birth_day = int(birth_yyyymmddhh[6:8])
    birth_hour_raw = int(birth_yyyymmddhh[8:10])
    hour_known = (birth_hour_raw != 99)
    birth_hour = birth_hour_raw if hour_known else 0

    today_year = int(today_yyyymmdd[0:4])
    today_month = int(today_yyyymmdd[4:6])
    today_day = int(today_yyyymmdd[6:8])

    year_gan, year_ji = _get_gan_ji_year(birth_year)
    month_gan, month_ji = _get_gan_ji_month(birth_year, birth_month)
    day_gan, day_ji = _get_gan_ji_day(birth_year, birth_month, birth_day)
    hour_gan, hour_ji = _get_gan_ji_hour(day_gan, birth_hour)

    today_gan, today_ji = _get_gan_ji_day(today_year, today_month, today_day)

    saju_sum = (
        year_gan * 11 + year_ji * 7
        + month_gan * 5 + month_ji * 3
        + day_gan * 13 + day_ji * 17
        + (hour_gan * 19 + hour_ji * 23 if hour_known else 0)
    )
    today_sum = today_gan * 13 + today_ji * 17

    elements = [year_gan % 5, month_gan % 5, day_gan % 5]
    if hour_known:
        elements.append(hour_gan % 5)
    harmony = sum(
        1 for i in range(len(elements))
        for j in range(i + 1, len(elements))
        if (elements[i] + elements[j]) % 5 == 0
    )

    branches = [year_ji, month_ji, day_ji]
    if hour_known:
        branches.append(hour_ji)
    conflict = sum(
        1 for i in range(len(branches))
        for j in range(i + 1, len(branches))
        if (branches[i] + 6) % 12 == branches[j]
    )

    combined = (saju_sum * 37 + today_sum * 41 + harmony * 19 + conflict * 23) % total
    return combined


# ---------------------------------------------------------------------------
# App class
# ---------------------------------------------------------------------------

CONFIG_DEFAULTS = {
    'birth': '',
    'show_on_start': 'true',
    'last_shown_date': '',
    'language_pref': 'auto',
}


class FortuneApp(BaseApp):
    """Daily Fortune application."""

    def on_run_cli(self, args: List[str]) -> int:
        """CLI mode: print today's fortune to stdout."""
        config = self.load_config(CONFIG_DEFAULTS)
        birth = config.get('birth', '')

        if not birth:
            print("Usage: set birth date in config (YYYYMMDDHH format)")
            return 1

        fortunes = _load_fortunes()
        today = datetime.now().strftime('%Y%m%d')
        idx = calculate_fortune_index(birth, today, len(fortunes))
        ko, en = fortunes[idx]
        print(f"[Today's Fortune / 오늘의 운세]")
        print(f"KO: {ko}")
        print(f"EN: {en}")
        return 0

    def on_run_desktop_initialize(self) -> int:
        self.register_handlers({
            'get_fortune': self._handle_get_fortune,
            'fortune_get_config': self._handle_get_config,
            'fortune_save_config': self._handle_save_config,
        })
        return 0

    def on_skillup_started(self):
        """Called when the desktop starts up. Shows daily fortune dialog if enabled."""
        config = self.load_config(CONFIG_DEFAULTS)
        show_on_start = config.get('show_on_start', 'true').lower() == 'true'
        if not show_on_start:
            return

        birth = config.get('birth', '')
        if not birth:
            return

        today = datetime.now().strftime('%Y%m%d')
        last_shown = config.get('last_shown_date', '')
        if last_shown == today:
            return  # Already shown today

        # Update last shown date
        config['last_shown_date'] = today
        self.save_config(config)

        fortunes = _load_fortunes()
        idx = calculate_fortune_index(birth, today, len(fortunes))
        ko, en = fortunes[idx]

        language_pref = config.get('language_pref', 'auto')

        # Notify JavaScript to show the startup fortune dialog
        self.callJS('showStartupFortune', {
            'ko': ko,
            'en': en,
            'date': today,
            'language_pref': language_pref,
        })

    # -----------------------------------------------------------------------
    # Handlers
    # -----------------------------------------------------------------------

    def _handle_get_fortune(self, data: dict, language: str) -> dict:
        """Return today's fortune for the configured birth date."""
        config = self.load_config(CONFIG_DEFAULTS)
        birth = data.get('birth') or config.get('birth', '')

        if not birth or len(birth) != 10 or not birth.isdigit():
            return {'success': False, 'error': 'invalid_birth', 'need_birth': True}

        fortunes = _load_fortunes()
        today = datetime.now().strftime('%Y%m%d')
        idx = calculate_fortune_index(birth, today, len(fortunes))
        ko, en = fortunes[idx]

        return {
            'success': True,
            'ko': ko,
            'en': en,
            'date': today,
            'index': idx,
        }

    def _handle_get_config(self, data: dict, language: str) -> dict:
        config = self.load_config(CONFIG_DEFAULTS)
        return {
            'success': True,
            'birth': config.get('birth', ''),
            'show_on_start': config.get('show_on_start', 'true'),
            'language_pref': config.get('language_pref', 'auto'),
        }

    def _handle_save_config(self, data: dict, language: str) -> dict:
        config = self.load_config(CONFIG_DEFAULTS)

        if 'birth' in data:
            birth = str(data['birth']).strip()
            if birth and (len(birth) != 10 or not birth.isdigit()):
                return {'success': False, 'error': 'invalid_birth_format'}
            config['birth'] = birth

        if 'show_on_start' in data:
            config['show_on_start'] = 'true' if data['show_on_start'] else 'false'

        if 'language_pref' in data:
            pref = str(data['language_pref'])
            if pref in ('auto', 'ko', 'en'):
                config['language_pref'] = pref

        self.save_config(config)
        return {'success': True}


register_app_class(FortuneApp)
