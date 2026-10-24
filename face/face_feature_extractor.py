"""Single portrait -> normalized face controls and RGBA material assets.

MediaPipe z is relative depth, not a metric 3D reconstruction. Controls are
heuristics for avatar fitting, not measurements of identity or emotion.
"""
import argparse
import json
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np

RANGES = {
    'eye_size': (0.12, 0.40), 'eye_openness': (0.12, 0.40),
    'eye_distance': (0.16, 0.36), 'eye_slant': (-15., 15.),
    'smile_degree': (-0.06, 0.12), 'jaw_roundness': (0.5, 3.5),
}


def normalize(value, limits):
    return float(np.clip((value - limits[0]) / (limits[1] - limits[0]), 0., 1.))


def geometry(points, width, height):
    """Remove roll before measuring image-plane ratios; keep z separately."""
    p = np.asarray(points, dtype=np.float64)[:, :2] * [width, height]
    eye_r = (p[33] + p[133]) / 2
    eye_l = (p[362] + p[263]) / 2
    axis = eye_l - eye_r
    if np.linalg.norm(axis) < 8:
        raise ValueError('Face/eyes are too small to measure reliably')
    axis /= np.linalg.norm(axis)
    down = np.array([-axis[1], axis[0]])
    q = np.column_stack(((p - (eye_l + eye_r) / 2) @ axis,
                         (p - (eye_l + eye_r) / 2) @ down))
    distance = lambda a, b: float(np.linalg.norm(q[a] - q[b]))
    fw = distance(234, 454)
    if fw < 32:
        raise ValueError('Face width must be at least 32 pixels')
    # Reject marked yaw/pitch: no single-photo frontal rectification can recover occlusion.
    widths = [distance(33, 133), distance(362, 263)]
    if min(widths) / max(widths) < .55:
        raise ValueError('Please use a near-frontal portrait with both eyes visible')
    openness = np.mean([
        np.mean([distance(159, 145), distance(158, 153)]) / widths[0],
        np.mean([distance(386, 374), distance(385, 380)]) / widths[1]])
    slants = []
    for outer, inner in [(33, 133), (263, 362)]:
        slants.append(np.degrees(np.arctan2(q[inner, 1] - q[outer, 1],
                                            abs(q[inner, 0] - q[outer, 0]))))
    mouth_width = distance(61, 291)
    lip_mid = (q[13, 1] + q[14, 1]) / 2
    smile = (lip_mid - (q[61, 1] + q[291, 1]) / 2) / max(mouth_width, 1.)
    # Fit a parabola through 13 lower-jaw points in face-width coordinates.
    # At the chin its dimensionless curvature is 2|a|/(1+slope^2)^1.5.
    jaw_ids = [172, 136, 150, 149, 176, 148, 152, 377, 400, 378, 379, 365, 397]
    jaw = q[jaw_ids] / fw
    a, b, c = np.polyfit(jaw[:, 0], jaw[:, 1], 2)
    slope = 2 * a * q[152, 0] / fw + b
    curvature = float(2 * abs(a) / (1 + slope * slope) ** 1.5)
    residual = float(np.sqrt(np.mean((np.polyval([a, b, c], jaw[:, 0]) - jaw[:, 1]) ** 2)))
    metrics = dict(eye_size=float(openness), eye_openness=float(openness),
                   eye_distance=distance(133, 362) / fw, eye_slant=float(np.mean(slants)),
                   smile_degree=float(smile), jaw_roundness=curvature)
    controls = {k: normalize(v, RANGES[k]) for k, v in metrics.items()}
    # Broad, low-curvature chins map to a higher JawRound weight.
    controls['jaw_roundness'] = 1. - controls['jaw_roundness']
    return metrics, controls, dict(jaw_fit_rmse=residual, face_width_pixels=fw), p


