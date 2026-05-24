from __future__ import annotations

from pathlib import Path

import pytest

from workers.ingestion.nj.config import NJConfig


@pytest.fixture
def nj_cfg(tmp_path: Path) -> NJConfig:
    return NJConfig.model_validate({
        "version": "1.0.0",
        "source": "nj",
        "shastra": {
            "natural_key": "samaysar",
            "title_hi": "समयसार",
            "author": {
                "natural_key": "kundkundacharya",
                "display_name_hi": "कुन्दकुन्दाचार्य",
                "kind": "acharya",
            },
            "teekas": [
                {
                    "natural_key": "samaysar:amritchandra",
                    "teekakar_natural_key": "amritchandracharya",
                    "teekakar_display_name_hi": "अमृतचंद्राचार्य",
                    "publication_natural_key": "samaysar:amritchandra:nikkyjain",
                    "publisher_id": "nikkyjain",
                    "role": "primary",
                },
                {
                    "natural_key": "samaysar:jaysenacharya",
                    "teekakar_natural_key": "jaysenacharya",
                    "teekakar_display_name_hi": "जयसेनाचार्य",
                    "publication_natural_key": "samaysar:jaysenacharya:nikkyjain",
                    "publisher_id": "nikkyjain",
                    "role": "secondary",
                },
            ],
        },
        "input": {
            "html_dir": str(tmp_path),
            "my_item_js": "myItem.js",
            "encoding": "utf-8",
            "skip_files": ["0000_intro.html"],
        },
        "selectors": {
            "primary_teeka_select": "select#select-native-0",
            "secondary_teeka_select": "select#select-native-1",
            "gatha_title_div": "div.title[id^='gatha-']",
            "gatha_heading_link": "div.title > span > a",
            "gatha_prakrit": "div.gatha",
            "gatha_sanskrit": "div.gathaS",
            "gatha_hindi_chhand_body": "div.gadya",
            "anyavartha_para": "div.paragraph",
            "anyavartha_marker": "अन्वयार्थ",
            "teeka0_div": "div#teeka0",
            "teeka1_div": "div#teeka1",
            "steeka0_div": "div.steeka#steeka0",
            "steeka1_div": "div.steeka#steeka1",
            "primary_teeka_label": "अमृतचंद्राचार्य",
            "secondary_teeka_label": "जयसेनाचार्य",
            "kalash_type_marker_color": "DarkSlateGray",
            "kalash_word_meaning_color": "maroon",
            "gatha_word_meaning_color": "darkRed",
            "teeka_separator": "hr.type_7",
        },
        "parsing": {"strip_zwj": False, "notes_teeka_index": 2},
    })
