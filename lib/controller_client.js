const axios = require('axios')
// const getXPath = require('get-xpath')
axios.defaults.headers.common = {
  'Content-Type': 'application/json'
}
const urlsLib = require('./urls')

const isSameElement = (elm1, elm2) => {
  // If the elements are anchors and they have hrefs with identical URLS (minus query parameters), they're the same.
  if ('href' in elm1 && 'href' in elm2) {
    if (elm1.href.split('?')[0] === elm2.href.split('?')[0]) {
        // console.log('Elements with hrefs', elm1.href, 'and', elm2.href, 'considered the same.')
      return true
    }
  }

  // Failing the ability to compare hrefs, if the two elements have the same keys and same bounding boxes, they are probably the same. Or, if they have the same keys and the same xpath.
  const same_keys = JSON.stringify(Object.keys(elm1).sort()) === JSON.stringify(Object.keys(elm2).sort())
  // I'm going to try taking out the Y-coordinate. I can try fuzzing all the attributes later.
  const same_bounding_box = elm1.x === elm2.x && elm1.width === elm2.width && elm1.height === elm2.height
  // Only compare xpath if both elements have calculated it. 
  let same_xpath = false
  if ('xpath' in elm1 && 'xpath' in elm2) {
      same_xpath = elm1.xpath === elm2.xpath
  }
  if (same_keys && same_bounding_box || same_keys && same_xpath) {
    return true
  }
  return false
}

const elementToJson = async (page, ele, find_xpath) => {
  let element_attributes
  try {
    element_attributes = await ele.evaluate((element, find_xpath) => {
        let path = ''
        const attribute_list = Array.from(element.attributes, ({ name, value }) => `${name}: ${value}`)
        const attribute_dict = {}
        for (const attribute of attribute_list) {
            attribute_dict[attribute.split(':')[0]] = attribute.split(/:(.+)/)[1]
        }
        if (!find_xpath) {
            return attribute_dict
        }
        while (element.parentNode !== null) {
            var ix= 0;
            var siblings= element.parentNode.childNodes;
            for (var i= 0; i<siblings.length; i++) {
                var sibling= siblings[i];
                if (sibling===element) {
                    break
                }
                if (sibling.nodeType===1 && sibling.tagName===element.tagName) {
                    ix++;
                }
            }
            path = element.tagName + '['+(ix+1)+']/' + path
            element = element.parentNode
        }
        attribute_dict['xpath'] = path
        return attribute_dict
      }, ele, find_xpath)
  } catch (err) {
    console.log('Error occurred (element context changed before eval?)')
    console.log(err)
    return {}
  }

  // Add the position and size of the element
  try {
    const { x, y, width, height } = await ele.boundingBox()
    element_attributes.x = x
    element_attributes.y = y
    element_attributes.width = width
    element_attributes.height = height
  } catch (err) {
    // If the element has no position, don't add it to the list.
    // console.log('Error!', element_attributes, err);
    return {}
  }
  return element_attributes
}

const flattenElements = async (page, body) => {
  // console.log('Message body:', body);
  const flat_same_domain = {}
  const flat_diff_domain = {}
  const named_elements = {}
  const named_json_elements = {}

  for (const key of Object.keys(body)) {
    if (key === 'crawler' || key === 'topLevelFrameDomain') {
      continue
    }

    let idx = 0
    for (const ele of body[key]) {
      const flat_key = key + '_' + idx.toString()
      // remove element_handle from ele because it won't serialize,and add it to named_elements
      named_elements[flat_key] = ele.element_handle
      named_json_elements[flat_key] = await elementToJson(page, ele.element_handle, idx<20)
      ele.element_handle = ''

      if (key.includes('sameDomain')) {
        flat_same_domain[flat_key] = ele
      } else {
        flat_diff_domain[flat_key] = ele
      }
      idx++
    }
  }

  return {
    final_msg: {
      sameDomain: flat_same_domain,
      diffDomain: flat_diff_domain,
      crawler: body.crawler,
      topLevelFrameDomain: body.topLevelFrameDomain
    },
    named_elements: named_elements,
    named_json_elements: named_json_elements
  }
}

const createMessage = async (page, msg) => {
  const formatted_msg = {}
  for (const key of Object.keys(msg)) {
    if (key === 'crawler') {
      continue
    }
    formatted_msg[key] = []
    let num_eles = 0
    for (const ele of Object.keys(msg[key])) {
      const element_attributes = await elementToJson(page, msg[key][ele], num_eles<20)

      // Keep original ElementHandle for the moment
      element_attributes.element_handle = msg[key][ele]

      formatted_msg[key].push(element_attributes)
      num_eles++
    }
    const top_level_frame_url = page.url()
    formatted_msg.topLevelFrameDomain = urlsLib.getHost(top_level_frame_url)
    formatted_msg.crawler = msg.crawler
  }
  return formatted_msg
}

const post = async (page, msg, state, logger) => {
  logger(`${state.pageDesc(page)} Sending POST request...`)
  const formatted_msg = await createMessage(page, msg)
  const flattened_elements = await flattenElements(page, formatted_msg)
  const named_elements = flattened_elements.named_elements
  const named_json_elements = flattened_elements.named_json_elements
  const final_msg = flattened_elements.final_msg
  // console.log('Formatted message:', final_msg);
  const element_to_click = await axios.post('http://localhost:8080/', final_msg)
    .then(function (response) {
      // handle success
      logger(`${state.pageDesc(page)} POST response received.`)
      return response.data
      // Handle the case where element = 'NONE' and where element is the element to click.
    })
    .catch(function (error) {
      // handle error
      logger(`${state.pageDesc(page)} Error getting post response:`)
      console.log(error)
      return 'ERROR'
    })
  if (element_to_click === 'ERROR' || element_to_click === 'NONE') {
    return element_to_click
  }
  state.element_to_click = named_json_elements[element_to_click]

  return { name: element_to_click, element_to_click: named_elements[element_to_click] }
}

// for (const name of crawler_names) {
//     post({
//         'sameDomainIframeElms': [],
//         'sameDomainAnchorElms': [],
//         'diffDomainIframeElms': [],
//         'diffDomainAnchorElms': [],
//         'crawler': name,
//     });
// }

module.exports.post = post
module.exports.elementToJson = elementToJson
module.exports.isSameElement = isSameElement
