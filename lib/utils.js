'use strict'

const urlLib = require('url')

module.exports.validateArgs = args => {
  if (args.url === undefined) {
    return {
      msg: "'url' argument must be provided"
    }
  }

  try {
    new urlLib.URL(args.url)
  } catch (e) {
    console.log(e)
    return {
      msg: e,
      value: args.url
    }
  }

  if (args.seconds !== undefined) {
    if (typeof args.seconds !== 'number') {
      return {
        msg: 'Seconds must be a number, or not provided.',
        value: args.seconds
      }
    }

    if (args.seconds <= 0 || args.seconds > 300) {
      return {
        msg: 'Seconds must fall within (0, 300].',
        value: args.seconds
      }
    }
  }

  if (args.debug !== undefined && typeof args.debug !== 'boolean') {
    return {
      msg: 'If provided, debug must be a boolean.',
      value: args.debug
    }
  }
}
