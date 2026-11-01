"""Run the rule engine with the desktop runtime or a source install's Node.js.

The desktop launcher supplies ZZ_NODE as an absolute path. Commands stay argument
lists, so installation paths containing spaces or Cyrillic need no shell quoting.
"""
import os
from pathlib import Path
import subprocess


def executable():
    configured=os.environ.get('ZZ_NODE')
    if not configured:return 'node'
    if not Path(configured).is_absolute():
        raise OSError('ZZ_NODE должен содержать абсолютный путь к Node.js.')
    return configured


def run_node(arguments, **options):
    if isinstance(arguments,(str,bytes)):
        raise TypeError('Node.js arguments must be a sequence, not a shell command.')
    if options.get('shell'):
        raise ValueError('The rule engine must run without a shell.')
    if os.name=='nt':
        options['creationflags']=options.get('creationflags',0)|subprocess.CREATE_NO_WINDOW
    return subprocess.run([executable(),*arguments],**options)
