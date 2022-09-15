'use strict'

const indexLib = require('./index')
const urlsLib = require('./lib/urls')
const resultsWriter = require('./lib/write_results')
const fs = require('fs')

const profile = process.argv[2]
const dy = process.argv[3]
const iteration = process.argv[4]
const seeder_domain = process.argv[5]

const getStartingURLFromFile = _ => {
  const prefix = '/data/test_results/redo_files/'
  const output_files = ['safariProfile1_redo_file.json', 'safariProfile2_redo_file.json', 'chromeProfile_redo_file.json']
  const elements = []
  const element_types = []
  const src_urls = []
  const dst_urls = []
  for (const output_file of output_files) {
    const rawdata = fs.readFileSync(prefix + output_file)
    const data = JSON.parse(rawdata)
    elements.push(data.element_to_click)
    src_urls.push(data.src_url)
    dst_urls.push(data.dst_url)
    element_types.push(data.element_type)
    console.log('Element_type:', data.element_type)
  }

  if (urlsLib.getHost(dst_urls[0]) !== urlsLib.getHost(dst_urls[1]) || urlsLib.getHost(dst_urls[1]) !== urlsLib.getHost(dst_urls[2])) {
    console.log("ERROR: Domains of dst_urls weren't the same! Skipping this crawl!")
    process.exit(4)
  }

  if (profile.includes('safariProfile1')) {
    return dst_urls[0]
  } else if (profile.includes('safariProfile2')) {
    return dst_urls[1]
  } else if (profile.includes('chromeProfile')) {
    return dst_urls[2]
  } else {
    console.log('ERROR: Unrecognized profile', profile, ': skipping this crawl.')
    process.exit(5)
  }
}

indexLib.handler({
  url: getStartingURLFromFile(),
  // chromePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  chromePath: '/usr/bin/google-chrome-stable',
  debug: true,
  seconds: 120,
  profile: profile
}, undefined, state => {
  console.log('test is over')
  const url = seeder_domain
  const folder = '/data/test_results/' + state.getCrawlerName()
  const redoFile = '/data/test_results/redo_files/' + state.getCrawlerName() + '_redo_file.json'
  const cookieFile = folder + '/cookies/' + dy + '_' + url + '_cookies_iter' + iteration + '.csv'
  const storageFile = folder + '/localStorage/' + dy + '_' + url + '_localStorage_iter' + iteration + '.csv'
  const crawlFile = folder + '/crawlEvents/' + dy + '_' + url + '_crawlEvents_iter' + iteration + '.csv'

  resultsWriter.writeCookieResults(state, cookieFile)
  resultsWriter.writeLocalStorage(state, storageFile)
  resultsWriter.writeCrawlEvents(state.getCrawlEvents(), crawlFile)
  resultsWriter.writeInfoForRedoCrawler(state, redoFile)

  const files = [cookieFile, storageFile, crawlFile]
  for (const file of files) {
    try {
      if (fs.existsSync(file)) {
        console.log(file, 'exists.')
      }
    } catch (err) {
      console.log(err)
      console.log('Failed to create', file, 'on crawl for', url)
    }
  }

  console.log(state.element_to_click_type)
  console.log(state.element_to_click)
  console.log(state.src_url)
  console.log(state.dst_url)
  if (state.haveLoadedFirstPage === false) {
    console.log('Crawl failed - domcontentloaded handler never fired.')
    process.exit(2)
  } else if (state.crawlFailed === true) {
    console.log('Crawl failed - manualNavigationAllTypes() failed to click an element and navigate the page.')
    process.exit(3)
  } else if (Object.keys(state.element_to_click).length === 0) {
    console.log('Crawl failed - element_to_click was empty.')
    process.exit(1)
  } else {
    process.exit(0)
  }
})
