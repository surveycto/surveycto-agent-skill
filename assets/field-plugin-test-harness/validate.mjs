#!/usr/bin/env node
/*
 * SurveyCTO field plug-in static validator.
 *
 * Usage:
 *   node validate.mjs <path>          # path = directory OR .fieldplugin.zip
 *   node validate.mjs <path> --json   # machine-friendly JSON output
 *
 * Zero runtime dependencies: Node 18+ stdlib only. For .zip input the script
 * shells out to the system `unzip` binary (read-only `unzip -l` / `unzip -p`).
 *
 * Checks performed:
 *   - All four required files (manifest.json, template.html, style.css,
 *     script.js) exist at the bundle root.
 *   - No subdirectories (warning — they get flattened on upload).
 *   - No duplicate basenames after flattening (error).
 *   - manifest.json parses and contains required keys with valid types.
 *   - manifest.supportedFieldTypes is a non-empty subset of the five allowed
 *     types.
 *   - manifest.version looks like semver (x.y.z, optional pre-release).
 *   - Optional manifest keys (externalCss, externalJs, hideDefault*) have
 *     valid types.
 *   - Each externalCss / externalJs file is present in the bundle.
 *   - script.js defines clearAnswer (warning if not detected — cheap regex,
 *     not a parser).
 *   - Bundle (zip) filename rules: letters/numbers/. -_, starts with a
 *     letter, length <= 100, ends in .fieldplugin.zip.
 *
 * Exit code: 0 on success (warnings allowed), 1 on any error.
 */

import { promises as fs } from 'node:fs';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const REQUIRED_FILES = ['manifest.json', 'template.html', 'style.css', 'script.js'];
const ALLOWED_FIELD_TYPES = ['text', 'integer', 'decimal', 'select_one', 'select_multiple'];
const SEMVER_RE = /^\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$/;
const SAFE_NAME_RE = /^[A-Za-z][A-Za-z0-9._-]*$/;

function makeReport() {
  return { errors: [], warnings: [], info: [] };
}

function err(report, message) { report.errors.push(message); }
function warn(report, message) { report.warnings.push(message); }
function info(report, message) { report.info.push(message); }

// --- Bundle adapters ------------------------------------------------------

/**
 * A "bundle" is an object with:
 *   { kind: 'dir'|'zip', root: string, listFiles(): string[],
 *     readText(name): Promise<string>, hasFile(name): bool,
 *     subdirs: string[], duplicates: string[] }
 *
 * For directories, `listFiles` returns a flat list of file basenames (any
 * file at the root); subdirs are reported separately. For zips, `listFiles`
 * returns the central-directory entries' basenames (after flattening), with
 * subdirs collected for warning.
 */

async function loadDirectoryBundle(dir) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  const subdirs = [];
  for (const e of entries) {
    if (e.isDirectory()) {
      subdirs.push(e.name);
    } else if (e.isFile()) {
      files.push(e.name);
    }
  }
  // Detect duplicates of the basename across any nested files (so that the
  // user sees the same error they'd hit on upload). For directories this
  // also walks one level deeper.
  const allBasenames = [...files];
  async function walk(sub, rel) {
    const subEntries = await fs.readdir(sub, { withFileTypes: true });
    for (const e of subEntries) {
      const full = path.join(sub, e.name);
      if (e.isDirectory()) {
        await walk(full, path.join(rel, e.name));
      } else if (e.isFile()) {
        allBasenames.push(e.name);
      }
    }
  }
  for (const s of subdirs) {
    await walk(path.join(dir, s), s);
  }
  const duplicates = findDuplicates(allBasenames);

  return {
    kind: 'dir',
    root: dir,
    files,
    subdirs,
    duplicates,
    allBasenames,
    hasFile(name) { return files.includes(name); },
    async readText(name) {
      return await fs.readFile(path.join(dir, name), 'utf8');
    },
  };
}

