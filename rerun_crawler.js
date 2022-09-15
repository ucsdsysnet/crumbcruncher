'use strict'

// const puppeteer = require("puppeteer-extra");
// // add stealth plugin and use defaults (all evasion techniques)
// const StealthPlugin = require('puppeteer-extra-plugin-stealth');
// puppeteer.use(StealthPlugin());
const puppeteer = require('puppeteer')

const urlsLib = require('./lib/urls')
const stateLib = require('./lib/state')
const navigationLib = require('./lib/navigate')
const crawlLib = require('./lib/crawl')
const controllerClientLib = require('./lib/controller_client')
const resultsWriter = require('./lib/write_results')
const fs = require('fs')

const delay = ms => new Promise(res => setTimeout(res, ms))

const instrumentPage = async (page, state, logger, closedCallback) => {
  const width = 1280
  const height = 2048

  logger(`${state.pageDesc(page)} (re)setting page instrumentation`)
  // !state.cancelTimeoutForPage(page);
  page.setDefaultNavigationTimeout(0)
  page.setViewport({ height, width })
  page.setRequestInterception(true)
  // page.on('console', consoleObj => console.log(consoleObj.text()));

  page.on('domcontentloaded', async _ => {
    logger(`${state.pageDesc(page)} domcontent loaded`)
    state.haveLoadedFirstPage = true
    await delay(10) // Cede execution to hopefully give the iframe clicking code time to finish?

    try {
      await page.evaluate(_ => {
        window.addEventListener('beforeunload', async _ => {
          console.log('before unload', window.location.href)
          try {
            await crawlLib.updateStorage(page, state, logger, 'beforeunload')
          } catch (err) {
            logger(`${state.pageDesc(page)} Error in updateStorage: ${err.stack}`)
          }
        })
      })
    } catch (err) {
      logger(`${state.pageDesc(page)}: ${err}`)
      logger(`${state.pageDesc(page)}: Error while adding beforeunload listener, returning from domcontentloaded handler.`)
      return
    }

    try {
      await crawlLib.updateStorage(page, state, logger, 'domcontentloaded')
    } catch (err) {
      logger(`${state.pageDesc(page)} Error in updateStorage: ${err.stack}`)
    }
  })

  page.on('request', async (request) => {
    const frame = request.frame()
    if (!frame) {
      request.continue()
      return
    }

    if (urlsLib.isHttpUrl(request.url()) === false) {
      // logger(`${state.frameDesc(frame)}Canceling non-HTTP request to ${request.url()}`);
      request.abort()
      return
    }

    // We can speed things up by just not downloading
    // things that affect the presentation of the page
    // in a way we don't care about.
    const resourceTypesToIgnore = new Set([
      'font'
    ])
    if (resourceTypesToIgnore.has(request.resourceType())) {
      request.abort()
      return
    }

    const frameId = state.idForFrame(frame)
    if (request.resourceType() !== 'document') { // This is how you check if the URL of any frame has changed. If the request WAS for a document, and the state doesn't say we tried to manually navigate, then a redirect occurred
      state.pushRequest(request, frameId, false, '', '', frame, page)
      request.continue()
      return
    }

    const request_domain = urlsLib.getDomain(request.url())
    state.setDomainForFrame(frame, urlsLib.getHost(request.url()))
    const crawlEvents = state.getCrawlEvents()
    let redirectDomain
    let isRedirect = false
    let queryParams = ''
    const numEvents = crawlEvents.length
    if (numEvents > 0) {
      const topCrawlEvent = crawlEvents[crawlEvents.length - 1]
      // Check if this request has any query parameters
      const split = request.url().split('?')
      if (split.length > 1) {
        queryParams = split[1]
      }

      // Is this request part of a redirect chain? THIS CODE PROBABLY WRONG
      const redirectChain = []
      for (let backwards_idx = 1; backwards_idx === crawlEvents.length; backwards_idx++) {
        const crawlEvent = crawlEvents[crawlEvents.length - backwards_idx]
        if ((crawlEvent.type === 'navigation' || crawlEvent.isRedirect) && crawlEvent.frameId === frameId) {
          redirectChain.push(crawlEvent)
        } else {
          break
        }
      }

      if (redirectChain.length > 0) {
        if (urlsLib.getDomain(topCrawlEvent.url) === request_domain) {
          redirectDomain = 'same'
        } else {
          redirectDomain = 'different'
        }
        isRedirect = true
      }
    }

    state.pushRequest(request, frameId, isRedirect, redirectDomain, queryParams, frame, page)
    request.continue()
  })

  page.on('response', response => {
    const responseUrl = response.url()
    let currentEvent
    let idx = 0
    for (const event of state.getCrawlEvents()) {
      if (event.url === responseUrl) {
        currentEvent = event
        break
      }
      idx += 1
    }
    if (currentEvent === undefined) {
      return
    }
    if (currentEvent.resourceType !== 'document' && currentEvent.resourceType !== 'other') {
      return
    }
    if ('set-cookie' in response.headers()) {
      const cookies = response.headers()['set-cookie'].replaceAll('\n', '|')
      state.getCrawlEvents()[idx].cookie = cookies
    }
    if ('location' in response.headers()) {
      state.getCrawlEvents()[idx].redirectTo = response.headers().location
    }
  })
}

