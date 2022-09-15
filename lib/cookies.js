'use strict'

const urlsLib = require('./urls')

const listCookies = async (page, time, state) => {
  // If you need all cookies from all domains, use the following commented lines.
  // let c = await page._client.send('Network.getAllCookies');
  // return c['cookies'];

  // If you only need first-party cookies under the page's top level url, you can use page.cookies()
  const cookie_lst = await page.cookies()
  const cookies = {}
  const frame_id = state.idForFrame(page.mainFrame())
  const frameDomain = urlsLib.getHost(page.mainFrame().url())
  for (const c of cookie_lst) {
    const domain = c.domain
    c.ts = time
    c.frameId = frame_id
    c.frameDomain = frameDomain
    if (!(domain in cookies)) {
      cookies[domain] = []
    }
    cookies[domain].push(c)
  }
  return cookies
}

const isSameCookie = (c1, c2) => {
  for (const key of Object
    .keys(c1)) {
    // console.log(key);
    if (c1[key] !== c2[key]) {
      return false
    }
  }
  return true
}

const updateMasterCookieList = (masterList, newList) => {
  for (const domain of Object.keys(newList)) {
    if (!(domain in masterList)) {
      masterList[domain] = []
    }
    for (const newCookie of newList[domain]) {
      let foundMatch = false
      for (const oldCookie of masterList[domain]) {
        if (isSameCookie(newCookie, oldCookie)) {
          foundMatch = true
          break
        }
      }
      if (!foundMatch) {
        masterList[domain].push(newCookie)
      }
    }
  }
  return masterList
}

const findNewCookies = (masterList, newList) => {
  const newCookies = []
  for (const domain of Object.keys(newList)) {
    if (!(domain in masterList)) {
      masterList[domain] = []
    }
    for (const newCookie of newList[domain]) {
      let foundMatch = false
      for (const oldCookie of masterList[domain]) {
        if (isSameCookie(newCookie, oldCookie)) {
          foundMatch = true
          break
        }
      }
      if (!foundMatch) {
        newCookies.push(newCookie)
      }
    }
  }
  return newCookies
}

const updateMasterLocalStorage = (masterList, newList) => {
  for (const domain of Object.keys(newList)) {
    if (!(domain in masterList)) {
      masterList[domain] = {}
    }
    Object.assign(masterList[domain], newList[domain])
  }
  return masterList
}

const listLocalStorage = async (page, time, state) => {
  const frame_id = state.idForFrame(page.mainFrame())
  const frame_domain = urlsLib.getHost(page.mainFrame().url())
  const localStorage = await page.evaluate(async (time, frame_id, frame_domain) => {
    const ls = {}
    const ls_obj = JSON.parse(JSON.stringify(localStorage))
    ls_obj.ts = time
    ls_obj.frame_domain = frame_domain
    ls_obj.frame_id = frame_id
    ls[window.location.origin] = ls_obj
    return ls
  }, time, frame_id, frame_domain)
  return localStorage
}

module.exports.listCookies = listCookies
module.exports.findNewCookies = findNewCookies
module.exports.listLocalStorage = listLocalStorage
module.exports.updateMasterCookieList = updateMasterCookieList
module.exports.updateMasterLocalStorage = updateMasterLocalStorage