async function loadZipBundle(zipPath) {
  // Use `unzip -l` for the listing and `unzip -p` for individual file reads.
  // Returns nothing if `unzip` isn't installed; we fall back to an explicit
  // error in that case.
  const list = spawnSync('unzip', ['-Z1', zipPath], { encoding: 'utf8' });
  if (list.error || list.status !== 0) {
    throw new Error(
      `Cannot read zip with system 'unzip' (${list.error ? list.error.message : 'exit ' + list.status}). ` +
      `Either install 'unzip' or unpack the zip and pass the directory.`
    );
  }
  const entries = list.stdout.split('\n').map(s => s.trim()).filter(Boolean);
  const files = [];
  const subdirs = new Set();
  const allBasenames = [];
  for (const entry of entries) {
    if (entry.endsWith('/')) {
      // A directory entry. Skip; remember the prefix.
      subdirs.add(entry.replace(/\/$/, '').split('/')[0]);
      continue;
    }
    const parts = entry.split('/');
    const basename = parts[parts.length - 1];
    if (parts.length === 1) {
      files.push(basename);
    } else {
      subdirs.add(parts[0]);
    }
    allBasenames.push(basename);
  }
  const duplicates = findDuplicates(allBasenames);

  return {
    kind: 'zip',
    root: zipPath,
    files,
    subdirs: [...subdirs],
    duplicates,
    allBasenames,
    hasFile(name) { return files.includes(name); },
    async readText(name) {
      const r = spawnSync('unzip', ['-p', zipPath, name], { encoding: 'utf8' });
      if (r.error || r.status !== 0) {
        throw new Error(`Failed to read ${name} from ${zipPath}`);
      }
      return r.stdout;
    },
  };
}

function findDuplicates(arr) {
  const seen = new Map();
  for (const x of arr) seen.set(x, (seen.get(x) || 0) + 1);
  return [...seen.entries()].filter(([, n]) => n > 1).map(([k]) => k);
}

// --- Validators -----------------------------------------------------------

function validateZipFilename(zipPath, report) {
  // Per the upstream developer docs, field plug-in filename rules apply to
  // the full filename (including the .fieldplugin.zip suffix): only letters,
  // numbers, '.', '-', '_'; must start with a letter; must not exceed 100
  // characters. Matching is case-insensitive at upload time.
  const base = path.basename(zipPath);
  if (!base.toLowerCase().endsWith('.fieldplugin.zip')) {
    warn(report, `Zip name '${base}' does not end in '.fieldplugin.zip' — required when uploading.`);
    return;
  }
  const stem = base.slice(0, -'.fieldplugin.zip'.length);
  if (stem.length === 0) err(report, `Zip name has no plug-in name before '.fieldplugin.zip'.`);
  if (base.length > 100) err(report, `Field plug-in filename '${base}' is ${base.length} characters; must not exceed 100.`);
  if (!SAFE_NAME_RE.test(base)) {
    err(report, `Field plug-in filename '${base}' must start with a letter and contain only letters, numbers, '.', '-', or '_'.`);
  }
}

