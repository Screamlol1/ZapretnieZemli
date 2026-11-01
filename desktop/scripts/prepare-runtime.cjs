#!/usr/bin/env node
'use strict';

// Only build-time downloads. Installed clients use these pinned bundled runtimes.
const fs = require('node:fs/promises');
const { createReadStream, createWriteStream } = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { Readable } = require('node:stream');
const { pipeline } = require('node:stream/promises');
const { spawnSync } = require('node:child_process');

const desktopRoot = path.resolve(__dirname, '..');
const cacheRoot = path.join(desktopRoot, '.cache');
const runtimeRoot = path.join(desktopRoot, '.runtime');
const lock = require('../runtime-lock.json');
const offline = process.argv.includes('--no-download');

function inside(root, target) {
  const resolved = path.resolve(target);
  const relative = path.relative(path.resolve(root), resolved);
  if (!relative || relative === '..' || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
    throw new Error(`Refusing an operation outside the build directory: ${target}`);
  }
  return resolved;
}

async function sha256(filename) {
  const hash = crypto.createHash('sha256');
  for await (const chunk of createReadStream(filename)) hash.update(chunk);
  return hash.digest('hex');
}

async function cacheArtifact(artifact) {
  if (!/^[a-f0-9]{64}$/.test(artifact.sha256) || !artifact.url.startsWith('https://')) {
    throw new Error(`Invalid pinned download: ${artifact.filename}`);
  }
  if (path.basename(artifact.filename) !== artifact.filename) throw new Error('Invalid artifact filename');
  const destination = inside(cacheRoot, path.join(cacheRoot, artifact.filename));
  try {
    if (await sha256(destination) === artifact.sha256) {
      console.log(`Verified cache: ${artifact.filename}`);
      return destination;
    }
    if (offline) throw new Error(`Cached checksum does not match: ${artifact.filename}`);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    if (offline) throw new Error(`Missing cached download: ${artifact.filename}`);
  }
  console.log(`Downloading ${artifact.filename}`);
  const partial = inside(cacheRoot, `${destination}.part-${process.pid}`);
  try {
    try {
      const response = await fetch(artifact.url, { signal: AbortSignal.timeout(300000) });
      if (!response.ok || !response.body) throw new Error(`Download failed (${response.status}): ${artifact.url}`);
      if (!response.url.startsWith('https://')) throw new Error('Refusing an insecure download redirect');
      await pipeline(Readable.fromWeb(response.body), createWriteStream(partial, { flags: 'wx' }));
    } catch (error) {
      // Windows curl uses the OS networking stack, useful for networks where
      // Node's direct connection fails. The same pinned hash is still required.
      await fs.rm(partial, { force: true });
      console.log(`Retrying with Windows HTTPS client: ${artifact.filename}`);
      run('curl.exe', ['--fail', '--location', '--silent', '--show-error',
        '--connect-timeout', '15', '--max-time', '300', '--proto', '=https',
        '--proto-redir', '=https', '--output', partial, artifact.url], { timeout: 310000 });
    }
    const actual = await sha256(partial);
    if (actual !== artifact.sha256) throw new Error(`SHA256 mismatch for ${artifact.filename}: ${actual}`);
    await fs.rename(partial, destination);
    return destination;
  } finally {
    await fs.rm(partial, { force: true });
  }
}

