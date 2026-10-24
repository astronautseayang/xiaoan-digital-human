"""Fetch pinned licensed avatars; stage models and portable per-avatar profiles."""
import hashlib, json, shutil, urllib.request, zipfile
from pathlib import Path
root = Path(__file__).resolve().parents[1]
catalog = json.loads((root/'unity-patches/VrmAssets/avatar-catalog.json').read_text())
for avatar, entry in catalog.items():
    source = root/'assets/avatars'/entry['file']
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        temporary = source.with_suffix('.download')
        try:
            local_source = root/entry['local_source'] if entry.get('local_source') else None
            if local_source and local_source.exists():
                shutil.copyfile(local_source, temporary)
            else:
                urllib.request.urlretrieve(entry['source'], temporary)
            if entry.get('zip_member'):
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != entry['source_sha256']:
                    raise ValueError('Avatar archive checksum mismatch: '+avatar)
                with zipfile.ZipFile(temporary) as archive:
                    model = archive.read(entry['zip_member'])
                temporary.write_bytes(model)
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Avatar download checksum mismatch: '+avatar)
            temporary.replace(source)
        finally:
            temporary.unlink(missing_ok=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('Local avatar checksum mismatch: '+str(source))
    target = root/'human-code/Assets/StreamingAssets/Avatars'
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target/source.name)
    shutil.copyfile(source, root/'human-code/Assets/Models'/source.name)
    profile = root/entry['profile']
    if profile.exists():
        data = json.loads(profile.read_text())
        if data.get('avatar_id') != avatar:
            raise ValueError('Mismatched cached profile: '+avatar)
        output = target/'Profiles'/avatar
        output.mkdir(parents=True, exist_ok=True)
        for key in ('texture_path', 'diffuse_texture_path'):
            if data.get(key):
                texture = Path(data[key])
                if not texture.is_absolute(): texture = root/texture
                shutil.copyfile(texture, output/texture.name)
                data[key] = texture.name
        (output/'face_params.json').write_text(json.dumps(data, indent=2)+'\n')
for filename in ('avatar-catalog.json',):
    shutil.copyfile(root/'unity-patches/VrmAssets'/filename, target/filename)
print('Verified and staged the male VRM asset and profile')

# Remove legacy female assets from Unity import and packaged StreamingAssets.
for relative in ('human-code/Assets/Models/female.vrm',
                 'human-code/Assets/Models/AliciaSolid.vrm',
                 'human-code/Assets/Models/Alicia-license.html',
                 'human-code/Assets/StreamingAssets/female.vrm',
                 'human-code/Assets/StreamingAssets/AliciaSolid.vrm',
                 'human-code/Assets/StreamingAssets/Alicia-license.html',
                 'human-code/Assets/StreamingAssets/Avatars/female.vrm',
                 'human-code/Assets/StreamingAssets/Avatars/Alicia-license.html',
                 'human-code/Assets/StreamingAssets/Avatars/Fumiriya-license.html',
                 'human-code/Assets/StreamingAssets/Avatars/Seed-san-license.html',
                 'human-code/Assets/StreamingAssets/Avatars/Profiles/woman'):
    path=root/relative
    if path.is_dir(): shutil.rmtree(path)
    else: path.unlink(missing_ok=True)
    Path(str(path)+'.meta').unlink(missing_ok=True)

for pattern in ('FemaleInteractive*', 'StableIdle.*'):
    for path in (root/'human-code/Assets/Models').glob(pattern):
        path.unlink(missing_ok=True)
