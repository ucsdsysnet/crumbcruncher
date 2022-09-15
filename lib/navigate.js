'use strict'

const urlsLib = require('./urls')
const controllerClientLib = require('./controller_client')

const isVisible = async elm => {
  const boxModel = await elm.boxModel()
  return (boxModel !== null)
}

const fileExtensionsToIgnore = new Set([
  'jpg', 'jpeg', 'png', 'pdf', 'gif', 'zip', 'gz', 'tar', 'bz', 'doc',
  'docx', 'rtf', 'txt', 'avi', 'mov', 'mp4', 'xls', 'xlsx', 'dmg', 'exe',
  'wav', 'mp3', 'aiff'
])

async function autoScroll (page, logger) {
  try {
    await page.waitForFunction(async () => {
      let totalHeight = 0
      const distance = 300
      const timer = setInterval(() => {
        const scrollHeight = document.body.scrollHeight
        window.scrollBy(0, distance)
        totalHeight += distance

        if (totalHeight >= scrollHeight) {
          clearInterval(timer)
          return true
        }
      }, 100)
    }, { timeout: 5000, polling: 10000 })
    return true
  } catch (err) {
    // If the global timeout fires while we're scrolling, this should trigger?
    if (page.isClosed()) {
      logger('Autoscroll: page was closed while scrolling, returning false.')
      return false
    }
    if (err.toString().indexOf('TimeoutError') > -1) {
      // logger("Autoscroll: Timeout triggered, but nothing should be wrong");
      return true
    } else {
      logger(`${err} Autoscroll: non-timeout error, returning false`)
      return false
    }
  }
};

const getIframeSrc = async (frame_ele, page_url) => {
  const frame = await frame_ele.contentFrame()
  if (frame === null) {
    return ''
  }
  if (frame.url()) {
    return frame.url()
  }
  const frame_src = await (await frame_ele.getProperty('src')).jsonValue()
  const frame_src_host = urlsLib.getHost(frame_src)
  if (frame_src_host) {
    return frame_src_host
  }

  let scripts
  try {
    scripts = await frame.$$('script')
  } catch (err) {
    if (frame.isDetached()) {
        return ''
    } else {
        console.log('WARNING: Failed to list scripts in getIframeSrc in navigate.js:', err)
        return ''
    }
  }
  const script_srcs = []
  for (const script of scripts) {
    let src
    try {
      src = await (await script.getProperty('src')).jsonValue()
    } catch (err) {
        console.log('WARNING: Failed to find src for script in getIframeSrc in navigate.js:', err)
        continue
    }
    const src_host = urlsLib.getHost(src)
    if (src_host) {
      script_srcs.push(src_host)
    }
  }
  if (page_url in script_srcs) {
    return page_url
  } else {
    // We don't really care what the src is, as long as it's a different origin than the top level document's url.
    // I could go through and try to find the most common occurrence, but it seems unnecessary.
    return script_srcs[0]
  }
}

const collectIframes = async (page, state, logger, do_autoscroll = true) => {
  const blank_result = {
    sameDomain: [],
    diffDomain: []
  }

  if (do_autoscroll) {
    const scroll_success = await autoScroll(page, logger)
    if (!scroll_success) {
      return {}
    }
  }

  let iframes
  try {
    iframes = await page.$$('iframe')
  } catch (err) {
    logger(`${state.pageDesc(page)} Error collecting iframes: ${err}`)
    return blank_result
  }
  if (iframes === null) {
    // console.log(" No iframes found on", page.url())
    return blank_result
  }

  const valid_iframes = []
  for (const frame_ele of iframes) {
    let frame
    try {
      frame = await frame_ele.contentFrame()
    } catch (err) {
      logger(`${state.pageDesc(page)} Error getting contentFrame: ${err}`)
      continue
    }
    if (frame === null) {
      // The frame may have detached before we could convert it to a frame object.
      continue
    }
    if (frame.parentFrame() === null || frame.parentFrame()?.parentFrame() !== null) {
      // The frame was either the top level frame or a child of a child frame.
      continue
    }
    if (urlsLib.getDomain(frame.url()) === urlsLib.getDomain(page.url())) {
      continue
    }

    const box = await frame_ele.boundingBox()
    if (box === null) {
      // The frame was invisible.
      continue
    }
    valid_iframes.push(frame_ele)
  }

  const same_origin_iframes = []
  const diff_origin_iframes = []
  for (const frame_ele of valid_iframes) {
    const page_url = page.url()
    const iframe_src = await getIframeSrc(frame_ele, page_url)
    if (iframe_src === page_url || iframe_src === 'about:blank') {
      same_origin_iframes.push(frame_ele)
    } else {
      diff_origin_iframes.push(frame_ele)
    }
  }
  return {
    sameDomain: same_origin_iframes,
    diffDomain: diff_origin_iframes
  }
}