const findElementToClick = async (page, state, logger, element, element_type) => {
  const scroll_success = await navigationLib.autoScroll(page, logger)
  if (!scroll_success) {
    logger(`${state.pageDesc(page)} Failed to scroll page, but searching for elements anyways.`)
  }

  // Returned dict is split by sameDomain, diffDomain
  let elements
  if (element_type === 'ANCHOR') {
    elements = await navigationLib.collectAnchors(page, state, logger)
  } else if (element_type === 'IFRAME') {
    elements = await navigationLib.collectIframes(page, state, logger, false)
  } else {
    logger(`${state.pageDesc(page)} ERROR: element_type was not IFRAME or ANCHOR, it was ${element_type}`)
    return false
  }

  for (const origin_type of ['sameDomain', 'diffDomain']) {
      let num_elements = 0
    for (const tmp_element of elements[origin_type]) {
      const tmp_element_json = await controllerClientLib.elementToJson(page, tmp_element, num_elements<20)
      if (controllerClientLib.isSameElement(element, tmp_element_json)) {
        return tmp_element
      }
      num_elements ++
    }
  }

  logger(`${state.pageDesc(page)} Did not find element to click.`)
  return false
}

const niceClose = async (browser, logger, state, cb, redirect_chain_id, seeder_domain) => {
  logger('attempting to shut down nicely')
  state.close()
  const pages = await browser.pages()
  for (const page of pages) {
    await page.removeAllListeners()
  }
  await delay(1000)

  logger('Master cookie list:')
  for (const key of Object.keys(state.masterCookieList)) {
    logger(`    ${key}: ${state.masterCookieList[key].length}`)
  }
  logger('Master storage:')
  for (const key of Object.keys(state.masterLocalStorage)) {
    logger(`    ${key}: ${Object.keys(state.masterLocalStorage[key]).length}`)
  }

  for (const page of pages) {
    await page.close({ runBeforeUnload: true })
  }

  await browser.close()
  logger('Browser is closed.')
  // Callback has to be last because it calls process.exit()
  await cb(state, redirect_chain_id, seeder_domain)
}

