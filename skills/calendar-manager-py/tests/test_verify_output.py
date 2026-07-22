"""verify_output.py — the structural checks that replace "look at the file"."""
import pytest

import verify_output as V


class TestVerifyPng:
    def test_missing_file(self, tmp_path):
        res = V.verify_png(str(tmp_path / "nope.png"))
        assert not res["ok"]

    def test_not_a_png(self, tmp_path):
        p = tmp_path / "fake.png"
        p.write_text("<html>error page saved as png</html>")
        res = V.verify_png(str(p))
        assert not res["ok"]
        assert any(c["name"] == "is_png" and not c["ok"] for c in res["checks"])

    def test_real_png_passes(self, tmp_path):
        Image = pytest.importorskip("PIL.Image")
        p = tmp_path / "cal.png"
        im = Image.new("RGB", (800, 600), (255, 255, 255))
        for x in range(400):
            im.putpixel((x, 100), (0, 0, 0))
        im.save(p)
        res = V.verify_png(str(p))
        assert res["ok"], res

    def test_blank_png_flagged(self, tmp_path):
        Image = pytest.importorskip("PIL.Image")
        p = tmp_path / "blank.png"
        Image.new("RGB", (800, 600), (255, 255, 255)).save(p)
        res = V.verify_png(str(p))
        assert not res["ok"]
        assert any(c["name"] == "not_blank" and not c["ok"] for c in res["checks"])

    def test_too_small_flagged(self, tmp_path):
        Image = pytest.importorskip("PIL.Image")
        p = tmp_path / "tiny.png"
        im = Image.new("RGB", (100, 80), (255, 255, 255))
        im.putpixel((1, 1), (0, 0, 0))
        im.save(p)
        res = V.verify_png(str(p))
        assert not res["ok"]
        assert any(c["name"] == "min_size" and not c["ok"] for c in res["checks"])


class TestVerifyHtml:
    def _write(self, tmp_path, text):
        p = tmp_path / "view.html"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def _doc(self, title="範例 第一週行事曆", cells=7, tail="</body>\n</html>"):
        day = '<div class="day">x</div>'
        return (f"<!DOCTYPE html><html><head><title>{title}</title></head>"
                f'<body><div class="grid">{day * cells}</div>{tail}')

    def test_good_doc_passes(self, tmp_path):
        p = self._write(tmp_path, self._doc())
        res = V.verify_html(p, expect_title="第一週", expect_day_cells=7)
        assert res["ok"], res

    def test_wrong_title(self, tmp_path):
        p = self._write(tmp_path, self._doc(title="範例 2026 年 4 月行事曆"))
        res = V.verify_html(p, expect_title="2026 年 8 月")
        assert not res["ok"]

    def test_wrong_cell_count(self, tmp_path):
        p = self._write(tmp_path, self._doc(cells=6))
        res = V.verify_html(p, expect_day_cells=7)
        assert not res["ok"]
        assert any(c["name"] == "day_cells" and not c["ok"] for c in res["checks"])

    def test_truncated_doc(self, tmp_path):
        p = self._write(tmp_path, self._doc(tail=""))
        res = V.verify_html(p)
        assert not res["ok"]
        assert any(c["name"] == "closed" and not c["ok"] for c in res["checks"])

    def test_missing_grid(self, tmp_path):
        p = self._write(tmp_path,
                        "<!DOCTYPE html><html><head><title>t</title></head>"
                        "<body>no grid</body></html>")
        res = V.verify_html(p)
        assert not res["ok"]


class TestFontCheck:
    def test_shape(self):
        res = V.cjk_font_check()
        assert set(res) >= {"ok", "skipped", "detail"}