const collectAnchors = async (page, state, logger) => {
  const matchingDiffDomainAnchors = []
  const foundDiffDomainHrefs = []
  const matchingSameDomainAnchors = []
  const foundSameDomainHrefs = []
  const blank_result = {
    sameDomain: [],
    diffDomain: []
  }
  const foundAnchorDomains = new Set()
  let num_anchors = 0
  for (const frame of page.frames()) {
    if (frame.isDetached()) {
      continue
    }
    let anchors
    try {
      anchors = await frame.$$('a') // Queries page for a specific selector (tag). Returns <Promise <Array <ElementHandle>>>
    } catch (err) {
      logger(`${state.pageDesc(page)} Error collecting anchors: ${err}`)
      return blank_result
    }
    for (const anchor of anchors) {
        // TODO: Remove?
        if (num_anchors > 50) {
            break
        }
        num_anchors += 1
        
      // If the link isn't visible, ignore it
      if (await isVisible(anchor) === false) {
        continue
      }

      // If the <a> tag doesn't have an href attribute, continue
      let href
      try {
        href = await (await anchor.getProperty('href')).jsonValue()
      } catch (_) {
        continue
      }
      if (href === undefined || href.length < 10) {
        continue
      }
        
      if (urlsLib.isHttpUrl(href) === false) {
        continue
      }

      const possibleFileExt = urlsLib.guessFileExtension(href)
      if (possibleFileExt !== undefined &&
                    fileExtensionsToIgnore.has(possibleFileExt) === true) {
        continue
      }

      const hrefDomain = urlsLib.getDomain(href)
      if (hrefDomain === false) {
        continue
      }

      const isSameDomain = (
        foundAnchorDomains.has(hrefDomain) ||
                state.isNewDomain(href) === false
      )

      foundAnchorDomains.add(hrefDomain)

      if (isSameDomain === true) {
        matchingSameDomainAnchors.push(anchor)
        foundSameDomainHrefs.push(href)
      } else {
          const diff_href = await anchor.evaluate(
            a => a.getAttribute('href')
        );
        matchingDiffDomainAnchors.push(anchor)
        foundDiffDomainHrefs.push(href)
      }
    }
  }

  return {
    sameDomain: matchingSameDomainAnchors,
    diffDomain: matchingDiffDomainAnchors
  }
}

const clickIframe = async (frame_ele, page, state, logger) => {
  const frame = await frame_ele.contentFrame()
  const browser = await page.browser()
  const pages = await browser.pages()
  const numPages = pages.length
  try {
    logger(`${state.pageDesc(page)} About to click iframe with url ${frame.url()} and name ${frame.name()}.`)
    const navigationEvent = {
      url: frame.url(),
      frameId: state.idForFrame(frame),
      frame: frame,
      elementType: 'iframe'
    }
    state.registerNavigationAttempt(navigationEvent, page)

    await Promise.all([
      page.waitForNavigation({ timeout: 10000, waitUntil: 'domcontentloaded' }),
      frame_ele.click()
    ])
    logger(`${state.pageDesc(page)} Navigating (via iframe click) to new page on current tab worked`)
    state.commitNavigationAttempt()
    return true
  } catch (err) {
    // If the error was a timeout, it may be because a new tab was opened and control passed to the new tab handler, which prevented page.waitForFunction() from completing its execution before the timeout.
    // page.waitForFunction would have stopped checking whether state.isInNewTabPhase is true, but the timeout completed anyways.
    // So we have to check for that here, and if it's the case, we were successful, we should exit.
    const newNumPages = await browser.pages()
    if (numPages < newNumPages.length) {
      logger(`${state.pageDesc(page)} Navigation (iframe) opened a new tab successfully.`)
      state.commitNavigationAttempt()
      state.setIsInNewTabPhase(false)
      return true
    }
    if (state.isClosed) {
        logger(`${state.pageDesc(page)} State is closed, niceClose has already been called, new tab probably opened correctly.`)
        return true
    }
    logger(`${state.pageDesc(page)} ${err}`)
    logger(`${state.pageDesc(page)} Clicking iframe did not navigate page.`)
    state.rollbackNavigationAttempt()
    return false
  }
}

