"""Build compact game audio from user-supplied recordings; never modify sources."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

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


PIPELINE_VERSION = 2
SAMPLE_RATE = 32000
TARGET_MEAN_DB = {'effect': -18.0, 'ambience': -22.0}
TARGET_PEAK_DB = -2.0
MAX_BOOST_DB = 9.0
MAX_REDUCTION_DB = -18.0


def run(arguments):
    return subprocess.run([str(value) for value in arguments], check=True, capture_output=True,
                          text=True, encoding='utf-8', errors='replace', timeout=180)


def find_tools(executable):
    resolved = shutil.which(str(executable))
    ffmpeg = Path(resolved or executable).resolve()
    ffprobe = ffmpeg.with_name('ffprobe' + ffmpeg.suffix)
    if not ffmpeg.is_file() or not ffprobe.is_file():
        raise ValueError('FFmpeg and ffprobe are required only on the development machine; use --ffmpeg <path>.')
    return ffmpeg, ffprobe


def probe(ffprobe, filename):
    info = json.loads(run([ffprobe, '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                          'stream=sample_rate,channels,duration:format=duration', '-of', 'json', filename]).stdout)
    stream = info['streams'][0]
    duration = float(info['format'].get('duration', stream.get('duration', 0)))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('Audio has no finite duration')
    return dict(duration=duration, sampleRate=int(stream['sample_rate']), channels=int(stream['channels']))


def measure(ffmpeg, filename, filters):
    output = run([ffmpeg, '-nostdin', '-hide_banner', '-i', filename, '-map', '0:a:0',
                  '-af', filters + ',volumedetect', '-f', 'null', '-']).stderr
    def field(name):
        match = re.search(rf'{name}:\s*(-?\d+(?:\.\d+)?) dB', output)
        if not match:
            raise ValueError('Cannot measure audio level: ' + name)
        return float(match.group(1))
    return field('mean_volume'), field('max_volume')


def normalization(mean_db, peak_db, kind):
    return round(max(MAX_REDUCTION_DB, min(MAX_BOOST_DB, TARGET_MEAN_DB[kind] - mean_db,
                                          TARGET_PEAK_DB - peak_db)), 2)


def build_library(source, public, ffmpeg, selection=SELECTION):
    """Prepare every clip before publishing; the source directory is read-only."""
    ffmpeg, ffprobe = find_tools(ffmpeg)
    source, public = Path(source).resolve()/'sounds', Path(public).resolve()
    if not source.is_dir():
        raise ValueError('Expected the supplied DragonSound folder containing sounds/')
    if public == source or public.is_relative_to(source):
        raise ValueError('Output must be outside the source recordings')
    public.mkdir(parents=True, exist_ok=True)
    destination = public/'audio'
    clips = []
    version = run([ffmpeg, '-version']).stdout.splitlines()[0]
    # Temporary output stays beside its destination, allowing atomic file replacement.
    with tempfile.TemporaryDirectory(prefix='.audio-import-', dir=public) as temporary:
        staging = Path(temporary)
        for clip_id, title, kind, relative, offset, limit, gain in selection:
            if not re.fullmatch(r'[a-z0-9-]+', clip_id) or kind not in TARGET_MEAN_DB:
                raise ValueError('Invalid audio selection')
            original = (source/relative).resolve()
            if not original.is_relative_to(source):
                raise ValueError('Source must stay inside sounds/')
            data = original.read_bytes()
            source_hash = hashlib.sha256(data).hexdigest()
            metadata = probe(ffprobe, original)
            if offset < 0 or metadata['duration'] <= offset or len(data) > 3_000_000:
                raise ValueError('Invalid or oversized selected audio: ' + relative)
            duration = min(limit, metadata['duration'] - offset) if limit else metadata['duration'] - offset
            channels = 1 if kind == 'effect' else min(2, metadata['channels'])
            bitrate = 64 if kind == 'effect' else 80
            trim = f'atrim=start={offset:.6f}' + (f':duration={duration:.6f}' if limit else '')
            base = f'{trim},asetpts=PTS-STARTPTS,aformat=sample_fmts=fltp:sample_rates={SAMPLE_RATE}:channel_layouts={"mono" if channels == 1 else "stereo"}'
            mean_db, peak_db = measure(ffmpeg, original, base)
            adjustment = normalization(mean_db, peak_db, kind)
            fade_in, fade_out = (.012, .06) if kind == 'effect' else (.05, .1)
            fade_in, fade_out = min(fade_in, duration/4), min(fade_out, duration/4)
            filters = (f'{base},volume={adjustment:.2f}dB,afade=t=in:st=0:d={fade_in:.6f},'
                       f'afade=t=out:st={max(0, duration-fade_out):.6f}:d={fade_out:.6f}')
            target = staging/(clip_id+'.mp3')
            run([ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', original,
                 '-map', '0:a:0', '-vn', '-sn', '-dn', '-map_metadata', '-1', '-map_chapters', '-1',
                 '-af', filters, '-ac', channels, '-ar', SAMPLE_RATE, '-c:a', 'libmp3lame', '-b:a', f'{bitrate}k',
                 '-threads', '1', '-fflags', '+bitexact', '-flags:a', '+bitexact', '-write_xing', '1',
                 '-id3v2_version', '0', target])
            derived = target.read_bytes()
            derived_hash = hashlib.sha256(derived).hexdigest()
            encoded = probe(ffprobe, target)
            if abs(encoded['duration'] - duration) > .15:
                raise ValueError('Prepared audio duration is inconsistent: ' + clip_id)
            if hashlib.sha256(original.read_bytes()).hexdigest() != source_hash:
                raise ValueError('Source changed during import: ' + relative)
            clips.append(dict(id=clip_id, title=title, kind=kind, url='audio/'+target.name,
                              bytes=len(derived), duration=round(duration, 6), encodedDuration=round(encoded['duration'], 6),
                              offset=0, limit=limit, gain=gain, prepared=True,
                              source='DragonSound/sounds/'+relative, sourceBytes=len(data), sourceDuration=metadata['duration'],
                              sourceOffset=offset, sourceLimit=limit, sourceSha256=source_hash,
                              sha256=derived_hash, derivedSha256=derived_hash,
                              processing=dict(sampleRate=SAMPLE_RATE, channels=channels, bitrateKbps=bitrate,
                                              measuredMeanDb=mean_db, measuredPeakDb=peak_db, gainDb=adjustment,
                                              fadeIn=fade_in, fadeOut=fade_out, filter=filters)))
        total = sum(clip['bytes'] for clip in clips)
        if total > 15_000_000:
            raise ValueError('Selected effects exceed the 15 MB release budget')
        manifest = dict(version=PIPELINE_VERSION,
                        provenance='Recordings supplied by the user in DragonSound/sounds; originals unchanged. Game MP3 files are derived by the documented development import pipeline.',
                        license='No license metadata was provided; no license is inferred.',
                        sourceTotalBytes=sum(clip['sourceBytes'] for clip in clips), totalBytes=total,
                        processing=dict(version=PIPELINE_VERSION, ffmpeg=version, codec='libmp3lame', sampleRate=SAMPLE_RATE,
                                        targetMeanDb=TARGET_MEAN_DB, targetPeakDb=TARGET_PEAK_DB,
                                        maxBoostDb=MAX_BOOST_DB, maxReductionDb=MAX_REDUCTION_DB),
                        clips=clips,
                        synthesized=[dict(id='dice', title='Короткий шорох костей', source='Generated locally by the game using filtered noise; no source recording.'),
                                     dict(id='magic', title='Мягкий магический тон', source='Generated locally by the game using oscillators; no source recording.')])
        catalog = staging/'audio-catalog.json'
        catalog.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        destination.mkdir(exist_ok=True)
        for clip in clips:
            os.replace(staging/(clip['id']+'.mp3'), destination/(clip['id']+'.mp3'))
        os.replace(catalog, public/'audio-catalog.json')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path, default=Path.home()/'Downloads'/'DragonSound')
    parser.add_argument('--ffmpeg', default='ffmpeg', help='Development FFmpeg executable, with ffprobe alongside it')
    args = parser.parse_args()
    public = Path(__file__).resolve().parent/'public'
    manifest = build_library(args.source, public, args.ffmpeg)
    print(f'Prepared {len(manifest["clips"])} clips: {manifest["totalBytes"]:,} bytes '
          f'(source {manifest["sourceTotalBytes"]:,}). Originals unchanged; music not imported.')


if __name__ == '__main__':
    main()
