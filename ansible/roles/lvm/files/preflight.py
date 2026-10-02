"""Read-only storage checks, executed on the guest before any LVM changes."""
import json
import os
from pathlib import Path
import subprocess
import sys


def command(*args, absent_ok=False):
    result = subprocess.run(args, text=True, capture_output=True, check=False)
    if absent_ok and result.returncode == 1 and not result.stdout.strip():
        return {}
    if result.returncode:
        raise ValueError(f"{' '.join(args)}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def flatten(nodes):
    for node in nodes:
        yield node
        yield from flatten(node.get('children', []))


def inspect(config):
    tree = command('lsblk', '--json', '--paths', '--output',
                   'NAME,TYPE,SERIAL,MOUNTPOINTS')['blockdevices']
    disks = [d for d in flatten(tree)
             if d['type'] == 'disk' and (d.get('serial') or '').strip() == config['serial']]
    if len(disks) != 1:
        raise ValueError('Expected exactly one whole disk with serial ' + config['serial'])
    disk = disks[0]
    device = os.path.realpath(disk['name'])
    volumes = config['volumes']
    paths = {v['path'] for v in volumes}
    for child in flatten([disk]):
        if child['type'] not in ('disk', 'lvm'):
            raise ValueError('Data disk contains partitions or an unsupported device: ' + child['name'])
        if any(p and p not in paths for p in child.get('mountpoints', [])):
            raise ValueError('Data disk is mounted outside the configured data paths')
    signatures = command('wipefs', '--json', device).get('signatures', [])
    types = {s['type'] for s in signatures}
    pvs = command('pvs', '--reportformat', 'json', '-o', 'pv_name,vg_name')['report'][0]['pv']
    members = [p for p in pvs if p['vg_name'].strip() == config['vg']]
    own = [p for p in pvs if os.path.realpath(p['pv_name'].strip()) == device]
    if types:
        if types != {'LVM2_member'} or len(own) != 1 or own[0]['vg_name'].strip() != config['vg']:
            raise ValueError('Disk has existing signatures and is not the expected LVM PV')
    elif own or members or disk.get('children'):
        raise ValueError('Ambiguous blank disk or existing volume group on another disk')
    if any(os.path.realpath(p['pv_name'].strip()) != device for p in members):
        raise ValueError('Volume group includes another disk; refusing to modify it')

    mounts = list(flatten(command('findmnt', '--json', '--output',
                                  'SOURCE,TARGET,FSTYPE')['filesystems']))
    pending = []
    for volume in volumes:
        path = Path(volume['path'])
        expected = os.path.realpath(f"/dev/{config['vg']}/{volume['name']}")
        if os.path.realpath(path) != str(path):
            raise ValueError(f'{path}: symlink in mount path is not supported')
        exact = [m for m in mounts if m['target'] == str(path)]
        if exact:
            if len(exact) != 1 or os.path.realpath(exact[0]['source']) != expected or exact[0]['fstype'] != 'ext4':
                raise ValueError(f'{path}: mounted from an unexpected device or filesystem')
            continue
        if (not config['migrate'] or config.get('quiesced', False)) and any(
                m['target'].startswith(str(path) + '/') for m in mounts):
            raise ValueError(f'{path}: nested mounts present; stop containers and unmount these first')
        if any(os.path.realpath(m['source']) == expected for m in mounts):
            raise ValueError(f'{expected}: already mounted elsewhere; check an interrupted migration')
        if path.exists() and not path.is_dir():
            raise ValueError(f'{path}: not a directory')
        backup = Path(str(path) + '.pre-lvm')
        if backup.exists() or backup.is_symlink():
            raise ValueError(f'{backup}: previous migration exists; recover manually before retrying')
        nonempty = path.exists() and any(path.iterdir())
        if nonempty and not config['migrate']:
            raise ValueError(f'{path}: existing data; use app_storage_migrate_existing=true in a maintenance window')
        pending.append(dict(volume, nonempty=bool(nonempty), exists=path.exists()))
    return {'device': device, 'pending': pending}


if __name__ == '__main__':
    try:
        print(json.dumps(inspect(json.load(sys.stdin))))
    except (ValueError, OSError, KeyError) as error:
        sys.exit(str(error))
