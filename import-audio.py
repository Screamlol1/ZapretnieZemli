"""Copy the selected user-provided DragonSound effects without transcoding."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

# Stable filenames keep network payloads and imports independent of local paths.
SELECTION = [
    ('metal', 'Звон металла', 'effect', 'fight/jeleznyie-okovyi--zvon-metalla_optimized.mp3', 0, 1.4, .45),
    ('battle', 'Столкновение мечей', 'ambience', 'fight/medieval-battle-knights-in-armor-clash-of-swords__mp3cut_net__optimized.mp3', 0, None, .32),
    ('footstep', 'Шаги по листве', 'effect', 'situation/the-sound-of-footsteps-on-the-leaves-in-the-forest_optimized.mp3', 3, 1.1, .45),
    ('monster', 'Рёв чудовища', 'effect', 'monsters/the-dragon-growls-hisses-releases-flames__mp3cut_net__optimized.mp3', 0, 1.7, .3),
    ('wolf', 'Рычание волка', 'effect', 'monsters/wolf-growl_optimized.mp3', 1, 1.6, .35),
    ('break', 'Разбитое стекло', 'effect', 'situation/noise-when-a-glass-window-is-broken_optimized.mp3', 0, 1.2, .3),
    ('thunder', 'Гром', 'effect', 'nature/thunder-lightning_optimized.mp3', 0, 2.5, .3),
    ('bell', 'Колокол поселения', 'effect', 'city/zvon-cerkovnyx-srednevekovyx-kolokolov__mp3cut_net___1__optimized.mp3', 0, 2, .35),
    ('blacksmith', 'Кузница', 'effect', 'city/anvil-blacksmith-forge_optimized.mp3', 0, 1.2, .35),
    ('wind', 'Лёгкий ветер', 'ambience', 'nature/legkii-veter_optimized.mp3', 0, None, .5),
    ('forest', 'Листва леса', 'ambience', 'nature/listia-derevev-na-vetru-bez-vetra_optimized.mp3', 0, None, .5),
    ('cave', 'Капли в пещере', 'ambience', 'nature/the-sound-of-a-dripping-cave__mp3cut_net__optimized.mp3', 0, None, .4),
    ('river', 'Течение реки', 'ambience', 'nature/the-river_optimized.mp3', 0, None, .42),
    ('marsh', 'Болотная вода', 'ambience', 'nature/bulkane-bolota__mp3cut_net__optimized.mp3', 0, None, .4),
    ('fire', 'Костёр', 'ambience', 'nature/bonfire_optimized.mp3', 0, None, .4),
    ('city', 'Средневековый город', 'ambience', 'city/srednevekovyi-gorod-bez-losadei_optimized.mp3', 0, None, .35),
    ('tavern', 'Разговоры в таверне', 'ambience', 'city/bar-pub-crowd-environmental-sounds_optimized.mp3', 0, None, .3),
    ('rain', 'Тихий дождь', 'ambience', 'nature/quiet-rain_optimized.mp3', 0, None, .45),
    ('night', 'Ночные сверчки', 'ambience', 'nature/cricket-chirping_optimized.mp3', 0, None, .4),
    ('snow-step', 'Шаги по снегу', 'effect', 'nature/steps-on-an-icy-surface-crunching-snow_optimized.mp3', 0, 1.2, .4),
]


def mp3_duration(data):
    """Read MPEG Layer III frame lengths; no external codec is needed to import."""
    index = 0
    if data[:3] == b'ID3' and len(data) >= 10:
        index = 10 + sum((data[6 + i] & 127) << (7 * (3 - i)) for i in range(4))
    total = 0.0
    while index + 4 < len(data):
        h = int.from_bytes(data[index:index + 4], 'big')
        version, layer, bitrate_index, rate_index = (h >> 19) & 3, (h >> 17) & 3, (h >> 12) & 15, (h >> 10) & 3
        if h >> 21 != 0x7ff or version == 1 or layer != 1 or bitrate_index in (0, 15) or rate_index == 3:
            index += 1
            continue
        bitrate = ([0,32,40,48,56,64,80,96,112,128,160,192,224,256,320] if version == 3 else [0,8,16,24,32,40,48,56,64,80,96,112,128,144,160])[bitrate_index]
        rate = [44100,48000,32000][rate_index] // (1 if version == 3 else 2 if version == 2 else 4)
        length = (144000 if version == 3 else 72000) * bitrate // rate + ((h >> 9) & 1)
        if index + length > len(data):
            break
        total += (1152 if version == 3 else 576) / rate
        index += length
    return round(total, 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, default=Path.home()/'Downloads'/'DragonSound')
    args = parser.parse_args()
    source = args.source.resolve()/'sounds'
    if not source.is_dir():
        raise SystemExit(f'Not found: {source}')
    public = Path(__file__).resolve().parent/'public'
    destination = public/'audio'
    destination.mkdir(exist_ok=True)
    clips = []
    total = 0
    for clip_id, title, kind, relative, offset, limit, gain in SELECTION:
        original = source/relative
        data = original.read_bytes()
        duration = mp3_duration(data)
        if duration <= offset or len(data) > 3_000_000:
            raise ValueError(f'Invalid or oversized audio: {relative}')
        target = destination/(clip_id+'.mp3')
        shutil.copyfile(original, target)
        clips.append(dict(id=clip_id,title=title,kind=kind,url='audio/'+target.name,bytes=len(data),duration=duration,offset=offset,limit=limit,gain=gain,source='DragonSound/sounds/'+relative,sha256=hashlib.sha256(data).hexdigest()))
        total += len(data)
    if total > 15_000_000:
        raise ValueError('Selected effects exceed the 15 MB release budget')
    manifest = dict(version=1,provenance='Files supplied by the user in DragonSound/sounds; copied without transcoding.',license='No license metadata was provided; no license is inferred.',totalBytes=total,clips=clips,synthesized=[dict(id='dice',title='Короткий шорох костей',source='Generated locally by the game using filtered noise; no source recording.'),dict(id='magic',title='Мягкий магический тон',source='Generated locally by the game using oscillators; no source recording.')])
    (public/'audio-catalog.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Imported {len(clips)} effects: {total:,} bytes. Music was not imported.')


if __name__ == '__main__':
    main()