async function validateBundle(bundle, report) {
  for (const f of REQUIRED_FILES) {
    if (!bundle.hasFile(f)) err(report, `Missing required file: ${f}`);
  }
  if (bundle.subdirs.length > 0) {
    warn(report, `Bundle contains subdirectories (${bundle.subdirs.join(', ')}). They will be flattened on upload — keep all files at the root.`);
  }
  if (bundle.duplicates.length > 0) {
    err(report, `Duplicate filenames after flattening: ${bundle.duplicates.join(', ')}. Uploads with duplicate basenames are rejected.`);
  }

  // Per the developer docs, every inner file's basename must contain only
  // letters, numbers, '.', '-', '_', start with a letter, and be ≤ 100 chars.
  // The four required files already satisfy these rules; check everything
  // else (root files plus anything nested under flattened subdirs).
  const seenInner = new Set();
  for (const name of bundle.allBasenames || bundle.files) {
    if (seenInner.has(name)) continue;
    seenInner.add(name);
    if (REQUIRED_FILES.includes(name)) continue;
    if (name.length > 100) {
      err(report, `Inner file '${name}' is ${name.length} characters; must not exceed 100.`);
    }
    if (!SAFE_NAME_RE.test(name)) {
      err(report, `Inner file '${name}' must start with a letter and contain only letters, numbers, '.', '-', or '_'.`);
    }
  }

  // Manifest
  if (!bundle.hasFile('manifest.json')) return;
  let manifest;
  try {
    const raw = await bundle.readText('manifest.json');
    manifest = JSON.parse(raw);
  } catch (e) {
    err(report, `manifest.json failed to parse: ${e.message}`);
    return;
  }
  validateManifest(manifest, bundle, report);

  // script.js sanity
  if (bundle.hasFile('script.js')) {
    let js = '';
    try { js = await bundle.readText('script.js'); } catch { /* unreadable */ }
    if (!/(^|\W)function\s+clearAnswer\s*\(/.test(js) && !/clearAnswer\s*=\s*function/.test(js) && !/clearAnswer\s*=\s*\(/.test(js)) {
      warn(report, `Could not detect a global clearAnswer() in script.js. clearAnswer is required by the field plug-in API.`);
    }
    if (!/setAnswer\s*\(/.test(js)) {
      warn(report, `Could not find any setAnswer(...) call in script.js. The plug-in must report answers via setAnswer.`);
    }
  }
}

function validateManifest(m, bundle, report) {
  if (typeof m !== 'object' || m === null || Array.isArray(m)) {
    err(report, `manifest.json must be a JSON object.`);
    return;
  }
  for (const key of ['name', 'author', 'version']) {
    if (typeof m[key] !== 'string' || m[key].length === 0) {
      err(report, `manifest.${key} is required and must be a non-empty string.`);
    }
  }
  if (typeof m.version === 'string' && !SEMVER_RE.test(m.version)) {
    warn(report, `manifest.version '${m.version}' does not look like semver (x.y.z[-prerelease]).`);
  }

  if (!Array.isArray(m.supportedFieldTypes) || m.supportedFieldTypes.length === 0) {
    err(report, `manifest.supportedFieldTypes is required and must be a non-empty array.`);
  } else {
    for (const t of m.supportedFieldTypes) {
      if (typeof t !== 'string' || !ALLOWED_FIELD_TYPES.includes(t)) {
        err(report, `manifest.supportedFieldTypes contains '${t}'. Allowed: ${ALLOWED_FIELD_TYPES.join(', ')}.`);
      }
    }
  }

  for (const arrKey of ['externalCss', 'externalJs']) {
    if (m[arrKey] === undefined) continue;
    if (!Array.isArray(m[arrKey])) {
      err(report, `manifest.${arrKey} must be an array of filenames.`);
      continue;
    }
    for (const f of m[arrKey]) {
      if (typeof f !== 'string' || f.length === 0) {
        err(report, `manifest.${arrKey} contains a non-string entry.`);
        continue;
      }
      if (!bundle.hasFile(f)) {
        err(report, `manifest.${arrKey} references '${f}' but the file is not in the bundle.`);
      }
    }
  }

  for (const boolKey of ['hideDefaultRequiredMessage', 'hideDefaultConstraintMessage']) {
    if (m[boolKey] !== undefined && typeof m[boolKey] !== 'boolean') {
      err(report, `manifest.${boolKey} must be a boolean.`);
    }
  }
}

// --- CLI ------------------------------------------------------------------

function parseArgs(argv) {
  const args = { path: null, json: false };
  for (const a of argv) {
    if (a === '--json') args.json = true;
    else if (a === '--help' || a === '-h') args.help = true;
    else if (!args.path) args.path = a;
  }
  return args;
}

function printHelp() {
  const text = `Usage: node validate.mjs <path> [--json]

  <path>   A field plug-in directory or a .fieldplugin.zip file.
  --json   Emit a JSON report (errors, warnings, info, ok).

Exit code is 0 on success (warnings allowed) and 1 on any error.`;
  process.stdout.write(text + '\n');
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || !args.path) {
    printHelp();
    process.exit(args.path ? 0 : 1);
  }
  const target = path.resolve(args.path);
  if (!existsSync(target)) {
    process.stderr.write(`Path not found: ${target}\n`);
    process.exit(1);
  }

  const report = makeReport();
  let bundle;
  try {
    const stat = await fs.stat(target);
    if (stat.isDirectory()) {
      bundle = await loadDirectoryBundle(target);
    } else if (stat.isFile() && target.toLowerCase().endsWith('.zip')) {
      validateZipFilename(target, report);
      bundle = await loadZipBundle(target);
    } else {
      err(report, `Path is neither a directory nor a .zip file: ${target}`);
    }
    if (bundle) await validateBundle(bundle, report);
  } catch (e) {
    err(report, e.message || String(e));
  }

  const ok = report.errors.length === 0;

  if (args.json) {
    process.stdout.write(JSON.stringify({
      ok,
      path: target,
      errors: report.errors,
      warnings: report.warnings,
      info: report.info,
    }, null, 2) + '\n');
  } else {
    if (report.errors.length) {
      process.stdout.write(`Errors:\n`);
      for (const m of report.errors) process.stdout.write(`  - ${m}\n`);
    }
    if (report.warnings.length) {
      process.stdout.write(`Warnings:\n`);
      for (const m of report.warnings) process.stdout.write(`  - ${m}\n`);
    }
    if (report.info.length) {
      process.stdout.write(`Info:\n`);
      for (const m of report.info) process.stdout.write(`  - ${m}\n`);
    }
    process.stdout.write(ok ? `OK: ${target}\n` : `FAIL: ${target}\n`);
  }
  process.exit(ok ? 0 : 1);
}

main();
