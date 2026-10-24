"""Stage 2 integration checks: actual FaceMesh, geometry invariance and bad input."""
import hashlib
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from face.face_feature_extractor import extract, geometry, expression_features, toon_skin_palette, hair_palette

out = ROOT / 'artifacts/validation/face-stage2'
photo = ROOT / 'assets/photo/me.png'
if not photo.exists(): photo = ROOT / 'assets/photo/woman.png'
packet = json.loads((out / 'ExportedFaceData/face_params.json').read_text())
assert packet['landmark_count'] == len(packet['landmarks']) == 478
assert np.isfinite(packet['landmarks']).all()
assert re.fullmatch(r'#[0-9A-F]{6}', packet['skin_tint'])
assert all(0 <= v <= 1 for v in packet['blendshapes'].values())
assert {'Joy', 'EyeSlanted', 'EyeDistance', 'JawRound', 'EyeSize', 'EyeOpenness'} <= packet['blendshapes'].keys()
assert all(len(v) == 3 and np.isfinite(v).all() for v in packet['bone_offsets'].values())
assert np.allclose(packet['bone_offsets']['LeftEye'], -np.array(packet['bone_offsets']['RightEye']))
for key, size in [('texture_path', (128, 256)), ('diffuse_texture_path', (512, 512))]:
    im = cv2.imread(packet[key], cv2.IMREAD_UNCHANGED)
    assert im.shape == (*size, 4)
    assert im[:, :, 3].min() == 0 and im[:, :, 3].max() == 255
# Toon color contract under dark, warm and bright source illumination.
for source in [[.08, .03, .01], [.6, .2, .1], [.98, .9, .86]]:
    palette = toon_skin_palette(source)
    hsv = cv2.cvtColor(np.float32([[palette['base_color']]]), cv2.COLOR_RGB2HSV)[0, 0]
    assert hsv[2] >= .85 - 1e-6 and .12 - 1e-6 <= hsv[1] <= .28 + 1e-6
    assert np.isclose(hsv[2], min(1., max(.85, max(source) * 1.15)))
    assert palette['shade_color'][2] > palette['shade_color'][1]
assert packet['schema_version'] == 3
assert all(len(c) == 3 and np.isfinite(c).all() and np.min(c) >= 0 and np.max(c) <= 1
           for palette in [packet['skin'], packet['hair']] for c in palette.values())
assert max(packet['hair']['base_color']) < .3
assert max(packet['skin']['base_color']) >= .85
assert packet['skin_tint'] != packet['source_skin_tint']
pixels = np.array(packet['landmarks'])[:, :2] * packet['source_size']
empty_hair, info = hair_palette(np.full_like(cv2.imread(str(photo)), 255), pixels)
assert empty_hair is None and not info['hair_detected']
# Repeat inference/export, including the optional-texture-disabled contract.
optional = extract(photo, out / 'no-pupil', pupil=False)
assert optional['texture_path'] is None
assert np.allclose(list(packet['metrics'].values()), list(optional['metrics'].values()), atol=1e-6)
# Roll/scale invariance of measurements without conflating inference variance.
p = np.array(packet['landmarks'])
w, h = packet['source_size']
baseline, _, _, _ = geometry(p, w, h)
base_expression, _ = expression_features(p, w, h)
assert base_expression['smile_degree'] > .8 and base_expression['mouth_open'] > .3
assert all(0 <= v <= 1 for v in base_expression.values())
angle = np.deg2rad(17)
rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
rotated = p.copy()
rotated[:, :2] = ((p[:, :2] * [w, h] - [w/2, h/2]) @ rot.T + [w/2, h/2]) / [w, h]
roll, _, _, _ = geometry(rotated, w, h)
scaled, _, _, _ = geometry(p, w * 2, h * 2)
assert np.allclose(list(baseline.values()), list(roll.values()), atol=1e-10)
assert np.allclose(list(baseline.values()), list(scaled.values()), atol=1e-10)
for points, width, height in [(rotated, w, h), (p, w*2, h*2)]:
    exp, _ = expression_features(points, width, height)
    assert np.allclose(list(base_expression.values()), list(exp.values()), atol=1e-10)
# A neutral closed mouth has neither smile nor opening; closed eyes alone are not joy.
neutral = p.copy()
neutral[[61, 291, 13, 14], 1] = np.mean(p[[61,291],1])
exp, _ = expression_features(neutral, w, h)
assert exp['smile_degree'] == exp['mouth_open'] == exp['eye_smile_left'] == exp['eye_smile_right'] == 0
for upper, lower in [(159,145),(158,153),(386,374),(385,380)]:
    neutral[upper,:2]=neutral[lower,:2]
closed, _ = expression_features(neutral, w, h)
assert closed['smile_degree'] == closed['eye_smile_left'] == closed['eye_smile_right'] == 0
# Explicit failures must not publish a face_params.json.
blank = out / 'blank.png'
cv2.imwrite(str(blank), np.full((512, 512, 3), 127, np.uint8))
bad = out / 'invalid.jpg'
bad.write_bytes(b'not an image')
portrait = cv2.imread(str(photo))
multiple = out / 'multiple.png'
cv2.imwrite(str(multiple), np.hstack([portrait, portrait]))
failures = {}
for name, path in [('no-face', blank), ('invalid', bad), ('missing', out/'missing.jpg'), ('multiple-faces', multiple)]:
    target = out / ('rejected-' + name)
    try:
        extract(path, target)
    except ValueError as error:
        failures[name] = str(error)
    else:
        raise AssertionError(f'{name} accepted unexpectedly')
    assert not (target / 'face_params.json').exists()
images = []
for path in (out/'ExportedFaceData').glob('*.png'):
    images.append(dict(file=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
report = dict(passed=True, landmark_count=478, skin_tint=packet['skin_tint'],
              blendshapes=packet['blendshapes'], expression=packet['expression'], expression_invariance=True, neutral_expression=True, metrics=packet['metrics'],
              quality=packet['quality'], skin=packet['skin'], hair=packet['hair'], toon_color_bounds=True, hair_background_abstention=True, roll_invariance=True, scale_invariance=True,
              repeat_inference=True, optional_pupil=True, rejected=failures, images=images)
(out/'acceptance.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