def expression_features(points, width, height):
    """Single-frame expression estimates, not calibrated emotion/teeth detection.

    Roll-free vertical gaps avoid mistaking head tilt for a smile. Eye compression
    uses a population reference (0.34 EAR); a neutral reference portrait would be
    needed to distinguish naturally narrow eyes from smiling eyes reliably.
    """
    p = np.asarray(points, dtype=np.float64)[:, :2] * [width, height]
    axis = (p[362] + p[263] - p[33] - p[133]) / 2
    axis /= np.linalg.norm(axis)
    q = np.column_stack((p @ axis, p @ np.array([-axis[1], axis[0]])))
    dist = lambda a, b: float(np.linalg.norm(q[a] - q[b]))
    mouth_width = max(dist(61, 291), 1.e-6)
    arc = float(((q[13, 1] + q[14, 1]) - (q[61, 1] + q[291, 1])) / (2 * mouth_width))
    gap = max(0., float(q[14, 1] - q[13, 1])) / mouth_width
    width_ratio = mouth_width / max(dist(234, 454), 1.e-6)
    # Width corroborates a raised-corner smile; an open neutral mouth alone is not joy.
    smile = normalize(arc, (.005, .14)) * (.75 + .25 * normalize(width_ratio, (.30, .48)))
    right = np.mean([dist(159, 145), dist(158, 153)]) / max(dist(33, 133), 1.e-6)
    left = np.mean([dist(386, 374), dist(385, 380)]) / max(dist(362, 263), 1.e-6)
    expression = dict(smile_degree=float(smile),
                      eye_smile_left=float(smile * normalize(.34 - left, (0., .16))),
                      eye_smile_right=float(smile * normalize(.34 - right, (0., .16))),
                      mouth_open=normalize(gap, (.015, .40)))
    return expression, dict(smile_arc=arc, mouth_width_face_ratio=width_ratio,
        mouth_gap_width_ratio=gap, eye_openness_left=float(left), eye_openness_right=float(right),
        neutral_eye_openness_reference=.34, open_smile_candidate=bool(smile > .4 and gap > .08))


def rgb_hex(rgb):
    return '#' + ''.join(f'{v:02X}' for v in np.rint(np.clip(rgb, 0, 1) * 255).astype(int))


def toon_skin_palette(rgb):
    """Art-directed sRGB palette; not an estimate of physical skin reflectance."""
    hsv = cv2.cvtColor(np.float32([[rgb]]), cv2.COLOR_RGB2HSV)[0, 0]
    value = float(np.clip(max(.85, hsv[2] * 1.15), 0, 1))
    saturation = float(np.clip(.25 * np.clip(hsv[1], .12, .28) + .75 * .12, .12, .28))
    def color(h, s, v):
        return cv2.cvtColor(np.float32([[[h, s, v]]]), cv2.COLOR_HSV2RGB)[0, 0].tolist()
    return dict(base_color=color(350., saturation, value),
                shade_color=color(325., .12, max(.82, value * .94)),
                shade2_color=color(285., .14, max(.76, value * .88)))


def skin_samples(image, p):
    """Small malar/upper-cheek patches, below eyelids and lateral to nose wings."""
    h, w = image.shape[:2]
    radius = max(2, int(np.linalg.norm(p[234] - p[454]) * .025))
    centers = [.6 * p[50] + .4 * p[101], .6 * p[280] + .4 * p[330],
               .7 * p[118] + .3 * p[101], .7 * p[347] + .3 * p[330]]
    mask = np.zeros((h, w), np.uint8)
    for center in centers:
        cv2.circle(mask, tuple(np.rint(center).astype(int)), radius, 255, -1)
    for ids in [[33, 160, 158, 133, 153, 144], [362, 385, 387, 263, 373, 380],
                [61, 40, 0, 270, 291, 321, 17, 91], [98, 97, 2, 326, 327]]:
        cv2.fillConvexPoly(mask, cv2.convexHull(p[ids].astype(np.int32)), 0)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)[mask > 0] / 255.
    if len(rgb) < 16:
        raise ValueError('Insufficient visible upper-cheek area')
    lum = rgb @ np.array([.2126, .7152, .0722])
    lo, hi = np.percentile(lum, [35, 90])
    rgb = rgb[(lum >= lo) & (lum <= hi)]
    bins = (rgb * 255).astype(np.uint8) // 24
    _, labels, counts = np.unique(bins, axis=0, return_inverse=True, return_counts=True)
    return np.median(rgb[labels == np.argmax(counts)], axis=0)


