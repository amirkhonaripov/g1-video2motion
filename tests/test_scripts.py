"""Fast checks of the helper scripts on tiny fixtures (no GPU, nothing from runs/ or data/)."""

import json
import sys
from pathlib import Path

import mujoco
import numpy as np
import pytest

from scripts import harness
from scripts.beyondmimic import train
from scripts.check import motion_quality
from scripts.g1 import G1_XML
from scripts.report import harness_tables

REPO = Path(__file__).resolve().parents[1]
CONDITIONS = list(harness_tables.CONDITIONS)


def write_motion(path, pelvis_z, fps=50):
  frames, bodies = len(pelvis_z), 2
  body_pos = np.zeros((frames, bodies, 3))
  body_pos[:, 0, 2] = pelvis_z
  body_quat = np.zeros((frames, bodies, 4))
  body_quat[..., 0] = 1
  np.savez(path, fps=np.array([fps]), joint_pos=np.zeros((frames, 29)), joint_vel=np.zeros((frames, 29)),
           body_pos_w=body_pos, body_quat_w=body_quat)
  return str(path)


def test_motion_quality_flags_floating(tmp_path):
  model = mujoco.MjModel.from_xml_path(str(REPO / G1_XML))
  grounded = write_motion(tmp_path / "grounded.npz", np.full(150, 0.8))
  floating = write_motion(tmp_path / "floating.npz", np.r_[np.full(50, 0.8), np.full(100, 0.9)])
  assert not motion_quality.analyze(grounded, model)["floats"]
  r = motion_quality.analyze(floating, model)
  assert r["floats"]
  assert r["float_start_end_s"] == [1.04, 3.0]
  assert r["float_height_m"] == pytest.approx(0.1, abs=1e-3)
  assert "floats: yes (1.0-3.0 s, 10 cm up)" in motion_quality.line(r)


def hop(land_m):
  """Lowest foot at 50 fps: 1 s on the floor, a 0.5 s hop 30 cm high landing at land_m, 1 s there."""
  u = np.arange(25) / 25
  return np.r_[np.zeros(50), 1.2 * u * (1 - u) + land_m * u, np.full(50, land_m)]


def test_motion_quality_hop_is_not_floating():
  stretch = motion_quality.longest_float(hop(0.0), 50)
  assert stretch is None or stretch[1] - stretch[0] < motion_quality.FLOAT_S


def test_motion_quality_hover_after_landing_is_floating():
  start, end, height = motion_quality.longest_float(hop(0.1), 50)
  assert 1.5 <= start < 1.6 and end == 2.5
  assert height == pytest.approx(0.1, abs=1e-3)


@pytest.mark.parametrize("motion, name", [
  ("data/motions/gmr/jazz.npz", "jazz_gmr"),
  ("data/motions/gmr/jump_kick_grounded.npz", "jump_kick_gmr_grounded"),
  ("data/motions/vith/tennis_s3.npz", "tennis_vith_s3"),
  ("data/motions/vith/pop_s2_grounded.npz", "pop_vith_s2_grounded"),
  ("/home/me/repo/data/motions/vith/studio_dance.npz", "studio_dance_vith"),
  ("data/motions/demo/lafan1_dance1_subject1.npz", "lafan1_dance1_subject1"),
  ("clips/my_clip.npz", "my_clip"),
])
def test_train_default_name(motion, name):
  assert train.default_name(motion) == name


@pytest.mark.parametrize("what, stem", [
  ("jazz_gmr", "jazz_gmr"),
  ("runs/onnx/pop_vith_s2/policy.onnx", "pop_vith_s2"),
  ("checkpoints/mine.onnx", "mine"),
])
def test_harness_policy_stem(what, stem):
  assert harness.policy_stem(what) == stem


@pytest.mark.parametrize("motion, sonic", [
  ("data/motions/gmr/pop.npz", "data/motions/sonic/pop_gmr.npz"),
  ("data/motions/vith/pop_s2_grounded.npz", "data/motions/sonic/pop_vith_s2_grounded.npz"),
  ("data/motions/sonic/pop_gmr.npz", "data/motions/sonic/pop_gmr.npz"),
])
def test_harness_sonic_motion(motion, sonic):
  assert harness.sonic_motion(motion) == sonic


