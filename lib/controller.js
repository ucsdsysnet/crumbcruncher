const http = require('http')
const shuffle = require('shuffle-array')
const controllerClientLib = require('./controller_client')

const createControllerState = _ => {
  const state = {}
  state.responses = {
    safariProfile1: undefined,
    safariProfile2: undefined,
    chromeProfile: undefined
  }
  state.crawler_elements = {
    safariProfile1: undefined,
    safariProfile2: undefined,
    chromeProfile: undefined
  }
  state.visited_hrefs_per_domain = {}

  const allMessagesReceived = _ => {
    for (const key of Object.keys(state.crawler_elements)) {
      if (state.crawler_elements[key] === undefined) {
        return false
      }
    }
    return true
  }

  const clearMessages = _ => {
    for (const key of Object.keys(state.crawler_elements)) {
      state.crawler_elements[key] = undefined
    }
  }

  state.chooseElement = (origin_type, current_url) => {
    // originType is sameDomain or diffDomain
    // state.crawler_elements is a dict of {crawler_name: {sameDomain: {elementName: [attributes]}, diffDomain: {elementName: [attributes]}}
    const common_elements = []

    // const visited_and_unvisited_elements = getVisitedAndUnvisitedElements(current_url, origin_type);
    // const visited_and_unvisited = ['unvisited', 'visited'];
    console.log('Choosing element for origin_type', origin_type)
    for (const element_name of Object.keys(state.crawler_elements.safariProfile1[origin_type])) {
      // console.log(element_name);
      const element = state.crawler_elements.safariProfile1[origin_type][element_name]
      let element_in_all_lists = true
      const common_element = { safariProfile1: element_name }
      for (const crawler of Object.keys(state.crawler_elements)) {
        if (crawler === 'safariProfile1') {
          continue
        }
        // console.log('Looking for matches from crawler', crawler);

        // Is attribute in both other attribute lists?
        for (const tmp_element_name of Object.keys(state.crawler_elements[crawler][origin_type])) {
          const tmp_element = state.crawler_elements[crawler][origin_type][tmp_element_name]
          if (controllerClientLib.isSameElement(element, tmp_element)) {
            common_element[crawler] = tmp_element_name
            break
          }
        }
        if (!(crawler in common_element)) {
          element_in_all_lists = false
          // console.log('\t\tFailed to find match.');
          break
        }
      }
      if (element_in_all_lists) {
        common_elements.push(common_element)
      }
    }

    // Shuffle common elements
    const shuffled_elements = shuffle(common_elements)
    if (shuffled_elements.length === 0) {
      return {
        safariProfile1: 'NONE',
        safariProfile2: 'NONE',
        chromeProfile: 'NONE'
      }
    }
    // for (const element of shuffled_elements) {
    //   console.log(element)
    //   if (element.safariProfile1.includes('_6')) {
    //     return element
    //   }
    // }
    return shuffled_elements[0]
  }

  state.chooseElementOrWait = (body) => {
    if (!(body.crawler in state.crawler_elements) || body.crawler === undefined) {
      console.log('ERROR: crawler name was not recognized:', body.crawler)
    }

    state.crawler_elements[body.crawler] = body
    const currentDomain = body.topLevelFrameDomain
    if (allMessagesReceived()) {
      let element = state.chooseElement('diffDomain', body.topLevelFrameDomain)
      if (element.safariProfile1 === 'NONE') {
        console.log(currentDomain, ': No common diffDomain elements between all crawls.')
        element = state.chooseElement('sameDomain', body.topLevelFrameDomain)
      }
      if (element.safariProfile1 === 'NONE') {
        console.log(currentDomain, ': Error: No common elements between crawls!')
      }
      clearMessages()
      return element
    } else {
      return undefined
    }
  }

  state.sendAllResponses = (element) => {
    for (const crawler of Object.keys(state.responses)) {
      const response = state.responses[crawler]
      response.writeHead(200)
      response.end(element[crawler])
    }
    state.responses = {
      safariProfile1: undefined,
      safariProfile2: undefined,
      chromeProfile: undefined
    }
  }

  return state
}

