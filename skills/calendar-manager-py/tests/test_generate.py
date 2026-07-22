"""The renderer: week numbering, the multi-location fix, spare-letter color
assignment, and the generated documents' structure."""
import datetime
import re

import generate_calendar as G

# Same shape verify_output uses: matches day cells (incl. empty ones) but not
# inner divs like day__head.
DAY_CELL_RE = re.compile(r'<div class="day[" ]')


# ---------------------------------------------------------------------------
# week numbering + fetch range
# ---------------------------------------------------------------------------

class TestWeeks:
    def test_leading_stub_gets_no_week(self):
        # 2026-08-01 is a Saturday: 第一週 starts Mon Aug 3, the Aug 1–2 stub
        # belongs to July's final week file.
        starts = G.week_starts_for_month(2026, 8)
        assert starts[0] == datetime.date(2026, 8, 3)
        assert len(starts) == 5
        assert starts[-1] == datetime.date(2026, 8, 31)  # spills into September

    def test_month_starting_on_monday(self):
        starts = G.week_starts_for_month(2026, 6)  # 2026-06-01 is a Monday
        assert starts[0] == datetime.date(2026, 6, 1)
        assert len(starts) == 5

    def test_fetch_range_covers_month_and_spill(self):
        lo, hi = G.fetch_range_for_month(2026, 8)
        assert lo == datetime.date(2026, 8, 1)      # stub days still shown in month grid
        assert hi == datetime.date(2026, 9, 6)      # 第五週 runs Aug 31 – Sep 6

    def test_fetch_range_contains_every_week(self):
        for y, m in [(2026, 1), (2026, 2), (2026, 12), (2028, 2)]:
            lo, hi = G.fetch_range_for_month(y, m)
            for s in G.week_starts_for_month(y, m):
                assert lo <= s and s + datetime.timedelta(days=6) <= hi

    def test_week_label(self):
        assert G.week_label(1) == "第一週"
        assert G.week_label(5) == "第五週"
        assert G.week_label(11) == "第11週"


# ---------------------------------------------------------------------------
# parse_events — the multi-location fix
# ---------------------------------------------------------------------------

class TestParseEvents:
    def test_collects_every_distinct_location(self, events):
        by = G.parse_events(events)
        locs, lines = by[(2026, 8, 3)]
        assert locs == ["地點A", "地點B"]  # first-seen order, both kept
        assert len(lines) == 2

    def test_all_day_line_and_sorting(self, events):
        events.append({"summary": "早會", "location": "北京",
                       "start": {"dateTime": "2026-08-12T08:00:00+08:00"},
                       "end": {"dateTime": "2026-08-12T08:30:00+08:00"}})
        by = G.parse_events(events)
        locs, lines = by[(2026, 8, 12)]
        assert lines[0].startswith("[全天]")  # all-day sorts first
        assert locs == ["北京"]              # duplicate location not repeated

    def test_missing_location_is_not_a_location(self):
        by = G.parse_events([{"summary": "x",
                              "start": {"dateTime": "2026-08-03T09:00:00+08:00"},
                              "end": {"dateTime": "2026-08-03T10:00:00+08:00"}}])
        assert by[(2026, 8, 3)][0] == []


# ---------------------------------------------------------------------------
# color assignment
# ---------------------------------------------------------------------------

