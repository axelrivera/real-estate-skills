"""Chart labels read in every PDF viewer: a background-colored copy under each label, never an outline drawn with
paint-order (Results_v5 case 02: the supported range label smeared into an unreadable block)."""
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "shared"))

import cma  # noqa: E402


class ChartLabels(unittest.TestCase):
    def test_halo_is_a_separate_copy(self):
        svg = cma._halo('<text x="1" y="2" class="lbl-band">Supported Range $375K–$395K</text>')
        self.assertEqual(svg.count("Supported Range"), 2)
        self.assertTrue(svg.startswith('<text x="1" y="2" aria-hidden="true" class="halo lbl-band">'))
        self.assertTrue(svg.endswith('class="lbl-band">Supported Range $375K–$395K</text>'))

    def test_no_paint_order_outlines(self):
        for path in ("shared/cma.css", "shared/report.css", "skills/contract-timeline/assets/timeline.css"):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                self.assertNotIn("paint-order", f.read(), path)

    def test_label_width_leaves_room_for_wider_fonts(self):
        self.assertGreater(cma._text_w("Supported Range $375K–$395K", 12, bold=True), 27 * 12 * 0.6)


if __name__ == "__main__":
    unittest.main()