const requestListener = async (request, response) => {
  let msg_body = ''
  await request.on('data', chunk => {
    msg_body += chunk.toString()
  })

  await request.on('end', _ => {
    const body = JSON.parse(msg_body)

    controller_state.responses[body.crawler] = response
    const element_or_wait = controller_state.chooseElementOrWait(body)
    if (element_or_wait !== undefined) {
      console.log('Enough messages, sending response\n')
      console.log(element_or_wait)
      controller_state.sendAllResponses(element_or_wait)
    } else {
      console.log('Not enough messages have come in yet')
    }
  })
}

const controller_state = createControllerState()
const server = http.createServer(requestListener)
server.listen(8080)

/// ////////////////////////////////
// Tests //////////////////////////
/// ////////////////////////////////

// const testChooseElement = _ => {
//   // state.crawler_elements is a dict of {crawler_name: {sameDomain: {elementName: [attributes]}, diffDomain: {elementName: [attributes]}}
//   const test_state = createControllerState()
//   test_state.crawler_elements = {
//     safariProfile1: {
//       sameDomain: {
//         sameDomainAnchorElms_0: {
//           class: 'testclass',
//           href: 'testhref',
//           onmousedown: 'testonmousedown',
//           x: 0,
//           y: 1,
//           width: 100,
//           height: 200
//         },
//         sameDomainAnchorElms_1: {
//           class: 'testclass1',
//           href: 'testhref1',
//           onmousedown: 'testonmousedown1',
//           x: 2,
//           y: 3,
//           width: 400,
//           height: 500
//         }
//       },
//       diffDomain: {
//         diffDomainAnchorElms_0: {
//           class: 'testclass',
//           href: 'testhref',
//           onmousedown: 'testonmousedown',
//           x: 0,
//           y: 1,
//           width: 100,
//           height: 200
//         },
//         diffDomainAnchorElms_1: {
//           class: 'testclass1',
//           href: 'testhref1',
//           onmousedown: 'testonmousedown1',
//           x: 2,
//           y: 3,
//           width: 400,
//           height: 500
//         }
//       }
//     },
//     safariProfile2: {
//       sameDomain: {
//         sameDomainAnchorElms_0: {
//           class: 'testclass',
//           href: 'testhref',
//           onmousedown: 'testonmousedown',
//           x: 0,
//           y: 1,
//           width: 100,
//           height: 200
//         },
//         sameDomainAnchorElms_1: {
//           class: 'testclass1',
//           href: 'testhref1',
//           onmousedown: 'testonmousedown1',
//           x: 2,
//           y: 3,
//           width: 400,
//           height: 500
//         }
//       },
//       diffDomain: {
//         diffDomainAnchorElms_0: {
//           class: 'testclass',
//           href: 'testhref',
//           onmousedown: 'testonmousedown',
//           x: 0,
//           y: 1,
//           width: 100,
//           height: 200
//         },
//         diffDomainAnchorElms_1: {
//           class: 'testclass1',
//           href: 'testhref1',
//           onmousedown: 'testonmousedown1',
//           x: 2,
//           y: 3,
//           width: 400,
//           height: 500
//         }
//       }
//     },
//     chromeProfile: {
//       sameDomain: {
//         sameDomainAnchorElms_0: {
//           class: 'testclass',
//           href: 'testhref',
//           onmousedown: 'testonmousedown',
//           x: 0,
//           y: 1,
//           width: 100,
//           height: 200
//         },
//         sameDomainAnchorElms_1: {
//           class: 'testclass1',
//           href: 'testhref1',
//           onmousedown: 'testonmousedown1',
//           x: 2,
//           y: 3,
//           width: 400,
//           height: 500
//         }
//       },
//       diffDomain: {
//         diffDomainAnchorElms_0: {
//           class: 'testclass',
//           href: 'testhref',
//           onmousedown: 'testonmousedown',
//           x: 0,
//           y: 1,
//           width: 100,
//           height: 200
//         },
//         diffDomainAnchorElms_1: {
//           class: 'testclass1',
//           href: 'testhref1',
//           onmousedown: 'testonmousedown1',
//           x: 2,
//           y: 3,
//           width: 400,
//           height: 500
//         }
//       }
//     }
//   }
//   const element = test_state.chooseElement('sameDomain')
//   console.log(element)
// }

// testChooseElement();
