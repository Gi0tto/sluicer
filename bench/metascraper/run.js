// metascraper's title, author and date rules over the test split.
// Run by bench/run.py with the packages from this directory's lockfile,
// installed by `npm ci` into bench/cache/. Only the metascraper call is timed.
'use strict'

const fs = require('fs')
const path = require('path')
const zlib = require('zlib')

const metascraper = require('metascraper')([
  require('metascraper-title')(),
  require('metascraper-author')(),
  // datePublished asks for the publication date's own rules. Without it,
  // metascraper's date puts dateModified first, and a publication date scored
  // against a modified one counted metascraper wrong for how it was called.
  require('metascraper-date')({ datePublished: true })
])

// The call a scoreboard scores and bench/timing.py times.
async function extract (html, url) {
  try {
    return await metascraper({ html, url: url || 'http://example.com/' })
  } catch (error) {
    return {}
  }
}

async function main (pagesPath, outPath, modules) {
  const root = path.dirname(pagesPath)
  const pages = JSON.parse(fs.readFileSync(pagesPath, 'utf8'))
  const results = []
  let seconds = 0
  for (const page of pages) {
    const html = zlib.gunzipSync(fs.readFileSync(path.join(root, page.path))).toString('utf8')
    const started = process.hrtime.bigint()
    const found = await extract(html, page.url)
    seconds += Number(process.hrtime.bigint() - started) / 1e9
    results.push({
      id: page.id,
      title: found.title || null,
      author: found.author || null,
      // Its publication date, and its general date where it finds none.
      date: found.datePublished || found.date || null
    })
  }
  const version = require('metascraper/package.json').version
  fs.writeFileSync(outPath, JSON.stringify({
    tool: 'metascraper',
    version,
    seconds,
    packages: countPackages(modules),
    results
  }))
  console.log(`metascraper ${version}: ${results.length} pages, ${seconds.toFixed(2)} s`)
}

// Every installed package, nested ones included: one package.json per package.
function countPackages (modules) {
  let count = 0
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (!entry.isDirectory() || entry.name.startsWith('.')) continue
      const full = path.join(dir, entry.name)
      if (entry.name.startsWith('@')) {
        walk(full)
        continue
      }
      if (fs.existsSync(path.join(full, 'package.json'))) count += 1
      const nested = path.join(full, 'node_modules')
      if (fs.existsSync(nested)) walk(nested)
    }
  }
  walk(modules)
  return count
}

// Every file under the installed packages, in bytes.
function installBytes (dir) {
  let total = 0
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) total += installBytes(full)
    else if (entry.isFile()) total += fs.statSync(full).size
  }
  return total
}

// bench/timing.py's pass: every page read once untimed, then one timed pass
// of the extraction call alone, reported on the last line as JSON.
async function timing (pagesPath, modules) {
  const root = path.dirname(pagesPath)
  const pages = JSON.parse(fs.readFileSync(pagesPath, 'utf8')).map((page) => ({
    html: zlib.gunzipSync(fs.readFileSync(path.join(root, page.path))).toString('utf8'),
    url: page.url
  }))
  for (const page of pages) await extract(page.html, page.url)
  let seconds = 0
  for (const page of pages) {
    const started = process.hrtime.bigint()
    await extract(page.html, page.url)
    seconds += Number(process.hrtime.bigint() - started) / 1e9
  }
  console.log(JSON.stringify({
    tool: 'metascraper',
    version: require('metascraper/package.json').version,
    runtime: `Node ${process.version.replace(/^v/, '')}`,
    seconds,
    // maxRSS is in kilobytes.
    peak_rss: process.resourceUsage().maxRSS * 1024,
    packages: countPackages(modules),
    install_bytes: installBytes(modules)
  }))
}

if (process.argv[2] === '--timing') {
  timing(process.argv[3], process.env.NODE_PATH)
} else {
  main(process.argv[2], process.argv[3], process.env.NODE_PATH)
}