function run(executable, args, options = {}) {
  const result = spawnSync(executable, args, {
    encoding: 'utf8', windowsHide: true, timeout: 180000, ...options,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${path.basename(executable)} failed: ${result.stderr || result.stdout}`);
  return result.stdout.trim();
}

async function extract(archive, destination) {
  inside(runtimeRoot, destination);
  await fs.mkdir(destination, { recursive: true });
  // Pass paths as environment values: no shell interpolation of workspace names.
  run('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command',
    "$ErrorActionPreference = 'Stop'; Expand-Archive -LiteralPath $env:ZZ_RUNTIME_ARCHIVE -DestinationPath $env:ZZ_RUNTIME_DESTINATION -Force"], {
    env: { ...process.env, ZZ_RUNTIME_ARCHIVE: archive, ZZ_RUNTIME_DESTINATION: destination },
  });
}

async function extractNode(archive, destination) {
  inside(runtimeRoot, destination);
  await fs.mkdir(destination);
  // npm is not needed at runtime: extract just two entries instead of thousands
  // of dependency files, which also avoids slow antivirus scans while building.
  run('powershell.exe', ['-NoLogo', '-NoProfile', '-NonInteractive', '-Command', [
    "$ErrorActionPreference = 'Stop'",
    'Add-Type -AssemblyName System.IO.Compression.FileSystem',
    '$zip = [System.IO.Compression.ZipFile]::OpenRead($env:ZZ_RUNTIME_ARCHIVE)',
    'try { foreach ($name in @("node.exe", "LICENSE")) {',
    '$entry = $zip.GetEntry($env:ZZ_RUNTIME_NODE_PREFIX + "/" + $name)',
    'if ($null -eq $entry) { throw "Missing runtime archive entry: $name" }',
    '[System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, (Join-Path $env:ZZ_RUNTIME_DESTINATION $name), $true)',
    '} } finally { $zip.Dispose() }',
  ].join('\n')], {
    env: { ...process.env, ZZ_RUNTIME_ARCHIVE: archive, ZZ_RUNTIME_DESTINATION: destination,
      ZZ_RUNTIME_NODE_PREFIX: lock.node.archiveDirectory },
  });
}

async function replaceDirectory(source, name) {
  const destination = inside(runtimeRoot, path.join(runtimeRoot, name));
  // Only the named generated runtime folder is replaced, never user game data.
  await fs.rm(destination, { recursive: true, force: true });
  await fs.rename(source, destination);
}

async function main() {
  if (process.platform !== 'win32') throw new Error('Prepare the Windows runtimes on Windows.');
  const unknown = process.argv.slice(2).filter(arg => arg !== '--no-download');
  if (unknown.length) throw new Error(`Unknown arguments: ${unknown.join(' ')}`);
  await fs.mkdir(cacheRoot, { recursive: true });
  await fs.mkdir(runtimeRoot, { recursive: true });
  const [pythonZip, nodeZip, cloudExe, cloudLicense] = await Promise.all([
    cacheArtifact(lock.python), cacheArtifact(lock.node), cacheArtifact(lock.cloudflared),
    cacheArtifact(lock.cloudflared.license),
  ]);
  const staging = inside(runtimeRoot, path.join(runtimeRoot, `.prepare-${process.pid}-${Date.now()}`));
  await fs.mkdir(staging);
  try {
    const pythonDir = path.join(staging, 'python');
    const nodeDir = path.join(staging, 'node');
    const cloudDir = path.join(staging, 'cloudflared');
    await extract(pythonZip, pythonDir);
    await extractNode(nodeZip, nodeDir);
    await fs.mkdir(cloudDir);
    await fs.copyFile(cloudExe, path.join(cloudDir, 'cloudflared.exe'));
    await fs.copyFile(cloudLicense, path.join(cloudDir, 'LICENSE'));
    await fs.access(path.join(pythonDir, lock.python.licenseFile));
    await fs.writeFile(path.join(pythonDir, lock.python.pathFile), [
      '# Isolated Python for Zapretnie Zemli. Paths are relative to this file.',
      lock.python.stdlibArchive, '.', '../../game', '',
    ].join('\n'), 'utf8');
    const pythonVersion = run(path.join(pythonDir, 'python.exe'), ['-c',
      'import sys, sqlite3, ssl, json, secrets, subprocess, http.server; print(sys.version.split()[0])']);
    const nodeVersion = run(path.join(nodeDir, 'node.exe'), ['--version']);
    const cloudVersion = run(path.join(cloudDir, 'cloudflared.exe'), ['--version']);
    if (pythonVersion !== lock.python.version || nodeVersion !== `v${lock.node.version}` || !cloudVersion.includes(lock.cloudflared.version)) {
      throw new Error('Extracted runtime version does not match runtime-lock.json');
    }
    await replaceDirectory(pythonDir, 'python');
    await replaceDirectory(nodeDir, 'node');
    await replaceDirectory(cloudDir, 'cloudflared');
    await fs.writeFile(path.join(runtimeRoot, 'runtime-manifest.json'), `${JSON.stringify({
      schemaVersion: lock.schemaVersion, platform: lock.platform, arch: lock.arch,
      python: { version: lock.python.version, archiveSha256: lock.python.sha256 },
      node: { version: lock.node.version, archiveSha256: lock.node.sha256 },
      cloudflared: { version: lock.cloudflared.version, sha256: lock.cloudflared.sha256 },
    }, null, 2)}\n`);
    console.log(`Ready: Python ${pythonVersion}, Node ${nodeVersion}, ${cloudVersion}`);
    console.log(`Runtime resources: ${runtimeRoot}`);
  } finally {
    await fs.rm(inside(runtimeRoot, staging), { recursive: true, force: true });
  }
}

main().catch(error => {
  console.error(`Runtime preparation failed: ${error.message}`);
  process.exitCode = 1;
});