def skin_color(image, p):
    return rgb_hex(toon_skin_palette(skin_samples(image, p))['base_color'])


def hair_palette(image, p):
    """Landmark-guided heuristic, not hair segmentation. Abstain if crop lacks hair."""
    h, w = image.shape[:2]
    up = p[10] - p[152]
    up /= max(np.linalg.norm(up), 1.)
    side = np.array([-up[1], up[0]])
    fw = np.linalg.norm(p[234] - p[454])
    mask = np.zeros((h, w), np.uint8)
    # Include upper forehead fringe and crown; exclude the face oval.
    for height in [.025, .10, .20, .32]:
        for lateral in [-.28, -.14, 0., .14, .28]:
            center = p[10] + fw * (height * up + lateral * side)
            cv2.circle(mask, tuple(np.rint(center).astype(int)), max(2, int(fw * .055)), 255, -1)
    oval = list({i for edge in mp.solutions.face_mesh.FACEMESH_FACE_OVAL for i in edge})
    cv2.fillConvexPoly(mask, cv2.convexHull(p[oval].astype(np.int32)), 0)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)[mask > 0] / 255.
    if len(rgb) < 32:
        return None, dict(hair_detected=False, hair_reason='crown outside image or insufficient samples')
    hsv = cv2.cvtColor(rgb.astype(np.float32)[None], cv2.COLOR_RGB2HSV)[0]
    # Discard glare / bright neutral studio background before dominant-color clustering.
    valid = (hsv[:, 2] < .90) & ~((hsv[:, 1] < .09) & (hsv[:, 2] > .65))
    rgb = rgb[valid]
    if len(rgb) < 32:
        return None, dict(hair_detected=False, hair_reason='no reliable non-background crown pixels')
    lum = rgb @ np.array([.2126, .7152, .0722])
    lo, hi = np.percentile(lum, [10, 75])
    rgb = rgb[(lum >= lo) & (lum <= hi)]
    _, labels, counts = np.unique((rgb * 255).astype(np.uint8) // 24, axis=0,
                                   return_inverse=True, return_counts=True)
    base = np.median(rgb[labels == np.argmax(counts)], axis=0)
    # Slight cool chromatic shadow; no black multiplier for skin (separate palette).
    shade = np.clip(base * [.78, .80, .88], 0, 1)
    return dict(base_color=base.tolist(), shade_color=shade.tolist()), dict(
        hair_detected=True, hair_sample_count=len(rgb), hair_method='landmark crown ROI, glare rejection, dominant RGB bin',
        hair_limitation='heuristic ROI can include dark background, hats or occlusion; not semantic segmentation')


def toon_diffuse(aligned, ap, palette):
    """Replace skin illumination with three chromatic bands, retaining eyes/lips/brows."""
    hsv = cv2.cvtColor(aligned.astype(np.float32) / 255., cv2.COLOR_BGR2HSV)
    # Warm low/moderate-saturation skin only. Protect linework and strong makeup.
    skin = (hsv[:, :, 0] < 55) & (hsv[:, :, 1] < .65) & (hsv[:, :, 2] > .22)
    for ids in [[33, 160, 158, 133, 153, 144], [362, 385, 387, 263, 373, 380],
                [61, 40, 0, 270, 291, 321, 17, 91], [70, 63, 105, 66, 107],
                [336, 296, 334, 293, 300]]:
        protected = np.zeros(skin.shape, np.uint8)
        cv2.fillConvexPoly(protected, cv2.convexHull(ap[ids].astype(np.int32)), 255)
        protected = cv2.dilate(protected, np.ones((5, 5), np.uint8))
        skin &= protected == 0
    if skin.any():
        lo, hi = np.percentile(hsv[:, :, 2][skin], [25, 60])
        band = np.where(hsv[:, :, 2] < lo, 2, np.where(hsv[:, :, 2] < hi, 1, 0))
        colors = np.array([palette[k][::-1] for k in ['base_color', 'shade_color', 'shade2_color']]) * 255
        aligned = aligned.copy()
        aligned[skin] = np.rint(colors[band[skin]]).astype(np.uint8)
    return aligned