const redoCrawl = async (crawlArgs, cb) => {
  const logger = crawlArgs.debug ? console.dir : _ => {}

  const state = stateLib.createState()
  const puppeteerOptions = {
    userDataDir: crawlArgs.profile,
    args: [
        `--disable-extensions-except=/home/ec2-user/brave-redirection-recorder/extensions/safariProfile1`,
        `--load-extension=/home/ec2-user/brave-redirection-recorder/extensions/safariProfile1`,
        `--enable-automation`,
    ],
  }
  if (crawlArgs.chromePath) {
    puppeteerOptions.executablePath = crawlArgs.chromePath
  }

  if (crawlArgs.debug === true) {
    puppeteerOptions.headless = false
  }
  // Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15
  const browser = await puppeteer.launch(puppeteerOptions).catch(err => console.log(err))
  const mainPage = (await browser.pages())[0]
  if (crawlArgs.profile.includes('safariProfile')) {
    mainPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15')
  } else if (crawlArgs.profile.includes('chromeProfile')) {
    mainPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36')
  } else {
    logger(`${state.pageDesc(mainPage)} ERROR: UA not set in crawl(), crawler name was ${state.getCrawlerName()}`)
  }

  // Check if settings have been erased
  // await mainPage.goto("chrome://settings/cookies?search=cookies");
  // await mainPage.screenshot({path: 'safariProfile1Copy.jpg'});
  const { cookies } = await mainPage._client.send('Network.getAllCookies')
  // console.log('Cookies before anything happens:', cookies)

  browser.on('targetcreated', async target => {
    const newPage = await target.page()
    if (newPage === null) {
      return
    }
    if (state.haveLoadedFirstPage === false) {
      return
    }
    state.setIsInNewTabPhase(true)

    logger(` - New tab opened for ${target.url()}`)
    logger(` - Switching to new tab  with URL=${target.url()}`)
    state.commitNavigationAttempt()
    if (crawlArgs.profile.includes('safariProfile')) {
      mainPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15')
    } else if (crawlArgs.profile.includes('chromeProfile')) {
      mainPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36')
    } else {
      logger(`${state.pageDesc(mainPage)} ERROR: UA not set in new tab handler, crawler name was ${state.getCrawlerName()}`)
    }

    // Add a beforeunload listener to the new page
    try {
      await newPage.evaluate(_ => {
        window.addEventListener('beforeunload', async _ => {
          console.log('before unload', window.location.href)
          try {
            await crawlLib.updateStorage(newPage, state, logger, 'beforeunload')
          } catch (err) {
            logger(`${state.pageDesc(newPage)} Error in updateStorage: ${err.stack}`)
          }
        })
      })
      logger(`${state.pageDesc(newPage)} beforeunload listener added`)
    } catch (err) {
      logger(`${state.pageDesc(newPage)} ${err}`)
      logger(`${state.pageDesc(newPage)} Error while adding beforeunload listener, retrying once:`)
      try {
        await newPage.evaluate(_ => {
          window.addEventListener('beforeunload', async _ => {
            console.log('before unload', window.location.href)
            try {
              await crawlLib.updateStorage(newPage, state, logger, 'beforeunload')
            } catch (err) {
              logger(`${state.pageDesc(newPage)} Error in updateStorage: ${err.stack}`)
            }
          })
        })
        logger(`${state.pageDesc(newPage)} beforeunload listener added`)
      } catch (err) {
        logger(`${state.pageDesc(newPage)} ${err}`)
        logger('Error while adding beforeunload listener a second time, returning from targetcreated handler.')
        return
      }
    }

    // Don't close the original main tab yet because it might still be in use in manualNavigation or manualIframeNavigation, waiting to see if its url has changed.
    // Removing its listeners is enough to ensure that after all its functions finish their current rounds of execution, no more will start.
    try {
      const tmp_pages = await browser.pages()
      for (const tmp_page of tmp_pages) {
        if (tmp_page !== newPage) {
          await tmp_page.removeAllListeners()
        }
      }
    } catch (err) {
      logger(`${err}\nError while removing listeners from mainPage, returning from targetcreated handler.`)
      return
    }

    try {
      await instrumentPage(newPage, state, logger, cb)
    } catch (err) {
      logger(`${state.pageDesc(mainPage)} Error in instrumentPage, called from new tab handler: \n${err}`)
    }
  })

  state.setGlobalTimeout(async _ => {
    logger('Global crawling time limit hit.')
    const pages = await browser.pages()
    state.dst_url = await pages[pages.length - 1].url()
    await niceClose(browser, logger, state, cb, crawlArgs.redirect_chain_id, crawlArgs.seeder_domain)
  }, crawlArgs.seconds)

  state.setMainFrameId(state.idForFrame(mainPage.mainFrame()))

  try {
    console.log('About to set up page')
    await instrumentPage(mainPage, state, logger, cb)
  } catch (err) {
    logger(`${state.pageDesc(mainPage)} ${err}`)
    return
  }
  // Navigate to start_url and look for the first url in crawlArgs.document_request_urls
  if (!await crawlLib.navigateToUrl(mainPage, crawlArgs.start_url, state, logger)) {
    logger(`Failed to navigate to starting URL: ${crawlArgs.start_url}`)
    try {
      const line = JSON.stringify(crawlArgs)
      fs.writeFileSync('/data/test_failed_navigating_start_url.txt', line + '\n', { flag: 'a+' })
    } catch (err) {
      console.log(err)
    }
    await niceClose(browser, logger, state, cb, crawlArgs.redirect_chain_id, crawlArgs.seeder_domain)
  }

  await delay(5000)

  const ele_to_click = await findElementToClick(mainPage, state, logger, crawlArgs.element_to_click, crawlArgs.element_type)
  if (!ele_to_click) {
    logger('Failed to find element to click.')
    try {
      const line = JSON.stringify(crawlArgs)
      fs.writeFileSync('/data/test_failed_finding_element_to_click.txt', line + '\n', { flag: 'a+' })
    } catch (err) {
      console.log(err)
    }
    await niceClose(browser, logger, state, cb, crawlArgs.redirect_chain_id, crawlArgs.seeder_domain)
  }

  if (crawlArgs.element_type === 'ANCHOR') {
    const click_succeeded = await navigationLib.clickAnchor(ele_to_click, mainPage, state, logger)
    if (!click_succeeded) {
      logger('Anchor click failed to navigate page.')
    }
  } else if (crawlArgs.element_type === 'IFRAME') {
    const click_succeeded = await navigationLib.clickIframe(ele_to_click, mainPage, state, logger)
    if (!click_succeeded) {
      logger('Iframe click failed to navigate page.')
    }
  }
  await delay(5000)
  await niceClose(browser, logger, state, cb, crawlArgs.redirect_chain_id, crawlArgs.seeder_domain)
}

