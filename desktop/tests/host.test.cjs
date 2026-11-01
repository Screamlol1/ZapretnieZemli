const {describe, test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const fsp = fs.promises;
const path = require('node:path');
const net = require('node:net');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const {once} = require('node:events');
const {GameHost} = require('../host.cjs');

const desktop = path.resolve(__dirname, '..');
const runtime = path.join(desktop, '.runtime');
const python = path.join(runtime, 'python', 'python.exe');
const node = path.join(runtime, 'node', 'node.exe');
const testRoot = path.join(desktop, '.cache', 'tests');
const password = 'desktop integration password 42';
const reason = process.platform !== 'win32' ? 'Windows embedded runtimes require Windows.' :
  !fs.existsSync(python) || !fs.existsSync(node) ? 'Run npm run prepare:runtime before Windows integration tests.' : false;

function emptyPathEnvironment() {
  return {...Object.fromEntries(Object.entries(process.env).filter(([key]) => key.toUpperCase() !== 'PATH')), PATH: ''};
}

function runBundled(executable, args, options = {}) {
  const result = spawnSync(executable, args, {
    windowsHide: true, encoding: 'utf8', timeout: 20000,
    ...options, env: emptyPathEnvironment(),
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr || result.stdout);
  return result.stdout;
}

async function startWithoutPath(host) {
  // Changing the launcher environment also tests the actual environment inherited
  // by Python and its Node rule-engine children. These tests run sequentially.
  const previous = Object.entries(process.env).filter(([key]) => key.toUpperCase() === 'PATH');
  for (const [key] of previous) delete process.env[key];
  process.env.PATH = '';
  try {
    return await host.start();
  } catch (error) {
    const log = await fsp.readFile(path.join(host.data, 'server.log'), 'utf8').catch(() => '');
    error.message += '\n' + log.slice(-8000);
    throw error;
  } finally {
    for (const key of Object.keys(process.env)) if (key.toUpperCase() === 'PATH') delete process.env[key];
    for (const [key, value] of previous) process.env[key] = value;
  }
}

async function request(host, endpoint, {body, cookie, token, status = 200} = {}) {
  const headers = {'User-Agent': cookie ? 'Browser integration player' : 'Desktop integration master'};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (cookie) headers.Cookie = cookie;
  if (token) headers.Authorization = token;
  const response = await fetch(new URL(endpoint, host.state.localUrl), {
    method: body === undefined ? 'GET' : 'POST', headers,
    body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(15000),
  });
  const text = await response.text();
  assert.equal(response.status, status, `${endpoint}: ${text}`);
  const value = response.headers.get('content-type')?.startsWith('application/json') ? JSON.parse(text) : text;
  const accountCookie = response.headers.getSetCookie().find(value => value.startsWith('zz_account='));
  return {value, cookie: accountCookie?.split(';')[0]};
}

async function assertProcessStopped(child, url) {
  assert.ok(child.pid, 'The integration test must start a real OS process.');
  assert.equal(child.exitCode, 0, 'The Python host must close gracefully, without kill fallback.');
  assert.throws(() => process.kill(child.pid, 0), error => error.code === 'ESRCH', 'No Python host may remain orphaned.');
  await assert.rejects(fetch(new URL('api/health', url), {signal: AbortSignal.timeout(2000)}));
}

async function stopAndCheck(host) {
  const child = host.child;
  const url = host.state.localUrl;
  assert.ok(child);
  await host.stop();
  assert.equal(host.state.server, 'stopped');
  assert.equal(host.child, null);
  await assertProcessStopped(child, url);
}

describe('Windows GameHost with real bundled Python and Node', {skip: reason, concurrency: false}, () => {
  let folder, resources;
  const hosts = [];

  before(async () => {
    await fsp.mkdir(testRoot, {recursive: true});
    folder = await fsp.mkdtemp(path.join(testRoot, 'Установка с пробелами '));
    resources = path.join(folder, 'resources');
    const game = path.join(resources, 'game');
    await fsp.mkdir(game, {recursive: true});
    // Match the installed resources/game layout, not the source-only fallback.
    await fsp.copyFile(path.join(desktop, 'desktop_server.py'), path.join(resources, 'desktop_server.py'));
    const source = path.dirname(desktop);
    for (const entry of await fsp.readdir(source, {withFileTypes: true})) {
      if (entry.isFile() && /\.(py|mjs|json)$/.test(entry.name)) {
        await fsp.copyFile(path.join(source, entry.name), path.join(game, entry.name));
      }
    }
    await fsp.cp(path.join(source, 'public'), path.join(game, 'public'), {recursive: true});
  });

  after(async () => {
    for (const host of hosts) await host.stop();
    if (folder) {
      const resolved = path.resolve(folder);
      assert.ok(resolved.startsWith(path.resolve(testRoot) + path.sep), 'Cleanup must remain within isolated test data.');
      await fsp.rm(resolved, {recursive: true, force: true, maxRetries: 3, retryDelay: 100});
    }
  });

  function makeHost(name, port = 0) {
    const host = new GameHost({resources, runtime, data: path.join(folder, name), port});
    hosts.push(host);
    return host;
  }

  test('occupied port fallback, browser/desktop campaign, character rules, restart and portable backup', {timeout: 90000}, async () => {
    const occupied = net.createServer();
    occupied.listen(0, '127.0.0.1');
    await once(occupied, 'listening');
    const port = occupied.address().port;
    const host = makeHost('Сохранения игрока', port);
    try {
      await startWithoutPath(host);
      assert.notEqual(new URL(host.state.localUrl).port, String(port), 'An occupied port must select a free port.');
      assert.equal((await request(host, 'api/health')).value.ok, true);
      assert.equal((await request(host, 'api/health')).value.publicTest, true);
      assert.match((await request(host, '/')).value, /account\.js/);
      assert.match((await request(host, 'tools/rules.js')).value, /export/);

      const gm = await request(host, 'api/account/register', {body: {login: 'desktop.master', name: 'Мастер Windows', password}});
      const player = await request(host, 'api/account/register', {body: {login: 'browser.player', name: 'Игрок браузера', password}});
      assert.ok(gm.cookie && player.cookie && gm.cookie !== player.cookie);
      assert.ok(gm.value.recovery && player.value.recovery);
      const campaign = (await request(host, 'api/account/create', {cookie: gm.cookie, body: {title: 'Общий поход Windows и браузера'}})).value;
      const joined = (await request(host, 'api/account/connect', {cookie: player.cookie, body: {code: campaign.code, key: campaign.playerKey}})).value;
      assert.equal(campaign.role, 'gm');
      assert.equal(joined.role, 'player');
      assert.equal(joined.code, campaign.code);
      assert.equal(joined.gmKey, null);

      const sheet = JSON.parse(runBundled(node, ['--input-type=module', '-e',
        "import {blank} from './public/tools/rules.js'; process.stdout.write(JSON.stringify({...blank(), name:'Следопыт из браузера'}));"],
        {cwd: path.join(resources, 'game')}));
      // Saving a sheet and deploying it exercise Python -> bundled Node calls.
      const saved = (await request(host, 'api/account/character', {cookie: player.cookie, body: {action: 'save', sheet}})).value;
      const dashboard = (await request(host, 'api/account', {cookie: player.cookie})).value;
      const savedCharacter = dashboard.characters.find(character => character.id === saved.id);
      assert.equal(savedCharacter.sheet.name, sheet.name);
      const deployed = (await request(host, 'api/account/character', {cookie: player.cookie,
        body: {action: 'deploy', id: saved.id, version: savedCharacter.version, code: campaign.code}})).value;
      const inventory = (await request(host, 'api/action', {token: joined.token,
        body: {action: 'inventoryOpen', character: deployed.character}})).value;
      assert.equal(inventory.characters.find(character => character.id === deployed.character).inventoryInitialized, true);
      const masterState = (await request(host, 'api/state', {token: campaign.token})).value;
      assert.equal(masterState.characters.find(character => character.id === deployed.character).name, sheet.name);

      // Use an image fixture and local map assets to verify the portable backup.
      await fsp.mkdir(path.join(host.data, 'map-images'), {recursive: true});
      const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX0kAAAAASUVORK5CYII=', 'base64');
      await fsp.writeFile(path.join(host.data, 'map-images', 'test-map.png'), png);
      await fsp.writeFile(path.join(host.data, 'local-assets', 'forbidden-lands.jpg'), 'private test map');
      await fsp.writeFile(path.join(host.data, 'local-assets', 'forbidden-lands-terrain.json'), '{}');
      await fsp.writeFile(path.join(host.data, 'local-assets', 'unrelated-secret.txt'), 'must not be copied');
      const backup = await host.backup(path.join(folder, 'Резервные копии'));
      const manifest = JSON.parse(await fsp.readFile(path.join(backup, 'COMPLETE.json'), 'utf8'));
      assert.deepEqual(Object.keys(manifest.sha256).sort(), [
        'campaigns.sqlite', 'local-assets/forbidden-lands-terrain.json', 'local-assets/forbidden-lands.jpg', 'map-images/test-map.png',
      ]);
      for (const [name, expected] of Object.entries(manifest.sha256)) {
        assert.equal(crypto.createHash('sha256').update(await fsp.readFile(path.join(backup, name))).digest('hex'), expected, name);
      }
      const integrity = JSON.parse(runBundled(python, ['-I', '-X', 'utf8', '-c',
        "import sqlite3,json,sys; from pathlib import Path; db=sqlite3.connect(Path(sys.argv[1]).resolve().as_uri()+'?mode=ro',uri=True); print(json.dumps({'integrity':db.execute('PRAGMA integrity_check').fetchone()[0],'accounts':db.execute('SELECT COUNT(*) FROM accounts').fetchone()[0],'members':db.execute('SELECT COUNT(*) FROM account_memberships').fetchone()[0]})); db.close()",
        path.join(backup, 'campaigns.sqlite')]));
      assert.deepEqual(integrity, {integrity: 'ok', accounts: 2, members: 2});

      // A failed backup must report an error without killing the game host.
      const invalidOutput = path.join(folder, 'not-a-directory');
      await fsp.writeFile(invalidOutput, 'occupied');
      await assert.rejects(host.backup(invalidOutput));
      assert.equal((await request(host, 'api/health')).value.ok, true);

      await stopAndCheck(host);
      await startWithoutPath(host);
      const persisted = (await request(host, 'api/account', {cookie: player.cookie})).value;
      assert.equal(persisted.campaigns[0].code, campaign.code);
      assert.equal(persisted.characters.find(character => character.id === saved.id).sheet.name, sheet.name);
      const resumed = (await request(host, 'api/account/connect', {cookie: player.cookie, body: {code: campaign.code}})).value;
      assert.equal(resumed.role, 'player');
      const restoredState = (await request(host, 'api/state', {token: resumed.token})).value;
      assert.equal(restoredState.characters.find(character => character.id === deployed.character).inventoryInitialized, true);
      const login = await request(host, 'api/account/login', {body: {login: 'desktop.master', password}});
      const resumedGm = (await request(host, 'api/account/connect', {cookie: login.cookie, body: {code: campaign.code}})).value;
      assert.equal(resumedGm.role, 'gm');
      await stopAndCheck(host);

      // Loading the backup in a separate host verifies that it is usable, not
      // merely a readable SQLite file or a correct manifest.
      const restored = new GameHost({resources, runtime, data: backup, port: 0});
      hosts.push(restored);
      await startWithoutPath(restored);
      const restoredAccount = (await request(restored, 'api/account', {cookie: player.cookie})).value;
      assert.equal(restoredAccount.campaigns[0].code, campaign.code);
      assert.equal(restoredAccount.characters.find(character => character.id === saved.id).sheet.name, sheet.name);
      await stopAndCheck(restored);
      assert.equal(fs.existsSync(path.join(resources, 'game', '__pycache__')), false, 'The installed resources must stay read-only.');
    } finally {
      await host.stop();
      await new Promise(resolve => occupied.close(resolve));
    }
  });

  test('closing launcher stdin without a stop command does not leave an orphan server', {timeout: 60000}, async () => {
    const host = makeHost('Закрытие окна');
    await startWithoutPath(host);
    const child = host.child;
    const url = host.state.localUrl;
    const exited = once(child, 'exit');
    child.stdin.end();
    const timeout = setTimeout(() => child.kill(), 10000);
    try {
      const [code] = await exited;
      assert.equal(code, 0, 'EOF must gracefully close Python before the emergency timeout.');
      await assertProcessStopped(child, url);
      assert.equal(host.child, null);
    } finally {
      clearTimeout(timeout);
      await host.stop();
    }
  });
});