const clickAnchor = async (anchor, page, state, logger) => {
  let linkHref
  let linkFrame
  let frameId
  const linkContext = await anchor.executionContext() // kind of like the namespace: variables and their values
  const browser = await page.browser()
  const pages = await browser.pages()
  const numPages = pages.length
  try {
    frameId = state.idForFrame(page.mainFrame())
  } catch (err) {
    logger(`Error in frameId: ${err}`)
  }

  try {
    linkFrame = linkContext && linkContext.frame() // linkFrame is the object you call click on, later (sort of)
    const hrefHandle = await anchor.getProperty('href')
    linkHref = await hrefHandle.jsonValue()
  } catch (_) {
    logger(`${state.pageDesc(page)} Unable to find the elm for ${linkHref}, trying again.`)
    return false
  }

  try {
    // page.on('console', consoleObj => console.log(consoleObj.text()));
    logger(`${state.pageDesc(page)} About to click link for ${linkHref}`)
    // const currentHost = urlsLib.getHost(page.url());
    const navigationEvent = {
      url: linkHref,
      frameId: frameId,
      frame: page.mainFrame(),
      elementType: 'anchor'
    }
    state.registerNavigationAttempt(navigationEvent, page)
    // Click the link
    console.log('Clicking link')
    await Promise.all([
      page.waitForNavigation({ timeout: 10000, waitUntil: 'domcontentloaded' }),
      linkFrame.evaluate(
        inFrameAnchor => inFrameAnchor.click(),
        anchor
      )
    ])
    console.log('Just after clicked link')

    logger(`${state.pageDesc(page)} Navigating (via anchor click) worked`)
    state.commitNavigationAttempt()
    return true
  } catch (err) {
    const newNumPages = await browser.pages()
    if (numPages < newNumPages.length) {
      logger(`${state.pageDesc(page)} Navigation (anchor) opened a new tab successfully.`)
      state.commitNavigationAttempt()
      state.setIsInNewTabPhase(false)
      return true
    } 
    if (state.isClosed) {
        logger(`${state.pageDesc(page)} State is closed, niceClose has already been called, new tab probably opened correctly.`)
        return true
    }
    logger(`${state.pageDesc(page)} ${err}`)
    logger(`${state.pageDesc(page)} Clicking ${linkHref} did not navigate page.`)
    state.rollbackNavigationAttempt()
    return false
  }
}

const manualNavigationAllTypes = async (page, state, logger) => {
  // Fetch all the iframes
  const iframeElms = await collectIframes(page, state, logger)
  if (Object.keys(iframeElms).length === 0) {
    // This will probably be because the global timeout was hit during autoScroll.
    return false
  }
  // Split the list of iframes into same-domain and different-domain
  const sameDomainIframeElms = iframeElms.sameDomain
  const diffDomainIframeElms = iframeElms.diffDomain

  // Repeat for anchors
  const anchorElms = await collectAnchors(page, state, logger)
  const sameDomainAnchorElms = anchorElms.sameDomain
  const diffDomainAnchorElms = anchorElms.diffDomain

  const element_to_click = await controllerClientLib.post(page, {
    sameDomainIframeElms: sameDomainIframeElms,
    sameDomainAnchorElms: sameDomainAnchorElms,
    diffDomainIframeElms: diffDomainIframeElms,
    diffDomainAnchorElms: diffDomainAnchorElms,
    crawler: state.getCrawlerName()
  }, state, logger)

  if (element_to_click === 'NONE' || element_to_click === 'ERROR') {
    console.log("ERROR: element_to_click_type is not set because we're returning too early! Element_to_click:", element_to_click)
    return false
  }

  const key = element_to_click.name
  // Friendly reminder that if this opens a new tab, nothing after the clickIframe or clickElement
  // calls will execute until control is given back to this function. But since right now we exit after
  // only clicking one link, control never DOES come back to this function.
  if (key.includes('Iframe')) {
    state.element_to_click_type = 'IFRAME'
    const iframe_success = await clickIframe(element_to_click.element_to_click, page, state, logger)
    return iframe_success
  } else if (key.includes('Anchor')) {
    state.element_to_click_type = 'ANCHOR'
    const anchor_success = await clickAnchor(element_to_click.element_to_click, page, state, logger)
    return anchor_success
  }
  console.log('Answer formatted incorrectly:', element_to_click)
  return false
}

module.exports.manualNavigationAllTypes = manualNavigationAllTypes
module.exports.clickAnchor = clickAnchor
module.exports.clickIframe = clickIframe
module.exports.autoScroll = autoScroll
module.exports.collectAnchors = collectAnchors
module.exports.collectIframes = collectIframes
