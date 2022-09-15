/**
 * @file
 * Library for managing state during a crawl.
*/
'use strict'

const urlsLib = require('./urls')

const createState = (crawler) => {
  const state = Object.create(null)
  const crawlEvents = []
  const visitedDomains = new Set()
  const pageNavigationTimerIdMapping = new WeakMap()
  const pageTimeouts = new Set()
  const frameMapping = new WeakMap()
  const frameIdToDomain = new Map()
  let mainFrameId
  let _frameId = 0
  let globalTimeout
  state.isClosed = false

  // New stuff for new type of crawler
  state.element_to_click = {}
  state.element_to_click_type = ''
  state.src_url = ''
  state.dst_url = ''
  state.crawlFailed = false
  state.hasNavigated = false

  state.getDomainForFrame = frame => {
    const frameId = state.idForFrame(frame)
    const domain = frameIdToDomain.get(frameId)
    if (domain !== undefined) {
      return domain
    }

    // Check if frame.url() is populated yet
    const url = frame.url()
    if (url.length > 1) {
      const newDomain = urlsLib.getHost(url)
      state.setDomainForFrame(frame, newDomain)
      return newDomain
    }
    return 'unknown_domain'
  }

  state.setDomainForFrame = (frame, domain) => {
    let existingFrameId = frameMapping.get(frame)
    // console.log("Setting domain", domain, "for frame", existingFrameId);
    if (existingFrameId === undefined) {
      frameMapping.set(frame, ++_frameId)
      existingFrameId = _frameId
    }
    frameIdToDomain.set(existingFrameId, domain)
    // console.log(frameIdToDomain);
  }

  state.idForFrame = frame => {
    const existingFrameId = frameMapping.get(frame)
    // console.log("frameId is", _frameId, existingFrameId);
    if (existingFrameId !== undefined) {
      return existingFrameId
    }
    frameMapping.set(frame, ++_frameId)
    return _frameId
  }

  state.frameDesc = frame => {
    const frameId = state.idForFrame(frame)
    const frameUrl = urlsLib.getHost(frame.url())
    return `${new Date()}:${frameId}:${frameUrl}:`
  }

  state.pageDesc = page => {
    try {
      return state.frameDesc(page.mainFrame())
    } catch (err) {
      console.log('Error in pageDesc:', err)
      return ''
    }
  }

  state.setMainFrameId = frameId => {
    mainFrameId = frameId
  }
  state.getMainFrameId = _ => mainFrameId
  state.getCrawlerName = _ => crawler.split('/')[3]

  state.haveLoadedFirstPage = false

  const setGlobalTimeout = (cb, sec) => {
    if (globalTimeout !== undefined) {
      clearTimeout(globalTimeout)
    }
    globalTimeout = setTimeout(_ => {
      if (state.isClosed === false) {
        cb()
      }
    }, sec * 1000)
  }
  state.setGlobalTimeout = setGlobalTimeout

  const cancelTimeoutForPage = page => {
    const timerId = pageNavigationTimerIdMapping.get(page)
    if (timerId === undefined) {
      return false
    }

    clearTimeout(timerId)
    pageNavigationTimerIdMapping.delete(page)
    pageTimeouts.delete(timerId)
    return true
  }
  state.cancelTimeoutForPage = cancelTimeoutForPage

  const setTimeoutForPage = (page, cb, secs) => {
    cancelTimeoutForPage(page)
    const timerId = setTimeout(_ => {
      if (state.isClosed === false) {
        cb()
      }
    }, secs)
    pageNavigationTimerIdMapping.set(page, timerId)
    pageTimeouts.add(timerId)
  }
  state.setTimeoutForPage = setTimeoutForPage

  state.addVisitedDomain = url => {
    const domain = urlsLib.getDomain(url)
    if (domain === false) {
      return false
    }
    visitedDomains.add(domain)
    return true
  }

  state.isNewDomain = url => {
    const domain = urlsLib.getDomain(url)
    return !visitedDomains.has(domain)
  }

  let isInNewTabPhase = false
  let navigationAttempt
  state.masterCookieList = {}
  state.masterLocalStorage = {}

  // Pushes the request record onto the stack, unless
  // the top item on the log is a navigation record,
  // in which case we just annotate the navigation
  // record with the URL that was actually fetched
  // during the navigation.
  const addRequestRecord = requestRecord => {
    const numEvents = crawlEvents.length
    if (numEvents === 0) {
      throw new Error('Trying to push a request record w/o any navigation records on the stack.')
    }

    // I have to comment this out because it doesn't always work:
    // we saw cases where this if statement was triggered but the wrong URL was put there.
    // The request that the request handler saw was NOT the request that the
    // topEventRecord had recorded as a navigation event, so the output file made it look
    // like we had tried to navigate to a URL that we had never tried to navigate to.

    // const topEventRecord = crawlEvents[numEvents - 1];
    // if (topEventRecord.type === "navigation" &&
    //         topEventRecord.url === undefined &&
    //         topEventRecord.frameId === requestRecord.frameId) {
    //     topEventRecord.url = requestRecord.url;
    //     return;
    // }

    crawlEvents.push(requestRecord)
  }

  const getFrameTree = frame => {
    let frame_tree = state.idForFrame(frame).toString()

    while (frame.parentFrame() !== null) {
      frame = frame.parentFrame()
      frame_tree += '-' + state.idForFrame(frame).toString()
    }
    return frame_tree
  }

  state.pushRequest = (request, frameId, isRedirect, redirectDomain, queryParams, frame, page) => {
    const url = request.url()

    if (url.indexOf('http') !== 0) {
      return
    }

    const frameTree = getFrameTree(frame)
    const frameDomain = state.getDomainForFrame(frame)
    const requestRecord = {
      type: 'request',
      time: Date.now(),
      frameId: frameId,
      frameTree: frameTree,
      frameDomain: frameDomain,
      url: url,
      topLevelFrameDomain: page.mainFrame().url(),
      isRedirect: isRedirect,
      redirectDomain: redirectDomain,
      queryParams: queryParams,
      resourceType: request.resourceType(),
      redirectTo: ''
    }

    addRequestRecord(requestRecord)
  }

  state.registerNavigationAttempt = (record, page) => {
    const frameTree = getFrameTree(record.frame)
    const frameDomain = state.getDomainForFrame(record.frame)
    if (navigationAttempt !== undefined) {
      console.log('WARNING: Overwriting navigationAttempt without committing or rolling back the last attempt!')
      console.log('Old navigation attempt:', navigationAttempt)
      // If there's still an old navigation attempt that hasn't been committed, but a new one was made, it probably
      // means the old one must have succeeded because the crawler would otherwise have just waited for the previous one to fail.
      crawlEvents.push(navigationAttempt)
    }
    navigationAttempt = {
      type: 'navigation',
      time: Date.now(),
      frameId: record.frameId,
      expectedUrl: record.url, // This is the href of the anchor element if we're clicking an anchor.
      frameTree: frameTree,
      frameDomain: frameDomain,
      topLevelFrameDomain: page.mainFrame().url(),
      elementType: record.elementType
    }
  }

  state.pushNavigation = (record, page) => {
    const frameTree = getFrameTree(record.frame)
    crawlEvents.push({
      type: 'navigation',
      time: Date.now(),
      frameId: record.frameId,
      expectedUrl: record.url,
      frameTree: frameTree,
      topLevelFrameDomain: page.mainFrame().url()
    })
  }

  state.commitNavigationAttempt = _ => {
    if (navigationAttempt === undefined) {
      return false
    }
    crawlEvents.push(navigationAttempt)
    navigationAttempt = undefined
    return true
  }

  state.rollbackNavigationAttempt = _ => {
    navigationAttempt = undefined
  }

  state.setIsInNewTabPhase = phase => {
    isInNewTabPhase = phase
  }

  state.getCrawlEvents = _ => crawlEvents
  state.getFrameIdToDomain = _ => frameIdToDomain

  state.getIsInNewTabPhase = _ => {
    return isInNewTabPhase
  }

  state.sitesVisited = _ => {
    let count = 0
    for (const event of crawlEvents) {
      if (event.type === 'navigation') {
        count++
      }
    }
    return count
  }

  state.close = _ => {
    state.isClosed = true
    try {
      clearTimeout(globalTimeout)
    } catch (_) {
      // console.log(_);
      // pass
    }

    for (const timerId of Array.from(pageTimeouts)) {
      try {
        clearTimeout(timerId)
      } catch (_) {
        // console.log(_);
        // pass
      }
    }
  }

  return state
}

module.exports.createState = createState