def write_run(folder, conditions, trials=None):
  trial = {"fall": False, "mpkpe_m": 0.1, "r_mpkpe_m": 0.05}
  pushes = {c: [{"start_s": 4.0}] if c.startswith("push") else [] for c in conditions}
  summary = {
    "adapter": {"describe": {"motion_frames": 500}},
    "trials": {c: {"seed_0": (trials or {}).get(c, trial)} for c in conditions},
    "perturbations": {c: {"seed_0": {"pushes": pushes[c]}} for c in conditions},
  }
  folder.mkdir(parents=True)
  (folder / "summary.json").write_text(json.dumps(summary))


def make_tables(monkeypatch, *options):
  monkeypatch.setattr(sys, "argv", ["harness_tables", *options])
  harness_tables.main()


def test_harness_tables(tmp_path, monkeypatch):
  monkeypatch.chdir(tmp_path)
  write_run(tmp_path / "runs/harness/beyondmimic_pop_gmr__all", CONDITIONS)
  for c in CONDITIONS:
    write_run(tmp_path / f"runs/harness/beyondmimic_jazz_gmr__{c}", [c])
  write_run(tmp_path / "runs/harness/beyondmimic_zz_custom__all", CONDITIONS)
  (tmp_path / "results/mjlab").mkdir(parents=True)
  metrics = {"num_episodes": 1024, "success_rate": 1.0}
  (tmp_path / "results/mjlab/pop_gmr.json").write_text(json.dumps({"metrics": metrics}))

  make_tables(monkeypatch)
  text = (tmp_path / "results/tables.md").read_text()
  assert "| Pop | GVHMR+GMR | 6/6 | 1/1 | 2/2 | 3/3 | 10.0 / 5.0 | 0/6 | 100.0% (1024/1024) |" in text
  assert "| Jazz | GVHMR+GMR | 6/6 | 1/1 | 2/2 | 3/3 | 10.0 / 5.0 | 0/6 | – |" in text
  assert "| zz_custom |  | 6/6 |" in text

  make_tables(monkeypatch, "--match", "pop*")
  text = (tmp_path / "results/tables_pop.md").read_text()
  assert "| Pop | GVHMR+GMR | 6/6 |" in text
  assert "| Jazz |" not in text and "zz_custom" not in text

  make_tables(monkeypatch, "--match", "zz_*", "--output", "zz.md")
  text = (tmp_path / "zz.md").read_text()
  assert "| zz_custom |  | 6/6 |" in text
  assert "| Pop |" not in text and "| Jazz |" not in text


def test_harness_tables_real_falls(tmp_path, monkeypatch):
  """Real falls from a run that kept going after the tracking failure, or from the rerun of an older run."""
  monkeypatch.chdir(tmp_path)
  ok = {"fall": False, "tracking_failure": False, "fell": False, "mpkpe_m": 0.1, "r_mpkpe_m": 0.05,
        "pre_failure_mpkpe_m": 0.1, "pre_failure_r_mpkpe_m": 0.05}
  failed = {**ok, "fall": True, "tracking_failure": True, "fell": True, "mpkpe_m": 0.9, "r_mpkpe_m": 0.8}
  write_run(tmp_path / "runs/harness/beyondmimic_pop_gmr__all", CONDITIONS,
            {c: failed if c == "flat_nominal" else ok for c in CONDITIONS})
  stopped = {"fall": True, "mpkpe_m": 0.1, "r_mpkpe_m": 0.05}
  write_run(tmp_path / "runs/harness/beyondmimic_jazz_gmr__all", CONDITIONS, {"flat_nominal": stopped})
  write_run(tmp_path / "runs/harness_falls/beyondmimic_jazz_gmr__flat_nominal", ["flat_nominal"],
            {"flat_nominal": failed})
  write_run(tmp_path / "runs/harness/beyondmimic_hiphop_back_gmr__all", CONDITIONS, {"flat_nominal": stopped})
  (tmp_path / "results").mkdir()

  make_tables(monkeypatch)
  text = (tmp_path / "results/tables.md").read_text()
  assert "| Pop | GVHMR+GMR | 5/6 | 0/1 | 2/2 | 3/3 | 10.0 / 5.0 | 1/6 |" in text
  assert "| Jazz | GVHMR+GMR | 5/6 | 0/1 | 2/2 | 3/3 | 10.0 / 5.0 | 1/6 |" in text
  assert "| Hip-hop (back) | GVHMR+GMR | 5/6 | 0/1 | 2/2 | 3/3 | 10.0 / 5.0 | 0/6 (1 not rerun) |" in text
  assert "| Pop | GVHMR+GMR | 0/1 · 1/1 · 5.0 |" in text
