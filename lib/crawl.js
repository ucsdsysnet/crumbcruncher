'use strict'

// const puppeteer = require("puppeteer-extra");
// // add stealth plugin and use defaults (all evasion techniques)
// const StealthPlugin = require('puppeteer-extra-plugin-stealth');
// puppeteer.use(StealthPlugin());
const puppeteer = require('puppeteer')

const urlsLib = require('./urls')
const stateLib = require('./state')
const cookieLib = require('./cookies')
const navigationLib = require('./navigate')

const delay = ms => new Promise(res => setTimeout(res, ms))

const domContentLoadedListener = async (page, state, logger, closedCallback) => {
  logger(`${state.pageDesc(page)} domcontent loaded`)
  state.haveLoadedFirstPage = true
  await delay(10) // Cede execution for 10ms to hopefully give the iframe clicking code time to finish?

  try {
    await page.evaluate(_ => {
      window.addEventListener('beforeunload', async _ => {
        console.log('before unload', window.location.href)
        try {
          await updateStorage(page, state, logger, 'beforeunload')
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
    await updateStorage(page, state, logger, 'domcontentloaded')
  } catch (err) {
    logger(`${state.pageDesc(page)} Error in updateStorage: ${err.stack}`)
  }
  try {
    await onLoad(page, state, logger, closedCallback)
  } catch (err) {
    logger(`${err}\nError while running onLoad, returning from domcontentloaded handler.`)
  }
}

const requestListener = (page, state, logger, request) => {
    //console.log('Request handler', request.resourceType(), request.url())
    // if (request.resourceType() === 'document') {
    //     console.log('     Document request for', request.url())
    // }
  const frame = request.frame()
  if (!frame) {
    logger(`${state.pageDesc(page)} WARNING: ${request.resourceType()} request for ${request.url()} will not be recorded because its frame was not found.`)
    request.continue()
    return
  }

  if (urlsLib.isHttpUrl(request.url()) === false) {
    // lslogger(`${state.frameDesc(frame)} WARNING: Canceling non-HTTP request to ${request.url()}`);
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
    // logger(`${state.frameDesc(frame)} WARNING: Canceling font request to ${request.url()}`);
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
}

const responseListener = (page, state, logger, response) => {
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
}

const navigateToUrl = async (page, url, state, logger) => {
  const frameId = state.idForFrame(page.mainFrame())
  try {
    state.pushNavigation({
      url: url,
      frameId: frameId,
      frame: page.mainFrame()
    }, page)
    await page.goto(url)
    return true
  } catch (err) {
    logger(`Error in navigateToUrl:\n ${err}`)
    return false
  }
}

const onLoad = async (page, state, logger, closedCallback) => {
  state.addVisitedDomain(page.url())
  console.log('Sites visited:', state.sitesVisited())
  if (state.sitesVisited() >= 2) {
    logger('Visited the requisite number of sites')
    state.dst_url = await page.url()
    await niceClose(page.browser(), logger, state, closedCallback)
    return
  }
  const navigated = await navigationLib.manualNavigationAllTypes(page, state, logger)
  if (!navigated && !state.isClosed) {
    logger(`${state.pageDesc(page)} Failed manualNavigationAllTypes.`)
    state.dst_url = await page.url()
    state.crawlFailed = true
    await niceClose(page.browser(), logger, state, closedCallback)
  }
}

const updateStorage = async (page, state, logger, handler) => {
  const d = new Date()
  const time = d.getTime()
  const currentCookieList = await cookieLib.listCookies(page, time, state)
  const newCookies = cookieLib.findNewCookies(state.masterCookieList, currentCookieList)
  if (newCookies.length > 0) {
    logger(`${state.pageDesc(page)} Cookies: Found ${newCookies.length} new cookies.`)
  }
  state.masterCookieList = cookieLib.updateMasterCookieList(state.masterCookieList, currentCookieList)
  // console.log(state.masterCookieList)

  const currentLocalStorage = await cookieLib.listLocalStorage(page, time, state)
  state.masterLocalStorage = cookieLib.updateMasterLocalStorage(state.masterLocalStorage, currentLocalStorage)
  for (const key of Object.keys(currentLocalStorage)) {
    logger(`${state.pageDesc(page)} Local storage: Found ${Object.keys(currentLocalStorage[key]).length} new local storage objects for ${key}.`)
  }
}

const instrumentPage = async (page, state, logger, closedCallback) => {
  const width = 1280
  const height = 2048

  logger(`${state.pageDesc(page)} (re)setting page instrumentation`)
  // !state.cancelTimeoutForPage(page);
  await page.setDefaultNavigationTimeout(0)
  await page.setViewport({ height, width })
  await page.setRequestInterception(true)
  // page.on('console', consoleObj => console.log(consoleObj.text()));

  try {
    await page.on('domcontentloaded', domContentLoadedListener.bind(null, page, state, logger, closedCallback))
  } catch (err) {
    logger(`${state.pageDesc(page)} Error adding domcontentloaded handler: ${err}`)
  }

  try {
    await page.on('request', requestListener.bind(null, page, state, logger))
  } catch (err) {
    logger(`${state.pageDesc(page)} Error adding request handler: ${err}`)
  }

  try {
    await page.on('response', responseListener.bind(null, page, state, logger))
  } catch (err) {
    logger(`${state.pageDesc(page)} Error adding domcontentloaded handler: ${err}`)
  }
}

const niceClose = async (browser, logger, state, cb) => {
    if (state.isClosed) {
        logger(`${new Date()}: niceClose called when state was already closed, returning.`)
        return
    }
    logger(`${new Date()}: Attempting to shut down nicely`)
    // Wait ten seconds for extension to send all requests)
    logger(`${new Date()}: Waiting ten seconds for extension to send requests to recording server...`)
    await delay(10000);
    logger(`${new Date()}: Done waiting for extension.`)
    state.close()

    let pages;
    try {
        pages = await browser.pages()
    } catch (err) {
        logger(`${new Date()}: ERROR: Failed to get page list in niceClose: ${err}`)
    }

    logger('Master cookie list:')
    for (const key of Object.keys(state.masterCookieList)) {
        logger(`    ${key}: ${state.masterCookieList[key].length}`)
    }
    logger('Master storage:')
    for (const key of Object.keys(state.masterLocalStorage)) {
        logger(`    ${key}: ${Object.keys(state.masterLocalStorage[key]).length}`)
    }

    try {
        if (pages !== undefined) {
            for (const page of pages) {
                await page.close({ runBeforeUnload: true })
            }
        }
        await browser.close()
        logger('Browser is closed.')
    } catch (err) {
        logger(`${new Date()}: ERROR: Failed to close pages or browser in niceClose: ${err}`)
    }
    // Callback needs to be last because it calls process.exit()
    await cb(state)
}

const crawl = async (crawlArgs, cb) => {
  const logger = crawlArgs.debug ? console.dir : _ => {}
  const state = stateLib.createState(crawlArgs.profile)
  const puppeteerOptions = {
    // userDataDir: '/Users/audrey/Library/Application Support/Google/Chrome/TmpProfileCookiesDisabled',
    // userDataDir: '/home/ec2-user/.config/google-chrome/thirdPartyCookiesDisabled/tmpProfileCookiesDisabled',
    userDataDir: crawlArgs.profile,
    args: [
        `--disable-extensions-except=/home/ec2-user/brave-redirection-recorder/extensions/${state.getCrawlerName()}`,
        `--load-extension=/home/ec2-user/brave-redirection-recorder/extensions/${state.getCrawlerName()}`,
        `--enable-automation`,
    ],
  }
  if (crawlArgs.chromePath) {
    puppeteerOptions.executablePath = crawlArgs.chromePath
  }

  if (crawlArgs.debug === true) {
    puppeteerOptions.headless = false
  }
  const browser = await puppeteer.launch(puppeteerOptions).catch(err => console.log(err))
  const mainPage = (await browser.pages())[0]
  if (crawlArgs.profile.includes('safariProfile')) {
    mainPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15')
  } else if (crawlArgs.profile.includes('chromeProfile')) {
    mainPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36')
  } else {
    logger(`${state.pageDesc(mainPage)} ERROR: UA not set in crawl(), crawler name was ${state.getCrawlerName()}`)
  }

  browser.on('targetcreated', async target => {
    const newPage = await target.page()
    if (newPage === null) {
      return
    }
    if (state.haveLoadedFirstPage === false) {
      return
    }
    if (state.getCrawlerName().includes('safariProfile')) {
      newPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.2 Safari/605.1.15')
    } else if (state.getCrawlerName().includes('chromeProfile')) {
      newPage.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/95.0.4638.69 Safari/537.36')
    } else {
      logger(`${state.pageDesc(newPage)} ERROR: UA not set in new tab handler, crawler name was ${state.getCrawlerName()}`)
    }

    try {
      await instrumentPage(newPage, state, logger, cb)
    } catch (err) {
      logger(`${state.pageDesc(newPage)} Error in instrumentPage, called from new tab handler: \n${err}`)
      return
    }

    logger(` - New tab opened for ${target.url()}`)
    logger(` - Switching to new tab  with URL=${target.url()}`)
    state.commitNavigationAttempt()

    // Add a beforeunload listener to the new page
    try {
      await newPage.evaluate(_ => {
        window.addEventListener('beforeunload', async _ => {
          console.log('before unload', window.location.href)
          try {
            await updateStorage(newPage, state, logger, 'beforeunload')
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
              await updateStorage(newPage, state, logger, 'beforeunload')
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
    // try {
    //   const tmp_pages = await browser.pages()
    //   for (const tmp_page of tmp_pages) {
    //     if (tmp_page !== newPage) {
    //       await tmp_page.removeAllListeners()
    //     }
    //   }
    // } catch (err) {
    //   logger(`${err}\nError while removing listeners from mainPage, returning from targetcreated handler.`)
    // }
  })

  state.setGlobalTimeout(async _ => {
    logger(`${new Date()} Global crawling time limit hit.`)
    // Get the URL of the most recently opened page to be the dst_url.
    // This will PROBABLY work. :/
    const pages = await browser.pages()
    state.dst_url = await pages[pages.length - 1].url()
    await niceClose(browser, logger, state, cb)
  }, crawlArgs.seconds)

  state.setMainFrameId(state.idForFrame(mainPage.mainFrame()))

  try {
    await instrumentPage(mainPage, state, logger, cb)
  } catch (err) {
    logger(`${state.pageDesc(mainPage)} Error in instrumentPage from crawl(): ${err}`)
    return
  }
  state.src_url = crawlArgs.url

  // // Check if settings have been erased
  // await mainPage.goto("chrome://settings/cookies?search=cookies");
  // await mainPage.screenshot({path: state.getCrawlerName()+'.jpg'});

  if (!navigateToUrl(mainPage, crawlArgs.url, state, logger)) {
    await niceClose(browser, logger, state, cb)
  }
}

module.exports.crawl = crawl
module.exports.niceClose = niceClose
module.exports.updateStorage = updateStorage
module.exports.navigateToUrl = navigateToUrl
module.exports.requestListener = requestListener