def write_png(path, image):
    ok, encoded = cv2.imencode('.png', image)
    if not ok:
        raise ValueError(f'Cannot encode {path.name}')
    path.write_bytes(encoded.tobytes())


def textures(image, p, output, pupil=True, palette=None):
    # Similarity/affine alignment corrects roll/scale only, never invents hidden geometry.
    left, right = (p[33] + p[133]) / 2, (p[362] + p[263]) / 2
    delta = right - left
    third = (left + right) / 2 + np.array([-delta[1], delta[0]])
    transform = cv2.getAffineTransform(np.float32([left, right, third]),
                                       np.float32([[164, 195], [348, 195], [256, 379]]))
    aligned = cv2.warpAffine(cv2.bilateralFilter(image, 9, 48, 7), transform, (512, 512))
    ap = cv2.transform(p.astype(np.float32)[None], transform)[0]
    mask = np.zeros((512, 512), np.uint8)
    oval = list({i for edge in mp.solutions.face_mesh.FACEMESH_FACE_OVAL for i in edge})
    cv2.fillConvexPoly(mask, cv2.convexHull(ap[oval].astype(np.int32)), 255)
    if palette is not None:
        aligned = toon_diffuse(aligned, ap, palette)
    rgba = cv2.cvtColor(aligned, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = cv2.GaussianBlur(mask, (0, 0), 1.5)
    write_png(output / 'face_diffuse.png', rgba)
    if not pupil:
        return None
    atlas = np.zeros((128, 256, 4), np.uint8)
    for n, ids in enumerate([list(range(468, 473)), list(range(473, 478))]):
        center, radius = cv2.minEnclosingCircle(p[ids].astype(np.float32))
        radius = max(radius, 1.)
        scale = 48. / radius
        matrix = np.float32([[scale, 0, 64 - center[0] * scale],
                             [0, scale, 64 - center[1] * scale]])
        patch = cv2.warpAffine(image, matrix, (128, 128))
        lab = cv2.cvtColor(patch, cv2.COLOR_BGR2LAB)
        lab[:, :, 0] = cv2.createCLAHE(clipLimit=1.2, tileGridSize=(4, 4)).apply(lab[:, :, 0])
        patch = cv2.cvtColor(cv2.cvtColor(lab, cv2.COLOR_LAB2BGR), cv2.COLOR_BGR2BGRA)
        alpha = np.zeros((128, 128), np.uint8)
        cv2.circle(alpha, (64, 64), 48, 255, -1)
        patch[:, :, 3] = cv2.GaussianBlur(alpha, (0, 0), .7)
        atlas[:, n * 128:(n + 1) * 128] = patch
    write_png(output / 'pupil_accent.png', atlas)
    return output / 'pupil_accent.png'


def extract(input_path, output_dir, pupil=True, avatar=None):
    if avatar not in (None, 'man', 'woman'):
        raise ValueError('avatar must be man or woman')
    input_path, output = Path(input_path), Path(output_dir)
    if not input_path.is_file() or not 0 < input_path.stat().st_size <= 16 * 1024 * 1024:
        raise ValueError('Input must be an existing image between 1 byte and 16 MiB')
    image = cv2.imdecode(np.frombuffer(input_path.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('Cannot decode portrait image')
    h, w = image.shape[:2]
    if min(h, w) < 96 or h * w > 32_000_000:
        raise ValueError('Image must be >=96 pixels per side and <=32 megapixels')
    scale = min(1., 1600 / max(h, w))
    inference = cv2.resize(image, None, fx=scale, fy=scale) if scale < 1 else image
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, max_num_faces=2,
                                        refine_landmarks=True, min_detection_confidence=.6) as mesh:
        faces = mesh.process(cv2.cvtColor(inference, cv2.COLOR_BGR2RGB)).multi_face_landmarks
    if not faces or len(faces) != 1 or len(faces[0].landmark) != 478:
        raise ValueError('Exactly one visible face with 478 landmarks is required')
    points = np.array([(v.x, v.y, v.z) for v in faces[0].landmark], np.float64)
    metrics, controls, quality, p = geometry(points, w, h)
    expression, expression_metrics = expression_features(points, w, h)
    metrics.update(expression_metrics)
    quality['expression_limitation'] = 'Single-photo geometry with population eye baseline; open smile is not verified tooth visibility'
    raw_skin = skin_samples(image, p)
    palette = toon_skin_palette(raw_skin)
    tint = rgb_hex(palette['base_color'])
    hair, hair_quality = hair_palette(image, p)
    quality.update(hair_quality)
    output.mkdir(parents=True, exist_ok=True)
    texture = textures(image, p, output, pupil, palette)
    offset = float(np.clip((metrics['eye_distance'] - .26) / 2, -.04, .04))
    result = dict(schema_version=3, expression=expression, skin_tint=tint, skin=palette, hair=hair,
                  source_skin_tint=rgb_hex(raw_skin), color_space='sRGB normalized 0..1',
                  blendshapes=dict(Joy=controls['smile_degree'], EyeSlanted=controls['eye_slant'],
                                   EyeDistance=controls['eye_distance'], JawRound=controls['jaw_roundness'],
                                   EyeSize=controls['eye_size'], EyeOpenness=controls['eye_openness']),
                  bone_offsets=dict(LeftEye=[offset, 0., 0.], RightEye=[-offset, 0., 0.]),
                  texture_path=texture.resolve().as_posix() if texture else None,
                  diffuse_texture_path=(output / 'face_diffuse.png').resolve().as_posix(),
                  features=controls, metrics=metrics, quality=quality,
                  normalization_ranges=RANGES, landmark_count=len(points),
                  landmark_space='normalized image x/y; z relative to head, not meters',
                  bone_offset_space='face-width units; Unity local +X toward subject left; neutral spacing 0.26',
                  pupil_layout='256x128: subject right iris then subject left iris; RGBA',
                  landmarks=points.tolist(), source_size=[w, h])
    if avatar is not None:
        result['avatar_id'] = avatar
    target = output / 'face_params.json'
    temporary = output / 'face_params.json.tmp'
    temporary.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
    temporary.replace(target)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--avatar', choices=['man', 'woman'], help='Explicit portrait identity; never infer model selection from a photo')
    parser.add_argument('--output_dir', type=Path, help='Override output directory; defaults to per-avatar cache when --avatar is supplied')
    parser.add_argument('--no_pupil', action='store_true', help='Skip optional iris atlas')
    args = parser.parse_args()
    output = args.output_dir
    if output is None:
        if not args.avatar:
            parser.error('Provide --avatar man/woman or --output_dir')
        output = Path(__file__).resolve().parents[1] / 'artifacts/validation/face-stage2' / args.avatar
    try:
        result = extract(args.input, output, not args.no_pupil, avatar=args.avatar)
    except (ValueError, OSError, cv2.error) as error:
        parser.exit(2, f'Face extraction failed: {error}\n')
    print(json.dumps({k: result[k] for k in ['landmark_count', 'skin_tint', 'blendshapes', 'texture_path']}, indent=2))


if __name__ == '__main__':
    main()
