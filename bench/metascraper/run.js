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
  require('metascraper-date')()
])

async function main (pagesPath, outPath, modules) {
  const root = path.dirname(pagesPath)
  const pages = JSON.parse(fs.readFileSync(pagesPath, 'utf8'))
  const results = []
  let seconds = 0
  for (const page of pages) {
    const html = zlib.gunzipSync(fs.readFileSync(path.join(root, page.path))).toString('utf8')
    const started = process.hrtime.bigint()
    let found = {}
    try {
      found = await metascraper({ html, url: page.url || 'http://example.com/' })
    } catch (error) {
      found = {}
    }
    seconds += Number(process.hrtime.bigint() - started) / 1e9
    results.push({
      id: page.id,
      title: found.title || null,
      author: found.author || null,
      date: found.date || null
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

main(process.argv[2], process.argv[3], process.env.NODE_PATH)
