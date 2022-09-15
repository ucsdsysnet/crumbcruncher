const fs = require('fs')

const writeCookieResults = (state, outfile) => {
  // console.log(state.masterCookieList);
  const header = ['frameId', 'frameDomain', 'name', 'value', 'domain', 'path', 'expires', 'size', 'httpOnly', 'secure', 'session', 'sameSite', 'sameParty', 'sourceScheme', 'sourcePort', 'ts']
  let line = ''
  for (const h of header) {
    line += h + ','
  }
  try {
    fs.writeFileSync(outfile, line + '\n', { flag: 'w' })
  } catch (err) {
    console.error(err)
  }
  if (!state.masterCookieList) {
    return
  }
  for (const url of Object.keys(state.masterCookieList)) {
    // console.log("List[url]:", state.masterCookieList[url]);
    for (const i in state.masterCookieList[url]) {
      let line = ''
      for (const h of header) {
        line += '`' + state.masterCookieList[url][i][h] + '`,'
      }
      try {
        fs.writeFileSync(outfile, line + '\n', { flag: 'a+' })
      } catch (err) {
        console.error(err)
      }
    }
  }
}

const writeLocalStorage = (state, outfile) => {
  const header = ['domain', 'key', 'value', 'ts', 'frameId', 'frameDomain']
  let line = ''
  for (const h of header) {
    line += h + ','
  }
  try {
    fs.writeFileSync(outfile, line + '\n', { flag: 'w' })
  } catch (err) {
    console.error(err)
  }
  if (!state.masterLocalStorage) {
    return
  }
  for (const url of Object.keys(state.masterLocalStorage)) {
    // console.log("Local storage:", state.masterLocalStorage[url]);
    for (const key of Object.keys(state.masterLocalStorage[url])) {
      if (key === 'frame_id' || key === 'ts' || key === 'frame_domain') {
        continue
      }
      const line = '`' + url + '`,`' + key + '`,`' + state.masterLocalStorage[url][key] + '`,`' + state.masterLocalStorage[url].ts + '`,`' + state.masterLocalStorage[url].frame_id + '`,`' + state.masterLocalStorage[url].frame_domain
      try {
        fs.writeFileSync(outfile, line + '\n', { flag: 'a+' })
      } catch (err) {
        console.error(err)
      }
    }
  }
}

const writeCrawlEvents = (crawlEvents, outfile) => {
  const header = ['url', 'type', 'time', 'frameId', 'frameDomain', 'frameTree', 'topLevelFrameDomain', 'expectedUrl', 'resourceType', 'redirectTo', 'isRedirect', 'redirectDomain', 'queryParams', 'cookie']
  let line = ''
  for (const h of header) {
    line += h + ','
  }
  try {
    fs.writeFileSync(outfile, line + '\n', { flag: 'w' })
  } catch (err) {
    console.error(err)
  }
  for (const event of crawlEvents) {
    line = ''
    for (const h of header) {
      if (h in event) {
        line += '`' + event[h] + '`'
      }
      line += ','
    }
    try {
      fs.writeFileSync(outfile, line + '\n', { flag: 'a+' })
    } catch (err) {
      console.error(err)
    }
  }
}

const writeInfoForRedoCrawler = (state, outfile) => {
  const info = {
    element_to_click: state.element_to_click,
    element_type: state.element_to_click_type,
    src_url: state.src_url,
    dst_url: state.dst_url
  }
  const info_str = JSON.stringify(info)
  try {
    fs.writeFileSync(outfile, info_str)
  } catch (err) {
    console.error(err)
  }
}

module.exports.writeCrawlEvents = writeCrawlEvents
module.exports.writeLocalStorage = writeLocalStorage
module.exports.writeCookieResults = writeCookieResults
module.exports.writeInfoForRedoCrawler = writeInfoForRedoCrawler