const setUpAndRun = async (seeder_domain, start_url, element_to_click, element_type, profile, iteration, ds) => {
  const crawlArgs = {
    seeder_domain: seeder_domain,
    element_to_click: element_to_click,
    element_type: element_type,
    start_url: start_url,
    seconds: 120,
    debug: true,
    profile: profile,
    chromePath: '/usr/bin/google-chrome-stable'
  }

  const logger = crawlArgs.debug === true ? console.dir : _ => { }

  logger('Beginning "redo" crawl with following settings:')
  logger(crawlArgs)

  const onCrawlComplete = (state, redirect_chain_id, seeder_domain) => {
    console.log('Redo is over')

    const folder = '/data/test_results/safariProfile1Copy'
    // TODO: Change the file names so they match the format of the original crawls otherwise they don't get parsed properly
    const cookieFile = folder + '/cookies/' + ds + '_' + seeder_domain + '_cookies_iter' + iteration + '.csv'
    const storageFile = folder + '/localStorage/' + ds + '_' + seeder_domain + '_localStorage_iter' + iteration + '.csv'
    const crawlFile = folder + '/crawlEvents/' + ds + '_' + seeder_domain + '_crawlEvents_iter' + iteration + '.csv'
    console.log('Cookie file:', cookieFile)
    console.log('Storage file:', storageFile)
    console.log('Crawl events file:', crawlFile)

    resultsWriter.writeCookieResults(state, cookieFile)
    resultsWriter.writeLocalStorage(state, storageFile)
    resultsWriter.writeCrawlEvents(state.getCrawlEvents(), crawlFile)

    process.exit(0)
  }

  redoCrawl(crawlArgs, onCrawlComplete) // .catch();
}

const main = _ => {
  const seeder_domain = process.argv[2]
  const ds = process.argv[3]
  const iteration = process.argv[4]
  console.log('Seeder domain:', seeder_domain, 'DS:', ds, 'iteration:', iteration)
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

  if (!controllerClientLib.isSameElement(elements[0], elements[1]) || !controllerClientLib.isSameElement(elements[1], elements[2])) {
    console.log("ERROR: Elements stored by output files weren't the same! Skipping this redo!")
    process.exit(4)
  }

  if (urlsLib.getHost(src_urls[0]) !== urlsLib.getHost(src_urls[1]) || urlsLib.getHost(src_urls[1]) !== urlsLib.getHost(src_urls[2])) {
    console.log("ERROR: Domains of src_urls weren't the same! Skipping this redo!")
    process.exit(4)
  }

  const profile = '/data/profiles/safariProfile1'
  setUpAndRun(seeder_domain, src_urls[0], elements[0], element_types[0], profile, iteration, ds)
}

// const element_to_click = {
//   class: ' MV3Tnb',
//   href: ' https://about.google/?fg=1&utm_source=google-US&utm_medium=referral&utm_campaign=hp-header',
//   onmousedown: " return rwt(this,'','','','','AOvVaw13L0SpN0L7ycx9R0_i4R2S','','0ahUKEwjVxf384I70AhXIRfEDHSTUAgcQkNQCCAI','','',event)",
//   x: 21,
//   y: 17,
//   width: 46.59375,
//   height: 26
// }

// const element_type = 'ANCHOR'
// const start_url = 'https://google.com'
// const profile = '/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/testProfileCookiesDisabled'
// setUpAndRun('google.com', start_url, element_to_click, element_type, profile, process.argv[2], process.argv[3]);
main()
