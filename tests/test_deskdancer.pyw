"""test_deskdancer.pyw  v2.0.0 — тесты ядра DeskDancer (двойной клик или python -m unittest)

Журнал:
v2.0.0: сервера сцены нет; танцы на Python (перенос, имена костей), неон
v1.0.0: такт по тестовому треку, ручной темп и «тап», настройки (атомарная
        запись, битый JSON → .bak), сервер сцены не выпускает за свои папки
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import deskdancer as core  # noqa: E402


class TestBeat(unittest.TestCase):
    def test_tempos(self):
        for bpm in (90.0, 110.0, 128.0, 140.0):
            tr = core.BeatTracker()
            tr.feed(core.synth_clicks(bpm, 10.0))
            st = tr.state()
            self.assertAlmostEqual(st["bpm"], bpm, delta=2.5, msg=f"{bpm}")
            period = 60.0 / bpm
            exp = (10.0 % period) / period
            self.assertLess(abs((st["phase"] - exp + 0.5) % 1 - 0.5), 0.12)
            self.assertTrue(st["active"])

    def test_silence(self):
        import numpy as np
        tr = core.BeatTracker()
        tr.feed(np.zeros(44100 * 4, np.float32))
        self.assertFalse(tr.state()["active"])

    def test_manual(self):
        c = core.ManualClock(100)
        c.set_bpm(300)
        self.assertEqual(c.bpm, 240)
        for _ in range(4):
            c.tap()
            time.sleep(0.25)
        self.assertGreater(c.bpm, 200)


class TestConfig(unittest.TestCase):
    def test_roundtrip_and_bak(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.json"
            cfg = core.load_config(p)
            cfg["theme"] = "light"
            self.assertTrue(core.save_config(cfg, p))
            cfg["theme"] = "dark"
            core.save_config(cfg, p)               # прежний — в .bak
            p.write_text("{битый", encoding="utf-8")
            c2 = core.load_config(p)
            self.assertEqual(c2["theme"], "light")
            self.assertFalse(c2.get("_readonly"))
            Path(str(p) + ".bak").unlink() if Path(str(p) + ".bak").exists() else None
            p.with_suffix(".json.bak").write_text("{тоже битый", encoding="utf-8")
            c3 = core.load_config(p)
            self.assertTrue(c3.get("_readonly"))
            self.assertFalse(core.save_config(c3, p))
            self.assertEqual(p.read_text(encoding="utf-8"), "{битый")

    def test_unique_dest(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.glb"
            f.write_bytes(b"abc")
            self.assertIsNone(core.unique_dest(d, "a.glb", b"abc", 3))
            self.assertEqual(core.unique_dest(d, "a.glb", b"xyz", 3).name, "a (2).glb")


class TestAnim(unittest.TestCase):
    """Танцы на Python: тот же скелет — как есть, чужой — перенос; доля в клипе."""

    def test_retarget(self):
        from app import gltf_anim as ga
        root = Path(__file__).resolve().parent.parent
        g = ga.Gltf(root / "characters/rocketbox/Алина.glb")
        s = ga.Gltf(root / "dances/rocketbox/Весёлый.glb")
        c = ga.retarget(s, ga.longest(ga.animations(s)), g)
        self.assertTrue(c.same)
        self.assertGreater(c.tracks, 60)
        self.assertAlmostEqual(c.period, 0.543, delta=0.01)
        rot, pos = c.frame(1.0)
        self.assertEqual(len(rot), len(c.rot))

    def test_names(self):
        from app.gltf_anim import norm_bone
        for a, b in (("mixamorig:LeftArm", "leftarm"), ("Bip01_L_UpperArm", "leftarm"),
                     ("CC_Base_R_Thigh", "rightupleg"), ("J_Bip_C_Hips", "hips"), ("upperarm_r", "rightarm")):
            self.assertEqual(norm_bone(a), b)


class TestNeon(unittest.TestCase):
    def test_neon(self):
        import numpy as np
        from app import neon
        img = np.zeros((120, 100, 4), np.uint8)
        img[30:90, 30:70] = (60, 80, 200, 255)
        out = neon.apply(img, "fire", 1.2, 0.5, 0.0)
        self.assertEqual(out.shape, img.shape)
        self.assertGreater(int(out[..., 3].max()), 200)          # контур светится
        self.assertTrue((out[..., :3] <= out[..., 3:4]).all())   # premultiplied


if __name__ == "__main__":
    unittest.main(verbosity=2)
