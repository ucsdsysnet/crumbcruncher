'use strict'

const indexLib = require('./index')
indexLib.handler({
  url: process.argv[2],
  chromePath: process.argv[3],
  seconds: +process.argv[4] || 60
}, undefined, result => {
  console.log(JSON.stringify(result))
})