class TestColors:
    def test_loc_class_keys_keep_their_letters(self, events):
        cls = G.assign_loc_classes(G.parse_events(events))
        for loc, letter in G.LOC_CLASS.items():
            assert cls[loc] == letter

    def test_spares_assigned_first_seen(self, events):
        cls = G.assign_loc_classes(G.parse_events(events))
        assert cls["北京"] == "e"   # first unmapped location (Aug 12)
        assert cls["在家"] == "f"   # second (Aug 17)

    def test_spare_overflow_degrades_to_none(self):
        evs = [{"summary": "x", "location": f"新地點{i}",
                "start": {"dateTime": f"2026-08-{10+i:02d}T09:00:00+08:00"},
                "end": {"dateTime": f"2026-08-{10+i:02d}T10:00:00+08:00"}}
               for i in range(len(G.SPARE_LETTERS) + 1)]
        cls = G.assign_loc_classes(G.parse_events(evs))
        letters = [cls[f"新地點{i}"] for i in range(len(G.SPARE_LETTERS) + 1)]
        assert letters[:-1] == G.SPARE_LETTERS
        assert letters[-1] is None

    def test_badge_single_vs_chained(self):
        cls = {"地點A": "a", "地點B": "b"}
        single = G.render_location_badge(["地點A"], cls)
        assert 'loc--a' in single and "→" not in single
        chained = G.render_location_badge(["地點A", "地點B"], cls)
        assert "loc--move" in chained and "→" in chained
        assert "地點A" in chained and "地點B" in chained
        assert G.render_location_badge([], cls) == ""

    def test_unmapped_badge_degrades_not_crashes(self):
        out = G.render_location_badge(["沒看過的地方"], {})
        assert "loc--other" in out

    def test_legend_includes_unmapped(self):
        html = G.legend_html_for(["地點A", "北京"], {"地點A": "a", "北京": "e"})
        assert "--loc-a" in html and "--loc-e" in html and "北京" in html


# ---------------------------------------------------------------------------
# document structure
# ---------------------------------------------------------------------------

class TestDocuments:
    def _month(self, tmp_path, events, title="範例 2026 年 8 月行事曆"):
        by = G.parse_events(events)
        cls = G.assign_loc_classes(by)
        month_events = {d: v for (y, m, d), v in by.items() if (y, m) == (2026, 8)}
        out = tmp_path / "month.html"
        G.build_month(2026, 8, title, month_events, out, cls)
        return out.read_text(encoding="utf-8")

    def test_month_title_and_grid(self, tmp_path, events):
        text = self._month(tmp_path, events)
        assert "<title>範例 2026 年 8 月行事曆</title>" in text
        assert len(DAY_CELL_RE.findall(text)) == 42  # 6 lead + 31 + 5 trail
        assert text.rstrip().endswith("</html>")
        assert "V2" not in text  # template's placeholder sup must not survive

    def test_month_multi_location_day_renders_chain(self, tmp_path, events):
        text = self._month(tmp_path, events)
        assert "loc--move" in text
        assert "--loc-e" in text  # spare color reached the legend

    def test_month_without_events_drops_legend(self, tmp_path):
        text = self._month(tmp_path, [])
        # the CSS rule .legend__item stays; the rendered legend div must go
        assert '<div class="legend">' not in text
        assert 'class="legend__item"' not in text

    def test_html_escaping(self, tmp_path):
        evil = [{"summary": "<script>alert(1)</script>", "location": "地點A",
                 "start": {"dateTime": "2026-08-03T09:00:00+08:00"},
                 "end": {"dateTime": "2026-08-03T10:00:00+08:00"}}]
        text = self._month(tmp_path, evil)
        assert "<script>alert" not in text
        assert "&lt;script&gt;" in text

    def test_week_structure(self, tmp_path, events):
        by = G.parse_events(events)
        cls = G.assign_loc_classes(by)
        out = tmp_path / "week.html"
        G.build_week("第五週", datetime.date(2026, 8, 31), by, out, "範例", cls)
        text = out.read_text(encoding="utf-8")
        assert "<title>範例 第五週行事曆</title>" in text
        assert len(DAY_CELL_RE.findall(text)) == 7
        assert "08/31–09/06" in text
        assert "跨月專案會議" in text  # the September spill event is visible

    def test_derive_title_prefix(self):
        assert G.derive_title_prefix("範例 2026 年 8 月行事曆") == "範例"
        assert G.derive_title_prefix("OO董 2026 年 12 月行事曆") == "OO董"
